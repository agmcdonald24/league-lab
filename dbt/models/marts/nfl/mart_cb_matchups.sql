{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}, {'columns': ['season', 'week', 'opponent']}], post_hook="analyze {{ this }}") }}
-- Cornerback matchup per receiver-week (plan R-14): every rostered WR / TE x regular-season week of 2025 on
-- with a game (plus, for the current season, every other WR / TE on his latest team: a fantasy lineup can
-- start anyone). For a week not yet played this is next week's matchup; the played weeks are kept so the
-- guess can be checked against what happened (docs/METRICS.md § Cornerback matchups).
--   * the opponent's corners: its depth chart as of that game (the latest snapshot before kickoff): the
--     rank-1 left corner (LCB), right corner (RCB) and nickel / slot corner (NB);
--   * where his targets go: pass location (left / middle / right, the offense's view) of his targets since
--     the start of last season, before that week. Public data has no receiver alignment (FTN charting and
--     participation carry none), so this is where his targets went, not where he lined up;
--   * the likely cover (a guess, stated as one): the outside corner on the side more of his targets go (the
--     offense's left faces the defense's right corner). call_strength 'clear' when that side leads the other
--     by 15+ points of his located targets, else 'even' (the other outside corner is named too). Fewer than
--     15 located targets -> no call. Tight ends get no cornerback call. Checked on 2025 (docs/METRICS.md):
--     with a clear lean the named corner was charged with 0.20 of the receiver's targets vs 0.14 for the other
--     outside corner; with an even split 0.19 vs 0.16. A lean, not an assignment: public data does not say who
--     covered whom on any play;
--   * how good that corner is: mart_cb_rankings, window 'two_seasons' of that season (latest, not as-of);
--   * what he has done: vs this defense this season before that week (fct_player_game) and with the likely
--     cover on the field since 2022 (mart_receiver_vs_cb, both kinds of evidence summed).
with uni_roster as (
    select gsis_id, season, week, team, position, player_name, game_id, opponent, is_home
    from {{ ref('int_player_week_universe') }}
    where position in ('WR', 'TE') and season >= 2025
),

cur as (
    select max(season) as season from {{ ref('dim_game') }} where season_type = 'REG'
),

-- every other WR / TE of the current season on his latest team (practice squad, cut, just signed): a
-- fantasy lineup can start anyone, and every WR / TE in a proposed lineup must get a row
uni_extra as (
    select p.gsis_id, g.season, g.week, p.latest_team as team, p.position, p.player_name, g.game_id,
           case when g.home_team = p.latest_team then g.away_team else g.home_team end as opponent,
           g.home_team = p.latest_team as is_home
    from {{ ref('dim_player') }} as p
    join {{ ref('dim_game') }} as g
      on g.season = (select season from cur) and g.season_type = 'REG' and p.latest_team in (g.home_team, g.away_team)
    where p.position in ('WR', 'TE') and p.last_season >= (select season from cur) - 1
      and not exists (select 1 from uni_roster as u where u.gsis_id = p.gsis_id and u.season = g.season and u.week = g.week)
),

uni as (
    select * from uni_roster
    union all
    select * from uni_extra
),

games as (
    select distinct u.season, u.week, u.game_id, u.opponent, g.kickoff_at
    from uni as u
    join {{ ref('dim_game') }} as g on g.game_id = u.game_id
),

snapshots as (
    select distinct team, snapshot_at
    from {{ ref('stg_nflverse__depth_charts') }}
    where pos_abb in ('LCB', 'RCB', 'NB') and season >= 2025
),

opp_snapshot as (   -- the opponent's latest depth chart before kickoff
    select gm.game_id, gm.opponent, max(s.snapshot_at) as depth_chart_at
    from games as gm
    join snapshots as s on s.team = gm.opponent and s.snapshot_at < gm.kickoff_at
    group by 1, 2
),

corners as (
    select os.game_id, os.opponent, os.depth_chart_at,
           max(d.gsis_id) filter (where d.pos_abb = 'LCB')      as lcb_gsis_id,
           max(d.player_name) filter (where d.pos_abb = 'LCB')  as lcb_name,
           max(d.gsis_id) filter (where d.pos_abb = 'RCB')      as rcb_gsis_id,
           max(d.player_name) filter (where d.pos_abb = 'RCB')  as rcb_name,
           max(d.gsis_id) filter (where d.pos_abb = 'NB')       as nb_gsis_id,
           max(d.player_name) filter (where d.pos_abb = 'NB')   as nb_name
    from opp_snapshot as os
    join {{ ref('stg_nflverse__depth_charts') }} as d
      on d.team = os.opponent and d.snapshot_at = os.depth_chart_at and d.pos_abb in ('LCB', 'RCB', 'NB') and d.pos_rank = 1
    group by 1, 2, 3
),

loc_week as (
    select receiver_player_id as gsis_id, season, week,
           count(*) filter (where pass_location = 'left')     as tgt_left,
           count(*) filter (where pass_location = 'middle')   as tgt_middle,
           count(*) filter (where pass_location = 'right')    as tgt_right
    from {{ ref('fct_play') }}
    where season >= 2024 and season_type = 'REG' and is_target and not is_no_play and not is_two_point
      and receiver_player_id is not null
    group by 1, 2, 3
),

loc as (   -- since the start of last season, before this week
    select u.gsis_id, u.season, u.week,
           coalesce(sum(l.tgt_left), 0) as tgt_left, coalesce(sum(l.tgt_middle), 0) as tgt_middle,
           coalesce(sum(l.tgt_right), 0) as tgt_right
    from uni as u
    left join loc_week as l
      on l.gsis_id = u.gsis_id and (l.season = u.season - 1 or (l.season = u.season and l.week < u.week))
    group by 1, 2, 3
),

base as (
    select u.*, c.depth_chart_at, c.lcb_gsis_id, c.lcb_name, c.rcb_gsis_id, c.rcb_name, c.nb_gsis_id, c.nb_name,
           l.tgt_left, l.tgt_middle, l.tgt_right,
           l.tgt_left + l.tgt_middle + l.tgt_right                                       as located_targets,
           case when l.tgt_left + l.tgt_middle + l.tgt_right > 0
                then round(l.tgt_middle::numeric / (l.tgt_left + l.tgt_middle + l.tgt_right), 3) end as middle_share,
           case when l.tgt_left + l.tgt_middle + l.tgt_right > 0
                then round(l.tgt_left::numeric / (l.tgt_left + l.tgt_middle + l.tgt_right), 3) end  as left_share,
           case when l.tgt_left + l.tgt_middle + l.tgt_right > 0
                then round(l.tgt_right::numeric / (l.tgt_left + l.tgt_middle + l.tgt_right), 3) end as right_share
    from uni as u
    left join corners as c on c.game_id = u.game_id and c.opponent = u.opponent
    left join loc as l on l.gsis_id = u.gsis_id and l.season = u.season and l.week = u.week
),

called as (
    select b.*,
           case when b.position = 'TE' then 'tight end'
                when b.located_targets < 15 then 'too few targets'
                when b.tgt_left > b.tgt_right then 'left'
                else 'right' end                                                         as alignment_lean,
           -- the share of his located targets on the called side, and on the other side
           case when b.located_targets > 0 then greatest(b.left_share, b.right_share) end as side_share,
           case when b.located_targets > 0 then least(b.left_share, b.right_share) end    as other_side_share
    from base as b
),

pick as (
    select c.*,
           case when c.depth_chart_at is null then 'no depth chart yet'
                when c.position = 'TE' then 'tight end'
                when c.alignment_lean = 'too few targets' then 'too few targets'
                else 'called' end                                                         as call_status,
           -- the outside corner on the side his targets lean to (the offense's left faces the defense's right
           -- corner); a missing corner falls back to the other outside one, then the nickel
           case when c.depth_chart_at is null or c.alignment_lean in ('tight end', 'too few targets') then null
                when c.alignment_lean = 'left' and c.rcb_gsis_id is not null then 'RCB'
                when c.alignment_lean = 'right' and c.lcb_gsis_id is not null then 'LCB'
                when c.lcb_gsis_id is not null then 'LCB'
                when c.rcb_gsis_id is not null then 'RCB'
                when c.nb_gsis_id is not null then 'NB' end                              as likely_cover_slot
    from called as c
),

named as (
    select p.*,
           case when p.call_status <> 'called' then null
                when p.side_share - p.other_side_share >= 0.15 then 'clear' else 'even' end as call_strength,
           case p.likely_cover_slot when 'LCB' then p.lcb_gsis_id when 'RCB' then p.rcb_gsis_id when 'NB' then p.nb_gsis_id end as likely_cover_gsis_id,
           case p.likely_cover_slot when 'LCB' then p.lcb_name when 'RCB' then p.rcb_name when 'NB' then p.nb_name end          as likely_cover_name
    from pick as p
),

-- an even split names the other outside corner too
named2 as (
    select n.*,
           case when n.call_strength = 'even' and n.likely_cover_slot = 'LCB' and n.rcb_gsis_id is not null then 'RCB'
                when n.call_strength = 'even' and n.likely_cover_slot = 'RCB' and n.lcb_gsis_id is not null then 'LCB' end as other_cover_slot
    from named as n
),

vs_opp as (   -- his line against this defense this season, before this week
    select u.gsis_id, u.season, u.week,
           count(pg.game_id) as games_vs_opp, sum(pg.targets) as targets_vs_opp, sum(pg.receptions) as receptions_vs_opp,
           sum(pg.receiving_yards) as yards_vs_opp, sum(pg.receiving_tds) as tds_vs_opp
    from uni as u
    join {{ ref('fct_player_game') }} as pg
      on pg.gsis_id = u.gsis_id and pg.season = u.season and pg.week < u.week and pg.opponent_team = u.opponent
     and pg.season_type = 'REG' and pg.played
    group by 1, 2, 3
),

vs_cover as (   -- with the likely cover on the field (or in the same game), every season in the history
    select n.gsis_id, n.season, n.week,
           sum(h.games) as games_vs_cover, sum(h.targets) as targets_vs_cover, sum(h.receptions) as receptions_vs_cover,
           sum(h.receiving_yards) as yards_vs_cover, sum(h.receiving_tds) as tds_vs_cover,
           min(h.season) as first_season_vs_cover, max(h.season) as last_season_vs_cover,
           string_agg(distinct h.evidence, ',' order by h.evidence) as evidence_vs_cover
    from named2 as n
    join {{ ref('mart_receiver_vs_cb') }} as h
      on h.receiver_gsis_id = n.gsis_id and h.defender_gsis_id = n.likely_cover_gsis_id
     and (h.evidence = 'on_field' or h.defender_snap_share >= 0.5)
    group by 1, 2, 3
),

quality as (
    select season, gsis_id, first_season, coverage_snaps, targets, yards_allowed, targets_per_coverage_snap,
           yards_per_target_allowed, adj_yards_per_target, passer_rating_allowed, is_ranked, n_ranked, min_coverage_snaps,
           quality_rank, quality_label, rank_targets_per_snap, rank_adj_yards_per_target, rank_passer_rating
    from {{ ref('mart_cb_rankings') }}
    where window_label = 'two_seasons'
)

select
    n.gsis_id, n.player_name, n.position, n.team, n.season, n.week, n.game_id, n.opponent, n.is_home,
    n.depth_chart_at, n.lcb_gsis_id, n.lcb_name, n.rcb_gsis_id, n.rcb_name, n.nb_gsis_id, n.nb_name,
    n.located_targets, n.tgt_left, n.tgt_middle, n.tgt_right, n.left_share, n.middle_share, n.right_share,
    n.alignment_lean, n.side_share, n.other_side_share, n.call_status, n.call_strength,
    n.likely_cover_slot, n.likely_cover_gsis_id, n.likely_cover_name,
    n.other_cover_slot,
    case n.other_cover_slot when 'LCB' then n.lcb_gsis_id when 'RCB' then n.rcb_gsis_id end as other_cover_gsis_id,
    case n.other_cover_slot when 'LCB' then n.lcb_name when 'RCB' then n.rcb_name end       as other_cover_name,
    q.first_season                    as cover_window_first_season,
    q.coverage_snaps                  as cover_coverage_snaps,
    q.targets                         as cover_targets,
    q.yards_allowed                   as cover_yards_allowed,
    q.targets_per_coverage_snap       as cover_targets_per_coverage_snap,
    q.yards_per_target_allowed        as cover_yards_per_target,
    q.adj_yards_per_target            as cover_adj_yards_per_target,
    q.passer_rating_allowed           as cover_passer_rating,
    coalesce(q.is_ranked, false)      as cover_is_ranked,
    q.quality_rank                    as cover_rank,
    q.quality_label                   as cover_label,
    q.rank_targets_per_snap           as cover_rank_targets_per_snap,
    q.rank_adj_yards_per_target       as cover_rank_adj_yards_per_target,
    q.rank_passer_rating              as cover_rank_passer_rating,
    -- the three listed corners' ranks (the card names the other outside corner on an even split, the table all three)
    ql.quality_rank as lcb_rank, ql.quality_label as lcb_label,
    qr.quality_rank as rcb_rank, qr.quality_label as rcb_label,
    qn.quality_rank as nb_rank, qn.quality_label as nb_label,
    coalesce(q.n_ranked, (select max(n_ranked) from quality as q2 where q2.season = n.season)) as cb_n_ranked,
    coalesce(q.min_coverage_snaps, (select max(min_coverage_snaps) from quality as q2 where q2.season = n.season)) as cb_min_coverage_snaps,
    coalesce(o.games_vs_opp, 0)       as games_vs_opp,
    o.targets_vs_opp, o.receptions_vs_opp, o.yards_vs_opp, o.tds_vs_opp,
    coalesce(v.games_vs_cover, 0)     as games_vs_cover,
    v.targets_vs_cover, v.receptions_vs_cover, v.yards_vs_cover, v.tds_vs_cover,
    v.first_season_vs_cover, v.last_season_vs_cover, v.evidence_vs_cover
from named2 as n
left join quality as q on q.season = n.season and q.gsis_id = n.likely_cover_gsis_id
left join quality as ql on ql.season = n.season and ql.gsis_id = n.lcb_gsis_id
left join quality as qr on qr.season = n.season and qr.gsis_id = n.rcb_gsis_id
left join quality as qn on qn.season = n.season and qn.gsis_id = n.nb_gsis_id
left join vs_opp as o on o.gsis_id = n.gsis_id and o.season = n.season and o.week = n.week
left join vs_cover as v on v.gsis_id = n.gsis_id and v.season = n.season and v.week = n.week
