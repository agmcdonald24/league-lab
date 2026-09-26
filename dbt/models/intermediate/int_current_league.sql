-- The reference league-season: its scoring is the "current scoring" used for cross-year research
-- views (plan §5). With several leagues loaded, the reference league is the first id in
-- LEAGUE_LAB_SLEEPER_LEAGUE_ID (dbt var reference_league_id); its newest season wins. One row.
select
    league_id,
    season,
    league_name,
    scoring_settings,
    roster_positions,
    playoff_week_start
from {{ ref('stg_sleeper__leagues') }}
order by (league_id = '{{ var("reference_league_id") }}') desc, season desc
limit 1
