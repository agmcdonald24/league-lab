"""IP-1 (Wave I-P): the quarterback candidates the diagnosis points at, through the harness's rule
(docs/METRICS.md § "The quarterback weak spot (IP-1)" -> "Candidates"). Read-only on the database.

* rt1.0 -- QB rushing TDs, a mean-unbiased scale (the one bias the diagnosis found in every sample): k_S = sum of actual
  rushing TDs / sum of projected over the played QB rows of the 3 seasons before S (the walk-forward rows, production
  inputs), clipped to [0.70, 1.50]; every QB line's rushing TDs x k_S.
* st1.0 -- "Is he the starter?" from what happened (dbt var ``pn_starter_from_play``, int_pn_team_game): training rows
  read the corrected history; the test season's rows keep the stored listing except where the as-of guard fires (a
  listing that repeats one already contradicted by the team's newest played game -> that game's real starter). Needs
  the corrected int_pn_team_game / mart_player_week_features built with the var on, and the frame before it
  (``--before``, a parquet of mart_player_week_features' QB inputs taken before the rebuild).

Each is judged by ``experiments.decide`` on the QB board (2021-2025, both house scorings, the season paired; scorer =
the priced line, the backtest's scope: every played row with its 12 outcomes known, weeks with >= 8 players).

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/ip1_qb_candidates.py rt --rows rows.parquet [--rows-early r.parquet]
       OMP_NUM_THREADS=1 uv run python scripts/analysis/ip1_qb_candidates.py st --rows rows.parquet --before before.parquet
(rows: the walk-forward cache of scripts/analysis/ip1_qb_diagnosis.py; --rows-early: the same for 2018-2020, QB)
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402

from league_lab import experiments as E  # noqa: E402
from league_lab import projections as P  # noqa: E402
from league_lab.config import get_settings  # noqa: E402
from league_lab.rankings import TOP_N, _hit_rate, _spearman  # noqa: E402

log = logging.getLogger("ip1")
TESTS = [2021, 2022, 2023, 2024, 2025]
RT_WINDOW = 3
RT_BOUNDS = (0.70, 1.50)


# ------------------------------------------------------------------------------ scoring, the harness's terms
def priced(rows: pd.DataFrame, prefix: str, leagues: dict) -> pd.DataFrame:
    """One row per league x player-week: the line in ``<prefix><component>`` priced, and the actual (the 12 components)."""
    known = rows[[f"out_{c}" for c in P.ALL_COMPONENTS]].notna().all(axis=1) & rows["played"].fillna(False).astype(bool)
    d = rows[known].reset_index(drop=True)
    line = d.assign(**{f"proj_{c}": d[f"{prefix}{c}"] for c in P.ALL_COMPONENTS})
    out = []
    for lid, (_, sc) in leagues.items():
        out.append(pd.DataFrame({"league_id": lid, "gsis_id": d["gsis_id"], "season": d["season"].astype(int),
                                 "week": d["week"].astype(int), "proj": P.price(line, sc, "proj_").to_numpy(),
                                 "actual": P.price(d, sc, "out_").to_numpy()}))
    return pd.concat(out, ignore_index=True)


def weekly(p: pd.DataFrame, min_players: int = 8) -> pd.DataFrame:
    rows = []
    for (lid, s, w), g in p.groupby(["league_id", "season", "week"]):
        if len(g) < min_players:
            continue
        rows.append({"league_id": lid, "season": s, "week": w, "n": len(g), "mae": float((g["proj"] - g["actual"]).abs().mean()),
                     "spearman": _spearman(g["proj"], g["actual"]), "hit_rate": _hit_rate(g["proj"], g["actual"], TOP_N["QB"])})
    return pd.DataFrame(rows)


def paired(base: pd.DataFrame, cand: pd.DataFrame) -> pd.DataFrame:
    """Per season: the league-averaged season means' change (cand - base), as ``decide`` reads them."""
    wb, wc = weekly(base), weekly(cand)
    m = wb.merge(wc, on=["league_id", "season", "week"], suffixes=("_b", "_c"))
    s = m.groupby(["league_id", "season"])[["mae_b", "mae_c", "spearman_b", "spearman_c"]].mean().reset_index()
    s["delta_mae"], s["delta_spearman"] = s["mae_c"] - s["mae_b"], s["spearman_c"] - s["spearman_b"]
    per = s.groupby("season")[["delta_mae", "delta_spearman", "mae_b", "mae_c"]].mean().reset_index()
    per["position"] = "QB"
    return per


def bias(p: pd.DataFrame) -> float:
    return float((p["actual"] - p["proj"]).mean())


