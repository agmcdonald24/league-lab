"""League Lab command line: ``league-lab --help``.

Typical flow
    league-lab db migrate                 # schemas + ops tables (idempotent)
    league-lab ingest sleeper             # league chain, matchups, transactions, drafts, players
    league-lab ingest nfl --seasons 2025  # pilot season
    league-lab ingest nfl                 # full history (settings.seasons_start .. current)
    league-lab dbt build                  # dbt deps/seed/run/test with the project's profile
    league-lab refresh                    # daily: sleeper + current NFL season + dbt build
    league-lab status                     # what loaded, when, and what failed
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import PROJECT_ROOT, get_settings
from .db import connect, fetch_all, migrate
from .ingest.nflverse import DATASETS

app = typer.Typer(no_args_is_help=True, help="League Lab: Sleeper + nflverse -> Postgres -> dbt -> explorer")
db_app = typer.Typer(no_args_is_help=True, help="Database utilities")
ingest_app = typer.Typer(no_args_is_help=True, help="Source ingestion")
app.add_typer(db_app, name="db")
app.add_typer(ingest_app, name="ingest")
console = Console(width=160)


@app.callback()
def _setup(verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging")):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def parse_seasons(text: str | None) -> list[int] | None:
    """'2025' | '2016-2025' | '2016,2018,2025' -> [ints]; None -> default range."""
    if not text:
        return None
    out: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return sorted(out)


def _print_results(results) -> int:
    t = Table(title="load results", show_lines=False)
    for c in ("source", "dataset", "partition", "status", "rows"):
        t.add_column(c, no_wrap=True)
    t.add_column("error", overflow="fold")
    failures = 0
    for r in results:
        if r.status in ("failed", "contract_failed"):
            failures += 1
        style = {"success": "green", "skipped_unchanged": "dim", "failed": "red", "contract_failed": "red"}[r.status]
        t.add_row(r.source, r.dataset, r.partition_key, f"[{style}]{r.status}[/{style}]",
                  "" if r.row_count is None else str(r.row_count), (r.error or "")[:80])
    console.print(t)
    if failures:
        console.print(f"[red]{failures} partition(s) failed; previous good data was kept for those.[/red]")
    return failures


# ----------------------------------------------------------------------------- db
@db_app.command("migrate")
def db_migrate():
    """Create schemas and ops tables (safe to re-run)."""
    with connect() as conn:
        migrate(conn)
        from .ingest.sleeper import ensure_tables
        ensure_tables(conn)
    console.print("[green]schemas and ops tables are in place[/green]")


@db_app.command("check")
def db_check():
    """Verify both roles can connect and the app role cannot write."""
    s = get_settings()
    with connect() as conn:
        v = fetch_all(conn, "select version(), current_user, current_database()")[0]
        console.print(f"pipeline role ok: {v[1]}@{v[2]}\n  {v[0]}")
    with connect(s.app_dsn(), autocommit=True) as conn:
        u = fetch_all(conn, "select current_user")[0][0]
        try:
            with conn.cursor() as cur:
                cur.execute("create table analytics.__write_probe (x int)")
            console.print("[red]app role could CREATE in analytics - fix grants (scripts/init_db.sql)[/red]")
            raise typer.Exit(1)
        except Exception as exc:  # noqa: BLE001 - expected: permission denied
            if "permission denied" in str(exc).lower() or "read-only transaction" in str(exc).lower():
                console.print(f"app role ok (read-only confirmed): {u}")
            else:
                console.print(f"app role connected as {u}; write probe raised: {exc}")


# ----------------------------------------------------------------------------- ingest
@ingest_app.command("sleeper")
def ingest_sleeper_cmd(
    league_id: str | None = typer.Option(None, help="Override LEAGUE_LAB_SLEEPER_LEAGUE_ID (comma-separate several leagues)"),
    offline: bool = typer.Option(False, help="Replay archived JSON from data/raw instead of calling the API"),
    force: bool = typer.Option(False, help="Reload partitions even when unchanged"),
    players: bool = typer.Option(True, help="Include the full NFL player directory (cached daily)"),
):
    """Fetch the league chain (settings, users, rosters, matchups, transactions, drafts, brackets)."""
    from .ingest.sleeper import ingest_sleeper

    with connect() as conn:
        migrate(conn)
        results = ingest_sleeper(conn, league_id, offline=offline, force=force, include_players=players)
    raise typer.Exit(1 if _print_results(results) else 0)


@ingest_app.command("nfl")
def ingest_nfl_cmd(
    seasons: str | None = typer.Option(None, help="e.g. 2025, 2016-2025, 2016,2024 (default: seasons_start..current)"),
    datasets: str | None = typer.Option(None, help="comma list; default all: " + ",".join(DATASETS)),
    offline: bool = typer.Option(False, help="Replay archived files from data/raw instead of downloading"),
    force: bool = typer.Option(False, help="Reload partitions even when unchanged"),
):
    """Download nflverse release files and load raw.nfl_* tables (one transaction per partition)."""
    from .ingest.nflverse import ingest_nflverse

    with connect() as conn:
        migrate(conn)
        results = ingest_nflverse(
            conn, parse_seasons(seasons), [d.strip() for d in datasets.split(",")] if datasets else None,
            offline=offline, force=force,
        )
    raise typer.Exit(1 if _print_results(results) else 0)


@ingest_app.command("all")
def ingest_all_cmd(
    seasons: str | None = typer.Option(None),
    offline: bool = typer.Option(False),
    force: bool = typer.Option(False),
):
    """Sleeper + every nflverse dataset."""
    from .ingest.nflverse import ingest_nflverse
    from .ingest.sleeper import ingest_sleeper

    with connect() as conn:
        migrate(conn)
        results = ingest_sleeper(conn, offline=offline, force=force)
        results += ingest_nflverse(conn, parse_seasons(seasons), offline=offline, force=force)
    raise typer.Exit(1 if _print_results(results) else 0)


# ----------------------------------------------------------------------------- dbt
def _dbt_env() -> dict[str, str]:
    s = get_settings()
    env = dict(os.environ)
    # .env sets DBT_PROFILES_DIR=config/dbt (relative to the repo); dbt runs with cwd=dbt/,
    # so a relative value must be resolved against the project root, not the subprocess cwd.
    profiles_dir = Path(env.get("DBT_PROFILES_DIR") or PROJECT_ROOT / "config" / "dbt")
    if not profiles_dir.is_absolute():
        profiles_dir = PROJECT_ROOT / profiles_dir
    env["DBT_PROFILES_DIR"] = str(profiles_dir)
    env.setdefault("LEAGUE_LAB_DB_HOST", s.db_host)
    env.setdefault("LEAGUE_LAB_DB_PORT", str(s.db_port))
    env.setdefault("LEAGUE_LAB_DB_NAME", s.db_name)
    env.setdefault("LEAGUE_LAB_DB_USER", s.db_user)
    env.setdefault("LEAGUE_LAB_DB_PASSWORD", s.db_password)
    env.setdefault("LEAGUE_LAB_SEASONS_START", str(s.seasons_start))
    env.setdefault("LEAGUE_LAB_REFERENCE_LEAGUE_ID", s.reference_league_id)
    return env


@app.command("dbt", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def dbt_cmd(ctx: typer.Context):
    """Run dbt with the project's profile, e.g. `league-lab dbt build`, `league-lab dbt test -s marts`."""
    args = list(ctx.args) or ["build"]
    cmd = [sys.executable, "-m", "dbt.cli.main", *args, "--project-dir", str(PROJECT_ROOT / "dbt")]
    console.print(f"[dim]$ dbt {' '.join(args)}[/dim]")
    res = subprocess.run(cmd, env=_dbt_env(), cwd=PROJECT_ROOT / "dbt")
    raise typer.Exit(res.returncode)


