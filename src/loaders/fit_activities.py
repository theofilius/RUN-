"""Optional per-second heart rate from Garmin activity .fit files.

The Garmin CSV has one row per run, so a run is judged easy or hard by its
average HR alone. If you put the original activity files in data/activities/:
  - Garmin Connect web: open an activity -> gear icon -> Export Original
    (gives a .zip with the .fit inside - unzip it), or
  - the .fit files inside a Garmin "Export Your Data" archive,
then for every run with a file the easy-run check counts the seconds actually
spent at or below EASY_HR_MAX instead.

Runs are matched to files by start time (within MATCH_WINDOW).
Reading a file takes a few seconds, so results are kept in ZONES_CACHE inside
the folder and a file is only read again when it changes.
"""

from pathlib import Path

import pandas as pd
from fit_tool.fit_file import FitFile
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage

from src.config import EASY_HR_MAX

ACTIVITY_DIR = "activities"
ZONES_CACHE = "zones_cache.csv"
MATCH_WINDOW = pd.Timedelta(minutes=10)
MAX_SAMPLE_GAP_S = 10   # a longer gap between samples is a pause, not running time


def to_local(ms):
    """FIT timestamps (milliseconds, UTC) -> local Jakarta time without tz."""
    return pd.to_datetime(ms, unit="ms", utc=True).tz_convert("Asia/Jakarta").tz_localize(None)


def time_in_zones(path, easy_hr_max=EASY_HR_MAX):
    """Seconds at or below / above easy_hr_max for one activity file, or None."""
    times, heart_rates, start = [], [], None
    for record in FitFile.from_file(str(path)).records:
        message = record.message
        if isinstance(message, SessionMessage) and message.start_time and start is None:
            start = message.start_time
        elif isinstance(message, RecordMessage) and message.timestamp and message.heart_rate:
            times.append(message.timestamp)
            heart_rates.append(message.heart_rate)
    if len(times) < 2:
        return None

    samples = pd.DataFrame({"time": to_local(times), "hr": heart_rates}).sort_values("time")
    # Each sample counts for the time since the previous one (pauses capped).
    samples["seconds"] = samples["time"].diff().dt.total_seconds().fillna(0).clip(upper=MAX_SAMPLE_GAP_S)
    easy = samples.loc[samples["hr"] <= easy_hr_max, "seconds"].sum()
    return {
        "start_time": to_local(start) if start else samples["time"].iloc[0],
        "zone_total_s": samples["seconds"].sum(),
        "zone_easy_s": easy,
        "fit_file": Path(path).name,
    }


def load_time_in_zones(activity_dir):
    """One row per readable .fit file in activity_dir (empty table if none)."""
    activity_dir = Path(activity_dir)
    columns = ["start_time", "zone_total_s", "zone_easy_s", "fit_file"]
    cache_path = activity_dir / ZONES_CACHE
    cached = pd.read_csv(cache_path, parse_dates=["start_time"]) if cache_path.exists() else pd.DataFrame()
    # A cached row is reused while the file and the easy limit are unchanged.
    known = {(row.fit_file, row.modified, row.easy_hr_max): row for row in cached.itertuples()}

    rows = []
    for path in sorted(activity_dir.glob("*.fit")):
        modified = path.stat().st_mtime
        hit = known.get((path.name, modified, EASY_HR_MAX))
        if hit is not None:
            zones = {c: getattr(hit, c) for c in columns}
        else:
            try:
                zones = time_in_zones(path)
            except Exception:   # a corrupt or non-activity file should not stop the dashboard
                zones = None
        if zones:
            rows.append({**zones, "modified": modified, "easy_hr_max": EASY_HR_MAX})
    table = pd.DataFrame(rows, columns=columns + ["modified", "easy_hr_max"])
    if rows:
        table.to_csv(cache_path, index=False)
    return table[columns]


def add_time_in_zones(runs, activity_dir):
    """Add zone_total_s / zone_easy_s / fit_file to runs that have a matching file."""
    zones = load_time_in_zones(activity_dir) if Path(activity_dir).is_dir() else pd.DataFrame()
    if zones.empty:
        return runs
    merged = pd.merge_asof(runs.sort_values("start_time"), zones.sort_values("start_time"),
                           on="start_time", direction="nearest", tolerance=MATCH_WINDOW)
    return merged.sort_values("start_time").reset_index(drop=True)
