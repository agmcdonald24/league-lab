"""Wave I-R, IR-2 — the trade engine's part of one verdict (no database): `covered_pair` (both rosters on the
replacement frame, one free agent never counted for both teams, the same numbers whichever side asks), `slot_changes`
(the players of the same slot paired, a FLEX cascade a chain of slots) and `fill_lineup` (the lineup `fill_empty`
totals)."""

from league_lab.lineup import Player, solve
from league_lab.roster_value import RosterBoard
from league_lab.trades import (
    _free_by_week,
    covered_pair,
    covered_side,
    fill_empty,
    fill_lineup,
    slot_changes,
)

from .test_trades import P, U, rows_for

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "BN", "BN", "BN", "BN"]
A = [P("aqb", "QB", 20), P("arb1", "RB", 15), P("arb2", "RB", 12), P("arb3", "RB", 11), P("awr1", "WR", 16),
     P("awr2", "WR", 14), P("ate", "TE", 9), P("ak", "K", 8), P("awr3", "WR", 5)]
B = [P("bqb", "QB", 18), P("brb1", "RB", 16), P("brb2", "RB", 13), P("bwr1", "WR", 13), P("bwr2", "WR", 12),
     P("bte", "TE", 7), P("brb3", "RB", 10), P("bk", "K", 8.5), P("bwr3", "WR", 4)]
FREE = [P("fk1", "K", 9.0), P("fk2", "K", 6.0), P("fwr", "WR", 6.0)]


def board(a6, b6) -> RosterBoard:
    rows = rows_for(1, 5, A, SLOTS) + rows_for(2, 5, B, SLOTS)
    rows += rows_for(1, 6, [p for p in A if p.id not in {x.id for x in a6}], SLOTS, a6)
    rows += rows_for(2, 6, [p for p in B if p.id not in {x.id for x in b6}], SLOTS, b6)
    return RosterBoard(rows, SLOTS)


def pool() -> dict[str, dict[int, Player]]:
    return {p.id: {5: p, 6: p} for p in FREE}


def test_fill_lineup_is_fill_empty():
    ps = [p for p in A if p.id != "ak"]
    fr = sorted(FREE, key=lambda p: -p.value)
    lu, used = fill_lineup(ps, SLOTS, fr)
    assert (lu.total, used) == fill_empty(ps, SLOTS, fr) and used == ("fk1",)
    assert "fk1" in lu.starter_ids


def test_one_free_agent_never_counted_for_both_teams_and_the_same_answer_from_either_side():
    b = board([U("ak", "K", None, "bye")], [U("bk", "K", None, "bye")])
    free = _free_by_week(pool(), (5, 6))
    m, t = covered_pair(b, 1, ["awr3"], ["bwr3"], (5, 6), free)
    for st in ("fills_before", "fills_after"):
        assert set(getattr(m, st)[1]).isdisjoint(getattr(t, st)[1])
    # without the rule both sides would take the 9-point kicker
    alone = covered_side(b, 2, ["bwr3"], ["awr3"], (5, 6), free)
    assert alone.fills_before[1] == ("fk1",) and t.fills_before[1] == ("fk2",)
    m2, t2 = covered_pair(b, 2, ["bwr3"], ["awr3"], (5, 6), free)
    assert (m.before, m.after, m.by_week) == (t2.before, t2.after, t2.by_week)
    assert (t.before, t.after, t.by_week) == (m2.before, m2.after, m2.by_week)
    assert m.lineup_before is not None and m.lineup_after is not None       # the first week's lineups, fills included


def test_slot_changes_pair_the_same_slot_and_follow_the_flex_chain():
    before = solve(A, SLOTS, margins=False)
    after = solve([p for p in A if p.id != "arb1"] + [P("bwr1", "WR", 13)], SLOTS, margins=False)
    ch = slot_changes(before, after, SLOTS)
    assert [(c["slot_type"], c["in"], c["out"], c["in_from"], c["out_to"]) for c in ch] == [
        ("FLEX", "bwr1", "arb3", None, ch[1]["slot"]),
        ("RB", "arb3", "arb1", "FLEX", None)]
    # a kicker for a kicker is the K slot, whatever else changes
    after_k = solve([p for p in A if p.id not in ("ak", "arb1")] + [P("bk", "K", 8.5), P("bwr1", "WR", 13)], SLOTS,
                    margins=False)
    k = next(c for c in slot_changes(before, after_k, SLOTS) if c["slot_type"] == "K")
    assert (k["in"], k["out"]) == ("bk", "ak")


def test_a_slot_renumbering_is_not_a_change():
    before = solve(A, SLOTS, margins=False)
    after = solve(list(reversed(A)), SLOTS, margins=False)
    assert slot_changes(before, after, SLOTS) == []
