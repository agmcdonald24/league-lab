"""Kicker streaming comparison — realized outcomes only."""

import streamlit as st
from lib.charts import bar_chart, color_map, line_chart
from lib.db import query
from lib.table import howto, show
from lib.ui import freshness_banner, league_slots, perspective, season_picker, setup, unavailable

setup("Kickers")
freshness_banner()

current_league_id, _, _ = perspective(require_team=False)
if "K" not in league_slots(current_league_id):
    st.info("This league does not start a kicker, so there is no kicker streaming to review. Pick another league in the sidebar.")
    st.stop()
league = season_picker(current_league_id, "League season")
league_id = league["league_id"]
season = int(league["season"])

st.subheader("Season summary")
howto(
    "Did swapping kickers every week pay off? This compares what each team's *started* kicker scored.",
    "**Common weeks** are the weeks every team started a kicker, so the totals are fair. **vs week avg** is a team's kicker "
    "minus the average started kicker that week: above zero, its kicker choices beat the league.",
    "**Kickers used**, **Changes** and **Acquired** show how much swapping it took. One kicker all year and a top-3 total? "
    "That team never needed to stream.",
    "It shows what happened, not what a different pick would have scored.",
)
summary = query(
    """select team_name, manager_name, weeks_started_k, common_weeks, total_points_common_weeks,
              avg_points_common_weeks, stddev_points_common_weeks, avg_points_vs_week_avg,
              distinct_kickers_started, kicker_changes, kicker_acquisitions, rank_common_weeks
       from analytics.mart_league_kicker_summary where league_id = %s order by rank_common_weeks""",
    (league_id,),
)
show(summary)
if not summary.empty:
    st.plotly_chart(bar_chart(summary, "team_name", "total_points_common_weeks", "Started-kicker points, common weeks", "points", horizontal=True), width="stretch")

weekly = query(
    """select week, team_name, kicker_name, nfl_team, points, round(week_avg_started_k::numeric, 2) as week_avg,
              week_rank, changed_kicker
       from analytics.mart_league_kicker_week where league_id = %s order by week, team_name""",
    (league_id,),
)
st.subheader("Week by week")
teams = sorted(weekly["team_name"].dropna().unique().tolist())
pick = st.multiselect("Teams", teams, default=teams[:6], max_selections=8)
sub = weekly[weekly["team_name"].isin(pick)]
if not sub.empty:
    st.plotly_chart(line_chart(sub, "week", "points", "team_name", "Started kicker points by week", "points", y_format=".1f", colors=color_map(teams)), width="stretch")
show(weekly, height=420)

unavailable("Streaming counterfactuals", "Reconstructed waiver availability and 'best available kicker' simulations are later work; "
            "only started points are compared here.")
