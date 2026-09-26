-- The newest league-season in the chain: its scoring is the "current scoring" used for
-- cross-year research views (plan §5). One row.
select
    league_id,
    season,
    league_name,
    scoring_settings,
    roster_positions,
    playoff_week_start
from {{ ref('stg_sleeper__leagues') }}
order by season desc
limit 1
