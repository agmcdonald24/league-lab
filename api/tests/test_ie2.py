"""Wave I-E, IE-2: a trade explained through the starting lineup, the metric dictionary, the scoring arithmetic under
"How we calculated this" — the review's own case on dad's league (MyFantasyLeague 70587, `fixtures/mfl/70587/`).

The review's reduced scenario: team 8 "Big Mac Attack" gives Bhayshul Tuten (12490), gets Rashee Rice (10229) from team 12
"Madeyes Revenge". On the fixture Rice starts at WR/TE, McConkey goes to the bench, and Nabers only slides from WR/TE 2 to
WR/TE 3: before IE-2 the lineup detail credited Nabers with +0.23 of the gain (a slot renumbering), now he shows none.
Numbers do not move (brief rule 3): the gains are the evaluation's own, pinned below as they were before the change.
"""

from __future__ import annotations

import re

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import player_ids as PI
from league_lab import trades as T
from league_lab.lineup import Lineup, Player, Slot, Start

from league_lab_api import decisions

from .conftest import needs_db
from .test_i0b import IDS, MFL_FX

KEY = "mfl:70587"
TUTEN, RICE, HOUSTON_QB = "12490", "10229", "mfl:0682"


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


def _eval(client, give, get, window=None) -> dict:
    body = {"league": KEY, "team": 8, "partner": 12, "give": give, "get": get}
    if window:
        body["window"] = window
    r = client.post("/api/trades/evaluate", json=body)
    assert r.status_code == 200, r.text[:400]
    return r.json()


# ------------------------------------------------------------------ the answer's new fields (the review's case)
@needs_db
def test_tuten_for_rice_explained_by_the_starting_lineup(client):
    d = _eval(client, [TUTEN], [RICE])
    # numbers unchanged (the same as before IE-2): +3.36 this week, +9.52 over weeks 4-7; them -2.05 / -2.67
    assert d["fit"]["this_week"] == {"mine": 3.36, "theirs": -2.05}
    assert d["fit"]["window"] == {"mine": 9.52, "theirs": -2.67}
    assert [x["player"]["player_name"] for x in d["starters_in"]] == ["Rashee Rice"]
    assert d["starters_in"][0]["slot"] == "WR/TE" and d["starters_in"][0]["how"] == "trade"
    assert [(x["player"]["player_name"], x["why"]) for x in d["starters_out"]] == [("Ladd McConkey", "to the bench")]
    assert d["cut"] == []
    assert d["lineup_words"] == "Rice starts at WR/TE; McConkey to the bench."
    assert d["effect_words"] == "Your starting lineup: about 3.4 more points this week, about 10 more in total over weeks 4–7."
    assert d["window_words"] == "over weeks 4–7 in total"
    assert d["backup_words"] == "Backup coverage: you lose Tuten, a backup RB (1 RB left on your bench)."
    tc = d["their_change"]
    assert tc["gain_week"] == -2.05 and tc["gain_window"] == -2.67
    assert tc["effect_words"].startswith("Madeyes Revenge's starting lineup: about 2.0 fewer points this week")
    assert tc["lineup_words"] == "Kittle starts at WR/TE; Rice goes to you."
    assert d["hold_words"].startswith("Standing pat keeps your starting lineup at 115.4 projected points this week.")
    assert "The best free agent for the same need" in d["hold_words"] and d["hold"]["waiver_gain"] is not None
    print(f"\n70587 8<->12 Tuten for Rice: {d['effect_words']} {d['lineup_words']} | {d['hold_words']}")


@needs_db
def test_no_gain_from_slot_renumbering_on_the_fixture(client):
    """Nabers slides WR/TE 2 -> WR/TE 3 (Rice takes WR/TE 2): no change of his own; the rows add up to the total."""
    d = _eval(client, [TUTEN], [RICE])
    for who in ("mine", "theirs"):
        lu = d["lineups"][who]
        s = sum(r["change"] or 0 for r in lu["slots"]) + sum(r["change"] for r in lu["out"])
        assert round(s, 2) == lu["total"]["change"] == d["fit"]["this_week"][who]
    rows = {r["player_name"]: r for r in d["lineups"]["mine"]["slots"]}
    assert rows["Malik Nabers"]["change"] is None and rows["Christian Watson"]["change"] is None
    assert rows["Rashee Rice (new)"]["change"] == 10.24 and rows["Rashee Rice (new)"]["status"] == "new"
    assert d["lineups"]["mine"]["out"] == [{"slot": "WR/TE", "player_name": "Ladd McConkey", "gsis_id": "00-0039915",
                                           "value": 6.88, "change": -6.88, "why": "to the bench"}]
    assert d["lineups"]["mine"]["reshuffled"] == ["Nabers WR/TE 2 → WR/TE 3"]
    print(f"\nlineup detail, mine: {[(r['slot'], r['player_name'], r['change']) for r in d['lineups']['mine']['slots']]}"
          f" out {[(r['player_name'], r['change']) for r in d['lineups']['mine']['out']]}")


