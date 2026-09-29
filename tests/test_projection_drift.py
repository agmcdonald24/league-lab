"""M-06 drift monitor: the live board's played weeks scored like the backtest (no database needed)."""

import re
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from league_lab import db, projections
from league_lab.projections import DRIFT_COLUMNS, score_drift

ROOT = Path(__file__).resolve().parents[1]


def _rows(week, game, position, proj, actual, played=True, rankable=True, spread=5.0):
    return [{"league_id": "L1", "season": 2026, "week": week, "position": position, "gsis_id": f"{position}{week}{game}{i}",
             "game_id": game, "played": played, "is_rankable": rankable,
             # the mart returns numeric columns as Decimal: score_drift must coerce them
             "proj_points": Decimal(str(p)), "p10": Decimal(str(p - spread)), "p90": Decimal(str(p + spread)),
             "points_actual": None if a is None else Decimal(str(a)), "model_version": "v2.0"}
            for i, (p, a) in enumerate(zip(proj, actual, strict=True))]


def _board() -> pd.DataFrame:
    proj = list(range(1, 21))
    rows = []
    # week 1, both games in: 20 QBs ranked perfectly, plus a player who is not rankable (Out, played anyway)
    # and one who did not play; neither may count
    rows += _rows(1, "G1", "QB", proj[:10], proj[:10]) + _rows(1, "G2", "QB", proj[10:], proj[10:])
    rows += _rows(1, "G2", "QB", [50.0], [0.0], rankable=False)
    rows += _rows(1, "G1", "QB", [30.0], [None], played=False)
    # week 2, one of two games in: the order is exactly reversed; 5 TEs is below the 8-player minimum
    rows += _rows(2, "G3", "QB", proj, [21 - p for p in proj])
    rows += _rows(2, "G4", "QB", [5.0] * 5, [None] * 5, played=False)
    rows += _rows(2, "G3", "TE", [1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    return pd.DataFrame(rows)


def test_score_drift_matches_hand_computed_values():
    res = score_drift(_board()).set_index(["week", "position"])
    assert list(res.reset_index().columns) == ["week", "position", *[c for c in DRIFT_COLUMNS if c not in ("week", "position")]]
    assert set(res.index) == {(1, "QB"), (2, "QB")}          # TE week 2: 5 players < 8, skipped like the backtest

    w1 = res.loc[(1, "QB")]
    assert w1["n_players"] == 20                              # not rankable / not played are out
    assert w1["spearman"] == pytest.approx(1.0)
    assert w1["hit_rate"] == pytest.approx(1.0)
    assert w1["top_n"] == 12
    assert w1["mae"] == pytest.approx(0.0)
    assert w1["coverage_80"] == pytest.approx(1.0)
    assert w1["interval_width"] == pytest.approx(10.0)
    assert (w1["games_played"], w1["games_scheduled"]) == (2, 2)
    assert w1["model_version"] == "v2.0"

    w2 = res.loc[(2, "QB")]
    assert w2["spearman"] == pytest.approx(-1.0)
    assert w2["hit_rate"] == pytest.approx(4 / 12)            # projected top 12 = proj 9..20, actual top 12 = proj 1..12
    assert w2["mae"] == pytest.approx(10.0)                   # mean |2p - 21| over p = 1..20
    assert w2["coverage_80"] == pytest.approx(0.3)            # |2p - 21| <= 5 for p = 8..13
    assert (w2["games_played"], w2["games_scheduled"]) == (1, 2)   # a week still being played is visible as such


def test_score_drift_spearman_equals_scipy_on_a_noisy_week():
    stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(0)
    proj = np.round(rng.gamma(3, 3, 40), 2)
    actual = np.round(np.clip(proj + rng.normal(0, 5, 40), 0, None), 2)   # ties at 0, like real weeks
    board = pd.DataFrame(_rows(3, "G9", "WR", proj.tolist(), actual.tolist()))
    r = score_drift(board).iloc[0]
    assert r["spearman"] == pytest.approx(stats.spearmanr(proj, actual).statistic)
    assert r["mae"] == pytest.approx(np.abs(proj - actual).mean())
    assert r["top_n"] == 24


def test_score_drift_before_any_game_is_empty_with_the_table_columns():
    assert list(score_drift(pd.DataFrame()).columns) == DRIFT_COLUMNS
    unplayed = pd.DataFrame(_rows(1, "G1", "WR", list(range(1, 13)), [None] * 12, played=False))
    out = score_drift(unplayed)
    assert out.empty and list(out.columns) == DRIFT_COLUMNS


def _ddl_columns(text: str) -> list[str]:
    body = re.search(r"create table if not exists ops\.projection_drift \((.*?)\)\s*(;|\"|$)", text, re.S).group(1)
    return [part.split()[0] for part in body.replace("\n", " ").split(",")]


def test_drift_ddl_is_the_same_everywhere():
    """Three copies of the DDL (migration, the writer's DDL dict, the dbt view's pre_hook) must agree,
    and every column score_drift produces must land in the table (_write drops unknown columns)."""
    cols = _ddl_columns(db.OPS_DDL)
    assert cols == _ddl_columns(projections.DDL["ops.projection_drift"])
    assert cols == _ddl_columns((ROOT / "dbt/models/marts/nfl/mart_projection_drift.sql").read_text())
    assert set(cols) == {*DRIFT_COLUMNS, "run_at"}
