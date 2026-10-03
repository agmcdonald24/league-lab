"""Expected-value pricing of a projected line (plan Iteration 17 C, Wave I-C M2): the numbers it needs.

The problem
-----------
A projected stat line is a set of *means*. Linear rules (points per yard, per catch, per TD) price a mean exactly:
E[0.1 x yards] = 0.1 x E[yards]. A flat bonus does not: "+10 at 100 rushing yards" priced on a projected 85-yard line
pays nothing (all or nothing), yet that back crosses 100 in about one game in three. Its expected value is
10 x P(rushing yards >= 100 | projected 85). A touchdown paid by distance (6 / 9 / 12 for 0-9 / 10-39 / 40+ yards)
has the same issue in another form: the line projects TDs, not their lengths, so a TD is worth
6 x P(0-9) + 9 x P(10-39) + 12 x P(40+) in expectation. This module holds the two distributions that turn those rules
into expected points, fitted offline and kept as constants, so the server never fits anything:

* ``prob_at_least(stat, position, mean, threshold)`` -- P(stat >= threshold in a game | the projection's mean), for
  passing / rushing / receiving yards and receptions. Two families, both monotone in the mean by construction:
  - **gamma** (rushing / receiving yards, receptions): ``m' = mean_scale x mean``, shape ``k = k0 + k1 x m'``, scale
    ``theta = m' / k``; ``P(X >= t) = Q(k, (t - 0.5) / theta)`` (``scipy.special.gammaincc``; 0.5 is the continuity
    correction of an integer stat). Shape and scale both rise with the mean (k0, k1 >= 0), and a gamma is
    stochastically increasing in both, so P never falls as the projection rises. A big projection is relatively
    less noisy (CV about 1 / sqrt(k1 x m')).
  - **normal** (passing yards): ``mu = mean_scale x mean``, ``sd = sd0 + sd1 x mu``, ``P = Phi((mu - t + 0.5) / sd)``;
    its derivative in the mean is proportional to ``sd0 + sd1 x t`` > 0. A quarterback's yards are closer to symmetric:
    out of sample (fitted 2019-2022, scored 2023-2025) the normal's log loss is 2.004 against the gamma's 2.059 and it
    prices a 400-yard game at 1.7% (observed 0.9%) where the gamma says 3.4%.
  Fitted per position x stat on the out-of-sample rows of ``calibration.oof_rows(lines=True)`` (the production model,
  walk-forward) by minimising the log loss of 1{actual >= t} over the thresholds leagues use (``FIT_THRESHOLDS``):
  the curve is fitted to exactly what it prices. It replaces M1's isotonic curves (``calibration.fit_bonus_curves``),
  which exist only at fixed thresholds and need the fitting rows at run time; out of sample it matches or beats them
  (docs/METRICS.md).
* ``td_distance_share(family, position, low, high)`` -- the expected share of a family's TDs whose distance is in
  [low, high] yards, measured on ``analytics.fct_play`` (every TD play, regular seasons 2019-2025; distance =
  ``yards_gained`` of the scoring play for offense, the same definition dbt uses for ``*_tds_40p``; the return yards
  parsed from the play description for return and defensive TDs). Survival shares at ``TD_KNOTS`` yards,
  log-linear between knots. A position with few TDs is shrunk to its family's pooled share (``SHRINK_TDS``).
* ``expected_floor_units(stat, position, mean, per)`` -- MFL's "1 point per whole 10 yards" in expectation, from the
  same curves (a linear price is high by the expected remainder, 0.3-0.5 points per yardage stat per game).

Offline (``run_fit()``) refits both from the database and prints the constants block below; ``seed_rows()`` writes
``dbt/seeds/scoring_distributions.csv`` from the constants (a test pins the two equal). Methods and the backtest:
docs/METRICS.md § "Expected-value pricing".
"""

from __future__ import annotations

import csv
import logging
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import numpy as np
from scipy.special import gammaincc, ndtr

log = logging.getLogger(__name__)

VERSION = "ev1.0"
FIT_SEASONS = "2019-2025"
CURVE_STATS = ("passing_yards", "rushing_yards", "receiving_yards", "receptions")
OFFENSE_TD_FAMILIES = ("passing_tds", "rushing_tds", "receiving_tds")
TD_FAMILIES = (*OFFENSE_TD_FAMILIES, "kick_return_tds", "punt_return_tds", "int_return_tds", "fumble_return_tds",
               "blocked_kick_tds", "missed_fg_return_tds")
