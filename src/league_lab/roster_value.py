"""Roster value on the B1 lineup service (plan B2, Iteration 9b): what a player is worth to a lineup
that is not his own.

The published lineup rows (``analytics.mart_league_roster_horizon`` = ``ops.lineups`` of the next four
weeks with names and Sleeper eligibility) carry, per roster-week, every starter, bench player and player
who cannot play, with the value the lineup service used. ``RosterBoard`` rebuilds the solver's input from
them (starters and bench are playable, a locked starter keeps his slot type, everybody else is left out),
which reproduces ``ops.lineup_totals.lineup_value`` to the cent, and answers:

* ``loss(player, week)`` - what his own roster loses without him: his margin in its lineup (the best
  lineup minus the best lineup re-solved without him; 0 for a bench player, who changes nothing);
* ``gain(roster, player, week)`` - what another roster gains with him: its best lineup with him added
  minus its best lineup now, i.e. the margin he would have in that roster's re-solved lineup. SUPER_FLEX
  and FLEX are filled by eligibility: a QB3 behind two better QBs (or behind a RB worth more at SUPER_FLEX)
  adds 0; a WR worth more than the FLEX starter adds the difference, even when he takes WR2 and pushes the
  WR2 into FLEX (the solver moves them; the gain is the same);
* ``fit = gain - loss`` - Trade Finder's "shape fit": the lineup points a move creates (the receiver gains
  more than the giver loses when their needs are opposite).

A player is available to another roster in a week when he can play for his own (starter or bench, not
locked) or sits on its taxi squad (a roster choice, not an injury); a bye, Out / Doubtful, NFL injured
reserve, Sleeper's IR slot or a game that has kicked off make him worth 0 to anybody that week.
Roster-size limits (who would be dropped) are out of scope here: that is the waiver engine (B3) and the
trade evaluator (T-01, ``league_lab.trades``), which re-solves whole packages with ``lineup_with`` (a
roster-week with players taken off and others' players put on) and reads roster spots from ``roster`` /
``is_active`` / ``active_count`` (Sleeper's IR slot and the taxi squad do not take a spot).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping

from .lineup import UNVALUED, Player, solve

PLAYABLE_ROLES = frozenset({"starter", "bench"})
# lineup-row reasons of a player who does not take an active roster spot (T-01): Sleeper's IR slot, taxi squad
INACTIVE_REASONS = frozenset({"IR slot", "taxi squad"})


def _get(row: Mapping, key: str, default=None):
    v = row.get(key, default) if hasattr(row, "get") else getattr(row, key, default)
    if v is None:
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    return v


def _positions(row: Mapping) -> tuple[str, ...] | None:
    fp = _get(row, "fantasy_positions")
    if fp is None:
        return None
    if isinstance(fp, str):   # a Postgres array read as text: "{DB,WR}"
        fp = [x for x in fp.strip("{}").split(",") if x]
    return tuple(str(x) for x in fp) or None


def _player(row: Mapping, *, locked: bool) -> Player:
    source = _get(row, "value_source")
    value = _get(row, "player_value", _get(row, "value"))
    return Player(
        id=str(_get(row, "sleeper_player_id")),
        position=_get(row, "position"),
        value=None if source == UNVALUED or value is None else float(value),
        value_source=source,
        fantasy_positions=_positions(row),
        locked_slot=_get(row, "slot_type") if locked else None,
    )


def players_from_rows(rows: Iterable[Mapping]) -> list[Player]:
    """The solver's players for one roster-week from its lineup rows: starters and bench players are
    playable, a locked starter keeps his slot type; empty slots and players who cannot play are left out."""
    out = []
    for r in rows:
        if _get(r, "role") not in PLAYABLE_ROLES or _get(r, "sleeper_player_id") is None:
            continue
        out.append(_player(r, locked=bool(_get(r, "is_locked", False)) and _get(r, "role") == "starter"))
    return out


def incoming_player(row: Mapping) -> Player | None:
    """The player as another roster would have him that week, from his row on his current roster, or
    None when he cannot play for anybody that week (see the module docstring)."""
    role, reason = _get(row, "role"), _get(row, "reason")
    if bool(_get(row, "is_locked", False)):
        return None
    if role in PLAYABLE_ROLES or (role == "unplayable" and reason == "taxi squad"):
        return _player(row, locked=False)
    return None


def _r2(x: float) -> float:
    return round(float(x) + 0.0, 2) + 0.0


class RosterBoard:
    """Every roster-week's lineup rows of one league, with the league's ``roster_positions``."""

    def __init__(self, rows: Iterable[Mapping], slots: Iterable[str]):
        self.slots = list(slots)
        self._rows: dict[tuple[int, int], list[Mapping]] = defaultdict(list)
        self._player: dict[tuple[str, int], Mapping] = {}
        self._owner: dict[str, int] = {}
        self._members: dict[int, dict[str, None]] = defaultdict(dict)   # roster -> players (insertion-ordered set)
        self._first: dict[str, tuple[int, Mapping]] = {}                 # player -> (first week, its row)
        for r in rows:
            roster, week = int(_get(r, "roster_id")), int(_get(r, "week"))
            self._rows[(roster, week)].append(r)
            sid = _get(r, "sleeper_player_id")
            if sid is not None:
                sid = str(sid)
                self._player[(sid, week)] = r
                self._owner[sid] = roster
                self._members[roster][sid] = None
                if sid not in self._first or week < self._first[sid][0]:
                    self._first[sid] = (week, r)
        self._pool: dict[tuple[int, int], list[Player]] = {}
        self._value: dict[tuple[int, int], float] = {}

    @property
    def weeks(self) -> list[int]:
        return sorted({w for _, w in self._rows})

    @property
    def rosters(self) -> list[int]:
        return sorted({r for r, _ in self._rows})

    def owner(self, player_id: str) -> int | None:
        return self._owner.get(str(player_id))

    def row(self, player_id: str, week: int) -> Mapping | None:
        return self._player.get((str(player_id), week))

    def pool(self, roster_id: int, week: int) -> list[Player]:
        key = (int(roster_id), int(week))
        if key not in self._pool:
            self._pool[key] = players_from_rows(self._rows.get(key, []))
        return self._pool[key]

    def lineup_value(self, roster_id: int, week: int) -> float:
        """The roster's best lineup that week, re-solved from its rows (= ops.lineup_totals.lineup_value)."""
        key = (int(roster_id), int(week))
        if key not in self._value:
            self._value[key] = solve(self.pool(*key), self.slots, margins=False).total
        return self._value[key]

    def gain(self, roster_id: int, player_id: str, week: int) -> float:
        """The lineup points ``roster_id`` gains that week by adding the player (his margin in its new
        lineup); 0 when he cannot play that week or is already on that roster."""
        row = self.row(player_id, week)
        if row is None or self.owner(player_id) == int(roster_id):
            return 0.0
        p = incoming_player(row)
        if p is None:
            return 0.0
        with_him = solve([*self.pool(roster_id, week), p], self.slots, margins=False).total
        return max(_r2(with_him - self.lineup_value(roster_id, week)), 0.0)

    def loss(self, player_id: str, week: int) -> float:
        """What his own roster loses that week without him: his margin (0 on the bench, when he cannot
        play, or when he is locked: his game has kicked off and he is not a decision any more)."""
        row = self.row(player_id, week)
        if row is None or _get(row, "role") != "starter" or bool(_get(row, "is_locked", False)):
            return 0.0
        m = _get(row, "lineup_margin", _get(row, "margin"))
        return _r2(m) if m is not None else 0.0

    def horizon_gain(self, roster_id: int, player_id: str, weeks: Iterable[int] | None = None) -> float:
        return _r2(sum(self.gain(roster_id, player_id, w) for w in (weeks or self.weeks)))

    def horizon_loss(self, player_id: str, weeks: Iterable[int] | None = None) -> float:
        return _r2(sum(self.loss(player_id, w) for w in (weeks or self.weeks)))

    # ---- T-01 (trade evaluator): whole packages, roster spots, locks
    def roster(self, roster_id: int) -> list[str]:
        """Every player on the roster (starters, bench, and those who cannot play: IR slot, taxi, bye ...)."""
        return list(self._members.get(int(roster_id), {}))

    def is_active(self, player_id: str) -> bool:
        """He takes one of the roster's active spots (starting + bench slots): not in Sleeper's IR slot, not on
        the taxi squad (read from his row in the board's first week: today's roster)."""
        first = self._first.get(str(player_id))
        return first is not None and _get(first[1], "reason") not in INACTIVE_REASONS

    def active_count(self, roster_id: int) -> int:
        return sum(self.is_active(p) for p in self.roster(roster_id))

    def is_locked(self, player_id: str, week: int) -> bool:
        """His game that week has kicked off: a locked starter, or a bench player whose game started."""
        row = self.row(player_id, week)
        return row is not None and (bool(_get(row, "is_locked", False)) or _get(row, "reason") == "game started (bench)")

    def has_value(self, player_id: str, weeks: Iterable[int] | None = None) -> bool:
        """He has a value (a projection, or points per game) in at least one of the weeks: unknown is not zero."""
        for w in (weeks or self.weeks):
            row = self.row(player_id, w)
            if row is not None and _get(row, "value_source") != UNVALUED and _get(row, "player_value", _get(row, "value")) is not None:
                return True
        return False

    def pool_with(self, roster_id: int, week: int, remove: Iterable[str] = (), add: Iterable[str] = ()) -> list[Player]:
        """The solver's players for the roster-week with ``remove`` taken off and ``add`` (players of other
        rosters, each as ``incoming_player`` carries him: left out when he cannot play for anybody that week)
        put on. The caller decides who may move (a locked player's game has kicked off: see league_lab.trades)."""
        gone = {str(x) for x in remove}
        out = [p for p in self.pool(roster_id, week) if p.id not in gone]
        for pid in add:
            row = self.row(pid, week)
            p = incoming_player(row) if row is not None else None
            if p is not None:
                out.append(p)
        return out

    def lineup_with(self, roster_id: int, week: int, remove: Iterable[str] = (), add: Iterable[str] = (), *,
                    margins: bool = False):
        """The best lineup of ``pool_with(...)`` (``lineup.solve``)."""
        return solve(self.pool_with(roster_id, week, remove, add), self.slots, margins=margins)


