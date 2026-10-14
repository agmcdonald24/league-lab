"""JB-1 (Wave J-B): gp1.0's candidate switch — the back flag, the fitted factor, the knot; unset, nothing moves."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from league_lab import gp_fix


def frame() -> pd.DataFrame:
    # A (BUF): plays w1, misses w2, plays w3 (back), plays w4; B (BUF) plays every week; C (MIA): w1 played, w2 not yet
    # played by anyone of MIA (a game still to come), w3 a row: unknown
    rows = [("A", 1, "BUF", True), ("A", 2, "BUF", False), ("A", 3, "BUF", True), ("A", 4, "BUF", True),
            ("B", 1, "BUF", True), ("B", 2, "BUF", True), ("B", 3, "BUF", True), ("B", 4, "BUF", True),
            ("C", 1, "MIA", True), ("C", 2, "MIA", False), ("C", 3, "MIA", False)]
    return pd.DataFrame([{"gsis_id": g, "season": 2024, "week": w, "team": t, "played": p} for g, w, t, p in rows]).sample(
        frac=1.0, random_state=1)


def test_the_back_flag():
    f = frame()
    got = dict(zip(zip(f["gsis_id"], f["week"], strict=True), gp_fix.back_flags(f), strict=True))
    assert np.isnan(got[("A", 1)]) and got[("A", 2)] == 0.0 and got[("A", 3)] == 1.0 and got[("A", 4)] == 0.0
    assert got[("B", 3)] == 0.0
    assert got[("C", 2)] == 0.0 and np.isnan(got[("C", 3)])        # MIA's week 2 has not been played by anyone


def test_off_changes_nothing_and_unset_is_the_shipped_candidate(monkeypatch):
    from league_lab import projections as P
    monkeypatch.setattr(P, "GP_MODE", None)          # a process started with the switch off
    monkeypatch.setenv(gp_fix.FLAG, "off")
    f = frame()
    assert gp_fix.mode() is None and gp_fix.add_feature(f) is f
    every = pd.DataFrame({"league_id": ["x"], "gsis_id": ["A"], "week": [3]})
    assert gp_fix.apply(None, 2024, every, {}, f, f, {}, {}) is every
    monkeypatch.setenv(gp_fix.FLAG, "something else")
    assert gp_fix.mode() is None
    monkeypatch.delenv(gp_fix.FLAG, raising=False)
    assert gp_fix.mode() == gp_fix.SHIPPED == "back_feature"             # fx1.0 (v3.8)
    assert gp_fix.apply(None, 2024, every, {}, f, f, {}, {}) is every     # C1 is an input, not a scale


def test_the_shipped_model_reads_the_input():
    from league_lab import projections as P
    on = P.GP_MODE == "back_feature"                                    # the switch as the process imported it
    assert (gp_fix.BACK_FEATURE in P.FEATURES_BY_POSITION["RB"]) == on
    assert gp_fix.BACK_FEATURE not in P.FEATURES_BY_POSITION["QB"] and gp_fix.BACK_FEATURE not in P.ALL_FEATURES
    assert P.MODEL_VERSION == "v3.8"


def test_the_feature_when_set(monkeypatch):
    from league_lab import projections as P
    monkeypatch.setattr(P, "GP_MODE", None)
    monkeypatch.setenv(gp_fix.FLAG, "back_feature")
    out = gp_fix.add_feature(frame())
    assert gp_fix.BACK_FEATURE in out and out.loc[(out["gsis_id"] == "A") & (out["week"] == 3), gp_fix.BACK_FEATURE].item() == 1.0


def test_the_factor_minimises_the_absolute_error():
    rng = np.random.default_rng(0)
    proj = rng.uniform(2, 12, 400)
    actual = 0.8 * proj
    assert gp_fix.best_k(proj, actual) == pytest.approx(0.80)
    assert gp_fix.best_k(proj[:50], actual[:50]) == 1.0                # under the minimum rows
    assert gp_fix.best_k(proj, proj * 5) == 1.20                       # bounded


def test_the_knot_is_the_median_36th_projection():
    oof = pd.DataFrame([{"season": 2023, "week": w, "proj_points": float(p)} for w in (1, 2, 3) for p in range(40 + w)])
    # week w: projections 0 .. 39 + w; the 36th highest is 39 + w - 35 = 4 + w -> 5, 6, 7; the median 6
    assert gp_fix.knot(oof) == 6.0
    assert gp_fix.knot(oof[oof["proj_points"] < 30]) is None           # no week with 36 rows
