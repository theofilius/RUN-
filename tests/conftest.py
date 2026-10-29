"""Shared test data: synthetic runs, so the tests never need your private CSV or internet."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make "src" importable


def make_runs(start="2026-09-01", end="2026-10-25", plan=((1, 5.0), (3, 5.0), (5, 7.0)), hr=150, pace_s=480):
    """Runs on fixed weekdays (0 = Monday) at one HR and pace (default easy, 8:00/km)."""
    rows = []
    for day in pd.date_range(start, end):
        for weekday, km in plan:
            if day.weekday() == weekday:
                seconds = km * pace_s
                rows.append({
                    "start_time": day + pd.Timedelta(hours=19), "activity_type": "Running",
                    "title": "Jakarta - Base", "distance_km": km, "duration_s": seconds,
                    "moving_time_s": seconds, "avg_hr": hr, "max_hr": hr + 20,
                })
    return pd.DataFrame(rows)


@pytest.fixture
def runs():
    return make_runs()


@pytest.fixture
def no_races(monkeypatch):
    """Isolate the planner from the races in config.py."""
    import src.analysis.races as races
    import src.planner.plan_generator as plan_generator

    monkeypatch.setattr(races, "RACES", {})
    monkeypatch.setattr(plan_generator, "GOAL_RACE", {"name": "test", "date": None, "distance_km": 21.1,
                                                      "target_time": "2:50:00"})
