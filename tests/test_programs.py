"""Saved training programs (src/programs.py), in a temporary folder."""

import datetime as dt

import pandas as pd

from src import programs


def test_add_activate_and_remove(tmp_path):
    store = programs.load(tmp_path)
    hm = programs.new_program("HM", 21.1, "2:40:00", "2027-04-11", "2026-11-02")
    ten = programs.new_program("10K", 10.0, None, None, "2026-11-02", weeks=12)
    programs.add(tmp_path, store, hm)
    programs.add(tmp_path, store, ten, make_active=False)
    store = programs.load(tmp_path)                               # it is saved
    assert programs.active(store)["name"] == "HM"
    (programs.plans_dir(tmp_path, hm)).mkdir(parents=True)
    programs.remove(tmp_path, store, hm["id"])
    assert programs.active(store)["name"] == "10K"                # another one takes over
    assert not programs.plans_dir(tmp_path, hm).exists()          # its frozen weeks go too


def test_length_runs_to_the_race_week():
    program = programs.new_program("HM", 21.1, None, "2027-04-11", "2026-10-28")   # Wed, race on a Sunday
    assert programs.week_count(program) == 24                     # Mon 26 Oct ... week of 5 Apr
    assert programs.week_count(programs.new_program("x", 10.0, weeks=12)) == 12


def test_status_follows_the_dates():
    program = programs.new_program("HM", 21.1, None, "2027-04-11", "2026-11-02")
    assert programs.status(program, dt.date(2026, 10, 30)) == "upcoming"
    assert programs.status(program, dt.date(2027, 1, 5)) == "running"
    assert programs.status(program, dt.date(2027, 4, 12)) == "finished"


def test_the_old_goal_becomes_the_first_program(tmp_path):
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "week-2026-10-26.pkl").write_bytes(b"frozen")
    old = {"name": "Next half marathon", "distance_km": 21.1, "target_time": "2:40:00", "date": None}
    store = programs.migrate(tmp_path, old, "2026-10-28")
    program = programs.active(store)
    assert (program["target_time"], program["start_date"]) == ("2:40:00", "2026-10-28")
    assert (programs.plans_dir(tmp_path, program) / "week-2026-10-26.pkl").read_bytes() == b"frozen"
    assert programs.migrate(tmp_path, {**old, "target_time": None}, "2026-11-30") == store   # only once


def ten_k_with_milestone(weeks=4):
    milestone = programs.suggest_milestone(10.0, "1:10:00", estimate_s=40 * 60)
    program = programs.new_program("10K", 10.0, "1:10:00", None, "2026-10-29", weeks=4,
                                   milestone={**milestone, "weeks": weeks})
    return program


def a_race(start, km, minutes):
    return pd.DataFrame([{"start_time": pd.Timestamp(start), "distance_km": km, "duration_s": minutes * 60,
                          "garmin_race": True}])


def test_the_milestone_is_the_target_on_a_shorter_race():
    m = programs.suggest_milestone(10.0, "1:10:00", estimate_s=40 * 60)
    assert (m["distance_km"], m["target_time"]) == (5.0, "0:33:34")          # Riegel, exponent 1.06
    assert m["weeks"] == programs.MILESTONE_WEEKS[1]                          # 19 weeks needed, capped
    assert programs.suggest_milestone(42.2, "5:00:00")["distance_km"] == 21.1
    assert programs.suggest_milestone(5.0, "0:30:00") is None                 # a 5K has no milestone


def test_stage_one_ends_with_the_test_then_stage_two_follows():
    program = ten_k_with_milestone()
    assert programs.test_date(program) == dt.date(2026, 11, 21)              # Saturday of week 4
    assert programs.final_start(program) == dt.date(2026, 11, 23)
    assert programs.week_count(program) == 8
    assert programs.current_goal(program)["distance_km"] == 5.0


def test_a_fast_enough_race_passes_and_stage_two_starts_the_monday_after():
    program = ten_k_with_milestone()
    slow = a_race("2026-11-14 06:00", 5.0, 35)
    assert programs.find_pass(program, slow) is None
    passed = programs.find_pass(program, pd.concat([slow, a_race("2026-11-17 19:00", 4.95, 33)]))
    assert passed["date"] == "2026-11-17"
    program["milestone"]["passed"] = passed
    assert programs.stage(program) == "final"
    assert programs.final_start(program) == dt.date(2026, 11, 23)
    assert programs.current_goal(program)["distance_km"] == 10.0
    # A 10K counts at what it is worth on 5K: 1:09 is about 33:05.
    assert programs.find_pass(ten_k_with_milestone(), a_race("2026-11-14 06:00", 10.0, 69))


def test_a_missed_test_is_repeated_or_given_up(tmp_path):
    store = programs.load(tmp_path)
    program = ten_k_with_milestone()
    programs.add(tmp_path, store, program)
    assert not programs.test_missed(program, dt.date(2026, 11, 20))
    assert programs.test_missed(program, dt.date(2026, 11, 21))
    programs.repeat_milestone(tmp_path, store, program["id"], dt.date(2026, 11, 25))   # decided in week 5
    assert programs.test_date(program) == dt.date(2026, 12, 26)              # week 5 + 4 weeks
    assert program["milestone"]["missed"] == ["2026-11-21"]
    programs.give_up(tmp_path, store, program["id"], dt.date(2026, 12, 28))
    assert programs.status(program, dt.date(2026, 12, 28)) == "stopped"
    assert not programs.is_live(program, dt.date(2026, 12, 28))


def test_a_postponed_check_in_moves_the_test(tmp_path):
    store = programs.load(tmp_path)
    program = ten_k_with_milestone(weeks=6)
    programs.add(tmp_path, store, program)
    programs.answer_check_in(tmp_path, store, program["id"], dt.date(2026, 11, 22), "postpone", 2)
    assert programs.test_date(program) == dt.date(2026, 12, 19)
    assert programs.check_in_choice(program, dt.date(2026, 11, 22)) == "postpone"
    assert programs.check_in_choice(program, dt.date(2026, 12, 6)) is None
