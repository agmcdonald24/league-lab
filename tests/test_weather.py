"""Plan D3: the Open-Meteo weather loader and the stadium reference (no database, no network).

The Open-Meteo answers are fixtures hand-built from the documented response format
(tests/fixtures/open_meteo/make_open_meteo_fixtures.py; Open-Meteo is unreachable from the
development sandbox), served through ``httpx.MockTransport``; rows go to an in-memory store that
behaves like ``PgStore`` (replace a partition, keep the manifest state).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from league_lab import http as http_mod
from league_lab.config import PROJECT_ROOT, get_settings
from league_lab.ingest import weather as wx
from league_lab.manifest import LoadRecord

FIX = Path(__file__).parent / "fixtures" / "open_meteo"
STADIUMS = wx.load_stadiums()
VENUES = wx.load_game_venues()
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

# (kind, start_date, end_date, latitude) -> fixture
ROUTES = {
    ("archive", "2024-09-08", "2024-09-15", "42.7738"): "archive_BUF00_2024.json",
    ("archive", "2024-10-06", "2024-10-06", "39.7601"): "archive_IND00_2024.json",
    ("archive", "2025-12-14", "2025-12-14", "42.7738"): "archive_BUF00_2025.json",
    ("archive", "2025-09-28", "2025-09-28", "53.3608"): "archive_DUB00_2025.json",
    ("archive", "2026-09-13", "2026-09-13", "42.7738"): "archive_BUF00_2026.json",
    ("archive", "2026-09-13", "2026-09-28", "42.7738"): "archive_BUF00_2026_b.json",
    ("archive", "2026-09-13", "2026-10-04", "42.7738"): "archive_BUF00_2026_c.json",
}


def schedule_row(game_id, gameday, gametime, stadium_id, stadium, roof):
    season = int(game_id[:4])
    return {"game_id": game_id, "season": season, "week": int(game_id[5:7]), "gameday": gameday, "gametime": gametime,
            "stadium_id": stadium_id, "stadium": stadium, "roof": roof}


SCHEDULE = [
    schedule_row("2024_01_ARI_BUF", "2024-09-08", "13:00", "BUF00", "Highmark Stadium", "outdoors"),
    schedule_row("2024_02_MIA_BUF", "2024-09-12", "20:15", "BUF00", "Highmark Stadium", "outdoors"),
    schedule_row("2024_03_JAX_BUF", "2024-09-15", "13:00", "BUF00", "Highmark Stadium", "outdoors"),
    schedule_row("2024_02_TB_DET", "2024-09-15", "13:00", "DET00", "Ford Field", "dome"),
    schedule_row("2024_01_HOU_IND", "2024-09-08", "13:00", "IND00", "Lucas Oil Stadium", "closed"),
    schedule_row("2024_05_PIT_IND", "2024-10-06", "13:00", "IND00", "Lucas Oil Stadium", "open"),
    schedule_row("2025_15_NE_BUF", "2025-12-14", "13:00", "BUF00", "Highmark Stadium", "outdoors"),
    schedule_row("2025_04_MIN_PIT", "2025-09-28", "09:30", "PIT00", "Acrisure Stadium", "outdoors"),   # Dublin
    schedule_row("2026_01_X_BUF", "2026-09-13", "13:00", "BUF00", "Highmark Stadium", "outdoors"),
    schedule_row("2026_04_Y_BUF", "2026-09-27", "20:20", "BUF00", "Highmark Stadium", "outdoors"),     # inside the archive delay
    schedule_row("2026_05_NE_BUF", "2026-10-04", "13:00", "BUF00", "Highmark Stadium", "outdoors"),    # upcoming: forecast
    schedule_row("2026_05_GB_DET", "2026-10-04", "13:00", "DET00", "Ford Field", "dome"),              # upcoming dome: never
    schedule_row("2026_09_Z_BUF", "2026-11-01", "13:00", "BUF00", "Highmark Stadium", "outdoors"),     # beyond 16 days
]
GAMES = [wx.make_game(r, STADIUMS, VENUES) for r in SCHEDULE]


class MemoryStore:
    """PgStore without Postgres: one list of rows per (source, season, stadium) partition."""

    def __init__(self) -> None:
        self.parts: dict[tuple[str, int, str], list[dict]] = {}
        self.state: dict[tuple[str, str], dict] = {}
        self.manifest: list[tuple[str, str, str]] = []

    def partition_state(self, dataset, partition_key):
        return self.state.get((dataset, partition_key))

    def replace(self, source, season, stadium_id, rows, rec: LoadRecord) -> int:
        if source == "forecast":   # upsert, never delete (PgStore: on conflict do update, no delete)
            kept = {(r["game_id"], r["fetched_at"]): r for r in self.parts.get((source, season, stadium_id), [])}
            kept.update({(r["game_id"], r["fetched_at"]): r for r in rows})
            rows = sorted(kept.values(), key=lambda r: (r["fetched_at"], r["game_id"]))
        self.parts[(source, season, stadium_id)] = list(rows)
        rec.row_count = len(rows)
        self.state[(rec.dataset, rec.partition_key)] = {"checksum_sha256": rec.checksum_sha256, "row_count": rec.row_count}
        self.record(rec)
        return len(rows)

    def record(self, rec: LoadRecord) -> None:
        self.manifest.append((rec.dataset, rec.partition_key, rec.status))

    def rows(self, source: str | None = None) -> list[dict]:
        return [r for (s, _, _), rows in sorted(self.parts.items()) for r in rows if source in (None, s)]

    def row(self, game_id: str, source: str = "archive") -> dict:
        (r,) = [r for r in self.rows(source) if r["game_id"] == game_id]
        return r


class Api:
    """MockTransport for both Open-Meteo endpoints; records every request it serves."""

    def __init__(self, forecasts=(), error: bool = False):
        self.calls: list[tuple[str, str, str, str]] = []
        self.forecasts = list(forecasts)
        self.error = error

    def __call__(self, request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        kind = "archive" if request.url.host.startswith("archive-api") else "forecast"
        key = (kind, q["start_date"], q["end_date"], q["latitude"])
        self.calls.append(key)
        assert q["timezone"] == "GMT" and q["wind_speed_unit"] == "mph" and q["temperature_unit"] == "fahrenheit"
        if self.error:
            return httpx.Response(400, content=(FIX / "error_400.json").read_bytes())
        name = self.forecasts.pop(0) if kind == "forecast" else ROUTES[key]
        return httpx.Response(200, content=(FIX / name).read_bytes(), headers={"content-type": "application/json"})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


class _NoNetwork:
    def get(self, *a, **k):  # pragma: no cover - failing is the point
        raise AssertionError("offline replay touched the network")


@pytest.fixture
def clock(monkeypatch):
    """Freeze the fetch time http.fetch_to_archive stamps on new archive files."""
    class Clock(datetime):
        current = T0

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(http_mod, "datetime", Clock)
    return Clock


def run(tmp_path, store, api, now=T0, **kw) -> wx.WeatherRun:
    r = wx.WeatherRun(games=GAMES, stadiums=STADIUMS, store=store, raw_dir=tmp_path, now=now,
                      client=api.client() if api else _NoNetwork(), min_interval=0, **kw)
    r.run()
    return r


# ------------------------------------------------------------------------------ the stadium reference
def test_stadium_reference_is_well_formed():
    assert len(STADIUMS) == 49
    names = [n for s in STADIUMS.values() for n in s.names]
    assert len(names) == len(set(names)), "a stadium name may belong to one venue only (name resolution)"
    for s in STADIUMS.values():
        assert s.roof_type in wx.ROOF_TYPES, s
        assert -90 <= s.latitude <= 90 and -180 <= s.longitude <= 180, s
        tz = ZoneInfo(s.timezone)
        # the time zone and the longitude must agree (catches a dropped minus sign or swapped coordinates)
        offset = datetime(2025, 1, 15, 12, tzinfo=tz).utcoffset().total_seconds() / 3600
        assert abs(offset - s.longitude / 15) < 3.5, (s.stadium_id, offset, s.longitude)
        assert (s.latitude < 0) == (s.country in ("Australia", "Brazil")), s.stadium_id
        for team, first, last in s.tenants:
            assert 2016 <= first <= last <= 2026 and team.isupper(), s
    for game_id, sid in VENUES.items():
        assert sid in STADIUMS, game_id
    assert {s.roof_type for s in STADIUMS.values()} == {"outdoors", "dome", "retractable"}


def _archived_schedules() -> Path | None:
    for root in (get_settings().raw_dir, PROJECT_ROOT / "data" / "raw"):
        p = root / "nflverse" / "schedules" / "games.parquet"
        if p.exists():
            return p
    return None


def test_stadium_reference_covers_every_schedules_stadium():
    """Acceptance (plan D3): every stadium_id nflverse records 2016-2026 is in the reference, every game
    resolves to a venue, home teams are the venue's tenants, and no early kickoff sits at a US venue."""
    path = _archived_schedules()
    if path is None:
        pytest.skip("no archived nflverse schedules (run `league-lab ingest nfl --datasets schedules`)")
    import polars as pl

    df = pl.read_parquet(path).filter(pl.col("season") >= 2016)
    assert df.height > 2900 and df["season"].max() >= 2026
    ids = set(df["stadium_id"].drop_nulls().unique().to_list())
    missing = ids - set(STADIUMS)
    assert not missing, f"stadium_id(s) not in stadiums.csv: {sorted(missing)}"
    bad_tenant, early_us = [], []
    for r in df.select("game_id", "season", "gameday", "gametime", "stadium_id", "stadium", "roof", "location", "home_team").to_dicts():
        g = wx.make_game(r, STADIUMS, VENUES)
        assert g.stadium_id is not None, r
        st = STADIUMS[g.stadium_id]
        if r["location"] == "Home" and g.resolved_by == "stadium_id":
            if not any(t == r["home_team"] and a <= r["season"] <= b for t, a, b in st.tenants):
                bad_tenant.append(r["game_id"])
        if st.country == "USA" and g.kickoff.astimezone(wx.EASTERN).hour < 10:
            early_us.append(r["game_id"])
    assert not bad_tenant, bad_tenant
    assert not early_us, f"international games recorded at a US stadium (add them to stadium_game_venues.csv): {early_us}"


