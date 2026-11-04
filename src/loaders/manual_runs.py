"""Runs a runner without Garmin logs by hand, kept in <their folder>/manual_runs.json.

Each run holds what the evaluation reads (see REQUIRED):
  date and start time   which planned day it belongs to (run_review, weekly evaluation)
  distance and time     done / short / long against the menu, pace, weekly load
  average heart rate    easy or hard (easy_check), efficiency = speed / HR (fitness trend,
                        check-ins); copy it from any watch or app that shows it
  max heart rate        optional, shown in the run analysis
  race                  a race or time trial: estimates, and passing a milestone test

They join the runs the entered stats describe (manual_stats.py), with the same columns.
Logged runs start the day after the stats' history ends, so nothing is counted twice.
Once a runner logs runs, the data covers up to yesterday: a planned run that was not
logged counts as not run - the plan reacts as it would to a Garmin sync.
"""

import json
import uuid
from pathlib import Path

import pandas as pd

from src.loaders.manual_stats import EMPTY

FILE = "manual_runs.json"
TITLE = "logged by hand"
MIN_KM = 1.0                  # as the loaders: shorter recordings are left out
REQUIRED = ("start", "distance_km", "duration_s", "avg_hr")


def load(data_dir):
    path = Path(data_dir) / FILE
    return json.loads(path.read_text()) if path.exists() else []


def save(data_dir, entries):
    path = Path(data_dir) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(entries, key=lambda e: e["start"]), indent=2))


def problems(entry, first_day, today, max_hr):
    """What is wrong with an entry, as keys for the dashboard's texts (empty when fine)."""
    found = [f"missing {k}" for k in REQUIRED if entry.get(k) in (None, "")]
    if found:
        return found
    day = pd.Timestamp(entry["start"]).date()
    if day < first_day:
        found.append("before stats")
    if day > today:
        found.append("in future")
    if entry["distance_km"] < MIN_KM:
        found.append("too short")
    pace = entry["duration_s"] / entry["distance_km"]
    if not 120 <= pace <= 1200:                # 2:00 to 20:00 per km: a typo, not a run
        found.append("odd pace")
    if not 60 <= entry["avg_hr"] < max_hr:
        found.append("odd avg hr")
    if entry.get("max_hr") and not entry["avg_hr"] <= entry["max_hr"] <= max_hr + 10:
        found.append("odd max hr")
    return found


def add(data_dir, entry):
    """Save a run; returns it with its id."""
    entries = load(data_dir)
    entry = {**entry, "id": uuid.uuid4().hex[:8]}
    save(data_dir, entries + [entry])
    return entry


def remove(data_dir, run_id):
    save(data_dir, [e for e in load(data_dir) if e["id"] != run_id])


def to_runs(entries):
    """The logged runs as a runs table (the columns of the Garmin loaders)."""
    if not entries:
        return pd.DataFrame()
    runs = pd.DataFrame([{
        "start_time": pd.Timestamp(e["start"]), "title": e.get("title") or TITLE,
        "distance_km": float(e["distance_km"]), "duration_s": float(e["duration_s"]),
        "avg_hr": float(e["avg_hr"]), "max_hr": float(e["max_hr"]) if e.get("max_hr") else float("nan"),
        "garmin_race": bool(e.get("race")), "manual_id": e["id"],
    } for e in entries])
    runs["activity_type"] = "Running"
    runs["moving_time_s"] = runs["duration_s"]
    runs["avg_pace_s_per_km"] = runs["duration_s"] / runs["distance_km"]
    for column in EMPTY:
        runs[column] = float("nan")
    return runs


def with_logged(runs, entries):
    """The stats' runs plus the logged ones, in time order."""
    logged = to_runs(entries)
    if logged.empty:
        return runs
    return pd.concat([runs, logged], ignore_index=True).sort_values("start_time").reset_index(drop=True)


def covered(stats_covered, entries, today):
    """Last day the data covers: the stats' last day, or yesterday once runs are logged."""
    if not entries:
        return stats_covered
    return max(stats_covered, pd.Timestamp(today).date() - pd.Timedelta(days=1))
