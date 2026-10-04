"""/api/leagues, /api/leagues/{id}/rosters and /api/my-week against the marts, read with independent SQL.

The acceptance pair: dynasty roster 12 and Scrubs roster 2, the current week (4 on 2026-10-01)."""

from __future__ import annotations

import pytest
from league_lab import clock  # ---- INF-1: "now" is the suite's pinned moment, never the database's now()

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db

pytestmark = needs_db

SLOT_WORDS = {"SUPER_FLEX": "Superflex", "REC_FLEX": "WR/TE flex", "WRRB_FLEX": "RB/WR flex"}


def label(slot: str) -> str:
    for k, w in SLOT_WORDS.items():
        if slot.startswith(k):
            return w + slot[len(k):]
    return slot


def current_week(sql, season: int) -> int | None:
    rows = sql("""select min(week) as week from (
                      select week, max(kickoff_at) as last_kick from analytics.dim_game
                      where season = %s and season_type = 'REG' group by week) w
                  where last_kick > %s""", (season, clock.now()))
    return rows[0]["week"]


def mart(sql, league: str, season: int, week: int, team: int) -> list[dict]:
    return sql("""select r.slot, r.slot_order, r.gsis_id, r.player_name, r.player_value, r.lineup_margin, r.is_weakest_slot,
                         r.lineup_value, r.is_empty_slot, r.value_source, r.position,
                         coalesce(g.kickoff_at <= %s, false) or r.is_locked as locked
                  from analytics.mart_lineup_recommendation r
                  left join analytics.mart_player_week_projections p
                         on p.league_id = r.league_id and p.season = r.season and p.week = r.week and p.gsis_id = r.gsis_id
                  left join analytics.dim_player dp on dp.gsis_id = r.gsis_id
                  left join lateral (select min(kickoff_at) as kickoff_at from analytics.dim_game g
                                     where g.season = r.season and g.week = r.week and g.season_type = 'REG'
                                       and coalesce(p.team, dp.latest_team) in (g.home_team, g.away_team)) g on true
                  where r.league_id = %s and r.season = %s and r.week = %s and r.roster_id = %s order by r.slot_order""",
               (clock.now(), league, season, week, team))


def test_leagues_and_rosters(client, sql):
    leagues = client.get("/api/leagues").json()
    assert [x["league_id"] for x in leagues] == [SCRUBS, DYNASTY]           # reference league first, like the app
    for lg in leagues:
        rosters = client.get(f"/api/leagues/{lg['league_id']}/rosters").json()
        n = sql("select count(*) as n from analytics.dim_league_member where league_id = %s", (lg["league_id"],))[0]["n"]
        assert len(rosters) == n == (12 if lg["league_id"] == DYNASTY else 10)
        assert ANDREW[lg["league_id"]] in {r["roster_id"] for r in rosters}
    assert client.get("/api/leagues/123/rosters").status_code == 404


@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_my_week_matches_the_lineup_mart(client, sql, league):
    team = ANDREW[league]
    r = client.get(f"/api/my-week?league={league}&team={team}")
    assert r.status_code == 200
    d = r.json()
    season = d["season"]
    week = current_week(sql, season)
    assert d["week"] == week
    rows = mart(sql, league, season, week, team)
    assert rows, "no proposed lineup in the mart"
    # the four-column table = the mart's starters, slot by slot
    assert [(x["slot"], x["gsis_id"], x["value"], x["margin"]) for x in d["lineup"]] == [
        (label(m["slot"]), m["gsis_id"], float(m["player_value"]) if m["player_value"] is not None else None,
         float(m["lineup_margin"]) if m["lineup_margin"] is not None else None) for m in rows]
    lv = float(rows[0]["lineup_value"])
    assert d["lineup_value"] == pytest.approx(lv)
    assert f"**{lv:.2f}**" in d["league_line"]
    # the full list adds the bench and the players who cannot play, from ops.lineups (same run)
    bench = sql("""select count(*) as n from ops.lineups where league_id = %s and season = %s and week = %s and roster_id = %s
                     and not is_realised and role in ('bench', 'unplayable')""", (league, season, week, team))[0]["n"]
    assert len(d["lineup_full"]) == len(rows) + bench


