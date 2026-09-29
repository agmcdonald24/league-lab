-- Plan U-10 acceptance: the sidebar's scoring label says what the two configured leagues are
-- (settings checked 2026-09-28). Forever Unclean Dynasty 2026 has a SUPER_FLEX slot and rec = 1;
-- League of Scrubs 2026, the reference league, has rec = 0.5. Pinned to those league-season ids,
-- which stay in dim_league_season after a season rollover. A row here is an expectation not met,
-- including a league-season that is not loaded (the test fails unless both are).
with expected (league_id, league_season, must_contain) as (
    values
        ('1321941740235550720', 'Forever Unclean Dynasty 2026', 'superflex'),
        ('1321941740235550720', 'Forever Unclean Dynasty 2026', 'full PPR'),
        ('1389709692405551104', 'League of Scrubs 2026 (reference)', 'half PPR')
)

select e.league_id, e.league_season, e.must_contain, d.scoring_label
from expected as e
left join {{ ref('dim_league_season') }} as d using (league_id)
where d.scoring_label is null
   or strpos(d.scoring_label, e.must_contain) = 0
