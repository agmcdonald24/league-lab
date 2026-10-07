{{ config(indexes=[{'columns': ['team', 'season', 'week'], 'unique': True}, {'columns': ['game_id']}]) }}
-- Plan D5 (personnel), helper 1 of 3: one row per team x regular-season game, 2016 on, played or not, one
-- code per franchise (kd_team: OAK -> LV, SD -> LAC, STL -> LA, as the player and team stats files say).
--   starting_qb_id   the schedule's starting QB (raw.nfl_schedules home_qb_id / away_qb_id): for a game not
--                    played yet it is the projected starter nflverse fills about a week ahead (NULL further
--                    out); for a played game it is the QB who started.
--   is_played        the team's box score is in (fct_team_game): the only games a week-W feature may read,
--                    and only those with week < W
--   team_snaps       offensive snaps of the game: the snap leader's snaps / his snap share (NULL without snaps)
--   team_targets / team_carries   fct_team_game (the denominators of the teammates' shares, never a sum of
--                    player rows)
--   game_no          the team's n-th regular-season game of the season (byes skipped)
--   starter_source   'override' when the hand-kept list (seed starter_overrides, IQ-2) set an unplayed game's
--                    starting_qb_id, else 'schedule' (the pick below)
-- ---- IP-1 (Wave I-P): the starter from what happened (st1.0; docs/METRICS.md § "The quarterback weak spot").
-- nflverse's schedule sometimes keeps the PRE-GAME projected starter after the game: the listed QB threw no pass
-- (2022: 4 team-games, 2024: 33, 2025: 7, 2026 weeks 1-4: 5; none 2016-2021), e.g. WAS 2024 weeks 9-13 "Mariota"
-- while Daniels started, SEA 2026 weeks 3-5 "Lock" while Darnold started. With var('pn_starter_from_play') on:
--   a played game's starting_qb_id = the listed QB when he threw a pass for the team in it, else the team's QB with
--     the most pass attempts (what happened: training's "is he the starter?" and every history input read it);
--   an unplayed game's = the listing, unless it repeats a listing that was already wrong in the team's newest
--     played game this season (that QB threw no pass there): then that game's real starter (known before kickoff).
--   listed_qb_id keeps the schedule's own value. Off: exactly the schedule, as before.
with games as (
    select g.game_id, g.season, g.week, g.kickoff_at,
           {{ kd_team('t.team') }} as team, {{ kd_team('t.opp') }} as opponent, t.qb_id as starting_qb_id
    from {{ ref('dim_game') }} as g
    cross join lateral (values (g.home_team, g.away_team, g.home_qb_id), (g.away_team, g.home_team, g.away_qb_id)) as t(team, opp, qb_id)
    where g.season_type = 'REG' and g.season >= {{ var('seasons_start') }}
),

snaps as (
    select distinct on (game_id, team)
           game_id, {{ kd_team('team') }} as team, round(offense_snaps / offense_snap_pct)::int as team_snaps
    from {{ ref('int_player_game_snaps') }}
    where game_type = 'REG' and offense_snap_pct > 0 and offense_snaps > 0
    order by game_id, team, offense_snaps desc, offense_snap_pct desc
),

-- ---- IP-1: who threw for the team in each game (any listed position: Taysom Hill started at QB listed as a TE; a
-- receiver's one trick-play pass never has the most attempts while a quarterback threw)
passers as (
    select game_id, {{ kd_team('team') }} as team, gsis_id, attempts
    from {{ ref('fct_player_game') }}
    where season_type = 'REG' and coalesce(attempts, 0) > 0
),

top_passer as (
    select distinct on (game_id, team) game_id, team, gsis_id as top_passer_id
    from passers
    order by game_id, team, attempts desc, gsis_id
),

base as (
    select
        g.season, g.week, g.game_id, g.team, g.opponent, g.kickoff_at,
        nullif(g.starting_qb_id, '')                                         as listed_qb_id,
        tg.game_id is not null                                               as is_played,
        s.team_snaps,
        tg.targets                                                           as team_targets,
        tg.carries                                                           as team_carries,
        row_number() over (partition by g.team, g.season order by g.week)::int as game_no,
        tp.top_passer_id,
        exists (select 1 from passers as p
                where p.game_id = g.game_id and p.team = g.team and p.gsis_id = nullif(g.starting_qb_id, '')) as listed_threw
    from games as g
    left join {{ ref('fct_team_game') }} as tg on tg.game_id = g.game_id and tg.team = g.team and tg.season_type = 'REG'
    left join snaps as s on s.game_id = g.game_id and s.team = g.team
    left join top_passer as tp on tp.game_id = g.game_id and tp.team = g.team
),

played as (
    select b.*,
           case when b.is_played and not b.listed_threw and b.top_passer_id is not null then b.top_passer_id
                else b.listed_qb_id end                                      as played_qb_id,
           (b.is_played and not b.listed_threw and b.top_passer_id is not null) as listing_wrong
    from base as b
),

guarded as (
    select p.*,
           (array_agg(p.listed_qb_id) filter (where p.is_played) over w_prev)[1]  as prev_listed_qb_id,
           (array_agg(p.played_qb_id) filter (where p.is_played) over w_prev)[1]  as prev_played_qb_id,
           (array_agg(p.listing_wrong) filter (where p.is_played) over w_prev)[1] as prev_listing_wrong
    from played as p
    window w_prev as (partition by p.team, p.season order by p.week desc
                      rows between 1 following and unbounded following)
),

-- ---- IP-1 fix round (Wave I-P): st1.1, the listing stands unless the evidence says it is stale (var
-- 'pn_starter_stale_rule'; docs/METRICS.md § "st1.1"). Week W's pick is Q instead of the listing L only when, in the
-- team's two newest played games of the season before W (g1 newer, g2): g1 was listed for L too; L took no dropback in
-- either; the same QB Q took the team's most dropbacks in both; and L was available in both (on the team's weekly
-- roster as ACT, not Out / Doubtful on that week's injury report: a hurt starter coming back keeps his listing). Read
-- only from weeks before W, played or not. A data-quality rule for who starts, judged on identification accuracy.
dropbacks as (
    select p.game_id, {{ kd_team('p.posteam') }} as team, coalesce(p.passer_player_id, p.rusher_player_id) as gsis_id,
           count(*) as dropbacks
    from {{ ref('fct_play') }} as p
    where p.season_type = 'REG' and p.is_dropback and not p.is_no_play
      and coalesce(p.passer_player_id, p.rusher_player_id) is not null
    group by 1, 2, 3
),

top_dropback as (
    select distinct on (game_id, team) game_id, team, gsis_id as top_qb_id
    from dropbacks
    order by game_id, team, dropbacks desc, gsis_id
),

available as (
    select r.gsis_id, r.season, r.week, {{ kd_team('r.team') }} as team
    from {{ ref('int_player_week_team') }} as r
    where r.season_type = 'REG' and r.roster_status = 'ACT'
      and not exists (select 1 from {{ ref('stg_nflverse__injuries') }} as i
                      where i.gsis_id = r.gsis_id and i.season = r.season and i.week = r.week and i.game_type = 'REG'
                        and i.report_status in ('Out', 'Doubtful'))
),

st11_hist as (
    select gd.*,
           (array_agg(gd.game_id) filter (where gd.is_played) over w_two)[1]      as g1_game_id,
           (array_agg(gd.game_id) filter (where gd.is_played) over w_two)[2]      as g2_game_id,
           (array_agg(gd.week) filter (where gd.is_played) over w_two)[1]         as g1_week,
           (array_agg(gd.week) filter (where gd.is_played) over w_two)[2]         as g2_week,
           (array_agg(gd.listed_qb_id) filter (where gd.is_played) over w_two)[1] as g1_listed_qb_id,
           (array_agg(td.top_qb_id) filter (where gd.is_played) over w_two)[1]    as g1_top_qb_id,
           (array_agg(td.top_qb_id) filter (where gd.is_played) over w_two)[2]    as g2_top_qb_id
    from guarded as gd
    left join top_dropback as td on td.game_id = gd.game_id and td.team = gd.team
    window w_two as (partition by gd.team, gd.season order by gd.week desc
                     rows between 1 following and unbounded following)
),

st11 as (
    select h.*,
           (h.listed_qb_id is not null and h.g2_game_id is not null
            and h.g1_listed_qb_id = h.listed_qb_id
            and h.g1_top_qb_id is not null and h.g1_top_qb_id = h.g2_top_qb_id and h.g1_top_qb_id <> h.listed_qb_id
            and not exists (select 1 from dropbacks as d
                            where d.team = h.team and d.gsis_id = h.listed_qb_id and d.game_id in (h.g1_game_id, h.g2_game_id))
            and exists (select 1 from available as a
                        where a.gsis_id = h.listed_qb_id and a.team = h.team and a.season = h.season and a.week = h.g1_week)
            and exists (select 1 from available as a
                        where a.gsis_id = h.listed_qb_id and a.team = h.team and a.season = h.season and a.week = h.g2_week)
           )                                                                    as listing_stale
    from st11_hist as h
),

-- ---- IQ-2 (Wave I-Q): the pick above is wrapped so the override list can set an unplayed game's starter
picked as (
select
    season, week, game_id, team, opponent, kickoff_at,
    {%- if var('pn_starter_from_play', false) %}
    case when is_played then played_qb_id
         when listed_qb_id is not null and listed_qb_id = prev_listed_qb_id and prev_listing_wrong then prev_played_qb_id
         else listed_qb_id end                                               as starting_qb_id,
    {%- elif var('pn_starter_stale_rule', false) %}
    case when listing_stale then g1_top_qb_id else listed_qb_id end          as starting_qb_id,
    {%- else %}
    listed_qb_id                                                             as starting_qb_id,
    {%- endif %}
    listed_qb_id,
    is_played, team_snaps, team_targets, team_carries, game_no
from {% if var('pn_starter_stale_rule', false) and not var('pn_starter_from_play', false) %}st11{% else %}guarded{% endif %}   -- off: st1.1's CTEs are never read
),
-- ---- end IP-1

-- ---- IQ-2 (Wave I-Q): who starts, set by hand (seed starter_overrides -> int_starter_override; docs/METRICS.md
-- § "Who starts"). A row in force sets starting_qb_id of the team's UNPLAYED games of weeks from_week ..
-- through_week -- never a played game, so never a training row, a history input (`starts`, `last_starter`) or the
-- record. Two rows on one game: the newest added_on wins. starter_source says where the pick came from.
override_pick as (
    select distinct on (p.game_id, p.team) p.game_id, p.team, o.gsis_id as override_qb_id
    from picked as p
    join {{ ref('int_starter_override') }} as o
      on o.season = p.season and o.team = p.team and p.week >= o.from_week
     and (o.through_week is null or p.week <= o.through_week)
    where not p.is_played and o.in_force
      and {{ var('starter_overrides', true) }}   -- the kill switch: --vars '{starter_overrides: false}' = the schedule as before
    order by p.game_id, p.team, o.added_on desc, o.from_week desc, o.gsis_id
)

select
    p.season, p.week, p.game_id, p.team, p.opponent, p.kickoff_at,
    coalesce(op.override_qb_id, p.starting_qb_id)                            as starting_qb_id,
    p.listed_qb_id,
    p.is_played, p.team_snaps, p.team_targets, p.team_carries, p.game_no,
    case when op.override_qb_id is not null then 'override' else 'schedule' end as starter_source
from picked as p
left join override_pick as op on op.game_id = p.game_id and op.team = p.team
-- ---- end IQ-2
