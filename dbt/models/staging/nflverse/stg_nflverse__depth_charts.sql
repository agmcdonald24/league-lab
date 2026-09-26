select
    season,
    dt::timestamptz                as snapshot_at,
    team,
    player_name,
    gsis_id,
    pos_grp,
    pos_name,
    pos_abb,
    pos_slot,
    pos_rank
from {{ source('raw', 'nfl_depth_charts') }}
where gsis_id is not null
