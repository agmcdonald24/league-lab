"""Wave I-I, II-3: the Stats Explorer (`/api/players?window=`; api/league_lab_api/stats.py) and the data inventory.

* the season window is mart_player_season's arithmetic to the digit (counts, shares, rates), so the table, the card and
  the season table agree;
* a share over several games is the summed numerator over the summed denominator, never a mean of weekly percentages;
* Kyren Williams's carry share: the card's number is the table's number (the review's 47.5% on the main database);
* windows (last N games played vs last N calendar weeks vs a week range), ownership, NFL team, minimum games, numeric
  sort over the full set before the page;
* unknown is null, never 0 (routes in season); every catalogue column is in docs/DATA_INVENTORY.md with its status.
"""

from __future__ import annotations

import json
import math
import os
import re
from urllib.parse import urlencode

import pandas as pd
import pytest

from league_lab_api import stats as ST
from league_lab_api.settings import ROOT

from .conftest import DYNASTY, SCRUBS, needs_db

KYREN = "00-0037840"


def _close(a, b, tol=1e-9) -> bool:
    if a is None or (isinstance(a, float) and math.isnan(a)):
        return b is None or (isinstance(b, float) and math.isnan(b))
    if b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def _get(client, **q) -> dict:
    r = client.get("/api/players?" + urlencode({"league": SCRUBS, **q}))
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------------------------------- pure arithmetic
def _rows(**over) -> pd.DataFrame:
    """Two games of one back: 10 of 20 team carries, then 2 of 40 (weekly 50% and 5%)."""
    base = {c: 0 for c in ST.SUMS + ST.TEAM_SUMS + ["team_dropbacks_with_participation", "passing_cpoe", "offense_snap_pct"]}
    g1 = {**base, "gsis_id": "x", "player_name": "X", "position": "RB", "game_id": "g1", "week": 1, "played": True,
          "snaps_known": True, "offense_snap_pct": 0.5, "carries": 10, "team_carries": 20, "team_rb_carries": 15,
          "routes_proxy": None, "routes": None, "team_charted_targets": 0, "passing_cpoe": None}
    g2 = {**g1, "game_id": "g2", "week": 2, "offense_snap_pct": 0.25, "carries": 2, "team_carries": 40, "team_rb_carries": 30}
    return pd.DataFrame([{**g1, **over}, {**g2, **over}])


def test_multi_game_share_is_summed_numerator_over_summed_denominator():
    a = ST.aggregate(_rows()).iloc[0]
    assert a["carries"] == 12 and a["team_carries"] == 60
    assert a["carry_share"] == pytest.approx(0.2)                 # 12 / 60, not (50% + 5%) / 2 = 27.5%
    assert a["carry_share"] != pytest.approx((10 / 20 + 2 / 40) / 2)
    assert a["rb_carry_share"] == pytest.approx(round(12 / 45, 4))
    assert a["carries_per_game"] == pytest.approx(6.0)
    assert a["games"] == 2
    # the one documented exception: snap share is the mean of the per-game shares (no team snap totals published)
    assert a["snap_share"] == pytest.approx(0.375)


def test_a_missed_game_does_not_widen_the_team_denominator():
    df = _rows()
    df.loc[1, ["played", "carries"]] = [False, 0]               # a stat row without an appearance (special teams)
    a = ST.aggregate(df).iloc[0]
    assert a["games"] == 1 and a["team_carries"] == 20 and a["carry_share"] == pytest.approx(0.5)


def test_unknown_is_null_never_zero():
    a = ST.aggregate(_rows()).iloc[0]
    for c in ("target_share", "route_participation", "tprr_proxy", "first_read_target_share", "catchable_rate", "adot",
              "routes", "cpoe"):
        assert a[c] is None or pd.isna(a[c]), c


def test_ratio_rounds_like_postgres_numeric():
    s = ST.ratio(pd.Series([1, 3, -1, 5]), pd.Series([32, 32, 32, 0]))
    assert list(s[:3]) == [0.0313, 0.0938, -0.0313] and pd.isna(s[3])     # half away from zero; 0 denominator -> null


