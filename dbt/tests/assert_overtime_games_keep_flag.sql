-- Overtime games are flagged from the schedule and never inferred from stats.
select game_id from {{ ref('dim_game') }}
where went_to_overtime and (total_points is null and is_final)
