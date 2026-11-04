"""Runs logged by hand (src/loaders/manual_runs.py) for runners without Garmin."""

from datetime import date

import pandas as pd

from src import users
from src.athlete import ATHLETE, Athlete, use
from src.loaders import manual_runs
from src.loaders.manual_stats import covered_until, history_end, runs_from_stats
from src.planner.month_plan import build_month_plan

STATS = {"sex": "female", "age": 30, "max_hr": None, "runs_per_week": 3, "weekly_km": 18.0, "longest_km": 8.0,
         "easy_pace_s": 450, "easy_hr": 148, "race": None, "injured": False, "as_of": "2026-11-04"}
RUN = {"start": "2026-11-10T19:00:00", "distance_km": 5.0, "duration_s": 2400, "avg_hr": 150, "max_hr": 165,
       "race": False, "title": None}


def test_saved_runs_come_back_as_a_runs_table(tmp_path):
    assert manual_runs.load(tmp_path) == []
    saved = manual_runs.add(tmp_path, RUN)
    manual_runs.add(tmp_path, {**RUN, "start": "2026-11-09T06:00:00", "race": True, "max_hr": None})
    entries = manual_runs.load(tmp_path)
    assert [e["start"][:10] for e in entries] == ["2026-11-09", "2026-11-10"]          # kept in time order
    runs = manual_runs.to_runs(entries)
    assert set(runs_from_stats(STATS, 187).columns) <= set(runs.columns)               # same columns as the stats
    assert runs["avg_pace_s_per_km"].tolist() == [480.0, 480.0]
    assert runs["garmin_race"].tolist() == [True, False] and pd.isna(runs["max_hr"].iloc[0])
    manual_runs.remove(tmp_path, saved["id"])
    assert len(manual_runs.load(tmp_path)) == 1


def test_entries_are_checked():
    first, today = history_end(STATS).date(), date(2026, 11, 12)
    assert first == date(2026, 11, 2)
    check = lambda **change: manual_runs.problems({**RUN, **change}, first, today, 187)
    assert check() == []
    assert check(avg_hr=None) == ["missing avg_hr"]
    assert check(start="2026-11-01T19:00:00") == ["before stats"]          # the stats already cover that week
    assert check(start="2026-11-13T19:00:00") == ["in future"]
    assert check(distance_km=0.5) == ["too short", "odd pace"]
    assert check(duration_s=240) == ["odd pace"]                           # 0:48/km: a typo
    assert check(avg_hr=190, max_hr=None) == ["odd avg hr"]
    assert check(max_hr=140) == ["odd max hr"]


def test_logging_moves_the_data_to_yesterday():
    stats_end = covered_until(STATS)
    assert manual_runs.covered(stats_end, [], "2026-11-12") == stats_end              # nothing logged: as before
    assert manual_runs.covered(stats_end, [RUN], "2026-11-12") == date(2026, 11, 11)


def test_a_logged_week_is_evaluated_with_its_runs():
    entries = [{**RUN, "id": "a", "start": "2026-11-03T19:00:00"},
               {**RUN, "id": "b", "start": "2026-11-05T19:00:00"},
               {**RUN, "id": "c", "start": "2026-11-08T06:00:00", "distance_km": 8.0, "duration_s": 3840}]
    try:
        use(users.athlete({"name": "Sari", "source": "stats", "stats": STATS}))
        runs = manual_runs.with_logged(runs_from_stats(STATS, ATHLETE.max_hr), entries)
        covered = manual_runs.covered(covered_until(STATS), entries, "2026-11-10")
        weeks = build_month_plan(runs, covered, plan_start="2026-11-02", today="2026-11-10", weeks_ahead=1,
                                 plans_dir=None)
    finally:
        use(Athlete())
    first = weeks[0]
    assert first["status"] == "done"
    assert first["evaluation"]["actual_runs"] == 3
    assert round(first["evaluation"]["actual_km"], 1) == 18.0
