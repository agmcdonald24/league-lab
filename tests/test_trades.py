"""T-01 trade evaluator and T-02 simulator logic on the B1 lineup service (``league_lab.trades``): both
rosters re-solved before / after a package, the forced cut of a two-for-one, the open spot and its best free
agent, locks, market value, the partner search against the exhaustive search, the fairness line, the rank
change and the URL parameters. Synthetic rosters, no database."""

import random

import pytest

from league_lab.lineup import Player, solve
from league_lab.roster_value import RosterBoard
from league_lab.trades import (
    Package,
    about_even,
    best_fill,
    clean_package,
    evaluate,
    fairness_line,
    fit_line,
    market_by_player,
    package_gains,
    parse_ids,
    partners,
    partners_exhaustive,
    price_by_player,
    rank_change,
    ranks,
    roster_limit,
    two_for_one_counts,
    verdict,
    whole,
)

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN", "BN", "BN"]              # 7 starters + 3 bench = 10 spots
SUPER = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "BN", "BN", "BN", "IR", "TAXI"]   # 6 + 3 = 9 spots


def P(pid: str, pos: str, value: float | None, **kw) -> Player:
    return Player(id=pid, position=pos, value=value, value_source="proj_points" if value is not None else None, **kw)


def rows_for(roster_id: int, week: int, players: list[Player], slots: list[str], unplayable: list[Player] = ()) -> list[dict]:
    """The lineup rows `league-lab lineups` would publish for one roster-week, from the solver itself."""
    lu = solve(players, slots)
    out = []
    for s in lu.starts:
        if s.player is None:
            out.append({"roster_id": roster_id, "week": week, "role": "empty", "slot": s.slot.label, "slot_type": s.slot.type,
                        "sleeper_player_id": None})
            continue
        p = s.player
        out.append({"roster_id": roster_id, "week": week, "role": "starter", "slot": s.slot.label, "slot_type": s.slot.type,
                    "sleeper_player_id": p.id, "gsis_id": f"g-{p.id}", "position": p.position, "fantasy_positions": list(p.positions),
                    "player_value": p.value, "value_source": p.value_source or "proj_points", "lineup_margin": s.margin,
                    "is_locked": s.locked, "reason": None})
    for p in lu.bench:
        out.append({"roster_id": roster_id, "week": week, "role": "bench", "slot": None, "slot_type": None, "sleeper_player_id": p.id,
                    "gsis_id": f"g-{p.id}", "position": p.position, "fantasy_positions": list(p.positions), "player_value": p.value,
                    "value_source": p.value_source or "proj_points", "lineup_margin": None, "is_locked": False, "reason": None})
    for p in [*lu.unplayable, *unplayable]:
        out.append({"roster_id": roster_id, "week": week, "role": "unplayable", "slot": None, "slot_type": None,
                    "sleeper_player_id": p.id, "gsis_id": f"g-{p.id}", "position": p.position, "fantasy_positions": list(p.positions),
                    "player_value": p.value, "value_source": "proj_points" if p.value is not None else None,
                    "lineup_margin": None, "is_locked": False, "reason": p.reason})
    return out


def U(pid: str, pos: str, value: float | None, reason: str) -> Player:
    return P(pid, pos, value, playable=False, reason=reason)


# me: deep at WR, thin at RB (RB2 7.0, FLEX a WR); them: deep at RB, thin at WR
ME = [P("mqb", "QB", 20.0), P("mrb1", "RB", 15.0), P("mrb2", "RB", 7.0), P("mwr1", "WR", 18.0), P("mwr2", "WR", 16.0),
      P("mwr3", "WR", 14.0), P("mwr4", "WR", 12.0), P("mte", "TE", 9.0), P("mqb2", "QB", 12.0), P("mrb3", "RB", 3.0)]
THEM = [P("tqb", "QB", 19.0), P("trb1", "RB", 17.0), P("trb2", "RB", 14.0), P("trb3", "RB", 13.0), P("trb4", "RB", 11.0),
        P("twr1", "WR", 15.0), P("twr2", "WR", 6.0), P("tte", "TE", 8.0), P("tqb2", "QB", 10.0), P("twr3", "WR", 2.0)]


def two_rosters(me=ME, them=THEM, slots=SLOTS, weeks=(4,), me_extra=(), them_extra=()) -> RosterBoard:
    rows = []
    for w in weeks:
        rows += rows_for(1, w, list(me), slots, list(me_extra)) + rows_for(2, w, list(them), slots, list(them_extra))
    return RosterBoard(rows, slots)


def total(players, slots=SLOTS) -> float:
    return solve(players, slots, margins=False).total


def without(ps, *ids):
    return [p for p in ps if p.id not in ids]


def by_id(ps, pid):
    return next(p for p in ps if p.id == pid)


