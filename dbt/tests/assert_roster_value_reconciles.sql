-- depends_on: {{ ref('mart_lineup_recommendation') }}
-- Plan B2: the roster views add up. For every current roster and every week of the horizon, the starters'
-- values in mart_league_roster_horizon sum to that week's lineup value (ops.lineup_totals, to the cent);
-- the 4-week horizon value is the sum of those lineup values; every current roster has a roster-value row
-- and is ranked on all three measures (lineup value, 4-week horizon, depth).
{{ config(severity='error') }}
with starters as (
    select league_id, season, roster_id, week, round(sum(player_value)::numeric, 2) as starters_value
    from {{ ref('mart_league_roster_horizon') }}
    where role = 'starter'
    group by 1, 2, 3, 4
),

weekly as (
    select s.*, t.lineup_value
    from starters as s
    join {{ source('ops', 'lineup_totals') }} as t
      on t.league_id = s.league_id and t.season = s.season and t.roster_id = s.roster_id and t.week = s.week and not t.is_realised
),

bad_week as (
    select league_id, roster_id, week, 'starters sum ' || starters_value || ' <> lineup ' || lineup_value as problem
    from weekly where abs(starters_value - lineup_value::numeric) > 0.005
),

bad_horizon as (
    select v.league_id, v.roster_id, v.week, 'horizon ' || v.horizon_value || ' <> sum ' || sum(w.lineup_value) as problem
    from {{ ref('mart_league_roster_value') }} as v
    join weekly as w on w.league_id = v.league_id and w.roster_id = v.roster_id
    group by v.league_id, v.roster_id, v.week, v.horizon_value
    having abs(v.horizon_value - round(sum(w.lineup_value)::numeric, 2)) > 0.005
),

members as (
    select m.league_id, m.roster_id
    from {{ ref('dim_league_member') }} as m
    join {{ ref('dim_league_season') }} as l on l.league_id = m.league_id and l.is_current_season
    -- only once the season has a week ahead (after the last kickoff there is no "this week")
    where exists (select 1 from {{ ref('mart_league_roster_value') }} as v where v.league_id = m.league_id)
),

missing as (
    select m.league_id, m.roster_id, null::integer as week, 'no roster value row' as problem
    from members as m
    left join {{ ref('mart_league_roster_value') }} as v using (league_id, roster_id)
    where v.roster_id is null
    union all
    select m.league_id, m.roster_id, null, 'not ranked on ' || x.measure
    from members as m
    cross join (values ('lineup_value'), ('horizon_value'), ('bench_value')) as x(measure)
    left join {{ ref('mart_league_roster_rankings') }} as r
           on r.league_id = m.league_id and r.roster_id = m.roster_id and r.measure = x.measure
    where r.roster_id is null
)

select * from bad_week
union all select * from bad_horizon
union all select * from missing
