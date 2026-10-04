"""Wave I-G, IG-1 — team units' season value, the finder on season value, unknown is not zero.

1. MFL's team units (TMQB / TMPK, dad's league `mfl:70587`) get a `market` row: season points = IC-4's per-week unit rows
   summed over the market's window, above the best FREE unit of the same kind (never a player). "Houston Texans QB +
   Tuten for Rice" now counts the Houston QB (IF-2: "Not counted (no season projection): Houston Texans QB.").
2. The finder's sanity rule (a) is the value gap — season value above replacement — not the raw rest-of-season totals.
3. A player with no projection row is sent as `null` (never 0) with `no_projection`; My Week says how many starters the
   total counts at 0 (`n_unvalued`).

The MFL cases run on the fixtures (`fixtures/mfl/70587/`, the ESPN overlay on — test_if2's setup) and price on the clone;
the Scrubs cases read the clone (League of Scrubs roster 6 "GoodGameBuddy": Josh Jacobs has no projection row).
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import injury_feed as F
from league_lab import mfl_client as M
from league_lab import player_ids as PI
from league_lab import trades as T
from league_lab.lineup import UNVALUED, Lineup, Player, Slot, Start

from league_lab_api import availability as AV
from league_lab_api import decisions, myweek

from .conftest import SCRUBS, needs_db
from .test_i0b import IDS, MFL_FX
from .test_ic4 import ESPN

KEY = "mfl:70587"
HOUSTON_QB, CAROLINA_QB, RICE, TUTEN = "mfl:0682", "mfl:0677", "10229", "12490"
JACOBS_SID, JACOBS = "5850", "00-0035700"


@pytest.fixture
def mfl(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    PI.reset()
    F.reset()
    AV._snap = None
    AV._built = None
    AV.clear_context()
    A._default = None
    decisions.clear_memo()
    yield
    PI.reset()
    F.reset()
    AV._snap = None
    AV.clear_context()
    A._default = None
    decisions.clear_memo()


@pytest.fixture
def house():
    decisions.clear_memo()
    yield
    decisions.clear_memo()


def _eval(client, give, get, team=8, partner=12, league=KEY) -> dict:
    r = client.post("/api/trades/evaluate", json={"league": league, "team": team, "partner": partner, "give": give, "get": get})
    assert r.status_code == 200, r.text[:400]
    return r.json()


def _partners(client, league=KEY, team=8) -> dict:
    r = client.get(f"/api/trades/partners?league={league}&team={team}")
    assert r.status_code == 200, r.text[:400]
    return r.json()


def _cards(d: dict) -> list[tuple[str, str]]:
    return [(" + ".join(x["player_name"] for x in r["give"]), " + ".join(x["player_name"] for x in r["get"])) for r in d["partners"]]


# ------------------------------------------------------------------ 1. team units' season value (no database)
def _lw(units_by_week: dict[int, list[tuple[str, str, float]]], rosters: list[list[str]], players: dict) -> SimpleNamespace:
    pr = {w: SimpleNamespace(units=pd.DataFrame(rows, columns=["position", "team", "proj_points"])) for w, rows in units_by_week.items()}
    return SimpleNamespace(rosters=[{"roster_id": i + 1, "players": p} for i, p in enumerate(rosters)], players=players,
                           rest_weeks=sorted(units_by_week), priced=pr)


def test_unit_market_sums_the_weeks_and_takes_the_best_free_unit_as_its_baseline():
    players = {"mfl:0682": {"position": "TMQB", "team": "HOU"}, "mfl:0700": {"position": "TMPK", "team": "HOU"},
               "4046": {"position": "QB", "team": "KC"}}
    weeks = {4: [("TMQB", "HOU", 20.0), ("TMQB", "ARI", 22.5), ("TMQB", "LA", 30.0), ("TMPK", "HOU", 8.0), ("TMPK", "NO", 9.0)],
             5: [("TMQB", "HOU", 19.5), ("TMQB", "ARI", 21.0), ("TMPK", "HOU", 7.0), ("TMPK", "NO", 10.25)],   # LA: a bye
             6: [("TMQB", "ARI", 20.0), ("TMPK", "NO", 6.0)]}                                                # HOU: a bye
    fa = pd.DataFrame([{"sleeper_id": "mfl:TMQB-ARI", "player_name": "Arizona Cardinals QB", "position": "TMQB", "nfl_team": "ARI",
                        "gsis_id": None},
                       {"sleeper_id": "mfl:TMQB-LAR", "player_name": "Los Angeles Rams QB", "position": "TMQB", "nfl_team": "LAR",
                        "gsis_id": None},
                       {"sleeper_id": "mfl:TMPK-NO", "player_name": "New Orleans Saints K", "position": "TMPK", "nfl_team": "NO",
                        "gsis_id": None},
                       {"sleeper_id": "9999", "player_name": "A free quarterback", "position": "QB", "nfl_team": "KC",
                        "gsis_id": "00-9"}])
    pts, repl, name = decisions.unit_market(_lw(weeks, [["mfl:0682", "mfl:0700", "4046"]], players), fa)
    assert pts == {"mfl:0682": 39.5, "mfl:0700": 15.0, "mfl:TMQB-ARI": 63.5, "mfl:TMQB-LAR": 30.0, "mfl:TMPK-NO": 25.25}
    assert repl == {"TMQB": 63.5, "TMPK": 25.25}                    # the best FREE unit of the kind; never the QB
    assert name == {"TMQB": "Arizona Cardinals QB", "TMPK": "New Orleans Saints K"}
    assert "4046" not in pts and "9999" not in pts                  # players are priced by market_points, not here
    # no unit slots, no units: nothing (a Sleeper league), and no context at all: nothing
    assert decisions.unit_market(_lw({4: []}, [["4046"]], {"4046": {"position": "QB", "team": "KC"}}), None) == ({}, {}, {})
    assert decisions.unit_market(None, fa) == ({}, {}, {})


def test_unit_with_no_priced_week_has_no_market_row():
    players = {"mfl:0682": {"position": "TMQB", "team": "HOU"}}
    pts, repl, _ = decisions.unit_market(_lw({4: [("TMQB", "ARI", 22.5)]}, [["mfl:0682"]], players), None)
    assert pts == {} and repl == {}                                  # unknown, not 0 - and no free unit: no baseline


@needs_db
def test_houston_qb_has_a_season_value_and_the_verdict_counts_it(client, mfl):
    e = _eval(client, [HOUSTON_QB, TUTEN], [RICE])
    by = {x["player_name"]: x for x in e["market"]["players"]}
    hou = by["Houston Texans QB"]
    print("\nHouston QB:", hou["season_points"], hou["market_price"], "| replacement:", e["market"]["replacement"].get("TMQB"),
          "|", e["values"]["season_value"]["words"], "| sanity:", e["sanity"])
    assert hou["unit"] is True and hou["season_points"] == 355 and hou["market_price"] == 0
    assert e["market"]["replacement"]["TMQB"] == {"season_points": 378, "player_name": "Arizona Cardinals QB"}
    assert e["market"]["replacement"]["TMPK"]["player_name"].endswith(" K")
    assert e["market"]["unknown"] == [] and e["values"]["season_value"]["unknown"] == []
    assert e["values"]["season_value"]["words"] == ("Season value above replacement: you give 14, you get 7 (about even). "
                                                   "You give 2 players for 1: 1 roster spot freed.")
    assert "about even by season value" in e["verdict"] and e["sanity"] is None
    # the other team QB of the review's headline trade is priced too
    e2 = _eval(client, [HOUSTON_QB], [RICE, CAROLINA_QB])
    assert e2["values"]["season_value"]["unknown"] == [] and "Not counted" not in e2["values"]["season_value"]["words"]


@needs_db
def test_a_units_season_points_are_ic4s_rest_of_season_rows_over_the_markets_weeks(client, mfl):
    ctx = decisions.trade_context(KEY)
    rw = decisions.ros_weeks(ctx)
    for k in (HOUSTON_QB, CAROLINA_QB):
        weeks = rw["weeks"].get(k) or {}
        want = round(sum(round(v, 2) for w, v in weeks.items() if w in ctx.lw.rest_weeks), 2)
        assert weeks and ctx.points[k] == pytest.approx(want, abs=0.011), k
        assert ctx.prices[k] == pytest.approx(max(0.0, ctx.points[k] - ctx.replacement["TMQB"]))


# ------------------------------------------------------------------ 2. the finder's rule (a) on season value
def test_the_value_rule_fires_on_a_value_gap_not_a_volume_gap():
    v = {"a": 42.0, "b": 0.4, "c": 10.0, "d": 3.0, "e": 0.0, "x": 69.0, "y": 56.0}
    ros = {"a": 300.0, "b": 200.0, "c": 120.0, "d": 140.0, "e": 90.0, "x": 200.0, "y": 450.0}
    assert T.sanity(["a", "b"], ["c"], ros=ros, ours={}, market={}, values=v) == (
        "you give 42 season value above replacement for 10: 32 more, over 25% of what you give")
    # a volume gap with no value gap: 140 rest-of-season points for 90 (the raw rule fires), 3 season value for 0: even
    assert T.sanity(["d"], ["e"], ros=ros, ours={}, market={}) is not None
    assert T.sanity(["d"], ["e"], ros=ros, ours={}, market={}, values=v) is None
    assert T.sanity(["x"], ["y"], ros=ros, ours={}, market={}, values=v) is None        # 69 for 56: under 25%
    assert T.sanity(["a"], ["z"], ros=ros, ours={}, market={}, values=v) is None        # z unknown: not judged
    assert T.sanity(["c"], ["a"], ros=ros, ours={}, market={}, values=v) is None        # you get the value
    assert T.value_gap(["a"], ["e"], {"a": 9.0, "e": 0.0}) is None                      # 9 for 0: about even (10 points)
    # the market rule (b) still comes first
    assert T.sanity(["a"], ["c"], ros={}, ours={"a": 5.0}, market={"a": 20.0}, values=v).startswith("the market disagrees")
    assert decisions.calc_sanity(["a", "b"], ["c"], v, {}, {}, str) == T.value_gap(["a", "b"], ["c"], v)


def test_the_screen_names_each_rule_among_the_left_out():
    rej = [((i,), f"you give {i} season value above replacement for 0: …") for i in range(5)] + [(("m",), "the market disagrees …")]
    ex = decisions.rejected_examples(rej)
    assert len(ex) == 3 and ex[0][1].startswith("the market") and ex[1] is rej[0] and ex[2] is rej[1]


@needs_db
def test_the_finders_warning_fires_on_the_value_rule_mfl(client, mfl):
    d = _partners(client)
    ctx = decisions.trade_context(KEY)
    print("\nafter:", _cards(d)[:6], "| rejected", d["rejected_count"], [x["why"] for x in d["rejected"]])
    assert d["sanity"]["rule"] == "season_value" and "season value above replacement" in d["sanity"]["words"]
    assert d["rejected"] and all(x["why"].startswith(("you give", "the market")) for x in d["rejected"])
    assert not any("rest-of-season points" in x["why"] for x in d["rejected"])
    for r in d["partners"]:
        give, get = [x["sleeper_id"] for x in r["give"]], [x["sleeper_id"] for x in r["get"]]
        assert T.value_gap(give, get, ctx.prices) is None
    cards = _cards(d)
    # the headline is unchanged; the IA-2 raw rule refused "Chicago Bears QB + Tuten for Coker" (484 rest-of-season
    # points for 141) - on season value it is 14 for 14: suggested now
    assert cards[0] == ("Chicago Bears QB", "Kansas City Chiefs QB + Rashee Rice")
    assert ("Chicago Bears QB + Bhayshul Tuten", "Jalen Coker") in cards
    assert d["partners"][0]["price_in"] == 29                                            # the team QB counted (0 before)


@needs_db
def test_the_finders_warning_fires_on_the_value_rule_scrubs(client, house):
    d = _partners(client, SCRUBS, 6)
    ctx = decisions.trade_context(SCRUBS)
    print("\nScrubs 6:", _cards(d), "| rejected", d["rejected_count"], [x["why"] for x in d["rejected"]])
    assert d["sanity"]["rule"] == "season_value"
    for r in d["partners"]:
        give, get = [x["sleeper_id"] for x in r["give"]], [x["sleeper_id"] for x in r["get"]]
        assert T.value_gap(give, get, ctx.prices) is None
    cards = _cards(d)
    assert ("Tyler Warren", "Mark Andrews + Brock Purdy") not in cards                # 20 season value for 3: refused
    assert ("Jameson Williams", "Kyler Murray") in cards                               # 8 for 0: about even (raw: 112 for 75)
    assert any(x["why"].startswith("you give 20 season value above replacement for 3") for x in d["rejected"]) or \
        d["rejected_count"] > 3


# ------------------------------------------------------------------ 3. unknown is not zero
def test_no_projection_fields_and_the_totals_words():
    rows = pd.DataFrame([
        {"role": "starter", "is_empty_slot": False, "value_source": "proj_points", "value": 12.0},
        {"role": "starter", "is_empty_slot": False, "value_source": UNVALUED, "value": 0.0},
        {"role": "starter", "is_empty_slot": True, "value_source": None, "value": None},
        {"role": "bench", "is_empty_slot": False, "value_source": UNVALUED, "value": 0.0}])
    assert myweek.n_unvalued(rows) == 1                               # starters only: the bench is not in the total
    assert myweek.no_projection_fields(rows.iloc[1]) == {"value": None, "margin": None, "no_projection": True}
    assert myweek.no_projection_fields(rows.iloc[0]) == {"no_projection": False}
    assert myweek.unvalued_words(0) is None
    assert myweek.unvalued_words(1) == "1 starter has no projection and counts as 0 in this total."
    assert myweek.unvalued_words(2) == "2 starters have no projection and count as 0 in this total."


def test_a_trade_lineup_slot_with_no_projection_is_null():
    k = Player(id="k1", position="K", value=0.0, value_source=UNVALUED, reason="no value yet")
    q = Player(id="q1", position="QB", value=21.456, value_source="proj_points")
    lu = Lineup(starts=(Start(Slot("QB", "QB", frozenset({"QB"}), 1), q, 1.0, False),
                        Start(Slot("K", "K", frozenset({"K"}), 2), k, 0.0, False)), total=21.456, bench=(), unplayable=())
    side = SimpleNamespace(lineup_after=lu)
    slots = decisions.no_projection_slots(side, [{"slot": "QB", "value": 21.46}, {"slot": "K", "value": 0.0}])
    assert slots == [{"slot": "QB", "value": 21.46, "no_projection": False}, {"slot": "K", "value": None, "no_projection": True}]
    assert decisions.start_value(lu.starts[1]) is None and decisions.start_value(lu.starts[0]) == 21.46


@needs_db
def test_a_bench_player_with_no_projection_answers_null(client, house):
    d = client.get(f"/api/my-week?league={SCRUBS}&team=6").json()
    jac = next(x for x in d["lineup_full"] if x["player_name"] == "Josh Jacobs")
    assert jac["value"] is None and jac["no_projection"] is True and jac["margin"] is None
    assert jac["flag"] == "no projection"                             # the console's flag on the same row (parity)
    assert all(x["value"] is not None for x in d["lineup_full"] if not x.get("no_projection") and x["role"] != "unplayable"
               and x.get("player_name"))
    assert d["n_unvalued"] == 0 and d["unvalued_words"] is None      # the bench is not in the total
    t = client.get(f"/api/team?league={SCRUBS}&team=6").json()
    tj = next(x for x in t["roster"] if x["player_name"] == "Josh Jacobs")
    assert tj["value"] is None and tj["no_projection"] is True
    e = _eval(client, [JACOBS_SID], ["1466"], team=6, partner=2, league=SCRUBS)
    g = e["give"][0]
    assert g["player_name"] == "Josh Jacobs" and g["this_week"] is None and g["market_price"] is None
    card = client.get(f"/api/player/{JACOBS}?league={SCRUBS}&team=6").json()
    assert card["proj_points"] is None


def test_the_console_shows_a_blank_and_the_words_never_0_00():
    from league_lab_api.applib import cards
    df = pd.DataFrame([{"value": 12.5, "margin": 3.0, "value_source": "proj_points", "flag": ""},
                       {"value": 0.0, "margin": 0.0, "value_source": UNVALUED, "flag": ""},
                       {"value": 0.0, "margin": None, "value_source": UNVALUED, "flag": "Questionable"}])
    out = cards.no_projection_blank(df)
    assert out["value"].isna().tolist() == [False, True, True] and out["margin"].isna().tolist() == [False, True, True]
    assert out["flag"].tolist() == ["", "no projection", "Questionable · no projection"]
    assert df["value"].tolist() == [12.5, 0.0, 0.0]                  # a copy: the rows the cards read are untouched


def test_a_side_with_an_unvalued_player_has_no_season_value_sum():
    assert decisions.known_value({"a": 10.4, "b": 3.6}, ["a", "b"]) == 14
    assert decisions.known_value({"a": 10.4}, ["a", "b"]) is None       # b unknown: the partial 10 is not the side's value
