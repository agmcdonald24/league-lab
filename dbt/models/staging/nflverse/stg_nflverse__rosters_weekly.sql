-- Historical team affiliation and roster status per player-week (the basis of
-- player_team_history). Rows without a gsis_id are dropped (legacy entries).
select
    gsis_id,
    season,
    week,
    game_type,
    case when game_type = 'REG' then 'REG' else 'POST' end  as season_type,
    team,
    position,
    depth_chart_position,
    status                                                   as roster_status,
    status_description_abbr                                  as roster_status_detail,
    full_name,
    first_name,
    last_name,
    jersey_number,
    birth_date,
    height,
    weight,
    college,
    years_exp,
    rookie_year,
    entry_year,
    pfr_id,
    esb_id,
    espn_id,
    sleeper_id,
    _fetched_at                                              as source_fetched_at
from {{ source('raw', 'nfl_rosters_weekly') }}
where gsis_id is not null
  and season >= {{ var('seasons_start') }}
