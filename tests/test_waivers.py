"""B3 waiver engine: the move evaluator on synthetic rosters (no database), the pruning rule against
the unpruned sweep and against brute force, the ranking, and the DDL / fingerprint copies."""

import random
import re
from pathlib import Path

import pytest

from league_lab import db, waivers
from league_lab.lineup import Player, solve
from league_lab.waivers import (
    MOVE_COLUMNS,
    entry_bar,
    guard,
    prepare,
    rank_moves,
    roster_moves,
    roster_moves_unpruned,
)

ROOT = Path(__file__).resolve().parents[1]
SCRUBS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN", "BN", "BN", "BN", "BN"]
DYNASTY = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", *["BN"] * 13]
SMALL = ["QB", "RB", "WR", "TE", "FLEX", "BN", "BN"]


def P(pid: str, pos: str, value: float | None, **kw) -> Player:
    return Player(id=pid, position=pos, value=value, value_source=kw.pop("value_source", "proj_points"), **kw)


def four(players: list[Player]) -> list[list[Player]]:
    return [list(players) for _ in range(4)]


def by_pair(moves) -> dict:
    return {(m.add, m.drop): m for m in moves}


# ------------------------------------------------------------------------------ the evaluator
def test_gain_from_filling_an_empty_slot():
    """No TE on the roster: a TE free agent fills the empty slot and gains his whole value, every week."""
    roster = [P("qb", "QB", 20.0), P("rb", "RB", 15.0), P("wr", "WR", 12.0), P("wr2", "WR", 9.0)]
    moves = by_pair(roster_moves(SMALL, four(roster), {"te": [P("te", "TE", 6.0)] * 4}, droppable=["wr2"], open_spot=True))
    m = moves[("te", None)]                                   # an open roster spot: no drop needed
    assert (m.weekly_gain, m.horizon_gain) == pytest.approx((6.0, 24.0))
    assert (m.add_slot, m.displaced) == ("TE", None)          # fills an empty slot: nobody is displaced
    assert m.lineup_after == pytest.approx(solve(roster + [P("te", "TE", 6.0)], SMALL).total)
    # dropping the FLEX WR to make room would cost his 9 a week for the TE's 6: a loss, so not a move
    assert ("te", "wr2") not in moves


def test_gain_from_beating_a_starter_names_the_displaced_starter():
    roster = [P("qb", "QB", 20.0), P("rb1", "RB", 15.0), P("rb2", "RB", 9.0), P("wr", "WR", 12.0),
              P("te", "TE", 7.0), P("bn", "RB", 5.0), P("bn2", "WR", 4.0)]
    before = solve(roster, SMALL)
    assert before.lineup["FLEX"][0].id == "rb2"
    moves = by_pair(roster_moves(SMALL, four(roster), {"fa": [P("fa", "WR", 11.0)] * 4}, droppable=["bn", "bn2"],
                                 open_spot=False))
    assert set(moves) == {("fa", "bn"), ("fa", "bn2")}        # full roster: a drop is required
    m = moves[("fa", "bn")]
    assert (m.weekly_gain, m.horizon_gain) == pytest.approx((2.0, 8.0))   # 11 over the FLEX RB's 9
    assert (m.add_slot, m.displaced) == ("FLEX", "rb2")
    assert m.lineup_before == pytest.approx(before.total) and m.lineup_after == pytest.approx(before.total + 2.0)


def test_no_gain_when_the_add_is_worse_than_the_bench():
    roster = [P("qb", "QB", 20.0), P("rb1", "RB", 15.0), P("rb2", "RB", 9.0), P("wr", "WR", 12.0),
              P("te", "TE", 7.0), P("bn", "RB", 5.0), P("bn2", "WR", 4.0)]
    adds = {"worse": [P("worse", "RB", 4.5)] * 4,              # worse than the bench RB
            "between": [P("between", "WR", 8.9)] * 4,          # better than the bench, worse than every starter he can play
            "tie": [P("tie", "RB", 9.0)] * 4}                  # equal to the FLEX RB: no gain either
    stats = {}
    assert roster_moves(SMALL, four(roster), adds, droppable=["bn", "bn2"], open_spot=True, stats=stats) == []
    assert stats["survivors"] == 0                             # all three fail the bar: nothing is paired
    assert roster_moves_unpruned(SMALL, four(roster), adds, droppable=["bn", "bn2"], open_spot=True) == []


