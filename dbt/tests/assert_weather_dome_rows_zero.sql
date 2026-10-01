-- Plan D3: a dome (or a closed / undecided retractable roof) keeps the weather out: every weather
-- feature is 0, and a 0 dome flag never hides behind a dome source.
select gsis_id, season, week, 'dome row with a non-zero weather feature' as problem
from {{ ref('int_player_week_weather') }}
where wx_dome = 1
  and (wx_wind_mph is distinct from 0 or wx_gust_mph is distinct from 0 or wx_precip_in is distinct from 0
       or wx_temp_f is distinct from 0 or wx_cold is distinct from 0 or wx_windy is distinct from 0
       or wx_snow is distinct from 0 or wx_source <> 'dome')
union all
select gsis_id, season, week, 'open-air row labelled dome'
from {{ ref('int_player_week_weather') }}
where wx_dome = 0 and wx_source = 'dome'
