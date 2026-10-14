# JB-1 — where we lose to Sleeper, and the first fix

**Start 11:07 EDT · end 12:40 EDT** (2026-10-14; clock 150 minutes). Branch `dev/JB1` from `integ/JB` `13de78a`; database
`league_lab_iq4` (the PO's loaded `ops.sleeper_history` 23,200 lines / 58 weeks, `ops.sleeper_history_weeks` 58 ok,
`ops.sleeper_h2h` 296 rows; `ops.h2h_ours` 34,592 v3.6 rows). **No week-5 actuals here: the study is 2023–2025 plus 2026
week 4** (2026 weeks 1–3 are refit boards, never graded).

## 1. Done / not done / cut

1. **The rule first** — gp1.0, `ef37fe4` (11:10 ET, before any number): the hh1.0 population in League of Scrubs'
   scoring; the gap = |ours − actual| − |Sleeper − actual| per player-week, a slice's mean and its share of the summed
   excess; the slices; 95% intervals resampling weeks (one set of draws per family); "holds most" = the two
   position × rank cells with the largest share; the ship rule (target position better in each of 2023–2025, order
   within 0.002; the others no more than 0.005 worse / 0.002 lower). The three candidates written after the diagnosis and
   before any candidate number (`28afbd3`).
2. **The diagnosis** (`scripts/analysis/jb1_gap.py diagnose`; `src/league_lab/h2h_gap.py`): every family with n, gap,
   interval, share, bias and close calls; the walk-forward re-run with the stat line kept matches the stored rows to the
   cent. **The gap is the fringe** — WR and RB we rank 37th or lower hold 39% and 30% of it — and **the first game back
   after a missed game** (12% of rows, 35% of the gap). Our top 12 at every position is level with Sleeper.
3. **The first fix**: three candidates behind `LEAGUE_LAB_GP_FIX`, each walk-forward 2023–2025 (9–10 minutes, one at a
   time). **fx1.0 = C1 ships** (`back_feature`: the model reads whether he missed his team's last game; RB / WR / TE;
   `MODEL_VERSION` **v3.8**). C2 (`back_scale`) fails the rule on order. **C3 (`fringe_scale`) passes the rule and would
   win its tie-break, and does not ship** — see §3: it turns fringe projections into medians (about a point low at RB and
   WR). That is one departure from the rule as written, said in METRICS, not hidden. `off` = v3.6 to the bit.
4. **The run summary** (`league-lab h2h --md`) gains "Where the gap is": the six largest position × rank cells under the
   head-to-head (`ops.sleeper_h2h_gap`, every family's rows); `/api/record` `history.gap` (the same six; `unavailable`
   when the table is absent or unreadable, `none` when empty).
5. Tests, METRICS (gp1.0, the diagnosis, the candidates, fx1.0), metric_registry rows, WORDS, this hand-back.

Not done / cut: no screen shows the gap (the brief asked for the summary and the API). K / DEF not studied (no
out-of-sample K / DEF rows). The by-component family is the study's only (the nightly keeps no walk-forward line).

## 2. Commits

`ef37fe4` 1. gp1.0 · `28afbd3` 2. the diagnosis + the candidates (rule) · `9e84b2a` 3. fx1.0 ships, v3.8 · `69cb4d9` 3.
(cont.) provenance's v3.8, test_ir4 · `b311e0a` 4. the summary's gap table, `/api/record` `history.gap` · `a07ee40` 3. (cont.) the version pins ·
`35ef59c` 5. About's versions e2e and screens · the last commit: hand-back, CHANGELOG.

## 3. Evidence

* Population 15,983 player-weeks; we miss by **+0.148 points a player-week** more than Sleeper (2023 0.166, 2024 0.232,
  2025 0.055).
* **WR ranked 37+**: 4,814 rows (30%), gap 0.192 [0.149, 0.228], **share 39% [31%, 48%]**, bias ours +0.21 / Sleeper −0.16;
  inside it the first game back holds 35% and the line's receiving yards 59%. **RB ranked 37+**: 2,142 (13%), gap 0.335
  [0.251, 0.424], **share 30% [23%, 39%]**, bias +0.25 / −0.29; rushing yards 41%, rushing TDs 25%. Top 12: QB −0.057, RB
  +0.020, WR +0.028, TE +0.036 (each interval holds 0).
* First game back 1,895 rows: gap 0.431, share 35% [27%, 44%], bias +0.60 / −0.34, close calls 37% ours right (2,474).
  Role down 5% of rows / 11%; cold starts 4% / 10%; venue, betting total, rookies, weeks 1–4: no concentration.
