-- Recomputed points (league scoring x nflverse stats) should match Sleeper's observed points
-- for mapped offensive players and kickers. Differences beyond the tolerance are reported as
-- warnings: they usually mean a stat correction, a scoring key League Lab does not model
-- (bonuses), or an identity problem worth a look. Never silently accepted.
{{ config(severity='warn') }}
select league_id, season, week, roster_id, sleeper_player_id, gsis_id, player_name, position,
       points_observed, points_recomputed, round(points_observed - points_recomputed, 2) as diff
from {{ ref('league_player_week') }}
where is_scored_week
  and points_recomputed is not null
  and position in ('QB', 'RB', 'WR', 'TE', 'K')
  and abs(points_observed - points_recomputed) > {{ var('points_tolerance') }}
