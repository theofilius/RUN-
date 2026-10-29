"""Running Training Analyzer dashboard.

Run from the project folder:
    streamlit run app/dashboard.py

This file only draws. Every number comes from src/analysis, so the
dashboard and the command-line reports always agree.
"""

import base64
import sys
from html import escape
from pathlib import Path

# Streamlit runs this file directly, so tell Python where the project root is
# (one folder up) so that "from src..." imports work.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analysis.easy_check import mislabelled_easy_runs, weekly_check
from src.analysis.fitness_trend import monthly_summary, training_runs_with_efficiency, trend_line
from src.analysis.heat_adjust import SLOWDOWN_TABLE, load_api_runs_with_heat, load_runs_with_heat
from src.analysis.race_postmortem import compare_races, race_rows
from src.analysis.races import race_list
from src.analysis.run_conditions import (
    WINDOWS, air_note, aqi_label, combine_air, day_conditions, describe_window, next_hours, window_conditions,
)
from src.config import (
    COMPARE_WEEKS, EASY_HR_MAX, HOME_CITY, MAX_HR, REFERENCE_HR, RUN_HOURS,
    START_RUNS_PER_WEEK, STEP_BACK_EVERY, TARGET_EASY_PCT, WEEKLY_GROWTH,
)
from src.planner.plan_generator import MIN_RUN_KM
from src.loaders.forecast_openmeteo import fetched_at, load_forecast
from src.loaders.garmin_api import KEY_WARN_DAYS, SYNC_HOURS, KeyRejected, api_key, key_days_left, sync, synced_at
from src.loaders.iqair import load_current
from src.export.fit_workout import file_name, workout_fit_bytes
from src.analysis.goal_planner import (
    REALISTIC_GAIN, RIEGEL_EXPONENT, describe_gap, goal_gap, parse_time, peak_km, target_options,
)
from src.goal_settings import DISTANCES, distance_name, load_goal, save_goal
from src.evidence import describe
from src.planner.month_plan import (
    build_month_plan, covered_until, covered_until_from_file, current_week, describe_evaluation, weekly_fitness_gain,
)
from src.units import format_duration, format_pace

# Palette: paper, red, black - plus tints of them for quiet chrome.
# Black and red as chart series were checked for colour-blind separation on PAPER.
PAPER = "#EEEBE3"
RED = "#f01e2c"          # accent: hard running, warnings, the line that matters
INK = "#000000"          # text and the main series
MUTED = "#6B6862"        # secondary text (black mixed into paper)
GRID = "#D6D1C4"         # hairlines

DATA_DIR = ROOT / "data"
ASSETS = Path(__file__).resolve().parent / "assets"


# ---------- data ----------

@st.cache_data
def load(csv_path):
    """Load once and keep in memory; Streamlit re-runs this file on every click."""
    return load_runs_with_heat(csv_path)


@st.cache_data(show_spinner="Reading your runs (new activity .fit files take a few seconds each)...")
def load_api(synced):
    """Runs from the last Garmin sync; `synced` (the sync time) makes a new sync reload."""
    return load_api_runs_with_heat(DATA_DIR)


def sync_garmin():
    """Pull new activities from Garmin Connect, with a progress bar for the .fit files."""
    bar = st.progress(0.0, text="Syncing with Garmin Connect...")
    try:
        summary = sync(DATA_DIR, ROOT, progress=lambda done, total: bar.progress(
            done / total, text=f"Downloading activity files {done}/{total}"))
    except KeyRejected as error:
        bar.empty()
        note(f"{escape(str(error))} Showing the last synced data.", accent=True)
        return
    except Exception as error:   # offline, Garmin down: keep the last sync
        bar.empty()
        note(f"Garmin sync failed ({escape(str(error))}). Showing the last synced data.", accent=True)
        return
    bar.empty()
    if summary["new"]:
        st.toast(f"{summary['new']} new activit{'y' if summary['new'] == 1 else 'ies'} from Garmin")


FORECAST_CACHE = DATA_DIR / "forecast_cache.csv"


@st.cache_data(ttl=600)
def get_forecast():
    """Weather + air-quality forecast; the loader itself re-downloads hourly."""
    return load_forecast(FORECAST_CACHE, HOME_CITY)


@st.cache_data(ttl=1800)
def get_air_now():
    """Measured AQI from IQAir, or None without an API key."""
    return load_current(DATA_DIR / "iqair_cache.json", HOME_CITY, ROOT)


def pace_axis(fig, values):
    """Show a seconds-per-km axis as m:ss, faster (smaller) at the top."""
    step = 15 if values.max() - values.min() <= 120 else 30
    low, high = int(values.min()) // step * step, int(values.max()) // step * step + step
    ticks = list(range(low, high + 1, step))
    fig.update_yaxes(tickvals=ticks, ticktext=[format_pace(t) for t in ticks], autorange="reversed")


def style(fig, y_title, height=380):
    """Thin, quiet chart chrome shared by every chart, in the page palette."""
    fig.update_layout(
        height=height,
        margin=dict(l=70, r=10, t=30, b=10),
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis_title=y_title,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK, family="sans-serif"),
        # A dark tooltip reads well on both light and dark pages.
        hoverlabel=dict(bgcolor="rgb(20,20,20)", bordercolor="rgb(20,20,20)", font=dict(color=PAPER)),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED), automargin=True)
    return fig


