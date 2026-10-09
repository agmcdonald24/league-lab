-- PO (Wave I-S, 2026-10-08): no stored waiver move adds a player who sits this week.
-- The waiver engine (src/league_lab/waivers.py, IS-2) leaves out every free agent availability_gate.sits() is true
-- for. This guard does not read the engine's blocks or the stored `availability` record (a guard must not read the
-- field it guards): it reads Sleeper's directory itself, and only the cases with no room for a date or source
-- disagreement — a reserve list (IR / PUP / NFI / suspended), or Out / Doubtful with news dated since the previous
-- week's last kickoff (an older game status was last week's: availability_gate.stale_game_status).
-- Severity by var, like assert_nobody_who_cannot_play_is_projected: a WARNING inside the nightly's builds (the full
-- build runs before `project`, on the moves the previous night stored — a status that changed overnight must not
-- stop the night), an ERROR in the nightly's soft availability step after `project` + projection-marts:
--   dbt test --select assert_waiver_adds_do_not_sit --vars '{availability_gate_severity: error}'
{{ config(severity=var('availability_gate_severity', 'warn')) }}
with m as (
    select * from {{ ref('mart_waiver_moves') }} where inputs_current and list_kind <> 'nothing'
),

prev_end as (
    select w.season, w.week, max(g.kickoff_at) as last_kickoff
    from (select distinct season, week from m) as w
    join {{ ref('dim_game') }} as g on g.season = w.season and g.week = w.week - 1 and g.season_type = 'REG'
    group by w.season, w.week
),

news as (
    select player_id, to_timestamp(nullif(payload ->> 'news_updated', '')::double precision / 1000.0) as news_at
    from {{ source('raw', 'sleeper_player') }}
    where (payload ->> 'news_updated') ~ '^[0-9]+$'
),

directory as (
    select p.sleeper_player_id as sleeper_id, max(upper(coalesce(p.injury_status, ''))) as code, max(n.news_at) as news_at
    from {{ ref('stg_sleeper__players') }} as p
    left join news as n on n.player_id = p.sleeper_player_id
    group by 1
)

select m.league_id, m.roster_id, m.season, m.week, m.add_sleeper_id, d.code, d.news_at, pe.last_kickoff
from m
join directory as d on d.sleeper_id = m.add_sleeper_id
left join prev_end as pe on pe.season = m.season and pe.week = m.week
where d.code in ('IR', 'PUP', 'NFI', 'SUS')
   or (d.code in ('OUT', 'DOUBTFUL') and d.news_at is not null and pe.last_kickoff is not null
       and d.news_at >= pe.last_kickoff)
