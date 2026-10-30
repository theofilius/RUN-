"""Review of one run against its planned menu (src/analysis/run_review.py)."""

import pandas as pd
from conftest import make_runs

from src.analysis.run_review import review
from src.planner.plan_generator import easy_run, interval_run, rest_day

EFF = 0.75   # m/min per bpm: easy pace ~8:1x at HR 157


def a_run(km=5.0, hr=150, pace_s=520, easy_s=None, when="2026-10-29 19:00"):
    seconds = km * pace_s
    run = {"start_time": pd.Timestamp(when), "title": "Jakarta - Run", "distance_km": km, "duration_s": seconds,
           "moving_time_s": seconds, "avg_pace_s_per_km": pace_s, "avg_hr": hr}
    if easy_s is not None:
        run.update(zone_total_s=seconds, zone_easy_s=easy_s)
    return pd.Series(run)


def test_an_easy_run_that_was_easy(no_races):
    day = easy_run(pd.Timestamp("2026-10-29").date(), 5.0, EFF)
    r = review(a_run(easy_s=0.9 * 5 * 520), day, make_runs(hr=150, pace_s=520))
    assert (r["distance"], r["intensity"]) == ("as planned", "easy")
    assert r["efficiency_verdict"] == "usual"          # same effort as the weeks before


def test_an_easy_run_that_was_too_hard(no_races):
    """Like 29 Oct: 5 km, average 161, 22% of the time at easy heart rate."""
    day = easy_run(pd.Timestamp("2026-10-29").date(), 5.0, EFF)
    r = review(a_run(hr=161, pace_s=479, easy_s=0.22 * 5 * 479), day, make_runs())
    assert r["intensity"] == "too hard"
    assert r["pace_vs_plan"] == "faster"


def test_short_extra_and_hard_runs(no_races):
    runs = make_runs()
    day = easy_run(pd.Timestamp("2026-10-29").date(), 6.0, EFF)
    assert review(a_run(km=4.0), day, runs)["distance"] == "short"
    rest = rest_day(pd.Timestamp("2026-10-29").date(), {})
    assert review(a_run(), rest, runs)["distance"] == "unplanned"
    reps = interval_run(pd.Timestamp("2026-10-29").date(), 6.0, EFF)
    assert review(a_run(hr=172, easy_s=0.1 * 5 * 520), reps, runs)["intensity"] == "hard session"


def test_faster_at_the_same_heart_rate_is_better(no_races):
    day = easy_run(pd.Timestamp("2026-10-29").date(), 5.0, EFF)
    r = review(a_run(hr=150, pace_s=480), day, make_runs(hr=150, pace_s=520))
    assert r["efficiency_verdict"] == "better" and r["efficiency_change"] > 0.03
