"""Saved training programs: what you are training for, kept in data/programs.json.

A program is a goal you commit to: a distance, an optional "sub" target, an
optional race date and the day training starts. You can keep several; one is
active, and the dashboard's home page plans from it.

The plan itself is not stored: it is rebuilt from your runs every time, so it
keeps adapting (paces follow your fitness, a missed long run does not grow).
Each finished week is frozen in the program's own folder
(data/programs/<id>/plans/), so a program's history never changes.

Without a race date a program runs for its "weeks" (DEFAULT_WEEKS).

A program can have a milestone: a shorter race to pass first (a 10K goal is
tested on a 5K, see MILESTONE_DISTANCE), at the time your target is worth on
that distance (Riegel). Stage 1 trains for that test, which ends its "weeks".
A race marked as a race in Garmin that is at least as long and at least as fast
passes it; stage 2, the program's own goal, starts the Monday after. Stage 2
runs for the program's "weeks" (or to its race date). A missed test is yours to
decide: repeat (REPEAT_WEEKS more) or give up, which stops the program.
Check-ins during stage 1 (src/analysis/checkpoint.py) can move the test later.
"""

import json
import math
import shutil
import uuid
from datetime import date
from pathlib import Path

import pandas as pd

from src.analysis.goal_planner import REALISTIC_GAIN, parse_time, peak_km, riegel_exponent, weeks_needed
from src.analysis.races import race_mask
from src.config import LONG_RUN_DAY
from src.units import format_duration

PROGRAMS_FILE = "programs.json"
PROGRAMS_DIR = "programs"
DEFAULT_WEEKS = 16
LEGACY_PLANS = "plans"   # frozen weeks from before programs existed
FINAL_PLANS = "plans-final"   # frozen weeks of stage 2 of a program with a milestone

MILESTONE_DISTANCE = {10.0: 5.0, 21.1: 10.0, 42.2: 21.1}   # goal distance -> the race it is tested on first
MILESTONE_WEEKS = (4, 12)   # suggested stage 1 length: shortest, longest
REPEAT_WEEKS = 4            # extra weeks before the next test after a missed one
FINAL_WEEKS = {10.0: 6, 21.1: 8, 42.2: 12}   # suggested stage 2 length: longer races need more endurance work
PASS_DISTANCE_SHARE = 0.98  # GPS: a 5K race may measure 4.9 km


def load(data_dir):
    """{"active": id or None, "programs": [...]}, oldest first."""
    path = Path(data_dir) / PROGRAMS_FILE
    return json.loads(path.read_text()) if path.exists() else {"active": None, "programs": []}


def save(data_dir, store):
    path = Path(data_dir) / PROGRAMS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2))


