-- Plan R-14: in the current season coverage snaps are estimated (his share of the defense's snaps x the
-- opponent's dropbacks) because participation arrives after the postseason. On the latest season that has
-- both, the estimate must track the play-level count for cornerbacks: total within 5% and an average miss
-- under 3 snaps a game (2025: ratio 0.973, 1.64 snaps). Warn only: it guards a modelling assumption.
{{ config(severity='warn') }}
with latest as (
    select max(season) as season
    from {{ ref('int_defender_game_coverage_snaps') }}
    where coverage_snaps_source = 'participation'
),

pairs as (
    select c.coverage_snaps_on_field as actual, c.coverage_snaps_estimated as estimate
    from {{ ref('int_defender_game_coverage_snaps') }} as c
    where c.season = (select season from latest) and c.season_type = 'REG' and c.position = 'CB'
      and c.coverage_snaps_on_field is not null and c.coverage_snaps_estimated is not null
)

select count(*) as n, sum(estimate) / nullif(sum(actual), 0) as ratio, avg(abs(estimate - actual)) as mae
from pairs
having count(*) = 0 or abs(sum(estimate) / nullif(sum(actual), 0) - 1) > 0.05 or avg(abs(estimate - actual)) >= 3
