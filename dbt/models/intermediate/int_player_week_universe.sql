{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}, {'columns': ['season', 'week', 'position']}], post_hook="analyze {{ this }}") }}
-- Rankings universe: every rostered QB/RB/WR/TE (ACT/INA/RES) x regular-season week in which his
-- team plays. The weekly roster file for a week appears around game day, so the upcoming week uses
-- the latest roster week on or before it (roster_week). Carries the game context (opponent, home,
-- closing line, implied team total).
-- IQ-4 (the bye-week bug): nflverse's weekly file lists only the teams that play that week, so once a bye week's file
-- is out (2026 week 5: no KC, no CAR) the teams on a bye are missing from it, and read across all teams every one of
-- their players dropped out of every later week (no projection, no rest of season, no trade value). A team missing
-- from the newest file reads its own newest file for the weeks after it (`team_fallback`), unless the player is on a
-- newer file elsewhere. Only weeks past the newest file can change: a played week has its own file for every team
-- that plays, so history (and every training row) is untouched.
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
),

-- ---- IQ-4: a team on a bye in the newest file reads its own newest file for the weeks after it
team_files as (
    select distinct season, team, week from {{ ref('int_player_week_team') }}
),

team_fallback as (
    select wr.season, wr.week, t.team, max(t.week) as roster_week
    from week_roster as wr
    join team_files as t on t.season = wr.season and t.week < wr.roster_week
    where wr.week > wr.roster_week
      and not exists (select 1 from team_files as x where x.season = wr.season and x.week = wr.roster_week and x.team = t.team)
    group by 1, 2, 3
),

week_rows as (
    select r.*, wr.week as cal_week, wr.roster_week
    from week_roster as wr
    join {{ ref('int_player_week_team') }} as r on r.season = wr.season and r.week = wr.roster_week
    union all
    select r.*, f.week as cal_week, f.roster_week
    from team_fallback as f
    join {{ ref('int_player_week_team') }} as r on r.season = f.season and r.week = f.roster_week and r.team = f.team
    where not exists (select 1 from {{ ref('int_player_week_team') }} as n      -- on a newer file elsewhere: that one
                      where n.gsis_id = r.gsis_id and n.season = f.season and n.week > f.roster_week and n.week <= f.week)
)
-- ---- end IQ-4

select distinct on (r.gsis_id, r.season, r.cal_week)
    r.gsis_id, r.season, r.cal_week as week, r.team, r.position, r.full_name as player_name, r.roster_status,
    r.roster_week,
    g.game_id,
    case when g.home_team = r.team then g.away_team else g.home_team end as opponent,
    g.home_team = r.team                                                   as is_home,
    g.spread_line, g.total_line,
    case when g.total_line is null or g.spread_line is null then null
         when g.home_team = r.team then (g.total_line + g.spread_line) / 2.0
         else (g.total_line - g.spread_line) / 2.0 end                     as implied_team_total
from week_rows as r                                                                       -- IQ-4
join cal_games as g on g.season = r.season and g.week = r.cal_week and r.team in (g.home_team, g.away_team)
where r.position in ('QB', 'RB', 'WR', 'TE') and r.roster_status in ('ACT', 'INA', 'RES')
order by r.gsis_id, r.season, r.cal_week, g.game_id
