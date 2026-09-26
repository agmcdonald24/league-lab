-- Coverage stats per defender x season (REG), season-to-date, from PFR advanced defense (2018+).
select
    gsis_id, season, max(defender_name) as defender_name, max(position) as position,
    string_agg(distinct team, ',' order by team) as teams,
    count(*) as games,
    sum(def_targets) as targets, sum(def_completions_allowed) as completions_allowed,
    case when sum(def_targets) > 0 then round((sum(def_completions_allowed) / sum(def_targets))::numeric, 3) end as completion_pct_allowed,
    sum(def_yards_allowed) as yards_allowed,
    case when sum(def_targets) > 0 then round((sum(def_yards_allowed) / sum(def_targets))::numeric, 2) end as yards_per_target_allowed,
    sum(def_receiving_td_allowed) as tds_allowed,
    sum(def_ints) as interceptions,
    round(avg(def_passer_rating_allowed) filter (where def_targets > 0)::numeric, 1) as avg_passer_rating_allowed_when_targeted,
    case when sum(def_targets) > 0 then round((sum(def_adot * def_targets) / sum(def_targets))::numeric, 1) end as adot_allowed,
    sum(def_yards_after_catch) as yac_allowed,
    sum(def_missed_tackles) as missed_tackles,
    round((sum(def_targets) / count(*))::numeric, 2) as targets_per_game
from {{ ref('int_defender_game_coverage') }}
where season_type = 'REG'
group by 1, 2