def report(name: str, per: pd.DataFrame, base: pd.DataFrame, cand: pd.DataFrame, flagged: pd.Series | None = None) -> None:
    dec = E.decide(per)
    print(f"\n### {name}\n")
    print("| season | MAE before → after | Δ MAE | Δ Spearman |\n|---|---|---|---|")
    for r in per.itertuples():
        print(f"| {r.season} | {r.mae_b:.3f} → {r.mae_c:.3f} | {r.delta_mae:+.3f} | {r.delta_spearman:+.4f} |")
    d = dec.iloc[0]
    print(f"\ndecide: Δ MAE {d.delta_mae:+.3f} (better in {d.seasons_better_mae} of {d.n_seasons}), Δ Spearman "
          f"{d.delta_spearman:+.4f} (better in {d.seasons_better_spearman} of {d.n_seasons}); helps {d.helps}, hurts {d.hurts} "
          f"-> **{d.decision}**")
    print(f"board bias (actual − projected), both scorings: {bias(base):+.3f} → {bias(cand):+.3f}")
    if flagged is not None:
        key = ["gsis_id", "season", "week"]
        fb = base.merge(flagged, on=key)
        fc = cand.merge(flagged, on=key)
        if len(fb):
            g = []
            for s in TESTS:
                b, c = fb[fb["season"] == s], fc[fc["season"] == s]
                if len(b) == 0:
                    g.append((s, 0, np.nan, np.nan, np.nan))
                    continue
                mb, mc = (b["proj"] - b["actual"]).abs().mean(), (c["proj"] - c["actual"]).abs().mean()
                g.append((s, len(b) // 2, mb, mc, mc - mb))
            print("\nflagged rows (both scorings; n = player-weeks a scoring):\n\n| season | n | MAE before → after | Δ |\n|---|---|---|---|")
            for s, n, mb, mc, dd in g:
                print(f"| {s} | {n} | " + ("—" if n == 0 else f"{mb:.2f} → {mc:.2f} | {dd:+.2f}") + (" | — |" if n == 0 else " |"))
            dl = [x[4] for x in g if x[1] > 0]
            lower = sum(1 for x in dl if x < 0)
            print(f"\nflagged: mean Δ MAE over the seasons with flagged rows {np.mean(dl):+.3f}, lower in {lower} of {len(TESTS)} "
                  f"seasons (the rule needs {E.seasons_needed(len(TESTS))}); bias {bias(fb):+.2f} → {bias(fc):+.2f}")


# ------------------------------------------------------------------------------ rt1.0
def rush_td_scale(rows: pd.DataFrame, s: int) -> tuple[float, int]:
    fit = rows[(rows["season"] >= s - RT_WINDOW) & (rows["season"] < s) & rows["played"].fillna(False).astype(bool)
               & rows["out_rushing_tds"].notna()]
    den = float(fit["v3_rushing_tds"].sum())
    k = float(fit["out_rushing_tds"].sum()) / den if den > 0 else 1.0
    return float(np.clip(k, *RT_BOUNDS)), len(fit)


def run_rt(rows: pd.DataFrame, leagues: dict) -> None:
    qb = rows[rows["position"] == "QB"].copy()
    cand = qb.copy()
    ks = {}
    for s in [*TESTS, 2026]:
        k, n = rush_td_scale(qb, s)
        ks[s] = (k, n)
        sel = cand["season"] == s
        cand.loc[sel, "v3_rushing_tds"] = cand.loc[sel, "v3_rushing_tds"] * k
    print("k by season (fitted on the 3 seasons before):", {s: f"{k:.3f} ({n} rows)" for s, (k, n) in ks.items()})
    t = qb[qb["season"].isin(TESTS)]
    c = cand[cand["season"].isin(TESTS)]
    base, alt = priced(t, "v3_", leagues), priced(c, "v3_", leagues)
    report("rt1.0: QB rushing TDs × k (mean-unbiased, 3 seasons before)", paired(base, alt), base, alt)
    rb = (t["out_rushing_tds"] - t["v3_rushing_tds"]).mean() * 6
    rc = (c["out_rushing_tds"] - c["v3_rushing_tds"]).mean() * 6
    print(f"rushing-TD bias (points at 6 a TD, played rows): {rb:+.3f} → {rc:+.3f}")


# ------------------------------------------------------------------------------ st1.0
TEAM_GAME_SQL = """select season, week, team, listed_qb_id, starting_qb_id, is_played from intermediate.int_pn_team_game
                   where season >= 2016 order by team, season, week"""


def guarded_listing(tg: pd.DataFrame) -> pd.DataFrame:
    """Per team-week: the stored listing with the as-of guard (``int_pn_team_game``'s unplayed-game rule, applied to
    every week: what a board made before that week's kickoff would have read)."""
    out = []
    for (team, season), g in tg.sort_values(["team", "season", "week"]).groupby(["team", "season"], sort=False):
        prev_listed = prev_played = None
        prev_wrong = False
        for r in g.itertuples():
            guard = r.listed_qb_id
            if r.listed_qb_id is not None and r.listed_qb_id == prev_listed and prev_wrong:
                guard = prev_played
            out.append((team, season, r.week, guard))
            if r.is_played:
                prev_listed, prev_played = r.listed_qb_id, r.starting_qb_id
                prev_wrong = r.listed_qb_id is not None and r.starting_qb_id != r.listed_qb_id
    return pd.DataFrame(out, columns=["team", "season", "week", "guard_qb_id"])


def run_st(rows: pd.DataFrame, before: pd.DataFrame, leagues: dict) -> None:
    s = get_settings()
    with psycopg.connect(s.pipeline_dsn()) as conn:
        conn.read_only = True
        seasons = P.available_seasons(conn)
        frame = P.load_frame(conn, [x for x in seasons if x <= max(TESTS)])
        tg = pd.DataFrame(conn.execute(TEAM_GAME_SQL).fetchall(), columns=["season", "week", "team", "listed_qb_id", "starting_qb_id", "is_played"])
    if (tg["listed_qb_id"].fillna("") == tg["starting_qb_id"].fillna("")).all():
        raise SystemExit("int_pn_team_game is not corrected: build it with --vars '{pn_starter_from_play: true}' first")
    # the frame's change: only the QB inputs may differ from the frame before
    key = ["gsis_id", "season", "week"]
    b = before.set_index(key)
    a = frame.assign(season=frame["season"].astype(int), week=frame["week"].astype(int)).set_index(key)
    common = a.index.intersection(b.index)
    moved = {}
    for c in [*P.QB_INPUTS, *P.TEAMMATE_INPUTS]:
        x, y = a.loc[common, c].astype(float), b.loc[common, c].astype(float)
        moved[c] = int(((x != y) & ~(x.isna() & y.isna())).sum())
    print("frame rows whose input moved (after vs before):", moved)
    # test rows: the stored inputs, "is he the starter?" from the guarded listing
    guard = guarded_listing(tg)
    first = min(seasons)
    feats = list(P.FEATURES_BY_POSITION["QB"])
    preds, flags = [], []
    for s_ in TESTS:
        t0 = time.monotonic()
        train = frame[(frame["season"] >= first) & (frame["season"] < s_)]
        d = train[(train["position"] == "QB") & train["played"] & ~train["no_history"]]
        d = d.dropna(subset=[f"out_{c}" for c in P.COMPONENTS["QB"]]).reset_index(drop=True)
        models = P._fit_components(P._matrix(d, feats), d, "QB")
        test = frame[(frame["season"] == s_) & (frame["position"] == "QB")].reset_index(drop=True)
        test = test.assign(season=test["season"].astype(int), week=test["week"].astype(int))
        old = before[before["season"] == s_].set_index(key)
        idx = pd.MultiIndex.from_frame(test[key])
        for c in P.QB_INPUTS:                                   # the stored (pre-correction) inputs of the test season
            test[c] = old[c].reindex(idx).to_numpy(dtype=float)
        g = test[["team", "season", "week"]].merge(guard, on=["team", "season", "week"], how="left")
        new_flag = np.where(g["guard_qb_id"].notna(), (g["guard_qb_id"] == test["gsis_id"]).astype(float), test["pn_qb_starting"])
        changed = new_flag != test["pn_qb_starting"].to_numpy()
        flags.append(test.loc[changed, key])
        test["pn_qb_starting"] = new_flag
        x = P._matrix(test, feats)
        out = test[[*key, "played", *[f"out_{c}" for c in P.ALL_COMPONENTS]]].copy()
        for c in P.ALL_COMPONENTS:
            out[f"st_{c}"] = np.clip(models[c].predict(x), 0, None) if c in models else 0.0
        preds.append(out)
        log.info("st1.0 %s: %s training rows, %s test rows, %s flags moved, %.0f s", s_, len(d), len(test), int(changed.sum()),
                 time.monotonic() - t0)
    cand = pd.concat(preds, ignore_index=True)
    base_rows = rows[(rows["position"] == "QB") & rows["season"].isin(TESTS)]
    base = priced(base_rows, "v3_", leagues)
    alt = priced(cand, "st_", leagues)
    flagged = pd.concat(flags, ignore_index=True).drop_duplicates()
    report("st1.0: the starter from what happened (training) + the as-of guard (test weeks)", paired(base, alt), base, alt,
           flagged)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", choices=["rt", "st"])
    ap.add_argument("--rows", type=Path, required=True)
    ap.add_argument("--rows-early", type=Path, default=None)
    ap.add_argument("--before", type=Path, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    rows = pd.read_parquet(args.rows)
    if args.rows_early is not None:
        rows = pd.concat([pd.read_parquet(args.rows_early), rows], ignore_index=True)
    rows["season"], rows["week"] = rows["season"].astype(int), rows["week"].astype(int)
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        leagues = P.league_scorings(conn)
    if args.candidate == "rt":
        run_rt(rows, leagues)
    else:
        if args.before is None:
            raise SystemExit("--before is required for st")
        run_st(rows, pd.read_parquet(args.before), leagues)


if __name__ == "__main__":
    main()
