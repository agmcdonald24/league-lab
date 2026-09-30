-- Plan B2 (review: "acquired is wrong for the dynasty roster"): every player on a current roster of every
-- loaded league has an acquisition row with an event (draft pick, trade, waiver, free agent or
-- commissioner move), read across the league chain for a dynasty. A row here is a rostered player whose
-- arrival the Sleeper history cannot explain (a missing season of transactions or drafts).
{{ config(severity='error') }}
select m.league_id, m.roster_id, m.sleeper_player_id, m.player_name
from {{ ref('mart_league_roster_membership') }} as m
join {{ ref('dim_league_season') }} as l on l.league_id = m.league_id and l.is_current_season
left join {{ ref('mart_league_acquisitions') }} as a
       on a.league_id = m.league_id and a.roster_id = m.roster_id and a.sleeper_player_id = m.sleeper_player_id
where a.acquired_how is null
