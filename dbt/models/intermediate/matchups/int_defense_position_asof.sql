{{ config(
    indexes=[{'columns': ['season', 'week', 'defense', 'position']}],
    post_hook="analyze {{ this }}") }}
-- Each defense's games before each regular-season week, per position, with the offense's baseline as of that
-- week (plan R-11): the rows mart_defense_position_profile aggregates. One row per season x week x defense x
-- position x game played before the week. Baseline = that offense's points to the position in its OTHER games
-- before the week plus 3 x its last-season average (the league's when it has none), over (its other games + 3).
-- One equality join to the small "games before" bridge (~1.7k rows; every game sits under each later week), then
-- the offense's games before the week are a window over that fan-out, so no `week < week` join and no join back
-- (C5 performance hotfix).
with fan as (
    select b.season, b.week, d.defense, d.position, d.game_id, d.offense,
           d.points, d.opps, d.yards, d.tds, d.targets, d.carries, d.offense_prev_pg, d.league_prev_pg
    from {{ ref('int_season_week_before') }} as b
    join {{ ref('int_defense_position_game') }} as d on d.season = b.season and d.week = b.before_week
)

select season, week, defense, position, game_id, offense, points, opps, yards, tds, targets, carries,
       (sum(points) over o - points + 3 * coalesce(offense_prev_pg, league_prev_pg, 0))
         / nullif(count(*) over o - 1 + 3, 0)                                         as offense_baseline
from fan
window o as (partition by season, week, offense, position)
