-- A week-N feature row may only use games before week N (T-11). asof_week must be < week, the
-- opponent's as-of games must be < week, and week-1 rows must carry no in-season form.
select gsis_id, season, week, asof_week, 'as-of game not before the week' as problem
from {{ ref('mart_player_week_features') }} where asof_week >= week
union all
select gsis_id, season, week, asof_week, 'week 1 with in-season form'
from {{ ref('mart_player_week_features') }} where week = 1 and (asof_week is not null or ppg_std is not null or opp_allowed_std is not null)
