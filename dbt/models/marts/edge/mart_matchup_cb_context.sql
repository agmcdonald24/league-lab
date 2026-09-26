-- For each defense (current depth chart): the cornerbacks likely to see snaps (LCB/RCB/NB with
-- depth rank 1-2) and their season-to-date coverage stats. This is *context for a WR matchup*, not
-- a shadow-coverage assignment: public data does not say who covered whom.
with dc as (
    select * from {{ ref('int_depth_chart_current') }}
    where pos_abb in ('LCB', 'RCB', 'NB', 'CB', 'SCB') and pos_rank <= 2
),

cov as (
    select * from {{ ref('mart_defender_coverage_season') }}
    where season = (select max(season) from {{ ref('mart_defender_coverage_season') }})
)

select
    dc.team as defense, dc.season as depth_chart_season, dc.snapshot_at, dc.gsis_id, dc.player_name as defender_name,
    dc.pos_abb as depth_position, dc.pos_rank as depth_rank,
    cov.games, cov.targets, cov.targets_per_game, cov.completion_pct_allowed, cov.yards_allowed, cov.yards_per_target_allowed,
    cov.tds_allowed, cov.interceptions, cov.avg_passer_rating_allowed_when_targeted, cov.adot_allowed, cov.missed_tackles,
    cov.gsis_id is not null as coverage_known
from dc
left join cov using (gsis_id)
