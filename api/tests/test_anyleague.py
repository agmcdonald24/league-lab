"""Plan E3: My Week for any Sleeper league, served without that league in the database (`league_lab.anyleague`,
`league_lab_api.ondemand`), checked against the nightly's marts for the two leagues the database does have.

The fixtures (`tests/fixtures/sleeper/`) are the two leagues' own Sleeper payloads from `raw.sleeper_*`, trimmed to
the fields the path reads (`python -m league_lab.anyleague fixtures <dir> <id> ...` rebuilds them). Each known league
is served as if it were new: its ranges come from the OTHER league (the path never uses a league's own fitted
ranges), so the gap to the fitted ranges is the error a new league would see.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import clock  # ---- INF-1

from league_lab_api import db, ondemand
from league_lab_api.applib import cards

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db

FIXTURES = Path(__file__).with_name("fixtures") / "sleeper"
OTHER = {DYNASTY: SCRUBS, SCRUBS: DYNASTY}
Q = ("p10", "p25", "p50", "p75", "p90")


@pytest.fixture(autouse=True)
def _borrowed_board(monkeypatch):
    """E3's measures are of the BORROWED board (each house league priced as if new, its ranges from the other):
    pinned here whatever F1 tables the database has (tests/test_f3.py covers the NFL-wide board)."""
    monkeypatch.setenv(A.BOARD_SOURCE_ENV, "borrow")


@pytest.fixture
def fixtures(monkeypatch):
    monkeypatch.setenv(A.FIXTURES_ENV, str(FIXTURES))
    A._default = None
    yield FIXTURES
    A._default = None


def _mart_rows(league: str, team: int) -> tuple[int, int, pd.DataFrame]:
    season = cards.league_season(league)
    week = cards.decision_week(season)
    rows = cards.lineup_rows(league, season, week, team)
    assert not rows.empty, "no proposed lineup in the mart"
    return season, week, rows


def _as_of(rows: pd.DataFrame):
    return pd.Timestamp(rows.loc[rows["role"] == "starter", "as_of"].dropna().iloc[0]).to_pydatetime()


def _kicked_off_since(season: int, week: int, as_of) -> bool:
    """Has a game of the week kicked off between the nightly's solve and now (the mart's cards then lock players
    the on-demand solve, pinned to the nightly's clock, does not)?"""
    g = db.query("select count(*) as n from analytics.dim_game where season = %s and week = %s and season_type = 'REG' "
                 "and kickoff_at > %s and kickoff_at <= %s", (season, week, as_of, clock.now()))   # ---- INF-1
    return int(g["n"].iloc[0]) > 0


# ------------------------------------------------------------------------------ no database needed
def test_league_ids_are_digits_only():
    for bad in ("../../etc/passwd", "abc", "", "1389709692405551104/rosters", "1" * 30):
        with pytest.raises(A.LeagueNotFound):
            A.check_id(bad)
    assert A.check_id(" 1389709692405551104 ") == "1389709692405551104"


def test_scoring_report_names_what_the_projection_cannot_price():
    dyn = json.loads((FIXTURES / f"league_{DYNASTY}.json").read_text())
    rep = A.scoring_report(dyn["scoring_settings"], dyn["roster_positions"])
    assert rep["unmapped"] == []                      # no DEF slot: the defense keys do not matter there
    assert {"pass_td_40p", "rec_td_40p", "rush_td_40p", "pass_2pt"} <= set(rep["not_projected"])
    assert "bonus_rec_yd_100" not in rep["not_projected"]          # yardage bonuses price on the projected line
    scrubs = json.loads((FIXTURES / f"league_{SCRUBS}.json").read_text())
    rep = A.scoring_report(scrubs["scoring_settings"], scrubs["roster_positions"])
    assert rep["unmapped"] == []                      # its DEF keys are the ones kd1.0 projects
    rep = A.scoring_report({**scrubs["scoring_settings"], "bonus_rec_te": 0.5, "idp_tkl": 1}, scrubs["roster_positions"])
    assert rep["unmapped"] == ["bonus_rec_te", "idp_tkl"]


def test_approximate_ranges_scale_with_the_price():
    ref = pd.DataFrame({"proj_points": [10.0, 10.0, 0.0], "p10": [4.0, 4.0, 0.0], "p25": [7.0, 7.0, 0.0],
                        "p50": [9.0, 9.0, 0.0], "p75": [13.0, 13.0, 1.0], "p90": [18.0, 18.0, 3.0]}, index=["a", "b", "c"])
    proj = pd.Series([12.0, 10.0, 0.5, 7.0], index=["a", "b", "c", "d"])
    r = A.approximate_ranges(proj, ref)
    assert r.loc["a"].tolist() == [4.8, 8.4, 10.8, 15.6, 21.6]     # offsets x 1.2
    assert r.loc["b"].tolist() == [4.0, 7.0, 9.0, 13.0, 18.0]      # same price: the reference's range
    assert r.loc["c"].tolist() == [0.5, 0.5, 0.5, 1.5, 3.5]         # no ratio from a zero price: the offsets unscaled
    assert r.loc["d"].isna().all()                                  # not on the reference board: unknown, not 0


