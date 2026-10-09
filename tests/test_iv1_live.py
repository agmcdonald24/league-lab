"""IV-1 (Wave I-V): fr1.1, the live week switched on. league_lab.live_week is the one place a reader's SQL becomes live
(the stored rows without an overlay row, plus the overlay's rows); an absent or empty overlay leaves the SQL unchanged;
every stored table a live reader reads has an overlay of its shape; the NFL-wide live rows are gated. No database."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from league_lab import anyleague as A
from league_lab import availability_gate as AG
from league_lab import live_week as LW
from league_lab import projections as P

ALL = frozenset(LW.OVERLAYS)


def test_no_overlay_means_the_sql_unchanged_character_for_character():
    for name in dir(A):
        q = getattr(A, name)
        if name.endswith("_SQL") and isinstance(q, str):
            assert LW.sql(q, frozenset()) == q and LW.sql(q, None) == q
    assert LW.sql("select 1 from analytics.mart_player_week_projections", ALL) == "select 1 from analytics.mart_player_week_projections"


@pytest.mark.parametrize("text, alias", [
    ("select p.proj_points from ops.projections as p where p.week = 5", " as p"),
    ("select p.proj_points from ops.projections p where p.week = 5", " p"),
    ("select proj_points from ops.projections where week = 5", " as projections"),
    ("select proj_points from ops.projections\n   where week = 5", " as projections"),
    ("select x from a join ops.projection_ranges r on r.gsis_id = a.gsis_id", " r"),
    ("select * from (select distinct on (unit_id) * from ops.kd_lines where week = 5 order by unit_id) as l", " as kd_lines"),
])
def test_every_from_and_join_of_a_stored_table_reads_the_overlay_first(text, alias):
    out = LW.sql(text, ALL)
    table = next(t for t in LW.OVERLAYS if f"{t} " in text or f"{t}\n" in text)
    assert LW.relation(table) + alias in out
    assert out.count("jsonb_populate_record") == 1


def test_only_active_overlays_and_never_the_overlay_tables_themselves():
    q = "select * from ops.projection_lines as l join ops.projection_ranges as r using (gsis_id)"
    out = LW.sql(q, {"ops.projection_ranges"})
    assert "from ops.projection_lines as l" in out and LW.relation("ops.projection_ranges") in out
    for live in LW.LIVE_TABLES:                              # an overlay is never rewritten into itself
        assert LW.sql(f"select * from {live}", ALL) == f"select * from {live}"
    assert LW.sql("select * from ops.projections_backup", ALL) == "select * from ops.projections_backup"


def test_the_relation_replaces_by_the_tables_key_and_casts_to_its_own_columns():
    r = LW.relation("ops.projection_ranges")
    assert "v.scoring_name = s.scoring_name and v.season = s.season and v.week = s.week and v.gsis_id = s.gsis_id" in r
    assert "jsonb_populate_record(null::ops.projection_ranges, to_jsonb(v))" in r and "union all" in r


def test_active_reads_which_overlays_exist_and_hold_rows():
    calls = []

    def execute(q):
        calls.append(q)
        if q.startswith("select to_regclass") or "to_regclass" in q:
            return (False, True, True, False, True)
        return {"h0": True, "h1": False, "h2": True}           # a dict row (the API's row factory) works too
    got = LW.active(execute)
    assert got == {"ops.projection_lines", "ops.kd_ranges"} and len(calls) == 2
    assert LW.active(lambda q: (False,) * 5) == frozenset()


def test_every_live_table_has_an_overlay_of_its_shape_that_migrate_creates():
    assert set(LW.LIVE_TABLES) <= set(P.NFL_DDL)                  # db.migrate runs every NFL_DDL statement
    for base, (live, keys) in LW.OVERLAYS.items():
        if base == "ops.projections":
            continue
        ddl = P.NFL_DDL[live]
        assert f"create table if not exists {live} (like {base})" in ddl and "game_kickoff" in ddl
        assert f"({', '.join(keys)})" in ddl                       # the key's index
    order = list(P.NFL_DDL)
    for base, (live, _) in LW.OVERLAYS.items():
        if base in order:
            assert order.index(base) < order.index(live)           # `like` needs the stored table first


SUN = datetime(2026, 10, 11, 17, 0, tzinfo=UTC)
TEAMS = pd.DataFrame({"team": ["BAL", "ATL"], "game_kickoff": [SUN, SUN]})


def _lines():
    rows = []
    for g, pos, team in (("lamar", "QB", "BAL"), ("huntley", "QB", "BAL"), ("flowers", "WR", "BAL"), ("dal_wr", "WR", "DAL")):
        rows.append({"model_version": "v3.6", "fitted_at": SUN, "train_seasons": "2016-2025", "season": 2026, "week": 5,
                     "gsis_id": g, "position": pos, **{f"proj_{c}": 10.0 for c in P.ALL_COMPONENTS}})
        rows.append({**rows[-1], "week": 6})
    return pd.DataFrame(rows)


def test_nfl_wide_live_rows_are_the_unplayed_games_of_the_week_gated():
    lines = _lines()
    ranges = lines[["season", "week", "gsis_id", "position", "model_version", "fitted_at"]].assign(
        scoring_name="half", proj_points=12.0, p10=4.0, p25=8.0, p50=12.0, p75=16.0, p90=20.0)
    pt = pd.DataFrame({"position": ["QB", "QB", "WR", "WR"], "gsis_id": ["lamar", "huntley", "flowers", "dal_wr"],
                       "team": ["BAL", "BAL", "BAL", "DAL"]})
    kt = pd.DataFrame(columns=["position", "gsis_id", "team"])
    out_ = AG.classify(AG.entry("OUT", "Sleeper", as_of=datetime(2026, 10, 9, 15, tzinfo=UTC), note="Ankle"))
    got = P.nfl_live_rows({"lines": lines, "ranges": ranges}, 5, TEAMS, pt, kt, {"lamar": out_})
    ln, rg = got["ops.projection_lines_live"], got["ops.projection_ranges_live"]
    assert set(ln["gsis_id"]) == {"lamar", "huntley", "flowers"} and set(ln["week"]) == {5}   # not DAL (kicked off)
    lamar = ln[ln["gsis_id"] == "lamar"].iloc[0]
    assert lamar["proj_passing_yards"] == 0 and isinstance(lamar["availability"], str)
    assert (rg.loc[rg["gsis_id"] == "lamar", ["proj_points", "p10", "p90"]] == 0).all().all()
    assert (rg.loc[rg["gsis_id"] == "huntley", "proj_points"] == 12.0).all()
    assert ln["frozen_source"].isna().all() and set(ln["game_kickoff"]) == {SUN}
    assert P.nfl_live_rows({"lines": lines}, 5, TEAMS.iloc[0:0], pt, kt, {}) == {}
