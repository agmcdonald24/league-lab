"""IS-4 (Wave I-S): /api/ready — a statement timeout is "query" (the database answered), never "does not answer"; the
probe never passes startup options (scripts/pooler_check.sh proves it through a transaction-mode PgBouncer)."""

from __future__ import annotations

import psycopg

from league_lab_api import ready


class _Conn:
    def __init__(self, exc=None):
        self.exc, self.sql = exc, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, *a, **k):
        self.sql.append(sql)
        if sql.startswith("set local"):
            return None
        raise self.exc


def test_a_statement_timeout_is_a_query_failure_not_a_dead_database(monkeypatch):
    assert issubclass(psycopg.errors.QueryCanceled, psycopg.OperationalError)     # why the order of the excepts matters
    monkeypatch.setattr(ready.psycopg, "connect",
                        lambda *a, **k: _Conn(psycopg.errors.QueryCanceled("canceling statement due to statement timeout")))
    ok, body = ready.check("postgresql://x@127.0.0.1:1/none")
    assert ok is False and body["code"] == "query" and body["checks"]["database"] == "ok"
    assert body["reason"] == "A readiness query took longer than 5 s (QueryCanceled)."


def test_the_probe_passes_no_startup_options_and_sets_its_timeout_inside_its_transaction(monkeypatch):
    seen = {}
    conn = _Conn(psycopg.errors.UndefinedTable("x"))

    def connect(*a, **k):
        seen.update(k)
        return conn
    monkeypatch.setattr(ready.psycopg, "connect", connect)
    ready.check("postgresql://x@127.0.0.1:1/none")
    assert "options" not in seen and not seen.get("autocommit")
    assert conn.sql[0].startswith("set local statement_timeout")


def test_a_new_publication_drops_every_published_region_and_refreshes_as_of(monkeypatch):
    from league_lab import memo

    from league_lab_api import db, main
    keep = memo.region("is4_not_published", ttl=600)
    pub = memo.region("is4_published", ttl=600, published=True)
    keep.put("k", 1)
    pub.put("k", 1)
    db._cache.put(("select 1", ()), "frame")
    ids = iter(["A", "A", "B"])
    monkeypatch.setattr(db, "publication_id", lambda: next(ids))
    monkeypatch.setattr(db, "_pub", {"id": None, "seen": False, "next": 0.0})
    main._health_state["next"] = 999999.0
    assert db.watch_publication(now=0.0) is False                  # first read: remembered, nothing dropped
    assert db.watch_publication(now=10.0) is False                 # within 30 s: not read
    assert db.watch_publication(now=31.0) is False                 # same id
    assert pub.get("k") == 1 and db._cache.get(("select 1", ())) == "frame"
    assert db.watch_publication(now=62.0) is True                  # a new publication
    assert pub.get("k") is None and db._cache.get(("select 1", ())) is None and keep.get("k") == 1
    assert main._health_state["next"] == 0.0                        # the health check reads as_of at once


def test_no_publication_comment_is_todays_behaviour(monkeypatch):
    from league_lab_api import db
    monkeypatch.setattr(db, "publication_id", lambda: None)
    monkeypatch.setattr(db, "_pub", {"id": None, "seen": False, "next": 0.0})
    db._cache.put(("select 2", ()), "frame")
    assert [db.watch_publication(now=t) for t in (0.0, 31.0, 62.0)] == [False, False, False]
    assert db._cache.get(("select 2", ())) == "frame"