def test_the_drops_horizon_value_is_counted():
    """The backup TE starts in week 3 (the TE1 is on bye there). A WR free agent beats the FLEX RB by 2
    every week. Dropping the WR who never starts costs nothing; dropping the backup TE leaves the TE
    slot empty in week 3, and the move is charged his 5 points there."""
    base = [P("qb", "QB", 20.0), P("rb", "RB", 15.0), P("wr", "WR", 12.0), P("te1", "TE", 8.0),
            P("fx", "RB", 9.0), P("te2", "TE", 5.0), P("bn2", "WR", 1.0)]
    weeks = four(base)
    weeks[2] = [replace_player(p, playable=False, reason="bye") if p.id == "te1" else p for p in base]
    add = {"fa": [P("fa", "WR", 11.0)] * 4}
    moves = by_pair(roster_moves(SMALL, weeks, add, droppable=["te2", "bn2"], open_spot=False))
    free, costly = moves[("fa", "bn2")], moves[("fa", "te2")]
    assert free.week_gains == pytest.approx((2.0, 2.0, 2.0, 2.0)) and sum(free.drop_loss) == pytest.approx(0.0)
    assert costly.week_gains == pytest.approx((2.0, 2.0, -3.0, 2.0))   # week 3: +2 at FLEX, -5 at TE
    assert costly.drop_loss == pytest.approx((0.0, 0.0, 5.0, 0.0))
    assert (free.horizon_gain, costly.horizon_gain) == pytest.approx((8.0, 3.0))
    ranked = rank_moves(list(moves.values()), {"te2": 1.0, "bn2": 40.0})   # even when the TE projects less
    assert (ranked[0][0].drop, ranked[0][2], ranked[0][3]) == ("bn2", True, 1)
    assert (ranked[1][0].drop, ranked[1][2], ranked[1][3]) == ("te2", False, None)


def test_locked_starter_is_not_displaced():
    """The TE's game has kicked off (locked in the TE slot): a better TE cannot take his slot this
    week; from next week he can, so the move is a cover, not a start-now."""
    slots = ["QB", "TE", "BN", "BN"]
    week0 = [P("qb", "QB", 20.0), P("te", "TE", 5.0, locked_slot="TE"), P("bn", "QB", 3.0)]
    later = [P("qb", "QB", 20.0), P("te", "TE", 5.0), P("bn", "QB", 3.0)]
    moves = by_pair(roster_moves(slots, [week0, later, later, later], {"fa": [P("fa", "TE", 9.0)] * 4},
                                 droppable=["bn"], open_spot=False))
    m = moves[("fa", "bn")]
    assert m.week_gains == pytest.approx((0.0, 4.0, 4.0, 4.0))
    assert waivers.list_kind(m) == "cover" and m.add_slot is None and m.displaced is None
    ref = by_pair(roster_moves_unpruned(slots, [week0, later, later, later], {"fa": [P("fa", "TE", 9.0)] * 4},
                                        droppable=["bn"], open_spot=False))
    assert ref[("fa", "bn")].key() == m.key()


def test_a_free_agent_who_cannot_play_this_week_can_still_cover_later():
    roster = [P("qb", "QB", 20.0), P("rb", "RB", 10.0), P("wr", "WR", 10.0), P("te", "TE", 4.0), P("bn", "WR", 2.0),
              P("bn2", "RB", 1.0)]
    fa = [P("fa", "TE", 8.0, playable=False, reason="bye"), P("fa", "TE", 8.0), None, P("fa", "TE", 8.0)]
    m = by_pair(roster_moves(SMALL, four(roster), {"fa": fa}, droppable=["bn2"], open_spot=False))[("fa", "bn2")]
    # weeks 2 and 4: he takes the TE slot, the TE moves to FLEX over the WR worth 2: +4 +2
    assert m.week_gains == pytest.approx((0.0, 6.0, 0.0, 6.0))
    assert waivers.list_kind(m) == "cover" and m.add_slot is None


def test_open_spot_and_full_roster():
    roster = [P("qb", "QB", 20.0), P("rb", "RB", 10.0)]
    add = {"wr": [P("wr", "WR", 7.0)] * 4}
    assert [m.drop for m in roster_moves(SMALL, four(roster), add, droppable=[], open_spot=True)] == [None]
    assert roster_moves(SMALL, four(roster), add, droppable=[], open_spot=False) == []   # full, nothing droppable


