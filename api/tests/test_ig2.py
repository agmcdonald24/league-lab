"""Wave I-G, IG-2: the event store (the decision-quality review § "Engineering requirements"; docs/HOSTING.md § "Events").

events.events holds what the app learned and showed — the overlay's status moves (ESPN / Sleeper), ESPN's news items,
PlayerWire's briefs — keyed by player / team / game, with the source URL, publication / effective / ingestion times and
which newer event superseded each. The writer is U-1's pattern (a queue, one thread, its own read-write transaction);
the readers feed My Week's "What changed" and the matchup evidence's missing corners.

The database tests apply scripts/hosted_events.sql themselves (twice: it is idempotent) with the pipeline role, write
with the API's read-only app role exactly as the server does, and remove their own rows afterwards (every row above the
id the test started from). Fixtures only: the ESPN feeds of ``fixtures/espn`` / ``fixtures/espn_if3`` (IF-3's as-of
case: Horn and Jackson on IR), PlayerWire's ``fixtures/playerwire/briefs.json``; nothing calls ESPN, Sleeper or Neon."""

from __future__ import annotations

import re
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from league_lab import injury_feed as F
from league_lab import news_feed as NF

from league_lab_api import availability as AV
from league_lab_api import db, events, myweek, news, research
from league_lab_api import playerwire as PW
from league_lab_api.settings import ROOT, app_dsn

from .conftest import SCRUBS, needs_db

SQL_FILE = ROOT / "scripts" / "hosted_events.sql"
USAGE_SQL = ROOT / "scripts" / "hosted_usage.sql"
SYNC = ROOT / "scripts" / "sync_to_hosted.sh"
INIT = ROOT / "scripts" / "init_db.sql"
FX = Path(__file__).with_name("fixtures")
ESPN, ESPN_IF3, PW_FX = FX / "espn", FX / "espn_if3", FX / "playerwire" / "briefs.json"
JEFFERSON, HORN, JACKSON = "00-0036322", "00-0036944", "00-0035277"
WILLIAMS, TUTEN = "00-0037240", "00-0040719"
NOW = datetime(2026, 10, 3, 19, 0, tzinfo=UTC)            # the fixtures' "now" (PlayerWire's as_of)


def _pipeline_dsn() -> str:
    from league_lab.config import get_settings
    return get_settings().pipeline_dsn()


def _owner(q: str, params: tuple = ()) -> list[dict]:
    with psycopg.connect(_pipeline_dsn(), autocommit=True) as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(q, params)
        return cur.fetchall() if cur.description else []


@pytest.fixture(scope="module")
def store():
    """scripts/hosted_events.sql applied by the test itself (twice); every row the tests write removed after."""
    try:
        with psycopg.connect(_pipeline_dsn(), autocommit=True, connect_timeout=5) as conn:
            conn.execute(SQL_FILE.read_text())
            conn.execute(SQL_FILE.read_text())
            start = conn.execute("select coalesce(max(id), 0) from events.events").fetchone()[0]
    except psycopg.Error as exc:
        pytest.skip(f"cannot apply scripts/hosted_events.sql with the pipeline role: {exc.__class__.__name__}")
    yield SimpleNamespace(start=start)
    events.flush()
    with psycopg.connect(_pipeline_dsn(), autocommit=True) as conn:
        conn.execute("update events.events set superseded_by = null where superseded_by > %s", (start,))
        conn.execute("delete from events.events where id > %s", (start,))


@pytest.fixture
def on(monkeypatch, store):
    """The store on (fixture mode keeps it off unless asked), a fresh process memory, the fixtures' clock, a clean slate:
    the rows an earlier test wrote are removed so each test counts its own."""
    monkeypatch.setenv(events.ENV, "on")
    monkeypatch.delenv(events.ESPN_NEWS_ENV, raising=False)
    monkeypatch.setattr(events, "clock", lambda: NOW)
    events.flush()
    _owner("update events.events set superseded_by = null where superseded_by > %s", (store.start,))
    _owner("delete from events.events where id > %s", (store.start,))
    events.reset(availability_baseline={})
    db.clear_cache()
    yield store
    events.flush()
    events.reset(availability_baseline={})


def rows(store, where: str = "true", params: tuple = ()) -> list[dict]:
    assert events.flush(10), "the writer thread did not drain its queue"
    return _owner(f"select * from events.events where id > %s and {where} order by id", (store.start, *params))


