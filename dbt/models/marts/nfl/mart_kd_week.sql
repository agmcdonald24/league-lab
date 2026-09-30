{{ config(indexes=[{'columns': ['position', 'unit_id', 'season', 'week'], 'unique': True}, {'columns': ['season', 'week', 'position']}]) }}
-- Kicker and team-defense units x regular-season week (plan R-13): the rows the K and D/ST
-- projections (`league_lab.kdef`) are fitted on and project, with the game context and, for played
-- weeks, the outcome as stat-line components (priced per league by `mart_player_week_projections`).
-- Grain: position ('K' | 'DEF'), unit_id, season, week.
--   K   : unit_id = gsis_id. Every kicker with a kicking row in the week's game (played), plus every
--         kicker on his team's latest weekly roster (ACT) for a week without one: the upcoming weeks,
--         or a week he was inactive (played = false). sleeper_id via player_id_map (NULL when
--         unmapped: such a kicker is projected but no league row can reach him by id).
--   DEF : unit_id = the Sleeper team-defense id ('KC'; the Rams are 'LAR' where nflverse says 'LA'),
--         one row per team per scheduled game; gsis_id NULL (a team defense has no NFL player id).
-- Outcome columns (out_*) are NULL unless played. K: FG made by distance (50p = 50-59 + 60+), FG
-- missed incl. blocked (and by distance, unblocked: nflverse does not bucket blocked kicks), PAT made,
-- PAT missed incl. blocked. DEF: from mart_kd_team_game (points allowed = the opponent's score).
with cal as (
    select game_id, season, week, home_team, away_team, kickoff_at, is_final
    from {{ ref('dim_game') }}
    where season_type = 'REG' and season >= {{ var('seasons_start') }}
),

tgame as (select * from {{ ref('mart_kd_team_game') }}),

kstats as (
    select distinct on (gsis_id, game_id)
           gsis_id, season, week, {{ kd_team('team') }} as team, game_id, player_name,
           fg_made_0_19, fg_made_20_29, fg_made_30_39, fg_made_40_49, fg_made_50_59 + fg_made_60_ as fg_made_50p,
           fg_missed + fg_blocked as fg_missed,
           fg_missed_0_19, fg_missed_20_29, fg_missed_30_39, fg_missed_40_49, fg_missed_50_59 + fg_missed_60_ as fg_missed_50p,
           pat_made, pat_missed + pat_blocked as pat_missed
    from {{ ref('stg_nflverse__player_stats_week') }}
    where season_type = 'REG' and position = 'K' and season >= {{ var('seasons_start') }}
    order by gsis_id, game_id, (fg_att + pat_att) desc
),

roster_weeks as (
    select distinct season, week as roster_week from {{ ref('int_player_week_team') }}
),

week_roster as (
    select w.season, w.week, max(rw.roster_week) as roster_week
    from (select distinct season, week from cal) as w
    join roster_weeks as rw on rw.season = w.season and rw.roster_week <= w.week
    group by 1, 2
),

kroster as (
    -- kickers on the team's weekly roster (the latest roster week on or before the week), active
    select r.gsis_id, wr.season, wr.week, {{ kd_team('r.team') }} as team, r.full_name as player_name, r.roster_status, c.game_id
    from week_roster as wr
    join {{ ref('int_player_week_team') }} as r on r.season = wr.season and r.week = wr.roster_week
    join cal as c on c.season = wr.season and c.week = wr.week
                 and {{ kd_team('r.team') }} in ({{ kd_team('c.home_team') }}, {{ kd_team('c.away_team') }})
    where r.position = 'K' and r.roster_status = 'ACT'
),

kunits as (
    -- a kicking row decides the team and game of that week; the roster fills the weeks without one
    select distinct on (gsis_id, season, week) gsis_id, season, week, team, game_id, player_name, roster_status, is_stats
    from (
        select gsis_id, season, week, team, game_id, player_name, 'ACT' as roster_status, true as is_stats from kstats
        union all
        select gsis_id, season, week, team, game_id, player_name, roster_status, false as is_stats from kroster
    ) as u
    order by gsis_id, season, week, is_stats desc
),

inj as (
    select distinct on (gsis_id, season, week) gsis_id, season, week, report_status
    from {{ ref('stg_nflverse__injuries') }}
    where season_type = 'REG'
    order by gsis_id, season, week, report_status
),

k as (
    select
        'K'::text                                                        as position,
        u.gsis_id                                                        as unit_id,
        u.gsis_id,
        m.sleeper_id,
        coalesce(dp.player_name, u.player_name)                          as player_name,
        u.team, t.opponent, u.game_id, t.is_home, t.is_dome, t.kickoff_at, t.spread_line, t.total_line,
        t.implied_team_total, t.opp_implied_total, u.season, u.week,
        u.roster_status,
        inj.report_status,
        u.is_stats and coalesce(t.played, false)                         as played,
        case when u.is_stats and coalesce(t.played, false) then s.fg_made_0_19 end                     as out_fg_made_0_19,
        case when u.is_stats and coalesce(t.played, false) then s.fg_made_20_29 end                    as out_fg_made_20_29,
        case when u.is_stats and coalesce(t.played, false) then s.fg_made_30_39 end                    as out_fg_made_30_39,
        case when u.is_stats and coalesce(t.played, false) then s.fg_made_40_49 end                    as out_fg_made_40_49,
        case when u.is_stats and coalesce(t.played, false) then s.fg_made_50p end                      as out_fg_made_50p,
        case when u.is_stats and coalesce(t.played, false) then s.fg_missed end                        as out_fg_missed,
        case when u.is_stats and coalesce(t.played, false) then s.fg_missed_0_19 end                   as out_fg_missed_0_19,
        case when u.is_stats and coalesce(t.played, false) then s.fg_missed_20_29 end                  as out_fg_missed_20_29,
        case when u.is_stats and coalesce(t.played, false) then s.fg_missed_30_39 end                  as out_fg_missed_30_39,
        case when u.is_stats and coalesce(t.played, false) then s.fg_missed_40_49 end                  as out_fg_missed_40_49,
        case when u.is_stats and coalesce(t.played, false) then s.fg_missed_50p end                    as out_fg_missed_50p,
        case when u.is_stats and coalesce(t.played, false) then s.pat_made end                         as out_pat_made,
        case when u.is_stats and coalesce(t.played, false) then s.pat_missed end                       as out_pat_missed,
        null::numeric as out_sacks, null::numeric as out_interceptions, null::numeric as out_fumble_recoveries,
        null::numeric as out_forced_fumbles, null::numeric as out_def_tds, null::numeric as out_st_tds,
        null::numeric as out_safeties, null::numeric as out_blocked_kicks, null::numeric as out_points_allowed
    from kunits as u
    join tgame as t on t.game_id = u.game_id and t.team = u.team
    left join kstats as s on s.gsis_id = u.gsis_id and s.game_id = u.game_id
    left join {{ ref('player_id_map') }} as m on m.gsis_id = u.gsis_id
    left join {{ ref('dim_player') }} as dp on dp.gsis_id = u.gsis_id
    left join inj on inj.gsis_id = u.gsis_id and inj.season = u.season and inj.week = u.week
),

sleeper_def as (
    select sleeper_player_id, full_name from {{ ref('stg_sleeper__players') }} where position = 'DEF'
),

d as (
    select
        'DEF'::text                                                      as position,
        case t.team when 'LA' then 'LAR' else t.team end                 as unit_id,
        null::text                                                       as gsis_id,
        sd.sleeper_player_id                                             as sleeper_id,
        coalesce(sd.full_name, dt.team_name, t.team)                     as player_name,
        t.team, t.opponent, t.game_id, t.is_home, t.is_dome, t.kickoff_at, t.spread_line, t.total_line,
        t.implied_team_total, t.opp_implied_total, t.season, t.week,
        'ACT'::text                                                      as roster_status,
        null::text                                                       as report_status,
        t.played,
        null::numeric as out_fg_made_0_19, null::numeric as out_fg_made_20_29, null::numeric as out_fg_made_30_39,
        null::numeric as out_fg_made_40_49, null::numeric as out_fg_made_50p, null::numeric as out_fg_missed,
        null::numeric as out_fg_missed_0_19, null::numeric as out_fg_missed_20_29, null::numeric as out_fg_missed_30_39,
        null::numeric as out_fg_missed_40_49, null::numeric as out_fg_missed_50p, null::numeric as out_pat_made,
        null::numeric as out_pat_missed,
        case when t.played then t.sacks end                              as out_sacks,
        case when t.played then t.interceptions end                      as out_interceptions,
        case when t.played then t.fumble_recoveries end                  as out_fumble_recoveries,
        case when t.played then t.forced_fumbles end                     as out_forced_fumbles,
        case when t.played then t.def_tds end                            as out_def_tds,
        case when t.played then t.st_tds end                             as out_st_tds,
        case when t.played then t.safeties end                           as out_safeties,
        case when t.played then t.blocked_kicks end                      as out_blocked_kicks,
        case when t.played then t.points_allowed end                     as out_points_allowed
    from tgame as t
    left join sleeper_def as sd on sd.sleeper_player_id = case t.team when 'LA' then 'LAR' else t.team end
    left join {{ ref('dim_team') }} as dt on dt.team_abbr = t.team
)

select * from k
union all
select * from d
