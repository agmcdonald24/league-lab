{{ config(indexes=[{'columns': ['season', 'gsis_id']}, {'columns': ['season', 'metric', 'direction']}]) }}
-- Player x season x metric: is the metric trending, by how much, and is the move bigger than the
-- player's own week-to-week noise?
--   value_l3     last three games played (sum/sum for shares)
--   value_prior  the games before those
--   change       value_l3 - value_prior
--   z            change measured in standard errors of the player's own game-to-game spread
--                (heuristic: sd over all games x sqrt(1/3 + 1/n_prior)); |z| >= 1 moderate, >= 2 strong
--   slope        least-squares slope of the per-game value over the season (per game)
--   direction    up / down / flat / insufficient (< 4 games or < 1 prior game)
-- A direction needs BOTH a practical minimum change (trend_metrics.min_change) and |z| >= 1.
with m as (
    select *, case when den > 0 then num / den end as value, games - game_no as games_from_end
    from {{ ref('int_player_game_metric_long') }}
),

agg as (
    select
        gsis_id, season, metric,
        max(player_name) as player_name,
        max(position) as position,
        (array_agg(team order by week desc))[1] as team,
        max(week) as latest_week,
        max(games) as games,
        count(*) filter (where value is not null) as games_with_metric,
        sum(num) filter (where games_from_end < 3) / nullif(sum(den) filter (where games_from_end < 3), 0) as value_l3,
        sum(num) filter (where games_from_end >= 3) / nullif(sum(den) filter (where games_from_end >= 3), 0) as value_prior,
        sum(num) / nullif(sum(den), 0) as value_season,
        count(*) filter (where games_from_end < 3 and value is not null) as n_l3,
        count(*) filter (where games_from_end >= 3 and value is not null) as n_prior,
        avg(value) filter (where games_from_end < 3) as mean_l3_per_game,
        avg(value) filter (where games_from_end >= 3) as mean_prior_per_game,
        stddev_samp(value) as sd_game,
        regr_slope(value, game_no) as slope_per_game,
        (array_agg(value order by week desc))[1] as value_latest
    from m
    group by 1, 2, 3
),

scored as (
    select
        a.*,
        t.label as metric_label, t.arrow_label, t.min_change, t.is_opportunity, t.display_kind,
        round(a.value_l3 - a.value_prior, 4) as change,
        case when a.sd_game > 0 and a.n_l3 >= 1 and a.n_prior >= 1
             then round((a.mean_l3_per_game - a.mean_prior_per_game) / (a.sd_game * sqrt(1.0 / a.n_l3 + 1.0 / a.n_prior)), 2) end as z
    from agg as a
    join {{ ref('trend_metrics') }} as t using (metric)
)

select
    *,
    case
        when games < 4 or n_prior < 1 or n_l3 < 1 then 'insufficient'
        when change >= min_change and z >= 1 then 'up'
        when change <= -min_change and z <= -1 then 'down'
        else 'flat'
    end as direction,
    case when z is null then null when abs(z) >= 2 then 'strong' when abs(z) >= 1 then 'moderate' else 'weak' end as confidence
from scored
