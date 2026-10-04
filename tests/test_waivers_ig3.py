"""IG-3 (Wave I-G): the nightly stash writer's drop follows IF-1's ``choose_drops`` (synthetic rosters, no database).

Before: ``upside_for_roster`` named the drop that costs the lineup least over the horizon (B3's rule, ties to the fewest
rest-of-season points), so a bench player worth keeping was a free drop, and the API re-decided claim / watch on read.
After: every legal drop is priced like an ``ops.waiver_moves`` row (the lineup loss with the add, plus the drop pieces)
and ``choose_drops`` names the cheapest; the row carries ``stash_action`` ('claim' when the pairing is worth a roster
spot if the role holds, else 'watch')."""

from __future__ import annotations

import pytest

from league_lab import waivers as W
from league_lab.lineup import Player

SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "BN", "BN"]


def P(pid: str, pos: str, v: float) -> Player:
    return Player(id=pid, position=pos, value=v, value_source="proj_points")


def roster() -> list[Player]:
    return [P("qb", "QB", 20.0), P("rb", "RB", 12.0), P("wr", "WR", 13.0), P("te", "TE", 8.0), P("flex", "WR", 9.0),
            P("bn1", "RB", 5.0), P("bn2", "WR", 2.0)]


def pieces(bn1_value: float = 0.0, bn2_value: float = 0.0) -> dict:
    """Each bench player's value pieces as ``drop_pieces`` writes them (season value above the best free agent)."""
    base = {"drop_depth_lost": 0.0, "drop_future_starts": 0.0, "drop_future_start_weeks": 0, "drop_upside": None,
            "drop_replacement_points": 40.0}
    return {"bn1": {**base, "drop_season_value": bn1_value, "drop_season_points": 40.0 + bn1_value},
            "bn2": {**base, "drop_season_value": bn2_value, "drop_season_points": 40.0 + bn2_value}}


ROS = {"bn1": 50.0, "bn2": 20.0}


def stash(holds_value: float, pcs: dict | None) -> W.Stash:
    weeks = [roster() for _ in range(4)]
    base = [P("fa", "WR", 6.0)] * 4
    holds = [P("fa", "WR", holds_value)] * 3 + [P("fa", "WR", 6.0)]       # the scenario covers three of the four weeks
    [s] = W.upside_for_roster(SLOTS, weeks, {"fa": base}, {"fa": holds}, ["bn1", "bn2"], False, ROS, pcs)
    return s


def test_without_pieces_the_tie_goes_to_the_fewest_season_points():
    """Both bench players cost the lineup nothing: B3's and choose_drops' tie-break agree (the fewer points)."""
    s = stash(11.0, None)
    assert s.drop == "bn2" and s.drop_loss == 0.0
    assert s.holds_gains == pytest.approx((2.0, 2.0, 2.0, 0.0)) and s.base_gains == (0.0, 0.0, 0.0, 0.0)


def test_a_bench_player_worth_keeping_is_not_the_free_drop():
    """B3 would drop bn2 (fewest rest-of-season points). He is worth 30 season points above the best free-agent WR, bn1
    nothing: choose_drops drops bn1 — the same drop the Waivers screen names for a claim of the same player."""
    s = stash(11.0, pieces(bn2_value=30.0))
    assert s.drop == "bn1"
    assert s.choice["drop_cost"] == 0.0 and s.choice["net_horizon_gain"] == pytest.approx(6.0)
    rows = [{"add_sleeper_id": "fa", "drop_sleeper_id": d, "list_kind": "upside", "weekly_gain": 2.0, "horizon_gain": 6.0,
             "add_horizon_gain": 6.0, "drop_ros_points": ROS[d], **{k: pieces(bn2_value=30.0)[d].get(k) for k in W.STASH_PIECE_KEYS}}
            for d in ("bn1", "bn2")]
    best = next(r for r in W.choose_drops(rows) if r["is_best_drop"])
    assert best["drop_sleeper_id"] == s.drop and best["net_horizon_gain"] == s.choice["net_horizon_gain"]


def test_claim_when_worth_a_roster_spot_if_it_holds():
    """+2 per week for three weeks (6 over the horizon) clears the 3-point bar: claim, dropping the free bench player."""
    s = stash(11.0, pieces(bn2_value=30.0))
    assert s.choice["stash_action"] == "claim"


def test_watch_when_under_the_bar():
    """+0.5 per week if it holds (1.5 over the horizon): under 1 this week and 3 over the weeks — watch, no claim yet."""
    s = stash(9.5, pieces())
    assert s.holds_gains == pytest.approx((0.5, 0.5, 0.5, 0.0))
    assert s.choice["stash_action"] == "watch" and s.choice["net_horizon_gain"] == pytest.approx(1.5)


