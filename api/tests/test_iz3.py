"""IZ-3 (Wave I-Z): the card says what he means for the viewer's roster (one line, My Week's numbers) and at most three
reasons (role, matchup, form), each naming where to read more. Hand-built rows first (no database, nothing cached
between tests), then the house leagues: the line's numbers are the ones My Week's "Recommended lineup" shows."""

import types

import pandas as pd
import pytest

from league_lab_api import availability as AVL
from league_lab_api import myweek as MW
from league_lab_api import player as P

from .conftest import needs_db

SCRUBS, UNCLEAN = "1389709692405551104", "1321941740235550720"


def _full(*rows):
    return [dict(r) for r in rows]


def _ctx(monkeypatch, rows: pd.DataFrame, full: list[dict]):
    monkeypatch.setattr(AVL, "roster_context", lambda league, team, week, house=True: types.SimpleNamespace(rows=rows))
    monkeypatch.setattr(MW, "lineup", lambda r: ([], full))


ROWS = pd.DataFrame([
    {"sleeper_player_id": "1", "gsis_id": "g1", "player_name": "Ann Able", "position": "WR", "slot_type": "WR", "role": "starter", "value": 14.0},
    {"sleeper_player_id": "2", "gsis_id": "g2", "player_name": "Bo Bell", "position": "WR", "slot_type": "WR", "role": "starter", "value": 9.5},
    {"sleeper_player_id": "3", "gsis_id": "g3", "player_name": "Cy Cole", "position": "RB", "slot_type": "FLEX", "role": "starter", "value": 8.0},
    {"sleeper_player_id": "4", "gsis_id": "g4", "player_name": "Di Dane", "position": "WR", "slot_type": "BN", "role": "bench", "value": 6.1},
])
FULL = _full(
    {"key": "1", "gsis_id": "g1", "player_name": "Ann Able", "position": "WR", "slot": "WR1", "role": "starter", "value": 14.0, "margin": 7.9, "margin_vs": "Di Dane"},
    {"key": "2", "gsis_id": "g2", "player_name": "Bo Bell", "position": "WR", "slot": "WR2", "role": "starter", "value": 9.5, "margin": 3.4, "margin_vs": "Di Dane"},
    {"key": "3", "gsis_id": "g3", "player_name": "Cy Cole", "position": "RB", "slot": "FLEX1", "role": "starter", "value": 8.0, "margin": None, "margin_vs": None},
    {"key": "4", "gsis_id": "g4", "player_name": "Di Dane", "position": "WR", "slot": "Bench", "role": "bench", "value": 6.1},
    {"key": "5", "gsis_id": "g5", "player_name": "Ed Eads", "position": "TE", "slot": "Can't play", "role": "unplayable", "value": 0.0, "flag": "bye"},
)


def _card(**kw):
    c = {"week": 5, "position": "WR", "rostered_by_roster_id": 2, "is_free_agent": False, "proj_points": 9.0}
    c.update(kw)
    return c


def test_a_starter_says_his_slot_and_his_margin_over_the_next_man(monkeypatch):
    _ctx(monkeypatch, ROWS, FULL)
    line = P.roster_line("L", "g2", 2, _card(), house=True)
    assert line["kind"] == "starter" and line["slot"] == "WR2" and line["margin"] == 3.4 and line["vs"] == "Di Dane"
    assert line["words"] == "Starts for you at WR2 this week, 3.4 points ahead of Di Dane."
    line = P.roster_line("L", "g3", 2, _card(position="RB"), house=True)       # no reserve behind him: no number made up
    assert line["words"] == "Starts for you at FLEX1 this week; nobody on your bench can take his place."


def test_a_bench_player_says_whom_he_sits_behind_and_a_player_who_cannot_play_says_why(monkeypatch):
    _ctx(monkeypatch, ROWS, FULL)
    line = P.roster_line("L", "g4", 2, _card(), house=True)
    assert line == {"kind": "bench", "behind": ["Ann Able", "Bo Bell"], "words": "On your bench this week, behind Ann Able and Bo Bell."}
    assert P.roster_line("L", "g5", 2, _card(position="TE"), house=True)["words"] == "Can't play for you this week (bye)."


