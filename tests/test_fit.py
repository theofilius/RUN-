"""Workout .fit export and per-second activity .fit reading."""

import pandas as pd
from fit_tool.fit_file import FitFile
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
from fit_tool.profile.profile_type import FileType, Manufacturer, WorkoutStepTarget

from src.export.fit_workout import MAX_NAME, MAX_NOTES, shorten, workout_fit_bytes
from src.loaders.fit_activities import add_time_in_zones, load_route, load_splits, route, splits, time_in_zones
from src.planner.plan_generator import interval_run, long_run

EFFICIENCY = 0.77


def decode(data):
    messages = [r.message for r in FitFile.from_bytes(data).records]
    workout = next(m for m in messages if isinstance(m, WorkoutMessage))
    steps = [m for m in messages if isinstance(m, WorkoutStepMessage)]
    return workout, steps


def test_workout_file_has_every_step_and_short_strings():
    workout = long_run(pd.Timestamp("2026-10-31").date(), 8.0, EFFICIENCY)
    header, steps = decode(workout_fit_bytes(workout))
    assert header.num_valid_steps == len(workout.steps) == len(steps)
    assert len(header.workout_name) <= MAX_NAME
    for step in steps:
        assert len(step.workout_step_name) <= MAX_NAME
        assert len(step.notes) <= MAX_NOTES


def test_interval_steps_target_pace_others_heart_rate():
    workout = interval_run(pd.Timestamp("2026-11-16").date(), 6.0, EFFICIENCY)
    _, steps = decode(workout_fit_bytes(workout))
    for plan_step, step in zip(workout.steps, steps):
        expected = WorkoutStepTarget.SPEED if plan_step.name == "interval" else WorkoutStepTarget.HEART_RATE
        assert step.target_type == expected.value


def test_shorten_cuts_at_a_word():
    assert shorten("Walk one minute whenever HR passes 157.", 20) == "Walk one minute"
    assert shorten("short", 20) == "short"


def write_activity(path, start, heart_rates):
    """A minimal activity .fit: one record per second with the given HR."""
    start_ms = round(start.timestamp() * 1000)
    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 0
    file_id.time_created = start_ms
    records = []
    for i, hr in enumerate(heart_rates):
        record = RecordMessage()
        record.timestamp = start_ms + i * 1000
        record.heart_rate = hr
        records.append(record)
    builder = FitFileBuilder(auto_define=True)
    builder.add(file_id)
    builder.add_all(records)
    builder.build().to_file(str(path))


def test_time_in_zones_counts_easy_seconds(tmp_path):
    start = pd.Timestamp("2026-10-29 19:00", tz="Asia/Jakarta")
    write_activity(tmp_path / "run.fit", start, [150] * 400 + [170] * 200)
    zones = time_in_zones(tmp_path / "run.fit", easy_hr_max=157)
    assert zones["zone_total_s"] == 599
    assert 398 <= zones["zone_easy_s"] <= 400
    assert zones["start_time"] == pd.Timestamp("2026-10-29 19:00")


def test_runs_are_matched_to_activity_files(tmp_path, runs):
    run_start = runs["start_time"].iloc[-1]
    write_activity(tmp_path / "run.fit", run_start.tz_localize("Asia/Jakarta") + pd.Timedelta(minutes=1),
                   [150] * 300)
    merged = add_time_in_zones(runs, tmp_path)
    assert merged["fit_file"].notna().sum() == 1
    assert merged.loc[merged["start_time"] == run_start, "fit_file"].iloc[0] == "run.fit"
    # The same read already left the splits and the route, so opening the run is instant.
    assert (tmp_path / "splits" / "run.csv").exists() and (tmp_path / "routes" / "run.csv").exists()
    assert (tmp_path / "heart_rate" / "run.csv").exists()