def test_venue_resolution_order():
    def venue(game_id, sid, name):
        return wx.resolve_venue(game_id, sid, name, STADIUMS, VENUES)

    assert venue("2025_04_MIN_PIT", "PIT00", "Acrisure Stadium") == ("DUB00", "game_override")
    assert venue("2026_05_PHI_JAX", "JAX00", "Tottenham Hotspur Stadium") == ("LON02", "stadium_name")
    assert venue("2016_01_X_BUF", "BUF00", "New Era Field") == ("BUF00", "stadium_id")
    assert venue("2027_01_X_Y", "ZZZ00", "Nowhere Park") == (None, "unresolved")


def test_kickoff_is_us_eastern_with_daylight_saving():
    assert wx.kickoff_utc("2024-09-08", "13:00") == datetime(2024, 9, 8, 17, tzinfo=UTC)     # EDT
    assert wx.kickoff_utc("2025-12-14", "13:00") == datetime(2025, 12, 14, 18, tzinfo=UTC)   # EST
    assert wx.kickoff_utc("2025-09-28", "09:30") == datetime(2025, 9, 28, 13, 30, tzinfo=UTC)  # Dublin, 14:30 local
    assert wx.kickoff_utc("2024-09-12", None) == datetime(2024, 9, 12, 17, tzinfo=UTC)       # missing time: 13:00 ET
    inst, prec = wx.game_hours(datetime(2025, 9, 28, 13, 30, tzinfo=UTC))
    assert [h.hour for h in inst] == [13, 14, 15] and [h.hour for h in prec] == [14, 15, 16]


