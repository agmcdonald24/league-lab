{{ config(indexes=[{'columns': ['league_id', 'position']}, {'columns': ['gsis_id']}, {'columns': ['player_key']}]) }}
-- Plan E2 (Wave E): rest of season, per league x player. One row per league x player (gsis_id; a team defense
-- is keyed by its Sleeper id in `player_key`, gsis_id NULL), from the current board (mart_player_week_projections,
-- whatever it holds per week: a frozen kickoff board, refit values or the live board).
--
-- * Window: from `from_week` = the first regular-season week whose LAST game has not kicked off (lib.ui.current_week,
--   the rule every page uses, here at build time) to `last_week` = the league's championship week (the playoff start +
--   the winners-bracket rounds x weeks per round - 1; Sleeper's `playoff_round_type` 1 adds a week to the final, 2 plays
--   every round over two weeks), never past the board's last week. Weeks after the final count for nobody in the league.
-- * Byes are excluded: a week with no regular-season dim_game row for his team is 0 games and 0 points, not a projection.
--   The current week counts whole until its last game kicks off (as the trade engine's market does).
-- * ros_points = sum of proj_points over the window (each week as the board rounds it, to the cent); ros_games = the
--   weeks summed; playoff_points / playoff_games = the same from the league's playoff start (dim_league_season).
-- * Range: each week's 80% range read as a normal, sd_week = (p90 - p10) / 2.563, weeks independent:
--   sd_ros = sqrt(sum sd_week^2), ros_p10 / ros_p90 = ros_points -/+ 1.2816 sd_ros (centred on the projection, floored
--   at 0). Independence understates the spread (a role change or an injury moves every later week together): see
--   docs/METRICS.md § Rest of season. NULL when any week in the window has no range (unknown is not zero).
-- * Ranks within the league (rostered or free agent alike): by position and overall, by ros_points, among players on
--   an active NFL roster now (`is_ranked`: not on injured reserve or otherwise inactive at the first week of his window;
--   a team defense is always ranked). An unranked player keeps his total and has NULL ranks.
-- * Betting lines: only the weeks the board has a Vegas implied total for (`weeks_with_lines`, the current week) know
--   them; later weeks lean on usage and schedule.
with league as (
    select l.league_id, l.league_name, l.season, l.playoff_week_start, l.playoff_teams,
           coalesce((r.payload -> 'settings' ->> 'playoff_round_type')::integer, 0) as playoff_round_type,
           b.bracket_rounds
    from {{ ref('dim_league_season') }} as l
    left join {{ source('raw', 'sleeper_league') }} as r on r.league_id = l.league_id
    left join (select league_id, max(round) as bracket_rounds
               from {{ ref('stg_sleeper__brackets') }} where bracket_type = 'winners' group by league_id) as b
           on b.league_id = l.league_id
    where l.is_current_season
),

-- the one week rule (lib.ui.current_week): the first regular-season week whose last game has not kicked off
week_end as (
    select season, week, max(kickoff_at) as last_kickoff
    from {{ ref('dim_game') }}
    where season_type = 'REG'
    group by season, week
),

open_week as (
    select season, min(week) as from_week, max(week) as season_last_week
    from week_end
    where last_kickoff > now()
    group by season
),

window_ as (
    select l.*, o.from_week,
           least(
               coalesce(o.season_last_week, 18),
               l.playoff_week_start - 1
                 + coalesce(l.bracket_rounds, ceil(ln(greatest(l.playoff_teams, 2)) / ln(2))::integer)
                   * case when l.playoff_round_type = 2 then 2 else 1 end
                 + case when l.playoff_round_type = 1 then 1 else 0 end
           ) as last_week
    from league as l
    join open_week as o on o.season = l.season
),

-- the board, one row per league x player x week (a week held twice, e.g. a frozen board next to a refit, keeps the
-- frozen row, then the newest fit)
board as (
    select distinct on (p.league_id, player_key, p.week)
           p.league_id, p.season, p.week, p.gsis_id,
           coalesce(p.gsis_id, case p.team when 'LA' then 'LAR' else p.team end) as player_key,
           p.position, p.player_name, p.team, p.roster_status,
           p.proj_points, p.p10, p.p90, p.implied_team_total, p.model_version
    from {{ ref('mart_player_week_projections') }} as p
    join window_ as w on w.league_id = p.league_id and w.season = p.season
    where p.week between w.from_week and w.last_week
      and p.proj_points is not null
    order by p.league_id, player_key, p.week, (p.frozen_source is not null) desc, p.fitted_at desc nulls last
),

-- a bye (no game for his team that week) is not a projection
weeks as (
    select b.*
    from board as b
    where exists (select 1 from {{ ref('dim_game') }} as g
                  where g.season = b.season and g.week = b.week and g.season_type = 'REG'
                    and b.team in (g.home_team, g.away_team))
),

latest as (    -- name, team and NFL status as of the first week of his window
    select distinct on (league_id, player_key) league_id, player_key, gsis_id, position, player_name, team, roster_status
    from weeks
    order by league_id, player_key, week
),

totals as (
    select w.league_id, w.player_key,
           count(*)                                                                     as ros_games,
           sum(w.proj_points)                                                           as ros_points,
           count(*) filter (where w.week >= l.playoff_week_start)                       as playoff_games,
           coalesce(sum(w.proj_points) filter (where w.week >= l.playoff_week_start), 0) as playoff_points,
           case when count(w.p10) = count(*) and count(w.p90) = count(*)
                then sqrt(sum(power((w.p90 - w.p10) / 2.563, 2))) end                   as ros_sd,
           count(w.implied_team_total)                                                  as weeks_with_lines,
           string_agg(distinct w.model_version, '+' order by w.model_version)          as model_versions,
           jsonb_agg(jsonb_build_array(w.week, w.proj_points) order by w.week)         as weeks_json
    from weeks as w
    join window_ as l on l.league_id = w.league_id
    group by w.league_id, w.player_key
),

joined as (
    select l.league_id, l.league_name, l.season, t.player_key, x.gsis_id, x.position, x.player_name, x.team,
           x.roster_status,
           x.position = 'DEF' or coalesce(x.roster_status, 'ACT') = 'ACT'                as is_ranked,
           l.from_week, l.last_week, l.playoff_week_start,
           t.ros_games, round(t.ros_points, 2) as ros_points,
           round(t.ros_points / t.ros_games, 2)                                          as ros_points_per_game,
           t.playoff_games, round(t.playoff_points, 2) as playoff_points,
           round(t.ros_sd::numeric, 2)                                                   as ros_sd,
           round(greatest(0, t.ros_points - 1.2816 * t.ros_sd)::numeric, 1)             as ros_p10,
           round((t.ros_points + 1.2816 * t.ros_sd)::numeric, 1)                         as ros_p90,
           -- his team's bye(s) inside the window (no game that week); the weeks he is not counted for
           array(select gs from generate_series(l.from_week, l.last_week) as gs
                 where not exists (select 1 from {{ ref('dim_game') }} as g
                                   where g.season = l.season and g.week = gs and g.season_type = 'REG'
                                     and x.team in (g.home_team, g.away_team))
                 order by gs)                                                            as bye_weeks,
           t.weeks_with_lines, t.model_versions, t.weeks_json
    from totals as t
    join window_ as l on l.league_id = t.league_id
    join latest as x on x.league_id = t.league_id and x.player_key = t.player_key
)

select
    league_id, league_name, season, player_key, gsis_id, position, player_name, team, roster_status, is_ranked,
    from_week, last_week, playoff_week_start,
    ros_games, ros_points, ros_points_per_game, ros_p10, ros_p90, ros_sd, playoff_games, playoff_points,
    case when is_ranked then rank() over (partition by league_id, position, is_ranked order by ros_points desc, player_key) end
        as ros_rank_pos,
    case when is_ranked then rank() over (partition by league_id, is_ranked order by ros_points desc, player_key) end
        as ros_rank_all,
    bye_weeks, weeks_with_lines, model_versions, weeks_json,
    now() as built_at
from joined
