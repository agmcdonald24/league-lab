"""B2 roster value on the B1 lineup service: rebuilding a lineup from its published rows, the lineup gain
of a player for another roster (superflex by eligibility, a WR who improves FLEX), the loss for his own
roster, and the SQL replacement rule of mart_league_roster_horizon (one bench player worth value - margin
comes in when a starter is removed) against the solver on random rosters. No database needed."""

import random

import pytest

from league_lab.lineup import Player, solve
from league_lab.roster_value import RosterBoard, incoming_player, players_from_rows

DYNASTY = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", *["BN"] * 13]
SCRUBS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN", "BN", "BN", "BN", "BN"]


def rows_for(roster_id: int, week: int, players: list[Player], slots: list[str], unplayable: list[Player] = ()) -> list[dict]:
    """The lineup rows `league-lab lineups` would publish for one roster-week (starters with margins,
    bench, unplayable), built with the solver itself."""
    lu = solve(players, slots)
    out = []
    for s in lu.starts:
        if s.player is None:
            out.append({"roster_id": roster_id, "week": week, "role": "empty", "slot": s.slot.label, "slot_type": s.slot.type,
                        "sleeper_player_id": None})
            continue
        p = s.player
        out.append({"roster_id": roster_id, "week": week, "role": "starter", "slot": s.slot.label, "slot_type": s.slot.type,
                    "sleeper_player_id": p.id, "position": p.position, "fantasy_positions": list(p.positions),
                    "player_value": p.value, "value_source": p.value_source or "proj_points", "lineup_margin": s.margin,
                    "is_locked": s.locked, "reason": None})
    for p in lu.bench:
        out.append({"roster_id": roster_id, "week": week, "role": "bench", "slot": None, "slot_type": None, "sleeper_player_id": p.id,
                    "position": p.position, "fantasy_positions": list(p.positions), "player_value": p.value,
                    "value_source": p.value_source or "proj_points", "lineup_margin": None, "is_locked": False, "reason": None})
    for p in unplayable:
        out.append({"roster_id": roster_id, "week": week, "role": "unplayable", "slot": None, "slot_type": None,
                    "sleeper_player_id": p.id, "position": p.position, "fantasy_positions": list(p.positions),
                    "player_value": p.value, "value_source": "proj_points", "lineup_margin": None, "is_locked": False,
                    "reason": p.reason})
    return out


def P(pid: str, pos: str, value: float | None, **kw) -> Player:
    return Player(id=pid, position=pos, value=value, value_source="proj_points" if value is not None else None, **kw)


# a dynasty roster: two QBs, the SUPER_FLEX goes to the QB2; FLEX is a WR at 10.00 with a RB at 9.85 behind
A = [P("qb1", "QB", 32.32), P("qb2", "QB", 21.49), P("rb1", "RB", 17.86), P("rb2", "RB", 10.83), P("rb3", "RB", 9.85),
     P("wr1", "WR", 16.15), P("wr2", "WR", 14.28), P("wr3", "WR", 10.00), P("wr4", "WR", 7.20), P("te1", "TE", 7.33),
     P("te2", "TE", 6.80)]
# another roster holding the candidates
B = [P("bqb1", "QB", 25.0), P("bqb2", "QB", 19.0), P("bqb3", "QB", 15.0), P("brb1", "RB", 15.0), P("brb2", "RB", 12.0),
     P("bwr1", "WR", 18.0), P("bwr2", "WR", 13.5), P("bwr3", "WR", 12.5), P("bte1", "TE", 9.0), P("brb3", "RB", 8.0)]


def board(week_rows: list[dict], slots=DYNASTY) -> RosterBoard:
    return RosterBoard(week_rows, slots)


def test_rows_rebuild_the_lineup_to_the_cent():
    b = board(rows_for(1, 4, A, DYNASTY) + rows_for(2, 4, B, DYNASTY))
    assert b.lineup_value(1, 4) == pytest.approx(solve(A, DYNASTY).total)
    assert b.lineup_value(1, 4) == pytest.approx(32.32 + 21.49 + 17.86 + 10.83 + 16.15 + 14.28 + 7.33 + 10.00)


def test_margin_is_lineup_minus_a_fresh_solve_without_him():
    rows = rows_for(1, 4, A, DYNASTY)
    b = board(rows)
    for r in rows:
        if r["role"] == "starter":
            without = [p for p in A if p.id != r["sleeper_player_id"]]
            assert b.loss(r["sleeper_player_id"], 4) == pytest.approx(round(solve(A, DYNASTY).total - solve(without, DYNASTY).total, 2))
    assert b.loss("wr3", 4) == pytest.approx(0.15)      # FLEX 10.00 over the RB at 9.85
    assert b.loss("rb3", 4) == 0.0                      # a bench player changes nothing


