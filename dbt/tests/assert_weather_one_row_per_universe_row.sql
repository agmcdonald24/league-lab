-- Plan D3, the feature-table contract: exactly one int_player_week_weather row per
-- int_player_week_universe row (the harness joins feature tables on the grain).
with u as (select count(*) as n from {{ ref('int_player_week_universe') }}),
     w as (select count(*) as n from {{ ref('int_player_week_weather') }})
select u.n as universe_rows, w.n as weather_rows from u, w where u.n <> w.n
