"""Which runs are races.

A run is a race when either:
  - you set its Event Type to "Race" in Garmin Connect (activity -> gear/edit ->
    Event Type). The Garmin API sync reads this as the garmin_race column; or
  - its start time is listed in RACES in config.py (for CSV data, which has no
    event type, or to give a race a short name).

Races are left out of training trends, get recovery days after them in the
plan, and the latest one anchors the goal estimate.
"""

import pandas as pd

from src.config import RACES


def race_mask(runs):
    """True for every run that is a race."""
    listed = runs["start_time"].isin(pd.to_datetime([race["start"] for race in RACES.values()]))
    if "garmin_race" not in runs:
        return listed
    return listed | runs["garmin_race"].astype("boolean").fillna(False).astype(bool)


def race_list(runs):
    """{name: {"start", "distance_km"}} for every race in runs, oldest first.

    The name is the one in RACES when the race is listed there, else its Garmin title.
    """
    names = {pd.Timestamp(race["start"]): name for name, race in RACES.items()}
    races = {}
    for run in runs[race_mask(runs)].sort_values("start_time").itertuples():
        name = names.get(run.start_time, run.title or "Race")
        if name in races:
            name = f"{name} ({run.start_time:%d %b %Y})"
        races[name] = {"start": str(run.start_time), "distance_km": run.distance_km}
    return races
