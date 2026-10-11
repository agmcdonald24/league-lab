# IX-1 — a game a player left early: the stat, the mark, the projected share (Wave I-X)

**Start 00:51 ET, Sunday 2026-10-11 (read from `date`); end 01:43.** Branch `dev/IX1` (from `integ/IX` = `main`
`38c0339`), `/home/claude/wt-iq4`, database `league_lab_iq4`. The rule: docs/METRICS.md § "A game left early" (lf1.0),
committed first (`01a4f3a`, 00:54), before any number was read.

## 1. Done / not done / cut

* **Definitions and the grade's rule, first** (`01a4f3a`): the on-field share exact (participation) and estimated
  (snaps; capped at 1, NULL without snaps), left early (snap drop + injury note identified by the play's own ids, or +
  no touch after half-time), candidates LE-A / LE-B / LE-0 (reference), the participation truth, precision / recall /
  F1, and the pick (higher F1; a tie ships LE-A).
* **Built** (`2d89ac7`): `int_player_game_on_field` (new) → `fct_player_game` gets `on_field_basis`,
  `on_field_targets`, `on_field_team_targets`, `on_field_target_share`, `on_field_carries`, `on_field_team_carries`,
  `on_field_carry_share`, `left_early`, `left_early_reason`; 12 new dbt tests. **LE-B ships, by the rule** (F1 0.422
  against LE-A's 0.253) — with a plain warning on its precision (§ 3).
* **Projected target share** on the card (`/api/player/{gsis}`, the live week): built; its accuracy is context (§ 3).
* **API fields for IX-2 / IX-3** (`e5f8b8a`, `18e445a`, `dff1314`): Stats' two catalogue columns with sums, basis and
  samples (on the window path, `window=…`, which the Stats screen uses; the plain season path reads
  `mart_player_season`, which does not carry them);
  the game log's `left_early` + reason (+ the display-only "then missed week N") and on-field shares; types in
  `web/src/lib/api.ts`; the Stats mirror (`columns.ts`: group and sample line).
* **Evidence**: Ja'Marr Chase's game is on the copy (2026 week 4, CIN at JAX) — § 3. The chain: ERROR 0 everywhere.
  **The projection's inputs: 0 cells differ** with the code toggled at one state (main's `fct_player_game.sql` and
  IX-1's, each followed by a rebuild of every model between it and the feature mart): `fct_player_game`'s 148 columns
  of `main` identical on all 186,415 rows; `mart_player_recent_form` identical; `mart_player_week_features` identical
  but for `prev_snap_pct`'s last floating-point bit (≤ 4.4e-16), which differs just as much between two rebuilds of the
  same code (29,869 rows). The projection's outputs against the pre-chain copy are **not** 0: weeks 6 – 18 and the live
  week differ (weeks 1 – 5 kept identical; max 1.48 points, 182 rows ≥ 0.5) — the refit's run-to-run variation and the
  copy's earlier state, not this change (§ 7).
* **Not done / cut**: no screen work (IX-2 / IX-3 own the card and the table), so no screenshots; the Stats screen's
  Full table gains the two columns through the catalogue (no saved answer carries them).

## 2. Commits

* `01a4f3a` the definitions and the grade's rule, before any number
* `2d89ac7` `int_player_game_on_field`, the columns on `fct_player_game`, tests; the grade script
* `e5f8b8a` the API fields (Stats catalogue, game log, the card's projected target share)
* `9992829` the result in METRICS, WORDS, CHANGELOG, the API tests, the types and the Stats mirror
* `c4e199d` METRICS wording (LE-A's recall, verified: 386 of 1,465)
* `18e445a` Stats rows carry the on-field samples
* `df64f89` lf1.0 in the metric registry
* `dff1314` the merge keeps the frame's notes; the pinned catalogue count; DATA_INVENTORY
* this file

## 3. Evidence

**Ja'Marr Chase, 2026 week 4** (Cincinnati at Jacksonville; "CIN-1-J.Chase was injured during the play", 2nd quarter
12:11, on a play whose receiver id is his):

| | Week 1 | Week 2 | Week 3 | **Week 4** |
|---|---:|---:|---:|---:|
| Targets / team targets | 4 / 34 | 9 / 31 | 12 / 37 | **3 / 53** |
| Snap share | 94% | 88% | 100% | **20%** (15 snaps) |
| Whole-game target share | 11.8% | 29.0% | 32.4% | **5.7%** |
| On-field target share (estimate; 2026 has no participation) | 12.5% | 33.0% | 32.4% | **28.3%** |
| Left early | — | — | — | **yes**: "15 snaps (20% of the team's; usually 94%); hurt on a play in the 2nd quarter" |

The card's projected target share for week 5: "8.0 of his team's 46.3 projected targets in week 5 (17%): the model's own
forecast of his share of the team's targets this week."

**The fields, exactly** (IX-2, IX-3):

* `GET /api/players?…&window=season` (Stats), per row: `on_field_target_share`, `on_field_carry_share` (0 – 1, null =
  unknown), `on_field_targets`, `on_field_team_targets`, `on_field_carries`, `on_field_team_carries` (the summed parts),
  `on_field_basis` (`participation` | `snaps` | `mixed` | null), `left_early_games`. Catalogue ids
  `on_field_target_share` ("Target share on the field", "Tgt % on", RB / WR / TE, group Receiving) and
  `on_field_carry_share` ("Carry share on the field", "Car % on", RB, group Rushing). Chase, 2026, `window=season`:
  `{"games": 4, "targets": 28, "team_targets": 155, "target_share": 0.1806, "on_field_target_share": 0.2621,
  "on_field_targets": 28, "on_field_team_targets": 106.84, "on_field_basis": "snaps", "left_early_games": 1}`.
* `GET /api/player/{gsis}/games`, per game: `left_early` (bool), `left_early_reason` (string | null),
  `on_field_target_share`, `on_field_carry_share`, `on_field_basis`. Chase, week 4: `{"week": 4, "targets": 3,
  "target_share": 0.0566, "on_field_target_share": 0.283, "on_field_carry_share": 0.0, "on_field_basis": "snaps",
  "left_early": true, "left_early_reason": "15 snaps (20% of the team's; usually 94%); hurt on a play in the 2nd
  quarter"}` ("; then missed week 5" is added once week 5's box score is in and he did not play).
* `GET /api/player/{gsis}`: `projected_target_share` = `{"share": 0.1724, "targets": 8.0, "team_targets": 46.3,
  "week": 5, "players": 13, "words": "8.0 of his team's 46.3 projected targets in week 5 (17%): the model's own
  forecast of his share of the team's targets this week."}` or null (a QB, no line, he sits, a team total of 0).

**The grade** (`scripts/analysis/ix1_left_early.py`, after the rule's commit): (a) the estimate against the exact share
on 2016 – 2025 — target share mean absolute difference 0.035 on all 52,131 player-games, **0.060 on the 1,732 truly
left-early ones** (the whole-game share is off by 0.200 there); carry share 0.038 / 0.047 (whole game 0.247). Coarse in
the tail: one left-early game in ten is off by 0.18 or more. (b) the rule against the truth (42,803 player-games, 1,465
true):

| Candidate | Flagged | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| LE-A snap drop + injury note | 224 | 0.955 | 0.146 | 0.253 |
| **LE-B snap drop + (note or no touch after half-time)** — ships | 1,367 | 0.437 | 0.408 | **0.422** |
| LE-0 snap drop alone (reference) | 3,719 | 0.219 | 0.557 | 0.315 |

Plainly: **LE-B's mark is right less than half the time**; the reason says which signal fired, so "hurt" is said only
when the play-by-play named him. LE-A is right 19 times in 20 (0.86 – 1.00 by season) and finds one in seven.

**The ten largest on-field − whole-game differences of 2026** (RB / WR / TE): all one-target games of a player with 1 –
4% of the snaps (Colbie Young CIN wk 3, J. Michael Sturdivant GB wk 4 (left early), Jayden Reed GB wk 2, Braxton Berrios
NYG wk 4 (left early), Tank Bigsby PHI wk 3 (left early), Cyrus Allen KC wk 1, Arian Smith NYJ wk 1, Demond Claiborne
MIN wk 2, Lan Larison NE wk 1, Jalen McMillan TB wk 3): the estimate caps at 100% and is noise on a handful of snaps — a
screen should show the sample beside it (the Stats row carries the parts: "1 of 1.0 team targets on the plays he was on
the field").

**The projected target share against weeks 1 – 4 of 2026** (frozen lines): the teams' summed projected targets average
32.8 against 31.2 real; the projected share is 0.051 from the real whole-game share on average (1,281 RB / WR / TE
player-weeks). Not graded against a baseline: context.

**The chain** (`LEAGUE_LAB_FREEZE=game /home/claude/waveIT/chain.sh /home/claude/wt-iq4 league_lab_iq4`, 801 s):

```
== 01:03:23 db migrate
== 01:03:25 dbt build (full)
05:10:14  Done. PASS=746 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=751
== 01:10:14 project
== 01:16:15 projection marts
05:16:29  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 01:16:30 availability guards (as errors)
05:16:38  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 01:16:39 audit
## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
```

**The projection's inputs** (how I checked; `scratchpad/ix1/toggle.sh`, `toggle2.sh`, `colcmp.py`):

1. `main`'s `fct_player_game.sql` built beside IX-1's as a scratch table (`ix1tmp_fct_player_game_main`, dropped):
   `except all` both ways on main's 148 columns → 0 and 0 rows (186,415 each).
2. Nothing in `dbt/models` or `src/league_lab` reads the new columns (grep: only `int_player_game_on_field.sql` and
   `fct_player_game.sql`).
3. The toggle (same data, same clock): main's file → `dbt run --select "fct_player_game+,+mart_player_week_features"`
   (16 models) → dump the feature mart (F0); IX-1's file → the same (F2); and IX-1's before it (F1). Per column:
   F0 vs F1 29,271 cells, F0 vs F2 30,128, **F1 vs F2 (the same code) 29,869** — every one in `prev_snap_pct`, all
   ≤ 4.4e-16 (an `avg` summed in a different order). No other column of the 127 differs.
4. The chain's projection against the pre-chain copy (`ops.*` snapshots before `project` ran): K / DEF identical
   (`kd_lines`, `kd_ranges` and their live rows); QB / RB / WR / TE weeks 1 – 5 identical, weeks 6 – 18 differ (12,406
   rows of `ops.projections`, `proj_points` up to 1.48) and the live week (898 rows). The copy's earlier feature mart had
   another hash (it was built at another time); with inputs equal to the last bit, this is the refit's variation, which
   IW-1 already saw between two chains of the same code. A second `project` at the same state (6 minutes) did not fit
   the clock.

## 4. Tests

* New: `api/tests/test_ix1.py` 5 passed (the catalogue's two columns, a window's on-field sums and basis, unknown
  never 0, the projected target share's words and its None cases, the game log's mark and "then missed week N");
  12 dbt tests (`int_player_game_on_field`: unique key, estimates ≤ 1, his on-field targets ≤ the team's, the mark's
  inputs, the shipped rule = LE-B, the basis; `fct_player_game`: shares in [0, 1], the basis, a mark has a reason,
  2026 is the estimate) — the chain's dbt build PASS 746, ERROR 0.
* API test files of the edited modules and changed routes (37 files: `stats` / `/api/players`, `player` /
  `/api/player/{gsis}`, `research` / the game log; `check_api.sh`): 555 passed, 37 failed, 9 skipped; **new against the
  known list: 8**, of which **5 were mine and are fixed** (`test_im1` ×3 — the merge dropped the frame's notes, and the
  catalogue's pinned count 104 → 106 on purpose; `test_ii3` — `docs/DATA_INVENTORY.md` rows added); re-run
  `test_im1` + `test_ii3` + `test_ix1`: 41 passed, 1 skipped. **3 are this copy's state, not mine**:
  `test_f3::test_player_card_ros_is_the_marts` ×2 (fails the same with `main`'s `player.py`),
  `test_ib0::test_waivers_never_calls_an_overlay_starter_would_not_start`,
  `test_inf1::test_waivers_deadline_answers_the_pinned_moment` (the waiver routes: no file of mine; the chain re-ran
  `project`).
* `check_root.sh`: 1,749 passed, 5 failed; new: `test_metric_registry` (lf1.0's row, fixed: 3 passed).
* `scripts/gate.sh python`: **GATE PASSED**. ruff `src app tests api scripts`: clean. Copy standard `--check`: clean.
  `web`: lint 0 errors / 0 warnings, build OK. e2e `im2` (Stats; both projects): 18 passed.

## 5. Edits outside my files

`dbt/models/marts/nfl/fct_player_game.sql` (the join and nine columns, in an IX-1 block), `dbt/models/marts/schema.yml`
and `dbt/models/intermediate/schema.yml` (tests); `api/league_lab_api/stats.py` (two catalogue entries, the merge, the
sums, the samples), `research.py` (the game log calls `onfield.game_log_marks`), `player.py` (one field);
`web/src/lib/api.ts` (types at the end), `web/src/components/stats/columns.ts` (group + sample line); docs METRICS,
WORDS, CHANGELOG. New: `int_player_game_on_field.sql`, `api/league_lab_api/onfield.py`, `api/tests/test_ix1.py`,
`scripts/analysis/ix1_left_early.py`.

## 6. PO lines

None needed: no new table to keep (every column is rebuilt by dbt from inputs the nightly already has), no workflow or
render line. Hosted size: `fct_player_game` (published slim, `SLIM_TABLES`) gains nine columns — 2.6 MB over all
seasons here, a fraction of that for the hosted seasons' window. `app/whats_new.md` waits for IX-2 / IX-3 (nothing on a screen reads these yet).

## 7. Found, not mine

* **The projection is not reproducible run to run** (weeks 6 – 18 and the live week, up to 1.5 points), and
  `mart_player_week_features.prev_snap_pct` changes in its last bit on every rebuild. IX-6's backtest should fix both
  (round `prev_snap_pct`; seed / order the refit) before it reads a 3% improvement.
* docs/METRICS.md line 12 lists a "partial-game exclusion" that no code implements: still true (IX-6's question).
* `fct_player_game.target_share` counts nflverse's team targets; the exact on-field share counts play-by-play targets
  (both numerator and denominator), so the two differ by a target or so on some games.

## 8. Next

1. IX-2 / IX-3: the fields in § 1 (exact names in the final message).
2. IX-6: LE-B is what ships for display; for the projection, LE-A's precision (0.955) may matter more than F1 — IX-6's
   rule decides. A feature-mart before / after must be compared column by column at one state (§ 3, § 7).
