-- The latest depth chart snapshot per team (most recent season loaded).
with latest as (
    select team, max(snapshot_at) as snapshot_at
    from {{ ref('stg_nflverse__depth_charts') }}
    group by team
)
select d.season, d.snapshot_at, d.team, d.gsis_id, d.player_name, d.pos_grp, d.pos_name, d.pos_abb, d.pos_slot, d.pos_rank
from {{ ref('stg_nflverse__depth_charts') }} as d
join latest using (team, snapshot_at)
