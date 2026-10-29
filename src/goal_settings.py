"""Your goal race, as chosen in the dashboard.

The active training program (data/programs.json, see src/programs.py) when there
is one; otherwise data/goal.json, the older single goal. Anything not saved falls
back to GOAL_RACE in config.py. All of it lives in data/, private and out of git.
"""

import json
from pathlib import Path

from src.config import GOAL_RACE

GOAL_FILE = Path(__file__).resolve().parent.parent / "data" / "goal.json"

DISTANCES = {"5K": 5.0, "10K": 10.0, "Half marathon": 21.1, "Marathon": 42.2}


def load_goal(path=GOAL_FILE):
    from src import programs
    program = programs.active(programs.load(Path(path).parent))
    if program:
        return {**GOAL_RACE, **programs.goal(program)}
    goal = dict(GOAL_RACE)
    path = Path(path)
    if path.exists():
        goal.update(json.loads(path.read_text()))
    return goal


def save_goal(goal, path=GOAL_FILE):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(goal, indent=2))


def distance_name(km):
    """'Half marathon' for 21.1 (nearest standard distance)."""
    return min(DISTANCES, key=lambda name: abs(DISTANCES[name] - km))