def test_unknown_is_not_zero_for_drops_or_displacements():
    """A K with no value yet starts at 0 (B1): a valued free-agent K is not credited with replacing
    him, and a player with no value yet is never suggested as a drop."""
    slots = ["QB", "K", "BN", "BN"]
    roster = [P("qb", "QB", 20.0), P("k", "K", None, value_source="unvalued"), P("bn", "QB", 3.0),
              P("x", "RB", None, value_source="unvalued")]
    shielded, droppable = guard(slots, four(roster), ["bn", "x", "k"])
    assert droppable == ["bn"]
    assert next(p for p in shielded[0] if p.id == "k").locked_slot == "K"
    assert roster_moves(slots, four(roster), {"fa": [P("fa", "K", 9.0, value_source="season_ppg")] * 4},
                        droppable=["bn", "x", "k"], open_spot=False) == []


def test_negative_or_unvalued_free_agents_gain_nothing():
    roster = [P("qb", "QB", 20.0)]
    adds = {"neg": [P("neg", "RB", -1.0)] * 4, "unv": [P("unv", "RB", None, value_source="unvalued")] * 4}
    assert roster_moves(SMALL, four(roster), adds, droppable=[], open_spot=True) == []


# ------------------------------------------------------------------------------ the pruning rule
def replace_player(p: Player, **kw) -> Player:
    from dataclasses import replace
    return replace(p, **kw)


def _random_roster(rng: random.Random, slots: list[str], n: int, prefix: str = "r") -> list[Player]:
    pos = ["QB", "RB", "WR", "TE"] + (["K", "DEF"] if "K" in slots else [])
    out = []
    for i in range(n):
        pid = f"{prefix}{i}"
        roll = rng.random()
        if roll < 0.08:
            out.append(P(pid, rng.choice(pos), rng.uniform(0, 20), playable=False, reason="bye"))
        elif roll < 0.12:
            out.append(P(pid, rng.choice(pos), None, value_source="unvalued"))
        elif roll < 0.16 and pos:
            p = rng.choice(["QB", "RB", "WR", "TE"])
            out.append(P(pid, p, round(rng.uniform(0, 20), 2), locked_slot=p if p in slots else None))
        else:
            out.append(P(pid, rng.choice(pos), round(rng.uniform(0, 20), 2)))
    return out


@pytest.mark.parametrize("seed", range(24))
def test_pruned_equals_unpruned_on_random_rosters(seed):
    rng = random.Random(seed)
    slots = [SCRUBS, DYNASTY, SMALL, ["QB", "RB", "WR", "TE", "REC_FLEX", "WRRB_FLEX", "SUPER_FLEX", "BN", "BN"]][seed % 4]
    base = _random_roster(rng, slots, rng.randint(6, 12))
    weeks = [base]
    for _h in range(3):   # later weeks: the same players, nobody locked, values moved a little, some on bye
        wk = []
        for p in base:
            q = replace_player(p, locked_slot=None)
            if q.value is not None and q.value_source != "unvalued":
                q = replace_player(q, value=round(q.value + rng.uniform(-3, 3), 2))
            if rng.random() < 0.1:
                q = replace_player(q, playable=False, reason="bye")
            wk.append(q)
        weeks.append(wk)
    fas = {}
    for j in range(7):
        pos = rng.choice(["QB", "RB", "WR", "TE"] + (["K"] if "K" in slots else []))
        seq = []
        for _h in range(4):
            r = rng.random()
            seq.append(None if r < 0.1 else P(f"f{j}", pos, round(rng.uniform(0, 22), 2), playable=r > 0.2,
                                              reason=None if r > 0.2 else "Out"))
        fas[f"f{j}"] = seq
    droppable = [p.id for p in base if p.locked_slot is None]
    open_spot = seed % 3 == 0
    fast = roster_moves(slots, weeks, fas, droppable, open_spot)
    ref = roster_moves_unpruned(slots, weeks, fas, droppable, open_spot)
    assert sorted(m.key() for m in fast) == sorted(m.key() for m in ref)
    # the seat may differ only between equally good lineups: same total either way
    for m in fast:
        r = next(x for x in ref if (x.add, x.drop) == (m.add, m.drop))
        assert m.lineup_after == pytest.approx(r.lineup_after)


