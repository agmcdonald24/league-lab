{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}, {'columns': ['season', 'week', 'position']}], post_hook="analyze {{ this }}") }}
-- Rankings universe: every rostered QB/RB/WR/TE (ACT/INA/RES) x regular-season week in which his
-- team plays. The weekly roster file for a week appears around game day, so the upcoming week uses
-- the latest roster week on or before it (roster_week). Carries the game context (opponent, home,
-- closing line, implied team total).
with cal_games as (
    select game_id, season, week, home_team, away_team, spread_line, total_line
    from {{ ref('dim_game') }}
    where season_type = 'REG' and season >= {{ var('seasons_start') }}
),

roster_weeks as (
    select distinct season, week as roster_week from {{ ref('int_player_week_team') }}
),

week_roster as (
    select w.season, w.week, max(rw.roster_week) as roster_week
    from (select distinct season, week from cal_games) as w
    join roster_weeks as rw on rw.season = w.season and rw.roster_week <= w.week
    group by 1, 2
)

select distinct on (r.gsis_id, wr.season, wr.week)
    r.gsis_id, wr.season, wr.week, r.team, r.position, r.full_name as player_name, r.roster_status,
    wr.roster_week,
    g.game_id,
    case when g.home_team = r.team then g.away_team else g.home_team end as opponent,
    g.home_team = r.team                                                   as is_home,
    g.spread_line, g.total_line,
    case when g.total_line is null or g.spread_line is null then null
         when g.home_team = r.team then (g.total_line + g.spread_line) / 2.0
         else (g.total_line - g.spread_line) / 2.0 end                     as implied_team_total
from week_roster as wr
join {{ ref('int_player_week_team') }} as r on r.season = wr.season and r.week = wr.roster_week
join cal_games as g on g.season = wr.season and g.week = wr.week and r.team in (g.home_team, g.away_team)
where r.position in ('QB', 'RB', 'WR', 'TE') and r.roster_status in ('ACT', 'INA', 'RES')
order by r.gsis_id, wr.season, wr.week, g.game_id
