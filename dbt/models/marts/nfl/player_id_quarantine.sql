-- Identity problems that must not silently join: ambiguous crosswalk pairs, stat rows without
-- a player id, and skill-position Sleeper players with no NFL id at all.
select
    'ambiguous_pair'                         as issue,
    gsis_id,
    sleeper_id,
    array_to_string(sources, ',') || case when name_match then ' (names match)' else ' (names differ)' end as detail
from {{ ref('int_player_id_map') }}
where resolution = 'rejected_ambiguous'

union all

select
    'sleeper_player_without_gsis',
    null,
    sleeper_player_id,
    full_name || ' (' || coalesce(position, '?') || ', ' || coalesce(team, 'FA') || ')'
from {{ ref('stg_sleeper__players') }}
where gsis_id is null
  and position in ('QB', 'RB', 'WR', 'TE', 'K')
  and active
  and sleeper_player_id not in (select sleeper_id from {{ ref('player_id_map') }} where sleeper_id is not null)

union all

select
    'roster_week_duplicate_id',
    gsis_id,
    null,
    'season ' || season || ' week ' || week || ': ' || string_agg(full_name || '/' || team, ' vs ' order by team)
from {{ ref('stg_nflverse__rosters_weekly') }}
group by gsis_id, season, week
having count(*) > 1

union all

select
    'stat_row_without_player_id',
    null,
    null,
    'season ' || season || ' week ' || week || ' team ' || coalesce(team, '?')
from {{ source('raw', 'nfl_player_stats_week') }}
where player_id is null
