# Weather Forecast Tool — Spec (Draft)

Status: spec draft (not yet built)
Owner: Ed
Started: 2026-04-29

## Why this exists

A reusable weather lookup that other tools and skills can call. Two known consumers:

1. **`/schedule` skill (future)** — needs to answer "is the weather right for this task?" so it can schedule weather-dependent work (water plants, spray weed killer, powerwash decks, drip system, etc.)
2. **Weather subagent / "weather girl" (future, fun)** — conversational weather assistant

Manual version first. No automation until manual works.

## Use cases (concrete)

These are the questions the tool needs to answer. If it can answer these well, it's done.

- "Will it rain tomorrow morning?" (yes/no + confidence)
- "What's the high/low for the next 3 days?"
- "When is the next dry stretch of 4+ hours?" (for outdoor tasks needing dry conditions)
- "What does the 7-day look like?" (human-readable summary)
- "Any severe weather alerts in the next 48 hours?"
- (Stretch) "What's the monthly outlook?" — likely just averages + trend, not a real forecast

## Decisions needed (DECIDE before building)

These are the choices Ed needs to make. Answers shape the build.

1. **Data source.** ✓ DECIDED: **NWS API** (api.weather.gov). Free, no auth, US-only, government-backed. Utah is fully covered. Revisit when building the travel agency — at that point may add OpenWeather or similar for international coverage.
2. **Location handling.** ✓ DECIDED: hardcoded home lat/lon in the script. Refactor to a config file with named locations when a second location actually needs tracking (e.g., when travel agency comes online).
3. **Output format.** ✓ DECIDED: JSON first (default), markdown summary as a second view that reads the same JSON. CLI flag `--format json|markdown`. One source of truth, two views.
4. **Distribution.** ✓ DECIDED: **Python CLI script** first. Subcommands like `weather-tool current`, `weather-tool forecast --days 7`. Other tools (`/schedule`, subagent) shell out via Bash. Refactor to MCP server only if integration friction shows up.
5. **Caching.** ✓ DECIDED: file-based cache with 1-hour TTL at `~/.cache/weather-tool/`. Cheap, polite to NWS, and fast for back-to-back lookups. Principle: work with providers, don't take advantage of them.
6. **Granularity.** ✓ DECIDED: **both**. Daily summary for the 7-day outlook, hourly for next 48 hours. JSON exposes both; markdown view shows daily by default with `--detailed` flag to expose hourly.

## Functional requirements (proposed)

- Lookup current conditions
- 7-day daily forecast (high, low, precipitation chance, summary)
- Hourly forecast for next 48 hours
- Active alerts/warnings
- Output as JSON (machine) or markdown (human)
- Configurable location

## Out of scope

- Long-range climate forecasting beyond 7 days (NWS doesn't really provide it)
- Historical weather data
- Weather radar imagery
- Push notifications (that's `/schedule`'s job, not this tool's)

## Open questions — RESOLVED

- ✓ Multi-location? **No** — home only to start. Revisit when travel agency comes online.
- ✓ Most-needed use case? **Avoiding being caught off-guard, and indoor-vs-outdoor task prioritization.** The tool isn't just "what's the weather" — it's "should today be an indoor or outdoor work day?" Weather can interfere with most outdoor tasks (water plants, weed killer, drip system, powerwash, paint, weed wack) and seasonal tasks (deck opening/closing). Implication: a high-value query is "is today/tomorrow good for outdoor work?" — a derived yes/no answer based on temp + precip + wind, not just raw forecast data.
- ✓ Severe weather alerts? **Folded** into the regular forecast output. Alerts at the top of any forecast if active. Dedicated `alerts` subcommand can come later if needed.

## Derived design implication (from Q2)

Add a high-level `weather-tool today` (or similar) command that returns a simple verdict like:

```json
{
  "outdoor_work_friendly": true,
  "reason": "Sunny, 68°F, low precipitation chance",
  "best_window": "9am-3pm",
  "alerts": []
}
```

This is the answer to "indoor or outdoor day?" — the question Ed actually asks. Build on top of the raw forecast data, not separate from it.

## Next steps

1. Ed answers the DECIDE items and Open Questions above
2. Move this spec to `coding_projects/apps/weather-tool/SPEC.md`
3. Leave a one-line pointer here noting the move
4. Build the Python CLI version
5. Test it manually for a week against real outdoor tasks
6. Then consider wiring it into `/schedule` (which itself isn't built yet)
