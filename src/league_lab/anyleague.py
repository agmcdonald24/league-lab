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
3. **Pricing**: ``scoring.price_projected`` on the stat line in the league's scoring (Wave I-D: the flat engine, or
   expected bonuses under ``LEAGUE_LAB_EV_PRICING``) — the same function ``projections.price`` uses, so a known
   league reproduces ``proj_points`` exactly.
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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import ClassVar

import numpy as np
import pandas as pd

from . import clock, memo, provider_trouble  # ---- IP-5: provider_trouble
from . import lineup as LU
from .scoring import (  # noqa: F401 - compute_points: the reference the vector form equals
    MAPPED_KEYS,
    LeagueScoring,
    ScoringSpec,
    compute_points,
    compute_points_frame,  # ---- M3: moved to scoring (Wave I-D); re-exported, the API's tests import it from here
    ev_for_week,  # ---- M4 (Wave I-G): the mode the record sets, per week
    ev_pricing,
    expected_frame,
    kd_flat,
    price_projected,
    spec_of,
    unmapped_keys,
)
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
# ---- I0-B (Wave I-0): league keys with a platform prefix (``mfl:21861``) -> platforms.Router, which answers every
# call below in Sleeper's shapes (an MFL league is translated in platforms.py / mfl_client.py); Sleeper ids stay bare.
from . import platforms  # noqa: E402 - the block stays self-contained
from .mfl_client import FIXTURES_ENV as MFL_FIXTURES_ENV  # noqa: E402

check_id = platforms.check_key          # a Sleeper id or an ``mfl:<id>`` key (sleeper_client.check_id: Sleeper only)
_default: platforms.Router | None = None


def sleeper() -> platforms.Router:
    """The process-wide client (one cache, one token bucket per platform); rebuilt when a fixture setting changes
    (tests). Sleeper keys reach the Sleeper client untouched; ``mfl:`` keys the MyFantasyLeague translation."""
    global _default
    fx, mfx = os.environ.get(FIXTURES_ENV), os.environ.get(MFL_FIXTURES_ENV)
    if (_default is None or str(_default.fixtures or "") != str(Path(fx) if fx else "")
            or _default.mfl_fixtures != str(Path(mfx) if mfx else "")
            or _default.env != platforms.adapter_env()):           # ---- IK-3: the ESPN / Yahoo settings (tests)
        from .mfl_client import MFL
        _default = platforms.Router(Sleeper(), MFL())
    return _default
# ---- end I0-B


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
    # INF-2 (Wave I-J): one Board per (query, season, week, source) for the whole process (``load_board``'s
    # ``boards`` region), shared by every league priced on it; counted once, in that region, not in each Priced
    _memo_shared: ClassVar[bool] = True


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


# ---- INF-2 (Wave I-J, the memory diet): one Board per week for every league. A Board is NFL-wide (the stat lines, the
# reference scorings' ranges, status, K / DEF): every league priced on the week reads the same one, so it is built once
# and kept 10 minutes (the SQL results' TTL), at most BOARD_MAX weeks, in the memory budget's ``boards`` region. Nothing
# mutates a Board after construction (every consumer reads ``line`` / ``status`` / ``fitted`` / ``kd``; checked by
# grep at INF-2) and pandas 3's copy-on-write keeps a frame derived from one from writing into it. Keyed on the
# ``query`` callable too: a test's stand-in query never sees the database's board.
BOARD_TTL_S = 600
BOARD_MAX = 20
_boards = memo.region("boards", ttl=BOARD_TTL_S, max_entries=BOARD_MAX)


def load_board(query: Query, season: int, week: int, source: str | None = None, *, cache: bool = True) -> Board:
    """The week's board: F1's NFL-wide tables when they exist and hold the week (``nfl_wide``), else E3's borrowing
    from ``ops.projections`` (``borrow``). ``source`` / ``LEAGUE_LAB_BOARD_SOURCE`` force one. INF-2: the same object
    for every caller for 10 minutes (``cache=False``: a fresh one, not kept)."""
    src = source or board_source()
    key = (query, int(season), int(week), src)
    if cache:
        hit = _boards.get(key)
        if hit is not None:
            return hit
    if src == "nfl_wide" or (src == "auto" and nfl_wide_ready(query, season, week)):
        b = _load_nfl_wide(query, season, week)
    else:
        b = _load_borrowed(query, season, week)
    if cache:
        _boards.put(key, b)
    return b


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


def price_lines(line: pd.DataFrame, scoring: Mapping[str, float] | ScoringSpec, *, season: int | None = None,
                week: int | None = None) -> pd.Series:   # ---- M4: season / week when the frame does not carry them
    """League points of every PROJECTED stat line, every row at once: ``scoring.price_projected`` — the one entry point
    ``projections.price`` (the nightly) calls too, so a house league reproduces its nightly ``proj_points`` to the bit
    under either state of ``LEAGUE_LAB_EV_PRICING``.

    Wave I-C (IC-1): the league's ``ScoringSpec`` decides — an MFL spec (per-position rules, TDs by distance, ``1/10``
    yards) prices with ``scoring.expected_frame`` per row position (units through ``ScoringSpec.rules_for``: TMQB ->
    QB's rules). Wave I-D (M3): a Sleeper scoring (a flat dict or a ``LeagueScoring``) prices on the flat engine
    (``compute_points_frame``) unless the flag is on AND it has a yardage or long-TD bonus (``scoring.ev_moves``)."""
    stats = line[list(STAT_LINE)].rename(columns=STAT_LINE).apply(pd.to_numeric, errors="coerce").fillna(0.0)
    if "position" in line:          # F1: a position premium (bonus_rec_te, …) prices only when the row carries the position
        stats["position"] = line["position"].to_numpy()
    # ---- M3 (Wave I-D): IC-1's own branch folded into the shared entry point
    # ---- M4 (Wave I-G): the mode follows the record (``scoring.ev_for_week``): a week the record holds is priced as
    # its rows were (a frozen week keeps its label), any other week as the newest build; the env overrides. The week
    # comes from the frame's ``week`` / ``season`` columns, else the caller's (``price_board``: the board's week)
    if len(line) and ("week" in line or week is not None):
        wk = (pd.to_numeric(line["week"], errors="coerce") if "week" in line else pd.Series(float(week), index=line.index))
        se = (pd.to_numeric(line["season"], errors="coerce") if "season" in line
              else pd.Series(np.nan if season is None else float(season), index=line.index))
        sa, wa = se.fillna(-1).astype(int).to_numpy(), wk.fillna(-1).astype(int).to_numpy()
        modes = {(a, b): ev_for_week(None if a < 0 else int(a), None if b < 0 else int(b))
                 for a, b in set(zip(sa.tolist(), wa.tolist(), strict=True))}
        if len(set(modes.values())) > 1:
            out = np.full(len(line), np.nan)
            for (a, b), ev in modes.items():
                sel = (sa == a) & (wa == b)
                out[sel] = price_projected(stats[sel], scoring, ev=ev)
            return pd.Series(out, index=line.index, dtype=float)
        return pd.Series(price_projected(stats, scoring, ev=next(iter(modes.values()))), index=line.index, dtype=float)
    # ---- /M4
    return pd.Series(price_projected(stats, scoring), index=line.index, dtype=float)
    # ---- /M3


# ------------------------------------------------------------------------------ ranges for a league the model never saw
def _mapped(scoring: Mapping[str, float]) -> dict[str, float]:
    """The scoring keys the stat line prices (scoring.MAPPED_KEYS), non-zero, rounded to 3 places (Sleeper stores
    float32: 0.05000000074505806 is 0.05) — what "the same scoring" means for choosing a reference."""
    sp = getattr(scoring, "spec", None)   # ---- IC-1: a non-Sleeper spec never equals a reference's flat keys
    if sp is not None and sp.flat is None:
        return {"__spec__": sp.key()}
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
    flat = kd_flat(spec_of(scoring), position)       # ---- IC-1: K / DEF keys from the spec (Sleeper: unchanged)
    rows["proj_points"] = kdef.price(rows.reset_index(drop=True), position, flat, "proj_")   # (kdef.price reads a spec too)
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
    # ---- IC-1: the spec's own account — ``priced`` (the read-back), ``approximated`` (the words), ``unpriced``
    spec = spec_of(scoring)
    approx = list(spec.approximated)
    if spec.flat is None:          # an MFL spec: the flat keys above are a summary, the spec's lists are the truth
        unm = [f"{u['name']} ({u['event']})" for u in spec.unpriced]
        not_proj = sorted({s for p in ("QB", "RB", "WR", "TE") if (r := spec.rules_for(p)) is not None
                           for s in [*r.rates, *r.bands, *r.steps] if s not in line_cols}
                          | {f for p in ("QB", "RB", "WR", "TE") if (r := spec.rules_for(p)) is not None
                             for f in r.distance if f in ("return_tds", "fumble_recovery_tds")})
    if any(r.distance for p, r in spec.positions.items() if p in ("QB", "RB", "WR", "TE")) and (spec.flat is None or ev_pricing()):
        approx.append("touchdowns by distance on a projection: the projected touchdowns × the share of touchdowns that "
                      "long at the position (placeholder shares until the measured ones land)")
    if any(r.steps for r in spec.positions.values()):
        approx.append("yards paid per whole 10 (or 20): a projection prices the expected whole tens (a 57-yard "
                      "projection is worth about 5.2, not 5.7)")
    return {"unmapped": sorted(unm), "not_projected": sorted(not_proj), "priced": spec.readback(),
            "approximated": approx, "unpriced": [f"{u['name']} ({u['event']})" for u in spec.unpriced]}
    # ---- /IC-1


