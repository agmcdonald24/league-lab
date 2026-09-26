-- Snap counts keyed by gsis_id via the PFR id on nflverse players. Unmapped PFR ids are dropped
-- here (counted in the quarantine model); missing snaps downstream mean "unknown", never 0.
select
    m.gsis_id,
    s.game_id,
    s.season,
    s.week,
    s.game_type,
    s.team,
    s.opponent,
    s.position                       as snap_position,
    s.offense_snaps,
    s.offense_snap_pct,
    s.st_snaps
from {{ ref('stg_nflverse__snap_counts') }} as s
join {{ ref('int_pfr_gsis_map') }} as m on m.pfr_id = s.pfr_player_id
