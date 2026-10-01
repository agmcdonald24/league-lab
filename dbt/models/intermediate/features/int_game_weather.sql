{{ config(indexes=[{'columns': ['game_id'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- Plan D3: one row per NFL game (seasons_start on, regular season and playoffs) with the venue it was
-- really played at and the game-day weather a projection may use (the `wx_` columns that
-- int_player_week_weather broadcasts to player-weeks).
--
-- Venue: a per-game correction (raw.nfl_stadium_game_venues: nflverse records several international
-- games at the home team's stadium), then a stadium name that belongs to another venue (2026_05_PHI_JAX:
-- JAX00 "Tottenham Hotspur Stadium"), then the recorded stadium_id. The Python twin is
-- league_lab.ingest.weather.resolve_venue (same order).
--
-- Roof: the venue's roof from the reference decides fixed domes and open-air stadiums (nflverse calls the
-- MCG, Stade de France and the Munich stadium 'dome'); a retractable roof is closed unless the schedules
-- say open. An undecided retractable roof (every upcoming game: nflverse fills `roof` on game day) counts
-- as closed: 370 of 418 retractable-roof games 2016-2025 were played closed (89%).
--
-- Weather, in this order (the first that exists):
--   played game:   'archive' (Open-Meteo ERA5 at the stadium, kickoff hour and the two after)
--                  > 'nflverse_observed' (schedules temp / wind, filled after the game; no gust, no rain)
--                  > 'forecast' (the last one fetched before kickoff)
--   upcoming game: 'forecast' (the newest one; every one is fetched before kickoff)
--   otherwise 'none' (values NULL = unknown); 'dome' when the roof keeps the weather out (values 0).
-- Training therefore sees observed weather and the live board a forecast: the train / serve gap of
-- docs/METRICS.md § Weather. Every forecast stays in raw.nfl_weather to measure it.
with games as (
    select game_id, season, season_type, week, kickoff_at, is_final, nullif(roof, '') as roof,
           stadium_id as recorded_stadium_id, stadium as recorded_stadium, temp, wind, source_fetched_at
    from {{ ref('stg_nflverse__games') }}
),

stadiums as (
    select stadium_id, names, roof_type, timezone, latitude, longitude from {{ source('raw', 'nfl_stadiums') }}
),

venue as (
    select g.game_id,
           coalesce(o.stadium_id, n.stadium_id, i.stadium_id)               as stadium_id,
           case when o.stadium_id is not null then 'game_override'
                when n.stadium_id is not null then 'stadium_name'
                when i.stadium_id is not null then 'stadium_id'
                else 'unresolved' end                                        as venue_resolved_by
    from games as g
    left join {{ source('raw', 'nfl_stadium_game_venues') }} as o on o.game_id = g.game_id
    left join stadiums as n on g.recorded_stadium = any(n.names) and n.stadium_id <> g.recorded_stadium_id
    left join stadiums as i on i.stadium_id = g.recorded_stadium_id
),

archive as (
    select distinct on (game_id) game_id, fetched_at, wind_mph, gust_mph, precip_in, snow, temp_f, n_hours
    from {{ source('raw', 'nfl_weather') }}
    where source = 'archive' and n_hours > 0
    order by game_id, fetched_at desc
),

forecast as (
    select distinct on (game_id) game_id, fetched_at, forecast_hours_ahead, wind_mph, gust_mph, precip_in, snow, temp_f
    from {{ source('raw', 'nfl_weather') }}
    where source = 'forecast' and fetched_at < kickoff_at and n_hours > 0
    order by game_id, fetched_at desc
),

decided as (
    select g.*, v.stadium_id, v.venue_resolved_by, s.roof_type, s.timezone,
           case when s.stadium_id is null then null
                when s.roof_type = 'dome' then 1
                when s.roof_type = 'retractable' and coalesce(lower(g.roof), 'undecided') not in ('open', 'outdoors') then 1
                else 0 end                                                   as dome,
           s.roof_type = 'retractable' and g.roof is null                    as roof_assumed_closed
    from games as g
    join venue as v using (game_id)
    left join stadiums as s on s.stadium_id = v.stadium_id
),

sourced as (
    select d.*,
           case when d.dome = 1 then 'dome'
                when d.is_final and a.game_id is not null then 'archive'
                when d.is_final and (d.wind is not null or d.temp is not null) then 'nflverse_observed'
                when f.game_id is not null then 'forecast'
                else 'none' end                                              as wx_source,
           a.fetched_at as a_at, a.wind_mph as a_wind, a.gust_mph as a_gust, a.precip_in as a_precip, a.snow as a_snow, a.temp_f as a_temp,
           f.fetched_at as f_at, f.forecast_hours_ahead as f_ahead, f.wind_mph as f_wind, f.gust_mph as f_gust,
           f.precip_in as f_precip, f.snow as f_snow, f.temp_f as f_temp
    from decided as d
    left join archive as a using (game_id)
    left join forecast as f using (game_id)
),

valued as (
    select *,
           case wx_source when 'dome' then 0 when 'archive' then a_wind when 'nflverse_observed' then wind::double precision
                          when 'forecast' then f_wind end                    as wind_v,
           case wx_source when 'dome' then 0 when 'archive' then a_gust when 'forecast' then f_gust end as gust_v,
           case wx_source when 'dome' then 0 when 'archive' then a_precip when 'forecast' then f_precip end as precip_v,
           case wx_source when 'dome' then 0 when 'archive' then a_temp when 'nflverse_observed' then temp::double precision
                          when 'forecast' then f_temp end                    as temp_v,
           case wx_source when 'dome' then false when 'archive' then a_snow when 'forecast' then f_snow end as snow_v,
           case wx_source when 'archive' then a_at when 'nflverse_observed' then source_fetched_at
                          when 'forecast' then f_at end                      as known_at
    from sourced
)

select
    game_id, season, season_type, week, kickoff_at, is_final,
    stadium_id, venue_resolved_by, recorded_stadium_id, roof_type, roof, roof_assumed_closed, timezone,
    dome                                                                     as wx_dome,
    round(wind_v::numeric, 2)                                                as wx_wind_mph,
    round(gust_v::numeric, 2)                                                as wx_gust_mph,
    round(precip_v::numeric, 3)                                              as wx_precip_in,
    round(temp_v::numeric, 2)                                                as wx_temp_f,
    case when dome = 1 then 0 when temp_v is null then null when temp_v < 32 then 1 else 0 end   as wx_cold,
    case when dome = 1 then 0 when wind_v is null then null when wind_v >= 15 then 1 else 0 end  as wx_windy,
    case when snow_v is null then null when snow_v then 1 else 0 end         as wx_snow,
    wx_source,
    known_at                                                                 as wx_known_at,
    case when wx_source = 'forecast' then f_ahead end                        as wx_forecast_hours_ahead,
    -- what each source says, side by side (the train / serve comparison reads these)
    a_wind as archive_wind_mph, a_temp as archive_temp_f, a_precip as archive_precip_in,
    wind as nflverse_wind_mph, temp as nflverse_temp_f,
    f_wind as forecast_wind_mph, f_temp as forecast_temp_f, f_precip as forecast_precip_in, f_ahead as forecast_hours_ahead
from valued