@app.command("refresh")
def refresh_cmd(
    full: bool = typer.Option(False, help="Also re-check every historical NFL season (monthly audit)"),
    skip_dbt: bool = typer.Option(False),
):
    """Daily refresh: Sleeper league + current NFL season + dbt build (plan §7 schedule)."""
    from .ingest.nflverse import current_nfl_season, ingest_nflverse
    from .ingest.sleeper import ingest_sleeper

    seasons = None if full else [current_nfl_season()]
    with connect() as conn:
        migrate(conn)
        results = ingest_sleeper(conn)
        results += ingest_nflverse(conn, seasons)
    failures = _print_results(results)
    if skip_dbt:
        raise typer.Exit(1 if failures else 0)
    cmd = [sys.executable, "-m", "dbt.cli.main", "build", "--project-dir", str(PROJECT_ROOT / "dbt")]
    res = subprocess.run(cmd, env=_dbt_env(), cwd=PROJECT_ROOT / "dbt")
    raise typer.Exit(1 if (failures or res.returncode) else 0)


# ----------------------------------------------------------------------------- status
@app.command("status")
def status_cmd(limit: int = typer.Option(40, help="Recent manifest rows to show")):
    """Show partition state and recent loads from the ops schema."""
    with connect() as conn:
        parts = fetch_all(conn, """
            select source, dataset, count(*) partitions, sum(row_count) rows, max(loaded_at) last_loaded
            from ops.source_partition group by 1,2 order by 1,2""")
        recent = fetch_all(conn, """
            select started_at, source, dataset, partition_key, status, row_count, left(error, 60)
            from ops.load_manifest order by load_id desc limit %s""", (limit,))
        fails = fetch_all(conn, """
            select source, dataset, partition_key, status, left(error, 90), started_at
            from ops.load_manifest m
            where status in ('failed','contract_failed')
              and started_at > now() - interval '7 days'
            order by started_at desc limit 20""")
    t = Table(title="source partitions (current state)")
    for c in ("source", "dataset", "partitions", "rows", "last loaded"):
        t.add_column(c)
    for r in parts:
        t.add_row(r[0], r[1], str(r[2]), str(r[3]), str(r[4])[:19])
    console.print(t)
    t = Table(title=f"last {limit} load attempts")
    for c in ("started", "source", "dataset", "partition", "status", "rows", "error"):
        t.add_column(c)
    for r in recent:
        t.add_row(str(r[0])[:19], r[1], r[2], r[3], r[4], str(r[5] or ""), r[6] or "")
    console.print(t)
    if fails:
        console.print("[red]failures in the last 7 days:[/red]")
        for r in fails:
            console.print(f"  {r[5]:%Y-%m-%d %H:%M} {r[0]}/{r[1]}/{r[2]} {r[3]}: {r[4]}")


