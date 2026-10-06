"""IN-2 (Wave I-N): the lab without a league — the reference key family (grammar, the site defaults' rules, the
options), a value for every player in a typical league of the chosen shape, the browsing player card, and the trade
calculator without a league (GET /api/trade-calc/free). docs/ANY_LEAGUE.md § reference keys, docs/METRICS.md § "Value
without a league"."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from league_lab import anyleague as A
from league_lab import platforms as P
from league_lab.sleeper_client import LeagueNotFound

from league_lab_api import freetrade, ratelimit, refleague
from league_lab_api.main import app

from .conftest import needs_db

PUKA, BIJAN, ARSB = "00-0039075", "00-0038542", "00-0036963"
KELCE = "00-0030506"
HOSTILE = ["ref:", "ref:half.t12", "ref:half.sf.sf", "ref:tep.half", "ref:half.tep.sf", "ref:half.t16", "ref:half;drop",
           "ref:half\x00", "ref:half/../x", "ref:" + "a" * 500, "ref:sleeper", "ref:half.t", "ref:half..sf", "ref:half.T10x",
           "ref:half%2Esf", "ref:ppr.p6.tep"]


@pytest.fixture
def api(monkeypatch):
    for k in ("LEAGUE_LAB_APP_PASSWORD", "LEAGUE_LAB_API_SECRET", "LEAGUE_LAB_GATE"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(app) as c:
        yield c


# ====================================================================================== 1. the key grammar
def test_every_key_round_trips_and_the_family_is_closed():
    assert len(P.REF_KEYS) == len(set(P.REF_KEYS)) == 160
    for k in P.REF_KEYS:
        base, sf, tep, p6, teams = P.parse_reference(k)
        assert P.ref_key(base, sf, tep, p6, teams) == k
        assert refleague.shape(k).key == k and P.check_key(k.upper()) == k and P.check_key(f"  {k} ") == k
    # IM-3's three keys mean what they meant; the default stays
    assert refleague.DEFAULT == "ref:half" and set(refleague.KEYS) <= set(P.REF_KEYS)
    assert refleague.shape("ref:half").teams == 12 and not refleague.shape("ref:half").sf


@pytest.mark.parametrize("key", HOSTILE)
def test_a_hostile_key_is_not_a_key(key):
    assert P.parse_reference(key) is None
    with pytest.raises(LeagueNotFound):
        refleague.shape(key)
    with pytest.raises(LeagueNotFound):
        P.check_key(key)


def test_labels_say_the_scoring_never_no_league():
    assert refleague.label("ref:half") == "Half PPR" and refleague.league("ref:half")["name"] == "Half PPR"
    assert refleague.label("ref:ppr.sf.tep.p6.t10") == "PPR · superflex · TE premium · 6-pt pass TD · 10 teams"
    assert refleague.shape("ref:espn.t8").assumes == "Value in an 8-team ESPN default league, one quarterback"
    assert refleague.shape("ref:half.sf").assumes == "Value in a 12-team Half PPR league, two quarterbacks (superflex)"
    assert all("No league" not in refleague.label(k) for k in P.REF_KEYS)
    assert P.provider_short("ref:half") != "No league"


# ====================================================================================== 2. the site defaults and the options
def _line(**stats) -> pd.DataFrame:
    row = {c: 0.0 for c in A.STAT_LINE}
    row.update({f"proj_{k}": v for k, v in stats.items()})
    return pd.DataFrame([{**row, "position": stats.pop("position", "WR")}], index=["x"])


def test_espn_default_pays_a_full_point_a_catch_and_minus_two_an_interception():
    espn, ppr = refleague.scoring_of(refleague.shape("ref:espn")), refleague.scoring_of(refleague.shape("ref:ppr"))
    assert espn["rec"] == 1.0 and espn["pass_int"] == -2.0 and ppr["pass_int"] == -1.0
    assert {k for k in espn if espn[k] != ppr.get(k)} == {"pass_int"}          # the only rule that differs from PPR
    qb = _line(passing_yards=250.0, passing_tds=2.0, passing_interceptions=2.0, position="QB")
    assert float(A.price_lines(qb, espn).iloc[0]) == pytest.approx(float(A.price_lines(qb, ppr).iloc[0]) - 2.0)


def test_yahoo_default_pays_half_a_catch_and_minus_one_an_interception():
    yahoo, espn = refleague.scoring_of(refleague.shape("ref:yahoo")), refleague.scoring_of(refleague.shape("ref:espn"))
    assert yahoo["rec"] == 0.5 and yahoo["pass_int"] == -1.0
    assert yahoo["pass_yd"] == 0.04 and yahoo["pass_td"] == 4.0 and yahoo["rush_yd"] == 0.1 and yahoo["rec_yd"] == 0.1
    assert yahoo["rush_td"] == yahoo["rec_td"] == 6.0 and yahoo["fum_lost"] == -2.0 and yahoo["rec_2pt"] == 2.0
    wr = _line(receptions=6.0, receiving_yards=80.0)
    assert float(A.price_lines(wr, espn).iloc[0]) - float(A.price_lines(wr, yahoo).iloc[0]) == pytest.approx(3.0)
    qb = _line(passing_interceptions=2.0, position="QB")
    assert float(A.price_lines(qb, yahoo).iloc[0]) == pytest.approx(-2.0)
    assert float(A.price_lines(qb, espn).iloc[0]) == pytest.approx(-4.0)
    # Yahoo's offense is Half PPR's exactly (the fitted ranges apply as they are)
    assert refleague.fitted_name(refleague.shape("ref:yahoo")) == "scrubs"


def test_the_options():
    sc = refleague.scoring_of(refleague.shape("ref:half.tep.p6"))
    assert sc["bonus_rec_te"] == 0.5 and sc["pass_td"] == 6.0 and sc["rec"] == 0.5
    te, wr = _line(receptions=5.0, position="TE"), _line(receptions=5.0, position="WR")
    assert float(A.price_lines(te, sc).iloc[0]) - float(A.price_lines(wr, sc).iloc[0]) == pytest.approx(2.5)
    assert "SUPER_FLEX" in refleague.slots_of(refleague.shape("ref:half.sf"))
    assert "SUPER_FLEX" not in refleague.slots_of(refleague.shape("ref:half"))
    assert refleague.league("ref:std.t14")["total_rosters"] == 14
    assert refleague.fitted_name(refleague.shape("ref:ppr.tep")) == "te_premium"
    assert refleague.fitted_name(refleague.shape("ref:espn")) is None
    assert not refleague.pricing(refleague.shape("ref:espn"), ["ppr"])["fitted"]
    assert "nearest scoring we fit every night (PPR)" in refleague.pricing(refleague.shape("ref:espn"), ["ppr"])["words"]


# ====================================================================================== 3. the value without a league
def _synthetic(n: int = 80) -> dict[str, list[float]]:
    """Each position's season points, best first (a smooth, thin TE pool)."""
    return {"QB": [300 - 4 * i for i in range(n)], "RB": [260 - 3 * i for i in range(n)],
            "WR": [250 - 2.5 * i for i in range(n)], "TE": [180 - 6 * i for i in range(30)],
            "K": [130 - 1 * i for i in range(40)], "DEF": [115 - 1 * i for i in range(32)]}


