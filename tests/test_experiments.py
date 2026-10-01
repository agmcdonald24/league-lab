"""Plan D1: the feature-group harness — decision rule, registry validation, no-peek check."""

from __future__ import annotations

import pandas as pd
import pytest

from league_lab import experiments as E
from league_lab import projections as P


def _seasons(pos: str, ds: list[float], dm: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"position": pos, "test_season": [2023, 2024, 2025][: len(ds)], "delta_spearman": ds, "delta_mae": dm})


# ------------------------------------------------------------------------------ the decision rule
def test_keep_on_spearman_when_consistent():
    d = E.decide(_seasons("WR", [0.010, 0.004, -0.001], [0.0, 0.0, 0.0])).iloc[0]
    assert d.delta_spearman == pytest.approx(0.013 / 3)   # 0.00433 < 0.005: not enough on average
    assert d.decision == "drop"
    d = E.decide(_seasons("WR", [0.012, 0.006, -0.001], [0.0, 0.0, 0.0])).iloc[0]
    assert d.seasons_better_spearman == 2 and d.delta_spearman >= E.KEEP_SPEARMAN
    assert d.decision == "keep" and d.helps and not d.hurts


def test_big_mean_from_one_season_is_not_enough():
    # +0.03 mean, but driven by one season: better in 1 of 3 -> drop
    d = E.decide(_seasons("RB", [0.10, -0.005, -0.005], [0.0, 0.0, 0.0])).iloc[0]
    assert d.delta_spearman > E.KEEP_SPEARMAN and d.seasons_better_spearman == 1
    assert d.decision == "drop"


def test_keep_on_mae_alone():
    d = E.decide(_seasons("TE", [0.0, 0.0, 0.0], [-0.10, -0.07, 0.01])).iloc[0]
    assert d.delta_mae <= E.KEEP_MAE and d.seasons_better_mae == 2
    assert d.decision == "keep"


def test_hurts_and_mixed():
    hurt = E.decide(_seasons("QB", [-0.01, -0.02, 0.001], [0.0, 0.0, 0.0])).iloc[0]
    assert hurt.hurts and not hurt.helps and hurt.decision == "drop"
    both = E.decide(_seasons("QB", [0.01, 0.01, 0.01], [0.06, 0.07, 0.08])).iloc[0]   # better order, bigger miss
    assert both.helps and both.hurts and both.decision == "mixed"


def test_group_verdict_across_positions():
    dec = E.decide(pd.concat([_seasons("WR", [0.01, 0.01, 0.0], [0, 0, 0]), _seasons("TE", [-0.01, -0.01, 0.0], [0, 0, 0]),
                              _seasons("QB", [0.0, 0.0, 0.0], [0, 0, 0])]))
    assert dict(zip(dec["position"], dec["decision"], strict=True)) == {"WR": "keep", "TE": "drop", "QB": "drop"}
    assert E.group_verdict(dec) == "mixed"                    # helps WR, hurts TE: the PO decides per position
    assert E.group_verdict(dec[dec["position"] != "TE"]) == "keep"
    assert E.group_verdict(dec[dec["position"] == "QB"]) == "drop"


def test_seasons_needed():
    assert [E.seasons_needed(n) for n in (1, 2, 3, 4, 5)] == [1, 2, 2, 3, 4]


# ------------------------------------------------------------------------------ registry validation
COLS = {"gsis_id": "text", "season": "integer", "week": "integer", "gc_rest_days": "integer", "gc_dome": "boolean",
        "gc_label": "text"}


def test_registry_entries_are_well_formed():
    reg = E.load_registry()
    for name, spec in reg.items():
        cols = {"gsis_id": "text", "season": "integer", "week": "integer", **{c: "double precision" for c in spec["columns"]}}
        g = E.check_spec(name, spec, cols)
        assert g.table == spec["table"] and g.columns == list(spec["columns"])


def test_missing_table_is_a_clear_error():
    with pytest.raises(E.GroupError, match=r"table intermediate\.int_nope does not exist .*dbt build"):
        E.check_spec("nope", {"table": "intermediate.int_nope", "columns": ["gc_rest_days"]}, None)


def test_missing_columns_are_named():
    with pytest.raises(E.GroupError, match=r"has no columns \['gc_travel_tz'\]"):
        E.check_spec("gc", {"table": "intermediate.x", "columns": ["gc_rest_days", "gc_travel_tz"]}, COLS)