def team_names(rosters: list[dict], users: list[dict]) -> dict[int, dict]:
    """roster_id -> team_name / manager_name, the dim_league_member rule (team name, else display name)."""
    by_user = {u.get("user_id"): u for u in users}
    out = {}
    for r in rosters:
        u = by_user.get(r.get("owner_id")) or {}
        tn = ((u.get("metadata") or {}).get("team_name") or "").strip() or None
        dn = u.get("display_name")
        # ---- IC-4: an MFL franchise without a shared owner name has no manager name (was the team name repeated)
        out[int(r["roster_id"])] = {"team_name": tn or dn or f"Roster {r['roster_id']}",
                                    "manager_name": dn or (None if u.get("platform") in ("mfl", "espn", "yahoo")  # IK-3
                                                           else "unknown")}
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
    # IC-2: team units (MFL's TMQB / TMPK) priced this week: one row per (position, nflverse team) — proj_points,
    # p10…p90, the starter whose range it carries (``price_units``); empty in a league without unit slots
    units: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=UNIT_COLUMNS))
    # INF-2: a Priced is counted in the memory budget's ``priced`` region; a LeagueWeeks or a decision memo holding it
    # does not count it again
    _memo_shared: ClassVar[bool] = True


PRICED_TTL_S = 600                         # the board changes once a night; a league's scoring almost never
# INF-2: the memory budget's ``priced`` region (was a dict cleared when it passed 500 entries); a Priced's ``board`` is
# the shared Board (counted in ``boards``), so an entry here is only the league's own proj / ranges / kd / units
_priced = memo.region("priced", ttl=PRICED_TTL_S)


def _scoring_key(scoring: Mapping[str, float]) -> str:
    sp = getattr(scoring, "spec", None)   # ---- IC-1: two MFL leagues with one flat summary may differ in the spec
    extra = {"__spec__": sp.key()} if sp is not None and sp.flat is None else {}
    return json.dumps({k: round(float(v), 6) for k, v in sorted(scoring.items())} | extra)


def price_week(query: Query, league_id: str, scoring: Mapping[str, float], slots: list[str], season: int, week: int, *,
               board: Board | None = None, exclude_reference: str | None = None, cache: bool = True) -> Priced:
    """Price a week's board in a league's scoring (skill lines, ranges, K / DEF) — cached 10 minutes per (scoring,
    slots' K / DEF, week, exclusion) in-process, so the rest-of-season sum and every request of the same league reuse it."""
    starts, units = kd_starts(slots), unit_starts(slots)          # IC-2: from the slots' eligibility sets
    key = (str(league_id), _scoring_key(scoring), starts, units, int(season), int(week), exclude_reference, board_source(),
           ev_for_week(season, week))   # ---- M4: a week priced in the other mode is another answer
    hit = _priced.get(key) if cache and board is None else None
    if hit is not None:
        return hit
    t0 = time.perf_counter()
    b = board or load_board(query, season, week, cache=cache)
    t1 = time.perf_counter()
    out = price_board(b, league_id, scoring, starts, exclude_reference=exclude_reference, t0=t0, t1=t1, units=units)
    if cache and board is None:
        _priced.put(key, out)
    return out


def price_board(b: Board, league_id: str, scoring: Mapping[str, float], starts: tuple[str, ...], *,
                exclude_reference: str | None = None, t0: float | None = None, t1: float | None = None,
                units: tuple[str, ...] = ()) -> Priced:
    """One week's board priced in a league's scoring (``price_week``'s body): the skill lines, the reference's ranges,
    K / DEF."""
    t0 = time.perf_counter() if t0 is None else t0
    t1 = time.perf_counter() if t1 is None else t1
    proj = price_lines(b.line, scoring, season=b.season, week=b.week)   # ---- M4: the board's week decides the mode
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
    unit_rows = price_units(b, scoring, proj, ranges, kd, units) if units else pd.DataFrame(columns=UNIT_COLUMNS)  # IC-2
    t4 = time.perf_counter()
    return Priced(str(league_id), int(b.season), int(b.week), b, proj, ranges, ref, kd, kd_src,
                  {"board": round((t1 - t0) * 1000, 1), "price": round((t2 - t1) * 1000, 1),
                   "ranges": round((t3 - t2) * 1000, 1), "kd": round((t4 - t3) * 1000, 1)}, unit_rows)


# ---- IC-2 (Wave I-C): slots as eligibility sets, team units priced from their team's lines
UNIT_COLUMNS = ["position", "team", "proj_points", *QUANTILES, "starter_gsis", "starter_name", "n_players"]
UNIT_SKIP_STATUS = ("Out", "Doubtful")              # a quarterback who will not play is not part of his team's unit
UNIT_QB_RULE = "starter"                            # TMQB = the starter's line ("sum": every playing QB's; unit_lines)


def slot_positions(slots: Iterable[str]) -> frozenset[str]:
    """Every position some starting slot admits (``lineup.parse_slots``' eligibility sets)."""
    return frozenset().union(*(s.elig for s in LU.parse_slots(slots)[0]))


def kd_starts(slots: Iterable[str]) -> tuple[str, ...]:
    """The K / DEF frames a league needs priced: K for a K slot or a team kicker (TMPK is priced from the team's
    kicker), DEF for a DEF / TMDEF slot."""
    el = slot_positions(slots)
    return tuple(p for p in ("K", "DEF") if p in el or (p == "K" and "TMPK" in el))


def unit_starts(slots: Iterable[str]) -> tuple[str, ...]:
    el = slot_positions(slots)
    return tuple(u for u in ("TMQB", "TMPK") if u in el)


def unit_lines(b: Board, proj: pd.Series | None = None, rule: str | None = None) -> pd.DataFrame:
    """TMQB's stat line per NFL team (nflverse code, the index). ``rule`` (default ``UNIT_QB_RULE``):

    * ``starter`` — the line of the team's best-projected quarterback who can play (by ``proj``, this league's points,
      when given, else passing yards; Out / Doubtful / NFL injured reserve left out unless that leaves none);
    * ``sum`` — the sum of the team's playing quarterbacks' lines (the brief's first reading). Measured on the week-4
      board the backups' lines are not near 0 (KC +6.5 points, ATL +13.1 over the starter in a 4-pt pass TD scoring):
      each line is projected on its own, so the sum counts the team's passing volume more than once.

    ``position`` "TMQB" (the spec prices it with the QB rules: ``lineup.UNIT_PRICES_AS``); ``starter_gsis``: the
    quarterback whose range the unit carries; ``n_players``: the quarterbacks in the line."""
    rule = rule or UNIT_QB_RULE
    cols = ["position", *STAT_LINE, "starter_gsis", "n_players"]
    qb = b.line[b.line["position"] == "QB"]
    if qb.empty or b.status is None or b.status.empty or "team" not in b.status:
        return pd.DataFrame(columns=cols)
    st = b.status.reindex(qb.index)
    team = st["team"]
    out_ = pd.Series(False, index=qb.index)
    if "report_status" in st:
        out_ |= st["report_status"].isin(UNIT_SKIP_STATUS)
    if "roster_status" in st:
        out_ |= st["roster_status"].eq("RES")
    rank = (proj.reindex(qb.index) if proj is not None else qb["proj_passing_yards"]).astype(float).fillna(-1e9)
    rows = {}
    # ---- IO-2 (Wave I-O): the stat lines made numeric once, not once per team (the same numbers; the MFL League
    # screen's first load spent ~1 s here: 32 teams × 15 weeks of a column-wise apply)
    num = qb[list(STAT_LINE)].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    # ---- end IO-2
    for t, idx in qb.groupby(team).groups.items():
        if not isinstance(t, str) or not t:
            continue
        keep = [g for g in idx if not out_.get(g, False)] or list(idx)
        starter = rank.loc[keep].idxmax()
        keep = keep if rule == "sum" else [starter]
        line = num.loc[keep].sum()                                          # ---- IO-2: was a per-team apply
        rows[t] = {"position": "TMQB", **line.to_dict(), "starter_gsis": starter, "n_players": len(keep)}
    return pd.DataFrame.from_dict(rows, orient="index", columns=cols)


def price_units(b: Board, scoring: Mapping[str, float], proj: pd.Series, ranges: pd.DataFrame,
                kd: Mapping[str, pd.DataFrame], units: Iterable[str]) -> pd.DataFrame:
    """The week's team units in this league's scoring, one row per (position, nflverse team): TMQB = ``unit_lines``
    priced through ``price_lines`` (the same entry point as every stat line: IC-1's spec prices it as QB), its range
    the starter's shifted onto the unit's points; TMPK = the team's kicker from ``kd_values`` (K by team, the best
    projected when there are two), his range. TMDEF is a DEF (``kd_values``)."""
    out = []
    if "TMQB" in units:
        ul = unit_lines(b, proj)
        if not ul.empty:
            pts = price_lines(ul, scoring)
            for t, r in ul.iterrows():
                g = r["starter_gsis"]
                row = {"position": "TMQB", "team": t, "proj_points": round(float(pts[t]), 2), "starter_gsis": g,
                       "starter_name": b.status.at[g, "player_name"] if "player_name" in b.status and g in b.status.index else None,
                       "n_players": int(r["n_players"])}
                for q in QUANTILES:
                    v = ranges.at[g, q] if g in ranges.index and q in ranges else np.nan
                    pg = proj.get(g, np.nan)
                    row[q] = (round(max(0.0, float(pts[t]) + float(v) - float(pg)), 2)
                              if pd.notna(v) and pd.notna(pg) else np.nan)
                out.append(row)
    if "TMPK" in units:
        k = kd.get("K")
        if k is not None and not k.empty:
            k = k.assign(_p=pd.to_numeric(k["proj_points"], errors="coerce")).dropna(subset=["_p"])
            k = k[k["team"].map(lambda x: isinstance(x, str) and bool(x))]
            for t, g in k.sort_values("_p", ascending=False).groupby("team", sort=False):
                r = g.iloc[0]
                out.append({"position": "TMPK", "team": t, "proj_points": round(float(r["_p"]), 2),
                            "p10": pd.to_numeric(r.get("p10"), errors="coerce"), "p25": np.nan, "p50": np.nan,
                            "p75": np.nan, "p90": pd.to_numeric(r.get("p90"), errors="coerce"),
                            "starter_gsis": r["unit_id"], "starter_name": r.get("player_name"), "n_players": len(g)})
    return pd.DataFrame(out, columns=UNIT_COLUMNS)


