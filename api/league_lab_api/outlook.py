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
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from fastapi import APIRouter, Response
from league_lab import anyleague as A
from league_lab import decisions as WP  # the week's win probability: one model in the product
from league_lab import memo

from . import availability
from . import decisions as D
from . import myweek as MW
from .applib import cards
from .db import query
from .myweek import NotFound

router = APIRouter()
VERSION = "ol1.0"
SEASONS = 10_000               # Monte Carlo error of a 50% playoff chance: ±0.5 points (one standard error)
SEED = 20261006
DRIFT = 0.03                   # the per-week random walk of a team's level, as a share of its weekly points (assumed)
PATH = "/api/league/outlook"
TTL_S = {"house": 600.0, "sleeper": 120.0}
_cache = memo.region("outlook", ttl=TTL_S["house"], max_entries=48)   # one small answer per league (~10 KB)

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
    "points_for_rank": "Points for: points scored so far in the regular season, and where that ranks in the league.",
    "schedule_left": "Schedule left: the average power number (points per week) of the opponents still to play in the "
                     "regular season. Rank 1 = the hardest schedule left.",
    "projected_record": "Projected record: the average final regular-season record over the simulated seasons, and the "
                        "middle 80% of the win totals (1 season in 10 ends below, 1 in 10 above).",
    "playoff_odds": "Playoff odds: how often the team finishes inside the playoff spots in the simulated seasons (ties "
                    "on wins broken by points for). 100% and out only when it is certain on wins alone.",
    "top_seed": "Top seed: how often the team finishes first after the regular season.",
    "bye": "Bye: how often the team finishes in a spot that skips the first playoff round.",
}


# ------------------------------------------------------------------------------------------- the first week: copula
def _dist(r: Mapping):
    """One starter's range as ``WP._week_dist`` reads it, ignoring a played game (the week's spread before kickoff)."""
    kind, d = WP._week_dist({**r, "actual": None})
    return d if kind == "range" else None


def first_week_draws(sides: Mapping[int, Sequence[Mapping]], *, n: int = SEASONS, seed: int = SEED,
                     k: float = WP.WEEK_SHRINK) -> dict:
    """Every team's total in the first week left, ``n`` joint draws (the week's odds' pieces for the whole league).

    ``sides``: roster id -> starters (``myweek.win_starters`` rows with ``actual`` set where the game is in). Returns
    ``teams``, ``totals`` (n × T: the raw joint draws, played games at their points — ``lineup_win_probability``'s
    totals for the whole league; the calibration is applied per game in ``play_out``), ``expected`` (T), ``spread`` (T:
    the raw standard deviation of each lineup's total over every starter's range, played or not — its pre-game
    spread), ``ranged_share`` (T). ``k`` is kept for the signature's sake (the first week is not widened)."""
    teams = sorted(int(t) for t in sides)
    cols: dict[str, int] = {}
    dists, meta, played_mask = [], [], []
    fixed = np.zeros(len(teams))
    point = np.zeros(len(teams))
    expected = np.zeros(len(teams))
    members: list[list[int]] = [[] for _ in teams]
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
                (fixed if act is not None else point)[ti] += act if act is not None else (0.0 if v is None else v)
                continue
            if act is None:
                ranged_val[ti] += abs(v or 0.0)
            else:
                fixed[ti] += act
            key = r.get("key")
            key = f"_{t}_{i}" if not isinstance(key, str) or not key else key
            if key in cols:                          # one player is on one roster: a repeat is the same draw
                members[ti].append(cols[key])
                continue
            cols[key] = len(dists)
            dists.append(WP._centred(d, v))
            meta.append(r)
            played_mask.append(act is not None)
            members[ti].append(cols[key])
    m = len(dists)
    share = np.where(abs_val > 0, ranged_val / np.where(abs_val > 0, abs_val, 1.0), 1.0)
    out = {"teams": teams, "expected": expected, "ranged_share": share, "n_starters": m}
    if m == 0:
        tot = np.tile(fixed + point, (n, 1))
        return {**out, "totals": tot, "spread": np.zeros(len(teams))}
    keys = list(cols)
    perm = sorted(range(m), key=lambda j: str(keys[j]))         # draws assigned in key order, as the week's odds do
    pos = {old: new for new, old in enumerate(perm)}
    dists, meta = [dists[j] for j in perm], [meta[j] for j in perm]
    played = np.array([played_mask[j] for j in perm], dtype=bool)
    members = [[pos[j] for j in mem] for mem in members]
    corr = np.eye(m)
    # only a pair ``relationship`` can name correlates (same NFL team, or one's team is the other's opponent): the
    # candidates of a player are those indexed under his team or his opponent — every pair the week's odds would see
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
            rho = WP.pair_rho(WP.relationship(ra.get("team"), ra.get("opponent"), rb.get("team"), rb.get("opponent")),
                              pos_of[a], pos_of[b])
            if rho:
                corr[a, b] = corr[b, a] = rho
    corr = WP._nearest_corr(corr)
    w, v = np.linalg.eigh(corr)
    root = v * np.sqrt(np.maximum(w, 0.0))
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, m)) @ root.T
    u = np.clip(WP._std_normal_cdf(z), 1e-12, 1 - 1e-12)
    x = np.column_stack([dists[j].ppf(u[:, j]) for j in range(m)])
    totals = np.empty((n, len(teams)))
    spread = np.zeros(len(teams))
    for ti, mem in enumerate(members):
        mem = np.array(mem, dtype=int)
        live = mem[~played[mem]] if len(mem) else mem
        r_live = x[:, live].sum(axis=1) if len(live) else np.zeros(n)
        totals[:, ti] = fixed[ti] + point[ti] + r_live
        spread[ti] = float(x[:, mem].sum(axis=1).std()) if len(mem) else 0.0
    return {**out, "totals": np.maximum(totals, 0.0), "spread": spread}


