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

from src.athlete import ATHLETE

ACTIVITY_DIR = "activities"
ZONES_CACHE = "zones_cache.csv"
MATCH_WINDOW = pd.Timedelta(minutes=10)
MAX_SAMPLE_GAP_S = 10   # a longer gap between samples is a pause, not running time
SPLIT_KM = 1.0
MIN_LAST_SPLIT_KM = 0.05    # a shorter leftover at the end is GPS noise, not a split
SPLITS_DIR = "splits"       # cached splits, one CSV per activity file
ROUTES_DIR = "routes"       # cached GPS routes, one CSV per activity file
HR_DIR = "heart_rate"       # cached per-second heart rate, so a new easy limit is a quick recount


def to_local(ms):
    """FIT timestamps (milliseconds, UTC) -> local Jakarta time without tz."""
    return pd.to_datetime(ms, unit="ms", utc=True).tz_convert("Asia/Jakarta").tz_localize(None)


def read(path):
    """Every message of one activity file. Parsing is the slow part (seconds for a long
    run), so load_time_in_zones parses a new file once and passes the messages on."""
    return [record.message for record in FitFile.from_file(str(path)).records]


def heart_rate(path, messages=None):
    """Heart-rate samples of one activity file: time and hr (local time), plus start,
    the session start (the same on every row; the first sample if the file has none)."""
    times, heart_rates, start = [], [], None
    for message in messages if messages is not None else read(path):
        if isinstance(message, SessionMessage) and message.start_time and start is None:
            start = message.start_time
        elif isinstance(message, RecordMessage) and message.timestamp and message.heart_rate:
            times.append(message.timestamp)
            heart_rates.append(message.heart_rate)
    if not times:
        return pd.DataFrame(columns=["time", "hr", "start"])
    samples = pd.DataFrame({"time": to_local(times), "hr": heart_rates}).sort_values("time")
    samples["start"] = to_local(start) if start else samples["time"].iloc[0]
    return samples.reset_index(drop=True)


def zones_from(samples, easy_hr_max, fit_file):
    """Seconds in all and at or below easy_hr_max from heart_rate() samples, or None."""
    if len(samples) < 2:
        return None
    times = pd.to_datetime(samples["time"])
    # Each sample counts for the time since the previous one (pauses capped).
    seconds = times.diff().dt.total_seconds().fillna(0).clip(upper=MAX_SAMPLE_GAP_S)
    return {
        "start_time": pd.Timestamp(samples["start"].iloc[0]),
        "zone_total_s": seconds.sum(),
        "zone_easy_s": seconds[samples["hr"] <= easy_hr_max].sum(),
        "fit_file": fit_file,
    }


def time_in_zones(path, easy_hr_max=None, messages=None):
    """Seconds at or below / above easy_hr_max (default: the runner's easy limit) for one activity file, or None."""
    return zones_from(heart_rate(path, messages), easy_hr_max or ATHLETE.easy_hr_max, Path(path).name)


def splits(path, split_km=SPLIT_KM, messages=None):
    """Per-kilometre splits of one activity file: km, distance_km, time_s, pace_s, avg_hr.

    Time is moving time (pauses longer than MAX_SAMPLE_GAP_S do not count), and a
    split ends exactly at each whole km (interpolated between samples). The last,
    shorter split is kept unless it is under MIN_LAST_SPLIT_KM.
    """
    times, metres, heart_rates = [], [], []
    for message in messages if messages is not None else read(path):
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


def cache_path(path, folder):
    return Path(path).parent / folder / f"{Path(path).stem}.csv"


def fresh(path, folder):
    """Whether folder holds a cached table for this file that is newer than the file."""
    cache = cache_path(path, folder)
    return cache.exists() and cache.stat().st_mtime >= Path(path).stat().st_mtime


