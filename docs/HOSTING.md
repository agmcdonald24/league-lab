# Hosting League Lab for the league (beta)

Goal: a link leaguemates can open. Cost: **$0** on free tiers. One nightly pipeline
(`scripts/nightly.sh`) refreshes the data and publishes the marts to a hosted Postgres (Neon).
**One writer (Wave H): only GitHub Actions publishes** (§5, every morning at 07:37 New York time); the
Mac's launchd job (08:00) runs the same pipeline for the Mac's own database — the research console
(`make app`), the weekly packs — and does not publish. The product API on the server (`docs/DEPLOY.md`)
and Streamlit Community Cloud read that database with a read-only role.

```
GitHub Actions (§5): scripts/nightly.sh                                   the ONE writer
  archive replay → live fetch → dbt build → project → Sleeper's projections
  → save the record → sync_to_hosted.sh ──► hosted Postgres (Neon; marts + ops, ~200 MB)
                                                  ▲               ▲
              the API on the server (DEPLOY.md) ──┘               └── Streamlit Community Cloud (app/Home.py)
                                                  read-only role (league_lab_app)
Mac (launchd 08:00): scripts/refresh.sh = the same nightly + a backup, into the Mac's own database; no publish
```

What leaves the runner: every analytics relation the readers of the hosted copy name — the Streamlit console
(`app/`, the weekly packs) and the product API (`api/` and the `src/league_lab` modules it imports) — found
in the code, not listed by hand (§ "What the hosted copy holds"); the views and what they read; the seeds and
the `ops` schema (the decision record) — never `raw`, `staging`, `intermediate`, the play-level tables, `.env`
or the archive.

## 1. Hosted Postgres (15 minutes)

