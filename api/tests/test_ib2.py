"""Wave I-B (IB-2): Waivers short — GET /api/waivers' `top3` (the three strongest moves: the move, the lineup gain, ONE
reason, the claim's cost), the views (Help now · Bye coverage · Stashes · All available, all in one answer) and, on
every move whose drop starts this week or next, `drop_starts` + `keep_alternative` (the best claim at the same position
that keeps him; the line that none does otherwise) — present exactly when the drop starts, absent otherwise. The house
leagues read their marts (the starters checked independently against `mart_league_roster_horizon`); the fictional Test
League is on demand (Sleeper fixtures); the overlay case forces two FLEX players Out so Croskey-Merritt starts this
week. Sleeper and ESPN are never called."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest
from league_lab import anyleague as A

from league_lab_api import availability, decisions

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db

TEST_LEAGUE = "9000000000000000001"
JEFFERSON, WILSON, CROSKEY = "00-0036322", "00-0038559", "00-0040242"
CROSKEY_SID = "12533"


@pytest.fixture(autouse=True)
def _fresh():
    A.clear_league_weeks()
    decisions.clear_memo()
    yield
    A.clear_league_weeks()
    decisions.clear_memo()


def _all_moves(w: dict) -> list[dict]:
    """Every move object the answer carries: the top three, both views, the paged list, Wave G's cards."""
    return ([c["move"] for c in w["top3"]] + [c["move"] for c in w["views"]["help"]["moves"]]
            + [c["move"] for c in w["views"]["bye"]["moves"]] + list(w["moves"]) + [c["move"] for c in w["cards"]])


# ------------------------------------------------------------------------------ the pieces (no database)
def _mv(rows: list[tuple]) -> pd.DataFrame:
    cols = ["add_sleeper_id", "add_gsis_id", "add_name", "add_position", "add_team", "drop_sleeper_id", "drop_gsis_id",
            "drop_name", "drop_position", "list_kind", "weekly_gain", "horizon_gain", "add_rank"]
    return pd.DataFrame(rows, columns=cols)


def test_the_alternative_keeps_the_starter_or_says_none_does(monkeypatch):
    monkeypatch.setattr(decisions, "bio", lambda _ids: {})
    mv = _mv([("a1", None, "Add One", "RB", "NO", "s1", None, "Star Starter", "RB", "start_now", 2.0, 5.0, 1),
              ("a2", None, "Add Two", "RB", "NO", "b1", None, "Bench Guy", "RB", "cover", 0.0, 3.4, 2),
              ("a3", None, "Add Three", "WR", "NO", "b1", None, "Bench Guy", "RB", "cover", 0.0, 9.0, 3)])
    soon = {"s1": {"weeks": [4], "slot": "RB1"}}
    move = {"add": {"sleeper_id": "a1", "position": "RB", "player_name": "Add One"},
            "drop": {"sleeper_id": "s1", "player_name": "Star Starter"}}
    st = decisions._drop_starts(move, soon, 4)
    assert st == {"weeks": [4], "slot": "RB1", "text": "Star Starter starts for you this week"}
    alt = decisions._alternative(move, mv, soon, set(), 4, 7)
    # the same position only (the WR's bigger gain is another slot), the drop who sits
    assert alt["move"]["add"]["player_name"] == "Add Two" and alt["move"]["drop"]["player_name"] == "Bench Guy"
    assert alt["line"] == "Or: add Add Two for a +3.4 gain over weeks 4–7 and keep Starter (drop Guy, who sits)."
    # a claim that drops nobody who starts: no line
    assert decisions._drop_starts({**move, "drop": {"sleeper_id": "b1", "player_name": "Bench Guy"}}, soon, 4) is None
    # nobody else at the position: the line says so (never a starter's drop without a line)
    none = decisions._alternative(move, mv[mv["add_sleeper_id"] != "a2"], soon, set(), 4, 7)
    assert none["move"] is None and none["line"].startswith("No free agent at RB helps without dropping a starter")
    # a free agent who cannot play is no alternative
    blocked = decisions._alternative(move, mv.assign(add_gsis_id=["g1", "g2", "g3"]), soon, {"g2"}, 4, 7)
    assert blocked["move"] is None


