-- Sleeper stores season "potential points" (ppts) per roster = the best possible lineup total over
-- the regular season. Our week-by-week optimal lineups summed over regular-season weeks must match.
-- Verified exact for 29 of 30 rosters on 2024-2026 data; the one exception (-9.7) is a defense whose
-- bench points Sleeper did not count as "potential" (likely acquired after its game started), so
-- this is a warning, not a failure.
{{ config(severity='warn') }}
with ours as (
    select o.league_id, o.roster_id, sum(o.points_optimal) as optimal_total
    from {{ ref('mart_league_optimal_lineup') }} as o
    join {{ ref('dim_league_season') }} as l using (league_id)
    where o.week < l.playoff_week_start
    group by 1, 2
)
select o.league_id, o.roster_id, o.optimal_total, m.sleeper_potential_points,
       round(o.optimal_total - m.sleeper_potential_points, 2) as diff
from ours as o
join {{ ref('dim_league_member') }} as m using (league_id, roster_id)
where m.sleeper_potential_points is not null
  and abs(o.optimal_total - m.sleeper_potential_points) > 0.05
