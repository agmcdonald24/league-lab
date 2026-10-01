{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- Plan E4 (Wave E): the feature group `qb_x_offense` (`qbx_`), evaluated by the D1 harness
-- (`league-lab experiment qb_x_offense`; src/league_lab/feature_groups/qb_x_offense.py).
-- Andrew: "are you treating everything equal? an elite QB going down on an elite offense vs a bad QB on a bad offense".
-- v3's QB inputs weigh the starter's quality (pn_qb_prev_ppg_diff: points per start of this week's projected starter
-- minus the usual QB's) and the trees MAY interact it with the Vegas implied total; this group hands them the
-- products explicitly. One row per int_player_week_universe row; the harness joins a group from one table, so the
-- products are materialized here. Every factor is known before kickoff:
--   pn_qb_prev_ppg_diff, pn_qb_is_rookie_or_backup   int_player_week_personnel (as of the week, D5)
--   implied_team_total, total_line                    the closing line (int_player_week_universe, as v3 reads them)
--   prev_team_ppg      the team's points per game over its previous regular season (analytics.dim_game final
--                      scores: fct_team_game carries no points); NULL in 2016 (no 2015)
--   prev_team_epa_play the team's EPA per play over its previous regular season (fct_team_game: (passing_epa +
--                      rushing_epa) / (attempts + sacks_suffered + carries)); NULL in 2016
--   qbx_gap_bucket     pn_qb_prev_ppg_diff in four steps: 2 = big drop (<= -6 points per start: a good starter
--                      replaced by a much worse one), 1 = some drop (-6 .. -2], 0 = like for like (-2 .. +2: the
--                      usual QB, or a backup for a backup), -1 = upgrade (>= +2); NULL = gap unknown
-- A product is NULL when either factor is.
with u as (
    select gsis_id, season, week, {{ kd_team('team') }} as team, implied_team_total, total_line
    from {{ ref('int_player_week_universe') }}
),

team_points as (
    select season, {{ kd_team('home_team') }} as team, home_score as pts from {{ ref('dim_game') }}
    where season_type = 'REG' and home_score is not null
    union all
    select season, {{ kd_team('away_team') }}, away_score from {{ ref('dim_game') }}
    where season_type = 'REG' and away_score is not null
),

prev as (
    select season + 1 as season, team, round(avg(pts)::numeric, 2) as prev_team_ppg
    from team_points group by 1, 2
),

prev_epa as (
    select season + 1 as season, {{ kd_team('team') }} as team,
           round((sum(coalesce(passing_epa, 0) + coalesce(rushing_epa, 0))
                  / nullif(sum(coalesce(attempts, 0) + coalesce(sacks_suffered, 0) + coalesce(carries, 0)), 0))::numeric, 4) as prev_team_epa_play
    from {{ ref('fct_team_game') }}
    where season_type = 'REG'
    group by 1, 2
)

select
    u.gsis_id, u.season, u.week,
    pn.pn_qb_prev_ppg_diff                                                          as qbx_qb_gap,
    p.prev_team_ppg                                                                  as qbx_prev_team_ppg,
    round((pn.pn_qb_prev_ppg_diff * u.implied_team_total)::numeric, 3)              as qbx_gap_x_implied,
    round((pn.pn_qb_prev_ppg_diff * u.total_line)::numeric, 3)                      as qbx_gap_x_total,
    round((pn.pn_qb_prev_ppg_diff * p.prev_team_ppg)::numeric, 3)                   as qbx_gap_x_prev_ppg,
    round((pn.pn_qb_is_rookie_or_backup * u.implied_team_total)::numeric, 3)        as qbx_backup_x_implied,
    e.prev_team_epa_play                                                             as qbx_prev_team_epa_play,
    round((pn.pn_qb_prev_ppg_diff * e.prev_team_epa_play)::numeric, 4)              as qbx_gap_x_prev_epa,
    case when pn.pn_qb_prev_ppg_diff is null then null
         when pn.pn_qb_prev_ppg_diff <= -6 then 2
         when pn.pn_qb_prev_ppg_diff <= -2 then 1
         when pn.pn_qb_prev_ppg_diff < 2 then 0
         else -1 end                                                                 as qbx_gap_bucket
from u
left join {{ ref('int_player_week_personnel') }} as pn using (gsis_id, season, week)
left join prev as p on p.season = u.season and p.team = u.team
left join prev_epa as e on e.season = u.season and e.team = u.team
