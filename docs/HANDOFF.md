# Handoff — League Lab, 2026-10-05

For the next agent (Claude Code or any other) picking this repo up. Read in this order:
`AGENTS.md` (rules) → this file → `docs/PROJECT_PLAN.md` § Iteration 9 (the tasks) →
`docs/STATUS.md` (evidence) → `docs/METRICS.md` and `docs/DATA_MODEL.md` when touching a metric or mart.

## Where things stand

* **The product's name is isuckatfantasy** (2026-10-04, Andrew: "rename the app effective immediately"; he is on the
  domain). One constant on each side — `web/src/lib/brand.ts` (`APP_NAME`, `APP_MARK` "isaf"; the icons from
  `web/scripts/make-icons.py`) and `api/league_lab_api/settings.py` (`APP_NAME`) — every sentence a manager reads
  takes it from there. The codebase, the package, the `LEAGUE_LAB_*` variables, the roles, the repository, the
  Render service and the console stay League Lab. **The domain `isuckatfantasy.io` (2026-10-04)**: Cloudflare has
  the two DNS-only CNAMEs and SSL "Full" (done by the PO on Andrew's yes); `render.yaml` carries `domains:
  [isuckatfantasy.io]` (the service is Blueprint-managed: the push syncs it, Render adds `www.` and the certificate);
  README / HOSTING § "The domain" / DEPLOY / smoke.sh say the address. **Verify after the push**: Render's service
  page lists the domain as verified; `https://isuckatfantasy.io/api/health` answers. The
  `image` workflow's smoke step and `scripts/smoke.sh` assert the product name in the served page title (the rename's
  first CI run failed there; fixed 2026-10-04) — a future rename changes `brand.ts`, `settings.py` and those two lines.

* Everything through **Wave A of Iteration 9** is built, tested and committed: two Sleeper leagues side by
  side (`LEAGUE_LAB_SLEEPER_LEAGUE_ID=<reference>,<other>`), the Phase 2 play-by-play layer, the
  OLS baseline rankings with backtest, and **Projection v2** (per-league stat-line projections with
  a calibrated floor/ceiling, walk-forward validated 2021–2025). The Streamlit console is live on Streamlit
  Community Cloud and **the beta (FastAPI + Svelte, any Sleeper league) is live on Render:
  `https://league-lab.onrender.com`** (Blueprint `league-lab` from `render.yaml`, Starter, Ohio; deployed
  2026-10-02, every route and screen checked on the server — `docs/STATUS.md` § "Deploy"). Both read the
  Neon Postgres copy. **Who writes Neon: GitHub Actions' nightly** (Wave H's one writer), live since
  2026-10-02 evening: Andrew set its three secrets (`LEAGUE_LAB_SLEEPER_LEAGUE_ID`, `LEAGUE_LAB_HOSTED_ADMIN_URL`,
  `LEAGUE_LAB_HOSTED_APP_PASSWORD`), run #4 failed on `pg_dump` 17 vs Neon's Postgres 18 (fixed: the runner is
  18, `bded338`), run #5 went green in 23 min with `verified: all 79 relations … on the hosted copy`. The Mac's
  08:00 launchd refresh builds only the Mac's database once `LEAGUE_LAB_MAC_WRITES_HOSTED=1` is out of its `.env`
  (Andrew removes it the same evening; if it is still there, remove it — two publishers overwrite each other's
  record). It runs at 07:37 ET; a red run leaves the previous night's copy in place (`/api/status` shows load times).
* Two leagues: **League of Scrubs** (reference; 10 teams, half PPR, K + DEF) and **Forever Unclean
  Dynasty** (12 teams, superflex, full PPR, 6-pt pass TD, yardage and long-TD bonuses, no K/DEF).
  Since **S-01a** (done 2026-09-27) league pages price every player in the selected league's own
  current scoring (`fct_player_game_league` → `mart_league_player_season` → availability, keeper
  facts, positional strength, league draft); the NFL research pages, defense vs position (and the
  Opp rank columns), the baseline formula and the projection features stay in the reference
  league's scoring (`points_current_scoring`) and say so.
* Test agents walked every page on both leagues on 2026-09-26; every finding is fixed, the
  per-league pricing last (S-01a; evidence in `docs/STATUS.md` § "S-01a").

## The tasks, in order (details and acceptance in `docs/PROJECT_PLAN.md` § Iteration 9b)

Wave A (S-01a, U-10, U-11, M-06) is delivered. **Wave B** builds the decision engine from
`docs/league-lab-next-iteration-2026-09-29.md`:

Round 1 (independent, in parallel): **B1** exact lineup service · **B5** decision record (frozen
projections, published drift) · **B6** GitHub Actions nightly — **delivered 2026-09-29** (`ba2c9c5`,
STATUS § "Wave B / PO merge and QA — round 1").
Round 2 (all consume B1): **B2** roster value and rankings · **B3** waiver engine · **B4** player
card + My Week — **delivered 2026-09-30** (STATUS § "PO merge and QA — round 2"), with the acceptance amended by Andrew's mobile review (plan § "Round 1 status and
Andrew's mobile review": answer-first cards, phone width, one projection, plain words). Then
Iteration 10 as Wave C: round 1 (U-13 mobile pass + U-16 League consolidation, U-14 plain-language
pass + U-15 model explainer, R-13 kicker and defense projections) **delivered 2026-09-30**; round 2 (**C4** T-01 trade
evaluator + T-02 simulator · **C5** R-14 cornerback matchups + R-15 defense-vs-position picture + R-11 matchup
comparison · **C6** R-10 role alerts + R-12 scenario upside + U-17 Receivers/Kickers context) **delivered
2026-09-30**. Iteration 10 is complete apart from P-01 (profiles + any league), which needs a design note first.
**Iteration 12 (Wave D) delivered 2026-10-01: projection v3.0** (starting-QB inputs at QB, teammate-out inputs
at RB/WR/TE — every other candidate group was tested through the feature harness and dropped), the 50% range,
per-tier calibration, the win probability on the decision cards, and the front-end spike with its decision note
(`docs/FRONTEND_DECISION.md`). Next: Andrew's decisions on the front end and P-01; the weather backfill and
kicker-wind re-test; the Iteration 11 operations rows.

