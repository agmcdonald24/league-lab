# IN-3 — matchups for everyone: the board, with search (Wave I-N, 2026-10-06)

**Task**: Wave I-N package IN-3 (`/home/claude/waveIN/BRIEF.md` § "IN-3"). **Branch** `dev/IN3` from `main` `967b2d9`.
Andrew, 09:19 ET: "even with, like, the no league, the matchups. We could either do, like, a search for a player kind
of thing, or just start laying them out, like each player by player with what the matchups are, at least for
receivers" — and, for DFS, "if somebody's going against a shutdown corner, that could be maybe taken into
consideration".

## Done, against the numbered list

1. **The board** (`/matchups`): every player at a position with a game this week, player by player — WR (default),
   TE, RB, QB. A row: the player (headshot, team, injury status), the game (vs / at, kickoff in ET), the projection
   and its range in the chosen scoring, the defense against his position (tone chip + "gives up the 7th-most to
   WRs"), for a WR the corner call ("McDuffie #3 of 74" likely · "Woolen #8 or Mitchell #9" unclear · "No call", the
   certainty, **Shutdown corner** when every named corner is one), and the one matchup tone. Search (server-side `q=`,
   2–40 characters, debounced, in the URL), filter by game and by tone (with counts), sort by projection / best
   matchup / easiest corner (WR), paged 25 at a time (Previous / Next, "Showing 1–25 of 219 wide receivers"). A row
   opens the sentence, the named corners, the certainty in words, his history against the likely corner, and the
   matchup evidence (`MatchupEvidence`, IF-3's object — nothing new invented), plus a link that opens the player's
   drawer. With a league and a team: **My players · Everyone** (default My players = the screen as before; Everyone =
   the board + who has him). Browsing (`ref:*`, or a league with no team) shows the board alone; the defense heatmap
   stays under it. `/matchups` with no league at all opens on `ref:half` (as `/dfs` does).
2. **`matchup_context(season, week, gsis_ids=None)`** and **`GET /api/matchups/board`** — exactly the brief's
   interface (`api/league_lab_api/matchup_board.py`; first working version committed at 09:50 ET, `376f905`).
   docs/INTERFACES.md § IN-3 has both shapes and how to import it lazily.
3. **Honesty.** Read from `src/league_lab/projections.py` `BASE_FEATURES`: the defense against the position **is**
   an input (`opp_allowed_std`, `opp_allowed_l4`, `opp_rank_std`, `f_opp_allowed_diff`, `league_allowed_avg`, as of the
   week from `mart_defense_vs_position`) and so are the betting lines; **who plays cornerback is not**. The corner calls
   are not graded as a forecast: the only check is METRICS § Cornerback matchups' 2025 check of the *lean* (the named
   corner drew 0.204 of his targets on a clear call vs 0.141 for the other outside corner). The screen says it twice in
   two sizes: under the controls "Projected points in Half PPR scoring. The defense is in the projection; the corner
   is not (context only)." and under the board the full sentence + the tone rule. `test_in3.py` parses the feature
   list: a corner input added to the projection fails it.
4. **Speed, tests, e2e, docs** — below.

**Beyond the list (small, conservative)**: a corner the call names who is **not expected to play** (the availability
overlay through `cards.corner_personnel`, the evidence's own read: listed on the depth chart, not expected) makes the
read "no call" — the context never says "faces a shutdown corner" about a corner who is out. The evidence is kept per
week for every league (it is league-free), so a warm board is 15–25 ms.

## How the single tone is formed (`matchup_board.combine_tone`)

The defense's tone (IB-3's cut: 10 of 32 at each end, `mart_defense_vs_position_current`, one scale for every league)
is the base. The corner moves it **only on a likely call** (his located targets lean 15+ points to one side):

| defense \ likely corner | favorable (target) | neutral (solid) | difficult (shutdown) | unclear / no call / unranked |
|---|---|---|---|---|
| favorable | favorable | favorable | **neutral** | favorable |
| neutral | **favorable** | neutral | **difficult** | neutral |
| difficult | **neutral** | difficult | difficult | difficult |
| none | none | none | none | none |

An unclear call never moves it (tested over every combination); a solid or unranked corner never moves it; no
defense read → no tone ("No read": unknown is not neutral). Coverage shows how rarely the corner moves it (below).

