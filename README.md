# League Lab — shipped as **isuckatfantasy**

The product a manager opens (the phone web app at `https://league-lab.onrender.com`, its API, the home-screen icon)
is called **isuckatfantasy** since 2026-10-04 (`web/src/lib/brand.ts`, `api/league_lab_api/settings.py:APP_NAME`).
The codebase, the Python package (`league_lab`), the environment variables (`LEAGUE_LAB_*`), the database roles,
the repository, the Render service and the research console keep the name League Lab: nothing a league-mate sees
says it, and renaming the internals would move every secret and workflow for no gain.

Local, reproducible analytics for a Sleeper fantasy league (League of Scrubs) and NFL
skill-position research, 2016 → today.

```
Sleeper API ─┐                         ┌─ staging views ─┐
             ├─ league-lab ingest ─► raw ─┤                 ├─► analytics marts ─► Streamlit explorer
nflverse ────┘   (Parquet/JSON archive)   └─ dbt models + tests ┘        (read-only role)
```

* **Data**: Sleeper league chain (settings, members, rosters, weekly lineups + points, transactions,
  drafts, brackets) and nflverse (game-level player/team stats, schedules, weekly rosters, snap
  counts, player identity, the Sleeper↔NFL id crosswalk).
* **Transformations**: dbt Core + dbt-postgres. Every key is tested; every share metric uses an
  independent team denominator over the same games as the numerator.
* **Interface**: Streamlit, bound to `127.0.0.1`, reading only validated marts with a read-only role.
  Pick any league and any team as the perspective (it lives in the URL, so a link opens on a
  leaguemate's team). Team Hub, Waiver Wire, Matchups (defense vs position + cornerback context),
  Trade Finder, League (luck, bench, weekly rank, roster rankings), plus the research pages.
* **Weekly packs**: `league-lab weekly-pack --week 3 --team 2` writes the facts behind a newsletter
  (results, luck, lineup decisions, top/bottom performers, moves, kickers) and a private team brief
  (roster health, waiver targets, buy-low/sell-high, trade fits, keeper facts) as Markdown + CSV.
* **Ops**: a load manifest with checksums, conditional downloads, transactional partition
  replacement, and idempotent replays. One command refreshes everything.

This is the **trimmed MVP1** described in [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md): the core
data path is complete and tested; play-by-play/FTN first-read metrics, Dagster orchestration and
blue/green publication are tracked there as the next phases. Read
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before trusting any number.

## Quick start (macOS, Apple Silicon)

```bash
cd ~/PycharmProjects/league-lab
./scripts/bootstrap.sh          # starts PostgreSQL 17, creates roles/db, uv sync, pilot ingest, dbt build
make app                        # http://127.0.0.1:8501
```

`bootstrap.sh` is idempotent. It writes a git-ignored `.env` with generated passwords, loads the
Sleeper league history plus the previous and current NFL seasons, and runs the full dbt build with
tests. Then:

```bash
./scripts/bootstrap.sh --full   # or: make backfill      -> NFL history 2016-present
make refresh                    # daily: the nightly pipeline (scripts/nightly.sh) + backup; GitHub Actions runs it too
make status                     # what loaded, when, what failed
make test                       # dbt tests only
make pytest                     # python unit tests (no database needed)
```

Full instructions, troubleshooting and scheduling: [`docs/SETUP_RUNBOOK.md`](docs/SETUP_RUNBOOK.md).

## Repository layout

```
league-lab/
  AGENTS.md                 # working agreement for humans and agents touching this repo
  pyproject.toml, uv.lock   # Python 3.13 project managed by uv (locked)
  .env.example              # every setting; copy to .env (bootstrap does this)
  Makefile                  # the entrypoints above
  config/dbt/profiles.yml   # dbt profile, env-driven
  src/league_lab/           # config, db helpers, http archive, manifest, scoring, ingestion, CLI
    ingest/sleeper.py       #   league chain -> raw.sleeper_*  (JSONB payload + promoted columns)
    ingest/nflverse.py      #   release files -> raw.nfl_*     (18 datasets, typed, schema-drift tolerant)
    reports.py              #   weekly data packs (Markdown + CSV)
  dbt/                      # sources, staging, intermediate, marts, seeds, tests, macros
  app/                      # Streamlit explorer: Home, Player, Team Hub, Waiver Wire, Trends, Rankings, Matchups,
                            #   Trade Finder, League, Players, Receivers, Kickers, Data Status
  scripts/                  # bootstrap.sh, init_db.sql, nightly.sh, refresh.sh, backup.sh, sync_to_hosted.sh, restore_test.sh, launchd/
  tests/                    # pytest unit tests + a synthetic Sleeper fixture generator
  docs/                     # plan, project plan/backlog, runbook, data model, metrics, sources, limitations, status
  data/raw/                 # (git-ignored) replayable source archive
  backups/, logs/, .state/  # (git-ignored)
```

## The `league-lab` CLI

```
league-lab db migrate            create schemas + ops tables (idempotent)
league-lab db check              both roles connect; app role proven read-only
league-lab ingest sleeper        league chain, users, rosters, matchups, transactions, drafts, brackets, players
league-lab ingest nfl            nflverse datasets for --seasons (default LEAGUE_LAB_SEASONS_START..current)
league-lab ingest all            both
league-lab dbt <args>            dbt with the project's profile (build, test, run, docs generate ...)
league-lab refresh [--full]      sleeper + current NFL season (+ all seasons with --full) + dbt build
league-lab status                partition state, recent loads, failures
league-lab teams                 roster ids for --team
league-lab weekly-pack           Markdown + CSV facts for a week (+ --team for the private brief)
league-lab import-routes FILE    licensed routes-run CSV -> raw.routes_feed (--provider name)
league-lab fit-rankings          refit the baseline projection weights (--train 2019-2022) -> seed
league-lab backtest              score the rankings on held-out seasons (--seasons 2023-2025)
```

All ingestion accepts `--offline` (replay the on-disk archive, no network) and `--force`
(reload even when the checksum is unchanged).

## Sharing it

`docs/HOSTING.md`: publish the marts to a free hosted Postgres (`make sync-hosted`) and serve the
explorer from Streamlit Community Cloud. The Mac stays the pipeline; nothing raw leaves it.

## Attribution and licenses

NFL data © nflverse (nflverse-data releases) and the dynastyprocess crosswalk; league data from the
Sleeper public API. FTN charting is CC-BY-SA 4.0, attributed to *FTN Data via nflverse*; play-by-play and
participation are nflverse releases of NFL data.
This repository holds code and configuration only — never raw data, dumps, backups or secrets.