**Iteration 13 (Wave E) delivered 2026-10-02 — from a lab to a product** (Andrew's direction: a $4–5/month
tool the fantasy population would pay for): "Our record" (Sleeper's own projections archived before kickoff
and scored against ours — the record starts the first week the nightly pulls them; `make sleeper-projections`),
rest-of-season projections on Player / Rankings / Trade Finder, the any-league design and spike
(`docs/ANY_LEAGUE.md`: stat lines stored once, scoring applied per request; `/api/my-week` for any Sleeper
league id), and four more model tests (all dropped; two v3.1 leads in STATUS). **Next: Wave F**, the customer
app on the D7 stack (FastAPI + Svelte; Streamlit stays as the research console) — first step E3's proposal:
reference scorings + `ops.projection_lines` / `ops.projection_ranges`; then Wave G (accounts, payments, hosting,
one nightly writer). Andrew checks Sleeper's commercial terms before anything is sold.

**Iteration 14 (Wave F) delivered 2026-10-02 — the customer app, phase 1**: NFL-wide model outputs (`ops.projection_lines`
/ `_ranges` per reference scoring, `ops.kd_lines` / `_ranges`), the API for any Sleeper league (`/api/leagues?username=`,
on-demand My Week with the opponent, player card, rest of season, record; Sleeper client with caches + token bucket;
Dockerfile serving `web/dist`), the web app (username → picker → My Week → player → rest of season → record). Sleeper's
API terms: free for non-commercial use, a licence for commercial use — **not asked** (Andrew, 2026-10-04: a prototype he
would love to commercialize, the odds slim; the licence question waits until it is prod-ready). **Wave G** shipped as the beta. Run it: `cd web && npm ci && npm run build`, then
`cd api && uv sync && uv run uvicorn league_lab_api.main:app --port 8581` → http://localhost:8581/.

**Iteration 15 (Wave G) delivered 2026-10-02 — the lab in the app**: the research (trends, matchups, players, receivers,
compare, game logs) and the decisions (waivers, trades, team hub, league) for any Sleeper league on demand, a design system
(`docs/DESIGN.md`: dark-first, team colors, the player card as the unit, an inline-SVG chart kit), every screen in the
web app, "About the numbers" (the model explanation + the record). Same run commands as Wave F.

