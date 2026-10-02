# League Lab API (plan D7 spike; the API for any league: plan F3)

A read-only JSON API over the same marts the Streamlit app reads, plus the phone web app (`web/`) served as
static files: **one process, one deploy**. It exists to let Andrew compare My Week and the player card on a
phone-first stack with the Streamlit pages (`docs/FRONTEND_DECISION.md`). Nothing in `app/`, `src/` or `dbt/`
depends on it; the nightly does not change.

## What it serves

| Endpoint | What | Source |
|---|---|---|
| `GET /api/session` | `{gate, signed_in}` | — |
| `POST /api/login` `{password}` | sets the `ll_auth` cookie (180 days) and returns the token | `LEAGUE_LAB_APP_PASSWORD` |
| `POST /api/logout` | clears the cookie | — |
| `GET /api/leagues` | current-season leagues (the house leagues), unchanged | `ui.current_leagues()` |
| `GET /api/leagues?username=` (F3) | a Sleeper user's NFL leagues this season and their own team in each (below) | Sleeper `/user/<name>`, `/user/<id>/leagues/nfl/<season>`, each league's rosters + users |
| `GET /api/leagues/{league_id}/rosters` | the team picker's options | the query in `ui.perspective()` |
| `GET /api/my-week?league=&team=` | Home's My Week: the record line, the league line, the cards (numbers **and** the cards' own text), the lineup (4 columns), the full lineup (+ bench, can't play), "How to read this", movers | `cards.lineup_rows` / `decisions` / `decision_cards` / `league_line` / `lineup_frame` / `howto_cards`; Home's two inline queries copied |
| `GET /api/my-week?league=<any Sleeper id>&team=` (plan E3) | **a league the database does not have** is served on demand: Sleeper's league / rosters / users, the NFL-wide stat lines priced in its scoring, ranges from the nearest fitted scoring, the lineup solved per request; same JSON plus `source: "sleeper"` and `on_demand` (range reference, unmapped players and scoring keys, K / DEF source, timings). `source=sleeper` forces it for a known league. 404 for a league Sleeper does not have, 502 when Sleeper does not answer | `league_lab.anyleague` (`lineup.build`, `scoring.compute_points`), `ondemand.py`, the cards via `myweek.cards_from_rows`; design `docs/ANY_LEAGUE.md` |
| `GET /api/player/{gsis}?league=&team=` | the player card: header + Usage, Projection, Availability, Value, Signals as ordered blocks, + `ros`, `missing`, `source` (F3). Any Sleeper league: built on demand (`source=sleeper` forces it for a house league) | `pages/0_Player.py`'s queries and sentences, copied verbatim; `cards.alternative` / `bench_gap`, `signals.*`; on demand `ondemand.PlayerContext` |
| `GET /api/ros?league=&position=QB\|RB\|WR\|TE\|K\|DEF\|ALL&limit=50` (F3) | rest of season, sorted by points | `mart_player_ros_projection` (house league) or `anyleague.ros_table` (priced on request) |
| `GET /api/record?league=` (F3) | our record vs Sleeper's projections, week by week + the season | `mart_projection_record` (house leagues; `available: false` elsewhere) |
| `GET /api/search?league=&q=` | the player card's search box (25 hits) | the page's query |
| `GET /api/status` | the freshness line, the stale-injury warning, + `sleeper` (cache ages, the call budget) and `board_source` (F3) | `ui.freshness_banner()`, `Sleeper.stats()` |
| `GET /api/docs` | OpenAPI page | — |
| anything else | the web app (`web/dist`): a real file, else `index.html` | — |

**Reuse, not a re-derivation.** `league_lab_api/applib.py` loads `app/lib/cards.py`, `ui.py` and `signals.py`
**unchanged** as a private package whose `db` module is this API's (same `query()` contract, no Streamlit) and
whose `streamlit` is a stand-in that records what a function would have drawn. So the numbers come from the
same SQL and pure functions, and the card text is what `render_decision` writes — a wording change in
`cards.py` (D6 is changing it this round) appears in both front ends with no change here. The player page keeps
its logic inline in the page file, so `player.py` copies it (marked); `tests/test_parity.py` renders the real
Streamlit pages headlessly and fails on any difference.

Every query is cached 10 minutes (the app's `st.cache_data(ttl=600)`); JSON is `Cache-Control: private,
max-age=120`; hashed web assets are immutable; responses are gzipped. A missing mart (a sync in progress)
answers 503 with the app's sentence.

## The JSON of the plan-F3 routes

Errors everywhere: `{"error": "<plain words>", "detail": …}` — 404 an unknown league / team / player / user, 502
`{"error": "Sleeper did not answer"}`, 503 `{"error": "the numbers are not ready yet"}` (a mart missing) or
`{"error": "busy, try again in a minute"}` (our Sleeper budget spent; `Retry-After: 60`).

```jsonc
// GET /api/leagues?username=test_manager            (404 {"error": "no such Sleeper user"})
{"user": {"user_id": "9100000000000000001", "username": "test_manager", "display_name": "Test Manager", "avatar": null},
 "season": 2026,
 "leagues": [   // sorted by name
   {"league_id": "1321941740235550720", "name": "Forever Unclean Dynasty", "season": 2026, "total_rosters": 12,
    "scoring_label": "12-team superflex dynasty · full PPR · 6‑pt pass TD · yardage bonuses", "roster_id": 12,
    "team_name": "Team 11", "status": "in_season", "in_database": true}, …]}
// roster_id / team_name: the user's own (owner_id or co_owners); null in a league they only run.
// scoring_label: dim_league_season.scoring_label's rule (anyleague.scoring_label; equal for the house leagues: tested).

// GET /api/my-week?league=&team=  — as before, plus:
{"source": "database" | "sleeper",
 "opponent": {"roster_id": 6, "team_name": "…", "manager": "…", "matchup_id": 4, "lineup_value": 120.31} | null,
 "scoring_label": "…",                       // on demand too now
 "on_demand": {…, "board_source": "nfl_wide" | "borrow", "opponent_note": null | "busy" | "sleeper_unavailable"}}
// opponent: the roster sharing the matchup_id in Sleeper's /league/<id>/matchups/<week> (cached 5 min); a house
// league falls back to fct_league_matchup when Sleeper is down. lineup_value = his best lineup this week: the
// nightly's (ops.lineup_totals) for a house league, solved on request (lineup.build) otherwise — equal to the cent.

// GET /api/player/{gsis}?league=&team=  — as before, plus:
{"ros": {"points": 236.25, "games": 12, "p10": 196.5, "p90": 276.0, "pos_rank": 1, "playoff_points": 39.18,
         "from_week": 4, "last_week": 16} | null,
 "missing": [],                                // on demand: ["value.points_per_game", "signals.upside"] where they apply
 "source": "database" | "sleeper",
 "on_demand": {"range_method": "ratio", "range_reference": "…", "profile_league": "…", "scoring_label": "…"}}  // on demand only

// GET /api/ros?league=&position=RB&limit=50
{"league_id": "…", "source": "database" | "sleeper", "position": "RB", "from_week": 4, "last_week": 16,
 "playoff_week_start": 15, "pos_rank_note": "…",
 "players": [{"gsis_id", "player_key", "player_name", "position", "team", "ros_points", "ros_games",
              "playoff_points", "p10", "p90", "pos_rank", "rostered_by_roster_id", "rostered_by_team"}, …]}
// player_key = gsis_id, or a team defense's Sleeper id (gsis_id null). pos_rank: among every projected player at
// the position on an active NFL roster, rostered or not — on demand the same population as the mart (tested).

// GET /api/record?league=
{"league_id": "…", "available": true, "season": 2026, "from_week": 4 | null,
 "weeks": [/* mart_projection_record rows, scope = 'week' */], "summary": {/* the season ALL row */, "by_position": […]} | null,
 "notice": null | "No week on the record yet: …"}
{"league_id": "9000000000000000001", "available": false, "why": "the record is kept for the leagues the nightly scores"}

// GET /api/status  — as before, plus:
{"sleeper": {"mode": "live" | "fixtures", "calls": 7, "stale_served": 0,
             "bucket": {"tokens": 293.0, "capacity": 300.0, "per_minute": 300.0, "refused": 0},
             "cache": {"rosters": {"entries": 2, "fresh": 2, "oldest_s": 41.2, "newest_s": 3.0, "ttl_s": 600}, …},
             "players_file_age_s": 5120.4},
 "board_source": "auto" | "nfl_wide" | "borrow"}
```

**Sleeper** (`src/league_lab/sleeper_client.py`; terms and budget: `docs/SLEEPER_TERMS.md`): one client per process,
caches by kind of call (player directory a day, on disk under `LEAGUE_LAB_CACHE_DIR`; league settings and users a
day; rosters 10 min; matchups 5 min; username lookups and league lists an hour), the last good answer served when
Sleeper fails, and a token bucket of `LEAGUE_LAB_SLEEPER_PER_MIN` (300) calls a minute.

**The board** (`anyleague.load_board`): F1's NFL-wide tables (`ops.projection_lines`, `ops.projection_ranges`,
`ops.kd_lines`, the seed `reference_scorings`; their names live in `anyleague.NFL_WIDE`, the one place) when they
hold the week, else E3's borrowing from `ops.projections`. A league's ranges come from the reference scoring whose
mapped keys equal its own, else the nearest by median |log(price ratio)|; K / DEF are priced from their stat lines
in the league's own scoring. `LEAGUE_LAB_BOARD_SOURCE=borrow|nfl_wide` forces one (a kill switch).

## Run it locally

```bash
cd api
uv sync                                                        # its own environment (api/.venv), Python 3.13
uv run uvicorn league_lab_api.main:app --port 8581             # reads the repository's .env (read-only role)
(cd ../web && npm ci && npm run build)                         # the web app at http://localhost:8581/
```

For front-end work, `cd web && npm run dev` (port 8582) proxies `/api` to 8581 and hot-reloads.

## Environment

| Variable | Meaning |
|---|---|
| `LEAGUE_LAB_APP_DB_URL` | the read-only role's connection string (hosted: the same value as the Streamlit secret) |
| `LEAGUE_LAB_APP_DB_USER` / `_PASSWORD`, `LEAGUE_LAB_DB_HOST` / `_PORT` / `_NAME` | used when the URL is not set (the local `.env`) |
| `LEAGUE_LAB_APP_PASSWORD` | the beta password; unset = open, like the app |
| `LEAGUE_LAB_API_SECRET` | optional signing key for the cookie; unset = derived from the password (changing the password signs everyone out) |
| `LEAGUE_LAB_WEB_DIST` | where the built web app is (default `web/dist`) |
| `LEAGUE_LAB_SLEEPER_FIXTURES` | plan E3: read Sleeper from `<dir>/league_<id>.json`, `rosters_<id>.json`, `users_<id>.json`, `players_nfl.json` instead of the network (tests, sandboxes); `python -m league_lab.anyleague fixtures <dir> <id> …` builds them from `raw.sleeper_*` |
| `LEAGUE_LAB_SLEEPER_API` | the Sleeper host (default `https://api.sleeper.app/v1`) |
| `LEAGUE_LAB_SLEEPER_PER_MIN` | plan F3: the Sleeper call budget of this process (default 300 a minute; Sleeper's limit is 1,000) |
| `LEAGUE_LAB_CACHE_DIR` | plan F3: where the Sleeper player directory is kept for a day (default `<repo>/.cache/`, git-ignored; the image: `/srv/cache`) |
| `LEAGUE_LAB_BOARD_SOURCE` | plan F3: `auto` (default: F1's NFL-wide tables when they hold the week), `nfl_wide`, `borrow` |
| `PORT` | the container's port (hosts set it) |

## Tests

```bash
cd api
uv run pytest -q              # 83 tests (see docs/STATUS.md § Wave F for the count on this data); the parity tests render the Streamlit pages: LL_SKIP_PARITY=1 skips them
uv run ruff check .
```

`test_myweek.py` / `test_player.py` check every endpoint against the marts with independent SQL (dynasty roster
12 and Scrubs roster 2, the current week); `test_parity.py` compares with the rendered Streamlit pages (it runs
`tests/streamlit_twin.py` in the repository's environment with `uv run --project ..`); `test_auth.py` the gate;
`test_static.py` the web app's files and headers; `test_anyleague.py` (plan E3) the on-demand path against the
marts with the two leagues' own Sleeper payloads as fixtures (`tests/fixtures/sleeper/`): the lineup to the cent,
the range error, an unknown league through the route, cold / warm latency (pinned to the borrowed board).
`test_f3.py` (plan F3): the Sleeper client with a fake clock (TTLs, the bucket, stale answers, the directory on
disk), the league picker, the opponent against `ops.lineup_totals`, the NFL-wide board against the marts (exact),
the fictional Test League with a K and a DEF, rest of season on demand against `mart_player_ros_projection`, the
player card on demand, the record, the status line, error shapes, the static app from a placeholder `dist`. The
fixtures: `tests/fixtures/make_f3_fixtures.py` (a fictional user `test_manager`; every Sleeper user id
pseudonymised); the NFL-wide tables in a clone: `psql … -f tests/fixtures/f1_tables.sql` (the NFL-wide tests skip
without them).

## Deploy (one service, the static app included)

`api/Dockerfile` builds the web app and the API into one image; build it from the repository root:

```bash
docker build -f api/Dockerfile -t league-lab-web .
docker run -p 8000:8000 -e LEAGUE_LAB_APP_DB_URL='postgresql://league_lab_app:…@…neon.tech/neondb?sslmode=require' \
           -e LEAGUE_LAB_APP_PASSWORD='…' league-lab-web
```

* **Render** (free web service: 512 MB, sleeps after 15 minutes without traffic, ~1 minute to wake; $7/month
  for always on): New → Web Service → the GitHub repo → Runtime *Docker*, Dockerfile path `api/Dockerfile`,
  build context `.` → Environment: the two variables above → health check path `/api/health`.
* **Fly.io** (no free allowance; a shared-cpu-1x 256 MB machine ≈ $2–3/month always on, less with
  auto-stop): `fly launch --dockerfile api/Dockerfile` from the repository root, `fly secrets set
  LEAGUE_LAB_APP_DB_URL=… LEAGUE_LAB_APP_PASSWORD=…`.
* **Railway** (Hobby $5/month including $5 of usage; a free plan of 0.5 GB RAM and one project): New project →
  Deploy from GitHub → set `RAILWAY_DOCKERFILE_PATH=api/Dockerfile` and the two variables.
* **Cloud Run** (2 million requests, 180,000 vCPU-seconds and 360,000 GiB-seconds free a month; scales to
  zero, a cold start of a few seconds): `gcloud run deploy league-lab --source .` with the Dockerfile path set.

Neon does not change: the API reads the same published marts with the same read-only role. The nightly does
not change either (it publishes marts; the API has no state of its own). A push to GitHub redeploys the
service; there is no restart stamp to bump (`app/requirements.txt`'s rule is Streamlit Community Cloud's).

If `app/lib/cards.py` ever imports from `league_lab.*` (the `src/` package), copy `src/` into the image too
(the stand-in already puts `src/` on the path) and add that module's dependencies to `api/pyproject.toml`.
