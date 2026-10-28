"""Running Training Analyzer dashboard.

Run from the project folder:
    streamlit run app/dashboard.py

This file only draws. Every number comes from src/analysis, so the
dashboard and the command-line reports always agree.
"""

import sys
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
from src.analysis.heat_adjust import SLOWDOWN_TABLE, load_runs_with_heat
from src.analysis.race_postmortem import compare_races, race_rows
from src.analysis.run_conditions import (
    WINDOWS, air_note, aqi_label, combine_air, day_conditions, describe_window, next_hours, window_conditions,
)
from src.config import (
    COMPARE_WEEKS, EASY_HR_MAX, HOME_CITY, MAX_HR, RACES, REFERENCE_HR, RUN_HOURS, TARGET_EASY_PCT,
)
from src.loaders.forecast_openmeteo import fetched_at, load_forecast
from src.loaders.iqair import load_current
from src.export.fit_workout import file_name, workout_fit_bytes
from src.planner.month_plan import build_month_plan, covered_until_from_file, current_week, describe_evaluation
from src.units import format_duration, format_pace

# Colours: validated for colour-blind safety on the light background.
BLUE = "#2a78d6"    # easy / main series
ORANGE = "#eb6834"  # hard / second series
MUTED = "#898781"   # axis labels, reference lines
GRID = "#e1e0d9"

DATA_DIR = ROOT / "data"


# ---------- data ----------

@st.cache_data
def load(csv_path):
    """Load once and keep in memory; Streamlit re-runs this file on every click."""
    return load_runs_with_heat(csv_path)


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
    """Thin, quiet chart chrome shared by every chart."""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis_title=y_title,
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def how(lines):
    """A 'How is this calculated?' box under each chart."""
    with st.expander("How is this calculated?"):
        st.markdown("\n".join(f"- {line}" for line in lines))


# ---------- page ----------

st.set_page_config(page_title="Running Training Analyzer", layout="wide", initial_sidebar_state="expanded")
st.title("Running Training Analyzer")
st.caption("Garmin records your runs. This explains your training.")

csv_files = sorted(p for p in DATA_DIR.glob("*.csv") if p.name != "weather_cache.csv")
if not csv_files:
    st.error(f"No Garmin CSV found in {DATA_DIR}. Export your activities and put the file there.")
    st.stop()
csv_path = st.selectbox("Data file", csv_files, format_func=lambda p: p.name)

runs = load(str(csv_path))
race_a, race_b = list(RACES)
races = race_rows(runs, race_a, race_b)
training = training_runs_with_efficiency(runs)
monthly = monthly_summary(training)
weekly = weekly_check(runs)

# Headline numbers
race_times = [runs.loc[runs["start_time"] == pd.Timestamp(RACES[n]["start"]), "duration_s"].iloc[0] for n in (race_a, race_b)]
first_month, last_month = monthly.iloc[0], monthly.iloc[-1]
total_easy_pct = 100 * weekly["easy_time_s"].sum() / weekly["moving_time_s"].sum()

c1, c2, c3 = st.columns(3)
# Comparisons go in a caption, not st.metric's delta: the delta always gets an
# up/down arrow, and "↑ target 80%" next to a low score reads as good news.
pace_change = last_month["pace_at_ref_hr_s"] - first_month["pace_at_ref_hr_s"]  # negative = faster
c1.metric(f"{race_b} time", format_duration(race_times[1]))
c1.caption(f"Race pace {races.iloc[1]['pace']}/km · {format_duration(race_times[0] - race_times[1])} "
           f"faster than {race_a}")
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

ICONS = {"pass": "✅ pass", "info": "ℹ️ note", "caution": "⚠️ caution", "high": "🛑 high"}
STATUS = {"done": "✅ done", "current": "▶️ this week", "needs data": "⏳ export needed", "upcoming": "upcoming"}
TITLES = {"easy": "Easy run", "long": "Long run", "tempo": "Tempo run", "interval": "Interval run"}


