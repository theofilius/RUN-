"""Backward goal planner: how far is your target from your current fitness?

A rough, fully explained estimate - not a race prediction you should bet on:
  1. Start from your most recent race (time T0, distance D0).
  2. Convert it to the goal distance with Riegel:    T = T0 x (D / D0) ^ 1.06
  3. Adjust for fitness gained since that race:      T_now = T x (E_race / E_now)
     E = efficiency (speed / HR) of your training runs - faster at the same HR
     means faster at the same effort, so race time scales with 1 / E.
  4. Project forward at your own recent gain g per week:  T(w) = T_now / (1 + g) ^ w
  5. From the target time:
       weeks needed      = ln(T_now / target) / ln(1 + g)
       gain needed/week  = (T_now / target) ^ (1 / weeks to race) - 1

Assumes race-day conditions (heat, pacing, fuelling) like your last race.
"""

import math

import pandas as pd

from src.analysis.fitness_trend import training_runs_with_efficiency
from src.analysis.races import race_mask
from src.units import format_duration

RIEGEL_EXPONENT = 1.06
LOOKBACK = pd.Timedelta(weeks=4)
REALISTIC_GAIN = 0.01   # more than ~1% a week, sustained, is unlikely

# Steps between "sub" targets in the dropdown, in minutes, per race distance (km).
TARGET_STEP_MIN = {5.0: 2, 10.0: 5, 21.1: 10, 42.2: 15}


# Peak weekly distance for a half-marathon target: (target time "h:mm", peak km/week).
# A planner heuristic, anchored on Fokkema 2020 (over 32 km/week went with faster
# halves in recreational runners); straight lines between rows, flat beyond the ends.
HALF_PEAK_KM = [("3:20", 26), ("3:10", 29), ("3:00", 33), ("2:50", 38), ("2:40", 44),
                ("2:30", 50), ("2:20", 56), ("2:10", 62), ("2:00", 68)]
# Other distances: their target is first converted to a half-marathon time (Riegel),
# then the half's peak is scaled by this factor.
PEAK_SCALE = {5.0: 0.6, 10.0: 0.75, 21.1: 1.0, 42.2: 1.15}


def peak_km(distance_km, target_s):
    """Weekly distance the plan builds up to for this target (km)."""
    half_equivalent = target_s * (21.1 / distance_km) ** RIEGEL_EXPONENT
    table = sorted((parse_time(t + ":00"), km) for t, km in HALF_PEAK_KM)   # fastest first
    times, kms = zip(*table)
    if half_equivalent <= times[0]:
        km = kms[0]
    elif half_equivalent >= times[-1]:
        km = kms[-1]
    else:
        i = next(i for i in range(1, len(times)) if half_equivalent <= times[i])
        share = (half_equivalent - times[i - 1]) / (times[i] - times[i - 1])
        km = kms[i - 1] + share * (kms[i] - kms[i - 1])
    scale = PEAK_SCALE[min(PEAK_SCALE, key=lambda d: abs(d - distance_km))]
    return round(km * scale)


def weeks_needed(estimate_s, target_s, weekly_gain):
    """Weeks at weekly_gain to go from estimate_s to target_s (0 if already there, None if flat)."""
    if estimate_s <= target_s:
        return 0.0
    if weekly_gain <= 0:
        return None
    return math.log(estimate_s / target_s) / math.log(1 + weekly_gain)


def target_options(estimate_s, distance_km, weekly_gain, count=8):
    """'Sub' targets from just above today's estimate downwards: [(target_s, weeks_needed), ...]."""
    step = 60 * TARGET_STEP_MIN[min(TARGET_STEP_MIN, key=lambda d: abs(d - distance_km))]
    first = math.ceil(estimate_s / step) * step
    targets = [first - i * step for i in range(count) if first - i * step > 0]
    return [(t, weeks_needed(estimate_s, t, weekly_gain)) for t in targets]


def parse_time(text):
    """'2:50:00' or '50:00' -> seconds."""
    seconds = 0
    for part in str(text).split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def efficiency_before(runs, when):
    """Median efficiency of training runs in the 4 weeks before `when`."""
    window = runs[(runs["start_time"] < when) & (runs["start_time"] >= when - LOOKBACK)]
    return training_runs_with_efficiency(window)["efficiency"].median()


def goal_gap(runs, goal, weekly_gain, today):
    """All numbers for the goal planner, or None without a past race."""
    race_runs = runs[race_mask(runs)]
    if race_runs.empty:
        return None
    last = race_runs.sort_values("start_time").iloc[-1]

    goal_km = goal["distance_km"]
    riegel = last["duration_s"] * (goal_km / last["distance_km"]) ** RIEGEL_EXPONENT
    e_race = efficiency_before(runs, last["start_time"])
    e_now = efficiency_before(runs, pd.Timestamp(today) + pd.Timedelta(days=1))
    now_s = riegel * (e_race / e_now) if e_race and e_now else riegel

    target_s = parse_time(goal["target_time"]) if goal.get("target_time") else now_s
    gap_s = now_s - target_s
    needed_ratio = now_s / target_s

    result = {
        "last_race": last,
        "riegel_s": riegel,
        "efficiency_race": e_race,
        "efficiency_now": e_now,
        "estimate_now_s": now_s,
        "target_s": target_s,
        "gap_s": gap_s,
        "weekly_gain": weekly_gain,
        "weeks_needed": weeks_needed(now_s, target_s, weekly_gain),
        "race_date": None,
    }
    if goal.get("date"):
        race_date = pd.Timestamp(goal["date"])
        weeks_to_race = max(0.0, (race_date - pd.Timestamp(today)).days / 7)
        result.update({
            "race_date": race_date,
            "weeks_to_race": weeks_to_race,
            "estimate_race_s": now_s / (1 + weekly_gain) ** weeks_to_race,
            "gain_needed": (needed_ratio ** (1 / weeks_to_race) - 1) if weeks_to_race > 0 and needed_ratio > 1 else 0.0,
        })
    return result


def describe_gap(g, goal):
    """Plain-language summary lines."""
    lines = [
        f"Last race: {format_duration(g['last_race']['duration_s'])} for {g['last_race']['distance_km']:g} km "
        f"on {g['last_race']['start_time']:%d %b %Y}.",
        f"Estimate today for {goal['distance_km']:g} km: {format_duration(g['estimate_now_s'])} "
        f"(target {goal['target_time']}, gap {format_duration(abs(g['gap_s']))} "
        f"{'to go' if g['gap_s'] > 0 else 'ahead'}).",
    ]
    if g["gap_s"] <= 0:
        lines.append("You are already at or under the target on current fitness.")
    elif g["weeks_needed"] is None:
        lines.append("Your fitness trend is flat, so the time needed cannot be estimated yet.")
    else:
        lines.append(f"At your recent fitness gain of {100 * g['weekly_gain']:.1f}%/week: about "
                     f"{g['weeks_needed']:.0f} weeks of consistent training.")
    if g["race_date"] is not None:
        lines.append(
            f"By {g['race_date']:%d %b %Y} ({g['weeks_to_race']:.0f} weeks): estimate "
            f"{format_duration(g['estimate_race_s'])}. To hit the target you would need "
            f"{100 * g['gain_needed']:.1f}%/week"
            + (" - realistic." if g["gain_needed"] <= REALISTIC_GAIN else
               " - more than ~1%/week is unlikely; consider a later race or a softer target.")
        )
    else:
        lines.append("Set GOAL_RACE['date'] in config.py to check the target against a race date and add a taper.")
    return lines
