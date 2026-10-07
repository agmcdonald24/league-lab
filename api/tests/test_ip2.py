"""IP-2 (Wave I-P): rankings for everyone (`GET /api/rankings`) and "Who should I start?" (`GET /api/rankings/start`) —
the tier rule on hand-built ranges, the head-to-head chances (symmetry, sums, identical players), the words' thresholds,
the route on a reference key, a shaped key and a house league (ownership only there), the parameters' bounds."""

from __future__ import annotations

import numpy as np
import pytest
from league_lab import decisions as WP

from league_lab_api import rankings_api as RK
from league_lab_api import ratelimit, refleague

from .conftest import DYNASTY, SCRUBS, needs_db

ROUTE, START = "/api/rankings", "/api/rankings/start"
ROW_KEYS = {"gsis_id", "player_name", "position", "team", "headshot_url", "rank", "tier", "proj_points", "p10", "p90",
            "opponent", "is_home", "kickoff_at", "report_status", "matchup"}


def _row(g: str, proj: float, p10: float, p90: float, pos: str = "WR", team: str = "AAA", opp: str = "BBB", **kw) -> dict:
    return {"gsis_id": g, "player_name": f"Player {g}", "position": pos, "team": team, "opponent": opp,
            "proj_points": proj, "p10": p10, "p90": p90, **kw}


# ------------------------------------------------------------------------------------------- pure: the distribution
def test_the_distribution_is_the_week_odds_piece():
    """The week's odds' piece: decisions._week_dist then _centred — the mean is the projection."""
    r = _row("00-0000001", 12.0, 4.0, 22.0, p25=8.0, p50=11.0, p75=16.0)
    d = RK.predictive(r)
    kind, raw = WP._week_dist({**{q: r.get(q) for q in ("p10", "p25", "p50", "p75", "p90")}, "value": 12.0, "actual": None})
    assert kind == "range" and isinstance(d, WP.Predictive)
    assert d == WP._centred(raw, 12.0)
    assert abs(d.mean() - 12.0) < 0.05
    assert RK.predictive(_row("00-0000002", 7.0, None, None)) == 7.0          # no range: a point at his projection
    assert RK.predictive({"proj_points": None}) is None


def test_p_beats_is_symmetric_and_identical_is_a_coin_flip():
    a = RK.grid(RK.predictive(_row("a", 12.0, 4.0, 22.0)))
    b = RK.grid(RK.predictive(_row("b", 9.0, 2.0, 18.0)))
    assert RK.p_beats(a, b) + RK.p_beats(b, a) == pytest.approx(1.0, abs=1e-12)
    assert RK.p_beats(a, a) == pytest.approx(0.5, abs=1e-12)
    assert RK.p_beats(a, b) > 0.5
    zero = RK.grid(0.0)
    assert RK.p_beats(zero, zero) == 0.5                                          # two points at 0 tie


def test_p_beats_matches_the_closed_form_for_normals():
    """Two normal-shaped ranges (P10 / P90 at ±1.2816 sd): the grid's chance within 0.02 of Φ(Δ / √(σa² + σb²)) (the
    piecewise-linear shape is not quite a normal) and within 0.006 of D6's Monte Carlo on the same shape."""
    from scipy.stats import norm
    z = 1.2815515655446004
    for (ma, sa), (mb, sb) in (((15, 5), (13, 5)), ((15, 6), (10, 3)), ((10, 4), (10.5, 4))):
        a = RK.grid(WP.Predictive.from_quantiles(ma - z * sa, ma, ma + z * sa))
        b = RK.grid(WP.Predictive.from_quantiles(mb - z * sb, mb, mb + z * sb))
        want = norm.cdf((ma - mb) / np.hypot(sa, sb))
        assert RK.p_beats(a, b) == pytest.approx(want, abs=0.02)          # D6's tolerance for the piecewise shape
        da = WP.Predictive.from_quantiles(ma - z * sa, ma, ma + z * sa)
        db = WP.Predictive.from_quantiles(mb - z * sb, mb, mb + z * sb)
        assert RK.p_beats(a, b) == pytest.approx(WP.prob_a_beats_b(da, db), abs=0.006)   # the same shape: D6's own number


