"""Wave I-C, IC-2: slots as eligibility sets, team units as players (league_lab.lineup).

Dad's league, MyFantasyLeague 70587 ("Make Football Great Again"), starts TMQB x1, RB x2, WR+TE x3, TMPK x1, Def x1;
the MFL translation (``mfl_client.slots``) writes those as ``roster_positions`` in the league's own words.
"""

from __future__ import annotations

import pytest

from league_lab import mfl_client as M
from league_lab.lineup import (
    SLOT_ELIGIBILITY,
    Player,
    align_starters,
    is_no_slot,
    no_slot_reason,
    parse_slots,
    slot_eligibility,
    solve,
    starter_slots,
)

DAD = ["TMQB", "RB", "RB", "WR+TE", "WR+TE", "WR+TE", "TMPK", "DEF", "BN", "BN", "BN", "BN", "BN", "BN"]
DAD_MFL_STARTERS = {"count": "8", "position": [
    {"name": "TMQB", "limit": "1"}, {"name": "RB", "limit": "2"}, {"name": "WR+TE", "limit": "3"},
    {"name": "TMPK", "limit": "1"}, {"name": "Def", "limit": "1"}]}


def P(i, pos, v, **kw):
    return Player(id=i, position=pos, value=v, value_source="proj_points", **kw)


def test_parse_slots_70587_eight_slots_with_their_eligibility_and_labels():
    slots, ignored = parse_slots(DAD)
    assert ignored == []
    assert [(s.label, s.type, set(s.elig), s.order) for s in slots] == [
        ("TMQB", "TMQB", {"TMQB"}, 1), ("RB1", "RB", {"RB"}, 2), ("RB2", "RB", {"RB"}, 3),
        ("WR+TE1", "WR+TE", {"WR", "TE"}, 4), ("WR+TE2", "WR+TE", {"WR", "TE"}, 5), ("WR+TE3", "WR+TE", {"WR", "TE"}, 6),
        ("TMPK", "TMPK", {"TMPK"}, 7), ("DEF", "DEF", {"DEF"}, 8)]


@pytest.mark.parametrize("name,elig", [
    ("WR+TE", {"WR", "TE"}), ("RB+WR", {"RB", "WR"}), ("RB+WR+TE", {"RB", "WR", "TE"}),
    ("QB+RB+WR+TE", {"QB", "RB", "WR", "TE"}), ("TMQB", {"TMQB"}), ("TMPK", {"TMPK"}), ("TMDEF", {"DEF"}),
    ("PK", {"K"}), ("Def", {"DEF"}), ("FLEX", {"RB", "WR", "TE"}), ("SUPER_FLEX", {"QB", "RB", "WR", "TE"}),
    ("REC_FLEX", {"WR", "TE"}), ("WRRB_FLEX", {"RB", "WR"}),
    ("DT+DE", None), ("IDP_FLEX", None), ("DL", None), ("LB", None), ("DB", None), ("XYZ", None), ("WR+XYZ", None),
])
def test_slot_eligibility(name, elig):
    got = slot_eligibility(name)
    assert (set(got) if got is not None else None) == elig
    # SLOT_ELIGIBILITY answers the same for every reader of slot types (waivers, decisions, availability)
    if elig is None:
        assert name.upper() not in SLOT_ELIGIBILITY and SLOT_ELIGIBILITY.get(name) is None
        with pytest.raises(KeyError):
            SLOT_ELIGIBILITY[name]
    else:
        assert set(SLOT_ELIGIBILITY[name.upper()]) == elig and set(SLOT_ELIGIBILITY.get(name.upper())) == elig


def test_idp_slots_are_reported_not_solved():
    slots, ignored = parse_slots(["QB", "RB", "DT+DE", "LB", "IDP_FLEX", "BN"])
    assert [s.label for s in slots] == ["QB", "RB"] and ignored == ["DT+DE", "LB", "IDP_FLEX"]


def dad_roster() -> list[Player]:
    return [P("tmqb", "TMQB", 21.4), P("tmqb2", "TMQB", 15.0), P("r1", "RB", 14.0), P("r2", "RB", 9.5), P("r3", "RB", 8.0),
            P("w1", "WR", 16.0), P("w2", "WR", 11.0), P("w3", "WR", 7.0), P("w4", "WR", 4.0), P("t1", "TE", 10.0),
            P("t2", "TE", 3.0), P("k", "TMPK", 8.5), P("d", "DEF", 6.0), P("pk", "K", 9.0)]


def test_solve_70587_seats_units_rbs_three_wr_te_and_def():
    lu = solve(dad_roster(), DAD)
    got = {s.slot.label: (s.player.id if s.player else None) for s in lu.starts}
    assert got == {"TMQB": "tmqb", "RB1": "r1", "RB2": "r2", "WR+TE1": "w1", "WR+TE2": "w2", "WR+TE3": "t1",
                   "TMPK": "k", "DEF": "d"}
    assert lu.empty_slots == [] and lu.total == pytest.approx(21.4 + 14 + 9.5 + 16 + 11 + 10 + 8.5 + 6)
    assert [p.id for p in lu.bench] == ["tmqb2", "r3", "w3", "w4", "t2"]
    # a WR is never "can't play" for want of a slot; the plain K has no slot (TMPK is the team's kicker)
    assert [(p.id, p.reason) for p in lu.unplayable] == [("pk", "No slot for a K in this league")]
    assert lu.no_slot == lu.unplayable and lu.cannot_play == ()
    # margins: the team QB over the other unit; the TE over the next WR (w3, 7)
    assert lu.margins["TMQB"] == pytest.approx(21.4 - 15.0) and lu.margins["WR+TE3"] == pytest.approx(10.0 - 7.0)


