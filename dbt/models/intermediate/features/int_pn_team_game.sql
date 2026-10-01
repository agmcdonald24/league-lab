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
)

select
    g.season, g.week, g.game_id, g.team, g.opponent, g.kickoff_at,
    nullif(g.starting_qb_id, '')                                         as starting_qb_id,
    tg.game_id is not null                                               as is_played,
    s.team_snaps,
    tg.targets                                                           as team_targets,
    tg.carries                                                           as team_carries,
    row_number() over (partition by g.team, g.season order by g.week)::int as game_no
from games as g
left join {{ ref('fct_team_game') }} as tg on tg.game_id = g.game_id and tg.team = g.team and tg.season_type = 'REG'
left join snaps as s on s.game_id = g.game_id and s.team = g.team
