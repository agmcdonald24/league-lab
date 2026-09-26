-- Offensive snaps per player-game (PFR ids; mapped to gsis in int_player_game_snaps).
-- Snaps are participation evidence, NOT a route count (plan §4).
select
    game_id,
    pfr_game_id,
    season,
    week,
    game_type,
    player                                                   as player_name,
    pfr_player_id,
    position,
    team,
    opponent,
    offense_snaps::integer                                   as offense_snaps,
    offense_pct                                              as offense_snap_pct,
    defense_snaps::integer                                   as defense_snaps,
    st_snaps::integer                                        as st_snaps,
    _fetched_at                                              as source_fetched_at
from {{ source('raw', 'nfl_snap_counts') }}
where season >= {{ var('seasons_start') }}
