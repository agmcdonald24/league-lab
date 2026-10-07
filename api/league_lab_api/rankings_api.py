"""Rankings for everyone, and "Who should I start?" (Wave I-P, IP-2; docs/METRICS.md § "Rankings and tiers").

* ``GET /api/rankings?league=&position=&view=week|season&limit=&offset=&q=`` — this week's or the rest of the season's
  rankings at a position (QB RB WR TE, K and DEF where the scoring starts them, FLEX = RB / WR / TE together), in the
  scoring of ``league`` (a reference key ``ref:half`` … — browsing —, a house league, any Sleeper / MFL league on demand).
  Built on what the app already holds, no new relation:
    - **week**: the matchup board's week frame (``matchup_board._week_rows``: every player with a game this week, his
      projection and range in this scoring, cached per scoring and week in the board's region) + the median (P50) the
      board does not carry (the mart for a house league, ``anyleague.price_week``'s ranges otherwise — both cached) +
      K / DEF from the same two sources;
    - **season**: the rest-of-season table ``/api/ros``'s projections view reads (``mart_player_ros_projection`` for a
      house league, ``ondemand.ros_on_demand`` — ``anyleague.ros_table`` — for anything else, a reference key included).
  The matchup chip is **the defense's tone only** (``matchup_board.combine_tone``; Wave I-O graded the cornerback call:
  no measurable effect — the corner is never shown, coloured or sorted here). Ownership only with a real league.
* ``GET /api/rankings/start?league=&ids=a,b[,c,d]`` — the chance each of two to four players outscores the others this
  week (``prob_best``), and the call in words (``call``).

**The one predictive distribution.** Every player's week is ``league_lab.decisions``' piece the week's odds draw from
(``_week_dist``: the piecewise-linear quantile function through his P10 … P90, a K / DEF row's projection as its median)
moved so its mean is his projection (``_centred``) — exactly what ``lineup_win_probability`` and the season outlook
draw. Two to four players: one Gaussian copula with D6's ``pair_rho`` for players of one game (independent otherwise),
40,000 draws, fixed seed, the draws symmetrised over every order of the players (so identical players get identical
chances and the pairwise chances add to 1 exactly), a tie split. No calibration shrink: D6 graded the pairwise number
on 4,895 start / sit pairs of 2024–2025 and a shrink fitted on one season did not help the other (METRICS § "The
decision probability"). The chance of being the highest of three or four is not graded: the screen says so.

**Tiers** (``tiers``): walking down the list, a player joins the tier of the player who opened it while that player
would outscore him in fewer than 55 weeks in 100 (``TIER_P`` = D6's "coin flip" edge, ``decisions.COIN_FLIP``) — the
order inside a tier is a coin flip; the first player the opener beats 55 times in 100 or more opens the next tier. The
chance is computed from the two distributions above (independent: a tier is a property of the list, not of one game)
on a 400-level grid of each (exact up to the grid; ties split). Stated on the screen (``TIER_WORDS``) and in METRICS.

**The cache** (``league_lab.memo`` region ``rankings``, 10 minutes, ≤ 64 entries; docs/DEPLOY.md § Memory): one entry
per (the canonical scoring key ``research._ctx_key``, season, week, view, position) — never keyed by ``q``, ``limit``
or ``offset`` (a filter on the cached frame). An entry is one position's ranked frame (≤ ~500 rows, ~0.1 MB).
"""

from __future__ import annotations

import itertools
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, Response
from league_lab import anyleague as A
from league_lab import clock, memo
from league_lab import decisions as WP

from . import matchup_board as MB
from . import refleague
from . import research as R
from .applib import cards
from .applib import ros as ROS
from .db import missing_relations, query

router = APIRouter()

POSITIONS = ("QB", "RB", "WR", "TE", "FLEX", "K", "DEF")
SKILL = ("QB", "RB", "WR", "TE")
FLEX = ("RB", "WR", "TE")
KD = ("K", "DEF")
VIEWS = ("week", "season")
MAX_LIMIT, DEFAULT_LIMIT, MAX_OFFSET = 200, 50, 1000
H2H_MIN, H2H_MAX = 2, 4
GSIS = re.compile(r"^\d{2}-\d{7}$")
TIER_P = WP.COIN_FLIP            # 0.55: the tier opener beats the next player at least this often -> a new tier
GRID = 400                       # probability levels per distribution for the tier chance
DRAWS = WP.N_DRAWS               # 40,000 joint draws for two to four players
TTL_S, ENTRIES = 600.0, 64
_cache = memo.region("rankings", ttl=TTL_S, max_entries=ENTRIES)

