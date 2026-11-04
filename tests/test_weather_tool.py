import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

import weather_tool as w


# --- forecast_rows (review finding #1) -------------------------------------

def per(name, day, temp):
    return {
        "name": name, "isDaytime": day, "temperature": temp, "temperatureUnit": "F",
        "shortForecast": "Clear", "probabilityOfPrecipitation": {"value": 0},
    }


DAY_FIRST = [per("This Afternoon", True, 77), per("Tonight", False, 53),
             per("Saturday", True, 74), per("Saturday Night", False, 50)]

EVENING = [per("Tonight", False, 41), per("Tuesday", True, 66),
           per("Tuesday Night", False, 44), per("Wednesday", True, 70),
           per("Wednesday Night", False, 45)]


def test_day_first_pairs_high_and_low():
    rows = w.forecast_rows(DAY_FIRST, days=2)
    assert [r[:3] for r in rows] == [["This Afternoon", "77°F", "53°F"],
                                     ["Saturday", "74°F", "50°F"]]


def test_evening_keeps_tonight_low():
    rows = w.forecast_rows(EVENING, days=3)
    assert rows[0][:3] == ["Tonight", "—", "41°F"]


def test_days_cap_does_not_cut_last_low():
    rows = w.forecast_rows(EVENING, days=3)
    assert len(rows) == 3
    assert rows[-1][:3] == ["Wednesday", "70°F", "45°F"]


def test_json_slice_keeps_last_low_in_evening():
    kept = EVENING[:w.json_period_count(EVENING, days=3)]
    assert kept[-1]["name"] == "Wednesday Night"
    assert len(DAY_FIRST[:w.json_period_count(DAY_FIRST, days=2)]) == 4


# --- cached_get (review findings #2 and #3) --------------------------------

URL = "https://api.weather.gov/test"
TTL = timedelta(hours=1)


class FakeResp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, data=None, error=None):
        self.data, self.error, self.calls = data, error, 0

    def get(self, url, timeout):
        self.calls += 1
        if self.error:
            raise self.error
        return FakeResp(self.data)


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "CACHE_DIR", tmp_path / "cache")
    return tmp_path / "cache"


def seed(age, data):
    path = w.cache_path(URL)
    path.parent.mkdir(parents=True, exist_ok=True)
    fetched = datetime.now(timezone.utc) - age
    path.write_text(json.dumps({"fetched_at": fetched.isoformat(), "url": URL, "data": data}))


def test_miss_fetches_and_writes_private_cache(tmp_cache):
    s = FakeSession(data={"v": 1})
    assert w.cached_get(s, URL, TTL) == {"v": 1}
    assert (tmp_cache.stat().st_mode & 0o777) == 0o700
    assert json.loads(w.cache_path(URL).read_text())["data"] == {"v": 1}
    assert not list(tmp_cache.glob("*.tmp"))  # temp file was renamed, not left behind


def test_fresh_hit_skips_network():
    seed(timedelta(minutes=5), {"v": "cached"})
    s = FakeSession(data={"v": "new"})
    assert w.cached_get(s, URL, TTL) == {"v": "cached"}
    assert s.calls == 0


def test_corrupt_cache_is_a_miss_not_a_crash(tmp_cache):
    tmp_cache.mkdir()
    w.cache_path(URL).write_text('{"fetched_at": "2026-11')  # truncated write
    assert w.cached_get(FakeSession(data={"v": 1}), URL, TTL) == {"v": 1}


def test_fetch_failure_serves_recently_expired_copy():
    seed(TTL + timedelta(hours=1), {"v": "stale"})
    s = FakeSession(error=requests.ConnectionError("NWS down"))
    assert w.cached_get(s, URL, TTL) == {"v": "stale"}


def test_fetch_failure_with_too_old_copy_raises():
    seed(TTL + w.STALE_GRACE + timedelta(minutes=1), {"v": "ancient"})
    with pytest.raises(requests.ConnectionError):
        w.cached_get(FakeSession(error=requests.ConnectionError("down")), URL, TTL)


def test_fetch_failure_with_no_cache_raises():
    with pytest.raises(requests.HTTPError):
        w.cached_get(FakeSession(error=requests.HTTPError("503")), URL, TTL)
