{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- For every universe row, the player's as-of form: his latest played game BEFORE the week.
select u.gsis_id, u.season, u.week, a.*
from {{ ref('int_player_week_universe') }} as u
cross join lateral (
    select games_to_date, ppg_std, ppg_l3, ppg_l5, points_sd_std, xppg_std, xppg_l3, xppg_l5, games_with_xp_std,
           target_share_std, target_share_l3, carry_share_std, carry_share_l3, snap_pct_l3, air_yards_share_l3,
           first_read_share_std, first_read_share_l3, route_participation_l3, attempts_std, attempts_l3,
           snap_pct_std,
           {%- for c in component_stats() %}
           {{ c }}_pg_std, {{ c }}_pg_l3,
           {%- endfor %}
           week as asof_week
    from {{ ref('int_player_game_asof') }} as x
    where x.gsis_id = u.gsis_id and x.season = u.season and x.week < u.week
    order by x.week desc
    limit 1
) as a