# pooled families (IC-1's spec names): return_tds = kick + punt returns; def_tds = interception, fumble and kick returns
# by the defense (blocked and missed); fg_made = made field goals by distance (fct_player_game's buckets)
POOLED_FAMILIES = {"return_tds": ("kick_return_tds", "punt_return_tds"),
                   "def_tds": ("int_return_tds", "fumble_return_tds", "blocked_kick_tds", "missed_fg_return_tds")}
DISTANCE_FAMILIES = (*TD_FAMILIES, *POOLED_FAMILIES, "fg_made")
POSITIONS = ("QB", "RB", "WR", "TE")
POSITION_ALIASES = {"TMQB": "QB", "TMPK": "K", "PK": "K", "TMDEF": "DEF", "Def": "DEF", "D/ST": "DEF", "DST": "DEF"}
TD_KNOTS = (5, 10, 20, 30, 40, 50, 60, 70, 80)   # survival share S(d) = P(distance >= d) is stored at these yards
TD_MAX_DISTANCE = 110                              # S(d) = 0 beyond (a return from deep in the end zone)
SHRINK_TDS = 30                                    # a position's share = (n x own + 30 x pooled) / (n + 30)
MIN_CURVE_ROWS = 1500                              # fewer fitting rows for a position x stat: the pooled (ALL) curve
GAMMA, NORMAL = 0, 1                               # the curve's family (the seed's ``family`` value)
CURVE_FAMILY = {"passing_yards": NORMAL}           # every other stat: GAMMA
FIT_THRESHOLDS: dict[str, tuple[int, ...]] = {
    "passing_yards": (150, 200, 250, 300, 350, 400),
    "rushing_yards": (25, 50, 75, 100, 125, 150, 200),
    "receiving_yards": (25, 50, 75, 100, 125, 150, 200),
    "receptions": (2, 3, 4, 5, 6, 7, 8, 10, 12),
}
# MFL's TD event codes -> the family here (scoring.py's MFL compiler names the same events)
MFL_TD_FAMILY = {"PS": "passing_tds", "RS": "rushing_tds", "RC": "receiving_tds", "KO": "kick_return_tds",
                 "PR": "punt_return_tds", "IR": "int_return_tds", "DR": "fumble_return_tds", "BF": "blocked_kick_tds",
                 "BP": "blocked_kick_tds", "MF": "missed_fg_return_tds", "FG": "fg_made"}
FG_BUCKETS = (("fg_made_0_19", 0), ("fg_made_20_29", 20), ("fg_made_30_39", 30), ("fg_made_40_49", 40),
              ("fg_made_50_59", 50), ("fg_made_60_", 60))   # fct_player_game's made-FG columns and their low edge

