# IV-1 — the live week after its first kickoff, switched on (Wave I-V, Friday 2026-10-09)

Branch `dev/IV1` (from `main` e216f6a), worktree `/home/claude/wt-iq4`, database `league_lab_iq4`. The rule as it now
stands: docs/METRICS.md § "The live week after its first kickoff", **fr1.1**. The container restarted at ~16:55 ET;
what ran before it and what was run again after it is said at each number.

## 1. Done / not done / cut

With `LEAGUE_LAB_FREEZE=game`:

1. **Done — every stored table a live reader reads has its overlay**: `ops.projection_live` (house leagues, IU-2) and,
   new, `ops.projection_lines_live`, `ops.projection_ranges_live`, `ops.kd_lines_live`, `ops.kd_ranges_live` (K and DEF
   included): each `like` the table it overlays plus `team`, `game_kickoff`; tonight's rows of the week under way for
   the units whose game has not kicked off, through the same gate as the live week (who sits: every number 0 and the
   reason; a kicker who sits: 0); all five written in one transaction after the NFL-wide writer.
2. **Done — one place answers "his number for the week under way"**: `league_lab.live_week.sql` (a stored table's rows
   without an overlay row, plus the overlay's rows cast to the stored table's own columns by name). It is applied
   (a) in the API at the one place every statement passes, `db._run` — so every route follows it; (b) in `project`'s
   lineup reads (`lineup.load_inputs`, its K / DEF read), which the lineup and the waiver solves use; (c) by the audit;
   (d) house marts: `mart_player_week_projections` (IU-2's SQL). The live readers:
   - [x] public Rankings, week list — checked on the copy (§ 3)
   - [x] "Who should I start?" — checked on the copy
   - [x] `anyleague`'s freshest board, every on-demand league and reference scoring (its SQL goes through `db._run`)
   - [x] the league week boards (`mart_player_week_projections`)
   - [x] the card's week projection — checked on the copy (ref:half and League of Scrubs); its chart reads the same
     board / mart
   - [x] My Week / Team / Waivers at request time (they read `ops.lineups` / the solves, solved on live numbers, and
     the mart / board through `db._run`)
   - [x] the trade calculator's and Finder's this-week numbers (`trades` SQL through `db._run`) — **not checked on the
     copy** (needs a roster pair holding the BAL players; cut for the clock)
   - [x] matchup board, DFS, Compare (the board / mart through `db._run`)
   - [x] the season lists' current-week part (`load_window` through `db._run`) and the ROS mart (reads the mart)
   - [x] **the lineup and waiver solves inside `project`** (`lineup.load_inputs` live; a player whose game kicked off
     keeps his recorded number: no overlay row is written for him)
   - The graders **do not**: `ops.lineup_record` (its reconstruction now reads the kickoff board explicitly:
     `load_inputs(..., live=False)`), `context_record`, drift, `mart_projection_record`, odds grades and both freeze
     tests read the stored tables on their own connections, never through `live_week`. Proof in § 3.
3. **Done — the API follows the data**: no setting on Render. An overlay that does not exist, holds no row, or cannot
   be read: the statement runs unchanged, character for character (tests; and on the copy: all five overlay tables
   dropped → every route 200, the stored row).
4. **Done — across nights**: rule: a game that has kicked off keeps **the last live number written before its
   kickoff**, the same on every screen; the overlays are state (`STATE_TABLES` line in § 6); `db migrate` creates all
   five (`projections.NFL_DDL`); `fresh_db_check.sh` passes with the line applied (26 state tables). A week's overlay is
   read until the first nightly after the week's last kickoff, whose `project` finds no week under way and empties
   every overlay (for week 5: the nightly of Tuesday 13 Oct, 07:37 ET); from then the played week shows the kickoff
   board (the record). Size: § 3.
5. **Done — the Baltimore case on the copy** (§ 3): one number per player on every route checked. The sentence: a
   player cleared after a frozen week's first kickoff is no longer promised "his number this week comes with the next
   update" (false with `week`): "His status changed after this week's numbers were set at its first kickoff (…); there
   is no number for him this week." With `game` he has his number (his live row carries tonight's word, so he is not
   among last night's 0s). **Not done:** the "Starter unclear … Our projections assume the listing" sentence under
   `week` when the listing changed after the freeze (the number is Thursday's): with `game` it is true; with `week` it
   still is not — the starter module's sentence (§ 8).
6. **Done — the shadow stays**; with `game` it reports what was written ("live week: … moved … (written); overlay rows
   written: …").
7. Proof: § 3 and § 4.

## 2. Commits

* `3ac13bd` IV-1: item 1-3 — every stored table a live reader reads gets its overlay (NFL-wide lines / ranges / K-DEF lines / ranges, gated, one transaction); league_lab.live_week is the one place a rea
* `c1968ce` IV-1: items 5-6 — a player cleared after a frozen week's first kickoff is told what is true (no update brings his number this week); the shadow with game reports what was written; tests (liv
* `69cd8ba` IV-1: the rule as it now stands (fr1.1, METRICS), the frozen-week sentence (WORDS), CHANGELOG
* `d784bd1` IV-1: ruff (the API test's imports)
* `62bbf4a` IV-1: ruff (tests)
* `7e6f0ef` IV-1: the audit reads what a visitor sees (the live numbers through live_week where project wrote an overlay)
* the hand-back commit (this file, the comparison numbers)

## 3. Evidence

### Item 5 — the Baltimore case on the copy (`game` chain 16:44–16:54, routes checked 16:55–16:57, before the restart)

Made on the copy with the app's own inputs, after week 5's freeze (Thursday 20:15 ET): Lamar Jackson ruled Out in
Sleeper's directory (`raw.sleeper_player`, injury_status Out, dated 9 Oct 15:00 UTC) and Baltimore's starter set to
Tyler Huntley (`starter_overrides`, week 5) — both undone before the hand-back (§ 3, last part). BAL at ATL is Sunday
20:20 ET, not kicked off. Routes on the fixture API (port 8927, clock Saturday 10 Oct 16:00 UTC).

| | kickoff board | live | Rankings ref:half | League of Scrubs (Rankings) | card ref:half | card Scrubs | "Who should I start?" (ref:half) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tyler Huntley, QB (the new starter) | 4.76 | **20.78** | 20.78 (#2) | 20.78 (#2) | 20.78 | 20.78 | 20.78 |
| Lamar Jackson, QB (ruled out) | 16.77 | **0** (Out (ankle) · Sleeper, Oct 9) | Not playing: "Ruled out this week…" | Not playing | 0.0 | 0.0 | "Jackson is out — ruled out this week (Out (ankle) · Sleeper, Oct 9)." |
| Zay Flowers, WR (his receiver) | 12.08 | 12.09 | 12.09 (#11) | 12.09 (#11) | 12.09 | 12.09 | 12.09 |

One number per player. Huntley's line: passing yards 42.7 → 234.9, passing TDs 0.28 → 1.59 (the override reaches the
QB rows through `pn_qb_*`; the shadow names "teammate sits: Lamar Jackson (QB)"). Flowers barely moves: RB / WR / TE
read no QB input (a QB change reaches them only through the market's lines, unchanged on the copy) — the honest
limit of the model, not of the overlay. The trade calculator's line was not checked (cut).

Re-checked after the restart (17:37, the `week` chain's state, overlays dropped again, then recreated by `db migrate`):
Rankings ref:half and League of Scrubs, both cards, "Who should I start?", the ref:ppr season list — all 200, no
traceback, Huntley's card the stored 4.76.

With the five overlay tables **dropped** (the deploy before the nightly that creates them): every route answered 200,
no 500 in the log; ref:half showed the stored numbers (Huntley 4.76, Lamar 16.77, Flowers 12.08). League of Scrubs
still showed 20.78: its mart had been built with the overlay — on the hosted copy the mart and the overlays publish
together, so before that nightly both are the old ones.

### Item 7 — `week` (switch unset): 0 cells against `main`

Re-run after the restart (17:02–17:17): on the same database and inputs (the Baltimore case still in place, the
overlays empty), `league-lab project` + the nightly's projection-marts build once on `main`'s code (e216f6a; 424 s)
and once on this branch with the switch unset (369 s). Every table `project` writes and the projection marts, each
sorted on all its columns, run stamps left out (`<scratchpad>/iv1/snap.sh`, `cmp.sh`):

| | tables | rows | cells that differ |
|---|---:|---:|---:|
| `main` vs `dev/IV1`, switch unset | 34 (25 `ops` incl. the 5 overlays, 9 marts) | 214,174 | **0** |

The overlays stay empty with the switch unset, and an empty overlay leaves every statement unchanged, character for
character (`live_week.sql(text, ∅) == text` for every board statement — tested — and `db._run` asks no question for
a statement that reads no projection table), so the API runs `main`'s SQL: no screen answer changes **except the one
sentence item 5 asked to change** (a player cleared after a frozen week's first kickoff).

### The record: 0 cells between a `week` chain and a `game` chain

The `game` chain (before the restart, with the Baltimore case) against the `week` chain (after it, 17:17–17:30, the
case undone), the record's tables, weeks 1–5, run stamps left out:

| table | rows (weeks 1–5) | rows that differ |
|---|---:|---:|
| `ops.projections` | 6,032 | 0 |
| `ops.projection_lines` | 2,954 | 0 |
| `ops.projection_ranges` | 14,770 | 0 |
| `ops.kd_lines` | 316 | 0 |
| `ops.kd_ranges` | 1,580 | 0 |
| `ops.lineup_record` | 2,249 | 0 |
| `ops.context_record` | 4,620 | 0 |
| `ops.projection_drift` | 32 | 0 |
| `mart_projection_record` | 10 | 0 |
| `mart_projection_drift` (whole) | 8 | 0 |

**0 cells of the record differ**: the kickoff board is what the graders read under both switches (and a ruling and a
starter change after the freeze do not reach it).

### Chains (last lines)

**`game`** (`LEAGUE_LAB_FREEZE=game /home/claude/waveIT/chain.sh /home/claude/wt-iq4 league_lab_iq4`, 16:43–16:54,
before the restart — the machine's uptime puts the restart at 16:59; this chain had finished at 16:54 and its snapshot,
the item 5 route checks and the dropped-tables check were done by 16:57):

```
== 16:43:59 db migrate
== 16:44:00 dbt build (full)
20:48:40  Done. PASS=733 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=738
== 16:48:40 project
== 16:53:31 projection marts
20:53:42  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 16:53:43 availability guards (as errors)
20:53:50  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 16:53:50 audit
## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
== 16:53:58 done
chain seconds: 599
== 16:54:02 END
```
fr1.0 step: `written_by_table` projection_live 1,104 · projection_lines_live 524 · projection_ranges_live 2,620 ·
kd_lines_live 56 · kd_ranges_live 280 (0.41 s). The audit read the live numbers (`live_week`): 237 who cannot play
(Lamar Jackson among them), **0 ranked or valued**.

**`week`** (switch unset, re-run after the restart, 17:17–17:30, the Baltimore case undone):

```
== 17:17:05 db migrate
== 17:17:07 dbt build (full)
21:23:55  Done. PASS=733 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=738
== 17:23:55 project
== 17:29:58 projection marts
21:30:12  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 17:30:12 availability guards (as errors)
21:30:21  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 17:30:22 audit
## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
== 17:30:27 done
chain seconds: 802
== 17:30:32 END
```
ERROR 0 in every step of both; both availability guards as errors PASS 2.

### Timings and sizes

* `project` with `game` (the `game` chain, before the restart): 291 s (16:48:40 → 16:53:31; the nightly's step is
  4m09s); with the switch unset, in the `week` chain after the restart: 363 s (a cold machine); its fr1.0 step 0.41 s, writing 4,584 overlay rows. With the switch unset the same step (the shadow) takes
  0.3–0.4 s. What `game` adds beyond that: one more read of the lineup inputs (the record's, from the kickoff board)
  when an overlay is active — seconds. Wall times of `project` on this box after the restart ran 369–424 s with the
  switch unset (a cold machine), so no difference between the switches can be read from wall clocks; the measured
  step is under half a second.
* Overlay rows for week 5 on the copy (14 games left): `projection_live` 1,104, `projection_lines_live` 524,
  `projection_ranges_live` 2,620, `kd_lines_live` 56, `kd_ranges_live` 280. Size by the stored tables' own bytes per
  row (484 / 295 / 243 / 346 / 248 B): ≈ 0.53 + 0.15 + 0.64 + 0.02 + 0.07 ≈ **1.4 MB**, ≈ 1.6 MB for a full 16-game
  week, so ≈ 3 MB while a publication holds two copies (of the 1 GB plan; `sync_to_hosted.sh` dumps all of `ops`).
  Empty with the switch unset (five empty tables, 8 kB each).

## 4. Tests

All re-run after the restart, on the final code:
* `tests/test_iv1_live.py` (12, new: the rewrite is the identity with no active overlay — every board statement; every
  `from` / `join` form; only active overlays; the key and the cast; `active` on tuple and dict rows; every overlay
  `like` its table and created by migrate after it; the NFL-wide live rows gated, Thursday's game left out),
  `tests/test_iu2_freeze.py` (17, extended: the shadow with `game` reports what was written), `tests/test_nfl_wide.py`
  (the overlays are not in the freeze-label check; the STATE_TABLES check excludes them until the PO's line lands).
* `api/tests/test_iv1.py` (7, new: no overlay table / empty / unreadable → the statement unchanged, never a 500; read
  once per publication and dropped with one; the frozen-week sentence and its "Who should I start?" form).
* `scripts/gate.sh python`: **GATE PASSED** (root 783, api 36, ruff). `check_root.sh`: 1,743 passed, 4 failed — all in
  the known list, **0 new**. `uv run ruff check src app tests api`: clean. Copy standard: clean (exit 0).
* The API test files of every route the change touches — `db._run` is every route, so the 61 files that exercise
  the rankings, card, start, My Week, Team, Waivers, trades, research and on-demand routes (list:
  `grep -l "rankings_api\|/api/rankings\|load_inputs\|from league_lab import lineup\|_live_sql\|/api/player/\|/api/my-week\|/api/team\|/api/waivers" api/tests/*.py`):
  862 passed, 85 failed, 19 skipped (624 s). 75 of the 85 are in `known_api_failures.txt`; the other 10 —
  `test_decisions::test_waivers_house_route_is_the_mart` ×2, `test_f3::test_player_card_ros_is_the_marts` ×2,
  `test_ib2::test_nothing_to_claim_dynasty`, `test_inf1::test_waivers_deadline_answers_the_pinned_moment`,
  `test_ib0::…would_not_start[None]`, `test_ig2` ×3 — **fail the same way on `main`'s code** on this database (run at
  17:43 with `src` / `api` checked out at e216f6a): they read the week the copy's stored waiver moves and lists are for
  (5 tonight, the tests expect 4) or are the copy's known environment failures (ib0, ig2). **New failures from IV-1:
  none.**
* `fresh_db_check.sh` with the `STATE_TABLES` line applied: every state table exists after `db migrate` (26).
* No `web/` change: no lint / build / e2e run.

## 5. Edits outside my files

Each marked `# ---- IV-1`:
* `api/league_lab_api/db.py` — `_live_sql` (one region `live_overlay`, 1 entry, 10 minutes, dropped with a
  publication) and its call in `_run`; `clear_cache` clears it. The one place the API applies `live_week`.
* `api/league_lab_api/rankings_api.py` — `BACK_FROZEN_WORDS`, `_week_frozen`, the gate's `frozen`, `_out_words`'s
  branch (the payload's shape unchanged).
* `src/league_lab/lineup.py` — `load_inputs(..., live=True)` and the K / DEF read through `live_week`; `lineups()`
  hands the record writer the kickoff board's inputs when an overlay is active.
* Mine: `src/league_lab/live_week.py` (new), `projections.py` (the overlays' DDL, `nfl_live_rows`,
  `_write_overlays`, `_clear_live` for all five, the step after the NFL-wide writer), `audit.py`, `cli.py`
  (freeze-shadow), tests. Docs: METRICS (fr1.1), WORDS (one row), CHANGELOG (Wave I-V).
* Not touched: `web/` (no screen changes shape; the sentence is the API's).

## 6. PO lines

**`.github/workflows/nightly.yml`** (the nightly step's env):

```diff
--- a/.github/workflows/nightly.yml	2026-10-09 16:47:59.291485248 -0400
+++ b/.github/workflows/nightly.yml	2026-10-09 16:47:59.322861424 -0400
@@ -211,6 +211,11 @@
           # keeps nothing and the same run publishes by the drop path, as before. Rollback = delete these two lines.
           LEAGUE_LAB_HOSTED_PUBLISH: auto
           LEAGUE_LAB_HOSTED_CAP_MB: "800"
+          # Wave I-V (IV-1): the live week (fr1.1; docs/METRICS.md § "The live week after its first kickoff"). `project`
+          # re-projects the week under way's games that have not kicked off into the overlays (ops.*_live); every request
+          # follows what is stored, so Render needs no setting. Rollback = delete these lines: the next nightly's
+          # `project` empties every overlay and every screen reads the kickoff board again (as before IU-2).
+          LEAGUE_LAB_FREEZE: game
         run: ./scripts/nightly.sh ${{ inputs.full && '--full' || '' }}
 
       # Save the archive only when its content changed (the key is a fingerprint of every data
```

**`scripts/nightly.sh`** (`STATE_TABLES`):

```diff
--- a/scripts/nightly.sh	2026-10-09 16:47:59.283957647 -0400
+++ b/scripts/nightly.sh	2026-10-09 16:47:59.322683309 -0400
@@ -288,6 +288,11 @@
 STATE_TABLES="$STATE_TABLES ops.horizon_record"
 RECORD_TABLES="$RECORD_TABLES ops.horizon_record"
 # ---- end IU-5
+# ---- IV-1 (Wave I-V): fr1.1, the live week's overlays (LEAGUE_LAB_FREEZE=game): a game that kicked off keeps the last
+# live number written before its kickoff until the week is over, so they are state (not record: no grade reads them).
+# `db migrate` creates them; a copy that does not have them yet is "not published there"; empty with the switch unset.
+STATE_TABLES="$STATE_TABLES ops.projection_live ops.projection_lines_live ops.projection_ranges_live ops.kd_lines_live ops.kd_ranges_live"
+# ---- end IV-1
 
 is_record() { case " $RECORD_TABLES " in *" $1 "*) return 0;; esac; return 1; }
 
```

The Mac: `LEAGUE_LAB_FREEZE=game` in its `.env` if its nightly publishes.

**The way back.** Delete the env line. The next nightly restores the overlays from the hosted copy (state), then its
`project` runs with the switch unset and **empties all five overlays** (`_clear_live`, logged "switch is week: …
emptied (N rows an earlier game run left)"), builds the marts on the stored rows, and publishes the empty overlays:
from that publication every screen reads the kickoff board again, exactly as before IU-2 (§ 3: 0 cells against
`main`). Until that nightly publishes, the screens keep the last live numbers. The `STATE_TABLES` line can stay (five
empty tables) or go.

## 7. Found, not mine

* Every two full chains on this copy re-project the live weeks 6–18 a little differently whatever the code or the
  switch (IU-2 § 7; tonight again: hb1.0's horizon weights printed {3: 0.5, 4: 0.25, 5: 0.35, …} in the `game` chain).
  The kept weeks never differ. IU-5's calibration; reported, not touched.
* The "Starter unclear … Our projections assume the listing: Huntley as the starter" sentence is true with `game` (the
  number assumes the listing) and false with `week` when the listing changed after the freeze (the number is
  Thursday's backup line). The starters module's sentence; I left it (§ 8).
* Not mine and not a defect: with the overlays dropped, a house league still shows the live number its mart was built
  with — the mart and the overlays are published together, so the hosted copy never holds one without the other.

## 8. Next

1. PO: apply the two lines (§ 6) before Saturday's 07:37 nightly; that nightly is the first `game` run and covers
   every Sunday and Monday game of week 5. Read its run summary's "fr1.0 live week" block (who moved and why).
2. The starter sentence under `week` (§ 7), and a word on the card for a live number ("updated tonight: Huntley
   starts") if the PO wants the change visible.
3. Check the trade calculator's this-week line on a roster pair (cut tonight), and, once a week has run under `game`,
   compare its live numbers with the kickoff board on what the players scored (the study fr1.0 could not date).
