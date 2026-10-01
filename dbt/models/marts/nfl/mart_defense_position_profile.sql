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
-- carries to the position ranked separately too: the comparison's reason names the one that stands out). The
-- per-game rows and the as-of step live in int_defense_position_game / int_defense_position_asof.
-- C5 performance hotfix: no join between large inputs. The keys (every regular-season week x every team of that
-- season x position) and the defense's games before each week (int_defense_position_asof, built with one equality
-- join to a small bridge) are stacked and grouped; the league's rates are window sums over the same rows.
with weeks as (
    select distinct season, week from {{ ref('dim_game') }}
    where season_type = 'REG' and season >= {{ var('seasons_start') }}
),

teams as (
    select distinct season, defense from {{ ref('int_defense_position_game') }}
),

keys_and_games as (
    select w.season, w.week, t.defense, unnest(array['QB', 'RB', 'WR', 'TE']) as position, true as is_key,
           null::text as game_id, null::numeric as points, null::bigint as opps, null::bigint as yards,
           null::bigint as tds, null::bigint as targets, null::bigint as carries, null::numeric as offense_baseline
    from weeks as w
    join teams as t on t.season = w.season
    union all
    select season, week, defense, position, false, game_id, points, opps, yards, tds, targets, carries, offense_baseline
    from {{ ref('int_defense_position_asof') }}
),

agg as (
    select season, week, defense, position,
           count(game_id)                                                               as games,
           sum(points) as points, sum(opps) as opps, sum(yards) as yards, sum(tds) as tds,
           sum(targets) as targets, sum(carries) as carries,
           sum(points - offense_baseline)                                               as resid_sum,
           avg(offense_baseline)                                                        as offense_baseline_pg
    from keys_and_games
    group by 1, 2, 3, 4
    having bool_or(is_key)
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

indexed as (   -- the league's rates over the same windows (pooled: sums over sums), as window sums: no join back
    select r.*,
           sum(r.points) over l / nullif(sum(r.games) over l, 0)                         as league_points_pg,
           (sum(r.opps) over l)::numeric / nullif(sum(r.games) over l, 0)                  as league_opps_pg,
           (sum(r.yards) over l)::numeric / nullif(sum(r.opps) over l, 0)                  as league_yards_per_opp,
           (sum(r.tds) over l)::numeric / nullif(sum(r.opps) over l, 0)                    as league_td_rate
    from rates as r
    window l as (partition by r.season, r.week, r.position)
),

indexed2 as (
    select i.*,
           i.opps_allowed_pg / nullif(i.league_opps_pg, 0)                               as opportunity_index,
           i.yards_per_opp_allowed / nullif(i.league_yards_per_opp, 0)                   as efficiency_index
    from indexed as i
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
from indexed2 as i
