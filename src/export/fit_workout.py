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
    WorkoutStepDuration,
    WorkoutStepTarget,
)

# FIT stores a custom heart-rate target as bpm + 100.
# (Values 0-100 mean "% of max HR", so 100 is added to tell them apart.)
HR_OFFSET = 100

# A watch HR target needs a low and a high end. Easy steps only have a
# ceiling, so the floor is set low enough that it never alerts.
EASY_HR_FLOOR = 100

INTENSITY = {
    "warm-up": Intensity.WARMUP,
    "cool-down": Intensity.COOLDOWN,
}


def workout_name(workout):
    """Short name shown on the watch, e.g. "Tue easy 4.5k"."""
    return f"{workout.day:%a} {workout.kind} {workout.distance_km:g}k"


def file_name(workout):
    """e.g. "2026-11-03_easy.fit" - sorts by date in the folder."""
    return f"{workout.day:%Y-%m-%d}_{workout.kind}.fit"


def step_message(step, index):
    """One plan Step -> one FIT workout step: distance + heart-rate range."""
    hr_low = step.hr_min or EASY_HR_FLOOR

    msg = WorkoutStepMessage()
    msg.message_index = index
    msg.workout_step_name = f"{step.name} {hr_low}-{step.hr_max}"
    msg.intensity = INTENSITY.get(step.name, Intensity.ACTIVE)
    msg.duration_type = WorkoutStepDuration.DISTANCE
    msg.duration_distance = step.distance_km * 1000  # metres
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
    header.workout_name = workout_name(workout)
    header.sport = Sport.RUNNING
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
    # python -m src.export.fit_workout "data/Running Data may-oct.csv" [YYYY-MM-DD]
    import sys

    from src.analysis.heat_adjust import load_runs_with_heat
    from src.planner.plan_generator import build_plan, next_monday

    runs = load_runs_with_heat(sys.argv[1])
    start = sys.argv[2] if len(sys.argv) > 2 else next_monday()
    plan = build_plan(runs, start)

    out_dir = Path("exports") / f"week-{plan['context']['plan_start']:%Y-%m-%d}"
    for path in export_plan(plan, out_dir):
        print(f"  {path}")
    print("\nCopy these files to the watch folder GARMIN/NewFiles (USB), then unplug.")
