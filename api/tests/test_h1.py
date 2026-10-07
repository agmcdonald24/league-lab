"""Wave H (H1): the gaps Wave G left — the upside stash and buy low / sell high on /api/waivers, /api/about (what the
projection leans on most, its grades), the rest of season in one round of queries, /api/search for any league."""

from __future__ import annotations

import json
import re
import time

import numpy as np
import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab.roster_value import RosterBoard, trade_candidates
from league_lab.scoring import compute_points

from league_lab_api import about, db, decisions, ondemand

from .conftest import ANDREW, DYNASTY, SCRUBS, SLEEPER_FIXTURES, needs_db

TEST_LEAGUE = "9000000000000000001"


def _scoring(league_id: str) -> dict:
    return A.league_scoring(json.loads((SLEEPER_FIXTURES / f"league_{league_id}.json").read_text()))[0]


# ------------------------------------------------------------------------------ the vectorised pricing
@needs_db
def test_compute_points_frame_equals_compute_points_bit_for_bit(monkeypatch):
    """price_lines (one vectorised pass) = compute_points row by row, to the last bit, on every 2026 stat line, in the
    three fixture leagues' scorings and every reference scoring (TE premium: the position premium)."""
    monkeypatch.setenv("LEAGUE_LAB_EV_PRICING", "0")   # M4: the flat engine's parity (unset, the record's mode decides)
    lines = db.query(f"select gsis_id, position, {A._COMPS} from ops.projection_lines where season = 2026", ())
    if lines.empty:
        pytest.skip("no NFL-wide lines in this database")
    lines = A._floats(lines, list(A.STAT_LINE)).set_index("gsis_id")
    refs = db.query(A.REFERENCES_SQL, ())
    scorings = [_scoring(lid) for lid in (DYNASTY, SCRUBS, TEST_LEAGUE)]
    scorings += [r if isinstance(r, dict) else json.loads(r) for r in refs["scoring_settings"]]
    stats = lines[list(A.STAT_LINE)].rename(columns=A.STAT_LINE).fillna(0.0)
    stats["position"] = lines["position"].to_numpy()
    recs = stats.to_dict("records")
    for sc in scorings:
        fast = A.price_lines(lines, sc).to_numpy()
        slow = np.array([compute_points(r, sc) for r in recs])
        assert np.array_equal(fast, slow)


# ------------------------------------------------------------------------------ rest of season in one round of queries
@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS, TEST_LEAGUE])
def test_ros_window_equals_the_week_by_week_path(monkeypatch, league):
    """The one-round window (load_window + skill_window + kd_window) = the same weeks priced one by one with
    price_week (the path before Wave H) — every column, every player, the references — and it is faster cold."""
    if not A.nfl_wide_ready(db.query, 2026, 4):
        pytest.skip("F1's tables are not in this database")
    monkeypatch.setenv(A.BOARD_SOURCE_ENV, "auto")
    t0 = time.perf_counter()
    _, fast = ondemand.ros_on_demand(league)
    t1 = time.perf_counter()
    db.clear_cache()
    A.clear_priced()
    real = A.load_window

    def no_weeks(*args, **kwargs):          # the window holds no week: every week goes through price_week
        w = real(*args, **kwargs)
        w.weeks = []
        return w
    monkeypatch.setattr(A, "load_window", no_weeks)
    t2 = time.perf_counter()
    _, slow = ondemand.ros_on_demand(league)
    t3 = time.perf_counter()
    print(f"\nros {league}: one round {1000 * (t1 - t0):.0f} ms, week by week {1000 * (t3 - t2):.0f} ms, {len(fast)} players")
    assert len(fast) == len(slow) > 300
    f, s = fast.set_index("player_key").sort_index(), slow.set_index("player_key").sort_index()
    assert list(f.index) == list(s.index)
    for c in f.columns:
        if c in ("bye_weeks", "weeks_json"):
            assert f[c].map(json.dumps).equals(s[c].map(json.dumps)), c
        elif f[c].dtype.kind in "fc":
            np.testing.assert_allclose(f[c].astype(float), s[c].astype(float), atol=1e-9, equal_nan=True, err_msg=c)
        else:
            assert f[c].fillna(-1).astype(str).equals(s[c].fillna(-1).astype(str)), c
    assert fast.attrs["references"] == slow.attrs["references"]


