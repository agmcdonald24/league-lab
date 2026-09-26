-- The waiver-wire / trade-target base table: every QB/RB/WR/TE/K with a Sleeper id who is on an
-- NFL roster this season, x each *current* league season, with who rosters them (NULL = free agent),
-- season-to-date usage, latest recent form, expected-points gap, injury and next matchup.
with cal as (select * from {{ ref('int_nfl_calendar') }}),

leagues as (
    select league_id, season from {{ ref('dim_league_season') }} where is_current_season
),

players as (
    select p.gsis_id, p.sleeper_id, p.player_name, p.position
    from {{ ref('dim_player') }} as p
    where p.sleeper_id is not null and p.position in ('QB', 'RB', 'WR', 'TE', 'K')
),

std as (
    select gsis_id, games_played, targets, carries, attempts, target_share, carry_share, air_yards_share, adot,
           avg_offense_snap_pct, targets_per_game, carries_per_game, points_current_scoring,
           points_current_scoring_per_game, receiving_tds, rushing_tds, passing_tds, teams
    from {{ ref('mart_player_season') }}
    where season = (select season from cal) and season_type = 'REG'
),

recent as (
    select distinct on (gsis_id) gsis_id, week as as_of_week, games_l3, target_share_l3, carry_share_l3, snap_pct_l3,
           points_per_game_l3, target_share_l5, points_per_game_l5, targets_l3, carries_l3,
           first_read_share_l3, first_read_share_std, route_participation_l3
    from {{ ref('mart_player_recent_form') }}
    where season = (select season from cal) and season_type = 'REG'
    order by gsis_id, week desc
),

exp as (
    select gsis_id, points_expected, expected_per_game, diff_per_game, games_with_expected
    from {{ ref('mart_player_expected_season') }}
    where season = (select season from cal)
),

nm as (select * from {{ ref('mart_player_next_matchup') }}),

owned as (
    select league_id, sleeper_player_id, roster_id, team_name, manager_name, is_current_starter, is_on_ir
    from {{ ref('mart_league_roster_membership') }}
)

select
    lg.league_id,
    lg.season,
    p.gsis_id,
    p.sleeper_id,
    p.player_name,
    p.position,
    nm.team                                    as nfl_team,
    nm.roster_status,
    o.roster_id                                as rostered_by_roster_id,
    o.team_name                                as rostered_by_team,
    o.manager_name                             as rostered_by_manager,
    o.roster_id is null                        as is_free_agent,
    o.is_current_starter,
    o.is_on_ir,
    std.games_played, std.targets, std.carries, std.attempts, std.targets_per_game, std.carries_per_game,
    std.target_share, std.carry_share, std.air_yards_share, std.adot, std.avg_offense_snap_pct,
    std.points_current_scoring                 as points_std,
    std.points_current_scoring_per_game        as ppg_std,
    recent.as_of_week, recent.games_l3, recent.targets_l3, recent.carries_l3,
    recent.target_share_l3, recent.carry_share_l3, recent.snap_pct_l3, recent.points_per_game_l3,
    recent.first_read_share_l3, recent.first_read_share_std, recent.route_participation_l3,
    recent.target_share_l5, recent.points_per_game_l5,
    round(recent.target_share_l3 - std.target_share, 4)   as target_share_trend,
    round(recent.carry_share_l3 - std.carry_share, 4)     as carry_share_trend,
    exp.expected_per_game, exp.diff_per_game, exp.games_with_expected,
    nm.next_week, nm.opponent, nm.is_home, nm.is_bye, nm.opp_rank_std, nm.opp_rank_l4, nm.opp_points_allowed_pg_std,
    nm.injury_status, nm.injury, nm.practice_status, nm.depth_rank, nm.depth_pos
from leagues as lg
cross join players as p
join nm using (gsis_id)
left join std using (gsis_id)
left join recent using (gsis_id)
left join exp using (gsis_id)
left join owned as o on o.league_id = lg.league_id and o.sleeper_player_id = p.sleeper_id
