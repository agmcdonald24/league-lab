{{ config(indexes=[{'columns': ['season', 'team', 'week']}, {'columns': ['gsis_id', 'season']}]) }}
-- Role inputs per player x team-game (plan R-10, role alerts): every QB / RB / WR / TE on a team's weekly
-- roster (active, inactive, injured reserve, PUP, suspended, exempt) or who played for it, for every
-- regular-season game the team played. Unlike fct_player_game (stat rows only), a receiver who was on
-- the field without a target is here, and so is a player who missed the game, with the reason:
--   status       'played' (offensive snaps or a stat) / 'out_injured' (did not play and was on the injury
--                report — Out, Doubtful or Questionable — or on injured reserve / PUP) / 'inactive' (on the
--                roster, did not play, no injury designation: a healthy scratch or a benching)
--   snap_share   offensive snaps / team offensive snaps; 0 for a player who did not play when the game has
--                snap counts; NULL when the game has none (unknown is not zero)
--   route_share  pass plays on the field / team dropbacks with participation (the routes proxy: presence
--                on a dropback, not a counted route); NULL without participation (the NFL publishes it
--                after the season, so the current season is NULL)
--   target_share / carry_share   his targets / carries over the team's (0 when he did not play)
-- src/league_lab/signals.py reads this model to find role changes (step changes, teammate absences).
with games as (
    -- one code per franchise (kd_team: the schedule's OAK / SD -> LV / LAC, as fct_team_game and the stats say;
    -- v3 fix: matching the schedule's code against fct_team_game's lost the Raiders 2016-19 and the Chargers 2016)
    select g.game_id, g.season, g.week, g.kickoff_at, {{ kd_team('t.team') }} as team,
           {{ kd_team("case when g.home_team = t.team then g.away_team else g.home_team end") }} as opponent,
           case when g.home_team = t.team then g.home_score - g.away_score else g.away_score - g.home_score end as team_margin
    from {{ ref('dim_game') }} as g
    cross join lateral (values (g.home_team), (g.away_team)) as t(team)
    -- games that have been played: the team's box score is in (an unplayed week is not a missed game)
    join {{ ref('fct_team_game') }} as tg on tg.game_id = g.game_id and tg.team = {{ kd_team('t.team') }}
    where g.season_type = 'REG' and g.season >= {{ var('seasons_start') }}
),

roster as (
    select r.gsis_id, r.season, r.week, {{ kd_team('r.team') }} as team, r.position, r.roster_status, r.full_name
    from {{ ref('int_player_week_team') }} as r
    where r.season_type = 'REG' and r.position in ('QB', 'RB', 'WR', 'TE')
      and r.roster_status in ('ACT', 'INA', 'RES', 'PUP', 'SUS', 'EXE', 'NON')
),

stats as (
    select p.gsis_id, p.game_id, p.team, p.position, p.player_name, p.played, p.offense_snaps, p.offense_snap_pct,
           p.attempts, p.targets, p.carries, p.receptions, p.receiving_yards, p.receiving_tds, p.rushing_yards,
           p.rushing_tds, p.passing_yards, p.passing_tds, p.passing_interceptions, p.fumbles_lost_total,
           p.receiving_air_yards, p.red_zone_targets, p.red_zone_carries, p.first_read_targets, p.routes_proxy
    from {{ ref('fct_player_game') }} as p
    where p.season_type = 'REG' and p.position in ('QB', 'RB', 'WR', 'TE')
),

snaps as (
    select gsis_id, game_id, {{ kd_team('team') }} as team, offense_snaps, offense_snap_pct
    from {{ ref('int_player_game_snaps') }}
    where game_type = 'REG'
),

team_snapped as (      -- games with snap counts for the team (then a missing player row means 0 snaps)
    select distinct game_id, team from snaps
),

team_game as (
    select t.team, t.game_id, t.attempts as team_attempts, t.targets as team_targets, t.carries as team_carries,
           t.passing_air_yards as team_air_yards, tp.dropbacks_with_participation as team_dropbacks_with_participation,
           tp.first_read_targets as team_first_read_targets, tp.charted_targets as team_charted_targets
    from {{ ref('fct_team_game') }} as t
    left join {{ ref('int_team_game_pbp') }} as tp on tp.team = t.team and tp.game_id = t.game_id
    where t.season_type = 'REG'
),

