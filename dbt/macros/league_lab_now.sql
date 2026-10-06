{#- IN-5 (Wave I-N): "now" for a view that decides the week by the time. The API sends the league's pinned clock
    (`league_lab.clock`: the test suites' LEAGUE_LAB_NOW) as the setting `league_lab.now` for the one statement
    (api/league_lab_api/db.py `pinned_now`); unset (production, the nightly, psql) it is the database's now(). -#}
{% macro league_lab_now() -%}
coalesce(nullif(current_setting('league_lab.now', true), '')::timestamptz, now())
{%- endmacro %}