def test_wr_te_slot_takes_the_best_of_wr_and_te():
    lu = solve([P("w1", "WR", 5.0), P("t1", "TE", 9.0), P("t2", "TE", 8.0), P("w2", "WR", 7.0)], ["WR+TE", "WR+TE", "WR+TE"])
    assert sorted(s.player.id for s in lu.starts) == ["t1", "t2", "w2"] and [p.id for p in lu.bench] == ["w1"]
    # labels follow value within a type: WR+TE1 >= WR+TE2 >= WR+TE3
    assert [s.player.value for s in lu.starts] == [9.0, 8.0, 7.0]


def test_no_wr_is_cannot_play_in_dads_league_even_unvalued():
    ps = [P("w", "WR", None), P("t", "TE", 2.0)]
    lu = solve(ps, DAD)
    assert lu.unplayable == () and {s.player.id for s in lu.starts if s.player} == {"w", "t"}


def test_no_slot_wording_and_counts():
    assert no_slot_reason("TMQB") == "No slot for a TMQB in this league"
    assert no_slot_reason("RB") == "No slot for an RB in this league"
    assert is_no_slot(no_slot_reason("K")) and not is_no_slot("bye") and not is_no_slot(None)
    # in a Sleeper league a team unit has no slot: reported, never "can't play"
    lu = solve([P("q", "QB", 20.0), P("u", "TMQB", 25.0), P("x", "WR", 3.0, playable=False, reason="bye")], ["QB", "WR"])
    assert [p.id for p in lu.no_slot] == ["u"] and [p.id for p in lu.cannot_play] == ["x"]


def test_sleeper_names_unchanged():
    slots, ignored = parse_slots(["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", "K", "DEF", "BN", "IR", "TAXI", "DL"])
    assert [s.label for s in slots] == ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "FLEX", "SUPER_FLEX", "K", "DEF"]
    assert ignored == ["DL"]
    assert [s.elig for s in slots] == [SLOT_ELIGIBILITY[s.type] for s in slots]


def test_locked_unit_keeps_its_slot():
    lu = solve([P("u", "TMQB", 12.0, locked_slot="TMQB"), P("u2", "TMQB", 30.0), P("w", "WR", 4.0, locked_slot="WR+TE")], DAD)
    by = {s.slot.label: s for s in lu.starts}
    assert by["TMQB"].player.id == "u" and by["TMQB"].locked and by["WR+TE1"].player.id == "w" and by["WR+TE1"].locked
    assert [p.id for p in lu.bench] == ["u2"]


def test_align_starters_puts_each_mfl_starter_in_a_slot_that_admits_him():
    starters = [("t", ["TE"]), ("w", ["WR"]), ("q", ["TMQB"]), ("r1", ["RB"]), ("r2", ["RB"]), ("w2", ["WR"]),
                ("k", ["TMPK"]), ("d", ["DEF"])]
    arr = align_starters(DAD, starters)
    assert arr[0] == "q" and set(arr[1:3]) == {"r1", "r2"} and set(arr[3:6]) == {"t", "w", "w2"} and arr[6:] == ["k", "d"]
    assert starter_slots(DAD, arr)["t"] == "WR+TE" and starter_slots(DAD, arr)["q"] == "TMQB"
    # a FLEX league: the narrow slot first (a WR at WR, the extra RB at FLEX); a missing starter leaves "0"
    arr = align_starters(["QB", "RB", "WR", "FLEX", "BN"], [("r1", ["RB"]), ("r2", ["RB"]), ("w", ["WR"])])
    assert arr == ["0", "r1", "w", "r2"] or arr == ["0", "r2", "w", "r1"]


def test_mfl_slots_70587_in_the_leagues_own_words():
    slots, note = M.slots({"starters": DAD_MFL_STARTERS, "rosterSize": "14"})
    assert slots == DAD
    assert note["idp"] == [] and note["flex"] == 0 and note["units"] == ["TMPK", "TMQB"] and note["bench"] == 6
    assert M.slot_name("PK") == "K" and M.slot_name("Def") == "DEF" and M.slot_name("rb+wr+te") == "RB+WR+TE"
    assert M.slot_name("DT+DE") is None and M.slot_name("CB") is None


def test_cards_copy_of_the_eligibility_rule_and_the_slot_words():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    from lib import cards
    for name in ("QB", "FLEX", "SUPER_FLEX", "REC_FLEX", "WRRB_FLEX", "WR+TE", "RB+WR+TE", "QB+RB+WR+TE", "TMQB",
                 "TMPK", "TMDEF", "K", "DEF", "PK", "DT+DE", "XYZ"):
        assert cards.slot_elig(name) == (slot_eligibility(name) or frozenset()), name
    assert cards.slot_label("WR+TE1") == "WR/TE 1" and cards.slot_label("WR+TE") == "WR/TE"
    assert cards.slot_label("TMQB") == "team QB" and cards.slot_label("TMPK") == "team K"
    assert cards.slot_label("RB+WR+TE2") == "RB/WR/TE 2" and cards.slot_label("FLEX2") == "FLEX2"
    assert cards.slot_label("SUPER_FLEX") == "Superflex" and cards.slot_label("RB1") == "RB1"
    assert cards.no_slot_or_cant(no_slot_reason("K")) == "No slot" and cards.no_slot_or_cant("bye") == "Can't play"
    assert cards._eligible("TE", "WR+TE") and cards._eligible("TMQB", "TMQB") and not cards._eligible("RB", "WR+TE")
