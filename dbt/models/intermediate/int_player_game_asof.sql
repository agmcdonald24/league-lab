{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week']}]) }}
-- As-of each played regular-season game: what was known about the player AFTER that game
-- (season-to-date, last-3 and last-5 windows for points, expected points and usage). The
-- feature-snapshot mart joins the latest row with week < target week, so a projection for
-- week N never sees week N or later (T-11: no peeking).
with rf as (
    select
        gsis_id, game_id, season, season_type, week, game_no, team, player_name, position,
        games_l3, games_l5,
        target_share_l3, target_share_l5, target_share_std, targets_l3,
        carry_share_l3, carry_share_l5, carry_share_std, carries_l3,
        air_yards_share_l3, snap_pct_l3, snap_pct_l5,
        points_per_game_l3, points_per_game_l5, points_per_game_std,
        first_read_share_l3, first_read_share_std, route_participation_l3
    from {{ ref('mart_player_recent_form') }}
    where season_type = 'REG'
),

xp as (
    select gsis_id, game_id, points_expected
    from {{ ref('int_expected_points_week') }}
),

pg as (
    select gsis_id, game_id, attempts, targets, carries, points_current_scoring
    from {{ ref('fct_player_game') }}
),

w as (
    select
        rf.*,
        pg.attempts, pg.targets, pg.carries, pg.points_current_scoring,
        xp.points_expected,
        count(xp.points_expected) over (partition by rf.gsis_id, rf.season order by rf.week) as games_with_xp_std,
        avg(xp.points_expected)   over (partition by rf.gsis_id, rf.season order by rf.week) as xppg_std,
        avg(xp.points_expected)   over (partition by rf.gsis_id, rf.season order by rf.week rows between 2 preceding and current row) as xppg_l3,
        avg(xp.points_expected)   over (partition by rf.gsis_id, rf.season order by rf.week rows between 4 preceding and current row) as xppg_l5,
        avg(pg.attempts)          over (partition by rf.gsis_id, rf.season order by rf.week rows between 2 preceding and current row) as attempts_l3,
        avg(pg.attempts)          over (partition by rf.gsis_id, rf.season order by rf.week) as attempts_std,
        stddev_samp(pg.points_current_scoring) over (partition by rf.gsis_id, rf.season order by rf.week) as points_sd_std
    from rf
    left join xp using (gsis_id, game_id)
    left join pg using (gsis_id, game_id)
)

select
    gsis_id, game_id, season, week, game_no as games_to_date, team, player_name, position,
    points_current_scoring, points_expected,
    points_per_game_std as ppg_std, points_per_game_l3 as ppg_l3, points_per_game_l5 as ppg_l5, points_sd_std,
    games_with_xp_std, round(xppg_std::numeric, 3) as xppg_std, round(xppg_l3::numeric, 3) as xppg_l3, round(xppg_l5::numeric, 3) as xppg_l5,
    target_share_std, target_share_l3, target_share_l5, targets_l3,
    carry_share_std, carry_share_l3, carry_share_l5, carries_l3,
    air_yards_share_l3, snap_pct_l3, snap_pct_l5,
    first_read_share_std, first_read_share_l3, route_participation_l3,
    round(attempts_std::numeric, 2) as attempts_std, round(attempts_l3::numeric, 2) as attempts_l3
from w
