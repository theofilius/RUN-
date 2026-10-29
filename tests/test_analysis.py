"""Goal planner, easy-time and air-quality helpers."""

import math

import pandas as pd
import pytest

from src.analysis.easy_check import easy_seconds
from src.analysis.goal_planner import parse_time, target_options, weeks_needed
from src.analysis.run_conditions import aqi_label, combine_air


def test_parse_time():
    assert parse_time("2:50:00") == 10200
    assert parse_time("50:00") == 3000


def test_target_options_start_just_above_the_estimate_in_steps():
    options = target_options(parse_time("3:13:29"), 21.1, weekly_gain=0.004)
    targets = [t for t, _ in options]
    assert targets[0] == parse_time("3:20:00") and targets[1] == parse_time("3:10:00")
    assert options[0][1] == 0                      # already faster than sub 3:20
    assert options[1][1] < options[2][1]           # harder targets need more weeks


def test_weeks_needed():
    assert weeks_needed(10000, 10000, 0.01) == 0
    assert weeks_needed(10100, 10000, 0.0) is None
    assert weeks_needed(10100, 10000, 0.01) == pytest.approx(1.0, rel=0.01)


def test_easy_seconds_uses_average_hr_without_fit_data():
    runs = pd.DataFrame({"moving_time_s": [600.0, 600.0], "avg_hr": [150, 170]})
    assert list(easy_seconds(runs)) == [600.0, 0.0]


def test_easy_seconds_uses_per_second_data_when_present():
    runs = pd.DataFrame({"moving_time_s": [600.0, 600.0], "avg_hr": [170, 170],
                         "zone_easy_s": [300.0, math.nan], "zone_total_s": [600.0, math.nan]})
    assert list(easy_seconds(runs)) == [300.0, 0.0]


@pytest.mark.parametrize("aqi, label", [(40, "good"), (100, "moderate"), (151, "unhealthy"), (400, "hazardous")])
def test_aqi_labels(aqi, label):
    assert aqi_label(aqi) == label


def test_measured_air_quality_corrects_the_model_and_fades():
    times = pd.date_range("2026-10-29 17:00", periods=60, freq="h")
    forecast = pd.DataFrame({"time": times, "us_aqi": 200.0})
    combined = combine_air(forecast, {"time": times[0], "us_aqi": 100})
    assert combined.loc[0, "us_aqi"] == 100 and combined.loc[0, "aqi_source"] == "measured"
    assert 100 < combined.loc[24, "us_aqi"] < 200 and combined.loc[24, "aqi_source"] == "adjusted"
    assert combined.loc[50, "us_aqi"] == 200 and combined.loc[50, "aqi_source"] == "model"


def test_no_measurement_keeps_the_model():
    forecast = pd.DataFrame({"time": pd.date_range("2026-10-29", periods=3, freq="h"), "us_aqi": 150.0})
    assert (combine_air(forecast, None)["us_aqi"] == 150).all()
