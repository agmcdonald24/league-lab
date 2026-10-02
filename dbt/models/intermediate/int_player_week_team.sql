{{ config(post_hook="analyze {{ this }}") }}
-- Wave H (H2): int_player_week_universe planned on this table before autovacuum analysed it (396 s of an 8 min build)
-- Historical team affiliation per player-week from weekly rosters, deduplicated to one row per
-- (gsis_id, season, week). nflverse occasionally emits two rows for one id in a week (e.g. a
-- 2019 id collision between two players); we keep the row whose name matches the nflverse
-- player record, then prefer active status. Dropped rows are listed in player_id_quarantine.
with rw as (
    select r.*,
           row_number() over (
               partition by r.gsis_id, r.season, r.week
               order by (r.full_name = p.display_name) desc nulls last,
                        (r.roster_status = 'ACT') desc,
                        r.team
           ) as rn
    from {{ ref('stg_nflverse__rosters_weekly') }} as r
    left join {{ ref('stg_nflverse__players') }} as p using (gsis_id)
)

select
    gsis_id,
    season,
    week,
    season_type,
    game_type,
    team,
    position,
    depth_chart_position,
    roster_status,
    roster_status_detail,
    full_name
from rw
where rn = 1
