-- Plan S-01a acceptance: for rostered players, the per-league points that price every NFL game in a
-- current league-season (fct_player_game_league) equal league_player_week.points_recomputed to the
-- cent — the same stats row, the same play-by-play long-TD counts, the same scoring map. A row here
-- means the two pricings disagree, or a rostered player-game with NFL stats is missing from the mart.
with cur as (
    select league_id from {{ ref('dim_league_season') }} where is_current_season
),

lpw as (
    select league_id, season, week, roster_id, sleeper_player_id, gsis_id, game_id, player_name, position,
           points_observed, points_recomputed
    from {{ ref('league_player_week') }}
    where league_id in (select league_id from cur)
      and points_recomputed is not null
)

select
    lpw.*,
    f.points                                   as points_league,
    round(f.points - lpw.points_recomputed, 2) as diff
from lpw
left join {{ ref('fct_player_game_league') }} as f
       on f.league_id = lpw.league_id and f.gsis_id = lpw.gsis_id and f.game_id = lpw.game_id
where f.points is null
   or round(f.points, 2) <> round(lpw.points_recomputed, 2)
