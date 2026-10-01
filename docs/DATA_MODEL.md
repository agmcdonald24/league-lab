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
| `nfl_weather` | source, season, stadium_id | game_id, source, fetched_at | plan D3, `league-lab ingest weather`: Open-Meteo at the stadium, kickoff hour + the two after — `wind_mph` (mean), `gust_mph` (max), `precip_in` / `rain_in` / `snowfall_in` (sums), `snow`, `temp_f` (mean), `weather_code`, `precip_prob_pct` (forecast), `n_hours`, the grid point, `hourly` jsonb (the values used). `source = 'archive'`: one row per game; `'forecast'`: one row per game per fetch, kept forever, `forecast_hours_ahead` = kickoff − fetch. Empty until the first run from a machine that reaches open-meteo.com |
| `nfl_stadiums` | all (from the repo) | stadium_id | plan D3 stadium reference (`src/league_lab/ingest/reference/stadiums.csv`, reloaded by `db migrate` when it changes): 49 venues, lat / lon, time zone, roof type, tenants, `names` (every name nflverse used) |
| `nfl_stadium_game_venues` | all (from the repo) | game_id | plan D3: games nflverse records at another stadium (the 2025 international games) → where they were played |

Every raw nfl table carries `_fetched_at`; every Sleeper table carries `payload jsonb` and
`fetched_at`: the **content time**, when those bytes were fetched from the source (see
`ops.source_partition.loaded_at` below). Column types are derived from the source file and widened
(never narrowed) when a later season's file changes type.

**Weather (plan D3, Wave D).** `intermediate.int_game_weather` — one row per game (seasons_start on,
REG + POST): the venue (per-game correction → a stadium name that belongs to another venue → the
recorded `stadium_id`; `venue_resolved_by`), `roof_type`, the game's `roof`, `roof_assumed_closed` (an
undecided retractable roof), the `wx_` values (below), `wx_source` (archive | forecast |
nflverse_observed | none | dome), `wx_known_at`, `wx_forecast_hours_ahead`, and each source's own
numbers side by side (`archive_*`, `nflverse_*`, `forecast_*`) for the train / serve comparison.
`intermediate.int_player_week_weather` — the feature group at the contract grain (gsis_id, season,
week; one row per `int_player_week_universe` row): `wx_dome`, `wx_wind_mph`, `wx_gust_mph`,
`wx_precip_in`, `wx_temp_f`, `wx_cold`, `wx_windy`, `wx_snow`, `wx_source`; definitions in
docs/METRICS.md § Weather, tests in `int_player_week_weather.yml` and `dbt/tests/assert_weather_*.sql`,
`assert_stadium_reference_covers_schedules.sql` (warn).

## ops

`ops.load_manifest` — one row per attempted partition load: source, dataset, partition_key,
source_url, source_last_modified, source_etag, fetched_at, checksum_sha256, schema_fingerprint,
row_count, status (`success` | `failed` | `skipped_unchanged` | `contract_failed`), error,
code_version, file_path, started_at, finished_at. `started_at` is **when this database checked**
the partition (every attempt, unchanged ones included; `mart_data_status.last_attempt_at`).

`ops.source_partition` — current state per (source, dataset, partition_key): last successful
load, checksum, ETag, rows, loaded_at. Used to skip unchanged content. **`loaded_at` is the content
time**, not the moment of the insert: the `fetched_at` of the bytes that were loaded. A live
download of new content stamps the download time (the same instant written to the archive's
`.meta.json`); an `--offline` replay stamps the archive's own `fetched_at` (the file's mtime if it
has no sidecar); an unchanged answer (304, or identical bytes under a new ETag / from Sleeper,
which sends none) keeps the archived `fetched_at` and records the check as `checked_at` in the
sidecar. So a database rebuilt from the archive every night (GitHub Actions) shows the same
`loaded_at` as one that loaded every file live, and it moves only when the content changes, which
is what `mart_data_status.last_loaded_at`, the page banner, B5's stale-injury flag and the sync's
"published through" line read. No separate column was needed: "checked" lives in `load_manifest`.
(Before 2026-09-29 `loaded_at` was the insert time, so a replayed database showed the replay time.)