def unit_map(league_id: str, priced: Mapping[int, Priced]) -> dict[tuple[str, int, str, str], dict]:
    """``LineupInputs.unit_proj`` from the priced weeks: (league, week, unit position, nflverse team) -> the value."""
    out = {}
    for w, pr in priced.items():
        for r in pr.units.itertuples():
            out[(league_id, int(w), r.position, r.team)] = {"proj_points": None if pd.isna(r.proj_points) else float(r.proj_points),
                                                            "team": r.team, "report_status": None, "roster_status": None}
    return out


def unit_value(pr: Priced, position: str, team: str | None) -> dict | None:
    """One unit's priced row this week (``team`` in Sleeper's or nflverse's code), or None."""
    if not team or pr.units.empty:
        return None
    t = LU._team(team)
    m = pr.units[(pr.units["position"] == position) & (pr.units["team"] == t)]
    return None if m.empty else m.iloc[0].to_dict()
# ---- end IC-2


# ---- IC-4 (Wave I-D): the team units in the rest of season. Each week of the window prices a unit by the week's own
# rule (``price_units``: TMQB = the line of the team's best-projected quarterback who can play that week, priced
# through ``price_lines`` as TMQB; TMPK = the team's best-projected kicker that week), its range the starter's; a bye is
# a week off (``_ros_table`` drops a team's rows in a week it does not play). The rows are keyed by the league's
# directory (a rostered unit under its MFL id, ``mfl:0656``; the others ``mfl:TMQB-KC``), so the trade board's
# rest-of-season weeks and "Value to my lineup" find them under the key the rosters carry.
UNIT_ROS_EXTRA = ["unit", "starter_gsis", "starter_name"]


def unit_window(win: Window, weeks: list[int], scoring: Mapping[str, float], sk: pd.DataFrame, kfr: pd.DataFrame | None,
                units: Iterable[str]) -> pd.DataFrame:
    """The units' rows of ``weeks`` on the NFL-wide window (``_ros_table``'s fast path): ``sk`` = ``skill_window``'s
    frame (the week's priced QB lines rank the starters and carry the ranges), ``kfr`` = ``kd_window(…, "K")``.
    Columns: ``_kd_frame``'s + the stat line (TMQB: the starter's) + ``starter_gsis`` / ``starter_name``."""
    from types import SimpleNamespace
    units = tuple(units)
    rows: list[dict] = []
    if "TMQB" in units and not win.lines.empty and not sk.empty:
        qb = win.lines[win.lines["week"].isin(weeks) & (win.lines["position"] == "QB")]
        st = win.status if not win.status.empty else pd.DataFrame(columns=["week", "gsis_id"])
        for w, lw in qb.groupby("week"):
            line = lw.drop_duplicates("gsis_id").set_index("gsis_id")
            status = st[st["week"] == w].drop_duplicates("gsis_id").set_index("gsis_id")
            skw = sk[sk["week"] == w].drop_duplicates("gsis_id").set_index("gsis_id")
            ul = unit_lines(SimpleNamespace(line=line, status=status), skw["proj_points"])
            if ul.empty:
                continue
            pts = price_lines(ul, scoring)
            for t, r in ul.iterrows():
                g = r["starter_gsis"]
                p = float(pts[t])
                pg = skw["proj_points"].get(g, np.nan)
                rng = {q: (round(max(0.0, p + float(skw.at[g, q]) - float(pg)), 2)
                           if g in skw.index and pd.notna(skw.at[g, q]) and pd.notna(pg) else np.nan) for q in ("p10", "p90")}
                rows.append({"player_key": f"TMQB-{t}", "gsis_id": None, "position": "TMQB", "proj_points": round(p, 2),
                             **rng, "team": t, "roster_status": "ACT", "player_name": None, "implied_team_total": None,
                             "week": int(w), **{c: float(r[c]) for c in STAT_LINE},
                             "starter_gsis": g, "starter_name": status["player_name"].get(g) if "player_name" in status else None})
    if "TMPK" in units and kfr is not None and not kfr.empty:
        k = kfr.assign(_p=pd.to_numeric(kfr["proj_points"], errors="coerce")).dropna(subset=["_p"])
        k = k[k["team"].map(lambda x: isinstance(x, str) and bool(x))]
        for (w, t), g in k.sort_values("_p", ascending=False).groupby(["week", "team"], sort=False):
            r = g.iloc[0]
            rows.append({"player_key": f"TMPK-{t}", "gsis_id": None, "position": "TMPK", "proj_points": round(float(r["_p"]), 2),
                         "p10": pd.to_numeric(r.get("p10"), errors="coerce"), "p90": pd.to_numeric(r.get("p90"), errors="coerce"),
                         "team": t, "roster_status": "ACT", "player_name": None, "implied_team_total": None, "week": int(w),
                         "starter_gsis": r["unit_id"], "starter_name": r.get("player_name")})
    return pd.DataFrame(rows)


def units_priced_frame(pr: Priced, w: int) -> pd.DataFrame:
    """One week's ``Priced.units`` as rest-of-season rows (the slow path: ``price_week`` priced them)."""
    if pr.units is None or pr.units.empty:
        return pd.DataFrame()
    u = pr.units
    out = pd.DataFrame({"player_key": [f"{p}-{t}" for p, t in zip(u["position"], u["team"], strict=True)],
                        "gsis_id": None, "position": u["position"].to_numpy(),
                        "proj_points": pd.to_numeric(u["proj_points"]).round(2).to_numpy(),
                        "p10": pd.to_numeric(u["p10"], errors="coerce").to_numpy(dtype=float),
                        "p90": pd.to_numeric(u["p90"], errors="coerce").to_numpy(dtype=float),
                        "team": u["team"].to_numpy(), "roster_status": "ACT", "player_name": None,
                        "implied_team_total": None, "week": int(w),
                        "starter_gsis": u["starter_gsis"].to_numpy(), "starter_name": u["starter_name"].to_numpy()})
    line = pr.board.line
    for c in STAT_LINE:            # TMQB: the starter's line (the pieces of "why this number"); TMPK: none
        out[c] = [float(line.at[g, c]) if p == "TMQB" and g in line.index and pd.notna(line.at[g, c]) else np.nan
                  for p, g in zip(out["position"], out["starter_gsis"], strict=True)]
    return out


def unit_directory(league_id: str) -> dict[tuple[str, str], dict]:
    """(unit position, nflverse team) -> {player_key, player_name} from the league's directory: a unit a roster of THIS
    league carries under its MFL id (``mfl:0656``), the others under ``mfl:TMQB-KC``. Empty for a league without units."""
    if not platforms.is_mfl(league_id):
        return {}
    r = sleeper()
    try:
        r.rosters(league_id)                     # registers the league's units in the directory (cached calls)
        mf = r.mfl
    except (LeagueNotFound, AttributeError):     # ---- IP-5: refused / failed raises (the caller keeps nothing)
        return {}
    mine = {k for k, how in mf.mapping.get(platforms.mfl_id(league_id), {}).values() if how == "unit"}
    out: dict[tuple[str, str], dict] = {}
    for key, row in list(mf.extra_players.items()):
        if not row.get("unit") or not row.get("team"):
            continue
        k = (str(row.get("position")), LU._team(row.get("team")))
        if k not in out or key in mine:
            out[k] = {"player_key": key, "player_name": row.get("full_name") or row.get("player_name")}
    return out


def unit_keys(league_id: str, out: pd.DataFrame) -> pd.DataFrame:
    """Rename the rest-of-season frame's unit rows (``TMQB-CIN``) to the directory's keys and names."""
    if out.empty or "unit" not in out or not out["unit"].fillna(False).astype(bool).any():
        return out
    d = unit_directory(league_id)
    out = out.copy()
    for i in out.index[out["unit"].fillna(False).astype(bool)]:
        pos, team = out.at[i, "position"], out.at[i, "team"]
        hit = d.get((str(pos), str(team)))
        name = hit["player_name"] if hit else f"{team} {'QB' if pos == 'TMQB' else 'K'}"
        out.at[i, "player_key"] = hit["player_key"] if hit else f"{platforms.PREFIX}{pos}-{team}"
        out.at[i, "player_name"] = name
    return out
# ---- end IC-4


def clear_priced() -> None:
    _priced.clear()
    _ros_cache.clear()
    _boards.clear()            # INF-2: the shared boards go with the priced weeks built on them


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
        if gsis is None and position != "DEF" and position not in LU.UNITS:     # IC-2: a team unit has no gsis by design
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
        kd_proj=kd_proj, k_team_proj=k_team, unit_proj=unit_map(league_id, {int(week): pr}))   # IC-2: team units
    rows, totals, _ = LU.build(inp, as_of=as_of)
    return rows, totals, unmapped, dp, g


