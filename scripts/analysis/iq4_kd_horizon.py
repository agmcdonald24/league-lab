"""IQ-4 (Wave I-Q): kickers and defenses 2-8 weeks ahead -- kd1.0 against the naive number (docs/METRICS.md § "Kickers
and defenses beyond next week"; the keep rule there was written before this ran). Read only.

Seasons 2021-2025, one kd1.0 fit per season and position on every completed season before it (``kdef.fit_kd``, the
production constants). As of week W (W = 3, 5, 7, 9) each unit's row for week T = W+h (h = 1..8) is rebuilt the way the
nightly builds a future week: T's own game columns (week, home, dome, opponent), its betting line only at h = 1 (the
market week; NULL from h = 2), and every as-of input (the team's and the opponent's season-to-date / last-three /
last-season rates, the kicker's career) frozen at what was known after week W -- the inputs of week W+1. The naive
number is the unit's points per game this season through week W (``kdef.ppg_baselines``' ``season_ppg`` of week W+1).
Scored against what each unit scored in T, in each house league's scoring, per season x W x T x position x league with
>= 8 units that played: MAE and Spearman of the model and of the naive number on the same unit-weeks.

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/iq4_kd_horizon.py [--seasons 2021-2025] [--out <csv>]
"""
from __future__ import annotations

import argparse
import logging
import os
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402

from league_lab import kdef as K  # noqa: E402
from league_lab.config import get_settings  # noqa: E402
from league_lab.rankings import _spearman  # noqa: E402

log = logging.getLogger("iq4")
TESTS = (2021, 2022, 2023, 2024, 2025)
AS_OF = (3, 5, 7, 9)
H_MAX = 8
MIN_UNITS = 8
SUMS: list[dict] = []     # context: weeks W+2..W+8 per unit (>= 5 of them played), per game, ranked
LINES = ["implied_team_total", "opp_implied_total", "total_line", "spread_line"]


def first_from(df: pd.DataFrame, key: str, season: int, week: int) -> pd.DataFrame:
    """Each ``key``'s first row of ``season`` at week >= ``week``: its as-of inputs exclude that week and later, and a
    team on a bye at ``week`` played nothing in between -- so these are the inputs known after week ``week`` - 1."""
    d = df[(df["season"] == season) & (df["week"] >= week)].sort_values([key, "week"])
    return d.drop_duplicates(key).set_index(key)


def asof_rows(frame: pd.DataFrame, ta: pd.DataFrame, pos: str, season: int, w: int) -> pd.DataFrame:
    """The rows of weeks W+1 .. W+8 of ``season`` rebuilt as of week W (see the module docstring), with ``h``."""
    f = frame[(frame["position"] == pos) & (frame["season"] == season)]
    feats = K.FEATURES[pos]
    asof_cols = [c for c in feats if c not in K.GAME_FEATURES]
    team_cols = [c for c in asof_cols if not c.startswith("opp_") and not c.startswith("k_")]
    opp_cols = [c for c in asof_cols if c.startswith("opp_")]
    k_cols = [c for c in asof_cols if c.startswith("k_")]
    team_at = first_from(ta, "team", season, w + 1)
    k_at = first_from(f, "unit_id", season, w + 1)[k_cols] if k_cols else None
    out = []
    for h in range(1, H_MAX + 1):
        t = f[(f["week"] == w + h) & f["played"]].copy()
        if t.empty:
            continue
        t = t[t["team"].isin(team_at.index) & t["opponent"].isin(team_at.index)]
        if k_cols:
            t = t[t["unit_id"].isin(k_at.index)]          # a kicker known by W+1 (production projects the roster's)
        for c in team_cols:
            t[c] = t["team"].map(team_at[c]).to_numpy(dtype=float)
        for c in opp_cols:
            t[c] = t["opponent"].map(team_at[c.removeprefix("opp_")]).to_numpy(dtype=float)
        for c in k_cols:
            t[c] = t["unit_id"].map(k_at[c]).to_numpy(dtype=float)
        if h >= 2:
            t[LINES] = np.nan
        t["h"] = h
        out.append(t)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def team_table(conn: psycopg.Connection, seasons: list[int]) -> pd.DataFrame:
    back = sorted({*seasons, *(s - 1 for s in seasons)})
    with conn.cursor() as cur:
        tg = K._frame(cur, f"""select {', '.join(K.TEAM_GAME_COLUMNS)} from analytics.mart_kd_team_game
                               where season = any(%s) order by team, season, week""", (back,))
    return K.team_asof(tg)


