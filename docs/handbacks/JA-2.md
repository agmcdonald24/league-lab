# JA-2 — the same weeks on Compare and Matchups (Wave J-A)

**Start 01:11 ET, Monday 2026-10-12 (read from `date`); end 01:33.** Branch `dev/JA2` (from `integ/JA` = JA-1),
`/home/claude/wt-iq4`, database `league_lab_iq4`.

## 1. Done / not done / cut

* **Done — 1. The compact closed form**: below 900 px a chosen stretch closes the week control to one line naming what
  is in force ("Weeks 3–4 against weeks 1–2 ▾", a real button with `aria-expanded`, opens in place; it stays open while
  the visitor works it — a quick pick, a handle, the switch). Stats' phone toolbar shares the question's row with "↓ CSV"
  (the column count from 640 px). **At 375 × 812 with weeks 3–4 against weeks 1–2: 3 whole table rows** (before: 2;
  round 2's season view: now 4).
* **Done — 2.** One preset when "the weeks before" and "the rest of the season" are the same weeks: "The weeks before".
* **Done — 3. Compare**: a card "Over the weeks you pick" with the same control and keys (`window`, `weeks`, `vs`); with
  other weeks "His early weeks against his recent ones": each player's A, the change and B for Games, Points per game,
  Targets per game, Target share, Receptions / Receiving yards per game, Carries per game, Carry share, Rushing yards per
  game, Pass attempts / Passing yards per game (QB), Snap share — the Stats frame's own arithmetic
  (`/api/compare/weeks`, `research` bucket). The forecasts (this week, the next 4 weeks, the rest of the season) stay on
  `/api/compare`, which takes no weeks, and a line says they are forecasts, not history.
* **Done — 4. Matchups**: a card "Defenses, weeks 3–4 against weeks 1–2" (the control without the games picks; a
  position chip): each defense's points per game to the position over the stretch, its rank (among those with two
  games or more; 1 = gives up the most), B's rank and the change ("▲ up 15" = gives up more now), "1 game: too few to
  rank". `/api/matchups/defense` with `window` / `weeks` / `vs` returns everything it returned before, unchanged, plus
  `stretch`; the screen's season heatmap and your starters' matchups come from the request without weeks.
* **Done — 5.** Stats' side by side opens Compare with `window`, `weeks`, `vs`.
* **Not done**: the Matchups card is a table per position (not a second heatmap); "Last 3 weeks" there means calendar
  weeks (a defense has no "games played" window).

**What reads the season's rank (unchanged by a stretch)**: the card's "Next:" line and its matchup evidence
(`player.py` 148, 586: `mart_defense_vs_position_current.rank_std`); My Week's and the trade's reasons
(`app/lib/cards.py` 182–190: the same `rank_std` as `opp_rank`); Compare's opponent rows (`league_dvp`, the season);
Matchups' heatmap and starters (`matchups_defense`, no weeks). None of these routes reads `window`, `weeks` or `vs`;
`test_ja2` checks `/api/player/{gsis}` and `/api/my-week` answer the same with and without them, and that the
defense route's season `teams` are identical with a stretch.

## 2. Commits

`c5c8fbb` (1–2) · `29b5a02` (3–4, the API) · `5e2a26d` (3–5, the screens) · the WORDS / CHANGELOG commit · this file.

## 3. Evidence (League of Scrubs, the fixture API; weeks 3–4 against weeks 1–2)

* **Compare, Justin Jefferson against Parker Washington**: target share 8.0% (1 game) against 35.7% in weeks 1–2:
  −27.7 pts; Washington 16.0% against 36.7%: −20.7 pts; points per game 4.2 / 17.1 and 6.5 / 15.1.
* **Matchups, WR**: Houston #1 in both stretches (37.5 points per game to WRs), Detroit #2 (was #4), Dallas #3 (was
  #18: ▲ up 15), Pittsburgh #8 (was #31: ▲ up 23), Indianapolis #24 (was #2: ▼ down 22); two defenses with one game in
  weeks 3–4 are not ranked.
* The phone with weeks 3–4 against 1–2: the control is one line, 3 table rows above the bottom menu
  (`docs/handbacks/ja2/ja2-stats-compact-375.jpg`). Screens: `ja2-compare-two-stretches-375/1300`,
  `ja2-matchups-change-in-rank-375/1300`. No sideways scroll.

## 4. Tests

* New: `api/tests/test_ja2.py` **5 passed** (Compare's rows equal the Stats frame's A and B; validation; the forecasts
  identical with weeks in the address; the defenses' stretch — 32 per position, rank 1 = the most, change = B − A,
  one game unranked — and the season `teams` identical; `/api/player` and `/api/my-week` identical with the weeks).
  `web/e2e/ja2` **6 passed**; `web/e2e/ja1` 8 passed (updated on purpose: a phone opens a chosen stretch closed — the
  specs tap `slider-toggle`; one preset when the two are the same weeks; a new test: ≥ 3 rows at 375 × 812).
* API files of the changed routes (`check_api.sh`: ja2, ja1, i0b, ib3, if3, im3, in2, io4, research, parity, ix3,
  im1): **253 passed, 5 failed — 0 new** (all in the known list).
* e2e, both projects — Compare and Matchups (ib1, ix5, io4, if3, in2, if4, ib3, in3, ir1, inf1, ia1, ja2): **92
  passed**; Stats (ja1, ix3, im2, ii3, il1, ip3, ip4, im3, ii6, in1, ii2, `fixtures.spec.ts`): **169 passed, 7
  skipped**.
* Ruff, the copy standard, `npm run lint`: clean; the build. `scripts/gate.sh`: see the final message.

## 5. Edits outside my files

`api/league_lab_api/research.py` (a JA-2 block at the end), `main.py` (the defense route's weeks; `/api/compare/weeks`),
`ratelimit.py` (`/api/compare/weeks` in `research`), `web/src/routes/Compare.svelte`, `Matchups.svelte`,
`Players.svelte` (the toolbar, the link to Compare), `web/src/lib/api.ts` (types and paths at the end), WORDS,
CHANGELOG. New: `api/tests/test_ja2.py`, `web/e2e/ja2/`, `web/fixtures/ja2/` (390 KB), `save_ja2_fixtures.py`.

## 6. PO lines

None (no table, no workflow or nightly line). `app/whats_new.md` (PO): "Compare two players over the weeks you pick —
their early weeks against their recent ones — and see which defenses have given up more or less lately."

## 7. Found, not mine

* Matchups' season heatmap names "weeks 1–N" from `weeks_used` but its ranks come from the mart's own season; with the
  league's scoring they can differ from the stretch card's season row by a place (the card ranks only defenses with two
  games or more).

## 8. Next

JA-3 (the connection pool). The control's keys are stable for any further screen: `window`, `weeks`, `vs`.
