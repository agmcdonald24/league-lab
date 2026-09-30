"""Projection v2 (plan M-01 / M-03): stat-line components, priced per league, with an interval.

What it does
------------
* **Components, not points.** Per position, a gradient-boosted model per stat-line component
  (targets, receptions, receiving yards/TDs, carries, rushing yards/TDs, attempts, passing
  yards/TDs/INTs, fumbles lost) from the as-of features in ``analytics.mart_player_week_features``.
  Points for *any* league are then the league's scoring map applied to the projected line
  (``proj_points``), so two leagues with different scoring get different, honest boards.
* **An interval.** Per position and league, quantile models (P10 / P50 / P90) of the league's
  points, trained on the same features. The interval is the part Andrew asked for: P10 is the
  floor, P90 the ceiling, and the backtest reports how often the actual landed inside (should be
  about 80%).
* **Same discipline as the baseline.** Walk-forward: train on seasons <= N-1, test on N. Scored
  on the same harness as ``rankings.backtest`` (Spearman, top-N hit rate, MAE) next to the OLS
  baseline, plus interval coverage and pinball loss. The production model is trained on every
  completed season and applied to the current one, so everything the page shows for this season
  is out of sample.

Nothing here is tuned per week; hyperparameters are fixed constants below (changing them is a
model version). scikit-learn's HistGradientBoostingRegressor handles NULL features natively, so
the raw as-of columns are used as they are (a NULL means "not known yet", which is information).

Outputs: ``ops.projections`` (one row per league x season x week x player), ``ops.projection_backtest``
(per season-week-position-scorer), ``ops.projection_importance`` (permutation importance of the
P50 model per position), ``ops.projection_drift`` (plan M-06: the live board's played weeks scored
like a held-out season), and a Markdown report under ``reports/backtests``.

Decision record (plan B5): a league-week's rows in ``ops.projections`` are rewritten by every refit
until the week's first kickoff and never after (``_write_projections`` / ``freeze_plan``); the rows
that were live at kickoff are kept and labelled ``frozen_source = 'kickoff'`` with ``frozen_at`` = their
publication time, and the drift scores them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from .config import PROJECT_ROOT, get_settings
from .kdef import rows_after_project as kd_rows_after_project
from .lineup import lineups_after_project
from .rankings import TOP_N, _hit_rate, _spearman, parse_seasons
from .scoring import compute_points
from .waivers import waivers_after_project

log = logging.getLogger(__name__)

MODEL_VERSION = "v2.0"
POSITIONS = ("QB", "RB", "WR", "TE")
QUANTILES = (0.1, 0.5, 0.9)

# Stat-line components projected per position (everything else is 0 for that position).
COMPONENTS: dict[str, list[str]] = {
    "QB": ["attempts", "passing_yards", "passing_tds", "passing_interceptions", "carries", "rushing_yards", "rushing_tds", "fumbles_lost_total"],
    "RB": ["carries", "rushing_yards", "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds", "fumbles_lost_total"],
    "WR": ["targets", "receptions", "receiving_yards", "receiving_tds", "carries", "rushing_yards", "rushing_tds", "fumbles_lost_total"],
    "TE": ["targets", "receptions", "receiving_yards", "receiving_tds", "fumbles_lost_total"],
}
ALL_COMPONENTS = ["targets", "receptions", "receiving_yards", "receiving_tds", "carries", "rushing_yards", "rushing_tds",
                  "attempts", "passing_yards", "passing_tds", "passing_interceptions", "fumbles_lost_total"]
YARDS = {"receiving_yards", "rushing_yards", "passing_yards"}  # can be negative: squared error, not Poisson

# Features (all as-of the week; NULL allowed). Shared by every component and quantile model.
BASE_FEATURES = [
    "week", "games_to_date", "f_sample", "prev_games",
    "ppg_std", "ppg_l3", "ppg_l5", "points_sd_std", "xppg_std", "xppg_l3", "xppg_l5", "prev_ppg", "prev_xppg", "pos_prev_ppg",
    "target_share_std", "target_share_l3", "carry_share_std", "carry_share_l3", "snap_pct_std", "snap_pct_l3",
    "air_yards_share_l3", "first_read_share_std", "first_read_share_l3", "prev_snap_pct",
    # NOT route_participation_l3: the participation file arrives after the postseason, so the feature
    # is NULL all season in production; a backtest that used it (TE leaned on it hardest) would
    # overstate what the live board can do. Only in-season-available inputs are allowed here.
    "opp_allowed_std", "opp_allowed_l4", "opp_rank_std", "league_allowed_avg", "f_opp_allowed_diff",
    "implied_team_total", "spread_line", "total_line", "f_home", "questionable",
    "red_zone_targets_pg_std", "red_zone_targets_pg_l3", "red_zone_carries_pg_std", "red_zone_carries_pg_l3",
]
COMPONENT_FEATURES = [f"{c}_pg_std" for c in ALL_COMPONENTS] + [f"{c}_pg_l3" for c in ALL_COMPONENTS] + [f"prev_{c}_pg" for c in ALL_COMPONENTS]
FEATURES = BASE_FEATURES + COMPONENT_FEATURES

# Fixed hyperparameters (a change is a new MODEL_VERSION). Small trees, strong leaf minimum:
# weekly fantasy outcomes are noisy and the training sets are a few thousand rows per position.
HGB = dict(max_iter=300, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=40, l2_regularization=1.0, random_state=0)


# ------------------------------------------------------------------------------ data
def load_frame(conn: psycopg.Connection, seasons: list[int]) -> pd.DataFrame:
    cols = ["gsis_id", "season", "week", "position", "player_name", "team", "opponent", "played", "points_actual", "no_history",
            "report_status", "roster_status", *[f for f in FEATURES if f != "questionable"], *[f"out_{c}" for c in ALL_COMPONENTS]]
    # ordered: the early-stopping validation split (automatic above 10k rows) follows row order, so an
    # unordered scan (synchronized seq scans on a 60 MB table) made two fits of the same data differ
    sql = (f"select {', '.join(dict.fromkeys(cols))} from analytics.mart_player_week_features "
           "where season = any(%s) and position = any(%s) order by gsis_id, season, week")
    with conn.cursor() as cur:
        cur.execute(sql, (seasons, list(POSITIONS)))
        names = [d.name for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=names)
    for c in df.columns:
        if c in FEATURES or c.startswith("out_") or c == "points_actual":
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["questionable"] = (df["report_status"] == "Questionable").astype(float)
    return df


def league_scorings(conn: psycopg.Connection) -> dict[str, tuple[str, dict[str, float]]]:
    """league_id -> (league_name, scoring_settings) for every current league-season, reference first."""
    with conn.cursor() as cur:
        cur.execute("""select league_id, league_name, scoring_settings from analytics.dim_league_season
                       where is_current_season order by is_reference_league desc, league_name""")
        return {r[0]: (r[1], {k: float(v) for k, v in r[2].items()}) for r in cur.fetchall()}


def price(df: pd.DataFrame, scoring: dict[str, float], prefix: str) -> pd.Series:
    """League points of a stat line held in ``<prefix><component>`` columns (bonus keys included where computable)."""
    rows = df[[f"{prefix}{c}" for c in ALL_COMPONENTS]].rename(columns=lambda c: c[len(prefix):])
    return pd.Series([compute_points(r, scoring) for r in rows.to_dict("records")], index=df.index, dtype=float)


# ------------------------------------------------------------------------------ models
@dataclass
class PositionModel:
    position: str
    components: dict[str, object] = field(default_factory=dict)      # component -> regressor
    quantiles: dict[tuple[str, float], object] = field(default_factory=dict)  # (league_id, q) -> regressor
    conformal: dict[str, float] = field(default_factory=dict)        # league_id -> interval widening (points)
    n_rows: int = 0
    calibration_season: int | None = None


def _regressor(loss: str, quantile: float | None = None):
    from sklearn.ensemble import HistGradientBoostingRegressor

    kw = dict(HGB)
    if quantile is not None:
        return HistGradientBoostingRegressor(loss="quantile", quantile=quantile, **kw)
    return HistGradientBoostingRegressor(loss=loss, **kw)


def _line_points(m: PositionModel, x: np.ndarray, scoring: dict[str, float]) -> np.ndarray:
    """The priced projected line for a feature matrix (the anchor the quantile models work from)."""
    comp = pd.DataFrame({f"proj_{c}": (np.clip(m.components[c].predict(x), 0, None) if c in m.components else 0.0) for c in ALL_COMPONENTS})
    return price(comp, scoring, "proj_").to_numpy(dtype=float)


def _quantile_features(x: np.ndarray, line: np.ndarray) -> np.ndarray:
    return np.column_stack([x, line])


def _binnable(x: np.ndarray) -> np.ndarray:
    """A copy where a column that is entirely unknown becomes 0, so the binner has something to
    bin (a first-read share on seasons before charting exists, say); the model then ignores it."""
    x = x.copy()
    all_nan = np.isnan(x).all(axis=0)
    x[:, all_nan] = 0.0
    return x


def _matrix(d: pd.DataFrame) -> np.ndarray:
    """Feature matrix (NaN = not known yet)."""
    return _binnable(d[FEATURES].to_numpy(dtype=float))


def _fit_components(x: np.ndarray, d: pd.DataFrame, position: str) -> dict[str, object]:
    models: dict[str, object] = {}
    for c in COMPONENTS[position]:
        y = d[f"out_{c}"].to_numpy(dtype=float)
        loss = "squared_error" if c in YARDS else "poisson"
        if loss == "poisson":
            y = np.clip(y, 0, None)
        models[c] = _regressor(loss).fit(_binnable(x), y)
    return models


def _price_models(models: dict[str, object], x: np.ndarray, scoring: dict[str, float]) -> np.ndarray:
    comp = pd.DataFrame({f"proj_{c}": (np.clip(models[c].predict(x), 0, None) if c in models else 0.0) for c in ALL_COMPONENTS})
    return price(comp, scoring, "proj_").to_numpy(dtype=float)


def _oof_lines(x: np.ndarray, d: pd.DataFrame, position: str, scorings: dict[str, tuple[str, dict[str, float]]]) -> dict[str, np.ndarray]:
    """Out-of-fold priced lines for every training row: components fitted on the odd seasons
    predict the even ones and vice versa, so the residuals the interval learns from are the
    size of real forecast errors, not in-sample fits."""
    seasons = sorted(d["season"].unique())
    fold = d["season"].map({s: i % 2 for i, s in enumerate(seasons)}).to_numpy()
    lines = {lid: np.full(len(d), np.nan) for lid in scorings}
    for k in (0, 1):
        tr, te = fold != k, fold == k
        if tr.sum() < 100 or te.sum() == 0:
            continue
        models = _fit_components(x[tr], d[tr], position)
        for lid, (_, scoring) in scorings.items():
            lines[lid][te] = _price_models(models, x[te], scoring)
    return lines


def fit_position(train: pd.DataFrame, position: str, scorings: dict[str, tuple[str, dict[str, float]]]) -> PositionModel:
    d = train[(train["position"] == position) & train["played"] & ~train["no_history"]]
    d = d.dropna(subset=[f"out_{c}" for c in COMPONENTS[position]]).reset_index(drop=True)
    x = _matrix(d)
    m = PositionModel(position, n_rows=len(d))
    # 1. the point projection: one regressor per component on every training row
    m.components = _fit_components(x, d, position)
    # 2. the interval: quantile regressors of the RESIDUAL of the league's points around the
    #    priced line (the line is also a feature). Fitting the 10th percentile of raw points
    #    fails on a target with a point mass at 0 (a fifth of played WR weeks score nothing): the
    #    initial constant sits on the mass and the model never leaves it. Residuals are taken
    #    against OUT-OF-FOLD lines so they are the size of real forecast errors.
    # 3. split-conformal calibration (CQR): the residual models are fitted on all but the newest
    #    training season; that season measures how far actuals fall outside [P10, P90], and both
    #    ends are widened by the 80th percentile of the miss, so "80% inside" holds out of sample.
    seasons = sorted(d["season"].unique())
    cal_season = seasons[-1] if len(seasons) >= 3 else None
    is_cal = (d["season"] == cal_season).to_numpy() if cal_season else np.zeros(len(d), dtype=bool)
    m.calibration_season = cal_season
    oof = _oof_lines(x, d, position, scorings)
    for league_id, (_, scoring) in scorings.items():
        line = oof[league_id]
        ok = ~np.isnan(line)
        y = price(d, scoring, "out_").to_numpy(dtype=float) - line
        xq = _quantile_features(x, np.nan_to_num(line))
        fit_idx, cal_idx = ok & ~is_cal, ok & is_cal
        for q in QUANTILES:
            m.quantiles[(league_id, q)] = _regressor("quantile", q).fit(_binnable(xq[fit_idx]), y[fit_idx])
        if cal_idx.sum() >= 50:
            lo = m.quantiles[(league_id, QUANTILES[0])].predict(xq[cal_idx])
            hi = m.quantiles[(league_id, QUANTILES[-1])].predict(xq[cal_idx])
            miss = np.maximum(lo - y[cal_idx], y[cal_idx] - hi)      # negative when inside the interval
            n = int(cal_idx.sum())
            level = min(1.0, np.ceil((n + 1) * (QUANTILES[-1] - QUANTILES[0])) / n)
            m.conformal[league_id] = float(np.quantile(miss, level))
        else:
            m.conformal[league_id] = 0.0
    log.info("fit %s: %s rows, %s components, %s quantile models, calibration season %s, widening %s",
             position, len(d), len(m.components), len(m.quantiles), cal_season,
             {k[-6:]: round(v, 2) for k, v in m.conformal.items()})
    return m


def predict_position(m: PositionModel, rows: pd.DataFrame, scorings: dict[str, tuple[str, dict[str, float]]]) -> pd.DataFrame:
    """One output row per league per input row: projected line, priced points, P10/P50/P90."""
    x = _matrix(rows)
    out = rows[["gsis_id", "season", "week", "position"]].copy()
    out["season"], out["week"] = out["season"].astype(int), out["week"].astype(int)   # week is also a feature (float)
    for c in ALL_COMPONENTS:
        out[f"proj_{c}"] = np.clip(m.components[c].predict(x), 0, None) if c in m.components else 0.0
    frames = []
    for league_id, (_, scoring) in scorings.items():
        o = out.copy()
        o["league_id"] = league_id
        o["proj_points"] = price(o, scoring, "proj_")
        line = o["proj_points"].to_numpy(dtype=float)
        xq = _quantile_features(x, line)
        for q, col in zip(QUANTILES, ("p10", "p50", "p90"), strict=True):
            o[col] = line + m.quantiles[(league_id, q)].predict(xq)
        # a quantile model has no monotonicity guarantee across separate fits: sort the three,
        # then apply the conformal widening to both ends (a floor of 0 for P10: no negative floors)
        qs = np.sort(o[["p10", "p50", "p90"]].to_numpy(dtype=float), axis=1)
        adj = m.conformal.get(league_id, 0.0)
        o["p10"], o["p50"], o["p90"] = np.clip(qs[:, 0] - adj, 0, None), qs[:, 1], qs[:, 2] + adj
        o["p90"] = np.maximum(o["p90"], o["proj_points"])   # the ceiling never sits below the projection
        o["p50"] = np.clip(o["p50"], o["p10"], o["p90"])     # keep the order after the floor was clipped at 0
        frames.append(o)
    return pd.concat(frames, ignore_index=True)


def importance(m: PositionModel, test: pd.DataFrame, league_id: str, scoring: dict[str, float]) -> pd.DataFrame:
    """Permutation importance of the P50 model on the held-out rows (drop in pinball loss)."""
    from sklearn.inspection import permutation_importance

    d = test[(test["position"] == m.position) & test["played"]].dropna(subset=[f"out_{c}" for c in COMPONENTS[m.position]])
    if len(d) < 50:
        return pd.DataFrame(columns=["position", "feature", "importance"])
    x = _matrix(d)
    line = _line_points(m, x, scoring)
    y = price(d, scoring, "out_").to_numpy(dtype=float) - line
    r = permutation_importance(m.quantiles[(league_id, 0.5)], _quantile_features(x, line), y, scoring="neg_mean_absolute_error", n_repeats=3, random_state=0)
    return pd.DataFrame({"position": m.position, "feature": [*FEATURES, "priced_line"], "importance": r.importances_mean}).sort_values("importance", ascending=False)


# ------------------------------------------------------------------------------ scoring a season
def _pinball(y: np.ndarray, q_pred: np.ndarray, q: float) -> float:
    diff = y - q_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def score_predictions(pred: pd.DataFrame, actual: pd.DataFrame, baseline: pd.DataFrame | None, min_players: int = 8) -> pd.DataFrame:
    """Per league-season-week-position: v2 (points and P50) and the baseline on the same players.

    ``actual`` carries out_* columns for played rows; the league's actual points are priced from them.
    """
    out: list[dict[str, object]] = []
    for league_id, scoring in pred.attrs["scorings"].items():
        p = pred[pred["league_id"] == league_id].merge(actual, on=["gsis_id", "season", "week", "position"], how="inner")
        p["points_league"] = price(p, scoring, "out_")
        if baseline is not None:
            p = p.merge(baseline, on=["gsis_id", "season", "week"], how="left")
        for (season, week, pos), g in p.groupby(["season", "week", "position"]):
            if len(g) < min_players:
                continue
            y = g["points_league"]
            inside = ((y >= g["p10"]) & (y <= g["p90"])).mean()
            scorers = {"v2_points": g["proj_points"], "v2_p50": g["p50"]}
            if baseline is not None and "baseline_points" in g and g["baseline_points"].notna().sum() >= min_players:
                scorers["baseline"] = g["baseline_points"]
            for name, s in scorers.items():
                gg = g[s.notna()]
                ss = s[s.notna()]
                out.append({
                    "league_id": league_id, "season": int(season), "week": int(week), "position": pos, "scorer": name,
                    "n_players": int(len(gg)),
                    "spearman": _spearman(ss, gg["points_league"]), "top_n": TOP_N[pos],
                    "hit_rate": _hit_rate(ss, gg["points_league"], TOP_N[pos]),
                    "mae": float((ss - gg["points_league"]).abs().mean()),
                    "coverage_80": float(inside) if name != "baseline" else None,
                    "pinball_10": _pinball(y.to_numpy(), g["p10"].to_numpy(), 0.1) if name != "baseline" else None,
                    "pinball_50": _pinball(y.to_numpy(), g["p50"].to_numpy(), 0.5) if name != "baseline" else None,
                    "pinball_90": _pinball(y.to_numpy(), g["p90"].to_numpy(), 0.9) if name != "baseline" else None,
                    "interval_width": float((g["p90"] - g["p10"]).mean()) if name != "baseline" else None,
                })
    return pd.DataFrame(out)


def load_baseline(conn: psycopg.Connection, seasons: list[int]) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("""select gsis_id, season, week, proj_points as baseline_points from analytics.mart_player_week_rankings
                       where season = any(%s) and is_rankable""", (seasons,))
        return pd.DataFrame(cur.fetchall(), columns=["gsis_id", "season", "week", "baseline_points"]).astype({"baseline_points": float})


# ------------------------------------------------------------------------------ walk-forward backtest
def backtest(conn: psycopg.Connection, test_seasons: list[int], out_dir: Path | None = None) -> pd.DataFrame:
    scorings = league_scorings(conn)
    all_seasons = available_seasons(conn)
    first = min(all_seasons)
    frame = load_frame(conn, [s for s in all_seasons if s <= max(test_seasons)])
    baseline = load_baseline(conn, test_seasons)
    results: list[pd.DataFrame] = []
    imps: list[pd.DataFrame] = []
    ref_id = next(iter(scorings))
    for n in test_seasons:
        train = frame[(frame["season"] >= first) & (frame["season"] < n)]
        test = frame[frame["season"] == n]
        if train.empty or test.empty:
            log.warning("season %s: no train (%s rows) or test (%s rows)", n, len(train), len(test))
            continue
        preds = []
        for pos in POSITIONS:
            m = fit_position(train, pos, {k: v for k, v in scorings.items()})
            preds.append(predict_position(m, test[test["position"] == pos], scorings))
            if n == max(test_seasons):
                imps.append(importance(m, test, ref_id, scorings[ref_id][1]))
        pred = pd.concat(preds, ignore_index=True)
        pred.attrs["scorings"] = {k: v[1] for k, v in scorings.items()}
        actual = test[test["played"]][["gsis_id", "season", "week", "position", *[f"out_{c}" for c in ALL_COMPONENTS]]].dropna()
        res = score_predictions(pred, actual, baseline)
        res["train_seasons"] = f"{first}-{n - 1}"
        results.append(res)
        log.info("season %s scored: %s rows", n, len(res))
    res = pd.concat(results, ignore_index=True)
    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    res["run_id"], res["run_at"], res["model_version"] = run_id, datetime.now(UTC), MODEL_VERSION
    # the K / DEF rows (R-13, model kd1.0, `league-lab backtest-kd`) share the table: not this run's to delete
    _write(conn, "ops.projection_backtest", res, "season = any(%s) and coalesce(model_version, '') not like 'kd%%'", (test_seasons,))
    imp = pd.concat(imps, ignore_index=True) if imps else pd.DataFrame(columns=["position", "feature", "importance"])
    imp["model_version"], imp["run_at"], imp["league_id"] = MODEL_VERSION, datetime.now(UTC), ref_id
    _write(conn, "ops.projection_importance", imp, "model_version = %s", (MODEL_VERSION,))
    out_dir = out_dir or PROJECT_ROOT / "reports" / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"projection_v2_{min(test_seasons)}_{max(test_seasons)}_{run_id}.md"
    path.write_text(report(res, scorings, imp))
    log.info("report written to %s", path)
    return res


def available_seasons(conn: psycopg.Connection) -> list[int]:
    with conn.cursor() as cur:
        cur.execute("select distinct season from analytics.mart_player_week_features where played order by 1")
        return [int(r[0]) for r in cur.fetchall()]


# ------------------------------------------------------------------------------ production projections
def project(conn: psycopg.Connection, season: int | None = None) -> pd.DataFrame:
    """Fit on every completed season before ``season`` and project every week of ``season``."""
    scorings = league_scorings(conn)
    seasons = available_seasons(conn)
    season = season or max(seasons)
    train_seasons = [s for s in seasons if s < season]
    frame = load_frame(conn, [*train_seasons, season])
    train = frame[frame["season"] < season]
    target = frame[frame["season"] == season]
    preds = []
    for pos in POSITIONS:
        m = fit_position(train, pos, scorings)
        preds.append(predict_position(m, target[target["position"] == pos], scorings))
    pred = pd.concat(preds, ignore_index=True)
    pred["model_version"], pred["fitted_at"] = MODEL_VERSION, datetime.now(UTC)
    pred["train_seasons"] = f"{min(train_seasons)}-{max(train_seasons)}"
    # R-13: K and DEF rows (model kd1.0, leagues that start them) go through the same B5 writer
    pred = _with_kd_rows(conn, pred, season)
    _write_projections(conn, pred, season)   # B5: weeks whose first game has kicked off are kept, not rewritten
    log.info("projections computed: %s rows for %s (%s leagues)", len(pred), season, len(scorings))
    # M-06: keep the drift monitor current on every refit. It scores the stored (for a started week:
    # frozen, B5) projections against the outcomes in mart_player_week_projections as last built: in
    # the nightly the full dbt build runs first, so the outcomes are tonight's.
    # A failure here must not cost the night its projections: log it, keep the previous drift rows.
    try:
        drift(conn, season)
    except Exception:
        conn.rollback()
        log.exception("drift monitor failed (projections were written); run `league-lab drift` after `dbt build`")
    lineups_after_project(conn, season)   # B1: exact lineups on the fresh projections (a failure is logged, not fatal)
    waivers_after_project(conn, season)   # B3: waiver moves on those lineups (a failure is logged, not fatal)
    return pred


def _with_kd_rows(conn: psycopg.Connection, pred: pd.DataFrame, season: int) -> pd.DataFrame:
    """R-13: the v2 rows plus the K / DEF rows of ``kdef`` (their own model_version, kd1.0), so one
    ``_write_projections`` call writes a league-week whole. No K / DEF rows (a failure, or no league
    starts them) leaves the v2 rows exactly as they were."""
    kd = kd_rows_after_project(conn, season)
    if kd.empty:
        return pred
    out = pd.concat([pred, kd], ignore_index=True)
    out.attrs = pred.attrs
    return out


# ------------------------------------------------------------------------------ drift (M-06): the live board, scored like the backtest
DRIFT_COLUMNS = ["league_id", "season", "week", "position", "n_players", "spearman", "top_n", "hit_rate", "mae",
                 "coverage_80", "interval_width", "games_played", "games_scheduled", "frozen_share", "model_version"]


def score_drift(board: pd.DataFrame, min_players: int = 8) -> pd.DataFrame:
    """Per league x season x week x position: the live board's played weeks scored the way
    ``score_predictions`` scores a held-out season (Spearman, top-N hit rate, MAE, share of actuals
    inside [P10, P90], mean P90 - P10), with the same ``min_players`` rule.

    ``board`` holds one row per league x season x week x player (``load_board``): league_id, season,
    week, position, game_id, played, is_rankable, points_actual (already priced in the league's own
    scoring) from ``analytics.mart_player_week_projections``, and the projection as stored in
    ``ops.projections`` (proj_points, p10, p90, model_version, frozen_source). Scored on players who
    played and were rankable (the board the page shows). ``games_played`` / ``games_scheduled`` count
    the week's games with at least one player in / on the board, so a week still being played
    (Thursday night only) is visible as such; the season view averages complete weeks only.
    ``frozen_share`` (B5) is the share of the scored rows whose projection is the board as published
    before the week's first kickoff (``frozen_source = 'kickoff'``); 0 = refit values (a week played
    before the freeze existed, or one not locked yet), and a board without the label counts as 0.
    """
    if board.empty:
        return pd.DataFrame(columns=DRIFT_COLUMNS)
    b = board.copy()
    for c in ("proj_points", "p10", "p90", "points_actual"):
        b[c] = pd.to_numeric(b[c], errors="coerce").astype(float)
    b["played"] = b["played"].fillna(False).astype(bool)
    b["is_rankable"] = b["is_rankable"].fillna(False).astype(bool)
    b["is_kickoff_board"] = (b["frozen_source"] == "kickoff").fillna(False).astype(bool) if "frozen_source" in b else False
    wk = ["league_id", "season", "week"]
    games = pd.DataFrame({
        "games_scheduled": b.groupby(wk)["game_id"].nunique(),
        "games_played": b[b["played"]].groupby(wk)["game_id"].nunique(),
    }).fillna(0).astype(int)
    s = b[b["played"] & b["is_rankable"] & b["points_actual"].notna() & b["proj_points"].notna()]
    out: list[dict[str, object]] = []
    for (league_id, season, week, pos), g in s.groupby([*wk, "position"]):
        if len(g) < min_players:
            continue
        y, p = g["points_actual"], g["proj_points"]
        iv = g[g["p10"].notna() & g["p90"].notna()]
        yi = iv["points_actual"]
        out.append({
            "league_id": league_id, "season": int(season), "week": int(week), "position": pos,
            "n_players": int(len(g)),
            "spearman": _spearman(p, y), "top_n": TOP_N[pos], "hit_rate": _hit_rate(p, y, TOP_N[pos]),
            "mae": float((p - y).abs().mean()),
            "coverage_80": float(((yi >= iv["p10"]) & (yi <= iv["p90"])).mean()) if len(iv) else None,
            "interval_width": float((iv["p90"] - iv["p10"]).mean()) if len(iv) else None,
            "games_played": int(games.loc[(league_id, season, week), "games_played"]),
            "games_scheduled": int(games.loc[(league_id, season, week), "games_scheduled"]),
            "frozen_share": float(g["is_kickoff_board"].mean()),
            "model_version": g["model_version"].dropna().max() if g["model_version"].notna().any() else None,
        })
    return pd.DataFrame(out, columns=DRIFT_COLUMNS)


def load_board(conn: psycopg.Connection, season: int) -> pd.DataFrame:
    """Every row of the season's board (played or not: the unplayed rows count the week's games).

    The projection comes from ``ops.projections`` itself (rounded like the mart), so a week that has
    kicked off is scored on its frozen rows even if the mart has not been rebuilt since the refit
    that locked it; outcomes, availability and games come from the mart."""
    with conn.cursor() as cur:
        cur.execute("""select m.league_id, m.season, m.week, m.position, m.gsis_id, m.game_id, m.played, m.is_rankable,
                              round(p.proj_points::numeric, 2) as proj_points, round(p.p10::numeric, 2) as p10,
                              round(p.p90::numeric, 2) as p90, m.points_actual, p.model_version, p.frozen_source
                       from analytics.mart_player_week_projections as m
                       join ops.projections as p using (league_id, season, week, gsis_id)
                       where m.season = %s and m.position = any(%s)""", (season, list(POSITIONS)))   # QB-TE: K/DEF (R-13) are not v2
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def drift(conn: psycopg.Connection, season: int | None = None) -> pd.DataFrame:
    """Score the played weeks of the projected season (default: the newest on the board) and
    replace that season's rows in ``ops.projection_drift``."""
    with conn.cursor() as cur:
        cur.execute(DDL["ops.projections"])   # an older database gains the freeze labels load_board reads
    if season is None:
        with conn.cursor() as cur:
            cur.execute("select max(season) from analytics.mart_player_week_projections")
            season = cur.fetchone()[0]
        if season is None:
            log.warning("drift: mart_player_week_projections is empty (run `league-lab project` and `dbt build`)")
            return pd.DataFrame(columns=[*DRIFT_COLUMNS, "run_at"])
    res = score_drift(load_board(conn, int(season)))
    res["run_at"] = datetime.now(UTC)
    _write(conn, "ops.projection_drift", res, "season = %s", (int(season),))
    log.info("drift written: %s rows for %s (weeks %s)", len(res), season, sorted(res["week"].unique().tolist()) if len(res) else "none played")
    return res


