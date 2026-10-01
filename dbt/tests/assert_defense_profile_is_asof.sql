-- Plan R-11: mart_defense_position_profile at week W uses only the defense's games BEFORE W. The games
-- count is recounted from fct_team_game independently; a row whose count includes week W or later fails.
{{ config(severity='error') }}
with recount as (
    select k.season, k.week, k.defense, count(t.game_id) as games
    from (select distinct season, week, defense from {{ ref('mart_defense_position_profile') }}) as k
    left join {{ ref('fct_team_game') }} as t
      on t.season = k.season and t.opponent_team = k.defense and t.season_type = 'REG' and t.week < k.week
    group by 1, 2, 3
)

select p.season, p.week, p.defense, p.position, p.games, r.games as recount
from {{ ref('mart_defense_position_profile') }} as p
join recount as r using (season, week, defense)
where p.games <> r.games