# ------------------------------------------------------------------------------------------- the season
def season_totals(teams: Sequence[int], weeks: Sequence[int], mean: Mapping[tuple[int, int], float],
                  cv: Mapping[int, float], level: Mapping[int, float], *, first: np.ndarray | None = None,
                  n: int = SEASONS, seed: int = SEED, k: float = WP.WEEK_SHRINK, drift: float = DRIFT) -> np.ndarray:
    """(n, T, W) points per simulated season, team and week. ``first`` (n × T): the first week's draws (the copula);
    without it the first week is drawn like the others with no drift. A later week h weeks after the first: its
    projected best lineup ``mean[(t, w)]`` + N(0, (cv_t · mean / k)²) + the team's drift (a random walk, step
    ``drift`` · ``level[t]``, h steps). Floored at 0."""
    T, W = len(teams), len(weeks)
    rng = np.random.default_rng(seed + 1)
    mu = np.array([[mean.get((int(t), int(w)), 0.0) for w in weeks] for t in teams], dtype=float)       # T × W
    sd = np.array([max(0.0, cv.get(int(t), 0.0)) for t in teams])[:, None] * mu / k
    eps = rng.standard_normal((n, T, W))
    steps = rng.standard_normal((n, T, W)) * (drift * np.array([max(0.0, level.get(int(t), 0.0)) for t in teams]))[None, :, None]
    steps[:, :, 0] = 0.0                                      # the first week left: today's lineups, no drift
    walk = np.cumsum(steps, axis=2)
    out = mu[None, :, :] + sd[None, :, :] * eps + walk
    if first is not None and W:
        out[:, :, 0] = first
    return np.maximum(out, 0.0)


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


