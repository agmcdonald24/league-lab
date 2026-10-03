"""Wave I-B (IB-3): matchup meaning first, "Value to my lineup", the card's default content.

* The tone per cell (docs/METRICS.md § Matchups): a defense-vs-position cell is favorable when it is one of the 10 (of
  32) that give up the most to the position, difficult when one of the 10 that give up the fewest, neutral between —
  the card's reason-line rule; a cornerback call's tone is the named corner's quarter (shutdown = difficult, target =
  favorable), on an unclear call only when every named corner is ranked and they agree, none when no corner is ranked.
* One rank direction: on /api/matchups/defense `tough_rank` 1 = the defense that gives up the fewest points to the
  position, on /api/matchups/cb `cover_rank` 1 = the corner hardest to throw on — both "1 = toughest for the offense",
  and a difficult tone always sits at the small-rank end on both routes.
* Value to my lineup (/api/ros?view=lineup&team=): for the fixture rosters a backup QB behind a healthy starter (a
  one-QB league) ranks below every starter; one of yours is worth what your lineup loses without him (a free agent
  filling the slot when that beats the bench); anyone else what he adds; the sentence says it; IA-3's pieces and the
  market line ride on every row.
* The card's status (IB-0 sends it from the API; the web derives it until then): the saved fixtures carry the three
  statuses and the web's rule (week.ts) matches the card's own coin-flip rule.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from league_lab_api import ondemand, research

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db

TEST_LEAGUE = "9000000000000000001"
ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "web" / "fixtures"


# ------------------------------------------------------------------------------------------------ pure: the tone
@pytest.mark.parametrize("rank,tone", [(1, "favorable"), (10, "favorable"), (11, "neutral"), (22, "neutral"),
                                       (23, "difficult"), (32, "difficult"), (None, None)])
def test_defense_tone_thresholds_follow_the_card_sentence(rank, tone):
    assert research.defense_tone(rank, 32) == tone
    if rank is not None:
        assert research.tough_rank(rank, 32) == 33 - rank


def test_defense_tone_scales_with_the_defenses_ranked():
    assert research.tone_edge(32) == 10 and research.tone_edge(28) == 9 and research.tone_edge(2) == 1
    assert research.defense_tone(9, 28) == "favorable" and research.defense_tone(10, 28) == "neutral"
    assert research.defense_tone(20, 28) == "difficult"


def test_rank_words_take_the_nearer_end():
    assert research.gives_up_words(1, 32) == "gives up the most"
    assert research.gives_up_words(2, 32) == "gives up the 2nd-most"
    assert research.gives_up_words(30, 32) == "gives up the 3rd-fewest"
    assert research.gives_up_words(32, 32) == "gives up the fewest"
    assert research.corner_words(17, 74) == "the 17th-hardest of 74 starting corners to throw on"
    assert research.corner_words(66, 74) == "the 9th-easiest of 74 starting corners to throw on"
    assert research.corner_words(None, 74) is None


def _cb(**kw):
    base = {"call_status": "called", "call_strength": "clear", "likely_cover_name": "DJ Turner II", "likely_cover_slot": "RCB",
            "cover_rank": 18, "cover_label": "shutdown", "cb_n_ranked": 74, "side_share": 0.469, "other_side_share": 0.292,
            "other_cover_name": None, "other_cover_slot": None, "games_vs_opp": 0, "games_vs_cover": 0, "lcb_rank": 34,
            "lcb_label": "solid", "rcb_rank": 18, "rcb_label": "shutdown"}
    return base | kw


def test_cornerback_tone_and_certainty_never_say_more_than_the_call():
    clear = research.cb_meaning(_cb())
    assert clear["certainty"] == "likely" and clear["tone"] == "difficult"
    assert clear["certainty_words"].startswith("likely: 47% of his targets go to that side")
    assert clear["named_corners"][0]["words"] == "the 18th-hardest of 74 starting corners to throw on"
    # an even split names both outside corners; their tones differ -> neutral, never the stronger one
    even = research.cb_meaning(_cb(call_strength="even", other_cover_name="Dax Hill", other_cover_slot="LCB"))
    assert even["certainty"] == "unclear" and even["tone"] == "neutral" and len(even["named_corners"]) == 2
    # both shutdown corners -> difficult even on an unclear call
    both = research.cb_meaning(_cb(call_strength="even", other_cover_name="Dax Hill", other_cover_slot="LCB", lcb_rank=3,
                                   lcb_label="shutdown"))
    assert both["tone"] == "difficult"
    # one unranked corner on an unclear call -> neutral; nobody ranked -> no read
    assert research.cb_meaning(_cb(call_strength="even", other_cover_name="X", other_cover_slot="LCB", lcb_rank=None,
                                   lcb_label=None))["tone"] == "neutral"
    assert research.cb_meaning(_cb(cover_rank=None, cover_label=None))["tone"] is None
    te = research.cb_meaning(_cb(call_status="tight end", call_strength=None))
    assert te["certainty"] == "no call" and te["tone"] is None and te["named_corners"] == []


# ------------------------------------------------------------------------------------------------ the routes
@needs_db
@pytest.mark.parametrize("league", [SCRUBS, DYNASTY])
def test_defense_route_tone_and_one_direction(client, league):
    d = client.get(f"/api/matchups/defense?league={league}&team={ANDREW[league]}").json()
    assert "#1 = the toughest for the offense" in d["rank_note"]
    df = pd.DataFrame(d["teams"])
    for pos, g in df[df["rank_std"].notna()].groupby("position"):
        n = len(g)
        assert (g["n_ranked"] == n).all()
        assert sorted(g["tough_rank"].astype(int)) == sorted(n + 1 - g["rank_std"].astype(int))
        t1 = g[g["tough_rank"] == g["tough_rank"].min()]
        assert t1["points_allowed_per_game_std"].min() == pytest.approx(g["points_allowed_per_game_std"].min()), pos
        e = research.tone_edge(n)
        assert (g.loc[g["tough_rank"] <= e, "tone"] == "difficult").all()
        assert (g.loc[g["tough_rank"] > n - e, "tone"] == "favorable").all()
        assert set(g["tone"]) <= set(research.TONES)
        assert g["rank_words"].str.match(r"^gives up the (most|fewest|\d+(st|nd|rd|th)-(most|fewest)) points to ").all()


@needs_db
@pytest.mark.parametrize("league", [SCRUBS, DYNASTY])
def test_cornerback_route_same_direction_and_a_label_beside_every_call(client, league):
    c = client.get(f"/api/matchups/cb?league={league}&team={ANDREW[league]}").json()
    assert c["rank_note"] == research.RANK_NOTE
    rows = c["matchups"]
    assert rows
    for m in rows:
        assert m["certainty"] in ("likely", "unclear", "no call")
        assert m["certainty_words"].startswith(m["certainty"])
        if m["call_status"] == "called":
            assert m["certainty"] == ("likely" if m["call_strength"] == "clear" else "unclear")
        if m["tone"] == "difficult" and m["certainty"] == "likely":
            assert m["cover_rank"] <= m["cb_n_ranked"] / 4 + 1      # 1 = hardest: difficult sits at the small ranks
        if m["tone"] == "favorable" and m["certainty"] == "likely":
            assert m["cover_rank"] > m["cb_n_ranked"] * 3 / 4 - 1
        assert "shutdown" not in json.dumps(m["named_corners"]).replace('"label": "shutdown"', "")  # the label stays data


# ------------------------------------------------------------------------------------------------ value to my lineup
def _lineup(league, team, **kw):
    return ondemand.ros(league, kw.pop("position", "ALL"), kw.pop("limit", 500), view="lineup", team=team, **kw)


@needs_db
@pytest.mark.parametrize("league,team", [(SCRUBS, 2), (TEST_LEAGUE, 3)])
def test_a_backup_qb_ranks_below_every_starter(league, team):
    d = _lineup(league, team, who="mine")
    rows = d["players"]
    assert d["view"] == "lineup" and d["window"]["weeks"] >= 10
    assert [r["lineup_rank"] for r in rows] == sorted(r["lineup_rank"] for r in rows)
    qbs = [r for r in rows if r["position"] == "QB"]
    starter = max(qbs, key=lambda r: r["lineup_weeks"])
    backups = [r for r in qbs if r["lineup_weeks"] <= 2 and r is not starter]
    assert backups, "the fixture roster carries a backup QB"
    starters = [r for r in rows if r["lineup_weeks"] >= d["window"]["weeks"] - 2]
    for b in backups:
        assert b["lineup_points"] < 0.05 or b["lineup_weeks"] <= 2
        assert all(b["lineup_rank"] > s["lineup_rank"] for s in starters), (b["player_name"], b["lineup_why"])
        assert re.search(r"QB2 only plays in week|backup QB", b["lineup_why"])
    # IA-3's pieces and the market line ride on the rows
    assert all("market_points" in r and "per_game" in r for r in rows)


@needs_db
def test_value_is_what_the_lineup_loses_or_gains():
    d = _lineup(DYNASTY, 12, who="all", limit=60)
    rows = d["players"]
    kinds = {r["lineup_kind"] for r in rows}
    assert kinds <= {"mine", "fa", "others"} and "others" in kinds
    vals = [r["lineup_points"] for r in rows]
    assert vals == sorted(vals, reverse=True)
    for r in rows:
        assert r["lineup_points"] >= 0 and 0 <= r["lineup_weeks"] <= d["window"]["weeks"]
        if r["lineup_kind"] == "others":
            assert r["lineup_why"].startswith(f"On {r['rostered_by_team']}")
        if r["lineup_kind"] == "fa":
            assert r["lineup_why"].startswith("Free agent")
    # a superflex league never calls a bench QB "QB2"
    mine = _lineup(DYNASTY, 12, who="mine")["players"]
    assert not any("QB2" in (r["lineup_why"] or "") for r in mine)


def test_lineup_view_needs_a_team(client):
    r = client.get(f"/api/ros?league={SCRUBS}&view=lineup")
    assert r.status_code == 400 and "team" in r.json()["error"]
    assert client.get(f"/api/ros?league={SCRUBS}&view=nope&team=2").status_code == 400


# ------------------------------------------------------------------------------------------------ the card's status
def test_the_saved_cards_carry_the_three_statuses_and_the_rule_matches_the_card():
    from league_lab_api.applib import cards
    seen = set()
    for f in sorted(FIX.glob("my-week_*.json")):
        d = json.loads(f.read_text())
        for c in d["cards"]:
            if "status" in c:
                seen.add(c["status"])
                assert (c["status"] == "close") == cards.is_coin_flip(c)
                assert c["strength"] in ("clear", "lean", "coin flip")
    assert seen == {"change", "set", "close"}
    ts = (ROOT / "web" / "src" / "lib" / "week.ts").read_text()
    assert f"const CLOSE_PWIN = {cards.CLOSE_PWIN};" in ts and f"const COIN_FLIP = {cards.COIN_FLIP};" in ts