def chart(fig, y_title):
    """Draw a chart with our own styling (not Streamlit's chart theme)."""
    st.plotly_chart(style(fig, y_title), use_container_width=True, theme=None)


def note(text, accent=False):
    """A plain boxed note; accent=True gives it a red edge for things to act on."""
    st.markdown(f"<div class='note{' accent' if accent else ''}'>{text}</div>", unsafe_allow_html=True)


def muted(text):
    return f"<span class='muted'>{text}</span>"


def page_css():
    """Notes, level labels, the refresh icon and chart chrome - all drawn in the theme's
    own text colour (currentColor), so they stay readable in light and dark mode.
    The page palette itself comes from .streamlit/config.toml (light)."""
    icon = base64.b64encode((ASSETS / "refresh.png").read_bytes()).decode()
    st.markdown(f"""<style>
    .note {{ background:rgba(128,128,128,0.12); border-left:3px solid currentColor; padding:10px 14px; margin:6px 0 12px; }}
    .note.accent {{ border-left-color:{RED}; }}
    .muted {{ opacity:0.7; }}
    [data-testid="stDecoration"] {{ display:none; }}
    .level {{ display:inline-block; font-size:0.72rem; font-weight:600; letter-spacing:0.06em;
              text-transform:uppercase; border:1px solid currentColor; padding:0 6px; margin-right:8px; }}
    .level.high {{ color:{RED}; }}
    .level.pass, .level.info {{ opacity:0.6; }}
    section[data-testid="stSidebar"] .stButton button {{ display:flex; align-items:center; justify-content:center; gap:8px; }}
    /* The PNG is used as a mask, so the icon takes the button's text colour. */
    section[data-testid="stSidebar"] .stButton button::before {{
        content:""; width:16px; height:16px; flex:none; background-color:currentColor;
        -webkit-mask:url(data:image/png;base64,{icon}) center / contain no-repeat;
        mask:url(data:image/png;base64,{icon}) center / contain no-repeat; }}
    /* Charts: text, grid and the black series follow the theme's text colour. */
    .js-plotly-plot .main-svg text {{ fill:currentColor !important; }}
    .js-plotly-plot .hoverlayer text {{ fill:{PAPER} !important; }}
    .js-plotly-plot .gridlayer path, .js-plotly-plot .zerolinelayer path {{ stroke:currentColor !important; stroke-opacity:0.15 !important; }}
    .js-plotly-plot path.xlines-above, .js-plotly-plot path.ylines-above {{ stroke:currentColor !important; stroke-opacity:0.3 !important; }}
    .js-plotly-plot [style*="fill: rgb(0, 0, 0)"] {{ fill:currentColor !important; }}
    </style>""", unsafe_allow_html=True)


def race_heat_note():
    """Whether heat explains the difference between the last two races."""
    if race_a is None:
        return ""
    heat = [runs.loc[runs["start_time"] == pd.Timestamp(race_list(runs)[n]["start"]), "heat_slowdown_pct"].iloc[0]
            for n in (race_a, race_b)]
    if abs(heat[1] - heat[0]) < 1:
        return (f" Your last two races had similar heat ({heat[0]:.1f}% and {heat[1]:.1f}%), so the "
                "difference between them is not the weather.")
    return (f" Heat differed between your last two races ({race_a} {heat[0]:.1f}%, {race_b} {heat[1]:.1f}%): "
            "compare their heat-adjusted paces, not the raw times.")


def how(lines):
    """A 'How is this calculated?' box under each chart."""
    with st.expander("How is this calculated?"):
        st.markdown("\n".join(f"- {line}" for line in lines))


# ---------- page ----------

st.set_page_config(page_title="Running Training Analyzer", layout="wide", initial_sidebar_state="auto")
page_css()
st.title("Running Training Analyzer")
st.caption("Garmin records your runs. This explains your training.")

# Data: Garmin Connect through the Personal API (with GARMIN_API_KEY in .env), or a CSV export.
GARMIN = "Garmin Connect (synced)"
csv_files = sorted(p for p in DATA_DIR.glob("*.csv") if p.name not in ("weather_cache.csv", "forecast_cache.csv"))
sources = ([GARMIN] if api_key(ROOT) else []) + csv_files
if not sources:
    note(f"No data yet. Put GARMIN_API_KEY in .env, or export a Garmin CSV into {DATA_DIR}.", accent=True)
    st.stop()
d1, d2 = st.columns([3, 1], vertical_alignment="bottom")
source = d1.selectbox("Data", sources, format_func=lambda s: s if s == GARMIN else s.name)
from_api = source == GARMIN
if from_api:
    last_sync = synced_at(DATA_DIR)
    stale = last_sync is None or pd.Timestamp.now() - last_sync > pd.Timedelta(hours=SYNC_HOURS)
    if d2.button("Sync now", use_container_width=True) or stale:
        sync_garmin()
        last_sync = synced_at(DATA_DIR)
    days_left = key_days_left(ROOT)
    if days_left is not None and days_left <= KEY_WARN_DAYS:
        note(("Your Garmin API key has expired" if days_left < 0 else
              f"Your Garmin API key expires in {days_left} day{'s' if days_left != 1 else ''}")
             + ". Create a new one on Garmin Connect web (Settings → Personal API Token), then update "
               "GARMIN_API_KEY and GARMIN_API_KEY_EXPIRES in .env.", accent=True)
    if last_sync is None:
        st.stop()
    runs = load_api(str(last_sync))
    covered = covered_until(last_sync)
    st.caption(f"Synced {last_sync:%a %d %b %H:%M} · {len(runs)} runs since {runs['start_time'].min():%b %Y} · "
               f"syncs by itself when older than {SYNC_HOURS} h")