def league_scoring(league: Mapping) -> tuple[dict[str, float], list[str]]:
    """(the flat ``scoring_settings`` as a ``LeagueScoring`` carrying the league's ``ScoringSpec``, the slots)."""
    scoring = LeagueScoring({k: float(v) for k, v in (league.get("scoring_settings") or {}).items() if v is not None})
    scoring.spec = league_spec(league)
    return scoring, [str(s) for s in league.get("roster_positions") or []]


# ---- IC-1 (Wave I-C): the league's scoring spec
def league_spec(league: Mapping) -> ScoringSpec:
    """``league["scoring_spec"]`` (JSON) when the translation put one there, else MFL's report's ``spec``, else the
    Sleeper settings compiled (``scoring.from_sleeper``)."""
    from .scoring import ScoringSpec as _S
    from .scoring import from_sleeper
    raw = league.get("scoring_spec") or ((league.get("mfl") or {}).get("scoring") or {}).get("spec")
    if raw:
        return _S.from_json(raw)
    return from_sleeper({k: float(v) for k, v in (league.get("scoring_settings") or {}).items() if v is not None})
# ---- /IC-1


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
    as_of = as_of or clock.now()  # ---- INF-1
    pr = price_week(query, league_id, scoring, slots, season, week, board=board, exclude_reference=exclude_reference)
    t["priced"] = time.perf_counter()
    rows, totals, unmapped, dp, g = _solve_roster(query, league_id, roster, players, pr, slots, as_of)
    t["solve"] = time.perf_counter()
    frame = _cards_frame(query, rows, totals[0] if totals else {}, pr.ranges, pr.board, dp, g, as_of,
                         units=pr.units, players=players)                                          # IC-2
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
    # Wave I-C (PO): a league can play a double header (MFL 70587 plays twice in weeks 2, 4, 6–9, 11 and 13): one
    # matchup row per game for the same roster — the first opponent is the answer, the rest ride in ``also``
    mines = [m for m in ms if int(m.get("roster_id", -1)) == int(roster_id) and m.get("matchup_id") is not None]
    opps = [o for mine in mines for o in ms
            if o.get("matchup_id") == mine.get("matchup_id") and int(o.get("roster_id", -1)) != int(roster_id)]
    if not mines or not opps:
        return None
    rosters, users = sl.rosters(league_id), sl.users(league_id)
    names = team_names(rosters, users)
    pr = None
    if solve and query is not None:
        league = sl.league(league_id)
        scoring, slots = league_scoring(league)
        pr = price_week(query, league_id, scoring, slots, int(league["season"]), int(week),
                        exclude_reference=exclude_reference)

    def one(opp: dict) -> dict:
        oid = int(opp["roster_id"])
        nm = names.get(oid, {})
        d = {"roster_id": oid, "team_name": nm.get("team_name"), "manager": nm.get("manager_name"),
             "matchup_id": int(opp["matchup_id"]), "lineup_value": None}
        roster = next((r for r in rosters if int(r.get("roster_id", -1)) == oid), None)
        if pr is not None and roster is not None:
            _, totals, _, _, _ = _solve_roster(query, league_id, roster, sl.players(), pr, slots, as_of or clock.now())  # ---- INF-1
            if totals and totals[0].get("lineup_value") is not None:
                d["lineup_value"] = round(float(totals[0]["lineup_value"]), 2)
        return d

    out = one(opps[0])
    if len(opps) > 1:
        out["also"] = [one(o) for o in opps[1:]]
    return out


def _cards_frame(query: Query, rows: list[dict], tot: dict, ranges: pd.DataFrame, b: Board, dp: pd.DataFrame,
                 games: pd.DataFrame, as_of: datetime, *, units: pd.DataFrame | None = None,
                 players: Mapping[str, dict] | None = None) -> pd.DataFrame:
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
        if r["position"] in LU.UNITS:                  # IC-2: a team unit's team is its directory row's
            return LU._team(((players or {}).get(r["sleeper_player_id"]) or {}).get("team"))
        return None
    df["team"] = df.apply(team, axis=1)
    for q in QUANTILES:
        df[q] = df["gsis_id"].map(lambda g, q=q: ranges.at[g, q] if isinstance(g, str) and g in ranges.index else np.nan)
        df[q] = pd.to_numeric(df[q], errors="coerce")
    # ---- IC-2: a team unit's range (its starter's, shifted onto the unit's points)
    if units is not None and not units.empty:
        uk = units.set_index(["position", "team"])
        m = df["position"].isin(LU.UNITS)
        for q in QUANTILES:
            df.loc[m, q] = [pd.to_numeric(uk[q].get((p, t), np.nan), errors="coerce") if isinstance(t, str) else np.nan
                            for p, t in zip(df.loc[m, "position"], df.loc[m, "team"], strict=True)]
    # ---- end IC-2
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


# --- Wave H (H1): the NFL-wide board for a window of weeks in one round of queries (rest of season). The per-week
# reads of _load_nfl_wide with "week between" instead of "week =": the same distinct-on rule per week.
LINES_WINDOW_SQL = f"""
select distinct on (week, gsis_id) week, gsis_id, position, model_version, frozen_source, {_COMPS}
from {NFL_WIDE['lines']}
where season = %s and week between %s and %s and position = any(%s)
order by week, gsis_id, {_FRESHEST}
"""
RANGES_WINDOW_SQL = f"""
select distinct on ({NFL_WIDE['scoring_name']}, week, gsis_id) {NFL_WIDE['scoring_name']} as scoring_name, week, gsis_id,
       position, proj_points, p10, p25, p50, p75, p90
from {NFL_WIDE['ranges']}
where season = %s and week between %s and %s and {NFL_WIDE['scoring_name']} = any(%s) and position = any(%s)
order by {NFL_WIDE['scoring_name']}, week, gsis_id, {_FRESHEST}
"""
KD_LINES_WINDOW_SQL = f"""
select l.*, u.team, u.report_status, u.roster_status, u.player_name, u.implied_team_total
from (select distinct on (week, position, {NFL_WIDE['kd_unit']}) *
      from {NFL_WIDE['kd_lines']} where season = %s and week between %s and %s
      order by week, position, {NFL_WIDE['kd_unit']}, {_FRESHEST}) as l
left join analytics.mart_kd_week as u
  on u.position = l.position and u.unit_id = l.{NFL_WIDE['kd_unit']} and u.season = l.season and u.week = l.week
"""
KD_RANGES_WINDOW_SQL = f"""
select distinct on ({NFL_WIDE['scoring_name']}, week, position, {NFL_WIDE['kd_unit']})
       {NFL_WIDE['scoring_name']} as scoring_name, week, position, {NFL_WIDE['kd_unit']} as unit_id, proj_points, p10, p90
from {NFL_WIDE['kd_ranges']} where season = %s and week between %s and %s
order by {NFL_WIDE['scoring_name']}, week, position, {NFL_WIDE['kd_unit']}, {_FRESHEST}
"""
STATUS_WINDOW_SQL = """
select distinct on (week, gsis_id) week, gsis_id, team, report_status, roster_status, player_name, implied_team_total
from analytics.mart_player_week_projections
where season = %s and week between %s and %s and gsis_id is not null
order by week, gsis_id, league_id
"""
# ---- INF-2 (Wave I-J): the SQL whose results only go into a Board (``load_board``) or a Window (``load_window``). The
# API keeps those products (the memory budget's ``boards`` region; the league's rest-of-season table in ``ros``), not
# the raw results as well: league_lab_api.ondemand registers these with ``db.not_kept``.
BOARD_INPUT_SQL = (BOARD_SQL, KD_SQL, LINES_SQL, RANGES_SQL, KD_LINES_SQL, KD_RANGES_SQL, STATUS_SQL,
                   LINES_WINDOW_SQL, RANGES_WINDOW_SQL, KD_LINES_WINDOW_SQL, KD_RANGES_WINDOW_SQL, STATUS_WINDOW_SQL)


@dataclass
class Window:
    """The NFL-wide board of weeks ``first``..``last`` read in one round of queries (``_load_nfl_wide``'s reads with
    "week between" instead of "week =", the same distinct-on rule per week); every frame carries ``week``."""
    lines: pd.DataFrame        # week, gsis_id, position, model_version, the 12 components (QB-TE)
    ranges: pd.DataFrame       # scoring_name, week, gsis_id, proj_points, p10-p90 (QB-TE)
    kd: pd.DataFrame           # week, position, unit_id, the K / DEF line, team, report_status, roster_status, player_name, …
    kd_ranges: pd.DataFrame    # scoring_name, week, position, unit_id, proj_points, p10, p90
    status: pd.DataFrame       # week, gsis_id, team, report_status, roster_status, player_name, implied_team_total
    scorings: dict[str, dict[str, float]]
    weeks: list[int]           # the weeks holding stat lines


