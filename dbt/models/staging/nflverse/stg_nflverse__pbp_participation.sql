-- Players on the field per play (NGS 2016-2022, FTN 2023+; a season's file arrives after its
-- postseason). offense_players / defense_players are ';'-separated gsis ids. Participation
-- measures presence; it does not prove a route was run (plan §6).
select
    nflverse_game_id                                         as game_id,
    play_id,
    season,
    possession_team,
    offense_formation,
    offense_personnel,
    defense_personnel,
    defenders_in_box,
    number_of_pass_rushers,
    nullif(offense_players, '')                              as offense_players,
    nullif(defense_players, '')                              as defense_players,
    n_offense,
    n_defense,
    ngs_air_yards::numeric                                   as ngs_air_yards,
    time_to_throw::numeric                                   as time_to_throw,
    was_pressure,
    nullif(route, '')                                        as targeted_route,
    nullif(defense_man_zone_type, '')                        as defense_man_zone_type,
    nullif(defense_coverage_type, '')                        as defense_coverage_type,
    coalesce(n_offense, 0) > 0                               as has_offense_participation,
    _fetched_at                                              as source_fetched_at
from {{ source('raw', 'nfl_pbp_participation') }}
where season >= {{ var('seasons_start') }}