# ------------------------------------------------------------------------------ against the database
@needs_db
def test_pricing_reproduces_every_league_points_exactly():
    """compute_points on the NFL-wide stat line = ops.projections.proj_points of every v3 row, both leagues; the stat
    lines are the same in both leagues (the design's premise)."""
    season = cards.league_season(SCRUBS)
    week = cards.decision_week(season)
    b = A.load_board(db.query, season, week)
    assert b.mismatched_lines == 0
    assert len(b.line) > 400
    for league, f in b.fitted.items():
        mine = A.price_lines(b.line.loc[f.index], b.scorings[league], season=b.season, week=b.week)   # M4: the week's mode
        gap = (mine - f["proj_points"]).abs()
        assert gap.max() < 1e-9, f"{league}: {int((gap > 1e-9).sum())} rows priced differently, max {gap.max()}"


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_on_demand_lineup_reproduces_the_mart(fixtures, league):
    """Acceptance: the same starters in the same slots, values and margins within 0.01, the lineup value within
    0.01, the same bench in the same order and the same players who cannot play (with the same reasons)."""
    team = ANDREW[league]
    season, week, mart = _mart_rows(league, team)
    od = A.lineup_rows(db.query, league, team, week, as_of=_as_of(mart))
    assert od.reference_league == OTHER[league]
    assert od.unmapped_players == [] and od.mismatched_lines == 0
    got = od.rows
    ms, gs = mart[mart["role"] == "starter"], got[got["role"] == "starter"]
    assert list(ms["slot"]) == list(gs["slot"])
    assert list(ms["sleeper_player_id"]) == list(gs["sleeper_player_id"])
    np.testing.assert_allclose(gs["value"].astype(float), ms["value"].astype(float), atol=0.01)
    np.testing.assert_allclose(gs["margin"].astype(float), ms["margin"].astype(float), atol=0.01)
    assert abs(float(gs["lineup_value"].iloc[0]) - float(ms["lineup_value"].iloc[0])) <= 0.01
    for role in ("bench", "unplayable"):
        mb, gb = mart[mart["role"] == role], got[got["role"] == role]
        assert sorted(mb["sleeper_player_id"]) == sorted(gb["sleeper_player_id"]), role
        if role == "bench":
            assert list(mb["sleeper_player_id"]) == list(gb["sleeper_player_id"])
            np.testing.assert_allclose(gb["value"].astype(float), mb["value"].astype(float), atol=0.01)
        else:
            assert dict(zip(mb["sleeper_player_id"], mb["reason"], strict=True)) == dict(zip(gb["sleeper_player_id"], gb["reason"], strict=True))
    if league == SCRUBS:
        assert od.kd_sources == {"K": SCRUBS, "DEF": SCRUBS}       # identical K / DEF keys: the fitted K / DEF values


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_range_error_on_the_roster(fixtures, league):
    """The approximated ranges of the roster's projected players vs the ranges fitted for this league (the error a
    league the model never saw would carry). Measured, then bounded: mean absolute gap per quantile."""
    team = ANDREW[league]
    season, week, mart = _mart_rows(league, team)
    od = A.lineup_rows(db.query, league, team, week, as_of=_as_of(mart))
    m = mart[mart["gsis_id"].notna() & mart["p10"].notna()].set_index("gsis_id")
    g = od.rows[od.rows["gsis_id"].notna()].drop_duplicates("gsis_id").set_index("gsis_id").reindex(m.index)
    gaps = {q: float((g[q].astype(float) - m[q].astype(float)).abs().mean()) for q in Q}
    print(f"\nrange gap {league} roster {team} week {week} ({len(m)} players, reference {od.reference_league}): "
          + ", ".join(f"{q} {v:.2f}" for q, v in gaps.items()))
    assert len(m) >= 10
    assert gaps["p10"] < 1.0 and gaps["p25"] < 1.0 and gaps["p50"] < 1.0
    assert gaps["p75"] < 1.5 and gaps["p90"] < 2.0


