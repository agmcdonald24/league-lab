{{ config(indexes=[{'columns': ['team', 'game_id'], 'unique': True}, {'columns': ['season', 'team']}, {'columns': ['season', 'opponent']}],
          post_hook="analyze {{ this }}") }}
{%- set max_gap = 75 %}
-- D4 (plan Iteration 12, team volume and style; metric team_style v1.0): one row per team x game it had the ball
-- in (2016+, regular season and postseason), the OFFENSE's facts as additive counts so any window of games can
-- pool them (sums over sums). The same row read from the other side is the DEFENSE's "allowed" facts:
-- int_team_week_style takes a defense's games as the rows where opponent = that defense.
--
-- Definitions (docs/METRICS.md § "Team volume and style"):
--   play            a snap that can produce a stat line: a dropback (pass attempt, sack, scramble) or a designed
--                   run. Kneels, spikes, two-point tries and penalty-nullified snaps are not plays.
--   neutral         1st or 2nd down, quarters 1-3, the offense's pre-play score within 7 points either way.
--   neutral pass rate  neutral dropbacks / neutral plays.
--   expected pass   nflfastR's xpass: the pre-snap probability of a dropback given down, distance, field
--                   position, clock, score, timeouts and win probability (one fixed model for every team, so a
--                   team's dropbacks minus its xpass is its pass rate over expectation, PROE).
--   pace            game-clock seconds from one real snap (play, punt or field goal; not a nullified one) to the
--                   offense's next real snap on the same drive, counted when the first snap is in a neutral
--                   score state (quarters 1-3, within 7) on any down. Clock that does not run (an incompletion)
--                   is not counted: this is game clock, not wall time.
--   time of possession  game clock elapsed from each play-by-play row to the next one in the same half,
--                   credited to that row's offense (a kickoff return to the receiving team, a punt to the
--                   punting team, as the official stat does within a second or two).
--   drive           a run of rows with the same nflfastR fixed_drive and offense that contains at least one play
--                   (kneel-only and spike-only possessions and return-only possessions are not drives).
--   drive points    the offense's score at the start of the next possession (or the final score) minus its score
--                   at the start of the drive: touchdowns, the try after, field goals. A defensive or return
--                   score does not count for the offense.
--   red-zone trip   a drive with a real snap (play, punt, field goal) at the opponent's 20 or closer.
--   clock glitches  a row-to-row clock gap outside 0-{{ max_gap }} s is a mislabelled quarter or a missing row in the
--                   source (2020_01_LV_CAR has Q2 times inside Q1): capped at 0 / {{ max_gap }} s for time of
--                   possession, left out of pace (0.2% of gaps; real snap-to-snap gaps are under a minute).
--   first downs     passing + rushing first downs from the nflverse team stats (penalty first downs excluded).
--   giveaways       interceptions thrown + fumbles lost, nflverse team stats.
with p as (
    select game_id, play_id, season, season_type, week, posteam, home_team, away_team, qtr, half, down,
           game_seconds_remaining as gsr, score_differential_pre, posteam_score_pre, defteam_score_pre,
           play_type, coalesce(is_no_play, false) as is_no_play, yardline_100, yards_gained, xpass, fixed_drive,
           coalesce(is_dropback, false) as is_dropback, coalesce(is_sack, false) as is_sack,
           coalesce(is_dropback, false) or (coalesce(is_rush_attempt, false) and not coalesce(is_kneel, false)) as is_play,
           down in (1, 2) and qtr <= 3 and abs(score_differential_pre) <= 7                      as is_neutral,
           down is not null and not coalesce(is_no_play, false)
               and play_type in ('pass', 'run', 'punt', 'field_goal', 'qb_kneel', 'qb_spike')   as is_snap
    from {{ ref('fct_play') }}
    where season >= {{ var('seasons_start') }}
),

plays as (
    select posteam as team, game_id,
           count(*) filter (where is_play)                                             as plays,
           count(*) filter (where is_play and is_dropback)                             as dropbacks,
           count(*) filter (where is_play and is_sack)                                 as sacks,
           coalesce(sum(yards_gained) filter (where is_play), 0)                       as yards,
           count(*) filter (where is_play and is_neutral)                              as neutral_plays,
           count(*) filter (where is_play and is_neutral and is_dropback)              as neutral_dropbacks,
           count(*) filter (where is_play and xpass is not null)                       as xpass_plays,
           count(*) filter (where is_play and xpass is not null and is_dropback)       as xpass_dropbacks,
           coalesce(sum(xpass) filter (where is_play), 0)                              as xpass_sum
    from p
    where posteam is not null
    group by 1, 2
),

