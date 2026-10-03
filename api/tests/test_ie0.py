"""Wave I-E, IE-0: the review's P0s on dad's league (MFL 70587, `docs/reviews/2026-10-03-mfl-70587-usability-review.md`).

1. The trade calculator keeps every asset: `give=mfl:0682,12490` (Houston Texans QB + Bhayshul Tuten, Big Mac Attack,
   team 8) for `get=10229` (Rashee Rice, Madeyes Revenge, team 12) is a two-for-one end to end; an asset the analysis
   cannot use is named in a 400, never dropped.
2. A Waivers explanation names a slot its candidate is eligible for and takes (no "team QB fills the empty DEF").
3. Platform words: Tuten's card on the MFL league says MFL, shows no Sleeper market line, and one points-per-game
   statement.
Fixtures: `fixtures/mfl/70587/` with the ESPN fixture overlay on (as the e2e's recording, `web/e2e/ie0`).
"""

from __future__ import annotations

import re

import pytest
from league_lab import lineup as LU
from league_lab import trades as T

from league_lab_api import decisions

from .conftest import needs_db
from .test_ic4 import KEY, _mfl_fixtures, overlay  # noqa: F401 - the fixtures, used by name

BIG_MAC, MADEYES = 8, 12
HOU_QB, TUTEN, RICE = "mfl:0682", "12490", "10229"


def _eval(client, give, get, team=BIG_MAC, partner=MADEYES):
    return client.post("/api/trades/evaluate", json={"league": KEY, "team": team, "partner": partner, "give": give, "get": get})


# ------------------------------------------------------------------ 1. the calculator keeps every asset
def test_asset_keys_are_opaque():
    assert T.parse_ids("mfl:0682,12490") == [HOU_QB, TUTEN]
    assert T.parse_ids(["mfl:TMQB-KC", " HOU ", "mfl:TMQB-KC"]) == ["mfl:TMQB-KC", "HOU"]


@needs_db
def test_review_package_is_a_two_for_one_end_to_end(client, overlay):  # noqa: F811
    r = _eval(client, [HOU_QB, TUTEN], [RICE])
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    # the answer names both assets, in the order sent; the unit carries its team (no "FA" badge)
    assert [p["sleeper_id"] for p in d["give"]] == [HOU_QB, TUTEN] and [p["sleeper_id"] for p in d["get"]] == [RICE]
    hou = d["give"][0]
    assert hou["player_name"] == "Houston Texans QB" and hou["team"] == "HOU" and hou["unit"] is True
    assert "Houston Texans QB" in d["headline"] and "Bhayshul Tuten" in d["headline"]
    # roster size: two for one opens a spot (never "no change (1 for 1)")
    assert "you open a spot" in d["size_words"] and "1 for 1" not in d["size_words"]
    # the after-lineup moves Houston out of team QB; Rice in
    slots = {s["slot"]: s["player_name"] for s in d["lineups"]["mine"]["slots"]}
    assert slots["team QB"] == "Chicago Bears QB" and "Houston Texans QB" not in slots.values()
    assert "Rashee Rice (new)" in slots.values()
    assert any("Houston Texans QB (team QB, 30.40, traded)" in n for n in d["lineups"]["mine"]["notes"])
    # the numbers equal the Finder's for the same package (trades.package_gains on the same board: the partner search)
    ctx = decisions.trade_context(KEY)
    board, weeks, span = decisions.window_board(ctx, "next4")
    pk = T.package_gains(board, [HOU_QB, TUTEN], [RICE], weeks)
    assert d["fit"]["this_week"]["mine"] == pytest.approx(pk.my_week, abs=0.01)
    assert d["fit"]["window"]["mine"] == pytest.approx(pk.my_horizon, abs=0.01)
    assert d["fit"]["this_week"]["theirs"] == pytest.approx(pk.their_week, abs=0.01)
    assert d["fit"]["window"]["theirs"] == pytest.approx(pk.their_horizon, abs=0.01)
    # the review's failure, for the record: the reduced one-for-one is a different trade with different numbers
    one = _eval(client, [TUTEN], [RICE]).json()
    assert "1 for 1" in one["size_words"] and one["fit"]["window"]["mine"] != pytest.approx(d["fit"]["window"]["mine"], abs=0.5)
    print(f"\nTwo-for-one ({span}): you {d['fit']['this_week']['mine']:+.2f} this week, {d['fit']['window']['mine']:+.2f} "
          f"over the window; them {d['fit']['this_week']['theirs']:+.2f} / {d['fit']['window']['theirs']:+.2f}; "
          f"Finder {pk.my_week:+.2f} / {pk.my_horizon:+.2f} / {pk.their_week:+.2f} / {pk.their_horizon:+.2f}; "
          f"dial {d['interest']['label']} {d['interest']['score']}")
    print(f"Reduced one-for-one (the review's bug): you {one['fit']['this_week']['mine']:+.2f} / "
          f"{one['fit']['window']['mine']:+.2f}; dial {one['interest']['label']} {one['interest']['score']}")


