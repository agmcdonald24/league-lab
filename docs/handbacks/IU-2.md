# IU-2 — the live week after its first kickoff (Wave I-U, Friday 2026-10-09)

Branch `dev/IU2` (from `main` 99fb216), worktree `/home/claude/wt-iq4`, database `league_lab_iq4` (week 5 under way:
TB at DAL kicked off Thursday 20:15 ET, 14 games left; week 6 live). Commits: `4783398` (read-first + the rule, before
any code), `5349814` (the evidence's rule before its numbers; the design corrected: v3 reads teammate-out inputs),
then the code. The switch defaults to `week`; nothing a reader sees changes until it is set.

## 1. What reads the frozen rows, and what a Saturday re-projection would leak or shift

Full text: docs/METRICS.md § "The live week after its first kickoff". In short:

* **The decision record** = the rows `freeze_plan` keeps once a week's first game kicked off (`ops.projections`, and
  NFL-wide `ops.projection_lines` / `projection_ranges` / `kd_lines` / `kd_ranges`), labelled `kickoff` (written
  before the first kickoff) or `refit`. Graded by `drift` → `ops.projection_drift` → `mart_projection_drift` (About's
  grades, `frozen_share`), `mart_projection_record` (`kickoff` only, against Sleeper's last pre-kickoff snapshot),
  `context_record` (`PROJ_SQL`), `lineup_record` (the lineup recommended before the first kickoff), `market_record`;
  `signals` skips kickoff weeks; kept across nights by `restore_state` and `save-record` / `restore_record_from_archive`;
  held by `assert_frozen_projections_precede_kickoff` / `assert_frozen_nfl_wide_precede_kickoff`.
* **Live readers of the same rows**: `mart_player_week_projections` (every house screen, the card, `ratings`), the ROS
  mart ("a week held twice keeps the frozen row"), `anyleague`'s `_FRESHEST` board, `unitcard`, the lineup and waiver
  solves inside `project` (`lineup.lineups` reads `ops.projections`), My Week's realised rows.
* **Why the whole week freezes at once**: `freeze_plan`'s unit is (league, week): one label, one `frozen_at`, one
  `fitted_at` per unit; the grades and both freeze tests assume "a week is the board as published". Rewriting part of
  a week would mix two fits under one label.
* **What a Saturday re-projection changes** (features are as-of week W, `assert_features_never_peek`): Thursday's
  game does **not** enter a Sunday player's season-to-date inputs (they stop at W−1), so nothing leaks from the
  played game. What shifts: the week's injury report (`questionable`; v3's personnel inputs — `pn_top_target_out`,
  `pn_top_rusher_out`, `pn_teammate_share_out`, `pn_absence_beneficiary`, `pn_qb_*` — all read week W's report and
  the reserve lists), the market (`implied_team_total`, `spread_line`), who starts at QB (the schedule's projected
  starter or IQ-2's override), the roster file's reserve lists, and the gate's word. Not the depth chart (the model
  does not read it). My first design text said the model has no teammate-out input; that was
  wrong and was corrected in `5349814`, before any number.

## 2. The design (the rule, committed before code)

1. A game's rows are the record once **that game** kicks off. The board managers saw at the week's first kickoff
   stays **kept, unchanged, where it is**; every grade keeps reading it there.
2. The live number lives in an overlay, **`ops.projection_live`** (the shape of `ops.projections` + `team`,
   `game_kickoff`): the started week's rows of the games not kicked off. Why not a column: a column on
   `ops.projections` means updating kept rows (the record's cells change, and `frozen_at`/`fitted_at` stop meaning
   "this row as published"); the existing record tables are the record. `db migrate` creates it (registered in
   `projections.NFL_DDL`, which migrate already runs; `db.py` untouched); the mart's pre-hook creates it too, so the
   mart builds on a database that never ran migrate. Size: see § 4.
3. `LEAGUE_LAB_FREEZE=week|game`, default **`week`** (unset, a typo, anything but `game`): `freeze_plan` and every
   writer untouched, the overlay empty. With `game`: `project` writes the overlay (tonight's rows, through the same
   gate: who sits is 0 with the reason) and `mart_player_week_projections` takes the overlay row for a (league, week,
   player) when one exists, else the stored row.
