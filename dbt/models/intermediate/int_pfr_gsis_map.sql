-- PFR id -> gsis id, usable only when the PFR id maps to exactly one player.
select pfr_id, min(gsis_id) as gsis_id
from {{ ref('stg_nflverse__players') }}
where pfr_id is not null
group by pfr_id
having count(distinct gsis_id) = 1
