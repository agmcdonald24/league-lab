-- Current NFL season position (last completed week, next week) for the explorer and data packs.
select * from {{ ref('int_nfl_calendar') }}
