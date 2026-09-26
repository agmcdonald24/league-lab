select
    player_gsis_id as gsis_id, season, season_type, week, week = 0 as is_season_aggregate,
    player_display_name as player_name, player_position as position, team_abbr as team,
    avg_time_to_throw, avg_completed_air_yards, avg_intended_air_yards, avg_air_yards_differential, aggressiveness,
    max_completed_air_distance, avg_air_yards_to_sticks, attempts, pass_yards, pass_touchdowns, interceptions,
    passer_rating, completions, completion_percentage, expected_completion_percentage,
    completion_percentage_above_expectation, avg_air_distance, max_air_distance
from {{ source('raw', 'nfl_ngs_passing') }}
where player_gsis_id is not null and season >= {{ var('seasons_start') }}
