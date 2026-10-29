"""Easy-run honesty check: were your easy runs actually easy?

Each run is labelled easy or hard by its average HR (easy = at or below
EASY_HR_MAX). Then, per Monday-Sunday week, we add up moving time to get
the easy share and compare it with the 80/20 target.

A second check compares what you *called* a run with what your heart did:
a run titled "Base" or "recovery" with a high average HR was not easy.
"""

import pandas as pd

from src.analysis.races import race_mask
from src.config import EASY_HR_MAX, TARGET_EASY_PCT

# Words in a run title that mean "this was meant to be easy".
EASY_TITLE_WORDS = ["base", "easy", "recov", "long"]

# Weekly verdicts, checked from the top: (minimum easy %, verdict).
VERDICTS = [
    (TARGET_EASY_PCT - 5, "on target"),
    (50, "too much hard running"),
    (0, "easy runs are not easy"),
]


def easy_seconds(runs):
    """Easy moving time of each run.

    With per-second HR from an activity .fit file (zone_* columns, see
    loaders/fit_activities.py): moving time x share of seconds at or below
    EASY_HR_MAX. Without it: the whole run if its average HR is at or below
    EASY_HR_MAX, otherwise nothing.
    """
    by_average = runs["moving_time_s"].where(runs["avg_hr"] <= EASY_HR_MAX, 0)
    if "zone_easy_s" not in runs:
        return by_average
    share = runs["zone_easy_s"] / runs["zone_total_s"]
    return (runs["moving_time_s"] * share).where(share.notna(), by_average)


def label_runs(runs):
    """Add is_easy (avg HR <= EASY_HR_MAX) and is_race columns."""
    labelled = runs.copy()
    labelled["is_easy"] = labelled["avg_hr"] <= EASY_HR_MAX
    labelled["is_race"] = race_mask(runs)
    return labelled


def verdict(easy_pct):
    """First verdict whose minimum the week reaches."""
    for minimum, text in VERDICTS:
        if easy_pct >= minimum:
            return text


def weekly_check(runs):
    """One row per week that has runs: time, easy %, verdict."""
    labelled = label_runs(runs)
    labelled["easy_time_s"] = easy_seconds(labelled)
    week = labelled["start_time"].dt.to_period("W-SUN")  # weeks run Monday-Sunday

    weekly = labelled.groupby(week).agg(
        runs=("moving_time_s", "size"),
        km=("distance_km", "sum"),
        moving_time_s=("moving_time_s", "sum"),
        easy_time_s=("easy_time_s", "sum"),
        race_week=("is_race", "any"),
    )
    weekly["easy_pct"] = 100 * weekly["easy_time_s"] / weekly["moving_time_s"]
    weekly["verdict"] = weekly["easy_pct"].map(verdict)
    weekly.index.name = "week"
    return weekly


def mislabelled_easy_runs(runs):
    """Runs whose title says easy but whose average HR says hard."""
    labelled = label_runs(runs)
    title = labelled["title"].str.lower()
    meant_easy = title.str.contains("|".join(EASY_TITLE_WORDS), na=False)
    return labelled[meant_easy & ~labelled["is_easy"]]


if __name__ == "__main__":
    # python -m src.analysis.easy_check "data/Running Data may-oct.csv"
    import sys

    from src.loaders.csv_garmin import load_garmin_csv

    runs = load_garmin_csv(sys.argv[1])
    weekly = weekly_check(runs)

    shown = pd.DataFrame({
        "runs": weekly["runs"],
        "km": weekly["km"].round(1),
        "minutes": (weekly["moving_time_s"] / 60).round(0).astype(int),
        "easy %": weekly["easy_pct"].round(0).astype(int),
        "verdict": weekly["verdict"],
        "": weekly["race_week"].map({True: "(race week)", False: ""}),
    })
    shown.index = [f"{p.start_time:%Y-%m-%d}" for p in weekly.index]
    shown.index.name = "week of"
    print(f"EASY vs HARD PER WEEK (target: {TARGET_EASY_PCT}% easy)\n")
    print(shown.to_string())

    total_easy = 100 * weekly["easy_time_s"].sum() / weekly["moving_time_s"].sum()
    on_target = (weekly["verdict"] == "on target").sum()
    print(f"\nOverall: {total_easy:.0f}% easy. Weeks on target: {on_target} of {len(weekly)}.")

    wrong = mislabelled_easy_runs(runs)
    print(f"\nRUNS CALLED EASY THAT WERE NOT ({len(wrong)} found)\n")
    print(wrong[["start_time", "title", "distance_km", "avg_hr"]].to_string(index=False))

    print("\nHOW")
    print(f"  easy run   = average HR <= {EASY_HR_MAX:.0f} bpm (EASY_HR_FRACTION x MAX_HR in config.py)")
    print("  easy %     = moving time of easy runs / total moving time, per Monday-Sunday week")
    print(f"  verdict    = on target >= {TARGET_EASY_PCT - 5}%, too much hard running >= 50%, else easy runs are not easy")
    print(f"  'called easy' = title contains one of {EASY_TITLE_WORDS}")
