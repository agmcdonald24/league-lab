# IX-6 — does handling a shortened game make the projection better? (Wave I-X)

**Start 05:03:51 ET, Sunday 2026-10-11 (read from `date`); end 06:12.** Branch `dev/IX6` (from `integ/IX`, IX-1 to
IX-5), `/home/claude/wt-iq4`, database `league_lab_iq4`. The study's rule: docs/METRICS.md § "Does handling a
shortened game make the projection better?" (lf2.0), committed `1e098e0` at 05:11, before any number of it was read.

## 1. Done / not done / cut

* **0. `project` says the same thing twice** (`0d2c4df`, METRICS `998e4ca`): the run-to-run difference was an
  **input**, not the fit — `mart_player_season.avg_offense_snap_pct` was a float `avg` over an unordered group, so each
  build summed the same snap shares in another order and `prev_snap_pct` changed its last bit on ~30,000 rows; values
  that were equal became distinct, the trees' histogram binner cut its bins elsewhere, and every unfrozen week moved.
  Fixed at the source (an exact `numeric` sum). The fit itself carries `random_state=0`, reads its frame in a fixed
  order and runs one thread. Shown: two compute passes of `project` at one state (`ix6_determinism.py`): 0 cells differ (the frame's
  109,409 rows, the lines' 50,985). **Two `project` runs at one state** (the chain's, then `league-lab project` again,
  live week on): **0 rows differ in all 13 tables** (§ 3).
* **2. The role alert** (`9e57b7d`, signals **ra1.3**): a game he left hurt (lf1.0's LE-A: the snap drop and the
  injury note naming him) is treated like a game missed injured — no alert from it, no "before" game for a later one,
  the next game is a return. Chase's "Smaller role … Why: Mitchell Tinsley back" is gone; so is Konata Mumpfield's
  (week 4, "snap share 69% → 27%, Puka Nacua back") — the only two of 2026's 65 alerts that change; none is added.
* **1. The projected target share** (`424af6f`, `703ef10`): lf1.0's team total counted every listed player (about 18.6
  a team, each with an "if he plays" line) — 40 – 47 targets against 29 – 33 real. lf1.1 = his projected targets ÷ the
  projected starter's projected pass attempts; on 2026 weeks 1 – 4 the denominators average 30.4 against 31.2 real team
  targets and the share is 0.056 from his real target share (bias +0.009). Shown on the card's Usage tab as one line.
  **The projection does not hand out too many targets** (§ 7).
* **3. The study** (rule `1e098e0` first; the candidates `e39d693`, `65329b4`; the result `050e9d2`): **nothing ships.**
  All six candidates ran (P1, P2, P3 × marks A and B). Every one is worse on its own affected rows in all five seasons
  (+4.9% to +9.1% error). The rule's pick, P1-B, fails clause (a). The projection keeps its inputs, and IX-1's columns
  stay display only.
* **Cut**: nothing from items 0–3. Not done: a refit-per-season backtest of the full model. The study fitted only the
  component models, which give exactly the backtest's projected points; the range models do not change the point.

## 2. Commits