def test_the_tier_rule_on_hand_built_ranges():
    """A run the opener beats under 55 times in 100 is one tier; the first he beats 55+ opens the next; the next tier
    is measured from its own opener."""
    rows = [_row("1", 20.0, 12.0, 28.0), _row("2", 19.6, 11.6, 27.6), _row("3", 19.3, 11.3, 27.3),
            _row("4", 16.0, 8.0, 24.0), _row("5", 15.8, 7.8, 23.8), _row("6", 8.0, 2.0, 14.0)]
    grids = [RK.grid(RK.predictive(r)) for r in rows]
    t, e = RK.tiers(grids)
    assert t == [1, 1, 1, 2, 2, 3]
    assert e[0] is None and e[3] is None and e[5] is None               # an opener has no edge against himself
    assert all(0.5 <= x < RK.TIER_P for x in (e[1], e[2], e[4]))
    # the rule is the stated one: the opener's chance against the next opener is at least 55 in 100
    assert RK.p_beats(grids[0], grids[3]) >= RK.TIER_P > RK.p_beats(grids[0], grids[2])
    # identical players are one tier however many; a player without a projection has none and opens nothing
    same = [RK.grid(RK.predictive(_row(str(i), 10.0, 3.0, 18.0))) for i in range(5)]
    assert RK.tiers(same)[0] == [1, 1, 1, 1, 1]
    assert RK.tiers([grids[0], None, grids[5]])[0] == [1, None, 2]
    assert RK.tiers([])[0] == []


def test_a_tier_break_needs_the_whole_gap_against_the_opener_not_the_neighbour():
    """Small steps add up: each neighbour is a coin flip, but the opener beats the sixth clearly -> a new tier there."""
    rows = [_row(str(i), 20.0 - 0.8 * i, 12.0 - 0.8 * i, 28.0 - 0.8 * i) for i in range(8)]
    grids = [RK.grid(RK.predictive(r)) for r in rows]
    assert all(RK.p_beats(grids[i], grids[i + 1]) < RK.TIER_P for i in range(7))
    t, _ = RK.tiers(grids)
    assert t[0] == 1 and t[-1] >= 2 and t == sorted(t)


# ------------------------------------------------------------------------------------------- pure: head to head
def test_head_to_head_symmetry_sums_and_identical_players():
    a = _row("00-0000001", 14.0, 6.0, 24.0, team="KC", opp="LV")
    b = _row("00-0000002", 12.0, 5.0, 21.0, team="DAL", opp="NYG")
    c = _row("00-0000003", 11.0, 3.0, 22.0, team="SF", opp="SEA")
    for rows in ([a, b], [a, b, c], [a, b, c, _row("00-0000004", 9.0, 2.0, 17.0, team="MIA", opp="BUF")]):
        res = RK.prob_best(rows)
        assert sum(res["best"].values()) == pytest.approx(1.0, abs=1e-12)
        for x in res["pair"]:
            for y in res["pair"][x]:
                assert res["pair"][x][y] + res["pair"][y][x] == pytest.approx(1.0, abs=1e-12)
        # the same players in another order: the same answer (the draws follow the ids, not the order given)
        assert RK.prob_best(list(reversed(rows)))["best"] == res["best"]
    twin = _row("00-0000005", 14.0, 6.0, 24.0, team="KC", opp="LV")
    res = RK.prob_best([a, twin])
    assert res["best"]["00-0000001"] == res["best"]["00-0000005"] == pytest.approx(0.5)
    res3 = RK.prob_best([_row("00-0000007", 10.0, 3.0, 18.0, team="T1", opp="O1"),
                         _row("00-0000008", 10.0, 3.0, 18.0, team="T2", opp="O2"),
                         _row("00-0000009", 10.0, 3.0, 18.0, team="T3", opp="O3")])
    assert len({round(v, 12) for v in res3["best"].values()}) == 1


def test_two_players_agree_with_the_cards_probability():
    """Two players in different games: the joint draws give D6's P(A outscores B) on the same centred ranges (Monte
    Carlo noise only)."""
    a = _row("00-0000001", 14.0, 6.0, 24.0, team="KC", opp="LV", p25=10.0, p50=13.5, p75=18.0)
    b = _row("00-0000002", 12.0, 5.0, 21.0, team="DAL", opp="NYG", p25=8.0, p50=11.5, p75=15.5)
    res = RK.prob_best([a, b])
    want = WP.prob_a_beats_b(RK.predictive(a), RK.predictive(b))
    assert res["pair"]["00-0000001"]["00-0000002"] == pytest.approx(want, abs=0.01)
    # teammates move together: a QB and his receiver are correlated (D6's pair_rho), so the pair's chance moves
    qb = _row("00-0000003", 18.0, 9.0, 28.0, pos="QB", team="KC", opp="LV")
    wr = _row("00-0000004", 17.0, 6.0, 30.0, pos="WR", team="KC", opp="LV")
    wr_away = _row("00-0000004", 17.0, 6.0, 30.0, pos="WR", team="DAL", opp="NYG")
    p_same = RK.prob_best([qb, wr])["pair"]["00-0000003"]["00-0000004"]
    p_apart = RK.prob_best([qb, wr_away])["pair"]["00-0000003"]["00-0000004"]
    assert p_same != p_apart


