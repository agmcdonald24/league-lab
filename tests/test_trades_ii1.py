"""II-1 (Wave I-I, the product and analytics handoff § 2): credible trades on synthetic rosters, no database.

The covered frame (an empty starting slot is filled from that week's free pool, never priced at zero), the K / DEF
guardrail derived from the league's slots and the free pool (a 1-QB league vs a Superflex league), the plausibility
label (a roster-fit idea without market inputs; the value rule both ways), the threshold, a legitimate unequal-size
trade, and the symmetry of the treatment (both teams get the same free pool)."""

import pytest

from league_lab.lineup import Player
from league_lab.roster_value import RosterBoard
from league_lab.trades import (
    CREDIBLE_MARGIN,
    _free_by_week,
    covered_move,
    covered_side,
    credible,
    fill_empty,
    flex_positions,
    guard_positions,
    package_weeks,
    plausibility,
    streamable_for_starter,
    their_value_gap,
)

from .test_trades import P, U, rows_for

ONE_QB = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "BN", "BN", "BN"]
SUPER = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "K", "BN", "BN", "BN"]


def board(rosters: dict[int, dict[int, list[Player]]], slots, unplayable: dict | None = None) -> RosterBoard:
    """rosters: {roster: {week: players}}; unplayable: {(roster, week): [players who cannot play that week]}."""
    rows = []
    for r, by_week in rosters.items():
        for w, ps in by_week.items():
            rows += rows_for(r, w, ps, slots, list((unplayable or {}).get((r, w), [])))
    return RosterBoard(rows, slots)


def free(by_week: dict[int, list[Player]]) -> dict[str, dict[int, Player]]:
    out: dict[str, dict[int, Player]] = {}
    for w, ps in by_week.items():
        for p in ps:
            out.setdefault(p.id, {})[w] = p
    return out


# a 1-QB league: a free kicker as good as the starters, a free QB as good as the weakest starting QB
A1 = [P("aqb", "QB", 20), P("arb1", "RB", 15), P("arb2", "RB", 12), P("awr1", "WR", 16), P("awr2", "WR", 14),
      P("ate", "TE", 9), P("awr3", "WR", 11), P("ak", "K", 8), P("arb3", "RB", 6), P("awr4", "WR", 5)]
B1 = [P("bqb", "QB", 15), P("brb1", "RB", 16), P("brb2", "RB", 13), P("bwr1", "WR", 12), P("bwr2", "WR", 10),
      P("bte", "TE", 7), P("brb3", "RB", 11), P("bk", "K", 8.5), P("bwr3", "WR", 4), P("bqb2", "QB", 13)]
FREE1 = [P("fk", "K", 8.4), P("fqb", "QB", 15.5), P("fwr", "WR", 6), P("frb", "RB", 5)]


def test_fill_empty_fills_only_empty_slots():
    pool = [p for p in A1 if p.id != "ak"]           # no kicker this week (a bye): the K slot is empty
    total, used = fill_empty(pool, ONE_QB, sorted(FREE1, key=lambda p: -p.value))
    assert used == ("fk",) and total == pytest.approx(sum(p.value for p in pool[:7]) + 8.4)
    # a free agent better than a rostered starter is a waiver move, not coverage: nothing is added when no slot is empty
    total2, used2 = fill_empty(A1, ONE_QB, [P("fwr9", "WR", 30)])
    assert used2 == () and total2 == pytest.approx(sum(p.value for p in A1[:8]))


def test_bye_cover_is_priced_against_the_free_fill_not_zero():
    """The Folk shape: my kicker is on a bye in week 2; theirs plays. Raw, their kicker fills my empty slot (+8.5 that
    week); covered, he is worth what he adds over the best free kicker (+0.1)."""
    weeks = (1, 2)
    b = board({1: {1: A1, 2: [p for p in A1 if p.id != "ak"]}, 2: {1: B1, 2: B1}}, ONE_QB,
              unplayable={(1, 2): [U("ak", "K", None, "bye")]})
    fr = _free_by_week(free({1: FREE1, 2: FREE1}), weeks)
    raw_m, _ = package_weeks(b, ["awr4"], ["bk"], weeks)
    assert raw_m[1] == pytest.approx(8.5)
    cov = covered_side(b, 1, ["awr4"], ["bk"], weeks, fr)
    assert cov.by_week[1] == pytest.approx(0.1) and cov.fills_before[1] == ("fk",) and cov.fills_after[1] == ()
    # the waiver alternative on the same frame: claiming the free kicker adds what he beats my kicker by in week 1
    # (8.4 over 8.0) and nothing in week 2, where the free fill already covered the bye
    assert covered_move(b, 1, free({1: FREE1, 2: FREE1})["fk"], "awr4", weeks, fr, "fk") == (0.4, 0.0)


