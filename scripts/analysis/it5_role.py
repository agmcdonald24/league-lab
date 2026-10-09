"""IT-5 (Wave I-T): the quarterback beyond next week -- who still starts (docs/METRICS.md § "v3.7: the role forecast
(IT-5)"; the rule was written and committed before any candidate number). Read only on the database.

* ``cache``: ``iq3_qb.py``'s cache (per season S = 2017..2025 the production QB component models fitted on 2016..S-1,
  applied to the 1-week board and to the horizon rows as of W = 3, 5, 7, 9 with v3.5's later-week inputs), with the
  extra columns the role forecast reads (all known at W: the market week's row).
* ``v36``: v3.6's own numbers on these rows (MAE and Spearman 2-8 weeks pooled, by season and by horizon) and the
  useful-decision grade ud1.0 for quarterbacks re-graded on v3.6's rows (IR-4 graded it on v3.5-era rows), beside a
  reproduction of IR-4's v3.5 number on the same decisions.
* ``study``: the candidate rf1.0 (and rf1.1), beside v3.6, "the starter always keeps the job" and the oracle that knows
  who started; the reliability table of the probability; the rule's clauses (a)-(e).

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/it5_role.py cache --out q.parquet
       OMP_NUM_THREADS=1 uv run python scripts/analysis/it5_role.py v36 --cache q.parquet
       OMP_NUM_THREADS=1 uv run python scripts/analysis/it5_role.py study --cache q.parquet
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402

from league_lab import projections as P  # noqa: E402
from league_lab.config import get_settings  # noqa: E402

_spec = importlib.util.spec_from_file_location("iq3_qb", Path(__file__).with_name("iq3_qb.py"))
Q = importlib.util.module_from_spec(_spec)
sys.modules["iq3_qb"] = Q
_spec.loader.exec_module(Q)

log = logging.getLogger("it5")
COMPS = Q.COMPS
TESTS = Q.TESTS
SCRUBS = "1389709692405551104"        # ud1.0 is graded in Half PPR (League of Scrubs)
# what the role forecast may read: the market week's row (known at W)
ROLE_COLS = ["questionable", "snap_pct_std", "pn_qb_games_together", "pn_qb_changed", "pn_qb_is_rookie_or_backup",
             "pn_qb_prev_ppg_diff"]


_spec4 = importlib.util.spec_from_file_location("ir4_useful", Path(__file__).with_name("ir4_useful.py"))
U = importlib.util.module_from_spec(_spec4)
sys.modules["ir4_useful"] = U
_spec4.loader.exec_module(U)


def cache(out: Path) -> None:
    for c in ROLE_COLS:
        if c not in Q.KEEP:
            Q.KEEP.append(c)
    Q.cache(out)


# ------------------------------------------------------------------------------ v3.6's lines on the cache (as iq3 built them)
def v36_lines(cache_path: Path) -> tuple[pd.DataFrame, dict]:
    """The cache with ``v_<c>`` (v3.5: the model, pt1.0 where the week has a real line), ``n_<c>`` (B1r per component)
    and ``hb0_<c>`` (v3.6 = hb1.0: h >= 2 blended toward n by the walk-forward weight) -- iq3_qb.run_candidates' steps."""
    d = pd.read_parquet(cache_path)
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        leagues = P.league_scorings(conn)
    d = Q.b0_lines(d, Q.pt_fits(d))
    d = Q.naive_lines(d, leagues)
    d = d[d["season"] >= Q.FIRST_HORIZON].reset_index(drop=True)
    d = Q.horizon_blend(d, "v", leagues, "hb0", market_week=False)
    return d, leagues


def priced_frame(d: pd.DataFrame, leagues: dict, lines: dict[str, str]) -> pd.DataFrame:
    """One row per league x cache row: actual, ok and each named line priced (``lines``: name -> column prefix)."""
    parts = []
    for lid, (_, sc) in leagues.items():
        r = d[["gsis_id", "player_name", "season", "week", "kind", "as_of", "h", "target_week", "played", "pn_qb_starting"]].copy()
        r["league_id"], r["actual"], r["ok"] = lid, Q.actual(d, sc), Q.scored(d)
        for name, pre in lines.items():
            r[name] = Q.price_cols(d, {c: f"{pre}_{c}" for c in COMPS}, sc)
        parts.append(r)
    return pd.concat(parts, ignore_index=True)


