-- Kicker streaming, realized outcomes only (plan §1): the kicker each roster *started* each
-- scored week and how that compared with the other started kickers that week.
with k as (
    select
        league_id, season, week, roster_id, sleeper_player_id, gsis_id, player_name,
        points_observed as points, nfl_team
    from {{ ref('league_player_week') }}
    where is_starter and slot = 'K' and is_scored_week
),

wk as (
    select
        league_id, week,
        avg(points) as week_avg_started_k, percentile_cont(0.5) within group (order by points) as week_median_started_k,
        max(points) as week_best_started_k, count(*) as kickers_started
    from k group by 1, 2
),

changes as (
    select
        league_id, roster_id, week, sleeper_player_id,
        lag(sleeper_player_id) over (partition by league_id, roster_id order by week) as prev_kicker_id
    from k
)

select
    k.league_id, k.season, k.week, k.roster_id, m.team_name, m.manager_name,
    k.sleeper_player_id, k.gsis_id, k.player_name as kicker_name, k.nfl_team, k.points,
    wk.week_avg_started_k, wk.week_median_started_k, wk.week_best_started_k, wk.kickers_started,
    round(k.points - wk.week_avg_started_k, 2)                as points_vs_week_avg,
    rank() over (partition by k.league_id, k.week order by k.points desc) as week_rank,
    c.prev_kicker_id is not null and c.prev_kicker_id <> k.sleeper_player_id as changed_kicker
from k
join wk using (league_id, week)
left join changes as c using (league_id, roster_id, week, sleeper_player_id)
left join {{ ref('dim_league_member') }} as m using (league_id, roster_id)