def test_which_games_are_open_to_the_weather():
    g = {x.game_id: x for x in GAMES}
    assert wx.open_to_weather(g["2024_01_ARI_BUF"], STADIUMS)
    assert not wx.open_to_weather(g["2024_02_TB_DET"], STADIUMS)        # fixed dome
    assert not wx.open_to_weather(g["2024_01_HOU_IND"], STADIUMS)       # retractable, closed
    assert wx.open_to_weather(g["2024_05_PIT_IND"], STADIUMS)           # retractable, open
    mcg = wx.make_game(schedule_row("2026_01_SF_LA", "2026-09-10", "20:35", "MEL00", "Melbourne Cricket Ground", "dome"),
                       STADIUMS, VENUES)
    assert wx.open_to_weather(mcg, STADIUMS), "the MCG is open-air whatever nflverse's roof says"
    undecided = wx.make_game(schedule_row("2026_06_X_DAL", "2026-10-11", "16:25", "DAL00", "AT&T Stadium", None), STADIUMS, VENUES)
    assert wx.open_to_weather(undecided, STADIUMS), "an undecided retractable roof is fetched (the forecast exists either way)"


# ------------------------------------------------------------------------------ the archive
def test_archive_is_one_call_per_stadium_season_not_per_game(tmp_path, clock):
    api, store = Api(), MemoryStore()
    r = run(tmp_path, store, api)
    planned = r.archive_plan()
    assert sorted(planned) == [(2024, "BUF00"), (2024, "IND00"), (2025, "BUF00"), (2025, "DUB00"), (2026, "BUF00")]
    n_games = sum(len(v) for v in planned.values())
    assert n_games == 7 and len(api.calls) == len(planned) == 5          # 7 games, 5 stadium-seasons, 5 calls
    assert api.calls[0] == ("archive", "2024-09-08", "2024-09-15", "42.7738")
    assert all(k[0] == "archive" for k in api.calls)                    # no forecast unless asked
    assert {x.game_id for x in planned[(2026, "BUF00")]} == {"2026_01_X_BUF"}, "a game inside the 5-day archive delay waits"
    assert (tmp_path / "open_meteo" / "archive" / "2024" / "BUF00.json.gz").exists()
    assert (tmp_path / "open_meteo" / "archive" / "2024" / "BUF00.json.gz.meta.json").exists()
    assert all(status == "success" for _, _, status in store.manifest)


