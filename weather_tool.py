"""Weather Tool — Phase 3b: hourly forecast and active alerts."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from config import HOME_LAT, HOME_LON, USER_AGENT_CONTACT

USER_AGENT = f"weather-tool/0.4 ({USER_AGENT_CONTACT})"
NWS_BASE = "https://api.weather.gov"

CACHE_DIR = Path.home() / ".cache" / "weather-tool"
POINTS_TTL = timedelta(days=30)
FORECAST_TTL = timedelta(hours=1)
ALERTS_TTL = timedelta(minutes=10)


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


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json",
    })
    return session


def fetch_points(session: requests.Session, lat: float, lon: float) -> dict:
    return cached_get(session, f"{NWS_BASE}/points/{lat},{lon}", POINTS_TTL)


def fetch_forecast(lat: float, lon: float) -> dict:
    session = make_session()
    points = fetch_points(session, lat, lon)
    return cached_get(session, points["properties"]["forecast"], FORECAST_TTL)


def fetch_hourly(lat: float, lon: float) -> dict:
    session = make_session()
    points = fetch_points(session, lat, lon)
    return cached_get(session, points["properties"]["forecastHourly"], FORECAST_TTL)


def fetch_alerts(lat: float, lon: float) -> list[dict]:
    session = make_session()
    url = f"{NWS_BASE}/alerts/active?point={lat},{lon}"
    data = cached_get(session, url, ALERTS_TTL)
    return data.get("features", [])


def _period_line(label: str, period: dict) -> str:
    temp = f"{period['temperature']}°{period['temperatureUnit']}"
    short = period["shortForecast"]
    precip = period.get("probabilityOfPrecipitation", {}).get("value")
    precip_str = f" / {precip}% precip" if precip is not None else ""
    return f"- **{label}** — {temp} · {short}{precip_str}"


def format_period_markdown(period: dict) -> str:
    return _period_line(period["name"], period)


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [
        max(len(h), max((len(r[i]) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]

    def bar(left, mid, right):
        return left + mid.join("─" * (w + 2) for w in widths) + right

    lines = [bar("┌", "┬", "┐")]
    lines.append("│" + "│".join(f" {h:^{widths[i]}} " for i, h in enumerate(headers)) + "│")
    for row in rows:
        lines.append(bar("├", "┼", "┤"))
        lines.append("│" + "│".join(f" {cell:<{widths[i]}} " for i, cell in enumerate(row)) + "│")
    lines.append(bar("└", "┴", "┘"))
    return lines


def format_hourly_period_markdown(period: dict) -> str:
    start = datetime.fromisoformat(period["startTime"]).astimezone()
    return _period_line(start.strftime("%a %-I %p"), period)


def format_alert_markdown(alert: dict) -> str:
    props = alert.get("properties", {})
    event = props.get("event", "Alert")
    ends_raw = props.get("ends") or props.get("expires")
    suffix = ""
    if ends_raw:
        try:
            dt = datetime.fromisoformat(ends_raw).astimezone()
            suffix = f" until {dt.strftime('%a %-I:%M %p')}"
        except ValueError:
            pass
    return f"> **Alert: {event}**{suffix}"


def alerts_banner(alerts: list[dict]) -> list[str]:
    if not alerts:
        return []
    return [format_alert_markdown(a) for a in alerts] + [""]


def cmd_forecast(args: argparse.Namespace) -> None:
    forecast = fetch_forecast(HOME_LAT, HOME_LON)
    try:
        alerts = fetch_alerts(HOME_LAT, HOME_LON)
    except Exception as e:
        print(f"warning: alerts unavailable ({e})", file=sys.stderr)
        alerts = []
    forecast["properties"]["periods"] = forecast["properties"]["periods"][:args.days * 2]

    if args.format == "json":
        print(json.dumps({"alerts": alerts, "forecast": forecast}, indent=2))
        return

    lines = alerts_banner(alerts)
    lines.append("# Weather forecast")
    updated = forecast["properties"].get("updateTime", "")
    if updated:
        lines.append(f"_Updated: {updated}_")
    lines.append("")

    periods = forecast["properties"]["periods"]
    rows = []
    i = 0
    while i < len(periods):
        p = periods[i]
        if p.get("isDaytime", True):
            nxt = periods[i + 1] if i + 1 < len(periods) else None
            night = nxt if nxt and not nxt.get("isDaytime", True) else None
            high = f"{p['temperature']}°{p['temperatureUnit']}"
            low = f"{night['temperature']}°{night['temperatureUnit']}" if night else "—"
            precip = p.get("probabilityOfPrecipitation", {}).get("value")
            cond = p["shortForecast"] + (f" / {precip}% precip" if precip is not None else "")
            rows.append([p["name"], high, low, cond])
            i += 2 if night else 1
        else:
            i += 1
    lines.extend(_table(["Day", "High", "Low", "Conditions"], rows))
    print("\n".join(lines))


def cmd_hourly(args: argparse.Namespace) -> None:
    hourly = fetch_hourly(HOME_LAT, HOME_LON)
    try:
        alerts = fetch_alerts(HOME_LAT, HOME_LON)
    except Exception as e:
        print(f"warning: alerts unavailable ({e})", file=sys.stderr)
        alerts = []
    hourly["properties"]["periods"] = hourly["properties"]["periods"][:args.hours]

    if args.format == "json":
        print(json.dumps({"alerts": alerts, "hourly": hourly}, indent=2))
        return

    lines = alerts_banner(alerts)
    lines.append(f"# Hourly forecast ({args.hours} hours)")
    lines.append("")
    lines.extend(format_hourly_period_markdown(p) for p in hourly["properties"]["periods"])
    print("\n".join(lines))


def cmd_current(args: argparse.Namespace) -> None:
    forecast = fetch_forecast(HOME_LAT, HOME_LON)
    try:
        alerts = fetch_alerts(HOME_LAT, HOME_LON)
    except Exception as e:
        print(f"warning: alerts unavailable ({e})", file=sys.stderr)
        alerts = []
    period = forecast["properties"]["periods"][0]

    if args.format == "json":
        print(json.dumps({"alerts": alerts, "current": period}, indent=2))
        return

    lines = alerts_banner(alerts)
    lines.append(format_period_markdown(period))
    print("\n".join(lines))


def _hours_arg(value: str) -> int:
    n = int(value)
    if not 1 <= n <= 48:
        raise argparse.ArgumentTypeError("--hours must be between 1 and 48")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="weather-tool",
        description="Weather lookups via the NWS API.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_forecast = sub.add_parser("forecast", help="Daily forecast (up to 7 days)")
    p_forecast.add_argument(
        "--days", type=int, default=7, choices=range(1, 8),
        help="Number of days to show (1-7, default 7)",
    )
    p_forecast.add_argument(
        "--format", choices=["json", "markdown"], default="json",
        help="Output format (default json)",
    )
    p_forecast.set_defaults(func=cmd_forecast)

    p_hourly = sub.add_parser("hourly", help="Hourly forecast (up to 48 hours)")
    p_hourly.add_argument(
        "--hours", type=_hours_arg, default=24, metavar="N",
        help="Number of hours to show (1-48, default 24)",
    )
    p_hourly.add_argument(
        "--format", choices=["json", "markdown"], default="json",
        help="Output format (default json)",
    )
    p_hourly.set_defaults(func=cmd_hourly)

    p_current = sub.add_parser("current", help="Current period (e.g. 'This Afternoon')")
    p_current.add_argument(
        "--format", choices=["json", "markdown"], default="json",
        help="Output format (default json)",
    )
    p_current.set_defaults(func=cmd_current)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