injuries as (
    select distinct on (gsis_id, season, week) gsis_id, season, week, report_status
    from {{ ref('stg_nflverse__injuries') }}
    where game_type = 'REG' and gsis_id is not null
    order by gsis_id, season, week, case report_status when 'Out' then 1 when 'Doubtful' then 2 when 'Questionable' then 3 else 4 end
),

-- one row per player x team-game: the roster grid plus anyone with a stat or snap row (a call-up)
keys as (
    select r.gsis_id, g.game_id, g.team from roster as r join games as g using (season, week, team)
    union
    select gsis_id, game_id, team from stats
    union
    select s.gsis_id, s.game_id, s.team from snaps as s
    join {{ ref('dim_player') }} as dp on dp.gsis_id = s.gsis_id and dp.position in ('QB', 'RB', 'WR', 'TE')
)

select
    k.gsis_id, g.season, g.week, k.game_id, k.team, g.opponent, g.kickoff_at, g.team_margin,
    coalesce(r.position, st.position, dp.position) as position,
    coalesce(dp.player_name, st.player_name, r.full_name) as player_name,
    r.roster_status, i.report_status,
    case when coalesce(sn.offense_snaps, st.offense_snaps, 0) > 0 or coalesce(st.played, false) then 'played'
         -- on the injury report (Questionable included) and did not play: hurt, not a role decision
         when i.report_status in ('Out', 'Doubtful', 'Questionable') or r.roster_status in ('RES', 'PUP') then 'out_injured'
         else 'inactive' end as status,
    coalesce(sn.offense_snaps, st.offense_snaps, case when ts.game_id is not null then 0 end) as offense_snaps,
    coalesce(sn.offense_snap_pct, st.offense_snap_pct, case when ts.game_id is not null then 0 end) as snap_share,
    coalesce(st.targets, 0) as targets, tg.team_targets,
    coalesce(st.carries, 0) as carries, tg.team_carries,
    coalesce(st.attempts, 0) as attempts, tg.team_attempts,
    case when tg.team_targets > 0 then round(coalesce(st.targets, 0)::numeric / tg.team_targets, 4) end as target_share,
    case when tg.team_carries > 0 then round(coalesce(st.carries, 0)::numeric / tg.team_carries, 4) end as carry_share,
    case when tg.team_dropbacks_with_participation > 0
         then coalesce(st.routes_proxy, 0) end as routes_proxy,
    tg.team_dropbacks_with_participation,
    case when tg.team_dropbacks_with_participation > 0
         then round(coalesce(st.routes_proxy, 0)::numeric / tg.team_dropbacks_with_participation, 4) end as route_share,
    coalesce(st.receptions, 0) as receptions, coalesce(st.receiving_yards, 0) as receiving_yards,
    coalesce(st.receiving_tds, 0) as receiving_tds, coalesce(st.rushing_yards, 0) as rushing_yards,
    coalesce(st.rushing_tds, 0) as rushing_tds, coalesce(st.passing_yards, 0) as passing_yards,
    coalesce(st.passing_tds, 0) as passing_tds, coalesce(st.passing_interceptions, 0) as passing_interceptions,
    coalesce(st.fumbles_lost_total, 0) as fumbles_lost_total,
    coalesce(st.receiving_air_yards, 0) as receiving_air_yards, tg.team_air_yards,
    coalesce(st.red_zone_targets, 0) as red_zone_targets, coalesce(st.red_zone_carries, 0) as red_zone_carries,
    case when tg.team_charted_targets > 0 then coalesce(st.first_read_targets, 0) end as first_read_targets,
    case when tg.team_charted_targets > 0 then tg.team_first_read_targets end as team_first_read_targets,
    xp.points_expected
from keys as k
join games as g on g.game_id = k.game_id and g.team = k.team
left join roster as r on r.gsis_id = k.gsis_id and r.season = g.season and r.week = g.week and r.team = k.team
left join stats as st on st.gsis_id = k.gsis_id and st.game_id = k.game_id
left join snaps as sn on sn.gsis_id = k.gsis_id and sn.game_id = k.game_id
left join team_snapped as ts on ts.game_id = k.game_id and ts.team = k.team
left join team_game as tg on tg.game_id = k.game_id and tg.team = k.team
left join injuries as i on i.gsis_id = k.gsis_id and i.season = g.season and i.week = g.week
left join {{ ref('dim_player') }} as dp on dp.gsis_id = k.gsis_id
left join {{ ref('int_expected_points_week') }} as xp on xp.gsis_id = k.gsis_id and xp.game_id = k.game_id
where coalesce(r.position, st.position, dp.position) in ('QB', 'RB', 'WR', 'TE')
