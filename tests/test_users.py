"""Runners (src/users.py), their settings (src/athlete.py) and the history their stats describe."""

import pandas as pd

from src import users
from src.athlete import ATHLETE, Athlete, use
from src.loaders.manual_stats import covered_until, runs_from_stats
from src.planner import plan_generator
from src.planner.month_plan import build_month_plan

STATS = {"sex": "female", "age": 30, "max_hr": None, "runs_per_week": 3, "weekly_km": 18.0, "longest_km": 8.0,
         "easy_pace_s": 450, "easy_hr": 148, "race": {"distance_km": 5.0, "time_s": 1800, "date": "2026-10-11"},
         "injured": False}


def test_tee_is_always_there_and_new_runners_get_their_own_folder(tmp_path):
    store = users.load(tmp_path)
    assert [u["id"] for u in store["users"]] == ["tee"]
    assert users.data_dir(tmp_path, store["users"][0]) == tmp_path
    sari = users.new_user(store, "Sari Dewi", STATS, today=pd.Timestamp("2026-11-04").date())
    users.add(tmp_path, store, sari)
    assert sari["id"] == "sari-dewi" and users.data_dir(tmp_path, sari).is_dir()
    assert users.new_user(store, "Sari Dewi", STATS)["id"] == "sari-dewi-2"
    assert users.find(users.load(tmp_path), "sari-dewi")["stats"]["as_of"] == "2026-11-04"


def test_settings_come_from_the_stats():
    runner = users.athlete({"name": "Sari", "source": "stats", "stats": {**STATS, "as_of": "2026-11-04"}})
    assert (runner.max_hr, runner.max_hr_source) == (187, "age")            # 208 - 0.7 x 30
    assert runner.easy_hr_max == round(0.82 * 187)                          # women's easy limit
    assert users.athlete({"name": "tee", "source": "data"}) == Athlete(name="tee")


def test_switching_runner_moves_the_heart_rate_zones():
    try:
        use(Athlete(name="x", max_hr=200))
        assert plan_generator.TEMPO_HR == (170, 180) and ATHLETE.easy_hr_max == 156
    finally:
        use(Athlete())
    assert plan_generator.TEMPO_HR == (round(0.85 * ATHLETE.max_hr), round(0.90 * ATHLETE.max_hr))


def test_stats_become_four_weeks_of_runs_and_the_race():
    stats = {**STATS, "as_of": "2026-11-04"}                                # a Wednesday
    runs = runs_from_stats(stats, 187)
    assert covered_until(stats) == pd.Timestamp("2026-11-01").date()
    training = runs[~runs["garmin_race"]]
    weekly = training.groupby(training["start_time"].dt.to_period("W-SUN"))["distance_km"].sum()
    assert weekly.iloc[-4:].round(1).tolist() == [18.0] * 4                 # the last 4 weeks as entered
    assert training["distance_km"].max() == 8.0
    assert runs["start_time"].min() >= pd.Timestamp("2026-09-07")           # 4 weeks before the race week
    assert runs[runs["garmin_race"]]["duration_s"].tolist() == [1800]


def test_a_new_runner_gets_a_plan():
    stats = {**STATS, "as_of": "2026-11-04"}
    try:
        use(users.athlete({"name": "Sari", "source": "stats", "stats": stats}))
        weeks = build_month_plan(runs_from_stats(stats, ATHLETE.max_hr), covered_until(stats),
                                 plan_start="2026-11-04", today="2026-11-04", weeks_ahead=4,
                                 goal_race={"name": "x", "distance_km": 10.0, "target_time": None, "date": None})
        assert weeks[0]["plan"]["n_runs"] == 3 and weeks[0]["plan"]["long_km"] == 8.0
    finally:
        use(Athlete())


def test_a_talk_test_replaces_the_share_of_max_hr(tmp_path):
    store = users.load(tmp_path)
    users.set_talk_test(tmp_path, store, "tee", 158, day=pd.Timestamp("2026-11-03").date())
    tee = users.find(users.load(tmp_path), "tee")
    assert tee["talk_test"] == {"hr": 158, "date": "2026-11-03"}
    try:
        use(users.athlete(tee))
        assert ATHLETE.easy_hr_max == 158 and plan_generator.EASY_HR[1] == 158
        notes = {s["setting"]: s["sources"] for s in plan_generator.hr_settings(pd.DataFrame({"max_hr": []}))}
        assert "Persinger" in notes["Easy limit 158 bpm"] and "Coyle" in notes["HR drift"]
    finally:
        use(Athlete())
    users.set_talk_test(tmp_path, store, "tee", None)
    assert users.athlete(users.find(users.load(tmp_path), "tee")).easy_hr_max == round(0.78 * 196)
