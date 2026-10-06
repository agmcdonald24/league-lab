-- IM-1 (Wave I-M): Pro Football Reference's weekly rows reach mart_player_game_advanced only through
-- analytics.player_id_map (PFR id -> gsis id; never by name). The rows of the newest season whose PFR id has no mapped
-- gsis id are listed here (they are not in the mart): a warning for any, an error past 25 (a broken map, not a rookie
-- the Sleeper-side map has not picked up yet). On the IM-1 clone, 2026 weeks 1-4: 7 rows, 3 players.
{{ config(severity='error', warn_if='>0', error_if='>25') }}
with pfr as (
    select 'rec' as file, pfr_player_id, pfr_player_name, game_id, season from {{ ref('stg_nflverse__pfr_advstats_rec') }}
    union all
    select 'rush', pfr_player_id, pfr_player_name, game_id, season from {{ ref('stg_nflverse__pfr_advstats_rush') }}
    union all
    select 'pass', pfr_player_id, pfr_player_name, game_id, season from {{ ref('stg_nflverse__pfr_advstats_pass') }}
)
select p.file, p.pfr_player_id, p.pfr_player_name, p.game_id
from pfr as p
left join {{ ref('player_id_map') }} as m on m.pfr_id = p.pfr_player_id
where m.gsis_id is null and p.season = (select max(season) from pfr)
