"""JB-1 (Wave J-B): gp1.0's first-fix candidates (docs/METRICS.md § "Where we lose to Sleeper" → "The candidates"),
behind ``LEAGUE_LAB_GP_FIX``. **C1 shipped (fx1.0, v3.8)**: unset = ``back_feature``; ``off`` = none of them (v3.6's
projection to the bit); ``back_scale`` / ``fringe_scale`` = the candidates that did not ship, kept for a later study.

* ``back_feature`` (C1): the input ``f_missed_prev`` (he did not play his team's previous game of the season, that game
  played) for RB / WR / TE.
* ``back_scale`` (C2): a back player's whole line × k_pos (RB / WR / TE), k the factor with the lowest mean absolute
  error over the back rows of the three seasons before (the model's out-of-sample rows, the anchor league's points).
* ``fringe_scale`` (C3): a line projected below the position's knot (the median over the fitting weeks of the
  36th-highest projection) × k_pos chosen the same way on the rows below the knot.

Called by ``projections.project`` (after the cold-start and new-team scales) and by ``h2h.build_ours`` (the
walk-forward, where the "three seasons before" are the rows that run computed).
"""

from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

FLAG = "LEAGUE_LAB_GP_FIX"
MODES = ("back_feature", "back_scale", "fringe_scale")
SHIPPED = "back_feature"          # fx1.0 (v3.8): gp1.0's rule shipped C1 at RB (docs/METRICS.md § "fx1.0")
OFF = ("off", "none", "0")
BACK_FEATURE = "f_missed_prev"
POSITIONS = ("RB", "WR", "TE")
K_GRID = tuple(round(0.50 + 0.01 * i, 2) for i in range(71))      # 0.50 … 1.20
MIN_ROWS = 100
FRINGE_RANK = 36
WINDOW = 3
LAST_PLAN: pd.DataFrame | None = None


def mode() -> str | None:
    """The candidate in force: the switch's value; unset = the shipped one (fx1.0); ``off`` (or anything unknown) = none."""
    m = os.environ.get(FLAG)
    if m is None or not m.strip():
        return SHIPPED
    m = m.strip().lower()
    return None if m in OFF else m if m in MODES else None


def back_flags(frame: pd.DataFrame) -> pd.Series:
    """Per row of ``frame`` (gsis_id, season, week, team, played): 1.0 when his previous row of the season says he did
    not play and that team game was played (a player of the team played it), 0.0 when he played it, NaN when unknown
    (his first row of the season, or a previous game still to come)."""
    d = frame[["gsis_id", "season", "week", "team", "played"]].copy()
    d["_i"] = np.arange(len(d))
    d = d.sort_values(["gsis_id", "season", "week"])
    g = d.groupby(["gsis_id", "season"], sort=False)
    prev_week, prev_team, prev_played = g["week"].shift(1), g["team"].shift(1), g["played"].shift(1)
    done = frame.loc[frame["played"].fillna(False).astype(bool), ["team", "season", "week"]].drop_duplicates()
    done_key = set(zip(done["team"], done["season"].astype(int), done["week"].astype(int), strict=True))
    team_done = [(t, int(s), int(w)) in done_key if pd.notna(w) else False
                 for t, s, w in zip(prev_team, d["season"], prev_week, strict=True)]
    out = np.where(prev_week.isna() | ~np.asarray(team_done), np.nan,
                   np.where(prev_played.astype(object) == False, 1.0, 0.0))  # noqa: E712
    return pd.Series(out, index=d["_i"].to_numpy()).sort_index().set_axis(frame.index)


def add_feature(frame: pd.DataFrame) -> pd.DataFrame:
    """C1: the frame with ``f_missed_prev`` when the switch says ``back_feature`` — now, or when the projection module
    was imported (its inputs list was fixed then: the column must exist whenever the list names it)."""
    import sys

    imported = getattr(sys.modules.get("league_lab.projections"), "GP_MODE", None)
    if "back_feature" not in (mode(), imported) or frame.empty:
        return frame
    frame = frame.copy()
    frame[BACK_FEATURE] = back_flags(frame).to_numpy()
    return frame


def best_k(proj: np.ndarray, actual: np.ndarray) -> float:
    """The factor in ``K_GRID`` with the lowest mean |k × proj − actual| (1.0 under ``MIN_ROWS`` rows; ties: nearest 1)."""
    if len(proj) < MIN_ROWS:
        return 1.0
    errs = [float(np.mean(np.abs(k * proj - actual))) for k in K_GRID]
    best = min(errs)
    return min((k for k, e in zip(K_GRID, errs, strict=True) if e <= best + 1e-12), key=lambda k: abs(k - 1.0))


