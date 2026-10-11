{{ config(indexes=[{'columns': ['season', 'season_type', 'situation']}, {'columns': ['gsis_id', 'game_id']}]) }}
-- Player x game x game situation (IX-3, Wave I-X; docs/METRICS.md § "Stats by game situation"): his targets,
-- receptions, receiving yards, carries and rushing yards in the plays of each situation, next to his team's targets,
-- carries and dropbacks in the SAME plays of the SAME game — so the Stats table can sum any window of games and divide
-- numerator by denominator inside one situation. The three situations are IX-2's (the card's Usage tab), from
-- int_play_context_long's pre-play score state:
--   trailing = his team behind by 9 or more (trailing_9plus)
--   close    = 8 points or fewer either way, tied included (trailing_1_8, tied, leading_1_8)
--   leading  = his team ahead by 9 or more (leading_9plus)
-- A row exists for every situation his team saw in a game he played (a zero is a real zero; a missing row means his
-- team never was in it that game). Same play set and same team join as mart_player_context.
with long as (
    select
        game_id, team, is_dropback, is_target, is_rush_attempt, is_complete,
        receiver_player_id, rusher_player_id, receiving_yards, rushing_yards,
        case
            when bucket = 'trailing_9plus' then 'trailing'
            when bucket in ('trailing_1_8', 'tied', 'leading_1_8') then 'close'
            when bucket = 'leading_9plus' then 'leading'
        end as situation
    from {{ ref('int_play_context_long') }}
    where context_type = 'score_state'
),

appearances as (
    select gsis_id, game_id, season, season_type, week, team, position
    from {{ ref('fct_player_game') }}
    where played and position in ('QB', 'RB', 'WR', 'TE')
),

team_sit as (
    select
        team, game_id, situation,
        count(*) filter (where is_dropback)      as team_dropbacks,
        count(*) filter (where is_target)        as team_targets,
        count(*) filter (where is_rush_attempt)  as team_carries
    from long
    where situation is not null
    group by 1, 2, 3
),

player_sit as (
    select gsis_id, game_id, situation,
           sum(targets) as targets, sum(receptions) as receptions, sum(receiving_yards) as receiving_yards,
           sum(carries) as carries, sum(rushing_yards) as rushing_yards
    from (
        select receiver_player_id as gsis_id, game_id, situation,
               count(*) filter (where is_target)                      as targets,
               count(*) filter (where is_target and is_complete)      as receptions,
               coalesce(sum(receiving_yards) filter (where is_target), 0) as receiving_yards,
               0::bigint as carries, 0::numeric as rushing_yards
        from long
        where receiver_player_id is not null and situation is not null
        group by 1, 2, 3
        union all
        select rusher_player_id, game_id, situation, 0, 0, 0,
               count(*) filter (where is_rush_attempt),
               coalesce(sum(rushing_yards) filter (where is_rush_attempt), 0)
        from long
        where rusher_player_id is not null and situation is not null
        group by 1, 2, 3
    ) as u
    group by 1, 2, 3
)

select
    a.gsis_id, a.game_id, a.season, a.season_type, a.week, a.team, a.position, t.situation,
    t.team_dropbacks, t.team_targets, t.team_carries,
    t.team_dropbacks + t.team_carries                          as team_plays,
    coalesce(p.targets, 0)                                     as targets,
    coalesce(p.receptions, 0)                                  as receptions,
    coalesce(p.receiving_yards, 0)                             as receiving_yards,
    coalesce(p.carries, 0)                                     as carries,
    coalesce(p.rushing_yards, 0)                               as rushing_yards
from appearances as a
join team_sit as t on t.team = a.team and t.game_id = a.game_id
left join player_sit as p on p.gsis_id = a.gsis_id and p.game_id = a.game_id and p.situation = t.situation