# ---------------------------------------------------------------------------------------------- fitted constants
# Generated by run_fit() on league_lab_m1 (2026-10-03). (stat, position) -> (family, mean_scale, p1, p2, rows):
# gamma p1, p2 = k0, k1; normal p1, p2 = sd0, sd1.
# BEGIN GENERATED CURVES
CURVES: dict[tuple[str, str], tuple[int, float, float, float, int]] = {
    ('passing_yards', 'ALL'): (1, 0.978797, 79.211, 0.000335463, 4565),
    ('passing_yards', 'QB'): (1, 0.978797, 79.211, 0.000335463, 4565),
    ('receiving_yards', 'ALL'): (0, 0.986952, 0.115957, 0.0415497, 35038),
    ('receiving_yards', 'RB'): (0, 0.969973, 0.000335463, 0.057332, 10582),
    ('receiving_yards', 'TE'): (0, 0.995078, 0.156821, 0.0484634, 8240),
    ('receiving_yards', 'WR'): (0, 0.989471, 0.0102637, 0.0409699, 16216),
    ('receptions', 'ALL'): (0, 1.01792, 0.187982, 0.690018, 33923),
    ('receptions', 'RB'): (0, 1.02605, 0.14719, 0.689118, 9920),
    ('receptions', 'TE'): (0, 1.03986, 0.401146, 0.629579, 8083),
    ('receptions', 'WR'): (0, 1.00846, 0.161527, 0.703054, 15920),
    ('rushing_yards', 'ALL'): (0, 1.00626, 0.0144127, 0.0443445, 24015),
    ('rushing_yards', 'QB'): (0, 0.951979, 0.000335463, 0.0568779, 4432),
    ('rushing_yards', 'RB'): (0, 1.01733, 0.000335463, 0.0421755, 10459),
    ('rushing_yards', 'WR'): (0, 0.893221, 0.000335463, 0.0590337, 9124),
}
# END GENERATED CURVES
# (family, position) -> (S(d) at TD_KNOTS, TDs counted, source). source: measured | shrunk (n < 100, pulled toward
# the family's pooled share) | proxy (too few of its own: another family's shares).
# BEGIN GENERATED SHARES
TD_SHARES: dict[tuple[str, str], tuple[tuple[float, ...], int, str]] = {
    ('blocked_kick_tds', 'ALL'): ((0.78788, 0.69697, 0.54545, 0.33333, 0.30303, 0.27273, 0.18182, 0.06061, 0.03030), 33, 'measured'),
    ('def_tds', 'ALL'): ((0.89070, 0.85349, 0.75349, 0.60465, 0.41628, 0.30465, 0.20698, 0.12326, 0.07209), 430, 'measured'),
    ('fg_made', 'ALL'): ((1.00000, 1.00000, 0.99595, 0.74003, 0.43339, 0.16207, 0.00535, 0.00000, 0.00000), 6170, 'measured'),
    ('fumble_return_tds', 'ALL'): ((0.77852, 0.71141, 0.59732, 0.46309, 0.30872, 0.21477, 0.12752, 0.07383, 0.04698), 149, 'measured'),
    ('int_return_tds', 'ALL'): ((0.97166, 0.95951, 0.87449, 0.72470, 0.49393, 0.36032, 0.25506, 0.15789, 0.08907), 247, 'measured'),
    ('kick_return_tds', 'ALL'): ((0.93878, 0.93878, 0.93878, 0.93878, 0.93878, 0.83673, 0.83673, 0.83673, 0.83673), 49, 'measured'),
    ('missed_fg_return_tds', 'ALL'): ((0.93878, 0.93878, 0.93878, 0.93878, 0.93878, 0.83673, 0.83673, 0.83673, 0.83673), 1, 'proxy'),
    ('passing_tds', 'ALL'): ((0.76207, 0.54759, 0.31499, 0.18750, 0.11950, 0.07049, 0.04297, 0.02237, 0.00639), 5632, 'measured'),
    ('passing_tds', 'QB'): ((0.76231, 0.54666, 0.31382, 0.18682, 0.11965, 0.07057, 0.04281, 0.02221, 0.00645), 5583, 'measured'),
    ('passing_tds', 'RB'): ((0.67957, 0.47384, 0.27926, 0.18598, 0.08744, 0.05158, 0.03144, 0.01637, 0.00468), 11, 'shrunk'),
    ('passing_tds', 'TE'): ((0.80624, 0.65304, 0.39166, 0.22917, 0.13297, 0.09797, 0.07831, 0.03979, 0.00457), 12, 'shrunk'),
    ('passing_tds', 'WR'): ((0.77931, 0.62596, 0.40817, 0.22955, 0.11972, 0.05663, 0.04162, 0.03038, 0.00349), 25, 'shrunk'),
    ('punt_return_tds', 'ALL'): ((0.92593, 0.92593, 0.92593, 0.90741, 0.90741, 0.87037, 0.81481, 0.64815, 0.38889), 54, 'measured'),
    ('receiving_tds', 'ALL'): ((0.76207, 0.54759, 0.31499, 0.18750, 0.11950, 0.07049, 0.04297, 0.02237, 0.00639), 5632, 'measured'),
    ('receiving_tds', 'QB'): ((0.74656, 0.53569, 0.26124, 0.16562, 0.08962, 0.05287, 0.03223, 0.01678, 0.00479), 10, 'shrunk'),
    ('receiving_tds', 'RB'): ((0.77934, 0.53664, 0.25137, 0.11906, 0.07001, 0.04916, 0.02635, 0.01249, 0.00172), 664, 'measured'),
    ('receiving_tds', 'TE'): ((0.67739, 0.43469, 0.18470, 0.08123, 0.03701, 0.01942, 0.00918, 0.00323, 0.00013), 1418, 'measured'),
    ('receiving_tds', 'WR'): ((0.80087, 0.60309, 0.38604, 0.24718, 0.16560, 0.09729, 0.06112, 0.03271, 0.01004), 3476, 'measured'),
    ('return_tds', 'ALL'): ((0.93204, 0.93204, 0.93204, 0.92233, 0.92233, 0.85437, 0.82524, 0.73786, 0.60194), 103, 'measured'),
    ('rushing_tds', 'ALL'): ((0.42808, 0.25910, 0.13056, 0.08579, 0.06153, 0.03928, 0.02715, 0.01415, 0.00549), 3462, 'measured'),
    ('rushing_tds', 'QB'): ((0.41914, 0.21744, 0.06978, 0.03169, 0.02264, 0.01099, 0.00513, 0.00191, 0.00022), 714, 'measured'),
    ('rushing_tds', 'RB'): ((0.41715, 0.25776, 0.14111, 0.09716, 0.07129, 0.04737, 0.03289, 0.01800, 0.00743), 2549, 'measured'),
    ('rushing_tds', 'TE'): ((0.40546, 0.23176, 0.13478, 0.10585, 0.05982, 0.03924, 0.03475, 0.01759, 0.00203), 51, 'shrunk'),
    ('rushing_tds', 'WR'): ((0.69771, 0.53060, 0.26229, 0.15752, 0.09517, 0.04602, 0.03727, 0.00913, 0.00106), 126, 'measured'),
}
# END GENERATED SHARES


