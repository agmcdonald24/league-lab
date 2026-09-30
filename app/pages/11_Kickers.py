"""Kicker streaming comparison — realized outcomes only."""

import streamlit as st
from lib.charts import bar_chart, color_map, line_chart
from lib.db import query
from lib.table import howto, show
from lib.ui import freshness_banner, league_slots, perspective, season_picker, setup, unavailable

setup("Kickers")
freshness_banner()

current_league_id, my_roster, _ = perspective(require_team=False)
if "K" not in league_slots(current_league_id):
    st.info("This league does not start a kicker, so there is no kicker streaming to review. Pick another league in the sidebar.")
    st.stop()
league = season_picker(current_league_id, "League season")
league_id = league["league_id"]
season = int(league["season"])

st.subheader("Season summary")
howto(
    "Did streaming kickers actually pay? This compares what each roster's *started* kicker scored.",
    "**Common weeks** are the weeks in which every roster started a kicker, so totals compare like with like. "
    "**vs week avg** is the roster's kicker minus the league's average started kicker that week.",
    "**Kickers used**, **Changes** and **Acquired** show how much churn it took. A roster with one kicker all year and a top-3 total didn't need to stream.",
    "This reports what happened. It does not reconstruct who was on waivers or simulate the alternative.",
)
summary = query(
    """select roster_id, team_name, manager_name, weeks_started_k, common_weeks, total_points_common_weeks,
              avg_points_common_weeks, stddev_points_common_weeks, avg_points_vs_week_avg,
              distinct_kickers_started, kicker_changes, kicker_acquisitions, rank_common_weeks
       from analytics.mart_league_kicker_summary where league_id = %s order by rank_common_weeks""",
    (league_id,),
)
with st.container(border=True):     # the answer first (U-13); the table behind it
    if summary.empty:
        st.markdown("**No started kickers scored yet this season.**")
    else:
        best = summary.sort_values("rank_common_weeks").iloc[0]
        line = (f"**Most started-kicker points: {best['team_name']}, {float(best['total_points_common_weeks'] or 0):.1f} "
                f"in {int(best['common_weeks'] or 0)} common weeks.**")
        mine = summary[summary["roster_id"] == my_roster] if my_roster is not None and league_id == current_league_id else summary.iloc[0:0]
        if not mine.empty and mine.iloc[0]["team_name"] != best["team_name"]:
            m = mine.iloc[0]
            line += f" Yours: {int(m['rank_common_weeks'])} of {len(summary)} ({float(m['total_points_common_weeks'] or 0):.1f})."
        st.markdown(line)
with st.expander("Every roster's kickers, every column"):
    show(summary, [c for c in summary.columns if c != "roster_id"],
         phone_cols=["team_name", "total_points_common_weeks", "avg_points_vs_week_avg", "kicker_changes", "rank_common_weeks"])
if not summary.empty:
    st.plotly_chart(bar_chart(summary, "team_name", "total_points_common_weeks", "Started-kicker points, common weeks", "points", horizontal=True), width="stretch")

weekly = query(
    """select week, team_name, gsis_id, kicker_name, nfl_team, points, round(week_avg_started_k::numeric, 2) as week_avg,
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
with st.expander("Every started kicker, week by week"):
    show(weekly, [c for c in weekly.columns if c != "gsis_id"], height=420, phone_cols=["week", "team_name", "kicker_name", "points", "week_rank"])

unavailable("Streaming counterfactuals", "Reconstructed waiver availability and 'best available kicker' simulations are later work; "
            "only started points are compared here.")