Either provider works; both have a free tier that fits (~320 MB today, +≈30 MB per season; Neon's cap is 0.5 GB).

**Neon** (recommended: cheap, no sleeping issues for a read-only workload). The project runs **Postgres 18** (18.6 on
2026-10-02; the Actions runner's service and client follow it — `nightly.yml`; the Mac's own Homebrew 17 is fine: it
never dumps from Neon in normal operation).
1. neon.tech → sign up → New project → name `league-lab`, region closest to you, the current Postgres.
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

Publish the first copy from the Mac (before the GitHub nightly exists, the Mac is the writer — say so):

```bash
LEAGUE_LAB_MAC_WRITES_HOSTED=1 make sync-hosted   # ~1-3 minutes: dumps the marts the readers name, creates the read-only role, restores
```

From then on GitHub Actions publishes every morning (§5). Without `LEAGUE_LAB_MAC_WRITES_HOSTED=1` the
sync refuses on the Mac ("GitHub Actions is the one writer", exit 7, nothing touched): a publish from the
Mac would replace the decision record GitHub keeps on the hosted copy with the Mac's. If the sync fails the
local data is untouched; run it again.

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
make ingest-sleeper && make build                                        # the Mac's own database
```

For the hosted copy: GitHub → Settings → Secrets and variables → Actions → `LEAGUE_LAB_SLEEPER_LEAGUE_ID` →
**Update** with the same list, then Actions → nightly → **Run workflow** (§5). (Any league works in the
product app without this: it reads Sleeper on demand. A house league gets the nightly's marts too.)

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

* **Freshness** = the last GitHub nightly (the banner on every page says when): it starts at 07:37 New
  York time (§5) and publishes by about 08:00. The Mac's launchd job no longer publishes.
* **Cold start**: Community Cloud sleeps an app after a few days without visitors; the first
  visitor waits ~30 s. Neon free tier suspends compute after 5 minutes idle; the first query
  waits ~1 s.
* **Limits**: 1 GB RAM on Community Cloud is plenty (pages read marts, never raw). Neon free:
  0.5 GB storage, 190 compute-hours/month — a read-only explorer for a 10-team league uses a
  fraction of that. If the marts outgrow 0.5 GB (several seasons from now), Neon's paid tier is
  ~$19/month; before that, the play-level tables are already excluded and `fct_player_game` can be
  slimmed.
* **Size (Neon free tier: 512 MB per project).** On 2026-09-30 the full history no longer fit and a sync died
  mid-restore at that limit. The sync publishes the heavy per-player-game tables (`fct_player_game`,
  `fct_player_game_league`, `mart_player_week_features`, `mart_player_week_rankings`, `mart_player_context`,
  `mart_player_recent_form`, `mart_player_expected_points`, `mart_player_trends`, `mart_player_season`,
  `mart_receiver_vs_cb`) for the newest `LEAGUE_LAB_HOSTED_SEASONS` seasons only (default 3: 2024–2026); everything
  else goes in full. **~200 MB** on 2026-10-02 (sandbox, the PO's data: 101.6 MB windowed + 98.3 MB in full,
  `ops` 30 MB of it; the database 200 MB) — down from ~265 MB + F1's 14 MB, because the two tables Wave H added to
  the window (`fct_player_game_league` 52 MB, `mart_player_week_features` 68 MB in full) are only ever read for
  recent seasons. The Mac keeps the full history, so season pickers on the hosted apps list the last three
  seasons. The sync prints the expected size before it touches anything, warns above 440 MB and **refuses above
  480 MB** (`LEAGUE_LAB_HOSTED_MAX_MB`; exit 6, the hosted copy keeps the last publication): lower the window or
  add a table to the list if it does. +≈30 MB a season.
* **A refresh in progress**: the sync drops the previous copy and restores the new one (free
  tiers cannot hold two copies at once — Neon caps a project at 0.5 GB), so for the length of the
  restore (a minute or two) pages say "marts not built on this machine yet" instead of failing.
  The nightly job runs around 07:40, before anyone is looking. If a restore ever fails midway, re-run the
  workflow (Actions → nightly → Run workflow); local data is never touched, and the small `ops` schema (the decision
  record the GitHub nightly restores from here) is swapped inside the restore transaction, so it
  is never half-gone.
* **Security model**: the hosted role is read-only (`default_transaction_read_only`), sees only the
  three published schemas and has a 30 s statement timeout. (U-1: plus `INSERT, SELECT` on the one table
  `usage.events`, written in its own explicit read-write transaction — § "Usage".) The beta password is a closed door for
  a link, not authentication; use Community Cloud's private sharing if that matters.

## 5. Nightly on GitHub Actions

`.github/workflows/nightly.yml` runs the whole nightly on a free GitHub runner: a throwaway
Postgres 18 (Neon's major: restore-state dumps from Neon with the runner's `pg_dump`, which refuses a newer server),
the raw archive restored from the Actions cache, live Sleeper + nflverse for the
current season, `dbt build`, projection v2, Sleeper's own projections, and the sync to Neon. Every step is in
`scripts/nightly.sh`, the same script the Mac runs (`make nightly`), so anything that fails there
can be reproduced on the Mac. **It is the one writer of the hosted copy** (Wave H): the beta must not depend on
the Mac being awake. The Mac keeps its own database (last section).

**PlayerWire's briefs (N2) — proposed: one writer per schema.** The hosted database also holds schema `playerwire`,
written every 15 minutes by the Mac's `scripts/playerwire_sync.py` as role `playerwire_writer` (which can write
nothing else); this nightly never dumps, drops, grants or audits it, and nothing in it references `analytics`. The
rule above then reads "one writer per schema": Actions for `analytics`, `analytics_seeds` and `ops`, the Mac for
`playerwire`. **Awaiting Andrew's confirmation**; the reasoning and the checks are in `docs/PLAYERWIRE.md` § "One
writer per schema".

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
   and downloads the whole history from GitHub releases (~280 MB, 52 s on a runner) and every season's weather
   (7 m 39 s: the one step that is slow without the archive). Measured 2026-10-02 (run #5, the first green one):
   **23 m 42 s** end to end, `dbt-build` 9 m 00 s, `project` 3 m 58 s, `sync-hosted` 18 s; add ~15 min if the hosted
   copy has no backtests yet (below). Normal nights replay the archive and take about 15.
4. Nothing to do on the Mac: its launchd job stops publishing by itself (last section). **One writer**: two
   syncs at once drop each other's schemas mid-restore, and a Mac publish would replace the record kept here.

### Run it by hand

**Actions** tab → **nightly** (left) → **Run workflow** → branch `main` → **Run workflow**. Two
optional tick boxes: *"Also re-check every historical NFL season live"* is the monthly audit
(`--full`: every old season is asked again with a conditional request, so unchanged files cost one
round trip); *"Recompute both backtests"* after a change to the projection model or its features.
From a terminal: `gh workflow run nightly` then `gh run watch`.

It also runs by itself every day at **11:37 UTC = 07:37 in New York on daylight time** (06:37 on
standard time, November to March; GitHub's cron has no time zones). GitHub may start a scheduled
run a few minutes late — and now and then it drops one outright (2026-10-03: no run, no log). So there is a
**backup time, 13:07 UTC (09:07 EDT)**: a ten-second `gate` job first asks GitHub whether a nightly already
succeeded today (UTC) and skips the rest when one has, so a normal day costs nothing; when the 11:37 run was
dropped, the backup publishes by about 09:30 EDT. A manual run is never skipped. A run takes about 15 minutes
(§ Cost), so the hosted copy is fresh by about 08:00 EDT. `concurrency: nightly` makes a second run wait for
the first; they never overlap.

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
  | `restore-state` | the hosted copy could not be read, or the decision record (`ops.projections`, `ops.projection_drift`, and the NFL-wide boards `ops.projection_lines`, `ops.projection_ranges`, `ops.kd_lines`, `ops.kd_ranges`) did not copy | Nothing was published: refitting every played week blind and publishing it would overwrite the record with refit values. Check Neon and the `HOSTED_*` secrets; re-run. A hosted copy that is reachable but has lost the record — or never had one of its tables (a warning, not a failure) — is repaired from the archive's copy (`data/raw/record/`, in the cache) without stopping |
  | `project` | projection code or its data | Reproduce with `make project`. The night carried on with the previous projections and lineups (on the runner: the ones restore-state copied back from the hosted copy) and published them again. It stops before publishing only when no projections exist anywhere yet |
  | `grade-odds` | the week's odds could not be graded | Nothing urgent: `/api/status` says `odds_grades: null`; reproduce with `uv run league-lab grade-odds --no-write` |
  | `save-record` | the archive directory is not writable | The night carried on and published; the cache just has no fresh copy of the record that night |
  | `sync-hosted` | Neon unreachable, or a wrong `HOSTED_*` secret; or the copy would be over the size budget (`over the 480 MB budget`, nothing touched); or a relation a page or the API reads is missing after the restore (`missing relations the readers name`) | Check the two secrets; re-run. Over the budget: § 4 "Size". If the restore died midway, pages say "marts not built yet" until a sync completes (§4) |
  | *Roles, database and .env* (before the pipeline) | a missing or malformed secret | The annotation names it |
  | `restore-state` with `pg_dump: error: aborting because of server version mismatch` | Neon moved to a newer Postgres major than the runner's client | In `nightly.yml`, raise `image: postgres:<N>` and `postgresql-client-<N>` / `/usr/lib/postgresql/<N>/bin` to Neon's major (run #4, 2026-10-02: Neon 18.6 vs client 17) |

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
(`league-lab backtest`, `backtest-v2`), the **decision record** — `ops.projections` (a house league-week's
board is frozen at its first kickoff and never rewritten, plan B5), the drift history scored on it
(`ops.projection_drift`) and, since Wave H, the NFL-wide boards the product API prices every league from
(`ops.projection_lines`, `ops.projection_ranges`, `ops.kd_lines`, `ops.kd_ranges`, frozen the same way, plan F1)
— and last night's lineups (`ops.lineups`, `ops.lineup_totals`). The runner's database is new every night, so it
copies all of them back from the hosted copy (where the previous sync put them: the sync publishes the whole
`ops` schema) before the build. Without that restore every played week would be refit from scratch each night
and the "kickoff board" share on Rankings would read 0%.

**The record rule** (`RECORD_TABLES` in `scripts/nightly.sh`). The six record tables get more protection,
because nothing can recompute them:

1. **Cannot read the hosted copy** (Neon down, a wrong secret): the night **stops** before anything is built
   or published, so nothing is overwritten. Re-run when Neon answers.
2. **A copy that fails midway** (fewer rows arrive than the hosted copy has): the night stops too.
3. **The hosted copy is reachable but has lost a record table's rows** (a restore that died midway, though the
   sync now swaps `ops` inside its transaction): after every successful `project` the record tables are also
   written to `data/raw/record/` — inside the cached archive (~5 MB compressed) — and that copy is used.
4. **The hosted copy does not have the table at all** (it was never published there: the first night after a
   table joins the record, or a hosted copy older than the table): said so in the log, and treated like case 3
   — a database that has rows keeps them ("kept (the hosted copy does not have this table yet: the next sync
   publishes it)"), else the archive's copy, else the record starts that night with an Actions warning (played
   weeks come back as refit values, except the frozen QB–TE lines and the two house leagues' ranges, which
   `project` re-seeds from `ops.projections`). Stopping there instead would stop every night until someone
   published the table by hand. In the sandbox (2026-10-02): a fresh database against a hosted copy without
   the four NFL-wide tables restored the other 11 tables and went on (the pre-Wave-H code stopped the night at
   `ops.projection_lines: relation does not exist`); with the archive's copy present it restored 9,911 / 49,555
   / 1,088 / 5,440 rows from it; against an unreachable hosted copy it still stops.

Not in the record: `raw.sleeper_projections` (Sleeper's own projections, the other side of "Our record"). The
hosted copy never holds `raw`, and its durable copy is already the archive — every snapshot is one file in
`data/raw/sleeper/projections/`, written once, kept in the Actions cache, replayed into the table every night
(`replay-projections`). A database dump next to them would live and die with the same cache. The second copy
is the Mac's own archive: its local nightly pulls the same snapshots.

The backtests are recomputed only when neither place has them (the first
run, if the hosted copy never had them), when the projection model's version changed, or when a
manual run ticks *"Recompute both backtests"*; `backtest-v2` then adds about 15 minutes to that
run. The lineups are restored only so a night whose `project` fails republishes a consistent copy;
`project` re-solves them from the frozen projections and Sleeper's rosters. A licensed routes file imported on the Mac
(`import-routes`) is not in the archive either; while GitHub publishes, the pages show the routes
proxy.

### What the hosted copy holds (the relation audit)

`scripts/sync_to_hosted.sh` publishes what the readers of the hosted copy name, found in the code by
`scripts/hosted_relations.py` (the one place the rule lives):

* **Readers**: the Streamlit console (`app/*.py`, `app/pages`, `app/lib`, the weekly packs) and the product API
  (`api/league_lab_api/*.py`, the `app/lib` modules and page functions it loads, and every `src/league_lab`
  module it imports, followed import by import: `anyleague`, `research`, `decisions`, `sleeper_client`,
  `waivers`, `trades`, `lineup`, `roster_value`, `kdef`, `scoring`, `config` today). The walk stops at the model
  fit and the loaders (`projections`, `rankings`, `feature_groups`, `experiments`, `ingest`): a route imports
  constants and pricing from them, never their input tables.
* **Names**: every `analytics.` / `analytics_seeds.` / `ops.<name>` in those files, plus the bare names in
  `missing_relations(...)` / `require_relations(...)` checks.
* **Published**: those analytics relations, every analytics view and what the views read, `analytics_seeds`
  and `ops` whole — except E4's experiment tables `ops.player_prior_oof` / `ops.player_prior_oof_pred` (large,
  rebuilt by the experiment harness when missing, read by no one).
* **Checked**: after the restore every name a reader uses must be on the hosted copy, or the run fails
  (`verified: all 79 relations the pages and the API read are on the hosted copy (the API's 63 included …)`).
  Names in `raw` / `staging` / `intermediate` are printed as "named in shared pipeline code, never published":
  today they are nightly-only functions in shared modules (`lineup.load_inputs`, `waivers.load_and_sweep` /
  `upside_stashes`, `kdef.load_frame`, `anyleague.write_fixtures`). A route that calls one of them fails on the
  server — the line is there so it is seen first.

`./scripts/sync_to_hosted.sh --relations` prints all of it — the API's list, the console's count, the closure
and the size — from the local database only (no hosted settings needed, nothing written). On 2026-10-02: the
API reads 63 relations (50 analytics + `analytics_seeds.reference_scorings` + 12 `ops`), the console 71; 62
analytics relations published of 74.

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

### Sleeper's projections in the nightly (plan E1)

"Our record" needs Sleeper's own projections saved **before** each week's first kickoff (they cannot be fetched
again afterwards: the endpoint then answers the later numbers). `scripts/nightly.sh` has two steps for it:
`replay-projections` (after `replay-weather`: every archived snapshot back into `raw.sleeper_projections`, soft,
skipped while `data/raw/sleeper/projections` does not exist) and `fetch-projections` (after `project`, before
`save-record`: one pull of the next week to kick off, `uv run league-lab ingest sleeper-projections`; soft; skipped
with `NIGHTLY_SLEEPER_OFFLINE=1`, which the workflow never sets); `mart_projection_record` is in the
projection-marts `--select`. **Before the freeze, checked (Wave H)**: a week freezes at its first kickoff —
Thursday 8:15–8:30 PM ET in 161 of the 190 regular-season weeks 2016–2026 (`dim_game`), never earlier than
12:30 PM ET (Thanksgiving) — and the Actions run starts at 07:37 ET (06:37 in winter), so that morning's snapshot
is saved 5+ hours before kickoff even when GitHub starts a scheduled run late. A dropped run (GitHub drops some
under load) leaves the previous night's snapshot as the one the record uses. No secret is needed for it. One call a night
to `api.sleeper.com` (not the documented v1 API: if Sleeper moves it, the step fails softly and Data Status shows
`sleeper / projections_pull` failing; point `LEAGUE_LAB_SLEEPER_PROJECTIONS_URL` at the new host). The Thursday
morning run (07:37 ET on Actions; the Mac's 08:00 pull only feeds the Mac's own database) is the snapshot the
hosted record uses for that week, the same run whose board is frozen. Archive: `data/raw/sleeper/projections/<season>/<week>_<stamp>.json.gz`, an estimated 0.2–0.4 MB a pull
(the real answer has not been seen from the sandbox), an unchanged answer adds nothing — under 30 MB a season
in the Actions cache; like the
weather forecasts, a lost cache cannot rebuild these snapshots.

### Expected-value pricing (Wave I-G, M4)

`LEAGUE_LAB_EV_PRICING: "1"` is set on the nightly step (`.github/workflows/nightly.yml`) and **nowhere else**: `project`
records the mode in `ops.projections.pricing` and the API follows the newest build's label (a frozen week keeps its
own; docs/METRICS.md § "The record's pricing column"), so Render never needs it — rollback = remove the line, run the
nightly by hand.

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

### The Mac's launchd job (one writer, Wave H)

GitHub Actions is the only writer of the hosted copy. The Mac's launchd job (`scripts/refresh.sh`, 08:00) keeps
running the same nightly for **the Mac's own database** — the research console (`make app`), the weekly packs
(`make weekly-pack`), backtests and experiments, the full history (the hosted copy keeps three seasons of the
per-game tables), a local backup, and a second archive of Sleeper's projection snapshots — and **does not
publish**: off GitHub Actions, `nightly.sh` skips `sync-hosted` ("GitHub Actions is the one writer of the hosted
copy") and `make sync-hosted` refuses (exit 7, nothing touched). It still *reads* the hosted copy when the Mac's
`.env` has `LEAGUE_LAB_HOSTED_ADMIN_URL`: a state table the Mac's database lost is copied back from there.

**The switch, once (5 minutes)** — GitHub first, so the beta never goes a morning without a publish:

1. GitHub → the repository → **Settings → Secrets and variables → Actions**: three secrets are listed —
   `LEAGUE_LAB_SLEEPER_LEAGUE_ID`, `LEAGUE_LAB_HOSTED_ADMIN_URL`, `LEAGUE_LAB_HOSTED_APP_PASSWORD` (names only; the
   values are hidden). Missing one: add it (§ "Set it up once").
2. **Actions → nightly → Run workflow** (branch `main`) and wait for the green tick (~15 minutes). Its summary page
   ends with `verified: all … relations the pages and the API read are on the hosted copy`.
3. On the Mac: `git pull`. From the next 08:00 run on, `logs/nightly.log` says `step sync-hosted: skipped (GitHub
   Actions is the one writer of the hosted copy …)`. Keep `LEAGUE_LAB_HOSTED_ADMIN_URL` and
   `LEAGUE_LAB_HOSTED_APP_PASSWORD` in the Mac's `.env` (the restore and the fallback below use them).

If step 2 cannot go green yet, add `LEAGUE_LAB_MAC_WRITES_HOSTED=1` to the Mac's `.env` before step 3 (the Mac keeps
publishing, as before) and disable the workflow until it can.
* **Turn it on** (GitHub Actions down for days, or the minutes ran out): first stop GitHub — **Actions → nightly
  → ⋯ (top right) → Disable workflow** — then add one line to the Mac's `.env`:

  ```
  LEAGUE_LAB_MAC_WRITES_HOSTED=1
  ```

  The next 08:00 run (or `make refresh` now) publishes. One publish by hand without the line:
  `LEAGUE_LAB_MAC_WRITES_HOSTED=1 make sync-hosted` (while no Actions run is in progress — the Actions tab shows it).
* **Turn it off again**: delete the line from `.env`, then **Actions → nightly → Enable workflow** and **Run
  workflow** once. The first GitHub run restores the record from the hosted copy, which the Mac has been
  publishing meanwhile, so nothing is lost; never let both publish (the second overwrites the first's record).
* **Retire the job** (the Mac's own database is not needed): `launchctl unload
  ~/Library/LaunchAgents/com.leaguelab.refresh.plist && rm ~/Library/LaunchAgents/com.leaguelab.refresh.plist`
  (the reinstall lines are in `docs/SETUP_RUNBOOK.md` § 2). The beta does not notice.

The two records drift apart a little: the Mac's 08:00 board and GitHub's 07:37 board for the same week are built
from the same data minutes apart, and each freezes its own at kickoff. The hosted one (GitHub's) is the record
the beta shows; the Mac's is the research console's.

### The trigger — GitHub's schedule is not a clock (2026-10-04)

**What happened.** Every scheduled nightly from 2026-09-30 to 2026-10-03 started 3.5–6 hours late (12:59, 13:29,
12:48, 11:13 ET), the 09:07 ET backup never appeared as a run of its own, and on Sunday 2026-10-04 nothing had started
by 09:45 ET. That is how GitHub Actions' `schedule` works: best-effort, delayed under load, a delayed run dropped when
the next is due, worse on repositories with little traffic. A `workflow_dispatch` run, by contrast, starts within
seconds, and the `gate` job never skips one.

**The fix.** `ops/nightly-trigger/` — a Cloudflare Worker (free plan; the account that holds the domain) on a Cron
Trigger `37 * * * *` (UTC). At **07:37 America/New_York** (DST-aware: the Worker reads the hour in New York) it
dispatches `nightly.yml` on `main`; at 09:37 and 11:37 it lists today's runs (UTC, the gate's day) and dispatches
only when none has succeeded or is running. GitHub's own two cron lines stay in the workflow as the last resort — a
late scheduled run is skipped by the gate once the dispatched one has succeeded. The Worker's URL prints what it does
and today's runs; nothing dispatches over HTTP.

**Secret.** `GITHUB_TOKEN` on the Worker — a fine-grained personal access token scoped to the one repository with
"Actions: Read and write" (one year; the expiry date goes in STATUS). It is the only credential outside GitHub and
Render that can start a build; it cannot read code or secrets. Rotation: a new token into the same secret. Rollback:
delete the Worker. Set-up steps: `ops/nightly-trigger/README.md`.

**Status (2026-10-04, 10:30 ET)**: the Worker `isuckatfantasy-nightly-trigger` exists in Cloudflare with the cron
`37 * * * *` and the five variables (set by the PO from the dashboard); the code and the `GITHUB_TOKEN` secret are
Andrew's two steps (the dashboard's code editor is a cross-origin frame the PO's browser pane cannot type into):
Edit code → paste `src/index.js` → Deploy; Settings → Variables and Secrets → `GITHUB_TOKEN` (Secret). The
Worker's URL (`https://isuckatfantasy-nightly-trigger.mcdonald-g-andrew.workers.dev/`) prints what it does and
today's runs once the code is in.

### When the nightly is late or fails (Wave I-H, IH-1)

Three things now tell someone, from the cheapest up. None needs a new secret.

**1. The product says so (live).** `league_lab/freshness.py` holds the one rule: the published data is **stale** when
the newest `ops.projections.fitted_at` (the morning update's fit — the same `as_of` `/api/health` has always shown) is
older than **30 hours**. A normal night lands about 08:00 ET, so a missed morning shows by about 14:00 ET (after the
trigger's 09:37 and 11:37 re-checks have had their chance). Then:
* `GET /api/health` (no password) carries `"stale": true` and `"age_hours"` — computed at each answer, so the
  hour-long cache of `as_of` never hides a missed morning; `null` when `as_of` is unknown (no projections, the
  database unreachable: unknown is neither stale nor fresh). A keyword monitor on `https://isuckatfantasy.io/api/health`
  for `"stale":false` (any free uptime service; an account, not a secret in this repository) is the one alarm that
  also catches a night that never started.
* `GET /api/status` carries `nightly: {as_of, age_hours, stale, limit_hours: 30, words}` (read on the pool at each
  call; it hands the newer `as_of` to the health state, so the two agree). `freshness` stays the footer's caption.
* My Week shows one line above the actions: *"Yesterday's numbers: the morning update did not run. Injury statuses
  are still live."* (two or more missed mornings: *"Numbers from Friday, Oct 2: the morning update has not run
  since. …"*), and the footer's "Updated …" adds "· the morning update did not run" with the sentence on tap. The
  availability overlay keeps reading ESPN and Sleeper's injury feeds on request, so the injury words stay true. The
  app reads `/api/status` again when it comes back on screen after 10 minutes away (a phone that kept the app open
  overnight). The console's Data Status page shows the same sentence with its own tail ("This console's injury tags
  are from that update too": the console has no live overlay).
* Known edge: out of season `project` may write nothing new, so `as_of` ages and the line shows; the beta is
  in-season — revisit before the off-season (a "no games this week" exemption in `nightly_state`).

**2. GitHub emails the run's actor (no setup).** When a workflow run fails, GitHub notifies the user it ran as: for
a `workflow_dispatch` run that is the owner of the token that dispatched it — the trigger's fine-grained token is
Andrew's, so **Andrew** gets it; for a scheduled run (the late fallback crons), the user who last changed the `cron`
lines. It comes from **`notifications@github.com`**, subject like **"[agmcdonald24/league-lab] Run failed: nightly -
main (1a2b3c4)"**, with a link to the run, by email and on github.com / the GitHub app — as long as GitHub → Settings →
Notifications → **Actions** has email ticked (the default; "Only notify for failed workflows" keeps the successes
out). Check it once. What it does not cover: a dispatch that never happened (an expired token — no run, no email): that
is item 1's monitor and the trigger's own page (below).

**3. The run's summary says where (a step, the PO wires it).** `scripts/nightly_failure_summary.sh` reads
`logs/nightly.log` and writes the top of the run's summary page — the failing stage (an aborted night's step, else
the first failed step, else "before scripts/nightly.sh": the setup steps), whether this night published (its own
`step sync-hosted: ok`), the next move (this section's "Reading a failed run" table) and the last 40 log lines with
anything password-like blanked — plus one `::error` annotation naming the stage. The proposed step, last in the
`nightly` job (after "Upload dbt run results"):

```yaml
      # Wave I-H (IH-1): a failed night's summary - the failing stage, published or not, the last 40 log lines
      # (GitHub's failure email to the run's actor links here; docs/HOSTING.md § 5 "When the nightly is late or fails")
      - name: Notify (the failing stage and the last 40 log lines)
        if: ${{ failure() }}
        run: ./scripts/nightly_failure_summary.sh logs
```

No permission, no secret, no outside call; it always exits 0. Checked by `tests/test_ih1.py` (four logs: a failed
build with a password in it, an aborted night after an older night, a night that published, a run that never reached
the pipeline).

**The trigger's own page** (`ops/nightly-trigger/`, IH-1): with a Workers KV namespace (free) bound as `STATE` the
Worker records each dispatch and its URL prints `last dispatch: ok (HTTP 204) at Oct 5, 2026, 7:37 AM ET — the
morning run` or `last dispatch: FAILED at … — the morning run: HTTP 401 …` (401: the token expired or lost "Actions:
write"; 404: the repository or the workflow file; 422: the branch). Without the binding it works as before and says
"not recorded". Set-up: `ops/nightly-trigger/README.md`; offline checks: `node ops/nightly-trigger/test.mjs`.

## The domain

*(2026-10-04.)* The product answers at **https://isuckatfantasy.io** (and `www.`, which Render redirects to the root);
`https://league-lab.onrender.com` keeps answering. The pieces, in case one has to be redone:

* **Cloudflare** (zone `isuckatfantasy.io`, the Free plan): SSL/TLS encryption mode **Full**; two **DNS-only** (grey
  cloud) records — `CNAME @ league-lab.onrender.com` and `CNAME www league-lab.onrender.com`; no `AAAA` record.
  Cloudflare flattens the root CNAME, which is what Render's own Cloudflare guide asks for. Proxying (orange cloud)
  is optional once Render shows the certificate issued; it is off.
* **Render**: the service is Blueprint-managed, so the domain is in `render.yaml` (`domains: [isuckatfantasy.io]`;
  the dashboard shows no Custom Domains section for it). Render adds `www.isuckatfantasy.io` itself, verifies both
  against the records above and issues the certificates (minutes). The beta password and the sign-in cookie are
  host-only, so a browser signed in at one address signs in again at the other.
* **Nothing in the code names the host**: the API and the web app are one origin; `scripts/smoke.sh <url>` takes
  either address.

## Usage

*(Wave I-F, U-1; plan § 17 E: "which screens get used".)* The phone web app counts screen views on the hosted copy,
so the beta can be steered by what people open, not by guesses.

**What a row holds** (`usage.events`, one row per screen view): `at` (the server's time), `screen` (the web router's
route name: `week`, `waivers`, `trades`, `trade-calc`, `team`, `league`, `player`, `ros`, `about`, `trends`,
`matchups`, `players`, `receivers`, `compare`, `leagues`; anything else is stored as `other`), `league_key`
(`1389709692405551104`, `mfl:70587`), `roster_id` (the team number in that league), `platform` (`sleeper` / `mfl`,
from the key), `version` (`/api/health`'s release), `session` (a random 32-hex id the server sets in the cookie
`ll_usage`, which the browser keeps until midnight New York time). **Nothing about a person**: no name, username, IP
address, user agent, login token, player or free text — the API keeps only allow-listed values and the table's
checks refuse anything else. About says so in one line ("League Lab counts screen views — which screen, which league
and team, when — and nothing about you").

**How it is written.** `web/src/lib/usage.ts` sends `POST /api/usage {screen, league, roster_id}` once per screen
view (a new route, league or team; a filter, a sort or the player pane is not a new view) with
`navigator.sendBeacon` (a keepalive `fetch` where there is none), after the screen is drawn and never before sign-in.
The route is behind the beta password like every other, answers 204 whatever happens, and only queues the row: one
writer thread of its own inserts it (a bounded queue of 1,000; when the database is down the queue fills and further
rows are dropped and counted), so a slow or sleeping database never holds a request or the server's request threads.
The server's role `league_lab_app` stays `default_transaction_read_only = on`: the one insert runs in its own
`BEGIN; SET TRANSACTION READ WRITE; INSERT; COMMIT` on its own connection (`db.write_one`), never on the read pool's
connections; a failure is counted and logged (`usage: insert failed (<class>)`), never shown. Limits: one row a
second per session, with bursts of five (tapping through tabs), and 20 rows a second from all sessions together.
**Off switch**: `LEAGUE_LAB_USAGE=off` on the server (Render → Environment) — the route still answers 204, writes
nothing and sets no cookie.

**Where it lives.** Schema `usage` on the hosted copy, created by `scripts/hosted_usage.sql` (plain SQL, idempotent:
the schema, the table, an index on `at`, and the app role's `USAGE` on the schema plus `INSERT, SELECT` on that one
table — no update, no delete). The sync never drops it: it drops and restores `analytics`, `analytics_seeds` and
`ops` only, then runs the file in its own transaction (`scripts/sync_to_hosted.sh`, block "U-1", after the restore;
a failure there prints a warning and the publish stands). The sync's log line: `usage: <n> events kept, <size>`.
Size: 168 bytes a row with its index (measured: 10,000 rows = 1.6 MB) — 10,000 views ≈ 1.6 MB of the 512 MB Neon
budget (the sync's size check counts the marts only; the line above is how to watch it).

**Reading it.**
* The console: **Usage** (`app/pages/99_Usage.py`, last in the page list) — views per screen per day, views /
  leagues / browser-days per day, the last 7 / 14 / 30 days (New York days).
* The API: `GET /api/usage/summary?days=7` (behind the password; `no-store`) — `{enabled, ready, days,
  views_by_screen_day, by_day: [{day, views, leagues, sessions}], by_screen, totals, process: {written, failed,
  limited, dropped}}` (`process`: this server process's counters since it started). `ready: false` until the table
  exists.
* SQL on the hosted copy (owner role): `select screen, count(*) from usage.events where at > now() - interval '7 days'
  group by 1 order by 2 desc;`

**Rollout** (nothing new to configure — no new secret, no new variable, no workflow change):
1. **PO**: merge to `main`. Render deploys the image once its check is green (`autoDeployTrigger: checksPass`); the
   web app starts sending counts on its next load.
2. **The next nightly** (07:37 ET by itself — or **Andrew**: Actions → nightly → Run workflow, to have it today) runs
   the sync, which creates `usage.events` and its grants; the sync's log shows `usage: 0 events kept, 32 kB` (an
   empty table: 32 kB). Until then every insert fails quietly (`process.failed` in the summary counts them) and
   nothing else changes.
3. **Check** (PO or Andrew, on the phone): About ends with the notice; `GET /api/usage/summary` (signed in) →
   `ready: true`; open two screens, reload the summary: `totals.views` up by 2. Or the console's Usage page.

**Local development.** The table in the local database too (the Mac's database is owned by the pipeline role):

```bash
psql "$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')" \
     -v ON_ERROR_STOP=1 -f scripts/hosted_usage.sql
```

Without it the local API counts nothing (each insert fails quietly) and the Usage page says how to set it up.
`api/tests/test_u1.py` applies the file itself.

### Google Analytics

*(Wave I-I, INF-1; Andrew: "I logged into my google analytics for you to create tracking on this".)* Beside the
first-party count, the web app sends the same screen views and a few taps to Google Analytics 4 — property
**557285408** (Andrew's Google account), web stream **isuckatfantasy web** (`https://isuckatfantasy.io`), measurement
id **`G-HJWGHZ79BG`** (`web/src/lib/brand.ts` `GA_MEASUREMENT_ID`; public by design — it is in every page GA runs on,
not a secret). Code: `web/src/lib/analytics.ts`; App.svelte calls it beside `countView`. **No PII**: ids only (league
keys and team numbers); never a username, a team or manager name, a manager's player names, a password or free text.

**What is sent** (every event carries `league_key`, `roster_id`, `platform` (`sleeper` / `mfl`) and `release` —
`/api/health`'s `version`, so a release boundary shows in GA; ids only):

| Event | When | Its own parameters |
|---|---|---|
| `page_view` | every route change (a new path, league or team; not a filter, a sort or the drawer) | `page_location` (the address with only `league` and `team` kept), `page_path`, `page_title` (the route's name: `week`, `waivers`, …) |
| `screen_view` | beside the first-party count (the same rule: once per screen, league and team) | `screen_name` (the route's name) |
| `login` | the beta password was accepted | `method: "password"` |
| `select_content` | a player's drawer opened (the URL's `pane=`, IB-1's pane and II-2's drawer share it; II-2's `openPlayer` may also call `track` — one open counts once) | `content_type: "player"`, `item_id` (the NFL player id, `00-0036322`), `origin` (the route), `from` (`lineup` / `waiver` / `trade` / `search` / `list`) |
| `edit_link_click` | "Open Sleeper / MFL to edit your lineup" tapped (My Week) | `link_platform` |
| `compare_open` | the Compare screen opened | `has_pair` (1 when two players are set) |
| `trade_evaluate` | a trade evaluated (the calculator; `POST /api/trades/evaluate`) | `partner_roster_id`, `give_count`, `get_count` |
| `waiver_view` | the Waivers screen opened | — |

**Never sent**: a username, a team or manager name, a password, a search box's text, any other query parameter, a
user id. Google signals and ad personalisation are off (`allow_google_signals: false`,
`allow_ad_personalization_signals: false`); the page views are ours (`send_page_view: false`). gtag.js is not in
`index.html`: the module loads it once, on first use, **only after sign-in** — the sign-in screen never loads it, and
when it shows again (a cookie expired) GA's own switch `window["ga-disable-G-HJWGHZ79BG"]` is on until the app is back.
The service worker passes Google's requests through (it handles same-origin GETs only) and the API sends no CSP header,
so nothing blocks gtag; a CSP added later must allow `https://www.googletagmanager.com` (script) and
`https://*.google-analytics.com` / `https://*.analytics.google.com` (connect).

**The switch** (build time — the web app is built into the image): **`LEAGUE_LAB_GA`**, read by `web/vite.config.ts`
(`define` → `__LL_GA__`; only that one value reaches the bundle).
* unset (the default, and Render today): **auto** — sends only from `isuckatfantasy.io` / `www.isuckatfantasy.io`
  (`brand.ts` `GA_HOSTS`) and never under automation (`navigator.webdriver`): `npm run dev`, `vite preview`, a LAN
  address on the phone, the fixture e2e runs and the measure runs send nothing.
* `LEAGUE_LAB_GA=off npm run build`: nothing loads, ever — the bundle holds no gtag URL (`web/e2e/inf1` builds one
  and checks).
* `LEAGUE_LAB_GA=on`: always (GA's DebugView from a dev machine).
* An e2e that wants it on sets `window.__llGa = "on"` in an init script (`web/e2e/inf1`: a gtag stub, nothing leaves).
To switch it off in production, `api/Dockerfile`'s web stage needs `ARG LEAGUE_LAB_GA` above `RUN npm run build` and the
variable on Render (a redeploy) — not needed today.

**Consent** (PO call, 2026-10-04): the beta is password-gated and About says what is counted and that Google Analytics
is used (the cookie, what is sent, never the username, team name or password) — no cookie banner. A public launch (or
visitors from the EU / UK) needs a consent banner with Consent Mode before GA loads; revisit then.

**In GA** (Andrew, once — Admin, on the property):
1. Data streams → *isuckatfantasy web* → Enhanced measurement → Page views → advanced: **turn off "Page changes based
   on browser history events"** (the app sends its own `page_view`; with it on, every route change counts twice), and
   turn off **Form interactions** and **Site search** (the sign-in form and the search box are none of GA's business).
2. Custom definitions → Create custom dimensions (event scope): `league_key`, `roster_id`, `platform`, `release`,
   `origin`, `from`, `link_platform`, `screen_name`; custom metrics (optional): `give_count`, `get_count`. Until then
   the parameters arrive (DebugView, BigQuery) but the standard reports do not show them.
3. Admin → Data retention: 14 months (the default is 2).
4. Key events (optional): mark `edit_link_click` and `trade_evaluate`.
Check after the deploy: Reports → Realtime shows a `page_view` within a minute of opening the app on the phone.

## Events

*(Wave I-G, IG-2; the decision-quality review § "Engineering requirements": "Store structured events keyed to player,
team, and game IDs, with source URL, publication time, effective time, ingestion time, status, and superseded
status".)* The server keeps a record of what it learned and showed — each injury-report status move, each news item
and PlayerWire brief a screen showed — so a recommendation can cite the event behind it, and the record can later
tell news-affected weeks apart (V-1).

**What a row holds** (`events.events`): `id`; `kind` (`availability` — a status move from the availability overlay,
ESPN's injuries feed or Sleeper's directory; `news` — an ESPN news item the player card or My Week showed; `brief` — a
PlayerWire brief they showed; `depth_chart` — allowed, no writer yet); the keys `gsis_id` (`00-0036322`), `player_key`
(the source's own id: `espn:4262921`, `sleeper:6794`, `pw:<brief id>`), `team` (nflverse abbreviations: `LA`, `WAS`,
`JAX`), `game_key` (nflverse `game_id` from `dim_game` for the player's team that week — IH-2; empty when the team has no game); `status` (availability: `OUT`, `DOUBTFUL`, `QUESTIONABLE`,
`IR`, `PUP`, `NFI`, `SUS`, `INACTIVE`, `ACTIVE`; brief: PlayerWire's verification — `official`, `reported`,
`corroborated`, `disputed`; news: `player` or `league`, IF-4's "about"); `headline`, `summary` (a brief's text; ESPN's
items: none); `source` (`ESPN`, `Sleeper`, `RotoWire via ESPN`, `Minnesota Vikings via PlayerWire`) and `source_url`
(https only: the player's ESPN page for an ESPN report, the story, the brief's first evidence link); `published_at`,
`effective_at`, `ingested_at`; `superseded_by`; `fingerprint`. **Times**: for a status move `published_at` is the copy's
own time (ESPN's feed timestamp; Sleeper: when its directory was read) and `effective_at` the report's (ESPN's entry
date, Sleeper's `news_updated`); for news and briefs `published_at` is the item's date. Every reader orders by
`coalesce(effective_at, published_at, ingested_at)`.

**Superseded and deduplicated.** One live event per player per kind: a new status move supersedes the player's older
live ones (the overlay's current status is always the newest row); a news item or brief supersedes the older ones by
date (one arriving late is stored already superseded). `fingerprint` (sha256 of kind, player, status, URL, time) is
unique: the same report or item seen twice — two screens, a restart, two processes — is one row. A status that
returns to a report already stored (a copy that dropped a player for a while) is a new move.

**How it is written.** U-1's pattern: the screens only put rows on a bounded queue (500 batches; full = dropped,
counted) that one writer thread of its own drains, each batch in its own `BEGIN; SET TRANSACTION READ WRITE; ...;
COMMIT` on its own connection (`league_lab_api/events.py`; the read pool never sees a read-write transaction, the role
stays `default_transaction_read_only = on`). A failure is counted and logged (`events: a write failed (<class>)`), never
shown. The overlay's moves are worked out on that thread too: each new merged copy is compared with the one before
(the first copy after a restart with the store's live statuses), and only when both ESPN and Sleeper loaded — a source
that failed to load is not a status move. The first copy on an empty store writes every listed player once (~150 rows on
the fixtures, a few hundred to ~1,500 on the live feeds). **Off switches**: `LEAGUE_LAB_EVENTS=off` — nothing written
or read (the screens use the live sources, as before); `LEAGUE_LAB_EVENTS_ESPN_NEWS=off` — ESPN's news items stay out
of the store (status moves and briefs are kept; docs/ESPN_TERMS.md § What we keep).

**Where it lives.** Schema `events` on the hosted copy, created by `scripts/hosted_events.sql` (plain SQL, idempotent:
the schema, the table with its checks — `kind`, the id shapes, https URLs, the lengths — the indexes on
`(gsis_id, ingested_at)`, `(team, ingested_at)` and the live rows, and the app role's `USAGE` on the schema, `SELECT,
INSERT` on the table, `UPDATE` of `superseded_by` only and `USAGE` on its id sequence — no delete). The sync never drops
it: it runs the file after the U-1 block (`scripts/sync_to_hosted.sh`, block "IG-2"; a failure prints a warning and the
publish stands). Log line: `events: <n> events kept (<live> live), <size>`. Locally `scripts/init_db.sql` runs the same
file as the pipeline role. Size: ~500 bytes a row with its indexes (measured: 10,000 rows = 5.1 MB) — a season of
status moves and shown items (an estimate: 30,000–80,000 rows) is 15–40 MB of the 512 MB Neon budget. Pruned on
every run (below, "Retention (events)").

**Reading it.**
* My Week's **News feed** (IN-5; was "What changed"): a status line cites its stored event — the source (ESPN / Sleeper), the report's time and
  the player's ESPN page; the news lines are ESPN's items and PlayerWire's briefs of the last 24 hours, one per player
  (his own brief first), with the store's live events filling in what a live read missed (`changed.lines[].event_id`,
  `origin`, `verification`).
* The matchup evidence (Compare, the card, Matchups): each missing corner's `event` (source, URL, date, id) and `url`;
  `changed.events` lists them (docs/METRICS.md § Matchups "Current personnel").
* `GET /api/status` → `events: {enabled, ready, rows, live, newest, process: {queued, written, duplicate, superseded,
  failed, dropped, moves}}`.
* `GET /api/events?league=&team=&hours=72` (behind the password; `no-store`; 1–720 hours): the roster's players' events,
  newest first, live and superseded (`live`), each with `player_name` — the PO's QA.
* SQL on the hosted copy: `select kind, status, count(*) from events.events where ingested_at > now() - interval '1 day'
  group by 1, 2 order by 3 desc;`

**Rollout** (no new secret, no new variable, no workflow change): merge; the next nightly's sync creates the schema
(its log: `events: 0 events kept (0 live), 48 kB` — an empty table with its indexes); until then every write fails
quietly and the screens read the live sources as before. Check: `/api/status` → `events.ready: true`, then `rows`
growing after a few screens (the overlay's first copy writes every listed player once);
`/api/events?league=1389709692405551104&team=2`.

**Local development.**

```bash
psql "$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')" \
     -v ON_ERROR_STOP=1 -f scripts/hosted_events.sql
```

In fixture mode (`LEAGUE_LAB_SLEEPER_FIXTURES`: the tests, the sandbox) the store is off unless `LEAGUE_LAB_EVENTS=on`,
and `api/tests/conftest.py` sets it off for every test, so a test run never writes made-up events into a developer's
database. `api/tests/test_ig2.py` applies the file itself
and removes its rows.

**Retention** *(Wave I-G, IG-3)*. Every run of `scripts/hosted_usage.sql` — the sync's "U-1" block, once a night —
ends with `delete from usage.events where at < now() - interval '180 days'`: the table holds about six months of
views (at 168 bytes a row, a busy beta of 1,000 views a day stays near 30 MB). The owner role deletes; the app role
still cannot (no `DELETE` grant). The console's Usage page says so under its tables. To keep everything, remove that
one statement; to keep less, change the interval (one place).

**Retention (events)** *(Wave I-H, IH-1)*. Every run of `scripts/hosted_events.sql` — the sync's "IG-2" block, once a
night; locally `scripts/init_db.sql` — ends with two deletes, by `ingested_at` (the store's own clock):
* `news` and `brief` rows **superseded** and ingested more than **120 days** ago. A player's newest item (live) stays
  however old — one per player; the News feed (was "What changed") reads 24 hours and the card the live item.
* `availability` rows ingested more than **400 days** ago, live or superseded: a season, its playoffs and the next
  preseason — longer than the decision record looks back (a starter's status move before this season's kickoffs). A
  player still listed after his live row went comes back as a new move on the overlay's next copy.
So the table holds about a season and a half of status moves and four months of superseded news — at IG-2's estimate
(30–80k rows a season, ~500 bytes each) under ~60 MB at its largest. `depth_chart` rows (no writer yet) are not pruned.
A kept row's `superseded_by` may name a pruned row: the readers only ask whether it is null. The owner deletes; the app
role still cannot. Re-running deletes nothing more (`api/tests/test_ih1.py` plants nine rows on the clone and applies the
file twice; by hand on `league_lab_ia3`: `DELETE 2` / `DELETE 2`, then `DELETE 0` / `DELETE 0`). To keep more, change
the two intervals (one place each).

## Yahoo (Wave I-K, IK-2): Connect with Yahoo

Yahoo leagues are read through Yahoo's official Fantasy Sports API with each manager's own sign-in (OAuth 2.0;
`docs/YAHOO_TERMS.md`). Until the two secrets below exist on Render, `GET /api/yahoo/connect` answers 503
`yahoo_not_configured` ("Yahoo sign-in is not set up on this server yet") and the setup screen says "coming soon".
Nothing else changes for Sleeper or MFL leagues.

### 1. Register the app (Andrew, 10 minutes, once)

1. Sign in to Yahoo with the account that should own the app (Andrew's own is fine; managers never see it).
2. Open **https://developer.yahoo.com/apps/create/** and fill in *Create an App*:
   | Field | Value |
   |---|---|
   | Application Name | `isuckatfantasy` |
   | Description | `A free beta that reads a manager's own Yahoo fantasy football leagues, read-only and with the manager's permission, to suggest lineups, waiver claims and trades. No writes; league data is held in memory for minutes, never stored.` |
   | Homepage URL | `https://isuckatfantasy.io` |
   | Redirect URI(s) | `https://isuckatfantasy.io/api/yahoo/callback` — exactly this: https, no trailing slash |
   | OAuth Client Type | **Confidential Client** (the older form calls it *Web Application*): the secret stays on our server |
   | API Permissions | **Fantasy Sports** → **Read** (not Read/Write). Leave *OpenID Connect Permissions* unchecked. |
   Then *Create App*.
3. The app's page shows **Client ID** (Yahoo also calls it *Consumer Key*) and **Client Secret** (*Consumer Secret*).
   Copy both; never paste them into a chat, an issue or git.
4. Apply for Fantasy access at **https://sports.yahoo.com/developer/access/** (Yahoo reviews every application and closes
   thin ones without a reply): *Product*: the description above plus "a private beta for a few dozen managers, free";
   *Data*: "league settings, teams, rosters, scoreboard, standings, transactions and free agents of the signing-in
   manager's own leagues, read-only"; *Expected users*: **Small (<1,000)**; *Client ID*: the one from step 3; *Notes*:
   "Read-only. Tokens stay in the manager's browser (an encrypted cookie); league data is cached in memory for minutes;
   attribution 'Fantasy data provided by Yahoo Fantasy' on every Yahoo league screen."

**Without step 4 nothing Yahoo-shaped works** (2026-10-05, a friend's public league): since August 2026 Yahoo no longer
gives a new app the Fantasy Sports API by itself. The sign-in completes and the tokens are valid, and every Fantasy
call is refused — HTTP 401 or 403, `oauth_problem="additional_authorization_required"` — until Yahoo has approved the
application **and** added the Client ID to its allowlist (two stages by other developers' accounts; no published
timeline; an approved app has also lost access again). The server knows this state two ways:

* **`LEAGUE_LAB_YAHOO_ACCESS: pending`** in `render.yaml` (set 2026-10-05): the setup screen says "Connect with Yahoo —
  coming soon … Yahoo has not switched on this app's access to fantasy data yet" and invites nobody to connect; a
  pasted Yahoo link answers the same words (`yahoo_not_configured`), and no request reaches Yahoo. **Remove the row
  (or set `open`) once the probe below answers ok.**
* **Yahoo's own refusal**, remembered for an hour (`yahoo_client.access_pending`): with the switch open, the first
  refused call turns the screen to "coming soon" by itself (so Yahoo taking the access away again needs no deploy) and
  the next answered call turns it back.

**The probe (the operator, any time — the switch does not block it)**: signed in to the beta, open
`https://isuckatfantasy.io/api/yahoo/connect` (Yahoo's consent → back to the setup screen), then
`https://isuckatfantasy.io/api/yahoo/status?probe=1`: `"probe": {"ok": true, "game_key": "…"}` means Yahoo answers
this app — remove the switch; `{"ok": false, "code": "yahoo_not_configured"}` with `access.last_refusal`
(`status`, `problem`, `resource`, the description's first words; never a token) is Yahoo's answer, word for word. The
same line is in Render's logs: `yahoo refused: HTTP 403 problem=additional_authorization_required resource=game/nfl …`.

### 2. The secrets on Render (2 minutes)

Render → the `isuckatfantasy` service → *Environment* → *Add Environment Variable* (as secrets):

| Name | Value |
|---|---|
| `LEAGUE_LAB_YAHOO_CLIENT_ID` | the Client ID from step 3 |
| `LEAGUE_LAB_YAHOO_CLIENT_SECRET` | the Client Secret from step 3 |
| `LEAGUE_LAB_YAHOO_REDIRECT_URI` | `https://isuckatfantasy.io/api/yahoo/callback` (the registered URI, sent on sign-in and on every token refresh; without it the server builds it from the request's host and refreshes with `oob`) |

`LEAGUE_LAB_API_SECRET` already exists (`render.yaml`: `generateValue: true`); it seals the `ll_yahoo` cookie. Changing it
signs every Yahoo manager out (they connect again in seconds). Optional: `LEAGUE_LAB_YAHOO_PER_MIN` (default 60 calls a
minute). Save → Render redeploys. The same lines for `render.yaml` (PO):

```yaml
      - key: LEAGUE_LAB_YAHOO_CLIENT_ID
        sync: false     # Render asks for it: the Yahoo app's Client ID (developer.yahoo.com/apps)
      - key: LEAGUE_LAB_YAHOO_CLIENT_SECRET
        sync: false     # Render asks for it: the Yahoo app's Client Secret
      - key: LEAGUE_LAB_YAHOO_REDIRECT_URI
        value: https://isuckatfantasy.io/api/yahoo/callback
```

### 3. Verify live (the PO, after the deploy; nothing Yahoo-shaped is verified until this passes)

1. `https://isuckatfantasy.io/api/yahoo/status` (signed in to the beta) → `{"configured": true, "connected": false, …}`.
2. `https://isuckatfantasy.io/leagues?platform=yahoo` → *Connect with Yahoo* → Yahoo's consent screen names
   *isuckatfantasy* and "Fantasy Sports — Read" → *Agree* → back on `/leagues?platform=yahoo` with your leagues listed.
   An error lands on `/leagues?platform=yahoo&yahoo_error=<denied|state|refused|down>`: `refused` usually means the
   redirect URI or the secret does not match the app page; "coming soon … Yahoo has not switched on this app's
   access" right after connecting means Yahoo has not approved the Fantasy access yet (step 1.4; the probe above). If Yahoo's sign-in page itself complains about the
   `scope`, set `LEAGUE_LAB_YAHOO_SCOPE` to an empty value on Render (the app's registered permission then applies).
3. `https://isuckatfantasy.io/api/yahoo/leagues` → your leagues with `team_id` = your team. Open one; check against
   Yahoo's own pages: the roster slots (a superflex league shows `Q/W/R/T` as SUPER_FLEX), the scoring card (the
   "not priced" list should hold only stats you know are odd), this week's starters exactly as Yahoo shows them, the
   record, last week's scores, the latest moves (and which week each lands in).
4. A public league that is not yours, by its link (`https://football.fantasysports.yahoo.com/f1/<id>`): it should
   open while connected. **The anonymous check** (settles whether public leagues could open without sign-in): with
   any access token removed, `curl -s 'https://fantasysports.yahooapis.com/fantasy/v2/league/nfl.l.<public id>/settings?format=json'`
   — a 401 means sign-in stays required (as built); a 200 means a "public league without Yahoo" path is a small change.
5. *Disconnect Yahoo* → the list asks to connect again. After an hour connected, reload a Yahoo screen: it must still
   answer (the access token is refreshed and the cookie re-set without a prompt).
6. Render's logs for the session: no `access_token`, `refresh_token` or `ll_yahoo=` value anywhere.

## Accounts

*(Wave I-K, IK-4; the design: `docs/ACCOUNTS.md`, what was built: its § "Built, phase 1".)* A manager can sign in
with an emailed link (no password) and keep their leagues, the team in each, a default league and the saved Stats
views on any device. Optional: guest use (this browser's memory) is unchanged, and the beta password stays in front of
everything.

**The switch.** `LEAGUE_LAB_ACCOUNTS` = `auto` (the default: nothing to set) — accounts are on when
`LEAGUE_LAB_API_SECRET` is set **and** the nightly has created the `accounts` schema, with the ways in the server has
(---- IM-4, Wave I-M): **passkeys** once the nightly has applied the passkey part of `scripts/hosted_accounts.sql`, **the
emailed link** once `LEAGUE_LAB_RESEND_API_KEY` is set. With neither, `GET /api/account/status` answers `{"enabled":
false, "reason": "no_secret" | "not_ready"}` (+ `why`: per method) and the web app shows no sign-in anywhere. `off` turns it off whatever else is set (the routes answer
404 `accounts_off`; saved rows stay). `on` is for tests and the fixture API only: with no Resend key it uses the stub
mailer, which keeps the messages in the process's memory.

**Render → Environment** (secrets by exact name):

| Name | Value | Needed |
|---|---|---|
| `LEAGUE_LAB_RESEND_API_KEY` | the `re_…` key from Resend (below), "Sending access" to `isuckatfantasy.io` only | yes — it turns accounts on |
| `LEAGUE_LAB_API_SECRET` | already set (Render generated it): it signs the session cookie too | already there |
| `LEAGUE_LAB_MAIL_FROM` | `signin@isuckatfantasy.io` (the default; set it only to change the address) | no |
| `LEAGUE_LAB_PUBLIC_URL` | `https://isuckatfantasy.io` (the default): the address the emailed link opens | no |
| `LEAGUE_LAB_ACCOUNTS_DAILY_MAX` | `90` (the default): sign-in emails a day in all; Resend's free tier sends 100 | no |
| `LEAGUE_LAB_PASSKEY_ORIGINS` | `https://isuckatfantasy.io` (the default): where passkeys may be made and used, comma-separated, https only; the rp id is the shortest listed host (---- IM-4) | no |

The link's address is never taken from the request: a forged `Host` header would otherwise mail a victim a link to
someone else's site. Rotating `LEAGUE_LAB_API_SECRET` (DEPLOY.md "Sign everyone out") signs every account out too.

**Resend (Andrew, once, ~15 minutes).** resend.com → sign up (the free plan: "3,000 emails / mo", "100 emails a day",
resend.com/pricing, read 2026-10-04) → **Domains → Add Domain** → `isuckatfantasy.io`, region **us-east-1** (the
default; the MX value below names the region you pick). Resend then shows the records to add — copy its values, the
DKIM key is yours alone. In **Cloudflare → isuckatfantasy.io → DNS → Records → Add record**, one per row (Cloudflare
appends the domain to the name: type the name exactly as here, "Omit your domain from the record values in Resend
when you paste", resend.com/docs/knowledge-base/cloudflare; TTL Auto; MX and TXT records are never proxied):

| Type | Name | Content | Priority | What it is |
|---|---|---|---|---|
| MX | `send` | `feedback-smtp.us-east-1.amazonses.com` (the value Resend shows) | 10 | bounces and complaints come back to Resend |
| TXT | `send` | `v=spf1 include:amazonses.com ~all` (the value Resend shows) | — | SPF: who may send for `send.isuckatfantasy.io` |
| TXT | `resend._domainkey` | `p=MIGfMA0…` (the long key Resend shows) | — | DKIM: the signature on every message |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:<an address Andrew reads>;` | — | DMARC, Resend's recommended start (resend.com/docs/dashboard/domains/dmarc) |

None of them touches the site's records (`CNAME @` / `CNAME www` stay as they are: § "The domain"). If `_dmarc`
already exists, edit it instead of adding a second. Back in Resend → **Verify DNS Records** (minutes; up to a few
hours). Then **API Keys → Create API Key** → name `isuckatfantasy-render`, permission **Sending access**, domain
`isuckatfantasy.io` → copy the `re_…` key once into Render's `LEAGUE_LAB_RESEND_API_KEY` → Save Changes (Render
redeploys). Later, once a few weeks of DMARC reports show only Resend sending: `p=quarantine`, then `p=reject`.

**Where it lives.** Schema `accounts` on the hosted copy, eight tables (`users`, `login_links`, `sessions`,
`connections`, `leagues`, `user_leagues`, `preferences`, `watchlist`), created by `scripts/hosted_accounts.sql`
(plain SQL, idempotent; the app role `league_lab_app` gets `SELECT, INSERT, UPDATE, DELETE` on those eight tables and
nothing else; no new role, no new connection string). The API writes in its own `BEGIN; SET TRANSACTION READ WRITE;
…; COMMIT` on its own connection (`db.run_rw`); the role stays `default_transaction_read_only = on` and the read pool
never writes. The nightly never drops the schema (it drops `analytics`, `analytics_seeds` and `ops` only). These are
**the first rows the nightly cannot rebuild**: Neon's point-in-time restore is their backup — check the plan's restore
window before inviting people. Retention (each run of the script): links older than a day, sessions ended more than a
day ago, a shared league row nobody has saved for a week. Size: a few kB per account.

**The nightly's lines** (`scripts/sync_to_hosted.sh`, after the IG-2 block — the PO adds them):

```bash
# ---- IK-4 (Wave I-K): accounts — docs/HOSTING.md § "Accounts". The `accounts` schema is never dropped above (only
# analytics, analytics_seeds and ops are); scripts/hosted_accounts.sql creates its eight tables if missing, grants the
# app role SELECT / INSERT / UPDATE / DELETE on those eight only (its default_transaction_read_only stays on) and prunes
# spent links and ended sessions. Idempotent, a few ms, its own transaction after IG-2, the same owner connection (no
# new secret). A failure here never fails the publish: accounts stay off (status: not_ready) until a sync applies it.
if psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction -f scripts/hosted_accounts.sql; then
  echo "accounts: $(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select (select count(*) from accounts.users) || ' accounts, ' || (select count(*) from accounts.user_leagues) || ' saved leagues, ' || pg_size_pretty((select sum(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'accounts' and c.relkind = 'r')::bigint)" 2>/dev/null || echo '?')"
else
  echo "WARNING: scripts/hosted_accounts.sql failed: accounts stay off until a sync applies it (the publish itself is fine)" >&2
fi
# ---- end IK-4
```

**Rollout.**
1. **PO**: merge to `main`; add the lines above to `scripts/sync_to_hosted.sh`. Render deploys; with no Resend key
   nothing changes for anyone (`/api/account/status` → `enabled: false, reason: "no_mailer"`).
2. **The next nightly** (or Actions → nightly → Run workflow) creates the schema: the log line
   `accounts: 0 accounts, 0 saved leagues, 408 kB`.
3. **Andrew**: Resend + the four DNS records + `LEAGUE_LAB_RESEND_API_KEY` on Render (above).
4. **Check** (phone): `https://isuckatfantasy.io/api/account/status` (signed in with the beta password) →
   `"enabled": true, "mailer": "resend"`; the ⋯ menu shows "Sign in to save your leagues"; `/account` → your email →
   the email arrives (check the spam folder once; Gmail → "Show original" says `SPF: PASS`, `DKIM: PASS`, `DMARC:
   PASS`) → the link → "Sign in on this device" → "Save these N leagues" → open the same link flow on a second
   device (a laptop, a private window): the leagues, the teams and the default come back, `/` opens the default
   league's week with no setup.

**Phase 2 (Wave I-L, IL-5): connections and the watchlist** — nothing new to set. A Yahoo / ESPN connection made
while signed in is kept in `accounts.connections`, sealed with `LEAGUE_LAB_API_SECRET` (purpose
`account-connection|<provider>`), so **rotating that secret also drops every saved connection** (each person connects
once more; the cookies on their devices stop opening too). The table, its grants and its `on delete cascade` were in
IK-4's script already: `scripts/hosted_accounts.sql` is unchanged. `ll_session`'s path is `/api` now (it was
`/api/account`). `docs/ACCOUNTS.md` § "Built, phase 2".

**Passkeys (Wave I-M, IM-4)** — nothing to set on Render (`LEAGUE_LAB_API_SECRET` is there; the origin list defaults
to the site). The nightly's IK-4 block already runs `scripts/hosted_accounts.sql` as the owner: its IM-4 part makes
`accounts.users.email` optional, adds `users.webauthn_handle`, and creates `accounts.passkeys` and
`accounts.passkey_challenges` with the app role's grants (idempotent; every row kept). The server re-checks once a minute
until they are there (`accounts.READY_SQL`) and then answers `"methods": ["passkey"]` — **accounts are on for everyone
from that moment** (the next nightly after the merge, or Actions → nightly → Run workflow). A passkey belongs to its
domain: do not move the site off `isuckatfantasy.io` without a plan for the accounts. `docs/ACCOUNTS.md` § "Passkeys".

**Local development.** On the Mac (the pipeline role owns the database):
`psql "$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')" -v ON_ERROR_STOP=1 -f scripts/hosted_accounts.sql`,
then run the API with `LEAGUE_LAB_ACCOUNTS=on LEAGUE_LAB_API_SECRET=dev` — the stub mailer keeps the link in the
process (nothing prints it); `api/tests/test_ik4.py` shows how a test reads it (`accounts.STUB.sent`).

## Licences to keep in mind when sharing

* nflverse data: free to use with attribution (kept on Home → Data & attribution).
* FTN Data charting via nflverse: **CC BY-SA 4.0** — first-read shares and other charting-derived
  numbers are adaptations and carry the same licence and attribution (they do).
* Sleeper: public, read-only API; league data belongs to the league.
* ---- IK-3 (Wave I-K) **ESPN**: no official API; isuckatfantasy reads public leagues through the undocumented
  `lm-api-reads.fantasy.espn.com` endpoints, labelled "unofficial", read-only, free beta only. Disney's terms prohibit
  automated access and commercial use (`docs/PROVIDERS.md` § ESPN, `docs/ESPN_TERMS.md`): a known risk the owner accepts
  for the free beta; a paid product needs a written agreement. **The private switch** `LEAGUE_LAB_ESPN_PRIVATE` ships
  **off**: on, a user may paste their own `espn_s2` / `SWID` into "Private league?" — kept only in their browser's sealed
  `ll_espn` cookie, never stored or logged on the server. **Risk if Andrew turns it on**: it asks users to share their
  ESPN login session (Disney: "you will not share your account"), and a leaked cookie is a full ESPN session for that
  user; turn it on only for people who understand that, and off again with the one variable.
* ---- IK-3 **Yahoo**: the official Fantasy Sports API under Yahoo's developer API terms — read-only; no income derived
  from it without Yahoo's written permission; Yahoo user data not kept beyond 24 hours (our caches are minutes); the
  attribution "Fantasy data provided by Yahoo Fantasy" (`docs/YAHOO_TERMS.md`, IK-2). "Connect with Yahoo" stays "coming
  soon" until `LEAGUE_LAB_YAHOO_CLIENT_ID` / `LEAGUE_LAB_YAHOO_CLIENT_SECRET` are set (HOSTING § "Yahoo", IK-2).
* Do not redistribute the raw files; the hosted copy holds only derived marts.
