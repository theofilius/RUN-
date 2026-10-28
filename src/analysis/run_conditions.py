"""Forecast conditions for a run day, in the two usual running windows.

For information only. For each window we average the forecast hours and give:
  heat slowdown % - same rule of thumb as heat_adjust.py (temp F + dew point F)
  rain chance     - the highest chance in the window
  US AQI          - with the US EPA category name

Air quality combines two sources (combine_air):
  now        - IQAir measurement (if you have an API key)
  next 48 h  - Open-Meteo model, scaled by how far off the model is right now;
               the correction fades out linearly over ADJUST_HOURS
  later      - Open-Meteo model only (7 days); after that no air-quality data
"""

import math

import numpy as np
import pandas as pd

from src.analysis.heat_adjust import slowdown_pct
from src.config import RUN_HOURS

ADJUST_HOURS = 48
RATIO_LIMITS = (0.5, 2.0)   # never scale the model by more than this

# Running windows as (first hour, last hour), local time: your usual time first,
# early morning as the alternative when the evening looks bad.
WINDOWS = {"run time": RUN_HOURS, "early morning": (5, 7)}

# WMO weather codes (used by Open-Meteo) -> icon and short label.
WEATHER_TYPES = [
    ((0,), "☀️", "clear"),
    ((1, 2), "🌤", "partly cloudy"),
    ((3,), "☁️", "cloudy"),
    ((45, 48), "🌫", "fog"),
    ((51, 53, 55, 56, 57), "🌦", "drizzle"),
    ((61, 63, 65, 66, 67), "🌧", "rain"),
    ((80, 81, 82), "🌧", "showers"),
    ((95, 96, 99), "⛈", "thunderstorm"),
]


def weather_type(code):
    """(icon, label) for a WMO weather code."""
    if code is None or (isinstance(code, float) and math.isnan(code)):
        return "", ""
    return next(((icon, label) for codes, icon, label in WEATHER_TYPES if int(code) in codes), ("", ""))


def next_hours(forecast, now, hours=6):
    """The current hour plus the next `hours` hours, with heat slowdown and weather type."""
    start = now.floor("h")
    rows = forecast[(forecast["time"] >= start) & (forecast["time"] <= start + pd.Timedelta(hours=hours))].copy()
    rows["heat_slowdown_pct"] = slowdown_pct(rows["air_temp_c"], rows["dew_point_c"])
    rows["icon"], rows["weather"] = zip(*rows["weather_code"].map(weather_type)) if len(rows) else ([], [])
    return rows

# US EPA Air Quality Index categories: (upper limit, name).
AQI_LEVELS = [
    (50, "good"),
    (100, "moderate"),
    (150, "unhealthy for sensitive groups"),
    (200, "unhealthy"),
    (300, "very unhealthy"),
    (math.inf, "hazardous"),
]


def aqi_label(aqi):
    return next(name for limit, name in AQI_LEVELS if aqi <= limit)


def combine_air(forecast, measured):
    """Forecast with us_aqi corrected by a current measurement, plus an aqi_source column.

    ratio  = measured AQI / model AQI for the same hour (limited to RATIO_LIMITS)
    weight = 1 now, falling linearly to 0 at ADJUST_HOURS ahead
    AQI    = model AQI x (1 + (ratio - 1) x weight)
    """
    combined = forecast.copy()
    combined["aqi_source"] = np.where(combined["us_aqi"].notna(), "model", "")
    if measured is None:
        return combined

    hour = measured["time"].floor("h")
    model_now = combined.loc[combined["time"] == hour, "us_aqi"]
    if model_now.empty or not model_now.iloc[0] > 0:
        return combined

    ratio = float(np.clip(measured["us_aqi"] / model_now.iloc[0], *RATIO_LIMITS))
    hours_ahead = (combined["time"] - hour).dt.total_seconds() / 3600
    weight = np.clip(1 - hours_ahead / ADJUST_HOURS, 0, 1).where(hours_ahead >= 0, 0)
    adjusted = (weight > 0) & combined["us_aqi"].notna()
    combined.loc[adjusted, "us_aqi"] = combined.loc[adjusted, "us_aqi"] * (1 + (ratio - 1) * weight[adjusted])
    combined.loc[adjusted, "aqi_source"] = "adjusted"
    combined.loc[combined["time"] == hour, ["us_aqi", "aqi_source"]] = [measured["us_aqi"], "measured"]
    return combined


def window_conditions(forecast, day, hours):
    """Average forecast for one day and window, or None if the forecast does not reach it."""
    first, last = hours
    rows = forecast[(forecast["time"].dt.date == day)
                    & (forecast["time"].dt.hour >= first) & (forecast["time"].dt.hour <= last)]
    if rows.empty:
        return None
    temp, dew = rows["air_temp_c"].mean(), rows["dew_point_c"].mean()
    aqi = rows["us_aqi"].mean()
    worst_code = rows["weather_code"].max() if "weather_code" in rows else None
    return {
        "icon": weather_type(worst_code)[0],
        "weather": weather_type(worst_code)[1],
        "air_temp_c": temp,
        "dew_point_c": dew,
        "heat_slowdown_pct": float(slowdown_pct(temp, dew)),
        "rain_chance_pct": rows["rain_chance_pct"].max(),
        "us_aqi": None if math.isnan(aqi) else aqi,
        "pm2_5": None if math.isnan(aqi) else rows["pm2_5"].mean(),
        # the most direct source in the window: measured > adjusted > model
        "aqi_source": next((s for s in ("measured", "adjusted", "model")
                            if "aqi_source" in rows and (rows["aqi_source"] == s).any()), ""),
    }


def describe_window(name, c):
    """'run time 19-21: 🌧 27°C, dew 24°C (heat -5%), rain 98%, AQI 205 very unhealthy (model)'"""
    first, last = WINDOWS[name]
    text = (f"{name} {first:02d}-{last:02d}: {c['icon']} {c['air_temp_c']:.0f}°C, dew {c['dew_point_c']:.0f}°C "
            f"(heat -{c['heat_slowdown_pct']:.0f}%), rain {c['rain_chance_pct']:.0f}%")
    if c["us_aqi"] is not None:
        text += f", AQI {c['us_aqi']:.0f} {aqi_label(c['us_aqi'])} ({c['aqi_source']})"
    return text


def air_note(conditions):
    """A short heads-up when the air is poor in every window that has data."""
    aqis = [c["us_aqi"] for c in conditions.values() if c and c["us_aqi"] is not None]
    if not aqis:
        return None
    best = min(aqis)
    if best > 150:
        return "Air forecast unhealthy - consider running indoors (treadmill) or easing off."
    if best > 100:
        return "Air forecast unhealthy for sensitive groups - pick a cleaner time if you can."
    return None


def day_conditions(forecast, day):
    return {name: window_conditions(forecast, day, hours) for name, hours in WINDOWS.items()}
