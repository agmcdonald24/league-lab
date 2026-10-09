### IT-5 — the quarterback beyond next week: who still starts (Wave I-T, 2026-10-09, 03:13–03:30 ET)

**Task**: IT-5 of `/home/claude/waveIT/BRIEF.md`. **Branch**: `dev/IT5` from `main` `7341acc`. **Worktree**:
`/home/claude/wt-ip1`. **Database**: `league_lab_im1` (read only tonight: the study reads, writes nothing).
**Result**: **nothing ships.** The candidate the brief names (rf1.0) fails clauses (b), (c) and (d) of the rule written
and committed before any candidate number. No production change; `MODEL_VERSION` stays v3.6; no switch added.

#### 1. Done / not done / cut

* Done: the rule with v3.6's own numbers on the same rows and ud1.0 for quarterbacks re-graded on v3.6's rows,
  committed first; the candidate rf1.0 (and rf1.1, graded but not eligible) beside the three baselines; the
  reliability table of the probability; the full five-season study (2021–2025, h 2–8, both house scorings); one
  post-hoc reading (rf1.2), defined and committed before its run and labelled not eligible; tests of the harness's
  mixture.
* Not done, by the rule: v3.7 in production, `LEAGUE_LAB_ROLE_FORECAST`, the version bump, provenance / `ros_grade`
  updates, the chain run (nothing the nightly reads changed), the top 20 after (nothing to show after).
* Cut: none for the clock. Not usable from the warehouse tonight: age, tenure as the starter, hand-set / disputed
  starter history, the team's record, a rookie behind him (METRICS § v3.7 "Not usable tonight").

#### 2. Commits (in order; the rule's first)

1. `4f39b88` 03:20:35 — **the rule**: docs/METRICS.md § "v3.7: the role forecast (IT-5)" (clauses (a)–(e), v3.6's
   numbers on the same rows, ud1.0 re-graded) + `scripts/analysis/it5_role.py` with rf1.0 / rf1.1 defined. Before
   this commit only `cache` (inputs, no lines) and `v36` (v3.6's own numbers) had run.
2. `57d475c` 03:22:40 — the harness's prior lookup restricted to the scored seasons (the first study run crashed on a
   2018 key before printing any points: only the base rates and the reliability tables were out); rf1.2 defined post
   hoc before its run.
3. `015ba18` 03:25:32 — the result in METRICS § v3.7; `tests/test_it5_role_mix.py`.
4. (this) — hand-back and CHANGELOG.

#### 3. Evidence

**v3.6 on the study's rows** (reproduces IQ-3 exactly): 2–8 weeks MAE 7.328 / 6.894 / 7.398 / 7.620 / 7.790, pooled
**7.406**; Spearman .519 / .533 / .518 / .478 / .426, pooled **0.4948**; the market week 6.421 / 0.596.

