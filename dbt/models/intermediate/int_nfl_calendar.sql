-- Where the current NFL season stands: last fully-final regular-season week and the next week with
-- unplayed games. One row.
with cur as (select max(season) as season from {{ ref('dim_game') }} where is_final),
weeks as (
    select g.season, g.week,
           bool_and(g.is_final) as all_final, bool_or(g.is_final) as any_final, min(g.kickoff_at) as first_kickoff
    from {{ ref('dim_game') }} as g join cur using (season)
    where g.season_type = 'REG'
    group by 1, 2
)
select
    season,
    max(week) filter (where all_final)                        as last_completed_week,
    min(week) filter (where not all_final)                    as next_week,
    max(week) filter (where any_final)                        as latest_week_with_results,
    (select min(first_kickoff) from weeks w2 where not w2.all_final) as next_week_first_kickoff
from weeks
group by season
