"""Any Sleeper league, on demand (plan E3 spike; the design is docs/ANY_LEAGUE.md).

Today a league is an env var plus a nightly batch that prices and solves everything per league. The projected
stat lines in ``ops.projections`` are the same for every league (0 of 8,134 2026 v3.0 pairs differ in a
``proj_*`` column), so a league the database has never seen can be served at request time:

1. **Sleeper** (``Sleeper``): ``/v1/league/{id}``, ``/v1/league/{id}/rosters``, ``/v1/league/{id}/users`` (cached
   ``LEAGUE_TTL_S``) and the NFL player directory ``/v1/players/nfl`` (cached a day; Sleeper asks for at most one
   call a day). ``LEAGUE_LAB_SLEEPER_FIXTURES=<dir>`` reads ``league_<id>.json`` / ``rosters_<id>.json`` /
   ``users_<id>.json`` / ``players_nfl.json`` from a directory instead (the sandbox cannot reach Sleeper).
2. **The NFL-wide board** (``load_board``): one league's ``ops.projections`` rows of the week carry the stat line
   (the league-specific columns are dropped); team / injury / roster status from ``mart_player_week_projections``
   (the same ``mart_player_week_features`` columns the lineup service reads); every fitted league's ranges are
   kept as candidate references for step 4.
3. **Pricing**: ``scoring.compute_points`` on the stat line with the league's ``scoring_settings`` (bonuses
   included) — the same function ``projections.price`` uses, so a known league reproduces ``proj_points`` exactly.
4. **Ranges** (``approximate_ranges``): the per-league residual quantile models do not exist for a new league.
   The reference league's range around its own projection is scaled by the ratio of the two prices of the same
   stat line (``p_q = proj + (p_q,ref - proj_ref) x proj / proj_ref``); the reference is the fitted league whose
   prices are closest to this league's on the week's board (median |log ratio|), never the league itself.
   Measured on the two known leagues (each approximated from the other): docs/ANY_LEAGUE.md § "The ranges".
5. **Lineup**: ``lineup.build`` on a ``LineupInputs`` assembled for this one roster-week — the exact code path of
   the nightly (IR / taxi / bye / Out / Doubtful / locks / unvalued), so the starters, slots and margins match
   ``ops.lineups`` for a known league.
6. **Rows for the cards**: ``lineup_rows`` returns the frame ``app/lib/cards.lineup_rows`` returns (LINEUP_SQL's
   columns), so ``cards.decisions`` / ``decision_cards(rows=...)`` render the cards unchanged.

K and DEF: their stat lines are not stored (``kdef.predict_kd`` returns them; ``project`` keeps only the priced
rows), so a K / DEF is valued from a fitted league whose kicking (or defense) keys are identical; otherwise it is
unvalued and reported. The season-PPG fallbacks need the league's history and are not used here.

Plan F3 (Wave F): the Sleeper client lives in ``sleeper_client.py`` (caches by kind of call, the player directory on
disk, a token bucket); ``load_board`` reads F1's NFL-wide tables (``NFL_WIDE``: stat lines, ranges per reference
scoring, K / DEF lines, the reference scorings) when they hold the week — then a league's range reference is an exact
scoring match when there is one, and K / DEF are priced from their lines in any scoring (``kd_values``) — else the
borrowing above; ``price_week`` caches a league's priced week; ``opponent`` (Sleeper's matchups), ``ros_table`` (rest
of season, mart_player_ros_projection's rules), ``scoring_label`` and ``user_leagues`` (the picker) serve the API.
``write_fixtures`` keeps Sleeper's user ids: run ``api/tests/fixtures/make_f3_fixtures.py`` after it (pseudonymises them).

Nothing here writes; every database read goes through the ``query(sql, params) -> DataFrame`` the caller passes
(the API's cached read-only pool, or a psycopg connection in scripts).
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import lineup as LU
from .scoring import MAPPED_KEYS, compute_points, unmapped_keys
from .sleeper_client import (  # noqa: F401 - re-exported: the API and the tests import them from here
    API_ENV,
    FIXTURES_ENV,
    SLEEPER_API,
    TTL_S,
    LeagueNotFound,
    Sleeper,
    SleeperBusy,
    SleeperUnavailable,
    TokenBucket,
    check_id,
    check_username,
)

Query = Callable[[str, tuple], pd.DataFrame]

LEAGUE_TTL_S = TTL_S["league"]
PLAYERS_TTL_S = TTL_S["players"]
SKILL = ("QB", "RB", "WR", "TE")
QUANTILES = ("p10", "p25", "p50", "p75", "p90")
RANGE_METHOD = "ratio"
RATIO_CLIP = (0.25, 4.0)                      # a player whose two prices differ more than 4x keeps a bounded scale

# keys a K or DEF projection is priced on (kdef.k_coefficients / price_def): a fitted league's K (DEF) values are
# reused only when every such key has the same weight in the requested league
K_KEY = re.compile(r"^(fgm|fgmiss|xpm|xpmiss)(_|$)")
DEF_PREFIXES = ("def_", "st_", "yds_allow", "pts_allow", "blk_", "sack", "int", "ff", "fum_rec", "safe", "qb_hit", "tkl")
# the defense keys kd1.0 projects (kdef.DEF_STAT_MAP + PTS_ALLOW_BUCKETS): not "unmapped" in a league that starts a DEF
DEF_PROJECTED = re.compile(r"^(sack|int|fum_rec|ff|def_td|def_st_td|st_td|safe|blk_kick|def_st_fum_rec|st_fum_rec|"
                           r"def_st_ff|st_ff|pts_allow_.*)$")


# ------------------------------------------------------------------------------ Sleeper (sleeper_client.py)
_default: Sleeper | None = None


def sleeper() -> Sleeper:
    """The process-wide client (one cache, one token bucket); rebuilt when the fixture setting changes (tests)."""
    global _default
    fx = os.environ.get(FIXTURES_ENV)
    if _default is None or str(_default.fixtures or "") != str(Path(fx) if fx else ""):
        _default = Sleeper()
    return _default


# ------------------------------------------------------------------------------ the NFL-wide board
# Plan F1's NFL-wide tables. ONE place holds their names and columns (the PO reconciles them with F1 at integration):
#   lines       one row per player-week: the 12 proj_* components + model_version, fitted_at, frozen_at, frozen_source
#   ranges      one row per scoring_name x player-week (QB-TE; K / DEF too when F1 writes them): proj_points, p10-p90
#   kd_lines    one row per K / DEF unit-week: kdef.predict_kd's league-free line (proj_<K_LINE / DEF_LINE column>)
#   references  the seed: name, label, scoring_settings (JSON text)
# A week held twice (a frozen board next to a refit) keeps the frozen row, then the newest fit — the rule
# mart_player_ros_projection's board uses.
NFL_WIDE = {
    "lines": "ops.projection_lines",
    "ranges": "ops.projection_ranges",
    "kd_lines": "ops.kd_lines",
    "kd_ranges": "ops.kd_ranges",            # F1: K / DEF priced points + range per reference scoring (unit_id key)
    "references": "analytics_seeds.reference_scorings",
    "scoring_name": "scoring_name",          # projection_ranges' reference column
    "kd_unit": "unit_id",                    # kd_lines' unit key (a kicker's gsis_id; a defense's Sleeper id)
    "ref_name": "name", "ref_label": "label", "ref_scoring": "scoring_settings",
}
BOARD_SOURCE_ENV = "LEAGUE_LAB_BOARD_SOURCE"   # auto (default) | nfl_wide | borrow: which board load_board reads

# ops.projections column -> the stat column compute_points prices (scoring.SLEEPER_STAT_MAP's names)
STAT_LINE = {"proj_targets": "targets", "proj_receptions": "receptions", "proj_receiving_yards": "receiving_yards",
             "proj_receiving_tds": "receiving_tds", "proj_carries": "carries", "proj_rushing_yards": "rushing_yards",
             "proj_rushing_tds": "rushing_tds", "proj_attempts": "attempts", "proj_passing_yards": "passing_yards",
             "proj_passing_tds": "passing_tds", "proj_passing_interceptions": "passing_interceptions",
             "proj_fumbles_lost_total": "fumbles_lost_total"}
_COMPS = ", ".join(STAT_LINE)
_FRESHEST = "(frozen_source is not null) desc, fitted_at desc nulls last"

# --- the borrowed board (E3's spike): one league's ops.projections rows carry the stat line
BOARD_SQL = f"""
select p.league_id, p.gsis_id, p.position, p.model_version, p.proj_points, p.p10, p.p25, p.p50, p.p75, p.p90, {_COMPS}
from ops.projections p
where p.season = %s and p.week = %s and p.position = any(%s)
order by p.gsis_id, p.league_id
"""
KD_SQL = """
select p.league_id, p.position, p.gsis_id as unit_id, round(p.proj_points::numeric, 2) as proj_points,
       round(p.p10::numeric, 2) as p10, round(p.p90::numeric, 2) as p90, u.team, u.report_status, u.roster_status,
       u.player_name, u.implied_team_total