* Candidates (pooled 2023–2025 error; gap to Sleeper RB / WR / TE; baseline 4.411 RB, 4.086 WR, 3.072 TE; +0.252 / +0.151
  / +0.077):
  C1 RB 4.304 / 4.409 / 4.484 by season (base 4.324 / 4.420 / 4.488), RB 4.400, WR 4.075, TE 3.066 → **+0.241 / +0.140 /
  +0.071**, passes at RB; bias unchanged; FLEX order 0.6215 → 0.6229; first-game-back gap 0.434 → 0.314.
  C2 RB 4.359, WR 4.038, TE 3.037 (+0.200 / +0.103 / +0.042) but order −0.008 (RB 2024), −0.015 (WR 2024): fails.
  C3 RB 4.253, WR 3.928, TE 3.013 (+0.094 / **−0.007** / +0.018), order unchanged: passes at RB and WR — but bias RB −0.10 →
  **−1.07**, WR +0.07 → **−1.09**, TE −0.25 → −0.69 (37+: +0.18 → −1.30, Sleeper −0.26); FLEX order 0.6215 → 0.6167;
  18.8% of 228,513 close cross-position pairs flip, 57.9% → 57.4% right. Not shipped.
* The switch unset = today to the bit: two `project` runs (before the candidates' code / with it, unset) gave the same
  seven-table hashes (`ops.projections` 19,364 `89937d40…`, `projection_lines` 9,234 `08e5cae5…`, `projection_ranges` 46,170
  `7144af5a…`, `kd_lines` 1,088 `58fe5f8a…`). After the ship, `LEAGUE_LAB_GP_FIX=off` gives the v3.6 board's numbers on
  all seven tables (hashes without the version column: `551013ae…`, `c396529b…`, `e9a637e1…`, `325032df…`).
* The summary's table on this database (written, then rolled back): six cells, WR 37+ 39%, RB 37+ 30%, TE 37+ 7%, RB
  25–36 7%, RB 13–24 5%, QB 25–36 4%; the head-to-head above it matches the PO's hosted grade (RB 4.41 / 4.17, WR 4.09 /
  3.94).

## 4. Tests

* New: `tests/test_jb1_gap.py` **18 passed** (the slices on constructed rows: the tier by our rank, first game back,
  role, QB change, experience, a pre-2016 career = 8+ games, venue, totals; **each family's shares sum to one** and the
  gap is the mean; a slice holding all the excess has share 1; close calls belong to the player we rank higher; the
  component family priced by hand; the ship rule passing, failing (a) on one season, failing (b) on another position, and
  "no better" not shipping; the summary's six rows and words); `tests/test_jb1_gp_fix.py` **6 passed** (the back flag
  incl. a game still to come; `off` changes nothing and unset is fx1.0; the input exists only when the switch says so;
  the factor minimises the absolute error, bounded; the knot); `api/tests/test_jb1.py` **9 passed** (`history.gap`
  absent / unreadable / empty / filled — the route 200 in every state; with no history, no gap block).
* **The switch unset = today's numbers to the last bit**: the two-run hash (`/home/claude/waveIX/verify.sh`'s `hashes`) —
  `project` before the candidates' code and with it (unset): identical on all seven tables; after the ship,
  `LEAGUE_LAB_GP_FIX=off` reproduces the v3.6 board's numbers (hashes without the version column identical).
* Root suite (`check_root.sh`): 1,821 passed, 4 failed (known), **no new failure** — after updating, on purpose, the
  five tests that pin `MODEL_VERSION` (`test_il3_v33`, `test_ip1_pass_td`, `test_iq1_future_inputs`,
  `test_iq3_horizon_blend`, `test_personnel`: "v3.6" → "v3.8"; personnel's RB / WR / TE inputs + fx1.0's).
* API: the record route's and About's files (`test_jb1 test_iz1 test_ir4 test_ix5 test_f3 test_m4 test_v1 test_im3
  test_ic4 test_ig3 test_ih1 test_i0b test_v2`): 408 passed, 12 failed, 5 skipped — the same 12 (`test_f3` × 8, `test_m4` ×
  4) fail with `main`'s files on this database (IZ-1's hand-back). `test_ir4`'s code-version sentence updated on purpose.
* e2e (both projects): `jb1 iz1 ir4 h1 ig2 ig3 ik4 im3` **49 passed, 1 skipped**; `jb1` recorded once from the fixture API
  (port 8930). `docs/handbacks` restored after the run. Web lint 0 / 0, build ok. ruff clean, copy standard clean.
