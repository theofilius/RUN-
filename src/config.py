"""Personal settings used across the analysis.

Change values here, not inside the analysis code, so every insight
can point back to one place that says which numbers were assumed.
"""

# Highest "Max HR" in the Garmin export (run on 2026-05-22).
# A measured value beats a formula: Tanaka 2001 found individuals differ from
# 208 - 0.7 x age by about 10 bpm, and recommends direct measurement when possible.
# Replace with the value from Garmin Connect > Heart Rate Zones if you find it.
MAX_HR = 196

# City for the weather and air-quality forecast (Jakarta, Tangerang or Bogor).
HOME_CITY = "Jakarta"

# When you usually run, as (first hour, last hour) in local 24-hour time.
# The forecast summarises these hours for every run day.
RUN_HOURS = (19, 21)

# Races to analyse. Start times are copied from the watch data.
RACES = {
    "VHM": {"start": "2026-06-14 04:51:01", "distance_km": 21.1},
    "Jakarta Running Festival HM": {"start": "2026-10-24 04:41:22", "distance_km": 21.1},
}

# A run counts as "easy" if its average HR is at or below this share of MAX_HR.
# 0.80 x 196 = 157 bpm. This is an assumption; real zones from Garmin would be better.
EASY_HR_FRACTION = 0.80
EASY_HR_MAX = round(EASY_HR_FRACTION * MAX_HR)  # whole bpm, like the watch shows

# Share of weekly running time that should be easy (the "80/20" rule).
TARGET_EASY_PCT = 80

# Heart rate used to express fitness as a pace ("pace @ 160 bpm").
# Close to your typical run HR, so the estimate stays near real data.
REFERENCE_HR = 160

# Planner: did you have a running injury in the last 12 months?
# The strongest injury predictor in Fokkema 2020; if True, build weeks hold
# distance flat instead of adding 10%.
INJURED_LAST_12_MONTHS = False

# Training plan: the day your plan started - the first run is on this day.
# Weeks run Monday-Sunday (week 1 is the week containing this date).
# PLAN_WEEKS_AHEAD = weeks shown from the current week (4 = about a month).
PLAN_START = "2026-10-28"
PLAN_WEEKS_AHEAD = 4

# Planner: how many runs a week you are aiming for. The plan uses as many as
# the week's safe distance allows (each run at least 3 km), up to this number.
RUNS_PER_WEEK = 6
START_RUNS_PER_WEEK = 4   # runs in the first week; one is added each week after

# Planner: weekly distance growth once RUNS_PER_WEEK is reached. Every week also
# stays under +30% of the previous 7 days (Nielsen 2014). 0.10 = cautious,
# 0.15 = middle, up to 0.29 = most aggressive still under the 30% limit.
WEEKLY_GROWTH = 0.15

# Planner: which days you like to run. The long run goes on LONG_RUN_DAY,
# other runs fill OTHER_RUN_DAYS in this order. 0 = Monday ... 6 = Sunday.
# Sunday is left out so the day after the long run is always rest.
LONG_RUN_DAY = 5  # Saturday
OTHER_RUN_DAYS = [1, 3, 0, 4, 2]  # Tue, Thu, Mon, Fri, Wed

# How many weeks before each race the post-mortem compares.
# 5 because the export only starts on 2026-05-10 (5 weeks before VHM).
COMPARE_WEEKS = 5
