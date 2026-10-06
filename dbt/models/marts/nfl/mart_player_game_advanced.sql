{{ config(indexes=[{'columns': ['gsis_id', 'game_id'], 'unique': True}, {'columns': ['season', 'season_type']}]) }}
-- IM-1 (Wave I-M): the Stats Explorer's advanced numerators, one row per skill player x game he played
-- (fct_player_game: QB / RB / WR / TE / FB with `played`) — merged onto his game row by api/league_lab_api/stats.py,
-- like mart_player_ngs_week. Numerators only: every rate is summed numerator / summed denominator over the window,
-- in the API (docs/METRICS.md § "Stats Explorer: Wave I-M columns").
--
-- * Play-by-play (int_player_game_efficiency, from fct_play): successful targets / carries / dropbacks, dropback EPA,
--   scramble yards; the team's deep targets (20+ air yards, the same flags as int_player_game_pbp.deep_targets)
--   counted from the plays of his team in the game — an independent team total, never summed player rows.
-- * Pro Football Reference advanced stats, weekly (nflverse `pfr_advstats`, 2018 on, published in season): joined by
--   PFR id -> gsis id through analytics.player_id_map, never by name. A PFR row that does not map is not here
--   (counted by api/tests/test_im1.py); a game PFR has no row for is unknown (has_pfr_* false), never 0 — the API
--   divides a PFR count only by the denominator of the games PFR covered.
-- * What PFR's weekly files carry (read 2026-10-05): receiving — drops, broken tackles, INTs and passer rating when
--   targeted; rushing — PFR's carries, yards before / after contact, broken tackles; passing — bad throws, his
--   receivers' drops, pressures, hurries, hits, blitzes, sacks. Not weekly (season files only, so no window can use
--   them): receiving yards before / after contact, on-target throws, pocket time.
with games as (
    select gsis_id, game_id, season, season_type, week, team, position
    from {{ ref('fct_player_game') }}
    where played and position in ('QB', 'RB', 'WR', 'TE', 'FB')
),

eff as (
    select * from {{ ref('int_player_game_efficiency') }}
),

team_deep as (
    select posteam as team, game_id, count(*) filter (where is_target and air_yards >= 20) as team_deep_targets
    from {{ ref('fct_play') }}
    where not is_no_play and posteam is not null
    group by 1, 2
),

ids as (
    select pfr_id, gsis_id from {{ ref('player_id_map') }} where pfr_id is not null
),

pfr_rec as (
    select i.gsis_id, r.game_id, r.receiving_drop, r.receiving_broken_tackles
    from {{ ref('stg_nflverse__pfr_advstats_rec') }} as r
    join ids as i on i.pfr_id = r.pfr_player_id
),

pfr_rush as (
    select i.gsis_id, r.game_id, r.carries, r.rushing_yards_before_contact, r.rushing_yards_after_contact,
           r.rushing_broken_tackles, r.receiving_broken_tackles
    from {{ ref('stg_nflverse__pfr_advstats_rush') }} as r
    join ids as i on i.pfr_id = r.pfr_player_id
),

pfr_pass as (
    select i.gsis_id, r.game_id, r.passing_bad_throws, r.passing_drops, r.times_pressured, r.times_hurried,
           r.times_hit, r.times_blitzed, r.times_sacked
    from {{ ref('stg_nflverse__pfr_advstats_pass') }} as r
    join ids as i on i.pfr_id = r.pfr_player_id
)

select
    g.gsis_id,
    g.game_id,
    g.season,
    g.season_type,
    g.week,
    g.team,
    -- play-by-play (0 when he had no play of that kind; dropback columns NULL for a player who never dropped back)
    coalesce(e.target_successes, 0)::smallint                   as target_successes,
    coalesce(e.carry_successes, 0)::smallint                    as carry_successes,
    coalesce(e.scramble_yards, 0)::smallint                     as scramble_yards,
    e.dropback_successes::smallint                              as dropback_successes,
    e.dropback_epa                                              as dropback_epa,
    td.team_deep_targets::smallint                              as team_deep_targets,
    -- PFR receiving (the row exists: PFR covered his game)
    rec.gsis_id is not null                                     as has_pfr_rec,
    rec.receiving_drop::smallint                                as pfr_drops,
    -- PFR rushing
    rsh.gsis_id is not null                                     as has_pfr_rush,
    rsh.carries::smallint                                       as pfr_carries,
    rsh.rushing_yards_before_contact::smallint                  as pfr_rush_yards_before_contact,
    rsh.rushing_yards_after_contact::smallint                   as pfr_rush_yards_after_contact,
    -- broken tackles, rushing + receiving: the rushing file carries both for a player with a carry, the receiving
    -- file the receiving ones for a player with a target only
    case when rec.gsis_id is not null or rsh.gsis_id is not null
         then coalesce(rsh.rushing_broken_tackles, 0)
            + coalesce(rsh.receiving_broken_tackles, rec.receiving_broken_tackles, 0) end::smallint as pfr_broken_tackles,
    -- PFR passing
    pss.gsis_id is not null                                     as has_pfr_pass,
    pss.passing_bad_throws::smallint                            as pfr_bad_throws,
    pss.passing_drops::smallint                                 as pfr_pass_drops,
    pss.times_pressured::smallint                               as pfr_times_pressured,
    pss.times_hurried::smallint                                 as pfr_times_hurried,
    pss.times_hit::smallint                                     as pfr_times_hit,
    pss.times_blitzed::smallint                                 as pfr_times_blitzed
from games as g
left join eff as e on e.gsis_id = g.gsis_id and e.game_id = g.game_id
left join team_deep as td on td.team = g.team and td.game_id = g.game_id
left join pfr_rec as rec on rec.gsis_id = g.gsis_id and rec.game_id = g.game_id
left join pfr_rush as rsh on rsh.gsis_id = g.gsis_id and rsh.game_id = g.game_id
left join pfr_pass as pss on pss.gsis_id = g.gsis_id and pss.game_id = g.game_id
