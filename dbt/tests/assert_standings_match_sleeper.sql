-- For completed seasons the W/L computed from scored regular-season matchups must equal the
-- record Sleeper stores on the roster.
{{ config(severity='warn') }}
select s.league_id, s.roster_id, s.wins, s.sleeper_wins, s.losses, s.sleeper_losses
from {{ ref('mart_league_standings') }} as s
join {{ ref('dim_league_season') }} as l using (league_id)
where l.status = 'complete'
  and (s.wins <> s.sleeper_wins or s.losses <> s.sleeper_losses)
