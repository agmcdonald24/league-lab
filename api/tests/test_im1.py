"""IM-1 (Wave I-M): the Stats tables' data — more metrics, every one honest.

* the two columns Andrew saw empty (WR / TE: separation, YAC over expected) fill for 2026 once mart_player_ngs_week is
  built, for every receiver NGS published a week for — the top 40 by targets all have both;
* the new columns are summed numerator / summed denominator over the window (never a mean of weekly rates), a zero
  denominator is null, and each reconciles with SQL over the marts (mart_player_game_advanced, fct_player_game);
* Pro Football Reference's counts divide only by the games PFR covered; unmapped PFR rows are counted, never guessed;
* the catalogue's shape for IM-2's screen: every column has a group, the catalogue runs group by group in GROUPS
  order, every preset has 10–14 default columns and a `full` list; GET /api/players.csv.
"""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal
from urllib.parse import urlencode

import pandas as pd
import pytest

from league_lab_api import stats as ST

from .conftest import SCRUBS, needs_db

NEW_RATES = ["yards_per_reception", "yards_per_touch", "adjusted_yards_per_attempt", "td_rate", "int_rate", "sack_rate",
             "wopr", "racr", "deep_target_share", "deep_target_rate", "epa_per_target", "receiving_success_rate",
             "first_downs_per_target", "receiving_td_rate", "epa_per_carry", "rushing_success_rate",
             "first_downs_per_carry", "rushing_td_rate", "epa_per_dropback", "passing_success_rate", "drop_rate",
             "broken_tackle_rate", "yards_before_contact_per_carry", "yards_after_contact_per_carry", "bad_throw_rate",
             "pressure_rate", "rushing_points_share"]


def _num(r: dict) -> dict:
    """SQL sums arrive as Decimal: compare as floats."""
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in r.items()}


def _get(client, **q) -> dict:
    r = client.get("/api/players?" + urlencode({"league": SCRUBS, **q}))
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------------------------------------- the catalogue
def test_every_column_has_a_group_and_the_catalogue_runs_group_by_group():
    assert ST.GROUPS == ["Games and points", "Receiving", "Rushing", "Passing", "Air yards", "Red zone", "Efficiency",
                         "Expected points", "Next Gen Stats", "Charting", "Snaps and routes", "Advanced (PFR)"]
    seen = [c["group"] for c in ST.CATALOGUE]
    assert all(g in ST.GROUPS for g in seen)
    runs = [g for i, g in enumerate(seen) if i == 0 or seen[i - 1] != g]
    assert runs == ST.GROUPS                                    # one run per group, in GROUPS order
    assert len({c["id"] for c in ST.CATALOGUE}) == len(ST.CATALOGUE) == 101


def test_every_new_column_says_how_it_adds_up_and_why_it_can_be_null():
    for cid in NEW_RATES:
        c = ST.CAT[cid]
        assert c["numerator"] and c["denominator"] and c["aggregation"] and c["reason"], cid
        assert c["status"] == "derived" and c["definition"].strip().endswith("."), cid
    # a noisy rate carries the sample the screen greys below, and that sample is a field of the row
    for c in ST.CATALOGUE:
        if c.get("minimum"):
            m = c["minimum"]
            assert m["n"] > 0 and m["field"] in set(ST.fields(c["positions"])), (c["id"], m)
    # the copy standard: a rate's label says "per" (WORDS.md § "The copy standard"), never "a game" / "a target"
    for c in ST.CATALOGUE:
        assert not re.search(r"\b(a|an) (game|target|carry|attempt|dropback|touch)\b", c["label"]), c["label"]


def test_presets_lead_with_10_to_14_columns_and_carry_the_full_table():
    pre = {p["key"]: p for p in ST.PRESETS}
    assert set(pre) == {"wrte", "rb", "qb"}
    for p in ST.PRESETS:
        assert 10 <= len(p["columns"]) <= 14, p["key"]
        assert all(ST.CAT[c]["status"] in ("present", "derived") for c in p["columns"]), p["key"]
        order = [c["id"] for c in ST.CATALOGUE]
        assert p["full"] == sorted(p["full"], key=order.index)                     # catalogue order
        assert set(p["columns"]) <= set(p["full"])
        for cid in p["full"]:
            assert set(ST.CAT[cid]["positions"]) & set(p["positions"]) and ST.CAT[cid]["status"] != "unavailable"
    assert {"adot", "air_yards_share", "epa_per_target", "separation", "yac_over_expected"} <= set(pre["wrte"]["columns"])
    assert "attempts" not in pre["wrte"]["full"] and "targets" not in pre["qb"]["full"]     # positions that apply