* `LEAGUE_LAB_FREEZE=game chain.sh` with v3.8 (12:14–12:27): migrate ok; dbt build PASS 755, WARN 5, **ERROR 0**; project
  ok (weeks 6–18 written, 1–5 kept frozen); projection marts PASS 146, ERROR 0; availability guards PASS 2, ERROR 0; audit
  ran.
* `scripts/gate.sh`: **GATE PASSED** (root 783, api 40, ruff, web lint, build; 83 s).
* Walk-forward runs: baseline 565 s, C1 / C2 / C3 9–10 minutes each, one at a time (11:11–12:02).

## 5. Edits outside my files

`src/league_lab/projections.py` (MODEL_VERSION v3.8; the switch's input after `ALL_FEATURES`; `load_frame` adds it;
`project` calls `gp_fix.apply` after `blend_lines`) · `src/league_lab/h2h.py` (`build_ours(keep_lines=)`, `gp_fix.apply` in
the walk-forward, the gap table in `run`, `ensure_tables`) · `api/league_lab_api/h2h_api.py` (`gap`) ·
`api/league_lab_api/provenance.py` (MODEL_VERSION, VERSIONS + v3.8) · `api/tests/test_ir4.py` (the code-version sentence) ·
`docs/METRICS.md`, `docs/WORDS.md`, `dbt/seeds/metric_registry.csv`, `CHANGELOG.md`. New: `src/league_lab/h2h_gap.py`,
`src/league_lab/gp_fix.py`, `scripts/analysis/jb1_gap.py`, `tests/test_jb1_gap.py`, `tests/test_jb1_gp_fix.py`,
`api/tests/test_jb1.py`.

## 6. PO lines

```diff
--- a/scripts/nightly.sh
+++ b/scripts/nightly.sh
@@ (after IZ-1's STATE_TABLES line)
 STATE_TABLES="$STATE_TABLES ops.sleeper_history ops.sleeper_history_weeks ops.h2h_ours ops.sleeper_h2h"
+STATE_TABLES="$STATE_TABLES ops.sleeper_h2h_gap"   # JB-1: gp1.0's slices (a failed h2h step keeps last night's)
```

Nothing else: the `h2h` step already writes `logs/sleeper_h2h.md`, which now carries the gap table. **The first night of
v3.8** costs what a model bump costs: `ensure_oof` rebuilds `ops.calibration_oof` (2–5 min), `backtest-v2` runs for v3.8
(minutes; soft since IR-3), `league-lab h2h` rebuilds `ops.h2h_ours` (about 9.5 min, then the grade is v3.8's). The frozen
weeks keep v3.6. The way back: `LEAGUE_LAB_GP_FIX=off` in the nightly's environment (v3.6's numbers; the rows say v3.8 —
revert `MODEL_VERSION` too if it must say v3.6). `ops.sleeper_h2h_gap` is published with `ops` (a few kB).
`app/whats_new.md` (yours): "Projections for running backs, receivers and tight ends now know when a player missed his
team's last game."

## 7. Found, not mine

* gp1.0's ship rule graded absolute error, which a median wins: C3 passed it by making fringe projections a point low.
  A rule for a number that is summed (lineups, odds, trades) should also bound the mean bias; I did not change the rule
  after its numbers — I overrode its tie-break once and said so.
* Sleeper's history lines carry no fumble key for most fringe players (priced 0), and were written after the games: the
  first-game-back and role-down gaps may partly be hindsight.
* `api/tests/test_ir4.py` pinned "Model v3.6" in the code-version case (now reads the code's version); recorded web
  fixtures still say v3.6 (recordings; they do not fail).
* About's "What each number has been checked against" (IR-4's study numbers) are v3.6's; v3.8 changes RB / WR / TE by a
  little (§ 3) — the PO's call whether those rows need a re-run.
* This database's board for weeks 6–18 is now v3.8 (the chain's `project`); `ops.h2h_ours` and `ops.sleeper_h2h` stay
  v3.6 here (the nightly rebuilds them for v3.8).

## 8. Next

1. The fringe, without shrinking the mean: a probability that he plays (inactive / healthy scratch) multiplying a
   played-game line — a candidate that can lower the error and keep the bias.
2. Bound the mean bias in the next ship rule (gp1.1).
3. The clean record from week 5 (JB-2's screen) is the test that does not favour Sleeper: read v3.8's weeks there.
