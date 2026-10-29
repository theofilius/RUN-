"""The Garmin Personal API loader, with Garmin replaced by a fake (no network)."""

import base64
import io
import json
import time
import zipfile
from urllib.error import HTTPError

import pandas as pd
import pytest

from src.loaders import garmin_api


def jwt(expires_in_s):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": time.time() + expires_in_s}).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


def activity(id_, start, kind="running", km=7.0, speed=2.0):
    return {"activityId": id_, "startTimeLocal": start, "activityType": {"typeKey": kind},
            "activityName": f"Jakarta - run {id_}", "distance": km * 1000, "duration": 3600.0,
            "movingDuration": 3500.0, "averageSpeed": speed, "averageHR": 150.0}


def zipped_fit():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("1_ACTIVITY.fit", b"fit bytes")
    return buffer.getvalue()


class FakeGarmin:
    """Answers the three calls the loader makes, and records them."""

    def __init__(self, activities):
        self.activities, self.calls = activities, []

    def __call__(self, path, params=None, token=None, key=None, method="GET"):
        self.calls.append((path, params))
        if path == garmin_api.TOKEN_PATH:
            return jwt(24 * 3600).encode()
        if path == garmin_api.ACTIVITIES_PATH:
            chosen = [a for a in self.activities if a["startTimeLocal"] >= params.get("startDate", "")]
            return json.dumps(chosen[params["start"]:params["start"] + params["limit"]]).encode()
        return zipped_fit()


def test_runs_get_the_csv_columns():
    runs = garmin_api.to_runs([activity(1, "2026-10-18 07:09:14", speed=1.994),
                               activity(2, "2026-10-19 07:00:00", kind="indoor_cycling"),
                               activity(3, "2026-10-20 07:00:00", kind="track_running"),
                               activity(4, "2026-10-21 07:00:00", km=0.03)])
    assert list(runs["activity_type"]) == ["Running", "Track Running"]     # cycling and a test dropped
    first = runs.iloc[0]
    assert first["distance_km"] == 7.0
    assert round(first["avg_pace_s_per_km"]) == 502                       # 1000 / 1.994 m/s
    assert first["start_time"] == pd.Timestamp("2026-10-18 07:09:14")
    assert not runs["garmin_race"].any()


def test_race_event_type_marks_a_race(no_races):
    from src.analysis.races import race_list, race_mask
    race = {**activity(5, "2026-10-24 04:41:22", km=21.4), "eventType": {"typeKey": "race"},
            "activityName": "HM - Jakarta Running Festival"}
    runs = garmin_api.to_runs([activity(1, "2026-10-18 07:09:14"), race])
    assert list(race_mask(runs)) == [False, True]
    assert list(race_list(runs)) == ["HM - Jakarta Running Festival"]   # named by its Garmin title


def test_token_is_reused_until_an_hour_before_expiry(tmp_path, monkeypatch):
    fake = FakeGarmin([])
    monkeypatch.setattr(garmin_api, "request", fake)
    cache = tmp_path / "token.txt"
    cache.write_text(jwt(3 * 3600))
    garmin_api.access_token("key", cache)
    assert fake.calls == []                       # 3 h left: reused
    cache.write_text(jwt(30 * 60))
    garmin_api.access_token("key", cache)
    assert len(fake.calls) == 1                   # 30 min left: renewed


def test_activity_list_is_read_page_by_page(monkeypatch):
    activities = [activity(i, f"2026-{1 + i // 28:02d}-{1 + i % 28:02d} 07:00:00") for i in range(250)]
    monkeypatch.setattr(garmin_api, "request", FakeGarmin(activities))
    assert len(garmin_api.fetch_activities("token")) == 250


def test_sync_adds_only_new_runs_and_their_files(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GARMIN_API_KEY=abc\n")
    monkeypatch.delenv("GARMIN_API_KEY", raising=False)
    today = pd.Timestamp.now()
    old = f"{today - pd.Timedelta(weeks=20):%Y-%m-%d} 07:00:00"     # before FIT_WEEKS: no file
    recent = f"{today - pd.Timedelta(days=5):%Y-%m-%d} 07:00:00"
    fake = FakeGarmin([activity(1, old), activity(2, recent)])
    monkeypatch.setattr(garmin_api, "request", fake)

    first = garmin_api.sync(tmp_path, tmp_path)
    assert (first["new"], first["fit_downloaded"]) == (2, 1)
    assert (tmp_path / "activities" / "2.fit").read_bytes() == b"fit bytes"

    fake.activities.append(activity(3, f"{today:%Y-%m-%d} 06:00:00"))
    second = garmin_api.sync(tmp_path, tmp_path)
    assert (second["new"], second["fit_downloaded"], second["runs"]) == (1, 1, 3)
    list_calls = [params for path, params in fake.calls if path == garmin_api.ACTIVITIES_PATH]
    assert "startDate" in list_calls[-1]              # the second sync only reads recent days
    assert len(garmin_api.load_api_runs(tmp_path)) == 3


def test_no_key_means_no_sync(tmp_path, monkeypatch):
    monkeypatch.delenv("GARMIN_API_KEY", raising=False)
    assert garmin_api.sync(tmp_path, tmp_path) is None


def test_key_expiry_countdown(tmp_path, monkeypatch):
    monkeypatch.delenv("GARMIN_API_KEY_EXPIRES", raising=False)
    assert garmin_api.key_days_left(tmp_path) is None
    (tmp_path / ".env").write_text("GARMIN_API_KEY=abc\nGARMIN_API_KEY_EXPIRES=2027-04-27\n")
    assert garmin_api.key_days_left(tmp_path, today="2027-04-13") == 14
    assert garmin_api.key_days_left(tmp_path, today="2027-04-28") == -1


def test_rejected_key_gives_a_clear_error(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise HTTPError("url", 401, "Unauthorized", {}, None)
    monkeypatch.setattr(garmin_api, "request", refuse)
    with pytest.raises(garmin_api.KeyRejected):
        garmin_api.access_token("old key", tmp_path / "token.txt")
