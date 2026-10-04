"""IH-3 (Wave I-H): the week's win probability, ``decisions.lineup_win_probability`` (no database needed)."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import norm

from league_lab import decisions as D


def _p(key, pos, team, opp, p50, spread=6.0, **kw):
    """A starter whose range is a normal's quantiles around ``p50`` (sd ``spread``), projected at ``p50``."""
    z10, z25 = norm.ppf(0.10), norm.ppf(0.25)
    return {"key": key, "position": pos, "team": team, "opponent": opp, "value": p50,
            "p10": p50 + z10 * spread, "p25": p50 + z25 * spread, "p50": p50, "p75": p50 - z25 * spread,
            "p90": p50 - z10 * spread, **kw}


def _lineup(prefix, shift=0.0, teams=None):
    teams = teams or ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"]
    pos = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "RB", "WR"]
    base = [20.0, 13.0, 11.0, 14.0, 12.0, 10.0, 9.0, 8.0, 8.0]
    return [_p(f"{prefix}{i}", p, t, f"X{t}", b + shift) for i, (p, t, b) in enumerate(zip(pos, teams, base, strict=True))]


def test_identical_lineups_are_a_coin_flip():
    a = _lineup("a")
    # the same players on both sides: the same draws, every week a tie -> exactly 50%
    assert D.lineup_win_probability(a, a)["p"] == pytest.approx(0.5)
    # the same distributions, different players (independent, different games): 50% up to Monte Carlo noise
    r = D.lineup_win_probability(a, _lineup("b", teams=[f"U{i}" for i in range(9)]))
    assert r["p"] == pytest.approx(0.5, abs=0.01)
    assert r["mine"] == pytest.approx(r["theirs"])
    assert D.week_words(r["p"]) == "a coin flip"


def test_every_starter_higher_is_a_favorite():
    mine, theirs = _lineup("a", shift=1.0), _lineup("b", teams=[f"U{i}" for i in range(9)])
    r = D.lineup_win_probability(mine, theirs)
    assert r["p"] > 0.5
    assert r["mine"] == pytest.approx(r["theirs"] + 9.0)
    # the closed form for two sums of independent normals (the piecewise-linear normal is close: within 0.02)
    sd = np.sqrt(2 * 9 * 36.0)
    assert r["p_raw"] == pytest.approx(norm.cdf(9.0 / sd), abs=0.02)
    assert r["p"] == pytest.approx(D.shrink_week(r["p_raw"])) and 0.5 < r["p"] < r["p_raw"]
    assert D.lineup_win_probability(theirs, mine)["p"] == pytest.approx(1 - r["p"], abs=0.01)
    assert D.week_words(r["p"]).endswith("favorite")
    assert D.week_words(1 - r["p"]).endswith("underdog")
    # each range is centred on its projection: the simulated totals are the expected totals the page prints
    assert r["sim_mine"] == pytest.approx(r["mine"], abs=0.3)
    # as stored, the ranges' means sit a little above the projections (the floor at 0, the exponential upper tail)
    raw = D.lineup_win_probability(mine, theirs, centre=False)
    assert 0 < raw["sim_mine"] - raw["mine"] < 1.5


def test_teammates_correlation_moves_the_spread():
    """A favourite's probability falls when his own starters move together (QB-WR teammates, rho +0.22: a wider total)
    and rises when the correlated pair sits across the matchup (my WRs catch passes from THEIR QB: the difference is
    narrower). Teammate backs (rho -0.08) narrow one side's total. Four starters a side, 400,000 draws (the effect is
    a point or two; the default 40,000 draws' noise is a quarter point)."""
    n = 400_000

    def four(prefix, shift, teams, pos=("QB", "WR", "WR", "WR")):
        return [_p(f"{prefix}{i}", p, t, f"X{t}", b + shift)
                for i, (p, t, b) in enumerate(zip(pos, teams, (20.0, 14.0, 12.0, 10.0), strict=True))]

    theirs = four("b", 0.0, ["U0", "U1", "U2", "U3"])
    base = D.lineup_win_probability(four("a", 1.5, ["T0", "T1", "T2", "T3"]), theirs, n=n)
    assert base["n_correlated_pairs"] == 0
    stacked = D.lineup_win_probability(four("a", 1.5, ["T0", "T0", "T0", "T0"]), theirs, n=n)
    assert stacked["n_correlated_pairs"] == 3 + 3                # QB-WR x3 and WR-WR x3
    assert stacked["p"] < base["p"] - 0.005
    hedged = D.lineup_win_probability(four("a", 1.5, ["T0", "U0", "U0", "U0"]), theirs, n=n)
    assert hedged["n_correlated_pairs"] == 3 + 3                 # my WRs x their QB, and with each other
    assert hedged["p"] > base["p"] + 0.005
    rbs = ("RB", "RB", "RB", "RB")
    base_rb = D.lineup_win_probability(four("a", 1.5, ["T0", "T1", "T2", "T3"], rbs), four("b", 0.0, ["U0", "U1", "U2", "U3"], rbs), n=n)
    split = D.lineup_win_probability(four("a", 1.5, ["T0", "T0", "T2", "T2"], rbs), four("b", 0.0, ["U0", "U1", "U2", "U3"], rbs), n=n)
    assert split["p"] > base_rb["p"]