@pytest.fixture
def overlay(monkeypatch):
    """The overlay on, reading ESPN's fixture feed (Justin Jefferson Out since 2026-10-02)."""
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    F.reset()
    NF.reset()
    AV._snap = None
    AV._built = None
    yield
    F.reset()
    NF.reset()
    AV._snap = None


@pytest.fixture
def corners_on_ir(monkeypatch):
    """IF-3's as-of fixture: Horn and Jackson (Carolina's regular corners) on injured reserve, dated 2026-09-30."""
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN_IF3))
    monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    F.reset()
    AV._snap = None
    yield
    F.reset()
    AV._snap = None


@pytest.fixture
def briefs(monkeypatch):
    monkeypatch.setenv(PW.FIXTURES_ENV, str(PW_FX))
    monkeypatch.delenv(PW.SWITCH_ENV, raising=False)
    PW.reset()
    yield
    PW.reset()


def _moved(snap, gsis: str, code: str | None, as_of: datetime | None = None, *, copy_at: str):
    """A later copy (ESPN's feed timestamp ``copy_at``) of the snapshot with one player's ESPN entry moved (None: off
    both lists)."""
    s = AV.Snapshot()
    s.espn, s.sleeper = {k: dict(v) for k, v in snap.espn.items()}, {k: dict(v) for k, v in snap.sleeper.items()}
    s.espn_fetched, s.sleeper_fetched, s.espn_timestamp = snap.espn_fetched, snap.sleeper_fetched, copy_at
    s._players = snap._players
    if code is None:
        s.espn.pop(gsis, None)
        s.sleeper.pop(gsis, None)
    else:
        s.espn[gsis] = {**s.espn[gsis], "code": code, "as_of": as_of}
    return s


# ------------------------------------------------------------------------------------------- the row (no database)
def test_the_row_is_checked_as_the_table_checks_it():
    r = events.make("availability", source="ESPN", gsis_id=JEFFERSON, team="LAR", player_key="espn:4262921",
                    status="OUT", headline="  Justin   Jefferson is out ", source_url="https://www.espn.com/nfl/player/_/id/4262921",
                    published_at="2026-10-03T03:58:44Z", effective_at="2026-10-02T18:35:00+00:00")
    assert r["team"] == "LA" and r["headline"] == "Justin Jefferson is out" and r["player_key"] == "espn:4262921"
    assert r["effective_at"] == datetime(2026, 10, 2, 18, 35, tzinfo=UTC) and re.fullmatch(r"[0-9a-f]{64}", r["fingerprint"])
    # the fingerprint: kind + subject + status + URL + time (effective first) — the same report read twice is one row
    again = events.make("availability", source="ESPN", gsis_id=JEFFERSON, team="MIN", status="OUT",
                        source_url="https://www.espn.com/nfl/player/_/id/4262921", published_at="2026-10-03T09:00:00Z",
                        effective_at=datetime(2026, 10, 2, 18, 35, tzinfo=UTC))
    assert again["fingerprint"] == r["fingerprint"]
    moved = events.make("availability", source="ESPN", gsis_id=JEFFERSON, status="QUESTIONABLE",
                        source_url="https://www.espn.com/nfl/player/_/id/4262921", effective_at="2026-10-02T18:35:00Z")
    assert moved["fingerprint"] != r["fingerprint"]
    # what does not fit is left out; no subject or no source is no row
    bad = events.make("news", source="ESPN", gsis_id=JEFFERSON, team="Minnesota Vikings", player_key="name:Jefferson",
                      status="has spaces in it", source_url="http://insecure.example/x", game_key="week 5")
    assert (bad["team"], bad["player_key"], bad["status"], bad["source_url"], bad["game_key"]) == (None,) * 5
    assert events.make("news", source="ESPN", gsis_id="Justin Jefferson") is None
    assert events.make("rumour", source="ESPN", gsis_id=JEFFERSON) is None
    assert events.make("news", source="", gsis_id=JEFFERSON) is None
    assert events.make("availability", source="ESPN", team="CAR")["gsis_id"] is None      # a team event
    assert events.team_abbr("WSH") == "WAS" and events.team_abbr("JAC") == "JAX" and events.team_abbr(None) is None


