"""Running Training Analyzer dashboard.

Run from the project folder:
    streamlit run app/dashboard.py

This file only draws. Every number comes from src/, so the dashboard and the
command-line reports always agree. Every sentence comes from app/i18n.py, in
English or Indonesian (⋮ → Settings → Language).

The page answers questions in the order a runner asks them:
  1. What do I run today?          5. Is anything risky?
  2. How is my week going?         6. How has my running gone so far?
  3. Where is my goal?             7. Go deeper: races, fitness, easy vs hard, heat.
  4. What comes next?
"""

import base64
import json
import sys
from html import escape
from pathlib import Path

# Streamlit runs this file directly, so tell Python where the project root is
# (one folder up) so that "from src..." and "from i18n" imports work.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from i18n import LANGUAGES, Text
from src.analysis import checkpoint
from src.analysis.easy_check import mislabelled_easy_runs, weekly_check
from src.analysis.fitness_trend import monthly_summary, training_runs_with_efficiency
from src.analysis.goal_planner import REALISTIC_GAIN, goal_gap, parse_time, peak_km, target_options, weeks_needed
from src.analysis.heat_adjust import SLOWDOWN_TABLE, load_api_runs_with_heat, load_runs_with_heat
from src.analysis.race_postmortem import METRICS, compare_races, race_rows
from src.analysis.races import race_list
from src.analysis.run_review import review
from src.analysis.run_conditions import aqi_label, combine_air, next_hours, window_conditions
from src.config import (
    COMPARE_WEEKS, EASY_HR_MAX, GOAL_RACE, HOME_CITY, MAX_HR, PLAN_START, REFERENCE_HR, RUN_HOURS, RUNS_PER_WEEK,
    TARGET_EASY_PCT,
)
from src import programs
from src.evidence import SOURCES
from src.goal_settings import DISTANCES, distance_name, load_goal
from src.loaders.forecast_openmeteo import fetched_at, load_forecast
from src.loaders.garmin_api import KEY_WARN_DAYS, SYNC_HOURS, KeyRejected, api_key, key_days_left, sync, synced_at
from src.loaders.fit_activities import ACTIVITY_DIR, load_splits
from src.loaders.iqair import load_current
from src.planner.month_plan import build_month_plan, covered_until, covered_until_from_file, current_week, \
    weekly_fitness_gain
from src.planner.plan_generator import RACE_PACE_MAX_KM
from src.planner.safety_rules import POST_RACE_REST_DAYS, RECOVERY_DAYS, recovery_days
from src.units import format_duration, format_pace

# Palette: paper, red, black - plus tints of them for quiet chrome.
# Black and red as chart series were checked for colour-blind separation on PAPER.
PAPER = "#EEEBE3"
RED = "#f01e2c"          # accent: today, hard running, warnings, the line that matters
INK = "#000000"          # text and the main series
MUTED = "#6B6862"        # secondary text (black mixed into paper)
GRID = "#D6D1C4"         # hairlines

DATA_DIR = ROOT / "data"
ASSETS = Path(__file__).resolve().parent / "assets"
FORECAST_CACHE = DATA_DIR / "forecast_cache.csv"
HARD = ("tempo", "interval")


# ---------- data ----------

@st.cache_data
def load(csv_path):
    """Load once and keep in memory; Streamlit re-runs this file on every click."""
    return load_runs_with_heat(csv_path)


@st.cache_data(show_spinner=False)
def load_api(synced):
    """Runs from the last Garmin sync; `synced` (the sync time) makes a new sync reload."""
    return load_api_runs_with_heat(DATA_DIR)


@st.cache_data(ttl=600)
def get_forecast():
    """Weather + air-quality forecast; the loader itself re-downloads hourly."""
    return load_forecast(FORECAST_CACHE, HOME_CITY)


@st.cache_data(ttl=1800)
def get_air_now():
    """Measured AQI from IQAir, or None without an API key."""
    return load_current(DATA_DIR / "iqair_cache.json", HOME_CITY, ROOT)


def sync_garmin():
    """Pull new activities from Garmin Connect, with a progress bar for the .fit files."""
    bar = st.progress(0.0, text=t("syncing"))
    try:
        summary = sync(DATA_DIR, ROOT, progress=lambda done, total: bar.progress(
            done / total, text=t("downloading", done=done, total=total)))
    except KeyRejected:
        bar.empty()
        note(t("key rejected"), accent=True)
        return
    except Exception as error:   # offline, Garmin down: keep the last sync
        bar.empty()
        note(t("sync failed", error=escape(str(error))), accent=True)
        return
    bar.empty()
    if summary["new"]:
        st.toast(t("new activities", n=summary["new"]))


# ---------- drawing helpers ----------

def pace_axis(fig, values):
    """Show a seconds-per-km axis as m:ss, faster (smaller) at the top."""
    step = 15 if values.max() - values.min() <= 120 else 30
    low, high = int(values.min()) // step * step, int(values.max()) // step * step + step
    ticks = list(range(low, high + 1, step))
    fig.update_yaxes(tickvals=ticks, ticktext=[format_pace(x) for x in ticks], autorange="reversed")


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


def chart(fig, y_title, height=380):
    """Draw a chart with our own styling (not Streamlit's chart theme)."""
    st.plotly_chart(style(fig, y_title, height), use_container_width=True, theme=None,
                    config={"displayModeBar": False})


def html(text):
    st.markdown(text, unsafe_allow_html=True)


def note(text, accent=False):
    """A plain boxed note; accent=True gives it a red edge for things to act on."""
    html(f"<div class='note{' accent' if accent else ''}'>{text}</div>")


def how(lines):
    """A 'How is this calculated?' box."""
    with st.expander(t("how calc")):
        st.markdown("\n".join(f"- {line}" for line in lines))


