# IN-6 hand-back — the League screen: power rankings and the rest of the season (Wave I-N, 2026-10-06)

**Task**: BRIEF § IN-6 (Andrew: "some power rankings, or, like, rest of season projections"). **Branch** `dev/IN6` from
`main` `967b2d9`. **Definitions**: docs/METRICS.md § "Power rankings and the season outlook" (ol1.0).

## Done / not done (the brief's numbered list)

1. **Power rankings — done.** One stated metric: each team's best lineup's expected points per week over the rest of
   the season (the trade engine's `window_board(ctx, "ros")`: today's rosters, this week on the availability overlay,
   IR / taxi / NFL IR carried out, every later week from the rest-of-season projections; each week re-solved, averaged
   to the league's final). Columns beside it: record, points for + rank, points against, the record-vs-points gap in
   words (≥ 3 places apart: "3–0 on the 7th-most points: a soft schedule so far"), schedule left (opponents' power
   number per game, rank 1 = hardest). **No arrows**: last week's rest-of-season board is not stored (`ops.projections`
   is refit in place; `ops.lineup_record` freezes only each week's own lineup), so last week's ranking cannot be rebuilt
   — `movement: null` and a line on the screen saying why.
2. **The rest of the season — done.** 10,000 seasons, numpy, fixed seed, sync route (thread pool) in the `heavy`
   bucket, `memo` region `outlook` (≤ 48 entries, key = league, house / on demand, build stamp, overlay stamp; TTL 10 min
   house / 2 min on demand). First week left = the week's odds' own pieces over the whole league (one copula, the same
   pairs, the same shrink applied per game); later weeks = the board's lineup totals, spread from each lineup's own
   ranges widened by 1/0.60, plus a 3%-per-week drift (assumed, stated). Outputs: projected record (mean + middle 80%),
   playoff odds (wins, then points for — stated), top seed, bye (2^⌈log₂ spots⌉ − spots top seeds), clinched / out
   proven on wins alone. **No title odds** (bracket not simulated). Providers: Sleeper house + on demand = everything;
   MFL = power + projected record, **no playoff columns** (MFL's export has no playoff team count; the screen says so);
   leagues with divisions = no playoff columns (said); ESPN through the same seam, unverified; Yahoo pending. A league
   with no readable outlook keeps the rankings + one line why.
3. **Assumptions + a check — done.** The screen says once: rosters as today, best lineups, known injuries only, the
   further out the wider; "Context, not a graded forecast"; "No title odds". **Replay** of 2024 + 2025 (both house
   leagues, 44 teams) from weeks 5 / 8 / 11 with what was known then (standings before, rosters that week, each player's
   walk-forward projection that week held flat — the old rest-of-season board is not stored —, byes, K/DEF at their
   ppg, the real pairings; the chain's 2026 cv; no injuries): **Brier 0.179 from week 5** (flat spots/teams 0.245,
   today's standings order 0.273), 0.139 from week 8, 0.089 from week 11. Buckets (132, not independent): 0–10% 3% → 0/22;
   10–30% 21% → 19%; 30–50% 39% → 22%; 50–70% 62% → 80%; 70–90% 79% → 76%; 90–100% 96% → 10/10. The drift (0 / 3 / 6%)
   is invisible in it (0.135 / 0.136 / 0.137). **Self-consistency**: odds sum to the spots, top seed to 1 (tests);
   clinched reads 100%, eliminated 0% (test); **first week vs `/api/league/week-odds`** on both house leagues' week 5:
   worst gap **0.45 pts** (Scrubs, 5 games), **0.62 pts** (dynasty, 6 games); a hand-built league held to 1 pt (test).
   The replay script was QA and is not committed; the method is in METRICS.
4. **The screen — done.** `/league`: "Power rankings" and "Rest of season" are the first two blocks after the screen's
   answer line; a table with the team column fixed and the numbers scrolling inside the card at 375 (no page scroll),
   bars at 1300 (per-week bar, the 10–90% win band with the mean tick, the playoff bar); my team marked (wash + left
   rule + "(you)"); every column header's ⓘ opens its definition (the Metrics tile's tap pattern). Light and dark.
5. **Tests — done.** `api/tests/test_in6.py` (17): certain winner, identical teams (equal within 4 SE, same seed same
   draws), sums to spots / byes, the tie-break, clinched / eliminated, first week vs `lineup_win_probability` (1 pt),
   14 teams under 2 s, the drift widens later weeks, the gap words, `ref:half` → `needs_league` + bucket `heavy`, both
   house leagues end to end, cache keyed by league and build, a missing schedule week (rankings stay, the reason names
   the week), MFL (no playoff odds + reason), the schedule reader (double header, missing week), the house settings from
   the nightly when Sleeper does not answer. METRICS + 3 registry rows (`power_ranking`, `projected_record`,
   `playoff_odds`, ol1.0); WORDS § IN-6; e2e `web/e2e/in6` (6: 375 + 1300, dark + light).

**Not done**: movement arrows (not honestly computable — see 1); title odds (bracket not simulated); ESPN / Yahoo not
exercised (no fixture with a full schedule); the replay is a proxy (flat projections, no injuries, cv borrowed).

## Files

New: `api/league_lab_api/outlook.py`, `api/tests/test_in6.py`, `api/tests/fixtures/make_in6_schedule.py` + 27
**synthetic** `api/tests/fixtures/sleeper/matchups_<league>_<6..14>.json` (a round robin, NOT the leagues' real
schedules — the fixture API can then show the outlook), `web/src/components/league/Outlook.svelte`, `…/league/outlook.ts`,
`web/e2e/in6/fixtures.spec.ts`, `web/fixtures/in6/outlook_*.json` (recorded from the fixture API, timings dropped),
`docs/handbacks/in6/*.png`. Edited (mine): `web/src/routes/League.svelte`, `docs/METRICS.md`,
`dbt/seeds/metric_registry.csv` (seed edit only, no dbt run). **`decisions.py` is not touched** (outlook reads its
`STANDINGS_SQL`, `od_league_marts`, `trade_context`, `window_board`).

**Edits outside my files** (marked `IN-6`): `api/league_lab_api/main.py` (router include after IM-5's block, before the
SPA fallback — it must stay above `api_404`), `api/league_lab_api/ratelimit.py` (`HEAVY_EXACT |= {"/api/league/outlook"}`
after `LEAGUE_SETUP`), `web/src/lib/api.ts` (types + `outlookPath` at the end), `docs/WORDS.md` (section before "Adding to
it"), `CHANGELOG.md` (created `## 2026-10-06 — Wave I-N` above the hotfix, one bullet). Shared fixtures: new files only.

**Interface** `GET /api/league/outlook?league=&team=&source=` → `{league_id, season, version "ol1.0", played_weeks,
roster_id, power: {rows[{roster_id, team_name, manager_name, rank, per_week, wins, losses, ties, standing, points_for,
points_for_rank, points_against, points_against_rank, gap_words, schedule_left, schedule_left_rank, schedule_left_games,
mine}], weeks, span, words, note, movement: null, movement_note}, outlook: {available, reason, weeks, seasons,
playoff_teams, playoff_week_start, byes, tiebreak, playoff_reason, assumptions[4], drift, shrink, first_week[{week, a, b,
p, p_raw}], first_week_number, rows[{roster_id, wins_mean, wins_p10, wins_p90, games_left, wins_left_mean,
points_for_mean, playoff, top_seed, bye, rank_mean, status, mine}]}, definitions{8}, timings_ms}`. `ref:*` → 404
`needs_league`; unknown team → 404; `source` other than `sleeper` → 400.

## Numbers (this box: 2 cores, six devs, load 2–3 while measured)

Simulation alone (10,000 seasons): 12-team house leagues **0.36–0.45 s cold**; a 14-team synthetic league 0.22–0.25 s
(test budget 2 s). Whole answer cold: Scrubs 1.0 s, dynasty 1.7 s, MFL 70587 7.1 s (6.2 s = the on-demand rest-of-season
board, the same the trade screens build and memoize); warm < 1 ms. Answer ~10 KB.

## Commands

`uv run pytest -q api/tests/test_in6.py` (17 passed, 14.5 s) · `api/tests/test_im3.py` (63 passed) ·
`uv run pytest -q tests/test_metric_registry.py` (3 passed) · `uv run ruff check src app tests api` (clean) ·
`scripts/copy_standard.py --check` (clean) · `cd web && npm run lint && npm run build` (clean) ·
`FIXTURES_PORT=8760 npx playwright test --config playwright.fixtures.config.ts e2e/in6` (6 passed); also the League
screens' existing e2e (`e2e/decisions -g "league: luck"`, `e2e/ic4`, `e2e/ih3`: 20 passed — there the outlook call has no
recording and the block shows its 404 line; nothing asserts its absence).

## The PO lines I need

* `app/whats_new.md`: "- **League: power rankings and the rest of the season.** Every team ranked by what its best
  lineup should score per week from here, and the season played out 10,000 times: projected record, playoff odds, top
  seed. Context, not a promise: it says what it assumes."
* docs/STATUS.md / HANDOFF.md: the Wave I-N line (route, region `outlook`, the synthetic schedule fixtures).
* Live check after deploy: `/api/league/outlook?league=1389709692405551104&team=2` — confirms Sleeper's
  `/matchups/<week>` answers future weeks with pairings (assumed, not verifiable here); if a future week comes back
  empty the screen says "the schedule for week N is not available from the league".

## Seen, not mine

* Sandbox: `mart_league_standings` counts 3 games while `fct_league_matchup` has week 4 points, the board's `this_week`
  is 5 and the pinned clock's decision week is 4 — the outlook treats week 4 as the first week (all games in, at their
  points). The on-demand fixture league (last_scored_leg 2, decision week 4) gets "week 3's results are not final yet".
* `platforms.py` MFL: `playoff_teams = min(2**rounds, n)` — for 70587 (4 playoff weeks) that is all 12 teams; any screen
  reading it as a fact is misled (I do not).
* MFL fixture `liveScoring_4.json`: most week-4 starters read as played with 0 points, so `/api/league/week-odds` shows
  several 50% "games" (both sides at 0) — a fixture artifact the outlook reproduces faithfully.

## Fix round (2026-10-06, branch `fix/IN6` from `integ/IN` `cd56421`; the review's M2, L1, the fan-out)

* **M2 — memory and work.** Seasons by size (`seasons_for`: 10,000; 4,500 for 32 × 10 × 11; 2,000 for 32 × 24 × 17;
  never under 1,000; `outlook.seasons` and the screen say the number run). Chunks with tallies (wins histogram in
  halves, place counts, summed points for); the first week drawn in ~64k-number chunks into team totals only; the
  copula rooted per NFL game; one vectorised quantile step per knot set (`ppf_group`, equal to `Predictive.ppf` to
  1e-14). Checks before any draw (teams ≤ 32, weeks ≤ 18, starters ≤ 30 → the reason; the range rule). One simulation
  at a time per process (`_SIM`, 5 s wait, then 429 `busy` in plain words, nothing cached; the screen retries 3 × 3 s).
  Peak MB / s (tracemalloc, load ~0.2), first week + rest: 12×10×11 **7 / 0.20 + 4 / 0.11** (was 37 / 0.16 + 50 / 0.10);
  32×10×11 **7 / 0.30 + 4 / 0.19** (was 100 / 0.52 + 134 / 0.30); 32×24×17 **7 / 0.71 + 4 / 0.17** (was 249 / 1.53 + 208 / 0.44).
* **L1 — the key.** `outlook()` canonicalises with `A.check_id` (= `platforms.check_key`) before `D.house` and the cache
  key; a key naming no league is 404. Test: `%20`-, tab- and newline-padded Scrubs ids → the same answer, one build.
* **Fan-out.** Schedule kept 6 h per league (`memo` region `outlook_schedule`, ≤ 256), read through the provider client
  (the week's odds' matchups cache). Provider calls for a cold Scrubs outlook: 12 (settings + weeks 4–14) before and
  after on the first; a second cold one inside the 6 h: **0** (was 12 once the client's 5-minute matchups cache expired).
* `ratelimit.py`'s comment says what is true (up to 10,000 seasons, fewer in a big league, one at a time).
* Checks: `test_in6.py` 25 passed (8 new); `test_im3.py` 63 passed; ruff, copy standard, lint, build clean; e2e in6 +
  the League specs (ic4, ih3, decisions "league: luck") 24 passed. First week vs `/api/league/week-odds` (week 5): worst
  0.62 pts (Scrubs), 0.82 (dynasty). Chunked vs before on the same inputs and seed: largest playoff change 1.5 pts
  (Scrubs), 1.2 (dynasty), mean wins 0.06, P10/P90 unchanged.
* Seen on `integ/IN`, not mine: the house boards now start at week 4 (span "weeks 4–16"; was 5–16 on `dev/IN6`), so the
  power numbers moved by up to ±2 per week from the merged tree, not from this round; `tests/test_metric_registry.py`
  fails on `mb1.0` (IN-3's METRICS section has no registry row).
