"""Plan U-15: what drives projection v2, in points (projections.component_importance) and in plain words
(projections.FEATURE_LABELS). No database: the component models are stand-ins that read one column each."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from league_lab import projections as P

# League of Scrubs' skill-position keys (half PPR, 4-pt pass TD, no bonuses): the reference scoring.
HALF_PPR = {"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0, "rush_yd": 0.1, "rush_td": 6.0, "pass_yd": 0.04, "pass_td": 4.0,
            "pass_int": -1.0, "fum_lost": -2.0, "bonus_rec_yd_100": 0.0}


# ------------------------------------------------------------------------------ plain names
def test_every_model_input_has_a_plain_name():
    missing = [f for f in P.FEATURES if f not in P.FEATURE_LABELS]
    assert not missing, f"FEATURES without a plain name in FEATURE_LABELS: {missing}"
    labels = [P.FEATURE_LABELS[f] for f in P.FEATURES]
    assert len(set(labels)) == len(labels), "two inputs share a plain name"
    jargon = re.compile(r"_|\bxPPG\b|\bP10\b|\bP90\b|Spearman|z-score|\bmart\b|quantile|gsis|\bstd\b|\bpg\b", re.I)
    bad = {f: lab for f, lab in zip(P.FEATURES, labels, strict=True) if jargon.search(lab) or lab == f}
    assert not bad, f"plain names that are not plain: {bad}"


def test_the_examples_read_as_promised():
    assert P.FEATURE_LABELS["targets_pg_l3"] == "Targets per game, last 3 games"
    assert P.FEATURE_LABELS["snap_pct_std"] == "Snap share, season"
    assert P.FEATURE_LABELS["prev_receiving_yards_pg"] == "Receiving yards per game, last season"


def test_unit_points_reference_scoring():
    w = P.unit_points(HALF_PPR)
    assert w["receptions"] == 0.5 and w["receiving_yards"] == 0.1 and w["receiving_tds"] == 6.0
    assert w["passing_yards"] == 0.04 and w["passing_interceptions"] == -1.0 and w["fumbles_lost_total"] == -2.0
    assert w["targets"] == 0.0 and w["carries"] == 0.0 and w["attempts"] == 0.0   # volume is not scored, only what it produces
    assert set(w) == set(P.ALL_COMPONENTS)


# ------------------------------------------------------------------------------ importance on a fixture
class OneColumn:
    """A stand-in component model: a + b x (one feature column)."""

    def __init__(self, feature: str | None, a: float, b: float = 0.0):
        self.j = P.FEATURES.index(feature) if feature else None
        self.a, self.b = a, b

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.full(len(x), self.a) if self.j is None else self.a + self.b * np.nan_to_num(x[:, self.j])


@pytest.fixture()
def fixture_rows() -> pd.DataFrame:
    """300 played TE weeks + 20 rows the importance must ignore (not played / no history / no outcome)."""
    rng = np.random.default_rng(7)
    n = 320
    df = pd.DataFrame({f: rng.normal(1.0, 0.3, n) for f in P.FEATURES})
    df["week"] = 5.0                                 # constant: scrambling it changes nothing
    df["targets_pg_l3"] = rng.uniform(2, 10, n)       # drives targets only (0 points per target)
    df["receiving_yards_pg_std"] = rng.uniform(10, 80, n)   # drives receiving yards (0.1 points per yard)
    df["position"], df["played"], df["no_history"] = "TE", True, False
    df["out_targets"] = df["targets_pg_l3"] + rng.normal(0, 1, n)
    df["out_receptions"] = 3.0 + rng.normal(0, 1, n)
    df["out_receiving_yards"] = df["receiving_yards_pg_std"] + rng.normal(0, 8, n)
    df["out_receiving_tds"] = rng.binomial(1, 0.3, n).astype(float)
    df["out_fumbles_lost_total"] = 0.0
    for c in P.ALL_COMPONENTS:
        if f"out_{c}" not in df:
            df[f"out_{c}"] = 0.0
    df.loc[300:305, "played"] = False
    df.loc[306:312, "no_history"] = True
    df.loc[313:319, "out_receiving_yards"] = np.nan
    return df


@pytest.fixture()
def te_model() -> P.PositionModel:
    return P.PositionModel("TE", components={
        "targets": OneColumn("targets_pg_l3", 0.0, 1.0),
        "receptions": OneColumn(None, 3.0),
        "receiving_yards": OneColumn("receiving_yards_pg_std", 0.0, 1.0),
        "receiving_tds": OneColumn(None, 0.3),
        "fumbles_lost_total": OneColumn(None, 0.0),
    })


def _total(imp: pd.DataFrame, feature: str) -> pd.Series:
    return imp[(imp["component"] == "total") & (imp["feature"] == feature)].iloc[0]


def test_importance_is_points_of_error_reproduced_by_hand(fixture_rows, te_model):
    imp = P.component_importance(te_model, fixture_rows, HALF_PPR, n_repeats=4, seed=3)
    d = fixture_rows.iloc[:300].reset_index(drop=True)             # the 20 rows it must ignore are gone
    assert (imp["n_rows"] == 300).all()
    # the board's miss before scrambling, by hand: priced line vs the points actually scored
    actual = 0.5 * d["out_receptions"] + 0.1 * d["out_receiving_yards"] + 6 * d["out_receiving_tds"]
    line = 0.5 * 3.0 + 0.1 * d["receiving_yards_pg_std"] + 6 * 0.3
    base = float((actual - line).abs().mean())
    yards = _total(imp, "receiving_yards_pg_std")
    assert yards["unit"] == "points" and yards["baseline_mae"] == pytest.approx(base, abs=1e-12)
    # the same shuffles, drawn in the same order (n_repeats per feature, features in FEATURES order)
    rng = np.random.default_rng(3)
    perms = {f: [rng.permutation(300) for _ in range(4)] for f in P.FEATURES}
    col = d["receiving_yards_pg_std"].to_numpy()
    rises = [float((actual - (0.5 * 3.0 + 0.1 * col[p] + 6 * 0.3)).abs().mean()) - base for p in perms["receiving_yards_pg_std"]]
    assert yards["importance"] == pytest.approx(np.mean(rises), abs=1e-12)
    assert yards["importance_sd"] == pytest.approx(np.std(rises), abs=1e-12)
    assert yards["importance"] > 0.3                                 # scrambling a 10-80 yard signal costs points
    assert yards["feature_label"] == "Receiving yards per game, season"
    # the per-stat row is in yards, and in points at 0.1 a yard
    comp = imp[(imp["component"] == "receiving_yards") & (imp["feature"] == "receiving_yards_pg_std")].iloc[0]
    assert comp["unit"] == "receiving_yards"
    assert comp["importance_points"] == pytest.approx(0.1 * comp["importance"], abs=1e-12)


def test_a_stat_worth_no_points_adds_no_points_of_error(fixture_rows, te_model):
    imp = P.component_importance(te_model, fixture_rows, HALF_PPR, n_repeats=4, seed=3)
    tgt = imp[(imp["component"] == "targets") & (imp["feature"] == "targets_pg_l3")].iloc[0]
    assert tgt["importance"] > 1.0                                   # the targets model leans on it hard ...
    assert tgt["importance_points"] == 0.0
    assert _total(imp, "targets_pg_l3")["importance"] == 0.0          # ... but targets score 0 in this league


def test_unused_and_constant_inputs_score_zero(fixture_rows, te_model):
    imp = P.component_importance(te_model, fixture_rows, HALF_PPR, n_repeats=3)
    tot = imp[imp["component"] == "total"].set_index("feature")["importance"]
    assert tot["week"] == 0.0 and tot["ppg_l3"] == 0.0 and tot["implied_team_total"] == 0.0
    assert tot.idxmax() == "receiving_yards_pg_std"
    assert set(imp["component"]) == {"total", *P.COMPONENTS["TE"]}
    assert len(imp) == len(P.FEATURES) * (1 + len(P.COMPONENTS["TE"]))


def test_deterministic_and_skipping_a_column_does_not_shift_the_others(fixture_rows, te_model):
    a = P.component_importance(te_model, fixture_rows, HALF_PPR, n_repeats=3, seed=11)
    b = P.component_importance(te_model, fixture_rows, HALF_PPR, n_repeats=3, seed=11)
    pd.testing.assert_frame_equal(a, b)
    varied = fixture_rows.copy()
    varied["week"] = np.arange(len(varied), dtype=float)             # the constant column now varies (unused by the models)
    c = P.component_importance(te_model, varied, HALF_PPR, n_repeats=3, seed=11)
    assert _total(c, "receiving_yards_pg_std")["importance"] == _total(a, "receiving_yards_pg_std")["importance"]


def test_too_few_rows_returns_an_empty_frame(fixture_rows, te_model):
    out = P.component_importance(te_model, fixture_rows.iloc[:40], HALF_PPR)
    assert out.empty and list(out.columns) == P.IMPORTANCE_COLUMNS
