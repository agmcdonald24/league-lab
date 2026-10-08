"""IR-3 (Wave I-R): /api/ready — readiness apart from liveness (league_lab_api/ready.py).

The rule's every branch on a stand-in connection (no database: these run in the release gate), the route's answers and
cache, the bucket, and one answer from the real database (needs_db)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from league_lab_api import ratelimit, ready

from .conftest import needs_db

NOW = datetime(2026, 10, 3, 16, 0, tzinfo=UTC)
FITTED = datetime(2026, 10, 3, 11, 52, tzinfo=UTC)
PUB = json.dumps({"publication": "20261003T1152Z-3dfa01d", "published_at": "2026-10-03T11:58:00+00:00",
                  "code": "3dfa01d", "mode": "swap"})


class _Res:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    """Answers ready.probe's statements from a dict of facts (what a published database would hold)."""

    def __init__(self, **facts):
        self.f = {"tables": set(ready.NEEDED), "schema_comment": PUB, "db_comment": None, "fitted": FITTED,
                  "next": (2026, 4), "board": True, "lists": True, "ros": True}
        self.f.update(facts)
        self.sql: list[str] = []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        f = self.f
        if sql == "select 1":
            return _Res((1,))
        if "to_regclass" in sql:
            return _Res(tuple(n in f["tables"] for n in ready.NEEDED))
        if "obj_description(to_regnamespace" in sql:
            return _Res((f["schema_comment"],))
        if "shobj_description" in sql:
            return _Res((f["db_comment"],))
        if "max(fitted_at)" in sql:
            return _Res((f["fitted"],))
        if "from analytics.dim_game" in sql:
            return _Res(f["next"])
        if "exists(select 1 from ops.projections" in sql:
            return _Res((f["board"], f["lists"]))
        if "mart_player_ros_projection" in sql:
            return _Res((f["ros"],))
        raise AssertionError(f"unexpected statement: {sql}")


def test_ready_when_every_check_passes_with_the_publication_and_the_week():
    ok, body = ready.probe(FakeConn(), NOW, NOW)
    assert ok is True and body["code"] == "ready"
    c = body["checks"]
    assert c["database"] == "ok" and c["as_of"] == FITTED.isoformat() and c["age_hours"] == 4.1
    assert c["publication"] == {"id": "20261003T1152Z-3dfa01d", "published_at": "2026-10-03T11:58:00+00:00",
                                "code": "3dfa01d", "mode": "swap"}
    assert c["week"] == {"season": 2026, "week": 4, "board": True, "lists": True} and c["rest_of_season"] is True


def test_a_database_published_before_ir3_has_no_publication_and_is_still_ready():
    ok, body = ready.probe(FakeConn(schema_comment=None), NOW)
    assert ok is True and body["checks"]["publication"] is None
    ok, body = ready.probe(FakeConn(schema_comment="not json at all"), NOW)
    assert ok is True and body["checks"]["publication"] is None


def test_an_old_publication_is_ready_with_its_age_never_a_503():
    """A missed nightly is the health check's `stale`, not an outage: the age is reported, the answer stays 200."""
    ok, body = ready.probe(FakeConn(fitted=datetime(2026, 9, 28, 11, 0, tzinfo=UTC)), NOW, NOW)
    assert ok is True and body["checks"]["age_hours"] == 125.0


@pytest.mark.parametrize("facts, code, words", [
    ({"tables": set()}, "missing_tables", "The published tables are missing: ops.projections, analytics.dim_game"),
    ({"tables": set(), "db_comment": json.dumps({"publishing_since": "2026-10-03T11:55:00+00:00", "mode": "drop"})},
     "publishing", "A new publication of the numbers is being restored (started 2026-10-03T11:55:00+00:00)"),
    ({"fitted": None}, "no_projections", "No projections have been published."),
    ({"board": False}, "week_missing", "Week 4 of 2026 has no projections in the boards."),
    ({"lists": False}, "week_missing", "Week 4 of 2026 has no projections in the lists."),
    ({"ros": False}, "lists_empty", "The rest-of-season list is empty."),
])
def test_each_failing_check_is_a_503_reason_in_words(facts, code, words):
    ok, body = ready.probe(FakeConn(**facts), NOW)
    assert ok is False and body["ready"] is False and body["code"] == code
    assert body["reason"].startswith(words)


def test_a_marker_without_missing_tables_is_ignored():
    """The marker matters only while the tables are away (a stale marker never makes a published site 'not ready')."""
    ok, _ = ready.probe(FakeConn(db_comment=json.dumps({"publishing_since": "2026-10-01T11:55:00+00:00"})), NOW)
    assert ok is True


def test_after_the_last_kickoff_the_week_check_is_season_over():
    ok, body = ready.probe(FakeConn(next=None), NOW)
    assert ok is True and body["checks"]["week"]["note"] == "season over"


def test_the_route_answers_503_in_words_without_a_database_and_never_names_the_host(client, monkeypatch):
    ready.reset()
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "s3cret")              # the gate on: readiness needs no password
    monkeypatch.setattr(ready, "app_dsn", lambda: "postgresql://nobody:x@127.0.0.1:1/none")
    r = client.get("/api/ready")
    assert r.status_code == 503 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["ready"] is False and body["code"] == "database"
    assert body["reason"].startswith("The database does not answer (")
    assert "127.0.0.1" not in r.text and "nobody" not in r.text
    ready.reset()


def test_the_answer_is_kept_a_minute_after_a_success_and_15_seconds_after_a_failure(client, monkeypatch):
    calls = []
    answers = iter([(True, {"ready": True}), (False, {"ready": False})])

    def fake_check():
        calls.append(1)
        return next(answers)
    ready.reset()
    monkeypatch.setattr(ready, "check", fake_check)
    clock = [1000.0]
    monkeypatch.setattr(ready.time, "monotonic", lambda: clock[0])
    assert client.get("/api/ready").status_code == 200
    clock[0] += 59
    assert client.get("/api/ready").status_code == 200 and len(calls) == 1    # cached
    clock[0] += 2
    assert client.get("/api/ready").status_code == 503 and len(calls) == 2    # re-probed after 60 s
    clock[0] += 14
    assert client.get("/api/ready").status_code == 503 and len(calls) == 2
    ready.reset()


def test_ready_is_in_the_read_bucket_and_health_stays_unlimited():
    assert ratelimit.bucket_for("GET", "/api/ready") == "read"
    assert ratelimit.bucket_for("GET", "/api/health") is None


@needs_db
def test_ready_on_the_database_at_the_pinned_moment(client):
    ready.reset()
    r = client.get("/api/ready")
    body = r.json()
    assert r.status_code == 200, body
    assert body["checks"]["week"]["season"] == 2026 and body["checks"]["week"]["week"] == 4
    assert body["checks"]["as_of"] and body["checks"]["rest_of_season"] is True
    ready.reset()