def test_the_availability_diff_on_hand_built_copies():
    """The writer thread's diff: a move is one row; no move is none; off both lists is ACTIVE; a copy missing a source
    is no move at all."""
    t0 = datetime(2026, 10, 2, 18, 35, tzinfo=UTC)
    ent = {"code": "QUESTIONABLE", "source": "ESPN", "as_of": t0, "fetched_at": t0, "note": "ankle",
           "name": "Justin Jefferson", "team": "MIN", "espn_id": "4262921"}
    snap = SimpleNamespace(espn={JEFFERSON: ent}, sleeper={}, espn_fetched=t0, sleeper_fetched=t0,
                           espn_timestamp="2026-10-02T19:00:00Z", _players={"6794": {}})
    events.reset(availability_baseline={JEFFERSON: {"code": "QUESTIONABLE", "source": "ESPN", "team": "MIN"}})
    try:
        assert events.availability_rows(snap) == []                                    # the same status: nothing
        snap.espn[JEFFERSON] = {**ent, "code": "OUT", "as_of": t0 + timedelta(hours=20)}
        (r,) = events.availability_rows(snap)
        assert (r["kind"], r["gsis_id"], r["status"], r["team"], r["source"]) == ("availability", JEFFERSON, "OUT", "MIN", "ESPN")
        assert r["source_url"] == "https://www.espn.com/nfl/player/_/id/4262921" and r["player_key"] == "espn:4262921"
        assert r["headline"] == "Justin Jefferson is out (ankle)"
        assert r["published_at"] == datetime(2026, 10, 2, 19, tzinfo=UTC) and r["effective_at"] == t0 + timedelta(hours=20)
        assert events.availability_rows(snap) == []                                    # asked again: nothing new
        missing_espn = SimpleNamespace(**{**vars(snap), "espn": {}, "espn_fetched": None})
        assert events.availability_rows(missing_espn) == []                            # ESPN did not load: no move
        cleared = SimpleNamespace(**{**vars(snap), "espn": {}})
        (r2,) = events.availability_rows(cleared)
        assert (r2["status"], r2["gsis_id"], r2["headline"]) == ("ACTIVE", JEFFERSON, "Justin Jefferson is no longer on the injury report")
    finally:
        events.reset()


def test_off_and_fixture_mode_write_nothing(monkeypatch):
    """LEAGUE_LAB_EVENTS=off (and fixture mode without LEAGUE_LAB_EVENTS=on: every other suite) queues nothing."""
    item = {"headline": "x", "date": "2026-10-03T12:00:00Z", "source": "ESPN", "url": "https://www.espn.com/x"}
    for value in ("off", "0", "false", "no", None):
        if value is None:
            monkeypatch.delenv(events.ENV, raising=False)                           # conftest's fixture mode
        else:
            monkeypatch.setenv(events.ENV, value)
        events.reset()
        assert not events.enabled()
        assert events.observe_items(JEFFERSON, [item]) == 0
        assert events.observe_availability(SimpleNamespace(espn={}, sleeper={})) is False
        assert events.recent([JEFFERSON]) == [] and events.for_team("CAR") == []
        assert events.info() == {"enabled": False, "rows": None, "newest": None}
        assert events._queue.unfinished_tasks == 0 and events.stats["queued"] == 0


def test_the_writer_never_waits_and_never_raises(monkeypatch):
    """A slow or failing store never holds or fails the caller: the row goes on the queue, the thread pays for it."""
    monkeypatch.setenv(events.ENV, "on")
    events.reset()

    def slow(_rows):
        time.sleep(1.5)
        raise psycopg.OperationalError("the database is asleep")
    monkeypatch.setattr(events, "write", slow)
    item = {"headline": "Jefferson ruled out", "date": "2026-10-03T12:00:00Z", "source": "ESPN", "url": "https://www.espn.com/a"}
    t = time.monotonic()
    assert events.observe_items(JEFFERSON, [item]) == 1
    assert time.monotonic() - t < 0.5
    assert events.flush(5)
    assert events.stats["failed"] == 1
    assert events.observe_items(JEFFERSON, [item]) == 1        # a failed row is forgotten: the next showing retries it
    events.flush(5)
    events.reset()