else:
    runs = load(str(source))
    covered = covered_until_from_file(source)
# What to do so the plan sees new runs.
update_hint = "Press Sync now" if from_api else "Export a new Garmin CSV"
# Races: Event Type "Race" in Garmin Connect, or listed in RACES in config.py.
# The headline and the post-mortem use the last two.
race_names = list(race_list(runs))
race_a, race_b = ([None] + race_names)[-2:] if race_names else (None, None)
races = race_rows(runs, race_a, race_b) if race_a else None
training = training_runs_with_efficiency(runs)
monthly = monthly_summary(training)
weekly = weekly_check(runs)

# Headline numbers
first_month, last_month = monthly.iloc[0], monthly.iloc[-1]
total_easy_pct = 100 * weekly["easy_time_s"].sum() / weekly["moving_time_s"].sum()

c1, c2, c3 = st.columns(3)
# Comparisons go in a caption, not st.metric's delta: the delta always gets an
# up/down arrow, and "↑ target 80%" next to a low score reads as good news.
pace_change = last_month["pace_at_ref_hr_s"] - first_month["pace_at_ref_hr_s"]  # negative = faster
if race_b:
    last_race = runs[runs["start_time"] == pd.Timestamp(race_list(runs)[race_b]["start"])].iloc[0]
    c1.metric(f"{race_b} time", format_duration(last_race["duration_s"]))
    caption = f"Race pace {format_pace(last_race['avg_pace_s_per_km'])}/km"
    if race_a:
        before = runs[runs["start_time"] == pd.Timestamp(race_list(runs)[race_a]["start"])].iloc[0]
        if abs(before["distance_km"] - last_race["distance_km"]) < 1:   # same distance: compare times
            change = before["duration_s"] - last_race["duration_s"]
            caption += f" · {format_duration(abs(change))} {'faster' if change > 0 else 'slower'} than {race_a}"
    c1.caption(caption)
else:
    c1.metric("Last race", "none yet")
    c1.caption("Set Event Type to Race in Garmin Connect")
c2.metric(f"Aerobic fitness: est. pace at {REFERENCE_HR} bpm", format_pace(last_month["pace_at_ref_hr_s"]))
c2.caption(f"Training runs in {monthly.index[-1].strftime('%b %Y')}, races excluded · "
           f"{abs(pace_change):.0f} s/km {'faster' if pace_change < 0 else 'slower'} than "
           f"{monthly.index[0].strftime('%b %Y')}")
c3.metric("Time spent easy", f"{total_easy_pct:.0f}%")
c3.caption(f"target {TARGET_EASY_PCT}%")

tab_plan, tab_pm, tab_fit, tab_easy, tab_heat = st.tabs(
    ["Training plan", "Race post-mortem", "Aerobic fitness", "Easy-run check", "Heat"]
)

# ---------- planner ----------

LEVELS = {"pass": "pass", "info": "note", "caution": "caution", "high": "high"}
STATUS = {"done": "done", "current": "this week", "needs data": "export needed", "upcoming": "upcoming"}
TITLES = {"easy": "Easy run", "long": "Long run", "tempo": "Tempo run", "interval": "Interval run"}


def what_changes(weeks, baseline):
    """One line: the weeks where the target's plan differs from the plan without a target."""
    diffs = []
    for week, base in zip(weeks, baseline):
        km = sum(w.distance_km for w in week["plan"]["workouts"])
        base_km = sum(w.distance_km for w in base["plan"]["workouts"])
        paced = [s for w in week["plan"]["workouts"] for s in w.steps if s.name == "race pace"]
        changed_pace = any(
            (s.pace_fast_s, s.pace_slow_s) != (b.pace_fast_s, b.pace_slow_s)
            for w, bw in zip(week["plan"]["workouts"], base["plan"]["workouts"])
            for s, b in zip(w.steps, bw.steps) if s.name in ("tempo", "interval"))
        if abs(km - base_km) >= 0.5 or paced or changed_pace:
            parts = [f"{km:g} km (no target {base_km:g})" if abs(km - base_km) >= 0.5 else f"{km:g} km"]
            if changed_pace:
                parts.append("target-based session pace")
            if paced:
                parts.append("goal-pace finish")
            diffs.append(f"week of {week['start']:%d %b}: " + ", ".join(parts))
    if not diffs:
        return "Compared with no target: no difference in these weeks yet."
    return ("What this target changes: " + "; ".join(diffs[:4])
            + ". Recovery weeks after a race are the same for every target - running then stays easy.")


