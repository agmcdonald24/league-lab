-- depends_on: {{ ref('mart_lineup_recommendation') }}
-- Roster value (plan B2), one row per current league x roster, from the B1 lineup service
-- (`ops.lineup_totals`, proposed lineups; mart_league_roster_horizon for names and the horizon):
--   * this week's lineup value (the best legal lineup, every slot solved together: FLEX and SUPER_FLEX
--     are filled by eligibility, never "a second QB slot"), its weakest replaceable slot (the starter with
--     the smallest margin), who replaces him and by how much;
--   * depth = this week's bench value: the best legal lineup the bench alone would field if every starter
--     sat (a QB3 counts here, never in the starting lineup unless he beats a starter);
--   * the 4-week horizon: the sum of the proposed lineup values of this week and the next three (byes,
--     injuries and taxi already in each week's lineup), and its weakest week.
-- Ranks across the league, each naming its horizon, are in mart_league_roster_rankings. Replaces
-- mart_league_positional_strength (season PPG of the top-N at each position, superflex counted as a QB
-- slot) as the roster view of Team Hub, Trade Finder and League.
{{ config(materialized='view') }}

with h as materialized (
    select * from {{ ref('mart_league_roster_horizon') }}
),

weeks as (
    select distinct league_id, season, roster_id, team_name, manager_name, week, this_week,
                    horizon_first_week, horizon_last_week, horizon_weeks
    from h
),

tot as (
    select w.*, t.lineup_value, t.bench_value, t.weakest_slot, t.weakest_margin, t.weakest_sleeper_player_id,
           t.empty_slots, t.n_unvalued, t.n_locked, t.n_questionable, t.slots_total, t.slots_filled
    from weeks as w
    join {{ source('ops', 'lineup_totals') }} as t
      on t.league_id = w.league_id and t.season = w.season and t.week = w.week and t.roster_id = w.roster_id
     and not t.is_realised
),

horizon as (
    select league_id, season, roster_id,
           round(sum(lineup_value)::numeric, 2)                                         as horizon_value,
           count(*)                                                                     as horizon_lineups,
           (array_agg(week order by lineup_value, week))[1]                             as worst_week,
           (array_agg(lineup_value order by lineup_value, week))[1]                     as worst_week_value
    from tot group by 1, 2, 3
),

weakest as (
    select league_id, season, roster_id, week, slot, player_name, gsis_id, position, player_value,
           replacement_name, replacement_value, replacement_sleeper_player_id
    from h
    where is_this_week and role = 'starter'
)

select
    t.league_id,
    t.season,
    t.roster_id,
    t.team_name,
    t.manager_name,
    t.this_week                                              as week,
    t.horizon_first_week,
    t.horizon_last_week,
    t.horizon_weeks,
    'week ' || t.this_week                                   as week_label,
    case when t.horizon_first_week = t.horizon_last_week then 'week ' || t.horizon_first_week
         else 'weeks ' || t.horizon_first_week || '–' || t.horizon_last_week end as horizon_label,
    t.lineup_value,
    t.bench_value,
    t.slots_total,
    t.slots_filled,
    t.empty_slots,
    t.n_unvalued,
    t.n_locked,
    t.n_questionable,
    t.weakest_slot,
    t.weakest_margin,
    w.player_name                                            as weakest_player_name,
    w.gsis_id                                                as weakest_gsis_id,
    w.position                                               as weakest_position,
    w.player_value                                           as weakest_value,
    w.replacement_name                                       as weakest_replacement_name,
    w.replacement_value                                      as weakest_replacement_value,
    h.horizon_value::double precision                        as horizon_value,
    h.horizon_lineups,
    h.worst_week,
    h.worst_week_value
from tot as t
join horizon as h using (league_id, season, roster_id)
left join weakest as w
       on w.league_id = t.league_id and w.season = t.season and w.roster_id = t.roster_id and w.slot = t.weakest_slot
where t.week = t.this_week
