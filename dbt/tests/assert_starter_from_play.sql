-- IP-1 (Wave I-P): int_pn_team_game's starter differs from the schedule's listing only where the play data says the
-- listing was wrong (docs/METRICS.md § "The quarterback weak spot (IP-1)"). Returns offending team-games:
--   * a played game whose starter is not the listing although the listed QB threw a pass for the team, or whose
--     corrected starter threw no pass for the team;
--   * an unplayed game whose starter is not the listing although the guard does not apply (the listing does not repeat
--     the team's newest played game's listing, or that listing was right).
-- IP-1 fix round: under var pn_starter_stale_rule (st1.1) instead, a pick other than the listing is the newest played
-- game's dropback leader, for a listing that game already carried and that its listed QB did not throw in.
-- Both off: the starter is the listing everywhere.
{{ config(severity='error') }}
with t as (
    select * from {{ ref('int_pn_team_game') }}
    where starter_source = 'schedule'     -- ---- IQ-2: a hand-kept override (unplayed games only) is checked by assert_starter_override_*
),

passes as (
    select game_id, {{ kd_team('team') }} as team, gsis_id
    from {{ ref('fct_player_game') }}
    where season_type = 'REG' and coalesce(attempts, 0) > 0
),

prev as (
    select t.*,
           (array_agg(t.listed_qb_id) filter (where t.is_played) over w)[1]   as prev_listed,
           (array_agg(t.starting_qb_id) filter (where t.is_played) over w)[1] as prev_starter
    from t
    window w as (partition by t.team, t.season order by t.week desc rows between 1 following and unbounded following)
)

{%- if var('pn_starter_from_play', false) %}
select p.season, p.week, p.team, p.listed_qb_id, p.starting_qb_id, 'played: corrected although the listed QB threw' as problem
from prev as p
where p.is_played and p.starting_qb_id is distinct from p.listed_qb_id
  and exists (select 1 from passes as x where x.game_id = p.game_id and x.team = p.team and x.gsis_id = p.listed_qb_id)

union all
select p.season, p.week, p.team, p.listed_qb_id, p.starting_qb_id, 'played: the corrected starter threw no pass'
from prev as p
where p.is_played and p.starting_qb_id is distinct from p.listed_qb_id
  and not exists (select 1 from passes as x where x.game_id = p.game_id and x.team = p.team and x.gsis_id = p.starting_qb_id)

union all
select p.season, p.week, p.team, p.listed_qb_id, p.starting_qb_id, 'unplayed: corrected without a contradicted repeat listing'
from prev as p
where not p.is_played and p.starting_qb_id is distinct from p.listed_qb_id
  and not (p.listed_qb_id = p.prev_listed and p.prev_starter is distinct from p.prev_listed
           and p.starting_qb_id is not distinct from p.prev_starter)
{%- elif var('pn_starter_stale_rule', false) %}
-- ---- IP-1 fix round, st1.1
select p.season, p.week, p.team, p.listed_qb_id, p.starting_qb_id, 'st1.1: overruled without a repeated, unthrown listing' as problem
from prev as p
where p.starting_qb_id is distinct from p.listed_qb_id
  and not (p.listed_qb_id = p.prev_listed
           and not exists (select 1 from passes as x
                           where x.team = p.team and x.gsis_id = p.listed_qb_id
                             and x.game_id = (select g.game_id from t as g where g.team = p.team and g.season = p.season
                                              and g.is_played and g.week < p.week order by g.week desc limit 1)))
-- ---- end IP-1 fix round
{%- else %}
select season, week, team, listed_qb_id, starting_qb_id, 'switch off: the starter is not the listing' as problem
from t
where starting_qb_id is distinct from listed_qb_id
{%- endif %}
