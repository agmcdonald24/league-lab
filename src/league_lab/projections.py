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
(per season-week-position-scorer), ``ops.projection_importance`` (plan U-15: permutation importance of
the component models in points, written by ``project``; the P50 interval model's, by ``backtest-v2``), ``ops.projection_drift`` (plan M-06: the live board's played weeks scored
like a held-out season), and a Markdown report under ``reports/backtests``.

NFL-wide outputs (plan F1, Wave F): the ranges are fitted per *reference scoring* (``reference_scorings``, the seed
``reference_scorings.csv``) and ``project`` writes ``ops.projection_lines`` (the stat line per player-week, one copy for
every league), ``ops.projection_ranges`` (per reference scoring x player-week) and, from ``kdef``, ``ops.kd_lines`` /
``ops.kd_ranges``; the house leagues' ``ops.projections`` rows are derived from the same numbers (``house_rows``).

Decision record (plan B5): a league-week's rows in ``ops.projections`` are rewritten by every refit
until the week's first kickoff and never after (``_write_projections`` / ``freeze_plan``); the rows
that were live at kickoff are kept and labelled ``frozen_source = 'kickoff'`` with ``frozen_at`` = their
publication time, and the drift scores them. The NFL-wide tables follow the same rule (``write_nfl_wide``; the unit
is the week, or the scoring x week for the ranges).
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from . import kdef as KD
from .config import PROJECT_ROOT, get_settings
from .feature_groups import personnel as _PN
from .lineup import lineups_after_project
from .rankings import TOP_N, _hit_rate, _spearman, parse_seasons
from .scoring import (  # ---- M4 (Wave I-G): the record's pricing column
    compute_points,
    pinned_writer,
    price_projected,
    priced_keys,
    pricing_engine,
    record_pricing_label,
)
from .signals import signals_after_project
from .waivers import waivers_after_project

log = logging.getLogger(__name__)

MODEL_VERSION = "v3.6"   # ---- IL-3: v3.3 = v3.0 + cs1.1 (cold starts, M6) + nt1.0 (the WR new-team scale); IP-1: v3.4 = + pt1.0 (QB passing TDs); IQ-1: v3.5 = + fi1.0 (later weeks' line and personnel); IQ-3: v3.6 = + hb1.0 (QB later weeks blended with his own per-game line)
POSITIONS = ("QB", "RB", "WR", "TE")
QUANTILES = (0.1, 0.5, 0.9)
# Plan D6 (Wave D): the 50% range ("most weeks"), fitted and calibrated with the same machinery as the
# 80% one (P10-P90) and written next to it as p25 / p75. The 80% models and their order are unchanged.
QUANTILES_50 = (0.25, 0.75)
# Plan D6 follow-up: the conformal widening of both ranges is computed per projection tier, the terciles of
# the calibration season's priced line within the position (cut points kept on the model), so a starter's
# range holds 80% / 50% on starters and not only on average; a tier with fewer than TIER_MIN_ROWS
# calibration rows takes the position-wide widening.
TIER_QUANTILES = (1 / 3, 2 / 3)
TIER_MIN_ROWS = 200

# ---- M5 (Wave I-G): v3.1 -- the ranges' target. The residual (range) models were fitted on the actual priced from
# the 12 projected components, so the 2-point conversions, the long-TD bonuses (``pass_td_40p`` ...), fumble-recovery
# and special-teams TDs the record grades on (``fct_player_game_league.points``) were outside every range (2024, a game:
# QB 0.44, RB 0.07, WR 0.12, TE 0.04 in the dynasty's scoring). With LEAGUE_LAB_RANGE_TARGET=graded the residuals are
# taken against the graded actual: ``compute_points`` over the components plus these outcome columns (``outx_<column>``,
# from ``analytics.fct_player_game``; the long-TD counts are play-by-play, as dbt's), at the positions the harness kept.
# Off by default: the verdicts are docs/METRICS.md § "Calibration of the top" -> "v3.1". The point projection is
# unchanged either way.
RANGE_TARGET_FLAG = "LEAGUE_LAB_RANGE_TARGET"
GRADED_EXTRAS = ("passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions", "fumbles_total",
                 "fumble_recovery_tds", "special_teams_tds", "pass_tds_40p", "pass_tds_50p", "rush_tds_40p",
                 "rush_tds_50p", "rec_tds_40p", "rec_tds_50p")
RANGE_TARGET_POSITIONS = ("QB",)   # where the harness kept it (2023-2025: the dynasty's QB interval score -0.0066, 2 of 3)


def range_target_graded(position: str | None = None) -> bool:
    """The switch: ``LEAGUE_LAB_RANGE_TARGET=graded`` (or 1 / true / on) fits the ranges on the graded actual at the
    positions the harness kept (``RANGE_TARGET_POSITIONS``; ``position`` None = any of them); ``graded-all`` at every
    position (the harness's setting). Default: the components' price everywhere (v3.0)."""
    import os

    v = os.environ.get(RANGE_TARGET_FLAG, "").strip().lower()
    if v in {"graded-all", "all"}:
        return True
    if v in {"graded", "1", "true", "yes", "on"}:
        return position is None or position in RANGE_TARGET_POSITIONS
    return False


