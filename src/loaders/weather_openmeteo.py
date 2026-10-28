"""Hourly air temperature and dew point from Open-Meteo (free, no API key).

The watch's own temperature sensor sits against your warm wrist and
reads several degrees too high, and it cannot measure humidity. So we
look up the real weather for the city and hour of each run instead.

Only city coordinates and dates are sent. Results are saved to a CSV
cache so each city is downloaded once, and later runs work offline.
"""

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

API_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

CITY_COORDS = {
    "Jakarta": (-6.2088, 106.8456),
    "Tangerang": (-6.1783, 106.6319),
    "Bogor": (-6.5971, 106.8060),
}
DEFAULT_CITY = "Jakarta"


def city_for_title(title):
    """Guess the city from a run title like "Tangerang - Base"."""
    for city in CITY_COORDS:
        if city.lower() in str(title).lower():
            return city
    return DEFAULT_CITY


def fetch_hourly(city, start_date, end_date):
    """Download hourly weather for one city between two dates (inclusive)."""
    lat, lon = CITY_COORDS[city]
    query = urlencode({
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "temperature_2m,dew_point_2m",
        "timezone": "Asia/Jakarta",  # same local time as the Garmin export
    })
    with urlopen(f"{API_URL}?{query}", timeout=30) as response:
        hourly = json.load(response)["hourly"]

    return pd.DataFrame({
        "city": city,
        "time": pd.to_datetime(hourly["time"]),
        "air_temp_c": hourly["temperature_2m"],
        "dew_point_c": hourly["dew_point_2m"],
    })


def load_weather(runs, cache_path):
    """Hourly weather for every city and day the runs need, using the cache."""
    cache_path = Path(cache_path)
    cached = pd.read_csv(cache_path, parse_dates=["time"]) if cache_path.exists() else None

    start = f"{runs['start_time'].min():%Y-%m-%d}"
    end = f"{runs['start_time'].max():%Y-%m-%d}"
    needed_cities = runs["title"].map(city_for_title).unique()

    tables = []
    for city in needed_cities:
        if cached is not None:
            have = cached[cached["city"] == city]
            if not have.empty and f"{have['time'].min():%Y-%m-%d}" <= start and f"{have['time'].max():%Y-%m-%d}" >= end:
                tables.append(have)
                continue
        tables.append(fetch_hourly(city, start, end))

    weather = pd.concat(tables, ignore_index=True)
    weather.to_csv(cache_path, index=False)
    return weather
