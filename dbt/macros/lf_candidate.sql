{#- ---- IX-6 (Wave I-X), lf2.0: a per-game value under the study's candidate (docs/METRICS.md § "Does handling a
    shortened game make the projection better?"). P1: a marked game's value leaves the window's average; P3: it is
    scaled to a full game (rf.lf_scale); otherwise the expression as is. -#}
{%- macro lfv(expr, mode) -%}
{%- if mode == 'p1' -%}case when rf.lf_mark then null else {{ expr }} end
{%- elif mode == 'p3' -%}({{ expr }}) * rf.lf_scale
{%- else -%}{{ expr }}{%- endif -%}
{%- endmacro %}