def test_guard_positions_follow_the_league_slots():
    weeks = (1,)
    fr = _free_by_week(free({1: FREE1}), weeks)
    g1 = guard_positions(board({1: {1: A1}, 2: {1: B1}}, ONE_QB), weeks, fr)
    # K: its own slot, and the free kicker (8.4) is as good as the weakest starting kicker (8): covered by the free pool
    assert g1["K"]["streamable"]
    # the skill positions are never guard positions (their scarcity lives in the replacement levels and the covered
    # frame), even a QB in a 1-QB league whose free pool holds a starting-calibre QB
    assert set(g1) == {"K"}
    # Superflex: a QB can start at SUPER_FLEX (flex-eligible)
    assert "QB" in flex_positions(SUPER) and "QB" not in flex_positions(ONE_QB)
    gs = guard_positions(board({1: {1: A1}, 2: {1: B1}}, SUPER), weeks, fr)
    assert "QB" not in gs and gs["K"]["streamable"]
    # a deep league whose free pool holds no starting-calibre kicker: K is not covered there
    g3 = guard_positions(board({1: {1: A1}, 2: {1: B1}}, ONE_QB), weeks, _free_by_week(free({1: [P("fk2", "K", 3)]}), weeks))
    assert not g3["K"]["streamable"]


def test_kicker_for_a_starter_is_implausible_unless_they_need_one():
    weeks = (1, 2)
    b = board({1: {1: A1, 2: A1}, 2: {1: B1, 2: B1}}, ONE_QB)
    fr = _free_by_week(free({1: FREE1, 2: FREE1}), weeks)
    g = guard_positions(b, weeks, fr)
    hit = streamable_for_starter(b, ["ak"], ["bwr1"], weeks, g, fr)          # my kicker for their starting WR
    assert hit is not None and hit["rule"] == "streamable_for_starter" and hit["starter"] == "bwr1" and hit["receiver"] == 2
    assert "K" in hit["words"] and "bwr1" in hit["words"]
    # either direction: their kicker for my starter is the same rule
    assert streamable_for_starter(b, ["awr1"], ["bk"], weeks, g, fr)["receiver"] == 1
    # a kicker for a bench player is not "for a starter"; a kicker for a kicker is not either
    assert streamable_for_starter(b, ["ak"], ["bwr3"], weeks, g, fr) is None
    assert streamable_for_starter(b, ["ak"], ["bk"], weeks, g, fr) is None
    # they have no kicker at all: a real hole - the rule passes (plausibility is left to the other checks)
    nok = [p for p in B1 if p.id != "bk"] + [P("bwr5", "WR", 3)]
    b2 = board({1: {1: A1, 2: A1}, 2: {1: nok, 2: nok}}, ONE_QB)
    assert streamable_for_starter(b2, ["ak"], ["bwr1"], weeks, guard_positions(b2, weeks, fr), fr) is None
    # their kicker projects far below the free pool's best: a need - passes
    weak = [p for p in B1 if p.id != "bk"] + [P("bk", "K", 4)]
    b3 = board({1: {1: A1, 2: A1}, 2: {1: weak, 2: weak}}, ONE_QB)
    assert streamable_for_starter(b3, ["ak"], ["bwr1"], weeks, guard_positions(b3, weeks, fr), fr) is None


def test_superflex_kicker_for_qb_and_qb_scarcity():
    """Superflex: a K for a starting QB is flagged (K is covered by the free pool); a QB for a WR + RB is not a guard
    case (QB is never a guard position there), and losing a starting QB is priced against the free pool's QB."""
    weeks = (1,)
    A = [P("aqb", "QB", 20), P("aqb2", "QB", 16), P("arb1", "RB", 15), P("awr1", "WR", 16), P("ate", "TE", 9),
         P("arb2", "RB", 12), P("ak", "K", 8), P("awr2", "WR", 7), P("arb3", "RB", 5)]
    B = [P("bqb", "QB", 18), P("bqb2", "QB", 14), P("brb1", "RB", 16), P("bwr1", "WR", 12), P("bte", "TE", 7),
         P("brb2", "RB", 13), P("bk", "K", 8.5), P("bwr2", "WR", 11), P("brb3", "RB", 10)]
    fsf = [P("fk", "K", 8.4), P("fqb", "QB", 9), P("fwr", "WR", 6)]
    b = board({1: {1: A}, 2: {1: B}}, SUPER)
    fr = _free_by_week(free({1: fsf}), weeks)
    g = guard_positions(b, weeks, fr)
    assert "QB" not in g
    assert streamable_for_starter(b, ["ak"], ["bqb2"], weeks, g, fr) is not None
    assert streamable_for_starter(b, ["aqb2"], ["bwr2", "brb3"], weeks, g, fr) is None
    # they give their second QB: their SUPER_FLEX falls to the best of the rest, never to an empty slot at zero
    c = covered_side(b, 2, ["bqb2"], ["awr2"], weeks, fr)
    assert c.by_week[0] < 0 and c.empty_after == ((),)


