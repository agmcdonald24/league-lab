select
    league_id,
    bracket_type,
    m                                  as match_no,
    r                                  as round,
    t1                                 as roster_id_1,
    t2                                 as roster_id_2,
    w                                  as winner_roster_id,
    l                                  as loser_roster_id,
    p                                  as place_decided,
    fetched_at
from {{ source('raw', 'sleeper_bracket') }}
