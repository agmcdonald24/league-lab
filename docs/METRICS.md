# Metric contract

The registry of record is `dbt/seeds/metric_registry.csv` (name, version, numerator, denominator,
grain, status, notes); this file explains the rules behind it. Plan §6 is the source of the rules.

## Rules that apply to every rate

1. **Sum, then divide.** Season and window rates are computed from summed numerators and summed
   denominators, never by averaging per-game rates.
2. **Shared window.** The denominator is the team total *in the same games* as the numerator —
   by default the player's appearance games (`played = true`). Filters (weeks, season type,
   partial-game exclusion) apply to both sides identically. The denominator is never narrowed to
   the selected player; other positions' targets stay in it.
3. **Independent denominators.** Team totals come from `fct_team_game` (nflverse team file), not
   from summing player rows. A test verifies player sums never exceed team totals.
4. **Zero denominator → NULL.** Never 0, never ∞.
5. **Signed air yards** can make `air_yards_share` negative or above 100%; the value is kept and
   `air_yards_denominator_unstable` is flagged when team air yards ≤ 0. No generic 0–100% test.
6. **Unknown ≠ zero.** Missing snaps → `snaps_known = false`, `offense_snap_pct` NULL. Deferred
   metrics (first read, context splits, routes) are NULL/"unavailable" everywhere.

## Available in this build (v1.0)

| Metric | Definition |
|---|---|
| `target_share` | targets ÷ team targets (games appeared) |
| `carry_share` | carries ÷ team carries |
| `air_yards_share` | receiving air yards ÷ team passing air yards (signed; see rule 5) |
| `offense_snap_pct` / `avg_offense_snap_pct` | from snap counts (PFR); participation evidence, not routes |
| `adot` | receiving air yards ÷ targets |
| `catch_rate`, `yards_per_target`, `yac_per_reception`, `yards_per_carry` | as named |
| `completion_rate`, `yards_per_attempt` | as named |
| `dropbacks_excl_scrambles` | attempts + sacks suffered (player and team). Scrambles need play-by-play; the name says so |
| `targets_per_game`, `carries_per_game` | ÷ games played (appearance games) |
| recent form `*_l3`, `*_l5`, `*_std` | last 3 / last 5 appearance games in the same season & season type, ordered by week; denominators summed over the same games; season-to-date alongside |
| `points_current_scoring` | reference league's newest `scoring_settings` × nflverse stats (cross-year research, NFL-wide marts) |
| `points` (`fct_player_game_league`) | each *current* league-season's `scoring_settings` × nflverse stats, every NFL game (league pages, S-01a) |
| `points_recomputed` (league) | that season's `scoring_settings` × nflverse stats |
| `points_observed` (league) | Sleeper's own `players_points` — includes commissioner edits, bonuses, DEF |
| kicker streaming (realized) | started-kicker points per roster-week; common eligible weeks = weeks every roster started a K; changes and acquisitions counted from lineups/transactions |
| `lineup_efficiency` | points for ÷ Sleeper potential points (`ppts`) |

Appearance: `played = offense_snaps > 0 OR any of attempts/carries/targets/fg_att/pat_att > 0`.
`games_with_stats` counts nflverse stat rows (a player on the active roster with a zero line still
has one); `games_played` counts `played`.

## Manager's Edge metrics (v1.0, 2026-09-26)

| Metric | Definition |
|---|---|
| `points_expected` / `expected_per_game` | league scoring applied to ffverse expected stats (receptions, yards, TDs, 2-pt, INT for pass/rush/receive): the viewer's league on league pages (`mart_league_player_season`, S-01a), the reference league in the NFL-wide marts. No kicking or fumbles, so K expected points are NULL. `diff_per_game` = actual − expected in the same scoring; negative = producing below opportunity |
| defense vs position | points (reference scoring) scored by opposing QB/RB/WR/TE/K against a defense, per game; season-to-date and last-4; rank 1 = allows the most. Regular season only. The same ranks appear as **Opp rank** on league pages |
| all-play | for each scored regular-season week, wins vs every other roster; season all-play win%; `expected_wins` = games × all-play win%; `luck_wins` = actual − expected |
| optimal lineup | best lineup from the players rostered that week using Sleeper observed points; greedy fill of fixed slots then REC_FLEX/WRRB_FLEX/FLEX/SUPER_FLEX (optimal for fixed slots + one flex type). `bench_points_left` = optimal − started; `lineup_efficiency` = started ÷ optimal. Validated against Sleeper's `ppts` (regular season): exact for 29/30 rosters |
| positional strength | sum of season ppg (the league's own scoring) over the top-N rostered players at a position (N = starting slots at that position); compared with the league median; rank 1 = strongest. **No page or pack reads it since B2** (superflex counted as a QB slot, FLEX never attributed): the roster views use § Roster value |
| availability | `rostered_by_*` from the current Sleeper roster payloads; free agent = not on any roster in that league. Team defenses (DEF) are not in the table (no NFL player id) |
| share trends | `target_share_trend` = last-3 share − season share (same for carries). Meaningless before 4 games |
| CB coverage context | PFR advanced defense when the defender was targeted: targets, completions, yards, TDs, passer rating allowed, aDOT, YAC, missed tackles; season-to-date; 2018+. The matchup page lists the opponent's LCB/RCB/NB (depth rank ≤ 2) from the latest depth chart. Not a shadow-coverage assignment |
| next matchup | next NFL week = first week with unplayed games; opponent from the schedule; bye when no game; injury = latest weekly report row |

## Trends (v1.0, 2026-09-26)

Every trend answers one question with two bars: *did the player's role change over his last three
games, and is the change bigger than his own week-to-week noise?*

| Term | Definition |
|---|---|
| window | the player's **last 3 played regular-season games** (`value_l3`) versus **every played game before them** (`value_prior`). Byes and DNP weeks are skipped, not counted as zero. Nothing is called before game 4 (`direction = insufficient`) |
| value | rate metrics are *sums over sums* inside each window (e.g. targets ÷ team targets over the 3 games), never the mean of three per-game rates; per-game metrics divide by games in the window |
| `change` | `value_l3 − value_prior`, compared with a **practical minimum** per metric (`seeds/trend_metrics.csv`: 3 points of target share, 5 of snap/carry/air-yard share, 1 target or 2 carries per game, 2 expected points, 3 fantasy points, 1 yard of aDOT, 3 pass attempts) |
| `z` ("Strength") | `(mean_l3 − mean_prior) ÷ (sd_game × √(1/3 + 1/n_prior))`, where `sd_game` is the standard deviation of the player's own per-game values this season. ±1 = beyond his usual noise; ±2 = a clear change. NULL when sd is 0 or there is no prior game |
| `direction` | **up** when `change ≥ min_change` *and* `z ≥ 1`; **down** symmetric; **flat** otherwise; **insufficient** below 4 games. `confidence` = strong (|z| ≥ 2) / moderate (≥ 1) / weak |
| `slope_per_game` | least-squares slope of the per-game value over game number, season-to-date (a smoother read than L3 vs prior; not used for direction) |
| `tags` ("Trend") | the up/down metrics spelled out, ordered by |z| — "↑ targets, ↑ snaps, ↓ aDOT" is more work at shallower depth; "↑ targets, ↑ aDOT" is a deeper role |
| `momentum` | mean `z` across the **opportunity** metrics only (targets/game, target share, air-yard share, carries/game, carry share, snap share, expected points; pass attempts for QBs). Fantasy points and aDOT are excluded on purpose: three touchdowns do not change a role. `opportunity_trend` = rising (≥ 1) / falling (≤ −1) / steady / insufficient |
| defense trend | points allowed to a position (current scoring, regular season) over the defense's last 3 games vs before, same `z` construction; **softer** when change ≥ 3 points and z ≥ 1, **stiffer** symmetric |

Metric positions: target/air-yard/aDOT metrics for RB/WR/TE; carry metrics for RB/QB; snaps and
expected points for all four; pass attempts for QB. Kickers and team defenses have no trends.

The older `target_share_trend` / `carry_share_trend` columns in `mart_player_availability` (L3 minus
season) are kept for the Waiver Wire sort; the trend marts supersede them for any judgement call.

## Scoring recomputation — approximations

| Sleeper key | Expression | Note |
|---|---|---|
| `fgmiss`, `xpmiss` | `fg_missed + fg_blocked`, `pat_missed + pat_blocked` | Sleeper treats blocked kicks as misses; nflverse separates them |
| `fgm_50p` | `fg_made_50_59 + fg_made_60_` | |
| `fum` | `fumbles_total` | any fumble |
| `fum_lost` | `fumbles_lost_total` | sack + rush + receiving fumbles lost |
| `st_td`, `fum_rec_td` | `special_teams_tds`, `fumble_recovery_tds` | |
| `fgmiss_0_19` … `fgmiss_50p` | `fg_missed_0_19` … `fg_missed_50_59 + fg_missed_60_` | nflverse has no per-distance blocked buckets, so a blocked FG scores 0 in a league with distance-bucketed misses (about 1% of attempts) |
| `pass_td_40p`, `rush_td_40p`, `rec_td_40p` (and `_50p`) | long-touchdown counts from play-by-play (`int_player_game_pbp`: touchdown plays with `yards_gained ≥ 40 / 50` by passer / rusher / receiver) | laterals credit the first receiver; 0 when a game has no plays loaded |
| `bonus_pass_yd_300/400`, `bonus_rush_yd_100/200`, `bonus_rec_yd_100/200` | `1` when `low ≤ yards < high` for the game | Sleeper's buckets are **exclusive** (100–199, 200+): a 210-yard game pays the 200+ bonus only. Kind `bonus` in the seed |
| **Expected points** | `stat` keys only (`league_points(…, include_bonuses=false)`) | a threshold on an expected yardage would pay deterministically at 100.0 and not at 99.9; in a league with bonuses, actual − expected carries the bonus points |
| DEF keys (`sack`, `int`, `pts_allow_*` …) | unmapped | team defense is out of MVP1; observed DEF points still come from Sleeper |
| position-conditional keys (`bonus_rec_te`, `bonus_rec_rb`, `bonus_rec_wr`), first-down keys (`*_fd`) | unmapped | the dbt test `assert_unmapped_scoring_keys_are_known` warns if a league uses one |

Reconciliation: `assert_recomputed_points_reconcile` warns on |observed − recomputed| > 0.5 for
QB/RB/WR/TE/K, in every configured league under that league-season's own settings. Differences are
information (stat corrections, unmodelled keys), not failures.

**Several leagues (per-league pricing, S-01a, 2026-09-27).** Two scales, one rule: *a league page
prices every player in that league's own current scoring; an NFL research page prices every player
and season in the reference league's scoring* (the first id in `LEAGUE_LAB_SLEEPER_LEAGUE_ID`;
`dim_league_season.is_reference_league`).