4. Shadow first (§ 5).
5. Housekeeping: a run replaces the overlay rows of the games not kicked off; a game that kicked off since keeps the
   rows it had (its number at its own kickoff) until the week is over; no week under way, or switch `week` → empty.

Every other reader keeps reading what it reads today (lineup / waiver solves inside `project` still read
`ops.projections`: with `game` they keep Thursday's numbers for the week — see "not done").

## 3. The switch with `week`: 0 cells differ

Method: the same sequence twice on the same database — `league-lab project` then the nightly's projection-marts build
(`--select` exactly as in `scripts/nightly.sh`) — once on `main`'s code (99fb216, before any `src/` edit; snapshot A),
once on this branch with `LEAGUE_LAB_FREEZE` unset (snapshot B). Every table `project` writes (every `ops` table but the
loaders' and the backtests') and the projection marts, each sorted on all its columns; run stamps left out (`fitted_at`,
`run_at`, `as_of`, `built_at`, `graded_at`, `written_at`, `fetched_at`). Fits are deterministic (ordered `load_frame`).

| | tables | rows | cells that differ |
|---|---:|---:|---:|
| A (main) vs B (branch, switch unset) | 28 (19 `ops`, 9 marts) | 212,607 | **0** |

The one new thing: `ops.projection_live` exists (created by `db migrate`), **0 rows**. The kept weeks (1–5) are
untouched in every table in every run of the day (A, B, the two chains). Scripts: `<scratchpad>/iu2/snap.sh`,
`cmp.sh`; the unset chain's own comparison is in § 7.

## 4. What `game` moves on this copy (week 5)

`LEAGUE_LAB_FREEZE=game` chain (§ 7): week 5 under way (TB at DAL played Thursday), 14 games not kicked off,
580 players re-projected, **1,104 overlay rows** (2 house leagues × 552, K / DEF included), 150 of them gated (75
players who sit: 0 with the reason — the same 75 the kickoff board gated; nobody's word changed: this copy's Sleeper
directory is from 2026-10-05 and no week-5 injury report is loaded — the last load was 2026-10-08 01:35 UTC).
`ops.projection_live`: 472 kB on this copy (≈ 1 MB on the hosted database during a publish, which holds two copies;
0.02 % of the 1 GB plan; empty with `week`). The mart reads the overlay row for those 1,104 (league, player)s; the
record (`ops.projections` weeks 1–5) is identical before and after.

What `game` moves on a real Saturday, and what it does not (read in the SQL; docs/METRICS.md point 5):

| input | reaches the live row? | how |
|---|---|---|
| injury report (Friday's final) | yes | the gate (Out / Doubtful → 0, with the reason), `questionable`, and for RB / WR / TE the teammates-out inputs (`pn_top_target_out`, `pn_top_rusher_out`, `pn_teammate_share_out`, `pn_absence_beneficiary`) and line starters out — "who replaces whom" is these, as far as the model learned them |
| roster file (weekly rosters) | yes | reserve lists: the gate's fallback and the personnel inputs' "gone" |
| IQ-2's starter override / the schedule's projected QB | yes, QB rows only | `pn_qb_*` (who starts); RB / WR / TE read no QB input — a QB change reaches his receivers only through the market's implied total |
| market lines | yes | `implied_team_total`, `spread_line`, `total_line` when the schedule file's lines move |
| Sleeper's word | yes | the gate only |
| depth chart | **no** | `int_depth_chart_current` feeds the matchup card and the starter check, not the projections |
| Thursday's played game | **no** | season-to-date inputs stop at week W−1 (`assert_features_never_peek`) |
| the lineup / waiver solves inside `project`, the record, every grade | **no** | they read `ops.projections` (the kickoff board), not the mart |

What moves against the kickoff board on this copy (Thursday 19:51 ET):

| league | player | kickoff board | tonight | move | why |
|---|---|---:|---:|---:|---|
| Forever Unclean Dynasty | Puka Nacua (WR, LA, Monday) | 21.91 | 25.53 | **+3.62** | receiving yards 98.2 → 105.5: the line crosses the dynasty's 100-yard bonus (+3; this league prices flat, the bonus counts when the line is over 100) |
| League of Scrubs | Puka Nacua | 18.06 | 18.67 | +0.61 | same line, no yardage bonus |
| Forever Unclean Dynasty | Jaxon Smith-Njigba (WR, SEA) | 17.94 | 18.58 | +0.64 | receiving yards +5.8 |
| Forever Unclean Dynasty | Davante Adams (WR, LA) | 17.58 | 17.08 | −0.50 | receiving yards −4.1 |

1 row moves by 2 points or more, 5 by 0.5 or more, 1 by 1 or more; mean |move| 0.045 points over 1,104 rows. Why
anything moves with no new data: tonight's warehouse build and code against Thursday's (the shadow's run before the
chain's full dbt build listed Stafford +3.81 and Nacua
+3.47; after it, Nacua alone) — not news. Nacua's 2-point move is a 3-point flat bonus switching on for 7 yards
(the unset chain's shadow shows Stafford's: passing yards 292.4 → 300.6, the dynasty's 300-yard bonus): the shadow
names the stat line and the bonus crossed so the reader sees it. On a real Saturday
the moves come from Friday's report through the gate, `questionable` and the personnel inputs, the market, and who
starts at QB (§ 1). The 2-point list is short on purpose: it is what the PO reads.

### Face validity

| case | Thursday board | live / Saturday | scored | reads right? |
|---|---:|---:|---:|---|
| CeeDee Lamb, DAL, 2025 week 5 (Out on Friday's report) — study | 20.35 | 0 | 0 | yes |
| Jayden Daniels, WAS, 2025 week 4 (Out) — study | 19.86 | 0 | 0 | yes |
| Puka Nacua, LA, 2025 week 7 (Out) — study | 17.50 | 0 | 0 | yes |
| Puka Nacua, dynasty, 2026 week 5 (Monday) — copy | 21.91 | 25.53 | — | the line +5 to +7 yards switches the 100-yard bonus on (+3, flat): a pricing step, named in the reason |
| Matthew Stafford, dynasty, 2026 week 5 — copy, unset shadow | 26.19 | 29.48 | — | passing 292 → 301 crosses the 300-yard bonus (+3): same |
| the 75 players gated at kickoff — copy | 0 | 0 (the same 75) | — | yes: no new word on this copy (directory of 2026-10-05) |
| TB / DAL (Thursday's game) — copy | kept | not in the overlay | — | yes; 13 of their rows changed `rank_pos` only (the live players around them moved) |
| a backup whose starter sits | — | — | — | not on this copy (no week-5 report loaded); the shadow names "teammate sits: …" when it happens (tested) |

## 5. The shadow (switch `week`)

With the switch unset, `project` computes what `game` would write (the same function, no write) in **0.26 s**
(0.32 s in the `game` run); `league-lab freeze-shadow` prints it in 0.01 s (1–5 s with `uv`'s start): far under the 3 minutes. It never raises
(a failure is logged, written into the JSON as `error`, and the night goes on; tested), and with `week` it writes no
row (§ 3). The output on this copy (switch unset, after the unset chain):

```
$ league-lab freeze-shadow --md logs/freeze_shadow.md      # 1.2 s with uv's start
fr1.0 shadow: week under way: 5; 2 house-league rows move by 2.0 points or more; 14 games not kicked off, 580 players re-projected (switch week; computed 2026-10-09T16:58:41.695432+00:00 in 0.25 s; gate: Sleeper directory copy of 2026-10-05T12:00:39.609393Z)
  Forever Unclean Dynasty  Matthew Stafford         QB  LA    26.19 ->  29.48 (+3.29)  the inputs moved since the kickoff board (the week's report, market lines, who starts at QB); the line: passing_yards 292.42 -> 300.55, passing_interceptions 0.37 -> 0.44, fumbles_lost_total 0.13 -> 0.15; crosses the 300-yard passing bonus (+3)
  Forever Unclean Dynasty  Puka Nacua               WR  LA    21.91 ->  24.75 (+2.84)  the inputs moved since the kickoff board (the week's report, market lines, who starts at QB); the line: receiving_tds 0.66 -> 0.58, receiving_yards 98.18 -> 101.87, receptions 7.69 -> 7.66; crosses the 100-yard receiving bonus (+3)
fr1.0 shadow printed in 0.01 s
```

The nightly diff (PO's file; `freeze-shadow` right after `project`, recorded but never added to `FAILED`; its markdown
goes into the run summary like the list audit):

```diff
--- a/scripts/nightly.sh	2026-10-09 12:15:38.085352461 -0400
+++ b/scripts/nightly.sh	2026-10-09 12:23:18.590893016 -0400
@@ -164,6 +164,9 @@
       # ---- IR-3 (Wave I-R): the post-publish check's lines, when it ran
       if [ -s logs/post_publish_check.txt ]; then echo; echo "**Post-publish check (the live site)**"; echo; echo '```'; cat logs/post_publish_check.txt; echo '```'; fi
       # ---- end IR-3
+      # ---- IU-2 (Wave I-U): fr1.0's shadow, when it ran (who would move if the started week's unplayed games were re-projected)
+      if [ -s logs/freeze_shadow.md ]; then echo; echo "<details><summary>Freeze shadow (fr1.0): the live week's games not kicked off</summary>"; echo; cat logs/freeze_shadow.md; echo; echo "</details>"; fi
+      # ---- end IU-2
       # ---- IQ-4 (Wave I-Q): the list audit, whole (about 100 lines of markdown), when it ran
       if [ -s logs/list_audit.md ]; then echo; echo "<details><summary>List audit (the trust guard)</summary>"; echo; cat logs/list_audit.md; echo; echo "</details>"; fi
       # ---- end IQ-4
@@ -519,6 +522,15 @@
   FAILED+=(project)
   finish
 fi
+# ---- IU-2 (Wave I-U): fr1.0's shadow -- the house-league rows of the started week's games not kicked off that would move by
+# 2 points or more if they were re-projected (LEAGUE_LAB_FREEZE=game), and why; `project` computed it (logs/freeze_shadow.json),
+# this prints it and writes the run summary's part (logs/freeze_shadow.md). A report nothing reads: a failure is recorded,
+# never added to FAILED (the night is not failed by it).
+rm -f logs/freeze_shadow.md
+if run_step freeze-shadow uv run league-lab freeze-shadow --md logs/freeze_shadow.md; then
+  record freeze-shadow "$LAST_SECS" "ok: $(head -1 logs/freeze_shadow.md 2>/dev/null | sed 's/^fr1.0 shadow //' | cut -c1-160)"
+else record freeze-shadow "$LAST_SECS" "FAILED (a report nothing reads: the night goes on)"; fi
+# ---- end IU-2
 # ---- V-1 (Wave I-G): `project` wrote the decision record (lineups() -> lineup.write_record, never fatal there);
 # `league-lab validate` writes it again when that failed (same freeze rule: idempotent) and prints the grade. Soft:
 # the weeks already kept are untouched, and a week not written tonight is rebuilt (labelled) the night after kickoff.
```

## 6. Evidence on the past

Rule committed first (`5349814`, docs/METRICS.md). The only dated news in the warehouse is the week's **final injury
report** (nflverse; Friday's designations): no Thursday copy of the lines, the depth chart or the report exists, so a
Thursday board T is the model's number (today's v3.6 refit on the seasons before), a Saturday board S is T with the
final report's Out / Doubtful (and the reserve lists) at 0 — the gate's part. Players of the games after the week's
first kickoff, ppr, actual 0 when he did not play; Spearman per week × position (≥ 8 players), averaged.

| population | n | MAE T | MAE S | Spearman T | Spearman S |
|---|---:|---:|---:|---:|---:|
| 2025 weeks 1–18, all | 9,594 | 4.238 | **3.249** | 0.614 | **0.746** |
| 2025, status changed (Out / Doubtful, not reserve) | 344 | 6.763 | **0.000** | — | — |
| 2026 weeks 2–4, all | 1,699 | 4.248 | **3.444** | 0.606 | **0.713** |
| 2026, status changed | 45 | 7.113 | **0.000** | — | — |
| *sensitivity: T already zeroes the reserve lists* — 2025 | 9,594 | 3.491 | 3.249 | 0.713 | 0.746 |
| *sensitivity* — 2026 weeks 2–4 | 1,699 | 3.632 | 3.444 | 0.689 | 0.713 |
| *extra: 2026 week 4's real kickoff board (v3.0), scrubs* | 554 | 3.957 | 3.135 | 0.581 | 0.708 |
| *extra: the same, dynasty* | 554 | 4.778 | 3.802 | 0.585 | 0.710 |

None of the 344 + 45 status-changed players played (25 of the 344 were Doubtful). Spearman for them: no cell of 8. The rule's
"2026 week 4 real kickoff board in ppr" is not computable as written (ppr's week-4 ranges are refit values; the
kickoff board exists in the two house scorings) — shown as the labelled extra. **Verdict by the rule: S is better in
both seasons → recommend `game` after one weekend of the shadow.** What it does and does not show: it measures the
gate's part, which the screens already apply at request time with `week`; the part only `game` adds (the stored
number the screens read without the request-time gate, the teammates' personnel inputs, the market, who starts at QB)
has no dated data to measure. Script: `<scratchpad>/iu2/study/fr1_study.py` (302 s), `fr1_w4.py`.

## 7. The chains

**Switch unset** (`/home/claude/waveIT/chain.sh /home/claude/wt-iq4 league_lab_iq4`, final code, 12:48–12:59, 693 s):
ERROR 0 in every step.

```
== 12:48:16 db migrate
schemas and ops tables are in place
== 12:48:17 dbt build (full)
16:53:44  Done. PASS=733 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=738
== 12:53:44 project
12:53:55 INFO league_lab.calibration: fi1.0: market week 5; later weeks' lines from the teams' own season (7229 rows, shrink 3.0 games), personnel of the market week (432 rows moved)
12:58:29 INFO league_lab.calibration: hb1.0: market week 5; QB weeks after it blended with the naive line, weight by horizon {2: 0.0, 3: 0.45, 4: 0.25, 5: 0.4, 6: 0.55, 7: 0.95, 8: 0.75} (lambda 0.25, k 6.0); 1039 QB lines moved
12:58:35 INFO league_lab.kdef: kd League of Scrubs (551104): D/ST keys not projected (price 0): def_st_ff, def_st_fum_rec, st_ff, st_fum_rec
12:58:41 INFO league_lab.availability_gate: availability gate: week 6, Sleeper directory (copy of 2026-10-05T12:00:39.609393Z): 77 players who cannot play or are unlikely to play get 0 this week (77 of them out indefinitely: no later weeks)
projected 19584 rows for 2026 (2 league(s), weeks 1-18); wrote 13332 (weeks [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]), kept frozen weeks [1, 2, 3, 4, 5]
availability gate, week 6: Sleeper directory copy of 2026-10-05T12:00:39.609393Z; 77 players who cannot play or are unlikely to play get 0 this week, 77 of them
== 12:59:21 projection marts
16:59:34  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 12:59:35 availability guards (as errors)
16:59:43  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 12:59:44 audit
# List audit — 2026, week 5
_Built 2026-10-09 16:59 UTC; every list a visitor can open without a league (Half PPR, PPR, Standard; this week and rest of season; the free calculator's values)._

## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
_Who cannot play: 236 players, unlikely to play (Doubtful): 0, by Sleeper's directory (copy of 2026-10-05T12:00:39.609393Z; the directory alone, never the stored record it checks); the screens' gate as the routes apply it at request time (the stored record, th
- None: every player who cannot play or is unlikely to play is off this week's screens, and every player out indefinitely off the season lists and the calculator's values.
- Note — stored rows the screens gate: 0 (week 5 froze at its first kickoff; its numbers are never rewritten).

## Coverage — every team in every list
- Every team with a game in a list's window has players in it (all 54 lists).

## Projected against what they have scored (3+ games this season)
### QB · this week
- Kyler Murray (MIN): #9 here, #30 in points per game (7.8 in 3 games) [Half PPR, PPR, Standard]
- Justin Herbert (LAC): #12 here, #25 in points per game (12.4 in 4 games) [Half PPR, PPR, Standard]
- Tyler Shough (NO): #3 in points per game (24.1 in 3 games), #18 here [Half PPR, PPR, Standard]
- explained by status: Bryce Young (a bye this week)
### RB · this week
- explained by status: Kenneth Walker III (a bye this week)
### WR · this week
- George Pickens (DAL): #11 here, #50 in points per game (5.6 in 4 games) [Standard]
### TE · this week
- Mike Gesicki (CIN): #4 in points per game (13.0 in 3 games), #24 here [Half PPR, PPR, Standard]
- Juwan Johnson (NO): #2 in points per game (13.6 in 3 games), #20 here [Half PPR, PPR, Standard]
- AJ Barner (SEA): #11 here, #27 in points per game (4.1 in 4 games) [Standard]
- explained by status: Travis Kelce (a bye this week)
### K · this week
- Cameron Dicker (LAC): #2 here, #28 in points per game (6.0 in 4 games) [Half PPR, PPR, Standard]
- Harrison Mevis (LA): #7 here, #26 in points per game (6.5 in 4 games) [Half PPR, PPR, Standard]
- Wil Lutz (DEN): #9 here, #30 in points per game (5.5 in 4 games) [Half PPR, PPR, Standard]
- Andy Borregales (NE): #11 here, #29 in points per game (5.8 in 4 games) [Half PPR, PPR, Standard]
- Matt Gay (LV): #4 in points per game (11.5 in 4 games), #24 here [Half PPR, PPR, Standard]
- Chase McLaughlin (TB): #5 in points per game (10.2 in 4 games), #21 here [Half PPR, PPR, Standard]
- Spencer Shrader (IND): #1 in points per game (13.2 in 4 games), #22 here [Half PPR, PPR, Standard]
### DEF · this week
- Washington Commanders (WAS): #3 here, #25 in points per game (5.0 in 4 games) [Half PPR, PPR, Standard]
- Dallas Cowboys (DAL): #4 here, #30 in points per game (3.0 in 4 games) [Half PPR, PPR, Standard]
- Las Vegas Raiders (LV): #2 in points per game (12.0 in 4 games), #23 here [Half PPR, PPR, Standard]
### QB · rest of season
- explained by status: Bryce Young (a bye this week)
== 12:59:49 done
```

(The project step's own fr1.0 line, which `chain.sh`'s filter does not show: `fr1.0 (week): week under way: 5, 14 games
not kicked off, 580 players re-projected, 2 house-league rows would move by 2.0 points or more; overlay off (0.25 s)`.)

**`LEAGUE_LAB_FREEZE=game`** (12:21–12:34, 725 s; code before the reasons named the line and the bonus — no cell
depends on them): ERROR 0 in every step; the audit is word for word the unset chain's (the free lists read the
NFL-wide board, which has no overlay).

```
== 12:21:53 db migrate
schemas and ops tables are in place
== 12:21:54 dbt build (full)
16:27:35  Done. PASS=733 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=738
== 12:27:36 project
12:27:48 INFO league_lab.calibration: fi1.0: market week 5; later weeks' lines from the teams' own season (7229 rows, shrink 3.0 games), personnel of the market week (432 rows moved)
12:32:32 INFO league_lab.calibration: hb1.0: market week 5; QB weeks after it blended with the naive line, weight by horizon {2: 0.0, 3: 0.5, 4: 0.2, 5: 0.2, 6: 0.5, 7: 0.95, 8: 0.75} (lambda 0.25, k 6.0); 1039 QB lines moved
12:32:38 INFO league_lab.kdef: kd League of Scrubs (551104): D/ST keys not projected (price 0): def_st_ff, def_st_fum_rec, st_ff, st_fum_rec
12:32:45 INFO league_lab.availability_gate: availability gate: week 6, Sleeper directory (copy of 2026-10-05T12:00:39.609393Z): 77 players who cannot play or are unlikely to play get 0 this week (77 of them out indefinitely: no later weeks)
projected 19584 rows for 2026 (2 league(s), weeks 1-18); wrote 13332 (weeks [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]), kept frozen weeks [1, 2, 3, 4, 5]
availability gate, week 6: Sleeper directory copy of 2026-10-05T12:00:39.609393Z; 77 players who cannot play or are unlikely to play get 0 this week, 77 of them
== 12:33:26 projection marts
16:33:43  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 12:33:43 availability guards (as errors)
16:33:52  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 12:33:52 audit
(identical to the unset chain's audit above, but its timestamps)
```
`fr1.0 (game): … overlay rows written: 1104 (0.32 s)`.

**What differs between the chains, and why it is not the switch** (snapshots of all 29 tables after each run):

| pair | weeks 1–5 (the record, and the week under way) | weeks 6–18 |
|---|---|---|
| main `project`+marts (A) vs branch, unset (B) | 0 cells | 0 cells |
| unset chain (C) vs unset chain again (C2), same code | 0 cells (but 4 `ops.lineups` rows of weeks 2 / 4) | differ (12,406 `ops.projections` rows) |
| main (A) vs unset chain (C2) | 0 cells | differ (the same drift) |
| `game` chain (G) vs unset chain (C) | **only** `mart_player_week_projections` week 5: 1,104 overlay rows + 13 `rank_pos` of Thursday's game; `ops.projection_live` 1,104 vs 0 | differ (the same drift) |

So the switch unset changes 0 cells; every full chain on this copy re-projects the live weeks 6–18 a little
differently from the one before, whatever the code (a full `dbt build` between two `project`s; hb1.0's fitted horizon
weights differ run to run — IU-5's file, not touched). The 4 `ops.lineups` rows of played weeks 2 / 4 that differ
between C and C2 (and not between A and C2) come from the lineup solve on identical projections — run-to-run
variation there, not investigated today.

## Files, tests, not done

* `src/league_lab/projections.py` — `freeze_unit` (the switch), `started_week`, `live_rows` (gated with
  `availability_gate.gate_frame`), `shadow_moves` / `_line_moves` / `_bonus_crossings` (the reasons),
  `live_after_project` (never raises; JSON; overlay write / clear), `_write_live` / `_clear_live`; `ops.projection_live`
  in `NFL_DDL` (so `db migrate` creates it); one call in `project` after `_write_projections`. `freeze_plan`,
  `_write_projections`, `write_nfl_wide` untouched (a test reads their source for the switch).
* `src/league_lab/cli.py` — `project` prints the fr1.0 line; `league-lab freeze-shadow [--md FILE]`.
* `dbt/models/marts/nfl/mart_player_week_projections.sql` — `p` = stored rows without an overlay row ∪ overlay rows
  cast to `ops.projections`' own columns (`jsonb_populate_record`: round trip exact on all 19,364 rows); the pre-hook
  creates the overlay (`like ops.projections`). `dbt/models/sources/sources.yml` — the source.
* `dbt/seeds/metric_registry.csv` — `live_week_freeze, fr1.0` (experimental). `docs/METRICS.md` — § "The live week
  after its first kickoff" (read-first, the rule, the corrections, the study's rule and result). `CHANGELOG.md` —
  Wave I-U bullet. No screen, no user-read sentence (WORDS.md untouched), no screenshot.
* Tests: `tests/test_iu2_freeze.py` (17: the switch, the week under way, the live rows gated and unlabelled, the
  shadow's reasons and threshold, the step never raises, the CLI and its markdown, the DDL / mart / source wiring,
  the writer untouched); `tests/test_nfl_wide.py` (the overlay is not state: kept out of the STATE_TABLES check).
  `scripts/gate.sh python`: GATE PASSED (root 783, api 34, ruff). Copy standard: exit 0. Root suite
  (`check_root.sh`): 1,722 passed, 4 failed — all 4 in the known list (`known_root_failures.txt`), 0 new.
* PO's files, as diffs only: `scripts/nightly.sh` (§ 5). To turn `game` on later: `LEAGUE_LAB_FREEZE=game` in the
  nightly's environment (the workflow / the Mac's env), nothing else.

**Not done / open.** (1) With `game`, the lineup and waiver solves inside `project`, the ROS mart and `anyleague`'s
NFL-wide board keep reading the stored rows (the overlay is house-league, `ops.projections`-shaped, read only by
`mart_player_week_projections`); NFL-wide (`projection_lines` / `projection_ranges`) has no overlay. (2) The overlay is
not in `STATE_TABLES`: on a fresh CI database a game that kicked off since the last night loses its live rows (the
screen falls back to the kickoff board for that game); the Mac keeps them. (3) Every two full chains on this copy
differ in the live weeks 6–18 (§ 7) whatever the switch — e.g. hb1.0's horizon weights printed {3: 0.5, 4: 0.2, …} in
one run and {3: 0.45, 4: 0.25, …} in the next; IU-5's file, reported here, not touched. (4) The study measures the
gate's part only (§ 6).
