select * from {{ source('raw', 'nfl_pfr_advstats_pass') }} where season >= {{ var('seasons_start') }}
