# IO-2 hand-back — the League page: movement, and a link worth sharing (Wave I-O, 2026-10-06)

**Task**: BRIEF § IO-2. **Branch** `dev/IO2` from `main` `cf8e743` (worktree `wt-io2`, database `league_lab_im4`,
schema `outlook` only). Definitions: docs/METRICS.md § "Power rankings and the season outlook" → the IO-2 block;
words: docs/WORDS.md § "The League link and movement (Wave I-O, IO-2)".

## Done / not done (the brief's numbered list)

1. **Keep each week's outlook — done.** `outlook.snapshots` (`scripts/hosted_outlook.sql`, idempotent, applied twice
   to `league_lab_im4` with the pipeline role): per league key, season, week — the power ranking (rank, per-week
   number, team name cut to 40 letters / 80 bytes), the outlook's rows (mean wins, playoff, top seed, title), league name, model version,
   built_at, closes_at (the week's first kickoff from `analytics.dim_game`), kind (house / saved / visitor). `week` =
   the first week the outlook has not seen played (`played_weeks + 1`). Written by `outlook_store.offer` on every
   **whole** build (not the power part): the first build inserts; a later build replaces only while `closes_at > now`
   (checked before queueing **and** in the upsert's `WHERE`, so a row queued before the kickoff and written after it
   cannot replace); after the kickoff nothing is written. Off the critical path: a bounded queue (64) drained by one
   daemon thread through `db.run_rw(purpose="outlook")`; a failure is counted and logged, never raised.
   `LEAGUE_LAB_OUTLOOK_STORE` = `auto` (default: on when the table exists and the app role may select / insert /
   update it; probed once a minute, every ten once it is there) | `off`. **Bounds**: only Sleeper and MyFantasyLeague
   keys (an ESPN / Yahoo / reference key is never stored); a row ≤ 8 KB of JSON (a table CHECK too; the largest league the outlook simulates, 32 teams with the longest names, measures 7.6 KB); house leagues and
   leagues an account has saved (`accounts.user_leagues` × `accounts.leagues`, when those tables are there) always;
   any other league **at most 20 new a day (rolling 24 h) and 200 held** (both checked inside the write's
   transaction); pruning in the SQL file (the nightly runs it): rows built > 140 days ago, and each league's newest 20
   weeks. **Size on Neon**: measured rows — a 12-team league 1,859 bytes of JSON → **1.75 KB on disk**; the cap is
   8 KB of JSON. Worst case (every row at the cap, incompressible): (200 visitor + house + saved leagues) × 20 weeks
   × ~8.3 KB ≈ **33 MB** + 166 KB per house / saved league; typical (12 teams) at the visitor cap ≈ **7 MB**.
2. **Movement — done.** With last week's stored row: `power.rows[].moved` (last week's rank − this week's; ▲ / ▼ /
   – on the screen), `outlook.rows[].playoff_change` (points of percentage; "+6 since last week" under the Playoffs
   number, hidden under 1). A team missing from last week's row gets none. The line under the table: "▲ ▼: places moved
   since the ranking kept before week N." / "Movement shows from next week: this week's ranking is kept." (this week's
   row stored or just queued) / "No movement arrows yet: each week's ranking is kept before its first game, and the
   arrows compare with last week's." (store on, nothing kept) / IN-6's sentence unchanged when the store is off.
   Never an arrow from anything but a stored row (the read is `outlook_store.stored`, at build time).
3. **A link a league-mate can open — done.** **Share** under the League screen's answer (Sleeper and MFL keys only;
   never ESPN / Yahoo / reference): the phone's share sheet on a touch screen, else the clipboard ("Link copied"), else
   the address to copy by hand. The link is `/league?league=<key>` (no team). Opened with no team: the League screen
   (rankings, rest of season, standings…) with nobody marked "(you)" and one strip, "Is this your league?" + a "Pick
   your team" picker → `team` in the URL → the normal app. Every League-screen call answers with no team (`/api/league`,
   `/api/league/week-odds`, `/api/league/outlook` with and without `part`: tested). **A private league's link**: an
   ESPN key is refused to a stranger on `/api/league` and `/api/league/outlook` (404 `espn_league_private`, IK-1's gate,
   before any cache: tested), never gets a Share button (e2e), is never stored, and its preview is the default card even
   when this process holds a card for it (tested). Yahoo: no button, never stored, default card (tested on the
   helpers; its data access is still pending).
