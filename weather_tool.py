"""Weather Tool — Phase 2: NWS roundtrip with file-based cache."""

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from config import HOME_LAT, HOME_LON, USER_AGENT_CONTACT

USER_AGENT = f"weather-tool/0.2 ({USER_AGENT_CONTACT})"
NWS_BASE = "https://api.weather.gov"

CACHE_DIR = Path.home() / ".cache" / "weather-tool"
POINTS_TTL = timedelta(days=30)
FORECAST_TTL = timedelta(hours=1)


def cache_path(url: str) -> Path:
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{key}.json"


def cached_get(session: requests.Session, url: str, ttl: timedelta) -> dict:
    path = cache_path(url)
    if path.exists():
        entry = json.loads(path.read_text())
        fetched = datetime.fromisoformat(entry["fetched_at"])
        age = datetime.now(timezone.utc) - fetched
        if age < ttl:
            print(f"cache hit  ({int(age.total_seconds())}s old) {url}", file=sys.stderr)
            return entry["data"]

    print(f"cache miss             {url}", file=sys.stderr)
    resp = session.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "data": data,
    }))
    return data


def fetch_forecast(lat: float, lon: float) -> dict:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json",
    })

    points_url = f"{NWS_BASE}/points/{lat},{lon}"
    points_data = cached_get(session, points_url, POINTS_TTL)

    forecast_url = points_data["properties"]["forecast"]
    return cached_get(session, forecast_url, FORECAST_TTL)


if __name__ == "__main__":
    forecast = fetch_forecast(HOME_LAT, HOME_LON)
    print(json.dumps(forecast, indent=2))