# ------------------------------------------------------------------------------ ud1.0 on the cache's rows
def ud_rates(d: pd.DataFrame, sc: dict[str, float], pre: str) -> pd.DataFrame:
    """ud1.0 (METRICS § "The useful decision grade"; ``ir4_useful.run``'s steps) for quarterbacks on the line ``<pre>_<c>``:
    per season x W, his projected points over W+1..W+4 (the horizon rows h 1-4), the top 24, the close pairs."""
    hz = d[(d["kind"] == "horizon") & (d["h"] <= 4)]
    board = d[d["kind"] == "board"]
    ok_b = Q.scored(board)
    pts_b = pd.Series(np.where(ok_b, Q.actual(board, sc), np.nan), index=board.index)
    res = []
    for s in TESTS:
        last = pts_b[(board["season"] == s - 1).to_numpy() & ok_b].groupby(board.loc[(board["season"] == s - 1).to_numpy() & ok_b, "gsis_id"]).mean()
        for w in U.AS_OF:
            rows = hz[(hz["season"] == s) & (hz["as_of"] == w)]
            ok = Q.scored(rows)
            proj = np.nan_to_num(Q.price_cols(rows, {c: f"{pre}_{c}" for c in COMPS}, sc), nan=0.0)
            act = np.where(ok, np.nan_to_num(Q.actual(rows, sc), nan=0.0), 0.0)
            t = pd.DataFrame({"gsis_id": rows["gsis_id"].to_numpy(), "proj": proj, "act": act, "games": 1.0})
            tot = t.groupby("gsis_id").agg(proj=("proj", "sum"), act=("act", "sum"), games=("games", "sum"))
            cs = (board["season"] == s).to_numpy() & (board["week"] <= w).to_numpy() & ok_b
            cur = pts_b[cs].groupby(board.loc[cs, "gsis_id"]).mean()
            rate = cur.reindex(tot.index).fillna(last.reindex(tot.index))
            tot["base"] = rate * tot["games"]
            top = tot.sort_values("proj", ascending=False).head(U.TOP["QB"]).reset_index()
            res.append({"season": s, "as_of": w, "position": "QB", "players": len(top), **U.pair_rates(top)})
    return pd.DataFrame(res)


def ud_summary(r: pd.DataFrame) -> pd.DataFrame:
    """Pair-weighted within a season; pooled = the mean over seasons (``ir4_useful.report``)."""
    def w(g, col, n):
        x = g[g[n] > 0]
        return float((x[col] * x[n]).sum() / x[n].sum()) if len(x) else float("nan")
    rows = [{"season": s, "pairs": int(g["pairs"].sum()), "model": w(g, "model", "pairs"), "base": w(g, "base", "pairs")}
            for s, g in r.groupby("season")]
    return pd.DataFrame(rows).set_index("season")


def run_v36(cache_path: Path) -> None:
    d, leagues = v36_lines(cache_path)
    r = priced_frame(d, leagues, {"B0": "v", "v3.6": "hb0", "M": "m"})
    print("\n### v3.6 on the horizon rows, pooled 2-8 weeks, both house scorings (season = mean of its cells)\n")
    print(Q.table({"B0 (v3.5)": Q.horizon_seasons(r, "B0"), "v3.6": Q.horizon_seasons(r, "v3.6")}))
    print("\n### v3.6 by horizon (seasons averaged, both scorings)\n")
    print(pd.concat({c: Q.by_h(r, c) for c in ("B0", "v3.6")}, axis=1).round(3).to_string())
    hz = Q.horizon_cells(r, "v3.6")
    print("\n### v3.6 by season x horizon (MAE / Spearman, both scorings)\n")
    print(hz.groupby(["league_id", "season", "h"])[["mae", "spearman"]].mean().groupby(["season", "h"]).mean()
          .unstack("h").round(3).to_string())
    print("\n### 1-week board (the market week), both scorings\n")
    print(Q.table({"B0": Q.board_seasons(r, "B0"), "v3.6": Q.board_seasons(r, "v3.6")}))
    sc = leagues[SCRUBS][1]
    for name, pre in (("M (the model alone: IR-4's v3.5-era rows)", "m"), ("v3.5 (pt1.0)", "v"), ("v3.6 (hb1.0)", "hb0")):
        u = ud_summary(ud_rates(d, sc, pre))
        print(f"\n### ud1.0, quarterbacks, {name}: calculator / his own record by season, pooled = mean over seasons\n")
        print(u.round(3).to_string())
        print(f"pooled: pairs {int(u['pairs'].sum())}, calculator {u['model'].mean():.3f}, his own record {u['base'].mean():.3f}, "
              f"seasons above both 50 % and the record: {int(((u['model'] > u['base']) & (u['model'] > 0.5)).sum())} of 5")


# ------------------------------------------------------------------------------ the role forecast (rf1.0, rf1.1)
RF_H = (2, 3, 4, 5, 6, 7, 8)


