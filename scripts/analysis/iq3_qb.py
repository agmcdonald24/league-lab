"""IQ-3 (Wave I-Q): the quarterback model reads the quarterback -- baselines, the ceiling and the candidates on the 1-week
QB board and on the horizon study (docs/METRICS.md § "v3.6: the quarterback model reads the quarterback (IQ-3)").
Read only on the database.

* ``cache``: per season S = 2017..2025 the production QB component models fitted on 2016..S-1 (``fit_position``'s
  training filter and inputs) applied to (1) every QB row of S as the mart has it -- the 1-week board -- and, for
  S >= 2018, (2) the horizon rows as of W = 3, 5, 7, 9 (``iq1_horizon.future_rows`` with v3.5's later-week inputs:
  the team's own line, the market week's personnel). One parquet of inputs, outcomes and the component lines.
* ``baselines``: B0 = v3.5 (the component lines; pt1.0's passing TDs where the week has a real line, a and b fitted on
  the 3 seasons before); B1 = a naive player baseline (his points per game this season and last, shrunk by games
  toward the starters' mean -- the per-game stat line priced in the scoring; the two weights fitted on the 3 seasons
  before); B1r = B1 with the prior of his listed role (the starters' mean for a listed starter, the others' for the
  rest); B2 = B1r with the opponent and the implied total where there is one (least squares on the 3 seasons before).
  The ceiling: an oracle that knew each QB's season mean of the scoring (with and without the week itself).
* ``candidates``: the candidates the keep rule (written before) judges.

Scored as the harness does: per league x season x week the MAE and Spearman over played QB rows with the 12 outcomes
known (weeks with >= 8 such players), the season the mean of its weeks, both house scorings; the horizon study per
season x W x target week x horizon (``iq1_horizon.score``), pooled over horizons 2-8.

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/iq3_qb.py cache --out q.parquet
       OMP_NUM_THREADS=1 uv run python scripts/analysis/iq3_qb.py baselines --cache q.parquet
       OMP_NUM_THREADS=1 uv run python scripts/analysis/iq3_qb.py candidates --cache q.parquet
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402

from league_lab import calibration as C  # noqa: E402
from league_lab import experiments as E  # noqa: E402
from league_lab import projections as P  # noqa: E402
from league_lab.config import get_settings  # noqa: E402
from league_lab.rankings import _spearman  # noqa: E402

_spec = importlib.util.spec_from_file_location("iq1_horizon", Path(__file__).with_name("iq1_horizon.py"))
H = importlib.util.module_from_spec(_spec)
sys.modules["iq1_horizon"] = H
_spec.loader.exec_module(H)

log = logging.getLogger("iq3")
TESTS = (2021, 2022, 2023, 2024, 2025)
FIRST_CACHE = 2017            # board rows from 2017: the 3 seasons of fitting rows before 2021 start at 2018
FIRST_HORIZON = 2018
WINDOW = 3                    # every fitted weight reads the 3 seasons before the scored one (as pt1.0 does)
COMPS = list(P.ALL_COMPONENTS)
KEEP = ["gsis_id", "player_name", "season", "week", "team", "opponent", "position", "played", "no_history", "f_home",
        "games_to_date", "prev_games", "ppg_std", "prev_ppg", "pn_qb_starting", "implied_team_total", "total_line",
        "spread_line", "f_opp_allowed_diff", "opp_allowed_std", "league_allowed_avg", "opp_games",
        *[f"{c}_pg_std" for c in COMPS], *[f"prev_{c}_pg" for c in COMPS], *[f"out_{c}" for c in COMPS]]


# ------------------------------------------------------------------------------ the cache
def cache(out: Path) -> None:
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        frame = H.load(conn, [s for s in P.available_seasons(conn) if s <= max(TESTS)])
    frame["season"] = frame["season"].astype(int)
    qb = frame[frame["position"] == "QB"]
    parts = []
    for s in range(FIRST_CACHE, max(TESTS) + 1):
        t0 = time.monotonic()
        models, feats = H.fit(frame, s, "QB")
        board = qb[qb["season"] == s].reset_index(drop=True)
        x = board[feats].to_numpy(dtype=float)      # NaN stays NaN (the whole season's batch: as the nightly)
        b = board[KEEP].copy()
        for c in COMPS:
            b[f"m_{c}"] = np.clip(models[c].predict(x), 0, None) if c in models else 0.0
        b = b.assign(kind="board", as_of=np.nan, h=np.nan, target_week=board["week"].astype(float), implied_imputed=False)
        parts.append(b)
        if s >= FIRST_HORIZON:
            for w in H.AS_OF:
                rows = H.future_rows(qb, s, w)
                rows = rows[rows["position"] == "QB"].reset_index(drop=True)
                rows = H.market_personnel(H.impute_lines(rows, H.team_lines_asof(frame, s, w)))   # v3.5 = "ad"
                x = rows[feats].to_numpy(dtype=float)
                r = rows[KEEP].copy()
                for c in COMPS:
                    r[f"m_{c}"] = np.clip(models[c].predict(x), 0, None) if c in models else 0.0
                r = r.assign(kind="horizon", as_of=float(w), h=rows["h"].astype(float), target_week=rows["target_week"].astype(float),
                             implied_imputed=rows["h"].to_numpy() > 1)
                parts.append(r)
        log.info("cache %s: %.0f s", s, time.monotonic() - t0)
    d = pd.concat(parts, ignore_index=True)
    d.to_parquet(out)
    log.info("cache: %s rows -> %s", len(d), out)


# ------------------------------------------------------------------------------ pricing helpers
def price_cols(d: pd.DataFrame, cols: dict[str, str], scoring: dict[str, float]) -> np.ndarray:
    """Price a stat line whose component c sits in column ``cols[c]`` (projection pricing)."""
    line = pd.DataFrame({f"proj_{c}": pd.to_numeric(d[cols[c]], errors="coerce").fillna(0.0).to_numpy(dtype=float) for c in COMPS})
    line["position"] = d["position"].to_numpy()
    return P.price(line, scoring, "proj_").to_numpy(dtype=float)


def actual(d: pd.DataFrame, scoring: dict[str, float]) -> np.ndarray:
    ok = d[[f"out_{c}" for c in COMPS]].notna().all(axis=1).to_numpy()
    a = np.full(len(d), np.nan)
    if ok.any():
        a[ok] = P.price(d[ok].fillna({f"out_{c}": 0.0 for c in COMPS}), scoring, "out_").to_numpy(dtype=float)
    return a


def scored(d: pd.DataFrame) -> np.ndarray:
    """The rows the board scores: played, the 12 outcomes known."""
    return (d["played"].fillna(False).astype(bool) & d[[f"out_{c}" for c in COMPS]].notna().all(axis=1)).to_numpy()


# ------------------------------------------------------------------------------ B0: v3.5 (pt1.0 on the component lines)
def pt_fits(d: pd.DataFrame) -> dict[int, tuple[float, float, int]]:
    """Per S: pt1.0's (a, b) from the board rows of the 3 seasons before (the walk-forward lines: what
    ``calibration.pass_td_fit_rows`` builds inside ``project``)."""
    b = d[d["kind"] == "board"]
    out = {}
    for s in sorted(d["season"].unique()):
        f = b[(b["season"] >= s - WINDOW) & (b["season"] < s)]
        if f["season"].nunique() < WINDOW:
            continue
        rows = pd.DataFrame({"played": f["played"].to_numpy(), "implied_team_total": f["implied_team_total"].to_numpy(dtype=float),
                             "proj_passing_tds": f["m_passing_tds"].to_numpy(), "proj_attempts": f["m_attempts"].to_numpy(),
                             "out_passing_tds": f["out_passing_tds"].to_numpy(dtype=float)})
        out[int(s)] = C.fit_pass_td(rows)
    return out


def b0_lines(d: pd.DataFrame, fits: dict[int, tuple[float, float, int]]) -> pd.DataFrame:
    """``v_<c>``: v3.5's stat line (the model's; pt1.0's passing TDs where there is a real line)."""
    out = d.copy()
    for c in COMPS:
        out[f"v_{c}"] = out[f"m_{c}"]
    for s, (a, b, _) in fits.items():
        sel = (out["season"] == s).to_numpy()
        ln = pd.DataFrame({"proj_passing_tds": out.loc[sel, "m_passing_tds"].to_numpy(), "proj_attempts": out.loc[sel, "m_attempts"].to_numpy(),
                           "implied_team_total": np.where(out.loc[sel, "implied_imputed"].to_numpy(dtype=bool), np.nan,
                                                          out.loc[sel, "implied_team_total"].to_numpy(dtype=float))})
        out.loc[sel, "v_passing_tds"] = C.apply_pass_td(ln, a, b)
    return out


