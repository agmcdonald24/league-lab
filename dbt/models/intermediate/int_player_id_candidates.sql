-- Every (gsis_id, sleeper_id) pairing asserted by any source, with the sources that assert it and
-- whether the two providers' *names* agree. Names never create a mapping; they only confirm one
-- candidate when providers disagree (see int_player_id_map).
-- Sources: nflverse ff_playerids, Sleeper's own directory, nflverse weekly rosters, and two id
-- bridges (Sleeper espn_id <-> nflverse players espn_id; Sleeper sportradar_id <-> ff_playerids
-- sportradar_id) that catch rookies the direct crosswalks have not picked up yet.
with ff as (
    select gsis_id, sleeper_id, 'ff_playerids' as source
    from {{ ref('stg_nflverse__ff_playerids') }}
    where gsis_id is not null and sleeper_id is not null
),

sleeper as (
    select gsis_id, sleeper_player_id as sleeper_id, 'sleeper_directory' as source
    from {{ ref('stg_sleeper__players') }}
    where gsis_id is not null
),

rosters as (
    select distinct gsis_id, sleeper_id, 'nflverse_rosters' as source
    from {{ ref('stg_nflverse__rosters_weekly') }}
    where gsis_id is not null and sleeper_id is not null
),

espn_bridge as (
    select n.gsis_id, s.sleeper_player_id as sleeper_id, 'espn_bridge' as source
    from {{ ref('stg_sleeper__players') }} as s
    join {{ ref('stg_nflverse__players') }} as n on n.espn_id = s.espn_id
    where s.espn_id is not null and n.espn_id is not null
),

sportradar_bridge as (
    select f.gsis_id, s.sleeper_player_id as sleeper_id, 'sportradar_bridge' as source
    from {{ ref('stg_sleeper__players') }} as s
    join {{ ref('stg_nflverse__ff_playerids') }} as f on f.sportradar_id = s.sportradar_id
    where s.sportradar_id is not null and f.sportradar_id is not null and f.gsis_id is not null
),

unioned as (
    select * from ff
    union all select * from sleeper
    union all select * from rosters
    union all select * from espn_bridge
    union all select * from sportradar_bridge
),

pairs as (
    select
        gsis_id,
        sleeper_id,
        array_agg(distinct source order by source) as sources,
        count(distinct source)                     as source_count
    from unioned
    group by 1, 2
),

names as (
    select
        p.gsis_id, p.sleeper_id,
        lower(regexp_replace(coalesce(n.display_name, ''), '[^a-z]', '', 'gi'))  as nfl_name_key,
        lower(regexp_replace(coalesce(s.full_name, ''), '[^a-z]', '', 'gi'))     as sleeper_name_key
    from pairs as p
    left join {{ ref('stg_nflverse__players') }} as n using (gsis_id)
    left join {{ ref('stg_sleeper__players') }} as s on s.sleeper_player_id = p.sleeper_id
)

select
    p.gsis_id,
    p.sleeper_id,
    p.sources,
    p.source_count,
    n.nfl_name_key <> '' and n.nfl_name_key = n.sleeper_name_key as name_match
from pairs as p
join names as n using (gsis_id, sleeper_id)
