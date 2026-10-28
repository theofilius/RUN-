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
| **Race post-mortem** | Compares the weeks before two races: volume, runs per week, longest run, average HR, easy share, efficiency, heat |
| **Aerobic fitness trend** | Estimated pace at a fixed heart rate (e.g. pace @ 160 bpm) per run and per month |
| **Easy-run honesty check** | Weekly easy vs hard time against an 80/20 target, plus runs you *called* easy whose heart rate says otherwise |
| **Heat-adjusted pace** | Real air temperature and dew point for each run (from Open-Meteo), converted to an expected slowdown |
| **Next-week planner** | Generates next week's runs from your data, gives a reason for each, and runs visible safety checks |
| **`.fit` workout export** | Turns planned runs into Garmin workout files you copy to your watch |
| **Dashboard** | All of the above in a local Streamlit app, with charts, tables and "How is this calculated?" boxes |

---

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/theofilius/RUN-.git
cd RUN-
pip install -r requirements.txt
```

### 1. Export your runs from Garmin Connect

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
RACES = {                       # races to compare (start time as on the watch)
    "Race A": {"start": "2026-06-14 04:51:01", "distance_km": 21.1},
    "Race B": {"start": "2026-10-24 04:41:22", "distance_km": 21.1},
}
LONG_RUN_DAY = 5                # 0 = Monday ... 6 = Sunday
OTHER_RUN_DAYS = [1, 3, 4, 0]   # preferred days for other runs
```

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
python -m src.planner.plan_generator   "$CSV"              # next Monday
python -m src.planner.plan_generator   "$CSV" 2026-11-09   # a specific week
python -m src.export.fit_workout       "$CSV"              # writes exports/week-.../*.fit
```

---

## Putting workouts on your watch

Third-party apps cannot write into Garmin Coach, and pushing workouts through
Garmin's API needs a business account. Instead, this project writes standard
`.fit` workout files:

1. Download the files from the dashboard's **Next week** tab, or run `python -m src.export.fit_workout`.
2. Connect the watch over USB and copy the files into **`GARMIN/NewFiles`**.
3. Unplug the watch. The workouts appear under **Training → Workouts**.

Each step is a distance with a heart-rate range, and the watch alerts you when
your HR leaves it.

On macOS, many newer Garmin watches connect over MTP and don't show up in
Finder. Use [OpenMTP](https://openmtp.ganeshrvel.com/) to copy the files.

---

## How the numbers are calculated

| Metric | Formula |
|---|---|
| Efficiency | (distance m ÷ moving minutes) ÷ average HR. Higher means fitter |
| Pace @ reference HR | 1000 ÷ (efficiency × reference HR) minutes per km |
| Easy run | average HR ≤ 80% of max HR (configurable) |
| Easy % | moving time of easy runs ÷ total moving time, per Monday–Sunday week |
| Heat slowdown | air temp °F + dew point °F, looked up in a runner's rule-of-thumb table (0% at 100 → 10% at 180) |
| Heat-adjusted pace | pace ÷ (1 + slowdown %) |
| Acute:chronic load | km this week ÷ average km/week over this week and the 3 before it |

The watch's own temperature sensor is **not** used. It sits against your wrist
and reads several degrees too high. Weather comes from
[Open-Meteo](https://open-meteo.com/), which is free and needs no API key. Only
city coordinates and dates are sent, and the results are cached in
`data/weather_cache.csv`.

### Planner rules

The planner checks these rules in order and uses the first one that matches:

1. **A race in the last 14 days** → *recovery week*: all easy, no extra distance.
2. **Easy time under 50%** → *fix-easy week*: distance holds, every run capped at the easy HR.
3. **Otherwise** → *build week*: +10% distance and one tempo run.

Safety checks shown with every plan:

- Weekly distance goes up by at most 10% over the 4-week average.
- The long run grows by at most 1.5 km.
- No hard sessions within 14 days of a race.
- A flag for any week where acute:chronic load went above 1.3.

---

## Project structure

```
data/                     your Garmin export + weather cache (gitignored)
exports/                  generated .fit files (gitignored)
src/
  config.py               personal settings: max HR, races, run days
  units.py                seconds ↔ "m:ss" / "h:mm:ss"
  loaders/
    csv_garmin.py         Garmin CSV → clean table (numbers, seconds, km)
    weather_openmeteo.py  hourly air temp + dew point, cached
  analysis/
    race_postmortem.py    compare the weeks before two races
    fitness_trend.py      efficiency and pace @ HR over time
    easy_check.py         weekly 80/20 check + mislabelled easy runs
    heat_adjust.py        heat slowdown and heat-adjusted pace
  planner/
    plan_generator.py     next week's workouts with reasons
    safety_rules.py       the checks every plan must pass
  export/
    fit_workout.py        workouts → Garmin .fit files
app/
  dashboard.py            Streamlit dashboard (draws only; all numbers come from src/)
```

Loading data is kept separate from analysis. Every analysis module works on
the same clean columns (`distance_km`, `avg_hr`, `moving_time_s`, ...), so a
Strava or Garmin API loader can be added later without touching the analysis.

---

## Limitations

- Garmin's CSV has **one summary row per run**, so the easy/hard check uses each run's *average* heart rate. A run with easy parts can still count as hard.
- Heat adjustment and pace @ HR are **estimates** for comparing runs, not exact predictions.
- The default max HR comes from the highest value seen in the data. Real HR zones from Garmin Connect would be more accurate.
- The `.fit` files are checked with Garmin's official FIT SDK decoder, but watch support for `GARMIN/NewFiles` varies by model.

---

## Roadmap

- [x] Phase 1: analysis (post-mortem, fitness trend, easy check, heat)
- [x] Phase 2: next-week planner with safety rules
- [x] Phase 3: `.fit` workout export
- [ ] Backward goal planner: the gap between current fitness and a target time
- [ ] Strava bulk-export loader
- [ ] Phase 4: automatic import via the Garmin personal API (pull-only)
