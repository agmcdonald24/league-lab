# IM-2 hand-back — the Stats tables' screen: the full table, readable without clicking into anyone

**Task**: Wave I-M, IM-2 (`/home/claude/waveIM/BRIEF.md` § IM-2). **Branch**: `dev/IM2` from `main` `ab50682`.
**Dev**: Claude (Opus), worktree `/home/claude/wt-im2`, web only, database `league_lab` read-only (nothing written).

## What was built, against the numbered list

| # | Item | State |
|---|---|---|
| 1 | Two views one tap apart: **Key stats** (preset columns) / **Full table** (every column for the position that is available, catalogue order, group headers); `group` / `full` derived when absent (`GROUPS` map in `components/stats/columns.ts`; full = catalogue columns whose `positions` include the position and `available` is true); `?view=`; remembered; Full from 900 px, Key on a phone | **Done.** The API's `group` / `full` win when present (e2e on a hand-added IM-1 shape). Remembered **on this device** (`accountPrefs.statsTable()`, localStorage `ll.stats.table`) — a phone and a desktop keep their own; a saved view keeps `view`, `hide`, `off` (they are in its address). Not pushed to the account (see Limitations). |
| 2 | Built for width: sticky player column + sticky header rows; sideways scroll inside the box only; right-aligned tabular figures; sort on any column (sorted column marked); group toggles over the column picker; row hover / tap highlight; the dash's reason on hover / tap; small samples greyed; per game / totals on every column that has both; the existing filters | **Done.** Sorting stays client-side over the whole frame (the screen already fetches `limit=1000`, every row of the window; the API's `sort=` / `dir=` go into the CSV link). "Small samples greyed": the screen had no such rule on `main` (`SAMPLE` in `stats.py` names the sample fields only), so `SMALL` in `columns.ts` sets one per rate (targets < 10, receptions < 8, carries < 15, pass attempts < 30, charted targets < 10, NGS targets < 10 / receptions < 8 / carries < 20 / pass attempts < 50). In the Full table the picker ticks columns on / off (`off=`); in Key stats it edits `cols=` as before. |
| 3 | All the players: "Showing 50 of 184 — Show all"; smooth at 400 rows × 40 columns on a phone; measure | **Done.** "Showing 50 of 291" + **Show all 291** / **Show the first 50**. Chunked rendering was not enough (see § Timings): past 100 rows the table renders only the rows near the box's visible part (8 rows overscan each side), spacer rows keep the height, the column widths are measured once and fixed, `aria-rowcount` / `aria-rowindex` say the size. No dependency. |
| 4 | Download CSV: a link to `GET /api/players.csv` with the current parameters; 404 → built in the browser | **Done.** `<a href="/api/players.csv?…" download>`; a click fetches it: `text/csv` → saved under the server's filename (`data-from="server"`); 404 (today) or no answer → the file is built from every filtered row and the columns on screen (`data-from="browser"`). Nothing to switch at the merge: with IM-1's route present the route is used automatically; drop the fallback if you prefer one path. |
| 5 | 375: Key stats default; Full table works; sticky name column ≤ 120 px (short name + team); "swipe for more →" until the first sideways scroll; group row sticky with the column row; the drawer still opens; dark and light | **Done.** Name column 120 px (checkbox, "J. Smith-Njigba" by CSS — the link's text and accessible name stay the whole name —, position + team badges; no headshot under 640 px). |
| 6 | Accessibility: real `<table>`, scoped headers, `aria-sort`, group headers as `colgroup` + header cells, focus visible, the sticky column never covers a focused cell | **Done.** Row headers are `<th scope="row">`; a `<caption>` (sr-only) names the view and sort; narrow groups show a short name ("Games") with the whole name for screen readers; `scroll-padding` keeps focus clear of the sticky column and header (e2e). |
| 7 | Tests: `web/e2e/im2/fixtures.spec.ts` on recordings of today's API + one with a hand-added `group` / `full`; screenshots 375 / 1300 light / dark | **Done.** 9 tests × 2 projects (18). Recordings: `web/fixtures/im2/api_im2.json` (WR / TE and ALL, League of Scrubs, 2026 weeks 1–4, from the fixture API on `league_lab`; `web/fixtures/save_im2_fixtures.py` re-records), `web/fixtures/im2/im1_shape.json` (IM-1's shape by hand: groups that differ from the client's map, a `full` list leaving out Charted targets, one new column the rows do not carry: Drops → a dash with its reason). |

## Files

Mine: `web/src/components/stats/StatsTable.svelte` (new), `web/src/components/stats/columns.ts` (new),
`web/src/routes/Players.svelte`, `web/src/lib/api.ts` (Stats types: `StatsColumn.group?`, `StatsPreset.full?`,
`statsCsvPath`), `web/e2e/im2/fixtures.spec.ts`, `web/fixtures/im2/*`, `web/fixtures/save_im2_fixtures.py`,
`docs/WORDS.md` § "The Stats tables (Wave I-M, IM-2)", `CHANGELOG.md` (one bullet under `## 2026-10-06 — Wave I-M`,
created), this file and `docs/handbacks/im2/*.png`.

**Edits outside my files** (smallest possible):
- `web/src/lib/prefs.ts` (+9 lines, owned by no package): `accountPrefs.statsTable()` / `setStatsTable()` and the key
  `ll.stats.table`.
- `web/e2e/ii3/fixtures.spec.ts` (2 lines): the sticky-column check reads the row's first `th, td` (the name cell is a
  row header now), and the column-picker test opens `&view=key` (from 1300 px the screen now opens on the Full table,
  where every column is already ticked).
