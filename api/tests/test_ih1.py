"""Wave I-H (IH-1): the product says when it is stale; the events store keeps a bounded history.

* The stale rule (league_lab/freshness.py): the newest `ops.projections.fitted_at` older than 30 hours = a missed
  morning update. Stale after 30 h, not before; unknown (no as_of) is neither stale nor fresh.
* `/api/health` carries `stale` and `age_hours` (computed at the answer, so the hour-long as_of cache never hides a
  missed morning); `/api/status` carries `nightly` = {as_of, age_hours, stale, limit_hours, words}.
* `scripts/hosted_events.sql` prunes on every run: superseded `news` / `brief` rows ingested more than 120 days ago,
  `availability` rows ingested more than 400 days ago. Applied twice on the clone with old rows planted = pruned once.

The as_of fixture is 40 hours before a fixed clock (Sunday 2026-10-04 4:00 PM ET): Saturday 12:00 AM ET, yesterday.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pandas as pd
import psycopg
import pytest
from league_lab import freshness

from league_lab_api import main
from league_lab_api.settings import ROOT

from .conftest import needs_db

NOW = datetime(2026, 10, 4, 20, 0, tzinfo=UTC)          # Sunday 4:00 PM ET
WORDS = "Yesterday's numbers: the morning update did not run. Injury statuses are still live."
SQL_FILE = ROOT / "scripts" / "hosted_events.sql"


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(freshness, "_now", lambda: NOW)


def _health_as_of(monkeypatch, as_of: datetime | None):
    """The health state as after a read `as_of` ago that is not due again for an hour (no database read)."""
    import time
    monkeypatch.setattr(main, "_health_state", {"as_of": None if as_of is None else as_of.isoformat(), "database": "ok",
                                                "next": time.monotonic() + 3600, "version": "test"})


# ------------------------------------------------------------------------------------------------ the rule itself
def test_stale_after_30_hours_not_before():
    for hours, stale in ((0.5, False), (24, False), (29.9, False), (30.0, False), (30.1, True), (40, True), (200, True)):
        s = freshness.nightly_state(NOW - timedelta(hours=hours), NOW)
        assert s["stale"] is stale, hours
        assert s["age_hours"] == round(hours, 1) and s["limit_hours"] == 30
        assert (s["words"] is not None) is stale


def test_unknown_is_not_stale_and_not_fresh():
    for as_of in (None, "", pd.NaT, float("nan")):
        s = freshness.nightly_state(as_of, NOW)
        assert s == {"as_of": None, "age_hours": None, "stale": None, "limit_hours": 30, "words": None}


def test_the_words():
    """Yesterday's numbers for one missed morning; the day's name once the numbers are older than yesterday; the
    console's tail says its injury tags are the nightly's (it has no live overlay)."""
    assert freshness.nightly_state(NOW - timedelta(hours=40), NOW)["words"] == WORDS == freshness.STALE_WORDS
    two = freshness.nightly_state(datetime(2026, 10, 2, 11, 50, tzinfo=UTC), NOW)          # Friday 7:50 AM ET
    assert two["words"] == "Numbers from Friday, Oct 2: the morning update has not run since. Injury statuses are still live."
    con = freshness.nightly_state(NOW - timedelta(hours=40), NOW, console=True)
    assert con["words"] == "Yesterday's numbers: the morning update did not run. This console's injury tags are from that update too."
    # an ISO string (the health state's form) and a naive timestamp (read as UTC) give the same answer
    iso = freshness.nightly_state((NOW - timedelta(hours=40)).isoformat(), NOW)
    naive = freshness.nightly_state((NOW - timedelta(hours=40)).replace(tzinfo=None), NOW)
    assert iso == naive == freshness.nightly_state(NOW - timedelta(hours=40), NOW)


def test_the_words_never_claim_live_injuries_when_the_overlay_is_off(client, clock, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_AVAILABILITY", "off")
    _health_as_of(monkeypatch, NOW - timedelta(hours=40))

    def boom(*_a, **_k):
        raise RuntimeError("no database here")

    monkeypatch.setattr(main, "query", boom)
    assert main._status_nightly()["words"] == ("Yesterday's numbers: the morning update did not run. "
                                               "Injury statuses are from that update too.")


# ------------------------------------------------------------------------------------------------ /api/health
def test_health_says_stale_after_30_hours(client, clock, monkeypatch):
    _health_as_of(monkeypatch, NOW - timedelta(hours=40))
    body = client.get("/api/health").json()
    assert body["stale"] is True and body["age_hours"] == 40.0 and body["ok"] is True
    assert body["as_of"] == (NOW - timedelta(hours=40)).isoformat()


def test_health_is_not_stale_before_30_hours(client, clock, monkeypatch):
    _health_as_of(monkeypatch, NOW - timedelta(hours=29, minutes=30))
    body = client.get("/api/health").json()
    assert body["stale"] is False and body["age_hours"] == 29.5


def test_health_unknown_as_of_is_not_called_stale(client, clock, monkeypatch):
    _health_as_of(monkeypatch, None)
    body = client.get("/api/health").json()
    assert body["stale"] is None and body["age_hours"] is None


def test_health_age_grows_while_as_of_is_cached(client, monkeypatch):
    """The cache holds as_of for an hour; the age is the answer's own, so a morning missed during the hour shows."""
    _health_as_of(monkeypatch, NOW - timedelta(hours=29))
    monkeypatch.setattr(freshness, "_now", lambda: NOW)
    assert client.get("/api/health").json()["stale"] is False
    monkeypatch.setattr(freshness, "_now", lambda: NOW + timedelta(hours=2))
    body = client.get("/api/health").json()
    assert body["stale"] is True and body["age_hours"] == 31.0


