-- Keeper facts for every currently rostered player in each current league-season: how he was
-- acquired (draft round/pick or waiver/FA), season-to-date production and positional rank, and
-- the expected-points signal. League keeper *rules* (cost, eligibility) are applied by the reader.
with cur as (select league_id, season from {{ ref('dim_league_season') }} where is_current_season),

members as (
    select * from {{ ref('mart_league_roster_membership') }}
    where league_id in (select league_id from cur)
),

drafted as (
    select league_id, sleeper_player_id, round as draft_round, pick_no as draft_pick, roster_id as drafted_by_roster_id, is_keeper
    from {{ ref('stg_sleeper__draft_picks') }}
    where league_id in (select league_id from cur)
),

std as (
    select gsis_id, season, position, games_played, points_current_scoring, points_current_scoring_per_game,
           rank() over (partition by season, position order by points_current_scoring desc nulls last) as position_rank_std,
           rank() over (partition by season, position order by points_current_scoring_per_game desc nulls last) as position_rank_ppg
    from {{ ref('mart_player_season') }}
    where season_type = 'REG' and position in ('QB', 'RB', 'WR', 'TE', 'K')
),

exp as (
    select gsis_id, season, expected_per_game, diff_per_game from {{ ref('mart_player_expected_season') }}
)

select
    m.league_id, m.season, m.roster_id, m.team_name, m.manager_name,
    m.sleeper_player_id, m.gsis_id, m.player_name, m.position, m.nfl_team,
    m.is_current_starter, m.is_on_ir,
    d.draft_round, d.draft_pick, d.drafted_by_roster_id,
    d.drafted_by_roster_id is not null and d.drafted_by_roster_id <> m.roster_id as acquired_after_draft,
    d.sleeper_player_id is null as undrafted_or_waiver,
    coalesce(d.is_keeper, false) as was_keeper,
    s.games_played, s.points_current_scoring as points_std, s.points_current_scoring_per_game as ppg_std,
    s.position_rank_std, s.position_rank_ppg,
    e.expected_per_game, e.diff_per_game
from members as m
left join drafted as d using (league_id, sleeper_player_id)
left join std as s on s.gsis_id = m.gsis_id and s.season = m.season
left join exp as e on e.gsis_id = m.gsis_id and e.season = m.season