# ------------------------------------------------------------------------------------------- the store (database)
@needs_db
def test_the_hosted_sql_is_idempotent_and_leaves_usage_alone(store):
    """Applied twice (the fixture) and once more here: one table, its checks and index, the app role's grants — and
    usage.events (U-1's table on the same database) exactly as it was."""
    with psycopg.connect(_pipeline_dsn(), autocommit=True) as conn:
        conn.execute(USAGE_SQL.read_text())
    usage_before = _owner("""select (select count(*) from usage.events) as n,
                                    (select string_agg(column_name || ' ' || data_type, ', ' order by ordinal_position)
                                     from information_schema.columns where table_schema = 'usage' and table_name = 'events') as cols,
                                    (select string_agg(conname, ',' order by conname) from pg_constraint
                                     where conrelid = 'usage.events'::regclass) as checks,
                                    (select relacl::text from pg_class where oid = 'usage.events'::regclass) as acl""")
    with psycopg.connect(_pipeline_dsn(), autocommit=True) as conn:
        conn.execute(SQL_FILE.read_text())
        conn.execute(SQL_FILE.read_text())
    usage_after = _owner("""select (select count(*) from usage.events) as n,
                                   (select string_agg(column_name || ' ' || data_type, ', ' order by ordinal_position)
                                    from information_schema.columns where table_schema = 'usage' and table_name = 'events') as cols,
                                   (select string_agg(conname, ',' order by conname) from pg_constraint
                                    where conrelid = 'usage.events'::regclass) as checks,
                                   (select relacl::text from pg_class where oid = 'usage.events'::regclass) as acl""")
    assert usage_after == usage_before
    cols = [r["column_name"] for r in _owner("select column_name from information_schema.columns where table_schema = 'events' "
                                              "and table_name = 'events' order by ordinal_position")]
    assert cols == ["id", "kind", "player_key", "gsis_id", "team", "game_key", "status", "headline", "summary", "source",
                    "source_url", "published_at", "effective_at", "ingested_at", "superseded_by", "fingerprint"]
    assert _owner("select count(*) as n from pg_tables where schemaname = 'events'")[0]["n"] == 1
    idx = {r["indexname"] for r in _owner("select indexname from pg_indexes where schemaname = 'events'")}
    assert {"events_gsis_ingested", "events_fingerprint_unique"} <= idx
    priv = _owner("""select has_table_privilege('league_lab_app', 'events.events', 'select') as sel,
                            has_table_privilege('league_lab_app', 'events.events', 'insert') as ins,
                            has_table_privilege('league_lab_app', 'events.events', 'delete') as del,
                            has_table_privilege('league_lab_app', 'events.events', 'truncate') as trunc,
                            has_column_privilege('league_lab_app', 'events.events', 'superseded_by', 'update') as upd_sup,
                            has_column_privilege('league_lab_app', 'events.events', 'headline', 'update') as upd_head,
                            has_sequence_privilege('league_lab_app', 'events.events_id_seq', 'usage') as seq""")[0]
    assert priv == {"sel": True, "ins": True, "del": False, "trunc": False, "upd_sup": True, "upd_head": False, "seq": True}
    sql = "\n".join(line.split("--")[0] for line in SQL_FILE.read_text().lower().splitlines())     # the statements only
    assert "drop " not in sql and "alter role" not in sql and "usage" not in sql.replace("grant usage on", "")


@needs_db
def test_the_app_role_writes_only_what_the_grants_allow(on):
    """The server's own role: an insert and a supersede in a read-write transaction work; anything else is refused;
    the table's checks hold."""
    r = events.make("news", source="ESPN", gsis_id=JEFFERSON, headline="grant check", source_url="https://www.espn.com/g",
                    published_at=NOW)
    assert events.write([r]) == 1 and events.write([r]) == 0                      # the fingerprint: once
    with psycopg.connect(app_dsn(), autocommit=True) as conn:
        for bad in ("update events.events set headline = 'x' where id > 0", "delete from events.events where id > 0"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                conn.execute("set transaction read write")
                conn.execute(bad)
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute("set transaction read write")
            conn.execute("insert into events.events (kind, gsis_id, source, fingerprint) values ('news', 'Jefferson', 'x', %s)",
                         ("0" * 64,))
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):               # the role stays read-only by default
            conn.execute("insert into events.events (kind, gsis_id, source, fingerprint) values ('news', %s, 'x', %s)",
                         (JEFFERSON, "1" * 64))


