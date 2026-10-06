{{ config(indexes=[{'columns': ['gsis_id', 'game_id'], 'unique': True}]) }}
-- IM-1 (Wave I-M): the play-by-play numerators behind the Stats Explorer's efficiency columns, player x game.
-- Beside int_player_game_pbp, not inside it: widening that model rebuilds fct_player_game and the 54 models under it
-- (the projection chain), and widens fct_player_game on the hosted copy; this one is read only by
-- mart_player_game_advanced. The play eligibility is fct_play's, the same flags int_player_game_pbp counts with:
--   * a target is `is_target` (two-point tries excluded; reconciles with nflverse weekly targets), a carry is
--     `is_rush_attempt` (scrambles and kneels included), a dropback is `is_dropback` (attempts + sacks + scrambles,
--     spikes excluded) by the QB on the play (`qb_player_id`);
--   * success is nflfastR's play success (the play's EPA > 0); EPA is the play's EPA, so a dropback's EPA includes a
--     catch-and-fumble by his receiver (nflfastR's qb_epa is not in fct_play) — said in docs/METRICS.md;
--   * no-plays (penalties that wipe the play) are never counted.
with plays as (
    select * from {{ ref('fct_play') }} where not is_no_play
),

recv as (
    select receiver_player_id as gsis_id, game_id,
           count(*) filter (where is_target and success)                      as target_successes,
           count(*) filter (where is_target and epa is not null)              as targets_with_epa
    from plays
    where receiver_player_id is not null
    group by 1, 2
),

rush as (
    select rusher_player_id as gsis_id, game_id,
           count(*) filter (where is_rush_attempt and success)                as carry_successes,
           count(*) filter (where is_rush_attempt and epa is not null)        as carries_with_epa,
           sum(rushing_yards) filter (where is_rush_attempt and is_scramble)  as scramble_yards
    from plays
    where rusher_player_id is not null
    group by 1, 2
),

qb as (
    select qb_player_id as gsis_id, game_id,
           count(*) filter (where is_dropback and success)                    as dropback_successes,
           count(*) filter (where is_dropback and epa is not null)            as dropbacks_with_epa,
           round(sum(epa) filter (where is_dropback), 3)                      as dropback_epa
    from plays
    where qb_player_id is not null
    group by 1, 2
),

keys as (
    select gsis_id, game_id from recv
    union select gsis_id, game_id from rush
    union select gsis_id, game_id from qb
)

select
    k.gsis_id,
    k.game_id,
    coalesce(recv.target_successes, 0)   as target_successes,
    coalesce(recv.targets_with_epa, 0)   as targets_with_epa,
    coalesce(rush.carry_successes, 0)    as carry_successes,
    coalesce(rush.carries_with_epa, 0)   as carries_with_epa,
    coalesce(rush.scramble_yards, 0)     as scramble_yards,
    qb.dropback_successes,
    qb.dropbacks_with_epa,
    qb.dropback_epa
from keys as k
left join recv using (gsis_id, game_id)
left join rush using (gsis_id, game_id)
left join qb using (gsis_id, game_id)
