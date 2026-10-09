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

v3.2 (M6, Wave I-H): the cold-start prior is the exception -- ``blend_lines`` scales a cold start's STAT LINE before
anything is priced (``LEAGUE_LAB_COLD_START``, on by default), so the house rows, the NFL-wide line, the ranges and
every request carry the same number. ``ensure_oof`` keeps ``ops.calibration_oof`` current where the nightly runs.
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
        _put_bands(out, sel.to_numpy(), shift_bands(out.loc[sel], delta))   # M5: column by column
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


def _put_bands(out: pd.DataFrame, sel: np.ndarray, moved: pd.DataFrame, prefix: str = "") -> None:
    """Write the band columns of ``moved`` (the ``sel`` rows) back into ``out`` column by column (M5: a whole-row
    ``out.loc[sel] = frame`` silently kept the old bands on frames carrying string / bool helper columns)."""
    for b in BAND_COLUMNS:
        if f"{prefix}{b}" in out and f"{prefix}{b}" in moved:
            out.loc[sel, f"{prefix}{b}"] = moved[f"{prefix}{b}"].to_numpy(dtype=float)


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
    d["model_version"] = P.MODEL_VERSION          # ---- M6: what ``ensure_oof`` checks (a model bump rebuilds)
    with conn.cursor() as cur:
        cur.execute(OOF_DDL)
        cur.execute(OOF_MODEL_DDL)                # ---- M6
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
    """``projections.project``'s hook. Flags off (the default): ``pred`` and ``ranges`` returned untouched. cal1.0's flag
    on: the maps fitted on ``ops.calibration_oof`` (seasons before ``season``; the house leagues' scorings, the ones the
    backtest prices) applied to the house leagues' rows (``pred``, QB-TE) and to the ranges of the reference scorings
    those leagues are (``source``). The stat line is not changed, so on-demand leagues (priced from the line at
    request time) do not see it. ``project`` writes through the B5 freeze, so kicked-off weeks keep their stored rows.
    M5 (Wave I-G): then the fringe level and the cold-start prior, each behind its own switch (``v31_outputs``)."""
    if enabled():
        pred, ranges = _cal10_outputs(conn, season, pred, ranges, source)
    # ---- M5 (Wave I-G); M6 (Wave I-H): the cold-start prior acts on the stat line before it is priced
    # (``blend_lines``, called by ``project``), never here on the points: only the fringe level is left in v31_outputs
    if fringe_enabled():
        pred, ranges = v31_outputs(conn, season, pred, ranges, source)
    # ---- /M5
    return pred, ranges