@needs_db
def test_a_status_move_writes_one_event_and_the_next_move_supersedes_it(on, overlay):
    """The overlay's copy (ESPN's fixture: Jefferson Out since Oct 2) writes his event once; the next copy moves him to
    Questionable (one new event, the first superseded); the one after drops him from both lists (ACTIVE, superseding)."""
    snap = AV.snapshot()                                     # the overlay's own path: availability.snapshot -> observe
    assert snap is not None and snap.espn[JEFFERSON]["code"] == "OUT"
    (jj,) = rows(on, "gsis_id = %s", (JEFFERSON,))
    assert (jj["kind"], jj["status"], jj["source"], jj["team"], jj["superseded_by"]) == ("availability", "OUT", "ESPN", "MIN", None)
    assert jj["source_url"] == "https://www.espn.com/nfl/player/_/id/4262921" and jj["player_key"] == "espn:4262921"
    assert jj["effective_at"] == datetime(2026, 10, 2, 18, 35, tzinfo=UTC)          # the report's date
    assert jj["published_at"] == datetime(2026, 10, 3, 3, 58, 44, tzinfo=UTC)       # the copy's own (the feed's timestamp)
    n_first = len(rows(on))
    assert n_first > 1 and all(r["kind"] == "availability" for r in rows(on))
    AV._snap = None
    assert AV.snapshot() is not None and len(rows(on)) == n_first              # the same copy again: nothing new
    events.observe_availability(_moved(snap, JEFFERSON, "QUESTIONABLE", datetime(2026, 10, 3, 20, 0, tzinfo=UTC),
                                       copy_at="2026-10-03T20:05:00Z"))
    first, second = rows(on, "gsis_id = %s", (JEFFERSON,))
    assert len(rows(on)) == n_first + 1                                         # one event: his move, nobody else's
    assert second["status"] == "QUESTIONABLE" and second["superseded_by"] is None
    assert first["superseded_by"] == second["id"]
    events.observe_availability(_moved(snap, JEFFERSON, None, copy_at="2026-10-04T12:00:00Z"))
    a, b, c = rows(on, "gsis_id = %s", (JEFFERSON,))
    assert c["status"] == "ACTIVE" and c["headline"] == "Justin Jefferson is no longer on the injury report"
    assert c["effective_at"] is None and c["published_at"] == datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    assert (a["superseded_by"], b["superseded_by"], c["superseded_by"]) == (b["id"], c["id"], None)
    # the readers: his history newest first (live and superseded), the live one only in `recent`
    db.clear_cache()
    hist = events.for_player(JEFFERSON)
    assert [e["status"] for e in hist] == ["ACTIVE", "QUESTIONABLE", "OUT"] and [e["live"] for e in hist] == [True, False, False]
    assert [e["status"] for e in events.recent([JEFFERSON], hours=48, kinds=("availability",))] == ["ACTIVE"]
    # a new process (no memory) diffs against the store: the store says ACTIVE, the copy says Out -> one event
    events.reset()
    AV._snap = None
    AV.snapshot()
    assert [r["status"] for r in rows(on, "gsis_id = %s", (JEFFERSON,))][-1] == "OUT"
    assert len(rows(on)) == n_first + 3


