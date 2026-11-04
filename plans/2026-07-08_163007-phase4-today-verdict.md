# Phase 4: `weather-tool today` verdict — Implementation Plan

**Goal:** Add a `weather-tool today` subcommand that returns a derived "indoor or outdoor work day?" verdict, built on the existing cached forecast data.

**Architecture:** A pure verdict function scores today's remaining daytime *hourly* periods against configurable thresholds (temp / precip / wind), finds the longest contiguous friendly window, and folds in active alerts. `cmd_today` assembles thresholds from `config` and renders JSON (default) or markdown, matching the existing subcommand pattern.

**Tech stack:** Python 3.13 (pinned in `.python-version`), managed by uv (`pyproject.toml` + `uv.lock`). `requests` (already used), `pytest` (already in the `dev` dependency group). No new runtime or dev deps.

> **Updated 2026-11-03:** packaging steps revised for the uv move (merged in 43f5724). Run all Python commands as `uv run ...` from the project root.

---

## Context / assumptions

- Phase 3b is complete: `forecast`, `hourly`, `current` subcommands work; caching + alerts are in place (`weather_tool.py`).
- NWS **hourly** periods carry everything the verdict needs, per hour: `temperature` (°F), `probabilityOfPrecipitation.value` (%), `windSpeed` (string, e.g. `"7 mph"` or `"5 to 10 mph"`), `isDaytime`, `startTime`, `endTime`, `shortForecast`.
- Target verdict shape (from `SPEC.md`):
  ```json
  {
    "outdoor_work_friendly": true,
    "reason": "Sunny, 68°F, low precipitation chance",
    "best_window": "9 AM–3 PM",
    "alerts": []
  }
  ```
- The threshold *values* are initial guesses. Per SPEC and the "no automation until the manual version works" rule, they get tuned after a week of real use — Phase 4 makes them configurable and gives sane defaults; it does not claim they're correct yet.
- `tests/` already exists: `conftest.py` + `test_weather_tool.py` (10 tests). `pyproject.toml` sets `pythonpath = ["."]`, so `import weather_tool` works from tests without path hacks.
- Dependencies live in `pyproject.toml`/`uv.lock`; the old `requirements.txt` was removed 2026-11-03.

## Approach

1. Make thresholds configurable (config file + resilient defaults in code).
2. Write the verdict as small **pure functions** (no network) so they're unit-testable against saved NWS fixtures.
3. Wire a `today` subcommand that renders JSON and markdown.
4. Verify against two real, saved NWS hourly responses; note the tuning follow-up.

## Files likely to change

- Modify: `config.example.py`, `config.py` — add threshold constants
- Modify: `weather_tool.py` — verdict helpers + `cmd_today` + argparse wiring; bump `USER_AGENT` version
- Create: `tests/test_verdict.py`, `tests/fixtures/hourly_sample1.json`, `tests/fixtures/hourly_sample2.json`
- No packaging changes needed — `pytest` is already a dev dependency
- Update at end: `README.md` (document the new subcommand)

---

## Phase 4a — Configurable thresholds

### Task 1: Add thresholds to `config.example.py`
Append after `USER_AGENT_CONTACT`:
```python
# Outdoor-work thresholds for `weather-tool today`.
# Initial guesses — tune after ~a week of real use (see SPEC.md, Phase 4).
TEMP_MIN_F = 45          # below this = too cold for comfortable outdoor work
TEMP_MAX_F = 90          # above this = too hot
MAX_PRECIP_PCT = 20      # max acceptable chance-of-precip for a "friendly" hour
MAX_WIND_MPH = 15        # above this = too windy
MIN_WINDOW_HOURS = 2     # shortest run of friendly hours worth calling a "window"
```

### Task 2: Mirror the same block into local `config.py`
Same five constants, same values (tune later). This is the file actually imported.

### Task 3: Read thresholds resiliently in `weather_tool.py`
Near the top, after the `from config import ...` line, add:
```python
import config

THRESHOLDS = {
    "temp_min_f": getattr(config, "TEMP_MIN_F", 45),
    "temp_max_f": getattr(config, "TEMP_MAX_F", 90),
    "max_precip_pct": getattr(config, "MAX_PRECIP_PCT", 20),
    "max_wind_mph": getattr(config, "MAX_WIND_MPH", 15),
    "min_window_hours": getattr(config, "MIN_WINDOW_HOURS", 2),
}
```
`getattr` fallback means an older `config.py` without these keys still runs — configurable, not brittle.

**Done When (4a):**
- [ ] `config.example.py` and `config.py` both contain the five threshold constants
- [ ] `uv run python -c "import weather_tool"` imports without error (fallbacks work even if a constant is missing)

---

## Phase 4b — Verdict logic (pure functions + tests)

