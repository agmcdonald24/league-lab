-- Sleeper player directory. `gsis_id` is Sleeper's own crosswalk to the NFL id and is one of
-- two sources for player_id_map (the other is nflverse ff_playerids).
select
    player_id                                   as sleeper_player_id,
    first_name,
    last_name,
    full_name,
    position,
    fantasy_positions,
    team,
    status,
    active,
    injury_status,
    number                                      as jersey_number,
    years_exp,
    age,
    birth_date,
    nullif(trim(gsis_id), '')                   as gsis_id,
    espn_id,
    yahoo_id,
    sportradar_id,
    rotowire_id,
    position = 'DEF'                            as is_team_defense,
    fetched_at
from {{ source('raw', 'sleeper_player') }}
