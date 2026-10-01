{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- Plan D5 (Wave D round 2): the personnel feature group (`pn_`), evaluated by the D1 harness
-- (`league-lab experiment personnel qb oline teammates own_injury`; src/league_lab/feature_groups/personnel.py).
-- One row per int_player_week_universe row. Every input is known before week W's kickoff: history comes from the
-- team's / player's PLAYED regular-season games with week < W (int_pn_player_game, int_pn_window_player), the
-- quarterback from the published schedule (the projected starter for a game not played yet), availability from
-- week W's injury report and the reserve lists (int_pn_player_week_status). NULL = not known (week 1 for the
-- in-season inputs, an injury report not published yet, a projected starter not filled in yet).
-- Definitions and the evidence: docs/METRICS.md § "Personnel".
with u as (
    select gsis_id, season, week, game_id, {{ kd_team('team') }} as team, position
    from {{ ref('int_player_week_universe') }}
),

tg as (
    select * from {{ ref('int_pn_team_game') }}
),

status as (
    select * from {{ ref('int_pn_player_week_status') }}
),

reports as materialized (       -- team-weeks whose injury report is out
    select distinct season, week, report_team as team from status where on_report
),

team_last as materialized (     -- the team's newest played game before W this season (NULL in week 1)
    select season, week, team, starting_qb_id as proj_qb_id,
           max(case when is_played then week end) over (partition by team, season order by week
                                                         rows between unbounded preceding and 1 preceding) as last_game_week
    from tg
),

-- ------------------------------------------------------------------ 1. quarterback
starts as materialized (        -- every played game's starting QB (any team), numbered per QB in time
    select g.starting_qb_id as qb_id, g.season, g.week, p.points,
           row_number() over (partition by g.starting_qb_id order by g.season, g.week)::int as start_no
    from tg as g
    left join {{ ref('int_pn_player_game') }} as p on p.gsis_id = g.starting_qb_id and p.game_id = g.game_id and p.team = g.team
    where g.is_played and g.starting_qb_id is not null
),

hist as materialized (          -- the player's newest four played games (this season before W, or last season)
    select u.gsis_id, u.season, u.week, h.starting_qb_id, h.rn
    from u
    cross join lateral (
        select p.starting_qb_id, row_number() over (order by p.season desc, p.week desc)::int as rn
        from {{ ref('int_pn_player_game') }} as p
        where p.gsis_id = u.gsis_id and p.played and p.starting_qb_id is not null
          and (p.season = u.season - 1 or (p.season = u.season and p.week < u.week))
        order by p.season desc, p.week desc
        limit {{ var('pn_usual_qb_games', 4) }}
    ) as h
),

usual as materialized (         -- the QB who started most of them (ties: the most recent)
    select distinct on (gsis_id, season, week) gsis_id, season, week, starting_qb_id as usual_qb_id
    from (select gsis_id, season, week, starting_qb_id,
                 count(*) over (partition by gsis_id, season, week, starting_qb_id) as k,
                 min(rn) over (partition by gsis_id, season, week, starting_qb_id) as recent
          from hist) as x
    order by gsis_id, season, week, k desc, recent
),

need as (                       -- (QB, season, week) pairs whose as-of record is needed
    select distinct proj_qb_id as qb_id, season, week from team_last where proj_qb_id is not null
    union
    select distinct usual_qb_id, season, week from usual
),

qb_career as materialized (     -- starts before the week (career since 2016)
    select n.qb_id, n.season, n.week, coalesce(max(s.start_no), 0) as career_starts
    from need as n
    left join starts as s on s.qb_id = n.qb_id and (s.season, s.week) < (n.season, n.week)
    group by 1, 2, 3
),

qb_asof as materialized (       -- points per start over his newest 17 starts of the last two seasons and this one
    select c.qb_id, c.season, c.week, c.career_starts, avg(s.points) as ppg_start, count(s.points)::int as ppg_starts
    from qb_career as c
    left join starts as s on s.qb_id = c.qb_id and s.start_no between c.career_starts - 16 and c.career_starts
                         and s.season >= c.season - 2 and c.career_starts > 0
    group by 1, 2, 3, 4
),