def test_starters_fill_flex_and_superflex_from_the_best_left():
    pts = _synthetic()
    st = refleague.starter_counts(pts, 12, False)
    assert st["QB"] == 12 and st["K"] == 12 and st["DEF"] == 12
    assert st["RB"] + st["WR"] + st["TE"] == 12 * 5 + 12                      # 2 RB, 2 WR, TE and a FLEX each
    sf = refleague.starter_counts(pts, 12, True)
    assert sum(sf[p] for p in ("QB", "RB", "WR", "TE")) == 12 * 8 and sf["QB"] > 12   # + a superflex each, mostly QBs
    ro = refleague.rostered_counts(pts, 12, False)
    assert sum(ro[p] for p in ("QB", "RB", "WR", "TE")) == 12 * 7 + 12 * refleague.BENCH   # 7 starters + the bench
    assert ro["K"] == 12 and ro["DEF"] == 12                                  # no kicker or defense on a bench


@pytest.mark.parametrize("sf", [False, True])
def test_value_is_monotonic_in_league_size_at_a_thin_position(sf):
    pts = _synthetic()
    frame = pd.DataFrame([{"player_key": f"{p}{i}", "gsis_id": f"{p}{i}", "player_name": f"{p}{i}", "position": p,
                           "ros_points": v, "is_ranked": True} for p, vs in pts.items() for i, v in enumerate(vs)])
    prev_repl, prev_top = None, None
    for teams in (8, 10, 12, 14):
        table, facts = refleague.values_from(frame, teams, sf)
        repl, top = facts["replacement"]["TE"], float(table[table["position"] == "TE"]["value"].max())
        if prev_repl is not None:
            assert repl <= prev_repl and top >= prev_top
        prev_repl, prev_top = repl, top
        assert (table["value"] >= 0).all()
        assert set(table["value"].round(1)) >= {0.0}                          # the replacement player and below are 0


