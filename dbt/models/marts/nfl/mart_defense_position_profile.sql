{{ config(indexes=[{'columns': ['season', 'week', 'defense', 'position'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- How each defense has played each position, as of a week (plan R-11, metric defense_profile v1.0): only the
-- regular-season games of that season BEFORE the week, so week W's row is what was knowable at kickoff.
--   opportunity allowed : opportunities per game to the position (RB / WR / TE: targets + carries; QB:
--                         pass attempts + carries) - does it give up volume?
--   efficiency allowed  : yards per opportunity (receiving + rushing; QB passing + rushing) and TD rate per
--                         opportunity - does it give up big plays?
--   points allowed      : fantasy points per game to the position, reference scoring (as defense vs position)
--   adjusted            : points allowed above what the offenses it faced usually score to the position. Each
--                         game's baseline = that offense's points to the position in its other games before
--                         the week, shrunk toward its last-season average with the weight of 3 games (the
--                         league's last-season average for a team with no last season); the sum of the
--                         game residuals / (games + 2), so two games cannot make a defense #1.
-- Indices are the defense's rate over the league's rate for the same games window (1.10 = 10% above
-- average); the profile words use a +/-8% band. Ranks: 1 = gives up the most of that thing, of 32 (targets and
-- carries to the position ranked separately too: the comparison's reason names the one that stands out).
with team_games as (
    select t.game_id, t.season, t.week, t.team as offense, t.opponent_team as defense
    from {{ ref('fct_team_game') }} as t
    where t.season_type = 'REG'
),

positions as (
    select unnest(array['QB', 'RB', 'WR', 'TE']) as position
),

pg as (
    select game_id, team as offense, position,
           sum(points_current_scoring)                                                  as points,
           sum(coalesce(targets, 0) + coalesce(carries, 0))                             as opps_skill,
           sum(coalesce(attempts, 0) + coalesce(carries, 0))                            as opps_qb,
           sum(coalesce(receiving_yards, 0) + coalesce(rushing_yards, 0))               as yards_skill,
           sum(coalesce(passing_yards, 0) + coalesce(rushing_yards, 0))                 as yards_qb,
           sum(coalesce(receiving_tds, 0) + coalesce(rushing_tds, 0))                   as tds_skill,
           sum(coalesce(passing_tds, 0) + coalesce(rushing_tds, 0))                     as tds_qb,
           sum(coalesce(targets, 0))                                                    as targets,
           sum(coalesce(carries, 0))                                                    as carries
    from {{ ref('fct_player_game') }}
    where season_type = 'REG' and position in ('QB', 'RB', 'WR', 'TE')
    group by 1, 2, 3
),

dg as (   -- one row per defense x game x position (a position nobody played that game counts as zero)
    select tg.game_id, tg.season, tg.week, tg.offense, tg.defense, p.position,
           coalesce(pg.points, 0)                                                        as points,
           coalesce(case when p.position = 'QB' then pg.opps_qb else pg.opps_skill end, 0)   as opps,
           coalesce(case when p.position = 'QB' then pg.yards_qb else pg.yards_skill end, 0) as yards,
           coalesce(case when p.position = 'QB' then pg.tds_qb else pg.tds_skill end, 0)     as tds,
           coalesce(pg.targets, 0) as targets, coalesce(pg.carries, 0) as carries
    from team_games as tg
    cross join positions as p
    left join pg on pg.game_id = tg.game_id and pg.offense = tg.offense and pg.position = p.position
),

weeks as (
    select distinct season, week from {{ ref('dim_game') }}
    where season_type = 'REG' and season >= {{ var('seasons_start') }}
),

keys as (
    select w.season, w.week, d.defense, p.position
    from weeks as w
    join (select distinct season, defense from team_games) as d on d.season = w.season
    cross join positions as p
),

-- each offense's points to the position before the week, and its last-season average
off_asof as (
    select k.season, k.week, d.offense, d.position, count(*) as n, sum(d.points) as points
    from (select distinct season, week from keys) as k
    join dg as d on d.season = k.season and d.week < k.week
    group by 1, 2, 3, 4
),

off_prev as (
    select season + 1 as season, offense, position, avg(points) as prev_pg
    from dg group by 1, 2, 3
),

league_prev as (
    select season + 1 as season, position, avg(points) as league_prev_pg
    from dg group by 1, 2
),

games_before as (   -- the defense's games before the week, each with its offense's baseline
    select k.season, k.week, k.defense, k.position, d.game_id, d.points, d.opps, d.yards, d.tds, d.targets, d.carries,
           (coalesce(oa.points, 0) - d.points + 3 * coalesce(op.prev_pg, lp.league_prev_pg, 0))
             / nullif(coalesce(oa.n, 0) - 1 + 3, 0)                                   as offense_baseline
    from keys as k
    join dg as d on d.season = k.season and d.defense = k.defense and d.position = k.position and d.week < k.week
    left join off_asof as oa on oa.season = k.season and oa.week = k.week and oa.offense = d.offense and oa.position = d.position
    left join off_prev as op on op.season = k.season and op.offense = d.offense and op.position = d.position
    left join league_prev as lp on lp.season = k.season and lp.position = d.position
),

agg as (
    select k.season, k.week, k.defense, k.position,
           count(g.game_id)                                                             as games,
           sum(g.points) as points, sum(g.opps) as opps, sum(g.yards) as yards, sum(g.tds) as tds,
           sum(g.targets) as targets, sum(g.carries) as carries,
           sum(g.points - g.offense_baseline)                                           as resid_sum,
           avg(g.offense_baseline)                                                      as offense_baseline_pg
    from keys as k
    left join games_before as g using (season, week, defense, position)
    group by 1, 2, 3, 4
),

rates as (
    select a.*,
           case when a.games > 0 then a.points / a.games end                            as points_allowed_pg,
           case when a.games > 0 then a.opps::numeric / a.games end                     as opps_allowed_pg,
           case when a.games > 0 then a.targets::numeric / a.games end                  as targets_allowed_pg,
           case when a.games > 0 then a.carries::numeric / a.games end                  as carries_allowed_pg,
           case when a.opps > 0 then a.yards::numeric / a.opps end                      as yards_per_opp_allowed,
           case when a.opps > 0 then a.tds::numeric / a.opps end                        as td_rate_allowed,
           case when a.games > 0 then a.resid_sum / (a.games + 2) end                   as adjusted_points_pg
    from agg as a
),

league as (   -- the league's rates over the same windows (pooled: sums over sums)
    select season, week, position,
           sum(points) / nullif(sum(games), 0)                  as league_points_pg,
           sum(opps)::numeric / nullif(sum(games), 0)           as league_opps_pg,
           sum(yards)::numeric / nullif(sum(opps), 0)           as league_yards_per_opp,
           sum(tds)::numeric / nullif(sum(opps), 0)             as league_td_rate
    from agg
    group by 1, 2, 3
),

indexed as (
    select r.*, l.league_points_pg, l.league_opps_pg, l.league_yards_per_opp, l.league_td_rate,
           r.opps_allowed_pg / nullif(l.league_opps_pg, 0)                               as opportunity_index,
           r.yards_per_opp_allowed / nullif(l.league_yards_per_opp, 0)                   as efficiency_index
    from rates as r
    join league as l using (season, week, position)
)

select
    i.season, i.week, i.defense, i.position, i.games,
    round(i.points_allowed_pg::numeric, 2)          as points_allowed_pg,
    round(i.opps_allowed_pg, 2)                     as opps_allowed_pg,
    round(i.targets_allowed_pg, 2)                  as targets_allowed_pg,
    round(i.carries_allowed_pg, 2)                  as carries_allowed_pg,
    round(i.yards_per_opp_allowed, 2)               as yards_per_opp_allowed,
    round(i.td_rate_allowed, 4)                     as td_rate_allowed,
    round(i.offense_baseline_pg::numeric, 2)        as offense_baseline_pg,
    round(i.adjusted_points_pg::numeric, 2)         as adjusted_points_pg,
    round(i.league_points_pg::numeric, 2)           as league_points_pg,
    round(i.league_opps_pg, 2)                      as league_opps_pg,
    round(i.league_yards_per_opp, 2)                as league_yards_per_opp,
    round(i.league_td_rate, 4)                      as league_td_rate,
    round(i.opportunity_index, 3)                   as opportunity_index,
    round(i.efficiency_index, 3)                    as efficiency_index,
    case when i.games = 0 then null
         when i.opportunity_index >= 1.08 and i.efficiency_index >= 1.08 then 'volume and big plays'
         when i.opportunity_index >= 1.08 then 'volume'
         when i.efficiency_index >= 1.08 then 'big plays'
         when i.opportunity_index <= 0.92 and i.efficiency_index <= 0.92 then 'little of either'
         else 'about average' end                   as gives_up,
    case when i.games > 0 then rank() over (partition by i.season, i.week, i.position, i.games > 0 order by i.points_allowed_pg desc) end     as rank_points,
    case when i.games > 0 then rank() over (partition by i.season, i.week, i.position, i.games > 0 order by i.opps_allowed_pg desc) end       as rank_opportunity,
    case when i.games > 0 then rank() over (partition by i.season, i.week, i.position, i.games > 0 order by i.yards_per_opp_allowed desc) end as rank_efficiency,
    case when i.games > 0 then rank() over (partition by i.season, i.week, i.position, i.games > 0 order by i.td_rate_allowed desc) end       as rank_td_rate,
    case when i.games > 0 then rank() over (partition by i.season, i.week, i.position, i.games > 0 order by i.adjusted_points_pg desc) end    as rank_adjusted,
    case when i.games > 0 then rank() over (partition by i.season, i.week, i.position, i.games > 0 order by i.targets_allowed_pg desc) end    as rank_targets,
    case when i.games > 0 then rank() over (partition by i.season, i.week, i.position, i.games > 0 order by i.carries_allowed_pg desc) end    as rank_carries,
    count(*) filter (where i.games > 0) over (partition by i.season, i.week, i.position)                                                     as n_defenses
from indexed as i