# ------------------------------------------------------------------------------ /api/about
@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_about_house_league_is_the_marts(client, sql, league):
    about.clear()
    d = client.get("/api/about", params={"league": league}).json()
    assert d["source"] == "database" and d["model"]["sections"] and d["model"]["answer"]
    imp = d["importance"]
    lid = imp["scored_in_league_id"]
    mart = pd.DataFrame(sql("""select position, feature_label, importance, importance_rank from analytics.mart_projection_importance
                               where model = 'component' and component = 'total' and league_id = %s and importance_rank <= 10
                                 and model_version = (select max(model_version) from analytics.mart_projection_importance
                                                      where model = 'component' and league_id = %s)
                               order by position, importance_rank""", (lid, lid)))
    for p in imp["positions"]:
        m = mart[mart["position"] == p["position"]]
        assert [f["feature_label"] for f in p["features"]] == list(m["feature_label"])
        assert [f["importance"] for f in p["features"]] == pytest.approx([float(x) for x in m["importance"]])
        assert p["top"] == m["feature_label"].iloc[0] and p["lead"].startswith(f"For {p['position']}s the model leans most on")
    assert "How we measured it" in imp["how_measured"] and imp["eval_season"] and imp["fit_seasons"]
    g = d["grades"]
    assert g["scored_in_league_id"] == league
    drift = {r["position"]: r for r in sql("""select * from analytics.mart_projection_drift where league_id = %s
                                              and season = (select max(season) from analytics.mart_projection_drift
                                                            where league_id = %s)""", (league, league))}
    bt = pd.DataFrame(sql("""select position, season, spearman, mae, coverage_80 from analytics.mart_projection_backtest
                             where league_id = %s and is_current and scorer = 'v2_points'""", (league,)))
    for p in g["positions"]:
        r = drift[p["position"]]
        assert p["backtest"]["spearman"] == pytest.approx(float(r["backtest_spearman"]))
        assert p["backtest"]["mae"] == pytest.approx(float(r["backtest_mae"]))
        if int(r["weeks_scored"] or 0) > 0:
            assert p["season"]["spearman"] == pytest.approx(float(r["spearman"]))
            assert p["season"]["coverage_80"] == pytest.approx(float(r["coverage_80"]))
        b = bt[bt["position"] == p["position"]].sort_values("season")
        assert [s["season"] for s in p["by_season"]] == list(b["season"])
        assert [s["spearman"] for s in p["by_season"]] == pytest.approx([float(x) for x in b["spearman"]])
    assert g["answer"] and g["howto"]


@needs_db
def test_about_any_league_says_whose_numbers(client):
    about.clear()
    d = client.get("/api/about", params={"league": TEST_LEAGUE}).json()
    assert d["source"] == "sleeper" and d["league_name"] == "Test League"
    assert d["grades"]["scored_in_league_id"] == SCRUBS            # the closest house scoring (full vs half PPR, same rest)
    assert "League of Scrubs" in d["why"] and d["importance"]["positions"]
    assert client.get("/api/about", params={"league": "123"}).status_code == 404


# ------------------------------------------------------------------------------ /api/waivers: upside stash, buy low / sell high
@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_waivers_upside_is_mart_waiver_upside(client, sql, league):
    decisions.clear_memo()
    team = ANDREW[league]
    d = client.get("/api/waivers", params={"league": league, "team": team}).json()
    mart = sql("""select * from analytics.mart_waiver_upside where league_id = %s and roster_id = %s and week = %s
                  order by upside_rank""", (league, team, d["week"]))
    st = d["upside"]["stashes"]
    assert [s["add"]["gsis_id"] for s in st] == [m["add_gsis_id"] for m in mart]
    for s, m in zip(st, mart, strict=True):
        assert s["scenario_value"] == pytest.approx(float(m["scenario_value"]))
        assert s["holds_horizon_gain"] == pytest.approx(float(m["holds_horizon_gain"]))
        # IF-1 (Wave I-F): a stash names its drop only when the scenario's lineup gain beats what the drop costs
        assert (s["drop"] or {}).get("player_name") == (m["drop_name"] if s.get("stash_action") != "watch" else None)
        assert s.get("stash_action") != "watch" or s["watch_words"].startswith("Watch, no claim yet")
        assert s["headline"].startswith(f"Upside stash: {m['add_name']}") and s["lines"]
    if not mart:
        assert d["upside"]["why"]


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_waivers_buy_low_sell_high_is_the_trade_finders(client, sql, league):
    """The Trade Finder page's lists: trade_candidates on mart_league_roster_horizon with mart_player_availability's
    PPG - xPPG (computed here independently), the same players in the same order, the gains to 0.01."""
    decisions.clear_memo()
    team = ANDREW[league]
    # IA-2: the lists moved from /api/waivers to the Trades screen (GET /api/trades/lists), the numbers unchanged
    d = client.get("/api/trades/lists", params={"league": league, "team": team}).json()
    hz = sql("select * from analytics.mart_league_roster_horizon where league_id = %s", (league,))
    slots = sql("select roster_positions from analytics.dim_league_season where league_id = %s and is_current_season",
                (league,))[0]["roster_positions"]
    cands = sql(decisions.CANDIDATES_SQL, (league,))
    buy, sell = trade_candidates(RosterBoard(hz, tuple(slots)), team, cands)
    assert [r["player"]["sleeper_id"] for r in d["buy_low"]] == [str(b["sleeper_player_id"]) for b in buy[:25]]
    assert [r["player"]["sleeper_id"] for r in d["sell_high"]] == [str(s["sleeper_player_id"]) for s in sell[:25]]
    for r, b in zip(d["buy_low"], buy, strict=False):
        assert r["fit_horizon"] == pytest.approx(b["fit_horizon"], abs=0.01) and r["diff_per_game"] < 0
        assert r["roster_id"] != team
    assert all(r["diff_per_game"] > 0 for r in d["sell_high"])
    # ---- IP-3 fix round (Wave I-P): the lists are named for what they are; no buy / sell on the strength of the gap
    assert d["buy_line"].startswith("**") and d["sell_line"].startswith("**") and d["howto"]
    assert not re.search(r"\b(buy low|sell high|buy|sell|due|bargain|regression)\b", d["buy_line"] + d["sell_line"], re.I)
    assert d["titles"] == {"below": "Scoring below his work", "above": "Scoring above his work"} and d["gap_line"]
    # ---- end IP-3


