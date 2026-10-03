"""Wave I-C, IC-3: dad's league end to end, the Leagues card tells the truth, the audit of Andrew's two leagues.

Fixtures: `fixtures/mfl/70587/` — MFL league 70587 ("Make Football Great Again", 12 teams, starters TMQB / RB 2 /
WR+TE 3 / TMPK / Def, scoring by position group with touchdowns by distance) fetched 2026-10-03 through the browser
pane, byte for byte (league, rules, rosters, schedule, standings, weekly results weeks 1-3 — week 2 is a double
header: 12 matchups —, live scoring week 4); its 177 players (rosters + every player in those results) appended to
the shared `fixtures/mfl/players.json`.

The card (`ondemand.league_card`): the lineup read back in the league's own words from the slots League Lab solves
(`lineup.parse_slots`), the scoring in one line from IC-1's `ScoringSpec.readback()` when the spec is in the tree
(else from the flat `scoring_settings`), what is not priced, and the scoring check's path (IC-1's route). Tests that
need IC-1's spec or IC-2's slots skip until they are merged (the reason says which); the rest hold either way.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from league_lab import anyleague as A
from league_lab import lineup as L
from league_lab import mfl_client as M
from league_lab import player_ids as PI
from league_lab import scoring as S

from league_lab_api import ondemand as O

from .conftest import DYNASTY, SCRUBS, needs_db

FX = Path(__file__).with_name("fixtures")
MFL_FX = FX / "mfl"
KEY = "mfl:70587"
IC1 = hasattr(S, "ScoringSpec")                     # IC-1's spec merged
IC2 = hasattr(L, "slot_eligibility")                 # IC-2's eligibility sets merged
needs_ic1 = pytest.mark.skipif(not IC1, reason="IC-1's ScoringSpec is not in this tree yet (Wave I-C merge)")
needs_ic2 = pytest.mark.skipif(not IC2, reason="IC-2's slots / units are not in this tree yet (Wave I-C merge)")
not_ic1 = pytest.mark.skipif(IC1, reason="the flat-settings path: replaced by IC-1's spec once merged")


@pytest.fixture(autouse=True)
def _mfl_fixtures(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(FX / "ff" / "db_playerids.csv"))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


def _fx(path: str) -> dict:
    return json.loads((MFL_FX / path).read_text())


# ------------------------------------------------------------------ the 70587 fixtures
def test_70587_fixtures_are_mfl_answers():
    lg = _fx("70587/league.json")["league"]
    assert lg["name"] == "Make Football Great Again" and lg["baseURL"] == "https://www44.myfantasyleague.com"
    assert [(p["name"], p["limit"]) for p in lg["starters"]["position"]] == [
        ("TMQB", "1"), ("RB", "2"), ("WR+TE", "3"), ("TMPK", "1"), ("Def", "1")]
    groups = {g["positions"]: g for g in _fx("70587/rules.json")["rules"]["positionRules"]}
    assert set(groups) == {"QB", "PK", "WR", "RB", "TE", "Def"}       # the units score by the QB and PK groups
    rs = [(r["event"]["$t"], r["range"]["$t"], r["points"]["$t"]) for r in groups["RB"]["rule"]]
    assert ("RS", "0-9", "6") in rs and ("RS", "10-39", "9") in rs and ("RS", "40-110", "12") in rs
    assert ("RY", "10-999", "1/10") in rs and ("RY", "100-999", "10") in rs
    rosters = _fx("70587/rosters.json")["rosters"]["franchise"]
    assert len(rosters) == 12 and sum(len(f["player"]) for f in rosters) == 167          # 11 x 14 + 13
    wr2 = _fx("70587/weeklyResults_2.json")["weeklyResults"]
    assert wr2["week"] == "2" and len(wr2["matchup"]) == 12                              # a double header
    have = {p["id"] for p in _fx("players.json")["players"]["player"]}
    rostered = {p["id"] for f in rosters for p in f["player"]}
    assert rostered <= have and {"0662", "0712", "0501", "13130"} <= have                # units and players
    assert len(have) == 260                                                              # 216 kept + 44 new


def test_70587_reads_through_the_client():
    sl = A.sleeper()
    lg = sl.league(KEY)
    assert lg["name"] == "Make Football Great Again" and lg["total_rosters"] == 12
    names = A.team_names(sl.rosters(KEY), sl.users(KEY))
    assert names[1]["team_name"] == "Knight Train"


# ------------------------------------------------------------------ the card: lineup read-back
def test_slot_words():
    assert [O.slot_word(x) for x in ("WR+TE", "SUPER_FLEX", "TMQB", "TMPK", "RB+WR+TE", "PK", "FLEX", "DEF")] == [
        "WR/TE", "superflex", "TMQB", "TMPK", "RB/WR/TE", "K", "FLEX", "DEF"]


def test_lineup_readback_sleeper_leagues():
    sl = A.sleeper()
    scrubs = O.lineup_readback(sl.league(SCRUBS))
    assert scrubs["text"] == "Your lineup: QB · 2 RB · 2 WR · TE · 2 FLEX · K · DEF"
    assert scrubs["unread"] == [] and scrubs["bench"] == 5
    dyn = O.lineup_readback(sl.league(DYNASTY))
    assert dyn["text"] == "Your lineup: QB · 2 RB · 2 WR · TE · FLEX · superflex" and dyn["bench"] == 13


def test_lineup_readback_names_what_is_not_solved():
    out = O.lineup_readback({"roster_positions": ["QB", "RB", "WR", "IDP_FLEX", "LB", "LB", "BN"]})
    assert out["text"] == "Your lineup: QB · RB · WR"
    assert out["unread"] == ["IDP flex", "LB"] and "IDP flex, LB" in out["unread_text"]


def test_lineup_readback_70587_tells_the_truth():
    """Whatever the translation reads, the card says it: before IC-2 the three dropped starters are named."""
    out = O.lineup_readback(A.sleeper().league(KEY))
    if IC2:
        assert out["text"] == "Your lineup: TMQB · 2 RB · 3 WR/TE · TMPK · DEF" and out["unread"] == []
    else:
        assert out["text"] == "Your lineup: 2 RB · DEF"
        assert out["unread"] == ["TMQB", "WR/TE", "TMPK"]


@needs_ic2
def test_lineup_readback_70587_after_ic2():
    out = O.lineup_readback({"roster_positions": ["TMQB", "RB", "RB", "WR+TE", "WR+TE", "WR+TE", "TMPK", "DEF"] + ["BN"] * 6})
    assert out["text"] == "Your lineup: TMQB · 2 RB · 3 WR/TE · TMPK · DEF"
    assert len(out["slots"]) == 8 and out["bench"] == 6


# ------------------------------------------------------------------ the card: scoring read-back
@not_ic1
def test_scoring_readback_house_leagues_from_settings():
    sl = A.sleeper()
    s = O.scoring_readback(sl.league(SCRUBS))
    assert s["source"] == "settings"
    assert s["text"] == ("half PPR · pass TD 4, rush / catch TD 6 · 1 pt per 25 passing yards · 1 pt per 10 rushing / "
                         "receiving yards · INT −1 · fumble lost −2 · FG 3 / 4 / 5 by distance · "
                         "DEF: sacks 1, takeaways 2, points allowed by band")
    assert s["not_priced"] == [] and "2-point conversions are not projected" in s["approximated"]
    d = O.scoring_readback(sl.league(DYNASTY))
    assert "+3 at 100, +6 at 200 rushing yards" in d["pieces"] and "+2 for a 40+ yard TD" in d["pieces"]
    assert "INT −2" in d["pieces"] and "full PPR" in d["pieces"]
    # the audit's finding, said on the card: the projections leave the long-TD bonus out and price yardage bonuses
    # all or nothing
    assert any("40+ yard touchdown bonuses" in a for a in d["approximated"])
    assert any("all or nothing" in a for a in d["approximated"])


@not_ic1
def test_scoring_readback_flat_unpriced_words():
    s = O.scoring_readback({"scoring_settings": {"rec": 1, "pass_td": 4, "rush_fd": 0.5, "rec_fd": 0.5, "bonus_rec_te": 0.5,
                                                 "sack": 1, "pts_allow_0": 10}, "roster_positions": ["QB", "TE", "DEF"]})
    assert s["not_priced"] == ["receiving first downs", "rushing first downs"]   # DEF keys and the TE premium are priced
    assert s["not_priced_text"] == "Not counted in the projections: receiving first downs, rushing first downs."
    assert "TE +0.5 per catch" in s["pieces"]


@needs_ic1
def test_scoring_readback_from_the_spec():
    sl = A.sleeper()
    for lid in (KEY, SCRUBS, DYNASTY):
        lg = sl.league(lid)
        s = O.scoring_readback(lg)
        spec = O._league_spec(lg)
        assert s["source"] == "spec" and s["pieces"] == list(spec.readback())
        assert s["text"] == " · ".join(spec.readback())
    s = O.scoring_readback(sl.league(KEY))
    assert any("6 / 9 / 12" in p for p in s["pieces"])                     # touchdowns by distance
    assert any("per 10" in p for p in s["pieces"])                         # 1 pt per 10 yards


# ------------------------------------------------------------------ the card on the routes
def test_mfl_card_on_the_route(client):
    r = client.get("/api/leagues", params={"mfl": "70587"})
    assert r.status_code == 200, r.text
    card = r.json()["card"]
    assert card["lineup"]["text"].startswith("Your lineup: ")
    assert card["scoring"]["text"] and card["scoring"]["source"] in ("spec", "settings")
    assert card["check_path"] == "/api/league/scoring-check?league=mfl%3A70587"
    names = [t["team_name"] for t in r.json()["teams"]]
    assert "Knight Train" in names and len(names) == 12


def test_user_leagues_carry_cards(client):
    r = client.get("/api/leagues", params={"username": "test_manager"})
    assert r.status_code == 200, r.text
    rows = {x["league_id"]: x for x in r.json()["leagues"]}
    assert rows and all(x["card"] is not None for x in rows.values())
    for lid in set(rows) & {SCRUBS, DYNASTY}:
        card = rows[lid]["card"]
        assert card["lineup"]["text"].startswith("Your lineup: QB · 2 RB · 2 WR · TE")
        assert card["check_path"].endswith(f"league={lid}")
        assert card["scoring"]["text"]


def test_check_route_wired(client):
    """The card's check path answers once IC-1's route is in the app (skips before the merge, never fakes it)."""
    if not any(getattr(rt, "path", "") == "/api/league/scoring-check" for rt in client.app.routes):
        pytest.skip("IC-1's /api/league/scoring-check is not in this tree yet (Wave I-C merge)")
    path = O.check_path("9000000000000000001")
    r = client.get(path)
    assert r.status_code == 200, r.text
    c = r.json()
    assert {"league", "week", "n", "within_1", "misses"} <= set(c) and c["n"] > 0


# ------------------------------------------------------------------ the audit, pinned (REPORT.md's numbers)
# analytics.league_player_week.points_observed = Sleeper's own points (staging.stg_sleeper__matchup_players, which the
# app role cannot read); the stat line from analytics.fct_player_game; no stat row = a player who did not play (0).
AUDIT_SQL = """
select w.league_id, w.week, w.sleeper_player_id, w.points_observed as theirs, w.points_recomputed as sql_points, g.*
  from analytics.league_player_week w
  join analytics.fct_player_game g on g.gsis_id = w.gsis_id and g.season = 2026 and g.season_type = 'REG'
   and g.week = w.week
 where w.league_id = any(%s) and w.season = 2026 and w.week in (1, 2) and not w.is_team_defense"""


@needs_db
def test_audit_house_leagues_weeks_1_2_match_sleeper(sql):
    """Every offensive player and kicker Sleeper scored in weeks 1-2 of both house leagues, priced with
    `scoring.compute_points` from `analytics.fct_player_game`: equal to Sleeper's own points within 0.1."""
    rows = sql(AUDIT_SQL, ([SCRUBS, DYNASTY],))
    if not rows:
        pytest.skip("no 2026 weeks 1-2 in this database")
    sl = A.sleeper()                               # the leagues' settings as Sleeper sent them (the fixtures)
    settings = {lid: {k: float(v) for k, v in (sl.league(lid).get("scoring_settings") or {}).items() if v}
                for lid in (SCRUBS, DYNASTY)}
    misses = [(r["league_id"], r["week"], r["player_name"], r["theirs"], S.compute_points(r, settings[r["league_id"]]))
              for r in rows if abs(float(r["theirs"]) - S.compute_points(r, settings[r["league_id"]])) > 0.1]
    sql_apart = [r["player_name"] for r in rows
                 if abs(float(r["sql_points"] or 0) - S.compute_points(r, settings[r["league_id"]])) > 0.01]
    assert len(rows) >= 700 and misses == [] and sql_apart == []
