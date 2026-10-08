"""Wave I-A (IA-2): the decisions screens — the window a trade is priced over (`window=week|next4|ros|playoffs` on
POST /api/trades/evaluate and /api/trades/partners), the interest dial's buckets, the sanity bound on partner
suggestions (a constructed Jefferson-for-Lloyd case for both rules, then the routes), buy low / sell high moved from
/api/waivers to GET /api/trades/lists, and the Trade Finder page's compiled sentences still loading. The fictional Test
League is on demand (Sleeper fixtures); the house leagues read their marts. Sleeper is never called."""

from __future__ import annotations

import re

import pytest
from league_lab import anyleague as A
from league_lab import trades as T
from league_lab.roster_value import RosterBoard

from league_lab_api import decisions

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db

TEST_LEAGUE = "9000000000000000001"


@pytest.fixture(autouse=True)
def _fresh():
    A.clear_league_weeks()
    decisions.clear_memo()
    yield
    A.clear_league_weeks()
    decisions.clear_memo()


# ------------------------------------------------------------------------------ the dial (no database)
# IE-1 (Wave I-E, the casual-user review): the dial is the effect on their starters — outcome words, no acceptance claim
# ("No deal" / "Maybe" / "Likely" / "Hard to say no" retired); the number, the needle and the 2 / 6 thresholds are unchanged
@pytest.mark.parametrize("gain,label", [(-8.0, "Makes their lineup weaker"), (-0.5, "Makes their lineup weaker"),
                                        (0.0, "About even"), (0.04, "About even"),
                                        (0.05, "About even"), (1.99, "About even"), (2.0, "Improves their lineup"),
                                        (6.0, "Improves their lineup"), (6.01, "Improves it a lot"), (40.0, "Improves it a lot")])
def test_dial_buckets(gain, label):
    d = decisions.interest(gain, 3.4, "weeks 4–7")
    assert d["label"] == label and 0 <= d["score"] <= 100
    assert d["caption"] == "their starters over weeks 4–7, by our numbers" and d["you"] == 3.4 and d["their_gain"] == round(gain, 2)
    assert d["title"] == "Effect on their starters"


def test_dial_score_is_monotone_and_each_label_owns_a_quarter():
    gains = [x / 4 for x in range(-40, 80)]
    scores = [decisions.interest(g, None, "week 4")["score"] for g in gains]
    assert scores == sorted(scores) and scores[0] == 0 and scores[-1] == 100
    assert decisions.interest(0.0, None, "")["score"] == 25 and decisions.interest(2.0, None, "")["score"] == 50
    assert decisions.interest(6.0, None, "")["score"] == 75 and decisions.interest(12.0, None, "")["score"] == 100


def test_window_must_be_one_of_four():
    assert decisions.check_window(None) == "next4" and decisions.check_window("ROS") == "ros"
    with pytest.raises(decisions.BadRequest):
        decisions.check_window("season")


# ------------------------------------------------------------------------------ the sanity bound, constructed (no database)
JJ, ML = "6794", "11581"          # Justin Jefferson (yours), MarShawn Lloyd (theirs): Sleeper ids, a made-up board
NAMES = {JJ: "Justin Jefferson", ML: "MarShawn Lloyd", "q1": "QB One", "w2": "WR Two", "r1": "RB One",
         "q2": "QB Two", "r3": "RB Three", "r4": "RB Four", "w4": "WR Four"}


def _board() -> RosterBoard:
    """Two rosters (QB, RB, WR, FLEX and a bench spot; two weeks alike). Ours has Jefferson at 10.0 (our number this
    week: a usage dip) in the FLEX and a weak RB; theirs has three RBs and a weak WR. By the lineups alone, Jefferson for
    Lloyd is the best 1-for-1: you +5 per week, them +4 (it was suggested on the live beta, +3.85 over weeks 4–7)."""
    me = [("q1", "QB", 20.0), (JJ, "WR", 10.0), ("w2", "WR", 14.0), ("r1", "RB", 8.0)]
    them = [("q2", "QB", 18.0), (ML, "RB", 15.0), ("r3", "RB", 13.0), ("w4", "WR", 3.0), ("r4", "RB", 12.0)]
    rows = []
    for roster, players in ((1, me), (2, them)):
        for sid, pos, v in players:
            for w in (4, 5):
                rows.append({"roster_id": roster, "week": w, "sleeper_player_id": sid, "position": pos, "player_value": v,
                             "value_source": "proj_points", "role": "bench", "is_locked": False, "reason": None,
                             "slot_type": None, "fantasy_positions": [pos]})
    return RosterBoard(rows, ("QB", "RB", "WR", "FLEX", "BN"))