def _cal10_outputs(conn: psycopg.Connection, season: int, pred: pd.DataFrame, ranges: pd.DataFrame,
                   source: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """cal1.0 (M1): the two-piece maps of ``CAL_POSITIONS`` applied (``calibrate_outputs`` checks the flag)."""
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


# ---- M5 (Wave I-G): v3.1 -- the fringe level and cold starts (docs/METRICS.md § "Calibration of the top" -> "v3.1").
# Both are post-hoc corrections of the priced point projection, measured walk-forward on the out-of-sample rows and
# judged by the harness's rules (experiments.decide); each has its own switch, off by default, and moves the ranges
# with the point (``shift_bands``) as cal1.0's map does.
FRINGE_FLAG = P.FRINGE_FLAG              # LEAGUE_LAB_FRINGE_LEVEL (the switches are named in projections.py)
COLD_START_FLAG = P.COLD_START_FLAG      # LEAGUE_LAB_COLD_START
FRINGE_VERSION = "fr1.0"
FRINGE_TOP = 24                      # the protected top: at or above the weekly 24th projection nothing moves
FRINGE_TIERS = (36, 60)              # fringe tiers by weekly rank: 25-36, 37-60, 61+ (cut points in projected points)
FRINGE_MIN_ROWS = 300                # a tier with fewer fitting rows joins the one above it
FRINGE_FLOOR = 0.5                   # cal(x) >= FRINGE_FLOOR x: a fringe player is never priced below half his line
COLD_N = 3                           # cold start: fewer than COLD_N career games before the week
COLD_VERSION = "cs1.0"
DRAFT_BUCKETS = ((1, 32, "pick 1-32"), (33, 64, "pick 33-64"), (65, 128, "pick 65-128"), (129, 400, "pick 129+"))
COLD_SHRINK = 30                     # a bucket's prior is shrunk to the position's by n / (n + COLD_SHRINK)
COLD_GRID = tuple(round(0.1 * k, 1) for k in range(11))   # the blend weight on the model, fitted per games-played step


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def fringe_enabled() -> bool:
    """``LEAGUE_LAB_FRINGE_LEVEL=1`` (off by default)."""
    return _flag(FRINGE_FLAG)


def cold_start_enabled() -> bool:
    """``LEAGUE_LAB_COLD_START``: M6 (Wave I-H) moved the blend onto the stat line (``blend_lines``); unset or empty =
    ``COLD_DEFAULT`` (the harness's verdict on the line, docs/METRICS.md § "v3.2"), ``1`` / ``0`` either way."""
    v = os.environ.get(COLD_START_FLAG)
    if v is None or not v.strip():
        return COLD_DEFAULT
    return _flag(COLD_START_FLAG)


@dataclass
class FringeMap:
    """``cal(x) = max(x + level(x), FRINGE_FLOOR x)``, ``level`` piecewise linear through ``knots`` (projected points,
    ascending) and ``levels``: 0 at and above the top cut (the last knot), flat below the first. The levels are the
    fringe tiers' mean residuals (actual - projected), player-clustered and shrunk like cal1.0's coefficients, then
    limited so that ``level`` never falls faster than MAX_SLOPE per point: ``cal`` is strictly increasing, so the order
    within a position (Spearman, the top N) never changes. No knots = the identity."""
    position: str
    scoring: str
    knots: tuple[float, ...] = ()
    levels: tuple[float, ...] = ()
    t: tuple[float, ...] = ()
    n_rows: int = 0
    seasons: str = ""

    def level(self, x: np.ndarray | pd.Series) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        if not self.knots:
            return np.zeros_like(x)
        return np.interp(x, np.asarray(self.knots), np.asarray(self.levels))

    def apply(self, x: np.ndarray | pd.Series) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        if not self.knots:
            return x.copy()
        return np.maximum(x + self.level(x), FRINGE_FLOOR * x)

    @property
    def identity(self) -> bool:
        return not self.knots or all(v == 0.0 for v in self.levels)


def fit_fringe(rows: pd.DataFrame, position: str = "", scoring: str = "", actual: str = "actual") -> FringeMap:
    """One position x scoring's fringe map from played out-of-sample rows (``proj_points``, ``actual``, ``gsis_id``,
    ``season``, ``week``): the weekly rank cut points (median over the weeks of the 24th / 36th / 60th projection) give
    the tiers, each fringe tier's level is its shrunk mean residual at the tier's median projection, and the top cut
    is anchored at 0."""
    d = rows[rows[actual].notna() & rows["proj_points"].notna()]
    label = f"{int(d['season'].min())}-{int(d['season'].max())}" if len(d) else ""
    if len(d) < FRINGE_MIN_ROWS:
        return FringeMap(position, scoring, n_rows=len(d), seasons=label)
    wk = d.groupby(["season", "week"])["proj_points"]
    cuts = []
    for r in (FRINGE_TOP, *FRINGE_TIERS):
        nth = wk.apply(lambda s, r=r: np.sort(s.to_numpy())[::-1][r - 1] if len(s) >= r else np.nan).dropna()
        cuts.append(float(nth.median()) if len(nth) else np.nan)
    top = cuts[0]
    if np.isnan(top):
        return FringeMap(position, scoring, n_rows=len(d), seasons=label)
    edges = [top] + [c for c in cuts[1:] if not np.isnan(c) and c < top] + [-np.inf]
    x, resid = d["proj_points"].to_numpy(dtype=float), (d[actual] - d["proj_points"]).to_numpy(dtype=float)
    groups = d["gsis_id"].to_numpy()
    tiers: list[np.ndarray] = []
    for hi, lo in zip(edges, edges[1:], strict=False):
        sel = (x < hi) & (x >= lo)
        if sel.sum() < FRINGE_MIN_ROWS and tiers:
            tiers[-1] = tiers[-1] | sel          # too few rows: joins the tier above
        elif sel.sum() > 0:
            tiers.append(sel)
    knots, levels, ts = [], [], []
    for sel in tiers:
        if sel.sum() < FRINGE_MIN_ROWS:
            continue
        beta, t = _clustered_t(np.ones((int(sel.sum()), 1)), resid[sel], groups[sel])
        knots.append(float(np.median(x[sel])))
        levels.append(_shrink(float(beta[0]), float(t[0])))
        ts.append(round(float(t[0]), 2))
    if not knots:
        return FringeMap(position, scoring, n_rows=len(d), seasons=label)
    order = np.argsort(knots)
    knots, levels, ts = [knots[i] for i in order] + [top], [levels[i] for i in order] + [0.0], [ts[i] for i in order]
    for i in range(len(knots) - 2, -1, -1):      # from the top down: never steeper than MAX_SLOPE (cal increasing)
        levels[i] = min(levels[i], levels[i + 1] + MAX_SLOPE * (knots[i + 1] - knots[i]))
    return FringeMap(position, scoring, tuple(knots), tuple(float(v) for v in levels), tuple(ts), int(len(d)), label)


def fit_fringes(rows: pd.DataFrame, actual: str = "actual") -> dict[tuple[str, str], FringeMap]:
    d = rows[rows[actual].notna() & rows["proj_points"].notna()]
    return {(pos, lid): fit_fringe(g, pos, lid, actual) for (pos, lid), g in d.groupby(["position", "league_id"])}


def apply_fringe(rows: pd.DataFrame, maps: dict[tuple[str, str], FringeMap], scoring_col: str = "league_id",
                 band_prefix: str = "") -> pd.DataFrame:
    """``rows`` with ``proj_points`` moved by the maps and the band columns (``<band_prefix>p10`` ...) by the same
    amount (``shift_bands``: a band at 0 stays). ``proj_points_raw`` keeps the model's number."""
    out = rows.copy()
    out["proj_points_raw"] = out["proj_points"]
    for (pos, lid), m in maps.items():
        if m.identity:
            continue
        sel = ((out["position"] == pos) & (out[scoring_col] == lid)).to_numpy()
        if not sel.any():
            continue
        raw = out.loc[sel, "proj_points"].to_numpy(dtype=float).copy()
        delta = m.apply(raw) - raw
        out.loc[sel, "proj_points"] = raw + delta
        _put_bands(out, sel, _shift_prefixed(out.loc[sel], delta, band_prefix), band_prefix)
    return out


def _shift_prefixed(rows: pd.DataFrame, delta: np.ndarray, prefix: str) -> pd.DataFrame:
    if not prefix:
        return shift_bands(rows, delta)
    cols = [f"{prefix}{b}" for b in BAND_COLUMNS if f"{prefix}{b}" in rows]
    moved = shift_bands(rows[cols].rename(columns=lambda c: c[len(prefix):]), delta)
    out = rows.copy()
    for c in cols:
        out[c] = moved[c[len(prefix):]].to_numpy()
    return out


def walk_forward_fringe(oof: pd.DataFrame, seasons: list[int], window: int = WINDOW, actual: str = "actual",
                        band_prefix: str = "") -> tuple[pd.DataFrame, list[FringeMap]]:
    """For each season S: the maps fitted on the out-of-sample rows of the ``window`` seasons before S only, applied
    to the season-S rows."""
    outs, maps = [], []
    for s in seasons:
        fit_rows = oof[(oof["season"] >= s - window) & (oof["season"] < s)]
        m = fit_fringes(fit_rows, actual)
        maps.extend(m.values())
        outs.append(apply_fringe(oof[oof["season"] == s], m, band_prefix=band_prefix))
    return pd.concat(outs, ignore_index=True), maps


# ------------------------------------------------------------------------------ cold starts
def draft_bucket(pick: pd.Series | np.ndarray) -> np.ndarray:
    """'pick 1-32' ... 'pick 129+' for an overall draft pick; 'undrafted' when there is none."""
    p = pd.to_numeric(pd.Series(np.asarray(pick, dtype=object)), errors="coerce").to_numpy(dtype=float)
    out = np.full(len(p), "undrafted", dtype=object)
    for lo, hi, label in DRAFT_BUCKETS:
        out[(p >= lo) & (p <= hi)] = label
    return out


def is_cold(career_games_before: pd.Series | np.ndarray, career_before_2016: pd.Series | np.ndarray | None = None,
            n: int = COLD_N) -> np.ndarray:
    """A cold start: fewer than ``n`` played regular-season games before the week (a career that began before the
    history window, ``career_before_2016``, is never cold)."""
    g = pd.to_numeric(pd.Series(np.asarray(career_games_before, dtype=object)), errors="coerce").fillna(0).to_numpy(dtype=float)
    old = (np.zeros(len(g), dtype=bool) if career_before_2016 is None
           else pd.Series(np.asarray(career_before_2016, dtype=object)).fillna(False).astype(bool).to_numpy())
    return (g < n) & ~old


@dataclass
class ColdPrior:
    """Per position x scoring: the mean actual of cold-start player-weeks by draft bucket (shrunk to the position's)
    and the fitted weight on the model's projection per games-played step (``weights[g]`` for g = 0 .. COLD_N - 1;
    1.0 = the model unchanged). At COLD_N games and beyond the blend is the identity."""
    position: str
    scoring: str
    prior: dict[str, float]
    weights: tuple[float, ...]
    n_rows: int = 0
    seasons: str = ""

    def blend(self, proj: np.ndarray, games: np.ndarray, bucket: np.ndarray, cold: np.ndarray) -> np.ndarray:
        proj = np.asarray(proj, dtype=float)
        g = np.clip(np.nan_to_num(np.asarray(games, dtype=float), nan=0.0), 0, COLD_N).astype(int)   # unknown: ``cold`` decides
        w = np.where(cold & (g < COLD_N), np.asarray([*self.weights, 1.0])[np.minimum(g, COLD_N)], 1.0)
        pr = np.array([self.prior.get(b, self.prior.get("all", np.nan)) for b in bucket], dtype=float)
        return np.where(np.isnan(pr), proj, w * proj + (1.0 - w) * np.nan_to_num(pr))


def blend_identity_at(n: int = COLD_N) -> bool:
    """The rule the tests pin: a player with ``n`` games of history is never blended."""
    cp = ColdPrior("WR", "x", {"all": 10.0}, tuple(0.0 for _ in range(n)))
    return bool(cp.blend(np.array([3.0]), np.array([n]), np.array(["all"]), np.array([False]))[0] == 3.0)


def fit_cold_prior(rows: pd.DataFrame, position: str = "", scoring: str = "", actual: str = "actual") -> ColdPrior:
    """From played rows of earlier seasons carrying ``proj_points``, ``actual``, ``career_games_before``, ``cold`` and
    ``bucket``: the prior per draft bucket (cold rows only) and, per games-played step, the weight on the model that
    minimises the absolute error of ``w proj + (1 - w) prior`` (``COLD_GRID``)."""
    d = rows[rows[actual].notna() & rows["proj_points"].notna()]
    c = d[d["cold"].astype(bool)]
    label = f"{int(d['season'].min())}-{int(d['season'].max())}" if len(d) else ""
    if len(c) < 30:
        return ColdPrior(position, scoring, {}, tuple(1.0 for _ in range(COLD_N)), len(c), label)
    pos_mean = float(c[actual].mean())
    prior = {"all": pos_mean}
    for b, g in c.groupby("bucket"):
        n = len(g)
        prior[str(b)] = (n * float(g[actual].mean()) + COLD_SHRINK * pos_mean) / (n + COLD_SHRINK)
    pr = np.array([prior.get(b, pos_mean) for b in c["bucket"]], dtype=float)
    games = np.clip(np.nan_to_num(c["career_games_before"].to_numpy(dtype=float), nan=0.0), 0, COLD_N).astype(int)
    weights = []
    for k in range(COLD_N):
        sel = games == k
        if sel.sum() < 30:
            weights.append(1.0)
            continue
        p, y, q = c["proj_points"].to_numpy(dtype=float)[sel], c[actual].to_numpy(dtype=float)[sel], pr[sel]
        errs = [np.mean(np.abs(w * p + (1 - w) * q - y)) for w in COLD_GRID]
        weights.append(float(COLD_GRID[int(np.argmin(errs))]))
    return ColdPrior(position, scoring, prior, tuple(weights), len(c), label)


def walk_forward_cold(oof: pd.DataFrame, seasons: list[int], actual: str = "actual", band_prefix: str = "",
                      first_fit: int | None = None) -> tuple[pd.DataFrame, list[ColdPrior]]:
    """For each season S: the priors fitted on the rows of seasons ``first_fit``..S-1, blended into the season-S rows
    (the bands move with the point). ``oof`` carries ``career_games_before``, ``cold`` and ``bucket``."""
    first_fit = int(oof["season"].min()) if first_fit is None else first_fit
    outs, fits = [], []
    for s in seasons:
        fit_rows = oof[(oof["season"] >= first_fit) & (oof["season"] < s)]
        out = oof[oof["season"] == s].copy()
        out["proj_points_raw"] = out["proj_points"]
        for (pos, lid), g in fit_rows.groupby(["position", "league_id"]):
            cp = fit_cold_prior(g, pos, lid, actual)
            fits.append(cp)
            sel = ((out["position"] == pos) & (out["league_id"] == lid)).to_numpy()
            if not sel.any() or not cp.prior:
                continue
            raw = out.loc[sel, "proj_points"].to_numpy(dtype=float).copy()   # a copy: the view would follow the write below
            new = cp.blend(raw, out.loc[sel, "career_games_before"].to_numpy(dtype=float), out.loc[sel, "bucket"].to_numpy(),
                           out.loc[sel, "cold"].to_numpy(dtype=bool))
            delta = new - raw
            out.loc[sel, "proj_points"] = new
            _put_bands(out, sel, _shift_prefixed(out.loc[sel], delta, band_prefix), band_prefix)
        outs.append(out)
    return pd.concat(outs, ignore_index=True), fits
# ------------------------------------------------------------------------------ v3.1 in production (behind the switches)
# The positions where the harness kept each correction (docs/METRICS.md § "Calibration of the top" -> "v3.1"); a switch
# turned on applies its correction at these positions only (empty: the switch logs that and changes nothing).
FRINGE_POSITIONS: tuple[str, ...] = ()                 # dropped at every position (the walk-forward, 2021-2025)
COLD_POSITIONS: tuple[str, ...] = ("RB", "WR", "TE")   # kept: cold-start MAE -0.16 / -0.31 / -0.30 (QB: the identity)
HISTORY_FIRST_SEASON = 2016     # the history window's first season: a career that began earlier is never a cold start

# every played regular-season game, whatever the position he was listed at that week (a fullback or a converted tight
# end has a career: counting only QB-TE weeks made Alec Ingold a "cold start" in 2026)
GAMES_SQL = """select gsis_id, season, week from analytics.fct_player_game where season_type = 'REG' and played"""
DRAFT_SQL = "select gsis_id, draft_pick, rookie_season from analytics.dim_player"


def career_games_before(rows: pd.DataFrame, games: pd.DataFrame) -> np.ndarray:
    """Per row of ``rows`` (gsis_id, season, week): the player's played regular-season games in ``games`` (gsis_id,
    season, week) strictly before that week -- for a week not played yet, every game so far."""
    if rows.empty:
        return np.zeros(0)
    g = games.assign(key=games["season"].astype(int) * 100 + games["week"].astype(int)).sort_values("key")
    g = g.assign(n=g.groupby("gsis_id").cumcount() + 1)[["gsis_id", "key", "n"]]
    r = rows[["gsis_id"]].assign(key=rows["season"].astype(int).to_numpy() * 100 + rows["week"].astype(int).to_numpy(),
                                 _i=np.arange(len(rows)))
    m = pd.merge_asof(r.sort_values("key"), g, on="key", by="gsis_id", allow_exact_matches=False, direction="backward")
    return m.sort_values("_i")["n"].fillna(0).to_numpy(dtype=float)


def cold_columns(rows: pd.DataFrame, games: pd.DataFrame, draft: pd.DataFrame) -> pd.DataFrame:
    """``rows`` with ``career_games_before``, ``cold`` and ``bucket`` (the draft-slot bucket)."""
    out = rows.copy()
    out["career_games_before"] = career_games_before(out, games)
    dr = draft.drop_duplicates("gsis_id").set_index("gsis_id")
    pick = out["gsis_id"].map(dr["draft_pick"]) if len(dr) else pd.Series(np.nan, index=out.index)
    rookie = out["gsis_id"].map(dr["rookie_season"]) if len(dr) else pd.Series(np.nan, index=out.index)
    out["bucket"] = draft_bucket(pick)
    early = pd.to_numeric(rookie, errors="coerce") < HISTORY_FIRST_SEASON
    out["cold"] = is_cold(out["career_games_before"], early.to_numpy())
    return out


def v31_outputs(conn: psycopg.Connection, season: int, pred: pd.DataFrame, ranges: pd.DataFrame,
                source: dict[str, str], cold_on_points: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The fringe level (``LEAGUE_LAB_FRINGE_LEVEL``) on the house leagues' rows and their reference ranges, fitted on
    ``ops.calibration_oof`` (the ``WINDOW`` seasons before ``season``), at the positions the harness kept. A missing
    table or no kept position: unchanged, logged. ``cold_on_points``: M5's cold-start blend on the points (kept for
    the comparison; ``project`` blends the stat line instead -- ``blend_lines``, M6)."""
    oof = load_oof(conn, season)
    if oof is None or oof.empty:
        log.warning("v3.1 switches on but %s is empty (run calibration.run_build_oof): unchanged", OOF_TABLE)
        return pred, ranges
    oof = oof[oof["season"] >= season - WINDOW]
    qbte = pred["position"].isin(P.POSITIONS)
    house, other = pred[qbte].copy(), pred[~qbte]
    rng = ranges.copy()
    if fringe_enabled():
        maps = {k: m for k, m in fit_fringes(oof[oof["position"].isin(FRINGE_POSITIONS)]).items()}
        if not maps:
            log.warning("%s=1 but no position is kept (FRINGE_POSITIONS is empty): unchanged", FRINGE_FLAG)
        for m in maps.values():
            log.info("fringe %s %s %s: knots %s levels %s (t %s, %s rows %s)", FRINGE_VERSION, m.position, m.scoring[-6:],
                     [round(k, 2) for k in m.knots], [round(v, 3) for v in m.levels], m.t, m.n_rows, m.seasons)
        house = apply_fringe(house, maps).drop(columns="proj_points_raw")
        by_ref = {(pos, source[lid]): m for (pos, lid), m in maps.items() if lid in source}
        if len(rng):
            rng = apply_fringe(rng, by_ref, scoring_col="scoring_name").drop(columns="proj_points_raw")
    if cold_on_points and cold_start_enabled():     # M5's wiring (the harness's comparison); production: blend_lines
        if not COLD_POSITIONS:
            log.warning("%s=1 but no position is kept (COLD_POSITIONS is empty): unchanged", COLD_START_FLAG)
        else:
            with conn.cursor() as cur:
                cur.execute(GAMES_SQL)
                games = pd.DataFrame(cur.fetchall(), columns=["gsis_id", "season", "week"])
                cur.execute(DRAFT_SQL)
                draft = pd.DataFrame(cur.fetchall(), columns=["gsis_id", "draft_pick", "rookie_season"])
            fit_rows = cold_columns(oof[oof["position"].isin(COLD_POSITIONS)], games, draft)
            priors = {(pos, lid): fit_cold_prior(g, pos, lid) for (pos, lid), g in fit_rows.groupby(["position", "league_id"])}
            house = _blend_rows(cold_columns(house, games, draft), priors, "league_id")
            by_ref = {(pos, source[lid]): cp for (pos, lid), cp in priors.items() if lid in source}
            if len(rng):
                rng = _blend_rows(cold_columns(rng, games, draft), by_ref, "scoring_name")
    out = pd.concat([house, other], ignore_index=True)
    out.attrs = pred.attrs
    return out, rng


def _blend_rows(rows: pd.DataFrame, priors: dict[tuple[str, str], ColdPrior], scoring_col: str) -> pd.DataFrame:
    out = rows.copy()
    for (pos, key), cp in priors.items():
        sel = ((out["position"] == pos) & (out[scoring_col] == key)).to_numpy()
        if not sel.any() or not cp.prior:
            continue
        raw = out.loc[sel, "proj_points"].to_numpy(dtype=float).copy()   # a copy: the view would follow the write below
        new = cp.blend(raw, out.loc[sel, "career_games_before"].to_numpy(dtype=float), out.loc[sel, "bucket"].to_numpy(),
                       out.loc[sel, "cold"].to_numpy(dtype=bool))
        delta = new - raw
        out.loc[sel, "proj_points"] = new
        _put_bands(out, sel, shift_bands(out.loc[sel], delta))
        log.info("cold start %s %s %s: weights %s, %s rows blended", COLD_VERSION, pos, str(key)[-6:], cp.weights,
                 int((delta != 0).sum()))
    return out.drop(columns=["career_games_before", "cold", "bucket"])
# ---- /M5


# ---- M6 (Wave I-H): v3.2 -- the cold-start prior on the stat line, veterans on a new team (docs/METRICS.md
# § "Calibration of the top" -> "v3.2"). M5's blend moved the house leagues' points and not the line, so a request
# priced from ``ops.projection_lines`` showed the unblended number (IB-0's two numbers). Here the blend sets ONE scale
# per player-week -- blended / raw points in the anchor scoring (the reference league's: the scoring the blend was
# fitted in) -- and multiplies every component of the model's line by it before anything is priced. ``project`` then
# prices and ranges the scaled line exactly as it does a frozen one (``predict_position(..., lines=)``), so
# ``ops.projection_lines``, ``ops.projections``, ``ops.projection_ranges`` and every on-demand price of the line are
# one number by construction, in any scoring and either pricing mode.
COLD_DEFAULT = True              # unset LEAGUE_LAB_COLD_START = on: the harness kept it on the line (RB -0.16 4 of 5, WR -0.32 / TE -0.29 5 of 5)
LINE_VERSION = "cs1.1"           # cs1.0 (M5) on the stat line
LINE_MIN_RAW = 0.5               # a line priced under half a point has nothing to scale: left as the model made it
NEW_TEAM_N = 3                   # a veteran with fewer than this many games with his current team is "on a new team"
NEW_TEAM_POSITIONS: tuple[str, ...] = ()      # where the harness kept the new-team blend (empty: measured, dropped)
TEAM_GAMES_SQL = """select gsis_id, season, week, team from analytics.fct_player_game where season_type = 'REG' and played"""
LAST_LINE_BLEND: pd.DataFrame | None = None     # the last ``blend_lines`` run's scaled player-weeks (``line_scales``)


def line_scale(raw: np.ndarray, blended: np.ndarray) -> np.ndarray:
    """The factor every component of a line is multiplied by: ``blended / raw`` (anchor points); 1.0 where nothing
    moved or the raw line is under ``LINE_MIN_RAW`` points (or not finite)."""
    raw, blended = np.asarray(raw, dtype=float), np.asarray(blended, dtype=float)
    ok = np.isfinite(raw) & np.isfinite(blended) & (raw >= LINE_MIN_RAW) & (blended != raw)
    out = np.ones(len(raw))
    out[ok] = blended[ok] / raw[ok]
    return out


def team_games_before(rows: pd.DataFrame, games: pd.DataFrame) -> np.ndarray:
    """Per row (gsis_id, season, week, team): his played regular-season games with ``team`` in the current stint --
    the games since his last game for another team, strictly before the week. A row whose last game was for another
    team (a trade, a signing): 0. No history: 0."""
    if rows.empty:
        return np.zeros(0)
    g = games.dropna(subset=["team"]).assign(key=games["season"].astype(int) * 100 + games["week"].astype(int))
    g = g.sort_values(["gsis_id", "key"])
    stint = (g["team"] != g.groupby("gsis_id")["team"].shift()).astype(int).groupby(g["gsis_id"]).cumsum()
    g = g.assign(stint=stint.to_numpy())
    g = g.assign(n=g.groupby(["gsis_id", "stint"]).cumcount() + 1)[["gsis_id", "key", "team", "n"]].rename(columns={"team": "last_team"})
    r = rows[["gsis_id"]].assign(key=rows["season"].astype(int).to_numpy() * 100 + rows["week"].astype(int).to_numpy(),
                                 team=rows["team"].to_numpy() if "team" in rows else None, _i=np.arange(len(rows)))
    m = pd.merge_asof(r.sort_values("key"), g.sort_values("key"), on="key", by="gsis_id", allow_exact_matches=False,
                      direction="backward").sort_values("_i")
    same = (m["last_team"] == m["team"]).to_numpy()
    return np.where(same, m["n"].fillna(0).to_numpy(dtype=float), 0.0)


def is_new_team(team_games: pd.Series | np.ndarray, career_games: pd.Series | np.ndarray, cold: pd.Series | np.ndarray,
                n: int = NEW_TEAM_N) -> np.ndarray:
    """A veteran on a new team: not a cold start (``cold``: M5's rule), at least ``n`` career games, fewer than ``n``
    with his current team."""
    tg = pd.to_numeric(pd.Series(np.asarray(team_games, dtype=object)), errors="coerce").fillna(0).to_numpy(dtype=float)
    cg = pd.to_numeric(pd.Series(np.asarray(career_games, dtype=object)), errors="coerce").fillna(0).to_numpy(dtype=float)
    c = pd.Series(np.asarray(cold, dtype=object)).fillna(False).astype(bool).to_numpy()
    return ~c & (tg < n) & (cg >= n)


def blend_frame(rows: pd.DataFrame, kind: str) -> pd.DataFrame:
    """``rows`` in the columns ``ColdPrior`` / ``fit_cold_prior`` read: 'cold' = as they are (career games, M5);
    'new_team' = the games with the current team as ``career_games_before`` and the new-team flag as ``cold``."""
    if kind == "cold":
        return rows
    if kind == "new_team":
        return rows.assign(career_games_before=rows["team_games_before"], cold=rows["new_team"].astype(bool))
    raise ValueError(kind)


def _history(conn: psycopg.Connection) -> tuple[pd.DataFrame, pd.DataFrame]:
    with conn.cursor() as cur:
        cur.execute(TEAM_GAMES_SQL)
        games = pd.DataFrame(cur.fetchall(), columns=["gsis_id", "season", "week", "team"])
        cur.execute(DRAFT_SQL)
        draft = pd.DataFrame(cur.fetchall(), columns=["gsis_id", "draft_pick", "rookie_season"])
    return games, draft


def history_columns(rows: pd.DataFrame, games: pd.DataFrame, draft: pd.DataFrame) -> pd.DataFrame:
    """``cold_columns`` plus ``team_games_before`` and ``new_team`` (rows need ``team``)."""
    out = cold_columns(rows, games[["gsis_id", "season", "week"]], draft)
    out["team_games_before"] = team_games_before(out, games)
    out["new_team"] = is_new_team(out["team_games_before"], out["career_games_before"], out["cold"])
    return out


def anchor_league(oof: pd.DataFrame, leagues: dict[str, tuple[str, dict[str, float]]]) -> str | None:
    """The scoring the scale is set in: the reference league (the first id of LEAGUE_LAB_SLEEPER_LEAGUE_ID) when the
    out-of-sample rows hold it, else the first house league they hold."""
    from .config import get_settings

    held = [lid for lid in dict.fromkeys(oof["league_id"].astype(str)) if lid in leagues]
    ref = get_settings().reference_league_id
    return ref if ref in held else (held[0] if held else None)


def line_scales(conn: psycopg.Connection, season: int, lines: pd.DataFrame,
                leagues: dict[str, tuple[str, dict[str, float]]]) -> pd.DataFrame:
    """Per player-week of ``lines`` (gsis_id, season, week, position, team, ``proj_*``): the blend's scale ``k`` with
    ``kind`` ('cold' | 'new_team'), the games it keyed on and the anchor's raw / blended points; only the rows that
    move (k != 1). Fitted on ``ops.calibration_oof`` (the ``WINDOW`` seasons before ``season``) in the anchor league."""
    cols = ["gsis_id", "season", "week", "position", "kind", "games", "raw", "blended", "k"]
    positions = tuple(dict.fromkeys((*COLD_POSITIONS, *NEW_TEAM_POSITIONS, *_nt_positions())))   # ---- IL-3: + v3.3
    oof = load_oof(conn, season)
    if oof is None or oof.empty or not positions:
        log.warning("%s on but %s (run calibration.run_build_oof): stat lines unchanged", COLD_START_FLAG,
                    "no position is kept" if not positions else f"{OOF_TABLE} is empty")
        return pd.DataFrame(columns=cols)
    oof = oof[(oof["season"] >= season - WINDOW) & oof["position"].isin(positions)]
    anchor = anchor_league(oof, leagues)
    if anchor is None:
        log.warning("%s on but %s holds none of the house leagues: stat lines unchanged", COLD_START_FLAG, OOF_TABLE)
        return pd.DataFrame(columns=cols)
    games, draft = _history(conn)
    fit = oof[oof["league_id"].astype(str) == anchor]
    fit = fit.merge(games, on=["gsis_id", "season", "week"], how="left")       # the team he played for that week
    fit = history_columns(fit, games, draft)
    rows = history_columns(lines[lines["position"].isin(positions)].reset_index(drop=True), games, draft)
    rows["raw"] = P.price(rows, leagues[anchor][1], "proj_").to_numpy(dtype=float)
    rows["blended"], rows["kind"], rows["games"] = rows["raw"], None, np.nan
    for kind, kept in (("cold", COLD_POSITIONS), ("new_team", NEW_TEAM_POSITIONS)):
        for pos in kept:
            cp = fit_cold_prior(blend_frame(fit[fit["position"] == pos], kind), pos, anchor)
            sel = ((rows["position"] == pos) & rows["kind"].isna()).to_numpy()
            if not cp.prior or not sel.any():
                continue
            r = blend_frame(rows[sel], kind)
            new = cp.blend(r["raw"].to_numpy(dtype=float), r["career_games_before"].to_numpy(dtype=float),
                           r["bucket"].to_numpy(), r["cold"].to_numpy(dtype=bool))
            hit = r["cold"].to_numpy(dtype=bool) & (new != r["raw"].to_numpy(dtype=float))
            idx = rows.index[sel][hit]
            rows.loc[idx, "blended"], rows.loc[idx, "kind"] = new[hit], kind
            rows.loc[idx, "games"] = r["career_games_before"].to_numpy(dtype=float)[hit]
            log.info("%s %s %s (%s): weights %s, prior %s, %s player-weeks", LINE_VERSION, kind, pos, anchor[-6:],
                     cp.weights, {k: round(v, 2) for k, v in cp.prior.items()}, int(hit.sum()))
    _new_team_scale_rows(oof, games, draft, leagues, rows)                       # ---- IL-3: v3.3, the WR new-team scale
    rows["k"] = line_scale(rows["raw"].to_numpy(), rows["blended"].to_numpy())
    return rows[rows["k"] != 1.0][cols].reset_index(drop=True)


def blend_lines(conn: psycopg.Connection, season: int, every: pd.DataFrame, models: dict, target: pd.DataFrame,
                fit: dict[str, tuple[str, dict[str, float]]], leagues: dict[str, tuple[str, dict[str, float]]]
                ) -> pd.DataFrame:
    """``projections.project``'s hook, before ``nfl_lines``: ``every`` (one row per fitted scoring x player-week) with
    the cold starts' stat lines scaled (``line_scales``) and those rows priced and ranged again from the scaled line by
    the same models (``predict_position(..., lines=)``, the path a frozen line takes). Switch off (or nothing to
    scale): ``every`` itself, untouched."""
    if not cold_start_enabled() or every.empty:
        return every
    first = every["league_id"].iloc[0]
    line = every[every["league_id"] == first]
    line = line.merge(target[["gsis_id", "week", "team"]].drop_duplicates(["gsis_id", "week"]), on=["gsis_id", "week"],
                      how="left")
    plan = line_scales(conn, season, line, leagues)
    if plan.empty:
        return every
    comps = [f"proj_{c}" for c in P.ALL_COMPONENTS]
    keys = ["gsis_id", "week"]
    new = []
    for pos, p in plan.groupby("position"):
        tgt = target[target["position"] == pos].drop_duplicates(keys)
        rows = p[keys].merge(tgt, on=keys, how="inner", validate="one_to_one")
        ln = rows[keys].merge(line[[*keys, *comps]], on=keys, how="left").merge(p[[*keys, "k"]], on=keys, how="left")
        ln[comps] = ln[comps].to_numpy(dtype=float) * ln[["k"]].to_numpy(dtype=float)
        new.append(P.predict_position(models[pos], rows, fit, lines=ln))
    moved = pd.concat(new, ignore_index=True)
    for c in ("model_version", "fitted_at", "train_seasons"):
        if c in every:
            moved[c] = every[c].iloc[0]
    hit = every.set_index(keys).index.isin(plan.set_index(keys).index)
    out = pd.concat([every[~hit], moved[every.columns]], ignore_index=True)
    out.attrs = every.attrs
    global LAST_LINE_BLEND
    LAST_LINE_BLEND = plan      # the night's moves (a module global: a frame in ``attrs`` breaks pandas' concat)
    top = plan.assign(d=plan["blended"] - plan["raw"]).sort_values("d", key=np.abs, ascending=False).head(5)
    log.info("%s on the line: %s player-weeks scaled (%s); the five biggest in the anchor scoring: %s", LINE_VERSION,
             len(plan), plan["kind"].value_counts().to_dict(),
             "; ".join(f"{r.gsis_id} wk{r.week} {r.raw:.2f}->{r.blended:.2f}" for r in top.itertuples()))
    return out


def rescale_to_stored(comp_b: pd.DataFrame, comp_s: pd.DataFrame, keys: list[tuple[str, int]], pred: pd.DataFrame
                      ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``signals.scenarios``' base (``comp_b``, the refit models' line) and larger-role lines (``comp_s``), row-aligned
    with ``keys`` (gsis_id, week): where the stored line (``pred``'s ``proj_*``) differs from the model's -- a cold start
    scaled by ``blend_lines`` -- the base becomes the stored line and the larger role is scaled by the same ``k``. Every
    other row (and a ``pred`` without the line) is returned as it was."""
    cols = [f"proj_{c}" for c in P.ALL_COMPONENTS]
    if not set(cols) <= set(pred.columns) or comp_b.empty:
        return comp_b, comp_s
    line = pred.drop_duplicates(["gsis_id", "week"]).assign(week=lambda d: d["week"].astype(int)).set_index(["gsis_id", "week"])[cols]
    b, s = comp_b.copy(), comp_s.copy()
    at = b.columns.get_indexer(cols)
    for j, key in enumerate(keys):
        if key not in line.index:
            continue
        st, mo = line.loc[key].to_numpy(dtype=float), b[cols].iloc[j].to_numpy(dtype=float)
        if np.allclose(st, mo, rtol=0.0, atol=1e-9):
            continue
        c = int(np.argmax(np.abs(mo)))
        if mo[c] == 0:
            continue
        k = st[c] / mo[c]
        # ---- IP-1 (Wave I-P): component by component (a component the model put at 0 takes the line's k). A cold
        # start's line is the model's x k in every component, so this is M6's rule exactly; pt1.0 changes a QB's passing
        # TDs alone, and the larger role's passing TDs follow by the same ratio (the gain stays the role's, not pt1.0's)
        ratio = np.where(mo != 0, st / np.where(mo != 0, mo, 1.0), k)
        # ---- end IP-1
        b.iloc[j, at] = st
        s.iloc[j, s.columns.get_indexer(cols)] = s[cols].iloc[j].to_numpy(dtype=float) * ratio
    return b, s


# ------------------------------------------------------------------------------ the out-of-sample rows where the nightly runs
OOF_MODEL_DDL = f"alter table {OOF_TABLE} add column if not exists model_version text"


def oof_current(conn: psycopg.Connection, seasons: list[int]) -> bool:
    """``ops.calibration_oof`` already holds exactly ``seasons``, built by this ``MODEL_VERSION``."""
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s)", (OOF_TABLE,))
        if cur.fetchone()[0] is None:
            return False
        cur.execute(OOF_MODEL_DDL)
        cur.execute(f"select distinct season, model_version from {OOF_TABLE}")
        held = cur.fetchall()
    conn.commit()
    return bool(held) and {int(s) for s, _ in held} == set(seasons) and {m for _, m in held} == {P.MODEL_VERSION}


def oof_target_seasons(conn: psycopg.Connection) -> list[int]:
    """The newest ``WINDOW`` completed seasons (what the next season's fits read)."""
    alls = P.available_seasons(conn)
    done = [s for s in alls if OOF_FIRST_SEASON <= s < max(alls)]
    return done[-WINDOW:]


def ensure_oof(force: bool = False) -> int:
    """The nightly's step (``scripts/nightly.sh``, before ``project``): ``run_build_oof`` only when the table does not
    already hold the newest ``WINDOW`` completed seasons of this model version (once a season, or after a model bump;
    otherwise a no-op that reads two rows). Returns the rows written, 0 when current."""
    from .config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        seasons = oof_target_seasons(conn)
        if not force and oof_current(conn, seasons):
            log.info("%s holds %s (%s): current, nothing to do", OOF_TABLE, seasons, P.MODEL_VERSION)
            return 0
    return run_build_oof(seasons)
# ---- /M6


# ---- IL-3 (Wave I-L): v3.3 — the mean-unbiased new-team scale at WR (nt1.0; docs/METRICS.md § "v3.3"). A veteran WR on a
# new team (``is_new_team``: not a cold start, >= 3 career games, < 3 with his current team in the current stint) gets one
# scale on every component of his line: k = sum(actual) / sum(projected) over the new-team WR rows of the ``WINDOW``
# seasons before (``ops.calibration_oof``, the house scorings pooled, rows priced at least ``LINE_MIN_RAW``), clipped to
# ``NEW_TEAM_SCALE_BOUNDS``; fewer than ``NEW_TEAM_SCALE_MIN_ROWS`` fitting rows: no scale. Decided by a rule written
# before the run (walk-forward 2021-2025, both scorings: the flagged rows' MAE -0.18, lower in 4 of 5 seasons, mean bias
# -0.94 -> -0.41, the board not hurt). It rides the cold-start switch (``blend_lines``: off = v3.0's lines) and has its
# own, ``LEAGUE_LAB_NEW_TEAM_SCALE`` (unset = on; ``0`` turns only this part off). A cold start is never also scaled.
NEW_TEAM_SCALE_FLAG = "LEAGUE_LAB_NEW_TEAM_SCALE"
NEW_TEAM_SCALE_POSITIONS: tuple[str, ...] = ("WR",)
NEW_TEAM_SCALE_VERSION = "nt1.0"
NEW_TEAM_SCALE_BOUNDS = (0.70, 1.10)
NEW_TEAM_SCALE_MIN_ROWS = 30
LAST_NEW_TEAM_SCALE: dict[str, tuple[float, int]] = {}     # the last ``line_scales`` run's {position: (k, fitting rows)}


def new_team_scale_enabled() -> bool:
    v = os.environ.get(NEW_TEAM_SCALE_FLAG)
    if v is None or not v.strip():
        return True
    return _flag(NEW_TEAM_SCALE_FLAG)


def _nt_positions() -> tuple[str, ...]:
    return NEW_TEAM_SCALE_POSITIONS if new_team_scale_enabled() else ()


def new_team_scale(fit: pd.DataFrame, position: str) -> tuple[float, int]:
    """(k, fitting rows): sum(actual) / sum(proj_points) over ``fit``'s rows at ``position`` flagged ``new_team``, played
    (``actual`` known) and priced at least ``LINE_MIN_RAW``, every scoring in ``fit`` pooled; clipped to
    ``NEW_TEAM_SCALE_BOUNDS``. (1.0, n) under ``NEW_TEAM_SCALE_MIN_ROWS`` rows or a non-positive projected sum."""
    if fit.empty:
        return 1.0, 0
    f = fit[(fit["position"] == position) & fit["new_team"].fillna(False).astype(bool) & fit["actual"].notna()
            & (pd.to_numeric(fit["proj_points"], errors="coerce") >= LINE_MIN_RAW)]
    n, den = len(f), float(pd.to_numeric(f["proj_points"], errors="coerce").sum())
    if n < NEW_TEAM_SCALE_MIN_ROWS or den <= 0:
        return 1.0, n
    lo, hi = NEW_TEAM_SCALE_BOUNDS
    return float(np.clip(float(pd.to_numeric(f["actual"], errors="coerce").sum()) / den, lo, hi)), n


def new_team_ahead(rows: pd.DataFrame, games: pd.DataFrame) -> pd.Series:
    """The new-team flag as the harness measured it (games with the team before *that* week), seen from today: a week
    after the newest played week of its season adds his projected games before it (his own earlier rows beyond that
    week: one a week he has a game) to the games he has with the team now. A WR with 2 games for his new team is flagged
    for his next game only, not for the rest of the season. Rows need ``team_games_before``, ``career_games_before``,
    ``cold``, ``season``, ``week``, ``gsis_id``."""
    if rows.empty:
        return pd.Series(dtype=bool)
    g = games.dropna(subset=["week"])
    last = g.groupby(g["season"].astype(int))["week"].max().astype(int).to_dict()
    season = rows["season"].astype(int)
    future = rows["week"].astype(int) > season.map(last).fillna(0).astype(int)
    ahead = pd.Series(0.0, index=rows.index)
    if future.any():
        f = rows[future]
        ahead.loc[f.index] = f.groupby(["gsis_id", f["season"].astype(int)])["week"].rank(method="first").to_numpy() - 1.0
    tg = pd.to_numeric(rows["team_games_before"], errors="coerce").fillna(0) + ahead
    cg = pd.to_numeric(rows["career_games_before"], errors="coerce").fillna(0) + ahead
    return pd.Series(is_new_team(tg, cg, rows["cold"]), index=rows.index)


def _new_team_scale_rows(oof: pd.DataFrame, games: pd.DataFrame, draft: pd.DataFrame,
                         leagues: dict[str, tuple[str, dict[str, float]]], rows: pd.DataFrame) -> None:
    """``line_scales``' v3.3 step, in place on ``rows`` (the lines with ``raw`` / ``blended`` / ``kind`` / ``games`` and
    the history columns): each kept position's new-team rows not already blended get ``blended = raw x k``."""
    LAST_NEW_TEAM_SCALE.clear()
    flag = new_team_ahead(rows, games)
    for pos in _nt_positions():
        sel = ((rows["position"] == pos) & rows["kind"].isna() & flag & (rows["raw"] >= LINE_MIN_RAW)).to_numpy()
        if not sel.any():
            continue
        pool = oof[(oof["position"] == pos) & oof["league_id"].astype(str).isin(list(leagues))]
        pool = history_columns(pool.merge(games, on=["gsis_id", "season", "week"], how="left"), games, draft)
        k, n = new_team_scale(pool, pos)
        LAST_NEW_TEAM_SCALE[pos] = (k, n)
        if k == 1.0:
            log.info("%s new team %s: %s fitting rows, no scale", NEW_TEAM_SCALE_VERSION, pos, n)
            continue
        idx = rows.index[sel]
        rows.loc[idx, "blended"] = rows.loc[idx, "raw"].to_numpy(dtype=float) * k
        rows.loc[idx, "kind"], rows.loc[idx, "games"] = "new_team", rows.loc[idx, "team_games_before"].to_numpy(dtype=float)
        log.info("%s new team %s: k = %.4f on %s fitting rows (%s scorings pooled), %s player-weeks", NEW_TEAM_SCALE_VERSION,
                 pos, k, n, pool["league_id"].nunique(), int(sel.sum()))
# ---- end IL-3


# ---- IP-1 (Wave I-P): v3.4 -- a quarterback's passing TDs regressed toward his team's implied total (pt1.0; docs/METRICS.md
# § "The quarterback weak spot (IP-1)"). The diagnosis: passing TDs carry most of a quarterback's miss (about 2 of the 5.4
# points), and the component model's count, learned from his own history, loses to the team's Vegas total. The candidate,
# written down before it was run: per season S, least squares WITHOUT intercept over the played QB rows of the WINDOW
# seasons before S (the walk-forward rows: the production component models fitted on the seasons before each), actual
# passing TDs = a x the model's passing TDs + b x (implied team total x the model's attempts / PASS_TD_ATTEMPTS); applied
# to every QB line that has an implied total (the weeks whose line is posted; later weeks keep the model's, as the harness
# never saw a row without one). The harness (2021-2025, both house scorings, experiments.decide on the QB board): MAE
# -0.076, lower in 5 of 5 seasons; Spearman +0.0145, higher in 5 of 5 -> keep. It changes the STAT LINE before anything is
# priced (the frozen-line path ``predict_position(..., lines=)``, like ``blend_lines``), so ops.projection_lines, the house
# rows, the ranges and every request carry one number. Switch: ``LEAGUE_LAB_QB_PASS_TD`` (unset = on; ``0`` = v3.3's
# lines). The fit runs inside ``project`` from the training frame (3 QB component fits): no table, no nightly step.
PASS_TD_FLAG = "LEAGUE_LAB_QB_PASS_TD"
PASS_TD_DEFAULT = True                 # the harness kept it (docs/METRICS.md § "The quarterback weak spot (IP-1)")
PASS_TD_VERSION = "pt1.0"
PASS_TD_POSITIONS: tuple[str, ...] = ("QB",)
PASS_TD_ATTEMPTS = 33.0                # about a starter's attempts per game: the team term is the implied total x his share
PASS_TD_MIN_ROWS = 300                 # fewer fitting rows: the identity (a = 1, b = 0)
LAST_PASS_TD: dict[str, float | int] = {}   # the last ``pass_td_lines`` run: a, b, fitting rows, lines moved


def pass_td_enabled() -> bool:
    """``LEAGUE_LAB_QB_PASS_TD``: unset or empty = ``PASS_TD_DEFAULT`` (on: the harness's verdict); ``1`` / ``0``."""
    v = os.environ.get(PASS_TD_FLAG)
    if v is None or not v.strip():
        return PASS_TD_DEFAULT
    return _flag(PASS_TD_FLAG)


def pass_td_team_term(implied: pd.Series | np.ndarray, attempts: pd.Series | np.ndarray) -> np.ndarray:
    """The implied team total x the projected attempts / ``PASS_TD_ATTEMPTS`` (NaN where the total is not known)."""
    return np.asarray(implied, dtype=float) * np.asarray(attempts, dtype=float) / PASS_TD_ATTEMPTS


def fit_pass_td(rows: pd.DataFrame) -> tuple[float, float, int]:
    """(a, b, fitting rows): least squares without intercept of ``out_passing_tds`` on ``proj_passing_tds`` and the team
    term, over played rows with all three known. Under ``PASS_TD_MIN_ROWS`` rows (or a singular fit): (1.0, 0.0, n), the
    identity."""
    d = rows[rows["played"].fillna(False).astype(bool)] if "played" in rows else rows
    team = pass_td_team_term(d["implied_team_total"], d["proj_attempts"])
    ok = np.isfinite(team) & d["proj_passing_tds"].notna().to_numpy() & d["out_passing_tds"].notna().to_numpy()
    n = int(ok.sum())
    if n < PASS_TD_MIN_ROWS:
        return 1.0, 0.0, n
    x = np.column_stack([d["proj_passing_tds"].to_numpy(dtype=float)[ok], team[ok]])
    coef, _, rank, _ = np.linalg.lstsq(x, d["out_passing_tds"].to_numpy(dtype=float)[ok], rcond=None)
    if rank < 2 or not np.isfinite(coef).all():
        return 1.0, 0.0, n
    return float(coef[0]), float(coef[1]), n


def apply_pass_td(lines: pd.DataFrame, a: float, b: float) -> np.ndarray:
    """The new passing TDs of ``lines`` (``proj_passing_tds``, ``proj_attempts``, ``implied_team_total``): a x the model's
    + b x the team term, at least 0; the model's own where the implied total is not known."""
    model = lines["proj_passing_tds"].to_numpy(dtype=float)
    team = pass_td_team_term(lines["implied_team_total"], lines["proj_attempts"])
    return np.where(np.isfinite(team), np.clip(a * model + b * team, 0.0, None), model)


def pass_td_fit_rows(train: pd.DataFrame, season: int, window: int = WINDOW) -> pd.DataFrame:
    """The fitting rows for ``season``: for each of the ``window`` seasons s before it, the production QB component
    models fitted on the frame's seasons before s (``fit_position``'s training filter and inputs) applied to s --
    passing TDs and attempts -- with the implied total and the outcome (the harness's rows, ``ip1_qb_candidates``)."""
    feats = list(P.FEATURES_BY_POSITION["QB"])
    out = []
    for s in range(season - window, season):
        te = train[train["season"] == s]
        rows = te[(te["position"] == "QB")].reset_index(drop=True)
        models = walk_forward_models(train, s, "QB")     # ---- IQ-3: the same fit, shared with hb1.0 (memoised)
        if models is None or rows.empty:
            continue
        x = P._matrix(rows, feats)
        out.append(pd.DataFrame({"season": s, "played": rows["played"].to_numpy(),
                                 "implied_team_total": rows["implied_team_total"].to_numpy(dtype=float),
                                 "proj_passing_tds": np.clip(models["passing_tds"].predict(x), 0, None),
                                 "proj_attempts": np.clip(models["attempts"].predict(x), 0, None),
                                 "out_passing_tds": rows["out_passing_tds"].to_numpy(dtype=float)}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(
        columns=["season", "played", "implied_team_total", "proj_passing_tds", "proj_attempts", "out_passing_tds"])


def pass_td_lines(season: int, every: pd.DataFrame, models: dict, target: pd.DataFrame, train: pd.DataFrame,
                  fit: dict[str, tuple[str, dict[str, float]]]) -> pd.DataFrame:
    """``projections.project``'s hook (before ``blend_lines``): ``every`` with each QB line's passing TDs regressed toward
    the team's implied total (``fit_pass_td`` on ``pass_td_fit_rows``), those rows priced and ranged again from the new
    line by the same models (``predict_position(..., lines=)``). Switch off, no kept position, a fit under the minimum or
    nothing that moves: ``every`` itself."""
    LAST_PASS_TD.clear()
    positions = [p for p in PASS_TD_POSITIONS if p in models]
    if not pass_td_enabled() or every.empty or not positions:
        return every
    a, b, n = fit_pass_td(pass_td_fit_rows(train, season))
    LAST_PASS_TD.update({"a": a, "b": b, "rows": n, "moved": 0})
    if (a, b) == (1.0, 0.0):
        log.info("%s: %s fitting rows, no fit: QB lines unchanged", PASS_TD_VERSION, n)
        return every
    comps = [f"proj_{c}" for c in P.ALL_COMPONENTS]
    keys = ["gsis_id", "week"]
    first = every["league_id"].iloc[0]
    new = []
    for pos in positions:
        line = every[(every["league_id"] == first) & (every["position"] == pos)]
        tgt = target[target["position"] == pos].drop_duplicates(keys)
        line = line.merge(tgt[[*keys, "implied_team_total"]], on=keys, how="left")
        if "implied_imputed" in tgt:     # ---- IQ-1: pt1.0 was measured on real lines only: an imputed one is no line
            imputed = line[keys].merge(tgt[[*keys, "implied_imputed"]], on=keys, how="left")["implied_imputed"]
            line.loc[imputed.fillna(False).astype(bool).to_numpy(), "implied_team_total"] = np.nan
        tds = apply_pass_td(line, a, b)
        moved = np.abs(tds - line["proj_passing_tds"].to_numpy(dtype=float)) > 1e-12
        if not moved.any():
            continue
        ln = line.loc[moved, [*keys, *comps]].reset_index(drop=True)
        ln["proj_passing_tds"] = tds[moved]
        rows = ln[keys].merge(tgt, on=keys, how="inner", validate="one_to_one")
        ln = rows[keys].merge(ln, on=keys, how="left")
        new.append(P.predict_position(models[pos], rows, fit, lines=ln))
    if not new:
        return every
    moved_rows = pd.concat(new, ignore_index=True)
    for c in ("model_version", "fitted_at", "train_seasons"):
        if c in every:
            moved_rows[c] = every[c].iloc[0]
    hit = every.set_index(keys).index.isin(moved_rows.set_index(keys).index) & every["position"].isin(positions).to_numpy()
    out = pd.concat([every[~hit], moved_rows[every.columns]], ignore_index=True)
    out.attrs = every.attrs
    LAST_PASS_TD["moved"] = int(moved_rows["league_id"].eq(first).sum())
    log.info("%s QB passing TDs: a = %.3f x the model + b = %.4f x implied total x attempts / %.0f, on %s fitting rows "
             "(%s-%s); %s QB lines moved (weeks with an implied total)", PASS_TD_VERSION, a, b, PASS_TD_ATTEMPTS, n,
             season - WINDOW, season - 1, LAST_PASS_TD["moved"])
    return out
# ---- end IP-1


# ---- IQ-1 (hotfix, 2026-10-07): v3.5 -- the weeks after the market week (docs/METRICS.md § "v3.5: rest-of-season
# quarterbacks (IQ-1)"). A week more than one ahead had no betting line (NaN: the component models never saw one in
# training, so every split sent it down the same branch and a QB's team lost its level -- the main cause of the
# re-ordered rest-of-season list, 2026 as of week 5: rank correlation with the market week 0.44 -> 0.78 with the line
# alone) and read its personnel from the team's newest played game instead of the schedule's listing for the market
# week (Daniels projected as a backup all season). Kept by the horizon rule (written before the run): candidate "ad",
# QB pooled horizons 2-8 MAE -0.183 lower in 5 of 5 seasons 2021-2025, Spearman +0.038, RB / WR / TE not worse.
#   a. a later week's implied total and game total = the team's own mean over its games so far this season, shrunk
#      toward the league's mean by FUTURE_LINE_SHRINK games; the spread (the home team's view) follows from them;
#   d. a later week's personnel inputs (``projections.QB_INPUTS``) = the player's own market-week row's.
# Played weeks are never touched; the market week only gets (a) while the books have posted no line for it (as on the
# night after a Monday game). ``implied_imputed`` marks the rows (a), so pt1.0 -- measured on
# real lines only -- skips them. Switch: LEAGUE_LAB_FUTURE_INPUTS (unset = on; 0 = v3.4's later weeks).
FUTURE_INPUTS_FLAG = "LEAGUE_LAB_FUTURE_INPUTS"
FUTURE_INPUTS_DEFAULT = True
FUTURE_INPUTS_VERSION = "fi1.0"
FUTURE_LINE_SHRINK = 3.0
LAST_FUTURE_INPUTS: dict[str, object] = {}


def future_inputs_enabled() -> bool:
    v = os.environ.get(FUTURE_INPUTS_FLAG)
    if v is None or not v.strip():
        return FUTURE_INPUTS_DEFAULT
    return _flag(FUTURE_INPUTS_FLAG)


def market_week(target: pd.DataFrame) -> int | None:
    """The first week after the newest week with a played row (the first week of the season when none is played)."""
    if target.empty:
        return None
    played = target.loc[target["played"].fillna(False).astype(bool), "week"]
    return int(played.max()) + 1 if len(played) else int(target["week"].min())


def team_lines(target: pd.DataFrame, through_week: int) -> pd.DataFrame:
    """Per team: mean implied total and game total over its games of weeks <= ``through_week`` with a line, and how many."""
    s = target[(target["week"] <= through_week) & target["implied_team_total"].notna()].drop_duplicates(["team", "week"])
    g = s.groupby("team")
    return pd.DataFrame({"imp": g["implied_team_total"].mean(), "tot": g["total_line"].mean(), "n": g.size()})


def future_inputs(target: pd.DataFrame, k: float = FUTURE_LINE_SHRINK) -> pd.DataFrame:
    """``target`` (one season's feature rows) with the weeks after the market week given (a) a line from the team's own
    season so far where they have none and (d) the market week's personnel inputs; ``implied_imputed`` marks (a)'s
    rows. Switch off, no market week or nothing after it: ``target`` with ``implied_imputed`` False."""
    out = target.copy()
    out["implied_imputed"] = False
    LAST_FUTURE_INPUTS.clear()
    mw = market_week(out)
    if not future_inputs_enabled() or mw is None:
        return out
    fut = (out["week"] > mw).to_numpy()
    if not fut.any():
        return out
    # a. the line
    lines = team_lines(out, mw - 1)
    # every unplayed week from the market week on without a line (the market week has one once the books post it)
    no_line = (out["week"] >= mw).to_numpy() & out["implied_team_total"].isna().to_numpy()
    if len(lines) and no_line.any():
        lg_imp, lg_tot = float(lines["imp"].mean()), float(lines["tot"].mean())
        t = lines.reindex(out["team"])
        n = t["n"].fillna(0).to_numpy(dtype=float)
        imp = (n * t["imp"].fillna(lg_imp).to_numpy(dtype=float) + k * lg_imp) / (n + k)
        tot = (n * t["tot"].fillna(lg_tot).to_numpy(dtype=float) + k * lg_tot) / (n + k)
        home = out["f_home"].fillna(0).to_numpy(dtype=float) > 0
        out.loc[no_line, "implied_team_total"] = imp[no_line]
        out.loc[no_line, "total_line"] = tot[no_line]
        out.loc[no_line, "spread_line"] = np.where(home, 2 * imp - tot, tot - 2 * imp)[no_line]
        out.loc[no_line, "implied_imputed"] = True
    # d. the personnel of the market week
    cols = [c for c in P.QB_INPUTS if c in out]
    mkt = out[out["week"] == mw].drop_duplicates("gsis_id").set_index("gsis_id")
    moved_pn = 0
    if cols and len(mkt):
        has = fut & out["gsis_id"].isin(mkt.index).to_numpy()
        src = mkt[cols].reindex(out.loc[has, "gsis_id"]).to_numpy(dtype=float)
        before = out.loc[has, cols].to_numpy(dtype=float)
        moved_pn = int((~((before == src) | (np.isnan(before) & np.isnan(src)))).any(axis=1).sum())
        out.loc[has, cols] = src
    LAST_FUTURE_INPUTS.update({"market_week": mw, "lines_imputed": int(no_line.sum()), "personnel_moved": moved_pn,
                               "teams_with_lines": len(lines)})
    log.info("%s: market week %s; later weeks' lines from the teams' own season (%s rows, shrink %s games), personnel "
             "of the market week (%s rows moved)", FUTURE_INPUTS_VERSION, mw, int(no_line.sum()), k, moved_pn)
    return out
# ---- end IQ-1


# ---- IQ-3 (Wave I-Q, 2026-10-07): v3.6 -- hb1.0, the weeks after the market week blend the QB model's stat line with
# the player's own per-game line (docs/METRICS.md § "v3.6: the quarterback model reads the quarterback (IQ-3)"). The
# baselines first: two to eight weeks ahead a naive line -- his points per game this season and last, shrunk by games
# toward his listed role's mean -- beat v3.5 (MAE 7.44 against 7.56, Spearman 0.491 against 0.473, 2021-2025); one week
# ahead the model beats it in every season. Kept by the IQ-3 rule (written before any candidate number): the market
# week unchanged (0 cells), pooled 2-8 MAE -0.154 lower in 5 of 5 seasons, Spearman +0.022 (0.473 -> 0.495).
#   n_c = (g x this season's c per game + lambda x g_prev x last season's + k x the role's mean c) / (g + lambda g_prev + k)
#   (g, g_prev: his games this season / last; the role: the week's listed starter or not -- for a later week the market
#   week's listing, fi1.0's d), lambda and k by the MAE of the priced line on the scored QB rows of the 3 seasons before;
#   a week h weeks after the market week (h = 2 .. 8; further out takes 8): (1 - w_h) x the model's line + w_h x n,
#   w_h on a 0-1 grid by 0.05 from the 3 seasons before as the horizon study builds them (as of weeks 3, 5, 7, 9: the
#   walk-forward QB component models fitted on the seasons before each, the later weeks with fi1.0's inputs), the MAE
#   of the priced line summed over the house scorings. On the stat line before pricing (``predict_position(...,
# lines=)``, like pt1.0), QB only. The market week and played weeks are never touched. Switch: LEAGUE_LAB_QB_HORIZON_BLEND
# (unset = on; 0 = v3.5's later weeks).
HORIZON_BLEND_FLAG = "LEAGUE_LAB_QB_HORIZON_BLEND"
HORIZON_BLEND_DEFAULT = True
HORIZON_BLEND_VERSION = "hb1.0"
HORIZON_BLEND_POSITIONS: tuple[str, ...] = ("QB",)
HB_AS_OF = (3, 5, 7, 9)
HB_H_MAX = 8
HB_LAMBDAS = (0.25, 0.5, 0.75, 1.0)
HB_KS = (1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0)
HB_GRID = tuple(round(0.05 * i, 2) for i in range(21))
HB_MIN_ROWS = 200                 # fewer fitting rows at a horizon: weight 0 (the model's line)
HB_OPP = ["opp_allowed_std", "opp_allowed_l4", "opp_rank_std", "league_allowed_avg", "f_opp_allowed_diff"]
LAST_HORIZON_BLEND: dict[str, object] = {}
_WF_MODELS: dict[tuple, dict] = {}     # walk-forward QB component models, shared by pt1.0 and hb1.0 within a run


def horizon_blend_enabled() -> bool:
    v = os.environ.get(HORIZON_BLEND_FLAG)
    if v is None or not v.strip():
        return HORIZON_BLEND_DEFAULT
    return _flag(HORIZON_BLEND_FLAG)


def walk_forward_models(train: pd.DataFrame, s: int, position: str = "QB") -> dict | None:
    """The production component models of ``position`` fitted on ``train``'s seasons before ``s`` (``fit_position``'s
    training filter and inputs); None with under 100 rows. Memoised for the run (pt1.0 and hb1.0 fit the same ones)."""
    first = int(train["season"].min())
    tr = train[(train["season"] >= first) & (train["season"] < s)]
    d = tr[(tr["position"] == position) & tr["played"] & ~tr["no_history"]]
    d = d.dropna(subset=[f"out_{c}" for c in P.COMPONENTS[position]]).reset_index(drop=True)
    if len(d) < 100:
        return None
    key = (position, s, first, len(d), float(d[f"out_{P.COMPONENTS[position][0]}"].sum()))
    if key not in _WF_MODELS:
        _WF_MODELS.clear() if len(_WF_MODELS) > 12 else None
        _WF_MODELS[key] = P._fit_components(P._matrix(d, list(P.FEATURES_BY_POSITION[position])), d, position)
    return _WF_MODELS[key]


def _scored(d: pd.DataFrame) -> np.ndarray:
    return (d["played"].fillna(False).astype(bool) & d[[f"out_{c}" for c in P.ALL_COMPONENTS]].notna().all(axis=1)).to_numpy()


def _actual(d: pd.DataFrame, scoring: dict[str, float]) -> np.ndarray:
    ok = d[[f"out_{c}" for c in P.ALL_COMPONENTS]].notna().all(axis=1).to_numpy()
    a = np.full(len(d), np.nan)
    if ok.any():
        a[ok] = P.price(d[ok], scoring, "out_").to_numpy(dtype=float)
    return a


def _priced(d: pd.DataFrame, prefix: str, scoring: dict[str, float], suffix: str = "") -> np.ndarray:
    """Points of the stat line in ``<prefix><component><suffix>`` (projection pricing)."""
    line = pd.DataFrame({f"proj_{c}": pd.to_numeric(d[f"{prefix}{c}{suffix}"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
                         for c in P.ALL_COMPONENTS})
    line["position"] = d["position"].to_numpy()
    return P.price(line, scoring, "proj_").to_numpy(dtype=float)


@dataclass
class NaiveParams:
    lam: float
    k: float
    role_means: dict[str, tuple[float, float]]     # component -> (listed starter, the rest)


def fit_naive(rows: pd.DataFrame, scorings: dict[str, tuple[str, dict[str, float]]]) -> NaiveParams | None:
    """The naive line's parameters from ``rows`` (QB board rows of the fitting seasons): the role means of each component
    over the scored rows, lambda and k by the MAE of the priced line summed over ``scorings``."""
    d = rows[_scored(rows)].reset_index(drop=True)
    if len(d) < HB_MIN_ROWS:
        return None
    starter = d["pn_qb_starting"].fillna(0).to_numpy(dtype=float) > 0.5
    if starter.sum() == 0 or (~starter).sum() == 0:
        return None
    means = {c: (float(d.loc[starter, f"out_{c}"].mean()), float(d.loc[~starter, f"out_{c}"].mean())) for c in P.ALL_COMPONENTS}
    g = d["games_to_date"].fillna(0).to_numpy(dtype=float)
    gp = d["prev_games"].fillna(0).to_numpy(dtype=float)
    parts = []
    for _, sc in scorings.values():
        this = _priced(d, "", sc, "_pg_std")
        last = _priced(d, "prev_", sc, "_pg")
        y = _actual(d, sc)
        pr = np.where(starter, float(np.mean(y[starter])), float(np.mean(y[~starter])))
        parts.append((np.where(g > 0, this, 0.0), np.where(gp > 0, last, 0.0), pr, y))
    best = None
    for lam in HB_LAMBDAS:
        for k in HB_KS:
            e = sum(float(np.mean(np.abs((g * t + lam * gp * la + k * pr) / (g + lam * gp + k) - y))) for t, la, pr, y in parts)
            if best is None or e < best[0]:
                best = (e, lam, k)
    return NaiveParams(lam=best[1], k=best[2], role_means=means)


def naive_line(rows: pd.DataFrame, p: NaiveParams) -> pd.DataFrame:
    """``n_<c>`` for every row: his per-game line this season and last, shrunk toward his listed role's mean by games."""
    g = rows["games_to_date"].fillna(0).to_numpy(dtype=float)
    gp = rows["prev_games"].fillna(0).to_numpy(dtype=float)
    starter = rows["pn_qb_starting"].fillna(0).to_numpy(dtype=float) > 0.5
    out = {}
    for c in P.ALL_COMPONENTS:
        this = np.where(g > 0, rows[f"{c}_pg_std"].fillna(0).to_numpy(dtype=float), 0.0)
        last = np.where(gp > 0, rows[f"prev_{c}_pg"].fillna(0).to_numpy(dtype=float), 0.0)
        pr = np.where(starter, *p.role_means[c])
        out[f"n_{c}"] = (g * this + p.lam * gp * last + p.k * pr) / (g + p.lam * gp + p.k)
    return pd.DataFrame(out, index=rows.index)


def horizon_rows(season_rows: pd.DataFrame, w: int, h_max: int = HB_H_MAX, k: float = FUTURE_LINE_SHRINK) -> pd.DataFrame:
    """One position's rows of one past season as the nightly would have built its later weeks as of week ``w``: for
    T = w+2 .. w+h_max a copy of the player's market-week (w+1) row (his history as of w, the market week's personnel:
    fi1.0's d) with T's opponent (its points allowed as of w), home / away, the week number, no injury report, and the
    team's own line so far shrunk by ``k`` games (fi1.0's a); T's outcome. ``h`` = T - w."""
    s = season_rows
    mkt = s[s["week"] == w + 1].drop_duplicates("gsis_id").set_index("gsis_id")
    if mkt.empty:
        return s.iloc[0:0].assign(h=pd.Series(dtype=float))
    opp = s[s["week"] <= w + 1].sort_values("week").drop_duplicates(["position", "opponent"], keep="last").set_index(
        ["position", "opponent"])[HB_OPP]
    lines = team_lines(s, w)
    lg_imp, lg_tot = (float(lines["imp"].mean()), float(lines["tot"].mean())) if len(lines) else (np.nan, np.nan)
    out = []
    for t in range(w + 2, w + h_max + 1):
        fut = s[(s["week"] == t) & s["gsis_id"].isin(mkt.index)].drop_duplicates("gsis_id")
        if fut.empty:
            continue
        base = mkt.loc[fut["gsis_id"]].reset_index()
        base["week"] = float(t)
        base["opponent"], base["f_home"] = fut["opponent"].to_numpy(), fut["f_home"].to_numpy()
        o = opp.reindex(pd.MultiIndex.from_arrays([base["position"], base["opponent"]]))
        for c in HB_OPP:
            base[c] = np.where(o[c].notna(), o[c].to_numpy(dtype=float), fut[c].to_numpy(dtype=float))
        tl = lines.reindex(base["team"])
        n = tl["n"].fillna(0).to_numpy(dtype=float)
        imp = (n * tl["imp"].fillna(lg_imp).to_numpy(dtype=float) + k * lg_imp) / (n + k)
        tot = (n * tl["tot"].fillna(lg_tot).to_numpy(dtype=float) + k * lg_tot) / (n + k)
        home = base["f_home"].fillna(0).to_numpy(dtype=float) > 0
        base["implied_team_total"], base["total_line"] = imp, tot
        base["spread_line"] = np.where(home, 2 * imp - tot, tot - 2 * imp)
        base["questionable"] = 0.0
        base[[f"out_{c}" for c in P.ALL_COMPONENTS]] = fut[[f"out_{c}" for c in P.ALL_COMPONENTS]].to_numpy()
        base["played"] = fut["played"].to_numpy()
        out.append(base.assign(h=float(t - w)))
    return pd.concat(out, ignore_index=True) if out else s.iloc[0:0].assign(h=pd.Series(dtype=float))


def fit_horizon_weights(train: pd.DataFrame, season: int, scorings: dict[str, tuple[str, dict[str, float]]],
                        position: str = "QB", window: int = WINDOW) -> dict[int, float]:
    """w_h (h = 2 .. HB_H_MAX) for ``season`` from the ``window`` seasons before it (``horizon_rows`` as of HB_AS_OF, the
    walk-forward models' line against the naive line with that season's own parameters); {} when nothing can be fitted."""
    feats = list(P.FEATURES_BY_POSITION[position])
    first = int(train["season"].min())
    pos_rows = train[train["position"] == position]
    parts = []
    for s in range(season - window, season):
        models = walk_forward_models(train, s, position)
        params = fit_naive(pos_rows[(pos_rows["season"] >= max(first, s - window)) & (pos_rows["season"] < s)], scorings)
        if models is None or params is None:
            continue
        srows = pos_rows[pos_rows["season"] == s]
        for w in HB_AS_OF:
            r = horizon_rows(srows, w)
            r = r[_scored(r)].reset_index(drop=True) if len(r) else r
            if r.empty:
                continue
            x = r[feats].to_numpy(dtype=float)        # NaN stays NaN
            m = pd.DataFrame({f"m_{c}": (np.clip(models[c].predict(x), 0, None) if c in models else np.zeros(len(r)))
                              for c in P.ALL_COMPONENTS}, index=r.index)
            r = pd.concat([r, m, naive_line(r, params)], axis=1)
            parts.append(r)
    if not parts:
        return {}
    d = pd.concat(parts, ignore_index=True)
    priced = [(_priced(d, "m_", sc), _priced(d, "n_", sc), _actual(d, sc)) for _, sc in scorings.values()]
    h = d["h"].to_numpy(dtype=float)
    weights = {}
    for hh in range(2, HB_H_MAX + 1):
        sel = h == hh
        if sel.sum() < HB_MIN_ROWS:
            weights[hh] = 0.0
            continue
        best = None
        for w in HB_GRID:
            e = sum(float(np.mean(np.abs((1 - w) * m[sel] + w * n[sel] - y[sel]))) for m, n, y in priced)
            if best is None or e < best[0]:
                best = (e, w)
        weights[hh] = best[1]
    return weights


def horizon_blend_lines(season: int, every: pd.DataFrame, models: dict, target: pd.DataFrame, train: pd.DataFrame,
                        fit: dict[str, tuple[str, dict[str, float]]],
                        scorings: dict[str, tuple[str, dict[str, float]]]) -> pd.DataFrame:
    """``projections.project``'s hook (after pt1.0, before ``blend_lines``): every QB line of a week after the market week
    blended with the player's naive line, weight w_h by the week's distance from the market week; those rows priced and
    ranged again from the new line (``predict_position(..., lines=)``). ``scorings``: the house leagues' (what the
    weights are fitted on). Switch off, no market week, nothing after it or no weight above 0: ``every`` itself."""
    LAST_HORIZON_BLEND.clear()
    positions = [p for p in HORIZON_BLEND_POSITIONS if p in models]
    mw = market_week(target)
    if not horizon_blend_enabled() or every.empty or not positions or mw is None or not (target["week"] > mw).any():
        return every
    comps = [f"proj_{c}" for c in P.ALL_COMPONENTS]
    keys = ["gsis_id", "week"]
    first = every["league_id"].iloc[0]
    new = []
    for pos in positions:
        weights = fit_horizon_weights(train, season, scorings, pos)
        pos_train = train[train["position"] == pos]
        params = fit_naive(pos_train[pos_train["season"] >= season - WINDOW], scorings)
        LAST_HORIZON_BLEND.update({"position": pos, "market_week": mw, "weights": weights,
                                   "lambda": params.lam if params else None, "k": params.k if params else None, "moved": 0})
        if params is None or not any(v > 0 for v in weights.values()):
            continue
        tgt = target[(target["position"] == pos) & (target["week"] > mw)].drop_duplicates(keys)
        line = every[(every["league_id"] == first) & (every["position"] == pos)].merge(tgt[keys], on=keys, how="inner")
        if line.empty:
            continue
        rows = line[keys].merge(tgt, on=keys, how="left", validate="one_to_one")
        n = naive_line(rows, params)
        h = np.minimum(rows["week"].to_numpy(dtype=float) - mw + 1, HB_H_MAX).astype(int)
        w = np.array([weights.get(int(x), 0.0) for x in h])
        ln = line[[*keys, *comps]].copy()
        for c in P.ALL_COMPONENTS:
            ln[f"proj_{c}"] = (1 - w) * ln[f"proj_{c}"].to_numpy(dtype=float) + w * n[f"n_{c}"].to_numpy(dtype=float)
        new.append(P.predict_position(models[pos], rows, fit, lines=ln))
        LAST_HORIZON_BLEND["moved"] = int((w > 0).sum())
    if not new:
        return every
    moved_rows = pd.concat(new, ignore_index=True)
    for c in ("model_version", "fitted_at", "train_seasons"):
        if c in every:
            moved_rows[c] = every[c].iloc[0]
    hit = every.set_index(keys).index.isin(moved_rows.set_index(keys).index) & every["position"].isin(positions).to_numpy()
    out = pd.concat([every[~hit], moved_rows[every.columns]], ignore_index=True)
    out.attrs = every.attrs
    log.info("%s: market week %s; QB weeks after it blended with the naive line, weight by horizon %s (lambda %s, k %s); "
             "%s QB lines moved", HORIZON_BLEND_VERSION, mw, LAST_HORIZON_BLEND.get("weights"), LAST_HORIZON_BLEND.get("lambda"),
             LAST_HORIZON_BLEND.get("k"), LAST_HORIZON_BLEND["moved"])
    return out
# ---- end IQ-3


# ---- IU-5 (Wave I-U): the role record -- a recorded forecast, not a number on a screen (docs/METRICS.md § "The horizon
# grade that counts a missed week (IU-5)", "The recorded forecast"). For the live market week M and every QB with a row
# in M, h = 1..8 (T = M + h - 1): p_start = the probability that he is the listed starter in week T (rf1.0's model: one
# logistic regression per market-week role, standardised inputs, C = 1, fitted on the earlier seasons' horizon rows as
# of W = 3, 5, 7, 9; the inputs from the market week's own row, its injury designation included), v3.6's points for T
# and the mixture's points. Written by ``context_record.write_horizon_record``; nothing on any screen reads it.
ROLE_RECORD_VERSION = "rr1.0"
ROLE_RECORD_FIRST_SEASON = 2018
ROLE_RECORD_AS_OF = (3, 5, 7, 9)
ROLE_RECORD_H = tuple(range(1, 9))
ROLE_RECORD_INPUTS = ("questionable", "snap_pct_std", "pn_qb_games_together", "pn_qb_changed", "pn_qb_is_rookie_or_backup",
                      "pn_qb_prev_ppg_diff", "ppg_std", "prev_ppg", "games_to_date", "prev_games")


def role_x(rows: pd.DataFrame, med: pd.Series | None = None) -> tuple[np.ndarray, pd.Series]:
    """The forecast's inputs (one column per horizon, then the market week's row; NaN -> the training median)."""
    x = rows[list(ROLE_RECORD_INPUTS)].astype(float)
    if med is None:
        med = x.median()
    x = x.fillna(med).fillna(0.0)
    x["pn_qb_games_together"] = np.log1p(x["pn_qb_games_together"].clip(lower=0))
    hh = np.stack([(rows["h"].to_numpy() == h).astype(float) for h in ROLE_RECORD_H], axis=1)
    return np.column_stack([hh, x.to_numpy()]), med


def role_training_rows(qb: pd.DataFrame, seasons: range | list[int]) -> pd.DataFrame:
    """The horizon rows of ``seasons``: the market week M = W + 1 (W = 3, 5, 7, 9), every QB with a row in M, each target
    week T = M + h - 1 (h 1..8) where he has a row; ``t_start`` = his listed role in T, the inputs from his row in M."""
    out = []
    for s in seasons:
        q = qb[qb["season"] == s].assign(week=lambda x: x["week"].astype(int))
        role = q.drop_duplicates(["gsis_id", "week"]).set_index(["gsis_id", "week"])["pn_qb_starting"]
        for w in ROLE_RECORD_AS_OF:
            m = q[q["week"] == w + 1].drop_duplicates("gsis_id")
            if m.empty:
                continue
            for h in ROLE_RECORD_H:
                has = m["gsis_id"].isin(set(q.loc[q["week"] == w + h, "gsis_id"])).to_numpy()
                t = role.reindex(pd.MultiIndex.from_arrays([m["gsis_id"], np.full(len(m), w + h)]))
                r = m[has].assign(h=h, t_start=t.fillna(0).to_numpy(dtype=float)[has] > 0.5)
                out.append(r)
    if not out:
        return qb.iloc[0:0].assign(h=pd.Series(dtype=int), t_start=pd.Series(dtype=bool), mkt_start=pd.Series(dtype=bool))
    d = pd.concat(out, ignore_index=True)
    d["mkt_start"] = d["pn_qb_starting"].fillna(0).astype(float) > 0.5
    return d


def fit_role_record(qb: pd.DataFrame, season: int) -> dict:
    """Per market-week role (True / False): (model, medians) fitted on the horizon rows of 2018..season-1."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    tr = role_training_rows(qb, range(ROLE_RECORD_FIRST_SEASON, int(season)))
    out = {}
    for role in (True, False):
        t = tr[tr["mkt_start"] == role]
        y = t["t_start"].to_numpy().astype(int)
        if len(t) < 50 or len(set(y)) < 2:
            continue
        x, med = role_x(t)
        m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
        m.fit(x, y)
        out[role] = (m, med, len(t))
    return out


def role_record_rows(qb: pd.DataFrame, season: int, market_week: int, proj: pd.DataFrame, playing: set[tuple[str, int]],
                     means: tuple[float, float], models: dict) -> pd.DataFrame:
    """The rows to store: every QB with a row in the market week, h 1..8 where his team plays in T (``playing``: the
    (team, week) pairs with a game). ``proj``: gsis_id, week, proj_points (v3.6, the reference scoring); ``means``: the
    starters' and the others' mean points (the scored QB weeks of the 3 seasons before)."""
    m = qb[(qb["season"] == season) & (qb["week"] == market_week)].drop_duplicates("gsis_id")
    if m.empty or not models:
        return pd.DataFrame()
    pts = proj.set_index(["gsis_id", "week"])["proj_points"]
    out = []
    for h in ROLE_RECORD_H:
        t = market_week + h - 1
        r = m[[(tm, t) in playing for tm in m["team"]]].assign(h=h, target_week=t)
        if r.empty:
            continue
        r["mkt_start"] = r["pn_qb_starting"].fillna(0).astype(float) > 0.5
        r["p_start"] = np.nan
        for role, (model, med, _) in models.items():
            sel = (r["mkt_start"] == role).to_numpy()
            if sel.any():
                r.loc[sel, "p_start"] = model.predict_proba(role_x(r[sel], med)[0])[:, 1]
        line = pts.reindex(pd.MultiIndex.from_arrays([r["gsis_id"], np.full(len(r), t)])).to_numpy(dtype=float)
        p = r["p_start"].to_numpy(dtype=float)
        r["proj_v36"] = line
        r["proj_mix"] = np.where(r["mkt_start"], p * line + (1 - p) * means[1], p * means[0] + (1 - p) * line)
        out.append(r)
    if not out:
        return pd.DataFrame()
    return pd.concat(out, ignore_index=True)[["gsis_id", "player_name", "team", "h", "target_week", "mkt_start", "p_start",
                                               "proj_v36", "proj_mix"]]
# ---- end IU-5
