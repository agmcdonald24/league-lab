{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- Plan D2 (Wave D): game context at the projection's grain, one row per int_player_week_universe row.
-- Everything comes from the published schedule (stg_nflverse__games = raw.nfl_schedules): weekday,
-- kickoff time, venue, roof type, surface, division, and each team's previous game date. Nothing from
-- the game itself (score, observed weather, the game-day open/closed call on a retractable roof).
-- `gametime` is Eastern time (nflverse); a flexed game carries its final, flexed time (nflverse rewrites
-- the schedule when the league flexes, at least 12 days ahead, 6 for week 18), a NULL gametime leaves the
-- kickoff columns NULL (never 13:00 by assumption). Time zones are hours relative to US Eastern (the
-- stadium map below; international venues at their in-season offset).
with games as (
    select game_id, season, week, game_date, weekday, kickoff_local_time as gametime, home_team, away_team,
           location, nullif(trim(lower(roof)), '') as roof, nullif(trim(lower(surface)), '') as surface,
           is_divisional, stadium_id
    from {{ ref('stg_nflverse__games') }}
    where game_type = 'REG' and season >= {{ var('seasons_start') }}
),

-- the week's Sunday: weekday is counted from it (Thursday -3, Saturday -1, Monday +1, a Christmas Wednesday -4)
week_sunday as (
    select season, week, min(game_date) filter (where weekday = 'Sunday') as sunday
    from games group by 1, 2
),

-- each team's games in order: rest days and byes from the schedule alone
team_games as (
    select game_id, season, week, game_date, team,
           game_date - lag(game_date) over w as rest_days,
           week - lag(week) over w           as weeks_since_prev
    from (select game_id, season, week, game_date, home_team as team from games
          union all
          select game_id, season, week, game_date, away_team from games) as t
    window w as (partition by team, season order by game_date, week)
),

-- the team's home stadium time zone (hours from US Eastern; Arizona counted as Mountain)
team_tz (team, tz) as (
    values ('ATL', 0), ('BAL', 0), ('BUF', 0), ('CAR', 0), ('CIN', 0), ('CLE', 0), ('DET', 0), ('IND', 0),
           ('JAX', 0), ('MIA', 0), ('NE', 0), ('NYG', 0), ('NYJ', 0), ('PHI', 0), ('PIT', 0), ('TB', 0), ('WAS', 0),
           ('CHI', -1), ('DAL', -1), ('GB', -1), ('HOU', -1), ('KC', -1), ('MIN', -1), ('NO', -1), ('TEN', -1),
           ('DEN', -2), ('ARI', -2),
           ('LA', -3), ('LAC', -3), ('LV', -3), ('OAK', -3), ('SD', -3), ('SF', -3), ('SEA', -3)
),

-- every venue since 2016 (nflverse stadium_id); a new stadium falls back to the home team's zone
stadium_tz (stadium_id, tz) as (
    values ('ATL00', 0), ('ATL97', 0), ('BAL00', 0), ('BOS00', 0), ('BUF00', 0), ('CAR00', 0), ('CIN00', 0),
           ('CLE00', 0), ('DET00', 0), ('IND00', 0), ('JAX00', 0), ('MIA00', 0), ('NYC01', 0), ('PHI00', 0),
           ('PIT00', 0), ('TAM00', 0), ('WAS00', 0),
           ('CHI98', -1), ('DAL00', -1), ('GNB00', -1), ('HOU00', -1), ('KAN00', -1), ('MIN01', -1), ('NAS00', -1),
           ('NOR00', -1), ('MEX00', -1),
           ('DEN00', -2), ('PHO00', -2),
           ('LAX01', -3), ('LAX97', -3), ('LAX99', -3), ('OAK00', -3), ('SDG00', -3), ('SEA00', -3), ('SFO01', -3),
           ('VEG00', -3),
           ('LON00', 5), ('LON01', 5), ('LON02', 5), ('DUB00', 5),
           ('FRA00', 6), ('GER00', 6), ('MUN01', 6), ('MAD01', 6), ('PAR00', 6),
           ('SAO00', 1), ('RIO00', 1),
           ('MEL00', 14)
),

base as (
    select
        u.gsis_id, u.season, u.week, u.game_id, u.team, u.opponent, u.is_home,
        g.game_date, g.gametime, g.location, g.roof, g.surface, g.is_divisional,
        g.game_date - ws.sunday                                                     as days_from_sunday,
        case when g.gametime ~ '^\d{1,2}:\d{2}'
             then split_part(g.gametime, ':', 1)::int + split_part(g.gametime, ':', 2)::int / 60.0 end
                                                                                    as kickoff_hour_et,
        tg.rest_days, tg.weeks_since_prev,
        og.rest_days                                                                as opp_rest_days,
        tt.tz                                                                       as team_tz,
        coalesce(st.tz, case when g.location = 'Home' then ht.tz end)               as venue_tz
    from {{ ref('int_player_week_universe') }} as u
    join games as g on g.game_id = u.game_id
    left join week_sunday as ws on ws.season = g.season and ws.week = g.week
    left join team_games as tg on tg.game_id = u.game_id and tg.team = u.team
    left join team_games as og on og.game_id = u.game_id and og.team = u.opponent
    left join team_tz as tt on tt.team = u.team
    left join team_tz as ht on ht.team = g.home_team
    left join stadium_tz as st on st.stadium_id = g.stadium_id
)

select
    gsis_id, season, week,
    -- when
    days_from_sunday                                                      as gc_weekday,
    kickoff_hour_et                                                       as gc_kickoff_hour_et,
    kickoff_hour_et >= 20                                                 as gc_primetime,
    kickoff_hour_et >= 12 and kickoff_hour_et < 14                        as gc_early_window,
    -- rest (NULL in week 1: no previous game this season)
    rest_days                                                             as gc_rest_days,
    rest_days <= 4                                                        as gc_short_week,
    case when weeks_since_prev is not null then weeks_since_prev >= 2 end as gc_off_bye,
    opp_rest_days                                                         as gc_opp_rest_days,
    rest_days - opp_rest_days                                             as gc_rest_edge,
    -- travel: time zones crossed from the team's home to the venue, west -> east positive (wrapped to +-12)
    case when venue_tz is not null and team_tz is not null
         then (((venue_tz - team_tz) + 12 + 24) % 24) - 12 end           as gc_travel_tz,
    case when team_tz is not null and kickoff_hour_et is not null
         then team_tz = -3 and kickoff_hour_et < 14 end                   as gc_west_coast_early,
    -- venue: fixed dome 1, open air 0, retractable NULL (open / closed is a game-day call: not known before)
    case roof when 'dome' then 1 when 'outdoors' then 0 end              as gc_roof,
    case when surface is not null then surface not in ('grass', 'dessograss') end as gc_surface_turf,
    is_divisional                                                         as gc_div_game,
    location = 'Neutral'                                                  as gc_neutral_site
from base