**Iteration 16 (Wave H) delivered 2026-10-02 — the beta on a server**: the deploy kit (`render.yaml`, the Dockerfile,
`image.yml`, `scripts/smoke.sh`, `docs/DEPLOY.md`), the gaps (upside stash, buy low / sell high, About's "what it leans
on most", one-query rest of season, search for any league), one writer (GitHub Actions publishes the hosted copy; the
Mac's launchd builds locally only), the NFL-wide boards in the record, the hosted relation closure in
`scripts/hosted_relations.py`. Deployed 2026-10-02 (`docs/DEPLOY.md`).
* **Wave I-0 (2026-10-03, after Andrew's beta walk — plan § Iteration 17)**: My Week (house and on-demand) re-solves
  the lineup at request time from an availability overlay — ESPN's public injuries feed (15 min on game days,
  hourly otherwise) + Sleeper's daily directory — and says who moved and why; Trends / Waivers / trades / ROS exclude
  players who cannot play (`api/league_lab_api/availability.py`, `src/league_lab/injury_feed.py`;
  `LEAGUE_LAB_AVAILABILITY=off` disables it). **MyFantasyLeague** leagues work on demand with `mfl:<id>` keys
  (`src/league_lab/mfl_client.py`, `platforms.py` — MFL answered in Sleeper's shapes, so no screen changed —
  `player_ids.py`, the nflverse id table downloaded into `LEAGUE_LAB_CACHE_DIR` once a day); the Leagues screen takes
  an MFL league link and a team picker. `docs/ANY_LEAGUE.md` § "Availability" / § "MyFantasyLeague"; `docs/MFL_TERMS.md`.
* **Wave I-A (2026-10-03, Saturday small hours)**: My Week's calls say why (`cards.reason_line`, shared with the
  console; a coin flip reads "A or B — a coin flip"), short names + headshots on the phone, Trends = "Below and above
  expectation" with reasons and a stat strip, the trade calculator as its own link with the interest dial and the
  window control (`window=week|next4|ros|playoffs`), the partner finder's sanity bound (`trades.sanity`), buy low /
  sell high on Trades, the rankings' pieces + "why this number" + the market line (`analytics.mart_market_line`,
  priced per league by `api/league_lab_api/why.py`), "How to read the rankings". M1: **no star penalty** (STATUS §
  "Wave I-A" M1): the gap Andrew sees is a level gap with the market (ours ~1–3 under Sleeper's top 24) plus an
  over-projected fringe; `calibration.py` exists behind `LEAGUE_LAB_PROJECTION_CALIBRATION` (off; WR fringe only).
* **Wave I-B (2026-10-03, Saturday midday, the second review)**: one availability truth
  (`availability.roster_context` — every screen reads the same overlay-adjusted roster; one lineup total everywhere;
  the cards' `status` / `strength`), navigation by task (My Team · Waivers · Trades · Players; About in the ⋯ menu; the
  player page inside the frame; the research pane `PlayerPane.svelte` / `lib/pane.svelte.ts` from any player name
  with Compare / Evaluate add-drop / Add to trade), Waivers short (top 3 + views, the best alternative before a drop),
  the calculator's pinned verdict, Favorable / Neutral / Difficult with one rank direction and corner certainty,
  **Value to my lineup** leading Season (`/api/ros?view=lineup`), the card's default content.
* **Wave I-C (2026-10-03, Saturday afternoon, dad's league)**: scoring and rosters are dynamic. A league's rules
  are data per position (`scoring.ScoringSpec`: rates, flat bands at any threshold, TDs and kicks by distance, MFL's
  whole-unit steps, premiums; `from_sleeper` / `from_mfl`; `anyleague.league_spec(league)`; the spec travels as
  `scoring_spec` next to the flat `scoring_settings` every old reader keeps) — actual lines priced exactly
  (`price_detail`), projected lines in expectation (`expected_frame` with `scoring_ev`'s threshold curves and
  TD-distance shares; MFL specs always, Sleeper specs behind `LEAGUE_LAB_EV_PRICING`, **off** until the nightly
  prices with the same engine so the player page and My Week agree). **The scoring check**
  (`/api/league/scoring-check?league=&week=`, `scoring_audit.check`): our points against the league's own for every
  rostered player of a played week — Scrubs and the dynasty 100% to the tenth (2026 weeks 1–2; the SQL macro agrees),
  MFL 70587 155 / 156 within a point. Slots are eligibility sets (`lineup.Slot`, `WR+TE`, `TMQB` / `TMPK` / `TMDEF`)
  and MFL team units are players priced from the team's starter; the Leagues card reads the lineup and the scoring
  back in the league's own words and shows the check; double headers name both opponents. dbt: `fct_player_game`
  (and the league twins) carry `pass/rush/rec_tds_10p`. Fixtures: `api/tests/fixtures/mfl/70587/`.
* **Wave I-D (2026-10-03, Saturday late afternoon)**: the nightly on the spec — `scoring.price_projected` is the one
  entry point for projected lines, called by `projections.price` (every nightly path) and `anyleague.price_lines`
  (the request side), so `LEAGUE_LAB_EV_PRICING` moves both at once (pinned bit for bit; the harness both ways in
  METRICS § "Expected-value pricing" → "On the nightly"); the team units on rest of season, the Team Hub, the League
  screen and the unit's card (`/api/player/mfl:0656`); the League screen's double headers and `/api/record` for MFL;
  Waivers fills an empty starting slot first; the player news line (`news_feed.py`, ESPN's public fantasy news
  endpoint, headline + link out, `LEAGUE_LAB_NEWS=off`; `docs/ESPN_TERMS.md`).
* **Wave I-E (2026-10-03, Saturday evening, the casual-user review)**: the third outside review
  (`docs/reviews/2026-10-03-mfl-70587-usability-review.md`) as the specification — the trade calculator keeps
  provider-keyed assets (`mfl:0682`; `parseIds` had dropped the colon) and names what it cannot analyse; Waivers'
  bye words come from the candidate's own move; platform words on MFL leagues; **My Week is a weekly action list**
  (`actions` ≤ 3 by urgency, combined calls, `set_line`, `edit_link` "Open MFL to edit your lineup", `nothing_submitted`);
  Waivers' top three lead with this week's gain; the dial is "Effect on their starters"; the Finder leads with the
  cheaper package; the trade result is told through the starting lineup (`trade_story`: starters in / out by
  membership, the cut, their side, the window, hold / waivers; no gains from slot renumbering); the dictionary
  (`docs/WORDS.md` § "The dictionary"); the setup screen with the team picker first; contrast ≥ 5.3. PO: the verdict
  without acceptance guesses, the lineup table's rows agreeing with the call (`annotate_swaps`).
* **Wave I-F (2026-10-03/04, Saturday night, the decision-quality review)**: the fourth outside review
  (`docs/reviews/2026-10-03-decision-quality-review.md`) — a drop's cost in pieces (`waivers.drop_cost`, `choose_drops`,
  14 columns on `ops.waiver_moves` and `mart_waiver_moves`; "Drop McPherson: Carlson replaces him at K"; stashes a
  watchlist; "no claim is worth a roster spot"); the finder ranked by gain beyond the best alternative
  (`decisions.best_alternative`, `beyond_alternative`, demotion, the value concepts named, `WeekStrip`); the matchup
  evidence (`research.matchup_evidence`: history · what changed · implication · `forecast_treatment` "contextual
  only"; the matchup tiebreak dropped when the corners changed); My Week's `review` lines ("No clear upgrade"),
  "What changed" (the "News feed" since Wave I-N), the pane trimmed, the language table, the I-E leftovers; **usage tracking** (`usage.events`,
  `scripts/hosted_usage.sql` run by the sync, `POST /api/usage`, the console's Usage page — no new secret; the table
  appears on Neon at the next nightly; `GET /api/usage/summary` says `ready`).

* **N2 (2026-10-03 evening, branch `playerwire-integration`; merged 2026-10-04)**: PlayerWire's briefs lead the news line (the Mac syncs
  them every 15 minutes into Neon's own schema `playerwire` as role `playerwire_writer`; ESPN fills the rest;
  `docs/PLAYERWIRE.md`). Waits on Andrew's yes to HOSTING.md § 5 as "one writer per schema", then five set-up steps. Merged over
  IF-4: ESPN's items keep IF-4's order and `about`; a PlayerWire brief is `about: "player"` (his by id); every item has `kind`.

* **Wave I-G (2026-10-04, overnight, six Opus devs; STATUS § "Wave I-G" PO section first)**: the record's `pricing`
  column and the request side following the record's label per week (M4; **the flip ships**: `LEAGUE_LAB_EV_PRICING:
  "1"` on the nightly's `project` step only — never on Render; the first nightly after the push prices weeks 5–18 at
  their odds, week 4 stays flat); v3.1 measured and off (M5: the cold-start prior is the keep worth finishing — on
  the stat line, v3.2); team units' season value, the Finder on season value above replacement, unknown is not zero
  (IG-1); the event store `events.events` written by the overlay / the news line / PlayerWire's briefs and read by
  "What changed" (the News feed) and the matchup evidence (IG-2; `scripts/hosted_events.sql` by the sync; `LEAGUE_LAB_EVENTS=off`,
  `LEAGUE_LAB_EVENTS_ESPN_NEWS=off`); the validation harness — `ops.lineup_record` frozen at kickoff,
  `mart_decision_record` / `mart_decision_calls`, `league-lab validate`, `/api/record` `decisions`, About's block
  (V-1; the first numbers are small-sample and unflattering: −1.2 a team a week on the rebuilt weeks 1–2 of Scrubs;
  the real record starts at week 5's kickoff); the stash writer's drop rule, MFL's freshness line, the waiver
  deadline, the MFL grade's qualification, usage retention 180 days (IG-3).

* **Wave I-H (2026-10-04, Sunday; five Opus devs; STATUS § "Wave I-H" PO section first)**: v3.2 (the cold-start
  prior on the stat line, on by default — `LEAGUE_LAB_COLD_START=0` turns it off; the first nightly builds
  `ops.calibration_oof`, ~3 min once), the decision record personal / live / MFL (`LEAGUE_LAB_RECORD_MFL` on the
  nightly), error states (`ErrorCard`), the stale state **operator-only** (Andrew: never tell people the data is
  stale), events retention, the nightly's failure summary, the I-G opens, the week's win probability. **Sunday
  afternoons turn ~45 API tests and 2 root tests red on any branch** (the on-demand path locks players as games kick
  off): compare against `main` at the same hour before believing a failure — **fixed in Wave I-I** (the pinned
  clock, `league_lab.clock.now()` + `LEAGUE_LAB_NOW`; the suites are green any day).

  **The nightly's trigger (2026-10-04)**: GitHub's `schedule` fired 3.5–6 h late every day since 2026-09-30 —
  `ops/nightly-trigger/` (a Cloudflare Worker, 07:37 ET + re-checks) replaces it as the clock; needs Andrew's
  fine-grained token in the Worker's secret (HOSTING § 5 "The trigger"). Until it exists, "Run workflow" by hand.

* **Wave I-L (2026-10-05, Monday 12:20–15:10 ET; five Opus devs; STATUS § "Wave I-L" PO section first)**: the
  deferred list. **Data**: `analytics.mart_player_ngs_week` (NGS weekly; the nightly's `dbt build` makes it, the sync
  publishes it — until then Stats says "Next Gen Stats arrive with the nightly update") and `src/league_lab/roles.py`
  behind the drawer's Role block (reads `player_team_history`, now windowed in `sync_to_hosted.sh`). **MFL**:
  transactions, live points, waiver order / blind bids — built on a synthetic fixture; **the transactions verified
  live 2026-10-05** on `mfl:70587` and `mfl:21861` (STATUS § "PO — MFL's transactions verified live"): MFL files a move
  made once a week's games have begun under the NEXT week, so `MFLLeagues.transactions` reads the next week's file
  with MFL's current week; a moved player on no roster is named from a directory read after the moves
  (`decisions.moved_directory`). No trade seen live yet (neither league has one).
  **Model**: `MODEL_VERSION` **v3.3** (the WR new-team scale, `LEAGUE_LAB_NEW_TEAM_SCALE=0` restores v3.2 on the
  `project` step) — the first nightly re-runs `backtest-v2` and the calibration once; `league-lab grade-odds` is a soft
  nightly step writing `analytics.odds_grades` (`/api/status` `odds_grades`; the Record page's table). **Memory**: the
  Sleeper directory trimmed at the read (`DIRECTORY_FIELDS` in `sleeper_client.py` — a new screen that needs a field
  adds it there; `/api/status` `memory.directory`), `LEAGUE_LAB_FINDER_LAZY_THEIRS` (default on). **Accounts phase
  2**: `accounts.connections`, `/watchlist`, `LEAGUE_LAB_PROVIDER_VERIFIED=espn,yahoo` on Render flips a provider to
  supported with no deploy; `ll_session`'s path is `/api`. Run `scripts/measure_memory.py` before touching the
  directory or the Finder again.

* **Wave I-M (2026-10-05/06, Monday night 22:45 – 02:00 ET; five Opus devs, an independent security review, a fix
  round; STATUS § "Wave I-M" PO section first)**: **the site is public** — `render.yaml` `LEAGUE_LAB_GATE: open`
  (`password` brings the beta password back; `auth.py`), a front door, **reference leagues** `ref:ppr` / `ref:half` /
  `ref:std` (`api/league_lab_api/refleague.py`: research routes with no team and no ownership; decision routes answer
  `needs_league`), the limiter (`ratelimit.py`: buckets `read` / `research` / `heavy` / `write`, the client from
  `CF-Connecting-IP` on Render, IPv6 by /64 and /48, an all-clients ceiling, 4 CPU slots — **a new route goes in the
  right bucket in `bucket_for`**; `ratelimit.client_group` is the one name of a visitor; never key on `request.client`:
  uvicorn's `--forwarded-allow-ips='*'` makes it client-written), the Guard (`security.py`: cross-site writes, body
  sizes, the CSP — a new outside host or inline script must pass it), `docs/SECURITY_PUBLIC.md` (what was checked and
  what is left). **Stats**: 101 columns in 12 groups (`stats.py` `CATALOGUE`; `mart_player_game_advanced`, PFR weekly),
  "Key stats" / "Full table" (`web/src/components/stats/`), `GET /api/players.csv`. **Accounts by passkey**
  (`passkeys.py`, `accounts.passkeys`; `LEAGUE_LAB_ACCOUNTS=auto` turns them on when the nightly has applied
  `scripts/hosted_accounts.sql` — for everyone; ceilings of 30 new accounts an hour / 200 a day; `docs/ACCOUNTS.md`
  § Passkeys). **DFS** (`src/league_lab/dfs.py`, `api/league_lab_api/dfs.py`, `/dfs`, `docs/DFS.md`): the user's
  DraftKings / FanDuel salary file → value, undervalued / overpriced, exact lineups; **nothing is fetched from either
  site** (their terms; the PO's tools cannot open them) and the parsers are **unverified against a real file**; the
  two POSTs run off the event loop one at a time (a semaphore) with a 5-second budget — keep it that way: the server
  is one process. **The sandbox's suites**: 92 API and 4 root tests fail on any tree in this session's database (2026
  through week 4, the clock pinned to 2026-10-03; five of them read the real date somewhere — unfound): compare
  failures by name against a run of `main` on the same database, never by count. **After the push the PO verifies live**
  (STATUS PO section): `/api/ratelimit` first.


* **Wave I-N (2026-10-06, Tuesday 09:20 – 13:00 ET; six Opus devs, an independent security review, a fix round;
  STATUS § "Wave I-N" PO section first)**: **`/` is the home page** when no league is remembered (`routes/Home.svelte`;
  `/home` always; a manager's `/` is still My Week) and `/leagues` is only "open your league". **The blog** is
  markdown files in `blog/` (front matter; `blog/README.md`; a push publishes; `api/league_lab_api/blog.py`,
  `lib/md.ts` `mdDoc` — escape-first, extend it there and nowhere else; the shell's per-path meta tags are built in
  `main.py`'s SPA fallback; `docs/BLOG.md`). **Reference keys are a closed family of 160**
  (`platforms.parse_reference` is the one parser; `refleague.py`; never parse a key elsewhere — `is_reference` /
  `label`), the bar's scoring picker (`components/scoring/`), a value without a league (rv1.0), the free trade
  calculator (`freetrade.py`); **"No league" is never shown**. **The matchup board** (`matchup_board.py`:
  `matchup_context` is scoring-free and never raises — the home and DFS read it; the corner is NOT in the
  projection, the defense IS: a test pins the words to the feature list). **DFS** opens with no file (context chips
  with "in the projection" / "not", `dfs.SIGNAL_INPUTS`), **published slates** are files in `dfs/slates/` (none
  ships; nothing fetches a salary), stacks and exposure. **My Week**: an open spot is its own roster alert
  (`myweek.open_spots`; pairing only through legal replacements), the words are "Roster alert" and "News feed";
  **every keyed `{#each}` carries an index-suffixed key and every screen sits in a `<svelte:boundary>`** (keep both
  when adding a list or a screen: a duplicate key blanked Team on the live site). **League outlook**
  (`outlook.py`: chunked simulation, one at a time, canonical league key before any cache). `render.yaml` is
  **`plan: standard`** (2 GB). `api/Dockerfile` copies `blog/` and `dfs/slates/` (a new top-level folder the server
  reads needs a `COPY` **and** a `.dockerignore` line). Known and left: the horizon view reads the database's
  `now()` (the suites' five Monday-night failures; do not "fix" one read path alone — the API and the console must
  share one clock).
* **Yahoo is "coming soon" again (2026-10-05 evening; STATUS § "PO — Yahoo refuses the app")**: Yahoo has not approved
  the app's Fantasy access, so the sign-in works and every data call is refused (401 / 403
  `additional_authorization_required`); a friend was told "expired, connect again" four times, then "league is private
  or does not exist" for a public league. `render.yaml` carries **`LEAGUE_LAB_YAHOO_ACCESS: pending`** (remove it once
  `/api/yahoo/status?probe=1` answers ok — HOSTING § Yahoo, "The probe"); `yahoo_client` raises `YahooAccessPending`
  for that refusal (and holds "coming soon" for an hour by itself if Yahoo ever takes the access away), logs every
  non-200 Yahoo answer (`yahoo refused: HTTP … problem=… resource=…`, never a token) and no longer calls a refusal on a
  resource that names no league "that league is private". **Yahoo's actual answer has not been seen yet** (the old
  code threw it away): the first probe after the deploy shows it. Andrew was given the Client ID and the form's text
  for `sports.yahoo.com/developer/access/` at 17:20 ET (he had never been asked to send it); Yahoo's attribution line
  is on the Yahoo league screens now. **Live since 21:14 ET (`8446cb7`)**, MFL's moves and the pending screen verified
  (STATUS, both PO sections); `image` #19 (`93deea5`) had failed at GitHub (no runner), so nothing deployed between.

