{{ config(indexes=[{'columns': ['season', 'week', 'defense', 'position'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- For every (season, week, defense, position): points allowed to the position as of the games
-- before that week, and the league-wide average as of the same point.
with keys as (
    select distinct season, week, opponent as defense, position from {{ ref('int_player_week_universe') }}
),

latest as (
    select k.season, k.week, k.defense, k.position, d.*
    from keys as k
    cross join lateral (
        select points_allowed_per_game_std as opp_allowed_std, points_allowed_per_game_l4 as opp_allowed_l4,
               rank_std as opp_rank_std, game_no as opp_games
        from {{ ref('mart_defense_vs_position') }} as d
        where d.defense = k.defense and d.season = k.season and d.position = k.position and d.week < k.week
        order by d.week desc
        limit 1
    ) as d
),

league_avg as (
    select w.season, w.week, w.position, round(avg(d.points_allowed), 3) as league_allowed_avg
    from (select distinct season, week, position from keys) as w
    join {{ ref('mart_defense_vs_position') }} as d on d.season = w.season and d.position = w.position and d.week < w.week
    group by 1, 2, 3
)

select k.season, k.week, k.defense, k.position,
       l.opp_allowed_std, l.opp_allowed_l4, l.opp_rank_std, l.opp_games, la.league_allowed_avg
from keys as k
left join latest as l using (season, week, defense, position)
left join league_avg as la using (season, week, position)
