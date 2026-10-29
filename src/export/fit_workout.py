"""Turn planned workouts into Garmin .fit workout files.

Third-party apps cannot write into Garmin Coach, so instead we create
the same kind of file Garmin Connect sends to the watch:

  1. connect the watch to the computer with the USB cable
  2. copy the .fit files into the watch folder  GARMIN/NewFiles
  3. unplug; the watch moves them to Training > Workouts

Each plan Step becomes one workout step: run a set distance while the
watch alerts you if your heart rate leaves the target range.
"""

import time
from pathlib import Path

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
from fit_tool.profile.profile_type import (
    FileType,
    Intensity,
    Manufacturer,
    Sport,
    SubSport,
    WorkoutStepDuration,
    WorkoutStepTarget,
)

from src.units import format_pace

# FIT stores a custom heart-rate target as bpm + 100.
# (Values 0-100 mean "% of max HR", so 100 is added to tell them apart.)
HR_OFFSET = 100

# Fallback floor for a step that only has an HR ceiling.
EASY_HR_FLOOR = 100

# Garmin watches and Garmin Connect expect short strings: step names up to 16
# characters, notes up to 50. Longer text can be cut off or rejected on import.
MAX_NAME = 16
MAX_NOTES = 50
SHORT_NAMES = {"warm-up": "WU", "easy": "Easy", "tempo": "Tempo", "interval": "Fast",
               "recovery": "Jog", "cool-down": "CD", "race pace": "Goal"}

INTENSITY = {
    "warm-up": Intensity.WARMUP,
    "cool-down": Intensity.COOLDOWN,
    "interval": Intensity.INTERVAL,
    "race pace": Intensity.ACTIVE,
    "recovery": Intensity.RECOVERY,
}


def shorten(text, limit):
    """Cut text to `limit` characters at a word boundary."""
    if len(text) <= limit:
        return text
    cut = text[:limit + 1].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:-")


def workout_name(workout):
    """Short name shown on the watch, e.g. "Tue easy 4.5k" (at most MAX_NAME characters)."""
    kind = {"interval": "intv"}.get(workout.kind, workout.kind)
    return f"{workout.day:%a} {kind} {workout.distance_km:g}k"


def file_name(workout):
    """e.g. "2026-11-03_easy.fit" - sorts by date in the folder."""
    return f"{workout.day:%Y-%m-%d}_{workout.kind}.fit"


def step_message(step, index):
    """One plan Step -> one FIT workout step: distance + heart-rate range.

    The watch alerts on heart rate; the pace range rides along in the step
    name and notes, so you can see it on the watch too.
    """
    hr_low = step.hr_min or EASY_HR_FLOOR
    pace = f"{format_pace(step.pace_fast_s)}-{format_pace(step.pace_slow_s)}"

    msg = WorkoutStepMessage()
    msg.message_index = index
    msg.workout_step_name = f"{SHORT_NAMES.get(step.name, step.name)} {pace}"[:MAX_NAME]  # e.g. "Easy 8:11-9:23"
    msg.notes = shorten(f"HR {hr_low}-{step.hr_max}. {step.note}", MAX_NOTES)
    msg.intensity = INTENSITY.get(step.name, Intensity.ACTIVE)
    msg.duration_type = WorkoutStepDuration.DISTANCE
    msg.duration_distance = step.distance_km * 1000  # metres
    if step.target == "pace":
        # HR lags on short repeats, and goal pace is about pace - the watch alerts on pace (m/s).
        msg.target_type = WorkoutStepTarget.SPEED
        msg.target_speed_zone = 0
        msg.custom_target_speed_low = 1000 / step.pace_slow_s
        msg.custom_target_speed_high = 1000 / step.pace_fast_s
    else:
        msg.target_type = WorkoutStepTarget.HEART_RATE
        msg.target_hr_zone = 0  # 0 = use the custom range below, not a Garmin zone
        msg.custom_target_heart_rate_low = hr_low + HR_OFFSET
        msg.custom_target_heart_rate_high = step.hr_max + HR_OFFSET
    return msg


def workout_fit_bytes(workout):
    """Build the .fit file for one Workout and return its bytes."""
    file_id = FileIdMessage()
    file_id.type = FileType.WORKOUT
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 0
    file_id.time_created = round(time.time() * 1000)
    file_id.serial_number = 0x52554E21  # any fixed number

    steps = [step_message(step, i) for i, step in enumerate(workout.steps)]

    header = WorkoutMessage()
    header.workout_name = workout_name(workout)[:MAX_NAME]
    header.sport = Sport.RUNNING
    header.sub_sport = SubSport.GENERIC
    header.num_valid_steps = len(steps)

    builder = FitFileBuilder(auto_define=True, min_string_size=50)
    builder.add(file_id)
    builder.add(header)
    builder.add_all(steps)
    return builder.build().to_bytes()


def export_plan(plan, out_dir):
    """Write one .fit file per workout in the plan; return the file paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for workout in plan["workouts"]:
        path = out_dir / file_name(workout)
        path.write_bytes(workout_fit_bytes(workout))
        paths.append(path)
    return paths


if __name__ == "__main__":
    # python -m src.export.fit_workout "data/Running Data may-oct.csv"   (exports this week of the plan)
    import sys

    from src.analysis.heat_adjust import load_runs_with_heat
    from src.planner.month_plan import build_month_plan, covered_until_from_file, current_week

    runs = load_runs_with_heat(sys.argv[1])
    from src.goal_settings import load_goal

    plan = current_week(build_month_plan(runs, covered_until_from_file(sys.argv[1]), goal_race=load_goal(),
                                         plans_dir=Path(sys.argv[1]).parent / "plans"))["plan"]

    out_dir = Path("exports") / f"week-{plan['context']['plan_start']:%Y-%m-%d}"
    for path in export_plan(plan, out_dir):
        print(f"  {path}")
    print("\nCopy these files to the watch folder GARMIN/NewFiles (USB), then unplug.")