@app.command("weekly-pack")
def weekly_pack_cmd(
    week: int | None = typer.Option(None, help="League week (default: last scored week)"),
    team: int | None = typer.Option(None, help="Roster id for a private team brief (see `league-lab teams`)"),
    league_id: str | None = typer.Option(None, help="League id (default: the current league loaded)"),
    out: Path | None = typer.Option(None, help="Output root (default: <repo>/reports)"),
):
    """Write the week's facts as Markdown + CSV (league recap pack, plus a team brief with --team)."""
    from .reports import build_packs

    for path in build_packs(league_id, week, team, out):
        console.print(f"[green]wrote[/green] {path}")


@app.command("import-routes")
def import_routes_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True, help="Provider CSV (see ingest/routes_feed.py for the contract)"),
    provider: str = typer.Option(..., help="Short provider name, e.g. pff, fantasypoints"),
):
    """Import a licensed routes-run export into raw.routes_feed (replaces the provider's rows per season)."""
    from .ingest.routes_feed import RoutesFeedError, import_routes

    with connect() as conn:
        migrate(conn)
        try:
            results = import_routes(conn, path, provider)
        except RoutesFeedError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(2) from exc
    raise typer.Exit(1 if _print_results(results) else 0)


@app.command("fit-rankings")
def fit_rankings_cmd(
    train: str = typer.Option("2019-2022", help="Training seasons for the baseline weights, e.g. 2019-2022"),
):
    """Refit the transparent baseline (OLS per position) and write dbt/seeds/ranking_weights.csv. Then `make build`."""
    from .rankings import SEED_PATH, run_fit

    for r in run_fit(train):
        console.print(f"[green]{r.position}[/green] n={r.n_rows} r2={r.r2:.3f}  " + ", ".join(f"{k}={v:+.3f}" for k, v in r.coef.items()))
    console.print(f"wrote {SEED_PATH} — run `make build` to apply")


@app.command("backtest")
def backtest_cmd(
    seasons: str = typer.Option("2023-2025", help="Held-out seasons to score, e.g. 2023-2025"),
    out: Path | None = typer.Option(None, help="Report directory (default: <repo>/reports/backtests)"),
):
    """Score the baseline and the naive baselines week by week (Spearman, top-N hit rate, MAE); writes ops.backtest_results + a report."""
    from .rankings import run_backtest, summarize

    res = run_backtest(seasons, out)
    t = Table(title=f"backtest {seasons} (mean over season-weeks)")
    for c in ("position", "scorer", "weeks", "spearman", "hit_rate", "mae"):
        t.add_column(c)
    for r in summarize(res).sort_values(["position", "spearman"], ascending=[True, False]).itertuples():
        t.add_row(r.position, r.scorer, str(r.weeks), f"{r.spearman:.3f}", f"{r.hit_rate:.1%}", f"{r.mae:.2f}")
    console.print(t)