def test_a_season_presets_full_list_keeps_only_what_is_available():
    cat = ST.catalogue(2026, pd.DataFrame())                                    # nothing loaded: NGS / charting / PFR off
    full = {p["key"]: p["full"] for p in ST.presets(cat)}
    assert "separation" not in full["wrte"] and "drop_rate" not in full["wrte"] and "targets" in full["wrte"]


# ------------------------------------------------------------------------------------------------- pure arithmetic
def _two_games(**over) -> pd.DataFrame:
    """One receiver, two games: 10 targets / 6 successes with PFR's row, then 2 targets / 0 successes without one."""
    base = {c: 0 for c in ST.SUMS + ST.TEAM_SUMS + ["team_dropbacks_with_participation", "passing_cpoe", "offense_snap_pct"]}
    g1 = {**base, "gsis_id": "x", "player_name": "X", "position": "WR", "game_id": "g1", "week": 1, "played": True,
          "snaps_known": True, "offense_snap_pct": 0.8, "targets": 10, "receptions": 6, "receiving_yards": 90,
          "receiving_air_yards": 120, "team_targets": 40, "team_air_yards": 300, "target_successes": 6,
          "receiving_epa": 4.5, "deep_targets": 2, "team_deep_targets": 5, "pfr_drops": 1, "has_pfr_rec": True,
          "routes_proxy": None, "routes": None, "team_charted_targets": 0, "passing_cpoe": None}
    g2 = {**g1, "game_id": "g2", "week": 2, "targets": 2, "receptions": 0, "receiving_yards": 0, "receiving_air_yards": 30,
          "team_targets": 20, "team_air_yards": 100, "target_successes": 0, "receiving_epa": -1.5, "deep_targets": 1,
          "team_deep_targets": 1, "pfr_drops": None, "has_pfr_rec": False}
    return pd.DataFrame([{**g1, **over}, {**g2, **over}])


def test_window_rates_are_summed_numerator_over_summed_denominator():
    a = ST.aggregate(_two_games()).iloc[0]
    assert a["receiving_success_rate"] == pytest.approx(0.5)                  # 6 / 12, not (60% + 0%) / 2 = 30%
    assert a["epa_per_target"] == pytest.approx(0.25)                          # 3.0 / 12
    assert a["deep_target_share"] == pytest.approx(0.5)                        # 3 / 6, not (40% + 100%) / 2
    assert a["deep_target_rate"] == pytest.approx(0.25)
    ts, ay = 12 / 60, 150 / 400
    assert a["wopr"] == pytest.approx(round(1.5 * round(ts, 4) + 0.7 * round(ay, 4), 4))
    assert a["racr"] == pytest.approx(0.6)                                     # 90 / 150
    assert a["yards_per_reception"] == pytest.approx(15.0)
    # PFR: game 2 has no PFR row, so its 2 targets are out of the denominator (1 drop / 10 targets, not / 12)
    assert a["drop_rate"] == pytest.approx(0.1) and a["drops"] == 1 and a["targets_pfr"] == 10 and a["pfr_rec_games"] == 1
    assert a["receiving_epa_per_game"] == pytest.approx(1.5)


def test_zero_or_meaningless_denominators_are_null_never_zero():
    a = ST.aggregate(_two_games(targets=0, receptions=0, receiving_air_yards=-5, team_deep_targets=0, has_pfr_rec=False,
                                pfr_drops=None, target_successes=0)).iloc[0]
    for c in ("receiving_success_rate", "epa_per_target", "racr", "deep_target_share", "deep_target_rate",
              "yards_per_reception", "drop_rate", "drops", "first_downs_per_target", "receiving_td_rate"):
        assert pd.isna(a[c]), c
    # a hand-built frame without the advanced mart's columns: unknown, not zero
    b = ST.aggregate(_two_games().drop(columns=["target_successes", "has_pfr_rec", "pfr_drops"])).iloc[0]
    assert pd.isna(b["receiving_success_rate"]) and pd.isna(b["drop_rate"])


