-- Every player-game stat row must resolve to a scheduled game (identity of the game is never
-- inferred from week alone).
select s.gsis_id, s.game_id, s.season, s.week
from {{ ref('stg_nflverse__player_stats_week') }} as s
left join {{ ref('dim_game') }} as g using (game_id)
where g.game_id is null
