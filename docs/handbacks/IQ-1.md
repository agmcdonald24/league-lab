### IQ-1 2026-10-07 — hotfix: rest-of-season quarterbacks, v3.5 (branch `dev/IQ1` from `main` `618bcd4`, database `league_lab_im1`)

* **Task**: the PO's IQ-1 brief: the live rest-of-season QB list was re-ordered (Murray 2nd, Willis 3rd, Lamar 18th,
  Burrow 17th; top 24 by the week-5 projection against the weeks 6–18 mean: QB 0.15, RB 0.90, WR 0.94, TE 0.86).
* **The rule** (METRICS § "v3.5", written at 16:52 ET and committed `1e5920a` before any candidate number was read):
  QB pooled horizons 2–8 MAE lower in ≥ 4 of 5 seasons, QB pooled Spearman not lower, RB / WR / TE pooled MAE not worse
  by > 0.01; the market week unchanged unless said; of several passing, the largest QB gain ships.

#### Diagnosis (`scripts/analysis/iq1_horizon.py diagnose`, 2026 as of week 5)

* Top-24 rank correlation, week 5 against the later weeks: 0.44 (the mart's rows) → 0.78 with week 5's betting line
  alone → 0.51 opponent → 0.53 personnel → 0.48 week number → 0.44 injury report; line + opponent 0.79.
* **The missing betting line re-orders** (a NULL line the models never saw in training: every QB's team loses its
  level). **The personnel compresses individual QBs** (a later week reads the newest played game's starter: Daniels
  7.2 a game for weeks 6–18). The opponent and the week number move it a little; pt1.0 touches the market week only;
  the cold-start / new-team scales do not touch QBs.
* Found: `projections._matrix` zeroes a column NULL in the whole batch (harmless for the nightly's season batch).

#### The horizon study and the candidates (`iq1_horizon.py horizon`, 2021–2025, W = 3 / 5 / 7 / 9, h 1–8)

| | QB pooled 2–8 MAE | Spearman | seasons lower | RB / WR / TE Δ MAE | decision |
|---|---|---|---|---|---|
| base (v3.4) | 7.743 | 0.436 | — | — | — |
| a. line from the team's season (shrink 3 games) | −0.042 | +0.026 | 3 | −0.008 / −0.012 / −0.007 | drop |
| b. opponent shrunk by 4 games | +0.011 | −0.003 | 1 | −0.005 / +0.001 / −0.013 | drop |
| c. market week's line effect carried | +0.003 | +0.026 | 3 | −0.003 / −0.026 / −0.015 | drop |
| d. market week's personnel carried | −0.143 | +0.014 | 5 | 0 / 0 / 0 | passes |
| **ad** | **−0.183** | **+0.038** | **5** | −0.008 / −0.012 / −0.007 | **ships** |
| abd | −0.181 | +0.039 | 5 | −0.013 / −0.012 / −0.020 | passes |

Horizon 1 (the market week) QB 6.44 / 0.587; v3.5 recovers 0.18 of the 1.30 MAE gap and 0.04 of the 0.15 Spearman gap.
Stability (top 24, 20 cells): QB 0.67 → 0.79 (lowest 0.44 → 0.59). K not run (kd1.0 is separate; 0.48, unchanged).

#### What ships

* `calibration.future_inputs` (fi1.0, `# ---- IQ-1` at the end of `calibration.py`), called by `projections.project` on
  the season's rows; `LEAGUE_LAB_FUTURE_INPUTS` (unset = on, `0` = v3.4); `MODEL_VERSION` **v3.5**. pt1.0 skips an
  imputed line (`implied_imputed`).
* The guard: `dbt/tests/assert_rest_of_season_follows_the_market_week.sql` (warn): QB ≥ 0.55, RB / WR / TE ≥ 0.65.

#### Evidence (`league_lab_im1`, `uv run league-lab project`, 9 min)

* "fi1.0: market week 5; later weeks' lines from the teams' own season (7349 rows, shrink 3.0 games), personnel of the
  market week (240 rows moved)"; pt1.0 unchanged (465 lines, real lines only); scenarios base = stored 0.00e+00 on 130.
* Frozen weeks 1–4: **0 cells of 4,856 rows**; week 5: **0 cells of 1,196 rows**; weeks 5–18 v3.5.
* Top 24, Pearson / rank, reference league: QB 0.15 / 0.44 → **0.60 / 0.60**; RB 0.90 → 0.93; WR 0.94 → 0.97; TE 0.86 →
  0.92; K 0.48, DEF 0.41 unchanged.
* QB rest of season, Half PPR (before → after, rank): Prescott 244.9 #2 → 259.3 #1, Mahomes 251.1 #1 → 256.1 #2, Allen
  225.6 #5 → 241.6 #3, Murray 238.7 #3 → 238.3 #4, Goff #14 → #5, Stafford #8 → #6, Stroud #13 → #7, Lamar #20 → #8,
  Purdy #10 → #9, Burrow #19 → #10, Lawrence #12 → #11, Maye #6 → #12, Willis #4 → #13, Daniels #33 → #21. Dynasty in METRICS.
* dbt: the nightly's projection-marts selection + the four freeze / pricing tests + the guard: **PASS 148, WARN 0**.
* Tests: `tests/test_iq1_future_inputs.py` (6); the edited modules' files (calibration, M5, M6, IL-3, IP-1, personnel,
  signals, NFL-wide, freeze): 133 passed; `api/tests/test_ip2.py test_in2.py test_f3.py`: 106 passed, 6 failed — all six
  in `known_api_failures.txt`; ruff, copy_standard clean; `check_root.sh`: 4 failed (all known), 1595 passed, 3 skipped — **no new failure**.

#### Limitations

* Half the problem: QB later weeks still miss by 7.56 (the market week 6.44); Murray stays #4 (his own week-5 number is
  a starter's 17.4). The opponent shrink (b) did not help QBs and was not shipped.
* d is measured with history's listings (mostly the real starter); live listings can be stale (IP-1's st1.x).
* K / DEF were not studied (separate model).

#### For the PO

* Nightly: no line. The first nightly under v3.5 runs `backtest-v2` once (no v3.5 rows), rebuilds `ops.calibration_oof`
  once and recomputes the importance once — as for v3.4.
* Decide: whether the rest-of-season QB numbers on the site should say they are made without a betting line beyond the
  next week (WORDS has no such sentence today; nothing user-facing changed here).
