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
| positional strength | sum of season ppg (the league's own scoring) over the top-N rostered players at a position (N = starting slots at that position); compared with the league median; rank 1 = strongest |
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
| League pages — Team Hub, Waiver Wire, Matchups start/sit, Trade Finder, League Intel, League (draft), weekly packs: PPG, points, PPG (L3/L5), xPPG, PPG − xPPG, positional strength, keeper / roster-value ranks, draft season points | the selected league's **current** scoring | `fct_player_game_league` → `mart_league_player_season` → `mart_player_availability`, `mart_league_keeper_candidates`, `mart_league_positional_strength`; `mart_league_draft` via `chain_id` |
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
`ops.projection_importance`; marts `mart_player_week_projections`, `mart_projection_backtest`.

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
| proposed | K | season points per game in this league's scoring (`mart_league_player_season.ppg`, games played > 0) | `season_ppg` |
| proposed | DEF, or a K without a season PPG here (no NFL id, or no NFL game yet) | mean of the points Sleeper scored for him in this league over this season's scored weeks his team played (byes excluded) | `observed_ppg` |
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
not used); K and DEF projections (season PPG is a placeholder until R-13 — a DEF or K first rostered in
a week Sleeper has not scored yet is unvalued: he fills his slot at 0, so the lineup value understates
that roster by his real expectation); a K / DEF whose season PPG is negative (an empty slot beats him;
none in 2026 so far); the K's injury status; IDP
slots; bye-week or multi-week planning (one week at a time — the 4-week horizon is B2); Sleeper's
per-player lock time beyond the scheduled kickoff; historical IR / taxi membership for past weeks; the
waiver pool (B3: § Waiver moves). Past weeks' proposals use this season's K / DEF points per game to date (hindsight for
those two positions only).

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

## Deferred (status in registry)

| Metric | Status | What it needs |
|---|---|---|
| routes (licensed), TPRR, YPRR without the proxy label | unavailable until imported | a provider CSV through `league-lab import-routes`; **never** derived from snaps or targets |
| in-season routes proxy | unavailable in-season | the NFL publishes participation after the postseason |

## Versioning

Bump the `version` in `metric_registry.csv` when a definition changes; the explorer shows the
registry on the Data Status page. Old versions are not recomputed retroactively unless the change
is a bug fix, in which case say so in `STATUS.md`.