def test_one_reason_is_one_fact():
    # IE-0 (Wave I-E): the bye words are the candidate's own — he fills the empty DEF only as a defense (the slot's type
    # admits him); a candidate of another position never borrows the team's need (the review's "team QB fills the DEF")
    week, byes, empty = 4, {5: ["Kansas City Chiefs", "Travis Kelce"], ("fit", 5): ["Kansas City Chiefs"],
                            ("pos", 5): {"Kansas City Chiefs": "DEF", "Travis Kelce": "TE"},
                            ("empty_types", 5): {"DEF": "DEF"}}, {5: ["DEF"]}
    now = {"add": {"gsis_id": "x"}, "weekly_gain": 1.7, "add_slot": "FLEX2", "week_gains": [1.7, 0, 0, 0],
           "displaced": {"player_name": "Bhayshul Tuten", "projection": 9.72}}
    assert decisions._reason(now, week, byes, empty, {}) == "Starts at FLEX2 this week over Tuten (9.7)."
    bye = {"add": {"gsis_id": "y", "position": "DEF"}, "weekly_gain": 0.0, "add_slot": None, "week_gains": [0, 8.3, 0, 0]}
    assert decisions._reason(bye, week, byes, empty, {}) == "Fills your empty DEF in week 5, when Kansas City Chiefs is on a bye."
    # a gain in a bye week where nobody he could stand in for is away: not the bye's doing
    assert decisions._reason({**bye, "add": {"gsis_id": "y", "position": "QB"}}, week, {5: ["Travis Kelce"], ("fit", 5): [],
                                                                                            ("pos", 5): {"Travis Kelce": "TE"}},
                             {}, {}) == "Would not start for you this week; helps in week 5."
    # IE-0: the same week with the DEF empty — a QB still gets no DEF words
    assert decisions._reason({**bye, "add": {"gsis_id": "y", "position": "QB"}}, week, byes, empty, {}) == (
        "Would not start for you this week; helps in week 5.")
    stash = {"y": {"change_text": "snap share 41% → 78%", "since_week": 3}}
    assert decisions._reason(bye, week, byes, empty, stash) == "His role grew: snap share 41% → 78% since week 3."
    for r in (decisions._reason(now, week, byes, empty, {}), decisions._reason(bye, week, byes, empty, {})):
        assert r.count(". ") == 0 and r.endswith(".")
    assert decisions._cost({"drop": None}, 4, 7, None) == "No drop: you have an open roster spot."
    # IF-1 (Wave I-F): "he sits anyway" is never the whole reason — without the drop's cost the words say what is known
    assert decisions._cost({"drop": {"player_name": "A B", "horizon_loss": 0.0}}, 4, 7, None) == \
        "Drop A B: he does not start for you over weeks 4–7."
    assert decisions._cost({"drop": {"player_name": "A B"}}, 4, 7, {"weeks": [4, 5]}) == "Drop A B: he starts for you this week and next."


