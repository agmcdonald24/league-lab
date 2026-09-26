-- Accepted provider-id mappings for a canonical player (gsis_id). One row per gsis_id and one
-- per sleeper_id. `resolution` says whether the pair was uncontested or confirmed by matching
-- provider names when another candidate existed.
select
    gsis_id,
    sleeper_id,
    pfr_id,
    esb_id,
    sources      as sleeper_map_sources,
    source_count as sleeper_map_source_count,
    resolution
from {{ ref('int_player_id_map') }}
where resolution in ('accepted', 'accepted_by_name_confirmation', 'accepted_by_source_majority')
