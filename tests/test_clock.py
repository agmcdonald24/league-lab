"""INF-1 (Wave I-I): league_lab.clock — pin / unpin, ISO parsing, UTC, the real time when nothing is set."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from league_lab import clock


def test_suite_runs_pinned():
    """The conftest pins the whole suite (a subprocess inherits it through the environment)."""
    from tests.conftest import PINNED_NOW

    assert clock.is_pinned()
    assert clock.now() == datetime(2026, 10, 3, 16, 0, tzinfo=UTC)
    assert clock.now() == clock.parse(PINNED_NOW)


def test_real_when_unset(real_clock):
    """Production (Render): LEAGUE_LAB_NOW unset, nothing pinned → the real time, aware, UTC."""
    assert not real_clock.is_pinned()
    before = datetime.now(UTC)
    got = real_clock.now()
    after = datetime.now(UTC)
    assert got.tzinfo is not None and got.utcoffset() == timedelta(0)
    assert before <= got <= after


def test_blank_env_is_unset(real_clock, monkeypatch):
    monkeypatch.setenv(clock.ENV, "   ")
    assert not clock.is_pinned()
    assert abs((clock.now() - datetime.now(UTC)).total_seconds()) < 5


@pytest.mark.parametrize(
    "text, want",
    [
        ("2026-10-03T16:00:00Z", datetime(2026, 10, 3, 16, 0, tzinfo=UTC)),
        ("2026-10-03T16:00:00z", datetime(2026, 10, 3, 16, 0, tzinfo=UTC)),
        ("2026-10-03T16:00:00+00:00", datetime(2026, 10, 3, 16, 0, tzinfo=UTC)),
        ("2026-10-03T12:00:00-04:00", datetime(2026, 10, 3, 16, 0, tzinfo=UTC)),   # New York's EDT → UTC
        ("2026-10-03T16:00:00", datetime(2026, 10, 3, 16, 0, tzinfo=UTC)),         # naive = UTC
        ("2026-10-03 16:00", datetime(2026, 10, 3, 16, 0, tzinfo=UTC)),
        (" 2026-10-03T16:00:00.250Z ", datetime(2026, 10, 3, 16, 0, 0, 250_000, tzinfo=UTC)),
    ],
)
def test_iso_parsing_is_utc(text, want):
    got = clock.parse(text)
    assert got == want
    assert got.tzinfo == UTC


@pytest.mark.parametrize("bad", ["", "  ", "Saturday", "2026-13-01T00:00:00Z"])
def test_bad_iso_raises(bad):
    with pytest.raises(ValueError):
        clock.parse(bad)


def test_env_moment(real_clock, monkeypatch):
    monkeypatch.setenv(clock.ENV, "2026-10-05T00:20:00Z")
    assert clock.is_pinned()
    assert clock.now() == datetime(2026, 10, 5, 0, 20, tzinfo=UTC)


def test_pin_beats_env_and_unpin_restores_it(monkeypatch):
    monkeypatch.setenv(clock.ENV, "2026-10-05T00:20:00Z")
    got = clock.pin(datetime(2026, 10, 4, 17, 0, tzinfo=timezone(timedelta(hours=-4))))   # 1 PM ET
    assert got == datetime(2026, 10, 4, 21, 0, tzinfo=UTC)
    assert clock.now() == got and clock.now().tzinfo == UTC
    clock.unpin()
    assert clock.now() == datetime(2026, 10, 5, 0, 20, tzinfo=UTC)


def test_pin_naive_datetime_is_utc():
    assert clock.pin(datetime(2026, 9, 10, 0, 20)) == datetime(2026, 9, 10, 0, 20, tzinfo=UTC)


def test_pinned_context_restores_the_previous_pin():
    clock.pin("2026-10-01T00:00:00Z")
    with clock.pinned("2026-10-02T00:00:00Z") as t:
        assert t == clock.now() == datetime(2026, 10, 2, tzinfo=UTC)
        with clock.pinned("2026-10-02T12:00:00Z"):
            assert clock.now() == datetime(2026, 10, 2, 12, tzinfo=UTC)
        assert clock.now() == datetime(2026, 10, 2, tzinfo=UTC)
    assert clock.now() == datetime(2026, 10, 1, tzinfo=UTC)


def test_pinned_context_restores_after_an_error():
    with pytest.raises(RuntimeError), clock.pinned("2026-10-02T00:00:00Z"):
        raise RuntimeError("boom")
    assert clock.now() == datetime(2026, 10, 3, 16, 0, tzinfo=UTC)          # back to the suite's moment


def test_the_env_is_read_on_every_call(real_clock, monkeypatch):
    """Never cached: a test (or a process) that changes LEAGUE_LAB_NOW sees the new moment at once."""
    monkeypatch.setenv(clock.ENV, "2026-10-01T00:00:00Z")
    assert clock.now() == datetime(2026, 10, 1, tzinfo=UTC)
    monkeypatch.setenv(clock.ENV, "2026-10-02T00:00:00Z")
    assert clock.now() == datetime(2026, 10, 2, tzinfo=UTC)


def test_the_stale_rule_is_not_pinned():
    """freshness.py keeps the real time: a pinned clock must never hide a missed morning (IH-1)."""
    from league_lab import freshness

    real = freshness._now()
    assert abs((real - datetime.now(UTC)).total_seconds()) < 5
    assert real != clock.now()


def test_now_floored_is_on_the_kickoff_marks():
    """A cached query's "kicked off by now" (app/lib/cards.py LINEUP_SQL): exact on five-minute kickoffs."""
    with clock.pinned("2026-10-04T20:09:59.900Z"):
        assert clock.now_floored() == datetime(2026, 10, 4, 20, 5, tzinfo=UTC)      # the 4:05 PM ET game has started
    with clock.pinned("2026-10-04T20:04:59Z"):
        assert clock.now_floored() == datetime(2026, 10, 4, 20, 0, tzinfo=UTC)      # ... not yet
        assert clock.now_floored(1) == datetime(2026, 10, 4, 20, 4, tzinfo=UTC)
    assert clock.now_floored() == clock.now()                                        # the suite's 16:00:00 is a mark
