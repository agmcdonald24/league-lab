select * from {{ source('raw', 'nfl_pfr_advstats_rush') }} where season >= {{ var('seasons_start') }}
