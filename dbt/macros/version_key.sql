{#- IP-1 fix round 2 (Wave I-P; the review's L4): a model version as an integer array, so versions compare by their
    numbers -- 'v3.10' > 'v3.9' (as text 'v3.10' < 'v3.9'). Every run of non-digits is a separator: 'v3.4' -> {3,4},
    'v3.4+wx' -> {3,4}, 'kd1.0' -> {1,0}; no digit -> NULL. -#}
{% macro version_key(expr) -%}
(regexp_split_to_array(nullif(trim(both '.' from regexp_replace({{ expr }}, '[^0-9]+', '.', 'g')), ''), '\.')::int[])
{%- endmacro %}
