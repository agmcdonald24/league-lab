-- Canonical player dimension keyed on gsis_id (nflverse players) with resolved provider ids.
-- Identity persists across trades and position changes; team is the *latest* team and must
-- not be used historically (use player_team_history / fct_player_game.team instead).
select
    p.gsis_id,
    p.display_name                           as player_name,
    p.first_name,
    p.last_name,
    p.position,
    p.position_group,
    p.position in ('QB', 'RB', 'WR', 'TE', 'K') as is_skill_or_kicker,
    p.latest_team,
    p.status,
    p.birth_date,
    p.height,
    p.weight,
    p.college_name,
    p.rookie_season,
    p.last_season,
    p.draft_year,
    p.draft_round,
    p.draft_pick,
    p.draft_team,
    p.headshot_url,
    m.sleeper_id,
    coalesce(m.pfr_id, p.pfr_id)             as pfr_id,
    p.esb_id,
    p.espn_id,
    m.sleeper_id is not null                 as has_sleeper_id
from {{ ref('stg_nflverse__players') }} as p
left join {{ ref('player_id_map') }} as m using (gsis_id)
