-- IL-1 (Wave I-L; the fifth review § 10): NFL Next Gen Stats per player x season x regular-season week, the three
-- NGS tables (passing, rushing, receiving) side by side. Week 0 is NGS's own season aggregate (is_season_aggregate),
-- kept apart: a window over weeks reads weeks >= 1 only (api/league_lab_api/stats.py).
--
-- * Identity is NGS's gsis id (player_gsis_id) on every row: the three tables are joined on gsis id + season + week,
--   never by name; analytics.player_id_map maps it on to Sleeper (AGENTS rule 3).
-- * Regular season only: NGS numbers the playoffs from week 18 (17-game seasons) or 19, which would collide with
--   week 18 of a regular season.
-- * NGS publishes a weekly row only for a player-week that clears its minimum (in our data: QBs with 15+ pass attempts,
--   running backs with 10+ carries, WRs / TEs with 5+ targets — the rushing table has no QBs, the receiving table no
--   running backs): a player-week with no row is unknown here (null), never 0.
-- * Each value is NGS's per-player aggregate for the week; the denominator NGS states sits beside it
--   (ngs_pass_attempts, ngs_rush_attempts, ngs_targets, ngs_receptions), so a window over several weeks is the mean
--   of the weekly values weighted by that denominator — never a mean of means (docs/METRICS.md § "Next Gen Stats").
with pass as (
    select * from {{ ref('stg_nflverse__ngs_passing') }} where season_type = 'REG'
), rush as (
    select * from {{ ref('stg_nflverse__ngs_rushing') }} where season_type = 'REG'
), rec as (
    select * from {{ ref('stg_nflverse__ngs_receiving') }} where season_type = 'REG'
), keys as (
    select gsis_id, season, week from pass
    union
    select gsis_id, season, week from rush
    union
    select gsis_id, season, week from rec
)

select
    k.gsis_id, k.season, k.week,
    k.week = 0 as is_season_aggregate,
    coalesce(p.player_name, r.player_name, c.player_name) as player_name,
    coalesce(dp.position, p.position, r.position, c.position) as position,
    coalesce(p.team, r.team, c.team) as team,
    -- passing (qualified: the week's row exists)
    p.gsis_id is not null as has_passing,
    p.attempts as ngs_pass_attempts,
    p.avg_time_to_throw,
    p.completion_percentage_above_expectation,
    p.aggressiveness,
    p.avg_intended_air_yards as pass_avg_intended_air_yards,
    -- rushing
    r.gsis_id is not null as has_rushing,
    r.rush_attempts as ngs_rush_attempts,
    r.rush_yards_over_expected,
    r.rush_yards_over_expected_per_att,
    r.efficiency as rush_efficiency,
    r.percent_attempts_gte_eight_defenders,
    r.avg_time_to_los,                                     -- IM-1 (Wave I-M): weighted by ngs_rush_attempts
    -- receiving
    c.gsis_id is not null as has_receiving,
    c.targets as ngs_targets,
    c.receptions as ngs_receptions,
    c.avg_separation,
    c.avg_cushion,
    c.avg_yac_above_expectation,
    c.percent_share_of_intended_air_yards,
    c.avg_intended_air_yards as rec_avg_intended_air_yards  -- IM-1 (Wave I-M): weighted by ngs_targets
from keys k
left join pass p on p.gsis_id = k.gsis_id and p.season = k.season and p.week = k.week
left join rush r on r.gsis_id = k.gsis_id and r.season = k.season and r.week = k.week
left join rec c on c.gsis_id = k.gsis_id and c.season = k.season and c.week = k.week
left join {{ ref('dim_player') }} dp on dp.gsis_id = k.gsis_id
