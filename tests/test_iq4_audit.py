"""IQ-4: `league-lab audit-lists`' rules on hand-built boards (league_lab.audit)."""

from __future__ import annotations

import pandas as pd

from league_lab import audit as AU


def _board(rows, view="week", position="QB"):
    df = pd.DataFrame(rows)
    if "rank" not in df:
        df = df.sort_values("proj", ascending=False).reset_index(drop=True)
        df["rank"] = range(1, len(df) + 1)
    for c in ("status", "bye", "gsis_id"):
        if c not in df:
            df[c] = None if c != "bye" else False
    return AU.Board("ref:half", "Half PPR", view, position, df, (5, 5))


def _ppg(per_player: dict[str, tuple[str, list[float]]]):
    rows = [{"player_key": k, "position": pos, "week": i + 1, "points": p}
            for k, (pos, pts) in per_player.items() for i, p in enumerate(pts)]
    return AU.ppg_ranks(pd.DataFrame(rows))


def test_status_words():
    assert AU.status_of("Out", "ACT") == "Out"
    assert AU.status_of("Doubtful", None) == "Doubtful"
    assert AU.status_of("Questionable", "ACT") is None
    assert AU.status_of(None, "RES") == "on a reserve list"
    assert AU.status_of(None, "IR") == "on injured reserve"
    assert AU.status_of(None, "ACT") is None


def test_coverage_names_the_missing_teams():
    b = _board([{"player_key": "a", "player_name": "A", "team": "BUF", "proj": 20}])
    assert AU.missing_teams(b.rows, {"BUF", "KC", "CAR"}) == ["CAR", "KC"]
    assert AU.missing_teams(b.rows, {"BUF"}) == []
    assert AU.missing_teams(pd.DataFrame(columns=["team"]), {"KC"}) == ["KC"]


def test_ppg_ranks_need_three_games():
    p = _ppg({"a": ("QB", [20, 20, 20]), "b": ("QB", [30, 30]), "c": ("QB", [10, 12, 14])})
    r = p.set_index("player_key")
    assert r.loc["a", "ppg_rank"] == 1 and r.loc["c", "ppg_rank"] == 2
    assert pd.isna(r.loc["b", "ppg_rank"])          # two games: no rank


def test_projected_high_scoring_low_is_flagged():
    # 30 quarterbacks with 3 games each; "low" scores 2 points per game (the 30th) but is projected 3rd
    per = {f"q{i}": ("QB", [40 - i] * 3) for i in range(29)}
    per["low"] = ("QB", [2, 2, 2])
    rows = [{"player_key": f"q{i}", "player_name": f"Q{i}", "team": f"T{i}", "proj": 30 - i} for i in range(29)]
    rows.append({"player_key": "low", "player_name": "Low", "team": "MIN", "proj": 28.5})
    flagged, explained = AU.against_scored(_board(rows), _ppg(per))
    names = {f["player"] for f in flagged if f["kind"] == "projected high, scoring low"}
    assert names == {"Low"}
    assert "#30 in points per game" in next(f for f in flagged if f["player"] == "Low")["why"]
    assert explained == []


def test_top_scorer_ranked_low_unless_his_status_explains_it():
    per = {f"q{i}": ("QB", [40 - i] * 3) for i in range(20)}
    rows = [{"player_key": f"q{i}", "player_name": f"Q{i}", "team": f"T{i}", "proj": 30 - i} for i in range(1, 20)]
    # q0 (the best scorer) ranked 20th; q1 (2nd best) missing from the list; q2 Out -> explained
    rows.append({"player_key": "q0", "player_name": "Best", "team": "BUF", "proj": 1.0})
    rows = [r for r in rows if r["player_key"] != "q1"]
    rows = [dict(r, status="Out") if r["player_key"] == "q2" else r for r in rows]
    rows = [dict(r, proj=0.5) if r["player_key"] == "q2" else r for r in rows]
    flagged, explained = AU.against_scored(_board(rows), _ppg(per))
    low = {f["player"]: f for f in flagged if f["kind"] == "top scorer ranked low"}
    assert set(low) == {"Best", "q1"}
    assert "not in the list" in low["q1"]["why"]
    assert [e["player"] for e in explained] == ["Q2"] and "explained: Out" in explained[0]["why"]


def test_a_bye_explains_a_top_scorer_outside_the_list():
    per = {f"q{i}": ("QB", [40 - i] * 3) for i in range(20)}
    rows = [{"player_key": f"q{i}", "player_name": f"Q{i}", "team": f"T{i}", "proj": 30 - i} for i in range(1, 20)]
    rows.append({"player_key": "q0", "player_name": "Mahomes", "team": "KC", "proj": 0.1, "bye": True})
    flagged, explained = AU.against_scored(_board(rows, view="season"), _ppg(per))
    assert not [f for f in flagged if f["player"] == "Mahomes"]
    assert explained and "a bye this week" in explained[0]["why"]


