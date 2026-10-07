"""IP-1 (Wave I-P): the quarterback weak spot -- is "6.5 points off, against 5.4" a signal, and where do the misses come
from? Reproduces every table of docs/METRICS.md § "The quarterback weak spot (IP-1)" from the database.

What it reads (nothing is written to the database):
* the 2026 board as it was scored (``ops.projections`` joined to ``analytics.mart_player_week_projections``: played,
  rankable, the reference league's scoring -- exactly the rows ``projections.drift`` scores);
* the walk-forward point projection per player-week (the component models of ``fit_position``, production training
  filter, 2016..S-1 -> S, S = 2021..2026), once with v2.0's inputs (``FEATURES``) and once with v3.0's
  (``FEATURES_BY_POSITION``) -- what ``backtest-v2`` grades, row by row (checked against ``ops.projection_backtest``);
* the play-by-play (designed runs vs scrambles), the schedule (starters, scores, head coaches), ``dim_player``.

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/ip1_qb_diagnosis.py [--rows rows.parquet] [--positions QB,TE]
       (--rows: a cache of the walk-forward rows; built and saved there when the file does not exist, ~2 min alone)
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

from league_lab import calibration as C  # noqa: E402
from league_lab import projections as P  # noqa: E402
from league_lab.config import get_settings  # noqa: E402
from league_lab.rankings import _spearman  # noqa: E402

log = logging.getLogger("ip1")
TESTS = [2021, 2022, 2023, 2024, 2025, 2026]
BOOT = 4000
META = ["gsis_id", "season", "week", "position", "player_name", "team", "opponent", "played", "no_history",
        "report_status", "roster_status", "games_to_date", "prev_games", "implied_team_total", "spread_line", "total_line",
        "f_home", "prev_ppg", "ppg_std", "rushing_yards_pg_std", "rushing_tds_pg_std", "prev_rushing_yards_pg",
        "prev_rushing_tds_pg", *P.QB_INPUTS, *[f"out_{c}" for c in P.ALL_COMPONENTS]]


# ------------------------------------------------------------------------------ rows
def walk_forward_rows(conn: psycopg.Connection, positions: list[str], tests: list[int] = TESTS) -> pd.DataFrame:
    """Per test season S and position: the component models fitted on 2016..S-1 (``fit_position``'s training filter),
    v2.0 inputs (``v2_<component>``) and v3.0 inputs (``v3_<component>``), applied to every row of S."""
    seasons = P.available_seasons(conn)
    frame = P.load_frame(conn, [s for s in seasons if s <= max(tests)])
    first = min(seasons)
    parts = []
    for s in tests:
        train, test = frame[(frame["season"] >= first) & (frame["season"] < s)], frame[frame["season"] == s]
        for pos in positions:
            d = train[(train["position"] == pos) & train["played"] & ~train["no_history"]]
            d = d.dropna(subset=[f"out_{c}" for c in P.COMPONENTS[pos]]).reset_index(drop=True)
            rows = test[test["position"] == pos].reset_index(drop=True)
            meta = rows[[c for c in META if c in rows.columns]].copy()
            for tag, feats in (("v2", list(P.FEATURES)), ("v3", list(P.FEATURES_BY_POSITION[pos]))):
                t0 = time.monotonic()
                models = P._fit_components(P._matrix(d, feats), d, pos)
                x = P._matrix(rows, feats)
                for c in P.ALL_COMPONENTS:
                    meta[f"{tag}_{c}"] = np.clip(models[c].predict(x), 0, None) if c in models else 0.0
                log.info("%s %s %s: %s training rows, %.0f s", s, pos, tag, len(d), time.monotonic() - t0)
            meta["train_seasons"] = f"{first}-{s - 1}"
            parts.append(meta)
    return pd.concat(parts, ignore_index=True)


def q(conn: psycopg.Connection, sql: str, args: tuple = ()) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


BOARD_SQL = """select m.league_id, m.season, m.week, m.position, m.gsis_id, m.player_name, m.team, m.opponent, m.game_id,
                      m.played, m.is_rankable, m.points_actual, p.model_version, p.frozen_source,
                      round(p.proj_points::numeric, 2) as proj_points, round(p.p10::numeric, 2) as p10,
                      round(p.p90::numeric, 2) as p90, {comps}
               from analytics.mart_player_week_projections as m
               join ops.projections as p using (league_id, season, week, gsis_id)
               where m.season = %s and m.position = any(%s) and m.league_id = %s"""

RUSH_SQL = """select season, week, rusher_player_id as gsis_id,
                     coalesce(sum(rushing_yards) filter (where is_scramble), 0)::float8 as scr_yards,
                     coalesce(sum(rushing_yards) filter (where not is_scramble and not is_kneel), 0)::float8 as des_yards,
                     coalesce(sum(rushing_yards) filter (where is_kneel), 0)::float8 as kneel_yards,
                     coalesce(sum(rush_touchdown::int) filter (where is_scramble), 0)::float8 as scr_tds,
                     coalesce(sum(rush_touchdown::int) filter (where not is_scramble), 0)::float8 as des_tds,
                     count(*) filter (where is_scramble)::float8 as scrambles,
                     count(*) filter (where not is_scramble and not is_kneel)::float8 as designed
              from analytics.fct_play
              where season_type = 'REG' and is_rush_attempt and not is_no_play and rusher_player_id is not null
              group by 1, 2, 3"""

GAME_SQL = """select g.game_id, g.season, g.week, g.home_team, g.away_team, g.home_score, g.away_score, g.home_qb_id,
                     g.away_qb_id, g.spread_line as g_spread, s.home_coach, s.away_coach
              from analytics.dim_game as g left join raw.nfl_schedules as s using (game_id)
              where g.season_type = 'REG'"""


def team_game_frame(games: pd.DataFrame) -> pd.DataFrame:
    """One row per team x game: points scored and allowed, the starting QB, the head coach, and whether the head
    coach differs from the team's previous season's last coach (a stand-in for a new play-caller)."""
    h = games.rename(columns={"home_team": "team", "home_score": "pts", "away_score": "opp_pts", "home_qb_id": "start_qb",
                              "home_coach": "coach"})[["game_id", "season", "week", "team", "pts", "opp_pts", "start_qb", "coach"]]
    a = games.rename(columns={"away_team": "team", "away_score": "pts", "home_score": "opp_pts", "away_qb_id": "start_qb",
                              "away_coach": "coach"})[["game_id", "season", "week", "team", "pts", "opp_pts", "start_qb", "coach"]]
    t = pd.concat([h, a], ignore_index=True).sort_values(["team", "season", "week"])
    last = t.groupby(["team", "season"])["coach"].last().rename("prev_coach").reset_index()
    last["season"] = last["season"] + 1
    t = t.merge(last, on=["team", "season"], how="left")
    t["new_coach"] = (t["prev_coach"].notna() & (t["coach"] != t["prev_coach"])).astype(float)
    t.loc[t["prev_coach"].isna(), "new_coach"] = np.nan
    return t


def career_starts_before(rows: pd.DataFrame, tg: pd.DataFrame) -> np.ndarray:
    """Games he started at QB (schedule's starter) strictly before the row's week, 2016 on."""
    st = tg.dropna(subset=["start_qb", "pts"]).rename(columns={"start_qb": "gsis_id"})[["gsis_id", "season", "week"]]
    return C.career_games_before(rows, st)


def add_context(conn: psycopg.Connection, r: pd.DataFrame) -> pd.DataFrame:
    """Kinds of quarterback, game script and the run split on every row (played or not)."""
    games = q(conn, GAME_SQL)
    tg = team_game_frame(games)
    hist = q(conn, C.TEAM_GAMES_SQL)
    draft = q(conn, C.DRAFT_SQL)
    out = r.copy()
    out["season"], out["week"] = out["season"].astype(int), out["week"].astype(int)
    out = out.merge(tg[["season", "week", "team", "pts", "opp_pts", "start_qb", "new_coach"]], on=["season", "week", "team"], how="left")
    out["started"] = (out["start_qb"] == out["gsis_id"]).astype(float)
    out.loc[out["start_qb"].isna(), "started"] = np.nan
    out = C.history_columns(out, hist, draft)
    out["career_starts"] = career_starts_before(out, tg)
    dp = draft.drop_duplicates("gsis_id").set_index("gsis_id")
    out["rookie"] = (out["gsis_id"].map(dp["rookie_season"]) == out["season"]).astype(float)
    rush = q(conn, RUSH_SQL)
    out = out.merge(rush, on=["season", "week", "gsis_id"], how="left")
    # his rushing share of points before the week: this season's per-game rates from 3 games, else last season's
    rsh_s = (0.1 * out["rushing_yards_pg_std"] + 6 * out["rushing_tds_pg_std"]) / out["ppg_std"]
    rsh_p = (0.1 * out["prev_rushing_yards_pg"] + 6 * out["prev_rushing_tds_pg"]) / out["prev_ppg"]
    share = np.where(out["games_to_date"].fillna(0) >= 3, rsh_s, rsh_p)
    out["rush_share"] = pd.Series(share, index=out.index).where(lambda s: np.isfinite(s))
    out["script"] = out["pts"] - out["implied_team_total"]
    return out


def price_cols(df: pd.DataFrame, prefix: str, scoring: dict[str, float]) -> pd.Series:
    return P.price(df, scoring, prefix)


# ------------------------------------------------------------------------------ statistics
def cluster_boot(err: np.ndarray, groups: np.ndarray, stat=np.mean, n: int = BOOT, seed: int = 0) -> tuple[float, float]:
    """95% interval of ``stat(err)`` resampling whole players (every week of a resampled player comes along)."""
    rng = np.random.default_rng(seed)
    codes, uniq = pd.factorize(groups)
    idx = [np.flatnonzero(codes == k) for k in range(len(uniq))]
    vals = np.empty(n)
    for b in range(n):
        pick = rng.integers(0, len(idx), len(idx))
        vals[b] = stat(err[np.concatenate([idx[k] for k in pick])])
    return float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))


def weekly_mae(d: pd.DataFrame, proj: str, actual: str = "actual", min_players: int = 8) -> pd.DataFrame:
    rows = []
    for (s, w), g in d.groupby(["season", "week"]):
        if len(g) < min_players:
            continue
        rows.append({"season": s, "week": w, "n": len(g), "mae": float((g[proj] - g[actual]).abs().mean()),
                     "spearman": _spearman(g[proj], g[actual])})
    return pd.DataFrame(rows)


def fmt(x: float | None, d: int = 2) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+.{d}f}" if d < 0 else f"{x:.{d}f}"


def sgn(x: float, d: int = 2) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+.{d}f}"


def md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


# ------------------------------------------------------------------------------ the tables
def signal_table(board: pd.DataFrame, rows: pd.DataFrame, pos: str, stored_bt: pd.DataFrame) -> tuple[str, dict]:
    """Is the 2026 number a signal: the board's weeks with a player-cluster interval, next to every backtest season's
    weeks 1-3 (v2.0 and v3.0 inputs, the drift's scope: played and rankable) and the whole season."""
    out, facts = [], {}
    b = board[(board["position"] == pos) & (board["week"] <= 3)]
    err = (b["proj_points"] - b["actual"]).abs().to_numpy()
    wk = weekly_mae(b, "proj_points")
    lo, hi = cluster_boot(err, b["gsis_id"].to_numpy())
    facts["board"] = (float(wk["mae"].mean()), float(err.mean()), lo, hi, len(b))
    out.append({"rows": f"2026 wk 1–3, the board as scored (model {', '.join(sorted(b['model_version'].unique()))})",
                "player-weeks": len(b), "MAE (mean of weeks)": fmt(wk["mae"].mean()), "MAE pooled": fmt(err.mean()),
                "95% interval (players resampled)": f"{lo:.2f}–{hi:.2f}", "weekly": " / ".join(f"{v:.2f}" for v in wk["mae"])})
    for tag in ("v2", "v3"):
        r = rows[(rows["position"] == pos) & rows["scored"]]
        for s in TESTS:
            for label, sel in (("wk 1–3", r["week"] <= 3), ("all weeks", r["week"] > 0)):
                if s == 2026 and label == "all weeks":
                    continue
                d = r[(r["season"] == s) & sel]
                if d.empty:
                    continue
                e = (d[f"{tag}_points"] - d["actual"]).abs().to_numpy()
                w = weekly_mae(d, f"{tag}_points")
                lo, hi = cluster_boot(e, d["gsis_id"].to_numpy(), n=1000) if label == "wk 1–3" else (np.nan, np.nan)
                facts[(tag, s, label)] = (float(w["mae"].mean()), float(e.mean()), lo, hi, len(d))
                out.append({"rows": f"{s} {label}, {'v2.0' if tag == 'v2' else 'v3.0'} inputs" + (" (refit now)" if s == 2026 else ""),
                            "player-weeks": len(d), "MAE (mean of weeks)": fmt(w["mae"].mean()), "MAE pooled": fmt(e.mean()),
                            "95% interval (players resampled)": "" if label != "wk 1–3" else f"{lo:.2f}–{hi:.2f}",
                            "weekly": "" if label != "wk 1–3" else " / ".join(f"{v:.2f}" for v in w["mae"])})
    t = pd.DataFrame(out)
    # the reproduction check: our v3.0 rows on every played row (the backtest's scope) vs the stored record
    chk = []
    for tag, mv in (("v2", "v2.0"), ("v3", "v3.0")):
        r = rows[(rows["position"] == pos) & rows["bt_scope"] & (rows["season"] < 2026)]
        w = weekly_mae(r, f"{tag}_points")
        sb = stored_bt[(stored_bt["model_version"] == mv) & (stored_bt["position"] == pos)]
        m = w.merge(sb, on=["season", "week"], suffixes=("", "_stored"))
        chk.append(f"{mv}: {len(m)} weeks matched, max |ΔMAE| {float((m['mae'] - m['mae_stored']).abs().max()):.4f}, "
                   f"max |Δn| {int((m['n'] - m['n_stored']).abs().max())}")
    facts["check"] = chk
    return md(t), facts


def diff_interval(board: pd.DataFrame, rows: pd.DataFrame, pos: str, tag: str) -> tuple[float, float, float, float]:
    """2026 board weeks 1-3 minus the backtest's weeks 1-3 (2021-2025, the same inputs), pooled MAE, players resampled
    on both sides independently: (difference, lo, hi, share of resamples where 2026 is worse)."""
    b = board[(board["position"] == pos) & (board["week"] <= 3)]
    r = rows[(rows["position"] == pos) & rows["scored"] & (rows["week"] <= 3) & (rows["season"] < 2026)]
    e1, g1 = (b["proj_points"] - b["actual"]).abs().to_numpy(), b["gsis_id"].to_numpy()
    e0 = (r[f"{tag}_points"] - r["actual"]).abs().to_numpy()
    g0 = (r["gsis_id"] + "_" + r["season"].astype(str)).to_numpy()
    rng = np.random.default_rng(1)

    def groups(g):
        codes, u = pd.factorize(g)
        return [np.flatnonzero(codes == k) for k in range(len(u))]
    i1, i0 = groups(g1), groups(g0)
    d = np.empty(BOOT)
    for k in range(BOOT):
        a = e1[np.concatenate([i1[j] for j in rng.integers(0, len(i1), len(i1))])].mean()
        c = e0[np.concatenate([i0[j] for j in rng.integers(0, len(i0), len(i0))])].mean()
        d[k] = a - c
    return float(e1.mean() - e0.mean()), float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975)), float((d > 0).mean())


def component_table(d: pd.DataFrame, proj_prefix: str, scoring: dict[str, float], comps: list[str], label: str) -> pd.DataFrame:
    """Per component, in the scoring's points: bias = mean(actual - projected), MAE of the component, and the change in
    the line's MAE when that component alone is replaced by what happened (how much of the miss it carries)."""
    w = P.unit_points(scoring)
    tot = d["actual"] - d[f"{proj_prefix}points"]
    base = float(tot.abs().mean())
    out = []
    for c in comps:
        e = (d[f"out_{c}"] - d[f"{proj_prefix}{c}"]) * w[c]
        fixed = (tot - e).abs().mean()
        out.append({"rows": label, "component": P.COMPONENT_LABELS[c], "bias (pts)": sgn(e.mean()),
                    "MAE (pts)": fmt(e.abs().mean()), "line's MAE if it were exact": f"{fixed:.2f} ({fixed - base:+.2f})"})
    out.append({"rows": label, "component": "**the line**", "bias (pts)": sgn(tot.mean()), "MAE (pts)": fmt(base),
                "line's MAE if it were exact": "0"})
    return pd.DataFrame(out)


def kind_table(d: pd.DataFrame, proj: str, kinds: dict[str, pd.Series], label: str) -> pd.DataFrame:
    """Per kind: n, bias (actual - projected) with a player-clustered 95% interval, MAE, and the bias's share of the
    kind's mean squared error."""
    out = []
    for name, sel in kinds.items():
        g = d[sel.reindex(d.index).fillna(False).astype(bool)]
        if len(g) < 5:
            out.append({"rows": label, "kind": name, "n": len(g), "bias": "—", "95% interval": "", "MAE": "—", "bias² / MSE": ""})
            continue
        e = (g["actual"] - g[proj]).to_numpy()
        lo, hi = cluster_boot(e, g["gsis_id"].astype(str).to_numpy() + g["season"].astype(str).to_numpy(), n=1000)
        out.append({"rows": label, "kind": name, "n": len(g), "bias": sgn(e.mean()), "95% interval": f"{lo:+.2f} to {hi:+.2f}",
                    "MAE": fmt(np.abs(e).mean()), "bias² / MSE": f"{e.mean() ** 2 / np.mean(e ** 2):.0%}"})
    return pd.DataFrame(out)


def qb_kinds(d: pd.DataFrame) -> dict[str, pd.Series]:
    rs = d["rush_share"]
    return {
        "all": pd.Series(True, index=d.index),
        "started, and was the projected starter": (d["started"] == 1) & (d["pn_qb_starting"] == 1),
        "started, projected NOT to start (v3's input said no)": (d["started"] == 1) & (d["pn_qb_starting"] != 1),
        "did not start (came off the bench)": d["started"] == 0,
        "rushing share < 15% of his points": (rs < 0.15) & (d["started"] == 1),
        "rushing share 15–30%": (rs >= 0.15) & (rs < 0.30) & (d["started"] == 1),
        "rushing share ≥ 30%": (rs >= 0.30) & (d["started"] == 1),
        "rushing share unknown (no history)": rs.isna() & (d["started"] == 1),
        "new starter (< 8 career starts), started": (d["career_starts"] < 8) & (d["started"] == 1),
        "veteran starter (≥ 8 starts), started": (d["career_starts"] >= 8) & (d["started"] == 1),
        "rookie, started": (d["rookie"] == 1) & (d["started"] == 1),
        "new team (< 3 games with it), started": (d["new_team"]) & (d["started"] == 1),
        "new head coach this season, started": (d["new_coach"] == 1) & (d["started"] == 1),
    }


def script_kinds(d: pd.DataFrame) -> dict[str, pd.Series]:
    s = d["script"]
    st = d["started"] == 1
    it = d["implied_team_total"]
    return {
        "team scored ≥ 7 under its implied total": st & (s <= -7),
        "3–7 under": st & (s > -7) & (s <= -3),
        "within 3": st & (s > -3) & (s < 3),
        "3–7 over": st & (s >= 3) & (s < 7),
        "≥ 7 over": st & (s >= 7),
        "implied total < 20 (known before)": st & (it < 20),
        "implied total 20–24": st & (it >= 20) & (it < 24),
        "implied total ≥ 24": st & (it >= 24),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=Path, default=None)
    ap.add_argument("--positions", default="QB,TE")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    positions = args.positions.split(",")
    s = get_settings()
    with psycopg.connect(s.pipeline_dsn()) as conn:
        conn.read_only = True
        leagues = P.league_scorings(conn)
        ref = next(iter(leagues))
        scoring = leagues[ref][1]
        if args.rows is not None and args.rows.exists():
            rows = pd.read_parquet(args.rows)
        else:
            rows = walk_forward_rows(conn, positions)
            if args.rows is not None:
                rows.to_parquet(args.rows)
        rows = rows[rows["position"].isin(positions)].reset_index(drop=True)
        comps = [f"proj_{c}" for c in P.ALL_COMPONENTS]
        board = q(conn, BOARD_SQL.format(comps=", ".join(f"p.{c}" for c in comps)), (2026, positions, ref))
        for c in ["proj_points", "p10", "p90", "points_actual", *comps]:
            board[c] = pd.to_numeric(board[c], errors="coerce").astype(float)
        board = board[board["played"].fillna(False) & board["is_rankable"].fillna(False) & board["points_actual"].notna()]
        board = board.rename(columns={"points_actual": "actual"})
        stored_bt = q(conn, """select model_version, position, season, week, n_players as n_stored, mae as mae_stored
                               from ops.projection_backtest where scorer = 'v2_points' and league_id = %s""", (ref,))
        stored_bt["mae_stored"] = stored_bt["mae_stored"].astype(float)
        # the rows' prices and scopes
        for tag in ("v2", "v3"):
            rows[f"{tag}_points"] = P.price(rows.assign(**{f"proj_{c}": rows[f"{tag}_{c}"] for c in P.ALL_COMPONENTS}), scoring, "proj_")
        known = rows[[f"out_{c}" for c in P.ALL_COMPONENTS]].notna().all(axis=1) & rows["played"].fillna(False).astype(bool)
        rows["actual"] = np.nan
        rows.loc[known, "actual"] = P.price(rows[known], scoring, "out_").to_numpy()
        rankable = (~rows["report_status"].isin(["Out", "Doubtful"])) & (rows["roster_status"].fillna("") != "RES")
        rows["bt_scope"] = known                    # backtest-v2's scope: every played row
        rows["scored"] = known & rankable           # the drift's scope: played and rankable
        rows = add_context(conn, rows)
        board_ctx = add_context(conn, board.merge(rows[rows["season"] == 2026][[c for c in META if c in rows.columns and c not in board.columns] + ["gsis_id", "week"]],
                                                  on=["gsis_id", "week"], how="left").assign(season=2026))
        for tag in ("v2", "v3"):
            board_ctx = board_ctx.merge(rows[rows["season"] == 2026][["gsis_id", "week", f"{tag}_points", *[f"{tag}_{c}" for c in P.ALL_COMPONENTS]]],
                                        on=["gsis_id", "week"], how="left")

    for pos in positions:
        print(f"\n\n## {pos}\n")
        t, facts = signal_table(board, rows, pos, stored_bt)
        print("### 1. Is it a signal?\n")
        print(t)
        print("\nreproduction:", "; ".join(facts["check"]))
        for tag in ("v2", "v3"):
            dlt, lo, hi, p = diff_interval(board, rows, pos, tag)
            print(f"\n2026 board wk 1–3 minus the {tag} backtest's wk 1–3 (2021–2025): {dlt:+.2f} (95% {lo:+.2f} to {hi:+.2f}; "
                  f"2026 worse in {p:.0%} of resamples)")
        refit = rows[(rows["season"] == 2026) & (rows["week"] <= 3) & rows["scored"] & (rows["position"] == pos)]
        dlt, lo, hi, p = diff_interval(refit.assign(proj_points=refit["v3_points"]), rows, pos, "v3")
        print(f"\n2026 wk 1–3 with v3.0 inputs (refit now) minus the v3 backtest's wk 1–3: {dlt:+.2f} (95% {lo:+.2f} to {hi:+.2f}; "
              f"2026 worse in {p:.0%} of resamples)")
        w4 = board[(board["position"] == pos) & (board["week"] == 4)]
        if len(w4):
            e4 = (w4["proj_points"] - w4["actual"]).abs()
            print(f"\nweek 4 (the board frozen at kickoff, {', '.join(sorted(w4['model_version'].unique()))}; {w4['game_id'].nunique()} "
                  f"games in this database): MAE {e4.mean():.2f} on {len(w4)} player-weeks")
        b3 = board_ctx[(board_ctx["position"] == pos) & (board_ctx["week"] <= 3)]
        bt = rows[(rows["position"] == pos) & rows["scored"] & (rows["season"] < 2026)]
        comps_pos = P.COMPONENTS[pos]
        comps_pos = [c for c in comps_pos if c not in ("attempts", "targets", "carries")]
        print("\n### 2. By component (reference scoring's points)\n")
        tabs = [component_table(b3.assign(**{"board_points": b3["proj_points"]}).rename(columns={f"proj_{c}": f"board_{c}" for c in P.ALL_COMPONENTS}),
                                "board_", scoring, comps_pos, "2026 wk 1–3, the board (v2.0)"),
                component_table(b3, "v3_", scoring, comps_pos, "2026 wk 1–3, v3.0 inputs refit now"),
                component_table(bt[bt["week"] <= 3], "v3_", scoring, comps_pos, "2021–2025 wk 1–3, v3.0"),
                component_table(bt, "v3_", scoring, comps_pos, "2021–2025 all weeks, v3.0")]
        print(md(pd.concat(tabs, ignore_index=True)))
        if pos == "QB":
            # the run split: designed runs vs scrambles (play-by-play), against the one rushing line the model projects
            print("\n### 2b. The rushing line: designed runs and scrambles (2021–2025, v3.0, started)\n")
            st = bt[bt["started"] == 1]
            w = P.unit_points(scoring)
            e_ry = (st["out_rushing_yards"] - st["v3_rushing_yards"]) * w["rushing_yards"]
            e_rt = (st["out_rushing_tds"] - st["v3_rushing_tds"]) * w["rushing_tds"]
            tbl = []
            for name, part in (("rushing yards", e_ry), ("rushing TDs", e_rt)):
                tbl.append({"piece": name, "bias (pts)": sgn(part.mean()), "MAE (pts)": fmt(part.abs().mean())})
            sd = (st["scr_yards"].fillna(0) * 0.1).mean(), (st["des_yards"].fillna(0) * 0.1).mean()
            print(md(pd.DataFrame(tbl)))
            print(f"\nper start, points from scramble yards {sd[0]:.2f}, from designed-run yards {sd[1]:.2f}; "
                  f"TDs: scramble {st['scr_tds'].fillna(0).mean() * 6:.2f}, designed {st['des_tds'].fillna(0).mean() * 6:.2f}")
            print("\n### 3. By kind of quarterback (bias = actual − projected, players resampled)\n")
            kt = [kind_table(bt, "v3_points", qb_kinds(bt), "2021–2025, v3.0"),
                  kind_table(b3, "proj_points", qb_kinds(b3), "2026 wk 1–3, the board (v2.0)"),
                  kind_table(b3, "v3_points", qb_kinds(b3), "2026 wk 1–3, v3.0 refit now")]
            print(md(pd.concat(kt, ignore_index=True)))
            print("\n### 4. By game script (started)\n")
            gt = [kind_table(bt, "v3_points", script_kinds(bt), "2021–2025, v3.0"),
                  kind_table(b3, "proj_points", script_kinds(b3), "2026 wk 1–3, the board (v2.0)")]
            print(md(pd.concat(gt, ignore_index=True)))
            e = bt["actual"] - bt["v3_points"]
            st = bt["started"] == 1
            r_script = np.corrcoef(bt.loc[st, "script"].astype(float), e[st])[0, 1]
            print(f"\ncorr(miss, team points − implied total), starters 2021–2025: {r_script:.2f} "
                  f"(R² {r_script ** 2:.0%} of the starters' miss variance is the game going differently from Vegas)")
            # bias by season per kind (is a kind's bias stable enough to fit?)
            print("\n### 5. Bias by season for the kinds a candidate would target (v3.0, started)\n")
            sk = qb_kinds(bt)
            rows5 = []
            for name in ["rushing share ≥ 30%", "rushing share < 15% of his points", "new starter (< 8 career starts), started",
                         "rookie, started", "new team (< 3 games with it), started", "new head coach this season, started",
                         "started, projected NOT to start (v3's input said no)"]:
                g = bt[sk[name]]
                per = g.assign(e=g["actual"] - g["v3_points"]).groupby("season")["e"].mean()
                rows5.append({"kind": name, **{str(int(k)): sgn(float(v)) for k, v in per.items()}, "n": len(g)})
            print(md(pd.DataFrame(rows5)))
            print("\n### 6. The largest 2026 misses (weeks 1–3, the board)\n")
            top = b3.assign(miss=b3["actual"] - b3["proj_points"]).sort_values("miss", key=np.abs, ascending=False).head(6)
            cols = ["week", "player_name", "team", "opponent", "proj_points", "v3_points", "actual", "miss", "proj_attempts", "out_attempts",
                    "proj_passing_yards", "out_passing_yards", "proj_passing_tds", "out_passing_tds", "proj_rushing_yards",
                    "out_rushing_yards", "out_rushing_tds", "pn_qb_starting", "started", "games_to_date", "career_starts"]
            print(md(top[cols].round(2)))
        print(f"\n### {'7' if pos == 'QB' else '3'}. Coverage of the 80% range (2026 board, wk 1–3)\n")
        cov = ((b3["actual"] >= b3["p10"]) & (b3["actual"] <= b3["p90"])).mean()
        print(f"{cov:.1%} of {len(b3)}")


if __name__ == "__main__":
    main()