# ------------------------------------------------------------------------------ persistence
DDL = {
    "ops.projections": """create table if not exists ops.projections (
        model_version text, fitted_at timestamptz, train_seasons text, league_id text, season integer, week integer,
        gsis_id text, position text,
        proj_targets double precision, proj_receptions double precision, proj_receiving_yards double precision,
        proj_receiving_tds double precision, proj_carries double precision, proj_rushing_yards double precision,
        proj_rushing_tds double precision, proj_attempts double precision, proj_passing_yards double precision,
        proj_passing_tds double precision, proj_passing_interceptions double precision, proj_fumbles_lost_total double precision,
        proj_points double precision, p10 double precision, p50 double precision, p90 double precision,
        frozen_at timestamptz, frozen_source text);
        alter table ops.projections add column if not exists frozen_at timestamptz;
        alter table ops.projections add column if not exists frozen_source text""",
    "ops.projection_backtest": """create table if not exists ops.projection_backtest (
        run_id text, run_at timestamptz, model_version text, train_seasons text, league_id text, season integer, week integer,
        position text, scorer text, n_players integer, spearman double precision, top_n integer, hit_rate double precision,
        mae double precision, coverage_80 double precision, pinball_10 double precision, pinball_50 double precision,
        pinball_90 double precision, interval_width double precision)""",
    "ops.projection_importance": """create table if not exists ops.projection_importance (
        model_version text, run_at timestamptz, league_id text, position text, feature text, importance double precision)""",
    "ops.projection_drift": """create table if not exists ops.projection_drift (
        run_at timestamptz, model_version text, league_id text, season integer, week integer, position text,
        n_players integer, spearman double precision, top_n integer, hit_rate double precision, mae double precision,
        coverage_80 double precision, interval_width double precision, games_played integer, games_scheduled integer,
        frozen_share double precision);
        alter table ops.projection_drift add column if not exists frozen_share double precision""",
}