@pytest.mark.parametrize(("p", "word", "lead"), [
    (0.71, "clear", "Start Aaa"), (0.65, "clear", "Start Aaa"), (0.6, "a lean", "Lean Aaa"),
    (0.547, "a lean", "Lean Aaa"),          # prints 55: the word follows the printed whole percent
    (0.544, "a coin flip", "A coin flip: Aaa"), (0.5, "a coin flip", "A coin flip: Aaa")])
def test_the_words_follow_the_stated_thresholds(p, word, lead):
    rows = [{"gsis_id": "00-0000001", "player_name": "Joe Aaa", "proj_points": 12.0},
            {"gsis_id": "00-0000002", "player_name": "Jim Bbb", "proj_points": 11.0}]
    res = {"best": {"00-0000001": p, "00-0000002": 1 - p},
           "pair": {"00-0000001": {"00-0000002": p}, "00-0000002": {"00-0000001": 1 - p}}}
    c = RK.call(rows, res)
    assert c["verdict"] == word and c["words"].startswith(lead)
    assert f"in {WP.percent(p)} of 100 such weeks" in c["words"]
    assert {"clear": "not a sure one", "a lean": "either is fine", "a coin flip": "either is fine"}[word] in c["words"]
    assert "100%" not in c["words"] and " 0 of 100" not in c["words"]


def test_three_players_say_the_chance_of_the_most():
    rows = [{"gsis_id": f"00-000000{i}", "player_name": n, "proj_points": 12.0 - i} for i, n in enumerate(("A Aa", "B Bb", "C Cc"))]
    res = {"best": {"00-0000000": 0.5, "00-0000001": 0.3, "00-0000002": 0.2},
           "pair": {"00-0000000": {"00-0000001": 0.62, "00-0000002": 0.7}, "00-0000001": {"00-0000000": 0.38, "00-0000002": 0.55},
                    "00-0000002": {"00-0000000": 0.3, "00-0000001": 0.45}}}
    c = RK.call(rows, res)
    assert c["pick"] == "00-0000000" and c["runner_up"] == "00-0000001" and c["verdict"] == "a lean"
    assert c["words"] == ("Lean Aa: he outscores Bb in 62 and Cc in 70 of 100 such weeks — close; either is fine. "
                          "Of the three, he scores the most in 50 of 100.")


# ------------------------------------------------------------------------------------------- the parameters
def test_the_routes_are_in_the_research_bucket():
    assert ratelimit.bucket_for("GET", ROUTE, "league=ref:half&q=chase") == "research"
    assert ratelimit.bucket_for("GET", START, "league=ref:half&ids=00-0000001,00-0000002") == "research"


@pytest.mark.parametrize("ids", [None, "", "00-0000001", "00-0000001,00-0000002,00-0000003,00-0000004,00-0000005",
                                 "00-0000001,abc", "00-0000001,00-0000001", "00-0000001,../etc", "x" * 80])
def test_start_parameters_are_refused(ids):
    with pytest.raises(RK.Bad):
        RK._ids(ids)


@pytest.mark.parametrize(("kw", "msg"), [({"position": "OL"}, "position"), ({"view": "month"}, "view"),
                                         ({"limit": 0}, "limit"), ({"limit": 201}, "limit"), ({"offset": -1}, "offset"),
                                         ({"offset": 1001}, "offset"), ({"limit": "ten"}, "numbers")])
def test_parameters_are_checked_before_anything_is_read(kw, msg, monkeypatch):
    monkeypatch.setattr(RK.R, "context", lambda *a, **k: (_ for _ in ()).throw(AssertionError("read")))
    with pytest.raises(RK.Bad, match=msg):
        RK.rankings("ref:half", **kw)


@pytest.mark.parametrize("q", ["a", "x" * 41])
def test_q_bounds(q, monkeypatch):
    monkeypatch.setattr(RK.R, "context", lambda *a, **k: (_ for _ in ()).throw(AssertionError("read")))
    with pytest.raises(RK.R.BadRequest):
        RK.rankings("ref:half", q=q)


