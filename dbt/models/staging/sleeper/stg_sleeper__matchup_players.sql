-- One row per league-week-roster-player with observed Sleeper points and lineup slot.
-- Slot index comes from the position of the player in the `starters` array; "0" marks an
-- empty slot and is excluded. Slot labels come from the league's roster_positions.
with matchups as (
    select * from {{ source('raw', 'sleeper_matchup') }}
),

leagues as (
    select league_id, payload -> 'roster_positions' as roster_positions
    from {{ source('raw', 'sleeper_league') }}
),

players as (
    select
        m.league_id,
        m.week,
        m.roster_id,
        m.matchup_id,
        kv.key                          as sleeper_player_id,
        kv.value::numeric               as points,
        array_position(m.starters, kv.key) as slot_index
    from matchups as m
    cross join lateral jsonb_each_text(coalesce(m.players_points, '{}'::jsonb)) as kv
    where kv.key <> '0'
)

select
    p.league_id,
    p.week,
    p.roster_id,
    p.matchup_id,
    p.sleeper_player_id,
    p.points,
    p.slot_index is not null            as is_starter,
    p.slot_index,
    case when p.slot_index is not null
         then l.roster_positions ->> (p.slot_index - 1) end as slot
from players as p
left join leagues as l using (league_id)
