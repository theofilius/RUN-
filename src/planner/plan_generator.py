"""Generate next week's runs from your real data, each with a reason.

Steps:
  1. context()       - read the last 4 weeks: volume, longest run, easy %,
                       days since the last race, current efficiency.
  2. choose_week()   - pick the kind of week with simple, ordered rules:
                         recent race       -> recovery: all easy, no progression
                         easy runs too hard -> hold volume, all easy, HR cap
                         otherwise         -> build: +10% volume, one tempo run
  3. build_plan()    - split the week's distance into runs, attach HR caps
                       and pace estimates, then run the safety checks.

Targets are heart-rate first. Paces are estimates from your recent
efficiency, already in your usual Jakarta heat.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from src.analysis.easy_check import weekly_check
from src.analysis.fitness_trend import training_runs_with_efficiency
from src.config import EASY_HR_MAX, LONG_RUN_DAY, MAX_HR, OTHER_RUN_DAYS, RACES
from src.planner import safety_rules
from src.units import format_pace

LOOKBACK_WEEKS = 4
EASY_PCT_TOO_LOW = 50       # below this, fix easy running before adding intensity
LONG_RUN_SHARE = 0.40       # long run at most 40% of the week's distance
MIN_RUN_KM = 3.0
TEMPO_HR = (round(0.85 * MAX_HR), round(0.90 * MAX_HR))  # "comfortably hard"


@dataclass
class Step:
    name: str            # "warm-up", "easy", "tempo", "cool-down"
    distance_km: float
    hr_max: int
    hr_min: int | None = None


@dataclass
class Workout:
    day: date
    kind: str            # "easy", "long", "tempo"
    steps: list[Step] = field(default_factory=list)
    reason: str = ""

    @property
    def distance_km(self):
        return sum(step.distance_km for step in self.steps)

    @property
    def is_hard(self):
        return any(step.hr_min is not None for step in self.steps)


def round_half(km):
    """Round to the nearest 0.5 km - easier to follow on a watch."""
    return round(km * 2) / 2


def pace_at_hr(efficiency, hr):
    """Estimated seconds per km at a heart rate, from efficiency (m/min per bpm)."""
    return 1000 / (efficiency * hr) * 60


def context(runs, plan_start):
    """Everything the rules need, from the LOOKBACK_WEEKS weeks before plan_start."""
    window_start = plan_start - pd.Timedelta(weeks=LOOKBACK_WEEKS)
    recent = runs[(runs["start_time"] >= window_start) & (runs["start_time"] < plan_start)]

    race_starts = pd.to_datetime([race["start"] for race in RACES.values()])
    recent_training = recent[~recent["start_time"].isin(race_starts)]
    past_races = race_starts[race_starts < plan_start]
    days_since_race = (plan_start - past_races.max()).days if len(past_races) else None

    weekly = weekly_check(recent) if len(recent) else None
    easy_pct = 100 * weekly["easy_time_s"].sum() / weekly["moving_time_s"].sum() if weekly is not None else 0

    acwr = safety_rules.weekly_acwr(runs, plan_start - pd.Timedelta(days=1)).tail(LOOKBACK_WEEKS)
    empty_weeks = [f"{p.start_time:%d %b}" for p, km in acwr["km"].items() if km == 0]

    efficiency = training_runs_with_efficiency(recent)["efficiency"].median()

    return {
        "plan_start": plan_start,
        "baseline_km": recent["distance_km"].sum() / LOOKBACK_WEEKS,
        "runs_per_week": len(recent) / LOOKBACK_WEEKS,
        "longest_recent_km": recent_training["distance_km"].max(),
        "easy_pct": easy_pct,
        "days_since_race": days_since_race,
        "efficiency": efficiency,
        "empty_weeks": empty_weeks,
    }


def choose_week(ctx):
    """Pick the week type. Rules are checked in order; the first match wins."""
    if ctx["days_since_race"] is not None and ctx["days_since_race"] < safety_rules.RECOVERY_DAYS:
        return "recovery", 1.0, (
            f"Your last race was {ctx['days_since_race']} days before this week. A common guideline "
            f"is about one easy day per mile raced (~13 days for a half), so this week stays easy "
            f"and does not add distance."
        )
    if ctx["easy_pct"] < EASY_PCT_TOO_LOW:
        return "fix easy", 1.0, (
            f"Only {ctx['easy_pct']:.0f}% of your last {LOOKBACK_WEEKS} weeks was easy (target 80%). "
            f"Adding harder work on top would pile on fatigue, so distance holds and every run is "
            f"capped at {EASY_HR_MAX} bpm."
        )
    return "build", 1 + safety_rules.MAX_WEEKLY_INCREASE, (
        f"Easy running is under control ({ctx['easy_pct']:.0f}% easy) and there is no recent race, "
        f"so distance goes up 10% and one tempo run adds race-pace work."
    )


def run_days(n_runs, plan_start):
    """Dates for the week: the long run day plus the first preferred other days."""
    days = sorted([LONG_RUN_DAY] + OTHER_RUN_DAYS[: n_runs - 1])
    return [plan_start.date() + timedelta(days=d) for d in days]


def easy_step(km):
    return Step("easy", km, hr_max=EASY_HR_MAX)


def build_plan(runs, plan_start):
    """Create next week's plan and its safety checks."""
    plan_start = pd.Timestamp(plan_start).normalize()
    ctx = context(runs, plan_start)
    week_type, volume_factor, why = choose_week(ctx)

    target_km = ctx["baseline_km"] * volume_factor
    n_runs = max(3, min(5, round(ctx["runs_per_week"])))

    # Long run: grows by at most MAX_LONG_RUN_STEP_KM, and only in non-recovery weeks.
    step = 0 if week_type == "recovery" else 1.0
    long_km = round_half(max(MIN_RUN_KM, min(ctx["longest_recent_km"] + step, LONG_RUN_SHARE * target_km)))
    other_km = max(MIN_RUN_KM, round_half((target_km - long_km) / (n_runs - 1)))
    # Rounding can push the total over the target; trim the other runs if so.
    while long_km + other_km * (n_runs - 1) > target_km + 0.25 and other_km > MIN_RUN_KM:
        other_km -= 0.5

    days = run_days(n_runs, plan_start)
    workouts = []
    for day in days:
        if day.weekday() == LONG_RUN_DAY:
            workouts.append(Workout(day, "long", [easy_step(long_km)],
                                    f"Long run builds endurance for the half; kept easy (HR ≤ {EASY_HR_MAX})."))
        else:
            workouts.append(Workout(day, "easy", [easy_step(other_km)],
                                    f"Easy aerobic run. Walk briefly whenever HR passes {EASY_HR_MAX}."))

    if week_type == "build":
        # First weekday run becomes a tempo (furthest from the long run):
        # warm-up, tempo block, cool-down.
        tempo = next(w for w in workouts if w.kind == "easy")
        block = max(1.0, round_half(tempo.distance_km - 2.5))
        tempo.kind = "tempo"
        tempo.steps = [
            Step("warm-up", 1.5, hr_max=EASY_HR_MAX),
            Step("tempo", block, hr_min=TEMPO_HR[0], hr_max=TEMPO_HR[1]),
            Step("cool-down", 1.0, hr_max=EASY_HR_MAX),
        ]
        tempo.reason = ("Tempo because your aerobic base improved but there has been no "
                        "sustained race-pace work; teaches you to hold a strong, steady effort.")

    checks = [
        safety_rules.check_weekly_increase(sum(w.distance_km for w in workouts), ctx["baseline_km"]),
        safety_rules.check_long_run(long_km, ctx["longest_recent_km"]),
        safety_rules.check_no_hard_after_race(workouts, ctx["days_since_race"]),
        safety_rules.check_recent_spikes(runs, plan_start),
    ]

    return {
        "week_type": week_type,
        "why": why,
        "context": ctx,
        "target_km": target_km,
        "workouts": workouts,
        "checks": checks,
        "easy_pace_s": pace_at_hr(ctx["efficiency"], EASY_HR_MAX),
        "tempo_pace_s": pace_at_hr(ctx["efficiency"], TEMPO_HR[0]),
    }


