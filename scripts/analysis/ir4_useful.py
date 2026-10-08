"""IR-4 (Wave I-R): the "useful decision" grade, ud1.0 (docs/METRICS.md § "What each number has been checked against
(IR-4)" → "The useful decision grade", defined and committed before this ran). Read only.

When the trade calculator favours one player over another of the same position (a close one-for-one: projected four-week
totals within 20 % of each other), does the favoured player score more over those four weeks? Against the side his own
per-game record favours. Seasons 2021–2025, as of weeks 3 / 5 / 7 / 9, one fit per season and position (2016..S−1),
the rows ``iq1_horizon.future_rows`` builds with v3.5's later-week inputs (variant *ad*), Half PPR (League of Scrubs).

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/ir4_useful.py [--positions QB,RB,WR,TE] [--out ud.parquet]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import iq1_horizon as H  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402

from league_lab import projections as P  # noqa: E402
from league_lab.config import get_settings  # noqa: E402

log = logging.getLogger("ir4")
TESTS = (2021, 2022, 2023, 2024, 2025)
AS_OF = (3, 5, 7, 9)
WINDOW = 4
TOP = {"QB": 24, "RB": 36, "WR": 36, "TE": 24}
CLOSE = 0.20          # a pair is close when the totals differ by at most 20 % of the larger
DECISIVE = 0.10       # ... and "not about even" when they differ by more than 10 %
SCRUBS = "1389709692405551104"
OUT = [f"out_{c}" for c in P.ALL_COMPONENTS]


def priced(rows: pd.DataFrame, sc: dict[str, float]) -> np.ndarray:
    ok = rows[OUT].notna().all(axis=1).to_numpy() & rows["played"].fillna(False).astype(bool).to_numpy()
    return np.where(ok, P.price(rows.fillna({c: 0 for c in OUT}), sc, "out_").to_numpy(dtype=float), 0.0)


def ppg(rows: pd.DataFrame, sc: dict[str, float]) -> pd.Series:
    r = rows[rows["played"].fillna(False).astype(bool) & rows[OUT].notna().all(axis=1)]
    if r.empty:
        return pd.Series(dtype=float)
    return pd.Series(P.price(r, sc, "out_").to_numpy(dtype=float), index=r["gsis_id"].to_numpy()).groupby(level=0).mean()


def pair_rates(t: pd.DataFrame) -> dict:
    """t: gsis_id, proj, act, base (NaN = no record) for one season × W × position's top players."""
    p, a, b = t["proj"].to_numpy(), t["act"].to_numpy(), t["base"].to_numpy()
    i, j = np.triu_indices(len(t), k=1)
    hi = np.maximum(p[i], p[j])
    gap = np.abs(p[i] - p[j])
    keep = (hi > 0) & (gap <= CLOSE * hi) & (gap > 0) & np.isfinite(b[i]) & np.isfinite(b[j])
    i, j, gap, hi = i[keep], j[keep], gap[keep], hi[keep]

    def hit(x):
        fav = np.sign(x[i] - x[j])
        out = np.sign(a[i] - a[j])
        return np.where(fav == 0, np.nan, np.where(out == 0, 0.5, (fav == out).astype(float)))
    m, bb = hit(p), hit(b)
    dec = gap > DECISIVE * hi
    return {"pairs": int(len(i)), "model": float(np.nanmean(m)) if len(i) else np.nan,
            "base": float(np.nanmean(bb)) if len(i) else np.nan,
            "pairs_decisive": int(dec.sum()), "model_decisive": float(np.nanmean(m[dec])) if dec.any() else np.nan,
            "base_decisive": float(np.nanmean(bb[dec])) if dec.any() else np.nan}


def run(positions: list[str], out: str) -> pd.DataFrame:
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        frame = H.load(conn, [s for s in P.available_seasons(conn) if s <= max(TESTS)])
        sc = P.league_scorings(conn)[SCRUBS][1]
    frame["season"] = frame["season"].astype(int)
    res = []
    for s in TESTS:
        for pos in positions:
            t0 = time.monotonic()
            models, feats = H.fit(frame, s, pos)
            fpos = frame[frame["position"] == pos]
            last = ppg(fpos[fpos["season"] == s - 1], sc)
            for w in AS_OF:
                rows = H.future_rows(fpos, s, w, h_max=WINDOW)
                rows = rows[rows["position"] == pos].reset_index(drop=True)
                v = H.market_personnel(H.impute_lines(rows, H.team_lines_asof(frame, s, w)))
                proj = np.nan_to_num(H.predict(models, feats, v, sc), nan=0.0)
                d = rows[["gsis_id"]].assign(proj=proj, act=priced(rows, sc), games=1.0)
                tot = d.groupby("gsis_id").agg(proj=("proj", "sum"), act=("act", "sum"), games=("games", "sum"))
                cur = ppg(fpos[(fpos["season"] == s) & (fpos["week"] <= w)], sc)
                rate = cur.reindex(tot.index).fillna(last.reindex(tot.index))
                tot["base"] = rate * tot["games"]
                top = tot.sort_values("proj", ascending=False).head(TOP[pos]).reset_index()
                res.append({"season": s, "as_of": w, "position": pos, "players": len(top), **pair_rates(top)})
            log.info("%s %s: %.0f s", s, pos, time.monotonic() - t0)
    r = pd.DataFrame(res)
    r.to_parquet(out)
    return r


