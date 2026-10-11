"""IX-4 (Wave I-X): My Week — one matchup number, the lineup it is, three decisions.

The review of 10 October § 1 (three totals, none labelled; a table headed "Your lineup" that was the best lineup on
paper), § 4's Big Mac Attack paragraph (Chicago team QB over Houston by about a point, the unclear starter in a lower
paragraph) and § 5's news sentence. Unit tests of the pieces (`myweek.matchup_summary`, `recommend`, `rule_calls`,
`build_actions`' order, `cards.league_line`) and the two paths against the database (League of Scrubs team 2, the MFL
league's team 8 on its fixtures)."""

from __future__ import annotations

import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import clock
from league_lab import mfl_client as M
from league_lab import player_ids as PI

from league_lab_api import myweek
from league_lab_api.applib import cards

from .conftest import SCRUBS, needs_db
from .test_i0b import IDS, MFL_FX

SATURDAY = "2026-10-10T16:00:00Z"          # week 5: Thursday's game (Tampa Bay at Dallas) has kicked off, the rest not
THURSDAY = "2026-10-08T12:00:00Z"          # week 5 before its first kickoff


# ------------------------------------------------------------------------------------------------ the one summary
def _answer(win: dict | None, *, mine=125.07, theirs=105.2, also=None) -> dict:
    opp = {"roster_id": 6, "team_name": "GoodGameBuddy", "lineup_value": theirs}
    if also:
        opp["also"] = also
    return {"week": 5, "lineup_value": mine, "opponent": opp, "win": win}


def _win(**kw) -> dict:
    base = {"opponent_roster_id": 6, "p": 0.58, "percent": 58, "words": "a slight favorite", "mine": 125.07,
            "theirs": 105.2, "n_played": 0, "n_starters": 9, "opp_n_played": 0, "opp_n_starters": 9, "n_started": 0,
            "opp_n_started": 0, "played_words": None, "assumptions": "assuming …"}
    return {**base, **kw}


def test_before_the_first_kickoff_one_line_labelled_best_lineups():
    m = myweek.matchup_summary(_answer(_win()))
    assert m["state"] == "before"
    assert m["line"] == "Week 5 vs **GoodGameBuddy**: you project 125, they project 105."
    assert m["basis"] == "Each side's best lineup by our projections."
    assert m["chance"] == "You're a slight favorite this week: 58%."          # the chance, no second total
    assert "125" not in m["chance"] and "105" not in m["chance"]


def test_once_a_game_kicked_off_the_live_line_is_the_one_summary():
    w = _win(mine=118.4, theirs=117.2, n_played=2, opp_n_played=1, n_started=2, opp_n_started=1,
             played_words="2 of your 9 have played, 1 of theirs", percent=53, words="a coin flip")
    m = myweek.matchup_summary(_answer(w))
    assert m["state"] == "live"
    assert m["line"] == "Week 5 vs **GoodGameBuddy**: 118 to 117 expected."
    assert m["basis"] == ("Points scored so far plus projections for players still to play (2 of your 9 have played, "
                          "1 of theirs).")
    assert m["chance"] == "This week is a coin flip: 53%."
    # a game under way with no points in yet: still the live line, and it says no points are in
    w2 = _win(opp_n_started=2)
    m2 = myweek.matchup_summary(_answer(w2))
    assert m2["state"] == "live" and m2["line"].endswith(": 125 to 105 expected.")
    assert "a game has kicked off; no points are in yet" in m2["basis"]


def test_after_every_starter_has_played_the_score():
    w = _win(mine=131.5, theirs=99.0, n_played=9, opp_n_played=9, n_started=9, opp_n_started=9, p=1.0, percent=99)
    m = myweek.matchup_summary(_answer(w))
    assert m["state"] == "final" and m["line"] == "Week 5 vs **GoodGameBuddy**: 132 to 99." and m["chance"] is None