def test_a_qb3_does_not_raise_a_superflex_lineup():
    b = board(rows_for(1, 4, A, DYNASTY) + rows_for(2, 4, B, DYNASTY))
    # B's QB3 (15.0) is worth less than A's QB2 at SUPER_FLEX (21.49): adding him changes nothing
    assert b.gain(1, "bqb3", 4) == 0.0
    # and removing a QB3 from a roster that has one does not move its lineup either
    three = [*A, P("qb3", "QB", 12.0)]
    assert solve(three, DYNASTY).total == pytest.approx(solve(A, DYNASTY).total)


def test_superflex_is_eligibility_not_a_qb_slot():
    # a roster whose SUPER_FLEX holds a RB (no QB2): a QB worth more than that RB is a real gain, and
    # the gain is QB value minus the RB he pushes out (the RB is then the best bench player)
    one_qb = [p for p in A if p.id != "qb2"]
    b = board(rows_for(1, 4, one_qb, DYNASTY) + rows_for(2, 4, B, DYNASTY))
    lu = solve(one_qb, DYNASTY)
    assert lu.lineup["SUPER_FLEX"][0].position == "RB" and lu.lineup["SUPER_FLEX"][1] == pytest.approx(9.85)
    assert b.gain(1, "bqb3", 4) == pytest.approx(15.0 - 9.85)


def test_a_wr_who_improves_flex_is_recognised():
    b = board(rows_for(1, 4, A, DYNASTY) + rows_for(2, 4, B, DYNASTY))
    # B's WR3 at 12.50 is no WR1/WR2 for A (16.15, 14.28) but beats A's FLEX (Tucker-like WR at 10.00):
    # A gains 12.50 - 10.00 = 2.50 through FLEX; a position-by-position count of "the top two WRs" sees 0
    assert b.gain(1, "bwr3", 4) == pytest.approx(2.50)
    # the gain is the margin he would have in A's re-solved lineup
    with_him = solve([*A, P("bwr3", "WR", 12.5)], DYNASTY)
    assert with_him.margins[next(s.slot.label for s in with_him.starts if s.player and s.player.id == "bwr3")] == pytest.approx(2.50)
    # a WR better than A's WR2 also lands at WR2 and pushes the WR2 into FLEX: gain = 18.0 - 10.0
    assert b.gain(1, "bwr1", 4) == pytest.approx(8.0)


def test_trade_fit_is_gain_minus_loss():
    b = board(rows_for(1, 4, A, DYNASTY) + rows_for(2, 4, B, DYNASTY))
    gain, loss = b.gain(1, "bwr3", 4), b.loss("bwr3", 4)
    # on B the WR3 is B's FLEX (12.50) and its RB3 (8.00) would take over: B loses 4.50, A gains 2.50
    without = [p for p in B if p.id != "bwr3"]
    assert loss == pytest.approx(round(solve(B, DYNASTY).total - solve(without, DYNASTY).total, 2)) == pytest.approx(4.50)
    assert round(gain - loss, 2) == pytest.approx(-2.00)   # he is worth more where he is: no fit


def test_players_who_cannot_play_are_worth_nothing_elsewhere_but_taxi_is_a_roster_choice():
    out = P("bout", "WR", 20.0, playable=False, reason="Out")
    taxi = P("btaxi", "WR", 11.0, playable=False, reason="taxi squad")
    rows = rows_for(1, 4, A, DYNASTY) + rows_for(2, 4, B, DYNASTY, unplayable=[out, taxi])
    b = board(rows)
    assert b.gain(1, "bout", 4) == 0.0
    assert b.gain(1, "btaxi", 4) == pytest.approx(1.0)       # 11.00 over the FLEX WR at 10.00
    assert incoming_player({"role": "starter", "is_locked": True, "sleeper_player_id": "x"}) is None
    # a locked starter keeps his slot type when a roster is rebuilt
    locked = players_from_rows([{"role": "starter", "is_locked": True, "slot_type": "WR", "sleeper_player_id": "x",
                                 "position": "WR", "player_value": 5.0, "value_source": "proj_points"}])
    assert locked[0].locked_slot == "WR"


def test_unvalued_rows_rebuild_as_unvalued():
    rows = rows_for(1, 4, [*A, Player(id="k0", position="WR", value=None)], DYNASTY)
    b = board(rows)
    assert b.lineup_value(1, 4) == pytest.approx(solve(A, DYNASTY).total)


