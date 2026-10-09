### IU-5 — a grade that can reward the right quarterback forecast, and this season's own record (Wave I-U, 2026-10-09, 13:43–14:30 ET)

**Task**: IU-5 of `/home/claude/waveIU/BRIEF.md` (continues IT-5). **Branch**: `dev/IU5` from `main` `99fb216`.
**Worktree**: `/home/claude/wt-ip1`. **Database**: `league_lab_im1` (the only writer). Started 13:43 ET (the package
reached me then); hard stop 14:30.

#### 1. Done / not done / cut

* Done: (1) the grade hg1.0, its cases and "better", committed before any number on it; (2) v3.6, "the starter keeps
  the job", rf1.0 and the oracle on hg1.0 (information); (3) **the recorded forecast rr1.0 in production**: each
  nightly's `context-record` stores every QB's probability of starting in week M … M+7 with v3.6's line and the
  mixture's line in `ops.horizon_record` (created by `db migrate`), and grades the stored rows on hg1.0 as weeks are
  played (`ops.context_grade` kind `role_record`); (5) the chain on my copy.
* **Cut for the clock: item 4** (the same record for RB / WR / TE 2–8 week lines). The design is the same table with
  `p_start` NULL and the position's v3.6 line; about 1,600 rows a market week more (≈ 7 MB a season). Not built.
* Not done: an interval on the record's grade (it stores n, the two misses, their difference and the Brier scores; a
  player-resampled interval is the next step before anyone reads it as evidence).

#### 2. Commits (the rule's first)

1. `9cb8afb` 13:46:31 — **the rule**: docs/METRICS.md § "The horizon grade that counts a missed week (IU-5)" (hg1.0, the
   cases, "better", the recorded forecast's definition) + `scripts/analysis/iu5_grade.py`. No number on hg1.0 existed.
2. `723eed4` 13:47:27 — the four lines on hg1.0 (information) in METRICS; ruff's `zip(strict=)` in the harness (no
   definition change).
3. `63bf32a` 13:50:50 — rr1.0: `calibration.py` (block `# ---- IU-5`), `context_record.py` (the horizon part, and two
   marked hooks in `run` / `write_grade`), `tests/test_iu5_role_record.py`.
4. `c9517bc` 13:53:21 — METRICS (the record: where, size, publication, when), CHANGELOG.
5. `5ac26af` 14:08:49 and the last — this hand-back.

#### 3. Evidence

**hg1.0** (the full definition in METRICS). A later-week QB row (h 2–8) counts his points if he played; **0** if he
did not play and was healthy on a roster (`ACT`, `INA`, `DEV`) or cut / retired with a row; **excluded** on a bye (no
row), when week T's report says Out / Doubtful / Questionable or his roster status is `RES`, or any other status.
"Better": MAE lower pooled and in ≥ 4 of 5 seasons, Spearman pooled not lower. On 2021–2025's rows: played 4,542,
healthy and not playing 4,463 (3,985 of them market-week backups), injured 1,065 excluded.

**The four lines on hg1.0** (`iu5_grade.py`, 24 s; MAE / Spearman, both house scorings):

| season | v3.6 | the starter keeps the job | rf1.0 | the oracle |
|---|---|---|---|---|
| 2021 | 6.395 / .672 | 6.395 / .672 | 6.575 / .680 | 5.260 / .796 |
| 2022 | 6.371 / .660 | 6.371 / .660 | 6.565 / .666 | 5.230 / .789 |
| 2023 | 6.611 / .631 | 6.611 / .631 | 6.864 / .633 | 5.551 / .783 |
| 2024 | 6.845 / .653 | 6.845 / .653 | 7.411 / .627 | 6.460 / .702 |
| 2025 | 6.730 / .682 | 6.730 / .682 | 7.078 / .681 | 6.044 / .778 |
| pooled | **6.590 / .6596** | 6.590 / .6596 | **6.899 / .6572** | 5.709 / .7696 |