def _write(conn: psycopg.Connection, table: str, df: pd.DataFrame, where: str, params: tuple) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL[table])
        cur.execute("select column_name from information_schema.columns where table_schema = %s and table_name = %s",
                    tuple(table.split(".")))
        cols = [r[0] for r in cur.fetchall() if r[0] in df.columns]
        cur.execute(f"delete from {table} where {where}", params)
        records = [tuple(None if (isinstance(v, float) and np.isnan(v)) else v for v in r)
                   for r in df[cols].itertuples(index=False, name=None)]
        with cur.copy(f"copy {table} ({', '.join(cols)}) from stdin") as cp:
            for r in records:
                cp.write_row(r)
    conn.commit()


# ------------------------------------------------------------------------------ decision record (B5): freeze a league-week at kickoff
def freeze_plan(new_weeks: pd.DataFrame, stored: pd.DataFrame, kickoffs: dict[int, datetime], now: datetime) -> pd.DataFrame:
    """What a refit may do to each (league_id, week) of the season in ``ops.projections``.

    ``new_weeks``: the refit's (league_id, week) pairs. ``stored``: one row per stored league-week with
    ``fitted_at`` (max), ``frozen_source`` and ``frozen_at`` (the label, NULL while live). ``kickoffs``:
    week -> first kickoff of that week (``dim_game.kickoff_at``); a week without one counts as not
    started. A week has *started* once its first kickoff is at or before ``now``.

    Rules (one label per league-week):
    * not started -> ``write``: the refit replaces the rows (live, label NULL); a stored week the refit
      no longer projects -> ``delete`` (what the old season-wide delete did);
    * started, rows stored -> ``keep``: never deleted or rewritten. The first refit after kickoff labels
      them (``relabel``): ``kickoff`` with ``frozen_at`` = their ``fitted_at`` when they were written
      before the first kickoff (the board managers saw), otherwise ``refit`` with ``frozen_at`` NULL
      (the week was already under way when its rows were written: 2026 weeks 1-3, which were played
      before this rule existed, or a league added mid-season);
    * started, nothing stored -> ``write`` labelled ``refit`` (and kept from then on).

    Returns columns league_id, week, first_kickoff, started, action, relabel, frozen_source, frozen_at.
    """
    keys = ["league_id", "week"]
    new = new_weeks[keys].drop_duplicates().astype({"league_id": object, "week": int}).assign(in_new=True)
    old = (stored.reindex(columns=[*keys, "fitted_at", "frozen_source", "frozen_at"])
           .astype({"league_id": object, "week": int, "frozen_source": object, "frozen_at": object}).assign(is_stored=True))
    w = new.merge(old, on=keys, how="outer")
    w["in_new"] = w["in_new"].astype("boolean").fillna(False).astype(bool)
    w["is_stored"] = w["is_stored"].astype("boolean").fillna(False).astype(bool)
    out = []
    for r in w.itertuples(index=False):
        kick = kickoffs.get(int(r.week))
        started = kick is not None and kick <= now
        stored_source = r.frozen_source if isinstance(r.frozen_source, str) else None
        stored_at = None if pd.isna(r.frozen_at) else r.frozen_at
        row = {"league_id": r.league_id, "week": int(r.week), "first_kickoff": kick, "started": started,
               "relabel": False, "frozen_source": None, "frozen_at": None}
        if not started:
            row["action"] = "write" if r.in_new else "delete"
        elif r.is_stored:
            row["action"] = "keep"
            if stored_source is not None:
                row["frozen_source"], row["frozen_at"] = stored_source, stored_at
            else:
                fitted = None if pd.isna(r.fitted_at) else r.fitted_at
                pre_kickoff = fitted is not None and fitted < kick
                row["relabel"] = True
                row["frozen_source"], row["frozen_at"] = ("kickoff", fitted) if pre_kickoff else ("refit", None)
        else:
            row["action"], row["frozen_source"] = "write", "refit"
        out.append(row)
    cols = [*keys, "first_kickoff", "started", "action", "relabel", "frozen_source", "frozen_at"]
    # object columns so a missing label stays None (pandas would turn it into NaN / NaT)
    plan = pd.DataFrame({c: pd.Series([row[c] for row in out], dtype=object) for c in cols})
    return plan.astype({"week": int, "started": bool, "relabel": bool})


