{{ config(indexes=[{'columns': ['team', 'season', 'week']}, {'columns': ['gsis_id', 'season', 'week']}], post_hook="analyze {{ this }}") }}
-- Plan D5 (personnel), helper: per team x regular-season week W (every scheduled game, played or not) and
-- player: his part in the team's last four PLAYED games of the season before W (the window), and whether he
-- is available for week W. The offensive-line and teammate features aggregate it.
--   window        the team's played regular-season games of this season with week < W, the newest four;
--                 week 1 (and a team's first game) has none: no rows
--   snap_share    his offensive snaps over the window / the team's (int_pn_team_game.team_snaps)
--   target_share / carry_share   his targets / carries over the window / the team's (fct_team_game)
--   out_injured   week W: report Out or Doubtful, or on a reserve list (RES = injured reserve / PUP / NFI, PUP,
--                 SUS, EXE, NON) with this team (int_pn_player_week_status)
--   gone          not out_injured and no longer on this team's roster for week W (released, traded, practice
--                 squad): his share is up for grabs too (the C6 absence logic's "traded" / "gone")
--   report_known  the team's week-W injury report is out (it has at least one row)
with tg as (
    select *,
           -- played games of the season so far, counting this one if played: the window is the n_before
           -- newest of them
           count(*) filter (where is_played) over (partition by team, season order by week)::int as played_through
    from {{ ref('int_pn_team_game') }}
),

tw as (       -- every team-week with the number of played games before it
    select season, week, team, played_through - is_played::int as n_before from tg
),

window_games as (
    select tw.season, tw.week, tw.team, g.game_id, g.week as game_week, g.team_snaps, g.team_targets, g.team_carries
    from tw
    join tg as g on g.team = tw.team and g.season = tw.season and g.is_played
                and g.played_through between tw.n_before - 3 and tw.n_before
    where tw.n_before > 0
),

team_window as (
    select season, week, team, count(*)::int as window_games, max(game_week) as last_game_week,
           sum(team_snaps) as team_snaps, sum(team_targets) as team_targets, sum(team_carries) as team_carries
    from window_games group by 1, 2, 3
),

player_window as (
    select w.season, w.week, w.team, p.gsis_id, max(p.pos_group) as pos_group, count(*)::int as games_played,
           sum(p.offense_snaps) as offense_snaps, sum(p.targets) as targets, sum(p.carries) as carries
    from window_games as w
    join {{ ref('int_pn_player_game') }} as p on p.game_id = w.game_id and p.team = w.team and p.played
    group by 1, 2, 3, 4
),

reports as (
    select distinct season, week, coalesce(roster_team, report_team) as team
    from {{ ref('int_pn_player_week_status') }}
    where team_report_known
),

status as (
    select
        pw.season, pw.week, pw.team, pw.gsis_id, pw.pos_group,
        tw.window_games, tw.last_game_week, pw.games_played,
        case when tw.team_snaps > 0 then round(least(1.0, pw.offense_snaps::numeric / tw.team_snaps), 4) end   as snap_share,
        case when tw.team_targets > 0 then round(pw.targets::numeric / tw.team_targets, 4) end                as target_share,
        case when tw.team_carries > 0 then round(pw.carries::numeric / tw.team_carries, 4) end                as carry_share,
        s.report_status, s.roster_status, s.roster_team,
        rp.team is not null                                                                                    as report_known
    from player_window as pw
    join team_window as tw using (season, week, team)
    left join {{ ref('int_pn_player_week_status') }} as s on s.gsis_id = pw.gsis_id and s.season = pw.season and s.week = pw.week
    left join reports as rp on rp.season = pw.season and rp.week = pw.week and rp.team = pw.team
)

select
    s.*,
    coalesce(s.report_status in ('Out', 'Doubtful'), false)
      or coalesce(s.roster_team = s.team and s.roster_status in ('RES', 'PUP', 'SUS', 'EXE', 'NON'), false)   as out_injured,
    not (coalesce(s.report_status in ('Out', 'Doubtful'), false)
         or coalesce(s.roster_team = s.team and s.roster_status in ('RES', 'PUP', 'SUS', 'EXE', 'NON'), false))
      and not coalesce(s.roster_team = s.team and s.roster_status in ('ACT', 'INA'), false)                    as gone
from status as s
