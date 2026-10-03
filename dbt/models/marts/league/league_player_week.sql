-- depends_on: {{ ref('scoring_stat_map') }}
{{ config(indexes=[{'columns': ['league_id', 'week', 'roster_id']}, {'columns': ['gsis_id']}]) }}
-- League-season x week x roster x player: who was on the roster, whether they started, in
-- which slot, the points Sleeper observed, and the points League Lab recomputes from NFL
-- statistics under that season's scoring version. Grain: league_id, week, roster_id, sleeper_player_id.
with mp as (
    select * from {{ ref('stg_sleeper__matchup_players') }}
),

l as (select league_id, season, scoring_settings, last_scored_leg from {{ ref('dim_league_season') }}),

sp as (
    select sleeper_player_id, full_name, position, team as sleeper_team, is_team_defense
    from {{ ref('stg_sleeper__players') }}
),

idmap as (select sleeper_id, gsis_id from {{ ref('player_id_map') }}),

stats as (
    -- weekly stats plus the play-by-play long-touchdown counts the bonus scoring keys need
    select w.*,
           coalesce(b.pass_tds_10p, 0) as pass_tds_10p, coalesce(b.pass_tds_40p, 0) as pass_tds_40p, coalesce(b.pass_tds_50p, 0) as pass_tds_50p,
           coalesce(b.rush_tds_10p, 0) as rush_tds_10p, coalesce(b.rush_tds_40p, 0) as rush_tds_40p, coalesce(b.rush_tds_50p, 0) as rush_tds_50p,
           coalesce(b.rec_tds_10p, 0)  as rec_tds_10p,  coalesce(b.rec_tds_40p, 0)  as rec_tds_40p,  coalesce(b.rec_tds_50p, 0)  as rec_tds_50p
    from {{ ref('stg_nflverse__player_stats_week') }} as w
    left join {{ ref('int_player_game_pbp') }} as b on b.gsis_id = w.gsis_id and b.game_id = w.game_id
)

select
    mp.league_id,
    l.season,
    mp.week,
    mp.roster_id,
    mp.matchup_id,
    mp.sleeper_player_id,
    idmap.gsis_id,
    coalesce(sp.full_name, mp.sleeper_player_id)     as player_name,
    sp.position,
    sp.is_team_defense,
    mp.is_starter,
    mp.slot_index,
    mp.slot,
    mp.points                                        as points_observed,
    case when idmap.gsis_id is null or s.gsis_id is null then null
         else {{ league_points('l.scoring_settings', 's') }} end as points_recomputed,
    s.game_id,
    s.team                                           as nfl_team,
    s.opponent_team                                  as nfl_opponent,
    s.gsis_id is not null                            as has_nfl_stat_row,
    mp.week <= coalesce(l.last_scored_leg, 0)        as is_scored_week
from mp
join l using (league_id)
left join sp using (sleeper_player_id)
left join idmap on idmap.sleeper_id = mp.sleeper_player_id
left join stats as s
       on s.gsis_id = idmap.gsis_id and s.season = l.season and s.week = mp.week
