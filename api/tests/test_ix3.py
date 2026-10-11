"""IX-3 (Wave I-X): Stats — a table that opens on an answer. The named views (at most eight columns, one question
each), the situation filter (IX-2's three groups, the same floor; a column that cannot be split is unknown, never the
all-plays number), and no internal name in what the screen prints."""

import numpy as np
import pandas as pd
import pytest

from league_lab_api import player as P
from league_lab_api import stats as ST

CHASE = "00-0036900"


def test_every_view_answers_one_question_in_at_most_eight_columns():
    for key in ("wrte", "rb", "qb", "all"):
        vs = ST.views(key)
        assert [v["key"] for v in vs][0] == "key"
        for v in vs:
            assert 2 <= len(v["columns"]) <= 8, (key, v["key"])
            assert v["columns"][0] == "games" and v["question"].strip()
            assert all(c in ST.CAT or c == "ros_value" for c in v["columns"]), (key, v["key"])
    assert {v["label"] for v in ST.views("wrte")} == {"Key stats", "Production", "Opportunity", "Role changes", "Efficiency",
                                                      "Advanced"}
    # IX-1's two on-field columns are in the Opportunity view
    opp = {v["key"]: v["columns"] for v in ST.views("rb")}["opportunity"]
    assert {"on_field_target_share", "on_field_carry_share"} <= set(opp)
    assert "on_field_target_share" in {v["key"]: v["columns"] for v in ST.views("wrte")}["opportunity"]
    # a season's catalogue drops what it does not have; a view left with games alone is not offered
    cat = [{**c, "available": c["id"] in ("games", "points", "attempts", "passing_yards")} for c in ST.CATALOGUE]
    qb = {v["key"]: v["columns"] for v in ST.views("qb", cat)}
    assert "role" not in qb and qb["key"] == ["games", "points", "attempts", "passing_yards"]


def test_the_situation_groups_are_ix2s():
    assert {k: v[0] for k, v in ST.SITUATION_WORDS.items()} == {k: label for k, label, _, _ in P.SITUATIONS}
    assert ST.SITUATION_MIN_PLAYS == P.SITUATION_MIN_PLAYS == 20


def _agg():
    return pd.DataFrame([
        {"gsis_id": "a", "player_name": "A", "position": "WR", "games": 4, "points": 50.0, "targets": 30,
         "target_share": 0.2, "snap_share": 0.9, "receiving_yards": 300, "on_field_target_share": 0.25},
        {"gsis_id": "b", "player_name": "B", "position": "WR", "games": 2, "points": 9.0, "targets": 5,
         "target_share": 0.1, "snap_share": 0.4, "receiving_yards": 40, "on_field_target_share": 0.1},
        {"gsis_id": "c", "player_name": "C", "position": "RB", "games": 1, "points": 3.0, "targets": 1,
         "target_share": 0.05, "snap_share": 0.3, "receiving_yards": 8, "on_field_target_share": 0.05},
    ])


def _sit():
    rows = []
    for g in ("g1", "g2"):
        rows.append({"gsis_id": "a", "game_id": g, "situation": "trailing", "team_plays": 30, "team_targets": 20,
                     "team_carries": 8, "targets": 6, "receptions": 4, "receiving_yards": 50, "carries": 0,
                     "rushing_yards": 0})
    rows.append({"gsis_id": "a", "game_id": "g9", "situation": "trailing", "team_plays": 99, "team_targets": 50,
                 "team_carries": 40, "targets": 20, "receptions": 9, "receiving_yards": 90, "carries": 0, "rushing_yards": 0})
    rows.append({"gsis_id": "b", "game_id": "g1", "situation": "trailing", "team_plays": 14, "team_targets": 9,
                 "team_carries": 4, "targets": 3, "receptions": 2, "receiving_yards": 20, "carries": 0, "rushing_yards": 0})
    rows.append({"gsis_id": "b", "game_id": "g1", "situation": "close", "team_plays": 40, "team_targets": 20,
                 "team_carries": 15, "targets": 2, "receptions": 1, "receiving_yards": 9, "carries": 0, "rushing_yards": 0})
    return pd.DataFrame(rows)


