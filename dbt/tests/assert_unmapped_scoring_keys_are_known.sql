-- Every non-zero scoring key in any league-season must be either mapped in scoring_stat_map or
-- an expected team-defense key. A new key (e.g. a bonus) would otherwise silently under-count.
{{ config(severity='warn') }}
with keys as (
    select league_id, scoring_key, weight from {{ ref('stg_sleeper__scoring_settings') }} where weight <> 0
),
mapped as (select sleeper_key from {{ ref('scoring_stat_map') }})
select k.*
from keys as k
left join mapped as m on m.sleeper_key = k.scoring_key
where m.sleeper_key is null
  and k.scoring_key not in ('sack','int','ff','fum_rec','def_td','safe','blk_kick','def_st_td','def_st_ff',
                            'def_st_fum_rec','st_ff','st_fum_rec','def_2pt','def_kr_yd','def_pr_yd',
                            'pts_allow_0','pts_allow_1_6','pts_allow_7_13','pts_allow_14_20','pts_allow_21_27',
                            'pts_allow_28_34','pts_allow_35p','pts_allow','yds_allow','yds_allow_0_100',
                            'yds_allow_100_199','yds_allow_200_299','yds_allow_300_349','yds_allow_350_399',
                            'yds_allow_400_449','yds_allow_450_499','yds_allow_500_549','yds_allow_550p')
