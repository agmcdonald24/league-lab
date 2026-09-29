# Data model

Lineage: `raw` (loaded by Python, one partition per transaction) → `staging` (views, renames and
typing only) → `intermediate` (identity resolution, snaps mapping, dedup) → `analytics` (tested
marts the explorer reads). `analytics_seeds` holds the scoring map and metric registry;
`ops` holds the load manifest. The explorer's role can only `SELECT` from `analytics`,
`analytics_seeds` and `ops`.

## raw (schema `raw`)

| Table | Partition (replaced atomically) | Key | Notes |
|---|---|---|---|
| `sleeper_league` | league_id | league_id | full payload + promoted settings |
| `sleeper_league_user` | league_id | league_id, user_id | |
| `sleeper_roster` | league_id | league_id, roster_id | players/starters/reserve as text[] |
| `sleeper_matchup` | league_id, week | league_id, week, roster_id | `players_points` jsonb, `starters_points` numeric[] |
| `sleeper_transaction` | league_id, week | league_id, transaction_id | adds/drops jsonb |
| `sleeper_draft` / `sleeper_draft_pick` | league_id / draft_id | draft_id / draft_id, pick_no | |
| `sleeper_traded_pick`, `sleeper_bracket` | league_id | see DDL | |
| `sleeper_player` | all | player_id | Sleeper directory incl. its own `gsis_id` |
| `sleeper_state` | sport | sport | current NFL week/season |
| `nfl_player_stats_week` | season | player_id, season, week | all 150 upstream columns |
| `nfl_team_stats_week` | season | team, season, week | |
| `nfl_rosters_weekly` | season | (gsis_id, season, week) — not unique upstream | dedup in intermediate |
| `nfl_snap_counts` | season | pfr_player_id, game_id | |
| `nfl_schedules` | all (seasons ≥ start) | game_id | |
| `nfl_players`, `nfl_teams`, `nfl_ff_playerids` | all | gsis_id / team_abbr / — | |
| `nfl_pbp` | season | game_id, play_id | nflfastR play-by-play, core subset (~190 of ~370 columns; `LEAGUE_LAB_PBP_COLUMNS=all` loads every column; the archived parquet keeps all). ~48k plays/season, 751 MB for 2016–2026 |
| `nfl_pbp_participation` | season | nflverse_game_id, play_id | players on the field per play (`offense_players` / `defense_players` as `;`-lists). 2016 → last completed season (published after the postseason). 321 MB |
| `nfl_ftn_charting` | season | nflverse_game_id, nflverse_play_id | FTN Data charting 2022+ (read_thrown, throwaway, drop, play action, RPO, motion, …). CC-BY-SA 4.0. 23 MB |
| `routes_feed` | provider, season | season, week, one of gsis_id/sleeper_id/pfr_id, provider | licensed routes import contract (`league-lab import-routes`), empty until used |

Every raw nfl table carries `_fetched_at`; every Sleeper table carries `payload jsonb` and
`fetched_at`. Column types are derived from the source file and widened (never narrowed) when a
later season's file changes type.

## ops

`ops.load_manifest` — one row per attempted partition load: source, dataset, partition_key,
source_url, source_last_modified, source_etag, fetched_at, checksum_sha256, schema_fingerprint,
row_count, status (`success` | `failed` | `skipped_unchanged` | `contract_failed`), error,
code_version, file_path, started_at, finished_at.

`ops.source_partition` — current state per (source, dataset, partition_key): last successful
load, checksum, ETag, rows, loaded_at. Used to skip unchanged content.

