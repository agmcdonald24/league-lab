"""Game-day weather from Open-Meteo (plan D3): stadium x kickoff hour -> ``raw.nfl_weather``.

Why: nflverse's schedules carry ``temp`` / ``wind`` only after a game is played (and no
precipitation), so the live board needs a forecast and training needs a history with the same
definition. Open-Meteo serves both by latitude / longitude, free, without a key:

* **history** ``archive-api.open-meteo.com/v1/archive`` (ERA5 / ERA5-Land reanalysis; ~5 days behind
  real time, ``ARCHIVE_DELAY``) -> ``source = 'archive'``, one row per game;
* **forecast** ``api.open-meteo.com/v1/forecast`` (up to 16 days ahead) -> ``source = 'forecast'``,
  one row per game *per fetch*, kept forever (``forecast_hours_ahead`` = kickoff - fetch). The archive
  never overwrites a forecast row: the two are different sources of the same game, and the forecast
  rows are what measures the train / serve gap (docs/METRICS.md § Weather).

What is fetched (``plan``): every game in ``raw.nfl_schedules`` (season >= seasons_start) whose venue is
open to the weather — an outdoor stadium, or a retractable roof that is open or not yet decided — at
the venue's coordinates from ``reference/stadiums.csv`` (the schedules' ``stadium_id`` is the key; a
name that belongs to another venue and the per-game corrections in ``reference/stadium_game_venues.csv``
come first: nflverse records several international games at the home team's stadium). Fixed domes and
closed roofs are never requested.

Batching (Open-Meteo's free tier: ~10k calls a day, counted per location x ~2 weeks x 10 variables):
**one archive call per stadium per season** covering all its games (date range first..last game), and
one forecast call per stadium per run for its games in the next 16 days — never one call per game.
Live calls are spaced ``MIN_REQUEST_INTERVAL`` apart; 429 / 5xx are retried by ``http.fetch_to_archive``.

Per game the hourly values are taken at the **kickoff hour and the two after it** (requested in UTC:
kickoff = ``gameday`` + ``gametime`` in US Eastern, which is how nflverse records every game, London
included; the UTC hour is the same instant as the local hour at the stadium). Instantaneous variables
(temperature, wind speed) are read at hours k, k+1, k+2; Open-Meteo's preceding-hour variables
(precipitation, rain, snowfall: sum of the preceding hour; gusts: maximum of the preceding hour) at
k+1, k+2, k+3, so both cover the game's first three hours [k, k+3). ``wind_mph`` / ``temp_f`` = the mean,
``gust_mph`` = the max, ``precip_in`` / ``snowfall_in`` = the sum (NULL unless all three hours are there),
``snow`` = any snowfall or a WMO snow code. Units are requested as °F, mph and inches.

Archive layout (replayable, like every source; ``--offline`` reads only these files):
    data/raw/open_meteo/archive/<season>/<stadium_id>.json.gz             one per stadium-season
    data/raw/open_meteo/forecast/<season>/<stadium_id>/<YYYYmmddTHHMMZ>.json.gz   one per stadium per fetch
each with the ``.meta.json`` sidecar ``http.fetch_to_archive`` writes. A stadium-season's archive file is
re-fetched only when a played game (older than ``ARCHIVE_DELAY``) is not inside it, so completed seasons
cost nothing after the first run and the current season about one call per stadium per home game.

Manifest: source ``open_meteo``, datasets ``archive`` and ``forecast``, partition ``<season>:<stadium_id>``
(the forecast partition = every forecast file of that stadium-season; its rows are rebuilt from all of
them, so a replay on a fresh database restores the full forecast history, and upserted, never deleted:
a forecast row outlives a lost file). The stadium reference is
source ``league_lab`` dataset ``stadiums``. ``raw.nfl_stadiums`` / ``raw.nfl_stadium_game_venues`` are
(re)loaded from the CSVs by ``db migrate`` so dbt can resolve venues before any weather is fetched.

Attribution: weather data by Open-Meteo.com (CC BY 4.0), ERA5 by the Copernicus Climate Change Service.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
import psycopg
from psycopg.types.json import Jsonb

from ..config import get_settings
from ..http import Fetched, FetchError, archived_at, fetch_to_archive, read_archive, read_meta
from ..manifest import LoadRecord, get_partition_state, record_manifest

log = logging.getLogger(__name__)

SOURCE = "open_meteo"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = ("temperature_2m", "precipitation", "rain", "snowfall", "weather_code", "wind_speed_10m", "wind_gusts_10m")
FORECAST_HOURLY = (*HOURLY, "precipitation_probability")
UNITS = {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch", "timezone": "GMT"}
# variables Open-Meteo reports for the PRECEDING hour (sum or max), read at k+1..k+3; the rest are instantaneous (k..k+2)
PRECEDING_HOUR = {"precipitation", "rain", "snowfall", "wind_gusts_10m"}
GAME_HOURS = 3
ARCHIVE_DELAY = timedelta(days=5)        # ERA5T reaches real time with ~5 days delay
ARCHIVE_GIVE_UP = timedelta(days=30)     # a game still without values this long after it is not re-fetched
FORECAST_DAYS = 16                       # the forecast API's horizon (today + 15)
FORECAST_MIN_AGE = timedelta(hours=6)    # a second run within 6 h replays the stadium's newest forecast instead
MIN_REQUEST_INTERVAL = 1.5               # seconds between live calls (600/min free-tier ceiling, weighted calls)
SNOW_CODES = {71, 73, 75, 77, 85, 86}    # WMO weather codes: snow fall / grains / showers
EASTERN = ZoneInfo("America/New_York")   # nflverse gametime is US Eastern for every game

REFERENCE_DIR = Path(__file__).with_name("reference")
STADIUMS_CSV = REFERENCE_DIR / "stadiums.csv"
GAME_VENUES_CSV = REFERENCE_DIR / "stadium_game_venues.csv"
ROOF_TYPES = ("outdoors", "dome", "retractable")

DDL = {
    "raw.nfl_weather": """
