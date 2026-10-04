-- depends_on: {{ ref('scoring_stat_map') }}
{{ config(
    materialized='table',
    indexes=[{'columns': ['league_id', 'season', 'scope', 'week']}],
    pre_hook=["create table if not exists ops.lineup_totals (run_at timestamptz, as_of timestamptz, model_version text, league_id text, season integer, week integer, roster_id integer, is_realised boolean, lineup_value double precision, bench_value double precision, slots_total integer, slots_filled integer, empty_slots text, weakest_slot text, weakest_margin double precision, weakest_sleeper_player_id text, n_players integer, n_bench integer, n_unplayable integer, n_locked integer, n_questionable integer, n_ppg_valued integer, inputs_fingerprint text, n_unvalued integer)",
              "alter table ops.projections add column if not exists pricing text"]
) }}
-- Plan E1, "Our record": League Lab's frozen board against Sleeper's own projections (the numbers every
-- Sleeper user gets for free) and what really happened, per league x season x week x position, plus one
-- row per league-week for the start/sit calls (position = 'ALL') and the season to date (scope = 'season').
--
-- * Ours: ops.projections rows frozen before the week's first kickoff (frozen_source = 'kickoff', plan B5),
--   QB / RB / WR / TE, the projection in the league's scoring as the board showed it (rounded like the mart).
-- * Sleeper: raw.sleeper_projections, the LAST snapshot fetched before the week's first kickoff (the same
--   freeze rule), its projected stat line priced in the league's scoring with league_points() — the macro that
--   prices our own line, yardage bonuses included. A DEF is not priced (team-defense keys are unmapped).
-- * Actual: mart_player_week_projections.points_actual (the league's scoring), players who played and were
--   rankable on our board (Out / Doubtful / IR excluded) — the population mart_projection_drift scores.
-- * On the players BOTH projected (Sleeper id -> gsis id through player_id_map): Spearman (average ranks,
--   NULL under 8 players, like drift), MAE, hit rate = share of the top N by projection that finished top N
--   (N = 12 QB, 24 RB, 36 WR, 12 TE).
-- * Start/sit calls (position = 'ALL'): per roster, the week's closest calls as the decision cards pick them
--   (app/lib/cards.py `decisions`: the 3 smallest-margin valued starters of the proposed lineup in ops.lineups,
--   weakest slot first on a tie, each with the bench player who comes in — value = starter value - margin),
--   taken as they stood before kickoff (no locks). Ours picks the starter; Sleeper picks whichever of the two
--   it projects higher in the league's scoring; the right call is whoever scored more (Sleeper's own count,
--   league_player_week.points_observed, else points_actual). Pushes and pairs Sleeper has no number for are
--   counted apart and left out of pairs_n.
-- * A week is 'scored' once every game on its board has players in (drift's rule); before that it is
--   'in_play': n_both is filled, the scores are NULL. Season rows average the scored weeks (weekly means,
--   like drift) and sum the calls.
-- * pricing (M4, Wave I-G): how OUR board's bonuses were priced that week — ops.projections.pricing ('flat': all
--   or nothing on the projected line; 'ev': at their odds; NULL, rows before the column existed, = 'flat'); one label
--   per league-week (every QB-TE row of a league-week is written by one build), 'mixed' if a week ever carries two;
--   season rows: the scored weeks' label, 'mixed' when they differ. Sleeper's side stays priced by the SQL macro
--   (all or nothing on its projected line) in either case — docs/METRICS.md § "The record's pricing column".
{%- set line_columns = ['attempts', 'completions', 'carries', 'targets', 'passing_yards', 'passing_tds',
    'passing_interceptions', 'passing_2pt_conversions', 'rushing_yards', 'rushing_tds', 'rushing_2pt_conversions',
    'receptions', 'receiving_yards', 'receiving_tds', 'receiving_2pt_conversions', 'fumbles_total', 'fumbles_lost_total',
    'fumble_recovery_tds', 'special_teams_tds', 'fg_made_0_19', 'fg_made_20_29', 'fg_made_30_39', 'fg_made_40_49',
    'fg_made_50_59', 'fg_missed', 'fg_missed_0_19', 'fg_missed_20_29', 'fg_missed_30_39', 'fg_missed_40_49',
    'fg_missed_50_59', 'pat_made', 'pat_missed', 'pass_tds_40p', 'pass_tds_50p', 'rush_tds_40p', 'rush_tds_50p',
    'rec_tds_40p', 'rec_tds_50p'] %}
{#- = league_lab.ingest.sleeper_projections.LINE_COLUMNS (tests/test_sleeper_projections.py keeps them equal) #}
{%- set min_players = 8 %}

with kick as (
    select season, week, min(kickoff_at) as first_kickoff_at
    from {{ ref('dim_game') }}
    where season_type = 'REG'
    group by 1, 2
),

-- Sleeper: the last snapshot of each week fetched before its first kickoff
snap as (
    select p.season, p.week, max(p.fetched_at) as fetched_at, k.first_kickoff_at
    from {{ source('raw', 'sleeper_projections') }} as p
    join kick as k using (season, week)
    where p.season_type = 'regular' and p.fetched_at < k.first_kickoff_at
    group by p.season, p.week, k.first_kickoff_at
),

sl as (
    select p.season, p.week, p.player_id, p.position, p.company, p.fetched_at,
           {%- for c in line_columns %}
           p.{{ c }},
           {%- endfor %}
           {{ zero_stat_columns(line_columns) }}
    from {{ source('raw', 'sleeper_projections') }} as p
    join snap as s using (season, week, fetched_at)
    where p.season_type = 'regular'
      -- a listed player with no stat line (stats null / {}: a backup, a player ruled out) is not a projection of 0
      -- (QA, Wave E): Sleeper's own total must be there, or at least one priced stat
      and (p.pts_ppr is not null or p.pts_half_ppr is not null or p.pts_std is not null
           or coalesce(p.attempts, p.carries, p.targets, p.passing_yards, p.rushing_yards, p.receiving_yards,
                       p.receptions, p.passing_tds, p.rushing_tds, p.receiving_tds, p.fg_made_0_19, p.pat_made) is not null)
),

leagues as (
    select league_id, league_name, scoring_settings from {{ ref('dim_league_season') }}
),

-- ours: the board as published before the week's first kickoff
board as (
    select p.league_id, p.season, p.week, p.gsis_id, p.position, round(p.proj_points::numeric, 2) as ours_points,
           p.model_version, p.frozen_at, coalesce(p.pricing, 'flat') as pricing
    from {{ source('ops', 'projections') }} as p
    where p.frozen_source = 'kickoff' and p.position in ('QB', 'RB', 'WR', 'TE')
),

-- the league-weeks on the record: both boards frozen before kickoff
weeks as (
    select b.league_id, b.season, b.week, max(b.model_version) as model_version, max(b.frozen_at) as board_frozen_at,
           s.fetched_at as sleeper_fetched_at, s.first_kickoff_at,
           case when count(distinct b.pricing) > 1 then 'mixed' else max(b.pricing) end as pricing
    from board as b
    join snap as s using (season, week)
    group by b.league_id, b.season, b.week, s.fetched_at, s.first_kickoff_at
),

sl_priced as (
    select w.league_id, sl.season, sl.week, sl.player_id, sl.position, sl.company,
           case when sl.position = 'DEF' or sl.player_id !~ '^[0-9]+$' then null
                else {{ league_points('l.scoring_settings', 'sl') }} end as sleeper_points
    from weeks as w
    join sl on sl.season = w.season and sl.week = w.week
    join leagues as l on l.league_id = w.league_id
),

outcome as (
    select league_id, season, week, gsis_id, game_id, played, is_rankable, points_actual
    from {{ ref('mart_player_week_projections') }}
),

games as (
    select o.league_id, o.season, o.week,
           count(distinct o.game_id) as games_scheduled,
           count(distinct o.game_id) filter (where o.played) as games_played
    from outcome as o
    join weeks as w using (league_id, season, week)
    group by 1, 2, 3
),

week_status as (
    select w.*, coalesce(g.games_scheduled > 0 and g.games_played >= g.games_scheduled, false) as is_scored
    from weeks as w
    left join games as g using (league_id, season, week)
),

-- the players both projected
both_proj as (
    select b.league_id, b.season, b.week, b.position, b.gsis_id, b.ours_points, sp.sleeper_points,
           o.played, o.is_rankable, o.points_actual
    from board as b
    join week_status as w using (league_id, season, week)
    join {{ ref('player_id_map') }} as m on m.gsis_id = b.gsis_id
    join sl_priced as sp on sp.league_id = b.league_id and sp.season = b.season and sp.week = b.week
                        and sp.player_id = m.sleeper_id
    left join outcome as o on o.league_id = b.league_id and o.season = b.season and o.week = b.week and o.gsis_id = b.gsis_id
    where sp.sleeper_points is not null
),

scored as (
    select x.*,
           rank() over (partition by league_id, season, week, position order by ours_points)
               + (count(*) over (partition by league_id, season, week, position, ours_points) - 1) / 2.0     as ours_rank,
           rank() over (partition by league_id, season, week, position order by sleeper_points)
               + (count(*) over (partition by league_id, season, week, position, sleeper_points) - 1) / 2.0  as sleeper_rank,
           rank() over (partition by league_id, season, week, position order by points_actual)
               + (count(*) over (partition by league_id, season, week, position, points_actual) - 1) / 2.0   as actual_rank,
           row_number() over (partition by league_id, season, week, position order by ours_points desc, gsis_id)    as ours_rn,
           row_number() over (partition by league_id, season, week, position order by sleeper_points desc, gsis_id) as sleeper_rn,
           row_number() over (partition by league_id, season, week, position order by points_actual desc, gsis_id)  as actual_rn,
           case position when 'QB' then 12 when 'RB' then 24 when 'WR' then 36 when 'TE' then 12 end                 as top_n
    from both_proj as x
    where x.played and x.is_rankable and x.points_actual is not null
),

pos_week as (
    select league_id, season, week, position, max(top_n) as top_n, count(*) as n_players,
           case when count(*) >= {{ min_players }} then corr(ours_rank, actual_rank) end                      as ours_spearman,
           case when count(*) >= {{ min_players }} then corr(sleeper_rank, actual_rank) end                   as sleeper_spearman,
           avg(abs(ours_points - points_actual))                                                              as ours_mae,
           avg(abs(sleeper_points - points_actual))                                                           as sleeper_mae,
           sum(abs(ours_points - points_actual))                                                              as ours_abs_err,
           sum(abs(sleeper_points - points_actual))                                                           as sleeper_abs_err,
           case when count(*) >= {{ min_players }} then
               (count(*) filter (where ours_rn <= top_n and actual_rn <= top_n))::numeric / least(max(top_n), count(*)) end    as ours_hit_rate,
           case when count(*) >= {{ min_players }} then
               (count(*) filter (where sleeper_rn <= top_n and actual_rn <= top_n))::numeric / least(max(top_n), count(*)) end as sleeper_hit_rate
    from scored
    group by 1, 2, 3, 4
),

n_both as (
    select league_id, season, week, position, count(*) as n_both
    from both_proj
    group by 1, 2, 3, 4
),

-- ---------------------------------------------------------------- the start/sit calls (the cards' pairs)
elig (slot_type, position) as (
    values ('QB', 'QB'), ('RB', 'RB'), ('WR', 'WR'), ('TE', 'TE'), ('K', 'K'), ('DEF', 'DEF'),
           ('FLEX', 'RB'), ('FLEX', 'WR'), ('FLEX', 'TE'),
           ('SUPER_FLEX', 'QB'), ('SUPER_FLEX', 'RB'), ('SUPER_FLEX', 'WR'), ('SUPER_FLEX', 'TE'),
           ('REC_FLEX', 'WR'), ('REC_FLEX', 'TE'), ('WRRB_FLEX', 'RB'), ('WRRB_FLEX', 'WR')
),

lu as (
    select l.league_id, l.season, l.week, l.roster_id, l.role, l.slot, l.slot_type, l.slot_order, l.bench_rank,
           l.sleeper_player_id, l.gsis_id, l.position, l.value, l.value_source, l.margin
    from {{ source('ops', 'lineups') }} as l
    join weeks as w using (league_id, season, week)
    where not l.is_realised and l.role in ('starter', 'bench')
),

starters as (
    select s.*, (s.slot = t.weakest_slot) as is_weakest_slot
    from lu as s
    left join {{ source('ops', 'lineup_totals') }} as t
           on t.league_id = s.league_id and t.season = s.season and t.week = s.week and t.roster_id = s.roster_id
          and not t.is_realised
    where s.role = 'starter' and s.margin is not null and s.value is not null and s.value_source <> 'unvalued'
      and s.sleeper_player_id is not null
),

bench as (
    select b.*, e.slot_type as eligible_for
    from lu as b
    left join elig as e on e.position = b.position
    where b.role = 'bench' and b.value is not null
),

-- the bench player who comes in (cards.alternative): the slot's best eligible bench player when his value is
-- the starter's value minus the margin; nobody when the margin is the starter's whole value; otherwise the
-- bench player with that value (a teammate slid over); failing that, the slot's best eligible bench player
alt as (
    select s.league_id, s.season, s.week, s.roster_id, s.slot, s.slot_order, s.is_weakest_slot, s.margin,
           s.sleeper_player_id, s.gsis_id, s.value,
           case when best.sleeper_player_id is not null and abs(best.value - (s.value - s.margin)) <= 0.011 then best.sleeper_player_id
                when abs(s.value - s.margin) <= 0.011 then null
                when ent.sleeper_player_id is not null then ent.sleeper_player_id
                else best.sleeper_player_id end                                                            as alt_sleeper_player_id
    from starters as s
    left join lateral (
        select b.sleeper_player_id, b.value
        from bench as b
        where b.league_id = s.league_id and b.season = s.season and b.week = s.week and b.roster_id = s.roster_id
          and b.eligible_for = s.slot_type
        order by b.value desc, b.bench_rank
        limit 1
    ) as best on true
    left join lateral (
        select b.sleeper_player_id
        from bench as b
        where b.league_id = s.league_id and b.season = s.season and b.week = s.week and b.roster_id = s.roster_id
          and abs(b.value - (s.value - s.margin)) <= 0.011
        order by (b.eligible_for = s.slot_type) desc nulls last, b.bench_rank
        limit 1
    ) as ent on true
),

pairs as (
    select a.*, row_number() over (partition by a.league_id, a.season, a.week, a.roster_id
                                   order by a.margin, (not coalesce(a.is_weakest_slot, false)), a.value, a.slot_order) as call_rank
    from alt as a
    where a.alt_sleeper_player_id is not null
),

pair_values as (
    select p.league_id, p.season, p.week, p.roster_id, p.call_rank,
           ss.sleeper_points as sleeper_starter, sa.sleeper_points as sleeper_alt,
           coalesce(ls.points_observed, os.points_actual) as actual_starter,
           coalesce(la.points_observed, oa.points_actual) as actual_alt
    from pairs as p
    left join sl_priced as ss on ss.league_id = p.league_id and ss.season = p.season and ss.week = p.week
                             and ss.player_id = p.sleeper_player_id
    left join sl_priced as sa on sa.league_id = p.league_id and sa.season = p.season and sa.week = p.week
                             and sa.player_id = p.alt_sleeper_player_id
    left join {{ ref('league_player_week') }} as ls on ls.league_id = p.league_id and ls.week = p.week
                             and ls.roster_id = p.roster_id and ls.sleeper_player_id = p.sleeper_player_id
    left join {{ ref('league_player_week') }} as la on la.league_id = p.league_id and la.week = p.week
                             and la.roster_id = p.roster_id and la.sleeper_player_id = p.alt_sleeper_player_id
    left join outcome as os on os.league_id = p.league_id and os.season = p.season and os.week = p.week
                           and os.gsis_id = p.gsis_id and os.played
    left join {{ ref('player_id_map') }} as ma on ma.sleeper_id = p.alt_sleeper_player_id
    left join outcome as oa on oa.league_id = p.league_id and oa.season = p.season and oa.week = p.week
                           and oa.gsis_id = ma.gsis_id and oa.played
    where p.call_rank <= 3
),

pair_calls as (
    select v.*,
           case when sleeper_starter > sleeper_alt then 'starter' when sleeper_starter < sleeper_alt then 'alt'
                when sleeper_starter = sleeper_alt then 'tie' end                                      as sleeper_pick,
           case when actual_starter > actual_alt then 'starter' when actual_starter < actual_alt then 'alt'
                when actual_starter = actual_alt then 'push' end                                       as actual_winner
    from pair_values as v
),

pair_week as (
    select c.league_id, c.season, c.week,
           count(*)                                                                                     as pairs_listed,
           count(*) filter (where c.sleeper_pick is null)                                               as pairs_no_sleeper,
           count(*) filter (where c.sleeper_pick is not null and c.actual_winner = 'push')              as pairs_push,
           count(*) filter (where c.sleeper_pick is not null and c.actual_winner in ('starter', 'alt'))  as pairs_n,
           count(*) filter (where c.sleeper_pick is not null and c.actual_winner = 'starter')           as pairs_ours_right,
           count(*) filter (where c.actual_winner in ('starter', 'alt') and c.sleeper_pick = c.actual_winner) as pairs_sleeper_right,
           count(*) filter (where c.actual_winner = 'starter' and c.sleeper_pick = 'starter')            as pairs_both_right,
           count(*) filter (where c.actual_winner = 'alt' and c.sleeper_pick is not null
                              and c.sleeper_pick <> 'alt')                                              as pairs_neither_right,
           count(*) filter (where c.actual_winner in ('starter', 'alt') and c.sleeper_pick in ('alt', 'tie')) as pairs_disagree,
           count(*) filter (where c.actual_winner = 'starter' and c.sleeper_pick in ('alt', 'tie'))     as pairs_ours_right_disagree
    from pair_calls as c
    group by 1, 2, 3
),

-- ---------------------------------------------------------------- one row per league x week x position
week_rows as (
    select w.league_id, w.season, w.week, pos.position, w.is_scored,
           case when w.is_scored then pw.top_n end as top_n, nb.n_both,
           case when w.is_scored then coalesce(pw.n_players, 0) end as n_players,
           case when w.is_scored then pw.ours_spearman end as ours_spearman,
           case when w.is_scored then pw.sleeper_spearman end as sleeper_spearman,
           case when w.is_scored then pw.ours_mae end as ours_mae,
           case when w.is_scored then pw.sleeper_mae end as sleeper_mae,
           case when w.is_scored then pw.ours_hit_rate end as ours_hit_rate,
           case when w.is_scored then pw.sleeper_hit_rate end as sleeper_hit_rate,
           null::bigint as pairs_listed, null::bigint as pairs_n, null::bigint as pairs_ours_right,
           null::bigint as pairs_sleeper_right, null::bigint as pairs_both_right, null::bigint as pairs_neither_right,
           null::bigint as pairs_disagree, null::bigint as pairs_ours_right_disagree, null::bigint as pairs_push,
           null::bigint as pairs_no_sleeper,
           w.model_version, w.board_frozen_at, w.sleeper_fetched_at, w.first_kickoff_at, w.pricing
    from week_status as w
    cross join (values ('QB'), ('RB'), ('WR'), ('TE')) as pos (position)
    join n_both as nb on nb.league_id = w.league_id and nb.season = w.season and nb.week = w.week and nb.position = pos.position
    left join pos_week as pw on pw.league_id = w.league_id and pw.season = w.season and pw.week = w.week
                            and pw.position = pos.position
),

all_rows as (
    select w.league_id, w.season, w.week, 'ALL' as position, w.is_scored, null::integer as top_n,
           (select sum(nb.n_both) from n_both as nb
            where nb.league_id = w.league_id and nb.season = w.season and nb.week = w.week)::bigint as n_both,
           case when w.is_scored then coalesce(agg.n_players, 0) end as n_players,
           null::double precision as ours_spearman, null::double precision as sleeper_spearman,
           case when w.is_scored then agg.ours_mae end as ours_mae,
           case when w.is_scored then agg.sleeper_mae end as sleeper_mae,
           null::numeric as ours_hit_rate, null::numeric as sleeper_hit_rate,
           pr.pairs_listed,
           case when w.is_scored then pr.pairs_n end as pairs_n,
           case when w.is_scored then pr.pairs_ours_right end as pairs_ours_right,
           case when w.is_scored then pr.pairs_sleeper_right end as pairs_sleeper_right,
           case when w.is_scored then pr.pairs_both_right end as pairs_both_right,
           case when w.is_scored then pr.pairs_neither_right end as pairs_neither_right,
           case when w.is_scored then pr.pairs_disagree end as pairs_disagree,
           case when w.is_scored then pr.pairs_ours_right_disagree end as pairs_ours_right_disagree,
           case when w.is_scored then pr.pairs_push end as pairs_push,
           pr.pairs_no_sleeper,
           w.model_version, w.board_frozen_at, w.sleeper_fetched_at, w.first_kickoff_at, w.pricing
    from week_status as w
    left join (
        select league_id, season, week, sum(n_players) as n_players,
               sum(ours_abs_err) / nullif(sum(n_players), 0) as ours_mae,
               sum(sleeper_abs_err) / nullif(sum(n_players), 0) as sleeper_mae
        from pos_week group by 1, 2, 3
    ) as agg using (league_id, season, week)
    left join pair_week as pr using (league_id, season, week)
),

weekly as (
    select * from week_rows
    union all
    select * from all_rows where n_both > 0 or pairs_listed > 0
),

-- ---------------------------------------------------------------- the season to date (scored weeks)
season_rows as (
    select league_id, season, max(week) as week, min(week) as first_week, count(*) as weeks_scored, position,
           true as is_scored, max(top_n) as top_n, sum(n_both)::bigint as n_both, sum(n_players)::bigint as n_players,
           avg(ours_spearman) as ours_spearman, avg(sleeper_spearman) as sleeper_spearman,
           avg(ours_mae) as ours_mae, avg(sleeper_mae) as sleeper_mae,
           avg(ours_hit_rate) as ours_hit_rate, avg(sleeper_hit_rate) as sleeper_hit_rate,
           sum(pairs_listed)::bigint as pairs_listed, sum(pairs_n)::bigint as pairs_n,
           sum(pairs_ours_right)::bigint as pairs_ours_right, sum(pairs_sleeper_right)::bigint as pairs_sleeper_right,
           sum(pairs_both_right)::bigint as pairs_both_right, sum(pairs_neither_right)::bigint as pairs_neither_right,
           sum(pairs_disagree)::bigint as pairs_disagree, sum(pairs_ours_right_disagree)::bigint as pairs_ours_right_disagree,
           sum(pairs_push)::bigint as pairs_push, sum(pairs_no_sleeper)::bigint as pairs_no_sleeper,
           string_agg(distinct model_version, ', ') as model_version, max(board_frozen_at) as board_frozen_at,
           max(sleeper_fetched_at) as sleeper_fetched_at, max(first_kickoff_at) as first_kickoff_at,
           case when count(distinct pricing) > 1 then 'mixed' else max(pricing) end as pricing
    from weekly
    where is_scored
    group by league_id, season, position
),

final as (
    select league_id, season, 'week' as scope, week, week as first_week, case when is_scored then 1 else 0 end as weeks_scored,
           position, case when is_scored then 'scored' else 'in_play' end as status, top_n, n_both, n_players,
           ours_spearman, sleeper_spearman, ours_mae, sleeper_mae, ours_hit_rate, sleeper_hit_rate,
           pairs_listed, pairs_n, pairs_ours_right, pairs_sleeper_right, pairs_both_right, pairs_neither_right,
           pairs_disagree, pairs_ours_right_disagree, pairs_push, pairs_no_sleeper,
           model_version, board_frozen_at, sleeper_fetched_at, first_kickoff_at, pricing
    from weekly
    union all
    select league_id, season, 'season' as scope, week, first_week, weeks_scored,
           position, 'scored' as status, top_n, n_both, n_players,
           ours_spearman, sleeper_spearman, ours_mae, sleeper_mae, ours_hit_rate, sleeper_hit_rate,
           pairs_listed, pairs_n, pairs_ours_right, pairs_sleeper_right, pairs_both_right, pairs_neither_right,
           pairs_disagree, pairs_ours_right_disagree, pairs_push, pairs_no_sleeper,
           model_version, board_frozen_at, sleeper_fetched_at, first_kickoff_at, pricing
    from season_rows
)

select f.league_id, l.league_name, f.season, f.scope, f.week, f.first_week, f.weeks_scored, f.position, f.status,
       f.top_n, f.n_both::integer as n_both, f.n_players::integer as n_players,
       round(f.ours_spearman::numeric, 3) as ours_spearman, round(f.sleeper_spearman::numeric, 3) as sleeper_spearman,
       round(f.ours_mae::numeric, 2) as ours_mae, round(f.sleeper_mae::numeric, 2) as sleeper_mae,
       round(f.ours_hit_rate::numeric, 3) as ours_hit_rate, round(f.sleeper_hit_rate::numeric, 3) as sleeper_hit_rate,
       f.pairs_listed::integer as pairs_listed, f.pairs_n::integer as pairs_n, f.pairs_ours_right::integer as pairs_ours_right,
       f.pairs_sleeper_right::integer as pairs_sleeper_right, f.pairs_both_right::integer as pairs_both_right,
       f.pairs_neither_right::integer as pairs_neither_right, f.pairs_disagree::integer as pairs_disagree,
       f.pairs_ours_right_disagree::integer as pairs_ours_right_disagree, f.pairs_push::integer as pairs_push,
       f.pairs_no_sleeper::integer as pairs_no_sleeper,
       f.model_version, f.board_frozen_at, f.sleeper_fetched_at, f.first_kickoff_at, f.pricing
from final as f
join leagues as l using (league_id)
