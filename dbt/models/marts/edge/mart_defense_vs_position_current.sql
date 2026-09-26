-- One row per defense x position with the latest season-to-date / L4 values (current season).
with latest as (
    select defense, position, max(week) as week
    from {{ ref('mart_defense_vs_position') }}
    where season = (select max(season) from {{ ref('mart_defense_vs_position') }})
    group by 1, 2
)
select d.defense, d.season, d.position, d.week as through_week, d.game_no as games,
       d.points_allowed_per_game_std, d.points_allowed_per_game_l4, d.games_l4,
       rank() over (partition by d.position order by d.points_allowed_per_game_std desc) as rank_std,
       rank() over (partition by d.position order by d.points_allowed_per_game_l4 desc) as rank_l4
from {{ ref('mart_defense_vs_position') }} as d
join latest using (defense, position, week)
where d.season = (select max(season) from {{ ref('mart_defense_vs_position') }})
