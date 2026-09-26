-- Defense x position: is the unit getting softer or stiffer? Same L3-vs-prior logic as players,
-- on fantasy points allowed per game.
with d as (
    select defense, season, position, week, game_no, points_allowed,
           max(game_no) over (partition by defense, season, position) as games
    from {{ ref('mart_defense_vs_position') }}
),

agg as (
    select defense, season, position, max(games) as games, max(week) as latest_week,
           avg(points_allowed) filter (where games - game_no < 3) as allowed_l3,
           avg(points_allowed) filter (where games - game_no >= 3) as allowed_prior,
           avg(points_allowed) as allowed_season,
           count(*) filter (where games - game_no >= 3) as n_prior,
           stddev_samp(points_allowed) as sd_game,
           regr_slope(points_allowed, game_no) as slope_per_game
    from d
    group by 1, 2, 3
)

select
    *,
    round(allowed_l3 - allowed_prior, 2) as change,
    case when sd_game > 0 and n_prior >= 1
         then round((allowed_l3 - allowed_prior) / (sd_game * sqrt(1.0 / 3 + 1.0 / n_prior)), 2) end as z,
    case when games < 4 or n_prior < 1 then 'insufficient'
         when allowed_l3 - allowed_prior >= 3 and (allowed_l3 - allowed_prior) / nullif(sd_game * sqrt(1.0 / 3 + 1.0 / n_prior), 0) >= 1 then 'softer'
         when allowed_l3 - allowed_prior <= -3 and (allowed_l3 - allowed_prior) / nullif(sd_game * sqrt(1.0 / 3 + 1.0 / n_prior), 0) <= -1 then 'stiffer'
         else 'steady' end as direction
from agg