def test_archive_values_worked_by_hand(tmp_path, clock):
    store = MemoryStore()
    run(tmp_path, store, Api())
    a = store.row("2024_01_ARI_BUF")
    # 13:00 EDT = 17:00 UTC: wind / temp at 17, 18, 19 UTC; gust / precipitation (preceding hour) at 18, 19, 20 UTC
    assert a["wind_mph"] == 15.0 and a["temp_f"] == 63.0            # (12 + 15 + 18) / 3, (61 + 63 + 65) / 3
    assert a["gust_mph"] == 27.0 and a["precip_in"] == 0.08          # max(21, 27, 24), 0.02 + 0.05 + 0.01
    assert a["weather_code"] == 63 and a["snow"] is False and a["n_hours"] == 3
    assert a["kickoff_at"] == datetime(2024, 9, 8, 17, tzinfo=UTC) and a["forecast_hours_ahead"] is None
    assert a["hourly"]["time"] == ["2024-09-08T17:00", "2024-09-08T18:00", "2024-09-08T19:00", "2024-09-08T20:00"]
    assert (a["grid_latitude"], a["elevation_m"]) == (42.77, 197.0)
    night = store.row("2024_02_MIA_BUF")                              # 20:15 EDT = 00:15 UTC the next day
    assert night["wind_mph"] == 6.0 and night["temp_f"] == 57.0
    snow = store.row("2025_15_NE_BUF")                                # 13:00 EST = 18:00 UTC
    assert snow["temp_f"] == 27.0 and snow["wind_mph"] == 21.0 and snow["snow"] is True and snow["snowfall_in"] == 0.9
    dub = store.row("2025_04_MIN_PIT")                                # recorded at PIT00, played in Dublin
    assert dub["stadium_id"] == "DUB00" and dub["wind_mph"] == 16.0 and dub["temp_f"] == 60.0
    games = {r["game_id"] for r in store.rows("archive")}
    assert "2024_02_TB_DET" not in games and "2024_01_HOU_IND" not in games


