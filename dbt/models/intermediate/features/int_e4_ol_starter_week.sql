{{ config(indexes=[{'columns': ['team', 'season', 'week']}], post_hook="analyze {{ this }}") }}
-- Plan E4 (Wave E), helper of the feature group `oline_quality`: per team x regular-season week W, the line's five
-- starters exactly as int_player_week_personnel picks them (the five linemen with the most offensive snaps over the
-- team's last four PLAYED games before W, int_pn_window_player; ties: gsis_id), each with how good he is AS OF W:
--   career_starts      his played regular-season games before W (any team, 2016 on) with snap share >= 0.5
--   draft_score        3 = 1st round, 2 = day 2 (rounds 2-3), 1 = day 3 (rounds 4-7), 0 = undrafted or unknown
--   prev_season_share  last season's snaps in season-equivalents: the sum of his per-game snap shares over season
--                      S-1 / that season's games per team (16 through 2020, 17 since); 0 = no snaps (a rookie)
--   quality_rank       1-5 among the five by prev_season_share (ties: window snap share, then gsis_id):
--                      1 = the line's most-used lineman last season
--   out_injured        week W: Out / Doubtful / reserve list (int_pn_window_player, the personnel rule)
-- Week 1 and a team's first game have no window: no rows.
with starters as materialized (
    select season, week, team, gsis_id, snap_share, out_injured
    from (select w.*, row_number() over (partition by season, week, team order by snap_share desc nulls last, gsis_id) as rn
          from {{ ref('int_pn_window_player') }} as w
          where pos_group = 'OL') as x
    where rn <= 5
),

season_games as (               -- regular-season games per team (16 / 17)
    select season, max(game_no) as games from {{ ref('int_pn_team_game') }} group by 1
),

prev_share as (                 -- per player-season: season-equivalents of snaps
    select p.gsis_id, p.season, round(sum(coalesce(p.snap_share, 0)) / max(sg.games), 4) as share
    from {{ ref('int_pn_player_game') }} as p
    join season_games as sg on sg.season = p.season
    group by 1, 2
),

starts_by_season as materialized (   -- starts (>= 50% of the snaps) per player-season, any team
    select gsis_id, season, count(*)::int as n
    from {{ ref('int_pn_player_game') }}
    where played and snap_share >= 0.5
    group by 1, 2
),

career as materialized (        -- starts before the week, any team, 2016 on: earlier seasons + this season before W
    select season, week, team, gsis_id, snap_share, out_injured, sum(n)::int as career_starts
    from (
        select s.*, 0 as n from starters as s
        union all
        select s.*, b.n from starters as s
        join starts_by_season as b on b.gsis_id = s.gsis_id and b.season < s.season
        union all
        select s.*, 1 from starters as s
        join {{ ref('int_pn_player_game') }} as p
          on p.gsis_id = s.gsis_id and p.season = s.season and p.week < s.week and p.played and p.snap_share >= 0.5
    ) as x
    group by 1, 2, 3, 4, 5, 6
),

players as (
    select gsis_id, draft_round from {{ ref('stg_nflverse__players') }} where gsis_id is not null
)

select
    s.season, s.week, s.team, s.gsis_id, s.snap_share, s.out_injured,
    s.career_starts,
    case when pl.draft_round = 1 then 3 when pl.draft_round <= 3 then 2 when pl.draft_round <= 7 then 1 else 0 end as draft_score,
    coalesce(ps.share, 0)                                                                                         as prev_season_share,
    row_number() over (partition by s.season, s.week, s.team
                       order by coalesce(ps.share, 0) desc, s.snap_share desc nulls last, s.gsis_id)::int         as quality_rank
from career as s
left join prev_share as ps on ps.gsis_id = s.gsis_id and ps.season = s.season - 1
left join players as pl on pl.gsis_id = s.gsis_id
