"""Feature group ``player_prior`` (plan E4, Wave E): how far the model has been off on HIM, as of the week.

Andrew: "what else could make this better". Some players beat (or miss) their projection week after week: a
receiver whose targets are worth more than the average target, a back the model keeps over-rating. v3 sees his
own rates; it does not see its own track record on him. This group gives it that: the running mean of his
out-of-fold residual against the production model - (actual points - the model's projection) over his earlier
games - exponentially weighted (half-life ``HALF_LIFE`` games), as of the week.

**Out of fold, as of the week** (the leak this has to avoid):
* the projection for a season-S game comes from a model trained only on seasons < S (``component_walk_forward``:
  exactly the walk-forward the harness and ``backtest-v2`` run - same frame order, same inputs per position
  (``projections.FEATURES_BY_POSITION``), same hyper-parameters, the same training filter as ``fit_position``),
  so it is a real forecast error, never an in-sample fit;
* the feature for (player, S, W) reads only residuals of his games with (season, week) < (S, W);
* in the harness's walk-forward for test season N, a training row (season < N) uses residuals of models trained on
  seasons before ITS season (all < N), and a test row uses residuals of season-N games predicted by the model
  trained on seasons < N - which is the baseline model of that fold. Nothing of season N's outcomes after week W
  reaches a week-W row.
Residuals start in 2017 (a 2016 game has no earlier season to train on); projections are priced in the reference
league's scoring, as the harness's outcome probe uses.

**The harness hook.** The table (``ops.player_prior_oof``) is not a dbt model: it is derived from the model's own
out-of-fold predictions, so the group registers a ``build`` callable (``experiments.get_group`` calls it before
reading the table). ``build`` refits only when the table is missing or its ``data_key`` (model version, the
inputs, the hyper-parameters, the frame's rows / played / points) differs from the current one; a refit is the
component models only (no interval models): ~10 season-folds x 4 positions.

The per-row out-of-fold projections are kept in ``ops.player_prior_oof_pred`` (both leagues' scoring): the
baseline's point projection for every played row 2017-2026, which also lets the weeks 1-4 subset of any group be
scored without refitting the baseline (``docs/STATUS.md`` § Wave E, E4).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

TABLE = "ops.player_prior_oof"
PRED_TABLE = "ops.player_prior_oof_pred"
HALF_LIFE = 8                      # games: the weight of a game halves every 8 games he plays after it
DECAY = 0.5 ** (1 / HALF_LIFE)     # per game


# ------------------------------------------------------------------------------ the rule (pure; pinned by tests)
def ewm_residual_asof(games: pd.DataFrame, rows: pd.DataFrame, decay: float = DECAY) -> pd.DataFrame:
    """As-of exponentially weighted mean of residuals.

    ``games``: one row per scored game, columns gsis_id, season, week, resid. ``rows``: the player-weeks to fill
    (gsis_id, season, week). For each row: the weighted mean of his residuals over games with (season, week) <
    (row season, row week), the newest weighing 1, the one before ``decay``, then ``decay``**2 ... (across seasons);
    ``pp_resid_games`` = how many such games; ``pp_asof_week`` = the week of the newest game used when it is in the
    row's season (NULL otherwise). No earlier game: NULL / 0 / NULL. Row order of ``rows`` is kept."""
    g = games.sort_values(["gsis_id", "season", "week"]).reset_index(drop=True)
    num = np.zeros(len(g))
    den = np.zeros(len(g))
    cnt = np.zeros(len(g), dtype=int)
    prev_id, n_, d_, c_ = None, 0.0, 0.0, 0
    for i, (pid, r) in enumerate(zip(g["gsis_id"].to_numpy(), g["resid"].to_numpy(dtype=float), strict=True)):
        if pid != prev_id:
            prev_id, n_, d_, c_ = pid, 0.0, 0.0, 0
        n_, d_, c_ = r + decay * n_, 1.0 + decay * d_, c_ + 1
        num[i], den[i], cnt[i] = n_, d_, c_
    g = g.assign(t=g["season"] * 100 + g["week"], pp_resid_ewm=num / den, pp_resid_games=cnt,
                 last_season=g["season"], last_week=g["week"])[["gsis_id", "t", "pp_resid_ewm", "pp_resid_games", "last_season", "last_week"]]
    r = rows[["gsis_id", "season", "week"]].copy()
    r["_order"] = np.arange(len(r))
    r["t"] = r["season"].astype(int) * 100 + r["week"].astype(int)
    out = pd.merge_asof(r.sort_values("t"), g.sort_values("t"), on="t", by="gsis_id", allow_exact_matches=False, direction="backward")
    out = out.sort_values("_order").reset_index(drop=True)
    out["pp_resid_games"] = out["pp_resid_games"].fillna(0).astype(int)
    same = out["last_season"] == out["season"]
    out["pp_asof_week"] = out["last_week"].where(same).astype("Int64")
    out["season"], out["week"] = out["season"].astype(int), out["week"].astype(int)
    return out[["gsis_id", "season", "week", "pp_resid_ewm", "pp_resid_games", "pp_asof_week"]]


