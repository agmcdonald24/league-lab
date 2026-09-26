{{ config(indexes=[{'columns': ['league_id', 'week']}]) }}
-- Roster x week results. Two rows per matchup (one per side). is_scored marks weeks Sleeper
-- has actually scored (future weeks in the live season come back with zero points).
with m as (
    select * from {{ ref('stg_sleeper__matchups') }}
),

l as (select * from {{ ref('dim_league_season') }}),

sides as (
    select
        m.league_id, l.season, m.week, m.roster_id, m.matchup_id, m.points, m.custom_points,
        o.roster_id as opponent_roster_id, o.points as opponent_points,
        m.week >= l.playoff_week_start as is_playoff_week,
        m.week <= coalesce(l.last_scored_leg, 0) as is_scored,
        l.status
    from m
    join l using (league_id)
    left join m as o
           on o.league_id = m.league_id and o.week = m.week and o.matchup_id = m.matchup_id
          and o.roster_id <> m.roster_id
)

select
    league_id, season, week, roster_id, matchup_id,
    case when is_playoff_week then 'PLAYOFF' else 'REG' end as week_type,
    is_playoff_week,
    is_scored,
    matchup_id is null                                  as is_bye,
    points,
    custom_points,
    opponent_roster_id,
    opponent_points,
    case when not is_scored or matchup_id is null then null
         when points > opponent_points then 'W'
         when points < opponent_points then 'L' else 'T' end as result,
    round(points - opponent_points, 2)                  as margin
from sides