-- pace: snap-to-snap game clock on the same drive, from a neutral-score snap in quarters 1-3
snaps as (
    select posteam as team, game_id, qtr, score_differential_pre,
           gsr - lead(gsr) over (partition by game_id, posteam, fixed_drive order by play_id) as gap
    from p
    where is_snap and posteam is not null and gsr is not null
),

pace as (
    select team, game_id, count(*) as pace_snaps, sum(gap) as pace_seconds
    from snaps
    where gap between 0 and {{ max_gap }} and qtr <= 3 and abs(score_differential_pre) <= 7
    group by 1, 2
),

-- time of possession: clock from each row to the next in the same half, to that row's offense. A row without an
-- offense (a timeout, stamped with the previous snap's clock since 2022) goes to the last offense before it.
clock as (
    select game_id, posteam,
           count(posteam) over (partition by game_id order by play_id)                    as offense_run,
           least({{ max_gap }}, greatest(0, gsr - coalesce(lead(gsr) over (partition by game_id, half order by play_id),
                                       case half when 'H1' then 1800 when 'H2' then 0 else gsr end))) as elapsed
    from p
    where gsr is not null
),

top as (
    select team, game_id, sum(elapsed) as top_seconds
    from (select game_id, elapsed, first_value(posteam) over (partition by game_id, offense_run order by posteam nulls last) as team
          from clock) c
    where team is not null
    group by 1, 2
),

-- possessions: rows with the same fixed_drive and offense, in game order
poss as (
    select game_id, posteam as team, fixed_drive, min(play_id) as start_play_id,
           bool_or(is_play)                                                            as is_drive,
           bool_or(is_snap and yardline_100 <= 20)                                     as reached_red_zone
    from p
    where posteam is not null
    group by 1, 2, 3
),

poss_scored as (
    select ps.*, s.home_team, s.away_team,
           case when s.posteam = s.home_team then s.posteam_score_pre else s.defteam_score_pre end as home_pre,
           case when s.posteam = s.home_team then s.defteam_score_pre else s.posteam_score_pre end as away_pre
    from poss as ps
    join p as s on s.game_id = ps.game_id and s.play_id = ps.start_play_id
),

poss_next as (
    select x.*,
           coalesce(lead(x.home_pre) over w, g.home_score) as home_next,
           coalesce(lead(x.away_pre) over w, g.away_score) as away_next
    from poss_scored as x
    left join {{ ref('dim_game') }} as g using (game_id)
    window w as (partition by x.game_id order by x.start_play_id)
),

drives as (
    select team, game_id,
           count(*)                                                                    as drives,
           sum(pts)                                                                    as drive_points,
           count(*) filter (where pts > 0)                                             as scoring_drives,
           count(*) filter (where reached_red_zone)                                    as red_zone_trips
    from (
        select team, game_id, reached_red_zone,
               case when team = home_team then home_next - home_pre else away_next - away_pre end as pts
        from poss_next
        where is_drive
    ) d
    group by 1, 2
),

games as (
    select distinct game_id, season, season_type, week, home_team, away_team from p
)

select
    pl.team,
    pl.game_id,
    g.season,
    g.season_type,
    g.week,
    case when pl.team = g.home_team then g.away_team else g.home_team end      as opponent,
    pl.team = g.home_team                                                      as is_home,
    pl.plays, pl.dropbacks, pl.sacks, pl.yards,
    pl.neutral_plays, pl.neutral_dropbacks,
    pl.xpass_plays, pl.xpass_dropbacks, round(pl.xpass_sum::numeric, 4)        as xpass_sum,
    coalesce(pc.pace_snaps, 0)                                                 as pace_snaps,
    coalesce(pc.pace_seconds, 0)                                               as pace_seconds,
    coalesce(t.top_seconds, 0)                                                 as top_seconds,
    coalesce(d.drives, 0)                                                      as drives,
    coalesce(d.drive_points, 0)                                                as drive_points,
    coalesce(d.scoring_drives, 0)                                              as scoring_drives,
    coalesce(d.red_zone_trips, 0)                                              as red_zone_trips,
    ts.passing_first_downs + ts.rushing_first_downs                            as first_downs,
    ts.passing_interceptions + ts.fumbles_lost_total                           as giveaways
from plays as pl
join games as g using (game_id)
left join pace as pc using (team, game_id)
left join top as t using (team, game_id)
left join drives as d using (team, game_id)
left join {{ ref('fct_team_game') }} as ts using (team, game_id)
where pl.plays > 0
