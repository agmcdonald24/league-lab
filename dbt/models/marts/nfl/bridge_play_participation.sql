{{ config(indexes=[{'columns': ['gsis_id', 'game_id']}, {'columns': ['game_id', 'play_id']}, {'columns': ['season', 'team']}]) }}
-- Offensive players on the field for each play (participation), one row per (game_id, play_id,
-- gsis_id). Offense only: this is what routes, on-field target rates and context splits need;
-- the defensive side stays in stg_nflverse__pbp_participation.defense_players until a consumer exists.
-- Presence is not a route: a tight end on the field for a dropback may have stayed in to block.
with part as (
    select game_id, play_id, season, possession_team, offense_players
    from {{ ref('stg_nflverse__pbp_participation') }}
    where offense_players is not null
)

select distinct  -- one upstream row (2024_02_CLE_JAX play 1985) lists a player twice
    part.game_id,
    part.play_id,
    part.season,
    part.possession_team                                     as team,
    x.gsis_id
from part
cross join lateral unnest(string_to_array(part.offense_players, ';')) as x(gsis_id)
where x.gsis_id <> ''