def join_graded_extras(conn: psycopg.Connection, df: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    """``df`` with ``outx_<column>`` for every ``GRADED_EXTRAS`` column of the player's regular-season game (row order
    and count kept; a player-week without a game row gets NaN, as its ``out_`` columns are)."""
    cols = ", ".join(f"coalesce({c}, 0)::float8 as outx_{c}" for c in GRADED_EXTRAS)
    with conn.cursor() as cur:
        cur.execute(f"""select gsis_id, season, week, {cols} from analytics.fct_player_game
                        where season_type = 'REG' and season = any(%s)""", (seasons,))
        extra = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    extra = extra.drop_duplicates(["gsis_id", "season", "week"]).astype({"season": df["season"].dtype, "week": df["week"].dtype})
    n = len(df)
    out = df.drop(columns=[c for c in df.columns if c.startswith("outx_")]).merge(
        extra, on=["gsis_id", "season", "week"], how="left", validate="many_to_one")
    assert len(out) == n, "graded extras changed the row count"
    return out


def graded_actual(d: pd.DataFrame, scoring: dict[str, float]) -> pd.Series:
    """The actual the record grades on: ``compute_points`` (bonuses included) over the ``out_`` components and the
    ``outx_`` columns (a missing ``outx_`` column counts 0, which is the components' price)."""
    rows = d[[f"out_{c}" for c in ALL_COMPONENTS]].rename(columns=lambda c: c[4:])
    for c in GRADED_EXTRAS:
        rows[c] = d[f"outx_{c}"].fillna(0.0).to_numpy(dtype=float) if f"outx_{c}" in d else 0.0
    if "position" in d.columns:
        rows["position"] = d["position"].to_numpy()
    return pd.Series([compute_points(r, scoring) for r in rows.to_dict("records")], index=d.index, dtype=float)


def range_actual(d: pd.DataFrame, scoring: dict[str, float]) -> pd.Series:
    """What the residual models are fitted on: the graded actual under the switch (at a kept position: ``d`` is one
    position's rows in ``fit_position``), else the components' price."""
    position = str(d["position"].iloc[0]) if "position" in d.columns and len(d) else None
    return graded_actual(d, scoring) if range_target_graded(position) else price(d, scoring, "out_")


# The other two v3.1 switches (the corrections live in ``calibration``; ``project`` applies them through
# ``calibration.calibrate_outputs``, after cal1.0's map): the fringe level and the cold-start prior. Off by default.
FRINGE_FLAG = "LEAGUE_LAB_FRINGE_LEVEL"
COLD_START_FLAG = "LEAGUE_LAB_COLD_START"
# ---- /M5

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
# Projection v3 (plan D5, Wave D): personnel inputs, per position, kept by the feature-group harness on 2021-2025
# (``int_player_week_personnel`` via ``mart_player_week_features``; docs/METRICS.md § "Personnel" / § projection v3).
# QB: who starts (the projected starter vs the QB his recent games were played with); RB / WR / TE: the leading
# teammate out this week. Every position keeps the v2 inputs; the lists live with the feature group.
QB_INPUTS = list(_PN.QB)                 # pn_qb_changed, pn_qb_games_together, pn_qb_prev_ppg_diff, pn_qb_is_rookie_or_backup, pn_qb_starting
TEAMMATE_INPUTS = list(_PN.TEAMMATES)    # pn_top_target_out, pn_top_rusher_out, pn_teammate_share_out, pn_absence_beneficiary
FEATURES_BY_POSITION: dict[str, list[str]] = {
    "QB": FEATURES + QB_INPUTS,
    "RB": FEATURES + TEAMMATE_INPUTS,
    "WR": FEATURES + TEAMMATE_INPUTS,
    "TE": FEATURES + TEAMMATE_INPUTS,
}
ALL_FEATURES = list(dict.fromkeys(f for fs in FEATURES_BY_POSITION.values() for f in fs))   # what load_frame reads

# Fixed hyperparameters (a change is a new MODEL_VERSION). Small trees, strong leaf minimum:
# weekly fantasy outcomes are noisy and the training sets are a few thousand rows per position.
HGB = dict(max_iter=300, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=40, l2_regularization=1.0, random_state=0)


# ------------------------------------------------------------------------------ data
def load_frame(conn: psycopg.Connection, seasons: list[int], extra_tables: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """The as-of feature frame of ``seasons`` (QB-TE), ordered by player, season, week.

    ``extra_tables`` (plan D1, the feature-group harness): ``{"schema.table": [columns]}`` of feature tables at
    ``(gsis_id, season, week)`` grain, left-joined onto the frame as float columns (NULL = not known). The
    default (None) is the production frame, untouched."""
    cols = ["gsis_id", "season", "week", "position", "player_name", "team", "opponent", "played", "points_actual", "no_history",
            "report_status", "roster_status", *[f for f in ALL_FEATURES if f != "questionable"], *[f"out_{c}" for c in ALL_COMPONENTS]]
    # ordered: the early-stopping validation split (automatic above 10k rows) follows row order, so an
    # unordered scan (synchronized seq scans on a 60 MB table) made two fits of the same data differ
    sql = (f"select {', '.join(dict.fromkeys(cols))} from analytics.mart_player_week_features "
           "where season = any(%s) and position = any(%s) order by gsis_id, season, week")
    with conn.cursor() as cur:
        cur.execute(sql, (seasons, list(POSITIONS)))
        names = [d.name for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=names)
    for c in df.columns:
        if c in ALL_FEATURES or c.startswith("out_") or c == "points_actual":
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["questionable"] = (df["report_status"] == "Questionable").astype(float)
    for table, extra in (extra_tables or {}).items():
        df = _join_feature_table(conn, df, table, extra, seasons)
    if range_target_graded():   # ---- M5: the graded actual's outcome columns (the residual models' target)
        df = join_graded_extras(conn, df, seasons)
    return df


def _join_feature_table(conn: psycopg.Connection, df: pd.DataFrame, table: str, columns: list[str], seasons: list[int]) -> pd.DataFrame:
    """Left-join one feature table's ``columns`` at ``(gsis_id, season, week)`` (row order kept: the fit depends on it)."""
    from psycopg import sql

    schema, name = table.split(".", 1)
    q = sql.SQL("select gsis_id, season, week, {} from {}.{} where season = any(%s)").format(
        sql.SQL(", ").join(sql.Identifier(c) for c in columns), sql.Identifier(schema), sql.Identifier(name))
    with conn.cursor() as cur:
        cur.execute(q, (seasons,))
        extra = pd.DataFrame(cur.fetchall(), columns=["gsis_id", "season", "week", *columns])
    for c in columns:   # booleans and numerics alike: float, NULL -> NaN (HGB treats it as "not known")
        extra[c] = pd.to_numeric(extra[c].map(lambda v: float(v) if v is not None else np.nan), errors="coerce").astype(float)
    extra = extra.astype({"season": df["season"].dtype, "week": df["week"].dtype})   # week is float in the frame (it is a feature)
    clash = [c for c in columns if c in df.columns]
    if clash:
        raise ValueError(f"{table}: columns {clash} already exist in the feature frame")
    n = len(df)
    df = df.merge(extra, on=["gsis_id", "season", "week"], how="left", validate="many_to_one")
    assert len(df) == n, f"{table}: the join changed the row count ({n} -> {len(df)})"
    return df


def league_scorings(conn: psycopg.Connection) -> dict[str, tuple[str, dict[str, float]]]:
    """league_id -> (league_name, scoring_settings) for every current league-season, reference first."""
    with conn.cursor() as cur:
        cur.execute("""select league_id, league_name, scoring_settings from analytics.dim_league_season
                       where is_current_season order by is_reference_league desc, league_name""")
        return {r[0]: (r[1], {k: float(v) for k, v in r[2].items()}) for r in cur.fetchall()}


REFERENCE_SEED = PROJECT_ROOT / "dbt" / "seeds" / "reference_scorings.csv"
MATCH_TOL = 1e-9     # two weights closer than this are the same weight (Sleeper stores float32-looking values)


def reference_scorings(conn: psycopg.Connection | None = None) -> dict[str, tuple[str, dict[str, float]]]:
    """name -> (label, scoring_settings) of the reference scorings (plan F1), in name order: the shape
    ``league_scorings`` returns, keyed by the seed's ``name``. Read from ``analytics_seeds.reference_scorings``
    (what the dbt tests price with); the seed file when the table is not built yet (a fresh database)."""
    rows: list[tuple[str, str, object]] = []
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('analytics_seeds.reference_scorings') is not null")
            if cur.fetchone()[0]:
                cur.execute("select name, label, scoring_settings from analytics_seeds.reference_scorings order by name")
                rows = list(cur.fetchall())
    if not rows:
        log.warning("analytics_seeds.reference_scorings is not built: reading %s (run `dbt seed`)", REFERENCE_SEED.name)
        with open(REFERENCE_SEED, newline="") as fh:
            rows = sorted((r["name"], r["label"], r["scoring_settings"]) for r in csv.DictReader(fh))
    out: dict[str, tuple[str, dict[str, float]]] = {}
    for name, label, settings in rows:
        d = json.loads(settings) if isinstance(settings, str) else dict(settings or {})
        out[str(name)] = (str(label), {k: float(v) for k, v in d.items() if v is not None})
    return out


def exact_reference(scoring: dict[str, float], references: dict[str, tuple[str, dict[str, float]]]) -> str | None:
    """The reference scoring that prices every projected QB-TE stat line exactly as ``scoring`` does: the same
    non-zero weights on the keys the line can carry (``scoring.priced_keys`` over ``ALL_COMPONENTS``, the
    position premiums included), each within ``MATCH_TOL``. None when no reference is that scoring."""
    mine = priced_keys(scoring, ALL_COMPONENTS)
    for name, (_, ref) in references.items():
        theirs = priced_keys(ref, ALL_COMPONENTS)
        if theirs.keys() == mine.keys() and all(abs(theirs[k] - mine[k]) <= MATCH_TOL for k in mine):
            return name
    return None


def fit_scorings(leagues: dict[str, tuple[str, dict[str, float]]], references: dict[str, tuple[str, dict[str, float]]]
                 ) -> tuple[dict[str, tuple[str, dict[str, float]]], dict[str, str]]:
    """What ``project`` fits (plan F1): every reference scoring, plus a house league no reference is (its ranges
    are fitted on its own, as before Wave F). Returns (scorings to fit, league_id -> the key its ops.projections
    rows take their ranges from: a reference name, or the league_id itself)."""
    fit = dict(references)
    source: dict[str, str] = {}
    for lid, (name, scoring) in leagues.items():
        ref = exact_reference(scoring, references)
        if ref is None:
            log.warning("%s (%s): no reference scoring prices its stat lines exactly; fitted on its own (add it to "
                        "dbt/seeds/reference_scorings.csv)", name, lid)
            fit[lid] = (name, scoring)
            source[lid] = lid
        else:
            source[lid] = ref
    return fit, source


def price(df: pd.DataFrame, scoring: dict[str, float], prefix: str, position: str | None = None) -> pd.Series:
    """League points of a stat line held in ``<prefix><component>`` columns (bonus keys included where computable).
    The player's position (the frame's ``position`` column, else ``position``) rides along so a position premium
    (``bonus_rec_te``, plan F1) prices; a scoring without one prices exactly as before."""
    rows = df[[f"{prefix}{c}" for c in ALL_COMPONENTS]].rename(columns=lambda c: c[len(prefix):])
    if "position" in df.columns:
        rows["position"] = df["position"].to_numpy()
    elif position is not None:
        rows["position"] = position
    # ---- M3 (Wave I-D): a PROJECTED line goes through the one entry point the request side calls too
    # (``scoring.price_projected``: the flat engine, or its expected-value pricing under LEAGUE_LAB_EV_PRICING); an
    # ACTUAL line (``out_``) stays on the exact engine — its bonus happened or it did not
    if prefix == "proj_":
        return pd.Series(price_projected(rows, scoring), index=df.index, dtype=float)
    # ---- /M3
    return pd.Series([compute_points(r, scoring) for r in rows.to_dict("records")], index=df.index, dtype=float)


# ------------------------------------------------------------------------------ models
@dataclass
class PositionModel:
    position: str
    components: dict[str, object] = field(default_factory=dict)      # component -> regressor
    quantiles: dict[tuple[str, float], object] = field(default_factory=dict)  # (scoring key, q) -> regressor (F1: a reference name or a league_id)
    conformal: dict[str, float] = field(default_factory=dict)        # league_id -> interval widening (points)
    conformal_50: dict[str, float] = field(default_factory=dict)     # league_id -> widening of the 50% range (plan D6)
    tier_cuts: dict[str, tuple[float, ...]] = field(default_factory=dict)          # league_id -> projection tier cut points
    conformal_tiers: dict[str, tuple[float, ...]] = field(default_factory=dict)    # league_id -> 80% widening per tier
    conformal_50_tiers: dict[str, tuple[float, ...]] = field(default_factory=dict) # league_id -> 50% widening per tier
    n_rows: int = 0
    calibration_season: int | None = None
    features: list[str] | None = None    # the inputs it was fitted on (fit_position always sets them); None = FEATURES


def _regressor(loss: str, quantile: float | None = None):
    from sklearn.ensemble import HistGradientBoostingRegressor

    kw = dict(HGB)
    if quantile is not None:
        return HistGradientBoostingRegressor(loss="quantile", quantile=quantile, **kw)
    return HistGradientBoostingRegressor(loss=loss, **kw)


def _line_points(m: PositionModel, x: np.ndarray, scoring: dict[str, float]) -> np.ndarray:
    """The priced projected line for a feature matrix (the anchor the quantile models work from)."""
    comp = pd.DataFrame({f"proj_{c}": (np.clip(m.components[c].predict(x), 0, None) if c in m.components else 0.0) for c in ALL_COMPONENTS})
    return price(comp, scoring, "proj_", m.position).to_numpy(dtype=float)


def _quantile_features(x: np.ndarray, line: np.ndarray) -> np.ndarray:
    return np.column_stack([x, line])


def _binnable(x: np.ndarray) -> np.ndarray:
    """A copy where a column that is entirely unknown becomes 0, so the binner has something to
    bin (a first-read share on seasons before charting exists, say); the model then ignores it."""
    x = x.copy()
    all_nan = np.isnan(x).all(axis=0)
    x[:, all_nan] = 0.0
    return x


def _matrix(d: pd.DataFrame, features: list[str] | None = None) -> np.ndarray:
    """Feature matrix (NaN = not known yet). ``features`` (plan D1 harness): default FEATURES.
    ---- IQ-3: NaN stays NaN. A column unknown in the whole batch used to become 0 here, for prediction too: a batch of
    later weeks alone (no betting line, no teammate report) then read "implied total 0" instead of "not known". The
    fits zero such a column themselves (``_fit_components``, the quantile fits: ``_binnable``), and a model never splits
    on a column that was constant in its fit, so a full season's batch predicts exactly as before."""
    return d[FEATURES if features is None else features].to_numpy(dtype=float)


def _fit_components(x: np.ndarray, d: pd.DataFrame, position: str) -> dict[str, object]:
    models: dict[str, object] = {}
    for c in COMPONENTS[position]:
        y = d[f"out_{c}"].to_numpy(dtype=float)
        loss = "squared_error" if c in YARDS else "poisson"
        if loss == "poisson":
            y = np.clip(y, 0, None)
        models[c] = _regressor(loss).fit(_binnable(x), y)
    return models


def _price_models(models: dict[str, object], x: np.ndarray, scoring: dict[str, float], position: str | None = None) -> np.ndarray:
    comp = pd.DataFrame({f"proj_{c}": (np.clip(models[c].predict(x), 0, None) if c in models else 0.0) for c in ALL_COMPONENTS})
    return price(comp, scoring, "proj_", position).to_numpy(dtype=float)


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
            lines[lid][te] = _price_models(models, x[te], scoring, position)
    return lines


def _short(key: str) -> str:
    """A league id's last six digits in a log line; a reference scoring's name as it is."""
    return key[-6:] if str(key).isdigit() else str(key)


def fit_position(train: pd.DataFrame, position: str, scorings: dict[str, tuple[str, dict[str, float]]],
                 features: list[str] | None = None) -> PositionModel:
    """``features`` (plan D1 harness): the input columns; default the position's production inputs
    (``FEATURES_BY_POSITION``, v3). The model keeps them (``predict_position`` / importance use them)."""
    features = list(FEATURES_BY_POSITION[position] if features is None else features)
    d = train[(train["position"] == position) & train["played"] & ~train["no_history"]]
    d = d.dropna(subset=[f"out_{c}" for c in COMPONENTS[position]]).reset_index(drop=True)
    x = _matrix(d, features)
    m = PositionModel(position, n_rows=len(d), features=features)
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
    #    Plan D6 follow-up: per projection tier (terciles of the calibration season's line), so it holds
    #    for starters too (position-wide, starters' ranges held 76-77% and the fringe's more than 80%).
    seasons = sorted(d["season"].unique())
    cal_season = seasons[-1] if len(seasons) >= 3 else None
    is_cal = (d["season"] == cal_season).to_numpy() if cal_season else np.zeros(len(d), dtype=bool)
    m.calibration_season = cal_season
    oof = _oof_lines(x, d, position, scorings)
    for league_id, (_, scoring) in scorings.items():
        line = oof[league_id]
        ok = ~np.isnan(line)
        y = range_actual(d, scoring).to_numpy(dtype=float) - line   # ---- M5: the graded actual under LEAGUE_LAB_RANGE_TARGET
        xq = _quantile_features(x, np.nan_to_num(line))
        fit_idx, cal_idx = ok & ~is_cal, ok & is_cal
        for q in QUANTILES:
            m.quantiles[(league_id, q)] = _regressor("quantile", q).fit(_binnable(xq[fit_idx]), y[fit_idx])
        # plan D6: the 50% range, fitted after the 80% models (each regressor has its own seed, so the
        # P10 / P50 / P90 models are exactly what they were) and calibrated the same way for 50%
        for q in QUANTILES_50:
            m.quantiles[(league_id, q)] = _regressor("quantile", q).fit(_binnable(xq[fit_idx]), y[fit_idx])
        xc, yc = xq[cal_idx], y[cal_idx]
        tiers = None
        if cal_idx.sum() >= 50:
            m.tier_cuts[league_id] = tuple(float(c) for c in np.quantile(line[cal_idx], TIER_QUANTILES))
            tiers = np.searchsorted(m.tier_cuts[league_id], line[cal_idx])
        for (q_lo, q_hi), pooled, per_tier in (((QUANTILES[0], QUANTILES[-1]), m.conformal, m.conformal_tiers),
                                               (QUANTILES_50, m.conformal_50, m.conformal_50_tiers)):
            lo = m.quantiles[(league_id, q_lo)].predict(xc) if len(yc) else np.zeros(0)
            hi = m.quantiles[(league_id, q_hi)].predict(xc) if len(yc) else np.zeros(0)
            pooled[league_id] = _conformal_widening(lo, hi, yc, q_hi - q_lo)
            if tiers is not None:
                per_tier[league_id] = tuple(_conformal_widening(lo[tiers == t], hi[tiers == t], yc[tiers == t], q_hi - q_lo)
                                            if (tiers == t).sum() >= TIER_MIN_ROWS else pooled[league_id]
                                            for t in range(len(TIER_QUANTILES) + 1))
    log.info("fit %s: %s rows, %s components, %s quantile models, calibration season %s, widening 80%% by tier %s, 50%% by tier %s",
             position, len(d), len(m.components), len(m.quantiles), cal_season,
             {_short(k): [round(v, 2) for v in t] for k, t in m.conformal_tiers.items()},
             {_short(k): [round(v, 2) for v in t] for k, t in m.conformal_50_tiers.items()})
    return m


def _conformal_widening(lo: np.ndarray, hi: np.ndarray, y_cal: np.ndarray, coverage: float) -> float:
    """Split-conformal widening (CQR) of the range [lo, hi] predicted for the calibration rows: the
    ceil((n + 1) x coverage) / n quantile of how far each actual falls outside it (negative = inside), so that
    share of held-out outcomes lands inside once both ends move out by it. 0 with fewer than 50 rows."""
    n = len(y_cal)
    if n < 50:
        return 0.0
    miss = np.maximum(lo - y_cal, y_cal - hi)      # negative when inside the interval
    level = min(1.0, np.ceil((n + 1) * coverage) / n)
    return float(np.quantile(miss, level))


def _widening(m: PositionModel, league_id: str, line: np.ndarray, band: str) -> np.ndarray | float:
    """Per row: the widening of its projection tier (``band`` '80' or '50'); the position-wide value for a model
    without tiers."""
    per_tier = (m.conformal_tiers if band == "80" else m.conformal_50_tiers).get(league_id)
    pooled = (m.conformal if band == "80" else m.conformal_50).get(league_id, 0.0)
    if not per_tier or league_id not in m.tier_cuts:
        return pooled
    return np.asarray(per_tier, dtype=float)[np.searchsorted(m.tier_cuts[league_id], line)]


def predict_position(m: PositionModel, rows: pd.DataFrame, scorings: dict[str, tuple[str, dict[str, float]]],
                     lines: pd.DataFrame | None = None) -> pd.DataFrame:
    """One output row per scoring (``league_id`` = its key) per input row: projected line, priced points, P10/P50/P90
    and (plan D6) P25/P75. ``lines`` (plan F1, row-aligned ``proj_<component>`` columns): price and range a given
    stat line instead of the components' prediction (a frozen week's stored line, ranged in a scoring that has
    no stored range yet)."""
    x = _matrix(rows, m.features)
    out = rows[["gsis_id", "season", "week", "position"]].copy()
    out["season"], out["week"] = out["season"].astype(int), out["week"].astype(int)   # week is also a feature (float)
    for c in ALL_COMPONENTS:
        if lines is not None:
            out[f"proj_{c}"] = pd.to_numeric(lines[f"proj_{c}"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        else:
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
        adj = _widening(m, league_id, line, "80")
        o["p10"], o["p50"], o["p90"] = np.clip(qs[:, 0] - adj, 0, None), qs[:, 1], qs[:, 2] + adj
        o["p90"] = np.maximum(o["p90"], o["proj_points"])   # the ceiling never sits below the projection
        o["p50"] = np.clip(o["p50"], o["p10"], o["p90"])     # keep the order after the floor was clipped at 0
        # plan D6: the 50% range, sorted and widened the same way, then kept inside the 80% one around P50
        # (P10 <= P25 <= P50 <= P75 <= P90); a model fitted before D6 has no 50% models: NULL
        if all((league_id, q) in m.quantiles for q in QUANTILES_50):
            q50 = np.sort(np.column_stack([line + m.quantiles[(league_id, q)].predict(xq) for q in QUANTILES_50]), axis=1)
            adj50 = _widening(m, league_id, line, "50")
            o["p25"] = np.clip(q50[:, 0] - adj50, o["p10"], o["p50"])
            o["p75"] = np.clip(q50[:, 1] + adj50, o["p50"], o["p90"])
        else:
            o["p25"], o["p75"] = np.nan, np.nan
        frames.append(o)
    return pd.concat(frames, ignore_index=True)


def importance(m: PositionModel, test: pd.DataFrame, league_id: str, scoring: dict[str, float]) -> pd.DataFrame:
    """Permutation importance of the P50 model on the held-out rows (drop in pinball loss)."""
    from sklearn.inspection import permutation_importance

    d = test[(test["position"] == m.position) & test["played"]].dropna(subset=[f"out_{c}" for c in COMPONENTS[m.position]])
    if len(d) < 50:
        return pd.DataFrame(columns=["position", "feature", "importance"])
    x = _matrix(d, m.features)
    line = _line_points(m, x, scoring)
    y = price(d, scoring, "out_").to_numpy(dtype=float) - line
    r = permutation_importance(m.quantiles[(league_id, 0.5)], _quantile_features(x, line), y, scoring="neg_mean_absolute_error", n_repeats=3, random_state=0)
    return pd.DataFrame({"position": m.position, "feature": [*(m.features or FEATURES), "priced_line"], "importance": r.importances_mean}).sort_values("importance", ascending=False)


# ------------------------------------------------------------------------------ importance of the projection itself (plan U-15)
# `importance()` above measures the P50 *interval* model, whose main input is the priced line: it
# describes the residual adjuster, not what drives the projection. What drives the projection are the
# component models (targets, catches, yards, TDs ... per position). `component_importance` scrambles one
# input at a time for all of them together, prices the scrambled stat line in the reference league's
# scoring and reports how many points of error that adds (plus each component's own rise in its units).

IMPORTANCE_REPEATS = 5   # shuffles per feature; the reported number is their mean (sd alongside)

COMPONENT_LABELS: dict[str, str] = {
    "targets": "Targets", "receptions": "Catches", "receiving_yards": "Receiving yards", "receiving_tds": "Receiving TDs",
    "carries": "Carries", "rushing_yards": "Rushing yards", "rushing_tds": "Rushing TDs", "attempts": "Pass attempts",
    "passing_yards": "Passing yards", "passing_tds": "Passing TDs", "passing_interceptions": "Interceptions thrown",
    "fumbles_lost_total": "Fumbles lost",
}

# Every model input in plain words (the Rankings page shows these, never the column names).
# tests/test_projection_importance.py: every model input (ALL_FEATURES) has one, and no two share a label.
FEATURE_LABELS: dict[str, str] = {
    "week": "Week of the season",
    "games_to_date": "Games played so far this season",
    "f_sample": "How much this season counts vs last (grows over 6 games)",
    "prev_games": "Games played last season",
    "ppg_std": "Points per game, season",
    "ppg_l3": "Points per game, last 3 games",
    "ppg_l5": "Points per game, last 5 games",
    "points_sd_std": "How much his points swing week to week, season",
    "xppg_std": "Expected points per game (what his touches are worth), season",
    "xppg_l3": "Expected points per game, last 3 games",
    "xppg_l5": "Expected points per game, last 5 games",
    "prev_ppg": "Points per game, last season",
    "prev_xppg": "Expected points per game, last season",
    "pos_prev_ppg": "Typical points per game for his position, last season",
    "target_share_std": "Share of his team's targets, season",
    "target_share_l3": "Share of his team's targets, last 3 games",
    "carry_share_std": "Share of his team's carries, season",
    "carry_share_l3": "Share of his team's carries, last 3 games",
    "snap_pct_std": "Snap share, season",
    "snap_pct_l3": "Snap share, last 3 games",
    "air_yards_share_l3": "Share of his team's air yards (throws downfield), last 3 games",
    "first_read_share_std": "How often he is the QB's first look, season",
    "first_read_share_l3": "How often he is the QB's first look, last 3 games",
    "prev_snap_pct": "Snap share, last season",
    "opp_allowed_std": "Points the opponent gives up to his position, season",
    "opp_allowed_l4": "Points the opponent gives up to his position, last 4 games",
    "opp_rank_std": "Opponent's rank against his position",
    "league_allowed_avg": "League-average points given up to his position",
    "f_opp_allowed_diff": "Opponent vs league average, points given up to his position",
    "implied_team_total": "Points Vegas expects his team to score",
    "spread_line": "Point spread (Vegas)",
    "total_line": "Game over/under (Vegas)",
    "f_home": "Home or away",
    "questionable": "Listed Questionable on the injury report",
    "red_zone_targets_pg_std": "Red-zone targets per game, season",
    "red_zone_targets_pg_l3": "Red-zone targets per game, last 3 games",
    "red_zone_carries_pg_std": "Red-zone carries per game, season",
    "red_zone_carries_pg_l3": "Red-zone carries per game, last 3 games",
    **{f"{c}_pg_std": f"{n} per game, season" for c, n in COMPONENT_LABELS.items()},
    **{f"{c}_pg_l3": f"{n} per game, last 3 games" for c, n in COMPONENT_LABELS.items()},
    **{f"prev_{c}_pg": f"{n} per game, last season" for c, n in COMPONENT_LABELS.items()},
    # v3 (plan D5): who plays next to him this week
    "pn_qb_changed": "A different QB starts than in his recent games",
    "pn_qb_games_together": "Games he has played with this week's QB",
    "pn_qb_prev_ppg_diff": "This week's QB vs his usual QB, points per start",
    "pn_qb_is_rookie_or_backup": "This week's QB has started fewer than 8 games",
    "pn_qb_starting": "Is he the projected starter?",
    "pn_top_target_out": "Top target on his team out this week",
    "pn_top_rusher_out": "Top ball carrier on his team out this week",
    "pn_teammate_share_out": "Share of the team's targets out this week",
    "pn_absence_beneficiary": "His role grew when a teammate went out, and that teammate is still out",
    "priced_line": "The projection itself (the interval model's input)",
}

IMPORTANCE_COLUMNS = ["position", "component", "feature", "feature_label", "unit", "importance", "importance_sd",
                      "importance_points", "baseline_mae", "n_rows"]


def unit_points(scoring: dict[str, float]) -> dict[str, float]:
    """Points one unit of each stat-line component is worth under ``scoring`` (stat keys only: a
    yardage bonus is not a per-unit value). The reference league has no bonus keys, so there a stat
    line's points are exactly the sum of component x unit points; ``targets`` is worth 0 in most leagues."""
    return {c: compute_points({c: 1.0}, scoring, include_bonuses=False) for c in ALL_COMPONENTS}


def component_importance(m: PositionModel, rows: pd.DataFrame, scoring: dict[str, float],
                         n_repeats: int = IMPORTANCE_REPEATS, seed: int = 0) -> pd.DataFrame:
    """Permutation importance of the component models, in points (plan U-15).

    Rows: the position's played player-weeks with history and known outcomes (the training filter
    of ``fit_position``). For each feature, ``n_repeats`` times: shuffle that one column, re-predict
    every component (clipped at 0, as ``predict_position`` does), and measure the mean absolute error
    against what happened:

    * per component (``component`` = e.g. ``targets``, ``unit`` = the component): the rise in that
      component's MAE, and ``importance_points`` = that rise x the component's points per unit;
    * for the projection (``component = 'total'``, ``unit = 'points'``): the rise in the MAE of the
      priced line (sum of component x points per unit) against the player's actual points, both in
      ``scoring``. This is the headline: "points of error added when the feature is scrambled". It
      weights each component by its points per unit, like summing the per-component
      ``importance_points``, but lets errors in different components offset or compound the way they
      do in the real projection, and counts the stats the model does not project (a WR's pass) in
      the actual points, as the board's misses do.

    The mean over the shuffles is ``importance``, their standard deviation ``importance_sd``; the
    unscrambled MAE is ``baseline_mae``. A feature that never varies on these rows scores 0.
    Deterministic for a given ``seed``; the models are only read (predictions are unaffected).
    """
    comps = [c for c in COMPONENTS[m.position] if c in m.components]
    d = rows[(rows["position"] == m.position) & rows["played"].fillna(False).astype(bool) & ~rows["no_history"].fillna(False).astype(bool)]
    d = d.dropna(subset=[f"out_{c}" for c in comps]).reset_index(drop=True)
    if len(d) < 50 or not comps:
        return pd.DataFrame(columns=IMPORTANCE_COLUMNS)
    x = _matrix(d, m.features)
    w = unit_points(scoring)
    outs = np.nan_to_num(d[[f"out_{c}" for c in ALL_COMPONENTS]].to_numpy(dtype=float))
    y_pts = outs @ np.array([w[c] for c in ALL_COMPONENTS])          # what the player actually scored (stat keys)
    y = {c: d[f"out_{c}"].to_numpy(dtype=float) for c in comps}
    wc = np.array([w[c] for c in comps])

    def predict(xm: np.ndarray) -> np.ndarray:                       # (rows, components)
        return np.column_stack([np.clip(m.components[c].predict(xm), 0, None) for c in comps])

    def maes(p: np.ndarray) -> tuple[float, np.ndarray]:
        return float(np.mean(np.abs(y_pts - p @ wc))), np.array([np.mean(np.abs(y[c] - p[:, k])) for k, c in enumerate(comps)])

    base_pts, base_c = maes(predict(x))
    n = len(d)
    rng = np.random.default_rng(seed)
    out: list[dict[str, object]] = []
    for j, f in enumerate(m.features or FEATURES):
        col = x[:, j]
        nan = np.isnan(col)
        varies = np.unique(col[~nan]).size + int(nan.any()) > 1      # "unknown" counts as a value of its own
        perms = [rng.permutation(n) for _ in range(n_repeats)]      # drawn for every feature: a skipped column never shifts the others
        rise_pts, rise_c = np.zeros(n_repeats), np.zeros((n_repeats, len(comps)))
        if varies:
            # all the shuffles of this column in one matrix: one predict call per component (the per-call
            # overhead of 300 trees dominates at these sizes)
            xp = np.tile(x, (n_repeats, 1))
            xp[:, j] = np.concatenate([col[p] for p in perms])
            pp = predict(xp)
            for r in range(n_repeats):
                mp, mc = maes(pp[r * n:(r + 1) * n])
                rise_pts[r], rise_c[r] = mp - base_pts, mc - base_c
        label = FEATURE_LABELS.get(f, f)
        out.append({"position": m.position, "component": "total", "feature": f, "feature_label": label, "unit": "points",
                    "importance": float(rise_pts.mean()), "importance_sd": float(rise_pts.std()),
                    "importance_points": float(rise_pts.mean()), "baseline_mae": base_pts, "n_rows": len(d)})
        for k, c in enumerate(comps):
            out.append({"position": m.position, "component": c, "feature": f, "feature_label": label, "unit": c,
                        "importance": float(rise_c[:, k].mean()), "importance_sd": float(rise_c[:, k].std()),
                        "importance_points": float(rise_c[:, k].mean() * abs(wc[k])), "baseline_mae": float(base_c[k]),
                        "n_rows": len(d)})
    return pd.DataFrame(out, columns=IMPORTANCE_COLUMNS)


def importance_after_project(conn: psycopg.Connection, train: pd.DataFrame, scorings: dict[str, tuple[str, dict[str, float]]],
                             train_seasons: str, force: bool = False) -> pd.DataFrame | None:
    """Side output of ``project`` (plan U-15): what drives the projection, into ``ops.projection_importance``
    (``model = 'component'``; the interval model's rows from ``backtest-v2`` stay, ``model = 'quantile_p50'``).

    Measured on the newest training season (``eval_season``) with a **twin** of the production component
    models fitted on the same window minus that season (``fit_seasons``): the same models that score that
    season in the walk-forward backtest. Scrambling inputs on rows a model was fitted on overstates the
    inputs it memorised (2025 QBs: rushing yards per game this season added 0.20 points of error on the
    production models, which saw 2025, and 0.05 on the twin, which did not), so the page shows the
    held-out number. In the reference league's scoring.

    Computed once per ``MODEL_VERSION`` x training window (a few minutes: one extra component fit and
    the shuffles), kept on later runs (the nightly restores the table from the hosted copy); ``force``
    recomputes. It never touches the production models or the projections, runs after they are written,
    and a failure is logged, never fatal."""
    try:
        with conn.cursor() as cur:
            cur.execute(DDL["ops.projection_importance"])
            cur.execute("""select count(*) from ops.projection_importance
                           where model_version = %s and model = 'component' and train_seasons = %s""", (MODEL_VERSION, train_seasons))
            have = cur.fetchone()[0]
        conn.commit()
        if have and not force:
            log.info("importance: kept (%s rows for %s, trained %s)", have, MODEL_VERSION, train_seasons)
            return None
        ref_id = next(iter(scorings))
        eval_season = int(train["season"].max())
        past = train[train["season"] < eval_season]
        rows = train[train["season"] == eval_season]
        frames = []
        for pos in POSITIONS:
            d = past[(past["position"] == pos) & past["played"] & ~past["no_history"]]          # fit_position's training filter
            d = d.dropna(subset=[f"out_{c}" for c in COMPONENTS[pos]]).reset_index(drop=True)
            feats = FEATURES_BY_POSITION[pos]
            twin = PositionModel(pos, components=_fit_components(_matrix(d, feats), d, pos), n_rows=len(d), features=feats)
            frames.append(component_importance(twin, rows, scorings[ref_id][1]))
        imp = pd.concat(frames, ignore_index=True)
        imp["model_version"], imp["model"], imp["run_at"], imp["league_id"] = MODEL_VERSION, "component", datetime.now(UTC), ref_id
        imp["train_seasons"], imp["eval_season"] = train_seasons, eval_season
        imp["fit_seasons"] = f"{int(past['season'].min())}-{int(past['season'].max())}"
        _write(conn, "ops.projection_importance", imp, "model_version = %s and model = 'component'", (MODEL_VERSION,))
        top = imp[imp["component"] == "total"].sort_values("importance", ascending=False).groupby("position").head(1)
        log.info("importance written: %s rows (%s season, held out from a %s fit, %s scoring); top input per position: %s", len(imp),
                 eval_season, imp["fit_seasons"].iloc[0], scorings[ref_id][0],
                 {r.position: f"{r.feature} +{r.importance:.2f} pts" for r in top.itertuples()})
        return imp
    except Exception:
        conn.rollback()
        log.exception("projection importance failed (projections were written); the next `league-lab project` retries")
        return None


def run_importance(force: bool = True) -> pd.DataFrame | None:
    """Recompute the importance on its own (``uv run python -c 'from league_lab.projections import run_importance; run_importance()'``)."""
    s = get_settings()
    with psycopg.connect(s.pipeline_dsn(), autocommit=False) as conn:
        season = max(available_seasons(conn))
        train_seasons = [x for x in available_seasons(conn) if x < season]
        train = load_frame(conn, train_seasons)
        return importance_after_project(conn, train, league_scorings(conn), f"{min(train_seasons)}-{max(train_seasons)}", force=force)


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
                    # plan D6: the 50% range (stored in ops.projection_backtest from v3.0 on)
                    **(_scores_50(y, g) if name != "baseline" else {}),
                })
    return pd.DataFrame(out)


def _scores_50(y: pd.Series, g: pd.DataFrame) -> dict[str, float | None]:
    """Coverage, pinball losses and width of the 50% range [P25, P75] (plan D6); None when the frame has none."""
    if "p25" not in g or "p75" not in g or g["p25"].isna().any() or g["p75"].isna().any():
        return {"coverage_50": None, "pinball_25": None, "pinball_75": None, "interval_width_50": None}
    yv = y.to_numpy()
    return {"coverage_50": float(((y >= g["p25"]) & (y <= g["p75"])).mean()),
            "pinball_25": _pinball(yv, g["p25"].to_numpy(), 0.25), "pinball_75": _pinball(yv, g["p75"].to_numpy(), 0.75),
            "interval_width_50": float((g["p75"] - g["p25"]).mean())}


def load_baseline(conn: psycopg.Connection, seasons: list[int]) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("""select gsis_id, season, week, proj_points as baseline_points from analytics.mart_player_week_rankings
                       where season = any(%s) and is_rankable""", (seasons,))
        return pd.DataFrame(cur.fetchall(), columns=["gsis_id", "season", "week", "baseline_points"]).astype({"baseline_points": float})


# ------------------------------------------------------------------------------ walk-forward backtest
def walk_forward(frame: pd.DataFrame, test_seasons: list[int], scorings: dict[str, tuple[str, dict[str, float]]], first: int,
                 baseline: pd.DataFrame | None, features: list[str] | dict[str, list[str]] | None = None, positions: tuple[str, ...] = POSITIONS,
                 importance_ref: str | None = None) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """The walk-forward loop of ``backtest``: for each test season N, fit every position on seasons
    ``first``..N-1 of ``frame`` and score N. ``features`` / ``positions`` (plan D1, the feature-group
    harness) default to production; ``importance_ref`` (a league id) also measures the P50 model's
    permutation importance on the newest test season. Returns the per-week scores and the importances."""
    results: list[pd.DataFrame] = []
    imps: list[pd.DataFrame] = []
    for n in test_seasons:
        train = frame[(frame["season"] >= first) & (frame["season"] < n)]
        test = frame[frame["season"] == n]
        if train.empty or test.empty:
            log.warning("season %s: no train (%s rows) or test (%s rows)", n, len(train), len(test))
            continue
        preds = []
        for pos in positions:
            feats = features.get(pos) if isinstance(features, dict) else features     # v3: per position
            m = fit_position(train, pos, {k: v for k, v in scorings.items()}, feats)
            preds.append(predict_position(m, test[test["position"] == pos], scorings))
            if importance_ref is not None and n == max(test_seasons):
                imps.append(importance(m, test, importance_ref, scorings[importance_ref][1]))
        pred = pd.concat(preds, ignore_index=True)
        pred.attrs["scorings"] = {k: v[1] for k, v in scorings.items()}
        actual = test[test["played"]][["gsis_id", "season", "week", "position", *[f"out_{c}" for c in ALL_COMPONENTS]]].dropna()
        res = score_predictions(pred, actual, baseline)
        res["train_seasons"] = f"{first}-{n - 1}"
        results.append(res)
        log.info("season %s scored: %s rows", n, len(res))
    return pd.concat(results, ignore_index=True), imps


@pinned_writer   # ---- M4: the writer prices in the env's mode alone (never the record it writes)
def backtest(conn: psycopg.Connection, test_seasons: list[int], out_dir: Path | None = None) -> pd.DataFrame:
    scorings = league_scorings(conn)
    all_seasons = available_seasons(conn)
    first = min(all_seasons)
    frame = load_frame(conn, [s for s in all_seasons if s <= max(test_seasons)])
    baseline = load_baseline(conn, test_seasons)
    ref_id = next(iter(scorings))
    res, imps = walk_forward(frame, test_seasons, scorings, first, baseline, importance_ref=ref_id)
    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    res["run_id"], res["run_at"], res["model_version"] = run_id, datetime.now(UTC), MODEL_VERSION
    res["pricing"] = res["league_id"].map({lid: record_pricing_label(sc) for lid, (_, sc) in scorings.items()})  # ---- M4
    # the K / DEF rows (R-13, model kd1.0, `league-lab backtest-kd`) share the table: not this run's to delete
    # v3: only this model version's rows are replaced (v2.0's stay as its record; K / DEF rows are kd1.0's)
    _write(conn, "ops.projection_backtest", res, "season = any(%s) and model_version = %s", (test_seasons, MODEL_VERSION))
    imp = pd.concat(imps, ignore_index=True) if imps else pd.DataFrame(columns=["position", "feature", "importance"])
    imp["model_version"], imp["run_at"], imp["league_id"] = MODEL_VERSION, datetime.now(UTC), ref_id
    imp["model"], imp["component"], imp["unit"] = "quantile_p50", "p50_residual", "points"   # U-15: the interval model's rows, labelled
    imp["feature_label"] = imp["feature"].map(FEATURE_LABELS)
    _write(conn, "ops.projection_importance", imp, "model_version = %s and model = 'quantile_p50'", (MODEL_VERSION,))
    out_dir = out_dir or PROJECT_ROOT / "reports" / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"projection_{MODEL_VERSION.replace('.', '_')}_{min(test_seasons)}_{max(test_seasons)}_{run_id}.md"
    path.write_text(report(res, scorings, imp))
    log.info("report written to %s", path)
    return res


def available_seasons(conn: psycopg.Connection) -> list[int]:
    with conn.cursor() as cur:
        cur.execute("select distinct season from analytics.mart_player_week_features where played order by 1")
        return [int(r[0]) for r in cur.fetchall()]


# ------------------------------------------------------------------------------ production projections
LINE_COLUMNS = ["model_version", "fitted_at", "train_seasons", "season", "week", "gsis_id", "position",
                *[f"proj_{c}" for c in ALL_COMPONENTS]]
RANGE_COLUMNS = ["scoring_name", "season", "week", "gsis_id", "position", "model_version", "fitted_at", "proj_points",
                 "p10", "p25", "p50", "p75", "p90"]
KD_LINES_TABLE_COLUMNS = ["model_version", "fitted_at", "train_seasons", "season", "week", "position", "unit_id",
                          *KD.KD_LINE_COLUMNS]
FREEZE_COLUMNS = ["frozen_at", "frozen_source"]
HOUSE_TOL = 1e-6     # a house league's price of the line vs its reference's: identical by construction (checked)


@pinned_writer   # ---- M4: the writer prices in the env's mode alone (never the record it writes)
def project(conn: psycopg.Connection, season: int | None = None) -> pd.DataFrame:
    """Fit on every completed season before ``season`` and project every week of ``season``.

    Plan F1 (Wave F): the residual ranges are fitted per *reference scoring* (``reference_scorings``) and the
    NFL-wide outputs are written: ``ops.projection_lines`` (the stat line per player-week),
    ``ops.projection_ranges`` (per reference scoring x player-week), ``ops.kd_lines`` / ``ops.kd_ranges`` (K / DEF).
    The house leagues' ``ops.projections`` rows are derived from the same numbers (the line priced in the league's
    scoring, the ranges of the reference that IS the league; a league no reference is gets fitted on its own), so
    the two never disagree. One ``fitted_at`` and one ``now`` for every table: the B5 freeze treats them alike."""
    leagues = league_scorings(conn)
    references = reference_scorings(conn)
    fit, source = fit_scorings(leagues, references)
    seasons = available_seasons(conn)
    season = season or max(seasons)
    train_seasons = [s for s in seasons if s < season]
    frame = load_frame(conn, [*train_seasons, season])
    train = frame[frame["season"] < season]
    target = frame[frame["season"] == season]
    # ---- IQ-1 (hotfix): v3.5 -- the weeks after the market week get a line from the team's own season and the market
    # week's personnel (calibration.future_inputs, LEAGUE_LAB_FUTURE_INPUTS, on); played weeks and the market week as built
    from . import calibration as _cal_iq1
    target = _cal_iq1.future_inputs(target)
    # ---- end IQ-1
    fitted_at, trained = datetime.now(UTC), f"{min(train_seasons)}-{max(train_seasons)}"
    preds, models = [], {}
    for pos in POSITIONS:
        models[pos] = m = fit_position(train, pos, fit)
        preds.append(predict_position(m, target[target["position"] == pos], fit))
    every = pd.concat(preds, ignore_index=True)     # one row per fitted scoring x player-week (league_id = the scoring key)
    every["model_version"], every["fitted_at"], every["train_seasons"] = MODEL_VERSION, fitted_at, trained
    # ---- M6 (Wave I-H): v3.2 -- the cold-start prior scales the stat line itself, before anything is priced from it
    # (LEAGUE_LAB_COLD_START; docs/METRICS.md § "v3.2"): the lines, the house rows, the ranges and every on-demand
    # price of the line are one number. Off (or nothing to scale): ``every`` unchanged.
    from . import calibration as _cal_m6
    # ---- IP-1 (Wave I-P): v3.4 -- a QB's passing TDs regressed toward his team's implied total (LEAGUE_LAB_QB_PASS_TD,
    # on; calibration.pass_td_lines), on the line before anything is priced; QB only, so it never meets the blend below
    every = _cal_m6.pass_td_lines(season, every, models, target, train, fit)
    # ---- end IP-1
    # ---- IQ-3 (Wave I-Q): v3.6 -- hb1.0, a QB's weeks after the market week blend the model's line with his own per-game
    # line, weight by the distance from the market week (LEAGUE_LAB_QB_HORIZON_BLEND, on; calibration.horizon_blend_lines);
    # on the line before anything is priced, QB only; the market week and played weeks untouched
    every = _cal_m6.horizon_blend_lines(season, every, models, target, train, fit, leagues)
    # ---- end IQ-3
    every = _cal_m6.blend_lines(conn, season, every, models, target, fit, leagues)
    # ---- /M6
    lines = nfl_lines(every)
    ranges = every[every["league_id"].isin(list(references))].rename(columns={"league_id": "scoring_name"})[RANGE_COLUMNS]
    pred = house_rows(every, leagues, source)
    # ---- M1 (Wave I-A): calibration of the top -- a no-op unless LEAGUE_LAB_PROJECTION_CALIBRATION=1
    # (docs/METRICS.md § "Calibration of the top"); the stat line is untouched, frozen weeks keep their rows (B5)
    from . import calibration as _cal
    pred, ranges = _cal.calibrate_outputs(conn, season, pred, ranges, source)
    # ---- end M1
    # R-13: K and DEF rows (model kd1.0, leagues that start them) go through the same B5 writer; F1: their
    # league-free lines and the reference scorings' offsets go NFL-wide
    kd = KD.run_after_project(conn, season, references, fitted_at)
    pred = _with_kd_rows(pred, kd.pred)
    # ---- M4 (Wave I-G): the record says how each row was priced (flat | ev; an MFL spec = ev; K / DEF: flat, kdef)
    pred["pricing"] = pred["league_id"].map({lid: record_pricing_label(sc) for lid, (_, sc) in leagues.items()})
    pred.loc[~pred["position"].isin(POSITIONS), "pricing"] = "flat"
    # ---- /M4
    now = datetime.now(UTC)
    # ---- IR-1 (Wave I-R): nobody who cannot play is projected. The live week's rows of a player who cannot play are
    # 0 with the reason (``availability``, frozen with the week); a player out indefinitely has no later weeks
    # (availability_gate; the Sleeper directory the nightly has just loaded, its date logged)
    from . import availability_gate as _ag
    gated, gate = _ag.apply_to_project(conn, season, {"pred": pred, "lines": lines, "ranges": ranges}, target, now,
                                       drop={"kd_lines": kd.lines})                 # ---- IS-1: kickers' NFL-wide lines
    pred, lines, ranges = gated["pred"], gated["lines"], gated["ranges"]
    if "kd_lines" in gated and gated["kd_lines"] is not None:                         # ---- IS-1
        kd.lines = gated["kd_lines"]
    pred.attrs["availability_gate"] = gate
    # ---- end IR-1
    _write_projections(conn, pred, season, now)   # B5: weeks whose first game has kicked off are kept, not rewritten
    # ---- IU-2 (Wave I-U): fr1.0 -- the started week's games not kicked off: the shadow (switch week, the default: nothing
    # written but logs/freeze_shadow.json) or the overlay ops.projection_live (LEAGUE_LAB_FREEZE=game). Never raises
    live = live_after_project(conn, season, pred, target, now)
    pred.attrs["live"] = {k: v for k, v in live.items() if k != "moves"} | {"moves": len(live["moves"])}
    # ---- end IU-2
    log.info("projections computed: %s rows for %s (%s leagues; ranges fitted in %s scorings: %s)", len(pred), season,
             len(leagues), len(fit), ", ".join(fit))

    def range_for(name: str, week: int, stored: pd.DataFrame) -> pd.DataFrame:
        """Ranges in ``name`` around a stored (frozen) stat line of ``week``: the week's features, tonight's models."""
        out = []
        for pos, mdl in models.items():
            rows = target[(target["position"] == pos) & (target["week"] == week)]
            ln = stored[stored["position"] == pos]
            if rows.empty or ln.empty:
                continue
            rows = rows.merge(ln[["gsis_id", *[f"proj_{c}" for c in ALL_COMPONENTS]]], on="gsis_id", how="inner")
            out.append(predict_position(mdl, rows, {name: fit[name]}, lines=rows))
        if not out:
            return pd.DataFrame(columns=RANGE_COLUMNS)
        r = pd.concat(out, ignore_index=True).rename(columns={"league_id": "scoring_name"})
        r["model_version"], r["fitted_at"] = MODEL_VERSION, fitted_at
        return r[RANGE_COLUMNS]

    # the NFL-wide tables (plan F1). A failure fails the step, after the house leagues' night has run
    nfl_error: Exception | None = None
    try:
        record = {ref: lid for lid, ref in source.items() if ref in references}   # reference -> the house league it IS
        pred.attrs["nfl_wide"] = write_nfl_wide(conn, season, lines, ranges, kd, references, record, range_for, now)
    except Exception as exc:   # noqa: BLE001 - re-raised below
        conn.rollback()
        log.exception("NFL-wide outputs failed (ops.projections was written); `league-lab project` retries them")
        nfl_error = exc
    signals_after_project(conn, season, train, target, pred, leagues)   # R-10/R-12: role alerts + scenario upside (a failure is logged, not fatal)
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
    market_record_after_project(conn, season, leagues)   # ---- M6: Sleeper's side of the record at the odds (soft)
    importance_after_project(conn, train, leagues, trained)   # U-15 (once per window; a failure is logged, not fatal)
    if nfl_error is not None:
        raise nfl_error
    return pred


def nfl_lines(every: pd.DataFrame) -> pd.DataFrame:
    """One row per player-week (``ops.projection_lines``): the stat line ``predict_position`` wrote for every
    scoring (the components are predicted once, so any scoring's copy is the line)."""
    first = every["league_id"].iloc[0] if len(every) else None
    return every[every["league_id"] == first][LINE_COLUMNS].reset_index(drop=True)


def house_rows(every: pd.DataFrame, leagues: dict[str, tuple[str, dict[str, float]]], source: dict[str, str]) -> pd.DataFrame:
    """The house leagues' ``ops.projections`` rows (QB-TE) from the fitted scorings: the stat line priced in the
    league's own scoring (``proj_points``) and the P10-P90 of the scoring it takes its ranges from (``source``:
    the reference that IS the league, else the league itself). Refuses a reference whose price of the line
    differs from the league's (they are the same priced keys: it cannot, unless the match is wrong)."""
    frames = []
    for lid, (name, scoring) in leagues.items():
        o = every[every["league_id"] == source[lid]].copy()
        own = price(o, scoring, "proj_")
        gap = float((own - o["proj_points"]).abs().max()) if len(o) else 0.0
        if gap > HOUSE_TOL:
            raise ValueError(f"{name}: priced {gap:.3g} points away from reference {source[lid]!r} (the match is wrong)")
        o["league_id"], o["proj_points"] = lid, own
        frames.append(o)
        log.info("%s (%s): ranges from %r; price of the line equal to it within %.1e; pricing %s", name, lid[-6:],
                 source[lid], gap, pricing_engine(scoring))   # M3: flat | ev (LEAGUE_LAB_EV_PRICING) | spec
    cols = ["model_version", "fitted_at", "train_seasons", "league_id", "season", "week", "gsis_id", "position",
            *[f"proj_{c}" for c in ALL_COMPONENTS], "proj_points", "p10", "p25", "p50", "p75", "p90"]
    return pd.concat(frames, ignore_index=True)[cols] if frames else pd.DataFrame(columns=cols)


def _with_kd_rows(pred: pd.DataFrame, kd: pd.DataFrame) -> pd.DataFrame:
    """R-13: the v2 rows plus the K / DEF rows of ``kdef`` (their own model_version, kd1.0), so one
    ``_write_projections`` call writes a league-week whole. No K / DEF rows (a failure, or no league
    starts them) leaves the v2 rows exactly as they were."""
    if kd.empty:
        return pred
    # one fitted_at per run: the freeze relabels a league-week with frozen_at = its fitted_at, and
    # assert_frozen_projections_precede_kickoff holds every row to it (kd stamped its own now() a few
    # seconds later, which left the QB-TE rows of a frozen week with frozen_at <> fitted_at: Mac, 2026-10-02)
    kd = kd.assign(fitted_at=pred["fitted_at"].iloc[0]) if "fitted_at" in kd and len(pred) else kd
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
        proj_points double precision, p10 double precision, p25 double precision, p50 double precision, p75 double precision,
        p90 double precision, frozen_at timestamptz, frozen_source text);
        alter table ops.projections add column if not exists frozen_at timestamptz;
        alter table ops.projections add column if not exists frozen_source text;
        alter table ops.projections add column if not exists p25 double precision;
        alter table ops.projections add column if not exists p75 double precision;
        alter table ops.projections add column if not exists pricing text;   -- M4: flat / ev (NULL = flat)
        alter table ops.projections add column if not exists availability text""",   # ---- IR-1: why a 0 (JSON)
    "ops.projection_backtest": """create table if not exists ops.projection_backtest (
        run_id text, run_at timestamptz, model_version text, train_seasons text, league_id text, season integer, week integer,
        position text, scorer text, n_players integer, spearman double precision, top_n integer, hit_rate double precision,
        mae double precision, coverage_80 double precision, pinball_10 double precision, pinball_50 double precision,
        pinball_90 double precision, interval_width double precision);
        alter table ops.projection_backtest add column if not exists coverage_50 double precision;
        alter table ops.projection_backtest add column if not exists interval_width_50 double precision;
        alter table ops.projection_backtest add column if not exists pinball_25 double precision;
        alter table ops.projection_backtest add column if not exists pinball_75 double precision;
        alter table ops.projection_backtest add column if not exists pricing text;""",   # ---- M4: flat / ev (NULL = flat)
    "ops.projection_importance": """create table if not exists ops.projection_importance (
        model_version text, run_at timestamptz, league_id text, position text, feature text, importance double precision);
        alter table ops.projection_importance add column if not exists model text;
        alter table ops.projection_importance add column if not exists component text;
        alter table ops.projection_importance add column if not exists feature_label text;
        alter table ops.projection_importance add column if not exists unit text;
        alter table ops.projection_importance add column if not exists importance_sd double precision;
        alter table ops.projection_importance add column if not exists importance_points double precision;
        alter table ops.projection_importance add column if not exists baseline_mae double precision;
        alter table ops.projection_importance add column if not exists n_rows integer;
        alter table ops.projection_importance add column if not exists train_seasons text;
        alter table ops.projection_importance add column if not exists eval_season integer;
        alter table ops.projection_importance add column if not exists fit_seasons text;
        update ops.projection_importance set model = 'quantile_p50', component = coalesce(component, 'p50_residual'),
            unit = coalesce(unit, 'points') where model is null""",
    "ops.projection_drift": """create table if not exists ops.projection_drift (
        run_at timestamptz, model_version text, league_id text, season integer, week integer, position text,
        n_players integer, spearman double precision, top_n integer, hit_rate double precision, mae double precision,
        coverage_80 double precision, interval_width double precision, games_played integer, games_scheduled integer,
        frozen_share double precision);
        alter table ops.projection_drift add column if not exists frozen_share double precision""",
}


_PROJ_DDL = ", ".join(f"proj_{c} double precision" for c in ALL_COMPONENTS)
_KD_DDL = ", ".join(f"{c} double precision" for c in KD.KD_LINE_COLUMNS)
# Plan F1 (Wave F): the NFL-wide outputs, one copy for every league (registered in db.migrate). Freeze unit (B5):
# the week for the line tables, the (scoring_name, week) for the range tables; frozen_source / frozen_at as in
# ops.projections (assert_frozen_nfl_wide_precede_kickoff).
NFL_DDL = {
    "ops.projection_lines": f"""create table if not exists ops.projection_lines (
        model_version text, fitted_at timestamptz, train_seasons text, season integer, week integer, gsis_id text,
        position text, {_PROJ_DDL}, frozen_at timestamptz, frozen_source text);
        alter table ops.projection_lines add column if not exists availability text;   -- IR-1: why a 0 (JSON)
        create index if not exists projection_lines_idx on ops.projection_lines (season, week, gsis_id)""",
    "ops.projection_ranges": """create table if not exists ops.projection_ranges (
        scoring_name text, season integer, week integer, gsis_id text, position text, model_version text,
        fitted_at timestamptz, proj_points double precision, p10 double precision, p25 double precision,
        p50 double precision, p75 double precision, p90 double precision, frozen_at timestamptz, frozen_source text);
        alter table ops.projection_ranges add column if not exists pricing text;   -- M4: flat / ev (NULL = flat)
        create index if not exists projection_ranges_idx on ops.projection_ranges (scoring_name, season, week, gsis_id)""",
    "ops.kd_lines": f"""create table if not exists ops.kd_lines (
        model_version text, fitted_at timestamptz, train_seasons text, season integer, week integer, position text,
        unit_id text, {_KD_DDL}, frozen_at timestamptz, frozen_source text);
        create index if not exists kd_lines_idx on ops.kd_lines (season, week, position, unit_id)""",
    "ops.kd_ranges": """create table if not exists ops.kd_ranges (
        scoring_name text, season integer, week integer, position text, unit_id text, model_version text,
        fitted_at timestamptz, proj_points double precision, p10 double precision, p50 double precision,
        p90 double precision, off_p10 double precision, off_p50 double precision, off_p90 double precision,
        frozen_at timestamptz, frozen_source text);
        create index if not exists kd_ranges_idx on ops.kd_ranges (scoring_name, season, week, position, unit_id)""",
    # ---- IU-2 (Wave I-U): fr1.0 -- the live overlay of the started week's games that have not kicked off (the shape of
    # ops.projections plus the game's team and kickoff); empty unless LEAGUE_LAB_FREEZE=game. Never the record: no grade
    # reads it, the freeze labels stay NULL (registered here so `league-lab db migrate` creates it)
    "ops.projection_live": f"""create table if not exists ops.projection_live (
        model_version text, fitted_at timestamptz, train_seasons text, league_id text, season integer, week integer,
        gsis_id text, position text, {_PROJ_DDL}, proj_points double precision, p10 double precision,
        p25 double precision, p50 double precision, p75 double precision, p90 double precision, pricing text,
        availability text, team text, game_kickoff timestamptz, frozen_at timestamptz, frozen_source text);
        create index if not exists projection_live_idx on ops.projection_live (league_id, season, week, gsis_id)""",
}
DDL.update(NFL_DDL)
LIVE_TABLE = "ops.projection_live"                       # ---- IU-2: not state, not the record (see live_after_project)


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
            # a kickoff row's frozen_at is its own fitted_at (the plan's value is the league-week's max, which
            # differs when two batches were stamped seconds apart); a refit row carries none
            cur.execute("""update ops.projections
                           set frozen_source = %s, frozen_at = case when %s = 'kickoff' then fitted_at end
                           where season = %s and league_id = %s and week = %s and frozen_source is null""",
                        (r.frozen_source, r.frozen_source, season, r.league_id, int(r.week)))
        # repair rows frozen by the older relabel (frozen_at = the league-week's max fitted_at): idempotent
        cur.execute("""update ops.projections set frozen_at = fitted_at
                       where season = %s and frozen_source = 'kickoff' and frozen_at is distinct from fitted_at""", (season,))
        if cur.rowcount:
            log.info("freeze labels repaired: %s kickoff rows now carry their own fitted_at", cur.rowcount)
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


# ------------------------------------------------------------------------------ IU-2 (Wave I-U): fr1.0, the live week after its first kickoff
# docs/METRICS.md § "The live week after its first kickoff": the kickoff board stays the record, kept where it is
# (freeze_plan, untouched); the started week's games that have not kicked off get tonight's number in an overlay
# (ops.projection_live) only with LEAGUE_LAB_FREEZE=game. With the default (week) the overlay stays empty and the shadow
# says who would move by SHADOW_MOVE points or more, and why (logs/freeze_shadow.json; `league-lab freeze-shadow`).
FREEZE_FLAG = "LEAGUE_LAB_FREEZE"
SHADOW_MOVE = 2.0
SHADOW_PATH = PROJECT_ROOT / "logs" / "freeze_shadow.json"
GAMES_SQL = """select week, home_team, away_team, kickoff_at from analytics.dim_game
               where season = %s and season_type = 'REG' and kickoff_at is not null"""
KD_TEAM_SQL = "select position, unit_id, team, player_name from analytics.mart_kd_week where season = %s and week = %s"
STORED_WEEK_SQL = f"""select league_id, gsis_id, position, proj_points, availability, model_version, frozen_source,
                     {', '.join(f'proj_{c}' for c in ALL_COMPONENTS)}
                     from ops.projections where season = %s and week = %s"""


def freeze_unit() -> str:
    """``LEAGUE_LAB_FREEZE``: ``game`` re-projects the started week's games that have not kicked off (the overlay);
    anything else — unset, ``week``, a typo — is ``week``: today's rule, bit for bit."""
    import os

    return "game" if os.environ.get(FREEZE_FLAG, "").strip().lower() == "game" else "week"


def started_week(games: pd.DataFrame, now: datetime) -> tuple[int | None, pd.DataFrame]:
    """(the week under way, its games not kicked off): the week whose first kickoff is at or before ``now`` and that
    still has a game kicking off after ``now``; (None, empty) between weeks. ``games``: week, home_team, away_team,
    kickoff_at. A game in progress has kicked off: it is not live."""
    empty = pd.DataFrame(columns=["team", "game_kickoff"])
    if games is None or games.empty:
        return None, empty
    g = games.assign(kickoff_at=pd.to_datetime(games["kickoff_at"], utc=True), week=games["week"].astype(int))
    t = pd.Timestamp(now)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    span = g.groupby("week")["kickoff_at"].agg(["min", "max"])
    under_way = span[(span["min"] <= t) & (span["max"] > t)]
    if under_way.empty:
        return None, empty
    week = int(under_way.index.min())
    left = g[(g["week"] == week) & (g["kickoff_at"] > t)]
    teams = pd.concat([left[["home_team", "kickoff_at"]].rename(columns={"home_team": "team"}),
                       left[["away_team", "kickoff_at"]].rename(columns={"away_team": "team"})], ignore_index=True)
    return week, teams.rename(columns={"kickoff_at": "game_kickoff"}).reset_index(drop=True)


def live_rows(pred: pd.DataFrame, week: int, teams: pd.DataFrame, player_team: pd.DataFrame,
              statuses: dict[str, dict]) -> pd.DataFrame:
    """Tonight's rows (``pred``, every league) of ``week`` for the players whose team's game has not kicked off
    (``teams``: team, game_kickoff), gated like the live week (``availability_gate.gate_frame``: who sits is 0 with the
    reason). ``player_team``: position, gsis_id, team (the week's team; K / DEF by their unit id)."""
    from . import availability_gate as _ag

    if pred is None or pred.empty or teams.empty:
        return pd.DataFrame(columns=[*pred.columns, "team", "game_kickoff"]) if pred is not None else pd.DataFrame()
    rows = pred[pred["week"].astype(int) == int(week)].copy()
    pt = player_team.dropna(subset=["gsis_id", "team"]).drop_duplicates(["position", "gsis_id"])
    rows = rows.merge(pt[["position", "gsis_id", "team"]], on=["position", "gsis_id"], how="inner")
    rows = rows.merge(teams, on="team", how="inner")
    rows, _ = _ag.gate_frame(rows, statuses, int(week))
    rows["frozen_source"], rows["frozen_at"] = None, None
    return rows.reset_index(drop=True)


def shadow_moves(live: pd.DataFrame, stored: pd.DataFrame, names: dict[str, str], move: float = SHADOW_MOVE,
                 leagues: dict[str, str] | None = None) -> list[dict]:
    """The players whose number would move by ``move`` points or more if the overlay were on: tonight's gated row
    (``live``) against the kickoff board (``stored``: ops.projections of the week), per house league, with the reason —
    he sits now (the gate's why) / he is back / a teammate sits (projection v3 reads the week's report: the personnel
    inputs) / the inputs moved (the model's version named when it changed)."""
    if live is None or live.empty or stored is None or stored.empty:
        return []
    m = live.merge(stored, on=["league_id", "gsis_id", "position"], how="inner", suffixes=("", "_kickoff"))
    m["delta"] = m["proj_points"].astype(float) - m["proj_points_kickoff"].astype(float)
    sits_now = {g for g, a, b in zip(m["gsis_id"], m["availability"], m["availability_kickoff"], strict=True)
                if isinstance(a, str) and not isinstance(b, str)}
    team_of = dict(zip(m["gsis_id"], m["team"], strict=False))
    pos_of = dict(zip(m["gsis_id"], m["position"], strict=False))
    out = []
    for r in m[m["delta"].abs() >= move].sort_values(["delta", "gsis_id", "league_id"]).itertuples(index=False):
        now_a, then_a = r.availability if isinstance(r.availability, str) else None, \
            r.availability_kickoff if isinstance(r.availability_kickoff, str) else None
        if now_a and not then_a:
            why = json.loads(now_a)
            reason = f"sits: {why.get('why') or why.get('code')}"
        elif then_a and not now_a:
            reason = f"back: the kickoff board had him out ({json.loads(then_a).get('code')}); tonight's word does not"
        else:
            group = ("QB",) if r.position == "QB" else ("RB", "WR", "TE") if r.position in ("RB", "WR", "TE") else ()
            mates = sorted(g for g in sits_now if g != r.gsis_id and team_of.get(g) == r.team and pos_of.get(g) in group)
            if mates:
                reason = "teammate sits: " + ", ".join(f"{names.get(g, g)} ({pos_of.get(g)})" for g in mates)
            elif r.model_version != r.model_version_kickoff:
                reason = f"the model changed since the kickoff board ({r.model_version_kickoff} -> {r.model_version})"
            else:
                reason = "the inputs moved since the kickoff board (report, market lines, depth chart / starter)"
            line = _line_moves(r._asdict())
            reason += f"; the line: {line}" if line and not reason.startswith(("sits", "back")) else ""
        out.append({"league_id": r.league_id, "league": (leagues or {}).get(r.league_id, r.league_id), "gsis_id": r.gsis_id, "name": names.get(r.gsis_id, r.gsis_id),
                    "position": r.position, "team": r.team, "kickoff_points": round(float(r.proj_points_kickoff), 2),
                    "live_points": round(float(r.proj_points), 2), "delta": round(float(r.delta), 2), "reason": reason})
    return out


def _line_moves(row: dict, top: int = 3) -> str:
    """The stat-line components that moved most between the kickoff board (``proj_<c>_kickoff``) and tonight's
    (``proj_<c>``), in their own units: "passing_yards 251.0 -> 270.4, passing_tds 1.71 -> 1.95"."""
    moved = []
    for c in ALL_COMPONENTS:
        a, b = row.get(f"proj_{c}_kickoff"), row.get(f"proj_{c}")
        if a is None or b is None or pd.isna(a) or pd.isna(b) or abs(float(b) - float(a)) < 0.01:
            continue
        moved.append((abs(float(b) - float(a)) / max(abs(float(a)), 1.0), c, float(a), float(b)))
    return ", ".join(f"{c} {a:.2f} -> {b:.2f}" for _, c, a, b in sorted(moved, reverse=True)[:top])


def live_after_project(conn: psycopg.Connection, season: int, pred: pd.DataFrame, target: pd.DataFrame,
                       now: datetime | None = None) -> dict:
    """``project``'s fr1.0 step, after the B5 writer (which it never touches): the started week's rows of the games
    not kicked off, gated with that week's word; the shadow (who would move, why) to ``SHADOW_PATH``; with
    ``LEAGUE_LAB_FREEZE=game`` the overlay rewritten (the rows of the games not kicked off; a game that kicked off since
    keeps its rows until the week is over), else emptied. Never raises: a failure is logged and the night goes on
    (with ``week`` nothing a reader sees depends on this step)."""
    import time

    from . import availability_gate as _ag

    t0, mode = time.perf_counter(), freeze_unit()
    now = now or datetime.now(UTC)
    summary: dict = {"mode": mode, "season": int(season), "week": None, "games_left": 0, "players_live": 0,
                     "moves": [], "move_threshold": SHADOW_MOVE, "written": 0, "computed_at": now.isoformat()}
    try:
        with conn.cursor() as cur:
            cur.execute(GAMES_SQL, (season,))
            games = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        week, teams = started_week(games, now)
        summary["week"], summary["games_left"] = week, int(len(teams) // 2)
        live = pd.DataFrame()
        if week is not None:
            tw = target[target["week"].astype(int) == week] if target is not None and not target.empty else pd.DataFrame()
            pt = tw[["position", "gsis_id", "team"]] if not tw.empty else pd.DataFrame(columns=["position", "gsis_id", "team"])
            names = dict(zip(tw["gsis_id"], tw["player_name"], strict=False)) if "player_name" in tw else {}
            with conn.cursor() as cur:
                cur.execute(KD_TEAM_SQL, (season, week))
                kt = pd.DataFrame(cur.fetchall(), columns=["position", "gsis_id", "team", "player_name"])
                names.update({g: n for g, n in zip(kt["gsis_id"], kt["player_name"], strict=False) if isinstance(n, str)})
                cur.execute(STORED_WEEK_SQL, (season, week))
                stored = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
            rs = dict(zip(tw["gsis_id"], tw["roster_status"], strict=False)) if "roster_status" in tw else {}
            raw, meta = _ag.stored(conn, season, week, rs)
            statuses = {g: s for g, s in ((g, _ag.classify(e)) for g, e in raw.items()) if _ag.sits(s)}
            live = live_rows(pred, week, teams, pd.concat([pt, kt[["position", "gsis_id", "team"]]], ignore_index=True), statuses)
            summary["players_live"] = int(live["gsis_id"].nunique()) if not live.empty else 0
            summary["gate_source"], summary["gate_copy"] = meta.get("source"), meta.get("fetched_at")
            with conn.cursor() as cur:
                cur.execute("select distinct on (league_id) league_id, league_name from analytics.dim_league_season "
                            "order by league_id, season desc")
                leagues = {str(a): b for a, b in cur.fetchall() if isinstance(b, str)}
            summary["moves"] = shadow_moves(live, stored, names, leagues=leagues)
        conn.commit()   # the reads above leave no transaction open
        if mode == "game":
            summary["written"] = _write_live(conn, season, live, now)
        else:
            _clear_live(conn)
    except Exception:  # noqa: BLE001 - the shadow / overlay never costs the night its projections
        conn.rollback()
        log.exception("fr1.0: the live-week step failed (the kickoff board and tonight's projections are written)")
        summary["error"] = "failed; see the log"
    summary["seconds"] = round(time.perf_counter() - t0, 2)
    try:
        SHADOW_PATH.parent.mkdir(parents=True, exist_ok=True)
        SHADOW_PATH.write_text(json.dumps(summary, indent=1, default=str))
    except OSError:
        log.warning("fr1.0: could not write %s", SHADOW_PATH)
    log.info("fr1.0 (%s): week %s under way, %s games not kicked off, %s players re-projected; %s house-league rows would "
             "move by %s points or more%s (%.1f s)", mode, summary["week"] or "none", summary["games_left"],
             summary["players_live"], len(summary["moves"]), SHADOW_MOVE,
             f"; overlay rows written: {summary['written']}" if mode == "game" else "; overlay off (LEAGUE_LAB_FREEZE=week)",
             summary["seconds"])
    return summary


def _clear_live(conn: psycopg.Connection) -> None:
    """With the switch ``week`` the overlay is empty: delete what an earlier ``game`` run left (none: nothing done)."""
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s) is not null", (LIVE_TABLE,))
        if cur.fetchone()[0]:
            cur.execute(f"select exists (select 1 from {LIVE_TABLE})")
            if cur.fetchone()[0]:
                cur.execute(f"delete from {LIVE_TABLE}")
                log.info("fr1.0: switch is week: %s emptied (%s rows an earlier game run left)", LIVE_TABLE, cur.rowcount)
    conn.commit()


def _write_live(conn: psycopg.Connection, season: int, live: pd.DataFrame, now: datetime) -> int:
    """The overlay (``LEAGUE_LAB_FREEZE=game``), in one transaction: rows of another week or season go, the rows of the
    games that have not kicked off are replaced by ``live``; a game that kicked off since the last run keeps its rows."""
    week = int(live["week"].iloc[0]) if live is not None and not live.empty else None
    with conn.cursor() as cur:
        cur.execute(NFL_DDL[LIVE_TABLE])
        if week is None:
            cur.execute(f"delete from {LIVE_TABLE}")
            conn.commit()
            return 0
        cur.execute(f"delete from {LIVE_TABLE} where season <> %s or week <> %s or game_kickoff > %s", (season, week, now))
    _write(conn, LIVE_TABLE, live, "season = %s and week = %s and game_kickoff > %s", (season, week, now))
    return int(len(live))


# ------------------------------------------------------------------------------ plan F1: the NFL-wide tables under the same freeze
WEEK_SCOPE = "nfl"     # the freeze unit of the line tables is the whole week (freeze_plan's league_id column)


def _kickoffs(cur: psycopg.Cursor, season: int) -> dict[int, datetime]:
    cur.execute("select week, min(kickoff_at) from analytics.dim_game where season = %s group by week", (season,))
    return {int(wk): k for wk, k in cur.fetchall() if k is not None}


def _none_for_missing(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Object columns with None for a missing value (pandas turns a missing timestamp into NaT, which COPY cannot write)."""
    df = df.copy()
    for c in cols:
        if c in df:
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def _nfl_plan(cur: psycopg.Cursor, table: str, scope: str | None, new: pd.DataFrame, season: int,
              kickoffs: dict[int, datetime], now: datetime) -> pd.DataFrame:
    """``freeze_plan`` for one NFL-wide table (its ``league_id`` column = ``scope``'s value, or ``WEEK_SCOPE`` when the
    freeze unit is the week), then the same relabel and repair ``_write_projections`` runs on ops.projections."""
    sc = scope or f"'{WEEK_SCOPE}'"
    cur.execute(f"""select {sc} as league_id, week, max(fitted_at) as fitted_at, max(frozen_source) as frozen_source,
                           max(frozen_at) as frozen_at from {table} where season = %s group by 1, 2""", (season,))
    stored = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    keys = pd.DataFrame({"league_id": new[scope] if scope else WEEK_SCOPE, "week": new["week"].astype(int)})
    plan = freeze_plan(keys, stored, kickoffs, now)
    for r in plan[plan["relabel"]].itertuples(index=False):
        cur.execute(f"""update {table} set frozen_source = %s, frozen_at = case when %s = 'kickoff' then fitted_at end
                        where season = %s and week = %s and frozen_source is null""" + (f" and {scope} = %s" if scope else ""),
                    (r.frozen_source, r.frozen_source, season, int(r.week), *([r.league_id] if scope else [])))
    cur.execute(f"""update {table} set frozen_at = fitted_at
                    where season = %s and frozen_source = 'kickoff' and frozen_at is distinct from fitted_at""", (season,))
    return plan


def _replace(conn: psycopg.Connection, table: str, rows: pd.DataFrame, columns: list[str], plan: pd.DataFrame,
             scope: str | None, season: int) -> None:
    """Delete the plan's write / delete units, copy ``rows`` (commits the relabel with them, like ``_write_projections``)."""
    rep = plan[plan["action"].isin(["write", "delete"])]
    rows = _none_for_missing(rows.reindex(columns=[*columns, *FREEZE_COLUMNS]), ["fitted_at", *FREEZE_COLUMNS])
    if scope:
        _write(conn, table, rows, f"season = %s and ({scope}, week) in (select * from unnest(%s::text[], %s::int[]))",
               (season, rep["league_id"].tolist(), [int(w) for w in rep["week"]]))
    else:
        _write(conn, table, rows, "season = %s and week = any(%s)", (season, sorted({int(w) for w in rep["week"]})))


def _weeks(plan: pd.DataFrame, action: str, source: str | None = "any") -> list[int]:
    m = plan["action"] == action
    if source != "any":
        m &= plan["frozen_source"].isna() if source is None else plan["frozen_source"].eq(source)
    return sorted({int(w) for w in plan.loc[m, "week"]})


def _lines_from_record(cur: psycopg.Cursor, season: int, weeks: list[int]) -> pd.DataFrame:
    """A started week's QB-TE stat lines as ``ops.projections`` holds them (the decision record, with its labels): the
    first house league's rows of the week (reference league first). Used when ``ops.projection_lines`` has nothing
    for a started week (its first run, or rows deleted by hand) so the lines agree with the record."""
    if not weeks:
        return pd.DataFrame(columns=[*LINE_COLUMNS, *FREEZE_COLUMNS])
    cur.execute(f"""select p.league_id, {', '.join('p.' + c for c in [*LINE_COLUMNS, *FREEZE_COLUMNS])}
                    from ops.projections as p
                    left join analytics.dim_league_season as d on d.league_id = p.league_id and d.is_current_season
                    where p.season = %s and p.week = any(%s) and p.position = any(%s)
                    order by p.week, coalesce(d.is_reference_league, false) desc, p.league_id, p.gsis_id""",
                (season, weeks, list(POSITIONS)))
    df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    if df.empty:
        return pd.DataFrame(columns=[*LINE_COLUMNS, *FREEZE_COLUMNS])
    first = df.groupby("week")["league_id"].transform("first")
    return df[df["league_id"] == first].drop(columns="league_id").reset_index(drop=True)


def _ranges_from_record(cur: psycopg.Cursor, season: int, league_id: str, week: int) -> pd.DataFrame:
    cur.execute("""select season, week, gsis_id, position, model_version, fitted_at, proj_points, p10, p25, p50, p75, p90,
                          frozen_at, frozen_source, pricing
                   from ops.projections where season = %s and league_id = %s and week = %s and position = any(%s)""",
                (season, league_id, int(week), list(POSITIONS)))
    return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def _stored(cur: psycopg.Cursor, table: str, season: int, weeks: list[int]) -> pd.DataFrame:
    cur.execute(f"select * from {table} where season = %s and week = any(%s)", (season, weeks))
    return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def write_nfl_wide(conn: psycopg.Connection, season: int, lines: pd.DataFrame, ranges: pd.DataFrame, kd: KD.KDRun,
                   references: dict[str, tuple[str, dict[str, float]]], record: dict[str, str],
                   range_for: Callable[[str, int, pd.DataFrame], pd.DataFrame], now: datetime | None = None) -> dict:
    """Write the NFL-wide tables (plan F1) under the B5 freeze, each like ``_write_projections``: a unit (the week, or
    the scoring x week for the ranges) is rewritten until the week's first kickoff and never after; the first refit
    after kickoff labels it ``kickoff`` (frozen_at = its fitted_at) or ``refit``.

    A started unit with nothing stored (the first run of these tables, a reference scoring added mid-season) is
    filled so the tables agree with each other and with the record: the QB-TE lines from ``ops.projections``' rows
    of the week (labels kept); a reference that IS a house league (``record``: name -> league_id) takes that
    league's ``ops.projections`` ranges; any other reference is ranged around the stored line by tonight's models
    (``range_for``), labelled ``refit``. K / DEF: the record holds priced points only, so a started week's K / DEF
    line with nothing stored is tonight's, labelled ``refit``; ``ops.kd_ranges`` is always the stored line priced
    in the scoring plus its offsets (``kdef.ranges_from_lines``). Returns a summary per table."""
    now = now or datetime.now(UTC)
    summary: dict[str, dict] = {}
    with conn.cursor() as cur:
        for ddl in NFL_DDL.values():
            cur.execute(ddl)
        kickoffs = _kickoffs(cur, season)
        # 1. the QB-TE stat lines
        plan = _nfl_plan(cur, "ops.projection_lines", None, lines, season, kickoffs, now)
        live, refit = _weeks(plan, "write", None), _weeks(plan, "write", "refit")
        seeded = _lines_from_record(cur, season, refit)
    rest = sorted(set(refit) - {int(w) for w in seeded["week"]})
    rows = pd.concat([lines[lines["week"].isin(live)].assign(frozen_source=None, frozen_at=None), seeded,
                      lines[lines["week"].isin(rest)].assign(frozen_source="refit", frozen_at=None)], ignore_index=True)
    _replace(conn, "ops.projection_lines", rows, [*LINE_COLUMNS, "availability"], plan, None, season)   # ---- IR-1
    summary["ops.projection_lines"] = {"rows_written": len(rows), "live": live, "from_record": sorted({int(w) for w in seeded["week"]}),
                                       "refit": rest, "kept": _weeks(plan, "keep")}
    # 2. the ranges per reference scoring
    with conn.cursor() as cur:
        plan = _nfl_plan(cur, "ops.projection_ranges", "scoring_name", ranges, season, kickoffs, now)
        w = plan[plan["action"] == "write"]
        live_units = w.loc[w["frozen_source"].isna(), ["league_id", "week"]].rename(columns={"league_id": "scoring_name"})
        parts = [ranges.merge(live_units, on=["scoring_name", "week"]).assign(frozen_source=None, frozen_at=None)]
        from_record, around_stored = [], []
        stored_lines: dict[int, pd.DataFrame] = {}
        for r in w[w["frozen_source"].eq("refit")].itertuples(index=False):
            lid = record.get(r.league_id)
            rec = _ranges_from_record(cur, season, lid, int(r.week)) if lid else pd.DataFrame()
            if len(rec):
                parts.append(rec.assign(scoring_name=r.league_id))
                from_record.append((r.league_id, int(r.week)))
                continue
            if int(r.week) not in stored_lines:
                stored_lines[int(r.week)] = _stored(cur, "ops.projection_lines", season, [int(r.week)])
            parts.append(range_for(r.league_id, int(r.week), stored_lines[int(r.week)]).assign(frozen_source="refit", frozen_at=None))
            around_stored.append((r.league_id, int(r.week)))
    rows = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else pd.DataFrame(columns=RANGE_COLUMNS)
    # ---- M4 (Wave I-G): tonight's rows say how tonight priced them; a unit taken from the record keeps its label
    labels = {name: record_pricing_label(sc) for name, (_, sc) in references.items()}
    rows = rows.assign(pricing=rows["pricing"] if "pricing" in rows else None)
    rows["pricing"] = rows["pricing"].where(rows["pricing"].notna(), rows["scoring_name"].map(labels))
    _replace(conn, "ops.projection_ranges", rows, [*RANGE_COLUMNS, "pricing"], plan, "scoring_name", season)
    # ---- /M4
    summary["ops.projection_ranges"] = {"rows_written": len(rows), "live_units": len(live_units), "from_record": from_record,
                                        "refit_around_stored_line": around_stored, "kept_units": int((plan["action"] == "keep").sum())}
    # 3. K / DEF
    if kd.lines.empty:
        log.warning("no K / DEF lines this run: ops.kd_lines / ops.kd_ranges keep their rows")
    else:
        kdl = kd.lines.reindex(columns=KD_LINES_TABLE_COLUMNS)
        with conn.cursor() as cur:
            plan = _nfl_plan(cur, "ops.kd_lines", None, kdl, season, kickoffs, now)
            w = plan[plan["action"] == "write"]
        rows = kdl.merge(w[["week", "frozen_source", "frozen_at"]], on="week")
        _replace(conn, "ops.kd_lines", rows, KD_LINES_TABLE_COLUMNS, plan, None, season)
        summary["ops.kd_lines"] = {"rows_written": len(rows), "live": _weeks(plan, "write", None),
                                   "refit": _weeks(plan, "write", "refit"), "kept": _weeks(plan, "keep")}
        fitted_at = kdl["fitted_at"].iloc[0]
        new = KD.ranges_from_lines(kdl, references, kd.offsets)
        with conn.cursor() as cur:
            plan = _nfl_plan(cur, "ops.kd_ranges", "scoring_name", new, season, kickoffs, now)
            w = plan[plan["action"] == "write"].rename(columns={"league_id": "scoring_name"})
            stored = _stored(cur, "ops.kd_lines", season, sorted({int(x) for x in w["week"]}))
        rows = KD.ranges_from_lines(stored, references, kd.offsets) if len(stored) else new.iloc[0:0]
        rows = rows.merge(w[["scoring_name", "week", "frozen_source", "frozen_at"]], on=["scoring_name", "week"])
        rows["model_version"], rows["fitted_at"] = KD.KD_MODEL_VERSION, fitted_at
        _replace(conn, "ops.kd_ranges", rows, KD.KD_RANGE_COLUMNS, plan, "scoring_name", season)
        summary["ops.kd_ranges"] = {"rows_written": len(rows), "kept_units": int((plan["action"] == "keep").sum())}
    log.info("NFL-wide outputs for %s: %s", season, summary)
    return summary


# ------------------------------------------------------------------------------ report
def summarize(res: pd.DataFrame) -> pd.DataFrame:
    return res.groupby(["league_id", "position", "scorer"]).agg(
        weeks=("week", "count"), spearman=("spearman", "mean"), hit_rate=("hit_rate", "mean"), mae=("mae", "mean"),
        coverage_80=("coverage_80", "mean"), interval_width=("interval_width", "mean"),
    ).reset_index()


def report(res: pd.DataFrame, scorings: dict[str, tuple[str, dict[str, float]]], imp: pd.DataFrame) -> str:
    lines = [f"# Projection backtest ({MODEL_VERSION})",
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


# ---- M6 (Wave I-H): the record's Sleeper side at the odds (M4's proposal, docs/METRICS.md § "The record's pricing
# column"). In a week our board priced its bonuses at their odds (``pricing = 'ev'``), Sleeper's line on the record was
# still priced all or nothing by the SQL macro. ``ops.market_record`` holds Sleeper's last pre-kickoff line priced the
# way ours was (``scoring.price_projected`` with ev=True, exactly what the card's "Sleeper's projection" shows that
# week); ``mart_projection_record.sl_priced`` reads it first, the macro for every other league-week.
MARKET_RECORD_TABLE = "ops.market_record"
MARKET_RECORD_DDL = f"""create table if not exists {MARKET_RECORD_TABLE} (
    league_id text not null, season integer not null, week integer not null, sleeper_id text not null,
    position text, fetched_at timestamptz not null, sleeper_points double precision, pricing text not null,
    written_at timestamptz not null, primary key (league_id, season, week, sleeper_id, fetched_at))"""
MARKET_SNAPSHOT_SQL = """with kick as (select week, min(kickoff_at) as first_kickoff_at from analytics.dim_game
                                       where season = %(season)s and season_type = 'REG' group by week)
    select p.week, max(p.fetched_at) as fetched_at from raw.sleeper_projections as p join kick as k using (week)
    where p.season = %(season)s and p.season_type = 'regular' and p.fetched_at < k.first_kickoff_at and p.week = any(%(weeks)s)
    group by p.week"""
EV_WEEKS_SQL = """select league_id, week from ops.projections where season = %s and position in ('QB', 'RB', 'WR', 'TE')
                  group by league_id, week having bool_and(pricing = 'ev')"""


def price_market(lines: pd.DataFrame, cols: list[str], scoring) -> np.ndarray:
    """Sleeper's QB-TE lines (``cols`` = the snapshot's stat columns, plus ``position``) priced at the odds in
    ``scoring`` -- ``scoring.price_projected(ev=True)``, the call ``why.market_points`` makes for an 'ev' week."""
    stats = lines[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    stats["position"] = lines["position"].to_numpy()
    return np.asarray(price_projected(stats.reset_index(drop=True), scoring, ev=True), dtype=float)


def market_record(conn: psycopg.Connection, season: int, leagues: dict[str, tuple[str, dict[str, float]]]) -> int:
    """Rewrite ``ops.market_record`` for ``season``: every house league-week labelled 'ev' in ``ops.projections``, Sleeper's
    last snapshot fetched before the week's first kickoff (the mart's rule), QB-TE lines priced at the odds in the
    league's scoring. A K / DEF / flat week has no row (the macro prices it, as before). Returns the rows written."""
    from .ingest import sleeper_projections as SP

    with conn.cursor() as cur:
        cur.execute(MARKET_RECORD_DDL)
        cur.execute(EV_WEEKS_SQL, (season,))
        ev = [(str(lid), int(wk)) for lid, wk in cur.fetchall() if str(lid) in leagues]
        cur.execute(f"delete from {MARKET_RECORD_TABLE} where season = %s", (season,))
        if not ev or conn.execute("select to_regclass('raw.sleeper_projections')").fetchone()[0] is None:
            conn.commit()
            return 0
        cur.execute(MARKET_SNAPSHOT_SQL, {"season": season, "weeks": sorted({w for _, w in ev})})
        snaps = {int(w): f for w, f in cur.fetchall()}
        cols = list(SP.LINE_COLUMNS)
        written, now, out = 0, datetime.now(UTC), []
        for week, fetched in sorted(snaps.items()):
            cur.execute(f"""select player_id, position, {', '.join(cols)} from raw.sleeper_projections
                            where season = %s and season_type = 'regular' and week = %s and fetched_at = %s
                              and position in ('QB', 'RB', 'WR', 'TE') and player_id ~ '^[0-9]+$'""", (season, week, fetched))
            df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
            if df.empty:
                continue
            for lid, wk in ev:
                if wk != week:
                    continue
                pts = price_market(df, cols, leagues[lid][1])
                out += [(lid, season, week, str(pid), pos, fetched, float(p), "ev", now)
                        for pid, pos, p in zip(df["player_id"], df["position"], pts, strict=True)]
        if out:
            with cur.copy(f"""copy {MARKET_RECORD_TABLE} (league_id, season, week, sleeper_id, position, fetched_at,
                              sleeper_points, pricing, written_at) from stdin""") as cp:
                for rec in out:
                    cp.write_row(rec)
            written = len(out)
    conn.commit()
    log.info("%s: %s rows (%s EV league-weeks with a pre-kickoff snapshot)", MARKET_RECORD_TABLE, written,
             sum(1 for _, w in ev if w in snaps))
    return written


def market_record_after_project(conn: psycopg.Connection, season: int,
                                leagues: dict[str, tuple[str, dict[str, float]]]) -> int | None:
    """``project``'s soft step: a failure is logged (the record's Sleeper side falls back to the macro), never fatal."""
    try:
        return market_record(conn, season, leagues)
    except Exception:  # noqa: BLE001 - the record's comparator, not the board
        conn.rollback()
        log.exception("%s failed (projections were written); the record prices Sleeper's line with the macro",
                      MARKET_RECORD_TABLE)
        return None
# ---- /M6
