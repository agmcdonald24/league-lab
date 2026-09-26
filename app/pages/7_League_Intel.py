"""League Intel: how every manager plays — luck, lineup discipline, activity, roster shape."""

import streamlit as st
from lib.charts import bar_chart, color_map, heat_style, line_chart
from lib.db import query
from lib.table import howto, show
from lib.ui import freshness_banner, perspective, setup

setup("League Intel")
freshness_banner()
league_id, roster_id, members = perspective(require_team=False)

st.subheader("Manager profiles")
howto(
    "**All-play %** is each roster's win rate if it had played every other roster every week — the record its points deserve. "
    "**Expected W** turns that into wins; **Luck** is actual wins minus expected. A 2-0 team with a big negative luck number "
    "is scoring like a 1-1 team and has been getting favourable draws.",
    "**Bench pts left/wk** is how much a better lineup would have added each week. High numbers mark managers who don't sweat start/sit — "
    "useful to know when you are trading with them.",
    "**Waiver adds / FA adds / Trades / FAAB spent** show who is active and who sits still; **Failed claims** shows who is chasing the same players as you.",
    "The **QB / RB / WR / TE / K / DEF / IR** columns count how many of each the roster currently holds.",
)
prof = query(
    """select team_name, manager_name, standing, wins, losses, points_for, points_against,
              all_play_win_pct, expected_wins, luck_wins, all_play_rank,
              avg_bench_points_left, weeks_left_10_plus,
              waiver_adds, free_agent_adds, trades, failed_waiver_claims, faab_spent,
              n_qb, n_rb, n_wr, n_te, n_k, n_def, n_ir
       from analytics.mart_league_manager_profile where league_id = %s order by standing nulls last""",
    (league_id,),
)
show(prof, height=420)

c1, c2 = st.columns(2)
c1.plotly_chart(bar_chart(prof.sort_values("luck_wins"), "team_name", "luck_wins", "Schedule luck (wins above what the points deserve)", "wins", horizontal=True, y_format="+.2f"), width="stretch")
c2.plotly_chart(bar_chart(prof.sort_values("avg_bench_points_left", ascending=False), "team_name", "avg_bench_points_left", "Points left on the bench per week", "points", horizontal=True, y_format=".1f"), width="stretch")

# ------------------------------------------------------------- all-play by week
st.subheader("Weekly scoring rank")
howto("Each cell is where the roster's score ranked that week (1 = top scorer, darker = better). A roster that keeps landing in the top half "
      "but keeps losing is unlucky; the opposite is riding a soft schedule.")
apw = query(
    """select week, team_name, points, week_points_rank, all_play_wins, result
       from analytics.mart_league_all_play_week where league_id = %s order by week, team_name""",
    (league_id,),
)
if not apw.empty:
    pv = apw.pivot_table(index="team_name", columns="week", values="week_points_rank")
    pv.index.name = "Team"
    pv.columns = [f"Wk {int(c)}" for c in pv.columns]
    st.dataframe(heat_style(pv), width="stretch")
    teams = sorted(apw["team_name"].unique().tolist())
    sel = st.multiselect("Teams on the chart", teams, default=teams[:5], max_selections=8)
    st.plotly_chart(line_chart(apw[apw["team_name"].isin(sel)], "week", "points", "team_name", "Points by week", "points", y_format=".1f", colors=color_map(teams)), width="stretch")

# ------------------------------------------------------------- positional strength heatmap
st.subheader("Roster shape — starter strength rank by position")
howto("Rank of each roster's would-be starters at each position by season points per game (1 = strongest, darker = stronger). "
      "Rosters that are dark in one column and light in another are the natural trade partners.")
ps = query(
    """select team_name, position, position_rank
       from analytics.mart_league_positional_strength where league_id = %s""",
    (league_id,),
)
if not ps.empty:
    pv = ps.pivot_table(index="team_name", columns="position", values="position_rank")[["QB", "RB", "WR", "TE", "K"]]
    pv.index.name = "Team"
    st.dataframe(heat_style(pv), width="stretch")

# ------------------------------------------------------------- historical luck
st.subheader("Past seasons — record vs what the points deserved")
hist = query(
    """select l.season, a.team_name, a.manager_name, a.wins, a.losses, a.all_play_win_pct, a.expected_wins, a.luck_wins, s.is_champion
       from analytics.mart_league_all_play a
       join analytics.dim_league_season l using (league_id)
       left join analytics.mart_league_standings s using (league_id, roster_id)
       where not l.is_current_season order by l.season desc, a.luck_wins desc""",
)
show(hist)