| Where | Scoring | Relations |
|---|---|---|
| League pages — Team Hub, Waiver Wire, Matchups start/sit, Trade Finder, League (manager profiles, draft), weekly packs: PPG, points, PPG (L3/L5), xPPG, PPG − xPPG, positional strength, keeper / roster-value ranks, draft season points | the selected league's **current** scoring | `fct_player_game_league` → `mart_league_player_season` → `mart_player_availability`, `mart_league_keeper_candidates`, `mart_league_positional_strength`; `mart_league_draft` via `chain_id` |
| Observed league history — standings, matchups, lineups, `points_recomputed` | that league-*season*'s own scoring (Sleeper's points) | `league_player_week`, `fct_league_matchup`, … |
| Rankings — projection v2 | the selected league's scoring | `mart_player_week_projections` |
| NFL research — Players, Trends, Receivers, defense vs position (and the **Opp rank** columns derived from it), the baseline projection formula, the projection features | reference scoring | `fct_player_game.points_current_scoring`, `mart_player_season`, `mart_player_recent_form`, `mart_player_expected_*`, `mart_defense_*`, `mart_player_week_features/_rankings` |

The per-league marts reuse the NFL-wide arithmetic unchanged — points over every stat row, PPG per
appearance game, L3/L5 = the last 3/5 appearance games of the season, xPPG over QB/RB/WR/TE game rows
with an expected row and an appearance, ranks over every NFL player at the position — so the reference
league's pages did not move by a cent (`assert_reference_league_matches_nfl_marts`), and
`assert_league_points_match_recomputed` holds every current league's per-game points equal to
`league_player_week.points_recomputed` for rostered players. Expected points stay without bonus keys
in every league. The metric-registry versions for `expected_points` and `positional_strength` still
read 1.0: the seed was out of bounds for S-01a (see `docs/STATUS.md`). `scoring_diff_vs_reference`
still lists the keys where a league differs; the sidebar shows it under a one-line notice.

## Play-by-play metrics (v1.0, Phase 2, 2026-09-26)

Source: nflfastR play-by-play (`fct_play`, one row per play, 2016+), NFL participation
(`bridge_play_participation`, players on the field, 2016 → last completed season) and FTN Data
charting (`fct_play_charting`, 2022+, CC-BY-SA 4.0 — attribute FTN Data when publishing).

### Eligibility flags (`fct_play`)

| Flag | Definition | Reconciliation |
|---|---|---|
| `is_no_play` | `play_type = 'no_play'` or `play_deleted` — nullified / no play. Kept, never counted | — |
| `is_pass_attempt` | ball thrown (completion, incompletion, interception **or spike**); sacks excluded | = team `attempts` in 5,340 of 5,344 team-games 2016–2026 (official stats count spikes) |
| `is_target` | pass attempt to an identified receiver, **excluding two-point tries** | = nflverse weekly `targets` in 4,533 of 4,533 player-weeks (2025); 5,342 of 5,344 team-games all seasons |
| `is_rush_attempt` | rush attempt incl. scrambles and kneels, excluding two-point tries | = nflverse weekly `carries` (1 player-week differs, Ogunbowale 2024) |
| `is_sack` / `is_scramble` | sack on a real play / `qb_scramble` on a run play | sacks = team `sacks_suffered` everywhere |
| `is_dropback` | `qb_dropback` on a real play, no two-point tries = attempts − spikes + sacks + scrambles | identity holds in every team-game |
| `is_two_point` / `is_two_point_target` | two-point conversion try; targeted two-point throws flagged separately | never a target, carry or dropback |
| `is_kneel`, `is_spike`, `has_penalty`, `is_aborted` | as named | spikes are attempts but not dropbacks; kneels are carries but not dropbacks |

### Context (`fct_play`, `mart_player_context`)

* **half**: `H1` / `H2` / `OT` (overtime separate). **score_state** from the offense's *pre-snap*
  differential: trailing 9+, trailing 1–8, tied, leading 1–8, leading 9+ (raw score and clock kept).
  **down_distance**: 1st; 2nd short (≤3) / medium (4–6) / long (7+); 3rd/4th short / medium / long.
  **field_zone**: own half, opp half (21–50), red zone 11–20, inside 10. **qb**: the passer on throws
  and sacks, the rusher on scrambles.
* `mart_player_context` (player × season × split × bucket): the player's targets, receptions, yards,
  first-read targets, carries and routes proxy in the bucket, next to the **team's** dropbacks,
  targets, carries and first-read targets in the same bucket over the same games (the games the
  player appeared in). A row exists for every bucket the team saw in those games, so 0 is a real
  zero. Test: halves sum to the season mart's totals.

### First-read target share

`first_read_target_share = player first-read targets ÷ team first-read targets` over the player's
appearance games (plan §6 definition, sums over sums, same window rules as target share).

`read_thrown` coding, **verified against the data** (every season 2022–2026):

| Code | Meaning | Evidence |
|---|---|---|
| `1` | first (primary) read | the majority code on targeted throws in every season (≈52%), where the first read is expected |
| `2` | second read or later | ≈11% |
| `CHK` | checkdown | ≈13% (one 2022 row is `" CHK"` with a leading space — trimmed) |
| `DES` | designed throw (screens, many RPOs) — **kept separate, never a first read** | ≈9% |
| `SD` | scramble drill | ≈6% |
| `0` (2023+) / `NULL` (2022) | **uncharted / not a throw** | sits on every run, kickoff and punt (≈19.8k plays a season) and on 2–3% of pass attempts — the same slice that is `NULL` in 2022 |

The nflreadr dictionary describes `0` as "first read from 2023"; the data contradicts it (a first-read
rate of 2% is impossible), so League Lab follows the data. `MVP1_PLAN.md` §6 carried the dictionary's
wording; treat this section as the correction.

