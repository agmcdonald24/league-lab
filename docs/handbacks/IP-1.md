### IP-1 2026-10-07 — the quarterback weak spot: diagnosed; v3.4 = pt1.0 (QB passing TDs toward the implied total) kept; the drift compares like with like (branch `dev/IP1` from `main` `e4b5eec`, database `league_lab_im1`)

* **Task**: Wave I-P brief § IP-1 ("Find out why and fix what the harness will let us keep"). METRICS § "v3.4: the
  quarterback weak spot (IP-1)" has every table; `scripts/analysis/ip1_qb_diagnosis.py` and `ip1_qb_candidates.py`
  reproduce them from the database (read only).
* **Why**: the home and About said "quarterbacks are our weak spot: 6.5 points off on average, against 5.4 in past
  seasons" (tight ends 3.5 against 3.0).

#### 1. Diagnosis (done; committed before any candidate number was read)

* **The comparison was v2.0 against v3.0.** 2026 weeks 1–3 were projected by v2.0 (the refit of 2026-09-29; v3.0
  shipped 2026-10-01 and made week 4 on). `mart_projection_drift` joined the backtest of the season's newest version
  (v3.0: 5.41). v2.0's own backtest at QB is 5.86 (reference league).
* **Is it a signal?** 112 QB-games, MAE 6.52, 95% interval 5.56–7.51 (whole players resampled). v2.0's weeks 1–3 in
  2021 / 22 / 23 / 24 / 25: 6.42 / 5.62 / 5.80 / 5.63 / 6.42. 2026 minus them (pooled): **+0.54 (−0.45 to +1.62) — not
  distinguishable.** Refit with v3.0's inputs, 2026 weeks 1–3 = 6.18 against v3.0's own weeks 1–3 (5.57 / 5.08 / 5.21 /
  4.97 / 5.53): +0.91 (−0.12 to +1.99). Early weeks are not worse under v3.0 (5.27 vs 5.41 all weeks). Week 4 (v3.0,
  kickoff board, 15 of 16 games in this database): 4.37 on 32.
* **Components** (reference scoring points): passing TDs carry most of every miss (exact passing TDs: 2026 MAE 6.52 →
  3.76; backtest 5.41 → 3.41), then passing yards (−1.72 / −1.33). The one bias in every sample: rushing TDs +0.21 to
  +0.31 a game (actual 0.15–0.17 a game, projected 0.10–0.15), mostly designed runs (0.12 TDs a start vs scrambles 0.06).
  2026 QBs threw 1.41 TDs a game in weeks 1–3 against 1.10–1.25 a season before.
* **Kinds** (2021–2025, 3,330 rows): no kind's bias is distinguishable from 0 and every one flips sign by season —
  rushing share ≥ 30% −0.31 (−1.02 to +0.38), new starter +0.32 (−0.45 to +1.15), rookie +0.08, new team +0.21, new head
  coach (the play-caller stand-in; the data has no play-caller) +0.35 (−0.23 to +0.96); bias² / MSE ≈ 0% each:
  **variance, not bias**.
* **Game script**: corr(miss, team points − implied total) = 0.60 among starters: 36% of a starter's squared miss is
  the team scoring more or less than Vegas said (≥ 7 under −5.89, ≥ 7 over +5.93); by the implied total known before
  the game the bias is −0.19 / +0.03 / +0.05.
* **The three largest 2026 misses**: Sam Darnold wk 3 (5.02 → 29.66: did not know he was starting — v2.0 had no starter
  input and read his 2-pass week-1 exit; the schedule lists Drew Lock for SEA weeks 3–5, so v3.0 refit gives him 2.89);
  Caleb Williams wk 1 (16.88 → 37.26: 65 rushing yards, 2 rushing TDs); Jaxson Dart wk 2 (21.03 → 0.80: left after 5
  passes).
* **The starter listing**: nflverse's schedule keeps a pre-game projected starter after the game in some seasons: listed
  QB threw no pass in 0 team-games a season 2016–2021, 4 in 2022, 0 in 2023, **33 in 2024**, 7 in 2025, 5 in 2026 weeks
  1–4. v3.0's strongest QB input is trained on it.
* **Tight ends** (one table): 3.51 (234 games, 3.05–4.02) against v2.0's weeks 1–3 of 2021–2025 (3.44 / 2.93 / 2.61 /
  2.85 / 2.80): +0.59 (+0.09 to +1.12) — distinguishable, made of touchdowns (+0.36 a game against −0.17 in past first
  weeks; exact TDs would cut 1.33 of 3.51). v2.0 / v3.0 differ by 0.01 at TE. Week 4: 3.05. No candidate.

#### 2. Candidates (`experiments.decide` on the QB board, 2021–2025, both house scorings, the season paired)

