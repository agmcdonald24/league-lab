"""E4 follow-up: player_prior as a post-hoc correction instead of a tree input.
proj' = proj + k_pos * pp_resid_ewm (0 when he has no scored game), k_pos = least-squares slope of the miss on
pp_resid_ewm fitted on seasons < S only (walk-forward), scored per week like score_predictions (weeks with >= 8
players), both leagues' scoring (the residual is in reference scoring; k is fitted per league on its own misses).
--bias-only: the control - proj + the position's mean miss over seasons < S (a constant shift, no player in it).

usage: OMP_NUM_THREADS=1 uv run python scripts/e4/player_prior_correction.py [--bias-only]"""
import sys

import numpy as np
import pandas as pd
import psycopg

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from week_subsets import weekly  # noqa: E402

from league_lab import projections as P
from league_lab.config import get_settings
from league_lab.feature_groups import player_prior as PP

BIAS_ONLY = "--bias-only" in sys.argv
with psycopg.connect(get_settings().pipeline_dsn(), autocommit=True) as conn:
    sc = list(P.league_scorings(conn))
    cols = ", ".join(f'"proj_{k}", "actual_{k}"' for k in sc)
    d = pd.DataFrame(conn.execute(f"select p.gsis_id, p.season, p.week, p.position, p.played, {cols}, o.pp_resid_ewm, o.pp_resid_games "
                                  f"from {PP.PRED_TABLE} p join {PP.TABLE} o using (gsis_id, season, week) where p.season between 2017 and 2025").fetchall(),
                     columns=["gsis_id", "season", "week", "position", "played", *[f"{a}_{k}" for k in sc for a in ("proj", "actual")], "pp", "ppn"])
d["pp"] = d["pp"].astype(float).fillna(0.0)
out = []
for lid in sc:
    x = d[d["played"] & d[f"actual_{lid}"].notna()].copy()
    x["miss"] = x[f"actual_{lid}"] - x[f"proj_{lid}"]
    for S in (2023, 2024, 2025):
        t = x[x["season"] == S].copy()
        for pos in P.POSITIONS:
            tr = x[(x["season"] < S) & (x["position"] == pos) & (x["ppn"] > 0)]
            k = float(np.dot(tr["pp"], tr["miss"]) / np.dot(tr["pp"], tr["pp"]))
            m = t["position"] == pos
            if BIAS_ONLY:
                t.loc[m, "adj"] = t.loc[m, f"proj_{lid}"] + float(x[(x["season"] < S) & (x["position"] == pos)]["miss"].mean())
            else:
                t.loc[m, "adj"] = t.loc[m, f"proj_{lid}"] + k * t.loc[m, "pp"]
            t.loc[m, "k"] = k
        t["adj"] = t["adj"].clip(lower=0)
        wb = weekly(t, f"proj_{lid}", f"actual_{lid}")
        wg = weekly(t, "adj", f"actual_{lid}")
        w = wb.merge(wg, on=["season", "week", "position", "n"], suffixes=("_b", "_g"))
        s = w.groupby(["season", "position"])[["spearman_b", "spearman_g", "mae_b", "mae_g"]].mean().reset_index()
        s["league_id"] = lid
        s["k"] = s["position"].map(t.groupby("position")["k"].first())
        out.append(s)
r = pd.concat(out)
r["ds"], r["dm"] = r["spearman_g"] - r["spearman_b"], r["mae_g"] - r["mae_b"]
per = r.groupby(["position", "season"])[["ds", "dm", "k"]].mean().reset_index()
print(per.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
summ = per.groupby("position").agg(ds=("ds", "mean"), better_s=("ds", lambda v: int((v > 0).sum())), dm=("dm", "mean"),
                                   better_m=("dm", lambda v: int((v < 0).sum())), k=("k", "mean")).reset_index()
print(summ.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
