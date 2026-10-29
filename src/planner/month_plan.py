"""Month plan: a rolling, week-by-week plan starting on PLAN_START.

How it works:
  1. The plan is cut into Monday-Sunday weeks, from the week of PLAN_START.
  2. Each week is planned with build_plan() from everything known before it
     starts: real runs from your Garmin export, plus - for days the export does
     not cover yet - the runs planned for earlier weeks, assumed done as planned.
  3. So future weeks are provisional. When you export new data at the end of a
     week, that week is evaluated (planned vs actual) and every later week is
     re-planned from the real numbers.
  4. Frequency first: one 5 km run is added each week (if at most one run was
     missed last week) until you reach RUNS_PER_WEEK.
  5. The long run never goes down: it grows by LONG_RUN_STEP_KM each week if
     last week's long run was done.
  6. Paces: this week's come from your latest real runs. Future weeks assume your
     aerobic fitness keeps improving at your own recent rate (straight-line trend
     of efficiency), capped at MAX_WEEKLY_GAIN. Real data replaces them each week.
  7. Every STEP_BACK_EVERY-th week is a step-back week (~25% less). The week after
     it returns to the level before it.
  8. With a GOAL_RACE date: the 2 weeks before it are a taper (Bosquet 2007).
     The weekly distance builds to a peak and holds: the target's, or without a
     target the one that matches today's race estimate.
  9. Finished weeks are frozen (with plans_dir): while a week is running, its
     plan is saved every time it is built, so a new target still changes it.
     Once the week is over, that last saved version is used from then on -
     it is the plan you actually saw, and the week is evaluated against it,
     even if the goal or the planner's rules change later.
"""

import math
import pickle

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.analysis.easy_check import easy_seconds, label_runs
from src.analysis.fitness_trend import training_runs_with_efficiency, trend_line
from src.config import GOAL_RACE, PLAN_START, PLAN_WEEKS_AHEAD, STEP_BACK_EVERY
from src.analysis.goal_planner import goal_gap, parse_time, peak_km
from src.planner.plan_generator import LOOKBACK_WEEKS, build_plan

LONG_RUN_DONE_SHARE = 0.9   # a long run counts as done at 90% of the planned distance
MAX_WEEKLY_GAIN = 0.01      # never project more than 1% fitness gain per week
MIN_RUNS_FOR_TREND = 10


def weekly_fitness_gain(real):
    """Your recent efficiency improvement per week, from the straight-line trend.

    0 if there are too few runs or fitness is not improving (no decline is projected).
    """
    training = training_runs_with_efficiency(real).dropna(subset=["efficiency"])
    if len(training) < MIN_RUNS_FOR_TREND:
        return 0.0
    trend = trend_line(training)
    per_week = (trend["end_efficiency"] - trend["start_efficiency"]) / trend["days"] * 7 / trend["end_efficiency"]
    return min(MAX_WEEKLY_GAIN, max(0.0, per_week))


def latest_efficiency(real, data_end):
    """Median efficiency of real training runs in the LOOKBACK_WEEKS before data_end."""
    recent = real[real["start_time"] >= data_end - pd.Timedelta(weeks=LOOKBACK_WEEKS)]
    return training_runs_with_efficiency(recent)["efficiency"].median()


def covered_until(exported_at):
    """Last full day an export or sync made at `exported_at` covers.

    Runs later that same day may be missing, so only the days before it count.
    """
    return pd.Timestamp(exported_at).date() - timedelta(days=1)


def covered_until_from_file(csv_path):
    """The same for a CSV: the file's modification time is when you exported it."""
    return covered_until(pd.Timestamp(Path(csv_path).stat().st_mtime, unit="s"))


def simulated_runs(workouts):
    """Planned workouts as run rows, assuming each is done exactly as planned."""
    rows = []
    for w in workouts:
        seconds = w.minutes * 60
        avg_hr = sum(s.minutes * (s.hr_min + s.hr_max) / 2 for s in w.steps) / w.minutes
        rows.append({
            "start_time": pd.Timestamp(w.day) + pd.Timedelta(hours=18),
            "activity_type": "Running",
            "title": f"planned {w.kind}",
            "distance_km": w.distance_km,
            "duration_s": seconds,
            "moving_time_s": seconds,
            "avg_hr": avg_hr,
        })
    return pd.DataFrame(rows)


def evaluate_week(plan, actual):
    """Planned vs actual for a week the export fully covers."""
    planned_long = next((w.distance_km for w in plan["workouts"] if w.kind == "long"), 0.0)
    longest = actual["distance_km"].max() if len(actual) else 0.0
    labelled = label_runs(actual)
    total_s = labelled["moving_time_s"].sum()
    return {
        "planned_km": sum(w.distance_km for w in plan["workouts"]),
        "actual_km": actual["distance_km"].sum(),
        "planned_runs": len(plan["workouts"]),
        "actual_runs": len(actual),
        "planned_long_km": planned_long,
        "longest_km": longest,
        "long_done": planned_long == 0 or longest >= LONG_RUN_DONE_SHARE * planned_long,
        "easy_pct": 100 * easy_seconds(labelled).sum() / total_s if total_s else None,
    }