def test_jefferson_for_lloyd_is_what_the_lineups_alone_suggest():
    b = _board()
    pk = T.package_gains(b, [JJ], [ML], b.weeks)
    assert pk.mutual and pk.my_horizon == pytest.approx(10.0) and pk.their_horizon == pytest.approx(8.0)
    best = T.partners(b, 1, shapes=("1-for-1",))[0].one_for_one
    assert (best.give, best.get) == ((JJ,), (ML,))


def test_rule_a_rest_of_season_refuses_jefferson_for_lloyd():
    b = _board()
    ros = {JJ: 149.19, ML: 96.77}            # League of Scrubs' rest-of-season board (weeks 4–16), 2026-10-03
    why = T.sanity([JJ], [ML], ros=ros, ours={}, market={}, name=NAMES.get)
    assert why == "you give 149 rest-of-season points for 97: 52 more, over 25% of what you give"
    assert T.sanity([JJ], [ML], ros={JJ: 120.0, ML: 100.0}, ours={}, market={}) is None      # 17%: a fair price
    assert T.sanity([JJ], [ML], ros={JJ: 149.19}, ours={}, market={}) is None                # Lloyd unknown: not judged
    rejected: list = []
    found = T.partners(b, 1, shapes=("1-for-1",), rejected=rejected,
                       allow=lambda p: T.sanity(p.give, p.get, ros=ros, ours={}, market={}, name=NAMES.get))
    best = found[0].one_for_one
    assert best is not None and (best.give, best.get) != ((JJ,), (ML,))
    assert [(p.give, p.get) for p, _ in rejected] == [((JJ,), (ML,))] and "rest-of-season" in rejected[0][1]


def test_rule_b_the_market_refuses_a_package_built_on_our_low_number():
    b = _board()
    ours, market = {JJ: 10.0}, {JJ: 16.2}    # ours under 65% of Sleeper's (61.7%)
    why = T.sanity([JJ], [ML], ros={}, ours=ours, market=market, name=NAMES.get)
    assert why is not None and why.startswith("the market disagrees with our number on Justin Jefferson")
    assert T.sanity([JJ], [ML], ros={}, ours={JJ: 11.0}, market=market) is None              # 67.9%: kept
    assert T.sanity([ML], [JJ], ros={}, ours=ours, market=market) is None                    # only players you GIVE
    rejected: list = []
    found = T.partners(b, 1, shapes=("1-for-1",), rejected=rejected,
                       allow=lambda p: T.sanity(p.give, p.get, ros={}, ours=ours, market=market, name=NAMES.get))
    best = found[0].one_for_one
    assert best is not None and JJ not in best.give
    assert rejected and all(JJ in p.give and w.startswith("the market disagrees") for p, w in rejected)


def test_the_partner_search_without_rules_is_unchanged():
    """`allow` None keeps G2's search: partners() and partners_exhaustive() agree on the made-up board."""
    b = _board()
    fast, slow = T.partners(b, 1), T.partners_exhaustive(b, 1)
    assert [(p.roster_id, p.best) for p in fast] == [(p.roster_id, p.best) for p in slow]


