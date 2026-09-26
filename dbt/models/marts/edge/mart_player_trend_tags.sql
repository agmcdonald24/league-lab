-- One row per player x season with the readable summary of mart_player_trends:
--   tags       "↑ target share, ↑ snaps, ↓ aDOT"  (significant directions, strongest first)
--   momentum   average z over *opportunity* metrics (targets, snaps, carries, expected points…);
--              positive = role growing, negative = role shrinking. Points are excluded on purpose:
--              this is about opportunity, not last week's touchdown.
with t as (
    select * from {{ ref('mart_player_trends') }}
),

tags as (
    select gsis_id, season,
           string_agg(case when direction = 'up' then '↑ ' else '↓ ' end || arrow_label, ', ' order by abs(z) desc)
               filter (where direction in ('up', 'down')) as tags,
           count(*) filter (where direction = 'up') as n_up,
           count(*) filter (where direction = 'down') as n_down,
           count(*) filter (where direction = 'insufficient') as n_insufficient,
           round(avg(z) filter (where is_opportunity), 2) as momentum,
           max(games) as games, max(latest_week) as latest_week,
           max(player_name) as player_name, max(position) as position, max(team) as team
    from t
    group by 1, 2
),

pivot as (
    select gsis_id, season,
           max(case when metric = 'target_share' then value_l3 end) as target_share_l3,
           max(case when metric = 'target_share' then change end) as target_share_change,
           max(case when metric = 'target_share' then z end) as target_share_z,
           max(case when metric = 'snap_share' then value_l3 end) as snap_share_l3,
           max(case when metric = 'snap_share' then change end) as snap_share_change,
           max(case when metric = 'snap_share' then z end) as snap_share_z,
           max(case when metric = 'carry_share' then change end) as carry_share_change,
           max(case when metric = 'carry_share' then z end) as carry_share_z,
           max(case when metric = 'air_yards_share' then change end) as air_yards_share_change,
           max(case when metric = 'adot' then change end) as adot_change,
           max(case when metric = 'expected_points' then value_l3 end) as expected_points_l3,
           max(case when metric = 'expected_points' then change end) as expected_points_change,
           max(case when metric = 'expected_points' then z end) as expected_points_z,
           max(case when metric = 'points' then value_l3 end) as points_l3,
           max(case when metric = 'points' then change end) as points_change
    from t
    group by 1, 2
)

select
    tg.gsis_id, tg.season, tg.player_name, tg.position, tg.team, tg.games, tg.latest_week,
    coalesce(tg.tags, case when tg.n_insufficient > 0 and tg.games < 4 then 'not enough games yet' else 'steady' end) as tags,
    tg.n_up, tg.n_down, tg.momentum,
    case when tg.games < 4 then 'insufficient'
         when tg.momentum >= 1 then 'rising' when tg.momentum <= -1 then 'falling' else 'steady' end as opportunity_trend,
    p.target_share_l3, p.target_share_change, p.target_share_z,
    p.snap_share_l3, p.snap_share_change, p.snap_share_z,
    p.carry_share_change, p.carry_share_z, p.air_yards_share_change, p.adot_change,
    p.expected_points_l3, p.expected_points_change, p.expected_points_z,
    p.points_l3, p.points_change
from tags as tg
left join pivot as p using (gsis_id, season)
