-- Plan R-14: every WR / TE in a proposed lineup (mart_lineup_recommendation) for the current week whose NFL
-- team plays that week has a cornerback row in mart_cb_matchups, and the row either names the likely
-- cover or says why not ('tight end', 'too few targets', 'no depth chart yet'). The current week is the
-- pages' rule (lib.ui.current_week): the first regular-season week whose last game has not kicked off.
-- Off-season (no such week): nothing to check.
{{ config(severity='error') }}
with lineup_season as (
    select max(season) as season from {{ ref('mart_lineup_recommendation') }}
),

wk as (
    select g.season, min(g.week) as week
    from (
        select season, week, max(kickoff_at) as last_kickoff
        from {{ ref('dim_game') }}
        where season_type = 'REG' and season = (select season from lineup_season)
        group by 1, 2
    ) as g
    where g.last_kickoff > now()
    group by 1
),

starters as (
    select distinct r.league_id, r.roster_id, r.season, r.week, r.slot, r.gsis_id, r.player_name, r.position, p.latest_team
    from {{ ref('mart_lineup_recommendation') }} as r
    join wk using (season, week)
    left join {{ ref('dim_player') }} as p on p.gsis_id = r.gsis_id
    where r.position in ('WR', 'TE') and not r.is_empty_slot
),

with_game as (
    select s.*
    from starters as s
    where exists (
        select 1 from {{ ref('dim_game') }} as g
        where g.season = s.season and g.week = s.week and g.season_type = 'REG' and s.latest_team in (g.home_team, g.away_team)
    )
)

select w.*, m.call_status, m.likely_cover_name
from with_game as w
left join {{ ref('mart_cb_matchups') }} as m on m.gsis_id = w.gsis_id and m.season = w.season and m.week = w.week
where w.gsis_id is null
   or m.gsis_id is null
   or m.call_status is null
   or (m.call_status = 'called' and m.likely_cover_gsis_id is null)
   or (m.call_status <> 'called' and m.likely_cover_gsis_id is not null)
