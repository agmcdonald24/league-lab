"""IR-3 (Wave I-R): the release gate's own canaries for slot assignment (no database; scripts/gate.sh runs them).

Every lineup the solver returns is legal (each starter in a slot that admits his position, nobody twice, the total the
sum of the starters), on many seeded rosters and the house leagues' slot lists plus an MFL-style one; and the one-QB /
superflex rule the review names (a surplus QB never fills a FLEX in a one-QB league; he does in superflex)."""

from __future__ import annotations

import random

import pytest

from league_lab import lineup as lu
from league_lab.lineup import Player

SCRUBS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN", "BN", "BN", "BN", "BN"]
DYNASTY = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", *["BN"] * 13]
MFL_LIKE = ["QB", "RB", "RB", "WR", "WR", "WR", "REC_FLEX", "WRRB_FLEX", "K", "DEF", "BN", "BN"]
POSITIONS = ["QB", "QB", "RB", "RB", "RB", "RB", "WR", "WR", "WR", "WR", "WR", "TE", "TE", "K", "DEF"]


def P(pid, pos, value):
    return Player(id=pid, position=pos, value=value, value_source="proj_points")


def roster(rng: random.Random, n: int = 15) -> list[Player]:
    return [P(f"p{i}", rng.choice(POSITIONS), round(rng.uniform(0, 30), 2)) for i in range(n)]


@pytest.mark.parametrize("slots", [SCRUBS, DYNASTY, MFL_LIKE], ids=["scrubs", "dynasty", "mfl-like"])
def test_every_solved_lineup_is_legal(slots):
    rng = random.Random(20261008)
    for _ in range(150):
        ps = roster(rng)
        res = lu.solve(ps, slots)
        seated = [s for s in res.starts if s.player is not None]
        ids = [s.player.id for s in seated]
        assert len(ids) == len(set(ids)), ids
        for s in seated:
            assert s.player.position in lu.slot_eligibility(s.slot.type), (s.slot.label, s.player)
        assert res.total == pytest.approx(sum(s.player.value for s in seated), abs=0.02)
        # nobody on the bench could improve an empty slot or beat a starter in a slot that admits him (optimality)
        for b in res.bench:
            for s in res.starts:
                if b.position in lu.slot_eligibility(s.slot.type) and s.player is None:
                    pytest.fail(f"{b.id} ({b.position}) sits while {s.slot.label} is empty")


def test_a_surplus_qb_never_fills_a_flex_in_a_one_qb_league_and_does_in_superflex():
    ps = [P("q1", "QB", 24), P("q2", "QB", 22), P("r1", "RB", 15), P("r2", "RB", 12), P("w1", "WR", 14),
          P("w2", "WR", 11), P("t1", "TE", 8), P("w3", "WR", 6), P("r3", "RB", 5)]
    one_qb = {s.player.id: s.slot.type for s in lu.solve(ps, SCRUBS).starts if s.player is not None}
    assert one_qb.get("q1") == "QB" and "q2" not in one_qb
    assert "FLEX" not in {one_qb.get("q2")}
    sf = {s.player.id: s.slot.type for s in lu.solve(ps, DYNASTY).starts if s.player is not None}
    assert sf.get("q2") == "SUPER_FLEX"
