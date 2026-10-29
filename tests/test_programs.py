"""Saved training programs (src/programs.py), in a temporary folder."""

import datetime as dt

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
