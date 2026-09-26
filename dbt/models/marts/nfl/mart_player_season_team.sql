-- Same as mart_player_season but split by historical offensive team (plan §5: team splits are
-- a separate view). Useful for mid-season trades.
with pg as (select * from {{ ref('fct_player_game') }})

select
    gsis_id, season, season_type, team,
    max(player_name) as player_name,
    mode() within group (order by position) as position,
    count(*) filter (where played) as games_played,
    min(week) as first_week, max(week) as last_week,
    sum(targets) as targets, sum(receptions) as receptions, sum(receiving_yards) as receiving_yards,
    sum(receiving_tds) as receiving_tds, sum(receiving_air_yards) as receiving_air_yards,
    sum(carries) as carries, sum(rushing_yards) as rushing_yards, sum(rushing_tds) as rushing_tds,
    sum(attempts) as attempts, sum(passing_yards) as passing_yards, sum(passing_tds) as passing_tds,
    -- team denominators over appearance games only (plan §5)
    sum(team_targets) filter (where played) as team_targets, sum(team_carries) filter (where played) as team_carries, sum(team_air_yards) filter (where played) as team_air_yards,
    case when sum(team_targets) filter (where played) > 0 then round(sum(targets)::numeric / sum(team_targets) filter (where played), 4) end as target_share,
    case when sum(team_carries) filter (where played) > 0 then round(sum(carries)::numeric / sum(team_carries) filter (where played), 4) end as carry_share,
    case when sum(team_air_yards) filter (where played) <> 0 then round(sum(receiving_air_yards)::numeric / sum(team_air_yards) filter (where played), 4) end as air_yards_share,
    sum(points_current_scoring) as points_current_scoring,
    -- play-derived (Phase 2), same window rules
    sum(routes_proxy) as routes_proxy,
    sum(team_dropbacks_with_participation) filter (where routes_proxy is not null and played) as team_dropbacks_with_participation,
    case when sum(team_dropbacks_with_participation) filter (where routes_proxy is not null and played) > 0
         then round(sum(routes_proxy)::numeric / sum(team_dropbacks_with_participation) filter (where routes_proxy is not null and played), 4) end as route_participation,
    case when sum(routes_proxy) > 0 then round(sum(targets) filter (where routes_proxy is not null)::numeric / sum(routes_proxy), 4) end as tprr_proxy,
    case when sum(routes_proxy) > 0 then round(sum(receiving_yards) filter (where routes_proxy is not null)::numeric / sum(routes_proxy), 2) end as yprr_proxy,
    sum(charted_targets) as charted_targets, sum(first_read_targets) as first_read_targets, sum(designed_targets) as designed_targets,
    sum(team_first_read_targets) filter (where played) as team_first_read_targets, sum(team_charted_targets) filter (where played) as team_charted_targets,
    case when sum(team_first_read_targets) filter (where played) > 0 then round(sum(first_read_targets)::numeric / sum(team_first_read_targets) filter (where played), 4) end as first_read_target_share,
    case when sum(team_targets) filter (where played) > 0 and sum(team_charted_targets) filter (where played) > 0 then round(sum(team_charted_targets) filter (where played)::numeric / sum(team_targets) filter (where played), 4) end as charting_coverage,
    sum(red_zone_targets) as red_zone_targets, sum(red_zone_carries) as red_zone_carries,
    sum(dropbacks) as dropbacks
from pg
group by 1, 2, 3, 4
