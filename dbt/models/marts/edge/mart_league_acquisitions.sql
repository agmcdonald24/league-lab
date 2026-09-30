-- How every currently rostered player came to his roster (plan B2, review finding "acquired is wrong
-- for the dynasty roster"). Grain: current league-season x rostered player (one roster per player).
--
-- The acquisition is the event that began the player's current, unbroken stint on this roster: the
-- latest move INTO this roster (a draft pick by this roster, or a completed trade / waiver / free-agent
-- / commissioner add to it), read across the league's whole chain for a dynasty
-- (dim_league_season.chain_id, linked by previous_league_id): a 2024 trade is a 2024 trade, not this
-- year's draft. A redraft or keeper league starts every season from its draft, so only the current
-- season counts there (a keeper shows as that draft's keeper pick). Roster ids are stable along a
-- Sleeper chain, so "this roster" is the same team in every season.
--
-- Draft labels: in a dynasty, the chain's first season's first draft is the startup draft, every later
-- one a rookie draft; "3.04" = round 3, 4th pick of the round. A trade names the roster that gave him
-- up (Sleeper's `drops` of the same transaction) with its manager at the time. "offseason" = before
-- that NFL season's first kickoff. A dynasty roster taken over by a new manager: what the roster held
-- before his first season is "Inherited <season> (<the roster's event>)" (`acquired_how_by_manager` =
-- 'inherited'); Sleeper records the owner and co-owners per season, so a takeover counts from that
-- season's start, and an owner who was already a co-owner has not taken over anything. `fantasy_positions` (Sleeper eligibility, e.g. Travis Hunter DB/WR)
-- is carried here for the lineup views and Trade Finder's solver, because staging is not published.
{{ config(materialized='table') }}

with cur as (
    select league_id, chain_id, season, league_type from {{ ref('dim_league_season') }} where is_current_season
),

ls as (
    select league_id, chain_id, season, league_type, previous_league_id from {{ ref('dim_league_season') }}
),

first_kickoff as (
    select season, min(kickoff_at) as first_kickoff_at
    from {{ ref('dim_game') }} where season_type = 'REG' group by 1
),

drafts as (
    select
        d.draft_id, d.league_id, d.started_at, d.teams,
        -- a dynasty chain starts with one startup draft; every later draft is a rookie draft
        case
            when ls.league_type <> 'dynasty' then 'draft'
            when coalesce(ls.previous_league_id, '0') = '0'
                 and row_number() over (partition by d.league_id order by d.started_at, d.draft_id) = 1 then 'startup'
            else 'rookie'
        end as draft_kind
    from {{ ref('stg_sleeper__drafts') }} as d
    join ls using (league_id)
),

events as (
    -- players added to a roster by a completed transaction
    select
        t.league_id, ls.chain_id, ls.season, t.week,
        t.transaction_type                          as acquired_how,
        coalesce(t.status_updated_at, t.created_at) as acquired_at,
        t.transaction_id                            as event_id,
        kv.key                                      as sleeper_player_id,
        kv.value::integer                           as roster_id,
        case when t.transaction_type = 'trade' then (t.drops ->> kv.key)::integer end as trade_partner_roster_id,
        t.waiver_bid,
        null::text                                  as draft_kind,
        null::integer                               as draft_round,
        null::integer                               as draft_pick,
        null::integer                               as draft_pick_in_round,
        false                                       as was_keeper,
        1                                           as event_order
    from {{ ref('stg_sleeper__transactions') }} as t
    join ls using (league_id)
    cross join lateral jsonb_each_text(coalesce(t.adds, '{}'::jsonb)) as kv
    where t.status = 'complete'

    union all

    -- players drafted by a roster (the pick's roster_id is the roster that made it)
    select
        d.league_id, ls.chain_id, ls.season, null::integer,
        'draft',
        d.started_at + p.pick_no * interval '1 second',   -- pick order inside the draft
        p.draft_id,
        p.sleeper_player_id,
        p.roster_id,
        null::integer,
        null::integer,
        d.draft_kind,
        p.round,
        p.pick_no,
        case when d.teams > 0 then (p.pick_no - 1) % d.teams + 1 end,
        p.is_keeper,
        0
    from {{ ref('stg_sleeper__draft_picks') }} as p
    join drafts as d using (draft_id)
    join ls on ls.league_id = d.league_id
    where p.sleeper_player_id is not null
),

members as (
    select m.*, c.chain_id, c.league_type, c.season as current_season
    from {{ ref('mart_league_roster_membership') }} as m
    join cur as c using (league_id)
),

stint as (
    select distinct on (m.league_id, m.roster_id, m.sleeper_player_id)
        m.league_id, m.current_season, m.roster_id, m.team_name, m.manager_name,
        m.sleeper_player_id, m.gsis_id, m.player_name, m.position,
        e.league_id as acquired_league_id, e.season as acquired_season, e.week as acquired_week,
        e.acquired_how, e.acquired_at, e.event_id, e.trade_partner_roster_id, e.waiver_bid,
        e.draft_kind, e.draft_round, e.draft_pick, e.draft_pick_in_round, e.was_keeper
    from members as m
    left join events as e
        on e.chain_id = m.chain_id
       and e.sleeper_player_id = m.sleeper_player_id
       and e.roster_id = m.roster_id
       and (m.league_type = 'dynasty' or e.season = m.current_season)
    order by m.league_id, m.roster_id, m.sleeper_player_id, e.acquired_at desc nulls last, e.event_order desc
),

-- who managed each roster in each league-season: Sleeper's owner and co-owners
managers as (
    select ls.league_id, ls.chain_id, ls.season, r.roster_id,
           array_append(coalesce(r.co_owners, '{}'::text[]), r.owner_id) as manager_ids
    from {{ ref('stg_sleeper__rosters') }} as r
    join ls using (league_id)
),

-- the first season of the current managers' unbroken run on this roster: the season after the last one
-- in which none of today's owner / co-owners managed it (a takeover); else the chain's first season.
-- Co-owners count: a roster whose owner and co-owner swap roles has not changed hands.
tenure as (
    select
        m.league_id, m.roster_id,
        coalesce(
            (select max(p.season) + 1 from managers as p
              where p.chain_id = m.chain_id and p.roster_id = m.roster_id and p.season < m.season
                and not (p.manager_ids && m.manager_ids)),
            (select min(p.season) from managers as p where p.chain_id = m.chain_id and p.roster_id = m.roster_id)
        ) as manager_since
    from managers as m
    join cur as c on c.league_id = m.league_id
),

labelled as (
    select
        s.*,
        s.acquired_at < fk.first_kickoff_at                    as is_offseason,
        partner.team_name                                      as trade_partner_team,
        partner.manager_name                                   as trade_partner_manager,
        t.manager_since,
        c.league_type = 'dynasty' and s.acquired_season < t.manager_since as is_inherited
    from stint as s
    join cur as c on c.league_id = s.league_id
    left join tenure as t on t.league_id = s.league_id and t.roster_id = s.roster_id
    left join first_kickoff as fk on fk.season = s.acquired_season
    left join {{ ref('dim_league_member') }} as partner
        on partner.league_id = s.acquired_league_id and partner.roster_id = s.trade_partner_roster_id
),

events_labelled as (
    select
        l.*,
        case l.acquired_how
            when 'draft' then
                case l.draft_kind when 'startup' then 'Startup draft' when 'rookie' then 'Rookie draft' else 'Draft' end
                || ' ' || l.acquired_season
                || coalesce(' · ' || l.draft_round || '.' || lpad(l.draft_pick_in_round::text, 2, '0'), '')
                || case when l.was_keeper then ' (keeper)' else '' end
            else
                case l.acquired_how
                    when 'trade' then 'Trade' when 'waiver' then 'Waiver' when 'free_agent' then 'Free agent'
                    when 'commissioner' then 'Commissioner' else initcap(replace(l.acquired_how, '_', ' '))
                end
                || ' ' || l.acquired_season
                || case when coalesce(l.is_offseason, false) or l.acquired_week is null then ' offseason' else ' wk ' || l.acquired_week end
                || case
                       when l.acquired_how = 'trade' then coalesce(' · from ' || l.trade_partner_manager, '')
                       when l.acquired_how = 'waiver' and l.waiver_bid > 0 then ' · $' || l.waiver_bid
                       else ''
                   end
        end as event_label
    from labelled as l
)

select
    l.league_id,
    l.current_season                                           as season,
    l.roster_id,
    l.team_name,
    l.manager_name,
    l.sleeper_player_id,
    l.gsis_id,
    l.player_name,
    l.position,
    sp.fantasy_positions,
    l.acquired_how,
    -- how the CURRENT manager got him: 'inherited' when the roster had him before this manager took over
    case when coalesce(l.is_inherited, false) then 'inherited' else l.acquired_how end as acquired_how_by_manager,
    l.acquired_season,
    l.acquired_week,
    l.acquired_at,
    coalesce(l.is_offseason, false)                            as is_offseason,
    l.acquired_league_id,
    l.event_id,
    l.draft_kind,
    l.draft_round,
    l.draft_pick,
    l.draft_pick_in_round,
    coalesce(l.was_keeper, false)                              as was_keeper,
    l.trade_partner_roster_id,
    l.trade_partner_team,
    l.trade_partner_manager,
    l.waiver_bid,
    l.manager_since,
    coalesce(l.is_inherited, false)                            as is_inherited,
    l.acquired_season < l.current_season                       as acquired_before_this_season,
    l.event_label,
    case when coalesce(l.is_inherited, false) then 'Inherited ' || l.manager_since || ' (' || l.event_label || ')'
         else l.event_label end                                as acquired_label
from events_labelled as l
left join {{ ref('stg_sleeper__players') }} as sp using (sleeper_player_id)
