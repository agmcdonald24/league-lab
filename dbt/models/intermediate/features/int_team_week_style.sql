{{ config(indexes=[{'columns': ['team', 'season', 'week'], 'unique': True}], post_hook="analyze {{ this }}") }}
{%- set prior_games = 3 -%}
{#- metric -> expression over a window's sums; '@' is the window suffix (_std, _l4, _prev). The DEFENSE's numbers
    are the same expressions over its opponents' offensive rows: plays faced, pace faced, pass rate faced, first
    downs allowed, sacks per opponent dropback (sacks made), opponent giveaways (= takeaways). -#}
{%- set metrics = {
    'plays_pg':           'plays@::numeric / nullif(games@, 0)',
    'sec_per_play':       'pace_seconds@::numeric / nullif(pace_snaps@, 0)',
    'neutral_pass_rate':  'neutral_dropbacks@::numeric / nullif(neutral_plays@, 0)',
    'proe':               '(xpass_dropbacks@ - xpass_sum@)::numeric / nullif(xpass_plays@, 0)',
    'first_downs_pg':     'first_downs@::numeric / nullif(fd_games@, 0)',
    'top_min_pg':         'top_seconds@::numeric / 60 / nullif(games@, 0)',
    'red_zone_trips_pg':  'red_zone_trips@::numeric / nullif(games@, 0)',
    'points_per_drive':   'drive_points@::numeric / nullif(drives@, 0)',
    'scoring_drive_rate': 'scoring_drives@::numeric / nullif(drives@, 0)',
    'yards_per_play':     'yards@::numeric / nullif(plays@, 0)',
    'sacks_per_dropback': 'sacks@::numeric / nullif(dropbacks@, 0)',
    'giveaways_pg':       'giveaways@::numeric / nullif(gv_games@, 0)',
} -%}
{%- set facts = ['plays', 'dropbacks', 'sacks', 'yards', 'neutral_plays', 'neutral_dropbacks', 'xpass_plays',
                 'xpass_dropbacks', 'xpass_sum', 'pace_snaps', 'pace_seconds', 'top_seconds', 'drives',
                 'drive_points', 'scoring_drives', 'red_zone_trips', 'first_downs', 'giveaways'] -%}
-- D4 (plan Iteration 12, team volume and style; metric team_style v1.0). Team x season x week (regular season,
-- 2016+, every week of the schedule incl. byes and weeks not played yet): how the team's OFFENSE and DEFENSE have
-- played, AS OF the week: only its regular-season games of the same season with week < this week, plus last
-- season's full regular season as the prior.
--
--   <side>_<metric>_std   season to date, shrunk toward last season
--   <side>_<metric>_l4    the last 4 games before the week (fewer early on), shrunk the same way
--   <side>_<metric>_prev  the prior: the team's full previous regular season (pooled), or the league's when the
--                         team has none; NULL in 2016 (no earlier season loaded)
--   shrinkage (macro ts_shrink)  value = (n * window + {{ prior_games }} * prev) / (n + {{ prior_games }}), n = the team's
--                         games this season before the week, for both windows (the in-season weight grows with
--                         the season, not with the window). Week 1 = prev; week 2 = 1/4 this season; week 10 after
--                         9 games = 3/4. No prior (2016): the in-season value (NULL in week 1).
--   rates pool sums over sums inside the window (numerator and denominator share the games).
--   <side>_asof_week      the newest game week used (NULL before the first game): always < week.
-- side: off = the team's offense; def = the offenses it faced (what the defense allowed). The metric expressions
-- live once, in the `metrics` map at the top; the per-game facts are defined in int_team_game_style.
with games as (
    select * from {{ ref('int_team_game_style') }} where season_type = 'REG'
),

sided as (
    select team, 'off' as side, season, week, {{ facts | join(', ') }} from games
    union all
    select opponent as team, 'def' as side, season, week, {{ facts | join(', ') }} from games
),

keys as (   -- every regular-season week x every team on that season's schedule (franchise codes, as the stats say)
    select distinct w.season, w.week, t.team
    from (select distinct season, week from {{ ref('dim_game') }}
          where season_type = 'REG' and season >= {{ var('seasons_start') }}) as w
    join (select season, {{ kd_team('home_team') }} as team from {{ ref('dim_game') }} where season_type = 'REG'
          union
          select season, {{ kd_team('away_team') }} from {{ ref('dim_game') }} where season_type = 'REG') as t
      on t.season = w.season
),

windowed as (   -- each side's games before the week, newest first
    select k.team, k.season, k.week, s.side, s.week as game_week,
           row_number() over (partition by k.team, k.season, k.week, s.side order by s.week desc) as recency,
           {% for f in facts %}s.{{ f }}{{ ', ' if not loop.last }}{% endfor %}
    from keys as k
    join sided as s on s.team = k.team and s.season = k.season and s.week < k.week
),

agg as (
    select team, season, week, side, max(game_week) as asof_week,
           {{ ts_sums(facts, '_std') }},
           {{ ts_sums(facts, '_l4', 'recency <= 4') }}
    from windowed
    group by 1, 2, 3, 4
),

window_values as (
    select team, season, week, side, asof_week, games_std
           {%- for m, expr in metrics.items() %},
           {{ expr.replace('@', '_std') }} as {{ m }}_std,
           {{ expr.replace('@', '_l4') }} as {{ m }}_l4
           {%- endfor %}
    from agg
),

team_prev as (   -- the prior: each team's full regular season, per side (joined to the NEXT season)
    select team, season + 1 as season, side
           {%- for m, expr in metrics.items() %},
           {{ expr.replace('@', '_prev') }} as {{ m }}_prev
           {%- endfor %}
    from (select team, season, side, {{ ts_sums(facts, '_prev') }} from sided group by 1, 2, 3) s
),

league_prev as (   -- the fallback prior: the league's season (every team-game once; the same for both sides)
    select season + 1 as season
           {%- for m, expr in metrics.items() %},
           {{ expr.replace('@', '_prev') }} as {{ m }}_prev
           {%- endfor %}
    from (select season, {{ ts_sums(facts, '_prev') }} from games group by 1) s
),
{%- for side in ['off', 'def'] %}

{{ side }} as (
    select k.team, k.season, k.week,
           coalesce(v.games_std, 0) as games,
           v.asof_week
           {%- for m in metrics %},
           v.{{ m }}_std, v.{{ m }}_l4,
           coalesce(tp.{{ m }}_prev, lp.{{ m }}_prev) as {{ m }}_prev
           {%- endfor %}
    from keys as k
    left join window_values as v on v.team = k.team and v.season = k.season and v.week = k.week and v.side = '{{ side }}'
    left join team_prev as tp on tp.team = k.team and tp.season = k.season and tp.side = '{{ side }}'
    left join league_prev as lp on lp.season = k.season
),
{%- endfor %}

shrunk as (
    select o.team, o.season, o.week,
           o.games as off_games, o.asof_week as off_asof_week,
           d.games as def_games, d.asof_week as def_asof_week
           {%- for side, x in [('off', 'o'), ('def', 'd')] %}
           {%- for m in metrics %}
           {%- for w in ['std', 'l4'] %},
           round(({{ ts_shrink(x ~ '.' ~ m ~ '_' ~ w, x ~ '.games', x ~ '.' ~ m ~ '_prev', prior_games) }})::numeric, 4) as {{ side }}_{{ m }}_{{ w }}
           {%- endfor %},
           round({{ x }}.{{ m }}_prev::numeric, 4) as {{ side }}_{{ m }}_prev
           {%- endfor %}
           {%- endfor %}
    from off as o
    join def as d using (team, season, week)
)

select s.*,
       round(avg(s.off_plays_pg_std) over (partition by s.season, s.week), 4)          as league_plays_pg_std,
       round(avg(s.off_neutral_pass_rate_std) over (partition by s.season, s.week), 4) as league_neutral_pass_rate_std
from shrunk as s
