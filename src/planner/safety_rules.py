"""Safety rules every generated week is checked against, shown next to the plan.

These are conservative training rules, not medical advice. Each check
returns a dict with a level, the actual numbers, the formula, and the
sources behind it (see src/evidence.py), so the plan can explain itself.

Levels:
  pass    - within the rule
  caution - worth noticing, plan still reasonable
  high    - the rule is broken; reconsider
  info    - the rule cannot be calculated; read the note
"""

import pandas as pd

from src.evidence import describe

MAX_WEEKLY_INCREASE = 0.10  # cautious default; evidence does not show 10% is a threshold
MAX_2WEEK_INCREASE = 0.30   # Nielsen 2014: >30% over 2 weeks linked to more injuries
MAX_RISING_WEEKS = 3        # warn when distance rises this many weeks in a row
MAX_LONG_RUN_STEP_KM = 1.5  # longest run grows by at most this much per week
ACWR_CAUTION = 1.3
ACWR_HIGH = 1.5
MIN_SPIKE_KM = 10           # ignore tiny weeks: 2 km after a break is not a "spike"
RECOVERY_DAYS = 14          # no hard sessions this many days after a half marathon
POST_RACE_REST_DAYS = 3     # Zhou 2026: muscle damage clears in ~72 h with rest, slower if running


def result(rule, level, detail, formula, sources, key=None, values=None):
    """key and values describe the check as data, so the dashboard can word it in any language."""
    return {
        "key": key,
        "values": values or {},
        "rule": rule,
        "level": level,
        "passed": level in ("pass", "info"),
        "detail": detail,
        "formula": formula,
        "sources": describe(sources),
    }


def km_between(runs, start, end):
    """Total km of runs starting in [start, end)."""
    in_range = (runs["start_time"] >= start) & (runs["start_time"] < end)
    return runs.loc[in_range, "distance_km"].sum()


def check_weekly_increase(planned_km, baseline_km):
    limit = baseline_km * (1 + MAX_WEEKLY_INCREASE)
    return result(
        "Weekly distance up by at most 10% (cautious default)",
        "pass" if planned_km <= limit + 0.25 else "caution",  # 0.25 km slack for rounding
        f"{planned_km:.1f} km planned, limit {limit:.1f} km. Stricter than the evidence requires: "
        "a 10%-rule trial did not reduce injuries, and 10-30% was no riskier than <10%.",
        "limit = average km/week over the last 4 weeks x 1.10",
        ["own", "buist2008", "nielsen2014"],
        "weekly 10%", {"planned_km": planned_km, "limit_km": limit},
    )


def check_two_week_increase(planned_km, runs, plan_start, reference_km=None):
    """Nielsen 2014: compare the next 7 days with the 7 days before.

    reference_km: after a step-back week, the week before it is the fair
    comparison - returning to a load you already handled is not a new jump.
    """
    last_7_km = max(km_between(runs, plan_start - pd.Timedelta(days=7), plan_start), reference_km or 0.0)
    rule = "Planned week at most 30% more than the last 7 days"
    formula = ("change = planned km / km in the 7 days before the plan - 1"
               + (" (after a step-back week: the week before it)" if reference_km else ""))
    if last_7_km == 0:
        return result(
            rule, "info",
            "No runs in the last 7 days, so the change cannot be calculated. The research says nothing "
            "about returning after a break - restart with short, easy runs.",
            formula, ["nielsen2014"], "two-week 30%", {"no_recent_runs": True},
        )
    change = planned_km / last_7_km - 1
    return result(
        rule,
        "pass" if change <= MAX_2WEEK_INCREASE else "high",
        f"{planned_km:.1f} km planned vs {last_7_km:.1f} km in the last 7 days ({change:+.0%})",
        formula, ["nielsen2014"],
        "two-week 30%", {"planned_km": planned_km, "last_km": last_7_km, "change": change},
    )


def check_rising_weeks(planned_km, runs, plan_start):
    """Nielsen 2014 discussion: several +25% weeks in a row may still add up."""
    weeks = [km_between(runs, plan_start - pd.Timedelta(weeks=n), plan_start - pd.Timedelta(weeks=n - 1))
             for n in range(MAX_RISING_WEEKS - 1, 0, -1)] + [planned_km]
    rising = all(later > earlier for earlier, later in zip(weeks, weeks[1:]))
    return result(
        f"Distance not rising {MAX_RISING_WEEKS} weeks in a row",
        "caution" if rising else "pass",
        " -> ".join(f"{km:.1f}" for km in weeks) + " km (last weeks -> planned)",
        f"caution if each of the last {MAX_RISING_WEEKS} weeks (incl. planned) is higher than the one before",
        ["nielsen2014"], "rising weeks", {"weeks_km": weeks},
    )


