-- Per league-week-roster: the points the roster actually started vs the best lineup it could have
-- started from the players it rostered that week (Sleeper observed points), and the bench points
-- left on the table. Slot filling is greedy in this order: fixed slots (QB/RB/WR/TE/K/DEF) by
-- points, then REC_FLEX (WR/TE), WRRB_FLEX (RB/WR), FLEX (RB/WR/TE), SUPER_FLEX (QB/RB/WR/TE).
-- For fixed slots + a single flex type this greedy order is optimal.
with lpw as (
    select l.league_id, l.season, l.week, l.roster_id, l.sleeper_player_id, l.points_observed as points,
           l.is_starter, coalesce(l.position, 'UNK') as position
    from {{ ref('league_player_week') }} as l
    where l.is_scored_week
),

slots as (
    select ls.league_id, rp.slot, count(*) as n
    from {{ ref('dim_league_season') }} as ls
    cross join lateral jsonb_array_elements_text(ls.roster_positions) as rp(slot)
    where rp.slot <> 'BN'
    group by 1, 2
),

fixed as (
    select p.*,
           row_number() over (partition by p.league_id, p.week, p.roster_id, p.position order by p.points desc nulls last) as pos_rank,
           coalesce(s.n, 0) as pos_slots
    from lpw as p
    left join slots as s on s.league_id = p.league_id and s.slot = p.position
),

picked_fixed as (select *, 'fixed' as picked_as from fixed where pos_rank <= pos_slots),

rest1 as (select * from fixed where pos_rank > pos_slots),
rec_flex as (
    select r.*, row_number() over (partition by r.league_id, r.week, r.roster_id order by r.points desc nulls last) as rn,
           coalesce(s.n, 0) as n
    from rest1 as r left join slots as s on s.league_id = r.league_id and s.slot = 'REC_FLEX'
    where r.position in ('WR', 'TE')
),
picked_rec as (select *, 'REC_FLEX' as picked_as from rec_flex where rn <= n),

rest2 as (
    select r.* from rest1 as r
    where not exists (select 1 from picked_rec p where p.league_id = r.league_id and p.week = r.week and p.roster_id = r.roster_id and p.sleeper_player_id = r.sleeper_player_id)
),
wrrb_flex as (
    select r.*, row_number() over (partition by r.league_id, r.week, r.roster_id order by r.points desc nulls last) as rn,
           coalesce(s.n, 0) as n
    from rest2 as r left join slots as s on s.league_id = r.league_id and s.slot = 'WRRB_FLEX'
    where r.position in ('RB', 'WR')
),
picked_wrrb as (select *, 'WRRB_FLEX' as picked_as from wrrb_flex where rn <= n),

rest3 as (
    select r.* from rest2 as r
    where not exists (select 1 from picked_wrrb p where p.league_id = r.league_id and p.week = r.week and p.roster_id = r.roster_id and p.sleeper_player_id = r.sleeper_player_id)
),
flex as (
    select r.*, row_number() over (partition by r.league_id, r.week, r.roster_id order by r.points desc nulls last) as rn,
           coalesce(s.n, 0) as n
    from rest3 as r left join slots as s on s.league_id = r.league_id and s.slot = 'FLEX'
    where r.position in ('RB', 'WR', 'TE')
),
picked_flex as (select *, 'FLEX' as picked_as from flex where rn <= n),

rest4 as (
    select r.* from rest3 as r
    where not exists (select 1 from picked_flex p where p.league_id = r.league_id and p.week = r.week and p.roster_id = r.roster_id and p.sleeper_player_id = r.sleeper_player_id)
),
sflex as (
    select r.*, row_number() over (partition by r.league_id, r.week, r.roster_id order by r.points desc nulls last) as rn,
           coalesce(s.n, 0) as n
    from rest4 as r left join slots as s on s.league_id = r.league_id and s.slot = 'SUPER_FLEX'
    where r.position in ('QB', 'RB', 'WR', 'TE')
),
picked_sflex as (select *, 'SUPER_FLEX' as picked_as from sflex where rn <= n),

optimal as (
    select league_id, season, week, roster_id, sleeper_player_id, points, picked_as from picked_fixed
    union all select league_id, season, week, roster_id, sleeper_player_id, points, picked_as from picked_rec
    union all select league_id, season, week, roster_id, sleeper_player_id, points, picked_as from picked_wrrb
    union all select league_id, season, week, roster_id, sleeper_player_id, points, picked_as from picked_flex
    union all select league_id, season, week, roster_id, sleeper_player_id, points, picked_as from picked_sflex
),

agg as (
    select league_id, season, week, roster_id,
           round(sum(points) filter (where is_starter), 2) as points_started,
           count(*) filter (where is_starter) as starters_counted
    from lpw group by 1, 2, 3, 4
),

opt as (
    select league_id, season, week, roster_id, round(sum(points), 2) as points_optimal, count(*) as optimal_slots_filled
    from optimal group by 1, 2, 3, 4
)

select
    a.league_id, a.season, a.week, a.roster_id,
    m.team_name, m.manager_name,
    a.points_started, o.points_optimal,
    round(o.points_optimal - a.points_started, 2)                     as bench_points_left,
    case when o.points_optimal > 0 then round(a.points_started / o.points_optimal, 4) end as lineup_efficiency,
    a.starters_counted, o.optimal_slots_filled
from agg as a
join opt as o using (league_id, season, week, roster_id)
left join {{ ref('dim_league_member') }} as m using (league_id, roster_id)