Stored with every rate: `first_read_targets`, `team_first_read_targets`, `charted_targets`
(targets with any read code), `charting_coverage` (team charted ÷ team targets), `designed_targets`,
`checkdown_targets`, `later_read_targets`, `scramble_drill_targets`, `first_read_metric_version`.
Uncharted targets are never assumed to be first reads. `first_read_rate_of_targets` (first reads ÷
the player's own charted targets) is a different question and is published separately.

Manual reconciliation (plan §9.6), PHI vs DAL 2025 week 1: 20 PHI targets, 20 charted; first reads on
Dotson (51-yd, 3rd-and-6), D. Smith (1st-and-10, Q3) and A.J. Brown (2nd-and-11, Q4) — three by hand,
`team_first_read_targets = 3` in the mart; Goedert 7 targets, 5 checkdowns, 0 first reads; Brown
`first_read_target_share = 1/3`.

### Routes proxy, TPRR / YPRR proxy, route participation

* `routes_proxy` = dropbacks (`is_dropback`) the player was on the field for, from participation,
  **receiving positions only** (WR/TE/RB/FB/HB). It is a proxy: presence is not a route (blocking
  tight ends, chip-and-release backs), so it runs ≈10–15% above the charting services — Chase 2024:
  705 vs ≈615 published. `NULL` when the game has no participation row (unknown, not zero).
* `tprr_proxy` = targets ÷ routes_proxy and `yprr_proxy` = receiving yards ÷ routes_proxy over
  participation-covered games — **lower bounds**; compare players with each other, not with
  published TPRR/YPRR.
* `route_participation` = routes_proxy ÷ team dropbacks with participation data: the passing-down
  analogue of snap share.
* Participation files are published after each season's postseason, so the current season has no
  routes proxy in-season. A licensed feed imported with `league-lab import-routes` fills `routes`,
  `targets_per_route_run`, `yards_per_route_run` (no proxy label) — CSV contract in
  `src/league_lab/ingest/routes_feed.py`.

### Dropbacks

`dropbacks` (team and QB) = attempts − spikes + sacks + scrambles from play-by-play. The stats-only
`dropbacks_excl_scrambles` (attempts + sacks) is kept next to it; where both exist the play-by-play
version is the one to use (plan §6: dropbacks include scrambles).

## Rankings — baseline projection and backtest (v1.0, 2026-09-26)

### Feature snapshot (`mart_player_week_features`)

One row per rostered QB/RB/WR/TE and regular-season week in which his team plays. Every feature is
**as of the games before that week** (test `assert_features_never_peek`): the player's latest played
game before the week supplies season-to-date / last-3 / last-5 PPG, expected points, shares and snaps;
the previous season supplies `prev_ppg` / `prev_xppg`; the opponent's points allowed to the position
and the league average are computed over games before the week; the Vegas implied team total is
`(total ± spread) / 2` from the closing line; the injury report is the week's own. For the upcoming
week the universe is the latest published roster. `no_history` marks players with neither in-season
nor previous-season games (projected from position averages).

Finished `f_*` inputs never contain NULL: season form falls back to last season, then to the position's
regulars' mean PPG from the previous season (`pos_prev_ppg`, itself as-of). `f_sample` runs 0 → 1 over
the first six games so the interaction terms fade last season out.

### Projection (`mart_player_week_rankings`)

`proj_points = intercept + Σ weight × feature`, per position, weights in `seeds/ranking_weights.csv`
(ordinary least squares on 2019–2022 played player-weeks, `league-lab fit-rankings`; test
`assert_rankings_apply_seed_formula` keeps SQL and seed identical). Contributions are grouped as
**form** (xPPG L5, PPG season / L3 / previous and the fade interactions), **usage** (L3-vs-season
target/carry share, L3 snap share), **matchup** (opponent allowed − league average), **Vegas**
(implied team total) and **home**. `is_rankable` excludes Out, Doubtful and IR; ranks are per
season-week-position among rankable players.

| Feature | QB | RB | WR | TE |
|---|---|---|---|---|
| `intercept` | +0.260 | −0.721 | −1.323 | −1.804 |
| `f_xppg_l5` | +0.095 | +0.143 | +0.212 | +0.255 |
| `f_ppg_std` | +0.271 | −0.064 | −0.008 | −0.000 |
| `f_ppg_l3` | +0.133 | +0.152 | +0.047 | +0.012 |
| `f_ppg_prev` | +0.168 | +0.116 | +0.154 | +0.197 |
| `f_ppg_std_x_sample` | +0.038 | +0.404 | +0.364 | +0.286 |
| `f_ppg_prev_x_nosample` | +0.016 | +0.380 | +0.390 | +0.275 |
| `f_opp_allowed_diff` | +0.145 | +0.065 | +0.018 | +0.071 |
| `f_implied_total` | +0.103 | +0.039 | +0.053 | +0.072 |
| `f_home` | +0.466 | +0.147 | +0.087 | −0.033 |
| `f_target_trend` | — | −3.995 | −1.754 | −1.489 |
| `f_carry_trend` | +7.883 | +1.633 | — | — |
| `f_snap_l3` | +1.942 | +4.197 | +2.472 | +2.564 |
| player-weeks / R² (train) | 2,469 / 0.31 | 5,931 / 0.35 | 8,856 / 0.28 | 4,449 / 0.27 |

Reading the weights: expected points and season PPG (through the fade term) carry most of the load;
last season matters until about game six; the **negative** target-trend weight says a last-3 target
share above the season share partly reverts — a hot streak is treated as partly noise; the opponent
term is worth about 0.07–0.15 points per point of "allowed above average", i.e. matchups move a
projection by a point or two, not five; QBs get the biggest home bump.

### Backtest (`league-lab backtest`, `mart_backtest_summary`)

For each held-out season-week-position, on players who played: **Spearman** rank correlation between
the scorer's order and actual points; **top-N hit rate** (N = 12 QB/TE, 24 RB/WR) = share of the actual
top-N the scorer's top-N contained; **MAE** in points; the actual PPG of the scorer's top-N next to the
true top-N (the ceiling). Scorers: the baseline and three naive rankings — season PPG to date,
last-3 PPG, expected points L5 — built from the same as-of inputs.

2023–2025 (weights fitted on 2019–2022, mean over 54 season-weeks per position):

| Pos | Baseline Spearman | Best naive | Gap | Baseline hit rate | Best naive hit rate |
|---|---|---|---|---|---|
| QB | 0.501 | 0.469 (xPPG L5) | +0.032 | 51.9% | 51.7% |
| RB | 0.670 | 0.644 (season PPG) | +0.026 | 62.3% | 61.7% |
| WR | 0.604 | 0.565 (season PPG) | +0.039 | 46.4% | 44.1% |
| TE | 0.573 | 0.524 (xPPG L5) | +0.048 | 46.3% | 44.4% |

The baseline has the higher Spearman in all 12 position-seasons. The levels are the honest part:
weekly fantasy points are mostly noise, a 0.6 rank correlation is a good weekly ranking, and a
top-24 WR list catches under half of the actual top 24. Any later model (ML or otherwise) must beat
this table on the same harness, out of sample, before it replaces the baseline.

## Projection v2 — stat-line projections with an interval (v2.0, 2026-09-26)

Plan M-01 / M-03. Code: `league_lab.projections`; tables `ops.projections`, `ops.projection_backtest`,
`ops.projection_importance`; marts `mart_player_week_projections`, `mart_projection_backtest`,
`mart_projection_importance` (U-15).

### What is projected

Per position, one gradient-boosted regressor (scikit-learn `HistGradientBoostingRegressor`, fixed
hyperparameters, Poisson loss for counts and touchdowns, squared error for yards) per **stat-line
component**: QB — attempts, passing yards/TDs/INTs, carries, rushing yards/TDs, fumbles lost; RB —
carries, rushing yards/TDs, targets, receptions, receiving yards/TDs, fumbles lost; WR — the RB list
with receiving first; TE — targets, receptions, receiving yards/TDs, fumbles lost. Other components
are 0 for that position.

**Points** (`proj_points`) = the projected line put through a league's scoring map
(`league_lab.scoring.compute_points`, stat keys + yardage bonuses; long-TD keys are not projected).
One row per configured league, so two leagues with different scoring get different boards — the
first honest multi-league projection (S-01 for projections).

**Floor / ceiling** (`p10`, `p90`; `p50` = projection + median miss, informational) = quantile
regressors of the **miss around the priced line** (the league's actual points minus the line),
on the same features plus the line. The misses they learn from are **out-of-fold**: components
fitted on the odd training seasons price the even ones and vice versa, so the residuals are the
size of real forecast errors, not in-sample fits. (Quantile regression of raw points fails at
P10: a fifth of played WR weeks score 0, the initial constant sits on that mass and the model
never leaves it — the first attempt put every WR's floor at 0.) The three are made monotone by
sorting, then **split-conformal calibrated**: fitted on all training seasons but the newest, the
newest measures how far actuals fall outside [P10, P90], and both ends are widened by the 80th
percentile of that miss. Coverage on data the model never saw is reported, not assumed. **The
board ranks by `proj_points`** (the priced line) among rankable players (Out / Doubtful / IR
excluded, like the baseline); the interval belongs to that projection.

### Features (all as-of the week; NULL allowed — the model treats "not known yet" as information)

Week, games to date, `f_sample`; season-to-date / last-3 / last-5 PPG and xPPG (reference scoring),
points SD; last season's PPG / xPPG / snap share / per-game component rates; position prior (last
season's regulars); target / carry / snap / air-yards shares (season, last 3); first-read share
(FTN, in-season); red-zone targets and carries per game; **per-game rate of every component,
season to date and last 3**; opponent's points allowed to the position (season, last 4, rank, league
average); implied team total, spread, total, home; Questionable flag. **Excluded on purpose:** the
routes proxy / route participation (the participation file arrives after the postseason, so it would
be NULL all season in production — the first backtest leaned on it for TEs and overstated the live
board). Feature list: `projections.FEATURES`.

### Backtest (`league-lab backtest-v2`, `mart_projection_backtest`)

Walk-forward: each held-out season N is scored by a model trained on 2016…N−1 (calibrated on N−1),
per league, on players who played, same harness as the baseline (Spearman, top-N hit rate, MAE)
plus **coverage_80** (share of actuals inside [P10, P90]), the pinball losses and the mean interval
width. Three scorers per league-season-week-position: `v2_p50`, `v2_points` (the priced line) and
`baseline` (the OLS formula, priced in reference scoring, scored against the league's actuals —
i.e. what a non-reference league saw before v2). Results are in `docs/STATUS.md` and on the page.

### Production (`league-lab project`, nightly)

Fits on every completed season (no calibration-season loss for the components; the interval gives
up one), projects every week of the current season for every configured league, writes
`ops.projections`; `mart_player_week_projections` adds names, context, the outcome priced under the
league's own scoring (`league_points` macro over the component outcomes) and `rank_pos`. Everything
shown for the current season is out of sample. Refit cadence: every refresh (≈1–2 min); a
hyperparameter change is a new `MODEL_VERSION`. Every week is re-projected by each refit, but only the
weeks that have not kicked off are **written**: a started week keeps the rows it had (next section).

### What drives the projection — importance (v2.0, plan U-15, 2026-09-30)

**Before U-15** Rankings showed the permutation importance of the **P50 interval model** (`importance()`,
written by `backtest-v2`): its inputs are the features *plus the priced line*, and the priced line
dominated, so "price line 0.017, snap 0.007" described the model that places the floor and ceiling around
the projection, not the projection. Those rows stay in `ops.projection_importance`, labelled
`model = 'quantile_p50'`, `component = 'p50_residual'`, and are no longer shown.

**Now** (`component_importance`, `importance_after_project`; rows `model = 'component'`):

* **Which models.** The component models (one per stat per position, `COMPONENTS`) that make the projection.
  They are measured as a **twin** of the production fit: same features, hyperparameters and training filter,
  fitted on the production window minus its newest season (`fit_seasons` 2016–2024) and scored on that newest
  season (`eval_season` 2025) — the models that grade 2025 in the walk-forward backtest. *Why not the
  production models on 2025* (the newest training season itself): both were measured on the clone. The top
  input per position is the same, but scoring rows a model was fitted on overstates what it memorised — QB
  rushing yards per game this season 0.20 points in-sample vs 0.05 held out, implied team total 0.34 vs 0.18;
  over all 74 inputs the two orders correlate 0.68 (QB), 0.80 (RB), 0.62 (WR), 0.58 (TE), top-10 overlap
  7, 9, 8, 6 of 10. The page shows the held-out number, consistent with "graded on seasons it never saw".
* **Scrambling.** Per input, `IMPORTANCE_REPEATS` = 5 shuffles of that column across the season's rows
  (`numpy` `default_rng(0)`, drawn for every input in `FEATURES` order, so an input that never varies — it
  scores 0 — never shifts the others); every component re-predicted from the scrambled matrix, clipped at 0
  like the board. `importance` = mean rise in error, `importance_sd` = its standard deviation over the 5.
* **Error: MAE, not Poisson deviance.** MAE is in the stat's own unit (targets, yards …), so times the points
  a unit is worth it is points; a deviance has no points equivalent.
* **One number per input per position** (`component = 'total'`, `unit = 'points'`): the rise in the MAE of the
  **priced line** against the points the player actually scored, both in the **reference league's scoring**
  (League of Scrubs; `unit_points`: 0.5 a catch, 0.1 a yard, 6 a TD, 0.04 a passing yard, 4 a passing TD, −1 an
  INT, −2 a fumble lost; it has no bonus keys, so a stat line's points are exactly that sum). This weights each
  component by its **points per unit** (not by its share of points) and adds the errors *before* taking the
  absolute value, so errors in different stats offset or compound the way they do in the projection, and the
  stats the model does not project (a WR's pass) stay in the actual points like the board's misses. Checked
  against the alternative the plan offered — the per-component rises weighted and summed
  (`importance_points` summed over components): the two order the 74 inputs almost identically (Spearman
  0.97–0.98 per position, top-10 overlap 8–9 of 10), so the choice moves the numbers, not the story.
  Targets, carries and attempts are worth 0 points per unit, so an input that moves only the targets model adds
  no points of error: volume matters through the catches, yards and touchdowns it predicts
  (`tests/test_projection_importance.py`).
* **Per stat** (`component` = the stat, `unit` = the stat): the rise in that component's MAE in its own unit,
  and `importance_points` = rise × |points per unit|, for a breakdown; `baseline_mae` is the unscrambled MAE
  (points for `total`), `n_rows` the rows scored.
* **Cadence.** Written by `league-lab project` after the projections, lineups and waiver moves, **once per
  `MODEL_VERSION` × training window** (`train_seasons` of the production fit); later runs keep it (the nightly
  restores the table from the hosted copy with the rest of `ops`). `projections.run_importance()` forces a
  recompute. It never reads or changes the production models: the board is byte-identical with or without it.
* **Published** by the view `mart_projection_importance` (`importance_rank` per model version × model × position
  × component; added to the `make project` / nightly projection-marts `--select`) and shown in Rankings' "The
  model" expander: top 10 per position, plain names from `projections.FEATURE_LABELS` (every input has one,
  tested), as "points of error added". Caveats said on the page: inputs that move together (targets and catches,
  a season and its last 3 games) share the credit, so each looks smaller than it is; importance is not cause.

### Decision record (plan B5, 2026-09-29): a week's board is frozen at its first kickoff

**Rule.** `league-lab project` rewrites a league-week's rows in `ops.projections` on every refit until
the week's **first kickoff** (`min(dim_game.kickoff_at)` over the season-week, every game type); from
then on the rows are never deleted or rewritten (`projections.freeze_plan`, applied by
`_write_projections` in one transaction). The first refit after kickoff labels the kept rows:

| `frozen_source` | `frozen_at` | Meaning |
|---|---|---|
| NULL | NULL | live board: the week has not kicked off (or has, and no refit has run since — it is labelled on the next one) |
| `kickoff` | the kept rows' `fitted_at` (always before the first kickoff) | **the board as published before kickoff** — what a manager saw when setting a lineup. The last refit before kickoff wins: with the nightly at 07:37 ET (GitHub Actions; 08:00 on the Mac) that is Thursday morning's board |
| `refit` | NULL | the week was already under way when its rows were locked: **2026 weeks 1–3**, played before this rule existed (their rows are the refit of 2026-09-26 23:53 UTC, after weeks 1–3 had kicked off), or a league-week first projected after its kickoff (a league added mid-season). Not a kickoff record, and the page says so |

A week without a scheduled kickoff counts as not started. To re-project a frozen week on purpose (a bug
fix), delete its rows by hand; the next refit writes it back labelled `refit`. Test:
`assert_frozen_projections_precede_kickoff` (a `kickoff` row's `frozen_at` equals its `fitted_at` and
precedes the week's first kickoff — kickoff times, not run times, since every scheduled game has one;
`refit` rows have no `frozen_at`; nothing written after kickoff is left live; one label per league-week).

**Why a column on `ops.projections`, not a separate `ops.projection_snapshots` table.** The acceptance
("after two consecutive `project` runs the played weeks' rows are byte-identical") is about
`ops.projections` itself; with a label on the table the row a manager saw is the only row there is, so
`mart_player_week_projections`, the Rankings board, the drift and the hosted copy (0.5 GB budget) need
no second copy, no "prefer the snapshot" join and no reconciliation of two versions of a played week.
What is given up: the refit values of a played week are no longer kept anywhere (they were never shown
after kickoff anyway), and the freeze is per week, not per game — a Sunday player's board is fixed at
Thursday's first kickoff, so Friday–Sunday injury news does not reach it (a per-game freeze is a
possible refinement).

### Drift (`league-lab drift`, `ops.projection_drift`, `mart_projection_drift`; plan M-06)

Once a week of the projected season has been played, the board (frozen at kickoff, B5) is scored the way the backtest
scores a held-out season: per league × week × position, on players who **played** and were
**rankable** (the board the page shows), projection = `proj_points`, actual = `points_actual` (the
league's own scoring), with the same harness — Spearman, top-N hit rate (QB/TE 12, RB/WR 24), MAE,
`coverage_80` (share of actuals inside [P10, P90]), mean P90 − P10 — and the same 8-player minimum.
`games_played / games_scheduled` mark a week still being played (Thursday night only is a handful
of players from two teams): its rows are written and refreshed nightly, but the season view averages
**complete weeks only** and reports the other as `week_in_progress`. The view sets each position's
season means next to the backtest's `v2_points` means over its held-out seasons (`backtest_*`).
Written at the end of every `league-lab project` and by `league-lab drift` on demand. **Scored on the
frozen board (B5):** the projection is read from `ops.projections` itself (rounded like the mart), i.e.
for a week that has kicked off the rows kept at kickoff, even if the mart has not been rebuilt since;
outcomes, availability and games come from `mart_player_week_projections` as last built (in the nightly
the full `dbt build` runs first, so they are that night's). `frozen_share` = share of the scored rows
whose `frozen_source` is `kickoff`; a week scored on `refit` (or not yet labelled) rows has 0, and the
view carries the player-weighted `frozen_share` over complete weeks plus `refit_weeks`, so the page says
"scored on the board as shown before kickoff" or "refit values" (2026 weeks 1–3 are refit values: they
were played before the freeze existed; their numbers did not move when B5 was deployed).
Scope difference from the backtest: the backtest scores every player who played, the drift only
rankable ones (Out / Doubtful / IR who played anyway are left out, as on the board). A few weeks are a small sample: read a gap to the backtest as a
question, not a verdict, until mid-season.

## Kicker and defense projections (kd1.0, plan R-13, 2026-09-30; `league_lab.kdef`, `league-lab backtest-kd`)

League of Scrubs starts a K and a DEF. Until R-13 the lineup valued a K at his season PPG, a DEF at the
points Sleeper had observed for it, and a newly rostered K / DEF at 0 ("unvalued"); the waiver engine could
not see free-agent defenses at all. kd1.0 projects both the way v2 projects QB–TE: a **stat line per
unit-week, priced in each league's own scoring**, with a calibrated interval, backtested walk-forward.

**Units and outcomes** (`mart_kd_team_game`, `mart_kd_week`). A K unit is a kicker (`gsis_id`); a DEF unit is
a team defense, keyed by its Sleeper id (`KC`; the Rams are `LAR` where nflverse says `LA`). Every kicker
who kicked in a week's game, plus every kicker on his team's latest weekly roster (ACT) for a week without
one (the upcoming weeks); every team × scheduled game for DEF. Outcomes come from the nflverse weekly
player stats (K) and team stats (DEF) and the schedule's final score; one franchise code throughout (the
2016–2019 schedule's OAK / SD are LV / LAC, as the stats files already say).

| Position | Line component (`out_*` / projected) | Source column | Priced by |
|---|---|---|---|
| K | FG made 0–19, 20–29, 30–39, 40–49, 50+ | `fg_made_*` (50+ = 50–59 + 60+) | `fgm_*` |
| K | FG missed (blocked counted as missed) | `fg_missed + fg_blocked` | `fgmiss` |
| K | FG missed by distance (projected: FG missed × the training seasons' distance shares; blocked kicks are not bucketed by nflverse) | `fg_missed_*` | `fgmiss_*` |
| K | PAT made / missed (blocked counted as missed) | `pat_made`, `pat_missed + pat_blocked` | `xpm`, `xpmiss` |
| DEF | sacks, interceptions, opponent fumbles recovered, forced fumbles | `def_sacks`, `def_interceptions`, `fumble_recovery_opp`, `def_fumbles_forced` | `sack`, `int`, `fum_rec`, `ff` |
| DEF | defensive TDs (interception and fumble returns) | `def_tds + fumble_recovery_tds` | `def_td` |
| DEF | special-teams TDs | `special_teams_tds` | `def_st_td` |
| DEF | safeties, blocked kicks (punt + FG + PAT) | `def_safeties`, `def_*_blocks` | `safe`, `blk_kick` |
| DEF | points allowed (the opponent's final score) | schedule | `pts_allow_0` … `pts_allow_35p` |

K keys price through the same Sleeper-key → nflverse-column map as every player (`scoring.SLEEPER_STAT_MAP`,
`league_points()`). The D/ST keys are not in that seed (it maps player keys and is generated from
`scoring.py`); `kdef.DEF_STAT_MAP` / `PTS_ALLOW_BUCKETS` and the dbt macro `def_points()` are the one
definition (a unit test checks the two list the same keys). **Reconciled with Sleeper**: League of Scrubs'
rostered D/ST weeks 2024–2025, priced this way against the points Sleeper counted: 349 of 398 exact, 388
within 1 point, MAE 0.19 (the misses are ±1 forced-fumble / recovery counting and special-teams
fumbles). Not projected (they price 0 and the log names them): `def_st_ff`, `def_st_fum_rec`, `st_ff`,
`st_fum_rec` (Scrubs weights them 1 each; about 0.1 a game), and yards-allowed buckets (no league scores them).

**Features** (as of the week: games before it; NULL = not known yet, handled natively by the trees):
the game — week, home, dome (roof dome / closed), Vegas implied totals for both sides, total, spread; the
team's per-game rates season to date, last 3 (this season) and last season — K: points scored, FG attempts
and makes, PAT attempts, red-zone plays, EPA per play; DEF: sacks, interceptions, fumble recoveries, forced
fumbles, defensive and special-teams TDs, blocked kicks, points allowed; the opponent's — K: points the
defense allows and FG attempts it allows; DEF: the offense's sacks taken, giveaways, points, EPA per play,
plays; and for K the kicker's career before the week: games, attempts 0–39, accuracy 0–39 / 40–49 / 50+ /
PAT each shrunk to a prior (0.93 / 0.80 / 0.66 / 0.94 with 10 pseudo-attempts), share of attempts from 50+.

**Model** (fixed constants; a change is a new version): one `HistGradientBoostingRegressor` per component,
Poisson loss for the counts, squared error for points allowed (150 iterations, learning rate 0.04, 7
leaves, ≥ 80 rows per leaf, L2 1.0, seed 0). Chosen over a hand rates model because the inputs interact
(implied total × dome × the kicker's range) and have holes (week 1, a new kicker, no line yet) the trees
handle as they are, and the stat-line machinery is v2's. **Points allowed as a distribution**: the
out-of-fold forecast errors of points allowed (components fitted on the odd training seasons predict the
even ones and vice versa) are added to the forecast; the share landing in each whole-point bucket
([lo − 0.5, hi + 0.5), below 0.5 = shutout) is the bucket's probability and the bucket points are the
probability-weighted sum. **Interval**: P10 / P50 / P90 = the projection + the 10th / 50th / 90th
percentile of the out-of-fold residuals of the league's points (a calibrated interval, not quantile models:
K and D/ST errors barely depend on the level, and a few thousand unit-weeks do not support a conditional
one); the floor is clipped at 0 like v2's (a Scrubs D/ST scores below 0 in 6.6% of team-weeks 2021–2025, a
K in 1.5%). Production fits on every completed season (2016–2025) and projects every unit-week of the
season; rows go to `ops.projections` (`model_version = 'kd1.0'`, `position` K / DEF, `gsis_id` = the
kicker's id or the Sleeper defense id) only for the leagues that start the position, through the same B5
writer as v2 (`projections.project` appends them before `_write_projections`), so the freeze applies
unchanged. v2's drift reads QB–TE only (`load_board` filters the positions) and v2's backtest bookkeeping
counts `v2.0` rows; `backtest-v2`'s delete leaves the `kd*` rows alone.

**Backtest** (walk-forward 2021–2025, League of Scrubs scoring, every kicker / D/ST that played, scored per
week on the unit-weeks all three scorers know; ~30 units a week, 18 weeks a season; `ops.projection_backtest`
rows tagged `kd1.0`, scorers `kd_points`, `season_ppg`, `last3_ppg`). `season_ppg` = league points per game
this season before the week (last season's before his first game); `last3_ppg` = his last three games
before the week, across seasons. Top-N = 10 (a 10-team league starts ten of each).

| Pos | Scorer | Spearman 2021 | 2022 | 2023 | 2024 | 2025 | **mean** | MAE (mean) | Top-10 hit | Coverage 80 |
|---|---|---|---|---|---|---|---|---|---|---|
| K | kd1.0 | 0.186 | 0.077 | 0.105 | 0.180 | 0.147 | **0.139** | 3.71 | 40.3% | 79.3% |
| K | season PPG | 0.101 | −0.000 | 0.045 | 0.082 | 0.118 | 0.069 | 4.06 | 36.3% | |
| K | last-3 PPG | 0.052 | 0.061 | 0.024 | 0.065 | 0.083 | 0.057 | 4.23 | 36.2% | |
| DEF | kd1.0 | 0.263 | 0.165 | 0.249 | 0.316 | 0.332 | **0.265** | 4.64 | 44.9% | 80.2% |
| DEF | season PPG | 0.098 | 0.013 | 0.050 | 0.154 | 0.076 | 0.078 | 5.14 | 36.6% | |
| DEF | last-3 PPG | 0.081 | 0.088 | 0.110 | 0.132 | 0.047 | 0.092 | 5.35 | 38.4% | |

**Ship rule** (Andrew: honest numbers, not a model for its own sake): the model ships for a position only
if its mean Spearman beats season PPG's; otherwise season PPG ships as that position's projection
(`kdef.KD_SHIP`, `ppg_projection`). kd1.0 beats season PPG in every held-out season at both positions (K
+0.070 on average, DEF +0.187) and has the lower MAE every season: both ship as the model. Weekly kicker
and defense scoring stays very noisy — a rank agreement of 0.14 for kickers means the order is only a
little better than a coin flip; the card copy says so.

**Where it is used.** `mart_player_week_projections` (K / DEF rows for the leagues that start them: context
and outcome from `mart_kd_week`, the actual priced in the league's scoring; a DEF row has `gsis_id` NULL and
is keyed by `team`); B1's lineups (`value_source = 'proj_points'`; § Lineup value); B3's waiver engine
(free-agent defenses from `mart_player_availability`'s DEF rows); the Kickers page's "Next week's kickers".

## Lineup value (B1, 2026-09-29; `league-lab lineups`, `ops.lineups`, `mart_lineup_recommendation`)

**Objective.** For one roster and one week, the lineup value is the largest total of player values
that a *legal* lineup can reach: every starting slot of the league (`dim_league_season.roster_positions`
minus BN / IR / TAXI) takes at most one player, every player starts at most once, a player only fills
a slot his Sleeper `fantasy_positions` allow (QB, RB, WR, TE, K, DEF; FLEX = RB/WR/TE; SUPER_FLEX =
QB/RB/WR/TE; REC_FLEX = WR/TE; WRRB_FLEX = RB/WR; IDP slots are not modelled and are reported), and a
slot may stay empty. Solved exactly as a maximum-weight bipartite matching
(`scipy.optimize.linear_sum_assignment`, `src/league_lab/lineup.py::solve`), not greedily slot by slot:
SUPER_FLEX is a slot like any other, so a WR who is worth more than the QB2 starts there; a player whose
value is below zero never beats an empty slot. The objective is lexicographic: **total first, filled slots
second, valued starters third** (tiny tie-break weights, 1e-9 per filled slot and 1e-12 per valued
starter). The chosen starters are then seated with the better players in the narrower slots (WR before
FLEX), which changes neither the set nor the total.

**Unvalued players** (PO decision 2026-09-29). A playable, eligible player with no value yet — a K or DEF
Sleeper has not scored in this league (first rostered in a week not yet scored), a K with no NFL id and no
Sleeper points, a QB–TE with no v2 projection this week although his team plays — is carried at value 0
with `value_source = 'unvalued'` and `reason = 'no value yet'`. By the objective above he is seated only
in a slot nobody valued can fill (a filled slot beats an empty one at equal total, and a valued player,
even one worth exactly 0, beats him at a tie), so he never displaces a valued player and never changes
the total; his margin is 0 and he is never the weakest slot. `n_unvalued` counts such starters. An
**empty slot** therefore means nobody on the roster is eligible to play there this week (bye, Out,
Doubtful, IR, taxi, nobody at the position) — or, in a realised lineup, only a negative scorer.

**Margin.** Per filled, unlocked starting slot: `margin = lineup value − lineup value with that player
removed`, re-solving the whole lineup (a WR's absence may pull a RB into FLEX and a TE into …). It is
what the player is worth to *this* lineup this week, ≥ 0 by construction; 0 means an equal alternative
sits on the bench. The **weakest slot** is the starter with the smallest margin (ties: the lower value)
— the closest lineup call. A locked starter (his game has kicked off) is not a decision and has no
margin. **Bench value** = the lineup value the playable bench alone would reach if every starter sat.

**Value sources** (`value_source`).

| Lineup | Position | Value | Source |
|---|---|---|---|
| proposed | QB / RB / WR / TE | projection v2 `proj_points` for that league-week (this league's scoring, rounded like the mart) | `proj_points` |
| proposed | K, DEF (R-13, 2026-09-30) | the kd1.0 projection `proj_points` for that league-week (§ Kicker and defense projections); a K without an NFL id takes his NFL team's projected kicker that week when the team has exactly one (never guessed when it has two) | `proj_points` |
| proposed | K without a kd1.0 projection | season points per game in this league's scoring (`mart_league_player_season.ppg`, games played > 0) | `season_ppg` |
| proposed | DEF without a kd1.0 projection, or a K without either of the above (no NFL id, or no NFL game yet) | mean of the points Sleeper scored for him in this league over this season's scored weeks his team played (byes excluded) | `observed_ppg` |
| proposed | any, when none of the above exists yet | 0, seated only where nobody valued can play | `unvalued` |
| realised | every position | the points Sleeper counted that week (`league_player_week.points_observed`) | `sleeper_observed` |

The realised lineup uses Sleeper's points for QB/RB/WR/TE too, not `points_actual` of the projections
mart: `points_actual` prices the projected components only and so leaves out 2-point conversions and
long-TD bonuses (28 rostered player-weeks in weeks 1–2 of 2026 were exactly 2 points short); a realised
optimum on it would sit below Sleeper's own max points by construction.

**Who cannot play** (listed with the reason, never in the lineup): bye (no game for his team that week),
Out, Doubtful, NFL injured reserve (`roster_status = 'RES'`), no NFL team (QB–TE on no NFL roster), no
slot for his position in this league; in a week not yet
scored also the Sleeper IR slot and the taxi squad (today's roster flags; unknown for past weeks, so not
applied there) and "game started (bench)". **Questionable plays** and is flagged (`report_status`).
**Locks**: in a week Sleeper has not scored, a player whose game kicked off before `as_of` stays where
Sleeper had him — a starter keeps his slot (value counted, no margin), a bench player stays benched
("game started (bench)"); a starter whose game has not started is free to move. Where he was comes from
Sleeper's list for that week when it exists, otherwise from today's roster: Sleeper's `starters` array
(`stg_sleeper__rosters.starter_ids`), ordered like `roster_positions` without BN / IR / TAXI (IDP slots
keep their place), "0" = an empty slot. So a Thursday game is locked correctly even when the weekly
list has not been fetched yet (B1 follow-up 2).

**Rosters.** Per week the roster is Sleeper's list for that week when there is one (first choice: every
week played so far, including the one in progress), otherwise today's roster with today's starters in
the slots Sleeper's `starters` array implies. Proposed lineups of weeks already scored are the pre-kickoff counterfactual on that week's
roster (no locks): what projection v2 would have started, for comparison with the realised optimum.

**Checks.** `tests/test_lineup.py` compares `solve()` with exhaustive enumeration of every legal lineup
(1QB, 2QB, superflex, FLEX + REC_FLEX + WRRB_FLEX, dual eligibility, byes, locks, fewer players than
slots, K/DEF present and absent, an unvalued K alone, an unvalued WR behind valued WRs, an unvalued RB
and an otherwise-empty FLEX, 240 random rosters with unvalued and zero-valued players) on all three
levels of the objective and every margin, and times both real slot
sets (median < 5 ms with margins). `assert_exact_lineup_dominates_greedy` (error): on every scored
roster-week the realised optimum ≥ `mart_league_optimal_lineup.points_optimal`, the per-week
reconstruction of Sleeper's max points, which the existing warn test holds to Sleeper's season `ppts`.
On 1,384 scored roster-weeks 2021–2026 the exact optimum equals the greedy fill in 1,367 and beats it in
17 (13 a negative scorer left out, 4 Travis Hunter — Sleeper DB, eligible at WR — started at WR), never
below; the Hunter weeks explain the 2025 gaps of the greedy against Sleeper's ppts (League of Scrubs
roster 6 −9.70, dynasty roster 11 −17.30: exact = ppts for both).

**Not modelled.** Matchup win probability or variance (the objective is expected points; P10/P90 are
not used); since R-13 K and DEF carry the kd1.0 projection, so a K or DEF first rostered in a week
Sleeper has not scored yet is valued like everyone else (the PPG paths and "unvalued" remain the fallback
where no projection exists); a K / DEF whose value is negative (an empty slot beats him; none in 2026 so
far); IDP
slots; bye-week or multi-week planning (one week at a time — the 4-week horizon is B2); Sleeper's
per-player lock time beyond the scheduled kickoff; historical IR / taxi membership for past weeks; the
waiver pool (B3: § Waiver moves). Past weeks' proposals use this season's K / DEF points per game to date (hindsight for
those two positions only).

## Roster value (B2, 2026-09-30; `mart_league_roster_value`, `_rankings`, `_slot_strength`, `_horizon`, `mart_league_acquisitions`)

Everything here is read from the B1 lineup service (§ Lineup value): proposed lineups solved on projection v2
priced in each league's scoring, one per league × roster × remaining week. Nothing is re-solved in SQL.

**This week** = the first regular-season week with a kickoff after `now()` (the rule `league-lab lineups` uses
for its next week); a week in progress (Thursday played) stays this week until its last kickoff. **Horizon** =
this week and the next three with a proposed lineup (fewer at the end of the season); every page names it
("week 4", "weeks 4–7").

| Metric | Definition | Grain |
|---|---|---|
| lineup value | `ops.lineup_totals.lineup_value` of this week: the best legal lineup (every slot solved together; FLEX / SUPER_FLEX by eligibility) | roster |
| weakest replaceable slot | the unlocked, valued starter with the smallest margin (`weakest_slot`, `weakest_margin`), with his **replacement**: the bench player who enters the re-solved lineup without him | roster |
| depth (bench value) | `bench_value`: the best legal lineup the bench alone would field if every starter sat (a QB3 counts here) | roster |
| 4-week horizon value | Σ lineup value over the horizon weeks (byes, Out / IR, taxi already in each week's lineup) | roster |
| starter strength | per slot type the roster starts: best lineup − best lineup with the roster's top starter at that slot type removed, the whole lineup re-solved | roster × slot type |
| league rank | `rank()` of the value among the league's rosters (1 = highest), per measure; each row carries its `horizon` | roster × measure |
| lineup gain (Trade Finder) | for a player X and a roster A that does not own him: best lineup of A with X − best lineup of A (= X's margin in A's re-solved lineup), per week and over the horizon | player × roster |
| lineup loss | X's margin in his own roster's lineup (0 on the bench, when he cannot play, or locked) | player |
| fit | gain of the receiving roster − loss of the giving roster: the lineup points a move creates | player × roster |
| acquired | the move that began the player's current stint on the roster (see below) | rostered player |

**Starter strength is read, not re-solved.** B1 already stores, for every unlocked starter, `margin = lineup value
− best lineup re-solved without him`, which is the definition. So starter strength is the margin of the
best-valued starter seated in a slot of that type (`is_top_at_slot_type`). Checked on the live data: all 773
unlocked starters of the 88 roster-weeks in the horizon (both leagues, weeks 4–7) have margin = lineup value −
a fresh `solve()` without him to the cent, and rebuilding each roster-week from the published rows reproduces
`lineup_value` to the cent (88/88; `docs/STATUS.md` § B2).

**Replacement.** Removing one starter from a maximum-weight matching changes the lineup along one alternating
path (a WR out, the FLEX WR slides to WR2, a bench RB joins at FLEX): exactly one bench player comes in, or
nobody worth anything (the slot stays empty or takes a player with no value yet), and the total falls by
value(starter) − value(entrant). So the entrant is the bench player worth value − margin to the cent (positive
values only; equal values: the better bench rank). Verified against the solver on the live data (773/773) and on
120 random rosters in `tests/test_roster_value.py`.

**Superflex and FLEX by eligibility.** A QB3 behind two starting QBs adds 0 to the lineup (Andrew's dynasty
roster: Rodgers 17.86 and Willis 17.28 on the bench, lineup 109.69 with or without them); a QB is a gain only
when he beats whoever sits at SUPER_FLEX (Kirk Cousins 16.19 adds +4.53 to The72Repeat, whose SUPER_FLEX is a RB
at 11.66, and 0 to Andrew's). A WR who beats the FLEX starter adds the difference even when he is nobody's WR1/WR2
(Tee Higgins 13.25 adds +3.25 to Pitts n' Titts through FLEX, over Tre Tucker 10.00). The retired
`mart_league_positional_strength` counted SUPER_FLEX as a QB slot and never attributed FLEX.

**Acquired** (`mart_league_acquisitions`). The latest move *into* this roster: a draft pick made by the roster
(`stg_sleeper__draft_picks.roster_id`), or a completed transaction whose `adds` put him there (trade, waiver,
free agent, commissioner), ordered by `status_updated` (draft picks by draft start + pick number). A dynasty reads
the whole chain (`dim_league_season.chain_id`, linked by `previous_league_id`; roster ids are stable along a
Sleeper chain); a redraft or keeper league only the current season (every season starts from its draft; a
keeper is that draft's keeper pick). Labels: "Rookie draft 2021 · 2.09" (round.pick in round), "Startup draft
2021 · 3.04" (a dynasty chain's first draft), "Trade 2025 offseason · from PhillyRoc" (the roster that gave him
up, its manager at the time; "offseason" = before that NFL season's first kickoff), "Waiver 2026 wk 2 · $36",
"Free agent 2025 wk 9". **Inherited**: when today's owner and co-owners managed none of the roster's seasons
before season S (a takeover), what it held before S is "Inherited S (<the event>)". Owner and co-owner swapping
roles is not a takeover. Sleeper records owners per season, so a mid-season takeover counts from its season.

**Not modelled.** Roster-size limits and the player sent back in a trade (the trade evaluator is Iteration 10
T-01; the waiver engine B3 handles add/drop pairs); a player on another roster's taxi squad counts as
available to the receiving roster (a roster choice, not an injury); a locked player (game kicked off) counts 0
both ways that week; a takeover within a season is dated to that season's start; the replacement's name is
ambiguous only when two bench players have exactly the same value (either is a correct answer: same total).
## Waiver moves (B3, 2026-09-30; `league-lab waivers`, `ops.waiver_moves`, `mart_waiver_moves`)

**Question.** For one roster: which free-agent claim (and which drop) improves the lineup, by how many points,
this week and over the next few weeks — and is there any at all?

**Moves.** Per roster of every current league: every free agent on an active NFL roster
(`mart_player_availability`: `is_free_agent`, `roster_status = 'ACT'`, injury not Out / IR, a position the
league can start; free-agent defenses are not in that mart) × every droppable player (on the roster today, not
in the IR slot, not on the taxi squad, not locked: his game in the decision week has not kicked off, and not a
player with no value yet — see below). **Roster size:** active players (not IR, not taxi) against the starting +
bench slots of `roster_positions`; with an open spot "claim without a drop" is a move too; an over-full roster
has no legal single move.

**Value of a move.** The B1 lineup (§ Lineup value) re-solved after the move minus before, per week:

    gain(week) = best lineup(roster − drop + add) − best lineup(roster)

on exactly the players and values `ops.lineups` holds for that roster-week (locks kept), the add valued as B1
would value him on the roster (`lineup._proposed_player`: v2 `proj_points` in this league's scoring, K at the
league's season PPG, cannot play on a bye / Out / Doubtful / NFL IR / after his game kicked off). The
**decision week** is the first week with a game still to kick off at `as_of` (default: the time the lineups
were solved); **weekly gain** = its gain; **horizon gain** = the sum over the decision week and the next three
(byes, Out weeks and the dropped player's own starts all count: what he would have contributed is what the move
gives up). `lineup_before` is `ops.lineup_totals.lineup_value` (= `mart_lineup_recommendation.lineup_value`),
so the number on the page is the number My Week shows; the starter a claim displaces is shown with his
`mart_lineup_recommendation.player_value`.

**Lists.** *Start now*: weekly gain > 0. *Cover*: weekly gain ≤ 0 and horizon gain > 0 (a bye or injury you
can cover). A move that gains in neither is not stored; a roster with no move gets one `nothing` row ("nothing
beats what you have"). *Upside stash* (a role growing before the points) needs the role alerts (R-10) and is
omitted. **No evidence yet**: the add has not played this season (his projection rests on last season and his
role) — allowed, labelled. **Rank**: horizon gain, then weekly gain, then "no drop", then the drop with the
fewest projected points over the rest of the season (`drop_ros_points`, weeks he can play) — the least useful
player; per add the first such move is its best drop (`is_best_drop`), and adds are ranked by it (`add_rank`).
Gains are rounded to 0.01; a move must gain at least 0.01.

**Unknown is not zero.** B1 carries a player with no value yet (a K / DEF Sleeper has not scored in this
league, a player with no projection, e.g. an injured star who has not played) at 0. The engine therefore
(1) keeps such a starter in his slot, so no claim is credited with "beating" a 0 that is really unknown, and
(2) never proposes dropping a player with no value in any horizon week. Without this the first run proposed
dropping League of Scrubs rosters' only (unscored) defense and an injured Josh Jacobs.

**Pruning (exact).** Removing a player never raises a lineup's best total, so a move's gain in a week is at
most the add's gain with nobody dropped, and that gain is exactly
`max(0, value(add) − bar)` with `bar = lineup − max over the open slots s he can play of lineup(without slot s)`:
the cheapest way to free a slot he can play (the starter he would push out after the reshuffle; 0 for an empty
slot). The bar depends only on the roster-week and the add's position set, so it costs a few re-solves. A free
agent at or below the bar in every week of the horizon cannot appear in either list with any drop: he is
skipped. Survivors are paired with every legal drop; a drop who does not start in the best lineup with the add
changes nothing (that lineup stays optimal), so only drops among those starters are re-solved. Re-solves reuse
B1's matching (`lineup._match`) on the roster-week's free players (locked starters fixed); the decision week's
seat for the stored moves comes from B1's `solve()` itself. `roster_moves_unpruned` evaluates every free agent ×
every drop × every week from scratch with `solve()`; `league-lab waivers --verify LEAGUE:ROSTER` compares the
two row for row (tests do the same on 24 random rosters, and check the bar against `solve()` on 40).

**Checks.** `tests/test_waivers.py`; `mart_waiver_moves` tests (lineup before = the published lineup, gains add
up, gain ≤ the add alone, lists follow from the gains); `assert_waiver_moves_are_legal` (the add is a free agent
on an active NFL roster, not Out / IR; the drop is on the roster, not IR / taxi / locked; roster size; every
roster covered). Rows of a league whose rosters or statuses changed since the moves were computed
(`inputs_fingerprint`) are skipped by the legality test and flagged on the page.

**Not modelled.** Waiver priority / FAAB and other managers' claims; free-agent defenses (no value path until
R-13); anything beyond the four weeks (a dynasty rookie's future: the page says to look twice); two-for-one
moves; the add's own injury risk beyond the report status; K values are season points per game so far (small
samples early in the season).
### Decision cards (B4, 2026-09-30; `app/lib/cards.py`, Home "My week", Matchups, the player card)

No new number: a card restates B1's lineup for one roster-week. **Which week**: the first regular-season
week of the league's season whose last game has not kicked off (`dim_game`), so a Thursday game does not
end the week's decisions — its players show as locked. **Which starters**: the unlocked, valued starters
(`lineup_margin` not NULL, `value_source` ≠ `unvalued`, and his game not kicked off at page time — B1's
`is_locked` is as of the nightly run) in B1's weakest-slot order (margin, then value, then slot order;
at a tie of the cent-rounded stored margins the mart's `is_weakest_slot` goes first), skipping a starter
nobody on the bench can replace (margin = his whole value: the only K, the only DEF), up to three.
**The named alternative** is the player who enters the best lineup when that starter sits. B1's margin is
exactly that re-solve, and removing one starter changes the optimum along one alternating path (teammates
may slide between slots; exactly one bench player comes in), so the alternative is the bench player whose
value is `player_value − lineup_margin` (± 0.011: values and margins are stored to the cent, a K's season
PPG is solved unrounded). First choice: the best unlocked bench player eligible for the slot, when his
value is that one ("start Gainwell at RB2 over Wilson, 0.45"); otherwise the bench player with that value
comes in after a teammate slides over, and the card names the teammate ("Judkins would come in at FLEX and
Golden would move to WR2"). Checked against the solver on every proposed roster-week of 2026 weeks 4–18
(both leagues, 330 roster-weeks, 978 cards: 920 direct swaps, 58 slides, 978/978 re-solves bring in exactly
the named player and lose exactly the margin) and on 360 random rosters in `tests/test_cards.py`.
**Words**: the projected difference on the card is the margin; under 1 point "a coin flip", under 3 "a
lean", otherwise "clear". The opponent's rank on a card is `mart_defense_vs_position_current.rank_std`
for his position (reference scoring, 1 = gives up the most), the same rank the Matchups page shows.
**Bench player on the player card**: the lowest-valued unlocked starter in a slot he can play and the gap
to him (a direct swap; a slide could make the real gap smaller — the card says "would have to beat", not
"is worth").

## Cornerback matchups (cb1.0, plan R-14, 2026-09-30; `mart_cb_rankings`, `mart_cb_matchups`, `mart_receiver_vs_cb`)

**What public data can and cannot say.** Pro-Football-Reference's advanced defense (nflverse, 2018 on, a few
days after each game) charges each target to a *primary defender*: per defender-game targets, completions, yards,
TDs and INTs allowed. It does not say which receiver those targets went to. The participation file (nflverse, every
completed season; the current season arrives after its postseason) lists the defenders on the field per play (and,
from 2023, a man / zone label per play) — no assignment. FTN charting (`fct_play_charting`) has no coverage or
defender field (checked: read, catchable, contested, drop, screen, play action, box count, blitzers … nothing names
a defender). Nobody publishes receiver alignment (left / right / slot). So: **"covered by" is never claimed**; the
page says "likely across from him" (a guess from where his targets go, stated as one), "on the field for 61% of
his targets vs DET" (participation) and "in games he played" (the current season).

**Coverage snaps** (`int_defender_game_coverage_snaps`): the opponent's dropbacks he was on the field for
(participation); in the current season, his share of his team's defensive snaps (PFR snap counts) × the opponent's
dropbacks. Checked on 2025 against the play-level count: total 0.973 of it, 1.64 snaps a game off on average
(`assert_coverage_snap_estimate_tracks_participation`, warn).

**Rank** (`mart_cb_rankings`, one row per cornerback × season × window). Windows: `season` (that season to
date), `last_4` (his last 4 regular-season games, that season and the one before), `two_seasons` (the season
before + that season — what the card quotes: three games of a new season are a dozen targets per corner).
Cornerback = PFR snap position CB (or DB with a PFR position CB / DB) in at least half his games in the window
(PFR's own position when the snap row is missing); safeties and linebackers are out. Ranked pool = cornerbacks with
**≥ 20 coverage snaps per team game** in the window (80 over the last 4) and a target. Three numbers, sums first:
* targets per coverage snap (how often quarterbacks throw at him);
* **adjusted yards per target**: each game's expectation = the opposing offense's WR + TE yards per target over
  that game's season and the one before, the game left out; weighted by his targets in the game. Adjusted =
  his yards per target − that expectation + the pool's expectation, shrunk toward the pool's yards per target with
  30 targets: `((ypt − exp + pool_exp) × targets + pool_ypt × 30) / (targets + 30)`. It adjusts for the offenses he
  faced, not the receivers he covered (unknowable);
* passer rating allowed: the NFL formula on the summed components (targets as attempts), each part clamped to
  [0, 2.375] — not an average of per-game ratings.

`quality_score` = − the mean of the three z-scores inside the pool (sample sd); `quality_rank` 1 = hardest to
throw on (`rank()`); `quality_label` = **shutdown** (top quarter, `rank ≤ ceil(n/4)`), **target** (bottom quarter),
**solid** (the middle half). Component ranks (`rank_targets_per_snap`, `rank_adj_yards_per_target`,
`rank_passer_rating`, 1 = best) are published beside it. Sanity check, 2026 `two_seasons` (74 ranked): top 5
Patrick Surtain II, Joey Porter Jr., Trent McDuffie, Eric Stokes, Tarheeb Still; bottom 5 DeAundre Alford,
Tyrique Stevenson, Amik Robertson, Darrell Baker Jr., Cam Hart. 2025 `season` (72): top Surtain II, Porter Jr.,
Derek Stingley Jr., Still, Riq Woolen; bottom Greg Newsome II, DaRon Bland, Brandon Stephens, Hart, Baker Jr.,
Robertson. The first version (targets per snap alone, and a pool that let safeties in through a nickel depth-chart
listing) put Coby Bryant, Brian Branch and Kyle Hamilton at 1, 2 and 4 and Christian Gonzalez 78th of 82.

**Likely cover** (`mart_cb_matchups`, one row per WR / TE × regular-season week from 2025, every rostered WR / TE
plus every WR / TE on his latest team in the current season). The opponent's rank-1 LCB, RCB and NB from its depth
chart as of kickoff (the latest snapshot before it). His targets by pass location (left / middle / right, the
offense's view) since the start of last season, before the week (`fct_play`). Rule: fewer than 15 located targets →
no call; a TE → no call (tight ends mostly draw linebackers and safeties); else the outside corner on the side more
of his targets went — **the offense's left faces the defense's right corner** (LCB when the lean is right, RCB when
left; a tie goes right; a missing corner falls back to the other outside one, then the nickel). `side_share` /
`other_side_share` = the two outside shares; `call_strength` **clear** when they are 15+ points apart, else
**even**, and the other outside corner is named too. **Checked on 2025** (as-of rows, week 2 on, per corner-game
least squares of his PFR targets on the targets of the receivers called onto him and the offense's other targets,
among the three listed starters): clear calls (545 receiver-games, 1,434 targets) — the named corner was charged
with **0.204** of the receiver's targets (se 0.025), the other outside corner 0.141, any other target 0.137-0.140;
even calls (1,888 receiver-games) — 0.185 vs 0.163. The slot corner drew 0.115-0.146 per target of these receivers
(no more than other throws), so the card does not send a "slot" receiver to the nickel: public data cannot tell who
plays inside. **A lean, not an assignment.**

**Who he faced** (`mart_receiver_vs_cb`, receiver × cornerback × season, 2022 on). `on_field` (seasons with
participation): his targets / catches / yards / TDs on the plays that corner was on the field, and
`share_of_targets` = those targets ÷ all his targets against that corner's defense(s) that season. `same_game` (the
current season): his totals in the games the corner played and the corner's average share of the defense's snaps.
History on the card = against this defense this season (before the week) and with the likely cover on the field
(on-field rows, or same-game rows where the corner played half the snaps), summed since 2022.

**Shadow corners: tested, not shown.** Per corner-season, the targets he drew per target the opposing WR1 got
against per target everyone else got (two-regressor least squares over his games); flag = ≥ 10 games, ≥ 40 targets,
slope ≥ 0.30 and 0.25 above the other slope (`wr1_follow_slope`, `other_follow_slope`, `shadow_flag` in
`mart_cb_rankings`). On six corners commonly reported to shadow in 2025 it caught **1**: Jalen Ramsey (flagged);
Patrick Surtain II (the most negative slope of the season: quarterbacks stop throwing at a shadowed WR1), Derek
Stingley Jr., Sauce Gardner, Christian Gonzalez and A.J. Terrell missed. Of the 10 corners flagged in 2024, none was
flagged again in 2025 (1–6 of 13–20 in earlier years). The page says we cannot tell who follows the top receiver.

**Evidence on the page, no projection change.** "His points against the best corners": per WR on the roster,
points per game in the league's scoring (`fct_player_game_league`) since the start of last season in games where
the corner named across from him (that week's row) was a shutdown corner vs every other game with a named corner
(the corner's label from that season's `two_seasons` rank, i.e. with that season's later games — not as-of). The
projection (v2) is unchanged: using the corner would be a model change.

**Checks.** dbt: keys unique, ranked rows complete and in range (targets per snap 0–0.6, rating 0–158.4, adjusted
ypt 0–25, expectation 3–15), unranked rows carry no rank, `last_4` ≤ 4 games, labels in the set; called rows name a
corner with shares in order and a strength, clear calls name one corner 15+ points apart, uncalled rows name none,
location shares sum to 1, a ranked cover has a label; `assert_cb_rankings_pool_size` (≥ 48 ranked: the current
`two_seasons` pool and every completed season's own); `assert_cb_matchup_covers_lineup_receivers` (every WR / TE in
a proposed lineup of the current week whose team plays has a row, called or with a reason). `tests/test_matchups.py`:
`call_cover` and `rank_corners` are the Python twins of the two SQL rules, pinned on fixtures; the evidence script
re-derives every `mart_cb_matchups` call (16,972 rows, 0 differences) and rebuilds the 2026 `two_seasons` pool from
`int_defender_game_coverage_snaps` at full precision (74 ranked, 0 rank or label differences).

## Matchup comparison (plan R-11) and defense vs position as a picture (plan R-15), 2026-09-30

**Defense profile** (`mart_defense_position_profile`, metric defense_profile v1.0, one row per season × week ×
defense × position QB / RB / WR / TE), from the defense's regular-season games of that season **before** the week
(`assert_defense_profile_is_asof` recounts the games):
* opportunity allowed: targets + carries per game to the position (QB: pass attempts + carries); targets and
  carries also per game on their own (`rank_targets`, `rank_carries`);
* efficiency allowed: yards per opportunity (receiving + rushing; QB passing + rushing) and TD rate per opportunity
  (for a WR / TE opportunities are his targets and his few carries);
* points allowed per game (reference scoring, one scale for every league, as defense vs position);
* adjusted: points allowed above what the offenses it faced usually score to the position. Each game's baseline =
  that offense's points to the position in its other games before the week plus 3 × its last-season average,
  over (its other games + 3) (the league's last-season average when it has none); the sum of the game residuals ÷
  (games + 2), so two games cannot make a defense #1;
* indices vs the league over the same windows and `gives_up` in words (± 8% band): volume and big plays, volume,
  big plays, little of either, about average. Ranks: 1 = gives up the most, of the defenses with a game.

**The comparison**: two players (default = this week's closest call on the decision cards whose two players are
QB / RB / WR / TE: the starter and the bench player who replaces him), each with his projection, floor – ceiling
(v2 in the league's scoring, `mart_player_week_projections`), the opponent and its profile as of that week. The
verdict: **"The lineup says {starter} by {margin}"** — the margin the card shows (`lineup_margin`, the re-solve) —
when the pair is that decision, else "{A} projects {difference} more"; then the matchup: it **leans** to the player
whose defense's adjusted rank is 6 or more places kinder ("his defense gives up the 4th-most carries to RBs": the
lowest of the leaning player's defense ranks among carries / targets / yards per touch / TD rate for an RB,
targets / yards per target / TD rate for a WR or TE, volume / yards per play / TD rate for a QB), "agrees" when that
is the lineup's starter, or "the matchups are about even". The page says the projection decides (it already counts
the opponent); the comparison is context.

**The picture (R-15)**: `mart_defense_vs_position_current` (reference scoring, season to date and last 4 games).
Heatmap = every defense × every position the league starts (QB / RB / WR / TE, K where it starts one), cell color
= the defense's rank against the position (one blue ramp, darker = gives up more, so positions on different point
scales compare), the number = points allowed per game; your starters' opponents pinned at the top with ◀ and the
cell where your starter plays ringed; the other defenses by their mean rank across the positions. Ranked bars = one
position, every defense ranked, yours solid and labelled with the value and rank. "Only your opponents" is on by
default at the Phone level. The table behind both stays in the expander.

## Deferred (status in registry)

| Metric | Status | What it needs |
|---|---|---|
| routes (licensed), TPRR, YPRR without the proxy label | unavailable until imported | a provider CSV through `league-lab import-routes`; **never** derived from snaps or targets |
| in-season routes proxy | unavailable in-season | the NFL publishes participation after the postseason |

## Versioning

Bump the `version` in `metric_registry.csv` when a definition changes; the explorer shows the
registry on the Data Status page. Old versions are not recomputed retroactively unless the change
is a bug fix, in which case say so in `STATUS.md`.