def describe_evaluation(ev):
    """One line summarising a finished week."""
    parts = [f"{ev['actual_km']:.1f} of {ev['planned_km']:.1f} km"]
    if ev["actual_runs"] >= ev["planned_runs"] - 1:
        parts.append(f"{ev['actual_runs']} of {ev['planned_runs']} runs")
    else:
        parts.append(f"{ev['actual_runs']} of {ev['planned_runs']} runs - no extra run next week")
    if ev["long_done"]:
        parts.append("long run done")
    else:
        parts.append(f"long run missed ({ev['longest_km']:.1f} of {ev['planned_long_km']:.1f} km) "
                     "- it will not grow next week")
    if ev["easy_pct"] is not None:
        parts.append(f"{ev['easy_pct']:.0f}% easy")
    return ", ".join(parts)


def week_phase(number, start, race_date, step_back_every=STEP_BACK_EVERY):
    """'race week', 'taper', 'step back' or None for the week starting on `start`."""
    if race_date is not None:
        days_to_race = (race_date - start).days
        if 0 <= days_to_race < 7:
            return "race week"
        if 7 <= days_to_race < 14:
            return "taper"
    if step_back_every and number % step_back_every == 0:
        return "step back"
    return None


def frozen_path(plans_dir, start):
    return Path(plans_dir) / f"week-{start:%Y-%m-%d}.pkl"


def load_frozen(plans_dir, start, first_day):
    """The saved plan for the week starting on `start`, or None.

    None too if it belongs to another plan (PLAN_START changed) or was saved by
    code too different to read back.
    """
    path = frozen_path(plans_dir, start)
    if not path.exists():
        return None
    try:
        saved = pickle.loads(path.read_bytes())
    except Exception:
        return None
    return saved["plan"] if saved["first_day"] == first_day else None


def save_frozen(plans_dir, start, first_day, plan):
    path = frozen_path(plans_dir, start)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps({"first_day": first_day, "plan": {**plan, "saved_at": pd.Timestamp.now()}}))


def week_status(start, end, today, data_end):
    if end <= data_end:
        return "done"
    if start <= today < end:
        return "current"
    if end <= today:
        return "needs data"   # finished, but the export does not cover it yet
    return "upcoming"