def test_second_run_makes_no_call_and_skips_unchanged(tmp_path, clock):
    store = MemoryStore()
    run(tmp_path, store, Api())
    api = Api()
    r = run(tmp_path, store, api)
    assert api.calls == [] and r.calls == 0
    assert {s for d, _, s in store.manifest[-5:]} == {"skipped_unchanged"}


def test_a_newly_archivable_game_refetches_only_its_stadium_season(tmp_path, clock):
    store = MemoryStore()
    run(tmp_path, store, Api())
    clock.current = T0 + timedelta(days=7)      # 09-28 game ready (+5 days); the 10-04 game not yet
    api = Api()
    run(tmp_path, store, api, now=T0 + timedelta(days=7))
    assert api.calls == [("archive", "2026-09-13", "2026-09-28", "42.7738")]
    late = store.row("2026_04_Y_BUF")
    assert late["wind_mph"] == 12.0 and late["precip_in"] == 0.3
    assert len([r for r in store.rows("archive") if r["season"] == 2026]) == 2   # the partition was replaced, not appended


def test_offline_replay_rebuilds_the_same_rows_without_the_network(tmp_path, clock):
    live = MemoryStore()
    run(tmp_path, live, Api(forecasts=["forecast_BUF00_2026_a.json"]), forecast=True)
    replay = MemoryStore()
    r = run(tmp_path, replay, None, offline=True)                     # a client that fails on any request
    assert r.calls == 0
    assert replay.rows() == live.rows() and len(replay.rows("archive")) == 7 and len(replay.rows("forecast")) == 1
    assert {d for d, _, _ in replay.manifest} == {"archive", "forecast"}


def test_offline_with_an_empty_archive_loads_nothing(tmp_path):
    store = MemoryStore()
    r = run(tmp_path, store, None, offline=True)
    assert r.results == [] and store.rows() == []


# ------------------------------------------------------------------------------ forecasts
def test_forecast_plan_upcoming_open_air_games_within_16_days(tmp_path):
    r = wx.WeatherRun(games=GAMES, stadiums=STADIUMS, store=MemoryStore(), raw_dir=tmp_path, now=T0)
    plan = r.forecast_plan()
    assert {k: [g.game_id for g in v] for k, v in plan.items()} == {(2026, "BUF00"): ["2026_05_NE_BUF"]}