def render_week(plan):
    """One week's why, daily menu and safety checks."""
    if plan.get("frozen"):
        st.caption(f"Frozen: this is the plan as you last saw it during the week "
                   f"(saved {plan['saved_at']:%a %d %b %H:%M}). Later changes to the goal do not rewrite it.")
    note(f"{escape(plan['why'])}<br>{muted('Source: ' + escape(plan['why_sources']))}")
    if plan.get("pace_note"):
        st.caption(plan["pace_note"])
    for day in plan["days"]:
        if day.kind == "race":
            note(f"<b>{day.day:%a %d %b} · Race</b><br>{escape(day.reason)}", accent=True)
            continue
        if day.kind == "rest":
            st.markdown(f"**{day.day:%a %d %b} · Rest**  \n{muted(day.reason)}", unsafe_allow_html=True)
            continue
        with st.container(border=True):
            st.markdown(f"**{day.day:%a %d %b} · {TITLES[day.kind]} · "
                        f"{day.distance_km:g} km · ~{day.minutes:.0f} min**")
            st.caption(day.reason)
            if forecast is not None:
                conditions = day_conditions(forecast, day.day)
                lines = [describe_window(n, c) for n, c in conditions.items() if c]
                if lines:
                    st.caption("Forecast (info only) - " + " · ".join(lines))
                    warning = air_note(conditions)
                    if warning:
                        note(warning, accent=True)
            st.dataframe(pd.DataFrame([{
                "step": s.name,
                "km": s.distance_km,
                "heart rate": f"{s.hr_min}-{s.hr_max} bpm",
                "pace": f"{format_pace(s.pace_fast_s)}-{format_pace(s.pace_slow_s)} /km",
                "time": f"~{s.minutes:.0f} min",
                "how": s.note,
            } for s in day.steps]), hide_index=True, use_container_width=True)
            st.download_button(f"Download {day.day:%a} workout (.fit)", workout_fit_bytes(day),
                               file_name=file_name(day), mime="application/octet-stream",
                               key=f"fit-{day.day}")

    st.markdown("**Safety checks**")
    for check in plan["checks"]:
        level = check["level"]
        st.markdown(f"<span class='level {level}'>{LEVELS[level]}</span>**{escape(check['rule'])}** - "
                    f"{escape(check['detail'])}<br>"
                    f"{muted(escape(check['formula']) + '<br>Source: ' + escape(check['sources']))}",
                    unsafe_allow_html=True)


# ---------- forecast sidebar ----------

with st.sidebar:
    st.subheader(f"{HOME_CITY} weather")
    if st.button("Refresh forecast", use_container_width=True):
        load_forecast(FORECAST_CACHE, HOME_CITY, force=True)
        get_forecast.clear()
        get_air_now.clear()

air_now = get_air_now()
forecast = get_forecast()
if forecast is not None:
    forecast = combine_air(forecast, air_now)

with st.sidebar:
    if forecast is None:
        st.caption("Forecast unavailable - no internet and no saved forecast.")
    else:
        now = pd.Timestamp.now()
        hours = next_hours(forecast, now)
        current = hours.iloc[0]
        aqi_now = air_now["us_aqi"] if air_now else current["us_aqi"]

        c1, c2 = st.columns(2)
        c1.metric("Now", f"{current['air_temp_c']:.0f}°C")
        c2.metric("US AQI", "-" if pd.isna(aqi_now) else f"{aqi_now:.0f}")
        st.caption(f"{current['weather']} · dew point {current['dew_point_c']:.0f}°C · "
                   f"heat -{current['heat_slowdown_pct']:.0f}% · rain {current['rain_chance_pct']:.0f}%"
                   + ("" if pd.isna(aqi_now) else f" · air {aqi_label(aqi_now)}"))

        st.markdown("**Next hours**")
        st.dataframe(pd.DataFrame({
            "time": hours["time"].dt.strftime("%H:%M"),
            "sky": hours["weather"],
            "°C": hours["air_temp_c"].round(0).astype(int),
            "rain": hours["rain_chance_pct"].map(lambda p: f"{p:.0f}%"),
            "AQI": hours["us_aqi"].map(lambda a: "-" if pd.isna(a) else f"{a:.0f}"),
        }), hide_index=True, use_container_width=True)

        # Your run window: today if it has not passed yet, otherwise tomorrow.
        run_day = now.date() if now.hour <= RUN_HOURS[1] else (now + pd.Timedelta(days=1)).date()
        run = window_conditions(forecast, run_day, RUN_HOURS)
        if run:
            when = "today" if run_day == now.date() else "tomorrow"
            st.markdown(f"**Your run time {when} ({RUN_HOURS[0]:02d}-{RUN_HOURS[1]:02d})**")
            st.caption(describe_window("run time", run).split(": ", 1)[1])
            warning = air_note({"run time": run})
            if warning:
                note(warning, accent=True)

        updated = fetched_at(FORECAST_CACHE)
        st.caption(f"Updated {updated:%H:%M} · Open-Meteo · info only, the plan does not change. "
                   "Air quality is a model estimate.")

