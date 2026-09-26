-- Sanity: team targets from the independent team table must be >= the sum of player targets
-- in that game (players can never out-target their team). Equality is expected; a shortfall
-- means the two nflverse files disagree and needs investigation.
select p.team, p.game_id, sum(p.targets) as player_target_sum, max(t.targets) as team_targets
from {{ ref('fct_player_game') }} as p
join {{ ref('fct_team_game') }} as t on t.team = p.team and t.game_id = p.game_id
group by 1, 2
having sum(p.targets) > max(t.targets)