def load_window(query: Query, season: int, first: int, last: int, scoring: Mapping[str, float] | None = None) -> Window:
    """Weeks ``first``..``last`` of the NFL-wide board in six queries. With ``scoring``: only the exact reference
    scoring's ranges are read when there is one and it holds every week (``choose_reference`` takes it then), else all."""
    args = (int(season), int(first), int(last))
    scorings = {}
    for r in query(REFERENCES_SQL, ()).itertuples():
        sc = r.scoring_settings if isinstance(r.scoring_settings, dict) else json.loads(r.scoring_settings or "{}")
        scorings[r.name] = {k: float(v) for k, v in sc.items() if v is not None}
    lines = _floats(query(LINES_WINDOW_SQL, (*args, list(SKILL))), list(STAT_LINE))
    weeks = sorted({int(w) for w in lines["week"]}) if not lines.empty else []
    exact = exact_reference(scoring, scorings) if scoring is not None else None
    names = [exact] if exact is not None else sorted(scorings)
    rg = _floats(query(RANGES_WINDOW_SQL, (*args, names, list(SKILL))), ["proj_points", *QUANTILES])
    if exact is not None and set(weeks) - {int(w) for w in rg["week"]}:
        rg = _floats(query(RANGES_WINDOW_SQL, (*args, sorted(scorings), list(SKILL))), ["proj_points", *QUANTILES])
    try:
        kdr = _floats(query(KD_RANGES_WINDOW_SQL, args), ["proj_points", "p10", "p90"])
    except Exception:  # noqa: BLE001 - no K / DEF ranges yet (as _load_nfl_wide)
        kdr = pd.DataFrame(columns=["scoring_name", "week", "position", "unit_id", "proj_points", "p10", "p90"])
    try:
        kd = query(KD_LINES_WINDOW_SQL, args)
        kd = kd.rename(columns={NFL_WIDE["kd_unit"]: "unit_id"}) if NFL_WIDE["kd_unit"] != "unit_id" else kd
    except Exception:  # noqa: BLE001 - no K / DEF lines yet: K / DEF unvalued
        kd = pd.DataFrame(columns=["week", "position", "unit_id", "team", "report_status", "roster_status"])
    try:
        status = query(STATUS_WINDOW_SQL, args)
    except Exception:  # noqa: BLE001 - no per-week mart (as _status)
        status = pd.DataFrame(columns=["week", "gsis_id", "team", "report_status", "roster_status", "player_name",
                                       "implied_team_total"])
    return Window(lines, rg, kd, kdr, status, scorings, weeks)


def _closest_by_week(new: pd.DataFrame, refs: pd.DataFrame, key: str, exclude: str | None = None) -> dict[int, str]:
    """week -> the reference whose prices are closest to ``new`` that week (``choose_reference``'s distance: the median
    |log ratio| over the rows both price above one point; the first by name on a tie; never ``exclude``).
    ``new``: week, ``key``, new; ``refs``: scoring_name, week, ``key``, proj_points."""
    both = new.merge(refs[["scoring_name", "week", key, "proj_points"]], on=["week", key])
    both = both[(both["new"] > 1) & (both["proj_points"].astype(float) > 1) & (both["scoring_name"] != exclude)]
    if both.empty:
        return {}
    both = both.assign(d=np.abs(np.log(both["new"] / both["proj_points"].astype(float))))
    d = both.groupby(["week", "scoring_name"])["d"].median().reset_index()
    d = d.sort_values(["week", "d", "scoring_name"], kind="mergesort")
    return {int(w): n for w, n in d.drop_duplicates("week")[["week", "scoring_name"]].itertuples(index=False)}


def skill_window(win: Window, weeks: list[int], scoring: Mapping[str, float],
                 exclude_reference: str | None = None) -> tuple[pd.DataFrame, set]:
    """Every QB-TE stat line of ``weeks`` priced in one pass (``price_lines``), each week with its reference's ranges
    (``price_week``'s rules: the exact reference scoring when the week has it, its quantiles as they are; else the
    closest reference that week and ``approximate_ranges``, row by row over the whole window) and the week's status.
    Returns the frame (week, gsis_id, position, proj_points, p10, p90, team, roster_status, player_name,
    implied_team_total) and the references used."""
    ln = win.lines[win.lines["week"].isin(weeks)].reset_index(drop=True)
    sk = pd.DataFrame({"week": ln["week"].astype(int).to_numpy(), "gsis_id": ln["gsis_id"].to_numpy(),
                       "position": ln["position"].to_numpy(),
                       "proj": price_lines(ln, scoring).to_numpy() if not ln.empty else np.array([], dtype=float)})
    # ---- IA-3 (Wave I-A): the stat line rides along (the rest-of-season pieces: "why this number")
    for c in STAT_LINE:
        sk[c] = pd.to_numeric(ln[c], errors="coerce").to_numpy(dtype=float) if c in ln else np.nan
    # ---- end IA-3
    rg = win.ranges
    present = rg.groupby("week")["scoring_name"].unique().to_dict() if not rg.empty else {}
    choice: dict[int, str] = {}
    exact_w: set[int] = set()
    for w in weeks:
        names = set(present.get(w, ()))
        ex = exact_reference(scoring, {n: sc for n, sc in win.scorings.items() if n in names}, exclude_reference)
        if ex is not None:
            choice[w] = ex
            exact_w.add(w)
    rest = [w for w in weeks if w not in exact_w]
    if rest and not rg.empty:
        new = sk[sk["week"].isin(rest)].rename(columns={"proj": "new"})[["week", "gsis_id", "new"]]
        choice.update(_closest_by_week(new, rg[rg["week"].isin(rest)], "gsis_id", exclude_reference))
    ch = pd.DataFrame({"week": list(choice), "scoring_name": list(choice.values())}, columns=["week", "scoring_name"])
    ref = rg.merge(ch, on=["week", "scoring_name"]) if not rg.empty else rg
    ref = ref.astype({"week": int}).set_index(["week", "gsis_id"])[["proj_points", *QUANTILES]] if not ref.empty else None
    sk["p10"] = sk["p90"] = np.nan
    if ref is not None and not sk.empty:
        idx = pd.MultiIndex.from_arrays([sk["week"], sk["gsis_id"]])
        proj = pd.Series(sk["proj"].to_numpy(), index=idx)
        ex = sk["week"].isin(exact_w).to_numpy()
        exact_rows = ref.reindex(idx)[["p10", "p90"]].astype(float).round(2)
        approx = approximate_ranges(proj[~ex], ref) if (~ex).any() else None
        for q in ("p10", "p90"):
            vals = exact_rows[q].to_numpy(dtype=float).copy()
            if approx is not None:
                vals[~ex] = approx[q].to_numpy(dtype=float)
            sk[q] = vals
    st = win.status.astype({"week": int}) if not win.status.empty else win.status
    sk = sk.merge(st[["week", "gsis_id", "team", "roster_status", "player_name", "implied_team_total"]],
                  on=["week", "gsis_id"], how="left") if not st.empty else sk.assign(team=None, roster_status=None,
                                                                                     player_name=None, implied_team_total=None)
    sk["proj_points"] = sk["proj"].round(2)
    return sk.drop(columns="proj"), {choice[w] for w in weeks if w in choice}


def kd_window(win: Window, weeks: list[int], scoring: Mapping[str, float], position: str) -> pd.DataFrame:
    """``kd_values`` on the NFL-wide board for every week at once: the K (DEF) lines of all weeks priced in one
    ``kdef.price`` call, each week's range = the fixed offsets of the reference with the closest K (DEF) prices that
    week. Columns: week + ``kd_values``' columns."""
    from . import kdef
    cols = ["week", "unit_id", "proj_points", "p10", "p90", "team", "report_status", "roster_status", "player_name",
            "implied_team_total"]
    if win.kd.empty or "position" not in win.kd:
        return pd.DataFrame(columns=cols)
    rows = win.kd[(win.kd["position"] == position) & win.kd["week"].isin(weeks)].reset_index(drop=True)
    if rows.empty:
        return pd.DataFrame(columns=cols)
    line_cols = [f"proj_{c}" for c in (kdef.K_LINE if position == "K" else kdef.DEF_LINE)]
    num = pd.DataFrame({c: (pd.to_numeric(rows[c], errors="coerce") if c in rows else pd.Series(0.0, index=rows.index))
                        for c in line_cols})
    proj = kdef.price(num, position, scoring, "proj_")
    out = rows.drop(columns=[c for c in rows.columns if c.startswith("proj_")]).assign(proj_points=proj)
    out["week"] = out["week"].astype(int)
    kdr = win.kd_ranges.astype({"week": int}) if not win.kd_ranges.empty else win.kd_ranges
    choice = _closest_by_week(out[["week", "unit_id"]].assign(new=proj), kdr, "unit_id") if not kdr.empty else {}
    ch = pd.DataFrame({"week": list(choice), "scoring_name": list(choice.values())}, columns=["week", "scoring_name"])
    f = (kdr.merge(ch, on=["week", "scoring_name"]).drop_duplicates(["week", "unit_id"]).set_index(["week", "unit_id"])
         if not kdr.empty else None)
    if f is not None and not f.empty:
        f = f.reindex(pd.MultiIndex.from_arrays([out["week"], out["unit_id"]]))
        lo = (f["p10"].astype(float) - f["proj_points"].astype(float)).to_numpy()
        hi = (f["p90"].astype(float) - f["proj_points"].astype(float)).to_numpy()
        has = np.array([w in choice for w in out["week"]])
        out["p10"] = np.where(has, np.round(np.clip(proj + lo, 0, None), 2), np.nan)
        out["p90"] = np.where(has, np.round(np.maximum(proj + hi, proj), 2), np.nan)
    else:
        out["p10"] = out["p90"] = np.nan
    for c in cols:
        if c not in out:
            out[c] = None
    return out[cols]


_ros_cache = memo.region("ros", ttl=PRICED_TTL_S)        # INF-2: in the memory budget (was cleared past 100 entries)
ROS_LINE = [f"ros_{s}" for s in STAT_LINE.values()]   # ---- IA-3: the window's stat line (ros_targets … ros_fumbles_lost_total)


def _week_lists(d: pd.DataFrame) -> pd.Series:
    """player_key -> [[week, points], …] in week order (``d`` sorted by player_key, week), without a per-group apply."""
    keys = d["player_key"].to_numpy()
    weeks, pts = d["week"].to_numpy(), d["proj_points"].to_numpy(dtype=float)
    out: dict = {}
    start = 0
    for i in range(1, len(keys) + 1):
        if i == len(keys) or keys[i] != keys[start]:
            out[keys[start]] = [[int(weeks[j]), round(float(pts[j]), 2)] for j in range(start, i)]
            start = i
    return pd.Series(out, dtype=object)