# ---------------------------------------------------------------------------------------------- lookups
def _pos(position: str | None) -> str:
    p = (position or "").strip()
    return POSITION_ALIASES.get(p, p.upper())


def _curve(stat: str, position: str | None) -> tuple[int, float, float, float, int] | None:
    return CURVES.get((stat, _pos(position))) or CURVES.get((stat, "ALL"))


def _tail(family: int, p1: float, p2: float, mp: np.ndarray, t: float) -> np.ndarray:
    """P(X >= t) for the scaled mean ``mp`` (> 0) of one family."""
    if family == NORMAL:
        return ndtr((mp - (t - 0.5)) / (p1 + p2 * mp))
    k = p1 + p2 * mp
    return gammaincc(k, max(t - 0.5, 0.0) * k / mp)


def has_curve(stat: str, position: str | None) -> bool:
    """True when ``prob_at_least`` has a fitted distribution for this stat (the position's own or the pooled one);
    False -> it falls back to the deterministic step (the scoring report says "approximated")."""
    return _curve(stat, position) is not None


def prob_at_least(stat: str, position: str | None, mean, threshold: float):
    """P(stat >= ``threshold`` in one game | projected mean ``mean``) -- scalar or array (broadcast). Monotone
    non-decreasing in ``mean``; 0 for a mean <= 0 or NaN; 1 for a threshold <= 0. A stat without a curve: the
    deterministic step ``float(mean >= threshold)`` (what the line paid before)."""
    m = np.asarray(mean, dtype=float)
    scalar = m.ndim == 0
    m = np.atleast_1d(m)
    t = float(threshold)
    if t <= 0:
        out = np.ones_like(m)
    else:
        c = _curve(stat, position)
        if c is None:
            out = np.where(np.nan_to_num(m, nan=-1.0) >= t, 1.0, 0.0)
        else:
            mp = c[1] * np.where(np.isfinite(m), m, 0.0)
            ok = mp > 1e-9
            out = np.zeros_like(m)
            if ok.any():
                out[ok] = _tail(c[0], c[2], c[3], mp[ok], t)
    return float(out[0]) if scalar else out


def prob_in_band(stat: str, position: str | None, mean, low: float, high: float | None):
    """P(low <= stat <= high) for one game; ``high`` inclusive (MFL's 100-199), None = open-ended. These stats are
    integers, so it is ``prob_at_least(low) - prob_at_least(high + 1)``."""
    p = prob_at_least(stat, position, mean, low)
    if high is None:
        return p
    q = prob_at_least(stat, position, mean, float(high) + 1)
    return np.clip(p - q, 0.0, 1.0) if isinstance(p, np.ndarray) else min(max(p - q, 0.0), 1.0)


def expected_band_points(stat: str, position: str | None, mean, bands: Iterable[tuple[float, float | None, float]]):
    """Sum of points x P(in band) over a stat's flat bands ``[(low, high_inclusive | None, points), ...]``."""
    total = 0.0
    for low, high, points in bands:
        total = total + float(points) * prob_in_band(stat, position, mean, low, high)
    return total


def expected_floor_units(stat: str, position: str | None, mean, per: float, start: float = 0.0, cap: float = 1000.0):
    """E[floor((X - start) / per)] for X >= start, else 0 -- MFL's "1 point per 10 yards" (``1/10``, paid per whole
    10 from the band's low ``start``) in expectation: sum over j >= 1 of P(X >= start + j x per). A linear price,
    (mean - start) / per, is high by the expected remainder (about 0.45 of a unit for a yardage stat that is
    usually well above 0). A stat without a curve: the linear price (the caller says "approximated")."""
    m = np.asarray(mean, dtype=float)
    per = float(per)
    if not has_curve(stat, position) or per <= 0:
        out = np.clip(np.nan_to_num(m) - start, 0.0, None) / max(per, 1e-9)
        return float(out) if out.ndim == 0 else out
    total = np.zeros_like(np.atleast_1d(m))
    j = 1
    while start + j * per <= cap:
        total = total + np.atleast_1d(prob_at_least(stat, position, m, start + j * per))
        j += 1
    return float(total[0]) if m.ndim == 0 else total


