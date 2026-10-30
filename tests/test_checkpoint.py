"""Check-ins during a milestone stage (src/analysis/checkpoint.py)."""

import datetime as dt

import pandas as pd
from conftest import make_runs

from src.analysis import checkpoint
from src.planner.plan_generator import easy_run, long_run, tempo_run

EFF = 0.9


def week(number, monday, hard=True, status="done", long_done=True):
    monday = pd.Timestamp(monday)
    day = lambda i: (monday + pd.Timedelta(days=i)).date()
    first = tempo_run(day(1), 5.0, EFF) if hard else easy_run(day(1), 5.0, EFF)
    workouts = [first, easy_run(day(3), 5.0, EFF), long_run(day(5), 7.0, EFF)]
    evaluation = {"planned_runs": 3, "actual_runs": 3, "planned_long_km": 7.0, "long_done": long_done,
                  "easy_pct": 80.0}
    return {"number": number, "start": monday, "end": monday + pd.Timedelta(days=6), "status": status,
            "plan": {"workouts": workouts}, "evaluation": evaluation if status == "done" else None}


def test_weeks_done_as_planned_are_on_track():
    runs = make_runs(end="2026-10-25")   # Tue 5 km, Thu 5 km, Sat 7 km: what the weeks ask for
    c = checkpoint.evaluate([week(3, "2026-10-12"), week(4, "2026-10-19")], runs)
    assert c["on_track"] and (c["hard_done"], c["hard_planned"]) == (2, 2)
    assert abs(c["efficiency_change"]) < 0.01


def test_a_missed_session_or_long_run_is_behind():
    runs = make_runs(end="2026-10-25")
    missed = runs[runs["start_time"].dt.date != dt.date(2026, 10, 20)]   # the second week's tempo
    c = checkpoint.evaluate([week(3, "2026-10-12"), week(4, "2026-10-19")], missed)
    assert not c["on_track"] and not c["checks"]["hard"]
    c = checkpoint.evaluate([week(3, "2026-10-12"), week(4, "2026-10-19", long_done=False)], runs)
    assert not c["on_track"] and not c["checks"]["long"]


def test_less_than_three_quarters_easy_is_behind():
    runs = make_runs(end="2026-10-25")
    weeks = [week(3, "2026-10-12"), week(4, "2026-10-19")]
    weeks[1]["evaluation"]["easy_pct"] = 50.0                # Muñoz 2014: ~75% below the first threshold
    assert not checkpoint.evaluate(weeks, runs)["checks"]["easy"]


def test_slower_for_the_same_heart_rate_is_behind():
    runs = pd.concat([make_runs(end="2026-10-11"), make_runs("2026-10-12", "2026-10-25", pace_s=520)])
    c = checkpoint.evaluate([week(3, "2026-10-12"), week(4, "2026-10-19")], runs)
    assert not c["checks"]["fitness"] and c["easy_pace_now_s"] > c["easy_pace_before_s"]


def test_check_ins_skip_recovery_blocks_and_unfinished_weeks():
    runs = make_runs(end="2026-10-25")
    weeks = [week(1, "2026-09-28", hard=False), week(2, "2026-10-05", hard=False),
             week(3, "2026-10-12"), week(4, "2026-10-19"), week(5, "2026-10-26", status="current"),
             week(6, "2026-11-02", status="upcoming")]
    assert checkpoint.latest(weeks[:2], runs, test_week=6) is None          # recovery only
    assert checkpoint.latest(weeks, runs, test_week=6)["end"] == dt.date(2026, 10, 25)   # week 4: 5 is running
    assert checkpoint.latest(weeks, runs, test_week=4)["end"] == dt.date(2026, 10, 18)   # week 3: 4 is the test
    assert checkpoint.latest(weeks, runs, test_week=3) is None               # before it only recovery


def test_a_week_with_only_a_race_has_no_fitness_verdict():
    runs = make_runs(end="2026-10-18")
    race = pd.DataFrame([{"start_time": pd.Timestamp("2026-10-24 05:00"), "activity_type": "Running",
                          "title": "HM", "distance_km": 21.1, "duration_s": 11000, "moving_time_s": 11000,
                          "avg_hr": 170, "max_hr": 190, "garmin_race": True}])
    c = checkpoint.evaluate([week(4, "2026-10-19")], pd.concat([runs, race], ignore_index=True))
    assert c["efficiency_change"] is None and c["checks"]["fitness"]