from ops.projections as p
join analytics.mart_kd_week as u
  on u.position = p.position and u.unit_id = p.gsis_id and u.season = p.season and u.week = p.week
where p.season = %s and p.week = %s and p.position in ('K', 'DEF')
"""
LEAGUES_SQL = "select league_id, scoring_settings from analytics.dim_league_season where is_current_season"

# --- the NFL-wide board (F1)
LINES_SQL = f"""
select distinct on (gsis_id) gsis_id, position, model_version, frozen_source, {_COMPS}
from {NFL_WIDE['lines']}
where season = %s and week = %s and position = any(%s)
order by gsis_id, {_FRESHEST}
"""
RANGES_SQL = f"""
select distinct on ({NFL_WIDE['scoring_name']}, gsis_id) {NFL_WIDE['scoring_name']} as scoring_name, gsis_id, position,
       proj_points, p10, p25, p50, p75, p90
from {NFL_WIDE['ranges']}
where season = %s and week = %s
order by {NFL_WIDE['scoring_name']}, gsis_id, {_FRESHEST}
"""
KD_LINES_SQL = f"""
select l.*, u.team, u.report_status, u.roster_status, u.player_name, u.implied_team_total
from (select distinct on (position, {NFL_WIDE['kd_unit']}) *
      from {NFL_WIDE['kd_lines']} where season = %s and week = %s
      order by position, {NFL_WIDE['kd_unit']}, {_FRESHEST}) as l
left join analytics.mart_kd_week as u
  on u.position = l.position and u.unit_id = l.{NFL_WIDE['kd_unit']} and u.season = l.season and u.week = l.week
"""
KD_RANGES_SQL = f"""
select distinct on ({NFL_WIDE['scoring_name']}, position, {NFL_WIDE['kd_unit']})
       {NFL_WIDE['scoring_name']} as scoring_name, position, {NFL_WIDE['kd_unit']} as unit_id, proj_points, p10, p90
