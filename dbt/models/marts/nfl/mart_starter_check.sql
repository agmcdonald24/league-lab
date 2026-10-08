-- ---- IQ-2 (Wave I-Q, 2026-10-07): "Starters to check" -- one row per team for its next unplayed regular-season game of
-- the newest season: what each source says about who starts, and what the projection assumes (docs/METRICS.md § "Who
-- starts"). The PO reads it every Tuesday (and IQ-4's audit prints it): a row with agree = false is a team to check
-- against the public depth charts and, when the listing is wrong, to correct with a row in seed starter_overrides.
--   listed_*      the schedule's listing for the game (nflverse games; NULL until filled, about a week ahead)
--   depth_*       the team's newest depth-chart snapshot's first quarterback (nflverse depth charts, daily);
--                 depth_available_* the first one not ruled out (Out / Doubtful on the report, or a reserve list)
--   last_*        the quarterback who led the team's dropbacks in its newest played game this season
--   *_report      that quarterback's status on the game week's injury report (NULL: not on it, or not published yet:
--                 report_published says which); *_roster his newest weekly-roster status (ACT, INA, RES ...)
--   override_*    a hand-kept row in force for the game (int_starter_override), its date and since when he leads
--   projected_qb_id  the quarterback the projection treats as the starter (int_pn_team_game.starting_qb_id;
--                 NULL: none known -- the projection then reads the team's newest played game's starter)
--   agree         the listing, the depth chart's first quarterback and the last game's leader are the same player
--                 (false when any of the three is missing or differs)
--   listing_disputed  the listing is not depth_available_qb_id (U1: the trigger starters.unclear reads)
{{ config(materialized='table') }}
with season as (
    select max(season) as season from {{ ref('int_pn_team_game') }}
),

next_game as (
    select distinct on (t.team) t.season, t.week, t.game_id, t.team, t.opponent, t.kickoff_at, t.listed_qb_id,
           t.starting_qb_id as projected_qb_id, t.starter_source
    from {{ ref('int_pn_team_game') }} as t
    join season as s on s.season = t.season
    where not t.is_played
    order by t.team, t.week
),

leaders as (
    select distinct on (p.game_id, p.team) p.season, p.week, p.game_id, {{ kd_team('p.team') }} as team,
           p.gsis_id as leader_id, p.dropbacks
    from {{ ref('fct_player_game') }} as p
    join season as s on s.season = p.season
    where p.season_type = 'REG' and coalesce(p.dropbacks, 0) > 0
    order by p.game_id, p.team, p.dropbacks desc, p.gsis_id
),

last_lead as (
    select distinct on (l.team) l.team, l.week as last_week, l.leader_id as last_qb_id
    from leaders as l
    join next_game as n on n.team = l.team and l.week < n.week
    order by l.team, l.week desc
),

depth_all as (                  -- the newest snapshot's quarterbacks, in order
    select {{ kd_team("case d.team when 'LAR' then 'LA' else d.team end") }} as team, d.gsis_id, d.snapshot_at,
           row_number() over (partition by d.team order by d.pos_rank, d.pos_slot, d.gsis_id) as depth_rank
    from {{ ref('int_depth_chart_current') }} as d
    join season as s on s.season = d.season
    where d.pos_abb = 'QB'
),

depth as (
    select team, gsis_id as depth_qb_id, snapshot_at as depth_snapshot_at from depth_all where depth_rank = 1
),

report as materialized (
    select i.season, i.week, {{ kd_team("case i.team when 'LAR' then 'LA' else i.team end") }} as team, i.gsis_id,
           i.report_status
    from {{ ref('stg_nflverse__injuries') }} as i
    join season as s on s.season = i.season
    where i.game_type = 'REG'
),

published as (
    select distinct season, week, team from report
),

roster_week as (
    select r.season, max(r.week) as week
    from {{ ref('stg_nflverse__rosters_weekly') }} as r
    join season as s on s.season = r.season
    group by 1
),

newest_roster as materialized (
    select distinct on (r.gsis_id) r.gsis_id, r.roster_status
    from {{ ref('stg_nflverse__rosters_weekly') }} as r
    join roster_week as w on w.season = r.season and w.week = r.week
    order by r.gsis_id, (r.roster_status = 'ACT') desc, r.team
),

depth_available as (            -- the first of them not ruled out: Out / Doubtful on the game week's report, or a
    select distinct on (a.team) a.team, a.gsis_id as depth_available_qb_id   -- newest roster status outside ACT/INA/DEV
    from depth_all as a
    join next_game as n on n.team = a.team
    where not exists (select 1 from report as r where r.season = n.season and r.week = n.week and r.gsis_id = a.gsis_id
                      and r.report_status in ('Out', 'Doubtful'))
      and not exists (select 1 from newest_roster as q where q.gsis_id = a.gsis_id
                      and q.roster_status not in ('ACT', 'INA', 'DEV'))
    order by a.team, a.depth_rank
),

override as (
    select distinct on (o.team) o.team, o.gsis_id as override_qb_id, o.added_on as override_added_on,
           o.led_since_week as override_led_since_week, o.reason as override_reason
    from {{ ref('int_starter_override') }} as o
    join next_game as n on n.team = o.team and n.season = o.season and n.week >= o.from_week
                       and (o.through_week is null or n.week <= o.through_week)
    where o.in_force and n.starter_source = 'override'
    order by o.team, o.added_on desc, o.from_week desc
),

names as (
    select gsis_id, player_name from {{ ref('dim_player') }}
)

select
    n.season, n.week, n.team, n.opponent, n.game_id, n.kickoff_at,
    n.listed_qb_id,   nl.player_name as listed_name,
    rl.report_status  as listed_report,  ql.roster_status as listed_roster,
    d.depth_qb_id,    nd.player_name as depth_name,  d.depth_snapshot_at,
    rd.report_status  as depth_report,   qd.roster_status as depth_roster,
    coalesce(da.depth_available_qb_id, n.listed_qb_id) as depth_available_qb_id, nda.player_name as depth_available_name,
    ll.last_week,     ll.last_qb_id,     np.player_name as last_name,
    rp.report_status  as last_report,    qp.roster_status as last_roster,
    (pub.team is not null)                                                       as report_published,
    o.override_qb_id, nov.player_name as override_name, o.override_added_on, o.override_led_since_week,
    o.override_reason,
    n.projected_qb_id, npj.player_name as projected_name, n.starter_source,
    coalesce(n.listed_qb_id = d.depth_qb_id and d.depth_qb_id = ll.last_qb_id, false) as agree,
    -- U1, the "starter unclear" trigger kept by the rule (METRICS § "Who starts"): the listing is not the depth
    -- chart's first available quarterback (the screens drop a team the override list corrects)
    coalesce(n.listed_qb_id <> coalesce(da.depth_available_qb_id, n.listed_qb_id), false) as listing_disputed
from next_game as n
left join depth as d on d.team = n.team
left join depth_available as da on da.team = n.team
left join last_lead as ll on ll.team = n.team
left join override as o on o.team = n.team
left join published as pub on pub.season = n.season and pub.week = n.week and pub.team = n.team
left join report as rl on rl.season = n.season and rl.week = n.week and rl.team = n.team and rl.gsis_id = n.listed_qb_id
left join report as rd on rd.season = n.season and rd.week = n.week and rd.team = n.team and rd.gsis_id = d.depth_qb_id
left join report as rp on rp.season = n.season and rp.week = n.week and rp.team = n.team and rp.gsis_id = ll.last_qb_id
left join newest_roster as ql on ql.gsis_id = n.listed_qb_id
left join newest_roster as qd on qd.gsis_id = d.depth_qb_id
left join newest_roster as qp on qp.gsis_id = ll.last_qb_id
left join names as nl on nl.gsis_id = n.listed_qb_id
left join names as nd on nd.gsis_id = d.depth_qb_id
left join names as nda on nda.gsis_id = coalesce(da.depth_available_qb_id, n.listed_qb_id)
left join names as np on np.gsis_id = ll.last_qb_id
left join names as nov on nov.gsis_id = o.override_qb_id
left join names as npj on npj.gsis_id = n.projected_qb_id
-- ---- end IQ-2