with tab_plan:
    if air_now:
        source = f"(measured by IQAir at {escape(air_now['station'])}, {air_now['time']:%H:%M})"
        note(f"Air right now: <b>AQI {air_now['us_aqi']:.0f} - {aqi_label(air_now['us_aqi'])}</b> {muted(source)}")
    known = runs[runs["start_time"] < pd.Timestamp(covered) + pd.Timedelta(days=1)]
    gain = weekly_fitness_gain(known)
    today = pd.Timestamp.now().date()

    # ---- goal: distance, "sub" target and optional race date; saved to data/goal.json ----
    goal = load_goal()
    st.subheader("Your goal")
    g1, g2, g3 = st.columns([1, 1.6, 1])
    # Each widget has a fixed key and is seeded from data/goal.json only once per
    # session. (Passing a changing default instead makes Streamlit treat it as a new
    # widget and silently reset your choice - every other change got lost.)
    state = st.session_state
    distances = list(DISTANCES)
    state.setdefault("goal_distance", distance_name(goal["distance_km"]))
    distance = g1.selectbox("Distance", distances, key="goal_distance")
    distance_km = DISTANCES[distance]

    estimate = goal_gap(known, {**goal, "distance_km": distance_km, "target_time": None}, gain, today)
    target_time = None
    if estimate:
        options = target_options(estimate["estimate_now_s"], distance_km, gain)
        labels = ["No target yet"] + [
            f"sub {format_duration(t)} · {format_pace(t / distance_km)}/km · "
            + ("in reach now" if w == 0 else f"~{w:.0f} weeks at your rate" if w is not None else "trend flat")
            + f" · peak ~{peak_km(distance_km, t)} km/week"
            for t, w in options]
        if state.get("goal_target") not in labels:   # first visit, or the distance changed
            saved = parse_time(goal["target_time"]) if goal.get("target_time") else None
            same_distance = abs(goal["distance_km"] - distance_km) < 0.1
            state["goal_target"] = next((labels[i + 1] for i, (t, _) in enumerate(options)
                                         if saved and same_distance and abs(t - saved) < 1), labels[0])
        choice = g2.selectbox(f"Target (estimate today {format_duration(estimate['estimate_now_s'])})",
                              labels, key="goal_target")
        if choice != labels[0]:
            target_time = format_duration(options[labels.index(choice) - 1][0])
    else:
        g2.caption("Mark a past race (Event Type: Race in Garmin Connect) to get target options.")

    state.setdefault("goal_has_date", bool(goal.get("date")))
    has_date = g3.checkbox("I have a race date", key="goal_has_date")
    race_date = None
    if has_date:
        saved_date = pd.Timestamp(goal["date"]).date() if goal.get("date") else today + pd.Timedelta(weeks=16)
        state.setdefault("goal_date", max(saved_date, today))
        race_date = g3.date_input("Race date", min_value=today, key="goal_date")

    chosen = {"name": f"Next {distance.lower()}", "distance_km": distance_km, "target_time": target_time,
              "date": race_date.isoformat() if race_date else None}
    # Save only when the choice changed (not just because the default name differs).
    if any(goal.get(k) != chosen[k] for k in ("distance_km", "target_time", "date")):
        save_goal(chosen)
    goal = {**goal, **chosen}

    weeks = build_month_plan(runs, covered, goal_race=goal, plans_dir=DATA_DIR / "plans")
    plan = current_week(weeks)["plan"]
    ctx = plan["context"]

    gap = goal_gap(known, goal, gain, today) if goal["target_time"] else None
    if not gap:
        st.caption("Pick a target to see the gap to it, get goal-pace running in your long runs and, with a "
                   "race date, a taper.")
    if gap:
        peak = peak_km(goal["distance_km"], parse_time(goal["target_time"]))
        lines = (describe_gap(gap, goal)
                 + [f"Training load for this target: builds to about {peak} km/week, then holds "
                    "(a harder target builds higher, an easier one lower)."]
                 + ([plan["goal_note"]] if plan.get("goal_note") else [])
                 + [what_changes(weeks, build_month_plan(runs, covered, goal_race={**goal, "target_time": None}))])
        note("<br>".join(escape(line) for line in lines),
             accent=gap["race_date"] is not None and gap["gain_needed"] > REALISTIC_GAIN)
        how([
            f"Riegel: last race time × (goal km ÷ race km)^{RIEGEL_EXPONENT} = {format_duration(gap['riegel_s'])}.",
            f"Fitness since then: × (efficiency before the race {gap['efficiency_race']:.3f} ÷ "
            f"now {gap['efficiency_now']:.3f}) = {format_duration(gap['estimate_now_s'])}.",
            f"Projection: estimate ÷ (1 + {100 * gap['weekly_gain']:.1f}% a week)^weeks - your own recent rate. "
            "Training 5-6 times a week may well raise that rate; each export updates it.",
            "Weeks needed = ln(estimate ÷ target) ÷ ln(1 + weekly gain).",
            "Assumes race conditions like your last race (Jakarta heat, similar pacing). A rough guide, "
            "not a prediction. Sources: " + describe(["riegel1981"]) + ".",
            "Peak load: a half-marathon table (sub 3:20 ~26 km/week, sub 3:00 ~33, sub 2:50 ~38, sub 2:40 ~44, "
            "sub 2:30 ~50, up to ~68), straight lines between rows; other distances via Riegel, scaled (5K x0.6, "
            "10K x0.75, marathon x1.15). A planner heuristic anchored on Fokkema 2020 (over 32 km/week went "
            "with faster halves). At the peak the long run keeps growing to half the peak and the easy runs "
            "make room (shorter first, then one fewer, at least 4 runs).",
            "What the target changes in the plan: goal pace = target ÷ distance. If it is faster than easy "
            "but not faster than the top of your tempo range, build-week long runs end with 2 km at goal "
            "pace (the watch targets pace). The long run grows towards the distance's maximum "
            "(5K 12, 10K 16, half 21, marathon 32 km). A race date adds the taper. The safety rules do "
            "not change with the target - a harder target means more weeks, not riskier ones.",
        ])

    st.subheader(f"Training plan from {weeks[0]['start']:%a %d %b %Y}")
    st.caption(f"Your data covers runs up to {covered:%a %d %b}. {update_hint} at the end of each "
               "week: that week is evaluated and the following weeks are re-planned. Frequency first: one "
               "run (5 km or more) is added each week until your target; the long run grows 1 km a week "
               "when the last one was done; every 4th week steps back. Paces are estimates in your usual "
               "heat - follow heart rate, not pace. Not medical advice.")

    st.dataframe(pd.DataFrame([{
        "week": w["number"],
        "dates": f"{w['start']:%d %b} - {w['end']:%d %b}",
        "type": w["plan"]["week_type"],
        "km": sum(x.distance_km for x in w["plan"]["workouts"]),
        "long run km": next((x.distance_km for x in w["plan"]["workouts"] if x.kind == "long"), 0.0),
        "runs": len(w["plan"]["workouts"]),
        "status": STATUS[w["status"]],
        "evaluation": describe_evaluation(w["evaluation"]) if w["evaluation"] else "",
    } for w in weeks]), hide_index=True, use_container_width=True)

    with st.expander(f"Weather & air quality forecast - {HOME_CITY} (info only)"):
        if forecast is None:
            st.caption("Forecast unavailable (no internet and no cached forecast).")
        else:
            rows = []
            for day in sorted(set(forecast["time"].dt.date)):
                for name, c in day_conditions(forecast, day).items():
                    if c:
                        rows.append({
                            "date": f"{day:%a %d %b}",
                            "window": f"{name} {WINDOWS[name][0]:02d}-{WINDOWS[name][1]:02d}",
                            "temp °C": round(c["air_temp_c"]),
                            "dew point °C": round(c["dew_point_c"]),
                            "heat slowdown": f"{c['heat_slowdown_pct']:.0f}%",
                            "rain chance": f"{c['rain_chance_pct']:.0f}%",
                            "US AQI": "" if c["us_aqi"] is None else f"{c['us_aqi']:.0f} ({aqi_label(c['us_aqi'])})",
                            "AQI source": c["aqi_source"],
                            "PM2.5 µg/m³": "" if c["pm2_5"] is None else f"{c['pm2_5']:.0f}",
                        })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            st.caption("Weather: Open-Meteo, 16 days. Air quality: **measured** = IQAir now; **adjusted** = "
                       "Open-Meteo model (CAMS) scaled by how far off it is from the IQAir measurement, fading "
                       "out over 48 h; **model** = Open-Meteo only (up to ~7 days); blank = no air data. "
                       "AQI categories: US EPA. Heat slowdown: same rule of thumb as the Heat tab.")

    for w in weeks:
        p = w["plan"]
        label = (f"Week {w['number']} · {w['start']:%d %b} - {w['end']:%d %b} · {p['week_type']} · "
                 f"{sum(x.distance_km for x in p['workouts']):g} km · {STATUS[w['status']]}")
        with st.expander(label, expanded=w["status"] == "current"):
            if w["evaluation"]:
                note(f"<b>Evaluation</b> - {escape(describe_evaluation(w['evaluation']))}")
            elif w["status"] == "upcoming":
                st.caption("Provisional - recalculated when the weeks before it have real data.")
            render_week(p)

    with st.expander("Heart-rate settings - why these numbers?"):
        for s in plan["hr_settings"]:
            st.markdown(f"**{s['setting']}** - {s['evidence']}  \n{muted('Source: ' + escape(s['sources']))}",
                        unsafe_allow_html=True)

    if ctx["empty_weeks"]:
        note(f"No runs recorded in week(s) of {', '.join(ctx['empty_weeks'])} - counted as 0 km. "
             f"If you ran, {update_hint.lower()} again.", accent=True)
    how([
        f"Based on the 4 weeks before {ctx['plan_start']:%d %b}: {ctx['baseline_km']:.1f} km/week, "
        f"{ctx['runs_per_week']:.1f} runs/week, longest training run {ctx['longest_recent_km']:.1f} km, "
        f"{ctx['easy_pct']:.0f}% easy.",
        "Week type, first rule that matches: race in the last 14 days → recovery (every run easy); easy "
        "time under 50% → fix easy (every run easy); otherwise → build, with one hard session a week - "
        "tempo and intervals in turn. Strides on one easy run a week from 7 days after a race.",
        f"Runs per week: starts at {START_RUNS_PER_WEEK}, then one run of {MIN_RUN_KM:g} km or more is "
        "added each week (also in recovery weeks; not if more than one run was missed last week, or after "
        "an injury) up to RUNS_PER_WEEK in config.py - unless it would put the week more than 30% above the "
        "last 7 days (Nielsen 2014).",
        f"Once at the target number of runs, weekly distance grows {WEEKLY_GROWTH:.0%} (WEEKLY_GROWTH), "
        "shared by the easy runs - still under the 30% limit.",
        "Long run: starts from your recent longest run and never goes down: +1 km a week when last week's "
        "reached 90% of plan and it fits under the 30% limit; the same distance if missed or in a recovery "
        "week; max 21 km. Only a taper shortens it.",
        f"Every {STEP_BACK_EVERY}th week is a step-back week: no extra run, long run holds, about 25% less "
        "distance (easy runs shorter first, then one fewer). The week after measures from the week before "
        "the step-back.",
        "With a race date (Your goal, above): 2 weeks before the race the distance drops to 70%, then 50% in "
        "race week, keeping runs frequent and some faster running (Bosquet 2007); no runs on race day or "
        "the day before. After the race, the usual 3 rest days and recovery weeks follow.",
        "Intervals: 3-6 x 800 m (as many as fit the run's distance) with 400 m jogs; the watch targets "
        "pace on the repeats because heart rate rises too slowly on short efforts.",
        "Future weeks assume planned runs are done as planned, until real data replaces them.",
        "Paces: this week's come from the median efficiency of your last 4 weeks of real runs. Future weeks "
        "add your own recent fitness gain per week (straight-line trend of efficiency, max 1%/week). Each "
        "new export recalculates them from real data - if you get fitter faster, paces speed up faster.",
        "Pace guide = 1000 ÷ (recent efficiency × HR) - your efficiency already includes the usual heat.",
    ])