Rules written before running (22:25 ET rt1.0 / st1.0; 22:47 ET pt1.0, after those two were read):

| Candidate | Δ MAE by season 2021 / 22 / 23 / 24 / 25 | Δ MAE (better of 5) | Δ Spearman (better) | bias before → after | decision |
|---|---|---|---|---|---|
| **pt1.0** QB passing TDs = a × model + b × implied total × attempts / 33 (least squares, no intercept, 3 seasons before) | −0.126 / −0.059 / −0.081 / −0.065 / −0.046 | **−0.076 (5)** | **+0.0145 (5)** | board +0.22 → +0.14 | **keep** |
| rt1.0 QB rushing TDs × mean-unbiased k (3 seasons before) | +0.047 / +0.054 / +0.033 / +0.031 / +0.016 | +0.036 (0) | −0.0018 (2) | rushing TDs +0.21 → −0.11 | drop |
| st1.0 the starter from what happened + an as-of guard (dbt var `pn_starter_from_play`) | +0.000 / +0.004 / +0.036 / −0.151 / −0.017 | −0.026 (2) | +0.0025 (2) | +0.22 → +0.23; flagged rows lower in 1 of 5 (2024: 11.47 → 7.07) | drop |

pt1.0 by league: reference 5.407 → 5.350, dynasty 7.586 → 7.492; projected starters 7.07 → 6.98, the rest 4.20 → 4.22.
st1.0's guard is right in 17 of 26 played team-games where it fires and wrong in 9 (a listed starter returning from an
injury: PIT 2022 Pickett, WAS 2025 Daniels …). st1.0's first build mislabelled Taysom Hill (listed TE): fixed (any listed
position) before the run in the table; the first run read −0.018, drop. Not built (the tables discard them): a QB
cold-start / new-starter prior (M5 measured it: w = 1), a rushing-archetype prior, a range width by archetype (2026's
QB range covered 78.6%).

#### 3. What ships

* **v3.4 = v3.3 + pt1.0** (`calibration.pass_td_lines`, called by `projections.project` before M6's `blend_lines`, `#
  ---- IP-1`): on the stat line before anything is priced (the frozen-line path), so `ops.projection_lines`,
  `ops.projections`, `ops.projection_ranges` and every request agree. Switch `LEAGUE_LAB_QB_PASS_TD` (unset = on; `0` =
  v3.3). Fitted inside `project` from its training frame (3 QB component fits). Weeks without an implied total keep the
  model's count. `MODEL_VERSION` "v3.4". `calibration.rescale_to_stored` (M6's, used by the scenarios) now moves the
  larger role component by component, so a QB scenario's gain is the role's and not pt1.0's (identical for M6's cold
  starts: their line is the model's × k in every component).
* **The drift** (`mart_projection_drift`, a view): each complete week against the backtest of the model that made it
  (newest backtested version at or before the week's). Reference league QB 6.52 against **5.86** (was 5.41), TE 3.51 /
  3.01, RB 4.18 / 4.28, WR 4.15 / 4.07. Also keeps the backtest columns filled once a v3.3 / v3.4 week completes on a
  database without backtest rows of that version.
* **st1.0's dbt switch, off**: `int_pn_team_game` gains `listed_qb_id` (the schedule's own value) and, under
  `var('pn_starter_from_play')` (default false), the corrected starter; `assert_personnel_is_asof` reads the corrected one
  only when the var is on; `assert_starter_from_play` (new) checks the correction against the play data. Off: rebuilt and
  compared with the frame before — every QB input of `mart_player_week_features` identical (the only cells that moved
  were 1,705 2026 rows of `pn_absence_beneficiary`, which reads `ops.player_role_alerts`: this copy's mart was older than
  its alerts table; unrelated to IP-1).

#### Files

Mine: `src/league_lab/calibration.py` (`# ---- IP-1` block at the end), `src/league_lab/projections.py` (`MODEL_VERSION`,
the hook), `scripts/analysis/ip1_qb_diagnosis.py`, `scripts/analysis/ip1_qb_candidates.py`, `tests/test_ip1_qb.py` (9),
`tests/test_ip1_pass_td.py` (10), `dbt/models/intermediate/features/int_pn_team_game.sql`,
`dbt/models/intermediate/features/int_player_week_personnel.yml`, `dbt/tests/assert_starter_from_play.sql` (new),
`docs/METRICS.md`, `dbt/seeds/metric_registry.csv` (+3: pt1.0 available, rt1.0 / st1.0 experimental), this file.
Outside my list: `dbt/models/marts/nfl/mart_projection_drift.sql` + its `schema.yml` description (`# ---- IP-1` blocks),
`dbt/tests/assert_personnel_is_asof.sql` (one marked `{% if %}`), `tests/test_il3_v33.py` and `tests/test_personnel.py`
(the pinned `MODEL_VERSION` "v3.3" → "v3.4", on purpose), `CHANGELOG.md`, `docs/WORDS.md` (marked blocks).

