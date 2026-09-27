-- Draft picks with the player's regular-season outcome under that league's *current* scoring
-- (points recomputed from NFL stats in fct_player_game_league for the chain's current season, plan
-- S-01a), so draft value can be reviewed after the fact and drafts from different years compare.
with picks as (
    select * from {{ ref('stg_sleeper__draft_picks') }}
),

l as (select league_id, chain_id, season, scoring_settings from {{ ref('dim_league_season') }}),

season_points as (
    select
        lpw.league_id, lpw.sleeper_player_id,
        sum(lpw.points_observed) filter (where lpw.is_starter) as points_started_for_any_roster,
        sum(lpw.points_observed) as points_rostered_any
    from {{ ref('league_player_week') }} as lpw
    where lpw.is_scored_week
    group by 1, 2
),

-- keyed by the chain's current league-season (chain_id = the newest season's league_id)
nfl_points as (
    select pg.league_id, pg.gsis_id, pg.season, sum(pg.points) as points_current_scoring, count(*) filter (where played) as games_played
    from {{ ref('fct_player_game_league') }} as pg
    where pg.season_type = 'REG'
    group by 1, 2, 3
)

select
    p.league_id, l.season, p.draft_id, p.pick_no, p.round, p.draft_slot, p.roster_id,
    m.team_name, m.manager_name,
    p.sleeper_player_id,
    coalesce(sp.full_name, p.sleeper_player_id) as player_name,
    coalesce(sp.position, p.drafted_position)   as position,
    p.drafted_team,
    p.is_keeper,
    idm.gsis_id,
    np.games_played                             as nfl_reg_games_played,
    np.points_current_scoring                   as nfl_reg_points_current_scoring,
    spt.points_rostered_any,
    spt.points_started_for_any_roster,
    rank() over (partition by p.league_id, coalesce(sp.position, p.drafted_position) order by np.points_current_scoring desc nulls last) as position_rank_by_points,
    rank() over (partition by p.league_id, coalesce(sp.position, p.drafted_position) order by p.pick_no) as position_rank_by_pick
from picks as p
join l using (league_id)
left join {{ ref('stg_sleeper__players') }} as sp using (sleeper_player_id)
left join {{ ref('player_id_map') }} as idm on idm.sleeper_id = p.sleeper_player_id
left join nfl_points as np on np.league_id = l.chain_id and np.gsis_id = idm.gsis_id and np.season = l.season
left join season_points as spt on spt.league_id = p.league_id and spt.sleeper_player_id = p.sleeper_player_id
left join {{ ref('dim_league_member') }} as m on m.league_id = p.league_id and m.roster_id = p.roster_id
