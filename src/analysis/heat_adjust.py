"""Heat-adjusted pace: what would this run have been in cool weather?

Rule of thumb used by many runners and coaches: add air temperature
and dew point, both in Fahrenheit, and look up how much heat and
humidity slow you down. Dew point stands in for humidity: the higher it
is, the less sweat can evaporate to cool you.

    temp F + dew point F   expected slowdown
           100                   0%
           130                   2%
           160                   6%
           180                  10%   (above this, hard running is not advised)

Between the listed points we interpolate in a straight line.

    heat-adjusted pace = actual pace / (1 + slowdown %)

so a 9:00/km run with a 5% slowdown counts as about 8:34/km in cool weather.
It is an estimate, not a law: use it to compare runs, not as a promise.
Slower runners likely lose more than the table says: in Hodgson et al. 2022
(Great North Run) the slowest finishers lost the most time per extra degree C.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src.loaders.csv_garmin import load_garmin_csv
from src.loaders.fit_activities import ACTIVITY_DIR, add_time_in_zones
from src.loaders.garmin_api import load_api_runs
from src.loaders.weather_openmeteo import city_for_title, load_weather

# (temp F + dew point F, slowdown %) - the full lookup table.
SLOWDOWN_TABLE = [
    (100, 0.0), (110, 0.5), (120, 1.0), (130, 2.0), (140, 3.0),
    (150, 4.5), (160, 6.0), (170, 8.0), (180, 10.0),
]


def c_to_f(celsius):
    return celsius * 9 / 5 + 32


def slowdown_pct(air_temp_c, dew_point_c):
    """Expected % slowdown for the given air temperature and dew point."""
    heat_score = c_to_f(air_temp_c) + c_to_f(dew_point_c)
    scores, slowdowns = zip(*SLOWDOWN_TABLE)
    # np.interp: straight line between table points, flat beyond both ends.
    return np.interp(heat_score, scores, slowdowns)


def weather_during_run(run, weather):
    """Average air temperature and dew point over the hours the run lasted."""
    city_weather = weather[weather["city"] == city_for_title(run["title"])]
    first_hour = run["start_time"].floor("h")
    last_hour = (run["start_time"] + pd.Timedelta(seconds=run["duration_s"])).floor("h")
    hours = city_weather[(city_weather["time"] >= first_hour) & (city_weather["time"] <= last_hour)]
    return hours["air_temp_c"].mean(), hours["dew_point_c"].mean()


def add_heat_adjustment(runs, weather):
    """Add air temp, dew point, heat score, slowdown % and heat-adjusted pace."""
    adjusted = runs.copy()
    conditions = adjusted.apply(lambda run: weather_during_run(run, weather), axis=1)
    adjusted["air_temp_c"] = [temp for temp, _ in conditions]
    adjusted["dew_point_c"] = [dew for _, dew in conditions]
    adjusted["heat_score_f"] = c_to_f(adjusted["air_temp_c"]) + c_to_f(adjusted["dew_point_c"])
    adjusted["heat_slowdown_pct"] = slowdown_pct(adjusted["air_temp_c"], adjusted["dew_point_c"])
    adjusted["heat_adj_pace_s"] = adjusted["avg_pace_s_per_km"] / (1 + adjusted["heat_slowdown_pct"] / 100)
    return adjusted


def add_conditions(runs, data_dir):
    """Weather and heat columns (weather cached in data_dir), plus time-in-zone
    columns for runs with an activity .fit in data_dir/activities/."""
    data_dir = Path(data_dir)
    weather = load_weather(runs, data_dir / "weather_cache.csv")
    return add_time_in_zones(add_heat_adjustment(runs, weather), data_dir / ACTIVITY_DIR)


def load_runs_with_heat(csv_path):
    """Garmin CSV runs plus weather, heat and (if available) time-in-zone columns."""
    csv_path = Path(csv_path)
    return add_conditions(load_garmin_csv(csv_path), csv_path.parent)


def load_api_runs_with_heat(data_dir):
    """The same, for runs from the last Garmin API sync (see loaders/garmin_api.py)."""
    return add_conditions(load_api_runs(data_dir), data_dir)


if __name__ == "__main__":
    # python -m src.analysis.heat_adjust "data/Running Data may-oct.csv"
    import sys

    from src.analysis.races import race_list
    from src.units import format_pace

    adjusted = load_runs_with_heat(sys.argv[1])

    shown = pd.DataFrame({
        "date": adjusted["start_time"].dt.strftime("%Y-%m-%d %H:%M"),
        "city": adjusted["title"].map(city_for_title),
        "km": adjusted["distance_km"],
        "watch C": adjusted["max_temp_c"],
        "air C": adjusted["air_temp_c"].round(1),
        "dew C": adjusted["dew_point_c"].round(1),
        "score F": adjusted["heat_score_f"].round(0).astype(int),
        "slow %": adjusted["heat_slowdown_pct"].round(1),
        "pace": adjusted["avg_pace_s_per_km"].map(format_pace),
        "heat-adj": adjusted["heat_adj_pace_s"].map(format_pace),
    })
    print("HEAT-ADJUSTED PACE PER RUN\n")
    print(shown.to_string(index=False))

    print("\nRACES")
    for name, info in race_list(adjusted).items():
        race = adjusted[adjusted["start_time"] == pd.Timestamp(info["start"])].iloc[0]
        print(f"  {name:<28} {format_pace(race['avg_pace_s_per_km'])}/km actual, "
              f"{format_pace(race['heat_adj_pace_s'])}/km heat-adjusted "
              f"(air {race['air_temp_c']:.1f} C, dew point {race['dew_point_c']:.1f} C, "
              f"-{race['heat_slowdown_pct']:.1f}%)")

    print("\nHOW")
    print("  weather     = Open-Meteo hourly air temp and dew point for the run's city,")
    print("                averaged over the hours the run lasted")
    print("  heat score  = air temp F + dew point F")
    print(f"  slowdown %  = straight line between {SLOWDOWN_TABLE}")
    print("  heat-adj    = pace / (1 + slowdown % / 100)")
    print("  note        = slower runners likely lose more than this (Hodgson et al. 2022)")
