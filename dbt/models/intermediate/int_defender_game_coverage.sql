-- PFR coverage stats per defender-game keyed by gsis_id (2018+), with the defender's position.
select
    m.gsis_id,
    d.game_id, d.season, d.season_type, d.week, d.team, d.opponent,
    d.pfr_player_name as defender_name,
    p.position,
    d.def_targets, d.def_completions_allowed, d.def_completion_pct, d.def_yards_allowed,
    d.def_yards_allowed_per_tgt, d.def_receiving_td_allowed, d.def_passer_rating_allowed, d.def_adot,
    d.def_air_yards_completed, d.def_yards_after_catch, d.def_ints, d.def_pressures, d.def_sacks,
    d.def_missed_tackles, d.def_tackles_combined
from {{ ref('stg_nflverse__pfr_advstats_def') }} as d
join {{ ref('int_pfr_gsis_map') }} as m on m.pfr_id = d.pfr_player_id
left join {{ ref('stg_nflverse__players') }} as p on p.gsis_id = m.gsis_id
