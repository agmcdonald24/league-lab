{# Team-defense (D/ST) points of one team-game under a Sleeper scoring_settings jsonb (plan R-13).

   def_points(scoring_expr, alias, prefix='')
     scoring_expr : SQL expression yielding the league's scoring_settings jsonb
     alias        : relation carrying <prefix>sacks, interceptions, fumble_recoveries, forced_fumbles,
                    def_tds, st_tds, safeties, blocked_kicks, points_allowed (mart_kd_week's out_* or
                    mart_kd_team_game's columns)

   The defense keys are NOT in scoring_stat_map (that seed maps player keys; it is generated from
   src/league_lab/scoring.py and stays that way). This macro is the SQL twin of
   league_lab.kdef.DEF_STAT_MAP / PTS_ALLOW_BUCKETS; tests/test_kdef.py checks the two list the same
   keys. Keys a league may weight that are not modelled (def_st_ff, def_st_fum_rec, yds_allow_*, ...)
   contribute 0 here and in the projection; docs/METRICS.md lists them. Reconciled against Sleeper's
   own D/ST points for League of Scrubs 2024-2025: 349 of 398 team-weeks exact, 388 within 1 point. #}
{% macro def_points(scoring_expr, alias, prefix='') -%}
  {%- set counts = {'sack': 'sacks', 'int': 'interceptions', 'fum_rec': 'fumble_recoveries', 'ff': 'forced_fumbles',
                    'def_td': 'def_tds', 'def_st_td': 'st_tds', 'safe': 'safeties', 'blk_kick': 'blocked_kicks'} -%}
  {%- set buckets = [('pts_allow_0', 0, 0), ('pts_allow_1_6', 1, 6), ('pts_allow_7_13', 7, 13), ('pts_allow_14_20', 14, 20),
                     ('pts_allow_21_27', 21, 27), ('pts_allow_28_34', 28, 34), ('pts_allow_35p', 35, none)] -%}
  {%- set terms = [] -%}
  {%- for key, col in counts.items() -%}
    {%- do terms.append("coalesce((" ~ scoring_expr ~ " ->> '" ~ key ~ "')::numeric, 0) * coalesce(" ~ alias ~ "." ~ prefix ~ col ~ ", 0)") -%}
  {%- endfor -%}
  {%- for key, lo, hi in buckets -%}
    {%- set pa = alias ~ "." ~ prefix ~ "points_allowed" -%}
    {%- set cond = pa ~ " >= " ~ lo ~ (" and " ~ pa ~ " <= " ~ hi if hi is not none else "") -%}
    {%- do terms.append("coalesce((" ~ scoring_expr ~ " ->> '" ~ key ~ "')::numeric, 0) * (case when " ~ cond ~ " then 1 else 0 end)") -%}
  {%- endfor -%}
  round(({{ terms | join(' + ') }})::numeric, 2)
{%- endmacro %}