# ------------------------------------------------------------------------------ evaluate
def test_one_for_one_with_gain_reproduces_both_solves():
    b = two_rosters()
    t = evaluate(b, ["mwr3"], ["trb3"])
    me_after = [*without(ME, "mwr3"), by_id(THEM, "trb3")]
    them_after = [*without(THEM, "trb3"), by_id(ME, "mwr3")]
    assert t.mine.before[0] == pytest.approx(total(ME)) and t.theirs.before[0] == pytest.approx(total(THEM))
    assert t.mine.after[0] == pytest.approx(total(me_after)) and t.theirs.after[0] == pytest.approx(total(them_after))
    # by hand: my RB2 7.0 -> 13.0 (+6), FLEX goes from mwr3 14.0 to mwr4 12.0 (-2): +4.0
    assert t.mine.gain_week == pytest.approx(4.0)
    # theirs: WR2 6.0 -> 14.0 (+8), FLEX was trb3 13.0 -> trb4 11.0 (-2): +6.0
    assert t.theirs.gain_week == pytest.approx(6.0)
    assert t.mine.cuts == () and t.theirs.cuts == () and t.mine.opened == 0 and t.theirs.opened == 0
    assert t.mine.size_after == t.mine.size_before == 10
    # the first week's lineups are the solver's
    assert t.mine.lineup_after.total == pytest.approx(t.mine.after[0])
    assert "trb3" in t.mine.lineup_after.starter_ids and "mwr3" not in t.mine.lineup_after.starter_ids


def test_one_for_one_depth_closest_call_and_who_starts_and_sits():
    b = two_rosters()
    t = evaluate(b, ["mwr3"], ["trb3"])
    # depth = the best lineup the bench alone fields (B1's bench_value): before QB mqb2 12 + RB mrb3 3 + WR mwr4 12;
    # after mwr4 starts at FLEX and mrb2 (RB 7) sits: QB 12 + RB 7 + RB 3
    assert t.mine.bench_before == pytest.approx(27.0) and t.mine.bench_after == pytest.approx(22.0)
    after_lu = solve([*without(ME, "mwr3"), by_id(THEM, "trb3")], SLOTS)
    assert t.mine.weakest_after.player.id == after_lu.weakest.player.id
    assert t.mine.weakest_after.margin == pytest.approx(after_lu.weakest.margin)
    assert set(t.mine.sits) == {"mwr3", "mrb2"} and set(t.mine.starts) == {"trb3", "mwr4"}


def test_one_for_one_where_one_side_loses_is_never_a_partner_trade():
    # my bench QB (12.0) for their FLEX RB (13.0): my RB2 goes 7.0 -> 13.0 (+6.0); their FLEX goes to the RB 11.0 and
    # the QB sits behind theirs (-2.0)
    b = two_rosters()
    t = evaluate(b, ["mqb2"], ["trb3"])
    assert t.mine.gain_week == pytest.approx(6.0) and t.theirs.gain_week == pytest.approx(-2.0)
    assert t.theirs.after[0] == pytest.approx(total([*without(THEM, "trb3"), by_id(ME, "mqb2")]))
    assert not package_gains(b, ("mqb2",), ("trb3",), (4,)).mutual
    ps = partners(b, 1)
    for p in ps:
        for pk in (p.one_for_one, p.two_for_one):
            assert pk is None or (pk.my_horizon >= 0.01 and pk.their_horizon >= 0.01)
            assert pk is None or (pk.give, pk.get) != (("mqb2",), ("trb3",))


KSLOTS = ["QB", "RB", "WR", "WR", "TE", "FLEX", "K", "BN", "BN"]      # 7 starters + 2 bench = 9 spots