def test_the_preview_is_a_closed_set():
    pv = RK.preview({"position": "wr", "view": "season"})
    assert pv["title"].startswith("Wide receiver rankings for the rest of the season")
    assert pv["url"].endswith("/rankings?position=WR&view=season")
    hostile = RK.preview({"position": "<script>alert(1)</script>", "view": "\" onload=x"})
    assert "<script" not in str(hostile) and "onload" not in str(hostile)
    assert hostile["title"].startswith("Fantasy rankings this week") and hostile["url"].endswith("/rankings")


# ------------------------------------------------------------------------------------------- the route (database)
def _keys(o, acc: set) -> set:
    if isinstance(o, dict):
        for k, v in o.items():
            acc.add(k)
            _keys(v, acc)
    elif isinstance(o, list):
        for v in o:
            _keys(v, acc)
    return acc


@needs_db
def test_rankings_on_a_reference_key(client):
    RK.clear()
    r = client.get(ROUTE, params={"league": "ref:half", "position": "WR", "limit": 200})
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["scoring"] == "Half PPR" and d["view"] == "week" and d["position"] == "WR" and d["week"] == 4
    assert d["positions"] == ["QB", "RB", "WR", "TE", "FLEX", "K", "DEF"]
    assert d["total"] > 100 and len(d["rows"]) == min(200, d["total"])
    rows = d["rows"]
    assert ROW_KEYS <= set(rows[0])
    assert [x["rank"] for x in rows] == list(range(1, len(rows) + 1))
    assert all(a["proj_points"] >= b["proj_points"] for a, b in zip(rows, rows[1:], strict=False))
    tiers = [x["tier"] for x in rows if x["tier"] is not None]
    assert tiers[0] == 1 and tiers == sorted(tiers) and d["tiers"] >= tiers[-1]
    assert all(x["tier_p"] is None or 0 <= x["tier_p"] <= RK.TIER_P for x in rows)          # rounded to 3 places
    # the matchup chip is the defense's tone only: no cornerback anywhere in the answer
    assert all(x["matchup"] is None or x["matchup"]["tone"] in ("favorable", "neutral", "difficult") for x in rows)
    assert not [k for k in _keys(d, set()) if "corner" in k or k in ("cb", "cb_detail")]
    assert not (_keys(d, set()) & refleague.OWNERSHIP)                   # browsing: nobody owns anyone
    assert "55 weeks in 100" in d["tier_words"] and "Half PPR" in d["assumes"]


@needs_db
def test_rankings_views_and_positions(client):
    flex = client.get(ROUTE, params={"league": "ref:half", "position": "FLEX", "limit": 200}).json()
    assert {x["position"] for x in flex["rows"]} <= {"RB", "WR", "TE"} and len({x["position"] for x in flex["rows"]}) == 3
    k = client.get(ROUTE, params={"league": "ref:half", "position": "K"}).json()
    assert k["total"] > 0 and all(x["matchup"] is None for x in k["rows"])
    dfs = client.get(ROUTE, params={"league": "ref:half", "position": "DEF"}).json()
    assert dfs["total"] > 0 and all(x["gsis_id"] is None and x["key"].startswith("DEF:") for x in dfs["rows"])
    season = client.get(ROUTE, params={"league": "ref:half", "position": "QB", "view": "season"}).json()
    assert season["view"] == "season" and season["from_week"] <= season["last_week"]
    assert all(x["ros_games"] for x in season["rows"]) and all(x["matchup"] is None for x in season["rows"])
    assert season["rows"][0]["proj_points"] > 100                         # a season, not a week
    # the season view is /api/ros's projections view, ranked: the same points for the same player
    ros = client.get("/api/ros", params={"league": "ref:half", "position": "QB", "view": "projections", "limit": 5}).json()
    top = {p["gsis_id"]: p["ros_points"] for p in ros["players"]}
    for x in season["rows"][:5]:
        if x["gsis_id"] in top:
            assert x["proj_points"] == pytest.approx(top[x["gsis_id"]], abs=0.01)


@needs_db
def test_a_shaped_key_prices_its_own_scoring(client):
    half = client.get(ROUTE, params={"league": "ref:half", "position": "QB", "limit": 5}).json()
    sf6 = client.get(ROUTE, params={"league": "ref:ppr.sf.p6.t10", "position": "QB", "limit": 5}).json()
    assert sf6["scoring"] == refleague.label("ref:ppr.sf.p6.t10") and "superflex" in sf6["scoring"]
    assert sf6["rows"][0]["proj_points"] > half["rows"][0]["proj_points"]       # 6-point passing touchdowns


