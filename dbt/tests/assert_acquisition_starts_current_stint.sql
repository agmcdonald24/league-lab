-- Plan B2: the acquisition shown for a rostered player is the move that began his CURRENT stint on the
-- roster: no completed transaction after it took him off this roster (a drop from it, or an add to
-- another roster) within the history that counts (the chain for a dynasty, this season otherwise).
-- A row here means the stint logic or the Sleeper history is inconsistent.
{{ config(severity='error') }}
with ls as (
    select league_id, chain_id, season from {{ ref('dim_league_season') }}
),

moves_off as (
    select ls.chain_id, ls.season, coalesce(t.status_updated_at, t.created_at) as at, kv.key as sleeper_player_id,
           kv.value::integer as roster_id, 'drop' as kind
    from {{ ref('stg_sleeper__transactions') }} as t
    join ls using (league_id)
    cross join lateral jsonb_each_text(coalesce(t.drops, '{}'::jsonb)) as kv
    where t.status = 'complete'
    union all
    select ls.chain_id, ls.season, coalesce(t.status_updated_at, t.created_at), kv.key, kv.value::integer, 'add elsewhere'
    from {{ ref('stg_sleeper__transactions') }} as t
    join ls using (league_id)
    cross join lateral jsonb_each_text(coalesce(t.adds, '{}'::jsonb)) as kv
    where t.status = 'complete'
)

select a.league_id, a.roster_id, a.player_name, a.acquired_label, a.acquired_at, o.at as later_move_at, o.kind, o.roster_id as move_roster_id
from {{ ref('mart_league_acquisitions') }} as a
join {{ ref('dim_league_season') }} as cur on cur.league_id = a.league_id
join moves_off as o
  on o.chain_id = cur.chain_id and o.sleeper_player_id = a.sleeper_player_id and o.at > a.acquired_at
 and (cur.league_type = 'dynasty' or o.season = cur.season)
 and ((o.kind = 'drop' and o.roster_id = a.roster_id) or (o.kind = 'add elsewhere' and o.roster_id <> a.roster_id))
