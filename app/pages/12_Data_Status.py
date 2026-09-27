"""Data status: freshness, coverage, failures, identity quarantine and the metric registry (plan §8.6)."""

import streamlit as st
from lib.db import query
from lib.table import howto, show
from lib.ui import setup

setup("Data Status", icon="🧪")

st.subheader("Sources")
howto("One row per dataset League Lab loads. **Partitions** are usually seasons. **Last status** is the most recent attempt; "
      "a failed attempt never replaces good data, so a failure here means *stale*, not *wrong*. `make refresh` retries.")
status = query(
    """select source, dataset, partitions, rows_loaded, first_partition, last_partition, last_loaded_at,
              last_status, last_attempt_at, failures_7d, last_failure_at, last_error
       from analytics.mart_data_status order by source, dataset"""
)
show(status)
if (status["failures_7d"].fillna(0) > 0).any():
    st.warning("Some partitions failed to load in the last 7 days. Previous good data was kept for those partitions; "
               "run `make status` for the manifest and `make refresh` to retry.")

st.subheader("Coverage by season")
cov = query("""select season, scheduled_games, final_games, through_reg_week, games_with_player_stats, games_with_snaps,
                      play_by_play_status, ftn_charting_status, participation_status, routes_status, leagues, league_scored_weeks
               from analytics.mart_coverage order by season""")
st.caption("Every source per season. 'not published yet' (participation) means the NFL releases that season's file after its "
           "postseason; 'no licensed feed' (routes) means the proxy from participation is what the pages use.")
st.dataframe(cov, hide_index=True, width="stretch", column_config={
    "season": "Season", "scheduled_games": "Games", "final_games": "Final", "through_reg_week": "Through wk",
    "games_with_player_stats": "Games w/ stats", "games_with_snaps": "Games w/ snaps", "play_by_play_status": "Play-by-play",
    "ftn_charting_status": "FTN charting (first reads)", "participation_status": "Participation (routes proxy)",
    "routes_status": "Licensed routes", "leagues": "Leagues", "league_scored_weeks": "League weeks scored"})

st.subheader("Identity quarantine")
q = query("select issue, count(*) as rows from analytics.player_id_quarantine group by issue order by 2 desc")
st.dataframe(q, hide_index=True, width="stretch")
with st.expander("Show quarantined rows"):
    st.dataframe(query("select * from analytics.player_id_quarantine order by issue, gsis_id, sleeper_id limit 500"),
                 hide_index=True, width="stretch")

st.subheader("Recent load attempts")
recent = query(
    """select started_at, source, dataset, partition_key, status, row_count, left(error, 120) as error, code_version
       from ops.load_manifest order by load_id desc limit 100"""
)
st.dataframe(recent, hide_index=True, width="stretch", height=360)

st.subheader("Metric registry")
st.dataframe(query("select metric, version, status, numerator, denominator, grain, notes from analytics_seeds.metric_registry order by status, metric"),
             hide_index=True, width="stretch")

st.subheader("Attribution")
st.markdown(
    "NFL data: **nflverse** (nflverse-data releases) and the **dynastyprocess** player-id crosswalk. "
    "League data: **Sleeper** public API. FTN charting (first reads, catchable balls, drops) is CC-BY-SA 4.0, attributed to "
    "*FTN Data via nflverse*. Check each source's terms before redistributing any of this data."
)