def test_a_situation_sums_the_windows_games_and_leaves_the_rest_unknown():
    games = pd.DataFrame({"gsis_id": ["a", "a", "b", "c"], "game_id": ["g1", "g2", "g1", "g1"]})   # g9: outside the window
    out = ST.with_situation(_agg(), games, "trailing", _sit()).set_index("gsis_id")
    a, b, c = out.loc["a"], out.loc["b"], out.loc["c"]
    assert a["targets"] == 12 and a["team_targets"] == 40 and a["situation_plays"] == 60
    assert a["target_share"] == pytest.approx(0.3) and a["receiving_yards"] == 100
    assert a["targets_per_game"] == pytest.approx(3.0)                 # his trailing targets / his games in the window
    # under 20 of his team's plays: the count stands, the share is unknown ("too few to read")
    assert b["situation_plays"] == 14 and b["targets"] == 3 and np.isnan(b["target_share"])
    # his team never trailed in his games: unknown, not 0
    assert c["situation_plays"] == 0 and np.isnan(c["targets"]) and np.isnan(c["target_share"])
    # a column the plays cannot split is unknown, never the all-plays number
    for col in ("points", "snap_share", "on_field_target_share"):
        assert out[col].isna().all(), col
    assert list(out["games"]) == [4, 2, 1]                              # the window's games stay (the sample)
    # no mart on this copy: every number unknown, the frame still answers
    none = ST.with_situation(_agg(), games, "close", None)
    assert none["targets"].isna().all() and none["situation_plays"].isna().all()


def test_stats_by_situation_on_this_copy(client, sql):
    q = {"league": "ref:half", "window": "season", "position": "WR,TE", "limit": 1000}
    bad = client.get("/api/players", params={**q, "situation": "losing"})
    assert bad.status_code == 400
    allp = client.get("/api/players", params=q).json()
    assert allp.get("situation") is None
    d = client.get("/api/players", params={**q, "situation": "trailing"}).json()
    s = d["situation"]
    assert s["label"] == "When trailing" and s["means"] == "his team behind by 9 or more" and s["min_plays"] == 20
    assert "target_share" in s["columns"] and "points" not in s["columns"]
    if not sql("select 1 from information_schema.tables where table_schema = 'analytics' and table_name = %s",
               (ST.SITUATION_REL,)):
        pytest.skip("mart_player_game_situation is not built on this copy")
    row = next(p for p in d["players"] if p["gsis_id"] == CHASE)
    want = sql("""select sum(targets) t, sum(team_targets) tt, sum(team_plays) tp
                  from analytics.mart_player_game_situation
                  where gsis_id = %s and season = %s and season_type = 'REG' and situation = 'trailing'""",
               (CHASE, d["season"]))[0]
    assert row["targets"] == want["t"] and row["situation_plays"] == want["tp"]
    if want["tp"] >= 20:
        assert row["target_share"] == pytest.approx(float(want["t"]) / float(want["tt"]), abs=1e-4)
    else:
        assert row["target_share"] is None
    for col in ("points", "snap_share", "on_field_target_share", "air_yards_share", "ros_value"):
        assert row.get(col) is None, col
    # the three groups add up to all plays' targets (the same games, the same plays)
    by = {k: next(p for p in client.get("/api/players", params={**q, "situation": k}).json()["players"]
                  if p["gsis_id"] == CHASE)["targets"] or 0 for k in ("trailing", "close", "leading")}
    whole = next(p for p in allp["players"] if p["gsis_id"] == CHASE)
    assert abs(sum(by.values()) - whole["targets"]) <= 2          # play-by-play's targets against the box score's


INTERNAL = r"\b(fct|mart|dim|bridge|int|stg)_[a-z_]+|league_lab\.|analytics\.|\bops\.|routes_feed|_proxy\b"


def test_no_internal_name_in_what_the_screen_prints(client):
    import re
    d = client.get("/api/players", params={"league": "ref:half", "window": "season", "position": "WR,TE",
                                           "limit": 5}).json()
    for c in d["catalogue"]:
        for k in ("label", "short", "definition", "numerator", "denominator", "aggregation", "source", "reason",
                  "coverage", "graded"):
            assert not re.search(INTERNAL, c.get(k) or ""), (c["id"], k, c.get(k))
    assert not re.search(INTERNAL, d["howto"])
    # 2026 has no route column (participation arrives after the season): the group is "Snaps"
    assert not any(c["available"] for c in d["catalogue"] if c["id"] in ST.ROUTE_COLS)
    assert {c["group"] for c in d["catalogue"] if c["id"] == "snap_share"} == {"Snaps"}
    assert "Snaps" in d["groups"] and "Snaps and routes" not in d["groups"]
    # a season with participation keeps the whole name
    old = client.get("/api/players", params={"league": "ref:half", "window": "season", "position": "WR,TE", "limit": 5,
                                             "season": 2024}).json()
    if any(c["available"] for c in old["catalogue"] if c["id"] in ST.ROUTE_COLS):
        assert {c["group"] for c in old["catalogue"] if c["id"] == "snap_share"} == {"Snaps and routes"}
