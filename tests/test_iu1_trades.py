"""Wave I-U, IU-1 — the partner search on the replacement frame, and the basis waiver move's drop netted. No database.

My quarterback is on a bye in week 5 with no backup: on the roster-only numbers their backup quarterback fills an empty
QB slot (his whole projection is my gain); on the replacement frame the free quarterback already covers that week, so
the package is worth only what their quarterback adds over him. The search proposes and bounds on the frame
(`partners(..., free=…)`), and its best package is the one an exhaustive pass on the frame finds."""

import pytest

from league_lab.roster_value import RosterBoard
from league_lab.trades import (
    _free_by_week,
    _Search,
    basis_best_move,
    covered_move,
    package_gains,
    package_gains_covered,
    partners,
    tradeable,
)

from . import test_it1_trades as IT1
from .test_trades import P, U, rows_for

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN", "BN"]
ME = [P("mqb", "QB", 20.0), P("mrb1", "RB", 15.0), P("mrb2", "RB", 7.0), P("mwr1", "WR", 18.0), P("mwr2", "WR", 16.0),
      P("mwr3", "WR", 14.0), P("mwr4", "WR", 12.0), P("mte", "TE", 9.0), P("mrb3", "RB", 3.0)]
THEM = [P("tqb", "QB", 19.0), P("tqb2", "QB", 15.0), P("trb1", "RB", 17.0), P("trb2", "RB", 14.0), P("trb3", "RB", 13.0),
        P("twr1", "WR", 15.0), P("twr2", "WR", 6.0), P("tte", "TE", 8.0), P("twr3", "WR", 2.0)]
FREE = [P("fqb", "QB", 14.0), P("frb", "RB", 5.0), P("fwr", "WR", 5.0), P("fte", "TE", 4.0)]
WEEKS = (5, 6)


def board() -> RosterBoard:
    rows = rows_for(1, 5, [p for p in ME if p.id != "mqb"], SLOTS, [U("mqb", "QB", None, "bye")])
    rows += rows_for(1, 6, ME, SLOTS)
    for w in WEEKS:
        rows += rows_for(2, w, THEM, SLOTS)
    return RosterBoard(rows, SLOTS)


def free():
    return _free_by_week({p.id: {w: p for w in WEEKS} for p in FREE}, WEEKS)


def test_the_bye_cover_is_worth_what_it_adds_over_the_free_quarterback():
    b = board()
    raw = package_gains(b, ("mwr4",), ("tqb2",), WEEKS)
    cov = _Search(b, 1, WEEKS, free=free()).evaluate(("mwr4",), ("tqb2",))
    assert raw.my_horizon == pytest.approx(15.0)          # an empty QB slot in week 5 priced at zero
    assert cov.my_horizon == pytest.approx(1.0)           # 15 over the free 14
    assert cov.their_horizon == raw.their_horizon == pytest.approx(12.0)    # their WR2 6 -> 12, both weeks


def test_the_search_on_the_frame_finds_the_exhaustive_best_one_for_one():
    b, f = board(), free()
    s = _Search(b, 1, WEEKS, free=f)
    best = None
    for a in tradeable(b, 1, WEEKS):
        for x in tradeable(b, 2, WEEKS):
            pk = s.evaluate((a,), (x,))
            if pk.mutual and (best is None or pk.order() < best.order()):
                best = pk
    found = partners(b, 1, shapes=("1-for-1",), free=f)[0].one_for_one
    assert best is not None and found is not None
    assert (found.give, found.get) == (best.give, best.get) and found.score == best.score
    # the roster-only search leads with the bye cover; the frame does not
    ro = partners(b, 1, shapes=("1-for-1",))[0].one_for_one
    assert ro is not None and ro.get == ("tqb2",) and found.get != ("tqb2",)


def test_every_proposed_package_is_priced_on_the_frame():
    b, f = board(), free()
    stats: dict = {}
    for p in partners(b, 1, free=f, stats=stats):
        for pk in (p.one_for_one, p.two_for_one):
            if pk is None:
                continue
            again = _Search(b, 1, WEEKS, free=f).covered_gains(pk.give, pk.get)
            assert (pk.my_horizon, pk.their_horizon) == (again.my_horizon, again.their_horizon)
            # only my roster has an empty slot, so the exclusive pricing (one free agent never for both) is the same
            exact = package_gains_covered(b, pk.give, pk.get, WEEKS, f)
            assert (exact.my_horizon, exact.their_horizon) == pytest.approx((pk.my_horizon, pk.their_horizon), abs=0.01)
    assert stats["evaluated"] >= 1


def test_the_drop_is_netted_its_season_value_beyond_its_lineup_loss():
    b = IT1.board(extra=[P("abn1", "WR", 3), P("abn2", "RB", 2)])           # a full roster
    pool = IT1.pool()
    fr = _free_by_week(pool, (5, 6))
    market = {"abn1": 40.0, "abn2": 10.0, "arb2": 90.0}
    # the cheapest bench player by the market (abn2) carries 6.0 of season value above replacement: netted 10 - 6 = 4;
    # abn1 costs nothing beyond his (zero) lineup loss: the move drops him, +10
    det: dict = {}
    add, drop, by = basis_best_move(b, 1, (5, 6), fr, pool, market=market, prices={"abn1": 0.0, "abn2": 6.0}, detail=det)
    assert (add, drop, by) == ("frb", "abn1", (5.0, 5.0))
    assert det["excess"] == 0.0 and det["net_window"] == 10.0
    # when abn1 is the dearer one the cheaper drop stays, and its netting is said in the detail
    det = {}
    add, drop, by = basis_best_move(b, 1, (5, 6), fr, pool, market=market, prices={"abn1": 9.0, "abn2": 2.0}, detail=det)
    assert drop == "abn2" and det["piece"] == "season_value" and det["excess"] == 2.0 and det["net_window"] == 8.0
    assert det["net_week"] == 3.0


def test_a_pick_the_frame_uses_as_a_fill_is_priced_over_the_next_free_agent():
    # IF-2's roster-only pick is the free quarterback who covers the bye; on the frame he is the fill itself: priced
    # with `only`, he adds what `covered_move` says (his points over the next free quarterback: none here, 0)
    b = IT1.board()
    pool = IT1.pool()
    fr = _free_by_week(pool, (5, 6))
    det: dict = {}
    mv = basis_best_move(b, 1, (5, 6), fr, pool, detail=det, only=("fqb", None))
    assert mv is not None and mv[0] == "fqb" and mv[1] is None
    assert mv[2] == pytest.approx(covered_move(b, 1, pool["fqb"], None, (5, 6), fr, "fqb"))
    assert det["net_window"] == pytest.approx(sum(mv[2]))