def test_out_but_projected_above_a_backup():
    b = _board([{"player_key": "a", "player_name": "A", "team": "BUF", "position": "WR", "proj": 9.0, "status": "Out"},
                {"player_key": "b", "player_name": "B", "team": "BUF", "position": "WR", "proj": 2.0, "status": "Out"},
                {"player_key": "c", "player_name": "C", "team": "BUF", "position": "WR", "proj": 12.0, "status": None}])
    out = AU.out_but_projected(b.rows)
    assert [o["player"] for o in out] == ["A"] and "Out, projected 9.0" in out[0]["why"]


def test_quarterbacks_per_team():
    b = _board([{"player_key": "a", "player_name": "Allen", "team": "BUF", "proj": 22.0},
                {"player_key": "b", "player_name": "Lock", "team": "SEA", "proj": 12.5},
                {"player_key": "c", "player_name": "Darnold", "team": "SEA", "proj": 11.0},
                {"player_key": "d", "player_name": "Backup", "team": "NYJ", "proj": 7.0}])
    got = {x["team"]: x["why"] for x in AU.qbs_per_team(b.rows, {"BUF", "SEA", "NYJ", "MIA"})}
    assert set(got) == {"SEA", "NYJ", "MIA"}
    assert got["SEA"].startswith("2 quarterbacks above 10")
    assert "best Backup 7.0" in got["NYJ"] and "no quarterback)" in got["MIA"]


def test_starter_against_the_last_game():
    qb = _board([{"player_key": "lock", "gsis_id": "lock", "player_name": "Drew Lock", "team": "SEA", "proj": 12.5},
                 {"player_key": "dar", "gsis_id": "dar", "player_name": "Sam Darnold", "team": "SEA", "proj": 4.5},
                 {"player_key": "allen", "gsis_id": "allen", "player_name": "Josh Allen", "team": "BUF", "proj": 22.0},
                 {"player_key": "kee", "gsis_id": "kee", "player_name": "Case Keenum", "team": "CHI", "proj": 14.6},
                 {"player_key": "bag", "gsis_id": "bag", "player_name": "Tyson Bagent", "team": "CHI", "proj": 3.0}]).rows
    last = pd.DataFrame([
        {"team": "SEA", "gsis_id": "dar", "player_name": "Sam Darnold", "week": 4, "dropbacks": 38},
        {"team": "SEA", "gsis_id": "lock", "player_name": "Drew Lock", "week": 4, "dropbacks": 0},
        {"team": "BUF", "gsis_id": "allen", "player_name": "Josh Allen", "week": 4, "dropbacks": 40},
        {"team": "CHI", "gsis_id": "kee", "player_name": "Case Keenum", "week": 4, "dropbacks": 1},
        {"team": "CHI", "gsis_id": "bag", "player_name": "Tyson Bagent", "week": 4, "dropbacks": 30}])
    got = {x["team"]: x["why"] for x in AU.starter_vs_last_game(qb, last)}
    assert set(got) == {"SEA", "CHI"}
    assert got["SEA"].startswith("projected starter Drew Lock (12.5) took no dropback in week 4; Sam Darnold led")
    assert got["CHI"].startswith("Tyson Bagent led week 4's dropbacks (30) but Case Keenum is projected")


def test_agreement_is_the_guards_number():
    rows = [{"weeks": [[5, 20 - i], [6, 20 - i], [7, 20 - i]]} for i in range(24)]
    assert abs(AU.agreement(pd.DataFrame(rows), 5) - 1.0) < 1e-9
    rows = [{"weeks": [[5, 20 - i], [6, i], [7, i]]} for i in range(24)]
    assert abs(AU.agreement(pd.DataFrame(rows), 5) + 1.0) < 1e-9
    # a bye this week (no week-5 point) is left out; fewer than 8 players: None
    assert AU.agreement(pd.DataFrame([{"weeks": [[6, 10]]}] * 30), 5) is None


def test_rank_moves_without_a_game_or_status_change():
    before = {"Half PPR · QB": {"a": {"rank": 30, "games": 4, "status": None, "name": "A"},
                                "b": {"rank": 3, "games": 4, "status": None, "name": "B"},
                                "c": {"rank": 40, "games": 3, "status": None, "name": "C"}}}
    today = {"Half PPR · QB": {"a": {"rank": 4, "games": 4, "status": None, "name": "A"},      # 26 up, nothing happened
                               "b": {"rank": 25, "games": 4, "status": "Out", "name": "B"},    # status changed
                               "c": {"rank": 10, "games": 4, "status": None, "name": "C"}}}    # a game played
    mv = AU.rank_moves(today, before)
    assert [m["player"] for m in mv] == ["A"] and "up 26" in mv[0]["why"]
