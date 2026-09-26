-- Per roster-season kicker outcomes over the weeks every roster started a kicker (common
-- eligible weeks), plus how many distinct kickers were started and acquired.
with kw as (select * from {{ ref('mart_league_kicker_week') }}),

common_weeks as (
    -- weeks in which every roster that started any kicker that season started one
    select league_id, week
    from kw
    group by 1, 2
    having count(distinct roster_id) = (select count(distinct roster_id) from kw as x where x.league_id = kw.league_id)
),

acq as (
    select tp.league_id, tp.roster_id, count(*) as kicker_acquisitions
    from {{ ref('stg_sleeper__transaction_players') }} as tp
    join {{ ref('stg_sleeper__players') }} as p using (sleeper_player_id)
    where tp.action = 'add' and p.position = 'K' and tp.status = 'complete'
    group by 1, 2
)

select
    kw.league_id, kw.season, kw.roster_id, kw.team_name, kw.manager_name,
    count(*)                                              as weeks_started_k,
    count(*) filter (where cw.week is not null)           as common_weeks,
    round(sum(kw.points), 2)                              as total_points,
    round(sum(kw.points) filter (where cw.week is not null), 2) as total_points_common_weeks,
    round(avg(kw.points) filter (where cw.week is not null), 2) as avg_points_common_weeks,
    round(stddev_samp(kw.points) filter (where cw.week is not null), 2) as stddev_points_common_weeks,
    round(avg(kw.points_vs_week_avg), 2)                  as avg_points_vs_week_avg,
    count(distinct kw.sleeper_player_id)                  as distinct_kickers_started,
    count(*) filter (where kw.changed_kicker)             as kicker_changes,
    coalesce(max(a.kicker_acquisitions), 0)               as kicker_acquisitions,
    rank() over (partition by kw.league_id order by sum(kw.points) filter (where cw.week is not null) desc nulls last) as rank_common_weeks
from kw
left join common_weeks as cw using (league_id, week)
left join acq as a using (league_id, roster_id)
group by 1, 2, 3, 4, 5
