-- One row per league-season in the chain, with its scoring version and playoff structure.
-- `is_reference_league` marks the league whose scoring prices NFL-wide numbers (int_current_league);
-- `scoring_diff_vs_reference` lists the scoring keys where this league differs from it;
-- `scoring_label` is the one-line summary the sidebar shows (plan U-10).
with l as (select * from {{ ref('stg_sleeper__leagues') }}),

-- the chain: every season of a league links to its previous season; chain_id is the newest
-- season's league_id, so pages can list "this league's seasons" whatever the configured id
chain as (
    with recursive walk as (
        select league_id, league_id as chain_id, previous_league_id, 0 as depth
        from l
        where league_id not in (select previous_league_id from l where previous_league_id is not null)
        union all
        select p.league_id, w.chain_id, p.previous_league_id, w.depth + 1
        from walk as w
        join l as p on p.league_id = w.previous_league_id
        where w.depth < 25
    )
    select league_id, min(chain_id) as chain_id from walk group by 1
),

ref_scoring as (
    select scoring_settings from {{ ref('int_current_league') }}
),

-- every scoring key in either league, with both values; keys absent on one side count as 0
keys as (
    select l.league_id, k.key
    from l cross join lateral jsonb_object_keys(l.scoring_settings) as k(key)
    union
    select l.league_id, k.key
    from l cross join ref_scoring as r cross join lateral jsonb_object_keys(r.scoring_settings) as k(key)
),

diffs as (
    select
        k.league_id,
        -- values rounded to 3 places: Sleeper stores float32 (0.05000000074505806), which is not a difference
        string_agg(k.key || ': ' || rtrim(rtrim(round(coalesce(l.scoring_settings ->> k.key, '0')::numeric, 3)::text, '0'), '.')
                         || ' vs ' || rtrim(rtrim(round(coalesce(r.scoring_settings ->> k.key, '0')::numeric, 3)::text, '0'), '.'),
                   ', ' order by k.key) as scoring_diff_vs_reference
    from keys as k
    join l on l.league_id = k.league_id
    cross join ref_scoring as r
    where round(coalesce(l.scoring_settings ->> k.key, '0')::numeric, 3) <> round(coalesce(r.scoring_settings ->> k.key, '0')::numeric, 3)
    group by k.league_id
),

-- plan U-10: the settings that make up the one-line scoring summary. Values rounded to 3 places
-- (Sleeper stores float32); a missing rec / bonus_rec_te counts as 0, a missing pass_td is left out.
label_parts as (
    select
        l.league_id,
        l.num_teams,
        l.league_type,
        round(coalesce(l.scoring_settings ->> 'rec', '0')::numeric, 3)          as rec,
        round((l.scoring_settings ->> 'pass_td')::numeric, 3)                   as pass_td,
        round(coalesce(l.scoring_settings ->> 'bonus_rec_te', '0')::numeric, 3) as te_premium,
        exists (
            select 1 from jsonb_each_text(l.scoring_settings) as e(key, value)
            where e.key ~ '^bonus_.+_yd_' and round(e.value::numeric, 3) <> 0
        )                                                                        as has_yardage_bonus,
        (select count(*) from jsonb_array_elements_text(l.roster_positions) as rp where rp = 'SUPER_FLEX') as superflex_slots,
        (select count(*) from jsonb_array_elements_text(l.roster_positions) as rp where rp = 'QB')         as qb_slots
    from l
),

-- "12-team superflex dynasty · full PPR · 6-pt pass TD · yardage bonuses"; numbers print without
-- trailing zeros (6, 0.5); concat_ws skips the parts that do not apply
labels as (
    select
        league_id,
        concat_ws(' · ',
            concat_ws(' ',
                num_teams || '-team',
                case when superflex_slots > 0 then 'superflex'
                     when qb_slots >= 2 then qb_slots || 'QB' end,
                league_type),
            case rec when 0 then 'standard' when 0.5 then 'half PPR' when 1 then 'full PPR'
                     else rtrim(rtrim(rec::text, '0'), '.') || ' PPR' end,
            rtrim(rtrim(pass_td::text, '0'), '.') || '‑pt pass TD',   -- non-breaking hyphen: "6-pt" never splits across lines
            case when has_yardage_bonus then 'yardage bonuses' end,
            case when te_premium <> 0 then 'TE premium ' || rtrim(rtrim(te_premium::text, '0'), '.') end
        ) as scoring_label
    from label_parts
)

select
    l.league_id,
    c.chain_id,
    l.season,
    l.league_name,
    l.league_type,
    l.status,
    l.previous_league_id,
    l.draft_id,
    l.num_teams,
    l.playoff_week_start,
    l.playoff_week_start - 1                         as regular_season_weeks,
    l.playoff_teams,
    l.last_scored_leg,
    l.current_leg,
    l.trade_deadline_week,
    l.waiver_type,
    l.waiver_budget,
    l.ppr_value,
    l.scoring_settings,
    l.roster_positions,
    (select count(*) from jsonb_array_elements_text(l.roster_positions) as rp where rp <> 'BN') as starter_slots,
    l.season = (select max(season) from l)           as is_current_season,
    l.league_id = (select league_id from {{ ref('int_current_league') }}) as is_reference_league,
    d.scoring_diff_vs_reference,
    lb.scoring_label,
    l.fetched_at
from l
left join chain as c using (league_id)
left join diffs as d using (league_id)
left join labels as lb using (league_id)
