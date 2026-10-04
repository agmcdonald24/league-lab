"""Wave I-H (M6): "why this number" prices its pieces in the week's own mode (M4's not-done).

On the morning after the flip the record says week 4 flat (frozen) and weeks 5-18 at the odds; the card's pieces for
week 4 must stay flat (a long-TD bonus is not in the per-TD value) while week 5's carry the long TD's expected share.
The why tests need no database (the record is played by a stand-in reader). The parity tests (needs_db) read the
clone after a `project` with the cold-start blend on the line (M6's run on ``league_lab_m1``): a rookie starter's line
priced on request = his stored projection, and My Week's total = the record's (M4's parity) for every roster whose week-5
lineup starts a 2026 rookie RB / WR / TE. They hold in either state of the switch (that is the point).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import scoring as S

from league_lab_api import db, ondemand, why
from league_lab_api.applib import cards

from .conftest import DYNASTY, SCRUBS, needs_db

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


# ------------------------------------------------------------------------------ the blend on the line: request = record
ROOKIE_STARTERS = """select l.league_id, l.roster_id, l.gsis_id, l.position
    from ops.lineups as l join analytics.dim_player as d on d.gsis_id = l.gsis_id
    where l.season = %s and l.week = %s and not l.is_realised and l.role = 'starter' and d.rookie_season = %s
      and l.position in ('RB', 'WR', 'TE') and l.league_id = %s
      and l.run_at = (select max(run_at) from ops.lineups where league_id = l.league_id and season = l.season and week = l.week)
    order by l.roster_id, l.gsis_id"""


@pytest.fixture
def record_mode(monkeypatch):
    monkeypatch.delenv("LEAGUE_LAB_EV_PRICING", raising=False)
    S.set_record_reader(ondemand._pricing_rows)      # the API's own reader (M4's tests do the same)
    yield
    S.set_record_reader(ondemand._pricing_rows)


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_a_rookie_starters_line_prices_to_his_stored_projection(sql, record_mode, league):
    season, week = 2026, 5
    if not A.nfl_wide_ready(db.query, season, week):
        pytest.skip("no NFL-wide tables for week 5")
    rookies = sql(ROOKIE_STARTERS, (season, week, season, league))
    if not rookies:
        pytest.skip("no rookie RB / WR / TE starts in week 5")
    ids = sorted({r["gsis_id"] for r in rookies})
    lines = db.query("select * from ops.projection_lines where season = %s and week = %s and gsis_id = any(%s)",
                     (season, week, ids))
    stored = db.query("""select gsis_id, proj_points from ops.projections where league_id = %s and season = %s
                         and week = %s and gsis_id = any(%s)""", (league, season, week, ids)).set_index("gsis_id")
    sc = sql("select scoring_settings from analytics.dim_league_season where league_id = %s and is_current_season", (league,))
    scoring = {k: float(v) for k, v in sc[0]["scoring_settings"].items() if v is not None}
    priced = A.price_lines(lines, scoring).set_axis(lines["gsis_id"])
    assert len(priced) == len(ids)
    for g in ids:
        assert priced[g] == pytest.approx(float(stored.loc[g, "proj_points"]), abs=1e-9), g


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_my_week_equals_the_record_for_a_roster_with_a_rookie_starter(sql, record_mode, monkeypatch, league):
    """M4's parity on the rosters the blend touches: the on-demand lineup (lines priced on request) = ops.lineup_totals."""
    season, week = 2026, 5
    if not A.nfl_wide_ready(db.query, season, week):
        pytest.skip("no NFL-wide tables for week 5")
    monkeypatch.setenv(A.BOARD_SOURCE_ENV, "nfl_wide")
    rosters = sorted({int(r["roster_id"]) for r in sql(ROOKIE_STARTERS, (season, week, season, league))})
    if not rosters:
        pytest.skip("no rookie RB / WR / TE starts in week 5")
    lseason = cards.league_season(league)
    for team in rosters:
        mart = cards.lineup_rows(league, lseason, week, team)
        if mart.empty:
            continue
        as_of = pd.Timestamp(mart.loc[mart["role"] == "starter", "as_of"].dropna().iloc[0]).to_pydatetime()
        house = sql("""select lineup_value from ops.lineup_totals where league_id = %s and season = %s and week = %s
                       and roster_id = %s and not is_realised order by run_at desc limit 1""", (league, lseason, week, team))
        S.clear_pricing_cache()
        A.clear_priced()
        od = A.lineup_rows(db.query, league, team, week, as_of=as_of)
        total = float(od.rows.loc[od.rows["role"] == "starter", "lineup_value"].iloc[0])
        assert total == pytest.approx(float(house[0]["lineup_value"]), abs=0.005), (league, team)
