-- Plan B3: every move the waiver engine stored is legal on the rosters it was computed on.
--   * the add is a free agent in this league on an active NFL roster (mart_player_availability: is_free_agent,
--     roster_status = 'ACT').
--     PO (Wave I-S): this also required `injury_status not in ('Out', 'IR')` — nflverse's newest report row, which
--     midweek is LAST week's game status. IS-2 moved the engine to the one definition (availability_gate: a stale
--     game status rules nothing) and this guard then failed 385 legal adds on the PO's rehearsal (Kyler Murray, Jayden
--     Daniels, Baker Mayfield ... "Out" from week 4): it would have stopped the nightly. Who sits is now checked by
--     assert_waiver_adds_do_not_sit (Sleeper's directory itself; a warning inside the builds, an error in the
--     nightly's soft availability step after `project`) — not here, because this test is a hard stop that runs
--     BEFORE `project` on the moves the previous night stored, and a status that changed overnight must not lock
--     the nightly out of ever recomputing them.
--   * the drop is on this roster, not in its IR slot, not on its taxi squad, and his game this week has
--     not kicked off (ops.lineups: not locked, not "game started (bench)");
--   * roster size: "no drop" only with an open spot (active players < starting + bench slots); a move
--     with a drop only when one drop is enough (active <= spots); an over-full roster has no move;
--   * every current roster has at least one row for the decision week (a move or 'nothing').
-- Only leagues whose rosters and free-agent statuses are unchanged since the moves were computed are
-- held to it (`inputs_current`, the fingerprint in waivers.py): a claim or a new injury report between
-- the nightly dbt build and the next `league-lab project` must not fail the night; the rebuild after
-- `project` checks every row.
{{ config(severity='error') }}
with m as (
    select * from {{ ref('mart_waiver_moves') }} where inputs_current
),

avail as (
    select * from {{ ref('mart_player_availability') }}
),

mem as (
    select * from {{ ref('mart_league_roster_membership') }}
),

spots as (
    select league_id, count(*) filter (where slot not in ('IR', 'TAXI')) as spots
    from {{ ref('dim_league_season') }}
    cross join lateral jsonb_array_elements_text(roster_positions) as rp(slot)
    where is_current_season
    group by league_id
),

active as (
    select league_id, roster_id,
           count(*) filter (where not coalesce(is_on_ir, false) and not coalesce(is_on_taxi, false)) as n_active
    from mem
    group by league_id, roster_id
),

locked as (
    select league_id, season, week, roster_id, sleeper_player_id
    from {{ source('ops', 'lineups') }}
    where not is_realised and (is_locked or reason = 'game started (bench)')
)

select 'add is not a free agent on an active NFL roster' as problem,
       m.league_id, m.roster_id, m.week, m.add_sleeper_id, m.drop_sleeper_id
from m
left join avail as a on a.league_id = m.league_id and a.sleeper_id = m.add_sleeper_id
where m.list_kind <> 'nothing'
  and (a.sleeper_id is null or not a.is_free_agent or a.roster_status is distinct from 'ACT')

union all

select 'drop is not on this roster, or is in its IR slot / on its taxi squad',
       m.league_id, m.roster_id, m.week, m.add_sleeper_id, m.drop_sleeper_id
from m
left join mem as d on d.league_id = m.league_id and d.roster_id = m.roster_id and d.sleeper_player_id = m.drop_sleeper_id
where m.drop_sleeper_id is not null
  and (d.sleeper_player_id is null or coalesce(d.is_on_ir, false) or coalesce(d.is_on_taxi, false))

union all

select 'drop is locked (his game this week has kicked off)',
       m.league_id, m.roster_id, m.week, m.add_sleeper_id, m.drop_sleeper_id
from m
join locked as k
  on k.league_id = m.league_id and k.season = m.season and k.week = m.week and k.roster_id = m.roster_id
 and k.sleeper_player_id = m.drop_sleeper_id

union all

select case when m.drop_sleeper_id is null then 'no drop, but the roster has no open spot'
            else 'one drop does not make room: the roster is over the limit' end,
       m.league_id, m.roster_id, m.week, m.add_sleeper_id, m.drop_sleeper_id
from m
join active as ac using (league_id, roster_id)
join spots as s using (league_id)
where m.list_kind <> 'nothing'
  and ((m.drop_sleeper_id is null and ac.n_active >= s.spots) or ac.n_active > s.spots)

union all

select 'no waiver row for a roster with a proposed lineup in the decision week',
       t.league_id, t.roster_id, t.week, null, null
from {{ source('ops', 'lineup_totals') }} as t
join (select distinct league_id, season, week from {{ source('ops', 'waiver_moves') }}) as w
  using (league_id, season, week)
where not t.is_realised
  and not exists (
      select 1 from {{ source('ops', 'waiver_moves') }} as x
      where x.league_id = t.league_id and x.season = t.season and x.week = t.week and x.roster_id = t.roster_id
  )
