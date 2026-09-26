-- Every eligible play once per context dimension (half, score state, down-distance, field zone,
-- QB on the play), so player and team counts can be summed inside identical buckets (plan §6:
-- game and context filters apply identically to numerator and denominator).
with p as (
    select
        game_id, play_id, season, season_type, week, posteam as team,
        half, score_state, down_distance, field_zone, qb_player_id,
        is_dropback, is_target, is_rush_attempt, is_complete, is_red_zone,
        receiver_player_id, rusher_player_id, receiving_yards, rushing_yards, air_yards
    from {{ ref('fct_play') }}
    where not is_no_play and posteam is not null and (is_dropback or is_target or is_rush_attempt)
),

c as (
    select game_id, play_id, is_first_read_target, is_charted_target from {{ ref('fct_play_charting') }}
),

dims as (
    select *, 'half' as context_type, half as bucket from p where half is not null
    union all
    select *, 'score_state', score_state from p where score_state is not null
    union all
    select *, 'down_distance', down_distance from p where down_distance is not null
    union all
    select *, 'field_zone', field_zone from p where field_zone is not null
    union all
    select *, 'qb', qb_player_id from p where qb_player_id is not null and is_dropback
)

select
    d.game_id, d.play_id, d.season, d.season_type, d.week, d.team,
    d.context_type, d.bucket,
    d.is_dropback, d.is_target, d.is_rush_attempt, d.is_complete,
    d.receiver_player_id, d.rusher_player_id,
    d.receiving_yards, d.rushing_yards, d.air_yards,
    coalesce(c.is_first_read_target, false) as is_first_read_target,
    coalesce(c.is_charted_target, false)    as is_charted_target
from dims as d
left join c using (game_id, play_id)
