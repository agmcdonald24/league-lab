"""The League screen's power rankings and the rest of the season (IN-6, Wave I-N; docs/METRICS.md § "Power rankings
and the season outlook").

``GET /api/league/outlook?league=&team=&source=`` (asked by the League screen after it shows, like the week's odds):

* **Power rankings** (``power``): every team ranked by **the points its best lineup is expected to score per week over
  the rest of the season** — the trade engine's rest-of-season board (``decisions.window_board(ctx, "ros")``: today's
  rosters, this week on the availability overlay, a player in the IR slot / on NFL injured reserve / with no team stays
  out, every later week from the rest-of-season projections), each week's best legal lineup re-solved
  (``RosterBoard.lineup_value``), averaged over the weeks to the league's final. One stated number, not a blend. Beside
  it, as columns: the record, points for (and its rank), points against, the record-vs-points gap in words when it is
  large, and the remaining schedule's strength (the opponents' own power number, averaged over the games left). No
  movement arrows: last week's rest-of-season board is not kept (the nightly overwrites the weeks ahead), so last week's
  ranking cannot be recomputed honestly.
* **The rest of the season** (``outlook``): ``SEASONS`` simulated seasons of the remaining regular-season schedule.
  - The first week left (normally this week) is drawn from **the week's odds' own pieces** (``league_lab.decisions``:
    every starter's range through his P10 … P90, centred on his projection, one Gaussian copula over every starter of
    the league with ``pair_rho`` for players of one NFL game, kickers / defenses independent, played games at their
    points), and each game is decided with **the week's odds' calibration**: the raw chance ``p_raw`` (the share of
    draws the side outscores the other) is shrunk exactly as the week's odds shrink it (``shrink_week``), and side a
    wins the draws where its margin is above the margin's (1 − p) quantile — so a game's simulated chance is the
    week's odds' number (``first_week`` lists both; within a point is the check) and a bigger margin still wins first.
  - Every later week: each team's best lineup that week on the rest-of-season board (the power ranking's own numbers),
    spread like its own lineup's ranges (the first week's spread as a share of its total), widened by 1/0.60 (for a
    near-normal difference the same calibration: ``sigmoid(0.6 · logit Φ(z))`` ≈ ``Φ(0.6 · z)``),
    plus a **drift that grows with the weeks ahead** (a random walk per team and season: ``DRIFT`` = 3% of its weekly
    level per week, √weeks — an assumption, not fitted: injuries, trades and role changes the projections cannot see).
    Opposing lineups of later weeks are independent.
  - Wins (a tie counts half) and points for add up; the final order is wins, then points for (the tie-break stated).
    Playoff odds = the share of seasons a team finishes inside the league's playoff spots; the top seed; a bye when the
    bracket has byes (2^⌈log₂ spots⌉ − spots, the top seeds). **No title odds**: the bracket is not simulated.
  - ``clinched`` / ``eliminated`` are proven, not simulated (wins alone: nobody else can reach / everybody needed is
    already past), and only then does a page say 100% / out.
  Cached per league, build and overlay stamp (``league_lab.memo`` region ``outlook``), the same TTL as the league's
  other decision answers (10 minutes on a house league, 2 on demand). The simulation is numpy, fixed seed (the same
  answer on a reload), off the event loop (a sync route: FastAPI's thread pool).

What a provider must give for the outlook: the playoff start week (the regular season's end), the remaining weeks'
pairings and, for the playoff columns, the number of playoff teams. Sleeper gives all three (house and on demand);
MyFantasyLeague's export has the schedule and the last regular-season week but **no playoff team count** (the adapter
guesses 2^rounds): the projected record shows, the playoff columns are absent with that reason. A league with
divisions: division winners' places are not simulated, so the playoff columns are absent and say so. ESPN reads
through the same seam (``playoffTeamCount`` and the schedule from its matchups) and is unverified live; Yahoo's data
access is pending.

**Wave I-O (IO-2)** — marked ``IO-2`` below: every full build offers its power ranking and rows to the snapshot store
(``outlook_store``: one row per league-week, replaced only until the week's first kickoff, off quietly without the
table); last week's stored row gives the **movement** (``power.rows[].moved``: places up (+) or down (−);
``outlook.rows[].playoff_change``: the change in playoff odds) — never anything but a stored row. ``part=power`` answers
the power rankings without the season simulation (the League screen asks it first, then the whole answer: the first
paint of a league not kept every night). A league not kept every night is read with a market-free context (the
outlook needs the lineups, not the trade market: the free agents and the later weeks' prices are what made MFL 70587's
first build ~10 s); the trade screens' own context is used when it is already built. ``preview`` / ``shell``: the page
shell's link preview for ``/league?league=<key>`` from what is cached or stored only. **Title odds** (Sleeper leagues
whose bracket is readable from the settings): the playoff weeks are drawn in the same simulated seasons, after the
regular season's (the drift carries on), and the bracket is played out per season (``play_bracket``: seeds by wins then
points for, the top seeds' byes, a round's points over its weeks, ``playoff_seed_type`` 1 = re-seeded before every
round — the house dynasty's 2021, 2022 and 2024 brackets pair exactly so — else a fixed bracket; a tie to the higher seed).
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from league_lab import anyleague as A
from league_lab import (  # ---- IO-2: clock; fix round: provider_share; IP-5: the watch
    clock,
    memo,
    provider_share,
    provider_trouble,
)
from league_lab import decisions as WP  # the week's win probability: one model in the product

from . import availability
from . import decisions as D
from . import myweek as MW
from . import outlook_store as S  # ---- IO-2
from .applib import cards
from .db import query
from .myweek import NotFound

router = APIRouter()
VERSION = "ol1.0"
SEASONS = 10_000               # Monte Carlo error of a 50% playoff chance: ±0.5 points (one standard error)
MIN_SEASONS = 1_000            # the fewest a big league gets (±1.6 points)
WORK_BUDGET = 1_600_000        # seasons × teams × max(weeks, starters per team): a 12-team league gets all 10,000
CHUNK_CELLS = 250_000          # numbers in one chunk's array (2 MB of float64): memory flat in the season count
FIRST_CELLS = 64_000           # the first week's chunks (a draw per starter; the quantile step makes ~10 temporaries)
MAX_TEAMS, MAX_STARTERS, MAX_WEEKS = 32, 30, 18                # beyond these: the power rankings only, and why
SEED = 20261006
DRIFT = 0.03                   # the per-week random walk of a team's level, as a share of its weekly points (assumed)
PATH = "/api/league/outlook"
TTL_S = {"house": 600.0, "sleeper": 120.0}
# one small answer per league (~10 KB); IO-2: 96 (was 48) — a league holds its power part (~7 KB) and its whole answer
_cache = memo.region("outlook", ttl=TTL_S["house"], max_entries=96)
# future pairings do not change: a league's remaining schedule is kept for hours ({week: [(a, b)]}, ~2 KB a league)
SCHEDULE_TTL_S = 6 * 3600.0
_schedules = memo.region("outlook_schedule", ttl=SCHEDULE_TTL_S, max_entries=256)
# ONE outlook simulation at a time in the process (on top of the heavy bucket and the CPU slots): a second waits up
# to BUSY_WAIT_S, then the route answers 429 `busy` (nothing is cached)
_SIM = threading.Lock()
BUSY_WAIT_S = 5.0
BUSY_WORDS = "Another league's season is being simulated right now. Try again in a few seconds."


class Busy(Exception):
    pass

ASSUMES = ("rosters as they are today (no trades, claims or drops ahead)", "every team starts its best lineup",
           "known injuries only (a player out today is out this week; injured reserve stays out)",
           "the further out the week, the wider its range")
POWER_WORDS = ("Ranked by the points each team's best lineup is expected to score per week over the rest of the "
               "season ({span}), with today's rosters and injuries.")
NO_ARROWS = "No movement arrows: last week's rest-of-season projections are not kept, so last week's ranking cannot be rebuilt."
DEFINITIONS = {
    "power": "Power ranking: teams in order of the points their best lineup is expected to score per week over the rest "
             "of the season (each week's best legal lineup from today's roster, this league's scoring, the weeks to the "
             "league's final). Record and points so far are beside it, not in it.",
    "record": "Record · points for: the regular-season record so far and the points scored, with where the points rank "
              "in the league (1st = the most). \"Soft schedule so far\" / \"Hard schedule so far\" when the record's "
              "place and the points' place are 3 or more apart.",
    "points_against": "Against: the points scored against the team so far (its opponents' totals in its games).",
    "schedule_left": "Schedule left: the average power number (points per week) of the opponents still to play in the "
                     "regular season. Rank 1 = the hardest schedule left.",
    "projected_record": "Projected record: the average final regular-season record over the simulated seasons, and the "
                        "middle 80% of the win totals (1 season in 10 ends below, 1 in 10 above).",
    "playoff_odds": "Playoff odds: how often the team finishes inside the playoff spots in the simulated seasons (ties "
                    "on wins broken by points for). 100% and out only when it is certain on wins alone.",
    "top_seed": "Top seed: how often the team finishes first after the regular season.",
    "bye": "Bye: how often the team finishes in a spot that skips the first playoff round.",
    # ---- IO-2
    "title": "Title: how often the team wins the league's playoff bracket in the simulated seasons (the bracket is "
             "described under the table). Context only: the title odds have not been replayed on past seasons.",
}


# ------------------------------------------------------------------------------------------- the first week: copula
def _dist(r: Mapping):
    """One starter's range as ``WP._week_dist`` reads it, ignoring a played game (the week's spread before kickoff)."""
    kind, d = WP._week_dist({**r, "actual": None})
    return d if kind == "range" else None


def prepare(sides: Mapping[int, Sequence[Mapping]]) -> dict:
    """The first week's pieces without a single draw (cheap): every starter's centred range, who plays for whom, the
    fixed points (games in; starters with no range), ``expected`` and ``ranged_share`` per team (the week's odds' rule
    is checked on these before anything is simulated), the starters per team."""
    teams = sorted(int(t) for t in sides)
    cols: dict[str, int] = {}
    dists, meta, played_mask, owners = [], [], [], []
    fixed = np.zeros(len(teams))
    expected = np.zeros(len(teams))
    ranged_val = np.zeros(len(teams))
    abs_val = np.zeros(len(teams))
    for ti, t in enumerate(teams):
        for i, r in enumerate(sides[t]):
            v = WP._num(r.get("value"))
            act = WP._num(r.get("actual"))
            d = _dist(r)
            expected[ti] += act if act is not None else (0.0 if v is None else v)
            abs_val[ti] += abs(v or 0.0) if act is None else 0.0
            if d is None:
                fixed[ti] += act if act is not None else (0.0 if v is None else v)
                continue
            if act is None:
                ranged_val[ti] += abs(v or 0.0)
            else:
                fixed[ti] += act
            key = r.get("key")
            key = f"_{t}_{i}" if not isinstance(key, str) or not key else key
            if key in cols:                          # one player is on one roster: a repeat is the same draw
                owners[cols[key]].append(ti)
                continue
            cols[key] = len(dists)
            dists.append(WP._centred(d, v))
            meta.append(r)
            played_mask.append(act is not None)
            owners.append([ti])
    share = np.where(abs_val > 0, ranged_val / np.where(abs_val > 0, abs_val, 1.0), 1.0)
    keys = list(cols)
    perm = sorted(range(len(dists)), key=lambda j: str(keys[j]))     # draws assigned in key order, as the week's odds do
    return {"teams": teams, "expected": expected, "ranged_share": share, "fixed": fixed,
            "dists": [dists[j] for j in perm], "meta": [meta[j] for j in perm], "owners": [owners[j] for j in perm],
            "played": np.array([played_mask[j] for j in perm], dtype=bool),
            "starters": {t: len(sides[t]) for t in teams}}


def _blocks(meta: Sequence[Mapping]) -> list[tuple[np.ndarray, np.ndarray | None]]:
    """The copula's correlation in independent blocks: only a pair ``relationship`` can name correlates (same NFL team,
    or one's team is the other's opponent), so the matrix is block-diagonal by NFL game. Each block repaired
    (``_nearest_corr``) and rooted on its own — the same as the whole matrix (a block-diagonal matrix's eigenvectors are
    its blocks'), at a fraction of the cost. [(column indices, root or None for a lone column)]."""
    m = len(meta)
    by_team: dict[str, list[int]] = {}
    by_opp: dict[str, list[int]] = {}
    pos_of: list = []
    for j, r in enumerate(meta):
        pj = WP.UNIT_AS.get(str(r.get("position")), r.get("position"))
        pos_of.append(pj)
        if pj in WP.KD_POSITIONS:
            continue
        if isinstance(r.get("team"), str) and r.get("team"):
            by_team.setdefault(r["team"], []).append(j)
        if isinstance(r.get("opponent"), str) and r.get("opponent"):
            by_opp.setdefault(r["opponent"], []).append(j)
    parent = list(range(m))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    rho: dict[tuple[int, int], float] = {}
    for a, ra in enumerate(meta):
        if pos_of[a] in WP.KD_POSITIONS or not isinstance(ra.get("team"), str) or not ra.get("team"):
            continue
        cand = set(by_team.get(ra["team"], ())) | set(by_opp.get(ra["team"], ()))
        if isinstance(ra.get("opponent"), str) and ra.get("opponent"):
            cand |= set(by_team.get(ra["opponent"], ()))
        for b in cand:
            if b <= a:
                continue
            rb = meta[b]
            r_ = WP.pair_rho(WP.relationship(ra.get("team"), ra.get("opponent"), rb.get("team"), rb.get("opponent")),
                             pos_of[a], pos_of[b])
            if r_:
                rho[(a, b)] = r_
                parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for j in range(m):
        groups.setdefault(find(j), []).append(j)
    out = []
    for idx in groups.values():
        idx_a = np.array(sorted(idx), dtype=int)
        if len(idx_a) == 1:
            out.append((idx_a, None))
            continue
        where = {j: i for i, j in enumerate(idx_a)}
        c = np.eye(len(idx_a))
        for (a, b), r_ in rho.items():
            if a in where and b in where:
                c[where[a], where[b]] = c[where[b], where[a]] = r_
        c = WP._nearest_corr(c)
        w, v = np.linalg.eigh(c)
        out.append((idx_a, (v * np.sqrt(np.maximum(w, 0.0))).T))
    return out


def chunk_rows(width: int, cells: int | None = None) -> int:
    """Seasons per chunk so that one chunk's array holds about ``cells`` numbers (default ``CHUNK_CELLS``; 50 … 2,000
    rows)."""
    return int(min(2000, max(50, (cells or CHUNK_CELLS) // max(1, width))))


def ppf_group(lv: np.ndarray, vals: np.ndarray, u: np.ndarray) -> np.ndarray:
    """``Predictive.ppf`` for many ranges with the same knots at once: ``lv`` (K levels), ``vals`` (g × K values),
    ``u`` (c × g probabilities) -> c × g points. The same function, column for column (linear between the knots; below
    the first, linear and never under 0; above the last, the exponential tail with a continuous density)."""
    K = len(lv)
    idx = np.clip(np.searchsorted(lv, u, side="right") - 1, 0, K - 2)
    g = np.arange(vals.shape[0])[None, :]
    l0, l1 = lv[idx], lv[idx + 1]
    v0, v1 = vals[g, idx], vals[g, idx + 1]
    out = v0 + (np.clip(u, lv[0], lv[-1]) - l0) / (l1 - l0) * (v1 - v0)
    half = int(np.searchsorted(lv, 0.5))
    slope_lo = np.maximum((vals[:, 1] - vals[:, 0]) / (lv[1] - lv[0]), (vals[:, half] - vals[:, 0]) / (lv[half] - lv[0]))
    slope_hi = np.maximum((vals[:, -1] - vals[:, -2]) / (lv[-1] - lv[-2]), (vals[:, -1] - vals[:, half]) / (lv[-1] - lv[half]))
    low = u < lv[0]
    if low.any():
        floor = np.minimum(0.0, vals[:, 0])[None, :]
        below = np.maximum(vals[:, 0][None, :] - slope_lo[None, :] * (lv[0] - u), floor)
        out = np.where(low, below, out)
    high = u > lv[-1]
    if high.any():
        sc = ((1.0 - lv[-1]) * slope_hi)[None, :]
        above = vals[:, -1][None, :] + sc * np.log((1.0 - lv[-1]) / (1.0 - np.where(high, u, 0.5)))
        out = np.where(high, above, out)
    return out


def first_week_draws(sides: Mapping[int, Sequence[Mapping]] | None = None, *, n: int = SEASONS, seed: int = SEED,
                     k: float = WP.WEEK_SHRINK, prep: dict | None = None) -> dict:
    """Every team's total in the first week left, ``n`` joint draws (the week's odds' pieces for the whole league),
    drawn in chunks of seasons: only the team totals are kept (n × T), never a draw per starter.

    ``sides``: roster id -> starters (``myweek.win_starters`` rows with ``actual`` set where the game is in), or
    ``prep`` (``prepare``'s answer). Returns ``teams``, ``totals`` (n × T: the raw joint draws, played games at their
    points — ``lineup_win_probability``'s totals for the whole league; the calibration is applied per game in
    ``simulate``), ``expected`` (T), ``spread`` (T: the raw standard deviation of each lineup's total over every
    starter's range, played or not — its pre-game spread), ``ranged_share`` (T). ``k`` is kept for the signature's
    sake (the first week is not widened)."""
    pr = prep if prep is not None else prepare(sides or {})
    teams, dists, owners, played = pr["teams"], pr["dists"], pr["owners"], pr["played"]
    T, m = len(teams), len(dists)
    out = {"teams": teams, "expected": pr["expected"], "ranged_share": pr["ranged_share"], "n_starters": m}
    if m == 0:
        return {**out, "totals": np.tile(pr["fixed"], (n, 1)), "spread": np.zeros(T)}
    blocks = _blocks(pr["meta"])
    groups: dict[tuple, list[int]] = {}                      # the ranges by their knots (3 or 5): one ppf per group
    for j, d in enumerate(dists):
        groups.setdefault(tuple(d.levels), []).append(j)
    gv = [(np.asarray(lv), np.array(cols, dtype=int), np.array([dists[j].values for j in cols], dtype=float))
          for lv, cols in groups.items()]
    own = np.zeros((m, T))                                    # starter -> his team (a key on two rosters: both)
    for j, ts in enumerate(owners):
        for ti in ts:
            own[j, ti] = 1.0
    own_live = own * (~played)[:, None]
    totals = np.empty((n, T))
    s1, s2 = np.zeros(T), np.zeros(T)
    rows = chunk_rows(m, FIRST_CELLS)
    for ci, lo in enumerate(range(0, n, rows)):
        c = min(rows, n - lo)
        rng = np.random.default_rng([seed, ci])
        z = rng.standard_normal((c, m))
        for idx, root in blocks:
            if root is not None:
                z[:, idx] = z[:, idx] @ root
        np.clip(WP._std_normal_cdf(z), 1e-12, 1 - 1e-12, out=z)               # z is now u
        for lv, cols, vals in gv:
            z[:, cols] = ppf_group(lv, vals, z[:, cols])                        # ... and now each starter's points
        pre = z @ own
        totals[lo:lo + c] = np.maximum(pr["fixed"][None, :] + z @ own_live, 0.0)
        s1 += pre.sum(axis=0)
        s2 += (pre * pre).sum(axis=0)
        del z, pre
    var = np.maximum(s2 / n - (s1 / n) ** 2, 0.0)
    return {**out, "totals": totals, "spread": np.sqrt(var)}


# ------------------------------------------------------------------------------------------- the season
def seasons_for(teams: int, weeks: int, starters: int) -> int:
    """How many seasons a league of this shape gets: ``SEASONS`` (10,000), fewer when teams × max(weeks, starters per
    team) would take more than ``WORK_BUDGET`` cells (in 500s, never under 1,000)."""
    per = max(1, int(teams)) * max(1, int(weeks), int(starters))
    n = WORK_BUDGET // per // 500 * 500
    return int(min(SEASONS, max(MIN_SEASONS, n)))


def season_totals(teams: Sequence[int], weeks: Sequence[int], mean: Mapping[tuple[int, int], float],
                  cv: Mapping[int, float], level: Mapping[int, float], *, first: np.ndarray | None = None,
                  n: int = SEASONS, seed: int | Sequence[int] = SEED, k: float = WP.WEEK_SHRINK,
                  drift: float = DRIFT) -> np.ndarray:
    """(n, T, W) points per simulated season, team and week (one chunk: ``simulate`` calls it per chunk). ``first``
    (n × T): the first week's draws (the copula); without it the first week is drawn like the others with no drift. A
    later week h weeks after the first: its projected best lineup ``mean[(t, w)]`` + N(0, (cv_t · mean / k)²) + the
    team's drift (a random walk, step ``drift`` · ``level[t]``, h steps). Floored at 0."""
    T, W = len(teams), len(weeks)
    rng = np.random.default_rng(seed + 1 if isinstance(seed, int) else [*seed, 1])
    mu = np.array([[mean.get((int(t), int(w)), 0.0) for w in weeks] for t in teams], dtype=float)       # T × W
    sd = np.array([max(0.0, cv.get(int(t), 0.0)) for t in teams])[:, None] * mu / k
    out = rng.standard_normal((n, T, W))
    out *= sd[None, :, :]
    steps = rng.standard_normal((n, T, W))
    steps *= (drift * np.array([max(0.0, level.get(int(t), 0.0)) for t in teams]))[None, :, None]
    steps[:, :, 0] = 0.0                                      # the first week left: today's lineups, no drift
    np.cumsum(steps, axis=2, out=steps)
    out += steps
    del steps
    out += mu[None, :, :]
    if first is not None and W:
        out[:, :, 0] = first
    np.maximum(out, 0.0, out=out)
    return out


def byes_for(spots: int | None) -> int:
    """First-round byes of a single-elimination bracket of ``spots`` teams: 2^⌈log₂ spots⌉ − spots (6 → 2, 4 → 0)."""
    if not spots or spots < 2:
        return 0
    return int(2 ** math.ceil(math.log2(spots)) - spots)


def clinch_flags(teams: Sequence[int], wins: Mapping[int, float], left: Mapping[int, int], spots: int) -> dict[int, str | None]:
    """"clinched" when fewer than ``spots`` other teams can reach the team's wins today (a tie on wins could go either way
    on points), "eliminated" when at least ``spots`` others already have more wins than it can reach; else None. Wins
    alone, ignoring who plays whom: a sufficient proof, never a guess."""
    out: dict[int, str | None] = {}
    for t in teams:
        w, best = float(wins.get(t, 0.0)), float(wins.get(t, 0.0)) + left.get(t, 0)
        reach = sum(1 for u in teams if u != t and float(wins.get(u, 0.0)) + left.get(u, 0) >= w)
        past = sum(1 for u in teams if u != t and float(wins.get(u, 0.0)) > best)
        out[t] = "clinched" if reach < spots else "eliminated" if past >= spots else None
    return out


def threshold(diff: np.ndarray, k: float = WP.WEEK_SHRINK) -> tuple[float | None, float, float]:
    """The week's odds' calibration of one game from every draw's raw margin ``diff``: p_raw = P(diff > 0) (a tie
    half), p = ``shrink_week``(p_raw, k), and the margin's (1 − p) quantile ``q`` side a must beat (None: a settled game
    or no shrink — the raw result stands). Returns (q, p_raw, p)."""
    raw = (diff > 0) + 0.5 * (diff == 0)
    p_raw = float(raw.mean())
    p = WP.shrink_week(p_raw, k)
    if p <= 0.0 or p >= 1.0 or float(diff.std()) == 0.0 or abs(p - p_raw) < 1e-12:
        return None, p_raw, p
    return float(np.quantile(diff, 1.0 - p)), p_raw, p


def _result(diff: np.ndarray, q: float | None) -> np.ndarray:
    return (diff > 0) + 0.5 * (diff == 0) if q is None else (diff > q).astype(float)


def calibrated_result(diff: np.ndarray, k: float = WP.WEEK_SHRINK) -> tuple[np.ndarray, float, float]:
    """Side a's result per draw (1 win, ½ tie, 0 loss) from its raw margin ``diff``, with the week's odds' calibration:
    a wins the draws whose margin is above the margin's (1 − p) quantile (``threshold``). Returns (results, p_raw, p)."""
    q, p_raw, p = threshold(diff, k)
    return _result(diff, q).astype(float), p_raw, p


class _Tally:
    """The seasons' answer kept as counts, never per season: per team a histogram of final wins (in halves), the
    distribution of final places, the summed points for."""

    def __init__(self, teams: Sequence[int], wins0: Mapping[int, float], cap: float):
        self.T = len(teams)
        self.halves = int(round(2 * cap)) + 1
        self.hist = np.zeros((self.T, self.halves), dtype=np.int64)
        self.place = np.zeros((self.T, self.T), dtype=np.int64)
        self.pf = np.zeros(self.T)
        self.title = np.zeros(self.T, dtype=np.int64)          # ---- IO-2: seasons won (the bracket played out)
        self.titled = False
        self.n = 0

    def add(self, wins: np.ndarray, pf: np.ndarray) -> None:
        c = wins.shape[0]
        key = wins * 1e6 + pf                                 # wins first, then points for (points < 1e6)
        order = np.argsort(-key, axis=1, kind="stable")
        rank = np.empty_like(order)
        rank[np.arange(c)[:, None], order] = np.arange(self.T)[None, :]
        h = np.clip(np.rint(wins * 2).astype(np.int64), 0, self.halves - 1)
        for i in range(self.T):
            self.hist[i] += np.bincount(h[:, i], minlength=self.halves)
            self.place[i] += np.bincount(rank[:, i], minlength=self.T)
        self.pf += pf.sum(axis=0)
        self.n += c

    def row(self, i: int, wins0: float, games_left: int, spots: int | None, byes: int) -> dict:
        n, h = self.n, self.hist[i]
        halves = np.arange(self.halves) / 2.0
        cdf = np.cumsum(h)
        mean = float((h * halves).sum() / n)
        return {"wins_mean": round(mean, 2), "wins_p10": float(halves[np.searchsorted(cdf, 0.10 * n)]),
                "wins_p90": float(halves[np.searchsorted(cdf, 0.90 * n)]), "games_left": int(games_left),
                "wins_left_mean": round(mean - wins0, 2), "points_for_mean": round(float(self.pf[i] / n), 1),
                "playoff": None if not spots else round(float(self.place[i, :spots].sum() / n), 4),
                "top_seed": round(float(self.place[i, 0] / n), 4),
                "bye": None if not spots or not byes else round(float(self.place[i, :byes].sum() / n), 4),
                "rank_mean": round(float((self.place[i] * np.arange(self.T)).sum() / n) + 1, 2),
                "title": round(float(self.title[i] / n), 4) if self.titled else None}      # ---- IO-2


# ---- IO-2 (Wave I-O): the playoff bracket, played out in every simulated season (title odds)
def bracket_order(size: int) -> list[int]:
    """The seeds' places in a single-elimination bracket of ``size`` (a power of two): 8 → [1, 8, 4, 5, 2, 7, 3, 6]
    (adjacent places meet; a seed past the playoff spots is a bye)."""
    order = [1, 2]
    while len(order) < size:
        m = 2 * len(order)
        order = [x for sd in order for x in (sd, m + 1 - sd)]
    return order[:max(1, size)] if size > 1 else [1]


def bracket_rounds(settings: Mapping, spots: int) -> list[list[int]]:
    """The weeks of each playoff round, from Sleeper's settings: ⌈log₂ spots⌉ rounds from ``playoff_week_start``;
    ``playoff_round_type`` 0 = one week a round, 1 = the final over two weeks, 2 = every round over two weeks
    (``anyleague.ros_window``'s reading)."""
    pws = int(settings.get("playoff_week_start") or 0)
    rounds = math.ceil(math.log2(spots)) if spots and spots > 1 else 0
    rtype = int(settings.get("playoff_round_type") or 0)
    out, w = [], pws
    for r in range(rounds):
        k = 2 if rtype == 2 or (rtype == 1 and r == rounds - 1) else 1
        out.append(list(range(w, w + k)))
        w += k
    return out


def play_bracket(wins: np.ndarray, pf: np.ndarray, ptot: np.ndarray, bracket: Mapping, spots: int) -> np.ndarray:
    """The champion's team index per season (c,). Seeds: wins, then points for (the regular season's order, as the
    playoff odds count it); round 1 by ``bracket_order`` (the top seeds' byes); a round's score = the team's points over
    the round's weeks (``ptot``: c × T × playoff weeks, in ``bracket["rounds"]`` order); a tie goes to the higher seed.
    ``reseed``: before every later round the teams left are paired highest seed against lowest (Sleeper's
    ``playoff_seed_type`` 1 — the house dynasty's 2021, 2022 and 2024 brackets pair exactly so); otherwise the bracket is fixed."""
    c, T = wins.shape
    order = np.argsort(-(wins * 1e6 + pf), axis=1, kind="stable")[:, :spots]     # c × spots: team index by seed
    size = 2 ** math.ceil(math.log2(spots))
    cur = np.tile(np.array([sd if sd <= spots else 0 for sd in bracket_order(size)]), (c, 1))     # seed numbers; 0 = bye
    rows = np.arange(c)[:, None]
    col = 0
    for r, wk in enumerate(bracket["rounds"]):
        if cur.shape[1] < 2:                                                      # the final is played
            break
        pts = ptot[:, :, col:col + len(wk)].sum(axis=2)                           # c × T
        col += len(wk)
        if r > 0 and bracket.get("reseed"):
            srt = np.sort(cur, axis=1)
            cur = srt[:, [p - 1 for p in bracket_order(srt.shape[1])]]
        a, b = cur[:, 0::2], cur[:, 1::2]
        ta = order[rows, np.maximum(a, 1) - 1]
        tb = order[rows, np.maximum(b, 1) - 1]
        pa, pb = pts[rows, ta], pts[rows, tb]
        a_wins = (b == 0) | ((a != 0) & ((pa > pb) | ((pa == pb) & (a < b))))
        cur = np.where(a_wins, a, b)
    return order[np.arange(c), cur[:, 0] - 1]
# ---- end IO-2


def simulate(teams: Sequence[int], weeks: Sequence[int], mean: Mapping[tuple[int, int], float], cv: Mapping[int, float],
             level: Mapping[int, float], games: Mapping[int, Sequence[tuple[int, int]]], wins0: Mapping[int, float],
             pf0: Mapping[int, float], spots: int | None, byes: int = 0, *, first: np.ndarray | None = None,
             n: int = SEASONS, seed: int = SEED, k: float = WP.WEEK_SHRINK, drift: float = DRIFT,
             calibrate_first: bool = True, bracket: Mapping | None = None) -> dict:
    """``n`` seasons in chunks (``chunk_rows`` of teams × weeks): each chunk drawn (``season_totals``), played out and
    counted (``_Tally``), then dropped — memory is flat in the season count apart from ``first`` (n × T). The first
    week's games are decided with the week's odds' calibration (``threshold`` over all of ``first``'s draws); later
    weeks by the points drawn (already widened). Returns per team the final wins (mean, P10, P90), points for (mean),
    playoff / top-seed / bye shares and the mean place; per game of the first week P(a wins) (raw and calibrated)."""
    T, W = len(teams), len(weeks)
    ix = {int(t): i for i, t in enumerate(teams)}
    gl = {int(w): [(a, b) for a, b in games.get(int(w), ()) if a in ix and b in ix] for w in weeks}
    played = np.zeros(T, dtype=int)
    for w in weeks:
        for a, b in gl[int(w)]:
            played[ix[a]] += 1
            played[ix[b]] += 1
    w0 = np.array([float(wins0.get(int(t), 0.0)) for t in teams])
    p0 = np.array([float(pf0.get(int(t), 0.0)) for t in teams])
    tally = _Tally(teams, wins0, float((w0 + played).max()) if T else 0.0)
    q0: dict[tuple[int, int], float | None] = {}
    first_rows: list[dict] = []
    if W:
        for a, b in gl[int(weeks[0])]:
            if first is not None and calibrate_first:
                d = first[:, ix[a]] - first[:, ix[b]]
                q, p_raw, _p = threshold(d, k)
                q0[(a, b)] = q
                first_rows.append({"week": int(weeks[0]), "a": int(a), "b": int(b),
                                   "p": round(float(_result(d, q).mean()), 4), "p_raw": round(p_raw, 4)})
    # ---- IO-2: title odds — the playoff weeks drawn in the same seasons (after the regular season's weeks: the drift
    # carries on), the bracket played out per season (play_bracket)
    pweeks = [int(w) for r in (bracket or {}).get("rounds", ()) for w in r]
    all_weeks = [*weeks, *pweeks] if bracket and spots else list(weeks)
    tally.titled = bool(bracket and spots and W)
    rows = chunk_rows(T * max(1, len(all_weeks)))
    seen: dict[tuple[int, int], float] = {}
    for ci, lo in enumerate(range(0, n, rows)):
        c = min(rows, n - lo)
        tot = season_totals(teams, all_weeks, mean, cv, level, first=None if first is None else first[lo:lo + c], n=c,
                            seed=[seed, ci], k=k, drift=drift)
        wins = np.tile(w0, (c, 1))
        for wi, w in enumerate(weeks):
            for a, b in gl[int(w)]:
                d = tot[:, ix[a], wi] - tot[:, ix[b], wi]
                res = _result(d, q0.get((a, b))) if wi == 0 and (a, b) in q0 else (d > 0) + 0.5 * (d == 0)
                wins[:, ix[a]] += res
                wins[:, ix[b]] += 1.0 - res
                if wi == 0 and (a, b) not in q0:
                    seen[(a, b)] = seen.get((a, b), 0.0) + float(res.sum())
        pf_c = p0[None, :] + tot[:, :, :W].sum(axis=2)
        tally.add(wins, pf_c)
        if tally.titled:                                                    # ---- IO-2
            champ = play_bracket(wins, pf_c, tot[:, :, W:], bracket, spots)
            tally.title += np.bincount(champ, minlength=T)
        del tot, wins
    if W and not q0:
        first_rows = [{"week": int(weeks[0]), "a": int(a), "b": int(b), "p": round(seen.get((a, b), 0.0) / n, 4), "p_raw": None}
                      for a, b in gl[int(weeks[0])]]
    out = {int(t): tally.row(ix[int(t)], float(w0[ix[int(t)]]), int(played[ix[int(t)]]), spots, byes) for t in teams}
    return {"teams": out, "first_week": first_rows, "seasons": int(n)}


def play_out(teams: Sequence[int], weeks: Sequence[int], totals: np.ndarray, games: Mapping[int, Sequence[tuple[int, int]]],
             wins0: Mapping[int, float], pf0: Mapping[int, float], spots: int | None, byes: int = 0, *,
             calibrate_first: bool = True, k: float = WP.WEEK_SHRINK) -> dict:
    """Already-drawn seasons (``totals``, n × T × W: a test's hand-built league) played out and counted as ``simulate``
    does — the first week's games with the week's odds' calibration over these draws (``calibrate_first``)."""
    T = len(teams)
    ix = {int(t): i for i, t in enumerate(teams)}
    n = totals.shape[0]
    gl = {int(w): [(a, b) for a, b in games.get(int(w), ()) if a in ix and b in ix] for w in weeks}
    played = np.zeros(T, dtype=int)
    w0 = np.array([float(wins0.get(int(t), 0.0)) for t in teams])
    wins = np.tile(w0, (n, 1))
    first: list[dict] = []
    for wi, w in enumerate(weeks):
        for a, b in gl[int(w)]:
            d = totals[:, ix[a], wi] - totals[:, ix[b], wi]
            if wi == 0 and calibrate_first:
                res, p_raw, _p = calibrated_result(d, k)
            else:
                res, p_raw = (d > 0) + 0.5 * (d == 0), None
            wins[:, ix[a]] += res
            wins[:, ix[b]] += 1.0 - res
            played[ix[a]] += 1
            played[ix[b]] += 1
            if wi == 0:
                first.append({"week": int(w), "a": int(a), "b": int(b), "p": round(float(res.mean()), 4),
                              "p_raw": None if p_raw is None else round(p_raw, 4)})
    tally = _Tally(teams, wins0, float((w0 + played).max()) if T else 0.0)
    tally.add(wins, np.array([float(pf0.get(int(t), 0.0)) for t in teams])[None, :] + totals.sum(axis=2))
    out = {int(t): tally.row(ix[int(t)], float(w0[ix[int(t)]]), int(played[ix[int(t)]]), spots, byes) for t in teams}
    return {"teams": out, "first_week": first, "seasons": int(n)}


# ------------------------------------------------------------------------------------------- reading a league
def _ordinal(k: int) -> str:
    return D._ordinal(k)


def order_rank(keys: Mapping[int, tuple]) -> dict[int, int]:
    """1 = the largest key (wins, then points for); equal keys share the better rank."""
    out = {}
    for r, k in keys.items():
        out[r] = 1 + sum(1 for o in keys.values() if o > k)
    return out


def gap_words(wins: int, losses: int, ties: int, standing: int, pf_rank: int, n: int) -> str | None:
    """"3–1 on the 8th-most points: a soft schedule so far" when the record's rank and the points' rank are far apart
    (3 places or more, a quarter of the league in a big one); None otherwise."""
    if n < 4 or abs(standing - pf_rank) < max(3, n // 4):
        return None
    rec = f"{wins}–{losses}" + (f"–{ties}" if ties else "")
    most = "the most points" if pf_rank == 1 else "the fewest points" if pf_rank == n else f"the {_ordinal(pf_rank)}-most points"
    kind = "a soft schedule so far" if standing < pf_rank else "a hard schedule so far"
    return f"{rec} on {most}: {kind}"


def _standings_frame(st: pd.DataFrame, names: Mapping[int, dict]) -> pd.DataFrame:
    cols = ["roster_id", "wins", "losses", "ties", "points_for", "points_against"]
    if st is None or st.empty:
        return pd.DataFrame([{"roster_id": int(r), "wins": 0, "losses": 0, "ties": 0, "points_for": 0.0, "points_against": 0.0}
                             for r in names], columns=cols)
    f = st[[c for c in cols if c in st.columns]].copy()
    for c in cols:
        if c not in f.columns:
            f[c] = 0
    f["roster_id"] = f["roster_id"].astype(int)
    have = set(f["roster_id"])
    extra = [{"roster_id": int(r), "wins": 0, "losses": 0, "ties": 0, "points_for": 0.0, "points_against": 0.0}
             for r in names if int(r) not in have]
    return pd.concat([f, pd.DataFrame(extra, columns=cols)], ignore_index=True) if extra else f


DIM_SQL = "select playoff_week_start, playoff_teams from analytics.dim_league_season where league_id = %s"


def _league_inputs(league_id: str, is_house: bool) -> dict:
    """The league's settings, names, standings so far and the provider's key: {"lg", "lid", "names", "standings",
    "played" (the last week counted in the standings), "season"}."""
    client = A.sleeper()
    if is_house:
        names = D._members(league_id)
        st = query(D.STANDINGS_SQL, (league_id,))
        apw = query(D.ALL_PLAY_WEEK_SQL, (league_id,))
        played = int(apw["week"].max()) if not apw.empty else 0
        degraded = False
        try:
            lg = client.league(A.check_id(league_id)) or {}
        except (A.SleeperUnavailable, A.LeagueNotFound):        # ---- IO-2 fix round: busy is not caught (503)
            lg, degraded = {}, True                              # the nightly's copy; this answer is not cached
        if not (lg.get("settings") or {}).get("playoff_week_start"):     # Sleeper not answering: the nightly's copy
            ls = query(DIM_SQL, (league_id,))
            if not ls.empty and pd.notna(ls["playoff_week_start"].iloc[0]):
                got = {k: int(ls[k].iloc[0]) for k in ("playoff_week_start", "playoff_teams") if pd.notna(ls[k].iloc[0])}
                lg = {**lg, "settings": {**(lg.get("settings") or {}), **got}}
        return {"lg": lg, "lid": str(league_id), "names": names, "standings": _standings_frame(st, names),
                "played": played, "season": int(cards.league_season(league_id)), "degraded": degraded}
    lg, rosters, users = D._sleeper_league(league_id)
    names = A.team_names(rosters, users)
    last = int((lg.get("settings") or {}).get("last_scored_leg") or 0)
    weeks = D._od(client.season_matchups, lg["league_id"], last) if last > 0 else {}
    st, _ap, apw = D.od_league_marts(lg, rosters, users, weeks)
    played = int(apw["week"].max()) if apw is not None and not apw.empty else 0
    return {"lg": lg, "lid": str(lg["league_id"]), "names": names, "standings": _standings_frame(st, names),
            "played": played, "season": int(lg["season"])}


def schedule(client, lid: str, weeks: Sequence[int]) -> tuple[dict[int, list[tuple[int, int]]], int | None]:
    """{week: [(a, b), …]} from the provider's matchups (a double header's two games both listed), and the first week
    with no pairings (None when every week has some). Read through the provider client (its own matchups cache is the
    one the week's odds fill) and kept per league in ``_schedules`` for ``SCHEDULE_TTL_S``: a week already kept is
    never asked for again (pairings do not change)."""
    kept: dict[int, list[tuple[int, int]]] = dict(_schedules.get(str(lid)) or {})
    out: dict[int, list[tuple[int, int]]] = {}
    missing = None
    for w in weeks:
        if int(w) in kept:
            out[int(w)] = kept[int(w)]
            continue
        try:
            ms = client.matchups(lid, int(w))
        except (A.SleeperBusy, A.SleeperUnavailable):
            # ---- IO-2 fix round (the review's M2): our budget refused, or the provider failed — not "no schedule".
            # The weeks read so far are kept; the build stops (503 busy / 502), nothing is cached or stored.
            if kept:
                _schedules.put(str(lid), kept)
            raise
        except A.LeagueNotFound:
            missing = int(w)
            break
        by: dict = {}
        for m in ms or []:
            if m.get("matchup_id") is not None and m.get("roster_id") is not None:
                by.setdefault(m["matchup_id"], set()).add(int(m["roster_id"]))
        pairs = [tuple(sorted(r)) for _mid, r in sorted(by.items(), key=lambda kv: str(kv[0])) if len(r) == 2]
        if not pairs:
            missing = int(w)
            break
        out[int(w)] = kept[int(w)] = [(int(a), int(b)) for a, b in pairs]
    if kept:
        _schedules.put(str(lid), kept)
    return out, missing


def week_sides(lid: str, is_house: bool, season: int, week: int, rids: Sequence[int]) -> tuple[dict[int, list[dict]] | None, str | None]:
    """Every roster's starters for ``week`` as the week's odds read them (``myweek.week_odds``: the roster contexts, the
    games already in at their points), or (None, why)."""
    client = A.sleeper()
    if is_house:
        ctxs = availability.contexts(lid, rids, week, house=True)
    else:
        ctxs = {r: availability.roster_context(lid, r, week, house=False, client=client) for r in rids}
    scored = MW.scored_teams(season, week)
    scored = MW.live_scored(lid, week, scored, is_house)
    points: dict[str, float] | None = {}
    if scored:
        if is_house:
            df = query(MW.OBSERVED_SQL, (lid, int(season), int(week), list(rids)))
            points = {str(r.sleeper_player_id): float(r.points) for r in df.itertuples() if r.points is not None and not pd.isna(r.points)}
        else:
            from .ondemand import week_points
            points = week_points(client, lid, week, rids)
        points = points or None
    sides = {}
    for r in rids:
        c = ctxs.get(r)
        sides[int(r)] = MW.win_starters(c.rows if c is not None else None)
        if not MW.with_actuals(sides[int(r)], scored, points):
            return None, MW.WIN_NO_LIVE
    return sides, None


def _stamp() -> tuple:
    def iso(d):
        return None if d is None else d.isoformat()
    return (iso(availability.build_time()), iso(availability.checked_at()))


def outlook(league_id: str, team: int | None = None, *, source: str | None = None, seasons: int = SEASONS,
            part: str | None = None) -> dict:
    """``GET /api/league/outlook``: the power rankings and the rest of the season (module docstring). The key is made
    canonical first (``platforms.check_key``: " 1389…104", "1389…104\t" and "MFL:70587" are the leagues they name), so
    the house check and the cache key never see a padded spelling; a key that names no league is 404.
    ``part="power"`` (IO-2): the power rankings alone, no simulation (``outlook.pending`` true)."""
    try:
        league_id = A.check_id(league_id)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc)) from exc
    is_house = D.house(league_id, source)
    key = (str(league_id), is_house, int(seasons), _stamp(), part)          # ---- IO-2: the part
    hit = None
    if part == "power":                                                     # ---- IO-2: the whole answer has it
        hit = _cache.get((str(league_id), is_house, int(seasons), _stamp(), None))
    if hit is None:
        hit = _cache.get(key)
    if hit is None:
        # ---- IO-2 fix round (the review's M2): a build during which a provider call was refused (this client's share
        # spent, or everyone's budget) or failed over to the nightly's copy is NOT cached, NOT stored and leaves no card:
        # another client must never get it; incomplete, the requester gets 503 busy (the screen asks again)
        # ---- IP-5 fix round (review M2): only what THIS build met — its own watch (provider_trouble: the clients note
        # each refusal / failure on the request's context) — never the process's counters, which any client's refusal
        # moved (one address with its share spent made every build "degraded": uncached, 429s at the simulation lock)
        with provider_trouble.watch() as w:
            try:
                built = _build(str(league_id), is_house, source, int(seasons), part=part)
            except (A.SleeperBusy, A.SleeperUnavailable) as exc:          # refused (503) / the provider failed (502)
                _forget_context(str(league_id), is_house)
                if isinstance(exc, A.SleeperBusy):
                    raise
                from .ondemand import SleeperDown
                raise SleeperDown(str(exc)) from exc
        degraded = bool(built.pop("degraded", False)) or w.troubled
        if w.stale and not degraded:              # built on a held answer past its TTL: served, kept for nobody
            _forget_context(str(league_id), is_house)
            built["power"]["kept"] = "not_kept"
            hit = built
        elif degraded:
            # ---- end IP-5
            _forget_context(str(league_id), is_house)
            if built["power"].get("note") or (part is None and not built["outlook"].get("available")
                                               and built["outlook"].get("reason")):
                raise A.SleeperBusy("busy, try again in a minute")
            built["power"]["kept"] = "not_kept"
            hit = built
        else:
            _keep(built, is_house, part)
            hit = _cache.put(key, built, ttl=TTL_S["house" if is_house else "sleeper"])
    if team is not None and int(team) not in {r["roster_id"] for r in hit["power"]["rows"]}:
        raise NotFound(f"no team {team} in this league")
    return _mine(hit, team)


# ---- IO-2 fix round: refusals, the context a refused build may have left, the snapshot and the card after the verdict
def _refusals() -> int:
    """Provider calls refused so far in this process: every client's share (IO-4's ``provider_share``) and the global
    buckets (Sleeper's, MFL's). A build compares it before and after (another client's refusal during the build only
    costs a cache miss)."""
    n = 0
    try:
        info = provider_share.shares().info()
        n += sum(int(v.get("refused", 0) or 0) for v in info.values() if isinstance(v, dict))
    except Exception:  # noqa: BLE001
        pass
    try:
        r = A.sleeper()
        n += int(getattr(getattr(r.sleeper, "bucket", None), "refused", 0) or 0)
        n += int(getattr(getattr(getattr(r, "_mfl_client", None), "bucket", None), "refused", 0) or 0)
    except Exception:  # noqa: BLE001
        pass
    return n                  # ---- IP-5 fix round: no longer read by outlook() (its own watch; review M2)


def _forget_context(lid: str, is_house: bool) -> None:
    """The board contexts a refused build may have left half-read (``window_board``'s rest-of-season frame is kept on
    the context): dropped, so the next build reads them again."""
    for k in (("outlook_context", lid), ("trade_context", lid, is_house)):
        try:
            D._memo_cache.pop(k)
        except Exception:  # noqa: BLE001
            pass


def _keep(ans: dict, is_house: bool, part: str | None) -> None:
    """A clean build: its row offered to the store (a whole build only) and its preview card kept."""
    lid, rows = str(ans["league_id"]), ans["power"]["rows"]
    if part is None and rows:
        try:
            offered = S.offer(S.snapshot(ans, league_name=ans.get("league_name"), week=int(ans["week"]),
                                         built_at=clock.now()), house=is_house)
        except Exception:  # noqa: BLE001 - the store is never load-bearing
            offered = "failed"
        ans["power"]["kept"] = offered
        if offered == "queued" and ans["power"]["movement"] is None and ans["power"]["movement_note"] == WAIT_NOTE:
            ans["power"]["movement_note"] = FIRST_NOTE
    top = [{"team": r["team_name"], "per_week": r["per_week"]} for r in rows[:5]]
    odds = {o["roster_id"]: o.get("playoff") for o in ans["outlook"].get("rows") or []}
    for t, r in zip(top, rows[:5], strict=False):
        t["playoff"] = odds.get(r["roster_id"])
    S.remember_card(lid, {"name": ans.get("league_name"), "week": ans.get("week"), "top": top})
# ---- end IO-2 fix round


def _mine(ans: dict, team: int | None) -> dict:
    out = {**ans, "roster_id": team}
    out["power"] = {**ans["power"], "rows": [{**r, "mine": team is not None and r["roster_id"] == int(team)} for r in ans["power"]["rows"]]}
    if ans["outlook"].get("rows"):
        out["outlook"] = {**ans["outlook"], "rows": [{**r, "mine": team is not None and r["roster_id"] == int(team)}
                                                     for r in ans["outlook"]["rows"]]}
    return out


def _season_outlook(ol: dict, out_rows: list, left_games: dict, timings: dict, *, lid: str, is_house: bool, season: int,
                    settings: dict, platform: str, played: int, weeks, rids: list[int], lineup: dict, level: dict,
                    rec: dict, pf: dict, seasons: int) -> str | None:
    """The rest of the season into ``ol`` / ``out_rows`` (and the schedule left into ``left_games``), or the reason
    there is none. Every check that can say no runs before anything is simulated; the simulation itself holds the
    process-wide lock (``_SIM``)."""
    t3 = time.perf_counter()
    pws = int(settings.get("playoff_week_start") or 0)
    if not pws:
        return "this league's regular-season length is not known from its settings"
    remaining = list(range(played + 1, pws))
    if not remaining:
        return "the regular season is over"
    if len(rids) > MAX_TEAMS:
        return f"this league has {len(rids)} teams: the outlook simulates leagues of up to {MAX_TEAMS}"
    if len(remaining) > MAX_WEEKS:
        return f"{len(remaining)} regular-season weeks are left: the outlook simulates up to {MAX_WEEKS}"
    board_weeks = set(int(w) for w in weeks)
    w0 = remaining[0]
    first_wk = int(cards.decision_week(season) or 0) if season else 0
    uncovered = [w for w in remaining[1:] if w not in board_weeks]
    if w0 not in board_weeks and w0 != first_wk:
        return f"week {w0}'s results are not final yet: the outlook returns once the league has scored it"
    if uncovered:
        return f"no projections for week {uncovered[0]} yet"
    games, missing = schedule(A.sleeper(), lid, remaining)
    if missing is not None:
        return f"the schedule for week {missing} is not available from the league"
    for w in remaining if not any(left_games.values()) else ():   # the schedule left (IO-2: unless _build read it)
        for a, b in games.get(w, ()):
            left_games.setdefault(a, []).append(b)
            left_games.setdefault(b, []).append(a)
    sides, why = week_sides(lid, is_house, season, w0, rids)
    if sides is None:
        return why
    most = max((len(v) for v in sides.values()), default=0)
    if most > MAX_STARTERS:
        return f"a lineup here has {most} starters: the outlook simulates up to {MAX_STARTERS}"
    pr = prepare(sides)
    if (pr["ranged_share"] < MW.MIN_RANGED_SHARE).any() or not pr["dists"]:      # the week's odds' rule, before a draw
        return MW.WIN_NO_RANGE
    bracket, title_reason = title_bracket(settings, platform, {w for (_r, w) in lineup})       # ---- IO-2
    pweeks = sum(len(r) for r in bracket["rounds"]) if bracket else 0
    n = min(int(seasons), seasons_for(len(rids), len(remaining) + pweeks, most))
    timings["inputs_ms"] = round((time.perf_counter() - t3) * 1000, 1)       # schedule + rosters
    if not _SIM.acquire(timeout=BUSY_WAIT_S):
        raise Busy()
    try:
        t4 = time.perf_counter()
        fw = first_week_draws(prep=pr, n=n)
        exp = dict(zip(fw["teams"], fw["expected"], strict=True))
        spr = dict(zip(fw["teams"], fw["spread"], strict=True))
        cvs = {t: spr[t] / exp[t] for t in fw["teams"] if exp[t] > 0 and spr[t] > 0}
        if not cvs:
            return MW.WIN_NO_RANGE
        med = float(np.median(list(cvs.values())))
        cv = {t: cvs.get(t, med) for t in rids}
        means = {**lineup, **{(t, w0): float(exp[t]) for t in fw["teams"]}}
        first = fw["totals"][:, [fw["teams"].index(t) for t in rids]]
        del fw
        spots = int(settings.get("playoff_teams") or 0) or None
        playoff_reason = None
        if platform == "mfl":
            playoff_reason = "MyFantasyLeague does not share how many teams make the playoffs, so playoff odds are left out"
        elif int(settings.get("divisions") or 0) > 1:
            playoff_reason = "this league has divisions: division winners' places are not simulated"
        elif not spots:
            playoff_reason = "this league's playoff spots are not in its settings"
        if playoff_reason:
            spots = None
        byes = byes_for(spots)
        wins0 = {r: rec[r][0] + 0.5 * rec[r][2] for r in rids}
        if playoff_reason:                                                         # ---- IO-2
            bracket, title_reason = None, None
        res = simulate(rids, remaining, means, cv, level, games, wins0, pf, spots, byes, first=first, n=n,
                       bracket=bracket)
        timings["simulation_ms"] = round((time.perf_counter() - t4) * 1000, 1)
    finally:
        _SIM.release()
    flags = clinch_flags(rids, wins0, {r: len(left_games.get(r, [])) for r in rids}, spots) if spots else {}
    for r in rids:
        row = {"roster_id": r, **res["teams"][r], "status": flags.get(r)}
        if flags.get(r) == "clinched":
            row["playoff"] = 1.0
        elif flags.get(r) == "eliminated":
            row["playoff"], row["bye"], row["top_seed"] = 0.0, (0.0 if byes else None), 0.0
            if row.get("title") is not None:                                       # ---- IO-2
                row["title"] = 0.0
        out_rows.append(row)
    ol.update({"available": True, "weeks": remaining, "seasons": n, "playoff_teams": spots,
               "byes": byes if spots else None, "playoff_reason": playoff_reason, "first_week": res["first_week"],
               "first_week_number": w0,
               # ---- IO-2: title odds (Sleeper, the bracket readable) or why not
               "title": bool(bracket and spots), "title_reason": title_reason,
               "bracket": ({"rounds": bracket["rounds"], "reseed": bracket["reseed"]} if bracket and spots else None)})
    return None


# ---- IO-2 (Wave I-O): title odds — which leagues, which bracket
def title_bracket(settings: Mapping, platform: str, board_weeks: set) -> tuple[dict | None, str | None]:
    """({"rounds": [[weeks], …], "reseed": bool}, None) for a Sleeper league whose bracket is readable from its
    settings (playoff teams, start week, round type; ``playoff_seed_type`` 1 = re-seeded each round), or (None, why)."""
    spots = int(settings.get("playoff_teams") or 0)
    if platform != "sleeper":
        return None, "the playoff bracket is read only from Sleeper's settings"
    if "playoff_seed_type" not in settings:                     # ---- IO-2 fix round: Sleeper's own settings only
        return None, "the playoff bracket's rules are not readable right now"
    if int(settings.get("divisions") or 0) > 1 or spots < 2:
        return None, "the playoff bracket is not simulated for this league"
    rounds = bracket_rounds(settings, spots)
    missing = [w for r in rounds for w in r if int(w) not in board_weeks]
    if not rounds or missing:
        return None, f"no projections for playoff week {missing[0] if missing else '?'} yet"
    return {"rounds": rounds, "reseed": int(settings.get("playoff_seed_type") or 0) == 1}, None


# ---- IO-2 (Wave I-O): the board without the trade market, the schedule left before the simulation, the movement
def _context(league_id: str, source: str | None, is_house: bool):
    """The lineups' board: a house league's (or any league's already built) trade context; otherwise a market-free
    one kept as long (``market=False``: no free agents, no later weeks priced for season value — the outlook reads the
    board's lineups and the rest-of-season board only). MFL 70587 cold: 3.7 s → 1.2 s for the context."""
    if is_house:
        return D.trade_context(league_id, source)
    full = D._memo_cache.get(("trade_context", str(league_id), False))
    if full is not None:
        return full
    return D._memo(("outlook_context", str(league_id)), False, lambda: D.TradeContext(league_id, source, market=False))


def _schedule_left(lid: str, played: int, settings: Mapping, n_teams: int) -> dict[int, list[int]]:
    """{roster: [opponents left]} from the remaining regular-season pairings; {} when they are not all readable or
    the league is beyond the outlook's limits (the season block says why)."""
    pws = int(settings.get("playoff_week_start") or 0)
    remaining = list(range(played + 1, pws)) if pws else []
    if not remaining or n_teams > MAX_TEAMS or len(remaining) > MAX_WEEKS:
        return {}
    games, missing = schedule(A.sleeper(), lid, remaining)
    if missing is not None:
        return {}
    left: dict[int, list[int]] = {}
    for w in remaining:
        for a, b in games.get(w, ()):
            left.setdefault(a, []).append(b)
            left.setdefault(b, []).append(a)
    return left


MOVED_NOTE = "▲ ▼: places moved since the ranking kept before week {week}."
FIRST_NOTE = "Movement shows from next week: this week's ranking is kept."
WAIT_NOTE = ("No movement arrows yet: each week's ranking is kept before its first game, and the arrows compare with "
             "last week's.")


def _movement(ans: dict, *, snap_week: int, offered: str | None) -> None:
    """Last week's stored ranking → ``moved`` per power row (places up +, down −; None: not in last week's) and
    ``playoff_change`` per outlook row (points of percentage); the note says which. Only ever a stored row."""
    lid = str(ans["league_id"])
    on = S.ready() and S.shareable(lid)
    st = S.stored(lid, int(ans["season"]), snap_week) if on else {"prev": None, "current": False}
    prev = st["prev"]
    pw = ans["power"]
    for r in pw["rows"]:
        r["moved"] = None
    for o in ans["outlook"].get("rows") or []:
        o["playoff_change"] = None
    if prev is None:
        pw["movement"] = None
        pw["movement_note"] = (FIRST_NOTE if st["current"] or offered == "queued" else WAIT_NOTE) if on else NO_ARROWS
        return
    ranks = {int(p["roster_id"]): p.get("rank") for p in prev["power"]}
    for r in pw["rows"]:
        was = ranks.get(int(r["roster_id"]))
        r["moved"] = None if was is None else int(was) - int(r["rank"])
    odds = {int(p["roster_id"]): p.get("playoff") for p in prev["rows"]}
    for o in ans["outlook"].get("rows") or []:
        was = odds.get(int(o["roster_id"]))
        o["playoff_change"] = (None if was is None or o.get("playoff") is None
                               else round((float(o["playoff"]) - float(was)) * 100))
    built = prev["built_at"]
    pw["movement"] = {"week": prev["week"], "built_at": built.isoformat() if hasattr(built, "isoformat") else built}
    pw["movement_note"] = MOVED_NOTE.format(week=prev["week"])


def _league_name(lg: Mapping, lid: str, is_house: bool) -> str | None:
    name = lg.get("name")
    if not name and is_house:
        try:
            df = query("select league_name from analytics.dim_league_season where league_id = %s", (lid,))
            name = None if df.empty else df["league_name"].iloc[0]
        except Exception:  # noqa: BLE001 - no name: "This league"
            name = None
    return str(name)[:120] if isinstance(name, str) and name.strip() else None
# ---- end IO-2


def _build(league_id: str, is_house: bool, source: str | None, seasons: int, *, part: str | None = None) -> dict:
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    inp = _league_inputs(league_id, is_house)
    lg, lid, names, played, season = inp["lg"], inp["lid"], inp["names"], inp["played"], inp["season"]
    timings["league_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    t1 = time.perf_counter()
    ctx = _context(league_id, source, is_house)                    # ---- IO-2: market-free on demand
    note = None
    try:
        board, weeks, span = D.window_board(ctx, "ros")
    except D.BadRequest:
        board, weeks, span = ctx.board, tuple(ctx.board.weeks), ctx.span_words
        note = f"The rest-of-season projections are not ready for this league yet: the ranking covers {span}."
    timings["board_ms"] = round((time.perf_counter() - t1) * 1000, 1)
    t2 = time.perf_counter()
    rids = sorted(int(r) for r in names)
    lineup = {(r, int(w)): float(board.lineup_value(r, int(w))) for r in rids for w in weeks}
    level = {r: (sum(lineup[(r, int(w))] for w in weeks) / len(weeks)) if weeks else 0.0 for r in rids}
    timings["lineups_ms"] = round((time.perf_counter() - t2) * 1000, 1)

    st = inp["standings"].set_index("roster_id")
    n = len(rids)
    pf = {r: float(st.at[r, "points_for"]) if r in st.index else 0.0 for r in rids}
    pa = {r: float(st.at[r, "points_against"]) if r in st.index else 0.0 for r in rids}
    rec = {r: tuple(int(st.at[r, c]) if r in st.index and pd.notna(st.at[r, c]) else 0 for c in ("wins", "losses", "ties")) for r in rids}
    pf_rank = D._rank(pf) if played else {}
    pa_rank = D._rank(pa) if played else {}
    standing = order_rank({r: (rec[r][0] + 0.5 * rec[r][2], round(pf[r], 2)) for r in rids})
    power_rank = {r: i + 1 for i, r in enumerate(sorted(rids, key=lambda r: (-level[r], r)))}

    settings = lg.get("settings") or {}
    pws = int(settings.get("playoff_week_start") or 0)
    platform = lg.get("platform") or ("mfl" if lid.startswith("mfl:") else "sleeper")
    out_rows: list[dict] = []
    ol: dict = {"available": False, "reason": None, "weeks": [], "seasons": seasons, "playoff_teams": None,
                "playoff_week_start": pws or None, "byes": None, "tiebreak": "points for", "playoff_reason": None,
                "assumptions": list(ASSUMES), "drift": DRIFT, "shrink": WP.WEEK_SHRINK, "first_week": [], "rows": [],
                "title": False, "title_reason": None, "bracket": None}                     # ---- IO-2: title odds
    left_games: dict[int, list[int]] = {r: [] for r in rids}
    # ---- IO-2: the schedule left is read for the rankings themselves (the power part has no simulation)
    t5 = time.perf_counter()
    for r, opp in _schedule_left(lid, played, settings, len(rids)).items():
        if r in left_games:
            left_games[r] = opp
    timings["schedule_ms"] = round((time.perf_counter() - t5) * 1000, 1)
    if part == "power":
        ol.update({"pending": True, "reason": None})
    else:
        ol["reason"] = _season_outlook(ol, out_rows, left_games, timings, lid=lid, is_house=is_house, season=season,
                                       settings=settings, platform=platform, played=played, weeks=weeks, rids=rids,
                                       lineup=lineup, level=level, rec=rec, pf=pf, seasons=seasons)
    # ---- end IO-2

    sched_left = {}
    for r in rids:
        opp = left_games.get(r) or []
        if opp:
            sched_left[r] = sum(level[o] for o in opp) / len(opp)
    sl_rank = D._rank(sched_left) if sched_left else {}
    rows = []
    for r in sorted(rids, key=lambda r: power_rank[r]):
        w, lo, t = rec[r]
        rows.append({"roster_id": r, "team_name": (names.get(r) or {}).get("team_name") or f"Team {r}",
                     "manager_name": (names.get(r) or {}).get("manager_name"), "rank": power_rank[r],
                     "per_week": round(level[r], 1), "wins": w, "losses": lo, "ties": t,
                     "standing": standing[r], "points_for": round(pf[r], 2) if played else None,
                     "points_for_rank": pf_rank.get(r), "points_against": round(pa[r], 2) if played else None,
                     "points_against_rank": pa_rank.get(r),
                     "gap_words": gap_words(w, lo, t, standing[r], pf_rank[r], n) if played and r in pf_rank else None,
                     "schedule_left": round(sched_left[r], 1) if r in sched_left else None,
                     "schedule_left_rank": sl_rank.get(r), "schedule_left_games": len(left_games.get(r) or [])})
    ol["rows"] = sorted(out_rows, key=lambda x: (-(x["playoff"] if x["playoff"] is not None else -1), -x["wins_mean"],
                                                 -x["points_for_mean"]))
    ans = {"league_id": league_id, "season": season, "version": VERSION, "played_weeks": played,
           "power": {"rows": rows, "weeks": list(int(w) for w in weeks), "span": span,
                     "words": POWER_WORDS.format(span=span), "note": note, "movement": None, "movement_note": NO_ARROWS},
           "outlook": ol, "definitions": DEFINITIONS, "timings_ms": timings}
    # ---- IO-2: keep the week (a full build only), the movement from last week's stored row, the preview card
    snap_week = int(played) + 1
    name = _league_name(lg, lid, is_house)
    ans["league_name"] = name
    ans["week"] = snap_week
    ans["shareable"] = S.shareable(lid)
    ans["power"]["kept"] = None
    _movement(ans, snap_week=snap_week, offered=None)
    ans["degraded"] = bool(inp.get("degraded"))        # fix round: the offer and the card wait for outlook()'s verdict
    # ---- end IO-2
    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return ans


@router.get(PATH)
def league_outlook(league: str, response: Response, team: int | None = None, source: str | None = None,
                   part: str | None = None):
    from .main import _json
    if source not in (None, "sleeper"):
        raise D.BadRequest("source is sleeper or nothing")
    if part not in (None, "power"):                                        # ---- IO-2
        raise D.BadRequest("part is power or nothing")
    try:
        return _json(outlook(league, team, source=source, part=part), response)
    except Busy:
        return JSONResponse({"error": BUSY_WORDS, "detail": BUSY_WORDS, "code": "busy", "retry_after_s": 3},
                            status_code=429, headers={"Cache-Control": "no-store", "Retry-After": "3"})


# ---- IO-2 (Wave I-O): the page shell's link preview for a League link (`/league?league=<key>`, no team): "League of
# Scrubs: power rankings, week 5" and the top three with their numbers — from the last build this process kept or the
# newest stored row only (outlook_store.card): a crawler's hit never calls a provider and never runs a simulation.
# Nothing kept, a private (ESPN / Yahoo) key, a reference key, a malformed key → None: the default card.
CARD_TOP = 3


def preview(league: str | None) -> dict | None:
    from urllib.parse import quote

    from . import blog as B
    c = S.card(league)
    if not c or not c.get("top"):
        return None
    key = A.check_id(str(league))
    name = c.get("name") or "This league"
    title = f"{name}: power rankings, week {int(c['week'])}"
    parts = []
    top = c["top"][:CARD_TOP]
    for i, t in enumerate(top, start=1):
        pw, po = t.get("per_week"), t.get("playoff")
        num = f"{float(pw):.1f}" if pw is not None else "—"
        parts.append(f"{i}. {t.get('team') or 'Team'} {num}" + (f" ({round(float(po) * 100)}% playoffs)" if po is not None else ""))
    odds = any(t.get("playoff") is not None for t in top)
    desc = ("; ".join(parts) + ". Points per week each team's best lineup should score over the rest of the season"
            + (", and playoff odds from simulated seasons." if odds else "."))
    return {"title": title, "description": desc, "url": f"{B.ORIGIN}/league?league={quote(key, safe=':')}",
            "image": B.DEFAULT_IMAGE, "type": "website", "status": 200}


_shell_text: dict[str, tuple[float, str]] = {}


def shell(index_html, league: str | None) -> str | None:
    """index.html with the League link's preview between the shell's ``ll:seo`` markers (blog.SEO_START / SEO_END,
    every value escaped by ``blog.seo_tags``), or None — the shell as it is."""
    from . import blog as B
    try:
        pv = preview(league)
    except Exception:  # noqa: BLE001 - a preview never fails the page
        pv = None
    if pv is None:
        return None
    try:
        mtime = index_html.stat().st_mtime
        hit = _shell_text.get(str(index_html))
        if hit is None or hit[0] != mtime:
            hit = (mtime, index_html.read_text(encoding="utf-8"))
            _shell_text[str(index_html)] = hit
    except OSError:
        return None
    text = hit[1]
    i, j = text.find(B.SEO_START), text.find(B.SEO_END)
    if i < 0 or j < i:
        return None
    return text[: i + len(B.SEO_START)] + "\n    " + B.seo_tags(pv) + "\n    " + text[j:]
# ---- end IO-2
