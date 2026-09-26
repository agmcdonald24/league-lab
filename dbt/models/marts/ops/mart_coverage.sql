-- Source-by-season coverage inventory (plan §7): which seasons each dataset covers, how far the
-- final-scored games reach, and explicit "not available" rows for deferred sources.
with games as (
    select season,
           max(game_date) filter (where is_final)            as through_game_date,
           max(week) filter (where is_final and season_type = 'REG') as through_reg_week,
           count(*) filter (where is_final)                  as final_games,
           count(*)                                          as scheduled_games
    from {{ ref('dim_game') }} group by 1
),

stats as (
    select season, count(distinct game_id) as games_with_player_stats, max(week) as max_week
    from {{ ref('fct_player_game') }} group by 1
),

snaps as (
    select season, count(distinct game_id) as games_with_snaps from {{ ref('int_player_game_snaps') }} group by 1
),

-- one row per season whatever the number of leagues configured (mart grain is the season)
league as (
    select season,
           count(*)                                              as leagues,
           string_agg(league_name || ' (' || league_id || ')', '; ' order by is_reference_league desc, league_name) as league_names,
           min(league_id) filter (where is_reference_league)    as league_id,
           max(last_scored_leg)                                  as league_scored_weeks,
           min(last_scored_leg)                                  as league_scored_weeks_min
    from {{ ref('dim_league_season') }}
    group by 1
),

pbp as (
    select season, count(distinct game_id) as games_with_pbp, count(*) as plays, max(week) as pbp_max_week
    from {{ ref('fct_play') }} group by 1
),

participation as (
    select season, count(distinct game_id) as games_with_participation from {{ ref('bridge_play_participation') }} group by 1
),

charting as (
    select season, count(distinct game_id) as games_with_charting, max(week) as charting_max_week,
           round(avg(charting_coverage), 3) as avg_charting_coverage
    from {{ ref('int_team_game_pbp') }} where charted_targets > 0 group by 1
),

routes as (
    select season, count(distinct provider) as route_providers, count(*) as route_rows from {{ ref('stg_routes_feed') }} group by 1
)

select
    g.season,
    g.scheduled_games, g.final_games, g.through_game_date, g.through_reg_week,
    s.games_with_player_stats, s.max_week as stats_max_week,
    sn.games_with_snaps,
    l.leagues, l.league_names, l.league_id, l.league_scored_weeks, l.league_scored_weeks_min,
    p.games_with_pbp, p.plays, p.pbp_max_week,
    pa.games_with_participation,
    c.games_with_charting, c.charting_max_week, c.avg_charting_coverage,
    case when p.games_with_pbp is null then 'not loaded'
         else format('%s games through week %s', p.games_with_pbp, p.pbp_max_week) end as play_by_play_status,
    case when g.season < 2022 then 'not published by source (FTN charting starts 2022)'
         when c.games_with_charting is null then 'not loaded'
         else format('%s games through week %s, %s%% of targets charted', c.games_with_charting, c.charting_max_week, round(100 * c.avg_charting_coverage, 1)) end as ftn_charting_status,
    case when pa.games_with_participation is null and g.final_games > 0 then 'not published yet (arrives after the postseason)'
         when pa.games_with_participation is null then 'not loaded'
         else format('%s games; routes proxy available', pa.games_with_participation) end as participation_status,
    case when r.route_rows is null then 'no licensed feed imported (league-lab import-routes)'
         else format('%s rows from %s provider(s)', r.route_rows, r.route_providers) end as routes_status
from games as g
left join stats as s using (season)
left join snaps as sn using (season)
left join league as l using (season)
left join pbp as p using (season)
left join participation as pa using (season)
left join charting as c using (season)
left join routes as r using (season)
order by g.season