def test_played_games_use_the_actual_points():
    mine, theirs = _lineup("a"), _lineup("b", teams=[f"U{i}" for i in range(9)])
    mine[0] = {**mine[0], "actual": 35.0}                       # his game is in: 35, not his 20 projected
    theirs[0] = {**theirs[0], "actual": 4.0}
    r = D.lineup_win_probability(mine, theirs)
    assert (r["n_played"], r["n_starters"], r["opp_n_played"], r["opp_n_starters"]) == (1, 9, 1, 9)
    assert r["mine"] == pytest.approx(sum(x["value"] for x in mine[1:]) + 35.0)
    assert r["theirs"] == pytest.approx(sum(x["value"] for x in theirs[1:]) + 4.0)
    sd = np.sqrt(2 * 8 * 36.0)
    assert r["p_raw"] == pytest.approx(norm.cdf(31.0 / sd), abs=0.02)
    # a week that is over: certain
    done_m = [{**x, "actual": 10.0} for x in mine]
    done_t = [{**x, "actual": 9.0} for x in theirs]
    assert D.lineup_win_probability(done_m, done_t)["p"] == 1.0
    assert D.lineup_win_probability(done_t, done_m)["p"] == 0.0


def test_no_range_counts_the_projection_and_kickers_take_their_projection_as_median():
    mine, theirs = _lineup("a"), _lineup("b", teams=[f"U{i}" for i in range(9)])
    k = {"key": "k1", "position": "K", "team": "T1", "opponent": "XT1", "value": 8.0, "p10": 3.0, "p90": 14.0}
    dst = {"key": "d1", "position": "DEF", "team": "U1", "opponent": "T1", "value": 7.0}       # no range at all
    r = D.lineup_win_probability([*mine, k], [*theirs, dst])
    assert r["n_no_range"] == 0 and r["opp_n_no_range"] == 1
    assert r["mine"] == pytest.approx(sum(x["value"] for x in mine) + 8.0)
    assert r["theirs"] == pytest.approx(sum(x["value"] for x in theirs) + 7.0)
    assert 0.5 < r["p"] < 0.6
    # a kicker shares a game with my QB but is independent (not measured)
    assert r["n_correlated_pairs"] == 0
    # nothing to draw (no ranges anywhere, nothing played): no probability
    assert D.lineup_win_probability([dst], [dst])["p"] is None


def test_the_shrink_is_symmetric_and_keeps_certainty():
    for p in (0.1, 0.3, 0.5, 0.62, 0.9):
        assert D.shrink_week(p) == pytest.approx(1 - D.shrink_week(1 - p))
        assert abs(D.shrink_week(p) - 0.5) <= abs(p - 0.5)
    assert (D.shrink_week(0.0), D.shrink_week(1.0), D.shrink_week(0.5)) == (0.0, 1.0, 0.5)


def test_inconsistent_correlations_are_repaired_and_fixed_seed():
    # two QBs of one team (-0.41) with the same receivers (+0.22 each): not jointly consistent for large rho; must run
    team = [_p(f"q{i}", "QB", "T1", "T2", 18.0) for i in range(2)] + [_p(f"w{i}", "WR", "T1", "T2", 12.0) for i in range(6)]
    other = _lineup("b", teams=[f"U{i}" for i in range(9)])
    r1 = D.lineup_win_probability(team, other)
    r2 = D.lineup_win_probability(team, other)
    assert 0.0 < r1["p"] < 1.0 and r1["p"] == r2["p"]
    c = np.array([[1.0, 0.9, 0.9], [0.9, 1.0, -0.9], [0.9, -0.9, 1.0]])
    f = D._nearest_corr(c)
    assert np.allclose(np.diag(f), 1.0) and np.linalg.eigvalsh(f).min() > -1e-9
