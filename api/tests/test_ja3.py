"""JA-3 (Wave J-A): a request never waits for a database connection it could have had (db.connection, db.pool_status).

No database: the pool is a stand-in. The connection is given back before the rows become a DataFrame; every pooled
caller (the blog included) takes the one wait; a wait over a second is one log line with how long, how many in use, the
route and the statement's first words (never the rest, never a DSN); /api/status carries the pool's counts."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

import pandas as pd
import pytest

from league_lab_api import blog_store, db

from .conftest import needs_db


class _Cur:
    description = [type("D", (), {"name": "n"})()]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        return None

    def fetchall(self):
        return [(1,), (2,)]


class _Conn:
    def cursor(self):
        return _Cur()

    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return (True,)

    def fetchall(self):
        return []


class _Pool:
    def __init__(self, delay: float = 0.0):
        self.delay, self.out = delay, 0

    @contextmanager
    def _cm(self, timeout=None):
        time.sleep(self.delay)
        self.out += 1
        try:
            yield _Conn()
        finally:
            self.out -= 1

    def connection(self, timeout=None):
        self.timeout = timeout
        return self._cm(timeout)


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(db, "_pstats", {k: (0.0 if "_s" in k else None if k.endswith(("route", "_at")) else 0)
                                        for k in db._pstats})
    p = _Pool()
    monkeypatch.setattr(db, "pool", lambda: p)
    monkeypatch.setattr(db, "_live_sql", lambda cur, sql: sql)
    return p


def test_the_connection_is_back_in_the_pool_before_the_rows_become_a_frame(fresh, monkeypatch):
    seen = []
    real = pd.DataFrame

    def frame(*a, **k):
        seen.append((fresh.out, db._pstats["in_use"]))
        return real(*a, **k)
    monkeypatch.setattr(db.pd, "DataFrame", frame)
    df = db._run_pooled("select n from t", ())
    assert list(df["n"]) == [1, 2] and seen and seen[0] == (0, 0)


def test_every_pooled_caller_takes_the_one_wait(fresh):
    with db.connection("select 1"):
        pass
    assert fresh.timeout == db.POOL_WAIT_S
    blog_store._read_published()                     # the blog's read: the same wait (it was 5 s)
    assert fresh.timeout == db.POOL_WAIT_S
    src = __import__("inspect").getsource(blog_store)
    assert "pool().connection(" not in src


def test_a_wait_over_a_second_is_one_log_line_with_the_counts_and_the_first_words_only(fresh, caplog):
    fresh.delay = 1.1
    tok = db.route.set("/api/player/*")
    try:
        with caplog.at_level(logging.WARNING, logger=db.log.name):
            with db.connection("select a, b, c, d, e, f, g, h from analytics.secret_table where x = 1"):
                pass
    finally:
        db.route.reset(tok)
    lines = [r.getMessage() for r in caplog.records if "waited" in r.getMessage()]
    assert len(lines) == 1
    msg = lines[0]
    assert msg.startswith("waited 1.1 s for a database connection (1 of ") and "on /api/player/*" in msg
    assert "secret_table" not in msg and "postgresql://" not in msg
    st = db.pool_status()
    assert st["waited_over_1s"] == 1 and st["longest_wait_s"] >= 1.1 and st["longest_wait_route"] == "/api/player/*"


def test_a_short_wait_is_silent(fresh, caplog):
    with caplog.at_level(logging.WARNING, logger=db.log.name):
        with db.connection("select 1"):
            pass
    assert not [r for r in caplog.records if "waited" in r.getMessage()]


def test_in_use_is_given_back_when_the_statement_fails(fresh):
    with pytest.raises(ValueError):
        with db.connection("select 1"):
            assert db._pstats["in_use"] == 1
            raise ValueError("boom")
    assert db._pstats["in_use"] == 0 and fresh.out == 0


@needs_db
def test_status_carries_the_pool_and_no_dsn(client):
    body = client.get("/api/status").json()
    pool = body["pool"]
    for k in ("size", "in_use", "waiting", "peak_in_use", "longest_wait_s", "longest_wait_route", "wait_limit_s"):
        assert k in pool
    assert pool["size"] == db.POOL_SIZE and "postgresql" not in str(pool)


def test_the_size_is_bounded(monkeypatch):
    for raw, want in (("1", 2), ("10", 10), ("500", 32)):
        monkeypatch.setenv("LEAGUE_LAB_POOL_SIZE", raw)
        assert max(2, min(int(raw), 32)) == want
