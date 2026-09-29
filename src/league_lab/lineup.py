"""Exact lineup service (plan B1, Iteration 9b): the best legal lineup, not a greedy one.

What it does
------------
* ``solve(players, slots)`` fills a league's starting slots with a **maximum-weight bipartite
  matching** (``scipy.optimize.linear_sum_assignment``) over the eligible (player, slot) pairs:
  each player in at most one slot, a slot may stay empty, a player who cannot play is left out
  (with the reason), a locked player keeps his slot. A playable player with no value yet is
  **unvalued**: he counts 0 (``value_source = 'unvalued'``) and is seated only in a slot nobody
  valued can fill (the objective is total first, filled slots second, valued before unvalued third),
  so he never displaces a valued player nor changes the total. Eligibility is ``SLOT_ELIGIBILITY`` applied
  to the player's Sleeper ``fantasy_positions`` (Travis Hunter is DB/WR, so he may start at WR or
  FLEX), and SUPER_FLEX keeps all four positions — never "a second QB slot". It returns the
  lineup (slot -> player, value), its total, the bench in value order, the players who cannot
  play, and per filled slot the **margin**: the total minus the best total when that player is
  removed and the whole lineup is re-solved. That is how much he matters this week (0 = an equal
  alternative sits on the bench); it is never negative.
* ``lineups(conn, season)`` runs the solver for every current league x roster x week of the
  projected season and replaces that season's rows in ``ops.lineups`` / ``ops.lineup_totals``
  (``mart_lineup_recommendation`` publishes them with names). Per roster-week:

  - the **proposed** lineup: QB/RB/WR/TE at projection v2 ``proj_points`` (this league's scoring);
    K at the league's season PPG (``mart_league_player_season``), DEF at the points per game
    Sleeper observed for it in this league (v2 projects neither: ``value_source`` says so); a K or
    DEF Sleeper has not scored in this league yet, or a skill player without a v2 projection this
    week, is unvalued (seated only in an otherwise-empty slot);
    Out / Doubtful / NFL injured reserve / bye / Sleeper IR slot / taxi squad cannot play;
    Questionable plays and is flagged (``report_status``); in a week not yet scored, a player
    whose game has kicked off is locked: a starter keeps his slot, a bench player stays benched;
  - for weeks Sleeper has scored, the **realised** optimum: the same roster at the points
    Sleeper counted (``league_player_week.points_observed``) — the hindsight yardstick, which
    ``assert_exact_lineup_dominates_greedy`` holds against Sleeper's max points.

Why the realised lineup uses Sleeper's points for every position (not ``points_actual`` of the
projections mart for QB/RB/WR/TE): ``points_actual`` prices the projected components only, so it
drops 2-point conversions and long-TD bonuses (28 rostered player-weeks, 2 points each, in weeks
1-2 of 2026); a realised optimum built on it would fall below Sleeper's max points by construction.

Why ``lineups()`` reads ``ops.projections`` (+ ``mart_player_week_features`` for status) rather
than ``mart_player_week_projections``: it runs inside ``league-lab project`` right after the refit,
before dbt rebuilds that mart, so the mart still holds the previous refit. Values are rounded to
2 decimals exactly as the mart rounds them, so after the rebuild the two agree.
"""

from __future__ import annotations

import logging
import math
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import psycopg
from scipy.optimize import linear_sum_assignment

log = logging.getLogger(__name__)

# ------------------------------------------------------------------------------ slots
SKILL = frozenset({"QB", "RB", "WR", "TE"})
SLOT_ELIGIBILITY: dict[str, frozenset[str]] = {
    "QB": frozenset({"QB"}),
    "RB": frozenset({"RB"}),
    "WR": frozenset({"WR"}),
    "TE": frozenset({"TE"}),
    "K": frozenset({"K"}),
    "DEF": frozenset({"DEF"}),
    "FLEX": frozenset({"RB", "WR", "TE"}),
    "SUPER_FLEX": frozenset({"QB", "RB", "WR", "TE"}),
    "REC_FLEX": frozenset({"WR", "TE"}),
    "WRRB_FLEX": frozenset({"RB", "WR"}),
}
IGNORED_SLOTS = frozenset({"IDP_FLEX", "DL", "LB", "DB"})   # IDP is not modelled: dropped, reported
NOT_SLOTS = frozenset({"BN", "IR", "TAXI"})                  # roster spots, not starting slots
EPS = 1e-9    # per filled slot: among equal totals prefer the lineup that fills more slots
EPS2 = 1e-12  # per valued starter: then prefer a valued player (even at 0) over an unvalued one
UNVALUED = "unvalued"
# Sleeper team abbreviations that differ from nflverse's (dim_game): the Rams
SLEEPER_TO_NFLVERSE_TEAM = {"LAR": "LA"}