from {NFL_WIDE['kd_ranges']} where season = %s and week = %s
order by {NFL_WIDE['scoring_name']}, position, {NFL_WIDE['kd_unit']}, {_FRESHEST}
"""
REFERENCES_SQL = (f"select {NFL_WIDE['ref_name']} as name, {NFL_WIDE['ref_label']} as label, "
                  f"{NFL_WIDE['ref_scoring']} as scoring_settings from {NFL_WIDE['references']} order by 1")
HAS_ROWS_SQL = f"select exists (select 1 from {NFL_WIDE['lines']} where season = %s and week = %s) as ok"

# team / injury report / NFL roster status of the week (NFL-wide columns; read from whichever league's rows exist)
STATUS_SQL = """
select distinct on (gsis_id) gsis_id, team, report_status, roster_status, player_name, implied_team_total
from analytics.mart_player_week_projections
where season = %s and week = %s and gsis_id is not null
order by gsis_id, league_id
"""


@dataclass
class Board:
    """The week's NFL-wide inputs: one stat line per player (``line``), the reference scorings' priced points and
    ranges (``fitted``: reference -> frame indexed by gsis_id), status, K / DEF rows, the reference scorings.

    ``source``: ``nfl_wide`` (F1's tables: references are ``reference_scorings`` names, ``kd`` holds K / DEF stat
    lines priced per request) or ``borrow`` (E3's spike: references are the fitted house leagues, ``kd`` holds each
    league's priced K / DEF rows)."""
    season: int
    week: int
    line: pd.DataFrame
    fitted: dict[str, pd.DataFrame]
    status: pd.DataFrame
    kd: pd.DataFrame
    scorings: dict[str, dict[str, float]]
    mismatched_lines: int = 0
    source: str = "borrow"
    labels: dict[str, str] = field(default_factory=dict)
    kd_fitted: dict[str, pd.DataFrame] = field(default_factory=dict)


def _floats(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def _status(query: Query, season: int, week: int) -> pd.DataFrame:
    try:
        return query(STATUS_SQL, (int(season), int(week))).set_index("gsis_id")
    except Exception:  # noqa: BLE001 - no per-week mart: team from dim_player, no statuses
        return pd.DataFrame(columns=["team", "report_status", "roster_status", "player_name"])


def board_source() -> str:
    v = (os.environ.get(BOARD_SOURCE_ENV) or "auto").strip().lower()
    return v if v in ("auto", "nfl_wide", "borrow") else "auto"


def nfl_wide_ready(query: Query, season: int, week: int) -> bool:
    """Do F1's tables exist and hold this week?"""
    try:
        df = query(HAS_ROWS_SQL, (int(season), int(week)))
    except Exception:  # noqa: BLE001 - the table is not there (DataNotReady / UndefinedTable): borrow
        return False
    return bool(not df.empty and df["ok"].iloc[0])


def load_board(query: Query, season: int, week: int, source: str | None = None) -> Board:
    """The week's board: F1's NFL-wide tables when they exist and hold the week (``nfl_wide``), else E3's borrowing
    from ``ops.projections`` (``borrow``). ``source`` / ``LEAGUE_LAB_BOARD_SOURCE`` force one."""
    src = source or board_source()
    if src == "nfl_wide" or (src == "auto" and nfl_wide_ready(query, season, week)):
        return _load_nfl_wide(query, season, week)
    return _load_borrowed(query, season, week)


def _load_borrowed(query: Query, season: int, week: int) -> Board:
    raw = _floats(query(BOARD_SQL, (int(season), int(week), list(SKILL))), ["proj_points", *QUANTILES, *STAT_LINE])
    comps = list(STAT_LINE)
    first = raw.drop_duplicates("gsis_id", keep="first").set_index("gsis_id")
    line = first[["position", "model_version", *comps]].copy()
    # the premise of the design: the stat line does not depend on the league (a mismatch is counted and reported)
    other = raw.set_index("gsis_id")[comps]
    mism = int((other.sub(line[comps].reindex(other.index)).abs() > 1e-9).any(axis=1).sum())
    fitted = {lid: g.set_index("gsis_id")[["proj_points", *QUANTILES]] for lid, g in raw.groupby("league_id")}
    status = _status(query, season, week)
    try:
        kd = _floats(query(KD_SQL, (int(season), int(week))), ["proj_points", "p10", "p90"])
    except Exception:  # noqa: BLE001 - a database without the K / DEF mart: K / DEF unvalued, reported
        kd = pd.DataFrame(columns=["league_id", "position", "unit_id", "proj_points", "p10", "p90", "team",
                                   "report_status", "roster_status", "player_name", "implied_team_total"])
    lg = query(LEAGUES_SQL, ())
    scorings = {r.league_id: {k: float(v) for k, v in (r.scoring_settings or {}).items()} for r in lg.itertuples()}
    kd_fitted = {lid: g.set_index("unit_id")[["proj_points", "p10", "p90"]] for lid, g in kd.groupby("league_id")}
    return Board(int(season), int(week), line, fitted, status, kd, scorings, mism, "borrow", {}, kd_fitted)


def _load_nfl_wide(query: Query, season: int, week: int) -> Board:
    line = _floats(query(LINES_SQL, (int(season), int(week), list(SKILL))), list(STAT_LINE)).set_index("gsis_id")
    line = line[["position", "model_version", *STAT_LINE]]
    rg = _floats(query(RANGES_SQL, (int(season), int(week))), ["proj_points", *QUANTILES])
    skill = rg[rg["position"].isin(SKILL)]
    fitted = {n: g.set_index("gsis_id")[["proj_points", *QUANTILES]] for n, g in skill.groupby("scoring_name")}
    # F1 keeps the K / DEF priced points and ranges in ops.kd_ranges (unit_id key), not in projection_ranges
    try:
        kdr = _floats(query(KD_RANGES_SQL, (int(season), int(week))), ["proj_points", "p10", "p90"])
    except Exception:  # noqa: BLE001 - no K / DEF ranges yet: the offsets fall back to nothing (K / DEF unranged)
        kdr = pd.DataFrame(columns=["scoring_name", "position", "unit_id", "proj_points", "p10", "p90"])
    kd_fitted = {n: g.set_index("unit_id")[["proj_points", "p10", "p90"]] for n, g in kdr.groupby("scoring_name")}
    refs = query(REFERENCES_SQL, ())
    scorings, labels = {}, {}
    for r in refs.itertuples():
        sc = r.scoring_settings if isinstance(r.scoring_settings, dict) else json.loads(r.scoring_settings or "{}")
        scorings[r.name] = {k: float(v) for k, v in sc.items() if v is not None}
        labels[r.name] = r.label
    try:
        kd = query(KD_LINES_SQL, (int(season), int(week)))
        kd = kd.rename(columns={NFL_WIDE["kd_unit"]: "unit_id"}) if NFL_WIDE["kd_unit"] != "unit_id" else kd
    except Exception:  # noqa: BLE001 - no K / DEF lines yet: K / DEF unvalued, reported
        kd = pd.DataFrame(columns=["position", "unit_id", "team", "report_status", "roster_status"])
    return Board(int(season), int(week), line, fitted, _status(query, season, week), kd, scorings, 0, "nfl_wide",
                 labels, kd_fitted)


def price_lines(line: pd.DataFrame, scoring: Mapping[str, float]) -> pd.Series:
    """League points of every stat line: ``compute_points`` (bonuses included), exactly as ``projections.price``."""
    stats = line[list(STAT_LINE)].rename(columns=STAT_LINE).fillna(0.0)
    if "position" in line:          # F1: a position premium (bonus_rec_te, …) prices only when the row carries the position
        stats["position"] = line["position"].to_numpy()
    return pd.Series([compute_points(r, scoring) for r in stats.to_dict("records")], index=line.index, dtype=float)


# ------------------------------------------------------------------------------ ranges for a league the model never saw
def _mapped(scoring: Mapping[str, float]) -> dict[str, float]:
    """The scoring keys the stat line prices (scoring.MAPPED_KEYS), non-zero, rounded to 3 places (Sleeper stores
    float32: 0.05000000074505806 is 0.05) — what "the same scoring" means for choosing a reference."""
    return {k: round(float(w), 3) for k, w in scoring.items() if k in MAPPED_KEYS and w and round(float(w), 3) != 0}


def exact_reference(scoring: Mapping[str, float] | None, scorings: Mapping[str, Mapping[str, float]],
                    exclude: str | None = None) -> str | None:
    """A reference whose mapped keys equal this league's (first by name), never ``exclude``."""
    if not scoring:
        return None
    mine = _mapped(scoring)
    for name in sorted(scorings):
        if name != exclude and _mapped(scorings[name]) == mine:
            return name
    return None


def choose_reference(proj: pd.Series, fitted: Mapping[str, pd.DataFrame], exclude: str | None = None, *,
                     scoring: Mapping[str, float] | None = None,
                     scorings: Mapping[str, Mapping[str, float]] | None = None) -> str | None:
    """The reference for this league's ranges: one whose mapped scoring keys equal the league's (when ``scoring``
    and ``scorings`` are given), else the one whose prices of this week's stat lines are closest to ``proj``
    (median |log ratio| over the players both price above one point); never ``exclude``."""
    if scoring is not None and scorings:
        ex = exact_reference(scoring, {n: sc for n, sc in scorings.items() if n in fitted}, exclude)
        if ex is not None:
            return ex
    best, best_d = None, math.inf
    for lid, f in sorted(fitted.items()):
        if lid == exclude:
            continue
        both = pd.concat([proj.rename("new"), f["proj_points"].rename("ref")], axis=1, join="inner")
        both = both[(both["new"] > 1) & (both["ref"] > 1)]
        if both.empty:
            continue
        d = float(np.median(np.abs(np.log(both["new"] / both["ref"]))))
        if d < best_d:
            best, best_d = lid, d
    return best


def reference_for(proj: pd.Series, b: Board, scoring: Mapping[str, float], league_id: str,
                  exclude_reference: str | None = None) -> str | None:
    """The one rule every on-demand surface uses (My Week, the player card, rest of season): the borrowed board
    never takes the league's own fitted ranges (a known league is measured as if it were new); the NFL-wide board
    takes an exact reference scoring when there is one. ``exclude_reference`` excludes one more (tests)."""
    exclude = exclude_reference if exclude_reference is not None else (league_id if b.source == "borrow" else None)
    ref = choose_reference(proj, b.fitted, exclude=exclude, scoring=scoring, scorings=b.scorings)
    if ref is None and exclude_reference is None:
        ref = choose_reference(proj, b.fitted, exclude=None, scoring=scoring, scorings=b.scorings)
    return ref


def approximate_ranges(proj: pd.Series, ref: pd.DataFrame) -> pd.DataFrame:
    """P10 / P25 / P50 / P75 / P90 for ``proj`` (this league's points, by gsis_id) from a fitted league's ranges
    ``ref`` (proj_points + quantiles): each offset from the reference projection scaled by proj / proj_ref, then
    the order and floors ``projections.predict_position`` applies (P10 >= 0, P90 >= the projection,
    P10 <= P25 <= P50 <= P75 <= P90). A player the reference does not price: NULL (unknown, never 0)."""
    r = ref.reindex(proj.index)
    pr = r["proj_points"]
    k = (proj / pr.where(pr > 0.05)).fillna(1.0).clip(*RATIO_CLIP)
    out = pd.DataFrame(index=proj.index)
    for q in QUANTILES:
        out[q] = proj + (r[q] - pr) * k
    has = r["p10"].notna() & r["p90"].notna()
    qs = np.sort(out[["p10", "p50", "p90"]].to_numpy(dtype=float), axis=1)
    out["p10"], out["p50"], out["p90"] = np.clip(qs[:, 0], 0, None), qs[:, 1], np.maximum(qs[:, 2], proj.to_numpy(dtype=float))
    out["p50"] = out["p50"].clip(out["p10"], out["p90"])
    have50 = r["p25"].notna() & r["p75"].notna()
    q50 = np.sort(out[["p25", "p75"]].to_numpy(dtype=float), axis=1)
    out["p25"] = pd.Series(np.clip(q50[:, 0], out["p10"], out["p50"]), index=out.index).where(have50)
    out["p75"] = pd.Series(np.clip(q50[:, 1], out["p50"], out["p90"]), index=out.index).where(have50)
    return out.where(has, np.nan).round(2)


# ------------------------------------------------------------------------------ the league, its scoring, its roster
def _keys(scoring: Mapping[str, float], pick: Callable[[str], bool]) -> dict[str, float]:
    return {k: float(w) for k, w in scoring.items() if w and pick(k)}


def _is_def_key(k: str) -> bool:
    return k.startswith(DEF_PREFIXES) and MAPPED_KEYS.get(k) is None


def kd_source(scoring: Mapping[str, float], position: str, board: Board) -> str | None:
    """Borrowed board: a fitted league whose K (DEF) pricing keys equal this league's, so its K (DEF) values are
    this league's. NFL-wide board: ``"lines"`` when the week has K (DEF) stat lines (priced in any scoring)."""
    if board.source == "nfl_wide":
        has = not board.kd.empty and bool((board.kd["position"] == position).any())
        return "lines" if has else None
    pick = (lambda k: bool(K_KEY.match(k))) if position == "K" else _is_def_key
    mine = _keys(scoring, pick)
    have = set(board.kd.loc[board.kd["position"] == position, "league_id"]) if not board.kd.empty else set()
    for lid in sorted(have):
        if _keys(board.scorings.get(lid, {}), pick) == mine:
            return lid
    return None


def kd_values(scoring: Mapping[str, float], position: str, board: Board) -> tuple[str | None, pd.DataFrame]:
    """(source, one row per K / DEF unit: unit_id, proj_points, p10, p90, team, report_status, roster_status) in this
    league's scoring. NFL-wide: ``kdef.price`` on the stat line (the function ``predict_kd`` prices with, so a house
    league reproduces its nightly K / DEF points), the range = the nearest reference's fixed offsets (kd1.0's
    interval is a fixed offset per scoring); borrowed: the fitted league with the same keys, else nothing."""
    cols = ["unit_id", "proj_points", "p10", "p90", "team", "report_status", "roster_status", "player_name",
            "implied_team_total"]
    src = kd_source(scoring, position, board)
    if src is None:
        return None, pd.DataFrame(columns=cols)
    if board.source != "nfl_wide":
        rows = board.kd[(board.kd["league_id"] == src) & (board.kd["position"] == position)]
        return src, rows.reindex(columns=cols).reset_index(drop=True)
    from . import kdef  # the K / DEF pricing (needs pydantic-settings via config)
    rows = board.kd[board.kd["position"] == position].copy()
    line_cols = [f"proj_{c}" for c in (kdef.K_LINE if position == "K" else kdef.DEF_LINE)]
    for c in line_cols:
        rows[c] = pd.to_numeric(rows[c], errors="coerce") if c in rows else 0.0
    rows["proj_points"] = kdef.price(rows.reset_index(drop=True), position, scoring, "proj_")
    # the range: the reference with the closest K (DEF) prices; its offsets kept as they are (fixed per scoring)
    proj = rows.set_index("unit_id")["proj_points"].astype(float)
    ref = choose_reference(proj, {n: f for n, f in board.kd_fitted.items() if not f.empty})
    if ref is not None:
        f = board.kd_fitted[ref].reindex(proj.index)
        lo, hi = (f["p10"] - f["proj_points"]).to_numpy(), (f["p90"] - f["proj_points"]).to_numpy()
        rows["p10"] = np.round(np.clip(proj.to_numpy() + lo, 0, None), 2)
        rows["p90"] = np.round(np.maximum(proj.to_numpy() + hi, proj.to_numpy()), 2)
    else:
        rows["p10"] = rows["p90"] = np.nan
    for c in ("team", "report_status", "roster_status", "player_name", "implied_team_total"):
        if c not in rows:
            rows[c] = None
    return "lines", rows[cols].reset_index(drop=True)


def scoring_report(scoring: Mapping[str, float], slots: list[str]) -> dict[str, list[str]]:
    """What the projection cannot price in this league: ``unmapped`` (no stat behind the key — DEF keys left out
    when the league starts a DEF, kd1.0 prices those) and ``not_projected`` (mapped, but the projected stat line
    has no such column: long-TD bonuses, 2-point conversions, return / fumble-recovery TDs — they price 0 in the
    projection, as in the nightly board)."""
    starts_def = "DEF" in {str(s).upper() for s in slots}
    # a defense key matters only in a league that starts a DEF, and there kd1.0 prices the ones it projects
    unm = [k for k in unmapped_keys(scoring)
           if not (_is_def_key(k) and (not starts_def or DEF_PROJECTED.match(k)))]
    line_cols = set(STAT_LINE.values())
    from .scoring import _PY_EXPR, SLEEPER_BONUS_MAP
    not_proj = []
    for k, w in scoring.items():
        if not w or k not in MAPPED_KEYS or K_KEY.match(k):
            continue
        cols = {SLEEPER_BONUS_MAP[k][0]} if k in SLEEPER_BONUS_MAP else set(_PY_EXPR.get(k, ()))
        if not cols <= line_cols:
            not_proj.append(k)
    return {"unmapped": sorted(unm), "not_projected": sorted(not_proj)}


def team_names(rosters: list[dict], users: list[dict]) -> dict[int, dict]:
    """roster_id -> team_name / manager_name, the dim_league_member rule (team name, else display name)."""
    by_user = {u.get("user_id"): u for u in users}
    out = {}
    for r in rosters:
        u = by_user.get(r.get("owner_id")) or {}
        tn = ((u.get("metadata") or {}).get("team_name") or "").strip() or None
        dn = u.get("display_name")
        out[int(r["roster_id"])] = {"team_name": tn or dn or f"Roster {r['roster_id']}", "manager_name": dn or "unknown"}
    return out


def records(rosters: list[dict]) -> dict[int, dict]:
    """roster_id -> wins, losses, standing (wins, then points for) from the roster payloads' settings."""
    rows = []
    for r in rosters:
        s = r.get("settings") or {}
        pts = float(s.get("fpts") or 0) + float(s.get("fpts_decimal") or 0) / 100
        rows.append((int(r["roster_id"]), int(s.get("wins") or 0), int(s.get("losses") or 0), pts))
    rows.sort(key=lambda t: (-t[1], -t[3], t[0]))
    return {rid: {"wins": w, "losses": lo, "standing": i} for i, (rid, w, lo, _) in enumerate(rows, 1)}


# ------------------------------------------------------------------------------ one roster-week
@dataclass
class OnDemand:
    """Everything ``lineup_rows`` built, plus what it could not price."""
    league: dict
    roster_id: int
    season: int
    week: int
    rows: pd.DataFrame                    # cards.lineup_rows' columns
    totals: dict
    reference_league: str | None
    unmapped_players: list[dict] = field(default_factory=list)
    scoring: dict[str, list[str]] = field(default_factory=dict)
    kd_sources: dict[str, str | None] = field(default_factory=dict)
    mismatched_lines: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)
    sleeper_calls: int = 0
    board_source: str = "borrow"


GAMES_SQL = """select week, home_team, away_team, kickoff_at from analytics.dim_game
               where season = %s and week = %s and season_type = 'REG'"""
DIM_PLAYER_SQL = "select gsis_id, player_name, latest_team from analytics.dim_player where gsis_id = any(%s)"
IDMAP_SQL = "select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)"
OPP_RANK_SQL = "select defense, position, rank_std from analytics.mart_defense_vs_position_current"


@dataclass
class Priced:
    """One league's prices of one week's board: the skill stat lines priced in its scoring (``proj`` by gsis_id),
    their ranges from the reference (``ranges``), the K / DEF values (``kd``: position -> frame) and their sources."""
    league_id: str
    season: int
    week: int
    board: Board
    proj: pd.Series
    ranges: pd.DataFrame
    reference: str | None
    kd: dict[str, pd.DataFrame]
    kd_sources: dict[str, str | None]
    timings_ms: dict[str, float] = field(default_factory=dict)


PRICED_TTL_S = 600                         # the board changes once a night; a league's scoring almost never
_priced: dict[tuple, tuple[float, Priced]] = {}


def _scoring_key(scoring: Mapping[str, float]) -> str:
    return json.dumps({k: round(float(v), 6) for k, v in sorted(scoring.items())})


def price_week(query: Query, league_id: str, scoring: Mapping[str, float], slots: list[str], season: int, week: int, *,
               board: Board | None = None, exclude_reference: str | None = None, cache: bool = True) -> Priced:
    """Price a week's board in a league's scoring (skill lines, ranges, K / DEF) — cached 10 minutes per (scoring,
    slots' K / DEF, week, exclusion) in-process, so the rest-of-season sum and every request of the same league reuse it."""
    starts = tuple(p for p in ("K", "DEF") if p in {str(x).upper() for x in slots})
    key = (str(league_id), _scoring_key(scoring), starts, int(season), int(week), exclude_reference, board_source())
    now = time.monotonic()
    hit = _priced.get(key) if cache and board is None else None
    if hit is not None and hit[0] > now:
        return hit[1]
    t0 = time.perf_counter()
    b = board or load_board(query, season, week)
    t1 = time.perf_counter()
    proj = price_lines(b.line, scoring)
    t2 = time.perf_counter()
    ref = reference_for(proj, b, scoring, str(league_id), exclude_reference)
    if ref is None:
        ranges = pd.DataFrame(index=proj.index, columns=list(QUANTILES), dtype=float)
    elif b.source == "nfl_wide" and _mapped(b.scorings.get(ref, {})) == _mapped(scoring):
        ranges = b.fitted[ref][list(QUANTILES)].reindex(proj.index).astype(float).round(2)   # an exact reference
    else:
        ranges = approximate_ranges(proj, b.fitted[ref])
    t3 = time.perf_counter()
    kd, kd_src = {}, {}
    for pos in starts:
        kd_src[pos], kd[pos] = kd_values(scoring, pos, b)
    t4 = time.perf_counter()
    out = Priced(str(league_id), int(season), int(week), b, proj, ranges, ref, kd, kd_src,
                 {"board": round((t1 - t0) * 1000, 1), "price": round((t2 - t1) * 1000, 1),
                  "ranges": round((t3 - t2) * 1000, 1), "kd": round((t4 - t3) * 1000, 1)})
    if cache and board is None:
        if len(_priced) > 500:
            _priced.clear()
        _priced[key] = (now + PRICED_TTL_S, out)
    return out


def clear_priced() -> None:
    _priced.clear()


def _solve_roster(query: Query, league_id: str, roster: dict, players: Mapping[str, dict], pr: Priced, slots: list[str],
                  as_of: datetime) -> tuple[list[dict], list[dict], list[dict], pd.DataFrame, pd.DataFrame]:
    """(ops.lineups-shaped rows, totals, unmapped players, dim_player rows, the week's games) for one roster —
    ``lineup.build`` on a ``LineupInputs`` assembled for this one roster-week (the nightly's code path)."""
    week, season, b, proj = pr.week, pr.season, pr.board, pr.proj
    roster_id = int(roster["roster_id"])
    # Sleeper ids -> gsis (player_id_map; never by name), the directory's position / eligibility / team / name
    pids = [str(p) for p in (roster.get("players") or [])]
    idm = query(IDMAP_SQL, (pids,))
    gsis_of = dict(zip(idm["sleeper_id"], idm["gsis_id"], strict=False)) if not idm.empty else {}
    gs = sorted({g for g in gsis_of.values() if g})
    dp = query(DIM_PLAYER_SQL, (gs,)).set_index("gsis_id") if gs else pd.DataFrame(columns=["player_name", "latest_team"])
    reserve, taxi = set(roster.get("reserve") or []), set(roster.get("taxi") or [])
    current, sleeper_meta, unmapped = [], {}, []
    for sid in pids:
        sp = players.get(sid) or {}
        name = sp.get("full_name") or " ".join(x for x in (sp.get("first_name"), sp.get("last_name")) if x) or sid
        position = sp.get("position")
        sleeper_meta[sid] = {"sleeper_player_id": sid, "position": position, "fantasy_positions": sp.get("fantasy_positions"),
                             "team": sp.get("team")}
        gsis = gsis_of.get(sid)
        if gsis is None and position != "DEF":
            unmapped.append({"sleeper_player_id": sid, "player_name": name, "position": position, "team": sp.get("team")})
        current.append({"sleeper_player_id": sid, "gsis_id": gsis, "player_name": name, "position": position,
                        "nfl_team": sp.get("team"), "is_on_ir": sid in reserve, "is_on_taxi": sid in taxi})

    # this league's values of this roster's players (the lineup service rounds to the cent, like the mart)
    proj_map = {}
    for c in current:
        g = c["gsis_id"]
        if g and g in proj.index:
            st = b.status.loc[g] if g in b.status.index else None
            proj_map[(league_id, int(week), g)] = {
                "proj_points": round(float(proj[g]), 2),
                "team": None if st is None else st.get("team"),
                "report_status": None if st is None else st.get("report_status"),
                "roster_status": None if st is None else st.get("roster_status")}
    kd_proj, k_team = {}, {}
    for pos, rows_ in pr.kd.items():
        by_team: dict[str, list[dict]] = {}
        for r in rows_.itertuples():
            v = {"proj_points": None if pd.isna(r.proj_points) else float(r.proj_points), "team": r.team,
                 "report_status": r.report_status, "roster_status": r.roster_status}
            kd_proj[(league_id, int(week), r.unit_id)] = v
            if pos == "K" and isinstance(r.team, str) and r.team:
                by_team.setdefault(r.team, []).append(v)
        k_team.update({(league_id, int(week), tm): v[0] for tm, v in by_team.items() if len(v) == 1})
    g = query(GAMES_SQL, (season, int(week)))
    games: dict[int, dict[str, datetime | None]] = {int(week): {}}
    for r in g.itertuples():
        games[int(week)][r.home_team] = r.kickoff_at
        games[int(week)][r.away_team] = r.kickoff_at
    inp = LU.LineupInputs(
        season=season,
        leagues=[{"league_id": league_id, "roster_positions": slots, "last_scored_leg": int(week) - 1,
                  "roster_ids": [roster_id]}],
        weeks={league_id: [int(week)]}, proj=proj_map, weekly={}, current={league_id: {roster_id: current}},
        sleeper=sleeper_meta, k_ppg={}, games=games, model_version=",".join(sorted(set(b.line["model_version"].dropna()))),
        starters={(league_id, roster_id): [str(s) for s in (roster.get("starters") or [])]},
        kd_proj=kd_proj, k_team_proj=k_team)
    rows, totals, _ = LU.build(inp, as_of=as_of)
    return rows, totals, unmapped, dp, g


def league_scoring(league: Mapping) -> tuple[dict[str, float], list[str]]:
    scoring = {k: float(v) for k, v in (league.get("scoring_settings") or {}).items() if v is not None}
    return scoring, [str(s) for s in league.get("roster_positions") or []]


def lineup_rows(query: Query, league_id: str, roster_id: int, week: int, *, as_of: datetime | None = None,
                client: Sleeper | None = None, exclude_reference: str | None = None,
                board: Board | None = None) -> OnDemand:
    """The proposed lineup of one roster-week of any Sleeper league, as the frame ``cards.lineup_rows`` returns.

    ``as_of`` decides which games have kicked off (default now; the parity test passes the nightly's). The range
    reference: ``reference_for`` (the borrowed board never uses the league's own fitted ranges; the NFL-wide board
    takes an exact reference scoring); ``exclude_reference`` excludes one more."""
    t = {"start": time.perf_counter()}
    sl = client or sleeper()
    calls0 = sl.calls
    league_id = check_id(league_id)
    league = sl.league(league_id)
    rosters = sl.rosters(league_id)
    sl.users(league_id)                      # with the league: the API names the teams from it (cached)
    players = sl.players()
    t["sleeper"] = time.perf_counter()
    roster = next((r for r in rosters if int(r.get("roster_id", -1)) == int(roster_id)), None)
    if roster is None:
        raise LeagueNotFound(f"no team {roster_id} in league {league_id}")
    season = int(league.get("season"))
    scoring, slots = league_scoring(league)
    as_of = as_of or datetime.now(UTC)
    pr = price_week(query, league_id, scoring, slots, season, week, board=board, exclude_reference=exclude_reference)
    t["priced"] = time.perf_counter()
    rows, totals, unmapped, dp, g = _solve_roster(query, league_id, roster, players, pr, slots, as_of)
    t["solve"] = time.perf_counter()
    frame = _cards_frame(query, rows, totals[0] if totals else {}, pr.ranges, pr.board, dp, g, as_of)
    t["frame"] = time.perf_counter()
    marks = list(t)
    timings = {f"{marks[i]}": round((t[marks[i]] - t[marks[i - 1]]) * 1000, 1) for i in range(1, len(marks))}
    timings["total"] = round((t[marks[-1]] - t["start"]) * 1000, 1)
    timings.update({f"priced.{k}": v for k, v in pr.timings_ms.items()})
    return OnDemand(league=league, roster_id=int(roster_id), season=season, week=int(week), rows=frame,
                    totals=totals[0] if totals else {}, reference_league=pr.reference, unmapped_players=unmapped,
                    scoring=scoring_report(scoring, slots), kd_sources=pr.kd_sources,
                    mismatched_lines=pr.board.mismatched_lines, timings_ms=timings, sleeper_calls=sl.calls - calls0,
                    board_source=pr.board.source)


# ------------------------------------------------------------------------------ the week's opponent (Sleeper's matchups)
def opponent(query: Query | None, league_id: str, roster_id: int, week: int, *, client: Sleeper | None = None,
             as_of: datetime | None = None, solve: bool = True, exclude_reference: str | None = None) -> dict | None:
    """The roster sharing this roster's ``matchup_id`` in Sleeper's ``/league/<id>/matchups/<week>`` (None when the
    week has no matchup: a bye, playoffs not reached, a league without head-to-head): roster_id, team_name, manager
    and, with ``solve``, the opponent's best lineup value this week solved the same way (``lineup.build``)."""
    sl = client or sleeper()
    league_id = check_id(league_id)
    ms = sl.matchups(league_id, int(week))
    mine = next((m for m in ms if int(m.get("roster_id", -1)) == int(roster_id)), None)
    if mine is None or mine.get("matchup_id") is None:
        return None
    opp = next((m for m in ms if m.get("matchup_id") == mine.get("matchup_id")
                and int(m.get("roster_id", -1)) != int(roster_id)), None)
    if opp is None:
        return None
    rosters, users = sl.rosters(league_id), sl.users(league_id)
    oid = int(opp["roster_id"])
    names = team_names(rosters, users).get(oid, {})
    out = {"roster_id": oid, "team_name": names.get("team_name"), "manager": names.get("manager_name"),
           "matchup_id": int(mine["matchup_id"]), "lineup_value": None}
    if solve and query is not None:
        league = sl.league(league_id)
        roster = next((r for r in rosters if int(r.get("roster_id", -1)) == oid), None)
        if roster is not None:
            scoring, slots = league_scoring(league)
            pr = price_week(query, league_id, scoring, slots, int(league["season"]), int(week),
                            exclude_reference=exclude_reference)
            _, totals, _, _, _ = _solve_roster(query, league_id, roster, sl.players(), pr, slots, as_of or datetime.now(UTC))
            if totals and totals[0].get("lineup_value") is not None:
                out["lineup_value"] = round(float(totals[0]["lineup_value"]), 2)
    return out


def _cards_frame(query: Query, rows: list[dict], tot: dict, ranges: pd.DataFrame, b: Board, dp: pd.DataFrame,
                 games: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    """ops.lineups-shaped rows -> the frame LINEUP_SQL returns (starters incl. empty slots, bench, can't play;
    team, range, kickoff, opponent, the opponent's rank vs the position)."""
    cols = ["role", "slot", "slot_type", "slot_order", "bench_rank", "gsis_id", "sleeper_player_id", "player_name", "position",
            "value", "value_source", "margin", "is_locked", "is_empty_slot", "report_status", "reason", "is_weakest_slot",
            "lineup_value", "bench_value", "weakest_slot", "weakest_margin", "n_unvalued", "as_of"]
    out = []
    for r in rows:
        if r["role"] not in ("starter", "empty", "bench", "unplayable"):
            continue
        starter = r["role"] in ("starter", "empty")
        name = r.get("player_name")
        if r.get("gsis_id") and r["gsis_id"] in dp.index and isinstance(dp.loc[r["gsis_id"], "player_name"], str):
            name = dp.loc[r["gsis_id"], "player_name"]
        out.append({
            "role": "starter" if starter else r["role"], "slot": r["slot"] if starter else None,
            "slot_type": r["slot_type"] if starter else None, "slot_order": r["slot_order"] if starter else None,
            "bench_rank": r.get("bench_rank"), "gsis_id": r.get("gsis_id"), "sleeper_player_id": r.get("sleeper_player_id"),
            "player_name": name, "position": r.get("position"), "value": r.get("value"), "value_source": r.get("value_source"),
            "margin": r.get("margin"), "is_locked": bool(r.get("is_locked")), "is_empty_slot": r["role"] == "empty",
            "report_status": r.get("report_status"), "reason": None if starter else r.get("reason"),
            "is_weakest_slot": bool(starter and r["slot"] == tot.get("weakest_slot")),
            "lineup_value": tot.get("lineup_value") if starter else None, "bench_value": tot.get("bench_value") if starter else None,
            "weakest_slot": tot.get("weakest_slot") if starter else None, "weakest_margin": tot.get("weakest_margin") if starter else None,
            "n_unvalued": tot.get("n_unvalued") if starter else None, "as_of": tot.get("as_of") if starter else None})
    df = pd.DataFrame(out, columns=cols)
    if df.empty:
        return df
    # team: the board's (this week's), else dim_player's latest, else a DEF's Sleeper id (LAR -> LA) — LINEUP_SQL's rule
    def team(r) -> str | None:
        g = r["gsis_id"]
        if isinstance(g, str) and g in b.status.index and isinstance(b.status.loc[g, "team"], str):
            return b.status.loc[g, "team"]
        if isinstance(g, str) and g in dp.index and isinstance(dp.loc[g, "latest_team"], str):
            return dp.loc[g, "latest_team"]
        if r["position"] == "DEF":
            return LU.SLEEPER_TO_NFLVERSE_TEAM.get(r["sleeper_player_id"], r["sleeper_player_id"])
        return None
    df["team"] = df.apply(team, axis=1)
    for q in QUANTILES:
        df[q] = df["gsis_id"].map(lambda g, q=q: ranges.at[g, q] if isinstance(g, str) and g in ranges.index else np.nan)
        df[q] = pd.to_numeric(df[q], errors="coerce")
    sched = {}
    for r in games.sort_values("kickoff_at").itertuples():
        sched.setdefault(r.home_team, (r.kickoff_at, r.away_team))
        sched.setdefault(r.away_team, (r.kickoff_at, r.home_team))
    df["kickoff_at"] = df["team"].map(lambda tm: sched.get(tm, (None, None))[0])
    df["opponent"] = df["team"].map(lambda tm: sched.get(tm, (None, None))[1])
    df["kicked_off"] = df["kickoff_at"].map(lambda k: bool(k is not None and not pd.isna(k) and k <= as_of))
    ranks = query(OPP_RANK_SQL, ())
    rk = {(r.defense, r.position): r.rank_std for r in ranks.itertuples()}
    df["opp_rank"] = [rk.get((o, p)) for o, p in zip(df["opponent"], df["position"], strict=True)]
    for c in ("is_locked", "is_empty_slot", "kicked_off", "is_weakest_slot"):
        df[c] = df[c].fillna(False).astype(bool)
    df["locked_now"] = df["is_locked"] | df["kicked_off"]
    for c in ("value", "margin", "lineup_value", "bench_value", "weakest_margin"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    order = df["role"].map({"starter": 0, "bench": 1}).fillna(2)
    df = df.assign(_o=order, _v=-df["value"].fillna(-1e9)).sort_values(["_o", "slot_order", "bench_rank", "_v"], na_position="last")
    return df.drop(columns=["_o", "_v"]).reset_index(drop=True)


# ------------------------------------------------------------------------------ rest of season, priced on request
ROS_GAMES_SQL = "select week, home_team, away_team from analytics.dim_game where season = %s and season_type = 'REG'"
SD_PER_80 = 2.563          # an 80% range is 2 x 1.2816 sd wide (mart_player_ros_projection)
Z80 = 1.2816


def ros_window(league: Mapping, from_week: int, season_last_week: int, bracket_rounds: int | None = None) -> tuple[int, int, int | None]:
    """(from_week, last_week, playoff_week_start): mart_player_ros_projection's window. The final = the playoff
    start + the winners-bracket rounds x weeks per round - 1 (Sleeper ``playoff_round_type`` 1 adds a week to the
    final, 2 plays every round over two weeks); the rounds from the bracket when known, else ceil(log2(playoff
    teams)); never past the schedule's last week. A league without playoffs runs to the last week."""
    st = league.get("settings") or {}
    pws = int(st.get("playoff_week_start") or 0)
    if pws <= 0:
        return int(from_week), int(season_last_week), None
    teams = max(int(st.get("playoff_teams") or 2), 2)
    rtype = int(st.get("playoff_round_type") or 0)
    rounds = int(bracket_rounds) if bracket_rounds else math.ceil(math.log(teams) / math.log(2))
    last = pws - 1 + rounds * (2 if rtype == 2 else 1) + (1 if rtype == 1 else 0)
    return int(from_week), int(min(season_last_week, last)), pws


def ros_table(query: Query, league_id: str, league: Mapping, from_week: int, last_week: int,
              playoff_week_start: int | None, *, exclude_reference: str | None = None) -> pd.DataFrame:
    """Rest of season for every projected player in this league's scoring — mart_player_ros_projection's columns
    and rules, priced on request: each week of the window priced (``price_week``, cached), byes (no regular-season
    game for his team that week) excluded, the sum, the playoff subtotal, the 80% range with the weeks read as
    independent normals, and the ranks by position / overall among every projected player on an active NFL roster
    (a team defense always ranked) — the same population the mart ranks, when the league is a house league."""
    scoring, slots = league_scoring(league)
    season = int(league["season"])
    g = query(ROS_GAMES_SQL, (season,))
    plays = {(int(r.week), t) for r in g.itertuples() for t in (r.home_team, r.away_team)}
    frames, refs = [], set()
    for w in range(int(from_week), int(last_week) + 1):
        pr = price_week(query, league_id, scoring, slots, season, w, exclude_reference=exclude_reference)
        refs.add(pr.reference)
        st = pr.board.status
        sk = pd.DataFrame({"player_key": pr.proj.index, "gsis_id": pr.proj.index,
                           "position": pr.board.line["position"].reindex(pr.proj.index).to_numpy(),
                           "proj_points": pr.proj.round(2).to_numpy(),
                           "p10": pr.ranges["p10"].reindex(pr.proj.index).to_numpy(dtype=float),
                           "p90": pr.ranges["p90"].reindex(pr.proj.index).to_numpy(dtype=float)})
        for c in ("team", "roster_status", "player_name", "implied_team_total"):
            sk[c] = st[c].reindex(pr.proj.index).to_numpy() if c in st else None
        frames.append(sk.assign(week=w))
        for pos, kd in pr.kd.items():
            if kd.empty:
                continue
            frames.append(pd.DataFrame({"player_key": kd["unit_id"].to_numpy(),
                                        "gsis_id": kd["unit_id"].to_numpy() if pos == "K" else None,
                                        "position": pos, "proj_points": pd.to_numeric(kd["proj_points"]).round(2).to_numpy(),
                                        "p10": pd.to_numeric(kd["p10"]).to_numpy(dtype=float),
                                        "p90": pd.to_numeric(kd["p90"]).to_numpy(dtype=float),
                                        "team": kd["team"].to_numpy(), "roster_status": kd["roster_status"].to_numpy(),
                                        "player_name": kd["player_name"].to_numpy(),
                                        "implied_team_total": kd["implied_team_total"].to_numpy(), "week": w}))
    cols = ["player_key", "gsis_id", "position", "player_name", "team", "roster_status", "is_ranked", "from_week",
            "last_week", "playoff_week_start", "ros_games", "ros_points", "ros_points_per_game", "ros_p10", "ros_p90",
            "ros_sd", "playoff_games", "playoff_points", "ros_rank_pos", "ros_rank_all", "bye_weeks", "weeks_with_lines",
            "weeks_json"]
    if not frames:
        return pd.DataFrame(columns=cols)
    d = pd.concat(frames, ignore_index=True)
    d = d[d["proj_points"].notna()]
    d = d[[(int(w), t) in plays for w, t in zip(d["week"], d["team"], strict=True)]]      # byes are not projections
    if d.empty:
        return pd.DataFrame(columns=cols)
    d = d.sort_values(["player_key", "week"])
    pws = playoff_week_start if playoff_week_start else 10 ** 6
    d["var"] = ((d["p90"] - d["p10"]) / SD_PER_80) ** 2
    d["in_po"] = d["week"] >= pws
    grp = d.groupby("player_key", sort=False)
    first = grp.head(1).set_index("player_key")
    out = pd.DataFrame({
        "ros_games": grp.size(),
        "ros_points_raw": grp["proj_points"].sum(),
        "playoff_games": grp["in_po"].sum().astype(int),
        "playoff_points": d[d["in_po"]].groupby("player_key")["proj_points"].sum(),
        "ros_sd_raw": np.sqrt(grp["var"].sum()).where(grp["var"].count() == grp.size()),
        "weeks_with_lines": grp["implied_team_total"].count(),
        "weeks_json": grp.apply(lambda x: [[int(w), round(float(p), 2)] for w, p in zip(x["week"], x["proj_points"], strict=True)],
                                include_groups=False),
    })
    out["playoff_points"] = out["playoff_points"].fillna(0.0).round(2)
    for c in ("gsis_id", "position", "player_name", "team", "roster_status"):
        out[c] = first[c]
    out.index.name = None
    out["player_key"] = out.index
    out["is_ranked"] = (out["position"] == "DEF") | (out["roster_status"].fillna("ACT") == "ACT")
    out["from_week"], out["last_week"], out["playoff_week_start"] = int(from_week), int(last_week), playoff_week_start
    out["ros_points"] = out["ros_points_raw"].round(2)
    out["ros_points_per_game"] = (out["ros_points_raw"] / out["ros_games"]).round(2)
    out["ros_sd"] = out["ros_sd_raw"].round(2)
    out["ros_p10"] = np.clip(out["ros_points_raw"] - Z80 * out["ros_sd_raw"], 0, None).round(1)
    out["ros_p90"] = (out["ros_points_raw"] + Z80 * out["ros_sd_raw"]).round(1)
    teams_weeks = {(w, t) for (w, t) in plays}
    out["bye_weeks"] = [[w for w in range(int(from_week), int(last_week) + 1) if (w, t) not in teams_weeks]
                        for t in out["team"]]
    ranked = out[out["is_ranked"]].sort_values(["ros_points", "player_key"], ascending=[False, True])
    out["ros_rank_pos"] = ranked.groupby("position").cumcount() + 1
    out["ros_rank_all"] = pd.Series(np.arange(1, len(ranked) + 1), index=ranked.index)
    out = out.reset_index(drop=True)
    out.attrs["references"] = sorted(r for r in refs if r)
    return out[cols]


# ------------------------------------------------------------------------------ the league picker (a Sleeper username)
def _fmt(v: float) -> str:
    return f"{float(v):.3f}".rstrip("0").rstrip(".")


def scoring_label(league: Mapping) -> str:
    """dim_league_season.scoring_label's rule (plan U-10) for a league payload: "12-team superflex dynasty · full
    PPR · 6‑pt pass TD · yardage bonuses" (values rounded to 3 places; a missing pass_td left out; the non-breaking
    hyphen keeps "6‑pt" on one line)."""
    st = league.get("settings") or {}
    sc = league.get("scoring_settings") or {}
    slots = [str(x) for x in league.get("roster_positions") or []]
    teams = st.get("num_teams") or league.get("total_rosters")
    ltype = {2: "dynasty", 1: "keeper"}.get(int(st.get("type") or 0), "redraft")
    sf, qbs = slots.count("SUPER_FLEX"), slots.count("QB")
    head = " ".join(x for x in (f"{int(teams)}-team" if teams else None,
                                "superflex" if sf else (f"{qbs}QB" if qbs >= 2 else None), ltype) if x)
    rec = round(float(sc.get("rec") or 0), 3)
    rec_w = {0: "standard", 0.5: "half PPR", 1: "full PPR"}.get(rec) or f"{_fmt(rec)} PPR"
    pass_td = sc.get("pass_td")
    te = round(float(sc.get("bonus_rec_te") or 0), 3)
    yd_bonus = any(re.match(r"^bonus_.+_yd_", k) and round(float(v or 0), 3) != 0 for k, v in sc.items())
    parts = [head, rec_w, f"{_fmt(round(float(pass_td), 3))}\u2011pt pass TD" if pass_td is not None else None,
             "yardage bonuses" if yd_bonus else None, f"TE premium {_fmt(te)}" if te else None]
    return " · ".join(p for p in parts if p)


def user_leagues(username: str, season: int, *, client: Sleeper | None = None,
                 in_database: Callable[[str], bool] = lambda _lid: False) -> dict:
    """``/api/leagues?username=``: the user, then each of their NFL leagues of ``season`` with their own roster
    (``owner_id`` or a ``co_owners`` entry; None in a league they only run), their team name, the scoring label.
    Calls: 2 + 2 per league (rosters 10 min, users a day; cached), the per-league pairs in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    sl = client or sleeper()
    u = sl.user(username)
    uid = str(u["user_id"])
    leagues = [lg for lg in sl.user_leagues(uid, int(season)) if isinstance(lg, dict) and lg.get("league_id")]

    def one(lg: dict) -> dict:
        lid = check_id(str(lg["league_id"]))
        rosters, users = sl.rosters(lid), sl.users(lid)
        mine = next((r for r in rosters if str(r.get("owner_id")) == uid), None) or \
            next((r for r in rosters if uid in [str(x) for x in (r.get("co_owners") or [])]), None)
        rid = int(mine["roster_id"]) if mine else None
        names = team_names(rosters, users)
        return {"league_id": lid, "name": lg.get("name"), "season": int(lg.get("season") or season),
                "total_rosters": lg.get("total_rosters"), "scoring_label": scoring_label(lg), "roster_id": rid,
                "team_name": names.get(rid, {}).get("team_name") if rid is not None else None,
                "status": lg.get("status"), "in_database": bool(in_database(lid))}

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(leagues)))) as ex:
        rows = list(ex.map(one, leagues))
    rows.sort(key=lambda r: ((r["name"] or "").lower(), r["league_id"]))
    return {"user": {"user_id": uid, "username": u.get("username"), "display_name": u.get("display_name"),
                     "avatar": u.get("avatar")},
            "season": int(season), "leagues": rows}


# ------------------------------------------------------------------------------ fixtures (the sandbox cannot reach Sleeper)
LEAGUE_FIELDS = ("league_id", "name", "season", "season_type", "sport", "status", "total_rosters", "roster_positions",
                 "scoring_settings", "settings", "previous_league_id", "draft_id")
ROSTER_FIELDS = ("league_id", "roster_id", "owner_id", "co_owners", "players", "starters", "reserve", "taxi", "settings")
PLAYER_FIELDS = ("player_id", "full_name", "first_name", "last_name", "position", "fantasy_positions", "team", "status",
                 "injury_status", "active", "gsis_id")


def write_fixtures(conn, league_ids: list[str], out_dir: str | Path) -> dict[str, int]:
    """Sleeper's three league payloads + the rostered players' directory entries, from the ``raw.sleeper_*``
    payload columns (what Sleeper returned when the league was last fetched), trimmed to the fields the on-demand
    path reads (no avatars, nicknames or chat; managers and team names replaced by "Manager n" / "Team n"): ``league_<id>.json``, ``rosters_<id>.json``, ``users_<id>.json``,
    ``players_nfl.json``. ``conn``: a psycopg connection that can read ``raw``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    pids: set[str] = set()
    with conn.cursor() as cur:
        for lid in league_ids:
            cur.execute("select payload from raw.sleeper_league where league_id = %s", (lid,))
            row = cur.fetchone()
            if row is None:
                raise LeagueNotFound(f"raw.sleeper_league has no {lid}")
            league = {k: row[0].get(k) for k in LEAGUE_FIELDS}
            cur.execute("select payload from raw.sleeper_roster where league_id = %s order by roster_id", (lid,))
            rosters = [{k: p.get(k) for k in ROSTER_FIELDS} for (p,) in cur.fetchall()]
            cur.execute("select payload from raw.sleeper_league_user where league_id = %s order by user_id", (lid,))
            # league-mates' names stay out of git: "Manager 3" / "Team 3" (the path reads them only for the summary line)
            users = [{"user_id": p.get("user_id"), "display_name": f"Manager {i}", "league_id": p.get("league_id"),
                      "is_owner": p.get("is_owner"), "metadata": {"team_name": f"Team {i}"}}
                     for i, (p,) in enumerate(cur.fetchall(), 1)]
            for r in rosters:
                pids |= {str(x) for x in (r.get("players") or [])}
            (out / f"league_{lid}.json").write_text(json.dumps(league, indent=1, sort_keys=True))
            (out / f"rosters_{lid}.json").write_text(json.dumps(rosters, indent=1, sort_keys=True))
            (out / f"users_{lid}.json").write_text(json.dumps(users, indent=1, sort_keys=True))
            counts[lid] = len(rosters)
        cur.execute("select player_id, payload from raw.sleeper_player where player_id = any(%s)", (sorted(pids),))
        players = {pid: {k: p.get(k) for k in PLAYER_FIELDS if k in p} for pid, p in cur.fetchall()}
    (out / "players_nfl.json").write_text(json.dumps(players, indent=0, sort_keys=True))
    counts["players"] = len(players)
    return counts


def _main(argv: list[str] | None = None) -> None:
    """``python -m league_lab.anyleague fixtures <out_dir> <league_id> ...`` (pipeline role: it reads raw)."""
    import sys

    import psycopg

    from .config import get_settings

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[0] != "fixtures":
        raise SystemExit("usage: python -m league_lab.anyleague fixtures <out_dir> <league_id> [<league_id> ...]")
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        print(write_fixtures(conn, args[2:], args[1]))


if __name__ == "__main__":
    _main()