def test_a_legitimate_unequal_size_trade_is_credible():
    """Two of my WRs for their stud RB (a consolidation: they are deep at RB, thin at WR): no empty slot anywhere, so the covered gains equal the raw
    gains; both sides beat standing pat by more than the margin; the market inputs are there: a plausible offer."""
    weeks = (1, 2)
    A = [P("aqb", "QB", 20), P("arb1", "RB", 12), P("arb2", "RB", 11), P("awr1", "WR", 16), P("awr2", "WR", 14),
         P("ate", "TE", 9), P("awr3", "WR", 13), P("ak", "K", 8), P("awr4", "WR", 12.5), P("arb3", "RB", 4)]
    B = [P("bqb", "QB", 19), P("brb1", "RB", 22), P("brb2", "RB", 15), P("brb3", "RB", 14), P("brb4", "RB", 13),
         P("bwr1", "WR", 6), P("bwr2", "WR", 5), P("bte", "TE", 7), P("bk", "K", 8.5), P("bwr3", "WR", 4), P("bqb2", "QB", 10)]
    b = board({1: {1: A, 2: A}, 2: {1: B, 2: B}}, ONE_QB)
    fr = _free_by_week(free({1: FREE1, 2: FREE1}), weeks)
    mine = covered_side(b, 1, ["awr3", "awr4"], ["brb1"], weeks, fr)
    theirs = covered_side(b, 2, ["brb1"], ["awr3", "awr4"], weeks, fr)
    raw_m, raw_t = package_weeks(b, ["awr3", "awr4"], ["brb1"], weeks)
    assert mine.by_week == raw_m and theirs.by_week == raw_t                # no empty slot: nothing to cover
    assert mine.gain_window >= CREDIBLE_MARGIN and theirs.gain_window >= CREDIBLE_MARGIN
    assert theirs.cuts and not mine.cuts                                    # they get two for one: a required cut
    g = guard_positions(b, weeks, fr)
    assert streamable_for_starter(b, ["awr3", "awr4"], ["brb1"], weeks, g, fr) is None
    prices = {"awr3": 30.0, "awr4": 28.0, "brb1": 55.0}
    pl = plausibility(guard_hit=None, their_value_gap=their_value_gap(["awr3", "awr4"], ["brb1"], prices), unpriced=[],
                      no_market_line=[])
    assert pl["key"] == "plausible"
    assert credible(mine.gain_window, theirs.gain_window, pl)


def test_plausibility_labels_and_the_threshold():
    # a market input missing: a roster-fit idea, still allowed through the threshold, never "plausible"
    pl = plausibility(guard_hit=None, their_value_gap=None, unpriced=["X"], no_market_line=["Y"])
    assert pl["key"] == "roster_fit" and "X" in pl["reasons"][0] and "Y" in pl["reasons"][0]
    assert credible(2.0, 2.0, pl)
    # the value rule from their side: they give much more season value than they get - implausible
    gap = their_value_gap(["mine"], ["theirs"], {"mine": 10.0, "theirs": 60.0})
    assert gap and gap.startswith("they give 60")
    assert plausibility(guard_hit=None, their_value_gap=gap, unpriced=[], no_market_line=[])["key"] == "implausible"
    assert not credible(5.0, 5.0, {"key": "implausible"})
    # the margin on both sides, and legality
    ok = {"key": "plausible"}
    assert not credible(CREDIBLE_MARGIN - 0.01, 5.0, ok) and not credible(5.0, CREDIBLE_MARGIN - 0.01, ok)
    assert credible(CREDIBLE_MARGIN, CREDIBLE_MARGIN, ok) and not credible(5.0, 5.0, ok, legal=False)
    assert not credible(None, 5.0, ok)


def test_both_teams_get_the_same_treatment():
    """covered_side(A gives x for y) and covered_side(B gives y for x) are the same two sides, swapped."""
    weeks = (1, 2)
    b = board({1: {1: A1, 2: [p for p in A1 if p.id != "ak"]}, 2: {1: B1, 2: B1}}, ONE_QB,
              unplayable={(1, 2): [U("ak", "K", None, "bye")]})
    fr = _free_by_week(free({1: FREE1, 2: FREE1}), weeks)
    a_mine = covered_side(b, 1, ["awr3"], ["brb3"], weeks, fr)
    a_theirs = covered_side(b, 2, ["brb3"], ["awr3"], weeks, fr)
    # read from B's side: B gives brb3 for awr3 - the same two computations, roles swapped
    b_mine = covered_side(b, 2, ["brb3"], ["awr3"], weeks, fr)
    b_theirs = covered_side(b, 1, ["awr3"], ["brb3"], weeks, fr)
    assert a_mine == b_theirs and a_theirs == b_mine
    # and the free pool covers an empty slot for whichever side has one (here mine, week 2)
    assert a_mine.fills_before[1] == ("fk",)
