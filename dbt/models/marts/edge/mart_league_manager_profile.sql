-- One row per league-season-roster: how each manager plays. Transaction volume and FAAB, lineup
-- discipline (bench points left), schedule luck, and a rough roster-construction fingerprint.
with tx as (
    select league_id, roster_id,
           count(distinct transaction_id) filter (where transaction_type = 'waiver' and status = 'complete' and action = 'add') as waiver_adds,
           count(distinct transaction_id) filter (where transaction_type = 'free_agent' and status = 'complete' and action = 'add') as free_agent_adds,
           count(distinct transaction_id) filter (where transaction_type = 'trade' and status = 'complete') as trades,
           count(distinct transaction_id) filter (where transaction_type = 'waiver' and status <> 'complete') as failed_waiver_claims,
           coalesce(sum(waiver_bid) filter (where transaction_type = 'waiver' and status = 'complete' and action = 'add'), 0) as faab_spent,
           count(*) filter (where action = 'add' and status = 'complete' and position = 'K') as kicker_adds,
           count(*) filter (where action = 'add' and status = 'complete' and position = 'DEF') as defense_adds
    from {{ ref('mart_league_transactions') }}
    group by 1, 2
),

lineup as (
    select league_id, roster_id,
           round(avg(bench_points_left), 2) as avg_bench_points_left,
           round(sum(bench_points_left), 2) as total_bench_points_left,
           round(avg(lineup_efficiency), 4) as avg_lineup_efficiency,
           count(*) filter (where bench_points_left >= 10) as weeks_left_10_plus
    from {{ ref('mart_league_optimal_lineup') }}
    group by 1, 2
),

roster_mix as (
    select league_id, roster_id,
           count(*) filter (where position = 'QB') as n_qb, count(*) filter (where position = 'RB') as n_rb,
           count(*) filter (where position = 'WR') as n_wr, count(*) filter (where position = 'TE') as n_te,
           count(*) filter (where position = 'K') as n_k, count(*) filter (where position = 'DEF') as n_def,
           count(*) filter (where is_on_ir) as n_ir
    from {{ ref('mart_league_roster_membership') }}
    group by 1, 2
)

select
    m.league_id, m.season, m.roster_id, m.team_name, m.manager_name, m.is_commissioner,
    ap.wins, ap.losses, ap.all_play_win_pct, ap.expected_wins, ap.luck_wins, ap.all_play_rank,
    st.points_for, st.points_against, st.standing,
    lu.avg_bench_points_left, lu.total_bench_points_left, lu.avg_lineup_efficiency, lu.weeks_left_10_plus,
    coalesce(tx.waiver_adds, 0) as waiver_adds, coalesce(tx.free_agent_adds, 0) as free_agent_adds,
    coalesce(tx.trades, 0) as trades, coalesce(tx.failed_waiver_claims, 0) as failed_waiver_claims,
    coalesce(tx.faab_spent, 0) as faab_spent, m.waiver_budget_used as sleeper_waiver_budget_used,
    coalesce(tx.kicker_adds, 0) as kicker_adds, coalesce(tx.defense_adds, 0) as defense_adds,
    rm.n_qb, rm.n_rb, rm.n_wr, rm.n_te, rm.n_k, rm.n_def, rm.n_ir
from {{ ref('dim_league_member') }} as m
left join {{ ref('mart_league_all_play') }} as ap using (league_id, roster_id)
left join {{ ref('mart_league_standings') }} as st using (league_id, roster_id)
left join lineup as lu using (league_id, roster_id)
left join tx using (league_id, roster_id)
left join roster_mix as rm using (league_id, roster_id)