# ---------------------------------------------------------------------------------------------- TD distances
def _shares(family: str, position: str | None) -> tuple[tuple[float, ...], int, str] | None:
    fam = MFL_TD_FAMILY.get(family, family)
    return TD_SHARES.get((fam, _pos(position))) or TD_SHARES.get((fam, "ALL"))


def td_share_source(family: str, position: str | None) -> str:
    """"measured" (this position's own TDs, or the family pooled) | "shrunk" | "proxy" | "placeholder" (an unknown
    family: priced with every offensive TD pooled)."""
    s = _shares(family, position)
    return "placeholder" if s is None else s[2]


def td_survival(family: str, position: str | None, distance) -> np.ndarray | float:
    """S(d) = the share of the family's TDs of at least ``distance`` yards (scalar or array)."""
    s = _shares(family, position) or TD_SHARES.get(("receiving_tds", "ALL"))
    d = np.asarray(distance, dtype=float)
    if s is None:   # constants not generated (never in a shipped build): everything is short
        out = np.where(d <= 0, 1.0, 0.0)
        return float(out) if out.ndim == 0 else out
    xs = np.array([0.0, *TD_KNOTS, float(TD_MAX_DISTANCE)])
    surv = np.array([1.0, *s[0]])
    ys = np.log(np.maximum(surv, 1e-6))
    # beyond the last knot: the last segment's log slope, to 0 at TD_MAX_DISTANCE
    slope = (ys[-1] - ys[-2]) / (xs[-2] - xs[-3]) if surv[-1] > 1e-6 else 0.0
    ys = np.append(ys, ys[-1] + slope * (xs[-1] - xs[-2]))
    out = np.exp(np.interp(d, xs, ys))
    out = np.where(d <= 0, 1.0, np.where(d > TD_MAX_DISTANCE, 0.0, out))
    return float(out) if out.ndim == 0 else out


def td_distance_share(family: str, position: str | None, low: int, high: int | None) -> float:
    """E[share of the family's TDs with distance in [low, high] yards], ``high`` inclusive, None = open. Distances are
    whole yards, so it is S(low) - S(high + 1); the shares over a partition of 0..inf sum to 1."""
    lo = float(td_survival(family, position, max(int(low), 0)))
    hi = 0.0 if high is None else float(td_survival(family, position, int(high) + 1))
    return max(lo - hi, 0.0)


def expected_td_distance_points(family: str, position: str | None, expected_tds,
                                bands: Iterable[tuple[int, int | None, float]]):
    """``expected_tds`` x sum(points x td_distance_share(band)) -- a projected line's TDs priced by distance."""
    per_td = sum(float(points) * td_distance_share(family, position, low, high) for low, high, points in bands)
    return np.asarray(expected_tds, dtype=float) * per_td if isinstance(expected_tds, np.ndarray) else float(expected_tds or 0) * per_td


# ---------------------------------------------------------------------------------------------- Sleeper settings
# The house leagues and every Sleeper league: the yardage bonuses (scoring.SLEEPER_BONUS_MAP, exclusive ranges) and
# the long-TD keys (scoring.SLEEPER_LONG_TD_MAP) priced at their expectation on a projected line. The backtest below
# uses it; IC-1's spec pricing does the same through prob_in_band / td_distance_share.
LONG_TD_FAMILY = {"pass_td_40p": ("passing_tds", 40), "pass_td_50p": ("passing_tds", 50),
                  "rush_td_40p": ("rushing_tds", 40), "rush_td_50p": ("rushing_tds", 50),
                  "rec_td_40p": ("receiving_tds", 40), "rec_td_50p": ("receiving_tds", 50)}


def sleeper_expected_bonus(line: Mapping[str, float | None], scoring: Mapping[str, float], position: str | None) -> float:
    """Expected points of a Sleeper scoring's bonus keys on one projected line (``line`` holds the
    ``projections.ALL_COMPONENTS`` means). Add it to ``compute_points(line, scoring, include_bonuses=False)``."""
    from .scoring import SLEEPER_BONUS_MAP

    total = 0.0
    for key, (col, lo, hi, _) in SLEEPER_BONUS_MAP.items():
        w = float(scoring.get(key) or 0.0)
        if w:
            total += w * prob_in_band(col, position, float(line.get(col) or 0.0), lo, None if hi is None else hi - 1)
    for key, (family, d) in LONG_TD_FAMILY.items():
        w = float(scoring.get(key) or 0.0)
        if w:
            total += w * float(line.get(family) or 0.0) * float(td_survival(family, position, d))
    return total


