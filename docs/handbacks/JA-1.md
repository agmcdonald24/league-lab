# JA-1 — Stats: the weeks you choose, one stretch against another, and a stat week by week (Wave J-A)

**Start 00:36 ET, Monday 2026-10-12 (read from `date`); end 01:12.** Branch `dev/JA1` (from `main` `03bc1af`),
`/home/claude/wt-iq4`, database `league_lab_iq4`.

## 1. Done / not done / cut

* **Done — 1. The slider** (`web/src/components/stretch/WeekSlider.svelte`; URL keys in `web/src/lib/stretch.ts`:
  `window` = season | last3 | last5 | last3w | last5w | weeks, `weeks` = A "3-4", `vs` = B "1-2"; the parent writes
  what `onchange` hands it, `readStretch(params)` reads them — JA-2 reuses both as they are). One track of the played
  weeks, two labelled `input type="range"` handles (drag, arrow keys, `aria-valuetext` "Week 3"), the week numbers as
  buttons (a tap moves the nearer handle), one handle on the other = one week, the choice in words ("Weeks 3–4 · 2
  weeks"), quick picks Season · Last 3 weeks · Last 5 weeks · This week · Last 3 games · Last 5 games (one row on a
  phone). It replaces the week-range select; on a phone it sits outside the Filters fold whenever it is not the season.
* **Done — 2. Compare with other weeks**: B on its own lane of the same track (hatched fill, square handles; A round
  and solid — colour is not the only carrier); presets "The weeks before" and "The rest of the season"; under each
  value the change from B (a share in points of share), ± buttons sort by the change; a change on one game or a small
  sample on either side is greyed with its sizes; under G "B: 2"; the headline "Biggest rise in target share, weeks
  3–4 against weeks 1–2: …". Not compared (says why): the role changes, the value column.
* **Done — 3. By week** (`view=byweek&stat=<column>`): W1 … Wn, the stretch's value (Season / Stretch) and a trend mark
  (▲ ▼ –: the sign of a line through his weeks); sortable by any week; a bye or a missed game is a dash with its reason.
* **Done — 4. The API**: `/api/players?…&vs=1-2&by=<column>` — one call, validated (`weeks` / `vs` within the played
  weeks, a range like 1-2; `by` one available catalogue column for the positions, not a role change; `limit` ≤ 1000 as
  before), the windows cached as before (`stats_agg`), the by-week grid in a new region `stats_byweek` (≤ 24 × ~60 KB);
  `research` bucket. The CSV carries A, B and the change per column and names the weeks, B and the situation.
* **Done — 5.** Tests, WORDS, How to read this, METRICS § "Stretches of weeks", DEPLOY's region line, CHANGELOG.
* **Not done**: the browser-built CSV of the By week view is the screen's grid (the server's CSV has no by-week form);
  the phone's first screen with a stretch in force carries the slider (about 300 px) above the table.

## 2. Commits

`1d9e9af` (4, the API) · `3bce0e2` (1) · `51f5637` (2) · `52674f5` (3) · `e11a11c`, `f39ec4b`, `0118e1a` (5) · this file.

## 3. Evidence (League of Scrubs, `league_lab_iq4`, fixture API; weeks 3–4 against weeks 1–2; two games each side)

* **Target share, biggest rises** (RB / WR / TE, ≥ 8 targets in the four weeks): Aaron Jones MIN 2.4% → 24.1%,
  Jakobi Meyers JAX 6.1% → 24.0%, Brenton Strange JAX 10.2% → 26.0%, Kenyon Sadiq NYJ 10.2% → 23.5%, Chris Bell MIA
  6.0% → 19.2%. **Biggest falls**: Parker Washington JAX 36.7% → 16.0%, Kenneth Walker III KC 23.5% → 6.0%, Brian
  Thomas Jr. JAX 22.4% → 6.0%, Dalton Kincaid BUF 25.0% → 8.9%, Dalton Schultz HOU 25.3% → 9.8% (132 players compared).
* **Carries (totals over the two weeks), rises**: Kyle Monangai CHI 20 → 40, Chuba Hubbard CAR 22 → 39, Jeremiyah Love
  ARI 20 → 35, Javonte Williams DAL 24 → 38, Jaylen Warren PIT 21 → 34. **Falls**: Chase Brown CIN 36 → 22, Tyler
  Allgeier ARI 22 → 10, Blake Corum LA 22 → 11, Kaelon Black SF 21 → 10, Omarion Hampton LAC 35 → 24 (55 RBs).