create table if not exists raw.nfl_weather (
    game_id              text not null,
    season               integer not null,
    week                 integer,
    stadium_id           text not null,            -- the venue the weather is for (reference/stadiums.csv)
    source               text not null check (source in ('archive', 'forecast')),
    fetched_at           timestamptz not null,     -- content time of the Open-Meteo answer (archive sidecar)
    kickoff_at           timestamptz not null,
    forecast_hours_ahead double precision,         -- forecast only: kickoff - fetched_at, hours
    wind_mph             double precision,         -- mean 10 m wind speed, kickoff hour and the two after
    gust_mph             double precision,         -- max 10 m gust over the game's first three hours
    precip_in            double precision,         -- precipitation (rain + snow water) over the first three hours
    rain_in              double precision,
    snowfall_in          double precision,
    snow                 boolean,                  -- any snowfall or a WMO snow code in those hours
    temp_f               double precision,         -- mean 2 m temperature
    weather_code         integer,                  -- highest WMO code over the hours
    precip_prob_pct      double precision,         -- forecast only: max precipitation probability
    n_hours              integer,                  -- game hours with wind and temperature present (0-3)
    grid_latitude        double precision,         -- the model grid point Open-Meteo answered for
    grid_longitude       double precision,
    elevation_m          double precision,
    hourly               jsonb,                    -- the hourly values used (k .. k+3), as returned
    file_path            text,
    _loaded_at           timestamptz not null default now(),
    primary key (game_id, source, fetched_at)
)""",
    "raw.nfl_weather_idx": "create index if not exists nfl_weather_partition_idx on raw.nfl_weather (source, season, stadium_id)",
    "raw.nfl_stadiums": """
create table if not exists raw.nfl_stadiums (
    stadium_id   text primary key,
    name         text not null,
    names        text[] not null,      -- every name nflverse has used for it (name first)
    city         text,
    country      text,
    latitude     double precision not null,
    longitude    double precision not null,
    timezone     text not null,
    roof_type    text not null check (roof_type in ('outdoors', 'dome', 'retractable')),
    tenants      text,                 -- 'BUF 2016-2026' ('|' between teams); empty for neutral-site venues
    in_nflverse  boolean not null,
    notes        text,
    _csv_sha256  text not null,
    _loaded_at   timestamptz not null default now()
)""",
    "raw.nfl_stadium_game_venues": """