@dataclass(frozen=True, slots=True)
class Slot:
    label: str   # unique within a lineup: QB, RB1, RB2, FLEX1, SUPER_FLEX (numbered only when repeated)
    type: str    # the Sleeper slot name: RB, FLEX, ...
    order: int   # 1-based position among the starting slots (roster_positions order)


def parse_slots(roster_positions: Iterable[str]) -> tuple[list[Slot], list[str]]:
    """Sleeper ``roster_positions`` -> the starting slots (BN / IR / TAXI dropped) and the slot
    names that are not modelled (IDP, anything unknown), which are reported, never guessed."""
    kept, ignored = [], []
    for raw in roster_positions:
        s = str(raw).upper()
        if s in NOT_SLOTS:
            continue
        (kept if s in SLOT_ELIGIBILITY else ignored).append(s)
    counts, seen, out = Counter(kept), Counter(), []
    for i, t in enumerate(kept, 1):
        seen[t] += 1
        out.append(Slot(f"{t}{seen[t]}" if counts[t] > 1 else t, t, i))
    return out, ignored


# ------------------------------------------------------------------------------ the solver
@dataclass(frozen=True, slots=True)
class Player:
    """One rostered player as the solver sees him. ``value`` None (or ``value_source`` "unvalued")
    on a playable player = no value yet: ``solve`` carries him as unvalued (value 0, reason "no value
    yet") and seats him only where nobody valued can play. ``locked_slot`` = the Sleeper slot type
    he is locked into."""
    id: str
    position: str | None
    value: float | None
    playable: bool = True
    locked_slot: str | None = None
    value_source: str | None = None
    reason: str | None = None          # why he cannot play
    status: str | None = None          # injury report status (Questionable plays, flagged)
    fantasy_positions: tuple[str, ...] | None = None   # Sleeper eligibility; default (position,)

    @property
    def positions(self) -> frozenset[str]:
        if self.fantasy_positions:
            return frozenset(self.fantasy_positions)
        return frozenset({self.position}) if self.position else frozenset()


_PLAYER_FIELDS = {f.name for f in fields(Player)}


def _as_player(p: Player | Mapping) -> Player:
    if isinstance(p, Player):
        return p
    d = {k: v for k, v in p.items() if k in _PLAYER_FIELDS}
    if isinstance(d.get("fantasy_positions"), list):
        d["fantasy_positions"] = tuple(d["fantasy_positions"])
    return Player(**d)


@dataclass(frozen=True, slots=True)
class Start:
    slot: Slot
    player: Player | None      # None = empty slot
    margin: float | None       # None for an empty slot and for a locked player (not a decision)
    locked: bool = False

    @property
    def value(self) -> float | None:
        return self.player.value if self.player is not None else None


@dataclass(frozen=True)
class Lineup:
    starts: tuple[Start, ...]
    total: float
    bench: tuple[Player, ...]            # playable, not starting, best value first
    unplayable: tuple[Player, ...]       # each with .reason
    ignored_slots: tuple[str, ...] = ()

    @property
    def lineup(self) -> dict[str, tuple[Player | None, float | None]]:
        return {s.slot.label: (s.player, s.value) for s in self.starts}

    @property
    def margins(self) -> dict[str, float]:
        return {s.slot.label: s.margin for s in self.starts if s.margin is not None}

    @property
    def empty_slots(self) -> list[str]:
        return [s.slot.label for s in self.starts if s.player is None]

    @property
    def starter_ids(self) -> list[str]:
        return [s.player.id for s in self.starts if s.player is not None]

    @property
    def weakest(self) -> Start | None:
        """The filled, unlocked, valued slot with the smallest margin (ties: the lower value). An
        unvalued starter (margin 0 by construction) is not a decision and is left out."""
        cands = [s for s in self.starts if s.margin is not None and s.player.value_source != UNVALUED]
        return min(cands, key=lambda s: (s.margin, s.value, s.slot.order)) if cands else None


