"""Runs straight from Garmin Connect, through Garmin's official Personal API.

Free for your own data, read-only. Create a key on Garmin Connect web
(Settings -> Personal API Token) and put it in the project's .env file:
    GARMIN_API_KEY=...
    GARMIN_API_KEY_EXPIRES=2027-04-27     # optional: the expiry date you chose
(.env is in .gitignore, so the key never reaches GitHub.) With the expiry
date set, the dashboard reminds you KEY_WARN_DAYS before the key stops working.

How it works:
  1. The key is traded for an access token that lasts 24 hours; the token is
     cached in data/garmin/ and reused while it has over an hour left.
  2. The activity list is read 100 at a time. The first sync reads everything,
     later syncs only the last OVERLAP_DAYS before the newest saved activity
     (edits to a recent run - a renamed title - are picked up too).
  3. For runs in the last FIT_WEEKS, the original .fit file is downloaded to
     data/activities/, so the easy-run check uses per-second heart rate
     (see loaders/fit_activities.py). Each file is downloaded once.
  4. Runs are turned into the same columns as the CSV loader, so every
     analysis works unchanged.

Endpoints are from Garmin's own client (github.com/garmin/connect-personal-api-python).
"""

import base64
import io
import json
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from src.env import env_value
from src.loaders.csv_garmin import MIN_DISTANCE_KM
from src.loaders.fit_activities import ACTIVITY_DIR

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
ACTIVITIES_PATH = "/activitylist-service/activities/search/activities"
FIT_PATH = "/download-service/files/activity/{id}"

API_DIR = "garmin"                 # inside data/
TOKEN_FILE = "token.txt"
ACTIVITIES_FILE = "activities.json"
PAGE_SIZE = 100
TOKEN_MARGIN_S = 3600              # renew the token when under an hour is left
OVERLAP_DAYS = 3
FIT_WEEKS = 12                     # older runs keep using their average HR
SYNC_HOURS = 1                     # the dashboard syncs by itself when older than this
KEY_WARN_DAYS = 14


class KeyRejected(Exception):
    """Garmin refused the API key: expired, revoked or mistyped."""


def api_key(project_root):
    return env_value("GARMIN_API_KEY", project_root)


def key_days_left(project_root, today=None):
    """Days until GARMIN_API_KEY_EXPIRES (negative once passed), or None if not set."""
    expires = env_value("GARMIN_API_KEY_EXPIRES", project_root)
    if not expires:
        return None
    return (pd.Timestamp(expires).normalize() - pd.Timestamp(today or pd.Timestamp.now()).normalize()).days


def request(path, params=None, token=None, key=None, method="GET"):
    """Raw response bytes for one call (key for the token call, token for the rest)."""
    url = BASE_URL + path + (f"?{urlencode(params)}" if params else "")
    auth = f"ApiKey {key}" if key else f"Bearer {token}"
    with urlopen(Request(url, method=method, headers={"Authorization": auth}), timeout=60) as response:
        return response.read()


def token_expiry(token):
    """Expiry time (unix seconds) from the JWT's 'exp' claim."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"]


def access_token(key, cache_path, renew=False):
    """A valid access token, from the cache or a fresh exchange."""
    cache_path = Path(cache_path)
    if not renew and cache_path.exists():
        token = cache_path.read_text().strip()
        if token_expiry(token) - time.time() > TOKEN_MARGIN_S:
            return token
    try:
        token = request(TOKEN_PATH, key=key, method="POST").decode().strip()
    except HTTPError as error:
        if error.code in (400, 401, 403):
            raise KeyRejected("Garmin rejected the API key - it may have expired or been revoked. Create a "
                              "new one on Garmin Connect web (Settings -> Personal API Token) and replace "
                              "GARMIN_API_KEY in .env.") from error
        raise
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(token)
    return token


def fetch_activities(token, start_date=None):
    """Every activity from start_date ('YYYY-MM-DD', or all when None), newest first."""
    activities = []
    while True:
        params = {"start": len(activities), "limit": PAGE_SIZE}
        if start_date:
            params["startDate"] = start_date
        page = json.loads(request(ACTIVITIES_PATH, params, token=token))
        activities += page
        if len(page) < PAGE_SIZE:
            return activities


def download_fit(token, activity_id, folder):
    """Save the activity's original .fit as folder/<id>.fit (it comes zipped)."""
    archive = zipfile.ZipFile(io.BytesIO(request(FIT_PATH.format(id=activity_id), token=token)))
    name = next(n for n in archive.namelist() if n.lower().endswith(".fit"))
    path = Path(folder) / f"{activity_id}.fit"
    path.write_bytes(archive.read(name))
    return path


def is_run(activity):
    return "running" in activity["activityType"]["typeKey"]


def pace(speed_m_s):
    """m/s -> seconds per km (None when missing or standing still)."""
    return 1000 / speed_m_s if speed_m_s else None