def test_close_totals_keep_a_decimal_and_no_opponent_no_summary():
    m = myweek.matchup_summary(_answer(_win(), mine=110.69, theirs=111.15))
    assert m["line"].endswith("you project 110.7, they project 111.2.")
    assert myweek.matchup_summary({"week": 5, "opponent": None}) is None


def test_live_scores_not_read_keeps_the_projection_line_and_says_so():
    w = {"opponent_roster_id": 6, "p": None, "line": None, "note": myweek.WIN_NO_LIVE, "n_started": 3,
         "opp_n_started": 0, "n_starters": 9, "opp_n_starters": 9}
    m = myweek.matchup_summary(_answer(w))
    assert m["line"] == "Week 5 vs **GoodGameBuddy**: you project 125, they project 105."
    assert m["basis"] == myweek.MATCHUP_NO_LIVE and m["chance"] is None


def test_a_double_header_one_summary_per_game():
    also = [{"roster_id": 9, "team_name": "Knight Train", "lineup_value": 98.0}]
    w = _win(also=[_win(opponent_roster_id=9, theirs=98.0, percent=70, words="a clear favorite")])
    m = myweek.matchup_summary(_answer(w, also=also))
    assert m["line"].startswith("Week 5 vs **GoodGameBuddy**")
    assert m["also"][0]["line"] == "Week 5 vs **Knight Train**: you project 125, they project 98."
    assert m["also"][0]["chance"] == "You're a clear favorite this week: 70%."


def test_kicked_off_reads_the_clock():
    with clock.pinned(THURSDAY):
        assert not myweek.kicked_off({"kickoff_at": pd.Timestamp("2026-10-09T00:15:00Z"), "locked_now": True})
    with clock.pinned(SATURDAY):
        assert myweek.kicked_off({"kickoff_at": pd.Timestamp("2026-10-09T00:15:00Z"), "locked_now": False})
    assert myweek.kicked_off({"kickoff_at": None, "locked_now": True})


# ------------------------------------------------------------------------------------------------ the recommendation
def _rows() -> pd.DataFrame:
    r = [  # slot code, key, name, position, role, value
        ("QB", "q1", "Patrick Mahomes", "QB", "starter", 20.0),
        ("RB", "r1", "Kyren Williams", "RB", "starter", 15.0),
        ("WR", "w1", "Ladd McConkey", "WR", "starter", 9.0),
        ("FLEX", "w2", "Justin Jefferson", "WR", "starter", 8.0),
        (None, "w3", "Jordan Addison", "WR", "bench", 8.9),
    ]
    return pd.DataFrame([{"slot": s, "sleeper_player_id": k, "player_name": n, "position": p, "role": ro, "value": v,
                          "gsis_id": None, "is_empty_slot": False, "locked_now": False, "report_status": None,
                          "value_source": "model", "lineup_value": 52.0 if ro == "starter" else None, "bench_rank": 1}
                         for s, k, n, p, ro, v in r])


def _out(rows: pd.DataFrame, swaps=None) -> dict:
    lu = [{"role": "starter", "slot": cards.slot_label(r.slot), "player_name": r.player_name, "gsis_id": None,
           "position": r.position, "value": r.value, "margin": 1.0, "flag": "", "key": r.sleeper_player_id}
          for r in rows[rows["role"] == "starter"].itertuples()]
    bench = [{"role": "bench", "slot": "Bench 1", "player_name": "Jordan Addison", "gsis_id": None, "position": "WR",
              "value": 8.9, "margin": None, "flag": "", "key": "w3"}]
    return {"lineup": lu, "lineup_full": lu + bench, "lineup_value": 52.0, "platform_name": "Sleeper", "swaps": swaps or []}


