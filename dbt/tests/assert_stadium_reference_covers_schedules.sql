{{ config(severity='warn') }}
-- Plan D3: every stadium_id nflverse records for a game since seasons_start is in the stadium reference
-- (src/league_lab/ingest/reference/stadiums.csv), every game resolves to a venue, and no early
-- (before 10:00 ET) kickoff resolves to a US stadium: that is an international game recorded at the
-- home team's stadium (2025: Dublin, London, Berlin, Madrid) and needs a stadium_game_venues.csv row.
-- A warning, not an error: a new venue in a future schedule must not stop the nightly; tests/test_weather.py
-- is the hard check on the archived schedules.
select g.stadium_id, min(g.game_id) as example_game, 'stadium_id not in raw.nfl_stadiums' as problem
from {{ source('raw', 'nfl_schedules') }} as g
left join {{ source('raw', 'nfl_stadiums') }} as s on s.stadium_id = g.stadium_id
where g.season >= {{ var('seasons_start') }} and s.stadium_id is null
group by g.stadium_id
union all
select w.stadium_id, w.game_id, 'game without a venue'
from {{ ref('int_game_weather') }} as w
where w.stadium_id is null
union all
select w.stadium_id, w.game_id, 'early kickoff at a US stadium (international game recorded at home?)'
from {{ ref('int_game_weather') }} as w
join {{ source('raw', 'nfl_stadiums') }} as s on s.stadium_id = w.stadium_id
where s.country = 'USA' and (w.kickoff_at at time zone 'America/New_York')::time < time '10:00'
