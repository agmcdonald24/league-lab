{{ config(indexes=[{'columns': ['season', 'week', 'before_week'], 'unique': True}, {'columns': ['season', 'before_week']}], post_hook="analyze {{ this }}") }}
-- "Games before" bridge (C5 performance hotfix): every regular-season week paired with each earlier week of its
-- season. The as-of models join on (season, week) = (season, before_week) - an equality join on a small indexed
-- table - instead of `week < week` between large inputs, which a planner without statistics can turn into a
-- nested loop over hundreds of thousands of rows. ~1.7k rows; the only inequality here is between ~18 weeks.
with weeks as (
    select distinct season, week
    from {{ ref('dim_game') }}
    where season_type = 'REG' and season >= {{ var('seasons_start') }}
)

select w.season, w.week, b.week as before_week
from weeks as w
join weeks as b on b.season = w.season and b.week < w.week