together as materialized (      -- per game: (player, QB) pairs who both played >= 50% of the offensive snaps
    select a.gsis_id, q.gsis_id as qb_id, a.season, a.week
    from {{ ref('int_pn_player_game') }} as a
    join {{ ref('int_pn_player_game') }} as q on q.game_id = a.game_id and q.team = a.team and q.pos_group = 'QB' and q.snap_share >= 0.5
    where a.snap_share >= 0.5 and a.pos_group in ('QB', 'RB', 'WR', 'TE')
),

together_n as (                 -- ... with this week's projected starter, before the week
    select u.gsis_id, u.season, u.week, count(*)::int as n
    from u
    join team_last as tl on tl.team = u.team and tl.season = u.season and tl.week = u.week
    join together as t on t.gsis_id = u.gsis_id and t.qb_id = tl.proj_qb_id and (t.season, t.week) < (u.season, u.week)
    group by 1, 2, 3
),

qb as (
    select u.gsis_id, u.season, u.week,
           tl.proj_qb_id, us.usual_qb_id,
           case when tl.proj_qb_id is null or us.usual_qb_id is null then null
                else (tl.proj_qb_id <> us.usual_qb_id)::int end                                         as pn_qb_changed,
           case when tl.proj_qb_id is not null then coalesce(tn.n, 0) end                              as pn_qb_games_together,
           case when tl.proj_qb_id is null or us.usual_qb_id is null then null
                when tl.proj_qb_id = us.usual_qb_id then 0
                else round((pa.ppg_start - ua.ppg_start)::numeric, 2) end                              as pn_qb_prev_ppg_diff,
           case when tl.proj_qb_id is not null then (coalesce(pa.career_starts, 0) < 8)::int end        as pn_qb_is_rookie_or_backup,
           case when u.position = 'QB' and tl.proj_qb_id is not null then (tl.proj_qb_id = u.gsis_id)::int end as pn_qb_starting
    from u
    left join team_last as tl on tl.team = u.team and tl.season = u.season and tl.week = u.week
    left join usual as us on us.gsis_id = u.gsis_id and us.season = u.season and us.week = u.week
    left join qb_asof as pa on pa.qb_id = tl.proj_qb_id and pa.season = u.season and pa.week = u.week
    left join qb_asof as ua on ua.qb_id = us.usual_qb_id and ua.season = u.season and ua.week = u.week
    left join together_n as tn on tn.gsis_id = u.gsis_id and tn.season = u.season and tn.week = u.week
),

-- ------------------------------------------------------------------ 2. offensive line
ol_starters as (               -- the five linemen with the most snaps over the window
    select * from (
        select w.*, row_number() over (partition by season, week, team order by snap_share desc nulls last, gsis_id) as rn
        from {{ ref('int_pn_window_player') }} as w
        where pos_group = 'OL'
    ) as x where rn <= 5
),

ol_week as (
    select season, week, team,
           count(*) filter (where out_injured)::int                     as starters_out,
           round(coalesce(sum(snap_share) filter (where out_injured), 0), 4) as snap_share_out
    from ol_starters group by 1, 2, 3
),

ol_game_five as (               -- per played game: the five linemen with the most snaps (the starting five)
    select team, season, week, string_agg(gsis_id, ',' order by gsis_id) as five
    from (select team, season, week, gsis_id,
                 row_number() over (partition by game_id, team order by offense_snaps desc, gsis_id) as rn
          from {{ ref('int_pn_player_game') }} where pos_group = 'OL' and played) as x
    where rn <= 5
    group by 1, 2, 3
),

ol_streak as (                  -- consecutive games (this season) with the same five, through each game
    select team, season, week,
           row_number() over (partition by team, season, grp order by week)::int as games_same
    from (select *, sum(case when prev is distinct from five then 1 else 0 end) over (partition by team, season order by week) as grp
          from (select *, lag(five) over (partition by team, season order by week) as prev from ol_game_five) as y) as x
),

-- ------------------------------------------------------------------ 3. teammates
skill_window as (
    select w.*, (w.out_injured or w.gone) as absent,
           row_number() over (partition by season, week, team order by carry_share desc nulls last, gsis_id) as carry_rank
    from {{ ref('int_pn_window_player') }} as w
    where pos_group in ('QB', 'RB', 'WR', 'TE')
),

