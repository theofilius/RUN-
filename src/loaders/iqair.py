"""Current, measured air quality from IQAir (free Community plan, needs an API key).

The key is read from the IQAIR_API_KEY environment variable, or from a .env file
in the project folder (.env is in .gitignore, so the key never reaches GitHub).
Without a key, load_current() returns None and only the model forecast is used.

Free plan: current conditions only (no AQI forecast), 500 calls a day - results
are cached for CACHE_MINUTES.
"""

import json
import time
from pathlib import Path

import pandas as pd

from src.env import env_value
from src.loaders.forecast_openmeteo import get_json
from src.loaders.weather_openmeteo import CITY_COORDS

API_URL = "https://api.airvisual.com/v2/nearest_city"
CACHE_MINUTES = 30


def api_key(project_root):
    """IQAIR_API_KEY from the environment or the project's .env file, or None."""
    return env_value("IQAIR_API_KEY", project_root)


def fetch_current(city, key):
    """Measured AQI at the IQAir station nearest to the city's coordinates."""
    lat, lon = CITY_COORDS[city]
    response = get_json(API_URL, {"lat": lat, "lon": lon, "key": key})
    if response.get("status") != "success":
        raise ValueError(f"IQAir: {response.get('data')}")
    data = response["data"]
    pollution = data["current"]["pollution"]
    measured_at = pd.Timestamp(pollution["ts"]).tz_convert("Asia/Jakarta").tz_localize(None)
    return {
        "time": measured_at.isoformat(),
        "us_aqi": pollution["aqius"],
        "main_pollutant": pollution.get("mainus"),
        "station": ", ".join(part for part in (data.get("city"), data.get("state")) if part),
    }


def load_current(cache_path, city, project_root):
    """Cached measurement (refreshed every CACHE_MINUTES), or None without a key or data."""
    key = api_key(project_root)
    if key is None:
        return None
    cache_path = Path(cache_path)
    fresh = cache_path.exists() and time.time() - cache_path.stat().st_mtime < CACHE_MINUTES * 60
    if not fresh:
        try:
            cache_path.write_text(json.dumps(fetch_current(city, key)))
        except (OSError, ValueError, KeyError):
            pass  # offline, bad key or unexpected reply: use the old cache if there is one
    if not cache_path.exists():
        return None
    measured = json.loads(cache_path.read_text())
    measured["time"] = pd.Timestamp(measured["time"])
    return measured
