"""League overview: standings, weekly scores, matchups, transactions, draft review."""

import streamlit as st
from lib.charts import bar_chart, color_map, line_chart
from lib.db import query
from lib.table import howto, show
from lib.ui import freshness_banner, league_seasons, setup

setup("League")
freshness_banner()

ls = league_seasons()
if ls.empty:
    st.warning("No league data loaded. Run `make ingest-sleeper` and `make build`.")
    st.stop()

season = st.selectbox("Season", ls["season"].tolist(), format_func=lambda s: f"{s} · {ls.set_index('season').loc[s, 'league_name']}")
league = ls.set_index("season").loc[season]
league_id = league["league_id"]

tab_standings, tab_weekly, tab_matchups, tab_tx, tab_draft = st.tabs(
    ["Standings", "Weekly scores", "Matchups & lineups", "Transactions", "Draft review"]
)

with tab_standings:
    howto("Regular-season record from scored weeks. **Lineup eff.** is points scored as a share of the best lineup available each week "
          "(Sleeper's 'max points'). **Std dev** is week-to-week volatility — a high-variance roster is dangerous in the playoffs and fragile before them.")
    standings = query(
        """select standing, team_name, manager_name, wins, losses, ties, points_for, points_against,
                  avg_points, stddev_points, best_week, worst_week, lineup_efficiency, is_champion
           from analytics.mart_league_standings where league_id = %s order by standing""",
        (league_id,),
    )
    show(standings)
    st.plotly_chart(bar_chart(standings, "team_name", "points_for", "Regular-season points for", "points", horizontal=True), width="stretch")

with tab_weekly:
    weekly = query(
        """select m.week, d.team_name, m.points, m.opponent_points, m.result, m.week_type
           from analytics.fct_league_matchup m
           join analytics.dim_league_member d using (league_id, roster_id)
           where m.league_id = %s and m.is_scored order by m.week, d.team_name""",
        (league_id,),
    )
    if weekly.empty:
        st.info("No scored weeks yet for this season.")
    else:
        teams = sorted(weekly["team_name"].unique().tolist())
        pick = st.multiselect("Teams (up to 8 for a readable chart)", teams, default=teams[:8], max_selections=8)
        sub = weekly[weekly["team_name"].isin(pick)]
        st.plotly_chart(line_chart(sub, "week", "points", "team_name", "Points by week", "points", colors=color_map(teams)), width="stretch")
        pivot = weekly.pivot_table(index="team_name", columns="week", values="points").round(1)
        pivot.index.name = "Team"
        pivot.columns = [f"Wk {int(c)}" for c in pivot.columns]
        st.dataframe(pivot, width="stretch")

with tab_matchups:
    wk = st.slider("Week", 1, int(max(league["last_scored_leg"] or 1, 1)), int(league["last_scored_leg"] or 1))
    mu = query(
        """select m.matchup_id, d.team_name, m.points, m.result, m.week_type
           from analytics.fct_league_matchup m
           join analytics.dim_league_member d using (league_id, roster_id)
           where m.league_id = %s and m.week = %s order by m.matchup_id, m.points desc""",
        (league_id, wk),
    )
    show(mu)
    lineup_team = st.selectbox("Show a lineup", sorted(mu["team_name"].unique().tolist()) if not mu.empty else [])
    if lineup_team:
        howto("**Points** are what Sleeper scored. **Recomputed** is the same week rebuilt from NFL statistics under this season's scoring — "
              "the two agree to the decimal for this league, which is how we know the scoring map is right. Blank for team defenses.")
        lineup = query(
            """select l.slot, l.player_name, l.position, l.nfl_team, l.points_observed, l.points_recomputed, l.is_starter
               from analytics.league_player_week l
               join analytics.dim_league_member d using (league_id, roster_id)
               where l.league_id = %s and l.week = %s and d.team_name = %s
               order by l.is_starter desc, l.slot_index nulls last, l.points_observed desc""",
            (league_id, wk, lineup_team),
        )
        show(lineup)

with tab_tx:
    tx = query(
        """select created_at, week, transaction_type, status, action, team_name, player_name, position, waiver_bid
           from analytics.mart_league_transactions where league_id = %s order by created_at desc, transaction_id, action""",
        (league_id,),
    )
    c1, c2 = st.columns(2)
    types = c1.multiselect("Type", sorted(tx["transaction_type"].dropna().unique().tolist()), default=None)
    only_complete = c2.checkbox("Completed only", value=True)
    view = tx if not types else tx[tx["transaction_type"].isin(types)]
    if only_complete:
        view = view[view["status"] == "complete"]
    show(view, ["created_at", "week", "transaction_type", "action", "team_name", "player_name", "position", "waiver_bid"], height=480)

with tab_draft:
    howto("Every pick with what the player went on to do. **Season pts** uses the current league scoring so drafts from different years compare; "
          "**Pts while started** is what he actually scored for whoever started him in this league. "
          "**Pos rank by pick** vs **Pos rank by pts** is the hit/miss column: a WR taken 8th at his position who finished 2nd was a steal.")
    draft = query(
        """select pick_no, round, team_name, player_name, position, drafted_team, is_keeper,
                  nfl_reg_games_played, nfl_reg_points_current_scoring, position_rank_by_pick, position_rank_by_points,
                  points_started_for_any_roster
           from analytics.mart_league_draft where league_id = %s order by pick_no""",
        (league_id,),
    )
    show(draft, height=520)