def _write_projections(conn: psycopg.Connection, pred: pd.DataFrame, season: int, now: datetime | None = None) -> pd.DataFrame:
    """Write a refit's season of projections under the B5 freeze rule (``freeze_plan``), in one
    transaction: label the league-weeks locked for the first time, then replace only the weeks that
    have not kicked off (and write, labelled ``refit``, a started week that has no rows yet). Rows of a
    week that has kicked off are never deleted or rewritten; to re-project one deliberately, delete
    its rows by hand first (it then comes back labelled ``refit``). ``now`` is for tests/simulation.
    Records the plan in ``pred.attrs["freeze"]`` for the CLI."""
    now = now or datetime.now(UTC)
    with conn.cursor() as cur:
        cur.execute(DDL["ops.projections"])
        cur.execute("select week, min(kickoff_at) from analytics.dim_game where season = %s group by week", (season,))
        kickoffs = {int(wk): k for wk, k in cur.fetchall() if k is not None}
        cur.execute("""select league_id, week, max(fitted_at) as fitted_at, max(frozen_source) as frozen_source, max(frozen_at) as frozen_at
                       from ops.projections where season = %s group by 1, 2""", (season,))
        stored = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        plan = freeze_plan(pred, stored, kickoffs, now)
        for r in plan[plan["relabel"]].itertuples(index=False):
            cur.execute("""update ops.projections set frozen_source = %s, frozen_at = %s
                           where season = %s and league_id = %s and week = %s and frozen_source is null""",
                        (r.frozen_source, r.frozen_at, season, r.league_id, int(r.week)))
    writes = plan[plan["action"] == "write"]
    rows = pred.merge(writes[["league_id", "week", "frozen_source", "frozen_at"]], on=["league_id", "week"], how="inner")
    rows["frozen_at"] = rows["frozen_at"].astype(object).where(rows["frozen_at"].notna(), None)
    replace = plan[plan["action"].isin(["write", "delete"])]
    _write(conn, "ops.projections", rows, "season = %s and (league_id, week) in (select * from unnest(%s::text[], %s::int[]))",
           (season, replace["league_id"].tolist(), [int(w) for w in replace["week"]]))   # commits the relabel with the write

    def weeks(mask: pd.Series) -> list[int]:
        return sorted(plan.loc[mask, "week"].astype(int).unique().tolist())

    summary = {"rewritten": weeks(plan["action"] == "write"), "kept": weeks(plan["action"] == "keep"),
               "kickoff": weeks(plan["frozen_source"] == "kickoff"), "refit": weeks(plan["frozen_source"] == "refit"),
               "locked_now": weeks(plan["relabel"]), "rows_written": len(rows)}
    pred.attrs["freeze"] = summary
    log.info("projections written for %s: %s rows (weeks %s rewritten); weeks %s kept as frozen (kickoff board: %s, refit values: %s; locked this run: %s)",
             season, len(rows), summary["rewritten"] or "none", summary["kept"] or "none", summary["kickoff"] or "none",
             summary["refit"] or "none", summary["locked_now"] or "none")
    return plan


