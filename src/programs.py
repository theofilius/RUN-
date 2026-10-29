"""Saved training programs: what you are training for, kept in data/programs.json.

A program is a goal you commit to: a distance, an optional "sub" target, an
optional race date and the day training starts. You can keep several; one is
active, and the dashboard's home page plans from it.

The plan itself is not stored: it is rebuilt from your runs every time, so it
keeps adapting (paces follow your fitness, a missed long run does not grow).
Each finished week is frozen in the program's own folder
(data/programs/<id>/plans/), so a program's history never changes.

Without a race date a program runs for its "weeks" (DEFAULT_WEEKS).
"""

import json
import shutil
import uuid
from datetime import date
from pathlib import Path

import pandas as pd

PROGRAMS_FILE = "programs.json"
PROGRAMS_DIR = "programs"
DEFAULT_WEEKS = 16
LEGACY_PLANS = "plans"   # frozen weeks from before programs existed


def load(data_dir):
    """{"active": id or None, "programs": [...]}, oldest first."""
    path = Path(data_dir) / PROGRAMS_FILE
    return json.loads(path.read_text()) if path.exists() else {"active": None, "programs": []}


def save(data_dir, store):
    path = Path(data_dir) / PROGRAMS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2))


def new_program(name, distance_km, target_time=None, race_date=None, start_date=None, weeks=DEFAULT_WEEKS):
    return {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "distance_km": distance_km,
        "target_time": target_time,
        "race_date": race_date,
        "start_date": start_date or date.today().isoformat(),
        "weeks": weeks,
        "created": date.today().isoformat(),
    }


def find(store, program_id):
    return next((p for p in store["programs"] if p["id"] == program_id), None)


def active(store):
    return find(store, store.get("active"))


def add(data_dir, store, program, make_active=True):
    store["programs"].append(program)
    if make_active or not store.get("active"):
        store["active"] = program["id"]
    save(data_dir, store)


def update(data_dir, store, program_id, **changes):
    find(store, program_id).update(changes)
    save(data_dir, store)


def remove(data_dir, store, program_id):
    """Delete a program and its frozen weeks."""
    store["programs"] = [p for p in store["programs"] if p["id"] != program_id]
    if store.get("active") == program_id:
        store["active"] = store["programs"][-1]["id"] if store["programs"] else None
    save(data_dir, store)
    shutil.rmtree(Path(data_dir) / PROGRAMS_DIR / program_id, ignore_errors=True)


def goal(program):
    """The program as the planner's goal race."""
    return {"name": program["name"], "distance_km": program["distance_km"],
            "target_time": program.get("target_time"), "date": program.get("race_date")}


def plans_dir(data_dir, program):
    return Path(data_dir) / PROGRAMS_DIR / program["id"] / "plans"


def week_count(program):
    """Monday-Sunday weeks from the week of the start to the race week (or the program's length)."""
    start = pd.Timestamp(program["start_date"])
    monday = start - pd.Timedelta(days=start.weekday())
    if program.get("race_date"):
        return (pd.Timestamp(program["race_date"]) - monday).days // 7 + 1
    return program.get("weeks") or DEFAULT_WEEKS


def status(program, today):
    """'upcoming', 'running' or 'finished'."""
    start = pd.Timestamp(program["start_date"]).date()
    monday = pd.Timestamp(program["start_date"]) - pd.Timedelta(days=pd.Timestamp(program["start_date"]).weekday())
    end = (monday + pd.Timedelta(weeks=week_count(program)) - pd.Timedelta(days=1)).date()
    if today < start:
        return "upcoming"
    return "finished" if today > end else "running"


def migrate(data_dir, old_goal, plan_start):
    """First run with programs: turn the goal you had (data/goal.json) into the first
    program, starting on PLAN_START, and keep its frozen weeks."""
    store = load(data_dir)
    if store["programs"]:
        return store
    program = new_program(old_goal.get("name") or "Training", old_goal["distance_km"], old_goal.get("target_time"),
                          old_goal.get("date"), str(pd.Timestamp(plan_start).date()))
    legacy = Path(data_dir) / LEGACY_PLANS
    if legacy.is_dir():
        target = plans_dir(data_dir, program)
        target.mkdir(parents=True, exist_ok=True)
        for frozen in legacy.glob("week-*.pkl"):
            shutil.copy2(frozen, target / frozen.name)
    add(data_dir, store, program)
    return store
