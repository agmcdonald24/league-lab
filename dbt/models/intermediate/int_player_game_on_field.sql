{{ config(indexes=[{'columns': ['gsis_id', 'game_id'], 'unique': True}]) }}
-- IX-1 (Wave I-X), lf1.0 — a game left early (docs/METRICS.md § "A game left early"). Per player x game he played:
--   * the on-field target / carry share, EXACT (participation seasons: his targets / the team's targets on the plays he
--     was on the field, both from play-by-play) and ESTIMATED (every season with snap counts: his targets / (the
--     team's targets x his share of the offensive snaps), NULL when his snaps are unknown or zero, capped at 1);
--   * the shipped share (exact where it exists, else the estimate) with its basis and summable parts;
--   * LEFT EARLY, knowable when the game ends: his snap share at most half the median of his previous games of the
--     season (>= 2 of them) AND an injury note naming him (identified by the play's own ids: the note's name is the
--     play's passer / receiver / rusher and the note's team is the offence; anyone else is unmatched, never guessed).
--     LE-B (graded, not shipped unless it wins): or a touch in the first half and none after it;
--   * the participation truth for the grade (2016 - 2025): his last play on the field and the team's plays after it.
-- Nothing here is a projection input (IX-6 decides).
with base as (
    select w.gsis_id, w.game_id, w.season, w.season_type, w.week, w.team, w.position,
           w.targets, w.carries, t.targets as team_targets, t.carries as team_carries,
           sn.offense_snaps, sn.offense_snap_pct, sn.offense_snaps is not null as snaps_known,
           coalesce(sn.offense_snaps, 0) > 0
               or coalesce(w.attempts, 0) + coalesce(w.carries, 0) + coalesce(w.targets, 0) > 0 as played
    from {{ ref('stg_nflverse__player_stats_week') }} as w
    left join {{ ref('fct_team_game') }} as t on t.team = w.team and t.game_id = w.game_id
    left join {{ ref('int_player_game_snaps') }} as sn on sn.gsis_id = w.gsis_id and sn.game_id = w.game_id
    where w.position in ('QB', 'RB', 'WR', 'TE', 'FB')
),

games as (
    select * from base where played
),

plays as (
    select game_id, play_id, posteam as team, qtr, is_target, is_rush_attempt, receiver_player_id, rusher_player_id
    from {{ ref('fct_play') }}
    where not is_no_play and posteam is not null
),

-- ---- exact (participation): the team's targets / carries on the plays he was on the field, and his last play
on_field as (
    select b.gsis_id, b.game_id,
           count(*)                                                                   as plays_on_field,
           count(*) filter (where p.is_target)                                        as team_targets_on_field,
           count(*) filter (where p.is_target and p.receiver_player_id = b.gsis_id)   as targets_on_field,
           count(*) filter (where p.is_rush_attempt)                                  as team_carries_on_field,
           count(*) filter (where p.is_rush_attempt and p.rusher_player_id = b.gsis_id) as carries_on_field,
           max(b.play_id)                                                             as last_play_id
    from {{ ref('bridge_play_participation') }} as b
    join plays as p on p.game_id = b.game_id and p.play_id = b.play_id and p.team = b.team
    group by b.gsis_id, b.game_id
),

participation_games as (
    select distinct game_id, team from {{ ref('bridge_play_participation') }}
),

team_plays as (
    select p.game_id, p.team, p.play_id, p.qtr,
           row_number() over (partition by p.game_id, p.team order by p.play_id) as seq,
           count(*) over (partition by p.game_id, p.team)                        as n_plays
    from plays as p
    join participation_games as pg on pg.game_id = p.game_id and pg.team = p.team
),

last_play as (
    select o.gsis_id, o.game_id, tp.qtr::int as last_qtr, (tp.n_plays - tp.seq)::int as team_plays_after
    from on_field as o
    join games as g on g.gsis_id = o.gsis_id and g.game_id = o.game_id
    join team_plays as tp on tp.game_id = o.game_id and tp.team = g.team and tp.play_id = o.last_play_id
),

-- ---- the injury notes: "<TEAM>-<jersey>-<name> was injured during the play", identified by the play's own ids
notes as (
    select s.game_id, s.play_id, s.qtr, s.posteam, m[1] as note_team, m[3] as note_name,
           s.passer_player_id, s.passer_player_name, s.receiver_player_id, s.receiver_player_name,
           s.rusher_player_id, s.rusher_player_name
    from {{ ref('stg_nflverse__pbp') }} as s
    cross join lateral regexp_matches(s.description,
        '([A-Z]{2,3})-([0-9]{1,2})-([A-Za-z][A-Za-z.''-]*(?: (?:Jr\.|Sr\.|II|III|IV|V))?) was injured during the play', 'g') as m
    where s.description like '%was injured during the play%'
),

notes_id as (
    select n.game_id, n.play_id, n.qtr,
           case when n.note_team <> n.posteam then null
                when n.note_name = n.receiver_player_name then n.receiver_player_id
                when n.note_name = n.rusher_player_name then n.rusher_player_id
                when n.note_name = n.passer_player_name then n.passer_player_id
           end as gsis_id
    from notes as n
),

injured as (
    select gsis_id, game_id, min(qtr)::int as injured_qtr, min(play_id) as injured_play_id
    from notes_id
    where gsis_id is not null
    group by gsis_id, game_id
),

-- ---- touches by half (LE-B): a target or a carry
touches as (
    select x.gsis_id, x.game_id,
           count(*) filter (where x.qtr <= 2) as touches_first_half,
           count(*) filter (where x.qtr >= 3) as touches_after_half
    from (
        select receiver_player_id as gsis_id, game_id, qtr from plays where is_target
        union all
        select rusher_player_id, game_id, qtr from plays where is_rush_attempt
    ) as x
    where x.gsis_id is not null
    group by x.gsis_id, x.game_id
),

-- ---- his usual snap share: the median of his previous played games of the season (snaps known), >= 2 of them
usual as (
    select g.gsis_id, g.game_id, count(h.game_id) as prev_games,
           percentile_cont(0.5) within group (order by h.offense_snap_pct) as usual_snap_pct
    from games as g
    join games as h on h.gsis_id = g.gsis_id and h.season = g.season and h.season_type = g.season_type
                   and h.week < g.week and h.snaps_known and h.offense_snap_pct is not null
    where g.season_type = 'REG'
    group by g.gsis_id, g.game_id
),

shares as (
    select g.*,
           o.plays_on_field, o.team_targets_on_field, o.targets_on_field, o.team_carries_on_field, o.carries_on_field,
           lp.last_qtr, lp.team_plays_after,
           u.prev_games, u.usual_snap_pct,
           i.injured_qtr, i.injured_play_id,
           coalesce(t.touches_first_half, 0) as touches_first_half, coalesce(t.touches_after_half, 0) as touches_after_half,
           -- the estimate: the team's targets x his snap share (NULL when his snaps are unknown or zero)
           case when g.snaps_known and g.offense_snap_pct > 0 then g.team_targets * g.offense_snap_pct end as team_targets_est,
           case when g.snaps_known and g.offense_snap_pct > 0 then g.team_carries * g.offense_snap_pct end as team_carries_est
    from games as g
    left join on_field as o on o.gsis_id = g.gsis_id and o.game_id = g.game_id
    left join last_play as lp on lp.gsis_id = g.gsis_id and lp.game_id = g.game_id
    left join usual as u on u.gsis_id = g.gsis_id and u.game_id = g.game_id
    left join injured as i on i.gsis_id = g.gsis_id and i.game_id = g.game_id
    left join touches as t on t.gsis_id = g.gsis_id and t.game_id = g.game_id
),

flags as (
    select s.*,
           case when s.team_targets_on_field > 0
                then round(s.targets_on_field::numeric / s.team_targets_on_field, 4) end         as on_field_target_share_exact,
           case when s.team_carries_on_field > 0
                then round(s.carries_on_field::numeric / s.team_carries_on_field, 4) end         as on_field_carry_share_exact,
           case when s.team_targets_est > 0
                then round(least(1, s.targets::numeric / s.team_targets_est)::numeric, 4) end    as on_field_target_share_est,
           case when s.team_carries_est > 0
                then round(least(1, s.carries::numeric / s.team_carries_est)::numeric, 4) end    as on_field_carry_share_est,
           (s.prev_games >= 2 and s.snaps_known and s.offense_snap_pct is not null)               as snap_drop_known,
           coalesce(s.prev_games >= 2 and s.snaps_known and s.offense_snap_pct <= 0.5 * s.usual_snap_pct, false) as snap_drop,
           s.injured_qtr is not null                                                               as injury_note,
           (s.touches_first_half > 0 and s.touches_after_half = 0)                                 as no_touch_after_half
    from shares as s
)

select
    f.gsis_id, f.game_id, f.season, f.season_type, f.week, f.team, f.position,
    f.targets, f.carries, f.team_targets, f.team_carries, f.offense_snaps, f.offense_snap_pct,
    -- exact (participation) and estimated (snaps)
    f.plays_on_field, f.targets_on_field, f.team_targets_on_field, f.carries_on_field, f.team_carries_on_field,
    f.on_field_target_share_exact, f.on_field_carry_share_exact,
    f.team_targets_est, f.team_carries_est, f.on_field_target_share_est, f.on_field_carry_share_est,
    -- the shipped share: exact where participation covers the game, else the estimate; its summable parts
    case when f.plays_on_field is not null then 'participation'
         when f.team_targets_est is not null or f.team_carries_est is not null then 'snaps' end   as on_field_basis,
    case when f.plays_on_field is not null then f.targets_on_field::numeric
         when f.team_targets_est is not null then f.targets::numeric end                          as on_field_targets,
    case when f.plays_on_field is not null then f.team_targets_on_field::numeric
         else round(f.team_targets_est::numeric, 4) end                                           as on_field_team_targets,
    case when f.plays_on_field is not null then f.carries_on_field::numeric
         when f.team_carries_est is not null then f.carries::numeric end                          as on_field_carries,
    case when f.plays_on_field is not null then f.team_carries_on_field::numeric
         else round(f.team_carries_est::numeric, 4) end                                           as on_field_team_carries,
    case when f.plays_on_field is not null then f.on_field_target_share_exact
         else f.on_field_target_share_est end                                                     as on_field_target_share,
    case when f.plays_on_field is not null then f.on_field_carry_share_exact
         else f.on_field_carry_share_est end                                                      as on_field_carry_share,
    -- left early (lf1.0): the inputs and both candidates
    f.prev_games, f.usual_snap_pct, f.snap_drop_known, f.snap_drop, f.injury_note, f.injured_qtr,
    f.touches_first_half, f.touches_after_half, f.no_touch_after_half,
    (f.snap_drop and f.injury_note)                                                               as left_early_a,
    (f.snap_drop and (f.injury_note or f.no_touch_after_half))                                    as left_early_b,
    -- the shipped rule (lf1.0): LE-B, the candidate the grade picked by the rule committed first (F1 0.422 against
    -- LE-A's 0.253 on 2016 - 2025; docs/METRICS.md § "A game left early"), and its reason in words
    {%- set le = 'f.snap_drop and (f.injury_note or f.no_touch_after_half)' %}
    ({{ le }})                                                                                     as left_early,
    case when {{ le }} then
        f.offense_snaps || ' snaps (' || round(100 * f.offense_snap_pct)::int || '% of the team''s; usually '
        || round(100 * f.usual_snap_pct)::int || '%); '
        || case when f.injury_note
                then 'hurt on a play in the ' || case f.injured_qtr when 1 then '1st' when 2 then '2nd' when 3 then '3rd'
                                                    when 4 then '4th' else 'overtime' end || ' quarter'
                else 'no target or carry after half-time' end
    end                                                                                            as left_early_reason,
    -- the participation truth's parts (2016 - 2025)
    f.last_qtr, f.team_plays_after
from flags as f