def test_k_for_wr_empties_the_k_slot_and_the_market_prices_the_kicker_near_zero():
    me = [P("mq", "QB", 20.0), P("mr1", "RB", 15.0), P("mr2", "RB", 7.0), P("mw1", "WR", 14.0), P("mw2", "WR", 12.0),
          P("mt", "TE", 9.0), P("mk", "K", 8.0), P("mw3", "WR", 6.0)]
    them = [P("tq", "QB", 18.0), P("tr1", "RB", 13.0), P("tr2", "RB", 12.0), P("tw1", "WR", 11.0), P("tw2", "WR", 10.5),
            P("tt", "TE", 7.0), P("tk", "K", 5.0), P("tw3", "WR", 10.0), P("tw4", "WR", 4.0)]
    b = two_rosters(me, them, KSLOTS)
    t = evaluate(b, ["mk"], ["tw3"])
    # mine: the K slot empties (-8.0), the WR 10.0 takes FLEX from the RB 7.0 (+3.0): -5.0
    assert "K" in t.mine.lineup_after.empty_slots and "K" not in t.mine.lineup_before.empty_slots
    assert t.mine.gain_week == pytest.approx(-5.0)
    assert t.mine.after[0] == pytest.approx(total([*without(me, "mk"), by_id(them, "tw3")], KSLOTS))
    # theirs: K 5.0 -> 8.0 (+3.0); the WR they give sat on their bench (0)
    assert t.theirs.gain_week == pytest.approx(3.0)
    assert "mk" in t.theirs.lineup_after.starter_ids and "tk" in t.theirs.sits
    # the market: a kicker projects nearly a WR's season points, but a free agent kicker projects more
    mk = {"mk": 8.0 * 14, "tw3": 10.0 * 14}
    pr = price_by_player(b, mk, {"K": 118.0, "WR": 100.0})
    assert pr == {"mk": 0.0, "tw3": 40.0}
    t = evaluate(b, ["mk"], ["tw3"], market=mk, prices=pr)
    assert (t.mine.points_out, t.mine.points_in) == (112, 140) and (t.mine.price_out, t.mine.price_in) == (0, 40)
    assert verdict(t, "week 4").startswith("Does not help you (-5.0 this week")
    assert verdict(t, "week 4").endswith("the market says you're getting more: only worth it for the season value.")
    # the partner search never offers it (my lineup loses)
    assert all(p.best is None or (p.best.give, p.best.get) != (("mk",), ("tw3",)) for p in partners(b, 1))


def test_bye_weeks_over_the_horizon():
    # week 5: their RB trb3 is on bye; my WR mwr3 plays both weeks
    rows = (rows_for(1, 4, ME, SLOTS) + rows_for(2, 4, THEM, SLOTS)
            + rows_for(1, 5, ME, SLOTS) + rows_for(2, 5, without(THEM, "trb3"), SLOTS, [U("trb3", "RB", None, "bye")]))
    b = RosterBoard(rows, SLOTS)
    t = evaluate(b, ["mwr3"], ["trb3"])
    assert t.weeks == (4, 5)
    # week 4 as the 1-for-1 test: me +4.0, them +6.0
    assert t.mine.after[0] - t.mine.before[0] == pytest.approx(4.0) and t.theirs.gain_week == pytest.approx(6.0)
    # week 5: he arrives on his bye (worth 0 to me that week), my FLEX drops from 14.0 to 12.0: -2.0
    assert t.mine.after[1] == pytest.approx(total(without(ME, "mwr3")))
    assert t.mine.after[1] - t.mine.before[1] == pytest.approx(-2.0)
    # they lose nothing in week 5 (he was on bye) and their WR2 goes 6.0 -> 14.0: +8.0
    assert t.theirs.before[1] == pytest.approx(total(without(THEM, "trb3")))
    assert t.theirs.after[1] - t.theirs.before[1] == pytest.approx(8.0)
    assert t.mine.gain_horizon == pytest.approx(2.0) and t.theirs.gain_horizon == pytest.approx(14.0)
    # a two-for-one: their TE is on bye in week 4 and starts in week 5 - the cut counts the horizon, so the TE (who
    # would cost 8.0 in week 5) is never the cut; a player who starts in neither week is
    them4 = [p for p in THEM if p.id != "tte"]
    rows = (rows_for(1, 4, ME, SLOTS) + rows_for(2, 4, them4, SLOTS, [U("tte", "TE", None, "bye")])
            + rows_for(1, 5, ME, SLOTS) + rows_for(2, 5, THEM, SLOTS))
    b = RosterBoard(rows, SLOTS)
    t = evaluate(b, ["mwr3", "mwr4"], ["trb3"])
    assert len(t.theirs.cuts) == 1 and t.theirs.cuts[0].player_id != "tte" and t.theirs.cuts[0].horizon_loss == 0.0
    assert "tte" in solve([p for p in b.pool_with(2, 5, ["trb3"], ["mwr3", "mwr4"]) if p.id != t.theirs.cuts[0].player_id],
                          SLOTS).starter_ids


def test_price_by_player_is_season_points_above_the_best_free_agent():
    rows = rows_for(1, 4, [P("w", "WR", 16.0), P("k", "K", 8.0), P("q", "QB", 20.0), P("t", "TE", 7.0)], ["QB", "WR", "TE", "K"])
    b = RosterBoard(rows, ["QB", "WR", "TE", "K"])
    pr = price_by_player(b, {"w": 150.4, "k": 112.0, "q": 250.0}, {"WR": 100.0, "K": 120.0})
    # QB: no free agent projected -> replacement 0; K below the free agent -> 0 (never negative); TE: no market -> absent
    assert pr == {"w": pytest.approx(50.4), "k": 0.0, "q": 250.0}


