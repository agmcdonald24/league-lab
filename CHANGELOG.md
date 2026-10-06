# Changelog

Newest first. Home's "What's new" is `app/whats_new.md`, the same releases in plain words (docs/WORDS.md).

## 2026-10-06 — Wave I-O

- **IO-1 — the context, graded; the record kept; weather on DFS.** The cornerback call and DFS's "Worth a look" were
  rebuilt for 2025 and 2026 weeks 1–4 from what was known before each game (the corner's rank in
  `mart_cb_matchups` read the whole season — look-ahead; `context_record.cb_rank_asof` rebuilds it, equal to the mart at
  season end) and graded against the projection (Half PPR, game-resampled intervals): **no measurable effect** for a
  likely shutdown corner (−0.39, −1.39 to +0.72, 99 games) or an easy one (−0.02, −1.11 to +1.22, 79), and the list was
  not distinguishable from chance (37 games, +0.72, −1.10 to +2.72). So the corner no longer counts toward "Worth a
  look" (the list is empty and says why), its chip carries its grade, and the card prints the record's sentence.
  `league-lab context-record` keeps `ops.context_record` (frozen before each first kickoff; played weeks rebuilt once,
  labelled) and `ops.context_grade`; `GET /api/context/record`; `analytics.mart_game_weather` puts the forecast
  on DFS's chips (not in the projection). docs/METRICS.md § "The context record" (cx1.0), docs/handbacks/IO-1.md.

## 2026-10-06 — Wave I-N

- **PO — the wave merged, reviewed and hardened.** Six branches (IN-1 … IN-6) on `integ/IN`, the full suites run by
  the PO on the merged tree (API 1,021 passed, root 1,537 passed; no failure that `main` does not have, by name), an
  independent security review (nothing Critical or High; two Mediums — the DFS slate listing rebuilt every slate on
  every call past four files, a cold League outlook grew to ~450 MB for a very large league — and five Lows, all
  fixed in a second round by the same devs). The PO's joins: `lib/api.ts` rebuilt block by block (the home reads
  IN-3's real board types), a **Home** tab while browsing, the invitation card's scoring words; `api/Dockerfile` +
  `.dockerignore` copy `blog/` and `dfs/slates/`; **`render.yaml` `plan: standard`** (2 GB, 1 CPU, $25 a month —
  Andrew's call). IN-5's pinned-clock mechanism for the horizon view was taken back out (it split the API's week
  from the console's in the suites; `db.py` and the view are exactly `967b2d9`'s). docs/STATUS.md § "Wave I-N".
- **IN-3 — matchups for everyone.** `/matchups` lays out every player at a position this week, player by player (WR by
  default, TE / RB / QB): his game, his projection and range in the chosen scoring, the defense against his position,
  for a wide receiver the cornerback likely across from him (rank, certainty, shutdown corner, his history against
  him), and one matchup tone for the two; search by name, filter by game and tone, sort by projection, matchup or
  corner, paged; a row opens the matchup evidence. With a league and a team: **My players · Everyone** (who has him).
  The screen says once what the projection counts (the defense: yes; the corner: no, ungraded). New
  `matchup_board.matchup_context` (read by DFS and the home) and `GET /api/matchups/board` (`research` bucket);
  docs/INTERFACES.md § IN-3, METRICS § "Matchups for everyone", WORDS.
- **IN-2 — the lab without a league: scoring choices, a value for every player, the trade calculator.** The reference
  key is a closed family of 160 (`ref:<ppr|half|std|espn|yahoo>[.sf][.tep][.p6][.t8|.t10|.t14]`, one parser:
  `platforms.parse_reference`); the bar's scoring picker (scoring with its rules, superflex, TE premium, 6-pt pass TD,
  8–14 teams; remembered on the device, in the URL); "No league" is gone from every surface, the API's `league_name`
  included. Every player has a value without a league — season points above the replacement level of a typical league
  of that shape (docs/METRICS.md § "Value without a league") — on the pane and the player page, with no ownership line
  and one foot line. Browsing, the tabs are Players · Trades · DFS and Trades is the calculator:
  `GET /api/trade-calc/free` (two sides by search, the gap in words with its 80% range, how much of it is one player,
  the roster-spot effect stated). The league calculator's path is unchanged.
