-- Roster x position for current league-seasons: how strong each roster is at each position, using
-- season-to-date points per game of the players it currently rosters (top-N where N = starting
-- slots at that position, plus depth = the rest). Compared with the league median for trade fit.
with cur as (select league_id from {{ ref('dim_league_season') }} where is_current_season),

-- starter slots per position; a SUPER_FLEX slot is a second QB start in practice, so it counts
-- toward QB (the flex slots are not attributed: the "starters" are the top-N at each position)
slots as (
    select ls.league_id, case rp.slot when 'SUPER_FLEX' then 'QB' else rp.slot end as position, count(*) as n
    from {{ ref('dim_league_season') }} as ls
    cross join lateral jsonb_array_elements_text(ls.roster_positions) as rp(slot)
    where rp.slot in ('QB', 'RB', 'WR', 'TE', 'K', 'SUPER_FLEX')
    group by 1, 2
),

players as (
    select a.league_id, a.rostered_by_roster_id as roster_id, a.rostered_by_team as team_name, a.position, a.player_name,
           coalesce(a.ppg_std, 0) as ppg, coalesce(a.points_per_game_l3, a.ppg_std, 0) as ppg_l3, a.is_on_ir,
           row_number() over (partition by a.league_id, a.rostered_by_roster_id, a.position order by a.ppg_std desc nulls last) as rn
    from {{ ref('mart_player_availability') }} as a
    where a.rostered_by_roster_id is not null and a.league_id in (select league_id from cur)
),

agg as (
    select p.league_id, p.roster_id, p.team_name, p.position,
           count(*) as players,
           round(sum(ppg) filter (where rn <= coalesce(s.n, 1)), 2) as starter_ppg,
           round(avg(ppg) filter (where rn <= coalesce(s.n, 1)), 2) as starter_avg_ppg,
           round(sum(ppg) filter (where rn > coalesce(s.n, 1)), 2) as bench_ppg,
           round(max(ppg) filter (where rn > coalesce(s.n, 1)), 2) as best_bench_ppg,
           string_agg(player_name || ' (' || ppg || ')', ', ' order by rn) filter (where rn <= coalesce(s.n, 1) + 2) as top_players
    from players as p
    left join slots as s on s.league_id = p.league_id and s.position = p.position
    group by 1, 2, 3, 4
)

select
    a.*,
    round((percentile_cont(0.5) within group (order by a2.starter_ppg))::numeric, 2) as league_median_starter_ppg,
    round((a.starter_ppg - percentile_cont(0.5) within group (order by a2.starter_ppg))::numeric, 2) as starter_ppg_vs_median,
    rank() over (partition by a.league_id, a.position order by a.starter_ppg desc) as position_rank
from agg as a
join agg as a2 on a2.league_id = a.league_id and a2.position = a.position
group by a.league_id, a.roster_id, a.team_name, a.position, a.players, a.starter_ppg, a.starter_avg_ppg, a.bench_ppg, a.best_bench_ppg, a.top_players
