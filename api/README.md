# League Lab API (plan D7 spike)

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
| `GET /api/leagues` | current-season leagues | `ui.current_leagues()` |
| `GET /api/leagues/{league_id}/rosters` | the team picker's options | the query in `ui.perspective()` |
| `GET /api/my-week?league=&team=` | Home's My Week: the record line, the league line, the cards (numbers **and** the cards' own text), the lineup (4 columns), the full lineup (+ bench, can't play), "How to read this", movers | `cards.lineup_rows` / `decisions` / `decision_cards` / `league_line` / `lineup_frame` / `howto_cards`; Home's two inline queries copied |
| `GET /api/player/{gsis}?league=&team=` | the player card: header + Usage, Projection, Availability, Value, Signals as ordered blocks | `pages/0_Player.py`'s queries and sentences, copied verbatim; `cards.alternative` / `bench_gap`, `signals.*` |
| `GET /api/search?league=&q=` | the player card's search box (25 hits) | the page's query |
| `GET /api/status` | the freshness line and the stale-injury warning | `ui.freshness_banner()` |
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
| `PORT` | the container's port (hosts set it) |

## Tests

```bash
cd api
uv run pytest -q              # 39 tests; ~70 s (the parity tests render the Streamlit pages: LL_SKIP_PARITY=1 skips them)
uv run ruff check .
```

`test_myweek.py` / `test_player.py` check every endpoint against the marts with independent SQL (dynasty roster
12 and Scrubs roster 2, the current week); `test_parity.py` compares with the rendered Streamlit pages (it runs
`tests/streamlit_twin.py` in the repository's environment with `uv run --project ..`); `test_auth.py` the gate;
`test_static.py` the web app's files and headers.

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