- **IN-1 — a home page, the setup screen on a desktop, the blog.** `/home` (and `/` when no league is remembered on
  the device): the name, one sentence, "Open your league" / "Browse players" and this week's top projections above the
  fold at 375 and 1300; below, matchups to target (IN-3's board, hidden without it), how the projections have done
  (About's grades with the bad ones first, the record's line), the newest posts, the tools — every module on Half PPR,
  each hidden when its call fails. `/leagues` is only "open your league" now: the results sit beside the form from
  900 px and come into view (and take focus) after "Find my leagues". **The blog**: posts are `blog/<date>-<slug>.md`
  (front matter; `draft: true`; pictures in `blog/img/`), `GET /api/blog`, `/api/blog/{slug}`, `/blog/rss.xml`,
  `/blog/img/{name}`, `/sitemap.xml` (`api/league_lab_api/blog.py`), `/blog` and `/blog/<slug>` (copy link, a readable
  measure, tables that scroll by themselves), `lib/md.ts` `mdDoc` (headings, lists, quotes, tables, code, our pictures —
  escaped first). Link previews per path in the HTML shell (`og:*`, `twitter:card`, canonical; `web/public/og.png`),
  robots points at the sitemap. The launch post "How to read this site's numbers"; `blog/README.md` for writing one.
  `docs/BLOG.md`, docs/STATUS.md § "Wave I-N" → IN-1.
- **IN-4 — DFS without the homework.** `/dfs` opens on the week's board with the context the projection does not hold
  (the matchup from IN-3's `matchup_context`, the role trend, the betting line; each labelled "In the projection" / "Not
  in the projection" from the model's own input list) and "Worth a look" per position (context, no backtest, said so);
  published slates (`dfs/slates/`, `GET /api/dfs/slates`, `GET /api/dfs/slate/{id}`) open on their values with no
  upload; lineups take stacks (QB + 1 or 2 pass catchers, a bring-back, no defense against the QB) and a maximum
  exposure, and accept a published `slate_id`. No real salary file ships. `tests/test_in4_dfs.py`, `api/tests/test_in4.py`,
  `web/e2e/in4`.
<!-- ---- IN-5 -->
- **IN-5 — My Week says what it means, and no screen can go blank.** A starting spot nobody on the roster can fill is
  its own roster alert ("Your quarterback spot is open: Mahomes and Young are on a bye. Add a quarterback before Sun
  1:00 PM ET." + "Find a quarterback on Waivers ›"); an incoming player is paired only with one he can legally replace
  (his slot or the slot chain) — never a receiver "in place of" a quarterback (`myweek.open_spots`, `fits`,
  `open_deadline`, `more_words`). "Change needed" → **Roster alert**, "What changed" → **News feed**. Every keyed
  `{#each}` on API data takes a key that cannot collide (42 lists in 19 files); two `<svelte:boundary>` blocks in
  `App.svelte` show `ErrorCard` ("This screen hit a problem" + Reload, an `exception` event with the screen's name) on
  a render error; no "nan" / "None" id on the way out (`decisions._sid` on the alternative and the transactions,
  "None" too). The five tests that turned red at week 4's last kickoff: the view `mart_league_roster_horizon` decides
  "this week" by the database's `now()` while the suites pin week 4 — diagnosed, not fixed (a clean fix needs every
  read path, API, console and root package, on one clock). `api/tests/test_in5.py` (Andrew's morning from the
  database's week-5 rows), `web/e2e/in5`, docs/STATUS.md § "Wave I-N" → IN-5.
<!-- ---- end IN-5 -->
- **IN-6 — the League screen's power rankings and the rest of the season** (`GET /api/league/outlook`, `outlook.py`,
  `components/league/Outlook.svelte`; METRICS § "Power rankings and the season outlook", ol1.0): every team ranked by
  its best lineup's expected points per week over the rest of the season (record, points for / against, the
  record-vs-points gap in words and the schedule left beside it; no arrows: last week's board is not kept), and 10,000
  simulated seasons of the weeks left on the week's odds' own pieces — projected record with its middle 80%, playoff
  odds (wins, then points for), top seed, a bye where the bracket has byes; clinched / out only when proven; no title
  odds; MyFantasyLeague without playoff odds (no playoff team count). Replayed on 2024–25 from week 5: Brier 0.179
  against 0.245 flat. The `heavy` bucket; `memo` region `outlook`.

## 2026-10-06 — hotfix: the Team screen with two open lineup spots

- **PO — Team was blank for a roster with two open starting spots** (Andrew's, week 5: QB and TE both open, Mahomes,
  Young and Kelce on a bye). The API sent the text `"nan"` as the Sleeper id of an open spot (a frame turns `None` into
  NaN, `str()` made it a word), the screen keys its roster rows by that id, and two equal keys stop Svelte's list
  (`each_key_duplicate`): the whole screen stayed on its loading blocks. `decisions._sid` (an open spot has no id:
  `null`), the roster list's key carries the row's position, and My Week no longer says "Start Kelce out of your
  lineup" for a spot nobody on the bench can fill ("Take Kelce out of your lineup."; the full open-spot action is
  Wave I-N's). `api/tests/test_in0.py`. Found on live 2026-10-06 09:20 ET, minutes after Wave I-M's deploy; the bug is
  older than the wave (latent since the keyed list, first week with two open spots).

## 2026-10-06 — Wave I-M

- **PO — the wave merged, reviewed and hardened; the site is public from this deploy.** Five branches (IM-1 … IM-5)
  on `integ/IM`; an independent security review of the merged tree found two Highs in DFS (a quadratic salary-file
  parser and an unbounded lineup solve, both on the event loop) and four Mediums in the public hardening (a
  case-sensitive `view=` check, research priced as a cheap read, IPv6 rotation, provider caches that never evicted) —
  all fixed in a second round by the same devs and re-checked by the PO with the reviewer's own scripts.
  `render.yaml`: **`LEAGUE_LAB_GATE: open`** (`password` brings the beta password back). `sync_to_hosted.sh` windows
  `mart_player_game_advanced`. One name for a visitor (`ratelimit.client_group`: the limiter's source, IPv6 by /64) —
  the accounts' limits use it. `/dfs` with no league opens on the reference league. Accounts turn on by themselves
  (passkeys) at the first nightly after the push. Checks: API 824 passed / 92 failed (all on the known data-state
  list), root 1,462 / 4, e2e 431 (`docs/STATUS.md` § "Wave I-M" PO section).

- **IM-1 — the Stats tables' data: more metrics, every one honest.** Andrew's two empty WR / TE columns (separation, YAC
  over expected) fill once the nightly builds `mart_player_ngs_week`: on the clone all 40 of the top 40 receivers by
  targets have both, and every receiver without one had no week with 5+ targets (NGS's rule). 50 new Stats columns (51 →
  101): EPA (total, per target / carry / dropback), success rates, first downs, WOPR, RACR, deep targets and deep-target
  share, looks inside the 10, touchdown rates, yards per reception / touch, AY/A, TD / INT / sack rates, scramble yards,
  the QB's rushing share of his points, expected points and points over expected, seven more Next Gen Stats fields, and
  Pro Football Reference's weekly drops, broken tackles, yards before / after contact, bad throws and pressures — new
  `analytics.mart_player_game_advanced` (+ `int_player_game_efficiency`), PFR joined by id through `player_id_map`
  (unmapped rows counted). Every column has a `group`; presets lead with 14 columns and carry a `full` list;
  `GET /api/players.csv`. docs/METRICS.md § "More columns" (adv1.0), DATA_INVENTORY, WORDS; docs/STATUS.md § "IM-1".
- **IM-3 — the open door.** `LEAGUE_LAB_GATE` = `open` | `password` (unset: today's rule — password when
  `LEAGUE_LAB_APP_PASSWORD` is set); `open` ignores the password, `password` with no password keeps the door shut. A rate
  limiter on every `/api/` route but the health check (`ratelimit.py`: per client, keyed by an HMAC of
  `CF-Connecting-IP` on Render, buckets read 300/min burst 150 · heavy 20/min burst 20 · write 60/min burst 30, 429 with
  `Retry-After`, `LEAGUE_LAB_RATE_LIMIT=off`, `GET /api/ratelimit` to verify the keying live); the Guard
  (`security.py`: cross-site writes refused by `Origin` / `Sec-Fetch-Site`, bodies bounded, `nosniff`,
  `Referrer-Policy`, a CSP the app and GA pass with `frame-ancestors 'none'`, HSTS on https); provider errors no longer
  echo their cause; MFL redirects only to `*.myfantasyleague.com`. Reference league keys `ref:ppr` / `ref:half` /
  `ref:std` (`refleague.py`) on every research route without ownership, `needs_league` on the decision routes; the web's
  front door ("Browse the lab"), the "No league · Half PPR ▾" picker and the invitation cards; title / description /
  Open Graph / canonical and `robots.txt`. `docs/SECURITY_PUBLIC.md`.
- **IM-4 — passkeys: accounts that work with no email.** "Create an account with a passkey" (one tap, the device's own
  sheet; this browser's leagues, default, Stats views and Yahoo / ESPN connection go to the account by themselves),
  "Sign in with a passkey" on any device (nothing typed), "Add another passkey", the list with labels and last use,
  Remove (never the only way in), "Add an email" when the server has a mailer. WebAuthn with py_webauthn 3.0.1
  (discoverable credentials, user verification preferred, attestation none); challenges kept on the server (single use,
  5 minutes, bound to the browser, the site and the purpose); `LEAGUE_LAB_PASSKEY_ORIGINS` (default
  `https://isuckatfantasy.io`). `LEAGUE_LAB_ACCOUNTS=auto` now turns accounts on when the API secret is set and the
  tables exist, with the methods the server has (`passkey` once the nightly has applied the new part of
  `scripts/hosted_accounts.sql`, `email` with the Resend key). Every state-changing account route refuses another site
  (`cross_site`). docs/ACCOUNTS.md § "Passkeys".
- **IM-5 — DFS: values, undervalued players and lineups from the site's own salary file** (`/dfs`, the DFS tab; no
  league needed; docs/DFS.md). Nothing fetches salaries: the user adds DraftKings' or FanDuel's salary CSV (classic,
  showdown, full roster), parsed in one request and kept only in that browser tab. Our stat lines re-priced in the
  site's scoring (DraftKings' +3 bonuses at their odds), the range from the nearest reference scoring, points per
  $1,000, each position's salary line on the slate and every player's gap to it (undervalued / overpriced with the
  app's own reason), unmatched players listed and never guessed, an exact lineup optimiser (checked against brute force;
  1 s a lineup; cash or tournament, 1–20 lineups, always in / leave out, the sites' team rules) and the lineup-upload
  CSV (formulas neutralised). `GET /api/dfs/projections`, `POST /api/dfs/slate`, `POST /api/dfs/lineups`. Salary files
  in the tests are synthetic; the real formats wait for Andrew's upload.
- **IM-2 — the Stats tables' screen: the full table, readable without clicking into anyone.** Players · Stats has two
  views one tap apart: **Key stats** (the preset's columns) and **Full table** (every column the position has, 31 for
  WR / TE today, under group headers: Receiving · Air yards · Red zone · Next Gen Stats · …); Full table from 900 px,
  Key stats on a phone; `?view=` and remembered on the device. A table built for width (`components/stats/`): the name
  column and both header rows sticky, sideways scroll inside the box only, sort on any column (`aria-sort`), group
  toggles over the column picker, a tapped row highlighted, a dash's reason and a small sample's size on hover or tap,
  "Showing 50 of 291 — Show all" (past 100 rows only the rows near the visible part are in the page: smooth at 450 rows
  x 46 columns), **Download CSV** (`/api/players.csv` when the API has it, else built in the browser). Works on today's
  answer and on IM-1's (`group`, `full`). The search's pending write no longer lands on the next page's address.

## 2026-10-05 — Wave I-L

- **PO — Yahoo refuses the app, and the app said so wrongly.** A friend connected with Yahoo four times in three minutes
  ("Your Yahoo connection has expired. Connect with Yahoo again.") and then got "league is private or does not exist"
  for a public prize league (`1598462`; Yahoo's own page opens signed out). Render's log: four clean sign-ins, no
  league ever listed, three 404s — every Yahoo data call failing, which is what Yahoo answers an app whose Fantasy
  access it has not approved (401 / 403 `oauth_problem="additional_authorization_required"`; self-serve access ended
  in August 2026). `yahoo_client`: that refusal is `YahooAccessPending` (the `yahoo_not_configured` code: "coming
  soon", in words that say Yahoo's approval is pending and nothing is wrong with the league or the sign-in), never a
  session expiry or a private league; a non-200 on a resource that names no league is never "that league is private";
  every non-200 is logged (status, `oauth_problem`, resource, the description — no token) and kept for
  `/api/yahoo/status` (`access`, and `?probe=1` for one live call). `render.yaml`: `LEAGUE_LAB_YAHOO_ACCESS: pending` —
  `/api/providers` `yahoo_configured` false + `yahoo_pending` true, the setup screen's disabled "Connect with Yahoo —
  coming soon" with the pending words; Yahoo's own refusal holds the same state for an hour without the switch. The
  league list's "expired" note is only for a refused token now. Yahoo's attribution ("Fantasy data provided by Yahoo
  Fantasy", linked) is under every screen of a Yahoo league and on its setup card — the docs said it was; no screen
  had it (`docs/STATUS.md` § "PO — Yahoo refuses the app").

- **PO, after the deploy — MyFantasyLeague's moves verified live; the weekend's moves were missing.** Checked
  `mfl:70587` and `mfl:21861` on the live app against MFL's own transactions export: every listed move matched (time,
  team, adds, drops, blind bids), but MFL files a move made once a week's games have begun under the *next* week, so
  the newest moves — dad's two of the weekend — were not listed until MFL's week turned. `MFLLeagues.transactions`
  reads the next week's file with MFL's current week (listed under the week in progress; a later round is empty, so
  nothing shows twice). A dropped team unit on no roster was named by its id (`mfl:0667`) on the first read after a
  start: the moves are read before the names now (`decisions.moved_directory`). MFL's transactions row loses "as
  built, not verified on a live league yet" (`platforms._CAPS`, the pins in `test_ii5` / `test_ik3`, PROVIDERS, the
  il5 / il2 recordings). No trade has been seen on a live MFL league yet (`docs/STATUS.md` § "PO — MFL's transactions
  verified live").

- **IL-4 — Sleeper's player directory a quarter of its size; the Trade Finder's first answer faster.** The directory
  (Sleeper's ~12,200 players × 53 fields, 37 MB in the server live) is trimmed as it is read to the 15 fields the code
  reads, nulls dropped, text shared, one read-only copy: **38.7 → 8.8 MB** at Sleeper's size (a synthetic directory of
  that size and shape, `scripts/measure_memory.py --synthetic-directory`); the server after the four leagues **281 →
  247 MB**. The Finder prices another manager's own best waiver move only when one of his trades can still be credible
  (`LEAGUE_LAB_FINDER_LAZY_THEIRS`, default on; the other cards say "not compared" and why) and reads a league's free
  agents once instead of once per roster: a cold Finder on an on-demand league **23.5–25.6 s → 8.7–10.1 s** with the
  whole directory (8.7–11.3 → 6.1–8.2 s with the fixtures'), the same verdict and credible trades. `/api/status`
  `memory.directory`. No screen changed but those "Explore alternatives" cards' "Theirs:" line; unverified live until
  the PO reads `/api/status` after the deploy (`docs/STATUS.md` § IL-4).

- **IL-2 — MyFantasyLeague complete on dad's league.** MFL's transactions export is read (`MFL.transactions`, week by
  week, a past week cached a day; `MFLLeagues.transactions` in Sleeper's shape: free agents, waivers with the blind
  bid, trades both ways with future picks): League's "Latest moves" lists an MFL league's moves, and Waivers gains
  **"Recently added in this league"** on every platform (every team's adds of this week and last). MFL's live scoring
  narrows the week's odds the way Sleeper's points do (a starter MFL says is done counts at MFL's points; a game in
  progress keeps its range) and the League card shows each team's score so far ("8.0 so far"). The Waivers stamp line
  names the team's place in an MFL waiver order or its blind-bid balance when MFL's export carries them. The
  correctness sweep on `mfl:70587`: every rule MFL states is priced; weeks 1–2 recomputed franchise by franchise from
  our scoring: 21 of 24 exact, 3 within 2 points (team defenses: a sack count, two return TDs without a length); 0 of
  167 rostered players unmapped; slots exact both ways; the playoff team count capped at the league's size; the
  check's names read "Kansas City Chiefs". **Built from MFL's documentation on a synthetic transactions fixture — not
  verified on a live league yet** (`docs/STATUS.md` § IL-2).

- **IL-5 — accounts phase 2: connections, the watchlist, the providers' loose ends.** A Yahoo or (switch on) ESPN
  connection made while signed in is kept with the account, sealed with the API secret (`accounts.connections`;
  Yahoo's refresh token + GUID, ESPN's two cookies; never in the clear, never logged): a sign-in on another device
  re-issues the cookie from it, Disconnect deletes it, deleting the account cascades, a refused Yahoo refresh marks it
  expired; guests unchanged; `/api/account/me` lists `connections`; `ll_session`'s path is `/api`. **`/watchlist`**:
  the players saved with **☆ Watch / ★ Watching** in the drawer (signed in), each with his status today, this week's
  projection in the league on screen and free agent / rostered by whom (`GET /api/account/watchlist`, read the lean
  way — equal to the drawer's card, ~5× cheaper); a tap opens the drawer; Remove; the ⋯ entry; GA `watchlist_add` /
  `watchlist_remove` (ids only); a one-line invitation signed out. `/api/providers` follows the switches:
  `LEAGUE_LAB_PROVIDER_VERIFIED=espn,yahoo` flips a provider to supported without a deploy, `LEAGUE_LAB_ESPN_LEAGUES=off`
  says "not available right now" in place of the form. The duplicate-id rule on `mfl_id` / `espn_id` / `yahoo_id` (4
  ESPN ids in nflverse's table, all retired / free agents, now map to nobody). Root 1,258 / API 730 (4 failed on the
  clone, as on `main`) / e2e 380, 0 failed. Verified live: no (`docs/STATUS.md` § IL-5).

- **IL-3 — the week's odds graded every night; v3.3 (a receiver on a new team); the registry.** `league-lab
  grade-odds` grades the win probability My Week showed (Brier, log loss, how often the favourite won, a ten-decile
  calibration table) and the ranges (P10–P90 and P25–P75 coverage, the median's miss per position) on the decision
  record's scored weeks, per league and week and season to date, into `analytics.odds_grades`; `/api/status` carries
  the latest (`odds_grades`). First grade on 2026 weeks 1–2: 22 matchups, Brier 0.271, 80% ranges held 69.6% of 352
  starters — two weeks are noise; the nightly re-grades from week 4 with the five-knot ranges. **v3.3**: a veteran WR
  in his first games with a new team is projected about a fifth lower (k = 0.79 for 2026; one mean-unbiased scale on
  his stat line, fitted on the three seasons before, both scorings), kept by a rule written before the run: on
  2021–2025 his projection's miss fell 0.18 a game (4 of 5 seasons), its bias −0.94 → −0.41, the board not hurt;
  `MODEL_VERSION` v3.3, `LEAGUE_LAB_NEW_TEAM_SCALE=0` turns it off. Twelve metric registry rows (the odds grades, v3.3
  and seven documented families that had none) and a test that lists any METRICS family without one (`docs/STATUS.md` §
  IL-3).

- **IL-1 — the advanced-data layer (the fifth review § 10).** `analytics.mart_player_ngs_week` (NFL Next Gen Stats per
  gsis id × season × regular-season week, week 0 = NGS's season aggregate; 26,069 rows 2016 → 2026 week 3; dbt PASS 12 /
  WARN 1: two NGS players not in `player_id_map`). Players · Stats gains **time to throw**, **NGS CPOE**, **RYOE per
  carry** (2018 →), **separation** and **YAC over expected** (WR / TE: NGS publishes no RBs) — each window the mean of
  NGS's weekly values weighted by NGS's own denominator, never a mean of means; "—" with NGS's qualification as the
  reason (QB 15+ attempts, RB 10+ carries, WR / TE 5+ targets), never 0; presets QB + TTT + CPOE, RB + RYOE, WR / TE +
  separation + YACOE. The drawer's **Role** block (`league_lab.roles`): his last 2 games against his earlier ones (a
  change named only past one s.d. of the earlier games and a floor; else "steady" / "too early to say"), his share of
  his position group's opportunities against its points in the league's scoring ("production ahead of his volume" /
  "volume ahead of his production" / "in line"), and the games a positional teammate missed while on the roster (2024
  on, same team, 2+ games or "no games without X to go on") — words about the past, no probability, no model change.
  For the PO: `player_team_history` into `SLIM_TABLES` (sync); nothing for the nightly.

## 2026-10-05 — Wave I-K

- **PO (the merge, 2026-10-05 12:30 ET).** The accounts block in `scripts/sync_to_hosted.sh`; the accounts schema on
  the sandbox's main database; the setup header names all four platforms. Root 1,263 / API 722 / e2e 366, 0 failed.
  ESPN and Yahoo ship labelled **unverified** until the PO opens a live league after the deploy; the ESPN private
  switch is off; Yahoo's button is "coming soon" until Andrew's app registration; accounts are off until a Resend key.

- **IK-3 — ESPN and Yahoo in the setup flow; the four-provider seam; the id-map audit.** The `Router` dispatches
  `espn:<id>` and `yahoo:<game>.l.<id>` keys to IK-1's and IK-2's adapters (a provider not set up answers in words,
  never a 500; Sleeper / MFL answers unchanged); `/api/leagues?espn=` / `?yahoo=` / `?yahoo_me=1` with specific errors;
  `/api/providers` says `espn_private` / `yahoo_configured`; ESPN and Yahoo "as built, not verified on a live league
  yet" on every feature. `/leagues` offers four platforms: ESPN by id or link ("Private league?" only behind the
  server's switch, off), Yahoo by "Connect with Yahoo" → your leagues → My Week ("coming soon" until the app is
  registered); remembered with "· ESPN" / "· Yahoo". The audit: ESPN and MFL ids cover every rostered skill player;
  nflverse has no `yahoo_id` for any 2025 / 2026 rookie. Usage counts ESPN / Yahoo views. Unverified live: everything
  ESPN / Yahoo (`docs/STATUS.md` § IK-3).

- **IK-1 — ESPN leagues on demand (unofficial).** A public ESPN league opens by its id or link (`espn:<id>`):
  `league_lab.espn_client` reads ESPN's own web endpoints (`lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/…`, the
  views `mSettings`, `mStatus`, `mTeam`, `mRoster`, `mMatchupScore`, `mTransactions2`, `kona_player_info`, as the
  open-source client cwendt94/espn-api documents them) with TTL caches, a 30-a-minute budget and the answers trimmed to
  what is read; `league_lab.espn_leagues.ESPNLeagues` serves the league in Sleeper's shapes — ESPN's lineup slots (OP as
  superflex, D/ST as the team's defense, IDP / P / HC left out and said), its scoring on Sleeper's keys (what is
  approximated or not priced listed on the card), rosters with ESPN's starters, the schedule and points, adds / drops /
  trades. Private leagues are in the code behind `LEAGUE_LAB_ESPN_PRIVATE` (**off**): the user's own `espn_s2` /
  `SWID` cookies, sealed into an `ll_espn` cookie in their browser, never stored or logged. `LEAGUE_LAB_ESPN_LEAGUES=off`
  is the kill switch. Synthetic fixtures `espn:4242` (public) / `espn:5150` (private); **not verified live** — the PO
  checks after the deploy (STATUS § IK-1), and Andrew needs any public ESPN league id for 2026.

- **IK-2 — Yahoo leagues through Yahoo's official API** (as built, **not verified live**). *Connect with Yahoo*
  (OAuth 2.0: `GET /api/yahoo/connect` → Yahoo's consent → `/api/yahoo/callback` → back to `/leagues?platform=yahoo`)
  keeps the manager's Yahoo tokens only in an encrypted `ll_yahoo` cookie on his device (`LEAGUE_LAB_API_SECRET`; never
  logged or stored); `yahoo_client` reads the Fantasy Sports API (settings, teams, rosters by week, scoreboard,
  standings, transactions, free agents, my leagues) with one normaliser for Yahoo's nested JSON, Yahoo's stat ids on
  Sleeper's scoring keys, W/R/T → FLEX and Q/W/R/T → SUPER_FLEX, a per-manager cache and a budget; `YahooLeagues`
  serves `yahoo:461.l.4242` in Sleeper's shapes (starters exactly where Yahoo seats them; `yahoo_id` from nflverse's
  table, else by name, else listed). Every read needs a connected manager, even for a public league (Yahoo's OAuth 2.0
  has no app-only token). Without `LEAGUE_LAB_YAHOO_CLIENT_ID` / `_SECRET` the connect route answers 503
  `yahoo_not_configured`. Synthetic 12-team superflex fixture league; it prices and solves through the real pipeline.
  `docs/YAHOO_TERMS.md`, HOSTING § Yahoo (Andrew's app registration). No Sleeper / MFL number moves.

- **IK-4 — accounts, phase 1 (built, off until the Resend key is set).** Sign in with an emailed link (no password;
  `/account`, the ⋯ menu, a line on the setup screen): the leagues, the team in each, a default league and the saved
  Stats views follow the account — a fresh browser that signs in gets them and opens the default league's week with
  no setup (the fifth review § 9's acceptance; `web/e2e/ik4` at 375 / 1300). `scripts/hosted_accounts.sql` (schema
  `accounts`, the design's eight tables, the app role's grants on those only), `api/league_lab_api/accounts.py`
  (`/api/account/*`, `ll_session` 90 days and revocable, limits 5 / address / hour, 30 / IP, 90 a day), `db.run_rw`;
  the link's token rides in the URL fragment and is never logged. Without `LEAGUE_LAB_RESEND_API_KEY` nothing shows.
  For the PO: the `sync_to_hosted.sh` lines, Resend + four DNS records (HOSTING § "Accounts"). Verified live: no.

## 2026-10-05 — Wave I-J

- **PO (the merge, 2026-10-05 01:50 ET).** `MALLOC_ARENA_MAX=2` / `MALLOC_TRIM_THRESHOLD_` in the image; the memory
  script re-run on the merged code: four leagues 404 → 272 MB. Render's auto-deploy trigger (`checksPass` → `commit`)
  is left to Andrew (the PO's tooling will not change a CI gate); until then pushes are deployed by hand.

- **INF-2 — the memory diet** (Render ran out of its 512 MB on Sunday 2026-10-04). Every in-process cache is now a
  region of one byte budget (`league_lab.memo`, `LEAGUE_LAB_CACHE_MB`, default 64; least recently used out first,
  TTLs kept), text values are interned at the fetch and `numeric` read as float, one projections Board per week is
  shared by every league (its raw rows not kept beside it), the cache hands out copy-on-write copies, and the server
  `malloc_trim`s after a request. Four leagues: **405 → 276 MB** on the PO's script (272 with `MALLOC_ARENA_MAX=2`,
  the Dockerfile line for the PO; the server alone 243); a fifth league and two more rounds of all five hold at ~308.
  `/api/status` gains `memory` (RSS, the budget by region), the console's Data Status page one line,
  `scripts/measure_memory.py` re-measures, DEPLOY § Memory. Same answers: no test re-pinned.

- **II-6 — the presentation list.** Waivers' top three: the name wins — a narrow card (three across at 1300, the drawer
  open, a phone) puts the gain and its label under the name ("+9.8 WEEKS 4–7 IN TOTAL"), the name wraps and is never
  cut ("Tyler …" before), no badge under the label (`ClaimCard`, a container query). Trades says "No compelling trade
  found" once: the answer at the top; the Finder adds nothing for Any, and one line of that position's reason under a
  position chip. Closing the drawer (×, Escape, Back) keeps what the screen wrote to the URL while it was open — a search
  typed just before the tap, a filter changed beside it — still one history entry per screen (the router's pop hook).
  `e2e/app.spec.ts` (the live-API suite) follows the drawer (a tap → the drawer, `pane-full` → the page); the II-4
  recording re-recorded at the pinned clock (its words differed). Fixtures e2e 344 passed. For the PO: web only; the
  live-API suite was updated blind (type-checked); the re-record's injury-check stamp is real time.

## 2026-10-04 — Wave I-I

- **PO (the merge, 2026-10-05).** The pinned clock lands (`league_lab.clock`, `LEAGUE_LAB_NOW`; both suites pinned to
  2026-10-03 16:00Z — API 630 passed, 0 failed on a Sunday evening); Google Analytics 4 wired (`G-HJWGHZ79BG`, no PII,
  `LEAGUE_LAB_GA`). The Waivers answer on the API is the web's `topIntro` (API, console and web agree); the replacement
  chain keeps the shown lineup on ties (no phantom swap of two tied defenses); the drawer counts a GA `select_content`
  once; `metric_registry` seeded (+8 rows). Known and left: Waivers' top-three card names squeeze beside an open drawer
  at 1300; the Trades screen says "No compelling trade found" twice.

- **II-0 — the calculation audit (the fifth review § 1).** Team's "Strength by slot" compared a starter's projected
  points with every roster's *margin* (Puka 14.8 against "average 5.0, best 7.3"); it now draws one bar per starting
  slot (RB1 and RB2, each FLEX apart), the player you start there against every roster's starter at the same slot, in
  the same points — the best is never below a member — with each position's starters added up and usable depth (the
  bench's own best lineup, not its raw points) under the bars (`/api/team` `strength_by_slot`). A replacement is a legal
  chain: "Bhayshul Tuten (RB) moves from FLEX to RB; Michael Wilson (WR) fills the open FLEX" (`lineup.replacement_chain`,
  locks kept: a locked FLEX stays put, a locked bench player never comes in; after a kickoff since the build the card's
  number is the re-solve's). Full names when two players on a roster share one (`cards.display_name`). The partner
  card says a losing week ("loses 0.5 this week but gains 7.2 over weeks 4–7"), never "Nothing changes this week"
  beside its own −0.5 (`trades.week_story`).

- **II-1 — credible trades.** The Finder promotes a trade only when it is legal, beats **both** teams' own best
  alternative by a starter point (every empty slot — a bye — filled from the free pool for both sides, never priced at
  zero) and is a plausible offer (a kicker or defense for a starter is not, derived from the league's slots and free
  pool; nor a trade that takes much more season value than it gives); otherwise "**No compelling trade found**" with the
  reason, the rest under "Explore alternatives". Each card: the label (plausible offer / a roster-fit idea /
  implausible), both lineup effects, required drops, depth, both waiver alternatives (guaranteed or a claim), why they
  might consider it, reasons they might refuse — no probability. The review's Folk package is a regression fixture:
  Implausible, not promoted.

- **II-2 — one player viewer everywhere: the drawer.** Every player name on a league screen (Players, Waivers,
  Receivers, Team, Season, Trades, League, Matchups, My Week, search, names inside sentences) opens the same drawer —
  beside the screen from 900 px, a full-height sheet on a phone — and the screen under it keeps its search, filters,
  sort and scroll. A compact first view in four sections (Overview · Usage · Game log · News), Expand (a larger view
  with every section), Add to compare, Full player page; Escape, × and browser Back close it and focus returns to the
  name that opened it. Waivers' free agents offer Evaluate add / drop from it. The research screens no longer re-mount
  when the drawer opens.

- **II-3 — Players · Stats: one research table with WR / TE, RB and QB presets, and a data inventory.** Receivers is
  the WR / TE preset (`/receivers` redirects; role cards at `/receivers?view=cards`); windows (season, last 3 / 5 games
  played, last 3 / 5 calendar weeks, a week range), totals or per game, whose players, NFL team, minimum games / opportunities, a column
  picker with definitions, sticky player column and header, saved views, 2–4 side by side. Shares over several games
  are summed numerator / summed denominator; unknown is — with the reason; routes are unavailable in-season (said).
  `docs/DATA_INVENTORY.md` lists every column: 15 verified present, 29 derived, 2 planned, 2 unavailable.

- **II-5 — one setup flow; what each platform gives, said; ESPN and Yahoo researched; accounts designed.** The league
  screen is one **Fantasy platform** choice (Sleeper / MyFantasyLeague, remembered, `?platform=`) → the username or the
  league link → the league → the team → My Week, with "where do I find it?" and an example per platform, specific
  errors with the fix ("That Sleeper username does not exist: “x”.", "MFL league 70587 is private or does not exist. Ask
  the commissioner to allow API access…"; `code` / `fix` on the API's 404s), a Sleeper league by its link
  (`/api/leagues?sleeper=`), a team picker where you have no team, and "No account needed". `platforms.capabilities()`
  (`/api/providers`): eight features per provider, said instead of substituted — League's moves on an MFL league read
  "Transactions: not available for MFL leagues yet." `docs/PROVIDERS.md` (the matrix; ESPN: public leagues read-only at
  most, not built, never login cookies; Yahoo: after accounts and Yahoo's approval) and `docs/ACCOUNTS.md` (the model;
  sign-in by an emailed link, ~$0 at beta scale).

- **II-4 — the copy standard, Season's three views, news as a decision feed.** Rates say "per game / per target / per
  week" everywhere (`scripts/copy_standard.py`, WORDS.md § "The copy standard" with each metric's denominator; Carry
  share defined on the card). Season is **My roster outlook** (default) / **Potential upgrades** (before acquisition
  cost: the add / drop or the trade is the next step) / **Rest-of-season projections**, each with its counterfactual
  said — the numbers unchanged; injury cover apart. My Week's "What changed" items say the decision status
  (Recommendation changed / Watch for confirmation / No action currently indicated), the forecast status ("Included
  in the current projection" only with a recorded update; context only; update pending), why it matters here and the
  next step; the home runs decisions → changes → lineup status; three clocks (data built · injuries checked · news),
  never a stale warning. Waivers' top claims say when they help (this week / a bye / later / stash) and name the
  claims competing for one spot; Team's depth defined; League's luck and hindsight words.

- **INF-1 — a pinned clock for the suites; Google Analytics.** `league_lab.clock.now()` (an in-process pin, else
  `LEAGUE_LAB_NOW`, else the wall clock — unset in production) now decides the locks and the decision week on the
  request path (`anyleague`, `decisions`, the card, `lineup.build`, events, PlayerWire, `app/lib/ui.first_open_week`,
  `app/lib/cards` — whose `kicked_off` was the database's `now()`); the stale rule and every fetch / write stamp keep
  the real time. Both suites run at Saturday 2026-10-03 16:00 UTC: on a Sunday evening during games, on the main
  database, the API suite is 575 passed / 0 failed (`main` in the same minutes: 54 failed) and the root suite 1,141
  passed / 0 failed (`main`: 2 failed); IH-2's three xfails are plain passing tests. The web app sends Google
  Analytics 4 (property 557285408, `G-HJWGHZ79BG`) page views, screen views and a few taps — ids only, only after
  sign-in, only from isuckatfantasy.io (`LEAGUE_LAB_GA=off` removes it at build time); About says so; no cookie
  banner for the password-gated beta (PO call). HOSTING § "Usage" → "Google Analytics".

## 2026-10-04 — Wave I-H

- **PO (integration).** Five packages merged (M6, V-2, IH-1, IH-2, IH-3 below). On Andrew's word the stale banner
  never shows to a league-mate (the state stays on `/api/health`, `/api/status` and the console); the nightly gains
  the failure summary step and `LEAGUE_LAB_RECORD_MFL`; registry rows `decision_market_edge`, `week_win_probability`.
  Root 1118 / API 518 / e2e 271 (plus the Sunday-afternoon clock failures that `main` shares).
- **M6 — v3.2: a rookie's first games are projected from his draft slot, on the stat line, and on by default.** M5's
  cold-start prior moved onto the line itself (`calibration.blend_lines`, before anything is priced): the house board,
  the NFL-wide line, the ranges and every on-demand league now carry the same number for a player in his first three
  games (re-measured on the line: cold rows' MAE RB −0.09 / WR −0.31 / TE −0.34, 4–5 of 5 seasons — kept, so
  `LEAGUE_LAB_COLD_START` defaults on). Veterans on a new team measured three ways, none kept (STATUS § M6). The nightly
  builds the prior's fitting rows itself (`calibration-oof`, a no-op once current; `ops.calibration_oof` travels).
  "Why this number" prices its pieces in the week's own mode. The record's Sleeper side is priced at the odds in an
  EV week (`ops.market_record`), like ours.

- **V-2: the decision record, personal and live.** The Team page's "Your calls this season" (what you started, what
  our lineup would have scored, the best possible, each close call and how it landed; `/api/record?league=&team=` →
  `decisions.team`, the console's Record page too), "had you started Sleeper's projections" next to ours
  (`ops.decision_market`, `league-lab validate`), the news-affected weeks from the event store's status moves (the
  injury report stays the fallback), and MyFantasyLeague leagues in the record: the on-demand lineup frozen before
  kickoff (`LEAGUE_LAB_RECORD_MFL`), graded from MFL's own weekly results — dad's league shows weeks 1–3, rebuilt.

- **IH-1: the product says when it is stale; the operator hears when the nightly fails.** One rule
  (`league_lab/freshness.py`: the newest projections' fit older than 30 hours): `/api/health` `stale` + `age_hours`,
  `/api/status` `nightly` {as_of, age_hours, stale, limit_hours, words}; My Week's one line above the actions
  ("Yesterday's numbers: the morning update did not run. Injury statuses are still live."), the footer's "Updated …"
  and the console's Data Status page say the same. The web app's error states: `components/ErrorCard.svelte` (the API
  down, a 500 naming `/api/status`, still waiting after 25 s — each with a Try again that really asks again) on My
  Week, the first screen, Trends, Receivers, Players and Compare; "Signed out — sign in again" on a 401 after sign-in;
  a 500 from the API is the contract's plain words. `scripts/nightly_failure_summary.sh` for a proposed `notify` step
  (the failing stage, published or not, the last 40 log lines; the PO wires it); GitHub's failure email to the run's
  actor (Andrew) in HOSTING § 5; the trigger's page reports the last dispatch (an optional KV binding `STATE`).
  Events retention: `hosted_events.sql` prunes superseded news / briefs after 120 days and availability after 400.

- **IH-2: the small opens from I-G.** A dropped MFL team unit has a season value and a replacement (IG-1's
  `unit_market` in Waivers' drop cost): a kicker claim now drops the kicker it replaces (dad's league teams 2, 4, 6,
  9, 10, 12; team 8 has an open spot and does not move); a trade verdict with an uncounted player leans on nothing;
  the console's stash card reads the nightly's claim / watch (one source for the watch words); the Team page says when
  MFL's roster was read; Sleeper's `daily_waivers_days` decoded ("Claims run every day except Saturday at 5:00 AM
  ET"); a Questionable starter shows once in "What changed"; availability events carry their `game_key`.

- **IH-3: the week's win probability, as information.** My Week says under the opponent line how often your starters
  outscore his ("This week is a coin flip: 53%, 120 to 117 expected."; one line per game of a double header; "2 of your
  9 have played, 3 of theirs" once games are in), and the League screen shows both teams' chance for every game of the
  week (`/api/league/week-odds`, asked after the screen shows). Both lineups' ranges, centred on the projections, one
  copula with D6's teammate / opponent correlations across both sides, played games at their actual points; calibrated
  on 308 house-league matchups of 2024–2025 (a shrink toward 50%: Brier 0.2395 against a coin flip's 0.25; the
  favourite predicted 58.0%, won 57.5%). It never picks a player: the cards still decide on expected points.
  METRICS § "Win probability — the week".

## 2026-10-04 — Wave I-G

- **The nightly's trigger.** GitHub's schedule started every nightly 3.5–6 hours late; `ops/nightly-trigger/` (a
  Cloudflare Worker on a cron) dispatches the workflow at 07:37 ET and re-checks at 09:37 / 11:37 (HOSTING § 5 "The
  trigger"); the workflow's own schedule stays as the last resort.
- **PO (integration).** Six packages merged overnight (M4, M5, IG-1, IG-2, V-1, IG-3 below); the registry rows
  `decision_edge`, `decision_regret`, `call_calibration`, `unit_season_value`; the flip of `LEAGUE_LAB_EV_PRICING`
  ships (the nightly's env only — Render untouched; the first nightly after the push prices weeks 5–18 at their
  odds, week 4 stays flat and frozen); v3.1 measured and left off; the hosted copy gains `mart_decision_record`,
  `mart_decision_calls`, `ops.lineup_record` and the `events` schema. Root 1082 / API 548 / e2e 222.
- **M4: the record says how it was priced, and every screen prices as the record does.** `ops.projections`,
  `ops.projection_ranges` and `ops.projection_backtest` carry `pricing` (`flat` | `ev`); `LEAGUE_LAB_EV_PRICING` is now
  an override and, when unset, the newest build's label decides (a frozen week keeps its own), so My Week, Waivers,
  Trades and the player card can no longer disagree with Trends and the record over the bonuses; "Sleeper's
  projection" is priced the same way; `/api/record` and About say "Weeks 1–4 were priced flat; from week 5 the bonuses
  are priced at their odds." The flip is the nightly's env alone (a separate commit: "M4: the flip"). Fixed on the
  way: the scenarios' base under expected-value pricing (it would have failed the first nightly after the flip).

- **M5 — v3.1 measured, nothing switched on.** Three candidates through the walk-forward harness, each behind its own
  switch (off): the ranges fitted on the graded points (`LEAGUE_LAB_RANGE_TARGET=graded`: the 2-point and long-TD
  points the record grades were outside every range), a level for the fringe (`LEAGUE_LAB_FRINGE_LEVEL`) and a
  draft-slot prior for a player's first games (`LEAGUE_LAB_COLD_START`). Kept: the graded target at QB (interval score
  −0.007 in the dynasty, coverage closer to 80%) and the cold-start prior at RB / WR / TE (their first three career
  games' MAE −0.16 / −0.31 / −0.30, 4–5 of 5 seasons); dropped: the fringe level (its miss changes sign by era). The
  harness table and the rules: STATUS § "Wave I-G" (M5), METRICS § "Calibration of the top" → "v3.1"; the rows in
  `dbt/seeds/feature_experiments.csv`.

- **IG-1** — team units count: MFL's team QB / team kicker get a season value above the best free unit of the same kind
  ("Houston Texans QB + Tuten for Rice" no longer says "Not counted"); the Finder leaves out trades on the season-value
  gap, not the raw rest-of-season totals; a player with no projection shows a dash and "no projection", never 0.00
  (the API sends null; My Week says how many starters its total counts at 0).

- **IG-2: the event store.** The server keeps what it learned and showed — each injury-report status move (ESPN /
  Sleeper), each ESPN headline and PlayerWire brief a screen showed — in `events.events` (keyed by player, team and
  game; source URL, publication / effective / ingestion times, superseded), written off the request path by one
  writer thread (`scripts/hosted_events.sql`, run by the sync after U-1; `LEAGUE_LAB_EVENTS=off`). My Week's "What
  changed" reads it: a status line cites its source, the report's time and the player's ESPN page; his PlayerWire brief
  shows there too. The matchup evidence's missing corners carry the event and its URL. `/api/status` → `events`;
  `/api/events?league=&team=` for QA; About says what is kept (docs/HOSTING.md § "Events").

- **V-1: the decision record — what our lineups would have scored, graded.** `ops.lineup_record` keeps the lineup
  the app recommended for every team before each week's first kickoff (the projections' freeze rule; weeks played
  before it existed are rebuilt once from the frozen projections and labelled so), with the cards' closest calls and
  their odds. `league_lab.validation` and the marts `mart_decision_record` / `mart_decision_calls` grade it: the points
  our lineups would have added over the ones started, the best lineup in hindsight, how the coin flips landed against
  their percentages, the lineups whose starter's injury report changed after the build. `/api/record` carries
  `decisions`; About and the console's Record page show "Our lineups against the ones started"; `league-lab validate`
  writes and grades (a nightly step proposed).

- **IG-3, the small opens.** The nightly's upside stashes name their drop by IF-1's cost (`choose_drops`) and say
  claim or watch on the row, so the mart and the screen agree; Waivers says when claims run, from the league's own
  settings ("Claims run Wednesday 3:00 AM ET (rolling waivers); players lock at their own kickoff — the next game
  starts Sunday 1:00 PM ET", MFL: first come, first served / "see MFL"); My Week for an MFL league says when MFL's
  rosters were read ("MFL rosters updated 4:05 AM ET ›"); About puts the MFL grade's qualification under the headline
  grade; `usage.events` keeps 180 days (the sync deletes older views); the console's page guide lists Usage.

## 2026-10-04 — the product is isuckatfantasy

- **Renamed.** Everything a manager sees — the sign-in screen, the top bar, the home-screen icon and its mark ("isaf"),
  the page title, the manifest, every sentence that named the app ("isuckatfantasy never changes your lineup or
  claims…") — now says isuckatfantasy (`web/src/lib/brand.ts`, `api/league_lab_api/settings.py:APP_NAME`). The
  codebase, the package, the environment variables, the roles, the repository, the Render service and the research
  console keep the name League Lab. The domain follows (Andrew).
- **CI.** The image workflow's smoke step and `scripts/smoke.sh` check the served page for the product name (the
  rename's first run failed on the old title; the image was not pushed, so that deploy was by hand).
- **N2 merged** (branch `playerwire-integration`, cut before Waves I-E/I-F; the PO resolved it): PlayerWire's briefs
  lead the news line and ESPN fills the rest in IF-4's order — every item carries `kind` ("playerwire" | "espn") and
  `about` (a brief is his by id: "player"); N2's own entry is below under 2026-10-03.
- **Fixed.** Compare (`/api/research/compare`) answered 500 whenever both players had an adjusted rank: the PO's I-F
  verdict words import `cards.rank_words` relative to `app/lib`, and the API loaded `matchups.py` outside applib's
  package (`research._load_matchups`); it is a member of that package now, as on the console.

## 2026-10-03 — Wave I-F

- **PO (integration).** `mart_waiver_moves` carries the drop's cost pieces (the rows fill at the next nightly; older
  rows are re-ranked on read); the Compare verdict's adjusted ranks read in one direction in words ("9th-fewest WR
  points allowed by Worthy's"); three registry rows (`drop_cost`, `trade_beyond_alternative`, `matchup_personnel`).

- **U-1 (usage tracking).** The web app counts screen views — which screen, which league and team number, when —
  in `usage.events` on the hosted copy (a schema the nightly never drops; `scripts/hosted_usage.sql`, run by the sync
  after the restore): `POST /api/usage` (beacon, 204, behind the password, 1 a second per browser-day with bursts of 5,
  `LEAGUE_LAB_USAGE=off` stops it), one explicit read-write transaction on its own connection while the app role stays
  read-only; no names, usernames or IP addresses. Read it on the console's Usage page or `GET /api/usage/summary`;
  About says so in one line.

- IF-1: waiver drops are valued before they are prescribed — each drop's cost in pieces (lineup loss with the claim, depth, later starts, season value above the waiver wire, upside); the cheapest drop per claim, one alternative and why (Carlson for McPherson, not Harrison); "No claim is worth a roster spot this week"; stashes say "watch" instead of a drop; `best_waiver_move` for the trade finder.

- **IF-3 (matchup evidence and current personnel).** A defense's rank against receivers now comes with the corners it
  was earned with: Compare, the player card / pane (under "Next:") and Matchups' cornerback rows say the history
  (games, period, scoring, not adjusted for the offenses faced), what changed (a regular corner on IR / out per the
  ESPN–Sleeper overlay with its source and date, or no longer on the depth chart; who starts instead, ranked or
  "unranked (insufficient snaps)"), what it means ("the historical rank is less representative this week") and that the
  forecast does not know it ("contextual only; not in the forecast"). A changed defense never breaks a coin flip or
  leans the compare's verdict; `cards.decision_cards` carries `matchup_uncertain` for My Week. No number moved.

- **IF-2: trades compete with the simpler alternatives.** The Trade Finder ranks trades by the starter points they add
  beyond your best waiver move over the same weeks, says it ("+14.6 over weeks 4–7: 1.8 more than your best waiver
  move"), marks the ones that do not beat it ("Below your best waiver move") and keeps a reason only from the numbers;
  the headline is the first card; every card and the calculator show the week-by-week strip for both sides. The
  calculator names its numbers (projected points, starter points, backup coverage, season value above replacement)
  and labels the raw rest-of-season totals "not a fairness test".

- **IF-4 (the decision-quality review § Priority 4).** My Week keeps a close call in view when the lineup already
  follows it — "Tuten or Williams at FLEX: a coin flip, 0.3 points apart; your lineup has Williams — no clear upgrade.
  Compare ›" and "No clear upgrade elsewhere." instead of "nothing to change" —, adds What changed (the injury
  report's moves and the week's news from the last 24 hours, the source and the time on each), names each margin's
  comparator ("over Lloyd" / "no eligible reserve"), shows only the bench in the bench expander and "Updated … ago"
  in the footer; the pane leads with the decision (the week by week, the season numbers, the new schedule table and
  the game log behind expanders); Compare bolds only what bears on the call; "Typical range" everywhere; the role line
  says "not enough games to say" or "role steady over N games"; empty tiles are defined; the news line shows the item
  about him first ("League news" for an article-level headline); the matchup rank in words ("12th-fewest WR points
  allowed"); no "expect him to pick up". No number moved.

## 2026-10-03 — Wave I-E

- **PO (integration).** The trade verdict says what each starting lineup gains and what the season value says —
  never a guess at the other manager's answer ("expect a no" / "worth offering" are gone); the three strongest
  waiver claims are ordered by this week's gain, which they now lead with; when a close call's injury tiebreak keeps
  the healthy player, the lineup table's two rows say so ("Questionable — the call above keeps Addison here for
  now") instead of reading as the opposite; the 70587 e2e answers re-recorded.

- **IE-0: MFL behaves correctly (the casual-user review's P0s).** The trade calculator keeps every asset of a package:
  a provider key such as `mfl:0682` (the Houston Texans QB unit) is opaque from the link to the answer, so the Finder's
  "Houston Texans QB + Tuten for Rice" opens as that two-for-one (it opened as Tuten alone and flipped the verdict); an
  asset that cannot be analysed is named ("Can't analyse …: not on Madeyes Revenge's roster") with no verdict, never
  dropped. Waivers' reasons come from the evaluated move: a candidate fills an empty slot only if he can play it (no
  "team QB fills the empty DEF"), slots in the league's words ("WR/TE 2"). MFL leagues read "MFL", not "Sleeper", show
  no Sleeper market line, and state points per game once with its source; a team unit's badge is its team, never
  "Free agent".

- **IE-2: a trade in starting-lineup words.** The calculator leads with what you give and get, one sentence on the
  effect ("about 3.4 more points this week, about 10 more in total over weeks 4–7"), who starts and who sits by name
  (a starter who only moves from WR/TE 2 to WR/TE 3 is not a change), the backup coverage lost, the other side, and
  standing pat / the best free agent for the same need; the arithmetic is under "How we calculated this". The review's
  metric dictionary (`docs/WORDS.md`), the setup screen with the team picker first and the scoring one status line,
  supporting text at ≥ 4.97:1 in both themes, labels 12 px.

- **IE-1: the weekly action list.** My Week opens with at most three actions, the most urgent first — a change your
  submitted lineup needs before the next kickoff, a close call, a waiver claim that changes this week's starters —
  each in one sentence with the reason under it and the numbers behind "Why?"; calls that share a player are one
  decision ("Keep Addison and Nabers ahead of McConkey for now"); "Your lineup is set — nothing to change" is a whole
  answer; every action says whether it is already in your MFL / Sleeper lineup, with "Open MFL to edit your lineup"
  and the line that League Lab never submits anything. Waivers' cards lead with this week's starter points and say the
  four-week number is a total; the answer, the three strongest and the Help now list no longer repeat one move. The
  trade dial is "Effect on their starters" (no 0–100, no "interest"); the Finder leads with the cheaper package when an
  extra player adds nothing for you. No projection, lineup total or gain changed.

## 2026-10-03 — N2: PlayerWire briefs on the news line

- **N2: PlayerWire first, ESPN fills.** The player card's news line leads with Andrew's own PlayerWire briefs —
  "News · 2 h ago · *Jefferson (ankle) ruled out for Sunday* · Minnesota Vikings via PlayerWire › OFFICIAL" with the
  brief's one-sentence news under it — and ESPN's headlines fill the rest (`kind`, `summary`, `verification`,
  `related` are new keys; N1's four stay). The briefs reach Neon from the Mac every 15 minutes
  (`scripts/playerwire_sync.py`, launchd, role `playerwire_writer`, schema `playerwire`, which the nightly never
  touches); a withdrawn brief loses its text on the next sync. Players are matched by Sleeper / gsis id through
  `player_id_map`; briefs nobody maps to are kept and counted in `/api/status`. `LEAGUE_LAB_PLAYERWIRE=off` hides them.
  Proposed for Andrew: HOSTING.md § 5 becomes "one writer per schema" (`docs/PLAYERWIRE.md`); nothing is installed
  until he says yes.

## 2026-10-03 — Wave I-D

- **PO (integration).** dbt's `assert_projection_ranges_price_the_lines` re-prices `scrubs` only: the dynasty's
  bonuses are priced at their probability under `LEAGUE_LAB_EV_PRICING`, which the SQL macro cannot express
  (`tests/test_projections_ev.py` pins the nightly and the request side equal). The flag stays off until Monday;
  STATUS § "Wave I-D" has the flip's order.

- **M3: the nightly on the scoring spec.** One function prices every projected line, in the nightly and on request
  (`scoring.price_projected`), so turning on expected-value pricing (`LEAGUE_LAB_EV_PRICING`, still off) moves the
  player page, Trends, the record and My Week together. Off, nothing changes; on, the dynasty's yardage and 40+ TD
  bonuses are priced at their chance (top 24 about +0.7 a week, season totals closer at every position), Scrubs is
  unchanged to the bit.

- **IC-4: the team units and the double header, finished.** Rest of season lists dad's league's team QBs and kickers
  (each week priced from that week's starting quarterback or kicker, the bye a week off, the team's badge where the
  face goes) and counts them against the free units in "Value to my lineup"; a unit opens its starter's card; the Team
  Hub names it "Bengals QB"; MFL teams no longer show their name twice as the manager; the League screen lists a
  double-header week's games, counts all-play once a week and the record from both games; Waivers puts the claim that
  fills an empty starting slot first.

- **N1: the news line on the card.** The player page and the research pane show the newest ESPN headline under the
  availability lines — "News · 2 h ago · *Jefferson (ankle) has been ruled out…* · RotoWire via ESPN ›", linked out —
  from ESPN's public player news, read when a card is opened (one player, cached an hour, 15 minutes on game days),
  nothing older than 14 days, nothing of the story kept; `LEAGUE_LAB_NEWS=off` turns it off (`docs/ESPN_TERMS.md`).

## 2026-10-03 — Wave I-C

- **PO (integration).** `fct_player_game` and its league twins carry the 10-yard touchdown cut (`*_tds_10p`), so
  MFL's touchdowns by distance are exact on actual lines without play-by-play on the server; the card's scoring
  read-back names the stat and the position of every rule ("1 pt per 20 passing yards · +10 at 100 rushing (RB) /
  receiving (RB/WR)"); a double-header week names both opponents and both totals on My Week; the MFL note reads the
  spec's words; M2's seed is in dbt. Expected-value pricing is on for MFL leagues and waits, for Sleeper leagues, on
  the nightly pricing with the same engine (v3.1).

- **IC-3: the Leagues card tells the truth.** After a pick, an MFL league's card and every Sleeper league row read
  back the lineup and the scoring League Lab uses, in the league's own words, say what is not priced, and show the
  scoring check; dad's league 70587 is a fixture end to end; the audit of Scrubs and the dynasty: the scoring
  matches Sleeper's to 0.1 (865 / 865 in weeks 1–2), the dynasty's bonuses are what the projections miss.

- **M2: the numbers expected-value pricing needs.** `league_lab.scoring_ev` prices the rules a projected line
  cannot price all or nothing, for example "+10 at 100 yards", TDs paid 6 / 9 / 12 by distance, or "1 point per whole
  10 yards". It has P(yards or catches ≥ any threshold | the projection), fitted on 2019–2025 out-of-sample lines,
  and the share of TDs by distance, measured on every TD play of 2019–2025 (no placeholders). The constants are in
  the module, with the seed `scoring_distributions.csv` proposed. On the dynasty scoring, expected bonuses take the
  top-6 RB / WR miss from +1.3 / +1.7 to +0.3 / +0.7 points a week and make season totals closer at every position.

- **IC-1: a real scoring engine, and the scoring check that proves it.** A league's rules are now data per position
  (`scoring.ScoringSpec`, compiled from Sleeper's settings and MyFantasyLeague's rules: TDs by distance, "1/10" yards,
  flat bonuses at any threshold, FG by distance, team units, premiums; unknown events listed by name). Projections of
  an MFL league price on it (dad's 70587 had priced its TDs and yards at 0); the house leagues' numbers are unchanged
  to the bit. `/api/league/scoring-check` compares our points with the league's own for a played week: Scrubs and the
  dynasty 100% to the tenth in weeks 1–2 (the SQL macro agrees everywhere), 70587 162 / 163 and 156 / 156 within a point.

- **IC-2: slots as eligibility sets, team units as players.** A slot is the set of positions it admits
  (`lineup.Slot(label, type, elig, order)`): Sleeper's names, MyFantasyLeague's combined slots (`WR+TE`, `RB+WR+TE`) and
  team units (`TMQB`, `TMPK`, `TMDEF`) in the league's own words ("WR/TE 1", "team QB"). A rostered MFL team QB / kicker
  is a player with its NFL team, priced from the team's starting quarterback's line / its kicker; Waivers lists the
  unrostered ones. MFL's starters are seated in the slot that admits them (a started TE no longer lands at RB2). A
  player no slot admits reads "No slot for a K in this league", never "Can't play". Dad's league 70587, team 1, week 4
  (fixture): 3 slots and 13.34 before, 8 slots and 38.65 now.

## 2026-10-03 — Wave I-B

- **PO merge.** IB-2's "who starts" reads IB-0's roster context (one overlay pass); the API suite answers MFL from
  fixtures for every test.
- **IB-0: one availability truth.** Every screen now reads a roster's week from one place,
  `availability.roster_context` (the nightly's lineup + the injury overlay, re-solved when a status changed since the
  build): My Week and the opponent's projected total, Waivers (the total, the weakest starter, each move's this-week
  gain and seat, the drop's cost — a player who starts because Jefferson is out is never "would not start"), the Team
  Hub (lineup / bench / horizon values, the closest call, slot strengths, the roster, the league's ranks), the player
  card (its lineup line, and "Justin Jefferson is out (ankle): he starts at FLEX2 this week" in Availability, the
  overlay's injury status) and the trade board (the calculator's "before"). The lineup total is one number: Scrubs
  roster 2 with Jefferson Out read 113.54 on My Week and 117.02 on Waivers and Team; all four screens now read 113.54
  (Test League 95.41, was 123.09 on Waivers / Team). My Week's cards carry `status` (change / set / close, against
  Sleeper's current lineup) and `strength` (clear / lean / coin flip) from `cards.decisions` for the web's card.

- **IB-3: matchup meaning first, "Value to my lineup", the card's default content.** Matchups lead with Favorable /
  Neutral / Difficult (cells, starters, cornerback calls), every rank runs 1 = the toughest for the offense, a corner
  call carries likely / unclear beside it and no shutdown badge (`/api/matchups/*`: `tone`, `tough_rank`, `rank_words`,
  `certainty`, `named_corners`); the Season screen opens on "Value to my lineup" (`/api/ros?view=lineup&team=&who=`:
  what each player adds to, or what you lose without him in, your best lineup over the weeks left, with a sentence);
  My Week's cards: status chip (Change needed / Already set / Close call), the call, the strength, one reason,
  "Compare these players", the numbers behind "Why?". `api/tests/test_ib3.py`, `web/e2e/ib3/`.

- **IB-2: Waivers short, the trade builder with the decision in view.** Waivers opens with the three strongest moves
  (one card each: the claim, the lineup gain over the next 4 weeks, one reason — "Starts at K this week over
  McLaughlin (8.1)", "Fills your empty DEF in week 5, when Kansas City Chiefs is on a bye" — and the claim's cost),
  then one view at a time behind chips: Help now · Bye coverage (the next bye your bench cannot cover) · Stashes · All
  available (`/api/waivers` gains `top3`, `views`, `default_view`; one answer, so a chip switches at once). A claim
  whose drop starts for you this week or next says so and shows the best claim that keeps him ("Or drop
  Croskey-Merritt instead (he sits) and keep Kansas City Chiefs: +9.7 over weeks 4–7"), or that none does. The trade
  calculator leads with the decision: once the dial scrolls away a verdict bar stays pinned at the top (the package,
  the dial's label, your gain; a tap opens it on a phone); the explanation and the lineups are behind "Why?" and
  "Lineups". Trades' suggestions: the package, the dial's label, your gain, one reason, Try it. Names on Waivers and
  Trades open the research pane when it is in the build.

- **IB-1: navigation by task, the research pane everywhere.** Four tabs — My Team (This week · Season · Team · League)
  · Waivers · Trades (Partners · Calculator) · Players (Trends · Matchups · Receivers · Compare · Players) — every path
  kept; a search field in the top bar; About the numbers in the ⋯ menu and at the foot of My Team; the player's page
  keeps the tabs. A player's name on My Week's lineup, in Players' list, in a search hit (and a Trends row on a phone)
  opens his card beside the screen (900 px+) or as a sheet (a phone) with "Compare with my starter" / "Evaluate add /
  drop" / "Add to trade" by where it was opened, and "Full page". Sticky panels stick again (`overflow-x: clip`).

## 2026-10-03 — Wave I-A

- **Nightly: a backup time.** GitHub dropped the 11:37 UTC scheduled run on 2026-10-03 (no run at all); a second cron
  at 13:07 UTC now runs behind a `gate` job that skips when a nightly already succeeded today (`actions: read`).
- **PO merge.** `analytics.mart_market_line` (Sleeper's latest projected line per player-week, league-free; the API
  prices it per league — the trade finder's market rule reads it too); a coin flip reads "A or B — a coin flip";
  About shows "How to read the rankings"; the Decisions tab says "Calculator"; three metric-registry rows.
- **IA-1: say it like a person would.** My Week's cards say why in one sentence under the call — the matchup ("he is
  at home against the Colts, who give up the 2nd-most points to running backs"), his share of his team's carries or
  targets moving, an injury, the betting line — and a coin flip says "Too close to call" and names the tiebreaker;
  "outscores him 51% of the time" and the numbers are the small print (`cards.reason_line`, shared with the console).
  The slot list shows a headshot on every row and short names on a phone ("J. Croskey-Merritt"), under one plain
  header ("Your lineup"). Trends is "Below and above expectation", each row with targets / carries a game (last 3 and
  the season), snaps, expected and actual points and a sentence ("Getting the targets of a 20.0-point player, scoring
  39.4: 4 touchdowns in 2 games on 6 red-zone targets"). Matchups' cornerback section lists receivers only, under a
  real title; Compare says "Choose a player".

- **IA-2: the decisions screens.** The **trade calculator** is its own link (Decisions › Trade calculator, `/trade-calc`):
  tick players both ways and an **interest dial** swings on every change to how much the other team would want it (No
  deal · Maybe · Likely · Hard to say no, "by our numbers over weeks 4–7") with your own gain beside it; the lineups are
  shown once (yours, then theirs under an expander). A **window control** (this week · next 4 · rest of season ·
  playoffs) on the calculator and the partner suggestions says why those weeks; `window=` on `POST
  /api/trades/evaluate` and `/api/trades/partners` (the longer windows extend the board with the rest-of-season board).
  Partner suggestions have a **sanity bound**: none gives away over 25% more rest-of-season points than it brings back,
  or works only because our number for a player you give is under 65% of Sleeper's ("Justin Jefferson for MarShawn
  Lloyd" is refused); what was left out is counted (`rejected`). **Buy low / sell high** moved from Waivers to Trades
  (`GET /api/trades/lists`; no longer in `/api/waivers`).

- **IA-3: the rankings — more to see, and "why this number".** Rest of season shows each player's headshot, bye,
  games left, a floor–ceiling range bar and the stat line a game (QB attempts · yards · TDs · INTs; RB carries · rush
  yards · targets · catches · rec yards · TDs; WR / TE targets · catches · yards · TDs) as sortable columns from 900 px
  and, everywhere, a tap-to-expand row with the pieces and "why this number" (the line × the league's scoring = the
  points a game × games = the total). The player card's Projection gets the same list for this week, the market line
  ("Sleeper has him at 16.2", the gap in words under 70% / over 140%) and the three inputs the model leans on most.
  A "How to read the rankings" paragraph tops the screen. `market_points` on `/api/ros`, `/api/player`, `/api/my-week`
  (null until the proposed `analytics.mart_market_line` is built; `why.py`).

- **M1: are the stars under-projected? No.** Measured out of sample on 2023–2025, player-week by player-week: the top 6 at
  each position land within about a point of their projection in a plain scoring (League of Scrubs: −0.98 QB to
  +0.51 WR, changing sign by season). In the dynasty league's scoring the top 24 RB / WR / TE beat their projection
  by 0.7–1.4 points, about two thirds of it the yardage bonuses (priced all-or-nothing on the projected line). Our
  top 24 sits about 2 points a week under Sleeper's: a level gap, not a star gap. `src/league_lab/calibration.py`
  (the per-row walk-forward, the bias tables, a monotone two-piece map, expected-bonus curves), wired into `project`
  behind `LEAGUE_LAB_PROJECTION_CALIBRATION=1`, **off**: it helps only WR, by trimming the fringe. docs/METRICS.md
  § "Calibration of the top".

## 2026-10-03 — Wave I-0

- **I0-A: who can play, checked every 15 minutes on game days.** My Week no longer starts a player ruled out after the
  nightly build: ESPN's injuries feed (15 min on game days, hourly otherwise) and Sleeper's directory are overlaid at
  request time; the lineup is re-solved and says who moved ("Justin Jefferson is out (ankle) — Michael Wilson starts at
  FLEX2"), the player row shows OUT / DOUBTFUL / IR, and "Injuries checked 2:40 PM" replaces the stale-news warning.
  Trends leave out Out / IR / PUP / suspended players; Waivers never suggest a player who cannot play or two QBs of
  one team; trades count an Out player as 0 this week; rest of season shows the status (`availability.py`).
- **MyFantasyLeague, read-only, on demand (I0-B).** Paste an MFL league link on the Leagues screen, pick your team,
  and the same My Week (and every other screen) runs on it: league keys `mfl:<id>`, `src/league_lab/mfl_client.py`
  (caches by kind, 60 calls a minute, the league's host followed), `platforms.py` (MFL answered in Sleeper's shapes),
  `player_ids.py` (the nflverse id table, downloaded once a day); `GET /api/leagues?mfl=`. League 21861: 216 of 216
  rostered players mapped. docs/ANY_LEAGUE.md § "MyFantasyLeague", docs/MFL_TERMS.md.
- **I0-C: find an MFL league by its name.** The MyFantasyLeague box on the Leagues screen takes a link, an id or the
  league's name as it appears in the MFL app; a name lists this season's matching leagues (at most 25, "MFL · 2026"),
  and tapping one opens the team picker as before. `GET /api/leagues?mfl_search=` (MFL's public league search, cached
  10 minutes; a link or id answers as `?mfl=`), `mfl_client.MFL.league_search`.

## 2026-10-02 — Wave H

- **Hotfix: the nightly on GitHub Actions.** Its first real run (#4, secrets set) failed in `restore-state`: Neon runs
  Postgres 18.6 and the runner installed `postgresql-client-17`, whose `pg_dump` refuses a newer server. The runner's
  service and client are now 18 (`nightly.yml`); HOSTING.md says so and has the row for next time. Run #5 was the
  first green nightly on Actions (23 min; 79 relations verified on the hosted copy): Actions is the writer of Neon.
- **Hotfix: the build context.** `api/Dockerfile.dockerignore` (a pre-Wave H duplicate that BuildKit preferred over
  the root `.dockerignore`) kept `app/pages` out of the image and failed the first Render build; it is deleted, and
  `api/tests/test_build_context.py` keeps the Dockerfile's `COPY` sources and `.dockerignore` in step.
- **One writer, the record kept, the hosted relation audit (H2).** GitHub Actions' nightly is the only writer of the
  hosted copy: off Actions `nightly.sh` skips `sync-hosted` and `sync_to_hosted.sh` refuses (exit 7) unless
  `LEAGUE_LAB_MAC_WRITES_HOSTED=1`, so the Mac's launchd refresh builds only the Mac's database. The NFL-wide boards
  (`ops.projection_lines` / `_ranges`, `ops.kd_lines` / `_ranges`) join the decision record (`RECORD_TABLES`: restored
  hard, saved to the archive); a record table the hosted copy has never had is said so and taken from this database
  or the archive instead of stopping the night. What the hosted copy holds is derived in one place,
  `scripts/hosted_relations.py`, from the Streamlit console AND the product API (`api/`, the `src/league_lab` modules
  it imports): the API's 63 relations verified after every publish; `fct_player_game_league` and
  `mart_player_week_features` join the three-season window and E4's experiment tables stay out — ~200 MB, with a
  480 MB refusal before anything is touched (`docs/HOSTING.md` § 5).

- **The deploy kit (H0).** `docs/DEPLOY.md` walks Andrew through putting the API and the phone app on Render ($7 a
  month, Starter): `render.yaml` (a Blueprint: one Docker web service built from `api/Dockerfile`, health check
  `/api/health`, the two secrets asked for, deployed after GitHub's checks pass), `.github/workflows/image.yml` (every
  push to `main` builds the image, starts it once and pushes `ghcr.io/<owner>/league-lab:<sha>` and `:main`),
  `scripts/smoke.sh <url> [password] [username]` (one line per check, exit 1 on a failure) and `/api/health` now
  answering the version, the database's newest projection fit (`as_of`) and whether the database answers. The image
  was proven stage by stage without Docker and fixed: `app/pages` was missing (Waivers and Trades would have failed on
  the server), it listens on `$PORT` (else 8080), runs as `nobody`, ships no uv / dev dependencies / package test
  suites, and `.dockerignore` keeps `data/` and `.env` out of the build. On the sandbox's copy of Neon, My Week, the
  player card, Matchups, Compare and rest of season fail until the nightly publishes the current tables
  (`docs/STATUS.md` § Wave H, H0 lists them).

- **The gaps Wave G left (H1).** Waivers shows the upside stash (a free agent whose role grew before his points did, with
  the what-if) and buy low / sell high (the Trade Finder's lists, best by position) for any league; About shows what the
  projection leans on most (bars per position) and its grades (this season vs the backtest) from the new `/api/about`;
  rest of season for any league is read in one round of queries and priced in one pass (cold 1.1–1.7 s → 0.25–0.53 s);
  the player search works for any Sleeper league (Sleeper's directory).

## 2026-10-02 — Wave G

- **The research for any league (G1).** Seven API routes serve the research pages as JSON for any Sleeper league —
  `/api/trends` (over- vs under-performing: points vs expected points per game, the trend tags, role alerts),
  `/api/matchups/defense` (points allowed by defense × position: the heatmap's cells, the trend, the defense profile),
  `/api/matchups/cb` (the cornerback lines, the corners, his points vs shutdown corners), `/api/players` (season tables:
  filter, sort, page, search), `/api/receivers` (the Receivers page's window, recent form, first reads, context splits),
  `/api/compare` (two players with the same keys) and `/api/player/{gsis}/games` (the card's chart) — with headshots,
  teams and whose roster on every player row, and every point in the league's own scoring: the league marts for a house
  league, priced on request with `scoring.compute_points` elsewhere (identical to the marts on every 2024–26 game of both
  house leagues); reference-scored fields keep the mart's name + `_ref` (`api/README.md` § Research (G1)).

- **The decisions, on demand (G2).** `/api/waivers` (the claims that improve your lineup, each with its drop, the gains
  and the Waiver Wire's own sentences; the priced free agents), `POST /api/trades/evaluate` (both lineups before / after,
  fit, market, verdict) and `/api/trades/partners` (the partner finder, `want=` a position), `/api/team` (roster value,
  ranks, slot strength, the horizon) and `/api/league` (standings, all-play and luck, transactions) — from the marts for
  the house leagues and computed on request for any Sleeper league (every roster solved; free agents = Sleeper's
  directory minus the rosters; Sleeper's played weeks and transactions), reproducing every mart row to the cent.

- **A design system and the research screens in the app (G3).** Dark first (light from the system), the player card
  as the unit (headshot, a big number, position and team badges), team accents for all 32 teams, one hand-rolled chart
  kit (`docs/DESIGN.md`); one bar with five tabs (a bottom bar on a phone); new Trends (who is due, who is running hot),
  Matchups (defense-vs-position heatmap, cornerbacks), Players, Receivers, Compare, the player card's points-by-week
  chart; "Our record" folded into About the numbers (`/about`); fixture e2e at 390 / 1300 px, light and dark (34 passed).

- **The decision screens (G4).** Waivers, Trade Finder, Team and League in the web app under Decisions, on G2's
  routes and G3's design system: each opens with its answer (the top claim, the best trade partner, your lineup's rank,
  your luck), player cards with headshots, bars against the league (slot strength, the next four weeks, luck, the
  market), a trade evaluated as you tick players (both lineups before / after, the verdict) and shared as a link; free
  agents by position with their range; fixture e2e at 390 / 1300 px, light and dark (18 passed).

## 2026-10-02 — Wave F

- **NFL-wide model outputs (F1).** `league-lab project` fits the ranges per reference scoring (new seed
  `reference_scorings.csv`: `scrubs`, `dynasty`, `ppr`, `standard`, `te_premium`) and writes `ops.projection_lines`,
  `ops.projection_ranges`, `ops.kd_lines`, `ops.kd_ranges` under the B5 freeze; the house leagues' `ops.projections`
  is derived from them (identical numbers, tested); `bonus_rec_te` priced in Python; METRICS § "NFL-wide outputs".

- **The API for any Sleeper league (F3).** `/api/leagues?username=` (a user's leagues and their team in each), the
  week's opponent on `/api/my-week` (Sleeper's matchups; his best lineup solved), the player card and `/api/ros` for any
  league (priced on request; a house league reproduces the marts to the cent), `/api/record`; F1's NFL-wide tables
  read when present (`anyleague.NFL_WIDE`), K / DEF priced in any scoring; the Sleeper client with caches, the player
  directory on disk and a 300-calls-a-minute budget (`docs/SLEEPER_TERMS.md`); JSON errors `{"error": …}`.

- **Web app, phase 1 (F2).** `web/`: sign in with a Sleeper username → the user's leagues this season (own team
  pre-selected, remembered on the phone) → My Week for any league with the week's opponent ("Week 4 vs **X**,
  projects 108 — you project 134"), the player card with the rest-of-season line (sections the API lists in
  `missing` left out and named), new screens Rest of season (`/ros`) and Our record (`/record`); built against the
  Wave F API contract with fixtures (`web/fixtures/`, a fictional any-league "Test League"), Playwright on fixtures at
  390 / 1300 px (14 passed), first content ≈ 0.1 s on fixtures.

## 2026-10-02 — Wave E

- **Model tests (E4), no production change.** Four feature groups through the harness, 2023–2025, both leagues —
  `rookie_prior` (+ `rookie_prior_early`), `oline_quality`, `qb_x_offense`, `player_prior` (the model's own out-of-fold
  miss on the player, `ops.player_prior_oof`, built through a new `build` hook in `experiments.get_group`): all drop at
  every position. Draft capital orders RBs / WRs better in weeks 1–4 only (+0.005–0.008, 3 of 3 seasons); the player's
  past miss works as a linear correction (RB MAE −0.054, WR −0.040, 3 of 3) but not as an input — the PO's v3.1 leads.
  New tables `int_e4_*` (dbt) and `ops.player_prior_oof` / `_pred`; METRICS § "Feature experiments" → "Wave E groups".

- **Rest of season (E2).** `mart_player_ros_projection`: one row per league × player (1,226 rows, ~1.1 MB) — the
  board's `proj_points` summed from `current_week` to the league's final (Scrubs 16, dynasty 17: winners-bracket
  rounds), byes excluded, the playoff subtotal, ranks by position and overall in the league (active NFL roster only),
  an 80% range from the weekly ranges combined as independent normals (stated as the assumption: it understates), the
  week-by-week values. Player card (one line + the week-by-week list), Rankings ("Rest of season" section under the
  weekly board, own position switch incl. K / DEF / All), Trade Finder (the package's totals next to fit and market;
  "Rest of season" and "ROS rank" columns in the market expander). Same totals as the trade engine's market on the same
  weeks (all rows); the market runs to week 18. `app/lib/ros.py`, `tests/test_ros.py`, METRICS § Rest of season.

- **Our record (E1).** `league-lab ingest sleeper-projections` saves Sleeper's own weekly projections as snapshots
  (`raw.sleeper_projections`, archive `data/raw/sleeper/projections/`, nightly `fetch-projections` /
  `replay-projections`); `mart_projection_record` holds the board frozen at kickoff against Sleeper's last
  pre-kickoff snapshot, priced in each league's scoring, and the actual points (Spearman, MAE, top-N hits on the
  players both projected; the cards' start/sit calls: who called it right), week by week and season to date; new
  page "Our record", linked from Rankings. Starts the first week Sleeper is pulled before kickoff.

- **Any league (E3, design + spike).** `docs/ANY_LEAGUE.md`: stat lines stored once NFL-wide, a league's scoring applied per request, lineups solved per request, ranges from the nearest fitted scoring scaled by the price ratio (measured on the two leagues, each rebuilt from the other: mean gap P10 0.19–0.23, P90 0.69–0.84 points; 80% coverage 78.0% vs 79.2% / 78.2% fitted). `src/league_lab/anyleague.py` + `api/league_lab_api/ondemand.py`: `/api/my-week` serves a Sleeper league the database does not have (fixture mode `LEAGUE_LAB_SLEEPER_FIXTURES`); for the two known leagues it reproduces the nightly's lineup exactly (111.46 / 117.02, same slots, values, margins, bench), ~150 ms warm / ~300 ms cold. The API image now carries `src/league_lab` (the cards needed it since D6).

## 2026-10-01 — Projection v3 and the decision ranges

- **Projection v3.0 (D5 + the v3 ship).** Per-position inputs, `projections.FEATURES_BY_POSITION`: QB = v2's inputs + 5
  starting-QB inputs (`pn_qb_starting`, games with this week's QB, points-per-start gap, < 8 career starts, QB
  changed); RB / WR / TE = v2's + 4 teammate inputs (top target / top ball carrier out, share of targets out, live
  absence alert). From `int_player_week_personnel` (new: `int_pn_team_game`, `int_pn_player_game`,
  `int_pn_player_week_status`, `int_pn_window_player`) joined into `mart_player_week_features`
  (`assert_features_never_peek` covers them). Walk-forward 2021–2025, both leagues: QB Spearman 0.538 → 0.582 (better in
  5 of 5 seasons), MAE 7.01 → 6.49, interval score 1.516 → 1.434; RB +0.009, WR +0.005, TE +0.002. `MODEL_VERSION`
  v3.0; v2.0's backtest rows stay (`mart_projection_backtest` gains `model_version` in its grain, `is_current`,
  `coverage_50`, `interval_width_50`, `interval_score`; `ops.projection_backtest` keeps the 50% range's scores from
  v3.0 on); the drift strip compares with the backtest of the model on the board. The scenario refits
  (`signals.py`) and the component importance use the position's inputs; nine plain labels; `pn_qb_starting` is the
  QB model's top input. A projected starter not filled yet (beyond about a week) is the team's last starter. K / DEF
  unchanged (kd1.0). Live boards already frozen keep their v2.0 rows (on the Mac v3 starts at week 5).
- **Ranges and decisions (D6).** A 50% range (`p25` / `p75`, "most weeks") next to the 80% one, both split-conformal
  widened per projection tier (starters' ranges were too narrow: top-N coverage 75.9–77.4% → 78.8–80.5%); decision
  cards lead with "A outscores B x% of the time" (`league_lab.decisions`: the two players' quantiles, a Gaussian
  copula with measured same-game correlations; Brier 0.221 on 5,374 lineup calls of 2024–2025 vs 0.249 for a coin flip).
- **After QA.** A card whose starter projects more but wins less often leads with the recommendation and says both;
  Home's intro moves under My week once a team is picked (the first card is above the fold on a phone); the Player
  page and `/api/player` show the "most weeks" range; the experiment record ships as the seed
  `dbt/seeds/feature_experiments.csv` (unioned into `mart_feature_experiments`), so "What we tried" fills on any build.
- **Feature-group harness (D1) and what it rejected (D2–D5).** `league-lab experiment <group>`: the production model with
  and without a group on 2023–2025, a paired keep / drop rule per position, a no-peek check; results in
  `ops.feature_experiments` / `mart_feature_experiments` and on Rankings → "What we tried". Dropped: game context
  (kickoff, rest, travel, venue), weather (Open-Meteo loader built, `league-lab ingest weather`), team volume and
  style, offensive-line absences, own injury history. The harness's baseline is now the production model (per
  position) and refuses a group whose columns are already inputs.
- **Fixes.** `int_player_game_role` matches teams on one code per franchise (the Raiders 2016–19 and the Chargers 2016
  were missing: 5,264 → 5,344 team-games, role alerts 7,074 → 7,157 under version ra1.2, which recomputes every
  season once). The read-only API (D7) gains `scipy` (the cards' decision probability needs it).

## 2026-09-30 — Wave C (mobile, plain words, kickers and defenses)

- **Matchups: cornerbacks, defense vs position as a picture, two players side by side (R-14, R-15, R-11).** New
  marts `mart_cb_rankings` (every starting corner ranked per season / last 4 games / two seasons on targets per
  coverage snap, yards per target adjusted for the offenses faced and rating allowed: shutdown / solid / target),
  `mart_cb_matchups` (per WR / TE-week: the opponent's corners from its depth chart before kickoff, where his targets
  went, the corner likely across from him — clear or even split — and his history), `mart_receiver_vs_cb` (who was on
  the field for his targets), `mart_defense_position_profile` (opportunity vs efficiency allowed, opponent-adjusted, as
  of each week) and `int_defender_game_coverage_snaps`; `mart_defender_coverage_season` and `mart_matchup_cb_context`
  retired. Matchups below the decision cards: a side-by-side card that opens on the closest call and quotes its margin
  ("The lineup says Gainwell by 0.45; the matchup agrees: his defense gives up the most carries to RBs"), one
  cornerback line per starting receiver, and a heatmap of every defense × position (your opponents pinned and ringed)
  with ranked bars for one position. No projection change; shadow coverage was tested and is not shown (it caught 1
  of 6 well-known 2025 shadow corners).
- **Plain words, and an honest "what drives the projection" (U-14, U-15).** Home is rewritten for a league-mate: a
  three-sentence intro, **Worth a look** (your schedule luck, points left on your bench, the best bargain on your
  roster, the player on it who is most often his quarterback's first look — each a link to the page behind it), the pages listed as the
  questions they answer, and "What's new" in plain words (`app/whats_new.md`) instead of this file. Every page's "How
  to read this" box says what to do with the page in three to five bullets, and the column tooltips lost their jargon
  (`docs/WORDS.md` is the word list). Rankings' "The model" section answers "is this a model you trained?" and the
  importance table now measures the projection itself: the component models (targets, catches, yards, TDs …),
  scrambled one input at a time on the newest training season (2025, scored by a twin fitted on 2016–2024), in
  **points of error added** in the reference scoring, with plain names, top 10 per position (snap share over the
  last 3 games leads for QB and WR, carry share for RB, target share for TE). The old table (price line
  0.017, snap 0.007) was the floor–ceiling model's median, whose main input is the projection; its rows stay in
  `ops.projection_importance` labelled `model = 'quantile_p50'`, off the page. New view `mart_projection_importance`
  (added to the `project` / nightly projection-marts `--select`); written by `league-lab project` after the
  projections, which are byte-identical to before.
- **Trade evaluator and simulator (T-01, T-02).** New `src/league_lab/trades.py` on B1's lineup service:
  `evaluate(board, give, get)` re-solves **both** rosters in every week of the horizon (this week + 3; byes, Out / IR,
  taxi and locks as in `ops.lineups`) and reports each side's lineup value before / after, depth (the bench's own
  lineup), the closest call, who starts and who sits, the roster size — a side over its limit cuts the player whose
  loss over the horizon is smallest (counted in the gain), a side left with an open spot is shown the best free agent
  — and the **market** kept apart from the fit: rest-of-season projected points above the best free agent at the
  position (`REPLACEMENT_SQL`; a kicker is ~0, a one-QB league's QBs are cheap), plus PPG / xPPG / position rank / age
  / NFL season per player. `partners(board, me)` ranks every other roster by its best 1-for-1 and 2-for-1 that raise
  both lineups over the horizon, by the smaller gain: an exact branch and bound on the lineup's submodularity,
  identical to the exhaustive search on both leagues, ~1 s a roster, cached 10 min. **Trade Finder** rewritten
  phone-first: three cards (best partner + package + both gains, your best buy-low by position, your best sell-high),
  **Try a trade** (partner, players both ways; both lineups this week and over four weeks, league rank change on
  lineup / 4 weeks / depth, roster size, the fit line, the market line and a one-sentence verdict), the package in the
  URL (`?partner=&give=&get=`), buy-low / sell-high lists by position and owner. The weekly pack's team brief gains
  "Trade partners" (with the market columns). Definitions: `docs/METRICS.md` § Trades. No new table or mart.
- **Player signals: role alerts, what-if upside, receiver and kicker context (C6: R-10, R-12, U-17).** New
  `src/league_lab/signals.py` (rule `ra1.1`), run by `league-lab project` right after the projections (one import +
  one call) and on its own as `league-lab signals`: a **role alert** is a step change in a QB/RB/WR/TE's snap, route
  (past seasons), target or carry share over his last one to three games, past his usual swing and held in every
  game, with a stated cause — `kind` role_up / role_down / absence_beneficiary (an injured, traded or released
  starter) / depth_move (a benching, a new starter, a depth-chart move: nflverse depth charts from 2025) /
  new_team — evidence before → after, games held and an expiry (a fill-in's alert ends when the starter is back
  on the report). New `intermediate.int_player_game_role`, `ops.player_role_alerts`, view
  `mart_player_role_alerts` (appended to the `project` / nightly projection-marts `--select`). Validated on known
  cases (Chase Brown 2024 wk 9 "Zack Moss out injured", Cedric Tillman 2024 wk 7 "Amari Cooper traded", Drake
  Maye 2024 wk 6 and Jaxson Dart 2025 wk 4 benchings, Rico Dowdle 2025 wk 5, TreVeyon Henderson 2025 wk 9); 43 of
  44 big 2024–25 weeks by established receivers and backs fired nothing; still real three games later: 67% of
  2025's bigger roles and 64% of the smaller ones, as the rule runs in season. **Scenario upside**
  (`ops.player_scenarios`, view `mart_player_scenarios`): the same component models re-price the next weeks with
  his last-3 inputs at the new role's level (capped at the position's 90th percentile), per league, with the
  probability-weighted "with the alert" line; calibrated on 2023–2025 first (`league-lab signals-backtest`): the
  larger role was the nearer number only 46–47% of the time, so it ships as a **what-if** with that hit rate, no
  probability. `ops.projections` is byte-identical with the hook. Waiver Wire's third card region is the
  **upside stash** list (`ops.waiver_upside`, view `mart_waiver_upside`: free agents with a live bigger role who do
  not help at their projection today, valued as it is and if it holds, with the cheapest legal drop). Trends opens
  with "Role alerts this week", the Player card ends with **Signals**; Receivers and Kickers explain why each number
  matters with worked examples and yardsticks from the selected season.

- **Built for your phone.** Open League Lab on a phone and every table shows at most five columns (a new **Phone**
  setting next to Essentials and Everything in the sidebar), and every page starts with its answer — a line or a
  card — with the big tables one tap below. **League Intel is gone: its charts now open the League page** — schedule
  luck, points left on the bench and each week's scoring rank for every team (not just eight), your team marked, under
  one line such as "You've been the unluckiest team by schedule; your bench has left 49 points unstarted". Rankings'
  filters fit in one row (position, week, the rest under "More filters"; injuries are a filter now) and the board is
  five columns: rank, player, opponent, projection and the bad-week-to-good-week range. Matchups sums up the corners
  your receivers face and your best and worst matchups in a line each. Tap a player's name in almost any table —
  Team Hub, Trade Finder, both sides of a waiver claim, League's lineups, moves and draft, Receivers, Players,
  Kickers — to open his card. And every page now agrees on which week "this week" is.
- **Kickers and defenses get real projections.** Each week's kicker is now projected from what his team is
  expected to score, how often it kicks field goals and extra points, the defense it faces, a dome, and his own
  accuracy from each distance; each defense from its sacks and takeaways, the offense it faces and how many points
  it is likely to allow — both priced in League of Scrubs' scoring. Tested on the last five seasons, these ordered
  kickers and defenses better than points per game in every season. Your lineup now uses them (a kicker or defense
  you just picked up is no longer counted as 0), the waiver list now includes free-agent defenses, and the Kickers
  page opens with next week's projections: your kicker, and the best one on waivers.

## 2026-09-30 — Wave B (decision engine)

- **My week, and a card for every player.** Home now opens on your week: your best lineup, and the two or three
  closest calls as plain cards — "RB2: start Kenny Gainwell over Emanuel Wilson, 7.54 vs 7.09 projected, 0.45 apart,
  a coin flip", with each player's opponent and how that defense ranks against the position. It uses the same
  projection as the rest of the league pages, in your league's scoring (the old "Your week" table used a simpler
  formula in League of Scrubs scoring, which is why a player could show 11.5 there and 10.3 on Waiver Wire). The same
  cards sit at the top of Matchups, with the start/sit board one tap below. Tap any player's name in a table — or
  search on the new **Player** page — for one screen on him: how much he is used, this week's projection with a bad
  and a good week, whether he is available (whose team, injury, bye, locked or not) and what he is worth in your
  league, including where he sits in his team's lineup this week.
- Behind the pages, League Lab now works out the **best legal lineup** for every team in both leagues, every
  week: all slots solved together (FLEX and superflex included — a WR who beats your QB2 goes in the superflex),
  byes, Out / Doubtful, IR and taxi left out, Questionable flagged, players whose game has started kept where
  they are. A kicker or defense you just picked up still fills its slot, counted as 0 until Sleeper has scored him
  in your league, and never ahead of anyone with a value; an empty slot now means nobody on the roster can play
  there. Each starter gets a **margin** — how many points the lineup loses without him — so the closest call
  of the week is named. For weeks already played it also computes the best lineup you could have started; it
  matches Sleeper's own max points (weeks 1–2: all 22 teams, to the cent, except one where it is 1 point higher
  by leaving a −1 defense out). No page shows it yet: the start/sit, waiver and roster views are being rebuilt on it.
- **Team Hub, Trade Finder and League Intel now read your real lineup.** Team Hub opens with the answer: your best
  lineup this week and your closest call (e.g. "FLEX, your starter over your best bench player by 0.15"), the next four weeks
  and your depth, each ranked against the league, and how your starters got there; the roster is one table
  (player, slot, value, margin, acquired). **"Acquired" is now right for the dynasty**: it reads every season of the
  league, so a 2023 trade says "Trade 2023 offseason · from <the manager you traded with>", not "Waiver / free agent". Trade Finder lists
  buy-low and sell-high players by position with what each would add to your lineup and cost his owner's, this
  week and over four weeks — a WR who beats your FLEX counts, a third QB behind two starters does not. League Intel
  ranks every team on this week, the next four weeks and depth. The old position-by-position strength bars are gone.
- **What the board said before kickoff is now kept.** From week 4 on, each week's projection v2 board (Rankings)
  is frozen when the week's first game kicks off: later refreshes no longer rewrite it, the page says "the board as
  published before the first kickoff (Thu …)", and the "How the model is doing this season" strip is scored on that
  frozen board. Weeks 1–3 were played before this existed, so their projections are labelled as **refit values**
  (from a later run of the same model), on the board and in the strip. Every page also warns when the injury report
  is stale ("Injury report is from Sat Sep 26, 7:02 AM ET — treat Questionable tags as stale (…)") — when it was
  loaded before the last final game's date or more than 48 hours before the next kickoff.
- Behind the scenes: the nightly data refresh can now run on GitHub's servers (about 7:40 a.m. Eastern) instead of
  Andrew's laptop, so a closed laptop no longer means yesterday's numbers. Same steps, same checks; the banner on every
  page still says when the data was last published.
- The "loaded" line under every page title now shows Eastern time with the label ("**nflverse** loaded Tue Sep 29,
  4:34 PM ET"), like the injury warning below it, and it means when that data arrived from the source: a nightly
  rebuild no longer makes week-old files look like they loaded this morning.
- The live board no longer jitters between refreshes with no news: two fits of the same data now give the same
  numbers (the training rows were read in an unordered scan, which moved the model's internal validation split;
  differences reached 1.5 points on a player).
- **Waiver Wire now answers "who should I claim, and who goes?"** Pick your team and the page opens with the claim
  that improves your lineup most, in one line: "Claim Michael Mayer (TE), drop Dylan Sampson: +1.1 this week at TE,
  +2.4 over the next 4 weeks", with the player he pushes out of your lineup and his projection (the same numbers as
  your lineup elsewhere, no second model). Every free agent is tried against every player you could drop, and your
  whole lineup is rebuilt each time — FLEX and superflex included, byes and the dropped player's own future starts
  counted over four weeks. Then the best **cover** for a coming bye, a **flyer** on someone with no games yet, or a
  plain "Nothing beats what you have". The full ranked list is one tap away; browsing every free agent moved under
  it. The "Adds worth a claim" position-by-position shortlist is gone.

## 2026-09-27 — Your league's scoring on every league page

- Team Hub, Waiver Wire, the Matchups start/sit board, Trade Finder, League Intel and the League page's draft review
  now price every player in **the league you picked**: PPG, PPG over the last 3 and 5 games, xPPG and PPG − xPPG,
  positional strength, roster-value and keeper ranks, draft season points. Until now a second league saw those in
  League of Scrubs scoring — Josh Allen showed 38.2 PPG on the Forever Unclean Dynasty Team Hub; it is 49.6 there
  now, exactly his Sleeper points per game. Nothing changes for League of Scrubs.
- The NFL research pages — Players, Trends, Receivers and defense vs position (with the Opp rank columns built from
  it) — keep one scale for everyone, League of Scrubs scoring, and each now says so. The sidebar notice is down to
  that one line.
- Home's "highest projections" panel is labelled for what it is: the baseline formula in League of Scrubs scoring.
  Projection v2 in your league's scoring is on the Rankings page.
- The sidebar says what kind of league you picked in one line under the league name, on every page
  ("12-team superflex dynasty · full PPR · 6-pt pass TD · yardage bonuses"); the key-by-key scoring differences
  moved into a collapsed "Scoring differences vs the reference league" section, one click away.
- Waiver Wire opens with **Adds worth a claim** for your team: per position your league starts, up to three free
  agents who beat your weakest projected starter this week (projection v2, your league's scoring) or your best
  bench player's PPG, each saying so in words ("+0.3 over your TE1 this week (Proj 7.9 vs 7.6)") with floor and
  ceiling; otherwise "Nothing on the wire beats what you have at RB." The free-agent table now ranks by projection
  v2 for next week by default; every other ranking and filter is still there.
- Rankings (projection v2) has a new strip, **"How the model is doing this season"**: once a week is complete, the live
  board is scored like the backtest — per position, this season's rank correlation and floor–ceiling coverage next
  to the backtest's, with the number of weeks scored. After weeks 1–2 of 2026 RB is at or above its backtest in both
  leagues, WR and QB below (QB 0.43 vs 0.54 in League of Scrubs) — two weeks is a small sample.

## 2026-09-26 — Projection v2

- Rankings now default to **Projection v2**: a projected stat line (targets, receptions, yards, TDs, carries,
  attempts, INTs) per player-week from a gradient-boosted model, priced in **your league's** scoring, with a
  **floor (P10) and ceiling (P90)** calibrated so about 80% of outcomes land inside. The baseline formula stays
  as the check; the backtest section scores both on seasons the model never saw, per league.
- Fixes from the first two-league walkthrough: League and Kickers pages pick the season within the selected
  league; League Intel history is per league; blank cells are blank (not "None"); no kicker options in a league
  without a kicker slot; superflex counts as a second QB starter; dynasty leagues get "roster value" instead of
  "keeper facts"; dates render as dates; Rankings only offers played weeks and the next one.

## 2026-09-26 — Second league

- Several Sleeper leagues at once: `LEAGUE_LAB_SLEEPER_LEAGUE_ID=<id>,<id>`; the first is the
  *reference* league whose scoring prices NFL-wide pages. `?league=<id>` opens the app on a league;
  the sidebar lists where a league's scoring differs from the reference.
- Scoring keys a league might use that were unmapped are now recomputed: yardage-game bonuses
  (`bonus_rec_yd_100` …, exclusive buckets), 40+/50+ yard touchdowns (from play-by-play) and
  distance-bucketed missed field goals. Expected points leave bonuses out on purpose.
- Sleeper's "no previous league" marker (`"0"`) no longer produces a failed partition.
- The league and team you pick now carry across pages (Streamlit drops the URL's `?league=&team=`
  when you switch pages; the choice is remembered for the browser session, and a shared link still
  wins when it carries one).
- A league without kicker slots no longer breaks Trade Finder and League Intel; a table missing
  during a hosted refresh shows a notice instead of a traceback; the Rankings guard no longer
  demands a mart the page does not read.

## 2026-09-26 — Share-ready beta

- Hosted publishing: `make sync-hosted` pushes the marts (never raw data) to a hosted Postgres in one
  atomic transaction; the app reads Streamlit secrets; optional beta password; feedback link.
- Sidebar **Table detail** toggle: *Essentials* hides denominators, noise statistics and fine-grained
  counts on every table; *Everything* shows every column.
- Home is a landing page: your week at a glance, what's new, data sources and licences.
- Rankings (page 4): a transparent weekly projection per position with form / usage / matchup / Vegas /
  home terms and a backtest scoreboard (2023–2025 out of sample).
- Play-by-play layer: first-read target share, routes proxy (TPRR / YPRR), context splits by half,
  score state, down & distance and QB on the play; true dropbacks; red-zone shares.
- Trends (page 3): which usage metrics moved over the last three games beyond a player's own noise;
  momentum; defenses getting softer or stiffer.