def test_two_for_one_forces_the_cheapest_cut_and_never_leaves_a_roster_over_size():
    # they get two (mwr3, mwr4) for one (trb3): 10 - 1 + 2 = 11 > 10 spots, one must go
    b = two_rosters()
    mk = {p.id: 10.0 * p.value for p in ME + THEM}     # season value proportional to this week's value
    mk["tqb2"], mk["twr3"] = 150.0, 40.0
    t = evaluate(b, ["mwr3", "mwr4"], ["trb3"], market=mk)
    assert roster_limit(SLOTS) == 10
    assert t.theirs.size_after == 10 == t.theirs.limit and len(t.theirs.cuts) == 1
    cut = t.theirs.cuts[0]
    # the droppable players who start in no after-lineup cost 0; among them the fewest season points: twr3 (2.0, 40)
    assert cut.player_id == "twr3" and cut.horizon_loss == 0.0 and cut.market == 40.0
    them_after = [*without(THEM, "trb3", "twr3"), by_id(ME, "mwr3"), by_id(ME, "mwr4")]
    assert t.theirs.after[0] == pytest.approx(total(them_after))
    # my side opens a spot (10 - 2 + 1 = 9): reported, nobody on my roster is cut
    assert t.mine.cuts == () and t.mine.size_after == 9 and t.mine.opened == 1
    # season points: whole points of what changes hands (140 + 120 = 260 out, 130 in); no prices given: no market score
    assert (t.mine.points_out, t.mine.points_in) == (260, 130) and (t.theirs.points_out, t.theirs.points_in) == (130, 260)
    assert t.mine.price_out is None and t.mine.price_in is None
    # with prices (season points above a free agent at the position): the sums of the whole-point prices
    pr = {"mwr3": 40.4, "mwr4": 20.5, "trb3": 55.0}
    t = evaluate(b, ["mwr3", "mwr4"], ["trb3"], market=mk, prices=pr)
    assert (t.mine.price_out, t.mine.price_in) == (40 + 21, 55) and (t.theirs.price_out, t.theirs.price_in) == (55, 61)
    # the cut is counted in their after-lineup and in their horizon gain
    assert t.theirs.gain_horizon == pytest.approx(total(them_after) - total(THEM))


def test_the_cut_is_the_cheapest_even_when_every_candidate_starts():
    # a roster with no bench (7 starters, limit 7 with no BN): receiving 2 for 1 forces cutting a starter; the
    # cheapest one over the horizon is cut, and his loss is counted in the after-lineup
    slots = ["QB", "RB", "WR", "TE", "FLEX", "BN"]            # 5 starters + 1 bench = 6 spots
    me = [P("a1", "WR", 12.0), P("a2", "RB", 11.0), P("aq", "QB", 20.0), P("ar", "RB", 5.0), P("aw", "WR", 5.0), P("at", "TE", 5.0)]
    them = [P("bq", "QB", 18.0), P("br", "RB", 9.0), P("bw", "WR", 8.0), P("bt", "TE", 6.0), P("bf", "RB", 7.5), P("bx", "WR", 7.0)]
    b = two_rosters(me, them, slots)
    t = evaluate(b, ["a1", "a2"], ["bx"])
    assert t.theirs.size_after == 6 and len(t.theirs.cuts) == 1
    # brute force: the post-trade lineup after every legal cut; the evaluator must pick the best one
    base = [*without(them, "bx"), by_id(me, "a1"), by_id(me, "a2")]
    best = max(total([p for p in base if p.id != c], slots) for c in ["bq", "br", "bw", "bt", "bf"])
    assert t.theirs.after[0] == pytest.approx(best)
    assert t.theirs.cuts[0].horizon_loss == pytest.approx(total(base, slots) - best)


def test_the_cut_is_the_cheapest_over_the_horizon_when_nobody_is_free():
    # every player they could cut starts in some week (byes in weeks 5 and 6), so no cut is free: the evaluator must
    # compare them all - not stop at the one with the fewest season points (bf) or the first id (bf)
    slots = ["QB", "RB", "WR", "TE", "FLEX", "BN"]            # 5 starters + 1 bench = 6 spots
    me = [P("a1", "WR", 12.0), P("a2", "RB", 11.0), P("aq", "QB", 20.0), P("ar", "RB", 5.0), P("aw", "WR", 5.0), P("at", "TE", 5.0)]
    base = {"bq": ("QB", 18.0), "br": ("RB", 9.0), "bw": ("WR", 8.0), "bt": ("TE", 6.0), "bf": ("RB", 7.5), "bx": ("WR", 7.0)}
    byes = {4: (), 5: ("br",), 6: ("br", "bw")}
    rows = []
    for w, off in byes.items():
        them = [P(k, pos_, v) for k, (pos_, v) in base.items() if k not in off]
        rows += rows_for(1, w, me, slots) + rows_for(2, w, them, slots, [U(k, base[k][0], None, "bye") for k in off])
    b = RosterBoard(rows, slots)
    mk = {"bf": 50.0, "br": 60.0, "bt": 70.0, "bw": 90.0, "bq": 200.0}
    for market in (mk, None):
        t = evaluate(b, ["a1", "a2"], ["bx"], market=market)
        # by hand: cutting bq costs 54.0 (no QB), bt 18.0 (no TE), bf 7.5 (the week-6 FLEX), br 1.0 (week 4: bw 8.0
        # takes FLEX), bw 0.5 (week 5: bf 7.5 takes FLEX)
        assert [c.player_id for c in t.theirs.cuts] == ["bw"] and t.theirs.cuts[0].horizon_loss == pytest.approx(0.5)
        after = [total([p for p in b.pool_with(2, w, ["bx"], ["a1", "a2"]) if p.id != "bw"], slots) for w in (4, 5, 6)]
        assert list(t.theirs.after) == pytest.approx(after)


