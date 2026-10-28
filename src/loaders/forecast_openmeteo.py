"""Weather and air-quality forecast from Open-Meteo (free, no API key).

For information only - the plan does not change because of it.
  weather:     16 days ahead, hourly - temperature, dew point, chance and amount
               of rain, weather type (WMO code), UV
  air quality: ~5-7 days ahead       - PM2.5 and US AQI (a model estimate, CAMS)

Results are cached for CACHE_HOURS so the dashboard does not call the API on
every click; force=True fetches now. If the API cannot be reached, the last
cached forecast is used.
"""

import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from src.loaders.weather_openmeteo import CITY_COORDS

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
CACHE_HOURS = 1


def get_json(url, params):
    with urlopen(f"{url}?{urlencode(params)}", timeout=30) as response:
        return json.load(response)


def fetch_forecast(city):
    """Hourly forecast for one city: weather joined with air quality."""
    lat, lon = CITY_COORDS[city]
    place = {"latitude": lat, "longitude": lon, "timezone": "Asia/Jakarta"}

    weather = get_json(FORECAST_URL, {**place, "forecast_days": 16, "hourly": (
        "temperature_2m,dew_point_2m,precipitation_probability,precipitation,weather_code,uv_index")})
    air = get_json(AIR_URL, {**place, "forecast_days": 7, "hourly": "pm2_5,us_aqi"})

    w, a = weather["hourly"], air["hourly"]
    forecast = pd.DataFrame({
        "time": pd.to_datetime(w["time"]),
        "air_temp_c": w["temperature_2m"],
        "dew_point_c": w["dew_point_2m"],
        "rain_chance_pct": w["precipitation_probability"],
        "rain_mm": w["precipitation"],
        "weather_code": w["weather_code"],
        "uv_index": w["uv_index"],
    })
    air_quality = pd.DataFrame({"time": pd.to_datetime(a["time"]), "pm2_5": a["pm2_5"], "us_aqi": a["us_aqi"]})
    return forecast.merge(air_quality, on="time", how="left")


def fetched_at(cache_path):
    """When the cached forecast was downloaded (local time), or None."""
    cache_path = Path(cache_path)
    return pd.Timestamp.fromtimestamp(cache_path.stat().st_mtime) if cache_path.exists() else None


def load_forecast(cache_path, city, force=False):
    """Cached forecast; refreshed when older than CACHE_HOURS or when force=True.

    None if no forecast has ever been downloaded.
    """
    cache_path = Path(cache_path)
    fresh = cache_path.exists() and time.time() - cache_path.stat().st_mtime < CACHE_HOURS * 3600
    if force or not fresh:
        try:
            fetch_forecast(city).to_csv(cache_path, index=False)
        except OSError:
            pass  # offline: fall back to the old cache below, if there is one
    return pd.read_csv(cache_path, parse_dates=["time"]) if cache_path.exists() else None
