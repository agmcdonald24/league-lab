{{ config(
    indexes=[{'columns': ['game_id', 'defense', 'position'], 'unique': True},
             {'columns': ['season', 'week', 'defense', 'position']},
             {'columns': ['season', 'week', 'offense', 'position']}],
    pre_hook=["analyze {{ ref('fct_team_game') }}", "analyze {{ ref('fct_player_game') }}"],
    post_hook="analyze {{ this }}") }}
-- One row per defense x regular-season game x position (QB / RB / WR / TE): what the offense's players at the
-- position did against that defense (plan R-11; feeds int_defense_position_asof and mart_defense_position_profile).
-- A position nobody played that game counts as zero. offense_prev_pg / league_prev_pg = the offense's (the league's)
-- points per game to the position the season before (the baseline's prior).
-- No join (C5 performance hotfix): the team-game x position frame and the player rows are stacked and grouped on
-- (game, offense, position); the priors are stacked as extra rows and broadcast with window functions. The
-- pre-hooks give the upstream tables statistics whatever order a parallel build ran them in.
with frame_and_players as (
    select t.game_id, t.team as offense, unnest(array['QB', 'RB', 'WR', 'TE']) as position,
           t.season, t.week, t.opponent_team as defense, true as is_frame,
           null::numeric as points, null::integer as opps_skill, null::integer as opps_qb, null::integer as yards_skill,
           null::integer as yards_qb, null::integer as tds_skill, null::integer as tds_qb, null::integer as targets,
           null::integer as carries
    from {{ ref('fct_team_game') }} as t
    where t.season_type = 'REG'
    union all
    select game_id, team, position, null, null, null, false,
           points_current_scoring,
           coalesce(targets, 0) + coalesce(carries, 0),
           coalesce(attempts, 0) + coalesce(carries, 0),
           coalesce(receiving_yards, 0) + coalesce(rushing_yards, 0),
           coalesce(passing_yards, 0) + coalesce(rushing_yards, 0),
           coalesce(receiving_tds, 0) + coalesce(rushing_tds, 0),
           coalesce(passing_tds, 0) + coalesce(rushing_tds, 0),
           coalesce(targets, 0),
           coalesce(carries, 0)
    from {{ ref('fct_player_game') }}
    where season_type = 'REG' and position in ('QB', 'RB', 'WR', 'TE')
),

g as (
    select game_id, max(season) as season, max(week) as week, offense, max(defense) as defense, position,
           coalesce(sum(points), 0)                                                                    as points,
           coalesce(case when position = 'QB' then sum(opps_qb) else sum(opps_skill) end, 0)           as opps,
           coalesce(case when position = 'QB' then sum(yards_qb) else sum(yards_skill) end, 0)         as yards,
           coalesce(case when position = 'QB' then sum(tds_qb) else sum(tds_skill) end, 0)             as tds,
           coalesce(sum(targets), 0)                                                                   as targets,
           coalesce(sum(carries), 0)                                                                   as carries
    from frame_and_players
    group by game_id, offense, position
    having bool_or(is_frame)
),

priors as (   -- the games, then each offense's and the league's season averages filed under the next season
    select game_id, season, week, offense, defense, position, points, opps, yards, tds, targets, carries,
           1 as kind, null::numeric as prev_pg, null::numeric as lg_prev_pg
    from g
    union all
    select null, season + 1, null, offense, null, position, null, null, null, null, null, null, 2, avg(points), null
    from g group by season, offense, position
    union all
    select null, season + 1, null, null, null, position, null, null, null, null, null, null, 3, null, avg(points)
    from g group by season, position
),

broadcast as (
    select p.*,
           max(p.prev_pg) over (partition by p.season, p.offense, p.position)                          as offense_prev_pg,
           max(p.lg_prev_pg) over (partition by p.season, p.position)                                  as league_prev_pg
    from priors as p
)

select game_id, season, week, offense, defense, position, points, opps, yards, tds, targets, carries,
       offense_prev_pg, league_prev_pg
from broadcast
where kind = 1
