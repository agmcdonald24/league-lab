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
    K and DEF at their kd1.0 projection (plan R-13, ``league_lab.kdef``: ``proj_points`` in this
    league's scoring, ``value_source = 'proj_points'``; a K Sleeper cannot map to an NFL id takes
    the projection of the one kicker his NFL team has that week), falling back to the league's
    season PPG for a K (``mart_league_player_season``) and to the points per game Sleeper observed
    in this league for a DEF when no projection exists; a K or DEF with neither, or a skill player
    without a v2 projection this week, is unvalued (seated only in an otherwise-empty slot);
    Out / Doubtful / NFL injured reserve / bye / Sleeper IR slot / taxi squad cannot play;
    Questionable plays and is flagged (``report_status``); in a week not yet scored, a player
    whose game has kicked off is locked: a starter keeps his slot, a bench player stays benched
    (where he was: Sleeper's list for that week, else today's `starters` array — ``starter_slots``);
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
import re
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import psycopg
from scipy.optimize import linear_sum_assignment

from . import clock

log = logging.getLogger(__name__)

# ------------------------------------------------------------------------------ slots
# ---- IC-2 (Wave I-C): a slot is an eligibility set. Sleeper's names (below), generic combined names "A+B[+C]" (the
# MyFantasyLeague translation: "WR+TE", "RB+WR+TE", "QB+RB+WR+TE"; Sleeper never emits them) and the team units
# "TMQB" / "TMPK" (MFL's team quarterback / kicker: one "player" per NFL team) and "TMDEF" (= a team defense, DEF).
SKILL = frozenset({"QB", "RB", "WR", "TE"})
UNITS = frozenset({"TMQB", "TMPK"})                  # team units that are positions of their own (TMDEF is a DEF)
UNIT_PRICES_AS = {"TMQB": "QB", "TMPK": "K", "TMDEF": "DEF"}   # the position whose scoring rules price a unit
UNIT_WORDS = {"TMQB": "QB", "TMPK": "kicker", "TMDEF": "defense"}
# a slot-name part -> the position it admits (MFL's PK / Def spellings; TMDEF is a team defense)
POSITION_ALIASES = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "PK": "K", "DEF": "DEF", "D": "DEF",
                    "DST": "DEF", "D/ST": "DEF", "TMDEF": "DEF", "TMQB": "TMQB", "TMPK": "TMPK"}