def test_a_trade_that_empties_a_slot():
    # they give their only TE for a WR: their TE slot is empty after, and they lose exactly the TE's value
    b = two_rosters()
    t = evaluate(b, ["mwr4"], ["tte"])
    assert "TE" in t.theirs.lineup_after.empty_slots and "TE" not in t.theirs.lineup_before.empty_slots
    assert t.theirs.after[0] == pytest.approx(total([*without(THEM, "tte"), by_id(ME, "mwr4")]))
    # their WR2 6.0 -> 12.0 (+6) and TE 8.0 -> empty (-8): -2.0
    assert t.theirs.gain_week == pytest.approx(-2.0)
    # mine: TE 9.0 stays, the incoming TE 8.0 sits; FLEX mwr4 12.0 is not starting anyway: 0
    assert t.mine.gain_week == pytest.approx(0.0)


def test_locked_players_stay_where_they_are_that_week():
    # week 4: my QB is locked in his slot (his game kicked off) and so is their RB1; week 5 nobody is locked
    me4 = [P("mqb", "QB", 20.0, locked_slot="QB"), *without(ME, "mqb")]
    them4 = [P("trb1", "RB", 17.0, locked_slot="RB"), *without(THEM, "trb1")]
    rows = rows_for(1, 4, me4, SLOTS) + rows_for(2, 4, them4, SLOTS) + rows_for(1, 5, ME, SLOTS) + rows_for(2, 5, THEM, SLOTS)
    b = RosterBoard(rows, SLOTS)
    assert b.is_locked("mqb", 4) and not b.is_locked("mqb", 5)
    # an untraded locked starter keeps his slot and value after the trade
    t = evaluate(b, ["mwr3"], ["trb3"])
    qb = next(s for s in t.mine.lineup_after.starts if s.slot.label == "QB")
    assert qb.player.id == "mqb" and qb.locked and qb.value == 20.0
    # a traded locked player stays in his old lineup in week 4 and moves in week 5
    t = evaluate(b, ["mrb2"], ["trb1"])
    assert "trb1" in t.theirs.lineup_after.starter_ids and "trb1" not in t.mine.lineup_after.starter_ids
    assert t.mine.after[0] == pytest.approx(total(without(me4, "mrb2")))          # he left me, nobody came in yet
    assert t.theirs.after[0] == pytest.approx(total([*them4, by_id(ME, "mrb2")]))  # they keep him this week
    assert t.mine.after[1] == pytest.approx(total([*without(ME, "mrb2"), by_id(THEM, "trb1")]))
    assert t.theirs.after[1] == pytest.approx(total([*without(THEM, "trb1"), by_id(ME, "mrb2")]))
    # a locked player is never the cut
    t = evaluate(b, ["mwr3", "mwr4"], ["tqb2"])
    assert t.theirs.cuts and t.theirs.cuts[0].player_id != "trb1"


def test_ir_and_taxi_players_hold_no_active_spot():
    # my taxi WR (11.0, can play for a new team) for their bench RB: I give no active spot and get one -> cut
    taxi = U("mtaxi", "WR", 11.0, "taxi squad")
    ir = U("mir", "RB", 9.0, "IR slot")
    b = two_rosters(me_extra=[taxi, ir])
    assert not b.is_active("mtaxi") and not b.is_active("mir") and b.active_count(1) == 10
    t = evaluate(b, ["mtaxi"], ["trb4"])
    assert t.mine.size_after == 10 and len(t.mine.cuts) == 1 and t.mine.cuts[0].player_id not in ("mtaxi", "mir")
    assert t.theirs.size_after == 10 and t.theirs.cuts == ()       # they gave an active player, got one
    # the taxi player plays for them: 11.0 beats their WR2 6.0
    assert t.theirs.gain_week == pytest.approx(total([*without(THEM, "trb4"), P("mtaxi", "WR", 11.0)]) - total(THEM))
    # an IR-slot player is worth nothing to the receiver that week
    t = evaluate(b, ["mir"], ["twr3"])
    assert t.theirs.gain_week == pytest.approx(total(without(THEM, "twr3")) - total(THEM))