POS_WORDS = {"QB": ("quarterback", "quarterbacks"), "RB": ("running back", "running backs"),
             "WR": ("wide receiver", "wide receivers"), "TE": ("tight end", "tight ends"),
             "FLEX": ("flex player", "running backs, wide receivers and tight ends"), "K": ("kicker", "kickers"),
             "DEF": ("defense", "team defenses")}
TIER_WORDS = ("A tier is a run of players the first of them outscores in fewer than 55 weeks in 100: their order is a "
              "coin flip, so start whichever you like inside one.")
TIER_RULE = ("A new tier starts at the first player the tier's first player outscores in 55 weeks in 100 or more "
             "(each from his range, centred on his projection).")
WEEK_ASSUMES = ("Projected points this week in {scoring} scoring, with the range 8 weeks in 10 land in. The matchup is "
                "the defense against his position (it is in the projection); who plays cornerback is not, and is not "
                "shown here.")
SEASON_ASSUMES = ("Projected points over the weeks left (weeks {first}–{last}) in {scoring} scoring, whoever rosters "
                  "him: no roster, no lineup and no cost considered. The range is 8 seasons in 10, the weeks read as "
                  "independent.")
# the honest floor under every head-to-head answer (D6's grade, docs/METRICS.md § "The decision probability")
START_FLOOR = ("How sure this is: the ranges are built to hold 8 weeks in 10 (through week 3 of 2026 they held 79 in 100); "
               "graded on 4,895 start-or-sit pairs from 2024–2025, calls we put at 55–65% came true 58 times in 100. "
               "Read anything under 65 as a lean, not a verdict.")
START_MULTI = "The chance of being the highest of three or four is not graded yet; each pair's chance is."
START_ASSUMES = ("Each player's range this week, centred on his projection; teammates and players facing each other "
                 "move together, everyone else independently. The ranges are \"if he plays\".")
CALL_WORDS = {"clear": "a clear call, not a sure one", "a lean": "close; either is fine",
              "a coin flip": "either is fine"}


class Bad(R.BadRequest):
    """A parameter the route cannot use (400, plain words)."""


# ------------------------------------------------------------------------------------------------ the distribution
def predictive(row: dict) -> WP.Predictive | float | None:
    """One player's week (or season) as the week's odds draw it: ``decisions._week_dist`` on his quantiles and his
    projection (``value``), centred on the projection (``decisions._centred``). A float = no range (a point at his
    projection); None = no projection."""
    v = WP._num(row.get("proj_points"))
    if v is None:
        return None
    kind, d = WP._week_dist({**{q: row.get(q) for q in ("p10", "p25", "p50", "p75", "p90")}, "value": v, "actual": None})
    if kind != "range":
        return float(v)
    return WP._centred(d, v)


_LEVELS = (np.arange(GRID) + 0.5) / GRID


def grid(d: WP.Predictive | float | None) -> np.ndarray | None:
    """The distribution on ``GRID`` evenly spaced levels (sorted ascending): a point is constant."""
    if d is None:
        return None
    if isinstance(d, float | int):
        return np.full(GRID, float(d))
    return np.sort(d.ppf(_LEVELS))


def p_beats(qa: np.ndarray, qb: np.ndarray) -> float:
    """P(A > B) + ½ P(A = B) for two independent distributions on the grid (each a sorted array of equal length)."""
    lo = np.searchsorted(qb, qa, side="left").sum()
    hi = np.searchsorted(qb, qa, side="right").sum()
    return float((lo + hi) / (2.0 * len(qa) * len(qb)))


