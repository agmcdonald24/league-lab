"""Waiver engine (plan B3, Iteration 9b): every legal add/drop for every roster, valued by the B1 solver.

What it does
------------
For every roster of every current league, for the **decision week** (the first week with a game
that has not kicked off at ``as_of``) and a **horizon** of that week and the next three:

* the **moves**: every free agent on an active NFL roster (``mart_player_availability``:
  ``is_free_agent``, ``roster_status = 'ACT'``, injury not Out / IR, a position the league starts)
  x every droppable player (on the roster, not in the IR slot or on the taxi squad, not locked:
  his game this week has not kicked off). When the roster has an open spot (fewer active players
  than starting + bench slots), "add without a drop" is a legal move too; an over-full roster has
  no legal single move.
* the **value of a move**: the B1 lineup solver re-run on the roster after the move minus before,
  week by week (``lineup.solve``'s matching on the same players and values ``ops.lineups`` holds for
  that roster-week; locked players stay locked). **Weekly gain** = the decision week; **horizon
  gain** = the sum over the horizon's weeks (byes, Out weeks and the drop's own future starts all
  count: the drop's contribution to the next four lineups is what the move gives up).
  The free agent is valued exactly as B1 would value him on the roster (``lineup._proposed_player``):
  projection v2 ``proj_points`` in this league's scoring, K and DEF at their kd1.0 projection (plan
  R-13; season / observed PPG where none exists), unplayable on a bye / Out / Doubtful / NFL IR /
  once his game has kicked off. Free-agent team defenses come from ``mart_player_availability``'s DEF
  rows (Sleeper id 'KC', no gsis id) for the leagues that start a DEF.
* the **lists**: *start now* (weekly gain > 0), *cover* (weekly gain <= 0, horizon gain > 0: a
  bye-week or injury cover). A move that gains nothing in either is not stored; a roster with no
  such move gets one ``list_kind = 'nothing'`` row ("nothing beats what you have"). Moves are ranked
  by horizon gain, then weekly gain; per add the best drop is flagged (ties: the drop with the
  fewest projected points over the horizon, i.e. the least useful player). A free agent with no
  game this season is flagged ``is_no_evidence`` ("no evidence yet": his projection rests on
  last season and priors only). *Upside stash* (plan R-12, from the R-10 role alerts): its own table,
  ``ops.waiver_upside``, written right after the moves (the section at the end of this module).

Pruning (why the sweep is fast, and why it loses nothing)
---------------------------------------------------------
A move's gain in a week can never exceed the add's gain on the full roster (removing a player never
raises a lineup's best total), and the add's gain is exactly

    gain(add) = max(0, value(add) - bar(positions of the add))
    bar = lineup total - max over the open slots s he can play of (best total with slot s removed)

i.e. the add enters only if he is worth more than the cheapest way to free a slot he can play: the
starter he would push out after the lineup reshuffles, 0 when such a slot is empty. The bar depends
on the roster-week and the position set only, so it costs a handful of re-solves per roster-week.
A free agent whose value is at or below the bar in every week of the horizon cannot improve any
week's lineup with any drop, so no move with him can reach the lists: he is pruned. Only the
survivors are paired with every legal drop. ``roster_moves_unpruned`` evaluates every free agent x
every drop x every week with a plain ``solve()`` from scratch; ``league-lab waivers --verify`` and the
tests compare the two.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import psycopg

from . import league_status as LS  # ---- IS-2: the one "can he play" question
from .lineup import (
    EPS,
    EPS2,
    SLOT_ELIGIBILITY,
    UNVALUED,
    Lineup,
    Player,
    _match,
    _observed_ppg,
    _proposed_player,
    _r2,
    load_inputs,
    parse_slots,
    solve,
)

log = logging.getLogger(__name__)

HORIZON = 4          # the decision week and the next three
BAR_TOL = 1e-6       # an add worth no more than the bar (+ float noise) cannot gain
NOT_ROSTER_SPOTS = frozenset({"IR", "TAXI"})


# ------------------------------------------------------------------------------ one roster-week, prepared
@dataclass
class _Week:
    """One roster-week solved once by B1's ``solve()``; what-ifs re-run the same matching
    (``lineup._match``) on the free part only: the locked starters keep their slots and value."""
    lineup: Lineup
    total: float
    locked_total: float
    open_types: list[str]
    pool: list[Player]
    index: dict[str, int]
    vals: np.ndarray
    tie: np.ndarray
    elig: np.ndarray

    @property
    def starters(self) -> set[str]:
        return set(self.lineup.starter_ids)


def _norm(p: Player) -> Player | None:
    """A free agent as solve() would carry him: None if he cannot play; no value -> unvalued at 0."""
    if not p.playable:
        return None
    if p.value is None or not math.isfinite(p.value) or p.value_source == UNVALUED:
        return replace(p, value=0.0, value_source=UNVALUED, reason=p.reason or "no value yet")
    return p


def _elig_row(p: Player, types: Sequence[str]) -> np.ndarray:
    return np.array([bool(p.positions & SLOT_ELIGIBILITY[t]) for t in types], dtype=bool)


def _tie(p: Player) -> float:
    return EPS + (0.0 if p.value_source == UNVALUED else EPS2)


def prepare(players: Sequence[Player], slots: Sequence[str]) -> _Week:
    lu = solve(players, slots, margins=False)
    open_types = [s.type for s in parse_slots(slots)[0]]
    locked_total = 0.0
    for s in lu.starts:
        if s.locked:
            open_types.remove(s.slot.type)
            if s.player.value is not None and math.isfinite(s.player.value):
                locked_total += s.player.value
    pool = [s.player for s in lu.starts if s.player is not None and not s.locked] + list(lu.bench)
    vals = np.array([p.value for p in pool], dtype=float)
    tie = np.array([_tie(p) for p in pool], dtype=float)
    elig = np.array([_elig_row(p, open_types) for p in pool], dtype=bool).reshape(len(pool), len(open_types))
    return _Week(lu, lu.total, locked_total, open_types, pool, {p.id: i for i, p in enumerate(pool)}, vals, tie, elig)


def _what_if(w: _Week, add: Player | None, drop: str | None) -> tuple[float, set[str]]:
    """Best total of the roster-week with ``drop`` removed and ``add`` (normalised, may be None) added,
    and the ids of the free starters of that lineup."""
    keep = np.ones(len(w.pool), dtype=bool)
    if drop is not None and drop in w.index:
        keep[w.index[drop]] = False
    vals, tie, elig = w.vals[keep], w.tie[keep], w.elig[keep]
    ids = [p.id for p, k in zip(w.pool, keep, strict=True) if k]
    if add is not None:
        row = _elig_row(add, w.open_types)
        if row.any():
            vals = np.append(vals, add.value)
            tie = np.append(tie, _tie(add))
            elig = np.vstack([elig, row[None, :]])
            ids.append(add.id)
    total, assign = _match(vals, elig, tie)
    return w.locked_total + total, {ids[i] for i in assign if i >= 0}


def entry_bar(w: _Week, positions: frozenset[str]) -> float | None:
    """The value a player with these positions must beat to raise this lineup's total: the lineup
    total minus the best total with one open slot he can play removed (0 when such a slot is empty
    or can be emptied for free). None: no open slot he can play (locked or not in this league)."""
    free_total, _ = _match(w.vals, w.elig, w.tie)
    best = None
    for t in dict.fromkeys(w.open_types):
        if not positions & SLOT_ELIGIBILITY[t]:
            continue
        cols = [j for j, u in enumerate(w.open_types) if u == t][1:] + [j for j, u in enumerate(w.open_types) if u != t]
        rest, _ = _match(w.vals, w.elig[:, sorted(cols)], w.tie)
        best = rest if best is None else max(best, rest)
    return None if best is None else max(0.0, free_total - best)


# ------------------------------------------------------------------------------ one roster
@dataclass(frozen=True)
class MoveResult:
    add: str
    drop: str | None
    week_gains: tuple[float, ...]    # per horizon week: lineup after the move minus before
    add_alone: tuple[float, ...]     # per week: the add's gain with nobody dropped (the pruning bound)
    drop_loss: tuple[float, ...]     # per week: what dropping him alone costs the lineup
    lineup_before: float             # decision week
    lineup_after: float
    add_slot: str | None             # the decision week's slot label he starts in (None: bench / cannot play)
    add_slot_type: str | None
    displaced: str | None            # the starter who leaves the decision week's lineup (the drop if he started)

    @property
    def weekly_gain(self) -> float:
        return self.week_gains[0]

    @property
    def horizon_gain(self) -> float:
        return sum(self.week_gains)

    def key(self) -> tuple:
        return (self.add, self.drop or "", round(self.weekly_gain, 2), round(self.horizon_gain, 2))


def _gains(x: float) -> bool:
    return round(x, 2) > 0


def _seat(before: Lineup, after: Lineup, add: str, drop: str | None) -> tuple[str | None, str | None, str | None]:
    """(slot label the add takes, its type, the displaced starter) in the decision week."""
    slot = next((s for s in after.starts if s.player is not None and s.player.id == add), None)
    before_ids = [s.player.id for s in before.starts if s.player is not None]
    if drop is not None and drop in before_ids:
        displaced = drop
    else:
        after_ids = set(after.starter_ids)
        out = [s for s in before.starts if s.player is not None and s.player.id not in after_ids and s.player.id != drop]
        displaced = min(out, key=lambda s: (s.value if s.value is not None else 0.0)).player.id if out else None
    return (slot.slot.label if slot else None), (slot.slot.type if slot else None), displaced


def _unvalued(p: Player) -> bool:
    return p.value is None or not math.isfinite(p.value) or p.value_source == UNVALUED


def guard(slots: Sequence[str], weeks: Sequence[Sequence[Player]], droppable: Sequence[str]) -> tuple[list[list[Player]], list[str]]:
    """Unknown is not zero. B1 carries a player with no value yet at 0 (a K / DEF Sleeper has not
    scored in this league, a player without a projection), so a move measured against him would
    count his real value as nothing: (1) a starter with no value yet keeps his slot (locked there),
    so no add is credited with replacing him; (2) a player with no value yet in any week of the
    horizon is not a drop candidate (what dropping him costs cannot be measured)."""
    out, unknown = [], set()
    for ps in weeks:
        lu = solve(ps, slots, margins=False)
        shield = {s.player.id: s.slot.type for s in lu.starts
                  if s.player is not None and not s.locked and s.player.value_source == UNVALUED}
        unknown |= {p.id for p in ps if (p.playable or p.locked_slot is not None) and _unvalued(p)}
        out.append([replace(p, locked_slot=shield[p.id]) if p.id in shield else p for p in ps])
    return out, [d for d in droppable if d not in unknown]


def roster_moves(slots: Sequence[str], weeks: Sequence[Sequence[Player]], adds: Mapping[str, Sequence[Player | None]],
                 droppable: Sequence[str], open_spot: bool, *, stats: dict | None = None) -> list[MoveResult]:
    """Every move (add x legal drop) that gains this week or over the horizon, for one roster.

    ``weeks[h]`` = the roster's players in horizon week h (h = 0 is the decision week), as B1 carried
    them; ``adds[id][h]`` = the free agent as B1 would carry him in week h (None = not projected /
    not eligible); ``droppable`` = ids that may be dropped; ``open_spot`` = the roster may add without
    a drop. Pruned (see the module docstring); ``roster_moves_unpruned`` is the yardstick."""
    weeks, droppable = guard(slots, weeks, droppable)
    preps = [prepare(ps, slots) for ps in weeks]
    before = [w.total for w in preps]
    drops: list[str | None] = ([None] if open_spot else []) + list(droppable)
    if not drops:
        return []
    # what each drop alone costs, per week (a bench player who never starts costs nothing)
    drop_only: list[dict[str | None, float]] = []
    for w in preps:
        d_only: dict[str | None, float] = {None: w.total}
        for d in droppable:
            d_only[d] = _what_if(w, None, d)[0] if d in w.starters else w.total
        drop_only.append(d_only)
    # the bar per week and position set, then the survivors
    bars: list[dict[frozenset, float | None]] = [{} for _ in preps]
    normed = {a: [(_norm(p) if p is not None else None) for p in seq] for a, seq in adds.items()}
    survivors = []
    for a, seq in normed.items():
        for h, p in enumerate(seq[:len(preps)]):
            if p is None or p.value <= 0:
                continue                                   # cannot play, or worth nothing: gains nothing
            if p.positions not in bars[h]:
                bars[h][p.positions] = entry_bar(preps[h], p.positions)
            bar = bars[h][p.positions]
            if bar is not None and p.value > bar + BAR_TOL:
                survivors.append(a)
                break
    if stats is not None:
        stats["adds"] = stats.get("adds", 0) + len(adds)
        stats["survivors"] = stats.get("survivors", 0) + len(survivors)

    out: list[MoveResult] = []
    for a in survivors:
        seq = normed[a]
        after: list[dict[str | None, float]] = []
        alone: list[float] = []
        for h, w in enumerate(preps):
            p = seq[h] if h < len(seq) else None
            if p is None or not _elig_row(p, w.open_types).any():
                after.append(dict(drop_only[h]))
                alone.append(0.0)
                continue
            t_add, starters = _what_if(w, p, None)
            row = {}
            for d in drops:
                # a drop who does not start in the best lineup with the add changes nothing
                row[d] = t_add if d is None or d not in starters else _what_if(w, p, d)[0]
            after.append(row)
            alone.append(t_add - w.total)
        for d in drops:
            gains = tuple(after[h][d] - before[h] for h in range(len(preps)))
            if not (_gains(gains[0]) or _gains(sum(gains))):
                continue
            out.append(MoveResult(a, d, gains, tuple(alone), tuple(before[h] - drop_only[h][d] for h in range(len(preps))),
                                  before[0], after[0][d], None, None, None))
    if stats is not None:
        stats["moves"] = stats.get("moves", 0) + len(out)
    # the decision week's seating, for the stored moves only (B1's solve(), so the slot labels are
    # the ones mart_lineup_recommendation shows); a drop who does not start with the add reuses the
    # lineup with the add alone (an optimal lineup of both rosters)
    base = preps[0].lineup
    full0 = list(weeks[0])
    cache: dict[str, Lineup] = {}
    seated = []
    for m in out:
        p = normed[m.add][0] if normed[m.add] else None
        extra = [p] if p is not None else []
        if m.add not in cache:
            cache[m.add] = solve(full0 + extra, slots, margins=False) if extra else base
        lu = cache[m.add]
        if m.drop is not None and m.drop in lu.starter_ids:
            lu = solve([q for q in full0 if q.id != m.drop] + extra, slots, margins=False)
        slot, stype, displaced = _seat(base, lu, m.add, m.drop)
        seated.append(replace(m, add_slot=slot, add_slot_type=stype, displaced=displaced))
    return seated


def roster_moves_unpruned(slots: Sequence[str], weeks: Sequence[Sequence[Player]], adds: Mapping[str, Sequence[Player | None]],
                          droppable: Sequence[str], open_spot: bool) -> list[MoveResult]:
    """The yardstick for ``roster_moves``: every add x every legal drop x every week, each lineup
    re-solved from scratch with ``solve()`` on the full player list. No bar, no shortcut."""
    weeks, droppable = guard(slots, weeks, droppable)
    before = [solve(ps, slots, margins=False) for ps in weeks]
    drops: list[str | None] = ([None] if open_spot else []) + list(droppable)
    loss = {d: tuple(b.total - solve([q for q in ps if q.id != d], slots, margins=False).total
                     for ps, b in zip(weeks, before, strict=True)) for d in drops}
    out = []
    for a, seq in adds.items():
        extra = [[seq[h]] if h < len(seq) and seq[h] is not None else [] for h in range(len(weeks))]
        alone = tuple(solve(list(ps) + extra[h], slots, margins=False).total - before[h].total for h, ps in enumerate(weeks))
        for d in drops:
            lus = [solve([q for q in ps if q.id != d] + extra[h], slots, margins=False) for h, ps in enumerate(weeks)]
            gains = tuple(lu.total - b.total for lu, b in zip(lus, before, strict=True))
            if not (_gains(gains[0]) or _gains(sum(gains))):
                continue
            slot, stype, displaced = _seat(before[0], lus[0], a, d)
            out.append(MoveResult(a, d, gains, alone, loss[d], before[0].total, lus[0].total, slot, stype, displaced))
    return out


# ------------------------------------------------------------------------------ IF-1: the drop's cost, in pieces
# (Wave I-F, the decision-quality review § "value the bench before prescribing drops"). B3 named the drop with the
# fewest projected points among equally good moves, so a bench WR who does not start in the next four weeks was a free
# drop for every claim ("he sits anyway"). A drop now costs the most of five pieces, each in points of this league's
# scoring (never their sum — they overlap):
#   lineup_loss   his starts over the horizon the move gives up WITH the add on the roster (add's gain alone − the
#                 move's gain): Carlson for McPherson gives up nothing — Carlson takes the K slot;
#   depth_lost    Σ over the horizon weeks he sits: max(0, his projection − the best free agent's at his position) × the
#                 chance a starter he can cover misses that week (1 − (1 − ABSENCE_RATE[pos])^starters at his position);
#   future_starts Σ over the weeks after the horizon: what the lineup (with the add) loses without him beyond the best
#                 free agent at his position (his season points over the weeks left: a bye the wire covers costs 0);
#   season_value  trades.price_by_player's rule: max(0, his rest-of-season points − the best free agent's at his
#                 position) — the replacement baseline (a 1-QB league's wire holds starting QBs, a superflex one does
#                 not; a team unit / DEF against the best free unit);
#   upside        a role scenario's extra points over the horizon (ops.player_scenarios), when he has one.
# net gain = the move's lineup gain − (cost − lineup_loss): the roster value the lineup numbers do not already count.
# Per add the best drop is the cheapest (equal costs: the starter the add replaces — "Carlson replaces McPherson at
# K" —, then the fewest rest-of-season points). A move is worthwhile when its net gain is ≥ WORTH_WEEK this week or
# ≥ WORTH_HORIZON over the horizon.
ABSENCE_RATE = {"QB": 0.06, "RB": 0.12, "WR": 0.10, "TE": 0.09, "K": 0.02, "DEF": 0.0}  # a starter's weekly miss rate
WORTH_WEEK, WORTH_HORIZON = 1.0, 3.0
COST_PIECES = ("lineup_loss", "season_value", "future_starts", "depth_lost", "upside")   # the tie order of `piece`
COST_COLUMNS = ["drop_cost", "drop_cost_piece", "drop_lineup_loss", "drop_depth_lost", "drop_future_starts",
                "drop_future_start_weeks", "drop_season_value", "drop_season_points", "drop_replacement_points",
                "drop_upside", "drop_is_incumbent", "net_weekly_gain", "net_horizon_gain", "is_worthwhile"]


@dataclass(frozen=True)
class DropCost:
    """What dropping one player costs a move (see the block comment). A piece that could not be measured is None
    (unknown, not 0): the cost is the most of the pieces that were."""
    lineup_loss: float = 0.0
    depth_lost: float | None = None
    future_starts: float | None = None
    future_start_weeks: int | None = None
    season_value: float | None = None
    upside: float | None = None

    @property
    def cost(self) -> float:
        return max(float(v) for v in (self.lineup_loss, self.depth_lost, self.future_starts, self.season_value,
                                      self.upside, 0.0) if v is not None)

    @property
    def piece(self) -> str | None:
        """The piece that sets the cost (None: every piece is 0)."""
        c = self.cost
        if round(c, 2) <= 0:
            return None
        return next(k for k in COST_PIECES if getattr(self, k) is not None and round(float(getattr(self, k)), 2) == round(c, 2))

    def as_dict(self) -> dict:
        return {"lineup_loss": _r2(self.lineup_loss), "depth_lost": _rn(self.depth_lost), "future_starts": _rn(self.future_starts),
                "future_start_weeks": self.future_start_weeks, "season_value": _rn(self.season_value),
                "upside": _rn(self.upside), "cost": _r2(self.cost), "piece": self.piece}


def _rn(x) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else _r2(float(x))


def season_value(points: float | None, replacement: float | None) -> float | None:
    """``trades.price_by_player``'s rule for one player: max(0, season points − the best free agent's at his
    position); a position with no free agent projected has replacement 0; no season points: unknown (None)."""
    if points is None or (isinstance(points, float) and math.isnan(points)):
        return None
    return max(0.0, float(points) - float(replacement or 0.0))


def cover_chance(position: str | None, starters_at_position: int) -> float:
    """The chance at least one of ``starters_at_position`` starters at this position misses a given week."""
    r = ABSENCE_RATE.get(str(position or ""), 0.0)
    return 1.0 - (1.0 - r) ** max(0, int(starters_at_position))


def depth_lost(values: Sequence[float | None], best_free: Sequence[float | None], sits: Sequence[bool],
               position: str | None, starters_at_position: Sequence[int]) -> float:
    """Σ over the weeks he sits: max(0, his value − the best free agent's at his position) × ``cover_chance``."""
    out = 0.0
    for v, f, s, k in zip(values, best_free, sits, starters_at_position, strict=True):
        if s and v is not None:
            out += max(0.0, float(v) - float(f or 0.0)) * cover_chance(position, k)
    return out


def drop_cost(lineup_loss: float, *, depth: float | None = None, future: float | None = None, future_weeks: int | None = None,
              season: float | None = None, upside: float | None = None) -> DropCost:
    return DropCost(max(0.0, float(lineup_loss or 0.0)), depth, future, future_weeks, season, upside)


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def choose_drops(rows: Sequence[Mapping]) -> list[dict]:
    """One roster's move rows (``ops.waiver_moves``' columns) with the drop's cost, the net gains and the ranks set:
    per add the best drop is the cheapest; moves ordered by net horizon gain, then net weekly gain. The value pieces
    are read from the rows (``drop_depth_lost``, ``drop_future_starts``, ``drop_season_value``, ``drop_upside``: None =
    not measured); the lineup loss from the row's own gains. The nightly writer, the on-demand sweep and the API's read
    of an older mart all call it; a 'nothing' row passes through."""
    rows = [dict(r) for r in rows]
    moves = [r for r in rows if r.get("list_kind") != "nothing" and isinstance(r.get("add_sleeper_id"), str)]
    if not moves:
        return rows
    incumbent: dict[str, str] = {}
    for r in moves:                     # the starter the add pushes out this week (a row that drops someone else)
        disp, d = r.get("displaced_sleeper_id"), r.get("drop_sleeper_id")
        if isinstance(disp, str) and disp != d and (_f(r.get("weekly_gain")) or 0.0) > 0:
            incumbent.setdefault(r["add_sleeper_id"], disp)
    for r in moves:
        d = r.get("drop_sleeper_id") if isinstance(r.get("drop_sleeper_id"), str) else None
        wg, hg = _f(r.get("weekly_gain")) or 0.0, _f(r.get("horizon_gain")) or 0.0
        if d is None:
            dc = DropCost(0.0, None, None, None, None, None)
        else:
            alone = _f(r.get("add_horizon_gain"))
            ll = (alone - hg) if alone is not None else (_f(r.get("drop_horizon_loss")) or 0.0)
            dc = drop_cost(ll, depth=_f(r.get("drop_depth_lost")), future=_f(r.get("drop_future_starts")),
                           future_weeks=None if _f(r.get("drop_future_start_weeks")) is None else int(_f(r["drop_future_start_weeks"])),
                           season=_f(r.get("drop_season_value")), upside=_f(r.get("drop_upside")))
        excess = dc.cost - dc.lineup_loss
        r.update({"drop_cost": _r2(dc.cost) if d else None, "drop_cost_piece": dc.piece if d else None,
                  "drop_lineup_loss": _r2(dc.lineup_loss) if d else None,
                  "drop_is_incumbent": (d is not None and incumbent.get(r["add_sleeper_id"]) == d) if d else None,
                  "net_weekly_gain": _r2(wg - excess), "net_horizon_gain": _r2(hg - excess)})
        r["is_worthwhile"] = bool(r["net_weekly_gain"] >= WORTH_WEEK or r["net_horizon_gain"] >= WORTH_HORIZON)

    def order(r: dict) -> tuple:
        d = r.get("drop_sleeper_id") if isinstance(r.get("drop_sleeper_id"), str) else None
        return (-round(r["net_horizon_gain"], 2), -round(r["net_weekly_gain"], 2), d is not None,
                round(_f(r.get("drop_cost")) or 0.0, 2), not bool(r.get("drop_is_incumbent")),
                round(_f(r.get("drop_ros_points")) or 0.0, 2), r["add_sleeper_id"], d or "")
    ranked = sorted(moves, key=order)
    best: dict[str, int] = {}
    for i, r in enumerate(ranked, 1):
        is_best = r["add_sleeper_id"] not in best
        if is_best:
            best[r["add_sleeper_id"]] = len(best) + 1
        r.update({"move_rank": i, "is_best_drop": is_best, "add_rank": best[r["add_sleeper_id"]] if is_best else None})
    return [r for r in rows if r.get("list_kind") == "nothing" or not isinstance(r.get("add_sleeper_id"), str)] + ranked


# ------------------------------------------------------------------------------ ranking and rows
def rank_moves(moves: Sequence[MoveResult], drop_points: Mapping[str | None, float]) -> list[tuple[MoveResult, int, bool, int | None]]:
    """(move, move_rank, is_best_drop, add_rank). Order: horizon gain, then this week's gain; among
    equal moves 'no drop' first, then the drop with the fewest ``drop_points`` (his projected points
    over the rest of the season: the least useful player). The best drop per add is his first move;
    adds are ranked by their best move."""
    def order(m: MoveResult) -> tuple:
        return (-round(m.horizon_gain, 2), -round(m.weekly_gain, 2), m.drop is not None,
                round(drop_points.get(m.drop, 0.0), 2), m.add, m.drop or "")
    ranked = sorted(moves, key=order)
    best: dict[str, int] = {}
    out = []
    for i, m in enumerate(ranked, 1):
        is_best = m.add not in best
        if is_best:
            best[m.add] = len(best) + 1
        out.append((m, i, is_best, best[m.add] if is_best else None))
    return out


def list_kind(m: MoveResult) -> str:
    return "start_now" if _gains(m.weekly_gain) else "cover"


# ------------------------------------------------------------------------------ persistence
DDL = {
    "ops.waiver_moves": """create table if not exists ops.waiver_moves (
        run_at timestamptz, as_of timestamptz, model_version text, league_id text, season integer, week integer,
        roster_id integer, horizon_weeks integer, horizon_last_week integer, list_kind text, move_rank integer,
        add_rank integer, is_best_drop boolean, add_sleeper_id text, add_gsis_id text, add_name text,
        add_position text, add_value double precision, add_value_source text, add_reason text, add_report_status text,
        add_games_played integer, is_no_evidence boolean, drop_sleeper_id text, drop_gsis_id text, drop_name text,
        drop_position text, drop_value double precision, drop_ros_points double precision, add_ros_points double precision,
        rest_of_season_weeks integer, drop_horizon_loss double precision, drop_is_starter boolean, weekly_gain double precision,
        horizon_gain double precision, week_gains double precision[], add_horizon_gain double precision,
        lineup_before double precision, lineup_after double precision, add_slot text, add_slot_type text,
        fills_empty_slot boolean, displaced_sleeper_id text, displaced_gsis_id text, displaced_name text,
        displaced_position text, displaced_value double precision, displaced_slot text, open_roster_spots integer,
        inputs_fingerprint text)""",
}
# IF-1: the drop's cost columns, added to a table created before them (``_write`` runs these first)
COST_DDL = [f"alter table ops.waiver_moves add column if not exists {c} {t}" for c, t in (
    ("drop_cost", "double precision"), ("drop_cost_piece", "text"), ("drop_lineup_loss", "double precision"),
    ("drop_depth_lost", "double precision"), ("drop_future_starts", "double precision"), ("drop_future_start_weeks", "integer"),
    ("drop_season_value", "double precision"), ("drop_season_points", "double precision"),
    ("drop_replacement_points", "double precision"), ("drop_upside", "double precision"), ("drop_is_incumbent", "boolean"),
    ("net_weekly_gain", "double precision"), ("net_horizon_gain", "double precision"), ("is_worthwhile", "boolean"))]
MOVE_COLUMNS = ["run_at", "as_of", "model_version", "league_id", "season", "week", "roster_id", "horizon_weeks",
                "horizon_last_week", "list_kind", "move_rank", "add_rank", "is_best_drop", "add_sleeper_id", "add_gsis_id",
                "add_name", "add_position", "add_value", "add_value_source", "add_reason", "add_report_status",
                "add_games_played", "is_no_evidence", "drop_sleeper_id", "drop_gsis_id", "drop_name", "drop_position",
                "drop_value", "drop_ros_points", "add_ros_points", "rest_of_season_weeks", "drop_horizon_loss", "drop_is_starter", "weekly_gain", "horizon_gain",
                "week_gains", "add_horizon_gain", "lineup_before", "lineup_after", "add_slot", "add_slot_type",
                "fills_empty_slot", "displaced_sleeper_id", "displaced_gsis_id", "displaced_name", "displaced_position",
                "displaced_value", "displaced_slot", "open_roster_spots", "inputs_fingerprint"]
ALL_COLUMNS = [*MOVE_COLUMNS, *COST_COLUMNS]   # IF-1: what the writer stores (MOVE_COLUMNS = the base DDL, kept identical)

# The legality inputs of a league at the time the moves were computed: who is rostered where (IR /
# taxi included) and each player's free-agent / NFL-roster / injury status. `mart_waiver_moves` and
# `assert_waiver_moves_are_legal` recompute the same expression and only hold moves whose league is
# unchanged since to the legality test (a claim, a drop or a new injury report between the nightly
# dbt build and the next `project` must not fail the night). Keep the three copies identical
# (tests/test_waivers.py checks).
FINGERPRINT_SQL = """select a.league_id, md5(a.fp || '|' || coalesce(r.fp, '')) as fp
from (select league_id, string_agg(sleeper_id || ':' || coalesce(rostered_by_roster_id::text, '') || ':'
                                   || coalesce(roster_status, '') || ':' || coalesce(injury_status, ''), ','
                                   order by sleeper_id, gsis_id) as fp
      from analytics.mart_player_availability group by league_id) as a
left join (select league_id, string_agg(roster_id::text || ':' || sleeper_player_id || ':' || coalesce(is_on_ir::text, '')
                                        || ':' || coalesce(is_on_taxi::text, ''), ','
                                        order by roster_id, sleeper_player_id) as fp
           from analytics.mart_league_roster_membership group by league_id) as r using (league_id)"""


def _frame(cur: psycopg.Cursor, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    names = [d.name for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def _num(v) -> float | None:
    return None if v is None else float(v)


@dataclass
class WaiverRun:
    season: int | None
    rows: pd.DataFrame
    seconds: float
    sweep_seconds: float
    stats: dict = field(default_factory=dict)
    week: dict[str, int] = field(default_factory=dict)


def _roster_player(r: dict, sleeper: Mapping[str, dict]) -> Player:
    """An ops.lineups row back into the Player B1 solved it as (fantasy positions from Sleeper)."""
    sp = sleeper.get(r["sleeper_player_id"]) or {}
    fp = tuple(sp["fantasy_positions"]) if sp.get("fantasy_positions") else None
    return Player(id=r["sleeper_player_id"], position=r["position"], value=_num(r["value"]),
                  playable=r["role"] in ("starter", "bench"), locked_slot=r["slot_type"] if r["is_locked"] else None,
                  value_source=r["value_source"], reason=r["reason"], status=r["report_status"], fantasy_positions=fp)


def load_and_sweep(conn: psycopg.Connection, season: int, as_of: datetime | None = None, *,
                   only: tuple[str, int] | None = None, unpruned: bool = False,
                   pieces_out: dict | None = None) -> tuple[list[dict], dict, dict]:
    """Read the inputs and evaluate every roster (or ``only`` = (league, roster)). Returns
    (ops.waiver_moves rows, stats, decision week per league). IG-3: ``pieces_out`` (a dict) receives each roster's
    drop pieces for every droppable player, keyed (league, roster) — the stash writer's input."""
    t_load = time.perf_counter()
    with conn.cursor() as cur:
        totals = _frame(cur, """
            select league_id, week, roster_id, lineup_value, as_of, model_version
            from ops.lineup_totals where season = %s and not is_realised""", (season,))
    if not totals:
        return [], {"note": "ops.lineup_totals has no proposed lineups for this season"}, {}
    lineup_as_of = max(t["as_of"] for t in totals if t["as_of"] is not None)
    as_of = as_of or lineup_as_of
    inp = load_inputs(conn, season)                           # B1's inputs: projections, games, K PPG, rosters
    obs_ppg = _observed_ppg(inp)
    ids = [lg["league_id"] for lg in inp.leagues]
    lineup_weeks: dict[str, list[int]] = defaultdict(list)
    for t in totals:
        lineup_weeks[t["league_id"]].append(int(t["week"]))
    decision: dict[str, int] = {}
    horizon: dict[str, list[int]] = {}
    for lg in inp.leagues:
        lid = lg["league_id"]
        weeks = sorted(set(lineup_weeks.get(lid, [])))
        upcoming = [w for w in weeks if w > int(lg["last_scored_leg"])
                    and any(k is not None and k > as_of for k in inp.games.get(w, {}).values())]
        if upcoming:
            decision[lid] = upcoming[0]
            horizon[lid] = [w for w in weeks if upcoming[0] <= w < upcoming[0] + HORIZON]
    first = min(decision.values(), default=None)
    want = sorted({w for ws in lineup_weeks.values() for w in ws if first is not None and w >= first})
    with conn.cursor() as cur:
        lrows = _frame(cur, """
            select league_id, week, roster_id, role, slot, slot_type, sleeper_player_id, gsis_id, player_name, position,
                   value, value_source, is_locked, report_status, reason
            from ops.lineups where season = %s and not is_realised and role <> 'empty' and week = any(%s)""", (season, want))
        fa_rows = _frame(cur, """
            select league_id, sleeper_id, gsis_id, player_name, position, nfl_team, games_played
            from analytics.mart_player_availability
            where league_id = any(%s) and is_free_agent and roster_status = 'ACT'
              and sleeper_id is not null""", (ids,))
        # ---- IS-2: a free agent who sits this week (availability_gate.sits over Sleeper's directory copy and the
        # stored record) is not an add; was the mart's injury_status ("Out" / "IR": nflverse's newest report row)
        sit = LS.sitting(LS.blocks(LS.conn_query(conn), season, first))
        fa_rows = [r for r in fa_rows if r.get("gsis_id") not in sit]
        # ---- end IS-2
        fa_sids = sorted({r["sleeper_id"] for r in fa_rows} - set(inp.sleeper))
        for r in _frame(cur, """select sleeper_player_id, position, fantasy_positions, team
                                from staging.stg_sleeper__players where sleeper_player_id = any(%s)""", (fa_sids,)):
            inp.sleeper[r["sleeper_player_id"]] = r
        fps = {r["league_id"]: r["fp"] for r in _frame(cur, FINGERPRINT_SQL)}
        values = {lid: value_inputs(cur, lid, season, decision[lid], horizon[lid][-1]) for lid in decision}   # ---- IF-1
    totals_by = {(t["league_id"], int(t["week"]), int(t["roster_id"])): t for t in totals}
    by_roster_week: dict[tuple[str, int, int], list[dict]] = defaultdict(list)
    for r in lrows:
        by_roster_week[(r["league_id"], int(r["week"]), int(r["roster_id"]))].append(r)
    stats: dict = {"load_seconds": time.perf_counter() - t_load, "rosters": 0, "lineup_mismatch": 0}

    rows: list[dict] = []
    run_at = datetime.now(UTC)
    t_sweep = time.perf_counter()
    for lg in inp.leagues:
        lid = lg["league_id"]
        if lid not in decision or (only and only[0] != lid):
            continue
        slots = list(lg["roster_positions"] or [])
        slot_types = {s.type for s in parse_slots(slots)[0]}
        hz = horizon[lid]
        week0 = hz[0]
        # the free agents, as B1 would carry each of them in each horizon week
        adds: dict[str, list[Player | None]] = {}
        fa_meta: dict[str, dict] = {}
        for r in fa_rows:
            if r["league_id"] != lid:
                continue
            sp = inp.sleeper.get(r["sleeper_id"]) or {}
            positions = frozenset(sp.get("fantasy_positions") or [r["position"]])
            if not any(positions & SLOT_ELIGIBILITY[t] for t in slot_types):
                continue                                          # a K in a league without a K slot
            row = {"sleeper_player_id": r["sleeper_id"], "gsis_id": r["gsis_id"], "position": r["position"],
                   "nfl_team": r["nfl_team"], "is_starter": False, "slot": None}
            adds[r["sleeper_id"]] = [_proposed_player(inp, lid, w, row, None, obs_ppg, w > int(lg["last_scored_leg"]), as_of)
                                     for w in hz]
            fa_meta[r["sleeper_id"]] = {**r, "_row": row}
        rest = [w for w in sorted(set(lineup_weeks[lid])) if w >= week0]   # the rest of the season
        add_ros: dict[str, float] = {}
        for roster_id in lg["roster_ids"]:
            if only and only[1] != roster_id:
                continue
            stats["rosters"] += 1
            week_rows = [by_roster_week.get((lid, w, roster_id), []) for w in hz]
            tot0 = totals_by.get((lid, week0, roster_id))
            if tot0 is None or not week_rows[0]:
                continue

            def add_ros_of(sid: str, lid=lid, lg=lg, rest=rest, add_ros=add_ros, fa_meta=fa_meta) -> float:
                if sid not in add_ros:   # his projected points over the rest of the season, weeks he can play
                    ps = [_proposed_player(inp, lid, w, fa_meta[sid]["_row"], None, obs_ppg, w > int(lg["last_scored_leg"]), as_of)
                          for w in rest]
                    add_ros[sid] = sum(p.value for p in ps if p.playable and not _unvalued(p))
                return add_ros[sid]
            key = {"run_at": run_at, "as_of": as_of, "model_version": tot0["model_version"], "league_id": lid,
                   "season": season, "week": week0, "roster_id": roster_id, "horizon_weeks": len(hz),
                   "horizon_last_week": hz[-1], "inputs_fingerprint": fps.get(lid)}
            rows += sweep_roster(slots, week_rows, inp.current.get(lid, {}).get(roster_id, []), adds, fa_meta,
                                 [r for w in rest for r in by_roster_week.get((lid, w, roster_id), [])], len(rest), add_ros_of, key,
                                 inp.sleeper, lineup_value=float(tot0["lineup_value"]), stats=stats, unpruned=unpruned,
                                 pieces_out=pieces_out, **values.get(lid, {}))                          # ---- IG-3
    stats["sweep_seconds"] = time.perf_counter() - t_sweep
    stats["rows"] = len(rows)
    return rows, stats, decision


UPSIDE_POINTS_SQL = """select gsis_id, sum(points_gain)::double precision as upside from ops.player_scenarios
                       where league_id = %s and season = %s and week between %s and %s and points_gain > 0 group by gsis_id"""


def value_inputs(cur: psycopg.Cursor, league_id: str, season: int, week: int, last: int) -> dict:
    """IF-1: a house league's drop-value inputs for ``sweep_roster`` — the market (rest-of-season points per player key),
    the replacement per position (``trades.MARKET_SQL`` / ``REPLACEMENT_SQL``, the Trade Finder's prices) and each
    role scenario's extra points over the horizon (``ops.player_scenarios``, when the table exists)."""
    from .trades import MARKET_SQL, REPLACEMENT_SQL  # trades imports this module: imported here
    market = {r["player_key"]: float(r["season_points"]) for r in _frame(cur, MARKET_SQL, (league_id, season, week))
              if r["season_points"] is not None}
    repl = {r["position"]: float(r["replacement"]) for r in _frame(cur, REPLACEMENT_SQL, (league_id, season, week, league_id))
            if r["replacement"] is not None}
    cur.execute("select to_regclass('ops.player_scenarios') is not null")
    up = ({r["gsis_id"]: float(r["upside"]) for r in _frame(cur, UPSIDE_POINTS_SQL, (league_id, season, week, last))}
          if cur.fetchone()[0] else {})
    return {"market": market, "replacement": repl, "upside": up}


def sweep_roster(slots: Sequence[str], week_rows: Sequence[Sequence[Mapping]], cur_rows: Sequence[Mapping],
                 adds: Mapping[str, Sequence[Player | None]], fa_meta: Mapping[str, Mapping], rest_rows: Sequence[Mapping],
                 rest_weeks: int, add_ros_of, key: Mapping, sleeper: Mapping[str, dict], *, lineup_value: float | None = None,
                 stats: dict | None = None, unpruned: bool = False, market: Mapping[str, float] | None = None,
                 replacement: Mapping[str, float] | None = None, upside: Mapping[str, float] | None = None,
                 pieces_out: dict | None = None) -> list[dict]:
    """One roster's ``ops.waiver_moves`` rows (``load_and_sweep``'s per-roster step; Wave G's on-demand path calls it
    with lineups solved on request). ``week_rows`` = the roster's lineup rows per horizon week (ops.lineups' columns,
    no empty slots), ``cur_rows`` = today's roster (IR / taxi flags), ``adds`` = every free agent as B1 carries him per
    horizon week, ``fa_meta`` = sid -> gsis_id / player_name / position / games_played, ``rest_rows`` = the roster's
    lineup rows over the ``rest_weeks`` weeks of the rest of the season (each player's rest-of-season points: the drop's
    tie-break), ``add_ros_of(sid)`` = a free agent's rest-of-season points, ``key`` = the run / league / week columns,
    ``lineup_value`` = the stored lineup value the re-solve must reproduce (logged when it does not). IF-1: ``market`` =
    player key (gsis id; a DEF's Sleeper id) -> rest-of-season points (``trades.MARKET_SQL``), ``replacement`` = position
    -> the best free agent's (``trades.REPLACEMENT_SQL``), ``upside`` = player key -> a role scenario's extra points over
    the horizon; None: the season points from ``rest_rows`` and the replacement from ``add_ros_of``. ``rest_rows`` carry
    ``week`` (the future starts); the rows come out of ``choose_drops``."""
    stats = stats if stats is not None else {"lineup_mismatch": 0}
    lid, roster_id, week0 = key["league_id"], key["roster_id"], key["week"]
    limit = sum(1 for s in slots if str(s).upper() not in NOT_ROSTER_SPOTS)
    players = [[_roster_player(r, sleeper) for r in wr] for wr in week_rows]
    info = {r["sleeper_player_id"]: r for wr in reversed(week_rows) for r in wr}
    rows: list[dict] = []
    # the roster as Sleeper has it today: IR / taxi are not droppable and do not take a spot
    active = [r for r in cur_rows if not r.get("is_on_ir") and not r.get("is_on_taxi")]
    open_spots = limit - len(active)
    in_week0 = {r["sleeper_player_id"]: r for r in week_rows[0]}
    droppable = [r["sleeper_player_id"] for r in active
                 if r["sleeper_player_id"] in in_week0 and not in_week0[r["sleeper_player_id"]]["is_locked"]
                 and in_week0[r["sleeper_player_id"]]["reason"] != "game started (bench)"]
    pool = {a: seq for a, seq in adds.items() if a not in info}
    if open_spots < 0:
        moves = []                                      # over the limit: no single add/drop is legal
    elif unpruned:
        moves = roster_moves_unpruned(slots, players, pool, droppable, open_spots > 0)
    else:
        moves = roster_moves(slots, players, pool, droppable, open_spots > 0, stats=stats)
    # the solver on ops.lineups must reproduce ops.lineup_totals (same players, same values)
    chk = solve(players[0], slots, margins=False).total
    if lineup_value is not None and abs(chk - float(lineup_value)) > 0.005:
        stats["lineup_mismatch"] = stats.get("lineup_mismatch", 0) + 1
        log.warning("waivers: %s roster %s week %s re-solves to %.2f, ops.lineup_totals says %.2f",
                    lid, roster_id, week0, chk, float(lineup_value))
    key = {**key, "open_roster_spots": open_spots}
    # ---- IG-3: the drop's value pieces of every droppable player, for the stash writer (``upside_stashes`` names the
    # stash's drop by the same cost); a player's pieces do not depend on the add or on which other players are priced
    if pieces_out is not None and droppable:
        pieces_out[(lid, int(roster_id))] = drop_pieces(
            slots, players, rest_rows, adds, fa_meta, info, sleeper, set(droppable), key.get("horizon_last_week"), rest_weeks,
            add_ros_of, market=market, replacement=replacement, upside=upside)
    # ---- end IG-3
    if not moves:
        rows.append({**key, "list_kind": "nothing", "lineup_before": _r2(chk), "lineup_after": _r2(chk),
                     "weekly_gain": 0.0, "horizon_gain": 0.0})
        return rows
    # each player's projected points over the rest of the season, weeks he can play (starting or
    # not): among equally good moves the drop with the fewest is named (the least useful player)
    ros: dict[str | None, float] = defaultdict(float)
    for r in rest_rows:
        if r["value"] is not None and r["role"] in ("starter", "bench") and r["value_source"] != UNVALUED:
            ros[r["sleeper_player_id"]] += float(r["value"])
    starters0 = {r["sleeper_player_id"] for r in week_rows[0] if r["role"] == "starter"}
    add_ros = {m.add: add_ros_of(m.add) for m in moves}
    for m, rank, is_best, add_rank in rank_moves(moves, ros):
        fa = fa_meta[m.add]
        a0 = adds[m.add][0]
        d = info.get(m.drop) if m.drop else None
        disp = info.get(m.displaced) if m.displaced else None
        disp0 = in_week0.get(m.displaced) if m.displaced else None
        rows.append({
            **key, "list_kind": list_kind(m), "move_rank": rank, "add_rank": add_rank, "is_best_drop": is_best,
            "add_sleeper_id": m.add, "add_gsis_id": fa["gsis_id"], "add_name": fa["player_name"],
            "add_position": fa["position"], "add_value": _r2(a0.value) if a0 is not None and a0.value is not None else None,
            "add_value_source": a0.value_source if a0 is not None else None,
            "add_reason": a0.reason if a0 is not None and not a0.playable else None,
            "add_report_status": a0.status if a0 is not None else None,
            "add_games_played": int(fa["games_played"]) if fa["games_played"] is not None else None,
            "is_no_evidence": not fa["games_played"],
            "drop_sleeper_id": m.drop, "drop_gsis_id": d["gsis_id"] if d else None,
            "drop_name": d["player_name"] if d else None, "drop_position": d["position"] if d else None,
            "drop_value": _r2(_num(in_week0[m.drop]["value"])) if m.drop else None,
            "drop_ros_points": _r2(ros.get(m.drop, 0.0)) if m.drop else None,
            "add_ros_points": _r2(add_ros[m.add]), "rest_of_season_weeks": rest_weeks,
            "drop_horizon_loss": _r2(sum(m.drop_loss)) if m.drop else None,
            "drop_is_starter": (m.drop in starters0) if m.drop else None,
            "weekly_gain": _r2(m.weekly_gain), "horizon_gain": _r2(m.horizon_gain),
            "week_gains": [_r2(g) for g in m.week_gains], "add_horizon_gain": _r2(sum(m.add_alone)),
            "lineup_before": _r2(m.lineup_before), "lineup_after": _r2(m.lineup_after),
            "add_slot": m.add_slot, "add_slot_type": m.add_slot_type,
            "fills_empty_slot": m.add_slot is not None and m.displaced is None,
            "displaced_sleeper_id": m.displaced, "displaced_gsis_id": disp["gsis_id"] if disp else None,
            "displaced_name": disp["player_name"] if disp else None,
            "displaced_position": disp["position"] if disp else None,
            "displaced_value": _r2(_num(disp0["value"])) if disp0 else None,
            "displaced_slot": disp0["slot"] if disp0 else None,
        })
    # ---- IF-1: the drop's value pieces (per player: the add does not change them), then the cost-ordered ranks
    need = {r["drop_sleeper_id"] for r in rows if r.get("drop_sleeper_id")}
    have = (pieces_out or {}).get((lid, int(roster_id))) or {}                                            # ---- IG-3
    pieces = {**have, **drop_pieces(slots, players, rest_rows, adds, fa_meta, info, sleeper, need - set(have),
                                     key.get("horizon_last_week"), rest_weeks, add_ros_of, market=market,
                                     replacement=replacement, upside=upside)}
    for r in rows:
        r.update(pieces.get(r.get("drop_sleeper_id"), {}))
    return choose_drops(rows)


def _rest_player(r: Mapping, sleeper: Mapping[str, dict], position: str | None) -> Player:
    """A rest-of-season lineup row (ops.lineups' columns; the on-demand rows carry fewer) as the solver's Player."""
    sp = sleeper.get(r["sleeper_player_id"]) or {}
    fp = tuple(sp["fantasy_positions"]) if sp.get("fantasy_positions") else None
    return Player(id=r["sleeper_player_id"], position=r.get("position") or position or "", value=_num(r.get("value")),
                  playable=r.get("role") in ("starter", "bench"), locked_slot=None, value_source=r.get("value_source"),
                  reason=r.get("reason"), status=r.get("report_status"), fantasy_positions=fp)


def drop_pieces(slots: Sequence[str], players: Sequence[Sequence[Player]], rest_rows: Sequence[Mapping],
                adds: Mapping[str, Sequence[Player | None]], fa_meta: Mapping[str, Mapping], info: Mapping[str, Mapping],
                sleeper: Mapping[str, dict], drops: set[str], horizon_last: int | None, rest_weeks: int, add_ros_of, *,
                market: Mapping[str, float] | None = None, replacement: Mapping[str, float] | None = None,
                upside: Mapping[str, float] | None = None) -> dict[str, dict]:
    """IF-1: per drop candidate, the ``ops.waiver_moves`` value columns (``drop_depth_lost``, ``drop_future_starts``,
    ``drop_future_start_weeks``, ``drop_season_value``, ``drop_season_points``, ``drop_replacement_points``,
    ``drop_upside``); see the block comment above ``DropCost``."""
    if not drops:
        return {}
    pos_of = {sid: (info.get(sid) or {}).get("position") for sid in drops}

    def pkey(sid: str) -> str:
        g = (info.get(sid) or {}).get("gsis_id")
        return str(g) if isinstance(g, str) and g else sid
    # season points: the market's (every projected week left) or, without one, the lineup rows' (weeks he can play)
    ros: dict[str, float] = defaultdict(float)
    for r in rest_rows:
        if r.get("value") is not None and r.get("role") in ("starter", "bench") and r.get("value_source") != UNVALUED:
            ros[r["sleeper_player_id"]] += float(r["value"])
    repl_cache: dict[str, float] = {}

    def repl(pos: str | None) -> float:
        if replacement is not None:
            return float(replacement.get(str(pos or ""), 0.0) or 0.0)
        if pos not in repl_cache:
            repl_cache[pos] = max((add_ros_of(a) for a, m in fa_meta.items() if m.get("position") == pos), default=0.0)
        return repl_cache[pos]
    # the horizon weeks: who sits, the best free agent per position, the starters per position
    lus = [solve(ps, slots, margins=False) for ps in players]
    best_free: list[dict[str, float]] = []
    for h in range(len(players)):
        bf: dict[str, float] = {}
        for a, seq in adds.items():
            p = seq[h] if h < len(seq) else None
            p = _norm(p) if p is not None else None
            pos = (fa_meta.get(a) or {}).get("position")
            if p is not None and pos and p.value is not None:
                bf[pos] = max(bf.get(pos, 0.0), float(p.value))
        best_free.append(bf)
    # the weeks after the horizon: each week's roster as the rest-of-season rows have it
    post: dict[int, list[Player]] = defaultdict(list)
    for r in rest_rows:
        w = r.get("week")
        if w is not None and horizon_last is not None and int(w) > int(horizon_last):
            post[int(w)].append(_rest_player(r, sleeper, (info.get(r["sleeper_player_id"]) or {}).get("position")))
    post_lu = {w: solve(ps, slots, margins=False) for w, ps in sorted(post.items())}
    weeks_left = max(1, int(rest_weeks) - 1)                 # the weeks left less a bye: a free agent's average week
    out: dict[str, dict] = {}
    for sid in drops:
        pos = pos_of.get(sid)
        k = pkey(sid)
        pts = _f(market.get(k)) if market is not None else (ros.get(sid) if sid in ros else None)
        rp = repl(pos)
        vals, sits, n_at = [], [], []
        for ps, lu in zip(players, lus, strict=True):
            me = next((p for p in ps if p.id == sid), None)
            vals.append(me.value if me is not None and me.playable and not _unvalued(me) else None)
            sits.append(me is not None and me.playable and sid not in set(lu.starter_ids))
            n_at.append(sum(1 for s in lu.starts if s.player is not None and s.player.position == pos))
        depth = depth_lost(vals, [bf.get(pos) for bf in best_free], sits, pos, n_at)
        fut, fut_w = 0.0, 0
        sp = sleeper.get(sid) or {}
        fps = tuple(sp["fantasy_positions"]) if sp.get("fantasy_positions") else None
        for w, lu in post_lu.items():
            if sid not in set(lu.starter_ids):
                continue
            fut_w += 1
            fa = Player(id="__free_agent__", position=pos or "", value=rp / weeks_left, playable=True,
                        value_source="replacement", fantasy_positions=fps)
            fut += max(0.0, lu.total - solve([q for q in post[w] if q.id != sid] + [fa], slots, margins=False).total)
        up = _f((upside or {}).get(k)) if upside is not None else None
        out[sid] = {"drop_depth_lost": _r2(depth), "drop_future_starts": _r2(fut) if post_lu else None,
                    "drop_future_start_weeks": fut_w if post_lu else None,
                    "drop_season_value": _rn(season_value(pts, rp)), "drop_season_points": _rn(pts),
                    "drop_replacement_points": _r2(rp), "drop_upside": _rn(up) if up is not None and up > 0 else None}
    return out


def _write(conn: psycopg.Connection, season: int, rows: list[dict]) -> None:
    """Replace the season's rows in one transaction."""
    with conn.cursor() as cur:
        for ddl in [*DDL.values(), *COST_DDL]:
            cur.execute(ddl)
        cur.execute("delete from ops.waiver_moves where season = %s", (season,))
        with cur.copy(f"copy ops.waiver_moves ({', '.join(ALL_COLUMNS)}) from stdin") as cp:
            for d in rows:
                cp.write_row([d.get(c) for c in ALL_COLUMNS])
    conn.commit()


def waiver_moves(conn: psycopg.Connection, season: int | None = None, as_of: datetime | None = None) -> WaiverRun:
    """Evaluate every roster and replace the season's rows in ``ops.waiver_moves``. ``season``
    defaults to the newest season in ``ops.lineup_totals``; ``as_of`` to the time those lineups were
    solved (so the free agents' locks and the rosters' locks are judged at the same instant)."""
    t0 = time.perf_counter()
    if season is None:
        with conn.cursor() as cur:
            cur.execute("select max(season) from ops.lineup_totals where not is_realised")
            season = cur.fetchone()[0]
    if season is None:
        log.warning("waivers: ops.lineup_totals is empty (run `league-lab project` first)")
        return WaiverRun(None, pd.DataFrame(columns=ALL_COLUMNS), 0.0, 0.0)
    season = int(season)
    pieces: dict = {}                                                                                  # ---- IG-3
    rows, stats, decision = load_and_sweep(conn, season, as_of, pieces_out=pieces)
    _write(conn, season, rows)
    run = WaiverRun(season, pd.DataFrame(rows, columns=ALL_COLUMNS), time.perf_counter() - t0,
                    stats.get("sweep_seconds", 0.0), stats, decision)
    moves = int((run.rows["list_kind"] != "nothing").sum()) if len(run.rows) else 0
    upside_after_waivers(conn, season, pieces)    # R-12: the upside stash list (ops.waiver_upside); logged, never fatal
    log.info("waiver moves written for %s: %s rows (%s moves, %s rosters with nothing better) for weeks %s "
             "in %.2f s (sweep %.2f s; %s of %s free-agent x roster pairs past the bar)",
             season, len(rows), moves, len(rows) - moves, decision, run.seconds, run.sweep_seconds,
             stats.get("survivors", 0), stats.get("adds", 0))
    return run


def waivers_after_project(conn: psycopg.Connection, season: int | None) -> WaiverRun | None:
    """Called at the end of ``league-lab project``, after the lineups: a failure is logged, never
    fatal (the previous ``ops.waiver_moves`` rows are kept)."""
    try:
        return waiver_moves(conn, season)
    except Exception:
        conn.rollback()
        log.exception("waiver engine failed (projections and lineups were written); run `league-lab waivers`")
        return None


def verify_roster(conn: psycopg.Connection, league_id: str, roster_id: int, season: int | None = None) -> dict:
    """Pruned vs unpruned on one roster: the stored moves must be identical (read-only)."""
    if season is None:
        with conn.cursor() as cur:
            cur.execute("select max(season) from ops.lineup_totals where not is_realised")
            season = int(cur.fetchone()[0])
    t0 = time.perf_counter()
    pruned, stats, _ = load_and_sweep(conn, season, only=(league_id, roster_id))
    t1 = time.perf_counter()
    full, _, _ = load_and_sweep(conn, season, only=(league_id, roster_id), unpruned=True)
    t2 = time.perf_counter()
    cols = [c for c in ALL_COLUMNS if c not in ("run_at",)]

    def canon(rows: list[dict]) -> list[tuple]:
        return sorted(tuple(str(r.get(c)) for c in cols) for r in rows)
    a, b = canon(pruned), canon(full)
    return {"season": season, "pruned_rows": len(pruned), "unpruned_rows": len(full), "identical": a == b,
            "only_pruned": [x for x in a if x not in b][:5], "only_unpruned": [x for x in b if x not in a][:5],
            "pruned_seconds": t1 - t0, "unpruned_seconds": t2 - t1, "survivors": stats.get("survivors"),
            "adds": stats.get("adds")}


def run_waivers(season: int | None = None) -> WaiverRun:
    from .config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        return waiver_moves(conn, season)


def run_verify(league_id: str, roster_id: int, season: int | None = None) -> dict:
    from .config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        return verify_roster(conn, league_id, roster_id, season)


__all__ = ["ALL_COLUMNS", "COST_COLUMNS", "DDL", "DropCost", "FINGERPRINT_SQL", "choose_drops", "drop_cost", "drop_pieces", "HORIZON", "MOVE_COLUMNS", "MoveResult", "WaiverRun", "entry_bar", "prepare",
           "rank_moves", "roster_moves", "roster_moves_unpruned", "run_verify", "run_waivers", "sweep_roster", "verify_roster",
           "waiver_moves", "waivers_after_project"]


# ------------------------------------------------------------------------------ R-12: the upside stash list (list_kind = 'upside')
# A free agent whose role grew in his last one to three games (a live role alert, league_lab.signals) and
# whose projection has a larger-role scenario, and who does NOT help this roster at his projection today
# (horizon gain <= 0: B3's start-now / cover lists do not carry him) — the stash case. Per roster he is
# valued the B3 way twice over the same horizon: the lineup gain at his projection (base_*_gain, <= 0 by
# construction) and "if it holds" at the scenario's projection for the weeks the scenario covers (the
# projection after it lapses). The drop is ``choose_drops``' cheapest for the add "if it holds" (IG-3; was B3's
# least lineup loss: see the IG-3 block below; none on an open roster spot). Written to
# ops.waiver_upside (its own table: the B3 lists, their dbt tests and the page's B3 region read
# ops.waiver_moves untouched); view mart_waiver_upside.

# the card's wording: "projects +X if it holds" from UPSIDE_MIN_GAIN, else "the projection already counts most of it"
UPSIDE_MIN_GAIN = 1.0
UPSIDE_DDL = """create table if not exists ops.waiver_upside (
    run_at timestamptz, as_of timestamptz, league_id text, season integer, week integer, roster_id integer,
    horizon_last_week integer, list_kind text, upside_rank integer, add_sleeper_id text, add_gsis_id text, add_name text,
    add_position text, add_team text, base_value double precision, scenario_value double precision, points_gain double precision,
    with_alert_value double precision, presentation text, alert_week integer, since_week integer, games_held integer,
    confidence text, kind text, trigger_kind text, trigger_name text, cause_text text, change_text text,
    expires_after_week integer, expiry_rule text, drop_sleeper_id text,
    drop_gsis_id text, drop_name text, drop_position text, drop_horizon_loss double precision, base_weekly_gain double precision,
    base_horizon_gain double precision, holds_weekly_gain double precision, holds_horizon_gain double precision,
    holds_week_gains double precision[], holds_slot text, open_roster_spots integer, inputs_fingerprint text)"""
UPSIDE_COLUMNS = ["run_at", "as_of", "league_id", "season", "week", "roster_id", "horizon_last_week", "list_kind", "upside_rank",
                  "add_sleeper_id", "add_gsis_id", "add_name", "add_position", "add_team", "base_value", "scenario_value",
                  "points_gain", "with_alert_value", "presentation", "alert_week", "since_week", "games_held", "confidence", "kind",
                  "trigger_kind", "trigger_name", "cause_text", "change_text", "expires_after_week", "expiry_rule",
                  "drop_sleeper_id", "drop_gsis_id",
                  "drop_name", "drop_position", "drop_horizon_loss", "base_weekly_gain", "base_horizon_gain",
                  "holds_weekly_gain", "holds_horizon_gain", "holds_week_gains", "holds_slot", "open_roster_spots",
                  "inputs_fingerprint"]


@dataclass(frozen=True)
class Stash:
    add: str
    drop: str | None
    drop_loss: float
    base_gains: tuple[float, ...]
    holds_gains: tuple[float, ...]
    holds_slot: str | None
    # ---- IG-3: the drop chosen by ``choose_drops`` (the cheapest by the drop's cost) and the claim / watch call
    choice: dict = field(default_factory=dict, compare=False)


# ---- IG-3 (Wave I-G): the stash writer follows ``choose_drops``. B3's rule named the drop that costs the LINEUP least
# (a bench WR who never starts was free), and the API re-decided claim / watch on read from IF-1's cost. Now each
# stash add is paired with every legal drop (none on an open roster spot) "if his role holds", the candidate rows carry
# the same value pieces as ``ops.waiver_moves`` (``drop_pieces``: depth, later starts, season value, upside) and go
# through ``choose_drops``: the stash's drop is the cheapest, the net gains are IF-1's, and the row says
# ``stash_action`` = 'claim' when that best pairing is worth a roster spot (``is_worthwhile``: net ≥ 1 this week or ≥ 3
# over the horizon, if the role holds), else 'watch' — no claim yet: the screen recommends no drop, the row keeps the
# drop a claim would take (the legality tests and the console read it) and its cost. The mart then says what the
# screen says.
STASH_PIECE_KEYS = ("drop_depth_lost", "drop_future_starts", "drop_future_start_weeks", "drop_season_value",
                    "drop_season_points", "drop_replacement_points", "drop_upside")


def upside_for_roster(slots: Sequence[str], weeks: Sequence[Sequence[Player]], adds_base: Mapping[str, Sequence[Player | None]],
                      adds_holds: Mapping[str, Sequence[Player | None]], droppable: Sequence[str], open_spot: bool,
                      ros: Mapping[str, float], pieces: Mapping[str, Mapping] | None = None) -> list[Stash]:
    """One roster's stashes (pure). ``weeks`` / ``droppable`` / ``open_spot`` as for ``roster_moves``;
    ``adds_base[id][h]`` the free agent as B1 carries him in horizon week h, ``adds_holds[id][h]`` the
    same with the larger-role projection where the scenario covers week h; ``ros`` = each rostered
    player's projected points over the rest of the season (the drop's tie-break); ``pieces`` = each drop
    candidate's value pieces (``drop_pieces``' columns; missing = not measured: the cost is his lineup loss).
    IG-3: the drop is ``choose_drops``' best for the add "if it holds" (``Stash.choice`` carries the cost, the
    net gains and ``stash_action``)."""
    weeks, droppable = guard(slots, weeks, droppable)
    if not open_spot and not droppable:
        return []
    preps = [prepare(ps, slots) for ps in weeks]
    loss = {d: sum(w.total - (_what_if(w, None, d)[0] if d in w.starters else w.total) for w in preps) for d in droppable}
    drops: list[str | None] = [None] if open_spot else list(droppable)
    pieces = pieces or {}
    out = []
    for a in sorted(adds_holds):
        gains: dict[str, dict[str | None, tuple[float, ...]]] = {"base": {}, "holds": {}}
        alone_h: list[float] = []
        displaced: str | None = None
        for label, seq in (("base", adds_base[a]), ("holds", adds_holds[a])):
            ps = [_norm(seq[h]) if h < len(seq) and seq[h] is not None else None for h in range(len(preps))]
            for d in drops:
                gains[label][d] = tuple((_what_if(w, p, d)[0] if p is not None else _what_if(w, None, d)[0]) - w.total
                                        for w, p in zip(preps, ps, strict=True))
            if label == "holds":
                for h, (w, p) in enumerate(zip(preps, ps, strict=True)):
                    t, st = _what_if(w, p, None) if p is not None else (w.total, set())
                    alone_h.append(t - w.total)
                    if h == 0 and p is not None and t - w.total > 0:     # the starter the add pushes out this week
                        gone = [q for q in w.pool if q.id in w.starters and q.id not in st]
                        displaced = min(gone, key=lambda q: q.value or 0.0).id if gone else None
        rows = [{"add_sleeper_id": a, "drop_sleeper_id": d, "list_kind": "upside",
                 "weekly_gain": gains["holds"][d][0], "horizon_gain": sum(gains["holds"][d]),
                 "add_horizon_gain": sum(alone_h), "drop_ros_points": ros.get(d, 0.0) if d else None,
                 "displaced_sleeper_id": displaced, **({k: (pieces.get(d) or {}).get(k) for k in STASH_PIECE_KEYS} if d else {})}
                for d in drops]
        best = next(r for r in choose_drops(rows) if r.get("is_best_drop"))
        d = best["drop_sleeper_id"]
        claim = bool(best["is_worthwhile"])
        choice = {"stash_action": "claim" if claim else "watch", "drop_cost": best.get("drop_cost"),
                  "drop_cost_piece": best.get("drop_cost_piece"), "net_weekly_gain": best["net_weekly_gain"],
                  "net_horizon_gain": best["net_horizon_gain"],
                  "base_max_horizon": max(sum(g) for g in gains["base"].values())}
        slot = None
        p0 = _norm(adds_holds[a][0]) if adds_holds[a] and adds_holds[a][0] is not None else None
        if p0 is not None:
            lu = solve([q for q in weeks[0] if q.id != d] + [p0], slots, margins=False)
            slot = next((s.slot.label for s in lu.starts if s.player is not None and s.player.id == a), None)
        out.append(Stash(a, d, loss.get(d, 0.0) if d else 0.0, gains["base"][d], gains["holds"][d], slot, choice))
    return out
# ---- end IG-3


UPSIDE_SQL = """
select s.league_id, s.week, s.gsis_id, s.base_points, s.larger_points, s.points_gain, s.with_alert_points, s.presentation,
       s.alert_week, s.since_week, s.games_held, s.confidence, s.kind, s.trigger_kind, s.trigger_name, s.cause_text,
       s.change_text, s.expires_after_week, s.expiry_rule,
       a.sleeper_id, a.player_name, a.position, a.nfl_team, a.games_played
from ops.player_scenarios as s
join analytics.mart_player_availability as a on a.league_id = s.league_id and a.gsis_id = s.gsis_id
where s.season = %s and a.is_free_agent and a.roster_status = 'ACT' and a.sleeper_id is not null"""
# ---- IS-2: UPSIDE_SQL no longer reads injury_status; upside_stashes drops who sits (league_status, the one definition)


# ---- IG-3: the drop pieces the stash writer reads when the sweep did not hand them over (``upside_after_waivers`` run
# alone): one row per roster x drop of the season's ``ops.waiver_moves`` (a player's pieces are the same for every add)
STASH_PIECES_SQL = """select distinct on (league_id, roster_id, drop_sleeper_id) league_id, roster_id, drop_sleeper_id,
       drop_depth_lost, drop_future_starts, drop_future_start_weeks, drop_season_value, drop_season_points,
       drop_replacement_points, drop_upside
from ops.waiver_moves where season = %s and drop_sleeper_id is not null and drop_cost is not null
order by league_id, roster_id, drop_sleeper_id, move_rank"""


def stored_pieces(cur: psycopg.Cursor, season: int) -> dict:
    """{(league, roster): {drop sleeper id: pieces}} from ``ops.waiver_moves`` ({} before IF-1's columns exist)."""
    cur.execute("""select count(*) from information_schema.columns where table_schema = 'ops' and table_name = 'waiver_moves'
                   and column_name = 'drop_cost'""")
    if not cur.fetchone()[0]:
        return {}
    out: dict = defaultdict(dict)
    for r in _frame(cur, STASH_PIECES_SQL, (season,)):
        out[(r["league_id"], int(r["roster_id"]))][r["drop_sleeper_id"]] = {k: r.get(k) for k in STASH_PIECE_KEYS}
    return dict(out)
# ---- end IG-3


def upside_stashes(conn: psycopg.Connection, season: int, as_of: datetime | None = None,
                   pieces: Mapping[tuple[str, int], Mapping[str, Mapping]] | None = None) -> list[dict]:
    """Every roster's upside stashes for the decision week and horizon of ``ops.waiver_moves`` (just written).
    IG-3: ``pieces`` = the sweep's drop pieces per (league, roster) (None: read from ``ops.waiver_moves``)."""
    with conn.cursor() as cur:
        cur.execute("select to_regclass('ops.player_scenarios') is not null")
        if not cur.fetchone()[0]:
            return []
        if pieces is None:                                                                           # ---- IG-3
            pieces = stored_pieces(cur, season)
        wk = _frame(cur, """select league_id, max(week) as week, max(horizon_last_week) as last, max(as_of) as as_of
                            from ops.waiver_moves where season = %s group by 1""", (season,))
        scen = _frame(cur, UPSIDE_SQL, (season,))
    decision = {r["league_id"]: (int(r["week"]), int(r["last"]), r["as_of"]) for r in wk}
    if not scen or not decision:
        return []
    # ---- IS-2: a stash who sits this week is not proposed (was the mart's injury_status "Out" / "IR")
    sit = LS.sitting(LS.blocks(LS.conn_query(conn), season, min(w0 for (w0, _l, _a) in decision.values())))
    scen = [r for r in scen if r.get("gsis_id") not in sit]
    # ---- end IS-2
    inp = load_inputs(conn, season)
    obs_ppg = _observed_ppg(inp)
    by_fa: dict[tuple[str, str], dict[int, dict]] = defaultdict(dict)
    for r in scen:
        by_fa[(r["league_id"], r["sleeper_id"])][int(r["week"])] = r
    with conn.cursor() as cur:
        weeks_all = sorted({w for (w0, last, _) in decision.values() for w in range(w0, 19)})
        lrows = _frame(cur, """
            select league_id, week, roster_id, role, slot, slot_type, sleeper_player_id, gsis_id, player_name, position,
                   value, value_source, is_locked, report_status, reason
            from ops.lineups where season = %s and not is_realised and role <> 'empty' and week = any(%s)""", (season, weeks_all))
        for r in _frame(cur, """select sleeper_player_id, position, fantasy_positions, team from staging.stg_sleeper__players
                                where sleeper_player_id = any(%s)""", (sorted({s for (_, s) in by_fa} - set(inp.sleeper)),)):
            inp.sleeper[r["sleeper_player_id"]] = r
        fps = {r["league_id"]: r["fp"] for r in _frame(cur, FINGERPRINT_SQL)}
    by_roster_week: dict[tuple[str, int, int], list[dict]] = defaultdict(list)
    for r in lrows:
        by_roster_week[(r["league_id"], int(r["week"]), int(r["roster_id"]))].append(r)
    run_at = datetime.now(UTC)
    rows: list[dict] = []
    for lg in inp.leagues:
        lid = lg["league_id"]
        if lid not in decision:
            continue
        week0, last, lu_as_of = decision[lid]
        as_of_l = as_of or lu_as_of
        hz = list(range(week0, last + 1))
        slots = list(lg["roster_positions"] or [])
        slot_types = {s.type for s in parse_slots(slots)[0]}
        limit = sum(1 for s in slots if str(s).upper() not in NOT_ROSTER_SPOTS)
        cands = {sid: wks for (l2, sid), wks in by_fa.items() if l2 == lid}
        base_adds: dict[str, list[Player | None]] = {}
        holds_adds: dict[str, list[Player | None]] = {}
        meta: dict[str, dict] = {}
        for sid, wks in cands.items():
            first = wks[min(wks)]
            sp = inp.sleeper.get(sid) or {}
            positions = frozenset(sp.get("fantasy_positions") or [first["position"]])
            if not any(positions & SLOT_ELIGIBILITY[t] for t in slot_types):
                continue
            row = {"sleeper_player_id": sid, "gsis_id": first["gsis_id"], "position": first["position"],
                   "nfl_team": first["nfl_team"], "is_starter": False, "slot": None}
            base = [_proposed_player(inp, lid, w, row, None, obs_ppg, w > int(lg["last_scored_leg"]), as_of_l) for w in hz]
            holds = [replace(p, value=float(wks[w]["larger_points"])) if (p.playable and w in wks and p.value is not None) else p
                     for p, w in zip(base, hz, strict=True)]
            if not any(w in wks for w in hz):
                continue      # the scenario covers none of the horizon weeks
            base_adds[sid], holds_adds[sid] = base, holds
            meta[sid] = wks
        if not holds_adds:
            continue
        rest = [w for w in range(week0, 19)]
        for roster_id in lg["roster_ids"]:
            week_rows = [by_roster_week.get((lid, w, roster_id), []) for w in hz]
            if not week_rows[0]:
                continue
            players = [[_roster_player(r, inp.sleeper) for r in wr] for wr in week_rows]
            info = {r["sleeper_player_id"]: r for wr in reversed(week_rows) for r in wr}
            cur_rows = inp.current.get(lid, {}).get(roster_id, [])
            active = [r for r in cur_rows if not r.get("is_on_ir") and not r.get("is_on_taxi")]
            open_spots = limit - len(active)
            if open_spots < 0:
                continue                                          # over the limit: no single add is legal
            in_week0 = {r["sleeper_player_id"]: r for r in week_rows[0]}
            droppable = [r["sleeper_player_id"] for r in active       # the same rule as load_and_sweep
                         if r["sleeper_player_id"] in in_week0 and not in_week0[r["sleeper_player_id"]]["is_locked"]
                         and in_week0[r["sleeper_player_id"]]["reason"] != "game started (bench)"]
            ros: dict[str, float] = defaultdict(float)
            for w in rest:
                for r in by_roster_week.get((lid, w, roster_id), []):
                    if r["value"] is not None and r["role"] in ("starter", "bench") and r["value_source"] != UNVALUED:
                        ros[r["sleeper_player_id"]] += float(r["value"])
            pool_b = {a: s for a, s in base_adds.items() if a not in info}
            pool_h = {a: s for a, s in holds_adds.items() if a not in info}
            # the stash case: B3's lists do not carry him today (no pairing gains at his projection). IG-3: the drop is
            # choose_drops' cheapest "if it holds", with the roster's drop pieces from the sweep
            stashes = [s for s in upside_for_roster(slots, players, pool_b, pool_h, droppable, open_spots > 0, ros,
                                                    (pieces or {}).get((lid, int(roster_id))))
                       if _r2(s.choice.get("base_max_horizon", sum(s.base_gains))) <= 0]
            # order: what the bigger role adds to THIS lineup beyond what he adds as he is (B3's lists already
            # carry the base value), then the scenario's points gain, then the scenario's projection
            stashes.sort(key=lambda s: (-round(sum(s.holds_gains) - sum(s.base_gains), 2), -round(max(float(x["points_gain"]) for x in meta[s.add].values()), 2),
                                        -float(meta[s.add][min(meta[s.add])]["larger_points"]), s.add))
            for rank, s in enumerate(stashes, 1):
                wks = meta[s.add]
                w_show = week0 if week0 in wks else min(wks)
                sc = wks[w_show]
                ch = s.choice                                                                        # ---- IG-3
                d = info.get(s.drop) if s.drop else None
                rows.append({
                    "run_at": run_at, "as_of": as_of_l, "league_id": lid, "season": season, "week": week0, "roster_id": roster_id,
                    "horizon_last_week": last, "list_kind": "upside", "upside_rank": rank, "add_sleeper_id": s.add,
                    "add_gsis_id": sc["gsis_id"], "add_name": sc["player_name"], "add_position": sc["position"],
                    "add_team": sc["nfl_team"], "base_value": _r2(float(sc["base_points"])), "scenario_value": _r2(float(sc["larger_points"])),
                    "points_gain": _r2(float(sc["points_gain"])), "with_alert_value": _r2(float(sc["with_alert_points"])),
                    "presentation": sc["presentation"], "alert_week": sc["alert_week"], "since_week": sc["since_week"],
                    "games_held": sc["games_held"], "confidence": sc["confidence"], "kind": sc["kind"],
                    "trigger_kind": sc["trigger_kind"], "trigger_name": sc["trigger_name"], "cause_text": sc["cause_text"],
                    "change_text": sc["change_text"],
                    "expires_after_week": sc["expires_after_week"], "expiry_rule": sc["expiry_rule"],
                    "drop_sleeper_id": s.drop, "drop_gsis_id": d["gsis_id"] if d else None, "drop_name": d["player_name"] if d else None,
                    "drop_position": d["position"] if d else None, "drop_horizon_loss": _r2(s.drop_loss) if s.drop else None,
                    "base_weekly_gain": _r2(s.base_gains[0]), "base_horizon_gain": _r2(sum(s.base_gains)),
                    "holds_weekly_gain": _r2(s.holds_gains[0]), "holds_horizon_gain": _r2(sum(s.holds_gains)),
                    "holds_week_gains": [_r2(g) for g in s.holds_gains], "holds_slot": s.holds_slot,
                    "open_roster_spots": open_spots, "inputs_fingerprint": fps.get(lid),
                    # ---- IG-3: the claim / watch call and the cheapest drop's cost (choose_drops)
                    "stash_action": ch.get("stash_action"), "drop_cost": ch.get("drop_cost"),
                    "drop_cost_piece": ch.get("drop_cost_piece"), "net_weekly_gain": ch.get("net_weekly_gain"),
                    "net_horizon_gain": ch.get("net_horizon_gain"),
                })
    return rows


# ---- IG-3: the stash's call and its drop's cost, added to a table created before them (``write_upside`` runs these)
UPSIDE_COST_COLUMNS = ["stash_action", "drop_cost", "drop_cost_piece", "net_weekly_gain", "net_horizon_gain"]
UPSIDE_COST_DDL = [f"alter table ops.waiver_upside add column if not exists {c} {t}" for c, t in (
    ("stash_action", "text"), ("drop_cost", "double precision"), ("drop_cost_piece", "text"),
    ("net_weekly_gain", "double precision"), ("net_horizon_gain", "double precision"))]
UPSIDE_ALL_COLUMNS = [*UPSIDE_COLUMNS, *UPSIDE_COST_COLUMNS]
# ---- end IG-3


def write_upside(conn: psycopg.Connection, season: int, rows: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.execute(UPSIDE_DDL)
        for ddl in UPSIDE_COST_DDL:                                                                    # ---- IG-3
            cur.execute(ddl)
        cur.execute("delete from ops.waiver_upside where season = %s", (season,))
        with cur.copy(f"copy ops.waiver_upside ({', '.join(UPSIDE_ALL_COLUMNS)}) from stdin") as cp:
            for d in rows:
                cp.write_row([d.get(c) for c in UPSIDE_ALL_COLUMNS])
    conn.commit()


def upside_after_waivers(conn: psycopg.Connection, season: int, pieces: Mapping | None = None) -> int | None:
    """The upside list after the B3 moves (same decision week and horizon). Logged, never fatal. IG-3: ``pieces`` =
    the sweep's drop pieces (``load_and_sweep(pieces_out=…)``; None: read back from ``ops.waiver_moves``)."""
    try:
        t0 = time.perf_counter()
        rows = upside_stashes(conn, season, pieces=pieces)
        write_upside(conn, season, rows)
        log.info("upside stashes written for %s: %s rows (%s rosters, %s free agents) in %.2f s", season, len(rows),
                 len({(r["league_id"], r["roster_id"]) for r in rows}), len({(r["league_id"], r["add_sleeper_id"]) for r in rows}),
                 time.perf_counter() - t0)
        return len(rows)
    except Exception:
        conn.rollback()
        log.exception("upside stashes failed (waiver moves were written)")
        return None


__all__ += ["UPSIDE_ALL_COLUMNS", "UPSIDE_COLUMNS", "UPSIDE_COST_COLUMNS", "Stash", "stored_pieces", "upside_after_waivers",
            "upside_for_roster", "upside_stashes"]