def test_window_last_games_played_vs_calendar_weeks():
    rows = pd.concat([_rows(), _rows().assign(game_id=["g3", "g4"], week=[4, 5])], ignore_index=True)
    rows.loc[rows["week"] == 4, "played"] = False                  # he missed week 4
    g, d = ST.window_rows(rows, "last3", "games", None)
    assert sorted(set(g["week"])) == [1, 2, 5] and int(g["played"].sum()) == 3       # his last 3 games played
    assert d["basis"] == "games" and "games played" in d["label"]
    g, d = ST.window_rows(rows, "last3", "weeks", None)
    assert sorted(set(g["week"])) == [4, 5] and d["weeks"] == [3, 5] and "calendar" in d["label"]
    assert int(g["played"].sum()) == 1                              # 3 calendar weeks, one game played: G says 1
    g, d = ST.window_rows(rows, "weeks", "weeks", (2, 4))
    assert sorted(set(g["week"])) == [2, 4] and d["label"] == "Weeks 2–4 (calendar weeks)"


def test_catalogue_entries_are_complete_and_presets_name_known_columns():
    ids = {c["id"] for c in ST.CATALOGUE}
    assert len(ids) == len(ST.CATALOGUE)
    for c in ST.CATALOGUE:
        assert c["status"] in ("present", "derived", "planned", "unavailable"), c["id"]
        assert c["definition"] and c["label"] and c["short"] and c["source"], c["id"]
        if c["kind"] in ("share", "rate"):
            assert c["numerator"] or c["status"] != "derived", c["id"]
    for p in ST.PRESETS:
        assert set(p["columns"]) <= ids and set(p["extra"]) <= ids, p["key"]
        # the review's default columns are present or derived, never planned / unavailable
        assert all(ST.CAT[c]["status"] in ("present", "derived") for c in p["columns"]), p["key"]
    assert ST.CAT["routes"]["status"] == "unavailable"
    assert ST.CAT["ryoe_per_attempt"]["status"] == "planned"


def test_the_inventory_lists_every_catalogue_column_with_its_status():
    text = (ROOT / "docs" / "DATA_INVENTORY.md").read_text()
    words = {"present": "verified present", "derived": "derived", "planned": "planned", "unavailable": "unavailable"}
    for c in ST.CATALOGUE:
        row = next((ln for ln in text.splitlines() if ln.startswith(f"| `{c['id']}` ")), None)
        assert row, f"{c['id']} missing from docs/DATA_INVENTORY.md"
        assert words[c["status"]] in row.lower(), (c["id"], c["status"], row)
    assert re.search(r"routes run.*unavailable in-season", text, re.I | re.S)


# ------------------------------------------------------------------------------------------- the database
SEASON_COLS = ["games_played:games", "targets", "receptions", "receiving_yards", "carries", "rushing_yards", "attempts",
               "passing_yards", "team_targets", "team_carries", "target_share", "carry_share", "air_yards_share",
               "catch_rate", "yards_per_target", "adot", "yac_per_reception", "yards_per_carry", "completion_rate",
               "yards_per_attempt", "first_read_target_share", "red_zone_target_share", "red_zone_carry_share",
               "route_participation", "tprr_proxy", "yprr_proxy", "avg_offense_snap_pct:snap_share",
               "targets_per_game", "carries_per_game"]


@needs_db
@pytest.mark.parametrize("season", [2025, 2026])
def test_season_window_equals_mart_player_season(client, sql, season):
    d = _get(client, window="season", season=season, position="ALL", min_games=0, limit=1000)
    got = {p["gsis_id"]: p for p in d["players"]}
    mart = sql("""select * from analytics.mart_player_season where season = %s and season_type = 'REG'
                  and position in ('QB', 'RB', 'WR', 'TE')""", (season,))
    assert len(mart) > 50
    bad = []
    for m in mart:
        p = got.get(m["gsis_id"])
        if p is None:
            bad.append(("missing", m["player_name"]))
            continue
        for spec in SEASON_COLS:
            mc, _, pc = spec.partition(":")
            if not _close(m[mc], p[pc or mc], 1e-6 if mc == "avg_offense_snap_pct" else 1e-9):
                bad.append((m["player_name"], mc, m[mc], p[pc or mc]))
    assert not bad, bad[:10]


