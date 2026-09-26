-- Sleeper's per-starter points must add up to the roster's matchup points (tolerance 0.05).
-- Commissioner overrides land in custom_points, which is excluded here on purpose.
{{ config(severity='warn') }}
with s as (
    select league_id, week, roster_id, round(sum(points_observed), 2) as starter_sum
    from {{ ref('league_player_week') }}
    where is_starter and is_scored_week
    group by 1, 2, 3
)
select m.league_id, m.week, m.roster_id, m.points, s.starter_sum
from {{ ref('fct_league_matchup') }} as m
join s using (league_id, week, roster_id)
where m.is_scored and abs(m.points - s.starter_sum) > 0.05