def sleeper_expected_bonus_frame(df, scoring: Mapping[str, float], prefix: str = "proj_") -> np.ndarray:
    """``sleeper_expected_bonus`` for every row of a frame with ``<prefix><component>`` columns and ``position``."""
    from .scoring import SLEEPER_BONUS_MAP

    out = np.zeros(len(df))
    pos = df["position"].to_numpy()
    for position in np.unique(pos):
        sel = pos == position
        g = df[sel]
        for key, (col, lo, hi, _) in SLEEPER_BONUS_MAP.items():
            w = float(scoring.get(key) or 0.0)
            if w:
                out[sel] += w * prob_in_band(col, position, g[f"{prefix}{col}"].to_numpy(dtype=float), lo,
                                             None if hi is None else hi - 1)
        for key, (family, d) in LONG_TD_FAMILY.items():
            w = float(scoring.get(key) or 0.0)
            if w:
                out[sel] += w * np.nan_to_num(g[f"{prefix}{family}"].to_numpy(dtype=float)) * float(td_survival(family, position, d))
    return out


# ---------------------------------------------------------------------------------------------- the seed
SEED = Path(__file__).resolve().parents[2] / "dbt" / "seeds" / "scoring_distributions.csv"
SEED_COLUMNS = ("kind", "stat", "position", "param", "value", "n", "seasons", "source", "version")


def seed_rows() -> list[dict[str, str]]:
    """The constants as ``dbt/seeds/scoring_distributions.csv`` rows (long format, one number per row)."""
    rows: list[dict[str, str]] = []
    for (stat, pos), (fam, scale, p1, p2, n) in sorted(CURVES.items()):
        names = ("sd0", "sd1") if fam == NORMAL else ("shape_k0", "shape_k1")
        for param, value in (("family", float(fam)), ("mean_scale", scale), (names[0], p1), (names[1], p2)):
            rows.append(dict(kind="curve", stat=stat, position=pos, param=param, value=f"{value:.6g}", n=str(n),
                             seasons=FIT_SEASONS, source="measured", version=VERSION))
    for (fam, pos), (surv, n, source) in sorted(TD_SHARES.items()):
        for knot, value in zip(TD_KNOTS, surv, strict=True):
            rows.append(dict(kind="td_share", stat=fam, position=pos, param=f"ge_{knot}", value=f"{value:.6g}", n=str(n),
                             seasons=FIT_SEASONS, source=source, version=VERSION))
    return rows


def write_seed(path: Path = SEED) -> int:
    rows = seed_rows()
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SEED_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


# ---------------------------------------------------------------------------------------------- offline fitting
_BOUNDS = {GAMMA: [(-0.5, 0.5), (-8.0, 4.0), (-10.0, 3.0)], NORMAL: [(-0.5, 0.5), (-5.0, 6.0), (-8.0, 2.0)]}
_X0 = {GAMMA: [0.0, 0.0, -3.0], NORMAL: [0.0, 1.0, -1.0]}


def _curve_loss(params: np.ndarray, family: int, m: np.ndarray, hits: list[tuple[float, np.ndarray]]) -> float:
    mp = np.exp(params[0]) * m
    loss = 0.0
    for t, y in hits:
        p = np.clip(_tail(family, float(np.exp(params[1])), float(np.exp(params[2])), mp, t), 1e-9, 1 - 1e-9)
        loss -= float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))
    return loss / len(m)


def fit_curve(proj: np.ndarray, actual: np.ndarray, stat: str) -> tuple[int, float, float, float, int]:
    """(family, mean_scale, p1, p2, rows) for one position x stat: minimum log loss of 1{actual >= t} over
    ``FIT_THRESHOLDS[stat]``, on rows with a projection > 0.5 (below it every threshold is ~0 either way). Parameters
    are fitted on the log scale, so k0, k1 / sd0, sd1 are positive and the mean scale stays within e^+-0.5."""
    from scipy.optimize import minimize

    family = CURVE_FAMILY.get(stat, GAMMA)
    proj, actual = np.asarray(proj, dtype=float), np.asarray(actual, dtype=float)
    ok = np.isfinite(proj) & np.isfinite(actual) & (proj > 0.5)
    m, y = proj[ok], actual[ok]
    hits = [(float(t), (y >= t).astype(float)) for t in FIT_THRESHOLDS[stat]]
    res = minimize(_curve_loss, x0=np.array(_X0[family]), args=(family, m, hits), method="L-BFGS-B", bounds=_BOUNDS[family])
    ls, l1, l2 = res.x
    return family, float(np.exp(ls)), float(np.exp(l1)), float(np.exp(l2)), int(ok.sum())