def test_a_free_agent_who_would_start_names_the_starter_and_the_gain(monkeypatch):
    _ctx(monkeypatch, ROWS, FULL)
    card = _card(rostered_by_roster_id=None, is_free_agent=True, proj_points=12.25)
    line = P.roster_line("L", "fa", 2, card, house=True)
    # the lowest starter whose spot admits a WR is Cy Cole at FLEX1 (8.0): +4.25 → 4.2 shown (one decimal, as My Week)
    assert line["kind"] == "free_agent_starts" and line["over"] == "Cy Cole" and line["slot"] == "FLEX1"
    assert line["words"] == f"A free agent: he would start for you at FLEX1 over Cy Cole (+{12.25 - 8.0:.1f} this week)."


def test_a_free_agent_fills_an_empty_spot_and_one_who_would_not_start_says_the_bar(monkeypatch):
    rows = pd.concat([ROWS, pd.DataFrame([{"sleeper_player_id": None, "gsis_id": None, "player_name": None, "position": None,
                                           "slot_type": "TE", "role": "empty", "value": None, "is_empty_slot": True}])],
                     ignore_index=True)
    _ctx(monkeypatch, rows, FULL)
    line = P.roster_line("L", "fa", 2, _card(rostered_by_roster_id=None, is_free_agent=True, position="TE", proj_points=5.0), house=True)
    assert line["kind"] == "free_agent_starts" and line["slot"] == "TE" and line["gain"] == 5.0
    _ctx(monkeypatch, ROWS, FULL)
    line = P.roster_line("L", "fa", 2, _card(rostered_by_roster_id=None, is_free_agent=True, proj_points=7.9), house=True)
    assert line["kind"] == "free_agent_sits" and line["over"] == "Cy Cole"
    assert line["words"] == "A free agent who would not start for you this week: Cy Cole, your lowest starter where he could play, projects 8.0."


def test_another_teams_player_names_the_team_and_no_lineup_costs_no_card(monkeypatch):
    line = P.roster_line("mfl:1", "g9", 1, _card(rostered_by_roster_id=7, rostered_by_team="Team Seven"), house=False)
    assert line == {"kind": "other_team", "team": "Team Seven", "words": "On another team: Team Seven."}
    assert P.roster_line("mfl:1", "g9", 1, _card(rostered_by_roster_id=7), house=False)["words"] == "On another team in this league."

    def boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(AVL, "roster_context", boom)
    assert P.roster_line("mfl:1", "g9", 1, _card(rostered_by_roster_id=1), house=False) is None
    assert P.roster_line("L", "g9", 2, _card(week=None, rostered_by_roster_id=None, is_free_agent=True), house=True)["kind"] == "free_agent"


def _sections(role_blocks=(), nxt=None, ppg=None, exp=None):
    return {"sections": {
        "role": {"blocks": [{"kind": "markdown", "text": t} for t in role_blocks]},
        "projection": {"blocks": [{"kind": "markdown", "text": nxt}] if nxt else []},
        "value": {"blocks": [{"kind": "metrics", "metrics": [{"label": "Points / game", "value": ppg}, {"label": "Expected", "value": exp}]}]},
    }}


def test_at_most_three_reasons_each_one_sentence_naming_where_to_read_more():
    card = _sections(["**Bigger role: 8.5 targets a game in his last 2, from 5.0.**"],
                     "Next: week 5 vs **BUF** — BUF ranks #6 of 32 vs RB (1 = gives up the most).", "19.8", "16.1")
    r = P.reasons(card)
    assert [x["key"] for x in r] == ["role", "matchup", "form"]
    assert r[0]["words"] == "Role: bigger role: 8.5 targets a game in his last 2, from 5.0. More under Usage."
    assert r[1]["words"] == "Matchup: week 5 vs BUF — BUF ranks #6 of 32 vs RB (1 = gives up the most). More in the schedule below."
    assert r[2]["words"] == "Form: 19.8 points per game this season on work worth 16.1. More under Game log."
    assert all(x["words"].count(". More ") == 1 for x in r) and len(r) <= 3


