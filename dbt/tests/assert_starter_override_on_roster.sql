-- ---- IQ-2 (Wave I-Q): every hand-kept starter override still in force names a quarterback on that team's current
-- roster (int_starter_override.on_roster: a QB on the team's newest weekly roster of the season, ACT / INA / DEV). A
-- typo or a wrong team must stop the build rather than silently move a team's starter (docs/METRICS.md § "Who starts").
{{ config(severity='warn') }}  -- PO (Wave I-Q): warn, and int_pn_team_game ignores the row: a typo must not stop the night
select override_id, season, team, from_week, gsis_id, added_on, 'not a QB on the team''s current roster' as problem
from {{ ref('int_starter_override') }}
where in_force and not on_roster
-- ---- end IQ-2