## Files

* New: `api/league_lab_api/matchup_board.py`, `api/tests/test_in3.py`, `web/src/components/matchups/Board.svelte`,
  `web/src/components/matchups/ToneChip.svelte`, `web/e2e/in3/fixtures.spec.ts`, `web/fixtures/in3/api_in3.json`
  (recorded from the fixture API, 527 KB), `docs/INTERFACES.md`, `docs/handbacks/IN-3.md`, `docs/handbacks/in3/*.png`.
* Mine, edited: `web/src/routes/Matchups.svelte` (the switch, the board, "per game", the scoring words for a reference
  key: "Half PPR", never a league name it does not have). `research.py`, `MatchupEvidence.svelte`, `Heatmap.svelte`:
  unchanged.
* **Edits outside my files** (marked `---- IN-3` blocks): `api/league_lab_api/main.py` (the router, after IM-5's),
  `api/league_lab_api/ratelimit.py` (`bucket_for`: `/api/matchups/board` → `research`), `web/src/lib/api.ts` (types +
  `boardPath`, at the end), `web/src/App.svelte` (`/matchups` without a league → `ref:half`, after the PO's `/dfs`
  effect), `docs/WORDS.md` (§ "Matchups for everyone"), `docs/METRICS.md` (§ "Matchups for everyone", before "Value to
  my lineup"), `CHANGELOG.md` (the `## 2026-10-06 — Wave I-N` heading created at the top, one bullet).
* No new env variable, no new dependency, no relation, nothing written to the database.

## Schema

In: `mart_player_week_projections` (the week's players and team), `dim_game`, `mart_defense_vs_position_current`,
`mart_cb_matchups` + `mart_cb_rankings` (through `research.cb_meaning`), `cards.corner_personnel`'s reads, the
league's projections (`research.projections`), `dim_player`, the ownership reads of `research.rostered`.
Out: `matchup_context` → `{gsis_id: {opponent, home, defense{tone, tough_rank, n_ranked, words}, cb{tone, certainty,
corner, corner_rank, shutdown, words} | None, tone, words}}`; the board → INTERFACES.md § IN-3. Memory: one region
`matchup_board` (≤ 24 entries, 10 min): the week's context, one frame per league scoring, the corners, the evidence.

## Evidence (the numbers)

* **Tests**: `api/tests/test_in3.py` **54 passed** (~3 s): the tone table (42 cases) and "unclear never moves it",
  the projection's feature list, the bucket, `matchup_context` with a missing mart → `{}`, never raises (a dead
  database, a bad season), the shape and the tone rule on every player of week 4, the copy is the reader's own; the
  board on `ref:half` (non-empty, sorted, **no ownership field at any depth**, TE has no corner), on League of Scrubs
  (ownership present), `q=` as text (`%%`, `%a%`, `a_`, `__`, `'; drop table x; --`, `\\`, `a%`, `*?`, `12`,
  `<script>` → 200 with 0 rows; 1 and 41 characters → 400), paging (5 + 5 = 10, far offset empty; limit 0 / 101,
  offset −1 / 5,001, position K, a bad tone / sort / game → 400 / 422; `ref:nope` → 404), filters and sorts (game,
  each tone = its count, tone order, corner order with unranked last), a corner who is out → no call.
  `api/tests/test_im3.py` (ratelimit's tests) **63 passed**. `ruff check src app tests api` clean.
  `scripts/copy_standard.py --check` clean. `npm run lint && npm run build` clean (179 files, 0 errors).
* **e2e** `web/e2e/in3` **6 passed** on the recordings (phone at 375, desktop at 1300): browsing — 25 rows, the
  honest lines, no switch, never "No league" / "rostered by" / "Free agent", no sideways scroll, the board wider than
  900 px at 1300; search "Nacua" → one row → the evidence ("not in the forecast") → the drawer link; `/matchups` with
  no league → `ref:half`; a league — My players (the cornerback section) → Everyone → "Who has him" → tone filter →
  back to My players. Also run against the live fixture API (`IN3_LIVE=http://localhost:8763`, which recorded the
  answers): 4 passed. The existing Matchups e2e (`fixtures.spec.ts`, `ia1`, `ib3`, `ii2`, filtered on "Matchups"):
  **10 passed**. Screenshots: `docs/handbacks/in3/` (board, evidence, everyone — phone and desktop).
* **Timings** (the fixture API over HTTP on this box, six devs on two cores; WR, `ref:half`): **cold 0.59–0.64 s** (a
  fresh process), **warm 15–19 ms** (target 150 ms / 1.5 s); League of Scrubs 58 ms first / 22 ms warm; `q=chase` 10 ms; `limit=100` 0.16–0.20 s the first time, 25 ms warm. `matchup_context(2026, 4)`: 172 ms cold,
  6 ms warm (792 players). Answer sizes: 115 KB raw / ~12 KB gzipped for 25 rows (the evidence is most of it).
  Memory: the region held **4.2 MB** after every position of five leagues was paged through.
* **Coverage** (`ref:half`, this database): **week 4** (the pinned decision week) — 219 WRs with a projection and a
  game: **36 likely, 96 unclear, 87 no call** (all "too few targets with a direction to tell his side"); 14 face only
  shutdown corners (7 on a likely call); the corner moved the tone for **6**; of the 41 projected 8+ points, 6 likely
  and 35 unclear. **Week 5**: 207 — 43 likely, 90 unclear, 74 no call; the corner moved 9. Tones at WR, week 4: 69
  favorable, 81 neutral, 69 difficult.

## Limitations (said straight)

* The corner read is mostly "unclear" for the receivers people start (35 of 41 at 8+ points): good receivers move
  around and public data has no alignment. So the corner rarely moves the tone; DFS will mostly see the defense's read.
* A receiver facing two shutdown corners on an **unclear** call shows "Shutdown corner" beside a tone the corner did not
  move (the brief's rule: an unclear call never moves the tone). The row's words say "either … could be across from him".
* The defense read is the reference mart's (Half PPR points allowed, one scale) on every league, as the interface
  says; the heatmap under the board ranks in the league's own scoring, so a house league can differ by a place or two.
* "Not expected to play" depends on the availability overlay (off on the fixture API: nothing in this sandbox was
  marked out); with it on, a status update reaches the board within the region's 10 minutes.
* Rows include games already kicked off in the decision week (the pinned Saturday has Thursday's game played), as
  every other screen does; no lock mark.
* Corner calls are not graded as a forecast (no backtest of tone against points) — a candidate for the next wave.

## The PO lines I need

None are required: no Dockerfile, render, workflow or nightly change. Suggested, optional:
* `app/whats_new.md` (newest on top): "**Matchups for everyone**: every receiver's matchup this week, player by
  player — the defense against his position and the cornerback likely across from him — with a search. Open your
  league for 'Everyone' with who has him."
* `docs/SECURITY_PUBLIC.md` § 1's table lists the research routes in the `read` bucket (stale since IM-3's fix
  round): add `/api/matchups/board` beside `/matchups/*` under `research`.
* STATUS / HANDOFF: the hand-back above.

## Seen, not mine

* The TopBar still reads "No league · Half PPR", and every research answer's `league_name` for a reference key is
  "No league · Half PPR" (`refleague.league`): IN-2's (the board's screen never shows `league_name`).
* `docs/INTERFACES.md` did not exist on `main`; created here with § IN-3 only.
* Matchups' heatmap caption said "Points each defense gives up a game to each position" (the copy standard's "per
  game"; the checker did not catch it in Svelte text) — fixed in my file.

## Commands

`OMP_NUM_THREADS=1 uv run pytest tests/test_in3.py tests/test_im3.py -q` (api/) · `uv run ruff check src app tests
api` · `uv run python scripts/copy_standard.py --check` · `npm run lint && npm run build` (web/) ·
`FIXTURES_PORT=8730 SHOTS_IN3=../docs/handbacks/in3 npx playwright test --config playwright.fixtures.config.ts e2e/in3`
· re-record: the fixture API on 8763 serving `web/dist`, then `IN3_LIVE=http://localhost:8763 … e2e/in3`.

## Next

Grade the corner: replay 2025 with as-of calls and ask whether a likely shutdown corner moves a receiver's points
against his projection (by certainty); only then may the corner enter the projection or a DFS ranking.
