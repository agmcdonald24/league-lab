"""Trade evaluator and simulator (plan T-01 / T-02, Iteration 10), on the exact lineup service (B1).

What a trade does to two lineups
--------------------------------
``evaluate(board, give, get, weeks)`` takes a package - ``give`` (players of one roster: mine) for ``get``
(players of one other roster: theirs) - and re-solves **both** rosters' best legal lineups with
``lineup.solve`` in every week of the board's horizon (this week and the next three; byes, Out / NFL IR,
Sleeper's IR slot and the taxi squad exactly as in B1's lineup rows, ``RosterBoard``):

* before = the roster-week as B1 solved it (``RosterBoard.lineup_value`` = ``ops.lineup_totals``);
* after  = the same roster-week without the players it gives and with the players it gets (each as
  ``roster_value.incoming_player`` carries him: worth nothing that week on a bye, Out / Doubtful, NFL IR
  or in the IR slot; a taxi-squad player can play), and without the player it has to cut (below);
* **locks**: a player whose game that week has kicked off stays where he is that week (his points count
  there) and moves from the next week; a locked starter keeps his slot (``solve`` holds it).

**Gain** this week = after − before in the first week; over the horizon = the sum over the weeks. For this
week each side also carries its lineups with margins: depth (the bench's own best lineup, B1's ``bench_value``),
the closest call (``Lineup.weakest``) and who starts / who sits.

Roster size
-----------
Active spots = the starting + bench slots of ``roster_positions`` (IR and TAXI slots are not spots); active
players = those not in Sleeper's IR slot and not on the taxi squad (B3's rule). Every player a roster gets
takes an active spot (Sleeper puts a traded player on the bench); a player it gives frees one only if he held
one. A side that ends over its limit **cuts** until it fits: each cut is the droppable player whose removal
costs the post-trade lineups least over the horizon (0 for one who starts in none of them; when nobody is free
every droppable player is compared), among equals the one with the fewest rest-of-season projected points
(B3's drop rule); several cuts are taken one at a time. The cut's loss is in the after-lineups. Droppable = on
the roster before the trade and staying, active, not locked this week, with a value in some week (unknown is
not zero: a player with no value yet is never the cut). A side left with a spot the trade opened gets **the
best free agent to fill it** (``best_fill``): the free agent whose addition raises the post-trade lineups most
over the horizon, exactly, with B3's entry bar (an add's gain with nobody dropped is max(0, value − bar),
``waivers.entry_bar``). The fill is reported, never added to the gain.

Market value, kept apart from fit
---------------------------------
``market`` (season points): a player's rest-of-season projected points - Σ ``ops.projections.proj_points``
in this league's scoring (each week rounded to the cent, as the lineups carry it) over the remaining weeks
from this week on, K and DEF included (a DEF is keyed by its Sleeper id). ``MARKET_SQL`` reads it;
``market_by_player`` keys it by Sleeper id. It breaks ties between cuts (B3's drop rule).

``prices`` (the market score, what the fairness line adds up): season points **above the best free agent
at his position** - max(0, season points − replacement(position)), replacement = the most rest-of-season
projected points of a free agent at that position on an active NFL roster, not Out / IR (``REPLACEMENT_SQL``;
0 when the position has none). Position-adjusted on purpose: a kicker projects about as many season points
as a WR3, but anyone can pick one up, so his price is near 0; in a one-QB league the waiver wire holds
starting QBs, in a superflex league it does not. The projection it starts from already weighs usage (the v2
model's inputs include expected points, L5 and season, next to points per game). A price, not a lineup: it
counts every projected week, injured or benched, and says nothing about fit. A player with no projection has
no price (unknown, never 0). ``price_by_player`` keys it by Sleeper id.

Partners
--------
``partners(board, me)``: for every other roster, the best **1-for-1** and the best **2-for-1** (two of mine
for one of theirs, or one of mine for two of theirs) that raise **both** lineups over the horizon, ranked
by the smaller of the two horizon gains (the trade both sides gain most from), then by their sum. A
two-for-one counts only when each of the two players adds to the lineup of the team getting them (after it
loses the player it gives); otherwise it is a one-for-one with a throw-in. Exact search with bounds (a
branch and bound: the tests compare it with ``partners_exhaustive``):

* a lineup is a maximum-weight matching, so adding players has diminishing returns (the valuation is
  submodular): a set adds at most the sum of what each player would add alone, and taking players off
  never raises a lineup. So my gain from a package is at most what its incoming players add to (my roster
  minus the players I give) minus what losing those costs me; the same for them;
* what one player adds to a roster-week is exactly max(0, value − bar) (B3's entry bar), so a bound is a
  lookup once the bars of the rosters involved (mine, theirs, each without one player) are known;
* packages are evaluated with ``evaluate``'s own code in the order of their bound, until the bound falls
  below the best package found (or below a cent: nobody gains).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations

from .lineup import SKILL, UNVALUED, Lineup, Player, Start, solve
from .roster_value import RosterBoard, _get, _r2, incoming_player
from .waivers import entry_bar, prepare

NOT_ROSTER_SPOTS = frozenset({"IR", "TAXI"})
MIN_GAIN = 0.01    # gains are rounded to the cent (B2, B3); a gain is at least a cent
TOL = 1e-6         # float noise of a solve (B1's tie-break terms move a total by < slots x 1e-9)
# two market totals are "about even" when they differ by at most this many points or this share of the larger
EVEN_POINTS, EVEN_SHARE = 10, 0.10

# rest-of-season projected points per player key (gsis id; a DEF's Sleeper id) from this week on
MARKET_SQL = """
select gsis_id as player_key, round(sum(round(proj_points::numeric, 2)), 2)::double precision as season_points,
       count(*) as weeks
from ops.projections
where league_id = %s and season = %s and week >= %s and proj_points is not null
group by gsis_id"""

# the replacement level per position: the most rest-of-season projected points of a free agent (on an active NFL
# roster, not left out this week by the stored availability record - IS-2) - params (league_id, season, week, league_id)
REPLACEMENT_SQL = """
with season_points as (
    select gsis_id, round(sum(round(proj_points::numeric, 2)), 2) as season_points,
           -- ---- IS-2: the stored record of availability_gate (project writes it for a player who sits this week;
           -- to_jsonb reads a column that may not exist yet) - was the mart's injury_status ("Out" / "IR")
           bool_or(to_jsonb(p) ->> 'availability' is not null) as sits
    from ops.projections as p
    where league_id = %s and season = %s and week >= %s and proj_points is not null
    group by gsis_id
)
select a.position, max(s.season_points)::double precision as replacement,
       (array_agg(a.player_name order by s.season_points desc, a.sleeper_id))[1] as replacement_name
from analytics.mart_player_availability a
join season_points s on s.gsis_id = coalesce(a.gsis_id, a.sleeper_id)
where a.league_id = %s and a.is_free_agent and (a.roster_status = 'ACT' or a.position = 'DEF')
  and not s.sits                                                    -- ---- end IS-2
