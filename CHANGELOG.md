# Changelog

Newest first. Home's "What's new" is `app/whats_new.md`, the same releases in plain words (docs/WORDS.md).

## 2026-10-04 — the product is isuckatfantasy

- **Renamed.** Everything a manager sees — the sign-in screen, the top bar, the home-screen icon and its mark ("isaf"),
  the page title, the manifest, every sentence that named the app ("isuckatfantasy never changes your lineup or
  claims…") — now says isuckatfantasy (`web/src/lib/brand.ts`, `api/league_lab_api/settings.py:APP_NAME`). The
  codebase, the package, the environment variables, the roles, the repository, the Render service and the research
  console keep the name League Lab. The domain follows (Andrew).

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

## 2026-09-30 — Wave C (mobile, plain words, kickers and defenses)

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