def test_slot_only_reshuffle_is_no_player_change():
    """Constructed: three interchangeable WR/TE slots; A and B start before and after, only their slot numbers change;
    C (8) leaves for D (11). Membership: D in, C out; A and B in neither list, no per-player gain."""
    slots = [Slot(f"WR+TE{i}", "WR+TE", frozenset({"WR", "TE"}), i) for i in (1, 2, 3)]
    a, b, c, d = (Player(x, "WR", v) for x, v in (("A", 12.0), ("B", 10.0), ("C", 8.0), ("D", 11.0)))
    before = Lineup((Start(slots[0], a, 1.0), Start(slots[1], b, 1.0), Start(slots[2], c, 1.0)), 30.0, (), ())
    after = Lineup((Start(slots[0], a, 1.0), Start(slots[1], d, 1.0), Start(slots[2], b, 1.0)), 33.0, (), ())
    side = T.Side(roster_id=1, gives=("C",), gets=("D",), weeks=(4,), before=(30.0,), after=(33.0,), lineup_before=before,
                  lineup_after=after, cuts=(), limit=10, size_before=3, size_after=3, opened=0, fill=None, price_out=None,
                  price_in=None)

    class _Ctx:
        def name(self, p):
            return {"A": "Al Aa", "B": "Bo Bb", "C": "Cy Cc", "D": "Di Dd"}[p]

        def pos(self, p):
            return "WR"

        def player(self, p):
            return {"sleeper_id": p, "player_name": self.name(p), "position": "WR"}

    m = decisions._membership(_Ctx(), side)
    assert [x["player"]["sleeper_id"] for x in m["in"]] == ["D"] and m["in"][0]["value"] == 11.0
    assert [(x["player"]["sleeper_id"], x["why"]) for x in m["out"]] == [("C", "traded")]
    assert m["moved"] == ["Bb WR/TE 2 → WR/TE 3"]
    assert decisions._lineup_words(_Ctx(), m, "Them") == "Dd starts at WR/TE; Cc goes to Them."


# ------------------------------------------------------------------ the dictionary in the answer's words
OLD_WORDS = re.compile(r"most weeks|\bmarket\b|\bfit\b|\binterest\b|\bdue\b|cool off", re.I)


@needs_db
def test_trade_words_use_the_dictionary(client):
    d = _eval(client, [TUTEN], [RICE])
    words = [d["fit"]["words"], d["market"]["words"], d["effect_words"], d["lineup_words"], d["backup_words"],
             d["hold_words"], d["window_words"], d["their_change"]["effect_words"], d["their_change"]["lineup_words"],
             *(v for v in d["how"].values() if v)]
    hits = [w for w in words if w and OLD_WORDS.search(w)]
    assert not hits, hits
    assert d["fit"]["words"].startswith("**Improvement to your starting lineup** (best lineup each week)")
    assert d["market"]["words"].startswith("**Projected value above available replacements**")
    assert d["fit"]["words"].endswith("you **+3.4** this week and **+9.5** over weeks 4–7; them **-2.0** and **-2.7**.")


@needs_db
def test_the_full_package_names_both_assets_in_the_lineup_story(client):
    """The review's headline package (Houston Texans QB + Tuten for Rice): the team QB's departure is a starter out."""
    d = _eval(client, [HOUSTON_QB, TUTEN], [RICE])
    assert {x["player_name"] for x in d["give"]} == {"Houston Texans QB", "Bhayshul Tuten"}
    out = {x["player"]["player_name"]: x["why"] for x in d["starters_out"]}
    assert out.get("Houston Texans QB") == "traded"
    assert "in place of Houston Texans QB (traded)" in d["lineup_words"]          # IR-2: slot by slot
    lu = d["lineups"]["mine"]
    assert round(sum(r["change"] or 0 for r in lu["slots"]) + sum(r["change"] for r in lu["out"]), 2) == d["fit"]["this_week"]["mine"]
    print(f"\n70587 8<->12 Houston QB + Tuten for Rice: this week {d['fit']['this_week']}, window {d['fit']['window']}; "
          f"{d['lineup_words']}")


@needs_db
def test_this_week_window_names_no_total(client):
    d = _eval(client, [TUTEN], [RICE], window="week")
    assert d["window_words"] == "this week" and "in total" not in d["effect_words"]
    assert d["effect_words"] == "Your starting lineup: about 3.4 more points this week."