IDP_POSITIONS = frozenset({"DL", "LB", "DB", "DT", "DE", "CB", "S", "IDP", "IDP_FLEX"})   # not modelled: reported
_BASE_ELIGIBILITY: dict[str, frozenset[str]] = {
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


def slot_eligibility(name: str | None) -> frozenset[str] | None:
    """The positions a slot admits, or None for a slot that is not modelled (IDP, unknown names: reported, never
    guessed). Sleeper's names; ``PK`` / ``Def`` / ``TMDEF``; the units ``TMQB`` / ``TMPK`` (only their own unit);
    ``A+B[+C]`` = the union of the parts (``WR+TE`` -> {WR, TE}); a combined name with an IDP or unknown part is
    not modelled (``DT+DE``, ``LB+DB``)."""
    s = str(name or "").strip().upper()
    if not s:
        return None
    if s in _BASE_ELIGIBILITY:
        return _BASE_ELIGIBILITY[s]
    if s in POSITION_ALIASES:
        return frozenset({POSITION_ALIASES[s]})
    if "+" in s or "/" in s:
        parts = [x.strip() for x in re.split(r"[+/]", s) if x.strip()]
        out: set[str] = set()
        for x in parts:
            pos = POSITION_ALIASES.get(x)
            if pos is None:
                return None
            out.add(pos)
        return frozenset(out) if out else None
    return None


class _Eligibility(dict):
    """``SLOT_ELIGIBILITY``: Sleeper's slot names as before, and any name ``slot_eligibility`` understands on lookup
    (``SLOT_ELIGIBILITY["WR+TE"]``, ``.get("TMQB")``), so every reader of slot types keeps working on an MFL league."""

    def __missing__(self, key):
        e = slot_eligibility(key)
        if e is None:
            raise KeyError(key)
        return e

    def get(self, key, default=None):
        e = slot_eligibility(key) if key is not None else None
        return default if e is None else e

    def __contains__(self, key) -> bool:
        return isinstance(key, str) and slot_eligibility(key) is not None


SLOT_ELIGIBILITY: dict[str, frozenset[str]] = _Eligibility(_BASE_ELIGIBILITY)
IGNORED_SLOTS = frozenset({"IDP_FLEX", "DL", "LB", "DB"})   # IDP is not modelled: dropped, reported
NOT_SLOTS = frozenset({"BN", "IR", "TAXI"})                  # roster spots, not starting slots
NO_SLOT = "No slot for"                                      # the reason's prefix: no slot in this league admits him
EPS = 1e-9    # per filled slot: among equal totals prefer the lineup that fills more slots
EPS2 = 1e-12  # per valued starter: then prefer a valued player (even at 0) over an unvalued one
UNVALUED = "unvalued"
# Sleeper team abbreviations that differ from nflverse's (dim_game): the Rams
SLEEPER_TO_NFLVERSE_TEAM = {"LAR": "LA"}


def no_slot_reason(position: str | None) -> str:
    """"No slot for a TMQB in this league": a player no starting slot admits. Not "can't play" (he is not hurt,
    on a bye or locked): the league's lineup has no place for his position."""
    p = str(position or "player")
    return f"{NO_SLOT} {'an' if p[:1] in 'AEFHILMNORSX' else 'a'} {p} in this league"


def is_no_slot(reason: str | None) -> bool:
    return isinstance(reason, str) and reason.startswith(NO_SLOT)


@dataclass(frozen=True, slots=True)
class Slot:
    label: str               # unique within a lineup, the league's own name: QB, RB1, WR+TE2, TMQB, SUPER_FLEX
    type: str                # the slot's name (upper case): RB, FLEX, WR+TE, TMQB ...
    elig: frozenset[str]     # the positions that may start here (FLEX {RB, WR, TE}; WR+TE {WR, TE}; TMDEF {DEF})
    order: int               # 1-based position among the starting slots (roster_positions order)


def parse_slots(roster_positions: Iterable[str]) -> tuple[list[Slot], list[str]]:
    """``roster_positions`` (Sleeper's, or the MFL translation's) -> the starting slots (BN / IR / TAXI dropped) and
    the slot names that are not modelled (IDP, anything unknown), which are reported, never guessed."""
    kept, ignored = [], []
    for raw in roster_positions:
        s = str(raw).strip().upper()
        if s in NOT_SLOTS:
            continue
        (kept if slot_eligibility(s) is not None else ignored).append(s)
    counts, seen, out = Counter(kept), Counter(), []
    for i, t in enumerate(kept, 1):
        seen[t] += 1
        out.append(Slot(f"{t}{seen[t]}" if counts[t] > 1 else t, t, slot_eligibility(t), i))
    return out, ignored


def align_starters(roster_positions: Iterable[str], starters: Iterable[tuple[str, Iterable[str]]]) -> list[str]:
    """A starters list in no slot order (MFL's: ids only) -> Sleeper's ``starters`` array: one id per starting slot of
    ``roster_positions`` (BN / IR / TAXI out, IDP slots keep their place), "0" for an empty slot. ``starters``:
    (id, positions) pairs, seated by a maximum matching that prefers the narrowest slot (a WR at WR before WR+TE
    before FLEX), so ``starter_slots`` reads the slot each starter really holds. A starter no open slot admits is
    left out of the array."""
    positions = [str(x).strip().upper() for x in roster_positions if str(x).strip().upper() not in NOT_SLOTS]
    elig = [slot_eligibility(t) or frozenset() for t in positions]
    out = ["0"] * len(positions)
    pairs = [(str(i), frozenset(p or ())) for i, p in starters]
    if not pairs or not positions:
        return out
    w = np.array([[(1.0 + 1.0 / max(1, len(e))) if (e & pos) else 0.0 for e in elig] for _, pos in pairs])
    rows, cols = linear_sum_assignment(w, maximize=True)
    for i, j in zip(rows, cols, strict=True):
        if w[i, j] > 0:
            out[j] = pairs[i][0]
    return out
# ---- end IC-2


def starter_slots(roster_positions: Iterable[str], starters: Iterable[str] | None) -> dict[str, str]:
    """Sleeper's roster ``starters`` array -> {player id: Sleeper slot}. The array is ordered like
    ``roster_positions`` without BN / IR / TAXI (IDP slots keep their place, so the alignment holds
    even though the solver ignores them); "0" (or empty) is an empty slot."""
    positions = [str(x).upper() for x in roster_positions if str(x).upper() not in NOT_SLOTS]
    return {sid: slot for slot, sid in zip(positions, starters or [], strict=False) if sid and sid != "0"}


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

    # ---- IC-2: a player no slot admits is listed with the unplayable (the rows keep role "unplayable", so every
    # reader leaves him out of the lineup), but he is not "can't play": ``no_slot`` / ``cannot_play`` split them
    @property
    def no_slot(self) -> tuple[Player, ...]:
        return tuple(p for p in self.unplayable if is_no_slot(p.reason))

    @property
    def cannot_play(self) -> tuple[Player, ...]:
        return tuple(p for p in self.unplayable if not is_no_slot(p.reason))
    # ---- end IC-2

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


def _canonical(assign: np.ndarray, values: np.ndarray, elig: np.ndarray, sets: list[frozenset[str]]) -> np.ndarray:
    """Same starters, same total, readable seating: the better players in the narrower slots
    (Jefferson at WR and the WR3 at FLEX, not the other way round). A second assignment over the
    chosen starters only; any eligible seating of them is legal and scores the same."""
    starters = assign[assign >= 0]
    if len(starters) < 2:
        return assign
    spec = np.array([1.0 / max(1, len(e)) for e in sets])      # IC-2: the slot's eligibility set
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
    sets = [s.elig for s in slot_list]                 # IC-2: eligibility is the slot's set
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
        elif not any(p.positions & e for e in set(sets)):
            unplayable.append(replace(given, playable=False, reason=no_slot_reason(p.position)))   # IC-2: not "can't play"
        else:
            pool.append(p)

    cols = np.array(open_cols, dtype=np.intp)
    vals = np.array([p.value for p in pool], dtype=float)
    tie = np.array([EPS + (0.0 if p.value_source == UNVALUED else EPS2) for p in pool], dtype=float)
    elig = np.array([[bool(p.positions & sets[j]) for j in open_cols] for p in pool],
                    dtype=bool).reshape(len(pool), len(open_cols))
    free_total, assign = _match(vals, elig, tie)
    locked_total = sum(p.value for p in locked.values() if p.value is not None and math.isfinite(p.value))

    chosen: dict[int, tuple[int, float | None]] = {}
    for k, i in enumerate(_canonical(assign, vals, elig, [sets[j] for j in open_cols])):
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
    # (league, roster) -> Sleeper's current `starters` array (ordered like roster_positions without
    # BN / IR / TAXI; "0" = empty): the slots of today's starters when a week has no Sleeper list yet
    starters: dict[tuple[str, int], list[str]] = field(default_factory=dict)
    # plan R-13: K / DEF projections (kd1.0). (league, week, unit) -> proj_points, team, report_status,
    # roster_status; unit = the kicker's gsis_id or the Sleeper defense id ('KC')
    kd_proj: dict[tuple[str, int, str], dict] = field(default_factory=dict)
    # (league, week, nflverse team) -> that team's kicker projection when exactly one K of the team is
    # projected that week: the value of a Sleeper kicker without an NFL id (unmapped rookie)
    k_team_proj: dict[tuple[str, int, str], dict] = field(default_factory=dict)
    # IC-2: team units (MFL's TMQB / TMPK). (league, week, unit position, nflverse team) -> proj_points, team,
    # report_status (the unit's QB / kicker); a unit's player row carries the team, never a gsis id
    unit_proj: dict[tuple[str, int, str, str], dict] = field(default_factory=dict)


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
        starter_rows = _frame(cur, """
            select league_id, roster_id, starter_ids from staging.stg_sleeper__rosters where league_id = any(%s)""", (ids,))
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
        kd_rows = _load_kd_projections(cur, season, ids)

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
        starters={(r["league_id"], int(r["roster_id"])): list(r["starter_ids"] or []) for r in starter_rows},
        **_kd_maps(kd_rows),
    )


