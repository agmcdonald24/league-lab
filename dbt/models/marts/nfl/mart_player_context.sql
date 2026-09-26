{{ config(indexes=[{'columns': ['gsis_id', 'season', 'context_type']}, {'columns': ['season', 'season_type', 'context_type', 'bucket']}]) }}
-- Player x season x context bucket (plan §6 context splits): targets, carries, routes proxy and
-- first-read targets inside each bucket, next to the team's totals in the SAME bucket over the
-- SAME games (the games the player appeared in). Buckets: half (H1/H2/OT), pre-play score state,
-- down-and-distance, field zone, and QB on the play (dropbacks only).
--
-- Rows exist for every bucket the player's team saw in his games, so a zero is a real zero and a
-- missing bucket means the team never faced it. Routes proxy is NULL where participation is
-- missing (the current season until its file is published).
with long as (
    select * from {{ ref('int_play_context_long') }}
),

-- games the player appeared in, with his team that game
appearances as (
    select gsis_id, game_id, season, season_type, team, player_name, position
    from {{ ref('fct_player_game') }}
    where played
),

team_bucket_game as (
    select
        team, game_id, context_type, bucket,
        count(*) filter (where is_dropback)                    as team_dropbacks,
        count(*) filter (where is_target)                      as team_targets,
        count(*) filter (where is_rush_attempt)                as team_carries,
        count(*) filter (where is_first_read_target)           as team_first_read_targets,
        count(*) filter (where is_charted_target)              as team_charted_targets
    from long
    group by 1, 2, 3, 4
),

player_bucket_game as (
    select
        receiver_player_id                                     as gsis_id,
        game_id, context_type, bucket,
        count(*) filter (where is_target)                      as targets,
        count(*) filter (where is_target and is_complete)      as receptions,
        sum(receiving_yards) filter (where is_target)          as receiving_yards,
        sum(air_yards) filter (where is_target)                as air_yards,
        count(*) filter (where is_first_read_target)           as first_read_targets,
        0::bigint                                              as carries,
        0::numeric                                             as rushing_yards
    from long
    where receiver_player_id is not null
    group by 1, 2, 3, 4
    union all
    select
        rusher_player_id, game_id, context_type, bucket,
        0, 0, 0, 0, 0,
        count(*) filter (where is_rush_attempt),
        sum(rushing_yards) filter (where is_rush_attempt)
    from long
    where rusher_player_id is not null
    group by 1, 2, 3, 4
),

-- routes proxy per bucket: dropbacks in the bucket the player was on the field for
routes_bucket_game as (
    select
        b.gsis_id, l.game_id, l.context_type, l.bucket,
        count(*)                                               as routes_proxy
    from long as l
    join {{ ref('bridge_play_participation') }} as b using (game_id, play_id)
    where l.is_dropback
    group by 1, 2, 3, 4
),

participation_games as (
    select distinct game_id from {{ ref('bridge_play_participation') }}
),

joined as (
    select
        a.gsis_id, a.season, a.season_type, a.player_name, a.position,
        t.context_type, t.bucket, a.game_id,
        t.team_dropbacks, t.team_targets, t.team_carries, t.team_first_read_targets, t.team_charted_targets,
        coalesce(pb.targets, 0) as targets, coalesce(pb.receptions, 0) as receptions,
        coalesce(pb.receiving_yards, 0) as receiving_yards, coalesce(pb.air_yards, 0) as air_yards,
        coalesce(pb.first_read_targets, 0) as first_read_targets,
        coalesce(pb.carries, 0) as carries, coalesce(pb.rushing_yards, 0) as rushing_yards,
        case when pg.game_id is not null then coalesce(r.routes_proxy, 0) end as routes_proxy,
        case when pg.game_id is not null then t.team_dropbacks end as team_dropbacks_with_participation
    from appearances as a
    join team_bucket_game as t on t.team = a.team and t.game_id = a.game_id
    left join (
        select gsis_id, game_id, context_type, bucket,
               sum(targets) as targets, sum(receptions) as receptions, sum(receiving_yards) as receiving_yards,
               sum(air_yards) as air_yards, sum(first_read_targets) as first_read_targets,
               sum(carries) as carries, sum(rushing_yards) as rushing_yards
        from player_bucket_game group by 1, 2, 3, 4
    ) as pb on pb.gsis_id = a.gsis_id and pb.game_id = a.game_id and pb.context_type = t.context_type and pb.bucket = t.bucket
    left join routes_bucket_game as r on r.gsis_id = a.gsis_id and r.game_id = a.game_id and r.context_type = t.context_type and r.bucket = t.bucket
    left join participation_games as pg on pg.game_id = a.game_id
    where a.position in ('QB', 'RB', 'WR', 'TE')
)

select
    gsis_id, season, season_type, player_name, position, context_type, bucket,
    count(distinct game_id)                                    as games,
    sum(targets)                                               as targets,
    sum(receptions)                                            as receptions,
    sum(receiving_yards)                                       as receiving_yards,
    sum(air_yards)                                             as air_yards,
    sum(first_read_targets)                                    as first_read_targets,
    sum(carries)                                               as carries,
    sum(rushing_yards)                                         as rushing_yards,
    sum(routes_proxy)                                          as routes_proxy,
    sum(team_dropbacks)                                        as team_dropbacks,
    sum(team_targets)                                          as team_targets,
    sum(team_carries)                                          as team_carries,
    sum(team_first_read_targets)                               as team_first_read_targets,
    sum(team_charted_targets)                                  as team_charted_targets,
    sum(team_dropbacks_with_participation)                     as team_dropbacks_with_participation,
    case when sum(team_targets) > 0 then round(sum(targets)::numeric / sum(team_targets), 4) end            as target_share,
    case when sum(team_carries) > 0 then round(sum(carries)::numeric / sum(team_carries), 4) end            as carry_share,
    case when sum(team_first_read_targets) > 0 then round(sum(first_read_targets)::numeric / sum(team_first_read_targets), 4) end as first_read_target_share,
    case when sum(team_dropbacks_with_participation) > 0 then round(sum(routes_proxy)::numeric / sum(team_dropbacks_with_participation), 4) end as route_participation,
    case when sum(routes_proxy) > 0 then round(sum(targets)::numeric / sum(routes_proxy), 4) end            as tprr_proxy,
    case when sum(routes_proxy) > 0 then round(sum(receiving_yards)::numeric / sum(routes_proxy), 2) end    as yprr_proxy,
    case when sum(targets) > 0 then round(sum(receiving_yards)::numeric / sum(targets), 2) end              as yards_per_target,
    case when sum(targets) > 0 then round(sum(air_yards)::numeric / sum(targets), 2) end                    as adot,
    case when sum(carries) > 0 then round(sum(rushing_yards)::numeric / sum(carries), 2) end                as yards_per_carry
from joined
group by 1, 2, 3, 4, 5, 6, 7
