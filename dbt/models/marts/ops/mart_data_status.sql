-- What the explorer shows on its Data Status page: per source/dataset freshness and health,
-- plus how far the NFL and league data actually reach.
with parts as (
    select
        source, dataset,
        count(*)                       as partitions,
        sum(row_count)                 as rows_loaded,
        min(loaded_at)                 as first_loaded_at,
        max(loaded_at)                 as last_loaded_at,
        min(partition_key)             as first_partition,
        max(partition_key)             as last_partition
    from {{ source('ops', 'source_partition') }}
    group by 1, 2
),

-- a partition counts as failing only when its LATEST attempt failed (an early failure that a
-- later run fixed is history, not a problem) - excluding partitions the loader expects to be
-- missing (a season file not yet published)
latest_per_partition as (
    select distinct on (source, dataset, partition_key)
           source, dataset, partition_key, status, started_at, error
    from {{ source('ops', 'load_manifest') }}
    order by source, dataset, partition_key, load_id desc
),

recent_failures as (
    select source, dataset,
           count(*) as failures_7d,
           max(started_at) as last_failure_at,
           (array_agg(left(error, 200) order by started_at desc))[1] as last_error
    from latest_per_partition
    where status in ('failed', 'contract_failed') and started_at > now() - interval '7 days'
      and partition_key <> '0'  -- Sleeper's "no previous league" sentinel, once fetched by mistake
    group by 1, 2
),

last_attempt as (
    select distinct on (source, dataset) source, dataset, status as last_status, started_at as last_attempt_at
    from {{ source('ops', 'load_manifest') }}
    order by source, dataset, load_id desc
)

select
    p.source, p.dataset, p.partitions, p.rows_loaded, p.first_partition, p.last_partition,
    p.first_loaded_at, p.last_loaded_at,
    la.last_status, la.last_attempt_at,
    coalesce(f.failures_7d, 0) as failures_7d, f.last_failure_at, f.last_error
from parts as p
left join last_attempt as la using (source, dataset)
left join recent_failures as f using (source, dataset)
