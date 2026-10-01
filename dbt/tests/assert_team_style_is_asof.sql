-- D4 (plan Iteration 12, metric team_style v1.0): int_team_week_style at week W uses only the team's regular-season
-- games of that season BEFORE W, plus last season, with the 3-game shrinkage. Re-derived here from fct_play on its
-- own path (plays per team-game counted again, windows and the prior rebuilt): a row whose game count or season-to-
-- date plays per game differs - a game of week W or later counted, a playoff game counted, a different prior - fails.
{{ config(severity='error') }}
with tg as (
    select posteam as team, season, week, count(*) as plays
    from {{ ref('fct_play') }}
    where season_type = 'REG' and season >= {{ var('seasons_start') }}
      and (is_dropback or (is_rush_attempt and not is_kneel))
    group by 1, 2, 3
),

k as (
    select team, season, week, off_games, off_plays_pg_std from {{ ref('int_team_week_style') }}
),

cur as (
    select k.team, k.season, k.week, count(tg.plays) as n, avg(tg.plays) as v
    from k
    left join tg on tg.team = k.team and tg.season = k.season and tg.week < k.week
    group by 1, 2, 3
),

prior as (
    select c.*, coalesce(t.p, l.p) as p
    from cur as c
    left join (select team, season + 1 as season, avg(plays) as p from tg group by 1, 2) as t using (team, season)
    left join (select season + 1 as season, avg(plays) as p from tg group by 1) as l using (season)
),

expected as (
    select team, season, week, n,
           case when p is null then v when n = 0 then p else (n * v + 3 * p) / (n + 3) end as plays_pg
    from prior
)

select e.team, e.season, e.week, e.n as games_recount, k.off_games, e.plays_pg as plays_pg_recount, k.off_plays_pg_std
from expected as e
join k using (team, season, week)
where e.n <> k.off_games
   or abs(coalesce(e.plays_pg, -1) - coalesce(k.off_plays_pg_std, -1)) > 0.0001