### Task 4: Add `parse_wind_mph`
```python
def parse_wind_mph(wind_speed: str) -> int:
    """Max mph from an NWS windSpeed string ('7 mph', '5 to 10 mph')."""
    nums = [int(tok) for tok in wind_speed.split() if tok.isdigit()]
    return max(nums) if nums else 0
```

### Task 5: Add `hour_is_friendly`
```python
def hour_is_friendly(period: dict, thresholds: dict) -> bool:
    temp = period["temperature"]
    precip = period.get("probabilityOfPrecipitation", {}).get("value") or 0
    wind = parse_wind_mph(period.get("windSpeed", "0 mph"))
    return (
        thresholds["temp_min_f"] <= temp <= thresholds["temp_max_f"]
        and precip <= thresholds["max_precip_pct"]
        and wind <= thresholds["max_wind_mph"]
    )
```

### Task 6: Add `todays_remaining_daytime_hours`
```python
def todays_remaining_daytime_hours(hourly_periods: list[dict]) -> list[dict]:
    now = datetime.now().astimezone()
    return [
        p for p in hourly_periods
        if p.get("isDaytime", True)
        and datetime.fromisoformat(p["startTime"]).astimezone() >= now
        and datetime.fromisoformat(p["startTime"]).astimezone().date() == now.date()
    ]
```

### Task 7: Add `longest_friendly_window`
```python
def longest_friendly_window(periods: list[dict], thresholds: dict) -> list[dict]:
    best, current = [], []
    for p in periods:
        if hour_is_friendly(p, thresholds):
            current.append(p)
        else:
            best, current = (current if len(current) > len(best) else best), []
    return current if len(current) > len(best) else best
```

### Task 8: Add `build_verdict` (assembles the dict)
```python
def _window_label(window: list[dict]) -> str:
    start = datetime.fromisoformat(window[0]["startTime"]).astimezone()
    end = datetime.fromisoformat(window[-1]["endTime"]).astimezone()
    return f"{start.strftime('%-I %p')}–{end.strftime('%-I %p')}"

def build_verdict(hourly: dict, alerts: list[dict], thresholds: dict) -> dict:
    periods = todays_remaining_daytime_hours(hourly["properties"]["periods"])
    window = longest_friendly_window(periods, thresholds)
    has_alert = bool(alerts)
    friendly = len(window) >= thresholds["min_window_hours"] and not has_alert

    if has_alert:
        reason = "Active weather alert — check details before outdoor work."
    elif friendly:
        mid = window[len(window) // 2]
        reason = f"{mid['shortForecast']}, {mid['temperature']}°F, low precip chance."
    elif not periods:
        reason = "No remaining daylight hours today."
    else:
        reason = "No long-enough window inside the temp/precip/wind thresholds today."

    return {
        "outdoor_work_friendly": friendly,
        "reason": reason,
        "best_window": _window_label(window) if window else None,
        "alerts": [a.get("properties", {}).get("event", "Alert") for a in alerts],
    }
```

### Task 9: Write unit tests (`tests/test_verdict.py`)
pytest is already installed via the `dev` group (`uv sync` installs it). Put these alongside the existing `tests/test_weather_tool.py`.
```python
import weather_tool as wt

T = {"temp_min_f": 45, "temp_max_f": 90, "max_precip_pct": 20,
     "max_wind_mph": 15, "min_window_hours": 2}

def _hour(temp, precip, wind, daytime=True, start="2026-07-08T12:00:00-06:00",
          end="2026-07-08T13:00:00-06:00", short="Sunny"):
    return {"temperature": temp, "probabilityOfPrecipitation": {"value": precip},
            "windSpeed": f"{wind} mph", "isDaytime": daytime,
            "startTime": start, "endTime": end, "shortForecast": short}

def test_parse_wind_mph_range():
    assert wt.parse_wind_mph("5 to 10 mph") == 10
    assert wt.parse_wind_mph("calm") == 0

def test_hour_friendly_and_unfriendly():
    assert wt.hour_is_friendly(_hour(70, 10, 5), T) is True
    assert wt.hour_is_friendly(_hour(95, 0, 0), T) is False   # too hot
    assert wt.hour_is_friendly(_hour(70, 60, 0), T) is False  # too wet

def test_longest_window_picks_the_run():
    periods = [_hour(70, 0, 5), _hour(95, 0, 5), _hour(70, 0, 5), _hour(72, 0, 5)]
    assert len(wt.longest_friendly_window(periods, T)) == 2

def test_verdict_alert_forces_unfriendly():
    hourly = {"properties": {"periods": [_hour(70, 0, 5), _hour(71, 0, 5)]}}
    v = wt.build_verdict(hourly, [{"properties": {"event": "Heat Advisory"}}], T)
    assert v["outdoor_work_friendly"] is False and v["alerts"] == ["Heat Advisory"]
```
Note: tests that rely on "today's remaining hours" use fixed dates — for those, either freeze `now` or test `longest_friendly_window`/`hour_is_friendly` directly (done above) to keep them deterministic. Keep date-sensitive assertions out of unit tests; cover that path in the real-fixture check in 4d.

