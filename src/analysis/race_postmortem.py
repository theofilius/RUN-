"""Race post-mortem: what changed between the training before two races?

For each race we take the N weeks before the start gun (the "block"),
summarise that block with a few simple numbers, and put the two blocks
side by side. Every metric carries a plain-language formula so the
report can show how each number was produced.
"""

import pandas as pd

from src.analysis.easy_check import easy_seconds
from src.analysis.races import race_list
from src.config import COMPARE_WEEKS, EASY_HR_MAX
from src.units import format_duration, format_pace


def training_block(runs, race_start, weeks):
    """Runs in the `weeks` weeks before race_start (the race itself excluded)."""
    block_start = race_start - pd.Timedelta(weeks=weeks)
    in_block = (runs["start_time"] >= block_start) & (runs["start_time"] < race_start)
    return runs[in_block]


def efficiency(runs):
    """Metres per minute for each beat per minute: speed / avg HR.

    Higher means you move faster for the same heart rate, a common
    sign of better aerobic fitness (often called "efficiency factor").
    """
    speed_m_per_min = runs["distance_km"] * 1000 / (runs["moving_time_s"] / 60)
    return speed_m_per_min / runs["avg_hr"]


def summarize_block(block, race_start, weeks):
    """Reduce a training block to the numbers in METRICS."""
    # 0 = the week right before the race, 1 = the week before that, ...
    weeks_before_race = (race_start - block["start_time"]).dt.days // 7
    total_time = block["moving_time_s"].sum()
    easy_time = easy_seconds(block).sum()

    return {
        "runs_per_week": len(block) / weeks,
        "km_per_week": block["distance_km"].sum() / weeks,
        "longest_run_km": block["distance_km"].max(),
        "weeks_with_runs": weeks_before_race.nunique(),
        "avg_hr": (block["avg_hr"] * block["moving_time_s"]).sum() / total_time,
        "easy_time_pct": 100 * easy_time / total_time,
        "efficiency": efficiency(block).median(),
        "heat_slowdown_pct": block["heat_slowdown_pct"].mean(),
    }


# key -> (label, how to display the value, how it is calculated)
METRICS = {
    "runs_per_week": ("Runs per week", "{:.1f}", "number of runs / weeks in block"),
    "km_per_week": ("Distance per week (km)", "{:.1f}", "sum of distance / weeks in block"),
    "longest_run_km": ("Longest run (km)", "{:.1f}", "max distance of any single run"),
    "weeks_with_runs": ("Weeks with at least 1 run", "{:.0f}", "count of 7-day periods (counted back from race) with a run"),
    "avg_hr": ("Average HR (bpm)", "{:.0f}", "each run's avg HR weighted by its moving time"),
    "easy_time_pct": ("Easy time (%)", "{:.0f}", f"moving time at HR <= {EASY_HR_MAX:.0f} bpm / total moving time "
                      "(per second where a .fit file exists, else by each run's average HR)"),
    "efficiency": ("Efficiency (m/min per bpm)", "{:.2f}", "median of (distance m / moving minutes) / avg HR; higher = fitter"),
    "heat_slowdown_pct": ("Heat slowdown (%)", "{:.1f}", "mean slowdown from air temp + dew point (heat_adjust.py)"),
}


def race_result(runs, race_start):
    """The race activity itself, matched by its exact start time."""
    match = runs[runs["start_time"] == race_start]
    if match.empty:
        raise ValueError(f"No run starts at {race_start}; check the race in RACES in config.py")
    return match.iloc[0]


def compare_races(runs, race_a, race_b, weeks=COMPARE_WEEKS):
    """Build the post-mortem table for two race names from race_list(runs).

    Returns a DataFrame with one row per metric: value before race A,
    value before race B, the change, and the formula behind it.
    """
    rows = []
    summaries = {}
    races = race_list(runs)
    for name in (race_a, race_b):
        start = pd.Timestamp(races[name]["start"])
        summaries[name] = summarize_block(training_block(runs, start, weeks), start, weeks)

    for key, (label, fmt, formula) in METRICS.items():
        a, b = summaries[race_a][key], summaries[race_b][key]
        rows.append({
            "metric": label,
            race_a: fmt.format(a),
            race_b: fmt.format(b),
            "change": f"{b - a:+.2f}" if key == "efficiency" else f"{b - a:+.1f}",
            "how": formula,
        })
    return pd.DataFrame(rows)


def race_rows(runs, race_a, race_b):
    """Side-by-side race results: time, pace, HR, efficiency."""
    rows = []
    races = race_list(runs)
    for name in (race_a, race_b):
        race = race_result(runs, pd.Timestamp(races[name]["start"]))
        rows.append({
            "race": name,
            "date": f"{race['start_time']:%Y-%m-%d}",
            "distance_km": race["distance_km"],
            "time": format_duration(race["duration_s"]),
            "pace": format_pace(race["avg_pace_s_per_km"]),
            "avg_hr": int(race["avg_hr"]),
            "efficiency": round(efficiency(race), 2),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    # python -m src.analysis.race_postmortem "data/Running Data may-oct.csv"
    import sys

    from src.analysis.heat_adjust import load_runs_with_heat

    runs = load_runs_with_heat(sys.argv[1])
    race_a, race_b = list(race_list(runs))[-2:]   # the last two races

    pd.set_option("display.width", 200, "display.max_colwidth", 80)
    print("RACES\n")
    print(race_rows(runs, race_a, race_b).to_string(index=False))
    print(f"\nTRAINING IN THE {COMPARE_WEEKS} WEEKS BEFORE EACH RACE\n")
    print(compare_races(runs, race_a, race_b).to_string(index=False))