def trade_candidates(board: RosterBoard, roster_id: int, candidates: Iterable[Mapping]) -> tuple[list[dict], list[dict]]:
    """Trade Finder's two lists for ``roster_id`` (and the weekly pack's): ``candidates`` carry
    ``sleeper_player_id`` and ``diff_per_game`` (PPG - xPPG in this league's scoring) plus anything to pass
    through (name, position, PPG, xPPG).

    * buy low: players on OTHER rosters producing below their usage (diff < 0), each with what this
      roster gains with him and what his roster loses without him, this week (the board's first week)
      and over the board's weeks, and the fit = gain - loss;
    * sell high: THIS roster's players producing above their usage (diff > 0), each with what this roster
      loses and the roster that gains most over the weeks (``partner``), its gain and the fit.
    Both sorted by the horizon fit, best first (ties: the bigger gap)."""
    weeks = board.weeks
    if not weeks:
        return [], []
    w0, roster_id = weeks[0], int(roster_id)
    buy, sell = [], []
    for c in candidates:
        sid, diff = str(_get(c, "sleeper_player_id")), _get(c, "diff_per_game")
        owner = board.owner(sid)
        if owner is None or diff is None:
            continue
        base = dict(c)
        l_w, l_h = board.loss(sid, w0), board.horizon_loss(sid, weeks)
        if owner != roster_id and diff < 0:
            g_w, g_h = board.gain(roster_id, sid, w0), board.horizon_gain(roster_id, sid, weeks)
            buy.append({**base, "owner": owner, "gain_week": g_w, "gain_horizon": g_h, "loss_week": l_w, "loss_horizon": l_h,
                        "fit_week": _r2(g_w - l_w), "fit_horizon": _r2(g_h - l_h)})
        elif owner == roster_id and diff > 0:
            gains = [(r, board.horizon_gain(r, sid, weeks)) for r in board.rosters if r != roster_id]
            partner, g_h = max(gains, key=lambda t: (t[1], -t[0]), default=(None, 0.0))
            g_w = board.gain(partner, sid, w0) if partner is not None else 0.0
            sell.append({**base, "partner": partner, "gain_week": g_w, "gain_horizon": g_h, "loss_week": l_w, "loss_horizon": l_h,
                         "fit_week": _r2(g_w - l_w), "fit_horizon": _r2(g_h - l_h)})
    buy.sort(key=lambda d: (-d["fit_horizon"], -d["gain_horizon"], d["diff_per_game"]))
    sell.sort(key=lambda d: (-d["fit_horizon"], -d["diff_per_game"]))
    return buy, sell