# ------------------------------------------------------------------------------ the window on the routes
@needs_db
def test_window_on_partners_and_evaluate_test_league(client):
    """The Test League (on demand), team 3: four windows, the spans named, the gains change; the longer windows extend the
    board past the next four weeks with the rest-of-season board, the first four weeks unchanged."""
    out = {}
    for w in decisions.WINDOWS:
        d = client.get(f"/api/trades/partners?league={TEST_LEAGUE}&team=3&window={w}").json()
        assert d["window"] == w and d["window_label"] == decisions.WINDOW_LABELS[w] and d["window_why"]
        weeks = d["weeks"]
        assert d["span"] == (f"weeks {weeks[0]}–{weeks[-1]}" if len(weeks) > 1 else f"week {weeks[0]}")
        assert all(r["you_gain_horizon"] >= 0.01 and r["they_gain_horizon"] >= 0.01 for r in d["partners"])
        assert "rejected_count" in d and len(d["rejected"]) <= 3
        out[w] = d
    assert out["week"]["span"] == "week 4" and out["next4"]["span"] == "weeks 4–7"
    ros, po = out["ros"]["weeks"], out["playoffs"]["weeks"]
    assert ros[0] == 4 and ros[-1] > 7 and po[-1] == ros[-1] and po[0] > 7 and set(po) < set(ros)
    # one package (the next-four best), evaluated over the four windows
    pk = next(r for r in out["next4"]["partners"] if r["is_best"])
    body = {"league": TEST_LEAGUE, "team": 3, "partner": pk["partner"], "give": [x["sleeper_id"] for x in pk["give"]],
            "get": [x["sleeper_id"] for x in pk["get"]]}
    ev = {w: client.post("/api/trades/evaluate", json={**body, "window": w}).json() for w in decisions.WINDOWS}
    plain = client.post("/api/trades/evaluate", json=body).json()          # no window: the next four weeks, as before
    assert plain["span"] == "weeks 4–7" and plain["fit"]["next_4"] == ev["next4"]["fit"]["next_4"]
    assert ev["next4"]["fit"]["window"]["mine"] == pytest.approx(pk["you_gain_horizon"], abs=0.01)
    for w, e in ev.items():
        assert e["window"] == w and e["span"] == out[w]["span"] and e["weeks"] == out[w]["weeks"]
        assert len(e["before"]["mine"]["by_week"]) == len(e["weeks"])
        assert e["fit"]["window"] == e["fit"]["next_4"]
        # IR-2: the dial is the decision's (the replacement basis, said in its caption)
        assert {**e["interest"], "need": None, "caption": None} == {
            **decisions.interest(e["fit"]["window"]["theirs"], e["fit"]["window"]["mine"], e["span"]), "caption": None}
        assert e["interest"]["caption"].endswith("against realistic replacements")
        assert e["interest"]["caption"] == f"their starters over {e['span']}, against realistic replacements"  # IR-2
        assert e["fit"]["this_week"] == ev["next4"]["fit"]["this_week"]         # this week is this week, whatever the window
        assert e["lineups"]["mine"]["slots"] == ev["next4"]["lineups"]["mine"]["slots"]
    assert ev["week"]["fit"]["window"] == ev["week"]["fit"]["this_week"]
    assert len({round(e["fit"]["window"]["mine"], 2) for e in ev.values()}) >= 3          # the gains change
    # the rest of season starts with the same four weeks the board holds
    assert ev["ros"]["before"]["mine"]["by_week"][:4] == pytest.approx(ev["next4"]["before"]["mine"]["by_week"], abs=0.01)
    assert ev["ros"]["after"]["mine"]["by_week"][:4] == pytest.approx(ev["next4"]["after"]["mine"]["by_week"], abs=0.01)
    assert client.post("/api/trades/evaluate", json={**body, "window": "season"}).status_code == 400
    assert client.get(f"/api/trades/partners?league={TEST_LEAGUE}&team=3&window=season").status_code == 400


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_window_on_a_house_league(client, league):
    """A house league: the rest-of-season window runs to the league's final (mart_player_ros_projection's last_week),
    the playoffs from its playoff_week_start; the extra weeks' values are the mart's weeks_json."""
    team = ANDREW[league]
    ctx = decisions.trade_context(league)
    rw = decisions.ros_weeks(ctx)
    for w, first, last in (("ros", ctx.this_week, rw["last"]), ("playoffs", rw["playoff_start"], rw["last"])):
        d = client.get(f"/api/trades/partners?league={league}&team={team}&window={w}").json()
        assert d["weeks"] == list(range(first, last + 1)) and d["span"] == f"weeks {first}–{last}"
    board, weeks, _ = decisions.window_board(ctx, "ros")
    sid = next(s for s in board.roster(team) if board.has_value(s, [weeks[-1]]))
    g = ctx.gsis(sid)
    assert float(board.row(sid, weeks[-1])["player_value"]) == pytest.approx(rw["weeks"][str(g or sid)][weeks[-1]], abs=0.01)
    for w0 in ctx.board.weeks:          # the board's own weeks are untouched
        assert board.lineup_value(team, w0) == pytest.approx(ctx.board.lineup_value(team, w0), abs=1e-9)


