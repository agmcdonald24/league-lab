"""IX-1 (Wave I-X), lf1.0: a game left early — the Stats columns, the game log's mark, the card's projected target share
(docs/METRICS.md § "A game left early"). Pure: the database parts are replaced by frames."""

from __future__ import annotations

import pandas as pd

from league_lab_api import onfield as OF
from league_lab_api import stats as ST


def _games(**over) -> pd.DataFrame:
    """One receiver, two games: a full one (participation) and one he left early (snaps: 3 of 53 team targets at 20%)."""
    base = {c: 0 for c in ST.SUMS + ST.TEAM_SUMS + ["team_dropbacks_with_participation", "passing_cpoe", "offense_snap_pct"]}
    g1 = {**base, "gsis_id": "x", "player_name": "X", "position": "WR", "game_id": "g1", "week": 1, "played": True,
          "snaps_known": True, "offense_snap_pct": 0.94, "targets": 9, "team_targets": 31, "routes_proxy": None,
          "routes": None, "team_charted_targets": 0, "passing_cpoe": None,
          "on_field_basis": "participation", "on_field_targets": 9, "on_field_team_targets": 29,
          "on_field_carries": 0, "on_field_team_carries": 20, "left_early": False}
    g2 = {**g1, "game_id": "g2", "week": 2, "offense_snap_pct": 0.2, "targets": 3, "team_targets": 53,
          "on_field_basis": "snaps", "on_field_targets": 3, "on_field_team_targets": 10.6, "on_field_team_carries": 5.0,
          "left_early": True}
    return pd.DataFrame([{**g1, **over}, {**g2, **over}])


def test_the_two_columns_are_in_the_catalogue_with_a_definition_and_the_basis():
    cat = {c["id"]: c for c in ST.CATALOGUE}
    t, c = cat["on_field_target_share"], cat["on_field_carry_share"]
    assert t["label"] == "Target share on the field" and set(t["positions"]) == {"RB", "WR", "TE"}
    assert c["label"] == "Carry share on the field" and c["positions"] == ["RB"]
    for col in (t, c):
        assert "on the plays he was on the field" in col["definition"] and "2026: estimated" in col["definition"]
        assert "participation" in col["source"] and "snap counts" in col["source"]
    assert "on_field_target_share" in ST.GROUP_ORDER["Receiving"] and "on_field_carry_share" in ST.GROUP_ORDER["Rushing"]


def test_a_window_sums_the_on_field_parts_and_says_its_basis():
    a = ST.aggregate(_games()).iloc[0]
    assert a["target_share"] == round(12 / 84, 4)                      # the whole games: dragged down by game 2
    assert a["on_field_target_share"] == round(12 / 39.6, 4)            # on the field: (9 + 3) / (29 + 10.6)
    assert a["on_field_basis"] == "mixed" and a["left_early_games"] == 1
    assert a["on_field_participation_games"] == 1 and a["on_field_snap_games"] == 1


def test_a_frame_without_the_columns_is_unknown_never_zero():
    a = ST.aggregate(_games().drop(columns=[*ST.ON_FIELD_COLS])).iloc[0]
    assert pd.isna(a["on_field_target_share"]) and a["on_field_basis"] is None and a["left_early_games"] == 0


def test_the_projected_target_share_is_his_lines_over_his_teams(monkeypatch):
    monkeypatch.setattr(OF, "query", lambda sql, params: pd.DataFrame([{"proj_targets": 8.0, "team_proj_targets": 46.3,
                                                                         "players": 13}]))
    d = OF.projected_target_share("00-0036900", "WR", 2026, 5)
    assert d["share"] == round(8 / 46.3, 4) and d["week"] == 5 and d["players"] == 13
    assert d["words"] == ("8.0 of his team's 46.3 projected targets in week 5 (17%): the model's own forecast of his "
                          "share of the team's targets this week.")
    assert "from ops.projection_lines as l" in OF.PTS_SQL                # the live week rewrites this form (db._run)
    assert OF.projected_target_share("x", "QB", 2026, 5) is None         # no quarterback share
    assert OF.projected_target_share("x", "WR", 2026, 5, sits=True) is None
    monkeypatch.setattr(OF, "query", lambda sql, params: pd.DataFrame([{"proj_targets": 0.0, "team_proj_targets": 0.0,
                                                                         "players": 0}]))
    assert OF.projected_target_share("x", "WR", 2026, 5) is None         # a team total of 0: no share, never 0 / 0


def test_the_game_log_marks_a_game_left_early_and_adds_a_missed_next_week_for_display(monkeypatch):
    log = pd.DataFrame([{"game_id": "g4", "team": "CIN", "week": 4, "season_type": "REG", "played": True},
                        {"game_id": "g3", "team": "CIN", "week": 3, "season_type": "REG", "played": True}])
    marks = pd.DataFrame([{"game_id": "g4", "left_early": True, "on_field_target_share": 0.283, "on_field_carry_share": 0,
                           "on_field_basis": "snaps",
                           "left_early_reason": "15 snaps (20% of the team's; usually 94%); hurt on a play in the 2nd quarter"},
                          {"game_id": "g3", "left_early": False, "left_early_reason": None, "on_field_target_share": 0.32,
                           "on_field_carry_share": 0, "on_field_basis": "snaps"}])
    sched = pd.DataFrame([{"game_id": "g5", "week": 5, "season_type": "REG", "team": "CIN", "has_rows": True}])
    monkeypatch.setattr(OF, "query", lambda sql, params: marks if sql == OF.ONFIELD_SQL else sched)
    out = OF.game_log_marks(log, "00-0036900", 2026).set_index("game_id")
    assert out.loc["g4", "left_early"] and not out.loc["g3", "left_early"]
    assert out.loc["g4", "left_early_reason"].endswith("hurt on a play in the 2nd quarter; then missed week 5")
    sched.loc[0, "has_rows"] = False                                     # week 5 not in yet: nothing is said
    out = OF.game_log_marks(log, "00-0036900", 2026).set_index("game_id")
    assert out.loc["g4", "left_early_reason"].endswith("2nd quarter")