# ------------------------------------------------------------------------------ B1 / B1r / B2
LAMBDAS = (0.25, 0.5, 0.75, 1.0)        # a last-season game's weight against a game this season
KS = (1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0)   # the prior's weight, in games


def naive_parts(d: pd.DataFrame, scoring: dict[str, float]) -> pd.DataFrame:
    """Per row: this season's and last season's points per game (priced per-game lines), their games, the listed role."""
    std = price_cols(d, {c: f"{c}_pg_std" for c in COMPS}, scoring)
    prev = price_cols(d, {c: f"prev_{c}_pg" for c in COMPS}, scoring)
    g = d["games_to_date"].fillna(0).to_numpy(dtype=float)
    gp = d["prev_games"].fillna(0).to_numpy(dtype=float)
    return pd.DataFrame({"std": np.where(g > 0, std, 0.0), "g": g, "prev": np.where(gp > 0, prev, 0.0), "gp": gp,
                         "starter": d["pn_qb_starting"].fillna(0).to_numpy(dtype=float) > 0.5})


def shrunk(p: pd.DataFrame, prior: np.ndarray, lam: float, k: float) -> np.ndarray:
    return (p["g"] * p["std"] + lam * p["gp"] * p["prev"] + k * prior) / (p["g"] + lam * p["gp"] + k)


def fit_naive(p: pd.DataFrame, y: np.ndarray, prior: np.ndarray) -> tuple[float, float]:
    best = None
    for lam in LAMBDAS:
        for k in KS:
            e = float(np.nanmean(np.abs(shrunk(p, prior, lam, k) - y)))
            if best is None or e < best[0]:
                best = (e, lam, k)
    return best[1], best[2]