def fit_curves(rows, min_rows: int = MIN_CURVE_ROWS) -> dict[tuple[str, str], tuple[int, float, float, float, int]]:
    """Every position x stat with enough rows, plus the pooled (ALL) curve per stat, from rows carrying
    ``position``, ``proj_<stat>`` and ``out_<stat>`` (``calibration.oof_rows(..., lines=True)``, one scoring)."""
    out: dict[tuple[str, str], tuple[int, float, float, float, int]] = {}
    for stat in CURVE_STATS:
        for pos, g in [*rows.groupby("position"), ("ALL", rows)]:
            x, y = g[f"proj_{stat}"].to_numpy(dtype=float), g[f"out_{stat}"].to_numpy(dtype=float)
            if int((np.isfinite(x) & np.isfinite(y) & (x > 0.5)).sum()) < min_rows:
                continue
            out[(stat, pos)] = fit_curve(x, y, stat)
            log.info("curve %s %s: %s", stat, pos, out[(stat, pos)])
    return out


TD_PLAYS_SQL = """
select p.season, p.week, p.play_type, p.description, p.yards_gained, p.pass_touchdown, p.rush_touchdown,
       p.is_interception, p.fumble, pp.position as passer_position, rp.position as receiver_position,
       rr.position as rusher_position
from analytics.fct_play p
left join analytics.fct_player_game pp on pp.gsis_id = p.passer_player_id and pp.game_id = p.game_id
left join analytics.fct_player_game rp on rp.gsis_id = p.receiver_player_id and rp.game_id = p.game_id
left join analytics.fct_player_game rr on rr.gsis_id = p.rusher_player_id and rr.game_id = p.game_id
where p.touchdown and p.season between %s and %s and p.season_type = 'REG' and not coalesce(p.is_two_point, false)
"""
_RETURN = re.compile(r"for (-?\d+) yards?, TOUCHDOWN|for no gain, TOUCHDOWN")


def return_distance(description: str | None) -> float:
    """The scoring run of a return / defensive TD from nflverse's play description ("... for 61 yards, TOUCHDOWN");
    0 for a recovery in the end zone ("RECOVERED ... at NO -8. TOUCHDOWN.")."""
    hits = list(_RETURN.finditer(description or ""))
    if not hits:
        return 0.0
    g = hits[-1].group(1)
    return float(g) if g is not None else 0.0


def td_family(play: Mapping) -> str:
    """The family of a TD play (offense by the pass / rush flags; the rest by play type)."""
    if play.get("pass_touchdown"):
        return "passing_tds"
    if play.get("rush_touchdown"):
        return "rushing_tds"
    if play.get("is_interception"):
        return "int_return_tds"
    blocked = "BLOCKED" in (play.get("description") or "")
    kind = play.get("play_type")
    if kind == "kickoff":
        return "kick_return_tds"
    if kind == "punt":
        return "blocked_kick_tds" if blocked else "punt_return_tds"
    if kind == "field_goal":
        return "blocked_kick_tds" if blocked else "missed_fg_return_tds"
    return "fumble_return_tds"


def td_distances(plays) -> list[tuple[str, str, float]]:
    """(family, position, distance) per TD: a passing TD counts for the passer (passing_tds) and the receiver
    (receiving_tds); return and defensive TDs have position ALL."""
    out: list[tuple[str, str, float]] = []
    for p in plays.to_dict("records"):
        fam = td_family(p)
        if fam == "passing_tds":
            d = float(p["yards_gained"])
            out.append(("passing_tds", p.get("passer_position") or "ALL", d))
            out.append(("receiving_tds", p.get("receiver_position") or "ALL", d))
        elif fam == "rushing_tds":
            out.append(("rushing_tds", p.get("rusher_position") or "ALL", float(p["yards_gained"])))
        else:
            out.append((fam, "ALL", return_distance(p.get("description"))))
    return out