def ros_table(query: Query, league_id: str, league: Mapping, from_week: int, last_week: int,
              playoff_week_start: int | None, *, exclude_reference: str | None = None) -> pd.DataFrame:
    """Rest of season for every projected player in this league's scoring — mart_player_ros_projection's columns
    and rules, priced on request: each week of the window priced, byes (no regular-season game for his team that week)
    excluded, the sum, the playoff subtotal, the 80% range with the weeks read as independent normals, and the ranks by
    position / overall among every projected player on an active NFL roster (a team defense always ranked) — the same
    population the mart ranks, when the league is a house league.

    Wave H (H1): on the NFL-wide board the whole window is read in one round of queries (``load_window``), every
    week's stat lines priced in one vectorised pass, the ranges and K / DEF the same way (``skill_window`` /
    ``kd_window``: ``price_week``'s rules per week); a week the NFL-wide tables do not hold (or the borrowed board) is
    priced week by week as before (``price_week``). The answer is kept 10 minutes (the priced weeks' rule)."""
    scoring, slots = league_scoring(league)
    season = int(league["season"])
    src = board_source()
    key = (str(league_id), _scoring_key(scoring), tuple(slots), season, int(from_week), int(last_week), playoff_week_start,
           exclude_reference, src)
    hit = _ros_cache.get(key)
    if hit is None:
        with provider_trouble.watch() as w:          # ---- IP-5: a unit's name read refused -> not kept (busy)
            hit = _ros_table(query, league_id, scoring, slots, season, from_week, last_week, playoff_week_start,
                             exclude_reference, src)
        if not w.clean:
            raise SleeperBusy("busy, try again in a minute")
        hit = _ros_cache.put(key, hit)
    res = hit.copy()
    res.attrs = dict(hit.attrs)
    return res


def _priced_frames(pr: Priced, w: int) -> list[pd.DataFrame]:
    """One week priced by ``price_week`` as the rest-of-season rows (skill players, then K / DEF)."""
    st = pr.board.status
    sk = pd.DataFrame({"player_key": pr.proj.index, "gsis_id": pr.proj.index,
                       "position": pr.board.line["position"].reindex(pr.proj.index).to_numpy(),
                       "proj_points": pr.proj.round(2).to_numpy(),
                       "p10": pr.ranges["p10"].reindex(pr.proj.index).to_numpy(dtype=float),
                       "p90": pr.ranges["p90"].reindex(pr.proj.index).to_numpy(dtype=float)})
    for c in ("team", "roster_status", "player_name", "implied_team_total"):
        sk[c] = st[c].reindex(pr.proj.index).to_numpy() if c in st else None
    # ---- IA-3 (Wave I-A): the stat line rides along (the rest-of-season pieces)
    for c in STAT_LINE:
        sk[c] = (pd.to_numeric(pr.board.line[c], errors="coerce").reindex(pr.proj.index).to_numpy(dtype=float)
                 if c in pr.board.line else np.nan)
    # ---- end IA-3
    frames = [sk.assign(week=w)]
    for pos, kd in pr.kd.items():
        if not kd.empty:
            frames.append(_kd_frame(kd.assign(week=w), pos))
    return frames


def _kd_frame(kd: pd.DataFrame, pos: str) -> pd.DataFrame:
    return pd.DataFrame({"player_key": kd["unit_id"].to_numpy(), "gsis_id": kd["unit_id"].to_numpy() if pos == "K" else None,
                         "position": pos, "proj_points": pd.to_numeric(kd["proj_points"]).round(2).to_numpy(),
                         "p10": pd.to_numeric(kd["p10"]).to_numpy(dtype=float),
                         "p90": pd.to_numeric(kd["p90"]).to_numpy(dtype=float),
                         "team": kd["team"].to_numpy(), "roster_status": kd["roster_status"].to_numpy(),
                         "player_name": kd["player_name"].to_numpy(),
                         "implied_team_total": kd["implied_team_total"].to_numpy(), "week": kd["week"].to_numpy()})


def _ros_table(query: Query, league_id: str, scoring: dict[str, float], slots: list[str], season: int, from_week: int,
               last_week: int, playoff_week_start: int | None, exclude_reference: str | None, src: str) -> pd.DataFrame:
    g = query(ROS_GAMES_SQL, (season,))
    plays = {(int(r.week), t) for r in g.itertuples() for t in (r.home_team, r.away_team)}
    starts = tuple(p for p in ("K", "DEF") if p in {str(x).upper() for x in slots})
    units = unit_starts(slots)                                                   # ---- IC-4: TMQB / TMPK rows
    window = list(range(int(from_week), int(last_week) + 1))
    frames, refs = [], set()
    fast: list[int] = []
    if window and src != "borrow":
        win = load_window(query, season, window[0], window[-1], scoring)
        # auto: the weeks the NFL-wide tables hold (load_board's rule per week); forced nfl_wide: every week
        fast = list(window) if src == "nfl_wide" else [w for w in window if w in set(win.weeks)]
        if fast:
            sk, used = skill_window(win, fast, scoring, exclude_reference)
            refs |= used
            frames.append(sk.assign(player_key=sk["gsis_id"]))
            for pos in starts:
                kd = kd_window(win, fast, scoring, pos)
                if not kd.empty:
                    frames.append(_kd_frame(kd, pos))
            if units:                                                            # ---- IC-4
                kfr = kd_window(win, fast, scoring, "K") if "TMPK" in units else None
                uf = unit_window(win, fast, scoring, sk, kfr, units)
                if not uf.empty:
                    frames.append(uf.assign(unit=True))                          # ---- end IC-4
    for w in window:
        if w in fast:
            continue
        pr = price_week(query, league_id, scoring, slots, season, w, exclude_reference=exclude_reference)
        refs.add(pr.reference)
        fr = _priced_frames(pr, w)
        if "K" not in starts:                                                    # ---- IC-4: priced for TMPK only
            fr = [f for f in fr if not (len(f) and (f["position"] == "K").all())]
        uf = units_priced_frame(pr, w) if units else pd.DataFrame()
        frames.extend(fr + ([uf.assign(unit=True)] if not uf.empty else []))     # ---- end IC-4
    cols = ["player_key", "gsis_id", "position", "player_name", "team", "roster_status", "is_ranked", "from_week",
            "last_week", "playoff_week_start", "ros_games", "ros_points", "ros_points_per_game", "ros_p10", "ros_p90",
            "ros_sd", "playoff_games", "playoff_points", "ros_rank_pos", "ros_rank_all", "bye_weeks", "weeks_with_lines",
            "weeks_json", *ROS_LINE]                                                                  # ---- IA-3
    if units:
        cols += UNIT_ROS_EXTRA                                                   # ---- IC-4
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
        "weeks_json": _week_lists(d),
    })
    out["playoff_points"] = out["playoff_points"].fillna(0.0).round(2)
    # ---- IA-3 (Wave I-A): the window's stat line, summed over the weeks counted (byes out): ros_<stat>; NULL for a
    # kicker / defense (no stat line), never 0
    comps = [c for c in STAT_LINE if c in d]
    sums = grp[comps].sum(min_count=1) if comps else pd.DataFrame(index=out.index)
    for comp, stat in STAT_LINE.items():
        out[f"ros_{stat}"] = sums[comp].round(3) if comp in sums else np.nan
    # ---- end IA-3
    for c in ("gsis_id", "position", "player_name", "team", "roster_status"):
        out[c] = first[c]
    if units:                                       # ---- IC-4: the decision week's starter / kicker of a unit
        for c in UNIT_ROS_EXTRA:
            out[c] = first[c] if c in first else None
        out["unit"] = out["unit"].fillna(False).astype(bool)
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
    out = unit_keys(league_id, out) if units else out                            # ---- IC-4
    out.attrs["references"] = sorted(r for r in refs if r)
    return out[cols]


# ------------------------------------------------------------------------------ Wave G (G2): every roster, several weeks
# The decisions on demand (api/league_lab_api/decisions.py): waivers, trades and the Team Hub need every roster of a
# league solved for the horizon (this week and the next three), exactly as the nightly solves the house leagues into
# ops.lineups: ONE LineupInputs for the whole league (every roster, every horizon week, the whole week's board priced
# so a free agent is valued by the same `lineup._proposed_player`), solved by `lineup.build`. The cost is the nightly's
# per league: rosters x weeks solves with margins (12 x 4 = 48 for the dynasty), plus the board priced per week (cached).
LAST_WEEK_SQL = "select max(week) as w from analytics.dim_game where season = %s and season_type = 'REG'"
GAMES_IN_SQL = """select week, home_team, away_team, kickoff_at from analytics.dim_game
                  where season = %s and week = any(%s) and season_type = 'REG'"""
# the NFL-wide status of players (the house leagues' mart rows carry the same NFL columns for every player): NFL
# roster status, the injury report, games played this season - the free-agent filter of the nightly (waivers.py)
NFL_STATUS_SQL = """select distinct on (sleeper_id) sleeper_id, gsis_id, player_name, position, nfl_team, roster_status,
                           injury_status, games_played
                    from analytics.mart_player_availability where sleeper_id = any(%s)
                    order by sleeper_id, league_id"""
HORIZON = 4
LEAGUE_WEEKS_TTL_S = 300                       # rosters change with waivers and trades (Sleeper's rosters: 10 minutes)
_league_weeks = memo.region("league_weeks", ttl=LEAGUE_WEEKS_TTL_S)   # INF-2: in the budget (was cleared past 64)


