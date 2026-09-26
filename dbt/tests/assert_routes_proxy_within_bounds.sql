-- A routes proxy can never exceed the team's participation-covered dropbacks in the same game,
-- and a receiving position's targets in a covered game should not exceed its dropbacks on the
-- field by more than a couple of plays (participation lists occasionally miss a player).
{{ config(severity='warn') }}
select gsis_id, game_id, position, routes_proxy, team_dropbacks_with_participation, targets
from {{ ref('fct_player_game') }}
where routes_proxy is not null
  and (routes_proxy > team_dropbacks_with_participation or targets > routes_proxy + 2)
