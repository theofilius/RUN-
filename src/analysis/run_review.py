"""Review of one run: what you ran against what the plan asked for.

Everything here is numbers and short verdicts; the dashboard words them.

  distance   = run km / planned km: "short" under 90%, "long" over 115%, else "as planned"
  intensity  (easy and long runs) = share of moving time at heart rate <= EASY_HR_MAX
               (per second from the activity .fit file, else the run's average HR):
               "easy" at 80% or more, "mostly easy" 50-80%, "too hard" under 50%
             (tempo and intervals are meant to be hard: "hard session")
  pace       = average pace against the planned range of the main step:
               "faster", "within" or "slower"
  efficiency = speed / average HR, against the median of your training runs in
               the 4 weeks before (higher = more speed for the same effort);
               "better" or "worse" beyond +-3%, else "usual". Heat changes it
               too, so the heat slowdown is reported next to it. The same idea
               as the heart rate-running speed index (Nuuttila 2022), where a
               3-4 bpm shift at the same speed was the smallest real change.
"""

import pandas as pd

from src.analysis.race_postmortem import efficiency
from src.analysis.races import race_mask
from src.config import EASY_HR_MAX

SHORT, LONG = 0.90, 1.15
EASY_SHARE_OK, EASY_SHARE_MOSTLY = 0.80, 0.50
EFFICIENCY_BAND = 0.03
LOOKBACK = pd.Timedelta(weeks=4)


def easy_share(run):
    """Share of moving time at easy heart rate (None without heart rate)."""
    if pd.notna(run.get("zone_total_s")) and run.get("zone_total_s"):
        return run["zone_easy_s"] / run["zone_total_s"]
    if pd.isna(run.get("avg_hr")):
        return None
    return 1.0 if run["avg_hr"] <= EASY_HR_MAX else 0.0


def recent_efficiency(runs, before):
    """Median efficiency of training runs (races left out) in the LOOKBACK before `before`."""
    window = runs[(runs["start_time"] < before) & (runs["start_time"] >= before - LOOKBACK)]
    window = window[~race_mask(window)]
    return efficiency(window).median() if len(window) else None


def review(run, day, runs):
    """Planned vs actual for one run. `day` is the planned Workout (or None); `runs` all runs."""
    result = {"km": run["distance_km"], "kind": day.kind if day is not None else None}
    planned = day is not None and day.kind not in ("rest", "race")
    if planned:
        ratio = run["distance_km"] / day.distance_km if day.distance_km else None
        result.update(planned_km=day.distance_km, distance_ratio=ratio,
                      distance=None if ratio is None else "short" if ratio < SHORT else "long" if ratio > LONG
                      else "as planned")
    else:
        result.update(planned_km=None, distance_ratio=None, distance="unplanned" if day is not None else None)

    share = easy_share(run)
    result["easy_share"] = share
    if planned and day.kind in ("tempo", "interval"):
        result["intensity"] = "hard session"
    elif share is None:
        result["intensity"] = None
    else:
        result["intensity"] = "easy" if share >= EASY_SHARE_OK else "mostly easy" if share >= EASY_SHARE_MOSTLY \
            else "too hard"
    result["hr_limit"] = EASY_HR_MAX

    main = None
    if planned:
        main = next((s for s in day.steps if s.name in ("easy", "tempo", "interval")), None)
    if main is not None and pd.notna(run.get("avg_pace_s_per_km")) and day.kind not in ("tempo", "interval"):
        pace = run["avg_pace_s_per_km"]
        result["pace_vs_plan"] = "faster" if pace < main.pace_fast_s else "slower" if pace > main.pace_slow_s \
            else "within"
        result["plan_pace"] = (main.pace_fast_s, main.pace_slow_s)
    else:
        result["pace_vs_plan"], result["plan_pace"] = None, None

    own = efficiency(pd.DataFrame([run])).iloc[0] if pd.notna(run.get("avg_hr")) else None
    base = recent_efficiency(runs, run["start_time"])
    change = own / base - 1 if own and base else None
    result.update(efficiency=own, efficiency_base=base, efficiency_change=change,
                  efficiency_verdict=None if change is None else "better" if change > EFFICIENCY_BAND
                  else "worse" if change < -EFFICIENCY_BAND else "usual")
    return result