def b2_design(d: pd.DataFrame, b1r: np.ndarray, lg_imp: float) -> np.ndarray:
    real = ~d["implied_imputed"].to_numpy(dtype=bool) & d["implied_team_total"].notna().to_numpy()
    imp = np.where(real, d["implied_team_total"].to_numpy(dtype=float) - lg_imp, 0.0)
    opp = d["f_opp_allowed_diff"].fillna(0).to_numpy(dtype=float)
    return np.column_stack([np.ones(len(d)), b1r, imp, opp])


def baselines_frame(d: pd.DataFrame, leagues: dict) -> pd.DataFrame:
    """One row per league x cache row: actual, B0, B1, B1r, B2 and the oracles (board rows), weights walk-forward."""
    fits = pt_fits(d)
    d = b0_lines(d, fits)
    out = []
    for lid, (_, sc) in leagues.items():
        y = actual(d, sc)
        ok = scored(d)
        p = naive_parts(d, sc)
        r = d[["gsis_id", "player_name", "season", "week", "kind", "as_of", "h", "target_week", "played", "pn_qb_starting",
               "implied_imputed"]].copy()
        r["league_id"], r["actual"], r["ok"] = lid, y, ok
        r["B0"] = price_cols(d, {c: f"v_{c}" for c in COMPS}, sc)
        r["M"] = price_cols(d, {c: f"m_{c}" for c in COMPS}, sc)        # the model without pt1.0
        for col in ("B1", "B1r", "B2"):
            r[col] = np.nan
        board = (d["kind"] == "board").to_numpy()
        for s in TESTS:
            fit_sel = board & ok & (d["season"] >= s - WINDOW).to_numpy() & (d["season"] < s).to_numpy()
            st_mean = float(np.mean(y[fit_sel & p["starter"].to_numpy()]))
            ot_mean = float(np.mean(y[fit_sel & ~p["starter"].to_numpy()]))
            pr_all = np.full(len(d), st_mean)
            pr_role = np.where(p["starter"], st_mean, ot_mean)
            lam1, k1 = fit_naive(p[fit_sel], y[fit_sel], pr_all[fit_sel])
            lam2, k2 = fit_naive(p[fit_sel], y[fit_sel], pr_role[fit_sel])
            b1r_fit = shrunk(p[fit_sel], pr_role[fit_sel], lam2, k2).to_numpy()
            lg_imp = float(np.nanmean(d.loc[fit_sel, "implied_team_total"]))
            x = b2_design(d[fit_sel], b1r_fit, lg_imp)
            coef, *_ = np.linalg.lstsq(x, y[fit_sel], rcond=None)
            sel = (d["season"] == s).to_numpy()
            r.loc[sel, "B1"] = shrunk(p[sel], pr_all[sel], lam1, k1).to_numpy()
            b1r = shrunk(p[sel], pr_role[sel], lam2, k2).to_numpy()
            r.loc[sel, "B1r"] = b1r
            r.loc[sel, "B2"] = b2_design(d[sel], b1r, lg_imp) @ coef
            log.info("%s %s: starters' mean %.2f, others' %.2f; B1 lambda %.2f k %.0f; B1r lambda %.2f k %.0f; B2 %s",
                     lid[-6:], s, st_mean, ot_mean, lam1, k1, lam2, k2, np.round(coef, 3))
        # the oracles (board rows only): his season mean of the scoring over the scored rows, with and without the week
        bd = r[board & ok]
        grp = bd.groupby(["gsis_id", "season"])["actual"]
        tot, n = grp.transform("sum"), grp.transform("count")
        r.loc[bd.index, "O_in"] = tot / n
        r.loc[bd.index, "O_loo"] = np.where(n > 1, (tot - bd["actual"]) / (n - 1).clip(lower=1), np.nan)
        # ... and his season mean in the same listed role (starter / not), leaving the week out
        role = bd["pn_qb_starting"].fillna(0).gt(0.5)
        grp = bd.assign(role=role).groupby(["gsis_id", "season", "role"])["actual"]
        tot, n = grp.transform("sum"), grp.transform("count")
        r.loc[bd.index, "O_role"] = np.where(n > 1, (tot - bd["actual"]) / (n - 1).clip(lower=1), np.nan)
        # the horizon rows read the oracle of the target week's own board row
        o = r.loc[bd.index, ["gsis_id", "season", "week", "O_in", "O_loo", "O_role"]]
        hz = r.index[~board]
        m = r.loc[hz, ["gsis_id", "season", "week"]].merge(o, on=["gsis_id", "season", "week"], how="left")
        for c in ("O_in", "O_loo", "O_role"):
            r.loc[hz, c] = m[c].to_numpy()
        out.append(r)
    return pd.concat(out, ignore_index=True)


# ------------------------------------------------------------------------------ scoring
def board_weekly(r: pd.DataFrame, col: str) -> pd.DataFrame:
    """Per league x season x week (board rows, scored, >= 8 players): MAE and Spearman of ``col``."""
    d = r[(r["kind"] == "board") & r["ok"] & r["season"].isin(TESTS) & r[col].notna()]
    rows = []
    for (lid, s, w), g in d.groupby(["league_id", "season", "week"]):
        if len(g) < 8:
            continue
        rows.append({"league_id": lid, "season": s, "week": w, "mae": float((g[col] - g["actual"]).abs().mean()),
                     "spearman": _spearman(g[col], g["actual"])})
    return pd.DataFrame(rows)


