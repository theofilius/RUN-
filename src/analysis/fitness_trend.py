"""Aerobic fitness trend: are you getting faster at the same heart rate?

Garmin's CSV has one row per run (average pace, average HR), so we
measure fitness per run with efficiency = speed / avg HR, then:
  1. express it as an estimated pace at REFERENCE_HR, which is easier to feel,
  2. summarise it per month,
  3. fit a straight line through all runs to get the overall direction.

Races are left out: 3-4 hours of racing fatigue drags efficiency down,
so they are not comparable with normal training runs.
"""

import numpy as np
import pandas as pd

from src.analysis.race_postmortem import efficiency
from src.analysis.races import race_mask
from src.config import REFERENCE_HR
from src.units import format_pace


def training_runs_with_efficiency(runs):
    """Training runs only, with efficiency and estimated pace @ REFERENCE_HR."""
    training = runs[~race_mask(runs)].copy()

    training["efficiency"] = efficiency(training)
    # efficiency = (m/min) / bpm  ->  speed at REFERENCE_HR = efficiency x REFERENCE_HR
    # pace (s/km) = 1000 m / speed (m/min) x 60 s
    training["pace_at_ref_hr_s"] = 1000 / (training["efficiency"] * REFERENCE_HR) * 60
    return training


def monthly_summary(training):
    """Median efficiency and pace @ REFERENCE_HR per calendar month.

    Median instead of mean so one odd run (GPS glitch, HR spike)
    cannot pull the whole month up or down.
    """
    month = training["start_time"].dt.to_period("M")
    summary = training.groupby(month).agg(
        runs=("efficiency", "size"),
        efficiency=("efficiency", "median"),
        pace_at_ref_hr_s=("pace_at_ref_hr_s", "median"),
        median_hr=("avg_hr", "median"),
        heat_slowdown_pct=("heat_slowdown_pct", "mean"),
    )
    summary.index.name = "month"
    return summary


def correlation(x, y):
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.corrcoef(x, y)[0, 1]


def trend_line(training):
    """Straight line efficiency = slope x day + intercept through all runs.

    Returns the fitted value on the first and last day, so the change
    can be read as "from X to Y", plus r: how closely the runs follow
    the line (0 = no pattern, 1 = perfect line).
    """
    days = (training["start_time"] - training["start_time"].min()).dt.days
    slope, intercept = np.polyfit(days, training["efficiency"], 1)
    first, last = intercept, intercept + slope * days.max()
    return {
        "days": int(days.max()),
        "start_efficiency": first,
        "end_efficiency": last,
        "change_pct": 100 * (last - first) / first,
        "start_pace_s": 1000 / (first * REFERENCE_HR) * 60,
        "end_pace_s": 1000 / (last * REFERENCE_HR) * 60,
        # r is undefined (nan) when every run has the same efficiency - no warning needed
        "r": correlation(days, training["efficiency"]),
    }


if __name__ == "__main__":
    # python -m src.analysis.fitness_trend "data/Running Data may-oct.csv"
    import sys

    from src.analysis.heat_adjust import load_runs_with_heat

    training = training_runs_with_efficiency(load_runs_with_heat(sys.argv[1]))

    monthly = monthly_summary(training)
    shown = pd.DataFrame({
        "runs": monthly["runs"],
        "efficiency": monthly["efficiency"].round(3),
        f"pace @ {REFERENCE_HR}": monthly["pace_at_ref_hr_s"].map(format_pace),
        "median HR": monthly["median_hr"].round(0).astype(int),
        "heat slowdown %": monthly["heat_slowdown_pct"].round(1),
    })
    print(f"FITNESS PER MONTH ({len(training)} training runs, races excluded)\n")
    print(shown.to_string())

    trend = trend_line(training)
    print(f"\nTREND OVER {trend['days']} DAYS (straight line through every run)\n")
    print(f"  efficiency     {trend['start_efficiency']:.3f} -> {trend['end_efficiency']:.3f}"
          f"  ({trend['change_pct']:+.1f}%)")
    print(f"  pace @ {REFERENCE_HR} bpm  {format_pace(trend['start_pace_s'])} -> "
          f"{format_pace(trend['end_pace_s'])} /km")
    print(f"  fit (r)        {trend['r']:.2f}  (0 = no pattern, 1 = perfect line)")

    print("\nHOW")
    print("  efficiency  = (distance m / moving minutes) / avg HR")
    print(f"  pace @ {REFERENCE_HR}  = 1000 / (efficiency x {REFERENCE_HR}) minutes per km")
    print("  assumes speed rises in proportion to HR; most reliable near your usual HR")
