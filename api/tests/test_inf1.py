"""INF-1 (Wave I-I): the pinned clock on the request path (league_lab.clock).

The suite runs at `conftest.PINNED_NOW` (Saturday 2026-10-03 16:00 UTC: week 4's Thursday game played, nothing else).
Two routes that read the clock answer that moment — and another moment when a test pins one: /api/waivers (the
deadline: the next claim run and the next kickoff) and /api/player (the lock line). The stale rule (/api/health,
league_lab.freshness) keeps the real time.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest
from league_lab import clock

from .conftest import PINNED_NOW, SCRUBS, needs_db

SATURDAY = datetime(2026, 10, 3, 16, 0, tzinfo=UTC)
MACZADDY_STARTER = "00-0035358"     # Scrubs roster 2, a Sunday 1:00 PM ET game in week 4 (test_parity's case)


def test_the_suite_is_pinned():
    assert clock.parse(PINNED_NOW) == SATURDAY
    assert clock.now() == SATURDAY


def _next_kickoff(sql, season: int, week: int, after: datetime) -> str | None:
    rows = sql("""select min(kickoff_at) as k from analytics.dim_game
                  where season = %s and week = %s and season_type = 'REG' and kickoff_at > %s""", (season, week, after))
    k = rows[0]["k"] if rows else None
    return None if k is None else pd.Timestamp(k).tz_convert("UTC").isoformat()


@needs_db
@pytest.mark.parametrize("when, runs_at", [
    (None, "2026-10-07T07:00:00+00:00"),                       # the suite's Saturday: Wednesday's 3:00 AM ET run
    ("2026-10-08T00:00:00Z", "2026-10-14T07:00:00+00:00"),     # after it: the next Wednesday's
])
def test_waivers_deadline_answers_the_pinned_moment(client, sql, when, runs_at):
    """/api/waivers `deadline`: the next claim run (Sleeper's rolling waivers, the fixture's settings) and the decision
    week's next kickoff — both "after now", now being the league clock's."""
    with clock.pinned(when or PINNED_NOW) as now:
        w = client.get("/api/waivers", params={"league": SCRUBS, "team": 2}).json()
        d = w["deadline"]
        assert d["runs_at"] == runs_at
        season, week = int(w.get("season") or 2026), int(w["week"])
        want = _next_kickoff(sql, season, week, now)
        assert (d["lock"] or {}).get("kickoff") == want
        if when is None:
            assert week == 4 and want == "2026-10-04T13:30:00+00:00"     # Sunday's London game is next


@needs_db
@pytest.mark.parametrize("when, locked", [(None, False), ("2026-10-04T17:30:00Z", True)])
def test_the_player_card_lock_answers_the_pinned_moment(client, when, locked):
    """/api/player: "Week 4 kickoff … — not locked yet" on the suite's Saturday; "Locked for week 4" once his game
    has kicked off by the pinned clock (the wall clock never decides it)."""
    with clock.pinned(when or PINNED_NOW):
        card = client.get(f"/api/player/{MACZADDY_STARTER}", params={"league": SCRUBS, "team": 2}).json()
    text = " ".join(str(b) for b in card["sections"]["availability"]["blocks"])
    assert ("**Locked** for week 4" in text) is locked
    assert ("not locked yet" in text) is not locked


@needs_db
def test_the_stale_rule_keeps_the_real_time(client):
    """/api/health `age_hours` is the real age of the data (IH-1's rule): a pinned clock never hides a missed morning."""
    h = client.get("/api/health").json()
    if h["as_of"] is None:
        pytest.skip("no projections on this database")
    real = (datetime.now(UTC) - datetime.fromisoformat(h["as_of"])).total_seconds() / 3600
    pinned = (SATURDAY - datetime.fromisoformat(h["as_of"])).total_seconds() / 3600
    assert h["age_hours"] == pytest.approx(real, abs=0.2)
    assert abs(real - pinned) < 0.2 or h["age_hours"] != pytest.approx(pinned, abs=0.2)


def test_production_reads_the_real_time(real_clock):
    """LEAGUE_LAB_NOW unset (Render), nothing pinned: the request path's clock is the wall clock."""
    from league_lab import anyleague  # noqa: F401 - the on-demand path imports the same module

    assert not clock.is_pinned()
    assert abs((clock.now() - datetime.now(UTC)).total_seconds()) < 5