def board_seasons(r: pd.DataFrame, col: str, league: str | None = None) -> pd.DataFrame:
    w = board_weekly(r, col)
    if league is not None:
        w = w[w["league_id"] == league]
    return w.groupby(["league_id", "season"])[["mae", "spearman"]].mean().groupby("season").mean()


def horizon_cells(r: pd.DataFrame, col: str) -> pd.DataFrame:
    d = r[(r["kind"] == "horizon") & r["ok"] & r["season"].isin(TESTS) & r[col].notna()]
    rows = []
    for (lid, s, w, t, h), g in d.groupby(["league_id", "season", "as_of", "target_week", "h"]):
        if len(g) < 8:
            continue
        rows.append({"league_id": lid, "season": s, "as_of": w, "target_week": t, "h": h,
                     "mae": float((g[col] - g["actual"]).abs().mean()), "spearman": _spearman(g[col], g["actual"])})
    return pd.DataFrame(rows)


def horizon_seasons(r: pd.DataFrame, col: str, hs: tuple[int, int] = (2, 8), league: str | None = None) -> pd.DataFrame:
    """Pooled horizons ``hs`` by season: cells averaged per league x season x h, then over h, then over the leagues
    (iq1_horizon.report's pooling)."""
    c = horizon_cells(r, col)
    if league is not None:
        c = c[c["league_id"] == league]
    c = c[(c["h"] >= hs[0]) & (c["h"] <= hs[1])]
    m = c.groupby(["league_id", "season", "h"])[["mae", "spearman"]].mean().reset_index()
    return m.groupby(["league_id", "season"])[["mae", "spearman"]].mean().groupby("season").mean()


def by_h(r: pd.DataFrame, col: str) -> pd.DataFrame:
    c = horizon_cells(r, col)
    return c.groupby(["league_id", "season", "h"])[["mae", "spearman"]].mean().groupby(["season", "h"]).mean().groupby("h").mean()


