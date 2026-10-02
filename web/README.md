# League Lab web app (plan D7 spike → Wave F phase 1, plan F2)

The phone-first web app any Sleeper manager uses: sign in with a Sleeper username, pick a league, then My Week,
the player card, rest of season and our record — for **any** Sleeper league (the API serves a league the database has
never seen on demand). Svelte 5 + TypeScript + Tailwind 4, built by Vite into static files that the API (`api/`)
serves — one deploy. It reads only the API; the API reads the same marts as the Streamlit app and speaks for
`app/lib`'s sentences. `docs/FRONTEND_DECISION.md` says why it exists and what it measured.

## The screens

| Screen | URL | What |
|---|---|---|
| Password | any | the beta gate (when the API has `LEAGUE_LAB_APP_PASSWORD`); a right password sets an HttpOnly cookie for 180 days |
| Sign in / league picker | `/` with no league known, or `/leagues` | one field, **"Your Sleeper username"** → `GET /api/leagues?username=` → the user's leagues this season (name, size and scoring, "Your team: …"), each a real link to its My Week with the user's own team pre-selected. "You have no team in this league" when `roster_id` is null (the team is then picked on My Week). Sleeper has no such user / Sleeper down: one plain sentence each. The username and the list are remembered on this phone (`ll.user`, `ll.userLeagues`); "Not you?" forgets them. Reached later from the league select's last option, "Other leagues (your Sleeper username)…" |
| My Week | `/?league=&team=` | the picker (league / team) and the three screens as tabs; the record line, then the **opponent of the week** ("Week 5 vs **Team**, projects 108 — you project 112": whole points, one decimal when whole points would hide the difference; just "Week 5 vs **Team**" without values; nothing without a matchup), the league line, the three closest calls as cards (the cards' text is `app/lib/cards.py`'s own), the lineup, the full lineup, "How to read this", movers. A `?league=&team=` link wins over what the phone remembers, and works for any league id |
| Player card | `/player/<gsis>?league=&team=` | Projection, Value, Availability, Usage, Signals (the answer first). The **rest-of-season line** is the API's sentence (`app/lib/ros.py` `card_line`, inside the Projection section today; `ros.line` if the API sends it separately), plus a link to the rest-of-season list at his position. A section listed in `missing` is left out and named in one line ("Not shown for Test League yet: Value.") |
| Rest of season | `/ros?league=&team=&position=` | the answer first ("**#1 WR for the rest of the season: Puka Nacua, 185 points over 12 games** (likely 150–219) · playoffs: 30."), then "Yours: #3 Jaxon Smith-Njigba 178 · …", then the list (Rank · Player · Points · Games · Playoffs; the user's players tinted; under each name his NFL team and who has him). Position switch QB / RB / WR / TE, **K and DEF only when the league starts them**, All = the overall rank (default). The switch rewrites the URL in place (no Back step) |
| Our record | `/record?league=` | the summary sentences and two numbers (calls right, average miss) from `GET /api/record`, the start/sit table week by week, the by-position table behind an expander, "How to read this" — or the honest empty state: "No week on the record yet. …" (no week saved before kickoff yet) / "No record for Test League. The record is kept for the leagues the nightly scores." (`available: false`) — the Streamlit page's words (`app/pages/13_Record.py`) |

**One tap, one tab.** Every name, league row and tab is a real link (`<a href>`, so long-press / share work) that the
app handles in place: no reload, no new tab, no new session. Back (the button or the browser's) returns to the same
scroll position — an expander that was open is open again, so the page has its old height; picking a league, a team or
a position rewrites the URL without adding a Back step.

**Phone first.** 390 px is the design width; one column up to 576 px (centred on a desktop); no table wider than the
screen (five columns at most); light / dark from the system; system fonts (nothing to download).

**Installable.** `public/manifest.webmanifest` (standalone, icons 192 / 512 / maskable, `apple-touch-icon`) and a
small service worker (`public/sw.js`: hashed files cache-first, the shell network-first, `/api` never cached).
On an iPhone: Safari → Share → *Add to Home Screen*.

**Fast first screen.** An inline script in `index.html` starts the first screen's API call before the app's
JavaScript arrives (≈34 KB gzipped JS + 5 KB CSS): My Week, the player card, rest of season or our record from the
URL's (or the remembered) league / team; on the sign-in screen with a username remembered, the user's league list.
Its URLs must match `src/lib/api.ts` `paths` exactly. Answers are kept in memory for five minutes, so Back and a
second visit render at once.

## Run

```bash
cd api && uv run uvicorn league_lab_api.main:app --port 8581      # the API (reads the repository's .env)
cd web && npm ci && npm run build                                 # → web/dist, served by the API at http://localhost:8581/
npm run dev                                                       # or: dev server on :8582 with hot reload, /api proxied to :8581
```

## Check

```bash
npm run lint                                   # eslint + svelte-check (types, a11y) + tsc on the e2e / config files
npm run build && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npm run e2e:fixtures
                                               # the app on FIXTURES: no API, no database, no Sleeper (vite preview :8584)
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npm run measure:fixtures
                                               # first content on fixtures (≤ 500 ms) → e2e/.out/measure_fixtures.{json,md}
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npm run e2e      # the spike's checks against a running API (E2E_BASE_URL, default :8581)
E2E_GATED_URL=http://localhost:8583 E2E_GATED_PASSWORD=… npm run e2e    # + the password screen (an API started with that password)
MEASURE_ST_URL=… npm run measure               # the D7 side by side with Streamlit (see e2e/measure.spec.ts)
```

`e2e/fixtures.spec.ts` (phone 390 × 844 with touch, desktop 1300 × 900) walks the stranger's path on the fictional
Test League — password (wrong, then right) → username (unknown, then known) → the picker → My Week (opponent line, the
first card inside the first screen, ≤ 5 columns, nothing says "not in the database") → a name in the lineup (one tap,
same tab, one history entry) → the card (Value omitted and named, the rest-of-season line) → Back (same scroll
position) → rest of season (K / DEF shown, WR's answer and "Yours") → our record (`available: false`) → a bare visit
remembers the league and team. Then a house league through the picker (all five sections, no K / DEF, a scored
record), a shared link without a username (Scrubs: K, the empty record, the league select's "Other leagues…"),
the commissioner-only league (no team → pick one), Sleeper down and "Not you?", dark mode, manifest + service worker.
Screenshots `f2_*` go to `SHOTS_DIR` (default `e2e/.out`).

## Fixtures

`fixtures/*.json`, one file per API response, served by `e2e/fixtures.ts` (Playwright route interception on the
browser context: every `/api` call, including the simulated password gate, password `fixture-beta`). Rebuilt by
`fixtures/make_fixtures.py` (needs an API on the clone and `psql`; its docstring has the command).

| File | Route | Source |
|---|---|---|
| `leagues.json` | `/api/leagues` | saved (the house leagues) |
| `leagues_user_fixture_user.json`, `leagues_user_fixture_commish.json` | `/api/leagues?username=` | hand-written to the contract: a fictional user with the two house leagues and the Test League; one with no team in the Test League (`roster_id: null`). Any other username → 404 `{"error": "no such Sleeper user"}`; `sleeper_down` → 502 |
| `rosters_<league>.json` | `/api/leagues/{id}/rosters` | saved; the Test League's 10 teams made up |
| `my-week_<league>_<team>.json` | `/api/my-week` | saved for dynasty 12 and Scrubs 2 (week 4) **plus** the contract's `source: "database"` and `opponent` object (the clone has no week-4 matchups: dynasty 12 vs roster 11, Scrubs 2 vs roster 1, `lineup_value` = that roster's week-4 starters in `ops.lineups`); the Test League's team 3 hand-made (`source: "sleeper"`): real players, their week-4 projections and ranges in Scrubs scoring, three cards in `cards.py`'s words |
| `player/<league>_<gsis>.json` | `/api/player/{gsis}` | saved for every player in both lineups (+ `ros` from the mart, `missing: []`); the Test League's from the Scrubs card retold (owner, no Value section, `missing: ["value"]`) |
| `ros_<league>_<POS>.json` | `/api/ros` | from `mart_player_ros_projection` in the contract's shape (+ the owner from `mart_player_availability`; the Test League's owners made up) |
| `record_<league>.json` | `/api/record` | Scrubs: the clone's real answer (nothing yet: `weeks: []`); dynasty: three scored weeks **hand-written** (the mart is empty on the clone); Test League: `available: false` |
| `search_<league>.json`, `status.json` | `/api/search`, `/api/status` | saved |
| `error_*.json` | the contract's errors | hand-written |

## Deploy

With the API: `api/Dockerfile` builds this app and serves it (see `api/README.md`). No environment variables
of its own; it talks to the API on the same origin.

## Files

| Path | What |
|---|---|
| `src/App.svelte` | boot (the gate, the house leagues, the remembered user's leagues), the league / team rule, the route switch |
| `src/routes/Leagues.svelte` | sign in with a Sleeper username → the league picker |
| `src/routes/MyWeek.svelte`, `Player.svelte`, `Ros.svelte`, `Record.svelte` | the four screens |
| `src/components/TopBar.svelte` | the picker + the three tabs (My week, Rest of season, Our record) |
| `src/components/*` | picker, lineup table, section card, metric tiles, expander (remembers open per page), markdown, login |
| `src/lib/api.ts` | the API's types (the Wave F contract included), fetch + five-minute memory cache, the prefetch hand-off |
| `src/lib/week.ts`, `ros.ts`, `record.ts` | My Week's record / opponent lines; rest of season's answer / "Yours"; our record's sentences (the Streamlit pages' words) |
| `src/lib/leagues.ts` | the league select's options (the user's leagues, else the house leagues, plus a linked league) |
| `src/lib/router.svelte.ts` | History-API router: same-tab links, Back with scroll restore, URL rewrites without history |
| `src/lib/md.ts` | the pages' markdown subset (bold, links, line breaks, bullets), escaped before rendering |
| `src/lib/prefs.ts` | the remembered pick and username (`localStorage`, guarded) |
| `public/` | manifest, icons (`scripts/make-icons.py`), service worker |
| `fixtures/` | the API's answers for the fixture tests, and `make_fixtures.py` |
| `e2e/` | `fixtures.spec.ts` + `fixtures.ts` (on fixtures), `measure-fixtures.spec.ts`, the spike's `app.spec.ts` (live API) and side-by-side `measure.spec.ts` |