def test_a_new_easy_limit_recounts_without_reading_the_file_again(tmp_path, monkeypatch):
    from src.athlete import Athlete, use
    from src.loaders import fit_activities
    write_activity(tmp_path / "run.fit", pd.Timestamp("2026-10-29 19:00", tz="Asia/Jakarta"), [150] * 300 + [155] * 300)
    try:
        use(Athlete(max_hr=196))                                       # easy limit 153
        first = fit_activities.load_time_in_zones(tmp_path)
        monkeypatch.setattr(fit_activities, "read", lambda path: (_ for _ in ()).throw(AssertionError("parsed")))
        use(Athlete(max_hr=201))                                       # easy limit 157: recount from the cache
        second = fit_activities.load_time_in_zones(tmp_path)
    finally:
        use(Athlete())
    assert 298 <= first["zone_easy_s"].iloc[0] <= 300                 # only the 150s
    assert 598 <= second["zone_easy_s"].iloc[0] <= 600                 # 155 is easy now too


def test_no_activity_folder_leaves_runs_unchanged(tmp_path, runs):
    assert add_time_in_zones(runs, tmp_path / "missing").equals(runs)


def write_run(path, start, seconds, metres_per_s, heart_rate=150):
    """An activity .fit with distance: one record per second at a steady speed."""
    start_ms = round(start.timestamp() * 1000)
    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 0
    file_id.time_created = start_ms
    records = []
    for i in range(seconds + 1):
        record = RecordMessage()
        record.timestamp = start_ms + i * 1000
        record.distance = i * metres_per_s
        record.heart_rate = heart_rate
        records.append(record)
    builder = FitFileBuilder(auto_define=True)
    builder.add(file_id)
    builder.add_all(records)
    builder.build().to_file(str(path))


def test_splits_are_whole_kilometres_plus_the_rest(tmp_path):
    # 2.5 km at 2.5 m/s = 6:40/km, 1000 s in all.
    write_run(tmp_path / "run.fit", pd.Timestamp("2026-10-29 19:00", tz="Asia/Jakarta"), 1000, 2.5)
    table = splits(tmp_path / "run.fit")
    assert list(table["km"]) == [1, 2, 3]
    assert list(table["distance_km"].round(2)) == [1.0, 1.0, 0.5]
    assert all(abs(p - 400) < 1 for p in table["pace_s"])   # 400 s/km in every split
    assert abs(table["time_s"].sum() - 1000) < 1
    assert (load_splits(tmp_path / "run.fit")["km"] == table["km"]).all()
    assert (tmp_path / "splits" / "run.csv").exists()          # cached for next time


def test_route_keeps_only_points_with_a_position(tmp_path):
    start_ms = round(pd.Timestamp("2026-10-29 19:00", tz="Asia/Jakarta").timestamp() * 1000)
    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 0
    file_id.time_created = start_ms
    records = []
    for i, position in enumerate([None, (0.0, 0.0), (-6.19, 106.88), (-6.191, 106.881)]):
        record = RecordMessage()
        record.timestamp = start_ms + i * 1000
        record.distance = i * 2.5
        record.heart_rate = 150
        if position:
            record.position_lat, record.position_long = position
        records.append(record)
    builder = FitFileBuilder(auto_define=True)
    builder.add(file_id)
    builder.add_all(records)
    builder.build().to_file(str(tmp_path / "run.fit"))

    points = route(tmp_path / "run.fit")
    assert len(points) == 2                                   # no fix yet and 0,0 are left out
    assert abs(points["lat"].iloc[0] + 6.19) < 1e-4 and abs(points["lon"].iloc[1] - 106.881) < 1e-4
    assert list(points["km"].round(4)) == [0.005, 0.0075]
    assert len(load_route(tmp_path / "run.fit")) == 2
    assert (tmp_path / "routes" / "run.csv").exists()          # cached for next time
    write_run(tmp_path / "indoor.fit", pd.Timestamp("2026-10-29 19:00", tz="Asia/Jakarta"), 10, 2.5)
    assert route(tmp_path / "indoor.fit").empty               # treadmill: no map
