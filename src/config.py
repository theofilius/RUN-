"""Personal settings used across the analysis.

Change values here, not inside the analysis code, so every insight
can point back to one place that says which numbers were assumed.
"""

# Highest "Max HR" in the Garmin export (run on 2026-05-22).
# Replace with the value from Garmin Connect > Heart Rate Zones if you find it.
MAX_HR = 196

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

# Planner: which days you like to run. The long run goes on LONG_RUN_DAY,
# other runs fill OTHER_RUN_DAYS in this order. 0 = Monday ... 6 = Sunday.
LONG_RUN_DAY = 5  # Saturday
OTHER_RUN_DAYS = [1, 3, 4, 0]  # Tue, Thu, Fri, Mon

# How many weeks before each race the post-mortem compares.
# 5 because the export only starts on 2026-05-10 (5 weeks before VHM).
COMPARE_WEEKS = 5
