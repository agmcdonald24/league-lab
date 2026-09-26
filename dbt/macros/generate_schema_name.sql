{# Use the configured schema name verbatim (staging / intermediate / analytics) instead of
   dbt's default "<target schema>_<custom>" concatenation. The target schema is only used
   when a model sets no +schema. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
