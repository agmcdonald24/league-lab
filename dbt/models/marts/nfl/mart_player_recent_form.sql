{{ config(indexes=[{'columns': ['season', 'season_type', 'player_name']}]) }}
-- As-of each game: the player's last-3 and last-5 appearance-game windows (same season and
-- season type, ordered by week) with shared numerator/denominator games, next to season-to-date.
-- Grain: player x game. Used for "recent vs season" usage comparisons (plan §6).
-- ---- IX-6 (Wave I-X), lf2.0: the study's candidates (docs/METRICS.md § "Does handling a shortened game make the
-- projection better?"), var lf_candidate = p1a | p1b | p2a | p2b | p3a | p3b; unset (the default): the SQL as before.
{%- set lf_cand = (var('lf_candidate', '') or '') | string | lower %}
{%- set lf_mode = lf_cand[:2] if lf_cand in ['p1a', 'p1b', 'p2a', 'p2b', 'p3a', 'p3b'] else '' %}
{%- set lf_mark = 'coalesce(lf.left_early_' ~ lf_cand[2:] ~ ', false)' %}
with pg as (
    select
        f.gsis_id, f.game_id, f.season, f.season_type, f.week, f.team, f.player_name, f.position, f.played,
        f.targets, f.receptions, f.receiving_yards, f.receiving_air_yards, f.carries, f.rushing_yards,
        f.attempts, f.passing_yards,
        {%- if lf_mode in ['p1', 'p3'] %}
        -- P1 / P3: the share windows' team totals weighted by his snap share (lf1.0's estimate)
        f.team_targets * case when f.snaps_known and f.offense_snap_pct > 0 then f.offense_snap_pct else 1 end as team_targets,
        f.team_carries * case when f.snaps_known and f.offense_snap_pct > 0 then f.offense_snap_pct else 1 end as team_carries,
        {%- else %}
        f.team_targets, f.team_carries,
        {%- endif %}
        f.team_air_yards, f.team_dropbacks_excl_scrambles,
        f.offense_snaps,
        {%- if lf_mode == 'p1' %}
        case when {{ lf_mark }} then null else f.offense_snap_pct end as offense_snap_pct,
        f.snaps_known,
        case when {{ lf_mark }} then null else f.points_current_scoring end as points_current_scoring,
        {%- elif lf_mode == 'p3' %}
        case when {{ lf_mark }} then lf.usual_snap_pct else f.offense_snap_pct end as offense_snap_pct,
        f.snaps_known,
        f.points_current_scoring * case when {{ lf_mark }} and f.offense_snap_pct > 0 and lf.usual_snap_pct > 0
                                        then lf.usual_snap_pct / f.offense_snap_pct else 1 end as points_current_scoring,
        {%- else %}
        f.offense_snap_pct, f.snaps_known, f.points_current_scoring,
        {%- endif %}
        {%- if lf_mode %}
        {{ lf_mark }} as lf_mark,
        case when {{ lf_mark }} and f.offense_snap_pct > 0 and lf.usual_snap_pct > 0
             then lf.usual_snap_pct / f.offense_snap_pct else 1 end as lf_scale,
        {%- endif %}
        f.first_read_targets, f.team_first_read_targets, f.team_charted_targets, f.routes_proxy, f.team_dropbacks_with_participation
    from {{ ref('fct_player_game') }} as f
    {%- if lf_mode %}
    left join {{ ref('int_player_game_on_field') }} as lf on lf.gsis_id = f.gsis_id and lf.game_id = f.game_id
    {%- endif %}
    where f.played
    {%- if lf_mode == 'p2' %}
      and not {{ lf_mark }}                 -- P2: a marked game is no game of his windows
    {%- endif %}
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
        {%- if lf_mode == 'p1' %}
        count(points_current_scoring) over (partition by gsis_id, season, season_type order by week rows between {{ n - 1 }} preceding and current row) as lf_points_games_l{{ n }},
        {%- endif %}
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
        {%- if lf_mode == 'p1' %},
        count(points_current_scoring) over (partition by gsis_id, season, season_type order by week) as lf_points_games_std
        {%- endif %}
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
    {%- if lf_mode == 'p1' %}
    round(points_l{{ n }} / nullif(lf_points_games_l{{ n }}, 0), 2) as points_per_game_l{{ n }},
    {%- else %}
    round(points_l{{ n }} / games_l{{ n }}, 2) as points_per_game_l{{ n }},
    {%- endif %}
    case when team_first_read_targets_l{{ n }} > 0 then round(first_read_targets_l{{ n }}::numeric / team_first_read_targets_l{{ n }}, 4) end as first_read_share_l{{ n }},
    case when team_dropbacks_part_l{{ n }} > 0 then round(routes_proxy_l{{ n }}::numeric / team_dropbacks_part_l{{ n }}, 4) end as route_participation_l{{ n }},
    {% endfor %}
    case when team_first_read_targets_std > 0 then round(first_read_targets_std::numeric / team_first_read_targets_std, 4) end as first_read_share_std,
    targets_std, team_targets_std,
    case when team_targets_std > 0 then round(targets_std::numeric / team_targets_std, 4) end as target_share_std,
    carries_std, team_carries_std,
    case when team_carries_std > 0 then round(carries_std::numeric / team_carries_std, 4) end as carry_share_std,
    {%- if lf_mode == 'p1' %}
    round(points_std / nullif(lf_points_games_std, 0), 2) as points_per_game_std
    {%- else %}
    round(points_std / game_no, 2) as points_per_game_std
    {%- endif %}
    {%- if lf_mode %}, lf_mark, lf_scale{% endif %}
from w