def test_bad_packages_are_refused():
    b = two_rosters()
    with pytest.raises(ValueError):
        evaluate(b, [], ["trb3"])
    with pytest.raises(ValueError):
        evaluate(b, ["mwr3"], ["mwr4"])              # same roster
    with pytest.raises(ValueError):
        evaluate(b, ["mwr3", "trb1"], ["trb3"])      # give spans two rosters
    with pytest.raises(ValueError):
        evaluate(b, ["nobody"], ["trb3"])


# ------------------------------------------------------------------------------ the open spot
def test_best_fill_is_the_free_agent_who_adds_most_exactly():
    b = two_rosters(weeks=(4, 5))
    t = evaluate(b, ["mwr3", "mwr4"], ["trb3"], weeks=(4, 5),
                 free_agents={"fa_rb": {4: P("fa_rb", "RB", 9.0), 5: P("fa_rb", "RB", 9.0)},
                              "fa_wr": {4: P("fa_wr", "WR", 13.5), 5: None},              # on bye in week 5
                              "fa_te": {4: P("fa_te", "TE", 9.5), 5: P("fa_te", "TE", 9.5)},
                              "trb1": {4: P("trb1", "RB", 17.0)}})                         # rostered: never a fill
    after = [*without(ME, "mwr3", "mwr4"), by_id(THEM, "trb3")]
    brute = {}
    for fid, vals in (("fa_rb", (9.0, 9.0)), ("fa_wr", (13.5, None)), ("fa_te", (9.5, 9.5))):
        g = []
        for v, pos in ((vals[0], fid[3:].upper()), (vals[1], fid[3:].upper())):
            g.append(0.0 if v is None else total([*after, P(fid, pos, v)]) - total(after))
        brute[fid] = g
    best = max(brute, key=lambda f: (round(sum(brute[f]), 2), round(brute[f][0], 2)))
    assert t.mine.fill is not None and t.mine.fill.player_id == best
    assert t.mine.fill.horizon_gain == pytest.approx(sum(brute[best]))
    assert list(t.mine.fill.week_gains) == pytest.approx(brute[best])
    # the fill is reported, not added to the gain
    assert t.mine.after[0] == pytest.approx(total(after))


def test_no_fill_when_nobody_helps():
    b = two_rosters()
    after = [*without(ME, "mwr3", "mwr4"), by_id(THEM, "trb3")]
    pools = [after]
    assert best_fill(b, (4,), pools, {"fa": {4: P("fa", "WR", 1.0)}}) is None


# ------------------------------------------------------------------------------ random rosters
def random_league(rng: random.Random, n_rosters=3, weeks=(4, 5), slots=SUPER, size=9):
    """Rosters of `size` active players (+ sometimes a taxi and an IR player), byes and a lock in week 4."""
    positions = ["QB", "QB", "RB", "RB", "RB", "WR", "WR", "WR", "TE", "TE"]
    rows = []
    for r in range(1, n_rosters + 1):
        base = [(f"r{r}p{i}", rng.choice(positions)) for i in range(size)]
        vals = {pid: round(rng.uniform(1, 25), 2) for pid, _ in base}
        extra = []
        if rng.random() < 0.5:
            extra.append((f"r{r}taxi", "WR", "taxi squad"))
        if rng.random() < 0.5:
            extra.append((f"r{r}ir", "RB", "IR slot"))
        bye = rng.choice([pid for pid, _ in base])
        lock = rng.choice([pid for pid, _ in base]) if rng.random() < 0.5 else None
        for w in weeks:
            ps, un = [], []
            for pid, pos in base:
                v = round(vals[pid] * rng.uniform(0.8, 1.2), 2)
                if pid == bye and w == weeks[-1]:
                    un.append(U(pid, pos, None, "bye"))
                else:
                    ps.append(P(pid, pos, v))
            if lock is not None and w == weeks[0]:
                lu = solve(ps, slots)
                start = next((s for s in lu.starts if s.player is not None and s.player.id == lock), None)
                if start is not None:
                    ps = [P(p.id, p.position, p.value, locked_slot=start.slot.type) if p.id == lock else p for p in ps]
            for pid, pos, reason in extra:
                un.append(U(pid, pos, round(rng.uniform(3, 15), 2), reason))
            rows += rows_for(r, w, ps, slots, un)
    return RosterBoard(rows, slots)


