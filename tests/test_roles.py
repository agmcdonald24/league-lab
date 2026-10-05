"""IL-1 (Wave I-L): role changes, opportunity vs production, contingent upside — on frames built here (no database)."""

from __future__ import annotations

import pandas as pd
from league_lab import roles


def games(targets, carries=None, snaps=None, rz=None, *, start_week=1, gsis="P1", team="CIN", position="WR",
          points=None, season=2025):
    n = len(targets)
    carries = carries or [0] * n
    snaps = snaps or [0.8] * n
    rz = rz or [0] * n
    points = points or [10.0] * n
    return pd.DataFrame({
        "gsis_id": gsis, "player_name": "Player One", "game_id": [f"{season}_{start_week + i:02d}_{team}" for i in range(n)],
        "season": season, "week": [start_week + i for i in range(n)], "team": team, "position": position,
        "played": True, "snaps_known": True, "offense_snaps": [round(s * 60) for s in snaps], "offense_snap_pct": snaps,
        "targets": targets, "carries": carries, "attempts": 0, "red_zone_targets": rz, "red_zone_carries": 0,
        "team_targets": 35, "team_carries": 25, "team_attempts": 35, "team_red_zone_targets": 6,
        "team_red_zone_carries": 5, "points": points})


# ------------------------------------------------------------------------------------------------- role change
def test_a_role_change_past_the_spread_is_named():
    out = roles.role_change(games([5, 6, 5, 6, 6, 9, 8]), "WR")
    t = next(m for m in out["metrics"] if m["metric"] == "targets")
    assert out["status"] == "changed" and t["named"] and t["direction"] == "up"
    assert t["games_recent"] == 2 and t["games_earlier"] == 5
    assert round(t["recent"], 1) == 8.5 and round(t["earlier"], 1) == 5.6
    assert t["change"] > t["spread"]
    assert out["headline"] == "Targets up: 8.5 per game in his last 2, 5.6 in the 5 before."
    # no regression claim, no forecast
    assert not any(w in out["headline"].lower() for w in ("regress", "will continue", "due"))


def test_a_change_inside_the_earlier_spread_is_steady():
    out = roles.role_change(games([2, 9, 3, 10, 4, 8, 9]), "WR")
    t = next(m for m in out["metrics"] if m["metric"] == "targets")
    assert round(t["change"], 1) == 2.9 and t["spread"] > t["change"]          # 8.5 vs 5.6, s.d. 3.6
    assert not t["named"] and t["direction"] == "steady"
    assert t["words"].startswith("Targets steady: 8.5 per game in his last 2, 5.6 in the 5 before (inside his usual swing")
    assert out["status"] == "steady" and out["headline"].startswith("Role steady:")


def test_a_tiny_metric_needs_the_floor_too():
    # a receiver's carries go from 0 to 0.5 per game: past a zero spread, under the 1.0 floor — not a change
    out = roles.role_change(games([6] * 7, carries=[0, 0, 0, 0, 0, 1, 0]), "WR")
    c = next(m for m in out["metrics"] if m["metric"] == "carries")
    assert c["spread"] == 0 and c["change"] == 0.5 and not c["named"]


def test_not_enough_games_yet():
    out = roles.role_change(games([5, 6, 9, 8]), "WR")
    assert out["status"] == "too_early" and out["games_recent"] == 2 and out["games_earlier"] == 2
    assert out["headline"].startswith("Too early to say: 4 games with a snap so far this season")
    assert all(not m["named"] for m in out["metrics"])


def test_a_game_without_a_snap_is_not_in_either_window():
    g = games([5, 6, 5, 6, 6, 9, 8])
    g.loc[6, ["offense_snaps", "offense_snap_pct", "played"]] = [0, 0.0, False]   # week 7: no snap
    out = roles.role_change(g, "WR")
    t = next(m for m in out["metrics"] if m["metric"] == "targets")
    assert t["games_recent"] == 2 and t["games_earlier"] == 4 and round(t["recent"], 1) == 7.5   # weeks 5–6


# ------------------------------------------------------------------------------------------------- opportunity vs production
def _group(his: pd.DataFrame, mate_targets: list[int], mate_points: list[float]) -> pd.DataFrame:
    mate = games(mate_targets, gsis="P2", points=mate_points)
    return pd.concat([his, mate], ignore_index=True)


