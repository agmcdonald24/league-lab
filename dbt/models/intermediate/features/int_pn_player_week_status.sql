{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}, {'columns': ['roster_team', 'season', 'week']}], post_hook="analyze {{ this }}") }}
-- Plan D5 (personnel), helper: every QB / RB / WR / TE / offensive lineman's availability for each
-- regular-season week W of 2016 on, as it stands BEFORE week W's kickoff - the only status a week-W feature
-- reads. One row per player x week for players on a weekly roster (the newest roster week <= W, the
-- universe's rule, so an upcoming week uses the latest roster) or on week W's injury report.
--   report_status / practice_status   week W's injury report (nflverse `injuries`: the team's final
--                     game-status report of the week - Friday for a Sunday game, Wednesday/Thursday for a
--                     Thursday game; median 47-55 h before kickoff where nflverse stamps it, 2016-24); NULL =
--                     not on the report; '' and 'Note' count as not listed
--   roster_status     the weekly roster's status. Only the reserve lists are read downstream (RES = injured
--                     reserve / PUP / NFI, PUP, SUS, EXE, NON: placed before the roster deadline). ACT vs INA is
--                     never read: INA is the game-day inactive list (0 of 7,204 INA player-weeks 2022-25 played)
--   team_report_known the player's team (roster team, else report team) has at least one row on week W's
--                     report: the report is out. An unpublished report is unknown, not "nobody hurt".
with weeks as (
    select distinct season, week from {{ ref('int_pn_team_game') }}
),

roster_weeks as (
    select w.season, w.week, max(r.week) as roster_week
    from weeks as w
    join (select distinct season, week from {{ ref('int_player_week_team') }} where season_type = 'REG') as r
      on r.season = w.season and r.week <= w.week
    group by 1, 2
),

roster as (
    select r.gsis_id, w.season, w.week, w.roster_week, {{ kd_team('r.team') }} as roster_team, r.roster_status
    from roster_weeks as w
    join {{ ref('int_player_week_team') }} as r on r.season = w.season and r.week = w.roster_week and r.season_type = 'REG'
    where r.position in ('QB', 'RB', 'WR', 'TE', 'OL')
),

inj as (
    select gsis_id, season, week, {{ kd_team('team') }} as report_team,
           case when report_status in ('Out', 'Doubtful', 'Questionable') then report_status end as report_status,
           case when practice_status ilike 'Did Not%' then 'DNP' when practice_status ilike 'Limited%' then 'Limited'
                when practice_status ilike 'Full%' then 'Full' end as practice_status
    from {{ ref('stg_nflverse__injuries') }}
    where game_type = 'REG' and season >= {{ var('seasons_start') }}
),

reports as (
    select distinct season, week, report_team as team from inj
),

joined as (
    select coalesce(r.gsis_id, i.gsis_id) as gsis_id, coalesce(r.season, i.season) as season, coalesce(r.week, i.week) as week,
           r.roster_week, r.roster_team, r.roster_status, i.report_team, i.report_status, i.practice_status,
           i.gsis_id is not null as on_report
    from roster as r
    full join inj as i on i.gsis_id = r.gsis_id and i.season = r.season and i.week = r.week
)

select j.*,
       rp.team is not null as team_report_known
from joined as j
left join reports as rp on rp.season = j.season and rp.week = j.week and rp.team = coalesce(j.roster_team, j.report_team)