@needs_db
def test_partners_route_applies_both_rules(client, monkeypatch):
    """Scrubs, Andrew's roster: no suggestion breaks rule (a) on the live rest-of-season board; with Sleeper's number for
    the best suggestion's player put far above ours (rule b: the database holds no snapshot this week), that package
    is set aside with the market's words and another comes first."""
    team = ANDREW[SCRUBS]
    d = client.get(f"/api/trades/partners?league={SCRUBS}&team={team}").json()
    ctx = decisions.trade_context(SCRUBS)
    ros, ours, _ = decisions.sanity_inputs(ctx)
    for r in d["partners"]:
        give, get = [x["sleeper_id"] for x in r["give"]], [x["sleeper_id"] for x in r["get"]]
        # ---- IG-1 (Wave I-G): rule (a) is on season value above replacement now (IA-2: the raw rest-of-season totals)
        assert T.sanity(give, get, ros=ros, ours={}, market={}, values=ctx.prices) is None
    assert d["sanity"]["rule"] == "season_value"
    assert d["rejected_count"] >= 1 and all(x["why"] for x in d["rejected"])
    assert d["sanity"]["market_note"] and d["sanity"]["ros_players"] > 0
    best = next(r for r in d["partners"] if r["is_best"])
    target = next(x for x in best["give"] if x["sleeper_id"] in ours)
    monkeypatch.setattr(decisions, "market_week", lambda c: {target["sleeper_id"]: ours[target["sleeper_id"]] * 2 + 1})
    decisions.clear_memo()
    d2 = client.get(f"/api/trades/partners?league={SCRUBS}&team={team}").json()
    assert all(target["sleeper_id"] not in [x["sleeper_id"] for x in r["give"]] for r in d2["partners"])
    assert any(x["why"].startswith(f"the market disagrees with our number on {target['player_name']}") for x in d2["rejected"])
    e = client.post("/api/trades/evaluate", json={"league": SCRUBS, "team": team, "partner": best["partner"],
                                                  "give": [x["sleeper_id"] for x in best["give"]],
                                                  "get": [x["sleeper_id"] for x in best["get"]]}).json()
    assert e["sanity"].startswith("the market disagrees")                      # the calculator says it, never hides it


# ------------------------------------------------------------------------------ buy low / sell high moved to Trades
@needs_db
@pytest.mark.parametrize("league,team", [(SCRUBS, 2), (TEST_LEAGUE, 3)])
def test_buy_low_sell_high_left_waivers_for_trades(client, league, team):
    w = client.get("/api/waivers", params={"league": league, "team": team}).json()
    assert "trade_lists" not in w and "upside" in w
    tl = client.get("/api/trades/lists", params={"league": league, "team": team}).json()
    # ---- IP-3 fix round (Wave I-P): renamed — no buy / sell on the strength of the gap; the record's line (or the plain one)
    assert tl["buy_low"] and tl["buy_line"].startswith("**") and tl["sell_line"].startswith("**")
    assert not re.search(r"\b(buy low|sell high|buy|sell|due|bargain|regression)\b", tl["buy_line"] + tl["sell_line"], re.I)
    assert tl["titles"]["below"] == "Scoring below his work" and tl["gap_line"]
    # ---- end IP-3
    assert all(r["diff_per_game"] < 0 and r["roster_id"] != team for r in tl["buy_low"])
    assert all(r["diff_per_game"] > 0 for r in tl["sell_high"]) and len(tl["buy_low"]) <= 25
    wr = client.get("/api/trades/lists", params={"league": league, "team": team, "position": "WR"}).json()
    assert all(r["player"]["position"] == "WR" for r in wr["buy_low"] + wr["sell_high"])
    assert client.get("/api/trades/lists", params={"league": league, "team": 99}).status_code == 404


def test_the_trade_finders_compiled_sentences_still_load():
    ns = decisions.page_functions("6_Trade_Finder.py", decisions.TRADE_FUNCS)
    assert all(callable(ns[f]) for f in decisions.TRADE_FUNCS)
