{# Emit a SQL expression that scores one stat row under a Sleeper scoring_settings jsonb.

   league_points(scoring_expr, stats_alias, include_bonuses=true)
     scoring_expr    : SQL expression yielding the league's scoring_settings jsonb
     stats_alias     : alias of the stg_nflverse__player_stats_week-shaped relation. With
                       include_bonuses it must also carry the play-by-play long-TD counts
                       (pass_tds_40p ... from int_player_game_pbp, coalesced to 0).
     include_bonuses : false scores the `stat` rows of the seed only (expected points: a
                       threshold on an expected yardage would pay deterministically).

   The key -> column mapping is the seed `scoring_stat_map` (generated from
   src/league_lab/scoring.py):
     kind = stat  : `col_a + col_b`            -> weight * (coalesce(a,0) + coalesce(b,0))
     kind = bonus : `col_a`                    -> weight * coalesce(a,0)          (long-TD counts)
                    `col:low:high`             -> weight * (low <= col < high)     (yardage bonus;
                                                  high empty = no upper bound)
   Keys the seed does not know (DEF, position-conditional bonuses) contribute 0 and are
   surfaced by the unmapped_scoring_keys check. #}
{% macro league_points(scoring_expr, stats_alias, include_bonuses=true) -%}
  {%- if execute -%}
    {%- set rows = run_query("select sleeper_key, kind, stat_expression from " ~ ref('scoring_stat_map') ~ " order by sleeper_key") -%}
    {%- set terms = [] -%}
    {%- for row in rows.rows -%}
      {%- if row[1] == 'stat' or include_bonuses -%}
        {%- set weight = "coalesce((" ~ scoring_expr ~ " ->> '" ~ row[0] ~ "')::numeric, 0)" -%}
        {%- if ':' in row[2] -%}
          {%- set spec = row[2].split(':') -%}
          {%- set cond = "coalesce(" ~ stats_alias ~ "." ~ spec[0] ~ ", 0) >= " ~ spec[1] -%}
          {%- if spec[2] | trim != '' -%}
            {%- set cond = cond ~ " and coalesce(" ~ stats_alias ~ "." ~ spec[0] ~ ", 0) < " ~ spec[2] -%}
          {%- endif -%}
          {%- do terms.append(weight ~ " * (case when " ~ cond ~ " then 1 else 0 end)") -%}
        {%- else -%}
          {%- set cols = [] -%}
          {%- for part in row[2].split('+') -%}
            {%- do cols.append("coalesce(" ~ stats_alias ~ "." ~ (part | trim) ~ ", 0)") -%}
          {%- endfor -%}
          {%- do terms.append(weight ~ " * (" ~ cols | join(' + ') ~ ")") -%}
        {%- endif -%}
      {%- endif -%}
    {%- endfor -%}
    round(({{ terms | join(' + ') }})::numeric, 2)
  {%- else -%}
    0::numeric
  {%- endif -%}
{%- endmacro %}
