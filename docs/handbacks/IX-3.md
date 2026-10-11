# IX-3 — Stats: a table that opens on an answer (Wave I-X)

**Start 02:39 ET, Sunday 2026-10-11 (read from `date`); end 03:13.** Branch `dev/IX3` (from `integ/IX` = IX-1 + IX-2,
`d67be9c`), `/home/claude/wt-iq4`, database `league_lab_iq4`.

## 1. Done / not done / cut

* **Done — 1. Key stats first on every width** (at most eight columns, games included; was 14, and Full table from
  900 px). Named views **Production · Opportunity · Role changes · Efficiency · Advanced**, each ≤ 8 columns per
  position with its question in a line under the switch; IX-1's two on-field shares are in Opportunity; Full table one
  tap away; saved views keep working (`view=` stays in their address; a named view clears a custom `cols=`). The views
  live in `stats.VIEWS` (the answer's `views`, and `presets[].views`); `columns.ts` mirrors them for an older answer. A
  view the season leaves with games alone is not offered (a quarterback has no Role changes view).
* **Done — 2. Remembered per position** (`ll.stats.tables` = {"wrte": …, "rb": …, "qb": …, "all": …}); IM-2's one
  `ll.stats.table` value is carried over once to every position and removed. Changing position drops `view=` from the
  address so the new position opens on its own choice.
* **Done — 3. The situation filter**: All plays · When trailing · Within a score · When leading (IX-2's words, groups
  and 20-play floor). New `analytics.mart_player_game_situation` (player × game × situation; 4 dbt tests) so any
  window splits. **Split**: targets, target share, receptions, receiving yards, carries, carry share, rushing yards
  (+ their per-game twins). **Not split** — a dash and "Not split by game situation: …" — everything else (points, snap
  share, the on-field shares, air yards, red zone, efficiency, NGS, PFR, charting, role changes, the value column).
  A share on fewer than 20 of his team's plays: a dash and "Too few to read: N plays of his team's when trailing."
* **Done — 4. No internal names**: every catalogue source in plain words; "Out of:" replaces "Denominator:"; the group
  is **Snaps** in a season with no route column (2026), "Snaps and routes" when one is there.
* **Done — 5.** The table's box: "Filter this table by name" (the top bar's "Search players" unchanged).
* **Done — 6. Checked, nothing to fix**: a card opened from the table and closed keeps position, view, situation,
  sort, the page scroll and the table's own scroll (both widths, `e2e/ix3`).
* **Done — 7.** Tests, WORDS, CHANGELOG, METRICS § "Stats by game situation".
* **Not done**: the CSV file name does not say the situation (its rows do: unsplit cells are empty). The `data-view`
  attribute of the table still reads "key" for every named view (IM-2's component; specs read the tab's
  `aria-pressed`).

## 2. Commits

`76d42a9` (1) · `d3c16d2` (2) · `d047180` (3, the mart and METRICS) · `9adf216` (4) · `9d95a93` (5) · `be17cc6` (6,
`e2e/ix3`, recordings, screens) · `3dbb7a5` (7, specs updated on purpose, WORDS, CHANGELOG) · this file.

## 3. Evidence (League of Scrubs, `league_lab_iq4`, the fixture API, 2026 weeks 1–4)

* **What a first-time visitor sees, before → after**: phone — Key stats, **14** WR / TE columns; desktop (≥ 900 px) —
  the **Full table, 63** WR / TE columns (68 RB, 52 QB) under 13 group chips → **Key stats, 8 columns on every width**
  (G · Pts/G · Tgt/G · Tgt % · Rec/G · Rec yds/G · Rec TD/G · Snap %), the line "Key stats: The numbers to read first:
  what he scores and how much of the offence is his.", then the switch Key stats · Production · Opportunity · Role
  changes · Efficiency · Advanced · Full table.
* View sizes (WR / TE · RB · QB): Key 8 · 8 · 8; Production 8 · 8 · 8; Opportunity 8 · 8 · 7; Role changes 6 · 8 · —;
  Efficiency 8 · 8 · 8; Advanced 7 · 8 · 8 (2026 drops the route columns).