`9e57b7d` (2. ra1.3), `424af6f` (1. lf1.1 + Usage line), `1e098e0` (3. the rule, before any number), `0d2c4df` (0. the
exact average + the determinism harness), `e39d693` (3. the candidates as dbt vars + the study script), `998e4ca` (0.
METRICS), `efa8eb5` (the study's scoring), `703ef10` (1. e2e + screenshots), `65329b4` (P1 / P3 numeric casts), `050e9d2`
(3. the result, registry rows), `2848c48` (CHANGELOG), and this file.

## 3. Evidence

**0. Two `project` runs at one state** (`LEAGUE_LAB_FREEZE=game`; the chain's `project` at 05:50, then `league-lab
project` again at 05:57; each table dumped sorted, run stamps left out; `scratchpad/ix6/snap_ops.sh`, `cmp_ops.sh`):

```
same  ops.projections (19,364 rows)        same  ops.projection_live (1,104)       same  ops.kd_lines (1,088)
same  ops.projection_lines (9,234)         same  ops.projection_lines_live (524)   same  ops.kd_lines_live (56)
same  ops.projection_ranges (46,170)       same  ops.projection_ranges_live (2,620) same ops.kd_ranges (5,440)
same  ops.kd_ranges_live (280)             same  ops.lineups (9,522)               same  ops.waiver_moves (7,509)
same  ops.player_role_alerts (7,151)
```

The feature mart's hash is the same after every rebuild: `b3fc4ac5…` before the study, and again after the study's
seven rebuilds of `mart_player_recent_form+,+mart_player_week_features` (the last one with no candidate). Before the
fix, two rebuilds of the same code and data gave `ff79…` and `3689…` (IX-1).

**2. Chase's card, Signals** (League of Scrubs, week 5):

* before (ra1.2): "Role: **Smaller role: Ja'Marr Chase — snap share 94% → 20%, target share 29% → 6% since week 4 (one
  game so far)**. Why: Mitchell Tinsley back. Check again after week 7 … Upside: none: his role shrank, and the
  projection above already leans on his last three games."
* after (ra1.3, written by the chain's `project`): "Role: **no role change called**: he left his last game (week 4)
  hurt, and a game cut short by an injury is not read as a smaller role. Upside: no additional modeled upside scenario
  available." (The default "his share … is where it has been" would not be true after such a game, so it is not said.)
* 2026's alerts: 65 → 63. Removed: Ja'Marr Chase week 4 and Konata Mumpfield week 4 ("snap share 69% → 27%", Puka
  Nacua back). None added.

**1. The projected target share's team total** (lf1.0's denominator, by week of 2026; the real game's figures where
played):

| Week | Teams | Median summed projected targets (max) | Players listed per team | Real team targets | Real attempts |
|---|---:|---:|---:|---:|---:|
| 1 | 32 | 47.1 (62.5) | 18.7 | 29.4 | 31.1 |
| 2 | 32 | 44.3 (57.2) | 18.5 | 30.2 | 31.8 |
| 3 | 32 | 44.0 (54.8) | 18.9 | 32.8 | 34.5 |
| 4 | 32 | 43.6 (54.4) | 18.6 | 32.6 | 34.3 |
| 5 | 30 | 40.1 (50.3) | 18.6 | — | — |

For the players who played, the summed projected targets average 31.7 a team against 31.2 real: the model is not
handing out too many targets. lf1.1 (over the projected starter's projected attempts), checked on weeks 1–4 across
1,195 player-weeks:

* the denominators average 30.4, against 31.2 real targets;
* the mean absolute difference from his real target share is 0.056, bias +0.009;
* for comparison, an oracle denominator (only the players who played, unknowable beforehand) gives 0.051.

Chase, week 5: "8.0 of the 33.8 passes we project Joe Burrow to throw in week 5 (24%): the model's own forecast of his
share of the team's targets this week." (lf1.0 said "8.0 of his team's 46.3 projected targets … (17%)".) Screenshots:
`docs/handbacks/ix6/ix6-usage-375.jpg`, `ix6-usage-1300.jpg`.

**3. The study** (Half PPR, walk-forward 2021–2025, component models, 28,808 played player-weeks). Today's error and
order on all rows: QB 5.412 / 0.588, RB 4.244 / 0.669, WR 4.076 / 0.614, TE 3.012 / 0.557.

| Candidate | Affected rows (by season) | Its error | Today's | Change | Seasons better | All rows: max error worse / order lower |
|---|---|---:|---:|---:|---:|---|
| P2-A skip | 180 (30, 28, 27, 48, 47) | 5.021 | 4.721 | +6.4% worse | 0 | 0.004 / 0.004 |
| P2-B skip | 1,347 (256, 360, 253, 246, 232) | 3.724 | 3.519 | +5.8% worse | 0 | 0.006 / 0.002 |
| P1-A on the field | 180 | 4.974 | 4.721 | +5.4% worse | 0 | 0.005 / 0.002 |
| **P1-B on the field** (the rule's pick) | 1,347 | **3.690** | 3.519 | +4.9% worse | 0 | 0.030 / 0.006 |
| P3-A scaled | 180 | 5.148 | 4.721 | +9.1% worse | 0 | 0.014 / 0.004 |
| P3-B scaled | 1,347 | 3.777 | 3.519 | +7.3% worse | 0 | 0.022 / 0.003 |

**Nothing ships.** No candidate meets (a), and most also fail (b). No week-under-way rows move, because no input
changed.

**The chain** (`LEAGUE_LAB_FREEZE=game /home/claude/waveIT/chain.sh /home/claude/wt-iq4 league_lab_iq4`, 832 s): dbt
754 passed / ERROR 0; project as before (frozen weeks 1–5 kept); projection marts 145 / ERROR 0; both availability
guards passed as errors; the audit's first line was 0.

## 4. Tests

* New tests:
  * `tests/test_ix6_signals.py`: 3 passed. Chase's case: the control without the mark fires ra1.2's alert; with the
    mark, no alert at week 4 and no "bigger role" at week 5; the rule version.
  * `api/tests/test_ix6.py`: 2 passed (the Signals words after a game left hurt; a short game without the note is not
    hurt).
  * `api/tests/test_ix1.py`: 5 passed. Its projected-share test now pins lf1.1's words; changed on purpose.
  * e2e `ip4`: 20 passed on both projects, including the new Usage-line test. One rookie test failed once under load
    and passed on re-run. `il1` + `if4`: 14 passed.
* `tests/test_signals.py`: 27 passed. `test_metric_registry`: 3 passed (lf1.1, lf2.0 rows).
* `check_root.sh`: 1,753 passed, 4 failed, **no new failures**.
* API test files of the routes and modules I touched (`check_api.sh`; the card, the game log, research, `onfield`; 36
  files + `test_ix6`): 516 passed, 33 failed, 9 skipped. New against the known list: 4, the same four IX-1 reported as
  this copy's state: `test_f3::test_player_card_ros_is_the_marts` ×2 (fails the same with `main`'s `player.py`),
  `test_ib0::…overlay_starter…` and `test_inf1::…pinned_moment` (waiver routes, no file of mine).
* `scripts/gate.sh python`: **GATE PASSED** (root 783, api 40, ruff). ruff `src app tests api scripts`: clean. Copy
  standard `--check`: clean. `web`: lint 0 errors / 0 warnings, build OK.

## 5. Edits outside my files

`dbt/models/marts/nfl/mart_player_season.sql` (the exact average), `mart_player_recent_form.sql` and
`dbt/models/intermediate/int_player_game_asof.sql` (the candidates behind `var('lf_candidate')`; unset = the SQL as
before), new `dbt/macros/lf_candidate.sql`; `src/league_lab/signals.py` (ra1.3); `api/league_lab_api/onfield.py`
(lf1.1), `web/src/components/PlayerPane.svelte` (one line on Usage), `web/src/lib/api.ts` (the type);
`web/e2e/ip4/fixtures.spec.ts` (one test), `api/tests/test_ix1.py` (the projected share's test, words changed on
purpose); new `tests/test_ix6_signals.py`, `scripts/analysis/ix6_determinism.py`, `scripts/analysis/ix6_study.py`;
docs METRICS, WORDS, CHANGELOG, metric registry.

## 6. PO lines

None. No new table and no new step. Signals ra1.3 rewrites `ops.player_role_alerts` on the next `project`, because
the rule version changed. The dbt var `lf_candidate` stays unset. `app/whats_new.md` (optional): "A player's card no
longer calls a game he left hurt a smaller role."

## 7. Found, not mine

* **The projection does not hand out too many targets.** For the players who played, weeks 1–4 projected targets
  sum to 31.7 a team against 31.2 real. lf1.0's 40–47 a team came from counting every listed player's "if he plays"
  line: about 18.6 players a team, three of them quarterbacks. That was a display fault, not a model fault.
* lf1.1 reads a little high (+0.009 on average): a pass attempt is not always a target.
* The game log shows LE-B marks without an injury note as "Played far less than usual" (LE-B precision
  0.437). Neither mark helps the projection (§ 3).

## 8. Next

1. Nothing for the projection from shortened games. If it comes back, try a different signal, such as the next
   week's practice report, rather than a rewrite of the windows; the windows are closer to the truth as they stand.
2. Grade lf1.1 against a baseline (his season target share) over a few weeks before the card says more than context.