@needs_db
def test_a_news_item_and_a_brief_write_their_events_once(on, overlay, briefs, monkeypatch):
    """The card's news line: ESPN's items (PlayerWire off) and PlayerWire's briefs (on: they fill the line), each item one
    event; showing them again writes nothing — in this process (its memory) and in a new one (the fingerprint)."""
    def show() -> list[dict]:
        monkeypatch.setenv(PW.SWITCH_ENV, "off")
        espn = news.for_card(JEFFERSON)
        monkeypatch.delenv(PW.SWITCH_ENV)
        return espn + news.for_card(JEFFERSON)
    items = show()
    assert {it["kind"] for it in items} == {"espn", "playerwire"}
    got = rows(on, "gsis_id = %s and kind in ('news', 'brief')", (JEFFERSON,))
    assert len(got) == len(items) == len({it["url"] + it["date"] for it in items})
    brief = next(r for r in got if r["kind"] == "brief" and r["status"] == "official")
    assert brief["source"] == "Minnesota Vikings via PlayerWire" and brief["headline"] == "Jefferson (ankle) ruled out for Sunday"
    assert brief["source_url"] == "https://www.vikings.com/news/injury-report-week-5"
    assert brief["summary"].startswith("Justin Jefferson (ankle) has been ruled out")
    assert brief["published_at"] == datetime(2026, 10, 3, 14, 10, tzinfo=UTC) and brief["effective_at"] is None
    espn = [r for r in got if r["kind"] == "news"]
    assert espn and all(r["source"] in ("ESPN", "RotoWire via ESPN") and r["source_url"].startswith("https://") for r in espn)
    assert {r["status"] for r in espn} <= {"player", "league"} and all(r["summary"] is None for r in espn)
    show()                                                         # shown again: nothing queued (this process knows)
    assert len(rows(on, "kind in ('news', 'brief')")) == len(items)
    events.reset(availability_baseline={})                         # a new process: the store's fingerprint refuses them
    show()
    assert len(rows(on, "kind in ('news', 'brief')")) == len(items) and events.stats["duplicate"] == len(items)
    # one live event per kind: the newest ESPN item, the newest brief; the older ones superseded by them
    live = {r["kind"]: r for r in rows(on, "kind in ('news', 'brief') and superseded_by is null")}
    assert set(live) == {"news", "brief"} and len(rows(on, "kind in ('news', 'brief') and superseded_by is null")) == 2
    assert live["news"]["published_at"] == max(r["published_at"] for r in espn)
    bs = rows(on, "kind = 'brief'")                                # the newest brief naming him is live: Addison's (related)
    assert live["brief"]["headline"].startswith("Addison in line for more targets")
    assert live["brief"]["published_at"] == max(r["published_at"] for r in bs)
    assert all(r["superseded_by"] == live["brief"]["id"] for r in bs if r["id"] != live["brief"]["id"])


@needs_db
def test_espn_news_can_stay_out_of_the_store(on, overlay, briefs, monkeypatch):
    monkeypatch.setenv(events.ESPN_NEWS_ENV, "off")
    news.for_card(JEFFERSON)
    assert {r["kind"] for r in rows(on, "gsis_id = %s", (JEFFERSON,)) if r["kind"] != "availability"} == {"brief"}


@needs_db
def test_what_changed_lists_a_brief_with_its_source(client, on, overlay, briefs):
    """My Week, Scrubs roster 2: Jefferson's status line cites the stored event (ESPN, the report's time, his ESPN page);
    his news line is PlayerWire's brief (N2's order) with its source and link, and carries the event's id once stored."""
    first = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()["changed"]
    events.flush(10)
    db.clear_cache()
    AV.clear_context()
    ch = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()["changed"]
    print("changed:", ch)
    st = [x for x in ch["lines"] if x["kind"] == "status"]
    assert st and "Jefferson" in st[0]["text"] and st[0]["gsis_id"] == JEFFERSON
    assert st[0]["source"] == "Injury report (ESPN)" and st[0]["at"] == "2026-10-02T18:35:00Z"
    assert st[0]["url"] == "https://www.espn.com/nfl/player/_/id/4262921" and isinstance(st[0]["event_id"], int)
    nw = [x for x in ch["lines"] if x["kind"] == "news" and x["gsis_id"] == JEFFERSON]
    assert len(nw) == 1
    b = nw[0]
    assert b["origin"] == "playerwire" and b["source"] == "Minnesota Vikings via PlayerWire" and b["verification"] == "official"
    assert b["text"] == "Jefferson (ankle) ruled out for Sunday" and b["url"] == "https://www.vikings.com/news/injury-report-week-5"
    assert b["at"] == "2026-10-03T14:10:00Z" and isinstance(b["event_id"], int)
    stored = rows(on, "id = %s", (b["event_id"],))[0]
    assert stored["kind"] == "brief" and stored["gsis_id"] == JEFFERSON
    assert [x["text"] for x in first["lines"]] == [x["text"] for x in ch["lines"]]    # the store changes the citation only
    # the store's lines survive a live source that did not answer this time (ESPN's one-second budget, an outage)
    monkeypatch_recent = pytest.MonkeyPatch()
    monkeypatch_recent.setattr(news, "recent", lambda *_a, **_k: [])
    monkeypatch_recent.setattr(PW, "recent", lambda *_a, **_k: [])
    try:
        AV.clear_context()
        again = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()["changed"]
        kept = [x for x in again["lines"] if x["kind"] == "news" and x["gsis_id"] == JEFFERSON]
        assert len(kept) == 1 and kept[0]["origin"] == "playerwire" and isinstance(kept[0]["event_id"], int)
        assert kept[0]["source"].endswith("via PlayerWire") and kept[0]["url"].startswith("https://")
    finally:
        monkeypatch_recent.undo()