#### Commands and evidence

* Rows: `OMP_NUM_THREADS=1 uv run python scripts/analysis/ip1_qb_diagnosis.py --rows <cache>.parquet` (the walk-forward
  rows, QB / TE, v2.0 and v3.0 inputs, 2021–2026: about 3 min alone; season means equal `ops.projection_backtest`'s to
  ±0.01, single weeks ±0.21 — the stored record is an older run on an older build). Candidates: `ip1_qb_candidates.py
  rt | pt | pt-ranges | st` (st needs `dbt build --select int_pn_team_game+ --vars '{pn_starter_from_play: true}'` and
  the frame before it as `--before`).
* dbt on `league_lab_im1`: `int_pn_team_game+` with the var on PASS 118 (after the as-of test learnt the var and the
  Taysom Hill fix), with it off PASS 118 (every QB input identical to before); `mart_projection_drift+` PASS 5; after the
  full `project`, the nightly's projection-marts selection + `assert_house_projections_are_the_nfl_wide_rows`,
  `assert_projection_ranges_price_the_lines`, `assert_frozen_*`: **PASS 147, WARN 0**.
* `uv run league-lab project` (v3.4, switches at their defaults; 12 min, load 4–9): "pt1.0 QB passing TDs: a = 0.035 x
  the model + b = 0.0637 x implied total x attempts / 33, on 2021 fitting rows (2023-2025); 465 QB lines moved"; wrote
  weeks 5–18, kept 1–4 frozen — **0 cells changed** in weeks 1–4 (4,856 house rows, 2,396 lines); week 5's QB rows are
  v3.4 and equal the isolated switch-on run to the cent (Josh Allen 21.87, Dak Prescott 20.95 …); importance recomputed
  once for v3.4 (QB's top input `pn_qb_starting` +1.84). A second `project` after the scenario change (`rescale_to_stored`
  per component): "scenarios written: 130 rows … base = stored projection to 0.00e+00 on 130 rows"; RB / WR / TE scenario
  gains moved 0 of 114, QB 6 of 16 (week 5: a "gain" of −1.71 that was pt1.0's shift reads −0.28, the role's own); the
  projection-marts selection again PASS 147, WARN 0.
* pt1.0's ranges (reported, 2023–2025, the production path): 80% interval score −0.0027 (reference) / +0.0016
  (dynasty), 50% −0.010 / −0.016, coverage 80% 0.757 → 0.757 / 0.756 → 0.762.
* Tests: `tests/test_ip1_qb.py` 9 + `tests/test_ip1_pass_td.py` 10 passed; the edited modules' root files (calibration,
  M5, M6, IL-3, personnel, NFL-wide, freeze, EV, drift, v2, importance, experiments, registry): 163 passed, 1 failed
  (`test_projections_ev::test_scrubs_pins_and_dynasty_moves`, known: reads this database's week-4 lines); API files that
  read the edited modules (`test_h1`, `test_il3`, `test_if3`, `test_in6`): 51 passed, 4 failed, all four in
  `known_api_failures.txt`; `uv run ruff check src app tests api scripts/analysis` clean; `copy_standard.py --check`
  clean; `/home/claude/waveIP/check_root.sh /home/claude/wt-ip1` (after the last src change): 4 failed, 1571 passed, 3 skipped — **no new failure** (the four are `known_root_failures.txt`).

#### Limitations

* `backtest-v2` under v3.4 measures the model without the line blends (as under v3.2 / v3.3): About's backtest at QB will
  not show pt1.0's −0.06; the first nightly under v3.4 runs `backtest-v2` once (the existing `backtests` step: no rows
  for the new version), as the v3.3 bump did.
* pt1.0 acts only on weeks with an implied total (in season: the next week); later weeks keep the model's count, so the
  rest-of-season sums mix the two for QBs.
* The starter listing stays the schedule's: SEA's week-5 board here reads Lock 13.72 / Darnold 4.38.
* "New play-caller" is a new head coach (the data has no play-caller).

#### For the PO

1. **Merge**: independent of IP-2…IP-5 (no shared file but CHANGELOG / WORDS, marked).
2. **The nightly**: nothing new to run — pt1.0 fits inside `project`. The bump makes the existing `calibration-oof`
   step rebuild `ops.calibration_oof` once (about 2–3 CPU-minutes alone) and `project` recompute the importance once.
   `scripts/nightly.sh` needs no line. The drift view is rebuilt by the nightly's `dbt build`.