def table(cols: dict[str, pd.DataFrame]) -> str:
    seasons = sorted(next(iter(cols.values())).index)
    head = "| season | " + " | ".join(f"{k} MAE | {k} ρ" for k in cols) + " |"
    lines = [head, "|---|" + "---|---|" * len(cols)]
    for s in [*seasons, "mean"]:
        cells = []
        for t in cols.values():
            v = t.mean() if s == "mean" else t.loc[s]
            cells.append(f"{v['mae']:.3f} | {v['spearman']:.3f}")
        lines.append(f"| {s} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def run_baselines(cache_path: Path, out: Path | None) -> pd.DataFrame:
    d = pd.read_parquet(cache_path)
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        leagues = P.league_scorings(conn)
    r = baselines_frame(d, leagues)
    if out is not None:
        r.to_parquet(out)
    ref = next(iter(leagues))
    cols = ["B0", "M", "B1", "B1r", "B2"]
    print("\n### 1-week QB board, both house scorings (season = mean of its weeks, leagues averaged)\n")
    print(table({c: board_seasons(r, c) for c in cols}))
    print("\n### 1-week QB board, reference league (Half PPR) only\n")
    print(table({c: board_seasons(r, c, ref) for c in cols}))
    print("\n### Horizon study, pooled 2-8 weeks ahead, both house scorings\n")
    print(table({c: horizon_seasons(r, c) for c in cols}))
    print("\n### Horizon study, pooled 2-8, reference league only\n")
    print(table({c: horizon_seasons(r, c, league=ref) for c in cols}))
    print("\n### Horizon study by horizon (seasons averaged, both scorings)\n")
    t = pd.concat({c: by_h(r, c) for c in cols}, axis=1)
    print(t.round(3).to_string())
    print("\n### The ceiling: 1-week board, an oracle that knew each QB's season mean (both scorings)\n")
    print(table({"B0": board_seasons(r, "B0"), "oracle (with the week)": board_seasons(r, "O_in"),
                 "oracle (leave the week out)": board_seasons(r, "O_loo")}))
    # the oracle on the same rows as B0 (the loo oracle has no value for a one-game season)
    loo = r[r["O_role"].notna()]
    print("\nsame rows as the role oracle (his season mean in the week's listed role, the week left out):\n")
    print(table({"B0": board_seasons(loo, "B0"), "oracle (role, week out)": board_seasons(loo, "O_role"),
                 "oracle (with the week)": board_seasons(loo, "O_in")}))
    print("\nhorizon pooled 2-8, same rows:\n")
    print(table({"B0": horizon_seasons(loo, "B0"), "B2": horizon_seasons(loo, "B2"), "oracle (role, week out)": horizon_seasons(loo, "O_role"),
                 "oracle (with the week)": horizon_seasons(loo, "O_in")}))
    st = r[r["pn_qb_starting"].fillna(0).gt(0.5)]
    print("\n### Listed starters only (information: the order inside the starters' band), 1 week\n")
    print(table({c: board_seasons(st, c) for c in ("B0", "B1r", "B2")} | {"oracle (role)": board_seasons(st[st["O_role"].notna()], "O_role")}))
    print("\nlisted starters only, horizon pooled 2-8:\n")
    print(table({c: horizon_seasons(st, c) for c in ("B0", "B1r", "B2")}))
    return r


# ------------------------------------------------------------------------------ the candidates (rule: METRICS § v3.6)
W_GRID = tuple(round(0.05 * i, 2) for i in range(21))
PE_KS = (1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0)
PE_LAST = 0.5          # a last-season game's weight in the player effect
H_CAP = 8              # a week further out than the study takes the 8-week weight


def horizon_of(d: pd.DataFrame) -> np.ndarray:
    """1 for the 1-week board's rows (each week is its own market week), the study's h for the horizon rows."""
    return np.where(d["kind"].to_numpy() == "board", 1, np.minimum(d["h"].fillna(1).to_numpy(), H_CAP)).astype(int)


def naive_lines(d: pd.DataFrame, leagues: dict) -> pd.DataFrame:
    """``n_<c>``: B1r per component (his per-game line this season and last, shrunk toward his listed role's mean line by
    games); per S the role means, lambda and k from the scored board rows of the 3 seasons before (lambda and k by the
    MAE of the priced line, summed over the house scorings)."""
    out = d.copy()
    ok = scored(d)
    board = (d["kind"] == "board").to_numpy()
    starter = d["pn_qb_starting"].fillna(0).to_numpy(dtype=float) > 0.5
    g = d["games_to_date"].fillna(0).to_numpy(dtype=float)
    gp = d["prev_games"].fillna(0).to_numpy(dtype=float)
    parts = {lid: naive_parts(d, sc) for lid, (_, sc) in leagues.items()}
    ys = {lid: actual(d, sc) for lid, (_, sc) in leagues.items()}
    for c in COMPS:
        out[f"n_{c}"] = np.nan
    out["naive_lambda"], out["naive_k"] = np.nan, np.nan
    for s in sorted(d["season"].unique()):
        if s - 1 < FIRST_CACHE:
            continue
        # the 3 seasons before (fewer for 2018-2019, the first seasons after the cache's first: still walk-forward)
        fit_sel = board & ok & (d["season"] >= max(FIRST_CACHE, s - WINDOW)).to_numpy() & (d["season"] < s).to_numpy()
        prior = {c: (float(d.loc[fit_sel & starter, f"out_{c}"].mean()), float(d.loc[fit_sel & ~starter, f"out_{c}"].mean())) for c in COMPS}
        pr_pts = {lid: (float(np.mean(ys[lid][fit_sel & starter])), float(np.mean(ys[lid][fit_sel & ~starter]))) for lid in leagues}
        best = None
        for lam in LAMBDAS:
            for k in KS:
                e = 0.0
                for lid in leagues:
                    pp = parts[lid][fit_sel]
                    pr = np.where(pp["starter"], *pr_pts[lid])
                    e += float(np.mean(np.abs(shrunk(pp, pr, lam, k) - ys[lid][fit_sel])))
                if best is None or e < best[0]:
                    best = (e, lam, k)
        _, lam, k = best
        sel = (d["season"] == s).to_numpy()
        for c in COMPS:
            this = d.loc[sel, f"{c}_pg_std"].fillna(0).to_numpy(dtype=float)
            last = d.loc[sel, f"prev_{c}_pg"].fillna(0).to_numpy(dtype=float)
            pr = np.where(starter[sel], *prior[c])
            out.loc[sel, f"n_{c}"] = (g[sel] * this + lam * gp[sel] * last + k * pr) / (g[sel] + lam * gp[sel] + k)
        out.loc[sel, "naive_lambda"], out.loc[sel, "naive_k"] = lam, k
    return out


def residual_history(d: pd.DataFrame, line: str, leagues: dict) -> pd.DataFrame:
    """Per row: the sums of his residuals (actual - ``<line>_<c>``, and in points per house scoring) and their weight
    over his scored board rows of this season before the row's market week and of last season (weight ``PE_LAST``)."""
    ok = scored(d)
    b = d[(d["kind"] == "board").to_numpy() & ok].copy()
    cols = [f"r_{c}" for c in COMPS]
    for c in COMPS:
        b[f"r_{c}"] = b[f"out_{c}"].to_numpy(dtype=float) - b[f"{line}_{c}"].to_numpy(dtype=float)
    for lid, (_, sc) in leagues.items():
        b[f"rp_{lid}"] = actual(b, sc) - price_cols(b, {c: f"{line}_{c}" for c in COMPS}, sc)
        cols.append(f"rp_{lid}")
    b["one"] = 1.0
    cols.append("one")
    b["season"], b["week"] = b["season"].astype(int), b["week"].astype(int)
    per = b.groupby(["gsis_id", "season", "week"])[cols].sum()
    weeks = list(range(1, 24))
    cum = {}
    for c in cols:
        w = per[c].unstack("week").reindex(columns=weeks).fillna(0.0).cumsum(axis=1).shift(1, axis=1).fillna(0.0)
        cum[c] = w.stack()
    cum = pd.DataFrame(cum)
    cum.index.names = ["gsis_id", "season", "week"]
    tot = b.groupby(["gsis_id", "season"])[cols].sum()
    # the market week the row was projected in: its own week (board) or W + 1 (horizon)
    mw = np.where(d["kind"].to_numpy() == "board", d["week"].to_numpy(dtype=float), d["as_of"].to_numpy(dtype=float) + 1).astype(int)
    idx = pd.MultiIndex.from_arrays([d["gsis_id"].to_numpy(), d["season"].astype(int).to_numpy(), mw])
    this = cum.reindex(idx).fillna(0.0).to_numpy()
    last = tot.reindex(pd.MultiIndex.from_arrays([d["gsis_id"].to_numpy(), d["season"].astype(int).to_numpy() - 1])).fillna(0.0).to_numpy()
    return pd.DataFrame(this + PE_LAST * last, columns=cols, index=d.index)


def player_effect(d: pd.DataFrame, line: str, leagues: dict, out_prefix: str) -> pd.DataFrame:
    """pe1.0: ``<out_prefix>_<c>`` = max(0, ``<line>_<c>`` + residual sum / (weight + k)); k per S from the scored board rows
    of the 3 seasons before (the points residual, MAE summed over the house scorings)."""
    out = d.copy()
    hist = residual_history(d, line, leagues)
    ok = scored(d)
    board = (d["kind"] == "board").to_numpy()
    base_pts = {lid: price_cols(d, {c: f"{line}_{c}" for c in COMPS}, sc) for lid, (_, sc) in leagues.items()}
    ys = {lid: actual(d, sc) for lid, (_, sc) in leagues.items()}
    n = hist["one"].to_numpy()
    out["pe_k"] = np.nan
    for c in COMPS:
        out[f"{out_prefix}_{c}"] = out[f"{line}_{c}"]
    for s in range(FIRST_HORIZON, max(TESTS) + 1):
        fit_sel = board & ok & (d["season"] >= max(FIRST_CACHE, s - WINDOW)).to_numpy() & (d["season"] < s).to_numpy()
        best = None
        for k in PE_KS:
            e = sum(float(np.mean(np.abs(base_pts[lid][fit_sel] + hist[f"rp_{lid}"].to_numpy()[fit_sel] / (n[fit_sel] + k)
                                         - ys[lid][fit_sel]))) for lid in leagues)
            if best is None or e < best[0]:
                best = (e, k)
        k = best[1]
        sel = (d["season"] == s).to_numpy()
        for c in COMPS:
            out.loc[sel, f"{out_prefix}_{c}"] = np.clip(d.loc[sel, f"{line}_{c}"].to_numpy(dtype=float)
                                                       + hist.loc[sel, f"r_{c}"].to_numpy() / (n[sel] + k), 0, None)
        out.loc[sel, "pe_k"] = k
        log.info("pe1.0 %s (%s): k %.0f", s, line, k)
    return out


def horizon_blend(d: pd.DataFrame, line: str, leagues: dict, out_prefix: str, market_week: bool) -> pd.DataFrame:
    """hb1.0 / hb1.1: ``<out_prefix>_<c>`` = (1 - w_h) ``<line>_<c>`` + w_h ``n_<c>``; w_h per S and horizon from the scored
    rows of the 3 seasons before (h >= 2: the horizon rows; h = 1, hb1.1 only: the board rows), grid 0-1 by 0.05, the
    MAE of the priced line summed over the house scorings. hb1.0 leaves h = 1 (the board, the market week) as it is."""
    out = d.copy()
    ok = scored(d)
    h = horizon_of(d)
    board = (d["kind"] == "board").to_numpy()
    lp = {lid: price_cols(d, {c: f"{line}_{c}" for c in COMPS}, sc) for lid, (_, sc) in leagues.items()}
    npx = {lid: price_cols(d, {c: f"n_{c}" for c in COMPS}, sc) for lid, (_, sc) in leagues.items()}
    ys = {lid: actual(d, sc) for lid, (_, sc) in leagues.items()}
    for c in COMPS:
        out[f"{out_prefix}_{c}"] = out[f"{line}_{c}"]
    weights = {}
    for s in TESTS:
        ws = {}
        for hh in range(1 if market_week else 2, H_CAP + 1):
            src = board if hh == 1 else (~board & (h == hh))
            fit_sel = src & ok & (d["season"] >= s - WINDOW).to_numpy() & (d["season"] < s).to_numpy()
            best = None
            for w in W_GRID:
                e = sum(float(np.mean(np.abs((1 - w) * lp[lid][fit_sel] + w * npx[lid][fit_sel] - ys[lid][fit_sel]))) for lid in leagues)
                if best is None or e < best[0]:
                    best = (e, w)
            ws[hh] = best[1]
        weights[s] = ws
        for hh, w in ws.items():
            sel = (d["season"] == s).to_numpy() & (h == hh)
            if hh == 1:
                sel &= board | (d["h"].fillna(0).to_numpy() == 1)
            for c in COMPS:
                out.loc[sel, f"{out_prefix}_{c}"] = (1 - w) * d.loc[sel, f"{line}_{c}"].to_numpy(dtype=float) + w * d.loc[sel, f"n_{c}"].to_numpy(dtype=float)
        log.info("%s %s weights by horizon: %s", out_prefix, s, ws)
    out.attrs[f"{out_prefix}_weights"] = weights
    return out


def judge(r: pd.DataFrame, cand: str, base: str = "B0") -> dict:
    """The rule's clauses 1, 2 and 4 (clause 3, the ranges, is ``ranges``)."""
    res = {}
    bb, bc = board_seasons(r, base), board_seasons(r, cand)
    changed = int((r.loc[r["kind"] == "board", cand] - r.loc[r["kind"] == "board", base]).abs().gt(1e-9).sum())
    dm, ds = bc["mae"] - bb["mae"], bc["spearman"] - bb["spearman"]
    per = pd.DataFrame({"position": "QB", "season": bb.index, "delta_mae": dm.to_numpy(), "delta_spearman": ds.to_numpy()})
    dec = E.decide(per).iloc[0]
    c1 = changed == 0 or (int((dm < 0).sum()) >= 4 and ds.mean() > 0 and not dec["hurts"])
    hb, hc = horizon_seasons(r, base), horizon_seasons(r, cand)
    hm, hs = hc["mae"] - hb["mae"], hc["spearman"] - hb["spearman"]
    c2 = int((hm < 0).sum()) >= 4 and hs.mean() > 0
    res.update({"cand": cand, "board_cells_changed": changed, "board_dmae": dm, "board_dsp": ds, "decide": dec["decision"],
                "decide_hurts": bool(dec["hurts"]), "c1": bool(c1), "hz_dmae": hm, "hz_dsp": hs, "c2": bool(c2),
                "board": bc, "hz": hc})
    return res


def print_judgement(j: dict) -> None:
    print(f"\n### {j['cand']}\n")
    print("| season | 1 wk MAE | Δ | ρ | Δ | 2–8 MAE | Δ | ρ | Δ |\n|---|---|---|---|---|---|---|---|---|")
    for s in j["board"].index:
        print(f"| {s} | {j['board'].loc[s, 'mae']:.3f} | {j['board_dmae'].loc[s]:+.3f} | {j['board'].loc[s, 'spearman']:.3f} | "
              f"{j['board_dsp'].loc[s]:+.4f} | {j['hz'].loc[s, 'mae']:.3f} | {j['hz_dmae'].loc[s]:+.3f} | "
              f"{j['hz'].loc[s, 'spearman']:.3f} | {j['hz_dsp'].loc[s]:+.4f} |")
    print(f"| mean | {j['board']['mae'].mean():.3f} | {j['board_dmae'].mean():+.3f} | {j['board']['spearman'].mean():.3f} | "
          f"{j['board_dsp'].mean():+.4f} | {j['hz']['mae'].mean():.3f} | {j['hz_dmae'].mean():+.3f} | {j['hz']['spearman'].mean():.3f} | "
          f"{j['hz_dsp'].mean():+.4f} |")
    print(f"\n1 week: {j['board_cells_changed']} board cells changed; MAE lower in {int((j['board_dmae'] < 0).sum())} of 5, "
          f"Spearman higher in {int((j['board_dsp'] > 0).sum())} of 5; decide: {j['decide']} (hurts {j['decide_hurts']}) "
          f"-> clause 1 {'passes' if j['c1'] else 'fails'}")
    print(f"2-8 weeks: MAE lower in {int((j['hz_dmae'] < 0).sum())} of 5, Spearman higher in {int((j['hz_dsp'] > 0).sum())} of 5, "
          f"mean Δ Spearman {j['hz_dsp'].mean():+.4f} -> clause 2 {'passes' if j['c2'] else 'fails'}")


def run_candidates(cache_path: Path, out: Path | None) -> None:
    d = pd.read_parquet(cache_path)
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        leagues = P.league_scorings(conn)
    d = b0_lines(d, pt_fits(d))
    d = naive_lines(d, leagues)
    d = player_effect(d, "v", leagues, "pe")          # the residual history reads the 2017 rows too
    d = d[d["season"] >= FIRST_HORIZON].reset_index(drop=True)      # rows with a naive line and a player effect (2018 on)
    d = horizon_blend(d, "v", leagues, "hb0", market_week=False)
    d = horizon_blend(d, "v", leagues, "hb1", market_week=True)
    d = horizon_blend(d, "pe", leagues, "pehb", market_week=False)
    names = {"hb0": "hb1.0", "hb1": "hb1.1", "pe": "pe1.0", "pehb": "pe1.0 + hb1.0"}
    parts = []
    for lid, (_, sc) in leagues.items():
        r = d[["gsis_id", "player_name", "season", "week", "kind", "as_of", "h", "target_week", "played", "pn_qb_starting"]].copy()
        r["league_id"], r["actual"], r["ok"] = lid, actual(d, sc), scored(d)
        r["B0"] = price_cols(d, {c: f"v_{c}" for c in COMPS}, sc)
        for k, name in names.items():
            r[name] = price_cols(d, {c: f"{k}_{c}" for c in COMPS}, sc)
        parts.append(r)
    r = pd.concat(parts, ignore_index=True)
    if out is not None:
        r.to_parquet(out)
        d[["gsis_id", "season", "week", "kind", "as_of", "h", *[f"{k}_{c}" for k in ("v", "n", *names) for c in COMPS]]].to_parquet(
            out.with_name(out.stem + "_lines.parquet"))
    print("\n### B0 (v3.5) on these rows\n")
    print(table({"B0 1 wk": board_seasons(r, "B0"), "B0 2-8": horizon_seasons(r, "B0")}))
    verdicts = {}
    for name in names.values():
        j = judge(r, name)
        print_judgement(j)
        verdicts[name] = j
    print("\n### By horizon (seasons averaged, both scorings)\n")
    print(pd.concat({c: by_h(r, c) for c in ["B0", *names.values()]}, axis=1).round(3).to_string())
    print("\n### Listed starters only, 2-8 weeks (information)\n")
    st = r[r["pn_qb_starting"].fillna(0).gt(0.5)]
    print(table({c: horizon_seasons(st, c) for c in ["B0", *names.values()]}))
    print("\nverdicts (clauses 1 and 2; 3 = ranges, 4 = QB only):", {k: (v["c1"], v["c2"]) for k, v in verdicts.items()})


# ------------------------------------------------------------------------------ clause 3: the ranges, production path
def run_ranges(lines_path: Path, cand: str = "hb0") -> None:
    """Per S: ``fit_position`` (QB, the house scorings) on 2016..S-1; v3.5's 1-week line (the model's, pt1.0 where there
    is a real line) ranged by ``predict_position(..., lines=)``; the horizon rows (v3.5's inputs) ranged around B0's line
    and around the candidate's (``<cand>_<c>`` from the candidates' lines parquet). Coverage of the 80 % and 50 % ranges
    against the components' price, per league x season x week (>= 8), the season the mean of its weeks."""
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        frame = H.load(conn, [s for s in P.available_seasons(conn) if s <= max(TESTS)])
        leagues = P.league_scorings(conn)
    frame["season"] = frame["season"].astype(int)
    lines = pd.read_parquet(lines_path)
    qb = frame[frame["position"] == "QB"]
    keys = ["gsis_id", "season", "week"]
    out = []
    for s in TESTS:
        t0 = time.monotonic()
        m = P.fit_position(frame[frame["season"] < s], "QB", leagues)
        board = qb[qb["season"] == s].reset_index(drop=True)
        ln = lines[(lines["kind"] == "board") & (lines["season"] == s)]
        bl = board[keys].assign(season=board["season"].astype(int), week=board["week"].astype(int)).merge(
            ln.assign(week=ln["week"].astype(int)), on=keys, how="left")
        sets = [("1 week", "B0", board, bl.rename(columns={f"v_{c}": f"proj_{c}" for c in COMPS}))]
        for w in H.AS_OF:
            rows = H.future_rows(qb, s, w)
            rows = rows[(rows["position"] == "QB") & (rows["h"] > 1)].reset_index(drop=True)
            rows = H.market_personnel(H.impute_lines(rows, H.team_lines_asof(frame, s, w))).assign(as_of=w)
            lh = lines[(lines["kind"] == "horizon") & (lines["season"] == s) & (lines["as_of"] == w) & (lines["h"] > 1)]
            hl = rows[["gsis_id", "h"]].merge(lh, on=["gsis_id", "h"], how="left", validate="one_to_one")
            for name, pre in (("B0", "v"), (cand, cand)):
                sets.append(("2-8 weeks", name, rows.assign(week=rows["target_week"]),
                             hl.rename(columns={f"{pre}_{c}": f"proj_{c}" for c in COMPS})))
        for horizon, name, rows, ln_ in sets:
            assert ln_["proj_passing_yards"].notna().all(), (s, horizon, name)
            pr = P.predict_position(m, rows, leagues, lines=ln_)
            ok = scored(rows)
            for lid, (_, sc) in leagues.items():
                o = pr[pr["league_id"] == lid].reset_index(drop=True)
                o["actual"] = np.where(ok, actual(rows, sc), np.nan)
                o = o[ok]
                o["week"] = rows.loc[ok, "week"].astype(int).to_numpy() if horizon == "1 week" else (
                    rows.loc[ok, "as_of"].astype(int).to_numpy() * 100 + rows.loc[ok, "target_week"].astype(int).to_numpy()) \
                    if "as_of" in rows else o["week"]
                sc_ = E.score_v31(o.assign(position="QB"))
                sc_["horizon"], sc_["variant"] = horizon, name
                out.append(sc_)
        log.info("ranges %s: %.0f s", s, time.monotonic() - t0)
    res = pd.concat(out, ignore_index=True)
    g = res.groupby(["horizon", "variant", "league_id", "season"])[["coverage_80", "coverage_50", "mae"]].mean().reset_index()
    print("\n### QB ranges, production path (coverage of the 80 % and 50 % ranges, season = mean of its weeks)\n")
    print(g.pivot_table(index=["horizon", "variant", "league_id"], columns="season", values="coverage_80").round(3).to_string())
    print("\nmeans over 2021-2025:\n")
    print(g.groupby(["horizon", "variant", "league_id"])[["coverage_80", "coverage_50", "mae"]].mean().round(3).to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["cache", "baselines", "candidates", "ranges"])
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.mode == "cache":
        cache(args.out)
    elif args.mode == "baselines":
        run_baselines(args.cache, args.out)
    elif args.mode == "ranges":
        run_ranges(args.cache)
    else:
        run_candidates(args.cache, args.out)


if __name__ == "__main__":
    main()