create table if not exists raw.nfl_stadium_game_venues (
    game_id             text primary key,
    stadium_id          text not null,   -- where the game was played
    recorded_stadium_id text,            -- what nflverse records
    note                text,
    _csv_sha256         text not null,
    _loaded_at          timestamptz not null default now()
)""",
}


# ------------------------------------------------------------------------------ the stadium reference
@dataclass(frozen=True)
class Stadium:
    stadium_id: str
    name: str
    names: tuple[str, ...]
    city: str
    country: str
    latitude: float
    longitude: float
    timezone: str
    roof_type: str
    tenants: tuple[tuple[str, int, int], ...]
    in_nflverse: bool
    notes: str


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tenants(text: str) -> tuple[tuple[str, int, int], ...]:
    out = []
    for part in (text or "").split("|"):
        part = part.strip()
        if not part:
            continue
        team, years = part.split()
        first, last = years.split("-")
        out.append((team, int(first), int(last)))
    return tuple(out)


def load_stadiums(path: Path = STADIUMS_CSV) -> dict[str, Stadium]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out: dict[str, Stadium] = {}
    for r in rows:
        names = (r["name"], *[n.strip() for n in (r["other_names"] or "").split("|") if n.strip()])
        out[r["stadium_id"]] = Stadium(
            stadium_id=r["stadium_id"], name=r["name"], names=names, city=r["city"], country=r["country"],
            latitude=float(r["latitude"]), longitude=float(r["longitude"]), timezone=r["timezone"],
            roof_type=r["roof_type"], tenants=_tenants(r["tenants"]), in_nflverse=r["in_nflverse"].strip().lower() == "true",
            notes=r["notes"] or "",
        )
    return out


def load_game_venues(path: Path = GAME_VENUES_CSV) -> dict[str, str]:
    """game_id -> the stadium_id it was really played at (nflverse records another one)."""
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["game_id"]: r["stadium_id"] for r in csv.DictReader(fh)}


def resolve_venue(game_id: str, stadium_id: str | None, stadium_name: str | None, stadiums: Mapping[str, Stadium],
                  game_venues: Mapping[str, str]) -> tuple[str | None, str]:
    """(venue stadium_id, how it was resolved): a per-game correction, then a stadium name that belongs
    to another venue (2026_05_PHI_JAX: JAX00 'Tottenham Hotspur Stadium'), then the recorded id.
    The dbt twin is ``int_game_weather`` (same order)."""
    if game_id in game_venues:
        return game_venues[game_id], "game_override"
    if stadium_name:
        for s in stadiums.values():
            if stadium_name in s.names:
                if s.stadium_id != stadium_id:
                    return s.stadium_id, "stadium_name"
                break
    if stadium_id and stadium_id in stadiums:
        return stadium_id, "stadium_id"
    return None, "unresolved"


def sync_reference(conn: psycopg.Connection, record: bool = False) -> LoadRecord | None:
    """Create the weather tables and (re)load the stadium reference when its CSVs changed. Caller commits.

    Called by ``db migrate`` (so dbt can resolve venues on a database that never fetched weather) and by
    ``ingest weather`` (``record=True``: a manifest row when the reference changed)."""
    with conn.cursor() as cur:
        for ddl in DDL.values():
            cur.execute(ddl)
        sha = hashlib.sha256((_sha256_file(STADIUMS_CSV) + _sha256_file(GAME_VENUES_CSV)).encode()).hexdigest()
        cur.execute("select count(*), min(_csv_sha256), max(_csv_sha256) from raw.nfl_stadiums")
        n, lo, hi = cur.fetchone()
        if n and lo == hi == sha:
            return None
        stadiums, venues = load_stadiums(), load_game_venues()
        cur.execute("delete from raw.nfl_stadiums")
        cur.executemany(
            """insert into raw.nfl_stadiums (stadium_id, name, names, city, country, latitude, longitude, timezone,
                   roof_type, tenants, in_nflverse, notes, _csv_sha256) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [(s.stadium_id, s.name, list(s.names), s.city, s.country, s.latitude, s.longitude, s.timezone, s.roof_type,
              "|".join(f"{t} {a}-{b}" for t, a, b in s.tenants), s.in_nflverse, s.notes or None, sha) for s in stadiums.values()],
        )
        with open(GAME_VENUES_CSV, newline="", encoding="utf-8") as fh:
            gv = list(csv.DictReader(fh))
        cur.execute("delete from raw.nfl_stadium_game_venues")
        cur.executemany(
            """insert into raw.nfl_stadium_game_venues (game_id, stadium_id, recorded_stadium_id, note, _csv_sha256)
               values (%s,%s,%s,%s,%s)""",
            [(r["game_id"], r["stadium_id"], r["recorded_stadium_id"] or None, r["note"] or None, sha) for r in gv],
        )
    log.info("stadium reference loaded: %s stadiums, %s per-game venue corrections", len(stadiums), len(venues))
    if not record:
        return None
    rec = LoadRecord(source="league_lab", dataset="stadiums", partition_key="all", source_url=str(STADIUMS_CSV),
                     fetched_at=datetime.now(UTC), checksum_sha256=sha, row_count=len(stadiums), file_path=str(STADIUMS_CSV))
    record_manifest(conn, rec)
    return rec


def ensure_tables(conn: psycopg.Connection) -> None:
    sync_reference(conn)
    conn.commit()


# ------------------------------------------------------------------------------ games and what to fetch
@dataclass(frozen=True)
class Game:
    game_id: str
    season: int
    week: int | None
    kickoff: datetime                # UTC
    stadium_id: str | None           # the venue (resolved)
    recorded_stadium_id: str | None  # what nflverse records
    roof: str | None                 # the schedules' roof for this game (retractables: open / closed / unknown)
    resolved_by: str = "stadium_id"