team_tops as (
    select season, week, team,
           max(gsis_id) filter (where pos_group in ('RB', 'WR', 'TE') and target_rank = 1)           as target_1,
           bool_or(absent) filter (where pos_group in ('RB', 'WR', 'TE') and target_rank = 1)      as target_1_absent,
           max(gsis_id) filter (where pos_group in ('RB', 'WR', 'TE') and target_rank = 2)           as target_2,
           bool_or(absent) filter (where pos_group in ('RB', 'WR', 'TE') and target_rank = 2)      as target_2_absent,
           max(gsis_id) filter (where carry_rank = 1)                                                as rusher_1,
           bool_or(absent) filter (where carry_rank = 1)                                             as rusher_1_absent,
           max(gsis_id) filter (where carry_rank = 2)                                                as rusher_2,
           bool_or(absent) filter (where carry_rank = 2)                                             as rusher_2_absent,
           coalesce(sum(target_share) filter (where pos_group in ('RB', 'WR', 'TE') and absent), 0)  as absent_target_share
    from (select s.*, row_number() over (partition by season, week, team, (pos_group in ('RB', 'WR', 'TE'))
                                          order by target_share desc nulls last, gsis_id) as target_rank
          from skill_window as s) as x
    group by 1, 2, 3
),

alerts as (
    select gsis_id, season, week, {{ kd_team('team') }} as team, trigger_gsis_id
    from {{ source('ops', 'player_role_alerts') }}
    where kind = 'absence_beneficiary'
),

benef as (                      -- an absence alert at his team's newest game whose absent teammate is still out
    select u.gsis_id, u.season, u.week,
           bool_or(not coalesce(ts.roster_team = u.team and ts.roster_status in ('ACT', 'INA')
                                and coalesce(ts.report_status not in ('Out', 'Doubtful'), true), false)) as live
    from u
    join team_last as tl on tl.team = u.team and tl.season = u.season and tl.week = u.week
    join alerts as a on a.gsis_id = u.gsis_id and a.season = u.season and a.week = tl.last_game_week and a.team = u.team
    left join status as ts on ts.gsis_id = a.trigger_gsis_id and ts.season = u.season and ts.week = u.week
    group by 1, 2, 3
),

alert_seasons as (              -- team-seasons the role alerts cover (none: unknown, not 0)
    select distinct season, {{ kd_team('team') }} as team from {{ source('ops', 'player_role_alerts') }}
),

-- ------------------------------------------------------------------ 4. his own injuries
own as (
    select u.gsis_id, u.season, u.week,
           h.missed_season, h.missed_prev, h.rows_prev, h.rows_any, h.last_week_this_season, l.injured_miss_streak
    from u
    cross join lateral (
        select count(*) filter (where p.season = u.season and p.status = 'missed_injured')::int     as missed_season,
               count(*) filter (where p.season = u.season - 1 and p.status = 'missed_injured')::int as missed_prev,
               count(*) filter (where p.season = u.season - 1)::int                                 as rows_prev,
               count(*)::int                                                                         as rows_any,
               max(p.week) filter (where p.season = u.season)                                        as last_week_this_season
        from {{ ref('int_pn_player_game') }} as p
        where p.gsis_id = u.gsis_id and (p.season = u.season - 1 or (p.season = u.season and p.week < u.week))
    ) as h
    left join lateral (
        select p.injured_miss_streak
        from {{ ref('int_pn_player_game') }} as p
        where p.gsis_id = u.gsis_id and (p.season = u.season - 1 or (p.season = u.season and p.week < u.week))
        order by p.season desc, p.week desc
        limit 1
    ) as l on true
),

own_report as (
    select u.gsis_id, u.season, u.week, u.team,
           s.report_status, s.practice_status,
           coalesce(s.roster_team = u.team and s.roster_status in ('RES', 'PUP', 'SUS', 'EXE', 'NON'), false) as on_reserve,
           r.team is not null as report_known,
           coalesce(s.report_status = 'Questionable', false) as is_q
    from u
    left join status as s on s.gsis_id = u.gsis_id and s.season = u.season and s.week = u.week
    left join reports as r on r.season = u.season and r.week = u.week and r.team = u.team
),

q_streak as (                   -- consecutive weeks Questionable through this week's report (his team's game weeks)
    select gsis_id, season, week,
           case when is_q then rk - coalesce(max(case when not is_q then rk end) over w, 0) else 0 end as q_streak
    from (select o.*, row_number() over (partition by gsis_id, season order by week) as rk from own_report as o) as x
    window w as (partition by gsis_id, season order by week rows between unbounded preceding and current row)
)

