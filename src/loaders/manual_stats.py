"""A run history built from the stats a new runner enters (see users.STAT_FIELDS).

The analysis and the planner only read a table of runs, so instead of a second
code path the stats become the runs they describe, with the same columns as a
Garmin export:

  the HISTORY_WEEKS Monday-Sunday weeks up to the last Sunday on or before the day
  you entered the stats
  (back to 4 weeks before your race, if it is older), each with
    runs_per_week runs on your usual days (config: LONG_RUN_DAY, OTHER_RUN_DAYS)
    one long run of longest_km, the rest of weekly_km shared by the others
    every run at your easy pace and easy heart rate
  plus your race (marked as a race) with its distance and time.

Every run is titled "from your stats". The data then ends on the last Sunday on
or before the day you entered them; later weeks are planned as if done, until real runs come in.
"""

import pandas as pd

from src.config import LONG_RUN_DAY, OTHER_RUN_DAYS, RUN_HOURS

HISTORY_WEEKS = 4            # as the planner's LOOKBACK_WEEKS
TITLE = "from your stats"
RACE_HR_SHARE = 0.88         # a race's average HR when you only give its time (estimate, shown nowhere as fact)
EMPTY = ["avg_gap_s_per_km", "aerobic_te", "avg_cadence", "ascent_m", "min_temp_c", "max_temp_c", "calories",
         "air_temp_c", "dew_point_c", "heat_score_f", "heat_slowdown_pct", "heat_adj_pace_s"]


def monday(day):
    day = pd.Timestamp(day).normalize()
    return day - pd.Timedelta(days=day.weekday())


def history_end(stats):
    """The Monday after the last week the stats describe (a Sunday entry counts its own week)."""
    return monday(pd.Timestamp(stats["as_of"]) + pd.Timedelta(days=1))


def covered_until(stats):
    """The last day the stats describe: the last Sunday on or before the day they were entered."""
    return (history_end(stats) - pd.Timedelta(days=1)).date()


def week_runs(week_start, stats):
    """One week of runs as (start time, km)."""
    n = max(1, int(stats["runs_per_week"]))
    weekly, longest = float(stats["weekly_km"]), min(float(stats["longest_km"]), float(stats["weekly_km"]))
    if n == 1:
        return [(week_start + pd.Timedelta(days=LONG_RUN_DAY, hours=6), weekly)]
    other_km = max(1.0, round((weekly - longest) / (n - 1), 1))
    days = OTHER_RUN_DAYS[:n - 1]
    return ([(week_start + pd.Timedelta(days=LONG_RUN_DAY, hours=6), longest)]
            + [(week_start + pd.Timedelta(days=d, hours=RUN_HOURS[0]), other_km) for d in days])


def runs_from_stats(stats, max_hr):
    """The runs table the stats describe (see the module docstring)."""
    first = history_end(stats) - pd.Timedelta(weeks=HISTORY_WEEKS)
    race = stats.get("race")
    race_start = pd.Timestamp(race["date"]) + pd.Timedelta(hours=6) if race else None
    if race_start is not None:
        first = min(first, monday(race_start) - pd.Timedelta(weeks=HISTORY_WEEKS))

    rows = []
    week = first
    while week < history_end(stats):
        for start, km in week_runs(week, stats):
            if race_start is not None and start.date() == race_start.date():
                continue   # race day: the race itself is the run
            seconds = km * stats["easy_pace_s"]
            rows.append({"start_time": start, "title": TITLE, "distance_km": km, "duration_s": seconds,
                         "avg_hr": stats["easy_hr"], "garmin_race": False})
        week += pd.Timedelta(weeks=1)
    if race_start is not None:
        rows.append({"start_time": race_start, "title": f"{TITLE}: race", "distance_km": race["distance_km"],
                     "duration_s": race["time_s"], "avg_hr": round(RACE_HR_SHARE * max_hr), "garmin_race": True})

    runs = pd.DataFrame(rows).sort_values("start_time").reset_index(drop=True)
    runs["activity_type"] = "Running"
    runs["moving_time_s"] = runs["duration_s"]
    runs["avg_pace_s_per_km"] = runs["duration_s"] / runs["distance_km"]
    runs["max_hr"] = runs["avg_hr"] + 15
    for column in EMPTY:
        runs[column] = float("nan")
    return runs
