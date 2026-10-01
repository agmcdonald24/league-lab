-- A week-N feature row may only use games before week N (T-11). asof_week must be < week, the
-- opponent's as-of games must be < week, and week-1 rows must carry no in-season form.
-- v3 (plan D5): the personnel inputs too - their as-of marker pn_asof_week < week, and in week 1 the teammate
-- inputs (built from this season's games) are NULL. The QB inputs may be set in week 1 (last season's games and
-- the published projected starter); dbt/tests/assert_personnel_is_asof.sql checks they read no game of the week.
select gsis_id, season, week, asof_week, 'as-of game not before the week' as problem
from {{ ref('mart_player_week_features') }} where asof_week >= week
union all
select gsis_id, season, week, asof_week, 'week 1 with in-season form'
from {{ ref('mart_player_week_features') }} where week = 1 and (asof_week is not null or ppg_std is not null or opp_allowed_std is not null)
union all
select gsis_id, season, week, pn_asof_week, 'personnel input from a game not before the week'
from {{ ref('mart_player_week_features') }} where pn_asof_week >= week
union all
select gsis_id, season, week, pn_asof_week, 'week 1 with in-season teammate inputs'
from {{ ref('mart_player_week_features') }}
where week = 1 and (pn_top_target_out is not null or pn_top_rusher_out is not null or pn_teammate_share_out is not null
                    or pn_absence_beneficiary is not null)
