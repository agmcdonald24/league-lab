-- ---- IQ-2 (Wave I-Q): a starter override in force that was added (or last re-confirmed: a newer added_on) more than
-- three weeks ago warns -- the PO checks it against the public depth charts, then removes it or re-dates it.
{{ config(severity='warn') }}
select override_id, season, team, from_week, gsis_id, added_on, current_date - added_on as days_old
from {{ ref('int_starter_override') }}
where in_force and added_on < current_date - 21
-- ---- end IQ-2
