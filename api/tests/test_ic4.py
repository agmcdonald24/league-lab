"""Wave I-D, IC-4: the team units and the double header, finished — dad's league, MyFantasyLeague 70587.

Fixtures (`fixtures/mfl/70587/`, IC-3's fetch of 2026-10-03): 12 teams, starters TMQB / RB / RB / WR+TE x3 / TMPK / Def;
team 1 "Knight Train" rosters the Bengals' and the Buccaneers' QB units (`mfl:0656`, `mfl:0675`) and the Chargers' kicker
unit (`mfl:0714`); weeks 2, 4, 6-9, 11 and 13 are double headers. The ESPN fixture overlay (Hall and Price Out) is on only
in the Waivers test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from league_lab import anyleague as A
from league_lab import injury_feed as F
from league_lab import mfl_client as M
from league_lab import player_ids as PI

from league_lab_api import availability as AV
from league_lab_api import decisions

from .conftest import needs_db
from .test_i0b import IDS, MFL_FX, _fx

KEY = "mfl:70587"
ESPN = Path(__file__).with_name("fixtures") / "espn"


@pytest.fixture(autouse=True)
def _mfl_fixtures(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    decisions.clear_memo()
    yield
    PI.reset()
    A._default = None
    decisions.clear_memo()


@pytest.fixture
def overlay(monkeypatch):
    """The availability overlay on, reading the ESPN fixture (Breece Hall and Jadarian Price Out in week 4)."""
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    F.reset()
    AV._snap = None
    AV._built = None
    AV.clear_context()
    yield
    F.reset()
    AV._snap = None
    AV.clear_context()


# ------------------------------------------------------------------ rest of season: the unit rows
@needs_db
def test_ros_unit_rows_priced_week_by_week(client):
    r = client.get(f"/api/ros?league={KEY}&team=1&limit=500")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    units = [p for p in d["players"] if p["unit"]]
    assert sum(p["position"] == "TMQB" for p in units) == 32 and sum(p["position"] == "TMPK" for p in units) == 32
    assert all(not p["unit"] for p in d["players"] if p["position"] not in ("TMQB", "TMPK"))
    cin = next(p for p in units if p["player_key"] == "mfl:0656")
    n_weeks = d["last_week"] - d["from_week"] + 1
    assert cin["player_name"] == "Cincinnati Bengals QB" and cin["team"] == "CIN" and cin["gsis_id"] is None
    assert cin["rostered_by_roster_id"] == 1 and cin["rostered_by_team"] == "Knight Train"
    assert cin["priced_from"]["player_name"] == "Joe Burrow"
    assert cin["priced_from_words"] == "Priced from Joe Burrow's line (the team's starting QB each week)"
    assert cin["bye_weeks"] == [6] and cin["ros_games"] == n_weeks - 1            # the bye is a week off
    assert cin["why"] is not None and cin["per_game"]                             # the starter's pieces, QB rules
    lac = next(p for p in units if p["player_key"] == "mfl:0714")
    assert lac["position"] == "TMPK" and lac["priced_from_words"].endswith("(the team's kicker each week)")
    free = [p for p in units if p["rostered_by_roster_id"] is None]
    assert free and all(p["player_key"].startswith(("mfl:TMQB-", "mfl:TMPK-")) for p in free)
    assert len(free) == 64 - 34                                                   # IC-2: 34 units rostered
    # a position filter for each unit
    only = client.get(f"/api/ros?league={KEY}&position=TMQB&limit=500").json()["players"]
    assert len(only) == 32 and {p["position"] for p in only} == {"TMQB"}
    print(f"\nBengals QB rest of season {cin['ros_points']} over {cin['ros_games']} games (week {d['from_week']}: "
          f"{cin['week_points']}), rank {cin['pos_rank']} of 32 team QBs; Chargers K {lac['ros_points']}")


@needs_db
def test_ros_units_equal_the_weeks_unit_prices():
    """Each week of a unit's rest of season = that week's `price_units` (My Week's number), every team."""
    from league_lab_api.db import query
    lg = A.sleeper().league(KEY)
    sc, slots = A.league_scoring(lg)
    df = A.ros_table(query, KEY, lg, 4, 6, None)
    u = df[df["unit"]]
    assert len(u) == 64
    for w in (4, 5):
        pr = A.price_week(query, KEY, sc, slots, 2026, w)
        want = {(r.position, r.team): round(float(r.proj_points), 2) for r in pr.units.itertuples()}
        got = {}
        for r in u.itertuples():
            v = dict((int(a), b) for a, b in r.weeks_json).get(w)
            if v is not None:
                got[(r.position, r.team)] = v
        assert got and all(got[k] == want[k] for k in got), w
        assert set(got) <= set(want)
    # a sum of its weeks, like every row
    for r in u.itertuples():
        assert abs(sum(b for _, b in r.weeks_json) - r.ros_points) < 0.02


@needs_db
def test_value_to_my_lineup_counts_units_against_the_wire(client):
    r = client.get(f"/api/ros?league={KEY}&team=1&view=lineup&limit=500")
    assert r.status_code == 200, r.text[:300]
    ps = r.json()["players"]
    mine = {p["player_key"]: p for p in ps if p["unit"] and p["lineup_kind"] == "mine"}
    assert set(mine) == {"mfl:0656", "mfl:0675", "mfl:0714"}
    assert all(p["lineup_points"] is not None for p in mine.values())
    assert "TMQB" not in " ".join(p["lineup_why"] for p in mine.values())      # "team QB" in words
    fa = [p for p in ps if p["unit"] and p["lineup_kind"] == "fa"]
    assert len(fa) == 30 and all(p["rostered_by_roster_id"] is None for p in fa)
    for p in mine.values():
        print(f"\n{p['player_name']}: {p['lineup_points']} over {p['lineup_weeks']} weeks — {p['lineup_why']}")


# ------------------------------------------------------------------ the unit's card, the Team Hub
@needs_db
def test_unit_card_is_the_starters_card(client):
    r = client.get(f"/api/player/mfl:0656?league={KEY}&team=1")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["unit"]["header"] == "Cincinnati Bengals QB — priced from Joe Burrow's line"
    assert d["player_name"] == "Cincinnati Bengals QB" and d["gsis_id"] == d["unit"]["starter_gsis"]
    assert d["rostered_by_roster_id"] == 1 and d["is_free_agent"] is False
    assert "on **Knight Train**" in d["header"] and d["header"].startswith("team QB · priced from Joe Burrow's line")
    ros = client.get(f"/api/ros?league={KEY}&position=TMQB&limit=500").json()["players"]
    free = next(p for p in ros if p["rostered_by_roster_id"] is None)
    f = client.get(f"/api/player/{free['player_key']}?league={KEY}").json()
    assert f["is_free_agent"] is True and f["unit"]["key"] == free["player_key"]
    assert client.get(f"/api/player/mfl:9999?league={KEY}").status_code == 404


@needs_db
def test_slot_strength_names_the_unit_with_its_team(client):
    r = client.get(f"/api/team?league={KEY}&team=1")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    ss = {s["slot_type"]: s for s in d["slot_strength"]}
    top = ss["TMQB"]["top"]
    assert top["unit"] is True and top["team"] == "CIN" and top["short_name"] == "Bengals QB"
    assert top["sleeper_id"] == "mfl:0656"
    assert ss["TMPK"]["top"]["team"] == "LAC" and ss["TMPK"]["top"]["short_name"] == "Chargers K"
    units = [x for x in d["roster"] if x["position"] in ("TMQB", "TMPK")]
    assert len(units) == 3 and all(x["team"] and x["unit"] for x in units)


# ------------------------------------------------------------------ manager names
def test_manager_names_from_mfl_owner_name(monkeypatch):
    """MFL's public `league` export carries no `owner_name` for 70587 (checked live through the pane, 2026-10-03):
    no manager name, never the team name repeated. When a league shares it, it is the manager name."""
    sl = A.sleeper()
    names = A.team_names(sl.rosters(KEY), sl.users(KEY))
    assert names[1] == {"team_name": "Knight Train", "manager_name": None}
    assert all(n["manager_name"] is None for n in names.values())
    lg = json.loads(json.dumps(_fx("70587/league.json")["league"]))
    for f in lg["franchises"]["franchise"]:
        if f["id"] == "0001":
            f["owner_name"] = "Owner &amp; One"                                  # HTML-escaped, as MFL sends names
    assert M.franchise_owners(lg) == {"0001": "Owner & One"}
    monkeypatch.setattr(sl.mfl.client, "league", lambda lid: lg)
    names = A.team_names(sl.rosters(KEY), sl.users(KEY))
    assert names[1] == {"team_name": "Knight Train", "manager_name": "Owner & One"} and names[2]["manager_name"] is None


@needs_db
def test_rosters_route_and_my_week_header_carry_the_owner(client, monkeypatch):
    lg = json.loads(json.dumps(_fx("70587/league.json")["league"]))
    lg["franchises"]["franchise"][0]["owner_name"] = "Owner One"
    sl = A.sleeper()
    monkeypatch.setattr(A, "sleeper", lambda: sl)
    monkeypatch.setattr(sl.mfl.client, "league", lambda lid: lg)
    rows = client.get(f"/api/leagues/{KEY}/rosters").json()
    assert next(r for r in rows if r["roster_id"] == 1)["manager_name"] == "Owner One"
    assert next(r for r in rows if r["roster_id"] == 2)["manager_name"] is None
    d = client.get(f"/api/my-week?league={KEY}&team=1").json()
    assert d["manager_name"] == "Owner One" and d["summary"].startswith("**Knight Train** · Owner One")


# ------------------------------------------------------------------ double headers
@needs_db
def test_league_screen_counts_both_games(client):
    r = client.get(f"/api/league?league={KEY}&team=1")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    wk2 = next(w for w in d["all_play_week"] if w["roster_id"] == 1 and w["week"] == 2)
    assert [g["opponent_team_name"] for g in wk2["games"]] == ["Millertime", "Blitzburg"]
    assert wk2["result"] == "L/L" and len({g["points"] for g in wk2["games"]}) == 1
    assert sum(1 for w in d["all_play_week"] if w["week"] == 2) == 12              # one row a team, both games on it
    for a in d["all_play"]:                                                       # every other team once a week
        assert a["all_play_wins"] + a["all_play_losses"] + a["all_play_ties"] == 11 * d["weeks_scored"]
    st = {s["roster_id"]: s for s in d["standings"]}
    assert st[1]["games"] == 4 and (st[1]["wins"], st[1]["losses"]) == (1, 3)
    this = next(m for m in d["matchups"] if not m["played"])
    assert this["week"] == 4 and this["double_header"] and len(this["games"]) == 12
    mine = [g for g in this["games"] if g["mine"]]
    assert [g["b"]["team_name"] if g["a"]["roster_id"] == 1 else g["a"]["team_name"] for g in mine] == \
        ["Big Mac Attack", "Klaby Crew"]
    assert this["games"][:2] == mine                                              # mine first
    last = next(m for m in d["matchups"] if m["played"])
    assert last["week"] == 3 and not last["double_header"] and len(last["games"]) == 6


@needs_db
def test_record_for_an_mfl_league_has_both_games(client):
    r = client.get(f"/api/record?league={KEY}")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["available"] is False                                               # no projection record kept
    by = {m["week"]: m for m in d["results"]}
    assert len(by[2]["games"]) == 12 and by[2]["double_header"] and len(by[1]["games"]) == 6
    st = _fx("70587/leagueStandings.json")["leagueStandings"]["franchise"]
    want = {int(f["id"]): (int(f["h2hw"]), int(f["h2hl"])) for f in st}
    got = {x["roster_id"]: (x["wins"], x["losses"]) for x in d["records"]}
    assert got == want                                                           # MFL's own standings


# ------------------------------------------------------------------ Waivers: RB2 stays empty
@needs_db
def test_rb2_claim_first_when_hall_and_price_are_out(client, overlay):
    r = client.get(f"/api/waivers?league={KEY}&team=1")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    # IE-1 (Wave I-E, the casual-user review: no triple copy): Help now lists what the three strongest do not already
    # show, so the RB2 claim that leads the three is not repeated as Help now's first row; it leads the three
    first = d["top3"][0]
    assert first["move"]["add"]["position"] == "RB" and first["move"]["fills_empty_slot"] is True
    assert first["reason"] == "Fills your empty RB2 this week."
    assert first["lead"].startswith(f"{first['move']['add']['player_name']} fills your empty RB2: ")
    assert all(c["move"]["add"]["player_name"] != first["move"]["add"]["player_name"] for c in d["views"]["help"]["moves"])
    words = " ".join(c["reason"] for c in [*d["top3"], *d["views"]["help"]["moves"]])
    assert "TMPK" not in words and "TMQB" not in words                           # the unit slots in words
    print(f"\nHelp now first: {first['move']['words']['headline']} — {first['reason']}")