`ops.projections` (projection v2) — one row per league_id × season × week × gsis_id: model_version,
fitted_at, train_seasons, position, the projected stat line (`proj_*`), `proj_points`, `p10 / p50 / p90`,
and the **decision-record labels (plan B5)** `frozen_source` / `frozen_at`. Written by `league-lab project`:
a league-week is replaced by every refit until the week's first kickoff (`min(dim_game.kickoff_at)`)
and never deleted or rewritten after it. `frozen_source` NULL = live; `kickoff` = the board as published
before the first kickoff, `frozen_at` = its `fitted_at` (< first kickoff); `refit` = rows locked after the
week had started (2026 weeks 1–3, played before B5; a league added mid-season), `frozen_at` NULL. One
label per league-week (`assert_frozen_projections_precede_kickoff`). Design: a label on this table
rather than a separate `ops.projection_snapshots` table — the row a manager saw is the only row, so the
mart, the page, the drift and the hosted copy need no second copy or "prefer the snapshot" join
(`docs/METRICS.md` § Decision record). `league-lab db migrate` (and the writer and the mart's pre-hook)
add the two columns to an existing table (`alter table … add column if not exists`).
**Plan R-13 (2026-09-30): K and DEF rows**, `model_version = 'kd1.0'`, for the leagues that start the
position: `position` K (`gsis_id` = the kicker's) or DEF (`gsis_id` = the **Sleeper defense id**, `KC`,
`LAR`: a team defense has no NFL player id), `proj_points` / `p10` / `p50` / `p90` in the league's scoring,
the QB–TE `proj_*` columns NULL (they do not apply). Written in the same `project` call and through the
same freeze as v2 (a league-week is written whole); `docs/METRICS.md` § Kicker and defense projections.

`ops.projection_drift` (M-06) — one row per league_id × season × week × position for played weeks
of the projected season (≥ 8 played, rankable players): n_players, spearman, top_n, hit_rate, mae,
coverage_80, interval_width, games_played / games_scheduled (the week is complete when they are
equal), `frozen_share` (B5: share of the scored rows that are the board as published before kickoff;
0 = refit values), model_version, run_at. Written by `league-lab drift` and at the end of `league-lab
project` (replaces the season's rows); the projection is read from `ops.projections` (the frozen rows
of a started week), outcomes from `mart_player_week_projections`.

`ops.lineups` (B1, exact lineup service) — per league_id × season × week × roster_id × `is_realised`
(false = the **proposed** lineup from projection v2, true = the **realised** optimum at Sleeper's points
for weeks Sleeper has scored), one row per starting slot and per rostered player:
`role` = `starter` | `empty` (a starting slot nobody on the roster is eligible for this week — or, in a
realised lineup, only a negative scorer: player columns NULL) | `bench` (playable, not starting;
`bench_rank` 1 = best value) | `unplayable` (`reason`: `bye`, `Out`, `Doubtful`, `NFL injured reserve`,
`IR slot`, `taxi squad`, `game started (bench)`, `no NFL team`, `no <POS> slot in this lineup`, …). A
playable player with no value yet is a starter or bench row with `value` 0, `value_source` `unvalued`
and `reason` `no value yet` (seated only where nobody valued can play). Starting rows carry `slot` (unique label within
the lineup: `QB`, `RB1`, `RB2`, `FLEX1`, `SUPER_FLEX`, … — numbered only when the slot repeats; same-type
slots list the better player first), `slot_type` (the Sleeper slot), `slot_order` (position in
`roster_positions`), `margin` (lineup total minus the best total without him, re-solved; NULL for an
empty slot and a locked player) and `is_locked` (his game has kicked off in a week not yet scored).
Every row: `sleeper_player_id`, `gsis_id` (NULL when unmapped: DEF, a rookie K), `player_name`
(Sleeper's), `position` (Sleeper's), `value` (NULL = unknown on an unplayable row; 0 on an `unvalued`
row), `value_source` (`proj_points` | `season_ppg` | `observed_ppg` | `unvalued` | `sleeper_observed`), `report_status` (injury report; Questionable plays),
`model_version` (proposed only), `run_at`. Keys: (league, season, week, roster, is_realised, slot) where
slot is set; (…, sleeper_player_id) where set — a player appears once per lineup (source tests).

`ops.lineup_totals` (B1) — one row per lineup (league_id × season × week × roster_id × is_realised):
`lineup_value` (sum of the starters' known values), `bench_value` (the best legal lineup the playable
bench alone would field), `slots_total`, `slots_filled`, `empty_slots` (comma-separated labels or NULL),
`weakest_slot` / `weakest_margin` / `weakest_sleeper_player_id` (the unlocked, valued starter with the smallest
margin), `n_players`, `n_bench`, `n_unplayable`, `n_locked`, `n_questionable` (starters), `n_ppg_valued`
(starters valued by a season PPG instead of a projection), `n_unvalued` (starters seated with no value
yet; added 2026-09-29, `db migrate` / the writer / the mart's pre_hook add it to an existing table), `as_of` (the time kickoffs were judged
against), `inputs_fingerprint` (realised rows: md5 of the Sleeper points the lineup was solved on — the
dbt test skips a roster-week whose points changed since), `model_version`, `run_at`. Both tables are
written together by `league-lab lineups` and at the end of `league-lab project` (the season's rows are
replaced in one transaction; `src/league_lab/lineup.py`).

`ops.waiver_moves` (B3, waiver engine) — per league_id × season × `week` (the **decision week**: the first
week with a game that has not kicked off at `as_of`) × roster_id × `add_sleeper_id` × `drop_sleeper_id`, one
row per legal move that raises the roster's best lineup this week or over the horizon (the decision week and
the next three: `horizon_weeks`, `horizon_last_week`), or one row with `list_kind = 'nothing'` (add / drop
NULL, gains 0) when no move does. `list_kind` = `start_now` (weekly gain > 0) | `cover` (weekly ≤ 0, horizon
> 0) | `nothing`; `move_rank` (1 = best: horizon gain, then weekly gain, then no drop, then the drop with the
fewest rest-of-season points); `is_best_drop` / `add_rank` (the best drop per add, adds ranked by it). The add:
`add_sleeper_id`, `add_gsis_id`, `add_name`, `add_position`, `add_value` (his decision-week value as B1 would
carry him: v2 `proj_points` in this league's scoring; K / DEF the kd1.0 `proj_points` since R-13, free-agent
defenses included), `add_value_source`, `add_reason` (why he
cannot play this week: bye, Doubtful, game started), `add_report_status`, `add_games_played`, `is_no_evidence`
(no game this season). The drop: `drop_*` ids / name / position, `drop_value` (this week), `drop_is_starter`,
`drop_horizon_loss` (what dropping him alone costs the lineup over the horizon), `drop_ros_points` /
`add_ros_points` (each one's projected points over the rest of the season, weeks he can play; `rest_of_season_weeks`).
The gain: `weekly_gain`, `horizon_gain`, `week_gains` (double precision[], one per horizon week),
`add_horizon_gain` (the add's gain with nobody dropped: the bound the pruning uses), `lineup_before` /
`lineup_after` (decision week; before = `ops.lineup_totals.lineup_value`). The seat (decision week, B1's
`solve()`): `add_slot` / `add_slot_type` (NULL = bench or cannot play), `fills_empty_slot`, `displaced_*` (the
starter who leaves the lineup — the drop himself when he started — with his `displaced_value` and
`displaced_slot` from `ops.lineups`). `open_roster_spots` (starting + bench slots minus active players; < 0 =
over the limit, no legal single move), `inputs_fingerprint` (md5 of the league's roster membership and every
player's free-agent / NFL-roster / injury status when computed: `waivers.FINGERPRINT_SQL`), `model_version`,
`as_of` (= the lineups' `as_of` by default), `run_at`. Written by `league-lab waivers` and at the end of
`league-lab project` right after the lineups (the season's rows replaced in one transaction;
`src/league_lab/waivers.py`); `db migrate`, the writer and the mart's pre_hook create it. Source test: one row
per (league, season, week, roster, add, drop).

`ops.player_role_alerts` (plan R-10, C6) — one row per season × gsis_id × week with a role alert: `game_id`,
`player_name`, `position`, `team`, `direction` (up / down), `games_held` (1–3) and `since_week` (the first game of the
change), `confidence` (one / two / three games), `primary_metric` and `metrics_changed` (text[]), `z` (the change over
its noise, primary metric), the evidence `snap_from/_to`, `route_from/_to`, `target_from/_to`, `carry_from/_to`
(0–1 shares, before = median of up to 8 prior games, after = the window), `change_text`, the named reason
`trigger_kind` (none / teammate_out / teammate_back / teammate_up / traded / depth_up / depth_down),
`trigger_gsis_id`, `trigger_name`, `trigger_status` (out_injured / inactive / barely_played / gone / traded_away /
back / took_over / the new team / the depth rank), `trigger_text`, `prior_games`, `kind` (role_up / role_down /
absence_beneficiary / depth_move / new_team), `cause_text` (always set), `expires_after_week` (the alert week + 3)
and `expiry_rule`, `signals_version` (ra1.1), `run_at`. Written by `league-lab project` right after the
projections and by `league-lab signals` (`src/league_lab/signals.py`): the projected season is rewritten every run,
every other season only when the table has no rows of it under the current `signals_version` (a fresh database
computes 2016 on in ~20 s). Past seasons use route share (published after the season); the current season has none.
The mart's pre_hook creates it. Source test: unique (season, gsis_id, week).

`ops.player_scenarios` (plan R-12, C6) — one row per league_id × season × week × gsis_id (QB/RB/WR/TE with a live
bigger-role alert; the weeks from the next unplayed one to `expires_after_week`): the alert (`alert_week`,
`since_week`, `games_held`, `confidence`, `kind`, `trigger_*`, `cause_text`, `change_text`), `base_points` (= the
stored projection, checked to 1e-6 in `project`), `larger_points` (the scenario), `points_gain`, `with_alert_points`
(base + `hold_rate` × gap), `hold_rate`, `backtest_n` / `backtest_hit_rate` (the calibration for that games-held
level), `presentation` ('what if' — or 'with the alert' once the backtest supports it) and `presentation_note`, both
stat lines (`base_*` / `larger_*` for targets, receptions, receiving yards, carries, rushing yards, attempts,
passing yards, touchdowns; `base_line` / `larger_line` jsonb with every component), `features_set` (jsonb
{input: [base, scenario]}), `expires_after_week`, `expiry_rule`, `model_version`, `signals_version`, `run_at`.
The projected season's rows are replaced every run. Source test: unique (league_id, season, week, gsis_id).

`ops.waiver_upside` (plan R-12, C6; B3's `list_kind = 'upside'`) — one row per league × season × decision week ×
roster × free agent with a live bigger-role scenario who does not help that roster at his projection today (base
horizon gain ≤ 0): `upside_rank`, the add (`add_*`), `base_value` / `scenario_value` / `points_gain` /
`with_alert_value` / `presentation` (his decision-week scenario row), the alert (`alert_week`, `since_week`,
`games_held`, `confidence`, `kind`, `trigger_*`, `cause_text`, `change_text`, `expires_after_week`, `expiry_rule`),
the drop (`drop_*`, `drop_horizon_loss`; NULL on an open roster spot), the B3-style gains at his projection
(`base_weekly_gain`, `base_horizon_gain`) and if the bigger role holds (`holds_weekly_gain`, `holds_horizon_gain`,
`holds_week_gains` double precision[], `holds_slot`), `open_roster_spots`, `inputs_fingerprint`, `as_of`,
`run_at`. Written by the waiver engine right after `ops.waiver_moves` (`waivers.upside_after_waivers`; the same
decision week and 4-week horizon). Source test: unique (league, season, week, roster, add).

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
| `intermediate.int_player_game_role` (R-10) | gsis_id, game_id | every QB/RB/WR/TE on a team's weekly roster (or who played for it) × each played regular-season team game: `status` (played / out_injured — did not play and on the injury report or IR/PUP / inactive), `snap_share` (0 for a missed game with snap counts, NULL without), `route_share` (routes proxy over dropbacks with participation; NULL in-season), target / carry shares with the team's totals, the stat line, air yards, red-zone and first-read counts, `points_expected`, `team_margin`, `report_status`, `roster_status`. Read by `signals.py` only. Tests: key unique, shares in 0–1, a missed game has no usage, `status` / `position` accepted values |

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
| `mart_player_next_matchup` | gsis_id | next game/bye, opponent DvP rank, injury, depth rank |
| `mart_league_roster_membership` | league_id, sleeper_player_id | who rosters whom now |
| `mart_player_availability` | league_id, sleeper_id (league_id, gsis_id where gsis_id is set) | rostered-by / free agent × usage × expected gap × next matchup; points columns (`points_std`, `ppg_std`, `points_per_game_l3/_l5`, `expected_per_game`, `diff_per_game`, `games_with_expected`) in the row's league scoring via `mart_league_player_season` (S-01a); usage, shares and opponent ranks are scoring-free or reference-scored. **R-13**: plus one row per team defense (`position` DEF, `sleeper_id` = `KC` …, `gsis_id` NULL, `roster_status` ACT) for the leagues that start a DEF: rostered-by / free agent, `games_played`, `points_std` / `ppg_std` / `points_per_game_l3` / `_l5` in the league's D/ST scoring (`def_points()` over `mart_kd_week`), next opponent / home / bye; the usage and injury columns NULL |
| `mart_league_optimal_lineup` | league_id, week, roster_id | started vs optimal points, bench points left (greedy fill over Sleeper's points; held below the exact solver by `assert_exact_lineup_dominates_greedy`) |
| `mart_lineup_recommendation` (view, B1) | league_id, season, week, roster_id, slot | the **proposed** lineup from `ops.lineups` / `ops.lineup_totals`, one row per starting slot (filled or empty): `slot`, `slot_type`, `slot_order`, `sleeper_player_id`, `gsis_id`, `player_name` (dim_player by gsis_id, else Sleeper's), `position`, `player_value`, `value_source`, `lineup_margin`, `is_weakest_slot`, `is_empty_slot`, `is_locked`, `report_status`, `is_questionable`; per lineup `lineup_value`, `bench_value`, `weakest_slot`, `weakest_margin`, `empty_slots`, `n_unvalued`, `realised_optimal` (scored weeks), `model_version`, `as_of`, `run_at`; `team_name` / `manager_name` from dim_league_member. Tests: key unique, a player once per lineup, margin ≥ 0, weakest = smallest valued margin, an unvalued starter counts 0 with margin 0, empty slot has no player, `value_source` in (proj_points, season_ppg, observed_ppg, unvalued) |
| `mart_waiver_moves` (view, B3) | league_id, season, week, roster_id, add_sleeper_id, drop_sleeper_id | `ops.waiver_moves` with names (dim_player by gsis_id, else Sleeper's), `team_name` / `manager_name`, the add's `add_team` (availability), `lineup_value` (the decision week's lineup as `mart_lineup_recommendation` publishes it), `on_current_lineup` (moves solved on the lineups published now: same `as_of`), `inputs_current` (the league's rosters and free-agent statuses unchanged since: same fingerprint). Tests (`dbt/models/marts/edge/waivers.yml`): key unique, `move_rank` / `add_rank` unique per roster, `lineup_before` = `lineup_value` (when on the current lineup), a move gains and its list follows from the gains, the `nothing` row is empty, weekly gain = after − before and horizon = Σ `week_gains`, gain ≤ the add alone, best drop ⇔ add rank; `assert_waiver_moves_are_legal` (error): the add is a free agent on an active NFL roster not Out / IR, the drop is on the roster and not IR / taxi / locked, "no drop" only with an open spot, one drop only when it makes room, every roster has a row — for leagues whose inputs are current |
| `mart_player_role_alerts` (view, R-10) | season, gsis_id, week | `ops.player_role_alerts` plus `direction_label`, `team_last_week`, `is_latest` (the alert game is his team's latest played game), `trigger_ended` (an injured teammate's absence alert whose teammate is active with no injury designation on the latest report: `mart_player_availability`), `trigger_injury_now`, `is_live` (= is_latest and not trigger_ended: "this week's alerts"). Tests (`signals.yml`): key unique, 1–3 games held, a trigger has text, direction matches the sign of `z`, `kind` matches the direction, the expiry is after the alert, `kind` / `trigger_kind` / `confidence` accepted values, `change_text` / `cause_text` not null |
| `mart_player_scenarios` (view, R-12) | league_id, season, week, gsis_id | `ops.player_scenarios` with the player's name, team and opponent and `proj_points` from `mart_player_week_projections`. Tests: key unique, `base_points` = `proj_points` (±0.005), gain = larger − base, `with_alert_points` between base and larger, the week is after the alert and within the expiry, `presentation` in ('with the alert', 'what if') |
| `mart_waiver_upside` (view, R-12) | league_id, season, week, roster_id, add_sleeper_id | `ops.waiver_upside` plus `inputs_current` (the league's rosters and statuses unchanged since: the waiver engine's fingerprint). Tests: keys unique (add; rank), `holds_horizon_gain` = Σ `holds_week_gains`, a drop or an open spot, `base_horizon_gain` ≤ 0 (the stash case); `assert_waiver_upside_is_legal` (error): the add is a free agent on an active NFL roster not Out / IR, the drop is on the roster and not IR / taxi / locked — for leagues whose inputs are current |
| `mart_league_all_play` / `_week` | league_id, roster_id / + week | all-play record, expected wins, luck |
| `mart_league_keeper_candidates` | league_id, sleeper_player_id | acquisition cost facts + production, ranks and xPPG in the league's own scoring (S-01a) |
| `mart_league_manager_profile` | league_id, roster_id | luck, lineup discipline, activity, roster shape |
| `mart_league_positional_strength` | league_id, roster_id, position | starter ppg vs league median, rank (league's own scoring through availability). **No page reads it since B2** (replaced by the roster-value marts below; superflex counted as a QB slot, FLEX not attributed); kept as a mart for comparison |

### Matchups (C5, plan R-14 / R-11, 2026-09-30)

Replaces `mart_defender_coverage_season` and `mart_matchup_cb_context` (retired; only the Matchups page read
them). No `ops` source: built by the ordinary `dbt build`. Definitions: `docs/METRICS.md` § Cornerback matchups,
§ Matchup comparison. Tests: `dbt/models/marts/nfl/matchups.yml` + `assert_cb_rankings_pool_size`,
`assert_cb_matchup_covers_lineup_receivers`, `assert_defense_profile_is_asof`,
`assert_coverage_snap_estimate_tracks_participation` (warn).

**Performance (hotfix 2026-10-01).** On PostgreSQL 17 with a 4-thread build, `mart_defense_position_profile`
ran > 30 min and `mart_receiver_vs_cb` 5 min: both joined large inputs on several correlated keys (a defense's
games `week < week`, a join back on receiver × corner × season, the raw participation table with no index), and
right after `fct_player_game` / `fct_team_game` were rebuilt without statistics the planner estimated a handful of
rows and chose nested loops (reproduced here: > 275 s, cancelled). The two marts now read six intermediate tables
(`dbt/models/intermediate/matchups/`), each indexed and analyzed (`post_hook`), the upstream tables analyzed in a
`pre_hook` before the query is planned, and **no join between large inputs anywhere**: rows that would be joined
are stacked (`union all`) and grouped on the key, or flagged / broadcast with window functions; the one join left
is to the ~1.7k-row week bridge. `int_season_week_before` (season, week, each earlier week) ·
`int_defense_position_game` (defense × game × position, with the offense's and the league's prior-season points)
· `int_defense_position_asof` (season × week × defense × position × each game before the week, with the offense
baseline as a window over that fan-out) · `int_target_participation` (target plays 2022+ with the defense's
on-field list) · `int_receiver_defender_game` (receiver × defender × game, with his targets against that defense
that season) · `int_defender_snap_share` (defender-game snaps and share, 2022+). Same rows as before (md5 of both
marts unchanged); 1–4 s per model with or without statistics, 1 or 4 threads.

| Model | Grain / key | Contract |
|---|---|---|
| `int_defender_game_coverage_snaps` (intermediate) | gsis_id, game_id | every defender-game PFR's advanced defense charts (2018+): the coverage numerators (`def_targets`, completions, yards, TDs, INTs, aDOT, YAC, missed tackles as the primary defender), PFR `position` and snap-count `snap_position`, `defense_snaps` / `team_defense_snaps`, the opponent's `opp_dropbacks`; `coverage_snaps` = `coverage_snaps_on_field` (participation: opponent dropbacks with him on the field) else `coverage_snaps_estimated` (snap share × opponent dropbacks), `coverage_snaps_source` |
| `mart_cb_rankings` | gsis_id, season, window_label | cornerbacks only; `window_label` season / last_4 / two_seasons; games, `games_at_cb`, first / last game, `coverage_snaps` (+ `_estimated`), targets, completions, yards, TDs, INTs allowed, `targets_per_coverage_snap`, `yards_per_target_allowed`, `exp_ypt_faced` (the offenses' WR + TE yards per target), `adj_yards_per_target`, `completion_pct_allowed`, `yards_per_coverage_snap`, `adot_allowed`, `passer_rating_allowed`, pool yardsticks, `z_targets` / `z_yards` / `z_rating`, `quality_score`, `min_coverage_snaps`, `is_ranked`, `n_ranked`, `quality_rank` (1 = hardest to throw on), component ranks, `quality_label` (shutdown / solid / target); shadow evidence `wr1_games`, `wr1_follow_slope`, `other_follow_slope`, `shadow_flag` (not shown in the app). 6,316 rows (74 ranked in 2026 `two_seasons`) |
| `mart_receiver_vs_cb` | receiver_gsis_id, defender_gsis_id, season | 2022 on, WR / TE × cornerback: `evidence` on_field (participation: targets / receptions / yards / TDs with him on the field, `targets_vs_defense`, `share_of_targets`) or same_game (current season: totals in games he played, `defender_snap_share`), receiver / defender names, teams, games. 39,572 rows |
| `mart_cb_matchups` | gsis_id, season, week | 2025 on, every rostered WR / TE (+ current-season WR / TE on his latest team) × REG week with a game: `opponent`, `depth_chart_at`, rank-1 `lcb_*` / `rcb_*` / `nb_*` (id, name, rank, label), `tgt_left` / `_middle` / `_right`, shares, `located_targets`, `alignment_lean`, `side_share`, `other_side_share`, `call_status` (called / tight end / too few targets / no depth chart yet), `call_strength` (clear / even), `likely_cover_slot` / `_gsis_id` / `_name`, `other_cover_*` (even calls), the cover's two-season numbers, `cover_rank`, `cover_label`, component ranks, `cb_n_ranked`, `cb_min_coverage_snaps`, his line vs the defense this season (`*_vs_opp`) and with the cover on the field since 2022 (`*_vs_cover`, `evidence_vs_cover`). 16,972 rows |
| `mart_defense_position_profile` | season, week, defense, position | as of the week (games before it): `games`, `points_allowed_pg`, `opps_allowed_pg`, `targets_allowed_pg`, `carries_allowed_pg`, `yards_per_opp_allowed`, `td_rate_allowed`, `offense_baseline_pg`, `adjusted_points_pg`, league rates, `opportunity_index`, `efficiency_index`, `gives_up`, ranks (`rank_points`, `rank_opportunity`, `rank_efficiency`, `rank_td_rate`, `rank_adjusted`, `rank_targets`, `rank_carries`; 1 = gives up the most), `n_defenses`. 24,704 rows |

### Roster value (B2, 2026-09-30)

Built on the exact lineup service (B1). The four views read `ops.lineups` / `ops.lineup_totals` and declare
`-- depends_on: mart_lineup_recommendation`, so `--select mart_lineup_recommendation+` (Makefile `project`,
nightly `projection-marts`) rebuilds and tests them after every `project`. Definitions: `docs/METRICS.md` § Roster value.

| Model | Grain / key | Contract |
|---|---|---|
| `mart_league_acquisitions` (table) | league_id, sleeper_player_id (current rosters) | how each rostered player joined his roster: the move that began his current stint (latest draft pick by / completed add to this roster), across the whole chain (`chain_id`) for a dynasty, the current season otherwise. `acquired_how` (draft, trade, waiver, free_agent, commissioner), `acquired_how_by_manager` (+ `inherited`: the roster had him before today's owner / co-owners took over), `acquired_season`, `acquired_week`, `acquired_at`, `is_offseason`, `draft_kind` (startup / rookie / draft), `draft_round`, `draft_pick`, `draft_pick_in_round`, `was_keeper`, `trade_partner_roster_id` / `_team` / `_manager` (at the time), `waiver_bid`, `manager_since`, `is_inherited`, `event_label`, `acquired_label` (plain words), `fantasy_positions` (Sleeper eligibility, published for the solver). Tests: key unique, how in the accepted set, a trade names its partner, a draft has round and pick, not in the future; `assert_every_rostered_player_has_acquisition`, `assert_acquisition_starts_current_stint` |
| `mart_league_roster_horizon` (view) | league_id, roster_id, week, sleeper_player_id (and slot) | every current roster's proposed lineup rows for this week (first REG week with a kickoff after `now()`) and the next three: `role` (starter / empty / bench / unplayable), `slot`, `slot_type`, `player_value`, `value_source`, `lineup_margin`, `is_locked`, `reason`, `fantasy_positions`, `is_top_at_slot_type`, `replacement_sleeper_player_id` / `_name` / `_value` (the bench player who enters when that starter is removed: worth value − margin), `acquired_label`, `acquired_how_by_manager`, `this_week`, `horizon_first_week`, `horizon_last_week`, `horizon_weeks`, `is_this_week`. Tests: keys unique, 1–4 weeks, every starter whose margin is below his value has a replacement worth value − margin |
| `mart_league_roster_value` (view) | league_id, roster_id | this week's `lineup_value`, `bench_value` (depth), `weakest_slot` / `_margin` / `_player_name` / `_value` / `_replacement_name` / `_replacement_value`, `empty_slots`, `n_unvalued`, `n_locked`, `n_questionable`; `horizon_value` (sum of the horizon's lineup values), `horizon_lineups`, `worst_week` / `_value`; `week_label` ('week 4'), `horizon_label` ('weeks 4–7'). Tests: key unique, every horizon week present and horizon ≥ this week, the replacement matches the margin; `assert_roster_value_reconciles` (starters sum to each week's lineup value to the cent, horizon = sum, every roster valued and ranked) |
| `mart_league_roster_rankings` (view) | league_id, roster_id, measure | `measure` (lineup_value, horizon_value, bench_value), `measure_label`, `horizon` (the weeks the rank covers), `value`, `league_rank` (rank(), 1 = highest), `n_rosters`, `rank_label` ('3/12'). Tests: key unique, horizon not null, rank within 1..n |
| `mart_league_roster_slot_strength` (view) | league_id, roster_id, slot_type | this week, per slot type the league starts: `slots`, `empty_slots`, the top starter (`top_player_name`, `top_value`, `top_is_locked`), `starter_strength` (= his B1 margin: lineup minus a fresh solve without him), `replacement_name` / `_value`. Tests: key unique, 0 ≤ strength ≤ his value |

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
| `mart_player_week_projections` | league_id, gsis_id, season, week | projection v2 from `ops.projections` (written by `league-lab project`): projected stat line, `proj_points` in the league's scoring, `p10 / p50 / p90`, `interval_width`, as-of context, the outcome priced under the league's scoring (`points_actual`), `actual_inside_interval`, `rank_pos` (by P50), `actual_rank_pos`, `frozen_source` / `frozen_at` (B5: NULL = live board, `kickoff` = frozen as published before the week's first kickoff, `refit` = locked after kickoff, not a kickoff record) |
| `mart_player_week_projections` — K / DEF rows (R-13) | league_id, gsis_id, season, week (K); league_id, team, season, week (DEF: `gsis_id` NULL) | kd1.0 from `ops.projections` for the leagues that start the position: `proj_points`, `p10 / p50 / p90`, `interval_width`, game context and `report_status` / `roster_status` / `games_to_date` from `mart_kd_week`, the outcome priced in the league's scoring (`league_points()` for K, `def_points()` for DEF), `actual_inside_interval`, `rank_pos` / `actual_rank_pos` within the position; the QB–TE stat-line, usage and PPG columns NULL |
| `mart_kd_team_game` (R-13) | team, game_id | every team × scheduled regular-season game 2016+: `is_home`, `is_dome`, `kickoff_at`, spread / total, `implied_team_total`, `opp_implied_total`, `played`; the team's kicking (`fg_att`, `fg_made`, `fg_made_0_19` … `fg_made_50p`, `fg_missed` incl. blocked, `pat_att`, `pat_made`, `pat_missed` incl. blocked), defense and special teams (`sacks`, `interceptions`, `fumble_recoveries`, `forced_fumbles`, `def_tds` incl. fumble-return TDs, `st_tds`, `safeties`, `blocked_kicks`, `points_allowed` = the opponent's final score) and offense (`points_for`, `sacks_suffered`, `giveaways`, `plays`, `red_zone_plays`, `offense_epa`); outcomes NULL unless played. One code per franchise (the schedule's OAK / SD → LV / LAC, as the stats files say: `kd_team()`) |
| `mart_kd_week` (R-13) | position, unit_id, season, week | K (`unit_id` = gsis_id; kickers who kicked that week + ACT kickers on the latest weekly roster for a week without a kick: the upcoming weeks) and DEF (`unit_id` = Sleeper id) units × regular-season week: `gsis_id`, `sleeper_id`, `player_name`, `team`, `opponent`, `game_id`, `is_home`, `is_dome`, lines, implied totals, `roster_status`, `report_status` (K injury report), `played`, the outcome line `out_*` (K: `out_fg_made_0_19` … `out_fg_made_50p`, `out_fg_missed`, `out_fg_missed_0_19` … `_50p`, `out_pat_made`, `out_pat_missed`; DEF: `out_sacks`, `out_interceptions`, `out_fumble_recoveries`, `out_forced_fumbles`, `out_def_tds`, `out_st_tds`, `out_safeties`, `out_blocked_kicks`, `out_points_allowed`), NULL unless played |
| `mart_projection_backtest` (view) | league_id, season, position, scorer | from `ops.projection_backtest` (written by `league-lab backtest-v2`; R-13: plus `league-lab backtest-kd`'s K / DEF rows, `model_version` kd1.0, scorers `kd_points` / `season_ppg` / `last3_ppg`): Spearman, hit rate, MAE, `coverage_80`, interval width per walk-forward season |
| `mart_projection_backtest` (view) | league_id, season, position, scorer | from `ops.projection_backtest` (written by `league-lab backtest-v2`): Spearman, hit rate, MAE, `coverage_80`, interval width per walk-forward season |
| `mart_projection_importance` (view, U-15) | model_version, model, position, component, feature | from `ops.projection_importance`: what drives projection v2. `model = 'component'` (written by `league-lab project`): permutation importance of the component models on the newest training season, `component = 'total'` in points of error of the priced line (reference league's scoring, `unit = 'points'`), one row per stat-line component in its own unit with `importance_points` (= rise × points per unit); `feature_label` (plain words, `projections.FEATURE_LABELS`), `importance_sd` over the shuffles, `baseline_mae`, `n_rows`, `train_seasons`, `eval_season`, `importance_rank` (1 = most error added, per model version × model × position × component). `model = 'quantile_p50'` (written by `backtest-v2`, and every row from before U-15): the P50 interval model, `component = 'p50_residual'`. Tests: key unique, `model` in the two values, component rows complete (plain label ≠ column name). Read by Rankings' "The model" expander |
| `mart_projection_drift` (view, M-06) | league_id, season, position | from `ops.projection_drift`: `weeks_scored`, `first_week` / `last_week`, `week_in_progress`, `player_weeks`, mean `spearman / hit_rate / mae / coverage_80 / interval_width` over **complete** weeks, next to `backtest_spearman / _hit_rate / _mae / _coverage_80 / _interval_width` (`mart_projection_backtest`, scorer `v2_points`, averaged over its held-out seasons; `backtest_seasons`, `backtest_weeks`); B5: `frozen_share` (player-weighted share of the complete weeks' scored rows that are the board as published before kickoff) and `refit_weeks` (complete weeks scored on refit values, e.g. `1, 2`) |

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
