# Hosting League Lab for the league (beta)

Goal: a link leaguemates can open. Cost: **$0** on free tiers. One nightly pipeline
(`scripts/nightly.sh`) refreshes the data and publishes the marts to a hosted Postgres; it runs on
GitHub Actions (§5; the Mac is then optional) or on your Mac (launchd, 08:00). Streamlit Community
Cloud serves the explorer from GitHub against that database.

```
GitHub Actions (§5) or Mac: scripts/nightly.sh
  archive replay → live fetch → dbt build → project → sync_to_hosted.sh ──► hosted Postgres (marts only, ~300 MB)
                                                                                    ▲
GitHub repo ──► Streamlit Community Cloud (app/Home.py) ────────────────────────────┘  read-only role
```

What leaves your machine: the analytics marts the pages and packs read (the script derives the list
from the code — 40 relations, ~320 MB), the seeds and the `ops` schema — never `raw`, `staging`,
`intermediate`, the play-level tables, `.env` or the archive.

## 1. Hosted Postgres (15 minutes)

Either provider works; both have a free tier that fits (~320 MB today, +≈30 MB per season; Neon's cap is 0.5 GB).

**Neon** (recommended: cheap, Postgres 17, no sleeping issues for a read-only workload)
1. neon.tech → sign up → New project → name `league-lab`, region closest to you, Postgres 17.
2. Dashboard → *Connection string* → choose the **owner** role (`neondb_owner`) → copy the URL.
   It looks like `postgresql://neondb_owner:...@ep-...-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require`.
   Use the **direct** (non-pooler) host for the sync; either for the app.

**Supabase** (alternative): New project → Project settings → Database → connection string (URI,
"session" mode, the `postgres` role). Same steps below.

Then in `.env` on the Mac:

```
LEAGUE_LAB_HOSTED_ADMIN_URL=postgresql://neondb_owner:...@ep-....neon.tech/neondb?sslmode=require
LEAGUE_LAB_HOSTED_APP_PASSWORD=<a long random password for the read-only app role>
```

Publish:

```bash
make sync-hosted        # ~1-3 minutes: dumps the marts the pages read, creates the read-only role, restores
```

Every `make refresh` (and the nightly launchd job) now ends with the same sync. If the sync fails
the local data is untouched; run `make sync-hosted` again.

The app's connection string is the same host and database with the **app** role:

```
postgresql://league_lab_app:<LEAGUE_LAB_HOSTED_APP_PASSWORD>@<host>/<db>?sslmode=require
```

## 2. GitHub repository (10 minutes)

Streamlit Community Cloud deploys from GitHub. The repo holds code and config only; `.gitignore`
already excludes `.env`, `data/`, `backups/`, `logs/`, `reports/`, `.state/` and every secrets file.

```bash
cd ~/PycharmProjects/league-lab
git init && git add -A && git commit -m "League Lab beta"
gh repo create league-lab --private --source=. --push       # or create it on github.com and push
```

Check before pushing: `git status --ignored | grep -E "\.env$|data/"` must list them as ignored.

## 3. Streamlit Community Cloud (10 minutes)

1. share.streamlit.io → sign in with GitHub → **New app**.
2. Repository `you/league-lab`, branch `main`, **main file path `app/Home.py`**.
3. *Advanced settings* → Python 3.13 → **Secrets** (TOML):

   ```toml
   LEAGUE_LAB_APP_DB_URL = "postgresql://league_lab_app:<password>@<host>/<db>?sslmode=require"
   LEAGUE_LAB_APP_PASSWORD = "the-beta-password-you-give-people"     # optional gate; remove for open access
   LEAGUE_LAB_FEEDBACK_URL = "https://forms.gle/..."                  # optional; shows a sidebar button
   ```

4. Deploy. **Every release must change `app/requirements.txt`** (the `# release: <sha>` line the PO bumps in
   each bundle): Community Cloud restarts the app only when that file changes. A push that only changes
   `app/lib/*.py` is hot-reloaded page by page against the library modules already in memory, and every
   page fails with `ImportError` / `unexpected keyword argument` until someone clicks **Reboot app**
   (app menu, top right) — which is also the fix if it ever happens. Dependencies come from `app/requirements.txt` (the explorer's runtime only; Community
   Cloud uses the entrypoint directory's file before the repo's `uv.lock`). First build ≈ 2 minutes.
5. Settings → *Sharing*: **Public** (anyone with the link; the password gate keeps it to invitees)
   or **Private** (viewers must sign in with an email you list — up to a handful on the free tier).

The URL is `https://<app-name>.streamlit.app`; you can rename it in the app settings.

## 3b. Adding another Sleeper league

```
LEAGUE_LAB_SLEEPER_LEAGUE_ID=1389709692405551104,<other league id>     # in .env; first id = reference scoring
make ingest-sleeper && make build && make sync-hosted
```

The league id is the number in the Sleeper URL (`sleeper.com/leagues/<id>/...`). Its whole chain of
previous seasons is fetched too. Leaguemates of the second league pick it in the sidebar; the link
`?league=<id>&team=<roster>` opens straight on their team. League pages use that league's scoring;
NFL pages use the reference league's, and the sidebar lists any scoring differences.

After the build, look at two tests in the output: `assert_unmapped_scoring_keys_are_known` (a warning
means the new league uses a scoring key League Lab cannot recompute — `METRICS.md` lists what is
modelled) and `assert_recomputed_points_reconcile` (rows = player-weeks where the recomputed points
differ from Sleeper's by more than 0.5; a handful per season is stat corrections, hundreds means a
key is modelled wrong).

## 4. What to expect

* **Freshness** = the last nightly run + sync (the banner on every page says when): GitHub Actions
  starts at 07:37 New York time (§5); the Mac's launchd job at 08:00, or when the Mac wakes.
* **Cold start**: Community Cloud sleeps an app after a few days without visitors; the first
  visitor waits ~30 s. Neon free tier suspends compute after 5 minutes idle; the first query
  waits ~1 s.
* **Limits**: 1 GB RAM on Community Cloud is plenty (pages read marts, never raw). Neon free:
  0.5 GB storage, 190 compute-hours/month — a read-only explorer for a 10-team league uses a
  fraction of that. If the marts outgrow 0.5 GB (several seasons from now), Neon's paid tier is
  ~$19/month; before that, the play-level tables are already excluded and `fct_player_game` can be
  slimmed.
* **Size (Neon free tier: 512 MB per project).** On 2026-09-30 the full history no longer fit and a sync died
  mid-restore at that limit. The sync now publishes the heavy per-player-game tables (`fct_player_game`,
  `mart_player_week_rankings`, `mart_player_context`, `mart_player_recent_form`, `mart_player_expected_points`,
  `mart_player_trends`, `mart_player_season`, `mart_receiver_vs_cb`) for the newest `LEAGUE_LAB_HOSTED_SEASONS`
  seasons only (default 3); everything else goes in full. The hosted copy went from >512 MB to ~265 MB. The Mac
  keeps the full history, so Players / Receivers / Trends season pickers on the hosted app list the last three
  seasons. The sync prints the expected size and warns above 440 MB; lower the window or trim the list if it does.
* **A refresh in progress**: the sync drops the previous copy and restores the new one (free
  tiers cannot hold two copies at once — Neon caps a project at 0.5 GB), so for the length of the
  restore (a minute or two) pages say "marts not built on this machine yet" instead of failing.
  The nightly job runs around 08:00, before anyone is looking. If a restore ever fails midway, run
  `make sync-hosted` again; local data is never touched, and the small `ops` schema (the decision
  record the GitHub nightly restores from here) is swapped inside the restore transaction, so it
  is never half-gone.
* **Security model**: the hosted role is read-only (`default_transaction_read_only`), sees only the
  three published schemas and has a 30 s statement timeout. The beta password is a closed door for
  a link, not authentication; use Community Cloud's private sharing if that matters.

## 5. Nightly on GitHub Actions

`.github/workflows/nightly.yml` runs the whole nightly on a free GitHub runner: a throwaway
Postgres 17, the raw archive restored from the Actions cache, live Sleeper + nflverse for the
current season, `dbt build`, projection v2, and the sync to Neon. Every step is in
`scripts/nightly.sh`, the same script the Mac runs (`make nightly`), so anything that fails there
can be reproduced on the Mac. Once it runs green, the Mac is optional.

### Set it up once (5 minutes)

1. The workflow has to be on `main`: GitHub runs schedules from the default branch only.
2. GitHub → the repository → **Settings → Secrets and variables → Actions → New repository secret**,
   three times:

   | Secret | Value |
   |---|---|
   | `LEAGUE_LAB_SLEEPER_LEAGUE_ID` | the same list as the Mac's `.env`, e.g. `1389709692405551104,1321941740235550720` (first id = the reference scoring) |
   | `LEAGUE_LAB_HOSTED_ADMIN_URL` | the Neon **owner** connection string, direct (non-pooler) host, as in §1 |
   | `LEAGUE_LAB_HOSTED_APP_PASSWORD` | **the same** password as in the Mac's `.env`. The sync sets the read-only role's password to this value on every run; a different one locks the Streamlit app out until you change its secret too |

   Nothing else: the runner's own database, roles and passwords are created fresh on every run.
   Without `LEAGUE_LAB_HOSTED_ADMIN_URL` a run builds everything and publishes nothing (a dry run,
   flagged with a warning).
3. Run it once by hand (next section) and watch it. The first run finds no archive in the cache
   and downloads the whole history from GitHub releases (~280 MB; about a minute more than a normal
   run: 23 MB/s from a sandbox, faster from a runner). Budget 15–20 minutes, plus ~15 if the hosted
   copy has no backtests yet (below).
4. Decide what the Mac does (last section below). **One writer**: two syncs at once drop each
   other's schemas mid-restore.

### Run it by hand

**Actions** tab → **nightly** (left) → **Run workflow** → branch `main` → **Run workflow**. Two
optional tick boxes: *"Also re-check every historical NFL season live"* is the monthly audit
(`--full`: every old season is asked again with a conditional request, so unchanged files cost one
round trip); *"Recompute both backtests"* after a change to the projection model or its features.
From a terminal: `gh workflow run nightly` then `gh run watch`.

It also runs by itself every day at **11:37 UTC = 07:37 in New York on daylight time** (06:37 on
standard time, November to March; GitHub's cron has no time zones). GitHub may start a scheduled
run a few minutes late. A run takes about 15 minutes (§ Cost), so the hosted copy is fresh by
about 08:00 EDT. `concurrency: nightly` makes a second run wait for the first; they never overlap.

### Reading a failed run

* The run's **summary page** shows a table of every step with its time and result, the dbt
  `Done. PASS=… WARN=… ERROR=…` line and the sync's `verified: all N page relations` line, and an
  annotation naming the failing step.
* In the job log, open **Nightly pipeline (scripts/nightly.sh)**: each nightly step is a
  collapsible group that ends with `step <name>: ok in 1m23s` or `step <name>: FAILED (exit 1)`.
* **Artifacts** (bottom of the run page, kept 14 days): `nightly-logs` (`nightly.log`, `sync.log`,
  `run_results.dbt-build.json` for the full build) and `dbt-run-results`.
* What stops a night and what does not:

  | Failing step | What happened | What to do |
  |---|---|---|
  | `fetch-sleeper`, `fetch-nflverse-current` | Sleeper or nflverse was down, or a file is not published yet | Nothing. The night carried on with the archive's copy of that partition, published, and is red so you notice. The next night retries. With no archive (first run, lost cache) there is no copy to fall back on: the night stops here instead ("no archive to fall back on"); re-run |
  | `fetch-nflverse-history` | a partial or empty cache and a download failed | Re-run (button on the run page). Stops before the build so a copy with holes in the history is never published |
  | `dbt-build` | a test failed on new data | The failing test is in the log and in `run_results.dbt-build.json`; reproduce with `make build` on the Mac. The hosted copy keeps the previous night |
  | `backtests`, `projection-marts` | projection code or its data | Reproduce with `make project`. Nothing was published |
  | `restore-state` | the hosted copy could not be read, or the decision record (`ops.projections`, `ops.projection_drift`) did not copy | Nothing was published: refitting every played week blind and publishing it would overwrite the record with refit values. Check Neon and the `HOSTED_*` secrets; re-run. A hosted copy that is reachable but has lost the record is repaired from the archive's copy (`data/raw/record/`, in the cache) without stopping |
  | `project` | projection code or its data | Reproduce with `make project`. The night carried on with the previous projections and lineups (on the runner: the ones restore-state copied back from the hosted copy) and published them again. It stops before publishing only when no projections exist anywhere yet |
  | `save-record` | the archive directory is not writable | The night carried on and published; the cache just has no fresh copy of the record that night |
  | `sync-hosted` | Neon unreachable, or a wrong `HOSTED_*` secret | Check the two secrets; re-run. If the restore died midway, pages say "marts not built yet" until a sync completes (§4) |
  | *Roles, database and .env* (before the pipeline) | a missing or malformed secret | The annotation names it |

### The archive cache

* **What**: `data/raw`, every nflverse file and Sleeper payload fetched so far (~280 MB, +≈25 MB a
  season). It is the only thing carried from one run to the next: the runner's database is
  rebuilt from it every night (replaying it takes about a minute; then only the current season is
  fetched live). A replayed partition keeps the time its file was fetched, so the "loaded" times on
  the pages (and the stale-injury warning) show when the data arrived, not when the runner
  replayed it.
* **Keys**: `league-lab-raw-v1-<season>-<fingerprint>`, the fingerprint being a hash of every file.
  A run restores the newest entry for this season (else the newest of any season, so a new season
  starts from last season's archive) and saves a new entry only when the fingerprint changed:
  most nights in season (new Sleeper weeks, the current season's files), rarely in the off-season
  (a sidecar that only records a new ETag or the last check does not count).
* **Budget**: GitHub keeps 10 GB of cache per repository and evicts entries nobody restored for 7
  days, so in season about seven ~280 MB entries live at once (~2 GB), plus uv's package cache
  (a few hundred MB). Well inside 10 GB.
* **Losing it** (eviction, or deleting it under **Actions → Caches**) costs one slow night, never
  data: the next run downloads the history again and Sleeper's live fetch reloads the whole chain.

What the archive cannot rebuild: the two backtests behind the Rankings scoreboards
(`league-lab backtest`, `backtest-v2`), the **decision record** (`ops.projections`: a league-week's
board is frozen at its first kickoff and never rewritten, plan B5; and the drift history scored on
it, `ops.projection_drift`) and last night's lineups (`ops.lineups`, `ops.lineup_totals`). The
runner's database is new every night, so it copies all of them back from the hosted copy (where
the previous sync put them: the sync publishes the whole `ops` schema) before the build. Without
that restore every played week would be refit from scratch each night and the "kickoff board"
share on Rankings would read 0%. The record gets two more protections, because nothing can
recompute it: the night **stops** when the hosted copy cannot be read or the copy fails (nothing is
published, so nothing is overwritten), and after every successful `project` the two record tables
are also written to `data/raw/record/` — inside the cached archive — so a hosted copy that has lost
them (a restore that died midway, though the sync now swaps `ops` inside its transaction) is
repaired from that copy. The backtests are recomputed only when neither place has them (the first
run, if the hosted copy never had them), when the projection model's version changed, or when a
manual run ticks *"Recompute both backtests"*; `backtest-v2` then adds about 15 minutes to that
run. The lineups are restored only so a night whose `project` fails republishes a consistent copy;
`project` re-solves them from the frozen projections and Sleeper's rosters. A licensed routes file imported on the Mac
(`import-routes`) is not in the archive either; while GitHub publishes, the pages show the routes
proxy.

### Weather in the nightly (plan D3)

`league-lab ingest weather` (Open-Meteo: free, no key, reachable from the Mac and from Actions) is not
in `scripts/nightly.sh` yet; the product owner adds these two lines (the script is not D3's to edit).
Both read `raw.nfl_schedules`, so each goes **after** its nflverse counterpart:

```bash
# 1. replay — after the replay-nflverse-current block
SOFT_WHY="weather features fall back to the schedules' observed temp / wind" soft replay-weather uv run league-lab ingest weather --offline
# 2. live — after the fetch-nflverse-current line
SOFT_WHY="the archived weather and the earlier forecasts stay" soft fetch-weather uv run league-lab ingest weather --forecast
```

* **Replay** rebuilds `raw.nfl_weather` on the runner's fresh database from the cached files (every
  archive file and every forecast ever fetched); with no weather archive yet it loads nothing and
  exits 0. **Live** fetches only what is new: an archive call for a stadium-season only when a
  played game (older than the archive's 5-day delay) is not in its file yet — about one per home
  game in season, nothing for completed seasons — and one forecast call per stadium with an
  open-air game in the next 16 days (~20–25 a night in season). Both are `soft`: a failure never
  stops the night (past games keep their archived weather, upcoming ones their last forecast or
  "unknown").
* **The first night with the lines** (or a lost cache) backfills the archive: 280 calls for every
  stadium-season 2016–2026, spaced 1.5 s apart — **about 8 extra minutes once**. On the Mac, run
  `uv run league-lab ingest weather --forecast` once by hand first (the backfill) so the first
  nightly is a normal one.
* **Archive cache**: `data/raw/open_meteo/archive/<season>/<stadium_id>.json.gz` — one small file per
  stadium-season (~280 files, ~20 KB each, ~6 MB for 2016–2026, +~0.5 MB a season), and
  `data/raw/open_meteo/forecast/<season>/<stadium_id>/<time>.json.gz` — one ~1 KB file per stadium per
  night with an upcoming open-air game (~3,500 files, ~3 MB a season; each with its `.meta.json`
  sidecar). The forecasts are never re-fetchable (a forecast is only ever available before the
  game), so they are the one part of the weather archive that a lost cache cannot rebuild: losing
  it costs the train / serve gap measurement its history, not the board.

### Cost

Measured in a 2-CPU / 7 GB sandbox (the size of GitHub's standard runner for private
repositories) against a fresh database, the way the runner starts every night: `nightly.sh` took
**10 min 09 s** with the backtests restored from the hosted copy (step times in `docs/STATUS.md`,
Wave B / B6). Add what the sandbox could not do: the live Sleeper fetch (~1–2 min), the restore
into Neon instead of a local database (~1–2 min) and the runner's setup and cache transfer
(~3 min): **about 15 minutes a run**, 30 runs ≈ **450 minutes a month**. GitHub Free includes
**2,000 minutes a month** for private repositories, so that is under a quarter, with room for
manual runs and the odd backtest recompute (+15 min). A public repository would run free. If the
minutes ever run out, GitHub stops runs until the month resets rather than charging, unless you
have set up a paid budget (Settings → Billing). Logs and artifacts are a few MB (500 MB of
artifact storage is included).

### The Mac's launchd job

Optional once the Actions run is green. Pick one:

* **Retire it**: `launchctl unload ~/Library/LaunchAgents/com.leaguelab.refresh.plist && rm ~/Library/LaunchAgents/com.leaguelab.refresh.plist`
  (the reinstall lines are in `docs/SETUP_RUNBOOK.md` § 2).
* **Keep it for local data only** (your own database for `make app`, weekly packs, backtests):
  delete `LEAGUE_LAB_HOSTED_ADMIN_URL` from the Mac's `.env`. The job keeps refreshing the Mac
  and never publishes.

`make sync-hosted` from the Mac still works as a manual fallback, while no Actions run is in
progress (the Actions tab shows it).

## Licences to keep in mind when sharing

* nflverse data: free to use with attribution (kept on Home → Data & attribution).
* FTN Data charting via nflverse: **CC BY-SA 4.0** — first-read shares and other charting-derived
  numbers are adaptations and carry the same licence and attribution (they do).
* Sleeper: public, read-only API; league data belongs to the league.
* Do not redistribute the raw files; the hosted copy holds only derived marts.
