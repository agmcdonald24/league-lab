"""IR-4 (Wave I-R): say what is verified, and carry starter uncertainty into the verdict (api provenance.py).

The pure parts run on hand-built rows (the board, the starter flags); the routes run on the database and check the
contract: every analysis carries ``provenance`` with its one line, the decisions carry ``caveats`` with the stated rule,
About lists the versions and what each number has been checked against.
"""

from __future__ import annotations

import pytest

from league_lab_api import provenance as P
from league_lab_api import ros_grade

from .conftest import needs_db

BOARD = {"model_version": "v3.6", "kd_model_version": "kd1.0", "published_at": "2026-10-08T00:05:49+00:00",
         "versions": [{"version": "v2.0", "first_week": 1, "last_week": 3}, {"version": "v3.0", "first_week": 4, "last_week": 4},
                      {"version": "v3.6", "first_week": 5, "last_week": 18}], "source": "board"}
LOCK, DARNOLD, KEENUM, BAGENT, JSN = "00-0035704", "00-0034869", "00-0028986", "00-0038416", "00-0038543"
MAYFIELD, DANIELS = "00-0034855", "00-0041251"


@pytest.fixture
def board(monkeypatch):
    monkeypatch.setattr(P, "board", lambda: dict(BOARD))


@pytest.fixture
def flags(monkeypatch):
    """Tampa Bay unclear (U1: Daniels listed, Mayfield first on the depth chart); Seattle corrected by hand."""
    unc = {DANIELS: {"team": "TB", "listed": "Jalon Daniels", "played": "Baker Mayfield", "role": "listed", "words": "…"},
           MAYFIELD: {"team": "TB", "listed": "Jalon Daniels", "played": "Baker Mayfield", "role": "depth", "words": "…"}}
    cor = {DARNOLD: {"team": "SEA", "listed": "Drew Lock", "set": "Sam Darnold", "role": "set", "words": "…"},
           LOCK: {"team": "SEA", "listed": "Drew Lock", "set": "Sam Darnold", "role": "listed", "words": "…"}}
    monkeypatch.setattr(P.starters, "unclear", lambda s, w: dict(unc))
    monkeypatch.setattr(P.starters, "corrected", lambda s, w: dict(cor))


def test_model_versions_are_the_codes():
    from league_lab import kdef, projections
    assert P.MODEL_VERSION == projections.MODEL_VERSION
    assert P.KD_MODEL_VERSION == kdef.KD_MODEL_VERSION
    assert P.VERSIONS[-1]["version"] == projections.MODEL_VERSION       # About's list ends at the code's version


def test_checks_agree_with_the_one_sentence():
    assert P.CHECKS[("later", "QB")]["mae"] == ros_grade.QB_LATER_MAE
    assert P.CHECKS[("next", "QB")]["mae"] == ros_grade.QB_NEXT_WEEK_MAE
    assert {round(P.CHECKS[("later", p)]["order"], 2) for p in ("K", "DEF")} == {round(v, 2) for v in ros_grade.KD_LATER_SPEARMAN.values()}
    # the status rule: graded = order ≥ 0.50; weak below; chance where IQ-4's rule said so
    for (sp, pos), c in P.CHECKS.items():
        if c["status"] == "graded":
            assert c["order"] >= 0.5, (sp, pos)
        elif c["status"] == "graded_weak":
            assert c["order"] < 0.5, (sp, pos)
        else:
            assert c["status"] == "chance" and sp == "later" and pos in ("K", "DEF")


def test_spans_follow_the_market_week():
    assert P.spans(P.horizon(5, 5, 5)) == ["next"]
    assert P.spans(P.horizon(5, 18, 5)) == ["next", "later"]
    assert P.spans(P.horizon(6, 9, 5)) == ["later"]
    assert P.spans(P.horizon(None, None, None)) == []
    assert P.horizon(5, 18, 5)["words"] == "weeks 5–18" and P.horizon(5, None, None)["words"] == "week 5"


def test_week_line_says_version_publication_week_and_check(board):
    p = P.block(["QB"], 5, 5, 5)
    assert p["model_version"] == "v3.6" and p["status"] == "graded" and not p["beta"]
    assert p["words"] == "Model v3.6, data published 7 Oct, 8:05 pm ET · week 5 · checked on 2021–2025: next week graded."


