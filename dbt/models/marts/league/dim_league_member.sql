-- Roster (team) x league-season with its manager. Grain: league_id x roster_id.
select
    r.league_id,
    l.season,
    r.roster_id,
    r.owner_id                                     as user_id,
    coalesce(u.display_name, 'unknown')            as manager_name,
    coalesce(u.team_name, u.display_name, 'Roster ' || r.roster_id) as team_name,
    coalesce(u.is_commissioner, false)             as is_commissioner,
    r.wins                                         as sleeper_wins,
    r.losses                                       as sleeper_losses,
    r.ties                                         as sleeper_ties,
    r.points_for                                   as sleeper_points_for,
    r.points_against                               as sleeper_points_against,
    r.potential_points                             as sleeper_potential_points,
    r.waiver_budget_used,
    r.waiver_position,
    r.player_ids                                   as current_player_ids
from {{ ref('stg_sleeper__rosters') }} as r
join {{ ref('dim_league_season') }} as l using (league_id)
left join {{ ref('stg_sleeper__league_users') }} as u
       on u.league_id = r.league_id and u.user_id = r.owner_id