def build_month_plan(runs, covered_until, plan_start=PLAN_START, today=None, weeks_ahead=PLAN_WEEKS_AHEAD,
                     goal_race=GOAL_RACE, step_back_every=STEP_BACK_EVERY, plans_dir=None):
    """All weeks from plan_start to weeks_ahead weeks past the current one.

    plans_dir: folder for frozen weeks (see point 9 above); None plans every week afresh.
    """
    first_day = pd.Timestamp(plan_start).normalize()                 # the first run
    plan_start = first_day - pd.Timedelta(days=first_day.weekday())  # weeks run Monday-Sunday
    today = pd.Timestamp(today or date.today()).normalize()
    data_end = pd.Timestamp(covered_until).normalize() + pd.Timedelta(days=1)  # first day not covered
    real = runs[runs["start_time"] < data_end]

    current = max(0, (today - plan_start).days // 7)
    gain = weekly_fitness_gain(real)
    base_eff = latest_efficiency(real, data_end)
    weeks, assumed = [], []
    long_from, long_grow = None, True
    runs_from, runs_grow = None, True
    last_quality = None   # build weeks alternate tempo and intervals, starting with tempo
    sessions = {"tempo": 0, "interval": 0}   # the step each hard session is at next: it grows each time
    race_date = pd.Timestamp(goal_race["date"]) if goal_race and goal_race.get("date") else None
    # Today's race estimate, so goal pace is judged against race fitness, not short runs.
    # The peak weekly distance: from the target, or without one from today's estimate
    # (the load that matches your current level), so the plan never grows without end.
    if goal_race and goal_race.get("target_time"):
        gap = goal_gap(real, goal_race, gain, today)
        goal_race = {**goal_race, "estimate_s": gap["estimate_now_s"] if gap else None,
                     "peak_km": peak_km(goal_race["distance_km"], parse_time(goal_race["target_time"]))}
    elif goal_race:
        gap = goal_gap(real, goal_race, gain, today)
        if gap:
            goal_race = {**goal_race, "peak_km": peak_km(goal_race["distance_km"], gap["estimate_now_s"])}
    steady_km = steady_runs = None   # the last normal week (not step-back or taper)
    prev_phase = None
    for k in range(current + weeks_ahead):
        start = plan_start + pd.Timedelta(weeks=k)
        end = start + pd.Timedelta(days=7)
        phase = week_phase(k + 1, start, race_date, step_back_every)
        # A taper, and the week after a step-back, measure from the last normal week.
        reference = steady_km if phase in ("taper", "race week") or prev_phase == "step back" else None
        if prev_phase == "step back" and steady_runs:
            runs_from = max(runs_from, steady_runs)
        known = pd.concat([real, *assumed], ignore_index=True) if assumed else real
        known = known[known["start_time"] < start].sort_values("start_time").reset_index(drop=True)

        status = week_status(start, end, today, data_end)
        # Weeks the data has not reached yet: latest fitness, plus the projected gain.
        weeks_past_data = max(0, math.ceil((start - data_end).days / 7))
        efficiency = None if status == "done" else base_eff * (1 + gain) ** weeks_past_data

        ended = end <= today
        quality = "interval" if last_quality == "tempo" else "tempo"
        # Lighter weeks repeat an easier version of the session instead of growing it.
        step = sessions[quality] if phase is None else max(0, sessions[quality] - 1)
        plan = load_frozen(plans_dir, start, first_day) if plans_dir and ended else None
        if plan is not None:
            plan["frozen"] = True
        else:
            plan = build_plan(known, start, long_from=long_from, long_grow=long_grow,
                              runs_from=runs_from, runs_grow=runs_grow, efficiency=efficiency,
                              first_day=first_day.date() if k == 0 else None,
                              quality=quality, phase=phase, reference_km=reference, race=goal_race,
                              quality_step=step)
            plan["pace_note"] = (
                "Paces from your real runs before this week." if efficiency is None else
                f"Paces from your latest runs (up to {data_end - pd.Timedelta(days=1):%d %b})"
                + (f", projected {weeks_past_data} week{'s' if weeks_past_data != 1 else ''} ahead at your "
                   f"recent fitness gain of {100 * gain:.1f}%/week. Real data replaces this each week."
                   if weeks_past_data else ".")
            )
            # The running week is saved every time; a finished week only once, then kept.
            if plans_dir and (ended or status == "current"):
                save_frozen(plans_dir, start, first_day, plan)
        last_quality = plan["quality"] or last_quality
        # The next session is one step up from the one this normal week actually had (a
        # goal-pace long run in the tempo slot counts too); lighter weeks leave it as it is.
        if phase is None and plan.get("quality_step") is not None:
            sessions[plan["quality"]] = plan["quality_step"] + 1
        actual_phase = phase if plan["week_type"] in ("step back", "taper", "race week") else None
        if actual_phase is None:
            steady_km, steady_runs = sum(w.distance_km for w in plan["workouts"]), plan["n_runs"]
        prev_phase = actual_phase

        evaluation = None
        if status == "done":
            actual = real[(real["start_time"] >= start) & (real["start_time"] < end)]
            evaluation = evaluate_week(plan, actual)

        not_covered = [w for w in plan["workouts"] if pd.Timestamp(w.day) >= data_end]
        if not_covered:
            assumed.append(simulated_runs(not_covered))

        long_from = max(long_from or 0.0, plan["long_km"])
        long_grow = evaluation["long_done"] if evaluation else True
        # Add a run next week only if at most one planned run was missed this week.
        runs_from = plan["n_runs"]
        runs_grow = evaluation["actual_runs"] >= evaluation["planned_runs"] - 1 if evaluation else True

        weeks.append({"number": k + 1, "start": start, "end": end - pd.Timedelta(days=1),
                      "status": status, "plan": plan, "evaluation": evaluation})
    return weeks


def current_week(weeks):
    """This week; before the plan starts its first week, after it ends its last."""
    return next((w for w in weeks if w["status"] == "current"),
                next((w for w in weeks if w["status"] == "upcoming"), weeks[-1]))


def print_month(weeks, covered_until):
    print(f"TRAINING PLAN from {weeks[0]['start']:%a %d %b %Y}  (data covers runs up to {covered_until:%d %b})\n")
    print(f"  {'week':<5} {'dates':<16} {'type':<9} {'km':>5} {'long':>5}  status")
    for w in weeks:
        p = w["plan"]
        km = sum(x.distance_km for x in p["workouts"])
        long_km = next((x.distance_km for x in p["workouts"] if x.kind == "long"), 0.0)
        print(f"  {w['number']:<5} {w['start']:%d %b}-{w['end']:%d %b}  {p['week_type']:<9} {km:>5.1f} "
              f"{long_km:>5.1f}  {w['status']}")
        if w["evaluation"]:
            print(f"        {describe_evaluation(w['evaluation'])}")
    print("\nUpcoming weeks are provisional: export a new Garmin CSV at the end of each week to "
          "evaluate it and re-plan the rest.\n")


if __name__ == "__main__":
    # python -m src.planner.month_plan "data/Running Data may-oct.csv"
    import sys

    from src.analysis.heat_adjust import load_runs_with_heat
    from src.planner.plan_generator import print_plan

    from src.goal_settings import load_goal

    covered = covered_until_from_file(sys.argv[1])
    month = build_month_plan(load_runs_with_heat(sys.argv[1]), covered, goal_race=load_goal(),
                             plans_dir=Path(sys.argv[1]).parent / "plans")
    print_month(month, covered)
    print_plan(current_week(month)["plan"])
