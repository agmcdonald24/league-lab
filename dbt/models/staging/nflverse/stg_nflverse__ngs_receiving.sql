-- Next Gen Stats receiving. week 0 rows are NGS's season aggregate.
select
    player_gsis_id as gsis_id, season, season_type, week, week = 0 as is_season_aggregate,
    player_display_name as player_name, player_position as position, team_abbr as team,
    avg_cushion, avg_separation, avg_intended_air_yards, percent_share_of_intended_air_yards,
    receptions, targets, catch_percentage, yards, rec_touchdowns, avg_yac, avg_expected_yac, avg_yac_above_expectation
from {{ source('raw', 'nfl_ngs_receiving') }}
where player_gsis_id is not null and season >= {{ var('seasons_start') }}
