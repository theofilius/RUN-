# Running Training Analyzer

**Garmin records your runs. This app explains your training.**

Garmin Connect and Strava already show charts, maps and activity feeds. This
project answers different questions:

- *Why* did I get faster between two races?
- Is my aerobic fitness actually improving?
- Are my easy runs really easy?
- How much is the heat slowing me down?
- What should I run next week, and why?

The app shows the formula and the data behind every number it gives.

> Built for a self-coached runner training in a tropical climate (Jakarta, Indonesia).
> This is not medical advice: the planner uses conservative rules of thumb.

---

## Features

| Feature | What it tells you |
|---|---|
| **Race post-mortem** | Compares the weeks before your last two races: volume, runs per week, longest run, average HR, easy share, efficiency, heat |
| **Aerobic fitness trend** | Estimated pace at a fixed heart rate (e.g. pace @ 160 bpm) per run and per month |
| **Easy-run honesty check** | Weekly easy vs hard time against an 80/20 target, plus runs you *called* easy whose heart rate says otherwise |
| **Heat-adjusted pace** | Real air temperature and dew point for each run (from Open-Meteo), converted to an expected slowdown |
| **Training plan** | A rolling month plan (Monday–Sunday weeks) re-planned every week from your latest data, with a planned-vs-actual evaluation of each finished week. A finished week is frozen as you last saw it, so later changes to the goal or the rules never rewrite the plan it is judged against. Each day is a menu: rest, or warm-up / main / cool-down with distance, heart-rate range, pace range, time and how to run it, plus a reason and visible safety checks |
| **Training programs** | Save what you train for (distance, "sub" target, race date, start), as many as you like, one active. Each program has its own page: the goal in plain words, a month-by-month calendar from start to race (tap a day for its menu and what you actually ran), every week and the build-up chart. Programs keep adapting to your runs; finished weeks stay frozen per program |
| **Goal planner** | Pick a distance and a "sub" target from a dropdown built from your current estimate. Each option shows the weeks needed at your own rate. The plan adapts: goal-pace finishes on long runs when the pace is within reach, a long-run ceiling for the distance, and a taper once you set a race date |
| **Taper and step-back weeks** | A 2-week taper before your goal race, and a lighter week every 4th week |
| **`.fit` workout export** | Turns planned runs into Garmin workout files you copy to your watch |
| **Weather & air quality** | Sidebar forecast for your city: now, the next hours and your usual run time (Open-Meteo, info only) |
| **Garmin Connect sync (optional)** | With a free Garmin Personal API key, runs come straight from Garmin Connect, including your full history, with no CSV export. The dashboard syncs by itself every hour or on **Sync now** |
| **Per-second heart rate** | The easy-run check counts actual seconds at easy HR from activity `.fit` files in `data/activities/`. The Garmin sync downloads them for the last 12 weeks; you can also add them by hand |
| **Dashboard** | A local Streamlit app in English or Indonesian (⋮ → Settings → Language). It opens on today's run in plain words, then shows the week (done / missed / today), your goal and build-up, the coming weeks, a one-line safety summary, and charts for races, fitness, easy vs hard and heat. Formulas and sources sit behind "Technical details" and "How is this calculated?" |