def _load_kd_projections(cur: psycopg.Cursor, season: int, ids: list[str]) -> list[dict]:
    """K / DEF rows of ops.projections (plan R-13) with the unit's team and status for the week
    (``mart_kd_week``); none on a database that has not built that mart yet."""
    cur.execute("select to_regclass('analytics.mart_kd_week') is not null")
    if not cur.fetchone()[0]:
        return []
    return _frame(cur, """
        select p.league_id, p.week, p.position, p.gsis_id as unit_id, round(p.proj_points::numeric, 2) as proj_points,
               u.team, u.report_status, u.roster_status
        from ops.projections as p
        join analytics.mart_kd_week as u
          on u.position = p.position and u.unit_id = p.gsis_id and u.season = p.season and u.week = p.week
        where p.season = %s and p.league_id = any(%s) and p.position in ('K', 'DEF')""", (season, ids))


def _kd_maps(rows: list[dict]) -> dict[str, dict]:
    """``kd_proj`` and ``k_team_proj`` of ``LineupInputs`` from ``_load_kd_projections`` rows."""
    kd: dict[tuple[str, int, str], dict] = {}
    by_team: dict[tuple[str, int, str], list[dict]] = defaultdict(list)
    for r in rows:
        v = {"proj_points": _num(r["proj_points"]), "team": r["team"], "report_status": r["report_status"],
             "roster_status": r["roster_status"]}
        kd[(r["league_id"], int(r["week"]), r["unit_id"])] = v
        if r["position"] == "K" and r["team"]:
            by_team[(r["league_id"], int(r["week"]), r["team"])].append(v)
    return {"kd_proj": kd, "k_team_proj": {k: v[0] for k, v in by_team.items() if len(v) == 1}}


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
    kp = None
    if positions & SKILL:
        if pr is not None:
            base = replace(base, value=pr["proj_points"], value_source="proj_points")
            status = pr["report_status"]
    elif "K" in positions:
        # plan R-13: the kd1.0 projection first (by NFL id; a K without one: his NFL team's only
        # projected kicker that week), then the PPG fallbacks
        kp = inp.kd_proj.get((league_id, week, gsis)) if gsis else (inp.k_team_proj.get((league_id, week, team)) if team else None)
        if kp is not None and kp["proj_points"] is not None:
            base = replace(base, value=kp["proj_points"], value_source="proj_points")
            status, team = kp["report_status"], kp["team"] or team
        elif gsis and (league_id, gsis) in inp.k_ppg:
            base = replace(base, value=inp.k_ppg[(league_id, gsis)], value_source="season_ppg")
        elif (league_id, sid) in obs_ppg:
            base = replace(base, value=obs_ppg[(league_id, sid)], value_source="observed_ppg")
    elif positions & UNITS:
        # IC-2: a team unit (TMQB / TMPK) is valued from its team's line this week (anyleague prices it)
        up = inp.unit_proj.get((league_id, week, next(iter(positions & UNITS)), team)) if team else None
        if up is not None and up.get("proj_points") is not None:
            base = replace(base, value=up["proj_points"], value_source="proj_points")
    elif "DEF" in positions:
        kp = inp.kd_proj.get((league_id, week, sid))
        if kp is not None and kp["proj_points"] is not None:
            base = replace(base, value=kp["proj_points"], value_source="proj_points")
        elif (league_id, sid) in obs_ppg:
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
        if "K" in positions and base.value_source == "proj_points" and kp is not None:
            if kp["roster_status"] == "RES":
                return out("NFL injured reserve")
            if kp["report_status"] in ("Out", "Doubtful"):
                return out(kp["report_status"])
        return base if base.value is not None else unvalued
    if positions & UNITS:            # IC-2: a unit can't play only on a bye (above); no line this week: unvalued
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
        "n_unplayable": len(lu.cannot_play), "n_locked": sum(s.locked for s in lu.starts),   # IC-2: no-slot not counted
        "n_questionable": sum(p.status == "Questionable" for p in starters),
        "n_ppg_valued": sum(p.value_source in PPG_SOURCES for p in starters),
        "n_unvalued": sum(p.value_source == UNVALUED for p in starters),
    }
    return rows, total


