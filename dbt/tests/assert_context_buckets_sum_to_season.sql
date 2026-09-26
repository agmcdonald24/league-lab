-- Context splits partition the season: summing a player's halves (H1+H2+OT) must give his season
-- targets and carries, and the team denominators must match the season mart's appearance-game
-- totals. Tolerance 1 on player counts and 2 on team counts: nflverse's published weekly stats and
-- its own play-by-play disagree by one target (Bell 2017), one carry (Ogunbowale 2024) and one
-- team target in two 2016/2017 games. Any row here means a bucket is missing or double-counted.
select s.gsis_id, s.season, s.season_type, s.targets, sum(c.targets) as targets_from_halves,
       s.carries, sum(c.carries) as carries_from_halves, s.team_targets, sum(c.team_targets) as team_targets_from_halves
from {{ ref('mart_player_season') }} as s
join {{ ref('mart_player_context') }} as c using (gsis_id, season, season_type)
where c.context_type = 'half' and s.position in ('QB', 'RB', 'WR', 'TE')
group by 1, 2, 3, 4, 6, 8
having abs(s.targets - sum(c.targets)) > 1 or abs(s.carries - sum(c.carries)) > 1 or abs(s.team_targets - sum(c.team_targets)) > 2