def tiers(grids: list[np.ndarray | None], p: float = TIER_P) -> tuple[list[int | None], list[float | None]]:
    """Tier numbers (1, 2, …) down a list sorted by projection, and each player's chance of being outscored by his
    tier's first player (None for the first). A player without a distribution has no tier (None) and never opens one."""
    out: list[int | None] = []
    edge: list[float | None] = []
    lead: np.ndarray | None = None
    k = 0
    for g in grids:
        if g is None:
            out.append(None)
            edge.append(None)
            continue
        if lead is None:
            k, lead = 1, g
            out.append(k)
            edge.append(None)
            continue
        pr = p_beats(lead, g)
        if pr >= p:
            k, lead = k + 1, g
            out.append(k)
            edge.append(None)
        else:
            out.append(k)
            edge.append(round(pr, 3))
    return out, edge


def prob_best(rows: list[dict], n: int = DRAWS, seed: int = WP.SEED) -> dict:
    """Two to four players this week: ``best`` (gsis -> the chance he scores the most of them, a tie split), ``pair``
    ({a: {b: P(a outscores b)}}, a tie counting half) — one Gaussian copula over the players (``pair_rho`` for a pair
    that shares a game), ``n`` draws symmetrised over every order of the players."""
    keys = [str(r["gsis_id"]) for r in rows]
    order = sorted(range(len(rows)), key=lambda j: keys[j])            # the draws are assigned in id order
    rows = [rows[j] for j in order]
    keys = [keys[j] for j in order]
    m = len(rows)
    dists = [predictive(r) for r in rows]
    corr = np.eye(m)
    for a, b in itertools.combinations(range(m), 2):
        ra, rb = rows[a], rows[b]
        if ra.get("position") in KD or rb.get("position") in KD:
            continue
        rho = WP.pair_rho(WP.relationship(ra.get("team"), ra.get("opponent"), rb.get("team"), rb.get("opponent")),
                          ra.get("position"), rb.get("position"))
        corr[a, b] = corr[b, a] = rho
    corr = WP._nearest_corr(corr)
    w, v = np.linalg.eigh(corr)
    root = (v * np.sqrt(np.maximum(w, 0.0))) @ v.T        # the symmetric root: it commutes with a swap the matrix allows
    perms = list(itertools.permutations(range(m)))
    base = max(1, math.ceil(n / len(perms)))
    z0 = np.random.default_rng(seed).standard_normal((base, m))
    z = np.concatenate([z0[:, list(p)] for p in perms]) @ root.T     # iid normals are exchangeable: every order is a draw
    u = np.clip(WP._std_normal_cdf(z), 1e-12, 1 - 1e-12)
    x = np.column_stack([np.full(len(u), d) if isinstance(d, float) else
                         (np.zeros(len(u)) if d is None else d.ppf(u[:, j])) for j, d in enumerate(dists)])
    top = x.max(axis=1, keepdims=True)
    win = x == top
    best = (win / win.sum(axis=1, keepdims=True)).mean(axis=0)
    pair: dict[str, dict[str, float]] = {k: {} for k in keys}
    for a, b in itertools.permutations(range(m), 2):
        pair[keys[a]][keys[b]] = float(np.mean(x[:, a] > x[:, b]) + 0.5 * np.mean(x[:, a] == x[:, b]))
    return {"best": {keys[j]: float(best[j]) for j in range(m)}, "pair": pair, "draws": int(len(u))}


def call(rows: list[dict], res: dict) -> dict:
    """The answer in words: the pick (the highest chance of scoring the most), the word for his edge over the
    runner-up (D6: under 55 a coin flip, 55–65 a lean, 65+ clear) and one sentence that sounds as sure as it is."""
    by = {str(r["gsis_id"]): r for r in rows}
    ranked = sorted(by, key=lambda g: (-res["best"][g], -(WP._num(by[g].get("proj_points")) or 0.0), g))
    pick, second = ranked[0], ranked[1]
    p2 = res["pair"][pick][second]
    word = WP.words(WP.percent(p2) / 100.0)          # the word follows the whole percent the sentence prints
    name = {g: cards.last_name(str(by[g].get("player_name") or g)) or str(by[g].get("player_name") or g) for g in by}
    beats = [f"{name[o]} in {WP.percent(res['pair'][pick][o])}" for o in ranked[1:]]
    if len(beats) == 1:
        span = f"he outscores {beats[0]} of 100 such weeks"
    else:
        span = f"he outscores {', '.join(beats[:-1])} and {beats[-1]} of 100 such weeks"
    if word == "clear":
        lead = f"Start {name[pick]}: {span}"
    elif word == "a lean":
        lead = f"Lean {name[pick]}: {span}"
    else:
        lead = f"A coin flip: {name[pick]} {span[3:]}" if len(ranked) == 2 else f"A coin flip at the top: {name[pick]} {span[3:]}"
    sentence = f"{lead} — {CALL_WORDS[word]}."
    if len(ranked) > 2:
        sentence += (f" Of the {['', '', 'two', 'three', 'four'][len(ranked)]}, he scores the most in "
                     f"{WP.percent(res['best'][pick])} of 100.")
    return {"pick": pick, "runner_up": second, "verdict": word, "p_vs_runner_up": round(p2, 4), "words": sentence}