def build(inp: LineupInputs, as_of: datetime | None = None, run_at: datetime | None = None) -> tuple[list[dict], list[dict], float]:
    """Solve every league x roster x projected week (and realised scored weeks). Returns
    (ops.lineups rows, ops.lineup_totals rows, seconds spent in the solver)."""
    as_of = as_of or clock.now()  # ---- INF-1: the league's now (run_at below stamps the run: real time)
    run_at = run_at or datetime.now(UTC)
    obs_ppg = _observed_ppg(inp)
    rows: list[dict] = []
    totals: list[dict] = []
    solve_s = 0.0
    for lg in inp.leagues:
        league_id, slots = lg["league_id"], list(lg["roster_positions"] or [])
        cur_by_roster = inp.current.get(league_id, {})
        # today's roster, with today's starters in the slots Sleeper's `starters` array implies: the lock
        # rule needs them in a week Sleeper has no list for yet (a Thursday game before the fetch)
        today: dict[int, list[dict]] = {}
        for roster_id in lg["roster_ids"]:
            slot_of = starter_slots(slots, inp.starters.get((league_id, roster_id)))
            today[roster_id] = [{**r, "is_starter": r["sleeper_player_id"] in slot_of, "slot": slot_of.get(r["sleeper_player_id"])}
                                for r in cur_by_roster.get(roster_id, [])]
        for week in inp.weeks.get(league_id, []):
            scored = week <= int(lg["last_scored_leg"])
            week_lists = inp.weekly.get((league_id, week))
            for roster_id in lg["roster_ids"]:
                cur_rows = {r["sleeper_player_id"]: r for r in today[roster_id]}
                # Sleeper's list for that week when there is one (first choice: it carries that week's
                # starters and slots); otherwise, and for a roster missing from it in an unscored week,
                # today's roster with today's starters (Sleeper's `starters` array)
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
    record_after_lineups(conn, inp, rows, totals, as_of)       # ---- V-1 (Wave I-G): the decision record, never fatal
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


