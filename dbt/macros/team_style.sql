{# D4 (plan Iteration 12, metric team_style v1.0): the early-season shrinkage of int_team_week_style.

   value = (n * window + k * prior) / (n + k)

   n = the team's games this season before the week, window = the in-season value (season to date or last 4),
   prior = last season's value (the team's; the league's when the team has none), k = the prior's weight in games
   (3, as mart_defense_position_profile weights an offense's last season). Week 1 (n = 0) is the prior; with no
   prior (2016) the in-season value stands (NULL in week 1); an in-season value that cannot be computed (no
   denominator) falls back to the prior. Python twin: league_lab.feature_groups.team_style.shrink. #}
{% macro ts_shrink(window, n, prior, k=3) -%}
    case when {{ prior }} is null then {{ window }}
         when {{ n }} = 0 or {{ window }} is null then {{ prior }}
         else ({{ n }} * {{ window }} + {{ k }} * {{ prior }}) / ({{ n }} + {{ k }}) end
{%- endmacro %}

{# The additive facts of int_team_game_style summed over a window of a team's games (rows meeting `cond`), named
   <fact><suffix>, plus the window's game counts (fd_games / gv_games: games whose team-stats row is loaded). #}
{% macro ts_sums(facts, suffix, cond='true') -%}
    count(*) filter (where {{ cond }})                         as games{{ suffix }},
    count(first_downs) filter (where {{ cond }})               as fd_games{{ suffix }},
    count(giveaways) filter (where {{ cond }})                 as gv_games{{ suffix }}
    {%- for f in facts %},
    sum({{ f }}) filter (where {{ cond }})                     as {{ f }}{{ suffix }}
    {%- endfor %}
{%- endmacro %}