# ------------------------------------------------------------------------------------------------ /api/status
def _status_with_as_of(client, monkeypatch, as_of):
    """/api/status with the fitted_at read answering `as_of` (every other read goes to the clone)."""
    real = main.query

    def fake(sql, params=None, *a, **k):
        if "max(fitted_at)" in sql:
            return pd.DataFrame({"t": [pd.Timestamp(as_of) if as_of is not None else pd.NaT]})
        return real(sql, params, *a, **k) if params is not None else real(sql, *a, **k)

    monkeypatch.setattr(main, "query", fake)
    return client.get("/api/status").json()


@needs_db
def test_status_carries_the_nightly_block(client, clock, monkeypatch):
    """The route on the clone. The tests run the availability overlay off (conftest), so the words' tail is the
    overlay-off one here; the production tail ("still live") is pinned by the next test."""
    _health_as_of(monkeypatch, None)
    s = _status_with_as_of(client, monkeypatch, NOW - timedelta(hours=40))
    assert s["nightly"] == {"as_of": (NOW - timedelta(hours=40)).isoformat(), "age_hours": 40.0, "stale": True,
                            "limit_hours": 30, "words": WORDS.replace("are still live", "are from that update too")}
    assert isinstance(s["freshness"], str)                        # the footer's caption is untouched (IF-4)
    assert "warning" in s and "updated_at" in s
    # the newer as_of reached the health state: the two answers agree without waiting for the hourly read
    assert client.get("/api/health").json()["stale"] is True


def test_status_words_with_the_overlay_on(clock, monkeypatch):
    """Production (the overlay on): the brief's words, exactly. Only the block's builder runs (no route, no feed)."""
    _health_as_of(monkeypatch, None)
    monkeypatch.setattr(main.availability, "enabled", lambda: True)
    monkeypatch.setattr(main, "query", lambda *_a, **_k: pd.DataFrame({"t": [pd.Timestamp(NOW - timedelta(hours=40))]}))
    assert main._status_nightly() == {"as_of": (NOW - timedelta(hours=40)).isoformat(), "age_hours": 40.0,
                                      "stale": True, "limit_hours": 30, "words": WORDS}


@needs_db
def test_status_fresh_and_unknown(client, clock, monkeypatch):
    _health_as_of(monkeypatch, None)
    s = _status_with_as_of(client, monkeypatch, NOW - timedelta(hours=3))
    assert s["nightly"]["stale"] is False and s["nightly"]["words"] is None and s["nightly"]["age_hours"] == 3.0
    s = _status_with_as_of(client, monkeypatch, None)
    assert s["nightly"]["stale"] is None and s["nightly"]["as_of"] is None


