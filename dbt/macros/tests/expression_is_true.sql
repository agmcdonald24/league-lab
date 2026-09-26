{% test expression_is_true(model, expression, condition="1=1", column_name=none) %}
{# Rows where `expression` is false (rows failing `condition` are ignored). #}
select *
from {{ model }}
where ({{ condition }}) and not ({{ expression }})
{% endtest %}