4. **The preview card — done.** `main.py`'s SPA fallback (marked IO-2) asks `outlook.shell(index, league)` for
   `/league?league=<key>`: `<title>`/`og:title` "League of Scrubs: power rankings, week 4" and the description
   "1. Run Bijan Run 119.5 (72% playoffs); 2. … 3. …. Points per week each team's best lineup should score over the rest
   of the season, and playoff odds from simulated seasons." — from the last build this process kept (`memo` region
   `outlook_card`, ≤ 512 leagues, ~300 B each, 14 days) or the newest stored row (`outlook_card_db`, ≤ 1,024 hits and
   misses kept 10 min; at most 120 store reads a minute across all links — the shell is not rate limited — past it the
   default card); escaped by `blog.seo_tags`; nothing kept / private / malformed → the default card. A crawler's hit
   never calls a provider and never builds (tested: the fixture client's call count and the outlook cache size
   unchanged across the shell request). **No `/league/card.png`**: no image library is installed in the API
   (no Pillow, no matplotlib, no cairo) and a new dependency is out of scope.
5. **The MFL League screen's first load — done (power rankings 2.6 s, rest of season 3.3 s cold).** See Numbers.
6. **Title odds — done** for Sleeper leagues whose settings describe the bracket (`playoff_teams`,
   `playoff_week_start`, `playoff_round_type`, `playoff_seed_type`; no divisions): the playoff weeks are drawn in the
   same simulated seasons after the regular season's (`season_totals` over regular + playoff weeks, the drift carrying
   on), seeds = the regular season's order (wins, then points for), the top seeds take the byes, a round = the points
   over its weeks, a tie to the higher seed. **The pairing rule, found in the data**: `playoff_seed_type` 1 = re-seeded
   before every round (best seed left v. worst): the house dynasty's 2021, 2022 and 2024 winners brackets
   (`staging.stg_sleeper__brackets` against `mart_league_standings`) pair exactly so where a fixed bracket would not;
   2023 and 2025 fit both. `playoff_seed_type` 0 = a fixed bracket — **assumed** (League of Scrubs' 4-team brackets
   cannot tell them apart). MFL / divisions / a playoff week not projected: no title odds and the reason. Context only:
   not replayed on past seasons (said under the table and in the column's ⓘ).
7. **Tests — done** (`api/tests/test_io2.py`, 14; e2e `web/e2e/io2`, 10 = 5 × phone 375 + desktop 1300).

**Not done / limits**: no PNG card (above). Snapshots are written only when someone opens a league's League screen
between the nightly and the week's first kickoff (the outlook is built on request): a week nobody opens before Thursday
has no row, and the next week shows "No movement arrows yet". The PO can make the house leagues certain (the nightly line
below). The playoff seeding tie-break is ours (wins, then points for), as IN-6's playoff odds; Sleeper's own tie-break was
not read. Title odds and movement are not graded.

## Files

New: `api/league_lab_api/outlook_store.py`, `scripts/hosted_outlook.sql`, `api/tests/test_io2.py`,
`web/e2e/io2/fixtures.spec.ts`, `web/fixtures/io2/outlook_scrubs_{2,guest}{,_power}.json` (recorded from this worktree's
fixture API, timings dropped; their movement was computed by the API from a week-3 row **seeded by hand** — a shuffled
order, every team at 50% — then deleted), `docs/handbacks/io2/*.png` (8: share, guest, movement, power-first × 375 / 1300).
Edited (mine): `api/league_lab_api/outlook.py` (IO-2 blocks: `part=power`, the market-free context, the schedule left
read for the rankings, movement, the snapshot offer, the card, `preview` / `shell`, title odds: `bracket_order`,
`bracket_rounds`, `play_bracket`, `title_bracket`, `simulate(bracket=)`, `_Tally.title`; region `outlook` 48 → 96 answers),
`web/src/routes/League.svelte` (Share, the guest strip, the outlook asked at once), `web/src/components/league/Outlook.svelte`
(power part first, arrows, odds change, the season's pending / error lines, the Title column and sentence),
`web/src/components/league/outlook.ts` (`movedWords`, `movedLabel`, `oddsChange`, `titleWords`).

**Edits outside my files** (marked IO-2): `api/league_lab_api/main.py` — `web(path, request)` takes the request and the
League link's case sits before IN-1's preview (7 lines); `web/src/lib/api.ts` — types + `outlookPowerPath` at the end;
`src/league_lab/anyleague.py` — `unit_lines` makes the stat lines numeric once instead of once per team (the MFL timing
led there; identical numbers: MFL 70587's 12 power numbers equal before / after; root suite: no new failure);
`docs/WORDS.md` (section at the end), `docs/METRICS.md` (a block at the end of IN-6's outlook section),
`CHANGELOG.md` (`## 2026-10-06 — Wave I-O`, created at the top, one bullet). `ratelimit.py` untouched: no new route
(`part` rides on `/api/league/outlook`, already `heavy`; tested). `decisions.py` untouched (the outlook calls
`TradeContext(market=False)` itself).

## Schema in / out

In: `outlook.snapshots` (read: `stored`, `card`; write: `write`), `analytics.dim_game` (first kickoff),
`analytics.dim_league_season` (league name fallback), `accounts.user_leagues` / `accounts.leagues` (saved? — only when
present and readable). Out: `GET /api/league/outlook` gains `league_name`, `week`, `shareable`, `power.kept`,
`power.movement {week, built_at} | null`, `power.rows[].moved`, `outlook.pending` (part=power), `outlook.title`,
`title_reason`, `bracket {rounds, reseed}`, `outlook.rows[].title`, `.playoff_change`, `definitions.title`;
`?part=power` (else 400).

## Numbers (this box: 2 cores, four devs; load given with each)

* **MFL 70587 League screen, cold** (a fresh fixture API each time). Before (main's code, load 0.3): `/api/league`
  1.44 s, then `/api/league/outlook` 10.86 s → everything at **12.3 s** (outlook timings: board 7.9 s = trade context
  with the market 3.7 s + rest-of-season board 2.0 s + first-request warm-up; schedule + rosters 2.3 s; simulation
  0.37 s). After (load 1.5, the screen's order — `/api/league` and `part=power` at once, then the whole answer):
  League answer **0.34 s**, power rankings **2.56 s / 2.57 s**, rest of season **3.30 s / 3.33 s** (two runs). Where it
  went: the market-free context (no free agents, no later weeks priced for season value) 3.7 → 1.2 s; `unit_lines`
  (TMQB over 32 teams × 15 weeks: a column-wise apply per team) — the power part 3.4 → 2.8 s in-process; the outlook no
  longer waits for the League answer; the whole answer after the power part 0.75–0.89 s (the board kept, the first
  week's roster contexts warm).
  **In a real browser** (Chromium on the built app served by the fixture API, a fresh server each run, outside
  requests aborted, load ~1, three runs): the League answer 0.52–0.60 s, the power rankings 2.65–2.75 s, the rest of
  the season 3.34–3.47 s (rendered by 3.73–3.84 s after navigation), this week's odds 3.41–3.55 s — the odds are now
  asked after the season outlook (at most 6 s; at once if the outlook fails): both solve every roster's week and the
  process runs one at a time (with them in parallel the power rankings took ~3.6 s).
* House leagues (whole answer, warm process): Scrubs 0.9 s. Title odds add +0.01–0.04 s to the simulation; peak memory
  unchanged (4.2–4.3 MB with or without the bracket at 12 × 10, 32 × 11 and 32 × 17, tracemalloc). Adding the playoff
  weeks to the draws moved League of Scrubs' playoff chances by ≤ 1.5 points and mean wins by ≤ 0.04 (Monte Carlo);
  the dynasty runs 9,500 seasons (work budget, was 10,000). Title odds sum to 1 (±0.002, rounding).
* Store: 12-team row 1.75 KB on disk; the cap 8 KB JSON; daily cap 20 new visitor leagues, 200 held; worst case ≈ 33 MB.

## Commands and results

`uv run pytest -q api/tests/test_io2.py` **14 passed** (19 s) · last run, everything in: `test_io2.py test_in6.py
test_in1.py test_im3.py` **130 passed** (36.5 s, load ~2.6) · `/home/claude/waveIO/check_root.sh` (src edited):
**1537 passed, 4 failed — all 4 known, no new failure** (116 s, load ~2.5) · `uv run ruff check src app tests api` clean ·
`scripts/copy_standard.py --check` clean · `cd web && npm run lint && npm run build` clean ·
`FIXTURES_PORT=8820 npx playwright test --config playwright.fixtures.config.ts e2e/io2 e2e/in6 e2e/ic4 e2e/ih3`
30 passed; `e2e/decisions -g league` 8 passed; last run (title odds in) `e2e/io2 e2e/in6` 14 passed.

## The public site (for SECURITY_PUBLIC — IO-4's file this wave)

* **A new write path any visitor triggers**: opening a League screen builds the outlook, which offers one row. Bounded:
  one row per league-week (an upsert), Sleeper / MFL keys only (canonical, `platforms.check_key`, and the table's
  CHECK on the key's shape), ≤ 8 KB, 20 new non-kept leagues a day, 200 held, 20 weeks; a bounded queue (64, then
  dropped) and one writer thread; the app role gets SELECT / INSERT / UPDATE on this one table, no DELETE (the owner
  prunes). The route itself is unchanged: `heavy`, one simulation at a time, `needs_league`.
* **The page shell** (not rate limited) reads the store for a League link at most 120 times a minute in all, each key's
  answer (hit or miss) kept 10 minutes in a 1,024-entry region; the value is escaped; a private / malformed key never
  reads anything. No provider call, no simulation (tested on the fixture client's call count).
* **Private leagues**: ESPN / Yahoo keys get no button, no row, no card; their League routes stay behind IK-1's gate
  (tested with the door open).

## What the site does without the schema (rule 10)

`outlook.snapshots` missing (the deploy before the nightly) or `LEAGUE_LAB_OUTLOOK_STORE=off`: the probe says not
ready → no write, no read, no error; the power rankings show IN-6's sentence and no arrows; Share, the guest view, the
power part, title odds and the preview card (from this process's builds) all work. Tested
(`test_without_the_table_the_store_is_off_and_the_outlook_answers_as_before`).

## The PO lines I need

* `scripts/sync_to_hosted.sh`, after the IK-4 block (before `echo "verifying ..."`), in the same shape:
  ```bash
  # ---- IO-2 (Wave I-O): the League outlook's weekly snapshots — docs/handbacks/IO-2.md. The `outlook` schema is never
  # dropped above; scripts/hosted_outlook.sql creates outlook.snapshots if missing, grants the app role SELECT / INSERT /
  # UPDATE on it (its default_transaction_read_only stays on) and prunes rows past 20 weeks. Idempotent, a few ms, its own
  # transaction, the same owner connection. A failure never fails the publish: the arrows stay off until a sync applies it.
  if psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction -f scripts/hosted_outlook.sql; then
    echo "outlook: $(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select count(*) || ' weeks kept (' || count(distinct league_key) || ' leagues), ' || pg_size_pretty(pg_total_relation_size('outlook.snapshots')) from outlook.snapshots" 2>/dev/null || echo '?')"
  else
    echo "WARNING: scripts/hosted_outlook.sql failed: no outlook is kept until a sync applies it (the publish itself is fine)" >&2
  fi
  # ---- end IO-2
  ```
* Optional, `scripts/nightly.sh` at its end (so the house leagues' week is kept even if nobody opens League before
  Thursday; one outlook build each on the live API, which then writes the row):
  `for L in 1389709692405551104 1321941740235550720; do curl -fsS -o /dev/null "https://isuckatfantasy.io/api/league/outlook?league=$L" || true; done`
* `dbt/seeds/metric_registry.csv` (IO-1 owns it this wave — one row to append at merge):
  `title_odds,ol1.0,"simulated seasons in which the team wins the league's playoff bracket (the playoff weeks drawn in the same seasons after the regular season; seeds by wins then points for; top seeds' byes; a round's points decide it, a tie to the higher seed; re-seeded each round when Sleeper's playoff_seed_type is 1)",simulated seasons,league x roster (as of today),available,"Wave I-O, IO-2: outlook.py play_bracket; GET /api/league/outlook outlook.rows[].title; Sleeper leagues whose settings describe the bracket; context, not replayed"`
* `app/whats_new.md`: "- **League: share it, see who moved, and title odds.** A Share button sends your league-mates
  the power rankings and the rest of the season; from next week the rankings show who moved up or down since last
  week; and each team's chance to win the title, from the same simulated seasons."
* `render.yaml`: nothing (`LEAGUE_LAB_OUTLOOK_STORE` defaults to `auto`). `api/Dockerfile`: nothing.

## New env variables / dependencies

`LEAGUE_LAB_OUTLOOK_STORE` (`auto` | `off`; default auto). No new dependency (Python or npm).

## Owned up

* A real-browser check of the MFL screen (after the e2e passed) found an effect loop in my first version of the
  week's-odds gate (the effect read and wrote `odds`: "This screen hit a problem" on a league whose odds answer) — fixed
  (`untrack`) before it was committed; the e2e fixtures never answer the week's odds for that path, the real API does.
* My first ad-hoc timing browser (a scratch script, not committed) loaded the page without aborting outside requests,
  so Chromium tried the page's outside resources (player pictures, analytics) through the sandbox proxy; every one was
  refused (`ERR_TUNNEL_CONNECTION_FAILED`), nothing was reached. The later runs abort every request that is not
  `localhost:8862`.

## Seen, not mine

* The sandbox's week state (IN-6's note) still holds: the house leagues' `played_weeks` is 3 with week 4 played, so
  the snapshot week is 4, whose first kickoff (Thu 2026-10-01) is before the pinned clock — every build here answers
  `kept: "closed"`. On the live site after Tuesday's nightly it is next week's, open until Thursday night.
* `accounts.client_ip` (IM-4) still takes the first `X-Forwarded-For` hop (SECURITY_PUBLIC § 2, Low) — unchanged.
* The writer connection for the store is one more long-lived Neon connection (`application_name=league-lab-outlook`),
  as accounts' and usage's are.