---

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/theofilius/RUN-.git
cd RUN-
pip install -r requirements.txt
```

### 1. Get your runs

**Option A: Garmin Personal API (recommended).** This option is free for your own data and read-only.

1. On Garmin Connect web, open **Settings → Personal API Token** and create a key.
2. Create a file called `.env` in the project folder, next to `README.md`, with this line:
   ```
   GARMIN_API_KEY=your-key
   GARMIN_API_KEY_EXPIRES=2027-04-27   # optional: the expiry you chose; the dashboard warns 14 days before
   ```
   `.env` is in `.gitignore`, so the key is never committed. Never paste it anywhere else.
3. Run a first sync. It downloads everything, plus `.fit` files for the last 12 weeks, in about a minute:
   ```bash
   python -m src.loaders.garmin_api
   ```
   Reading new `.fit` files takes a few seconds each, once; the results are then cached. After that, the dashboard keeps itself up to date.

**Option B: CSV export.**

1. Open **connect.garmin.com** in a browser. The mobile app cannot export.
2. Go to **Activities → All Activities**.
3. Scroll down until every run you want has loaded.
4. Scroll back up and click **Export CSV**, at the top right of the list.
5. Create a `data/` folder in the project and put the CSV in it.

`data/` is listed in `.gitignore`, so your personal data is never committed.

### 2. Set your details

Edit [`src/config.py`](src/config.py):

```python
MAX_HR = 196                    # your max heart rate
RACES = {                       # extra races (start time as on the watch) - see below
    "Race A": {"start": "2026-06-14 04:51:01", "distance_km": 21.1},
    "Race B": {"start": "2026-10-24 04:41:22", "distance_km": 21.1},
}
PLAN_START = "2026-10-28"       # the day your plan starts (weeks run Monday-Sunday)
RUNS_PER_WEEK = 6               # your target; START_RUNS_PER_WEEK is week 1
WEEKLY_GROWTH = 0.15            # distance growth once the target number of runs is reached
STEP_BACK_EVERY = 4             # every 4th week is lighter (0 = off)
# Your goal (distance, "sub" target, race date) is chosen in the dashboard and
# saved to data/goal.json; GOAL_RACE here is only the default.
LONG_RUN_DAY = 5                # 0 = Monday ... 6 = Sunday
OTHER_RUN_DAYS = [1, 3, 0, 4, 2]   # preferred days for the other runs, in order
HOME_CITY = "Jakarta"           # weather and air-quality forecast
RUN_HOURS = (19, 21)            # when you usually run
```

**Races.** With the Garmin sync, set **Event Type → Race** on a race activity in Garmin Connect and it is
picked up by itself: recovery days after it, left out of training trends, and used for the goal estimate.
`RACES` is for CSV data, which has no event type, or for giving a race a short name. Both work together.

With the CSV option, you can add activity `.fit` files to `data/activities/` yourself for
per-second heart-rate analysis (Garmin Connect web → an activity → gear icon →
**Export Original**, then unzip). The API sync does this for you.

### 3. Open the dashboard

```bash
streamlit run app/dashboard.py
```

The dashboard opens at http://localhost:8501.

### Or use the command line

Every module also runs on its own and prints a plain-text report:

```bash
CSV="data/your-garmin-export.csv"