def role_frame(d: pd.DataFrame) -> pd.DataFrame:
    """Per horizon row h >= 2: who he was in the market week (``mkt_start``: the listed starter of W+1, which the later
    weeks' inputs carry) and who he was in week T (``t_start``: the target week's own listed role from its board row;
    no board row = not the starter); the inputs of the forecast (all from the market week's row)."""
    hz = d[(d["kind"] == "horizon") & (d["h"] >= 2)].copy()
    b = d[d["kind"] == "board"][["gsis_id", "season", "week", "pn_qb_starting"]].rename(
        columns={"week": "target_week", "pn_qb_starting": "t_pn"})
    b["target_week"] = b["target_week"].astype(float)
    hz["target_week"] = hz["target_week"].astype(float)
    hz = hz.reset_index().merge(b, on=["gsis_id", "season", "target_week"], how="left", validate="many_to_one").set_index("index")
    hz["mkt_start"] = hz["pn_qb_starting"].fillna(0).to_numpy(dtype=float) > 0.5
    hz["t_start"] = hz["t_pn"].fillna(0).to_numpy(dtype=float) > 0.5
    hz["played_b"] = hz["played"].fillna(False).astype(bool)
    return hz


def role_x(hz: pd.DataFrame, med: pd.Series | None = None) -> tuple[np.ndarray, pd.Series]:
    """The forecast's inputs: the horizon (one column per h), and from the market week: an injury designation, his
    snap share this season, games with this team's skill players, a changed starter, rookie / backup, his points per
    game this season and last (priced in the frame), his games this season and last."""
    cols = ["questionable", "snap_pct_std", "pn_qb_games_together", "pn_qb_changed", "pn_qb_is_rookie_or_backup",
            "pn_qb_prev_ppg_diff", "ppg_std", "prev_ppg", "games_to_date", "prev_games"]
    x = hz[cols].astype(float)
    if med is None:
        med = x.median()
    x = x.fillna(med)
    x["pn_qb_games_together"] = np.log1p(x["pn_qb_games_together"].clip(lower=0))
    hh = np.stack([(hz["h"].to_numpy() == h).astype(float) for h in RF_H], axis=1)
    return np.column_stack([hh, x.to_numpy()]), med


def fit_role(tr: pd.DataFrame):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    x, med = role_x(tr)
    y = tr["t_start"].to_numpy().astype(int)
    m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    m.fit(x, y)
    return m, med


def role_probs(hz: pd.DataFrame, conditional: bool) -> pd.Series:
    """Walk-forward: per test season S, one model per market-week role (starter / not), fitted on the horizon rows of
    2018..S-1 (every earlier season in the cache); rf1.0 on every row (unconditional), rf1.1 on the rows where he played
    in week T (the probability that he starts given that he plays)."""
    p = pd.Series(np.nan, index=hz.index)
    for s in TESTS:
        for role in (True, False):
            tr = hz[(hz["season"] < s) & (hz["mkt_start"] == role)]
            if conditional:
                tr = tr[tr["played_b"]]
            te = hz[(hz["season"] == s) & (hz["mkt_start"] == role)]
            m, med = fit_role(tr)
            p.loc[te.index] = m.predict_proba(role_x(te, med)[0])[:, 1]
    return p


def role_priors(d: pd.DataFrame) -> dict[int, dict[str, tuple[float, float]]]:
    """Per S the starters' and the others' mean outcome per component (the scored board rows of the 3 seasons before:
    the role prior ``naive_lines`` uses)."""
    ok = Q.scored(d)
    board = (d["kind"] == "board").to_numpy()
    st = d["pn_qb_starting"].fillna(0).to_numpy(dtype=float) > 0.5
    out = {}
    for s in TESTS:
        f = board & ok & (d["season"] >= s - Q.WINDOW).to_numpy() & (d["season"] < s).to_numpy()
        out[s] = {c: (float(d.loc[f & st, f"out_{c}"].mean()), float(d.loc[f & ~st, f"out_{c}"].mean())) for c in COMPS}
    return out