def test_every_drop_worth_more_than_the_role_adds_is_a_watch():
    """Both bench players are worth more than the stash adds if it holds: the cheapest (bn1, 12 season points above the
    wire) costs 12 beyond the lineup numbers, so the +6 nets -6 — watch."""
    s = stash(11.0, pieces(bn1_value=12.0, bn2_value=30.0))
    assert s.drop == "bn1" and s.choice["drop_cost"] == pytest.approx(12.0)
    assert s.choice["net_horizon_gain"] == pytest.approx(6.0 - 12.0) and s.choice["stash_action"] == "watch"


def test_an_open_roster_spot_never_drops():
    weeks = [roster()[:-1] for _ in range(4)]                                  # bn2 gone: a bench spot is open
    holds = [P("fa", "WR", 11.0)] * 4
    [s] = W.upside_for_roster(SLOTS, weeks, {"fa": [P("fa", "WR", 6.0)] * 4}, {"fa": holds}, ["bn1"], True, ROS, pieces())
    assert s.drop is None and s.choice["drop_cost"] is None and s.choice["stash_action"] == "claim"


def test_the_stash_drop_equals_the_moves_best_drop():
    """When the scenario equals his projection the stash is an ordinary move: the stash writer's drop is the drop the
    move writer (roster_moves + choose_drops, as sweep_roster writes ops.waiver_moves) names for the same add."""
    weeks = [roster() for _ in range(4)]
    fa = [P("fa", "WR", 11.0)] * 4
    pcs = pieces(bn2_value=30.0)
    moves = W.roster_moves(SLOTS, weeks, {"fa": fa}, ["bn1", "bn2"], False)
    rows = [{"add_sleeper_id": m.add, "drop_sleeper_id": m.drop, "list_kind": W.list_kind(m), "weekly_gain": m.weekly_gain,
             "horizon_gain": m.horizon_gain, "add_horizon_gain": sum(m.add_alone), "drop_ros_points": ROS.get(m.drop),
             "displaced_sleeper_id": m.displaced, **{k: (pcs.get(m.drop) or {}).get(k) for k in W.STASH_PIECE_KEYS}}
            for m in moves]
    best = next(r for r in W.choose_drops(rows) if r["is_best_drop"])
    [s] = W.upside_for_roster(SLOTS, weeks, {"fa": fa}, {"fa": fa}, ["bn1", "bn2"], False, ROS, pcs)
    assert s.drop == best["drop_sleeper_id"] == "bn1"
    assert s.choice["net_horizon_gain"] == pytest.approx(best["net_horizon_gain"])
    assert s.choice["stash_action"] == ("claim" if best["is_worthwhile"] else "watch")


def test_choose_drops_finds_nothing_to_change_on_its_own_rows():
    """The API re-runs choose_drops on the mart's rows (decisions.if1_choose): on rows the writer ranked it is a fixed
    point — the same best drop, rank and net gains for every add."""
    weeks = [roster() for _ in range(4)]
    adds = {"fa": [P("fa", "WR", 11.0)] * 4, "fb": [P("fb", "RB", 13.0)] * 4}
    pcs = pieces(bn1_value=3.0, bn2_value=30.0)
    rows = [{"add_sleeper_id": m.add, "drop_sleeper_id": m.drop, "list_kind": W.list_kind(m), "weekly_gain": m.weekly_gain,
             "horizon_gain": m.horizon_gain, "add_horizon_gain": sum(m.add_alone), "drop_ros_points": ROS.get(m.drop),
             "displaced_sleeper_id": m.displaced, **{k: (pcs.get(m.drop) or {}).get(k) for k in W.STASH_PIECE_KEYS}}
            for m in W.roster_moves(SLOTS, weeks, adds, ["bn1", "bn2"], False)]
    once = W.choose_drops(rows)
    twice = W.choose_drops(once)
    key = ("add_sleeper_id", "drop_sleeper_id", "move_rank", "is_best_drop", "add_rank", "net_horizon_gain", "drop_cost")
    assert [tuple(r[k] for k in key) for r in once] == [tuple(r[k] for k in key) for r in twice]


def test_the_writer_columns():
    """ops.waiver_upside: the base DDL unchanged (the view's pre-hook copy, test_signals), the call added after it."""
    assert W.UPSIDE_ALL_COLUMNS == [*W.UPSIDE_COLUMNS, *W.UPSIDE_COST_COLUMNS]
    assert W.UPSIDE_COST_COLUMNS == ["stash_action", "drop_cost", "drop_cost_piece", "net_weekly_gain", "net_horizon_gain"]
    assert all(f" {c} " in d for c, d in zip(W.UPSIDE_COST_COLUMNS, W.UPSIDE_COST_DDL, strict=True))
