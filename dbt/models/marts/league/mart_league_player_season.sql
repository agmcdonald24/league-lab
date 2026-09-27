{{ config(indexes=[{'columns': ['league_id', 'season', 'gsis_id']}]) }}
-- League x player x NFL regular season (plan S-01a): the per-game numbers league pages show —
-- season points and PPG, recent-form PPG windows, expected points, positional ranks — priced in
-- that league's own current scoring (fct_player_game_league). Grain: league_id, gsis_id, season.
-- The arithmetic mirrors the NFL-wide (reference-scored) marts exactly, so for the reference league
-- every column reproduces them to the cent (assert_reference_league_matches_nfl_marts):
--   points, ppg                 <- mart_player_season.points_current_scoring / _per_game
--                                  (points over every stat row; per appearance game)
--   points_per_game_l3 / _l5    <- mart_player_recent_form.points_per_game_l3 / _l5 at the player's
--                                  latest appearance of the season (last 3 / 5 appearance games)
--   games_with_expected, points_expected, expected_per_game, diff_per_game
--                               <- mart_player_expected_season (QB/RB/WR/TE game rows; per game over
--                                  appearances with an expected-points row; NULL for anyone else)
--   position_rank_points / _ppg <- the keeper-facts ranks: all NFL players at the position
with g as (
    select * from {{ ref('fct_player_game_league') }}
    where season_type = 'REG'
),

recent as (
    select league_id, gsis_id, season, points,
           row_number() over (partition by league_id, gsis_id, season order by week desc) as games_ago
    from g
    where played
),

form as (
    select
        league_id, gsis_id, season,
        round(sum(points) filter (where games_ago <= 3) / count(*) filter (where games_ago <= 3), 2) as points_per_game_l3,
        round(sum(points) filter (where games_ago <= 5) / count(*) filter (where games_ago <= 5), 2) as points_per_game_l5
    from recent
    group by 1, 2, 3
),

agg as (
    select
        league_id, gsis_id, season,
        mode() within group (order by position)                                        as position,
        max(player_name)                                                               as player_name,
        count(*) filter (where played)                                                 as games_played,
        sum(points)                                                                    as points,
        -- expected points: skill-position game rows only, like mart_player_expected_points
        count(*) filter (where position in ('QB', 'RB', 'WR', 'TE'))                   as skill_rows,
        count(*) filter (where position in ('QB', 'RB', 'WR', 'TE') and expected_known and played) as games_with_expected,
        round(sum(points_expected) filter (where position in ('QB', 'RB', 'WR', 'TE') and expected_known), 2) as points_expected,
        round(avg(points_expected) filter (where position in ('QB', 'RB', 'WR', 'TE') and expected_known and played), 2) as expected_per_game,
        round(avg(points - points_expected) filter (where position in ('QB', 'RB', 'WR', 'TE') and expected_known and played), 2) as diff_per_game
    from g
    group by 1, 2, 3
),

s as (
    select
        a.*,
        case when a.games_played > 0 then round(a.points / a.games_played, 2) end as ppg
    from agg as a
)

select
    s.league_id,
    s.gsis_id,
    s.season,
    s.player_name,
    s.position,
    s.games_played,
    s.points,
    s.ppg,
    f.points_per_game_l3,
    f.points_per_game_l5,
    -- a player without a skill-position game row has no expected-points season at all (NULL, not 0)
    case when s.skill_rows > 0 then s.games_with_expected end                        as games_with_expected,
    s.points_expected,
    s.expected_per_game,
    s.diff_per_game,
    rank() over (partition by s.league_id, s.season, s.position order by s.points desc nulls last) as position_rank_points,
    rank() over (partition by s.league_id, s.season, s.position order by s.ppg desc nulls last)    as position_rank_ppg
from s
left join form as f using (league_id, gsis_id, season)
