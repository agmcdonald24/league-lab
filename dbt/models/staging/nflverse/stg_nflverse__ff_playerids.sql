-- dynastyprocess crosswalk. All columns are text in the source CSV; 'NA' was nulled at load.
select
    gsis_id,
    sleeper_id,
    pfr_id,
    espn_id,
    yahoo_id,
    sportradar_id,
    name,
    merge_name,
    position,
    team,
    birthdate::date                        as birth_date,
    draft_year::integer                    as draft_year,
    db_season::integer                     as db_season
from {{ source('raw', 'nfl_ff_playerids') }}