def calibrated_result(diff: np.ndarray, k: float = WP.WEEK_SHRINK) -> tuple[np.ndarray, float, float]:
    """Side a's result per draw (1 win, ½ tie, 0 loss) from its raw margin ``diff``, with the week's odds' calibration:
    p_raw = P(diff > 0) (a tie half), p = ``shrink_week``(p_raw, k); a wins the draws whose margin is above the
    margin's (1 − p) quantile. A settled game (no spread) keeps its result. Returns (results, p_raw, p)."""
    raw = (diff > 0) + 0.5 * (diff == 0)
    p_raw = float(raw.mean())
    p = WP.shrink_week(p_raw, k)
    if p <= 0.0 or p >= 1.0 or float(diff.std()) == 0.0 or abs(p - p_raw) < 1e-12:
        return raw.astype(float), p_raw, p
    q = float(np.quantile(diff, 1.0 - p))
    return (diff > q).astype(float), p_raw, p


def play_out(teams: Sequence[int], weeks: Sequence[int], totals: np.ndarray, games: Mapping[int, Sequence[tuple[int, int]]],
             wins0: Mapping[int, float], pf0: Mapping[int, float], spots: int | None, byes: int = 0, *,
             calibrate_first: bool = True, k: float = WP.WEEK_SHRINK) -> dict:
    """The seasons played out: per team the final wins (mean, P10, P90), losses (mean), points for (mean), playoff /
    top-seed / bye shares; per game of the first week P(a wins) (raw and calibrated). Order: wins (a tie half), then
    points for. The first week's games are decided by ``calibrated_result`` (``calibrate_first``); later weeks by the
    points drawn (already widened in ``season_totals``)."""
    T = len(teams)
    n = totals.shape[0]
    ix = {int(t): i for i, t in enumerate(teams)}
    wins = np.tile(np.array([float(wins0.get(int(t), 0.0)) for t in teams]), (n, 1))
    played = np.zeros(T)
    first: list[dict] = []
    for wi, w in enumerate(weeks):
        for a, b in games.get(int(w), ()):
            if a not in ix or b not in ix:
                continue
            ta, tb = totals[:, ix[a], wi], totals[:, ix[b], wi]
            if wi == 0 and calibrate_first:
                res, p_raw, _p = calibrated_result(ta - tb, k)
            else:
                res = (ta > tb) + 0.5 * (ta == tb)
                p_raw = None
            wins[:, ix[a]] += res
            wins[:, ix[b]] += 1.0 - res
            played[ix[a]] += 1
            played[ix[b]] += 1
            if wi == 0:
                first.append({"week": int(w), "a": int(a), "b": int(b), "p": round(float(res.mean()), 4),
                              "p_raw": None if p_raw is None else round(p_raw, 4)})
    pf = np.array([float(pf0.get(int(t), 0.0)) for t in teams])[None, :] + totals.sum(axis=2)
    key = wins * 1e6 + pf                                     # wins first, then points for (points < 1e6)
    order = np.argsort(-key, axis=1, kind="stable")
    rank = np.empty_like(order)
    rank[np.arange(n)[:, None], order] = np.arange(T)[None, :]
    rows = {}
    for t in teams:
        i = ix[int(t)]
        w = wins[:, i]
        g0 = float(wins0.get(int(t), 0.0))
        rows[int(t)] = {"wins_mean": round(float(w.mean()), 2), "wins_p10": float(np.percentile(w, 10)),
                        "wins_p90": float(np.percentile(w, 90)), "games_left": int(played[i]),
                        "wins_left_mean": round(float(w.mean()) - g0, 2),
                        "points_for_mean": round(float(pf[:, i].mean()), 1),
                        "playoff": None if not spots else round(float((rank[:, i] < spots).mean()), 4),
                        "top_seed": round(float((rank[:, i] == 0).mean()), 4),
                        "bye": None if not spots or not byes else round(float((rank[:, i] < byes).mean()), 4),
                        "rank_mean": round(float(rank[:, i].mean()) + 1, 2)}
    return {"teams": rows, "first_week": first, "seasons": int(n)}


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


