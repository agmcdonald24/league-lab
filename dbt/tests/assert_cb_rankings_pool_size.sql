-- Plan R-14: the cornerback rank the Matchups card quotes (window 'two_seasons' of the latest season) ranks at
-- least 48 corners (a starter pool: two outside corners per team is 64), and every completed season's own
-- window ranks at least 48 too. A smaller pool means coverage snaps or the cornerback filter broke.
{{ config(severity='error') }}
with latest as (
    select max(season) as season from {{ ref('mart_cb_rankings') }}
),

pools as (
    select season, window_label, count(*) filter (where is_ranked) as n_ranked
    from {{ ref('mart_cb_rankings') }}
    where season >= 2019
    group by 1, 2
)

select p.*
from pools as p
where (p.window_label = 'two_seasons' and p.season = (select season from latest) and p.n_ranked < 48)
   or (p.window_label = 'season' and p.season < (select season from latest) and p.n_ranked < 48)
