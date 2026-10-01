"""E4: score a feature group on week subsets (weeks 1-4 / 5+, rookies) from per-row point projections.

The harness keeps only season means per league x position (summarize_scores), so a weeks 1-4 subset needs per-row
predictions. Spearman / MAE / hit rate depend only on the point projection (the component models), so:
  baseline per-row projections = ops.player_prior_oof_pred (component_walk_forward with FEATURES_BY_POSITION:
                                 the harness baseline's point projection, row for row),
  group per-row projections    = component_walk_forward with FEATURES_BY_POSITION + the group's columns (refit here).
Scored exactly like projections.score_predictions (scorer v2_points): per league x season x week x position over
played rows with every out_ component known, weeks with >= 8 players; season means of the weekly scores.

usage: OMP_NUM_THREADS=1 uv run python scripts/e4/week_subsets.py <group> [--check]   (writes pred_<group>.parquet and
subset_<group>.csv to $E4_OUT, default the current directory)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from league_lab import experiments as E
from league_lab import projections as P
from league_lab.config import get_settings
from league_lab.feature_groups import player_prior as PP
from league_lab.rankings import TOP_N, _hit_rate, _spearman

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
OUT = Path(os.environ.get("E4_OUT", "."))
SEASONS = [2023, 2024, 2025]


def weekly(df: pd.DataFrame, proj: str, actual: str, mask: pd.Series | None = None, min_players: int = 8) -> pd.DataFrame:
    d = df if mask is None else df[mask]
    rows = []
    for (season, week, pos), g in d.groupby(["season", "week", "position"]):
        if len(g) < min_players:
            continue
        rows.append({"season": season, "week": week, "position": pos, "n": len(g),
                     "spearman": _spearman(g[proj], g[actual]), "hit_rate": _hit_rate(g[proj], g[actual], TOP_N[pos]),
                     "mae": float((g[proj] - g[actual]).abs().mean()), "bias": float((g[proj] - g[actual]).mean())})
    return pd.DataFrame(rows)


def main(group: str, check: bool) -> None:
    t0 = time.monotonic()
    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=True) as conn:
        spec = E.get_group(conn, group)
        scorings = P.league_scorings(conn)
        seasons_all = P.available_seasons(conn)
        frame = P.load_frame(conn, [s for s in seasons_all if s <= max(SEASONS)], extra_tables={spec.table: spec.columns})

        base = pd.DataFrame(conn.execute(
            f"select gsis_id, season, week, position, played, {', '.join(f'proj_{k}, actual_{k}' for k in scorings)} "
            f"from {PP.PRED_TABLE} where season = any(%s)", (SEASONS,)).fetchall(),
            columns=["gsis_id", "season", "week", "position", "played", *[f"{a}_{k}" for k in scorings for a in ("proj", "actual")]])
        rk = pd.DataFrame(conn.execute("select gsis_id, season, week, rk_is_rookie, rk_years_in from intermediate.int_e4_player_week_rookie_prior "
                                       "where season = any(%s)", (SEASONS,)).fetchall(),
                          columns=["gsis_id", "season", "week", "rk_is_rookie", "rk_years_in"])
    feats = {p: [*P.FEATURES_BY_POSITION[p], *spec.columns] for p in P.POSITIONS}
    grp = PP.component_walk_forward(frame, SEASONS, scorings, min(seasons_all), feats)
    grp.to_parquet(OUT / f"pred_{group}.parquet")
    m = base.merge(grp[["gsis_id", "season", "week", *[f"proj_{k}" for k in scorings]]], on=["gsis_id", "season", "week"],
                   suffixes=("_base", "_grp"), validate="one_to_one")
    m = m.merge(rk, on=["gsis_id", "season", "week"], how="left")
    rows = []
    for lid in scorings:
        d = m[m["played"] & m[f"actual_{lid}"].notna()]
        for subset, mask in (("all weeks", None), ("weeks 1-4", d["week"] <= 4), ("weeks 5+", d["week"] >= 5)):
            wb = weekly(d, f"proj_{lid}_base", f"actual_{lid}", mask)
            wg = weekly(d, f"proj_{lid}_grp", f"actual_{lid}", mask)
            w = wb.merge(wg, on=["season", "week", "position", "n"], suffixes=("_b", "_g"))
            s = w.groupby(["season", "position"])[["spearman_b", "spearman_g", "mae_b", "mae_g", "hit_rate_b", "hit_rate_g"]].mean().reset_index()
            s["league_id"], s["subset"] = lid, subset
            rows.append(s)
        # rookies (first NFL season) in weeks 1-4: too few per week for a rank; pooled MAE and bias per season
        r = d[(d["week"] <= 4) & (d["rk_is_rookie"] == 1)]
        for (season, pos), g in r.groupby(["season", "position"]):
            rows.append(pd.DataFrame([{"season": season, "position": pos, "league_id": lid, "subset": "rookies weeks 1-4 (pooled)",
                                       "n": len(g), "mae_b": (g[f"proj_{lid}_base"] - g[f"actual_{lid}"]).abs().mean(),
                                       "mae_g": (g[f"proj_{lid}_grp"] - g[f"actual_{lid}"]).abs().mean(),
                                       "bias_b": (g[f"proj_{lid}_base"] - g[f"actual_{lid}"]).mean(),
                                       "bias_g": (g[f"proj_{lid}_grp"] - g[f"actual_{lid}"]).mean()}]))
    res = pd.concat(rows, ignore_index=True)
    res["d_spearman"] = res.get("spearman_g") - res.get("spearman_b")
    res["d_mae"] = res["mae_g"] - res["mae_b"]
    res.to_csv(OUT / f"subset_{group}.csv", index=False)
    # league-averaged per season, then over seasons (the harness's pairing)
    per = res.groupby(["subset", "position", "season"])[["d_spearman", "d_mae"]].mean().reset_index()
    summ = per.groupby(["subset", "position"]).agg(d_spearman=("d_spearman", "mean"), better_s=("d_spearman", lambda x: int((x > 0).sum())),
                                                   d_mae=("d_mae", "mean"), better_m=("d_mae", lambda x: int((x < 0).sum())),
                                                   n_seasons=("season", "count")).reset_index()
    pd.set_option("display.width", 200)
    print(summ.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    rook = res[res["subset"].str.startswith("rookies")].groupby(["position"]).agg(
        n=("n", "sum"), mae_b=("mae_b", "mean"), mae_g=("mae_g", "mean"), bias_b=("bias_b", "mean"), bias_g=("bias_g", "mean")).reset_index()
    print("rookies, weeks 1-4 (mean over seasons and leagues of the pooled values):")
    print(rook.to_string(index=False, float_format=lambda v: f"{v:+.3f}"))
    if check:   # the full-season numbers next to the harness's rows
        with psycopg.connect(get_settings().pipeline_dsn(), autocommit=True) as conn:
            h = pd.DataFrame(conn.execute("""select league_id, test_season, position, spearman, mae, baseline_spearman, baseline_mae
                                             from ops.feature_experiments where feature_group = %s and model_version = %s""",
                                          (group, P.MODEL_VERSION)).fetchall(),
                             columns=["league_id", "season", "position", "spearman", "mae", "baseline_spearman", "baseline_mae"])
        a = res[res["subset"] == "all weeks"].merge(h, on=["league_id", "season", "position"])
        a["dsb"] = a["spearman_b"] - a["baseline_spearman"].astype(float)
        a["dsg"] = a["spearman_g"] - a["spearman"].astype(float)
        a["dmb"] = a["mae_b"] - a["baseline_mae"].astype(float)
        a["dmg"] = a["mae_g"] - a["mae"].astype(float)
        print("reproduction of the harness (all weeks): max |diff| spearman base/group, mae base/group:",
              *[f"{np.abs(a[c]).max():.2e}" for c in ("dsb", "dsg", "dmb", "dmg")], f"({len(a)} cells)")
    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=True) as conn:   # the baseline: always comparable
        hb = pd.DataFrame(conn.execute("""select league_id, test_season, position, spearman, mae, hit_rate from ops.feature_experiments
                                          where feature_group = 'baseline' and model_version = %s and test_seasons = '2023,2024,2025'""",
                                       (P.MODEL_VERSION,)).fetchall(), columns=["league_id", "season", "position", "hs", "hm", "hh"])
    a = res[res["subset"] == "all weeks"].merge(hb, on=["league_id", "season", "position"])
    print("baseline reproduction (OOF projections vs the harness's cached baseline, all weeks): max |diff| spearman",
          f"{(a['spearman_b'] - a['hs'].astype(float)).abs().max():.2e}, mae {(a['mae_b'] - a['hm'].astype(float)).abs().max():.2e},",
          f"hit rate {(a['hit_rate_b'] - a['hh'].astype(float)).abs().max():.2e} ({len(a)} cells)")
    print(f"done in {time.monotonic() - t0:.0f} s")


if __name__ == "__main__":
    main(sys.argv[1], "--check" in sys.argv)
