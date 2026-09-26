-- One row per player moved by a transaction (add or drop) and the roster it affected.
with t as (
    select * from {{ source('raw', 'sleeper_transaction') }}
)

select league_id, transaction_id, week, type as transaction_type, status,
       'add' as action, kv.key as sleeper_player_id, kv.value::integer as roster_id
from t cross join lateral jsonb_each_text(coalesce(t.adds, '{}'::jsonb)) as kv
union all
select league_id, transaction_id, week, type, status,
       'drop', kv.key, kv.value::integer
from t cross join lateral jsonb_each_text(coalesce(t.drops, '{}'::jsonb)) as kv