def mix_lines(d: pd.DataFrame, hz: pd.DataFrame, p: pd.Series, pre: str, priors: dict) -> pd.DataFrame:
    """``<pre>_<c>``: the market week's starter: p x his v3.6 line + (1 - p) x the others' mean line (a backup's line);
    the market week's non-starter: p x his starter line (B1r with the starters' prior: his per-game line this season
    and last shrunk toward the starters' mean by v3.6's lambda and k) + (1 - p) x his v3.6 line. h <= 1 and the board
    rows keep v3.6's line (the market week does not move)."""
    out = d
    for c in COMPS:
        out[f"{pre}_{c}"] = out[f"hb0_{c}"].to_numpy(dtype=float)
    idx = hz.index[p.loc[hz.index].notna().to_numpy() & hz["season"].isin(TESTS).to_numpy()]   # the scored seasons
    h = hz.loc[idx]
    pp = p.loc[idx].to_numpy(dtype=float)
    st = h["mkt_start"].to_numpy()
    g = h["games_to_date"].fillna(0).to_numpy(dtype=float)
    gp = h["prev_games"].fillna(0).to_numpy(dtype=float)
    lam = h["naive_lambda"].to_numpy(dtype=float)
    k = h["naive_k"].to_numpy(dtype=float)
    seasons = h["season"].astype(int).to_numpy()
    for c in COMPS:
        pr_st = np.array([priors[s][c][0] for s in seasons])
        pr_ot = np.array([priors[s][c][1] for s in seasons])
        line = h[f"hb0_{c}"].to_numpy(dtype=float)
        this = h[f"{c}_pg_std"].fillna(0).to_numpy(dtype=float)
        last = h[f"prev_{c}_pg"].fillna(0).to_numpy(dtype=float)
        as_starter = (g * this + lam * gp * last + k * pr_st) / (g + lam * gp + k)
        out.loc[idx, f"{pre}_{c}"] = np.where(st, pp * line + (1 - pp) * pr_ot, pp * as_starter + (1 - pp) * line)
    return out


def reliability(hz: pd.DataFrame, p: pd.Series, label: str, rows: np.ndarray) -> None:
    t = hz.loc[rows & hz["season"].isin(TESTS).to_numpy()].assign(p=p)
    t = t[t["p"].notna()]
    for role, name in ((True, "the market week's starter still starts"), (False, "a market-week non-starter starts")):
        x = t[t["mkt_start"] == role]
        if x.empty:
            continue
        x = x.assign(dec=pd.qcut(x["p"].rank(method="first"), 10, labels=False) + 1)
        tab = x.groupby("dec").agg(n=("p", "size"), forecast=("p", "mean"), observed=("t_start", "mean"))
        brier = float(np.mean((x["p"] - x["t_start"].astype(float)) ** 2))
        base = float(np.mean((x["t_start"].mean() - x["t_start"].astype(float)) ** 2))
        print(f"\n#### {label}: {name} (2021-2025 out of sample, {len(x)} rows; Brier {brier:.4f}, "
              f"climatology {base:.4f})\n")
        print(tab.round(3).to_string())
        byh = x.groupby("h").agg(n=("p", "size"), forecast=("p", "mean"), observed=("t_start", "mean"))
        print("\nby horizon:\n" + byh.round(3).to_string())


def judge(r: pd.DataFrame, d: pd.DataFrame, sc: dict, cand: str, pre: str, base_ud: pd.DataFrame) -> dict:
    """The rule's clauses (a)-(e) against v3.6 on the same rows (METRICS § v3.7)."""
    bd = r["kind"] == "board"
    h1 = (r["kind"] == "horizon") & (r["h"] <= 1)
    a_cells = int((r.loc[bd | h1, cand] - r.loc[bd | h1, "v3.6"]).abs().gt(1e-9).sum())
    hb, hc = Q.horizon_seasons(r, "v3.6"), Q.horizon_seasons(r, cand)
    dm, ds = hc["mae"] - hb["mae"], hc["spearman"] - hb["spearman"]
    b_ok = bool(hc["mae"].mean() < hb["mae"].mean() and int((dm < 0).sum()) >= 4)
    c_ok = bool(hc["spearman"].mean() >= hb["spearman"].mean())
    u = ud_summary(ud_rates(d, sc, pre))
    d_ok = bool(u["model"].mean() >= base_ud["model"].mean())
    return {"cand": cand, "a_cells": a_cells, "a": a_cells == 0, "mae": hc["mae"].mean(), "mae_v36": hb["mae"].mean(),
            "seasons_lower": int((dm < 0).sum()), "b": b_ok, "sp": hc["spearman"].mean(), "sp_v36": hb["spearman"].mean(),
            "c": c_ok, "ud": u["model"].mean(), "ud_v36": base_ud["model"].mean(), "d": d_ok, "ud_tab": u, "hz": hc, "dm": dm, "ds": ds}


