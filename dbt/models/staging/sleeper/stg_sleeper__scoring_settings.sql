-- Long form of each league-season's scoring settings (one row per key).
select
    l.league_id,
    kv.key                    as scoring_key,
    kv.value::numeric         as weight
from {{ source('raw', 'sleeper_league') }} as l
cross join lateral jsonb_each_text(coalesce(l.payload -> 'scoring_settings', '{}'::jsonb)) as kv
