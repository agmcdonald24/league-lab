"""Write the Open-Meteo fixtures tests/test_weather.py replays (hand-built, never fetched).

Open-Meteo (archive-api.open-meteo.com, api.open-meteo.com) is blocked from the development sandbox,
so these answers are built by hand in the shape its documentation gives for an hourly request
(``latitude``, ``longitude``, ``generationtime_ms``, ``utc_offset_seconds``, ``timezone``,
``timezone_abbreviation``, ``elevation``, ``hourly_units``, ``hourly`` = ``time`` + one array per
variable; ``timezone=GMT`` so ``time`` is UTC ISO8601 without an offset; units as requested: °F,
mp/h, inch; the forecast adds ``precipitation_probability`` in %; an error is HTTP 400 with
``{"error": true, "reason": ...}``). The values are invented: a quiet background, and chosen
numbers in the hours of the test games so the expected aggregates can be worked out by hand
(tests/test_weather.py says which).

Usage:  uv run python tests/fixtures/open_meteo/make_open_meteo_fixtures.py   (rewrites the *.json here)
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARCHIVE_VARS = ["temperature_2m", "precipitation", "rain", "snowfall", "weather_code", "wind_speed_10m", "wind_gusts_10m"]
FORECAST_VARS = [*ARCHIVE_VARS, "precipitation_probability"]
UNITS = {"time": "iso8601", "temperature_2m": "°F", "precipitation": "inch", "rain": "inch", "snowfall": "inch",
         "weather_code": "wmo code", "wind_speed_10m": "mp/h", "wind_gusts_10m": "mp/h", "precipitation_probability": "%"}


def h(y: int, m: int, d: int, hour: int) -> datetime:
    return datetime(y, m, d, hour, tzinfo=UTC)


def answer(lat: float, lon: float, elevation: float, start: date, end: date, variables: list[str],
           overrides: dict[datetime, dict[str, float]], background: dict[str, float]) -> dict:
    t0 = datetime(start.year, start.month, start.day, tzinfo=UTC)
    hours = [t0 + timedelta(hours=i) for i in range(((end - start).days + 1) * 24)]
    hourly: dict[str, list] = {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in hours]}
    for v in variables:
        hourly[v] = [overrides.get(x, {}).get(v, background[v]) for x in hours]
    return {
        "latitude": lat, "longitude": lon, "generationtime_ms": 0.42, "utc_offset_seconds": 0, "timezone": "GMT",
        "timezone_abbreviation": "GMT", "elevation": elevation,
        "hourly_units": {k: UNITS[k] for k in ["time", *variables]}, "hourly": hourly,
    }


QUIET = {"temperature_2m": 55.0, "precipitation": 0.0, "rain": 0.0, "snowfall": 0.0, "weather_code": 1,
         "wind_speed_10m": 6.0, "wind_gusts_10m": 12.0, "precipitation_probability": 5}


def game(inst_start: datetime, temps, winds, gusts, precips, codes, snows=(0.0, 0.0, 0.0), probs=(None, None, None)):
    """Overrides for one game: instantaneous values at k..k+2, preceding-hour values at k+1..k+3."""
    out: dict[datetime, dict[str, float]] = {}
    for i in range(3):
        out.setdefault(inst_start + timedelta(hours=i), {}).update(
            {"temperature_2m": temps[i], "wind_speed_10m": winds[i], "weather_code": codes[i]})
        p = {"wind_gusts_10m": gusts[i], "precipitation": precips[i], "rain": round(precips[i] - snows[i] / 10, 3),
             "snowfall": snows[i]}
        if probs[i] is not None:
            p["precipitation_probability"] = probs[i]
        out.setdefault(inst_start + timedelta(hours=i + 1), {}).update(p)
    return out


FIXTURES: dict[str, dict] = {
    # BUF00 2024: three home games, one archive call (2024-09-08 .. 2024-09-15)
    "archive_BUF00_2024.json": answer(
        42.77, -78.79, 197.0, date(2024, 9, 8), date(2024, 9, 15), ARCHIVE_VARS,
        {**game(h(2024, 9, 8, 17), (61, 63, 65), (12, 15, 18), (21, 27, 24), (0.02, 0.05, 0.01), (61, 63, 61)),
         **game(h(2024, 9, 13, 0), (58, 57, 56), (5, 6, 7), (10, 11, 12), (0.0, 0.0, 0.0), (1, 1, 2)),
         **game(h(2024, 9, 15, 17), (70, 71, 72), (9, 10, 11), (15, 16, 17), (0.0, 0.0, 0.0), (0, 0, 1))},
        QUIET),
    # IND00 2024: the one open-roof game
    "archive_IND00_2024.json": answer(
        39.75, -86.16, 218.0, date(2024, 10, 6), date(2024, 10, 6), ARCHIVE_VARS,
        game(h(2024, 10, 6, 17), (68, 69, 70), (4, 5, 6), (9, 9, 10), (0.0, 0.0, 0.0), (0, 0, 0)), QUIET),
    # BUF00 2025: a December game (EST: 13:00 ET = 18:00 UTC), snow
    "archive_BUF00_2025.json": answer(
        42.77, -78.79, 197.0, date(2025, 12, 14), date(2025, 12, 14), ARCHIVE_VARS,
        game(h(2025, 12, 14, 18), (28, 27, 26), (20, 22, 21), (30, 34, 33), (0.03, 0.04, 0.02), (73, 75, 73),
             snows=(0.3, 0.4, 0.2)), QUIET),
    # DUB00 2025: the Dublin game nflverse records at PIT00 (09:30 ET = 13:30 UTC -> hour 13)
    "archive_DUB00_2025.json": answer(
        53.36, -6.25, 12.0, date(2025, 9, 28), date(2025, 9, 28), ARCHIVE_VARS,
        game(h(2025, 9, 28, 13), (59, 60, 61), (14, 16, 18), (25, 26, 29), (0.01, 0.0, 0.0), (51, 3, 2)), QUIET),
    # BUF00 2026, first answer: covers the week-1 game only (the week-4 game is inside the archive delay)
    "archive_BUF00_2026.json": answer(
        42.77, -78.79, 197.0, date(2026, 9, 13), date(2026, 9, 13), ARCHIVE_VARS,
        game(h(2026, 9, 13, 17), (75, 76, 77), (3, 4, 5), (8, 8, 9), (0.0, 0.0, 0.0), (0, 0, 0)), QUIET),
    # BUF00 2026, ten days later: week 1 and week 4
    "archive_BUF00_2026_b.json": answer(
        42.77, -78.79, 197.0, date(2026, 9, 13), date(2026, 9, 28), ARCHIVE_VARS,
        {**game(h(2026, 9, 13, 17), (75, 76, 77), (3, 4, 5), (8, 8, 9), (0.0, 0.0, 0.0), (0, 0, 0)),
         **game(h(2026, 9, 28, 0), (50, 49, 48), (11, 12, 13), (19, 20, 21), (0.1, 0.1, 0.1), (63, 63, 63))},
        QUIET),
    # BUF00 2026, once the 2026-10-04 game is archivable too (it was also forecast twice)
    "archive_BUF00_2026_c.json": answer(
        42.77, -78.79, 197.0, date(2026, 9, 13), date(2026, 10, 4), ARCHIVE_VARS,
        {**game(h(2026, 9, 13, 17), (75, 76, 77), (3, 4, 5), (8, 8, 9), (0.0, 0.0, 0.0), (0, 0, 0)),
         **game(h(2026, 9, 28, 0), (50, 49, 48), (11, 12, 13), (19, 20, 21), (0.1, 0.1, 0.1), (63, 63, 63)),
         **game(h(2026, 10, 4, 17), (47, 46, 45), (17, 19, 21), (27, 30, 33), (0.06, 0.09, 0.05), (63, 65, 63))},
        QUIET),
    # BUF00 2026-10-04 13:00 ET (17:00 UTC): two forecasts, fetched 2026-10-01 12:00Z and 2026-10-02 12:00Z
    "forecast_BUF00_2026_a.json": answer(
        42.77, -78.79, 197.0, date(2026, 10, 4), date(2026, 10, 4), FORECAST_VARS,
        game(h(2026, 10, 4, 17), (52, 53, 54), (10, 11, 12), (18, 19, 20), (0.0, 0.01, 0.0), (2, 3, 3),
             probs=(20, 35, 30)), QUIET),
    "forecast_BUF00_2026_b.json": answer(
        42.77, -78.79, 197.0, date(2026, 10, 4), date(2026, 10, 4), FORECAST_VARS,
        game(h(2026, 10, 4, 17), (49, 48, 47), (14, 16, 18), (24, 28, 31), (0.05, 0.08, 0.04), (61, 63, 63),
             probs=(70, 85, 80)), QUIET),
    "error_400.json": {"error": True, "reason": "Parameter 'end_date' is out of allowed range from 1940-01-01 to 2026-09-26"},
}


def main() -> None:
    for name, payload in FIXTURES.items():
        (HERE / name).write_text(json.dumps(payload, separators=(",", ":")) + "\n")
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