def _match(values: np.ndarray, elig: np.ndarray, tie: np.ndarray) -> tuple[float, np.ndarray]:
    """Maximum-weight matching of players (rows) to slots (columns) where a slot may stay empty.
    Non-edges and negative values weigh 0, which is exactly "leave the slot empty / the player
    benched", so the optimum of the assignment problem is the optimum of the matching. ``tie`` per
    row (EPS, + EPS2 for a valued player) orders equal totals: more filled slots, then more valued
    starters. Returns (total value, player row per slot or -1)."""
    n, m = elig.shape
    assign = np.full(m, -1, dtype=np.intp)
    if n == 0 or m == 0:
        return 0.0, assign
    w = np.where(elig, (values + tie)[:, None], 0.0)
    np.maximum(w, 0.0, out=w)
    rows, cols = linear_sum_assignment(w, maximize=True)
    keep = w[rows, cols] > 0.0
    assign[cols[keep]] = rows[keep]
    used = assign[assign >= 0]
    return float(values[used].sum()), assign


def _canonical(assign: np.ndarray, values: np.ndarray, elig: np.ndarray, types: list[str]) -> np.ndarray:
    """Same starters, same total, readable seating: the better players in the narrower slots
    (Jefferson at WR and the WR3 at FLEX, not the other way round). A second assignment over the
    chosen starters only; any eligible seating of them is legal and scores the same."""
    starters = assign[assign >= 0]
    if len(starters) < 2:
        return assign
    spec = np.array([1.0 / len(SLOT_ELIGIBILITY[t]) for t in types])
    se = elig[starters]
    w = np.where(se, 1e6 + (np.maximum(values[starters], 0.0) + 1.0)[:, None] * spec[None, :], 0.0)
    rows, cols = linear_sum_assignment(w, maximize=True)
    if len(rows) != len(starters) or not se[rows, cols].all():
        return assign
    out = np.full_like(assign, -1)
    out[cols] = starters[rows]
    return out


def solve(players: Sequence[Player | Mapping], slots: Iterable[str], *, margins: bool = True) -> Lineup:
    """The best legal lineup for ``slots`` (Sleeper ``roster_positions``; BN/IR/TAXI ignored) from
    ``players`` (``Player`` or mappings with its fields). See the module docstring."""
    slot_list, ignored = parse_slots(slots)
    types = [s.type for s in slot_list]
    open_cols = list(range(len(slot_list)))
    unplayable: list[Player] = []
    locked: dict[int, Player] = {}
    pool: list[Player] = []
    for p in map(_as_player, players):
        given = p
        if (p.playable or p.locked_slot is not None) and (
                p.value is None or not math.isfinite(p.value) or p.value_source == UNVALUED):
            p = replace(p, value=0.0, value_source=UNVALUED, reason=p.reason or "no value yet")
        if p.locked_slot is not None:
            t = p.locked_slot.upper()
            j = next((j for j in open_cols if types[j] == t), None)
            if j is None:
                unplayable.append(replace(p, playable=False, reason=p.reason or f"locked in {t}, which is not a free slot here"))
            else:
                open_cols.remove(j)
                locked[j] = p
        elif not p.playable:
            unplayable.append(p if p.reason else replace(p, reason="cannot play"))
        elif not any(p.positions & SLOT_ELIGIBILITY[t] for t in set(types)):
            unplayable.append(replace(given, playable=False, reason=f"no {p.position} slot in this lineup"))
        else:
            pool.append(p)

    cols = np.array(open_cols, dtype=np.intp)
    vals = np.array([p.value for p in pool], dtype=float)
    tie = np.array([EPS + (0.0 if p.value_source == UNVALUED else EPS2) for p in pool], dtype=float)
    elig = np.array([[bool(p.positions & SLOT_ELIGIBILITY[types[j]]) for j in open_cols] for p in pool],
                    dtype=bool).reshape(len(pool), len(open_cols))
    free_total, assign = _match(vals, elig, tie)
    locked_total = sum(p.value for p in locked.values() if p.value is not None and math.isfinite(p.value))

    chosen: dict[int, tuple[int, float | None]] = {}
    for k, i in enumerate(_canonical(assign, vals, elig, [types[j] for j in open_cols])):
        if i < 0:
            continue
        margin = None
        if margins:
            mask = np.ones(len(pool), dtype=bool)
            mask[i] = False
            alt, _ = _match(vals[mask], elig[mask], tie[mask])
            margin = free_total - alt
            margin = 0.0 if abs(margin) < 1e-6 else margin   # EPS tie-breaks move a total by < slots x 1e-9
        chosen[int(cols[k])] = (int(i), margin)

    # one Start per slot; same-type slots are interchangeable, so list them best first (RB1 >= RB2)
    entries: list[tuple[Player | None, float | None, bool]] = []
    for j in range(len(slot_list)):
        if j in locked:
            entries.append((locked[j], None, True))
        elif j in chosen:
            i, margin = chosen[j]
            entries.append((pool[i], margin, False))
        else:
            entries.append((None, None, False))
    by_type: dict[str, list[int]] = defaultdict(list)
    for j, t in enumerate(types):
        by_type[t].append(j)
    ordered = list(entries)
    for idx in by_type.values():
        if len(idx) > 1:
            group = sorted((entries[j] for j in idx),
                           key=lambda e: (e[0] is None, -(e[0].value if e[0] is not None and e[0].value is not None else -math.inf)))
            for j, e in zip(idx, group, strict=True):
                ordered[j] = e
    starts = tuple(Start(slot_list[j], p, m, lk) for j, (p, m, lk) in enumerate(ordered))

    starting = {i for i, _ in chosen.values()}
    bench = tuple(sorted((p for i, p in enumerate(pool) if i not in starting), key=lambda p: (-p.value, p.id)))
    return Lineup(starts, locked_total + free_total, bench, tuple(unplayable), tuple(ignored))