@needs_db
def test_value_on_the_database_is_the_definition():
    table, facts = refleague.value_table("ref:half")
    assert facts["from_week"] == 4 and facts["last_week"] == 18 and facts["teams"] == 12 and not facts["superflex"]
    assert len(table) > 300
    for pos in ("QB", "RB", "WR", "TE"):
        t = table[table["position"] == pos]
        repl = facts["replacement"][pos]
        assert ((t["ros_points"] - repl).clip(lower=0).round(1) == t["value"]).all()
        assert t["value"].max() > 0
    # monotonic in league size at TE on the real board, and superflex raises a quarterback's value
    tops = [float(refleague.value_table(k)[0].query("position == 'TE'")["value"].max())
            for k in ("ref:half.t8", "ref:half.t10", "ref:half", "ref:half.t14")]
    assert tops == sorted(tops)
    qb1 = refleague.value_table("ref:half")[0].query("position == 'QB'")["value"].max()
    qb2 = refleague.value_table("ref:half.sf")[0].query("position == 'QB'")["value"].max()
    assert qb2 > qb1


@needs_db
def test_the_browsing_card_has_the_value_and_no_owner(api):
    r = api.get(f"/api/player/{PUKA}", params={"league": "ref:half.sf.t10"})
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    text = json.dumps(d)
    for w in ("free agent", "Free agent", "No league", "rostered by", "Rostered by", "Waiver Wire", "League of Scrubs"):
        assert w not in text, w
    assert d["league_name"] == "Half PPR · superflex · 10 teams"
    assert d["foot"] == "Open your league to see who has him and what he is worth to your team."
    v = d["ref_value"]
    assert v["assumes"] == "Value in a 10-team Half PPR league, two quarterbacks (superflex)"
    row = refleague.value_of("ref:half.sf.t10", [PUKA])[PUKA]
    assert v["value"] == pytest.approx(float(row["value"])) and v["position"] == "WR"
    assert "Value in a 10-team Half PPR league" in json.dumps(d["sections"]["value"])
    assert not refleague.OWNERSHIP & set(d)
    hits = api.get("/api/search", params={"league": "ref:half", "q": "nacua"}).json()
    assert hits and all("free agent" not in h["label"] for h in hits)


# ====================================================================================== 4. the calculator without a league
def _side(values: list[float], sds: list[float]) -> dict:
    ps = [{"gsis_id": f"00-000000{i}", "player_name": f"P{i}", "value": v, "no_projection": False} for i, v in enumerate(values)]
    import math
    return {"players": ps, "n": len(ps), "value": sum(values), "ros_points": sum(values) + 100.0,
            "sd": math.sqrt(sum(s * s for s in sds)), "unknown": [], "low": None, "high": None}


def test_the_verdict_rules():
    even = freetrade.verdict(_side([100.0], [30.0]), _side([130.0], [30.0]))       # gap 30, range ± 54: about even
    assert even["even"] and even["lean"] is None and even["low"] < 0 < even["high"]
    assert even["words"].startswith("About even: you get 30 points more")
    lean = freetrade.verdict(_side([100.0], [10.0]), _side([200.0, 20.0], [10.0, 5.0]))
    assert not lean["even"] and lean["lean"] == "get" and lean["words"].startswith("You get more: 120 points")
    assert lean["one_player"]["player_name"] == "P0" and lean["one_player"]["share"] == 1.0
    small = freetrade.verdict(_side([300.0], [1.0]), _side([305.0], [1.0]))       # tight ranges, within 10 points
    assert small["even"]
    assert freetrade.verdict(_side([], []), _side([10.0], [1.0]))["words"] == "Add a player to each side to compare them."


def test_the_route_validates_and_spends_research(api):
    assert ratelimit.bucket_for("GET", "/api/trade-calc/free", "league=ref:half&give=00-0039075") == "research"
    seven = ",".join(f"00-00{i:05d}" for i in range(7))
    for params, code in [({"league": "ref:half", "give": seven}, 400),
                         ({"league": "ref:half", "give": "00-123"}, 400),
                         ({"league": "ref:half", "give": "x' or 1=1--"}, 400),
                         ({"league": "ref:half", "give": PUKA, "get": PUKA}, 400),
                         ({"league": "1389709692405551104", "give": PUKA}, 400),
                         ({"league": "ref:bogus", "give": PUKA}, 404),
                         ({"league": "ref:" + "x" * 300, "give": PUKA}, 404)]:
        r = api.get("/api/trade-calc/free", params=params)
        assert r.status_code == code, (params, r.text[:200])
        assert r.headers["Cache-Control"] == "no-store"
    assert freetrade.ids(f"{PUKA}, {PUKA},,{BIJAN}", "give") == [PUKA, BIJAN]


