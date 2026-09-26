-- Weekly detail behind mart_league_all_play (all-play wins per week and points rank).
with fm as (
    select league_id, season, week, roster_id, points, result, opponent_points
    from {{ ref('fct_league_matchup') }}
    where is_scored and week_type = 'REG' and not is_bye
)
select a.league_id, a.season, a.week, a.roster_id, m.team_name, a.points, a.opponent_points, a.result,
       count(*) filter (where a.points > b.points) as all_play_wins,
       count(*) filter (where a.points < b.points) as all_play_losses,
       rank() over (partition by a.league_id, a.week order by a.points desc) as week_points_rank,
       percentile_cont(0.5) within group (order by b.points) as week_median_others
from fm as a
join fm as b on b.league_id = a.league_id and b.week = a.week and b.roster_id <> a.roster_id
left join {{ ref('dim_league_member') }} as m on m.league_id = a.league_id and m.roster_id = a.roster_id
group by a.league_id, a.season, a.week, a.roster_id, m.team_name, a.points, a.opponent_points, a.result
