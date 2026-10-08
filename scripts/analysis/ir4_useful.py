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
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    r = pd.read_parquet(a.report) if a.report else run(a.positions.split(","), a.out)
    report(r)


if __name__ == "__main__":
    main()
