-- Plan D2: the game-context features are known before kickoff. (1) one row per universe player-week;
-- (2) for games not played yet (no final score) every column whose schedule source is filled is filled
-- too: nothing waits for the game (the harness's no-peek check runs the generic version on top);
-- (3) rest is NULL in week 1 (no previous game; also a team's first game after a postponed opener,
-- 2017 MIA / TB in week 2).
with u as (
    select gsis_id, season, week, game_id from {{ ref('int_player_week_universe') }}
),

f as (
    select f.*, g.is_final, g.kickoff_local_time as gametime, g.surface
    from {{ ref('int_player_week_game_context') }} as f
    join u using (gsis_id, season, week)
    join {{ ref('stg_nflverse__games') }} as g using (game_id)
)

select gsis_id, season, week, 'universe row without game context' as problem
from u where not exists (select 1 from {{ ref('int_player_week_game_context') }} as f
                         where (f.gsis_id, f.season, f.week) = (u.gsis_id, u.season, u.week))
union all
select gsis_id, season, week, 'future game with a schedule-derived column missing'
from f
where not is_final
  and (gc_weekday is null or gc_travel_tz is null or gc_div_game is null or gc_neutral_site is null
       or (gametime is not null and (gc_kickoff_hour_et is null or gc_primetime is null or gc_early_window is null))
       or (week > 1 and (gc_rest_days is null or gc_off_bye is null or gc_opp_rest_days is null))
       or (nullif(trim(surface), '') is not null and gc_surface_turf is null))
union all
select gsis_id, season, week, 'rest known in week 1'
from f
where week = 1 and (gc_rest_days is not null or gc_off_bye is not null)