@pytest.mark.parametrize(("spec", "msg"), [
    ({"columns": ["gc_rest_days"]}, "'table' is required"),
    ({"table": "x", "columns": ["gc_rest_days"]}, "schema.table"),
    ({"table": "s.x", "columns": ["gc_rest_days", "gc_rest_days"]}, "duplicate columns"),
    ({"table": "s.x", "columns": ["implied_team_total"]}, "already model inputs"),
    ({"table": "s.x", "columns": ["gc_rest_days"], "positions": ["K"]}, "unknown positions"),
    ({"table": "s.x", "columns": ["gc_rest_days"], "in_season": ["gc_other"]}, "in_season columns"),
    ({"table": "s.x", "columns": ["gc_label"]}, "numeric or boolean"),
])
def test_malformed_specs(spec, msg):
    with pytest.raises(E.GroupError, match=msg):
        E.check_spec("g", spec, COLS)


def test_baseline_name_is_reserved_and_valid_spec_passes():
    with pytest.raises(E.GroupError, match="reserved"):
        E.check_spec("baseline", {"table": "s.x", "columns": ["gc_rest_days"]}, COLS)
    g = E.check_spec("gc", {"table": "s.x", "columns": ["gc_rest_days", "gc_dome"], "positions": ["WR"]}, COLS)
    assert g.positions == ("WR",) and g.label == "gc"


# ------------------------------------------------------------------------------ the no-peek check
def test_probe_judges_a_leak_and_passes_a_pre_game_input():
    probe = pd.DataFrame([
        {"position": "WR", "column": "x_leak", "n": 18000, "r_same": 0.90, "r_prev": 0.38, "r_next": 0.37},       # the game's own yards
        {"position": "QB", "column": "x_vegas", "n": 4800, "r_same": 0.30, "r_prev": 0.26, "r_next": 0.25},       # week-specific, pre-game
        {"position": "RB", "column": "x_form", "n": 11000, "r_same": 0.57, "r_prev": 0.70, "r_next": 0.54},       # season-to-date form
        {"position": "TE", "column": "x_small", "n": 100, "r_same": 1.0, "r_prev": 0.0, "r_next": 0.0},           # too few rows to judge
    ])
    out = E.judge_probe(probe)
    assert len(out) == 1 and out[0].startswith("x_leak (WR)")


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from league_lab.config import get_settings

    try:
        c = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=3, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    with c:
        if not c.execute("select to_regclass('analytics.mart_player_week_features')").fetchone()[0]:
            pytest.skip("mart_player_week_features not built")
        yield c


def test_no_peek_check_catches_planted_leaks(conn):
    """A temp table at the contract grain: an honest input, the week's own points (planted leak), an as-of
    marker that peeks one week ahead, and an 'in-season' input filled in week 1."""
    conn.execute("drop table if exists pg_temp.d1_planted")
    conn.execute("""create temp table d1_planted as
        select u.gsis_id, u.season, u.week,
               (u.week % 3)::float8 as pl_honest,
               u.week % 2 = 0 as pl_honest_flag,
               m.points_actual as pl_leak,
               u.week as pl_asof_week,
               1.0::float8 as pl_form
        from intermediate.int_player_week_universe as u
        left join analytics.mart_player_week_features as m using (gsis_id, season, week)
        where u.season >= 2023""")
    honest = E.check_spec("honest", {"table": "pg_temp.d1_planted", "columns": ["pl_honest", "pl_honest_flag"]},
                          E.describe_table(conn, "pg_temp.d1_planted"))
    rep = E.no_peek_check(conn, honest)
    # the planted as-of marker is a column of the table, so the table is refused whichever columns a group uses
    assert any(f.startswith("as-of:") for f in rep.failures)
    conn.execute("alter table pg_temp.d1_planted drop column pl_asof_week")
    rep = E.no_peek_check(conn, honest)
    assert rep.ok, rep.failures
    leak = E.GroupSpec("leak", "pg_temp.d1_planted", ["pl_leak"])
    rep = E.no_peek_check(conn, leak)
    assert not rep.ok and all("pl_leak" in f for f in rep.failures) and len(rep.failures) == 4   # every position
    assert any("serve gap" in w for w in rep.warnings) or rep.warnings == []                     # the newest season may be unplayed
    form = E.GroupSpec("form", "pg_temp.d1_planted", ["pl_form"], in_season=["pl_form"])
    rep = E.no_peek_check(conn, form)
    assert len(rep.failures) == 1 and rep.failures[0].startswith("week 1:")
    with pytest.raises(E.NoPeekError, match="refused by the no-peek check"):
        E.run_experiment(conn, leak, test_seasons=(2025,), write=False)


def test_default_path_unchanged():
    """The harness hooks default to production: no `features` = FEATURES, and a model remembers what it was fitted on."""
    import numpy as np

    d = pd.DataFrame({f: np.arange(3, dtype=float) for f in [*P.FEATURES, "gc_x"]})
    assert np.array_equal(P._matrix(d), P._matrix(d, list(P.FEATURES)))
    assert P._matrix(d, [*P.FEATURES, "gc_x"]).shape == (3, len(P.FEATURES) + 1)
    assert P.PositionModel("WR").features is None
