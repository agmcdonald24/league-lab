-- Regular-season standings per league-season computed from scored matchups, next to the
-- W/L/PF Sleeper reports on the roster (a dbt test checks they agree for completed seasons).
with fm as (
    select * from {{ ref('fct_league_matchup') }} where is_scored and week_type = 'REG' and not is_bye
),

agg as (
    select
        league_id, season, roster_id,
        count(*) filter (where result = 'W') as wins,
        count(*) filter (where result = 'L') as losses,
        count(*) filter (where result = 'T') as ties,
        round(sum(points), 2) as points_for,
        round(sum(opponent_points), 2) as points_against,
        round(avg(points), 2) as avg_points,
        round(stddev_samp(points), 2) as stddev_points,
        max(points) as best_week,
        min(points) as worst_week,
        count(*) as games
    from fm
    group by 1, 2, 3
),

champ as (
    select league_id, winner_roster_id as roster_id, true as is_champion
    from {{ ref('stg_sleeper__brackets') }}
    where bracket_type = 'winners' and place_decided = 1
)

select
    a.league_id, a.season, a.roster_id,
    m.manager_name, m.team_name,
    a.wins, a.losses, a.ties, a.games,
    round(a.wins::numeric / nullif(a.games, 0), 3)             as win_pct,
    a.points_for, a.points_against, a.avg_points, a.stddev_points, a.best_week, a.worst_week,
    rank() over (partition by a.league_id order by a.wins desc, a.points_for desc) as standing,
    m.sleeper_wins, m.sleeper_losses, m.sleeper_points_for, m.sleeper_potential_points,
    case when m.sleeper_potential_points > 0
         then round(a.points_for / m.sleeper_potential_points, 4) end as lineup_efficiency,
    coalesce(c.is_champion, false)                              as is_champion
from agg as a
left join {{ ref('dim_league_member') }} as m using (league_id, roster_id)
left join champ as c using (league_id, roster_id)
