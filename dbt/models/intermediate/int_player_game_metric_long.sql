-- One row per player-game-metric (regular season, games the player actually played), as a
-- numerator/denominator pair so windows can be summed then divided. Position eligibility per
-- metric comes from the trend_metrics seed.
with g as (
    select
        p.gsis_id, p.season, p.week, p.game_id, p.player_name, p.position, p.team,
        row_number() over (partition by p.gsis_id, p.season order by p.week) as game_no,
        count(*) over (partition by p.gsis_id, p.season) as games,
        p.targets, p.team_targets, p.carries, p.team_carries, p.receiving_air_yards, p.team_air_yards,
        p.offense_snap_pct, p.snaps_known, p.attempts,
        p.first_read_targets, p.team_first_read_targets, p.team_charted_targets,
        p.routes_proxy, p.team_dropbacks_with_participation,
        p.points_current_scoring, e.points_expected
    from {{ ref('fct_player_game') }} as p
    left join {{ ref('int_expected_points_week') }} as e on e.gsis_id = p.gsis_id and e.game_id = p.game_id
    where p.season_type = 'REG' and p.played and p.position in ('QB', 'RB', 'WR', 'TE')
),

long as (
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'target_share' as metric, targets::numeric as num, team_targets::numeric as den from g
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'air_yards_share', receiving_air_yards::numeric, team_air_yards::numeric from g
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'adot', receiving_air_yards::numeric, targets::numeric from g
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'targets_per_game', targets::numeric, 1 from g
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'carry_share', carries::numeric, team_carries::numeric from g
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'carries_per_game', carries::numeric, 1 from g
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'snap_share', offense_snap_pct::numeric, 1 from g where snaps_known
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'expected_points', points_expected, 1 from g where points_expected is not null
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'points', points_current_scoring, 1 from g
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'pass_attempts', attempts::numeric, 1 from g
    -- Phase 2: charted games only (first read), participation games only (routes proxy)
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'first_read_share', first_read_targets::numeric, team_first_read_targets::numeric from g where team_charted_targets > 0
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'route_participation', routes_proxy::numeric, team_dropbacks_with_participation::numeric from g where routes_proxy is not null
    union all
    select gsis_id, season, week, game_id, player_name, position, team, game_no, games,
           'tprr_proxy', targets::numeric, routes_proxy::numeric from g where routes_proxy is not null
)

select l.*
from long as l
join {{ ref('trend_metrics') }} as t on t.metric = l.metric
where position(l.position in t.positions) > 0