group by a.position"""


def roster_limit(slots: Iterable[str]) -> int:
    """Active roster spots: the starting + bench slots (IR and TAXI slots hold players off the active roster)."""
    return sum(1 for s in slots if str(s).upper() not in NOT_ROSTER_SPOTS)


def whole(x: float) -> int:
    """Round half up to a whole point (market values are shown and summed as whole points)."""
    return int(math.floor(float(x) + 0.5))


def market_by_player(board: RosterBoard, points: Mapping[str, float]) -> dict[str, float]:
    """Sleeper id -> rest-of-season points for every player on the board. ``points`` is keyed like
    ``ops.projections.gsis_id``: the gsis id (the board rows' ``gsis_id``), a DEF's Sleeper id. A player with
    no projection is left out (unknown, not 0)."""
    out = {}
    for roster in board.rosters:
        for sid in board.roster(roster):
            row = next((board.row(sid, w) for w in board.weeks if board.row(sid, w) is not None), None)
            gsis = _get(row, "gsis_id") if row is not None else None
            v = points.get(str(gsis) if gsis else sid)
            if v is not None and math.isfinite(float(v)):
                out[sid] = float(v)
    return out


def position_of(board: RosterBoard, player_id: str) -> str | None:
    row = next((board.row(player_id, w) for w in board.weeks if board.row(player_id, w) is not None), None)
    return _get(row, "position") if row is not None else None


def price_by_player(board: RosterBoard, market: Mapping[str, float], replacement: Mapping[str, float]) -> dict[str, float]:
    """Sleeper id -> market score: season points above the best free agent at his position, max(0, season points
    − replacement(position)); a position with no free agent projected has replacement 0. A player with no season
    points is left out (unknown, not 0)."""
    out = {}
    for sid, pts in market.items():
        repl = replacement.get(position_of(board, sid) or "", 0.0) or 0.0
        out[sid] = max(0.0, float(pts) - float(repl))
    return out


def about_even(a: float, b: float) -> bool:
    """Two market totals within EVEN_POINTS or EVEN_SHARE of the larger (the verdict calls that a fair price)."""
    return abs(a - b) <= max(EVEN_POINTS, EVEN_SHARE * max(abs(a), abs(b)))


# ------------------------------------------------------------------------------ results
@dataclass(frozen=True)
class Cut:
    player_id: str
    horizon_loss: float           # what cutting him costs the post-trade lineups over the weeks
    market: float | None          # his rest-of-season projected points (None: unknown)


@dataclass(frozen=True)
class Fill:
    player_id: str
    week_gains: tuple[float, ...]  # per week: post-trade lineup with him minus without him

    @property
    def week_gain(self) -> float:
        return self.week_gains[0] if self.week_gains else 0.0

    @property
    def horizon_gain(self) -> float:
        return _r2(sum(self.week_gains))


@dataclass(frozen=True)
class Side:
    """One roster's view of a trade."""
    roster_id: int
    gives: tuple[str, ...]
    gets: tuple[str, ...]
    weeks: tuple[int, ...]
    before: tuple[float, ...]            # best lineup per week, before
    after: tuple[float, ...]             # per week, after the trade and the cuts
    lineup_before: Lineup | None         # the first week's lineups (None in the partner search)
    lineup_after: Lineup | None
    cuts: tuple[Cut, ...]
    limit: int                           # active roster spots
    size_before: int                     # active players before
    size_after: int                      # active players after the trade and the cuts
    opened: int                          # active spots the trade opened (and left open)
    fill: Fill | None                    # the best free agent for an opened spot
    price_out: int | None                # market score given / got: whole points above a free agent (None: no prices)
    price_in: int | None
    points_out: int | None = None        # rest-of-season projected points given / got, whole (None: no market)
    points_in: int | None = None
    unknown_out: tuple[str, ...] = ()    # players given / got with no season projection
    unknown_in: tuple[str, ...] = ()
    bench_before: float | None = None    # depth this week: the best lineup the bench alone fields (None in the search)
    bench_after: float | None = None

    @property
    def gain_week(self) -> float:
        return _r2(self.after[0] - self.before[0]) if self.weeks else 0.0

    @property
    def gain_horizon(self) -> float:
        return _r2(sum(self.after) - sum(self.before))

    @property
    def before_horizon(self) -> float:
        return _r2(sum(self.before))

    @property
    def after_horizon(self) -> float:
        return _r2(sum(self.after))

    @property
    def weakest_before(self) -> Start | None:
        """This week's closest call before: the unlocked starter with the smallest margin (B1's ``weakest``)."""
        return self.lineup_before.weakest if self.lineup_before is not None else None

    @property
    def weakest_after(self) -> Start | None:
        return self.lineup_after.weakest if self.lineup_after is not None else None

    @property
    def sits(self) -> tuple[str, ...]:
        """This week's starters before who do not start after (traded, cut, or to the bench)."""
        if self.lineup_before is None or self.lineup_after is None:
            return ()
        after = set(self.lineup_after.starter_ids)
        return tuple(p for p in self.lineup_before.starter_ids if p not in after)

    @property
    def starts(self) -> tuple[str, ...]:
        """This week's starters after who did not start before (arrived, or up from the bench)."""
        if self.lineup_before is None or self.lineup_after is None:
            return ()
        before = set(self.lineup_before.starter_ids)
        return tuple(p for p in self.lineup_after.starter_ids if p not in before)


@dataclass(frozen=True)
class Trade:
    mine: Side
    theirs: Side

    @property
    def weeks(self) -> tuple[int, ...]:
        return self.mine.weeks


# ------------------------------------------------------------------------------ the evaluator
def _ids(x: Iterable | str | None) -> tuple[str, ...]:
    if x is None:
        return ()
    if isinstance(x, str):
        x = [x]
    return tuple(dict.fromkeys(str(i) for i in x if i is not None and str(i) != ""))


def _owner(board: RosterBoard, ids: Sequence[str], what: str) -> int:
    owners = {board.owner(i) for i in ids}
    if None in owners:
        raise ValueError(f"{what}: {[i for i in ids if board.owner(i) is None]} not on any roster of this board")
    if len(owners) != 1:
        raise ValueError(f"{what}: players of {len(owners)} rosters ({sorted(owners)}); a side comes from one roster")
    return owners.pop()


def _moving(board: RosterBoard, ids: Sequence[str], week: int) -> list[str]:
    """The players of ``ids`` who change roster that week: not those whose game has kicked off."""
    return [p for p in ids if not board.is_locked(p, week)]


def season_value(values: Mapping[str, float] | None, ids: Sequence[str]) -> tuple[int | None, tuple[str, ...]]:
    """(Σ whole points of the known players, the players with no value) for a side of a package: each player rounded
    half up first, so the total is the sum of the numbers the tables show."""
    if values is None:
        return None, ()
    known = [whole(values[p]) for p in ids if p in values]
    return sum(known), tuple(p for p in ids if p not in values)


def _cheapest(board: RosterBoard, cands: list[str], pools: list[list[Player]], lineups: list[Lineup],
              market: Mapping[str, float] | None) -> Cut:
    """The candidate whose removal costs the post-trade lineups least over the weeks; ties: fewest
    rest-of-season points (unknown last), then id. A player who starts in no week costs 0 (the lineups stay
    optimal without him), so candidates are tried in market order and the first free one wins."""
    def mkt(p: str) -> float:
        if market is None:
            return 0.0
        v = market.get(p)
        return math.inf if v is None else float(v)

    starters = [set(lu.starter_ids) for lu in lineups]
    bench = sorted((q for q in cands if not any(q in s for s in starters)), key=lambda q: (mkt(q), q))
    best: tuple[tuple, str, float] | None = ((0.0, mkt(bench[0]), bench[0]), bench[0], 0.0) if bench else None
    if best is not None and market is None:
        # no market to break ties (the partner search): every free cut leaves the same lineups, take one
        return Cut(best[1], 0.0, None)
    for p in sorted((q for q in cands if q not in bench), key=lambda q: (mkt(q), q)):
        if best is not None and best[2] <= TOL and (mkt(p), p) >= best[0][1:]:
            break     # the best cut is free: a starter can at best tie it on loss, and he has more season points
        loss = 0.0
        for h, lu in enumerate(lineups):
            if p in starters[h]:
                loss += lu.total - solve([q for q in pools[h] if q.id != p], board.slots, margins=False).total
        loss = max(0.0, _r2(loss))
        key = (loss, mkt(p), p)
        if best is None or key < best[0]:
            best = (key, p, loss)
    _, pid, loss = best
    return Cut(pid, loss, market.get(pid) if market is not None else None)


def _after(board: RosterBoard, roster: int, out: Sequence[str], inc: Sequence[str], weeks: Sequence[int],
           market: Mapping[str, float] | None) -> tuple[list[list[Player]], list[Lineup], list[Cut], int]:
    """(pools, lineups, cuts, active players) of one roster after the trade, per week."""
    limit = roster_limit(board.slots)
    size = board.active_count(roster) - sum(board.is_active(p) for p in out) + len(inc)
    pools = [board.pool_with(roster, w, _moving(board, out, w), _moving(board, inc, w)) for w in weeks]
    lineups = [solve(ps, board.slots, margins=False) for ps in pools]
    cuts: list[Cut] = []
    over = size - limit
    if over > 0:
        gone = set(out)
        stay = [p for p in board.roster(roster) if p not in gone and board.is_active(p)]
        cands = [p for p in stay if not board.is_locked(p, weeks[0]) and board.has_value(p, weeks)]
        if len(cands) < over:     # not expected: fall back to the unknown, then to anybody staying
            cands = [p for p in stay if not board.is_locked(p, weeks[0])]
        if len(cands) < over:
            cands = list(stay)
        if len(cands) < over:
            raise ValueError(f"roster {roster}: {size} active players after the trade and only {len(cands)} to cut "
                             f"(limit {limit})")
        for _ in range(over):
            c = _cheapest(board, cands, pools, lineups, market)
            cuts.append(c)
            cands.remove(c.player_id)
            for h in range(len(weeks)):
                started = c.player_id in lineups[h].starter_ids
                pools[h] = [q for q in pools[h] if q.id != c.player_id]
                if started:
                    lineups[h] = solve(pools[h], board.slots, margins=False)
        size -= len(cuts)
    return pools, lineups, cuts, size


def _side(board: RosterBoard, roster: int, out: Sequence[str], inc: Sequence[str], weeks: Sequence[int],
          market: Mapping[str, float] | None, free_agents: Mapping[str, Mapping[int, Player | None]] | None,
          *, detail: bool = True, prices: Mapping[str, float] | None = None) -> Side:
    pools, lineups, cuts, size = _after(board, roster, out, inc, weeks, market)
    limit = roster_limit(board.slots)
    size_before = board.active_count(roster)
    opened = min(max(0, limit - size), max(0, size_before - size))
    fill = best_fill(board, weeks, pools, free_agents) if detail and opened > 0 and free_agents else None
    po, uo = season_value(prices, out)
    pi, ui = season_value(prices, inc)
    so, uo2 = season_value(market, out)
    si, ui2 = season_value(market, inc)
    before_lu = after_lu = None
    bench_before = bench_after = None
    if detail and weeks:
        # this week's lineups with margins (the closest call) and the bench's own best lineup (depth, as B1 stores it)
        before_lu = solve(board.pool(roster, weeks[0]), board.slots, margins=True)
        after_lu = solve(pools[0], board.slots, margins=True)
        bench_before = _r2(solve(before_lu.bench, board.slots, margins=False).total)
        bench_after = _r2(solve(after_lu.bench, board.slots, margins=False).total)
    return Side(
        roster_id=int(roster), gives=tuple(out), gets=tuple(inc), weeks=tuple(weeks),
        before=tuple(board.lineup_value(roster, w) for w in weeks), after=tuple(lu.total for lu in lineups),
        lineup_before=before_lu, lineup_after=after_lu,
        cuts=tuple(cuts), limit=limit, size_before=size_before, size_after=size, opened=opened, fill=fill,
        price_out=po, price_in=pi, points_out=so, points_in=si,
        unknown_out=uo if prices is not None else uo2, unknown_in=ui if prices is not None else ui2,
        bench_before=bench_before, bench_after=bench_after)


def evaluate(board: RosterBoard, give: Iterable[str], get: Iterable[str], weeks: Iterable[int] | None = None, *,
             market: Mapping[str, float] | None = None, prices: Mapping[str, float] | None = None,
             free_agents: Mapping[str, Mapping[int, Player | None]] | None = None) -> Trade:
    """Both rosters before and after the package (see the module docstring). ``give``: players of one roster
    (mine); ``get``: players of one other roster (theirs); ``weeks``: default the board's (this week first);
    ``market``: Sleeper id -> rest-of-season points (the cut's tie-break, ``points_out`` / ``points_in``);
    ``prices``: Sleeper id -> market score (``price_by_player``: the fairness line's ``price_out`` / ``price_in``);
    ``free_agents``: Sleeper id -> {week: Player as B1 would carry him on a roster that week (None / not playable:
    cannot play)} for the open-spot fill."""
    give, get = _ids(give), _ids(get)
    if not give or not get:
        raise ValueError("a trade needs at least one player on each side")
    me, them = _owner(board, give, "give"), _owner(board, get, "get")
    if me == them:
        raise ValueError("give and get come from the same roster")
    weeks = tuple(int(w) for w in (weeks or board.weeks))
    if not weeks:
        raise ValueError("no weeks to evaluate")
    return Trade(_side(board, me, give, get, weeks, market, free_agents, prices=prices),
                 _side(board, them, get, give, weeks, market, free_agents, prices=prices))


# ------------------------------------------------------------------------------ the open spot
def _valued(p: Player | None) -> bool:
    return (p is not None and p.playable and p.value is not None and math.isfinite(p.value)
            and p.value_source != UNVALUED and p.value > 0)


def best_fill(board: RosterBoard, weeks: Sequence[int], pools: Sequence[Sequence[Player]],
              free_agents: Mapping[str, Mapping[int, Player | None]]) -> Fill | None:
    """The free agent whose addition (nobody dropped) raises the lineups of ``pools`` (one roster, per week of
    ``weeks``) most over the weeks, then this week; None when nobody raises them. Exact: an add's gain in a
    roster-week is max(0, value − bar(his positions)) (waivers.entry_bar)."""
    preps = [prepare(list(ps), board.slots) for ps in pools]
    bars: list[dict[frozenset, float | None]] = [{} for _ in preps]
    best: tuple[tuple, str, tuple[float, ...]] | None = None
    for fid in sorted(free_agents):
        if board.owner(fid) is not None:
            continue                                   # rostered since the free-agent list was read
        by_week = free_agents[fid] or {}
        gains = []
        for h, w in enumerate(weeks):
            p = by_week.get(w)
            if not _valued(p):
                gains.append(0.0)
                continue
            if p.positions not in bars[h]:
                bars[h][p.positions] = entry_bar(preps[h], p.positions)
            bar = bars[h][p.positions]
            gains.append(0.0 if bar is None else max(0.0, p.value - bar))
        g = tuple(_r2(x) for x in gains)
        key = (-_r2(sum(gains)), -g[0] if g else 0.0, fid)
        if best is None or key < best[0]:
            best = (key, fid, g)
    if best is None or -best[0][0] < MIN_GAIN:
        return None
    return Fill(best[1], best[2])


# ------------------------------------------------------------------------------ partners
@dataclass(frozen=True)
class Package:
    partner: int
    give: tuple[str, ...]
    get: tuple[str, ...]
    my_week: float
    my_horizon: float
    their_week: float
    their_horizon: float

    @property
    def shape(self) -> str:
        return f"{len(self.give)}-for-{len(self.get)}"

    @property
    def mutual(self) -> bool:
        return self.my_horizon >= MIN_GAIN and self.their_horizon >= MIN_GAIN

    @property
    def score(self) -> tuple[float, float]:
        """(the smaller horizon gain, the sum): the trade both sides gain most from comes first."""
        return _r2(min(self.my_horizon, self.their_horizon)), _r2(self.my_horizon + self.their_horizon)

    def order(self) -> tuple:
        s = self.score
        return (-s[0], -s[1], len(self.give) + len(self.get), self.give, self.get)


@dataclass(frozen=True)
class Partner:
    roster_id: int
    one_for_one: Package | None
    two_for_one: Package | None       # the best of 2-for-1 (two of mine) and 1-for-2 (two of theirs)

    @property
    def best(self) -> Package | None:
        cands = [p for p in (self.one_for_one, self.two_for_one) if p is not None]
        return min(cands, key=Package.order) if cands else None


def package_gains(board: RosterBoard, give: Sequence[str], get: Sequence[str], weeks: Sequence[int]) -> Package:
    """A package's four gains with ``evaluate``'s code (cuts included; no fill, no market)."""
    give, get = _ids(give), _ids(get)
    me, them = _owner(board, give, "give"), _owner(board, get, "get")
    a = _side(board, me, give, get, weeks, None, None, detail=False)
    b = _side(board, them, get, give, weeks, None, None, detail=False)
    return Package(them, give, get, a.gain_week, a.gain_horizon, b.gain_week, b.gain_horizon)


def tradeable(board: RosterBoard, roster: int, weeks: Sequence[int]) -> list[str]:
    """Players a partner search moves: on the roster with a value in some week (unknown is not zero)."""
    return [p for p in board.roster(roster) if board.has_value(p, weeks)]


class _Bars:
    """One roster, per week, with some of its players taken off (those whose game has kicked off stay): its
    best total and, lazily, the entry bar per position set, so what a player adds is a lookup."""

    def __init__(self, board: RosterBoard, roster: int, weeks: Sequence[int], remove: Sequence[str] = (),
                 free: Mapping[int, Sequence[Player]] | None = None):
        self.preps = []
        for w in weeks:
            ps = board.pool_with(roster, w, _moving(board, remove, w))
            pr = prepare(ps, board.slots)
            if free is not None and pr.lineup.empty_slots:   # ---- IU-1: the replacement frame (empty slots filled)
                pr = prepare(_covered_pool(ps, board.slots, free.get(int(w), ())), board.slots)
            self.preps.append(pr)
        self.totals = [p.total for p in self.preps]
        self._bars: list[dict[frozenset, float | None]] = [{} for _ in weeks]
        self._adds: dict[str, float] = {}

    def adds(self, incoming: Sequence[Player | None]) -> list[float]:
        """Per week: what this player (as he would arrive that week) adds to the lineup."""
        out = []
        for h, p in enumerate(incoming):
            if not _valued(p):
                out.append(0.0)
                continue
            positions = p.positions
            c = self._bars[h]
            if positions not in c:
                c[positions] = entry_bar(self.preps[h], positions)
            bar = c[positions]
            out.append(0.0 if bar is None else max(0.0, p.value - bar))
        return out

    def adds_total(self, pid: str, incoming: Sequence[Player | None]) -> float:
        """Σ over the weeks of ``adds`` (memoised per player)."""
        if pid not in self._adds:
            self._adds[pid] = sum(self.adds(incoming))
        return self._adds[pid]


def _useful(g: Sequence[float]) -> bool:
    return round(sum(g), 2) >= MIN_GAIN


@dataclass
class _Search:
    board: RosterBoard
    me: int
    weeks: tuple[int, ...]
    stats: dict = field(default_factory=dict)
    allow: Callable[[Package], str | None] | None = None     # IA-2: None = keep; a reason = the package is set aside
    rejected: list = field(default_factory=list)              # IA-2: (package, reason) set aside, in search order
    free: Mapping[int, Sequence[Player]] | None = None        # IU-1: search on the replacement frame (None: roster-only)

    def __post_init__(self):
        self.incoming: dict[str, list[Player | None]] = {}
        self.minus: dict[tuple[int, str], _Bars] = {}
        self.full: dict[int, _Bars] = {}
        self._loss: dict[tuple[int, str], float] = {}
        self._ub: dict[tuple[int, str, str], float] = {}

    def inc(self, pid: str) -> list[Player | None]:
        if pid not in self.incoming:
            b = self.board
            self.incoming[pid] = [None if b.is_locked(pid, w) or b.row(pid, w) is None else incoming_player(b.row(pid, w))
                                  for w in self.weeks]
        return self.incoming[pid]

    def bars(self, roster: int) -> _Bars:
        if roster not in self.full:
            self.full[roster] = _Bars(self.board, roster, self.weeks, free=self.free)
        return self.full[roster]

    def bars_minus(self, roster: int, pid: str) -> _Bars:
        key = (roster, pid)
        if key not in self.minus:
            self.minus[key] = _Bars(self.board, roster, self.weeks, [pid], free=self.free)
            self.stats["bar_sets"] = self.stats.get("bar_sets", 0) + 1
        return self.minus[key]

    def loss(self, roster: int, pid: str) -> float:
        """Σ over the weeks of what the roster's lineup loses without him (0 in a week he is locked: he stays)."""
        key = (roster, pid)
        if key not in self._loss:
            full, minus = self.bars(roster), self.bars_minus(roster, pid)
            self._loss[key] = sum(max(0.0, a - b) for a, b in zip(full.totals, minus.totals, strict=True))
        return self._loss[key]

    def adds(self, bars: _Bars, pid: str) -> float:
        return bars.adds_total(pid, self.inc(pid))

    def one_ub(self, roster: int, out: str, x: str) -> float:
        """Upper bound (exact without a cut) of a roster's horizon gain giving ``out`` and getting ``x``."""
        key = (roster, out, x)
        if key not in self._ub:
            self._ub[key] = self.adds(self.bars_minus(roster, out), x) - self.loss(roster, out)
        return self._ub[key]

    def evaluate(self, give: tuple[str, ...], get: tuple[str, ...]) -> Package:
        self.stats["evaluated"] = self.stats.get("evaluated", 0) + 1
        if self.free is not None:                                                    # ---- IU-1
            return self.covered_gains(give, get)
        return package_gains(self.board, give, get, self.weeks)

    def covered_gains(self, give: tuple[str, ...], get: tuple[str, ...]) -> Package:
        """IU-1: a package's four gains on the replacement frame — each side after the trade (`_after`: the cuts) with
        its empty starting slots filled, against its covered total before (`bars(...).totals`). The verdict's exact
        numbers (`covered_pair`: one free agent never for both teams) come later, on the rows shown."""
        board, weeks = self.board, self.weeks
        them = _owner(board, get, "get")
        gains = []
        for roster, out, inc in ((self.me, give, get), (them, get, give)):
            pools, lineups, _, _ = _after(board, roster, out, inc, weeks, None)
            after = [lu.total if not lu.empty_slots else fill_lineup(ps, board.slots, self.free.get(int(w), ()))[0].total
                     for ps, lu, w in zip(pools, lineups, weeks, strict=True)]
            g = [_r2(a - b) for a, b in zip(after, self.bars(roster).totals, strict=True)]
            gains.append((g[0] if g else 0.0, _r2(sum(after) - sum(self.bars(roster).totals))))
        return Package(them, tuple(give), tuple(get), gains[0][0], gains[0][1], gains[1][0], gains[1][1])


def _best(search: _Search, cands: list[tuple[float, tuple[str, ...], tuple[str, ...]]]) -> Package | None:
    """Branch and bound over (upper bound, give, get): evaluate in bound order until the bound cannot reach
    the best package found (or a cent). With ``search.allow`` (IA-2): a package that would be the best so far but
    fails the sanity rules is set aside (``search.rejected``) and the search goes on to the next."""
    best: Package | None = None
    search.stats["candidates"] = search.stats.get("candidates", 0) + len(cands)
    for ub, give, get in sorted(cands, key=lambda c: (-c[0], len(c[1]) + len(c[2]), c[1], c[2])):
        floor = max(MIN_GAIN, best.score[0] if best is not None else MIN_GAIN)
        if ub + 0.005 + TOL < floor:
            break
        pk = search.evaluate(give, get)
        if pk.mutual and (best is None or pk.order() < best.order()):
            why = search.allow(pk) if search.allow is not None else None   # ---- IA-2: the sanity bound
            if why:
                search.rejected.append((pk, why))
                continue
            best = pk
    return best


def partner(search: _Search, them: int, shapes: Sequence[str] = ("1-for-1", "2-for-1", "1-for-2"),
            want: str | None = None) -> Partner:
    board, me, weeks = search.board, search.me, search.weeks
    mine, theirs = tradeable(board, me, weeks), tradeable(board, them, weeks)
    if want is not None:      # Wave G (G2): only packages that bring me a player at this position
        theirs = [b for b in theirs if position_of(board, b) == want]
    me_full, them_full = search.bars(me), search.bars(them)
    # a player the other side cannot use (adds nothing to its full roster in any week) can only move as a
    # throw-in: a package's gain for the receiver is at most what its players add to the full roster
    useful_b = [b for b in theirs if round(search.adds(me_full, b), 2) >= MIN_GAIN]     # could raise my lineup
    useful_a = [a for a in mine if round(search.adds(them_full, a), 2) >= MIN_GAIN]     # could raise theirs

    one = two = None
    if "1-for-1" in shapes:
        cands = []
        for a in useful_a:
            for b in useful_b:
                ub = min(search.one_ub(me, a, b), search.one_ub(them, b, a))
                cands.append((ub, (a,), (b,)))
        one = _best(search, cands)
    cands2 = []
    if "2-for-1" in shapes:     # two of mine (each useful to them without b) for one of theirs
        for b in useful_b:
            minus_b = search.bars_minus(them, b)
            loss_b = search.loss(them, b)
            g = {a: search.adds(minus_b, a) for a in mine}
            ok = [a for a in mine if round(g[a], 2) >= MIN_GAIN]
            for a1, a2 in combinations(ok, 2):
                my_ub = min(search.one_ub(me, a1, b), search.one_ub(me, a2, b))
                their_ub = g[a1] + g[a2] - loss_b
                cands2.append((min(my_ub, their_ub), (a1, a2), (b,)))
    if "1-for-2" in shapes:     # one of mine for two of theirs (each useful to me without a)
        for a in useful_a:
            minus_a = search.bars_minus(me, a)
            loss_a = search.loss(me, a)
            g = {b: search.adds(minus_a, b) for b in theirs}
            ok = [b for b in theirs if round(g[b], 2) >= MIN_GAIN]
            for b1, b2 in combinations(ok, 2):
                my_ub = g[b1] + g[b2] - loss_a
                their_ub = min(search.one_ub(them, b1, a), search.one_ub(them, b2, a))
                cands2.append((min(my_ub, their_ub), (a,), (b1, b2)))
    if cands2:
        two = _best(search, cands2)
    return Partner(int(them), one, two)


def partners(board: RosterBoard, me: int, *, weeks: Iterable[int] | None = None,
             shapes: Sequence[str] = ("1-for-1", "2-for-1", "1-for-2"), stats: dict | None = None,
             rosters: Iterable[int] | None = None, want: str | None = None,
             allow: Callable[[Package], str | None] | None = None, rejected: list | None = None,
             free: Mapping[int, Sequence[Player]] | None = None) -> list[Partner]:
    """Every other roster (or those in ``rosters``) with its best 1-for-1 and 2-for-1 (see the module
    docstring), best partner first; rosters with no trade that raises both lineups come last (``best`` None).
    ``want`` (Wave G, the API's partner finder): only packages in which every player I get plays that position
    (the search is the same, on fewer of their players; None = every package, the page's sweep).
    ``allow`` (IA-2, the sanity bound): called on a package that would be a roster's best; a reason sets it aside
    (appended to ``rejected`` as (package, reason)) and the search takes the next best. None: every package."""
    t0 = time.perf_counter()
    weeks = tuple(int(w) for w in (weeks or board.weeks))
    search = _Search(board, int(me), weeks, stats if stats is not None else {}, allow=allow,
                     rejected=rejected if rejected is not None else [], free=free)
    only = None if rosters is None else {int(r) for r in rosters}
    out = [partner(search, r, shapes, want) for r in board.rosters if r != int(me) and (only is None or r in only)]
    out.sort(key=lambda p: (p.best is None, p.best.order() if p.best is not None else (), p.roster_id))
    search.stats["seconds"] = time.perf_counter() - t0
    return out


def two_for_one_counts(board: RosterBoard, give: Sequence[str], get: Sequence[str], weeks: Sequence[int]) -> bool:
    """For a package moving two players one way: each of the two adds to the lineup of the team getting them
    (after it loses what it gives) in some week - re-solved with ``solve``, no bars (the exhaustive yardstick)."""
    give, get = _ids(give), _ids(get)
    pair, single = (give, get) if len(give) == 2 else (get, give)
    receiver = board.owner(single[0])
    for x in pair:
        gains = []
        for w in weeks:
            base = board.pool_with(receiver, w, _moving(board, single, w))
            with_x = board.pool_with(receiver, w, _moving(board, single, w), _moving(board, [x], w))
            gains.append(solve(with_x, board.slots, margins=False).total - solve(base, board.slots, margins=False).total)
        if not _useful(gains):
            return False
    return True


def partners_exhaustive(board: RosterBoard, me: int, *, weeks: Iterable[int] | None = None,
                        shapes: Sequence[str] = ("1-for-1", "2-for-1", "1-for-2"),
                        rosters: Iterable[int] | None = None) -> list[Partner]:
    """The yardstick for ``partners``: every package of every shape evaluated with ``package_gains``, no bound."""
    weeks = tuple(int(w) for w in (weeks or board.weeks))
    only = None if rosters is None else {int(r) for r in rosters}
    out = []
    for them in board.rosters:
        if them == int(me) or (only is not None and them not in only):
            continue
        mine, theirs = tradeable(board, me, weeks), tradeable(board, them, weeks)
        one = two = None
        if "1-for-1" in shapes:
            for a in mine:
                for b in theirs:
                    pk = package_gains(board, (a,), (b,), weeks)
                    if pk.mutual and (one is None or pk.order() < one.order()):
                        one = pk
        pk2 = []
        if "2-for-1" in shapes:
            pk2 += [((a1, a2), (b,)) for a1, a2 in combinations(mine, 2) for b in theirs]
        if "1-for-2" in shapes:
            pk2 += [((a,), (b1, b2)) for a in mine for b1, b2 in combinations(theirs, 2)]
        for give, get in pk2:
            pk = package_gains(board, give, get, weeks)
            if pk.mutual and (two is None or pk.order() < two.order()) and two_for_one_counts(board, give, get, weeks):
                two = pk
        out.append(Partner(int(them), one, two))
    out.sort(key=lambda p: (p.best is None, p.best.order() if p.best is not None else (), p.roster_id))
    return out


# ------------------------------------------------------------------------------ IA-2: the sanity bound on suggestions
# "Justin Jefferson for MarShawn Lloyd" must not be proposed: the lineup gain over a few weeks can hide a big loss of
# season value, and our projection can sit far under the market's for a star whose usage dipped. Two rules on a
# package the partner search would suggest (``partners(..., allow=...)``); the user's own trades are only flagged.
ROS_GAP_SHARE = 0.25      # (a) refuse when what you give is worth this share more rest of season than what you get
MARKET_SHARE = 0.65       # (b) refuse when our number for a player you give is under this share of Sleeper's


def sanity(give: Sequence[str], get: Sequence[str], *, ros: Mapping[str, float], ours: Mapping[str, float],
           market: Mapping[str, float], name: Callable[[str], str] = str,
           values: Mapping[str, float] | None = None) -> str | None:          # ---- IG-1: values
    """Why a package should not be suggested, or None. (b) the market: a player you give whose projection this week
    (``ours``) is under ``MARKET_SHARE`` of Sleeper's (``market``, the same week in the league's scoring) - the
    suggestion only works because our number is low; (a) the value gap (IG-1, Wave I-G): with ``values`` (season value
    above replacement, ``price_by_player``) the season value you give exceeds what comes back by more than
    ``ROS_GAP_SHARE`` of what you give and the two are not about even (``value_gap``); without it, the IA-2 rule on the
    raw rest-of-season points (``ros``: all positions added up - a volume gap, kept for callers that pass no values).
    A player with no number is not judged (unknown is not zero): (a) needs every player of the package."""
    for p in give:
        o, m = ours.get(p), market.get(p)
        if o is not None and m is not None and m > 0 and o < MARKET_SHARE * m:
            return f"the market disagrees with our number on {name(p)} (ours {o:.1f} this week, Sleeper's {m:.1f})"
    if values is not None:                                                    # ---- IG-1: the value rule
        return value_gap(give, get, values)
    if give and get and all(p in ros for p in (*give, *get)):
        out, inc = sum(float(ros[p]) for p in give), sum(float(ros[p]) for p in get)
        if out > 0 and out - inc > ROS_GAP_SHARE * out:
            return (f"you give {whole(out)} rest-of-season points for {whole(inc)}: {whole(out - inc)} more, over "
                    f"{round(ROS_GAP_SHARE * 100)}% of what you give")
    return None


# ------------------------------------------------------------------------------ words and ranks
def _s1(x: float) -> str:
    """One decimal with its sign, and no "-0.0" (a gain under 0.05 is shown as +0.0)."""
    return f"{x:+.1f}" if abs(x) >= 0.05 else "+0.0"


def fit_line(trade: Trade, span: str) -> str:
    """The fit (T-01): what both best lineups gain, this week and over ``span`` ("weeks 4–7"), one decimal - the
    numbers of the lineup headers."""
    m, t = trade.mine, trade.theirs
    return (f"**Fit** (what the best lineups gain): you **{_s1(m.gain_week)}** this week and **{_s1(m.gain_horizon)}** over "
            f"{span}; them **{_s1(t.gain_week)}** and **{_s1(t.gain_horizon)}**.")


def fairness_line(trade: Trade) -> str:
    """The fairness (T-01): the market score given and received, whole points - the sums of the market table's
    column. Players with no projection are named as not counted."""
    m = trade.mine
    po, pi = m.price_out or 0, m.price_in or 0
    gap = pi - po
    lean = ("about even" if about_even(po, pi) else f"you get {gap} more" if gap > 0 else f"you give {-gap} more")
    line = (f"**Market** (season points above the best free agent at the position): you give **{po}**, you get "
            f"**{pi}**: {lean}.")
    unknown = len(m.unknown_out) + len(m.unknown_in)
    if unknown:
        line += (f" {unknown} player{'s' if unknown > 1 else ''} in it {'have' if unknown > 1 else 'has'} no projection "
                 f"yet and {'are' if unknown > 1 else 'is'} not counted.")
    return line


def verdict(trade: Trade, span: str) -> str:
    """One sentence (T-02; words revised in Wave I-E after the casual-user review): whose starting lineup it helps,
    by how much, and what the season value says — never a guess at the other manager's answer (we cannot know how he
    rates his players). "Season value" is the projected season points above the best free agent at the position
    (``docs/WORDS.md`` § The dictionary: "projected value above available replacements")."""
    m, t = trade.mine, trade.theirs
    me_w, me_h, th_w, th_h = m.gain_week, m.gain_horizon, t.gain_week, t.gain_horizon
    po, pi = m.price_out or 0, m.price_in or 0
    mine_up, theirs_up = me_h >= MIN_GAIN, th_h >= MIN_GAIN
    even = about_even(po, pi)
    they_pay_more = not even and pi > po           # by season value they give up more than they get
    value = ("about even by season value" if even else
             "you give up more season value" if po > pi else "you get more season value")
    # ---- IH-2 (Wave I-H, unknown is not zero): a side with a player the season value cannot count (no season projection)
    # has no season-value sum — the lean would be a partial sum's. Say so and lean on nothing (team units count: IG-1).
    n_unknown = len(m.unknown_out) + len(m.unknown_in)
    if n_unknown:
        even, they_pay_more = True, False
        value = (f"season value not compared ({n_unknown} player{'s' if n_unknown > 1 else ''} in it "
                 f"{'have' if n_unknown > 1 else 'has'} no season projection)")
    # ---- end IH-2

    if abs(th_w) < 0.05 and abs(th_h) < 0.05:
        them = "no change for their lineup"
    elif theirs_up and th_w <= -0.05:
        them = f"them {_s1(th_h)} over {span} ({_s1(th_w)} this week)"
    elif theirs_up:
        them = f"them {_s1(th_w)} ({_s1(th_h)} over {span})"
    elif th_w <= 0:
        them = f"costs their lineup {abs(th_w):.1f} ({abs(th_h):.1f} over {span})"
    else:
        them = f"them {_s1(th_w)} but {_s1(th_h)} over {span}"
    if mine_up:
        head = (f"Helps your lineup {_s1(me_h)} over {span} ({_s1(me_w)} this week), {them}" if me_w <= -0.05
                else f"Helps your lineup {_s1(me_w)} this week ({_s1(me_h)} over {span}), {them}")
        if theirs_up:
            answer = "helps both lineups, and they give up the value" if they_pay_more else "helps both lineups"
        else:
            answer = ("a lineup loss for them; the value is on their side" if (po > pi and not even)
                      else "a lineup loss for them")
    else:
        head = f"Does not help your lineup ({_s1(me_w)} this week, {_s1(me_h)} over {span}), {them}"
        answer = ("not for your lineup; the value is on your side" if (pi > po and not even)
                  else "not worth it for your lineup")
    return f"{head}; {value}: {answer}."


def ranks(values: Mapping[int, float]) -> dict[int, int]:
    """rank() of each roster's value, 1 = highest; ties share a rank (like mart_league_roster_rankings)."""
    vals = {int(k): round(float(v), 2) for k, v in values.items() if v is not None}
    return {k: 1 + sum(1 for o in vals.values() if o > v) for k, v in vals.items()}


def rank_change(values: Mapping[int, float], after: Mapping[int, float]) -> dict[int, tuple[int, int]]:
    """{roster: (rank before, rank after)} when the rosters in ``after`` take their post-trade values."""
    before = ranks(values)
    new = ranks({**{int(k): v for k, v in values.items()}, **{int(k): v for k, v in after.items()}})
    return {k: (before[k], new[k]) for k in new if k in before}


def parse_ids(text: str | Sequence[str] | None) -> list[str]:
    """``?give=7547,96`` -> ['7547', '96'] (Sleeper ids; blanks and repeats dropped)."""
    if text is None:
        return []
    parts = text.split(",") if isinstance(text, str) else [x for t in text for x in str(t).split(",")]
    return list(dict.fromkeys(p.strip() for p in parts if p and p.strip()))


def clean_package(board: RosterBoard, me: int, them: int | None, give: Iterable[str], get: Iterable[str]) -> tuple[list[str], list[str], list[str]]:
    """Keep the ids of ``give`` on my roster and of ``get`` on theirs; returns (give, get, dropped ids)."""
    give, get = parse_ids(list(give)), parse_ids(list(get))
    g = [p for p in give if board.owner(p) == int(me)]
    t = [p for p in get if them is not None and board.owner(p) == int(them)]
    return g, t, [p for p in give if p not in g] + [p for p in get if p not in t]


# ---- IF-2 (Wave I-F, the decision-quality review § Priority 3): the value concepts, named and kept apart, and a
# package's gains week by week. The review: "you get more season value" next to "492 rest-of-season points for 164"
# described two concepts without naming them. Each number a trade shows belongs to exactly one of these; they are never
# added to one another. The fairness test is season value above replacement (``price_by_player``), never the raw totals.
VALUE_CONCEPTS = {
    "projected_points": "Projected points",                  # one player, one week: a line
    "starter_points": "Starter points",                      # what enters the best legal lineup, summed over the weeks
    "depth": "Backup coverage",                              # the bench's own best lineup this week (B1's bench_value)
    "season_value": "Season value above replacement",        # price_by_player: rest of season above the best free agent
    "ros_points": "Rest-of-season projected points",         # the raw totals, all positions added up: not a fairness test
}
ROS_NOT_FAIRNESS = "all positions added up — not a fairness test"


def package_weeks(board: RosterBoard, give: Sequence[str], get: Sequence[str],
                  weeks: Sequence[int]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """(mine, theirs): per week of ``weeks``, the change of each side's best lineup (``package_gains``' code — cuts
    included, no fill, no market); their sums are the package's horizon gains."""
    give, get = _ids(give), _ids(get)
    me, them = _owner(board, give, "give"), _owner(board, get, "get")
    a = _side(board, me, give, get, weeks, None, None, detail=False)
    b = _side(board, them, get, give, weeks, None, None, detail=False)
    return (tuple(_r2(x - y) for x, y in zip(a.after, a.before, strict=True)),
            tuple(_r2(x - y) for x, y in zip(b.after, b.before, strict=True)))


def season_value_line(price_out: int | None, price_in: int | None, n_give: int, n_get: int,
                      unknown: Sequence[str] = (), name: Callable[[str], str] = str) -> str:
    """The fairness test in words: season value above replacement given and received (whole points, each side's sum),
    the roster spots the package frees or uses (package size), and the players it cannot count (no season projection)."""
    po, pi = price_out or 0, price_in or 0
    lean = ("about even" if about_even(po, pi) else f"you get {pi - po} more" if pi > po else f"you give {po - pi} more")
    line = f"Season value above replacement: you give {po}, you get {pi} ({lean})."
    if n_get > n_give:
        k = n_get - n_give
        line += f" You get {n_get} players for {n_give}: {k} more roster spot{'s' if k > 1 else ''} used."
    elif n_give > n_get:
        k = n_give - n_get
        line += f" You give {n_give} players for {n_get}: {k} roster spot{'s' if k > 1 else ''} freed."
    if unknown:
        line += f" Not counted (no season projection): {', '.join(name(p) for p in unknown)}."
    return line
# ---- end IF-2


# ---- IG-1 (Wave I-G): the finder's rule (a) on SEASON VALUE ABOVE REPLACEMENT (the fairness test, ``price_by_player``),
# not on the raw rest-of-season totals (a volume gap: "Houston QB + Tuten for Rice" gave "493 rest-of-season points for
# 134" - two starters' volume, not their value over what the waiver wire holds). One rule for the finder (`partners`'
# allow) and the calculator's warning (`decisions.calc_sanity`).
def value_gap(give: Sequence[str], get: Sequence[str], values: Mapping[str, float]) -> str | None:
    """The value rule: the season value above replacement you give (each player rounded half up, as the tables show
    it) exceeds what comes back by more than ``ROS_GAP_SHARE`` of what you give, and the two are not ``about_even``
    (the verdict's fair price: within ``EVEN_POINTS`` / ``EVEN_SHARE`` - a warning never contradicts "about even by
    season value"). Every player of the package needs a value (unknown is not zero: not judged)."""
    if not give or not get or not all(p in values for p in (*give, *get)):
        return None
    po, pi = season_value(values, give)[0] or 0, season_value(values, get)[0] or 0
    if po > 0 and po - pi > ROS_GAP_SHARE * po and not about_even(po, pi):
        return (f"you give {po} season value above replacement for {pi}: {po - pi} more, over "
                f"{round(ROS_GAP_SHARE * 100)}% of what you give")
    return None
# ---- end IG-1


# ---- II-1 (Wave I-I, the product and analytics handoff § 2 "Make trade recommendations credible"): a suggestion is
# promoted only when it is legal, beats BOTH teams' realistic alternatives by a margin, and is a plausible offer.
# The review's case: "Folk -> Run Bijan Run for Stafford + Reichard", +19.4 for MacZaddy in one week because the engine
# priced a week with an empty kicker / QB slot at zero. Here a roster-week's lineup is valued with every EMPTY starting
# slot filled from that week's free pool (a one-week pickup — bye coverage is priced against the best free fill, never
# against zero), for both sides alike (`covered_side`); each side's gain is then compared with its OWN best alternative
# (the same function for both teams: `decisions.ii1_alternative`); the K / DEF guardrail is a rule from the league's
# slots and the free pool (`guard_positions`, `streamable_for_starter`), never a name; the value rule (a) is applied both
# ways. Words come from these numbers only; there is no acceptance probability anywhere (docs/METRICS.md § "Credible
# trades"). Numbers of `evaluate` / `partners` are unchanged: these are new fields beside them.
CREDIBLE_MARGIN = 1.0      # starter points over the window each side must gain beyond its own best alternative
CREDIBLE_MAX = 3           # the Finder promotes at most this many; the rest go behind "Explore alternatives"
NO_COMPELLING = "No compelling trade found"
PLAUSIBILITY = {"plausible": "Plausible offer", "roster_fit": "A roster-fit idea", "implausible": "Implausible"}


def _free_by_week(free_agents: Mapping[str, Mapping[int, Player | None]] | None,
                  weeks: Sequence[int]) -> dict[int, list[Player]]:
    """week -> the free agents who can play that week, best first (``best_fill``'s pool shape)."""
    out: dict[int, list[Player]] = {int(w): [] for w in weeks}
    for fid in sorted(free_agents or {}):
        for w, p in (free_agents[fid] or {}).items():
            if int(w) in out and _valued(p):
                out[int(w)].append(p)
    for w in out:
        out[w].sort(key=lambda p: (-float(p.value), p.id))
    return out


def fill_empty(pool: Sequence[Player], slots: Sequence[str], free: Sequence[Player],
               exclude: Iterable[str] = ()) -> tuple[float, tuple[str, ...]]:
    """(the best lineup's total with each EMPTY starting slot filled from ``free`` — one week's free agents, best first —,
    the ids of the free agents used). Only empty slots are filled: a free agent better than a rostered starter is a
    waiver move (the alternatives), not coverage. An empty slot no free agent can fill stays empty (0)."""
    lu, used = fill_lineup(pool, slots, free, exclude)
    return lu.total, used


def fill_lineup(pool: Sequence[Player], slots: Sequence[str], free: Sequence[Player],
                exclude: Iterable[str] = ()) -> tuple[Lineup, tuple[str, ...]]:
    """``fill_empty``'s lineup itself (IR-2: the explanations read its slots): (the best lineup with the empty starting
    slots filled from ``free``, the ids of the free agents in it)."""
    lu = solve(list(pool), slots, margins=False)
    gone = {str(x) for x in exclude} | {p.id for p in pool}
    used: list[str] = []
    cur = list(pool)
    for _ in range(len(lu.starts)):
        empties = [s for s in lu.starts if s.player is None]
        if not empties:
            break
        elig = frozenset().union(*(s.slot.elig for s in empties))
        pick = next((p for p in free if p.id not in gone and p.id not in used and p.positions & elig), None)
        if pick is None:
            break
        used.append(pick.id)
        cur.append(pick)
        nxt = solve(cur, slots, margins=False)
        if nxt.total <= lu.total + TOL:
            cur.pop()
            used.pop()
            break
        lu = nxt
    return lu, tuple(used)


@dataclass(frozen=True)
class Covered:
    """One side of a package, every roster-week valued with its empty starting slots filled from the free pool."""
    roster_id: int
    weeks: tuple[int, ...]
    before: tuple[float, ...]
    after: tuple[float, ...]
    fills_before: tuple[tuple[str, ...], ...]     # per week: the free agents that cover an empty slot
    fills_after: tuple[tuple[str, ...], ...]
    cuts: tuple[Cut, ...]
    starting: tuple[tuple[str, ...], ...] = ()    # per week: the incoming players who start after the trade
    empty_after: tuple[tuple[str, ...], ...] = ()  # per week: starting slots no rostered player fills after (uncovered)
    empty_before: tuple[tuple[str, ...], ...] = ()
    lineup_before: Lineup | None = None            # ---- IR-2: the first week's lineups, free-agent fills included
    lineup_after: Lineup | None = None

    @property
    def by_week(self) -> tuple[float, ...]:
        return tuple(_r2(a - b) for a, b in zip(self.after, self.before, strict=True))

    @property
    def gain_week(self) -> float:
        return self.by_week[0] if self.weeks else 0.0

    @property
    def gain_window(self) -> float:
        return _r2(sum(self.after) - sum(self.before))


def covered_side(board: RosterBoard, roster: int, out: Sequence[str], inc: Sequence[str], weeks: Sequence[int],
                 free: Mapping[int, Sequence[Player]], market: Mapping[str, float] | None = None, *,
                 taken_before: Sequence[Iterable[str]] | None = None,
                 taken_after: Sequence[Iterable[str]] | None = None) -> Covered:
    """Before / after per week for one roster (``evaluate``'s pools and cuts) with the empty slots covered.
    IR-2: ``taken_before`` / ``taken_after`` (per week) are free agents another roster already uses in the same state
    of the league (``covered_pair``): one free agent is never counted for two teams in the same week."""
    pools, lineups, cuts, _ = _after(board, roster, out, inc, weeks, market)
    before, after, fb, fa, st, em, eb = [], [], [], [], [], [], []
    lus: list[Lineup | None] = [None, None]
    incs = set(inc)
    for h, w in enumerate(weeks):
        fw = free.get(int(w), ())
        lb, ub = fill_lineup(board.pool(roster, w), board.slots, fw, taken_before[h] if taken_before else ())
        la, ua = fill_lineup(pools[h], board.slots, fw, taken_after[h] if taken_after else ())
        if h == 0:
            lus = [lb, la]
        before.append(lb.total)
        after.append(la.total)
        fb.append(ub)
        fa.append(ua)
        st.append(tuple(p for p in lineups[h].starter_ids if p in incs))
        em.append(tuple(lineups[h].empty_slots))
        eb.append(tuple(solve(board.pool(roster, w), board.slots, margins=False).empty_slots))
    return Covered(int(roster), tuple(int(w) for w in weeks), tuple(before), tuple(after), tuple(fb), tuple(fa), tuple(cuts),
                   tuple(st), tuple(em), tuple(eb), lus[0], lus[1])


# ---- IR-2 (Wave I-R, the dependability review's P0 1 and 2): one basis for the whole verdict, and explanations from the
# slots themselves. `covered_pair` prices both rosters of a package on the replacement frame with one free agent never
# counted for both teams in the same week (the roster earlier in the league's order fills first, in every state of the
# league, so the answer does not depend on whose side the calculator is read from); `slot_changes` lists, slot by slot,
# who starts there before and after (the after lineup re-seated to keep every player where he was when it can:
# `lineup._reseat`), so a sentence pairs the players of the same slot — and a FLEX cascade is a chain of slots — never
# the first incoming starter with the first outgoing one.
def covered_pair(board: RosterBoard, me: int, give: Sequence[str], get: Sequence[str], weeks: Sequence[int],
                 free: Mapping[int, Sequence[Player]], market: Mapping[str, float] | None = None) -> tuple[Covered, Covered]:
    """(my side, their side) on the replacement frame; ``give`` is ``me``'s, ``get`` the other roster's."""
    me = int(me)
    them = _owner(board, _ids(get), "get")
    order = sorted((me, them))
    sides: dict[int, Covered] = {}
    first = order[0]
    out1, in1 = (give, get) if first == me else (get, give)
    sides[first] = covered_side(board, first, out1, in1, weeks, free, market)
    c1 = sides[first]
    second = order[1]
    out2, in2 = (give, get) if second == me else (get, give)
    sides[second] = covered_side(board, second, out2, in2, weeks, free, market,
                                 taken_before=c1.fills_before, taken_after=c1.fills_after)
    return sides[me], sides[them]


def slot_changes(before: Lineup | None, after: Lineup | None, slots: Sequence[str]) -> list[dict]:
    """The starting slots whose player changes from ``before`` to ``after`` (one week's lineups of one roster), in chain
    order: [{slot, slot_type, in, out, in_from, out_to}] — ``in`` / ``out`` the player ids (None: the slot is empty
    after / was empty before), ``in_from`` the slot label the incoming player held before (None: he was not starting),
    ``out_to`` the slot the outgoing player holds after (None: he no longer starts). A chain starts where a player enters
    the lineup and follows the player he displaces from slot to slot."""
    from .lineup import _reseat, parse_slots
    if before is None or after is None:
        return []
    slot_list, _ = parse_slots(slots)
    by_label = {s.label: s for s in slot_list}
    seat_b = {s.player.id: s.slot.label for s in before.starts if s.player is not None}
    fixed = {s.player.id: s.slot.label for s in after.starts if s.player is not None and s.locked}
    seat_a = _reseat([s.player for s in after.starts if s.player is not None], slot_list, fixed, seat_b)
    occ_b = {lab: pid for pid, lab in seat_b.items()}
    occ_a = {lab: pid for pid, lab in seat_a.items()}
    changed = {}
    for s in slot_list:
        x, y = occ_a.get(s.label), occ_b.get(s.label)
        if x == y:
            continue
        changed[s.label] = {"slot": s.label, "slot_type": s.type, "in": x, "out": y,
                            "in_from": seat_b.get(x) if x is not None else None,
                            "out_to": seat_a.get(y) if y is not None else None}
    out: list[dict] = []
    seen: set[str] = set()
    heads = [lab for lab, c in changed.items() if c["in_from"] is None]
    for lab in [*heads, *[k for k in changed if k not in heads]]:
        cur = lab
        while cur is not None and cur in changed and cur not in seen:
            seen.add(cur)
            out.append(changed[cur])
            cur = changed[cur]["out_to"]
    for c in out:
        c["order"] = by_label[c["slot"]].order
    return out
# ---- end IR-2


def covered_move(board: RosterBoard, roster: int, add: Mapping[int, Player | None] | None, drop: str | None,
                 weeks: Sequence[int], free: Mapping[int, Sequence[Player]], add_id: str | None = None) -> tuple[float, ...]:
    """Per week: what a waiver move (add, maybe a drop) adds to the covered lineup — the alternative on the same frame
    as the trade (a claim that only covers a bye is worth what it adds over the free fill)."""
    out = []
    for w in weeks:
        fw = free.get(int(w), ())
        b, _ = fill_empty(board.pool(roster, w), board.slots, fw)
        remove = [drop] if drop and not board.is_locked(drop, w) else []
        pool = board.pool_with(roster, w, remove)
        p = (add or {}).get(int(w))
        if _valued(p):
            pool = [*pool, p]
        a, _ = fill_empty(pool, board.slots, fw, exclude=[add_id] if add_id else ())
        out.append(_r2(a - b))
    return tuple(out)


def flex_positions(slots: Sequence[str]) -> frozenset[str]:
    """The positions some multi-position starting slot of the league admits (FLEX, SUPER_FLEX, WR+TE ...)."""
    from .lineup import parse_slots
    out: set[str] = set()
    for s in parse_slots(slots)[0]:
        if len(s.elig) > 1:
            out |= set(s.elig)
    return frozenset(out)


def guard_positions(board: RosterBoard, weeks: Sequence[int], free: Mapping[int, Sequence[Player]]) -> dict[str, dict]:
    """The positions the free pool covers in THIS league (the K / DEF guardrail's, derived — never a name): a position
    that is not a skill position (QB / RB / WR / TE), fills only its own slot (no FLEX / SUPER_FLEX / IDP flex of the
    league admits it) and whose best free agent projects at least as much as the league's weakest starter at that slot,
    on average over the weeks: K and DEF (MFL's TMPK / TMDEF) in most leagues; a deep league whose free pool holds no
    starting-calibre kicker has none. {position: {free_best, weakest_starter, streamable}}."""
    from .lineup import parse_slots
    flex = flex_positions(board.slots)
    single = {next(iter(s.elig)) for s in parse_slots(board.slots)[0] if len(s.elig) == 1}
    out: dict[str, dict] = {}
    # the skill positions (and a team QB unit) are never guard positions: a RB for a WR is an ordinary trade even in a
    # league with no FLEX; their scarcity is in the replacement levels (prices) and the covered frame
    for pos in sorted(single - flex - SKILL - {"TMQB"}):
        fb, ws = [], []
        for w in weeks:
            best = next((float(p.value) for p in free.get(int(w), ()) if pos in p.positions), None)
            starters = []
            for r in board.rosters:
                lu = solve(board.pool(r, w), board.slots, margins=False)
                starters += [float(s.value) for s in lu.starts if s.player is not None and pos in s.slot.elig
                             and s.value is not None and s.player.value_source != UNVALUED]
            if best is not None:
                fb.append(best)
            if starters:
                ws.append(min(starters))
        f = sum(fb) / len(fb) if fb else None
        k = sum(ws) / len(ws) if ws else None
        out[pos] = {"free_best": None if f is None else _r2(f), "weakest_starter": None if k is None else _r2(k),
                    "streamable": f is not None and (k is None or f + TOL >= k)}
    return out


def _starts_for(board: RosterBoard, roster: int, pid: str, weeks: Sequence[int]) -> int:
    """In how many of the weeks he starts in his roster's best lineup."""
    n = 0
    for w in weeks:
        if pid in solve(board.pool(roster, w), board.slots, margins=False).starter_ids:
            n += 1
    return n


def streamable_for_starter(board: RosterBoard, give: Sequence[str], get: Sequence[str], weeks: Sequence[int],
                           guard: Mapping[str, Mapping], free: Mapping[int, Sequence[Player]],
                           name: Callable[[str], str] = str) -> dict | None:
    """The K / DEF guardrail: one side sends only players at positions the free pool covers (``guard_positions``) and
    the other sends a starter at another position (one who starts for them in at least half the weeks). Implausible
    unless the side receiving the kicker (defense …) has that slot EMPTY — nobody at the position in any week of the
    window (see the comment below for why "worse than the free pool" is not an exception). None when the rule does not
    apply or passes."""
    streamable = {p for p, g in guard.items() if g.get("streamable")}
    for xs, ys in ((tuple(give), tuple(get)), (tuple(get), tuple(give))):
        pos_x = {position_of(board, p) for p in xs}
        if not xs or not ys or None in pos_x or not pos_x <= streamable:
            continue
        y = board.owner(ys[0])
        starter = next((p for p in ys if position_of(board, p) not in pos_x
                        and 2 * _starts_for(board, y, p, weeks) >= len(weeks)), None)
        if starter is None:
            continue
        # their need at the position: nobody at it in any week of the window (a structural hole). II-1's decision: the
        # brief's second exception ("worse than the free pool") is not applied - the free pool's best kicker beats nearly
        # every rostered kicker by about a point (the best of ~20 near-equal projections), so it would let every kicker-
        # for-starter package through; a team whose kicker is worse than the free pool claims the free one, it does not
        # give a starter for one. A bye is not a need either: the free pool covers it and the covered frame prices it.
        need = False
        for pos in sorted(pos_x):
            has = False
            for w in weeks:
                lu = solve(board.pool(y, w), board.slots, margins=False)
                if any(s.player is not None and s.slot.elig == frozenset({pos}) for s in lu.starts):
                    has = True
                    break
            if not has:
                need = True
        if need:
            continue
        what = "/".join(sorted(pos_x))
        return {"rule": "streamable_for_starter", "positions": sorted(pos_x), "receiver": y, "starter": starter,
                "words": (f"a {what} for a starter ({name(starter)}): they have a {what} and the free pool holds one "
                          f"about as good, so a {what} is not worth a starter to them")}
    return None


def _one(x: float) -> str:
    return f"{x:+.1f}" if abs(x) >= 0.05 else "+0.0"


def plausibility(*, guard_hit: dict | None, their_value_gap: str | None, unpriced: Sequence[str],
                 no_market_line: Sequence[str]) -> dict:
    """{key, label, reasons}: implausible (a guardrail, or they give away much more season value than they get — rule (a)
    from their side), a roster-fit idea (a market input is missing: a player with no season value, or no market line),
    else a plausible offer. Never a probability."""
    if guard_hit is not None:
        return {"key": "implausible", "label": PLAUSIBILITY["implausible"], "reasons": [guard_hit["words"]]}
    if their_value_gap:
        return {"key": "implausible", "label": PLAUSIBILITY["implausible"], "reasons": [their_value_gap]}
    missing = [*unpriced, *[x for x in no_market_line if x not in unpriced]]
    if missing:
        return {"key": "roster_fit", "label": PLAUSIBILITY["roster_fit"],
                "reasons": [f"no market price for {', '.join(missing)}: this is how the rosters fit, not what the players "
                            f"would fetch"]}
    return {"key": "plausible", "label": PLAUSIBILITY["plausible"], "reasons": []}


def their_value_gap(give: Sequence[str], get: Sequence[str], values: Mapping[str, float]) -> str | None:
    """Rule (a) from the other side (the same rule, both teams): they give much more season value than they get."""
    why = value_gap(get, give, values)
    return None if why is None else why.replace("you give", "they give", 1)


def credible(beyond_mine: float | None, beyond_theirs: float | None, plaus: Mapping, legal: bool = True) -> bool:
    """The threshold: legal, both sides beyond their own best alternative by ``CREDIBLE_MARGIN``, and not implausible."""
    return (legal and beyond_mine is not None and beyond_theirs is not None and beyond_mine >= CREDIBLE_MARGIN
            and beyond_theirs >= CREDIBLE_MARGIN and plaus.get("key") != "implausible")
# ---- end II-1


__all__ = ["MARKET_SQL", "REPLACEMENT_SQL", "Cut", "Fill", "Package", "Partner", "Side", "Trade", "about_even", "best_fill",
           "clean_package", "evaluate", "fairness_line", "fit_line", "market_by_player", "package_gains", "parse_ids",
           "partners", "partners_exhaustive", "position_of", "price_by_player", "rank_change", "ranks", "roster_limit",
           "sanity", "season_value", "tradeable", "two_for_one_counts", "verdict", "whole",
           "VALUE_CONCEPTS", "package_weeks", "season_value_line",          # ---- IF-2
           "value_gap",                                                       # ---- IG-1
           "CREDIBLE_MARGIN", "CREDIBLE_MAX", "NO_COMPELLING", "PLAUSIBILITY", "Covered", "covered_move",  # ---- II-1
           "covered_side", "credible", "fill_empty", "flex_positions", "guard_positions", "plausibility",
           "streamable_for_starter", "their_value_gap"]


# ---- II-0 (Wave I-I, the fifth review § 1.6): one frame, one story. The partner card said "Nothing changes this week"
# beside a −1.5 in its own week strip: the sentence read one number (only a gain counted as a change) and the strip
# another. ``week_story`` builds the sentence from the very numbers the week-by-week table shows, so a loss is said as
# a loss and every number in the words is a number in the table (rounded the way the table rounds it: one decimal).
STORY_EPS = 0.05


def _story_kind(x: float | None) -> str:
    if x is None:
        return "unknown"
    return "none" if abs(x) < STORY_EPS else ("gain" if x > 0 else "loss")


def week_story(weeks, by_week, span: str | None, *, this_week: int | None = None) -> dict:
    """{this_week: {week, change, kind}, window: {change, kind}, by_week: [{week, change}], words} from one list of
    week-by-week changes to your starting lineup (``by_week[i]`` for ``weeks[i]``; None = not known). ``this_week``: the
    current week (the first entry is "this week" only when it is that week). kind: gain | loss | none | unknown."""
    ws = [int(w) for w in weeks]
    vals = [None if x is None else round(float(x), 2) for x in list(by_week)[:len(ws)]]
    vals += [None] * (len(ws) - len(vals))
    rows = [{"week": w, "change": v} for w, v in zip(ws, vals, strict=True)]
    first = rows[0] if rows and this_week is not None and rows[0]["week"] == int(this_week) else None
    known = [v for v in vals if v is not None]
    total = round(sum(known), 2) if known else None
    tw = {"week": None if first is None else first["week"], "change": None if first is None else first["change"],
          "kind": "unknown" if first is None else _story_kind(first["change"])}
    win = {"change": total, "kind": _story_kind(total)}
    when = f"over {span}" if span else "over these weeks"
    bits = []
    if first is not None:
        bits.append({"gain": f"Your lineup gains {first['change']:.1f} this week",
                     "loss": f"Your lineup loses {-first['change']:.1f} this week",
                     "none": "Nothing changes this week",
                     "unknown": "This week's change is not known"}[tw["kind"]])
    if len(rows) > 1 or first is None:
        lead = "" if first is not None else "Your lineup "
        bits.append(lead + {"gain": f"gains {total:.1f} {when} in total" if total is not None else "",
                            "loss": f"loses {-total:.1f} {when} in total" if total is not None else "",
                            "none": f"does not change {when} in total",
                            "unknown": f"has no known change {when}"}[win["kind"]])
    if first is not None and len(bits) == 2 and tw["kind"] == win["kind"] and tw["kind"] in ("gain", "loss"):
        bits[1] = bits[1].split(" ", 1)[1]                      # "gains 0.1 this week and 11.1 over weeks 4–7 in total"
        words = " and ".join(bits)
    elif first is not None and len(bits) == 2 and {tw["kind"], win["kind"]} == {"gain", "loss"}:
        words = " but ".join(bits)
    else:
        if first is not None and len(bits) == 2:
            bits[1] = "your lineup " + bits[1]
        words = "; ".join(b for b in bits if b)
    worst = min((r for r in rows[1:] if r["change"] is not None and r["change"] <= -STORY_EPS), key=lambda r: r["change"],
                default=None)
    if worst is not None and win["kind"] == "gain":
        words += f" (week {worst['week']} loses {-worst['change']:.1f})"
    return {"this_week": tw, "window": win, "by_week": rows, "words": (words + ".") if words else ""}


__all__ += ["week_story"]
# ---- end II-0

__all__ += ["covered_pair", "fill_lineup", "slot_changes"]          # ---- IR-2


# ---- IT-1 (Wave I-T): the best waiver move searched on the replacement frame itself. IF-1 / IF-2 choose the move on the
# roster-only numbers (a claim that fills a bye is worth its whole projection there) and the card re-prices it on the
# frame, where such a claim adds nothing the free fill did not. This searches the moves on the frame: each week's pool
# is the roster with its empty starting slots filled from that week's free pool (the fills stay in the pool), and an add
# is worth what it raises that lineup (`best_fill`'s exact entry bar). The moves tried: an open roster spot; else a drop —
# the bench player with the fewest rest-of-season points (a bench player costs no lineup points; an add that beats a
# starter sends that starter to the bench, so this covers "upgrade a starter"); a starter only when nobody sits on the
# bench (dropping a starter would let the free pool refill his slot every week: a second pickup, not one claim). Free
# agents used as a fill in any week are not candidates. Returns (add, drop | None, per-week gain) or None.
def basis_best_move(board: RosterBoard, roster: int, weeks: Sequence[int], free: Mapping[int, Sequence[Player]],
                    free_agents: Mapping[str, Mapping[int, Player | None]],
                    market: Mapping[str, float] | None = None, prices: Mapping[str, float] | None = None,
                    detail: dict | None = None,
                    only: tuple[str, str | None] | None = None) -> tuple[str, str | None, tuple[float, ...]] | None:
    """(add, drop | None, per-week gain on the frame) or None. IU-1: a drop is NETTED the way the roster-only move nets
    it (`waivers.choose_drops`: net = the move's gain − (the drop's cost − his lineup loss), the cost the most of its
    pieces): his lineup loss here is on the frame, his season value above replacement is ``prices`` (the same rule), his
    depth is `waivers.depth_lost` on the frame's weeks; his starts after the window and a role scenario's upside are not
    read here (None: not measured, as the waiver sweep treats a missing piece). Up to three bench players are tried (the
    fewest rest-of-season points first) and the cheapest net wins; ``detail`` (when given) receives the netting
    ({lineup_loss, season_value, depth_lost, cost, piece, excess, net_week, net_window}). ``only`` = (add, drop): that one
    move, netted the same way (another search's pick priced on this frame)."""
    from .waivers import depth_lost
    roster, weeks = int(roster), tuple(int(w) for w in weeks)
    if not weeks:
        return None

    def covered(remove: Sequence[str]) -> tuple[list[list[Player]], list[float], set[str]]:
        pools, totals, used = [], [], set()
        for w in weeks:
            ps = board.pool_with(roster, w, [d for d in remove if not board.is_locked(d, w)])
            fw = free.get(w, ())
            lu, ids = fill_lineup(ps, board.slots, fw)
            fills = [q for q in fw if q.id in set(ids)]
            pools.append([*ps, *fills])
            totals.append(lu.total)
            used |= set(ids)
        return pools, totals, used

    base_pools, base_totals, used = covered(())
    cands = {k: v for k, v in (free_agents or {}).items() if k not in used and board.owner(k) is None}
    if only is not None:
        cands = {k: v for k, v in cands.items() if k == str(only[0])}
    if not cands:
        return None
    best: tuple[tuple, str, str | None, tuple[float, ...], dict] | None = None

    def consider(pools, loss, drop):
        nonlocal best
        f = best_fill(board, weeks, pools, cands)
        if f is None:
            return
        by = tuple(_r2(g - x) for g, x in zip(f.week_gains, loss, strict=True))
        net = {"lineup_loss": _r2(sum(loss)), "season_value": None, "depth_lost": None, "cost": 0.0, "piece": None,
               "excess": 0.0}
        if drop is not None:
            pos = position_of(board, drop)
            vals, sits, n_at, bf = [], [], [], []
            for w, ps in zip(weeks, base_pools, strict=True):
                lu = solve(ps, board.slots, margins=False)
                me = next((q for q in ps if q.id == drop), None)
                vals.append(me.value if me is not None and me.playable and me.value_source != UNVALUED else None)
                sits.append(me is not None and me.playable and drop not in set(lu.starter_ids))
                n_at.append(sum(1 for st in lu.starts if st.player is not None and st.player.position == pos))
                bf.append(next((float(q.value) for q in free.get(w, ()) if pos in q.positions), None))
            depth = _r2(depth_lost(vals, bf, sits, pos, n_at))
            season = None if prices is None or drop not in prices else _r2(float(prices[drop]))
            pieces = {"lineup_loss": max(0.0, net["lineup_loss"]), "season_value": season, "depth_lost": depth}
            cost = max(v for v in pieces.values() if v is not None)
            net.update(season_value=season, depth_lost=depth, cost=_r2(cost),
                       piece=None if cost <= 0 else next(k for k, v in pieces.items() if v is not None and _r2(v) == _r2(cost)),
                       excess=_r2(cost - max(0.0, net["lineup_loss"])))
        net["net_week"] = _r2(by[0] - net["excess"])
        net["net_window"] = _r2(sum(by) - net["excess"])
        k = (net["net_window"], net["net_week"])
        if best is None or k > best[0]:
            best = (k, f.player_id, drop, by, net)

    if only is not None:
        d = None if only[1] is None else str(only[1])
        if d is None:
            consider(base_pools, [0.0] * len(weeks), None)
        else:
            pools, totals, _ = covered([d])
            consider(pools, [b - a for b, a in zip(base_totals, totals, strict=True)], d)
    elif roster_limit(board.slots) - board.active_count(roster) > 0:
        consider(base_pools, [0.0] * len(weeks), None)
    else:
        stay = [p for p in board.roster(roster) if board.is_active(p) and not board.is_locked(p, weeks[0])]
        starts = set()
        for w in weeks:
            starts |= set(solve(board.pool(roster, w), board.slots, margins=False).starter_ids)

        def mkt(p: str) -> float:
            v = (market or {}).get(p)
            return math.inf if v is None else float(v)
        bench = sorted((p for p in stay if p not in starts), key=lambda p: (mkt(p), p))[:3]
        starters = [] if bench else sorted((p for p in stay if p in starts), key=lambda p: (mkt(p), p))[:1]
        for d in [*bench, *starters]:
            pools, totals, _ = covered([d])
            consider(pools, [b - a for b, a in zip(base_totals, totals, strict=True)], d)
    if best is None or (only is None and best[0][0] < MIN_GAIN):
        return None
    if detail is not None:
        detail.update(best[4])
    return best[1], best[2], best[3]
# ---- end IT-1

__all__ += ["basis_best_move"]                                       # ---- IT-1


# ---- IU-1 (Wave I-U): the partner search on the replacement frame. With ``free`` (week -> that week's free agents, best
# first: `_free_by_week`), `partners` proposes and bounds every package on the frame the verdict judges it on: each
# roster-week's pool carries the free agents that fill its empty starting slots (`_covered_pool`), so an entry bar, a
# loss and a package's exact gains (`package_gains_covered`: `covered_pair`, one free agent never counted for both
# teams) are the basis's. The bounds ignore that exclusivity (it only moves the second roster's fills); the exact gains
# do not. Without ``free`` the search is the roster-only one, unchanged.
def _covered_pool(pool: Sequence[Player], slots: Sequence[str], free_week: Sequence[Player]) -> list[Player]:
    """The pool with the free agents `fill_lineup` puts in its empty starting slots."""
    _, ids = fill_lineup(pool, slots, free_week)
    if not ids:
        return list(pool)
    used = set(ids)
    return [*pool, *[q for q in free_week if q.id in used]]


def package_gains_covered(board: RosterBoard, give: Sequence[str], get: Sequence[str], weeks: Sequence[int],
                          free: Mapping[int, Sequence[Player]]) -> Package:
    """`package_gains` on the replacement frame (cuts included, no market)."""
    give, get = _ids(give), _ids(get)
    me = _owner(board, give, "give")
    a, b = covered_pair(board, me, give, get, weeks, free)
    return Package(_owner(board, get, "get"), give, get, a.gain_week, a.gain_window, b.gain_week, b.gain_window)


__all__ += ["package_gains_covered"]                                         # ---- IU-1

