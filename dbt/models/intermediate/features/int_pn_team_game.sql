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
      and coalesce(o.on_roster, false)           -- PO (Wave I-Q): a row whose quarterback is not on the team's roster is ignored (and warned), never a stop
      and {{ var('starter_overrides', true) }}   -- the kill switch: --vars '{starter_overrides: false}' = the schedule as before
    order by p.game_id, p.team, o.added_on desc, o.from_week desc, o.gsis_id
),

-- ---- end IQ-2

-- ---- IW-1 (Wave I-W): sq1.0, who starts decided by the data (docs/METRICS.md § "Who starts, decided by the data": S4,
-- the most accurate rule fixing >= 80% of stale listings on 2025 - 2026 week 4). An UNPLAYED game's starter is the
-- listing L, unless (i) L is not available for the week -> the newest depth-chart snapshot before kickoff's first
-- available quarterback D (none: L); or (ii) D is also the quarterback who led the team's dropbacks in its newest played
-- game this season, and he is not L -> him. Played games keep the listing (training rows, history inputs, the record).
-- "Available" is availability_gate's question: not Out / Doubtful on week W's report, not on a reserve list (week W's
-- roster status outside ACT / INA / DEV), and for the nearest unplayed week not sitting by Sleeper's directory (the
-- gate's codes; a game status dated before the previous week's last kickoff is stale). Questionable is available.
-- A game with no listing yet (more than about a week out) stays without a starter, as before.
sq_games as (
    select p.season, p.week, p.game_id, p.team, p.kickoff_at, p.starting_qb_id as listing_qb_id
    from picked as p
    where not p.is_played
),

sq_next_week as (   -- the nearest week ahead: the week of the first game not yet kicked off (var starter_now: tests)
    select g.week, g.season from sq_games as g
    where g.kickoff_at > '{{ var("starter_now", "now") }}'::timestamptz
    order by g.kickoff_at, g.week
    limit 1
),

sq_prev_end as (
    select max(g.kickoff_at) as t from {{ ref('dim_game') }} as g, sq_next_week as n
    where g.season = n.season and g.week = n.week - 1 and g.season_type = 'REG'
),

sq_directory_out as (
    select coalesce(nullif(p.gsis_id, ''), m.gsis_id) as gsis_id
    from {{ source('raw', 'sleeper_player') }} as p
    left join {{ ref('player_id_map') }} as m on m.sleeper_id = p.player_id
    cross join sq_prev_end as pe
    where (upper(coalesce(p.injury_status, '')) in ('IR', 'PUP', 'NFI', 'SUS')
           or lower(coalesce(p.status, '')) in ('injured reserve', 'physically unable to perform', 'non-football injury', 'suspended')
           or (upper(coalesce(p.injury_status, '')) in ('OUT', 'DNR', 'COV', 'DOUBTFUL')
               and (pe.t is null or to_timestamp(nullif(p.payload ->> 'news_updated', '')::bigint / 1000.0) >= pe.t)))
),

sq_out as (
    select i.season, i.week, i.gsis_id from {{ ref('stg_nflverse__injuries') }} as i
    where i.game_type = 'REG' and i.report_status in ('Out', 'Doubtful')
    union
    select r.season, r.week, r.gsis_id from {{ ref('stg_nflverse__rosters_weekly') }} as r
    where r.position = 'QB' and r.roster_status not in ('ACT', 'INA', 'DEV')
    union
    select n.season, n.week, d.gsis_id from sq_directory_out as d cross join sq_next_week as n
    where d.gsis_id is not null
),

sq_snap as (
    select g.game_id, g.team, g.season, g.week,
           (select max(d.snapshot_at) from {{ ref('stg_nflverse__depth_charts') }} as d
            where {{ kd_team('d.team') }} = g.team and d.pos_abb = 'QB' and d.snapshot_at < g.kickoff_at) as snap_at
    from sq_games as g
),

sq_depth as (
    select distinct on (s.game_id, s.team) s.game_id, s.team, d.gsis_id as depth_qb_id
    from sq_snap as s
    join {{ ref('stg_nflverse__depth_charts') }} as d
      on {{ kd_team('d.team') }} = s.team and d.snapshot_at = s.snap_at and d.pos_abb = 'QB'
    where not exists (select 1 from sq_out as o where o.season = s.season and o.week = s.week and o.gsis_id = d.gsis_id)
    order by s.game_id, s.team, d.pos_rank, d.pos_slot, d.gsis_id
),

sq_last as (
    select g.game_id, g.team,
           (select td.top_qb_id from picked as p2
            join top_dropback as td on td.game_id = p2.game_id and td.team = p2.team
            where p2.team = g.team and p2.season = g.season and p2.week < g.week and p2.is_played
            order by p2.week desc limit 1)                                   as last_qb_id
    from sq_games as g
),