def test_rest_of_season_line_names_the_weak_and_the_ungraded(board):
    p = P.block(["ALL"], 5, 18, 5, season_range=True)
    assert p["kd_model_version"] == "kd1.0" and p["status"] == "not_graded"
    w = p["words"]
    assert w.startswith("Model v3.6 (kickers and defenses kd1.0), data published 7 Oct, 8:05 pm ET · weeks 5–18 · ")
    assert "two to eight weeks ahead graded, quarterbacks weak, kickers and defenses no better than chance" in w
    assert "next week graded, kickers and defenses weak" in w and "the season total's range not graded" in w
    assert {c["span"] for c in p["checks"]} == {"next", "later", "season_range"}
    assert all(c["ref"].startswith("docs/METRICS.md") for c in p["checks"])


def test_trade_line_is_beta_and_says_the_gap_is_not_graded(board):
    p = P.block(["RB", "WR"], 5, 8, 5, trade_gap=True, beta=True)
    assert p["beta"] and p["words"].startswith("Beta · Model v3.6")
    assert "the trade's range not graded" in p["words"] and "weeks 5–8" in p["words"]


def test_no_board_no_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no database")
    monkeypatch.setattr(P, "query", boom)
    b = P.board()
    assert b["model_version"] == P.MODEL_VERSION and b["published_at"] is None and b["source"] == "code"
    p = P.block(["QB"], 5, 5, 5)
    assert p["words"].startswith("Model v3.6 · week 5")         # no publication time: none claimed


def test_unclear_starter_withholds_corrected_softens_receivers_carry_nothing(flags):
    ps = [{"gsis_id": DANIELS, "position": "QB", "player_name": "Jalon Daniels", "team": "TB"},
          {"gsis_id": DARNOLD, "position": "QB", "player_name": "Sam Darnold", "team": "SEA"},
          {"gsis_id": JSN, "position": "WR", "player_name": "Jaxon Smith-Njigba", "team": "SEA"}]
    cv = P.caveats_for(ps, 2026, 5)
    assert [c["kind"] for c in cv] == ["starter_unclear", "starter_set_by_hand"]     # withhold first
    assert cv[0]["effect"] == "withhold" and cv[0]["players"] == ["Jalon Daniels"]
    assert cv[0]["words"] == ("No verdict while Tampa Bay's starter is unclear: Jalon Daniels is listed, the depth chart "
                              "puts Baker Mayfield first, and this depends on Jalon Daniels. The numbers assume the listing.")
    assert cv[1]["effect"] == "soften" and cv[1]["players"] == ["Sam Darnold"]           # not the receiver
    assert "set by hand (Sam Darnold, not the listed Drew Lock)" in cv[1]["words"]
    assert P.effect(cv) == "withhold"
    a = P.apply("Accept: you gain 6.1 points over weeks 5–8.", cv)
    assert a["verdict"] is None and a["effect"] == "withhold" and a["words"].startswith("No verdict while Tampa Bay's")


def test_soften_keeps_the_verdict_with_its_sentence(flags):
    cv = P.caveats_for([{"gsis_id": LOCK, "position": "QB", "player_name": "Drew Lock", "team": "SEA"}], 2026, 5)
    a = P.apply("Accept.", cv)
    assert a["verdict"] == "Accept." and a["effect"] == "soften" and "assumes Darnold starts" in a["words"]
    assert P.apply("Accept.", []) == {"verdict": "Accept.", "effect": None, "words": None}


def test_mfl_team_qb_unit_of_a_flagged_team(flags):
    unit = {"gsis_id": None, "position": "TMQB", "player_name": "Tampa Bay Buccaneers QB", "team": "TB"}
    kick = {"gsis_id": None, "position": "TMPK", "player_name": "Seattle Seahawks K", "team": "SEA"}
    cv = P.caveats_for([unit, kick], 2026, 5)
    assert len(cv) == 1 and cv[0]["kind"] == "starter_unclear" and cv[0]["players"] == ["Tampa Bay Buccaneers QB"]
    assert P._team("LAR") == "LA" and P._team(" tb ") == "TB"           # the Rams: the schedule's "LA", MFL's "LAR"