**What hg1.0 would have decided**: rf1.0 not better (MAE higher in 5 of 5, Δ +0.181 … +0.567; Spearman lower); the
oracle better by 0.88 of MAE. The grade rewards knowing **who plays at all**: half its rows are healthy QBs who did
not play (mostly backups), and v3.6 and rf1.0 both give a backup his "if he plays" line. A forecast built for hg1.0
needs a play probability for the market week's backups, not only a start probability.

**The record in production (rr1.0)** on `league_lab_im1` (`write_horizon_record` alone, 13:49:40):

* market week 6 (the first week whose first kickoff is after now), 606 rows (85 QBs at h = 1; byes leave fewer), 139 KB
  with its index; 16.4 s to write, 1.3 s to grade (0 grade rows: no stored week T is played yet).
* Mean p_start by h 0.33–0.35 (all QBs, backups included); h = 4 top by the mixture: Prescott p 0.925, 20.0 → 18.8;
  Mahomes 0.937, 19.6 → 18.6; Allen 0.965, 18.3 → 17.7; Purdy 0.930; L. Jackson 0.901; Stafford 0.922; Lawrence
  0.904; Jayden Daniels (listed non-starter in week 6) 0.259, 15.5 → 15.7; Maye 0.861; Watson 0.875; Stroud 0.843;
  Keenum 0.883.