@needs_db
@pytest.mark.parametrize("key", HOSTILE[:6])
def test_a_hostile_key_is_404_and_never_a_cache_entry(api, key):
    before = set(refleague._values._entries)
    assert api.get("/api/trade-calc/free", params={"league": key, "give": PUKA}).status_code == 404
    assert api.get(f"/api/player/{PUKA}", params={"league": key}).status_code == 404
    after = set(refleague._values._entries)
    assert after <= before | {k for k in after if k[0] in P.REF_KEYS}
    assert all(k[0] in P.REF_KEYS for k in after)


@needs_db
def test_the_calculator_is_symmetric(api):
    a = api.get("/api/trade-calc/free", params={"league": "ref:half", "give": PUKA, "get": f"{BIJAN},{ARSB}"})
    b = api.get("/api/trade-calc/free", params={"league": "ref:half", "give": f"{BIJAN},{ARSB}", "get": PUKA})
    assert a.status_code == b.status_code == 200, a.text[:300]
    x, y = a.json(), b.json()
    assert x["give"]["value"] == y["get"]["value"] and x["get"]["value"] == y["give"]["value"]
    vx, vy = x["verdict"], y["verdict"]
    assert vx["gap"] == pytest.approx(-vy["gap"]) and vx["low"] == pytest.approx(-vy["high"])
    assert vx["high"] == pytest.approx(-vy["low"]) and vx["even"] == vy["even"]
    assert {vx["lean"], vy["lean"]} == {"get", "give"}
    assert x["roster_spots"]["you_get_back"] == -y["roster_spots"]["you_get_back"] == -1
    assert y["roster_spots"]["words"].startswith("You get 1 roster spot back")
    assert x["verdict"]["one_player"]["player_name"] == "Bijan Robinson"
    # per player: the pane's value, his rank, this week's outlook
    p = x["give"]["players"][0]
    assert p["value"] == pytest.approx(float(refleague.value_of("ref:half", [PUKA])[PUKA]["value"]))
    assert p["value_rank_pos"] >= 1 and p["outlook"]["week"] == 4 and p["outlook"]["points"] is not None
    assert x["league_words"] == "Open your league to see what this does to your lineup."
    assert "No league" not in json.dumps(x) and "free agent" not in json.dumps(x)


@needs_db
def test_an_unknown_player_makes_his_side_unknown_not_zero(api):
    d = api.get("/api/trade-calc/free", params={"league": "ref:half", "give": "00-0000001", "get": PUKA}).json()
    assert d["give"]["players"][0]["no_projection"] and d["give"]["value"] is None
    assert d["verdict"]["words"].startswith("Not comparable yet") and d["verdict"]["gap"] is None


# ====================================================================================== 5. the Stats table's value column
@needs_db
def test_the_stats_table_has_the_value_column_while_browsing(api):
    d = api.get("/api/players", params={"league": "ref:half", "window": "season", "position": "WR", "limit": 1000}).json()
    cat = {c["id"]: c for c in d["catalogue"]}
    assert refleague.VALUE_COLUMN in cat and cat["ros_value"]["group"] == "Games and points"
    assert "Value in a 12-team Half PPR league" in cat["ros_value"]["definition"]
    for p in d["presets"]:
        cols = p["columns"]
        assert cols[cols.index("points") + 1] == "ros_value"
    vals = refleague.value_of("ref:half", [PUKA])
    row = next(p for p in d["players"] if p["gsis_id"] == PUKA)
    assert row["ros_value"] == pytest.approx(float(vals[PUKA]["value"]))
    top = api.get("/api/players", params={"league": "ref:half", "window": "season", "position": "WR", "sort": "ros_value",
                                          "limit": 3}).json()["players"]
    assert [p["ros_value"] for p in top] == sorted((p["ros_value"] for p in top), reverse=True) and top[0]["gsis_id"] == PUKA
    csv = api.get("/api/players.csv", params={"league": "ref:half", "position": "WR", "sort": "ros_value",
                                              "cols": "points,ros_value", "limit": 3}).text.splitlines()
    assert csv[0].endswith('"Value (rest of season, above replacement)"') and "Rostered by" not in csv[0]
    assert csv[1].startswith("Puka Nacua,")
    house = api.get("/api/players", params={"league": "1389709692405551104", "window": "season", "position": "WR",
                                            "limit": 5}).json()
    assert "ros_value" not in {c["id"] for c in house["catalogue"]}               # a real league: unchanged


@needs_db
def test_compare_carries_the_value_while_browsing(api):
    d = api.get("/api/compare", params={"league": "ref:half.t14", "a": PUKA, "b": ARSB}).json()
    vals = refleague.value_of("ref:half.t14", [PUKA, ARSB])
    assert d["a"]["ros_value"] == pytest.approx(float(vals[PUKA]["value"]))
    assert d["b"]["ros_value"] == pytest.approx(float(vals[ARSB]["value"]))
    assert d["value_assumes"] == "Value in a 14-team Half PPR league, one quarterback"
