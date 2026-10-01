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
        console.print(f"[red]{failures} partition(s) failed; whatever those partitions held before was kept (nothing, if they were never loaded).[/red]")
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


@ingest_app.command("weather")
def ingest_weather_cmd(
    seasons: str | None = typer.Option(None, help="e.g. 2025, 2016-2025 (default: every season with games)"),
    forecast: bool = typer.Option(False, help="Also fetch the forecast for games in the next 16 days (one call per stadium)"),
    offline: bool = typer.Option(False, help="Replay every archived Open-Meteo file from data/raw/open_meteo; no network"),
    force: bool = typer.Option(False, help="Re-fetch and reload even when the archive already covers the games"),
):
    """Game-day weather from Open-Meteo by stadium and kickoff hour -> raw.nfl_weather (archive: one call per stadium-season; reads raw.nfl_schedules, so run it after `ingest nfl`)."""
    from .ingest.weather import ingest_weather

    with connect() as conn:
        migrate(conn)
        results = ingest_weather(conn, parse_seasons(seasons), offline=offline, forecast=forecast, force=force)
    if not results:
        console.print("weather: nothing to load (no archived Open-Meteo files to replay, or no game needs weather)")
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


@app.command("backtest-kd")
def backtest_kd_cmd(
    seasons: str = typer.Option("2021-2025", help="Held-out seasons, each scored by a model trained on the seasons before it"),
    out: Path | None = typer.Option(None, help="Report directory (default: <repo>/reports/backtests)"),
    weather: bool = typer.Option(False, help="Plan D3 experiment: add game-day wind + dome (intermediate.int_game_weather) to the features; writes only the report"),
):
    """Walk-forward backtest of the K and D/ST projections (kd1.0) against season-to-date and last-3 PPG, in each K/DEF league's scoring; writes the kd1.0 rows of ops.projection_backtest + a report."""
    from .kdef import run_backtest, summarize, verdict

    res = run_backtest(seasons, out, weather=weather)
    t = Table(title=f"K / DEF backtest {seasons} (mean over season-weeks, same unit-weeks for every scorer)")
    for c in ("league", "position", "season", "scorer", "weeks", "units/wk", "spearman", "top-10 hit", "mae", "coverage_80"):
        t.add_column(c)
    for r in summarize(res, ("league_id", "position", "season", "scorer")).itertuples():
        cov = "" if r.coverage_80 != r.coverage_80 else f"{r.coverage_80:.1%}"
        t.add_row(r.league_id[-6:], r.position, str(r.season), r.scorer, str(r.weeks), f"{r.n:.0f}", f"{r.spearman:.3f}",
                  f"{r.hit_rate:.1%}", f"{r.mae:.2f}", cov)
    console.print(t)
    for (lid, pos), v in verdict(res).items():
        console.print(f"{lid[-6:]} {pos}: kd_points {v.get('kd_points', float('nan')):.3f} vs season_ppg "
                      f"{v.get('season_ppg', float('nan')):.3f} vs last3_ppg {v.get('last3_ppg', float('nan')):.3f} Spearman -> ships {v['ships']}")


@app.command("project")
def project_cmd(
    season: int | None = typer.Option(None, help="Season to project (default: the newest with features); trained on the seasons before it"),
):
    """Fit projection v2 on completed seasons and write this season's weekly projections per league to ops.projections (and rescore the played weeks: ops.projection_drift; re-solve the lineups: ops.lineups). Then `make build`."""
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


@app.command("lineups")
def lineups_cmd(
    season: int | None = typer.Option(None, help="Projected season (default: the newest in ops.projections)"),
):
    """Exact lineup service (plan B1): the best legal lineup per league x roster x week from projection v2 (and the
    realised optimum for scored weeks); writes ops.lineups + ops.lineup_totals. Then `make project` publishes the mart."""
    from .lineup import run_lineups

    run = run_lineups(season)
    if run.season is None:
        console.print("ops.projections is empty: run `league-lab project` first")
        return
    t = run.totals
    realised = int(t["is_realised"].sum()) if len(t) else 0
    console.print(f"wrote {len(run.rows)} rows to ops.lineups and {len(t)} to ops.lineup_totals for {run.season} "
                  f"({len(t) - realised} proposed, {realised} realised roster-weeks) in {run.seconds:.2f} s "
                  f"(solver {run.solve_seconds:.2f} s)")
    if run.next_week is None or t.empty:
        return
    nxt = t[(t["week"] == run.next_week) & ~t["is_realised"]].sort_values(["league_id", "roster_id"])
    tab = Table(title=f"proposed lineups, week {run.next_week}")
    for c in ("league", "roster", "lineup", "bench", "weakest slot", "margin", "empty", "PPG-valued"):
        tab.add_column(c)
    def txt(v, spec: str = "") -> str:
        return "" if v is None or v != v else format(v, spec)

    for r in nxt.itertuples():
        tab.add_row(r.league_id[-6:], str(r.roster_id), txt(r.lineup_value, ".2f"), txt(r.bench_value, ".2f"),
                    txt(r.weakest_slot), txt(r.weakest_margin, ".2f"), txt(r.empty_slots), str(r.n_ppg_valued))
    console.print(tab)