# ------------------------------------------------------------------------------------------------ the parameters
def _position(v: str | None) -> str:
    p = (v or "WR").strip().upper()
    if p not in POSITIONS:
        raise Bad("position is QB, RB, WR, TE, FLEX, K or DEF.")
    return p


def _view(v: str | None) -> str:
    s = (v or "week").strip().lower()
    if s not in VIEWS:
        raise Bad("view is week or season.")
    return s


def _page(limit, offset) -> tuple[int, int]:
    try:
        n = DEFAULT_LIMIT if limit is None else int(limit)
        off = 0 if offset is None else int(offset)
    except (TypeError, ValueError) as exc:
        raise Bad("limit and offset are numbers.") from exc
    if not 1 <= n <= MAX_LIMIT:
        raise Bad(f"limit is 1 to {MAX_LIMIT}.")
    if not 0 <= off <= MAX_OFFSET:
        raise Bad(f"offset is 0 to {MAX_OFFSET}.")
    return n, off


def _ids(ids: str | None) -> list[str]:
    raw = [s.strip() for s in str(ids or "").split(",") if s.strip()]
    if len(str(ids or "")) > 64 or not H2H_MIN <= len(raw) <= H2H_MAX:
        raise Bad("Pick two to four players.")
    if any(not GSIS.match(s) for s in raw):
        raise Bad("A player is his id (as the rankings give it).")
    if len(set(raw)) != len(raw):
        raise Bad("Pick two to four different players.")
    return raw


# ------------------------------------------------------------------------------------------------ the frames
FRAME_COLS = ["key", "gsis_id", "player_name", "position", "team", "headshot_url", "opponent", "is_home", "kickoff_at",
              "game_id", "is_final", "report_status", "proj_points", "p10", "p25", "p50", "p75", "p90", "tone",
              "tone_words", "ros_games", "ros_points_per_game", "bye_weeks", "name_key"]


def kd_positions(ctx: R.Ctx) -> tuple[str, ...]:
    """K / DEF where the scoring starts them (the league's slots; a reference key's standard slots start both)."""
    try:
        return A.kd_starts(ctx.slots or [])
    except Exception:  # noqa: BLE001 - unreadable slots: the skill positions only
        return ()


def available(ctx: R.Ctx) -> list[str]:
    return [*SKILL, "FLEX", *kd_positions(ctx)]


def _p50(ctx: R.Ctx, week: int, ids: list[str]) -> dict[str, float]:
    """gsis -> this week's median in this scoring (the board's frame carries P10 / P25 / P75 / P90 only)."""
    if not ids:
        return {}
    if ctx.house:
        d = query("""select gsis_id, p50 from analytics.mart_player_week_projections
                     where league_id = %s and season = %s and week = %s and gsis_id = any(%s)""",
                  (ctx.league_id, ctx.season, int(week), list(ids)))
        return {str(g): float(v) for g, v in zip(d["gsis_id"], d["p50"], strict=True) if WP._num(v) is not None}
    pr = A.price_week(query, ctx.league_id, ctx.scoring, ctx.slots, ctx.season, int(week))
    s = pr.ranges["p50"].reindex(ids) if "p50" in pr.ranges else pd.Series(dtype=float)
    return {str(g): float(v) for g, v in s.items() if WP._num(v) is not None}


KD_HOUSE_SQL = """select gsis_id, player_name, position, team, report_status, proj_points, p10, p25, p50, p75, p90
                  from analytics.mart_player_week_projections
                  where league_id = %s and season = %s and week = %s and position = %s and proj_points is not null"""