# ------------------------------------------------------------------------------ persistence
DDL = {
    "ops.lineups": """create table if not exists ops.lineups (
        run_at timestamptz, model_version text, league_id text, season integer, week integer, roster_id integer,
        is_realised boolean, role text, slot text, slot_type text, slot_order integer, bench_rank integer,
        sleeper_player_id text, gsis_id text, player_name text, position text, value double precision,
        value_source text, margin double precision, is_locked boolean, report_status text, reason text)""",
    "ops.lineup_totals": """create table if not exists ops.lineup_totals (
        run_at timestamptz, as_of timestamptz, model_version text, league_id text, season integer, week integer,
        roster_id integer, is_realised boolean, lineup_value double precision, bench_value double precision,
        slots_total integer, slots_filled integer, empty_slots text, weakest_slot text, weakest_margin double precision,
        weakest_sleeper_player_id text, n_players integer, n_bench integer, n_unplayable integer, n_locked integer,
        n_questionable integer, n_ppg_valued integer, inputs_fingerprint text, n_unvalued integer);
        alter table ops.lineup_totals add column if not exists n_unvalued integer""",
}
LINEUP_COLUMNS = ["run_at", "model_version", "league_id", "season", "week", "roster_id", "is_realised", "role", "slot",
                  "slot_type", "slot_order", "bench_rank", "sleeper_player_id", "gsis_id", "player_name", "position",
                  "value", "value_source", "margin", "is_locked", "report_status", "reason"]
TOTALS_COLUMNS = ["run_at", "as_of", "model_version", "league_id", "season", "week", "roster_id", "is_realised",
                  "lineup_value", "bench_value", "slots_total", "slots_filled", "empty_slots", "weakest_slot",
                  "weakest_margin", "weakest_sleeper_player_id", "n_players", "n_bench", "n_unplayable", "n_locked",
                  "n_questionable", "n_ppg_valued", "inputs_fingerprint", "n_unvalued"]
PPG_SOURCES = ("season_ppg", "observed_ppg")

# The fingerprint of the Sleeper points a realised lineup was solved on; the dbt test recomputes it
# with the same expression and skips roster-weeks whose points changed since (a stat correction
# between the nightly dbt build and the next `league-lab lineups`), so it never fails on stale rows.
FINGERPRINT_SQL = ("md5(string_agg(sleeper_player_id || '=' || coalesce(points_observed::text, ''), ',' "
                   "order by sleeper_player_id))")


def _r2(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x) + 0.0, 2) + 0.0


