{% test unique_combination_of_columns(model, combination_of_columns) %}
{# Rows whose combination of columns appears more than once. #}
with grouped as (
    select {{ combination_of_columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ combination_of_columns | join(', ') }}
    having count(*) > 1
)
select * from grouped
{% endtest %}