# ---- V-1 (Wave I-G): the decision record — what the app recommended, frozen before the week's first kickoff
# ``lineups()`` re-solves and overwrites ``ops.lineups`` every run, so nothing kept what the app said before kickoff.
# ``ops.lineup_record`` keeps it, under the ``ops.projections`` freeze rule (plan B5; docs/METRICS.md § "The decision
# record"): per league x week,
#   * the week has not kicked off -> ``write``: every build replaces the rows (the last build before kickoff wins),
#     labelled ``kickoff``; only the NEXT week to kick off is written (a later week is replaced before it can count);
#   * kicked off, rows stored -> ``keep``: never rewritten or deleted;
#   * kicked off, nothing stored (2026 weeks 1-4: played before this record existed; a league added mid-season) ->
#     ``reconstruct`` once from the frozen ``ops.projections`` rows (the as-of inputs), solved as of one second before
#     the first kickoff (no locks), labelled ``reconstructed``. Caveat: a reconstructed week reads the week's final
#     injury report (``mart_player_week_features``), not the one the morning build saw.
# One row per player of the proposed lineup (starters, empty slots, bench, unplayable) with the lineup total, and on
# a starter's row the decision cards' call (app/lib/cards.py ``decisions``: the three smallest-margin valued starters
# a bench player could replace, with that player and P(starter outscores him), ``league_lab.decisions``).
RECORD_COLUMNS = ["run_at", "as_of", "first_kickoff_at", "record_source", "model_version", "pricing", "league_id", "season",
                  "week", "roster_id", "role", "slot", "slot_type", "slot_order", "bench_rank", "sleeper_player_id",
                  "gsis_id", "player_name", "position", "value", "value_source", "margin", "report_status", "reason",
                  "lineup_value", "call_rank", "alt_sleeper_player_id", "alt_gsis_id", "alt_player_name", "alt_value",
                  "p_win", "is_coin_flip"]
RECORD_DDL = """create table if not exists ops.lineup_record (
        run_at timestamptz, as_of timestamptz, first_kickoff_at timestamptz, record_source text, model_version text,
        pricing text, league_id text, season integer, week integer, roster_id integer, role text, slot text,
        slot_type text, slot_order integer, bench_rank integer, sleeper_player_id text, gsis_id text, player_name text,
        position text, value double precision, value_source text, margin double precision, report_status text,
        reason text, lineup_value double precision, call_rank integer, alt_sleeper_player_id text, alt_gsis_id text,
        alt_player_name text, alt_value double precision, p_win double precision, is_coin_flip boolean);
        create index if not exists lineup_record_idx on ops.lineup_record (league_id, season, week, roster_id)"""
DDL["ops.lineup_record"] = RECORD_DDL      # `league-lab db migrate` creates it (a fresh nightly database restores into it)
RECORD_SOURCES = ("kickoff", "reconstructed")
N_CALLS = 3                  # the cards' closest calls per roster-week (cards.decisions' n)
CALL_TOL = 0.011             # = cards.TOL: values and margins are stored to the cent
CLOSE_PWIN, COIN_FLIP_MARGIN = 0.55, 1.0    # = cards.CLOSE_PWIN / cards.COIN_FLIP: the card's "coin flip"
QUANTILES = ("p10", "p25", "p50", "p75", "p90")


def first_kickoffs(games: Mapping[int, Mapping[str, datetime | None]]) -> dict[int, datetime]:
    """week -> the week's first kickoff (``LineupInputs.games``); a week without a kickoff time is left out."""
    out = {}
    for week, teams in games.items():
        ks = [k for k in teams.values() if k is not None]
        if ks:
            out[int(week)] = min(ks)
    return out


def record_plan(weeks: Mapping[str, Iterable[int]], stored: Iterable[tuple[str, int]], kickoffs: Mapping[int, datetime],
                now: datetime) -> dict[tuple[str, int], str]:
    """What this build does to each league-week of the record: ``write`` (the next week to kick off), ``keep`` (kicked
    off, stored), ``reconstruct`` (kicked off, nothing stored). A week without a known kickoff, or a later unstarted
    week, is left alone (absent from the answer)."""
    have = {(str(lg), int(w)) for lg, w in stored}
    plan: dict[tuple[str, int], str] = {}
    for league_id, ws in weeks.items():
        ws = sorted({int(w) for w in ws if int(w) in kickoffs})
        started = [w for w in ws if kickoffs[w] <= now]
        ahead = [w for w in ws if kickoffs[w] > now]
        for w in started:
            plan[(league_id, w)] = "keep" if (league_id, w) in have else "reconstruct"
        if ahead:
            plan[(league_id, ahead[0])] = "write"
    return plan


