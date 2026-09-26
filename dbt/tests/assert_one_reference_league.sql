-- Exactly one league-season prices the NFL-wide numbers (points_current_scoring, expected points,
-- rankings): the reference league's current season. With several leagues configured the first id
-- in LEAGUE_LAB_SLEEPER_LEAGUE_ID is the reference; zero or two would mean the env var and the
-- loaded leagues disagree (fails).
with ref_seasons as (
    select count(*) as n from {{ ref('dim_league_season') }} where is_reference_league and is_current_season
)
select n from ref_seasons where n <> 1
