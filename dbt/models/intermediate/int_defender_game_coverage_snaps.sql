{{ config(indexes=[{'columns': ['gsis_id', 'game_id'], 'unique': True}, {'columns': ['season', 'team']}], post_hook="analyze {{ this }}") }}
-- Coverage snaps per defender-game (plan R-14): the pass plays (the opponent's dropbacks) he was on the
-- field for. From participation (play level) where the game has an on-field list; otherwise estimated as
-- his share of his team's defensive snaps (PFR snap counts) x the opponent's dropbacks in that game. A
-- season's participation file arrives after its postseason, so the current season is always estimated
-- (validated against participation on 2025 in docs/METRICS.md § Cornerback matchups).
-- Keyed to the games PFR's advanced defense charts (the coverage numerators: targets, yards, TDs allowed
-- as the primary defender), 2018+, so numerator and denominator share the same games.
with cov as (
    select c.*, {{ kd_team('c.team') }} as team_code
    from {{ ref('int_defender_game_coverage') }} as c
),

snap_rows as (
    select s.pfr_player_id, s.game_id, {{ kd_team('s.team') }} as team, s.position as snap_position, s.defense_snaps,
           max(s.defense_snaps) over (partition by s.game_id, s.team) as team_defense_snaps   -- before the id map drops anyone
    from {{ ref('stg_nflverse__snap_counts') }} as s
    where s.season >= 2018
),

snaps as (
    select m.gsis_id, r.game_id, r.team, r.snap_position, r.defense_snaps, r.team_defense_snaps
    from snap_rows as r
    join {{ ref('int_pfr_gsis_map') }} as m on m.pfr_id = r.pfr_player_id
),

-- the offense each defender faced in that game: its dropbacks and how many carry an on-field list
opp as (
    select game_id, team as offense, dropbacks, dropbacks_with_participation
    from {{ ref('int_team_game_pbp') }}
    where season >= 2018
),

onfield as (
    select x.gsis_id, p.game_id, count(distinct p.play_id) as dropbacks_on_field
    from {{ ref('fct_play') }} as p
    join {{ ref('stg_nflverse__pbp_participation') }} as pa on pa.game_id = p.game_id and pa.play_id = p.play_id
    cross join lateral unnest(string_to_array(pa.defense_players, ';')) as x(gsis_id)
    where p.season >= 2018 and p.is_dropback and not p.is_no_play and p.posteam is not null
      and pa.defense_players is not null and x.gsis_id <> ''
    group by 1, 2
),

joined as (
    select
        c.gsis_id, c.game_id, c.season, c.season_type, c.week, c.team_code as team, {{ kd_team('c.opponent') }} as opponent,
        c.defender_name, c.position,
        s.snap_position, s.defense_snaps, s.team_defense_snaps,
        o.dropbacks                                                    as opp_dropbacks,
        o.dropbacks_with_participation                                 as opp_dropbacks_with_participation,
        case when o.dropbacks_with_participation > 0 then coalesce(f.dropbacks_on_field, 0) end as coverage_snaps_on_field,
        case when s.team_defense_snaps > 0 and o.dropbacks is not null
             then round(s.defense_snaps::numeric / s.team_defense_snaps * o.dropbacks, 1) end as coverage_snaps_estimated,
        c.def_targets, c.def_completions_allowed, c.def_yards_allowed, c.def_receiving_td_allowed, c.def_ints,
        c.def_passer_rating_allowed, c.def_adot, c.def_air_yards_completed, c.def_yards_after_catch, c.def_missed_tackles
    from cov as c
    left join snaps as s on s.gsis_id = c.gsis_id and s.game_id = c.game_id
    left join opp as o on o.game_id = c.game_id and o.offense = {{ kd_team('c.opponent') }}
    left join onfield as f on f.gsis_id = c.gsis_id and f.game_id = c.game_id
)

select
    *,
    coalesce(coverage_snaps_on_field, coverage_snaps_estimated)       as coverage_snaps,
    case when coverage_snaps_on_field is not null then 'participation'
         when coverage_snaps_estimated is not null then 'snap_share' end as coverage_snaps_source
from joined