def test_quarterback_rates():
    q = _two_games(position="QB", targets=0, attempts=30, completions=20, passing_yards=250, passing_tds=2,
                   passing_interceptions=1, sacks_suffered=2, dropbacks=34, dropback_successes=17, dropback_epa=3.4)
    a = ST.aggregate(q).iloc[0]
    assert a["adjusted_yards_per_attempt"] == pytest.approx(round((500 + 20 * 4 - 45 * 2) / 60, 2))
    assert a["td_rate"] == pytest.approx(round(4 / 60, 4)) and a["int_rate"] == pytest.approx(round(2 / 60, 4))
    assert a["sack_rate"] == pytest.approx(round(4 / 64, 4))
    assert a["epa_per_dropback"] == pytest.approx(0.1) and a["passing_success_rate"] == pytest.approx(0.5)


def test_points_over_expected_uses_the_same_games_and_the_rushing_share_prices_the_rushing_line():
    g = pd.DataFrame([
        {"gsis_id": "q", "game_id": "g1", "played": True, "position": "QB", "rushing_yards": 50, "rushing_tds": 1,
         "rushing_2pt_conversions": 0, "rush_tds_40p": 0, "rush_tds_50p": 0},
        {"gsis_id": "q", "game_id": "g2", "played": True, "position": "QB", "rushing_yards": 10, "rushing_tds": 0,
         "rushing_2pt_conversions": 0, "rush_tds_40p": 0, "rush_tds_50p": 0}])
    lg = pd.DataFrame([{"gsis_id": "q", "game_id": "g1", "points": 25.0, "points_expected": 20.0, "expected_known": True},
                       {"gsis_id": "q", "game_id": "g2", "points": 10.0, "points_expected": None, "expected_known": False}])
    out = ST.points(lg, g, {"rush_yd": 0.1, "rush_td": 6.0, "pass_yd": 0.04}).iloc[0]
    assert out["points"] == 35.0 and out["expected_points"] == 20.0
    assert out["points_over_expected"] == pytest.approx(5.0)                   # game 1 only: 25 − 20, not 35 − 20
    assert out["points_over_expected_per_game"] == pytest.approx(5.0) and out["games_with_expected"] == 1
    assert out["rushing_points"] == pytest.approx(12.0)                        # 50 x 0.1 + 6, then 10 x 0.1
    assert out["rushing_points_share"] == pytest.approx(round(12 / 35, 4))
    # without the league's scoring there is no rushing share: unknown, not zero; nor with one the pricer cannot read
    assert pd.isna(ST.points(lg, g).iloc[0]["rushing_points_share"])
    odd = ST.points(lg, g, {"rush_yd": "not a number"}).iloc[0]
    assert pd.isna(odd["rushing_points_share"]) and pd.isna(odd["rushing_points"]) and odd["points"] == 35.0


def test_csv_cells_keep_unknown_empty_and_disarm_formulas():
    assert ST._csv_cell(None) == "" and ST._csv_cell(float("nan")) == ""
    assert ST._csv_cell(0) == "0" and ST._csv_cell(-0.45) == "-0.45" and ST._csv_cell(0.8300000000000001) == "0.83"
    assert ST._csv_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and ST._csv_cell("@x") == "'@x"
    assert ST._csv_cell('Smith, "Jr"') == '"Smith, ""Jr"""'


# ------------------------------------------------------------------------------------------------- the clone
@needs_db
def test_the_two_empty_columns_fill_for_2026_with_the_mart_built(client, sql):
    """Andrew's WR / TE preset: separation and YAC over expected. With mart_player_ngs_week built, the top 40 receivers
    by targets all have both; every receiver NGS published a week for has them; the others have none (NGS's 5-target
    qualification), shown as — with the reason, never 0."""
    d = _get(client, window="season", season=2026, position="WR,TE", min_games=1, limit=1000)
    cat = {c["id"]: c for c in d["catalogue"]}
    assert cat["separation"]["available"] and cat["yac_over_expected"]["available"]
    rows = pd.DataFrame(d["players"])
    top = rows.sort_values(["targets", "player_name"], ascending=[False, True]).head(40)
    assert int(top["separation"].notna().sum()) == 40 and int(top["yac_over_expected"].notna().sum()) == 40
    published = {r["gsis_id"] for r in sql("""select distinct gsis_id from analytics.mart_player_ngs_week
                                              where season = 2026 and week between 1 and 18 and has_receiving""")}
    has = set(rows.loc[rows["separation"].notna(), "gsis_id"])
    assert has == published & set(rows["gsis_id"])
    none = rows[~rows["gsis_id"].isin(published)]
    assert len(none) and none["separation"].isna().all() and (none["ngs_rec_weeks"] == 0).all()
    # why the others have none: no week with 5+ targets (NGS's count) in the window
    assert none["targets"].max() <= 4 * none["games"].max()


