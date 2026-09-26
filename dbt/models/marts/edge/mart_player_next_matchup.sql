-- Every skill player on a current NFL roster: next game (or bye), the opposing defense's
-- points-allowed rank for the player's position, latest injury report and depth-chart rank.
with cal as (select * from {{ ref('int_nfl_calendar') }}),

roster as (
    -- latest weekly roster row per player in the current season
    select distinct on (gsis_id) gsis_id, team, position, roster_status, depth_chart_position, week as roster_week
    from {{ ref('int_player_week_team') }}
    where season = (select season from cal)
    order by gsis_id, week desc
),

games as (
    select g.*, cal.next_week
    from {{ ref('dim_game') }} as g join cal on g.season = cal.season and g.week = cal.next_week
),

inj as (
    select distinct on (gsis_id) gsis_id, week as injury_week, report_status, report_primary_injury, practice_status
    from {{ ref('stg_nflverse__injuries') }}
    where season = (select season from cal)
    order by gsis_id, week desc
),

dc as (
    select gsis_id, min(pos_rank) as depth_rank, string_agg(distinct pos_abb, '/') as depth_pos
    from {{ ref('int_depth_chart_current') }}
    group by 1
)

select
    r.gsis_id,
    p.player_name,
    r.position,
    r.team,
    r.roster_status,
    cal.season,
    cal.next_week,
    g.game_id,
    case when g.home_team = r.team then g.away_team else g.home_team end  as opponent,
    g.home_team = r.team                                                 as is_home,
    g.kickoff_at,
    g.game_id is null                                                    as is_bye,
    dvp.points_allowed_per_game_std                                      as opp_points_allowed_pg_std,
    dvp.rank_std                                                         as opp_rank_std,
    dvp.points_allowed_per_game_l4                                       as opp_points_allowed_pg_l4,
    dvp.rank_l4                                                          as opp_rank_l4,
    inj.report_status                                                    as injury_status,
    inj.report_primary_injury                                            as injury,
    inj.practice_status,
    inj.injury_week,
    dc.depth_rank,
    dc.depth_pos
from roster as r
join cal on true
left join {{ ref('dim_player') }} as p using (gsis_id)
left join games as g on r.team in (g.home_team, g.away_team)
left join {{ ref('mart_defense_vs_position_current') }} as dvp
       on dvp.defense = case when g.home_team = r.team then g.away_team else g.home_team end
      and dvp.position = r.position
left join inj using (gsis_id)
left join dc using (gsis_id)
where r.position in ('QB', 'RB', 'WR', 'TE', 'K')
