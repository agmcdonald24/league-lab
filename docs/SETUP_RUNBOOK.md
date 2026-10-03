# Setup runbook (macOS, Apple Silicon)

Target machine (plan §2): Apple Silicon Mac, Homebrew, PostgreSQL 17 installed via Homebrew,
Python managed by uv (project-local 3.13; system Python untouched).

## 1. First run

```bash
cd ~/PycharmProjects/league-lab
./scripts/bootstrap.sh
```

What it does, in order (every step is safe to repeat):

1. Checks Homebrew, `psql` (installs `postgresql@17` if missing) and `uv` (installs if missing).
2. `brew services start postgresql@17` and waits for `pg_isready` on `localhost:5432`.
3. Writes `.env` from `.env.example` with two generated passwords (`chmod 600`). Existing `.env` is kept.
4. Runs `scripts/init_db.sql` as your macOS user (Homebrew's superuser): roles
   `league_lab_pipeline` (owner) and `league_lab_app` (read-only), database `league_lab`, schemas
   `raw`, `ops`, `staging`, `intermediate`, `analytics`, `analytics_seeds`, grants and default privileges.
5. `uv python install 3.13` and `uv sync --locked`.
6. `league-lab db migrate` (ops tables) and `league-lab db check` (proves the app role cannot write).
7. Ingests the Sleeper league chain and the previous + current NFL seasons (pilot).
8. `league-lab dbt build` (seeds, models, tests).

Then `make app` and open http://127.0.0.1:8501.

Flags: `--full` ingests every season from `LEAGUE_LAB_SEASONS_START` (2016) instead of the pilot;
`--skip-ingest` stops after step 6.

## 2. Day-to-day

| Want | Run |
|---|---|
| Refresh league + current season, rebuild, project, back up, publish | `make refresh` (= `scripts/refresh.sh` → `scripts/nightly.sh`) |
| The same pipeline exactly as GitHub Actions runs it (no backup) | `make nightly` (`NIGHTLY_SLEEPER_OFFLINE=1` skips live Sleeper) |
| Backfill all history | `make backfill` |
| Only Sleeper | `make ingest-sleeper` |
| Only some seasons | `make ingest-nfl SEASONS=2019-2021` |
| Rebuild models/tests | `make build` / `make test` |
| dbt docs site | `make docs` (port 8080) |
| Load status and failures | `make status` |
| Unit tests / lint | `make pytest` / `make lint` |
| Roster ids | `make teams` |
| Newsletter facts pack | `make weekly-pack WEEK=3 TEAM=2` → `reports/<league>/week_03/` |
| Backup now | `make backup` → `backups/league_lab_<stamp>.dump` |
| Test a backup | `./scripts/restore_test.sh backups/<file>.dump` |

### Schedule the daily refresh (optional)

```bash
mkdir -p logs
sed "s|__ROOT__|$PWD|g" scripts/launchd/com.leaguelab.refresh.plist > ~/Library/LaunchAgents/com.leaguelab.refresh.plist
launchctl load ~/Library/LaunchAgents/com.leaguelab.refresh.plist
```

Runs at 08:00 local time; launchd runs a missed job the next time the Mac wakes. `scripts/refresh.sh`
is `scripts/nightly.sh` (the pipeline GitHub Actions runs: archive replay, live Sleeper + current NFL
season, dbt build, projections, Sleeper's projections) plus a backup, into **the Mac's own database** (the
research console, `make app`, the weekly packs). Logs go to `logs/nightly.log` (every step
with its time and a summary) and `logs/refresh.log`. It refuses to start while another run holds
`.state/refresh.lock` (one writer; a lock left by a killed run is recognised by its pid and removed).
Manual `make refresh` is always fine.

**The hosted copy is GitHub's job** (Wave H: one writer): `docs/HOSTING.md` § 5 "Nightly on GitHub Actions"
(three repository secrets). This job does not publish to it — `sync-hosted` is skipped off GitHub Actions —
unless `LEAGUE_LAB_MAC_WRITES_HOSTED=1` is in `.env` (the fallback while Actions is down; disable the workflow
first). How to turn that on and off: HOSTING.md § "The Mac's launchd job".

### Upgrading an existing install (new datasets or models)

```bash
make sync            # if uv.lock changed
make ingest-nfl      # picks up newly registered datasets for all seasons
make build           # rebuild models + tests
```

Phase 2 (2026-09-26) adds three datasets: `pbp` (≈20 MB per season), `pbp_participation` (≈3–5 MB,
2016 → last completed season) and `ftn_charting` (≈0.5 MB, 2022+) — about 265 MB once, then only the
current season's files change. The current season's participation file does not exist until after the
postseason; the loader skips it (`season_lag`), so no failure is recorded for it. Expect the database to
grow by ≈1.1 GB. To load every play-by-play column instead of the core subset set
`LEAGUE_LAB_PBP_COLUMNS=all` in `.env` before ingesting.

### Rankings: backtest and refit

```bash
make backtest                 # scores 2023-2025 (a few seconds); fills the Rankings page scoreboard
make fit-rankings TRAIN=2019-2024 && make build && make backtest SEASONS=2025   # refit after a season, if wanted
```

The shipped seed was fitted on 2019–2022 and evaluated on 2023–2025. Refitting on more seasons is fine
but then the backtest must use seasons the fit never saw, or it stops meaning anything.

### Projection v2 (stat lines, per-league points, floor / ceiling)

```bash
make project                  # fit on completed seasons, project this season for every league, build its marts (~2 min)
make backtest-v2              # walk-forward 2021-2025 (~6 min): each season scored by a model trained on the seasons before it
```

`make refresh` (and the nightly job) runs `project` after the build, so the live board follows the
week's lines and injury reports. The Rankings page defaults to v2 and keeps the baseline formula as
the check; the backtest section shows both on the same held-out seasons.

### Importing a licensed routes file (optional)

```bash
uv run league-lab import-routes ~/Downloads/routes_2026.csv --provider pff
make build
```

CSV needs `season, week, routes` and one of `gsis_id | sleeper_id | pfr_id` (header names, any order;
extra columns ignored). Rows replace the provider's previous rows for that season. The Receivers and
Players pages then show **Routes / TPRR / YPRR** without the proxy label; identity is resolved through
`player_id_map`, never by name.

## 3. Verifying a fresh install (plan §9.1)

```bash
uv sync --locked                     # must succeed without network changes to the lock
make pytest                          # 21 tests, no database needed
make check                           # both roles; "read-only confirmed"
make build                           # all dbt tests pass (warnings are reconciliation reports, read them)
make status                          # every dataset has a success status
```

Reconciliation reports worth reading after the first real Sleeper load:

* `assert_recomputed_points_reconcile` (warn): players whose Sleeper points differ from
  scoring-settings × nflverse stats by more than 0.5. Expect a handful — stat corrections,
  Sleeper-only bonuses. Many rows for one week means a scoring key League Lab does not model
  (see `assert_unmapped_scoring_keys_are_known`).
* `assert_starter_points_sum_to_matchup_points` (warn): should be empty; a row means a
  commissioner override or a mid-week roster edit.
* `assert_standings_match_sleeper` (warn): computed W/L vs Sleeper's stored record for
  completed seasons; a difference usually means a median/bye rule League Lab doesn't model.

## 4. Configuration reference (`.env`)

| Variable | Meaning |
|---|---|
| `LEAGUE_LAB_DB_HOST/PORT/NAME/USER/PASSWORD` | pipeline role connection (ingestion + dbt) |
| `LEAGUE_LAB_DB_URL` | full DSN override (hosted Postgres later) |
| `LEAGUE_LAB_APP_DB_USER/PASSWORD`, `LEAGUE_LAB_APP_DB_URL` | read-only role for the explorer |
| `LEAGUE_LAB_SLEEPER_LEAGUE_ID` | newest league in the chain (`1389709692405551104`) |
| `LEAGUE_LAB_SEASONS_START` | first NFL season year to keep (2016) |
| `LEAGUE_LAB_DATA_DIR` | where `raw/` lives (default `<repo>/data`) |
| `DBT_PROFILES_DIR` | `config/dbt` |
| `PLAYERWIRE_API_URL` | PlayerWire's read API on this Mac (default `http://127.0.0.1:8790`; N2, `docs/PLAYERWIRE.md`) |
| `PLAYERWIRE_API_KEY` | PlayerWire's bearer key for League Lab (`python3 -m pw client create --name league-lab --scopes read`) |
| `PLAYERWIRE_WRITER_PASSWORD` | the password `make playerwire-schema` sets for the hosted role `playerwire_writer` |
| `PLAYERWIRE_HOSTED_URL` | `postgresql://playerwire_writer:<password>@<Neon host>/neondb?sslmode=require`: the briefs' writer (`make playerwire-sync`, launchd every 15 minutes) |

Running plain `dbt` instead of `league-lab dbt` (from the repo root, so the relative
`DBT_PROFILES_DIR` resolves): `set -a; source .env; set +a; dbt build --project-dir dbt`.

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `pg_isready` never succeeds | `brew services list`; `tail /opt/homebrew/var/log/postgresql@17.log`; a stale `postmaster.pid` in `/opt/homebrew/var/postgresql@17` after a crash — delete it and restart the service |
| `Cannot connect to the 'postgres' maintenance database as <you>` | cluster initialised with another superuser: `psql -U postgres -d postgres -v pipeline_pw="'...'" -v app_pw="'...'" -f scripts/init_db.sql`, then `./scripts/bootstrap.sh --skip-ingest` |
| `password authentication failed` | `.env` and the roles disagree: re-run `scripts/init_db.sql` with the `.env` passwords (`-v pipeline_pw=... -v app_pw=...`) |
| `app role could CREATE in analytics` | grants missing: re-run `scripts/init_db.sql` |
| nflverse `404` for the current season early in September | upstream has not published that file yet; the partition is recorded as failed and retried next refresh |
| `contract_failed: missing required columns` | upstream schema change. Look at the file in `data/raw/nflverse/...`, adjust `required` in `ingest/nflverse.py` and the staging model, then `--force` |
| Sleeper `429` | the client backs off automatically; run again later |
| dbt `relation ... does not exist` for `raw.*` | ingestion never loaded that table; `make status` |
| Streamlit shows "Cannot reach the analytics database" | check `LEAGUE_LAB_APP_DB_*` in `.env`, PostgreSQL running, grants |
| `uv sync --locked` fails | the lock and `pyproject.toml` diverged; `uv lock` then commit both |

## 6. Where things live on disk

* Raw archive: `data/raw/sleeper/<league_id>/...json.gz`, `data/raw/nflverse/<dataset>/<file>.parquet`
  with `*.meta.json` sidecars (URL, ETag, fetch time = when those bytes were first fetched, last check,
  sha256). Replay with `--offline`; a replayed partition keeps the archive's fetch time as its "loaded" time.
* Manifest: `ops.load_manifest` (every attempt) and `ops.source_partition` (current state).
* Backups: `backups/` (7 daily + weekly). Choose an off-machine destination (O05) and copy them there.
* Footprint today: raw archive ≈ 60 MB for 2016–2026; database ≈ 1 GB after full build.

## 7. Sharing later (Phase 4, sketch)

The explorer reads only `analytics.*` through a DSN. To share: create a hosted Postgres (Neon
free tier), `pg_dump -n analytics -n analytics_seeds` → restore there, deploy `app/` to Streamlit
Community Cloud with `LEAGUE_LAB_APP_DB_URL` as a secret. No code change in the app is required;
`docs/PROJECT_PLAN.md` P4 has the tasks.
