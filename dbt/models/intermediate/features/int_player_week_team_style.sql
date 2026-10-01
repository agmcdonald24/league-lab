{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}], post_hook="analyze {{ this }}") }}
{%- set metrics = ['plays_pg', 'sec_per_play', 'neutral_pass_rate', 'proe', 'first_downs_pg', 'top_min_pg',
                   'red_zone_trips_pg', 'points_per_drive', 'scoring_drive_rate', 'yards_per_play',
                   'sacks_per_dropback', 'giveaways_pg'] -%}
-- D4 (plan Iteration 12, feature group team_style; metric team_style v1.0): one row per row of
-- int_player_week_universe (gsis_id, season, week: a rostered QB / RB / WR / TE x a regular-season week his team
-- plays), the team-style numbers of his OWN offense (ts_off_*) and of this week's OPPONENT's defense (ts_def_*:
-- what that defense has allowed), as of the week (int_team_week_style: only games before the week, shrunk toward
-- last season). Team and opponent are the universe's (the weekly roster's team and the schedule's opponent),
-- mapped to one code per franchise (kd_team: OAK -> LV, SD -> LAC, STL -> LA) like the team stats.
--   ts_pace_product  the expected play count of this matchup: offense plays per game x the opponent's plays faced
--                    per game / the league's plays per game (all season to date, as of the week)
--   ts_pass_env      the expected neutral pass rate of this matchup: offense neutral pass rate x the opponent's
--                    neutral pass rate faced / the league's neutral pass rate (log5-style; same windows)
-- A player-week without a team-week row (none today: the universe has no bye weeks) carries NULLs.
with u as (
    select gsis_id, season, week, {{ kd_team('team') }} as team, {{ kd_team('opponent') }} as opponent
    from {{ ref('int_player_week_universe') }}
)

select
    u.gsis_id, u.season, u.week,
    o.off_games                                                    as ts_off_games,
    o.off_asof_week                                                as ts_off_asof_week,
    d.def_games                                                    as ts_def_games,
    d.def_asof_week                                                as ts_def_asof_week
    {%- for m in metrics %}
    {%- for w in ['std', 'l4'] %},
    o.off_{{ m }}_{{ w }}                                          as ts_off_{{ m }}_{{ w }}
    {%- endfor %}
    {%- endfor %}
    {%- for m in metrics %}
    {%- for w in ['std', 'l4'] %},
    d.def_{{ m }}_{{ w }}                                          as ts_def_{{ m }}_{{ w }}
    {%- endfor %}
    {%- endfor %},
    round(o.off_plays_pg_std * d.def_plays_pg_std / nullif(o.league_plays_pg_std, 0), 4)                    as ts_pace_product,
    round(o.off_neutral_pass_rate_std * d.def_neutral_pass_rate_std / nullif(o.league_neutral_pass_rate_std, 0), 4) as ts_pass_env
from u
left join {{ ref('int_team_week_style') }} as o on o.team = u.team and o.season = u.season and o.week = u.week
left join {{ ref('int_team_week_style') }} as d on d.team = u.opponent and d.season = u.season and d.week = u.week