def _kd_week(ctx: R.Ctx, week: int, pos: str, games: pd.DataFrame) -> pd.DataFrame:
    """This week's kickers or defenses in this scoring, with their game."""
    if ctx.house:
        d = query(KD_HOUSE_SQL, (ctx.league_id, ctx.season, int(week), pos))
    else:
        pr = A.price_week(query, ctx.league_id, ctx.scoring, ctx.slots, ctx.season, int(week))
        kd = pr.kd.get(pos)
        if kd is None or kd.empty:
            return pd.DataFrame(columns=FRAME_COLS)
        d = pd.DataFrame({"gsis_id": kd["unit_id"] if pos == "K" else None, "player_name": kd["player_name"],
                          "position": pos, "team": kd["team"], "report_status": kd.get("report_status"),
                          "proj_points": pd.to_numeric(kd["proj_points"], errors="coerce"),
                          "p10": pd.to_numeric(kd["p10"], errors="coerce"), "p90": pd.to_numeric(kd["p90"], errors="coerce")})
    if d.empty:
        return pd.DataFrame(columns=FRAME_COLS)
    d = d.merge(games, on="team", how="inner")
    if pos == "DEF":
        d["gsis_id"] = None
    d["key"] = [g if isinstance(g, str) and g else f"DEF:{t}" for g, t in zip(d["gsis_id"], d["team"], strict=True)]
    if pos == "K" and not d.empty:
        dim = query(R.DIM_SQL, (sorted({g for g in d["gsis_id"] if isinstance(g, str)}),))
        d = d.merge(dim[["gsis_id", "headshot_url"]], on="gsis_id", how="left")
    return d


def _week_frame(ctx: R.Ctx, season: int, week: int, pos: str) -> pd.DataFrame | None:
    """One position's (or FLEX's) rows this week, unranked: None when the week's frame cannot be built."""
    wk = MB._week_frame(season, week)
    if wk is None:
        return None
    if pos in KD:
        d = _kd_week(ctx, week, pos, wk["games"])
        d["tone"] = None
        d["tone_words"] = None
    else:
        ref = refleague.is_reference(ctx.league_id)
        league_def = None if ref else MB.league_defense(ctx, season)     # IO-4: one rank per defense on a screen
        df = MB._week_rows(ctx, season, week, wk, league_def)
        want = FLEX if pos == "FLEX" else (pos,)
        d = df[df["position"].isin(want)].copy()
        p50 = _p50(ctx, week, sorted(set(d["gsis_id"])))
        d["p50"] = [p50.get(g) for g in d["gsis_id"]]
        d["key"] = d["gsis_id"]
        if league_def is not None and "def_words" in d:
            d["tone_words"] = [f"{w}." if isinstance(w, str) and w else None for w in d["def_words"]]
        else:
            d["tone_words"] = [(wk["rows"].get(g) or {}).get("words") for g in d["gsis_id"]]
    for c in FRAME_COLS:
        if c not in d:
            d[c] = None
    d["name_key"] = [R._norm(n) for n in d["player_name"]]
    return d[FRAME_COLS]


ROS_HOUSE_SQL = "select {cols} from analytics.mart_player_ros_projection where league_id = %s and position = any(%s)"


