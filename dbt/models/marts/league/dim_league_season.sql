-- One row per league-season in the chain, with its scoring version and playoff structure.
with l as (select * from {{ ref('stg_sleeper__leagues') }})

select
    league_id,
    season,
    league_name,
    status,
    previous_league_id,
    draft_id,
    num_teams,
    playoff_week_start,
    playoff_week_start - 1                         as regular_season_weeks,
    playoff_teams,
    last_scored_leg,
    current_leg,
    trade_deadline_week,
    waiver_type,
    waiver_budget,
    ppr_value,
    scoring_settings,
    roster_positions,
    (select count(*) from jsonb_array_elements_text(roster_positions) as rp where rp <> 'BN') as starter_slots,
    season = (select max(season) from l)           as is_current_season,
    fetched_at
from l