@needs_db
def test_status_reads_the_clone_as_it_is(client, sql):
    """No monkeypatch: the clone's newest fitted_at (a snapshot days old) is reported as it is."""
    newest = sql("select max(fitted_at) as t from ops.projections")[0]["t"]
    n = client.get("/api/status").json()["nightly"]
    assert pd.Timestamp(n["as_of"]) == pd.Timestamp(newest)
    assert n["stale"] is (datetime.now(UTC) - newest > timedelta(hours=30))


def test_status_survives_a_failed_read(client, clock, monkeypatch):
    """The fitted_at read fails: the health state's last value answers (a status line, never a failure)."""
    _health_as_of(monkeypatch, NOW - timedelta(hours=40))

    def boom(*_a, **_k):
        raise RuntimeError("down")

    monkeypatch.setattr(main, "query", boom)
    assert main._status_nightly()["stale"] is True


# ------------------------------------------------------------------------------------------------ events retention
def _pipeline_dsn() -> str:
    from league_lab.config import get_settings
    return get_settings().pipeline_dsn()


def _fp(tag: str) -> str:
    return hashlib.sha256(f"ih1-test:{tag}".encode()).hexdigest()


@needs_db
def test_hosted_events_sql_prunes_old_rows_once():
    """Planted rows: old superseded news / brief (pruned), old live news (kept: a player's newest item), old
    availability live and superseded past 400 days (pruned), availability at 200 days (kept), a fresh superseded news
    row (kept). Applied twice: the second run deletes nothing more."""
    try:
        conn = psycopg.connect(_pipeline_dsn(), autocommit=True, connect_timeout=5)
    except psycopg.Error as exc:
        pytest.skip(f"cannot reach the clone with the pipeline role: {exc.__class__.__name__}")
    with conn:
        conn.execute(SQL_FILE.read_text())                             # the table exists (idempotent)
        conn.execute("delete from events.events where fingerprint like any(%s)", ([_fp(t) for t in TAGS],))
        ids = {}
        for tag, kind, days, _superseded in PLANTED:
            ids[tag] = conn.execute(
                """insert into events.events (kind, gsis_id, status, source, published_at, ingested_at, fingerprint)
                   values (%s, '00-0036322', %s, 'ESPN', now() - %s * interval '1 day', now() - %s * interval '1 day', %s)
                   returning id""",
                (kind, "OUT" if kind == "availability" else "player", days, days, _fp(tag))).fetchone()[0]
        live = ids["live_news_old"]
        for tag, _kind, _days, superseded in PLANTED:
            if superseded:
                conn.execute("update events.events set superseded_by = %s where id = %s", (live, ids[tag]))
        try:
            def left() -> set[str]:
                rows = conn.execute("select fingerprint from events.events where fingerprint = any(%s)",
                                    ([_fp(t) for t in TAGS],)).fetchall()
                back = {_fp(t): t for t in TAGS}
                return {back[r[0]] for r in rows}

            assert left() == set(TAGS)
            conn.execute(SQL_FILE.read_text())
            after_one = left()
            assert after_one == KEPT, sorted(after_one ^ KEPT)
            conn.execute(SQL_FILE.read_text())
            assert left() == after_one                                 # twice = once
        finally:
            conn.execute("update events.events set superseded_by = null where fingerprint = any(%s)", ([_fp(t) for t in TAGS],))
            conn.execute("delete from events.events where fingerprint = any(%s)", ([_fp(t) for t in TAGS],))


# tag, kind, days ago (ingested), superseded
PLANTED = [
    ("news_old_superseded", "news", 121, True),
    ("brief_old_superseded", "brief", 200, True),
    ("live_news_old", "news", 300, False),
    ("news_recent_superseded", "news", 119, True),
    ("brief_recent_superseded", "brief", 10, True),
    ("avail_old_live", "availability", 401, False),
    ("avail_old_superseded", "availability", 500, True),
    ("avail_200", "availability", 200, True),
    ("avail_recent", "availability", 1, False),
]
TAGS = [p[0] for p in PLANTED]
KEPT = {"live_news_old", "news_recent_superseded", "brief_recent_superseded", "avail_200", "avail_recent"}