* **The arithmetic**: a constructed receiver with 1 of 2 team targets (week 1) and 9 of 30 (week 2) reads **31.3%**
  (10 / 32) over the stretch, not 40% (the mean of 50% and 30%); his by-week cells are 50.0% and 30.0%, week 3 a dash
  ("bye" / "did not play"), trend ▼ (`test_ja1`). On the copy, every B target share checked equals Σ targets / Σ team
  targets over his weeks 1–2 games (≥ 10 players).
* **Cost of the heaviest call** (all positions, two stretches, a situation, by week): 0.83 s with both windows new
  (the season frame loaded), 0.27–0.5 s warm; ~2.0 MB (2.4 MB with the season as A). A plain stretch: 0.15 s, 1.9 MB.
* **Before → after on screen**: a select "Week range (calendar)" + two week selects inside the phone's fold → the
  slider (screens `docs/handbacks/ja1/`: `ja1-slider-open-375/1300`, `ja1-slider-closed-375` (Filters closed, the
  slider and the table showing), `ja1-a-against-b-375/1300`, `ja1-by-week-375/1300`). No sideways scroll at 375.

## 4. Tests

* New: `api/tests/test_ja1.py` **12 passed** (the constructed player, the trend, B beside A against the copy, seven
  validation cases, by week against the game rows, the CSV and its name). `web/e2e/ja1` **6 passed** (phone and
  desktop: the slider by keyboard, quick picks, a tap on a week, the URL round trip, folded only for the season; A
  against B, sort by the change, the presets, the headline; by week with a dash's reason and a sort by week).
* API files of the changed modules and routes (`check_api.sh`: ja1, ix3, im1, ii3, il1, in2, im3, io4, ip3, ix1,
  research, i0b, il4, ip4, parity): **305 passed, 2 failed, 2 skipped; 0 new** (`test_research::test_trends_route` ×2,
  known).
* e2e that open Stats, both projects: ja1, ix3, im2, ii3, il1, in2, ip3, io4, ib1 → **88 passed**; ip4, im3, ii6, in1,
  ii2, `fixtures.spec.ts` → **103 passed, 7 skipped**. **Updated on purpose**: `ii3` (the window select → the slider's
  quick picks), `ix3` (the Filters label no longer names the weeks; `stats-weeks` folded for the season).
* Ruff, the copy standard, `npm run lint` (eslint + svelte-check + tsc): clean; the build. `scripts/gate.sh`: see the
  final message.

## 5. Edits outside my files

`api/league_lab_api/research.py` (`stats_frame`: `vs`, `by`, the validation, STATS_HOWTO's new bullet),
`api/league_lab_api/main.py` (the two Stats routes pass `vs`; `/api/players` passes `by`), `stats.py` (the JA-1 block,
the CSV), `web/src/routes/Players.svelte`, `web/src/components/stats/StatsTable.svelte` (the change line, the ± sort),
`columns.ts` (`change`, the trend mark, a row's own reason), `web/src/lib/api.ts` (types, end), `web/src/lib/prefs.ts`
(+ byweek), `web/e2e/ii3`, `ix3`, docs WORDS / METRICS / DEPLOY, CHANGELOG. New: `WeekSlider.svelte`, `lib/stretch.ts`,
`api/tests/test_ja1.py`, `web/e2e/ja1/`, `web/fixtures/ja1/` (2.2 MB: four answers trimmed to 120 rows),
`web/fixtures/save_ja1_fixtures.py`.

## 6. PO lines

None: no new table (the stretches are the existing per-game rows), no workflow, render or nightly line. The new cache
region `stats_byweek` is in DEPLOY § Memory (≤ 24 × ~60 KB). `app/whats_new.md` (PO): "Stats: pick any weeks with a
slider, compare one stretch of weeks with another (who gained or lost target share), and see one stat week by week."

## 7. Found, not mine

* With a stretch in force the phone's first screen carries the slider (~300 px) and shows fewer table rows than
  IX-3 round 2's three; a compact closed form of the slider (the words and the track, quick picks behind a tap) would
  give them back.
* "The weeks before" and "the rest of the season" are the same weeks when A ends the season (both offered, as asked).
* The CSV served by the API has no by-week form (the screen builds that file itself).

## 8. Next

JA-2: Compare and Matchups reuse `WeekSlider` and `readStretch` / `stretchParams` (`window`, `weeks`, `vs`).
