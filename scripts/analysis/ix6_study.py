"""IX-6 (Wave I-X), lf2.0: does handling a shortened game make the projection better? (docs/METRICS.md § "Does
handling a shortened game make the projection better?"; the rule was committed before this script ran: 1e098e0).

    uv run python scripts/analysis/ix6_study.py frame CAND OUT      # dbt with var lf_candidate=CAND (base: none), the frame
    uv run python scripts/analysis/ix6_study.py backtest FRAME OUT  # walk-forward 2021-2025, component models, Half PPR
    uv run python scripts/analysis/ix6_study.py grade DIR           # the table and the rule's verdict

The walk-forward is ``projections.walk_forward``'s loop with only the component models fitted (the projected points
are the priced component predictions: the backtest's ``proj_points``). Reads and writes on its own connection.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TEST_SEASONS = [2021, 2022, 2023, 2024, 2025]
MODELS = "mart_player_recent_form+,+mart_player_week_features"


def frame(cand: str, out: str) -> None:
    from league_lab import projections as P
    from league_lab.db import connect

    args = ["uv", "run", "league-lab", "dbt", "run", "--select", MODELS]
    if cand != "base":
        args += ["--vars", f"{{lf_candidate: {cand}}}"]
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    done = [ln for ln in r.stdout.splitlines() if "Done." in ln or "ERROR" in ln]
    print(cand, done[-1] if done else r.stdout[-400:])
    if r.returncode:
        raise SystemExit(r.stdout[-2000:])
    with connect() as conn:
        seasons = [s for s in P.available_seasons(conn) if s <= max(TEST_SEASONS)]
        df = P.load_frame(conn, seasons)
    df.to_pickle(out)


def half_ppr():
    from league_lab import projections as P
    from league_lab.db import connect

    with connect() as conn:
        refs = P.reference_scorings(conn)
    key = next(k for k in refs if "half" in k.lower())
    return key, refs[key][1]


def backtest(frame_path: str, out: str) -> None:
    from league_lab import projections as P

    key, scoring = half_ppr()
    df = pd.read_pickle(frame_path)
    first = int(df["season"].min())
    rows = []
    for n in TEST_SEASONS:
        train = df[(df["season"] >= first) & (df["season"] < n)]
        test = df[(df["season"] == n) & df["played"]]
        for pos in P.POSITIONS:
            feats = list(P.FEATURES_BY_POSITION[pos])
            d = train[(train["position"] == pos) & train["played"] & ~train["no_history"]]
            d = d.dropna(subset=[f"out_{c}" for c in P.COMPONENTS[pos]]).reset_index(drop=True)
            models = P._fit_components(P._matrix(d, feats), d, pos)
            t = test[test["position"] == pos].dropna(subset=[f"out_{c}" for c in P.ALL_COMPONENTS])
            if t.empty:
                continue
            o = t[["gsis_id", "season", "week", "position"]].copy()
            o["proj_points"] = P._price_models(models, P._matrix(t, feats), scoring, pos)
            o["points"] = P.price(t, scoring, "out_", pos).to_numpy(dtype=float)
            rows.append(o)
        print(n, "scored", flush=True)
    res = pd.concat(rows, ignore_index=True)
    res.attrs["scoring"] = key
    res.to_pickle(out)


def marks() -> pd.DataFrame:
    from league_lab.db import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute("""select gsis_id, season, week, left_early_a, left_early_b from intermediate.int_player_game_on_field
                       where season_type = 'REG' and season between 2016 and 2025""")
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def affected(res: pd.DataFrame, m: pd.DataFrame, mark: str) -> pd.Series:
    """A player's next three games played after a game marked ``mark`` (a / b), the same season."""
    hit = m[m[f"left_early_{mark}"]][["gsis_id", "season", "week"]].rename(columns={"week": "mark_week"})
    played = res[["gsis_id", "season", "week"]].drop_duplicates().sort_values(["gsis_id", "season", "week"])
    j = played.merge(hit, on=["gsis_id", "season"])
    j = j[j["week"] > j["mark_week"]].sort_values(["gsis_id", "season", "mark_week", "week"])
    j["rank"] = j.groupby(["gsis_id", "season", "mark_week"]).cumcount()
    keys = j[j["rank"] < 3][["gsis_id", "season", "week"]].drop_duplicates()
    flag = res[["gsis_id", "season", "week"]].merge(keys.assign(_a=True), how="left", on=["gsis_id", "season", "week"])
    return flag["_a"].fillna(False).astype(bool).to_numpy()


