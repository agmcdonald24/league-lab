"""Wave I-C (IC-1): the scoring check — our points against each league's own for a scored week, on the clone's
2026-09-26 snapshot (weeks 1-2 complete; week 3 is Thursday night only).

* House leagues: Sleeper's per-player points (``analytics.league_player_week`` / ``staging.stg_sleeper__matchup_players``)
  against the spec on ``fct_player_game``; also the dbt macro's twin (``fct_player_game_league``).
* The Test League (``9000000000000000001``): ``players_points`` in its week 1-2 matchups fixtures were built with the
  pre-spec flat engine (``fixtures/make_ic1_fixtures.py``), so the check is 100% within 0.1 by construction.
* Dad's league MFL 70587: MFL's ``weeklyResults`` per-player scores (IC-3's fixtures) against the spec compiled from
  its rules; ``fixtures/ic1/db_playerids_70587.csv`` is the nflverse id table trimmed to that league's players.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import player_ids as PI

from .conftest import DYNASTY, SCRUBS, needs_db

FX = Path(__file__).with_name("fixtures")
TEST = "9000000000000000001"
DAD = "mfl:70587"


@pytest.fixture
def mfl_70587(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(FX / "mfl"))
    monkeypatch.setenv(PI.CSV_ENV, str(FX / "ic1" / "db_playerids_70587.csv"))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    from league_lab_api import main
    main._scoring_checks.clear()
    yield
    PI.reset()
    A._default = None


@pytest.fixture(autouse=True)
def _no_cached_checks():
    from league_lab_api import main
    main._scoring_checks.clear()
    yield
    main._scoring_checks.clear()


def _get(client, league: str, week: int | None = None) -> dict:
    url = f"/api/league/scoring-check?league={league}" + (f"&week={week}" if week is not None else "")
    r = client.get(url)
    assert r.status_code == 200, r.text
    return r.json()


@needs_db
@pytest.mark.parametrize("week", [1, 2])
def test_house_leagues_match_sleeper_and_the_sql(client, week):
    for lid in (SCRUBS, DYNASTY):
        out = _get(client, lid, week)
        assert out["source"] == "sleeper" and out["week"] == week and out["n"] >= 140
        assert out["within_1"] == out["n"] and out["within_0_1"] == out["n"], out["misses"][:5]
        assert out["theirs_from"] == "analytics.league_player_week"
        assert out["sql"] is not None and out["sql"]["n"] >= 130 and out["sql"]["disagree"] == []
        assert out["words"].startswith(f"Week {week} check: we match the league's own points for")


@needs_db
def test_house_league_default_week_is_the_last_complete_one(client):
    out = _get(client, SCRUBS)
    assert out["scored_weeks"] == [1, 2] and out["week"] == 2


@needs_db
def test_week_three_is_not_complete_and_says_so(client):
    out = _get(client, SCRUBS, 3)
    assert out["n"] == 0 and "not complete" in out["words"] and out["misses"] == []


@needs_db
@pytest.mark.parametrize("week", [1, 2])
def test_test_league_is_exact_by_construction(client, week):
    out = _get(client, TEST, week)
    assert out["theirs_from"] == "sleeper matchups" and out["n"] >= 140
    assert out["within_0_1"] == out["n"], out["misses"][:5]
    assert out["sql"] is None                      # not a house league: no macro twin


@needs_db
def test_dads_league_week_2(client, mfl_70587):
    out = _get(client, DAD, 2)
    assert out["source"] == "mfl" and out["theirs_from"] == "MyFantasyLeague weeklyResults"
    assert out["n"] >= 150 and out["within_1"] / out["n"] >= 0.90
    assert out["unmatched"] == [] and out["spec_unpriced"] == []
    for m in out["misses"]:
        assert m["likely_rule"] and m["likely_rule"] != "unexplained", m
    print("70587 week 2:", out["words"])


@needs_db
def test_dads_league_week_1_units_and_the_named_miss(client, mfl_70587):
    out = _get(client, DAD, 1)
    assert out["n"] >= 150 and out["within_1"] / out["n"] >= 0.95
    assert all(m["position"] == "DEF" for m in out["misses"])           # every player and unit line exact
    print("70587 week 1:", out["words"])


@needs_db
def test_unknown_league_is_404(client):
    r = client.get("/api/league/scoring-check?league=1234567890123456789")
    assert r.status_code == 404


def test_league_spec_from_the_mfl_translation(mfl_70587):
    lg = A.sleeper().league(DAD)
    spec = A.league_spec(lg)
    assert spec.source == "mfl" and spec.rules_for("TMQB") is spec.positions["QB"]
    sc, _ = A.league_scoring(lg)
    assert sc.spec.key() == spec.key()
    rep = A.scoring_report(sc, lg["roster_positions"])
    assert rep["priced"][0] == "TDs by distance 6 / 9 / 12" and rep["unpriced"] == []
    assert any("distance" in a for a in rep["approximated"])
    # the flat summary is filled for the old readers (the I0-B translation found nothing for 70587's offense)
    assert lg["scoring_settings"]["rush_yd"] == 0.1 and lg["scoring_settings"]["pass_td"] == 6.0


@needs_db
def test_price_lines_on_the_mfl_spec_and_house_parity(mfl_70587):
    import pandas as pd

    from league_lab_api.db import query
    b = A.load_board(query, 2026, 4)
    dad, _ = A.league_scoring(A.sleeper().league(DAD))
    scrubs, _ = A.league_scoring(A.sleeper().league(SCRUBS))
    p = A.price_lines(b.line, dad)
    flat = A.price_lines(b.line, dict(scrubs))            # the flat dict alone: the pre-spec path
    assert (A.price_lines(b.line, scrubs) == flat).all()  # a Sleeper spec prices bit for bit as before
    top = pd.concat([b.line["position"], p.rename("p")], axis=1).groupby("position")["p"].max()
    assert top["QB"] > 30 and top["RB"] > 15 and top["WR"] > 8 and top["TE"] > 5    # no 15-point lineups
    units = b.line[b.line["position"] == "QB"].head(3).assign(position="TMQB")
    assert (A.price_lines(units, dad).to_numpy() == p.loc[units.index].to_numpy()).all()