def _elig(position: str | None, slot_type: str | None) -> bool:
    e = slot_eligibility(slot_type)
    return bool(position) and e is not None and position in e


def _alternative(s: dict, bench: list[dict]) -> dict | None:
    """cards.alternative on record rows: the bench player who comes in when starter ``s`` sits (value = starter value -
    margin; the slot's best eligible bench player when that matches, else the one with that value), or None."""
    target = float(s["value"]) - float(s["margin"])
    valued = [b for b in bench if b["value"] is not None]
    elig = sorted((b for b in valued if _elig(b["position"], s["slot_type"])), key=lambda b: (-b["value"], b["bench_rank"]))
    best = elig[0] if elig else None
    if best is not None and abs(best["value"] - target) <= CALL_TOL:
        return best
    if abs(target) <= CALL_TOL:
        return None
    entering = [b for b in valued if abs(b["value"] - target) <= CALL_TOL]
    if entering:
        return sorted(entering, key=lambda b: (not _elig(b["position"], s["slot_type"]), b["bench_rank"]))[0]
    return best


def close_calls(rows: list[dict], weakest_slot: str | None, quantiles: Mapping[str, dict] | None = None,
                n: int = N_CALLS) -> list[tuple[dict, dict, float | None]]:
    """The decision cards' closest calls for one roster-week of record rows (no locks before kickoff): the n valued
    starters with the smallest margins (weakest slot first on a tie, then value, slot order) someone on the bench
    could replace, each with that bench player and P(starter outscores him) (``decisions.win_probability`` on the
    frozen quantiles; only for two QB-TE projections, like the card). ``quantiles``: gsis -> p10..p90, team, opponent."""
    from . import decisions as D

    starters = [r for r in rows if r["role"] == "starter" and r["margin"] is not None and not r.get("is_locked")
                and r["value_source"] != UNVALUED and r["value"] is not None]
    starters.sort(key=lambda r: (r["margin"], r["slot"] != weakest_slot, r["value"], r["slot_order"]))
    bench = [r for r in rows if r["role"] == "bench" and not r.get("is_locked")]
    out = []
    for s in starters:
        if len(out) >= n:
            break
        alt = _alternative(s, bench)
        if alt is None:
            continue
        p = None
        if (quantiles is not None and s["value_source"] == alt["value_source"] == "proj_points"
                and s["position"] in SKILL and alt["position"] in SKILL):
            qa, qb = quantiles.get(s["gsis_id"]), quantiles.get(alt["gsis_id"])
            if qa is not None and qb is not None:
                p = D.win_probability({**qa, "position": s["position"]}, {**qb, "position": alt["position"]})
        out.append((s, alt, p))
    return out


def is_coin_flip(p_win: float | None, margin: float | None) -> bool:
    """The card's own rule (cards.is_coin_flip): under 55% when the odds exist, else under a point apart."""
    return (p_win < CLOSE_PWIN) if p_win is not None else float(margin or 0.0) < COIN_FLIP_MARGIN


def record_rows(rows: list[dict], totals: list[dict], meta: Mapping[tuple[str, int], dict],
                quantiles: Mapping[tuple[str, int], Mapping[str, dict]], source: str, as_of: datetime) -> list[dict]:
    """``ops.lineup_record`` rows from a build's proposed (not realised) rows of the league-weeks in ``meta``
    ((league, week) -> first_kickoff_at, model_version, pricing)."""
    by_rw: dict[tuple[str, int, int], list[dict]] = defaultdict(list)
    for r in rows:
        if not r["is_realised"] and (r["league_id"], int(r["week"])) in meta:
            by_rw[(r["league_id"], int(r["week"]), int(r["roster_id"]))].append(r)
    tot = {(t["league_id"], int(t["week"]), int(t["roster_id"])): t for t in totals
           if not t["is_realised"] and (t["league_id"], int(t["week"])) in meta}
    out = []
    for key, rw in sorted(by_rw.items()):
        league_id, week, _ = key
        t = tot.get(key, {})
        m = meta[(league_id, week)]
        calls = {}
        for k, (s, alt, p) in enumerate(close_calls(rw, t.get("weakest_slot"), quantiles.get((league_id, week))), 1):
            calls[id(s)] = {"call_rank": k, "alt_sleeper_player_id": alt["sleeper_player_id"], "alt_gsis_id": alt["gsis_id"],
                            "alt_player_name": alt["player_name"], "alt_value": alt["value"],
                            "p_win": None if p is None else round(float(p), 4), "is_coin_flip": is_coin_flip(p, s["margin"])}
        for r in rw:
            out.append({c: r.get(c) for c in RECORD_COLUMNS} | {
                "as_of": as_of, "first_kickoff_at": m.get("first_kickoff_at"), "record_source": source,
                "model_version": m.get("model_version") or r.get("model_version"), "pricing": m.get("pricing") or "flat",
                "lineup_value": t.get("lineup_value"), **calls.get(id(r), {})})
    return out