# ---- the simple baseline beyond next week (METRICS § "His own record beyond next week at RB / WR / TE")
def baseline_run(positions: list[str], out: str) -> pd.DataFrame:
    """Per season × W × target week × position × league (players who played, ≥ 8): the model's (variant ad) and his
    own record's MAE and Spearman on the same rows (a row without a record is left out of both)."""
    from league_lab.rankings import _spearman
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        frame = H.load(conn, [s for s in P.available_seasons(conn) if s <= max(TESTS)])
        leagues = P.league_scorings(conn)
    frame["season"] = frame["season"].astype(int)
    res = []
    for s in TESTS:
        for pos in positions:
            t0 = time.monotonic()
            models, feats = H.fit(frame, s, pos)
            fpos = frame[frame["position"] == pos]
            for w in AS_OF:
                rows = H.future_rows(fpos, s, w)
                rows = rows[rows["position"] == pos].reset_index(drop=True)
                v = H.market_personnel(H.impute_lines(rows, H.team_lines_asof(frame, s, w)))
                ok = rows[OUT].notna().all(axis=1).to_numpy() & rows["played"].fillna(False).astype(bool).to_numpy()
                for lid, (_, sc) in leagues.items():
                    proj = H.predict(models, feats, v, sc)
                    act = np.where(ok, P.price(rows.fillna({c: 0 for c in OUT}), sc, "out_").to_numpy(dtype=float), np.nan)
                    cur = ppg(fpos[(fpos["season"] == s) & (fpos["week"] <= w)], sc)
                    last = ppg(fpos[fpos["season"] == s - 1], sc)
                    rec = cur.reindex(rows["gsis_id"]).to_numpy(dtype=float)
                    rec = np.where(np.isfinite(rec), rec, last.reindex(rows["gsis_id"]).to_numpy(dtype=float))
                    d = rows[["target_week", "h"]].assign(proj=proj, base=rec, act=act)
                    d = d[np.isfinite(d["act"]) & np.isfinite(d["base"]) & np.isfinite(d["proj"])]
                    for (t, h), g in d.groupby(["target_week", "h"]):
                        if len(g) < 8:
                            continue
                        res.append({"season": s, "as_of": w, "target_week": t, "h": h, "position": pos, "league_id": lid,
                                    "n": len(g), "mae": float((g["proj"] - g["act"]).abs().mean()),
                                    "spearman": _spearman(g["proj"], g["act"]),
                                    "base_mae": float((g["base"] - g["act"]).abs().mean()),
                                    "base_spearman": _spearman(g["base"], g["act"])})
            log.info("baseline %s %s: %.0f s", s, pos, time.monotonic() - t0)
    r = pd.DataFrame(res)
    r.to_parquet(out)
    return r


def baseline_report(r: pd.DataFrame) -> None:
    for name, hs in (("next four weeks (h 1-4)", range(1, 5)), ("rest of season (h 1-8)", range(1, 9)),
                     ("two to eight weeks (h 2-8)", range(2, 9))):
        x = r[r["h"].isin(list(hs))]
        by = x.groupby(["position", "season"])[["mae", "spearman", "base_mae", "base_spearman"]].mean()
        print(f"\n{name}: by season")
        print(by.round(3).to_string())
        pooled = by.groupby("position").mean()
        wins = by.assign(win=(by["spearman"] > by["base_spearman"]) & (by["mae"] < by["base_mae"]),
                         loss=(by["spearman"] < by["base_spearman"]) & (by["mae"] > by["base_mae"])).groupby("position")[["win", "loss"]].sum()
        print(f"{name}: pooled (mean over seasons) and seasons where the model is ahead on both / behind on both")
        print(pd.concat([pooled.round(3), wins], axis=1).to_string())


def report(r: pd.DataFrame) -> None:
    def w(g, col, n):              # pair-weighted within a season
        x = g[g[n] > 0]
        return float((x[col] * x[n]).sum() / x[n].sum()) if len(x) else float("nan")
    rows = []
    for (pos, s), g in r.groupby(["position", "season"]):
        rows.append({"position": pos, "season": s, "pairs": int(g["pairs"].sum()), "model": w(g, "model", "pairs"),
                     "base": w(g, "base", "pairs"), "pairs_decisive": int(g["pairs_decisive"].sum()),
                     "model_decisive": w(g, "model_decisive", "pairs_decisive"),
                     "base_decisive": w(g, "base_decisive", "pairs_decisive")})
    t = pd.DataFrame(rows)
    print(t.round(3).to_string(index=False))
    pooled = t.groupby("position").agg(pairs=("pairs", "sum"), model=("model", "mean"), base=("base", "mean"),
                                       model_decisive=("model_decisive", "mean"), base_decisive=("base_decisive", "mean"))
    wins = t.assign(win=(t["model"] > t["base"]) & (t["model"] > 0.5)).groupby("position")["win"].sum()
    pooled["seasons_above_base_and_half"] = wins
    print("\npooled (mean over seasons):")
    print(pooled.round(3).to_string())
    allp = t.groupby("season").apply(lambda g: pd.Series({"model": (g["model"] * g["pairs"]).sum() / g["pairs"].sum(),
                                                          "base": (g["base"] * g["pairs"]).sum() / g["pairs"].sum()}),
                                     include_groups=False)
    print("\nall positions, pair-weighted by season:")
    print(allp.round(3).to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--positions", default="QB,RB,WR,TE")
    ap.add_argument("--out", default="ud.parquet")
    ap.add_argument("--report", default=None, help="only report an existing parquet")
    ap.add_argument("--baseline", action="store_true", help="the own-record baseline beyond next week instead")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if a.baseline:
        baseline_report(pd.read_parquet(a.report) if a.report else baseline_run(a.positions.split(","), a.out))
        return
    r = pd.read_parquet(a.report) if a.report else run(a.positions.split(","), a.out)
    report(r)


if __name__ == "__main__":
    main()