def cached(path, folder, make, messages=None):
    """make(path, messages=...) kept as a CSV in folder next to the file, rebuilt when the file changes."""
    path = Path(path)
    cache = cache_path(path, folder)
    if fresh(path, folder):
        return pd.read_csv(cache)
    table = make(path, messages=messages)
    cache.parent.mkdir(exist_ok=True)
    table.to_csv(cache, index=False)
    return table


def load_heart_rate(path, messages=None):
    """heart_rate(path), kept in HR_DIR next to the file so it is read only once."""
    return cached(path, HR_DIR, heart_rate, messages)


def load_splits(path, messages=None):
    """splits(path), kept in SPLITS_DIR next to the file so it is read only once."""
    return cached(path, SPLITS_DIR, splits, messages)


def route(path, messages=None):
    """GPS points of one activity file, in time order: lat, lon (degrees), km, hr.

    A point without a position (treadmill, GPS still searching) is left out, and so is
    0,0, which some watches write before they have a fix. An indoor run gives an empty table.
    """
    rows = []
    for message in messages if messages is not None else read(path):
        if isinstance(message, RecordMessage) and message.timestamp and message.position_lat is not None \
                and message.position_long is not None and (message.position_lat, message.position_long) != (0, 0):
            rows.append({"t": message.timestamp, "lat": message.position_lat, "lon": message.position_long,
                         "km": message.distance / 1000 if message.distance is not None else None,
                         "hr": message.heart_rate})
    columns = ["lat", "lon", "km", "hr"]
    if not rows:
        return pd.DataFrame(columns=columns)
    points = pd.DataFrame(rows).sort_values("t")
    points["km"] = points["km"].ffill().fillna(0).cummax()
    return points[columns].reset_index(drop=True)


def load_route(path, messages=None):
    """route(path), kept in ROUTES_DIR next to the file so it is read only once."""
    return cached(path, ROUTES_DIR, route, messages)


def load_time_in_zones(activity_dir):
    """One row per readable .fit file in activity_dir (empty table if none)."""
    activity_dir = Path(activity_dir)
    columns = ["start_time", "zone_total_s", "zone_easy_s", "fit_file"]
    zones_file = activity_dir / ZONES_CACHE
    saved = pd.read_csv(zones_file, parse_dates=["start_time"]) if zones_file.exists() else pd.DataFrame()
    # A saved row is reused while the file and the easy limit are unchanged.
    known = {(row.fit_file, row.modified, row.easy_hr_max): row for row in saved.itertuples()}

    rows = []
    for path in sorted(activity_dir.glob("*.fit")):
        modified = path.stat().st_mtime
        hit = known.get((path.name, modified, ATHLETE.easy_hr_max))
        if hit is not None:
            zones = {c: getattr(hit, c) for c in columns}
        else:
            try:
                # A new file is parsed once for everything, so its splits and map are ready
                # before the run is opened. A new easy limit only recounts the cached heart rate.
                caches = (HR_DIR, SPLITS_DIR, ROUTES_DIR)
                messages = None if all(fresh(path, folder) for folder in caches) else read(path)
                zones = zones_from(load_heart_rate(path, messages), ATHLETE.easy_hr_max, path.name)
                load_splits(path, messages)
                load_route(path, messages)
            except Exception:   # a corrupt or non-activity file should not stop the dashboard
                zones = None
        if zones:
            rows.append({**zones, "modified": modified, "easy_hr_max": ATHLETE.easy_hr_max})
    table = pd.DataFrame(rows, columns=columns + ["modified", "easy_hr_max"])
    if rows:
        table.to_csv(zones_file, index=False)
    return table[columns]


def add_time_in_zones(runs, activity_dir):
    """Add zone_total_s / zone_easy_s / fit_file to runs that have a matching file."""
    zones = load_time_in_zones(activity_dir) if Path(activity_dir).is_dir() else pd.DataFrame()
    if zones.empty:
        return runs
    merged = pd.merge_asof(runs.sort_values("start_time"), zones.sort_values("start_time"),
                           on="start_time", direction="nearest", tolerance=MATCH_WINDOW)
    return merged.sort_values("start_time").reset_index(drop=True)
