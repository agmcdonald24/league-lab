# Putting League Lab on a server (the beta)

> **Done on 2026-10-02; the product's own address since 2026-10-04: https://isuckatfantasy.io** (docs/HOSTING.md
> § "The domain"). The beta is live at **https://league-lab.onrender.com** (Render Blueprint `league-lab`,
> service `srv-db01bl60tbcc73fpbuh0`, Starter, Ohio). Steps 1–8 below are the record of how, and what to redo if
> the service is ever recreated. Day to day: a merge to `main` reaches the server by itself ("How a new version
> reaches the server"); if something is off, "When it breaks". **Neon is published by GitHub's nightly** (07:37 ET;
> its secrets were set and its first green run was #5 on 2026-10-02, after the runner moved to Postgres 18 to match
> Neon) — `docs/HOSTING.md` § 5.

This puts the phone app and its API at one web address your league-mates open on their phones. You do it once, in
about 30 minutes, from a browser and one terminal command. After that, every change merged to `main` reaches the
server by itself.

**Cost: $7 a month** (Render's Starter server). Neon (the database) and GitHub stay free.

```
you merge to main ──► GitHub Actions "image": builds the server, starts it once ──► green check
                  └─► Render: builds the same server, puts it live after the green check ──► https://league-lab.onrender.com
                                                                                │ read-only
GitHub Actions "nightly" (unchanged) ──► Neon: the numbers ◄─────────────────────┘
```

The server only reads Neon, with the read-only role. It never writes anywhere but its own scratch folder.

## Before you start

You need three things you already have:

* The GitHub repository `league-lab` (private is fine).
* The Neon project the Streamlit app reads (`docs/HOSTING.md` § 1).
* The beta password your league-mates already use for the Streamlit app.

**The copy on Neon must hold the current tables.** GitHub's nightly publishes them (its three secrets — GitHub →
**Settings** → **Secrets and variables** → **Actions**: `LEAGUE_LAB_SLEEPER_LEAGUE_ID`, `LEAGUE_LAB_HOSTED_ADMIN_URL`,
`LEAGUE_LAB_HOSTED_APP_PASSWORD` — exist since 2026-10-02; the last two are the values in the Mac's `.env`, pasted
without the quotes). If the copy is ever stale: **Actions** → **nightly** → **Run workflow** → `main` (about 15
minutes; the first run on an empty cache took 24). With a stale copy My Week, the player card and the matchup
screens fail or show old numbers; `/api/status` shows when each source was loaded.

## 1. Copy the database address (Neon, 3 minutes)

The server needs the **read-only** address, the one whose user is `league_lab_app`.

1. The quickest place: **share.streamlit.io** → your app → **⋮** → **Settings** → **Secrets**. Copy the value of
   `LEAGUE_LAB_APP_DB_URL` (between the quotes). It is the same address.
2. Or from Neon: **console.neon.tech** → the `league-lab` project → **Dashboard** → **Connect**. Pick role
   **`league_lab_app`**, database `neondb`, turn **Connection pooling** on, and copy the address. Neon may hide the
   password as `****`: the password is `LEAGUE_LAB_HOSTED_APP_PASSWORD` in the `.env` file on your Mac.

Check what you copied:

* It starts with `postgresql://league_lab_app:` — never `neondb_owner` (that one can write).
* The host has **`-pooler`** in it, like `ep-cool-name-123456-pooler.us-east-2.aws.neon.tech`. If yours does not,
  type `-pooler` right after the `ep-…` part. (The pooled address lets Neon's database go to sleep when nobody is
  using the app, which keeps it inside the free hours.)
* It ends with **`?sslmode=require`**. Add it if it is missing.

Look at the host once more: **`us-east-2`** means Ohio, which is what `render.yaml` picks (`region: ohio`). If yours
says `us-east-1`, change that line to `region: virginia` (`us-west-2` → `oregon`, `eu-central-1` → `frankfurt`): on
github.com open `render.yaml` → the pencil → edit the line → **Commit changes**. Do this before step 3: Render cannot
move a server to another region later. A server far from its database makes every page slower.

## 2. Make a Render account (5 minutes)

1. Go to **render.com** → **Get Started** → **GitHub** (sign up with your GitHub account) → **Authorize**.
2. Render asks for a workspace name: `League Lab` is fine.
3. Add a card: your avatar (top right) → **Billing** → add a payment method. The Starter server is paid; nothing is
   charged until step 3 creates it.

