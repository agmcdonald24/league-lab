-- One row per player-week (upstream has a few duplicates; the most severe report wins).
with ranked as (
    select
        gsis_id, season, week, season_type, game_type, team, position, full_name,
        report_status, report_primary_injury, report_secondary_injury,
        practice_status, practice_primary_injury,
        row_number() over (
            partition by gsis_id, season, week
            order by case report_status when 'Out' then 0 when 'Doubtful' then 1 when 'Questionable' then 2 else 3 end,
                     case when practice_status ilike 'Did Not%' then 0 when practice_status ilike 'Limited%' then 1 else 2 end
        ) as rn
    from {{ source('raw', 'nfl_injuries') }}
    where gsis_id is not null and season >= {{ var('seasons_start') }}
)
select gsis_id, season, week, season_type, game_type, team, position, full_name,
       report_status, report_primary_injury, report_secondary_injury, practice_status, practice_primary_injury
from ranked where rn = 1
