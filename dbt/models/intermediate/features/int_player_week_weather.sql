{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- Plan D3 feature group `weather` (sub-groups `wind`, `temp`, `dome`): the game-day weather of the
-- player's game, at the feature-table contract grain (one row per int_player_week_universe row).
-- Every value is the game's (int_game_weather): known before kickoff for the live board (a forecast),
-- observed after the game for training and the backtest (Open-Meteo archive, else the schedules'
-- temp / wind) — the documented train / serve gap (docs/METRICS.md § Weather). NULL = unknown.
select
    u.gsis_id, u.season, u.week,
    w.wx_dome, w.wx_wind_mph, w.wx_gust_mph, w.wx_precip_in, w.wx_temp_f, w.wx_cold, w.wx_windy, w.wx_snow,
    coalesce(w.wx_source, 'none') as wx_source
from {{ ref('int_player_week_universe') }} as u
left join {{ ref('int_game_weather') }} as w on w.game_id = u.game_id
