# IP-4 — the player card (Wave I-P)

**Branch** `dev/IP4` from `main` `e4b5eec`. **Dev**: IP-4. **Database**: `league_lab`, read only (nothing written).

## Task

The player page (`/player/<gsis>`) and the drawer were a stack of text sections. Make them the card Andrew keeps
describing ("player pictures and real charts", "Madden Ultimate Team / franchise — dark, data-dense panels, player
cards"): a head with one headline number, honest ratings, real charts, and every section the card had, reorganised.

## Done (against the brief's list)

1. **The head** (`components/card/CardHead.svelte`, `RangeBar.svelte`; `lib/card.ts` `headRange` / `nextGame` /
   `headValue` / `headNumber` / `statusTone`): his picture on his team's colour (the team `primary` as the photo's
   field, the `accent` as a glow and the card's 6 px edge; no text on team colour), first name / LAST NAME, position and
   team badges, the status chip in the injury's word, "Game started", this week's game, kickoff and the opponent's rank
   vs his position, the depth-chart / whose-team line; **this week's projection as the one headline number** (48 px,
   64 px from 1280 px; the Projection tile's own string, so the head and the tile never disagree on rounding), its range
   bar (low-end · typical · high-end, the numbers printed), and his value in the scoring on screen (browsing: IN-2's
   `ref_value`, "WR1 · +140 over a free WR"; with a league: the Value section's rank and points per game). Every number
   is one the card already carried; the head computes none.
2. **Ratings** — `GET /api/player/{gsis}/ratings?league=` (`api/league_lab_api/ratings.py`; the fixed interface
   `{season, through_week, position, n_ranked, ratings: [{key, label, value, percentile, rating, words}], overall}` plus
   `display`, `n`, `minimum`, `definition`, `lower_is_better`, `population`, `qualified`, `overall_n`, `overall_words`,
   `label`, `how`). Built on the Stats frame: `stats.season_rows` + `stats.aggregate_window` with the **same cache key
   as the Stats table's season window** (no new cache, no new relation, no cache keyed by user text). Rules:
   - population = his position's players this season with QB 50+ dropbacks · RB 20+ touches · WR 15+ targets · TE 10+
     targets (2026 through week 4: 33 QBs, 55 RBs, 71 WRs);
   - a rating also needs the catalogue's own minimum for its column (e.g. EPA per target 20+ targets, yards after
     contact 20+ carries charted by PFR); percentile = (players below + half the ties, himself excluded) / (others
     ranked); rating = round(99 × percentile); "fewer is better" columns (sacks per dropback, interceptions per attempt)
     rank the other way and say so;
   - under a minimum, a missing value or a population of one: `rating: null` and the reason, never a low number;
   - **overall = the plain mean of the ratings shown, shown with 3 or more**, labelled "average of 8"; the panel's first
     line: "Where he ranks this season among receivers with 15+ targets, 0–99. Not a projection.";
   - per position (6–8, a test pins it): **WR / TE** target share, air-yard share, first-read share, red-zone target
     share, snap share, yards per target, EPA per target, catch rate; **RB** carry share, target share, snap share,
     goal-line (inside-5) carry share, yards after contact per carry, rushing success rate, yards per touch; **QB** EPA
     per dropback, dropback success rate, adjusted yards per attempt, CPOE, intended air yards per attempt, carry share,
     sacks per dropback (fewer better), interceptions per attempt (fewer better). K / DEF: no panel; the route answers
     `ratings: []` and the words.
   - NFL-wide: the same in every league and scoring (`league` validated, not used). `research` bucket via the existing
     `/api/player/` prefix (a test asserts it); the id validated by `^00-\d{7}$` (freetrade.py's pattern).
3. **Real charts** (`components/card/WeekChart.svelte` — the chart kit's week chart: categorical axis, rounded bars, a
   band, lines, hollow points for a week with no game; `lib/chart.ts` `bandPath` / `bands`):
   (a) **Points against the projection** (`PointsChart.svelte`): his points as bars against the **projection made before
   each game** as a line with its low-end to high-end band — new `GET /api/player/{gsis}/projections?league=` (house
   league: `mart_player_week_projections`; a reference key: `ops.projection_ranges` when the key prices a stored scoring
   exactly — Half PPR, PPR, Standard; anything else: `weeks: []` + the reason, the bars alone). The answer above it in
   counts ("Above his projection in 1 of 2 games, inside its range in 2 of 2"); the notes say which weeks are the board
   shown before kickoff and which were **rebuilt after kickoff** (2026 weeks 1–3, `frozen_source = 'refit'`).
   (b) **His role by week** (`RoleChart.svelte`): target, carry and snap share as lines from the game log's own columns
   (the request the game log already makes), toggled (`aria-pressed`), the default set by position; IP-3's
   `summary()["role"]` sentence under it when graded (absent: nothing — a test with a hand-built record).
   (c) **Expected against actual**: the existing `GameLog` / `LineChart`, now keyboard-reachable too.
   Every chart: tap / hover a week → the line under the chart says its numbers (the last played week by default);
   the plot is a `role="slider"` (← → Home End; `aria-valuetext` is the week's sentence); "Show the numbers" is the
   table; dark and light from the tokens.
4. **Every section stays** (`lib/card.ts`'s sections, unchanged): the page is the head, then the ratings (5/12, 4/12
   from 1280 px) beside the points chart, then CSS columns (two from 900 px, three from 1280 px): Projection + "Why this
   number", Availability + the news line, the role chart, the game log, Role, Value, Usage, Signals, Schedule, "How to
   read this", the foot. Section tiles two to a row inside a column. The drawer's Overview: the compact head, the
   reason, the actions, the ratings, the points chart, then its sections as before.
5. Performance (numbers below); the ratings and the charts load in a chunk of their own (`card/panels.ts`, `lazy.ts`).
6. Tests and e2e (below).

## Not done / limits

- **Phone: the sections stay open** (not "sections that open"): existing e2e (the root fixtures spec, ia3, if4, il1, n1, …) assert `section-*` visible on the
  page. At 375 the head and the start of the ratings fill the first screen; the first chart is ~1.3 screens down.
- **Kickers and defenses**: no past projections in the chart (their ranges are in `ops.kd_ranges`, not read): the
  bars alone, titled "Points by week". Any league that is not a house league or a stored reference scoring: the same
  (its past boards are not kept; pricing `ops.projection_lines` in its scoring on request is the next step).
- No "schedule ahead" rating: it is not a percentile of a Stats column (the schedule table stays).
- Pictures: the sandbox reaches no picture host, so every screenshot shows `Headshot`'s silhouette on the team field
  (designed for: the card reads as a card without a photo). A real picture is 104 px round in the same place.
- The defense case in the e2e is **hand-built** (the kicker's card with a defense's identity): the API answers no card
  for a defense at all (see "Wrong, not mine").

## Files

New: `api/league_lab_api/ratings.py`, `api/tests/test_ip4.py`, `web/src/components/card/{CardHead,RangeBar,Ratings,
WeekChart,PointsChart,RoleChart}.svelte`, `card/{panels,lazy}.ts`, `web/e2e/ip4/fixtures.spec.ts`,
`web/fixtures/ip4/api_ip4.json` (121 KB, trimmed: game rows to the 11 fields read, the players list to 6 rows),
`docs/handbacks/ip4/*.jpg` (7). Changed (mine): `routes/Player.svelte`, `components/PlayerPane.svelte`,
`LineChart.svelte`, `lib/card.ts`, `lib/chart.ts`, `docs/DESIGN.md` (§ "The player card (Wave I-P, IP-4)").
**Edits outside my files** (marked blocks): `api/league_lab_api/main.py` (the router, before the SPA catch-all, after
IO-1), `api/league_lab_api/ratelimit.py` (a comment: the routes are `research` through the `/api/player/` prefix),
`web/src/lib/api.ts` (types + `cardPaths`, at the end), `docs/WORDS.md` (§ "The player card"), `CHANGELOG.md` (the
Wave I-P heading created, one bullet), `web/e2e/app.spec.ts` (one assertion, on purpose: see below).

## Schema in / out

In: `analytics.fct_player_game`, `mart_player_game_advanced`, `mart_player_ngs_week` (through the Stats frame),
`dim_player`, `mart_player_week_projections`, `ops.projection_ranges`. Out: nothing. **No new relation.** On a
database without anything new: everything works (no new object is read); a copy without `ops.projection_ranges` or
the projections mart gives the bars alone, never a 500.

## Evidence

- `GET /api/player/{gsis}/ratings`: **cold 0.40 s** (first read of the season frame in the process: query 0.15 s +
  aggregate 0.20 s), **warm 0.026 s** (curl, HTTP included). `…/projections`: 8–13 ms (house), 5 ms (reference).
- Page (fixture API, warm, 4 loads each): **the head visible 316–465 ms** (the card's own request dominates), first
  contentful paint 76–248 ms, the points chart 398–605 ms, at 375 and at 1300.
- Bundle: the app chunk **243.40 → 260.90 KB (+17.5 KB; gzip 75.95 → 82.93, +7.0 KB)**; the new lazy `panels`
  chunk 22.0 KB (8.3 KB gzip), loaded with the player page or the first drawer.
- Tests: `api/tests/test_ip4.py` **20 passed** (percentiles on hand-built frames, ties, lower-is-better, a population
  of one, the minimum sample, a column's own minimum, a missing value, a player with no games, the overall's 3-rating
  rule, 6–8 catalogue columns per position, formats, the bucket, bad ids / league / season, the routes on the
  database). With `test_im3`, `test_im4`, `test_h0`, `test_auth` (modules touched: the router, ratelimit): **117
  passed**. `ruff check src app tests api` clean; `npm run lint && npm run build` clean; `copy_standard.py --check`
  clean.
- e2e `e2e/ip4` (FIXTURES_PORT=8940): **16 passed** (8 × phone at 375, desktop at 1300): WR (Puka Nacua), RB (Breece
  Hall, Out), QB (Lamar Jackson), a rookie with two games (Colbie Young: one reason line, every rating a dash, "no
  average yet"), a kicker (Brandon Aubrey) and a defense (no ratings, the card stands), the drawer, the record's role
  sentence; tap, keyboard and "Show the numbers" on the charts; no sideways scroll; at 1300 the ratings and the chart
  side by side. Recorded with `IP4_LIVE=http://localhost:8964`.
- Existing e2e that read the card, the pane or the player page (fixtures.spec, ia3, ib1, if3, if4, ig1, ig2, ii2, ii3,
  ii6, il1, il5, im2, im3, im5, in1, in2, inf1, io3, n1, n2): **86 + 142 passed, 14 skipped** (their existing skips).
  io3's "a 429 too_fast is waited out" failed once while three suites shared the box and passed on the rerun (blog
  editor timing; not the card).
- **Changed on purpose**: `web/e2e/app.spec.ts` (the live-API spec, not run here): "the projection starts in the top
  half" now reads the head's `card-number` (the projection is the head's number; the Projection section follows the
  ratings and the first chart).
- Screenshots (`docs/handbacks/ip4/`, JPEG q70, 47–160 KB each, 752 KB in all): `ip4-wr-1300-dark`,
  `ip4-qb-1300-light`, `ip4-k-1300-dark`, `ip4-pane-1300-light` (the drawer alone), `ip4-wr-375-dark`,
  `ip4-rb-375-light`, `ip4-rookie-375-dark`.
- Branch size: 1,926 lines added (228 KB of text, 121 KB of it the e2e recording); binaries 7 JPEGs 752 KB (+ one
  earlier version of `ip4-k-1300-dark.jpg`, 66 KB, in history) — under 1 MB generated in all.

## PO lines

- `app/whats_new.md` (yours), suggested: "**The player card.** Every player's page leads with a card: his picture on
  his team's colour, this week's projection and its range, his value in your scoring, ratings that say where he ranks
  this season among players at his position (0–99, from his own numbers — not a projection), and charts of his points
  against the projection made before each game and of his role by week."
- `docs/STATUS.md` / `HANDOFF.md`: this file.
- Nothing for the nightly, the Dockerfile, render.yaml or the workflows. No new env variables. No new dependencies.

## Wrong, not mine

1. **A defense has no card**: `GET /api/player/DEN?league=…` answers 404 "No player with id `DEN`" in a house league
   and on `ref:half`, while `/api/search` returns `{"gsis_id": "DEN", "player_name": "Denver Broncos"}` — a defense
   picked in search opens an error page.
2. **One rounding, two answers**: the API formats with Python (`f"{8.25:.1f}"` → "8.2"), the web with `toFixed`
   ("8.3"); on Brandon Aubrey's card the old head said 8.3 above a tile saying 8.2. The head now uses the tile's string;
   other screens that print `fmt.pts(proj_points)` beside an API string can still differ by 0.1.
3. Running the existing e2e rewrites committed PNGs under `docs/handbacks/in1/` and `docs/handbacks/io3/` (those specs
   write their screenshots into docs by default): a `git add -A` after a test run would commit them.

## Next

Past projections for kickers / defenses (`ops.kd_ranges`) and for any league priced on request; a rating's trend
(this season's percentile against last season's, same rule); real pictures checked on the live site at both widths.
