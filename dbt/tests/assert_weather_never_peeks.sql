-- Plan D3, the feature-table contract's as-of check for weather: no value may exist before it could
-- be known. An observation (Open-Meteo archive, the schedules' temp / wind) only for a game that was
-- played and kicked off before the observation was fetched; a forecast only when fetched before
-- kickoff; and a game that has not been played carries no observed value at all.
select game_id, kickoff_at, wx_source, wx_known_at, 'observation for a game not yet played' as problem
from {{ ref('int_game_weather') }}
where wx_source in ('archive', 'nflverse_observed') and not is_final
union all
select game_id, kickoff_at, wx_source, wx_known_at, 'observation known before kickoff'
from {{ ref('int_game_weather') }}
where wx_source in ('archive', 'nflverse_observed') and (wx_known_at is null or wx_known_at <= kickoff_at)
union all
select game_id, kickoff_at, wx_source, wx_known_at, 'forecast fetched after kickoff'
from {{ ref('int_game_weather') }}
where wx_source = 'forecast' and (wx_known_at is null or wx_known_at >= kickoff_at or wx_forecast_hours_ahead <= 0)
union all
select game_id, kickoff_at, source, fetched_at, 'raw forecast row fetched after kickoff'
from {{ source('raw', 'nfl_weather') }}
where source = 'forecast' and fetched_at >= kickoff_at
union all
select game_id, kickoff_at, source, fetched_at, 'raw archive row fetched before the game ended'
from {{ source('raw', 'nfl_weather') }}
where source = 'archive' and fetched_at < kickoff_at + interval '3 hours'
