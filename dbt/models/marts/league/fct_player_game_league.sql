-- depends_on: {{ ref('scoring_stat_map') }}
{{ config(indexes=[{'columns': ['league_id', 'gsis_id', 'season']}, {'columns': ['league_id', 'season', 'season_type']}]) }}
-- Player x game x league (plan S-01a): every NFL player-game (2016+) priced under each *current*
-- league-season's own scoring, so league pages show PPG, xPPG, ranks and positional strength in
-- the viewer's league instead of the reference league's. Grain: league_id, gsis_id, game_id.
--   points          : league_points() over the weekly stats row + the play-by-play long-TD counts,
--                     i.e. the same inputs as league_player_week.points_recomputed (reconciled to
--                     the cent by assert_league_points_match_recomputed)
--   points_expected : the same league's map over the ffverse expected stats, stat keys only
--                     (include_bonuses=false, as int_expected_points_week); NULL when ffverse has
--                     no row for the player-game (kickers, special-teams-only rows)
-- NFL research marts keep the reference league's scoring (fct_player_game.points_current_scoring).
with leagues as (
    select league_id, scoring_settings
    from {{ ref('dim_league_season') }}
    where is_current_season
),

stats as (
    -- the weekly stats row plus the play-by-play long-touchdown counts the bonus scoring keys need
    -- (identical to fct_player_game / league_player_week)
    select w.*,
           coalesce(b.pass_tds_40p, 0) as pass_tds_40p, coalesce(b.pass_tds_50p, 0) as pass_tds_50p,
           coalesce(b.rush_tds_40p, 0) as rush_tds_40p, coalesce(b.rush_tds_50p, 0) as rush_tds_50p,
           coalesce(b.rec_tds_40p, 0)  as rec_tds_40p,  coalesce(b.rec_tds_50p, 0)  as rec_tds_50p
    from {{ ref('stg_nflverse__player_stats_week') }} as w
    left join {{ ref('int_player_game_pbp') }} as b on b.gsis_id = w.gsis_id and b.game_id = w.game_id
),

pg as (
    -- keys, position and the appearance flag exactly as the NFL-wide marts use them
    select gsis_id, game_id, season, season_type, week, team, player_name, position, played
    from {{ ref('fct_player_game') }}
),

e as (
    select * from {{ ref('stg_nflverse__ff_opportunity') }}
)

select
    l.league_id,
    pg.gsis_id,
    pg.game_id,
    pg.season,
    pg.season_type,
    pg.week,
    pg.team,
    pg.player_name,
    pg.position,
    pg.played,
    {{ league_points('l.scoring_settings', 's') }}                                   as points,
    e.gsis_id is not null                                                           as expected_known,
    case when e.gsis_id is not null
         then {{ league_points('l.scoring_settings', 'e', include_bonuses=false) }} end as points_expected
from pg
join stats as s on s.gsis_id = pg.gsis_id and s.game_id = pg.game_id
cross join leagues as l
left join e on e.gsis_id = pg.gsis_id and e.game_id = pg.game_id
