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

Nothing here writes; every database read goes through the ``query(sql, params) -> DataFrame`` the caller passes
(the API's cached read-only pool, or a psycopg connection in scripts).
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import lineup as LU
from .scoring import MAPPED_KEYS, compute_points, unmapped_keys

Query = Callable[[str, tuple], pd.DataFrame]

SLEEPER_API = "https://api.sleeper.app/v1"
FIXTURES_ENV = "LEAGUE_LAB_SLEEPER_FIXTURES"
API_ENV = "LEAGUE_LAB_SLEEPER_API"           # override the host (a proxy, a mock)
LEAGUE_TTL_S = 15 * 60                        # league settings, rosters, users
PLAYERS_TTL_S = 24 * 3600                     # the NFL player directory (~15 MB; Sleeper: at most once a day)
SKILL = ("QB", "RB", "WR", "TE")
QUANTILES = ("p10", "p25", "p50", "p75", "p90")
RANGE_METHOD = "ratio"
RATIO_CLIP = (0.25, 4.0)                      # a player whose two prices differ more than 4x keeps a bounded scale
_ID = re.compile(r"^\d{1,24}$")

# keys a K or DEF projection is priced on (kdef.k_coefficients / price_def): a fitted league's K (DEF) values are
# reused only when every such key has the same weight in the requested league
K_KEY = re.compile(r"^(fgm|fgmiss|xpm|xpmiss)(_|$)")
DEF_PREFIXES = ("def_", "st_", "yds_allow", "pts_allow", "blk_", "sack", "int", "ff", "fum_rec", "safe", "qb_hit", "tkl")
# the defense keys kd1.0 projects (kdef.DEF_STAT_MAP + PTS_ALLOW_BUCKETS): not "unmapped" in a league that starts a DEF
DEF_PROJECTED = re.compile(r"^(sack|int|fum_rec|ff|def_td|def_st_td|st_td|safe|blk_kick|def_st_fum_rec|st_fum_rec|"
                           r"def_st_ff|st_ff|pts_allow_.*)$")


class LeagueNotFound(LookupError):
    """Sleeper has no such league (or no such roster in it)."""


class SleeperUnavailable(RuntimeError):
    """Sleeper could not be reached (or a fixture is missing)."""


# ------------------------------------------------------------------------------ Sleeper
class Sleeper:
    """Read-only Sleeper client with a TTL cache; fixture mode when ``LEAGUE_LAB_SLEEPER_FIXTURES`` is set."""

    def __init__(self, fixtures: str | Path | None = None, base: str | None = None, timeout: float = 10.0) -> None:
        fx = fixtures if fixtures is not None else os.environ.get(FIXTURES_ENV)
        self.fixtures = Path(fx) if fx else None
        self.base = (base or os.environ.get(API_ENV) or SLEEPER_API).rstrip("/")
        self.timeout = timeout
        self.calls = 0                        # network (or fixture) reads, for the latency report
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def _get(self, path: str, fixture: str, ttl: float) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(path)
        if hit is not None and hit[0] > now:
            return hit[1]
        self.calls += 1
        if self.fixtures is not None:
            f = self.fixtures / fixture
            if not f.exists():
                if not fixture.startswith("league_"):
                    raise SleeperUnavailable(f"no fixture {f}")
                data = None                    # what Sleeper answers for a league id it does not have
            else:
                data = json.loads(f.read_text())
        else:
            req = urllib.request.Request(f"{self.base}{path}", headers={"User-Agent": "league-lab/any-league"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - fixed https host
                    data = json.loads(r.read().decode("utf-8") or "null")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise SleeperUnavailable(f"Sleeper {path}: {exc}") from exc
        with self._lock:
            self._cache[path] = (now + ttl, data)
        return data

    def league(self, league_id: str) -> dict:
        data = self._get(f"/league/{league_id}", f"league_{league_id}.json", LEAGUE_TTL_S)
        if not isinstance(data, dict) or data.get("sport", "nfl") != "nfl":
            raise LeagueNotFound(f"no Sleeper NFL league {league_id}")
        return data

    def rosters(self, league_id: str) -> list[dict]:
        return list(self._get(f"/league/{league_id}/rosters", f"rosters_{league_id}.json", LEAGUE_TTL_S) or [])

    def users(self, league_id: str) -> list[dict]:
        return list(self._get(f"/league/{league_id}/users", f"users_{league_id}.json", LEAGUE_TTL_S) or [])

    def players(self) -> dict[str, dict]:
        return dict(self._get("/players/nfl", "players_nfl.json", PLAYERS_TTL_S) or {})

    def user_leagues(self, username: str, season: int) -> list[dict]:
        """A username's NFL leagues of a season (two calls: /user/<name>, /user/<id>/leagues/nfl/<season>) — the
        customer app's league picker; not used by My Week."""
        u = self._get(f"/user/{username}", f"user_{username}.json", LEAGUE_TTL_S)
        if not isinstance(u, dict) or not u.get("user_id"):
            raise LeagueNotFound(f"no Sleeper user {username}")
        return list(self._get(f"/user/{u['user_id']}/leagues/nfl/{season}", f"leagues_{u['user_id']}_{season}.json",
                              LEAGUE_TTL_S) or [])


_default: Sleeper | None = None


def sleeper() -> Sleeper:
    """The process-wide client (one cache); rebuilt when the fixture setting changes (tests)."""
    global _default
    fx = os.environ.get(FIXTURES_ENV)
    if _default is None or str(_default.fixtures or "") != str(Path(fx) if fx else ""):
        _default = Sleeper()
    return _default


def check_id(league_id: str) -> str:
    """A Sleeper league id is digits; anything else never reaches a URL or a file name."""
    s = str(league_id).strip()
    if not _ID.match(s):
        raise LeagueNotFound(f"not a Sleeper league id: {league_id!r}")
    return s


# ------------------------------------------------------------------------------ the NFL-wide board
BOARD_SQL = """
select p.league_id, p.gsis_id, p.position, p.model_version, p.proj_points, p.p10, p.p25, p.p50, p.p75, p.p90,
       p.proj_targets, p.proj_receptions, p.proj_receiving_yards, p.proj_receiving_tds, p.proj_carries,
       p.proj_rushing_yards, p.proj_rushing_tds, p.proj_attempts, p.proj_passing_yards, p.proj_passing_tds,
       p.proj_passing_interceptions, p.proj_fumbles_lost_total
from ops.projections p
where p.season = %s and p.week = %s and p.position = any(%s)
order by p.gsis_id, p.league_id
"""
# ops.projections column -> the stat column compute_points prices (scoring.SLEEPER_STAT_MAP's names)
STAT_LINE = {"proj_targets": "targets", "proj_receptions": "receptions", "proj_receiving_yards": "receiving_yards",
             "proj_receiving_tds": "receiving_tds", "proj_carries": "carries", "proj_rushing_yards": "rushing_yards",
             "proj_rushing_tds": "rushing_tds", "proj_attempts": "attempts", "proj_passing_yards": "passing_yards",
             "proj_passing_tds": "passing_tds", "proj_passing_interceptions": "passing_interceptions",
             "proj_fumbles_lost_total": "fumbles_lost_total"}
STATUS_SQL = """
select gsis_id, team, report_status, roster_status from analytics.mart_player_week_projections
where league_id = %s and season = %s and week = %s and gsis_id is not null
"""
KD_SQL = """
select p.league_id, p.position, p.gsis_id as unit_id, round(p.proj_points::numeric, 2) as proj_points,
       u.team, u.report_status, u.roster_status
from ops.projections as p
join analytics.mart_kd_week as u
  on u.position = p.position and u.unit_id = p.gsis_id and u.season = p.season and u.week = p.week
where p.season = %s and p.week = %s and p.position in ('K', 'DEF')
"""
LEAGUES_SQL = "select league_id, scoring_settings from analytics.dim_league_season where is_current_season"


@dataclass
class Board:
    """The week's NFL-wide inputs: one stat line per player (``line``), every fitted league's priced points and
    ranges (``fitted``: league_id -> frame indexed by gsis_id), status, K / DEF rows, fitted scorings."""
    season: int
    week: int
    line: pd.DataFrame
    fitted: dict[str, pd.DataFrame]
    status: pd.DataFrame
    kd: pd.DataFrame
    scorings: dict[str, dict[str, float]]
    mismatched_lines: int = 0


def _floats(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def load_board(query: Query, season: int, week: int) -> Board:
    raw = _floats(query(BOARD_SQL, (int(season), int(week), list(SKILL))), ["proj_points", *QUANTILES, *STAT_LINE])
    comps = list(STAT_LINE)
    first = raw.drop_duplicates("gsis_id", keep="first").set_index("gsis_id")
    line = first[["position", "model_version", *comps]].copy()
    # the premise of the design: the stat line does not depend on the league (a mismatch is counted and reported)
    other = raw.set_index("gsis_id")[comps]
    mism = int((other.sub(line[comps].reindex(other.index)).abs() > 1e-9).any(axis=1).sum())
    fitted = {lid: g.set_index("gsis_id")[["proj_points", *QUANTILES]] for lid, g in raw.groupby("league_id")}
    ref_for_status = next(iter(sorted(fitted)), None)
    status = (query(STATUS_SQL, (ref_for_status, int(season), int(week))).drop_duplicates("gsis_id").set_index("gsis_id")
              if ref_for_status else pd.DataFrame(columns=["team", "report_status", "roster_status"]))
    try:
        kd = _floats(query(KD_SQL, (int(season), int(week))), ["proj_points"])
    except Exception:  # noqa: BLE001 - a database without the K / DEF mart: K / DEF unvalued, reported
        kd = pd.DataFrame(columns=["league_id", "position", "unit_id", "proj_points", "team", "report_status", "roster_status"])
    lg = query(LEAGUES_SQL, ())
    scorings = {r.league_id: {k: float(v) for k, v in (r.scoring_settings or {}).items()} for r in lg.itertuples()}
    return Board(int(season), int(week), line, fitted, status, kd, scorings, mism)


def price_lines(line: pd.DataFrame, scoring: Mapping[str, float]) -> pd.Series:
    """League points of every stat line: ``compute_points`` (bonuses included), exactly as ``projections.price``."""
    stats = line[list(STAT_LINE)].rename(columns=STAT_LINE).fillna(0.0)
    return pd.Series([compute_points(r, scoring) for r in stats.to_dict("records")], index=line.index, dtype=float)


# ------------------------------------------------------------------------------ ranges for a league the model never saw
def choose_reference(proj: pd.Series, fitted: Mapping[str, pd.DataFrame], exclude: str | None = None) -> str | None:
    """The fitted league whose prices of this week's stat lines are closest to ``proj`` (median |log ratio| over
    the players both price above one point); never ``exclude`` (the requested league itself)."""
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
    """A fitted league whose K (DEF) pricing keys equal this league's, so its K (DEF) values are this league's."""
    pick = (lambda k: bool(K_KEY.match(k))) if position == "K" else _is_def_key
    mine = _keys(scoring, pick)
    have = set(board.kd.loc[board.kd["position"] == position, "league_id"]) if not board.kd.empty else set()
    for lid in sorted(have):
        if _keys(board.scorings.get(lid, {}), pick) == mine:
            return lid
    return None


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


GAMES_SQL = """select week, home_team, away_team, kickoff_at from analytics.dim_game
               where season = %s and week = %s and season_type = 'REG'"""
DIM_PLAYER_SQL = "select gsis_id, player_name, latest_team from analytics.dim_player where gsis_id = any(%s)"
IDMAP_SQL = "select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)"
OPP_RANK_SQL = "select defense, position, rank_std from analytics.mart_defense_vs_position_current"


def lineup_rows(query: Query, league_id: str, roster_id: int, week: int, *, as_of: datetime | None = None,
                client: Sleeper | None = None, exclude_reference: str | None = None,
                board: Board | None = None) -> OnDemand:
    """The proposed lineup of one roster-week of any Sleeper league, as the frame ``cards.lineup_rows`` returns.

    ``as_of`` decides which games have kicked off (default now; the parity test passes the nightly's). The range
    reference is never the league itself (a known league is measured as if it were new); ``exclude_reference``
    excludes one more."""
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
    scoring = {k: float(v) for k, v in (league.get("scoring_settings") or {}).items() if v is not None}
    slots = [str(s) for s in league.get("roster_positions") or []]
    as_of = as_of or datetime.now(UTC)

    b = board or load_board(query, season, week)
    t["board"] = time.perf_counter()
    proj = price_lines(b.line, scoring)
    t["price"] = time.perf_counter()
    ref = choose_reference(proj, b.fitted, exclude=league_id if exclude_reference is None else exclude_reference)
    if ref is None and exclude_reference is None:
        ref = choose_reference(proj, b.fitted, exclude=None)
    ranges = approximate_ranges(proj, b.fitted[ref]) if ref else pd.DataFrame(index=proj.index, columns=list(QUANTILES))
    t["ranges"] = time.perf_counter()

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
    kd_proj, k_team, kd_src = {}, {}, {}
    for pos in ("K", "DEF"):
        if pos not in {s.upper() for s in slots}:
            continue
        src = kd_source(scoring, pos, b)
        kd_src[pos] = src
        if src is None:
            continue
        rows_ = b.kd[(b.kd["league_id"] == src) & (b.kd["position"] == pos)]
        by_team: dict[str, list[dict]] = {}
        for r in rows_.itertuples():
            v = {"proj_points": None if pd.isna(r.proj_points) else float(r.proj_points), "team": r.team,
                 "report_status": r.report_status, "roster_status": r.roster_status}
            kd_proj[(league_id, int(week), r.unit_id)] = v
            if pos == "K" and r.team:
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
                  "roster_ids": [int(roster_id)]}],
        weeks={league_id: [int(week)]}, proj=proj_map, weekly={}, current={league_id: {int(roster_id): current}},
        sleeper=sleeper_meta, k_ppg={}, games=games, model_version=",".join(sorted(set(b.line["model_version"].dropna()))),
        starters={(league_id, int(roster_id)): [str(s) for s in (roster.get("starters") or [])]},
        kd_proj=kd_proj, k_team_proj=k_team)
    t["inputs"] = time.perf_counter()
    rows, totals, _ = LU.build(inp, as_of=as_of)
    t["solve"] = time.perf_counter()
    frame = _cards_frame(query, rows, totals[0] if totals else {}, ranges, b, dp, g, as_of)
    t["frame"] = time.perf_counter()
    marks = list(t)
    timings = {f"{marks[i]}": round((t[marks[i]] - t[marks[i - 1]]) * 1000, 1) for i in range(1, len(marks))}
    timings["total"] = round((t[marks[-1]] - t["start"]) * 1000, 1)
    return OnDemand(league=league, roster_id=int(roster_id), season=season, week=int(week), rows=frame,
                    totals=totals[0] if totals else {}, reference_league=ref, unmapped_players=unmapped,
                    scoring=scoring_report(scoring, slots), kd_sources=kd_src, mismatched_lines=b.mismatched_lines,
                    timings_ms=timings, sleeper_calls=sl.calls - calls0)


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
