{# The stat-line components projection v2 forecasts per player-week and then prices under any
   league's scoring map (plan M-01). One list, used by the as-of models and the features mart, so
   a new component is added in one place. #}
{% macro component_stats() %}
  {{ return(['targets', 'receptions', 'receiving_yards', 'receiving_tds', 'carries', 'rushing_yards', 'rushing_tds',
             'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions', 'fumbles_lost_total',
             'red_zone_targets', 'red_zone_carries']) }}
{% endmacro %}
