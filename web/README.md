# League Lab web app (plan D7 spike → Wave F phase 1, plan F2 → Wave G design system + research, G3)

The phone-first web app any Sleeper manager uses: sign in with a Sleeper username, pick a league, then My Week,
the player card, rest of season, the research screens (Trends, Matchups, Players, Receivers, Compare) and About the
numbers — for **any** Sleeper league (the API serves a league the database has
never seen on demand). Svelte 5 + TypeScript + Tailwind 4, built by Vite into static files that the API (`api/`)
serves — one deploy. It reads only the API; the API reads the same marts as the Streamlit app and speaks for
`app/lib`'s sentences. `docs/FRONTEND_DECISION.md` says why it exists and what it measured; `docs/DESIGN.md` is the
design system (tokens, components, the chart kit, the rules).

**The bar (Wave G).** Every league screen sits under one bar (`TopBar`): the league / team picker and five tabs — My
week · Rest of season · **Research** (Trends, Matchups, Players, Receivers, Compare as a second row) · **Decisions**
(Waivers, Trades, Team, League: G4's screens; a "coming" card until they land) · **About**. On a phone the five tabs
are a bottom bar (icons + short labels); from 900 px they sit in the top bar and the screens use the width (list on
the left, detail on the right). Dark first, a light mode from the system.

## The screens

| Screen | URL | What |
|---|---|---|
| Password | any | the beta gate (when the API has `LEAGUE_LAB_APP_PASSWORD`); a right password sets an HttpOnly cookie for 180 days |
| Sign in / league picker | `/` with no league known, or `/leagues` | one field, **"Your Sleeper username"** → `GET /api/leagues?username=` → the user's leagues this season (name, size and scoring, "Your team: …"), each a real link to its My Week with the user's own team pre-selected. "You have no team in this league" when `roster_id` is null (the team is then picked on My Week). Sleeper has no such user / Sleeper down: one plain sentence each. The username and the list are remembered on this phone (`ll.user`, `ll.userLeagues`); "Not you?" forgets them. Reached later from the league select's last option, "Other leagues (your Sleeper username)…" |
| My Week | `/?league=&team=` | the picker (league / team) and the three screens as tabs; the record line, then the **opponent of the week** ("Week 5 vs **Team**, projects 108 — you project 112": whole points, one decimal when whole points would hide the difference; just "Week 5 vs **Team**" without values; nothing without a matchup), the league line, the three closest calls as cards (the cards' text is `app/lib/cards.py`'s own), the lineup, the full lineup, "How to read this", movers. A `?league=&team=` link wins over what the phone remembers, and works for any league id |
| Player card | `/player/<gsis>?league=&team=` | his **player card** on top (headshot, the week's projection as the big number, position + team badges, the depth chart and owner), then Projection beside **Points by week** (the game log: points in this league's scoring and expected points by week, 2026 / 2025, `GET /api/player/{gsis}/games`), then Value, Availability, Usage, Signals (the answer first). The **rest-of-season line** is the API's sentence (`app/lib/ros.py` `card_line`, inside the Projection section today; `ros.line` if the API sends it separately), plus a link to the rest-of-season list at his position. A section listed in `missing` is left out and named in one line ("Not shown for Test League yet: Value.") |
| Rest of season | `/ros?league=&team=&position=` | the answer first ("**#1 WR for the rest of the season: Puka Nacua, 185 points over 12 games** (likely 150–219) · playoffs: 30."), then "Yours: #3 Jaxon Smith-Njigba 178 · …", then the list (Rank · Player · Points · Games · Playoffs; the user's players tinted; under each name his NFL team and who has him). Position switch QB / RB / WR / TE, **K and DEF only when the league starts them**, All = the overall rank (default). The switch rewrites the URL in place (no Back step) |
| Trends | `/trends?league=&team=&view=&position=&who=&pick=` | over- vs under-performing: the answer first ("Due to pick up: X (14.9 a game on work worth 25.3). Running hot: Y …"), the two as player cards, then every player as a row with his gap (points a game minus expected points a game, this league's scoring) as a diverging bar; filters Everyone / Due / Running hot, position, Everyone / Yours / Free agents (in the URL, no Back step). From 900 px the picked player's detail on the right: his card, the two numbers as bars, his role alert, last-3 tiles, his points by week. `GET /api/trends` |
| Matchups | `/matchups?league=&team=` | the answer first (your starters' best and toughest matchup, "#2 vs RB"), your starters with their rank chips, the cornerbacks your receivers face (`cb_line`'s sentence, the side bar: where his targets go, the corner's side highlighted, the corner's rank), and the **defense-vs-position heatmap** (32 teams × the positions the league starts, points allowed a game, your starters' cells ringed and their defenses first). `GET /api/matchups/defense`, `/api/matchups/cb` |
| Players | `/players?league=&team=&position=&who=&nfl=&sort=&dir=&q=` | every skill player's season as a sortable table with headshots: the points leader first, search, position, NFL team, whose; a phone keeps Player · Pts/g · Pts, the usage columns join from 640 px. Loaded once per league (`limit=500`), filtered and sorted on the phone. `GET /api/players` |
| Receivers | `/receivers?league=&team=&position=&who=&pick=` | WR / TE roles: the biggest share of his team's targets first, the list (target share, last-3 share), the picked receiver's role as bars against the yardstick (the top 12's average: a tick on each bar) and his share over his last 3 / 5 games vs the season. `GET /api/receivers` |
| Compare | `/compare?league=&team=&a=&b=` | two players side by side; opens on your closest call this week (My Week's first card), a search on each side picks anyone (from the players list). The answer first (this week's projections, rest of season), the two as player cards, then paired bars (blue / orange, the better number bold): this week, the season, last 3 games, usage, rest of season, the next 4 opponents. `GET /api/compare` |
| About the numbers | `/about?league=` (`/record` still opens it) | where the projections come from (the Rankings page's "The model" words: what it learned from, what it predicts, the ranges, how it was graded, what it does not know, what we tried), then **our record** against Sleeper's projections: the summary sentences and two numbers (calls right, average miss) from `GET /api/record`, the start/sit table week by week, the by-position table behind an expander, "How to read this" — or the honest empty state: "No week on the record yet. …" (no week saved before kickoff yet) / "No record for Test League. The record is kept for the leagues the nightly scores." (`available: false`) — the Streamlit page's words (`app/pages/13_Record.py`) |

**One tap, one tab.** Every name, league row and tab is a real link (`<a href>`, so long-press / share work) that the
app handles in place: no reload, no new tab, no new session. Back (the button or the browser's) returns to the same
scroll position — an expander that was open is open again, so the page has its old height; picking a league, a team or
a position rewrites the URL without adding a Back step.

**Phone first.** 390 px is the design width; from 900 px the screens use the width (up to 1152 px: list + detail, two
columns); no table wider than the screen (columns past three or four show from 640 px); dark first, light from the
system; system fonts (nothing to download); headshots load lazily and fall back to a silhouette.

**Installable.** `public/manifest.webmanifest` (standalone, icons 192 / 512 / maskable, `apple-touch-icon`) and a
small service worker (`public/sw.js`: hashed files cache-first, the shell network-first, `/api` never cached).
On an iPhone: Safari → Share → *Add to Home Screen*.

**Fast first screen.** An inline script in `index.html` starts the first screen's API call before the app's
JavaScript arrives (≈45 KB gzipped JS for the first screen + 7 KB CSS; the research screens and About load on first use,
4–6 KB each): My Week, the player card, rest of season, about, trends, matchups, players, receivers or compare from the
URL's (or the remembered) league / team; on the sign-in screen with a username remembered, the user's league list.
Its URLs must match `src/lib/api.ts` `paths` / `researchPaths` exactly. Answers are kept in memory for five minutes, so Back and a
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
                                               # the app on FIXTURES: no API, no database, no Sleeper (vite preview :8584;
                                               # FIXTURES_PORT=… for another port, G3_SHOTS_DIR=… for the g3_* screenshots)
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
Wave G (G3): Trends (the answer, the gap bars, filters in the URL, the detail at 1300 / none at 390, a name → the card
and its game log, 2025's weeks), Matchups (best / toughest, 32 heatmap rows, ringed cells, the corner cards), Players
(the leader, 3 columns on a phone, search, sort, whose), Receivers (the yardstick bars, routes not shown as 0), Compare
(opens on My Week's closest call with the same numbers, paired bars, pick another), the Test League on the research
routes, headshots (a picture / the silhouette), the bottom bar vs the top bar and the Decisions "coming" cards, and
**every screen in light and in dark** (no sideways scroll, the background of each mode). Screenshots `f2_*` and
`g3_<screen>_<phone|desktop>_<light|dark>` go to `SHOTS_DIR` / `G3_SHOTS_DIR` (default `e2e/.out`).

## Fixtures

`fixtures/*.json`, one file per API response, served by `e2e/fixtures.ts` (Playwright route interception on the
browser context: every `/api` call, including the simulated password gate, password `fixture-beta`). Rebuilt by
`fixtures/make_fixtures.py` (needs an API on the clone and `psql`; its docstring has the command); the research
routes' files by `fixtures/make_research_fixtures.py` (the clone's marts through `psql`, app/lib's sentences:
`PGPASSWORD=… uv run python web/fixtures/make_research_fixtures.py`, `DB=league_lab_g3`). Headshots
(`static.www.nfl.com`) are never fetched by a test: the fixture server aborts them (the silhouette shows).

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
| `trends_<league>.json` | `/api/trends` (any `view` / `position`: the screen filters) | `mart_player_availability` (`ppg_std`, `expected_per_game`, `diff_per_game` = ppg / xppg / gap in the league's scoring) + `mart_player_trend_tags` (2026) + live `mart_player_role_alerts` (+ `kind_label`), the 120 biggest gaps, owners |
| `matchups_defense_<league>_<team>.json` | `/api/matchups/defense?team=` | `mart_defense_vs_position_current` (2026, QB / RB / WR / TE + K where the league starts one) + `starters`: the team's week-4 starters and the defense each faces (`mart_player_week_projections`) — a field G3 asks of G1 |
| `matchups_cb_<league>_<team>.json` | `/api/matchups/cb` | `mart_cb_matchups` week 4 for the team's WR / TE (+ `shadow_flag` from `mart_cb_rankings`, the projection), `line` = `cb_line`, `lean` = `lean_text` |
| `players_<league>.json` | `/api/players` | `mart_player_season` 2026 REG + points / points a game from `fct_player_game_league` (the league's scoring), owners |
| `receivers_<league>.json` | `/api/receivers` | `mart_player_season` WR / TE usage + the latest `mart_player_recent_form` row, and `yardsticks` (the top 12 by points a game, per position) |
| `compare_<league>.json` | `/api/compare?a=&b=` | one side per player (both lineups + the top 60 by points + the top 30 gaps), `{a, b}` composed by the fixture server; another player → 404 |
| `games_<league>.json` | `/api/player/{gsis}/games?season=` | `fct_player_game` 2025–2026 REG + `points` / `expected_points` from `fct_player_game_league`, per player; the server filters the season |

The Test League's research files are Scrubs' numbers (the same half-PPR scoring) with the Test League's owners (team 3 =
its My Week roster).

## Deploy

With the API: `api/Dockerfile` builds this app and serves it (see `api/README.md`). No environment variables
of its own; it talks to the API on the same origin.

## Files

| Path | What |
|---|---|
| `src/App.svelte` | boot (the gate, the house leagues, the remembered user's leagues), the league / team rule, the route switch |
| `src/routes/Leagues.svelte` | sign in with a Sleeper username → the league picker |
| `src/routes/MyWeek.svelte`, `Player.svelte`, `Ros.svelte`, `About.svelte` | My Week, the player card, rest of season, about the numbers (+ the record) |
| `src/routes/Trends.svelte`, `Matchups.svelte`, `Players.svelte`, `Receivers.svelte`, `Compare.svelte` | the research screens (lazy chunks) |
| `src/components/TopBar.svelte` | the picker + the five tabs (bottom bar on a phone) + the section's second row |
| `src/components/*` | the design system (`docs/DESIGN.md`): Card, PlayerCard, PlayerRow, Headshot, PosBadge, TeamBadge, StatTile, Bar, Meter, Table, ListDetail, Tabs, Chips, ScreenHead, Coming; the chart kit LineChart, Heatmap, Sparkline; GameLog; and Wave F's picker, lineup table, section card, metric tiles, expander, markdown, login |
| `src/lib/api.ts` | the API's types (the Wave F contract, the G3 research block), fetch + five-minute memory cache, the prefetch hand-off |
| `src/lib/theme.ts`, `chart.ts` | team accents (32 teams), position colors, chart roles, number formats; the chart kit's scale and paths |
| `src/lib/remote.svelte.ts`, `research.ts`, `about.ts` | one API answer per screen (cache first, plain-words errors); the research screens' words; About's model words |
| `src/lib/week.ts`, `ros.ts`, `record.ts` | My Week's record / opponent lines; rest of season's answer / "Yours"; our record's sentences (the Streamlit pages' words) |
| `src/lib/leagues.ts` | the league select's options (the user's leagues, else the house leagues, plus a linked league) |
| `src/lib/router.svelte.ts` | History-API router: same-tab links, Back with scroll restore, URL rewrites without history |
| `src/lib/md.ts` | the pages' markdown subset (bold, links, line breaks, bullets), escaped before rendering |
| `src/lib/prefs.ts` | the remembered pick and username (`localStorage`, guarded) |
| `public/` | manifest, icons (`scripts/make-icons.py`), service worker |
| `fixtures/` | the API's answers for the fixture tests, and `make_fixtures.py` |
| `e2e/` | `fixtures.spec.ts` + `fixtures.ts` (on fixtures), `measure-fixtures.spec.ts`, the spike's `app.spec.ts` (live API) and side-by-side `measure.spec.ts` |

## The decision screens (Wave G, plan G4)

Under the **Decisions** tab (G3's navigation): four screens on G2's routes, each opening with the answer, in G3's
components (`docs/DESIGN.md`). Each loads on first use in its own chunk (`src/lib/decisionPages.ts`), so the first
screen stays as small as Wave F measured it.

| Screen | URL | What |
|---|---|---|
| Waivers | `/waivers?league=&team=&position=` | the answer first (the top claim's sentence, `2_Waiver_Wire.py` `_headline`: "Claim A (TE), drop B: +3.4 this week at TE, +9.0 over the next 4 weeks", or "Nothing beats what you have."), four tiles (this week, next 4 weeks, your lineup → with the claim, the closest call), the moves as cards (top claim, best cover for a coming week, a flyer: the free agent's headshot and badges, the gain as the big number, what each of the next four weeks gains as small bars, the drop, the card's lines), the other claims in an expander, then **free agents by position** (All / QB / RB / WR / TE, K and DEF when the league starts them): one row each with this week's projection, its range on one track (most weeks as the band, a bad week to a good week as the line, the projection as the tick) and rest of season; from 900 px the picked one is a player card on the right (range, rest of season, points and expected points a game, target and snap shares). "How to read this" |
| Trade Finder | `/trades?league=&team=&partner=&give=&get=&want=` | the answer first: the **best partner** (the trade that raises both lineups the most, `trades.partners`) with "Try this trade"; **Try a trade**: the partner select, both rosters as tick lists (`/api/team` for each side), and the package evaluated as soon as both sides have a player (POST `/api/trades/evaluate`): the headline and the **verdict** (`trades.verdict`, the engine's words), the fit as four tiles (you / them, this week / over the weeks, before → after), the market and rest of season as bars (give vs get), the roster-size line, both lineups after the trade slot by slot (new players marked, the change per slot), week by week in an expander; **Who should I trade with?** (Any / QB / RB / WR / TE) as cards with "Try it". The package is the URL (Sleeper ids): a copied link opens the same trade |
| Team | `/team?league=&team=` | the answer first ("Week 4: your best lineup projects 111.2, 11th of 12 in the league."), tiles (lineup value, next 4 weeks, depth, record, each with its rank), the closest call and how the starters were acquired, **strength by slot vs the league** (bars: your best starter at the slot, the league's average as the tick, orange below it), the next four weeks against the league's middle team, every roster's lineup value (yours marked), the roster as player rows (slot, margin, how he was acquired) |
| League | `/league?league=&team=` | the answer first (`8_League.py`: "You've been the unluckiest team by schedule (−0.9 wins); your bench has left 49 points unstarted …"; without a team, the league's luckiest and unluckiest), standings with the all-play record, **who has been lucky** (diverging bars around 0), points left on the bench, the weekly scoring rank (last 5 weeks on a phone, 10 on a desktop), the latest moves (one card per transaction), the draft where Sleeper has it (two rounds, the rest in an expander; pick → position rank by points so far) |

**The contract they read** is G2's (`api/league_lab_api/decisions.py` on `dev/G2`, `api/README.md` § G2): the
fixtures are its own answers, SAVED from G2's routes running on a clone (`fixtures/save_decision_fixtures.py`, see
below), so the shapes match by construction. Rows carry the marts' column names, player objects carry `headshot_url`
/ `team` / `position`, the pages' sentences come as `words` (`words.headline`, `words.lines`, `fit.words`,
`market.words`, `ros.words`, `size_words`, `ranks.words`, `notice`) and the screens show them as they come; where a
sentence is missing the screen writes it (`src/lib/decisions.ts`, the Streamlit pages' words). **Requested of G2**
(the saver adds them from G2's own answers, so the numbers are G2's): on `/api/team`, `slot_strength[].league = {avg,
best, rank, n}` (every roster's best starter at the slot: the "vs the league" bars) and `weekly[].league = {median,
best, rank, n}`; on `/api/waivers`, `positions` (the free-agent tabs; without it: QB RB WR TE, plus K / DEF when the
list has them). Not in the contract and asked for: the league's name on `/api/league` (the screen takes it from the
league picker).

**Fixtures**: `fixtures/{waivers_<league>_<team>_<POS>, trades_evaluate_<league>_<team>_<partner>_<give>_<get>,
trades_partners_<league>_<team>_<WANT>, team_<league>_<roster>, league_<league>[_<team>]}.json` — dynasty roster 12,
Scrubs roster 2 and the Test League's team 3; every roster's Team (the partner picker reads the partner's roster
there); two trades per league (the best partner's, and one by hand). The house leagues come from their marts, the
Test League from G2's on-demand path (its Sleeper fixtures), its teams renamed to the web fixtures' names ("Team 3" →
"Fixture Falcons"). Rebuild: G2's API on a clone, then the saver:

```bash
cd api && LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper uv run uvicorn league_lab_api.main:app --port 8694 &
API=http://localhost:8694 python3 web/fixtures/save_decision_fixtures.py
```

Served by `e2e/decisions-fixtures.ts` (registered after `serveFixtures`; nfl.com headshots answered 404 at once, so the
silhouette shows offline).

**Check**: `npm run e2e:fixtures` runs `e2e/decisions/fixtures.spec.ts` with F2's and G3's (the four screens × phone / desktop
× light / dark, numbers read from the fixtures, nothing past the screen's right edge, the Decisions tab); alone, on its own
port: `E2E_PORT=8594 npx playwright test --config playwright.g4.config.ts`. Screenshots `g4_*` in `SHOTS_DIR`.

| Path | What |
|---|---|
| `src/routes/Waivers.svelte`, `Trades.svelte`, `Team.svelte`, `League.svelte` | the four screens |
| `src/routes/decisions/MoveCard.svelte`, `RangeBar.svelte` | a waiver move as a card; a projection and its range on one track |
| `src/lib/decisions.ts` | the screens' words (waiver headline, team answer and closest call, luck line, partner line) and number formats |
| `src/lib/decisionPages.ts` | the four screens loaded on first use |
| `src/lib/api.ts` (`// ---- G4`) | G2's shapes as types, `decisionPaths`, `postEvaluate` |
| `fixtures/save_decision_fixtures.py`, `e2e/decisions-fixtures.ts`, `e2e/decisions/fixtures.spec.ts`, `playwright.g4.config.ts` | the fixtures' saver, their routes, the e2e, the e2e alone on its own port |
| `fixtures/save_ia1_fixtures.py`, `e2e/ia1/fixtures.spec.ts` (IA-1) | brings the saved My Week and Trends answers to Wave I-A's shapes in place (cards' reasons, lineup headshots, Trends' work a game); the e2e for My Week, Trends, Matchups, Compare at 375 and 1300 |