# ---------- race post-mortem ----------

with tab_pm:
    st.subheader("What changed between the two races?")
    if race_a is None:
        note("The post-mortem needs two races. Set Event Type to Race on your race activities in Garmin "
             "Connect (or list them in RACES in config.py).")
    else:
        st.dataframe(races, hide_index=True, use_container_width=True)
        st.markdown(f"**Training in the {COMPARE_WEEKS} weeks before each race**")
        st.dataframe(compare_races(runs, race_a, race_b), hide_index=True, use_container_width=True)
    how([
        f"Races: activities with Event Type Race in Garmin Connect, plus any listed in RACES in config.py. "
        f"The last two are compared ({len(race_names)} found).",
        f"Block = all runs in the {COMPARE_WEEKS} weeks before the race start, race excluded.",
        f"{COMPARE_WEEKS} weeks because the export starts on {runs['start_time'].min():%Y-%m-%d}.",
        "The *how* column shows the formula for every row.",
    ])

# ---------- aerobic fitness ----------

with tab_fit:
    st.subheader(f"Are you faster at the same heart rate? (estimated pace @ {REFERENCE_HR} bpm)")
    # A "median" of 1-2 runs is just those runs, so leave such months off the line.
    solid = monthly[monthly["runs"] >= 3]
    month_mid = solid.index.to_timestamp() + pd.Timedelta(days=14)

    fig = go.Figure()
    fig.add_scatter(
        x=training["start_time"], y=training["pace_at_ref_hr_s"], mode="markers", name="Each run",
        marker=dict(size=9, color=INK, opacity=0.35, line=dict(width=0)),
        customdata=list(zip(training["title"], training["avg_pace_s_per_km"].map(format_pace),
                            training["avg_hr"].astype(int), training["pace_at_ref_hr_s"].map(format_pace))),
        hovertemplate="%{x|%d %b}  %{customdata[0]}<br>actual %{customdata[1]}/km @ %{customdata[2]} bpm"
                      f"<br>@ {REFERENCE_HR} bpm: %{{customdata[3]}}/km<extra></extra>",
    )
    fig.add_scatter(
        x=month_mid, y=solid["pace_at_ref_hr_s"], mode="lines+markers", name="Monthly median (3+ runs)",
        line=dict(width=2, color=RED), marker=dict(size=9, color=RED),
        customdata=list(zip(solid.index.astype(str), solid["pace_at_ref_hr_s"].map(format_pace), solid["runs"])),
        hovertemplate="%{customdata[0]}: %{customdata[1]}/km (%{customdata[2]} runs)<extra></extra>",
    )
    pace_axis(fig, training["pace_at_ref_hr_s"])
    chart(fig, f"pace @ {REFERENCE_HR} bpm (faster ↑)")

    trend = trend_line(training)
    st.markdown(
        f"Monthly median: **{format_pace(first_month['pace_at_ref_hr_s'])} → "
        f"{format_pace(last_month['pace_at_ref_hr_s'])} /km**. "
        f"Straight-line fit through every run: efficiency {trend['change_pct']:+.1f}% (r = {trend['r']:.2f}). "
        "Months with fewer than 3 runs are shown as dots only."
    )
    how([
        "efficiency = (distance m ÷ moving minutes) ÷ average HR",
        f"pace @ {REFERENCE_HR} = 1000 ÷ (efficiency × {REFERENCE_HR}) minutes per km",
        "Assumes speed rises in proportion to HR - most reliable near your usual HR.",
        "Races are left out: hours of racing fatigue make them not comparable.",
    ])
    with st.expander("Table"):
        table = monthly.copy()
        table["pace_at_ref_hr_s"] = table["pace_at_ref_hr_s"].map(format_pace)
        table.index = table.index.astype(str)
        st.dataframe(table.round(2), use_container_width=True)

