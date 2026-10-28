"""Safety rules every generated week must pass, shown next to the plan.

These are conservative training rules of thumb, not medical advice.
Each check returns a dict with what was tested, whether it passed,
the actual numbers, and the formula, so the plan can explain itself.
"""

import pandas as pd

MAX_WEEKLY_INCREASE = 0.10  # the classic "10% rule"
MAX_LONG_RUN_STEP_KM = 1.5  # longest run grows by at most this much per week
ACWR_SPIKE = 1.3            # acute:chronic load above this = injury-risk zone
MIN_SPIKE_KM = 10           # ignore tiny weeks: 2 km after a break is not a "spike"
RECOVERY_DAYS = 14          # no hard sessions this many days after a half marathon


def result(rule, passed, detail, formula):
    return {"rule": rule, "passed": bool(passed), "detail": detail, "formula": formula}


def check_weekly_increase(planned_km, baseline_km):
    limit = baseline_km * (1 + MAX_WEEKLY_INCREASE)
    return result(
        "Weekly distance up by at most 10%",
        planned_km <= limit + 0.25,  # 0.25 km slack for rounding to 0.5 km
        f"{planned_km:.1f} km planned, limit {limit:.1f} km",
        "limit = average km/week over the last 4 weeks x 1.10",
    )


def check_long_run(long_run_km, longest_recent_km):
    limit = longest_recent_km + MAX_LONG_RUN_STEP_KM
    return result(
        f"Long run at most {MAX_LONG_RUN_STEP_KM} km longer than recent longest",
        long_run_km <= limit,
        f"{long_run_km:.1f} km planned, longest training run in last 4 weeks {longest_recent_km:.1f} km",
        f"limit = longest recent run + {MAX_LONG_RUN_STEP_KM} km (races not counted)",
    )


def check_no_hard_after_race(workouts, days_since_race):
    hard = [w for w in workouts if w.is_hard]
    too_soon = days_since_race is not None and days_since_race < RECOVERY_DAYS
    return result(
        f"No hard sessions within {RECOVERY_DAYS} days of a race",
        not (too_soon and hard),
        f"last race {days_since_race} days before this week, {len(hard)} hard session(s) planned",
        f"hard sessions allowed only when days since race >= {RECOVERY_DAYS}",
    )


def weekly_acwr(runs, until):
    """Acute:chronic workload ratio for each week up to `until`.

    acute   = km in that Monday-Sunday week
    chronic = average km/week over that week and the 3 before it
    ratio   = acute / chronic   (1.0 = same as usual, 1.5 = 50% above usual)
    """
    week = runs["start_time"].dt.to_period("W-SUN")
    weekly_km = runs.groupby(week)["distance_km"].sum()
    all_weeks = pd.period_range(weekly_km.index.min(), pd.Timestamp(until).to_period("W-SUN"), freq="W-SUN")
    weekly_km = weekly_km.reindex(all_weeks, fill_value=0.0)  # weeks with no runs count as 0 km

    chronic = weekly_km.rolling(4, min_periods=4).mean()
    return pd.DataFrame({"km": weekly_km, "chronic_km": chronic, "acwr": weekly_km / chronic})


def check_recent_spikes(runs, plan_start, weeks=6):
    """Flag weeks in the recent past whose load jumped above ACWR_SPIKE."""
    table = weekly_acwr(runs, plan_start - pd.Timedelta(days=1)).tail(weeks)
    spikes = table[(table["acwr"] > ACWR_SPIKE) & (table["km"] >= MIN_SPIKE_KM)]
    detail = ", ".join(f"week of {p.start_time:%d %b}: {r.km:.1f} km vs usual {r.chronic_km:.1f} = {r.acwr:.2f}"
                       for p, r in spikes.iterrows())
    return result(
        f"No load spike (acute:chronic > {ACWR_SPIKE}) in the last {weeks} weeks",
        spikes.empty,
        detail or "none",
        f"acute:chronic = km this week / average km per week over this + previous 3 weeks "
        f"(weeks under {MIN_SPIKE_KM} km ignored)",
    )