- `docs/DESIGN.md`: rule 6 notes the Stats table as the one sideways-scrolling table; a new § "The Stats table".

**Schema in / out**: reads `GET /api/players?window=…` as today (`catalogue[].group` and `presets[].full` optional);
calls `GET /api/players.csv?league&limit=1000&position&window[&basis][&weeks]&sort&dir&cols=<catalogue ids>&mode=game|total[&who][&team][&nfl][&q][&min_games]`
(IM-1: `mode` is mine — per game or totals for the columns that have both; ignore it or honour it).
No new env variable, no new dependency, no new relation, no new cache region.

## Commands and evidence

- `cd web && npm run lint` (eslint + svelte-check `--fail-on-warnings` + tsc): **0 errors, 0 warnings**.
  `npm run build`: **ok** (Players chunk 39 kB, 13.8 kB gzip before the stats components; see the build log).
- `FIXTURES_PORT=8620 npx playwright test --config playwright.fixtures.config.ts e2e/im2`: **18 passed**.
- Whole fixtures e2e: see § "Whole suite" below.
- `uv run python scripts/copy_standard.py --check`: **clean** (exit 0). `uv run ruff check web/fixtures/save_im2_fixtures.py`: clean.
- PO scripts: see § "Check scripts".

### Timings (the e2e test "400 rows x 40 columns"; recording: every position, **453 rows × 46 columns = 20,838 cells**)

The box: 2 cores shared with four other devs (load average 7–10 while measuring), headless Chromium (software
compositing). "Phone" = the phone project at 375 px with CPU throttled 4× (CDP `Emulation.setCPUThrottlingRate`);
"desktop" = 1300 px, no throttle. Frames are rAF intervals (16.7 ms = 60 fps). Several runs; ranges given.

