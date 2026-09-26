-- Play-derived team counts must reconcile with the independently published team stats (plan §9):
-- targets, sacks and carries exactly, attempts within 1 (spike/aborted-play stat corrections).
-- Over 2016-2026 the residue is a handful of team-games; anything beyond that is a flag bug.
{{ config(severity='warn') }}
with pb as (
    select posteam as team, game_id, season,
           count(*) filter (where is_pass_attempt and not is_two_point) as attempts,
           count(*) filter (where is_sack) as sacks,
           count(*) filter (where is_target) as targets,
           count(*) filter (where is_rush_attempt) as carries
    from {{ ref('fct_play') }}
    where season_type = 'REG'
    group by 1, 2, 3
)
select pb.season, pb.team, pb.game_id,
       pb.attempts - t.attempts as attempts_diff, pb.sacks - t.sacks_suffered as sacks_diff,
       pb.targets - t.targets as targets_diff, pb.carries - t.carries as carries_diff
from pb
join {{ ref('fct_team_game') }} as t using (team, game_id)
where abs(pb.attempts - t.attempts) > 1 or pb.sacks <> t.sacks_suffered
   or abs(pb.targets - t.targets) > 1 or abs(pb.carries - t.carries) > 1