def run_study(cache_path: Path) -> None:
    d, leagues = v36_lines(cache_path)
    hz = role_frame(d)
    priors = role_priors(d)
    p0 = role_probs(hz, conditional=False)
    p1 = role_probs(hz, conditional=True)
    print("\n### Base rates (h 2-8, every row with a week-T row / the rows where he played in week T)\n")
    print(hz.groupby(["mkt_start", "h"]).agg(n=("t_start", "size"), starts=("t_start", "mean"),
                                             n_played=("played_b", "sum")).round(3).unstack("mkt_start").to_string())
    print(hz[hz["played_b"]].groupby(["mkt_start", "h"])["t_start"].mean().round(3).unstack("mkt_start").to_string())
    print("\n### Reliability of the probability by decile (calibration first, before any points)")
    reliability(hz, p0, "rf1.0 (every row)", np.ones(len(hz), dtype=bool))
    reliability(hz, p1, "rf1.1 (rows where he played in week T)", hz["played_b"].to_numpy())
    keep = pd.Series(np.where(hz["mkt_start"], 1.0, 0.0), index=hz.index)
    oracle = pd.Series(hz["t_start"].astype(float).to_numpy(), index=hz.index)
    d = mix_lines(d, hz, keep, "keep", priors)
    d = mix_lines(d, hz, p0, "rf0", priors)
    d = mix_lines(d, hz, p1, "rf1", priors)
    d = mix_lines(d, hz, oracle, "orc", priors)
    # rf1.2 -- defined AFTER rf1.0's numbers were read (post hoc, information only, not eligible to ship): rf1.0's
    # probability for the market week's non-starters only; the market week's starter keeps v3.6's line
    p2 = p0.where(~hz["mkt_start"], 1.0)
    d = mix_lines(d, hz, p2, "rf2", priors)
    names = {"v3.6": "hb0", "keeps the job": "keep", "rf1.0": "rf0", "rf1.1": "rf1", "rf1.2 (post hoc)": "rf2", "oracle": "orc"}
    r = priced_frame(d, leagues, names)
    print("\n### 2-8 weeks pooled, both house scorings (MAE / Spearman by season; mean = the rule's pooled number)\n")
    print(Q.table({k: Q.horizon_seasons(r, k) for k in names}))
    print("\n### by horizon (seasons averaged, both scorings)\n")
    print(pd.concat({k: Q.by_h(r, k) for k in names}, axis=1).round(3).to_string())
    for lid in leagues:
        print(f"\n### 2-8 weeks pooled, league {lid[-6:]} only\n")
        print(Q.table({k: Q.horizon_seasons(r, k, league=lid) for k in names}))
    st = r[r["pn_qb_starting"].fillna(0).gt(0.5)]
    nst = r[~r["pn_qb_starting"].fillna(0).gt(0.5)]
    print("\n### market-week starters only / non-starters only, 2-8 pooled (information)\n")
    print(Q.table({k: Q.horizon_seasons(st, k) for k in names}))
    print(Q.table({k: Q.horizon_seasons(nst, k) for k in names}))
    sc = leagues[SCRUBS][1]
    base_ud = ud_summary(ud_rates(d, sc, "hb0"))
    print("\n### ud1.0 quarterbacks by season (calculator; his own record)\n")
    uds = {k: ud_summary(ud_rates(d, sc, pre)) for k, pre in names.items()}
    print(pd.concat({k: u["model"] for k, u in uds.items()} | {"his own record": base_ud["base"]}, axis=1).round(3).to_string())
    print("pooled:", {k: round(float(u["model"].mean()), 4) for k, u in uds.items()}, "record", round(float(base_ud["base"].mean()), 4))
    print("\n### The rule (clause e: QB-only code, 0 cells at other positions by construction)\n")
    for cand, pre in (("rf1.0", "rf0"), ("rf1.1", "rf1"), ("rf1.2 (post hoc)", "rf2"), ("oracle", "orc")):
        j = judge(r, d, sc, cand, pre, base_ud)
        print(f"{cand}: (a) {j['a_cells']} market-week cells -> {j['a']}; (b) MAE {j['mae']:.3f} vs {j['mae_v36']:.3f}, "
              f"lower in {j['seasons_lower']} of 5 (Δ by season {np.round(j['dm'].to_numpy(), 3).tolist()}) -> {j['b']}; "
              f"(c) Spearman {j['sp']:.4f} vs {j['sp_v36']:.4f} (Δ by season {np.round(j['ds'].to_numpy(), 4).tolist()}) -> {j['c']}; "
              f"(d) ud1.0 {j['ud']:.4f} vs {j['ud_v36']:.4f} -> {j['d']}; "
              f"all: {j['a'] and j['b'] and j['c'] and j['d']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["cache", "v36", "study"])
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if a.mode == "cache":
        cache(a.out)
    elif a.mode == "v36":
        run_v36(a.cache)
    else:
        run_study(a.cache)


if __name__ == "__main__":
    main()
