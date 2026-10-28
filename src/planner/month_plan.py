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
"""

import math

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.analysis.easy_check import label_runs
from src.analysis.fitness_trend import training_runs_with_efficiency, trend_line
from src.config import PLAN_START, PLAN_WEEKS_AHEAD
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


def covered_until_from_file(csv_path):
    """Last full day the export covers.

    The file's modification time is when you exported it. Runs later that same
    day may be missing, so only the days before it count as covered.
    """
    exported = date.fromtimestamp(Path(csv_path).stat().st_mtime)
    return exported - timedelta(days=1)


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
        "easy_pct": 100 * labelled.loc[labelled["is_easy"], "moving_time_s"].sum() / total_s if total_s else None,
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


def week_status(start, end, today, data_end):
    if end <= data_end:
        return "done"
    if start <= today < end:
        return "current"
    if end <= today:
        return "needs data"   # finished, but the export does not cover it yet
    return "upcoming"


def build_month_plan(runs, covered_until, plan_start=PLAN_START, today=None, weeks_ahead=PLAN_WEEKS_AHEAD):
    """All weeks from plan_start to weeks_ahead weeks past the current one."""
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
    for k in range(current + weeks_ahead):
        start = plan_start + pd.Timedelta(weeks=k)
        end = start + pd.Timedelta(days=7)
        known = pd.concat([real, *assumed], ignore_index=True) if assumed else real
        known = known[known["start_time"] < start].sort_values("start_time").reset_index(drop=True)

        status = week_status(start, end, today, data_end)
        # Weeks the data has not reached yet: latest fitness, plus the projected gain.
        weeks_past_data = max(0, math.ceil((start - data_end).days / 7))
        efficiency = None if status == "done" else base_eff * (1 + gain) ** weeks_past_data

        plan = build_plan(known, start, long_from=long_from, long_grow=long_grow,
                          runs_from=runs_from, runs_grow=runs_grow, efficiency=efficiency,
                          first_day=first_day.date() if k == 0 else None,
                          quality="interval" if last_quality == "tempo" else "tempo")
        last_quality = plan["quality"] or last_quality
        plan["pace_note"] = (
            "Paces from your real runs before this week." if efficiency is None else
            f"Paces from your latest runs (up to {data_end - pd.Timedelta(days=1):%d %b})"
            + (f", projected {weeks_past_data} week{'s' if weeks_past_data != 1 else ''} ahead at your "
               f"recent fitness gain of {100 * gain:.1f}%/week. Real data replaces this each week."
               if weeks_past_data else ".")
        )

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
    return next((w for w in weeks if w["status"] == "current"), weeks[-1])


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

    covered = covered_until_from_file(sys.argv[1])
    month = build_month_plan(load_runs_with_heat(sys.argv[1]), covered)
    print_month(month, covered)
    print_plan(current_week(month)["plan"])