# ------------------------------------------------------------------------------ report
def summarize(res: pd.DataFrame) -> pd.DataFrame:
    return res.groupby(["league_id", "position", "scorer"]).agg(
        weeks=("week", "count"), spearman=("spearman", "mean"), hit_rate=("hit_rate", "mean"), mae=("mae", "mean"),
        coverage_80=("coverage_80", "mean"), interval_width=("interval_width", "mean"),
    ).reset_index()


def report(res: pd.DataFrame, scorings: dict[str, tuple[str, dict[str, float]]], imp: pd.DataFrame) -> str:
    lines = [f"# Projection v2 backtest ({MODEL_VERSION})",
             f"_generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · walk-forward: train on seasons before N, test N · players who played, "
             "regular season, weeks with ≥ 8 ranked players_", "",
             "Scorers: `v2_points` = projected stat line priced under the league's scoring; `v2_p50` = the median of the quantile model; "
             "`baseline` = the OLS formula (`ranking_weights.csv`, reference league only). `coverage_80` = share of actuals inside [P10, P90] "
             "(target 0.80); `interval_width` = mean P90 − P10 in points.", ""]
    s = summarize(res)
    for league_id, (name, _) in scorings.items():
        sl = s[s["league_id"] == league_id]
        if sl.empty:
            continue
        lines += [f"## {name} ({league_id})", "", "| Pos | Scorer | Weeks | Spearman | Top-N hit | MAE | Coverage 80 | Width |", "|---|---|---|---|---|---|---|---|"]
        for r in sl.sort_values(["position", "spearman"], ascending=[True, False]).itertuples():
            cov = "" if pd.isna(r.coverage_80) else f"{r.coverage_80:.1%}"
            wid = "" if pd.isna(r.interval_width) else f"{r.interval_width:.1f}"
            lines.append(f"| {r.position} | `{r.scorer}` | {r.weeks} | {r.spearman:.3f} | {r.hit_rate:.1%} | {r.mae:.2f} | {cov} | {wid} |")
        lines.append("")
        rl = res[res["league_id"] == league_id]
        for season, rs in rl.groupby("season"):
            lines += [f"### {season}", "", "| Pos | Scorer | Spearman | Top-N hit | MAE | Coverage 80 |", "|---|---|---|---|---|---|"]
            for r in summarize(rs).sort_values(["position", "spearman"], ascending=[True, False]).itertuples():
                cov = "" if pd.isna(r.coverage_80) else f"{r.coverage_80:.1%}"
                lines.append(f"| {r.position} | `{r.scorer}` | {r.spearman:.3f} | {r.hit_rate:.1%} | {r.mae:.2f} | {cov} |")
            lines.append("")
    lines += ["## Verdict (reference league)", ""]
    ref = next(iter(scorings))
    sr = s[s["league_id"] == ref]
    for pos in POSITIONS:
        sp = sr[sr["position"] == pos].set_index("scorer")["spearman"]
        if "baseline" not in sp:
            continue
        best = "v2_points"   # the board ranks by the priced line; P50 is informational
        gap = sp[best] - sp["baseline"]
        verdict = "beats" if gap >= 0.01 else ("ties" if gap > -0.01 else "loses to")
        lines.append(f"- **{pos}**: `{best}` {verdict} the baseline by {gap:+.3f} Spearman.")
    if not imp.empty:
        lines += ["", "## What the P50 model leans on (permutation importance, newest test season)", ""]
        for pos in POSITIONS:
            top = imp[imp["position"] == pos].head(8)
            if not top.empty:
                lines.append(f"- **{pos}**: " + ", ".join(f"{r.feature} ({r.importance:.2f})" for r in top.itertuples()))
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------ entry points
def run_backtest(seasons: str, out: Path | None = None) -> pd.DataFrame:
    s = get_settings()
    with psycopg.connect(s.pipeline_dsn(), autocommit=False) as conn:
        return backtest(conn, parse_seasons(seasons), out)


def run_project(season: int | None = None) -> pd.DataFrame:
    s = get_settings()
    with psycopg.connect(s.pipeline_dsn(), autocommit=False) as conn:
        return project(conn, season)


def run_drift(season: int | None = None) -> pd.DataFrame:
    s = get_settings()
    with psycopg.connect(s.pipeline_dsn(), autocommit=False) as conn:
        return drift(conn, season)
