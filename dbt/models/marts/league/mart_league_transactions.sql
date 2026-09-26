-- Flattened transactions: one row per player moved, with names and the manager involved.
select
    tp.league_id,
    l.season,
    tp.week,
    tp.transaction_id,
    tp.transaction_type,
    tp.status,
    t.created_at,
    tp.action,
    tp.roster_id,
    m.team_name,
    m.manager_name,
    tp.sleeper_player_id,
    coalesce(p.full_name, tp.sleeper_player_id) as player_name,
    p.position,
    t.waiver_bid,
    t.notes
from {{ ref('stg_sleeper__transaction_players') }} as tp
join {{ ref('stg_sleeper__transactions') }} as t using (league_id, transaction_id)
join {{ ref('dim_league_season') }} as l using (league_id)
left join {{ ref('stg_sleeper__players') }} as p using (sleeper_player_id)
left join {{ ref('dim_league_member') }} as m on m.league_id = tp.league_id and m.roster_id = tp.roster_id
