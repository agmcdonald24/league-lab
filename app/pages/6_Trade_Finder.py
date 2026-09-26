"""Trade Finder: where a partner is deep and you are thin, and which players are priced by box
score rather than by opportunity."""

import pandas as pd
import streamlit as st
from lib.charts import heat_style
from lib.db import query
from lib.table import howto, show
from lib.ui import freshness_banner, perspective, setup

setup("Trade Finder")
freshness_banner()
league_id, roster_id, members = perspective(require_team=True)
labels = {int(r.roster_id): f"{r.team_name} ({r.manager_name})" for r in members.itertuples()}

howto(
    "A trade works when two rosters have opposite shapes. Step 1 finds the shape; step 2 finds the players.",
    "**Positional strength** adds up season points-per-game for each roster's would-be starters at a position and ranks the league (1 = strongest). "
    "Read across a row for a roster's shape, down a column for who is deep where you are thin.",
    "**Buy low**: players producing *below* their opportunity (PPG − xPPG negative). Their manager sees a disappointing box score; the usage says otherwise.",
    "**Sell high**: your players producing *above* their opportunity. The box score is doing your negotiating — it usually won't last.",
    "None of this is a valuation model. It tells you where to look and what to say.",
    title="How to use this page",
)

# ------------------------------------------------------------- surplus / need matrix
st.subheader("Positional strength — every roster")
ps = query(
    """select roster_id, team_name, position, starter_ppg, starter_ppg_vs_median, position_rank, best_bench_ppg
       from analytics.mart_league_positional_strength where league_id = %s""",
    (league_id,),
)
rank_pivot = ps.pivot_table(index="team_name", columns="position", values="position_rank")[["QB", "RB", "WR", "TE", "K"]]
rank_pivot.index.name = "Team"
st.caption("Rank of starter points per game by position (1 = strongest, darker = stronger).")
st.dataframe(heat_style(rank_pivot), width="stretch")

mine = ps[ps["roster_id"] == roster_id].set_index("position")
weak = mine.sort_values("starter_ppg_vs_median").head(2).index.tolist()
strong = mine.sort_values("starter_ppg_vs_median", ascending=False).head(2).index.tolist()
st.info(f"Your thinnest positions vs the league median: **{', '.join(weak)}** · your deepest: **{', '.join(strong)}**")

# ------------------------------------------------------------- partner picker
partners = [r for r in members["roster_id"].tolist() if r != roster_id]
partner = st.selectbox("Trade partner", partners, format_func=lambda r: labels[int(r)])
pp = ps[ps["roster_id"] == partner].set_index("position")
fit = pd.DataFrame({
    "position": ["QB", "RB", "WR", "TE", "K"],
    "you_vs_median": [mine["starter_ppg_vs_median"].get(p) for p in ["QB", "RB", "WR", "TE", "K"]],
    "partner_vs_median": [pp["starter_ppg_vs_median"].get(p) for p in ["QB", "RB", "WR", "TE", "K"]],
    "partner_best_bench_ppg": [pp["best_bench_ppg"].get(p) for p in ["QB", "RB", "WR", "TE", "K"]],
})
fit["complementary"] = (fit["you_vs_median"] < 0) & (fit["partner_vs_median"] > 0)
st.markdown("**Shape fit with this partner** — a *Fit* marks a position where you are below the league median and they are above it.")
show(fit)

# ------------------------------------------------------------- targets on their roster
cols = """player_name, position, nfl_team, is_current_starter, injury_status, games_played, ppg_std, points_per_game_l3,
          expected_per_game, diff_per_game, target_share, carry_share, avg_offense_snap_pct, opponent, opp_rank_std"""
show_cols = ["player_name", "position", "nfl_team", "is_current_starter", "injury_status", "games_played", "ppg_std", "points_per_game_l3",
             "expected_per_game", "diff_per_game", "target_share", "carry_share", "avg_offense_snap_pct", "opponent", "opp_rank_std"]
theirs = query(
    f"""select {cols} from analytics.mart_player_availability
        where league_id = %s and rostered_by_roster_id = %s order by diff_per_game asc nulls last""",
    (league_id, partner),
)
st.subheader("Their roster — buy-low candidates first")
show(theirs, show_cols)

yours = query(
    f"""select {cols} from analytics.mart_player_availability
        where league_id = %s and rostered_by_roster_id = %s order by diff_per_game desc nulls last""",
    (league_id, roster_id),
)
st.subheader("Your roster — sell-high candidates first")
show(yours, show_cols)

# ------------------------------------------------------------- league-wide regression lists
st.subheader("League-wide: biggest gaps between opportunity and production (rostered by others)")
gap = query(
    """select player_name, position, nfl_team, rostered_by_team, is_current_starter, games_with_expected, ppg_std, expected_per_game, diff_per_game, target_share
       from analytics.mart_player_availability
       where league_id = %s and not is_free_agent and rostered_by_roster_id <> %s and coalesce(games_with_expected, 0) >= 2
         and position in ('QB','RB','WR','TE')""",
    (league_id, roster_id),
)
gap_cols = ["player_name", "position", "nfl_team", "rostered_by_team", "is_current_starter", "games_with_expected", "ppg_std", "expected_per_game", "diff_per_game", "target_share"]
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Producing below their opportunity (ask about these)**")
    show(gap.sort_values("diff_per_game").head(12), gap_cols)
with c2:
    st.markdown("**Producing above their opportunity (be wary of paying for these)**")
    show(gap.sort_values("diff_per_game", ascending=False).head(12), gap_cols)
