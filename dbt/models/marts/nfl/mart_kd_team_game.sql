{{ config(indexes=[{'columns': ['team', 'season', 'week']}, {'columns': ['game_id']}]) }}
-- Team x regular-season game (plan R-13): the kicking and team-defense facts the K and D/ST
-- projections (`league_lab.kdef`) learn from, next to the game context known before kickoff.
-- One row per team per scheduled REG game, played or not (a future game has NULL outcomes).
--   kicking  : the team's FG made by distance, FG missed (blocked kicks count as misses, like
--              Sleeper's `fgmiss`), PAT made / missed (blocked counted as missed) - nflverse team stats
--   defense  : sacks, interceptions, opponent fumbles recovered, forced fumbles, defensive TDs
--              (interception and fumble-return TDs: nflverse files fumble-return TDs under
--              fumble_recovery_tds, Sleeper pays them as `def_td`), special-teams TDs, safeties,
--              blocked kicks (punt + FG + PAT), points allowed (= the opponent's final score:
--              what Sleeper's pts_allow buckets count; reconciled in docs/METRICS.md)
--   offense  : the opponent-facing rates (sacks taken, giveaways, plays, red-zone plays, EPA)
-- Team totals come from the team stats file and the schedule, never from summing player rows.
with g as (
    select game_id, season, week, kickoff_at, home_team, away_team, home_score, away_score, is_final, roof,
           spread_line, total_line
    from {{ ref('dim_game') }}
    where season_type = 'REG' and season >= {{ var('seasons_start') }}
),

-- the schedule keeps a franchise's code of the day (OAK to 2019, SD in 2016); the team stats file
-- uses today's (LV, LAC): one code per franchise here, today's, so every join below meets
sides as (
    select g.*, {{ kd_team('g.home_team') }} as team, {{ kd_team('g.away_team') }} as opponent, true as is_home from g
    union all
    select g.*, {{ kd_team('g.away_team') }} as team, {{ kd_team('g.home_team') }} as opponent, false as is_home from g
),

ts as (
    select * from {{ source('raw', 'nfl_team_stats_week') }}
    where season_type = 'REG' and season >= {{ var('seasons_start') }}
),

tg as (
    select team, game_id, plays_excl_scrambles, red_zone_targets, red_zone_carries, passing_epa, rushing_epa
    from {{ ref('fct_team_game') }}
    where season_type = 'REG'
)

select
    s.team,
    s.game_id,
    s.season,
    s.week,
    s.opponent,
    s.is_home,
    s.kickoff_at,
    s.roof,
    s.roof in ('dome', 'closed')                                                          as is_dome,
    s.spread_line,
    s.total_line,
    case when s.total_line is null or s.spread_line is null then null
         when s.is_home then (s.total_line + s.spread_line) / 2.0
         else (s.total_line - s.spread_line) / 2.0 end                                     as implied_team_total,
    case when s.total_line is null or s.spread_line is null then null
         when s.is_home then (s.total_line - s.spread_line) / 2.0
         else (s.total_line + s.spread_line) / 2.0 end                                     as opp_implied_total,
    coalesce(s.is_final, false) and t.team is not null                                    as played,
    case when s.is_final then case when s.is_home then s.home_score else s.away_score end end as points_for,
    case when s.is_final then case when s.is_home then s.away_score else s.home_score end end as points_allowed,
    -- kicking (the team's; the kicker's own line is in mart_kd_week)
    t.fg_att,
    t.fg_made,
    t.fg_made_0_19,
    t.fg_made_20_29,
    t.fg_made_30_39,
    t.fg_made_40_49,
    t.fg_made_50_59 + t.fg_made_60_                                                        as fg_made_50p,
    t.fg_missed + t.fg_blocked                                                             as fg_missed,
    t.pat_att,
    t.pat_made,
    t.pat_missed + t.pat_blocked                                                           as pat_missed,
    -- team defense and special teams
    t.def_sacks                                                                            as sacks,
    t.def_interceptions                                                                    as interceptions,
    t.fumble_recovery_opp                                                                  as fumble_recoveries,
    t.def_fumbles_forced                                                                   as forced_fumbles,
    t.def_tds + t.fumble_recovery_tds                                                      as def_tds,
    t.special_teams_tds                                                                    as st_tds,
    t.def_safeties                                                                         as safeties,
    t.def_punt_blocks + t.def_fg_blocks + t.def_pat_blocks                                 as blocked_kicks,
    -- the offense (what an opposing defense faces)
    t.sacks_suffered,
    t.passing_interceptions + t.fumbles_lost_total                                         as giveaways,
    x.plays_excl_scrambles                                                                 as plays,
    x.red_zone_targets + x.red_zone_carries                                                as red_zone_plays,
    x.passing_epa + x.rushing_epa                                                          as offense_epa
from sides as s
left join ts as t on t.game_id = s.game_id and t.team = s.team
left join tg as x on x.game_id = s.game_id and x.team = s.team
