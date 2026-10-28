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
from src.config import COMPARE_WEEKS, EASY_HR_MAX, MAX_HR, RACES, REFERENCE_HR, TARGET_EASY_PCT
from src.export.fit_workout import file_name, workout_fit_bytes
from src.planner.plan_generator import build_plan, next_monday
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

st.set_page_config(page_title="Running Training Analyzer", layout="wide")
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
c1.metric(f"{race_b} time", format_duration(race_times[1]),
          f"-{format_duration(race_times[0] - race_times[1])} vs {race_a}", delta_color="off")
pace_change = last_month["pace_at_ref_hr_s"] - first_month["pace_at_ref_hr_s"]  # negative = faster
c2.metric(f"Pace @ {REFERENCE_HR} bpm, {monthly.index[-1]}", format_pace(last_month["pace_at_ref_hr_s"]),
          f"{abs(pace_change):.0f} s/km {'faster' if pace_change < 0 else 'slower'} than {monthly.index[0]}",
          delta_color="off")
c3.metric("Time spent easy", f"{total_easy_pct:.0f}%", f"target {TARGET_EASY_PCT}%", delta_color="off")

tab_plan, tab_pm, tab_fit, tab_easy, tab_heat = st.tabs(
    ["Next week", "Race post-mortem", "Aerobic fitness", "Easy-run check", "Heat"]
)

# ---------- planner ----------

with tab_plan:
    start = st.date_input("Week starting (Monday)", next_monday())
    plan = build_plan(runs, start)
    ctx = plan["context"]

    st.subheader(f"{plan['week_type'].capitalize()} week · "
                 f"{sum(w.distance_km for w in plan['workouts']):.1f} km over {len(plan['workouts'])} runs")
    st.info(plan["why"])

    rows = []
    for w in plan["workouts"]:
        steps = " → ".join(
            f"{s.name} {s.distance_km:g} km (HR {s.hr_min}-{s.hr_max})" if s.hr_min
            else f"{s.name} {s.distance_km:g} km (HR ≤ {s.hr_max})"
            for s in w.steps
        )
        rows.append({"day": f"{w.day:%a %d %b}", "type": w.kind, "km": w.distance_km,
                     "workout": steps, "why": w.reason})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(f"Pace guide: easy ≈ {format_pace(plan['easy_pace_s'])}/km at {EASY_HR_MAX} bpm in your usual heat. "
               "Follow heart rate, not pace. Not medical advice - stop and rest if something hurts.")

    st.markdown("**Send to your watch** - download, then copy into `GARMIN/NewFiles` on the watch over USB.")
    for col, w in zip(st.columns(len(plan["workouts"])), plan["workouts"]):
        col.download_button(f"⬇ {w.day:%a} {w.kind} {w.distance_km:g} km", workout_fit_bytes(w),
                            file_name=file_name(w), mime="application/octet-stream", key=f"fit-{w.day}")

    st.markdown("**Safety checks**")
    for check in plan["checks"]:
        icon = "✅" if check["passed"] else "⚠️"
        st.markdown(f"{icon} **{check['rule']}** - {check['detail']}  \n"
                    f"<span style='color:{MUTED}'>{check['formula']}</span>", unsafe_allow_html=True)

    if ctx["empty_weeks"]:
        st.warning(f"No runs recorded in week(s) of {', '.join(ctx['empty_weeks'])} - counted as 0 km. "
                   "If you ran, export your Garmin CSV again.")
    how([
        f"Based on the 4 weeks before {ctx['plan_start']:%d %b}: {ctx['baseline_km']:.1f} km/week, "
        f"{ctx['runs_per_week']:.1f} runs/week, longest training run {ctx['longest_recent_km']:.1f} km, "
        f"{ctx['easy_pct']:.0f}% easy.",
        "Week type, first rule that matches: race in the last 14 days → recovery (easy, no extra distance); "
        "easy time under 50% → hold distance, all easy; otherwise → +10% distance and one tempo run.",
        "Long run: at most 40% of the week and at most 1.5 km longer than your recent longest.",
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
