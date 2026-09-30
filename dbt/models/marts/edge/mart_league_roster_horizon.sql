-- depends_on: {{ ref('mart_lineup_recommendation') }}
-- Roster value (plan B2): every player of every current roster in the proposed B1 lineup of each week
-- of the 4-week horizon. Grain: league x roster x week x lineup row (starting slot, bench player or a
-- player who cannot play that week), straight from `ops.lineups` (proposed, not realised).
--
-- "This week" is the first regular-season week with a kickoff still ahead (now(); the same rule as
-- `league-lab lineups`' next week): during a week in progress (Thursday played, Sunday not yet) it stays
-- that week. The horizon is this week and the next three that have a proposed lineup (fewer at the end of
-- the season). Proposed lineups for every remaining week are solved by `league-lab lineups` on projection
-- v2 priced in this league's scoring (frozen at each week's first kickoff); byes, Out / IR and taxi are
-- already in them, so nothing is re-solved here.
--
-- Per unlocked starter, `replacement_*` names who takes his place when he is removed and the whole lineup
-- is re-solved. Removing one starter from a maximum-weight matching changes the lineup along one
-- alternating path (a WR out, the FLEX WR slides to WR2, a bench RB comes in at FLEX), so exactly one
-- bench player enters, or nobody worth anything (the slot stays empty or takes a player with no value yet:
-- margin = his value, no replacement named), and the total drops by
-- value(starter) - value(entrant): the entrant is the bench player worth value - `lineup_margin` (to the
-- cent; equal values: the better bench rank).
-- `is_top_at_slot_type` marks the best-valued starter of each slot type (QB, RB, WR, TE, FLEX,
-- SUPER_FLEX, K, DEF): his margin is the roster's starter strength there.
-- A view (like mart_lineup_recommendation): `ops.lineups` is rewritten by `league-lab project` after the
-- nightly dbt build. Eligibility (`fantasy_positions`) comes from mart_league_acquisitions (published;
-- staging is not). Downstream of mart_lineup_recommendation (depends_on above), whose pre-hooks create the
-- ops tables on a fresh database, so `--select mart_lineup_recommendation+` rebuilds and tests it.
{{ config(materialized='view') }}

with cur as (
    select league_id, season from {{ ref('dim_league_season') }} where is_current_season
),

this_week as (
    select c.league_id, c.season, min(g.week) as this_week
    from cur as c
    join {{ ref('dim_game') }} as g on g.season = c.season and g.season_type = 'REG' and g.kickoff_at > now()
    group by 1, 2
),

horizon as (
    -- equality joins on generated weeks (not a range join): the planner then estimates the row counts
    -- and hash-joins the replacement lookup below instead of nesting loops
    select t.league_id, t.season, t.this_week, lt.week, lt.roster_id
    from this_week as t
    cross join generate_series(0, 3) as k(k)
    join {{ source('ops', 'lineup_totals') }} as lt
      on lt.league_id = t.league_id and lt.season = t.season and lt.week = t.this_week + k.k and not lt.is_realised
),

bounds as (
    select league_id, season, this_week, min(week) as horizon_first_week, max(week) as horizon_last_week,
           count(distinct week) as horizon_weeks
    from horizon group by 1, 2, 3
),

rows as (
    select
        l.league_id, l.season, l.week, l.roster_id, l.role, l.slot, l.slot_type, l.slot_order, l.bench_rank,
        l.sleeper_player_id, l.gsis_id,
        coalesce(p.player_name, l.player_name, a.player_name)                  as player_name,
        coalesce(l.position, a.position)                                       as position,
        coalesce(a.fantasy_positions, array[coalesce(l.position, a.position)]) as fantasy_positions,
        l.value, l.value_source, l.margin, l.is_locked, l.report_status, l.reason,
        a.acquired_label, a.acquired_how_by_manager
    from {{ source('ops', 'lineups') }} as l
    join (select distinct league_id, season, week, roster_id from horizon) as h
      using (league_id, season, week, roster_id)
    left join {{ ref('dim_player') }} as p on p.gsis_id = l.gsis_id
    left join {{ ref('mart_league_acquisitions') }} as a
           on a.league_id = l.league_id and a.roster_id = l.roster_id and a.sleeper_player_id = l.sleeper_player_id
    where not l.is_realised
),

-- who comes in when a starter is removed (see the header): the bench player worth value - margin, found
-- in one pass (a window over integer cents, no self-join: values and margins are rounded to the cent)
keyed as (
    select
        r.*,
        -- only a positive value: when the margin is his whole value nobody worth anything comes in (the slot
        -- stays empty, or a player with no value yet fills it at 0), and a 0 would match any 0 on the bench
        case when r.role = 'bench' and round(r.value * 100) > 0 then round(r.value * 100)::bigint
             when r.role = 'starter' and r.margin is not null and round((r.value - r.margin) * 100) > 0
                  then round((r.value - r.margin) * 100)::bigint
        end as match_cents
    from rows as r
)

select
    r.league_id,
    r.season,
    r.roster_id,
    m.team_name,
    m.manager_name,
    r.week,
    b.this_week,
    b.horizon_first_week,
    b.horizon_last_week,
    b.horizon_weeks,
    r.week = b.this_week                                     as is_this_week,
    r.role,
    r.slot,
    r.slot_type,
    r.slot_order,
    r.bench_rank,
    r.sleeper_player_id,
    r.gsis_id,
    r.player_name,
    r.position,
    r.fantasy_positions,
    r.value                                                  as player_value,
    r.value_source,
    r.margin                                                 as lineup_margin,
    r.is_locked,
    r.report_status,
    r.reason,
    r.role = 'starter' and row_number() over (
        partition by r.league_id, r.season, r.week, r.roster_id, r.role, r.slot_type
        order by r.value desc nulls last, r.slot_order
    ) = 1                                                    as is_top_at_slot_type,
    case when r.role = 'starter' and r.match_cents is not null
         then first_value(case when r.role = 'bench' then r.sleeper_player_id end) over rep end as replacement_sleeper_player_id,
    case when r.role = 'starter' and r.match_cents is not null
         then first_value(case when r.role = 'bench' then r.player_name end) over rep end as replacement_name,
    case when r.role = 'starter' and r.match_cents is not null
         then first_value(case when r.role = 'bench' then r.value end) over rep end as replacement_value,
    r.acquired_label,
    r.acquired_how_by_manager
from keyed as r
join bounds as b using (league_id, season)
left join {{ ref('dim_league_member') }} as m using (league_id, roster_id)
window rep as (
    -- bench players first (the best bench rank among equal values), then the starters looking for them
    partition by r.league_id, r.season, r.week, r.roster_id, r.match_cents
    order by (r.role = 'bench') desc, r.bench_rank, r.slot_order
    rows between unbounded preceding and unbounded following
)