@needs_db
def test_the_new_columns_reconcile_with_sql_over_the_marts(client, sql):
    d = _get(client, window="season", season=2026, position="WR,TE", min_games=1, limit=1000)
    rows = {p["gsis_id"]: p for p in d["players"]}
    ref = sql("""select f.gsis_id, sum(f.targets) as targets, sum(a.target_successes) as succ, sum(f.receiving_epa) as epa,
                        sum(f.deep_targets) as deep, sum(a.team_deep_targets) filter (where f.played) as team_deep,
                        sum(a.pfr_drops) as drops, sum(f.targets) filter (where a.has_pfr_rec) as targets_pfr
                 from analytics.fct_player_game f
                 left join analytics.mart_player_game_advanced a using (gsis_id, game_id)
                 where f.season = 2026 and f.season_type = 'REG' and f.position in ('WR', 'TE')
                 group by 1 having sum(f.targets) >= 10""")
    checked = 0
    for r in map(_num, ref):
        p = rows.get(r["gsis_id"])
        if p is None or p["position"] not in ("WR", "TE"):
            continue
        assert p["receiving_success_rate"] == pytest.approx(r["succ"] / r["targets"], abs=1e-4), p["player_name"]
        assert p["epa_per_target"] == pytest.approx(round(float(r["epa"]) / r["targets"], 3), abs=0.002)
        if r["team_deep"]:
            assert p["deep_target_share"] == pytest.approx(r["deep"] / r["team_deep"], abs=1e-4)
        if r["targets_pfr"]:
            assert p["drop_rate"] == pytest.approx(r["drops"] / r["targets_pfr"], abs=1e-4)
        checked += 1
    assert checked >= 100


@needs_db
def test_quarterbacks_on_the_clone(client, sql):
    d = _get(client, window="season", season=2026, position="QB", min_games=1, limit=1000)
    rows = {p["gsis_id"]: p for p in d["players"]}
    assert "targets" not in d["players"][0]                                       # receiving columns: not a QB's
    ref = sql("""select f.gsis_id, sum(f.dropbacks) as db, sum(a.dropback_epa) as epa, sum(a.dropback_successes) as succ,
                        sum(a.pfr_times_pressured) as press, sum(f.dropbacks) filter (where a.has_pfr_pass) as db_pfr
                 from analytics.fct_player_game f join analytics.mart_player_game_advanced a using (gsis_id, game_id)
                 where f.season = 2026 and f.season_type = 'REG' and f.position = 'QB'
                 group by 1 having sum(f.dropbacks) >= 30""")
    assert len(ref) >= 25
    for r in map(_num, ref):
        p = rows[r["gsis_id"]]
        assert p["epa_per_dropback"] == pytest.approx(round(float(r["epa"]) / r["db"], 3), abs=0.002), p["player_name"]
        assert p["passing_success_rate"] == pytest.approx(r["succ"] / r["db"], abs=1e-4)
        if r["db_pfr"]:
            assert p["pressure_rate"] == pytest.approx(r["press"] / r["db_pfr"], abs=1e-4)
    shares = [p for p in d["players"] if p["rushing_points_share"] is not None]
    assert len(shares) >= 40
    for p in shares:                 # signed: a passer with negative passing points has a share above 100%
        assert p["points"] > 0 and p["rushing_points_share"] == pytest.approx(p["rushing_points"] / p["points"], abs=1e-4)
    assert all(p["rushing_points_share"] is None for p in d["players"] if (p["points"] or 0) <= 0)


@needs_db
def test_a_week_window_reads_only_its_weeks(client, sql):
    d = _get(client, window="weeks", weeks="2-2", season=2026, position="RB", min_games=1, limit=1000)
    ref = {r["gsis_id"]: r for r in sql("""select f.gsis_id, f.carries, a.carry_successes from analytics.fct_player_game f
                                            join analytics.mart_player_game_advanced a using (gsis_id, game_id)
                                            where f.season = 2026 and f.week = 2 and f.position = 'RB' and f.carries > 0""")}
    hits = [p for p in d["players"] if p["gsis_id"] in ref]
    assert len(hits) >= 30
    for p in hits:
        r = _num(ref[p["gsis_id"]])
        assert p["rushing_success_rate"] == pytest.approx(r["carry_successes"] / r["carries"], abs=1e-4)


