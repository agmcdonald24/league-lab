-- D5 (personnel): pn_ol_starters_out re-derived from the RAW tables on its own path - nflverse snap counts by PFR
-- id (mapped like int_pfr_gsis_map: one gsis id per PFR id), the schedule, the injury report and the weekly roster,
-- none of the D5 helpers - for every team-week of 2016-2026 the model fills. The window is the team's newest four
-- PLAYED regular-season games with week < W (a row may never see its own game); "out" is week W's report (Out /
-- Doubtful) or a reserve list on week W's roster. Returns the team-weeks where the two disagree.
{{ config(severity='error') }}
with sched as (
    select s.game_id, s.season, s.week, {{ kd_team('t.team') }} as team, s.home_score is not null as played
    from {{ source('raw', 'nfl_schedules') }} as s
    cross join lateral (values (s.home_team), (s.away_team)) as t(team)
    where s.game_type = 'REG' and s.season >= {{ var('seasons_start') }}
),

team_weeks as (
    select distinct season, week, team from sched
),

windows as (               -- the newest four played games before the week
    select tw.season, tw.week, tw.team, g.game_id, g.week as game_week
    from team_weeks as tw
    cross join lateral (
        select game_id, week from sched as g
        where g.team = tw.team and g.season = tw.season and g.played and g.week < tw.week
        order by g.week desc limit 4
    ) as g
),

ids as (
    select pfr_id, min(gsis_id) as gsis_id from {{ source('raw', 'nfl_players') }}
    where pfr_id is not null group by pfr_id having count(distinct gsis_id) = 1
),

snaps as (
    select s.game_id, {{ kd_team('s.team') }} as team, i.gsis_id, s.position, s.offense_snaps, s.offense_pct
    from {{ source('raw', 'nfl_snap_counts') }} as s
    join ids as i on i.pfr_id = s.pfr_player_id
    where s.game_type = 'REG' and s.offense_snaps > 0
),

roster_pos as (            -- the roster's position wins over the snap file's (as the model does)
    select distinct on (gsis_id, season, week) gsis_id, season, week, position
    from {{ source('raw', 'nfl_rosters_weekly') }}
    where game_type = 'REG' and gsis_id is not null
    order by gsis_id, season, week, (status = 'ACT') desc, team
),

ol_window as (
    select w.season, w.week, w.team, s.gsis_id, sum(s.offense_snaps) as snaps
    from windows as w
    join snaps as s on s.game_id = w.game_id and s.team = w.team
    left join roster_pos as rp on rp.gsis_id = s.gsis_id and rp.season = w.season and rp.week = w.game_week
    where coalesce(rp.position, case when s.position in ('T', 'G', 'C', 'OL', 'OT', 'OG') then 'OL' end) = 'OL'
    group by 1, 2, 3, 4
),

starters as (
    select * from (select o.*, row_number() over (partition by season, week, team order by snaps desc, gsis_id) as rn
                   from ol_window as o) as x
    where rn <= 5
),

roster_week as (
    select tw.season, tw.week, max(r.week) as roster_week
    from (select distinct season, week from team_weeks) as tw
    join (select distinct season, week from {{ source('raw', 'nfl_rosters_weekly') }} where game_type = 'REG') as r
      on r.season = tw.season and r.week <= tw.week
    group by 1, 2
),

out_flags as (
    select st.season, st.week, st.team, st.gsis_id,
           exists (select 1 from {{ source('raw', 'nfl_injuries') }} as i
                   where i.gsis_id = st.gsis_id and i.season = st.season and i.week = st.week and i.game_type = 'REG'
                     and i.report_status in ('Out', 'Doubtful'))
           or exists (select 1 from {{ source('raw', 'nfl_rosters_weekly') }} as r
                      join roster_week as rw on rw.season = r.season and rw.roster_week = r.week
                      where r.gsis_id = st.gsis_id and r.season = st.season and rw.week = st.week and r.game_type = 'REG'
                        and {{ kd_team('r.team') }} = st.team and r.status in ('RES', 'PUP', 'SUS', 'EXE', 'NON')) as is_out
    from starters as st
),

raw_count as (
    select season, week, team, count(*) filter (where is_out)::int as starters_out
    from out_flags group by 1, 2, 3
),

model as (
    select distinct season, week, team, pn_ol_starters_out
    from {{ ref('int_player_week_personnel') }}
    where pn_ol_starters_out is not null
)

select m.season, m.week, m.team, m.pn_ol_starters_out, r.starters_out as raw_starters_out
from model as m
left join raw_count as r using (season, week, team)
where m.pn_ol_starters_out is distinct from coalesce(r.starters_out, 0)