## 3. Create the server from the Blueprint (5 minutes)

`render.yaml` in the repository describes the whole server, so Render asks you almost nothing.

1. **dashboard.render.com** → **New** (top right) → **Blueprint**.
2. **Connect GitHub** (first time only): pick your account → **Only select repositories** → `league-lab` →
   **Install**. Back on Render, pick **league-lab** → **Connect**.
3. **Blueprint Name**: `league-lab`. **Branch**: `main`. Render reads `render.yaml` and lists one web service,
   `league-lab`, Docker, Starter, Ohio.
4. It asks for the two values `render.yaml` leaves to you:

   | Render shows | You paste |
   |---|---|
   | `LEAGUE_LAB_APP_DB_URL` | the read-only address from step 1 |
   | `LEAGUE_LAB_APP_PASSWORD` | the beta password |

   The other settings are filled in already (`LEAGUE_LAB_API_SECRET` is made up by Render; you never need to see it).
5. **Deploy Blueprint** (or **Apply**).

## 4. Watch it build (5–8 minutes the first time)

Render → **league-lab** → **Logs**. You will see, in order:

1. `npm ci` and `vite build` (the phone app), then `uv sync` (the Python parts): the build.
2. `Uvicorn running on http://0.0.0.0:10000`: the server started.
3. At the top of the page the status turns to **Live**.

Render checks `/api/health` before it sends anyone to the new server. A later deploy works the same way, and the old
server keeps answering until the new one is healthy, so a deploy never takes the site down.

## 5. Your address, and the health check (1 minute)

The address is at the top of the service page: **`https://league-lab.onrender.com`** (Render adds a few letters,
like `league-lab-x7k2.onrender.com`, if the name is taken).

Open `https://<your address>/api/health` in a browser. You should see something like:

```json
{"ok": true, "version": "3f9c2a1b7d4e", "as_of": "2026-10-03T11:52:10.381+00:00", "board_source": "auto", "database": "ok"}
```

* `"database": "ok"`: the server reads Neon.
* `as_of`: when the nightly last fitted the projections. It should be this morning (or yesterday before 08:00 New York).
* `version`: the commit the server runs.

## 6. Run the smoke test from your Mac (1 minute)

In Terminal, in the repository folder:

```bash
scripts/smoke.sh https://league-lab.onrender.com 'the-beta-password'
```

Every line starts with `ok` and the last line says `All checks passed.` It checks the health route, the app's page,
the password door (refused without the password, refused with a wrong one, accepted with yours), the freshness line,
the two house leagues, a team list and a My Week. Put the password in single quotes.

To also check a league picked by a Sleeper username (this one asks Sleeper, through the server):

```bash
scripts/smoke.sh https://league-lab.onrender.com 'the-beta-password' <a Sleeper username>
```

## 7. Put it on your iPhone's home screen (1 minute)

1. Open the address in **Safari** (not Chrome: on an iPhone only Safari adds apps to the home screen).
2. Type the beta password once. The phone stays signed in for 180 days.
3. Tap **Share** (the square with the arrow) → scroll → **Add to Home Screen** → **Add**.

It opens full screen from the League Lab icon, like an app. On Android: Chrome → **⋮** → **Add to Home screen**.

## 8. Share it with the league (2 minutes)

Send the address and the password, for example:

> League Lab beta: https://league-lab.onrender.com — password: ********. Open it in Safari, sign in once, then
> Share → Add to Home Screen. Type your Sleeper username to see your own team in any of your leagues.

* **Change the password**: Render → **league-lab** → **Environment** → `LEAGUE_LAB_APP_PASSWORD` → edit → **Save
  Changes** (the server restarts in about a minute). People already signed in stay signed in.
* **Sign everyone out** (a password leaked): same page → `LEAGUE_LAB_API_SECRET` → **Generate** → **Save Changes**.

## What it costs, per month