@needs_db
def test_a_house_league_says_who_has_him(client):
    d = client.get(ROUTE, params={"league": SCRUBS, "position": "WR", "limit": 30}).json()
    assert d["scoring"] == "League of Scrubs" and d["league_name"] == "League of Scrubs"
    assert any(x.get("rostered_by_team") for x in d["rows"])
    assert all("rostered_by_roster_id" in x for x in d["rows"])
    dyn = client.get(ROUTE, params={"league": DYNASTY, "position": "K"})
    assert dyn.status_code == 400 and "does not start a kicker" in dyn.json()["error"]
    assert "K" not in client.get(ROUTE, params={"league": DYNASTY, "position": "WR", "limit": 1}).json()["positions"]


@needs_db
def test_search_and_paging(client):
    RK.clear()
    all_wr = client.get(ROUTE, params={"league": "ref:half", "position": "WR", "limit": 200}).json()
    name = all_wr["rows"][0]["player_name"]
    hit = client.get(ROUTE, params={"league": "ref:half", "position": "WR", "q": name.split()[-1]}).json()
    assert hit["total"] >= 1 and hit["rows"][0]["rank"] == 1                    # the rank is the position's, not the search's
    assert client.get(ROUTE, params={"league": "ref:half", "position": "WR", "q": "%%"}).json()["total"] == 0
    p2 = client.get(ROUTE, params={"league": "ref:half", "position": "WR", "limit": 10, "offset": 10}).json()
    assert [x["rank"] for x in p2["rows"]] == list(range(11, 21)) and p2["total"] == all_wr["total"]
    far = client.get(ROUTE, params={"league": "ref:half", "position": "WR", "offset": 1000}).json()
    assert far["rows"] == [] and far["total"] == all_wr["total"]
    for bad in ({"limit": 201}, {"offset": 1001}, {"q": "a"}, {"position": "XX"}, {"view": "year"}):
        assert client.get(ROUTE, params={"league": "ref:half", **bad}).status_code == 400, bad
    # the cache is keyed by the scoring, the week, the view and the position — never by the search or the page
    keys = [k for k in RK._cache.keys() if k[0] == "rk"]
    assert all(len(k) == 6 for k in keys) and len({k for k in keys if k[-1] == "WR"}) == 1


@needs_db
def test_start_answers_two_to_four(client):
    rows = client.get(ROUTE, params={"league": "ref:half", "position": "WR", "limit": 3}).json()["rows"]
    ids = [x["gsis_id"] for x in rows]
    two = client.get(START, params={"league": "ref:half", "ids": ",".join(ids[:2])})
    assert two.status_code == 200, two.text[:300]
    d = two.json()
    assert d["answer"]["verdict"] in ("clear", "a lean", "a coin flip") and "of 100 such weeks" in d["answer"]["words"]
    assert sum(p["p_best"] for p in d["players"]) == pytest.approx(1.0, abs=1e-3)
    assert d["floor"] == RK.START_FLOOR and d["multi_note"] is None
    a, b = d["players"]
    assert a["vs"][b["gsis_id"]] + b["vs"][a["gsis_id"]] == pytest.approx(1.0, abs=1e-3)
    three = client.get(START, params={"league": "ref:half", "ids": ",".join(ids)}).json()
    assert len(three["players"]) == 3 and three["multi_note"] and "Of the three" in three["answer"]["words"]
    # the same pair in either order: the same chances
    rev = client.get(START, params={"league": "ref:half", "ids": f"{ids[1]},{ids[0]}"}).json()
    assert {p["gsis_id"]: p["p_best"] for p in rev["players"]} == {p["gsis_id"]: p["p_best"] for p in d["players"]}
    gone = client.get(START, params={"league": "ref:half", "ids": f"{ids[0]},00-0000000"}).json()
    assert gone["answer"] is None and gone["missing"][0]["gsis_id"] == "00-0000000" and gone["notice"]
    assert client.get(START, params={"league": "ref:half", "ids": ids[0]}).status_code == 400


@needs_db
def test_rankings_in_the_shell_and_the_sitemap(client):
    sm = client.get("/sitemap.xml").text
    assert "/rankings</loc>" in sm
    page = client.get("/rankings", params={"position": "TE", "view": "season"})
    if page.status_code == 200 and "ll:seo" in page.text:          # a build with the markers (web/dist)
        assert "Tight end rankings for the rest of the season" in page.text
        assert "<script>alert" not in client.get("/rankings", params={"position": "<script>alert(1)</script>"}).text
