-- Plan B5 (decision record): the freeze labels in ops.projections are honest.
-- * a row kept as "the board shown before kickoff" (frozen_source = 'kickoff') says when that board
--   was published (frozen_at, equal to its fitted_at) and that moment precedes the week's first
--   kickoff (dim_game.kickoff_at over every game of the season-week; kickoff times are available for
--   every scheduled game, so the test does not fall back to run times);
-- * a row labelled 'refit' (locked after the week had started: 2026 weeks 1-3) carries no frozen_at;
-- * a row written after its week's first kickoff is never left live (unlabelled);
-- * one label per league-week, and no other label value.
-- A row here is a violation.
with kickoff as (
    select season, week, min(kickoff_at) as first_kickoff
    from {{ ref('dim_game') }}
    group by 1, 2
),

p as (
    select p.league_id, p.season, p.week, p.gsis_id, p.frozen_source, p.frozen_at, p.fitted_at, k.first_kickoff
    from {{ source('ops', 'projections') }} as p
    left join kickoff as k using (season, week)
),

mixed as (
    select league_id, season, week
    from p
    group by 1, 2, 3
    having count(distinct coalesce(frozen_source, '(live)')) > 1
)

select *, 'kickoff row without a pre-kickoff frozen_at' as problem
from p
where frozen_source = 'kickoff'
  and (frozen_at is null or first_kickoff is null or frozen_at >= first_kickoff or frozen_at is distinct from fitted_at)

union all

select *, 'refit row with a frozen_at' as problem
from p
where frozen_source = 'refit' and frozen_at is not null

union all

select *, 'unknown frozen_source' as problem
from p
where frozen_source not in ('kickoff', 'refit')

union all

select *, 'written after kickoff but still live' as problem
from p
where frozen_source is null and fitted_at >= first_kickoff

union all

select p.*, 'more than one label in a league-week' as problem
from p
join mixed using (league_id, season, week)
