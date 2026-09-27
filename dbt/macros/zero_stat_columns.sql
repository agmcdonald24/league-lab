{# Emit `0 as <column>` for every weekly-stat column the scoring seed references except the ones
   named, so a relation that carries only some components can still be priced with league_points()
   (a projection line has no kicking or 2-pt columns, say). Uses the same seed as league_points. #}
{% macro zero_stat_columns(have) -%}
  {%- if execute -%}
    {%- set rows = run_query("select stat_expression from " ~ ref('scoring_stat_map')) -%}
    {%- set cols = [] -%}
    {%- for row in rows.rows -%}
      {%- set expr = row[0] -%}
      {%- if ':' in expr -%}
        {%- set parts = [expr.split(':')[0]] -%}
      {%- else -%}
        {%- set parts = expr.split('+') -%}
      {%- endif -%}
      {%- for part in parts -%}
        {%- set c = part | trim -%}
        {%- if c not in have and c not in cols -%}{%- do cols.append(c) -%}{%- endif -%}
      {%- endfor -%}
    {%- endfor -%}
    {%- for c in cols -%}0 as {{ c }}{{ ", " if not loop.last }}{%- endfor -%}
  {%- else -%}
    0 as _no_stats
  {%- endif -%}
{%- endmacro %}
