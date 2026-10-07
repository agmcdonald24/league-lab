-- IQ-1 (hotfix, 2026-10-07; docs/METRICS.md § "v3.5: rest-of-season quarterbacks"): the guard that would have caught the
-- re-ordered rest-of-season list. For the newest season on the board, the reference league: among the top 24 at each
-- position by the market-week projection (the first week still live: no frozen rows), the rank correlation between that
-- projection and the player's mean over the later live weeks. A row per position below its floor. The floors come from
-- the horizon study (`iq1_horizon.py stability`: 2021-2025 as of weeks 3 / 5 / 7 / 9, 20 cells a position): with v3.5's
-- inputs QB mean 0.79, lowest 0.59 (v3.4's: 0.67, lowest 0.44); RB / WR / TE lowest 0.69 / 0.79 / 0.77. Floors below
-- every v3.5 cell: QB 0.55, the others 0.65. A warning, never a stop for the nightly.
{{ config(severity='warn') }}
with ref as (
    select league_id from {{ ref('dim_league_season') }} where is_reference_league and is_current_season
),

board as (
    select p.season, p.week, p.position, p.gsis_id, p.proj_points
    from {{ source('ops', 'projections') }} as p
    join ref using (league_id)
    where p.position in ('QB', 'RB', 'WR', 'TE')
      and p.season = (select max(season) from {{ source('ops', 'projections') }})
),

market as (
    select min(week) as week from board
    where week not in (select week from {{ source('ops', 'projections') }} where frozen_source is not null
                       and season = (select max(season) from board))
),

mk as (
    select b.position, b.gsis_id, b.proj_points,
           row_number() over (partition by b.position order by b.proj_points desc, b.gsis_id) as rk
    from board as b join market as m on b.week = m.week
),

later as (
    select b.position, b.gsis_id, avg(b.proj_points) as later_mean
    from board as b join market as m on b.week > m.week
    group by 1, 2
),

top as (
    select mk.position, mk.proj_points, l.later_mean
    from mk join later as l using (position, gsis_id)
    where mk.rk <= 24
),

ranked as (
    select position,
           rank() over (partition by position order by proj_points) as r_mk,
           rank() over (partition by position order by later_mean) as r_later
    from top
),

corr as (
    select position, count(*) as players, corr(r_mk, r_later) as rank_corr from ranked group by position
)

select position, players, round(rank_corr::numeric, 3) as rank_corr,
       case when position = 'QB' then {{ var('ros_corr_floor_qb', 0.55) }} else {{ var('ros_corr_floor', 0.65) }} end as floor
from corr
where players >= 12
  and rank_corr < case when position = 'QB' then {{ var('ros_corr_floor_qb', 0.55) }} else {{ var('ros_corr_floor', 0.65) }} end
