"""IT-5 (Wave I-T): the role forecast's mixture in the study harness (scripts/analysis/it5_role.py). No database.

The tables in docs/METRICS.md § "v3.7: the role forecast (IT-5)" rest on three properties of the mixture: "the starter
keeps the job" is v3.6's line exactly, the market week (the board and the h = 1 rows) never moves, and the oracle reads
the target week's own listed role (no board row in week T = not the starter)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def it5():
    spec = importlib.util.spec_from_file_location("it5_role", ROOT / "scripts" / "analysis" / "it5_role.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["it5_role"] = mod
    spec.loader.exec_module(mod)
    return mod


def _frame(it5) -> pd.DataFrame:
    """Season 2023: a starter (S) and a backup (B) of one team; board weeks 4-6, horizon rows as of W = 3 (h 1-3).
    In week 6 the backup is the listed starter; in week 5 the starter has no board row (not on the board)."""
    rows = []
    board = [("S", 4, 1.0), ("B", 4, 0.0), ("B", 5, 0.0), ("S", 6, 0.0), ("B", 6, 1.0)]
    for g, w, st in board:
        rows.append({"gsis_id": g, "season": 2023, "week": float(w), "kind": "board", "as_of": np.nan, "h": np.nan,
                     "target_week": float(w), "pn_qb_starting": st})
    for g, st in (("S", 1.0), ("B", 0.0)):
        for h in (1, 2, 3):
            rows.append({"gsis_id": g, "season": 2023, "week": float(3 + h), "kind": "horizon", "as_of": 3.0, "h": float(h),
                         "target_week": float(3 + h), "pn_qb_starting": st})
    d = pd.DataFrame(rows)
    d["player_name"], d["played"] = d["gsis_id"], True
    d["games_to_date"], d["prev_games"] = 3.0, 10.0
    d["naive_lambda"], d["naive_k"] = 0.25, 6.0
    for i, c in enumerate(it5.COMPS):
        d[f"hb0_{c}"] = np.where(d["gsis_id"] == "S", 10.0 + i, 1.0 + 0.1 * i)
        d[f"{c}_pg_std"] = np.where(d["gsis_id"] == "S", 11.0 + i, 0.5)
        d[f"prev_{c}_pg"] = np.where(d["gsis_id"] == "S", 9.0 + i, 2.0)
        d[f"out_{c}"] = 1.0
    return d


def _priors(it5) -> dict:
    return {s: {c: (20.0 + i, 2.0) for i, c in enumerate(it5.COMPS)} for s in it5.TESTS}


def test_role_frame_reads_the_target_week(it5):
    d = _frame(it5)
    hz = it5.role_frame(d)
    assert set(hz["h"]) == {2.0, 3.0}                       # the later weeks only
    got = hz.set_index(["gsis_id", "target_week"])["t_start"].to_dict()
    assert got == {("S", 5.0): False, ("S", 6.0): False, ("B", 5.0): False, ("B", 6.0): True}
    assert hz.set_index(["gsis_id", "target_week"])["mkt_start"].to_dict()[("S", 5.0)]


def test_the_starter_keeps_the_job_is_v36(it5):
    d = _frame(it5)
    hz = it5.role_frame(d)
    keep = pd.Series(np.where(hz["mkt_start"], 1.0, 0.0), index=hz.index)
    out = it5.mix_lines(d.copy(), hz, keep, "keep", _priors(it5))
    for c in it5.COMPS:
        np.testing.assert_allclose(out[f"keep_{c}"], out[f"hb0_{c}"])


def test_the_market_week_never_moves_and_the_mixture_is_per_role(it5):
    d = _frame(it5)
    hz = it5.role_frame(d)
    p = pd.Series(0.25, index=hz.index)
    out = it5.mix_lines(d.copy(), hz, p, "rf", _priors(it5))
    fixed = (out["kind"] == "board") | (out["h"] == 1)
    for c in it5.COMPS:
        np.testing.assert_allclose(out.loc[fixed, f"rf_{c}"], out.loc[fixed, f"hb0_{c}"])
    c, i = it5.COMPS[0], 0
    s_row = out[(out["gsis_id"] == "S") & (out["h"] == 2)].iloc[0]
    assert s_row[f"rf_{c}"] == pytest.approx(0.25 * (10.0 + i) + 0.75 * 2.0)          # his line / a backup's line
    b_row = out[(out["gsis_id"] == "B") & (out["h"] == 2)].iloc[0]
    as_starter = (3 * 0.5 + 0.25 * 10 * 2.0 + 6 * (20.0 + i)) / (3 + 0.25 * 10 + 6)   # B1r with the starters' prior
    assert b_row[f"rf_{c}"] == pytest.approx(0.25 * as_starter + 0.75 * 1.0)


def test_a_season_outside_the_grade_keeps_v36(it5):
    d = _frame(it5)
    d["season"] = 2019                                       # no prior for it: the line is left as v3.6's
    hz = it5.role_frame(d)
    out = it5.mix_lines(d.copy(), hz, pd.Series(0.5, index=hz.index), "rf", _priors(it5))
    for c in it5.COMPS:
        np.testing.assert_allclose(out[f"rf_{c}"], out[f"hb0_{c}"])
