# IZ-1 — us against Sleeper's projections, on every week Sleeper still serves

**Start 18:04 EDT · end 18:52 EDT** (2026-10-11; clock 140 minutes). Branch `dev/IZ1` from `main` `2673b65`; database
`league_lab_iq4`. No Sleeper number exists on this copy: every number below is about our side, the code or the sizes.

## 1. Done / not done / cut

Done, in the brief's order of importance:

1. **The history pull** (`league-lab ingest sleeper-history [--offline]`, `src/league_lab/ingest/sleeper_history.py`):
   2023–2025 weeks 1–18 and each current-season week whose last game is over and that has no snapshot fetched before
   its first kickoff (on this copy: 2026 weeks 1–4, exactly the weeks before the record). One request a week, a second
   apart, through the ingest's client; three failures in a row stop the night. Rows with a projected line only, in
   `ops.sleeper_history` (`served = 'after_week'`, the payload's `updated_at`), one row a week in
   `ops.sleeper_history_weeks` (`ok` = held, never asked again; `failed` = asked the next night). Archive in
   `data/raw/sleeper/projections_history/` — never the snapshot folder the record replays. A fresh database: the state
   tables come back from the hosted copy; whatever is still missing is replayed from the archive before any request.
   Exit 0 on a partial or failed pull. The record cannot read a history row: another table, another folder, and dbt test
   `assert_record_reads_no_history` (error severity, PASS here).
2. **The rule first** (`c2b4b20`, 18:11 ET, before any code of the grade): docs/METRICS.md § "Us against Sleeper on
   the weeks Sleeper still serves (hh1.0)". **`ops.calibration_oof` answered**: it is the out-of-sample *component*
   projection (fitted on the seasons before, priced in the house scorings) — the rows the cold-start and new-team
   scales are fitted on, so *before* those steps and before the QB passing-TD regression. It says v3.0 because this
   copy's rows were built 2026-10-05 12:21 UTC (08:21 ET), when `MODEL_VERSION` still said "v3.0" (v3.1 / v3.2 never
   bumped it; v3.3 came at 12:37 ET that day) and this copy has not run the nightly's `calibration-oof` step since;
   the nightly's `ensure_oof` rebuilds it to the live version — still without the three steps. **So I built the live
   model's rows**: `ops.h2h_ours` (`h2h.build_ours`, once per `MODEL_VERSION`): per season S, `fit_position` on
   2016…S−1, then `pass_td_lines` and `blend_lines` (cold-start + WR new-team scales fitted on the component rows of
   the three seasons before S, computed in the same run), priced in both house scorings. The grade falls back to
   `ops.calibration_oof`, labelled "without the live board's latest adjustments", only when `ops.h2h_ours` lacks the
   live version. 2026 = the board frozen at kickoff (refit weeks 1–3 left out; an `ev`-priced week left out).
