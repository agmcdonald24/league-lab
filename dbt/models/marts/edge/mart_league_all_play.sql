-- Schedule luck. For every scored regular-season week, each roster's record if it had played every
-- other roster ("all-play"); the season all-play win% times games played is the expected win count.
-- luck = actual wins - expected wins. Positive = has beaten its points.
with fm as (
    select league_id, season, week, roster_id, points, result
    from {{ ref('fct_league_matchup') }}
    where is_scored and week_type = 'REG' and not is_bye
),

pairs as (
    select a.league_id, a.season, a.week, a.roster_id, a.points, a.result,
           count(*) filter (where a.points > b.points) as ap_wins,
           count(*) filter (where a.points < b.points) as ap_losses,
           count(*) filter (where a.points = b.points) as ap_ties,
           rank() over (partition by a.league_id, a.week order by a.points desc) as week_points_rank,
           count(*) over (partition by a.league_id, a.week) as rosters_in_week
    from fm as a
    join fm as b on b.league_id = a.league_id and b.week = a.week and b.roster_id <> a.roster_id
    group by a.league_id, a.season, a.week, a.roster_id, a.points, a.result
),

season as (
    select league_id, season, roster_id,
           count(*) as games,
           count(*) filter (where result = 'W') as wins,
           count(*) filter (where result = 'L') as losses,
           sum(ap_wins) as all_play_wins, sum(ap_losses) as all_play_losses, sum(ap_ties) as all_play_ties,
           count(*) filter (where week_points_rank <= rosters_in_week / 2.0) as top_half_weeks,
           round(avg(week_points_rank), 2) as avg_points_rank
    from pairs
    group by 1, 2, 3
)

select
    s.league_id, s.season, s.roster_id, m.team_name, m.manager_name,
    s.games, s.wins, s.losses,
    s.all_play_wins, s.all_play_losses, s.all_play_ties,
    round(s.all_play_wins::numeric / nullif(s.all_play_wins + s.all_play_losses + s.all_play_ties, 0), 4) as all_play_win_pct,
    round(s.games * s.all_play_wins::numeric / nullif(s.all_play_wins + s.all_play_losses + s.all_play_ties, 0), 2) as expected_wins,
    round(s.wins - s.games * s.all_play_wins::numeric / nullif(s.all_play_wins + s.all_play_losses + s.all_play_ties, 0), 2) as luck_wins,
    s.top_half_weeks,
    s.avg_points_rank,
    rank() over (partition by s.league_id order by s.all_play_wins desc) as all_play_rank
from season as s
left join {{ ref('dim_league_member') }} as m using (league_id, roster_id)