def _league_inputs(league_id: str, is_house: bool) -> dict:
    """The league's settings, names, standings so far and the provider's key: {"lg", "lid", "names", "standings",
    "played" (the last week counted in the standings), "season"}."""
    client = A.sleeper()
    if is_house:
        names = D._members(league_id)
        st = query(D.STANDINGS_SQL, (league_id,))
        apw = query(D.ALL_PLAY_WEEK_SQL, (league_id,))
        played = int(apw["week"].max()) if not apw.empty else 0
        try:
            lg = client.league(A.check_id(league_id)) or {}
        except (A.SleeperBusy, A.SleeperUnavailable, A.LeagueNotFound):
            lg = {}
        return {"lg": lg, "lid": str(league_id), "names": names, "standings": _standings_frame(st, names),
                "played": played, "season": int(cards.league_season(league_id))}
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
    with no pairings (None when every week has some)."""
    out: dict[int, list[tuple[int, int]]] = {}
    for w in weeks:
        try:
            ms = client.matchups(lid, int(w))
        except (A.SleeperBusy, A.SleeperUnavailable, A.LeagueNotFound):
            return out, int(w)
        by: dict = {}
        for m in ms or []:
            if m.get("matchup_id") is not None and m.get("roster_id") is not None:
                by.setdefault(m["matchup_id"], set()).add(int(m["roster_id"]))
        pairs = [tuple(sorted(r)) for _mid, r in sorted(by.items(), key=lambda kv: str(kv[0])) if len(r) == 2]
        if not pairs:
            return out, int(w)
        out[int(w)] = [(int(a), int(b)) for a, b in pairs]
    return out, None


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


def outlook(league_id: str, team: int | None = None, *, source: str | None = None, seasons: int = SEASONS) -> dict:
    """``GET /api/league/outlook``: the power rankings and the rest of the season (module docstring)."""
    is_house = D.house(league_id, source)
    key = (str(league_id), is_house, int(seasons), _stamp())
    hit = _cache.get(key)
    if hit is None:
        hit = _cache.put(key, _build(str(league_id), is_house, source, int(seasons)),
                         ttl=TTL_S["house" if is_house else "sleeper"])
    if team is not None and int(team) not in {r["roster_id"] for r in hit["power"]["rows"]}:
        raise NotFound(f"no team {team} in this league")
    return _mine(hit, team)


def _mine(ans: dict, team: int | None) -> dict:
    out = {**ans, "roster_id": team}
    out["power"] = {**ans["power"], "rows": [{**r, "mine": team is not None and r["roster_id"] == int(team)} for r in ans["power"]["rows"]]}
    if ans["outlook"].get("rows"):
        out["outlook"] = {**ans["outlook"], "rows": [{**r, "mine": team is not None and r["roster_id"] == int(team)}
                                                     for r in ans["outlook"]["rows"]]}
    return out


def _build(league_id: str, is_house: bool, source: str | None, seasons: int) -> dict:
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    inp = _league_inputs(league_id, is_house)
    lg, lid, names, played, season = inp["lg"], inp["lid"], inp["names"], inp["played"], inp["season"]
    timings["league_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    t1 = time.perf_counter()
    ctx = D.trade_context(league_id, source)
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
                "assumptions": list(ASSUMES), "drift": DRIFT, "shrink": WP.WEEK_SHRINK, "first_week": [], "rows": []}
    left_games: dict[int, list[int]] = {r: [] for r in rids}
    t3 = time.perf_counter()
    reason = None
    first_wk = int(cards.decision_week(season) or 0) if season else 0
    if not pws:
        reason = "this league's regular-season length is not known from its settings"
    else:
        remaining = list(range(played + 1, pws))
        if not remaining:
            reason = "the regular season is over"
        else:
            board_weeks = set(int(w) for w in weeks)
            w0 = remaining[0]
            uncovered = [w for w in remaining[1:] if w not in board_weeks]
            if w0 not in board_weeks and w0 != first_wk:
                reason = f"week {w0}'s results are not final yet: the outlook returns once the league has scored it"
            elif uncovered:
                reason = f"no projections for week {uncovered[0]} yet"
            else:
                games, missing = schedule(A.sleeper(), lid, remaining)
                if missing is not None:
                    reason = f"the schedule for week {missing} is not available from the league"
                else:
                    sides, why = week_sides(lid, is_house, season, w0, rids)
                    if sides is None:
                        reason = why
                    else:
                        timings["inputs_ms"] = round((time.perf_counter() - t3) * 1000, 1)   # schedule + rosters
                        t4 = time.perf_counter()
                        fw = first_week_draws(sides, n=seasons)
                        exp = dict(zip(fw["teams"], fw["expected"], strict=True))
                        spr = dict(zip(fw["teams"], fw["spread"], strict=True))
                        cvs = {t: spr[t] / exp[t] for t in fw["teams"] if exp[t] > 0 and spr[t] > 0}
                        med = float(np.median(list(cvs.values()))) if cvs else None
                        if med is None or (fw["ranged_share"] < MW.MIN_RANGED_SHARE).any():   # the week's odds' rule
                            reason = MW.WIN_NO_RANGE
                        else:
                            cv = {t: cvs.get(t, med) for t in rids}
                            means = {**lineup, **{(t, w0): float(exp[t]) for t in fw["teams"]}}
                            first = fw["totals"][:, [fw["teams"].index(t) for t in rids]]
                            tot = season_totals(rids, remaining, means, cv, level, first=first, n=seasons)
                            spots = int(settings.get("playoff_teams") or 0) or None
                            playoff_reason = None
                            if platform == "mfl":
                                playoff_reason = ("MyFantasyLeague does not share how many teams make the playoffs, "
                                                  "so playoff odds are left out")
                            elif int(settings.get("divisions") or 0) > 1:
                                playoff_reason = "this league has divisions: division winners' places are not simulated"
                            elif not spots:
                                playoff_reason = "this league's playoff spots are not in its settings"
                            if playoff_reason:
                                spots = None
                            byes = byes_for(spots)
                            wins0 = {r: rec[r][0] + 0.5 * rec[r][2] for r in rids}
                            res = play_out(rids, remaining, tot, games, wins0, pf, spots, byes)
                            for w in remaining:
                                for a, b in games.get(w, ()):
                                    left_games.setdefault(a, []).append(b)
                                    left_games.setdefault(b, []).append(a)
                            flags = clinch_flags(rids, wins0, {r: len(left_games.get(r, [])) for r in rids}, spots) if spots else {}
                            for r in rids:
                                row = {"roster_id": r, **res["teams"][r], "status": flags.get(r)}
                                if flags.get(r) == "clinched":
                                    row["playoff"] = 1.0
                                elif flags.get(r) == "eliminated":
                                    row["playoff"], row["bye"], row["top_seed"] = 0.0, (0.0 if byes else None), 0.0
                                out_rows.append(row)
                            ol.update({"available": True, "weeks": remaining, "playoff_teams": spots, "byes": byes if spots else None,
                                       "playoff_reason": playoff_reason, "first_week": res["first_week"],
                                       "first_week_number": w0})
    ol["reason"] = reason
    if "inputs_ms" in timings:
        timings["simulation_ms"] = round((time.perf_counter() - t4) * 1000, 1)

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
    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return {"league_id": league_id, "season": season, "version": VERSION, "played_weeks": played,
            "power": {"rows": rows, "weeks": list(int(w) for w in weeks), "span": span,
                      "words": POWER_WORDS.format(span=span), "note": note, "movement": None, "movement_note": NO_ARROWS},
            "outlook": ol, "definitions": DEFINITIONS, "timings_ms": timings}


@router.get(PATH)
def league_outlook(league: str, response: Response, team: int | None = None, source: str | None = None):
    from .main import _json
    if source not in (None, "sleeper"):
        raise D.BadRequest("source is sleeper or nothing")
    return _json(outlook(league, team, source=source), response)
