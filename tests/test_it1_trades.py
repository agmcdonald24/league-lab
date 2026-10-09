"""Wave I-T, IT-1 — the best waiver move searched on the replacement frame (`trades.basis_best_move`), no database.

A quarterback on a bye leaves the QB slot empty: on the roster-only numbers the best claim is the free quarterback (his
whole projection fills the empty slot); on the replacement frame the free quarterback already covers that slot, so the
best move is the free running back who beats a starter."""

from league_lab.lineup import Player
from league_lab.roster_value import RosterBoard
from league_lab.trades import _free_by_week, basis_best_move, best_fill

from .test_trades import P, U, rows_for

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "BN", "BN"]
ME = [P("aqb", "QB", 20), P("arb1", "RB", 15), P("arb2", "RB", 9), P("awr1", "WR", 16), P("awr2", "WR", 14),
      P("ate", "TE", 9), P("awr3", "WR", 8), P("ak", "K", 8)]
FREE = [P("fqb", "QB", 17.0), P("frb", "RB", 13.0), P("fwr", "WR", 4.0)]


def board(extra=()) -> RosterBoard:
    rows = rows_for(1, 5, [p for p in ME if p.id != "aqb"] + list(extra), SLOTS, [U("aqb", "QB", None, "bye")])
    rows += rows_for(1, 6, ME + list(extra), SLOTS)
    return RosterBoard(rows, SLOTS)


def pool() -> dict[str, dict[int, Player]]:
    return {p.id: {5: p, 6: p} for p in FREE}


def test_the_roster_only_pick_is_the_bye_cover_the_basis_pick_beats_a_starter():
    b = board()
    weeks = (5, 6)
    raw = best_fill(b, weeks, [b.pool(1, w) for w in weeks], pool())
    assert raw is not None and raw.player_id == "fqb"                  # 17 points into an empty QB slot
    add, drop, by = basis_best_move(b, 1, weeks, _free_by_week(pool(), weeks), pool())
    assert (add, drop) == ("frb", None)        # an open spot: RB2 9 → 13, and the 9 moves to FLEX over the 8
    assert by == (5.0, 5.0)


def test_a_full_roster_drops_its_cheapest_bench_player():
    b = board(extra=[P("abn1", "WR", 3), P("abn2", "RB", 2)])           # 10 players: the limit
    weeks = (5, 6)
    add, drop, by = basis_best_move(b, 1, weeks, _free_by_week(pool(), weeks), pool(),
                                    market={"abn1": 40.0, "abn2": 10.0, "arb2": 90.0})
    assert add == "frb" and drop == "abn2" and by == (5.0, 5.0)


def test_no_move_when_nobody_beats_the_covered_lineup():
    b = board()
    weak = {"fwr": {5: P("fwr", "WR", 4.0), 6: P("fwr", "WR", 4.0)}}
    assert basis_best_move(b, 1, (5, 6), _free_by_week(weak, (5, 6)), weak) is None