@pytest.mark.parametrize("seed", range(8))
def test_random_packages_never_leave_a_roster_over_size(seed):
    rng = random.Random(seed)
    b = random_league(rng, n_rosters=2)
    limit = roster_limit(SUPER)
    for _ in range(12):
        give = rng.sample(b.roster(1), rng.randint(1, 3))
        get = rng.sample(b.roster(2), rng.randint(1, 3))
        t = evaluate(b, give, get)
        for side in (t.mine, t.theirs):
            assert side.size_after <= limit
            cut = {c.player_id for c in side.cuts}
            assert not cut & set(side.gets) and not cut & set(side.gives)
            # the size is the active players left: everybody active who stayed (minus the cuts) + everybody received
            stay = [p for p in b.roster(side.roster_id) if p not in side.gives and b.is_active(p) and p not in cut]
            assert side.size_after == len(stay) + len(side.gets)
            if side.size_before - sum(b.is_active(p) for p in side.gives) + len(side.gets) > limit:
                assert side.size_after == limit
            # the after-lineups never start a cut player; every week re-solves to the stored total
            def after_total(drop, t=t, side=side):
                tot = 0.0
                for w in t.weeks:
                    moving_out = [p for p in side.gives if not b.is_locked(p, w)]
                    moving_in = [p for p in side.gets if not b.is_locked(p, w)]
                    tot += solve([p for p in b.pool_with(side.roster_id, w, moving_out, moving_in) if p.id not in drop],
                                 SUPER, margins=False).total
                return tot
            for h, w in enumerate(t.weeks):
                moving_out = [p for p in side.gives if not b.is_locked(p, w)]
                moving_in = [p for p in side.gets if not b.is_locked(p, w)]
                pool = [p for p in b.pool_with(side.roster_id, w, moving_out, moving_in) if p.id not in cut]
                assert side.after[h] == pytest.approx(solve(pool, SUPER, margins=False).total)
            # one cut: brute force over every legal cut - the evaluator keeps the best post-trade lineups
            if len(side.cuts) == 1:
                legal = [p for p in stay + list(cut) if p not in side.gives and not b.is_locked(p, t.weeks[0])
                         and b.has_value(p, t.weeks)]
                best = max(after_total({c}) for c in legal)
                assert sum(side.after) == pytest.approx(best)
                assert side.cuts[0].horizon_loss == pytest.approx(round(after_total(set()) - best, 2), abs=0.006)


@pytest.mark.parametrize("seed", range(4))
def test_partner_search_equals_the_exhaustive_search(seed):
    rng = random.Random(100 + seed)
    b = random_league(rng, n_rosters=3, size=7)
    fast = {p.roster_id: p for p in partners(b, 1)}
    slow = {p.roster_id: p for p in partners_exhaustive(b, 1)}
    assert fast.keys() == slow.keys()
    found = 0
    for r in fast:
        for a, e in ((fast[r].one_for_one, slow[r].one_for_one), (fast[r].two_for_one, slow[r].two_for_one)):
            assert (a is None) == (e is None)
            if a is not None:
                found += 1
                assert a.order() == e.order()
                assert a.mutual and a.my_horizon >= 0.01 and a.their_horizon >= 0.01
    assert found > 0     # the fixtures do produce trades


def test_partners_find_the_complementary_trade_and_rank_by_the_smaller_gain():
    # roster 1 (WR-rich, RB-poor), roster 2 (RB-rich, WR-poor), roster 3 (a copy of roster 1: nothing to swap)
    rows = rows_for(1, 4, ME, SLOTS) + rows_for(2, 4, THEM, SLOTS) + rows_for(3, 4, [P("c" + p.id, p.position, p.value) for p in ME], SLOTS)
    b = RosterBoard(rows, SLOTS)
    ps = partners(b, 1)
    assert ps[0].roster_id == 2 and ps[0].best is not None and ps[0].best.mutual
    best1 = ps[0].one_for_one
    # the best 1-for-1 is the WR-for-RB swap that maximises the smaller gain; check against every 1-for-1
    every = [package_gains(b, (a,), (x,), (4,)) for a in b.roster(1) for x in b.roster(2)]
    mutual = [p for p in every if p.mutual]
    assert best1.order() == min(mutual, key=Package.order).order()
    assert b.owner(best1.give[0]) == 1 and by_id(ME, best1.give[0]).position == "WR"
    assert by_id(THEM, best1.get[0]).position == "RB"
    assert ps[-1].roster_id == 3 and ps[-1].best is None      # identical rosters: nobody gains from a swap


def test_a_throw_in_is_not_a_two_for_one():
    b = two_rosters()
    # mqb2 (QB 12.0) adds nothing to their lineup (QB 19.0, no superflex): a throw-in
    assert not two_for_one_counts(b, ("mwr3", "mqb2"), ("trb3",), (4,))
    assert two_for_one_counts(b, ("mwr3", "mwr4"), ("trb3",), (4,))