| What | Cost |
|---|---|
| Render Starter server (512 MB memory, always on) | **$7** |
| Render builds (about 5 minutes per release; Render's free workspace includes a monthly allowance of build minutes) | $0 |
| GitHub Actions: the image check (about 4 minutes per release) + the nightly (about 15 minutes a day); a private repository gets 2,000 free minutes a month | $0 |
| GitHub's container registry: the images (a private account gets 500 MB free; a release adds a few MB) | $0 |
| Neon: unchanged. The health check reads it at most once an hour, so Neon can sleep when nobody uses the app | $0 |
| **Total** | **$7** |

Render's **Free** server costs $0 but goes to sleep after 15 minutes without visitors, and the next visitor waits
about a minute: for a league-mate opening it on Sunday morning, that looks broken. To try it anyway, change
`plan: starter` to `plan: free` in `render.yaml`.

Memory: see **Memory** below. If Render → **Metrics** → **Memory** gets near 512 MB, or the Events list says the
server ran out of memory, switch to **Standard** (2 GB, $25 a month): **Settings** → **Instance Type**. **It happened
once**: 2026-10-04 15:25 ET (a Sunday afternoon, the heaviest hour; `c47c5ea`), "ran out of memory (used over
512 MB)", the instance restarted itself and recovered within the minute. Andrew chose the memory diet (Wave I-J,
INF-2) over Standard.

## Memory

What the server holds, measured with `scripts/measure_memory.py` (the fixture leagues, the main database, the pinned
clock; `tree` = the PO's figure, which includes the `uv run` wrapper's ~33 MB that Render does not have):

| | before (Wave I-I) | after (Wave I-J, INF-2) |
|---|---|---|
| started, nothing opened | 172–177 MB | 176 MB (the server alone: 144) |
| the two house leagues, every screen | 229–234 MB | 218 MB |
| + the Test League and MFL 70587 on demand | 400–405 MB | 272–276 MB (the server alone: ~243) |
| each further league | +75–100 MB, never given back | a plateau: the caches stay inside their budget |

**Where it goes.** About 145 MB is Python, pandas, numpy and scipy standing there. On top: the caches (a league's
priced weeks, its solved lineups, its rest of season, the SQL results, the trade finder's context …), which now share
**one budget** (`LEAGUE_LAB_CACHE_MB`, default **64**): past it, the least recently used entries go first, whichever
league they belong to, and the server hands the freed memory back (`malloc_trim` after a request). A league evicted
and opened again is rebuilt from the database in a second or two. Text values are stored once however many tables hold
them (a player id is one string, not one per row), one week's projections board is shared by every league, and a
board's raw rows are not kept next to the board. Not in the budget: Sleeper's player directory (one per day) and each
league's Sleeper / MFL payloads.

**Sleeper's player directory (Wave I-L, IL-4).** Sleeper's `/players/nfl` is ~12,200 players × 53 fields (16 MB of
JSON); parsed as sent it held **37 MB** on the live server (`outside_mb.sleeper`, 2026-10-05). It is now trimmed as it
is parsed (`league_lab.sleeper_client.DIRECTORY_FIELDS`: the 15 fields the code reads — names, position, fantasy
positions, team, status, injury status and body part, active, gsis / ESPN ids, news time, depth-chart order; every
other field and every null dropped, the text interned), kept as **one shared read-only copy** (no copy per call), and
written to the disk cache in that shape. Rows are not dropped (a retired player can sit on a dynasty roster). Measured
with `scripts/measure_memory.py --synthetic-directory` (a directory of Sleeper's size and shape; the fixtures' own is
842 players):

| | before (main `93115db`) | after (IL-4) |
|---|---|---|
| the directory, as `/api/status` counts it (`outside_mb.sleeper`) | 38.7 MB | 8.8 MB (`memory.directory.mb` 8.6) |
| the directory, Python's own count (`tracemalloc`; the real 2026-09-26 payloads) | 36.6 MB | 11.3 MB |
| the server's RSS: the directory read, no league opened | +41.5 MB | +15.3 MB |
| the server's RSS after the four leagues (house × 2, the Test League, MFL 70587) | 281 MB | 248 MB |

A field a new reader needs goes into `DIRECTORY_FIELDS` (`api/tests/test_il4.py` runs the on-demand screens over a
directory that records every field asked for and fails on one outside the list). `/api/status` → `memory.directory`
says `{loaded, rows, fields, mb, kept}`.

**Seeing it.** `/api/status` → `memory`: `rss_mb` (what Render meters), `cache_mb` of `budget_mb`, `regions` (MB per
cache: `sql`, `boards`, `priced`, `ros`, `league_weeks`, `contexts`, `decisions`, `research_priced`, `research_memo`,
`about`, `stats`, `scoring_checks`), `entries`, `evictions`, `trims`, `outside_mb` (the Sleeper / MFL clients' own
caches), `malloc_arena_max`. The console's **Data Status** page says it in one line when `LEAGUE_LAB_API_URL` (and,
with the password gate on, `LEAGUE_LAB_API_TOKEN` from `/api/login`) are set.

