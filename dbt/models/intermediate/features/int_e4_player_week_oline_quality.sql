{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- Plan E4 (Wave E): the feature group `oline_quality` (`pn_olq_`), evaluated by the D1 harness
-- (`league-lab experiment oline_quality`; src/league_lab/feature_groups/oline_quality.py).
-- Andrew: "a really good lineman vs a replacement-level one". D5's `oline` counted the line's starters out this week
-- and summed their window snap share - every starter weighed the same. This adds how good the absent starters are,
-- as of the week (int_e4_ol_starter_week): their career starts, draft capital, last season's snaps, and the rank of
-- the best one out. One row per int_player_week_universe row; NULL exactly where int_player_week_personnel's
-- pn_ol_starters_out is NULL (week 1, or week W's injury report not out): unknown is not "nobody out".
with u as (
    select gsis_id, season, week, team, pn_ol_starters_out, pn_ol_snap_share_out
    from {{ ref('int_player_week_personnel') }}
),

tw as (
    select season, week, team,
           count(*) filter (where out_injured)::int                                     as starters_out,
           coalesce(sum(career_starts) filter (where out_injured), 0)::int               as career_starts_out,
           coalesce(sum(draft_score) filter (where out_injured), 0)::int                 as draft_capital_out,
           coalesce(min(quality_rank) filter (where out_injured), 0)::int                as best_out,
           round(coalesce(sum(prev_season_share) filter (where out_injured), 0), 4)      as prev_season_share_out
    from {{ ref('int_e4_ol_starter_week') }}
    group by 1, 2, 3
)

select
    u.gsis_id, u.season, u.week,
    u.pn_ol_starters_out                                                                       as pn_olq_starters_out,
    u.pn_ol_snap_share_out                                                                     as pn_olq_snap_share_out,
    case when u.pn_ol_starters_out is not null then coalesce(tw.career_starts_out, 0) end      as pn_olq_career_starts_out,
    case when u.pn_ol_starters_out is not null then coalesce(tw.draft_capital_out, 0) end      as pn_olq_draft_capital_out,
    case when u.pn_ol_starters_out is not null then coalesce(tw.best_out, 0) end               as pn_olq_best_out,
    case when u.pn_ol_starters_out is not null then coalesce(tw.prev_season_share_out, 0) end  as pn_olq_prev_season_share_out,
    tw.starters_out                                                                            as olq_check_starters_out   -- = pn_ol_starters_out (dbt test)
from u
left join tw on tw.season = u.season and tw.week = u.week and tw.team = u.team
