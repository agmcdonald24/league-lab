"""JB-3: the after-publish check's trade, chosen from the current rosters (scripts/post_deploy_trade.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("post_deploy_trade",
                                               Path(__file__).resolve().parents[1] / "scripts" / "post_deploy_trade.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)


def row(key, pos, v, role="bench", flag="", slot="BN"):
    return {"key": key, "position": pos, "value": v, "role": role, "flag": flag, "slot": slot, "player_name": f"P{key}"}


WEEKS = {
    1: {"lineup_full": [row("1", "QB", 20, role="starter", slot="QB"), row("2", "WR", 9.0), row("3", "RB", 11.0, flag="IR slot"),
                        row("4", "K", 12.0), row("5", "TE", 0.0)]},
    6: {"lineup_full": [row("6", "RB", 7.5), row("7", "WR", 7.5), row("8", "QB", 15.0, role="unplayable", flag="game started (bench)")]},
    9: {"lineup_full": [row("9", "WR", 3.0, role="starter")]},
}


def fake_call(teams):
    def call(method, path):
        if path.endswith("/rosters"):
            return 200, 0.0, [{"roster_id": t} for t in teams]
        rid = int(path.rsplit("team=", 1)[1])
        return (200, 0.0, WEEKS[rid]) if rid in WEEKS else (404, 0.0, {"error": "no such team"})
    return call


def test_a_bench_player_with_a_projection_from_each_of_two_teams():
    trade, words = T.live_trade(fake_call([1, 6]))
    assert trade["team"] == 1 and trade["partner"] == 6
    assert trade["give"] == ["2"] and trade["get"] == ["8"]       # not the starter, not IR, not a kicker, not 0 points
    assert "team 1 gives P2 (WR, key 2) for team 6's P8 (QB, key 8)" == words


def test_a_team_without_a_candidate_is_skipped():
    trade, _ = T.live_trade(fake_call([9, 1, 6]))
    assert (trade["team"], trade["partner"]) == (1, 6)


def test_ties_choose_the_lower_key_so_the_pick_is_stable():
    assert T.candidate({"lineup_full": [row("7", "WR", 7.5), row("6", "RB", 7.5)]})["key"] == "6"


def test_no_two_teams_is_said_not_guessed():
    trade, why = T.live_trade(fake_call([9]))
    assert trade is None and "team list" in why or "no two" in why
    trade, why = T.live_trade(fake_call([9, 404]))
    assert trade is None and why.startswith("no two of the first")
