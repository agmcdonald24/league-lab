select
    team_abbr,
    team_name,
    team_nick,
    team_conf                              as conference,
    team_division                          as division,
    team_color                             as color_primary,
    team_color2                            as color_secondary,
    team_logo_espn                         as logo_url,
    team_wordmark                          as wordmark_url
from {{ source('raw', 'nfl_teams') }}
