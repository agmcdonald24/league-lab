{{ config(indexes=[{'columns': ['gsis_id', 'season']}, {'columns': ['season', 'week']}]) }}
-- Player x game: actual points (current league scoring) vs expected points (same scoring applied to
-- ffverse expected stats). Positive diff = scored above what the opportunity implied.
select
    a.gsis_id, a.game_id, a.season, a.season_type, a.week, a.team, a.player_name, a.position,
    a.played,
    a.targets, a.carries, a.attempts, a.receiving_air_yards,
    a.points_current_scoring                          as points_actual,
    e.points_expected,
    round(a.points_current_scoring - e.points_expected, 2) as points_diff,
    e.receptions_exp, a.receptions,
    e.receiving_yards_exp, a.receiving_yards,
    e.receiving_tds_exp, a.receiving_tds,
    e.rushing_yards_exp, a.rushing_yards,
    e.rushing_tds_exp, a.rushing_tds,
    e.passing_yards_exp, a.passing_yards, e.passing_tds_exp, a.passing_tds,
    e.ffopp_fantasy_points_exp, e.ffopp_fantasy_points,
    e.gsis_id is not null                              as expected_known
from {{ ref('fct_player_game') }} as a
left join {{ ref('int_expected_points_week') }} as e
       on e.gsis_id = a.gsis_id and e.game_id = a.game_id
where a.position in ('QB', 'RB', 'WR', 'TE')
