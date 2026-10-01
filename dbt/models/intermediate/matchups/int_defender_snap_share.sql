{{ config(
    indexes=[{'columns': ['game_id', 'team']}, {'columns': ['gsis_id', 'season']}],
    pre_hook=["analyze {{ ref('int_pfr_gsis_map') }}"],
    post_hook="analyze {{ this }}") }}
-- Defensive snaps per defender-game, regular season 2022 on (PFR snap counts mapped to gsis ids), with his share
-- of the most snaps any mapped teammate played that game. mart_receiver_vs_cb's same-game evidence (the seasons
-- without participation) joins it on (game_id, team). No join (C5 performance hotfix): the PFR -> gsis map is
-- stacked under the snap rows and broadcast by PFR id with a window function.
with stacked as (
    select s.pfr_player_id as pfr_id, null::text as map_gsis_id, s.game_id, s.season, s.team, s.defense_snaps, true as is_snap
    from {{ ref('stg_nflverse__snap_counts') }} as s
    where s.season >= 2022 and s.game_type = 'REG'
    union all
    select m.pfr_id, m.gsis_id, null, null, null, null, false
    from {{ ref('int_pfr_gsis_map') }} as m
),

mapped as (
    select st.*, max(st.map_gsis_id) over (partition by st.pfr_id) as gsis_id
    from stacked as st
)

select gsis_id, game_id, season, team, defense_snaps,
       defense_snaps::numeric / nullif(max(defense_snaps) over (partition by game_id, team), 0) as snap_share
from mapped
where is_snap and gsis_id is not null