def test_opportunity_vs_production_labels():
    his = games([6, 6, 6, 6], points=[20.0] * 4)
    # he has half the WR targets and 2/3 of the WR points: production ahead of his volume
    out = roles.opportunity_vs_production(his, _group(his, [6, 6, 6, 6], [10.0] * 4), "WR", scoring="League of Scrubs")
    assert out["label"] == "production ahead of his volume"
    assert round(out["opportunity_share"], 3) == 0.5 and round(out["production_share"], 3) == 0.667
    assert "50% of the targets and carries of his team's WRs and TEs, 67% of their fantasy points" in out["words"]
    assert "Of the whole team: 10% of its targets + carries, 0% of its red-zone targets." in out["words"]   # 24 of 4 x 60
    # the reverse
    out = roles.opportunity_vs_production(games([6] * 4, points=[5.0] * 4), _group(games([6] * 4, points=[5.0] * 4),
                                          [6] * 4, [15.0] * 4), "WR")
    assert out["label"] == "volume ahead of his production"
    # equal conversion
    out = roles.opportunity_vs_production(his, _group(his, [6] * 4, [20.0] * 4), "WR")
    assert out["label"] == "in line"
    assert not any(w in out["words"].lower() for w in ("regress", "unsustainable", "due for"))


def test_opportunity_vs_production_needs_two_games():
    his = games([6])
    out = roles.opportunity_vs_production(his, his, "WR")
    assert out["status"] == "too_early" and out["label"] is None


# ------------------------------------------------------------------------------------------------- contingent upside
def _pair(missed: int):
    """He plays 6 games (2025 weeks 1–6); the teammate is on the roster all six and plays all but the last `missed`."""
    his = games([5, 5, 5, 5, 9, 10], points=[8.0, 9.0, 8.0, 9.0, 15.0, 16.0])
    mate = games([8] * 6, gsis="P2", points=[14.0] * 6)
    mate = mate.iloc[: 6 - missed]
    roster = pd.DataFrame({"season": 2025, "week": range(1, 7), "game_id": list(his["game_id"])})
    return his, mate, roster


def test_pick_teammate_takes_the_top_target_share_at_his_position():
    his = games([5] * 3)
    wr2 = games([9] * 3, gsis="P2")
    te = games([4] * 3, gsis="P3", position="TE")
    rb = games([12] * 3, gsis="P4", position="RB")
    mate = roles.pick_teammate(pd.concat([his, wr2, te, rb]), "P1", "WR")
    assert mate["gsis_id"] == "P2" and round(mate["share"], 3) == round(9 / 35, 3)


def test_contingent_upside_with_two_games_without_him():
    his, mate, roster = _pair(2)
    m = {"gsis_id": "P2", "player_name": "Ja'Marr Chase", "position": "WR"}
    out = roles.contingent_upside(his, mate, roster, m, "WR", scoring="League of Scrubs")
    assert out["status"] == "ok" and out["games_without"] == 2 and out["games_with"] == 4
    assert out["without"] == {"opportunity": 9.5, "points": 15.5} and out["with"] == {"opportunity": 5.0, "points": 8.5}
    assert out["words"].startswith("Contingent upside: in the 2 games without Ja'Marr Chase (2025), 9.5 targets and "
                                   "15.5 points per game, against 5.0 and 8.5 in the 4 games with him (2025).")
    assert "not a forecast" in out["words"] and "%" not in out["words"]            # no probability


def test_contingent_upside_with_one_game_is_not_enough():
    his, mate, roster = _pair(1)
    out = roles.contingent_upside(his, mate, roster, {"gsis_id": "P2", "player_name": "Ja'Marr Chase"}, "WR")
    assert out["status"] == "not_enough" and out["games_without"] == 1
    assert out["words"].startswith("Contingent upside: no games without Ja'Marr Chase to go on — only 1 game without him (2025)")


def test_a_game_before_the_teammate_joined_is_not_a_game_without_him():
    his, mate, roster = _pair(2)
    roster = roster[roster["week"] <= 5]                 # week 6: he was not on the roster yet → not "without him"
    out = roles.contingent_upside(his, mate, roster, {"gsis_id": "P2", "player_name": "X"}, "WR")
    assert out["games_without"] == 1 and out["status"] == "not_enough"


def test_contingent_upside_says_when_there_is_little_to_compare_against():
    his, mate, roster = _pair(5)                         # the teammate played only week 1 with him
    out = roles.contingent_upside(his, mate, roster, {"gsis_id": "P2", "player_name": "X"}, "WR")
    assert out["status"] == "ok" and out["games_without"] == 5 and out["games_with"] == 1
    assert "; only 1 game with him to compare against (2025)." in out["words"]

