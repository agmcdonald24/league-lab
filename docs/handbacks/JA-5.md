# JA-5 — Stats opens on the table on a desktop too (Wave J-A)

**Start 02:21 ET, Monday 2026-10-12 (read from `date`); end 02:33.** Branch `dev/JA5` (from `integ/JA`).

## 1. Done / not done / cut

* **Done**: from 900 px the controls are one row — the positions, the weeks as one line (`WeekSlider collapse="always"`:
  "Season · weeks 1–4 ▾", the slider and its quick picks open in place), the situation as a select (`stats-sit-pick`;
  the chips stay behind Filters), and the one **Filters** button (the phone's, now on every width: named when closed —
  "Filters: When trailing · Free agents · At least 2 games" — opening the name filter, ownership, NFL team, per game /
  totals, the minimums, the situation chips, the window line, columns and saved views, the role cards in place). The
  view's caption stays one line under the tabs. Nothing removed; URL keys unchanged; a link with filters opens with
  them applied and named.
* **The phone unchanged**: round 2's and JA-2's tests pass (≥ 3 rows at 375 × 812 with a stretch and a comparison).
* **Not done**: the weeks' one-line box is a few pixels taller than the chips beside it.

## 2. Commits

The JA-5 screen commit, the WORDS / CHANGELOG commit, this file.

## 3. Evidence (1300 × 900, League of Scrubs, WR / TE)

* **Before**: the table's header at about 880 px (`docs/handbacks/ja1/ja1-slider-open-1300.jpg`): no row on the first
  screen. **After**: nothing chosen — the first row's top at **416 px, 8 whole rows**; weeks 3–4 against weeks 1–2,
  when trailing, free agents, at least 2 games — the closed row reads "Weeks 3–4 against weeks 1–2 ▾ · When trailing ·
  Filters: When trailing · Free agents · At least 2 games", **416 px, 8 rows**.
* Screens (`docs/handbacks/ja5/`): `ja5-nothing-chosen-1300`, `ja5-everything-closed-1300`, `ja5-filters-open-1300`,
  `ja5-phone-375`.

## 4. Tests

* New `web/e2e/ja5`: 3 passed (the two 1300 × 900 states with the thresholds 520 px / 6 rows and 5 rows; Filters and
  the weeks open in place; the phone unchanged).
* Specs updated on purpose: `ja1` (the weeks open closed on a desktop too: an `openWeeks` helper; the desktop branches),
  `ii3` (`openWeeks` before the quick picks), `ix3` (the desktop has the Filters button now). The existing
  `openFilters` helpers already act on a desktop (they click the button when it is visible).
* e2e that open Stats, both projects: ja1, ii3, ja2, ja5 → 27 passed, 3 skipped (ja5's per-project skips); ix3, im2,
  il1, in2, ip3, io4, ib1 → 71 passed + ix3's desktop test updated and re-run (2 passed); ip4, im3, ii6, in1, ii2,
  `fixtures.spec.ts` → 102 passed, 7 skipped, 1 failed and passed alone (`ip4` "the card: rookie", desktop: a card
  test, timing).
* Lint, the build, the copy standard: clean. `scripts/gate.sh`: see the final message.

## 5. Edits outside my files

`web/src/routes/Players.svelte`, `web/src/components/stretch/WeekSlider.svelte` (`collapse` prop), the specs above,
WORDS, CHANGELOG. New: `web/e2e/ja5/`, `web/fixtures/ja5/` (one answer, 520 KB).

## 6. PO lines

None.

## 7. Found, not mine

* `ip4` "the card: rookie" (desktop) failed once in a long run and passed alone.

## 8. Next

—
