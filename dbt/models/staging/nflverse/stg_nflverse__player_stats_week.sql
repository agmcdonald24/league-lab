-- Game-level player statistics (nflverse stats_player_week). Grain: player (gsis_id) x game.
-- Rows without a player id (team-level special teams entries) are excluded here and counted
-- in the quarantine model. Defensive/punting columns are intentionally not modelled (plan §1).
select
    player_id                                   as gsis_id,
    player_display_name                         as player_name,
    position,
    position_group,
    season,
    week,
    season_type,
    game_id,
    team,
    opponent_team,
    -- passing
    completions, attempts, passing_yards, passing_tds, passing_interceptions,
    sacks_suffered, sack_yards_lost, sack_fumbles, sack_fumbles_lost,
    passing_air_yards, passing_yards_after_catch, passing_first_downs,
    passing_epa, passing_cpoe, passing_2pt_conversions, pacr,
    -- rushing
    carries, rushing_yards, rushing_tds, rushing_fumbles, rushing_fumbles_lost,
    rushing_first_downs, rushing_epa, rushing_2pt_conversions,
    -- receiving
    receptions, targets, receiving_yards, receiving_tds, receiving_fumbles,
    receiving_fumbles_lost, receiving_air_yards, receiving_yards_after_catch,
    receiving_first_downs, receiving_epa, receiving_2pt_conversions, racr,
    target_share                                as nflverse_target_share,
    air_yards_share                             as nflverse_air_yards_share,
    wopr                                        as nflverse_wopr,
    -- misc scoring
    special_teams_tds, fumble_recovery_tds, fumbles_total, fumbles_lost_total,
    -- kicking
    fg_made, fg_att, fg_missed, fg_blocked, fg_long, fg_pct,
    fg_made_0_19, fg_made_20_29, fg_made_30_39, fg_made_40_49, fg_made_50_59, fg_made_60_,
    fg_missed_0_19, fg_missed_20_29, fg_missed_30_39, fg_missed_40_49, fg_missed_50_59, fg_missed_60_,
    fg_made_list, fg_missed_list, fg_blocked_list,
    pat_made, pat_att, pat_missed, pat_blocked,
    -- nflverse default fantasy points (standard / full PPR) kept for reconciliation only
    fantasy_points                              as nflverse_fantasy_points_std,
    fantasy_points_ppr                          as nflverse_fantasy_points_ppr,
    _fetched_at                                 as source_fetched_at
from {{ source('raw', 'nfl_player_stats_week') }}
where player_id is not null
  and season >= {{ var('seasons_start') }}