def knot(oof: pd.DataFrame) -> float | None:
    """The median over the fitting weeks of the FRINGE_RANK-th highest projection (weeks with that many rows)."""
    vals = [g["proj_points"].nlargest(FRINGE_RANK).iloc[-1] for _, g in oof.groupby(["season", "week"])
            if len(g) >= FRINGE_RANK]
    return float(np.median(vals)) if vals else None


def plan(season: int, line: pd.DataFrame, oof: pd.DataFrame, history: pd.DataFrame, anchor_scoring: dict) -> pd.DataFrame:
    """Per target row to scale: gsis_id, week, position, k (only rows with k != 1). ``line``: the anchor scoring's
    rows (gsis_id, week, position, proj_*), ``oof``: the anchor league's out-of-sample rows (gsis_id, season, week,
    position, proj_points, actual), ``history``: a frame with the seasons before and this one (back flags)."""
    from . import projections as P

    m = mode()
    cols = ["gsis_id", "week", "position", "k"]
    if m not in ("back_scale", "fringe_scale") or line.empty or oof is None or oof.empty:
        return pd.DataFrame(columns=cols)
    oof = oof[(oof["season"] >= season - WINDOW) & (oof["season"] < season)].copy()
    tgt = line[line["position"].isin(POSITIONS)].copy()
    tgt["points"] = P.price(tgt, anchor_scoring, "proj_").to_numpy(dtype=float)
    if m == "back_scale":
        flags = history[["gsis_id", "season", "week"]].assign(back=back_flags(history).to_numpy())
        oof = oof.merge(flags, on=["gsis_id", "season", "week"], how="left")
        tgt = tgt.merge(flags[flags["season"] == season].drop(columns="season"), on=["gsis_id", "week"], how="left")
    out = []
    for pos in POSITIONS:
        f = oof[oof["position"] == pos]
        t = tgt[tgt["position"] == pos]
        if m == "back_scale":
            fit_rows, sel = f[f["back"] == 1.0], (t["back"] == 1.0).to_numpy()
            what = "back"
        else:
            kn = knot(f)
            if kn is None:
                continue
            fit_rows, sel = f[f["proj_points"] < kn], (t["points"] < kn).to_numpy()
            what = f"below {kn:.2f}"
        k = best_k(fit_rows["proj_points"].to_numpy(float), fit_rows["actual"].to_numpy(float))
        log.info("gp1.0 %s %s %s: k = %.2f on %s fitting rows; %s rows of %s", m, pos, what, k, len(fit_rows),
                 int(sel.sum()), season)
        if k != 1.0 and sel.any():
            out.append(t.loc[sel, ["gsis_id", "week", "position"]].assign(k=k))
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def apply(conn, season: int, every: pd.DataFrame, models: dict, target: pd.DataFrame, history: pd.DataFrame,
          fit: dict, leagues: dict) -> pd.DataFrame:
    """C2 / C3 on ``every`` (one row per fitted scoring × player-week): the planned rows' lines scaled and priced and
    ranged again by the same models (``predict_position(..., lines=)``, as ``blend_lines``). Switch unset or C1:
    ``every`` itself."""
    global LAST_PLAN
    if mode() not in ("back_scale", "fringe_scale") or every.empty:
        return every
    from . import calibration as cal
    from . import projections as P

    oof = cal.load_oof(conn, season)
    anchor = cal.anchor_league(oof, leagues) if oof is not None and not oof.empty else None
    if anchor is None:
        log.warning("gp1.0 %s: no out-of-sample rows of a house league before %s: lines unchanged", mode(), season)
        return every
    first = every["league_id"].iloc[0]
    line = every[every["league_id"] == first]
    pl = plan(season, line, oof[oof["league_id"].astype(str) == anchor], history, leagues[anchor][1])
    LAST_PLAN = pl
    if pl.empty:
        return every
    comps = [f"proj_{c}" for c in P.ALL_COMPONENTS]
    keys = ["gsis_id", "week"]
    new = []
    for pos, p in pl.groupby("position"):
        tgt = target[target["position"] == pos].drop_duplicates(keys)
        rows = p[keys].merge(tgt, on=keys, how="inner", validate="one_to_one")
        ln = rows[keys].merge(line[[*keys, *comps]], on=keys, how="left").merge(p[[*keys, "k"]], on=keys, how="left")
        ln[comps] = ln[comps].to_numpy(dtype=float) * ln[["k"]].to_numpy(dtype=float)
        new.append(P.predict_position(models[pos], rows, fit, lines=ln))
    moved = pd.concat(new, ignore_index=True)
    for c in ("model_version", "fitted_at", "train_seasons"):
        if c in every:
            moved[c] = every[c].iloc[0]
    hit = every.set_index(keys).index.isin(pl.set_index(keys).index)
    out = pd.concat([every[~hit], moved[every.columns]], ignore_index=True)
    out.attrs = every.attrs
    return out
