"""Wave I-H (M6): "why this number" prices its pieces in the week's own mode (M4's not-done).

On the morning after the flip the record says week 4 flat (frozen) and weeks 5-18 at the odds; the card's pieces for
week 4 must stay flat (a long-TD bonus is not in the per-TD value) while week 5's carry the long TD's expected share.
No database: the record is played by a stand-in reader.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from league_lab import scoring as S

from league_lab_api import why

LONG = {"rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0, "rush_yd": 0.1, "rush_td": 6.0, "fum_lost": -2.0, "rec_td_40p": 2.0,
        "rush_td_40p": 2.0}
LINE = {"targets": 7.0, "receptions": 5.0, "receiving_yards": 70.0, "receiving_tds": 0.5, "carries": 0.0,
        "rushing_yards": 0.0, "rushing_tds": 0.0, "fumbles_lost_total": 0.05}


@pytest.fixture
def flipped(monkeypatch):
    monkeypatch.delenv("LEAGUE_LAB_EV_PRICING", raising=False)
    t4, t5 = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 5, tzinfo=UTC)
    S.set_record_reader(lambda: [(2026, 4, t4, False), *[(2026, w, t5, True) for w in range(5, 19)]])
    yield
    S.set_record_reader(None)


def test_weights_follow_the_weeks_mode(flipped):
    flat = why.weights(LONG, "WR", season=2026, week=4)
    ev = why.weights(LONG, "WR", season=2026, week=5)
    assert flat["receiving_tds"] == 6.0                       # the frozen flat week: a TD is 6, the 40+ bonus is not in it
    assert ev["receiving_tds"] > 6.0                          # at the odds: 6 + 2 x the measured 40+ share
    assert why.weights(LONG, "WR") == ev                      # no week: the newest build's mode, as before
    with S.pinned_pricing("flat"):                            # a pin (or the env) still overrides
        assert why.weights(LONG, "WR", season=2026, week=5) == flat


def test_explain_passes_the_week(flipped):
    e4 = why.explain(LINE, 20.0, LONG, "WR", season=2026, week=4)
    e5 = why.explain(LINE, 20.0, LONG, "WR", season=2026, week=5)
    td4 = next(p for p in e4["pieces"] if p["stat"] == "receiving_tds")
    td5 = next(p for p in e5["pieces"] if p["stat"] == "receiving_tds")
    assert td4["each"] == 6.0 and td5["each"] > 6.0
    assert sum(p["points"] for p in e4["pieces"]) == pytest.approx(20.0, abs=0.011)   # the list still adds up
