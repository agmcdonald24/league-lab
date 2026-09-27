-- Plan S-01a guard: moving the league pages onto per-league pricing must not move a single number
-- for the reference league, whose scoring already priced them. For the reference league's current
-- season the per-league marts must reproduce the NFL-wide (reference-scored) marts exactly, and
-- every NFL player-game must be priced once for every current league (nothing lost in the fan-out).
with ref as (
    select league_id from {{ ref('dim_league_season') }} where is_reference_league and is_current_season
),

cur as (
    select league_id from {{ ref('dim_league_season') }} where is_current_season
),

game_points as (
    select 'game points'::text as check_name, p.gsis_id, p.season, p.game_id::text as detail,
           p.points_current_scoring::text as nfl_value, f.points::text as league_value
    from {{ ref('fct_player_game') }} as p
    join {{ ref('fct_player_game_league') }} as f
      on f.gsis_id = p.gsis_id and f.game_id = p.game_id and f.league_id = (select league_id from ref)
    where f.points is distinct from p.points_current_scoring
),

missing as (
    select 'player-game not priced for a current league'::text, p.gsis_id, p.season, (c.league_id || ' ' || p.game_id)::text,
           null::text, null::text
    from {{ ref('fct_player_game') }} as p
    cross join cur as c
    left join {{ ref('fct_player_game_league') }} as f
      on f.league_id = c.league_id and f.gsis_id = p.gsis_id and f.game_id = p.game_id
    where f.league_id is null
),

season_points as (
    select 'season points / ppg / games / position'::text, s.gsis_id, s.season, null::text,
           concat_ws(' / ', p.points_current_scoring, p.points_current_scoring_per_game, p.games_played, p.position),
           concat_ws(' / ', s.points, s.ppg, s.games_played, s.position)
    from {{ ref('mart_league_player_season') }} as s
    left join {{ ref('mart_player_season') }} as p
      on p.gsis_id = s.gsis_id and p.season = s.season and p.season_type = 'REG'
    where s.league_id = (select league_id from ref)
      and (s.points is distinct from p.points_current_scoring
           or s.ppg is distinct from p.points_current_scoring_per_game
           or s.games_played is distinct from p.games_played
           or s.position is distinct from p.position)
),

recent as (
    select distinct on (gsis_id, season) gsis_id, season, points_per_game_l3, points_per_game_l5
    from {{ ref('mart_player_recent_form') }}
    where season_type = 'REG'
    order by gsis_id, season, week desc
),

recent_form as (
    select 'recent-form ppg l3 / l5'::text, s.gsis_id, s.season, null::text,
           concat_ws(' / ', r.points_per_game_l3, r.points_per_game_l5),
           concat_ws(' / ', s.points_per_game_l3, s.points_per_game_l5)
    from {{ ref('mart_league_player_season') }} as s
    left join recent as r on r.gsis_id = s.gsis_id and r.season = s.season
    where s.league_id = (select league_id from ref)
      and (s.points_per_game_l3 is distinct from r.points_per_game_l3
           or s.points_per_game_l5 is distinct from r.points_per_game_l5)
),

expected as (
    select 'expected points / xppg / diff / games'::text, s.gsis_id, s.season, null::text,
           concat_ws(' / ', e.points_expected, e.expected_per_game, e.diff_per_game, e.games_with_expected),
           concat_ws(' / ', s.points_expected, s.expected_per_game, s.diff_per_game, s.games_with_expected)
    from {{ ref('mart_league_player_season') }} as s
    left join {{ ref('mart_player_expected_season') }} as e on e.gsis_id = s.gsis_id and e.season = s.season
    where s.league_id = (select league_id from ref)
      and (s.points_expected is distinct from e.points_expected
           or s.expected_per_game is distinct from e.expected_per_game
           or s.diff_per_game is distinct from e.diff_per_game
           or s.games_with_expected is distinct from e.games_with_expected)
)

select * from game_points
union all select * from missing
union all select * from season_points
union all select * from recent_form
union all select * from expected