@dataclass
class LeagueWeeks:
    """One league solved on request: every roster's lineup rows (``rows``: ops.lineups' columns) and totals for the
    horizon ``weeks``, the inputs that solved them (``inp``: ``lineup._proposed_player`` values any player of the board
    the same way, a free agent included), the priced weeks (``priced``: the horizon, plus the rest of the season when
    asked) and the Sleeper payloads."""
    league: dict
    league_id: str
    season: int
    weeks: list[int]
    rest_weeks: list[int]
    slots: list[str]
    scoring: dict[str, float]
    rosters: list[dict]
    users: list[dict]
    names: dict[int, dict]
    players: dict[str, dict]
    priced: dict[int, Priced]
    inp: LU.LineupInputs
    gsis_of: dict[str, str]
    dp: pd.DataFrame
    rows: list[dict]
    totals: list[dict]
    as_of: datetime
    timings_ms: dict[str, float] = field(default_factory=dict)
    sleeper_calls: int = 0
    cache: dict = field(default_factory=dict)            # derived frames (horizon_frame), built once per solve
    # INF-2: the Sleeper payloads are the client's own cached objects (the player directory: one per process), not
    # counted again in the memory budget's ``league_weeks`` region; a decision memo or a TradeContext holding this
    # LeagueWeeks does not count it again either (it is counted here, in ``league_weeks``)
    _memo_skip: ClassVar[tuple[str, ...]] = ("league", "rosters", "users", "players")
    _memo_shared: ClassVar[bool] = True

    @property
    def roster_ids(self) -> list[int]:
        return sorted(int(r["roster_id"]) for r in self.rosters)

    def roster_rows(self, roster_id: int, week: int) -> list[dict]:
        return [r for r in self.rows if int(r["roster_id"]) == int(roster_id) and int(r["week"]) == int(week)]

    def total(self, roster_id: int, week: int) -> dict:
        return next((t for t in self.totals if int(t["roster_id"]) == int(roster_id) and int(t["week"]) == int(week)), {})

    def player_row(self, sid: str, *, gsis: str | None = None, position: str | None = None) -> dict:
        """The row ``lineup._proposed_player`` reads for a player who is on no roster (a free agent)."""
        sp = self.players.get(str(sid)) or {}
        return {"sleeper_player_id": str(sid), "gsis_id": gsis if gsis is not None else self.gsis_of.get(str(sid)),
                "position": position or sp.get("position"), "nfl_team": sp.get("team"), "is_starter": False, "slot": None}

    def value(self, sid: str, week: int, row: dict | None = None) -> LU.Player:
        """The player as B1 carries him on a roster that week (a free agent: no IR / taxi, not a starter)."""
        return LU._proposed_player(self.inp, self.league_id, int(week), row or self.player_row(sid), None, {},
                                   int(week) > int(self.weeks[0]) - 1, self.as_of)


def _sleeper_name(sp: Mapping, sid: str) -> str:
    return sp.get("full_name") or " ".join(x for x in (sp.get("first_name"), sp.get("last_name")) if x) or str(sid)


def league_inputs(query: Query, league_id: str, season: int, rosters: list[dict], players: Mapping[str, dict],
                  priced: Mapping[int, Priced], slots: list[str], weeks: list[int], *,
                  extra_sids: Iterable[str] = ()) -> tuple[LU.LineupInputs, dict[str, str], pd.DataFrame]:
    """(LineupInputs for every roster of the league over ``weeks``, sid -> gsis, dim_player rows): ``_solve_roster``'s
    assembly for the whole league; every priced week's board goes into ``proj`` / ``kd_proj`` (so ``extra_sids``, the
    free agents, are valued by the same rule), the schedule of every priced week into ``games`` (byes)."""
    rostered = [str(p) for r in rosters for p in (r.get("players") or [])]
    pids = sorted(set(rostered) | {str(x) for x in extra_sids})
    idm = query(IDMAP_SQL, (pids,)) if pids else pd.DataFrame(columns=["sleeper_id", "gsis_id"])
    gsis_of = {str(k): v for k, v in zip(idm["sleeper_id"], idm["gsis_id"], strict=False) if v} if not idm.empty else {}
    gs = sorted({gsis_of[s] for s in rostered if s in gsis_of})
    dp = query(DIM_PLAYER_SQL, (gs,)).set_index("gsis_id") if gs else pd.DataFrame(columns=["player_name", "latest_team"])
    current: dict[int, list[dict]] = {}
    sleeper_meta: dict[str, dict] = {}
    for sid in pids:
        sp = players.get(sid) or {}
        sleeper_meta[sid] = {"sleeper_player_id": sid, "position": sp.get("position"),
                             "fantasy_positions": sp.get("fantasy_positions"), "team": sp.get("team")}
    for roster in rosters:
        rid = int(roster["roster_id"])
        reserve, taxi = {str(x) for x in roster.get("reserve") or []}, {str(x) for x in roster.get("taxi") or []}
        current[rid] = [{"sleeper_player_id": sid, "gsis_id": gsis_of.get(sid),
                         "player_name": _sleeper_name(players.get(sid) or {}, sid),
                         "position": (players.get(sid) or {}).get("position"), "nfl_team": (players.get(sid) or {}).get("team"),
                         "is_on_ir": sid in reserve, "is_on_taxi": sid in taxi}
                        for sid in [str(p) for p in (roster.get("players") or [])]]
    proj_map: dict[tuple, dict] = {}
    kd_proj: dict[tuple, dict] = {}
    k_team: dict[tuple, dict] = {}
    for w, pr in priced.items():
        st = pr.board.status
        cols = [c for c in ("team", "report_status", "roster_status") if c in st]
        sd = st[cols].to_dict("index") if not st.empty else {}
        for g, v in pr.proj.items():
            s = sd.get(g) or {}
            proj_map[(league_id, int(w), g)] = {"proj_points": round(float(v), 2), "team": s.get("team"),
                                                "report_status": s.get("report_status"), "roster_status": s.get("roster_status")}
        for pos, rows_ in pr.kd.items():
            by_team: dict[str, list[dict]] = {}
            for r in rows_.itertuples():
                v = {"proj_points": None if pd.isna(r.proj_points) else float(r.proj_points), "team": r.team,
                     "report_status": r.report_status, "roster_status": r.roster_status}
                kd_proj[(league_id, int(w), r.unit_id)] = v
                if pos == "K" and isinstance(r.team, str) and r.team:
                    by_team.setdefault(r.team, []).append(v)
            k_team.update({(league_id, int(w), tm): v[0] for tm, v in by_team.items() if len(v) == 1})
    g = query(GAMES_IN_SQL, (int(season), sorted(int(w) for w in priced)))
    games: dict[int, dict[str, datetime | None]] = {int(w): {} for w in priced}
    for r in g.itertuples():
        games[int(r.week)][r.home_team] = r.kickoff_at
        games[int(r.week)][r.away_team] = r.kickoff_at
    mv = sorted({m for pr in priced.values() for m in pr.board.line["model_version"].dropna()})
    inp = LU.LineupInputs(
        season=int(season),
        leagues=[{"league_id": league_id, "roster_positions": slots, "last_scored_leg": min(weeks) - 1,
                  "roster_ids": sorted(current)}],
        weeks={league_id: [int(w) for w in weeks]}, proj=proj_map, weekly={}, current={league_id: current},
        sleeper=sleeper_meta, k_ppg={}, games=games, model_version=",".join(mv),
        starters={(league_id, int(r["roster_id"])): [str(s) for s in (r.get("starters") or [])] for r in rosters},
        kd_proj=kd_proj, k_team_proj=k_team, unit_proj=unit_map(league_id, priced))           # IC-2: team units
    return inp, gsis_of, dp


def horizon_weeks(query: Query, season: int, week: int, n: int = HORIZON) -> list[int]:
    """This week and the next ``n - 1`` regular-season weeks (fewer at the end of the season)."""
    last = query(LAST_WEEK_SQL, (int(season),))
    last_w = int(last["w"].iloc[0]) if not last.empty and pd.notna(last["w"].iloc[0]) else int(week)
    return [w for w in range(int(week), int(week) + n) if w <= last_w]


def league_weeks(query: Query, league_id: str, week: int, *, client: Sleeper | None = None, as_of: datetime | None = None,
                 exclude_reference: str | None = None, rest: bool = False, extra_sids: Iterable[str] = (),
                 cache: bool = True) -> LeagueWeeks:
    """Every roster of a Sleeper league solved for the horizon from ``week`` (``lineup.build`` on one LineupInputs);
    ``rest`` also prices every later regular-season week (rest-of-season sums), ``extra_sids`` (free agents) are mapped
    and valued too. Cached ``LEAGUE_WEEKS_TTL_S`` per (league, rosters, week, as_of given or not, board)."""
    t0 = time.perf_counter()
    sl = client or sleeper()
    calls0 = sl.calls
    league_id = check_id(league_id)
    league = sl.league(league_id)
    rosters, users, players = sl.rosters(league_id), sl.users(league_id), sl.players()
    t1 = time.perf_counter()
    season = int(league["season"])
    extra = tuple(sorted({str(x) for x in extra_sids}))
    key = (league_id, int(week), json.dumps(rosters, sort_keys=True, default=str), _scoring_key(league.get("scoring_settings") or {}),
           None if as_of is None else as_of.isoformat(), exclude_reference, bool(rest), extra, board_source())
    hit = _league_weeks.get(key) if cache else None
    if hit is not None:
        return hit
    scoring, slots = league_scoring(league)
    weeks = horizon_weeks(query, season, int(week))
    if not weeks:
        raise LeagueNotFound(f"no regular-season week {week} in {season}")
    last = query(LAST_WEEK_SQL, (season,))
    rest_weeks = list(range(int(week), int(last["w"].iloc[0]) + 1)) if rest else list(weeks)
    priced = {w: price_week(query, league_id, scoring, slots, season, w, exclude_reference=exclude_reference)
              for w in sorted(set(weeks) | set(rest_weeks))}
    t2 = time.perf_counter()
    when = as_of or clock.now()  # ---- INF-1
    with provider_trouble.watch() as trouble:        # ---- IP-5: a build that swallowed a refused read is not kept
        inp, gsis_of, dp = league_inputs(query, league_id, season, rosters, players, priced, slots, weeks, extra_sids=extra)
        rows, totals, _ = LU.build(inp, as_of=when)
    t3 = time.perf_counter()
    out = LeagueWeeks(league=league, league_id=league_id, season=season, weeks=weeks, rest_weeks=rest_weeks, slots=slots,
                      scoring=scoring, rosters=rosters, users=users, names=team_names(rosters, users), players=players,
                      priced=priced, inp=inp, gsis_of=gsis_of, dp=dp, rows=rows, totals=totals, as_of=when,
                      timings_ms={"sleeper": round((t1 - t0) * 1000, 1), "price": round((t2 - t1) * 1000, 1),
                                  "solve": round((t3 - t2) * 1000, 1), "total": round((t3 - t0) * 1000, 1)},
                      sleeper_calls=sl.calls - calls0)
    if cache and trouble.clean:                      # ---- IP-5
        _league_weeks.put(key, out)
    return out


