select
    player_gsis_id as gsis_id, season, season_type, week, week = 0 as is_season_aggregate,
    player_display_name as player_name, player_position as position, team_abbr as team,
    efficiency, percent_attempts_gte_eight_defenders, avg_time_to_los, rush_attempts, rush_yards, avg_rush_yards,
    rush_touchdowns, expected_rush_yards, rush_yards_over_expected, rush_yards_over_expected_per_att, rush_pct_over_expected
from {{ source('raw', 'nfl_ngs_rushing') }}
where player_gsis_id is not null and season >= {{ var('seasons_start') }}