@pytest.mark.parametrize("seed", range(40))
def test_entry_bar_is_the_exact_price_of_entry(seed):
    """gain(add) = max(0, value - bar) for every value, checked against solve() on the roster + add."""
    rng = random.Random(1000 + seed)
    slots = [SCRUBS, DYNASTY, SMALL][seed % 3]
    roster = _random_roster(rng, slots, rng.randint(3, 14))
    w = prepare(roster, slots)
    for pos in ("QB", "RB", "WR", "TE"):
        bar = entry_bar(w, frozenset({pos}))
        for v in (0.5, 4.0, 9.0, 15.0, 25.0):
            gain = solve(roster + [P("fa", pos, v)], slots).total - solve(roster, slots).total
            expect = 0.0 if bar is None else max(0.0, v - bar)
            assert gain == pytest.approx(expect, abs=1e-6), (pos, v, bar)


def test_the_pruning_keeps_only_free_agents_past_the_bar():
    roster = [P("qb", "QB", 20.0), P("rb", "RB", 10.0), P("wr", "WR", 10.0), P("te", "TE", 6.0),
              P("fx", "RB", 8.0), P("bn", "WR", 3.0), P("bn2", "RB", 2.0)]
    w = prepare(roster, SMALL)
    assert entry_bar(w, frozenset({"TE"})) == pytest.approx(6.0)     # beat the TE
    assert entry_bar(w, frozenset({"WR"})) == pytest.approx(8.0)     # beat the FLEX RB (the cheapest seat he can take)
    assert entry_bar(w, frozenset({"K"})) is None                    # no K slot in this league
    stats = {}
    roster_moves(SMALL, four(roster), {"a": [P("a", "TE", 6.0)] * 4, "b": [P("b", "WR", 8.5)] * 4,
                                       "c": [P("c", "RB", 7.9)] * 4}, droppable=["bn", "bn2"], open_spot=False, stats=stats)
    assert (stats["adds"], stats["survivors"]) == (3, 1)


# ------------------------------------------------------------------------------ ranking
def test_rank_prefers_horizon_then_week_then_no_drop_then_the_least_useful_drop():
    mk = lambda a, d, g: waivers.MoveResult(a, d, g, g, (0.0,) * len(g), 100.0, 100.0 + g[0], None, None, None)  # noqa: E731
    moves = [mk("x", "d1", (1.0, 1.0)), mk("x", "d2", (1.0, 1.0)), mk("x", None, (1.0, 1.0)),
             mk("y", "d1", (0.0, 3.0)), mk("z", "d2", (2.0, 0.0))]
    ranked = rank_moves(moves, {"d1": 50.0, "d2": 10.0})
    order = [(m.add, m.drop) for m, *_ in ranked]
    assert order == [("y", "d1"), ("z", "d2"), ("x", None), ("x", "d2"), ("x", "d1")]
    assert [(r, best, ar) for _, r, best, ar in ranked] == [(1, True, 1), (2, True, 2), (3, True, 3), (4, False, None), (5, False, None)]


# ------------------------------------------------------------------------------ copies agree
def _ddl_columns(text: str) -> list[str]:
    body = re.search(r"create table if not exists ops\.waiver_moves \((.*?)\)\s*(;|\"|,|$)", text, re.S).group(1)
    return [part.split()[0] for part in body.replace("\n", " ").split(",")]


def test_waiver_ddl_is_the_same_everywhere():
    cols = _ddl_columns(db.OPS_DDL)
    assert cols == _ddl_columns(waivers.DDL["ops.waiver_moves"])
    assert cols == _ddl_columns((ROOT / "dbt/models/marts/edge/mart_waiver_moves.sql").read_text())
    assert cols == MOVE_COLUMNS


def _norm_sql(s: str) -> str:
    s = re.sub(r"\{\{\s*ref\('([a-z_]+)'\)\s*\}\}", r"analytics.\1", s)
    return re.sub(r"\s+", " ", s).strip()


def test_fingerprint_sql_is_the_same_in_python_and_the_mart():
    mart = (ROOT / "dbt/models/marts/edge/mart_waiver_moves.sql").read_text()
    body = re.search(r"fp as \(\n(.*?)\n\)\n", mart, re.S).group(1)
    assert _norm_sql(body) == _norm_sql(waivers.FINGERPRINT_SQL)

