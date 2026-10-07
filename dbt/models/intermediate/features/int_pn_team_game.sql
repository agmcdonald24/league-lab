{{ config(indexes=[{'columns': ['team', 'season', 'week'], 'unique': True}, {'columns': ['game_id']}]) }}
-- Plan D5 (personnel), helper 1 of 3: one row per team x regular-season game, 2016 on, played or not, one
-- code per franchise (kd_team: OAK -> LV, SD -> LAC, STL -> LA, as the player and team stats files say).
--   starting_qb_id   the schedule's starting QB (raw.nfl_schedules home_qb_id / away_qb_id): for a game not
--                    played yet it is the projected starter nflverse fills about a week ahead (NULL further
--                    out); for a played game it is the QB who started.
--   is_played        the team's box score is in (fct_team_game): the only games a week-W feature may read,
--                    and only those with week < W
--   team_snaps       offensive snaps of the game: the snap leader's snaps / his snap share (NULL without snaps)
--   team_targets / team_carries   fct_team_game (the denominators of the teammates' shares, never a sum of
--                    player rows)
--   game_no          the team's n-th regular-season game of the season (byes skipped)
-- ---- IP-1 (Wave I-P): the starter from what happened (st1.0; docs/METRICS.md § "The quarterback weak spot").
-- nflverse's schedule sometimes keeps the PRE-GAME projected starter after the game: the listed QB threw no pass
-- (2022: 4 team-games, 2024: 33, 2025: 7, 2026 weeks 1-4: 5; none 2016-2021), e.g. WAS 2024 weeks 9-13 "Mariota"
-- while Daniels started, SEA 2026 weeks 3-5 "Lock" while Darnold started. With var('pn_starter_from_play') on:
--   a played game's starting_qb_id = the listed QB when he threw a pass for the team in it, else the team's QB with
--     the most pass attempts (what happened: training's "is he the starter?" and every history input read it);
--   an unplayed game's = the listing, unless it repeats a listing that was already wrong in the team's newest
--     played game this season (that QB threw no pass there): then that game's real starter (known before kickoff).
--   listed_qb_id keeps the schedule's own value. Off: exactly the schedule, as before.
with games as (
    select g.game_id, g.season, g.week, g.kickoff_at,
           {{ kd_team('t.team') }} as team, {{ kd_team('t.opp') }} as opponent, t.qb_id as starting_qb_id
    from {{ ref('dim_game') }} as g
    cross join lateral (values (g.home_team, g.away_team, g.home_qb_id), (g.away_team, g.home_team, g.away_qb_id)) as t(team, opp, qb_id)
    where g.season_type = 'REG' and g.season >= {{ var('seasons_start') }}
),

snaps as (
    select distinct on (game_id, team)
           game_id, {{ kd_team('team') }} as team, round(offense_snaps / offense_snap_pct)::int as team_snaps
    from {{ ref('int_player_game_snaps') }}
    where game_type = 'REG' and offense_snap_pct > 0 and offense_snaps > 0
    order by game_id, team, offense_snaps desc, offense_snap_pct desc
),

-- ---- IP-1: who threw for the team in each game (any listed position: Taysom Hill started at QB listed as a TE; a
-- receiver's one trick-play pass never has the most attempts while a quarterback threw)
passers as (
    select game_id, {{ kd_team('team') }} as team, gsis_id, attempts
    from {{ ref('fct_player_game') }}
    where season_type = 'REG' and coalesce(attempts, 0) > 0
),

top_passer as (
    select distinct on (game_id, team) game_id, team, gsis_id as top_passer_id
    from passers
    order by game_id, team, attempts desc, gsis_id
),

base as (
    select
        g.season, g.week, g.game_id, g.team, g.opponent, g.kickoff_at,
        nullif(g.starting_qb_id, '')                                         as listed_qb_id,
        tg.game_id is not null                                               as is_played,
        s.team_snaps,
        tg.targets                                                           as team_targets,
        tg.carries                                                           as team_carries,
        row_number() over (partition by g.team, g.season order by g.week)::int as game_no,
        tp.top_passer_id,
        exists (select 1 from passers as p
                where p.game_id = g.game_id and p.team = g.team and p.gsis_id = nullif(g.starting_qb_id, '')) as listed_threw
    from games as g
    left join {{ ref('fct_team_game') }} as tg on tg.game_id = g.game_id and tg.team = g.team and tg.season_type = 'REG'
    left join snaps as s on s.game_id = g.game_id and s.team = g.team
    left join top_passer as tp on tp.game_id = g.game_id and tp.team = g.team
),

played as (
    select b.*,
           case when b.is_played and not b.listed_threw and b.top_passer_id is not null then b.top_passer_id
                else b.listed_qb_id end                                      as played_qb_id,
           (b.is_played and not b.listed_threw and b.top_passer_id is not null) as listing_wrong
    from base as b
),

guarded as (
    select p.*,
           (array_agg(p.listed_qb_id) filter (where p.is_played) over w_prev)[1]  as prev_listed_qb_id,
           (array_agg(p.played_qb_id) filter (where p.is_played) over w_prev)[1]  as prev_played_qb_id,
           (array_agg(p.listing_wrong) filter (where p.is_played) over w_prev)[1] as prev_listing_wrong
    from played as p
    window w_prev as (partition by p.team, p.season order by p.week desc
                      rows between 1 following and unbounded following)
)

select
    season, week, game_id, team, opponent, kickoff_at,
    {%- if var('pn_starter_from_play', false) %}
    case when is_played then played_qb_id
         when listed_qb_id is not null and listed_qb_id = prev_listed_qb_id and prev_listing_wrong then prev_played_qb_id
         else listed_qb_id end                                               as starting_qb_id,
    {%- else %}
    listed_qb_id                                                             as starting_qb_id,
    {%- endif %}
    listed_qb_id,
    is_played, team_snaps, team_targets, team_carries, game_no
from guarded
-- ---- end IP-1