def clear_league_weeks() -> None:
    _league_weeks.clear()


def horizon_frame(lw: LeagueWeeks) -> pd.DataFrame:
    """The solved rows in ``mart_league_roster_horizon``'s columns and rules (names from dim_player, else Sleeper's
    directory; eligibility from Sleeper; ``is_top_at_slot_type``: the best-valued starter of each slot type;
    ``replacement_*``: the bench player worth value - margin, matched to the cent, the better bench rank first) -
    what ``roster_value.RosterBoard`` and the Team Hub read."""
    cols = ["roster_id", "team_name", "manager_name", "week", "this_week", "horizon_first_week", "horizon_last_week",
            "horizon_weeks", "is_this_week", "role", "slot", "slot_type", "slot_order", "bench_rank", "sleeper_player_id",
            "gsis_id", "player_name", "position", "fantasy_positions", "player_value", "value_source", "lineup_margin",
            "is_locked", "report_status", "reason", "is_top_at_slot_type", "replacement_sleeper_player_id",
            "replacement_name", "replacement_value"]
    if not lw.rows:
        return pd.DataFrame(columns=cols)
    if "horizon_frame" in lw.cache:
        return lw.cache["horizon_frame"].copy()
    df = pd.DataFrame(lw.rows)
    w0, w1 = min(lw.weeks), max(lw.weeks)

    def name(r) -> str | None:
        g = r["gsis_id"]
        if isinstance(g, str) and g in lw.dp.index and isinstance(lw.dp.loc[g, "player_name"], str):
            return lw.dp.loc[g, "player_name"]
        sid = r["sleeper_player_id"]
        if not isinstance(sid, str):
            return None
        return _sleeper_name(lw.players.get(sid) or {}, sid)

    df["player_name"] = df.apply(name, axis=1)
    df["fantasy_positions"] = [((lw.players.get(s) or {}).get("fantasy_positions") or ([p] if isinstance(p, str) else None))
                               if isinstance(s, str) else None for s, p in zip(df["sleeper_player_id"], df["position"], strict=True)]
    df["team_name"] = df["roster_id"].map(lambda r: lw.names.get(int(r), {}).get("team_name"))
    df["manager_name"] = df["roster_id"].map(lambda r: lw.names.get(int(r), {}).get("manager_name"))
    df["this_week"], df["horizon_first_week"], df["horizon_last_week"], df["horizon_weeks"] = w0, w0, w1, len(lw.weeks)
    df["is_this_week"] = df["week"] == w0
    df = df.rename(columns={"value": "player_value", "margin": "lineup_margin"})
    for c in ("player_value", "lineup_margin"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["is_locked"] = df["is_locked"].fillna(False).astype(bool)
    st = df[df["role"] == "starter"].copy()
    st["_v"] = st["player_value"].fillna(-1e18)
    st = st.sort_values(["roster_id", "week", "slot_type", "_v", "slot_order"], ascending=[True, True, True, False, True])
    top = st.groupby(["roster_id", "week", "slot_type"]).head(1).index
    df["is_top_at_slot_type"] = df.index.isin(top)
    # the replacement: the bench player worth value - margin (to the cent), the better bench rank first
    df["replacement_sleeper_player_id"] = None
    df["replacement_name"] = None
    df["replacement_value"] = np.nan
    bench = df[(df["role"] == "bench") & (df["player_value"].round(2) * 100).round().gt(0)].copy()
    bench["_c"] = (bench["player_value"] * 100).round().astype("int64")
    bench = bench.sort_values(["roster_id", "week", "_c", "bench_rank"])
    first = bench.drop_duplicates(["roster_id", "week", "_c"]).set_index(["roster_id", "week", "_c"])
    for i, r in df[(df["role"] == "starter") & df["lineup_margin"].notna()].iterrows():
        c = round((float(r["player_value"]) - float(r["lineup_margin"])) * 100)
        if c <= 0:
            continue
        k = (r["roster_id"], r["week"], int(c))
        if k in first.index:
            b = first.loc[k]
            df.at[i, "replacement_sleeper_player_id"] = b["sleeper_player_id"]
            df.at[i, "replacement_name"] = b["player_name"]
            df.at[i, "replacement_value"] = float(b["player_value"])
    lw.cache["horizon_frame"] = df[cols]
    return df[cols].copy()


def free_agents(query: Query, league_id: str, rosters: list[dict], players: Mapping[str, dict], slots: list[str]) -> pd.DataFrame:
    """The league's free agents: Sleeper's player directory minus every roster, mapped by ``player_id_map`` (never by
    name; a team defense keeps its Sleeper id), with the nightly's waiver filter (``waivers.load_and_sweep``): on an
    active NFL roster, not Out / IR, a position the league starts. NFL status from the house marts' NFL-wide columns
    (``NFL_STATUS_SQL``), else Sleeper's directory (``status`` Active, its ``injury_status``)."""
    cols = ["sleeper_id", "gsis_id", "player_name", "position", "nfl_team", "roster_status", "injury_status", "games_played"]
    taken = {str(p) for r in rosters for p in (r.get("players") or [])}
    starts = {s.type for s in LU.parse_slots(slots)[0]}
    # ---- IC-2: team units (MFL's TMQB / TMPK) are free agents too, one per (unit, team): a team whose unit a roster
    # here carries is taken; of two rows for one free unit (its MFL id, the placeholder) the MFL id is kept
    unit_taken = {((players.get(x) or {}).get("position"), (players.get(x) or {}).get("team")) for x in taken
                  if (players.get(x) or {}).get("position") in LU.UNITS}
    unit_seen: dict[tuple, str] = {}
    # ---- end IC-2
    cands = []
    for sid, sp in players.items():
        sid = str(sid)
        if sid in taken or not isinstance(sp, dict):
            continue
        pos = frozenset(sp.get("fantasy_positions") or ([sp["position"]] if sp.get("position") else []))
        if not any(pos & LU.SLOT_ELIGIBILITY[t] for t in starts):
            continue
        if pos & LU.UNITS:                                                      # IC-2
            u = (sp.get("position"), sp.get("team"))
            if u in unit_taken or (u in unit_seen and sp.get("mfl_id") is None):
                continue
            if u in unit_seen:
                cands.remove(unit_seen[u])
            unit_seen[u] = sid
        cands.append(sid)
    if not cands:
        return pd.DataFrame(columns=cols)
    idm = query(IDMAP_SQL, (cands,))
    gsis_of = dict(zip(idm["sleeper_id"].astype(str), idm["gsis_id"], strict=False)) if not idm.empty else {}
    nfl = query(NFL_STATUS_SQL, (cands,))
    nfl = nfl.set_index("sleeper_id") if not nfl.empty else pd.DataFrame(columns=cols[1:])
    out = []
    for sid in cands:
        sp = players.get(sid) or {}
        position = sp.get("position")
        if sid in nfl.index:
            n = nfl.loc[sid]
            rs, inj, gp = n["roster_status"], n["injury_status"], n["games_played"]
            team = n["nfl_team"] if isinstance(n["nfl_team"], str) else sp.get("team")
            position = n["position"] if isinstance(n["position"], str) else position
            if isinstance(n["player_name"], str):
                sp = {**sp, "full_name": n["player_name"]}
        else:
            rs = "ACT" if (position == "DEF" or (sp.get("team") and str(sp.get("status") or "").lower() == "active")) else None
            inj, gp, team = sp.get("injury_status"), None, sp.get("team")
        gsis = gsis_of.get(sid)
        if position != "DEF" and position not in LU.UNITS and gsis is None:   # IC-2: a unit has no gsis by design
            continue                                   # unmapped: never joined by name
        if rs != "ACT" or inj in ("Out", "IR"):
            continue
        out.append({"sleeper_id": sid, "gsis_id": gsis, "player_name": _sleeper_name(sp, sid),
                    "position": position, "nfl_team": team, "roster_status": rs,
                    "injury_status": None if inj is None or (isinstance(inj, float) and math.isnan(inj)) else inj,
                    "games_played": None if gp is None or (isinstance(gp, float) and math.isnan(gp)) else int(gp)})
    return pd.DataFrame(out, columns=cols)


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
    import contextvars  # ---- IO-4
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

    ctx = contextvars.copy_context()           # ---- IO-4: the request's client (provider_share) reaches each thread
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(leagues)))) as ex:
        rows = list(ex.map(lambda lg: ctx.copy().run(one, lg), leagues))
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
