"""Calibration of the top (plan Iteration 17 B, Wave I-A M1): is the top of the distribution under-projected?

The question
------------
Andrew's examples (Justin Jefferson at 10.0 for a week; Dak #1; Brissett top-8 rest of season) could be (a) the
model pulling the best players toward the middle, (b) usage that really is down, (c) superflex arithmetic. A model
that pulls its top toward the middle is *miscalibrated at the top*: among the player-weeks it projects highest, the
actual points land above the projection on average. That is measurable without any new feature: bin the out-of-sample
projections by how high they are and compare the mean actual with the mean projection in each bin.

What is here
------------
* ``oof_rows`` -- the walk-forward of ``projections.backtest`` (fit on the seasons before S, project S), kept **per
  player-week** instead of aggregated: the projection, the ranges and the league's actual points. ``ops.projection_backtest``
  stores only the per-week scores, so the diagnosis needs these rows (``ops.calibration_oof`` in an experiment clone).
* ``bias_table`` -- bias (mean actual - projected) and MAE by position x projected-points decile, or x projected-rank
  bucket (top 6 / 7-12 / 13-24 / 25+ within the week).
* ``fit_map`` / ``apply_maps`` -- the post-hoc calibration: per position x scoring, a monotone, continuous
  piecewise-linear map from projected points to calibrated points with one knot (the 80th percentile of the fitting
  rows' projections): ``cal(x) = x + level + s_lo x min(x - knot, 0) + s_hi x max(x - knot, 0)``. Two modes:
  'hinge' (level = s_lo = 0, s_hi >= 0: only the top can move, only up) and 'two_piece' (all three). Every coefficient
  is the least-squares fit of (actual - projected), kept only when its player-clustered t-statistic says so (shrunk to
  0 at |t| <= 1), slopes within +-MAX_SLOPE: monotone, and the identity when there is no bias. A two-piece-linear map,
  not isotonic: isotonic's flat steps tie players the model separates (Spearman and the top-N would move for no
  reason), and its jumps follow the noise of the fitting seasons; three numbers per position x scoring are readable.
* ``walk_forward_calibrate`` -- the map for season S fitted only on the out-of-sample rows of seasons < S, applied to S.
* ``score_rows`` -- the harness's terms on any set of rows: MAE, pinball (P10 / P50 / P90), 80% coverage, Spearman and
  top-N hit rate per week (``projections.score_predictions``' definitions).

* ``fit_bonus_curves`` / ``bonus_delta`` -- a measured proposal, not wired: yardage bonuses priced at their probability.

What the walk-forward found (docs/METRICS.md § "Calibration of the top", the M1 report): the top is NOT progressively
under-projected (the slope above the knot is ~0 at every position, t <= 1); what is real is a level a little low near
the starter line and a fringe that is too high (the slope below the knot, t 3-5). The production setting is therefore
the two-piece map, fitted on the last ``WINDOW`` seasons, at the positions where it passed the harness's MAE rule in
the walk-forward (``CAL_POSITIONS``: WR).

Production (``projections.project``) applies it only when ``LEAGUE_LAB_PROJECTION_CALIBRATION=1`` (off by default):
fitted at ``project`` time from ``ops.calibration_oof`` (the seasons before the projected one), applied to the house
leagues' rows and their reference scorings' ranges that ``project`` writes; the B5 freeze keeps every kicked-off week's
stored rows as they were (``frozen_source`` rows are never touched). The stat line is not changed: on-demand leagues,
priced from the line at request time, do not see it.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import psycopg

from . import projections as P
from .scoring import SLEEPER_BONUS_MAP

log = logging.getLogger(__name__)

FLAG = "LEAGUE_LAB_PROJECTION_CALIBRATION"
OOF_TABLE = "ops.calibration_oof"
RANK_BUCKETS = ((1, 6, "top 6"), (7, 12, "7-12"), (13, 24, "13-24"), (25, 10_000, "25+"))
BAND_COLUMNS = ("p10", "p25", "p50", "p75", "p90")

# The map's fixed constants (a change is a new calibration version, like the model's hyper-parameters).
CAL_VERSION = "cal1.0"
MODE = "two_piece"        # see fit_map ('hinge': only the top, only up -- tested, it is the identity almost everywhere)
WINDOW = 3                # production fits on the newest WINDOW seasons before the projected one (the bias drifts by era)
CAL_POSITIONS = ("WR",)   # where the walk-forward passed the harness rule (MAE -0.07 / -0.08, 3 of 3 seasons, both leagues)
KNOT_QUANTILE = 0.80      # the knot: this quantile of the fitting rows' projections (about the starter line)
MAX_SLOPE = 0.5           # slopes within +-0.5 points per point: 1 + slope >= 0.5 > 0, so the map is strictly increasing
MIN_ROWS_ABOVE = 300      # fewer fitting rows above the knot: identity
SHRINK_T = 2.0            # a coefficient is used in full when |t| >= SHRINK_T, scaled linearly to 0 at |t| <= 1


def enabled() -> bool:
    """The production switch: ``LEAGUE_LAB_PROJECTION_CALIBRATION=1`` (off by default)."""
    return os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


# ------------------------------------------------------------------------------ the per-row walk-forward
def oof_rows(frame: pd.DataFrame, seasons: list[int], scorings: dict[str, tuple[str, dict[str, float]]], first: int,
             ranges: bool = True, lines: bool = False) -> pd.DataFrame:
    """Per test season S: per position, the production model fitted on seasons ``first``..S-1 of ``frame`` (exactly
    ``projections.walk_forward``'s fit: ``fit_position`` with the production inputs) applied to every season-S row.
    One output row per scoring x frame row: ``proj_points``, the five band columns (NaN when ``ranges`` is False: the
    component models only, which give the same point projection at a third of the cost) and ``actual`` (the
    scoring's points priced from the outcome columns; NaN for a row that was not played). ``lines``: keep the projected
    stat line (``proj_<component>``) and the outcome columns (``out_<component>``) too."""
    out = []
    for s in seasons:
        train = frame[(frame["season"] >= first) & (frame["season"] < s)]
        test = frame[frame["season"] == s]
        if train.empty or test.empty:
            log.warning("season %s: no train or test rows", s)
            continue
        for pos in P.POSITIONS:
            t0 = time.time()
            rows = test[test["position"] == pos]
            if ranges:
                m = P.fit_position(train, pos, scorings)
                pred = P.predict_position(m, rows, scorings)
            else:
                feats = list(P.FEATURES_BY_POSITION[pos])
                d = train[(train["position"] == pos) & train["played"] & ~train["no_history"]]
                d = d.dropna(subset=[f"out_{c}" for c in P.COMPONENTS[pos]]).reset_index(drop=True)
                models = P._fit_components(P._matrix(d, feats), d, pos)
                x = P._matrix(rows, feats)
                base = rows[["gsis_id", "season", "week", "position"]].copy()
                base["season"], base["week"] = base["season"].astype(int), base["week"].astype(int)
                for c in P.ALL_COMPONENTS:
                    base[f"proj_{c}"] = np.clip(models[c].predict(x), 0, None) if c in models else 0.0
                frames = []
                for lid, (_, scoring) in scorings.items():
                    o = base.copy()
                    o["league_id"], o["proj_points"] = lid, P.price(o, scoring, "proj_")
                    for b in BAND_COLUMNS:
                        o[b] = np.nan
                    frames.append(o)
                pred = pd.concat(frames, ignore_index=True)
            keep = [f"proj_{c}" for c in P.ALL_COMPONENTS] if lines else []
            pred = pred[["gsis_id", "season", "week", "position", "league_id", "proj_points", *BAND_COLUMNS, *keep]]
            ok = rows[[f"out_{c}" for c in P.ALL_COMPONENTS]].notna().all(axis=1) & rows["played"].astype(bool)
            meta = rows[["gsis_id", "player_name", "team", "played", "no_history",
                         *([f"out_{c}" for c in P.ALL_COMPONENTS] if lines else [])]].copy()
            meta["season"], meta["week"] = rows["season"].astype(int), rows["week"].astype(int)
            acts = []
            for lid, (_, scoring) in scorings.items():
                a = meta.copy()
                a["league_id"] = lid
                v = pd.Series(np.nan, index=rows.index)
                if ok.any():
                    v[ok] = P.price(rows[ok], scoring, "out_").to_numpy()
                a["actual"] = v.to_numpy()
                acts.append(a)
            pred = pred.merge(pd.concat(acts, ignore_index=True), on=["gsis_id", "season", "week", "league_id"], how="left",
                              validate="one_to_one")
            pred["train_seasons"] = f"{first}-{s - 1}"
            out.append(pred)
            log.info("oof: season %s %s: %s rows (%s) in %.0f s", s, pos, len(rows), "ranges" if ranges else "points", time.time() - t0)
    return pd.concat(out, ignore_index=True)


# ------------------------------------------------------------------------------ the diagnosis
def rank_bucket(rank: pd.Series) -> pd.Series:
    """'top 6' / '7-12' / '13-24' / '25+' for a 1-based rank."""
    out = pd.Series(pd.NA, index=rank.index, dtype="object")
    for lo, hi, label in RANK_BUCKETS:
        out[(rank >= lo) & (rank <= hi)] = label
    return out


def with_buckets(rows: pd.DataFrame, value: str = "proj_points") -> pd.DataFrame:
    """The played rows (``actual`` known) with ``rank`` (by ``value``, within league x season x week x position: the
    population the harness scores), ``bucket`` (the rank bucket) and ``decile`` (1 = lowest tenth of ``value`` within
    league x position over every season of ``rows``, 10 = the top tenth)."""
    d = rows[rows["actual"].notna() & rows[value].notna()].copy()
    d["rank"] = d.groupby(["league_id", "season", "week", "position"])[value].rank(ascending=False, method="first").astype(int)
    d["bucket"] = rank_bucket(d["rank"])
    d["decile"] = d.groupby(["league_id", "position"])[value].transform(
        lambda s: pd.qcut(s.rank(method="first"), 10, labels=False) + 1).astype(int)
    return d


def bias_table(rows: pd.DataFrame, by: str, value: str = "proj_points", extra: tuple[str, ...] = ()) -> pd.DataFrame:
    """Bias (mean actual - ``value``) and MAE per league x position x ``by`` ('bucket' or 'decile') [x ``extra``], with
    the mean projection, the mean actual, n and the bias's standard error (rows treated as independent: a lower
    bound on the real uncertainty, since a player's weeks are correlated)."""
    d = rows.assign(resid=rows["actual"] - rows[value], abs_err=(rows["actual"] - rows[value]).abs())
    keys = ["league_id", "position", *extra, by]
    g = d.groupby(keys, observed=True)
    out = pd.DataFrame({"n": g.size(), "proj": g[value].mean(), "actual": g["actual"].mean(), "bias": g["resid"].mean(),
                        "se": g["resid"].std(ddof=1) / np.sqrt(g.size()), "mae": g["abs_err"].mean()}).reset_index()
    if by == "bucket":
        order = {label: i for i, (_, _, label) in enumerate(RANK_BUCKETS)}
        out = out.sort_values([*keys[:-1], "bucket"], key=lambda s: s.map(order) if s.name == "bucket" else s)
    return out.reset_index(drop=True)


# ------------------------------------------------------------------------------ the map
@dataclass
class CalMap:
    """``cal(x) = x + level + s_lo x min(x - knot, 0) + s_hi x max(x - knot, 0)``: continuous, two slopes, one knot.
    Monotone by construction (``1 + s_lo`` and ``1 + s_hi`` are at least ``1 - MAX_SLOPE`` > 0). Every coefficient is
    the least-squares fit of the residual (actual - projected) on the fitting rows, kept in full only when its
    player-clustered t-statistic is at least ``SHRINK_T``, scaled down linearly to 0 at |t| <= 1: noise gives the
    identity. ``n_rows`` = 0 (too few rows) is the identity."""
    position: str
    scoring: str
    knot: float = 0.0
    level: float = 0.0
    s_lo: float = 0.0
    s_hi: float = 0.0
    n_rows: int = 0
    t: tuple[float, float, float] = (0.0, 0.0, 0.0)
    seasons: str = ""

    def apply(self, x: np.ndarray | pd.Series) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        z = x - self.knot
        return x + self.level + self.s_lo * np.minimum(z, 0.0) + self.s_hi * np.maximum(z, 0.0)

    @property
    def identity(self) -> bool:
        return self.level == 0.0 and self.s_lo == 0.0 and self.s_hi == 0.0


def _clustered_t(x: np.ndarray, r: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS of ``r`` on the columns of ``x`` and the t-statistics with standard errors clustered by ``groups`` (a
    player's weeks are not independent draws; treating them as such would overstate the evidence)."""
    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ x.T @ r
    e = r - x @ beta
    scores = pd.DataFrame(x * e[:, None]).groupby(groups).sum().to_numpy()
    meat = scores.T @ scores
    cov = xtx_inv @ meat @ xtx_inv
    se = np.sqrt(np.clip(np.diag(cov), 1e-12, None))
    return beta, beta / se


def _shrink(coef: float, t: float) -> float:
    w = float(np.clip((abs(t) - 1.0) / (SHRINK_T - 1.0), 0.0, 1.0))
    return coef * w


def fit_map(proj: np.ndarray, actual: np.ndarray, groups: np.ndarray | None = None, position: str = "", scoring: str = "",
            seasons: str = "", mode: str | None = None) -> CalMap:
    """The map of one position x scoring from out-of-sample (projection, actual) pairs. ``mode`` (default ``MODE``):
    'hinge' -- only the slope above the knot, at least 0: the top can be lifted, nothing below the knot moves;
    'two_piece' -- the level at the knot and both slopes: the whole board can move."""
    mode = mode or MODE
    proj, actual = np.asarray(proj, dtype=float), np.asarray(actual, dtype=float)
    ok = ~np.isnan(proj) & ~np.isnan(actual)
    proj, actual = proj[ok], actual[ok]
    groups = np.arange(len(proj)) if groups is None else np.asarray(groups)[ok]
    if len(proj) < MIN_ROWS_ABOVE / (1 - KNOT_QUANTILE):
        return CalMap(position, scoring, n_rows=0, seasons=seasons)
    knot = float(np.quantile(proj, KNOT_QUANTILE))
    z = proj - knot
    if mode == "hinge":
        above = z > 0
        beta, t = _clustered_t(z[above, None], (actual - proj)[above], groups[above])
        level, s_lo, s_hi = 0.0, 0.0, float(np.clip(_shrink(beta[0], t[0]), 0.0, MAX_SLOPE))
        t = np.array([0.0, 0.0, t[0]])
    else:
        x = np.column_stack([np.ones_like(z), np.minimum(z, 0.0), np.maximum(z, 0.0)])
        beta, t = _clustered_t(x, actual - proj, groups)
        level, s_lo, s_hi = (_shrink(b, tt) for b, tt in zip(beta, t, strict=True))
        s_lo, s_hi = float(np.clip(s_lo, -MAX_SLOPE, MAX_SLOPE)), float(np.clip(s_hi, -MAX_SLOPE, MAX_SLOPE))
    return CalMap(position, scoring, knot=knot, level=float(level), s_lo=s_lo, s_hi=s_hi, n_rows=int(len(proj)),
                  t=tuple(round(float(v), 2) for v in t), seasons=seasons)


def fit_maps(rows: pd.DataFrame, mode: str | None = None) -> dict[tuple[str, str], CalMap]:
    """One map per position x scoring (``league_id``) from played out-of-sample rows (``proj_points``, ``actual``)."""
    d = rows[rows["actual"].notna() & rows["proj_points"].notna()]
    label = f"{int(d['season'].min())}-{int(d['season'].max())}" if len(d) else ""
    return {(pos, lid): fit_map(g["proj_points"].to_numpy(), g["actual"].to_numpy(), g["gsis_id"].to_numpy(), pos, lid, label, mode)
            for (pos, lid), g in d.groupby(["position", "league_id"])}


def apply_maps(rows: pd.DataFrame, maps: dict[tuple[str, str], CalMap], scoring_col: str = "league_id") -> pd.DataFrame:
    """``rows`` with ``proj_points`` calibrated and the five band columns moved by the same amount (the range keeps its
    shape around the new centre; P10 floored at 0, the order P10 <= P25 <= P50 <= P75 <= P90 kept). A position x scoring
    without a map is left as it is. ``proj_points_raw`` keeps the model's number."""
    out = rows.copy()
    out["proj_points_raw"] = out["proj_points"]
    for (pos, lid), m in maps.items():
        if m.identity:
            continue
        sel = (out["position"] == pos) & (out[scoring_col] == lid)
        if not sel.any():
            continue
        raw = out.loc[sel, "proj_points"].to_numpy(dtype=float)
        delta = m.apply(raw) - raw
        out.loc[sel, "proj_points"] = raw + delta
        out.loc[sel] = shift_bands(out.loc[sel], delta)
    return out


def shift_bands(rows: pd.DataFrame, delta: np.ndarray) -> pd.DataFrame:
    """The band columns moved by ``delta`` -- except a band at the floor (0 points) stays there: a fifth of played WR
    weeks score 0, so a P10 of 0 is a point mass, and lifting it would put every zero outside the range. Order
    P10 <= P25 <= P50 <= P75 <= P90 kept, nothing below 0."""
    out = rows.copy()
    bands = [b for b in BAND_COLUMNS if b in out]
    for b in bands:
        v = out[b].to_numpy(dtype=float)
        out[b] = np.where(v <= 0.0, v, np.clip(v + delta, 0.0, None))
    for lo, hi in zip(bands, bands[1:], strict=False):
        out[hi] = np.maximum(out[hi], out[lo])
    return out


def walk_forward_calibrate(oof: pd.DataFrame, seasons: list[int], first_fit: int | None = None, mode: str | None = None,
                           window: int | None = None) -> tuple[pd.DataFrame, list[CalMap]]:
    """For each season S in ``seasons``: maps fitted on the out-of-sample rows of seasons ``first_fit``..S-1 only, applied
    to the season-S rows (``window``: only the newest ``window`` seasons before S). Returns the calibrated rows of
    ``seasons`` and every map (``CalMap.seasons`` = its fit window)."""
    first_fit = int(oof["season"].min()) if first_fit is None else first_fit
    outs, maps = [], []
    for s in seasons:
        lo = first_fit if window is None else max(first_fit, s - window)
        fit_rows = oof[(oof["season"] >= lo) & (oof["season"] < s)]
        m = fit_maps(fit_rows, mode)
        maps.extend(m.values())
        outs.append(apply_maps(oof[oof["season"] == s], m))
    return pd.concat(outs, ignore_index=True), maps


# ------------------------------------------------------------------------------ scoring, in the harness's terms
def score_rows(rows: pd.DataFrame, value: str = "proj_points", min_players: int = 8) -> pd.DataFrame:
    """Per league x season x week x position (played rows, at least ``min_players``): Spearman, top-N hit rate, MAE,
    80% coverage, pinball at P10 / P50 / P90 and the interval score ((pinball 10 + pinball 90) / 2) -- the definitions
    of ``projections.score_predictions`` / ``experiments.summarize_scores``."""
    from .rankings import TOP_N, _hit_rate, _spearman

    d = rows[rows["actual"].notna() & rows[value].notna()]
    out = []
    for (lid, season, week, pos), g in d.groupby(["league_id", "season", "week", "position"]):
        if len(g) < min_players:
            continue
        y = g["actual"].to_numpy(dtype=float)
        rec = {"league_id": lid, "season": int(season), "week": int(week), "position": pos, "n_players": len(g),
               "spearman": _spearman(g[value], g["actual"]), "hit_rate": _hit_rate(g[value], g["actual"], TOP_N[pos]),
               "mae": float(np.mean(np.abs(g[value].to_numpy(dtype=float) - y)))}
        if "p10" in g and g["p10"].notna().all():
            rec |= {"coverage_80": float(((y >= g["p10"]) & (y <= g["p90"])).mean()),
                    "pinball_10": P._pinball(y, g["p10"].to_numpy(dtype=float), 0.1),
                    "pinball_50": P._pinball(y, g["p50"].to_numpy(dtype=float), 0.5),
                    "pinball_90": P._pinball(y, g["p90"].to_numpy(dtype=float), 0.9)}
            rec["interval_score"] = (rec["pinball_10"] + rec["pinball_90"]) / 2
        out.append(rec)
    return pd.DataFrame(out)


def compare(base: pd.DataFrame, cal: pd.DataFrame, by: tuple[str, ...] = ("league_id", "position")) -> pd.DataFrame:
    """Weekly scores of the model's numbers vs the calibrated ones, averaged over weeks per ``by`` (+ the deltas and
    the number of seasons in which the calibrated MAE is lower)."""
    metrics = ["spearman", "hit_rate", "mae", "coverage_80", "pinball_10", "pinball_50", "pinball_90", "interval_score"]
    b, c = score_rows(base), score_rows(cal)
    keys = ["league_id", "season", "week", "position"]
    m = b.merge(c, on=[*keys, "n_players"], suffixes=("_base", "_cal"))
    g = m.groupby(list(by))
    out = pd.DataFrame({"weeks": g.size(), "player_weeks": g["n_players"].sum()})
    for k in metrics:
        if f"{k}_base" in m:
            out[f"{k}_base"], out[f"{k}_cal"] = g[f"{k}_base"].mean(), g[f"{k}_cal"].mean()
            out[f"d_{k}"] = out[f"{k}_cal"] - out[f"{k}_base"]
    season_mae = m.groupby([*by, "season"])[["mae_base", "mae_cal"]].mean()
    out["seasons_mae_better"] = (season_mae["mae_cal"] < season_mae["mae_base"]).groupby(list(by)).sum()
    out["seasons"] = season_mae.groupby(list(by)).size()
    return out.reset_index()


# ------------------------------------------------------------------------------ production (behind the flag)
OOF_DDL = f"""create table if not exists {OOF_TABLE} (
    gsis_id text, season integer, week integer, position text, league_id text, proj_points double precision,
    actual double precision, train_seasons text, built_at timestamptz)"""
OOF_FIRST_SEASON = 2019    # the first season projected out of sample (trained on 2016-2018)


def write_oof(conn: psycopg.Connection, rows: pd.DataFrame) -> int:
    """Replace ``ops.calibration_oof`` with the played out-of-sample rows (what the maps are fitted on)."""
    from datetime import UTC, datetime

    d = rows[rows["actual"].notna()][["gsis_id", "season", "week", "position", "league_id", "proj_points", "actual", "train_seasons"]].copy()
    d["built_at"] = datetime.now(UTC)
    with conn.cursor() as cur:
        cur.execute(OOF_DDL)
        cur.execute(f"truncate {OOF_TABLE}")
        with cur.copy(f"copy {OOF_TABLE} ({', '.join(d.columns)}) from stdin") as cp:
            for rec in d.itertuples(index=False):
                cp.write_row([None if (isinstance(v, float) and np.isnan(v)) else v for v in rec])
    conn.commit()
    log.info("%s: %s rows (seasons %s-%s)", OOF_TABLE, len(d), d["season"].min(), d["season"].max())
    return len(d)


def load_oof(conn: psycopg.Connection, before_season: int) -> pd.DataFrame | None:
    """The stored out-of-sample rows of the seasons before ``before_season``; None when the table is missing."""
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s)", (OOF_TABLE,))
        if cur.fetchone()[0] is None:
            return None
        cur.execute(f"select gsis_id, season, week, position, league_id, proj_points, actual from {OOF_TABLE} where season < %s",
                    (before_season,))
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    return df.astype({"proj_points": float, "actual": float})


def calibrate_outputs(conn: psycopg.Connection, season: int, pred: pd.DataFrame, ranges: pd.DataFrame,
                      source: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``projections.project``'s hook. Flag off (the default): ``pred`` and ``ranges`` returned untouched. Flag on: the
    maps fitted on ``ops.calibration_oof`` (seasons before ``season``; the house leagues' scorings, the ones the
    backtest prices) applied to the house leagues' rows (``pred``, QB-TE) and to the ranges of the reference scorings
    those leagues are (``source``). The stat line is not changed, so on-demand leagues (priced from the line at
    request time) do not see it. ``project`` writes through the B5 freeze, so kicked-off weeks keep their stored rows."""
    if not enabled():
        return pred, ranges
    oof = load_oof(conn, season)
    oof = oof[(oof["season"] >= season - WINDOW) & oof["position"].isin(CAL_POSITIONS)] if oof is not None else None
    if oof is None or oof.empty:
        log.warning("%s=1 but %s has no rows for %s-%s (run calibration.run_build_oof): projections not calibrated", FLAG,
                    OOF_TABLE, season - WINDOW, season - 1)
        return pred, ranges
    maps = fit_maps(oof)
    for m in maps.values():
        log.info("calibration %s %s %s: knot %.2f, level %.3f, slope below %.3f, above %.3f (t %s, %s rows %s)", CAL_VERSION,
                 m.position, m.scoring[-6:], m.knot, m.level, m.s_lo, m.s_hi, m.t, m.n_rows, m.seasons)
    qbte = pred["position"].isin(P.POSITIONS)
    out = pd.concat([apply_maps(pred[qbte], maps).drop(columns="proj_points_raw"), pred[~qbte]], ignore_index=True)
    out.attrs = pred.attrs
    by_ref = {(pos, source[lid]): m for (pos, lid), m in maps.items() if lid in source}
    rng = apply_maps(ranges, by_ref, scoring_col="scoring_name").drop(columns="proj_points_raw") if len(ranges) else ranges
    moved = int((out["proj_points"].to_numpy() != pd.concat([pred[qbte], pred[~qbte]])["proj_points"].to_numpy()).sum())
    log.info("calibration %s applied: %s of %s house rows moved", CAL_VERSION, moved, len(out))
    return out, rng


def run_build_oof(seasons: list[int] | None = None) -> int:
    """Offline (``uv run python -c "from league_lab.calibration import run_build_oof; run_build_oof()"``, ~2 CPU-min with
    ``OMP_NUM_THREADS=1``): the point projection of the newest ``WINDOW`` completed seasons (default; any seasons from
    ``OOF_FIRST_SEASON`` on request), each fitted on the seasons before it, priced in the house leagues' scorings ->
    ``ops.calibration_oof``. Re-run once a season, after it ends (the next season's map is fitted on it)."""
    from .config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        scorings = P.league_scorings(conn)
        alls = P.available_seasons(conn)
        done = [s for s in alls if s >= OOF_FIRST_SEASON and s < max(alls)]
        seasons = seasons or done[-WINDOW:]
        frame = P.load_frame(conn, [s for s in alls if s <= max(seasons)])
        rows = oof_rows(frame, seasons, scorings, min(alls), ranges=False)
        return write_oof(conn, rows)


# ------------------------------------------------------------------------------ expected yardage bonuses (measured proposal)
# What the diagnosis found behind the dynasty league's top-24 gap: a per-game yardage bonus (Sleeper's
# bonus_rec_yd_100 etc., scoring.SLEEPER_BONUS_MAP) is priced on the projected line deterministically, so a receiver
# projected for 85 yards gets none of the 3-point 100-yard bonus although he crosses 100 in about one game in four.
# The fix measured here prices each bonus at its probability: P(yards >= threshold | projected yards), an isotonic
# (increasing) curve per position x stat x threshold fitted on out-of-sample rows of earlier seasons. Scoring-free
# (the curves), so it would serve any league's bonus keys; not wired into production (the PO's decision).
BONUS_THRESHOLDS: dict[str, tuple[int, ...]] = {
    col: tuple(sorted({b for c, lo, hi, _ in SLEEPER_BONUS_MAP.values() if c == col for b in (lo, hi) if b is not None}))
    for col in dict.fromkeys(c for c, *_ in SLEEPER_BONUS_MAP.values())}


def fit_bonus_curves(rows: pd.DataFrame, min_rows: int = 200) -> dict[tuple[str, str, int], object]:
    """(position, stat, threshold) -> isotonic P(out_<stat> >= threshold | proj_<stat>) from played rows carrying the
    projected line and the outcome columns."""
    from sklearn.isotonic import IsotonicRegression

    d = rows[rows["actual"].notna()]
    curves: dict[tuple[str, str, int], object] = {}
    for pos, g in d.groupby("position"):
        for col, thresholds in BONUS_THRESHOLDS.items():
            x, y = g[f"proj_{col}"].to_numpy(dtype=float), g[f"out_{col}"].to_numpy(dtype=float)
            ok = ~np.isnan(x) & ~np.isnan(y)
            if ok.sum() < min_rows:
                continue
            for t in thresholds:
                curves[(pos, col, t)] = IsotonicRegression(increasing=True, out_of_bounds="clip", y_min=0, y_max=1).fit(
                    x[ok], (y[ok] >= t).astype(float))
    return curves


def bonus_delta(rows: pd.DataFrame, scoring: dict[str, float], curves: dict[tuple[str, str, int], object]) -> np.ndarray:
    """Per row: expected bonus points (each bonus key's weight x P(its bucket)) minus the bonus the projected line
    pays deterministically. 0 for a scoring without yardage bonuses."""
    delta = np.zeros(len(rows))
    pos = rows["position"].to_numpy()
    for key, (col, lo, hi, _) in SLEEPER_BONUS_MAP.items():
        w = float(scoring.get(key) or 0.0)
        if not w:
            continue
        x = rows[f"proj_{col}"].to_numpy(dtype=float)
        det = (x >= lo) & ((x < hi) if hi is not None else True)
        p = np.zeros(len(rows))
        for position in np.unique(pos):
            sel = pos == position
            c_lo, c_hi = curves.get((position, col, lo)), curves.get((position, col, hi)) if hi is not None else None
            if c_lo is None:
                p[sel] = det[sel]          # no curve: keep the deterministic price
                continue
            p_lo = c_lo.predict(np.nan_to_num(x[sel]))
            p_hi = c_hi.predict(np.nan_to_num(x[sel])) if c_hi is not None else 0.0
            p[sel] = np.clip(p_lo - p_hi, 0, 1)
        delta += w * (p - det)
    return delta
