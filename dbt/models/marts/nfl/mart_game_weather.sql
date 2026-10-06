{{ config(indexes=[{'columns': ['game_id'], 'unique': True}, {'columns': ['season', 'week']}], post_hook="analyze {{ this }}") }}
-- Wave I-O (IO-1): the game-day weather the site may show (DFS's game-environment chip), one row per regular-season
-- or playoff game of the current season and the one before. A thin publication of int_game_weather (plan D3; its
-- header says which value a game gets: a played game what was observed, an upcoming game its newest forecast, a dome
-- 0s) with the teams and when the forecast was fetched. NOT an input of the projection: projection v3 reads no wx_
-- column (league_lab.dfs.SIGNAL_INPUTS['weather'] is asserted against projections.FEATURES_BY_POSITION).
-- ~570 rows, well under 0.2 MB.
with w as (
    select * from {{ ref('int_game_weather') }}
    where season >= (select max(season) from {{ ref('int_game_weather') }}) - 1
)

select
    w.game_id, w.season, w.season_type, w.week, w.kickoff_at, w.is_final,
    g.home_team, g.away_team,
    w.stadium_id, w.roof_type, w.roof, w.roof_assumed_closed,
    w.wx_dome, w.wx_source,
    w.wx_temp_f, w.wx_wind_mph, w.wx_gust_mph, w.wx_precip_in, w.wx_snow, w.wx_cold, w.wx_windy,
    w.wx_known_at,
    case when w.wx_source = 'forecast' then w.wx_known_at end                    as forecast_at,
    w.wx_forecast_hours_ahead                                                    as forecast_hours_ahead,
    w.forecast_wind_mph, w.forecast_temp_f, w.forecast_precip_in
from w
left join {{ ref('dim_game') }} as g on g.game_id = w.game_id