def _season_frame(ctx: R.Ctx, season: int, week: int, pos: str) -> tuple[pd.DataFrame | None, dict]:
    """One position's rest-of-season rows (the table /api/ros's projections view reads) + the window."""
    want = list(FLEX) if pos == "FLEX" else [pos]
    if ctx.house:
        if missing_relations(("mart_player_ros_projection",)):      # a fresh copy: the notice, never a 500
            return None, {}
        df = query(ROS_HOUSE_SQL.format(cols=ROS.ROS_COLUMNS), (ctx.league_id, want))
    else:
        from .ondemand import ros_on_demand
        _lg, df = ros_on_demand(ctx.league_id)
        df = df[df["position"].isin(want)] if not df.empty else df
    if df.empty:
        return pd.DataFrame(columns=FRAME_COLS), {}
    if "is_ranked" in df:
        df = df[df["is_ranked"].fillna(True).astype(bool)]
    win = {"from_week": WP._num(df["from_week"].min()), "last_week": WP._num(df["last_week"].max())}
    d = pd.DataFrame({"key": df["player_key"].astype(str), "gsis_id": df["gsis_id"], "player_name": df["player_name"],
                      "position": df["position"], "team": df["team"],
                      "proj_points": pd.to_numeric(df["ros_points"], errors="coerce"),
                      "p10": pd.to_numeric(df["ros_p10"], errors="coerce"), "p90": pd.to_numeric(df["ros_p90"], errors="coerce"),
                      "ros_games": df["ros_games"], "ros_points_per_game": df["ros_points_per_game"],
                      "bye_weeks": df["bye_weeks"]})
    d["gsis_id"] = [g if isinstance(g, str) and g else None for g in d["gsis_id"]]
    d["key"] = [g if g else f"DEF:{t}" if p == "DEF" else k for g, t, p, k in
                zip(d["gsis_id"], d["team"], d["position"], d["key"], strict=True)]
    ids = sorted({g for g in d["gsis_id"] if g})
    dim = query(R.DIM_SQL, (ids,)) if ids else pd.DataFrame(columns=["gsis_id", "headshot_url"])
    d = d.merge(dim[["gsis_id", "headshot_url"]], on="gsis_id", how="left")
    wk = MB._week_frame(season, week) if week is not None else None
    if wk is not None:                       # this week's game beside his season (information, no chip)
        d = d.merge(wk["games"][["team", "opponent", "is_home", "kickoff_at", "game_id", "is_final"]], on="team", how="left")
    for c in FRAME_COLS:
        if c not in d:
            d[c] = None
    d["tone"] = None
    d["tone_words"] = None
    d["name_key"] = [R._norm(n) for n in d["player_name"]]
    return d[FRAME_COLS], win


def ranked(ctx: R.Ctx, view: str, pos: str) -> tuple[pd.DataFrame | None, dict]:
    """The ranked frame (rank, tier, tier_p) of one position and view, cached per canonical scoring key, season, week,
    view and position (never by the search or the page)."""
    season, week = int(ctx.season), ctx.week
    key = ("rk", R._ctx_key(ctx), season, week, view, pos)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    if view == "week":
        d, extra = _week_frame(ctx, season, int(week), pos), {}
        if d is None:
            return None, {}
    else:
        d, extra = _season_frame(ctx, season, int(week), pos)
        if d is None:
            return None, {}
    d = d[d["proj_points"].notna()].copy()
    d = d.sort_values(["proj_points", "key"], ascending=[False, True]).reset_index(drop=True)
    d["rank"] = np.arange(1, len(d) + 1)
    gs = [grid(predictive(r)) for r in d.to_dict("records")]
    t, e = tiers(gs)
    d["tier"], d["tier_p"] = t, e
    out = (d, extra)
    _cache.put(key, out)
    return out


def clear() -> None:
    _cache.clear()


# ------------------------------------------------------------------------------------------------ the routes
def _scoring(ctx: R.Ctx, league: str) -> str:
    return refleague.label(league) if refleague.is_reference(league) else ctx.league_name


def _matchup(r: dict) -> dict | None:
    t = r.get("tone")
    if t not in MB.TONES:
        return None
    return {"tone": t, "words": r.get("tone_words")}


ROW_KEYS = ("key", "gsis_id", "player_name", "position", "team", "headshot_url", "rank", "tier", "tier_p", "proj_points",
            "p10", "p25", "p50", "p75", "p90", "opponent", "is_home", "kickoff_at", "report_status")