**ud1.0, quarterbacks** (Half PPR, W 3/5/7/9, four weeks, top 24, close pairs ≤ 20 %): the model alone (IR-4's rows)
3,680 pairs, **0.594 / 0.615** — IR-4 reproduced exactly; v3.5 (pt1.0) 3,776, 0.597 / 0.617 (1 of 5); **v3.6 3,999,
0.613 / 0.595, above both 50 % and his own record in 4 of 5 seasons** (2021 .601/.598, 2022 .590/.600, 2023 .655/.599,
2024 .625/.583, 2025 .595/.594).

**The probability, calibration first** (2021–2025 out of sample; forecast / observed by decile):

| decile | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | Brier (base rate) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| starter still starts (3,750) | .40/.48 | .64/.64 | .73/.74 | .78/.77 | .82/.81 | .86/.85 | .89/.87 | .91/.93 | .94/.92 | .97/.94 | 0.145 (0.164) |
| non-starter starts (6,320) | .03/.06 | .04/.04 | .06/.06 | .07/.08 | .08/.10 | .09/.11 | .10/.13 | .12/.11 | .17/.19 | .41/.34 | 0.099 (0.106) |

By horizon (forecast / observed): starter h2 .904/.897, h3 .852/.846, h4 .810/.817, h5 .774/.782, h6 .756/.763, h7
.748/.742, h8 .709/.714; non-starter h2 .056/.062 … h8 .165/.162.

**Points, 2–8 weeks pooled, both house scorings (MAE / Spearman)**:

| season | v3.6 | starter keeps the job | **rf1.0** | rf1.1 (not eligible) | rf1.2 (post hoc) | oracle |
|---|---|---|---|---|---|---|
| 2021 | 7.328 / .519 | 7.328 / .519 | 7.103 / .525 | 7.560 / .521 | 7.274 / .526 | 6.653 / .572 |
| 2022 | 6.894 / .533 | 6.894 / .533 | 6.901 / .531 | 6.766 / .545 | 6.751 / .532 | 6.366 / .526 |
| 2023 | 7.398 / .518 | 7.398 / .518 | 7.375 / .529 | 7.270 / .530 | 7.291 / .523 | 6.853 / .543 |
| 2024 | 7.620 / .478 | 7.620 / .478 | 8.146 / .460 | 7.733 / .456 | 7.555 / .480 | 7.471 / .486 |
| 2025 | 7.790 / .426 | 7.790 / .426 | 7.941 / .422 | 7.995 / .426 | 7.806 / .427 | 7.129 / .493 |
| pooled | **7.406 / .4948** | 7.406 / .4948 | **7.493 / .4935** | 7.465 / .4956 | 7.336 / .4974 | 6.894 / .5240 |
| ud1.0 QB | 0.613 | 0.613 | **0.603** | 0.627 | 0.611 | 0.628 |

By horizon, v3.6 → rf1.0 → oracle: h2 7.178/.544 → 7.196/.555 → 6.982/.547; h3 6.768/.527 → 6.782/.538 → 6.305/.557; h4
7.391/.471 → 7.454/.466 → 7.043/.491; h5 7.395/.523 → 7.507/.521 → 6.822/.554; h6 7.705/.466 → 7.908/.446 →
7.280/.476; h7 7.535/.471 → 7.516/.490 → 6.701/.528; h8 7.871/.462 → 8.089/.439 → 7.127/.515. Each league alone (the
study's output; Half PPR: v3.6 6.227 / .499, rf1.0 6.298 / .497; dynasty 8.585 / .491 → 8.688 / .490).

**Against the rule**: rf1.0 (a) 0 cells — holds; (b) 7.493 vs 7.406, lower in 2 of 5 (Δ −0.224 / +0.006 / −0.023 /
+0.526 / +0.151) — **fails**; (c) 0.4935 vs 0.4948 — **fails**; (d) 0.603 vs 0.613 — **fails**; (e) QB-only — holds.
rf1.2 (post hoc, not eligible) passes (a)–(c) and fails (d) (0.611 vs 0.613). The oracle passes all (the ceiling).

**Why** (read after the run): the grade scores QBs who played in week T; a market-week starter who played was still
the starter 93–98 % of the time by season, while rf1.0's unconditional p averages about 0.79 on those rows, so every
continuing starter is pulled about a fifth of the way toward a backup's line, and the starters who lost the job are
mostly not scored. 2024 is worst (starters' rows 7.432 → 8.306): veterans on new teams kept the job while the
forecast doubted them (2024 rows: Rodgers p 0.58 over 25 rows, Darnold 0.61, Maye 0.60). On the market week's
non-starters rf1.0 helps (7.283 → 7.109, 4 of 5). The oracle's 0.512 of MAE is almost all on non-starters (7.283 →
5.951; starters 7.452 → 7.387).

**A defect in the candidate as run**: the "injury designation" input is always 0 on the later-week rows
(`iq1_horizon.future_rows` writes `questionable = 0` for h ≥ 2); its coefficient is 0.000. The market week's own
designation (the h = 1 row) was the one meant. It does not change the decision (it was the rule's candidate as run).

**Face validity**: nothing ships, so no list changes; the rest-of-season QB top 20 on `league_lab_im1` is v3.6's as
IQ-3 left it. Not re-shown.

#### 4. Tests

* `tests/test_it5_role_mix.py` 4 passed (the target week's role, "keeps the job" = v3.6 bit for bit, the market week
  never moves, the per-role mixture, a season outside the grade keeps v3.6) + `tests/test_metric_registry.py` 3 passed.
* `uv run ruff check src app tests api scripts`: clean. `scripts/copy_standard.py --check`: clean (rc 0).
  `scripts/gate.sh python`: GATE PASSED (56 s; api decision suite 29 ran, 0 failed).
* Not run: `check_root.sh` and the calibration test files (no `src/` edit); the API suite (rule 7); the chain (nothing
  the nightly reads changed: no `src/`, dbt, seed or table change).
* Reproducibility: `study` and `v36` re-run at 03:27 — byte-identical output.

#### Commands and run times (one thread each, one at a time)

| command | ran | took |
|---|---|---|
| `OMP_NUM_THREADS=1 uv run python scripts/analysis/it5_role.py cache --out <scratch>/it5/q.parquet` | 03:17:06–03:18:54 | 108 s (31,640 rows, 2017–2025) |
| `… it5_role.py v36 --cache <scratch>/it5/q.parquet` | 03:19:04–03:19:16 | 12 s |
| `… it5_role.py study --cache …` (crashed before any points: base rates and reliability printed) | 03:20:42–03:20:48 | 6 s |
| `… it5_role.py study --cache …` (rf1.0, rf1.1, baselines) | 03:20:57–03:21:27 | 30 s |
| `… it5_role.py study --cache …` (+ rf1.2 post hoc) | 03:22:47–03:23:17 | 30 s |
| a scratch diagnosis (p by season, 2024's lowest p, coefficients) | 03:23 | ~30 s |
| re-run `study` and `v36` (determinism) | 03:27:20–03:28:00 | 40 s |
| `scripts/gate.sh python` | 03:25:59–03:26:55 | 56 s |

Much faster than the brief's 2–3× warning: the machine was quiet at this hour.

#### 5. Edits outside my files

`CHANGELOG.md` (one bullet under a new top heading `## 2026-10-09 — Wave I-T`). Nothing else outside
`scripts/analysis/it5_role.py`, `tests/test_it5_role_mix.py`, `docs/METRICS.md` § v3.7, this file.

#### 6. The PO's lines I need (none required; one recommended, the PO's call)

The live About / provenance still says quarterbacks are "no better than his own record" (v3.5-era rows) and lists
"quarterbacks' useful-decision grade on the current version" as not graded. On v3.6's rows it is graded now. If the PO
accepts the re-grade (it uses ud1.0's definition unchanged; the pair set follows the calculator's own top 24):

```diff
--- api/league_lab_api/provenance.py
-    "quarterbacks' useful-decision grade on the current version (it was measured on the version before)",
-# scored more over those four weeks, against the side his own per-game record favours. QB rows are v3.5's.
-USEFUL = {"QB": {"pairs": 3680, "rate": 0.594, "base": 0.615, "seasons": 0, "useful": False},
+# scored more over those four weeks, against the side his own per-game record favours. QB rows are v3.6's (IT-5,
+# scripts/analysis/it5_role.py v36; on v3.5's rows 3,680 pairs, 0.594 against 0.615).
+USEFUL = {"QB": {"pairs": 3999, "rate": 0.613, "base": 0.595, "seasons": 4, "useful": True},
--- src/league_lab/context_record.py (line 1666)
-    "QB": (3680, 0.594, 0.615, 0), "RB": …
+    "QB": (3999, 0.613, 0.595, 4), "RB": …
```

and `USEFUL_WORDS`' quarterback clause rewritten (its "but the side his own per-game record favours did better" would
then be false): e.g. "… and {QB rate} at quarterback — more often than the side his own per-game record favours ({WR},
{RB}, {TE} and {QB base})." — plus WORDS.md and whatever API test pins the old QB sentence (I did not search the API
tests; `ops.context_grade` kind `useful` is rewritten by `context-record` from `USEFUL_GRADES`).

#### 7. Found, not mine

* `iq1_horizon.future_rows` sets `questionable = 0` on every later-week row (h ≥ 2) — right for the trees (the nightly
  has no report for a later week) but any study that wants the market week's designation must read the h = 1 row.
* The MAE / Spearman board grades only the QBs who played in week T, so it cannot reward a forecast that a starter
  will not play; ud1.0 counts a missed week as 0 and can. The two grades pull in opposite directions for an
  unconditional role forecast (rf1.0 loses on both, rf1.1 gains on ud1.0 and loses MAE).

#### 8. Next

1. A forecast for the market week's backups only, graded on seasons it was not chosen on (rf1.2 reads 7.336 / 0.4974
   but fails ud1.0 by 0.002 and was chosen after rf1.0's numbers).
2. Better inputs: the market week's injury designation and practice status (the h = 1 row), age (players' birth
   dates), the team's record (the schedule's results), a QB drafted in rounds 1–2 this year, a starter new to his team
   (2024's misses).
3. A horizon grade that counts a week he did not play as 0 (as ud1.0 does), so a forecast of who plays can be
   rewarded — and production's later weeks would then need a play probability too.