sq_pick as (
    select g.game_id, g.team,
           -- S4 (sq1.0): the listing, unless he is not available -> D; or D is also the newest game's leader -> him
           case when g.listing_qb_id is null then null   -- no listing yet (more than about a week out): as before, unknown
                when lo.gsis_id is not null then coalesce(dq.depth_qb_id, g.listing_qb_id)
                when dq.depth_qb_id is not null and dq.depth_qb_id = sl.last_qb_id and sl.last_qb_id <> g.listing_qb_id
                     then sl.last_qb_id
                else g.listing_qb_id end                                     as s4_qb_id,
           -- S7 (sq1.1, the PO's product decision): S4, and a listing neither D nor the newest leader names is dropped:
           -- D; no D: the newest leader if available; else the listing
           case when g.listing_qb_id is null then null
                when dq.depth_qb_id is distinct from g.listing_qb_id and sl.last_qb_id is distinct from g.listing_qb_id
                     then coalesce(dq.depth_qb_id, case when sl.last_qb_id is not null and lso.gsis_id is null then sl.last_qb_id end,
                                   g.listing_qb_id)
                when lo.gsis_id is not null then coalesce(dq.depth_qb_id, g.listing_qb_id)
                when dq.depth_qb_id is not null and dq.depth_qb_id = sl.last_qb_id and sl.last_qb_id <> g.listing_qb_id
                     then sl.last_qb_id
                else g.listing_qb_id end                                     as s7_qb_id,
           -- why each rule moved off the listing (the row's sentence): listing_out | two_sources | unsupported
           case when g.listing_qb_id is null then null
                when lo.gsis_id is not null then 'listing_out'
                when dq.depth_qb_id is not null and dq.depth_qb_id = sl.last_qb_id and sl.last_qb_id <> g.listing_qb_id
                     then 'two_sources' end                                  as s4_reason,
           case when g.listing_qb_id is null then null
                when lo.gsis_id is not null then 'listing_out'
                when dq.depth_qb_id is not null and dq.depth_qb_id = sl.last_qb_id and sl.last_qb_id <> g.listing_qb_id
                     then 'two_sources'
                when dq.depth_qb_id is distinct from g.listing_qb_id and sl.last_qb_id is distinct from g.listing_qb_id
                     then 'unsupported' end                                  as s7_reason
    from sq_games as g
    left join sq_depth as dq on dq.game_id = g.game_id and dq.team = g.team
    left join sq_last as sl on sl.game_id = g.game_id and sl.team = g.team
    left join sq_out as lo on lo.season = g.season and lo.week = g.week and lo.gsis_id = g.listing_qb_id
    left join sq_out as lso on lso.season = g.season and lso.week = g.week and lso.gsis_id = sl.last_qb_id
)

-- the shipped rule (var starter_from_data): 's7' (default, the PO's decision), 's4' (the rule the study picked), or
-- false / 'off' / 'listing' (the schedule's listing, as before IW-1). S4's and S7's picks are both kept (the record).
{%- set sq_rule = (var('starter_from_data', 's7') | string | lower) %}
select
    p.season, p.week, p.game_id, p.team, p.opponent, p.kickoff_at,
    coalesce(op.override_qb_id, {{ 'sq.s7_qb_id' if sq_rule == 's7' else ('sq.s4_qb_id' if sq_rule == 's4' else 'null') }},
             p.starting_qb_id)                                               as starting_qb_id,
    p.listed_qb_id,
    p.is_played, p.team_snaps, p.team_targets, p.team_carries, p.game_no,
    case when op.override_qb_id is not null then 'override'
         when {{ 'sq.s7_qb_id' if sq_rule == 's7' else ('sq.s4_qb_id' if sq_rule == 's4' else 'null') }} is not null
              and {{ 'sq.s7_qb_id' if sq_rule == 's7' else ('sq.s4_qb_id' if sq_rule == 's4' else 'null') }}
                  is distinct from p.starting_qb_id then 'data'
         else 'schedule' end                                                 as starter_source,
    sq.s4_qb_id, sq.s7_qb_id,                                                -- ---- IW-1 round 3: both rules, recorded
    {{ 'sq.s7_reason' if sq_rule == 's7' else ('sq.s4_reason' if sq_rule == 's4' else 'null') }} as starter_reason
from picked as p
left join override_pick as op on op.game_id = p.game_id and op.team = p.team
left join sq_pick as sq on sq.game_id = p.game_id and sq.team = p.team
-- ---- end IW-1