@needs_db
def test_kyren_carry_share_card_and_table_agree(client, sql):
    """The review: Kyren's card says Carry share 47.5% (the main database, weeks 1–3); the table must say the same.
    Both read summed carries / summed team carries in his games: on any database they are one number."""
    d = _get(client, window="season", position="RB", limit=1000)
    t = next(p for p in d["players"] if p["gsis_id"] == KYREN)
    card = client.get(f"/api/player/{KYREN}?league={SCRUBS}").json()
    shown = [m for b in card["sections"]["usage"]["blocks"] if b.get("kind") == "metrics" for m in b["metrics"]
             if m.get("label") == "Carry share"]
    assert shown, "the card has no Carry share"
    assert shown[0]["value"] == f"{t['carry_share']:.1%}" or shown[0]["value"] == f"{round(t['carry_share'] * 100)}%", \
        (shown[0], t["carry_share"])
    av = sql("select carry_share from analytics.mart_player_availability where league_id = %s and gsis_id = %s",
             (SCRUBS, KYREN))
    assert float(av[0]["carry_share"]) == pytest.approx(t["carry_share"])
    g = sql("""select carries, team_carries from analytics.fct_player_game where gsis_id = %s and season = %s
               and season_type = 'REG' and played""", (KYREN, d["season"]))
    assert t["carry_share"] == pytest.approx(round(sum(r["carries"] for r in g) / sum(r["team_carries"] for r in g), 4))
    weekly = sum(r["carries"] / r["team_carries"] for r in g) / len(g)
    if len(g) > 1 and len({r["team_carries"] for r in g}) > 1:
        assert t["carry_share"] != pytest.approx(round(weekly, 4))   # not a mean of weekly percentages


@needs_db
def test_points_per_game_equals_the_season_table(client):
    old = {p["gsis_id"]: p for p in client.get(f"/api/players?league={SCRUBS}&position=RB&limit=500").json()["players"]}
    new = _get(client, window="season", position="RB", limit=1000)["players"]
    pairs = [(p, old[p["gsis_id"]]) for p in new if p["gsis_id"] in old]
    assert len(pairs) > 20
    assert all(_close(p["points_per_game"], o["ppg"]) and _close(p["points"], o["points"]) for p, o in pairs), \
        [(p["player_name"], p["points_per_game"], o["ppg"]) for p, o in pairs if not _close(p["points_per_game"], o["ppg"])][:5]


@needs_db
def test_windows_and_sample_counts(client):
    last3 = _get(client, window="last3", basis="games", season=2025, position="WR", limit=1000)
    assert last3["window"]["basis"] == "games" and all(p["games"] <= 3 for p in last3["players"])
    weeks = _get(client, window="last3", basis="weeks", season=2025, position="WR", limit=1000)
    assert weeks["window"]["weeks"] == [16, 18] and all(16 <= p["first_week"] for p in weeks["players"])
    rng = _get(client, window="weeks", weeks="3-5", season=2025, position="WR", limit=1000)
    assert rng["window"]["label"] == "Weeks 3–5 (calendar weeks)"
    assert all(3 <= p["first_week"] and p["last_week"] <= 5 and p["games"] <= 3 for p in rng["players"])
    # min games and the visible sample
    two = _get(client, window="season", season=2025, position="WR", min_games=10, limit=1000)
    assert two["players"] and all(p["games"] >= 10 for p in two["players"])


@needs_db
def test_ownership_partition_and_nfl_team(client):
    allp = _get(client, window="season", position="WR,TE", limit=1000)
    parts = {w: _get(client, window="season", position="WR,TE", who=w, team=2, limit=1000) for w in ("mine", "fa", "others")}
    assert sum(parts[w]["total"] for w in parts) == allp["total"]
    assert all(p["rostered_by_roster_id"] == 2 for p in parts["mine"]["players"])
    assert all(p["rostered_by_roster_id"] is None for p in parts["fa"]["players"])
    assert all(p["rostered_by_roster_id"] not in (None, 2) for p in parts["others"]["players"])
    det = _get(client, window="season", position="WR,TE", nfl="DET", limit=1000)
    assert det["players"] and all(p["team"] == "DET" for p in det["players"])


