# Weather Forecast Tool

A weather lookup tool for use by other tools and skills (e.g. `/schedule`, weather subagent).

## Status

Phase 3b complete (2026-04-30) — added `hourly` subcommand and active-alert banner folded into all forecast outputs. Next up is the `today` outdoor-friendly verdict (Phase 4).

## Files

- `SPEC.md` — design doc with all DECIDE items locked
- `weather_tool.py` — main script (single-file for now)
- `config.example.py` — copy to `config.py` and fill in your values
- `requirements.txt` — Python dependencies

## Setup

```bash
# Create a venv (uv shown; python -m venv also works)
uv venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure your location and contact info
cp config.example.py config.py
# Edit config.py — set HOME_LAT, HOME_LON, USER_AGENT_CONTACT

# Run — see available subcommands
python weather_tool.py

# 7-day forecast (JSON)
python weather_tool.py forecast

# 3-day forecast (human-readable)
python weather_tool.py forecast --days 3 --format markdown

# Next 24 hours, hourly
python weather_tool.py hourly --format markdown

# Current period only
python weather_tool.py current --format markdown
```

All forecast outputs include any active NWS alerts: as an `"alerts"` array
in the JSON wrapper, and as a brief banner above the markdown output.

`config.py` is gitignored. The `USER_AGENT_CONTACT` value goes into the User-Agent header on every NWS request — [NWS asks API users to identify themselves](https://www.weather.gov/documentation/services-web-api#/) with a contact address.

Forecasts are cached at `~/.cache/weather-tool/`: points metadata for 30 days, forecast data for 1 hour, alerts for 10 minutes.

## Origin

Spec drafted in `~/Projects/time_management/projects/weather-tool.md`,
moved here on 2026-04-29 when ownership shifted to the workshop.

## First session prompt

Paste this when you `cd` into this folder and start Claude for the first
build session. It's deliberate about what to read, what NOT to do
immediately, and what trade-offs to surface.

```
This is the first build session for the weather-tool. Before doing anything,
read these two files in full:

1. README.md — orientation
2. SPEC.md — full design with all DECIDE items locked

Important context about how I work:
- Slow, tested, one phase at a time
- Manual version works first, automation later
- I'm a retired developer learning to code — explain decisions and trade-offs
  rather than just writing code
- Python lives in ~/.venv (uv, Python 3.12.9) — activate with
  `source ~/.venv/bin/activate`
- Be polite to NWS: cache, reasonable User-Agent, conservative rate

After reading the spec, do NOT start coding. Instead, propose a phased build
plan. I'm thinking the first phase should be the smallest thing that proves
the foundation works — probably:

  Phase 1: Project skeleton + a single working call to NWS that fetches
           the current conditions for my home coordinates and prints
           the JSON response. No CLI framework yet, no caching yet,
           no formatting yet. Just prove the API call works.

But propose what you think Phase 1 should be, with reasoning. Then we'll
agree on it before any code gets written.

Two things I'll need from you upfront:
- My home lat/lon (I'll provide when you ask — don't guess)
- Which Python HTTP library to use and why (requests vs httpx vs stdlib)

Ask me anything else you need before proposing the plan.
```

### Why this prompt is structured this way

- **Read first, propose second, code third** — prevents Claude from diving
  into code before understanding the spec
- **States working preferences explicitly** — slow/tested/one-phase, manual-first,
  retired-dev-learning, the venv path
- **Pre-frames Phase 1 but invites pushback** — gives Claude a target while
  letting it propose better
- **Forces clarification upfront** — home coordinates and HTTP library choice
  surface before they become mid-build interruptions
- **Reinforces provider etiquette** — caching + User-Agent (NWS specifically
  asks API users to identify themselves with a contact email in the UA string)

When future projects start, copy this pattern: point at the spec, state working
preferences, name the phase, surface the questions you know are coming.