@needs_db
def test_what_changed_without_the_store_is_if4s(client, overlay, briefs, monkeypatch):
    """LEAGUE_LAB_EVENTS=off: IF-4's lines (ESPN's news only, no event ids); the status line still names its source."""
    monkeypatch.setenv(events.ENV, "off")
    ch = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()["changed"]
    nw = [x for x in ch["lines"] if x["kind"] == "news"]
    assert nw and all("event_id" not in x for x in nw) and nw[0]["source"] == "RotoWire via ESPN"
    st = [x for x in ch["lines"] if x["kind"] == "status"]
    assert st and st[0]["source"] == "Injury report (ESPN)" and st[0]["at"] == "2026-10-02T18:35:00Z" and "event_id" not in st[0]


@needs_db
def test_the_matchup_evidence_cites_the_event(client, on, corners_on_ir):
    """IF-3's case with the store on: Horn's and Jackson's IR are availability events of Carolina (events.for_team);
    `changed.missing[]` carries each event and its URL, `changed.events` lists them; the words are IF-3's."""
    assert AV.snapshot() is not None
    car = rows(on, "team = 'CAR' and gsis_id in (%s, %s)", (HORN, JACKSON))
    assert {r["gsis_id"] for r in car} == {HORN, JACKSON} and {r["status"] for r in car} == {"IR"}
    db.clear_cache()
    d = client.get(f"/api/compare?league={SCRUBS}&a={WILLIAMS}&b={TUTEN}").json()
    c = d["a"]["matchup_evidence"]["changed"]
    assert c["kind"] == "changed"
    miss = {m["gsis_id"]: m for m in c["missing"]}
    assert miss[HORN]["url"] == "https://www.espn.com/nfl/player/_/id/9900101"
    assert miss[JACKSON]["url"] == "https://www.espn.com/nfl/player/_/id/9900102"
    for m in miss.values():
        ev = m["event"]
        assert ev["kind"] == "availability" and ev["source"] == "ESPN" and ev["status"] == "IR"
        assert ev["at"] == "2026-09-30T20:15:00Z" and isinstance(ev["id"], int)
        assert (m["source"], m["date_words"]) == ("ESPN", "Sep 30")                 # the overlay's words stay
    assert {e["gsis_id"] for e in c["events"]} == {HORN, JACKSON} and all(e["url"] for e in c["events"])
    assert "Jackson and Horn are on injured reserve (ESPN, Sep 30)" in d["a"]["matchup_evidence"]["sentences"][0]


@needs_db
def test_without_an_event_the_overlay_stays_the_fallback(client, corners_on_ir, monkeypatch):
    monkeypatch.setenv(events.ENV, "off")
    c = client.get(f"/api/compare?league={SCRUBS}&a={WILLIAMS}&b={TUTEN}").json()["a"]["matchup_evidence"]["changed"]
    assert c["kind"] == "changed" and c["events"] == []
    assert all(m["event"] is None and m["url"] is None and m["source"] == "ESPN" for m in c["missing"])


@needs_db
def test_a_failing_store_never_fails_a_request(client, on, overlay, briefs, monkeypatch):
    def boom(*_a, **_k):
        raise psycopg.OperationalError("no route to the store")
    monkeypatch.setattr(events, "write", boom)
    monkeypatch.setattr(events, "db", SimpleNamespace(query=boom, fresh=boom))     # the readers too (events' own reads)
    r = client.get(f"/api/my-week?league={SCRUBS}&team=2")
    assert r.status_code == 200 and r.json()["changed"]["lines"]
    assert client.get(f"/api/player/{JEFFERSON}?league={SCRUBS}&team=2").status_code == 200
    assert events.flush(10) and events.stats["failed"] >= 1
    s = client.get("/api/status").json()["events"]
    assert s["enabled"] is True and s["ready"] is False


