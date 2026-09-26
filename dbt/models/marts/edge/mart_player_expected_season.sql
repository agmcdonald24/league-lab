-- Player x season (REG): actual vs expected points over games where both are known, per game.
-- The gap between them is the regression-candidate signal (buy low / sell high).
select
    gsis_id, season, max(player_name) as player_name, mode() within group (order by position) as position,
    string_agg(distinct team, ',' order by team) as teams,
    count(*) filter (where played) as games_played,
    count(*) filter (where expected_known and played) as games_with_expected,
    round(sum(points_actual), 2) as points_actual,
    round(sum(points_expected) filter (where expected_known), 2) as points_expected,
    round(sum(points_actual) filter (where expected_known) - sum(points_expected) filter (where expected_known), 2) as points_diff,
    round(avg(points_actual) filter (where played), 2) as points_per_game,
    round(avg(points_expected) filter (where expected_known and played), 2) as expected_per_game,
    round(avg(points_actual - points_expected) filter (where expected_known and played), 2) as diff_per_game,
    sum(targets) as targets, sum(carries) as carries,
    round((sum(receiving_tds_exp) filter (where expected_known))::numeric, 2) as receiving_tds_exp, sum(receiving_tds) as receiving_tds,
    round((sum(rushing_tds_exp) filter (where expected_known))::numeric, 2) as rushing_tds_exp, sum(rushing_tds) as rushing_tds
from {{ ref('mart_player_expected_points') }}
where season_type = 'REG'
group by 1, 2
