-- depends_on: {{ ref('scoring_stat_map') }}
-- Expected fantasy points per player-week = the *current* league scoring applied to ffverse
-- expected stats (pass/rush/receive only). Actual points come from fct_player_game for the same
-- player-game so both sides share one scoring version. Bonus keys (yardage-game bonuses, 40+ yard
-- TDs) are left out on purpose: a threshold on an expected yardage pays deterministically at
-- 100.0 and not at 99.9, which is not an expectation. In a league with bonuses, actual minus
-- expected therefore carries the bonus points; the docs say so.
with e as (
    select * from {{ ref('stg_nflverse__ff_opportunity') }}
),

cs as (
    select scoring_settings from {{ ref('int_current_league') }}
)

select
    e.gsis_id,
    e.season,
    e.week,
    e.game_id,
    e.team,
    e.player_name,
    e.position,
    e.targets, e.carries, e.attempts, e.rec_air_yards,
    e.receptions as receptions_exp, e.receiving_yards as receiving_yards_exp, e.receiving_tds as receiving_tds_exp,
    e.rushing_yards as rushing_yards_exp, e.rushing_tds as rushing_tds_exp,
    e.passing_yards as passing_yards_exp, e.passing_tds as passing_tds_exp,
    case when cs.scoring_settings is null then null
         else {{ league_points('cs.scoring_settings', 'e', include_bonuses=false) }} end as points_expected,
    e.ffopp_fantasy_points_exp,
    e.ffopp_fantasy_points
from e
left join cs on true