* Size per season ≈ 8,000 rows, about 2 MB. **It rides the publication** (`sync_to_hosted.sh` dumps `ops.*`: two
  copies during a swap, about 4 MB at a season's end) **and is kept state** (restored each night) once the PO adds it
  to `STATE_TABLES` / `RECORD_TABLES` (diff below).
* **First graded rows**: week 6's h = 2 rows are week 7 (last game Mon 26 Oct 20:15 ET); a week is graded 12 hours
  after its last kickoff once its stats are loaded → the first nightly after Tue 27 Oct 08:15 ET (in practice Wed 28
  Oct). **The 4-of-5 form can never be read on 2026 alone** (one season). What can be said: the probability's
  calibration from about mid-season (target weeks 7–12 graded, early December; ~2,000 QB-weeks, but the same players
  repeat across market weeks and horizons); the mixture against v3.6 on hg1.0 as one out-of-sample season with a
  player-resampled interval after week 18 (mid-January 2027) — evidence, not a ship decision.

**The chain** (`/home/claude/waveIT/chain.sh /home/claude/wt-ip1 league_lab_im1`):

```
== 13:51:05 db migrate
schemas and ops tables are in place
== 13:51:09 dbt build (full)
17:56:45  Done. PASS=732 WARN=6 ERROR=0 SKIP=0 NO-OP=0 TOTAL=738
== 13:56:46 project
13:56:58 INFO league_lab.calibration: fi1.0: market week 5; later weeks' lines from the teams' own season (7349 rows, shrink 3.0 games), personnel of the market week (444 rows moved)
14:01:33 INFO league_lab.calibration: hb1.0: market week 5; QB weeks after it blended with the naive line, weight by horizon {2: 0.0, 3: 0.5, 4: 0.25, 5: 0.35, 6: 0.75, 7: 0.95, 8: 0.75} (lambda 0.25, k 6.0); 1061 QB lines moved
14:01:46 INFO league_lab.availability_gate: availability gate: week 6, Sleeper directory (copy of 2026-10-05T12:00:39.609393Z): 77 players who cannot play or are unlikely to play get 0 this week (77 of them out indefinitely: no later weeks)
projected 19844 rows for 2026 (2 league(s), weeks 1-18); wrote 13572 (weeks [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]), kept frozen weeks [1, 2, 3, 4, 5]
== 14:02:28 projection marts
18:02:42  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 14:02:42 availability guards (as errors)
18:02:51  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 14:02:52 audit
## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
== 14:02:57 done
```

ERROR 0 in every step; 11 min 52 s in all. `chain.sh` does not run `context-record`, so I ran the nightly's real step
after it (`uv run league-lab context-record`, 14:07:30–14:07:56): **25 s in all, of which rr1.0 about 10 s** ("rr1.0:
606 role-record rows written"), `ops.context_grade` 216 rows (0 of kind `role_record`: nothing to grade yet), no
error. **Added: about 10 s a night and about 140 KB a market week (about 2 MB a season).** A plumbing check of the
grader on real rows (a pretend run as of 2026-09-20, market week 3, then deleted): 82 graded QB-weeks in week 4 (h = 2;
week 5 not yet graded — its last game is Monday), the `role_record` rows and sentence written. Not evidence: the stored
"v3.6" line of week 4 is the frozen week-4 board, not a projection made three weeks earlier.

#### 4. Tests

* `tests/test_iu5_role_record.py` 4 passed (the target week's role in the training rows, v3.6 beside the mixture and a
  bye with no row, hg1.0's cases, `db migrate`'s DDL).
* The existing test files of the modules I edited: `test_io1_context_record`, `test_ip3_trend_record`,
  `test_calibration`, `test_iq3_horizon_blend`, `test_iq1_future_inputs`, `test_it5_role_mix`: 60 passed.
* `check_root.sh`: 1,709 passed, 3 skipped, 4 failed — all four in the known list, **no new failure** (94 s).
* `ruff check src app tests api scripts` clean; `copy_standard.py --check` clean; `scripts/gate.sh python` GATE PASSED
  (49 s). The API suite not run (rule). No `web/` change.

**Run times**: `iu5_grade.py` 24 s; `write_horizon_record` alone 16.4 s (+ 1.3 s grade); the chain 11 min 52 s;
`context-record` 25 s; `check_root` 94 s; gate 49 s.

#### 5. Edits outside my files

`CHANGELOG.md` (one bullet under `## 2026-10-09 — Wave I-U`). `context_record.py`'s `run` and `write_grade` (IO-1's)
each gained one marked `# ---- IU-5` hook that catches its own failure. Not `projections.py`, not `db.py` (the table's
DDL is appended to `context_record.DDL`, which `db migrate` already runs).

#### 6. The PO's lines (needed for the record to persist from night to night)

```diff
--- scripts/nightly.sh
 STATE_TABLES="$STATE_TABLES ops.context_record ops.context_grade"
 RECORD_TABLES="$RECORD_TABLES ops.context_record"
 # ---- end IO-1
+# ---- IU-5 (Wave I-U): the role record (rr1.0, a recorded forecast of who starts 1-8 weeks out; kept like the
+# context record; context-record writes and grades it)
+STATE_TABLES="$STATE_TABLES ops.horizon_record"
+RECORD_TABLES="$RECORD_TABLES ops.horizon_record"
+# ---- end IU-5
```

Without it the step still runs and never fails, but a fresh runner database starts the record again every night (the
market week's rows are rewritten until its kickoff anyway; the earlier market weeks would be lost). `project` does not
call my code: no line in `projections.py`.

#### 7. Found, not mine

* `chain.sh` does not run `context-record`, so the chain does not exercise a write that lives there; I ran the write
  alone on my copy (above) and `db migrate` (in the chain) creates the table.
* On this copy `project` treats week 5 as the market week (frozen at its first kickoff, games not all played) while the
  record's market week is 6 (the first week not kicked off): between a week's first kickoff and its last game, the
  record's h and hb1.0's own horizon differ by one. The record stores v3.6's line as the nightly wrote it, so the
  comparison is what was on the board; the IU-2 game freeze (if switched on) would change which lines those are.
* `ops.context_grade`'s columns are named for the corner grade; the `role_record` rows reuse `mean_miss` (the mixture),
  `rest_beat_share` (v3.6), `vs_rest`, `beat_share` (Brier), `lo` (the base rate's Brier) — documented in METRICS.

#### 8. Next

1. A player-resampled interval on the `role_record` grade, and a reliability table by quintile, before anyone reads it.
2. A play probability for backups (the piece hg1.0 says matters most), defined now and graded on 2026–2027 only.
3. Item 4: the same record for RB / WR / TE.
