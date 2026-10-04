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

## Scoring spec (Wave I-C, IC-1, 2026-10-03; `league_lab.scoring.ScoringSpec`, `league_lab.scoring_audit`)

A league's rules as data, **per position**: what Sleeper's flat `scoring_settings` and MyFantasyLeague's position
groups both compile to (`from_sleeper`, `from_mfl`). It travels with the league (`league_scoring(league)` returns
the flat dict as a `LeagueScoring` carrying `.spec`; an MFL league's `mfl.scoring.spec` is its JSON); the flat dict
stays for the old readers (for MFL it is a summary, `flat_from_spec`).

| Part | Meaning | Example (MFL 70587 "Make Football Great Again") |
|---|---|---|
| `rates` | points per unit of a stat | `passing_interceptions: -3`, `fumbles_lost_total: -3`, 2-pt `2`; no `receptions` (no PPR) |
| `bands` | flat points once a game when `low ≤ stat < high + 1` (MFL's whole-number ranges) | RB `rushing_yards: (100, None, 10)`; WR / TE / QB `(75, None, 10)` rushing; TE `(75, None, 10)` receiving; QB `(250, None, 10)` passing; DEF `points_allowed: (0, 0, 10), (1, 3, 8)` |
| `distance` | per **play** by its length; every band holding the length pays (MFL's are disjoint; Sleeper's long-TD bonuses overlap the base rate) | `rushing_tds / receiving_tds / passing_tds / return_tds / fumble_recovery_tds: (0, 9, 6), (10, 39, 9), (40, 110, 12)`; K `fg_made: (0, 39, 3), (40, 49, 5), (50, 59, 10), (60, 99, 15)` |
| `steps` | MFL's `a/b` over a range: `base + a · floor((v − origin) / b)` while `low ≤ v ≤ high`; `thresholdPoints` t → base t, origin = the range's low | `rushing_yards: Step(10, None, 1, 10)` (1 a whole 10), QB `passing_yards: Step(20, None, 1, 20)` |
| `premiums` | per unit on top of `rates` for one position | Sleeper `bonus_rec_te 0.5` → TE `receptions: 0.5` |
| `unpriced` | events no stat line carries, with the platform's code and name | MFL `UY` "punt return yards"; Sleeper `def_st_ff` "special-teams forced fumble"; IDP groups |

Positions are QB RB WR TE K DEF; a unit prices with the position it stands for (`rules_for`: `TMQB` → QB, `TMPK` → K,
`TMDEF` / `Def` → DEF). Sleeper applies every key to every player, so its QB / RB / WR / TE / K (and `*`, a row with no
position) share one rule set; that is what keeps the house leagues' parity with the SQL macro.

**Actual lines** (`price_detail` / `compute_points_spec`, the scoring check): exact. A touchdown's length comes from
play-by-play (`analytics.fct_play`: `yards_gained` of the scoring play, passer / receiver / rusher) when the row's
count matches; else the row's `*_tds_40p / _50p` counts are exact at 40 and 50 and the split below 40 is interpolated
with the distance shares — said per row (`approximated_rows`). Proposed for the PO (dbt): `*_tds_10p` in
`int_player_game_pbp` → `fct_player_game`; the spec reads them when present and the check then needs no play-by-play.

**Projected lines** (`expected_frame`, what `price_lines` uses for any non-Sleeper spec, and for a Sleeper spec only
under `LEAGUE_LAB_EV_PRICING=1`):
* rates and premiums linear;
* `steps` at the **expected whole units** (`expected_floor_units`: Σ_j P(X ≥ origin + j·b)), not linear. MFL pays per
  whole 10; the brief suggested linear for an expectation, but M2 measured linear 0.3–0.5 a game too high per
  yardage stat on a 70587-style scoring (weekly bias QB −0.87 → −0.09 with the floor) — so the floor's expectation;
* a flat band at its probability, points × P(low ≤ X < high + 1 | projected mean) — M2's fitted curves
  (`scoring_ev.prob_at_least`), else (marked fallback) a normal with sd = a + b × mean (`SPREAD_FALLBACK`,
  placeholders). An MFL league always prices bands this way (a projected 249 vs 251 passing yards is not a 10-point
  difference); a Sleeper league keeps all-or-nothing on the mean until M2's yes;
* a distance band = projected TDs × Σ band points × the share of that family's TDs in the band at the position
  (`scoring_ev.td_distance_share`, else the placeholder shares `TD_SHARE_FALLBACK`: receiving ≥ 10 yd 0.55, ≥ 40 0.12;
  rushing 0.35 / 0.06; passing 0.60 / 0.14 — not measured here).

**K and DEF** price through kd1.0 (`kdef.price`) on a Sleeper-shaped dict from the spec (`kd_flat`): a Sleeper spec
hands back its own settings (no change); MFL: FG by distance onto Sleeper's buckets (50+ = the 50–59 band),
points-allowed bands onto Sleeper's by the average over each bucket's points (70587: 1–3 → 8 is 4.0 on 1–6), a
defensive / return TD at its expected points by distance.

**Parity.** For a Sleeper spec, `price_lines` is the flat path bit for bit (`compute_points_frame` on the same dict),
so the house leagues' projections did not move; `tests/test_scoring_spec.py` holds `compute_points_spec ==
compute_points` on every `tests/test_scoring.py` row and on 2,000 random lines each for Scrubs, the dynasty and a TE
premium + long-TD scoring (`compute_points` = the SQL macro, `tests/test_scoring.py`).

**The scoring check** (`scoring_audit.check`, `GET /api/league/scoring-check?league=&week=`, cached a day): for a
complete week (the clone: weeks 1–2), every rostered player's points as the platform scored them (Sleeper:
`analytics.league_player_week.points_observed`, else `staging.stg_sleeper__matchup_players`, else the matchups call's
`players_points`; MFL: `weeklyResults` per-player `score`) against `price_detail` on his `fct_player_game` line (a
`TMQB` = the team's QBs' summed line, `TMPK` the team's kickers', a defense `mart_kd_week`'s outcome line). `n` counts
rostered players matched to an NFL player who played or scored; `within_0_1`, `within_1`; each miss has
`likely_rule` — one of our pieces whose removal closes the gap to within a point (`band:rushing_yards:100`), one
event of a rate we may have counted differently (`count:sacks`), a touchdown or 2-pt we cannot see, or
`unexplained`; `suspect_rules` counts them. House leagues also compare with the dbt macro's twin
(`fct_player_game_league.points`): `sql: {n, agree, disagree}`.

Results on the clone (2026-09-26 snapshot): League of Scrubs week 1 146 / 146 within 0.1, week 2 144 / 144; the
dynasty 219 / 219 and 228 / 228; the SQL macro agrees on all of them (136 + 133, 219 + 228); the Test League 151 / 151
and 144 / 144 (by construction); MFL 70587 week 1 162 / 163 within 1 (161 to the tenth; the miss: Kansas City's
defense, 14 vs 12 — one sack more in MFL's count), week 2 156 / 156 (155 to the tenth).

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
excluded, like the baseline); the interval belongs to that projection. **Plan D6** adds the 50% range
(`p25`, `p75`, "most weeks") with the same machinery: § Ranges and decisions.

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

### NFL-wide outputs (plan F1, Wave F, 2026-10-02): reference scorings, `ops.projection_lines` / `_ranges`, `ops.kd_lines` / `_ranges`

The stat line is league-independent (`docs/ANY_LEAGUE.md`), so `league-lab project` now writes it once for the NFL
and the ranges once per **reference scoring**, not per house league. Same model (v3.0 / kd1.0), same fits.

**Reference scorings** (`dbt/seeds/reference_scorings.csv` → `analytics_seeds.reference_scorings`: `name`, `label`,
`scoring_settings` jsonb; read by `projections.reference_scorings`, the seed file when the table is not built yet):

| `name` | label | what it is |
|---|---|---|
| `scrubs` | Half PPR, 4-pt pass TD | League of Scrubs' `scoring_settings`, copied from `dim_league_season` on 2026-10-02 (Sleeper's defaults at half PPR; K and DEF keys) |
| `dynasty` | Full PPR, 6-pt pass TD, yardage and long-TD bonuses | Forever Unclean Dynasty's, copied the same day (−2 per INT, 0.05 per passing yard, 300/400-yard, 100/200-yard and 40+ TD bonuses) |
| `ppr` | Full PPR, 4-pt pass TD | Sleeper's defaults (= `scrubs`) with 1 point per catch |
| `standard` | Standard (no points per catch), 4-pt pass TD | Sleeper's defaults with 0 per catch |
| `te_premium` | Full PPR plus 0.5 per tight-end catch, 4-pt pass TD | `ppr` + `bonus_rec_te` 0.5 |

**What is fitted.** The residual quantile models (P10 / P25 / P50 / P75 / P90 and the per-tier conformal widening)
are fitted once per reference scoring (`PositionModel.quantiles[(scoring_name, q)]`); the component models once
(they are league-free). Each regressor has its own seed, so a reference's models are exactly what a league with that
scoring had before (the log's per-tier widening for `scrubs` / `dynasty` equals League of Scrubs' / Forever Unclean's
before F1, to the printed digit). A house league is matched to the reference that **is** its scoring
(`projections.exact_reference`: the same non-zero weights, within 1e-9, on the keys a projected QB–TE line can carry
— `scoring.priced_keys(scoring, ALL_COMPONENTS)`; kicking, 2-point, long-TD and defense keys do not decide). A house
league no reference is (its commissioner changed the scoring) is fitted on its own, as before F1, with a warning:
add its scoring to the seed. Cost: the residual models are most of `project`; five scorings instead of two.

**The tables** (one copy for every league; the B5 freeze applies to each, below):

| Table | Grain | Columns |
|---|---|---|
| `ops.projection_lines` | season × week × gsis_id (QB–TE) | `model_version`, `fitted_at`, `train_seasons`, `position`, the 12 `proj_*` components, `frozen_at`, `frozen_source` |
| `ops.projection_ranges` | scoring_name × season × week × gsis_id | `position`, `model_version`, `fitted_at`, `proj_points` (the line priced in the scoring, `scoring.compute_points`, bonuses included), `p10`, `p25`, `p50`, `p75`, `p90`, `frozen_at`, `frozen_source` |
| `ops.kd_lines` | season × week × position × unit_id (K, DEF) | `model_version` (kd1.0), `fitted_at`, `train_seasons`, the K line (`proj_fg_made_0_19` … `proj_fg_made_50p`, `proj_fg_missed` and its split `proj_fg_missed_*`, `proj_pat_made`, `proj_pat_missed`) or the DEF line (`proj_sacks`, `proj_interceptions`, `proj_fumble_recoveries`, `proj_forced_fumbles`, `proj_def_tds`, `proj_st_tds`, `proj_safeties`, `proj_blocked_kicks`, `proj_points_allowed`, the bucket probabilities `proj_pa_0` … `proj_pa_35p`), the other position's columns NULL; freeze labels |
| `ops.kd_ranges` | scoring_name × season × week × position × unit_id | `proj_points` = `kdef.price` of the line in the scoring, `p10` / `p50` / `p90` = `kdef.interval(proj_points, offsets)`, the offsets `off_p10` / `off_p50` / `off_p90` (fitted per scoring × position on the out-of-fold residuals, constant over the season); no rows for a scoring that pays nothing for the position |

`unit_id` is the kicker's gsis_id or the Sleeper defense id (`KC`, `LAR`) — `ops.projections.gsis_id` of the same K /
DEF row. **Pricing a K / DEF in any scoring**: `proj = kdef.price(line, position, scoring, "proj_")`, then
`kdef.interval(proj, (off_p10, off_p50, off_p90))` with the offsets of the reference the league is matched to (sort,
P10 ≥ 0, P90 ≥ the projection, P10 ≤ P50 ≤ P90).

**The house leagues' `ops.projections`** (the Streamlit console, drift, the backtest's record, lineups, waivers read
it) is derived from the same numbers: QB–TE rows = the line priced in the league's own scoring (`proj_points`) and
the P10–P90 of the reference the league is (`projections.house_rows`, which refuses a reference whose price of the
line differs by more than 1e-6); K / DEF rows = `kdef.predict_kd` in the league's scoring from the same lines and
the same offset fit as `ops.kd_ranges`. Tests: `assert_house_projections_are_the_nfl_wide_rows` (line, P10–P90,
label and `fitted_at` equal to 1e-9 for every week, no row on one side only), `assert_projection_ranges_price_the_lines`
(`proj_points` = the line re-priced by the SQL `league_points` macro, 1e-6, `scrubs` only since Wave I-D: the dynasty's
bonuses are priced at their probability by `scoring.price_projected` under `LEAGUE_LAB_EV_PRICING`, which the macro
cannot express — `tests/test_projections_ev.py` pins its nightly and request-side prices equal instead).

**The freeze (B5) on the new tables.** The same `freeze_plan`, relabel and repair as `ops.projections`, with one
`fitted_at` and one `now` per run for every table. Freeze unit: the week for the line tables, the scoring × week
for the range tables (a reference added mid-season gets its own labels). A started unit with nothing stored (the
tables' first run; a reference added mid-season) is filled so the tables agree with each other and with the record:
the QB–TE lines from `ops.projections`' rows of the week (the first house league's, labels and `fitted_at` kept); a
reference that is a house league takes that league's `ops.projections` ranges; any other reference is ranged around
the stored line by the current models and the week's as-of features (`predict_position(..., lines=...)`), labelled
`refit`. K / DEF: the record holds priced points only, so a started week with no stored line gets the current
line, labelled `refit`; `ops.kd_ranges` is always the stored line priced plus the offsets. On the first run
(2026-10-02): weeks 1–3 (`refit`, v2.0) and 4 (`kickoff`, v3.0) came from the record. Test:
`assert_frozen_nfl_wide_precede_kickoff` (the five rules of `assert_frozen_projections_precede_kickoff`, per unit).

**TE premium (and the RB / WR catch premiums).** `scoring.SLEEPER_POSITION_MAP` (`bonus_rec_te`, `bonus_rec_rb`,
`bonus_rec_wr`): `compute_points` pays the weight per catch when the stats row carries the player's `position`
(`projections.price` passes it; a row without one prices it 0, exactly as before). They are not in `MAPPED_KEYS` or
`scoring_stat_map`: the SQL `league_points` macro has no position to condition on, so `unmapped_keys` still reports
them and `assert_unmapped_scoring_keys_are_known` still flags a house league that enables one. `te_premium`'s
ranges therefore exist in Python only (the SQL pricing test covers `scrubs` and `dynasty`).

**Rules for the seed.** A reference scoring's settings are never edited once published — frozen weeks were priced
in them; add a new `name` instead (a house league whose commissioner changes the scoring stops matching its
reference and is fitted on its own until a reference for the new scoring is added). The two comparison tests
(`assert_projection_ranges_price_the_lines`, `assert_house_projections_are_the_nfl_wide_rows`) and the
`scoring_name` relationship test are `warn`: the nightly's full `dbt build` runs before `project`, and an error
there would stop the night before the refit that repairs the live weeks. The freeze test is `error`, like B5's.

### Projection v3 (v3.0, 2026-10-01; Wave D): personnel inputs by position

v3 is v2 (every input, hyperparameter and interval model above; D6's 50% range and per-tier conformal widening, §
"Ranges and decisions") plus the two personnel sub-groups the harness kept (§ "Personnel", § "Feature experiments"),
**per position** (`projections.FEATURES_BY_POSITION`; the lists live in `league_lab.feature_groups.personnel`):

| Position | Inputs | Added (plain name on Rankings) |
|---|---|---|
| QB | `FEATURES` + 5 | `pn_qb_starting` "Is he the projected starter?", `pn_qb_games_together` "Games he has played with this week's QB", `pn_qb_prev_ppg_diff` "This week's QB vs his usual QB, points per start", `pn_qb_is_rookie_or_backup` "This week's QB has started fewer than 8 games", `pn_qb_changed` "A different QB starts than in his recent games" |
| RB, WR, TE | `FEATURES` + 4 | `pn_top_target_out` "Top target on his team out this week", `pn_top_rusher_out` "Top ball carrier on his team out this week", `pn_teammate_share_out` "Share of the team's targets out this week", `pn_absence_beneficiary` "His role grew when a teammate went out, and that teammate is still out" |

The nine columns reach the model through `mart_player_week_features` (left-joined from `int_player_week_personnel`;
`assert_features_never_peek` covers them: `pn_asof_week` < week, the teammate inputs NULL in week 1). Dropped by the
harness and not in v3: game context, rest and travel, weather, team volume and style, the offensive line, a player's
own injury history. The K / DEF model is unchanged (kd1.0). The projected starter for a game nflverse has not filled
yet (more than about a week ahead) is the starter of the team's newest played game (`proj_qb_source = 'last_start'`):
the board's later weeks assume the same starter rather than leave unknown an input that is always known in training.

**Backtest** (`league-lab backtest-v2 --seasons 2021-2025`, both leagues, priced line, mean over seasons of the
league-averaged season means; "n/5" = seasons better; the v2.0 rows of `ops.projection_backtest` are its record from
an earlier run and stay; `mart_projection_backtest.is_current` picks v3.0):

| Pos | Spearman v2.0 → v3.0 | Δ (n/5) | MAE v2.0 → v3.0 | Δ (n/5) | Coverage 80 v2.0 → v3.0 | Coverage 50 v3.0 | Width 80 v2.0 → v3.0 | Width 50 v3.0 | Interval score v2.0 → v3.0 |
|---|---|---|---|---|---|---|---|---|---|
| QB | 0.538 → 0.582 | **+0.0445 (5)** | 7.01 → 6.49 | **−0.52 (5)** | 77.9% → 78.4% | 48.9% | 22.8 → 21.5 | 11.1 | 1.516 → 1.434 (−0.082) |
| RB | 0.662 → 0.670 | +0.0086 (5) | 4.54 → 4.50 | −0.044 (5) | 79.7% → 80.4% | 51.0% | 13.6 → 13.9 | 7.3 | 0.993 → 0.979 |
| WR | 0.617 → 0.622 | +0.0047 (4) | 4.47 → 4.46 | −0.002 (3) | 81.0% → 80.7% | 49.9% | 13.7 → 14.2 | 7.3 | 0.968 → 0.960 |
| TE | 0.562 → 0.565 | +0.0024 (4) | 3.29 → 3.29 | +0.002 (2) | 81.0% → 81.3% | 50.4% | 9.7 → 10.0 | 5.2 | 0.736 → 0.733 |

QB by season: +0.048 / +0.018 / +0.071 / +0.024 / +0.062. The coverage and width changes include D6's per-tier
widening (starters' ranges were too narrow), not only the new inputs. On identical data, 2023–2025 against the
harness's cached v2 baseline (key `cb461af0c56b4811`), v3.0 reproduces the harness: QB +0.0528 / MAE −0.541 /
interval score −0.082 (the `qb` group exactly, cell for cell), RB +0.0065, WR +0.0058, TE +0.0061 (the `teammates`
group: +0.0064 / +0.0053 / +0.0054; the ±0.002 difference is the Raiders 2016–19 / Chargers 2016 absence alerts the
`int_player_game_role` fix added to training). The stored v2.0 record itself differs from that baseline by up to
±0.004 per cell (an older run), which is why the five-season Δ at RB / WR / TE above is not the harness's to the digit.

**What drives it** (component importance, 2025 held out from a 2016–2024 twin, reference scoring; Rankings "What it
leans on most"): QB **1st `pn_qb_starting` (+1.83 points of error when scrambled; next, the implied total +0.18)**,
6th games with this week's QB (+0.07); RB 4th top ball carrier out (+0.06); WR 5th share of the team's targets out
(+0.02); TE 10th share of the team's targets out (+0.02).

**Live board.** On a database where week 4 froze before v3 shipped (the Mac: week 4's board froze at its first
kickoff, 2026-10-02 00:15 UTC, with v2.0 rows) v3 starts at week 5; weeks already frozen keep their v2.0 rows and
`model_version` says which model made each row; the drift strip compares a season with the backtest of the newest
model on its board. Two consecutive `project` runs write byte-identical weeks 4–18 (`ops.projections`, md5 in STATUS).

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

## Weather (plan D3, Wave D round 1, 2026-10-01; `league_lab.ingest.weather`, `int_game_weather`, `int_player_week_weather`)

Andrew asked about "weather during that day, wind conditions, precipitation". v2 does not use weather
(the Vegas total prices some of it in). D3 builds the feature group and measures it; nothing ships
until the feature-group harness keeps it (one `MODEL_VERSION` bump for v3).

**Where the numbers come from.** Open-Meteo at the stadium's coordinates (`raw.nfl_stadiums`), hourly,
for the **kickoff hour and the two after it**: wind speed and temperature at hours k, k+1, k+2
(instantaneous), gusts / precipitation / snowfall at k+1, k+2, k+3 (Open-Meteo reports those for the
preceding hour), so both cover the game's first three hours. Kickoff = nflverse `gameday` + `gametime`
in US Eastern (every game, London included), requested in UTC. History = the Open-Meteo archive (ERA5
reanalysis); the live board = the Open-Meteo forecast (up to 16 days ahead, refreshed nightly). Until
the first real run backfills `raw.nfl_weather` (Open-Meteo is unreachable from the development
sandbox), past games fall back to the schedules' observed `temp` / `wind` (no gust, no precipitation).

| Column (`int_player_week_weather`) | Definition | NULL when |
|---|---|---|
| `wx_dome` | 1 = the weather does not reach the field: a fixed dome (stadium reference), or a retractable roof that is closed — **or not decided yet** (every upcoming game: nflverse fills `roof` on game day; 370 of 418 retractable-roof games 2016–2025 were played closed, 89%); 0 = open to the weather. The reference wins over nflverse's `roof` for fixed roofs (nflverse calls the MCG, Stade de France and the Munich stadium `dome`) | the venue is not in the reference |
| `wx_wind_mph` | mean 10 m wind speed, mph (hours k..k+2); 0 in a dome | no source for an open-air game |
| `wx_gust_mph` | max 10 m gust, mph (k+1..k+3); 0 in a dome | Open-Meteo has not answered for the game (the schedules have no gusts) |
| `wx_precip_in` | precipitation (rain + snow water equivalent), inches, sum over k+1..k+3; 0 in a dome | as gusts; also when an hour is missing (a sum with a gap would understate it) |
| `wx_temp_f` | mean 2 m temperature, °F; **0 in a dome** (the contract: every weather feature 0 under a roof; `wx_dome` tells a dome from a 0 °F game) | no source |
| `wx_cold` | 1 when outdoors and `wx_temp_f` < 32 | `wx_temp_f` NULL |
| `wx_windy` | 1 when outdoors and `wx_wind_mph` ≥ 15 | `wx_wind_mph` NULL |
| `wx_snow` | 1 when Open-Meteo has snowfall or a WMO snow code (71–77, 85–86) in those hours | no Open-Meteo answer |
| `wx_source` | `archive` · `forecast` · `nflverse_observed` · `none` (open-air, nothing known) · `dome` — bookkeeping, not a model input | never |

**Which value a game gets** (`int_game_weather`): a played game takes the archive, else the schedules'
observation, else its last forecast; an upcoming game its newest forecast (always fetched before
kickoff). `assert_weather_never_peeks`: an observation only for a game played before it was fetched,
a forecast only from before kickoff, no observation for a game not yet played;
`assert_weather_dome_rows_zero`; one row per universe row (`assert_weather_one_row_per_universe_row`).

**Venue.** The schedules' `stadium_id`, except a per-game correction (`stadium_game_venues.csv`: the seven
2025 international games nflverse records at the home team's stadium — São Paulo, Dublin, London ×3,
Berlin, Madrid) and a stadium name that belongs to another venue (2026_05_PHI_JAX, `JAX00` "Tottenham
Hotspur Stadium" → London). `assert_stadium_reference_covers_schedules` (warn) flags a new stadium id or
an early kickoff at a US stadium.

### The train / serve gap (measure it, do not assume it away)

Training and the backtest see the weather **as it was** (archive, or the stadium's own report); the live
board sees **a forecast** made one to six days earlier. A model that learned "20 mph wind costs a
kicker 1.5 points" applies that to a forecast of 20 mph that may verify at 12. Three consequences:

1. The backtest's gain from a weather group is an **upper bound** on the live gain.
2. The schedules' observation (field level, the stadium's report) and the archive (10 m, model grid)
   differ in level as well: the sandbox evaluation uses the former, the first real run switches every
   past game to the archive, so the harness must be **re-run after the backfill** before any keep
   decision is final. `int_game_weather` keeps `archive_*`, `nflverse_*` and `forecast_*` side by side.
3. **The plan to measure it**: every forecast is kept (`raw.nfl_weather`, `source = 'forecast'`, one row
   per game per nightly fetch, `forecast_hours_ahead`; never overwritten by the archive). After one
   season of forecasts (2026: about 200 open-air games × up to 16 nightly fetches each), compare per lead time (0–24 h,
   1–2 d, 3–4 d, 5–7 d) the forecast with the archive for the same game: mean error and MAE of wind,
   temperature and precipitation, and the share of `wx_windy` / `wx_cold` flags that flip. Then re-score
   the season's played weeks with the features from the forecast the board actually had at its
   kickoff freeze (the B5 decision record time) instead of the archive: the difference in Spearman /
   MAE is the live value of the group. If it is gone at the board's usual lead time, the group stays
   out (or ships only for the Sunday-morning refit).

The retractable roof is a second, smaller gap: training knows whether it was open; the board assumes
closed until game day (the roof is open for about 1 game in 9, in mild weather).

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

### Drop cost (IF-1, Wave I-F, 2026-10-03; `waivers.choose_drops`, `drop_pieces`, `DropCost`)

The decision-quality review (Priority 2): B3 named, among equally good moves, the drop with the fewest projected
points, so a bench WR who does not start in the next four weeks was the drop for every claim ("he sits anyway"),
even for a kicker claim whose incumbent kicker becomes redundant. A drop now has a **cost**, per (add, drop) pair,
the most (never the sum) of five pieces, each in points of the league's scoring:

| Piece | Definition |
|---|---|
| `lineup_loss` | his starts over the horizon the move gives up **with the add on the roster**: the add's gain alone − the move's gain (Carlson for McPherson: 0, Carlson takes the K slot) |
| `depth_lost` | Σ over the horizon weeks he sits: max(0, his projection − the best free agent's at his position that week) × the chance a starter he can cover misses (1 − (1 − r)^n, n = starters at his position, r = `ABSENCE_RATE`: QB 0.06, RB 0.12, WR 0.10, TE 0.09, K 0.02, DEF 0 — documented constants, not yet fitted to the availability history) |
| `future_starts` | Σ over the weeks after the horizon he starts in today's roster's best lineup: what the lineup loses when he is replaced by the best free agent at his position (that free agent's season points ÷ the weeks left less a bye). Measured without the add: a free agent at the add's position is at least as good as the add, so the add can only lower it |
| `season_value` | `trades.price_by_player`'s rule: max(0, rest-of-season points − the best free agent's at his position) (`MARKET_SQL` / `REPLACEMENT_SQL`; on demand `market_points` / `replacement_level`; a team unit against the best free unit). A 1-QB wire holds starting QBs (a QB3 is worth ~0), a superflex wire does not |
| `upside` | Σ over the horizon of a role scenario's extra points (`ops.player_scenarios.points_gain`), when he has one |

**Net gain** = the move's lineup gain − (cost − lineup_loss) — the roster value the lineup numbers do not already
count; over the horizon it equals the add's gain alone − the cost. **The best drop per add** is the cheapest
(equal costs: the starter the add replaces this week — `drop_is_incumbent` —, then the fewest rest-of-season points).
Moves are ordered by net horizon gain, then net weekly gain. **Worthwhile** (`is_worthwhile`): net ≥ 1 this week
(`WORTH_WEEK`) or ≥ 3 over the horizon (`WORTH_HORIZON`); when no claim is, Waivers says "No claim is worth a roster
spot this week" instead of a claim. A **stash** recommends its drop only when the scenario's lineup gain beats the
drop's own cost; otherwise "watch" and what would change it.

**Columns** (`ops.waiver_moves`, added by `_write`'s `alter table … add column if not exists`): `drop_cost`,
`drop_cost_piece`, `drop_lineup_loss`, `drop_depth_lost`, `drop_future_starts`, `drop_future_start_weeks`,
`drop_season_value`, `drop_season_points`, `drop_replacement_points`, `drop_upside`, `drop_is_incumbent`,
`net_weekly_gain`, `net_horizon_gain`, `is_worthwhile`. A mart built before them is re-ranked on read by the API
with the season value (and upside) only.

**Not modelled.** Trade value from a real market; injury-specific absence rates (constants); the add's own future
starts beyond the horizon (only the drop's); a probability on the role scenario (it is a what-if).

**The stash writer (IG-3, Wave I-G, 2026-10-04; `waivers.upside_for_roster`, `upside_stashes`).** The nightly's upside
stashes (`ops.waiver_upside`) used B3's drop (the least lineup loss over the horizon, ties to the fewest
rest-of-season points) and the API decided claim / watch on read. Now each stash add is paired with every legal drop
(none on an open roster spot) at the scenario's projection ("if it holds"); each pairing is an `ops.waiver_moves`-shaped
row — the lineup loss with the add, plus the drop's pieces from the same sweep (`load_and_sweep(pieces_out=…)` hands
every droppable player's `drop_pieces` to the stash writer; run alone, it reads them back from `ops.waiver_moves`) —
and `choose_drops` names the cheapest. The row carries `stash_action` = **claim** when that pairing is worthwhile if the
role holds (net ≥ 1 this week or ≥ 3 over the horizon — the same bar as any claim), else **watch**, plus `drop_cost`,
`drop_cost_piece`, `net_weekly_gain`, `net_horizon_gain`. A watch row keeps the drop a claim would take (the legality
tests read it); the screen shows no drop for it. The API shows the writer's call as written and re-decides only rows
written before Wave I-G (the old rule: the scenario's lineup gain against the drop's own cost). The stash case itself
(no pairing gains at his projection) and every gain are unchanged. On `league_lab_i0b` (2026-09-26 clone): 83 stashes,
all **watch** (the scenarios add nothing to these lineups over weeks 4–7); their drops moved on 6 of 36 dynasty rows
(B3's Jordan Mason / Carson Beck → DeeJay Dallas / Greg Dulcich: the cheaper by season value), none on Scrubs.
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
lean", otherwise "clear". **Since plan D6** the headline is the probability that the starter outscores the
alternative (50–55% a coin flip, 55–65% a lean, 65%+ clear; § Ranges and decisions) and the margin is the
second line; the margin's words remain only where there is no probability (K, DEF, points-per-game values). The opponent's rank on a card is `mart_defense_vs_position_current.rank_std`
for his position (reference scoring, 1 = gives up the most), the same rank the Matchups page shows.
**Bench player on the player card**: the lowest-valued unlocked starter in a slot he can play and the gap
to him (a direct swap; a slide could make the real gap smaller — the card says "would have to beat", not
"is worth").

## Trades (T-01 evaluator, T-02 simulator, 2026-09-30; `league_lab.trades`, Trade Finder, the weekly pack)

**Question.** For a package — players of my roster for players of one other roster — what happens to *both*
best lineups this week and over the next four, to depth and roster size, and is it a fair price? Across the
league: who should I call, with what? Two answers, never blended: **fit** (lineup points) and **market**
(what the players are worth), plus a one-sentence verdict that reads both.

**Fit (lineup gain of a package).** Per roster and per week of the horizon (this week and the next three: the weeks
of `mart_league_roster_horizon`, § Roster value), with B1's `lineup.solve` on the players and values `ops.lineups`
holds for that roster-week (`RosterBoard`):

    gain(roster, week) = best lineup(roster − what it gives + what it gets − its cut) − best lineup(roster)

**Before** = `ops.lineup_totals.lineup_value` (reproduced to the cent by the re-solve). A player it gets is
carried as B1 carries him on his own roster (`roster_value.incoming_player`): nothing that week on a bye, Out /
Doubtful, NFL injured reserve or in Sleeper's IR slot; a taxi-squad player can play. **Locks**: a player whose
game that week has kicked off stays with his roster that week (his points count there) and moves from the
next week; a locked starter keeps his slot. **This week's gain** = the first week; **horizon gain** = the sum over
the four weeks. Gains are rounded to the cent; the page shows one decimal. Both sides are evaluated with the
same code (`evaluate(board, give, get)`: one board holds both rosters of the league).

**Depth, closest call, who starts and who sits** (this week, both sides). Depth = the best lineup the bench alone
would field (`solve(bench)`, B1's `bench_value`; before = `mart_league_roster_value.bench_value` to the cent).
Closest call = B1's `weakest` of the after-lineup (the unlocked starter with the smallest margin). Who starts = the
after-lineup's starters who did not start before (arrived, or up from the bench); who sits = the before-lineup's
starters who do not start after (traded, cut, or to the bench), each named on the page.

**Roster size.** Active spots = starting + bench slots of `roster_positions` (IR and TAXI slots are not spots);
active players = not in the IR slot, not on the taxi squad (B3's rule). Every player a roster gets takes an
active spot (Sleeper puts a traded player on the bench); a player it gives frees one only if he held one. A
roster left over its limit **cuts** until it fits (never more): the cut is the droppable player whose removal
costs the post-trade lineups least over the horizon (0 for a player who starts in none of them — the lineups
stay optimal without him), ties to the fewest rest-of-season projected points (B3's drop rule); every droppable
player is compared (the first version stopped after the first starter when no cut was free — found by the hand
check, fixed, and a test now holds it); two cuts are taken one at a time. Droppable = was on the roster, stays,
active, not locked this week, has a value in some horizon week (unknown is not zero). **The cut's loss is in the
after-lineups** (and so in the gain). A roster left with a spot **the trade opened** is shown the best free
agent to fill it: among free agents on an active NFL roster (not Out / IR; `mart_player_availability`), valued
per week at this league's projection (`ops.projections`; bye = no projection; Out / Doubtful, NFL IR or a game
already kicked off = can't play), the one whose addition raises the post-trade lineups most over the horizon,
then this week — exactly, with B3's entry bar (an add's gain with nobody dropped is max(0, value − bar), § Waiver
moves). The fill is reported, never added to the gain.

**Market (the fairness score), kept apart from fit.** Per player:

    season points = Σ ops.projections.proj_points (this league's scoring, each week rounded to the cent) from this week to week 18
    market score  = max(0, season points − replacement(position))
    replacement   = the most season points of a free agent at that position (active NFL roster, not Out / IR); 0 if none

(`trades.MARKET_SQL`, `trades.REPLACEMENT_SQL`, `price_by_player`). What we chose and why:
*projection, not PPG*: the market score starts from the one projection every page uses (v2 in this league's
scoring, K and DEF at kd1.0), and v2 already weighs usage — its strongest inputs are expected points (xPPG, last 5
and season) next to points per game — so it is "xPPG-weighted" without a second model; the season's PPG and xPPG
are shown next to it (the market line) because PPG is what the other manager sees. *Position-adjusted by the
waiver wire*: a kicker projects about a WR3's season points, but a better one is on waivers (League of Scrubs:
the best free-agent kicker projects 127 season points, more than any rostered kicker), so his market score is
0; in the one-QB League of Scrubs the waiver wire holds 239-point QBs (a rostered QB below that scores 0), in the
superflex dynasty the best free-agent QB projects 113. *Whole points*: each player is rounded half up, then the
side is summed, so the fairness line's totals are the market column's numbers. A player with no projection has
no market score: counted as unknown and said so, never 0. **About even** = the two sides within 10 points or
10 % of the larger (`trades.about_even`).

*Why it is only a rough guide* (said on the page): it is this season only (a dynasty's future years, draft picks
and keeper costs are not in it); it counts every projected week, injured or benched (a player on IR is priced as
if he plays); the replacement is one free agent's projection (a hot pickup moves the bar); and other managers
price on names, PPG and need, not on our projection — the verdict says "expect", never "will".

**Market line** (every player in a package, next to the lineups, never added to them): market score, season points,
PPG and xPPG this season and position rank by season points in this league's scoring (`mart_league_player_season`),
games, age (from `dim_player.birth_date`) and NFL season (season − `rookie_season` + 1, 1 = rookie), and this
week's value.

**The three lines (T-02).**
* *Fit line*: "Fit (what the best lineups gain): you +g this week and +G over weeks 4–7; them +h and +H."
* *Market line*: "Market (season points above the best free agent at the position): you give M_out, you get M_in:
  about even | you get / give N more."
* *Verdict* (one sentence): whose lineup it helps and by how much (this week first, or the horizon first when the
  week is negative), then the market, then the likely answer — both lineups gain over the horizon: "worth
  offering", or "they may ask for more" when the market says they give up more; only mine gains: "expect a no",
  or "a rebuilding team might take it for the value" when the market says they get more; mine does not gain:
  "skip it", or "only worth it for the season value" when the market says I get more. Example (dynasty, Andrew's
  roster): "Helps you +5.4 this week (+27.3 over weeks 4–7), them +6.8 (+29.0 over weeks 4–7); the market calls
  it about even: worth offering."

**League rank change.** `mart_league_roster_rankings` (measures `lineup_value`, `horizon_value`, `bench_value`) with
the two rosters' values replaced by their post-trade totals; `rank()` semantics (ties share a rank).

**Partners (who to call).** For every other roster: the best **1-for-1** and the best **2-for-1** (two of mine
for one of theirs, or one of mine for two of theirs) that raise **both** lineups over the horizon (each ≥ 0.01),
ranked by the **smaller of the two horizon gains** (the trade both sides gain most from), then their sum; a trade
that helps only one side is never listed ("no trade helps both of you" is an answer per team). A two-for-one counts
only when each of the two players adds to the lineup of the team getting them after it loses the player it
gives; otherwise it is a one-for-one with a throw-in (a throw-in changes neither lineup: the receiver cuts his
cheapest player). The best partner = the roster whose best package ranks first. Moved players: every rostered
player with a value in some horizon week. The horizon is the test (it includes this week): a trade that helps
both this week and costs one side over four weeks is not one both should accept.

*Exact search with bounds (branch and bound).* A lineup is a maximum-weight matching, a gross-substitutes
valuation, hence submodular in the player set: adding a set of players gains at most the sum of what each would add
alone, and removing players never raises the total. So for a package my horizon gain is at most what its incoming
players add to (my roster − the players I give) minus what losing those costs me; the same for them; a 1-for-1's
bound is its exact value when no cut is needed, and a cut only lowers a gain. What one player adds to a roster-week
is exactly max(0, value − bar) (B3's entry bar), so every bound is a lookup once the bars of the rosters involved
(mine, theirs, each without one player) are prepared. Candidates are evaluated with the evaluator's own code in the
order of their bound until the bound drops below the best package found. `partners_exhaustive` evaluates every
package with no bound: identical results on 4 random 3-roster leagues × all shapes (tests) and on every partner of
both real leagues for all shapes (Andrew's rosters, after the cut fix: dynasty 11/11 partners identical, exhaustive
315 s vs 0.6 s; League of Scrubs 9/9, 64 s vs 0.6 s). **Timing** (page time, computed once per league / team / data
version and cached 10 min): every roster of both leagues, a fresh board each time, the sandbox shared with two
other builds (load 3.7): dynasty median 0.81 s, max 1.20 s (12 rosters, 114–288 packages re-solved in full each);
League of Scrubs median 0.63 s, max 0.98 s (10 rosters). Andrew's dynasty roster 12: 13,212 packages bounded, 149
evaluated.

**Checks.** `tests/test_trades.py` (33: 1-for-1 both gain reproduced by hand; 1-for-1 where one side loses, never a
partner trade; depth, closest call, who starts / sits; 2-for-1 with the forced cut and the market sums; the cheapest
cut when nobody is free (byes over the horizon; fails on the first version); a K-for-WR trade that empties the K
slot and prices the kicker at 0; bye weeks over the horizon; a trade that empties a slot; locks; IR / taxi spots;
the fill against brute force; 96 random packages never over the roster size, a single cut against brute force;
the partner search against the exhaustive search; fit / market / verdict lines; rank change; URL parameters) and
`tests/test_trade_finder_page.py` (AppTest on the database: the page opens on the best partner's trade, the
simulator equals `evaluate`, the market line's numbers are the table's, a pasted link reproduces the package,
broken links render, the buy-low list filters by position and owner).

**Not modelled.** Draft picks, keeper costs and seasons after this one (a dynasty trade's long run: the market
score is this season only); waiver priority / FAAB for the fill; what the other manager believes (the verdict
is a heuristic, not a prediction); a traded player's Sleeper IR / taxi status on his new roster (he takes a bench
spot); two cuts chosen jointly (they are taken one at a time); 3-for-1 or 2-for-2 in the partner search (the
simulator takes any package). No `metric_registry.csv` rows (seeds are out of bounds for this task); proposed:
`trade_fit` (v1.1: package gain per roster, week and horizon), `trade_market_score` (v1.0: season points above
the best free agent at the position, grain player × league × week).
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
## Matchups: the tone and one rank direction (IB-3, Wave I-B, 2026-10-03; `research.defense_meaning` / `cb_meaning`)

The screen's main signal is a tone — **favorable / neutral / difficult** — and every rank on it runs one way:
**1 = the toughest for the offense**. Display only: the marts keep their own ranks (`rank_std`: 1 = gives up the
most; `quality_rank`: 1 = hardest to throw on) and the console keeps its words.

* **Defense vs position** (`/api/matchups/defense`, each team × position row): `n_ranked` = the defenses ranked at
  the position (`rank_std` not null); `tough_rank = n_ranked + 1 − rank_std` (1 = gives up the fewest points a game to
  the position this season, this league's scoring); `tough_rank_l4` the same on the last-4 rank. **Tone**: edge =
  round(n × 10 / 32) (10 of 32): `rank_std ≤ edge` → favorable, `rank_std ≥ n + 1 − edge` → difficult, else neutral —
  the same cut as the decision card's reason line (`cards.reason_pieces`: rank ≤ 10 "gives up the Nth-most", ≥ 23
  "the Nth-fewest"), so a card and a cell never disagree. `rank_words`: the nearer end in words ("gives up the
  2nd-most points to running backs" / "the 3rd-fewest").
* **Cornerbacks** (`/api/matchups/cb`, each receiver): `cover_rank` already runs 1 = hardest to throw on.
  **Certainty** from the mart's call: `call_strength = 'clear'` (his located targets lean 15+ points to one side) →
  *likely*; `'even'` → *unclear* (either outside corner, both named); no call (`tight end`, `too few targets`, `no depth
  chart yet`) → *no call*. **Tone** from the named corner's quarter (`quality_label`: shutdown → difficult, solid →
  neutral, target → favorable): on a *likely* call the likely corner's; on an *unclear* call the shared tone only when
  every named corner is ranked and they agree, else neutral (never the stronger of the two); no ranked corner named →
  none ("No read": unknown is not neutral). A corner's rank is said in words ("the 17th-hardest of 74 starting corners
  to throw on", the nearer end) with the certainty beside it; no "shutdown" badge.
* Tests: `api/tests/test_ib3.py` (the cut points, the scaling with n, the words, the corner rules; on both house
  leagues: `tough_rank` 1 = the fewest points allowed, difficult at the small ranks on both routes).

### Current personnel (pers1.0, IF-3, Wave I-F, 2026-10-03; `cards.corner_personnel`, `research.matchup_evidence`)

A defense's rank against receivers was earned by the corners who played its games. When they are not the corners
expected this week, the rank is less representative and must not settle a close call. The **matchup evidence**
(`/api/compare` `a|b.matchup_evidence`, the player card's `matchup_evidence`, `/api/matchups/cb` rows) keeps three
parts apart:

* **History**: the rank the screen shows — Compare and Matchups: this league's scoring (`research.league_dvp`,
  `rank_std`); the card: `mart_defense_vs_position_current` (the reference league's scoring, the card's "Next:" line) —
  with its games, period ("2026, weeks 1–3"), scoring, and **not adjusted for the offenses it faced**; the
  opponent-adjusted rank (`mart_defense_position_profile.rank_adjusted`, reference scoring) beside it.
* **What changed** (receivers only; corners are what the evidence covers):
  * *regulars* = the defense's corners with at least **50% of the leading corner's coverage snaps** this season
    (`mart_cb_rankings`, window `season` — the games played so far, latest, not as-of; at most three);
  * *listed* = its depth chart as of the game: `mart_cb_matchups`' left / right / slot corner (rank 1, the latest
    snapshot before kickoff);
  * *cannot play* = the availability overlay (`availability.now`: ESPN / Sleeper, the newer wins; Out, Doubtful, IR,
    PUP, NFI, suspended, inactive) with its source and date. A listed starter who cannot play gives his spot to the
    next corner at that spot **on the same depth chart** (`mart_matchup_cb_context`, depth rank 2+);
  * *missing* = a regular who is not expected: he cannot play (status, source, date) or the depth chart no longer
    starts him ("no longer listed as a starter"); *expected* = the corners who start, each with his two-season rank
    in words or "unranked (insufficient snaps)", `is_new` when he is not a regular, `replaces` when he took a spot.
  * kind: `changed` (a regular is missing), `same`, `unknown` (no depth chart before the game, or no games this
    season); `not_checked` for QB / RB / TE.
* **Implication**: `less_representative` ("the historical rank is less representative this week: both starting
  corners changed" — the words count them), `stands` ("the same corners"), `unknown`, `unchecked`.
* **Forecast treatment**: **contextual only; not in the forecast.** The projection's opponent inputs
  (`projections.BASE_FEATURES`) are `opp_allowed_std`, `opp_allowed_l4`, `opp_rank_std`, `f_opp_allowed_diff`,
  `league_allowed_avg` (the points this defense has allowed to the position) and the betting lines
  (`implied_team_total`, `spread_line`, `total_line`); the personnel group (`pn_*`) is the player's own team. Nothing
  says who plays corner. `api/tests/test_if3.py` parses the feature list: an opponent-personnel input fails it.

**What it changes.** No number. A receiver whose opponent's corners changed: the card's matchup piece
(`cards.reason_pieces`) stays a fact but scores 0 under its own kind (`matchup_caveat`), so `cards._tiebreak` never
breaks a coin flip on the matchup (either player's) and the coin flip says "the matchup rank does not settle it this
week: Carolina's starting corners changed (Jackson and Horn are on injured reserve)"; the compare's verdict keeps the
projection's head and drops the matchup lean for the same words; `cards.decision_cards`' frame carries
`matchup_uncertain` (My Week's "No clear upgrade" words, IF-4). The console's cards read the depth chart only (no
overlay); the API sets `cards.STATUSES = availability.now`.

**Known limits.** The regulars come from the latest season window (a replay of an old week sees later games); a
corner who changed teams counts for his latest team; the overlay's entry is the status and its date, not the team's
announcement URL (`ops.events`, designed in the IF-3 hand-back, would carry it); one corner of two missing is already
"less representative" (no threshold is invented for "how much").
*Wave I-G (IG-2): the URL now carried.* The event store (`events.events`, `docs/HOSTING.md` § "Events") keeps each
injury-report move with its source URL, so every missing regular with a status carries the stored event:
`changed.missing[].event = {id, kind, source, url, at, status, headline}` and `changed.missing[].url`, with
`changed.events` listing them (`research._cite_missing`: the opponent's live availability events, `events.for_team`,
then the player's own, the last 60 days; the one that says he cannot play, his overlay status first). The URL is the
source's: the player's ESPN page for an ESPN report (ESPN's injuries feed carries no story link); a Sleeper report has
none. The team's own announcement (the Panthers' release) is still not read — no feed of team sites is licensed — so
the citation is ESPN's (or Sleeper's) record of it, dated with the report's time. No event (the store off, empty,
unreachable; a depth-chart change): `event` and `url` are null and the overlay's status, source and date stay. The
words and the numbers do not change.

## "Value to my lineup" (IB-3, Wave I-B, 2026-10-03; `ondemand.lineup_values`, `/api/ros?view=lineup&team=`)

What a player is worth to **one roster's best lineup** over the weeks left (this week to the league's final), summed
week by week on the trade engine's rest-of-season board (`decisions.window_board(ctx, "ros")`: the four-week lineup
horizon, then the rest-of-season per-week projections; byes, the IR slot, NFL injured reserve as there; IB-0's
availability overlay through the board), each week solved with the waiver engine (`waivers.prepare` / `entry_bar` /
`_what_if` on `lineup.solve`'s matching):

* **one of yours**: what the lineup loses without him = total − max(the best lineup without him, the best lineup
  without him plus the best free agent at his position that week) — his edge over the next-best who would take his
  place, bench or waiver wire (a lone kicker is worth his edge over the best free kicker, not his whole projection);
* **anyone else** (free agent or another roster's): what he adds if he were on your roster, nobody dropped (a bench
  spot is assumed): Σ max(0, his value − the entry bar of the slots he can play). A free agent's weeks are his
  rest-of-season projection; Out / Doubtful this week (the overlay) → nothing this week; IR / PUP / suspended → nothing.
* `lineup_points` (≥ 0), `lineup_weeks` (weeks he starts, or would), `lineup_kind` (mine / fa / others), `lineup_why`
  (one sentence). Ranked by `lineup_points`, then `lineup_weeks`, then rest-of-season points. A backup QB in a one-QB
  league is 0 except in his starter's bye week (and 0 then too when a free agent would outscore him).

### Team units and the value rule (IG-1, Wave I-G, 2026-10-04; `decisions.unit_market`, `trades.value_gap`)

* **A team unit's season value** (MyFantasyLeague's team QB / team kicker, TMQB / TMPK): the trade context's market
  (`TradeContext.points` → `trades.market_by_player` / `price_by_player`) had no row for a unit, so the verdict's season
  value, the calculator's warning and the Finder's rule left it out ("Not counted (no season projection): Houston Texans
  QB"). Now: **season points** = Σ over the market's window (this week to the last regular-season week —
  `market_points`' window, the season every player is priced over) of the unit's priced week (`lw.priced[w].units`: IC-4's
  per-week unit rows — the team's best-projected quarterback who can play that week, priced as TMQB; the team's kicker
  for TMPK), each week rounded to the cent; a bye week has no row and adds nothing (a player's bye likewise). **The
  replacement** = the most season points of a **free unit of the same kind** (`anyleague.free_agents` keeps one free unit
  per team), never a player; season value above replacement = max(0, season points − replacement). A unit with no
  priced week has no row (unknown, not 0); no free unit priced → baseline 0 (the players' rule for a position with no
  free agent). On the fixture (MFL 70587 team 8, weeks 4–18): Houston Texans QB 355 season points, the best free team QB
  Arizona Cardinals QB 378 → 0 above; the best free team kicker New Orleans Saints K 169. A unit's season points equal
  its rest-of-season rows (`weeks_json`) summed over the same weeks (`api/tests/test_ig1.py`). House leagues have no
  units: their market is unchanged to the bit.
* **The Finder's rule (a) on value, not volume** (ti1.2): `trades.value_gap` — the season value above replacement you
  give (whole points per player, as the tables sum it) exceeds what comes back by more than 25% of what you give **and**
  the two are not about even (`about_even`: within 10 points or 10% — a warning never contradicts the verdict's "about
  even by season value"); every player of the package needs a value. One rule for the Finder (`partners`' `allow`) and
  the calculator's warning (`calc_sanity`). The raw rest-of-season line stays on the calculator, labelled "all
  positions added up — not a fairness test" (IF-2). What it changes (fixtures / the clone, next four weeks): Scrubs
  roster 6 — 5 cards → 7, 2 left out → 10 (in: Williams → Purdy + Likely, Lamb → Allen + Chase, Williams → Kyler
  Murray, Lamb + Javonte Williams → Taylor; out: Warren → Andrews + Purdy "20 for 3", Lamb → Allen + Golden "69 for
  35"); MFL 70587 team 8 — 15 → 17 cards, the headline unchanged (Chicago Bears QB → Kansas City Chiefs QB + Rice, now
  "0 for 29"); "Chicago Bears QB + Tuten for Coker" (IA-2: "484 rest-of-season points for 141") is suggested (14 for 14);
  Tuten → Wan'Dale Robinson stays out ("14 for 0"). No gain number moved.
* **A side with an unvalued player** has no season-value sum (`decisions.known_value`: the Finder's rows' `price_out` /
  `price_in`, the calculator's other-objective words) — the partial sum of the others is not that side's value.
* **No projection** (AGENTS.md rule 5): the solver carries a player with no projection row at 0 (`value_source =
  'unvalued'`); the API sends `null` + `no_projection` (My Week's lineup and bench, Team's roster, the trade answers'
  lineups / starters in and out / `this_week`, a Waivers drop with no rest-of-season row), My Week's `n_unvalued` (the
  starters the total counts at 0) and `unvalued_words`; the web shows a dash titled "no projection", the console a
  blank with the flag "no projection".

## Role alerts (ra1.1 rule, version ra1.2 since 2026-10-01; plan R-10, 2026-09-30; `league_lab.signals`, `ops.player_role_alerts`, `mart_player_role_alerts`)

**Question.** Has a player's *role* changed in his last one to three games, and why — before his points show it?
A role alert is a detected role change with a stated cause, not a hot streak: a big game on the same snaps and
targets is not one.

**Inputs.** `intermediate.int_player_game_role`: every QB/RB/WR/TE on a team's weekly roster (or who played for it)
× each played regular-season team game, with `status` (played / out_injured / inactive), snap share (0 when he
missed a game that has snap counts), route share (routes proxy over dropbacks with participation — past seasons
only, NULL in-season), target and carry share with the team's totals; the injury report of the next week; last
season's median snap share; nflverse depth charts (2025 on): his best rank at his position in the team's last
snapshot before each game.

**Rule (per player × game W, k = 3, 2, 1 games held).** Window N = his last k games (injury absences skipped, a
healthy scratch counts 0), prior P = up to 8 games before it. A share *changed* when (1) the window level (mean
snap / route share; Σ targets / Σ team targets, carries likewise) is at least STEP above (below) the prior's
**median** (a short fill-in stint inside the prior does not become the baseline) — STEP snaps / routes 0.20 (QB
0.30), target share 0.08, carry share 0.15 — and every window game is past the step while the game before the window
was not; (2) the new level (up) or the old one (down) is a real role: FLOOR snaps / routes 0.45 (QB 0.50), targets
0.12, carries 0.30; (3) z = change / (σ × √(1/k + 1/n_prior)) ≥ 2.0, or ≥ 1.5 with a named reason, σ = the median
within-player game-to-game sd of that share at the position (2016–2025: snaps 0.12–0.17, routes 0.15–0.20, targets
0.055–0.072, carries 0.15). Then: at least one **structural** share (snaps or routes) changed, except an RB's carry
share with a named reason or two games (ra1.1: a target or carry share alone held 32–42% of the time in 2025); one
game alone needs a snap / route change and not a 20+-point blowout, or a named reason; a one-game **drop** needs a
named reason (ra1.1: 32% held without one) and is skipped when he is on next week's report as Out / Doubtful / IR;
a bigger role is never read from a game he missed, nor from his return from injury; an up change whose window
included an injured starter's absence that has already ended (the starter is back for the latest game) is expired,
not news. The alert keeps the longest k with a named reason, else the longest k; after three games the change is
his role (his last-3 inputs have caught up) and it stops being reported.

**Named reasons (`trigger_kind`) and kind.**

| Reason | Detected as | `kind` | `cause_text` |
|---|---|---|---|
| traded | his own team changed between the prior and the window | new_team | "traded to BUF" |
| teammate out, injured / traded / released | a starter of his group (QB; RB; WR+TE; median prior snap share ≥ 0.40 RB, 0.50 others; with < 2 prior games, last season's level) played the last prior game and missed every window game (out_injured, gone, traded_away; a game he barely played (< 10%) counts as injured when he is Out / Doubtful / IR next or misses the next game hurt) | absence_beneficiary | "Zack Moss out injured", "Amari Cooper traded" |
| teammate benched | the same, but inactive while healthy or < 10% of the snaps | depth_move | "Russell Wilson benched" |
| depth-chart move | his rank crossed the starter line (QB/RB/TE 1, WR 3) between the snapshot before the last prior game and the one before the latest game | depth_move | "up to RB1 on the depth chart" |
| a new starter took over (down only, a label) | a teammate below the starter line in the prior starts every window game | depth_move | "&lt;name&gt; took over" |
| teammate back (down) | a teammate missing from the last prior game starts every window game | role_down | "Chuba Hubbard back" |
| none | — | role_up / role_down | "no teammate out, no trade: the coaches changed his role" |

**Evidence, confidence, expiry.** `snap_from → snap_to` (and routes / targets / carries: before = prior median,
after = window level), `change_text`; `games_held` 1–3 ("one game so far" … "three games: this is his role now");
`expires_after_week` = W + 3, `expiry_rule`; an absence beneficiary's alert also ends when the injured teammate is
back: `mart_player_role_alerts.trigger_ended` (active on his NFL roster with no injury designation on the latest
report), and `is_live` = the alert game is his team's latest game and the reason has not ended.

**Validation (`league-lab signals-backtest`, the rule as it runs in season: no routes).** Known cases — the alert
fires in the week of the change with the right cause: Chase Brown (CIN) 2024 wk 9, absence_beneficiary "Zack Moss
out injured", snaps 36% → 80%, carries 49% → 87%; Cedric Tillman (CLE) 2024 wk 7, "Amari Cooper traded", target
share 1% → 25%, snaps 34% → 82%; Drake Maye (NE) 2024 wk 6, depth_move "Jacoby Brissett benched", snaps 0% → 100%;
Jaxson Dart (NYG) 2025 wk 4, depth_move "Russell Wilson benched", 4% → 97%; Rico Dowdle (CAR) 2025 wk 5,
"Chuba Hubbard out injured", snaps 36% → 67%, carries 32% → 72% (no alert in wk 7 when Hubbard was back; a second,
cause-less change from wk 9: "up to RB1 on the depth chart"); TreVeyon Henderson (NE) 2025 wk 9, "Rhamondre
Stevenson out injured", routes 30% → 90%; Amari Cooper (BUF) 2024 wk 7, new_team down, snaps 89% → 35%.
No alert for players who merely had a big week: of the 44 games in 2024–25 where an established (≥ 60% snaps over
his last 3) RB/WR/TE scored ≥ 25 points and ≥ 2.5× his PPG, 43 fired nothing — the one was TreVeyon Henderson's
third game of a real change. The two controls: Ja'Marr Chase 2024 wk 10 (49.9 points) and Kyle Pitts 2025 wk 15
(40.1 on a 7.7 PPG season) — no alert that week, nor any other week of their seasons. DeAndre Hopkins (KC) and Davante Adams (NYJ) after their 2024 trades: no
alert (their role did not change).

**Precision** — first detections (a change is re-reported at two and three games), "real" = the mean of the
primary share over his next three games (games missed injured skipped) kept at least half the change; an absence
alert whose injured teammate was back for the next game is "expired" (it lapsed as designed), not false; an
absence alert only counts the games the teammate still missed:

| Season | Bigger role: real / false (precision) | expired | unresolved | Smaller role: real / false (precision) |
|---|---|---|---|---|
| 2023 | 114 / 37 (75.5%) | 34 | 52 | 73 / 29 (71.6%) |
| 2024 | 123 / 41 (75.0%) | 34 | 49 | 62 / 42 (59.6%) |
| 2025 | 120 / 60 (66.7%) | 29 | 46 | 77 / 43 (64.2%) |

2025 by kind: absence_beneficiary 68%, depth_move 67%, role_up 62%, role_down 65%, new_team 4 of 6. ra1.0 (before
the structural requirement, the 1.5 bar with a reason and the one-game-drop rule) was 57% / 51% on 2025 (measured with routes).

## Scenario upside (sc1.0, plan R-12, 2026-09-30; `ops.player_scenarios`, `mart_player_scenarios`, `ops.waiver_upside`)

**Question.** If a bigger role holds, what does he project — and how much should anyone believe it?

**Scenario.** For every QB/RB/WR/TE with a live bigger-role alert (not lapsed: an injured teammate expected back
ends it), each week from the next unplayed one to `expires_after_week`: the **base** is the stored projection (the
same component models, refitted in `signals.component_models` on the same rows with the same seed; `project` checks
the refit reproduces every stored `proj_points` to 1e-6 and fails the step otherwise). The **larger role** re-predicts
the stat line from the same as-of row with his last-3 opportunity inputs set to the level of the games since the
change — snap share, target / carry / air-yard / first-read share, targets, carries, attempts, red-zone chances and
expected points per game — each capped at the position's 90th percentile of the training player-weeks unless his own
level is already above it; catches, yards and TDs per game scale with the volume at his own last-3 rate (a larger
role, not better hands); `ppg_l3` moves by the priced change of that line. Priced in each league's scoring.
`with_alert_points` = base + hold rate × (larger − base), hold rate = the share of 2016–2022 bigger-role alerts still
real three games later (one game held 69.5%, two 76.4%, three 81.4%).

**Calibration before a probability is shown** (`league-lab signals-backtest --seasons 2023-2025`): every bigger-role
alert of 2023–2025 at QB–TE with a next game (absence alerts whose teammate played that game dropped: lapsed), the
as-of row for his next game re-priced with component models fitted on the seasons before, against his points per
game over his next three games (reference scoring):

| Games held | alerts (scenario moved) | larger role nearer than the projection | "with the alert" nearer | mean miss: projection / larger / with | mean gap (larger − base) | mean (actual − base) |
|---|---|---|---|---|---|---|
| 1 | 285 | 45.6% | 47.0% | 3.34 / 3.37 / 3.31 | +1.04 | +1.12 |
| 2 | 266 | 47.4% | 48.1% | 3.30 / 3.29 / 3.29 | +0.48 | +0.71 |
| 3 | 18 | 72.2% | 72.2% | 2.70 / 2.53 / 2.56 | −0.19 | −0.31 |

**Decision: shipped as a "what if"** (`SCENARIO_SHIP = False`, `presentation = 'what if'`): neither line was the
nearer number more often than not at one or two games held, and the mean miss moved by under 0.04 points. The page
shows the larger role and its hit rate ("tested on 2023–2025: after 285 alerts like this, the next three games landed
nearer it than the projection 46% of the time"), never a chance. What the backtest does say: these players did
outscore their projection on average by about the scenario's gap (+1.12 vs +1.04 a game at one game held) — the
projection under-reacts to a new role on average, but single outcomes are too noisy (and right-skewed) for the
scenario to be the better call for one player. By position the gap was about right for RB, too big for WR (+0.83
gap, +0.17 actual) and too small for QB / TE. A rule or feature change re-runs the backtest before the constants
(`HOLD_RATE`, `BACKTEST`, `SCENARIO_SHIP`) change.

**Upside stash** (B3's `list_kind = 'upside'`, `ops.waiver_upside`): per roster, the free agents with a live
scenario who do not help that roster at their projection today (base horizon gain ≤ 0 — the start-now / cover lists
already carry the rest), valued the B3 way twice over the same horizon — at the projection and "if it holds" (the
scenario's projection for the weeks it covers) — with B3's drop rule (the droppable player whose loss costs the
lineup least over the horizon; ties to the fewest rest-of-season points; none on an open spot); ordered by the gain
if it holds, then the scenario's gain.

## Feature experiments (fx1.0, plan D1, Wave D, 2026-10-01; `league_lab.experiments`, `league-lab experiment`, `ops.feature_experiments`, `mart_feature_experiments`)

The gate for projection v3: a group of new inputs joins `FEATURES` only if it makes v2 better on seasons it
never saw, consistently, per position. Nothing edits `mart_player_week_features` until a group is kept.

**A group** is a table at `(gsis_id, season, week)` grain (one row per `int_player_week_universe` row, regular
season from 2016, columns prefixed by group: `gc_`, `wx_`, `ts_`, every column as-of the week, NULL where
unknown) plus the columns to try. It is registered in a module of `src/league_lab/feature_groups/` as
`GROUPS = {name: {"table": "schema.table", "columns": [...], "positions": [...] (default all), "in_season":
[...] (columns built from this season's games), "label": "plain words", "note": "..."}}`; one module per
family so parallel branches never edit the same lines. Validation (`check_spec`) refuses, with the reason: an
unknown or missing table, missing columns, a column that is already a v2 input or a key, a non-numeric /
non-boolean column, an unknown position, an `in_season` column that is not in `columns`, the name `baseline`.

**The run.** `league-lab experiment <group> [<group> ...] [--seasons 2023-2025] [--leagues id,id]`:
1. the no-peek check (below) on every named group's table — a failure refuses the group before any fit;
2. one frame (`projections.load_frame(..., extra_tables=...)`: the production frame with the groups' columns
   left-joined as floats, row order kept);
3. the **baseline**: `projections.walk_forward` (the loop `backtest-v2` runs, factored out unchanged) with
   `FEATURES`, every position, for each test season N trained on 2016..N-1, scored by `score_predictions`
   in every current league's scoring. Cached in `ops.feature_experiments` (`feature_group = 'baseline'`)
   under `model_version` + `test_seasons` + `data_key` (an md5 of the model version, harness version,
   `FEATURES`, `HGB`, the leagues' scoring and the training frame's row count, played count and points
   sum), so every group compares with the same numbers and a rebuilt mart refits it;
   `league-lab experiment baseline` refits it on demand;
4. the group: the same loop with `FEATURES + columns` on the group's positions;
5. per league × test season × position, the season means of the priced line's weekly scores (scorer
   `v2_points`, what the board ranks by): Spearman, top-N hit rate, MAE, coverage_80, interval width and the
   **interval score** = mean of the pinball losses at 0.1 and 0.9 (points; lower = a sharper range at the
   same honesty; it is 1/20 of the Winkler score of the 80% interval), each next to the baseline's and as
   Δ = group − baseline.

**The decision rule** (`experiments.decide`), per position, paired across test seasons (each season's Δ
averaged over the two leagues first: the season is the unit, the leagues share the component models):
* *helps*: mean ΔSpearman ≥ +0.005 **and** ΔSpearman > 0 in at least ⌈2n/3⌉ of the n test seasons (2 of 3),
  **or** mean ΔMAE ≤ −0.05 points with ΔMAE < 0 in at least ⌈2n/3⌉ seasons;
* *hurts*: the mirror image (mean ΔSpearman ≤ −0.005 and worse in ⌈2n/3⌉, or mean ΔMAE ≥ +0.05 and worse
  in ⌈2n/3⌉);
* position decision: **keep** = helps and not hurts; **mixed** = both (better order with a bigger miss, or
  the reverse); **drop** = otherwise — no consistent gain is a drop (inputs cost fit time and drift risk);
* group verdict: **keep** = helps at least one position and hurts none; **mixed** = helps one position and
  hurts another (the PO decides per position); **drop** = helps none.
The interval score and coverage are reported (Δ) but do not decide: v2's intervals are conformally widened,
so coverage stays near 80% whatever the inputs; a sharper range shows up as a lower interval score and width.

**The no-peek check** (`experiments.no_peek_check`), the harness's generic version of
`dbt/tests/assert_features_never_peek.sql`, run on the group's table before fitting. Refused:
1. *grain*: duplicate `(gsis_id, season, week)` keys;
2. *universe*: rows that are not player-weeks of `int_player_week_universe` (a join error);
3. *as-of marker* (the dbt test's first clause): any column named `*asof_week` must be < `week`;
4. *week 1* (its second clause): the group's `in_season` columns must be NULL in week 1;
5. *outcome probe* (for tables without an as-of marker, which is most of them): per position and column,
   on played player-weeks with a played week before and after in the same season, the correlation of the
   input with this week's points (reference scoring) against its correlations with the previous and the
   next played week's points. An input known before kickoff tracks this week barely more than its
   neighbours (on the 72 production inputs the largest excess is 0.047: the opponent's points allowed,
   QB); one built from the game itself jumps (the game's own targets, carries, yards: 0.11–0.52; the week's
   points: 0.52–0.66). Refused when |r_same| − max(|r_prev|, |r_next|) ≥ 0.10 on ≥ 500 rows.
Warned, recorded in `no_peek_warnings`, not refused:
6. *coverage*: universe player-weeks the table lacks;
7. *serve gap*: on the newest season, a column known on ≥ 50% of the played rows but on none of the rows of
   the first week nobody has played yet is only known after the game (observed weather): training sees
   something the live board cannot.
A planted leak (the week's own points as an input) fails check 5 at every position (r = 1.00 vs 0.34–0.48)
and triggers warning 7; a planted `*_asof_week = week` fails check 3; an `in_season` column filled in week 1
fails check 4 (`tests/test_experiments.py::test_no_peek_check_catches_planted_leaks`).

**Outputs.** `ops.feature_experiments`: one row per run × group × position × league × test season (`n_weeks`,
`n_player_weeks`, the six metrics, `baseline_*`, `delta_*`, `decision`, `group_verdict`, `runtime_s`,
`no_peek_warnings`, `data_key`). A rerun of a group replaces its rows for the same model version, test seasons
and leagues. `mart_feature_experiments` (view): per group × position from each group's latest run, the
league-averaged season deltas averaged over seasons, `seasons_better_spearman` / `seasons_better_mae`, the
decision and the verdict. Rankings → "The model" → "What we tried" shows it in plain words.

Runtime: the walk-forward refits every position for each test season (components, out-of-fold lines,
3 quantile models per league); with `OMP_NUM_THREADS=1` a group of 2023–2025 is measured in STATUS
§ "Wave D (Iteration 12)". Several groups in one call share the frame and the baseline.

### Wave E groups (plan E4, 2026-10-01; `feature_groups/rookie_prior.py`, `oline_quality.py`, `qb_x_offense.py`, `player_prior.py`)

Andrew's questions behind them: "are you treating everything equal? an elite QB going down on an elite offense vs a
bad QB on a bad offense; a really good lineman vs a replacement-level one" and "what else could make this better".
Four candidate groups against v3.0 (the baseline is the production model per position; a group adds its columns to
every position's inputs). Nothing in production reads them. Tables at the projection's grain, one row per
`int_player_week_universe` row (`assert_e4_feature_groups_cover_universe`); docs and tests in
`dbt/models/intermediate/features/int_e4_feature_groups.yml`; Python twins in the modules
(`tests/test_e4_feature_groups.py` pins them on fixtures and reproduces every 2025 row on its own path).

| Group (table) | Column | Definition |
|---|---|---|
| `rookie_prior` (`int_e4_player_week_rookie_prior`; static within a season, known before it) | `rk_draft_round`, `rk_draft_pick` | round 1–7 and overall pick (`raw.nfl_players`); NULL for an undrafted player |
| | `rk_draft_tier` | 3 = 1st round, 2 = day 2 (rounds 2–3), 1 = day 3 (rounds 4–7), 0 = undrafted; NULL = not in the players table |
| | `rk_undrafted` | 1 = in the players table without a draft round |
| | `rk_years_in`, `rk_is_rookie` | season − entry season (draft year; an undrafted player's rookie season), floored at 0; rookie = 0 |
| | `rk_age` | age on September 1 of the season, (Sep 1 − birth date) / 365.25, one decimal |
| `rookie_prior_early` (same table; a follow-up, see the verdicts) | `rk_early_*` | the same seven columns in weeks 1–4 only, NULL from week 5 on (the prior while his season has little history) |
| `oline_quality` (`int_e4_player_week_oline_quality`; helper `int_e4_ol_starter_week`; in-season: NULL exactly where D5's `pn_ol_starters_out` is — week 1, report not out) | `pn_olq_starters_out`, `pn_olq_snap_share_out` | copies of D5's `pn_ol_starters_out` / `pn_ol_snap_share_out` (the five starters = most offensive snaps over the team's last four played games; out = Out / Doubtful / reserve) |
| | `pn_olq_career_starts_out` | sum over the out starters of their games before the week (any team, 2016 on) with ≥ 50% of the offensive snaps |
| | `pn_olq_draft_capital_out` | sum of their draft score: 1st round 3, day 2 2, day 3 1, undrafted 0 |
| | `pn_olq_best_out` | the quality rank of the best starter out among the five by last season's snaps (1 = the line's most-used lineman last season … 5); 0 = nobody out |
| | `pn_olq_prev_season_share_out` | sum of their last-season snaps in season-equivalents: Σ per-game snap share over season S−1 / games per team that season (16 / 17); 0 = no snaps (a rookie) |
| `qb_x_offense` (`int_e4_player_week_qb_x_offense`; the harness joins one table per group, so the products are materialized) | `qbx_gap_x_implied` | `pn_qb_prev_ppg_diff` (D5: points per start of the projected starter − the usual QB's) × `implied_team_total` |
| | `qbx_gap_x_total` | the gap × `total_line` |
| | `qbx_gap_x_prev_ppg` | the gap × the team's points per game over its previous regular season (`dim_game` final scores — `fct_team_game` has no points; one code per franchise; NULL in 2016) |
| | `qbx_backup_x_implied` | `pn_qb_is_rookie_or_backup` (< 8 career starts) × `implied_team_total` |
| | `qbx_gap_x_prev_epa` | the gap × the team's EPA per play over its previous regular season (`fct_team_game`: (`passing_epa` + `rushing_epa`) / (attempts + sacks + carries); NULL in 2016) |
| | `qbx_gap_bucket` | the gap in four steps: 2 = big drop (≤ −6 points per start: a good starter replaced by a much worse one), 1 = some drop (−6, −2], 0 = like for like (−2, +2): the usual QB or a backup for a backup, −1 = upgrade (≥ +2); NULL = no gap known |
| `player_prior` (`ops.player_prior_oof`, built in Python: see below) | `pp_resid_ewm` | his running out-of-fold residual: exponentially weighted mean (half-life 8 games: weight 0.5^(k/8) for his k-th newest game, across seasons) of (actual − projected points, reference scoring) over his games with (season, week) < (S, W); NULL before his first scored game |
| | `pp_resid_games` | how many such games (0 = none) |

**player_prior — out of fold, as of the week.** The projection for a season-S game comes from the production model
trained only on seasons < S (`player_prior.component_walk_forward`: the component models of `fit_position` — same
training filter, inputs per position, hyper-parameters and frame order — for S = 2017 … 2026; the interval models are
not fitted, they do not move the point projection). Those projections are exactly the harness baseline's: scored
like the harness on 2023–2025 they reproduce its cached baseline's Spearman, MAE and hit rate to 0.00e+00 in all 24
league × season × position cells. The feature for (player, S, W) reads only residuals of his games before (S, W); in
the walk-forward for test season N a training row (season < N) uses residuals from models trained before its own
season, a test row residuals of season-N games before its week from the model trained on seasons < N (the fold's own
baseline). 2016 has no residuals (nothing earlier to train on). `pp_asof_week` (the week of the newest game used when
it is this season's) is < week on every row (the harness's check 3).

**The harness hook.** `player_prior`'s spec carries `"build": player_prior.build`: `experiments.get_group` calls it
before reading the table, and it refits only when `ops.player_prior_oof` is missing or its `data_key` (model version,
inputs per position, hyper-parameters, half-life, the leagues' scoring, the frame's rows / played / points) changed.
A build is 10 season-folds × 4 positions of component models: 395 CPU-s (672 s wall on the shared box). It also keeps
the per-row out-of-fold projections in `ops.player_prior_oof_pred` (99,272 rows, both leagues' scoring), which is
what a week subset of any group is scored against without refitting the baseline.

**Weeks 1–4.** The harness keeps season means only (`summarize_scores`; the cached baseline has no weekly rows), so a
week subset is scored from per-row point projections: the baseline's from `ops.player_prior_oof_pred`, the group's
from `component_walk_forward` with its columns (`scripts/e4/week_subsets.py`), each week scored exactly as
`score_predictions` does (played rows with every component known, weeks with ≥ 8 players), then averaged like the
harness. Spearman / MAE / hit rate only (they depend on the point projection alone); the interval scores need the
interval models.

**Verdicts** (harness 2023–2025, both leagues, each season's Δ averaged over the leagues; "better" = seasons of 3;
runtime with `OMP_NUM_THREADS=1` on the shared two-core box). Every group **drops** at every position:

| Group | QB ΔSpearman / ΔMAE | RB | WR | TE | Fit |
|---|---|---|---|---|---|
| `rookie_prior` (7) | −0.0091 (0/3) / +0.049 (0/3) | +0.0015 (2/3) / +0.003 (1/3) | +0.0013 (3/3) / −0.009 (2/3) | +0.0046 (3/3) / +0.010 (1/3) | 793 s |
| `rookie_prior_early` (7) | −0.0008 (1/3) / +0.015 (1/3) | +0.0011 (2/3) / −0.009 (2/3) | +0.0016 (3/3) / −0.013 (3/3) | +0.0019 (3/3) / +0.001 (1/3) | 602 s |
| `oline_quality` (6) | −0.0047 (0/3) / +0.035 (0/3) | −0.0004 (1/3) / −0.008 (3/3) | +0.0001 (2/3) / −0.015 (2/3) | −0.0018 (0/3) / −0.002 (1/3) | 652 s |
| `qb_x_offense` (6) | −0.0052 (1/3) / +0.032 (0/3) | −0.0004 (1/3) / −0.005 (1/3) | +0.0003 (2/3) / −0.013 (2/3) | −0.0031 (0/3) / +0.000 (2/3) | 529 s |
| `player_prior` (2) | −0.0019 (2/3) / +0.009 (1/3) | +0.0005 (2/3) / −0.000 (2/3) | +0.0017 (3/3) / −0.017 (2/3) | −0.0047 (1/3) / +0.011 (1/3) | 552 s (+ the table: 395 CPU-s once) |

No-peek: every group passes (no failure); the largest outcome-probe excess is 0.0075 (`pn_olq_best_out`, QB), then
0.0067 (`qbx_gap_x_implied`, RB); `pp_resid_ewm` / `pp_resid_games` stay below −0.0015 (they track the previous week as
much as this one); `pp_asof_week` < week on all 109,123 rows. `oline_quality` carries the same *serve gap* warning as
D5's `oline` / `personnel` (known on 52% of 2026's played rows, none of week 4's): the week-4 injury report is not in
the clone yet — the report is published before kickoff, so this is data timing, not a leak.

**Weeks 1–4** (`scripts/e4/week_subsets.py`, same scorer; the baseline from `ops.player_prior_oof_pred` reproduces the
harness's cached baseline to 0.00e+00 in all 24 cells, and the group's "all weeks" rows reproduce the harness's
group deltas). ΔSpearman (seasons better) / ΔMAE:

| Group, weeks 1–4 | QB | RB | WR | TE |
|---|---|---|---|---|
| `rookie_prior` | −0.0178 (1/3) / +0.049 | **+0.0067 (3/3)** / −0.003 | **+0.0054 (3/3)** / −0.020 (3/3) | +0.0038 (2/3) / +0.027 |
| `rookie_prior_early` | −0.0074 (1/3) / +0.019 | **+0.0079 (3/3)** / −0.003 | **+0.0078 (3/3)** / −0.006 (3/3) | +0.0047 (2/3) / +0.018 |
| `player_prior` | −0.0020 (2/3) / −0.046 | +0.0005 (2/3) / −0.009 | +0.0017 (3/3) / −0.015 | −0.0040 (1/3) / +0.010 |

Draft capital orders RBs and WRs better in weeks 1–4 (+0.005 to +0.008, every season, both variants) — over the
season that is +0.001–0.002, under the bar. It does not help rookies themselves: their weeks 1–4 MAE, pooled
(QB 78, RB 328, WR 500, TE 184 player-weeks), is unchanged or worse (`rookie_prior` QB 5.80 → 6.05, RB 4.41 → 4.42,
WR 4.29 → 4.27, TE 3.08 → 3.09; `_early` worse at every position) — v3's `pos_prev_ppg` and the Vegas line already
carry a rookie's expected role; draft capital mostly separates the second- and third-year players.

**player_prior as a correction, not an input** (`scripts/e4/player_prior_correction.py`). A player's past misses do
predict his next one — corr(`pp_resid_ewm`, this week's miss) = 0.12 QB, 0.11 RB, 0.07 WR, 0.09 TE on 2019–2025
rows with ≥ 8 earlier games — but as a tree input the signal is lost (the drop above). Applied linearly,
proj' = proj + k × `pp_resid_ewm`, k per position fitted on seasons < S only (k ≈ 0.46 QB, 0.34 RB, 0.23 WR, 0.25 TE),
point projection only: ΔMAE RB **−0.054 (3/3)**, WR −0.040 (3/3), TE −0.014 (3/3), QB +0.007 (2/3); ΔSpearman
+0.000 to +0.002. The control — the position's mean miss added as a constant — makes MAE worse (+0.03 to +0.12), so
the gain is the player, not a bias fix. Not a harness verdict (the harness tests inputs; the ranges were not refit):
a candidate for a v3.1 test, see STATUS § Wave E, E4.

**Andrew's two questions, from the out-of-fold projections** (v3.0 trained on seasons < S, 2019–2025, reference
scoring, miss = actual − projected, ± one standard error):
* *An elite QB lost on an elite offense vs a bad QB lost on a bad one.* RB / WR / TE teammates of a QB who is ≥ 6
  points per start worse than the usual one: −0.73 ± 0.28 on a top-third offense (last season's points), −0.43 ± 0.27
  middle, −0.29 ± 0.28 bottom third; with the usual QB −0.01 … +0.08 (28,000 rows). The model does lower them (it
  sees the teammates' own recent games, the Vegas total), but not quite enough, and more so on a good offense — about
  0.4–0.7 points a week on ~6% of player-weeks; at QB itself the misses do not depend on the drop. The explicit
  interactions (`qb_x_offense`) did not fix it in the walk-forward.
* *A Pro Bowl tackle vs a backup guard.* The model's misses do not depend on which lineman is out: QB +0.29 ± 0.31
  with one of the line's two most-used linemen out vs +0.36 ± 0.13 with nobody out; WR / TE −0.04 either way; RB
  −0.21 ± 0.17 vs +0.10 ± 0.07 (the only hint, 0.3 points). The proxy sees snaps, starts, draft slot and years —
  not PFF grades, pass-block win rates or contracts; a good lineman by those measures being out barely moves
  fantasy points, and the model is not systematically wrong about it.

## Team volume and style (team_style v1.0, plan D4, Wave D, 2026-10-01; feature group `team_style`)

Andrew asked about "team stats, defensively, time of possession, number of first downs". Projection v2 prices a
player's opportunity through his own shares and his team's Vegas implied total; it does not know how many plays
his offense runs, how fast, how often it throws, or what the opponent's defense forces. This group adds those,
as of the week, for the harness to judge (D1). Tables: `int_team_game_style` (team × game facts) →
`int_team_week_style` (team × week, as of) → `int_player_week_team_style` (the group's table at the projection's
grain). Python twins of the rules: `league_lab.feature_groups.team_style` (`tests/test_team_style.py`).

**Per game** (`int_team_game_style`, one row per offense × game, regular season and postseason, 2016+; additive
counts so any window pools sums over sums):

| Fact | Definition | Source |
|---|---|---|
| play | a dropback (pass attempt, sack, scramble) or a designed run; kneels, spikes, two-point tries and penalty-nullified snaps are not plays | `fct_play` flags |
| neutral | 1st or 2nd down, quarters 1–3, the offense's pre-play score within 7 points either way | `fct_play` |
| neutral pass rate | neutral dropbacks / neutral plays | `fct_play` |
| PROE (pass rate over expected) | (dropbacks − Σ xpass) / plays with xpass, every play. xpass = nflfastR's pre-snap probability of a dropback (down, distance, field position, clock, score, timeouts, win probability), one fixed model for every team, so the expectation is "an average team in this exact situation". League mean is −1 to −2.5% since 2017 (teams run more than the model's training years did): compare teams within a season | `fct_play.xpass` |
| pace (seconds per play) | game-clock seconds from a real snap (play, punt, field goal; not a nullified one) to the offense's next real snap on the same drive, from snaps in quarters 1–3 with the score within 7 (any down); lower = faster. Game clock, so an incompletion's stopped clock is not counted | `fct_play.game_seconds_remaining` |
| time of possession | the game clock from each play-by-play row to the next one in the same half, credited to that row's offense (a row without one — a timeout, stamped with the previous snap's time since 2022 — to the last offense before it); a kickoff return goes to the receiving team, a punt to the punting team, as the official stat does within a second or two | `fct_play` |
| drive | a run of rows with the same nflfastR `fixed_drive` and offense containing at least one play (kneel-only, spike-only and return-only possessions are not drives) | `fct_play` |
| drive points / scoring drive | the offense's score at the start of the next possession (or the final score, `dim_game`) minus its score at the drive's start: touchdowns, the try, field goals; a defensive or return score never counts for the offense. Scoring drive = drive points > 0 | `fct_play` pre-play scores |
| red-zone trip | a drive with a real snap at the opponent's 20 or closer | `fct_play` |
| first downs | passing + rushing first downs (penalty first downs excluded) | nflverse team stats (`fct_team_game`) |
| giveaways | interceptions thrown + fumbles lost | nflverse team stats |
| clock glitches | a row-to-row clock gap outside 0–75 s is a mislabelled quarter or a missing row in the source (`2020_01_LV_CAR` has Q2 clock times inside Q1): capped at 0 / 75 s for time of possession, left out of pace (0.2% of gaps; real snap-to-snap gaps are under a minute). After the cap 2,332 of 2,637 regulation games sum to 60:00 ± 15 s of possession, 138 differ by more than a minute | |

**Per week, as of** (`int_team_week_style`, team × season × regular-season week, byes and unplayed weeks
included). For the **offense** (`off_`) and the **defense** (`def_`: the same quantity over the offenses it
faced — plays faced, pace faced, pass rate faced, first downs allowed, sacks made per opponent dropback,
opponent giveaways = takeaways, points per drive allowed …), twelve metrics:

| Metric | Formula over the window's games |
|---|---|
| `plays_pg` | plays / games |
| `sec_per_play` | pace seconds / pace snaps |
| `neutral_pass_rate` | neutral dropbacks / neutral plays |
| `proe` | (dropbacks − Σ xpass) / plays with xpass |
| `first_downs_pg` | first downs / games with a team-stats row |
| `top_min_pg` | time of possession (minutes) / games |
| `red_zone_trips_pg` | red-zone trips / games |
| `points_per_drive` | drive points / drives |
| `scoring_drive_rate` | scoring drives / drives |
| `yards_per_play` | yards on plays (sacks negative) / plays |
| `sacks_per_dropback` | sacks / dropbacks (defense: sacks made per opponent dropback) |
| `giveaways_pg` | giveaways / games with a team-stats row (defense: takeaways) |

Windows: `_std` = the team's regular-season games of the season **before the week**; `_l4` = the last four of
those (fewer early on); `_prev` = the team's full previous regular season (the league's when the team has none).
Playoff games never count. **Shrinkage** (dbt macro `ts_shrink`, the 3-game weight `mart_defense_position_profile`
uses for an offense's last season): value = (n × window + 3 × prev) / (n + 3), n = the team's games this season
before the week, **for both windows** — the in-season weight grows with the season, not with the window: week 1
is last season; week 2 = ¼ this season; week 7 after 6 games = ⅔; week 10 after 9 games = ¾. No prior (2016, the
first season loaded): the window's own value (NULL in week 1); a window value with no denominator falls back to
the prior. `off_asof_week` / `def_asof_week` = the newest game week used (< week).

**Per player-week** (`int_player_week_team_style`, the group's table): one row per `int_player_week_universe` row;
`ts_off_<metric>_<std|l4>` = his offense this week (the universe's team), `ts_def_<metric>_<std|l4>` = this week's
opponent defense, `ts_off_games` / `ts_def_games` (n), `ts_off_asof_week` / `ts_def_asof_week` (the harness's
as-of marker), and two matchup inputs:
* `ts_pace_product` = `ts_off_plays_pg_std` × `ts_def_plays_pg_std` / the league's plays per game (mean of the 32
  teams' `off_plays_pg_std` that week): the expected play count of this matchup;
* `ts_pass_env` = `ts_off_neutral_pass_rate_std` × `ts_def_neutral_pass_rate_std` / the league's neutral pass rate
  that week: the matchup's expected neutral pass rate (log5-style; the plan's "offense × defense", divided by the
  league so it reads as a rate).
Team codes: one per franchise (`kd_team`: OAK → LV, SD → LAC, STL → LA), as play-by-play and the team stats use.

**League sanity, 2025 regular season** (pooled over every team-game): plays per game 60.3; neutral pass rate
53.2% (2023 54.2%, 2024 53.5%; the same filter on **all** downs is 58.5%: third downs are 80% passes); PROE −2.2%;
seconds per play 31.8; time of possession 30.2 minutes per team-game (overtime included; 30:00 by construction in
regulation); drives 10.1 per game; points per drive 2.17; scoring-drive share 40.8%; red-zone trips 3.26; first
downs 17.5; yards per play 5.43; sacks per dropback 6.5%; giveaways 1.16.

**What the market already knows.** On 4,766 team-games (2017–2025), the efficiency numbers track the Vegas
implied total closely (r = 0.60–0.67 for points per drive, yards per play, first downs, red-zone trips, scoring
drives, season to date) and add nothing to the drive points the team then scored once the implied total and the
game total are partialled out (partial r −0.01 to +0.02). Volume and pass rate are what the lines do not carry:
`ts_pace_product` r = 0.25 with the implied total, partial r = +0.115 with the plays the offense then ran
(seconds per play −0.118); `ts_off_proe_std` r = 0.26 with the implied total, partial r = +0.25 with the game's
dropback share (`ts_pass_env` +0.21, the opponent's PROE faced +0.09); the implied total itself correlates −0.03
with the dropback share. Script: `scratchpad/waveD/d4/market_corr.py`.

**Harness result** (D1's walk-forward, test seasons 2023–2025, both leagues; the table is in STATUS § "Wave D
(Iteration 12)" → D4): every group drops at RB, WR and TE (|ΔSpearman| ≤ 0.006, ΔMAE −0.004 to +0.032). The only
keep by the rule is `team_style_pass_rate` at QB (ΔSpearman +0.0096, better in 3 of 3; ΔMAE −0.014; interval score
−0.009), and it does not hold on 2021–2022 (−0.005 each): over five seasons +0.0037, better in 3 of 5. v2 already
sees each player's attempts / targets / carries per game, which carry his team's volume and pass rate; the team
numbers add little on top. Recommendation: drop for v3 (PO's decision).
## Game context (gc_, plan D2, Wave D, 2026-10-01; `int_player_week_game_context`, feature groups `game_context` / `rest` / `time` / `venue`)

A candidate for v3, evaluated by the harness above; not a v2 input. One row per `int_player_week_universe`
row (109,123: every rostered QB/RB/WR/TE × regular-season week his team plays, 2016–2026), every column from
the **published schedule** (`raw.nfl_schedules` → `stg_nflverse__games`), so it is known for future weeks
exactly as for past ones (`assert_game_context_known_before_kickoff`: every not-yet-played game has every
column whose schedule source is filled; the harness's outcome probe: largest excess 0.019, limit 0.10).

| Column | Definition | Known |
|---|---|---|
| `gc_weekday` | days from the week's Sunday — an **ordinal**, not one-hot (HGB splits it where it matters): Thu −3, Fri −2, Sat −1, Sun 0, Mon +1, Tue +2 (2020 reschedules), a Christmas Wednesday before the Sunday −4. From the game date and the date of the week's Sunday games | schedule |
| `gc_kickoff_hour_et` | `gametime` (nflverse: US Eastern) as hours, minutes as a fraction: 13.0, 16.42 (4:25), 20.33 (8:20), 9.5 (London) | schedule; a flexed game carries its flexed time (nflverse rewrites the schedule when the league flexes: 12+ days ahead, 6 for week 18); NULL gametime → NULL (never assumed 13:00; none in 2016–2026) |
| `gc_primetime` | kickoff ≥ 20:00 ET | as above |
| `gc_early_window` | kickoff 12:00–13:59 ET (the Sunday 1 pm games, Thanksgiving 12:30) | as above |
| `gc_rest_days` | days since the team's previous regular-season game this season, from the game dates; NULL in week 1 (and for 2017 MIA / TB in week 2, whose opener was postponed). nflverse's `home_rest` / `away_rest` agree on 101,768 of 102,476 week-2+ rows; the 675 that differ are late-season Saturday games (2019 week 16: BUF at NE on Saturday after a Sunday game is 6 days, nflverse says 7) and the 2021 COVID reschedules, where the dates are right. nflverse's week-1 value (7) is a placeholder | schedule |
| `gc_short_week` | rest ≤ 4 days | schedule |
| `gc_off_bye` | the team's previous game was ≥ 2 weeks earlier; NULL in week 1 | schedule |
| `gc_opp_rest_days`, `gc_rest_edge` | the opponent's rest; his team's rest − the opponent's | schedule |
| `gc_travel_tz` | time zones crossed from the team's home stadium to the venue, west → east positive (SEA at NYG +3, NYG at SEA −3, home 0, a Pacific team in Munich +9, the Rams in Melbourne −7: wrapped to the short way). A stadium → zone map in the model (every `stadium_id` since 2016; Arizona counted as Mountain; international venues at their in-season offset; an unknown stadium falls back to the home team's zone) | schedule |
| `gc_west_coast_early` | a Pacific-zone team (LA, LAC, LV/OAK, SD, SF, SEA) kicking off before 14:00 ET (the 1 pm body-clock game; London mornings included) | schedule |
| `gc_roof` | 1 = fixed dome, 0 = open air, **NULL = retractable**: whether the roof is open or closed is decided on game day (nflverse fills `open` / `closed` after the game and leaves future games empty), so training never sees the call either | stadium |
| `gc_surface_turf` | artificial turf (fieldturf, matrixturf, a_turf, sportturf, astroturf) vs grass; NULL when blank | stadium |
| `gc_div_game` | division game | schedule |
| `gc_neutral_site` | `location = 'Neutral'` (international and relocated games) | schedule |

Shares over the 109,123 rows: primetime 19.9%, 1 pm window 52.0%, short week 6.4%, off a bye 6.4%, west-coast
team at 1 pm 3.6%, fixed dome 18.5% (retractable NULL 15.4%), turf 43.3%, division game 36.5%, neutral site 1.9%.
Sub-groups for the harness: `time` = weekday, kickoff hour, primetime, 1 pm window, time zones crossed, west-coast
early (when the game is and the body clock); `rest` = the five rest columns; `venue` = roof, turf, division,
neutral site. Results (2026-10-01, harness fx1.0, test seasons 2023–2025, both leagues): **drop** for every group
and position: no mean ΔSpearman beyond ±0.004, no mean ΔMAE beyond ±0.02 points, interval score flat. The Vegas
lines v2 already uses price the game context. Table: STATUS § "Wave D (Iteration 12)" / D2; Rankings → "What we tried".

## Personnel (pn_, plan D5, Wave D round 2, 2026-10-01; `int_player_week_personnel`, feature groups `personnel` / `qb` / `oline` / `teammates` / `own_injury`)

Andrew: "certain injuries might make an impact … quarterback, that's a big one, but offensive line injuries". Round 1
found that game context, weather and team style add nothing beyond the betting lines; personnel is the family with a
mechanism the lines may not carry **at the player level**: a receiver's history was built with one quarterback and the
board prices him with another; a back runs behind a line missing two starters; the top target is out and the shares
move; a backup quarterback is projected from his own thin history. A candidate for v3, evaluated by the harness
(§ "Feature experiments"); not a v2 input. Tables: `int_pn_team_game` → `int_pn_player_game` (what each QB / RB / WR /
TE / lineman did in each played game) → `int_pn_player_week_status` (availability for week W) → `int_pn_window_player`
(the team's last four games before W, per player) → `int_player_week_personnel` (one row per `int_player_week_universe`
row). One code per franchise (`kd_team`). Python twins of the two hard-coded rules: `league_lab.feature_groups.personnel`.

**What "as of the week" means here.** History: only the team's / player's **played** regular-season games with
week < W. Availability: week W's **injury report** — nflverse `injuries`, one row per player-week: the team's final
game-status report of the week (Friday for a Sunday game, Wednesday or Thursday for a Thursday game); where nflverse
stamps `date_modified` (2016–2024) its median is 47–55 hours before kickoff, 24 of ≈ 52,000 rows were modified after
kickoff (13 of them 2020 reschedules); 2025–26 carry no stamp — plus the **weekly roster's reserve lists** (RES =
injured reserve / PUP / NFI, PUP, SUS, EXE, NON: placed before the roster deadline; 0 RES player-weeks 2017–2025 have
snaps in that week's game, 17 in 2016). The roster's ACT vs INA split is **never** read: INA is the game-day inactive
list (0 of 7,204 INA player-weeks 2022–25 played, 94% of ACT did), announced 90 minutes before kickoff. A team whose
week-W report has no row yet (an upcoming week) gets NULL report-based inputs: unpublished is unknown, not "nobody hurt".
The quarterback: the schedule's `home_qb_id` / `away_qb_id` (see the train / serve gap below).

| Column | Definition |
|---|---|
| `pn_qb_changed` | 1 = this week's projected starter (`proj_qb_id`) is not the QB his history was built with (`usual_qb_id`: the schedule's starting QB in the majority of his newest **four** played games, this season before the week or last season; ties → the more recent). NULL when either is unknown. A receiver traded in the offseason is "changed" until most of his last four games are with the new QB |
| `pn_qb_games_together` | games (2016 on, before the week) in which he and the projected starter both played ≥ 50% of the team's offensive snaps (a QB's own row: his games with ≥ 50%) |
| `pn_qb_prev_ppg_diff` | points per start (reference scoring) of the projected starter minus the usual QB's, each over his newest **17 starts of the last two seasons and this one** before the week (not "last season" alone: a backup's last start is often two seasons back; the brief left the choice). 0 for the same QB; NULL when either has no start in that span |
| `pn_qb_is_rookie_or_backup` | the projected starter has < 8 career starts before the week (counted from 2016: overstated in 2016–17, 61% / 20% of rows) |
| `pn_qb_starting` | QB rows: 1 = he is the projected starter, 0 = another QB is; NULL for RB / WR / TE |
| `pn_ol_starters_out` | of the team's five line starters — the five linemen with the most offensive snaps over the team's last four played games — how many are Out or Doubtful on week W's report or on a reserve list. NULL in week 1 and when the report is not out |
| `pn_ol_snap_share_out` | their combined snap share over those games (≈ 1 per full-time starter) |
| `pn_ol_games_since_change` | consecutive games through the team's last one that the same five linemen led it in snaps (1 = the five changed last game) |
| `pn_top_target_out` | 1 = the teammate (RB / WR / TE, **not him**) with the largest target share over the team's last four games is out this week (Out / Doubtful / reserve) or gone from the roster (released, traded — the C6 absence logic's "traded" / "gone"). For the top target himself it is about the second one |
| `pn_top_rusher_out` | the same for the largest carry share (QB included) |
| `pn_teammate_share_out` | the summed target share of the RB / WR / TE teammates out or gone this week (his own excluded) |
| `pn_absence_beneficiary` | 1 = an `absence_beneficiary` role alert (C6, `ops.player_role_alerts`) at his team's last game and the absent teammate is still out this week. NULL for team-seasons the alerts do not cover (the Raiders 2016–19 and the Chargers 2016: `int_player_game_role` joins `dim_game`'s OAK / SD to `fct_team_game`'s LV / LAC and loses them — a C6 defect for the PO) |
| `pn_games_missed_season` / `_prev` | team-games he missed injured (did not play and was Out / Doubtful / Questionable that week or on a reserve list — the C6 rule) this season before the week / last season (NULL with no team-game last season) |
| `pn_q_streak` | consecutive weeks (his team's game weeks) Questionable through this week's report; 0 when not Questionable |
| `pn_returning` | 1 = he missed his last two or more team-games injured (across seasons) and is not Out / Doubtful / reserve this week |
| `pn_report_status_ord` | 3 Out or reserve, 2 Doubtful, 1 Questionable, 0 not listed (v2 already has `questionable`) |
| `pn_practice_ord` | the report's practice participation: 2 did not participate, 1 limited, 0 full or not listed (added to the brief's list: a Questionable player who did not practise is a different case) |

In-season columns (NULL in week 1, the harness's check 4): the `oline` and `teammates` ones. `pn_asof_week` (the newest
game of this season any input read) is < week on every row (check 3).

**Evidence.** `dbt build --select int_pn_team_game+ int_pn_player_week_status+`: 5 models + 22 tests, PASS=27, 78 s on a quiet box (the feature table 57 s) (grain, ranges, as-of, week 1, QB flags agree,
`assert_personnel_is_asof`: universe row for row, the projected starter = the raw schedule's, the usual QB comes from a
game he played before the week, career starts re-counted on the raw schedule; `assert_personnel_ol_count_from_raw`: the
OL count re-derived on its own path from raw snap counts, injuries and weekly rosters for every team-week 2016–2026, 0
differences). Negative control: a window that includes the week's own game fails `pn_window_is_asof` on 113,684 rows and
changes the OL count on 631 of 5,018 team-weeks. The twins reproduce the table on every 2025 row (`tests/test_personnel.py`).
The harness's no-peek check passes all five groups (0 refusals; largest probe excess 0.040, `pn_top_rusher_out` at RB,
limit 0.10).

Hand checks. **QB change, 2025** (schedule `home_qb_id` / `away_qb_id`): CIN week 3 (Burrow hurt in week 2 → Browning),
NYG week 4 (Wilson benched → Dart), ARI week 6 (Murray hurt → Brissett): every Bengals / Giants / Cardinals RB / WR / TE
row has `pn_qb_changed` 0 the week before and 1 that week; the new starter's row has `pn_qb_starting` 1, the old one's 0;
`pn_qb_is_rookie_or_backup` 1 for Browning (7 career starts, all 2023) and Dart (0); the points-per-start gap −1.86
(Browning 20.05 over his 7 starts of 2023 vs Burrow 21.91 over his newest 17), −9.79 (Brissett vs Murray), NULL for Dart
(no start). One exception that is right: Noah Fant (from Seattle) is "changed" in CIN week 2 too — his last four games
were mostly with Geno Smith. **Offensive line**, MIN 2025 week 5 (reproduced from `raw.nfl_snap_counts`, `raw.nfl_injuries`,
`raw.nfl_rosters_weekly`; `scratchpad/waveD/d5/ol_handcheck.sql`): weeks 1–4, 239 team snaps; the five starters Fries
227 (0.9498), O'Neill 162 (0.6778, **Out** knee), Jackson 159 (0.6653, **Out** wrist), Skule 156 (0.6527), Jurgens 126
(0.5272, **Out** hamstring) → 3 out, share 1.8703 = the table (Kelly, on injured reserve, is 7th by snaps over the
window and not a starter by the rule). **Teammates**, LA 2025 week 7: Puka Nacua (target share 0.3103 over weeks 2–6)
Out → `pn_top_target_out` 1 and `pn_teammate_share_out` 0.3103 on every other Rams row, 0 on Nacua's own (his leading
teammate is Davante Adams, active).

Coverage (share of universe rows with a value; 2026 = the weeks published on 2026-09-26):

| Season | rows | qb (changed) | qb (ppg gap) | oline / teammates | oline, weeks 2+ | absence alert | own report | games missed last season |
|---|---|---|---|---|---|---|---|---|
| 2016 | 9,851 | 72.7% | 69.2% | 91.3% | 100.0% | 85.4% | 100.0% | — (no 2015) |
| 2017 | 9,681 | 88.0% | 85.8% | 94.0% | 99.6% | 91.6% | 99.8% | 80.7% |
| 2018 | 9,373 | 89.2% | 86.8% | 94.0% | 100.0% | 91.1% | 100.0% | 80.9% |
| 2019 | 9,608 | 87.5% | 85.1% | 93.8% | 100.0% | 90.8% | 100.0% | 80.7% |
| 2020 | 9,800 | 90.3% | 87.6% | 94.2% | 100.0% | 94.2% | 99.8% | 82.3% |
| 2021 | 10,538 | 91.8% | 89.1% | 94.4% | 100.0% | 94.4% | 100.0% | 85.8% |
| 2022 | 10,161 | 90.4% | 87.3% | 93.6% | 99.5% | 94.1% | 99.5% | 82.1% |
| 2023 | 10,034 | 91.6% | 89.3% | 94.0% | 99.8% | 94.2% | 99.8% | 81.1% |
| 2024 | 9,898 | 91.4% | 89.8% | 94.3% | 100.0% | 94.3% | 99.8% | 82.8% |
| 2025 | 10,268 | 91.7% | 89.2% | 94.4% | 100.0% | 94.4% | 100.0% | 82.6% |
| 2026 | 9,911 | 20.0% | 19.8% | 11.8% | 12.6% | 23.6% | 29.7% | 82.8% |

QB rows with `pn_qb_starting` known: 100% of 2016–2025. 2026: the projected starters are filled through week 4, the
reports through week 3 (week 4's comes out during the week).

**The train / serve gaps (measure them, do not assume them away).**
1. *The starting QB.* Training sees the QB who started; the live board sees nflverse's projected starter. Checked against
   today's nflverse file: the projections of 2026-09-26 for week 3's 30 unplayed team-games matched all 30 actual
   starters; for week 4, 2 of 32 projections changed during the week (CHI Bagent → Keenum, TB Mayfield → Jalon Daniels;
   the nightly picks such changes up until the freeze). A weaker source for comparison: ESPN's depth-chart QB1 at the last
   snapshot before kickoff (median 10.8 h) agreed with the starter in 495 of 544 2025 team-games and showed only 28 of
   the season's 55 starter changes. The archive keeps one copy of `games.parquet`; keeping a dated copy per nightly would
   measure the gap in-season.
2. *The injury report and the freeze.* Training sees the week's **final** report (Friday for a Sunday game); the decision
   record freezes a week's board at the week's **first** kickoff (B5, Thursday night), so a Sunday player's frozen
   projection was made before his final designation. v2's own `questionable` input has the same gap today. It matters
   for the report-based columns (`oline`, `teammates`, `own_injury`) and not for `qb` (the projected starter is filled
   a week ahead).

**Harness result** (fx1.0, test seasons 2023–2025, both leagues; mean over seasons of the league-averaged Δ, "n/3" =
seasons better; one session, 66 min wall, baseline from the cache): see STATUS § "Wave D (Iteration 12)" → D5 for the
full table. `qb` keeps QB (ΔSpearman +0.053, 3/3; ΔMAE −0.54 points, 3/3; interval score −0.084) and nothing else;
`teammates` keeps RB / WR / TE (+0.0064 / +0.0053 / +0.0054, all 3/3, MAE better 3/3) and hurts QB (−0.0069, 0/3:
mixed); `oline` and `own_injury` drop everywhere; `personnel` (all 20) keeps QB / RB / WR, drops TE (the extra columns
dilute the teammates signal). Where the QB gain comes from (2025, reference league, 677 played QB rows, MAE 6.04 →
5.39; `scratchpad/waveD/d5/qb_segments.py`): 74% from the 140 rows of QBs who played without being the projected
starter (relief and mop-up: v2 projected them 6.5 from their history, the actual mean was 2.1, with `qb` 3.3), 12% from
the 43 rows of a new starter (v2 9.0, actual 13.2, with `qb` 12.4), 14% from the 494 rows of the usual starter.

Five seasons (2021–2022 added with the harness's pieces, `scratchpad/waveD/d5/qb_wr_extend.py`; 2023 reproduces the
harness): `qb` at QB +0.046 / +0.018 / +0.072 / +0.022 / +0.065 (mean +0.0446, 5 of 5; MAE −0.51, 5 of 5); `teammates` at
WR +0.0032 / +0.0042 / +0.0023 / +0.0056 / +0.0082 (mean +0.0047, 5 of 5: consistent, 0.0003 under the bar); `personnel`
at WR +0.0059, 5 of 5. Recommendation (the PO's decision): v3 takes `qb` at QB and `teammates` at RB / WR / TE (per-position
inputs), drops `oline` and `own_injury`. **Shipped 2026-10-01 as v3.0** (§ "Projection v3"): the harness now refuses `personnel`, `qb` and
`teammates` (their columns are model inputs; kept for the record as `personnel.SHIPPED_GROUPS`); `oline` and `own_injury`
stay registered as candidates.
## Ranges and decisions (plan D6, Wave D round 2, 2026-10-01; `projections.fit_position` / `predict_position`, `league_lab.decisions`, `app/lib/cards.py`)

Andrew: "if an 80% confidence interval is like a 20-point spread, how useful is that?". The 80% range is
calibrated, so it cannot be narrowed by decree. Three things could change, and D6 tried all three: a
**sharper** range at the same honesty, a **50% range** to lead with, and the **decision quantity** itself.

### The two ranges

* **80% range, floor to ceiling** (`p10`, `p90`): unchanged from v2 (§ Projection v2: quantile regressors of
  the miss around the priced line on out-of-fold lines, split-conformal widened on the newest training season).
* **50% range, "most weeks"** (`p25`, `p75`, new columns on `ops.projections` and
  `mart_player_week_projections`): two more quantile regressors (0.25, 0.75) on the same rows and inputs as
  P10 / P90, fitted after them (each regressor has its own seed: P10 / P50 / P90 are bit-for-bit what they
  were), sorted, then widened by the split-conformal amount for 50%: the ceil((n + 1) × 0.5) / n quantile of
  `max(P25 − y, y − P75)` on the calibration season (`_conformal_widening`, the same function the 80% range
  uses). Production widenings (fit 2016–2025, calibrated on 2025, League of Scrubs, per projection tier
  low / middle / top — the tier rule below): 50% QB 0.53 / 0.80 / 0.91, RB −0.02 / 0.23 / 0.39, WR 0.00 / −0.17
  / 0.38, TE 0.02 / 0.03 / 0.30 points; 80% QB 0.79 / 1.81 / 1.28, RB −0.01 / 0.20 / 0.60, WR 0.00 / −0.04 /
  0.26, TE 0.00 / 0.04 / 0.32 (position-wide before the tier rule: 80% QB 1.06, RB 0.07; 50% QB 0.67, RB 0.03). Finally kept inside the 80% range around the
  median: `P10 ≤ P25 ≤ P50 ≤ P75 ≤ P90` (mart test `projection_50_range_inside_80_range`).
* **The tier rule (D6 follow-up, PO decision 2026-10-01).** Both widenings (80% and 50%) are computed **per
  position × league × projection tier**: the tiers are the terciles of the calibration season's priced line
  (out-of-fold) within the position (`TIER_QUANTILES = (1/3, 2/3)`; the cut points are kept on the model and a
  projected row takes its tier by its own `proj_points`); a tier with fewer than `TIER_MIN_ROWS = 200`
  calibration rows takes the position-wide widening (never needed so far: the smallest tier in the walk-forward
  has 206 rows, QB 2023; in production 213+). Why: position-wide, the board's starters held 76–77% (80%) and
  47–48% (50%) while the fringe held more; coverage at the nominal level is the contract, and per tier it holds
  on starters (78.8–80.5% / 48.1–51.0%) at no interval-score cost (−0.17% to +0.17%). Production widenings
  are logged per tier by `league-lab project`. NULL on rows written
  before D6 (2026 weeks 1–3 are frozen with P10 / P50 / P90 only; so is any week frozen before the first D6
  refit) and on K / DEF (kd1.0 has no 50% range); pages and the decision probability fall back to the 80%
  range there.
* **How wide** (walk-forward 2023–2025, both leagues, played player-weeks, the board's top 24 RB / WR and top
  12 QB / TE by projection each week): League of Scrubs — RB 17.9 → **9.5** points, WR 17.5 → **9.4**, TE 13.1 →
  7.5, QB 19.4 → 10.1 (80% → 50%); dynasty (full PPR, 6-point passing TDs) RB 20.4 → 10.7, WR 22.0 → 11.6, TE
  15.8 → 9.1, QB 27.4 → 14.1. **Coverage of the 50% range** (mean of 2023–2025 × both leagues, 4,042 QB,
  8,990 RB, 14,228 WR, 7,332 TE played player-weeks), with the tier rule: **RB 51.3%, WR 49.6%, TE 50.7%,
  QB 47.2%** (target 48–52%; position-wide before it: 51.3 / 49.7 / 50.7 / 46.7%). QB misses like its 80%
  range does (75.8%): see "Quarterbacks" below.

### Can the range be sharper? The experiment

Walk-forward 2023–2025 (each season N: components and out-of-fold lines fitted on 2016…N−1, the residual
models on 2016…N−2, calibrated on N−1), both leagues' scoring, played player-weeks, scored the harness's way
(per week with ≥ 8 players; season means; **interval score** = mean pinball loss at 0.1 and 0.9, lower =
sharper at the same honesty; the six league × season cells averaged per position). The component models and
priced lines were fitted once and shared by every variant, so the point projection and its Spearman are
identical across variants (QB 0.533, RB 0.683, WR 0.624, TE 0.583). The v2 variant reproduces the harness
baseline in `ops.feature_experiments` (key `cb461af0c56b4811`) to four decimals in every cell. Variants
(scripts and the full 18-variant table: `docs/STATUS.md` § D6):

| Variant | QB | RB | WR | TE |
|---|---|---|---|---|
| v2: interval score / coverage 80 / width 80 | 1.509 / 75.5% / 21.9 | 0.971 / 79.8% / 13.6 | 0.957 / 81.4% / 13.8 | 0.719 / 80.9% / 9.5 |
| (a) role inputs added to the quantile models (own points SD, dud rate and CV over the last 16 games, TD share of points, RB receiving share, QB rushing share; WR / TE aDOT and deep-target share) | −0.1% | −0.2% | −0.3% | −0.3% |
| (b) heteroscedastic: a scale model of the absolute miss × a fixed-shape residual distribution (normalised conformal) | +3.8% | +1.5% | +0.4% | +2.3% |
| (b) the same with the role inputs | +3.4% | +1.1% | +0.3% | +2.0% |
| (c) conformal per projection tier (terciles) | 0.0% | 0.0% | −0.1% | −0.2% |
| (c) conformal per role (deep / short WR-TE, receiving RB, rushing QB) | −0.1% | 0.0% | 0.0% | −0.1% |
| (c) each tail calibrated on its own (10% below, 10% above) | 0.0% | −0.1% | 0.0% | −0.2% |
| (a)+(c) role inputs, per tail, per tier | −0.1% | −0.5% | −0.7% | −0.5% |
| (d) two-part: separate models for regulars (snap share ≥ 50%) and the rest, per tail | −0.5% | +0.1% | +0.3% | +1.2% |
| regularised residual models (early stopping / leaf ≥ 200) | +0.7% / +0.4% | 0.0% / +0.2% | 0.0% / 0.0% | +0.3% / +0.5% |
| in-season recalibration (the season's played weeks join the calibration set) | −0.1% | 0.0% | 0.0% | 0.0% |
| control: **no inputs at all** (residual quantiles by projection bin) | +1.5% | +0.2% | −0.1% | 0.0% |

(Δ interval score vs v2; negative = sharper. Coverage stayed within 78.0–82.0% for every RB / WR / TE variant.)

**Verdict: nothing is kept.** No variant beats v2 by the 2% bar at any position; the best is −0.7% (WR).
The control explains why: residual quantiles that look only at the projection itself are within 0.2% of v2
at RB / WR / TE. Once the projection is known, the ~80 inputs do not tell a volatile player from a steady
one; the width is the week-to-week noise of fantasy points, not a modelling gap. A scale model is worse
(it chases noise). The 80% range is as sharp as this data allows.

Three findings that stand anyway:

* **Starters' ranges were slightly too narrow, the fringe's slightly too wide.** On the board's top 24 RB / WR
  and top 12 QB / TE the position-wide 80% range held 75.9–77.4% (50%: 46.8–47.9%); the average was right
  because players outside the top held more. Conformal per projection tier fixes it at no interval-score cost
  by making starters' ranges *wider* (top-24 WR 19.8 → 21.3 points at 80%). Not a sharpening (the 2% bar);
  **adopted as a calibration fix** (PO, 2026-10-01): the tier rule above, numbers below.
* **Quarterbacks** fall below the floor too often (15.4% instead of 10%; coverage 75.5% / 46.7%), in v2 and in
  every variant. The lower tail is partial games: in 2023, the 88 QB weeks with ≤ 25% of the snaps landed
  below P10 62.5% of the time, full games (507) 6.9%. The share of played QB weeks with ≤ 50% of the snaps
  rose from 12–13% (2016–17) to 18–20% (2020–25, 2022 aside at 15%), and none of the variants (per tail, per tier, in-season
  recalibration, regularised, two-part) closes the gap. It needs inputs that see the injury (plan D5).
* **P10 at 0** is the fringe: 17% of QB and RB, 34% of WR, 42% of TE played weeks have a floor of 0 (2023–2025,
  both leagues); by the snaps he actually played (2023, League of Scrubs): 80% of the WR weeks on ≤ 25% of the
  snaps, 3–7% of the weeks on ≥ 75% (healthy starters) at every position. The two-part split did not sharpen
  the starters' range (above).

**Per-tier calibration, before → after** (walk-forward 2023–2025, both leagues, the v2 residual models;
top-N = the board's top 24 RB / WR and top 12 QB / TE by projection each week among those who played, rest =
the others who played):

| Pos | Coverage 80: all / top-N / rest | Coverage 50: all / top-N / rest | Top-N width 80 / 50 (points) | Interval score 80 / 50 |
|---|---|---|---|---|
| QB | 75.5 → **75.8** / 77.4 → **78.8** / 74.6 → 74.3% | 46.7 → **47.2** / 47.6 → **48.1** / 46.2 → 46.9% | 23.4 → 24.1 / 12.1 → 12.2 | 1.5092 → 1.5094 (+0.01%) / 2.7785 → 2.7831 (+0.17%) |
| RB | 79.8 → **79.9** / 77.3 → **79.5** / 80.8 → 80.1% | 51.3 → **51.3** / 47.7 → **51.0** / 52.7 → 51.4% | 19.1 → 19.9 / 10.1 → 11.0 | 0.9709 → 0.9710 (+0.01%) / 1.7048 → 1.7055 (+0.04%) |
| WR | 81.4 → **81.1** / 75.9 → **79.7** / 82.7 → 81.4% | 49.7 → **49.6** / 46.8 → **49.0** / 50.4 → 49.8% | 19.8 → 21.3 / 10.5 → 11.1 | 0.9572 → 0.9558 (−0.15%) / 1.6752 → 1.6759 (+0.04%) |
| TE | 80.9 → **81.3** / 76.3 → **80.5** / 81.9 → 81.5% | 50.7 → **50.7** / 47.9 → **48.6** / 51.3 → 51.2% | 14.4 → 15.6 / 8.3 → 8.4 | 0.7186 → 0.7174 (−0.17%) / 1.2643 → 1.2648 (+0.04%) |

QB stays below both targets: partial games (above), not the tier.

### The decision probability (`league_lab.decisions`)

**P(A outscores B)** for a lineup call, from both players' calibrated quantiles in the league's scoring:

* each player is a **piecewise-linear quantile function** through P10 / P25 / P50 / P75 / P90 (three knots,
  P10 / P50 / P90, on a row without the 50% range): uniform density between knots; below P10 linear with the
  first segment's slope, never below 0; above P90 an exponential tail `P90 + s·ln(0.1 / (1 − u))` with
  `s = 0.1 ×` the last segment's slope, so the density is continuous and a 40-point week stays possible;
* the two are **independent unless they share a game**. Teammates and opponents use a Gaussian copula with
  the correlation measured on the walk-forward (normal scores of each played player-week's randomised PIT
  under its own distribution, pairs where both were projected ≥ 5 points, mean of the two leagues):
  teammates QB–WR **+0.22**, QB–TE +0.21, QB–RB +0.03, RB–RB **−0.08**, RB–WR −0.03, WR–WR +0.02, TE–WR +0.01,
  QB–QB **−0.41** (a starter and the backup who replaced him); opponents QB–QB +0.11, QB–WR +0.07, WR–WR +0.05,
  QB–TE +0.04, others within ±0.03; a pair with < 150 observations in a league (TE–TE teammates) uses the
  pooled value (teammates +0.05, opponents +0.03). From 540 pairs (QB–QB teammates) to 14,536 (RB–WR teammates), both leagues;
* **Monte Carlo**: 40,000 paired draws, fixed seed (the same pair always gets the same answer), a tie counts
  half (two floors of 0). Checked against the closed form for two normals (ρ = 0, 0.35, −0.3) within
  0.01, and the piecewise-linear version of those normals within 0.02 (`tests/test_decisions.py`).

**Calibration on 2024–2025** (walk-forward projections for the weeks, both leagues' Sleeper rosters of those
seasons; for every roster-week the B1 solver on QB–TE values (K / DEF / IDP slots dropped), every filled
slot's named alternative = the bench player the re-solve brings in, the probability before the week, the
outcome after): 5,374 pairs, **4,895 where both played** (the ranges are "if he plays"; 479 pairs had a
player who did not play). With the ranges as shipped (the tier rule): Brier **0.2208** vs 0.3672 for "the
higher projection wins = 100%" and 0.2491 for a coin flip; mean predicted 64.1%, observed 63.2% (2024: 63.5 /
63.7, Brier 0.2192; 2025: 64.6 / 62.7, 0.2225). Deciles (equal counts):

| Predicted | 49.7% | 53.3% | 55.8% | 58.3% | 61.1% | 64.0% | 67.1% | 70.9% | 75.8% | 84.8% |
|---|---|---|---|---|---|---|---|---|---|---|
| **Observed** | 49.2% | 52.8% | 52.9% | 58.0% | 61.1% | 60.4% | 64.8% | 75.2% | 75.7% | 82.1% |

By word: "a coin flip" (50–55%) 1,036 pairs, predicted 51.9%, observed 51.5%; "a lean" (55–65%) 1,821, 59.6% /
57.7%; "clear" (65%+) 2,038, 74.3% / 74.0%. The cards' three closest calls per roster-week (2,005 pairs):
Brier 0.2458 vs a coin flip's 0.2486 — the closest calls really are close to coin flips, and the percentage
says so (mean 56.2%, observed 54.1%). Slightly overconfident on average (0.9 points; 1.5 with the
position-wide ranges, Brier 0.2210); a shrink toward 50% fitted on one season did not help the other, so none
is applied. The same-game correlation is right in principle and immaterial here: 242 of the 4,895 pairs share
a game (Brier 0.2028 with it, 0.2025 without).

**On the cards** (`app/lib/cards.py`): the headline is "**Tucker outscores Monangai 54% of the time — a coin
flip.**" (whole percent, 1–99; 50–55% a coin flip, 55–65% a lean, 65%+ clear, read on either side of 50%),
the margin the lineup is solved on is the second line ("10.00 vs 9.85 projected: 0.15 apart."), then "Most
weeks: Tucker 6–14, Monangai 5–13." and "A bad week to a good week: 3–19 and 2–20." (whole points). Only for
two QB–TE projections; a kicker, a defense or a points-per-game value keeps the margin's words. When the
starter is below 50% the card says so and says both numbers: the range (how often) and the projection (how
many points on average) come from different models and can disagree on a close call. Week 4, League of Scrubs
roster 2: Croskey-Merritt projects 9.13 to Tuten's 9.07, but Tuten's range sits higher (most weeks 4–13 vs
4–12), so Croskey-Merritt outscores him 47% of the time. The Rankings board's range column is
the 50% range ("Most weeks"), the floor and ceiling in the full table; a week without it shows the 80% range
under its old name.

## Rest of season (ros1.0, plan E2, Wave E, 2026-10-01; `mart_player_ros_projection`, `app/lib/ros.py`)

One row per league × player (current season): the projection added up over the weeks left in **the league's**
season. Read by the Player card (one line + the week-by-week list), Rankings ("Rest of season" section under the
weekly board) and Trade Finder (the package's totals next to the engine's fit and market). One row, one number
and one rank on all three pages.

| Column | Definition |
|---|---|
| `from_week` | the first regular-season week whose **last** game has not kicked off (`lib.ui.current_week`'s rule, evaluated at build time; the nightly rebuilds daily, so between Monday night's kickoff and the next build the page's week can be one ahead: the pages print the mart's window) |
| `last_week` | the league's championship week: `playoff_week_start` − 1 + rounds × weeks per round (+ 1 for a two-week final). Rounds = the winners bracket's rounds (`stg_sleeper__brackets`), else ⌈log₂ playoff_teams⌉; weeks per round from Sleeper's `settings.playoff_round_type` (0 one week, 1 two-week final, 2 two weeks per round — values 1 and 2 unverified, both leagues use 0). Never past the board's last week. **League of Scrubs: 16** (4 playoff teams, 2 rounds), **Forever Unclean Dynasty: 17** (6 teams, 3 rounds) |
| window | `from_week` … `last_week`; a week with no regular-season `dim_game` row for his team is a **bye**: 0 games and no points, not a projection (`bye_weeks` lists them). The current week counts whole until its last game kicks off (a Thursday player's week stays in until Monday night, as in the trade engine's market) |
| `ros_points` | Σ `proj_points` (each week as the board rounds it, to the cent) over his weeks with a game in the window, whatever the board holds per week (a frozen kickoff board, refit values or the live board; a week held twice keeps the frozen row) |
| `ros_games` | the weeks summed; `ros_points_per_game` = `ros_points / ros_games` |
| `playoff_points`, `playoff_games` | the same over `greatest(from_week, playoff_week_start)` … `last_week` (0 once the playoffs are past) |
| `ros_sd` | √Σ sd_week², sd_week = (p90 − p10) / 2.563 — each week's calibrated 80% range read as a normal (P10 and P90 sit 1.2816 sd either side of the middle) |
| `ros_p10`, `ros_p90` | `ros_points` ∓ 1.2816 · `ros_sd` (floored at 0); NULL when any week in the window has no range (unknown is not zero). Centred on the projection, not on the quantiles' median, so the range always brackets the total the pages print |
| `ros_rank_pos`, `ros_rank_all` | rank by `ros_points` within the league, by position and overall (K and DEF included where the league starts them), rostered and free agents alike; ties broken by `player_key`. Only `is_ranked` players get a rank: on an active NFL roster at the first week of his window (`roster_status` ACT; a team defense always). A player on injured reserve keeps his total (it assumes he plays every remaining game) and has no rank — the weekly board's rule, without the week-only Out / Doubtful exclusion (one week out does not end a season) |
| `weeks_with_lines` | weeks in the window with a Vegas implied total on the board. Today only the current week: `mart_player_week_features.implied_team_total` is NULL for every 2026 week ≥ 5 (verified: 0 of the week-5…18 rows), so the later weeks lean on usage, form and the schedule and come out flatter (Amon-Ra St. Brown, dynasty: 18.1 in week 4, 17.5–18.0 every week after) |
| `weeks_json` | `[[week, points], …]` in week order, the weeks summed (the Player card's "week by week" line) |
| `player_key` | `gsis_id`; a team defense's Sleeper id (`LAR` where nflverse says `LA`), the key `ops.projections` and the trade engine use |

**The independence assumption.** The weeks are combined as if each were its own draw. They are not: a role
change, an injury or a trade moves every later week the same way, and the projections for weeks without lines
share one set of inputs. Positive correlation between weeks widens the true range (with an average week-to-week
correlation ρ over n weeks the variance is n·sd²·(1 + (n − 1)·ρ); ρ = 0.1 over 13 weeks already doubles the
variance, √2.2 ≈ 1.48× the width). So `ros_p10` / `ros_p90` is the narrowest honest range, not a calibrated one,
and the pages say so ("if every week were its own roll of the dice … the real range is wider"). The range also
assumes he plays every game: the projection has no injury risk in it. **Open**: measure the coverage of this range
on 2024–2025 (walk-forward per-row projections from `backtest-v2`, weeks 4 → 17 summed against the actual totals)
and, if it under-covers, inflate `ros_sd` by the measured factor (one number per position) — the D6 conformal step
applied to the sum.

**Against the trade engine.** `league_lab.trades.MARKET_SQL` (the market's "Season pts") sums the same
`ops.projections` rows from this week **to week 18**; on the same weeks it equals `ros_points` exactly (all 1,226
rows, `tests/test_ros.py::test_mart_matches_the_trade_engines_sum_on_the_same_weeks`). The two windows differ on
purpose: weeks after the league's final count for nobody in the league (League of Scrubs plays to week 16, the
dynasty to 17), so the market carries on average 14% (Scrubs, weeks 17–18) and 7% (dynasty, week 18) more points
than the league will play. Trade Finder shows both, labelled: the plain rest-of-season total (this mart) next to the
market price (the engine). Whether the market should stop at the league's final is the PO's call.

Size: 645 + 581 rows (Scrubs incl. 32 K + 32 DEF, dynasty), ~1.1 MB with indexes. Tests:
`dbt/models/marts/edge/mart_player_ros_projection.yml` (key unique, games fit the window and its byes, playoffs inside
the window, the range brackets the total, `weeks_json` length = games, ranked ⇔ rank, DEF ⇔ no gsis id) and
`tests/test_ros.py` (every row recomputed in Python from the board, the schedule and the bracket; the trade engine's
sum on the same weeks; the page sentences).

## Projection record (pr1.0, plan E1, Wave E, 2026-10-02; `league_lab.ingest.sleeper_projections`, `mart_projection_record`, page "Our record")

The benchmark people already get for free: Sleeper's own weekly projections, held against League Lab's board
and the actual points, week by week, in each league's scoring.

**Sleeper's side.** `league-lab ingest sleeper-projections` pulls
`api.sleeper.com/projections/nfl/<season>/<week>?season_type=regular&position[]=QB…DEF&order_by=ppr`
(`LEAGUE_LAB_SLEEPER_PROJECTIONS_URL`; not part of the documented v1 API) into `raw.sleeper_projections`, one
**snapshot** per pull (every row of a pull shares its `fetched_at`; never overwritten; a pull identical to the
week's newest snapshot adds nothing). The record uses **the last snapshot fetched before the week's first
kickoff** (`min(dim_game.kickoff_at)`, regular season) — the moment `ops.projections` freezes (B5), so both
sides are judged on what they said at the same time; Friday–Sunday news is in neither.

**Pricing.** Sleeper's projected stat line (its scoring keys) is parsed into the weekly-stats column names
(`STAT_COLUMNS`: `pass_yd` → `passing_yards`, `rec_tgt` → `targets`, `fum_lost` → `fumbles_lost_total`,
`fgm_50p` → `fg_made_50_59` …) and priced with `league_points()` — the macro that prices our own line, yardage
bonuses applied to the projected line the same way (a 104-yard projection pays the 100-yard bonus, 99.9 does
not). Python twin: `sleeper_projections.price_line` (= `scoring.compute_points`). Check: in a standard half-PPR
league (League of Scrubs' settings) the priced line reproduces Sleeper's `pts_half_ppr` within 0.05 (and
`pts_ppr` / `pts_std` with rec = 1 / 0) on the 29 priced fixture players (`tests/test_sleeper_projections.py`;
worst difference 0.00: both sides round to the cent). A DEF is not priced (team-defense keys are unmapped): pairs involving one are counted apart.

**Ours.** `ops.projections` rows with `frozen_source = 'kickoff'` (the board as published before the first
kickoff), QB / RB / WR / TE, `proj_points` rounded to the cent like the mart. Refit weeks (2026 weeks 1–3) are
never on the record, and no week is filled in after the fact: the record starts the first week Sleeper was
pulled before kickoff.

**Population and scores** (per league × season × week × position; scope `week`):

| Column | Definition |
|---|---|
| `n_both` | players on both boards (Sleeper id → gsis id via `player_id_map`) |
| `n_players` | of those, played and rankable on our board (Out / Doubtful / IR excluded) with an actual — drift's population |
| `ours_spearman`, `sleeper_spearman` | rank correlation with `points_actual` (average ranks); NULL under 8 players (drift's `min_players`) |
| `ours_mae`, `sleeper_mae` | mean \|projection − actual\| in the league's scoring; the `ALL` row pools the four positions |
| `ours_hit_rate`, `sleeper_hit_rate` | \|top N by projection ∩ top N by actual\| / min(N, n): N = 12 QB, **24 RB, 36 WR**, 12 TE (WR 36 here vs 24 in the backtest / drift: the plan's choice — three starting WRs plus a flex per team) |
| `status` | `scored` once every game on the week's board has players in (drift's rule); `in_play` before: counts only, scores NULL |

**Start/sit calls** (`position = 'ALL'`). Per roster and week, the decision cards' pairs
(`app/lib/cards.py` `decisions`): the three smallest-margin valued starters of the proposed lineup
(`ops.lineups`, not realised; weakest slot first on a tie), each with the bench player who comes in (value =
starter value − margin; the slot's best eligible bench player when that matches, else the one with that value),
taken as they stood before kickoff (no locks). Reproduced in SQL: 132 of 132 pairs identical to
`cards.decisions()` on the same rows (both leagues, weeks 2 and 4 of the sandbox clone). Ours picks the starter;
Sleeper picks whichever of the two it projects higher in the league's scoring (equal = no call); the right call
is whoever scored more (`league_player_week.points_observed`, Sleeper's own count, else `points_actual`).
`pairs_listed` = every pair; `pairs_no_sleeper` = one of the two has no Sleeper number (a DEF); `pairs_push` =
equal actual points; `pairs_n` = the rest (graded) = both right + ours only + Sleeper only + neither;
`pairs_disagree` = graded pairs where Sleeper picked the bench player (or tied), `pairs_ours_right_disagree` =
how many of those we won — the number that separates the two sources.

**Season rows** (`scope = 'season'`): the scored weeks so far — weekly means of the scores (like drift), sums of
the counts and calls; `week` = the last scored week, `first_week` = the first.

**What it is not.** Not a backtest (no past seasons: Sleeper's past snapshots were never saved); not every
player Sleeper lists; not Sleeper's own scoring (its line is counted the league's way); a few weeks are noise
(the page says so under four weeks).

### The decision record (dr1.0, V-1, Wave I-G, 2026-10-04; `ops.lineup_record`, `league_lab.validation`, `mart_decision_record`, `mart_decision_calls`, `league-lab validate`)

The projection record grades the numbers; this grades **the lineups we recommended**. Before it, `lineups()` re-solved
and overwrote `ops.lineups` every night, so nothing kept what the app said before kickoff (the review's "audit the
distinction between a frozen evaluation snapshot and the forecasts actually served").

**The record** (`ops.lineup_record`, written by every `lineups()` run — so every `project` — and by `league-lab
validate`). Per league × week, the `ops.projections` freeze rule (B5): the **next** week to kick off is replaced by
every build (the last build before its first kickoff wins: `record_source = 'kickoff'`); a week that has kicked off
is never rewritten; a kicked-off week with no rows (2026 weeks 1–4, played before the record existed; a league added
mid-season) is **rebuilt once** from its frozen `ops.projections` rows, solved as of one second before its first
kickoff (no locks), and labelled `reconstructed`. One row per player of the proposed lineup (starters, empty slots,
bench, unplayable: `ops.lineups`' columns), the lineup total, `model_version`, `pricing` (M4's label of the
league-week's projections; `flat` before it), and on a starter's row the decision cards' call: `call_rank` 1–3 (the
three smallest-margin valued starters a bench player could replace, weakest slot first on a tie — `cards.decisions`,
reproduced in `lineup.close_calls`; `tests/test_v1.py` holds them equal on random rosters), the bench player who
would come in, `p_win` = P(starter outscores him) (`decisions.win_probability` on the frozen ranges; QB–TE pairs only,
like the card) and `is_coin_flip` (the card's rule: under 55%, else under a point apart).

**The grade** (per roster-week; `validation.grade_roster_weeks` = `mart_decision_record`, equal on the clone's 110
roster-weeks and 330 calls):

| Column | Definition |
|---|---|
| `submitted_points` | the starters Sleeper lists for the roster-week, at Sleeper's points (= the matchup score) |
| `app_points` | the record's starters at the points they scored that week: Sleeper's count in the league; a starter on no roster that week, his points in the league's scoring (`fct_player_game_league`); no stat row = he did not play = 0 (Sleeper's own rule); a K / DEF with no number = **unknown**: the roster-week's `app_points` is NULL, left out of the sums, counted in `n_app_unknown` |
| `optimum_points` | the hindsight optimum (`ops.lineup_totals` `is_realised`: the best lineup the roster Sleeper listed could have started, at Sleeper's points) |
| `regret` | optimum − submitted (≥ 0) |
| `app_edge` | app − submitted: what following our lineup would have added |
| `app_regret` | optimum − app (can be below 0 when the record's roster held a player dropped before kickoff who then scored) |
| `n_changed` | the record's starters Sleeper did not start |
| `is_news_affected` | a starter of a `kickoff` record whose week's final injury report (`mart_player_week_features`) differs from the one the build saw, or who went to NFL injured reserve; graded apart (`news`). A rebuilt week read the final report: never flagged |
| `status` | `scored` once Sleeper has scored the week; `in_play` before, every point column NULL |

**The calls** (`mart_decision_calls`): each card call graded by what happened — `outcome` 1 = the starter outscored the
bench player, ½ = equal, 0 = not. The calls with a percentage make the calibration: `decisions.coverage_table`
(equal-count bins, at least 10 calls a bin, at most 10 bins: predicted vs landed) and `decisions.brier`; the coin
flips (under 55%) make the line "The coin flips landed 54% for the side we leaned (52% expected, 31 calls)".

**The season to date** (`validation.summary`; `/api/record` `decisions`, About, the console's Record page): per scored
week the league's sums over the roster-weeks with every number known; the season = the sum of the weeks (to the
cent; `api/tests/test_v1.py`).

**What it is not.** Not a backtest (the record starts in 2026). The rebuilt weeks are kinder to us than a real
Thursday-morning call: they read the final injury report and, for weeks 1–3, the refit board (`frozen_source =
'refit'`, trained on 2016–2025, so no 2026 outcome is in the model, but the board is not the one managers saw). The
record freezes at the week's **first** kickoff (Thursday): Friday–Sunday news reaches the lineups served later in the
week, not the record — that is exactly what the news-affected cases measure. Two or three weeks are a small sample.

**First numbers** (the sandbox clone `league_lab_i0a`, 2026-09-26 snapshot, weeks 1–2 scored, both rebuilt from the
refit v2.0 board): League of Scrubs — our lineups would have scored 23.54 points fewer than the ones started (−20.88
week 1, −2.66 week 2; −1.2 a team a week); the best lineups in hindsight beat the ones started by 313.7; the coin flips
landed 59% for the side we leaned (52% expected, 34 calls); 60 graded calls, Brier 0.235. Forever Unclean Dynasty —
118.10 fewer (−148.05 week 1, +29.95 week 2); hindsight +677.9; coin flips 49% (52% expected, 42 calls); Brier 0.251.

#### Personal and live (dr1.1, V-2, Wave I-H, 2026-10-04; `league_lab.validation` V-2 block, `league_lab.record_mfl`, `league_lab.record_run`, `ops.decision_market`, `/api/record?team=`)

Four additions; every dr1.0 number above is unchanged (the clone's Scrubs and dynasty weeks grade to the cent as before).

**News from the event store.** `events.events` (IG-2) holds every injury-status move the server saw, with its time.
A `kickoff` record's starter is **news-affected** when the store has an availability event for him after the record's
`run_at` and before **his own** kickoff (his game's `dim_game.kickoff_at`; unknown → the week's first kickoff + 4
days) whose status differs from the one the build saw (`report_status`; none = `ACTIVE`). The store answers for a
league-week only when it was running across it (its first availability event at or before the week's first kickoff,
its newest at or after `run_at`); otherwise the dr1.0 rule (the final report differs) stands. Each roster-week says
which: `news_source` = `events` | `report` (`decisions.news.source`, `weeks[].news_source`: `mixed` when both). The
store lives on the hosted copy and the marts are built in the nightly's database, so the marts carry the report rule
and **the API applies the store's flags on the request** (`validation.news_overrides` → `apply_news`); `league-lab
validate` reads the store itself where the database has it. Graded apart as before; the sentence names the count and
the net, e.g.: "2 lineups had a starter's injury status change between our build and his kickoff; there our lineups scored
−4.1 against the ones started. They are graded apart: we could not have known." Rebuilt weeks are never flagged.

**"Had you started Sleeper's projections"** (`ops.decision_market`, written by `league-lab validate`; recomputed
every run, so not record state). For each record roster-week of a Sleeper league: the best lineup of **the roster the
record saw** (its starters and bench; the unplayable stay out) valued by Sleeper's projection — the last snapshot
fetched before the week's first kickoff (`mart_projection_record`'s rule) — priced in the league's scoring the way the
record priced ours (`scoring.price_projected` in the week's `pricing`; a K flat; `why.market_points`' rule). Sleeper's
DEF line is not priced: a DEF keeps our value, so the two lineups never differ there. A player Sleeper has no line for
is unvalued (seated only where nobody valued can play). Graded like ours: `market_points` (NULL when a starter has no
number, `n_market_unknown`), `market_edge` = market − submitted (`mart_decision_record`; a dbt test holds the
identity). A week's league sum (`weeks[].market`) only when every team has one; the season (`season_totals.market`,
`market_weeks`) over those weeks; `sentences.market`, e.g. (the shape; no number yet): "Weeks 5–6: had every team started Sleeper's projections, the
league would have scored 2410.3 — 12.4 fewer than our lineups and 8.1 more than the ones started." The house leagues
only (Sleeper's projections are archived for them); the sandbox clone holds no snapshot, so its numbers are null.

**One team** (`/api/record?league=&team=` → `decisions.team`; `validation.team_summary`; the Team page's "Your calls
this season", the console's Record page). The roster's graded weeks under the league's filter (scored, every number
known — so the teams' weeks add up to the league's to the cent: `api/tests/test_v2.py` sums all ten Scrubs rosters),
each with started / ours / best / Sleeper's / the edge / the regret / `n_changed` / the news flag and its close calls
("Chris Olave over Xavier Worthy (we gave it 64%): 18.6 to 11.0 — the right call."), the season sums, the calls'
calibration (n, landed, expected, Brier, the coin flips), the news-affected weeks, and the sentences: "Weeks 1–2: you
started 265.0; our lineup would have scored 253.9; the best possible was 281.7." · "Our closest calls for you landed 3
of 6 (3.3 expected)."

**MyFantasyLeague leagues.** An MFL league has no `ops.lineups` rows, so its record is the **on-demand** lineup
(`anyleague._solve_roster`, the frame My Week serves) frozen under the same rule (`record_mfl.mfl_record_rows`): the next
week to kick off is written before its first kickoff from the league's current rosters (`kickoff`); a played week
with no rows is rebuilt once (`reconstructed`) from the rosters MFL's `weeklyResults` lists for it, priced on that
week's frozen `ops.projection_lines` in the league's scoring, as of one second before its first kickoff; a week MFL
has not scored waits. The calls' odds come from the on-demand ranges (the opponent is left out of the pair's
correlation). Rows: `ops.lineup_record` with `league_id = 'mfl:<id>'`, written by `league-lab validate` for the keys
in `LEAGUE_LAB_RECORD_MFL` (or `--mfl`). **The grade** reads MFL itself on the request (`record_mfl.mfl_load`):
submitted = the franchise's starters at MFL's scores (= its score), optimum = MFL's own `opt_pts`, ours = the
record's starters at MFL's player scores (a listed player with no score = 0, MFL's count; a starter on no franchise
that week = unknown, never 0); a double-header franchise counted once a week; no final injury report (the news flag
only through the event store). The marts leave MFL rows out.

**First numbers.** Scrubs roster 6 (GoodGameBuddy), weeks 1–2 rebuilt: started 265.0, ours 253.9, best 281.7 (−11.1
for us; 16.7 left on the bench); calls 3 of 6 (3.3 expected). Dad's league (MFL 70587, the fixtures' weeks 1–3, all
rebuilt): started 4197, ours 4059, best 4880 — our lineups 138 fewer (−3.8 a team a week), the best lineups 683 more
(19.0 a team a week); coin flips 57% (52% expected, 27 calls); 100 calls with odds, Brier 0.225. Knight Train: started
224, ours 223, best 331.

## Effect on their starters and the sanity bound (ti1.1, IE-1, Wave I-E, 2026-10-03; was "Trade interest and the sanity bound", ti1.0, IA-2; `api/league_lab_api/decisions.py`, `league_lab.trades.sanity`)

- **Window**: the weeks a trade is priced over — `week` (this week), `next4` (this week and the next three: the board's
  horizon, the default), `ros` (this week to the league's final, `anyleague.ros_window`), `playoffs` (the league's
  `playoff_week_start` to the final). Weeks past the board's four come from the rest-of-season board (each player's
  projection that week in the league's scoring; a bye is unplayable; IR slot / taxi / NFL IR / no team as in the
  board's last week). Gain over the window = Σ over its weeks of (best lineup after − before), both rosters re-solved.
- **Effect on their starters** (the dial; ti1.1, IE-1 — the casual-user review: "Their interest: 0/100", "Likely" and
  "Hard to say no" implied a prediction of the other manager's answer that the number never was): from the other
  team's best-lineup gain over the window, g (unchanged). Label: g < −0.05 "Makes their lineup weaker", −0.05 ≤ g < 2
  "About even", 2 ≤ g ≤ 6 "Improves their lineup", g > 6 "Improves it a lot" (ti1.0's "No deal" / "Maybe" / "Likely" /
  "Hard to say no" retired; a gain in [−0.05, 0.05), formerly "No deal", now reads "About even"). The needle's position
  is unchanged — piecewise linear through (−6, 0), (0, 25), (2, 50), (6, 75), (12, 100), clamped — but the 0–100
  number is no longer shown. **The need** (`interest.need`, the calculator): one phrase from the other side's lineup
  this week by starter membership — "fills their empty RB", "starts at their WR/TE over Robinson" (who goes to the
  bench), "takes over their team QB from Kansas City Chiefs QB" (whom they trade away); none when nothing they get
  starts this week. Lineup fit by our projection — not an acceptance probability; any future acceptance model is
  validated separately and labelled apart from this.
- **The least costly package first** (IE-1, the Finder): when a partner's two-for-one gives two of yours for one of
  theirs and one of the two alone reaches the same gain for you (|Δ| < 0.05 over the window) and still raises both
  lineups, the one-for-one leads (`is_best`, the headline, "Try this trade"; `cheaper_than`) and the two-for-one names
  the extra player as `optional` with his rest-of-season points ("it costs you RB depth (RJ Harvey: 97 season
  points)"): a bench player's cost is never 0. Both packages keep their own gains.
- **Sanity bound** on partner suggestions (never on a trade the user builds; the calculator only says it): (b) the
  market — a player given whose projection this week is under 65% of Sleeper's (`raw.sleeper_projections`, the week's
  latest snapshot, priced in the league's scoring); (a) **the value gap** (ti1.2, IG-1, Wave I-G — was the raw
  rest-of-season totals, ti1.1): Σ season value above replacement given − Σ received > 25% of Σ given, and the two not
  about even (`trades.value_gap`; § "Value to my lineup" › "Team units and the value rule"). Either sets the package
  aside and the search takes the next best. Unknown is not zero: a player without the number is not judged.

- **Against the alternatives** (ta1.0, IF-2, Wave I-F, 2026-10-03 — the decision-quality review § Priority 3: the
  Finder's headline, +9.8 over weeks 4–7 on the live server, lost to a free Arizona team QB claim, +11.4, for an open
  spot, and nothing said so). One ladder per roster and window, the same weeks and scoring: **standing pat** (0), **the
  best legal waiver move** (`decisions.best_alternative`: IF-1's `best_waiver_move` — the claim's starter gain net of
  the drop's cost — when it is in `decisions`, over the next four weeks; else, and for the other windows, the open-spot
  fill on today's free agents, `ctx.fa_pool` + `trades.best_fill`, and with no open spot the best add for each droppable
  player with his lineup loss netted out), **the trade**. `beyond_alternative` = the trade's starter points over the
  window (this week's for the one-week window) − the alternative's; `beats_alternative` when it is ≥ 0.05. **Ranking**:
  the trades that beat the alternative first, then by `beyond_alternative` (= by your gain, the alternative being one
  number per roster and window), the bigger package never above its cheaper equal (IE-1); `rank` 1 is the headline —
  the headline and the first card are the same trade (they were not: the headline was the best partner's best package,
  the first card that partner's one-for-one). Was: partners by the smaller of the two gains, then the sum
  (`Package.order`; the search itself is unchanged and still finds, per partner, the package both sides gain most from).
  A trade below the alternative is marked (`demoted`) and keeps a reason only from the numbers (`other_objective`: more
  this week than the claim by ≥ 0.5; more season value above replacement coming in, not about even; in the calculator,
  the bench's best lineup up ≥ 2 this week) — never invented. A trade that takes the open roster spot the claim needs
  says so. **The strip**: per week, each side's best-lineup change (`trades.package_weeks`, `package_gains`' code); its
  sums are the gains. **The value concepts** (`trades.VALUE_CONCEPTS`), never added to one another: projected points
  (one player, one week), starter points (the best legal lineup's change over the window), backup coverage (the bench's
  best lineup), **season value above replacement** (`price_by_player`: the fairness test; package size named — the
  roster spots freed or used — and the players it cannot count), rest-of-season projected points (the raw totals,
  labelled "all positions added up — not a fairness test"). The calculator's warning (`calc_sanity`) is on season value
  above replacement (given − received > 25% of given, every player priced); the Finder's sanity bound on suggestions
  (rule (a), the raw rest-of-season totals) is unchanged.

## Calibration of the top (cal1.0, Wave I-A M1, 2026-10-03; `league_lab.calibration`, flag `LEAGUE_LAB_PROJECTION_CALIBRATION`, off)

The question (Andrew, Iteration 17 B): does the model pull the best players toward the middle? If it did, the
player-weeks it projects highest would beat their projection on average. Measured out of sample, per player-week.

**Rows.** `ops.projection_backtest` keeps per-week scores only, so `calibration.oof_rows` re-runs the backtest's
walk-forward (`fit_position` / `predict_position`, production inputs, trained on 2016..S−1) and keeps every
player-week: projection, P10–P90, actual (the 12 components priced in the league's scoring, yardage bonuses
included; 2-point and 40-yard-TD bonuses are not in the components). On 2023–2025 the rows reproduce every stored
v3.0 cell of `ops.projection_backtest` exactly. `ops.calibration_oof` (an experiment clone, or
`calibration.run_build_oof()`) stores the played rows for fitting.

**Diagnosis** (`with_buckets`, `bias_table`). Bias = mean(actual − projected). It is computed per league × position ×
rank bucket (top 6 / 7–12 / 13–24 / 25+ by projection within the week, among the played rows the harness scores)
or × projected-points decile (within league × position). The standard error treats rows as independent, so it is
a lower bound. Result, 2023–2025: in the Scrubs scoring (no bonuses) the top 6 miss by −0.98 (QB) to +0.51 (WR),
changing sign by season. In the dynasty scoring the top 24 RB / WR / TE are +0.7 to +1.4, about two thirds of it the
yardage bonuses: they are priced on the projected line all or nothing (a 104-yard line pays the 100-yard bonus, 99
does not), but a top receiver crosses 100 in about a quarter of his games. Without bonuses the dynasty top-6 miss is
+0.5. Bottom half of every position: −0.3 to −0.6 (too high). Numbers and tables: STATUS § "Wave I-A" (M1).

**The map** (`fit_map`, `apply_maps`). Per position × scoring, with knot = the 80th percentile of the fitting rows'
projections: `cal(x) = x + level + s_lo·min(x − knot, 0) + s_hi·max(x − knot, 0)`. The coefficients come from least
squares on actual − projected, with t-statistics clustered by player (a player's weeks are not independent). A
coefficient is used in full at |t| ≥ 2 and scaled linearly to 0 at |t| ≤ 1, so noise gives the identity. Slopes stay
within ±0.5, so the map is strictly increasing: the order within a position, and so Spearman and the top-N, never
changes. Modes: `hinge` (level = s_lo = 0, s_hi ≥ 0) and `two_piece` (all three). The ranges move with the point,
except a band at 0 stays at 0 (the point mass of zero-point games). Fewer than 1,500 fitting rows: identity.
`walk_forward_calibrate` fits the map for season S on earlier seasons only (optionally the newest `window`).

**Measured** (walk-forward, 2023–2025 and 2026 weeks 1–3, both house scorings; MAE, pinball, interval score,
coverage, Spearman). `hinge` is the identity except dynasty WR (MAE +0.012). `two_piece` on the last 3 seasons
passes the harness's MAE bar (−0.05) only at WR (−0.082 dynasty / −0.074 Scrubs, 3 of 3; 2026: −0.14 / −0.15), by
lowering the fringe. RB −0.01 / −0.02 (2 of 3), TE ≈ 0, QB worse (+0.02 / +0.03). WR coverage rises to 0.85 because
P10s reach the floor; the interval score moves −0.003. Fitted on every earlier season it is worse: the bias drifts
by era.

**Production, off by default.** With `LEAGUE_LAB_PROJECTION_CALIBRATION=1`, `project` fits `two_piece` maps for
`CAL_POSITIONS` (WR) on the newest `WINDOW` (3) seasons of `ops.calibration_oof`. It applies them to the house
leagues' `ops.projections` rows and to `ops.projection_ranges` of the reference scorings those leagues are.
Kicked-off weeks keep their stored rows (B5), and `frozen_source` rows are never touched. The stat line
(`ops.projection_lines`) is unchanged, so on-demand leagues, priced from the line at request time, are not
calibrated. dbt's `assert_projection_ranges_price_the_lines` (warn) then flags the calibrated weeks, by design.
Without `ops.calibration_oof` the flag logs a warning and changes nothing. The PO's call: leave it off (a WR-only
gain that comes from the fringe).

**Expected yardage bonuses** (`fit_bonus_curves`, `bonus_delta`; a measured proposal, not wired). Each bonus is
priced at its probability: an isotonic P(yards ≥ threshold | projected yards) per position × stat × threshold,
fitted on earlier seasons. The curves are scoring-free. Dynasty 2023–2025: top-6 bias RB +1.19 → +0.51, WR +1.43 →
+0.61 (QB −0.34 → −1.23); weekly MAE +0.02 to +0.03, because a mean correction of a skewed bonus does not help a
median loss; Spearman ±0.005. It is right for totals (rest of season, trades) and does not help weekly start/sit.
It belongs in the pricing of a projected line (v3.1 candidate), not in a points map.

### v3.1: the ranges' target, the fringe level, cold starts (Wave I-G M5, 2026-10-04; three switches, all off)

Three candidates from M1's and M3's lists, each measured walk-forward and judged by a rule fixed before the verdicts
were read (one amendment, made on the first season's QB rows: a range whose v3.0 coverage is already outside 78–82% —
QB, about 73–76% — "holds" when it gets no farther from the nominal level). None changes the board unless its switch
is on; none bumps `MODEL_VERSION`.

**The harness.** `experiments.v31_rows` is the walk-forward of `backtest-v2`, kept per player-week (M1's `oof_rows`
with both range targets): for each test season S, `fit_position` on 2016..S−1 with the production inputs, applied to
S, in both house scorings. The two range targets share one set of component fits (`experiments.shared_component_fits`
returns the models already fitted for the same rows), so the point projection is identical by construction and only
the quantile models differ (checked on every fit). Every row carries both actuals: `actual` (the 12 components priced,
what `score_predictions` has always graded) and `graded` (`projections.graded_actual`: the same plus the 2-point
conversions, the 40+ / 50+ TD bonuses, fumble-recovery and special-teams TDs; equal to `fct_player_game_league.points`
on every 2024 played row of both house leagues, 5,735 each, to the cent). Scores: `experiments.score_v31` (Spearman,
top-N, MAE, the 80% and 50% ranges' coverage, width and interval score per league × week × position, the harness's
definitions), paired by `paired_v31` (the season is the paired unit). Test seasons: the point corrections 2021–2025
(the component-only walk-forward of 2018–2025 is cheap); the ranges 2023–2025, the harness's default — refitting the
quantile models twice per season took 15–40 minutes a season on the shared sandbox, so 2021–2022 did not fit the time
box. Rows: `scratch/rows` of the M5 run (not in git); the seed rows: `dbt/seeds/feature_experiments.csv`
(`range_target_graded`, `fringe_level`, `cold_start_prior`).

**1. The ranges' target** (`LEAGUE_LAB_RANGE_TARGET=graded`; `projections.range_actual`). The residual models were
fitted on the components' price, so everything the record grades beyond the 12 components fell outside every range:
per game the graded actual is above the components' price by QB 0.44 / RB 0.07 / WR 0.12 / TE 0.04 in the dynasty's
scoring and QB 0.12 / RB 0.03 / WR 0.04 / TE 0.03 in Scrubs' (2024; Scrubs has no long-TD bonus, the gap there is
2-point conversions). Under the switch `load_frame` joins the outcome columns (`outx_*`, `join_graded_extras`) and
`fit_position` takes the residuals against the graded actual; the conformal widening is measured on the same target.
Rule (`experiments.decide_ranges`, per league × position, both judged against the graded actual): keep when the mean
paired change of the 80% interval score is at most −0.005 points and lower in ceil(2n/3) seasons, **and** the coverage
holds (`coverage_holds`: 78–82% at 80% and 48–52% at 50%, or — QB, whose v3.0 range already covers about 73% — no
farther from the nominal level than v3.0's plus 0.005); a mean change under 0.005 either way is "no change".

Results (2023–2025, both house scorings, scored on the graded actual; the point projection, Spearman and MAE are
identical by construction). Δ = graded target − v3.0; the interval score is (pinball 10 + pinball 90) / 2 in points
(lower is better):

| League | Position | Δ interval score 80% (seasons lower, of 3) | Δ interval score 50% | Δ width 80% | coverage 80%: v3.0 → graded | coverage 50%: v3.0 → graded | per league |
|---|---|---|---|---|---|---|---|
| dynasty | QB | −0.0066 (2) | −0.0036 | +1.09 | 0.751 → 0.756 | 0.460 → 0.472 | keep |
| dynasty | RB | +0.0002 (1) | +0.0037 | +0.21 | 0.799 → 0.802 | 0.512 → 0.513 | no change |
| dynasty | WR | +0.0055 (0) | +0.0029 | +0.40 | 0.805 → 0.805 | 0.502 → 0.504 | drop |
| dynasty | TE | +0.0001 (1) | +0.0009 | +0.03 | 0.813 → 0.814 | 0.517 → 0.507 | no change |
| Scrubs | QB | −0.0036 (2) | +0.0050 | +0.16 | 0.761 → 0.761 | 0.474 → 0.478 | no change |
| Scrubs | RB | +0.0017 (2) | +0.0024 | +0.08 | 0.806 → 0.804 | 0.524 → 0.512 | no change |
| Scrubs | WR | +0.0013 (2) | +0.0019 | +0.14 | 0.805 → 0.808 | 0.499 → 0.495 | no change |
| Scrubs | TE | −0.0007 (3) | −0.0001 | +0.06 | 0.806 → 0.812 | 0.510 → 0.505 | no change |

Per season (Δ interval score 80%, the graded target's coverage): dynasty QB +0.0039 (0.720) / −0.0069 (0.766) /
−0.0168 (0.781); dynasty WR +0.0052 / +0.0081 / +0.0032. **Verdict: keep at QB, drop elsewhere.** The target matters
where the ungraded part is large — a QB's 40+ pass TDs (2 points each in the dynasty) and 2-point passes, 0.44 a game —
and there the 80% range is 1.1 points wider on average and gets closer to its nominal coverage in both bands; at
RB / TE the extra is 0.03–0.07 a game and nothing moves; at WR in the dynasty the wider range costs more than it
covers. `RANGE_TARGET_POSITIONS = ("QB",)`: the switch on applies at QB only (`graded-all`, the harness's setting,
everywhere). Judged on the components' actual instead, every cell is within ±0.0061 (dynasty WR +0.0061, the only
drop).

**2. The fringe level** (`LEAGUE_LAB_FRINGE_LEVEL=1`; `calibration.fit_fringe`, fr1.0). M1 found the bottom half of
every position 0.3–0.6 too high in 2023–2025. The correction: per position × scoring, tiers by weekly projected rank
(25–36, 37–60, 61+; cut points = the median over the fitting weeks of the 24th / 36th / 60th projection, in points),
each tier's level = its mean residual (actual − projected), player-clustered and shrunk like cal1.0 (0 at |t| ≤ 1, full
at |t| ≥ 2), anchored at 0 at the top-24 cut, linear between the tiers' median projections, never falling faster than
0.5 a point and never below half the line: strictly increasing, so the order within a position — Spearman, the top N —
cannot change, and the top 24 do not move. Fitted on the 3 seasons before S (cal1.0's window; the bias drifts by era).
Rule: `experiments.decide` on MAE / Spearman per position (the leagues averaged, the season paired) **and** the top-24
bias may not grow by more than 0.02 in either league.

Results (2021–2025; the interval columns 2023–2025, where the ranges exist):

| Position | Δ MAE (seasons lower, of 5) | Δ Spearman | top-24 bias, dynasty: before → after | top-24 bias, Scrubs | Δ interval score | coverage 80%: before → after | decision |
|---|---|---|---|---|---|---|---|
| QB | +0.084 (0) | 0 | +0.32 → +0.30 | −0.26 → −0.27 | +0.0031 | 0.760 → 0.760 | drop (hurts) |
| RB | −0.005 (2) | 0 | +0.98 → +0.98 | +0.49 → +0.49 | −0.0003 | 0.804 → 0.827 | drop |
| WR | −0.021 (3) | 0 | +0.85 → +0.85 | +0.13 → +0.13 | −0.0028 | 0.806 → 0.859 | drop |
| TE | +0.022 (1) | 0 | +0.37 → +0.38 | +0.19 → +0.19 | +0.0009 | 0.809 → 0.833 | drop |

**Verdict: drop at every position.** The fringe's miss changes sign by era: fitted on 2018–2020 the levels are
*positive* (the fringe then scored more than projected: QB +2.1, WR +0.3 to +0.6, TE +0.8), fitted on 2020–2022 they
are near 0 at RB / WR / TE (QB still +1.0), and in 2021–2025 the 25+ bucket's miss is QB +0.43 to +0.58, RB −0.13 to −0.19,
WR −0.28 to −0.32, TE −0.09 to −0.10. A level fitted on the seasons before cannot follow it; at QB it lifts the
backups too far (25+ bucket +0.58 → −0.36 in the dynasty; MAE +0.08). M1's "over-projected fringe" is real in 2023–2025 and not a stable property of the
model; the order is untouched either way (the map is monotone), so the board's decisions do not depend on it.

**3. Cold starts** (`LEAGUE_LAB_COLD_START=1`; `calibration.fit_cold_prior`, cs1.0). A player with fewer than 3
played regular-season games before the week (any position he was listed at; a career that began before 2016 is never
cold) has no last-3 or season shares, and the model sees NaNs. Measured on 2021–2025 (played rows, the components'
actual), cold starts are over-projected at every position, the debut most:

| Dynasty scoring, 2021–2025 | career games 0–2: n, bias, MAE | a new team, games 0–2 | the rest |
|---|---|---|---|
| QB | 183, −0.35, 5.54 | 372, +0.09, 6.08 | 2,775, +0.50, 7.93 |
| RB | 461, −0.65, 3.89 | 545, −0.51, 4.24 | 6,600, +0.30, 4.85 |
| WR | 690, −0.85, 3.95 | 943, −0.95, 4.16 | 10,193, +0.06, 4.98 |
| TE | 347, −1.06, 2.98 | 389, −0.44, 2.67 | 5,310, +0.19, 3.67 |

By career game (dynasty, bias): the debut is the worst — RB −1.79, WR −2.25, TE −1.49, QB −0.48; game 2 RB +0.19,
WR −0.12, TE −1.04; game 3 RB −0.20, WR −0.02, TE −0.60. A WR with no history gets about 6 points (the
rookie WRs without a game in the 2026 week-5 board sit at 5.8–6.1); a debut scores about 2 less than projected. Scrubs' table is the same shape
(RB −0.63, WR −0.76, TE −0.93). Veterans in their first games for a new team are over-projected too (RB −0.51, WR
−0.95, TE −0.44): a lead, not addressed here (the draft-slot prior is a rookie's).

The fix: per position × scoring, the mean actual of cold starts by draft slot (picks 1–32, 33–64, 65–128, 129+,
undrafted; shrunk to the position's mean by n / (n + 30)), blended with the projection as w·model + (1 − w)·prior,
w fitted per games-played step (0, 1, 2) on the seasons before S (2018..S−1) by absolute error over a 0.0–1.0 grid;
at 3 games and beyond the blend is the identity. The ranges move with the point (`shift_bands`). Rule: the cold rows'
MAE falls by at least 0.05 (the harness's bar) in ceil(2n/3) seasons (the leagues averaged), and the whole board is
not hurt (`decide`'s "hurts").

Results (2021–2025, the leagues averaged per season; "cold rows" = the blended player-weeks, the whole board =
every played row; the interval columns 2023–2025):

| Position | cold rows (both leagues) | cold Δ MAE (seasons lower, of 5) | cold bias: before → after | board Δ MAE | board Δ Spearman | board Δ interval score | decision |
|---|---|---|---|---|---|---|---|
| QB | 366 | 0.000 (0) | −0.30 → −0.30 | 0.000 | 0 | 0 | drop (the fit keeps the model: w = 1) |
| RB | 922 | −0.159 (4) | −0.64 → −0.35 | −0.009 | +0.0018 | −0.0006 | keep |
| WR | 1,380 | −0.314 (5) | −0.81 → −0.19 | −0.018 | +0.0034 | −0.0008 | keep |
| TE | 694 | −0.298 (5) | −0.99 → −0.12 | −0.017 | +0.0037 | −0.0007 | keep |

**Verdict: keep at RB / WR / TE.** The weights fitted on 2018–2024 (what 2025 used; the dynasty's, Scrubs' within
0.1): RB 0.0 / 1.0 / 0.8 on the model at career games 0 / 1 / 2, WR 0.0 / 0.5 / 0.6, TE 0.0 / 0.2 / 0.3, QB 1.0
throughout. The priors (dynasty, points a game, played weeks): WR picks 1–32 10.2, 33–64 6.1, 65–128 4.7, 129+ 3.6,
undrafted 2.6; RB 9.0 / 6.1 / 5.7 / 3.3 / 3.8; TE 4.4 / 3.6 / 3.2 / 2.6 / 2.0. The order changes only among cold
starts and the players around them, and for the better (whole-board Spearman +0.002 to +0.004).

**In production.** All three switches are off. The ranges' target lives inside `fit_position` (the residual
target), so `LEAGUE_LAB_RANGE_TARGET=graded` reaches every scoring the night it is turned on — at QB only
(`RANGE_TARGET_POSITIONS`), in every reference scoring (the harness judged the two house scorings). `project` applies
the fringe level and the cold-start prior through `calibration.calibrate_outputs` (after cal1.0's map) at the
positions the harness kept — `FRINGE_POSITIONS` (none) and `COLD_POSITIONS` (RB, WR, TE) — fitted on
`ops.calibration_oof` (`run_build_oof`, the 3 seasons before) and the game history (`fct_player_game`, every
position's weeks; `dim_player.draft_pick`). Like cal1.0 they move the house leagues' rows and their reference
ranges, not the stat line: on-demand leagues (priced from the line at request time) would not see them — the
request side and the record would disagree for exactly the players the prior moves (IB-0's class of bug) — and
dbt's `assert_projection_ranges_price_the_lines` (warn) would flag the moved rows. So the cold-start prior is kept by
the harness but **not ready to switch on as wired**: it belongs on the stat line (scale the line's components by the
blended / raw points of a reference scoring before `nfl_lines`, so `ops.projection_lines` and every request carry
it), which is a v3.1 change for the PO to schedule. What it would do to the 2026 board as wired (the main database,
read-only, weeks 5–18; weeks 1–4 are frozen): 2,754 of 19,822 QB–TE rows move, 120 players — mean −1.6 (RB) /
−0.9 (TE) / −1.8 (WR) a week in the dynasty, from −8.6 to +5.5; e.g. Germie Bernard (WR, pick 47, one game) 9.93 → 4.85,
Jordyn Tyson (WR, pick 8, no game yet) 6.08 → 8.42, rookie TEs 3.7–3.8 → 2.7. Turning any switch on is
a model change (v3.1): the PO's call, with the version bump.

## Expected-value pricing (ev1.0, Wave I-C M2, 2026-10-03; `league_lab.scoring_ev`, seed `scoring_distributions`)

**Why.** A projected line is a set of means. A linear rule (points per yard, per catch, per TD) prices a mean
exactly. A flat bonus does not: "+10 at 100 rushing yards" on a projected 85-yard line pays nothing all or nothing,
yet that back crosses 100 in about one game in three (P = 0.33). Its expected value is 10 × P(yards ≥ 100 | 85). A TD
paid by distance (MFL 70587: 6 / 9 / 12 for 0–9 / 10–39 / 40+ yards) is the same problem: the line projects TDs, not
their lengths. MFL's "1 point per 10 yards" pays per *whole* 10, so its expectation is below the linear price.
`scoring_ev` holds the distributions that turn these rules into expected points. They are fitted offline and kept
as constants in the module (no database, no refit at import); `seed_rows()` writes `dbt/seeds/scoring_distributions.csv`
from them, and `tests/test_scoring_ev.py` pins the two equal. `scoring_ev_fit.run_fit()` refits both (about 6 CPU-minutes; the fit lives in its own module so the
server's import closure never names the play table — `scripts/hosted_relations.py`).

**Threshold curves** (`prob_at_least(stat, position, mean, threshold)`, `prob_in_band`, `expected_band_points`).
P(stat ≥ t in one game | the projection's mean), for passing / rushing / receiving yards and receptions. Two
families, both monotone in the mean by construction:

* *gamma* (rushing and receiving yards, receptions): m′ = scale × mean, shape k = k0 + k1 × m′, scale θ = m′ / k,
  P(X ≥ t) = Q(k, (t − 0.5) / θ). The 0.5 is the continuity correction of an integer stat. Shape and scale both rise
  with the mean (k0, k1 ≥ 0), and a gamma is stochastically increasing in both. The relative spread falls as
  1 / √(k1 × m′): a big projection is relatively less noisy.
* *normal* (passing yards): μ = scale × mean, sd = sd0 + sd1 × μ, P = Φ((μ − t + 0.5) / sd). Its derivative in the
  mean is proportional to sd0 + sd1 × t > 0. The fit puts sd at a flat 79 yards.

Each curve is fitted per position × stat on the walk-forward out-of-sample lines (`calibration.oof_rows(lines=True)`:
the production model, fitted on 2016..S−1, projecting S = 2019–2025; 39,622 played player-weeks). The fit minimises
the log loss of 1{actual ≥ t} over the thresholds leagues use (passing 150–400; rushing and receiving 25–200;
receptions 2–12). The curve is fitted to exactly what it prices. A position × stat with fewer than 1,500 rows
(TE rushing, QB receiving) takes the pooled curve. It replaces M1's isotonic curves (`calibration.fit_bonus_curves`),
which exist only at fixed thresholds and need the fitting rows at run time.

The two were compared on 2023–2025, each fitted on 2019–2022, by log loss summed over the thresholds (lower is
better). Gamma against isotonic: QB rushing 0.742 vs 0.777, RB rushing 1.553 vs 1.581, RB receiving 0.622 vs 0.625,
WR receiving 1.620 vs 1.620, TE receiving 1.063 vs 1.069, receptions RB 1.884 vs 1.894, WR 2.579 vs 2.579 and
TE 2.292 vs 2.307. For QB passing the normal scores 2.004, against 2.059 for a gamma and 2.010 for isotonic. A gamma
puts a 400-yard game at 3.4%, the normal at 1.7%; 0.9% happened. Mean predicted against observed (2023–2025, fitted
earlier):

| | RB rush ≥ 100 | WR rec ≥ 100 | WR rec ≥ 75 | TE rec ≥ 100 | QB pass ≥ 250 | QB pass ≥ 300 |
|---|---|---|---|---|---|---|
| all rows | 0.068 / 0.064 | 0.066 / 0.063 | 0.135 / 0.134 | 0.017 / 0.015 | 0.310 / 0.297 | 0.155 / 0.127 |
| top eighth of the projection | 0.248 / 0.235 | 0.234 / 0.239 | 0.414 / 0.436 | 0.077 / 0.072 | 0.599 / 0.565 | 0.358 / 0.292 |

QB passing bonuses come out about 20% high in 2023–2025, at every window length tried (2, 3 or every earlier
season). This is not the curve: passing in that era fell below what the QB lines project, so the QB projection runs
high (M1: the Scrubs top 6 are −0.98).

**TD distances** (`td_distance_share(family, position, low, high)`, `td_survival`, `expected_td_distance_points`).
The clone has no `raw.nfl_pbp`, but `analytics.fct_play` has every play of 2016–2026 with `yards_gained` and the TD
flags, so **the 10-yard split is measured, not a placeholder.** Distance is `yards_gained` of the scoring play (a
pass: air + run after the catch), the definition dbt uses for `*_tds_40p` (`int_player_game_pbp.sql`). With it, the
2019–2025 counts reproduce `fct_player_game`'s exactly: 5,632 receiving and 3,462 rushing TDs, and 673 / 397
receiving TDs of 40+ / 50+ and 213 rushing TDs of 40+. Return and defensive TDs take the return yards from nflverse's play description ("… for 61 yards,
TOUCHDOWN"; 0 for a recovery in the end zone). Survival shares S(d) are stored at 5, 10, 20, 30, 40, 50, 60, 70 and
80 yards, log-linear between knots (to 0 at 110). A position with n < 100 TDs is shrunk toward its family's pooled
share by (n × own + 30 × pooled) / (n + 30) ("shrunk"). Missed field goals returned (1 TD in 7 seasons) take the
kick-return shares ("proxy"). The spec's pooled families are there too: `return_tds` (kick and punt returns,
103 TDs) and `def_tds` (interception, fumble and blocked or missed kick returns, 430 TDs). So is `fg_made`, made field
goals by distance from `fct_player_game`'s buckets (6,170 makes; exact at 20 / 30 / 40 / 50 / 60 yards). The K line
projects makes by bucket up to 50+, so this splits 50–59 from 60+ and prices a made FG of unknown length. MFL's
event codes PS RS RC KO PR IR DR BF BP MF FG are accepted as the family. Regular seasons 2019–2025:

| Family | Position | TDs | ≥ 10 yd | ≥ 20 | ≥ 40 | ≥ 50 | median yd |
|---|---|---|---|---|---|---|---|
| passing | QB | 5,583 | 0.547 | 0.314 | 0.120 | 0.071 | 11 |
| receiving | WR | 3,476 | 0.604 | 0.387 | 0.166 | 0.098 | 13 |
| receiving | TE | 1,418 | 0.432 | 0.182 | 0.035 | 0.018 | 8 |
| receiving | RB | 664 | 0.536 | 0.248 | 0.068 | 0.048 | 10 |
| receiving | all | 5,632 | 0.548 | 0.315 | 0.119 | 0.070 | 11 |
| rushing | RB | 2,549 | 0.258 | 0.141 | 0.071 | 0.047 | 3 |
| rushing | QB | 714 | 0.216 | 0.067 | 0.021 | 0.010 | 3 |
| rushing | WR | 126 | 0.595 | 0.294 | 0.103 | 0.048 | 14.5 |
| rushing | all | 3,462 | 0.259 | 0.131 | 0.062 | 0.039 | 3 |
| interception return | DEF | 247 | 0.960 | 0.874 | 0.494 | 0.360 | 39 |
| fumble return | DEF | 149 | 0.711 | 0.597 | 0.309 | 0.215 | 27 |
| blocked punt / FG return | DEF | 33 | 0.697 | 0.545 | 0.303 | 0.273 | 21 |
| punt return | all | 54 | 0.926 | 0.926 | 0.907 | 0.870 | 75 |
| kick return | all | 49 | 0.939 | 0.939 | 0.939 | 0.837 | 99 |
| all defensive returns (`def_tds`) | DEF | 430 | 0.853 | 0.753 | 0.416 | 0.305 | — |
| made field goals (`fg_made`) | K | 6,170 | 1.000 | 0.996 | 0.433 | 0.162 | — (≥ 60: 0.005) |

The plan's fallback constants were close for receiving (≥ 10: 0.55, ≥ 40: 0.12) but high for rushing (0.35 against
0.26 measured) and for passing (0.60 / 0.14 against 0.55 / 0.12). Under 70587's 6 / 9 / 12, one expected TD is worth
6.99 for an RB's rush, 8.31 for a WR's catch, 7.42 for a TE's catch, 8.00 for a QB's pass and 10.36 for an
interception return. Its FG bands (0–39 / 40–49 / 50–59 / 60+ = 3 / 5 / 10 / 15) split made kicks
0.567 / 0.271 / 0.157 / 0.005, which is 4.70 points per made FG of unknown length.

**Per whole unit** (`expected_floor_units(stat, position, mean, per, start=0)`). MFL's `1/10` is
E[floor((X − start) / per)] = Σ_j P(X ≥ start + j × per). The linear price is high by about the expected remainder.
For an RB projected 85 rushing yards it is 8.20 points, against 8.50 linear. For a TE projected 35 receiving yards it
is 3.03 against 3.50, and for a QB projected 250 passing yards at 1 per 20 it is 11.76 against 12.50 (the curve's
scale of 0.98 included).

**Does it help.** The test re-prices the walk-forward projected lines in Forever Unclean Dynasty's scoring (3 / 6 at
100 / 200 rushing and receiving yards and 300 / 400 passing, 2 per 40+ TD). Before is the production price: bonuses
all or nothing on the projected line, 40+ TDs 0. After uses expected bonuses and the expected 40+ TD bonus,
projected TDs × S(40). The curves and shares for season S are fitted only on seasons before S. Actual is the league's
points from the outcome line plus the 40+ TD bonuses from `fct_player_game` (2-point conversions are in neither).
The rank is by each price within the week × position. 2023–2025:

| Position | Bucket | n | Bias before | Bias after | MAE before | MAE after |
|---|---|---|---|---|---|---|
| QB | top 6 | 324 | +0.07 | −1.39 | 9.02 | 9.11 |
| QB | 7–12 | 324 | +0.82 | −0.57 | 9.14 | 9.19 |
| QB | 13–24 | 648 | +1.24 | +0.45 | 8.31 | 8.38 |
| QB | 25+ | 725 | +0.58 | +0.23 | 6.27 | 6.23 |
| RB | top 6 | 324 | +1.34 | +0.31 | 8.09 | 8.17 |
| RB | 7–12 | 324 | +1.29 | +0.93 | 6.95 | 6.96 |
| RB | 13–24 | 648 | +1.40 | +0.83 | 6.38 | 6.35 |
| RB | 25+ | 3,199 | −0.24 | −0.34 | 3.77 | 3.79 |
| WR | top 6 | 324 | +1.65 | +0.70 | 8.66 | 8.91 |
| WR | 7–12 | 324 | +0.31 | −0.63 | 7.56 | 7.38 |
| WR | 13–24 | 648 | +0.82 | +0.27 | 7.30 | 7.37 |
| WR | 25+ | 5,818 | −0.22 | −0.39 | 4.19 | 4.23 |
| TE | top 6 | 324 | +0.91 | +0.65 | 6.30 | 6.34 |
| TE | 7–12 | 324 | +0.41 | +0.07 | 5.15 | 5.08 |
| TE | 13–24 | 648 | +0.80 | +0.80 | 4.46 | 4.50 |
| TE | 25+ | 2,370 | −0.03 | −0.05 | 2.64 | 2.64 |

Over all rows, bias goes QB +0.75 → −0.09, RB +0.22 → −0.03, WR −0.02 → −0.29 and TE +0.24 → +0.17. MAE goes
+0.01 to +0.03 and Spearman moves by ±0.001. With M1's definition of actual (no 40+ bonuses), the top 6 reproduce
M1's numbers: RB +1.19 → +0.31 (isotonic +0.42) and WR +1.43 → +0.65 (isotonic +0.61). The expected bonus per row
matches what was paid (expected / realized, yardage bonuses):

| | QB | RB | WR | TE |
|---|---|---|---|---|
| yardage bonuses | 0.547 / 0.416 | 0.217 / 0.203 | 0.205 / 0.193 | 0.053 / 0.045 |
| 40+ TD bonus | 0.297 / 0.275 | 0.041 / 0.050 | 0.076 / 0.065 | 0.013 / 0.012 |
| before (all or nothing) | 0.007 | 0.007 | 0.004 | 0.000 |

The all-or-nothing price pays almost no bonus at all, because a projected line rarely reaches 100 yards.

*Season totals* add up each player-season's played weeks, the sum rest of season and trades use. The rank is by
each projected total within the season × position. 2023–2025:

| Position | Bucket | n | Bias before | Bias after | MAE before | MAE after |
|---|---|---|---|---|---|---|
| QB | top 6 | 18 | +30.4 | +7.8 | 48.0 | 42.3 |
| QB | 7–12 | 18 | +19.9 | +0.1 | 44.3 | 40.4 |
| QB | 13–24 | 36 | +19.1 | +4.8 | 41.4 | 39.9 |
| QB | all | 243 | +6.2 | −0.7 | 24.1 | 23.3 |
| RB | top 6 | 18 | +45.3 | +32.1 | 57.0 | 55.3 |
| RB | 7–12 | 18 | +32.6 | +27.5 | 38.6 | 33.7 |
| RB | 13–24 | 36 | +26.7 | +16.7 | 36.9 | 31.0 |
| RB | all | 455 | +2.1 | −0.3 | 17.6 | 16.9 |
| WR | top 6 | 18 | +38.5 | +22.4 | 56.6 | 52.4 |
| WR | 7–12 | 18 | +18.1 | +6.0 | 35.0 | 35.8 |
| WR | 13–24 | 36 | +20.2 | +10.5 | 31.1 | 27.8 |
| WR | all | 687 | −0.2 | −3.0 | 18.4 | 18.3 |
| TE | top 6 | 18 | +28.6 | +24.3 | 39.8 | 37.8 |
| TE | 7–12 | 18 | +8.6 | +6.4 | 29.8 | 29.2 |
| TE | 13–24 | 36 | +15.6 | +12.2 | 25.9 | 23.5 |
| TE | all | 381 | +2.3 | +1.7 | 12.8 | 12.6 |

The large positive bias of the top buckets is a selection effect of ranking by a projected total: the totals with
the most played weeks, and players who beat their line, end up on top. It is the same before and after.

*A 70587-style scoring.* The same rows were priced in a scoring built like dad's league: TDs 6 / 9 / 12 by distance;
yards 1 per 10, QB passing 1 per 20; +10 at 100 rushing, 100 receiving (TE 75) and 250 passing (QB); INT −3; fumble
lost −3; no point per catch. Actual applies MFL's whole-10 rule and the real TD distances (`fct_play`). The flat
price is TDs at 6 with all-or-nothing bonuses. The placeholder price uses the plan's fallback shares. EV uses the
curves, the measured shares and linear yards. EV + floor adds `expected_floor_units`. Weekly bias / MAE, and season
total MAE, over all rows, 2023–2025:

| Position | Flat | Placeholder | EV | EV + floor | Season MAE flat → EV + floor |
|---|---|---|---|---|---|
| QB | +2.63 / 11.39 | −0.09 / 11.49 | −0.87 / 11.26 | −0.09 / 11.22 | 39.9 → 33.3 |
| RB | +0.36 / 5.09 | −0.05 / 5.19 | −0.65 / 5.31 | +0.06 / 5.04 | 21.4 → 18.5 |
| WR | +0.53 / 4.69 | +0.10 / 4.82 | −0.61 / 5.02 | −0.14 / 4.82 | 20.8 → 18.4 |
| TE | +0.45 / 3.30 | +0.16 / 3.40 | −0.23 / 3.50 | +0.20 / 3.32 | 13.9 → 12.3 |

**Decision (for the PO).** Turn EV pricing on for projected lines in every league whose rules have flat bonuses,
distance-banded TDs or whole-unit rates. A league without them prices exactly as before. The reasons:

* Season totals improve at every position. In dynasty, MAE per player-season goes −0.8 QB, −0.7 RB, −0.1 WR and
  −0.2 TE, and −0.6 to −5.9 in 11 of the 12 top-24 buckets (WR 7–12: +0.8). In a 70587-style league it goes −1.6
  to −6.6 against flat.
* The top-6 weekly bias falls from +1.34 / +1.65 / +0.91 to +0.31 / +0.70 / +0.65 (RB / WR / TE).
* Weekly start/sit is unaffected: Spearman ±0.001, and weekly MAE +0.01 to +0.03. A mean is not a median, so the
  MAE of a skewed bonus does not improve.

The one cost is the QB top 6, whose weekly bias goes from +0.07 to −1.39. The all-or-nothing price was hiding the
QB line's own over-projection behind a missing bonus. The fix belongs in the QB model (M1's v3.1 list), not in a
bonus priced at 0.

**Not covered.** 2-point conversions are not projected. Return TDs are not projected: their shares exist for a
league's actual lines and a team defense's rules, but no line projects them. Kickers' FG distance bands stay in
`kdef`. The curves are conditional on the production model (v3.0): a new model version needs `scoring_ev_fit.run_fit()` (the
seed's `version` changes).

### On the nightly (Wave I-D, M3, 2026-10-03; `scoring.price_projected`, flag `LEAGUE_LAB_EV_PRICING`, off)

**One entry point.** `scoring.price_projected(stats, scoring, position=None, *, ev=None)` prices every projected
stat line, on both sides: `projections.price(..., "proj_")` (the nightly: `predict_position`'s `proj_points` and the
ranges' anchor, `_oof_lines`, `house_rows`, the harness, signals' what-ifs) and `anyleague.price_lines` (My Week,
Waivers, Trades, rest of season, team units), plus the on-demand larger-role what-if (`decisions`). Actual lines
(`out_`) stay on `compute_points`: a bonus on an actual line happened or it did not. The engine:

* an MFL spec: `expected_frame(ev=True)`, always (unchanged);
* a Sleeper scoring, flag off (the default): the flat engine (`compute_points_frame`) — the pre-wave numbers to the bit;
* a Sleeper scoring, flag on, with a yardage or long-TD bonus (`ev_moves`): `expected_frame(ev=True)` on the spec of
  `projected_view(scoring)` — the flat engine's keys only, sorted, so only HOW a bonus is priced changes, never which
  keys count, and a house league prices exactly as the reference it is (`house_rows` checks it every night);
* a Sleeper scoring, flag on, with no such bonus (Scrubs, the Test League, ppr / standard / te_premium): the flat
  engine — unchanged to the bit by construction.

The flag is read at call time in each process: the nightly and the API must carry the same value.

**The ranges.** The P10 … P90 residual models are fitted around the priced line (`_quantile_features`). Under the flag
the anchor moves by the expected bonus, and `project` refits every residual model on the new anchor every night, so
the ranges are consistent after one nightly. Weeks already kicked off keep their stored rows and ranges (B5).

**The harness, both ways.** `calibration.oof_rows` (ranges and lines; the walk-forward of `backtest-v2`, kept per
row, because the rank buckets and the season totals need the rows), 2023–2025, both house leagues, one run per flag
state (17.5 minutes each on two cores). Flag off, its weekly scores reproduce all 432 stored v3.0 cells of
`ops.projection_backtest` exactly (Spearman, hit rate, MAE, 80% coverage). Flag on, **Scrubs is identical to the bit
in every column** (projection, P10 … P90, actual) and the stat lines are identical in both runs. The dynasty, with
actual = the 12 components priced + the 40+ TD bonuses Sleeper pays (`fct_player_game`; the harness's own actual
omits them, see below):

| Position | Spearman | Top-N hit rate | Weekly MAE | 80% coverage | 50% coverage |
|---|---|---|---|---|---|
| QB | 0.576 → 0.578 | 0.517 → 0.522 | 7.820 → 7.845 | 0.753 → 0.753 | 0.456 → 0.463 |
| RB | 0.692 → 0.692 | 0.645 → 0.643 | 4.685 → 4.707 | 0.799 → 0.803 | 0.511 → 0.519 |
| WR | 0.636 → 0.636 | 0.485 → 0.485 | 4.834 → 4.875 | 0.805 → 0.807 | 0.501 → 0.495 |
| TE | 0.596 → 0.596 | 0.474 → 0.469 | 3.504 → 3.511 | 0.813 → 0.813 | 0.517 → 0.517 |

Bias (actual − projected) and MAE by rank bucket within the week, and per player-season (the totals rest of season
and trades use; ranked by projected total within the season × position):

| Position | Bucket | n | Weekly bias | Weekly MAE | Seasons | Season bias | Season MAE |
|---|---|---|---|---|---|---|---|
| QB | top 6 | 324 | +0.07 → −1.29 | 9.02 → 9.10 | 18 | +30.4 → +9.0 | 48.0 → 42.4 |
| QB | 7–12 | 324 | +0.82 → −0.54 | 9.14 → 9.19 | 18 | +19.9 → +1.1 | 44.3 → 40.4 |
| QB | 13–24 | 648 | +1.24 → +0.45 | 8.31 → 8.34 | 36 | +19.1 → +5.5 | 41.4 → 39.8 |
| QB | 25+ | 725 | +0.58 → +0.29 | 6.27 → 6.26 | 171 | −0.4 → −2.7 | 15.8 → 16.0 |
| QB | all | | | | 243 | +6.2 → −0.4 | 24.1 → 23.3 |
| RB | top 6 | 324 | +1.34 → +0.36 | 8.09 → 8.12 | 18 | +45.3 → +32.2 | 57.0 → 55.3 |
| RB | 7–12 | 324 | +1.29 → +0.89 | 6.95 → 7.00 | 18 | +32.6 → +27.6 | 38.6 → 33.7 |
| RB | 13–24 | 648 | +1.40 → +0.84 | 6.38 → 6.35 | 36 | +26.7 → +16.8 | 36.9 → 31.0 |
| RB | 25+ | 3,199 | −0.24 → −0.34 | 3.77 → 3.79 | 383 | −3.6 → −4.8 | 13.0 → 13.0 |
| RB | all | | | | 455 | +2.1 → −0.3 | 17.6 → 16.9 |
| WR | top 6 | 324 | +1.65 → +0.74 | 8.66 → 8.90 | 18 | +38.5 → +23.0 | 56.6 → 52.4 |
| WR | 7–12 | 324 | +0.31 → −0.60 | 7.56 → 7.38 | 18 | +18.1 → +6.5 | 35.0 → 35.8 |
| WR | 13–24 | 648 | +0.82 → +0.29 | 7.30 → 7.38 | 36 | +20.2 → +10.9 | 31.1 → 27.9 |
| WR | 25+ | 5,818 | −0.22 → −0.38 | 4.19 → 4.23 | 615 | −3.0 → −4.7 | 16.1 → 16.2 |
| WR | all | | | | 687 | −0.2 → −2.9 | 18.4 → 18.3 |
| TE | top 6 | 324 | +0.91 → +0.65 | 6.30 → 6.34 | 18 | +28.6 → +24.2 | 39.8 → 37.8 |
| TE | 7–12 | 324 | +0.41 → +0.14 | 5.15 → 5.14 | 18 | +8.6 → +6.5 | 29.8 → 29.2 |
| TE | 13–24 | 648 | +0.80 → +0.77 | 4.46 → 4.47 | 36 | +15.6 → +12.3 | 25.9 → 23.5 |
| TE | 25+ | 2,370 | −0.03 → −0.05 | 2.64 → 2.64 | 309 | −1.2 → −1.1 | 8.7 → 8.9 |
| TE | all | | | | 381 | +2.3 → +1.7 | 12.8 → 12.6 |

Read: the season totals improve at every position (MAE −0.8 QB, −0.7 RB, −0.1 WR, −0.2 TE) and in 11 of the 12
top-24 buckets (WR 7–12 +0.8); the top-6 weekly bias falls RB +1.34 → +0.36, WR +1.65 → +0.74, TE +0.91 → +0.65;
both ranges hold their coverage (80%: 0.753–0.813, ±0.004; 50%: ±0.008); weekly start/sit is unchanged (Spearman
±0.002, hit rate ±0.005, weekly MAE +0.007 to +0.041). The QB top 6 goes +0.07 → −1.29, as M2 found: the QB line's
own over-projection (M1's v3.1 list), no longer hidden behind an unpaid bonus. With the harness's own actual (no 40+
TD bonus) the story is the same: top-6 bias RB +1.19 → +0.21, WR +1.43 → +0.51, QB −0.34 → −1.67; coverage 80%
0.758–0.813 → 0.759–0.813. These match M2's walk-forward (RB +0.31, WR +0.70, QB −1.39) within 0.1 although
`scoring_ev`'s constants were fitted on 2019–2025, i.e. in sample for these seasons: the in-sample curves do not
flatter the result.

**On the week-4 board** (the clone's `ops.projection_lines`): Scrubs moves 0 of 8,134 player-weeks (weeks 4–18). The
dynasty moves 8,037 of 8,134, by at most 1.63; the top 24 per position in week 5 by QB +1.01, RB +0.71, WR +0.73,
TE +0.18 a week (96 players: +0.66; none down), rest of season (weeks 5–18) for the top 24 by QB +11.9, RB +8.5,
WR +9.8, TE +2.4. A line projected past a threshold moves down: in week 4 two of the top 96 (Bijan Robinson
26.72 → 25.52 — a 100+ rushing-yard projection the all-or-nothing price paid in full). Josh Allen, week 4:
30.24 → 31.68.

**Not covered.** The residual models learn from the harness's actual, which carries no 40+ TD bonus (the outcome
columns of `mart_player_week_features` have no long-TD count): the ranges of a long-TD scoring sit below what Sleeper
pays by the bonus's average, 0.01 (TE) to 0.3 (QB) a game (both flag states; v3.1: price the actual's long TDs). K / DEF stay flat (`kdef`).
`dbt`'s `assert_projection_ranges_price_the_lines` (warn) re-prices the dynasty reference with the SQL macro (all
or nothing): with the flag on it warns on every dynasty row, by design, until it is limited to the scorings
`ev_moves` leaves flat. Sleeper's own projection in the record (`mart_projection_record`, `why`'s "Sleeper's
projection") is still priced all or nothing.

### The record's pricing column (Wave I-G, M4, 2026-10-04; `scoring.pricing_mode`, `ops.projections.pricing`)

**The column.** `pricing` (text, nullable) on `ops.projections`, `ops.projection_ranges` and `ops.projection_backtest`
says how a row's bonuses were priced: `flat` (all or nothing on the projected line) or `ev` (at their odds). The writer
sets it from `pricing_engine(scoring)` under the build's mode, with `spec` mapped to `ev` because an MFL spec is always
priced in expectation. K and DEF rows are always `flat` (`kdef`). A row written before the column existed is NULL,
which means flat. A frozen week keeps its rows and therefore its label. A range unit copied from the record keeps the
record's label. The writers add the column themselves (`add column if not exists`, also in `db migrate` and the two
marts' pre-hooks), so the hosted restore carries it. `mart_player_week_projections.pricing` carries the row's label.
`mart_projection_record.pricing` gives one label per league × week (every QB–TE row of a league-week is written by
one build), `mixed` if a week ever has two. A season row gets the scored weeks' label, or `mixed` when they differ.

**The mode.** `scoring.ev_pricing()`, M3's flag, is now a mode, resolved in this order:

1. The nightly writer's pinned mode. `projections.project` and `backtest` run under `pinned_pricing()`, which uses
   the env alone and defaults to flat. The writer never follows the record it is writing. So a rollback is "unset
   the env and re-run the nightly", and EV cannot keep itself on.
2. `LEAGUE_LAB_EV_PRICING` when it is set and non-empty. This is an override in either direction: `1` / `true` /
   `yes` / `on` means EV, anything else means flat.
3. The newest build in `ops.projections`: EV when any QB–TE row of the newest `fitted_at` says `ev`. Only Sleeper
   leagues count, because an MFL spec's `ev` says nothing about the build's mode.
4. Otherwise flat.

The record is read with one query (`RECORD_PRICING_SQL`), cached ten minutes per process. A failure (no database,
or no column before the first Wave I-G nightly) gives flat and is cached for a minute. The API reads the record
through its read-only `db.query`. The console and the CLI read it through `league_lab`'s connection, app role first.

`scoring.ev_for_week(season, week)` prices one week's lines. A week the record holds is priced as its rows were. A
week the record does not hold is priced as the newest build. `anyleague.price_lines` uses it per row: the frame's
`season` / `week`, or the board's week (`price_board`), or the record's newest season for a window frame that has
weeks but no season. `price_week`'s cache key carries the mode. `why.market_points` uses it for Sleeper's line.

**So the two sides agree by construction.** My Week, Waivers, Trades, rest of season and the player card price at
request time. Trends, the house board and the record were priced by the nightly. Both now use the same mode for the
same week. **Render needs no env change. The flip is the nightly's env alone**: `LEAGUE_LAB_EV_PRICING: "1"` in
`.github/workflows/nightly.yml`.

**The morning the record is half flat and half EV.** Take the first nightly after the flip, run during week 4.
Week 4 kicked off under flat and is frozen (B5): its rows stay flat and keep the label. Weeks 5–18 are rewritten
under EV. On the request side, from that nightly on:

* the newest build wins for every week it wrote;
* the frozen week is priced by its own label (week 4 stays flat on My Week and on the board alike);
* a frame with no week is priced as the newest build.

There is no window in which one side has flipped and the other has not. Rolling back works the same way in
reverse: weeks that kicked off under EV keep `ev`.

**Measured on the M4 clone** (`league_lab_m1`; `project` with the env on, against the flat build before it):

* Scrubs: 0 of 9,911 player-weeks moved, and 0 of 180 lineup totals.
* The dynasty: 7,464 of 9,911 player-weeks moved, all of them in weeks 5–18, by −1.26 to +1.63. Week 4 is
  unchanged because it is frozen. Lineup totals in weeks 5–18 rose by +4.97 per roster-week on average; Andrew's
  roster 12 went from 118.12 to 123.24 in week 5 and stayed at 111.15 in week 4.
* Under the record's mode, the week-5 top 24 moved as M3 measured: QB +1.01, RB +0.71, WR +0.73, TE +0.18
  (96 players, +0.66 on average, none down). Josh Allen in week 4 is 30.24 under the frozen flat label and 31.68
  priced at the odds; in week 5 he went from 22.85 to 23.76.
* The scenarios' base reproduces the stored projection to 0 under EV once the position rides along (`signals.py`,
  below).

**"Sleeper's projection"** (`why.market_points`: the card, rest of season, My Week, the Finder's market sanity bound)
is priced like ours. It goes through `price_projected` in the week's mode, and a K stays flat. In flat mode it gives
the pre-I-G number to the cent. Josh Allen's week-4 line (the fixture's invented line: 267 passing yards, 2.0 passing
TDs) in the dynasty is 31.58 flat and 33.20 at the odds (+1.62). Ours moves +1.44, so the ratio barely changes
(0.958 → 0.954). In Scrubs it is 25.50 both ways. In EV mode a long-TD bonus on Sleeper's line is priced the way
ours is: Sleeper's projected TDs × the measured share that long. Sleeper's own `*_tds_40p` columns are not used.

**Not covered.** The record's Sleeper side (`mart_projection_record.sl_priced`) is still the SQL macro, which pays a
bonus all or nothing. In an EV week ours is priced at the odds and Sleeper's is not. M2's measurements put the
effect at about ±0.02 on MAE and ±0.002 on Spearman. A few close start/sit calls could flip. The proposal for the PO:
a Python-priced `ops.market_record`, written by `project` for the league-weeks labelled `ev` (the pre-kickoff
snapshot already exists by then), coalesced in `sl_priced`. That change needs a `sources.yml` row.
`ops.projection_backtest` is rewritten only when the model version changes, so its v3.0 rows stay NULL, which means
flat, after the flip. Their numbers were priced flat, so the label is true.

**Found on the way.** `signals.scenarios` priced the scenario base without the position. Under EV the base then
used the pooled curves and missed the stored projection by 0.04. The scenario step failed (logged) and kept
yesterday's flat rows. The projection-marts step's test `scenario_base_is_the_projection` would then have failed the
first nightly after the flip. The position now rides along, as it does in `predict_position`. In flat mode nothing
moves, because the house leagues have no position premium.

## Deferred (status in registry)

| Metric | Status | What it needs |
|---|---|---|
| routes (licensed), TPRR, YPRR without the proxy label | unavailable until imported | a provider CSV through `league-lab import-routes`; **never** derived from snaps or targets |
| in-season routes proxy | unavailable in-season | the NFL publishes participation after the postseason |

## Versioning

Bump the `version` in `metric_registry.csv` when a definition changes; the explorer shows the
registry on the Data Status page. Old versions are not recomputed retroactively unless the change
is a bug fix, in which case say so in `STATUS.md`.
