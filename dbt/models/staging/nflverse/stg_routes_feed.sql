-- Licensed routes-run import (raw.routes_feed, plan P2-12). Empty until a provider file is
-- imported with `league-lab import-routes`. Identity resolved downstream through player_id_map.
select
    season,
    week,
    gsis_id,
    sleeper_id,
    pfr_id,
    player_name                                              as provider_player_name,
    team                                                     as provider_team,
    routes,
    targets::numeric                                         as provider_targets,
    receiving_yards::numeric                                 as provider_receiving_yards,
    provider,
    source_file,
    imported_at
from {{ source('raw', 'routes_feed') }}