@needs_db
def test_finder_rows_carry_the_units_team(client, overlay):  # noqa: F811
    d = client.get(f"/api/trades/partners?league={KEY}&team={BIG_MAC}").json()
    units = [p for row in d["partners"] for p in [*row["give"], *row["get"]] if p["position"] in ("TMQB", "TMPK")]
    assert units and all(p["team"] and p["unit"] is True for p in units)


@needs_db
def test_an_asset_the_analysis_cannot_use_is_named_never_dropped(client, overlay):  # noqa: F811
    r = _eval(client, [HOU_QB, "mfl:9999"], [RICE])
    assert r.status_code == 400
    d = r.json()
    assert d["unavailable"] == [{"key": "mfl:9999", "side": "give", "name": None,
                                 "why": "not a player League Lab knows in this league"}]
    assert d["error"].startswith("Can't analyse mfl:9999")
    # a known player on the wrong side: named, with whose roster he is on
    r = _eval(client, [HOU_QB], ["11632"])                     # Malik Nabers is Big Mac Attack's own
    assert r.status_code == 400
    assert r.json()["unavailable"] == [{"key": "11632", "side": "get", "name": "Malik Nabers",
                                        "why": "on Big Mac Attack's roster, not Madeyes Revenge's"}]
    # the unit itself asked for from the wrong team: named by its unit name
    r = _eval(client, [TUTEN], [HOU_QB])
    assert r.status_code == 400 and r.json()["unavailable"][0]["name"] == "Houston Texans QB"


# ------------------------------------------------------------------ 2. Waivers: the explanation is the evaluated move's
def _slot_type_of_label(label: str) -> str:
    return re.sub(r"\d+$", "", label)


@needs_db
def test_every_help_now_card_names_a_slot_its_candidate_takes(client, overlay):  # noqa: F811
    d = client.get(f"/api/waivers?league={KEY}&team={BIG_MAC}").json()
    cards = [*d["top3"], *d["views"]["help"]["moves"]]
    assert cards
    for c in cards:
        m, reason = c["move"], c["reason"]
        if (m.get("weekly_gain") or 0) >= decisions.GAIN_EPS and m.get("add_slot"):
            words = decisions.cards.slot_label(m["add_slot"])
            assert words in reason, (reason, m["add_slot"])
            assert m["add"]["position"] in LU.slot_eligibility(_slot_type_of_label(m["add_slot"])), reason
        assert "WR+TE" not in reason and "TMQB" not in reason and "TMPK" not in reason           # the league's words
    for c in d["views"]["bye"]["moves"]:
        hit = re.search(r"Fills your empty (\S+)", c["reason"])
        if hit:
            assert c["move"]["add"]["position"] == "DEF" and hit.group(1) == "DEF", c["reason"]
    print("\n" + "\n".join(f"{c['move']['add']['player_name']} ({c['move']['add']['position']}): {c['reason']}" for c in cards[:4]))


