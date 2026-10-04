"""The decision probability (plan D6, Wave D): how often player A outscores player B this week.

Two overlapping ranges ("10.0, floor 4 ceiling 18" vs "9.9, floor 3 ceiling 19") do not answer the
question a lineup call asks. This module turns each player's predictive distribution (the calibrated
quantiles projection v2 writes: P10 / P25 / P50 / P75 / P90 in the league's scoring) into P(A > B).

The distribution
----------------
``Predictive`` is a **piecewise-linear quantile function** through the stored quantiles (five knots, or
three — P10 / P50 / P90 — on rows written before the 50% range existed):

* between two knots: linear in the probability level (a uniform density between them);
* below P10: linear with the slope of the first segment, never below 0 (P10 itself is floored at 0, so a
  player whose floor is 0 has his bottom tenth at 0: the weeks he barely plays);
* above P90: an exponential tail, ``P90 + s * ln(0.1 / (1 - u))`` with ``s`` chosen so the density is
  continuous at P90 (``s = 0.1 x`` the slope of the last segment). Weekly fantasy points are right-skewed
  (a 40-point week happens); a linear tail would stop at a hard maximum. The tail is fixed by the inner
  quantiles: nothing is fitted here;
* each tail's slope is floored by the average slope of its half of the distribution ((P90 - P50) / 0.4 above,
  (P50 - P10) / 0.4 below), so a row whose 50% end was clipped onto its 80% end (P75 = P90: separately fitted
  quantile models that cross, 1 of 16,268 rows of 2026 weeks 4-18) still has an upper tail. For a normal the
  floor never binds.

The pair
--------
Two players' misses are independent unless they share a game. Teammates and opponents are correlated
(a shootout lifts both offenses; a QB and his receivers rise and fall together; two backs on one team
split the work). Those pairs use a **Gaussian copula** with the correlation measured on the walk-forward
backtest (``PAIR_RHO``: normal scores of each player-week's calibrated quantile level, held-out seasons
2023-2025, both leagues' scoring; docs/METRICS.md § "Ranges and decisions"). P(A > B) is a Monte Carlo
over ``N_DRAWS`` paired draws with a fixed seed (common random numbers: the same pair always gets the
same answer, and a tie counts half — two floors of 0 tie).

``tests/test_decisions.py`` checks the quantile function, the Monte Carlo against the closed form for two
normals (independent and correlated) and the correlation lookup.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

LEVELS5 = (0.10, 0.25, 0.50, 0.75, 0.90)
LEVELS3 = (0.10, 0.50, 0.90)
N_DRAWS = 40_000
SEED = 20261001

# Words for a probability on a card (plan D6): 50-55% a coin flip, 55-65% a lean, 65%+ clear.
COIN_FLIP, LEAN = 0.55, 0.65

# Correlation of two players' outcomes (Gaussian-copula rho, normal scores of the calibrated quantile
# level) when they play in the same game, from the walk-forward backtest (held-out seasons 2023-2025,
# both leagues' scoring, played player-weeks): key (relationship, positions sorted). Pairs not listed
# (or in different games) are independent. See docs/METRICS.md § "Ranges and decisions" for the counts.
# Measured 2026-10-01 on pairs of played player-weeks where both were projected >= 5 points (the mean of the
# two leagues' scoring; every pair has >= 150 observations, most several thousand). A teammate QB pair is a
# starter and the backup who replaced him (one's lost snaps are the other's); TE-TE teammates (89-234 pairs)
# fall back on the relationship's pooled value.
PAIR_RHO: dict[tuple[str, str, str], float] = {
    ("teammates", "QB", "QB"): -0.407, ("teammates", "QB", "RB"): 0.033, ("teammates", "QB", "TE"): 0.205,
    ("teammates", "QB", "WR"): 0.223, ("teammates", "RB", "RB"): -0.084, ("teammates", "RB", "TE"): -0.007,
    ("teammates", "RB", "WR"): -0.029, ("teammates", "TE", "WR"): 0.011, ("teammates", "WR", "WR"): 0.016,
    ("opponents", "QB", "QB"): 0.112, ("opponents", "QB", "RB"): 0.010, ("opponents", "QB", "TE"): 0.043,
    ("opponents", "QB", "WR"): 0.066, ("opponents", "RB", "RB"): -0.023, ("opponents", "RB", "TE"): 0.002,
    ("opponents", "RB", "WR"): 0.010, ("opponents", "TE", "TE"): -0.012, ("opponents", "TE", "WR"): 0.023,
    ("opponents", "WR", "WR"): 0.047,
}
# fallback for a same-game pair whose position pair has no estimate: all such pairs pooled
DEFAULT_RHO = {"teammates": 0.053, "opponents": 0.031}


@dataclass(frozen=True)
class Predictive:
    """One player's predictive distribution as a quantile function (see the module docstring)."""

    levels: tuple[float, ...]
    values: tuple[float, ...]

    @classmethod
    def from_quantiles(cls, p10: float, p50: float, p90: float, p25: float | None = None, p75: float | None = None) -> Predictive:
        """From the stored quantiles; P25 / P75 may be missing (rows frozen before they existed): three knots."""
        have5 = p25 is not None and p75 is not None and not (_nan(p25) or _nan(p75))
        levels = LEVELS5 if have5 else LEVELS3
        vals = [p10, p25, p50, p75, p90] if have5 else [p10, p50, p90]
        v = np.maximum.accumulate(np.asarray(vals, dtype=float))     # monotone (stored rows already are)
        return cls(tuple(levels), tuple(float(x) for x in v))

    @classmethod
    def from_row(cls, row: Mapping) -> Predictive | None:
        """From a mapping with p10 / p50 / p90 (and optionally p25 / p75); None when the 80% range is missing."""
        p10, p50, p90 = (row.get(k) for k in ("p10", "p50", "p90"))
        if any(v is None or _nan(v) for v in (p10, p50, p90)):
            return None
        return cls.from_quantiles(float(p10), float(p50), float(p90), _num(row.get("p25")), _num(row.get("p75")))

    def ppf(self, u: np.ndarray) -> np.ndarray:
        """Quantile function at probability levels ``u`` (array in (0, 1))."""
        u = np.asarray(u, dtype=float)
        lv, vv = np.asarray(self.levels), np.asarray(self.values)
        out = np.interp(u, lv, vv)
        # the tails take the outer segment's slope, floored by the average slope of that half of the
        # distribution: a range whose 50% end was clipped onto its 80% end (P75 = P90, quantile models that
        # cross) must not get a hard ceiling. For a normal the floor never binds.
        half = int(np.searchsorted(lv, 0.5))
        slope_lo = max((vv[1] - vv[0]) / (lv[1] - lv[0]), (vv[half] - vv[0]) / (lv[half] - lv[0]))
        slope_hi = max((vv[-1] - vv[-2]) / (lv[-1] - lv[-2]), (vv[-1] - vv[half]) / (lv[-1] - lv[half]))
        # below the first knot: linear, never below 0 (or the floor itself if negative)
        lo = u < lv[0]
        out[lo] = np.maximum(vv[0] - slope_lo * (lv[0] - u[lo]), min(0.0, vv[0]))
        # above the last knot: exponential tail with a continuous density
        s = (1.0 - lv[-1]) * slope_hi
        hi = u > lv[-1]
        out[hi] = vv[-1] + s * np.log((1.0 - lv[-1]) / (1.0 - u[hi]))
        return out

    def mean(self, n: int = 20_000) -> float:
        """The distribution's mean (midpoint rule on n levels): a check against the projection."""
        u = (np.arange(n) + 0.5) / n
        return float(self.ppf(u).mean())


