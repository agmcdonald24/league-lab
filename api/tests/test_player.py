"""/api/player/{gsis} and /api/search against the marts (independent SQL)."""

from __future__ import annotations

import pytest

from .conftest import DYNASTY, SCRUBS, needs_db

pytestmark = needs_db

# the headless check's players: rostered WR (dynasty 12), a WR, a K (Scrubs 2), a free-agent WR, no projection
# + a bench player (Emanuel Wilson), a taxi-squad player (Caleb Douglas), an IR-slot player (Adam Randall), an Out player
CASES = [(DYNASTY, 12, "00-0036963"), (DYNASTY, 12, "00-0036919"), (DYNASTY, 12, "00-0038824"),
         (DYNASTY, 12, "00-0038797"), (DYNASTY, 12, "00-0041523"), (DYNASTY, 12, "00-0040888"),
         (SCRUBS, 2, "00-0035358"), (SCRUBS, 2, "00-0038824"), (SCRUBS, 2, "00-0035700"), (SCRUBS, 2, "00-0041496")]


def blocks(section: dict, kind: str) -> list:
    return [b for b in section["blocks"] if b["kind"] == kind]


@pytest.mark.parametrize("league,team,gsis", CASES)
def test_player_card_numbers(client, sql, league, team, gsis):
    r = client.get(f"/api/player/{gsis}?league={league}&team={team}")
    assert r.status_code == 200
    d = r.json()
    assert list(d["sections"]) == ["usage", "projection", "availability", "value", "signals", "role"]   # ---- IL-1: + role
    proj = sql("""select proj_points, p10, p25, p75, p90 from analytics.mart_player_week_projections
                  where league_id = %s and gsis_id = %s and season = %s and week = %s""", (league, gsis, d["season"], d["week"]))
    m = blocks(d["sections"]["projection"], "metrics")
    sits = bool((d.get("availability") or {}).get("sits"))
    if sits:
        # IS-2 + PO (Wave I-S): a player who sits this week (the one definition; here "Out" on this week's own injury
        # report) is shown no projection the mart may still hold: 0, the reason, no metrics
        assert not m and blocks(d["sections"]["projection"], "unavailable") and d["proj_points"] == 0.0
    elif proj:
        p = proj[0]
        # the 50% range (plan D6) sits between the projection and the floor; weeks frozen before it existed have none
        mid = [("Most weeks", f"{float(p['p25']):.0f}–{float(p['p75']):.0f}")] if p["p25"] is not None and p["p75"] is not None else []
        assert [(x["label"], x["value"]) for x in m[0]["metrics"]] == [
            ("Projected", f"{float(p['proj_points']):.1f}"), *mid, ("Floor", f"{float(p['p10']):.1f}"), ("Ceiling", f"{float(p['p90']):.1f}")]
        assert d["proj_points"] == pytest.approx(float(p["proj_points"]))
    else:
        assert not m and blocks(d["sections"]["projection"], "unavailable")
    av = sql("""select rostered_by_roster_id, rostered_by_team, is_free_agent from analytics.mart_player_availability
                where league_id = %s and gsis_id = %s""", (league, gsis))
    if av and av[0]["rostered_by_roster_id"] is not None:
        assert d["rostered_by_roster_id"] == av[0]["rostered_by_roster_id"]
        assert f"on **{av[0]['rostered_by_team']}**" in d["header"]
        # a starter's lineup sentence carries the mart's value and margin
        st = sql("""select slot, player_value, lineup_margin from analytics.mart_lineup_recommendation
                    where league_id = %s and season = %s and week = %s and roster_id = %s and gsis_id = %s""",
                 (league, d["season"], d["week"], av[0]["rostered_by_roster_id"], gsis))
        if st and st[0]["lineup_margin"] is not None and float(st[0]["lineup_margin"]) < float(st[0]["player_value"]):
            line = " ".join(b["text"] for b in blocks(d["sections"]["value"], "markdown"))
            assert f"{float(st[0]['player_value']):.2f}" in line and f"**{float(st[0]['lineup_margin']):.2f}**" in line
    elif av and av[0]["is_free_agent"]:
        assert d["is_free_agent"] and "**free agent** in this league" in d["header"]


def test_kicker_card(client):
    d = client.get(f"/api/player/00-0035358?league={SCRUBS}&team=2").json()
    assert d["position"] == "K"
    usage = d["sections"]["usage"]
    assert usage["title"] == "**Usage** — his kicks this season"
    assert blocks(d["sections"]["signals"], "unavailable")[0]["text"].startswith("unavailable: role alerts cover")


def test_unknown_player(client):
    r = client.get(f"/api/player/00-9999999?league={DYNASTY}")
    assert r.status_code == 404
    assert client.get("/api/player/00-0036963?league=nope").status_code == 404


def test_search(client, sql):
    hits = client.get(f"/api/search?league={DYNASTY}&q=st brown").json()
    assert hits and hits[0]["gsis_id"] == "00-0036963" and hits[0]["label"].startswith("Amon-Ra St. Brown · WR · DET · ")
    assert client.get(f"/api/search?league={DYNASTY}&q=a").json() == []
    assert len(client.get(f"/api/search?league={SCRUBS}&q=son").json()) <= 25
    assert client.get("/api/search?league=nope&q=allen").status_code == 404
