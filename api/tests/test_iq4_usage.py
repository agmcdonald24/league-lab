"""IQ-4 (Wave I-Q): the site's own counter — Rankings is a screen, a reference key's view is counted (its insert used to
fail usage.events' checks: the cause of 30 of 323 failed writes on 7 Oct), a connection error is tried once more on
the writer thread, the failure's kind is counted in the summary's ``process``, and the summary has a per-session depth.
The database tests apply scripts/hosted_usage.sql themselves (as test_u1.py) and remove their rows."""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient
from league_lab_api import db, main, usage
from league_lab_api.main import app
from league_lab_api.settings import ROOT

from .conftest import needs_db

SQL_FILE = ROOT / "scripts" / "hosted_usage.sql"
VERSION = "iq4test"


def _pipeline_dsn() -> str:
    from league_lab.config import get_settings
    return get_settings().pipeline_dsn()


@pytest.fixture(scope="module")
def usage_table():
    try:
        with psycopg.connect(_pipeline_dsn(), autocommit=True, connect_timeout=5) as conn:
            conn.execute(SQL_FILE.read_text())
    except psycopg.Error as exc:
        pytest.skip(f"cannot apply scripts/hosted_usage.sql with the pipeline role: {exc.__class__.__name__}")
    yield
    with psycopg.connect(_pipeline_dsn(), autocommit=True) as conn:
        conn.execute("delete from usage.events where version = %s", (VERSION,))


@pytest.fixture
def api(monkeypatch):
    monkeypatch.delenv("LEAGUE_LAB_APP_PASSWORD", raising=False)
    monkeypatch.delenv("LEAGUE_LAB_API_SECRET", raising=False)
    monkeypatch.delenv(usage.ENV, raising=False)
    monkeypatch.setattr(main, "_version", lambda: VERSION)
    monkeypatch.setattr(usage, "RETRY_PAUSE_S", 0.0)
    usage.reset()
    t = [1000.0]
    monkeypatch.setattr(usage, "clock", lambda: t[0])
    with TestClient(app) as c:
        c.tick = t                        # type: ignore[attr-defined]
        yield c
    usage.reset()


def _rows(session: str) -> list[dict]:
    assert usage.flush()
    with psycopg.connect(_pipeline_dsn(), autocommit=True) as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("select * from usage.events where version = %s and session = %s order by at", (VERSION, session))
        return cur.fetchall()


def test_rankings_and_the_editor_are_screens():
    assert usage.event({"screen": "rankings"}, version=None, session=usage.new_session())["screen"] == "rankings"
    assert usage.event({"screen": "write"}, version=None, session=usage.new_session())["screen"] == "write"


def test_a_reference_key_is_no_league():
    e = usage.event({"screen": "ros", "league": "ref:half", "roster_id": 1}, version="x", session=usage.new_session())
    assert e["screen"] == "ros" and e["league_key"] is None and e["platform"] is None and e["roster_id"] is None
    e = usage.event({"screen": "week", "league": "1389709692405551104", "roster_id": 2}, version="x", session=usage.new_session())
    assert e["league_key"] == "1389709692405551104" and e["platform"] == "sleeper" and e["roster_id"] == 2


@needs_db
def test_a_view_while_browsing_is_counted(usage_table, api):
    s = usage.new_session()
    api.cookies.set(usage.COOKIE, s)
    for screen, league in (("rankings", "ref:half"), ("ros", "ref:ppr.sf"), ("trade-calc", "ref:std")):
        api.tick[0] += 2
        assert api.post("/api/usage", json={"screen": screen, "league": league}).status_code == 204
    got = _rows(s)
    assert [r["screen"] for r in got] == ["rankings", "ros", "trade-calc"]
    assert all(r["league_key"] is None and r["platform"] is None for r in got)
    assert usage.stats["failed"] == 0 and usage.stats["written"] == 3


def test_a_connection_error_is_tried_once_more(api, monkeypatch):
    calls = []

    def flaky(*_a, **_k):
        calls.append(1)
        if len(calls) == 1:
            raise psycopg.OperationalError("SSL SYSCALL error: EOF detected")
    monkeypatch.setattr(db, "write_one", flaky)
    assert usage.write({"at": None, "screen": "week", "league_key": None, "roster_id": None, "platform": None,
                        "version": None, "session": None}) is True
    assert len(calls) == 2 and usage.stats["retried"] == 1 and usage.stats["written"] == 1 and usage.stats["failed"] == 0


def test_the_failures_kind_is_counted_and_a_refused_row_not_retried(api, monkeypatch):
    calls = []

    def refused(*_a, **_k):
        calls.append(1)
        raise psycopg.errors.CheckViolation("new row violates check constraint")
    monkeypatch.setattr(db, "write_one", refused)
    row = {"at": None, "screen": "week", "league_key": None, "roster_id": None, "platform": None, "version": None,
           "session": None}
    assert usage.write(row) is False and len(calls) == 1
    monkeypatch.setattr(db, "write_one", lambda *_a, **_k: (_ for _ in ()).throw(psycopg.OperationalError("asleep")))
    assert usage.write(row) is False
    assert usage.stats["failed"] == 2
    assert usage.failed_kinds == {"CheckViolation": 1, "OperationalError": 1}
    p = api.get("/api/usage/summary").json()["process"]
    assert p["failed"] == 2 and p["failed_kinds"] == {"CheckViolation": 1, "OperationalError": 1}


@needs_db
def test_the_summary_says_how_deep_sessions_went(usage_table, api):
    def depth_today() -> dict:
        d = api.get("/api/usage/summary?days=1").json()
        assert d["ready"] is True
        return (d["depth"] or [{}])[0]
    before = depth_today()
    for n in (1, 3, 5):                   # one bounce, one 2–3, one 4+
        s = usage.new_session()
        api.cookies.set(usage.COOKIE, s)
        for i in range(n):
            api.tick[0] += 2
            assert api.post("/api/usage", json={"screen": ["home", "rankings", "ros", "trade-calc", "week"][i]}).status_code == 204
        assert len(_rows(s)) == n
    db.clear() if hasattr(db, "clear") else None
    after = depth_today()
    assert after["one"] - before.get("one", 0) == 1
    assert after["two_three"] - before.get("two_three", 0) == 1
    assert after["four_plus"] - before.get("four_plus", 0) == 1