def test_every_forecast_is_kept_and_the_archive_never_replaces_it(tmp_path, clock):
    store = MemoryStore()
    api = Api(forecasts=["forecast_BUF00_2026_a.json", "forecast_BUF00_2026_b.json"])
    run(tmp_path, store, api, forecast=True)                          # 2026-10-01 12:00Z
    assert api.calls[-1] == ("forecast", "2026-10-04", "2026-10-04", "42.7738")
    clock.current = T0 + timedelta(hours=2)
    run(tmp_path, store, api, now=T0 + timedelta(hours=2), forecast=True)
    assert len(api.calls) == 6, "a forecast younger than FORECAST_MIN_AGE is not fetched again"
    clock.current = T0 + timedelta(days=1)
    run(tmp_path, store, api, now=T0 + timedelta(days=1), forecast=True)
    fc = sorted(store.rows("forecast"), key=lambda r: r["fetched_at"])
    assert [r["game_id"] for r in fc] == ["2026_05_NE_BUF", "2026_05_NE_BUF"]
    assert [r["forecast_hours_ahead"] for r in fc] == [77.0, 53.0]   # 2026-10-04 17:00Z minus each fetch
    assert [r["wind_mph"] for r in fc] == [11.0, 16.0] and [r["precip_prob_pct"] for r in fc] == [35, 85]
    assert fc[1]["precip_in"] == 0.17 and fc[1]["gust_mph"] == 31.0
    # a forecast file that disappears from the archive does not take its row with it
    first = sorted((tmp_path / "open_meteo" / "forecast" / "2026" / "BUF00").glob("*.json.gz"))[0]
    first.unlink()
    first.with_name(first.name + ".meta.json").unlink()
    run(tmp_path, store, Api(), now=T0 + timedelta(days=1, hours=1), forecast=True)
    assert len(store.rows("forecast")) == 2
    # ten days later the game is in the archive too: both forecast rows stay
    clock.current = T0 + timedelta(days=10)
    run(tmp_path, store, Api(), now=T0 + timedelta(days=10))
    assert len(store.rows("forecast")) == 2
    assert store.row("2026_05_NE_BUF", "archive")["wind_mph"] == 19.0       # observed: (17 + 19 + 21) / 3


def test_a_forecast_row_only_before_kickoff():
    payload = json.loads((FIX / "forecast_BUF00_2026_a.json").read_text())
    g = {x.game_id: x for x in GAMES}["2026_05_NE_BUF"]
    assert len(wx.weather_rows(payload, [g], "forecast", g.kickoff - timedelta(hours=1))) == 1
    assert wx.weather_rows(payload, [g], "forecast", g.kickoff) == []
    assert wx.weather_rows(payload, [g], "forecast", g.kickoff + timedelta(hours=1)) == []


# ------------------------------------------------------------------------------ failures
def test_an_api_error_is_a_failed_partition_and_writes_nothing(tmp_path, clock):
    store = MemoryStore()
    api = Api(error=True)
    r = run(tmp_path, store, api, forecast=True)
    assert len(api.calls) == 6                                         # 5 archive + 1 forecast, each tried once (400: no retry)
    assert {s for _, _, s in store.manifest} == {"failed"} and store.rows() == []
    assert all("HTTP 400" in (x.error or "") for x in r.results)
    assert not list((tmp_path / "open_meteo").rglob("*.json.gz")), "a failed call leaves no archive file"


def test_partial_hours_give_no_sum_but_keep_the_means():
    payload = json.loads((FIX / "archive_IND00_2024.json").read_text())
    g = {x.game_id: x for x in GAMES}["2024_05_PIT_IND"]
    i = payload["hourly"]["time"].index("2024-10-06T19:00")
    payload["hourly"]["precipitation"][i] = None
    payload["hourly"]["wind_speed_10m"][i - 1] = None
    w = wx.summarize_game(payload, g)
    assert w["precip_in"] is None and w["wind_mph"] == 5.0 and w["n_hours"] == 2   # mean of 4 and 6; 18:00 lost wind
    assert wx.summarize_game(payload, wx.Game("x", 2024, 1, datetime(2024, 10, 7, 17, tzinfo=UTC), "IND00", "IND00", "open")) is None


def test_request_url_units_and_dates():
    url = wx.request_url(wx.ARCHIVE_URL, STADIUMS["LAX01"], date(2024, 9, 8), date(2025, 1, 5), wx.HOURLY)
    q = dict(httpx.URL(url).params)
    assert q["latitude"] == "33.9534" and q["longitude"] == "-118.3390" and q["start_date"] == "2024-09-08"
    assert q["hourly"].split(",") == list(wx.HOURLY) and q["precipitation_unit"] == "inch"