def study(conn: psycopg.Connection, seasons: tuple[int, ...]) -> pd.DataFrame:
    leagues = K.kd_leagues(conn)
    frame = K.load_frame(conn, list(range(2016, max(seasons) + 1)))
    ta = team_table(conn, list(seasons))
    rows = []
    for s in seasons:
        train = frame[frame["season"] < s]
        for pos in K.KD_POSITIONS:
            scorings = leagues[pos]
            if not scorings:
                continue
            t0 = time.time()
            m = K.fit_kd(train, pos, scorings)
            naive = {lid: K.ppg_baselines(frame[frame["season"] <= s], pos, sc) for lid, (_, sc) in scorings.items()}
            pts = {lid: K.unit_points(frame[frame["season"] == s], pos, sc) for lid, (_, sc) in scorings.items()}
            for w in AS_OF:
                r = asof_rows(frame, ta, pos, s, w)
                if r.empty:
                    continue
                pred, _ = K.predict_kd(m, r, scorings)
                pred = pred.merge(r[["unit_id", "season", "week", "h"]], on=["unit_id", "season", "week"])
                for lid in scorings:
                    nb = naive[lid][naive[lid]["week"] == w + 1][["unit_id", "season_ppg"]]
                    p = (pred[pred["league_id"] == lid].merge(pts[lid], on=["position", "unit_id", "season", "week"])
                         .merge(nb, on="unit_id", how="left")).dropna(subset=["proj_points", "season_ppg", "points"])
                    later = p[p["h"] >= 2]                    # context: the weeks' sum, the list's own claim
                    if not later.empty:
                        tot = later.groupby("unit_id").agg(model=("proj_points", "mean"), naive=("season_ppg", "mean"),
                                                           points=("points", "mean"), games=("h", "size"))
                        tot = tot[tot["games"] >= 5]
                        if len(tot) >= MIN_UNITS:
                            SUMS.append({"season": s, "as_of": w, "position": pos, "league_id": lid, "n": len(tot),
                                         "sp_model": _spearman(tot["model"], tot["points"]),
                                         "sp_naive": _spearman(tot["naive"], tot["points"])})
                    for (week, h), g in p.groupby(["week", "h"]):
                        if len(g) < MIN_UNITS:
                            continue
                        y = g["points"]
                        rows.append({"season": s, "as_of": w, "week": int(week), "h": int(h), "position": pos,
                                     "league_id": lid, "n": len(g),
                                     "mae_model": float((g["proj_points"] - y).abs().mean()),
                                     "mae_naive": float((g["season_ppg"] - y).abs().mean()),
                                     "sp_model": _spearman(g["proj_points"], y), "sp_naive": _spearman(g["season_ppg"], y)})
            log.info("season %s %s: fit + score %.0f s", s, pos, time.time() - t0)
    return pd.DataFrame(rows)


def summary(res: pd.DataFrame) -> str:
    out = []
    for pos, g in res.groupby("position"):
        out.append(f"\n### {pos}\n")
        out.append("| horizon | cells | MAE model | MAE naive | Spearman model | Spearman naive |")
        out.append("|---|---|---|---|---|---|")
        for h, gh in g.groupby("h"):
            out.append(f"| {h} | {len(gh)} | {gh['mae_model'].mean():.3f} | {gh['mae_naive'].mean():.3f} | "
                       f"{gh['sp_model'].mean():.3f} | {gh['sp_naive'].mean():.3f} |")
        p = g[g["h"] >= 2]
        out.append(f"| **pooled 2–8** | {len(p)} | **{p['mae_model'].mean():.3f}** | **{p['mae_naive'].mean():.3f}** | "
                   f"**{p['sp_model'].mean():.3f}** | **{p['sp_naive'].mean():.3f}** |")
        by = p.groupby("season")[["mae_model", "mae_naive", "sp_model", "sp_naive"]].mean()
        out.append("\n| season (pooled 2–8) | MAE model | MAE naive | Spearman model | Spearman naive |")
        out.append("|---|---|---|---|---|")
        for s, r in by.iterrows():
            out.append(f"| {s} | {r.mae_model:.3f} | {r.mae_naive:.3f} | {r.sp_model:.3f} | {r.sp_naive:.3f} |")
        sp_win = int((by["sp_model"] > by["sp_naive"]).sum())
        mae_ok = int((by["mae_model"] <= by["mae_naive"]).sum())
        nsp_win = int((by["sp_naive"] > by["sp_model"]).sum())
        nmae_ok = int((by["mae_naive"] <= by["mae_model"]).sum())
        best = max(by["sp_model"].mean(), by["sp_naive"].mean())
        if sp_win >= 4 and mae_ok >= 4:
            verdict = "keep kd1.0"
        elif nsp_win >= 4 and nmae_ok >= 4:
            verdict = "replace by the naive number"
        else:
            verdict = "no different: the naive number (the cheaper honest choice)"
        off = best < 0.15
        out.append(f"\nmodel Spearman higher in {sp_win} of {len(by)} seasons, MAE not higher in {mae_ok}; naive Spearman "
                   f"higher in {nsp_win}, MAE not higher in {nmae_ok}; best pooled Spearman {best:.3f} -> **{verdict}**"
                   + ("; **take the list off the public screen** (best Spearman below 0.15)" if off else ""))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2021-2025")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    lo, _, hi = a.seasons.partition("-")
    seasons = tuple(range(int(lo), int(hi or lo) + 1))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        res = study(conn, seasons)
    if a.out:
        res.to_csv(a.out, index=False)
    print(summary(res))
    sums = pd.DataFrame(SUMS)
    if not sums.empty:
        print("\n### Context (decides nothing): weeks W+2 .. W+8 per unit (5+ played), points per game, ranked against what it scored per game\n")
        print("| position | cells | Spearman model | Spearman naive |")
        print("|---|---|---|---|")
        for pos, g in sums.groupby("position"):
            print(f"| {pos} | {len(g)} | {g['sp_model'].mean():.3f} | {g['sp_naive'].mean():.3f} |")


if __name__ == "__main__":
    main()