def render_week(plan):
    """One week's why, daily menu and safety checks."""
    st.info(f"{plan['why']}\n\n*Source: {plan['why_sources']}*")
    if plan.get("pace_note"):
        st.caption(plan["pace_note"])
    for day in plan["days"]:
        if day.kind == "rest":
            st.markdown(f"**{day.day:%a %d %b} · Rest**  \n"
                        f"<span style='color:{MUTED}'>{day.reason}</span>", unsafe_allow_html=True)
            continue
        with st.container(border=True):
            st.markdown(f"**{day.day:%a %d %b} · {TITLES[day.kind]} · "
                        f"{day.distance_km:g} km · ~{day.minutes:.0f} min**")
            st.caption(day.reason)
            if forecast is not None:
                conditions = day_conditions(forecast, day.day)
                lines = [describe_window(n, c) for n, c in conditions.items() if c]
                if lines:
                    note = air_note(conditions)
                    st.caption("🌤 Forecast (info only) - " + " · ".join(lines) + (f"  \n⚠️ {note}" if note else ""))
            st.dataframe(pd.DataFrame([{
                "step": s.name,
                "km": s.distance_km,
                "heart rate": f"{s.hr_min}-{s.hr_max} bpm",
                "pace": f"{format_pace(s.pace_fast_s)}-{format_pace(s.pace_slow_s)} /km",
                "time": f"~{s.minutes:.0f} min",
                "how": s.note,
            } for s in day.steps]), hide_index=True, use_container_width=True)
            st.download_button(f"⬇ Download {day.day:%a} workout (.fit)", workout_fit_bytes(day),
                               file_name=file_name(day), mime="application/octet-stream",
                               key=f"fit-{day.day}")

    st.markdown("**Safety checks**")
    for check in plan["checks"]:
        st.markdown(f"{ICONS[check['level']]} · **{check['rule']}** - {check['detail']}  \n"
                    f"<span style='color:{MUTED}'>{check['formula']}<br>Source: {check['sources']}</span>",
                    unsafe_allow_html=True)


# ---------- forecast sidebar ----------

