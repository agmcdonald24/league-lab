"""Wave I-C, IC-2: slots as eligibility sets, team units as players — dad's league, MyFantasyLeague 70587.

Fixtures (`fixtures/mfl/70587/`, IC-3's fetch of 2026-10-03 through the browser pane): "Make Football Great Again",
12 teams, roster 14, starters TMQB x1, RB x2, WR+TE x3, TMPK x1, Def x1; team 1 is "Knight Train". The team units
(TMQB `06xx`, TMPK `07xx`) are in the shared `fixtures/mfl/players.json`.
"""

from __future__ import annotations

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import player_ids as PI
from league_lab.lineup import UNITS, parse_slots

from .conftest import needs_db
from .test_i0b import IDS, MFL_FX, _fx

KEY = "mfl:70587"
DAD = ["TMQB", "RB", "RB", "WR+TE", "WR+TE", "WR+TE", "TMPK", "DEF"]
WORDS = ["team QB", "RB1", "RB2", "WR/TE 1", "WR/TE 2", "WR/TE 3", "team K", "DEF"]


@pytest.fixture(autouse=True)
def _mfl_fixtures(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


# ------------------------------------------------------------------ the translation (no database)
def test_70587_slots_in_the_leagues_own_words():
    slots, note = M.slots(_fx("70587/league.json")["league"])
    assert [s for s in slots if s != "BN"] == DAD and slots.count("BN") == 6        # roster 14 - 8 starters
    assert note["idp"] == [] and note["units"] == ["TMPK", "TMQB"] and not note["approximated"]
    parsed, ignored = parse_slots(slots)
    assert len(parsed) == 8 and ignored == []
    lg = A.sleeper().league(KEY)
    assert lg["roster_positions"] == slots


def test_70587_units_are_players_with_a_team_and_no_gsis():
    sl = A.sleeper()
    rosters = sl.rosters(KEY)
    players = sl.players()
    ids = [p for r in rosters for p in r["players"]]
    units = [p for p in ids if (players.get(p) or {}).get("position") in UNITS]
    by = sl.mfl.mapped_by(KEY)
    print(f"\nMFL 70587: {len(ids)} rostered, {len(units)} team units, mapped by {by}, unmapped {sl.mfl.unmapped(KEY)}")
    assert len(units) == 34 and by["unit"] == 34 and sl.mfl.unmapped(KEY) == []
    cin = players["mfl:0656"]
    assert {k: cin[k] for k in ("player_key", "position", "team", "player_name", "unit")} == {
        "player_key": "mfl:0656", "position": "TMQB", "team": "CIN", "player_name": "Cincinnati Bengals QB", "unit": True}
    assert players["mfl:0714"]["player_name"] == "Los Angeles Chargers K" and players["mfl:0714"]["team"] == "LAC"
    assert players["mfl:0675"]["team"] == "TB"                                     # MFL's TBB -> Sleeper's TB
    # Sleeper's starters array: one id per starting slot ("0" = empty), each in a slot that admits him
    knight = next(r for r in rosters if r["roster_id"] == 1)
    assert len(knight["starters"]) == 8
    slot_of = A.LU.starter_slots(lg_slots := sl.league(KEY)["roster_positions"], knight["starters"])
    for sid, slot in slot_of.items():
        pos = frozenset(players[sid].get("fantasy_positions") or [players[sid]["position"]])
        assert pos & A.LU.SLOT_ELIGIBILITY[slot], (sid, slot)
    assert all(s in knight["players"] for s in knight["starters"] if s != "0") and len(lg_slots) == 14


def test_free_agent_units_one_per_unrostered_team():
    sl = A.sleeper()
    rosters, players = sl.rosters(KEY), sl.players()
    rostered = {(players[p]["position"], players[p]["team"]) for r in rosters for p in r["players"]
                if players.get(p, {}).get("position") in UNITS}
    free = [(sid, p) for sid, p in players.items() if p.get("position") in UNITS and sid not in
            {x for r in rosters for x in r["players"]} and (p["position"], p["team"]) not in rostered]
    assert len(rostered) == 34 and len(free) == 64 - 34
    assert len({(p["position"], p["team"]) for _, p in free}) == 30


# ------------------------------------------------------------------ the API on the fixture (database)
@needs_db
def test_70587_my_week_full_eight_slot_lineup_with_the_units_priced(client):
    r = client.get(f"/api/my-week?league={KEY}&team=1")
    assert r.status_code == 200, r.text[:500]
    d = r.json()
    assert d["team_name"] == "Knight Train" and d["platform"] == "mfl"
    assert [x["slot"] for x in d["lineup"]] == WORDS
    rows = {x["slot"]: x for x in d["lineup"]}
    tmqb, tmpk = rows["team QB"], rows["team K"]
    assert (tmqb["position"], tmqb["team"], tmqb["player_name"]) == ("TMQB", "CIN", "Cincinnati Bengals QB")
    assert (tmpk["position"], tmpk["team"], tmpk["player_name"]) == ("TMPK", "LAC", "Los Angeles Chargers K")
    # TMQB = the starting quarterback's line priced in this league's scoring (A.unit_lines); TMPK = the team's kicker
    lg = A.sleeper().league(KEY)
    scoring, slots = A.league_scoring(lg)
    pr = A.price_week(A_query(), KEY, scoring, slots, int(lg["season"]), int(d["week"]))
    u = pr.units.set_index(["position", "team"])
    burrow = u.loc[("TMQB", "CIN")]
    qb_alone = float(pr.proj[burrow["starter_gsis"]])
    k = pr.kd["K"]
    lac_k = float(pd_max(k[k["team"] == "LAC"]["proj_points"]))
    print(f"\n70587 team 1 week {d['week']}: TMQB CIN {tmqb['value']} (starter {burrow['starter_name']} "
          f"{qb_alone:.2f} alone), TMPK LAC {tmpk['value']} (kicker {lac_k:.2f}); lineup {d['lineup_value']}")
    for x in d["lineup_full"]:
        print(f"   {x['slot']:<11} {str(x['player_name']):<28} {str(x['position']):<5} {str(x.get('team')):<4} {x['value']}  {x['flag']}")
    assert tmqb["value"] == pytest.approx(round(qb_alone, 2), abs=0.011)
    assert tmpk["value"] == pytest.approx(round(lac_k, 2), abs=0.011)
    # nobody "can't play" for want of a slot: the WRs / TEs are starters or on the bench
    full = d["lineup_full"]
    assert not [x for x in full if x["slot"] == "Can't play" and str(x.get("flag") or "").startswith(("No slot", "no "))]
    cant = [(x["position"], x["flag"]) for x in full if x["slot"] == "Can't play"]
    assert cant == [("WR", "NFL injured reserve")] and "No slot" not in [x["slot"] for x in full]   # Ja'Kobi Lane
    assert all(x["player_name"] for x in d["lineup"]) and d["lineup_value"] == pytest.approx(sum(x["value"] for x in d["lineup"]))
    assert d["on_demand"]["unmapped_players"] == [] and d["on_demand"]["mfl_unmapped"] == []
    # the opponent is solved with the same slots
    assert d["opponent"] is None or d["opponent"]["lineup_value"] is not None


@needs_db
def test_70587_free_agents_include_the_units_priced(client):
    r = client.get(f"/api/waivers?league={KEY}&team=1&position=ALL&limit=500")
    assert r.status_code == 200, r.text[:500]
    fa = r.json()["free_agents"]
    units = [x for x in fa if x["position"] in UNITS]
    print(f"\n70587 free agents: {len(fa)}, team units {len(units)}: "
          f"{[(x['player_name'], x['team'], x['projection']) for x in units[:4]]}")
    assert len(units) == 30 and len({(x["position"], x["team"]) for x in units}) == 30
    assert sum(x["projection"] is not None for x in units) >= 24          # byes (and a team without a line) unpriced
    # the free TMQB units are priced like the rostered ones (the starter's line)
    assert any(x["position"] == "TMQB" and x["projection"] for x in units)
    assert any(x["position"] == "TMPK" and x["projection"] for x in units)


@needs_db
def test_70587_rosters_route_and_the_team_hub_name_the_units(client):
    teams = client.get(f"/api/leagues/{KEY}/rosters")
    assert teams.status_code == 200 and len(teams.json()) == 12
    assert {"roster_id": 1, "team_name": "Knight Train", "manager_name": None} in teams.json()
    hub = client.get(f"/api/team?league={KEY}&team=1")
    assert hub.status_code == 200, hub.text[:300]
    tops = {s["slot_type"]: s["top"] for s in hub.json()["slot_strength"] if s.get("top")}
    assert tops["TMQB"]["player_name"] == "Cincinnati Bengals QB" and tops["TMPK"]["player_name"] == "Los Angeles Chargers K"
    assert set(tops) >= {"TMQB", "RB", "WR+TE", "TMPK", "DEF"}


@needs_db
def test_sleeper_house_league_lineup_unchanged(client):
    """Sleeper slot names solve exactly as before (the parity suite pins the numbers; here: the slot words)."""
    r = client.get("/api/my-week?league=1389709692405551104&team=2&source=sleeper")
    assert r.status_code == 200
    slots = [x["slot"] for x in r.json()["lineup"]]
    assert slots[:3] == ["QB", "RB1", "RB2"] and "No slot" not in slots


def A_query():
    from league_lab_api.db import query
    return query


def pd_max(s):
    import pandas as pd
    return pd.to_numeric(s, errors="coerce").max()


@needs_db
def test_every_route_answers_for_dads_league(client):
    """The screens beyond My Week read the same slots (eligibility sets) and the unit rows without a 500."""
    mw = client.get(f"/api/my-week?league={KEY}&team=1").json()
    gsis = [x["gsis_id"] for x in mw["lineup"] if x.get("gsis_id")]
    routes = [f"/api/team?league={KEY}&team=1", f"/api/waivers?league={KEY}&team=1", f"/api/trades/partners?league={KEY}&team=1",
              f"/api/ros?league={KEY}", f"/api/league?league={KEY}&team=1", f"/api/player/{gsis[0]}?league={KEY}&team=1"]
    for path in routes:
        r = client.get(path)
        assert r.status_code == 200, (path, r.text[:300])
    other = mw["opponent"]["roster_id"] if mw.get("opponent") else 2
    theirs = client.get(f"/api/my-week?league={KEY}&team={other}").json()
    get = [x["gsis_id"] for x in theirs["lineup"] if x.get("gsis_id")][:1]
    ev = client.post("/api/trades/evaluate", json={"league": KEY, "team": 1, "partner": other, "give": gsis[:1], "get": get})
    assert ev.status_code == 200, ev.text[:300]