@app.command("backtest-v2")
def backtest_v2_cmd(
    seasons: str = typer.Option("2021-2025", help="Held-out seasons, each scored by a model trained on the seasons before it"),
    out: Path | None = typer.Option(None, help="Report directory (default: <repo>/reports/backtests)"),
):
    """Walk-forward backtest of projection v2 (components + P10/P50/P90) against the baseline; writes ops.projection_backtest + a report."""
    from .projections import run_backtest, summarize

    res = run_backtest(seasons, out)
    t = Table(title=f"projection v2 backtest {seasons} (mean over season-weeks)")
    for c in ("league", "position", "scorer", "weeks", "spearman", "hit_rate", "mae", "coverage_80", "width"):
        t.add_column(c)
    for r in summarize(res).sort_values(["league_id", "position", "spearman"], ascending=[True, True, False]).itertuples():
        cov = "" if r.coverage_80 != r.coverage_80 else f"{r.coverage_80:.1%}"
        wid = "" if r.interval_width != r.interval_width else f"{r.interval_width:.1f}"
        t.add_row(r.league_id[-6:], r.position, r.scorer, str(r.weeks), f"{r.spearman:.3f}", f"{r.hit_rate:.1%}", f"{r.mae:.2f}", cov, wid)
    console.print(t)


@app.command("project")
def project_cmd(
    season: int | None = typer.Option(None, help="Season to project (default: the newest with features); trained on the seasons before it"),
):
    """Fit projection v2 on completed seasons and write this season's weekly projections per league to ops.projections (and rescore the played weeks: ops.projection_drift). Then `make build`."""
    from .projections import run_project

    pred = run_project(season)
    fz = pred.attrs.get("freeze", {})
    console.print(f"projected {len(pred)} rows for {int(pred['season'].iloc[0])} "
                  f"({pred['league_id'].nunique()} league(s), weeks {int(pred['week'].min())}-{int(pred['week'].max())}); "
                  f"wrote {fz.get('rows_written', len(pred))} (weeks {fz.get('rewritten') or 'none'}), "
                  f"kept frozen weeks {fz.get('kept') or 'none'} (kickoff board: {fz.get('kickoff') or 'none'}; refit values: {fz.get('refit') or 'none'}) — "
                  "run `make build` to publish mart_player_week_projections")


@app.command("drift")
def drift_cmd(
    season: int | None = typer.Option(None, help="Projected season to score (default: the newest in mart_player_week_projections)"),
):
    """Score the projection v2 board's played weeks like the backtest (Spearman, hit rate, MAE, coverage, share frozen at kickoff); writes ops.projection_drift."""
    from .projections import run_drift

    res = run_drift(season)
    if res.empty:
        console.print("no played week on the board yet: ops.projection_drift has no rows for this season")
        return
    t = Table(title=f"projection drift {int(res['season'].iloc[0])} (stored board, frozen at kickoff for started weeks; played + rankable players)")
    for c in ("league", "week", "position", "n", "spearman", "hit_rate", "mae", "coverage_80", "width", "games", "kickoff board"):
        t.add_column(c)
    def fmt(v, spec: str) -> str:
        return "" if v is None or v != v else format(v, spec)

    for r in res.sort_values(["league_id", "week", "position"]).itertuples():
        t.add_row(r.league_id[-6:], str(r.week), r.position, str(r.n_players), fmt(r.spearman, ".3f"), fmt(r.hit_rate, ".1%"),
                  fmt(r.mae, ".2f"), fmt(r.coverage_80, ".1%"), fmt(r.interval_width, ".1f"), f"{r.games_played}/{r.games_scheduled}",
                  fmt(r.frozen_share, ".0%"))
    console.print(t)


@app.command("teams")
def teams_cmd():
    """List roster ids and team names for the current league season(s)."""
    with connect(get_settings().app_dsn(), autocommit=True) as conn:
        rows = fetch_all(conn, """select l.league_id, l.league_name, l.season, m.roster_id, m.team_name, m.manager_name
                                  from analytics.dim_league_member m join analytics.dim_league_season l using (league_id)
                                  where l.is_current_season order by l.league_name, m.roster_id""")
    t = Table(title="current league rosters")
    for c in ("league_id", "league", "season", "roster_id", "team", "manager"):
        t.add_column(c)
    for r in rows:
        t.add_row(*[str(x) for x in r])
    console.print(t)


@app.command("version")
def version_cmd():
    from .manifest import code_version

    console.print(f"league-lab 0.1.0 ({code_version()}) at {datetime.now(UTC):%Y-%m-%d %H:%M UTC}")
    console.print(f"project root: {PROJECT_ROOT}")
    console.print(f"data dir:     {Path(get_settings().data_dir)}")