# ------------------------------------------------------------------------------ market, words, ranks, URL
def test_market_by_player_keys_by_gsis_and_def_by_sleeper_id():
    rows = rows_for(1, 4, [P("7547", "WR", 16.0), P("KC", "DEF", 7.0)], ["WR", "DEF"])
    for r in rows:
        if r["sleeper_player_id"] == "KC":
            r["gsis_id"] = None                     # a team defense has no NFL player id
    b = RosterBoard(rows, ["WR", "DEF"])
    m = market_by_player(b, {"g-7547": 235.3, "KC": 101.26, "other": 5.0})
    assert m == {"7547": 235.3, "KC": 101.26}
    assert whole(235.5) == 236 and whole(101.49) == 101


def _trade(my_w, my_h, th_w, th_h, po, pi, unknown=()):
    """A Trade shell with the numbers the lines read (one week for the week figure, the rest in week 2)."""
    from league_lab.trades import Side, Trade

    def side(w, h, out, inc, unk=()):
        return Side(1, (), (), (4, 5), (100.0, 100.0), (100.0 + w, 100.0 + h - w), None, None, (), 10, 10, 10, 0, None,
                    out, inc, unknown_out=unk)
    return Trade(side(my_w, my_h, po, pi, unknown), side(th_w, th_h, pi, po))


def test_fit_line_market_line_and_verdict():
    t = _trade(4.2, 10.3, -1.1, -3.0, 85, 60)
    assert fit_line(t, "weeks 4–7") == ("**Fit** (what the best lineups gain): you **+4.2** this week and **+10.3** over "
                                        "weeks 4–7; them **-1.1** and **-3.0**.")
    assert fairness_line(t) == ("**Market** (season points above the best free agent at the position): you give **85**, "
                                "you get **60**: you give 25 more.")
    # the plan's example: helps me, costs them, the market says I give up more -> they could take it for the value
    assert verdict(t, "weeks 4–7") == ("Helps you +4.2 this week (+10.3 over weeks 4–7), costs them 1.1 (3.0 over weeks 4–7); "
                                       "the market says you're giving up more: a rebuilding team might take it for the value.")
    # helps me, costs them, I get more of the market too -> a no
    assert verdict(_trade(4.2, 10.3, -1.1, -3.0, 40, 70), "weeks 4–7").endswith(
        "the market says you're getting more: expect a no.")
    # both gain, about even (within 10 points / 10%) -> worth offering; both gain, they give up more -> they may ask for more
    s = verdict(_trade(3.0, 9.0, 1.0, 4.0, 100, 95), "weeks 4–7")
    assert s.startswith("Helps you +3.0 this week (+9.0 over weeks 4–7), them +1.0 (+4.0 over weeks 4–7)")
    assert s.endswith("about even: worth offering.")
    assert verdict(_trade(3.0, 9.0, 1.0, 4.0, 40, 90), "weeks 4–7").endswith("they may ask for more.")
    # does not help me: skip it, unless the market gives me more
    assert verdict(_trade(-1.0, -3.0, 2.0, 5.0, 90, 40), "weeks 4–7").endswith("skip it.")
    s = verdict(_trade(0.0, 0.0, 2.0, 5.0, 40, 90), "weeks 4–7")
    assert s.startswith("Does not help you (+0.0 this week, +0.0 over weeks 4–7)") and s.endswith("only worth it for the season value.")
    # a lineup that gains over the horizon but not this week leads with the horizon
    assert verdict(_trade(-2.3, 0.8, -5.3, 4.5, 50, 45), "weeks 4–7").startswith(
        "Helps you +0.8 over weeks 4–7 (-2.3 this week), them +4.5 over weeks 4–7 (-5.3 this week);")
    # unknown players are named as not counted
    assert "1 player in it has no projection yet and is not counted." in fairness_line(_trade(1, 1, 1, 1, 10, 10, ("x",)))
    assert about_even(100, 91) and not about_even(100, 89) and about_even(20, 11) and not about_even(20, 9)


def test_rank_change_uses_rank_semantics():
    values = {1: 110.0, 2: 120.0, 3: 100.0, 4: 120.0}
    assert ranks(values) == {1: 3, 2: 1, 3: 4, 4: 1}
    assert rank_change(values, {1: 125.0, 2: 105.0}) == {1: (3, 1), 2: (1, 3), 3: (4, 4), 4: (1, 2)}


def test_url_ids_are_parsed_and_bad_ones_dropped():
    assert parse_ids("7547, 96,,96") == ["7547", "96"] and parse_ids(None) == [] and parse_ids(["a,b", "c"]) == ["a", "b", "c"]
    b = two_rosters()
    give, get, dropped = clean_package(b, 1, 2, ["mwr3", "trb1", "zzz"], ["trb3", "mwr1"])
    assert give == ["mwr3"] and get == ["trb3"] and set(dropped) == {"trb1", "zzz", "mwr1"}
    give, get, dropped = clean_package(b, 1, None, ["mwr3"], ["trb3"])
    assert give == ["mwr3"] and get == [] and dropped == ["trb3"]
