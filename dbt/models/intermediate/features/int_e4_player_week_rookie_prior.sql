{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- Plan E4 (Wave E): the feature group `rookie_prior` (`rk_`), evaluated by the D1 harness
-- (`league-lab experiment rookie_prior`; src/league_lab/feature_groups/rookie_prior.py).
-- One row per int_player_week_universe row. Draft capital and age carry the prior for a player with little NFL
-- history: v3 already sees games_to_date / prev_games / pos_prev_ppg, not where he was drafted or how old he is.
-- Every input is fixed before the season (the draft, the birth date) and constant within it; nothing is read from
-- a game. Definitions: docs/METRICS.md § "Feature experiments" → "Wave E groups".
--   rk_draft_round / rk_draft_pick  the round (1-7) and overall pick; NULL for an undrafted player (rk_undrafted = 1)
--   rk_draft_tier    3 = 1st round, 2 = day 2 (rounds 2-3), 1 = day 3 (rounds 4-7), 0 = undrafted; NULL = not in
--                    the players table (unknown is not zero)
--   rk_years_in      season - his entry season (draft year; rookie season for an undrafted player); 0 = rookie
--   rk_is_rookie     rk_years_in = 0
--   rk_age           age in years on September 1 of the season (one decimal)
with u as (
    select gsis_id, season, week from {{ ref('int_player_week_universe') }}
),

p as (
    select gsis_id, draft_year, draft_round, draft_pick, rookie_season, birth_date
    from {{ ref('stg_nflverse__players') }}
    where gsis_id is not null
),

base as (
    select
    u.gsis_id, u.season, u.week,
    p.draft_round                                                                       as rk_draft_round,
    p.draft_pick                                                                        as rk_draft_pick,
    case when p.gsis_id is null then null
         when p.draft_round is null then 0
         when p.draft_round = 1 then 3
         when p.draft_round <= 3 then 2
         else 1 end                                                                     as rk_draft_tier,
    case when p.gsis_id is not null then (p.draft_round is null)::int end              as rk_undrafted,
    -- an undrafted player's rookie_season can sit a season after a practice-squad / roster appearance: floor at 0
    greatest(0, u.season - coalesce(p.draft_year, p.rookie_season))                    as rk_years_in,
    (greatest(0, u.season - coalesce(p.draft_year, p.rookie_season)) = 0)::int          as rk_is_rookie,
    round(((make_date(u.season, 9, 1) - p.birth_date) / 365.25)::numeric, 1)          as rk_age
    from u
    left join p using (gsis_id)
)

-- rookie_prior_early: the same seven columns in weeks 1-4 only (NULL from week 5 on), so the trees can use draft
-- capital and age only while a player's season has little history (the weeks 1-4 subset was the one that moved)
select base.*,
    case when week <= 4 then rk_draft_round end  as rk_early_draft_round,
    case when week <= 4 then rk_draft_pick end   as rk_early_draft_pick,
    case when week <= 4 then rk_draft_tier end   as rk_early_draft_tier,
    case when week <= 4 then rk_undrafted end    as rk_early_undrafted,
    case when week <= 4 then rk_years_in end     as rk_early_years_in,
    case when week <= 4 then rk_is_rookie end    as rk_early_is_rookie,
    case when week <= 4 then rk_age end          as rk_early_age
from base