def kickoff_utc(gameday: str | date, gametime: str | None) -> datetime:
    """nflverse ``gameday`` + ``gametime`` (US Eastern, every game) -> UTC (13:00 when the time is missing,
    as ``stg_nflverse__games`` does)."""
    d = gameday if isinstance(gameday, date) else date.fromisoformat(str(gameday)[:10])
    hh, mm = (gametime or "13:00").split(":")[:2]
    return datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=EASTERN).astimezone(UTC)


def make_game(row: Mapping[str, Any], stadiums: Mapping[str, Stadium], game_venues: Mapping[str, str]) -> Game:
    venue, how = resolve_venue(row["game_id"], row.get("stadium_id"), row.get("stadium"), stadiums, game_venues)
    return Game(game_id=row["game_id"], season=int(row["season"]), week=row.get("week"),
                kickoff=kickoff_utc(row["gameday"], row.get("gametime")), stadium_id=venue,
                recorded_stadium_id=row.get("stadium_id"), roof=(row.get("roof") or None), resolved_by=how)


def read_games(conn: psycopg.Connection, seasons: Iterable[int] | None, stadiums: Mapping[str, Stadium],
               game_venues: Mapping[str, str]) -> list[Game]:
    s = get_settings()
    with conn.cursor() as cur:
        cur.execute("""select game_id, season, week, gameday, gametime, stadium_id, stadium, roof
                       from raw.nfl_schedules where season >= %s and gameday is not null order by gameday, game_id""",
                    (s.seasons_start,))
        names = [d.name for d in cur.description]
        rows = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
    wanted = set(seasons) if seasons else None
    games = [make_game(r, stadiums, game_venues) for r in rows if wanted is None or int(r["season"]) in wanted]
    bad = [g for g in games if g.stadium_id is None]
    if bad:
        log.warning("%s game(s) at a stadium the reference does not know (add it to %s): %s", len(bad), STADIUMS_CSV.name,
                    ", ".join(f"{g.game_id} ({g.recorded_stadium_id})" for g in bad[:10]))
    return games


def open_to_weather(game: Game, stadiums: Mapping[str, Stadium]) -> bool:
    """Does the weather reach the field? Outdoor venue: yes (whatever the schedules' roof says: nflverse
    calls some open-air international venues 'dome'). Fixed dome: no. Retractable roof: unless closed
    (open, or not decided yet: an upcoming game, fetched so the forecast exists either way)."""
    st = stadiums.get(game.stadium_id or "")
    if st is None or st.roof_type == "dome":
        return False
    if st.roof_type == "retractable":
        return (game.roof or "").lower() not in ("closed", "dome")
    return True


def game_hours(kickoff: datetime) -> tuple[list[datetime], list[datetime]]:
    """(instantaneous hours k..k+2, preceding-hour hours k+1..k+3) for a kickoff (UTC); k = the kickoff hour."""
    k = kickoff.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    inst = [k + timedelta(hours=i) for i in range(GAME_HOURS)]
    return inst, [h + timedelta(hours=1) for h in inst]


def _date_range(games: Iterable[Game]) -> tuple[date, date]:
    gs = list(games)
    first = min(game_hours(g.kickoff)[0][0] for g in gs).date()
    last = max(game_hours(g.kickoff)[1][-1] for g in gs).date()
    return first, last


def request_url(base: str, st: Stadium, start: date, end: date, hourly: Iterable[str]) -> str:
    params = {"latitude": f"{st.latitude:.4f}", "longitude": f"{st.longitude:.4f}", "start_date": start.isoformat(),
              "end_date": end.isoformat(), "hourly": ",".join(hourly), **UNITS}
    return f"{base}?{urlencode(params, safe=',')}"


# ------------------------------------------------------------------------------ parsing an answer
def _parse_times(payload: Mapping[str, Any]) -> list[datetime]:
    """Open-Meteo hourly ``time`` (ISO8601 local to ``utc_offset_seconds``, or unixtime) -> UTC datetimes."""
    times = (payload.get("hourly") or {}).get("time") or []
    offset = timedelta(seconds=int(payload.get("utc_offset_seconds") or 0))
    out = []
    for t in times:
        if isinstance(t, (int, float)):
            out.append(datetime.fromtimestamp(t, UTC))
        else:
            out.append(datetime.fromisoformat(t).replace(tzinfo=UTC) - offset)
    return out


def coverage(payload: Mapping[str, Any]) -> tuple[datetime, datetime] | None:
    times = _parse_times(payload)
    return (min(times), max(times)) if times else None