* **Ja'Marr Chase by situation** (Stats, season): When trailing 0 of 21 team targets (28 plays: 0.0%) · Within a score
  25 of 106 (170 plays: 23.6%) · When leading 3 of 28 (56 plays: 10.7%); all plays 28 of 155 (18.1%) — 0 + 25 + 3 = 28.
  The same as the card's Usage tab (IX-2).
* Leaders, target share when trailing (≥ 5 targets): Tetairoa McMillan 8 / 17 (47%, 33 plays), Isaiah Likely 10 / 23,
  DeVonta Smith 6 / 14. WR / TE when trailing: 45 players "too few to read", 68 whose team never trailed by 9+ in their
  games (unknown, not 0).
* **The mart reconciles**: summed by player, season and group, `mart_player_game_situation` equals
  `mart_player_context`'s five buckets on all 20,306 player-season-situation rows, 2016–2026 (0 differ). 106,700 rows,
  19 MB locally; the hosted window (3 seasons) is 23,874 rows (~4.3 MB).
* Sentences before → after: "Find a player" (the table's box) → "Filter this table by name"; "Denominator: …" → "Out
  of: …"; sources "nflverse play-by-play (fct_play)" → "nflverse play-by-play", "… (mart_player_ngs_week)" → "NFL Next Gen
  Stats via nflverse", "(team totals: fct_team_game); league_lab.role_trend" → "(team totals: his team's game totals); the
  measure DFS's role trend reads", "licensed routes feed (routes_feed)" → "a licensed routes feed"; group "Snaps and
  routes" → "Snaps" (2026); the How-to line adds the named views.
* Screens (`docs/handbacks/ix3/`, JPEG q70): `ix3-key-*`, `ix3-opportunity-*`, `ix3-trailing-*`, `ix3-full-*` at 375
  and 1300. No sideways scroll at 375.

## 4. Tests

* New: `api/tests/test_ix3.py` **5 passed** (views ≤ 8 with a question; IX-2's groups and floor; the window sum, the
  floor, unknown not 0, unsplit columns null; the route against SQL on this copy and the three groups adding up; no
  internal name in the catalogue, "Snaps" in 2026). dbt: `mart_player_game_situation` PASS 8 (model + 7 tests).
  `web/e2e/ix3` **10 passed** (5 × phone, desktop).
* API files of the edited modules and changed routes (`check_api.sh`: i0b, ii3, il1, il4, im1, im3, in2, io4, ip3,
  ip4, ix1, ix2, ix3, research, parity): **296 passed, 2 failed, 2 skipped; 0 new** (the 2: `test_research::
  test_trends_route` ×2, in the known list). **Updated on purpose**: `test_im1` (Key stats 6–8 columns, was 10–14; the
  five deeper receiver columns are in the named views), `test_il1` (the NGS columns in the named views).
* `check_root.sh`: 1,750 passed, 4 failed, **0 new**. Ruff `src app tests api scripts`: clean. Copy standard: clean.
  `npm run lint`: 0 errors / 0 warnings (210 files); build OK.
* e2e that open Stats, both projects: im2, ii3, il1, in2, ip3, io4 → 58 passed + `il1` QB test updated on purpose and
  re-run (2 passed); ip4, im3, ii6, in1, ii2, `fixtures.spec.ts` → 101 passed, 7 skipped. **Updated on purpose**:
  `im2` (every width opens on Key stats; Key stats ≤ 8; the group "Snaps"), `il1` (the QB test opens `view=full`).
* `scripts/gate.sh` (python + web), run last: **GATE PASSED** (79 s).

## 5. Edits outside my files

`api/league_lab_api/stats.py` (PRESETS' Key stats, VIEWS, sources, the "Snaps" group, the situation functions),
`research.py` (`stats_frame`: `situation`, `views`, `groups_for`), `main.py` (the two Stats routes take `situation`;
`_situation_only`, IX-3 block), `web/src/lib/api.ts` (types, end), `web/src/lib/prefs.ts` (IX-3 block),
`web/src/components/stats/columns.ts`, `StatsTable.svelte` ("Out of:"), `web/e2e/im2`, `web/e2e/il1`,
`api/tests/test_im1.py`, `test_il1.py`, CHANGELOG, WORDS, METRICS. New: `dbt/models/marts/nfl/
mart_player_game_situation.sql`, `situation.yml`, `api/tests/test_ix3.py`, `web/e2e/ix3/`, `web/fixtures/ix3/`,
`web/fixtures/save_ix3_fixtures.py`.

## 6. PO lines

```diff
--- scripts/sync_to_hosted.sh
-SLIM_TABLES="fct_player_game … mart_player_game_advanced"  # …
+SLIM_TABLES="fct_player_game … mart_player_game_advanced mart_player_game_situation"  # … IX-3: the Stats situation filter, windowed (19 → ~4.3 MB)
```
(The sync finds the relation by itself — the API names `analytics.mart_player_game_situation`; without the line it
goes whole, 19 MB.) The nightly's `dbt build` builds it with no edit. `app/whats_new.md` (PO): "Stats opens on eight
columns that answer a question, with views for production, opportunity, role changes, efficiency and advanced numbers,
and a filter for when a team trails, is within a score or leads."

## 7. Found, not mine

* The phone's first screen is still mostly controls (search, four chip rows, three selects) before the table: the
  table starts below 375 × 812's fold. A collapsed "Filters" row would put the answer first.
* `StatsTable`'s `data-view` attribute is binary (key / full).
* WORDS rule 4 lists "denominator" as never on a page; the catalogue's `aggregation` text says "summed numerator /
  summed denominator" (not shown on the Stats screen today; the CSV does not carry it).

## 8. Next

The CSV name with the situation; a "Filters" fold on the phone; IX-4.

## Round 2 — a phone opens on the answer too (start 07:09, end 07:20 ET; branch `dev/IX7` from `main`)

* **Done.** Under 900 px the Stats screen shows the title line (and its answer sentence), one **Filters** button, the
  position chips, the view tabs in **one row** (scrolling inside themselves, never the page), the count / CSV row, the
  view's question and the table. Behind the button (a real `<button>`, `aria-expanded`, `aria-controls`, Enter opens
  it in place): the name filter, ownership, NFL team, window, per game / totals, both minimums, the situation chips and
  their explanation, the window line, columns and saved views, the role-cards link. Closed, the button names every
  filter in force ("Filters: When trailing · Free agents · Last 5 calendar weeks"), else "Filters". From 900 px nothing
  changes (no button; every control where it was).
* **At 375 × 812: 3 whole table rows** above the bottom menu (the 4th cut by it); before: 0 (the table started below
  the fold). Screens: `ix3r2-closed-375.jpg`, `ix3r2-open-375.jpg`, `ix3r2-closed-filtered-375.jpg`.
* **Not done**: the "8 columns · Download CSV" row stays on the phone's first screen (moving it would give a fourth
  row; phone specs use `stats-csv`).
* **Tests**: `e2e/ix3` 12 passed (a new test: folded, named when in force, one-row tabs, keyboard, ≥ 3 rows; 1300
  unchanged); every spec that opens Stats, both projects — ix3, im2, ii3, il1, in2, ip3, io4, ib1: 82 passed; ip4, im3,
  ii6, in1, ii2, `fixtures.spec.ts`: 103 passed, 7 skipped. Lint 0 / 0, build, copy standard clean; `scripts/gate.sh`
  last: GATE PASSED.
* **Specs touched** (an `openFilters(page)` helper, called before a folded control; a no-op on a desktop): `e2e/ix3`
  (and the new test), `im2` (7 calls), `ii3` (7), `fixtures.spec.ts` (5), `ib1`, `ii2`, `ii6`, `il1` (1 each).