# ------------------------------------------------------------------------------ the house leagues (the marts)
@needs_db
def test_top3_the_views_and_the_alternative_scrubs(client, sql):
    w = client.get("/api/waivers", params={"league": SCRUBS, "team": ANDREW[SCRUBS]}).json()
    wk, last = w["week"], w["horizon_last_week"]
    top = w["top3"]
    assert len(top) == 3
    assert len({c["move"]["add"]["position"] for c in top}) == 3                     # one claim per position
    # I-E (PO): the three lead with this week's gain and are ordered by it (the window total second); the set is still
    # the three biggest window gains, one per position
    assert [c["this_week"] for c in top] == sorted((c["this_week"] for c in top), reverse=True)
    for c in top:
        assert c["gain"] == c["move"]["horizon_gain"] and c["gain_label"] == f"weeks {wk}–{last}"
        assert c["reason"] and c["reason"].endswith(".") and c["reason"].count(". ") == 0   # one fact, one sentence
        assert c["cost"].startswith(("Drop ", "No drop"))
    # the strongest is the biggest gain among the best-drop claims (mart_waiver_moves, independently)
    best = sql("""select max(horizon_gain) as g from analytics.mart_waiver_moves where league_id = %s and roster_id = %s
                  and is_best_drop and list_kind <> 'nothing'""", (SCRUBS, ANDREW[SCRUBS]))[0]["g"]
    assert max(c["gain"] for c in top) == pytest.approx(best, abs=0.01)
    # the views: one answer carries them all
    v = w["views"]
    assert set(v) == {"help", "bye", "stash", "all"} and w["default_view"] == "help"
    assert [x["label"] for x in v.values()] == ["Help now", "Bye coverage", "Stashes", "All available"]
    hg = [c["this_week"] for c in v["help"]["moves"]]
    assert hg and all(g >= 0.05 for g in hg) and hg == sorted(hg, reverse=True)
    assert v["bye"]["week"] == 5 and v["bye"]["empty_slots"] == ["DEF"] and "Kansas City Chiefs" in v["bye"]["on_bye"]
    assert v["bye"]["line"].startswith("Week 5: Kansas City Chiefs")
    bg = [c["week_gain"] for c in v["bye"]["moves"]]
    assert bg and all(g >= 0.05 for g in bg) and bg == sorted(bg, reverse=True)
    assert all(c["move"]["add"]["position"] == "DEF" for c in v["bye"]["moves"])
    assert v["stash"]["count"] == len(w["upside"]["stashes"]) and v["all"]["count"] == len(w["free_agents"])
    # the alternative: present exactly when the drop starts this week or next (the horizon's lineup, read here)
    starts = {r["sleeper_player_id"] for r in sql(
        """select sleeper_player_id from analytics.mart_league_roster_horizon where league_id = %s and roster_id = %s
           and week in (%s, %s) and role = 'starter'""", (SCRUBS, ANDREW[SCRUBS], wk, wk + 1))}
    moves = _all_moves(w)
    n_starts = 0
    for m in moves:
        d = m["drop"]
        if d is not None and d["sleeper_id"] in starts:
            n_starts += 1
            assert m["drop_starts"] and m["drop_starts"]["text"].startswith(f"{d['player_name']} starts for you")
            alt = m["keep_alternative"]
            assert alt and alt["line"]
            if alt["move"] is not None:
                assert alt["move"]["add"]["position"] == m["add"]["position"]
                assert alt["move"]["drop"] is None or alt["move"]["drop"]["sleeper_id"] not in starts
                assert alt["move"]["horizon_gain"] >= 0.05
        else:
            assert m.get("drop_starts") is None and m.get("keep_alternative") is None
    assert n_starts >= 2                                         # the Giants for the Chiefs, Carlson for McLaughlin
    giants = next(c for c in top if c["move"]["drop"] and c["move"]["drop"]["player_name"] == "Kansas City Chiefs")
    # IF-1 (Wave I-F): the drop the claim replaces at his slot is named as such, with the alternative drop and why
    assert giants["cost"].startswith("Drop Chiefs defense: Giants defense replaces him at DEF.")
    assert "keep Kansas City Chiefs" in giants["move"]["keep_alternative"]["line"]


@needs_db
def test_nothing_to_claim_dynasty(client):
    w = client.get("/api/waivers", params={"league": DYNASTY, "team": ANDREW[DYNASTY]}).json()
    assert w["top3"] == [] and w["views"]["help"]["moves"] == [] and w["views"]["bye"]["moves"] == []
    assert w["views"]["help"]["line"] == w["notice"] and w["notice"].startswith("**Nothing beats what you have.**")
    assert w["views"]["all"]["count"] == len(w["free_agents"]) > 0


@needs_db
def test_the_views_on_every_scrubs_roster_hold_the_rules(client):
    """The rules on every roster of the house league: one claim a position in the top three, each listed claim's drop
    either sits both weeks or carries the alternative."""
    for team in range(1, 11):
        w = client.get("/api/waivers", params={"league": SCRUBS, "team": team}).json()
        assert len(w["top3"]) <= 3 and len({c["move"]["add"]["position"] for c in w["top3"]}) == len(w["top3"])
        for m in _all_moves(w):
            assert (m.get("drop_starts") is None) == (m.get("keep_alternative") is None)