def covers(payload: Mapping[str, Any], game: Game) -> bool:
    span = coverage(payload)
    if span is None:
        return False
    inst, prec = game_hours(game.kickoff)
    return span[0] <= inst[0] and prec[-1] <= span[1]


def archive_covers(payload: Mapping[str, Any], fetched_at: datetime, game: Game) -> bool:
    """Does an archived answer already hold this played game? Its hours are inside it with wind and
    temperature present — or inside it and fetched ``ARCHIVE_GIVE_UP`` after the game (a hole the archive
    will not fill: the row keeps NULLs instead of re-fetching the stadium-season every night)."""
    if not covers(payload, game):
        return False
    w = summarize_game(payload, game)
    return bool(w and w["n_hours"]) or fetched_at - game.kickoff > ARCHIVE_GIVE_UP


def _num(v: Any) -> float | None:
    return None if v is None else float(v)


def summarize_game(payload: Mapping[str, Any], game: Game) -> dict[str, Any] | None:
    """The game's weather from an hourly answer that covers it (None when it does not)."""
    if not covers(payload, game):
        return None
    hourly = payload["hourly"]
    index = {t: i for i, t in enumerate(_parse_times(payload))}
    inst, prec = game_hours(game.kickoff)

    def vals(var: str) -> list[float | None]:
        series = hourly.get(var)
        if series is None:
            return [None] * GAME_HOURS
        hours = prec if var in PRECEDING_HOUR else inst
        return [_num(series[index[h]]) if h in index else None for h in hours]

    def mean(xs: list[float | None]) -> float | None:
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 2) if xs else None

    def total(xs: list[float | None]) -> float | None:          # a sum needs every hour (a gap would understate it)
        return round(sum(xs), 3) if xs and all(x is not None for x in xs) else None

    def peak(xs: list[float | None]) -> float | None:
        xs = [x for x in xs if x is not None]
        return max(xs) if xs else None

    wind, temp = vals("wind_speed_10m"), vals("temperature_2m")
    snowfall, codes = vals("snowfall"), vals("weather_code")
    snow_total = total(snowfall)
    any_code = [int(c) for c in codes if c is not None]
    snow: bool | None
    if snow_total is None and not any_code:
        snow = None
    else:
        snow = bool((snow_total or 0) > 0 or any(c in SNOW_CODES for c in any_code))
    window = sorted({*inst, *prec})
    slice_ = {"time": [h.strftime("%Y-%m-%dT%H:%M") for h in window]}
    for var, series in hourly.items():
        if var != "time" and isinstance(series, list):
            slice_[var] = [series[index[h]] if h in index else None for h in window]
    return {
        "wind_mph": mean(wind), "gust_mph": peak(vals("wind_gusts_10m")), "precip_in": total(vals("precipitation")),
        "rain_in": total(vals("rain")), "snowfall_in": snow_total, "snow": snow, "temp_f": mean(temp),
        "weather_code": max(any_code) if any_code else None, "precip_prob_pct": peak(vals("precipitation_probability")),
        "n_hours": sum(1 for w, t in zip(wind, temp, strict=True) if w is not None and t is not None),
        "grid_latitude": _num(payload.get("latitude")), "grid_longitude": _num(payload.get("longitude")),
        "elevation_m": _num(payload.get("elevation")), "hourly": slice_,
    }


def weather_rows(payload: Mapping[str, Any], games: Iterable[Game], source: str, fetched_at: datetime,
                 file_path: str | None = None) -> list[dict[str, Any]]:
    """raw.nfl_weather rows for the games an answer covers. A forecast row only for a game that had not
    kicked off when the forecast was fetched (anything else is not a forecast)."""
    rows = []
    for g in games:
        if source == "forecast" and g.kickoff <= fetched_at:
            continue
        w = summarize_game(payload, g)
        if w is None:
            continue
        rows.append({
            "game_id": g.game_id, "season": g.season, "week": g.week, "stadium_id": g.stadium_id, "source": source,
            "fetched_at": fetched_at, "kickoff_at": g.kickoff,
            "forecast_hours_ahead": round((g.kickoff - fetched_at).total_seconds() / 3600, 1) if source == "forecast" else None,
            **w, "file_path": file_path,
        })
    return rows


# ------------------------------------------------------------------------------ where rows go
class Store(Protocol):
    def partition_state(self, dataset: str, partition_key: str) -> dict[str, Any] | None: ...
    def replace(self, source: str, season: int, stadium_id: str, rows: list[dict[str, Any]], rec: LoadRecord) -> int: ...
    def record(self, rec: LoadRecord) -> None: ...


