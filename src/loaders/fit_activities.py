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
from numpy import interp as np_interp
from fit_tool.fit_file import FitFile
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage

from src.config import EASY_HR_MAX

ACTIVITY_DIR = "activities"
ZONES_CACHE = "zones_cache.csv"
MATCH_WINDOW = pd.Timedelta(minutes=10)
MAX_SAMPLE_GAP_S = 10   # a longer gap between samples is a pause, not running time
SPLIT_KM = 1.0
MIN_LAST_SPLIT_KM = 0.05    # a shorter leftover at the end is GPS noise, not a split
SPLITS_DIR = "splits"       # cached splits, one CSV per activity file


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


def splits(path, split_km=SPLIT_KM):
    """Per-kilometre splits of one activity file: km, distance_km, time_s, pace_s, avg_hr.

    Time is moving time (pauses longer than MAX_SAMPLE_GAP_S do not count), and a
    split ends exactly at each whole km (interpolated between samples). The last,
    shorter split is kept unless it is under MIN_LAST_SPLIT_KM.
    """
    times, metres, heart_rates = [], [], []
    for record in FitFile.from_file(str(path)).records:
        message = record.message
        if isinstance(message, RecordMessage) and message.timestamp and message.distance is not None:
            times.append(message.timestamp / 1000)
            metres.append(message.distance)
            heart_rates.append(message.heart_rate)
    columns = ["km", "distance_km", "time_s", "pace_s", "avg_hr"]
    if len(times) < 2:
        return pd.DataFrame(columns=columns)

    samples = pd.DataFrame({"t": times, "km": pd.Series(metres) / 1000, "hr": heart_rates}).sort_values("t")
    samples["km"] = samples["km"].cummax()          # GPS distance never runs backwards
    samples["moving"] = samples["t"].diff().fillna(0).clip(upper=MAX_SAMPLE_GAP_S).cumsum()

    total_km = samples["km"].iloc[-1]
    edges = [i * split_km for i in range(int(total_km // split_km) + 1)]
    if total_km - edges[-1] >= MIN_LAST_SPLIT_KM:
        edges.append(total_km)
    # Moving time at each edge, interpolated on distance.
    at_edge = np_interp(edges, samples["km"].values, samples["moving"].values)

    rows = []
    for i in range(1, len(edges)):
        lo, hi = edges[i - 1], edges[i]
        seconds = at_edge[i] - at_edge[i - 1]
        hr = samples.loc[(samples["km"] > lo) & (samples["km"] <= hi), "hr"].dropna()
        rows.append({"km": i, "distance_km": hi - lo, "time_s": seconds, "pace_s": seconds / (hi - lo),
                     "avg_hr": hr.mean() if len(hr) else None})
    return pd.DataFrame(rows, columns=columns)


def load_splits(path):
    """splits(path), kept in SPLITS_DIR next to the file so it is read only once."""
    path = Path(path)
    cache = path.parent / SPLITS_DIR / f"{path.stem}.csv"
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return pd.read_csv(cache)
    table = splits(path)
    cache.parent.mkdir(exist_ok=True)
    table.to_csv(cache, index=False)
    return table


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
