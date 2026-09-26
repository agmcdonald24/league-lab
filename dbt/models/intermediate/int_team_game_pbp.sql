-- Team x game counts derived from plays: true dropbacks (attempts + sacks + scrambles, no
-- spikes / kneels / two-point tries), first-read charting totals and participation coverage.
-- These are the independent denominators for every play-derived share (plan §5).
with plays as (
    select * from {{ ref('fct_play') }} where posteam is not null and not is_no_play
),

charting as (
    select game_id, play_id, is_charted_target, is_first_read_target, is_designed_target
    from {{ ref('fct_play_charting') }}
),

participation as (
    select distinct game_id, play_id from {{ ref('bridge_play_participation') }}
)

select
    p.posteam                                                        as team,
    p.game_id,
    p.season,
    p.season_type,
    p.week,
    count(*)                                                         as plays,
    count(*) filter (where p.is_dropback)                            as dropbacks,
    count(*) filter (where p.is_pass_attempt and not p.is_spike and not p.is_two_point) as pass_attempts_pbp,
    count(*) filter (where p.is_sack)                                as sacks_pbp,
    count(*) filter (where p.is_scramble)                            as scrambles,
    count(*) filter (where p.is_spike)                               as spikes,
    count(*) filter (where p.is_kneel)                               as kneels,
    count(*) filter (where p.is_two_point)                           as two_point_tries,
    count(*) filter (where p.is_target)                              as targets_pbp,
    count(*) filter (where p.is_rush_attempt)                        as carries_pbp,
    count(*) filter (where p.is_target and p.is_red_zone)            as red_zone_targets,
    count(*) filter (where p.is_rush_attempt and p.is_red_zone)      as red_zone_carries,
    -- FTN coverage (2022+): charted = a read code exists on the target
    count(*) filter (where c.is_charted_target)                      as charted_targets,
    count(*) filter (where c.is_first_read_target)                   as first_read_targets,
    count(*) filter (where c.is_designed_target)                     as designed_targets,
    case when count(*) filter (where p.is_target) > 0
         then round(count(*) filter (where c.is_charted_target)::numeric / count(*) filter (where p.is_target), 4) end as charting_coverage,
    -- participation coverage: dropbacks with an on-field list
    count(*) filter (where p.is_dropback and pa.play_id is not null) as dropbacks_with_participation,
    count(*) filter (where pa.play_id is not null)                   as plays_with_participation,
    case when count(*) filter (where p.is_dropback) > 0
         then round(count(*) filter (where p.is_dropback and pa.play_id is not null)::numeric / count(*) filter (where p.is_dropback), 4) end as participation_coverage
from plays as p
left join charting as c using (game_id, play_id)
left join participation as pa using (game_id, play_id)
group by 1, 2, 3, 4, 5
