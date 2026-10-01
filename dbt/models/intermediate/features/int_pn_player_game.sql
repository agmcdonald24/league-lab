{{ config(indexes=[{'columns': ['team', 'season', 'week']}, {'columns': ['gsis_id', 'season', 'week']}], post_hook="analyze {{ this }}") }}
-- Plan D5 (personnel), helper 2 of 3: what happened to each QB / RB / WR / TE / offensive lineman in each of
-- his team's PLAYED regular-season games (2016 on), the history every personnel feature reads from (always
-- through `week < W` for a week-W row). One code per franchise (kd_team), so the Raiders 2016-19 and the
-- Chargers 2016 are here (int_player_game_role joins dim_game's OAK / SD to fct_team_game's LV / LAC and
-- loses them).
-- Rows: the team's weekly roster that week (any status: active, inactive, reserve ...), plus anyone with a
-- snap or stat row for the team in the game (a call-up).
--   pos_group     QB / RB / WR / TE / OL (roster position first, then the snap file's, then the player file's)
--   played        offensive snaps > 0, or a stat row that says he played
--   status        'played' / 'missed_injured' (did not play and was on that week's injury report - Out,
--                 Doubtful or Questionable - or on a reserve list: the C6 rule) / 'missed_other' (healthy
--                 scratch, benched, inactive)
--   snap_share    offensive snaps / the team's (0 when the team has snap counts and he has none; NULL without)
--   starting_qb_id / started_qb   the schedule's starting QB of the game / he is that QB
--   injured_miss_streak   games in a row missed injured through this one (his own team-games, across seasons)
--   points        reference-scoring points (fct_player_game.points_current_scoring; NULL without a stat row)
with tg as (
    select * from {{ ref('int_pn_team_game') }} where is_played
),

roster as (
    select gsis_id, season, week, {{ kd_team('team') }} as team, roster_status,
           case when position = 'OL' then 'OL' else position end as pos
    from {{ ref('int_player_week_team') }}
    where season_type = 'REG' and season >= {{ var('seasons_start') }} and position in ('QB', 'RB', 'WR', 'TE', 'OL')
),

snaps as (
    select gsis_id, game_id, {{ kd_team('team') }} as team, offense_snaps,
           case when snap_position in ('T', 'G', 'C', 'OL', 'OT', 'OG') then 'OL'
                when snap_position in ('QB', 'RB', 'WR', 'TE') then snap_position end as pos
    from {{ ref('int_player_game_snaps') }}
    where game_type = 'REG'
),

stats as (
    select gsis_id, game_id, team, position as pos, played, targets, carries, points_current_scoring as points
    from {{ ref('fct_player_game') }}
    where season_type = 'REG' and position in ('QB', 'RB', 'WR', 'TE')
),

inj as materialized (
    select gsis_id, season, week, nullif(report_status, '') as report_status
    from {{ ref('stg_nflverse__injuries') }}
    where game_type = 'REG'
),

keys as (
    select r.gsis_id, t.game_id, t.team from roster as r join tg as t using (season, week, team)
    union
    select s.gsis_id, s.game_id, s.team from snaps as s join tg as t using (game_id, team) where s.pos is not null
    union
    select st.gsis_id, st.game_id, st.team from stats as st join tg as t using (game_id, team)
),

rows_ as (
    select
        k.gsis_id, t.season, t.week, k.game_id, k.team, t.game_no,
        coalesce(r.pos, sn.pos, st.pos, case when dp.position in ('T', 'G', 'C', 'OL', 'OT', 'OG') then 'OL' else dp.position end) as pos_group,
        r.roster_status, i.report_status,
        coalesce(sn.offense_snaps, 0) > 0 or coalesce(st.played, false)                      as played,
        case when coalesce(sn.offense_snaps, 0) > 0 or coalesce(st.played, false) then 'played'
             when i.report_status in ('Out', 'Doubtful', 'Questionable') or r.roster_status in ('RES', 'PUP') then 'missed_injured'
             else 'missed_other' end                                                           as status,
        case when sn.offense_snaps is not null then sn.offense_snaps
             when t.team_snaps is not null then 0 end                                          as offense_snaps,
        case when t.team_snaps > 0 then least(1.0, coalesce(sn.offense_snaps, 0)::numeric / t.team_snaps) end as snap_share,
        coalesce(st.targets, 0)                                                                as targets,
        coalesce(st.carries, 0)                                                                as carries,
        st.points,
        t.starting_qb_id,
        k.gsis_id = t.starting_qb_id                                                           as started_qb
    from keys as k
    join tg as t on t.game_id = k.game_id and t.team = k.team
    left join roster as r on r.gsis_id = k.gsis_id and r.season = t.season and r.week = t.week and r.team = k.team
    left join snaps as sn on sn.gsis_id = k.gsis_id and sn.game_id = k.game_id and sn.team = k.team
    left join stats as st on st.gsis_id = k.gsis_id and st.game_id = k.game_id and st.team = k.team
    left join inj as i on i.gsis_id = k.gsis_id and i.season = t.season and i.week = t.week
    left join {{ ref('dim_player') }} as dp on dp.gsis_id = k.gsis_id
    where coalesce(r.pos, sn.pos, st.pos, case when dp.position in ('T', 'G', 'C', 'OL', 'OT', 'OG') then 'OL' else dp.position end) in ('QB', 'RB', 'WR', 'TE', 'OL')
)

select r.*,
       -- games in a row he has missed injured, through this one (0 when he played or missed for another reason;
       -- across seasons: his previous team-game may be last season's)
       case when r.status = 'missed_injured'
            then r.rk - coalesce(max(case when r.status <> 'missed_injured' then r.rk end)
                                   over (partition by r.gsis_id order by r.rk rows between unbounded preceding and current row), 0)
            else 0 end::int as injured_miss_streak
from (select x.*, row_number() over (partition by x.gsis_id order by x.season, x.week) as rk from rows_ as x) as r
