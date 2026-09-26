-- Resolved crosswalk.
--   accepted                    : neither id has a competing partner
--   accepted_by_name_confirmation: ids have competing partners, but exactly one candidate on each
--                                  side carries matching provider names (name confirms, never creates)
--   accepted_by_source_majority : names don't settle it, but one candidate is asserted by strictly
--                                  more independent sources than every competitor on both sides
--   rejected_ambiguous          : everything else -> player_id_quarantine
-- pfr ids come from nflverse players (primary) with ff_playerids as fallback.
with cand as (
    select * from {{ ref('int_player_id_candidates') }}
),

g as (
    select gsis_id, count(*) as n, count(*) filter (where name_match) as matches,
           max(source_count) as max_sources, count(*) filter (where source_count = (select max(source_count) from cand c2 where c2.gsis_id = cand.gsis_id)) as at_max
    from cand group by 1
),
s as (
    select sleeper_id, count(*) as n, count(*) filter (where name_match) as matches,
           max(source_count) as max_sources, count(*) filter (where source_count = (select max(source_count) from cand c2 where c2.sleeper_id = cand.sleeper_id)) as at_max
    from cand group by 1
),

flagged as (
    select
        c.*,
        (g.n > 1 or s.n > 1) as is_contested,
        case
            when not (g.n > 1 or s.n > 1) then 'accepted'
            when c.name_match and g.matches = 1 and s.matches = 1 then 'accepted_by_name_confirmation'
            when g.matches = 0 and s.matches = 0
                 and c.source_count = g.max_sources and g.at_max = 1
                 and c.source_count = s.max_sources and s.at_max = 1 then 'accepted_by_source_majority'
            else 'rejected_ambiguous'
        end as resolution
    from cand as c
    join g using (gsis_id)
    join s using (sleeper_id)
),

pfr as (
    select p.gsis_id, coalesce(p.pfr_id, f.pfr_id) as pfr_id, p.esb_id
    from {{ ref('stg_nflverse__players') }} as p
    left join (
        select gsis_id, min(pfr_id) as pfr_id
        from {{ ref('stg_nflverse__ff_playerids') }}
        where gsis_id is not null and pfr_id is not null
        group by 1
    ) as f using (gsis_id)
)

select
    f.gsis_id,
    f.sleeper_id,
    pfr.pfr_id,
    pfr.esb_id,
    f.sources,
    f.source_count,
    f.name_match,
    f.is_contested,
    f.resolution,
    f.resolution = 'rejected_ambiguous' as is_ambiguous
from flagged as f
left join pfr using (gsis_id)
