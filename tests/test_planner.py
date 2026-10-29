"""The planner's safety rules, checked over a 12-week plan."""

import pandas as pd
import pytest
from conftest import make_runs

from src.analysis import races
from src.planner import plan_generator, safety_rules
from src.planner.month_plan import build_month_plan
from src.planner.plan_generator import LONG_RUN_DAY, MIN_RUN_KM, build_plan

NO_GOAL = {"name": "test race", "date": None, "distance_km": 21.1, "target_time": None}


def month(runs, goal=NO_GOAL, weeks=12, step_back_every=4):
    return build_month_plan(runs, covered_until="2026-10-25", plan_start="2026-10-26", today="2026-10-26",
                            weeks_ahead=weeks, goal_race=goal, step_back_every=step_back_every)


def week_km(week):
    return sum(w.distance_km for w in week["plan"]["workouts"])


def test_no_week_more_than_30_percent_above_the_last(runs, no_races):
    last_real = runs[runs["start_time"] >= pd.Timestamp("2026-10-19")]["distance_km"].sum()
    previous, normal = last_real, last_real
    for week in month(runs):
        km = week_km(week)
        reference = max(previous, normal) if week["plan"]["week_type"] != "step back" else previous
        assert km <= reference * 1.3 + 0.25, f"week {week['number']}: {km} km after {reference} km"
        if week["plan"]["week_type"] not in ("step back", "taper", "race week"):
            normal = km
        previous = km


def test_long_run_never_goes_down(runs, no_races):
    longs = [week["plan"]["long_km"] for week in month(runs)]
    assert all(later >= earlier for earlier, later in zip(longs, longs[1:])), longs


def test_at_most_one_extra_run_per_week_up_to_the_target(runs, no_races):
    counts = [week["plan"]["n_runs"] for week in month(runs, step_back_every=0)]
    assert all(later - earlier <= 1 for earlier, later in zip(counts, counts[1:])), counts
    assert max(counts) == min(plan_generator.RUNS_PER_WEEK, 1 + len(plan_generator.OTHER_RUN_DAYS))


def test_easy_and_long_runs_are_at_least_the_minimum(runs, no_races):
    for week in month(runs):
        for w in week["plan"]["workouts"]:
            if w.kind in ("easy", "long", "tempo"):
                assert w.distance_km >= MIN_RUN_KM, (w.day, w.kind, w.distance_km)


def test_every_fourth_week_steps_back(runs, no_races):
    weeks = month(runs)
    for week in weeks:
        if week["number"] % 4 == 0:
            assert week["plan"]["week_type"] == "step back"
            assert week_km(week) < week_km(weeks[week["number"] - 2])


def test_one_hard_session_at_most(runs, no_races):
    for week in month(runs):
        assert sum(w.is_hard for w in week["plan"]["workouts"]) <= 1


def race_run(start, km=21.1):
    return pd.DataFrame([{"start_time": pd.Timestamp(start), "activity_type": "Running", "title": "HM",
                          "distance_km": km, "duration_s": km * 540, "moving_time_s": km * 540,
                          "avg_hr": 170, "max_hr": 185}])


@pytest.mark.parametrize("how", ["garmin event type", "config"])
def test_no_runs_in_the_three_days_after_a_race(runs, no_races, monkeypatch, how):
    race = pd.Timestamp("2026-10-24 05:00")
    with_race = pd.concat([runs, race_run(race)], ignore_index=True).sort_values("start_time")
    if how == "config":
        monkeypatch.setattr(races, "RACES", {"race": {"start": str(race), "distance_km": 21.1}})
    else:
        with_race["garmin_race"] = with_race["start_time"] == race
    plan = build_plan(with_race, "2026-10-26", runs_from=5)
    for w in plan["workouts"]:
        assert (w.day - race.date()).days > safety_rules.POST_RACE_REST_DAYS


def test_taper_before_the_goal_race(runs, no_races):
    goal = {**NO_GOAL, "date": "2027-01-24"}  # a Sunday
    weeks = {w["plan"]["week_type"]: w for w in month(runs, goal=goal, weeks=13)}
    assert "taper" in weeks and "race week" in weeks
    race_week = weeks["race week"]["plan"]
    run_days = {w.day for w in race_week["workouts"]}
    assert pd.Timestamp("2027-01-24").date() not in run_days
    assert pd.Timestamp("2027-01-23").date() not in run_days
    assert any(d.kind == "race" for d in race_week["days"])


def test_missed_long_run_does_not_grow(runs, no_races):
    plan = build_plan(runs, "2026-11-09", long_from=8.0, long_grow=False, runs_from=4)
    assert plan["long_km"] == 8.0


def test_long_run_is_on_the_long_run_day(runs, no_races):
    plan = build_plan(runs, "2026-11-09", runs_from=4)
    assert [w.day.weekday() for w in plan["workouts"] if w.kind == "long"] == [LONG_RUN_DAY]