# ------------------------------------------------------------------------------ on demand (the Test League)
def _force_out(monkeypatch, gsis: set[str]) -> None:
    """The overlay on with these players Out, newer than any build (no feed read)."""
    at = datetime.now(UTC)
    out = {g: {"status": "Out", "code": "OUT", "cannot_play": True, "flagged": False, "source": "ESPN", "as_of": at,
               "fetched_at": at, "note": "ankle"} for g in gsis}
    monkeypatch.setattr(availability, "enabled", lambda: True)
    monkeypatch.setattr(availability, "now", lambda gsis_ids=None, sleeper_of=None: {
        g: a for g, a in out.items() if gsis_ids is None or g in {str(x) for x in gsis_ids}})
    decisions.clear_memo()


@needs_db
def test_on_demand_test_league(client, monkeypatch):
    """Roster 9 on demand: its claims all drop Marvin Harrison Jr., who sits — no line. With every WR / TE who starts
    ahead of him Out, he starts this week: each claim that drops him now says so, with the claim that keeps him."""
    w = client.get("/api/waivers", params={"league": TEST_LEAGUE, "team": 9}).json()
    assert w["source"] == "sleeper" and len(w["top3"]) == 3 and w["views"]["help"]["moves"]
    mhj = [m for m in _all_moves(w) if m["drop"] and m["drop"]["player_name"] == "Marvin Harrison Jr."]
    assert mhj and all(m["drop_starts"] is None and m["keep_alternative"] is None for m in mhj)
    for m in _all_moves(w):
        assert (m.get("drop_starts") is None) == (m.get("keep_alternative") is None)
    wk = client.get("/api/my-week", params={"league": TEST_LEAGUE, "team": 9}).json()
    ahead = {r["gsis_id"] for r in wk["lineup_full"] if r.get("role") == "starter" and r.get("position") in ("WR", "TE")
             and r.get("gsis_id") and r.get("player_name") != "Marvin Harrison Jr."}
    assert ahead
    _force_out(monkeypatch, ahead)
    on = client.get("/api/waivers", params={"league": TEST_LEAGUE, "team": 9}).json()
    mhj_on = [m for m in _all_moves(on) if m["drop"] and m["drop"]["player_name"] == "Marvin Harrison Jr."]
    assert mhj_on
    for m in mhj_on:
        assert m["drop_starts"]["weeks"][0] == on["week"] and m["drop_starts"]["text"] == "Marvin Harrison Jr. starts for you this week" \
            or m["drop_starts"]["text"] == "Marvin Harrison Jr. starts for you this week and next"
        alt = m["keep_alternative"]
        assert alt["line"] and (alt["move"] is None or alt["move"]["drop"] is None
                                or alt["move"]["drop"]["player_name"] != "Marvin Harrison Jr.")
    # roster 3 (the web fixtures' team): nothing beats what it has
    w3 = client.get("/api/waivers", params={"league": TEST_LEAGUE, "team": 3}).json()
    assert w3["top3"] == [] and w3["views"]["help"]["line"]


# ------------------------------------------------------------------------------ the overlay: a starter because of the news
@needs_db
def test_a_player_who_starts_because_of_the_overlay_is_a_starter(client, monkeypatch):
    """Jefferson and Michael Wilson Out (newer than the build): Croskey-Merritt starts at a FLEX this week, so a claim
    that drops him says so and shows the claim that keeps him; with the overlay off he sits and no line shows."""
    off = client.get("/api/waivers", params={"league": SCRUBS, "team": ANDREW[SCRUBS]}).json()
    cm_off = [m for m in _all_moves(off) if m["drop"] and m["drop"]["sleeper_id"] == CROSKEY_SID]
    assert cm_off and all(m["drop_starts"] is None for m in cm_off)
    _force_out(monkeypatch, {JEFFERSON, WILSON})
    on = client.get("/api/waivers", params={"league": SCRUBS, "team": ANDREW[SCRUBS]}).json()
    cm_on = [m for m in _all_moves(on) if m["drop"] and m["drop"]["sleeper_id"] == CROSKEY_SID]
    assert cm_on
    for m in cm_on:
        assert m["drop_starts"]["weeks"][0] == on["week"] and m["drop_starts"]["text"].startswith("Jacory Croskey-Merritt starts")
        assert m["keep_alternative"]["line"]
        alt = m["keep_alternative"]["move"]
        assert alt is None or alt["drop"] is None or alt["drop"]["sleeper_id"] != CROSKEY_SID