python -m src.analysis.race_postmortem "$CSV"
python -m src.analysis.fitness_trend   "$CSV"
python -m src.analysis.easy_check      "$CSV"
python -m src.analysis.heat_adjust     "$CSV"
python -m src.planner.month_plan       "$CSV"              # month plan from PLAN_START + this week's menu
python -m src.planner.plan_generator   "$CSV" 2026-11-09   # a single week starting on a date
python -m src.export.fit_workout       "$CSV"              # this week's runs -> exports/week-.../*.fit
```

### Run the tests

```bash
python -m pytest
```

The tests use synthetic runs, so they need neither your CSV nor internet. They
check the planner's safety rules (never more than +30% a week, the long run
never goes down, at most one extra run a week, 3 rest days after a race, the
taper), the `.fit` files, the analysis helpers, and the Garmin sync (against a fake Garmin).

---

## Putting workouts on your watch

Third-party apps cannot write into Garmin Coach, and pushing workouts through
Garmin's API needs a business account. Instead, this project writes standard
`.fit` workout files:

1. Run `python -m src.export.fit_workout` (the dashboard no longer offers the files).
2. Connect the watch over USB and copy the files into **`GARMIN/NewFiles`**.
3. Unplug the watch. The workouts appear under **Training → Workouts**.

Each step is a distance with a heart-rate range, and the watch alerts you when
your HR leaves it. Interval repeats target **pace** instead, because heart rate
rises too slowly on short efforts. Step names carry the pace range (for example
`Easy 8:11-9:23`).

On macOS, many newer Garmin watches (for example the Forerunner 165) connect
over MTP and don't show up in Finder. Use
[OpenMTP](https://openmtp.ganeshrvel.com/) to copy the files.

Garmin Connect web cannot import workout `.fit` files. Its Import only accepts
activities, so the USB route is the way in.

---

## How the numbers are calculated

| Metric | Formula |
|---|---|
| Efficiency | (distance m ÷ moving minutes) ÷ average HR. Higher means fitter |
| Pace @ reference HR | 1000 ÷ (efficiency × reference HR) minutes per km |
| Easy run | average HR ≤ 80% of max HR (configurable) |
| Easy % | easy moving time ÷ total moving time, per Monday–Sunday week. Per second where an activity `.fit` exists, otherwise by each run's average HR |
| Goal estimate | last race × (goal km ÷ race km)^1.06 (Riegel) × (efficiency before that race ÷ efficiency now) |
| Weeks to goal | ln(estimate ÷ target) ÷ ln(1 + your weekly fitness gain) |
| Air quality | US AQI. Open-Meteo model (CAMS), or IQAir measured now plus a 48 h correction if you add an IQAir key |
| Heat slowdown | air temp °F + dew point °F, looked up in a runner's rule-of-thumb table (0% at 100 → 10% at 180) |
| Heat-adjusted pace | pace ÷ (1 + slowdown %) |
| Acute:chronic load | km this week ÷ average km/week over the 3 weeks *before* it (uncoupled) |

The watch's own temperature sensor is **not** used. It sits against your wrist
and reads several degrees too high. Weather comes from
[Open-Meteo](https://open-meteo.com/), which is free and needs no API key. Only
city coordinates and dates are sent, and the results are cached in
`data/weather_cache.csv`.

### Planner rules

**Week type** (the first rule that matches):

1. **A race in the last 14 days** → *recovery*: every run easy.
2. **Easy time under 50%** → *fix easy*: every run easy.
3. **Otherwise** → *build*: one hard session a week, tempo and intervals in turn.

The month plan can also set a **phase**:
- every 4th week is a *step back*
- the 2 weeks before `GOAL_RACE` are *taper* and *race week*

**How the week is built (frequency first):**

- **Runs:** week 1 has `START_RUNS_PER_WEEK`. After that, one run of 5 km or more is added each week, up to `RUNS_PER_WEEK`. No run is added if more than one run was missed last week, after an injury, or if it would break the 30% limit.
- **Long run:** starts from your recent longest run and never goes down. It grows +1 km a week when last week's reached 90% of plan and it fits the 30% limit. Only a taper shortens it. Maximum 21 km.
- **Growth:** once you reach the target number of runs, weekly distance grows by `WEEKLY_GROWTH`, shared by the easy runs.
- **30% limit:** every week stays under +30% of the last 7 days. After a step-back week, it's measured from the week before the step-back.
- **Step-back week:** no extra run, the long run holds, and distance drops about 25% (easy runs get shorter first, then one is dropped).
- **Taper:** 70% of a normal week, then 50% in race week. Runs stay frequent and some faster running is kept. No runs on race day or the day before.
- **After any race:** 3 rest days, then recovery weeks. Strides start from day 7.
- **Intervals:** 3–6 × 800 m, as many as fit the run's distance, with 400 m jogs.
- **Paces:** from your own efficiency, projected forward at your recent fitness gain (at most 1% a week).

Every plan shows these checks, each with a level (pass / note / caution / high)
and its source:

| Check | Evidence |
|---|---|
| No runs in the 3 days after a race | Zhou et al. 2026, doi:10.1186/s13102-026-01640-w; Wang et al. 2025, doi:10.1186/s40798-025-00824-x |
| Planned week ≤ last 7 days + 30% | Nielsen et al. 2014, doi:10.2519/jospt.2014.5164 |
| Weekly distance ≤ 4-week average + 10% | Cautious default, shown as caution only. A 10%-rule trial did not reduce injuries (Buist et al. 2008, doi:10.1177/0363546507307505) |
| Distance not rising 3 weeks in a row | Nielsen et al. 2014 (discussion) |
| Long run ≤ recent longest + 1.5 km | Planner default; Fokkema et al. 2020 links longer long runs to faster times (doi:10.1111/sms.13725) |
| No hard sessions within 14 days of a race | Planner default |
| Acute:chronic ratio: caution ≥ 1.3, high ≥ 1.5 | Cloosterman et al. 2024, doi:10.4085/1062-6050-0430.23. Weak evidence for runners |
| Taper: about 2 weeks, volume −41–60% | Bosquet et al. 2007, doi:10.1249/mss.0b013e31806010e0 |

All sources are listed in [`src/evidence.py`](src/evidence.py).

---

## Project structure

```
data/                     your Garmin data, caches, activities/, frozen weeks in plans/ (gitignored)
exports/                  generated .fit files (gitignored)
src/
  config.py               personal settings: max HR, races, goal race, run days, plan
  evidence.py             the papers behind each rule, with DOIs
  units.py                seconds ↔ "m:ss" / "h:mm:ss"
  env.py                  API keys from the environment or .env
  programs.py             saved training programs (data/programs.json), one active
  loaders/
    csv_garmin.py         Garmin CSV → clean table (numbers, seconds, km)
    garmin_api.py         Garmin Personal API sync → the same table (needs GARMIN_API_KEY in .env)
    fit_activities.py     optional per-second HR from activity .fit files
    weather_openmeteo.py  hourly air temp + dew point for past runs, cached
    forecast_openmeteo.py weather + air-quality forecast, cached
    iqair.py              optional measured AQI (needs IQAIR_API_KEY in .env)
  analysis/
    races.py              which runs are races (Garmin Event Type or RACES)
    race_postmortem.py    compare the weeks before two races
    fitness_trend.py      efficiency and pace @ HR over time
    easy_check.py         weekly 80/20 check + mislabelled easy runs
    heat_adjust.py        heat slowdown and heat-adjusted pace
    goal_planner.py       estimate today vs target time
    run_conditions.py     forecast per run window, AQI labels, model + measured air
  planner/
    plan_generator.py     one week of workouts with reasons
    month_plan.py         the rolling month plan, weekly evaluation, phases, frozen weeks
    safety_rules.py       the checks every plan must pass
  export/
    fit_workout.py        workouts → Garmin .fit files
