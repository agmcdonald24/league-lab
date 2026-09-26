{# Emit a SQL expression that scores one stat row under a Sleeper scoring_settings jsonb.

   league_points(scoring_expr, stats_alias)
     scoring_expr : SQL expression yielding the league's scoring_settings jsonb
     stats_alias  : alias of the stg_nflverse__player_stats_week-shaped relation

   The key -> column mapping is the seed `scoring_stat_map` (generated from
   src/league_lab/scoring.py). Keys the seed does not know (DEF, bonuses) contribute 0 and are
   surfaced by the unmapped_scoring_keys check. #}
{% macro league_points(scoring_expr, stats_alias) -%}
  {%- if execute -%}
    {%- set rows = run_query("select sleeper_key, stat_expression from " ~ ref('scoring_stat_map')) -%}
    round((
    {%- for row in rows.rows -%}
      {%- set parts = row[1].split('+') -%}
      coalesce(({{ scoring_expr }} ->> '{{ row[0] }}')::numeric, 0) * (
        {%- for part in parts -%}
          coalesce({{ stats_alias }}.{{ part | trim }}, 0)
          {%- if not loop.last %} + {% endif -%}
        {%- endfor -%}
      )
      {%- if not loop.last %} + {% endif -%}
    {%- endfor -%}
    )::numeric, 2)
  {%- else -%}
    0::numeric
  {%- endif -%}
{%- endmacro %}