@app.command("waivers")
def waivers_cmd(
    season: int | None = typer.Option(None, help="Projected season (default: the newest in ops.lineup_totals)"),
    verify: str | None = typer.Option(None, help="LEAGUE_ID:ROSTER_ID — also run the unpruned sweep on that roster and compare (read-only)"),
):
    """Waiver engine (plan B3): every legal add/drop per roster, valued by re-solving the B1 lineups for the next
    unplayed week and the 4-week horizon; writes ops.waiver_moves (runs at the end of `project`). Then `make project`
    publishes mart_waiver_moves."""
    from .waivers import run_verify, run_waivers

    if verify:
        league_id, _, roster = verify.partition(":")
        res = run_verify(league_id, int(roster), season)
        console.print(f"{league_id} roster {roster}: pruned {res['pruned_rows']} rows in {res['pruned_seconds']:.2f} s "
                      f"({res['survivors']} of {res['adds']} free agents past the bar), unpruned {res['unpruned_rows']} rows "
                      f"in {res['unpruned_seconds']:.2f} s — {'IDENTICAL' if res['identical'] else 'DIFFERENT'}")
        for label in ("only_pruned", "only_unpruned"):
            for row in res[label]:
                console.print(f"  {label}: {row}")
        if not res["identical"]:
            raise typer.Exit(1)
        return
    run = run_waivers(season)
    if run.season is None:
        console.print("ops.lineup_totals is empty: run `league-lab project` first")
        return
    t = run.rows
    st = run.stats
    console.print(f"wrote {len(t)} rows to ops.waiver_moves for {run.season} (decision week {run.week}) in {run.seconds:.2f} s "
                  f"(sweep of {st.get('rosters', 0)} rosters {run.sweep_seconds:.2f} s; {st.get('survivors', 0)} of "
                  f"{st.get('adds', 0)} free agent x roster pairs past the bar; lineups re-solved to ops.lineup_totals: "
                  f"{st.get('rosters', 0) - st.get('lineup_mismatch', 0)}/{st.get('rosters', 0)})")
    if t.empty:
        return
    tab = Table(title="top move per roster (horizon = the decision week and the next three)")
    for c in ("league", "roster", "list", "add", "drop", "this week", "horizon", "slot", "displaced"):
        tab.add_column(c)

    def txt(v, spec: str = "") -> str:
        return "" if v is None or v != v else format(v, spec)

    first = t.sort_values(["league_id", "roster_id", "move_rank"], na_position="first").groupby(["league_id", "roster_id"]).head(1)
    for r in first.itertuples():
        tab.add_row(r.league_id[-6:], str(r.roster_id), r.list_kind, txt(r.add_name), txt(r.drop_name) or ("—" if r.list_kind != "nothing" else ""),
                    txt(r.weekly_gain, "+.2f"), txt(r.horizon_gain, "+.2f"), txt(r.add_slot), txt(r.displaced_name))
    console.print(tab)


@app.command("signals")
def signals_cmd(
    season: int | None = typer.Option(None, help="Projected season (default: the newest)"),
):
    """Role alerts + scenario upside (plan R-10 / R-12) on their own: rewrites ops.player_role_alerts (the season, and any
    season written by another rule version) and ops.player_scenarios; `project` runs the same step after the projections."""
    from .signals import run_signals

    run = run_signals(season)
    if run is None:
        console.print("signals failed: see the log")
        raise typer.Exit(1)
    console.print(f"{run.alerts} alerts this season ({run.live_up} live bigger-role alerts at QB-TE, {run.lapsed} lapsed); "
                  f"{run.scenarios} scenario rows in {run.seconds:.1f} s; base = stored projection to {run.base_max_diff:.1e}")


@app.command("signals-backtest")
def signals_backtest_cmd(
    seasons: str = typer.Option("2023-2025", help="Seasons to test (walk-forward: models fitted on the seasons before each)"),
    out: Path | None = typer.Option(None, help="Directory for the CSV + report (default reports/backtests)"),
):
    """Calibrate the larger-role scenario before a probability is shown (plan R-12), and measure the role alerts'
    precision (R-10), with the rule as it runs in season (no routes). Read-only on the database."""
    import psycopg

    from .signals import scenario_backtest

    wanted = parse_seasons(seasons) or []
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        cal = scenario_backtest(conn, wanted)
    d = out or PROJECT_ROOT / "reports" / "backtests"
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    cal.rows.to_csv(d / f"scenario_backtest_{stamp}.csv", index=False)
    text = ["# Scenario upside calibration and role-alert precision", "",
            f"hold rates (bigger role still there three games later, seasons before {min(wanted)}): {cal.hold}", "",
            "## Scenario vs projection (alerts whose scenario moved the projection)", "", cal.summary.to_string(index=False), "",
            "## Role alerts: first detections, three games later", "", cal.precision.to_string(index=False), "",
            cal.precision_kind.to_string(index=False), ""]
    (d / f"scenario_backtest_{stamp}.md").write_text("\n".join(text))
    console.print("\n".join(text))
    console.print(f"written to {d}/scenario_backtest_{stamp}.*")


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
