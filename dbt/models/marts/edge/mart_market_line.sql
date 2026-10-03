{{ config(materialized='table', indexes=[{'columns': ['season', 'week', 'gsis_id']}]) }}
-- The market line ("Sleeper has him at 16.2"): Sleeper's own projected stat line per player-week, LEAGUE-FREE, from
-- the LATEST snapshot of each week fetched so far (raw.sleeper_projections; mart_projection_record keeps the last
-- pre-kickoff one for the record — this is the freshest, for the week being decided). One row per season x week x
-- gsis_id (QB RB WR TE K; a team defense is left out: its keys are unmapped, as in the record). The API prices the
-- line in each league's own scoring on request (`api/league_lab_api/why.py` market_points: scoring.compute_points,
-- the pricing of our own line, yardage bonuses and position premiums included), so a house league and any on-demand
-- league get their own number from the same rows. A listed player with no stat line (a backup, a player ruled out)
-- is not a projection of 0 and is left out (the record's rule). Read by /api/ros, /api/player, /api/my-week.
{%- set line_columns = ['attempts', 'completions', 'carries', 'targets', 'passing_yards', 'passing_tds',
    'passing_interceptions', 'passing_2pt_conversions', 'rushing_yards', 'rushing_tds', 'rushing_2pt_conversions',
    'receptions', 'receiving_yards', 'receiving_tds', 'receiving_2pt_conversions', 'fumbles_total', 'fumbles_lost_total',
    'fumble_recovery_tds', 'special_teams_tds', 'fg_made_0_19', 'fg_made_20_29', 'fg_made_30_39', 'fg_made_40_49',
    'fg_made_50_59', 'fg_missed', 'fg_missed_0_19', 'fg_missed_20_29', 'fg_missed_30_39', 'fg_missed_40_49',
    'fg_missed_50_59', 'pat_made', 'pat_missed', 'pass_tds_40p', 'pass_tds_50p', 'rush_tds_40p', 'rush_tds_50p',
    'rec_tds_40p', 'rec_tds_50p'] %}
{#- = league_lab.ingest.sleeper_projections.LINE_COLUMNS (as mart_projection_record) #}

with latest as (
    select season, week, max(fetched_at) as fetched_at
    from {{ source('raw', 'sleeper_projections') }}
    where season_type = 'regular'
      and season = (select max(season) from {{ source('raw', 'sleeper_projections') }})
    group by season, week
)

select m.gsis_id, p.player_id as sleeper_id, p.season, p.week, p.position, p.team, p.opponent, p.fetched_at,
       p.pts_ppr, p.pts_half_ppr, p.pts_std,
       {%- for c in line_columns %}
       p.{{ c }}{{ "," if not loop.last }}
       {%- endfor %}
from {{ source('raw', 'sleeper_projections') }} as p
join latest as l using (season, week, fetched_at)
join {{ ref('player_id_map') }} as m on m.sleeper_id = p.player_id
where p.season_type = 'regular'
  and p.position in ('QB', 'RB', 'WR', 'TE', 'K')
  and (p.pts_ppr is not null or p.pts_half_ppr is not null or p.pts_std is not null
       or coalesce(p.attempts, p.carries, p.targets, p.passing_yards, p.rushing_yards, p.receiving_yards,
                   p.receptions, p.passing_tds, p.rushing_tds, p.receiving_tds, p.fg_made_0_19, p.pat_made) is not null)
