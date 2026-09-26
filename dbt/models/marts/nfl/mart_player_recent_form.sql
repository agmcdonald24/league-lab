{{ config(indexes=[{'columns': ['season', 'season_type', 'player_name']}]) }}
-- As-of each game: the player's last-3 and last-5 appearance-game windows (same season and
-- season type, ordered by week) with shared numerator/denominator games, next to season-to-date.
-- Grain: player x game. Used for "recent vs season" usage comparisons (plan §6).
with pg as (
    select
        gsis_id, game_id, season, season_type, week, team, player_name, position, played,
        targets, receptions, receiving_yards, receiving_air_yards, carries, rushing_yards,
        attempts, passing_yards, team_targets, team_carries, team_air_yards, team_dropbacks_excl_scrambles,
        offense_snaps, offense_snap_pct, snaps_known, points_current_scoring,
        first_read_targets, team_first_read_targets, team_charted_targets, routes_proxy, team_dropbacks_with_participation
    from {{ ref('fct_player_game') }}
    where played
),

w as (
    select
        *,
        row_number() over (partition by gsis_id, season, season_type order by week) as game_no,
        {% for n in [3, 5] %}
        sum(targets)      over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as targets_l{{ n }},
        sum(team_targets) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as team_targets_l{{ n }},
        sum(carries)      over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as carries_l{{ n }},
        sum(team_carries) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as team_carries_l{{ n }},
        sum(receiving_air_yards) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as air_yards_l{{ n }},
        sum(team_air_yards)      over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as team_air_yards_l{{ n }},
        avg(offense_snap_pct) filter (where snaps_known) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as snap_pct_l{{ n }},
        sum(points_current_scoring) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as points_l{{ n }},
        count(*)          over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as games_l{{ n }},
        sum(first_read_targets) filter (where team_charted_targets > 0) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as first_read_targets_l{{ n }},
        sum(team_first_read_targets) filter (where team_charted_targets > 0) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as team_first_read_targets_l{{ n }},
        sum(routes_proxy) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as routes_proxy_l{{ n }},
        sum(team_dropbacks_with_participation) filter (where routes_proxy is not null) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as team_dropbacks_part_l{{ n }},
        {% endfor %}
        sum(first_read_targets) filter (where team_charted_targets > 0) over (partition by gsis_id, season, season_type order by week) as first_read_targets_std,
        sum(team_first_read_targets) filter (where team_charted_targets > 0) over (partition by gsis_id, season, season_type order by week) as team_first_read_targets_std,
        sum(targets)      over (partition by gsis_id, season, season_type order by week) as targets_std,
        sum(team_targets) over (partition by gsis_id, season, season_type order by week) as team_targets_std,
        sum(carries)      over (partition by gsis_id, season, season_type order by week) as carries_std,
        sum(team_carries) over (partition by gsis_id, season, season_type order by week) as team_carries_std,
        sum(points_current_scoring) over (partition by gsis_id, season, season_type order by week) as points_std
    from pg
)

select
    gsis_id, game_id, season, season_type, week, game_no, team, player_name, position,
    targets, carries, receiving_air_yards, offense_snap_pct, points_current_scoring,
    {% for n in [3, 5] %}
    games_l{{ n }},
    targets_l{{ n }}, team_targets_l{{ n }},
    case when team_targets_l{{ n }} > 0 then round(targets_l{{ n }}::numeric / team_targets_l{{ n }}, 4) end as target_share_l{{ n }},
    carries_l{{ n }}, team_carries_l{{ n }},
    case when team_carries_l{{ n }} > 0 then round(carries_l{{ n }}::numeric / team_carries_l{{ n }}, 4) end as carry_share_l{{ n }},
    case when team_air_yards_l{{ n }} <> 0 then round(air_yards_l{{ n }}::numeric / team_air_yards_l{{ n }}, 4) end as air_yards_share_l{{ n }},
    round(snap_pct_l{{ n }}::numeric, 4) as snap_pct_l{{ n }},
    round(points_l{{ n }} / games_l{{ n }}, 2) as points_per_game_l{{ n }},
    case when team_first_read_targets_l{{ n }} > 0 then round(first_read_targets_l{{ n }}::numeric / team_first_read_targets_l{{ n }}, 4) end as first_read_share_l{{ n }},
    case when team_dropbacks_part_l{{ n }} > 0 then round(routes_proxy_l{{ n }}::numeric / team_dropbacks_part_l{{ n }}, 4) end as route_participation_l{{ n }},
    {% endfor %}
    case when team_first_read_targets_std > 0 then round(first_read_targets_std::numeric / team_first_read_targets_std, 4) end as first_read_share_std,
    targets_std, team_targets_std,
    case when team_targets_std > 0 then round(targets_std::numeric / team_targets_std, 4) end as target_share_std,
    carries_std, team_carries_std,
    case when team_carries_std > 0 then round(carries_std::numeric / team_carries_std, 4) end as carry_share_std,
    round(points_std / game_no, 2) as points_per_game_std
from w