with st.sidebar:
    st.subheader(f"🌤 {HOME_CITY} weather")
    if st.button("🔄 Refresh forecast", use_container_width=True):
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
        c1.metric(f"Now {current['icon']}", f"{current['air_temp_c']:.0f}°C")
        c2.metric("US AQI", "-" if pd.isna(aqi_now) else f"{aqi_now:.0f}")
        st.caption(f"{current['weather']} · dew point {current['dew_point_c']:.0f}°C · "
                   f"heat -{current['heat_slowdown_pct']:.0f}% · rain {current['rain_chance_pct']:.0f}%"
                   + ("" if pd.isna(aqi_now) else f" · air {aqi_label(aqi_now)}"))

        st.markdown("**Next hours**")
        st.dataframe(pd.DataFrame({
            "time": hours["time"].dt.strftime("%H:%M"),
            " ": hours["icon"],
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
            note = air_note({"run time": run})
            if note:
                st.warning(note)

        updated = fetched_at(FORECAST_CACHE)
        st.caption(f"Updated {updated:%H:%M} · Open-Meteo · info only, the plan does not change. "
                   "Air quality is a model estimate.")

with tab_plan:
    if air_now:
        st.info(f"🌫 Air right now: **AQI {air_now['us_aqi']:.0f} - {aqi_label(air_now['us_aqi'])}** "
                f"(measured by IQAir at {air_now['station']}, {air_now['time']:%H:%M})")
    else:
        st.caption("🌫 Measured air quality is off. Add a free IQAir key as IQAIR_API_KEY=... in a .env file "
                   "in the project folder to see the real-time AQI and correct the forecast with it.")
    covered = covered_until_from_file(csv_path)
    weeks = build_month_plan(runs, covered)
    plan = current_week(weeks)["plan"]
    ctx = plan["context"]

    st.subheader(f"Training plan from {weeks[0]['start']:%a %d %b %Y}")
    st.caption(f"Your data covers runs up to {covered:%a %d %b}. Export a new Garmin CSV at the end of each "
               "week: that week is evaluated and the following weeks are re-planned. Frequency first: one "
               "5 km run is added each week until you reach your target; the long run holds until then, "
               "then grows 1 km a week. Paces are estimates in your usual heat - follow heart rate, not "
               "pace. Not medical advice.")

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

    with st.expander(f"🌤 Weather & air quality forecast - {HOME_CITY} (info only)"):
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
                st.success(f"Evaluation: {describe_evaluation(w['evaluation'])}")
            elif w["status"] == "upcoming":
                st.caption("Provisional - recalculated when the weeks before it have real data.")
            render_week(p)

    with st.expander("Heart-rate settings - why these numbers?"):
        for s in plan["hr_settings"]:
            st.markdown(f"**{s['setting']}** - {s['evidence']}  \n"
                        f"<span style='color:{MUTED}'>Source: {s['sources']}</span>", unsafe_allow_html=True)

    if ctx["empty_weeks"]:
        st.warning(f"No runs recorded in week(s) of {', '.join(ctx['empty_weeks'])} - counted as 0 km. "
                   "If you ran, export your Garmin CSV again.")
    how([
        f"Based on the 4 weeks before {ctx['plan_start']:%d %b}: {ctx['baseline_km']:.1f} km/week, "
        f"{ctx['runs_per_week']:.1f} runs/week, longest training run {ctx['longest_recent_km']:.1f} km, "
        f"{ctx['easy_pct']:.0f}% easy.",
        "Week type, first rule that matches: race in the last 14 days → recovery (easy, no extra distance); "
        "easy time under 50% → hold distance, all easy; injury in the last 12 months → hold distance, "
        "one tempo run; otherwise → +10% distance and one tempo run.",
        "Runs per week: one 5 km run is added each week (not in recovery weeks, and only if at most one "
        "run was missed last week) until RUNS_PER_WEEK in config.py. A run is not added if it would put "
        "the week more than 30% above the last 7 days (Nielsen 2014).",
        "Long run: starts from your recent longest run and never goes down. It holds while runs are being "
        "added, then +1 km a week when last week's long run reached 90% of plan; max 21 km.",
        "Future weeks assume planned runs are done as planned, until real data replaces them.",
        "Paces: this week's come from the median efficiency of your last 4 weeks of real runs. Future weeks "
        "add your own recent fitness gain per week (straight-line trend of efficiency, max 1%/week). Each "
        "new export recalculates them from real data - if you get fitter faster, paces speed up faster.",
        "Pace guide = 1000 ÷ (recent efficiency × HR) - your efficiency already includes the usual heat.",
    ])

# ---------- race post-mortem ----------

with tab_pm:
    st.subheader("What changed between the two races?")
    st.dataframe(races, hide_index=True, use_container_width=True)
    st.markdown(f"**Training in the {COMPARE_WEEKS} weeks before each race**")
    st.dataframe(compare_races(runs, race_a, race_b), hide_index=True, use_container_width=True)
    how([
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
        marker=dict(size=9, color=BLUE, opacity=0.45, line=dict(width=2, color="#fcfcfb")),
        customdata=list(zip(training["title"], training["avg_pace_s_per_km"].map(format_pace),
                            training["avg_hr"].astype(int), training["pace_at_ref_hr_s"].map(format_pace))),
        hovertemplate="%{x|%d %b}  %{customdata[0]}<br>actual %{customdata[1]}/km @ %{customdata[2]} bpm"
                      f"<br>@ {REFERENCE_HR} bpm: %{{customdata[3]}}/km<extra></extra>",
    )
    fig.add_scatter(
        x=month_mid, y=solid["pace_at_ref_hr_s"], mode="lines+markers", name="Monthly median (3+ runs)",
        line=dict(width=2, color=BLUE), marker=dict(size=9, color=BLUE),
        customdata=list(zip(solid.index.astype(str), solid["pace_at_ref_hr_s"].map(format_pace), solid["runs"])),
        hovertemplate="%{customdata[0]}: %{customdata[1]}/km (%{customdata[2]} runs)<extra></extra>",
    )
    pace_axis(fig, training["pace_at_ref_hr_s"])
    st.plotly_chart(style(fig, f"pace @ {REFERENCE_HR} bpm (faster ↑)"), use_container_width=True)

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
    fig.add_bar(x=weeks, y=easy_min, name=f"Easy (avg HR ≤ {EASY_HR_MAX})", marker_color=BLUE,
                customdata=weekly["easy_pct"].round(0), hovertemplate="week of %{x|%d %b}<br>easy %{y:.0f} min (%{customdata:.0f}%)<extra></extra>")
    fig.add_bar(x=weeks, y=hard_min, name=f"Hard (avg HR > {EASY_HR_MAX})", marker_color=ORANGE,
                customdata=weekly["verdict"], hovertemplate="week of %{x|%d %b}<br>hard %{y:.0f} min<br>%{customdata}<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.25, barcornerradius=4, legend_traceorder="normal")
    for week in weeks[weekly["race_week"]]:
        fig.add_annotation(x=week, y=(weekly["moving_time_s"] / 60).max() * 1.08, text="race",
                           showarrow=False, font=dict(color=MUTED, size=12))
    st.plotly_chart(style(fig, "minutes per week"), use_container_width=True)

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
        "Uses each run's *average* HR, so a run can contain easy parts and still count as hard.",
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
        marker=dict(size=9, color=BLUE, line=dict(width=2, color="#fcfcfb")),
        customdata=list(zip(runs["title"], runs["air_temp_c"].round(1), runs["dew_point_c"].round(1),
                            runs["avg_pace_s_per_km"].map(format_pace), runs["heat_adj_pace_s"].map(format_pace))),
        hovertemplate="%{x|%d %b}  %{customdata[0]}<br>air %{customdata[1]} °C, dew point %{customdata[2]} °C"
                      "<br>slowdown %{y:.1f}%<br>actual %{customdata[3]} → cool-weather %{customdata[4]}/km<extra></extra>",
    )
    fig.update_yaxes(range=[0, 10], ticksuffix="%")
    st.plotly_chart(style(fig, "expected slowdown"), use_container_width=True)

    st.markdown(
        f"Heat costs you about **{runs['heat_slowdown_pct'].median():.1f}%** on a typical run "
        f"(range {runs['heat_slowdown_pct'].min():.1f}-{runs['heat_slowdown_pct'].max():.1f}%). "
        "Both races had almost identical conditions, so the race-to-race gain is not the weather."
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
