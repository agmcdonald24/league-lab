# IQ-3 — the quarterback model reads the quarterback (Wave I-Q, 2026-10-07)

**Task**: IQ-3 of `/home/claude/waveIQ/BRIEF.md`. **Branch**: `dev/IQ3` from `main` `6a76100`. **Database**:
`league_lab_im1` (the only writer). **Result**: v3.6 ships one candidate, **hb1.0** (a QB's weeks after the market week
blend the model's stat line with his own per-game line), kept by a rule written before any candidate number. Not
"cured": the 2–8 weeks Spearman goes from 0.473 to 0.495; the target was 0.53.

## Order of work (commits)

1. `39030c9` 20:40 ET — the baselines, the ceiling and **the keep rule** (docs/METRICS.md § "v3.6: the quarterback
   model reads the quarterback (IQ-3)"), before any candidate number.
2. `16d57d4` — the candidates' code (hb1.0, hb1.1, pe1.0, pe1.0 + hb1.0), defined before the run.
3. `bac49fa` — v3.6 in production (`calibration.horizon_blend_lines`), tests, the `_matrix` fix, CHANGELOG, registry.
4. the docs commit (METRICS results, this hand-back).

## Baselines (2021–2025, both house scorings averaged; season = the mean of its weeks)

B0 = v3.5; B1 = his points per game this season and last, shrunk by games toward the starters' mean; B1r = B1 with the
prior of his listed role (starter / not); B2 = B1r + the opponent and the real implied total.

| season | 1 wk B0 MAE / ρ | B1 | B1r | B2 | 2–8 wks B0 MAE / ρ | B1 | B1r | B2 |
|---|---|---|---|---|---|---|---|---|
| 2021 | 6.499 / 0.605 | 7.861 / 0.473 | 6.636 / 0.581 | 6.557 / 0.597 | 7.718 / 0.440 | 8.059 / 0.466 | 7.355 / 0.515 | 7.370 / 0.520 |
| 2022 | 6.168 / 0.593 | 7.105 / 0.470 | 6.520 / 0.537 | 6.260 / 0.583 | 7.202 / 0.510 | 7.247 / 0.429 | 6.966 / 0.527 | 6.999 / 0.535 |
| 2023 | 6.264 / 0.608 | 7.522 / 0.474 | 6.527 / 0.567 | 6.401 / 0.598 | 7.404 / 0.519 | 7.641 / 0.460 | 7.382 / 0.517 | 7.388 / 0.522 |
| 2024 | 6.779 / 0.573 | 7.731 / 0.454 | 6.908 / 0.538 | 6.858 / 0.554 | 7.624 / 0.479 | 8.177 / 0.368 | 7.640 / 0.470 | 7.678 / 0.477 |
| 2025 | 6.394 / 0.602 | 8.110 / 0.400 | 6.992 / 0.523 | 6.909 / 0.542 | 7.850 / 0.417 | 8.623 / 0.354 | 7.869 / 0.425 | 7.821 / 0.432 |
| mean | **6.421 / 0.596** | 7.666 / 0.454 | 6.717 / 0.549 | 6.597 / 0.575 | **7.560 / 0.473** | 7.949 / 0.416 | 7.442 / 0.491 | 7.451 / 0.497 |

Finding: one week ahead the model beats every naive baseline in every season; two to eight weeks ahead the naive line
with the role prior beats v3.5 (MAE 7.442 vs 7.560, Spearman 0.491 vs 0.473). The ceiling: an oracle that knew each
QB's season mean in the week's role (the week left out) scores 6.605 / 0.545 one week out — the model (6.466 / 0.578 on
those rows) already beats it — and 6.605 / 0.552 two to eight weeks out (B0 7.609 / 0.456, B2 7.494 / 0.482 there).

## The rule (written 20:40 ET, committed `39030c9` before any candidate number)

Kept when: (1) 1 week — the market week unchanged (0 cells), or MAE lower than B0 in ≥ 4 of 5 seasons and mean
Spearman higher (decide reported, "hurts" fails); (2) 2–8 weeks pooled — MAE lower in ≥ 4 of 5 and mean Spearman
higher; (3) QB 80 % range coverage on the production path within 77–83 % in each house scoring at 1 week, 2–8 reported;
(4) RB / WR / TE untouched or not worse by > 0.01. Largest pooled 2–8 Spearman gain ships. "Cured" = pooled 2–8
Spearman ≥ 0.53 with the 1-week 0.596 kept. One reading to flag: the PO's suggested rule asked the 1-week board to
improve too; I wrote clause 1 so that a candidate which does not touch the market week passes it by construction (the
PO's own "cheapest fix", a horizon-dependent blend, could not pass otherwise). hb1.1 (the blend with a market-week
weight) was judged by the full clause and failed.

## Candidates (Δ against B0)

| candidate | 1 wk | 2–8 wks Δ MAE by season | 2–8: seasons lower / Δ ρ | decision |
|---|---|---|---|---|
| **hb1.0** horizon blend, h ≥ 2 | 0 cells | −0.391 / −0.308 / −0.006 / −0.004 / −0.060 | 5 of 5 / +0.0216 | **kept, ships** |
| hb1.1 + a market-week weight | Δ MAE −0.017 / +0.010 / +0.012 / −0.016 / +0.066 (2 of 5), Δ ρ +0.0023 | as hb1.0 | 5 / +0.0216 | drop (clause 1) |
| pe1.0 player effect (shrunk past residuals) | Δ MAE −0.067 / +0.005 / −0.037 / −0.022 / +0.019 (3 of 5), Δ ρ +0.0010 | −0.106 / +0.056 / −0.060 / +0.030 / +0.036 | 2 / +0.0102 | drop (1, 2) |
| pe1.0 + hb1.0 | as pe1.0 | −0.393 / −0.310 / −0.007 / +0.000 / −0.043 | 4 / +0.0209 | drop (clause 1) |

hb1.0: pooled 2–8 MAE 7.560 → 7.406, Spearman 0.473 → 0.495 (by season 0.519 / 0.533 / 0.518 / 0.478 / 0.426; 2023
and 2024 −0.001). Ranges (production path, 80 % coverage): 1 week 78.4 % Half PPR / 78.5 % dynasty (unchanged: holds);
2–8 weeks 71.9 / 71.2 % → 73.4 / 72.3 %. The production weight fit reproduces the study's 2024 and 2025 weights exactly;
2026's (fitted on 2023–2025), h 2…8: 0.0 / 0.5 / 0.2 / 0.35 / 0.55 / 0.95 / 0.75 (λ 0.25, k 6).

## What shipped (v3.6)

* `src/league_lab/calibration.py` (block `# ---- IQ-3`): `HORIZON_BLEND_FLAG = LEAGUE_LAB_QB_HORIZON_BLEND` (unset = on,
  `0` = v3.5), `fit_naive`, `naive_line`, `horizon_rows`, `fit_horizon_weights`, `horizon_blend_lines`,
  `walk_forward_models` (memoised; `pass_td_fit_rows` now uses it — same models, pt1.0's 2026 fit unchanged: a 0.035,
  b 0.0637 on 2,021 rows).
* `src/league_lab/projections.py`: `MODEL_VERSION = "v3.6"`; `project` calls `horizon_blend_lines` after pt1.0
  (marked block); `_matrix` keeps NaN (the all-NULL-column trap; the fits zero such a column themselves).
* `scripts/analysis/iq3_qb.py` (cache / baselines / candidates / ranges), `tests/test_iq3_horizon_blend.py`; version
  pins v3.5 → v3.6 in `tests/test_il3_v33.py`, `test_personnel.py`, `test_ip1_pass_td.py`, `test_iq1_future_inputs.py`.
* Docs: docs/METRICS.md § v3.6, `dbt/seeds/metric_registry.csv` (`qb_horizon_blend` hb1.0, `qb_naive_baseline`),
  CHANGELOG (`## 2026-10-08 — Wave I-Q`). No new table, no schema change, no API or screen change.

## Evidence on `league_lab_im1` (a full `project`, v3.5 → v3.6)

* Frozen weeks 1–4: 0 cells changed (projections 4,856 rows, lines 2,396, ranges 11,980). Week 5 (market): 0 cells.
  Weeks 6–18 RB / WR / TE / K / DEF: 0 cells. QB weeks 7–18: 1,061 lines moved (week 6 has weight 0).
* dbt projection-marts selection + the freeze, house-row and ranges-price-the-lines tests + the guard: PASS 147,
  **WARN 1** — the guard (`assert_rest_of_season_follows_the_market_week`): QB in the reference league 0.53 < 0.55.
* Top 24 by week 5 vs the weeks 6–18 mean (Pearson / rank): Half PPR QB 0.60 / 0.60 → 0.60 / 0.53; dynasty QB 0.57 /
  0.58 → 0.52 / 0.46; RB 0.93 / 0.94, WR 0.97 / 0.95, TE 0.92 / 0.85 (Half PPR) unchanged; K / DEF unchanged.
* QB this week (week 5): unchanged in both leagues (hb1.0 does not touch the market week). Rest of season (weeks
  5–18), Half PPR, top 20 after (before rank): 1 Allen 267.9 (#3), 2 Mahomes 251.5 (#2), 3 Prescott 247.6 (#1), 4 Purdy
  245.1 (#9), 5 Goff 236.0 (#5), 6 Stafford 232.1 (#6), 7 Lawrence 227.5 (#11), 8 L. Jackson 226.9 (#8), 9 Burrow 226.4
  (#10), 10 Hurts 221.8 (#17), 10 Maye 221.8 (#12), 12 Shough 220.2 (#22), 13 Keenum 219.8 (#19), 14 Brissett 217.8
  (#14), 14 Stroud 217.8 (#7), 16 Watson 216.0 (#15), 17 Nix 213.6 (#16), 18 Cousins 211.5 (#18), 19 Daniels 210.3
  (#21), 20 B. Young 210.0 (#31); Murray #4 → #23. Dynasty: 1 Allen 323.6 (#6), 2 Mahomes 322.2 (#2), 3 Prescott 321.1
  (#1), 4 Purdy 313.3 (#12), 5 Goff 311.5 (#4), 6 Stafford 307.6 (#3), 7 Burrow 292.6 (#8), 8 Lawrence 291.3 (#11), 9
  L. Jackson 287.8 (#10), 10 Brissett 282.6 (#9), 11 Keenum 280.2 (#17), 12 Stroud 279.0 (#7), 13 Maye 277.6 (#13), 14
  Shough 277.2 (#24), 15 Hurts 277.0 (#20), 16 Cousins 275.7 (#14), 17 Nix 269.8 (#15), 18 Watson 268.7 (#19), 19 B.
  Young 268.6 (#31), 20 Love 266.0 (#22). Evidence, not the criterion.

## Tests

* New: `tests/test_iq3_horizon_blend.py` — 9 passed (the naive line, only later QB weeks move by the horizon weight,
  the house rows price the NFL-wide line bit for bit flat and at the odds with the switch on and off, off / zero weights
  = identity, `horizon_rows`, the `_matrix` trap).
* Version-pinned and neighbouring files (`test_ip1_pass_td`, `test_iq1_future_inputs`, `test_il3_v33`,
  `test_personnel`, `test_metric_registry`): 39 passed.
* Root suite (`/home/claude/waveIP/check_root.sh`): 1,604 passed, 3 skipped, 4 failed — all four in the known list, no
  new failure.
* API: `api/tests/test_if3.py` (the one API file importing `projections`): 7 passed, 3 failed — all three in the known
  list. The full API suite not run (rule 7).
* `ruff check src app tests api`: clean. `scripts/copy_standard.py --check`: clean. No `web/` change (no lint / build /
  e2e needed).

## What the first nightly does once because of the version bump

`backtests` runs `backtest-v2` once (no rows for v3.6; it measures the market week, which v3.6 does not change);
`calibration-oof` rebuilds `ops.calibration_oof` once (2–3 CPU-minutes); `project` recomputes the importance once (about
2 minutes here). hb1.0 itself adds about 2 s to `project` (it reuses pt1.0's walk-forward fits). No new table, no new
step, no `scripts/nightly.sh` line.

## Limitations

* Not cured: 0.495 against the 0.53 target, about two fifths of the way. The oracle that knew each QB's season level and
  his role in the target week reaches 0.552; one week out the model is past that oracle already.
* The 2–8 weeks ranges stay narrow (about 72–73 % for the 80 % range): they are calibrated one week ahead.
* The guard warns on this week's board (0.53 against its 0.55 floor); its floor was set on a footing without pt1.0.
* The naive line uses the frame's per-game rates over games played (a game left early counts as a game).
* History's market-week listing is mostly the real starter (nflverse corrects played games), a little better than live.

## For the PO to decide

1. The guard's QB floor: keep 0.55 (the nightly will show WARN 1 on this board) or lower it to 0.45, below every v3.6
   cell of the study (Half PPR lowest 0.47, dynasty 0.42). One line in
   `dbt/tests/assert_rest_of_season_follows_the_market_week.sql`; I did not change it.
2. Clause 1's reading (a candidate that leaves the market week alone passes it): accept, or ask for the stricter rule.

## Next

The one thing I would try next: the quarterback's per-dropback record (EPA, pass-TD, sack and interception rates per
dropback, empirical-Bayes shrunk over career / last season / this season with the dropback counts) as inputs to the QB
component models, judged on the same two boards by the same rule.