**The switches.**
* `LEAGUE_LAB_CACHE_MB` (Render → **Environment**; default 64): the caches' budget. Lower = less memory, more
  rebuilding; on **Standard** (2 GB) 300 is comfortable. The budget counts a table's arrays (a text column as pointers:
  the strings are shared), so the Python heap the caches really hold is about 1.5 times the figure.
* `MALLOC_ARENA_MAX=2` and `MALLOC_TRIM_THRESHOLD_=131072` in the image (`api/Dockerfile`'s `ENV` line): fewer glibc
  heaps for the server's worker threads and an earlier hand-back; about 4–15 MB less on the script, more under
  concurrent Sunday traffic (each worker thread otherwise gets a heap of its own).
* `LEAGUE_LAB_FINDER_LAZY_THEIRS` (default on; `off` restores Wave I-I's order): the Trade Finder prices a partner's
  own best waiver move only when one of his trades can still be credible without it (IL-4) — a cold Finder prices
  fewer waiver sweeps, and holds fewer of them in the `decisions` region.
* Re-measure after a change: `uv run python scripts/measure_memory.py --plateau --cycles 2` (Postgres up; see its
  header for the options); `LEAGUE_LAB_CACHE_MB=40 …` to see a smaller budget; `--synthetic-directory` to hold
  Sleeper's directory at its real size (the fixtures' is 842 players).

## How a new version reaches the server

1. A change is merged to `main` on GitHub.
2. GitHub Actions runs **image** (about 4 minutes): it builds the server, starts it once, checks it answers, and saves
   the image as `ghcr.io/<your GitHub name>/league-lab:<commit>` and `:main`.
3. When that check is green, Render builds the same commit and puts it live (about 5 minutes). If the check is red,
   Render does not deploy that commit and the server keeps running the last good one.

A change that touches nothing the server runs (the docs, dbt, the Streamlit pages) does not rebuild it. New numbers
need no deploy at all: the nightly publishes them to Neon and the server picks them up within 10 minutes.

## When it breaks

| What you see | What to do |
|---|---|
| Render says **Deploy failed** | Render → **Events** → the failed deploy → **Logs**: the first line with `ERROR` says why. The previous version is still live. Send the log to the PO, or **Rollback** on the last good deploy in **Events**. |
| GitHub shows a red **image** check | Actions → **image** → the run: the failing step names it. Render waits; nothing changed on the server. |
| `/api/health` says `"database": "unreachable: …"` | The database address is wrong or Neon is down. Render → **Environment** → check `LEAGUE_LAB_APP_DB_URL` against step 1 (role `league_lab_app`, `-pooler`, `sslmode=require`); status.neon.tech. The server tries again every minute. |
| `as_of` in `/api/health` is days old (it is re-read hourly) | Nothing has published Neon: GitHub → Actions → **nightly** — the red run names the step (`docs/HOSTING.md` § Reading a failed run); **Run workflow** again once fixed. Stop-gap for days without Actions: `LEAGUE_LAB_MAC_WRITES_HOSTED=1` in the Mac's `.env` and disable the workflow (HOSTING.md § launchd), never both publishing. |
| Render says **Deploy failed** in ten seconds with `COPY … not found` | A path the Dockerfile copies is kept out of the build: `.dockerignore` must list it (`!app/pages/` and so on), and no `api/Dockerfile.dockerignore` may exist — `api/tests/test_build_context.py` checks both; run `cd api && uv run pytest -q tests/test_build_context.py`. |
| A page says **the numbers are not ready yet** | The nightly is publishing right now (one or two minutes, around 08:00 New York), or a table is missing on Neon. Reload in two minutes; if it stays, run the nightly by hand. |
| **busy, try again in a minute** | The server's Sleeper allowance (300 calls a minute) is spent. It refills within a minute. |
| The site does not load at all | Render → the service: **Live**? If not, **Manual Deploy** → **Deploy latest commit**. Still not: **Manual Deploy** → **Clear build cache & deploy**. |
| A push is green on GitHub but Render shows **no deploy at all** for it (not failed — nothing started) | Seen 2026-10-04 for `c47c5ea` and `786c2f5`, the first two pushes after the Blueprint sync that added the domain (`dc8d668` before it auto-deployed fine). **Manual Deploy** → **Deploy latest commit** (36 s) is the remedy; the PO does it after every push and says so until the cause is known (the Blueprint / webhook path is the suspect — Render's Events list has nothing to explain it). |
| The smoke test prints `FAIL` | The line says which check and what the server answered. `health` → the rows above; `gate` → the password you typed; `my week` → a missing table on Neon (run the nightly). |
| The Blueprint page rejects a line of `render.yaml` | Render renames a setting now and then. The message names the line; send it to the PO. (If it is `autoDeployTrigger`, replacing that line with `autoDeploy: true` works: Render then deploys every commit without waiting for the check.) |

Render's logs keep the server's own messages (each request, any error with its traceback): **Logs**, with a search
box. Nothing private is logged; the password is never printed.

## Deploying the built image instead (optional)

`render.yaml` lets Render build the server itself. The other way: Render runs the exact image GitHub Actions already
built (`ghcr.io/<you>/league-lab:<commit>`).

| | Render builds it (what `render.yaml` does) | Render runs the GitHub image |
|---|---|---|
| Setup | nothing beyond this page | a GitHub token for Render + a deploy hook secret in GitHub (5 more steps) |
| Push to live | ~4 min check, then ~5 min Render build | ~4 min check, then ~30 s to pull the image |
| Build minutes | Render's (≈5 a release, inside the free allowance) | GitHub's only |
| Same bytes as the check | rebuilt from the same commit and lock files (the base images can move between the two builds) | the very image the check started |

For a beta that releases a few times a week, the first column is fewer moving parts, so it is the default. To switch
later:

1. GitHub → your avatar → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)** →
   **Generate new token (classic)** → scope **`read:packages`** only, no expiry or a long one → copy it.
2. Render → **Workspace Settings** → **Registry Credentials** → **Add**: registry **GitHub**, your GitHub username, the
   token.
3. Render → **New** → **Web Service** → **Existing image** → `ghcr.io/<your GitHub name, lower case>/league-lab:main`
   with that credential; the same region, plan, health check path `/api/health` and the same environment values
   (copy them from the current service's **Environment**).
4. On the new service: **Settings** → **Deploy Hook** → copy. GitHub → the repository → **Settings** → **Secrets and
   variables** → **Actions** → **New repository secret** `RENDER_DEPLOY_HOOK_URL` = the hook. From then on the image
   workflow's last step tells Render which image to run.
5. Check the new address with the smoke test, then delete the old service (**Settings** → **Delete Web Service**) and
   the Blueprint.

## What is not there yet

* **Accounts.** One shared password for everyone; no personal sign-in, no saved settings per person.
* **Payments.** Nothing is charged and nothing is for sale. Both wait for Wave I, after Sleeper's licence: Sleeper's
  data is free for non-commercial use only (`docs/SLEEPER_TERMS.md`). The beta stays free and behind the password.
* **A custom domain** (`leaguelab.app`-style). Render supports one later: **Settings** → **Custom Domains**.
* **More than one server.** One process holds the Sleeper allowance and its cache; a second one would need a shared
  cache first (`docs/SLEEPER_TERMS.md`).

The Streamlit research console stays where it is (`docs/HOSTING.md`).

## For developers

* The image: `api/Dockerfile` (three stages: the web app on Node 22, the Python environment with uv, then
  `python:3.13-slim` with the `.venv`, `api/league_lab_api`, `app/lib`, `app/pages`, `src/league_lab`, `web/dist`;
  runs as `nobody`; writes only `LEAGUE_LAB_CACHE_DIR=/srv/cache`; listens on `$PORT`, else 8080). `.dockerignore`
  keeps everything else out of the build. Locally:
  `docker build -f api/Dockerfile -t league-lab . && docker run -p 8080:8080 -e LEAGUE_LAB_APP_DB_URL=… -e LEAGUE_LAB_APP_PASSWORD=… league-lab`.
* `/api/health` (no password): `{"ok", "version", "as_of", "board_source", "database"}`; always 200 while the process
  runs (a restart does not fix a database), the database's state in the body. `version` = `LEAGUE_LAB_VERSION` (the
  workflow's build argument), else Render's `RENDER_GIT_COMMIT`, else `git rev-parse`, else `dev`.
* The settings: `render.yaml` (each line commented) and `api/README.md` § Environment.
* Proof without Docker (the sandbox has no daemon) and the measured numbers: `docs/STATUS.md` § Wave H, H0.
