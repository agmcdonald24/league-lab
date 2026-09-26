"""Weekly rankings: a transparent baseline projection and the backtest that keeps it honest.

The projection is a per-position linear formula over the finished ``f_*`` features in
``analytics.mart_player_week_features`` (as-of the week: nothing from the week itself leaks in).
Its coefficients live in ``dbt/seeds/ranking_weights.csv`` so dbt applies the *same* formula in
``mart_player_week_rankings`` and the explorer can print it. ``fit_weights`` refits the seed from a
training window with ordinary least squares (no tuning knobs, nothing hidden); ``backtest`` scores
the projection and three naive baselines (season PPG, last-3 PPG, expected points L5) on held-out
seasons with Spearman rank correlation, top-N hit rate and mean absolute error, per
season-week-position, and writes ``ops.backtest_results`` plus a Markdown report.

Plan §1: "The foundation must support later forecasting without asserting that descriptive
correlations already predict performance" - the backtest is the assertion's replacement. A model
earns a place only by beating the naive baselines here, out of sample.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from .config import PROJECT_ROOT, get_settings

log = logging.getLogger(__name__)

SEED_PATH = PROJECT_ROOT / "dbt" / "seeds" / "ranking_weights.csv"
POSITIONS = ("QB", "RB", "WR", "TE")

# Features per position, in formula order. Interactions (x_sample) let last season fade as the
# current one accumulates; everything is still one weighted sum the page can print.
FEATURES: dict[str, list[str]] = {
    "QB": ["f_xppg_l5", "f_ppg_std", "f_ppg_l3", "f_ppg_prev", "f_ppg_std_x_sample", "f_ppg_prev_x_nosample",
           "f_opp_allowed_diff", "f_implied_total", "f_home", "f_carry_trend", "f_snap_l3"],
    "RB": ["f_xppg_l5", "f_ppg_std", "f_ppg_l3", "f_ppg_prev", "f_ppg_std_x_sample", "f_ppg_prev_x_nosample",
           "f_opp_allowed_diff", "f_implied_total", "f_home", "f_carry_trend", "f_target_trend", "f_snap_l3"],
    "WR": ["f_xppg_l5", "f_ppg_std", "f_ppg_l3", "f_ppg_prev", "f_ppg_std_x_sample", "f_ppg_prev_x_nosample",
           "f_opp_allowed_diff", "f_implied_total", "f_home", "f_target_trend", "f_snap_l3"],
    "TE": ["f_xppg_l5", "f_ppg_std", "f_ppg_l3", "f_ppg_prev", "f_ppg_std_x_sample", "f_ppg_prev_x_nosample",
           "f_opp_allowed_diff", "f_implied_total", "f_home", "f_target_trend", "f_snap_l3"],
}
ALL_FEATURES = sorted({f for fs in FEATURES.values() for f in fs})
# top-N per position for the hit-rate metric: roughly the weekly starters in a 10-12 team league
TOP_N = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}
NAIVE = {"naive_ppg_std": "f_ppg_std", "naive_ppg_l3": "f_ppg_l3", "naive_xppg_l5": "f_xppg_l5"}
SCORERS = ["proj_points", *NAIVE]


def parse_seasons(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(out))


def add_interactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["f_ppg_std_x_sample"] = df["f_ppg_std"] * df["f_sample"]
    df["f_ppg_prev_x_nosample"] = df["f_ppg_prev"] * (1 - df["f_sample"])
    return df


def load_features(conn: psycopg.Connection, seasons: list[int]) -> pd.DataFrame:
    sql = """select gsis_id, season, week, position, player_name, team, opponent, played, points_actual, no_history,
                    report_status, roster_status, games_to_date,
                    f_xppg_l5, f_ppg_std, f_ppg_l3, f_ppg_prev, f_opp_allowed_diff, f_implied_total, f_home,
                    f_target_trend, f_carry_trend, f_snap_l3, f_sample
             from analytics.mart_player_week_features where season = any(%s)"""
    with conn.cursor() as cur:
        cur.execute(sql, (seasons,))
        cols = [d.name for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    for c in df.columns:
        if c.startswith("f_") or c == "points_actual":
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return add_interactions(df)


# ------------------------------------------------------------------------------ fit
@dataclass
class FitResult:
    position: str
    n_rows: int
    r2: float
    coef: dict[str, float]


def fit_weights(conn: psycopg.Connection, train_seasons: list[int], seed_path: Path = SEED_PATH) -> list[FitResult]:
    """OLS per position on played rows (the ones a ranking is judged on). Writes the seed."""
    df = load_features(conn, train_seasons)
    df = df[df["played"] & df["points_actual"].notna() & ~df["no_history"]]
    results: list[FitResult] = []
    rows: list[dict[str, object]] = []
    fitted_at = datetime.now(UTC).strftime("%Y-%m-%d")
    train_label = f"{min(train_seasons)}-{max(train_seasons)}"
    for pos in POSITIONS:
        d = df[df["position"] == pos]
        feats = FEATURES[pos]
        x = np.column_stack([np.ones(len(d)), d[feats].to_numpy(dtype=float)])
        y = d["points_actual"].to_numpy(dtype=float)
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
        pred = x @ beta
        ss_res = float(((y - pred) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
        coef = {"intercept": float(beta[0]), **{f: float(b) for f, b in zip(feats, beta[1:], strict=True)}}
        results.append(FitResult(pos, len(d), r2, coef))
        for feat, w in coef.items():
            rows.append({"position": pos, "feature": feat, "weight": round(w, 5), "train_seasons": train_label,
                         "n_rows": len(d), "r2_train": round(r2, 4), "fitted_at": fitted_at})
        log.info("fit %s: n=%s r2=%.3f", pos, len(d), r2)
    with open(seed_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["position", "feature", "weight", "train_seasons", "n_rows", "r2_train", "fitted_at"])
        w.writeheader()
        w.writerows(rows)
    return results


# ------------------------------------------------------------------------------ backtest
def _spearman(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 3:
        return float("nan")
    return float(a.rank().corr(b.rank()))


def _hit_rate(pred: pd.Series, actual: pd.Series, n: int) -> float:
    n = min(n, len(pred))
    if n == 0:
        return float("nan")
    top_pred = set(pred.sort_values(ascending=False).index[:n])
    top_act = set(actual.sort_values(ascending=False).index[:n])
    return len(top_pred & top_act) / n


def backtest(conn: psycopg.Connection, seasons: list[int], out_dir: Path | None = None, min_players: int = 8) -> pd.DataFrame:
    """Score every scorer per season-week-position on players who played. Returns the long results."""
    sql = """select season, week, position, gsis_id, player_name, points_actual, proj_points, naive_ppg_std, naive_ppg_l3, naive_xppg_l5,
                    is_rankable
             from analytics.mart_player_week_rankings
             where season = any(%s) and played and points_actual is not null"""
    with conn.cursor() as cur:
        cur.execute(sql, (seasons,))
        cols = [d.name for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    for c in ("points_actual", *SCORERS):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df = df[df["is_rankable"]]
    out: list[dict[str, object]] = []
    for (season, week, pos), g in df.groupby(["season", "week", "position"]):
        if len(g) < min_players:
            continue
        for scorer in SCORERS:
            gg = g.dropna(subset=[scorer])
            out.append({
                "season": int(season), "week": int(week), "position": pos, "scorer": scorer, "n_players": int(len(gg)),
                "spearman": _spearman(gg[scorer], gg["points_actual"]),
                "top_n": TOP_N[pos],
                "hit_rate": _hit_rate(gg[scorer], gg["points_actual"], TOP_N[pos]),
                "mae": float((gg[scorer] - gg["points_actual"]).abs().mean()),
                "top_n_actual_ppg": float(gg["points_actual"].sort_values(ascending=False).head(TOP_N[pos]).mean()),
                "top_n_picked_ppg": float(gg.sort_values(scorer, ascending=False).head(TOP_N[pos])["points_actual"].mean()),
            })
    res = pd.DataFrame(out)
    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    res["run_id"] = run_id
    res["run_at"] = datetime.now(UTC)
    _write_results(conn, res, seasons)
    report = _report(res, seasons)
    out_dir = out_dir or PROJECT_ROOT / "reports" / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"backtest_{min(seasons)}_{max(seasons)}_{run_id}.md"
    path.write_text(report)
    log.info("backtest written to %s", path)
    return res


def _write_results(conn: psycopg.Connection, res: pd.DataFrame, seasons: list[int]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """create table if not exists ops.backtest_results (
                   run_id text, run_at timestamptz, season integer, week integer, position text, scorer text,
                   n_players integer, spearman double precision, top_n integer, hit_rate double precision,
                   mae double precision, top_n_actual_ppg double precision, top_n_picked_ppg double precision)"""
        )
        cur.execute("delete from ops.backtest_results where season = any(%s)", (seasons,))
        cur.executemany(
            """insert into ops.backtest_results values (%(run_id)s, %(run_at)s, %(season)s, %(week)s, %(position)s, %(scorer)s,
               %(n_players)s, %(spearman)s, %(top_n)s, %(hit_rate)s, %(mae)s, %(top_n_actual_ppg)s, %(top_n_picked_ppg)s)""",
            [{k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in r.items()} for r in res.to_dict("records")],
        )
    conn.commit()


def summarize(res: pd.DataFrame) -> pd.DataFrame:
    s = res.groupby(["position", "scorer"]).agg(
        weeks=("week", "count"), spearman=("spearman", "mean"), hit_rate=("hit_rate", "mean"), mae=("mae", "mean"),
        top_n_picked_ppg=("top_n_picked_ppg", "mean"), top_n_actual_ppg=("top_n_actual_ppg", "mean"),
    ).reset_index()
    return s


def _report(res: pd.DataFrame, seasons: list[int]) -> str:
    lines = [f"# Rankings backtest {min(seasons)}–{max(seasons)}",
             f"_generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · players who played, regular season, weeks with ≥ 8 ranked players_",
             "",
             "Scorers: `proj_points` = League Lab baseline (seed `ranking_weights.csv`); `naive_ppg_std` = season PPG to date; "
             "`naive_ppg_l3` = last-3 PPG; `naive_xppg_l5` = expected points last 5. Metrics per season-week-position, then averaged: "
             "Spearman rank correlation with actual points; top-N hit rate (share of the actual top-N the scorer's top-N caught); "
             "MAE in points; and the actual PPG of the scorer's top-N against the true top-N (the ceiling).", ""]
    s = summarize(res)
    lines.append("## All held-out seasons\n")
    lines.append("| Pos | Scorer | Weeks | Spearman | Top-N hit rate | MAE | Top-N picked PPG | Top-N ceiling PPG |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in s.sort_values(["position", "spearman"], ascending=[True, False]).itertuples():
        lines.append(f"| {r.position} | `{r.scorer}` | {r.weeks} | {r.spearman:.3f} | {r.hit_rate:.1%} | {r.mae:.2f} | {r.top_n_picked_ppg:.1f} | {r.top_n_actual_ppg:.1f} |")
    for season, rs in res.groupby("season"):
        lines.append(f"\n## {season}\n")
        lines.append("| Pos | Scorer | Weeks | Spearman | Top-N hit rate | MAE |")
        lines.append("|---|---|---|---|---|---|")
        for r in summarize(rs).sort_values(["position", "spearman"], ascending=[True, False]).itertuples():
            lines.append(f"| {r.position} | `{r.scorer}` | {r.weeks} | {r.spearman:.3f} | {r.hit_rate:.1%} | {r.mae:.2f} |")
    # verdict
    lines.append("\n## Verdict\n")
    for pos in POSITIONS:
        sp = s[s["position"] == pos].set_index("scorer")["spearman"]
        if sp.empty:
            continue
        best_naive = sp.drop("proj_points", errors="ignore").idxmax()
        gap = sp.get("proj_points", float("nan")) - sp[best_naive]
        verdict = "beats" if gap > 0.01 else ("ties" if gap > -0.01 else "loses to")
        lines.append(f"- **{pos}**: baseline {verdict} the best naive scorer (`{best_naive}`) by {gap:+.3f} Spearman.")
    return "\n".join(lines) + "\n"


def run_fit(train: str) -> list[FitResult]:
    s = get_settings()
    with psycopg.connect(s.pipeline_dsn(), autocommit=True) as conn:
        return fit_weights(conn, parse_seasons(train))


def run_backtest(seasons: str, out: Path | None) -> pd.DataFrame:
    s = get_settings()
    with psycopg.connect(s.pipeline_dsn(), autocommit=False) as conn:
        return backtest(conn, parse_seasons(seasons), out)
