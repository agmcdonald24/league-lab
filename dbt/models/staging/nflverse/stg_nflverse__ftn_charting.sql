-- FTN Data play charting (CC-BY-SA 4.0; attribution required), 2022+.
--
-- read_thrown coding, verified against the data (docs/METRICS.md "First-read target share"):
--   '1' = first (primary) read     '2' = second read or later
--   'CHK' = checkdown              'DES' = designed throw (screens, many RPOs)
--   'SD'  = scramble drill         '0' (2023+) / NULL (2022) = not charted / not a throw
-- The nflreadr dictionary describes '0' as first read from 2023; in every season '0' sits on
-- run/kick/punt plays and on ~2-3% of pass attempts while '1' is the majority code on targeted
-- throws (~52%), exactly where 2022 has NULL. We follow the data, not the dictionary.
select
    nflverse_game_id                                         as game_id,
    nflverse_play_id                                         as play_id,
    season,
    week,
    ftn_game_id,
    ftn_play_id,
    nullif(trim(read_thrown), '')                            as read_thrown_raw,
    case nullif(trim(read_thrown), '')
        when '1' then 'first'
        when '2' then 'later'
        when 'CHK' then 'checkdown'
        when 'DES' then 'designed'
        when 'SD' then 'scramble_drill'
        else null                                            -- '0' / NULL: uncharted
    end                                                      as read_thrown,
    starting_hash,
    qb_location,
    n_offense_backfield,
    n_defense_box,
    n_blitzers,
    n_pass_rushers,
    is_no_huddle,
    is_motion,
    is_play_action,
    is_screen_pass,
    is_rpo,
    is_trick_play,
    is_qb_out_of_pocket,
    is_qb_sneak,
    is_qb_fault_sack,
    is_throw_away,
    is_interception_worthy,
    is_catchable_ball,
    is_contested_ball,
    is_created_reception,
    is_drop,
    date_pulled                                              as charted_at,
    _fetched_at                                              as source_fetched_at
from {{ source('raw', 'nfl_ftn_charting') }}
where season >= {{ var('seasons_start') }}
