{# One code per franchise for the K / D/ST models (plan R-13): the schedule says OAK (to 2019) and SD
   (2016) where the team and player stats files already say LV and LAC. Today's code wins. #}
{% macro kd_team(expr) -%}
  case {{ expr }} when 'OAK' then 'LV' when 'SD' then 'LAC' when 'STL' then 'LA' else {{ expr }} end
{%- endmacro %}
