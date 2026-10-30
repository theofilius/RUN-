"""Check-ins during a milestone stage: is the training on track for the test?

Every week of stage 1 (once your data covers it, and only when it had hard
sessions to judge) is checked against what the plan asked for. Weekly, as
adjusting the load from training data (twice a week in Nuuttila 2022) left
fewer runners without progress. Sources per check in CHECK_SOURCES:

  runs       done / planned runs                      >= MIN_RUNS_SHARE         (own)
  long runs  every long run done (90% of its distance, see month_plan)          (own)
  hard       every tempo / interval day has a run of  >= HARD_DONE_SHARE of its distance
             (Nielsen 2020: a session counts as done within 10% of its distance; that
             every session is done is our own demand - few runners manage it for long)
  easy       share of the week's time at easy HR      >= EASY_PCT_MIN
             (Muñoz 2014: ~75% below the first threshold; 78% improved 10K most)
  fitness    efficiency (speed per heartbeat) of training runs in the week, against
             the LOOKBACK before it: not more than EFFICIENCY_DROP worse
             (Nuuttila 2022: a 3-4 bpm shift at the same speed is the smallest real change)

All of them -> "on track". Otherwise "behind", and you choose: move the test
POSTPONE_WEEKS later, or keep the date - that choice is ours, no study sets it.
One hot week can make the fitness line look worse.
"""

import pandas as pd

from src.analysis.fitness_trend import training_runs_with_efficiency
from src.config import EASY_HR_MAX

CHECK_WEEKS = 1
POSTPONE_WEEKS = 1
MIN_RUNS_SHARE = 0.8
HARD_DONE_SHARE = 0.9       # Nielsen 2020: within 10% of the planned distance
EASY_PCT_MIN = 75           # Muñoz 2014: the polarized model's share below the first threshold
EFFICIENCY_DROP = 0.03
LOOKBACK = pd.Timedelta(weeks=4)
CHECK_SOURCES = {"runs": ["own"], "long": ["own"], "hard": ["nielsen2020", "own"],
                 "easy": ["munoz2014"], "fitness": ["nuuttila2022ind"]}


def hard_sessions(weeks, runs):
    """(planned, done) tempo / interval days in weeks."""
    planned = [w for week in weeks for w in week["plan"]["workouts"] if w.is_hard]
    done = 0
    for w in planned:
        that_day = runs[runs["start_time"].dt.date == w.day]
        done += that_day["distance_km"].sum() >= HARD_DONE_SHARE * w.distance_km
    return len(planned), done


def median_efficiency(runs, start, end):
    """Median efficiency of training runs (races left out) between start and end, or None."""
    window = runs[(runs["start_time"] >= start) & (runs["start_time"] < end)]
    median = training_runs_with_efficiency(window)["efficiency"].median() if len(window) else None
    return None if median is None or pd.isna(median) else median


def evaluate(weeks, runs):
    """The check for a block of finished weeks (each with its "evaluation")."""
    evaluations = [w["evaluation"] for w in weeks]
    start, end = weeks[0]["start"], weeks[-1]["end"] + pd.Timedelta(days=1)
    planned_runs = sum(e["planned_runs"] for e in evaluations)
    actual_runs = sum(e["actual_runs"] for e in evaluations)
    hard_planned, hard_done = hard_sessions(weeks, runs)
    easy = [e["easy_pct"] for e in evaluations if e["easy_pct"] is not None]
    easy_pct = sum(easy) / len(easy) if easy else None
    now = median_efficiency(runs, start, end)
    before = median_efficiency(runs, start - LOOKBACK, start)
    change = now / before - 1 if now and before else None

    checks = {
        "runs": actual_runs >= MIN_RUNS_SHARE * planned_runs,
        "long": all(e["long_done"] for e in evaluations),
        "hard": hard_done >= hard_planned,
        "easy": easy_pct is None or easy_pct >= EASY_PCT_MIN,
        "fitness": change is None or change >= -EFFICIENCY_DROP,
    }
    return {
        "start": start.date(), "end": weeks[-1]["end"].date(),
        "planned_runs": planned_runs, "actual_runs": actual_runs,
        "long_planned": sum(e["planned_long_km"] > 0 for e in evaluations),
        "long_done": sum(e["long_done"] and e["planned_long_km"] > 0 for e in evaluations),
        "hard_planned": hard_planned, "hard_done": hard_done,
        "easy_pct": easy_pct,
        "efficiency_change": change,
        # easy pace at the easy HR limit: what the change means on your easy runs
        "easy_pace_before_s": 1000 / (before * EASY_HR_MAX) * 60 if before else None,
        "easy_pace_now_s": 1000 / (now * EASY_HR_MAX) * 60 if now else None,
        "checks": checks,
        "on_track": all(checks.values()),
    }


def latest(weeks, runs, test_week):
    """The newest check-in of stage 1, or None.

    weeks: stage 1's weeks (numbered from 1); test_week: the number of the test week.
    A check-in closes every CHECK_WEEKS weeks before the test week, once all its
    weeks are done; a block with no hard session planned (recovery) is skipped.
    """
    for end in range(test_week - 1, 0, -1):
        if end % CHECK_WEEKS:
            continue
        block = [w for w in weeks if end - CHECK_WEEKS < w["number"] <= end]
        if len(block) < CHECK_WEEKS or any(w["status"] != "done" or not w["evaluation"] for w in block):
            continue
        if not any(x.is_hard for w in block for x in w["plan"]["workouts"]):
            continue
        return evaluate(block, runs)
    return None