def test_a_team_qb_never_fills_a_defense_vacancy():
    """The review's case on 70587's week-7 shape: Jacksonville (DEF, a starter), Tuten (bench RB) and McConkey (WR+TE3,
    a starter) on a bye, the DEF slot empty. A team QB with a week-7 gain gets no DEF words; a defense does; a WR
    stands in at McConkey's slot."""
    week = 4
    byes = {7: ["Jacksonville Jaguars", "Bhayshul Tuten", "Ladd McConkey"], ("fit", 7): ["Jacksonville Jaguars"],
            ("pos", 7): {"Jacksonville Jaguars": "DEF", "Bhayshul Tuten": "RB", "Ladd McConkey": "WR"},
            ("empty_types", 7): {"DEF": "DEF"},
            "starter_slot": {"Jacksonville Jaguars": ("DEF", "DEF"), "Ladd McConkey": ("WR+TE3", "WR+TE")}}
    empty = {7: ["DEF"]}
    qb = {"add": {"player_name": "Arizona Cardinals QB", "position": "TMQB"}, "weekly_gain": 0.0, "add_slot": None,
          "week_gains": [0.0, 0.0, 0.0, 3.2]}
    before = "Fills your empty DEF in week 7, when Jacksonville Jaguars is on a bye."        # the review's words
    got = decisions._reason(qb, week, byes, empty, {})
    assert got != before and "DEF" not in got and got == "Would not start for you this week; helps in week 7."
    assert decisions._bye_reason({**qb, "_week": week}, 7, byes, empty) is None
    de = {**qb, "add": {"player_name": "Cincinnati Bengals", "position": "DEF"}}
    assert decisions._reason(de, week, byes, empty, {}) == before
    wr = {**qb, "add": {"player_name": "Devaughn Vele", "position": "WR"}}
    assert decisions._reason(wr, week, byes, empty, {}) == "Starts at WR/TE 3 in week 7, when McConkey is on a bye."
    # a unit is priced from its starter's games: never "no games this season yet"
    assert "No games" not in decisions._reason({**qb, "add": {**qb["add"], "is_no_evidence": True}}, week, byes, empty, {})


# ------------------------------------------------------------------ 3. platform words on the player's card
@needs_db
def test_tutens_card_speaks_mfl_and_states_points_per_game_once(client, overlay):  # noqa: F811
    d = client.get(f"/api/player/00-0040719?league={KEY}&team={BIG_MAC}").json()
    text = " ".join(b.get("text") or "" for s in d["sections"].values() for b in s.get("blocks", []))
    assert d["platform"] == "mfl"
    assert "in MFL" in text and "Sleeper" not in text and "(None)" not in text and "(None)" not in d["header"]
    assert d["market"] is None                                         # Sleeper's number: not on an MFL card
    # one points-per-game statement, with its source; nothing lists it as not shown
    assert "value.points_per_game" not in d["missing_keys"]
    ppg = [m for b in d["sections"]["value"]["blocks"] for m in (b.get("metrics") or []) if m["label"] == "Points / game"]
    assert len(ppg) == 1 and "reconstructed in this league's MFL scoring" in ppg[0]["help"]
    games = client.get(f"/api/player/00-0040719/games?league={KEY}&season={d['season']}").json()["games"]
    played = [g["points"] for g in games if g["played"] and g["season_type"] == "REG"]
    assert float(ppg[0]["value"]) == pytest.approx(sum(played) / len(played), abs=0.051)   # the chart's own number
    print(f"\nTuten: {text[:120]} … ppg {ppg[0]['value']} ({ppg[0]['help']})")


@needs_db
def test_mfl_lists_carry_no_sleeper_market(client, overlay):  # noqa: F811
    d = client.get(f"/api/ros?league={KEY}&team={BIG_MAC}&limit=20").json()
    assert d.get("market_note") is None
    assert all(p.get("market_points") is None for p in d["players"])
