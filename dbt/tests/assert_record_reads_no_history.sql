-- IZ-1 (hh1.0, docs/METRICS.md § "Us against Sleeper on the weeks Sleeper still serves"): the record's Sleeper side
-- is the last snapshot fetched before the week's first kickoff, never a line Sleeper served after the week. The
-- history pull (league_lab.ingest.sleeper_history) writes ops.sleeper_history and its own archive folder
-- (data/raw/sleeper/projections_history), never raw.sleeper_projections; a row here means one leaked into the record.
{{ config(severity='error') }}
select r.league_id, r.season, r.week, 'the record used a snapshot fetched at or after the first kickoff' as why
from {{ ref('mart_projection_record') }} as r
where r.scope = 'week' and r.sleeper_fetched_at >= r.first_kickoff_at

union all

select null as league_id, p.season, p.week, 'a history answer was loaded as a snapshot' as why
from {{ source('raw', 'sleeper_projections') }} as p
where p.file_path like '%projections_history%'