* **Wave I-K (2026-10-05, Monday 08:40–12:30 ET; four Opus devs; STATUS § "Wave I-K" PO section first)**: **ESPN**
  leagues on demand (`espn:<id>`, public read-only, unofficial; private via the manager's cookies behind
  `LEAGUE_LAB_ESPN_PRIVATE=off`; kill switch `LEAGUE_LAB_ESPN_LEAGUES=off`), **Yahoo** leagues through the official
  OAuth API (`yahoo:<game>.l.<id>`; needs `LEAGUE_LAB_YAHOO_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` on Render after
  Andrew registers the app — HOSTING § Yahoo; until then "coming soon"), the four-provider seam (`platforms.provider_of`,
  `Router(sleeper, mfl, espn, yahoo)`, `capabilities()` `unverified` for both until a live league is checked), the
  setup flow's four platforms, **accounts phase 1** (`scripts/hosted_accounts.sql` applied by the nightly's sync; sign-in
  by an emailed link via Resend — `LEAGUE_LAB_RESEND_API_KEY` turns it on; HOSTING § Accounts has the DNS records).
  **Nothing ESPN / Yahoo / accounts is verified live yet** — the PO's checklist is in the STATUS PO section; after it
  passes, flip `capabilities` to `supported`, the words, PROVIDERS, and the pins in `test_ik3` / `test_ii5`. Memory:
  ESPN answers are trimmed before caching; Yahoo caches are per manager; both clients go through `league_lab.memo`'s
  rules (`docs/DEPLOY.md` § Memory) — re-run `scripts/measure_memory.py` after the first live leagues.