WEATHER_COLUMNS = ["game_id", "season", "week", "stadium_id", "source", "fetched_at", "kickoff_at", "forecast_hours_ahead",
                   "wind_mph", "gust_mph", "precip_in", "rain_in", "snowfall_in", "snow", "temp_f", "weather_code",
                   "precip_prob_pct", "n_hours", "grid_latitude", "grid_longitude", "elevation_m", "hourly", "file_path"]


class PgStore:
    """raw.nfl_weather + the load manifest. One transaction per partition (rows + manifest row)."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def partition_state(self, dataset: str, partition_key: str) -> dict[str, Any] | None:
        return get_partition_state(self.conn, SOURCE, dataset, partition_key)

    def replace(self, source: str, season: int, stadium_id: str, rows: list[dict[str, Any]], rec: LoadRecord) -> int:
        """Archive: the stadium-season's rows are replaced (one per game, the newest answer). Forecast:
        upserted and never deleted — a forecast cannot be fetched again, so a row outlives its file."""
        cols = ", ".join(WEATHER_COLUMNS)
        marks = ", ".join(["%s"] * len(WEATHER_COLUMNS))
        updates = ", ".join(f"{c} = excluded.{c}" for c in WEATHER_COLUMNS if c not in ("game_id", "source", "fetched_at"))
        try:
            with self.conn.transaction(), self.conn.cursor() as cur:
                if source == "archive":
                    cur.execute("delete from raw.nfl_weather where source = %s and season = %s and stadium_id = %s",
                                (source, season, stadium_id))
                if rows:
                    cur.executemany(f"""insert into raw.nfl_weather ({cols}) values ({marks})
                                        on conflict (game_id, source, fetched_at) do update set {updates}, _loaded_at = now()""",
                                    [tuple(Jsonb(r[c]) if c == "hourly" else r[c] for c in WEATHER_COLUMNS) for r in rows])
                rec.row_count = len(rows)
                record_manifest(self.conn, rec)
            self.conn.commit()
        except Exception as exc:
            self.conn.rollback()
            rec.status, rec.error = "failed", f"{type(exc).__name__}: {exc}"
            self.record(rec)
            log.exception("weather load failed for %s %s", rec.dataset, rec.partition_key)
        return rec.row_count or 0

    def record(self, rec: LoadRecord) -> None:
        record_manifest(self.conn, rec)
        self.conn.commit()


# ------------------------------------------------------------------------------ the run
@dataclass
class WeatherRun:
    games: list[Game]
    stadiums: Mapping[str, Stadium]
    store: Store
    raw_dir: Path
    seasons: list[int] | None = None
    offline: bool = False
    forecast: bool = False
    force: bool = False
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    client: httpx.Client | None = None
    min_interval: float = MIN_REQUEST_INTERVAL
    results: list[LoadRecord] = field(default_factory=list)
    calls: int = 0
    _last_call: float = 0.0

    # ---- paths and fetching ---------------------------------------------------------
    @property
    def archive_root(self) -> Path:
        return self.raw_dir / SOURCE

    def archive_path(self, season: int, stadium_id: str) -> Path:
        return self.archive_root / "archive" / str(season) / f"{stadium_id}.json.gz"

    def forecast_dir(self, season: int, stadium_id: str) -> Path:
        return self.archive_root / "forecast" / str(season) / stadium_id

    def _fetch(self, url: str, path: Path, offline: bool) -> Fetched:
        if not offline:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0 and self.calls:
                time.sleep(wait)
            self.calls += 1
            self._last_call = time.monotonic()
        return fetch_to_archive(url, path, conditional=False, offline=offline, client=self.client, compress=True)

    def _wanted(self, season: int) -> bool:
        return not self.seasons or season in self.seasons

    def _games_at(self, season: int, stadium_id: str) -> list[Game]:
        return [g for g in self.games if g.season == season and g.stadium_id == stadium_id]

    def _fail(self, rec: LoadRecord, error: str) -> LoadRecord:
        rec.status, rec.error = "failed", error
        self.store.record(rec)
        self.results.append(rec)
        log.warning("%s %s: %s", rec.dataset, rec.partition_key, error)
        return rec

    # ---- the archive (history) ------------------------------------------------------------
    def archive_plan(self) -> dict[tuple[int, str], list[Game]]:
        """(season, stadium) -> the played games open to the weather that the archive can answer
        (kickoff + the game window + ARCHIVE_DELAY before now). One request per key."""
        plan: dict[tuple[int, str], list[Game]] = defaultdict(list)
        for g in self.games:
            if not self._wanted(g.season) or not open_to_weather(g, self.stadiums):
                continue
            if game_hours(g.kickoff)[1][-1] + ARCHIVE_DELAY > self.now:
                continue
            plan[(g.season, g.stadium_id)].append(g)
        return dict(sorted(plan.items()))

    def load_archive(self, season: int, stadium_id: str, planned: list[Game] | None) -> LoadRecord:
        """One stadium-season. Live: fetch unless the archived file already covers every planned game.
        Offline (``planned`` None): replay the archived file."""
        st = self.stadiums[stadium_id]
        path = self.archive_path(season, stadium_id)
        key = f"{season}:{stadium_id}"
        offline = self.offline or planned is None
        if planned:
            start, end = _date_range(planned)
            url = request_url(ARCHIVE_URL, st, start, end, HOURLY)
            if not offline and not self.force and path.exists():
                try:
                    cached, cached_at = json.loads(read_archive(path)), archived_at(path, read_meta(path))
                    if all(archive_covers(cached, cached_at, g) for g in planned):
                        offline = True            # nothing new for this stadium-season: replay the file
                except (OSError, ValueError):
                    pass
        else:
            url = (read_meta(path) or {}).get("url") or str(path)
        rec = LoadRecord(source=SOURCE, dataset="archive", partition_key=key, source_url=url)
        try:
            fetched = self._fetch(url, path, offline)
            payload = json.loads(fetched.content)
        except (FetchError, ValueError) as exc:
            return self._fail(rec, str(exc))
        if not isinstance(payload, dict) or payload.get("error"):
            return self._fail(rec, f"Open-Meteo error: {payload.get('reason') if isinstance(payload, dict) else payload!r}")
        rec.fetched_at, rec.checksum_sha256, rec.file_path = fetched.fetched_at, fetched.checksum, str(fetched.path)
        rec.source_url = fetched.url
        return self._load(rec, "archive", season, stadium_id,
                          weather_rows(payload, self._games_at(season, stadium_id), "archive", fetched.fetched_at, str(path)))

    # ---- forecasts -------------------------------------------------------------------------
    def forecast_plan(self) -> dict[tuple[int, str], list[Game]]:
        """(season, stadium) -> games open to the weather that kick off after now and end within the
        forecast horizon. One request per stadium."""
        horizon = datetime.combine(self.now.date() + timedelta(days=FORECAST_DAYS - 1), datetime.max.time(), UTC)
        plan: dict[tuple[int, str], list[Game]] = defaultdict(list)
        for g in self.games:
            if not self._wanted(g.season) or not open_to_weather(g, self.stadiums):
                continue
            if self.now < g.kickoff and game_hours(g.kickoff)[1][-1] <= horizon:
                plan[(g.season, g.stadium_id)].append(g)
        return dict(sorted(plan.items()))

    def fetch_forecast(self, season: int, stadium_id: str, games: list[Game]) -> bool:
        """A new forecast file for the stadium (False: failed or skipped because a recent one exists)."""
        d = self.forecast_dir(season, stadium_id)
        newest = max(d.glob("*.json.gz"), default=None) if d.exists() else None
        if newest is not None and not self.force:
            age = self.now - archived_at(newest, read_meta(newest))
            if age < FORECAST_MIN_AGE:
                log.info("forecast %s:%s is %s old; not fetched again", season, stadium_id, age)
                return False
        start, end = _date_range(games)
        url = request_url(FORECAST_URL, self.stadiums[stadium_id], max(start, self.now.date()), end, FORECAST_HOURLY)
        path = d / f"{self.now:%Y%m%dT%H%MZ}.json.gz"
        try:
            fetched = self._fetch(url, path, offline=False)
            payload = json.loads(fetched.content)
            if not isinstance(payload, dict) or payload.get("error"):
                raise ValueError(f"Open-Meteo error: {payload.get('reason') if isinstance(payload, dict) else payload!r}")
        except (FetchError, ValueError) as exc:
            path.unlink(missing_ok=True)
            path.with_name(path.name + ".meta.json").unlink(missing_ok=True)
            self._fail(LoadRecord(source=SOURCE, dataset="forecast", partition_key=f"{season}:{stadium_id}", source_url=url), str(exc))
            return False
        return True

    def load_forecasts(self, season: int, stadium_id: str) -> LoadRecord:
        """Every archived forecast of a stadium-season -> its forecast rows (rebuilt from all files, so a
        replay restores the whole forecast history). The partition checksum comes from the sidecars, so an
        unchanged stadium-season is skipped without parsing its files."""
        d = self.forecast_dir(season, stadium_id)
        files = sorted(d.glob("*.json.gz"))
        rec = LoadRecord(source=SOURCE, dataset="forecast", partition_key=f"{season}:{stadium_id}", file_path=str(d))
        if not files:
            return self._fail(rec, f"no forecast files in {d}")
        metas = {f: read_meta(f) or {} for f in files}
        sums = [f"{f.name}:{m.get('sha256') or hashlib.sha256(read_archive(f)).hexdigest()}" for f, m in metas.items()]
        rec.checksum_sha256 = hashlib.sha256("\n".join(sums).encode()).hexdigest()
        rec.fetched_at, rec.source_url = archived_at(files[-1], metas[files[-1]]), metas[files[-1]].get("url") or str(files[-1])
        prior = self.store.partition_state(rec.dataset, rec.partition_key)
        if prior and prior["checksum_sha256"] == rec.checksum_sha256 and not self.force:
            return self._load(rec, "forecast", season, stadium_id, [])
        games = self._games_at(season, stadium_id)
        rows: list[dict[str, Any]] = []
        for f in files:
            try:
                fetched = fetch_to_archive(metas[f].get("url") or str(f), f, offline=True)
                payload = json.loads(fetched.content)
            except (FetchError, ValueError) as exc:
                return self._fail(rec, f"{f.name}: {exc}")
            if isinstance(payload, dict) and not payload.get("error"):
                rows += weather_rows(payload, games, "forecast", fetched.fetched_at, str(f))
        return self._load(rec, "forecast", season, stadium_id, rows)

    # ---- shared tail -------------------------------------------------------------------------
    def _load(self, rec: LoadRecord, source: str, season: int, stadium_id: str, rows: list[dict[str, Any]]) -> LoadRecord:
        prior = self.store.partition_state(rec.dataset, rec.partition_key)
        if prior and prior["checksum_sha256"] == rec.checksum_sha256 and not self.force:
            rec.status, rec.row_count = "skipped_unchanged", prior["row_count"]
            self.store.record(rec)
        else:
            self.store.replace(source, season, stadium_id, rows, rec)
            if rec.status == "success":
                log.info("weather %s %s: %s rows", rec.dataset, rec.partition_key, rec.row_count)
        self.results.append(rec)
        return rec

    def _archived(self, kind: str) -> list[tuple[int, str]]:
        """(season, stadium) partitions present in the archive for ``kind`` ('archive' | 'forecast')."""
        root = self.archive_root / kind
        if not root.exists():
            return []
        out = []
        for sdir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit()):
            season = int(sdir.name)
            if not self._wanted(season):
                continue
            if kind == "archive":
                out += [(season, f.name.removesuffix(".json.gz")) for f in sorted(sdir.glob("*.json.gz"))]
            else:
                out += [(season, p.name) for p in sorted(sdir.iterdir()) if p.is_dir() and any(p.glob("*.json.gz"))]
        return [(s, st) for s, st in out if st in self.stadiums]

    def run(self) -> list[LoadRecord]:
        if self.offline:
            for season, st in self._archived("archive"):
                self.load_archive(season, st, None)
            for season, st in self._archived("forecast"):
                self.load_forecasts(season, st)
            if not self.results:
                log.info("no Open-Meteo archive under %s yet: nothing to replay", self.archive_root)
            return self.results
        for (season, st), planned in self.archive_plan().items():
            self.load_archive(season, st, planned)
        if self.forecast:
            for (season, st), games in self.forecast_plan().items():
                self.fetch_forecast(season, st, games)
            # every stadium-season with forecast files (new or not) is reloaded when its files changed
            for season, st in self._archived("forecast"):
                self.load_forecasts(season, st)
        log.info("weather: %s live call(s) to Open-Meteo", self.calls)
        return self.results


def ingest_weather(conn: psycopg.Connection, seasons: list[int] | None = None, *, offline: bool = False,
                   forecast: bool = False, force: bool = False, now: datetime | None = None,
                   client: httpx.Client | None = None) -> list[LoadRecord]:
    """``league-lab ingest weather``: the stadium reference, then the archive for ``seasons`` (default:
    every season with games), then (``forecast``) the forecasts for the next 16 days. ``offline``
    replays every archived Open-Meteo file and never touches the network."""
    s = get_settings()
    ref = sync_reference(conn, record=True)
    conn.commit()
    stadiums, venues = load_stadiums(), load_game_venues()
    games = read_games(conn, seasons, stadiums, venues)
    run = WeatherRun(games=games, stadiums=stadiums, store=PgStore(conn), raw_dir=s.raw_dir, seasons=seasons,
                     offline=offline, forecast=forecast, force=force, now=now or datetime.now(UTC), client=client)
    own = client is None and not offline
    if own:
        run.client = httpx.Client(timeout=httpx.Timeout(s.http_timeout_seconds, connect=30.0), follow_redirects=True,
                                  headers={"User-Agent": "league-lab/0.1 (+local analytics)"}, trust_env=True)
    try:
        results = run.run()
    finally:
        if own and run.client is not None:
            run.client.close()
    return ([ref] if ref else []) + results