**Done When (4b):**
- [ ] `uv run pytest tests/test_verdict.py -v` → all pass
- [ ] `parse_wind_mph`, `hour_is_friendly`, `longest_friendly_window`, `build_verdict` exist and are import-clean

---

## Phase 4c — `today` subcommand

### Task 10: Add `cmd_today`
```python
def cmd_today(args: argparse.Namespace) -> None:
    hourly = fetch_hourly(HOME_LAT, HOME_LON)
    try:
        alerts = fetch_alerts(HOME_LAT, HOME_LON)
    except Exception as e:
        print(f"warning: alerts unavailable ({e})", file=sys.stderr)
        alerts = []
    verdict = build_verdict(hourly, alerts, THRESHOLDS)

    if args.format == "json":
        print(json.dumps(verdict, indent=2))
        return

    icon = "✅" if verdict["outdoor_work_friendly"] else "🚫"
    lines = alerts_banner(alerts)
    lines.append(f"{icon} **Outdoor work today:** {'yes' if verdict['outdoor_work_friendly'] else 'no'}")
    lines.append(f"- {verdict['reason']}")
    if verdict["best_window"]:
        lines.append(f"- Best window: **{verdict['best_window']}**")
    print("\n".join(lines))
```

### Task 11: Register the subparser (in `main`, alongside the others)
```python
p_today = sub.add_parser("today", help="Indoor/outdoor verdict for today")
p_today.add_argument("--format", choices=["json", "markdown"], default="json",
                     help="Output format (default json)")
p_today.set_defaults(func=cmd_today)
```

### Task 12: Bump the User-Agent version
`USER_AGENT = f"weather-tool/0.5 ({USER_AGENT_CONTACT})"` (was 0.4).

**Done When (4c):**
- [ ] `weather-tool today` prints a JSON verdict without crashing
- [ ] `weather-tool today --format markdown` prints the ✅/🚫 summary
- [ ] `weather-tool` (no args) still prints help; other subcommands unaffected

---

## Phase 4d — Verify against real NWS data + set up tuning

### Task 13: Capture two real fixtures on different days
```bash
weather-tool hourly --format json > tests/fixtures/hourly_sample1.json
# (another day / cache-miss) ->
weather-tool hourly --format json > tests/fixtures/hourly_sample2.json
```

### Task 14: Add a fixture-driven test that build_verdict handles real payloads
Load each fixture, call `build_verdict(fixture, [], THRESHOLDS)`, assert it returns a dict with all four keys and doesn't raise. (This is the "tested against ≥2 real NWS responses" gate.)

### Task 15: Record the tuning follow-up
Add a short note to `SPEC.md` (or a `current_context.md`) that the threshold values are provisional and should be revisited after a week of matching verdicts against how the day actually felt for outdoor work.

**Done When (4d):**
- [ ] Two real hourly fixtures saved under `tests/fixtures/`
- [ ] `uv run pytest -v` passes including the fixture test (and the existing 10)
- [ ] Tuning follow-up recorded

---

## Verification (whole phase)

- `uv run pytest -v` → green
- `weather-tool today` and `weather-tool today --format markdown` run against live/cached data without error
- Manual sanity check: does the verdict match what the raw `hourly` output implies for today?

## Risks, tradeoffs, open questions

- **Thresholds are guesses.** The verdict is only as good as the numbers; treat Phase 4 as scaffolding for the manual tuning loop, not a finished judgment. (Consistent with SPEC's "test manually for a week.")
- **"Today" late in the day** can yield zero remaining daylight hours → verdict returns `outdoor_work_friendly: false`, `best_window: null`, reason "No remaining daylight hours." Confirm that reads sensibly; consider a `--tomorrow` flag later (out of scope now, YAGNI).
- **Wind parsing** assumes mph integer tokens; NWS is consistent here, but `parse_wind_mph` degrades to 0 on anything odd (e.g. "calm") rather than crashing.
- **Open question:** should a moderate alert (e.g. a frost advisory) hard-block outdoor work, or just annotate? Current plan hard-blocks on *any* active alert. Revisit if that's too blunt.
- **Commit boundary:** weather-tool is its own repo (github.com/echeadle/weather-tool). Commit per phase (4a→4d), each after its Done When passes. Decide separately whether to commit `plans/` into that repo.

## Next steps (separate, approved)

- Optionally `/grill-me` the open question above (alert severity handling) before building.
- On approval, execute phase by phase; check each `Done When` before starting the next. Commit on request per phase.