@needs_db
def test_range_error_on_the_whole_board():
    """Every projected player of the week, each league approximated from the other: mean absolute gap per quantile
    and the 80% / 50% widths (docs/ANY_LEAGUE.md § The ranges has the same measure over weeks 4-18)."""
    season = cards.league_season(SCRUBS)
    week = cards.decision_week(season)
    b = A.load_board(db.query, season, week)
    for new, ref in ((DYNASTY, SCRUBS), (SCRUBS, DYNASTY)):
        fit = b.fitted[new]
        apx = A.approximate_ranges(fit["proj_points"], b.fitted[ref])
        gaps = {q: float((apx[q] - fit[q]).abs().mean()) for q in Q}
        w80 = float((apx["p90"] - apx["p10"]).mean()) / float((fit["p90"] - fit["p10"]).mean())
        print(f"\nboard week {week}: {new} from {ref} ({len(fit)} players): "
              + ", ".join(f"{q} {v:.2f}" for q, v in gaps.items()) + f"; width80 ratio {w80:.3f}")
        assert max(gaps.values()) < 1.2
        assert 0.95 < w80 < 1.05


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_route_serves_the_same_week_on_demand(client, fixtures, league):
    """`source=sleeper` forces the on-demand path for a known league: the lineup table and the cards' calls are
    the database path's (the probabilities move a little: the ranges are approximated)."""
    team = ANDREW[league]
    season, week, mart = _mart_rows(league, team)
    base = client.get(f"/api/my-week?league={league}&team={team}").json()
    r = client.get(f"/api/my-week?league={league}&team={team}&source=sleeper")
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "sleeper" and d["week"] == base["week"]
    assert d["team_name"].startswith("Team ") and d["record"]["wins"] + d["record"]["losses"] >= 0   # pseudonymised fixture
    assert d["on_demand"]["range_reference_league"] == OTHER[league]
    if _kicked_off_since(season, week, _as_of(mart)):
        pytest.skip("a game kicked off after the nightly solved the week: the two paths' locks differ by design")
    assert [(x["slot"], x["gsis_id"], x["value"], x["margin"]) for x in d["lineup"]] == \
           [(x["slot"], x["gsis_id"], x["value"], x["margin"]) for x in base["lineup"]]
    assert d["lineup_value"] == pytest.approx(base["lineup_value"], abs=0.01)
    assert [(c["slot"], c["alt_gsis_id"], c["margin"]) for c in d["cards"]] == \
           [(c["slot"], c["alt_gsis_id"], c["margin"]) for c in base["cards"]]
    for c, b in zip(d["cards"], base["cards"], strict=True):
        if c["p_win"] is not None and b["p_win"] is not None:
            assert abs(c["p_win"] - b["p_win"]) < 0.1
    assert d["howto"] == base["howto"]


@needs_db
def test_unknown_league_falls_through_to_sleeper(client, tmp_path, monkeypatch):
    """A league the database has never seen (the dynasty payloads under a new id) is served by the same route; a
    league with exactly a fitted league's scoring gets exactly that league's ranges (its prices match: ratio 1)."""
    new_id = "990000000000000012"
    for kind in ("league", "rosters", "users"):
        data = json.loads((FIXTURES / f"{kind}_{DYNASTY}.json").read_text())
        for item in data if isinstance(data, list) else [data]:
            item["league_id"] = new_id
        (tmp_path / f"{kind}_{new_id}.json").write_text(json.dumps(data))
    shutil.copy(FIXTURES / "players_nfl.json", tmp_path / "players_nfl.json")
    monkeypatch.setenv(A.FIXTURES_ENV, str(tmp_path))
    A._default = None
    r = client.get(f"/api/my-week?league={new_id}&team=12")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] == "sleeper" and d["league_name"] == "Forever Unclean Dynasty"
    assert d["on_demand"]["range_reference_league"] == DYNASTY
    assert d["lineup"] and d["cards"]
    mart = db.query("""select p.gsis_id, p.p10, p.p90 from analytics.mart_player_week_projections p
                       where p.league_id = %s and p.season = %s and p.week = %s""", (DYNASTY, d["season"], d["week"]))
    fitted = mart.set_index("gsis_id")
    od = A.lineup_rows(db.query, new_id, 12, d["week"])
    rows = od.rows[od.rows["gsis_id"].isin(fitted.index) & od.rows["p10"].notna()]
    assert len(rows) >= 10
    assert (rows["p10"].to_numpy() - fitted.loc[rows["gsis_id"], "p10"].astype(float).to_numpy()).__abs__().max() <= 0.011
    assert client.get(f"/api/my-week?league={new_id}&team=99").status_code == 404
    assert client.get("/api/my-week?league=not-a-league&team=1").status_code == 404
    A._default = None


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_latency_cold_and_warm(fixtures, league):
    """Cold = empty query cache and a new Sleeper client (fixtures: no network); warm = both cached. Printed for
    the hand-back; bounded loosely (a loaded 2-core sandbox)."""
    team = ANDREW[league]
    db.clear_cache()
    A._default = None
    t0 = time.perf_counter()
    cold = ondemand.my_week(league, team, exclude_reference=league)
    t1 = time.perf_counter()
    warm = ondemand.my_week(league, team, exclude_reference=league)
    t2 = time.perf_counter()
    print(f"\nlatency {league} roster {team}: cold {1000 * (t1 - t0):.0f} ms {cold['on_demand']['timings_ms']}; "
          f"warm {1000 * (t2 - t1):.0f} ms {warm['on_demand']['timings_ms']}")
    assert warm["lineup"] == cold["lineup"]
    assert (t2 - t1) < (t1 - t0) and (t1 - t0) < 15
