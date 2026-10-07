-- ---- IQ-2 (Wave I-Q, 2026-10-07): who starts, set by hand -- one row per row of the seed `starter_overrides`, with
-- its state (docs/METRICS.md § "Who starts"). A row names the quarterback the projection treats as the team's starter
-- for its UNPLAYED games of weeks from_week .. through_week (empty = until removed); int_pn_team_game applies it, never
-- to a played game (so never to a training row or to any history input).
--   in_force         false once the row has EXPIRED BY ITSELF: the team has played a game at or after from_week in
--                    which this quarterback did not lead the team's dropbacks (fct_player_game.dropbacks: pass
--                    attempts, sacks and scrambles). A played game with no dropback data cannot expire it.
--   expired_in_week  the first such week (NULL while in force)
--   on_roster        the quarterback is a QB on the team's newest weekly roster of the season (ACT, INA or DEV); a
--                    season with no weekly roster yet reads dim_player (position QB, latest team). Tested (error) for
--                    the rows in force: a typo must not silently move a team's starter.
--   led_since_week   the first week of the team's current run of played games whose dropbacks he led (NULL when the
--                    team's newest played game was led by someone else) -- the sentence on the screens reads it
--   listed_qb_id     the schedule's listing for the team's next unplayed game in the row's window (what it corrects)
with seed as (
    select row_number() over (order by s.season, s.team, s.from_week, s.gsis_id, s.added_on)::int as override_id,
           s.season::int                                                                      as season,
           {{ kd_team("case upper(trim(s.team)) when 'LAR' then 'LA' else upper(trim(s.team)) end") }} as team,
           s.from_week::int                                                                   as from_week,
           s.through_week::int                                                                as through_week,
           trim(s.gsis_id)                                                                    as gsis_id,
           s.reason, s.source, s.added_on::date                                               as added_on
    from {{ ref('starter_overrides') }} as s
),

leaders as (                    -- every played regular-season team-game's dropback leader
    select distinct on (p.game_id, p.team) p.season, p.week, p.game_id, {{ kd_team('p.team') }} as team,
           p.gsis_id as leader_id
    from {{ ref('fct_player_game') }} as p
    where p.season_type = 'REG' and coalesce(p.dropbacks, 0) > 0
    order by p.game_id, p.team, p.dropbacks desc, p.gsis_id
),

expiry as (
    select s.override_id, min(l.week) as expired_in_week
    from seed as s
    join leaders as l on l.season = s.season and l.team = s.team and l.week >= s.from_week and l.leader_id <> s.gsis_id
    group by 1
),

run as (                        -- his current run of led games: after the newest game somebody else led
    select s.override_id,
           max(l.week) filter (where l.leader_id <> s.gsis_id) as last_other_week,
           max(l.week)                                          as last_played_week
    from seed as s
    join leaders as l on l.season = s.season and l.team = s.team
    group by 1
),

led as (
    select s.override_id, min(l.week) as led_since_week
    from seed as s
    join run as r using (override_id)
    join leaders as l on l.season = s.season and l.team = s.team and l.leader_id = s.gsis_id
                     and l.week > coalesce(r.last_other_week, 0)
    group by 1
),

newest_roster as (
    select season, max(week) as week from {{ ref('stg_nflverse__rosters_weekly') }} group by 1
),

roster as (
    select r.season, {{ kd_team("case r.team when 'LAR' then 'LA' else r.team end") }} as team, r.gsis_id
    from {{ ref('stg_nflverse__rosters_weekly') }} as r
    join newest_roster as n on n.season = r.season and n.week = r.week
    where r.position = 'QB' and r.roster_status in ('ACT', 'INA', 'DEV')
),

next_listing as (               -- the schedule's listing for the team's next unplayed game in the row's window
    select distinct on (s.override_id) s.override_id, nullif(t.qb_id, '') as listed_qb_id, g.week as next_week
    from seed as s
    join {{ ref('dim_game') }} as g on g.season = s.season and g.season_type = 'REG' and g.week >= s.from_week
                                   and (s.through_week is null or g.week <= s.through_week)
    cross join lateral (values (g.home_team, g.home_qb_id), (g.away_team, g.away_qb_id)) as t(team, qb_id)
    where {{ kd_team('t.team') }} = s.team
      and not exists (select 1 from leaders as l where l.game_id = g.game_id and l.team = s.team)
    order by s.override_id, g.week
)

select
    s.override_id, s.season, s.team, s.from_week, s.through_week, s.gsis_id, s.reason, s.source, s.added_on,
    e.expired_in_week,
    e.expired_in_week is null                                                   as in_force,
    case when exists (select 1 from newest_roster as n where n.season = s.season)
         then exists (select 1 from roster as r where r.season = s.season and r.team = s.team and r.gsis_id = s.gsis_id)
         else exists (select 1 from {{ ref('dim_player') }} as d
                      where d.gsis_id = s.gsis_id and d.position = 'QB' and d.latest_team = s.team) end as on_roster,
    ld.led_since_week,
    r.last_played_week,
    nl.listed_qb_id,
    nl.next_week
from seed as s
left join expiry as e using (override_id)
left join led as ld using (override_id)
left join run as r using (override_id)
left join next_listing as nl using (override_id)
-- ---- end IQ-2
