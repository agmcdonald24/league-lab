"""Plan D6: the decision probability (league_lab.decisions) and the 50% range columns (no database needed)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import norm

from league_lab import db, projections
from league_lab import decisions as D

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------------------ the quantile function
def test_quantile_function_passes_through_the_five_quantiles():
    p = D.Predictive.from_quantiles(4.0, 11.0, 21.0, p25=7.5, p75=15.0)
    assert p.levels == D.LEVELS5
    np.testing.assert_allclose(p.ppf(np.array(D.LEVELS5)), [4.0, 7.5, 11.0, 15.0, 21.0])
    # linear between knots: halfway in level = halfway in points
    np.testing.assert_allclose(p.ppf(np.array([0.375, 0.825])), [(7.5 + 11.0) / 2, (15.0 + 21.0) / 2])


def test_quantile_function_tails():
    p = D.Predictive.from_quantiles(4.0, 11.0, 21.0, p25=7.5, p75=15.0)
    u = np.linspace(0.0005, 0.9995, 4001)
    x = p.ppf(u)
    assert (np.diff(x) >= -1e-12).all()                      # monotone
    assert x.min() >= 0.0                                    # never below 0
    # lower tail: the first segment's slope (3.5 points per 0.15) down to 0
    np.testing.assert_allclose(p.ppf(np.array([0.05])), [4.0 - 3.5 / 0.15 * 0.05])
    # upper tail: exponential with the density continuous at P90 (slope 6 points per 0.15 = 40 per unit level)
    h = 1e-6
    left = (p.ppf(np.array([0.9])) - p.ppf(np.array([0.9 - h]))) / h
    right = (p.ppf(np.array([0.9 + h])) - p.ppf(np.array([0.9]))) / h
    np.testing.assert_allclose(left, right, rtol=1e-3)
    s = 0.1 * 6.0 / 0.15
    np.testing.assert_allclose(p.ppf(np.array([0.99])), [21.0 + s * math.log(10)])
    # a floor of 0: the bottom tenth is 0 (a player who barely plays)
    z = D.Predictive.from_quantiles(0.0, 3.0, 12.0, p25=1.0, p75=6.0)
    assert (z.ppf(np.array([0.01, 0.05, 0.099])) == 0.0).all()


def test_a_clipped_range_still_has_an_upper_tail():
    # P75 clipped onto P90 (George Kittle, 2026 week 4): the last segment is flat, the tail takes the upper
    # half's average slope (P90 - P50) / 0.4 instead of stopping at a hard maximum
    k = D.Predictive.from_quantiles(2.24, 9.24, 14.4, p25=5.04, p75=14.4)
    s = 0.1 * (14.4 - 9.24) / 0.4
    np.testing.assert_allclose(k.ppf(np.array([0.99])), [14.4 + s * math.log(10)])
    assert (k.ppf(np.array([0.95, 0.99])) > 14.4).all()
    # and the floor never binds for a normal: the outer segments are the steepest
    lv = np.array(D.LEVELS5)
    n = D.Predictive.from_quantiles(*norm.ppf([0.1, 0.5, 0.9], 10, 4), p25=norm.ppf(0.25, 10, 4), p75=norm.ppf(0.75, 10, 4))
    v = np.array(n.values)
    assert (v[-1] - v[-2]) / 0.15 > (v[-1] - v[2]) / 0.4 and (v[1] - v[0]) / 0.15 > (v[2] - v[0]) / 0.4
    assert lv[2] == 0.5


def test_three_knots_when_the_50_range_is_missing():
    for p25, p75 in ((None, None), (float("nan"), float("nan")), (5.0, None)):
        p = D.Predictive.from_quantiles(2.0, 9.0, 20.0, p25=p25, p75=p75)
        assert p.levels == D.LEVELS3 and p.values == (2.0, 9.0, 20.0)
    row = {"p10": 2.0, "p50": 9.0, "p90": 20.0, "p25": None, "p75": None}
    assert D.Predictive.from_row(row).levels == D.LEVELS3
    assert D.Predictive.from_row({"p10": None, "p50": 9.0, "p90": 20.0}) is None
    assert D.Predictive.from_row({"p10": float("nan"), "p50": 9.0, "p90": 20.0}) is None


def test_unsorted_quantiles_are_made_monotone():
    p = D.Predictive.from_quantiles(5.0, 9.0, 20.0, p25=4.0, p75=8.0)   # p25 < p10, p75 < p50
    assert list(p.values) == sorted(p.values)


# ------------------------------------------------------------------------------ Monte Carlo vs closed form
@pytest.mark.parametrize("rho", [0.0, 0.35, -0.3])
def test_monte_carlo_matches_the_closed_form_for_two_normals(rho):
    ma, sa, mb, sb = 12.0, 5.0, 10.5, 6.0
    exact = norm.cdf((ma - mb) / math.sqrt(sa ** 2 + sb ** 2 - 2 * rho * sa * sb))
    got = D.prob_a_beats_b(lambda u: norm.ppf(u, ma, sa), lambda u: norm.ppf(u, mb, sb), rho=rho)
    assert abs(got - exact) < 0.01           # 40k draws: standard error ~0.0025
    # the piecewise-linear function through the normals' five quantiles is close to the exact answer too
    qa = D.Predictive.from_quantiles(*norm.ppf([0.1, 0.5, 0.9], ma, sa), p25=norm.ppf(0.25, ma, sa), p75=norm.ppf(0.75, ma, sa))
    qb = D.Predictive.from_quantiles(*norm.ppf([0.1, 0.5, 0.9], mb, sb), p25=norm.ppf(0.25, mb, sb), p75=norm.ppf(0.75, mb, sb))
    assert abs(D.prob_a_beats_b(qa, qb, rho=rho) - exact) < 0.02


def test_monte_carlo_is_deterministic_and_symmetric():
    a = D.Predictive.from_quantiles(4.0, 11.0, 21.0, p25=7.5, p75=15.0)
    b = D.Predictive.from_quantiles(3.0, 10.0, 22.0, p25=6.0, p75=14.5)
    p1, p2 = D.prob_a_beats_b(a, b), D.prob_a_beats_b(a, b)
    assert p1 == p2
    assert abs(D.prob_a_beats_b(a, b) + D.prob_a_beats_b(b, a) - 1.0) < 0.01
    assert D.prob_a_beats_b(a, a) == pytest.approx(0.5, abs=0.01)
    # two floors of 0: ties count half, so the same distribution is exactly a coin flip
    z = D.Predictive.from_quantiles(0.0, 2.0, 9.0, p25=0.5, p75=4.0)
    assert D.prob_a_beats_b(z, z, rho=1.0) == pytest.approx(0.5)


def test_correlation_moves_the_probability_the_right_way():
    a = D.Predictive.from_quantiles(6.0, 12.0, 20.0, p25=9.0, p75=15.5)
    b = D.Predictive.from_quantiles(5.0, 10.0, 19.0, p25=7.5, p75=13.5)
    p_ind, p_pos, p_neg = (D.prob_a_beats_b(a, b, rho=r) for r in (0.0, 0.5, -0.5))
    assert p_neg < p_ind < p_pos          # moving together makes the better projection win more often


# ------------------------------------------------------------------------------ the pair
def test_relationship_and_correlation_lookup(monkeypatch):
    assert D.relationship("KC", "BUF", "KC", "BUF") == "teammates"
    assert D.relationship("KC", "BUF", "BUF", "KC") == "opponents"
    assert D.relationship("KC", "BUF", "DAL", "NYG") is None
    assert D.relationship(None, "BUF", "KC", "BUF") is None
    assert D.relationship(float("nan"), None, "KC", "BUF") is None
    monkeypatch.setattr(D, "PAIR_RHO", {("teammates", "RB", "WR"): -0.1, ("opponents", "WR", "WR"): 0.05})
    monkeypatch.setattr(D, "DEFAULT_RHO", {"teammates": 0.02, "opponents": 0.03})
    assert D.pair_rho("teammates", "WR", "RB") == D.pair_rho("teammates", "RB", "WR") == -0.1   # order does not matter
    assert D.pair_rho("opponents", "WR", "WR") == 0.05
    assert D.pair_rho("teammates", "QB", "TE") == 0.02            # no estimate for the pair: the relationship's default
    assert D.pair_rho(None, "WR", "WR") == 0.0                    # different games: independent


def test_win_probability_uses_the_pair_correlation(monkeypatch):
    monkeypatch.setattr(D, "PAIR_RHO", {("teammates", "RB", "RB"): -0.5})
    a = {"p10": 5.0, "p25": 8.0, "p50": 11.0, "p75": 14.0, "p90": 19.0, "team": "DET", "opponent": "GB", "position": "RB"}
    b = {"p10": 4.0, "p25": 7.0, "p50": 10.0, "p75": 13.0, "p90": 18.0, "team": "DET", "opponent": "GB", "position": "RB"}
    other = dict(b, team="SEA", opponent="ARI")
    p_team = D.win_probability(a, b)
    p_ind = D.win_probability(a, other)
    assert p_team < p_ind
    assert p_ind == pytest.approx(D.prob_a_beats_b(D.Predictive.from_row(a), D.Predictive.from_row(other)))
    assert D.win_probability(a, dict(b, p10=None)) is None


def test_words_and_percent():
    assert D.words(0.52) == "a coin flip" and D.words(0.48) == "a coin flip"
    assert D.words(0.55) == "a lean" and D.words(0.64) == "a lean" and D.words(0.36) == "a lean"
    assert D.words(0.65) == "clear" and D.words(0.9) == "clear"
    assert D.percent(0.999) == 99 and D.percent(0.001) == 1 and D.percent(0.544) == 54


def test_calibration_helpers():
    pairs = [(0.55, 1.0), (0.55, 0.0), (0.9, 1.0), (0.9, 1.0)]
    assert D.brier(pairs) == pytest.approx(((0.45 ** 2) + (0.55 ** 2) + 2 * 0.01) / 4)
    tab = D.coverage_table(pairs, bins=2)
    assert [r["n"] for r in tab] == [2, 2]
    assert tab[0]["predicted"] == pytest.approx(0.55) and tab[0]["observed"] == pytest.approx(0.5)
    assert tab[1]["observed"] == pytest.approx(1.0)


# ------------------------------------------------------------------------------ the 50% range columns (B5 way)
def test_p25_p75_are_added_in_every_copy_of_the_projections_ddl():
    mart = (ROOT / "dbt/models/marts/nfl/mart_player_week_projections.sql").read_text()
    for text in (db.OPS_DDL, projections.DDL["ops.projections"], mart):
        for col in ("p25", "p75"):
            assert f"alter table ops.projections add column if not exists {col} double precision" in text
    assert "round(p.p25::numeric, 2) as p25" in mart and "round(k.p25::numeric, 2) as p25" in mart


# ------------------------------------------------------------------------------ per-tier conformal (D6 follow-up)
def test_conformal_widening_is_the_split_conformal_quantile():
    rng = np.random.default_rng(0)
    y = rng.normal(0, 1, 400)
    lo, hi = np.full(400, -1.0), np.full(400, 1.0)
    miss = np.maximum(lo - y, y - hi)
    expected = np.quantile(miss, np.ceil(401 * 0.8) / 400)
    assert projections._conformal_widening(lo, hi, y, 0.8) == pytest.approx(expected)
    assert projections._conformal_widening(lo[:49], hi[:49], y[:49], 0.8) == 0.0    # too few rows: no widening
    # widened by it, the calibration rows hold at least 80%
    w = projections._conformal_widening(lo, hi, y, 0.8)
    assert ((y >= lo - w) & (y <= hi + w)).mean() >= 0.8


def test_widening_follows_the_projection_tier():
    m = projections.PositionModel("WR")
    m.conformal, m.conformal_50 = {"L": 0.5}, {"L": 0.2}
    lines = np.array([2.0, 7.9, 8.0, 12.0, 30.0])
    assert projections._widening(m, "L", lines, "80") == 0.5          # no tiers on the model: position-wide
    m.tier_cuts["L"] = (5.0, 10.0)
    m.conformal_tiers["L"], m.conformal_50_tiers["L"] = (-0.3, 0.4, 1.1), (-0.1, 0.1, 0.6)
    np.testing.assert_allclose(projections._widening(m, "L", lines, "80"), [-0.3, 0.4, 0.4, 1.1, 1.1])
    np.testing.assert_allclose(projections._widening(m, "L", lines, "50"), [-0.1, 0.1, 0.1, 0.6, 0.6])
    assert projections.TIER_QUANTILES == (1 / 3, 2 / 3) and projections.TIER_MIN_ROWS == 200