def test_flags_failing_never_cost_the_decision(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("closed pool")
    monkeypatch.setattr(P.starters, "unclear", boom)
    assert P.caveats_for([{"gsis_id": LOCK, "position": "QB", "team": "SEA"}], 2026, 5) == []
    assert P.caveats_for([{"gsis_id": LOCK, "position": "QB", "team": "SEA"}], None, None) == []


def test_for_trade_reads_the_answers_weeks_and_players(board, flags, monkeypatch):
    monkeypatch.setattr(P, "_season_now", lambda: 2026)
    ans = {"week": 5, "weeks": [5, 6, 7, 8], "give": [{"gsis_id": JSN, "position": "WR", "player_name": "J", "team": "SEA"}],
           "get": [{"gsis_id": MAYFIELD, "position": "QB", "player_name": "Baker Mayfield", "team": "TB"}]}
    out = P.with_trade(dict(ans))
    assert out["provenance"]["horizon"]["words"] == "weeks 5–8" and out["provenance"]["beta"]
    assert out["caveat_effect"] == "withhold" and out["caveat_rule"] == P.RULE_WORDS
    assert out["caveats"][0]["players"] == ["Baker Mayfield"]
    free = P.with_free_trade({"window": {"first": 5, "last": 18}, "give": {"players": [ans["get"][0]]}, "get": {"players": []}})
    assert free["caveat_effect"] == "withhold" and "weeks 5–18" in free["provenance"]["words"]
    assert P.with_trade("not a dict") == "not a dict"


def test_about_block_lists_versions_and_checks(board):
    a = P.about_block()
    v = a["versions"]
    assert [x["version"] for x in v["list"]][:2] == ["v2.0", "kd1.0"] and v["current"] == "v3.6"
    assert v["by_week"] == "weeks 1–3: v2.0; week 4: v3.0; weeks 5–18: v3.6"
    assert "recipe" not in v["words"] and "changes during the season" in v["words"]
    rows = {r["position"]: r for r in a["checked"]["rows"]}
    assert rows["QB"]["later"]["status"] == "graded_weak" and rows["QB"]["next4"]["base_order"] is not None
    assert rows["K"]["later"]["words"] == "no better than chance" and rows["K"]["next4"] is None
    assert any("several players" in n for n in a["checked"]["not_graded"])
    assert a["checked"]["useful"]["by_position"]["QB"]["useful"] is False


# ------------------------------------------------------------------------------------------------ the routes (database)
@needs_db
@pytest.mark.parametrize("view", ["week", "season"])
def test_rankings_carry_provenance(client, view):
    r = client.get(f"/api/rankings?league=ref:half&position=QB&view={view}")
    assert r.status_code == 200, r.text[:300]
    p = r.json().get("provenance")
    assert p and p["words"].startswith("Model v") and p["model_version"]
    assert ("later" in {c["span"] for c in p["checks"]}) == (view == "season")


@needs_db
def test_ros_free_trade_card_and_about_carry_it(client):
    r = client.get("/api/ros?league=ref:half&position=QB&limit=5")
    assert r.status_code == 200 and r.json()["provenance"]["words"].startswith("Model v")
    pl = r.json()["players"]
    if len(pl) >= 2:
        give, get = pl[0]["gsis_id"], pl[1]["gsis_id"]
        f = client.get(f"/api/trade-calc/free?league=ref:half&give={give}&get={get}")
        assert f.status_code == 200, f.text[:300]
        d = f.json()
        assert d["provenance"]["beta"] and d["provenance"]["words"].startswith("Beta · Model v")
        assert isinstance(d["caveats"], list) and d["caveat_rule"] == P.RULE_WORDS
        c = client.get(f"/api/player/{give}?league=ref:half")
        assert c.status_code == 200 and c.json()["provenance"]["words"].startswith("Model v")
    a = client.get("/api/about?league=ref:half")
    assert a.status_code == 200
    assert a.json()["versions"]["list"] and a.json()["checked"]["rows"]


def test_the_record_rows_hold_the_same_numbers():
    from league_lab import context_record as CR
    allrows = CR.horizon_grade_rows()
    rows = {r["grp"]: r for r in allrows if r["kind"] == "horizon"}
    assert len(rows) == len(CR.HORIZON_GRADES)
    useful = {r["grp"].split("/")[0]: r for r in allrows if r["kind"] == "useful"}
    for pos, u in P.USEFUL.items():
        assert (useful[pos]["n"], useful[pos]["beat_share"], useful[pos]["rest_beat_share"], useful[pos]["beat"]) == (
            u["pairs"], u["rate"], u["base"], u["seasons"])
        assert u["useful"] == (u["seasons"] >= 4)              # the rule: above 50 % and the baseline in 4 of 5
    for (sp, pos), c in P.CHECKS.items():
        r = rows[f"{pos}/{'next1' if sp == 'next' else 'later'}"]
        assert (r["mean_miss"], r["beat_share"]) == (c["mae"], c["order"]), (sp, pos)
    for (w, pos), c in P.WINDOWS.items():
        r = rows[f"{pos}/{w}"]
        assert (r["mean_miss"], r["beat_share"], r["rest_beat_share"]) == (c["mae"], c["order"], c["base_order"])
    assert rows["QB/next4"]["words"] == ("Quarterbacks, the next four weeks: order 0.54, miss 6.9 points per game (his own "
                                         "record: 0.54, 7.0).")
    assert rows["RB/ros"]["words"] == ("Running backs, the rest of the season (up to eight weeks ahead): order 0.64, miss 4.7 "
                                       "points per game (his own record: 0.60, 4.9).") and rows["RB/ros"]["vs_rest"] < 0
    assert all(r["rest_beat_share"] is not None for r in rows.values())       # every cell has its baseline now
    # the stored grade carries them (a record with one graded row is enough to write the grade)
    assert all(k in CR.GRADE_COLUMNS for k in rows["QB/ros"])


def test_the_free_calculator_verdict_follows_the_rule(board, flags, monkeypatch):
    monkeypatch.setattr(P, "_season_now", lambda: 2026)
    v = {"even": False, "lean": "get", "gap": 103.0, "low": 53.0, "high": 153.0, "one_player": None,
         "words": "You get more: 103 points of season value (likely +53 to +153)."}
    soft = P.with_free_trade({"window": {"first": 5, "last": 18}, "verdict": dict(v),
                              "give": {"players": [{"gsis_id": DARNOLD, "position": "QB", "player_name": "Sam Darnold", "team": "SEA"}]},
                              "get": {"players": [{"gsis_id": "00-0036555", "position": "RB", "player_name": "Chuba Hubbard", "team": "CAR"}]}})
    assert soft["verdict"]["words"] == "You get more: 103 points of season value (likely +53 to +153) (a lean: it assumes Darnold starts)."
    assert soft["verdict"]["lean"] == "get" and soft["verdict"]["words_unqualified"] == v["words"]
    held = P.with_free_trade({"window": {"first": 5, "last": 18}, "verdict": dict(v),
                              "give": {"players": [{"gsis_id": MAYFIELD, "position": "QB", "player_name": "Baker Mayfield", "team": "TB"}]},
                              "get": {"players": []}})
    assert held["verdict"]["words"] == "No verdict: it depends on who starts for Tampa Bay."
    assert held["verdict"]["lean"] is None and held["verdict"]["gap"] == 103.0          # the numbers stay
    plain = P.with_free_trade({"window": {"first": 5, "last": 18}, "verdict": dict(v), "give": {"players": []}, "get": {"players": []}})
    assert plain["verdict"] == v


def test_the_site_reads_the_record_rows(monkeypatch):
    import copy

    import pandas as pd
    from league_lab import context_record as SR

    from league_lab_api import context_record as CR
    rows = SR.horizon_grade_rows()
    cols = ["kind", "grp", "corner_certainty", "corner_tier", "n", "games", "mean_miss", "lo", "hi", "beat", "beat_share",
            "vs_rest", "vs_rest_lo", "vs_rest_hi", "rest_n", "rest_beat_share", "span", "scoring", "words"]
    df = pd.DataFrame([{c: r.get(c) for c in cols} for r in rows])
    monkeypatch.setattr(CR, "query", lambda sql, *a, **k: pd.DataFrame({"ok": [True]}) if "to_regclass" in sql else df)
    out = CR._build()
    h = out["horizon"]
    assert h["graded"] and h["n"] == 24
    assert h["cells"]["horizon:QB/next4"]["order"] == 0.538 and h["cells"]["useful:WR/next4"]["n"] == 8643
    assert out["corner"] == copy.deepcopy(CR.EMPTY)["corner"]          # the other kinds as they were (no rows: not graded)