def new_program(name, distance_km, target_time=None, race_date=None, start_date=None, weeks=DEFAULT_WEEKS,
                milestone=None):
    """milestone: None, or {"distance_km", "target_time", "weeks"} from suggest_milestone."""
    return {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "distance_km": distance_km,
        "target_time": target_time,
        "race_date": race_date,
        "start_date": start_date or date.today().isoformat(),
        "weeks": weeks,
        "created": date.today().isoformat(),
        "milestone": milestone,
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


def plans_dir(data_dir, program, final=False):
    """Frozen weeks; final=True for stage 2 of a program with a milestone."""
    return Path(data_dir) / PROGRAMS_DIR / program["id"] / (FINAL_PLANS if final else "plans")


def monday_of(day):
    day = pd.Timestamp(day).normalize()
    return day - pd.Timedelta(days=day.weekday())


# ---- milestone ----

def milestone_distance(distance_km):
    """The distance a goal is tested on first, or None (a 5K has no milestone)."""
    return next((m for d, m in MILESTONE_DISTANCE.items() if abs(d - distance_km) < 0.1), None)


def milestone_target_s(distance_km, target_time):
    """What the target is worth on the milestone distance (Riegel), in whole seconds."""
    km = milestone_distance(distance_km)
    return math.floor(parse_time(target_time) * (km / distance_km) ** riegel_exponent(km, distance_km))


def final_weeks(distance_km):
    return FINAL_WEEKS[min(FINAL_WEEKS, key=lambda d: abs(d - distance_km))]


def suggest_milestone(distance_km, target_time, estimate_s=None):
    """{"distance_km", "target_time", "weeks"} for a goal with a target, or None.

    estimate_s: today's estimate on the milestone distance. Stage 1 lasts the weeks
    that gap takes at REALISTIC_GAIN a week, within MILESTONE_WEEKS.
    """
    km = milestone_distance(distance_km)
    if km is None or not target_time:
        return None
    target_s = milestone_target_s(distance_km, target_time)
    needed = weeks_needed(estimate_s, target_s, REALISTIC_GAIN) if estimate_s else None
    weeks = min(MILESTONE_WEEKS[1], max(MILESTONE_WEEKS[0], math.ceil(needed or 0)))
    return {"distance_km": km, "target_time": format_duration(target_s), "weeks": weeks}


def stage(program):
    """None (no milestone), 'milestone', 'final' (it was passed) or 'stopped' (given up)."""
    m = program.get("milestone")
    if not m:
        return None
    if m.get("gave_up"):
        return "stopped"
    return "final" if m.get("passed") else "milestone"


def test_date(program):
    """The day of the milestone test: the long-run day of stage 1's last week."""
    m = program["milestone"]
    return (monday_of(program["start_date"]) + pd.Timedelta(weeks=m["weeks"] - 1, days=LONG_RUN_DAY)).date()


def final_start(program):
    """Monday stage 2 starts: after the week of the pass, or (provisionally) after the test week."""
    m = program["milestone"]
    if m.get("passed"):
        return (monday_of(m["passed"]["date"]) + pd.Timedelta(weeks=1)).date()
    return (monday_of(program["start_date"]) + pd.Timedelta(weeks=m["weeks"])).date()


def milestone_goal(program):
    """The milestone test as the planner's goal race: speed first (two hard sessions in
    build weeks), and a race week without the 2-week taper."""
    m = program["milestone"]
    goal = {"name": f"milestone {m['distance_km']:g} km", "distance_km": m["distance_km"],
            "target_time": m["target_time"], "date": test_date(program).isoformat(), "taper_weeks": 1,
            "hard_sessions": 2}
    if program.get("target_time"):   # build the weekly distance for the final goal already:
        # it predicts 10 km time best (Suwankan 2024), and the test is only a check on the way
        goal["peak_km"] = peak_km(program["distance_km"], parse_time(program["target_time"]))
    return goal


def find_pass(program, runs):
    """The first race since the start that passes the milestone, as a dict, or None.

    A longer race counts at what it is worth on the milestone distance (Riegel).
    """
    m = program["milestone"]
    races = runs[race_mask(runs) & (runs["start_time"] >= pd.Timestamp(program["start_date"]))
                 & (runs["distance_km"] >= PASS_DISTANCE_SHARE * m["distance_km"])].sort_values("start_time")
    for race in races.itertuples():
        km = max(race.distance_km, m["distance_km"])
        worth_s = race.duration_s * (m["distance_km"] / km) ** riegel_exponent(m["distance_km"], km)
        if worth_s <= parse_time(m["target_time"]):
            return {"date": str(race.start_time.date()), "time_s": round(race.duration_s),
                    "distance_km": round(race.distance_km, 2)}
    return None


def test_missed(program, covered_until):
    """True once the data covers the test day and the milestone is still not passed."""
    return stage(program) == "milestone" and pd.Timestamp(covered_until).date() >= test_date(program)


def repeat_milestone(data_dir, store, program_id, today):
    """Another REPEAT_WEEKS of stage 1, counted from this week at the earliest."""
    program = find(store, program_id)
    m = program["milestone"]
    this_week = (monday_of(today) - monday_of(program["start_date"])).days // 7 + 1
    missed = m.get("missed", []) + [test_date(program).isoformat()]
    update(data_dir, store, program_id,
           milestone={**m, "weeks": max(m["weeks"], this_week) + REPEAT_WEEKS, "missed": missed})


def test_week(program):
    """The number of stage 1's test week (its last)."""
    return program["milestone"]["weeks"]


def check_in_choice(program, end):
    """'postpone' or 'keep' if you already answered the check-in ending on `end`, else None."""
    return next((c["choice"] for c in program["milestone"].get("check_ins", []) if c["end"] == str(end)), None)


def answer_check_in(data_dir, store, program_id, end, choice, weeks=0):
    """Record your answer to a check-in; 'postpone' moves the test `weeks` later."""
    program = find(store, program_id)
    m = program["milestone"]
    check_ins = m.get("check_ins", []) + [{"end": str(end), "choice": choice}]
    update(data_dir, store, program_id,
           milestone={**m, "weeks": m["weeks"] + (weeks if choice == "postpone" else 0), "check_ins": check_ins})


def give_up(data_dir, store, program_id, today):
    program = find(store, program_id)
    update(data_dir, store, program_id, milestone={**program["milestone"], "gave_up": str(today)})


def current_goal(program):
    """The goal the plan trains for now: the milestone test in stage 1, else the program's own."""
    return milestone_goal(program) if stage(program) == "milestone" else goal(program)


# ---- length and status ----

def week_count(program):
    """Monday-Sunday weeks from the week of the start to the race week (or the program's length).

    With a milestone: stage 1, then stage 2 from final_start; a stopped program ends with stage 1.
    """
    monday = monday_of(program["start_date"])
    if stage(program) == "stopped":
        return program["milestone"]["weeks"]
    if stage(program):
        monday = pd.Timestamp(final_start(program))
    if program.get("race_date"):
        weeks = (pd.Timestamp(program["race_date"]) - monday).days // 7 + 1
    else:
        weeks = program.get("weeks") or DEFAULT_WEEKS
    return weeks + (monday - monday_of(program["start_date"])).days // 7


def status(program, today):
    """'upcoming', 'running', 'finished' or 'stopped' (a milestone given up)."""
    if stage(program) == "stopped":
        return "stopped"
    start = pd.Timestamp(program["start_date"]).date()
    end = (monday_of(program["start_date"]) + pd.Timedelta(weeks=week_count(program)) - pd.Timedelta(days=1)).date()
    if today < start:
        return "upcoming"
    return "finished" if today > end else "running"


def is_live(program, today):
    """A program the home page plans from."""
    return status(program, today) in ("upcoming", "running")


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
