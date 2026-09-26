-- Player x season x week affiliation with the game played that week (null on byes / no game).
with rw as (
    select * from {{ ref('int_player_week_team') }}
),

games as (
    select game_id, season, week, home_team, away_team from {{ ref('dim_game') }}
)

select
    rw.gsis_id,
    rw.season,
    rw.season_type,
    rw.week,
    rw.team,
    g.game_id,
    case when g.game_id is null then null
         when g.home_team = rw.team then g.away_team else g.home_team end as opponent,
    rw.position,
    rw.depth_chart_position,
    rw.roster_status,
    rw.roster_status_detail,
    rw.full_name
from rw
left join games as g
       on g.season = rw.season and g.week = rw.week
      and rw.team in (g.home_team, g.away_team)