def to_runs(activities):
    """Runs of MIN_DISTANCE_KM or more, in the CSV loader's columns, oldest first."""
    rows = [{
        "start_time": pd.Timestamp(a["startTimeLocal"]),
        "activity_type": a["activityType"]["typeKey"].replace("_", " ").title(),   # "Track Running"
        "title": a.get("activityName") or "",
        "distance_km": (a.get("distance") or 0) / 1000,
        "duration_s": a.get("duration"),
        "moving_time_s": a.get("movingDuration") or a.get("duration"),
        "avg_pace_s_per_km": pace(a.get("averageSpeed")),
        "avg_gap_s_per_km": pace(a.get("avgGradeAdjustedSpeed")),
        "avg_hr": a.get("averageHR"),
        "max_hr": a.get("maxHR"),
        "aerobic_te": a.get("aerobicTrainingEffect"),
        "avg_cadence": a.get("averageRunningCadenceInStepsPerMinute"),
        "ascent_m": a.get("elevationGain"),
        "min_temp_c": a.get("minTemperature"),
        "max_temp_c": a.get("maxTemperature"),
        "calories": a.get("calories"),
        "garmin_race": (a.get("eventType") or {}).get("typeKey") == "race",   # Event Type set to Race
    } for a in activities if is_run(a)]
    runs = pd.DataFrame(rows)
    numbers = runs.columns.drop(["start_time", "activity_type", "title", "garmin_race"])
    runs[numbers] = runs[numbers].astype(float)
    runs = runs[runs["distance_km"] >= MIN_DISTANCE_KM]
    return runs.sort_values("start_time").reset_index(drop=True)


def saved_activities(data_dir):
    path = Path(data_dir) / API_DIR / ACTIVITIES_FILE
    return json.loads(path.read_text()) if path.exists() else []


def synced_at(data_dir):
    """When the last sync finished, or None if never."""
    path = Path(data_dir) / API_DIR / ACTIVITIES_FILE
    return pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").tz_convert("Asia/Jakarta").tz_localize(None) \
        if path.exists() else None


def sync(data_dir, project_root, full=False, progress=None):
    """Download new activities and .fit files. Returns a summary, or None without a key.

    progress(done, total) is called while .fit files download (for a progress bar).
    """
    key = api_key(project_root)
    if key is None:
        return None
    folder = Path(data_dir) / API_DIR
    token_path = folder / TOKEN_FILE
    token = access_token(key, token_path)

    saved = [] if full else saved_activities(data_dir)
    start_date = None
    if saved:
        newest = max(pd.Timestamp(a["startTimeLocal"]) for a in saved)
        start_date = f"{newest - pd.Timedelta(days=OVERLAP_DAYS):%Y-%m-%d}"
    try:
        fresh = fetch_activities(token, start_date)
    except HTTPError as error:
        if error.code != 401:
            raise
        token = access_token(key, token_path, renew=True)   # token revoked or expired early
        fresh = fetch_activities(token, start_date)

    # Merge by id; the fresh copy wins.
    by_id = {a["activityId"]: a for a in saved}
    new = [a for a in fresh if a["activityId"] not in by_id]
    by_id.update({a["activityId"]: a for a in fresh})
    activities = sorted(by_id.values(), key=lambda a: a["startTimeLocal"], reverse=True)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ACTIVITIES_FILE).write_text(json.dumps(activities))

    fit_dir = Path(data_dir) / ACTIVITY_DIR
    fit_dir.mkdir(exist_ok=True)
    since = pd.Timestamp.now() - pd.Timedelta(weeks=FIT_WEEKS)
    missing = [a["activityId"] for a in activities
               if is_run(a) and pd.Timestamp(a["startTimeLocal"]) >= since
               and not (fit_dir / f"{a['activityId']}.fit").exists()]
    for done, activity_id in enumerate(missing, 1):
        try:
            download_fit(token, activity_id, fit_dir)
        except (HTTPError, zipfile.BadZipFile, StopIteration):
            pass   # no file for this activity (e.g. manual entry): average HR is used
        if progress:
            progress(done, len(missing))
    return {"activities": len(activities), "runs": sum(map(is_run, activities)),
            "new": len(new), "fit_downloaded": len(missing)}


def load_api_runs(data_dir):
    """Runs from the last sync (empty table if never synced)."""
    activities = saved_activities(data_dir)
    return to_runs(activities) if activities else pd.DataFrame()


if __name__ == "__main__":
    # python -m src.loaders.garmin_api          (add --full to re-read everything)
    import sys

    root = Path(__file__).resolve().parents[2]
    data = root / "data"
    summary = sync(data, root, full="--full" in sys.argv,
                   progress=lambda done, total: print(f"  .fit {done}/{total}", end="\r"))
    if summary is None:
        sys.exit("No GARMIN_API_KEY in the environment or .env.")
    print(f"\n{summary['activities']} activities ({summary['runs']} runs), {summary['new']} new, "
          f"{summary['fit_downloaded']} .fit files downloaded.")
    runs = load_api_runs(data)
    print(f"Runs {runs['start_time'].min():%d %b %Y} to {runs['start_time'].max():%d %b %Y}")
    print(runs[["start_time", "title", "distance_km", "duration_s", "avg_pace_s_per_km", "avg_hr"]].tail().to_string())