def _nan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return True


def _num(v) -> float | None:
    return None if v is None or _nan(v) else float(v)


def _std_normal_cdf(z: np.ndarray) -> np.ndarray:
    from scipy.special import ndtr

    return ndtr(z)


def _uniform_pairs(n: int, rho: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """n paired probability levels from a Gaussian copula with correlation ``rho`` (fixed seed)."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((2, n))
    z2 = rho * z[0] + math.sqrt(max(0.0, 1.0 - rho * rho)) * z[1]
    eps = 1e-12
    return np.clip(_std_normal_cdf(z[0]), eps, 1 - eps), np.clip(_std_normal_cdf(z2), eps, 1 - eps)


def prob_a_beats_b(a, b, rho: float = 0.0, n: int = N_DRAWS, seed: int = SEED) -> float:
    """P(A outscores B): ``a`` / ``b`` are ``Predictive`` objects or any quantile function (callable on an
    array of levels); ``rho`` the copula correlation of the pair. A tie counts half."""
    fa = a.ppf if isinstance(a, Predictive) else a
    fb = b.ppf if isinstance(b, Predictive) else b
    ua, ub = _uniform_pairs(n, rho, seed)
    xa, xb = fa(ua), fb(ub)
    return float(np.mean(xa > xb) + 0.5 * np.mean(xa == xb))


# ------------------------------------------------------------------------------ the pair
def relationship(team_a: str | None, opp_a: str | None, team_b: str | None, opp_b: str | None) -> str | None:
    """'teammates' (same NFL team this week), 'opponents' (each other's opponent), or None (different games / unknown)."""
    team_a, opp_a, team_b, opp_b = (v if isinstance(v, str) and v else None for v in (team_a, opp_a, team_b, opp_b))
    if team_a is None or team_b is None:
        return None
    if team_a == team_b:
        return "teammates"
    if (opp_a and team_b == opp_a) or (opp_b and team_a == opp_b):
        return "opponents"
    return None


def pair_rho(rel: str | None, pos_a: str | None, pos_b: str | None) -> float:
    """The copula correlation for a pair (0 when they do not share a game)."""
    if rel is None:
        return 0.0
    key = (rel, *sorted((str(pos_a), str(pos_b))))
    return PAIR_RHO.get(key, DEFAULT_RHO.get(rel, 0.0))


def win_probability(a: Mapping, b: Mapping, n: int = N_DRAWS, seed: int = SEED) -> float | None:
    """P(A outscores B) for two projection rows (p10 ... p90, team, opponent, position); None when either has
    no 80% range."""
    pa, pb = Predictive.from_row(a), Predictive.from_row(b)
    if pa is None or pb is None:
        return None
    rho = pair_rho(relationship(a.get("team"), a.get("opponent"), b.get("team"), b.get("opponent")), a.get("position"), b.get("position"))
    return prob_a_beats_b(pa, pb, rho, n, seed)


def words(p: float) -> str:
    """How close a call is, from the starter's probability of outscoring the alternative (either side of 50%)."""
    q = max(p, 1.0 - p)
    if q < COIN_FLIP:
        return "a coin flip"
    if q < LEAN:
        return "a lean"
    return "clear"


def percent(p: float) -> int:
    """Whole percent for a card; never 100 or 0 (a weekly outcome is never certain)."""
    return int(min(99, max(1, round(100 * p))))


def coverage_table(pairs: Sequence[tuple[float, float]], bins: int = 10) -> list[dict]:
    """Calibration of predicted probabilities: ``pairs`` = (predicted P(A wins), outcome 1 / 0.5 / 0); one row per
    decile of the prediction (by value: 0.5-0.55, ... as equal-count bins), with the mean predicted and the
    observed rate."""
    if not pairs:
        return []
    p = np.array([x[0] for x in pairs], dtype=float)
    o = np.array([x[1] for x in pairs], dtype=float)
    order = np.argsort(p, kind="mergesort")
    out = []
    for k, idx in enumerate(np.array_split(order, bins)):
        if len(idx) == 0:
            continue
        out.append({"bin": k + 1, "n": int(len(idx)), "p_lo": float(p[idx].min()), "p_hi": float(p[idx].max()),
                    "predicted": float(p[idx].mean()), "observed": float(o[idx].mean())})
    return out


def brier(pairs: Sequence[tuple[float, float]]) -> float:
    p = np.array([x[0] for x in pairs], dtype=float)
    o = np.array([x[1] for x in pairs], dtype=float)
    return float(np.mean((p - o) ** 2))


# ---- IH-3 (Wave I-H): the week's win probability — the game objective, as information. The decision-quality review
# § "The analytics worth building next" item 5: compare expected points with the matchup's win probability, and never
# turn "underdog" into an instruction to chase ceilings. This block describes the week; the cards decide the lineup.
#
# P(my starters outscore the opponent's) from every starter's predictive distribution (``Predictive`` through his
# P10 ... P90 in the league's scoring), one Gaussian copula over BOTH lineups: every pair that shares a game gets
# ``pair_rho`` (teammates / opponents, QB-TE as measured in D6, on either side of the matchup — my QB and his WR who
# catches passes from him move together); every other pair is independent. Paired draws with the fixed seed, a tie
# counts half. A starter whose game is in (``actual`` not None) is a point mass at his actual points. What is ignored
# (and said in ``WEEK_ASSUMPTIONS``): pairs in different games (weather and league-wide scoring trends tie them a
# little), a kicker / defense / team unit's correlation with anyone (not measured: independent), and a starter who
# does not play at all (the ranges are "if he plays": an inactive starter scores 0, which the distribution does not
# carry — the morning's statuses already sit him when he is ruled out).
WEEK_ASSUMPTIONS = "assuming the players' weeks are independent except teammates and opponents"
# The calibration (docs/METRICS.md § "Win probability" → "The week"; 2024-2025 house-league matchups, the managers' real
# starters, walk-forward ranges): the raw probability is overconfident (the favourite predicted 62.9%, won 57.8%; "clear"
# 73.2% vs 62.3%) — the ranges are "if he plays" and the weeks of different games are not independent. A logit shrink
# ``p = sigmoid(WEEK_SHRINK * logit(p_raw))`` fitted on one season improves the other (Brier 2025 0.2452 -> 0.2412 with
# 2024's 0.64; 2024 0.2405 -> 0.2379 with 2025's 0.54) and 2026 weeks 1-2 (0.2454 -> 0.2402); the pooled fit is used.
WEEK_SHRINK = 0.59
KD_POSITIONS = frozenset({"K", "DEF", "TMPK", "TMDEF"})
UNIT_AS = {"TMQB": "QB"}          # an MFL team quarterback correlates like his starter


def _week_dist(r: Mapping) -> tuple[str, Predictive | float]:
    """('played', actual) | ('range', Predictive) | ('point', value): one starter's week. A K / DEF row with only P10 /
    P90 (kd1.0 ranges, the MFL kicker unit) takes its projection, clipped into the range, as the median."""
    act = _num(r.get("actual"))
    if act is not None:
        return "played", act
    d = Predictive.from_row(r)
    if d is None:
        p10, p90, v = _num(r.get("p10")), _num(r.get("p90")), _num(r.get("value"))
        if p10 is not None and p90 is not None and v is not None and p90 >= p10:
            d = Predictive.from_quantiles(p10, min(max(v, p10), p90), p90)
    if d is not None:
        return "range", d
    v = _num(r.get("value"))
    return "point", 0.0 if v is None else v


def _nearest_corr(c: np.ndarray) -> np.ndarray:
    """A correlation matrix made positive semi-definite (eigenvalues floored at 0, the diagonal rescaled to 1): pairwise
    estimates measured separately need not be jointly consistent (two QBs of one team with the same receiver)."""
    w, v = np.linalg.eigh(c)
    if w.min() >= 1e-10:
        return c
    a = (v * np.maximum(w, 1e-10)) @ v.T
    d = np.sqrt(np.diag(a))
    return a / np.outer(d, d)


def lineup_win_probability(mine: Sequence[Mapping], theirs: Sequence[Mapping], *, n: int = N_DRAWS,
                           seed: int = SEED) -> dict:
    """P(``mine`` outscores ``theirs``) this week. Each starter is a mapping: ``key`` (who: a gsis id; the same key on
    both sides is the same player, one draw), ``position``, ``team``, ``opponent``, ``p10`` ... ``p90``, ``value`` (his
    projection: the expected total, and his whole week when he has no range) and ``actual`` (his points when his game
    is in; None before). Empty slots carry nothing (leave them out, or value 0).

    Returns ``p`` (calibrated: ``shrink_week`` of the Monte Carlo ``p_raw``; None when neither side has a single range),
    ``mine`` / ``theirs`` (the expected totals: projections,
    actual points where the game is in — the numbers the page shows), ``sim_mine`` / ``sim_theirs`` (the
    distributions' means, a check), ``n_played`` / ``n_starters`` / ``opp_n_played`` / ``opp_n_starters``,
    ``n_no_range`` / ``opp_n_no_range`` (starters counted at their projection: no range) and the pairs correlated."""
    sides = [list(mine), list(theirs)]
    cols: dict[str, int] = {}
    dists: list[Predictive] = []
    meta: list[Mapping] = []
    fixed = [0.0, 0.0]
    expected = [0.0, 0.0]
    plays = [[], []]                     # per side: (column, ) for each ranged starter
    counts = [{"n": 0, "played": 0, "no_range": 0}, {"n": 0, "played": 0, "no_range": 0}]
    for s, rows in enumerate(sides):
        for i, r in enumerate(rows):
            kind, d = _week_dist(r)
            counts[s]["n"] += 1
            if kind == "played":
                counts[s]["played"] += 1
                fixed[s] += float(d)
                expected[s] += float(d)
                continue
            v = _num(r.get("value"))
            expected[s] += 0.0 if v is None else v
            if kind == "point":
                counts[s]["no_range"] += 1
                fixed[s] += float(d)
                continue
            key = r.get("key")
            key = f"_{s}_{i}" if not isinstance(key, str) or not key else key
            if key not in cols:
                cols[key] = len(dists)
                dists.append(d)
                meta.append(r)
            plays[s].append(cols[key])
    m = len(dists)
    out = {"mine": round(expected[0], 2), "theirs": round(expected[1], 2),
           "n_starters": counts[0]["n"], "n_played": counts[0]["played"], "n_no_range": counts[0]["no_range"],
           "opp_n_starters": counts[1]["n"], "opp_n_played": counts[1]["played"], "opp_n_no_range": counts[1]["no_range"],
           "n_correlated_pairs": 0, "p": None, "p_raw": None, "sim_mine": None, "sim_theirs": None}
    if m == 0:
        if counts[0]["n"] and counts[1]["n"] and counts[0]["played"] == counts[0]["n"] and counts[1]["played"] == counts[1]["n"]:
            out["p"] = out["p_raw"] = 1.0 if fixed[0] > fixed[1] else 0.0 if fixed[0] < fixed[1] else 0.5   # the week is over
        return out
    corr = np.eye(m)
    npairs = 0
    for a in range(m):
        ra = meta[a]
        pa = UNIT_AS.get(str(ra.get("position")), ra.get("position"))
        if pa in KD_POSITIONS:
            continue
        for b in range(a + 1, m):
            rb = meta[b]
            pb = UNIT_AS.get(str(rb.get("position")), rb.get("position"))
            if pb in KD_POSITIONS:
                continue
            rel = relationship(ra.get("team"), ra.get("opponent"), rb.get("team"), rb.get("opponent"))
            rho = pair_rho(rel, pa, pb)
            if rho:
                corr[a, b] = corr[b, a] = rho
                npairs += 1
    out["n_correlated_pairs"] = npairs
    corr = _nearest_corr(corr)
    w, v = np.linalg.eigh(corr)
    root = v * np.sqrt(np.maximum(w, 0.0))
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, m)) @ root.T
    u = np.clip(_std_normal_cdf(z), 1e-12, 1 - 1e-12)
    x = np.column_stack([dists[j].ppf(u[:, j]) for j in range(m)])
    tot = [fixed[s] + (x[:, plays[s]].sum(axis=1) if plays[s] else np.zeros(n)) for s in (0, 1)]
    raw = float(np.mean(tot[0] > tot[1]) + 0.5 * np.mean(tot[0] == tot[1]))
    out["p_raw"], out["p"] = raw, shrink_week(raw)
    out["sim_mine"], out["sim_theirs"] = round(float(tot[0].mean()), 2), round(float(tot[1].mean()), 2)
    return out


def shrink_week(p: float, k: float = WEEK_SHRINK) -> float:
    """The calibrated week probability from the raw Monte Carlo one (a logit shrink toward 50%; 0 and 1 stay)."""
    if p <= 0.0 or p >= 1.0:
        return float(p)
    return float(1.0 / (1.0 + math.exp(-k * math.log(p / (1.0 - p)))))


def week_words(p: float) -> str:
    """The week in words, on ``words``' scale read from my side: 50-55% either way a coin flip, 55-65% slight, 65%+
    clear; favorite above 50%, underdog below."""
    w = words(p)
    if w == "a coin flip":
        return w
    side = "favorite" if p > 0.5 else "underdog"
    return f"a slight {side}" if w == "a lean" else f"a clear {side}"
# ---- end IH-3