# ------------------------------------------------------------------------------ out-of-fold projections
def component_walk_forward(frame: pd.DataFrame, seasons: list[int], scorings: dict, first: int,
                           features: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """Per test season S in ``seasons``: per position, the component models of ``projections.fit_position`` (same
    training filter, inputs and order) trained on seasons ``first``..S-1, applied to every season-S row; the
    projected line priced in each league's scoring (``proj_<league_id>``). One row per frame row of those seasons.
    Equal, row for row, to the point projection of the harness's / backtest's walk-forward (the interval models
    are not fitted: they do not move the point projection)."""
    from .. import projections as P

    out = []
    for s in seasons:
        train = frame[(frame["season"] >= first) & (frame["season"] < s)]
        test = frame[frame["season"] == s]
        if train.empty or test.empty:
            continue
        for pos in P.POSITIONS:
            feats = list((features or P.FEATURES_BY_POSITION)[pos])
            d = train[(train["position"] == pos) & train["played"] & ~train["no_history"]]
            d = d.dropna(subset=[f"out_{c}" for c in P.COMPONENTS[pos]]).reset_index(drop=True)
            models = P._fit_components(P._matrix(d, feats), d, pos)
            rows = test[test["position"] == pos]
            x = P._matrix(rows, feats)
            o = rows[["gsis_id", "season", "week", "position", "played", "no_history"]].copy()
            o["season"], o["week"] = o["season"].astype(int), o["week"].astype(int)   # week is a float feature in the frame
            comp = pd.DataFrame({f"proj_{c}": (np.clip(models[c].predict(x), 0, None) if c in models else 0.0) for c in P.ALL_COMPONENTS},
                                index=rows.index)
            for lid, (_, scoring) in scorings.items():
                o[f"proj_{lid}"] = P.price(comp, scoring, "proj_").to_numpy()
                ok = rows[[f"out_{c}" for c in P.ALL_COMPONENTS]].notna().all(axis=1) & rows["played"]
                act = pd.Series(np.nan, index=rows.index)
                if ok.any():
                    act[ok] = P.price(rows[ok], scoring, "out_").to_numpy()
                o[f"actual_{lid}"] = act.to_numpy()
            out.append(o)
            log.info("player_prior: season %s %s fitted on %s rows", s, pos, len(d))
    return pd.concat(out, ignore_index=True)


def data_key(frame: pd.DataFrame, scorings: dict) -> str:
    from .. import projections as P

    payload = json.dumps({"mv": P.MODEL_VERSION, "features_by_position": P.FEATURES_BY_POSITION, "hgb": P.HGB, "half_life": HALF_LIFE,
                          "scorings": {k: v[1] for k, v in sorted(scorings.items())}, "rows": len(frame),
                          "points": round(float(frame["points_actual"].fillna(0).sum()), 2),
                          "played": int(frame["played"].fillna(False).sum())}, sort_keys=True, default=str)
    return hashlib.md5(payload.encode()).hexdigest()[:16]


def build(conn, force: bool = False) -> bool:
    """(Re)build ``ops.player_prior_oof`` (and the per-row projections) when missing or stale. True = rebuilt."""
    from .. import projections as P

    scorings = P.league_scorings(conn)
    seasons = P.available_seasons(conn)
    frame = P.load_frame(conn, seasons)
    key = data_key(frame, scorings)
    if not force:
        with conn.cursor() as cur:
            cur.execute("select to_regclass(%s)", (TABLE,))
            if cur.fetchone()[0]:
                cur.execute(f"select max(data_key), min(data_key) from {TABLE}")   # noqa: S608 (constant)
                hi, lo = cur.fetchone()
                if hi == lo == key:
                    log.info("player_prior: %s is current (key %s)", TABLE, key)
                    conn.commit()
                    return False
        conn.commit()
    t0 = time.monotonic()
    first = min(seasons)
    pred = component_walk_forward(frame, [s for s in seasons if s > first], scorings, first)
    ref = next(iter(scorings))                     # the reference league (league_scorings orders it first)
    games = pred[pred["played"] & pred[f"actual_{ref}"].notna()].copy()
    games["resid"] = games[f"actual_{ref}"] - games[f"proj_{ref}"]
    feat = ewm_residual_asof(games[["gsis_id", "season", "week", "resid"]], frame[["gsis_id", "season", "week"]])
    feat["data_key"], feat["built_at"] = key, datetime.now(UTC)
    _write(conn, TABLE, feat, """gsis_id text not null, season integer not null, week integer not null, pp_resid_ewm double precision,
                                pp_resid_games integer, pp_asof_week integer, data_key text, built_at timestamptz""",
           ["gsis_id", "season", "week"])
    keep = ["gsis_id", "season", "week", "position", "played", "no_history", *[c for c in pred.columns if c.startswith(("proj_", "actual_"))]]
    p = pred[keep].copy()
    p["data_key"] = key
    ddl = ", ".join([
        "gsis_id text not null", "season integer not null", "week integer not null", "position text", "played boolean", "no_history boolean",
        *[f'"{c}" double precision' for c in keep if c.startswith(("proj_", "actual_"))], "data_key text"])
    _write(conn, PRED_TABLE, p, ddl, ["gsis_id", "season", "week"])
    log.info("player_prior: built %s (%s rows) and %s (%s rows) in %.0f s, key %s", TABLE, len(feat), PRED_TABLE, len(p),
             time.monotonic() - t0, key)
    return True


def _write(conn, table: str, df: pd.DataFrame, ddl: str, key: list[str]) -> None:
    from psycopg import sql

    schema, name = table.split(".")
    ident = sql.Identifier(schema, name)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("drop table if exists {}").format(ident))
        cur.execute(sql.SQL("create table {} (" + ddl + ")").format(ident))
        with cur.copy(sql.SQL("copy {} ({}) from stdin").format(ident, sql.SQL(", ").join(sql.Identifier(c) for c in df.columns))) as cp:
            for r in df.itertuples(index=False, name=None):
                cp.write_row(tuple(_py(v) for v in r))
        cur.execute(sql.SQL("create unique index on {} ({})").format(ident, sql.SQL(", ").join(sql.Identifier(c) for c in key)))
        cur.execute(sql.SQL("analyze {}").format(ident))
    conn.commit()


def _py(v):
    """A plain Python value for COPY (numpy scalars unwrapped; NaN / NA -> NULL)."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if hasattr(v, "item"):
        v = v.item()
    return None if isinstance(v, float) and np.isnan(v) else v


COLUMNS = ["pp_resid_ewm", "pp_resid_games"]

GROUPS = {
    "player_prior": {
        "table": TABLE, "columns": COLUMNS, "build": build,
        "label": "How far the model has been off on him",
        "note": "E4: his running out-of-fold residual against the production model (actual - projected points, reference "
                "scoring) over his earlier games, exponentially weighted (half-life 8 games), and how many games it has",
    },
}