def check_long_run(long_km, longest_recent_km):
    limit = longest_recent_km + MAX_LONG_RUN_STEP_KM
    return result(
        f"Long run at most {MAX_LONG_RUN_STEP_KM} km longer than recent longest",
        "pass" if long_km <= limit else "high",
        f"{long_km:.1f} km planned, longest training run in last 4 weeks {longest_recent_km:.1f} km",
        f"limit = longest recent run + {MAX_LONG_RUN_STEP_KM} km (races not counted)",
        ["own", "fokkema2020"], "long run step", {"long_km": long_km, "longest_km": longest_recent_km},
    )


def check_no_hard_after_race(workouts, days_since_race):
    hard = [w for w in workouts if w.is_hard]
    too_soon = days_since_race is not None and days_since_race < RECOVERY_DAYS
    return result(
        f"No hard sessions within {RECOVERY_DAYS} days of a race",
        "high" if too_soon and hard else "pass",
        f"last race {days_since_race} days before this week, {len(hard)} hard session(s) planned",
        f"hard sessions allowed only when days since race >= {RECOVERY_DAYS}",
        ["own"], "hard after race", {"days_since_race": days_since_race, "hard": len(hard)},
    )


def check_post_race_rest(workouts, last_race):
    """No runs in the first POST_RACE_REST_DAYS days after a race."""
    rule = f"No runs in the first {POST_RACE_REST_DAYS} days after a race"
    formula = f"rest on race day + 1 ... race day + {POST_RACE_REST_DAYS}"
    if last_race is None:
        return result(rule, "pass", "no race before this plan", formula, ["zhou2026", "wang2025"],
                      "post-race rest")
    race_day = last_race.date()
    too_soon = [w for w in workouts if 0 < (w.day - race_day).days <= POST_RACE_REST_DAYS]
    return result(
        rule,
        "high" if too_soon else "pass",
        f"race on {race_day:%a %d %b}; {len(too_soon)} run(s) planned in the {POST_RACE_REST_DAYS} days after",
        formula,
        ["zhou2026", "wang2025"], "post-race rest", {"runs_too_soon": len(too_soon)},
    )


def weekly_acwr(runs, until, planned_km=None):
    """Uncoupled acute:chronic workload ratio per Monday-Sunday week.

    acute   = km in that week
    chronic = average km/week over the 3 weeks BEFORE it (not including it,
              because including it biases the ratio - Windt & Gabbett 2019)
    ratio   = acute / chronic; not available when chronic is 0

    With planned_km, the planned week is added as the last row.
    """
    week = runs["start_time"].dt.to_period("W-SUN")
    weekly_km = runs.groupby(week)["distance_km"].sum()
    all_weeks = pd.period_range(weekly_km.index.min(), pd.Timestamp(until).to_period("W-SUN"), freq="W-SUN")
    weekly_km = weekly_km.reindex(all_weeks, fill_value=0.0)  # weeks with no runs count as 0 km
    if planned_km is not None:
        weekly_km[all_weeks[-1] + 1] = planned_km

    chronic = weekly_km.shift(1).rolling(3, min_periods=3).mean()
    acwr = (weekly_km / chronic).where(chronic > 0)
    return pd.DataFrame({"km": weekly_km, "chronic_km": chronic, "acwr": acwr})


def check_load_spikes(runs, plan_start, planned_km, weeks=6):
    """Judge the planned week's acute:chronic ratio; recent spikes are listed for context.

    Only the planned week sets the level - a spike weeks ago is history, not
    something this plan can still change.
    """
    table = weekly_acwr(runs, plan_start - pd.Timedelta(days=1), planned_km).tail(weeks + 1)
    counted = table[table["km"] >= MIN_SPIKE_KM]
    planned = table.iloc[-1]
    ratio = planned["acwr"] if planned["km"] >= MIN_SPIKE_KM else None

    level = "pass"
    if ratio is not None and ratio >= ACWR_HIGH:
        level = "high"
    elif ratio is not None and ratio >= ACWR_CAUTION:
        level = "caution"

    flagged = counted[counted["acwr"] >= ACWR_CAUTION]
    planned_week = table.index[-1]
    detail = ", ".join(
        f"{'planned week' if p == planned_week else f'week of {p.start_time:%d %b}'}: "
        f"{r.km:.1f} km vs usual {r.chronic_km:.1f} = {r.acwr:.2f}"
        for p, r in flagged.iterrows()
    )
    return result(
        f"Acute:chronic load of the planned week below {ACWR_CAUTION} (caution) / {ACWR_HIGH} (high); "
        f"spikes in the last {weeks} weeks listed",
        level,
        (detail or "none") + ". Weak evidence for runners - treat as a warning sign, not a rule.",
        f"ratio = km this week / average km per week over the 3 weeks before it "
        f"(weeks under {MIN_SPIKE_KM} km ignored)",
        ["cloosterman2024", "windt2019"],
        "load spike", {"ratio": None if ratio is None or pd.isna(ratio) else float(ratio),
                       "usual_km": None if pd.isna(planned["chronic_km"]) else float(planned["chronic_km"])},
    )