def test_the_table_is_the_lineup_the_calls_produce():
    rows = _rows()
    out = _out(rows, swaps=[{"in": "w3", "in_name": "Addison", "out": "w1", "out_name": "McConkey", "status": "Questionable"}])
    rec = myweek.recommend(out, rows, None)
    names = [r["player_name"] for r in rec["rows"]]
    assert "Jordan Addison" in names and "Ladd McConkey" not in names            # the call's player IN the slot
    assert rec["rows"][names.index("Jordan Addison")]["slot"] == "WR"
    assert [r["player_name"] for r in rec["bench"]] == ["Ladd McConkey"]
    assert rec["total"] == pytest.approx(20 + 15 + 8.9 + 8) and rec["best_total"] == 52.0
    assert rec["words"] is None and rec["changes"] is None                       # the provider's lineup unknown: nothing said
    assert not any("the call above" in (r.get("flag") or "") for r in rec["rows"] + rec["bench"])


def test_rows_that_differ_from_the_provider_say_who_is_there_now():
    rows = _rows()
    rec = myweek.recommend(_out(rows), rows, {"q1": "QB", "r1": "RB", "w1": "WR", "w3": "FLEX"})
    assert rec["changes"] == 1 and rec["words"] == "1 change from your Sleeper lineup."
    flex = next(r for r in rec["rows"] if r["key"] == "w2")
    assert flex["now_words"] == "In Sleeper now: Addison"
    assert all(not r.get("now_words") for r in rec["rows"] if r["key"] != "w2")
    same = myweek.recommend(_out(rows), rows, {"q1": "QB", "r1": "RB", "w1": "WR", "w2": "FLEX"})
    assert same["changes"] == 0 and same["words"] == "Matches your Sleeper lineup."


# ------------------------------------------------------------------------------------------------ the starter rule
def _caveated(effect: str, strength: str, gain: float) -> dict:
    lineup_full = [{"key": "mfl:0671", "player_name": "Chicago Bears QB", "position": "TMQB", "team": "CHI", "role": "starter"},
                   {"key": "mfl:0682", "player_name": "Houston Texans QB", "position": "TMQB", "team": "HOU", "role": "bench"}]
    kind = "starter_unclear" if effect == "withhold" else "starter_projected"
    return {"platform_name": "MFL", "lineup_full": lineup_full,
            "caveats": [{"kind": kind, "effect": effect, "team": "CHI", "players": ["Chicago Bears QB"],
                         "words": "We project Caleb Williams to start for Chicago, not the listed Case Keenum: Chicago Bears "
                                  "QB's projection assumes Williams starts."}],
            "cards": [{"key": "mfl:0671", "alt_key": "mfl:0682", "strength": strength, "margin": gain}],
            "actions": [{"kind": "change", "urgency": 1, "action": "Start Chicago Bears QB at team QB in place of Houston Texans QB.",
                         "reason": "The change is worth about 2 more projected points this week.", "slot_label": "team QB",
                         "start": [{"key": "mfl:0671", "name": "Chicago Bears QB", "link": "Chicago Bears QB"}],
                         "sit": [{"key": "mfl:0682", "name": "Houston Texans QB", "link": "Houston Texans QB"}],
                         "submitted": False, "submitted_words": "Not in your MFL lineup yet: make the change in MFL.",
                         "cards": [0], "gain": gain}],
            "review": [], "recommended": {"rows": [dict(lineup_full[0])]}}


def test_the_review_case_a_close_call_on_a_disputed_team_qb_says_check_who_starts_first():
    a = myweek.rule_calls(_caveated("soften", "lean", 1.91))
    act = a["actions"][0]
    assert act["action"] == "Chicago Bears QB or Houston Texans QB at team QB: check who starts first."
    assert act["reason"].startswith("We project Caleb Williams to start for Chicago, not the listed Case Keenum")
    assert "about 1.9 points ahead" in act["reason"]
    assert act["kind"] == "close" and act["caveat"]["check_first"] is True
    assert act["action_unqualified"].startswith("Start Chicago Bears QB")
    assert a["cards"][0]["caveat"]["effect"] == "soften"
    assert a["recommended"]["rows"][0]["check_words"] == "Check who starts for Chicago before kickoff"