# ---------- easy-run check ----------

with tab_easy:
    st.subheader("Were your easy runs actually easy?")
    weeks = weekly.index.to_timestamp()  # Monday of each week
    easy_min = weekly["easy_time_s"] / 60
    hard_min = (weekly["moving_time_s"] - weekly["easy_time_s"]) / 60

    fig = go.Figure()
    fig.add_bar(x=weeks, y=easy_min, name=f"Easy (avg HR ≤ {EASY_HR_MAX})", marker_color=INK,
                customdata=weekly["easy_pct"].round(0), hovertemplate="week of %{x|%d %b}<br>easy %{y:.0f} min (%{customdata:.0f}%)<extra></extra>")
    fig.add_bar(x=weeks, y=hard_min, name=f"Hard (avg HR > {EASY_HR_MAX})", marker_color=RED,
                customdata=weekly["verdict"], hovertemplate="week of %{x|%d %b}<br>hard %{y:.0f} min<br>%{customdata}<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.25, barcornerradius=4, legend_traceorder="normal")
    for week in weeks[weekly["race_week"]]:
        fig.add_annotation(x=week, y=(weekly["moving_time_s"] / 60).max() * 1.08, text="race",
                           showarrow=False, font=dict(color=MUTED, size=12))
    chart(fig, "minutes per week")

    on_target = (weekly["verdict"] == "on target").sum()
    st.markdown(f"Overall **{total_easy_pct:.0f}% easy** (target {TARGET_EASY_PCT}%). "
                f"Weeks on target: **{on_target} of {len(weekly)}**.")

    wrong = mislabelled_easy_runs(runs)
    st.markdown(f"**Runs you called easy that were not ({len(wrong)})**")
    st.dataframe(
        pd.DataFrame({
            "date": wrong["start_time"].dt.strftime("%Y-%m-%d"),
            "title": wrong["title"],
            "km": wrong["distance_km"],
            "avg HR": wrong["avg_hr"].astype(int),
            "above easy by": (wrong["avg_hr"] - EASY_HR_MAX).astype(int).astype(str) + " bpm",
        }),
        hide_index=True, use_container_width=True,
    )
    how([
        f"Easy run = average HR ≤ {EASY_HR_MAX} bpm (80% of max HR {MAX_HR}, set in config.py).",
        "Easy % = moving time of easy runs ÷ total moving time, per Monday-Sunday week.",
        f"Verdict: on target ≥ {TARGET_EASY_PCT - 5}%, too much hard running ≥ 50%, otherwise easy runs are not easy.",
        "Runs with an activity .fit file in data/activities/ count the actual seconds at HR ≤ "
        f"{EASY_HR_MAX}. Runs without one use their *average* HR, so a run with easy parts can still "
        "count as hard.",
    ])
    with st.expander("Table"):
        table = weekly.copy()
        table.index = table.index.map(lambda p: f"{p.start_time:%Y-%m-%d}")
        table["moving_time_s"] = (table["moving_time_s"] / 60).round(0)
        table = table.drop(columns="easy_time_s").rename(columns={"moving_time_s": "minutes"})
        st.dataframe(table.round(1), use_container_width=True)

# ---------- heat ----------

with tab_heat:
    st.subheader("How much did heat and humidity slow each run?")
    fig = go.Figure()
    fig.add_scatter(
        x=runs["start_time"], y=runs["heat_slowdown_pct"], mode="markers", name="Heat slowdown",
        marker=dict(size=9, color=INK, line=dict(width=0)),
        customdata=list(zip(runs["title"], runs["air_temp_c"].round(1), runs["dew_point_c"].round(1),
                            runs["avg_pace_s_per_km"].map(format_pace), runs["heat_adj_pace_s"].map(format_pace))),
        hovertemplate="%{x|%d %b}  %{customdata[0]}<br>air %{customdata[1]} °C, dew point %{customdata[2]} °C"
                      "<br>slowdown %{y:.1f}%<br>actual %{customdata[3]} → cool-weather %{customdata[4]}/km<extra></extra>",
    )
    fig.update_yaxes(range=[0, 10], ticksuffix="%")
    chart(fig, "expected slowdown")

    st.markdown(
        f"Heat costs you about **{runs['heat_slowdown_pct'].median():.1f}%** on a typical run "
        f"(range {runs['heat_slowdown_pct'].min():.1f}-{runs['heat_slowdown_pct'].max():.1f}%)."
        + race_heat_note()
    )
    how([
        "Air temperature and dew point: Open-Meteo, hourly, for the city in the run title, averaged over the run.",
        "Your watch's own temperature is not used: it reads 5-9 °C high because it sits on your wrist.",
        "Heat score = air temp °F + dew point °F; slowdown % is read from this table (straight line between rows): "
        + ", ".join(f"{s} → {p}%" for s, p in SLOWDOWN_TABLE),
        "Heat-adjusted pace = actual pace ÷ (1 + slowdown % ÷ 100). A rule of thumb for comparing runs, not an exact law.",
        "Slower runners likely lose more than this estimate: in Hodgson et al. 2022 the slowest finishers "
        "lost the most time per extra °C.",
    ])
    with st.expander("Table"):
        st.dataframe(pd.DataFrame({
            "date": runs["start_time"].dt.strftime("%Y-%m-%d %H:%M"),
            "title": runs["title"],
            "air °C": runs["air_temp_c"].round(1),
            "dew point °C": runs["dew_point_c"].round(1),
            "slowdown %": runs["heat_slowdown_pct"].round(1),
            "actual": runs["avg_pace_s_per_km"].map(format_pace),
            "heat-adjusted": runs["heat_adj_pace_s"].map(format_pace),
        }), hide_index=True, use_container_width=True)