@pytest.mark.parametrize("target, finish", [
    ("2:50:00", True),    # 8:03/km: faster than easy, slower than the top of tempo -> practise it
    ("3:10:00", False),   # 9:00/km: already easy effort -> long runs, no pace block
    ("2:00:00", False),   # 5:41/km: beyond today's tempo -> not yet
])
def test_goal_pace_finish_only_when_reachable(no_races, target, finish):
    runs = make_runs(hr=150, pace_s=528)  # easy runs, efficiency like yours: easy ~8:24, tempo top ~7:30
    goal = {**NO_GOAL, "target_time": target, "estimate_s": 11600}
    plan = build_plan(runs, "2026-11-09", runs_from=5, long_from=10.0, race=goal)
    long_steps = [s.name for w in plan["workouts"] if w.kind == "long" for s in w.steps]
    assert ("race pace" in long_steps) == finish
    assert plan["goal_note"]


@pytest.mark.parametrize("phase", ["step back", "taper"])
def test_reduced_weeks_add_no_run(runs, no_races, phase):
    plan = build_plan(runs, "2026-11-09", runs_from=5, phase=phase, reference_km=30.0,
                      race={**NO_GOAL, "date": "2026-11-22"})
    assert plan["n_runs"] <= 5


def test_harder_target_builds_more_load(runs, no_races):
    def peak_week(target):
        goal = {**NO_GOAL, "target_time": target}
        return max(week_km(w) for w in month(runs, goal=goal, weeks=14))
    easy, mid, hard = peak_week("3:20:00"), peak_week("2:50:00"), peak_week("2:30:00")
    assert easy < mid < hard


def test_load_holds_at_the_target_peak(runs, no_races):
    from src.analysis.goal_planner import parse_time, peak_km
    goal = {**NO_GOAL, "target_time": "3:00:00"}
    limit = peak_km(21.1, parse_time("3:00:00"))
    assert all(week_km(w) <= limit + 0.5 for w in month(runs, goal=goal, weeks=14))


def test_target_sets_session_paces_within_todays_ability(no_races):
    from src.planner.plan_generator import TEMPO_HR, pace_at_hr, target_session_paces
    eff = 0.77
    slow = target_session_paces({**NO_GOAL, "target_time": "2:50:00"}, eff)
    fast = target_session_paces({**NO_GOAL, "target_time": "2:40:00"}, eff)
    too_fast = target_session_paces({**NO_GOAL, "target_time": "2:00:00"}, eff)
    assert fast["tempo"] < slow["tempo"]                          # harder target -> faster tempo
    assert too_fast["tempo"] == pytest.approx(pace_at_hr(eff, TEMPO_HR[1]))  # capped at today's limit
    assert too_fast["notes"]
    assert target_session_paces(NO_GOAL, eff) is None             # no target -> HR-based paces


def frozen_weeks(runs, goal, today, plans_dir, plan_start="2026-10-26"):
    return build_month_plan(runs, covered_until="2026-10-25", plan_start=plan_start, today=today,
                            weeks_ahead=2, goal_race=goal, plans_dir=plans_dir)


def test_finished_week_stays_as_you_saw_it(runs, no_races, tmp_path):
    target = {**NO_GOAL, "target_time": "2:50:00"}
    seen = frozen_weeks(runs, target, "2026-10-28", tmp_path)[0]       # Wednesday of week 1
    later = frozen_weeks(runs, NO_GOAL, "2026-11-03", tmp_path)        # week 1 over, target removed
    assert later[0]["plan"]["frozen"]
    assert later[0]["plan"]["goal_note"] == seen["plan"]["goal_note"]
    assert [w.distance_km for w in later[0]["plan"]["workouts"]] == [w.distance_km for w in seen["plan"]["workouts"]]
    assert not later[1]["plan"].get("frozen")                          # the running week is live


def test_running_week_still_follows_a_new_target(runs, no_races, tmp_path):
    with_target = frozen_weeks(runs, {**NO_GOAL, "target_time": "2:50:00"}, "2026-10-28", tmp_path)[0]["plan"]
    without = frozen_weeks(runs, NO_GOAL, "2026-10-28", tmp_path)[0]["plan"]
    assert with_target["goal_note"] != without["goal_note"]
    assert not without.get("frozen")


def test_frozen_weeks_of_an_old_plan_are_ignored(runs, no_races, tmp_path):
    frozen_weeks(runs, {**NO_GOAL, "target_time": "2:50:00"}, "2026-10-28", tmp_path)
    restarted = frozen_weeks(runs, NO_GOAL, "2026-11-03", tmp_path, plan_start="2026-10-27")
    assert not restarted[0]["plan"].get("frozen")