def test_a_clear_call_on_a_disputed_starter_stands_as_a_lean():
    act = myweek.rule_calls(_caveated("soften", "clear", 6.0))["actions"][0]
    assert act["action"].startswith("Start Chicago Bears QB") and act["caveat"]["check_first"] is False
    assert "Read it as a lean. We project Caleb Williams" in act["reason"]


def test_an_unclear_starter_withholds_the_call_whatever_the_gap():
    act = myweek.rule_calls(_caveated("withhold", "clear", 6.0))["actions"][0]
    assert act["action"].endswith(": check who starts first.") and act["caveat"]["effect"] == "withhold"
    assert "Start " not in act["action"]


def test_no_caveat_no_change():
    a = _caveated("soften", "lean", 1.9)
    a["caveats"] = []
    assert myweek.rule_calls(a)["actions"][0]["action"].startswith("Start Chicago Bears QB")


# ------------------------------------------------------------------------------------------------ the league line
def test_the_league_line_keeps_the_rank_and_never_the_total(monkeypatch):
    rows = pd.DataFrame([{"role": "starter", "lineup_value": 125.07}])
    monkeypatch.setattr(cards, "missing_relations", lambda rels: ())
    monkeypatch.setattr(cards, "query", lambda *a, **k: pd.DataFrame(
        [{"measure": "lineup_value", "league_rank": 3, "n_rosters": 12, "week": 5, "horizon": "week 5"}]))
    assert cards.league_line("x", 2, 5, rows) == "Your best lineup ranks 3rd of 12 in the league in week 5."
    monkeypatch.setattr(cards, "missing_relations", lambda rels: tuple(rels))
    assert cards.league_line("x", 2, 5, rows) == ""


# ------------------------------------------------------------------------------------------------ both paths, the database
@needs_db
def test_house_league_scrubs_team_2(client):
    with clock.pinned(SATURDAY):
        d = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()
    m = d["matchup"]
    assert m["state"] == "live"                          # Thursday's game has kicked off for one of the two sides
    assert m["line"].startswith("Week 5 vs **") and m["line"].endswith(" expected.")
    assert f"{d['lineup_value']:.2f}" not in d["league_line"]
    rec = d["recommended"]
    assert rec["total"] == pytest.approx(sum(r["value"] for r in rec["rows"] if r["player_name"] and r["value"] is not None))
    assert rec["known"] in (True, False)
    if rec["known"]:
        assert rec["words"] in ("Matches your Sleeper lineup.",) or rec["words"].endswith("from your Sleeper lineup.")
    assert len(d["actions"]) <= 3 and isinstance(d["more_actions"], list)
    with clock.pinned(THURSDAY):
        before = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()["matchup"]
    assert before["state"] == "before" and ": you project " in before["line"]
    assert before["basis"] == "Each side's best lineup by our projections."


@pytest.fixture
def _mfl(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


@needs_db
def test_mfl_big_mac_attack_the_unclear_starter_sits_on_the_call(client, _mfl):
    with clock.pinned(SATURDAY):
        d = client.get("/api/my-week?league=mfl:70587&team=8").json()
    assert d["league_line"] == ""                         # no rank on demand, and never the total
    assert d["matchup"]["line"].startswith("Week 5 vs **")
    chi = [c for c in d.get("caveats") or [] if c.get("team") == "CHI"]
    if not chi:
        pytest.skip("Chicago's starter is not disputed on this copy")
    calls = [a for a in d["actions"] + d["more_actions"] if a.get("caveat")]
    assert calls, "the Chicago team-QB call carries the caveat"
    a = calls[0]
    assert a["action"].endswith(": check who starts first.") and "Chicago Bears QB" in a["action"]
    assert "Chicago" in a["reason"]
    row = next(r for r in d["recommended"]["rows"] if r.get("position") == "TMQB")
    assert row["check_words"] == "Check who starts for Chicago before kickoff"
    assert d["recommended"]["words"].endswith("from your MFL lineup.") or d["recommended"]["words"] == "Matches your MFL lineup."