def page_css():
    """Cards, the week strip, notes and chart chrome - all drawn in the theme's own
    text colour (currentColor) and see-through greys, so they stay readable in light
    and dark mode. The page palette itself comes from .streamlit/config.toml."""
    icon = base64.b64encode((ASSETS / "refresh.png").read_bytes()).decode()
    html(f"""<style>
    [data-testid="stDecoration"] {{ display:none; }}
    .block-container {{ padding-top:2.2rem; max-width:1100px; }}
    h1 {{ font-size:1.9rem !important; }}
    h3 {{ margin-top:0.6rem !important; }}
    .note {{ background:rgba(128,128,128,0.12); border-left:3px solid currentColor; padding:10px 14px; margin:6px 0 12px; }}
    .note.accent {{ border-left-color:{RED}; }}
    .muted {{ opacity:0.68; }}
    .eyebrow {{ font-size:0.74rem; font-weight:600; letter-spacing:0.08em; text-transform:uppercase; opacity:0.65; }}
    .eyebrow.red {{ color:{RED}; opacity:1; }}

    /* Today: a training sheet - a heavy rule, big numbers, the run's profile. No box. */
    .today {{ border-top:3px solid currentColor; padding-top:10px; margin:2px 0 18px; }}
    .today .top {{ display:flex; justify-content:space-between; flex-wrap:wrap; gap:4px 16px; font-size:0.74rem;
                   font-weight:600; letter-spacing:0.08em; text-transform:uppercase; }}
    .today .top .date {{ color:{RED}; }}
    .today .top .phase {{ opacity:0.6; }}
    .today .kind {{ font-size:1.05rem; font-weight:600; margin-top:20px; }}
    .today .rest {{ font-size:2.6rem; font-weight:700; line-height:1; margin-top:16px; }}
    .stats {{ display:flex; flex-wrap:wrap; gap:14px 48px; margin-top:6px; }}
    .stat .v {{ font-size:2.6rem; font-weight:700; line-height:1; font-variant-numeric:tabular-nums; white-space:nowrap; }}
    .stat .v small {{ font-size:1.05rem; font-weight:600; margin-left:4px; }}
    .stat.key .v {{ color:{RED}; }}
    .stat .l {{ font-size:0.7rem; font-weight:600; letter-spacing:0.08em; text-transform:uppercase; opacity:0.6; margin-top:6px; }}
    .profile {{ display:flex; gap:2px; height:12px; margin-top:24px; }}
    .profile span {{ background:currentColor; opacity:0.22; }}
    .profile span.main {{ opacity:1; }}
    .profile span.hard {{ background:{RED}; opacity:1; }}
    .sequence {{ font-size:0.86rem; margin-top:7px; opacity:0.75; }}
    .today .hint {{ font-size:0.92rem; margin-top:12px; }}
    .today .hint.muted {{ opacity:0.68; }}
    .conditions {{ border-top:1px solid rgba(128,128,128,0.35); margin-top:18px; padding-top:9px; font-size:0.92rem; }}
    .conditions .when {{ font-weight:600; margin-right:10px; font-variant-numeric:tabular-nums; }}
    .alert {{ color:{RED}; font-weight:600; margin-top:6px; }}
    .alert::before {{ content:""; display:inline-block; width:8px; height:8px; background:{RED}; margin-right:8px; vertical-align:1px; }}
    @media (max-width:640px) {{ .stat .v {{ font-size:2rem; }} .stats {{ gap:14px 28px; }} }}

    /* The week strip: 7 equal tiles, also on a phone */
    .week {{ display:grid; grid-template-columns:repeat(7, minmax(0, 1fr)); gap:6px; margin:6px 0 4px; }}
    .tile {{ border:1px solid rgba(128,128,128,0.3); border-radius:10px; padding:8px 2px 7px; text-align:center; min-width:0; }}
    .tile .dn {{ font-size:0.7rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; opacity:0.6; white-space:nowrap; }}
    @media (max-width:640px) {{ .tile .dn {{ font-size:0.6rem; letter-spacing:0.02em; }} .spacer {{ display:none; }} }}
    .tile .dk {{ font-size:0.86rem; font-weight:600; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .tile .dd {{ font-size:0.78rem; opacity:0.75; }}
    .tile .ds {{ font-size:0.66rem; margin-top:4px; min-height:1.1em; opacity:0.75; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .tile.rest {{ opacity:0.5; }}
    .tile.hard .dk {{ color:{RED}; }}
    .tile.done {{ background:rgba(128,128,128,0.16); }}
    .tile.missed .ds {{ color:{RED}; opacity:1; }}
    .tile.today {{ border:2px solid {RED}; }}
    .tile.today .ds {{ color:{RED}; opacity:1; font-weight:600; }}

    /* Page links under the title */
    .nav {{ display:flex; gap:22px; border-bottom:1px solid rgba(128,128,128,0.35); margin:2px 0 14px; }}
    .nav a {{ color:inherit !important; text-decoration:none !important; font-weight:600; padding:6px 0 8px;
              margin-bottom:-1px; border-bottom:2px solid transparent; opacity:0.6; }}
    .nav a.on {{ border-bottom-color:{RED}; opacity:1; }}
    a.more {{ color:{RED} !important; font-weight:600; text-decoration:none !important; }}

    /* Programs: a list of rules, not cards */
    .program {{ border-top:2px solid currentColor; padding:10px 0 12px; margin-top:8px; }}
    .program .name {{ font-size:1.25rem; font-weight:700; }}
    .program .name a {{ color:inherit !important; text-decoration:none !important; }}
    .program .meta {{ opacity:0.7; font-size:0.9rem; margin-top:2px; }}
    .badge {{ display:inline-block; font-size:0.66rem; font-weight:600; letter-spacing:0.08em; text-transform:uppercase;
              border:1px solid currentColor; padding:0 6px; margin-left:10px; vertical-align:3px; opacity:0.7; }}
    .badge.on {{ color:{RED}; border-color:{RED}; opacity:1; }}

    /* Calendar: a month per block, Monday first; each day links to its menu */
    .cal-month {{ font-size:0.78rem; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; margin:20px 0 6px; }}
    .cal {{ display:grid; grid-template-columns:repeat(7, minmax(0, 1fr)); gap:3px; }}
    .cal .hd {{ font-size:0.64rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; opacity:0.55; padding:0 4px 2px; }}
    .cal .day, .cal .empty {{ position:relative; display:block; min-height:56px; padding:4px 5px; min-width:0;
                              border-top:2px solid rgba(128,128,128,0.3); background:rgba(128,128,128,0.06); }}
    .cal .day[tabindex] {{ cursor:pointer; outline:none; }}
    .cal .empty {{ background:transparent; border-top-color:transparent; }}
    .cal .n {{ font-size:0.7rem; opacity:0.6; }}
    .cal .k {{ font-size:0.8rem; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .cal .d {{ font-size:0.72rem; opacity:0.75; white-space:nowrap; }}
    .cal .s {{ font-size:0.62rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .cal .day.rest .k {{ font-weight:400; opacity:0.4; }}
    .cal .day.hard {{ border-top-color:{RED}; }}
    .cal .day.hard .k {{ color:{RED}; }}
    .cal .day.race {{ background:{RED}; color:{PAPER}; border-top-color:{RED}; }}
    .cal .day.done {{ background:rgba(128,128,128,0.2); }}
    .cal .day.missed .s {{ color:{RED}; }}
    .cal .day.today {{ box-shadow:inset 0 0 0 2px {RED}; }}
    .cal .day.sel, .cal .day[tabindex]:focus {{ box-shadow:inset 0 0 0 2px currentColor; }}
    .cal .day.outside {{ opacity:0.3; }}
    /* The day's menu: shown on hover (mouse) or when the day is tapped (focus) */
    .cal .pop {{ display:none; position:absolute; top:calc(100% + 4px); left:0; z-index:20; width:290px;
                 background:rgb(20,20,20); color:{PAPER}; padding:12px 14px; box-shadow:0 6px 24px rgba(0,0,0,0.25);
                 font-size:0.82rem; line-height:1.4; cursor:default; }}
    .cal .day.mid .pop {{ left:50%; transform:translateX(-50%); }}
    .cal .day.end .pop {{ left:auto; right:0; }}
    .cal .day:hover .pop, .cal .day:focus .pop, .cal .day:focus-within .pop {{ display:block; }}
    /* With a mouse, a click on the day opens it; on a touch screen a tap shows the menu first. */
    .cal .day a.go {{ display:none; position:absolute; inset:0; z-index:1; }}
    @media (hover:hover) and (pointer:fine) {{ .cal .day a.go {{ display:block; }} }}
    .review {{ border-top:3px solid currentColor; padding-top:10px; margin:8px 0 18px; }}
    .review .verdict {{ font-size:1.35rem; font-weight:700; margin:10px 0 4px; }}
    .review .verdict.bad {{ color:{RED}; }}
    .review ul {{ margin:8px 0 0 1.1rem; padding:0; }}
    .review li {{ margin:4px 0; }}
    .review table {{ width:100%; border-collapse:collapse; margin-top:14px; font-size:0.9rem; }}
    .review td {{ padding:6px 8px 6px 0; border:0 !important; border-top:1px solid rgba(128,128,128,0.3) !important;
                  background:transparent !important; }}
    .review td:first-child {{ opacity:0.7; width:45%; }}
    .splits {{ margin:0 0 18px; }}
    .splits table {{ width:100%; border-collapse:collapse; margin-top:6px; font-size:0.9rem;
                     font-variant-numeric:tabular-nums; }}
    .splits th {{ text-align:left; font-weight:600; opacity:0.7; padding:4px 8px 4px 0;
                  border:0 !important; background:transparent !important; }}
    .splits td {{ padding:5px 8px 5px 0; border:0 !important; border-top:1px solid rgba(128,128,128,0.3) !important;
                  background:transparent !important; }}
    .splits td:nth-child(4) {{ width:38%; }}
    .splits .bar {{ display:block; height:4px; margin-top:3px; border-radius:2px; background:currentColor;
                    opacity:0.35; }}
    .splits .bar.hard {{ background:{RED}; opacity:1; }}
    .splits .hint {{ font-size:0.8rem; opacity:0.65; margin-top:6px; }}
    .pop .t {{ font-weight:700; font-size:0.9rem; }}
    .pop .m {{ opacity:0.75; margin-bottom:8px; }}
    .pop table {{ width:100%; border-collapse:collapse; margin:4px 0 6px; }}
    .pop td {{ padding:4px 8px 4px 0; border-top:1px solid rgba(238,235,227,0.15); vertical-align:top; }}
    .pop td + td {{ white-space:nowrap; text-align:right; padding-right:0; }}
    .pop .o {{ opacity:0.65; }}
    .pop table, .pop tr, .pop td {{ border-left:0 !important; border-right:0 !important; border-bottom:0 !important;
                                    background:transparent !important; }}
    .pop table {{ border-top:0 !important; }}
    .pop td.h {{ color:{RED}; font-weight:600; }}
    .pop .x {{ opacity:0.8; margin-top:4px; white-space:normal; }}
    .pop a {{ color:{RED} !important; font-weight:600; text-decoration:none !important; display:inline-block; margin-top:6px; }}
    /* On a phone the menu is a sheet along the bottom of the screen. */
    @media (max-width:640px) {{ .cal .day, .cal .empty {{ min-height:48px; padding:3px; }} .cal .k {{ font-size:0.7rem; }}
        .cal .pop, .cal .day.mid .pop, .cal .day.end .pop {{ position:fixed; top:auto; bottom:12px; left:12px; right:12px;
                                                             width:auto; transform:none; font-size:0.9rem; padding:14px 16px; }} }}

    /* Progress bar and glance cards */
    .bar {{ height:8px; background:rgba(128,128,128,0.2); border-radius:4px; overflow:hidden; margin:6px 0 2px; }}
    .bar span {{ display:block; height:100%; background:currentColor; }}
    .glance {{ border:1px solid rgba(128,128,128,0.3); border-radius:12px; padding:12px 14px; height:100%; }}
    .glance .value {{ font-size:1.5rem; font-weight:700; margin:4px 0; }}
    .glance .value.red {{ color:{RED}; }}
    .glance .caption {{ font-size:0.86rem; opacity:0.7; }}
    .level {{ display:inline-block; font-size:0.7rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase;
              border:1px solid currentColor; padding:0 6px; margin-right:8px; }}
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
    .js-plotly-plot [style*="stroke: rgb(0, 0, 0)"] {{ stroke:currentColor !important; }}
    </style>""")


# ---------- wording: the planner's data in the chosen language ----------

def pace_range(step):
    return f"{format_pace(step.pace_fast_s)}–{format_pace(step.pace_slow_s)}"


def kind_name(kind, short=False):
    return t(("short " if short else "kind ") + kind)


def week_type(plan):
    return t("week " + plan["week_type"])


def rest_reason(day, race_name=""):
    """Why a day is a rest day (or a race), from the planner's data."""
    info = getattr(day, "info", {}) or {}
    why = info.get("rest")
    if day.kind == "race":
        return t("race day", name=escape(race_name))
    if why == "before plan":
        return t("rest before plan")
    if why == "post race":
        return t("rest post race", day=info["day"])
    if why == "after hard":
        return t("rest after " + info["after"])
    if why == "before race":
        return t("rest before race")
    return t("rest normal")


def metres(step):
    """'800' for an 800 m repeat."""
    return f"{1000 * step.distance_km:.0f}"


def today_stats(day):
    """The three numbers of today's run: distance, what to hold, time. [(value, unit, label, key)]"""
    reps = [s for s in day.steps if s.name == "interval"]
    main = next((s for s in day.steps if s.name in ("easy", "tempo")), day.steps[0])
    stats = [(f"{day.distance_km:g}", "km", t("stat distance"), False)]
    if reps:
        stats.append((pace_range(reps[0]), "/km", t("stat pace reps"), True))
    elif main.target == "pace":
        stats.append((pace_range(main), "/km", t("stat pace tempo"), True))
    else:
        stats.append((f"{main.hr_min}–{main.hr_max}", "bpm", t("stat hr"), True))
    stats.append((f"{day.minutes:.0f}", t("min short"), t("stat time"), False))
    return stats


def today_hint(day):
    """One line under the numbers: what the number means in practice."""
    reps = [s for s in day.steps if s.name == "interval"]
    main = next((s for s in day.steps if s.name in ("easy", "tempo")), day.steps[0])
    if reps:
        return t("hint interval", reps=len(reps), m=metres(reps[0]))
    if main.name == "tempo":
        return t("hint tempo", km=f"{main.distance_km:g}")
    return t("hint hr", fast=format_pace(main.pace_fast_s), slow=format_pace(main.pace_slow_s))


def profile(day):
    """The run drawn as bars as long as each step; hard parts in red."""
    bars = "".join(
        f"<span class='{'hard' if s.name in ('tempo', 'interval', 'race pace') else 'main' if s.name == 'easy' else ''}'"
        f" style='flex:{s.distance_km}'></span>" for s in day.steps)
    names, seen = [], []
    for s in day.steps:   # repeats are shown once: "6 × 800 m"
        if s.name in ("interval", "recovery"):
            if s.name == "interval" and "interval" not in seen:
                names.append(f"{sum(x.name == 'interval' for x in day.steps)} × {metres(s)} m")
            seen.append(s.name)
            continue
        names.append(f"{t('step ' + s.name)} {s.distance_km:g} km")
    return f"<div class='profile'>{bars}</div><div class='sequence'>{'  →  '.join(names)}</div>"


def extra_lines(day):
    info = getattr(day, "info", {}) or {}
    lines = []
    if info.get("strides"):
        lines.append(t("strides"))
    if info.get("sharpener"):
        lines.append(t("sharpener"))
    if info.get("second"):
        lines.append(t("second hard"))
    if info.get("finish_km"):
        pace = next((s for s in day.steps if s.name == "race pace"), None)
        if pace:
            lines.append(t("finish", km=f"{info['finish_km']:g}",
                           pace=format_pace((pace.pace_fast_s + pace.pace_slow_s) / 2)))
    if info.get("fuel_min") or day.minutes > 60:
        lines.append(t("fuel"))
    return lines