@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_cards_are_the_closest_replaceable_calls(client, sql, league):
    """By hand: the cards are the (up to) three unlocked, valued starters with the smallest margins among those
    somebody on the bench can replace (margin < his value: a margin equal to his whole value means nobody can),
    smallest first; each card's numbers are the mart's and its alternative's value is the value minus the margin."""
    team = ANDREW[league]
    d = client.get(f"/api/my-week?league={league}&team={team}").json()
    rows = mart(sql, league, d["season"], d["week"], team)
    cand = [m for m in rows if not m["is_empty_slot"] and m["lineup_margin"] is not None and not m["locked"]
            and m["value_source"] != "unvalued" and float(m["lineup_margin"]) < float(m["player_value"]) - 0.011]
    cand.sort(key=lambda m: (float(m["lineup_margin"]), not m["is_weakest_slot"], float(m["player_value"]), m["slot_order"]))
    assert [c["slot"] for c in d["cards"]] == [m["slot"] for m in cand[:3]]
    by_slot = {m["slot"]: m for m in rows}
    for c in d["cards"]:
        m = by_slot[c["slot"]]
        assert c["value"] == pytest.approx(float(m["player_value"]))
        assert c["margin"] == pytest.approx(float(m["lineup_margin"]))
        assert c["alt_value"] == pytest.approx(c["value"] - c["margin"], abs=0.011)
        alt = sql("""select value from ops.lineups where league_id = %s and season = %s and week = %s and roster_id = %s
                       and not is_realised and role = 'bench' and gsis_id = %s""",
                  (league, d["season"], d["week"], team, c["alt_gsis_id"]))
        assert alt and float(alt[0]["value"]) == pytest.approx(c["alt_value"])
        text = " ".join(b["text"] for b in c["blocks"])
        assert f"{c['value']:.2f} vs {c['alt_value']:.2f}" in text
        # D6: with a win probability the headline is "outscores … x% of the time" and the margin is the second
        # line ("0.45 apart."); without one (K / DEF / PPG-valued) the margin carries the verdict
        assert f"{c['margin']:.2f} apart" in text
        assert ("outscores" in text) or (f"**{c['margin']:.2f} apart, {c['verdict']}**" in text)
        assert f"[{c['player_name']}](/player/{c['gsis_id']})" in text      # one-tap link to the card, in the app
    weakest = [m for m in rows if m["is_weakest_slot"]]
    if weakest and not weakest[0]["locked"] and d["cards"]:
        assert d["cards"][0]["slot"] == weakest[0]["slot"]


def test_worked_example_dynasty_12(client):
    """The card as it reads on 2026-10-01 (week 4) — the numbers checked by hand against the mart above:
    RB2 Gainwell 7.54, margin 0.45, Emanuel Wilson 7.09 on the bench."""
    d = client.get(f"/api/my-week?league={DYNASTY}&team=12").json()
    if d["week"] != 4:
        pytest.skip("the worked example is week 4's board")
    # the board moves with every refit (v3 flipped this pair's order on the PO's database), so the pin is the
    # shape, not the names: the first card is the weakest slot with its named alternative and a verdict
    c = d["cards"][0]
    assert c["slot"] and c["player_name"] and c["alt_name"] and c["verdict"]
    assert c["value"] >= c["alt_value"] and c["margin"] == pytest.approx(round(c["value"] - c["alt_value"], 2), abs=0.011)
    assert d["league_line"].startswith("Your best lineup projects **")


def test_unknown_team_and_league(client, monkeypatch):
    # plan E3: a league the database does not have is looked up on Sleeper (fixtures here: no network); Sleeper
    # has no league "1", so it is still a 404
    from pathlib import Path
    monkeypatch.setenv("LEAGUE_LAB_SLEEPER_FIXTURES", str(Path(__file__).with_name("fixtures") / "sleeper"))
    assert client.get(f"/api/my-week?league={DYNASTY}&team=99").status_code == 404
    assert client.get("/api/my-week?league=1&team=2").status_code == 404
    assert client.get(f"/api/my-week?league={DYNASTY}").status_code == 422
