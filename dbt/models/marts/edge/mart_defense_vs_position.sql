-- Fantasy points (current league scoring) allowed by each NFL defense to opposing players by
-- position, per game, with season-to-date and last-4 rolling totals and ranks (1 = allows the most).
with pg as (
    select opponent_team as defense, season, season_type, week, game_id, position,
           sum(points_current_scoring) as points_allowed,
           sum(targets) as targets_allowed, sum(carries) as carries_allowed,
           sum(receiving_yards) as receiving_yards_allowed, sum(rushing_yards) as rushing_yards_allowed,
           sum(receiving_tds + rushing_tds + passing_tds) as tds_allowed
    from {{ ref('fct_player_game') }}
    where position in ('QB', 'RB', 'WR', 'TE', 'K') and season_type = 'REG'
    group by 1, 2, 3, 4, 5, 6
),

w as (
    select *,
        row_number() over (partition by defense, season, position order by week) as game_no,
        sum(points_allowed) over (partition by defense, season, position order by week) as points_allowed_std,
        avg(points_allowed) over (partition by defense, season, position order by week) as points_allowed_per_game_std,
        avg(points_allowed) over (partition by defense, season, position order by week rows between 3 preceding and current row) as points_allowed_per_game_l4,
        count(*) over (partition by defense, season, position order by week rows between 3 preceding and current row) as games_l4
    from pg
)

select
    defense, season, week, game_id, position, game_no,
    round(points_allowed, 2) as points_allowed,
    targets_allowed, carries_allowed, receiving_yards_allowed, rushing_yards_allowed, tds_allowed,
    round(points_allowed_per_game_std, 2) as points_allowed_per_game_std,
    round(points_allowed_per_game_l4, 2) as points_allowed_per_game_l4,
    games_l4,
    rank() over (partition by season, week, position order by points_allowed_per_game_std desc) as rank_std,
    rank() over (partition by season, week, position order by points_allowed_per_game_l4 desc) as rank_l4
from w