def step_note(step, day, index, total_reps):
    """'How' for one step of the menu."""
    hard = day.kind in HARD
    if step.name == "warm-up":
        return t("note warm-up strides") if hard else t("note warm-up", hr=step.hr_max)
    if step.name == "easy":
        text = t("note easy long" if day.kind == "long" else "note easy", hr=step.hr_max)
        return text + (" " + t("strides") if (getattr(day, "info", {}) or {}).get("strides") else "")
    if step.name == "interval":
        sharpener = (getattr(day, "info", {}) or {}).get("sharpener")
        return t("note sharpen" if sharpener else "note interval", i=index, n=total_reps)
    return t("note " + step.name)


def steps_table(day):
    reps = [s for s in day.steps if s.name == "interval"]
    rows, rep = [], 0
    for s in day.steps:
        rep += s.name == "interval"
        rows.append({
            t("col step"): t("step " + s.name),
            "km": s.distance_km,
            t("col hr"): f"{s.hr_min}-{s.hr_max}",
            t("col pace"): f"{pace_range(s)} /km",
            t("col time"): f"~{s.minutes:.0f} min",
            t("col how"): step_note(s, day, rep, len(reps)),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def window_text(conditions, hours):
    """'19-21: drizzle, 26°C, rain 92%' plus an air warning, in the chosen language."""
    if not conditions:
        return "", None
    sky = t.get("sky " + conditions["weather"])
    text = t("weather at", start=f"{hours[0]:02d}", end=f"{hours[1]:02d}", sky=f"{sky}, " if sky else "",
             temp=f"{conditions['air_temp_c']:.0f}", rain=f"{conditions['rain_chance_pct']:.0f}")
    aqi = conditions["us_aqi"]
    warning = None
    if aqi is not None and aqi > 150:
        warning = t("air bad", aqi=f"{aqi:.0f}")
    elif aqi is not None and aqi > 100:
        warning = t("air sensitive", aqi=f"{aqi:.0f}")
    return text, warning


def week_reason(plan):
    """Plain-language 'why' for a week, from its type and numbers."""
    ctx = plan["context"]
    kind = plan["week_type"]
    if kind == "recovery":
        lines = [t("why recovery", days=ctx["days_since_race"], easy=recovery_days(ctx.get("last_race_km")))]
    elif kind == "fix easy":
        lines = [t("why fix easy", pct=f"{ctx['easy_pct']:.0f}", hr=EASY_HR_MAX)]
    elif kind == "build" and plan.get("second_quality"):
        lines = [t("why build two"), t("sessions grow")]
    elif kind == "build" and (plan.get("goal") or {}).get("every_other"):
        lines = [t("why build goal"), t("sessions grow")]
    else:
        lines = [t("why " + kind)] + ([t("sessions grow")] if kind == "build" else [])
    n = plan["n_runs"]
    lines.append(t("why runs full", n=n) if n >= RUNS_PER_WEEK else t("why runs", n=n, target=RUNS_PER_WEEK))
    if plan["long_km"]:
        lines.append(t("why long", km=f"{plan['long_km']:g}"))
    return lines


def check_message(check):
    """A plain sentence for a check that is not simply 'ok', or None."""
    key, v, level = check.get("key"), check.get("values", {}), check["level"]
    if level == "pass" or (level == "info" and not v.get("no_recent_runs")):
        return None
    if key == "weekly 10%":
        return t("check weekly 10%", planned=f"{v['planned_km']:.1f}", limit=f"{v['limit_km']:.1f}")
    if key == "two-week 30%":
        return t("check two-week none") if v.get("no_recent_runs") else \
            t("check two-week 30%", change=f"{100 * v['change']:.0f}")
    if key == "long run step":
        return t("check long run step", long=f"{v['long_km']:g}", longest=f"{v['longest_km']:.1f}")
    if key == "load spike":
        return t("check load spike", ratio=f"{v['ratio']:.1f}", usual=f"{v['usual_km']:.0f}")
    if key in ("hard after race", "post-race rest"):
        return t("check " + key, days=v.get("days", RECOVERY_DAYS if key == "hard after race" else POST_RACE_REST_DAYS))
    if key == "rising weeks":
        return t("check " + key)
    return escape(f"{check['rule']} - {check['detail']}")   # a plan saved before checks had keys


def evaluation_text(ev):
    return t("eval", actual=f"{ev['actual_km']:.1f}", planned=f"{ev['planned_km']:.1f}", runs=ev["actual_runs"],
             planned_runs=ev["planned_runs"], long=t("eval long done" if ev["long_done"] else "eval long missed"),
             easy="" if ev["easy_pct"] is None else t("eval easy", pct=f"{ev['easy_pct']:.0f}"))


def technical(plan):
    """The planner's own English notes and sources, below a rule (it sits inside an expander)."""
    st.markdown("---")
    st.caption(t("technical"))
    st.markdown(f"{plan['why']}  \n*Source: {plan['why_sources']}*")
    if plan.get("goal_note"):
        st.markdown(plan["goal_note"])
    if plan.get("pace_note"):
        st.caption(plan["pace_note"])


def render_day(day, race_name=""):
    """One day: rest or race with its reason, or the run with its menu."""
    if day.kind in ("rest", "race"):
        html(f"**{t.date(day.day)} · {kind_name(day.kind)}**  \n<span class='muted'>{rest_reason(day, race_name)}</span>")
        return
    with st.container(border=True):
        st.markdown(f"**{t.date(day.day)} · {kind_name(day.kind)} · {day.distance_km:g} km · "
                    f"{t('about min', min=f'{day.minutes:.0f}')}**")
        for line in extra_lines(day):
            st.caption(line)
        steps_table(day)


def render_days(plan, race_name=""):
    """Every day of a week, with its menu."""
    if plan.get("frozen"):
        st.caption(t("frozen", when=t.date(plan["saved_at"])))
    for day in plan["days"]:
        render_day(day, race_name)


def language_setting(lang):
    """Add a language choice to Streamlit's own Settings dialog (⋮ → Settings).

    Streamlit has no way to add options there, so a small script watches the
    page and inserts a select into the dialog whenever it opens, styled like
    the dialog's own controls. Choosing a language reloads the page with
    ?lang=... in the address. If a Streamlit update changes the dialog, the
    choice simply does not appear; ?lang=en in the address still works.
    """
    options = "".join(f'<option value="{code}"{" selected" if code == lang else ""}>{name}</option>'
                      for code, name in LANGUAGES.items())
    chevron = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8'>"
               "<path d='M1 1l5 5 5-5' fill='none' stroke='black' stroke-width='1.6'/></svg>\")")
    # The script is moved into the page itself: a component's own frame may not reload the page.
    script = """
    (() => {
      if (window.__runLanguage) return;
      window.__runLanguage = true;
      const leaf = (root, text) => [...root.querySelectorAll('*')].find(e => e.children.length === 0 && e.textContent.trim() === text);
      const add = () => {
        const dialog = [...document.querySelectorAll('[role=dialog]')].find(d => leaf(d, 'Appearance'));
        if (!dialog || dialog.querySelector('#run-language')) return;
        // Copy the look of the dialog's own section title, label and theme select.
        const title = leaf(dialog, 'Appearance');
        const label = [...dialog.querySelectorAll('*')].find(e => e.children.length === 0 && /^Choose app theme/.test(e.textContent.trim()));
        const select = dialog.querySelector('[data-baseweb=select] > div');
        const look = select ? getComputedStyle(select) : null;
        const box = document.createElement('div');
        box.id = 'run-language';
        box.style.marginTop = '1.5rem';
        const heading = title.cloneNode(true);
        heading.textContent = 'Language / Bahasa';
        const text = label ? label.cloneNode(true) : document.createElement('div');
        text.textContent = 'Choose the language of this app';
        text.style.marginTop = '0.5rem';
        const choice = document.createElement('select');
        choice.innerHTML = `OPTIONS`;
        Object.assign(choice.style, {
          display: 'block', width: '100%', boxSizing: 'border-box', marginTop: '0.25rem',
          height: look ? look.height : '2.5rem', padding: '0 2.25rem 0 0.75rem',
          font: 'inherit', fontSize: '1rem', color: 'inherit', cursor: 'pointer',
          border: 'none', borderRadius: look ? look.borderRadius : '0.5rem',
          backgroundColor: look ? look.backgroundColor : 'rgba(128,128,128,0.15)',
          backgroundImage: CHEVRON, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 0.85rem center',
          appearance: 'none', webkitAppearance: 'none',
        });
        choice.onchange = () => {
          const url = new URL(location.href);
          url.searchParams.set('lang', choice.value);
          location.href = url.toString();
        };
        box.append(heading, text, choice);
        (label ? label.closest('[data-testid], div').parentElement.parentElement : title.parentElement).append(box);
      };
      new MutationObserver(add).observe(document.body, {childList: true, subtree: true});
    })();
    """.replace("OPTIONS", options).replace("CHEVRON", repr(chevron))
    components.html(f"""<script>
    const s = window.parent.document.createElement('script');
    s.textContent = {script!r};
    window.parent.document.head.append(s);
    </script>""", height=0)


def sidebar_weather():
    """Weather for your city in the sidebar: now, the next hours, your run time."""
    with st.sidebar:
        st.subheader(t("weather title", city=HOME_CITY))
        if st.button(t("refresh"), use_container_width=True):
            load_forecast(FORECAST_CACHE, HOME_CITY, force=True)
            get_forecast.clear()
            get_air_now.clear()
            st.rerun()
        if forecast is None:
            st.caption(t("forecast none"))
        else:
            now = pd.Timestamp.now()
            hours = next_hours(forecast, now)
            current = hours.iloc[0]
            aqi_now = air_now["us_aqi"] if air_now else current["us_aqi"]
            c1, c2 = st.columns(2)
            c1.metric(t("now"), f"{current['air_temp_c']:.0f}°C")
            c2.metric("AQI", "-" if pd.isna(aqi_now) else f"{aqi_now:.0f}")
            if not pd.isna(aqi_now):
                st.caption(f"{t.get('sky ' + current['weather'])} · {t('aqi ' + aqi_label(aqi_now))}")
            if air_now:
                note(t("air now", aqi=f"{air_now['us_aqi']:.0f}", label=t("aqi " + aqi_label(air_now["us_aqi"])),
                       station=escape(air_now["station"]), time=f"{air_now['time']:%H:%M}"))
            st.markdown(f"**{t('next hours')}**")
            st.dataframe(pd.DataFrame({
                t("col time"): hours["time"].dt.strftime("%H:%M"),
                t("col sky"): hours["weather"].map(lambda w: t.get("sky " + w, w)),
                "°C": hours["air_temp_c"].round(0).astype(int),
                t("col rain"): hours["rain_chance_pct"].map(lambda p: f"{p:.0f}%"),
                "AQI": hours["us_aqi"].map(lambda a: "-" if pd.isna(a) else f"{a:.0f}"),
            }), hide_index=True, use_container_width=True)
            # Your run window: today if it has not passed yet, otherwise tomorrow.
            run_day = now.date() if now.hour <= RUN_HOURS[1] else (now + pd.Timedelta(days=1)).date()
            text, warning = window_text(window_conditions(forecast, run_day, RUN_HOURS), RUN_HOURS)
            if text:
                title = "run time today" if run_day == now.date() else "run time tomorrow"
                st.markdown(f"**{t(title, start=f'{RUN_HOURS[0]:02d}', end=f'{RUN_HOURS[1]:02d}')}**")
                st.caption(text)
                if warning:
                    note(warning, accent=True)
            st.caption(t("forecast updated", time=f"{fetched_at(FORECAST_CACHE):%H:%M}"))


# ---------- page ----------

st.set_page_config(page_title="Running Training Analyzer", layout="wide", initial_sidebar_state="auto")

# Language: chosen in Streamlit's own menu (⋮ → Settings, see language_setting) and kept
# in the address (?lang=en), so a reload or a home-screen shortcut keeps it.
lang = st.query_params.get("lang", "id")
lang = lang if lang in LANGUAGES else "id"
t = Text(lang)
state = st.session_state
page_css()
language_setting(lang)
st.title("Running Training Analyzer")
st.caption(t("tagline"))

# Data: Garmin Connect through the Personal API (with GARMIN_API_KEY in .env), or a CSV export.
GARMIN = "garmin"
csv_files = sorted(p for p in DATA_DIR.glob("*.csv") if p.name not in ("weather_cache.csv", "forecast_cache.csv"))
sources = ([GARMIN] if api_key(ROOT) else []) + csv_files
if not sources:
    note(t("no data", folder=DATA_DIR), accent=True)
    st.stop()
with st.sidebar:
    source = st.selectbox(t("data source"), sources,
                          format_func=lambda s: t("garmin source") if s == GARMIN else s.name)
from_api = source == GARMIN
s1, s2 = st.columns([4, 1.3], vertical_alignment="center")
if from_api:
    last_sync = synced_at(DATA_DIR)
    stale = last_sync is None or pd.Timestamp.now() - last_sync > pd.Timedelta(hours=SYNC_HOURS)
    if s2.button(t("sync now"), use_container_width=True) or stale:
        sync_garmin()
        last_sync = synced_at(DATA_DIR)
    days_left = key_days_left(ROOT)
    if days_left is not None and days_left <= KEY_WARN_DAYS:
        note(t("key expired") if days_left < 0 else t("key expires", days=days_left), accent=True)
    if last_sync is None:
        st.stop()
    with st.spinner(t("reading runs")):
        runs = load_api(str(last_sync))
    covered = covered_until(last_sync)
    s1.caption(t("synced", when=f"{t.date(last_sync)} {last_sync:%H:%M}", runs=len(runs),
                 since=t.month(runs["start_time"].min())))
else:
    runs = load(str(source))
    covered = covered_until_from_file(source)

today = pd.Timestamp.now().date()
known = runs[runs["start_time"] < pd.Timestamp(covered) + pd.Timedelta(days=1)]
gain = weekly_fitness_gain(known)
race_names = list(race_list(runs))
race_a, race_b = ([None] + race_names)[-2:] if race_names else (None, None)

# Weather (sidebar, and the run-time line on today's card).
air_now = get_air_now()
forecast = get_forecast()
if forecast is not None:
    forecast = combine_air(forecast, air_now)

runs_by_day = runs.groupby(runs["start_time"].dt.date)
data_key = str(last_sync) if from_api else f"{source}:{Path(source).stat().st_mtime}"
page = st.query_params.get("page", "today")


def plan_stage(runs, start, n_weeks, goal, plans_dir):
    """n_weeks of plan from `start` for `goal`."""
    current = max(0, (pd.Timestamp(today) - programs.monday_of(start)).days // 7)
    return build_month_plan(runs, covered, plan_start=start, today=today, weeks_ahead=n_weeks - current,
                            goal_race=goal, plans_dir=plans_dir)


@st.cache_data(show_spinner=False)
def plan_program(program_json, data_key, today, covered, _runs):
    """A program's plan from its start to its race (cached until new data or a change to it).

    With a milestone: stage 1 up to final_start, then (once passed) stage 2, numbered on.
    Each week gets its "stage" (None, 1 or 2).
    """
    program = json.loads(program_json)
    stage = programs.stage(program)
    if stage is None:
        weeks = plan_stage(_runs, program["start_date"], programs.week_count(program), programs.goal(program),
                           programs.plans_dir(DATA_DIR, program))
        return [{**w, "stage": None} for w in weeks]
    first = (pd.Timestamp(programs.final_start(program)) - programs.monday_of(program["start_date"])).days // 7
    if stage == "stopped":
        first = program["milestone"]["weeks"]
    weeks = [{**w, "stage": 1} for w in plan_stage(_runs, program["start_date"], first, programs.milestone_goal(program),
                                                   programs.plans_dir(DATA_DIR, program))]
    if stage == "final":
        final = plan_stage(_runs, programs.final_start(program).isoformat(), programs.week_count(program) - first,
                           programs.goal(program), programs.plans_dir(DATA_DIR, program, final=True))
        weeks += [{**w, "number": w["number"] + first, "stage": 2} for w in final]
    return weeks


def program_plan(program):
    return plan_program(json.dumps(program, sort_keys=True), data_key, today, covered, runs)


def link(text, **params):
    """A link within the app that keeps the language."""
    query = "&".join(f"{k}={v}" for k, v in {**params, "lang": lang}.items() if v is not None)
    return f"<a href='?{query}' target='_self'>{text}</a>"


def milestone_label(program):
    """'5K test sub 0:33:34'"""
    m = program["milestone"]
    return t("milestone label", dist=t("dist " + distance_name(m["distance_km"])), target=m["target_time"])


def race_name(program, day):
    """What a race day in the program is: the milestone test in stage 1, else the program's race."""
    if programs.stage(program) and day < programs.final_start(program):
        return milestone_label(program)
    return program["name"]


def program_line(program):
    """'Half marathon · sub 2:40:00 · race 12 Apr 2027 · from 28 Oct'"""
    parts = [t("dist " + distance_name(program["distance_km"]))]
    if program.get("target_time"):
        parts.append(f"sub {program['target_time']}")
    if programs.stage(program) in ("milestone", "stopped"):
        parts.append(t("after milestone", label=milestone_label(program)))
    if program.get("race_date"):
        parts.append(t("race on", date=t.date(pd.Timestamp(program["race_date"]), weekday=False)))
    else:
        parts.append(t("n weeks", n=programs.week_count(program)))
    parts.append(t("from date", date=t.date(pd.Timestamp(program["start_date"]), weekday=False)))
    return " · ".join(parts)


def week_of(program, weeks):
    """'Week 3 of 24', or the program's state when it is not running."""
    state_now = programs.status(program, today)
    if state_now != "running":
        return t("program " + state_now)
    week = current_week(weeks)
    text = t("week of", n=week["number"], total=programs.week_count(program))
    return f"{t('stage n', n=week['stage'])} · {text}" if week.get("stage") else text


def milestone_box(program, where, weeks):
    """Where a program with a milestone stands, its latest check-in, and the choice after a missed test."""
    stage = programs.stage(program)
    if stage is None:
        return
    m = program["milestone"]
    final = t("dist " + distance_name(program["distance_km"])) + \
        (f" sub {program['target_time']}" if program.get("target_time") else "")
    if stage == "stopped":
        note(t("milestone stopped", date=t.date(pd.Timestamp(m["gave_up"]), weekday=False)))
        return
    if stage == "final":
        passed = m["passed"]
        note(t("milestone passed", label=milestone_label(program), time=format_duration(passed["time_s"]),
               km=f"{passed['distance_km']:g}", date=t.date(pd.Timestamp(passed["date"]), weekday=False),
               final=final))
        return
    target_s = parse_time(m["target_time"])
    lines = [t("milestone now", label=milestone_label(program), pace=format_pace(target_s / m["distance_km"]),
               date=t.date(pd.Timestamp(programs.test_date(program)), weekday=False), final=final),
             t("milestone rule", dist=t("dist " + distance_name(m["distance_km"])))]
    if m.get("missed"):
        lines.append(t("milestone tries", n=len(m["missed"])))
    if not programs.test_missed(program, covered):
        note("<br>".join(lines))
        check_in_box(program, [w for w in weeks if w.get("stage") == 1], where)
        return
    note(t("milestone missed", label=milestone_label(program),
           date=t.date(pd.Timestamp(programs.test_date(program)), weekday=False), weeks=programs.REPEAT_WEEKS),
         accent=True)
    b1, b2, _ = st.columns([1.4, 1, 2])
    if b1.button(t("milestone repeat", weeks=programs.REPEAT_WEEKS), type="primary", key=f"{where}-repeat",
                 use_container_width=True):
        programs.repeat_milestone(DATA_DIR, store, program["id"], today)
        st.rerun()
    if b2.button(t("milestone give up"), key=f"{where}-give-up", use_container_width=True):
        programs.give_up(DATA_DIR, store, program["id"], today)
        st.rerun()


def check_in_box(program, weeks, where):
    """The newest check-in of stage 1 (src/analysis/checkpoint.py) and, when behind, the choice."""
    c = checkpoint.latest(weeks, known, programs.test_week(program))
    if c is None:
        return
    ok = c["checks"]

    def line(key, text):
        """'ok · runs: 5 of 5 done (own rule)': the verdict, the numbers and where the limit comes from."""
        sources = ", ".join(t("own rule") if k == "own" else SOURCES[k]["cite"].split(",")[0]
                            for k in checkpoint.CHECK_SOURCES[key])
        return f"<b>{t('check ok' if ok[key] else 'check short')}</b> · {text} <span class='muted'>({sources})</span>"

    lines = [t("check in title", start=t.date(pd.Timestamp(c["start"]), weekday=False),
               end=t.date(pd.Timestamp(c["end"]), weekday=False)),
             line("runs", t("check in runs", done=c["actual_runs"], planned=c["planned_runs"])),
             line("long", t("check in long", done=c["long_done"], planned=c["long_planned"])),
             line("hard", t("check in hard", done=c["hard_done"], planned=c["hard_planned"]))]
    if c["easy_pct"] is not None:
        lines.append(line("easy", t("check in easy", pct=f"{c['easy_pct']:.0f}", min=checkpoint.EASY_PCT_MIN)))
    if c["efficiency_change"] is not None:
        lines.append(line("fitness", t("check in fitness", change=f"{100 * c['efficiency_change']:+.1f}",
                                       hr=EASY_HR_MAX, before=format_pace(c["easy_pace_before_s"]),
                                       now=format_pace(c["easy_pace_now_s"]))))
    choice = programs.check_in_choice(program, c["end"])
    if c["on_track"]:
        note("<br>".join(lines + [t("check in go")]))
        return
    if choice:
        note("<br>".join(lines + [t("check in chose " + choice, weeks=checkpoint.POSTPONE_WEEKS)]))
        return
    note("<br>".join(lines + [t("check in behind", weeks=checkpoint.POSTPONE_WEEKS)]), accent=True)
    b1, b2, _ = st.columns([1.4, 1.2, 2])
    if b1.button(t("check in postpone", weeks=checkpoint.POSTPONE_WEEKS), type="primary", key=f"{where}-postpone",
                 use_container_width=True):
        programs.answer_check_in(DATA_DIR, store, program["id"], c["end"], "postpone", checkpoint.POSTPONE_WEEKS)
        st.rerun()
    if b2.button(t("check in keep"), key=f"{where}-keep", use_container_width=True):
        programs.answer_check_in(DATA_DIR, store, program["id"], c["end"], "keep")
        st.rerun()


def goal_summary(goal, plan):
    """Plain-language lines: estimate, gap, time needed, load, what the target does in the plan."""
    gap = goal_gap(known, goal, gain, today) if goal.get("target_time") else None
    if not gap:
        if plan.get("peak_km"):
            note(t("no target peak", peak=plan["peak_km"]))
        else:
            st.caption(t("pick target"))
        return None
    peak = goal.get("peak_km") or peak_km(goal["distance_km"], parse_time(goal["target_time"]))
    lines = [t("estimate now", est=format_duration(gap["estimate_now_s"]), dist=t("dist " + distance_name(goal["distance_km"]))),
             t("gap", gap=format_duration(gap["gap_s"])) if gap["gap_s"] > 0 else t("gap none")]
    if gap["gap_s"] > 0:
        lines.append(t("trend flat") if gap["weeks_needed"] is None else
                     t("weeks needed", weeks=f"{gap['weeks_needed']:.0f}"))
    if gap["race_date"] is not None:
        lines.append(t("by date", date=t.date(gap["race_date"], weekday=False), weeks=f"{gap['weeks_to_race']:.0f}",
                       est=format_duration(gap["estimate_race_s"]), pct=f"{100 * gap['gain_needed']:.1f}",
                       verdict=t("realistic" if gap["gain_needed"] <= REALISTIC_GAIN else "ambitious")))
    lines.append(t("build to", peak=peak))
    g = plan.get("goal")
    if g:
        status = g["status"]
        if status == "too fast":
            lines.append(t("goal too fast", pace=format_pace(g["pace_s"]), tempo=format_pace(g["tempo_limit_s"])))
        elif status == "already beats":
            lines.append(t("goal beats"))
        elif status == "within easy":
            lines.append(t("goal within easy", pace=format_pace(g["pace_s"]), dist=f"{goal['distance_km']:g}",
                           long=f"{g['long_max_km']:g}"))
        elif g.get("every_other"):
            lines.append(t("goal finish alt", km=f"{g['finish_km']:g}", pace=format_pace(g["pace_s"]),
                           max=f"{RACE_PACE_MAX_KM:g}"))
        else:
            lines.append(t("goal finish", km=f"{g['finish_km']:g}", pace=format_pace(g["pace_s"])))
        if g.get("session_paces"):
            paces = g["session_paces"]
            lines.append(t("session paces interval", interval=format_pace(paces["interval"])) if g.get("every_other")
                         else t("session paces", tempo=format_pace(paces["tempo"]), interval=format_pace(paces["interval"])))
    note("<br>".join(lines), accent=gap["race_date"] is not None and gap["gain_needed"] > REALISTIC_GAIN)
    return peak


def load_chart(weeks, peak):
    """Weekly distance: the 8 weeks before the plan as run, then the plan (planned and run)."""
    weekly_km = runs.groupby(runs["start_time"].dt.to_period("W-SUN"))["distance_km"].sum()
    first_plan = weeks[0]["start"].to_period("W-SUN")
    history = weekly_km[(weekly_km.index < first_plan)].tail(8)
    plan_weeks = [w["start"].to_period("W-SUN") for w in weeks]
    x_hist = [p.start_time for p in history.index]
    x_plan = [p.start_time for p in plan_weeks]
    actual_plan = [weekly_km.get(p, 0.0) if w["start"].date() <= today else None for p, w in zip(plan_weeks, weeks)]
    planned = [sum(x.distance_km for x in w["plan"]["workouts"]) for w in weeks]
    fig = go.Figure()
    fig.add_bar(x=x_plan, y=planned, name=t("planned"), marker=dict(color="rgba(0,0,0,0)", line=dict(color=INK, width=1.5)),
                hovertemplate="%{x|%d %b}: %{y:.1f} km<extra>" + t("planned") + "</extra>")
    fig.add_bar(x=x_hist + x_plan, y=list(history.values) + actual_plan, name=t("actual"), marker_color=INK,
                hovertemplate="%{x|%d %b}: %{y:.1f} km<extra>" + t("actual") + "</extra>")
    if peak:
        fig.add_hline(y=peak, line=dict(color=RED, width=2, dash="dash"),
                      annotation=dict(text=f"{t('peak line')} {peak} km", font=dict(color=RED, size=12),
                                      xanchor="left", x=0))
    fig.update_layout(barmode="overlay", bargap=0.3, barcornerradius=4)
    ticks = (x_hist + x_plan)[::max(2, len(x_hist + x_plan) // 10)]
    fig.update_xaxes(tickvals=ticks, ticktext=[t.date(x, weekday=False) for x in ticks])
    st.markdown(f"**{t('load chart')}**")
    chart(fig, t("km per week"), height=300)


def weeks_table(weeks):
    staged = any(w.get("stage") for w in weeks)
    st.dataframe(pd.DataFrame([{
        t("col week"): w["number"],
        **({t("col stage"): w.get("stage")} if staged else {}),
        t("col dates"): f"{t.date(w['start'], weekday=False)} - {t.date(w['end'], weekday=False)}",
        t("col type"): week_type(w["plan"]),
        "km": sum(x.distance_km for x in w["plan"]["workouts"]),
        t("col long"): w["plan"]["long_km"],
        t("col runs"): len(w["plan"]["workouts"]),
        t("col status"): t("status " + w["status"]),
        t("col result"): evaluation_text(w["evaluation"]) if w["evaluation"] else "",
    } for w in weeks]), hide_index=True, use_container_width=True)


def calendar(program, weeks, selected):
    """The program month by month, Monday first. Each day shows its menu on hover or tap."""
    days = {d.day: d for w in weeks for d in w["plan"]["days"]}
    first, last = min(days), max(days)
    month = pd.Timestamp(first).to_period("M")
    blocks = []
    while month <= pd.Timestamp(last).to_period("M"):
        start = month.start_time.date()
        cells = [f"<div class='hd'>{t.day(pd.Timestamp('2024-01-01') + pd.Timedelta(days=i))}</div>" for i in range(7)]
        # Only the Monday-Sunday rows that have program days; other days of the month are blank.
        monday = start - pd.Timedelta(days=start.weekday())
        end = month.end_time.date()
        while monday <= end:
            row = [monday + pd.Timedelta(days=i) for i in range(7)]
            if any(d in days for d in row):
                cells += [day_cell(program, days, d, selected) if d.month == month.month and d in days else
                          f"<div class='day outside'><div class='n'>{d.day}</div></div>" if d.month == month.month else
                          "<div class='empty'></div>" for d in row]
            monday += pd.Timedelta(weeks=1)
        blocks.append(f"<div class='cal-month'>{t.month(month)}</div><div class='cal'>{''.join(cells)}</div>")
        month += 1
    html("".join(blocks))


def day_cell(program, days, day, selected):
    """One calendar day: what to run, done or missed, today, selected."""
    plan_day = days[day]
    ran = runs_by_day.get_group(day) if day in runs_by_day.groups else None
    is_run = plan_day.kind not in ("rest", "race")
    classes = ["day", plan_day.kind if plan_day.kind in ("rest", "race") else "run"]
    if plan_day.kind in HARD or (plan_day.kind == "long" and plan_day.is_hard):
        classes.append("hard")
    status = ""
    if ran is not None:
        classes.append("done")
        status = f"{ran['distance_km'].sum():.1f} km"
    elif is_run and day < today and day <= covered:
        classes.append("missed")
        status = t("state missed")
    if day == today:
        classes.append("today")
    if day == selected:
        classes.append("sel")
    classes.append("mid" if day.weekday() in (2, 3) else "end" if day.weekday() >= 4 else "start")
    km = f"{plan_day.distance_km:g} km" if is_run else "&nbsp;"
    href = f"?page=programs&program={program['id']}&day={day.isoformat()}&lang={lang}"
    return (f"<div class='{' '.join(classes)}' tabindex='0'><a class='go' href='{href}' target='_self'></a>"
            f"<div class='n'>{day.day}</div>"
            f"<div class='k'>{kind_name(plan_day.kind, short=True)}</div><div class='d'>{km}</div>"
            f"<div class='s'>{status}</div>{day_popup(plan_day, ran, href, race_name(program, day))}</div>")


def day_popup(day, ran, href, race_name):
    """The day's menu in a few lines: time, what to hold, warm-up / main / cool-down."""
    parts = [f"<div class='t'>{t.date(day.day, long=True)} · {kind_name(day.kind)}</div>"]
    if day.kind in ("rest", "race"):
        parts.append(f"<div class='x'>{rest_reason(day, race_name)}</div>")
    else:
        parts.append(f"<div class='m'>{day.distance_km:g} km · {t('about min', min=f'{day.minutes:.0f}')}</div>")
        rows, reps = [], [s for s in day.steps if s.name == "interval"]
        for s in day.steps:
            if s.name == "recovery":
                continue
            if s.name == "interval":
                if s is reps[0]:
                    rows.append((f"{len(reps)} × {metres(s)} m", True, pace_range(s), f"{s.hr_min}–{s.hr_max}"))
                    rows.append((f"{t('step recovery')} {len(reps) - 1} × 400 m", False, "", ""))
                continue
            hard = s.name in ("tempo", "race pace")
            rows.append((f"{t('step ' + s.name)} {s.distance_km:g} km", hard, pace_range(s), f"{s.hr_min}–{s.hr_max}"))
        parts.append("<table>" + "".join(
            f"<tr><td class='{'h' if hard else ''}'>{name}</td>"
            f"<td>{pace + ' /km' if pace else ''}{'<br><span class=o>' + hr + ' bpm</span>' if hr else ''}</td></tr>"
            for name, hard, pace, hr in rows) + "</table>")
        parts += [f"<div class='x'>{line}</div>" for line in extra_lines(day)]
    if ran is not None:
        km = ran["distance_km"].sum()
        pace = format_pace(ran["moving_time_s"].sum() / km) if km else "-"
        hr = f"{ran['avg_hr'].mean():.0f}"
        parts.append(f"<div class='x'><b>{t('you ran', km=f'{km:.1f}', pace=pace, hr=hr)}</b></div>")
    parts.append(f"<a href='{href}' target='_self'>{t('analysis link' if ran is not None else 'full menu')} →</a>")
    return f"<div class='pop'>{''.join(parts)}</div>"


def run_analysis(run, day):
    """One run in full: the numbers, an overall verdict and what they mean against the menu."""
    r = review(run, day, runs)
    pace = run["avg_pace_s_per_km"]
    stats = [(f"{run['distance_km']:.2f}", "km", t("stat distance")),
             (format_duration(run["moving_time_s"]), "", t("stat moving")),
             (format_pace(pace) if pd.notna(pace) else "-", "/km", t("stat pace")),
             (f"{run['avg_hr']:.0f}" if pd.notna(run["avg_hr"]) else "-", "bpm", t("stat avg hr"))]
    share = r["easy_share"]
    lines = []
    if r["distance"] == "unplanned":
        lines.append(t("dist unplanned"))
    elif r["distance"]:
        lines.append(t("dist " + r["distance"], km=f"{r['km']:.1f}", plan=f"{r['planned_km']:g}"))
    if r["intensity"] == "hard session":
        lines.append(t("int hard session", avg=f"{run['avg_hr']:.0f}"))
    elif r["intensity"]:
        lines.append(t("int " + r["intensity"], pct=f"{100 * share:.0f}", hr=r["hr_limit"], avg=f"{run['avg_hr']:.0f}"))
    if r["pace_vs_plan"]:
        lines.append(t("pace " + r["pace_vs_plan"], pace=format_pace(pace), fast=format_pace(r["plan_pace"][0]),
                       slow=format_pace(r["plan_pace"][1])))
    if pd.notna(run.get("heat_slowdown_pct")) and pd.notna(run.get("air_temp_c")):
        lines.append(t("heat review", temp=f"{run['air_temp_c']:.0f}", dew=f"{run['dew_point_c']:.0f}",
                       pct=f"{run['heat_slowdown_pct']:.0f}", adj=format_pace(run["heat_adj_pace_s"])))
    if r["efficiency_verdict"]:
        lines.append(t("eff " + r["efficiency_verdict"], chg=f"{100 * abs(r['efficiency_change']):.0f}"))
    overall = ("too hard" if r["intensity"] == "too hard" else "short" if r["distance"] == "short"
               else "extra" if r["distance"] == "unplanned" else
               "good" if r["distance"] in ("as planned", "long") and r["intensity"] in ("easy", "hard session") else "ok")

    slower = t("slower by", pct=f"{run['heat_slowdown_pct']:.0f}") if pd.notna(run.get("heat_slowdown_pct")) else ""
    rows = [(t("row max hr"), f"{run['max_hr']:.0f} bpm" if pd.notna(run.get("max_hr")) else "-"),
            (t("row easy time"), f"{format_duration(share * run['moving_time_s'])} ({100 * share:.0f}%)"
             if share is not None else "-"),
            (t("row heat adj"), f"{format_pace(run['heat_adj_pace_s'])} /km" if pd.notna(run.get("heat_adj_pace_s")) else "-"),
            (t("row gap"), f"{format_pace(run['avg_gap_s_per_km'])} /km" if pd.notna(run.get("avg_gap_s_per_km")) else "-"),
            (t("row cadence"), f"{run['avg_cadence']:.0f} spm" if pd.notna(run.get("avg_cadence")) else "-"),
            (t("row ascent"), f"{run['ascent_m']:.0f} m" if pd.notna(run.get("ascent_m")) else "-"),
            (t("row te"), f"{run['aerobic_te']:.1f}" if pd.notna(run.get("aerobic_te")) else "-"),
            (t("row weather"), f"{run['air_temp_c']:.0f}°C · {t('dew')} {run['dew_point_c']:.0f}°C · {slower}"
             if pd.notna(run.get("air_temp_c")) else "-"),
            (t("row efficiency"), f"{r['efficiency']:.3f}" + (f" ({t('usual short')} {r['efficiency_base']:.3f})"
                                                              if r["efficiency_base"] else "") if r["efficiency"] else "-"),
            (t("row calories"), f"{run['calories']:.0f} kcal" if pd.notna(run.get("calories")) else "-")]
    stats_html = "".join(f"<div class='stat'><div class='v'>{v}<small>{u}</small></div><div class='l'>{l}</div></div>"
                         for v, u, l in stats)
    html(f"<div class='review'><div class='eyebrow'>{t('run analysis')} · {escape(run['title'])} · "
         f"{run['start_time']:%H:%M}</div><div class='stats'>{stats_html}</div>"
         f"<div class='verdict{' bad' if overall == 'too hard' else ''}'>{t('overall ' + overall)}</div>"
         f"<ul>{''.join(f'<li>{line}</li>' for line in lines)}</ul>"
         f"<table>{''.join(f'<tr><td>{a}</td><td>{b}</td></tr>' for a, b in rows)}</table></div>")
    split_table(run)


def split_table(run):
    """Per-km distance, time, pace and heart rate from the run's activity file, with a pace bar."""
    fit_file = run.get("fit_file")
    path = DATA_DIR / ACTIVITY_DIR / str(fit_file)
    if pd.isna(fit_file) or not path.exists():
        st.caption(t("no splits"))
        return
    table = load_splits(path)
    if table.empty:
        st.caption(t("no splits"))
        return
    fastest, slowest = table["pace_s"].min(), table["pace_s"].max()
    rows = []
    for split in table.itertuples():
        hard = pd.notna(split.avg_hr) and split.avg_hr > EASY_HR_MAX
        # A longer bar is a slower kilometre: the fastest gets 30%, the slowest 100%.
        width = 100 if slowest == fastest else 30 + 70 * (split.pace_s - fastest) / (slowest - fastest)
        rows.append(f"<tr><td>{split.km}</td><td>{split.distance_km:.2f}</td><td>{format_pace(split.time_s) if split.time_s < 3600 else format_duration(split.time_s)}</td>"
                    f"<td>{format_pace(split.pace_s)}<span class='bar{' hard' if hard else ''}' "
                    f"style='width:{width:.0f}%'></span></td>"
                    f"<td>{f'{split.avg_hr:.0f}' if pd.notna(split.avg_hr) else '-'}</td></tr>")
    head = "".join(f"<th>{t(k)}</th>" for k in ("split km", "split dist", "split time", "split pace", "split hr"))
    html(f"<div class='splits'><div class='eyebrow'>{t('splits')}</div>"
         f"<table><tr>{head}</tr>{''.join(rows)}</table>"
         f"<div class='hint'>{t('split note', hr=EASY_HR_MAX)}</div></div>")


def goal_inputs(prefix, program=None):
    """Distance, target, race date, start and length widgets for a new or an edited program.

    Fixed keys, seeded once from the program (a changing default would reset the choice).
    Returns the chosen values.
    """
    base = program or {"distance_km": 21.1, "target_time": None, "race_date": None,
                       "start_date": today.isoformat(), "weeks": programs.DEFAULT_WEEKS}
    key = lambda name: f"{prefix}-{name}"
    c1, c2 = st.columns(2)
    state.setdefault(key("distance"), distance_name(base["distance_km"]))
    distance = c1.selectbox(t("distance"), list(DISTANCES), key=key("distance"), format_func=lambda d: t("dist " + d))
    distance_km = DISTANCES[distance]
    estimate = goal_gap(known, {"distance_km": distance_km, "target_time": None, "date": None}, gain, today)
    target_time = None
    if estimate:
        options = [None] + [round(x) for x, _ in target_options(estimate["estimate_now_s"], distance_km, gain)]
        if state.get(key("target"), "unset") not in options:   # first time, or the distance changed
            saved = round(parse_time(base["target_time"])) if base.get("target_time") else None
            state[key("target")] = saved if abs(base["distance_km"] - distance_km) < 0.1 and saved in options else None
        choice = c2.selectbox(t("target"), options, key=key("target"),
                              format_func=lambda x: t("no target") if x is None else
                              f"sub {format_duration(x)} · {format_pace(x / distance_km)}/km")
        target_time = format_duration(choice) if choice else None
        c2.caption(t("estimate today", est=format_duration(estimate["estimate_now_s"])))
    else:
        c2.caption(t("mark a race"))
    milestone = milestone_input(key, program, distance_km, target_time)
    c3, c4 = st.columns(2)
    state.setdefault(key("start"), pd.Timestamp(base["start_date"]).date())
    start = c3.date_input(t("start date"), key=key("start"))
    state.setdefault(key("has date"), bool(base.get("race_date")))
    has_date = c4.checkbox(t("has date"), key=key("has date"))
    race_date, weeks = None, base.get("weeks") or programs.DEFAULT_WEEKS
    if has_date:
        saved = pd.Timestamp(base["race_date"]).date() if base.get("race_date") else start + pd.Timedelta(weeks=16)
        state.setdefault(key("race"), saved)
        race_date = c4.date_input(t("race date"), min_value=start, key=key("race"))
    elif milestone:   # its own widget: one that changes label and limits loses its value
        state.setdefault(key("final weeks"), weeks if (program or {}).get("milestone") else
                         programs.final_weeks(distance_km))
        weeks = c4.number_input(t("final weeks"), min_value=1, max_value=40, step=1, key=key("final weeks"))
    else:
        state.setdefault(key("weeks"), weeks)
        weeks = c4.number_input(t("length weeks"), min_value=4, max_value=40, step=1, key=key("weeks"))
    return {"distance": distance, "distance_km": distance_km, "target_time": target_time,
            "race_date": race_date.isoformat() if race_date else None, "start_date": start.isoformat(),
            "weeks": int(weeks), "milestone": milestone}


def milestone_input(key, program, distance_km, target_time):
    """The milestone checkbox and its length, for a goal with a target; returns the milestone or None.

    An edited program keeps its milestone's progress (passed, missed tests) while
    the distance and target stay the same.
    """
    milestone_km = programs.milestone_distance(distance_km)
    if not target_time or milestone_km is None:
        return None
    estimate = goal_gap(known, {"distance_km": milestone_km, "target_time": None, "date": None}, gain, today)
    suggested = programs.suggest_milestone(distance_km, target_time, estimate and estimate["estimate_now_s"])
    saved = (program or {}).get("milestone")
    same = saved and saved["distance_km"] == suggested["distance_km"] and saved["target_time"] == suggested["target_time"]
    state.setdefault(key("milestone"), bool(saved) if program else True)
    m1, m2 = st.columns(2)
    if not m1.checkbox(t("use milestone", dist=t("dist " + distance_name(milestone_km))), key=key("milestone")):
        return None
    state.setdefault(key("milestone weeks"), saved["weeks"] if same else suggested["weeks"])
    weeks = m2.number_input(t("milestone weeks"), min_value=1, max_value=40, step=1, key=key("milestone weeks"))
    target_s = parse_time(suggested["target_time"])
    hint = t("milestone hint", dist=t("dist " + distance_name(milestone_km)), target=suggested["target_time"],
             pace=format_pace(target_s / milestone_km))
    if estimate:
        hint += " " + t("milestone estimate", est=format_duration(estimate["estimate_now_s"]),
                        weeks=f"{weeks_needed(estimate['estimate_now_s'], target_s, REALISTIC_GAIN) or 0:.0f}",
                        gain=f"{100 * REALISTIC_GAIN:g}")
    m1.caption(hint)
    return {**(saved if same else {}), **suggested, "weeks": int(weeks)}


def default_name(values):
    name = t("dist " + values["distance"])
    return f"{name} sub {values['target_time']}" if values["target_time"] else name


def programs_page():
    chosen = programs.find(store, st.query_params.get("program") or "")
    if chosen:
        program_detail(chosen)
        return
    st.subheader(t("programs title"))
    if not store["programs"]:
        st.caption(t("no programs"))
    for program in reversed(store["programs"]):
        weeks = program_plan(program)
        badge = (f"<span class='badge on'>{t('active')}</span>" if program["id"] == store.get("active")
                 else f"<span class='badge'>{t('program ' + programs.status(program, today))}</span>")
        html(f"<div class='program'><div class='name'>{link(escape(program['name']), page='programs', program=program['id'])}"
             f"{badge}</div><div class='meta'>{program_line(program)} · {week_of(program, weeks)}</div>"
             f"<div style='margin-top:6px'>{link(t('open program') + ' →', page='programs', program=program['id']).replace('<a ', '<a class=more ')}</div></div>")
    st.markdown("&nbsp;")
    with st.expander(t("new program"), expanded=not store["programs"]):
        values = goal_inputs("new")
        name = st.text_input(t("program name"), placeholder=default_name(values), key="new-name")
        make_active = st.checkbox(t("make active"), value=True, key="new-active")
        if st.button(t("save program"), type="primary"):
            program = programs.new_program(name.strip() or default_name(values), values["distance_km"],
                                           values["target_time"], values["race_date"], values["start_date"],
                                           values["weeks"], values["milestone"])
            programs.add(DATA_DIR, store, program, make_active)
            st.query_params.update({"page": "programs", "program": program["id"]})
            st.rerun()


def program_detail(program):
    is_active = program["id"] == store.get("active")
    weeks = program_plan(program)
    html(link("← " + t("all programs"), page="programs").replace("<a ", "<a class=more "))
    badge = (f"<span class='badge on'>{t('active')}</span>" if is_active
             else f"<span class='badge'>{t('program ' + programs.status(program, today))}</span>")
    html(f"<div class='program'><div class='name'>{escape(program['name'])}{badge}</div>"
         f"<div class='meta'>{program_line(program)} · {week_of(program, weeks)}</div></div>")
    a1, _ = st.columns([1, 3])
    if not is_active and a1.button(t("make active now"), use_container_width=True):
        store["active"] = program["id"]
        programs.save(DATA_DIR, store)
        st.rerun()

    milestone_box(program, "detail", weeks)
    if not programs.test_missed(program, covered):   # until you choose, the old test date means nothing
        goal_summary(programs.current_goal(program), current_week(weeks)["plan"])

    st.markdown(f"### {t('calendar')}")
    st.caption(t("calendar hint"))
    selected = st.query_params.get("day")
    selected = pd.Timestamp(selected).date() if selected else None
    calendar(program, weeks, selected)
    day = next((d for w in weeks for d in w["plan"]["days"] if d.day == selected), None) if selected else None
    st.markdown(f"### {t('day menu')}")
    if day is None:
        st.caption(t("pick a day"))
    else:
        ran = runs_by_day.get_group(selected) if selected in runs_by_day.groups else None
        if ran is not None:
            for _, run in ran.iterrows():
                run_analysis(run, day)
            st.markdown(f"**{t('planned menu')}**")
        render_day(day, race_name(program, day.day))

    st.markdown(f"### {t('all weeks')}")
    weeks_table(weeks)
    peak = peak_km(program["distance_km"], parse_time(program["target_time"])) if program.get("target_time") else None
    load_chart(weeks, peak)

    with st.expander(t("edit program")):
        values = goal_inputs(f"edit-{program['id']}", program)
        name = st.text_input(t("program name"), value=program["name"], key=f"edit-{program['id']}-name")
        st.caption(t("edit note"))
        if st.button(t("save changes"), type="primary"):
            programs.update(DATA_DIR, store, program["id"], name=name.strip() or program["name"],
                            distance_km=values["distance_km"], target_time=values["target_time"],
                            race_date=values["race_date"], start_date=values["start_date"], weeks=values["weeks"],
                            milestone=values["milestone"])
            st.rerun()
    with st.expander(t("delete program")):
        sure = st.checkbox(t("delete sure"), key=f"delete-{program['id']}")
        if st.button(t("delete now"), disabled=not sure):
            programs.remove(DATA_DIR, store, program["id"])
            st.query_params.clear()
            st.query_params.update({"page": "programs", "lang": lang})
            st.rerun()


# ---- programs: what you train for (data/programs.json); the active one plans the home page ----
store = programs.migrate(DATA_DIR, load_goal(), PLAN_START)   # the first time, your old goal becomes a program
for p in store["programs"]:   # a race that passes a milestone moves its program to stage 2
    if programs.stage(p) == "milestone" and (passed := programs.find_pass(p, known)):
        programs.update(DATA_DIR, store, p["id"], milestone={**p["milestone"], "passed": passed})
program = programs.active(store)
html("<div class='nav'>" + "".join(
    link(t("nav " + key), page=key).replace("<a ", f"<a class='{'on' if page == key else ''}' ")
    for key in ("today", "programs")) + "</div>")
sidebar_weather()
if page == "programs":
    programs_page()
    st.stop()

# Home: the active program. Without one (or once it has ended) a plan with no target, from today.
if program and programs.is_live(program, today):
    goal = programs.current_goal(program)
    if programs.stage(program) == "milestone":
        goal = {**goal, "name": milestone_label(program)}
    weeks = program_plan(program)
else:
    goal = {**GOAL_RACE, "target_time": None, "date": None}
    weeks = build_month_plan(runs, covered, plan_start=today, today=today, goal_race=goal)
this_week = current_week(weeks)
plan = this_week["plan"]
ctx = plan["context"]
current_index = weeks.index(this_week)

# The page in reading order.
today_slot = st.container()
week_slot = st.container()
goal_slot = st.container()
next_slot = st.container()
safety_slot = st.container()
glance_slot = st.container()
deep_slot = st.container()

# ---- 3. the active program and its goal ----
with goal_slot:
    st.subheader(t("active program"))
    planned_now = sum(w.distance_km for w in plan["workouts"])
    if program and programs.is_live(program, today):
        html(f"<div class='program'><div class='name'>{escape(program['name'])}</div>"
             f"<div class='meta'>{program_line(program)} · {week_of(program, weeks)}</div>"
             f"<div style='margin-top:6px'>{link(t('open program') + ' →', page='programs', program=program['id']).replace('<a ', '<a class=more ')}</div></div>")
        milestone_box(program, "home", weeks)
    else:
        note(t("no active program") + " " + link(t("make program") + " →", page="programs").replace("<a ", "<a class=more "))
    missed = program and programs.is_live(program, today) and programs.test_missed(program, covered)
    peak = None if missed else goal_summary(goal, plan)
    if peak:
        share = min(1.0, planned_now / peak)
        html(f"<div class='bar'><span style='width:{100 * share:.0f}%'></span></div>"
             f"<div class='muted' style='font-size:0.85rem'>{t('progress', now=f'{planned_now:g}', peak=peak)}</div>")
    load_chart(weeks[:current_index + 5], peak)

# ---- 1. today ----
with today_slot:
    today_day = next((d for d in plan["days"] if d.day == today), None)
    done = runs_by_day.get_group(today) if today in runs_by_day.groups else None
    is_run = today_day is not None and today_day.kind not in ("rest", "race")
    parts = [f"<div class='top'><span class='date'>{t.date(today, long=True)}</span>"
             f"<span class='phase'>{t('week n', n=this_week['number'])} · {week_type(plan)}</span></div>"]
    if not is_run:
        kind = today_day.kind if today_day else "rest"
        parts.append(f"<div class='rest'>{kind_name(kind)}</div>")
        if today_day:
            parts.append(f"<div class='hint'>{rest_reason(today_day, goal.get('name') or '')}</div>")
        upcoming = next((d for d in plan["days"] if d.day > today and d.kind not in ("rest", "race")), None) \
            or next((d for w in weeks if w["start"].date() > today for d in w["plan"]["days"]
                     if d.kind not in ("rest", "race")), None)
        if upcoming:
            parts.append(f"<div class='hint muted'>{t('next up', day=t.date(upcoming.day), kind=kind_name(upcoming.kind), km=f'{upcoming.distance_km:g}')}</div>")
    else:
        stats = "".join(f"<div class='stat{' key' if key else ''}'><div class='v'>{value}<small>{unit}</small></div>"
                        f"<div class='l'>{label}</div></div>" for value, unit, label, key in today_stats(today_day))
        parts += [f"<div class='kind'>{kind_name(today_day.kind)}</div>", f"<div class='stats'>{stats}</div>",
                  profile(today_day), f"<div class='hint muted'>{today_hint(today_day)}</div>"]
        parts += [f"<div class='hint'>{line}</div>" for line in extra_lines(today_day)]
    below = []
    if done is not None:
        below.append(f"<div><b>{t('done today', km=f'{done['distance_km'].sum():.1f}', hr=f'{done['avg_hr'].mean():.0f}')}</b></div>")
    if forecast is not None and is_run:
        text, warning = window_text(window_conditions(forecast, today, RUN_HOURS), RUN_HOURS)
        if text:
            when, _, rest = text.partition(": ")
            below.append(f"<div><span class='when'>{when}</span>{rest}</div>")
        if warning:
            below.append(f"<div class='alert'>{warning}</div>")
    if below:
        parts.append(f"<div class='conditions'>{''.join(below)}</div>")
    html(f"<div class='today'>{''.join(parts)}</div>")

    with st.expander(t("why")):
        st.markdown("\n".join(f"- {line}" for line in week_reason(plan)))
        technical(plan)

# ---- 2. this week ----
with week_slot:
    planned_runs = plan["workouts"]
    st.subheader(t("this week"))
    st.caption(t("week summary", km=f"{planned_now:g}", n=len(planned_runs), long=f"{plan['long_km']:g}"))
    tiles = []
    for day in plan["days"]:
        ran = runs_by_day.get_group(day.day) if day.day in runs_by_day.groups else None
        classes, status = ["tile"], ""
        is_run = day.kind not in ("rest", "race")
        if not is_run:
            classes.append("rest")
        if day.kind in HARD:
            classes.append("hard")
        if ran is not None:
            classes.append("done")
            status = t("state done") if is_run else t("state extra")
        elif is_run and day.day < today and day.day <= covered:
            classes.append("missed")
            status = t("state missed")
        if day.day == today:
            classes.append("today")
            status = status or t("state today")
        km = f"{ran['distance_km'].sum():.1f} km" if ran is not None else (f"{day.distance_km:g} km" if is_run else "&nbsp;")
        tiles.append(f"<div class='{' '.join(classes)}'><div class='dn'>{t.day(day.day)} {day.day.day}</div>"
                     f"<div class='dk'>{kind_name(day.kind, short=True)}</div><div class='dd'>{km}</div>"
                     f"<div class='ds'>{status}</div></div>")
    html(f"<div class='week'>{''.join(tiles)}</div>")
    with st.expander(t("day menus")):
        render_days(plan, goal.get("name") or "")
    if ctx["empty_weeks"]:
        note(t("no runs weeks", weeks=", ".join(ctx["empty_weeks"])), accent=True)

# ---- 4. coming weeks ----
with next_slot:
    st.subheader(t("coming weeks"))
    st.caption(t("coming note"))
    nearby = weeks[max(0, current_index - 1):current_index + 5]   # last week, this week and 4 ahead
    weeks_table(nearby)
    for w in nearby:
        if w is this_week:
            continue
        p = w["plan"]
        label = (f"{t('week n', n=w['number'])} · {t.date(w['start'], weekday=False)} · {week_type(p)} · "
                 f"{sum(x.distance_km for x in p['workouts']):g} km · {t('status ' + w['status'])}")
        with st.expander(label):
            if w["evaluation"]:
                note(evaluation_text(w["evaluation"]))
            st.markdown("\n".join(f"- {line}" for line in week_reason(p)))
            render_days(p, goal.get("name") or "")

# ---- 5. safety ----
with safety_slot:
    messages = [(c["level"], m) for c in plan["checks"] if (m := check_message(c))]
    if messages:
        st.subheader(t("safety watch", k=len(messages)))
        for level, message in messages:
            html(f"<div class='note{' accent' if level == 'high' else ''}'><span class='level {level}'>"
                 f"{t('level ' + level)}</span>{message}</div>")
    else:
        st.subheader(t("safety ok", n=len(plan["checks"])))
    with st.expander(t("safety details")):
        for check in plan["checks"]:
            level = check["level"]
            html(f"<span class='level {level}'>{t('level ' + level)}</span>**{escape(check['rule'])}** - "
                 f"{escape(check['detail'])}<br><span class='muted'>{escape(check['formula'])}<br>"
                 f"Source: {escape(check['sources'])}</span>")
        st.markdown("---")
        for s in plan["hr_settings"]:
            html(f"**{s['setting']}** - {s['evidence']}  \n<span class='muted'>Source: {escape(s['sources'])}</span>")

# ---- 6. at a glance ----
training = training_runs_with_efficiency(runs)
monthly = monthly_summary(training)
weekly = weekly_check(runs)
total_easy_pct = 100 * weekly["easy_time_s"].sum() / weekly["moving_time_s"].sum()
first_month, last_month = monthly.iloc[0], monthly.iloc[-1]


def glance(column, label, value, caption, red=False):
    column.markdown(f"<div class='glance'><div class='eyebrow'>{label}</div>"
                    f"<div class='value{' red' if red else ''}'>{value}</div>"
                    f"<div class='caption'>{caption}</div></div>", unsafe_allow_html=True)


with glance_slot:
    st.subheader(t("at a glance"))
    c1, c2, c3 = st.columns(3)
    if race_b:
        last_race = runs[runs["start_time"] == pd.Timestamp(race_list(runs)[race_b]["start"])].iloc[0]
        caption = t("race pace", pace=format_pace(last_race["avg_pace_s_per_km"]))
        if race_a:
            before = runs[runs["start_time"] == pd.Timestamp(race_list(runs)[race_a]["start"])].iloc[0]
            if abs(before["distance_km"] - last_race["distance_km"]) < 1:   # same distance: compare times
                change = before["duration_s"] - last_race["duration_s"]
                caption += " · " + t("faster than" if change > 0 else "slower than",
                                     diff=format_duration(abs(change)), race=escape(race_a))
        glance(c1, f"{t('last race')} · {escape(race_b)}", format_duration(last_race["duration_s"]), caption)
    else:
        glance(c1, t("last race"), t("no race yet"), t("mark race hint"))
    pace_change = last_month["pace_at_ref_hr_s"] - first_month["pace_at_ref_hr_s"]   # negative = faster
    month0 = t.month(monthly.index[0])
    glance(c2, t("fitness"), t("fitness value", pace=format_pace(last_month["pace_at_ref_hr_s"]), hr=REFERENCE_HR),
           t("fitness change", s=f"{abs(pace_change):.0f}", month=month0) if pace_change < 0 else
           t("fitness change slower", s=f"{abs(pace_change):.0f}", month=month0))
    low_easy = total_easy_pct < TARGET_EASY_PCT - 5
    glance(c3, t("easy share"), t("easy value", pct=f"{total_easy_pct:.0f}"),
           t("easy low", hr=EASY_HR_MAX) if low_easy else t("easy ok"), red=low_easy)

# ---- 7. go deeper ----
with deep_slot:
    st.subheader(t("go deeper"))
    tab_pm, tab_fit, tab_easy, tab_heat = st.tabs([t("tab races"), t("tab fitness"), t("tab easy"), t("tab heat")])

with tab_pm:
    st.markdown(f"**{t('pm title')}**")
    if race_a is None:
        note(t("pm needs two"))
    else:
        st.dataframe(race_rows(runs, race_a, race_b).rename(columns={
            "race": "race", "date": t("col date"), "distance_km": "km", "time": t("col time"), "pace": "pace",
            "avg_hr": t("col avg hr"), "efficiency": t.metric("efficiency")}), hide_index=True, use_container_width=True)
        st.markdown(f"**{t('pm training', weeks=COMPARE_WEEKS)}**")
        table = compare_races(runs, race_a, race_b)
        labels = {label: key for key, (label, _, _) in METRICS.items()}
        table["metric"] = table["metric"].map(lambda label: t.metric(labels[label]) if label in labels else label)
        st.dataframe(table.drop(columns="how"), hide_index=True, use_container_width=True)
    how([t("pm how", weeks=COMPARE_WEEKS)])

with tab_fit:
    st.markdown(f"**{t('fit title')}**")
    # A "median" of 1-2 runs is just those runs, so leave such months off the line.
    solid = monthly[monthly["runs"] >= 3]
    month_mid = solid.index.to_timestamp() + pd.Timedelta(days=14)
    fig = go.Figure()
    fig.add_scatter(
        x=training["start_time"], y=training["pace_at_ref_hr_s"], mode="markers", name=t("fit each"),
        marker=dict(size=9, color=INK, opacity=0.35, line=dict(width=0)),
        customdata=list(zip(training["title"], training["avg_pace_s_per_km"].map(format_pace),
                            training["avg_hr"].astype(int), training["pace_at_ref_hr_s"].map(format_pace))),
        hovertemplate="%{x|%d %b}  %{customdata[0]}<br>%{customdata[1]}/km @ %{customdata[2]} bpm"
                      f"<br>@ {REFERENCE_HR} bpm: %{{customdata[3]}}/km<extra></extra>",
    )
    fig.add_scatter(
        x=month_mid, y=solid["pace_at_ref_hr_s"], mode="lines+markers", name=t("fit month"),
        line=dict(width=2, color=RED), marker=dict(size=9, color=RED),
        customdata=list(zip(solid.index.astype(str), solid["pace_at_ref_hr_s"].map(format_pace), solid["runs"])),
        hovertemplate="%{customdata[0]}: %{customdata[1]}/km (%{customdata[2]})<extra></extra>",
    )
    pace_axis(fig, training["pace_at_ref_hr_s"])
    chart(fig, t("fit axis", hr=REFERENCE_HR))
    html(t("fit summary", first=format_pace(first_month["pace_at_ref_hr_s"]),
           last=format_pace(last_month["pace_at_ref_hr_s"]), hr=REFERENCE_HR))
    how([t("fit how", hr=REFERENCE_HR)])
    with st.expander(t("table")):
        table = monthly.copy()
        table["pace_at_ref_hr_s"] = table["pace_at_ref_hr_s"].map(format_pace)
        table.index = table.index.astype(str)
        st.dataframe(table.round(2), use_container_width=True)

with tab_easy:
    st.markdown(f"**{t('easy title')}**")
    week_starts = weekly.index.to_timestamp()   # Monday of each week
    easy_min = weekly["easy_time_s"] / 60
    hard_min = (weekly["moving_time_s"] - weekly["easy_time_s"]) / 60
    fig = go.Figure()
    fig.add_bar(x=week_starts, y=easy_min, name=t("easy bar", hr=EASY_HR_MAX), marker_color=INK,
                customdata=weekly["easy_pct"].round(0),
                hovertemplate="%{x|%d %b}<br>%{y:.0f} min (%{customdata:.0f}%)<extra></extra>")
    fig.add_bar(x=week_starts, y=hard_min, name=t("hard bar", hr=EASY_HR_MAX), marker_color=RED,
                hovertemplate="%{x|%d %b}<br>%{y:.0f} min<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.25, barcornerradius=4, legend_traceorder="normal")
    for week in week_starts[weekly["race_week"]]:
        fig.add_annotation(x=week, y=(weekly["moving_time_s"] / 60).max() * 1.08, text=t("race mark"),
                           showarrow=False, font=dict(color=MUTED, size=12))
    chart(fig, t("minutes week"))
    on_target = (weekly["verdict"] == "on target").sum()
    html(t("easy summary", pct=f"{total_easy_pct:.0f}", target=TARGET_EASY_PCT, on=on_target, n=len(weekly)))
    wrong = mislabelled_easy_runs(runs)
    st.markdown(f"**{t('wrong easy', n=len(wrong))}**")
    st.dataframe(pd.DataFrame({
        t("col date"): wrong["start_time"].dt.strftime("%Y-%m-%d"),
        t("col title"): wrong["title"],
        "km": wrong["distance_km"].round(1),
        t("col avg hr"): wrong["avg_hr"].astype(int),
        t("col above"): (wrong["avg_hr"] - EASY_HR_MAX).astype(int).astype(str) + " bpm",
    }), hide_index=True, use_container_width=True)
    how([t("easy how", hr=EASY_HR_MAX, max=MAX_HR)])

with tab_heat:
    st.markdown(f"**{t('heat title')}**")
    fig = go.Figure()
    fig.add_scatter(
        x=runs["start_time"], y=runs["heat_slowdown_pct"], mode="markers", name=t("heat series"),
        marker=dict(size=9, color=INK, line=dict(width=0)),
        customdata=list(zip(runs["title"], runs["air_temp_c"].round(1), runs["dew_point_c"].round(1),
                            runs["avg_pace_s_per_km"].map(format_pace), runs["heat_adj_pace_s"].map(format_pace))),
        hovertemplate="%{x|%d %b}  %{customdata[0]}<br>%{customdata[1]} °C, dew %{customdata[2]} °C"
                      "<br>-%{y:.1f}%<br>%{customdata[3]} → %{customdata[4]}/km<extra></extra>",
    )
    fig.update_yaxes(range=[0, 10], ticksuffix="%")
    chart(fig, t("heat axis"))
    heat_note = ""
    if race_a:
        heat = [runs.loc[runs["start_time"] == pd.Timestamp(race_list(runs)[n]["start"]), "heat_slowdown_pct"].iloc[0]
                for n in (race_a, race_b)]
        heat_note = t("heat similar" if abs(heat[1] - heat[0]) < 1 else "heat differed",
                      a=f"{heat[0]:.1f}", b=f"{heat[1]:.1f}")
    html(t("heat summary", median=f"{runs['heat_slowdown_pct'].median():.1f}",
           low=f"{runs['heat_slowdown_pct'].min():.1f}", high=f"{runs['heat_slowdown_pct'].max():.1f}") + heat_note)
    how([t("heat how"), "Table: " + ", ".join(f"{s} °F → {p}%" for s, p in SLOWDOWN_TABLE)])

