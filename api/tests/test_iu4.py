"""IU-4 (Wave I-U): /api/ready asks again at once when a request finds a published table away (a drop-path publish);
the swap's fallback and the kept-copy rule are drilled on a scratch database (docs/handbacks/IU-4.md)."""

from __future__ import annotations

import psycopg

from league_lab_api import db, ready


def test_a_missing_table_makes_the_next_ready_probe_at_once(monkeypatch):
    ready.reset()
    answers = iter([(True, {"ready": True, "code": "ready"}),
                    (False, {"ready": False, "code": "publishing", "reason": "The numbers are being replaced"})])
    monkeypatch.setattr(ready, "check", lambda: next(answers))
    assert ready.cached()[0] is True
    assert ready.cached()[0] is True                       # kept (60 s)

    class Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a):
            raise psycopg.errors.UndefinedTable("relation \"analytics.x\" does not exist")

    class Conn(Cur):
        def cursor(self):
            return Cur()

    class Pool:
        def connection(self):
            return Conn()
    monkeypatch.setattr(db, "pool", lambda: Pool())
    try:
        db._run("select 1 from analytics.x", ())
    except db.DataNotReady:
        pass
    ok, body = ready.cached()                              # asked again at once: the gap is seen
    assert ok is False and body["code"] == "publishing"
    ready.reset()


def test_the_hook_is_registered_once():
    assert db.on_tables_away.count(ready._tables_away) == 1
