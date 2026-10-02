"""Plan H0 (Wave H): /api/health — what the host's health check and scripts/smoke.sh read."""

from __future__ import annotations

import pytest

from league_lab_api import main

from .conftest import needs_db


@pytest.fixture
def fresh_health(monkeypatch):
    """A health state as after a start: nothing read yet, the version not stamped."""
    monkeypatch.setattr(main, "_health_state", {"as_of": None, "database": "not checked yet", "next": 0.0,
                                                "version": None})


@needs_db
def test_health_reports_the_version_and_the_databases_as_of(client, sql, fresh_health, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_VERSION", "2026-10-02.h0")
    r = client.get("/api/health")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    newest = sql("select max(fitted_at) as t from ops.projections")[0]["t"]
    assert body == {"ok": True, "version": "2026-10-02.h0", "as_of": newest.isoformat(),
                    "board_source": body["board_source"], "database": "ok"}
    assert body["board_source"] in ("auto", "nfl_wide", "borrow")


def test_health_version_falls_back_to_the_hosts_commit(client, fresh_health, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_VERSION", "dev")                # the image's default when built without the arg
    monkeypatch.setenv("RENDER_GIT_COMMIT", "0123456789abcdef0123")
    assert client.get("/api/health").json()["version"] == "0123456789ab"


def test_health_needs_no_password_and_answers_when_the_database_does_not(client, fresh_health, monkeypatch):
    """Gate on, database unreachable: still 200 (a restart would not fix the database), the state in the body."""
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "s3cret")
    monkeypatch.setattr(main, "_app_dsn", lambda: "postgresql://nobody:x@127.0.0.1:1/none?connect_timeout=1")
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["as_of"] is None and body["database"].startswith("unreachable: ")
    assert main._health_state["next"] > 0                          # retried in a minute, not on every check
    assert client.get("/api/status").status_code == 401           # the rest stays behind the gate