def test_a_reason_with_nothing_to_say_is_left_out():
    early = "**Too early to say: 1 game with a snap so far this season; a change is called from his last 2 games.**"
    opp = ("Opportunity vs production: **in line** — 23% of the targets and carries of his team's WRs and TEs, 26% of their "
           "fantasy points in League of Scrubs scoring (weeks 1–4, 4 games). Of the whole team: 12% of its targets + carries.")
    r = P.reasons(_sections([early, opp]))
    assert r == [{"key": "role", "words": "Role: 23% of the targets and carries of his team's WRs and TEs and 26% of their fantasy "
                                         "points (weeks 1–4, 4 games). More under Usage."}]
    assert P.reasons(_sections([early])) == []                                   # too early and no shares: no role reason
    assert P.reasons(_sections(ppg="—")) == [] and P.reasons({}) == []          # unknown is not zero: no form reason


# ---- the house leagues: the card's line against My Week's "Recommended lineup" (the same numbers) ----
def _get(client, url):
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code, r.text[:300])
    return r.json()


@needs_db
@pytest.mark.parametrize("league,team", [(SCRUBS, 2), (UNCLEAN, 12)])
def test_the_line_agrees_with_my_week_on_the_house_leagues(client, league, team):
    mw = _get(client, f"/api/my-week?league={league}&team={team}")
    full = mw.get("lineup_full") or []
    if not full:
        pytest.skip("no lineup this week on this copy")
    seen = set()
    for row in [r for r in full if r.get("gsis_id")][:6]:
        d = _get(client, f"/api/player/{row['gsis_id']}?league={league}&team={team}")
        assert d.get("week") == mw.get("week")
        line = d.get("roster_line") or {}
        if row["role"] == "starter":
            assert line["kind"] == "starter" and line["slot"] == row["slot"]
            if row.get("margin") is not None and row.get("margin_vs"):
                assert line["margin"] == round(float(row["margin"]), 1) and line["vs"] == row["margin_vs"]
                assert f"{float(row['margin']):.1f} points ahead of {row['margin_vs']}" in line["words"]
        elif row["role"] == "bench":
            assert line["kind"] == "bench"
            assert all(n in [s["player_name"] for s in full if s["role"] == "starter"] for n in line["behind"])
        else:
            assert line["kind"] in ("bench", "out")
        seen.add(line["kind"])
        assert len(d.get("reasons") or []) <= 3
    assert "starter" in seen
    w = _get(client, f"/api/waivers?league={league}&team={team}&position=ALL&limit=60")
    fas = [p for p in w.get("free_agents") or [] if p.get("gsis_id") and p.get("projection") is not None][:4]
    starters = {r["key"]: r for r in full if r["role"] == "starter" and r.get("gsis_id")}
    for fa in fas:
        d = _get(client, f"/api/player/{fa['gsis_id']}?league={league}&team={team}")
        line = d.get("roster_line") or {}
        assert line.get("kind") in ("free_agent_starts", "free_agent_sits", "free_agent"), line
        if line.get("over"):                                    # the starter he is measured against, at My Week's value
            low = next(r for r in starters.values() if r["player_name"].strip() == line["over"])
            if line["kind"] == "free_agent_starts":
                assert line["slot"] == low["slot"]
                assert line["gain"] == round(float(d["proj_points"]) - float(low["value"]), 1)
            else:
                assert f"projects {float(low['value']):.1f}" in line["words"]


@needs_db
def test_another_teams_player_and_no_league(client, sql):
    rows = sql("select m.team_name, m.roster_id from analytics.dim_league_member m where m.league_id = %s and m.roster_id <> 2 "
               "order by m.roster_id limit 1", (SCRUBS,))
    if not rows:
        pytest.skip("no members on this copy")
    d = _get(client, f"/api/player/00-0036900?league={SCRUBS}&team=2")
    line = d.get("roster_line") or {}
    if d.get("rostered_by_roster_id") not in (None, 2):
        name = sql("select team_name from analytics.dim_league_member where league_id = %s and roster_id = %s",
                   (SCRUBS, int(d["rostered_by_roster_id"])))[0]["team_name"]
        assert line["kind"] == "other_team" and line["words"].startswith(f"On another team: {name}")
    ref = _get(client, "/api/player/00-0036900?league=ref%3Ahalf")
    assert ref.get("roster_line") is None and len(ref.get("reasons") or []) <= 3