select
    u.gsis_id, u.season, u.week, u.team, u.position,
    -- 1. quarterback
    qb.proj_qb_id, qb.usual_qb_id,
    qb.pn_qb_changed, qb.pn_qb_games_together, qb.pn_qb_prev_ppg_diff, qb.pn_qb_is_rookie_or_backup, qb.pn_qb_starting,
    -- 2. offensive line (NULL: week 1, or week W's report not out)
    case when tl.last_game_week is not null and rp.team is not null then coalesce(ol.starters_out, 0) end        as pn_ol_starters_out,
    case when tl.last_game_week is not null and rp.team is not null then coalesce(ol.snap_share_out, 0) end      as pn_ol_snap_share_out,
    os.games_same                                                                                                as pn_ol_games_since_change,
    -- 3. teammates (the leading teammate other than him; NULL: week 1, or week W's report not out)
    case when tl.last_game_week is not null and rp.team is not null and tt.team is not null then
        (case when tt.target_1 = u.gsis_id then tt.target_2_absent else tt.target_1_absent end)::int end         as pn_top_target_out,
    case when tl.last_game_week is not null and rp.team is not null and tt.team is not null then
        (case when tt.rusher_1 = u.gsis_id then tt.rusher_2_absent else tt.rusher_1_absent end)::int end         as pn_top_rusher_out,
    case when tl.last_game_week is not null and rp.team is not null then
        round(greatest(0, coalesce(tt.absent_target_share, 0)
                          - coalesce(case when me.absent and me.pos_group in ('RB', 'WR', 'TE') then me.target_share end, 0)), 4) end
                                                                                                                 as pn_teammate_share_out,
    case when tl.last_game_week is not null and als.team is not null then coalesce(b.live, false)::int end      as pn_absence_beneficiary,
    -- 4. his own injuries
    own.missed_season                                                                                            as pn_games_missed_season,
    case when own.rows_prev > 0 then own.missed_prev end                                                         as pn_games_missed_prev,
    case when orp.report_known or orp.on_reserve then qs.q_streak end                                            as pn_q_streak,
    case when own.rows_any > 0 then (coalesce(own.injured_miss_streak, 0) >= 2
                                     and not orp.on_reserve and coalesce(orp.report_status not in ('Out', 'Doubtful'), true))::int end
                                                                                                                 as pn_returning,
    case when orp.on_reserve or orp.report_status = 'Out' then 3 when orp.report_status = 'Doubtful' then 2
         when orp.report_status = 'Questionable' then 1 when orp.report_known then 0 end                         as pn_report_status_ord,
    case when orp.practice_status = 'DNP' then 2 when orp.practice_status = 'Limited' then 1
         when orp.report_known then 0 end                                                                        as pn_practice_ord,
    -- as-of marker for the harness (check 3): the newest game of this season any input read (< week)
    greatest(tl.last_game_week, own.last_week_this_season)                                                       as pn_asof_week
from u
left join qb on qb.gsis_id = u.gsis_id and qb.season = u.season and qb.week = u.week
left join team_last as tl on tl.team = u.team and tl.season = u.season and tl.week = u.week
left join reports as rp on rp.season = u.season and rp.week = u.week and rp.team = u.team
left join ol_week as ol on ol.team = u.team and ol.season = u.season and ol.week = u.week
left join ol_streak as os on os.team = u.team and os.season = u.season and os.week = tl.last_game_week
left join team_tops as tt on tt.team = u.team and tt.season = u.season and tt.week = u.week
left join skill_window as me on me.gsis_id = u.gsis_id and me.team = u.team and me.season = u.season and me.week = u.week
left join alert_seasons as als on als.season = u.season and als.team = u.team
left join benef as b on b.gsis_id = u.gsis_id and b.season = u.season and b.week = u.week
left join own on own.gsis_id = u.gsis_id and own.season = u.season and own.week = u.week
left join own_report as orp on orp.gsis_id = u.gsis_id and orp.season = u.season and orp.week = u.week
left join q_streak as qs on qs.gsis_id = u.gsis_id and qs.season = u.season and qs.week = u.week