def rankings(league: str, *, position: str | None = None, view: str | None = None, limit=None, offset=None,
             q: str | None = None, source: str | None = None) -> dict:
    pos, vw = _position(position), _view(view)
    n, off = _page(limit, offset)
    qq = MB._param_q(q)
    ctx = R.context(league, source)
    ref = refleague.is_reference(league)
    scoring = _scoring(ctx, league)
    positions = available(ctx)
    meta = {"season": ctx.season, "week": ctx.week, "view": vw, "position": pos, "scoring": scoring,
            "positions": positions, "limit": n, "offset": off, "q": qq, "tier_words": TIER_WORDS, "tier_rule": TIER_RULE,
            "tier_p": TIER_P, "league_name": None if ref else ctx.league_name, "rows": [], "total": 0, "tiers": 0}
    if pos not in positions:
        raise Bad(f"{scoring} does not start a {POS_WORDS[pos][0]}: pick {', '.join(positions)}.")
    if ctx.week is None:
        return {**meta, "notice": "The regular season is over."}
    df, extra = ranked(ctx, vw, pos)
    if df is None:
        return {**meta, "notice": "These rankings arrive with the next data refresh."}
    if vw == "week":
        meta["assumes"] = WEEK_ASSUMES.format(scoring=scoring)
    else:
        first = extra.get("from_week") or ctx.week
        last = extra.get("last_week") or first
        meta.update(from_week=int(first), last_week=int(last),
                    assumes=SEASON_ASSUMES.format(first=int(first), last=int(last), scoring=scoring))
    meta["tiers"] = int(pd.to_numeric(df["tier"], errors="coerce").max()) if len(df) and df["tier"].notna().any() else 0
    if qq is not None:              # text, never a pattern (the board's rule)
        k = R._norm(qq) if MB.NAME_CHARS.match(qq.lower()) else ""
        df = df[df["name_key"].str.contains(k, regex=False)] if k else df.iloc[0:0]
    total = int(len(df))
    page = R._records(df.iloc[off:off + n])
    now = pd.Timestamp(clock.now())
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    own = None
    if not ref and page:
        try:
            own = R.rostered(ctx).set_index("gsis_id")
        except Exception:  # noqa: BLE001 - ownership is context: the rankings stand without it
            own = None
    rows = []
    for r in page:
        row = {k: r.get(k) for k in ROW_KEYS}
        row["game_state"] = MB.game_state(r.get("kickoff_at"), r.get("is_final"), now) if r.get("kickoff_at") else None
        row["matchup"] = _matchup(r)
        if vw == "season":
            row.update(ros_games=r.get("ros_games"), ros_points_per_game=r.get("ros_points_per_game"),
                       bye_weeks=[int(w) for w in (r.get("bye_weeks") or []) if WP._num(w) is not None])
        if own is not None:
            o = own.loc[r["gsis_id"]] if r.get("gsis_id") in own.index else None
            row["rostered_by_roster_id"] = (None if o is None or pd.isna(o["rostered_by_roster_id"])
                                            else int(o["rostered_by_roster_id"]))
            row["rostered_by_team"] = None if o is None else o["rostered_by_team"]
        rows.append(row)
    return {**meta, "rows": rows, "total": total}


def start(league: str, ids: str | None, *, source: str | None = None) -> dict:
    want = _ids(ids)
    ctx = R.context(league, source)
    out = {"season": ctx.season, "week": ctx.week, "scoring": _scoring(ctx, league), "ids": want, "players": [],
           "missing": [], "floor": START_FLOOR, "assumes": START_ASSUMES, "multi_note": None, "answer": None,
           "started_note": None}
    if ctx.week is None:
        return {**out, "notice": "The regular season is over."}
    have: dict[str, dict] = {}
    for pos in ("QB", "RB", "WR", "TE", *(p for p in kd_positions(ctx) if p == "K")):
        df, _ = ranked(ctx, "week", pos)
        if df is None:
            return {**out, "notice": "This week's rankings arrive with the next data refresh."}
        sub = df[df["gsis_id"].isin(want)]
        for r in R._records(sub):
            have[str(r["gsis_id"])] = r
    found = [have[g] for g in want if g in have]
    out["missing"] = [{"gsis_id": g, "why": "no projection this week (a bye, or not on a team's roster)"}
                      for g in want if g not in have]
    out["players"] = [{k: r.get(k) for k in ("gsis_id", "player_name", "position", "team", "headshot_url", "opponent",
                                             "is_home", "kickoff_at", "proj_points", "p10", "p25", "p50", "p75", "p90",
                                             "rank", "tier")} for r in found]
    if len(found) < H2H_MIN:
        return {**out, "notice": "Pick at least two players with a game this week."}
    res = prob_best(found)
    for p in out["players"]:
        g = p["gsis_id"]
        p["p_best"] = round(res["best"][g], 4)
        p["pct_best"] = WP.percent(res["best"][g])
        p["vs"] = {o: round(v, 4) for o, v in res["pair"][g].items()}
    out["players"].sort(key=lambda p: -p["p_best"])
    out["answer"] = call(found, res)
    out["draws"] = res["draws"]
    out["multi_note"] = START_MULTI if len(found) > 2 else None
    # a game already under way: the chances are the ones from before kickoff (the ranges do not read live scores)
    now = pd.Timestamp(clock.now())
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    begun = [r for r in found if r.get("kickoff_at") and MB.game_state(r.get("kickoff_at"), r.get("is_final"), now)]
    out["started_note"] = (None if not begun else
                           f"{' and '.join(cards.last_name(str(r['player_name'])) or str(r['player_name']) for r in begun)}"
                           f"{'’s game has' if len(begun) == 1 else '’s games have'} kicked off: these chances are from "
                           "before kickoff and do not count what has happened since.")
    out["same_game"] = any(WP.relationship(a.get("team"), a.get("opponent"), b.get("team"), b.get("opponent"))
                           for a, b in itertools.combinations(found, 2))
    return out