app/
  dashboard.py            Streamlit dashboard (draws only; all numbers come from src/)
  i18n.py                 every sentence of the dashboard, in English and Indonesian
  assets/refresh.png      refresh icon
tests/                    pytest suite on synthetic data
```

Loading data is kept separate from analysis. Every analysis module works on
the same clean columns (`distance_km`, `avg_hr`, `moving_time_s`, ...), so the
CSV and Garmin API loaders are interchangeable, and a Strava loader could be added the same way.

---

## Limitations

- Garmin's CSV has **one summary row per run**. Runs without an activity `.fit` file use their *average* heart rate in the easy/hard check, so a run with easy parts can still count as hard. With the API sync, these are runs older than 12 weeks.
- The Garmin Personal API is new (October 2026). Garmin can change its endpoints and has not published rate limits.
- Recordings under 1 km, such as watch tests and false starts, are left out.
- Heat adjustment, pace @ HR, interval paces and the goal estimate are **estimates** for comparing and planning, not predictions.
- The default max HR comes from the highest value seen in the data. Real HR zones from Garmin Connect would be more accurate.
- The `.fit` workouts are checked with Garmin's official FIT SDK decoder, but watch support for `GARMIN/NewFiles` varies by model.
- Air quality is a model estimate unless an IQAir key is set.
- Dark mode uses Streamlit's built-in dark theme (Streamlit 1.37 supports one custom theme). Choose **Custom Theme** in Settings for the app's own palette.

---

## Roadmap

- [x] Phase 1: analysis (post-mortem, fitness trend, easy check, heat)
- [x] Phase 2: planner with safety rules, month plan, weekly evaluation
- [x] Phase 3: `.fit` workout export
- [x] Backward goal planner, taper and step-back weeks
- [x] Optional per-second HR from activity `.fit` files
- [x] Phase 4: automatic import via the Garmin Personal API (pull-only)
- [ ] Strava bulk-export loader