def _order(r: pd.DataFrame) -> pd.Series:
    from league_lab import projections as P

    out = {}
    for pos, g in r.groupby("position"):
        vals = [P._spearman(w["proj_points"], w["points"]) for _, w in g.groupby(["season", "week"]) if len(w) >= 8]
        out[pos] = float(np.nanmean(vals))
    return pd.Series(out)


def grade(d: str) -> None:
    base = pd.read_pickle(f"{d}/bt_base.pkl")
    m = marks()
    key = ["gsis_id", "season", "week", "position"]
    base_mae = (base["proj_points"] - base["points"]).abs().groupby(base["position"]).mean()
    base_order = _order(base)
    print(f"scoring: {base.attrs.get('scoring')}; rows {len(base)}")
    print("baseline, all rows: MAE", base_mae.round(4).to_dict(), "order", base_order.round(4).to_dict())
    lines = []
    for cand in ("p2a", "p2b", "p1a", "p1b", "p3a", "p3b"):
        p = Path(f"{d}/bt_{cand}.pkl")
        if not p.exists():
            lines.append({"candidate": cand, "status": "not run"})
            continue
        c = pd.read_pickle(p).merge(base[key + ["proj_points"]].rename(columns={"proj_points": "base_points"}), on=key)
        aff = affected(c, m, cand[-1])
        e_c = (c["proj_points"] - c["points"]).abs()
        e_b = (c["base_points"] - c["points"]).abs()
        seasons = {int(s): (float(e_c[aff & (c["season"] == s)].mean()), float(e_b[aff & (c["season"] == s)].mean()),
                            int((aff & (c["season"] == s)).sum())) for s in TEST_SEASONS}
        better = sum(1 for v in seasons.values() if v[0] < v[1])
        gain = 1 - e_c[aff].mean() / e_b[aff].mean()
        mae = e_c.groupby(c["position"]).mean()
        order = _order(c)
        worse = (mae - base_mae).max()
        lower = (base_order - order).max()
        ok = gain >= 0.03 and better >= 4 and worse <= 0.005 and lower <= 0.002
        lines.append({"candidate": cand, "affected": int(aff.sum()), "mae_aff": round(e_c[aff].mean(), 4),
                      "base_mae_aff": round(e_b[aff].mean(), 4), "gain": round(gain, 4), "seasons_better": better,
                      "max_mae_worse": round(worse, 4), "max_order_lower": round(lower, 4), "passes": ok,
                      "per_season": {s: (round(a, 3), round(b, 3), n) for s, (a, b, n) in seasons.items()},
                      "mae_by_pos": mae.round(4).to_dict(), "order_by_pos": order.round(4).to_dict()})
    t = pd.DataFrame(lines)
    with pd.option_context("display.width", 250, "display.max_colwidth", 120):
        print(t.drop(columns=[c for c in ("per_season", "mae_by_pos", "order_by_pos") if c in t]).to_string(index=False))
        for r in lines:
            if r.get("per_season"):
                print(r["candidate"], "per season (cand, base, n):", r["per_season"])
                print("   MAE by pos:", r["mae_by_pos"], " order by pos:", r["order_by_pos"])
    ran = t[t["status"].isna()] if "status" in t else t
    if ran.empty:
        print("verdict: nothing run")
        return
    best = ran.sort_values("mae_aff").iloc[0]          # the rule: the lowest error on its affected rows, then the test
    print(f"lowest error on its affected rows: {best['candidate']}; "
          f"verdict: {'ships' if bool(best['passes']) else 'does not pass: nothing ships'}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "frame":
        frame(sys.argv[2], sys.argv[3])
    elif cmd == "backtest":
        backtest(sys.argv[2], sys.argv[3])
    elif cmd == "grade":
        grade(sys.argv[2])
