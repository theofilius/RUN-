"""Generate next week's runs from your real data, each with a reason.

Steps:
  1. context()       - read the last 4 weeks: volume, longest run, easy %,
                       days since the last race, current efficiency.
  2. choose_week()   - pick the kind of week with simple, ordered rules:
                         recent race       -> recovery: all easy, no progression
                         easy runs too hard -> hold volume, all easy, HR cap
                         otherwise         -> build: +10% volume, one tempo run
  3. build_plan()    - split the week's distance into runs, give every run a
                       warm-up / main / cool-down menu, fill the other days
                       with rest, then run the safety checks.

Every step has a distance, a heart-rate range and a pace range. Targets are
heart-rate first; paces are estimates from your recent efficiency, already
in your usual Jakarta heat.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from src.analysis.easy_check import weekly_check
from src.analysis.fitness_trend import training_runs_with_efficiency
from src.config import (
    EASY_HR_FRACTION, EASY_HR_MAX, INJURED_LAST_12_MONTHS, LONG_RUN_DAY, MAX_HR, OTHER_RUN_DAYS, RACES,
    RUNS_PER_WEEK, START_RUNS_PER_WEEK, WEEKLY_GROWTH,
)
from src.evidence import describe
from src.planner import safety_rules
from src.units import format_pace

LOOKBACK_WEEKS = 4
EASY_PCT_TOO_LOW = 50       # below this, fix easy running before adding intensity
MIN_RUN_KM = 5.0            # shortest easy/tempo run - your usual minimum
LONG_RUN_STEP_KM = 1.0      # weekly long-run growth when last week's long run was done
LONG_RUN_MAX_KM = 21.0      # Fokkema 2020: a longest run over 21 km linked to faster halves
FUEL_AFTER_MIN = 60         # Racinais 2015: fluids, sodium and carbs for exercise over 1 h

# Heart-rate zones as (low, high) bpm.
WARMUP_HR = (round(0.60 * MAX_HR), round(0.70 * MAX_HR))  # very easy jog / brisk walk
EASY_HR = (round(0.70 * MAX_HR), EASY_HR_MAX)             # below the first threshold
TEMPO_HR = (round(0.85 * MAX_HR), round(0.90 * MAX_HR))   # "comfortably hard"
INTERVAL_HR = (round(0.90 * MAX_HR), round(0.95 * MAX_HR))  # hard repeats
REP_KM, JOG_KM = 0.8, 0.4                                   # 800 m repeats, 400 m jog between
STRIDES_AFTER_RACE_DAYS = 7                                 # no strides in the first week after a race

WARMUP_NOTE = f"Start with 3-5 min brisk walking, then jog very gently. Walk if HR passes {WARMUP_HR[1]}."
COOLDOWN_NOTE = "Jog very gently, then walk the last few minutes. Drink and stretch afterwards."


@dataclass
class Step:
    name: str            # "warm-up", "easy", "tempo", "cool-down"
    distance_km: float
    hr_min: int
    hr_max: int
    pace_fast_s: float   # estimated pace at hr_max (s/km)
    pace_slow_s: float   # estimated pace at hr_min (s/km)
    note: str = ""

    @property
    def minutes(self):
        """Estimated duration at the middle of the pace range."""
        return self.distance_km * (self.pace_fast_s + self.pace_slow_s) / 2 / 60


@dataclass
class Workout:
    day: date
    kind: str            # "easy", "long", "tempo", "rest"
    steps: list[Step] = field(default_factory=list)
    reason: str = ""

    @property
    def distance_km(self):
        return sum(step.distance_km for step in self.steps)

    @property
    def minutes(self):
        return sum(step.minutes for step in self.steps)

    @property
    def is_hard(self):
        return any(step.name in ("tempo", "interval") for step in self.steps)


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

    # Easy share of training only: a race is meant to be hard.
    weekly = weekly_check(recent_training) if len(recent_training) else None
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
        "last_race": past_races.max() if len(past_races) else None,
        "efficiency": efficiency,
        "empty_weeks": empty_weeks,
    }


def choose_week(ctx):
    """Pick the week type. Rules are checked in order; the first match wins.

    Returns (week type, why, source keys).
    """
    if ctx["days_since_race"] is not None and ctx["days_since_race"] < safety_rules.RECOVERY_DAYS:
        return "recovery", (
            f"Your last race was {ctx['days_since_race']} day{'s' if ctx['days_since_race'] != 1 else ''} "
            f"before this week. A common guideline "
            f"is about one easy day per mile raced (~13 days for a half), so every run stays easy: "
            f"no tempo or intervals yet."
        ), ["own"]
    if ctx["easy_pct"] < EASY_PCT_TOO_LOW:
        return "fix easy", (
            f"Only {ctx['easy_pct']:.0f}% of your last {LOOKBACK_WEEKS} weeks of training was easy (target: "
            f"mostly easy). Adding hard work on top would pile on fatigue, so every run stays easy "
            f"(HR ≤ {EASY_HR_MAX}) and there is no tempo."
        ), ["rosenblat2025", "own"]
    if INJURED_LAST_12_MONTHS:
        return "build", (
            f"Easy running is under control ({ctx['easy_pct']:.0f}% easy), so one tempo run is added. "
            f"No extra runs, because you had an injury in the last 12 months - the strongest injury "
            f"predictor in recreational runners."
        ), ["rosenblat2025", "fokkema2020"]
    return "build", (
        f"Easy running is under control ({ctx['easy_pct']:.0f}% easy) and there is no recent race, "
        f"so one hard session a week adds faster work: tempo and intervals in turn."
    ), ["rosenblat2025", "casado2022"]


def week_dates(plan_start):
    """The 7 dates of the plan, starting on plan_start (any weekday)."""
    return [plan_start.date() + timedelta(days=i) for i in range(7)]


def run_days(n_runs, plan_start, rest_until=None, first_day=None):
    """n_runs dates in the plan week: the long run day first, then preferred days.

    Days inside the post-race rest window are skipped, so a run that would
    land there moves to the next preferred free day instead of disappearing.
    first_day: the day training starts - no runs before it, and it is a run day.
    """
    allowed = {d.weekday(): d for d in week_dates(plan_start)
               if (rest_until is None or d > rest_until) and (first_day is None or d >= first_day)}
    preference = [LONG_RUN_DAY, *OTHER_RUN_DAYS]
    if first_day is not None and first_day.weekday() in allowed:
        preference = [first_day.weekday()] + [w for w in preference if w != first_day.weekday()]
    return sorted([allowed[w] for w in preference if w in allowed][:n_runs])


def make_step(name, km, hr, efficiency, note):
    """A step with its HR range and the pace range that HR range implies."""
    low, high = hr
    return Step(name, km, hr_min=low, hr_max=high,
                pace_fast_s=pace_at_hr(efficiency, high), pace_slow_s=pace_at_hr(efficiency, low),
                note=note)


def easy_run(day, km, eff, strides=False):
    note = f"Conversational effort. Walk 1 min whenever HR passes {EASY_HR[1]}."
    reason = "Easy aerobic run: builds your base without adding fatigue."
    if strides:
        note += (" Then 6 x 20 s strides: quick but relaxed (not a sprint), easy jog 60 s between. "
                 "HR will jump briefly - that is fine.")
        reason = "Easy run with strides: keeps your legs quick without adding real fatigue."
    return Workout(day, "easy", [
        make_step("warm-up", 1.0, WARMUP_HR, eff, WARMUP_NOTE),
        make_step("easy", km - 1.5, EASY_HR, eff, note),
        make_step("cool-down", 0.5, WARMUP_HR, eff, COOLDOWN_NOTE),
    ], reason)


def interval_run(day, km, eff):
    """Warm-up, 4-6 x 800 m hard with 400 m jog between, cool-down."""
    reps = 4 if km <= 5.5 else 5 if km <= 7 else 6
    steps = [make_step("warm-up", 1.5, WARMUP_HR, eff, WARMUP_NOTE + " Finish with 4 x 20 s relaxed strides.")]
    for i in range(reps):
        steps.append(make_step("interval", REP_KM, INTERVAL_HR, eff,
                               f"Rep {i + 1} of {reps}: hard but controlled - the same pace every rep. "
                               "HR rises slowly on short repeats, so judge by pace and breathing."))
        if i < reps - 1:
            steps.append(make_step("recovery", JOG_KM, WARMUP_HR, eff, "Slow jog or walk until breathing settles."))
    steps.append(make_step("cool-down", 1.0, WARMUP_HR, eff, COOLDOWN_NOTE))
    return Workout(day, "interval", steps,
                   f"Interval week (alternates with tempo): {reps} x 800 m trains your top-end aerobic "
                   "capacity (VO2max). One hard session a week keeps most running easy.")


def long_run(day, km, eff):
    return Workout(day, "long", [
        make_step("warm-up", 1.0, WARMUP_HR, eff, WARMUP_NOTE),
        make_step("easy", km - 2.0, EASY_HR, eff,
                  f"Steady and relaxed. Walk 1 min whenever HR passes {EASY_HR[1]}; "
                  "walking breaks are fine on a long run."),
        make_step("cool-down", 1.0, WARMUP_HR, eff, COOLDOWN_NOTE),
    ], "Long run: builds the endurance you need for the half. Kept easy so you can recover.")


def tempo_run(day, km, eff):
    block = max(1.0, round_half(km - 2.5))
    return Workout(day, "tempo", [
        make_step("warm-up", 1.5, WARMUP_HR, eff, WARMUP_NOTE + " Finish with 4 x 20 s relaxed strides."),
        make_step("tempo", block, TEMPO_HR, eff,
                  "Comfortably hard: you can say short phrases, not full sentences. Hold it steady; "
                  "ease off if HR goes above the range."),
        make_step("cool-down", 1.0, WARMUP_HR, eff, COOLDOWN_NOTE),
    ], "Tempo because your aerobic base improved but there has been no sustained race-pace "
       "work; teaches you to hold a strong, steady effort.")


def add_fuel_note(workout):
    """Runs over FUEL_AFTER_MIN minutes get a drinking and fuelling note (Racinais 2015)."""
    if workout.minutes > FUEL_AFTER_MIN:
        workout.reason += (f" Expected ~{workout.minutes:.0f} min: carry water with electrolytes and "
                           "take 30-60 g carbohydrate per hour. Sip, don't over-drink.")


def post_race_rest_until(ctx):
    """Last date of the no-running window after the most recent race, or None."""
    if ctx["last_race"] is None:
        return None
    return ctx["last_race"].date() + timedelta(days=safety_rules.POST_RACE_REST_DAYS)


def rest_day(day, runs_by_date, rest_until=None, first_day=None):
    """A non-running day, with a note that depends on what came the day before."""
    yesterday = runs_by_date.get(day - timedelta(days=1))
    days_after_race = (day - (rest_until - timedelta(days=safety_rules.POST_RACE_REST_DAYS))).days \
        if rest_until else None
    if first_day is not None and day < first_day:
        note = "Before your plan starts."
    elif rest_until and 0 < days_after_race <= safety_rules.POST_RACE_REST_DAYS:
        note = (f"Post-race rest (day {days_after_race} after your race). With rest, muscle damage "
                f"clears in about 72 h; running in this window slowed recovery. Walking is fine.")
    elif yesterday and yesterday.kind in ("long", "tempo"):
        note = f"Rest after yesterday's {yesterday.kind} run. Optional: 20-30 min easy walk or gentle stretching."
    else:
        note = "Rest day. Optional: easy walk, stretching or 15-20 min of strength exercises (squats, lunges, calf raises)."
    return Workout(day, "rest", [], note)


def build_plan(runs, plan_start, long_from=None, long_grow=True, runs_from=None, runs_grow=True,
               efficiency=None, first_day=None, quality="tempo"):
    """Create one week's plan and its safety checks. Frequency first:

    runs_from: last week's number of runs. One run is added (up to RUNS_PER_WEEK)
      if runs_grow is True, it is not a recovery week, and the extra MIN_RUN_KM
      keeps the week within 30% of the last 7 days (Nielsen 2014).
    long_from: last week's long run (km). The long run never goes down; it grows
      by LONG_RUN_STEP_KM a week if long_grow is True (last week's long run was done).
    efficiency: overrides the efficiency that paces are calculated from
      (used to project fitness gains into future weeks).
    quality: the hard session in a build week, "tempo" or "interval".
    """
    plan_start = pd.Timestamp(plan_start).normalize()
    ctx = context(runs, plan_start)
    if efficiency is not None:
        ctx["efficiency"] = efficiency
    week_type, why, why_sources = choose_week(ctx)
    last_7_km = safety_rules.km_between(runs, plan_start - pd.Timedelta(days=7), plan_start)

    # 1. Number of runs.
    if runs_from is None:
        n_runs, add_run = START_RUNS_PER_WEEK, False
    else:
        n_runs = runs_from
        add_run = runs_grow and not INJURED_LAST_12_MONTHS
    max_runs = min(RUNS_PER_WEEK, 1 + len(OTHER_RUN_DAYS))
    n_runs = min(max_runs, n_runs)

    # Every week stays under +30% of the last 7 days (Nielsen 2014).
    cap_km = last_7_km * (1 + safety_rules.MAX_2WEEK_INCREASE) if last_7_km > 0 else float("inf")

    # 2. Add a run first (frequency first), if it fits under the cap.
    long_km = round_half(max(MIN_RUN_KM, ctx["longest_recent_km"])) if long_from is None else long_from
    if add_run and n_runs < max_runs:
        with_extra = long_km + n_runs * MIN_RUN_KM
        if with_extra > cap_km:
            note = f"no extra run: {with_extra:g} km would be more than 30% above the last 7 days ({last_7_km:.1f} km)"
        else:
            n_runs += 1
            note = "one more than last week"
    elif n_runs >= max_runs:
        note = "your target"
    elif runs_from is None:
        note = "starting point"
    elif not runs_grow:
        note = "same as last week, because last week's runs were not all done"
    else:
        note = "same as last week"

    # 3. Long run +1 km (never down) if last week's was done and it still fits under the cap.
    if long_from is not None and long_grow and week_type != "recovery":
        longer = min(LONG_RUN_MAX_KM, long_km + LONG_RUN_STEP_KM)
        if longer + (n_runs - 1) * MIN_RUN_KM <= cap_km:
            long_km = longer

    # 4. Once the target number of runs is reached, the easy runs share
    #    WEEKLY_GROWTH more distance than last week (still under the cap).
    other_km = MIN_RUN_KM
    if n_runs >= max_runs and week_type != "recovery" and last_7_km > 0:
        target = min(cap_km, last_7_km * (1 + WEEKLY_GROWTH))
        other_km = max(MIN_RUN_KM, round_half((target - long_km) / (n_runs - 1)))
        while long_km + (n_runs - 1) * other_km > target + 0.25 and other_km > MIN_RUN_KM:
            other_km -= 0.5
    target_km = long_km + (n_runs - 1) * other_km

    why += (f" {n_runs} runs ({note}), building to {max_runs} a week. Long run {long_km:g} km - it grows "
            f"1 km a week when last week's was done, and the week always stays under +30% of the last 7 days.")

    eff = ctx["efficiency"]
    rest_until = post_race_rest_until(ctx)
    # No runs in the first days after a race (Zhou 2026, Wang 2025).
    days = run_days(n_runs, plan_start, rest_until, first_day)
    # In a build week, the first non-long run is the hard session (tempo or intervals).
    quality = quality if week_type == "build" else None
    quality_day = next((d for d in days if d.weekday() != LONG_RUN_DAY), None) if quality else None
    # One easy run a week gets strides: not the day before the long run, not the
    # day after the hard session, and not in the first week after a race.
    race_day = ctx["last_race"].date() if ctx["last_race"] is not None else None
    strides_day = next((d for d in days
                        if d != quality_day and d.weekday() != LONG_RUN_DAY
                        and (d + timedelta(days=1)).weekday() != LONG_RUN_DAY
                        and (quality_day is None or d != quality_day + timedelta(days=1))
                        and (race_day is None or (d - race_day).days >= STRIDES_AFTER_RACE_DAYS)), None)

    workouts = []
    for day in days:
        if day.weekday() == LONG_RUN_DAY:
            workouts.append(long_run(day, long_km, eff))
        elif day == quality_day:
            workouts.append(tempo_run(day, other_km, eff) if quality == "tempo" else interval_run(day, other_km, eff))
        else:
            workouts.append(easy_run(day, other_km, eff, strides=day == strides_day))
    for workout in workouts:
        add_fuel_note(workout)

    runs_by_date = {w.day: w for w in workouts}
    week = [runs_by_date.get(d) or rest_day(d, runs_by_date, rest_until, first_day) for d in week_dates(plan_start)]

    planned_km = sum(w.distance_km for w in workouts)
    planned_long_km = next((w.distance_km for w in workouts if w.kind == "long"), 0.0)
    checks = [
        safety_rules.check_post_race_rest(workouts, ctx["last_race"]),
        safety_rules.check_two_week_increase(planned_km, runs, plan_start),
        safety_rules.check_weekly_increase(planned_km, ctx["baseline_km"]),
        safety_rules.check_rising_weeks(planned_km, runs, plan_start),
        safety_rules.check_long_run(planned_long_km, ctx["longest_recent_km"]),
        safety_rules.check_no_hard_after_race(workouts, ctx["days_since_race"]),
        safety_rules.check_load_spikes(runs, plan_start, planned_km),
    ]

    return {
        "week_type": week_type,
        "why": why,
        "why_sources": describe(why_sources),
        "context": ctx,
        "target_km": target_km,
        "long_km": long_km,
        "n_runs": n_runs,
        "quality": quality,
        "workouts": workouts,
        "days": week,
        "checks": checks,
        "hr_settings": hr_settings(runs),
        "easy_pace_s": pace_at_hr(ctx["efficiency"], EASY_HR_MAX),
        "tempo_pace_s": pace_at_hr(ctx["efficiency"], TEMPO_HR[0]),
    }


def hr_settings(runs):
    """Evidence for the two numbers every HR target depends on."""
    near_max = runs[runs["max_hr"] >= MAX_HR - 5]
    max_note = (
        f"{len(near_max)} runs on different days reached {near_max['max_hr'].min():.0f}-"
        f"{near_max['max_hr'].max():.0f} bpm, so {MAX_HR} is unlikely to be a single wrist-sensor spike. "
        f"A measured max beats the 208 - 0.7 x age formula, which is off by ~10 bpm for many people."
        if len(near_max) > 1 else
        f"Only one run reached within 5 bpm of {MAX_HR}; it could be a wrist-sensor spike."
    )
    easy_note = (
        f"{EASY_HR_FRACTION:.0%} of max HR. In 1,272 lab-tested adults, the top of easy effort was at "
        f"~75% (men) / ~78% (women) of max HR in the least-trained group and higher in fitter people, "
        f"+/-5-7% between individuals. So {EASY_HR_MAX} may be on the high side; set EASY_HR_FRACTION "
        f"to 0.77 ({round(0.77 * MAX_HR)} bpm) in config.py to be more cautious."
    )
    return [
        {"setting": f"Max HR {MAX_HR} bpm", "evidence": max_note,
         "sources": describe(["tanaka2001", "sartor2018"])},
        {"setting": f"Easy limit {EASY_HR_MAX} bpm", "evidence": easy_note,
         "sources": describe(["benitez2025"])},
    ]


def next_monday(today=None):
    today = today or date.today()
    return today + timedelta(days=7 - today.weekday())


def print_plan(plan):
    ctx = plan["context"]
    total = sum(w.distance_km for w in plan["workouts"])
    print(f"PLAN FOR THE WEEK OF {ctx['plan_start']:%a %d %b %Y}  -  {plan['week_type'].upper()} WEEK\n")
    print(f"Why: {plan['why']}")
    print(f"     source: {plan['why_sources']}")
    if plan.get("pace_note"):
        print(f"     {plan['pace_note']}")
    print()

    for w in plan["days"]:
        if w.kind == "rest":
            print(f"  {w.day:%a %d %b}  REST       {w.reason}\n")
            continue
        print(f"  {w.day:%a %d %b}  {w.kind.upper():<6} RUN  {w.distance_km:.1f} km  ~{w.minutes:.0f} min")
        print(f"      {w.reason}")
        for s in w.steps:
            pace = f"{format_pace(s.pace_fast_s)}-{format_pace(s.pace_slow_s)}/km"
            print(f"      {s.name:<10} {s.distance_km:>4.1f} km  HR {s.hr_min}-{s.hr_max}  "
                  f"pace {pace:<13} ~{s.minutes:.0f} min")
            print(f"                 {s.note}")
        print()
    print(f"  Total {total:.1f} km over {len(plan['workouts'])} runs. "
          f"Paces are estimates in your usual heat - follow heart rate, not pace.")

    print("\nSAFETY CHECKS")
    for c in plan["checks"]:
        print(f"  [{c['level'].upper():<7}] {c['rule']}: {c['detail']}")
        print(f"            {c['formula']}")
        print(f"            source: {c['sources']}")

    print("\nHEART-RATE SETTINGS")
    for s in plan["hr_settings"]:
        print(f"  {s['setting']}: {s['evidence']}")
        print(f"            source: {s['sources']}")

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