| | All rows in the page, rendered in chunks (first build) | Windowed past 100 rows (shipped) |
|---|---|---|
| Show all → every row in the table, desktop | 1.5–2.4 s (longest frame 133 ms) | **0.11–0.48 s** (longest frame 50–150 ms) |
| Show all, phone 4× | 6.3–9.3 s (longest frame 600 ms) | **0.26–1.08 s** (longest frame 50–550 ms) |
| Re-sort all rows, desktop / phone 4× | 0.7–1.0 s / 3.6–4.2 s | **0.10–0.35 s / 0.30–0.81 s** |
| Scroll, desktop (p50 / p95 frame) | 60–100 ms / 90–300 ms | **16.7–18.8 ms / 23–78 ms** (brisk: 3,000 px down + across in 2 s) |
| Scroll, phone 4× (p50 / p95 frame) | 77–151 ms / 145–380 ms | **18–56 ms / 41–540 ms** (same brisk scroll; the tail tracks the box's load) |
| Rows in the page after Show all | 453 | 28–37 |
| Baseline: the first 50 rows, same scroll | p50 16.7 ms everywhere | p50 16.2–17 ms |

Why windowed: an A/B on the same build (desktop, brisk scroll, CSS injected) — all name cells sticky: p50 80 ms;
`tbody th { position: static }`: p50 21 ms; no sticky header either: p50 17.5 ms. Every sticky name cell is a layer the
browser re-places each scroll frame; 450 of them dominate. Making only nearby rows sticky (IntersectionObserver) was
worse (p50 242 ms): toggling `position` re-lays out the whole 20,000-cell table. Main-thread work during the 2 s phone
scroll (4×): script 0.2–0.5 s, style 0.09–0.42 s, layout 0.12–0.47 s. A **fling** (every row and column in 2 s,
~12,000 px/s) still janks: 270–610 ms frames (the whole window is rebuilt each frame).

## Screenshots (`docs/handbacks/im2/`, 256-colour PNGs at CSS pixels)

`im2-full-1300-dark.png`, `im2-full-1300-light.png`, `im2-full-375-dark.png`, `im2-full-375-light.png`,
`im2-key-375-dark.png`, `im2-key-375-light.png` — WR / TE, League of Scrubs, sorted by target share.

## Limitations (said plainly)

- **The remembered view is per device**, not per account: an account restore would need one line in IM-4's
  `lib/account.svelte.ts` (`restore`); I did not add it (a phone and a desktop want different defaults).
- **Windowed mode** (Show all past 100 rows): the browser's find-in-page sees only the rows near the visible part; Tab
  from the last rendered row leaves the table (keyboard users reach the rest by scrolling the box or sorting). A fling
  janks (above).
- **A dash's reason** is in the cell's title (hover; Chrome exposes it as the cell's description) and a note on a tap;
  dash cells are not keyboard-focusable (thousands of tab stops otherwise).
- **Small-sample thresholds** are client constants (`SMALL`); if IM-1's catalogue carries a minimum sample, wire it there.
- **Group order** per position is the client's (`ORDER` in `columns.ts`: the position's own stats first); inside a group
  the answer's order is kept.
- The CSV from the browser holds every filtered row (not only the 50 on screen), shares as percent numbers
  ("Target share (%)", 26.5), unknown as an empty cell; text a spreadsheet would run as a formula is neutralised.

## PO lines I need

- `app/whats_new.md` (PO-owned), one entry: "**Stats: the full table.** Players · Stats now has two views: Key stats
  and Full table — every number we have for the position, grouped (Receiving, Air yards, Red zone, Next Gen Stats…).
  Tap a group to hide it, sort any column, show every player, and download the table as a CSV."
- `docs/STATUS.md` (PO-owned): the § "Wave I-M" IM-2 line from this file's summary.

## Seen, not mine

- The fixture API recipe (rule 6) leaves the availability overlay on: my API on :8752 tried `site.api.espn.com` twice
  (the proxy refused; I stopped the API once the recordings were saved). `LEAGUE_LAB_AVAILABILITY=off` in the recipe
  would keep a fixture API off the network.
- `routes/Players.svelte` on `main`: the search's 250 ms debounced `setParams` survived the screen — a fast tap on a
  player's "Full player page" put `q=…` on the player page's address (`e2e/ib1` "the player's page keeps the tab bar"
  failed once on that). Fixed here (the timer is cleared when the screen unmounts).

## Next

The merge with IM-1: run `e2e/im2` against IM-1's API answer (re-record with `save_im2_fixtures.py`) and check the
`full` list's order reads well under the groups; decide whether the CSV keeps the browser fallback.