`ops.projection_drift` (M-06) — one row per league_id × season × week × position for played weeks
of the projected season (≥ 8 played, rankable players): n_players, spearman, top_n, hit_rate, mae,
coverage_80, interval_width, games_played / games_scheduled (the week is complete when they are
equal), model_version, run_at. Written by `league-lab drift` and at the end of `league-lab project`
(replaces the season's rows); scored from `mart_player_week_projections`.

## analytics — NFL

| Model | Grain / key | Contract |
|---|---|---|
| `dim_team` | team_abbr | includes historical abbreviations (OAK, SD, STL, LA) |
| `dim_game` | game_id | season, season_type (REG/POST), week, kickoff, teams, scores, `is_final`, `went_to_overtime`, listed starting QBs |
| `dim_player` | gsis_id | canonical player; `latest_team` is not historical; resolved sleeper_id/pfr_id |
| `player_id_map` | gsis_id (unique), sleeper_id (unique) | accepted pairs from ff_playerids ∪ Sleeper directory; ambiguous pairs excluded |
| `player_id_quarantine` | issue, ids | ambiguous pairs, skill players without an NFL id, stat rows without player id, duplicate roster ids |
| `player_team_history` | gsis_id, season, week | historical team + roster status + game_id (null on bye) |
| `fct_team_game` | team, game_id | independent totals: attempts, targets, carries, air yards, `dropbacks_excl_scrambles` |
| `fct_player_game` | gsis_id, game_id | stats + team denominators + snaps + shares + `points_current_scoring`; `played`, `snaps_known` |
| `mart_player_season` | gsis_id, season, season_type | sums first, rates second; `teams`, `team_count`; routes/TPRR/YPRR NULL by design |
| `mart_player_season_team` | + team | per-team split |
| `mart_player_recent_form` | gsis_id, game_id | last-3/last-5 windows with shared denominators, season-to-date |

## analytics — league

| Model | Grain / key | Contract |
|---|---|---|
| `dim_league_season` | league_id (season unique) | scoring version, roster positions, playoff structure, `is_current_season`; `chain_id`, `is_reference_league`, `scoring_diff_vs_reference` (keys that differ from the reference league); `scoring_label` (U-10, not null): one line built in SQL from `num_teams`, `roster_positions`, `league_type` and `scoring_settings` — "12-team superflex dynasty · full PPR · 6-pt pass TD · yardage bonuses" (rec 0 / 0.5 / 1 → standard / half PPR / full PPR, else "x PPR"; `pass_td` → "n-pt pass TD"; any non-zero `bonus_*_yd_*` → yardage bonuses; non-zero `bonus_rec_te` → TE premium x; a SUPER_FLEX slot → superflex, else two QB slots → 2QB) |
| `dim_league_member` | league_id, roster_id | manager/team names, Sleeper-stored record |
| `fct_league_matchup` | league_id, week, roster_id | opponent, result, `is_playoff_week`, `is_scored` |
| `league_player_week` | league_id, week, roster_id, sleeper_player_id | starter flag + slot, `points_observed` (Sleeper), `points_recomputed` (that season's scoring × nflverse) |
| `fct_player_game_league` | league_id, gsis_id, game_id | every `fct_player_game` row × each **current** league-season (S-01a, 2026-09-27): `points` under that league's current scoring (`league_points` over the stats row + long-TD counts, = `league_player_week.points_recomputed` to the cent), `points_expected` (same map, ffverse expected stats, stat keys only), `played`, `position`. ≈369k rows for two leagues. Pipeline-only (no page reads it; not published) |
| `mart_league_player_season` | league_id, gsis_id, season | regular season in the league's own scoring (S-01a): `points`, `ppg`, `points_per_game_l3/_l5` (last 3/5 appearance games), `games_with_expected`, `points_expected`, `expected_per_game`, `diff_per_game`, `position_rank_points/_ppg` (all NFL players at the position). Same arithmetic as `mart_player_season` / `mart_player_recent_form` / `mart_player_expected_season`; the reference league reproduces them exactly |
| `mart_league_standings` | league_id, roster_id | computed vs Sleeper record, lineup efficiency, champion flag |
| `mart_league_kicker_week` / `_summary` | league-week-roster / league-roster | realized started-kicker points, common eligible weeks, changes, acquisitions |
| `mart_league_transactions` | transaction × player × action | |
| `mart_league_draft` | draft_id, pick_no | pick vs season outcome; season points under the chain's **current** scoring (`fct_player_game_league` via `chain_id`) |

## analytics — Manager's Edge (2026-09-26)

| Model | Grain / key | Contract |
|---|---|---|
| `mart_nfl_calendar` | one row | current season, last completed week, next week |
| `mart_player_expected_points` / `_season` | gsis_id, game_id / gsis_id, season | actual vs expected points under current league scoring |
| `mart_defense_vs_position` / `_current` | defense, game_id, position / defense, position | points allowed per game STD and L4 with ranks |
| `mart_defender_coverage_season` | gsis_id, season | PFR coverage stats when targeted |
| `mart_matchup_cb_context` | defense, gsis_id, depth_position | opponent's CBs (latest depth chart) + coverage |
| `mart_player_next_matchup` | gsis_id | next game/bye, opponent DvP rank, injury, depth rank |
| `mart_league_roster_membership` | league_id, sleeper_player_id | who rosters whom now |
| `mart_player_availability` | league_id, gsis_id | rostered-by / free agent × usage × expected gap × next matchup; points columns (`points_std`, `ppg_std`, `points_per_game_l3/_l5`, `expected_per_game`, `diff_per_game`, `games_with_expected`) in the row's league scoring via `mart_league_player_season` (S-01a); usage, shares and opponent ranks are scoring-free or reference-scored |
| `mart_league_optimal_lineup` | league_id, week, roster_id | started vs optimal points, bench points left |
| `mart_league_all_play` / `_week` | league_id, roster_id / + week | all-play record, expected wins, luck |
| `mart_league_keeper_candidates` | league_id, sleeper_player_id | acquisition cost facts + production, ranks and xPPG in the league's own scoring (S-01a) |
| `mart_league_manager_profile` | league_id, roster_id | luck, lineup discipline, activity, roster shape |
| `mart_league_positional_strength` | league_id, roster_id, position | starter ppg vs league median, rank (league's own scoring through availability) |

## analytics — Trends (2026-09-26)

| Model | Grain / key | Contract |
|---|---|---|
| `trend_metrics` (seed) | metric | label, arrow label, practical `min_change`, `is_opportunity`, positions, `display_kind` |
| `int_player_game_metric_long` | gsis_id, game_id, metric | numerator / denominator per player-game-metric (REG, played, QB/RB/WR/TE; metric ↔ position from the seed) |
| `mart_player_trends` | gsis_id, season, metric | `value_l3`, `value_prior`, `value_season`, `value_latest`, per-game means, `sd_game`, `change`, `z`, `slope_per_game`, `direction` (up/down/flat/insufficient), `confidence` |
| `mart_player_trend_tags` | gsis_id, season | `tags`, `n_up`, `n_down`, `momentum`, `opportunity_trend`, pivoted `*_l3` / `*_change` / `*_z` for target share, snap share, carry share, air-yard share, aDOT, expected points, points |
| `mart_defense_trends` | defense, season, position | `allowed_prior`, `allowed_l3`, `allowed_season`, `change`, `z`, `direction` (softer/stiffer/steady/insufficient) |

Consumers: Trends page (`app/pages/3_Trends.py`), Team Hub roster and Waiver Wire (tags + momentum),
weekly packs (Movers, roster trends, free agents with rising opportunity). Definitions in `METRICS.md`.

Identity resolution now has three sources (ff_playerids, Sleeper directory, nflverse weekly rosters'
`sleeper_id`); contested pairs are accepted only when exactly one candidate on each side has matching
provider names (`resolution = accepted_by_name_confirmation`), otherwise quarantined.

## analytics — play-by-play (Phase 2, 2026-09-26)

| Model | Grain / key | Contract |
|---|---|---|
| `fct_play` | game_id, play_id (2016+) | one row per play: eligibility flags (`is_no_play`, `is_dropback`, `is_pass_attempt`, `is_target`, `is_rush_attempt`, `is_sack`, `is_scramble`, `is_two_point`, `is_spike`, `is_kneel`), context (`half`, `score_state`, `down_distance`, `field_zone`, `qb_player_id`), actors, yards, EPA/WPA/CPOE. Indexed on receiver, rusher, QB |
| `bridge_play_actor` | game_id, play_id, role, gsis_id | passer / receiver / rusher / kicker / scorer |
| `bridge_play_participation` | game_id, play_id, gsis_id | offensive players on the field (presence, not routes). 4.9M rows 2016–2025 |
| `fct_play_charting` | game_id, play_id (2022+) | FTN fields + `read_thrown` normalised (first / later / checkdown / designed / scramble_drill / NULL = uncharted) and `is_first_read_target`, `is_designed_target`, `is_charted_target` |
| `int_team_game_pbp` | team, game_id | dropbacks, scrambles, spikes, kneels, two-point tries, targets/carries from plays, red-zone counts, charted / first-read / designed targets, `charting_coverage`, `dropbacks_with_participation`, `participation_coverage` |
| `int_player_game_pbp` | gsis_id, game_id | targets by read, drops / catchable / contested, red-zone and inside-10 counts, deep targets, scrambles, QB dropbacks, `routes_proxy` (receiving positions on covered dropbacks), `participation_known` |
| `int_play_context_long` | play × context dimension | every eligible play once per split (half, score_state, down_distance, field_zone, qb) |
| `mart_player_context` | gsis_id, season, season_type, context_type, bucket | player counts and team denominators inside the bucket over the player's games; shares, TPRR/YPRR proxy |

`fct_team_game` gained `dropbacks`, `scrambles`, `spikes`, `kneels`, `two_point_tries`, `dropback_rate`,
red-zone and charting/participation coverage columns; `fct_player_game` gained `routes_proxy`,
`route_participation`, `tprr_proxy`, `yprr_proxy`, `routes` / `tprr` / `yprr` (licensed feed),
first-read counts and `first_read_target_share`, `charting_coverage`, red-zone / inside-10 / deep
counts, `dropbacks`, `sacks_taken`, `scrambles`. `mart_player_season(_team)` carry the same as season
sums and rates; team denominators are now summed over **appearance games only** (`played`), which
moved a handful of special-teams-only players' shares — the correct direction per plan §5.

## analytics — rankings (Phase 2b, 2026-09-26)

| Model | Grain / key | Contract |
|---|---|---|
| `int_player_game_asof` | gsis_id, game_id | what was known after each played game: STD / L3 / L5 PPG, expected points, shares, snaps, first-read, attempts |
| `int_player_week_universe` | gsis_id, season, week | rostered QB/RB/WR/TE × week the team plays (latest published roster for upcoming weeks), opponent, home, closing line, implied team total |
| `int_player_week_asof_features` | gsis_id, season, week | the player's latest as-of row before the week |
| `int_opponent_week_asof` | season, week, defense, position | opponent points allowed to the position before the week; league average as of the same point |
| `mart_player_week_features` | gsis_id, season, week | raw as-of inputs + finished `f_*` features + previous season + injury report + outcome (`points_actual`, `played`) |
| `ranking_weights` (seed) | position, feature | OLS weights from `league-lab fit-rankings` (train window, n, R², fit date) |
| `mart_player_week_rankings` | gsis_id, season, week | `proj_points`, contributions `c_form / c_usage / c_matchup / c_vegas / c_home / c_intercept`, inputs, naive baselines, `is_rankable`, `rank_pos`, `rank_overall`, `actual_rank_pos` |
| `mart_backtest_summary` (view) | season, position, scorer | from `ops.backtest_results` (written by `league-lab backtest`): Spearman, hit rate, MAE, top-N picked vs ceiling PPG |
| `mart_player_week_projections` | league_id, gsis_id, season, week | projection v2 from `ops.projections` (written by `league-lab project`): projected stat line, `proj_points` in the league's scoring, `p10 / p50 / p90`, `interval_width`, as-of context, the outcome priced under the league's scoring (`points_actual`), `actual_inside_interval`, `rank_pos` (by P50), `actual_rank_pos` |
| `mart_projection_backtest` (view) | league_id, season, position, scorer | from `ops.projection_backtest` (written by `league-lab backtest-v2`): Spearman, hit rate, MAE, `coverage_80`, interval width per walk-forward season |
| `mart_projection_drift` (view, M-06) | league_id, season, position | from `ops.projection_drift`: `weeks_scored`, `first_week` / `last_week`, `week_in_progress`, `player_weeks`, mean `spearman / hit_rate / mae / coverage_80 / interval_width` over **complete** weeks, next to `backtest_spearman / _hit_rate / _mae / _coverage_80 / _interval_width` (`mart_projection_backtest`, scorer `v2_points`, averaged over its held-out seasons; `backtest_seasons`, `backtest_weeks`) |

## analytics — ops views

`mart_data_status` (per source/dataset freshness and failures), `mart_coverage` (per season:
through-game date, games with stats/snaps/pbp/participation/charting, average charting coverage,
league scored weeks, and explicit status text for play-by-play / FTN / participation / routes —
"not published yet" for the current season's participation, "no licensed feed imported" for routes).

## Identity resolution

1. Candidates: (gsis_id, sleeper_id) pairs from `nfl_ff_playerids` and from `sleeper_player.gsis_id`.
2. A pair is accepted only if the gsis_id maps to exactly one sleeper_id **and** vice versa;
   otherwise every involved pair is quarantined.
3. pfr_id comes from `nfl_players` (fallback ff_playerids); snap counts join via pfr_id only when
   the pfr_id maps to exactly one gsis_id.
4. Sleeper entities without an NFL id (team DEF like `KC`, some rookies) keep their sleeper id in
   league marts with `gsis_id` NULL; they never join to NFL stats.

## Scoring

`scoring_stat_map` (seed, generated from `league_lab.scoring`) maps Sleeper keys to nflverse
column expressions, with a `kind`: `stat` rows are `+`-joined weekly-stat columns; `bonus` rows
are either a play-by-play long-touchdown count (`pass_tds_40p` …, joined from
`int_player_game_pbp` onto the stats row by the scoring models) or a per-game threshold
`column:low:high`. The `league_points(scoring_jsonb, alias, include_bonuses=true)` macro builds
`Σ weight × expression`; expected points pass `include_bonuses=false`.
`zero_stat_columns(have)` emits `0 as <col>` for every seed column a relation lacks so a partial line
(a projection, the component outcomes) can be priced with the same macro.
`fct_player_game.points_current_scoring` uses the reference league's newest settings
(cross-year research: every NFL mart, the research pages, defense vs position, trends, the projection
features); `league_player_week.points_recomputed` uses each league-season's own settings (history);
`fct_player_game_league.points` uses each *current* league-season's settings for every NFL game
(league pages: availability, keeper facts, positional strength, draft outcomes — plan S-01a). Approximations are listed in `METRICS.md`. Seeds are always recreated
(`+full_refresh: true`) so a new seed column never needs a manual `--full-refresh`.
