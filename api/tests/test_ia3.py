"""Wave I-A (IA-3): the rankings — the pieces, "why this number", the market line, the honesty paragraph.

* The pieces add up: for ten rows of each fixture league (League of Scrubs: the house path, per-week lines from
  mart_player_week_projections; the dynasty: yardage bonuses; the fictional Test League: on demand, anyleague's
  ros_<stat> sums), the listed pieces sum to the points a game to the cent, the points a game x games is the rest
  of season total, and in a scoring without bonuses the per-unit prices explain the number with no remainder line.
* The market: `market_points` is None everywhere when the market mart is not built (this clone), when it is empty,
  and when its read fails — never an exception; present, priced in the league's own scoring, for the players a
  (constructed) mart has a row for — on /api/ros, /api/player and /api/my-week alike, house league or not (the
  mart is league-free: a stat line per player-week, priced on request).
* The words: the gap sentence under 70% / over 140% of the market; the honesty paragraph is one text (about.py and
  web/src/lib/ros.ts) and the ROS answer and /api/about carry it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd
import pytest
from league_lab import scoring as S

from league_lab_api import about, ondemand, why

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db

TEST_LEAGUE = "9000000000000000001"
ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------------------------------------ pure: the pieces
SCRUBS_SCORING = {"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0, "rush_yd": 0.1, "rush_td": 6.0, "pass_yd": 0.04,
                  "pass_td": 4.0, "pass_int": -1.0, "fum_lost": -2.0, "fum": 0.0}


def test_weights_price_each_stat_and_the_position_premium():
    w = why.weights({**SCRUBS_SCORING, "bonus_rec_te": 0.5}, "TE")
    assert w["receptions"] == 1.0 and w["receiving_yards"] == 0.1 and w["passing_yards"] == 0.04
    assert w["targets"] == 0.0 and w["carries"] == 0.0 and w["attempts"] == 0.0     # no points on their own
    assert why.weights({**SCRUBS_SCORING, "bonus_rec_te": 0.5}, "WR")["receptions"] == 0.5


def test_explain_adds_up_and_says_the_chain():
    line = {"targets": 8.9, "receptions": 5.47, "receiving_yards": 96.41, "receiving_tds": 0.45, "carries": 0.2,
            "rushing_yards": 2.5, "rushing_tds": 0.03, "fumbles_lost_total": 0.04}
    pts = S.compute_points({**line, "position": "WR"}, SCRUBS_SCORING)
    e = why.explain(line, pts, SCRUBS_SCORING, "WR", games=12, total=pts * 12)
    assert abs(sum(p["points"] for p in e["pieces"]) - pts) < 0.011
    assert e["sentence"].startswith("8.9 targets → 5.5 catches → 96 yards → 0.48 TDs → ")
    assert e["sentence"].endswith(f"points a game × 12 games = {pts * 12:.0f}")
    words = [p["words"] for p in e["pieces"]]
    assert "5.5 catches × 0.5 = +2.7" in words and "8.9 targets (no points on their own)" in words
    assert "0.20 carries (no points on their own)" not in words                     # worth nothing here: left out


def test_explain_says_a_yardage_bonus():
    sc = {**SCRUBS_SCORING, "bonus_pass_yd_300": 3.0}
    line = {"attempts": 38.0, "passing_yards": 310.0, "passing_tds": 2.1, "passing_interceptions": 0.7}
    pts = S.compute_points({**line, "position": "QB"}, sc)
    e = why.explain(line, pts, sc, "QB")
    assert e["pieces"][-1]["stat"] == "rest" and e["pieces"][-1]["label"].startswith("yardage bonuses")
    assert abs(sum(p["points"] for p in e["pieces"]) - pts) < 0.011
    assert why.explain(line, pts, sc, "K") is None and why.explain({}, 3.0, sc, "QB") is None


def test_market_words_flag_only_the_far_gaps():
    assert why.market_words(10.0, 16.2) == ("Sleeper has him at 16.2. We're well under the market: our number follows "
                                            "his recent usage. Treat it with care.")
    assert why.market_words(23.0, 16.0).startswith("Sleeper has him at 16.0. We're well over the market")
    assert why.market_words(14.0, 16.0) == "Sleeper has him at 16.0."                # 88%: just the number
    assert why.market_words(14.0, None) is None
    b = why.market_block(10.0, None, 4)
    assert b["market_points"] is None and b["words"] is None and b["why"] == why.MARKET_WHY


def test_the_honesty_paragraph_is_one_text():
    ts = (ROOT / "web" / "src" / "lib" / "ros.ts").read_text()
    a = ts.index("export const RANKINGS_HOWTO =")
    body = ts[a:ts.index(";\n", a)]
    assert "".join(ast.literal_eval(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"', body)) == about.RANKINGS_HOWTO
    t = about.RANKINGS_HOWTO
    # Andrew's examples: Dak #1 / Kyler #3 (superflex, 6-point passing TDs), Brissett top-8 (a starter's volume)
    for words in ("not his name", "superflex", "6 points for a passing touchdown", "throws 35 times a game",
                  "volume beats reputation", "Sleeper's own number"):
        assert words in t


# ------------------------------------------------------------------------------------------- the leagues' answers
def _check_rows(rows: list[dict], *, no_rest: bool) -> int:
    n = 0
    for p in rows:
        w = p.get("why")
        if not w or not p.get("ros_games"):
            continue
        assert abs(sum(x["points"] for x in w["pieces"]) - w["points"]) < why.MIN_SHOWN, p["player_name"]   # a cent-level rest is no line
        assert abs(w["points"] * p["ros_games"] - p["ros_points"]) < 0.02 * p["ros_games"], p["player_name"]
        assert w["total"] == pytest.approx(p["ros_points"]) and w["games"] == p["ros_games"]
        if no_rest:          # no bonuses in this scoring: the per-unit prices explain the number (a remainder line
            # is only the pieces too small to list, each under 0.05 a game, and the cents)
            assert all(abs(x["points"]) < 0.15 for x in w["pieces"] if x["stat"] == "rest"), (p["player_name"], w["pieces"])
        assert set(p["per_game"]) == set(why.COLUMNS[p["position"]])
        n += 1
    return n


@needs_db
@pytest.mark.parametrize("league, no_rest", [(SCRUBS, True), (DYNASTY, False), (TEST_LEAGUE, False)])
def test_the_pieces_add_up_for_ten_rows_per_position(league, no_rest):
    checked = 0
    for pos in ("QB", "RB", "WR", "TE"):
        out = ondemand.ros(league, pos, 10)
        assert out["piece_columns"][pos] == list(why.COLUMNS[pos])
        assert out["howto_rankings"] == about.RANKINGS_HOWTO
        checked += _check_rows(out["players"], no_rest=no_rest)
        top = out["players"][0]
        assert top["headshot_url"] and top["ros_points_per_game"] > 0 and isinstance(top["bye_weeks"], list)
        assert top["market_points"] is None and top["market_words"] is None      # no market mart in the clone
    assert checked == 40


@needs_db
def test_kickers_and_defenses_have_no_pieces():
    out = ondemand.ros(SCRUBS, "K", 5)
    assert all(p["why"] is None and p["per_game"] == {} for p in out["players"])
    out = ondemand.ros(SCRUBS, "DEF", 5)
    assert all(p["why"] is None and p["market_points"] is None for p in out["players"])


# ------------------------------------------------------------------------------------------------------ the market
def _fake_market(monkeypatch, rows: list[dict]):
    """A built market mart holding ``rows`` (Sleeper's stat lines, league-free)."""
    df = pd.DataFrame(rows)
    monkeypatch.setattr(why, "missing_relations", lambda names: [])
    monkeypatch.setattr(why, "query", lambda sql, params=(): df[df["gsis_id"].isin(params[2])].copy()
                        if not df.empty else df)


@needs_db
def test_market_points_where_the_mart_has_a_row(monkeypatch, client):
    top = ondemand.ros(SCRUBS, "WR", 3)["players"]
    g = top[0]["gsis_id"]
    line = {"gsis_id": g, "position": "WR", "fetched_at": "2026-10-02T21:00:00Z", "receptions": 7.0,
            "receiving_yards": 92.0, "receiving_tds": 0.6, "targets": 10.0}
    _fake_market(monkeypatch, [line])
    want = S.compute_points({**line, "position": "WR"}, SCRUBS_SCORING)
    rows = client.get(f"/api/ros?league={SCRUBS}&position=WR&limit=3").json()["players"]
    assert rows[0]["market_points"] == pytest.approx(want) and rows[0]["market_words"].startswith(f"Sleeper has him at {want:.1f}.")
    assert all(r["market_points"] is None for r in rows[1:])                       # no row: None, not 0
    card = client.get(f"/api/player/{g}?league={SCRUBS}&team={ANDREW[SCRUBS]}").json()
    assert card["market"]["market_points"] == pytest.approx(want) and card["market"]["words"].startswith("Sleeper has him at")
    assert card["why"]["sentence"].endswith("points this week") and card["leans_on"]["words"].startswith("For WRs")
    # on demand: the same line priced in the Test League's own scoring (full PPR) — a different number
    od = ondemand.ros(TEST_LEAGUE, "WR", 50)["players"]
    hit = [r for r in od if r["gsis_id"] == g]
    assert hit and hit[0]["market_points"] == pytest.approx(S.compute_points({**line, "position": "WR"},
                                                                            {**SCRUBS_SCORING, "rec": 1.0}), abs=0.6)


@needs_db
def test_market_on_my_week_rows(monkeypatch, client):
    mw = client.get(f"/api/my-week?league={SCRUBS}&team={ANDREW[SCRUBS]}").json()
    starters = [r for r in mw["lineup_full"] if r.get("gsis_id")]
    assert starters and all(r["market_points"] is None for r in mw["lineup_full"])
    g = starters[0]["gsis_id"]
    _fake_market(monkeypatch, [{"gsis_id": g, "position": starters[0]["position"], "receptions": 5.0,
                                "receiving_yards": 60.0, "rushing_yards": 10.0}])
    mw = client.get(f"/api/my-week?league={SCRUBS}&team={ANDREW[SCRUBS]}").json()
    by = {r["gsis_id"]: r["market_points"] for r in mw["lineup_full"] if r.get("gsis_id")}
    assert by[g] == pytest.approx(5.0 * 0.5 + 6.0 + 1.0) and sum(v is not None for v in by.values()) == 1


@needs_db
def test_market_never_raises(monkeypatch, client):
    # built but empty
    monkeypatch.setattr(why, "missing_relations", lambda names: [])
    monkeypatch.setattr(why, "query", lambda sql, params=(): pd.DataFrame())
    assert all(r["market_points"] is None for r in client.get(f"/api/ros?league={SCRUBS}&position=RB&limit=5").json()["players"])

    # a read that fails (a mart whose columns moved)
    def boom(sql, params=()):
        raise RuntimeError("column does not exist")
    monkeypatch.setattr(why, "query", boom)
    r = client.get(f"/api/ros?league={TEST_LEAGUE}&position=WR&limit=5")
    assert r.status_code == 200 and all(p["market_points"] is None for p in r.json()["players"])
    card = client.get(f"/api/player/00-0036963?league={SCRUBS}").json()
    assert card["market"]["market_points"] is None and card["market"]["why"] == why.MARKET_WHY


@needs_db
def test_about_carries_the_honesty_paragraph(client):
    about.clear()
    assert client.get(f"/api/about?league={SCRUBS}").json()["rankings_howto"] == about.RANKINGS_HOWTO