3. **Start / sit** defined before running: per house league × week × position, startable = top 24 QB / 48 RB / 60 WR /
   24 TE by ours **or** Sleeper's; a close call = two startable players within 3 points by either, ranked the other way
   round by the two, actual points different (pushes counted apart); share right, pair-weighted, interval from
   resampling weeks; plus all startable pairs (each side's share ordered right, ties half).
4. **The blend (bl1.0)** measured by its own pre-committed rule (w on a 0.05 grid fitted on 2023 → tested 2024,
   2023–24 → 2025; "gains" = ≥ 1% lower error on both test seasons and order ≤ 0.002 lower, League of Scrubs' scoring).
   Nothing shipped. Andrew's paragraph: METRICS § "Borrowing Sleeper's number" (`faa96ef`) — the gain is an upper
   bound (Sleeper's past lines were written after the games), the terms question (RotoWire's number through an
   undocumented endpoint: docs/SLEEPER_TERMS.md § "Sleeper's projections"), the way back (one switch, one place,
   frozen weeks keep what they published).
5. **Where it shows**: `ops.sleeper_h2h` (state; ~300 rows); `league-lab h2h --md logs/sleeper_h2h.md` — one table
   for the run's summary (weeks held of asked by season, objects / lines, NOT-held weeks with the error, lines matched
   by id of lines, player-weeks graded by position and season, then per position error / order with ours, Sleeper,
   diff [95%], the close calls we won and the word, the dynasty's word beside it, the word by season, the blend);
   `/api/record` `history` (`unavailable` + "The comparison with Sleeper on past weeks is not available right now." when
   the table is absent or unreadable; `none` with no sentence when it has no row; `graded` with the positions, the
   calls, by season, the blend, one sentence built from the rows and the caveat); About's record shows that sentence
   and the caveat ("Ours: …" + "Sleeper's numbers for past weeks are the ones its site serves now, written after the
   games, so this favours Sleeper; …").

Not done / cut: **no real numbers** (the first are the nightly's). K / DEF not graded (no out-of-sample K / DEF rows on
our side). A league we do not score gets no `history` block (the sentence names no scoring; `test_f3` pins that answer).
The pull writes no load-manifest rows (Data Status does not show it; `ops.sleeper_history_weeks` is its record). 2026
adds only week 4 to the history grade (weeks 1–3 are refit boards, never on any record).

## 2. Commits

`c2b4b20` the rule (hh1.0, bl1.0's rule) · `848f4df` the pull · `1e8bd1d` the grade (`ops.h2h_ours`, `ops.sleeper_h2h`,
dbt test) · `faa96ef` the blend's paragraph, SLEEPER_TERMS · `629e58d` where it shows (API, About, WORDS, screens) ·
`01bf417` metric_registry rows · `b24ef4e` the grade's rows written in their columns' types · the last commit:
hand-back, CHANGELOG.

## 3. Evidence

* The live model's rows on this copy (`ensure_ours`, 18:18–18:26): **34,592 rows** (2023 11,464 · 2024 11,470 · 2025
  11,658 — the same player-weeks as `ops.calibration_oof`, both house scorings), **507 s wall**, peak RSS 1.4 GB, table
  4.2 MB; window rows 2020–2022 in 105 s, then 130–138 s a season. The steps ran: pt1.0 moved 1,529 / 1,477 / 1,536 QB
  lines; cs1.1 + nt1.0 scaled 1,424 / 1,631 / 1,391 player-weeks (2023 / 2024 / 2025).
* Live rows against the stored v3.0 rows (League of Scrubs' scoring, same player-weeks, actuals identical): they differ
  on 99.6% QB / 88.2% RB / 95.8% TE / 96.3% WR of player-weeks; mean |difference| QB 0.65, RB 0.09, TE 0.17, WR 0.21
  points (max 4.7–8.4). The stored rows are not the live model.
* The copy's real 2026 week-5 snapshot through the history parser: 3,304 objects, **448 with a line** (= the snapshot's
  `pts_half_ppr` count): QB 30, RB 94, WR 156, TE 103, K 30, DEF 30, FB 4, DB 1.
* Offline pull on the copy: "weeks held: 0 of 58 (2023 0/18, 2024 0/18, 2025 0/18, 2026 0/4)".
* The grade's database path, dry run in a transaction rolled back (the real week-5 lines relabelled 2025 wk 9 and 2026
  wk 4 — plumbing only, measures not read): 766 QB–TE lines, 762 matched by id (2 ids unmatched), 968 population rows
  (2026 = kickoff board, 2025 = live rows), 152 grade rows, a 4-row summary table; 0 rows left after the rollback.
* The writers on Postgres, each in a transaction rolled back: `PgStore` (a week saved: 448 rows, `served`
  'after_week', `by_position` QB 30; a failed week twice: attempts 2, not held; 0 rows left) and `write_grade`'s COPY
  (62 constructed rows; the first version would have refused a pooled row's season — fixed in `b24ef4e`).
* Sizes: one week's answer 2.30 MB JSON, 0.19 MB gzip → 58 weeks ≈ 133 MB downloaded once, ≈ 11 MB of archive;
  `ops.sleeper_history` ≈ 6.1 MB (58 × 448 rows in a temp table); `ops.h2h_ours` 4.2 MB; `ops.sleeper_h2h` < 0.2 MB.
* The summary on this copy today: "Sleeper's past weeks: none pulled yet. / Our side, 2023–2025: the live model (v3.6)
  re-run on each season: kept from an earlier night / No player-week graded yet …".
* Screens (390 and 1300, `docs/handbacks/iz1/*-constructed-*.png`: the spec injects constructed words, not a
  measurement): the sentence and caveat under the record; no sideways scroll at 390.

## 4. Tests

* New: `tests/test_iz1_history.py` **12 passed** (the pull on saved answers in the real shape: lines kept / counted,
  `updated_at` one instant, 2023 without it, refused answers, which weeks, once a week a second apart, a failed week asked
  the next night only, an empty answer is a failed week, three failures stop the night, a fresh database takes the
  archive before asking, the archive is never the record's folder, the report's lines); `tests/test_iz1_grade.py`
  **28 passed** (constructed cases with known answers: Spearman / top-N, a four-player start / sit case by hand, ties,
  startable by either, every word, better side ahead / worse behind / identical level, the interval reproducible and
  around the mean, both scorings, the blend leaning on the better side and its weight never seeing the test season,
  kickoff-board weeks graded but not blended, Sleeper priced like the record, the summary's lines, the record reads
  no history, the written rows' types); `api/tests/test_iz1.py` **14 passed** (absent, unreadable, empty, filled,
  malformed; `/api/record` for League of Scrubs and `ref:half` in all four states: 200 every time).
* `web/e2e/iz1` **4 passed** (phone, desktop); the specs that open About — `e2e/iz1 h1 ig2 ig3 ik4 im3`: **35 passed, 1
  skipped**, both projects. `npm run lint` 0 errors / 0 warnings; `npm run build` ok.
* Existing files of the modules and route I changed: `api/tests/test_f3.py test_m4.py test_v1.py test_im3.py
  test_ic4.py test_ig3.py test_ih1.py test_i0b.py test_v2.py` (+ test_iz1): 180 passed, 12 failed, 5 skipped — the 12
  fail the same with `main`'s `ondemand.py` on this database (8 in test_f3, 4 in test_m4; test_m4's fourth case started
  failing after the chain's `project` rewrote weeks 6–18, with `main`'s file too). `test_f3::test_record_route` pins the
  answer for a league we do not score: kept unchanged (no `history` there). `tests/test_sleeper_projections.py`,
  `test_metric_registry.py` pass.
* Root suite (`check_root.sh`): 1,793 passed, 4 failed, 3 skipped — **no new failure** (the registry rows were missing on
  the first run: fixed in `01bf417`).
* `uv run ruff check src app tests api`: clean. Copy standard: clean. dbt: `assert_record_reads_no_history` PASS.
* `LEAGUE_LAB_FREEZE=game chain.sh` (18:31–18:43): migrate ok; full dbt build PASS 755, WARN 5, **ERROR 0**; project ok
  (kept frozen weeks 1–5); projection marts PASS 146, ERROR 0; availability guards PASS 2, ERROR 0; audit ran.
* `scripts/gate.sh`: **GATE PASSED** (root 783 ran, api 40 ran, ruff, web lint, build; 72 s).

## 5. Edits outside my files

`api/league_lab_api/ondemand.py` (`record()`: `history`, marked IZ-1) · `src/league_lab/db.py` (`migrate`: the four
tables) · `src/league_lab/cli.py` (`ingest sleeper-history`, `h2h`) · `web/src/routes/About.svelte` (two lines under the
pricing sentence) · `web/src/lib/api.ts` (types at the end) · `docs/METRICS.md`, `docs/WORDS.md`, `docs/SLEEPER_TERMS.md`,
`dbt/seeds/metric_registry.csv`, `CHANGELOG.md`. New: `src/league_lab/ingest/sleeper_history.py`, `src/league_lab/h2h.py`,
`api/league_lab_api/h2h_api.py`, `dbt/tests/assert_record_reads_no_history.sql`, `tests/test_iz1_history.py`,
`tests/test_iz1_grade.py`, `api/tests/test_iz1.py`, `web/e2e/iz1/fixtures.spec.ts`.

## 6. PO lines

**`scripts/nightly.sh`** (two soft steps, the state tables, the summary's table):

```diff
--- a/scripts/nightly.sh
+++ b/scripts/nightly.sh
@@ -170,6 +170,9 @@
       # ---- IU-2 (Wave I-U): fr1.0's shadow, when it ran (who would move if the started week's unplayed games were re-projected)
       if [ -s logs/freeze_shadow.md ]; then echo; echo "<details><summary>Freeze shadow (fr1.0): the live week's games not kicked off</summary>"; echo; cat logs/freeze_shadow.md; echo; echo "</details>"; fi
       # ---- end IU-2
+      # ---- IZ-1 (Wave I-Z): us against Sleeper on past weeks, one table (open, not folded: the PO reads it every morning)
+      if [ -s logs/sleeper_h2h.md ]; then echo; cat logs/sleeper_h2h.md; fi
+      # ---- end IZ-1
       # ---- IQ-4 (Wave I-Q): the list audit, whole (about 100 lines of markdown), when it ran
       if [ -s logs/list_audit.md ]; then echo; echo "<details><summary>List audit (the trust guard)</summary>"; echo; cat logs/list_audit.md; echo; echo "</details>"; fi
       # ---- end IQ-4
@@ -298,6 +301,12 @@
 # `db migrate` creates them; a copy that does not have them yet is "not published there"; empty with the switch unset.
 STATE_TABLES="$STATE_TABLES ops.projection_live ops.projection_lines_live ops.projection_ranges_live ops.kd_lines_live ops.kd_ranges_live"
 # ---- end IV-1
+# ---- IZ-1 (Wave I-Z): Sleeper's past weeks (ops.sleeper_history, ops.sleeper_history_weeks: pulled once, ~6 MB), the live
+# model's walk-forward rows (ops.h2h_ours: built once per MODEL_VERSION, ~4 MB, ~8-9 CPU-min) and the grade (ops.sleeper_h2h,
+# rebuilt every night, < 0.2 MB). State, not record: restored so no week is asked twice and the model is not refit each
+# night; when the hosted copy has none, `ingest sleeper-history` replays data/raw/sleeper/projections_history first.
+STATE_TABLES="$STATE_TABLES ops.sleeper_history ops.sleeper_history_weeks ops.h2h_ours ops.sleeper_h2h"
+# ---- end IZ-1
 
 is_record() { case " $RECORD_TABLES " in *" $1 "*) return 0;; esac; return 1; }
 
@@ -576,12 +585,27 @@
 else
   SOFT_WHY="the week keeps its earlier snapshots; the record uses the last one saved before kickoff" soft fetch-projections uv run league-lab ingest sleeper-projections
 fi
+# ---- IZ-1 (Wave I-Z): Sleeper's line for every past week it still serves (2023-2025 weeks 1-18, this season's weeks with no
+# snapshot saved before kickoff), once: weeks held are never asked again, a failed week is asked the next night (exit 0).
+# Never the record's input (another table, another archive folder; dbt test assert_record_reads_no_history).
+if [ "${NIGHTLY_SLEEPER_OFFLINE:-}" = 1 ]; then
+  SOFT_WHY="the weeks held stay; the archive is replayed only" soft sleeper-history uv run league-lab ingest sleeper-history --offline
+else
+  SOFT_WHY="the weeks held stay; the missing ones are asked the next night" soft sleeper-history uv run league-lab ingest sleeper-history
+fi
+# ---- end IZ-1
 soft save-record save_record
 # the projection marts on tonight's projections (+ mart_projection_backtest+: dbt's view swap
 # cascades to mart_projection_drift, which must be rebuilt or it never reaches the hosted copy)
 # and the lineup mart on the lineups `project` solved last (plan B1)
 hard projection-marts dbt_step projection-marts build --select mart_player_week_projections+ mart_projection_backtest+ mart_lineup_recommendation+ mart_projection_importance mart_player_role_alerts+ mart_waiver_upside mart_player_ros_projection mart_projection_record
 soft drift drift_if_unscored
+# ---- IZ-1 (Wave I-Z): us against Sleeper on past weeks (hh1.0; docs/METRICS.md): the live model's walk-forward rows when
+# missing (once per model version), the grade (ops.sleeper_h2h, /api/record `history`, About's sentence) and the one table
+# the run's summary shows (logs/sleeper_h2h.md). Soft: the hosted copy keeps last night's grade.
+rm -f logs/sleeper_h2h.md
+SOFT_WHY="the hosted copy keeps last night's grade" soft h2h uv run league-lab h2h --md logs/sleeper_h2h.md
+# ---- end IZ-1
 # ---- V-1 (Wave I-G): the decision record graded (the marts /api/record's `decisions` and the console's Record page read)
 SOFT_WHY="the hosted copy keeps last night's grade; the record itself is saved" soft decision-marts dbt_step decision-marts build --select mart_decision_record mart_decision_calls
 # ---- end V-1
```

**Publishing**: `ops` is published whole (`OPS_EXCLUDE` unchanged), so the four tables reach the hosted copy, ≈ 10.5 MB
(`ops.sleeper_history` ≈ 6.1, `ops.h2h_ours` 4.2, the rest < 0.3); recommended — the API reads `ops.sleeper_h2h` there,
and restore-state then never re-asks a week or refits the model. To keep the raw history out instead:
`OPS_EXCLUDE="… ops.sleeper_history ops.sleeper_history_weeks"` (a fresh database then replays the Actions-cache archive;
a lost cache re-asks the 58 weeks). Keep `ops.h2h_ours` published (else ~8.5 minutes every night).

**The first night**: `sleeper-history` 58 requests ≥ 1 s apart, ≈ 133 MB down, ≈ 2–4 minutes (estimate: no Sleeper
here); `h2h` ≈ 8.5 minutes (the live rows, measured here: 507 s) + the grade < 1 minute (estimate: the two-week dry run
1.2 s); +11 MB in the Actions cache, +10.5 MB on the hosted copy. Later nights: 0 requests (bar a failed week or a missed
snapshot), `h2h` about a minute; again ~8.5 minutes the first night of each new `MODEL_VERSION`.

## 7. Found, not mine

* `MODEL_VERSION` was not bumped for v3.1 / v3.2: rows built while cs1.1 was live are stamped "v3.0".
* This copy's `ops.calibration_oof` is v3.0 (2026-10-05); the nightly rebuilds it (`ensure_oof`), the copy never did.
* `http.fetch_to_archive` retries a 5xx / 429 up to 5 attempts with 1–16 s backoff: a week Sleeper answers 500 costs up
  to five requests that night (still polite; three such weeks in a row stop the pull).
* 11 failures in `api/tests/test_f3.py` / `test_m4.py` (on-demand vs nightly boards, My Week vs record totals) fail the
  same with `main`'s `ondemand.py` (this database's week state).
* The e2e fixture `record_1389709692405551104.json` is the "No week on the record yet" answer, so the constructed
  screenshot reads "the record above, from week 5 of 2026" under an empty record; on the live site the record has weeks.

## 8. Next

1. Read the first night's `h2h` table; where a position says "behind", the fix-or-borrow package starts from that
   position's weeks (and the clean record's, from week 5).
2. Andrew: the blend (bl1.0's word + the paragraph) — and Sleeper / RotoWire on the terms before any blended number.
3. Bump `MODEL_VERSION` with every model change (v3.1 / v3.2 lesson): `ops.h2h_ours` and `ops.calibration_oof` key on it.