* **Wave I-J (2026-10-04/05, Sunday night 22:30–01:50 ET; two Opus devs; STATUS § "Wave I-J" PO section first)**: the memory
  diet after Sunday's out-of-memory restart (Starter, 512 MB; four leagues → 400 MB before) — strings interned at the
  fetch, one Board per week shared, one byte budget over every per-league cache (`src/league_lab/memo.py`,
  `LEAGUE_LAB_CACHE_MB` default 64, LRU), `malloc_trim`, `MALLOC_ARENA_MAX=2` in the image, `/api/status` `memory`,
  `scripts/measure_memory.py` (**run it before and after any change that touches caches or frames**: four leagues
  404 → 272 MB, the server alone ~240; per on-demand league +97 → +29; a plateau over five leagues cycled twice).
  Also II-6's presentation leftovers. **Open**: Render's auto-deploy trigger — `checksPass` has produced no deploy
  since the domain's Blueprint sync; the fix is `autoDeployTrigger: commit` (Andrew's one word in `render.yaml`, or
  Render → Settings → Auto-Deploy → "On Commit"); until then deploy by hand after every push. Sleeper's player
  directory is outside the budget (`outside_mb.sleeper`) — the next lever if a Sunday still climbs.

* **Wave I-I (2026-10-04/05, Sunday evening; seven Opus devs + an integration engineer; STATUS § "Wave I-I" PO
  section first)**: the fifth review delivered in its order — the calculation audit (Team's strength by slot on one
  metric and population, legal replacement chains, full names, one frame for the trade story), credible trades (the
  covered frame, both teams' alternatives, the K / DEF guardrail, "No compelling trade found", the trade card; the Folk
  package Implausible), the drawer everywhere, the Stats Explorer + `docs/DATA_INVENTORY.md`, the copy standard
  (`scripts/copy_standard.py --check` must stay clean), Season's three views, the news feed, one setup flow +
  `platforms.capabilities()` + `docs/PROVIDERS.md` (the ESPN verdict) + `docs/ACCOUNTS.md` (design only). **The
  pinned clock is in**: `league_lab.clock.now()`, `LEAGUE_LAB_NOW`; both suites pin `2026-10-03T16:00:00Z` in their
  conftests (`PINNED_NOW`; `real_clock` fixture for a test that needs the wall clock) — the Sunday-afternoon red is
  over; a new wall-clock read on the request path goes through `clock.now()`. **Google Analytics 4** is wired
  (`web/src/lib/analytics.ts`, `G-HJWGHZ79BG` in `brand.ts`, `LEAGUE_LAB_GA=off` to strip it; no PII — ids only);
  Andrew's three GA settings are in the STATUS PO section.

  **Render has not auto-deployed a push since the domain's Blueprint sync** (`c47c5ea` and `786c2f5`: CI green, no
  deploy event at all; `786c2f5` deployed by the PO by hand 2026-10-04 20:31 ET) — after every push, check Render's
  Events for a "Deploy started" and otherwise **Manual Deploy → Deploy latest commit** (DEPLOY § troubleshooting).
  **The server ran out of memory once** (2026-10-04 15:25 ET, Starter's 512 MB, recovered on its own): Andrew's call
  between Standard ($25) and the memory diet (DEPLOY § Memory).

  **Next**: after the push, deploy (by hand if Render does not) and verify live (`/api/health` `version`, Team's
  bars, the Finder's verdict, the drawer, GA's realtime view once Andrew opens the site); the presentation list in STATUS (Waivers' card names beside the drawer,
  the Finder's doubled headline, the drawer's Back and the URL, `app.spec.ts`); accounts (ACCOUNTS.md) when Andrew
  says so; the two planned NGS columns as marts; the Finder's cold cost if Render's first answer matters; Wave J
  (Stripe, ESPN beyond public read) parked until the prototype is prod-ready (Andrew, 2026-10-04; no licence request
  made; ESPN's terms bear on the news line and injury overlay — a decision before anything is charged for).

Do one task per handoff. Update `docs/STATUS.md` and `CHANGELOG.md` in the same change, add the
dbt/unit tests named in the acceptance column, and cite the task ID in the commit. A release a
league-mate would notice also gets a plain-words entry in `app/whats_new.md` (Home's "What's new"), and
page copy follows `docs/WORDS.md`.

## How to work here

```bash
make sync                                   # uv, from uv.lock
make pytest && make lint                    # no database needed
make build                                  # dbt seed + run + test (migrate first)
make project                                # projection v2 for this season, then its marts
make backtest-v2                            # only when the model or its features change (~12 min)
make app                                    # http://127.0.0.1:8501
make sync-hosted                            # refuses off Actions (the one writer) unless LEAGUE_LAB_MAC_WRITES_HOSTED=1 — HOSTING.md § launchd
```

Headless page check that catches most regressions before a browser does:

```python
# every page on both leagues; exceptions=0 everywhere or you are not done
import sys, pathlib; sys.path.insert(0, "app")
from streamlit.testing.v1 import AppTest
for league, team in (("1321941740235550720", "1"), ("1389709692405551104", "2")):
    for page in ["Home.py", *sorted(str(p.relative_to("app")) for p in pathlib.Path("app/pages").glob("*.py"))]:
        at = AppTest.from_file(f"app/{page}", default_timeout=180)
        at.query_params["league"], at.query_params["team"] = league, team
        at.run(); assert not at.exception, (page, league, [e.value for e in at.exception])
```

## Things that will bite you (each cost real time once)

* **Two leagues share seasons.** Never key anything on `season` alone; `dim_league_season` has
  `league_id` (one per league-season), `chain_id` (the newest season's id, for "this league's
  seasons") and `is_reference_league`. Pages get the league from `perspective()` in the sidebar
  and seasons from `season_picker(league_id)`; positions from `league_slots(league_id)` — the
  dynasty league has no K/DEF, hard-coded `["QB","RB","WR","TE","K"]` breaks it.
* **Streamlit drops `?league=&team=` on page navigation.** `perspective()` keeps the choice in
  `st.session_state` (URL > session > reference league). Any new page must call it.
* **`require_relations("x")` must name only relations the page reads as `analytics.x`.** The
  hosted sync derives what to publish from those references; `tests/test_app_guards.py` enforces it.
* **Missing cells**: `show()` passes `placeholder=""`; do not print NaN/None yourself.
* **Two scoring scales.** A league page reads points from `mart_league_player_season` /
  `mart_player_availability` / `fct_player_game_league` (the league's own scoring) — never
  `points_current_scoring`. The NFL-wide marts (`fct_player_game`, `mart_player_season`,
  `mart_player_recent_form`, `mart_player_expected_*`) stay reference-scored because the projection
  features read them; do not re-key them. `assert_reference_league_matches_nfl_marts` fails if the
  two sets of arithmetic drift apart. Do not name `analytics.fct_player_game_league` in page code
  unless a page reads it: the hosted sync publishes every relation the code names (≈52 MB more; `mart_league_player_season` is ≈8 MB).
* **Seeds are generated.** `scoring_stat_map.csv` comes from `league_lab.scoring.write_seed()`;
  `tests/test_scoring.py` fails if they diverge. Seeds always full-refresh (`+full_refresh: true`).
  Pricing anywhere in SQL goes through the `league_points(scoring_jsonb, alias, include_bonuses)`
  macro, with `zero_stat_columns(have)` to fill columns a relation lacks.
* **Projection v2 rules** (`src/league_lab/projections.py`): features must be available
  *in-season* (the routes proxy is not — the participation file arrives after the postseason);
  a quantile model on raw points collapses at P10 because a fifth of played weeks score 0 — the
  interval is a quantile of the *out-of-fold* miss around the priced line, conformally widened;
  hyperparameters are constants and a change is a new `MODEL_VERSION`; anything new must beat the
  baseline on `make backtest-v2` before the page prefers it.
* **Rules that never bend** (AGENTS.md): join players by `player_id_map`, never by name;
  denominators from `fct_team_game`, never summed players; unknown is NULL, never 0; raw payloads
  are kept; nothing keyed to Andrew's username; Andrew writes the newsletter — data packs only.
* **Hosted copy budget**: Neon free tier is 0.5 GB and the sync cannot hold two copies; today
  ≈ 300 MB. A new mart the pages read must be small or slimmed.
* **On the Mac**: Postgres 17 via Homebrew; `.env` holds the Neon owner URL (never commit it);
  `make sync-hosted` from the repo root; the launchd job logs to `logs/`.

## What Andrew wants from a handoff (AGENTS.md § handoff format)

Task ID, plan sections touched, exact files changed, commands run, validation evidence (test
output, row counts, reconciliation numbers, the headless page check, a browser walk on both
leagues), data partitions touched, unresolved limitations, next task. Honest, no varnish: if a
number is worse, say so and show it.

* **Wave I-P (2026-10-06/07, overnight; five Opus devs, an independent review, fix rounds; STATUS § "Wave I-P" PO
  section first)**: **delivery changed for good** — the PO never runs git on Andrew's Mac (git needs to delete its
  lock files and deleting is off there: Wave I-O's delivery left the repository locked) and never asks for delete
  permission (declined, 2026-10-06: the folder is not fully backed up). Write **one bundle file under ~13 MB** into
  `league-lab/.git-bundles/` and give Andrew one line (`cd ~/PycharmProjects/league-lab && git fetch
  .git-bundles/<name>.bundle +main:refs/bundles/x && git merge --ff-only refs/bundles/x && git push`); read whether
  he pushed from `/api/health` and GitHub Actions. **The nightly on a fresh database**: every table in
  `scripts/nightly.sh` `STATE_TABLES` must be created by `league-lab db migrate` (`src/league_lab/db.py`) —
  `restore_state` counts each right after the migrate and the Actions database is new every night; Wave I-O missed
  it for `ops.context_record` / `ops.context_grade`. Before delivery run init + migrate on a scratch database and
  count every state table (the PO's `fresh_db_check.sh`). **Model**: v3.4 = v3.3 + pt1.0
  (`calibration.pass_td_lines`, switch `LEAGUE_LAB_QB_PASS_TD`); `mart_projection_drift` sets a week against the
  backtest of the model that made it and versions compare by number (`version_key`) — never compare a season's
  weeks with another model's backtest again (the home's "weak spot" was that). **Who starts**: nflverse's schedule
  keeps stale projected starters (SEA 2026: Lock listed, Darnold playing); two correcting rules failed their
  accuracy rules and are off (dbt vars `pn_starter_from_play`, `pn_starter_stale_rule`); `api/league_lab_api/starters.py`
  `unclear(season, week)` flags both quarterbacks and Rankings / "Who should I start?" give them no tier and no
  call — a label, not a correction. **Rankings**: `/rankings` + `/api/rankings` + `/api/rankings/start`
  (`rankings_api.py`, the `rankings` memo region, keyed by scoring **and the tone's source**); a tier runs while its
  first player outscores the next in fewer than 55 in 100 (`decisions.COIN_FLIP`); no tiers on the season view
  until the season ranges are graded. **The grades** (`context_record.summary()` keys `corner`, `worth`, `trend`,
  `role`; METRICS cx1.1): Trends' gap is what happened and the projection already counts it, a role change is
  mostly priced — do not write "buy low", "sell high", "due" or "running hot" anywhere again; a past week's tag in
  `mart_league_player_season` / `mart_player_trend_tags` is look-ahead (rebuild as-of: `context_record.asof_trend`).
  **The player card**: `components/card/**`, `GET /api/player/{gsis}/ratings` (percentiles on the Stats frame's
  cached season aggregate; `read`; no `league` parameter) and `/projections` (`read`), `unitcard.py` (a defense's
  card), one decimal the API's way on the card (`lib/card.ts` `pts1`). **Provider reads**:
  `src/league_lab/provider_trouble.py` — a cache on a request path builds inside `watch()` and keeps nothing built
  during a refused, failed or stale read (`kept()` serves the last good value, else `SleeperBusy` → 503 "busy"); a
  reader must not swallow a refusal into a default on an on-demand path (SECURITY_PUBLIC § 15 lists every site).
  **Shells**: `player_share.py` (the player page's card from the board the process already holds; never a query),
  any page with `?league=` is `noindex`.
* **Wave I-O (2026-10-06, Tuesday 18:25 – 21:30 ET; four Opus devs, an independent security review, a fix round;
  STATUS § "Wave I-O" PO section first)**: **the context record** — `ops.context_record` / `ops.context_grade`,
  written by `league-lab context-record` in the nightly (frozen before the week's first kickoff, graded after),
  read by `api/league_lab_api/context_record.py` `summary()`; **a past week's corner rank in `mart_cb_matchups` is
  look-ahead** (the season to date): grade only through `context_record.cb_rank_asof`. **The corner call has no
  measurable effect** (2,190 receiver-games): `matchup_board.combine_tone` returns the defense's tone, `cb["tone"]`
  is always None, the corner is information in neutral styling — do not colour, sort "best matchup" or build a list
  on it again without an out-of-sample grade in the record; "Worth a look" is off the DFS screen (`dfs.worth`
  stays for the record). **League**: `outlook_store.py` + `scripts/hosted_outlook.sql` (`outlook.snapshots`: one
  ceiling for every non-house league, a size guard, replaced until kickoff), movement only from a stored row, the
  Share link `/league?league=<key>` with a guest view (Sleeper / MFL only; an ESPN or Yahoo league is never shared,
  stored or carded), the shell's League card from cache or the store only, `?part=power` first, title odds; **a
  refused provider read inside a build is raised, never cached**. **The blog editor**: `blog_store.py` +
  `scripts/hosted_blog.sql`, editors = account ids in `LEAGUE_LAB_EDITORS` (Render's dashboard, `sync: false`;
  unset → the editor's routes are 404), every write same-site + `write` bucket + the per-post floor; rendering stays
  escape-first through `lib/md.ts` `mdDoc`; `docs/BLOG.md`. **Per-client provider share**:
  `src/league_lab/provider_share.py` (a context variable set by the limiter's middleware — **a new thread pool on a
  request path must carry the context** (`ctx.copy().run`): `test_io4` lists every pool and fails on a new one).
  **Shared**: `src/league_lab/role_trend.py` (DFS's chips and Stats' "Role change" group). **Hosted SQL**: a new
  schema the API writes gets its own idempotent `scripts/hosted_<name>.sql` and a block in `sync_to_hosted.sh`; the
  API must answer without it (the deploy lands before the nightly).