# ------------------------------------------------------------------------------ inputs
@dataclass
class LineupInputs:
    """Everything ``build()`` needs, loaded by ``load_inputs()`` (or built by hand in tests)."""
    season: int
    leagues: list[dict]                                     # league_id, roster_positions, last_scored_leg, roster_ids
    weeks: dict[str, list[int]]                             # league_id -> projected weeks
    proj: dict[tuple[str, int, str], dict]                  # (league, week, gsis) -> proj_points, team, report_status, roster_status
    weekly: dict[tuple[str, int], dict[int, list[dict]]]    # (league, week) -> roster -> Sleeper's list for that week
    current: dict[str, dict[int, list[dict]]]               # league -> roster -> current roster (with IR / taxi flags)
    sleeper: dict[str, dict]                                # sleeper id -> position, fantasy_positions, team
    k_ppg: dict[tuple[str, str], float]                     # (league, gsis) -> season PPG in the league's scoring
    games: dict[int, dict[str, datetime | None]]            # week -> nflverse team -> kickoff
    fingerprints: dict[tuple[str, int, int], str] = field(default_factory=dict)
    model_version: str | None = None


def _frame(cur: psycopg.Cursor, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    names = [d.name for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def _num(v) -> float | None:
    return None if v is None else float(v)


def load_inputs(conn: psycopg.Connection, season: int) -> LineupInputs:
    with conn.cursor() as cur:
        leagues = _frame(cur, """
            select l.league_id, l.roster_positions, coalesce(l.last_scored_leg, 0) as last_scored_leg,
                   array(select m.roster_id from analytics.dim_league_member m where m.league_id = l.league_id order by 1) as roster_ids
            from analytics.dim_league_season l where l.season = %s and l.is_current_season order by l.league_id""", (season,))
        ids = [lg["league_id"] for lg in leagues]
        # fresh projections (see module docstring) with the as-of status the mart shows next to them
        proj_rows = _frame(cur, """
            select p.league_id, p.week, p.gsis_id, round(p.proj_points::numeric, 2) as proj_points, p.model_version,
                   f.team, f.report_status, f.roster_status
            from ops.projections as p
            join analytics.mart_player_week_features as f using (gsis_id, season, week)
            where p.season = %s and p.league_id = any(%s)""", (season, ids))
        weekly_rows = _frame(cur, """
            select league_id, week, roster_id, sleeper_player_id, gsis_id, player_name, position, is_starter, slot,
                   points_observed, is_scored_week
            from analytics.league_player_week where season = %s and league_id = any(%s)""", (season, ids))
        fp_rows = _frame(cur, f"""
            select league_id, week, roster_id, {FINGERPRINT_SQL} as fp
            from analytics.league_player_week where season = %s and league_id = any(%s) and is_scored_week
            group by 1, 2, 3""", (season, ids))
        current_rows = _frame(cur, """
            select league_id, roster_id, sleeper_player_id, gsis_id, player_name, position, nfl_team, is_on_ir, is_on_taxi
            from analytics.mart_league_roster_membership where league_id = any(%s)""", (ids,))
        sids = sorted({r["sleeper_player_id"] for r in weekly_rows} | {r["sleeper_player_id"] for r in current_rows})
        sleeper_rows = _frame(cur, """
            select sleeper_player_id, position, fantasy_positions, team
            from staging.stg_sleeper__players where sleeper_player_id = any(%s)""", (sids,))
        k_rows = _frame(cur, """
            select league_id, gsis_id, ppg from analytics.mart_league_player_season
            where season = %s and league_id = any(%s) and games_played > 0 and ppg is not null""", (season, ids))
        game_rows = _frame(cur, """
            select week, home_team, away_team, kickoff_at from analytics.dim_game
            where season = %s and season_type = 'REG'""", (season,))

    proj: dict[tuple[str, int, str], dict] = {}
    weeks: dict[str, set[int]] = defaultdict(set)
    versions = set()
    for r in proj_rows:
        proj[(r["league_id"], int(r["week"]), r["gsis_id"])] = {
            "proj_points": _num(r["proj_points"]), "team": r["team"],
            "report_status": r["report_status"], "roster_status": r["roster_status"]}
        weeks[r["league_id"]].add(int(r["week"]))
        versions.add(r["model_version"])
    weekly: dict[tuple[str, int], dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in weekly_rows:
        r["points_observed"] = _num(r["points_observed"])
        weekly[(r["league_id"], int(r["week"]))][int(r["roster_id"])].append(r)
    current: dict[str, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in current_rows:
        current[r["league_id"]][int(r["roster_id"])].append(r)
    games: dict[int, dict[str, datetime | None]] = defaultdict(dict)
    for g in game_rows:
        games[int(g["week"])][g["home_team"]] = g["kickoff_at"]
        games[int(g["week"])][g["away_team"]] = g["kickoff_at"]
    return LineupInputs(
        season=season,
        leagues=[{**lg, "roster_ids": list(lg["roster_ids"])} for lg in leagues],
        weeks={k: sorted(v) for k, v in weeks.items()},
        proj=proj, weekly=weekly, current=current,
        sleeper={r["sleeper_player_id"]: r for r in sleeper_rows},
        k_ppg={(r["league_id"], r["gsis_id"]): float(r["ppg"]) for r in k_rows},
        games=games,
        fingerprints={(r["league_id"], int(r["week"]), int(r["roster_id"])): r["fp"] for r in fp_rows},
        model_version=",".join(sorted(v for v in versions if v)) or None,
    )


# ------------------------------------------------------------------------------ building the lineups
def _team(t: str | None) -> str | None:
    return SLEEPER_TO_NFLVERSE_TEAM.get(t, t) if t else None


def _observed_ppg(inp: LineupInputs) -> dict[tuple[str, str], float]:
    """(league, sleeper id) -> mean Sleeper points over the scored weeks this league rostered him
    and his NFL team played (a bye's 0 is not a game). Used for DEF and for a K without an NFL id."""
    pts: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for (league_id, week), rosters in inp.weekly.items():
        for rows in rosters.values():
            for r in rows:
                if not r["is_scored_week"] or r["points_observed"] is None:
                    continue
                sid = r["sleeper_player_id"]
                team = _team(sid if (r["position"] == "DEF") else (inp.sleeper.get(sid) or {}).get("team"))
                if team is not None and team not in inp.games.get(week, {}):
                    continue
                pts[(league_id, sid)][week] = r["points_observed"]
    return {k: round(sum(v.values()) / len(v), 2) for k, v in pts.items() if v}


def _meta(inp: LineupInputs, row: dict) -> tuple[str | None, tuple[str, ...] | None, str | None]:
    sp = inp.sleeper.get(row["sleeper_player_id"]) or {}
    position = row.get("position") or sp.get("position")
    fp = tuple(sp["fantasy_positions"]) if sp.get("fantasy_positions") else None
    return position, fp, _team(sp.get("team") or row.get("nfl_team"))


def _proposed_player(inp: LineupInputs, league_id: str, week: int, row: dict, cur: dict | None,
                     obs_ppg: dict, unscored: bool, as_of: datetime) -> Player:
    sid, gsis = row["sleeper_player_id"], row.get("gsis_id")
    position, fp, team = _meta(inp, row)
    positions = frozenset(fp) if fp else frozenset({position} if position else ())
    base = Player(id=sid, position=position, value=None, fantasy_positions=fp)
    pr = inp.proj.get((league_id, week, gsis)) if gsis else None
    if pr is not None and pr["team"]:
        team = pr["team"]
    if "DEF" in positions and not positions & SKILL:
        team = _team(sid)

    # value and status first (an unplayable player keeps his value for display)
    status = None
    if positions & SKILL:
        if pr is not None:
            base = replace(base, value=pr["proj_points"], value_source="proj_points")
            status = pr["report_status"]
    elif "K" in positions:
        if gsis and (league_id, gsis) in inp.k_ppg:
            base = replace(base, value=inp.k_ppg[(league_id, gsis)], value_source="season_ppg")
        elif (league_id, sid) in obs_ppg:
            base = replace(base, value=obs_ppg[(league_id, sid)], value_source="observed_ppg")
    elif "DEF" in positions and (league_id, sid) in obs_ppg:
        base = replace(base, value=obs_ppg[(league_id, sid)], value_source="observed_ppg")
    base = replace(base, status=status)

    def out(reason: str) -> Player:
        return replace(base, playable=False, reason=reason)

    if unscored and cur is not None:
        if cur.get("is_on_ir"):
            return out("IR slot")
        if cur.get("is_on_taxi"):
            return out("taxi squad")
    kickoff = inp.games.get(week, {}).get(team) if team else None
    if unscored and kickoff is not None and kickoff <= as_of:
        if row.get("is_starter") and row.get("slot"):
            return replace(base, locked_slot=row["slot"])
        return out("game started (bench)")
    if team is not None and inp.games and team not in inp.games.get(week, {}):
        return out("bye")
    # no value yet (no v2 projection this week; a K / DEF Sleeper has not scored in this league):
    # playable, carried at 0 as unvalued, seated by solve() only where nobody valued can play
    unvalued = replace(base, value=None, value_source=UNVALUED, reason="no value yet")
    if positions & SKILL:
        if pr is None:
            return unvalued if team else out("no NFL team")   # no NFL team: not on a roster, no game
        if pr["roster_status"] == "RES":
            return out("NFL injured reserve")
        if pr["report_status"] in ("Out", "Doubtful"):
            return out(pr["report_status"])
        return base
    if positions & {"K", "DEF"}:
        return base if base.value is not None else unvalued
    return base  # no slot for his position: solve() says so


def _emit(lu: Lineup, key: dict, names: dict[str, dict]) -> tuple[list[dict], dict]:
    rows = []

    def row(p: Player | None, **kw) -> dict:
        n = names.get(p.id, {}) if p else {}
        return {**key, "sleeper_player_id": p.id if p else None, "gsis_id": n.get("gsis_id"),
                "player_name": n.get("player_name"), "position": p.position if p else None,
                "value": _r2(p.value) if p else None, "value_source": p.value_source if p else None,
                "report_status": p.status if p else None, "slot": None, "slot_type": None, "slot_order": None,
                "bench_rank": None, "margin": None, "is_locked": False, "reason": p.reason if p else None, **kw}

    for s in lu.starts:
        rows.append(row(s.player, role="starter" if s.player else "empty", slot=s.slot.label, slot_type=s.slot.type,
                        slot_order=s.slot.order, margin=_r2(s.margin), is_locked=s.locked))
    for i, p in enumerate(lu.bench, 1):
        rows.append(row(p, role="bench", bench_rank=i))
    for p in lu.unplayable:
        rows.append(row(p, role="unplayable"))
    w = lu.weakest
    starters = [s.player for s in lu.starts if s.player is not None]
    total = {
        **key, "lineup_value": _r2(lu.total), "slots_total": len(lu.starts), "slots_filled": len(starters),
        "empty_slots": ", ".join(lu.empty_slots) or None,
        "weakest_slot": w.slot.label if w else None, "weakest_margin": _r2(w.margin) if w else None,
        "weakest_sleeper_player_id": w.player.id if w else None,
        "n_players": len(starters) + len(lu.bench) + len(lu.unplayable), "n_bench": len(lu.bench),
        "n_unplayable": len(lu.unplayable), "n_locked": sum(s.locked for s in lu.starts),
        "n_questionable": sum(p.status == "Questionable" for p in starters),
        "n_ppg_valued": sum(p.value_source in PPG_SOURCES for p in starters),
        "n_unvalued": sum(p.value_source == UNVALUED for p in starters),
    }
    return rows, total


def build(inp: LineupInputs, as_of: datetime | None = None, run_at: datetime | None = None) -> tuple[list[dict], list[dict], float]:
    """Solve every league x roster x projected week (and realised scored weeks). Returns
    (ops.lineups rows, ops.lineup_totals rows, seconds spent in the solver)."""
    as_of = as_of or datetime.now(UTC)
    run_at = run_at or datetime.now(UTC)
    obs_ppg = _observed_ppg(inp)
    rows: list[dict] = []
    totals: list[dict] = []
    solve_s = 0.0
    for lg in inp.leagues:
        league_id, slots = lg["league_id"], list(lg["roster_positions"] or [])
        cur_by_roster = inp.current.get(league_id, {})
        for week in inp.weeks.get(league_id, []):
            scored = week <= int(lg["last_scored_leg"])
            week_lists = inp.weekly.get((league_id, week))
            for roster_id in lg["roster_ids"]:
                cur_rows = {r["sleeper_player_id"]: r for r in cur_by_roster.get(roster_id, [])}
                # Sleeper's list for that week when there is one (it carries the slots of locked
                # starters); otherwise, and for a roster missing from it in an unscored week, today's roster
                roster = (week_lists or {}).get(roster_id) or ([] if scored else list(cur_rows.values()))
                if scored and not roster:
                    continue   # a scored week Sleeper has no list for: nothing honest to solve
                names = {r["sleeper_player_id"]: {"gsis_id": r.get("gsis_id"), "player_name": r.get("player_name")} for r in roster}
                key = {"run_at": run_at, "league_id": league_id, "season": inp.season, "week": week, "roster_id": roster_id}
                players = [_proposed_player(inp, league_id, week, r, cur_rows.get(r["sleeper_player_id"]),
                                            obs_ppg, not scored, as_of) for r in roster]
                t0 = time.perf_counter()
                lu = solve(players, slots)
                bench_lu = solve(lu.bench, slots, margins=False)
                solve_s += time.perf_counter() - t0
                r_rows, tot = _emit(lu, {**key, "model_version": inp.model_version, "is_realised": False}, names)
                rows += r_rows
                totals.append({**tot, "as_of": as_of, "bench_value": _r2(bench_lu.total), "inputs_fingerprint": None})
                if scored and week_lists and roster_id in week_lists:
                    realised = []
                    for r in roster:
                        position, fp, _ = _meta(inp, r)
                        v = r["points_observed"]
                        realised.append(Player(id=r["sleeper_player_id"], position=position, fantasy_positions=fp, value=v,
                                               playable=v is not None, value_source="sleeper_observed",
                                               reason=None if v is not None else "no Sleeper points"))
                    t0 = time.perf_counter()
                    rl = solve(realised, slots)
                    rb = solve(rl.bench, slots, margins=False)
                    solve_s += time.perf_counter() - t0
                    r_rows, tot = _emit(rl, {**key, "model_version": None, "is_realised": True}, names)
                    rows += r_rows
                    totals.append({**tot, "as_of": as_of, "bench_value": _r2(rb.total),
                                   "inputs_fingerprint": inp.fingerprints.get((league_id, week, roster_id))})
    return rows, totals, solve_s


def _write(conn: psycopg.Connection, season: int, rows: list[dict], totals: list[dict]) -> None:
    """Replace the season's rows in both tables in one transaction."""
    with conn.cursor() as cur:
        for ddl in DDL.values():
            cur.execute(ddl)
        for table, cols, data in (("ops.lineups", LINEUP_COLUMNS, rows), ("ops.lineup_totals", TOTALS_COLUMNS, totals)):
            cur.execute(f"delete from {table} where season = %s", (season,))
            with cur.copy(f"copy {table} ({', '.join(cols)}) from stdin") as cp:
                for d in data:
                    cp.write_row([d.get(c) for c in cols])
    conn.commit()


@dataclass
class LineupRun:
    season: int | None
    rows: pd.DataFrame
    totals: pd.DataFrame
    seconds: float
    solve_seconds: float
    next_week: int | None


def lineups(conn: psycopg.Connection, season: int | None = None, as_of: datetime | None = None) -> LineupRun:
    """Solve and write ``ops.lineups`` / ``ops.lineup_totals`` for the projected season (default:
    the newest in ``ops.projections``). ``as_of`` (default now) decides which games have kicked off."""
    t0 = time.perf_counter()
    as_of = as_of or datetime.now(UTC)
    if season is None:
        with conn.cursor() as cur:
            cur.execute("select max(season) from ops.projections")
            season = cur.fetchone()[0]
    if season is None:
        log.warning("lineups: ops.projections is empty (run `league-lab project` first)")
        return LineupRun(None, pd.DataFrame(columns=LINEUP_COLUMNS), pd.DataFrame(columns=TOTALS_COLUMNS), 0.0, 0.0, None)
    season = int(season)
    inp = load_inputs(conn, season)
    if not inp.leagues:
        log.warning("lineups: no current league plays season %s; nothing written", season)
    rows, totals, solve_s = build(inp, as_of=as_of)
    _write(conn, season, rows, totals)
    upcoming = sorted(w for w, teams in inp.games.items() if any(k is not None and k > as_of for k in teams.values()))
    run = LineupRun(season, pd.DataFrame(rows, columns=LINEUP_COLUMNS), pd.DataFrame(totals, columns=TOTALS_COLUMNS),
                    time.perf_counter() - t0, solve_s, upcoming[0] if upcoming else None)
    realised = int(run.totals["is_realised"].sum()) if len(run.totals) else 0
    log.info("lineups written for %s: %s rows, %s roster-weeks (%s proposed, %s realised) in %.2f s (solver %.2f s)",
             season, len(rows), len(totals), len(totals) - realised, realised, run.seconds, solve_s)
    return run


def lineups_after_project(conn: psycopg.Connection, season: int | None) -> LineupRun | None:
    """Called at the end of ``league-lab project``: a failure here is logged, never fatal to the
    projections already written (the previous ``ops.lineups`` rows are kept)."""
    try:
        return lineups(conn, season)
    except Exception:
        conn.rollback()
        log.exception("lineup service failed (projections were written); run `league-lab lineups`")
        return None


def run_lineups(season: int | None = None) -> LineupRun:
    from .config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        return lineups(conn, season)
