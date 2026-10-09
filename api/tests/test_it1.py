"""Wave I-T, IT-1 — one basis on every trade screen.

The Trade Finder's rows (`/api/trades/partners`) are the calculator's answer for their package: three rows on each of
two leagues (League of Scrubs from its marts, the Test League on demand from the Sleeper fixtures) are opened in the
calculator (`POST /api/trades/evaluate`, the route with IR-4's caveats and the PO's starter rule) and compared field by
field — the dial, the gains, the strip, the verdict, the alternative, the recommendation. Meaning and consistency,
never today's numbers."""

from __future__ import annotations

import pytest

from league_lab_api import decisions

from .conftest import SCRUBS, needs_db

TEST_LEAGUE = "9000000000000000001"
CASES = [(SCRUBS, 2), (TEST_LEAGUE, 3)]


@pytest.fixture(autouse=True)
def _fresh():
    decisions.clear_memo()
    yield
    decisions.clear_memo()


def _compare(row: dict, ev: dict) -> None:
    rd, d = row["decision"], ev["decision"]
    assert rd["basis"] == d["basis"] == "replacement"
    assert rd["dial"] == d["dial"], (rd["dial"], d["dial"])
    assert row["interest"] == d["dial"]
    for k in ("mine", "theirs"):
        for f in ("gain_week", "gain_window", "by_week"):
            assert rd[k][f] == d[k][f], (k, f)
    assert row["you_gain_horizon"] == d["mine"]["gain_window"] and row["they_gain_horizon"] == d["theirs"]["gain_window"]
    assert row["strip"] == d["strip"]
    assert rd["verdict"] == d["verdict"]
    assert rd["alternative"]["words"] == d["alternative"]["words"] == row["alternative_words"]
    assert rd["alternative"]["beats"] == d["alternative"]["beats"] == row["beats_alternative"]
    assert rd["alternative"]["beyond"]["mine"] == d["alternative"]["beyond"]["mine"]
    rr, er = rd["recommendation"], d["recommendation"]
    assert (rr["key"], rr["credible"], rr["label"]) == (er["key"], er["credible"], er["label"])
    assert row["card"]["credible"] == er["credible"]
    assert (row.get("tier") == "credible") == er["credible"]
    assert rd.get("caveat") == d.get("caveat")
    alt_t = row["card"]["waiver_alternative"]["theirs"]
    if alt_t.get("kind") != decisions.IL4_NOT_COMPARED:
        assert rr["words"] == er["words"]                  # the same sentence, word for word
    else:                                                  # IL-4: their move was not needed to answer; said so
        assert alt_t["words"].startswith("their own best waiver move was not compared")
        assert not er["credible"]


@needs_db
@pytest.mark.parametrize("league,team", CASES, ids=["scrubs", "test-league"])
def test_three_finder_rows_are_the_calculators_answer(client, league, team):
    p = client.get("/api/trades/partners", params={"league": league, "team": team})
    assert p.status_code == 200, p.text
    rows = p.json()["partners"]
    assert len(rows) >= 3
    for row in rows[:3]:
        body = {"league": league, "team": team, "partner": row["partner"],
                "give": [x["sleeper_id"] for x in row["give"]], "get": [x["sleeper_id"] for x in row["get"]]}
        ev = client.post("/api/trades/evaluate", json=body)
        assert ev.status_code == 200, ev.text
        print(league, row["partner"], body["give"], body["get"], row["interest"]["label"], row["you_gain_horizon"],
              row["decision"]["recommendation"]["label"])
        _compare(row, ev.json())


@needs_db
@pytest.mark.parametrize("league,team", CASES, ids=["scrubs", "test-league"])
def test_the_finder_orders_and_tiers_on_the_decision(client, league, team):
    rows = client.get("/api/trades/partners", params={"league": league, "team": team}).json()["partners"]
    keys = [(not r["beats_alternative"], -r["beyond_alternative"]) for r in rows if not r.get("optional")]
    assert keys == sorted(keys)                            # beats first, then by the gain beyond the waiver move
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    for r in rows:
        assert r["demoted"] == (not r["beats_alternative"])
        assert r["interest"]["label"] == decisions.effect_label(r["they_gain_horizon"])
        assert r["interest"]["caption"].endswith("against realistic replacements")
        if r.get("tier") == "credible":
            assert r["decision"]["recommendation"]["credible"]


@needs_db
def test_a_finder_row_player_who_sits_carries_the_league_screens_note(client, monkeypatch):
    """Item 5: each row's players carry `league_gate.note` (the reason, its source and date; `sits`) — the cell My Week
    and the Team Hub draw. The status itself is the gate's (a block handed in here), never a code tested in this path."""
    rows = client.get("/api/trades/partners", params={"league": SCRUBS, "team": 2}).json()["partners"]
    p0 = rows[0]["get"][0]
    assert "availability" in p0                              # every row player: a note or None (no word)
    blk = {"why": "IR (knee) · Sleeper, Oct 2", "status": "IR", "cannot_play": True, "unlikely": False,
           "out_indefinitely": True, "week_words": "on injured reserve", "ros_words": "on injured reserve: no return date"}
    monkeypatch.setattr(decisions.LG, "blocks", lambda ids, *a, **k: {g: blk for g in ids if g == p0["gsis_id"]})
    decisions.clear_memo()
    rows = client.get("/api/trades/partners", params={"league": SCRUBS, "team": 2}).json()["partners"]
    hit = [x for r in rows for x in (*r["give"], *r["get"]) if x["gsis_id"] == p0["gsis_id"]]
    assert hit and all(x["availability"]["sits"] and x["availability"]["why"] == blk["why"] for x in hit)
    others = [x for r in rows for x in (*r["give"], *r["get"]) if x["gsis_id"] != p0["gsis_id"]]
    assert all(x["availability"] is None for x in others)