def _record_meta(cur: psycopg.Cursor, season: int, keys: list[tuple[str, int]], kickoffs: Mapping[int, datetime]) -> dict:
    """(league, week) -> first_kickoff_at, model_version (the league-week's ops.projections versions), pricing (M4's
    column when it exists: ``coalesce(max(pricing), 'flat')``; NULL / no column = flat, every row before Wave I-G)."""
    cur.execute("""select 1 from information_schema.columns
                   where table_schema = 'ops' and table_name = 'projections' and column_name = 'pricing'""")
    pricing = "coalesce(max(pricing), 'flat')" if cur.fetchone() else "'flat'"
    cur.execute(f"""select league_id, week, string_agg(distinct model_version, ',' order by model_version) as mv, {pricing} as pricing
                    from ops.projections where season = %s and (league_id, week) in (select * from unnest(%s::text[], %s::int[]))
                    group by 1, 2""", (season, [k[0] for k in keys], [k[1] for k in keys]))
    got = {(lg, int(w)): {"model_version": mv, "pricing": pr} for lg, w, mv, pr in cur.fetchall()}
    return {k: {"first_kickoff_at": kickoffs.get(k[1]), **got.get(k, {"model_version": None, "pricing": "flat"})} for k in keys}


def _record_quantiles(cur: psycopg.Cursor, season: int, keys: list[tuple[str, int]]) -> dict:
    """(league, week) -> gsis -> the frozen p10..p90, team and opponent (the card's win probability inputs)."""
    cur.execute("""select p.league_id, p.week, p.gsis_id, p.p10, p.p25, p.p50, p.p75, p.p90, f.team,
                          case when g.home_team = f.team then g.away_team when g.away_team = f.team then g.home_team end as opponent
                   from ops.projections as p
                   left join analytics.mart_player_week_features as f using (gsis_id, season, week)
                   left join analytics.dim_game as g
                     on g.season = p.season and g.week = p.week and g.season_type = 'REG' and f.team in (g.home_team, g.away_team)
                   where p.season = %s and p.position in ('QB', 'RB', 'WR', 'TE')
                     and (p.league_id, p.week) in (select * from unnest(%s::text[], %s::int[]))""",
                (season, [k[0] for k in keys], [k[1] for k in keys]))
    out: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
    for lg, w, g, *vals in cur.fetchall():
        q = dict(zip([*QUANTILES, "team", "opponent"], vals, strict=True))
        out[(lg, int(w))][g] = {k: (_num(v) if k in QUANTILES else v) for k, v in q.items()}
    return out


@dataclass
class RecordRun:
    plan: dict[tuple[str, int], str]
    rows: int
    written: list[tuple[str, int]]
    reconstructed: list[tuple[str, int]]


def write_record(conn: psycopg.Connection, inp: LineupInputs, rows: list[dict] | None = None, totals: list[dict] | None = None,
                 as_of: datetime | None = None) -> RecordRun:
    """Write ``ops.lineup_record`` for one build under the freeze rule (``record_plan``), in one transaction. ``rows`` /
    ``totals``: this build's ``build()`` output at ``as_of`` (the ``write`` weeks are taken from it; None = solve them
    here); ``reconstruct`` weeks are solved here, as of one second before their first kickoff."""
    as_of = as_of or datetime.now(UTC)
    kickoffs = first_kickoffs(inp.games)
    with conn.cursor() as cur:
        cur.execute(RECORD_DDL)
        cur.execute("select distinct league_id, week from ops.lineup_record where season = %s", (inp.season,))
        stored = [(lg, int(w)) for lg, w in cur.fetchall()]
        plan = record_plan(inp.weeks, stored, kickoffs, as_of)
        write = sorted(k for k, a in plan.items() if a == "write")
        rebuild = sorted(k for k, a in plan.items() if a == "reconstruct")
        if not write and not rebuild:
            conn.commit()
            return RecordRun(plan, 0, [], [])
        meta = _record_meta(cur, inp.season, write + rebuild, kickoffs)
        quant = _record_quantiles(cur, inp.season, write + rebuild)
        out: list[dict] = []
        if write:
            if rows is None or totals is None:
                rows, totals, _ = build(replace(inp, weeks={lg: [w for (g, w) in write if g == lg] for lg in inp.weeks}), as_of=as_of)
            out += record_rows(rows, totals, {k: meta[k] for k in write}, quant, "kickoff", as_of)
        for league_id, week in rebuild:
            just_before = kickoffs[week] - timedelta(seconds=1)
            r_rows, r_tot, _ = build(replace(inp, weeks={league_id: [week]}), as_of=just_before, run_at=as_of)
            out += record_rows(r_rows, r_tot, {(league_id, week): meta[(league_id, week)]}, quant, "reconstructed", just_before)
        for r in out:
            r["run_at"] = as_of
        cur.execute("delete from ops.lineup_record where season = %s and (league_id, week) in (select * from unnest(%s::text[], %s::int[]))",
                    (inp.season, [k[0] for k in write], [k[1] for k in write]))
        with cur.copy(f"copy ops.lineup_record ({', '.join(RECORD_COLUMNS)}) from stdin") as cp:
            for d in out:
                cp.write_row([d.get(c) for c in RECORD_COLUMNS])
    conn.commit()
    log.info("decision record for %s: %s rows (written: %s; reconstructed: %s; kept: %s)", inp.season, len(out),
             write or "none", rebuild or "none", sorted(k for k, a in plan.items() if a == "keep") or "none")
    return RecordRun(plan, len(out), write, rebuild)


