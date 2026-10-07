-- IP-1 fix round 2 (Wave I-P; the review's L4): `version_key` orders model versions by their numbers. Returns the pairs
-- it gets wrong (a must sort before b), and any version mart_projection_drift / mart_projection_backtest would read
-- as unparsable (a NULL key for a 'v…' version).
{{ config(severity='error') }}
select v.a, v.b, 'not ordered by number' as problem
from (values ('v3.9', 'v3.10'), ('v3.4', 'v3.10'), ('v2.0', 'v3.0'), ('v3.3', 'v3.4'), ('v3.4', 'v3.4.1'),
             ('v9.9', 'v10.0'), ('v3.4+wx', 'v3.5')) as v(a, b)
where not ({{ version_key('v.a') }} < {{ version_key('v.b') }})

union all
select model_version, null, 'a version without a number'
from {{ source('ops', 'projection_backtest') }}
where model_version like 'v%' and {{ version_key('model_version') }} is null