@needs_db
def test_waivers_extras_on_demand(client):
    """The Test League (on demand): the stash = Sleeper's free agents with an NFL-wide role alert, the what-if re-priced in
    the league's scoring from the stat lines ops.player_scenarios keeps, said so in `why`; the trade lists answer."""
    decisions.clear_memo()
    d = client.get("/api/waivers", params={"league": TEST_LEAGUE, "team": 3}).json()
    up = d["upside"]
    assert up["source"] == "on demand" and "not on request" in up["why"]
    sc = _scoring(TEST_LEAGUE)
    rows: dict = {}
    for r in db.query("select * from ops.player_scenarios where season = 2026 and week >= %s order by week, league_id",
                      (d["week"],)).to_dict("records"):
        rows.setdefault(r["gsis_id"], r)                         # the first week the alert covers (the route's rule)
    assert up["stashes"]
    for s in up["stashes"]:
        r = rows[s["add"]["gsis_id"]]
        line = r["larger_line"] if isinstance(r["larger_line"], dict) else json.loads(r["larger_line"])
        assert s["scenario_value"] == pytest.approx(compute_points({**line, "position": r["position"]}, sc), abs=0.006)
        assert s["holds_horizon_gain"] is None and s["lines"] and s["headline"].startswith("Upside stash:")
    tl = client.get("/api/trades/lists", params={"league": TEST_LEAGUE, "team": 3}).json()      # IA-2: moved to Trades
    assert "trade_lists" not in d
    assert tl["buy_low"] and tl["points_source"].startswith("priced on request")
    assert all(r["diff_per_game"] < 0 and r["roster_id"] != 3 for r in tl["buy_low"])


@needs_db
def test_waivers_trade_lists_on_demand_equal_the_house_path(client):
    """Dynasty 12 through the on-demand path (Sleeper's rosters, the board solved on request, PPG - xPPG priced from the
    stat columns) gives the house path's buy-low list."""
    decisions.clear_memo()
    house = client.get("/api/trades/lists", params={"league": DYNASTY, "team": 12}).json()          # IA-2: moved to Trades
    od = client.get("/api/trades/lists", params={"league": DYNASTY, "team": 12, "source": "sleeper"}).json()
    h = {r["player"]["sleeper_id"]: r for r in house["buy_low"][:10]}
    o = {r["player"]["sleeper_id"]: r for r in od["buy_low"]}
    assert set(h) <= set(o)
    for k, r in h.items():
        assert o[k]["fit_horizon"] == pytest.approx(r["fit_horizon"], abs=0.01)
        assert o[k]["diff_per_game"] == pytest.approx(r["diff_per_game"], abs=0.01)


# ------------------------------------------------------------------------------ /api/search for any league
@needs_db
def test_search_any_league(client):
    rosters = json.loads((SLEEPER_FIXTURES / f"rosters_{TEST_LEAGUE}.json").read_text())
    owner = {str(p): int(r["roster_id"]) for r in rosters for p in (r.get("players") or [])}
    hits = client.get("/api/search", params={"league": TEST_LEAGUE, "q": "brown"}).json()
    assert hits and all("brown" in h["player_name"].lower() for h in hits)
    ajb = next(h for h in hits if h["player_name"] == "A.J. Brown")
    assert ajb["gsis_id"] == "00-0035676" and ajb["rostered_by_roster_id"] == owner.get(ajb["sleeper_id"])
    assert ajb["label"].startswith("A.J. Brown · WR")
    for h in hits:
        assert h["is_free_agent"] == (owner.get(h["sleeper_id"]) is None)
    assert client.get("/api/search", params={"league": TEST_LEAGUE, "q": "b"}).json() == []
    assert set(hits[0]) >= {"gsis_id", "player_name", "position", "nfl_team", "rostered_by_team", "is_free_agent", "label"}
    house = client.get("/api/search", params={"league": DYNASTY, "q": "St. Brown"}).json()     # house leagues unchanged
    assert house and "sleeper_id" not in house[0]