@needs_db
def test_before_the_nightly_builds_the_mart_the_columns_say_why(client, monkeypatch):
    """The hosted copy before the first nightly: no mart_player_game_advanced — every column it feeds is — with the
    reason, the catalogue marks them unavailable, nothing fails."""
    real = ST.missing_relations
    monkeypatch.setattr(ST, "missing_relations", lambda rels: [r for r in rels if r == ST.ADV_REL] or real(rels))
    ST.clear()
    try:
        d = _get(client, window="season", season=2026, position="WR,TE", min_games=1, limit=1000)
    finally:
        ST.clear()
    cat = {c["id"]: c for c in d["catalogue"]}
    for cid in ("receiving_success_rate", "deep_target_share", "drop_rate", "broken_tackles"):
        assert not cat[cid]["available"] and cat[cid]["reason"] == ST.ADV_NOT_BUILT, cid
        assert all(p[cid] is None for p in d["players"]), cid
    assert cat["epa_per_target"]["available"]                                   # fct_player_game's own columns stay
    full = next(p for p in d["presets"] if p["key"] == "wrte")["full"]
    assert "drop_rate" not in full and "epa_per_target" in full


def _pfr_rows_unmapped() -> list[dict]:
    """The newest season's PFR rows without a mapped gsis id — read as the pipeline role (raw is not the app role's)."""
    import psycopg
    from league_lab.config import get_settings
    q = """with r as (select pfr_player_id, game_id, season from raw.nfl_pfr_advstats_rec
                      union all select pfr_player_id, game_id, season from raw.nfl_pfr_advstats_rush
                      union all select pfr_player_id, game_id, season from raw.nfl_pfr_advstats_pass)
           select count(*) as n, count(*) filter (where m.gsis_id is null) as unmapped
           from r left join analytics.player_id_map m on m.pfr_id = r.pfr_player_id
           where r.season = (select max(season) from r)"""
    with psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=5) as conn, \
            conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(q)
        return cur.fetchall()


@needs_db
def test_pfr_rows_join_by_id_and_the_unmapped_are_counted(sql):
    try:
        r = _pfr_rows_unmapped()[0]
    except Exception as exc:  # noqa: BLE001 - the pipeline role is a developer's; CI has only the app role
        pytest.skip(f"pipeline role not reachable: {exc}")
    assert r["n"] > 1000 and r["unmapped"] <= 25, r                                  # the clone: 7 of 1,290 (3 players)
    mart = sql("""select count(*) filter (where has_pfr_rec) as rec, count(*) filter (where has_pfr_rush) as rush,
                         count(*) filter (where has_pfr_pass) as pass
                  from analytics.mart_player_game_advanced where season = 2026""")[0]
    assert mart["rec"] + mart["rush"] + mart["pass"] <= r["n"] - r["unmapped"]


# ------------------------------------------------------------------------------------------------- the CSV
@needs_db
def test_players_csv_is_the_same_frame_with_a_header_of_labels(client):
    q = {"league": SCRUBS, "window": "season", "season": 2026, "position": "WR,TE", "min_games": 1}
    frame = _get(client, **q, limit=1000)
    r = client.get("/api/players.csv?" + urlencode({**q, "view": "full"}))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="isuckatfantasy-stats-2026-wr-te-season-weeks-1-4.csv"' in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    cat = {c["id"]: c for c in frame["catalogue"]}
    full = next(p for p in frame["presets"] if p["key"] == "wrte")["full"]
    assert rows[0][:5] == ["Player", "Position", "NFL team", "Rostered by", "Games played"]
    assert rows[0][5:] == [cat[c]["label"] for c in full if c != "games"]
    assert len(rows) - 1 == frame["total"]
    first = dict(zip(rows[0], rows[1], strict=True))
    p0 = frame["players"][0]
    assert first["Player"] == p0["player_name"] and first["Targets"] == str(p0["targets"])
    # unknown stays an empty cell (routes in season), never 0
    if "Routes run" in rows[0]:
        assert all(r_[rows[0].index("Routes run")] == "" for r_ in rows[1:])
    # key stats + per game; cols=; an unknown column is refused in words
    k = list(csv.reader(io.StringIO(client.get("/api/players.csv?" + urlencode({**q, "per_game": 1})).text)))
    assert "Targets per game" in k[0] and len(k[0]) == 5 + len(next(p for p in frame["presets"]
                                                                       if p["key"] == "wrte")["columns"]) - 1
    c = client.get("/api/players.csv?" + urlencode({**q, "cols": "targets,adot"})).text.splitlines()[0]
    assert c.endswith("Targets,Average depth of target")
    bad = client.get("/api/players.csv?" + urlencode({**q, "cols": "targets,nope"}))
    assert bad.status_code == 400 and "nope" in bad.json()["error"]