@needs_db
def test_the_question_available_receivers_by_target_share(client):
    """"Which available WRs have the highest target share, and how do their yards per game compare?" — one call."""
    d = _get(client, window="season", position="WR", who="fa", team=2, sort="target_share", dir="desc", limit=10)
    shares = [p["target_share"] for p in d["players"]]
    assert shares == sorted(shares, reverse=True) and all(p["rostered_by_roster_id"] is None for p in d["players"])
    assert all("receiving_yards_per_game" in p for p in d["players"])
    # sorted over the full set before the page: the page is the full sort's head
    full = _get(client, window="season", position="WR", who="fa", team=2, sort="target_share", dir="desc", limit=1000)
    assert [p["gsis_id"] for p in full["players"][:10]] == [p["gsis_id"] for p in d["players"]]


@needs_db
def test_routes_are_null_in_season_and_the_catalogue_says_why(client, sql):
    cur = sql("select max(season) as s from analytics.fct_player_game")[0]["s"]
    has = sql("select count(*) as n from analytics.fct_player_game where season = %s and routes_proxy is not null", (cur,))[0]["n"]
    d = _get(client, window="season", season=cur, position="WR", limit=1000)
    cat = {c["id"]: c for c in d["catalogue"]}
    assert cat["routes"]["available"] is False and cat["routes"]["status"] == "unavailable"
    if has == 0:
        assert cat["route_participation"]["available"] is False and "after the season" in cat["route_participation"]["reason"]
        assert all(p["route_participation"] is None and p["tprr_proxy"] is None for p in d["players"])
    assert all(p["routes"] is None for p in d["players"])                      # never 0


@needs_db
def test_bad_parameters_say_so(client):
    for q in ({"window": "fortnight"}, {"window": "weeks"}, {"window": "weeks", "weeks": "x"}, {"window": "season", "who": "x"},
              {"window": "last3", "basis": "days"}):
        r = client.get("/api/players?" + urlencode({"league": SCRUBS, **q}))
        assert r.status_code == 400 and r.json()["error"], q


@needs_db
def test_legacy_answer_unchanged_plus_catalogue(client):
    d = client.get(f"/api/players?league={SCRUBS}&position=WR&limit=5").json()
    assert "window" not in d and d["columns"][0] == "targets" and len(d["players"]) == 5
    assert {c["id"] for c in d["catalogue"]} == {c["id"] for c in ST.CATALOGUE} and d["presets"]


# ------------------------------------------------------------------------------------------- the e2e recording
@needs_db
@pytest.mark.skipif(not os.environ.get("II3_RECORD"), reason="II3_RECORD=1 re-records web/fixtures/ii3/api_ii3.json")
def test_record_e2e_answers(client):
    """The answers web/e2e/ii3 replays: the Stats frame for League of Scrubs roster 2 — the presets' first loads and the
    windows the spec switches to."""
    def key(path: str, **q) -> str:
        return path + ("?" + urlencode(sorted((k, str(v)) for k, v in q.items())) if q else "")

    out: dict = {}

    def rec(path: str, **q):
        r = client.get(key(path, **q))
        out[key(path, **q)] = {"status": r.status_code, "body": r.json()}

    for pos in ("WR,TE", "RB", "QB"):
        rec("/api/players", league=SCRUBS, window="season", position=pos, limit=1000)
    for pos in ("ALL", "WR,TE"):                            # the shared fixture specs' league (web/e2e/fixtures.spec.ts)
        rec("/api/players", league=DYNASTY, window="season", position=pos, limit=1000)
    rec("/api/players", league=SCRUBS, window="last3", basis="games", position="WR,TE", limit=1000)
    rec("/api/players", league=SCRUBS, window="last3", basis="weeks", position="WR,TE", limit=1000)
    rec("/api/players", league=SCRUBS, window="weeks", weeks="1-2", position="RB", limit=1000)
    rec(f"/api/player/{KYREN}", league=SCRUBS)
    f = ROOT / "web" / "fixtures" / "ii3" / "api_ii3.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, separators=(",", ":"), default=str) + "\n")   # compact: one line
    assert all(v["status"] == 200 for v in out.values()), {k: v["status"] for k, v in out.items()}