def next_monday(today=None):
    today = today or date.today()
    return today + timedelta(days=7 - today.weekday())


def print_plan(plan):
    ctx = plan["context"]
    total = sum(w.distance_km for w in plan["workouts"])
    print(f"PLAN FOR THE WEEK OF {ctx['plan_start']:%a %d %b %Y}  -  {plan['week_type'].upper()} WEEK\n")
    print(f"Why: {plan['why']}\n")

    for w in plan["workouts"]:
        print(f"  {w.day:%a %d %b}  {w.kind:<6} {w.distance_km:>4.1f} km")
        for s in w.steps:
            hr = f"HR {s.hr_min}-{s.hr_max}" if s.hr_min else f"HR ≤ {s.hr_max}"
            print(f"      {s.name:<10} {s.distance_km:>4.1f} km  {hr}")
        print(f"      reason: {w.reason}")
    print(f"\n  Total {total:.1f} km over {len(plan['workouts'])} runs. "
          f"Easy pace guide ~{format_pace(plan['easy_pace_s'])}/km at {EASY_HR_MAX} bpm "
          f"- follow HR, not pace.")

    print("\nSAFETY CHECKS")
    for c in plan["checks"]:
        mark = "PASS" if c["passed"] else "FLAG"
        print(f"  [{mark}] {c['rule']}: {c['detail']}")
        print(f"         {c['formula']}")

    print("\nBASED ON (last 4 weeks)")
    print(f"  average {ctx['baseline_km']:.1f} km/week, {ctx['runs_per_week']:.1f} runs/week, "
          f"longest training run {ctx['longest_recent_km']:.1f} km, {ctx['easy_pct']:.0f}% easy, "
          f"efficiency {ctx['efficiency']:.3f}")
    if ctx["empty_weeks"]:
        print(f"  note: no runs recorded in week(s) of {', '.join(ctx['empty_weeks'])} - counted as 0 km. "
              f"If you ran, export again and re-run.")
    print("\nNot medical advice. Stop and rest if something hurts.")


if __name__ == "__main__":
    # python -m src.planner.plan_generator "data/Running Data may-oct.csv" [YYYY-MM-DD]
    import sys

    from src.analysis.heat_adjust import load_runs_with_heat

    runs = load_runs_with_heat(sys.argv[1])
    start = sys.argv[2] if len(sys.argv) > 2 else next_monday()
    print_plan(build_plan(runs, start))
