"""IQ-1 (hotfix): rest-of-season quarterbacks -- the diagnosis and the horizon evaluation (docs/METRICS.md § "v3.5:
rest-of-season quarterbacks (IQ-1)"). Read only.

* ``diagnose``: 2026 as of week 5. The production component models (fit on 2016-2025), the market week's rows and the
  later weeks' rows as the mart builds them; then each group of inputs of the later rows replaced by the player's own
  market-week values (the betting line, the opponent, the personnel, the injury report, the week number) to see which
  group re-orders the board. Top 24 by the market-week projection; rank correlation with the mean of the later weeks.
* ``horizon``: seasons 2021-2025, one fit per season and position (2016..S-1, the production inputs), as of week W
  (W = 3, 5, 7, 9) the market week W+1 as the mart builds it and the later weeks T = W+2 .. W+8 the way the nightly builds
  a future week: the player's history as of W (his week-(W+1) row), the future game's opponent (its points allowed as of
  W) and home / away, no betting line, no injury report, the week number T. Scored against what happened in T:
  MAE and Spearman per season x W x T x position (weeks with >= 8 players who played), pooled over horizons 2-8.
  Candidates (``--candidates``): a = the line imputed from the team's own season so far; b = the opponent shrunk by
  games; c = the market week's line effect carried forward; ab = a and b.

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/iq1_horizon.py diagnose
       OMP_NUM_THREADS=1 uv run python scripts/analysis/iq1_horizon.py horizon [--positions QB,RB,WR,TE] [--candidates a,b,c,ab]
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

from league_lab import projections as P  # noqa: E402
from league_lab.config import get_settings  # noqa: E402
from league_lab.rankings import _spearman  # noqa: E402

log = logging.getLogger("iq1")
TESTS = (2021, 2022, 2023, 2024, 2025)
AS_OF = (3, 5, 7, 9)
H_MAX = 8
LINES = ["implied_team_total", "spread_line", "total_line"]
OPP = ["opp_allowed_std", "opp_allowed_l4", "opp_rank_std", "league_allowed_avg", "f_opp_allowed_diff"]
TEAM_SHRINK = 3.0      # (a): a team's season-so-far line is shrunk toward the league's by 3 games
OPP_SHRINK = 4.0       # (b): an opponent's points allowed is shrunk toward the league average by 4 games


def load(conn: psycopg.Connection, seasons: list[int]) -> pd.DataFrame:
    """The production frame plus ``opp_games`` (how many games the opponent's points allowed rest on)."""
    frame = P.load_frame(conn, seasons)
    og = pd.DataFrame(conn.execute("""select gsis_id, season, week, opp_games from analytics.mart_player_week_features
                                      where season = any(%s)""", (seasons,)).fetchall(), columns=["gsis_id", "season", "week", "opp_games"])
    og = og.astype({"season": frame["season"].dtype, "week": frame["week"].dtype})
    og["opp_games"] = pd.to_numeric(og["opp_games"], errors="coerce").astype(float)
    n = len(frame)
    frame = frame.merge(og, on=["gsis_id", "season", "week"], how="left", validate="one_to_one")
    assert len(frame) == n
    return frame


def fit(frame: pd.DataFrame, season: int, pos: str) -> tuple[dict, list[str]]:
    feats = list(P.FEATURES_BY_POSITION[pos])
    tr = frame[(frame["season"] < season)]
    d = tr[(tr["position"] == pos) & tr["played"] & ~tr["no_history"]]
    d = d.dropna(subset=[f"out_{c}" for c in P.COMPONENTS[pos]]).reset_index(drop=True)
    return P._fit_components(P._matrix(d, feats), d, pos), feats


def predict(models: dict, feats: list[str], rows: pd.DataFrame, scoring: dict[str, float]) -> np.ndarray:
    """The priced line. NaN stays NaN (``projections._matrix`` turns a column that is NaN in the whole batch into 0 --
    harmless for the nightly, whose batch is the whole season, but a batch of future weeks alone would read "no line"
    as an implied total of 0)."""
    x = rows[feats].to_numpy(dtype=float)
    comp = pd.DataFrame({f"proj_{c}": (np.clip(models[c].predict(x), 0, None) if c in models else 0.0) for c in P.ALL_COMPONENTS})
    comp["position"] = rows["position"].to_numpy()
    return P.price(comp, scoring, "proj_").to_numpy(dtype=float)


# ------------------------------------------------------------------------------ the future rows, as the nightly builds them
def opponent_asof(frame: pd.DataFrame, season: int, w: int) -> pd.DataFrame:
    """(position, opponent) -> the opponent features of the newest row at week <= w+1 where that team was the opponent
    (its points allowed through week w)."""
    s = frame[(frame["season"] == season) & (frame["week"] <= w + 1)].sort_values("week")
    return s.drop_duplicates(["position", "opponent"], keep="last").set_index(["position", "opponent"])[[*OPP, "opp_games"]]


def team_lines_asof(frame: pd.DataFrame, season: int, w: int) -> pd.DataFrame:
    """Per team: its mean implied total and game total over its games of weeks <= w, and how many (the line as the
    market set it before each game)."""
    s = frame[(frame["season"] == season) & (frame["week"] <= w) & frame["implied_team_total"].notna()]
    g = s.drop_duplicates(["team", "week"]).groupby("team")
    return pd.DataFrame({"imp": g["implied_team_total"].mean(), "tot": g["total_line"].mean(), "n": g.size()})


def future_rows(frame: pd.DataFrame, season: int, w: int, h_max: int = H_MAX) -> pd.DataFrame:
    """Rows for T = w+1 .. w+h_max: T = w+1 is the market week as the mart has it; later T copy the player's week-(w+1)
    row (history as of w) with T's opponent (as of w), home / away, the week number, and no line or injury report."""
    s = frame[frame["season"] == season]
    mkt = s[s["week"] == w + 1].set_index("gsis_id")
    opp = opponent_asof(frame, season, w)
    # the nightly's personnel for a week the schedule has not listed: the newest played game's (`last_start`), i.e. the
    # player's week-w row; the market week's own (the listing for w+1) kept as mkt_pn_* for candidate d
    pw = s[s["week"] == w].drop_duplicates("gsis_id").set_index("gsis_id")
    pn = list(P.QB_INPUTS)
    out = [mkt.reset_index().assign(target_week=w + 1, h=1, **{f"mkt_{c}": mkt[c].to_numpy() for c in pn})]
    for t in range(w + 2, w + h_max + 1):
        fut = s[(s["week"] == t) & s["gsis_id"].isin(mkt.index)]
        if fut.empty:
            continue
        base = mkt.loc[fut["gsis_id"]].reset_index()
        base["week"] = float(t)
        base["opponent"], base["f_home"] = fut["opponent"].to_numpy(), fut["f_home"].to_numpy()
        o = opp.reindex(pd.MultiIndex.from_arrays([base["position"], base["opponent"]]))
        for c in [*OPP, "opp_games"]:
            base[c] = np.where(o[c].notna(), o[c].to_numpy(dtype=float), fut[c].to_numpy(dtype=float))
        for c in LINES:
            base[c] = np.nan
        for c in pn:
            base[f"mkt_{c}"] = base[c].to_numpy()
            last = pw[c].reindex(base["gsis_id"]).to_numpy(dtype=float) if c in pw else np.full(len(base), np.nan)
            base[c] = np.where(pd.notna(last), last, base[c].to_numpy(dtype=float))
        base["questionable"] = 0.0
        base[[f"out_{c}" for c in P.ALL_COMPONENTS]] = fut[[f"out_{c}" for c in P.ALL_COMPONENTS]].to_numpy()
        base["played"] = fut["played"].to_numpy()
        out.append(base.assign(target_week=t, h=t - w))
    return pd.concat(out, ignore_index=True)


def impute_lines(rows: pd.DataFrame, lines: pd.DataFrame, k: float = TEAM_SHRINK) -> pd.DataFrame:
    """(a): a future week's line from the team's own season so far, shrunk toward the league by ``k`` games: implied
    total and game total; the spread (home team's view, as the frame keeps it) follows from them."""
    r = rows.copy()
    lg_imp, lg_tot = float(lines["imp"].mean()), float(lines["tot"].mean())
    t = lines.reindex(r["team"])
    n = t["n"].fillna(0).to_numpy()
    imp = (n * t["imp"].fillna(lg_imp).to_numpy() + k * lg_imp) / (n + k)
    tot = (n * t["tot"].fillna(lg_tot).to_numpy() + k * lg_tot) / (n + k)
    fut = r["h"].to_numpy() > 1
    home = r["f_home"].fillna(0).to_numpy() > 0
    r.loc[fut, "implied_team_total"] = imp[fut]
    r.loc[fut, "total_line"] = tot[fut]
    r.loc[fut, "spread_line"] = np.where(home, 2 * imp - tot, tot - 2 * imp)[fut]
    return r


def market_personnel(rows: pd.DataFrame) -> pd.DataFrame:
    """(d): the later weeks keep the market week's personnel inputs (the schedule's listed starter for it)."""
    r = rows.copy()
    for c in P.QB_INPUTS:
        if f"mkt_{c}" in r:
            r[c] = r[f"mkt_{c}"].to_numpy()
    return r


def shrink_opponent(rows: pd.DataFrame, k: float = OPP_SHRINK) -> pd.DataFrame:
    """(b): a future week's opponent: points allowed shrunk toward the league average by ``k`` games."""
    r = rows.copy()
    fut = r["h"].to_numpy() > 1
    g = r["opp_games"].fillna(0).to_numpy(dtype=float)
    lg = r["league_allowed_avg"].to_numpy(dtype=float)
    for c, cap in (("opp_allowed_std", None), ("opp_allowed_l4", 4.0)):
        gg = np.minimum(g, cap) if cap else g
        v = r[c].to_numpy(dtype=float)
        r.loc[fut, c] = ((gg * v + k * lg) / (gg + k))[fut]
    r.loc[fut, "f_opp_allowed_diff"] = (r["opp_allowed_std"] - r["league_allowed_avg"]).to_numpy()[fut]
    return r


# ------------------------------------------------------------------------------ scoring
def score(rows: pd.DataFrame, proj: np.ndarray, actual: np.ndarray) -> pd.DataFrame:
    d = rows[["season", "target_week", "h", "position", "gsis_id"]].assign(proj=proj, actual=actual)
    d = d[d["actual"].notna() & rows["played"].fillna(False).astype(bool).to_numpy()]
    out = []
    for (s, t, h, pos), g in d.groupby(["season", "target_week", "h", "position"]):
        if len(g) < 8:
            continue
        out.append({"season": s, "target_week": t, "h": h, "position": pos, "n": len(g),
                    "mae": float((g["proj"] - g["actual"]).abs().mean()), "spearman": _spearman(g["proj"], g["actual"])})
    return pd.DataFrame(out)


def horizon(positions: list[str], candidates: list[str]) -> None:
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        frame = load(conn, [s for s in P.available_seasons(conn) if s <= max(TESTS)])
        leagues = P.league_scorings(conn)
    frame["season"] = frame["season"].astype(int)
    known = frame[[f"out_{c}" for c in P.ALL_COMPONENTS]].notna().all(axis=1)
    scores = []
    for s in TESTS:
        for pos in positions:
            t0 = time.monotonic()
            models, feats = fit(frame, s, pos)
            for w in AS_OF:
                rows = future_rows(frame[frame["position"] == pos], s, w)
                rows = rows[rows["position"] == pos].reset_index(drop=True)
                lines = team_lines_asof(frame, s, w)
                ok = rows[[f"out_{c}" for c in P.ALL_COMPONENTS]].notna().all(axis=1)
                for lid, (_, sc) in leagues.items():
                    act = np.where(ok, P.price(rows.fillna({f"out_{c}": 0 for c in P.ALL_COMPONENTS}), sc, "out_"), np.nan)
                    variants = {"base": rows}
                    if "a" in candidates:
                        variants["a"] = impute_lines(rows, lines)
                    if "b" in candidates:
                        variants["b"] = shrink_opponent(rows)
                    if "d" in candidates:
                        variants["d"] = market_personnel(rows)
                    if "ad" in candidates:
                        variants["ad"] = market_personnel(impute_lines(rows, lines))
                    if "abd" in candidates:
                        variants["abd"] = market_personnel(shrink_opponent(impute_lines(rows, lines)))
                    preds = {k: predict(models, feats, v, sc) for k, v in variants.items()}
                    if "c" in candidates:      # the market week's line effect carried to the later weeks of the same player
                        mk = rows["h"] == 1
                        raw_mkt = rows[mk].assign(**{c: np.nan for c in LINES}, questionable=0.0)
                        eff = pd.Series(preds["base"][mk.to_numpy()] - predict(models, feats, raw_mkt, sc),
                                        index=rows.loc[mk, "gsis_id"].to_numpy())
                        eff = eff[~eff.index.duplicated()]
                        add = rows["gsis_id"].map(eff).fillna(0.0).to_numpy() * (rows["h"].to_numpy() > 1)
                        preds["c"] = preds["base"] + add
                    for k, p in preds.items():
                        sc_ = score(rows, p, act)
                        sc_["variant"], sc_["league_id"], sc_["as_of"] = k, lid, w
                        scores.append(sc_)
            log.info("%s %s: %.0f s", s, pos, time.monotonic() - t0)
    res = pd.concat(scores, ignore_index=True)
    res.to_parquet(os.environ.get("IQ1_OUT", "iq1_horizon.parquet"))
    report(res)
    del known


def stability(positions: list[str]) -> None:
    """The guard's floor: among the top 24 by the market-week projection, the rank correlation of that projection with the
    player's mean over the later weeks (h 2-8), per season x W, before (base) and with v3.5's inputs (ad)."""
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        frame = load(conn, [s for s in P.available_seasons(conn) if s <= max(TESTS)])
        leagues = P.league_scorings(conn)
    frame["season"] = frame["season"].astype(int)
    sc = next(iter(leagues.values()))[1]
    out = []
    for s in TESTS:
        for pos in positions:
            models, feats = fit(frame, s, pos)
            for w in AS_OF:
                rows = future_rows(frame[frame["position"] == pos], s, w)
                rows = rows[rows["position"] == pos].reset_index(drop=True)
                lines = team_lines_asof(frame, s, w)
                for v, r in (("base", rows), ("ad", market_personnel(impute_lines(rows, lines)))):
                    p = r.assign(p=predict(models, feats, r, sc))
                    mk = p[p["h"] == 1].drop_duplicates("gsis_id").set_index("gsis_id")["p"]
                    later = p[p["h"] > 1].groupby("gsis_id")["p"].mean()
                    top = mk.sort_values(ascending=False).head(24).index
                    top = [g for g in top if g in later.index]
                    out.append({"season": s, "position": pos, "as_of": w, "variant": v,
                                "corr": float(mk[top].rank().corr(later[top].rank()))})
    d = pd.DataFrame(out)
    print("\n### Top-24 rank correlation, market week vs the later weeks' mean (reference scoring)\n")
    print(d.groupby(["position", "variant"])["corr"].describe()[["mean", "min", "25%", "50%"]].round(2).to_string())


def report(res: pd.DataFrame) -> None:
    # per season x position x variant: horizon 1 and pooled horizons 2-8 (cells averaged over the leagues, W and T)
    m = res.groupby(["variant", "position", "season", "h"])[["mae", "spearman"]].mean().reset_index()
    print("\n### By horizon (base: the nightly's future weeks today), seasons 2021-2025 averaged\n")
    b = m[m["variant"] == "base"].groupby(["position", "h"])[["mae", "spearman"]].mean().unstack("position")
    print(b.round(3).to_string())
    pooled = m[m["h"] >= 2].groupby(["variant", "position", "season"])[["mae", "spearman"]].mean().reset_index()
    print("\n### Pooled horizons 2-8, by season (MAE / Spearman)\n")
    for pos, g in pooled.groupby("position"):
        t = g.pivot(index="season", columns="variant", values=["mae", "spearman"])
        print(f"\n{pos}\n" + t.round(3).to_string())
    if "base" in set(pooled["variant"]):
        base = pooled[pooled["variant"] == "base"].set_index(["position", "season"])
        print("\n### Candidates against base, pooled horizons 2-8\n")
        print("| candidate | position | Δ MAE by season | Δ MAE mean | seasons lower | Δ Spearman mean | seasons not lower |")
        print("|---|---|---|---|---|---|---|")
        for (v, pos), g in pooled[pooled["variant"] != "base"].groupby(["variant", "position"]):
            g = g.set_index(["position", "season"])
            dm = g["mae"] - base.loc[g.index, "mae"]
            ds = g["spearman"] - base.loc[g.index, "spearman"]
            print(f"| {v} | {pos} | {' / '.join(f'{x:+.3f}' for x in dm)} | {dm.mean():+.3f} | {int((dm < 0).sum())} | "
                  f"{ds.mean():+.4f} | {int((ds >= 0).sum())} |")


# ------------------------------------------------------------------------------ the 2026 diagnosis
def diagnose() -> None:
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        seasons = P.available_seasons(conn)
        frame = load(conn, seasons)
        leagues = P.league_scorings(conn)
        ref = next(iter(leagues))
        stored = pd.DataFrame(conn.execute(
            """select gsis_id, week, proj_points from ops.projections where league_id = %s and season = 2026 and position = 'QB'""",
            (ref,)).fetchall(), columns=["gsis_id", "week", "stored"])
    frame["season"] = frame["season"].astype(int)
    sc = leagues[ref][1]
    models, feats = fit(frame, 2026, "QB")
    s = frame[(frame["season"] == 2026) & (frame["position"] == "QB")]
    mkt = s[s["week"] == 5].set_index("gsis_id")
    fut = s[(s["week"] >= 6) & s["gsis_id"].isin(mkt.index)].copy()
    groups = {"the betting line": LINES, "the opponent": OPP, "the personnel (pn_qb_*)": list(P.QB_INPUTS),
              "the injury report": ["questionable"], "the week number": ["week"]}
    mk = predict(models, feats, mkt.reset_index(), sc)
    mkt_proj = pd.Series(mk, index=mkt.index)
    st = stored[stored["week"] == 5].set_index("gsis_id")["stored"]
    top = st.sort_values(ascending=False).head(24).index
    rows = []

    def summary(name, f):
        p = pd.Series(predict(models, feats, f, sc), index=f.index)
        later = f.assign(p=p.to_numpy()).groupby("gsis_id")["p"].mean()
        t = [g for g in top if g in later.index]
        rows.append({"later weeks as": name, "rank corr. with week 5 (stored, top 24)": round(float(pd.Series(st[t]).rank().corr(later[t].rank())), 2),
                     "rank corr. with week 5 (model, no pt1.0)": round(float(mkt_proj[t].rank().corr(later[t].rank())), 2),
                     "mean later − week 5 (top 24)": round(float((later[t] - mkt_proj[t]).mean()), 2),
                     "sd of later − week 5": round(float((later[t] - mkt_proj[t]).std()), 2)})
    summary("the mart's rows (today)", fut.reset_index(drop=True))
    for name, cols in groups.items():
        f = fut.copy()
        for c in cols:
            f[c] = mkt[c].reindex(f["gsis_id"]).to_numpy() if c != "week" else 5.0
        summary(f"… with week 5's {name}", f.reset_index(drop=True))
    f = fut.copy()
    for c in [*LINES, *OPP]:
        f[c] = mkt[c].reindex(f["gsis_id"]).to_numpy()
    summary("… with week 5's line and opponent", f.reset_index(drop=True))
    f = fut.copy()
    for c in feats:
        f[c] = mkt[c].reindex(f["gsis_id"]).to_numpy()
    summary("… with every week-5 input (control: the week-5 model number)", f.reset_index(drop=True))
    print("\n### 2026 as of week 5: QB top 24 by the stored week-5 projection\n")
    print(pd.DataFrame(rows).to_string(index=False))
    names = s.drop_duplicates("gsis_id").set_index("gsis_id")["player_name"]
    later = stored[stored["week"] >= 6].groupby("gsis_id")["stored"].mean()
    t = pd.DataFrame({"name": names.reindex(top), "week 5 stored": st[top].round(1), "week 5 model (no pt1.0)": mkt_proj.reindex(top).round(1),
                      "weeks 6-18 stored mean": later.reindex(top).round(1)})
    print("\n" + t.to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["diagnose", "horizon", "stability"])
    ap.add_argument("--positions", default="QB,RB,WR,TE")
    ap.add_argument("--candidates", default="")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.mode == "diagnose":
        diagnose()
    elif args.mode == "stability":
        stability(args.positions.split(","))
    else:
        horizon(args.positions.split(","), [c for c in args.candidates.split(",") if c])


if __name__ == "__main__":
    main()
