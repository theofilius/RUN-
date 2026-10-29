"""Load a Garmin Connect activity-list CSV export into a clean table.

Garmin writes every value as text: "1,548" for numbers, "9:03" for pace,
"03:14:13" for time, "--" when missing. This module turns those into real
numbers (seconds, km, bpm) so the analysis code never has to parse text.

The analysis code only depends on the column names produced here, so a
Strava or API loader can later produce the same columns and plug straight in.
"""

from pathlib import Path

import pandas as pd

# Garmin column name -> our column name. Columns not listed here are dropped.
COLUMNS = {
    "Date": "start_time",
    "Activity Type": "activity_type",
    "Title": "title",
    "Distance": "distance_km",
    "Time": "duration_s",
    "Moving Time": "moving_time_s",
    "Avg Pace": "avg_pace_s_per_km",
    "Avg GAP": "avg_gap_s_per_km",  # grade-adjusted pace (corrected for hills)
    "Avg HR": "avg_hr",
    "Max HR": "max_hr",
    "Aerobic TE": "aerobic_te",
    "Avg Run Cadence": "avg_cadence",
    "Total Ascent": "ascent_m",
    "Min Temp": "min_temp_c",
    "Max Temp": "max_temp_c",
    "Calories": "calories",
}

# Columns stored as "h:mm:ss" or "m:ss" text that we convert to seconds.
TIME_COLUMNS = ["duration_s", "moving_time_s", "avg_pace_s_per_km", "avg_gap_s_per_km"]

# Plain number columns that may contain thousands separators like "1,548".
NUMBER_COLUMNS = [
    "distance_km", "avg_hr", "max_hr", "aerobic_te", "avg_cadence",
    "ascent_m", "min_temp_c", "max_temp_c", "calories",
]

MISSING = {"--", ""}

# Shorter recordings are watch tests or false starts, not runs.
MIN_DISTANCE_KM = 1.0


def time_to_seconds(text):
    """Convert "03:14:13" or "9:03" to seconds. Returns None if missing.

    Works for both formats by reading left to right:
    each new part means "previous total x 60, plus this part".
    """
    if pd.isna(text) or str(text).strip() in MISSING:
        return None
    total = 0.0
    for part in str(text).split(":"):
        total = total * 60 + float(part)
    return total


def to_number(text):
    """Convert "1,548" to 1548.0. Returns None if missing."""
    if pd.isna(text) or str(text).strip() in MISSING:
        return None
    return float(str(text).replace(",", ""))


def load_garmin_csv(path):
    """Read the Garmin export and return one row per run, oldest first."""
    # dtype=str: keep everything as text first, then convert on purpose below.
    raw = pd.read_csv(Path(path), dtype=str, encoding="utf-8-sig")

    df = raw[list(COLUMNS)].rename(columns=COLUMNS)

    df["start_time"] = pd.to_datetime(df["start_time"])
    for col in TIME_COLUMNS:
        df[col] = df[col].map(time_to_seconds).astype(float)
    for col in NUMBER_COLUMNS:
        df[col] = df[col].map(to_number).astype(float)

    # Keep running only ("Running", "Treadmill Running", "Trail Running", ...).
    df = df[df["activity_type"].str.contains("Running", na=False)]
    df = df[df["distance_km"] >= MIN_DISTANCE_KM]

    return df.sort_values("start_time").reset_index(drop=True)


if __name__ == "__main__":
    # Quick check: python -m src.loaders.csv_garmin "data/Running Data may-oct.csv"
    import sys

    runs = load_garmin_csv(sys.argv[1])
    print(f"{len(runs)} runs, {runs['start_time'].min():%Y-%m-%d} to {runs['start_time'].max():%Y-%m-%d}")
    print(runs.dtypes.to_string())
    print(runs[["start_time", "title", "distance_km", "duration_s", "avg_pace_s_per_km", "avg_hr"]].tail().to_string())
