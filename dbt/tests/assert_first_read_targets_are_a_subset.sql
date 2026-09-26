-- First-read targets are a subset of charted targets, which are a subset of targets; designed
-- throws are never first reads (plan §6: keep designed throws separate).
select game_id, play_id, 'first read but not charted target' as problem from {{ ref('fct_play_charting') }} where is_first_read_target and not is_charted_target
union all
select game_id, play_id, 'charted but not a target' from {{ ref('fct_play_charting') }} where is_charted_target and not is_target
union all
select game_id, play_id, 'first read and designed' from {{ ref('fct_play_charting') }} where is_first_read_target and is_designed_target
union all
select game_id, play_id, 'charted read on a two-point try' from {{ ref('fct_play_charting') }} where is_charted_target and play_id in (select play_id from {{ ref('fct_play') }} p where p.game_id = {{ ref('fct_play_charting') }}.game_id and p.is_two_point)
