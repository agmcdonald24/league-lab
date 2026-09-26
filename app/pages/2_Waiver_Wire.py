"""Waiver Wire: free agents ranked by opportunity, not by last week's box score."""

import streamlit as st
from lib.db import query
from lib.table import howto, show
from lib.ui import freshness_banner, next_week_info, perspective, setup

setup("Waiver Wire")
freshness_banner()
league_id, roster_id, members = perspective(require_team=False)
cal = next_week_info()
if not cal.empty:
    st.caption(f"NFL {int(cal['season'])}: week {int(cal['last_completed_week'])} complete, week {int(cal['next_week'])} next.")

howto(
    "Waiver decisions are about **opportunity**, because opportunity persists and touchdowns don't. Rank by the usage columns, then check the points.",
    "**Target % / Snap %** — the player's share of his team's targets and offensive snaps. A receiver at 20%+ targets on 80%+ snaps has a real role whatever his points say.",
    "**xPPG** prices that opportunity under this league's scoring. **PPG − xPPG** well below zero = he has been unlucky; the cheap add nobody else sees.",
    "**Trend / Momentum** (from the Trends page) name the usage metrics that moved over the last three games beyond the player's own noise. Blank until game four.",
    "**1st-read share** (season and last 3) is the player's share of his team's first-read targets — where the QB looks first, from FTN charting. "
    "A free agent whose first-read share is rising before his target share is the earliest role signal on this page.",
    "**Opp rank** is next week's matchup for his position (1 = the defense that gives up the most). **Depth** is his rank on the team's latest depth chart.",
    "Injured (Out / injured reserve) players are hidden by default.",
    title="How to use this page",
)

c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1.4])
positions = c1.multiselect("Positions", ["QB", "RB", "WR", "TE", "K"], default=["RB", "WR", "TE"])
min_games = c2.number_input("Min games played", 1, 17, 2)
hide_injured = c3.checkbox("Hide Out / IR", value=True)
sort_labels = {
    "expected_per_game": "Expected PPG (opportunity)", "momentum": "Momentum (role trend, needs 4+ games)", "target_share_l3": "Target % (last 3)", "target_share_trend": "Target trend",
    "first_read_share_l3": "1st-read share (last 3)",
    "carry_share_l3": "Carry % (last 3)", "snap_pct_l3": "Snap % (last 3)", "points_per_game_l3": "PPG (last 3)", "ppg_std": "PPG (season)",
    "diff_per_game": "Most unlucky (PPG − xPPG)",
}
sort_by = c4.selectbox("Rank by", list(sort_labels), format_func=lambda k: sort_labels[k])

fa = query(
    """select a.player_name, a.position, a.nfl_team, a.roster_status, a.injury_status, a.depth_rank,
              a.games_played, a.targets_per_game, a.carries_per_game, a.target_share, a.target_share_l3, a.target_share_trend,
              a.carry_share, a.carry_share_l3, a.avg_offense_snap_pct, a.snap_pct_l3, a.first_read_share_std, a.first_read_share_l3,
              a.ppg_std, a.points_per_game_l3, a.expected_per_game, a.diff_per_game,
              a.opponent, a.is_bye, a.opp_rank_std, t.tags, t.momentum
       from analytics.mart_player_availability a
       left join analytics.mart_player_trend_tags t on t.gsis_id = a.gsis_id and t.season = a.season
       where a.league_id = %s and a.is_free_agent and a.position = any(%s) and coalesce(a.games_played, 0) >= %s""",
    (league_id, positions, int(min_games)),
)
if hide_injured:
    fa = fa[~fa["injury_status"].isin(["Out", "IR"]) & (fa["roster_status"] != "RES")]
fa = fa.sort_values(sort_by, ascending=(sort_by == "diff_per_game"), na_position="last")

st.subheader(f"Free agents · {len(fa)} players")
rec_cols = ["player_name", "position", "nfl_team", "injury_status", "depth_rank", "games_played", "tags", "momentum", "targets_per_game", "target_share",
            "target_share_l3", "first_read_share_std", "first_read_share_l3", "avg_offense_snap_pct", "snap_pct_l3", "ppg_std", "points_per_game_l3",
            "expected_per_game", "diff_per_game", "opponent", "is_bye", "opp_rank_std"]
rb_cols = ["player_name", "position", "nfl_team", "injury_status", "depth_rank", "games_played", "tags", "momentum", "carries_per_game", "carry_share",
           "carry_share_l3", "targets_per_game", "target_share", "first_read_share_l3", "avg_offense_snap_pct", "snap_pct_l3", "ppg_std", "points_per_game_l3",
           "expected_per_game", "diff_per_game", "opponent", "is_bye", "opp_rank_std"]
qbk_cols = ["player_name", "position", "nfl_team", "injury_status", "depth_rank", "games_played", "tags", "momentum", "ppg_std", "points_per_game_l3",
            "expected_per_game", "diff_per_game", "opponent", "is_bye", "opp_rank_std"]
if set(positions) <= {"RB"}:
    cols = rb_cols
elif set(positions) <= {"QB", "K"}:
    cols = qbk_cols
else:
    cols = rec_cols
show(fa, cols, height=560)

# ------------------------------------------------------------- your drop candidates
if roster_id is not None:
    st.subheader("Your bench, weakest first")
    howto("Sorted by expected PPG, then PPG. The bottom of this list is where a waiver add would come from. "
          "A player on a bye with low expected points is the usual first cut; an injured player with a strong role is not.")
    bench = query(
        """select player_name, position, nfl_team, injury_status, games_played, ppg_std, points_per_game_l3, expected_per_game,
                  target_share_l3, carry_share_l3, snap_pct_l3, opponent, is_bye, opp_rank_std
           from analytics.mart_player_availability
           where league_id = %s and rostered_by_roster_id = %s and not is_current_starter and not is_on_ir
           order by coalesce(expected_per_game, ppg_std, 0) asc""",
        (league_id, roster_id),
    )
    show(bench)

# ------------------------------------------------------------- recent league moves
st.subheader("Recent league moves")
howto("Completed waiver claims, free-agent adds, drops and trades, newest first. Useful for seeing who is chasing the same positions and what bids clear.")
tx = query(
    """select created_at, week, transaction_type, action, team_name, player_name, position, waiver_bid
       from analytics.mart_league_transactions where league_id = %s and status = 'complete'
       order by created_at desc limit 40""",
    (league_id,),
)
show(tx)