def record_after_lineups(conn: psycopg.Connection, inp: LineupInputs, rows: list[dict], totals: list[dict],
                         as_of: datetime) -> RecordRun | None:
    """Called by ``lineups()`` after its own write: a failure here is logged, never fatal (the lineups are written;
    ``league-lab validate`` writes the record again)."""
    try:
        return write_record(conn, inp, rows, totals, as_of)
    except Exception:
        conn.rollback()
        log.exception("decision record failed (lineups were written); run `league-lab validate`")
        return None


def run_record(season: int | None = None, as_of: datetime | None = None) -> RecordRun | None:
    """``league-lab validate``'s writer: load the inputs and write the record without touching ``ops.lineups``."""
    from .config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        if season is None:
            with conn.cursor() as cur:
                cur.execute("select max(season) from ops.projections")
                season = cur.fetchone()[0]
        if season is None:
            log.warning("record: ops.projections is empty (run `league-lab project` first)")
            return None
        return write_record(conn, load_inputs(conn, int(season)), as_of=as_of)
# ---- end V-1


# ---- V-2 (Wave I-H): MyFantasyLeague leagues in the decision record. An MFL league has no ``ops.lineups`` rows (the
# nightly does not price it), so its record is the ON-DEMAND lineup (``anyleague._solve_roster``: the frame My Week
# serves), frozen under the same rule (``record_plan``): the next week to kick off is written by every run before its
# first kickoff (``kickoff``) from the league's current rosters; a played week with no rows is rebuilt once
# (``reconstructed``) from the rosters MFL's ``weeklyResults`` list for it (every franchise's starters and bench),
# priced on that week's frozen projection lines in the league's scoring, as of one second before its first
# kickoff. A week MFL has not scored yet is left until it has. Rows: ``ops.lineup_record`` with ``league_id =
# 'mfl:<id>'``; the calls' odds from the on-demand ranges. Written by ``league-lab validate`` for the keys in
# ``LEAGUE_LAB_RECORD_MFL`` (comma list) or ``--mfl``; the grade is ``validation.mfl_weekly`` + ``mfl_inputs``.
# The writer itself is ``league_lab.record_mfl`` (it reaches anyleague / MFL: kept out of this module, which the console
# imports, so scripts/hosted_relations.py does not count the on-demand tables as the console's).
MFL_RECORD_ENV = "LEAGUE_LAB_RECORD_MFL"
# Sleeper's projections as a lineup (league_lab.record_run writes it; `db migrate` creates it)
MARKET_DDL = """create table if not exists ops.decision_market (league_id text, season integer, week integer,
        roster_id integer, slot text, sleeper_player_id text, gsis_id text, player_name text, position text,
        market_value double precision, value_source text, fetched_at timestamptz, pricing text, written_at timestamptz);
        create index if not exists decision_market_idx on ops.decision_market (league_id, season, week, roster_id)"""
DDL["ops.decision_market"] = MARKET_DDL


def mfl_record_keys(raw: str | None = None) -> list[str]:
    """The MFL leagues the record is kept for: ``LEAGUE_LAB_RECORD_MFL`` (comma list of ``mfl:<id>``)."""
    import os
    text = os.environ.get(MFL_RECORD_ENV, "") if raw is None else raw
    return sorted({k.strip() for k in text.split(",") if k.strip().startswith("mfl:")})


# ---- end V-2