3. **The home's sentence** (`home.ts` `gradeLead`, not mine): with the drift fix it reads "6.5 … against 5.9"; the
   honest words are in WORDS § "How the projections have done, honestly".
4. **Decide**: whether to correct the starter listing (st1.0 dropped by the rule; a data fix for played games without
   the guard was not measured on its own).

### IP-1 fix round 2026-10-07 — st1.1 (who starts) judged on identification accuracy; the home's grades (branch `fix/IP1` from `integ/IP` `0551b7d`)

* **st1.1** (dbt var `pn_starter_stale_rule`, `int_pn_team_game`; rule written before the build, METRICS § "st1.1"):
  week W keeps the listing L unless, in the team's two newest played games of the season, L was listed for the newer
  one too, took no dropback in either, was available in both (weekly roster ACT, not Out / Doubtful), and one other QB
  led both games' dropbacks — then that QB. As-of only (nothing from W's game, report or roster).
* **Confusion table** 2022 – 2026 wk 4: fixed 11, still wrong 38, newly broken 3 (in-game changes kept: 66; stale
  listings 49). (a) 22% < 60% **fail**; (b) 3 > 11 / 6 **fail**; (c) QB board −0.020 pooled, pass. **Not shipped**:
  the var defaults off; off, `int_pn_team_game` reads none of its CTEs and every QB input equals the frame before (0 of
  109,539 rows differ). With it on, week 5 here changes one starter: SEA Lock → Darnold.
* **The alternative, described** (not built): "starter unclear" — a team whose listed QB took no dropback in its newest
  played game while another led: both QBs marked, both out of the tiers, numbers unchanged. As of each week it would
  have flagged ~2 team-weeks a week (169 in 2022 – 2026 wk 4), 32 of the 49 stale listings; week 5 here: CHI, SEA, WAS.
* **The home** (`web/src/components/home/home.ts`, marked `// ---- IP-1`): `MIN_WEEKS = 6`; under it a position more
  than 10% above its past is "unclear" (plain tile) and the lead ends "— too few weeks to call that a difference";
  from six weeks a difference needs a miss above every past season of the same model and > 10% over the backtest. No
  API field added (`season.weeks_scored` and `by_season` were there). `web/e2e/in1/fixtures.spec.ts` updated on purpose
  (the recorded answer now reads "unclear" and the new lead; "worse" / "weak spot" were the old expectations) plus a
  pure-code test of the three cases.
* **Files**: `dbt/models/intermediate/features/int_pn_team_game.sql`, `dbt/tests/assert_starter_from_play.sql`,
  `dbt/tests/assert_personnel_is_asof.sql`, `scripts/analysis/ip1_starter_rule.py` (new), `tests/test_ip1_starter.py`
  (new, 3), `web/src/components/home/home.ts`, `web/e2e/in1/fixtures.spec.ts`, `docs/METRICS.md`, `docs/WORDS.md`,
  `dbt/seeds/metric_registry.csv` (+1, st1.1 experimental), `CHANGELOG.md`.
* **The nightly**: nothing (the var is off; the home is the web build). No `scripts/nightly.sh` line; no new env.

### IP-1 fix round 2 2026-10-07 — "starter unclear", the flag; versions compare by number (branch `fix2/IP1` from `integ/IP` `3d1b76b`)

* `api/league_lab_api/starters.py` `unclear(season, week) -> {gsis_id: {team, listed, played, role, words, last_week}}`
  (the interface IP-2 reads; `last_week` is an extra key). Reads `analytics.dim_game` (the listing, the games),
  `analytics.fct_player_game` (`dropbacks`, `played`), `analytics.dim_player` (names) — all on the hosted copy, no new
  relation. As of the week (`week < W` only). `{}` on a missing relation, a week outside 1–22, an unlisted week or any
  failure. Memo region `starters` (≤ 32 entries, 10 min; DEPLOY § Memory).
* Re-measured through `unclear()`: 169 flags in 76 weeks of 2022 – 2026 wk 4 (46 / 33 / 48 / 37 / 5), 32 of 49 stale
  listings marked, 137 flags not stale — the same as the round-1 measurement. 2026 week 5: CHI (Keenum / Bagent), SEA
  (Lock / Darnold), WAS (Daniels / Kaliakmanis); week 4: SEA only (CHI's own week-4 game does not count); weeks 1 and 6:
  none.
* The review's L4: `dbt/macros/version_key.sql` (an integer array of a version's numbers) in `mart_projection_drift`
  (the newest version, "at or before") and `mart_projection_backtest.is_current`; `assert_model_versions_compare_by_number`
  (v3.9 < v3.10 …); the drift on this database identical before and after (24 columns, 8 rows).
* Tests: `api/tests/test_ip1_starters.py` (5), `tests/test_ip1_qb.py` + the L4 text test (10); dbt PASS 9.