@router.get("/api/rankings")
def rankings_route(league: str, response: Response, position: str = "WR", view: str = "week", limit: int = DEFAULT_LIMIT,
                   offset: int = 0, q: str | None = None, source: str | None = None):
    from .main import _research
    return _research(rankings(league, position=position, view=view, limit=limit, offset=offset, q=q, source=source),
                     league, response)


@router.get("/api/rankings/start")
def start_route(league: str, response: Response, ids: str | None = None, source: str | None = None):
    from .main import _research
    return _research(start(league, ids, source=source), league, response)


# ------------------------------------------------------------------------------------------------ the shell, the sitemap
def preview(params) -> dict:
    """/rankings's link preview: title and description per position and view (a closed set; anything else: the
    defaults — never the query's own text)."""
    from . import blog
    pos = str(params.get("position") or "").strip().upper()
    pos = pos if pos in POSITIONS else None
    vw = str(params.get("view") or "").strip().lower()
    vw = vw if vw in VIEWS else "week"
    when = "this week" if vw == "week" else "for the rest of the season"
    if pos is None:
        title = f"Fantasy rankings {when} · {blog.APP_NAME}"
        what = "Every quarterback, running back, receiver and tight end"
    else:
        title = f"{POS_WORDS[pos][0].capitalize()} rankings {when} · {blog.APP_NAME}"
        what = f"Every {POS_WORDS[pos][0]}" if pos != "FLEX" else "Every running back, receiver and tight end together"
    desc = (f"{what} ranked by {'this week' if vw == 'week' else 'the rest of the season'}'s projection in PPR, Half PPR "
            "or Standard scoring, with his range, his matchup and tiers — and the chance one outscores another.")
    qs = "&".join(x for x in (f"position={pos}" if pos else "", "view=season" if vw == "season" else "") if x)
    return {"title": title, "description": desc, "url": f"{blog.ORIGIN}/rankings" + (f"?{qs}" if qs else ""),
            "image": blog.DEFAULT_IMAGE, "type": "website", "status": 200}


_shell_text: dict[str, tuple[float, str]] = {}


def shell(index_html: Path, params) -> str | None:
    """index.html with /rankings's preview in the head (between the ``ll:seo`` markers), every text escaped by the
    blog's ``seo_tags``; None = serve the file as it is."""
    from . import blog
    try:
        mtime = index_html.stat().st_mtime
        hit = _shell_text.get(str(index_html))
        if hit is None or hit[0] != mtime:
            hit = (mtime, index_html.read_text(encoding="utf-8"))
            _shell_text[str(index_html)] = hit
    except OSError:
        return None
    text = hit[1]
    i, j = text.find(blog.SEO_START), text.find(blog.SEO_END)
    if i < 0 or j < i:
        return None
    return text[: i + len(blog.SEO_START)] + "\n    " + blog.seo_tags(preview(params)) + "\n    " + text[j:]


def install_pages(blog_mod) -> None:
    """/rankings in the sitemap and the blog's fixed previews (its plain path; the per-position ones come from
    ``shell``)."""
    if "/rankings" not in blog_mod.SITEMAP_PATHS:
        blog_mod.SITEMAP_PATHS = (*blog_mod.SITEMAP_PATHS, "/rankings")
    pv = preview({})
    blog_mod.PAGES.setdefault("/rankings", (pv["title"], pv["description"]))