def measure_td_shares(distances: list[tuple[str, str, float]], shrink: int = SHRINK_TDS, min_family: int = 20
                      ) -> dict[tuple[str, str], tuple[tuple[float, ...], int, str]]:
    """S(d) at TD_KNOTS per family x position (QB-TE) and pooled (ALL). A position with n TDs is shrunk toward the
    pooled: (n x own + ``shrink`` x pooled) / (n + shrink), source "shrunk" when n < 100. A family with fewer than
    ``min_family`` TDs in all takes the kick-return shares (source "proxy": a missed field goal returned is a kick
    return)."""
    import pandas as pd

    d = pd.DataFrame(distances, columns=["family", "position", "distance"])
    knots = np.array(TD_KNOTS, dtype=float)
    out: dict[tuple[str, str], tuple[tuple[float, ...], int, str]] = {}

    def surv(x: np.ndarray) -> np.ndarray:
        return (x[:, None] >= knots[None, :]).mean(axis=0)

    pooled: dict[str, tuple[np.ndarray, int]] = {}
    for fam, g in d.groupby("family"):
        pooled[fam] = (surv(g["distance"].to_numpy(dtype=float)), len(g))
    for fam, (s, n) in pooled.items():
        if n >= min_family:
            out[(fam, "ALL")] = (tuple(round(float(v), 5) for v in s), n, "measured")
    for fam, (_s, n) in pooled.items():
        if n < min_family and ("kick_return_tds", "ALL") in out:
            out[(fam, "ALL")] = (out[("kick_return_tds", "ALL")][0], n, "proxy")
    for fam, members in POOLED_FAMILIES.items():
        g = d[d["family"].isin(members)]
        if len(g) >= min_family:
            out[(fam, "ALL")] = (tuple(round(float(v), 5) for v in surv(g["distance"].to_numpy(dtype=float))), len(g), "measured")
    for fam in OFFENSE_TD_FAMILIES:
        if fam not in pooled:
            continue
        base = pooled[fam][0]
        for pos in POSITIONS:
            g = d[(d["family"] == fam) & (d["position"] == pos)]
            n = len(g)
            own = surv(g["distance"].to_numpy(dtype=float)) if n else base
            s = (n * own + shrink * base) / (n + shrink)
            out[(fam, pos)] = (tuple(round(float(v), 5) for v in s), n, "measured" if n >= 100 else "shrunk")
    return out


FG_SQL = f"""select {', '.join(f'sum({c})' for c, _ in FG_BUCKETS)} from analytics.fct_player_game
             where season between %s and %s and season_type = 'REG'"""


def measure_fg_shares(made: Mapping[str, float]) -> tuple[tuple[float, ...], int, str]:
    """S(d) at TD_KNOTS for made field goals from the bucket totals (``FG_BUCKETS`` columns -> count): exact at the
    bucket edges 20 / 30 / 40 / 50 / 60, 1 below 20 (none shorter than 18), 0 from 70 (no made kick of 70)."""
    n = float(sum(made.values()))
    out = []
    for knot in TD_KNOTS:
        if knot <= 18:
            out.append(1.0)
        elif knot >= 70:
            out.append(0.0)
        else:
            out.append(round(sum(float(made.get(c) or 0) for c, lo in FG_BUCKETS if lo >= knot) / n, 5))
    return tuple(out), int(n), "measured"


def constants_block(curves, shares) -> str:
    """The two generated constant blocks as Python source (paste between the BEGIN / END markers)."""
    lines = ["CURVES: dict[tuple[str, str], tuple[int, float, float, float, int]] = {"]
    for (stat, pos), (fam, s, p1, p2, n) in sorted(curves.items()):
        lines.append(f"    ({stat!r}, {pos!r}): ({fam}, {s:.6g}, {p1:.6g}, {p2:.6g}, {n}),")
    lines.append("}")
    lines.append("TD_SHARES: dict[tuple[str, str], tuple[tuple[float, ...], int, str]] = {")
    for (fam, pos), (sv, n, src) in sorted(shares.items()):
        lines.append(f"    ({fam!r}, {pos!r}): (({', '.join(f'{v:.5f}' for v in sv)}), {n}, {src!r}),")
    lines.append("}")
    return "\n".join(lines)


def run_fit(seasons: tuple[int, int] = (2019, 2025), scoring_league: str | None = None) -> str:
    """Offline: the walk-forward out-of-sample rows with the projected line (``calibration.oof_rows(lines=True)``,
    about 45 CPU-seconds per season with ``OMP_NUM_THREADS=1``) -> the curves; ``analytics.fct_play`` -> the TD
    shares. Returns the constants block (and logs it); the module is not rewritten in place."""
    import pandas as pd
    import psycopg

    from . import projections as P
    from .calibration import oof_rows
    from .config import get_settings

    lo, hi = seasons
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        scorings = P.league_scorings(conn)
        alls = P.available_seasons(conn)
        frame = P.load_frame(conn, [s for s in alls if s <= hi])
        with conn.cursor() as cur:
            cur.execute(TD_PLAYS_SQL, (lo, hi))
            plays = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
            cur.execute(FG_SQL, (lo, hi))
            fg = dict(zip([c for c, _ in FG_BUCKETS], [float(v or 0) for v in cur.fetchone()], strict=True))
    lid = scoring_league or next(iter(scorings))
    rows = oof_rows(frame, list(range(lo, hi + 1)), {lid: scorings[lid]}, min(alls), ranges=False, lines=True)
    shares = measure_td_shares(td_distances(plays))
    shares[("fg_made", "ALL")] = measure_fg_shares(fg)
    block = constants_block(fit_curves(rows[rows["actual"].notna()]), shares)
    log.info("scoring_ev constants:\n%s", block)
    return block