def test_horizon_sums_weeks():
    rows = rows_for(1, 4, A, DYNASTY) + rows_for(2, 4, B, DYNASTY) + rows_for(1, 5, A, DYNASTY)
    rows += rows_for(2, 5, [p for p in B if p.id != "bwr3"], DYNASTY, unplayable=[P("bwr3", "WR", 12.5, playable=False, reason="bye")])
    b = board(rows)
    assert b.weeks == [4, 5]
    assert b.horizon_gain(1, "bwr3") == pytest.approx(2.50)   # the bye week adds nothing
    assert b.horizon_loss("bwr3") == pytest.approx(b.loss("bwr3", 4))


def _random_roster(rng: random.Random, slots: list[str]) -> list[Player]:
    n = rng.randint(8, 16)
    pos = ["QB", "RB", "WR", "TE"] + (["K", "DEF"] if "K" in slots else [])
    out = []
    for i in range(n):
        position = rng.choice(pos)
        value = round(rng.uniform(0, 30), 2) if rng.random() > 0.08 else None
        out.append(Player(id=f"p{i}", position=position, value=value, value_source="proj_points" if value is not None else None))
    return out


@pytest.mark.parametrize("slots", [DYNASTY, SCRUBS], ids=["superflex", "flex-k-def"])
@pytest.mark.parametrize("seed", range(60))
def test_the_sql_replacement_rule_matches_the_solver(slots, seed):
    """mart_league_roster_horizon names the replacement of a starter as the bench player worth value -
    margin (to the cent, positive values only). Removing a starter changes a maximum-weight matching along
    one alternating path, so the re-solved lineup brings in exactly one new player or nobody worth
    anything; check it against the solver."""
    rng = random.Random(seed)
    players = _random_roster(rng, slots)
    lu = solve(players, slots)
    bench = list(lu.bench)
    base = set(lu.starter_ids)
    for s in lu.starts:
        if s.player is None or s.margin is None:
            continue
        target = round((s.player.value - s.margin) * 100)
        named = next((b for b in bench if round(b.value * 100) == target and target > 0), None)
        without = solve([p for p in players if p.id != s.player.id], slots, margins=False)
        entered = set(without.starter_ids) - (base - {s.player.id})
        assert without.total == pytest.approx(lu.total - s.margin, abs=1e-6)
        entered_values = sorted(round(next(p for p in players if p.id == e).value or 0.0, 2) for e in entered)
        if target > 0:
            assert named is not None and entered
            assert round(named.value, 2) in entered_values
        else:
            assert all(v == 0.0 for v in entered_values)


def test_trade_candidates_buy_low_and_sell_high():
    from league_lab.roster_value import trade_candidates

    b = board(rows_for(1, 4, A, DYNASTY) + rows_for(2, 4, B, DYNASTY))
    cands = [{"sleeper_player_id": "bwr3", "diff_per_game": -2.0, "player_name": "B WR3"},    # B's FLEX: +2.50 for A, -4.50 for B
             {"sleeper_player_id": "brb3", "diff_per_game": -1.0, "player_name": "B RB3"},    # B's bench: costs B nothing
             {"sleeper_player_id": "bqb3", "diff_per_game": -3.0, "player_name": "B QB3"},    # adds nothing to A (superflex full)
             {"sleeper_player_id": "bwr1", "diff_per_game": 1.0, "player_name": "B WR1"},     # above usage but not A's: ignored
             {"sleeper_player_id": "wr3", "diff_per_game": 2.0, "player_name": "A WR3"}]      # A's sell-high candidate
    buy, sell = trade_candidates(b, 1, cands)
    by = {d["sleeper_player_id"]: d for d in buy}
    assert set(by) == {"bwr3", "brb3", "bqb3"}
    assert (by["bwr3"]["gain_week"], by["bwr3"]["loss_week"], by["bwr3"]["fit_week"]) == pytest.approx((2.50, 4.50, -2.00))
    assert by["brb3"]["gain_week"] == 0.0 and by["brb3"]["loss_week"] == 0.0     # 8.00 beats no A starter
    assert by["bqb3"]["gain_week"] == 0.0                                          # a QB3 adds nothing
    assert [d["sleeper_player_id"] for d in buy][0] in {"brb3", "bqb3"}            # fit 0 beats fit -2
    assert len(sell) == 1 and sell[0]["partner"] == 2
    # A's FLEX WR (10.00) on B: B's FLEX is 12.50 and its RB3 8.00 is the next man: he beats nobody there
    assert sell[0]["loss_week"] == pytest.approx(0.15) and sell[0]["gain_week"] == 0.0