@needs_db
def test_status_and_the_qa_route(client, on, overlay):
    AV.snapshot()
    events.flush(10)
    db.clear_cache()
    s = client.get("/api/status").json()["events"]
    assert s["enabled"] is True and s["ready"] is True and s["rows"] >= 1 and s["newest"]
    r = client.get(f"/api/events?league={SCRUBS}&team=2&hours=720")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["enabled"] is True and body["players"] >= 10 and body["hours"] == 720
    jj = [e for e in body["events"] if e["gsis_id"] == JEFFERSON]
    assert jj and jj[0]["player_name"] == "Justin Jefferson" and jj[0]["status"] == "OUT" and "fingerprint" not in jj[0]
    assert client.get(f"/api/events?league={SCRUBS}&team=2&hours=99999").json()["hours"] == 720


def test_the_qa_route_is_behind_the_gate(monkeypatch):
    from fastapi.testclient import TestClient

    from league_lab_api.main import app
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "beta")
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "s" * 32)
    with TestClient(app) as c:
        assert c.get(f"/api/events?league={SCRUBS}&team=2").status_code == 401


# ------------------------------------------------------------------------------------------- the scripts (the PO reviews them)
def test_the_sync_keeps_and_creates_the_events_schema():
    text = SYNC.read_text()
    assert subprocess.run(["bash", "-n", str(SYNC)], capture_output=True).returncode == 0
    drops = re.findall(r"drop schema[^;\"\n]*", text)
    assert drops and not any("events" in d for d in drops)                   # never dropped
    block = text.split("# ---- IG-2")[1].split("# ---- end IG-2")[0]
    assert re.search(r'psql "\$LEAGUE_LAB_HOSTED_ADMIN_URL"[^\n|]*-f scripts/hosted_events\.sql; then', block)
    assert text.index("# ---- IG-2") > text.index("# ---- end U-1")          # after the usage block
    assert "PASSWORD" not in block


def test_init_db_creates_the_local_store_as_the_pipeline_role():
    block = INIT.read_text().split("-- ---- IG-2")[1].split("-- ---- end IG-2")[0]
    assert "set role league_lab_pipeline;" in block and "\\ir hosted_events.sql" in block and "reset role;" in block


def test_the_readers_floor_the_window_to_the_minute(monkeypatch):
    monkeypatch.setattr(events, "clock", lambda: datetime(2026, 10, 3, 19, 0, 42, 5, tzinfo=UTC))
    assert events._since(hours=1) == datetime(2026, 10, 3, 18, 0, tzinfo=UTC)    # the query cache keys on it
    assert events._since() == events.EPOCH
    assert research.EVENT_LOOKBACK == timedelta(days=60)
    assert myweek.MAX_CHANGED == 5


# ------------------------------------------------------------------------------------------- the e2e's recorded answers (web/e2e/ig2)
@needs_db
@pytest.mark.skipif(not __import__("os").environ.get("IG2_RECORD"), reason="records web/fixtures/ig2/api_ig2.json: IG2_RECORD=1")
def test_record_e2e_answers(client, on, overlay, briefs):
    """My Week for Scrubs roster 2 with the store on (the second answer: the events stored, so the lines carry them) and
    the status line, keyed like web/e2e/if4's recordings."""
    import json
    from urllib.parse import urlencode

    def key(path: str, **q) -> str:
        return path + ("?" + urlencode(sorted((k, str(v)) for k, v in q.items())) if q else "")

    client.get(key("/api/my-week", league=SCRUBS, team=2))
    events.flush(10)
    db.clear_cache()
    AV.clear_context()
    out: dict = {}
    for path, q in (("/api/my-week", {"league": SCRUBS, "team": 2}), ("/api/status", {})):
        r = client.get(key(path, **q))
        out[key(path, **q)] = {"status": r.status_code, "body": r.json()}
    f = ROOT / "web" / "fixtures" / "ig2" / "api_ig2.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    assert all(v["status"] == 200 for v in out.values()), {k: v["status"] for k, v in out.items()}
    lines = out[key("/api/my-week", league=SCRUBS, team=2)]["body"]["changed"]["lines"]
    assert any(x.get("origin") == "playerwire" for x in lines) and lines[0].get("event_id")
