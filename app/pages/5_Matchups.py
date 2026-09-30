"""Matchups: next week's opponents for a roster, defense-vs-position, and cornerback coverage context."""

import pandas as pd
import streamlit as st
from lib.cards import decision_cards, decision_week, howto_cards, lineup_rows, lineup_table
from lib.charts import heat_style
from lib.db import query
from lib.table import howto, show
from lib.ui import (
    current_leagues,
    freshness_banner,
    league_slots,
    next_week_info,
    perspective,
    reference_scoring_note,
    setup,
)

setup("Matchups")
freshness_banner()
league_id, roster_id, members = perspective(require_team=False)
cal = next_week_info()
if cal.empty:
    st.stop()
season, next_week = int(cal["season"]), int(cal["next_week"])
kick = pd.Timestamp(cal["next_week_first_kickoff"]).tz_convert("America/New_York") if pd.notna(cal["next_week_first_kickoff"]) else None
st.caption(f"NFL {season} · week {next_week}" + (f" · first kickoff {kick:%a %b %-d, %-I:%M %p} ET" if kick is not None else ""))

# ------------------------------------------------------------- lineup decisions, then the start/sit board (plan B4)
if roster_id is not None:
    # the same cards as Home's My Week (lib/cards.py): the closest calls of the best lineup (B1), for the
    # first week with a game still to kick off
    lu_season = int(current_leagues().set_index("league_id").loc[league_id, "season"])
    lu_week = decision_week(lu_season)
    if lu_week is not None:
        st.subheader(f"Your lineup decisions — week {lu_week}")
        lu_rows = lineup_rows(league_id, lu_season, lu_week, roster_id)
        decision_cards(league_id, roster_id, lu_week, lu_season, rows=lu_rows)
        with st.expander("Your best lineup this week"):
            lineup_table(lu_rows, full=True)
        howto_cards()

    board = query(
        """select gsis_id, player_name, position, nfl_team, is_current_starter, injury_status, practice_status, is_bye,
                  opponent, is_home, opp_rank_std, opp_rank_l4, opp_points_allowed_pg_std,
                  ppg_std, points_per_game_l3, expected_per_game, target_share_l3, snap_pct_l3, depth_rank
           from analytics.mart_player_availability
           where league_id = %s and rostered_by_roster_id = %s
           order by array_position(array['QB','RB','WR','TE','K'], position), coalesce(expected_per_game, ppg_std) desc nulls last""",
        (league_id, roster_id),
    )
    with st.expander("Start / sit board: every player with his matchup"):
        st.markdown(
            "- Every player on your roster with next week's opponent. **Opp rank** 1 = the defense that gives up the most to his "
            "position (the matchup you want), 32 = the fewest; **(L4)** uses only its last 4 games.\n"
            "- Weigh the matchup against his work: **xPPG** (expected points per game) is what his targets and carries are usually "
            "worth. A great matchup for a player nobody throws to is still a bad start.\n"
            "- **Injury** and **Practice** are the latest official report: Questionable with a full practice is usually fine, "
            "Questionable with no practice is a real risk.\n"
            "- **BYE** means no game: he scores zero if you start him."
        )
        show(board, ["player_name", "position", "nfl_team", "is_current_starter", "injury_status", "practice_status", "opponent", "is_home", "is_bye",
                     "opp_rank_std", "opp_rank_l4", "opp_points_allowed_pg_std", "ppg_std", "points_per_game_l3", "expected_per_game",
                     "target_share_l3", "snap_pct_l3", "depth_rank"], height=520)

    st.subheader("Cornerback context for a receiver")
    howto(
        "Pick one of your receivers to see the cornerbacks he is likely to face and how they have done when targeted this season.",
        "**Rating allowed** is the quarterback rating on throws at that defender: lower = tougher coverage. **Y/Tgt allowed** "
        "(yards per throw at him) and **Comp % allowed** say the same in plainer numbers.",
        "Use it to judge *how tough the secondary is*, not to call a one-on-one: public data does not say which corner covered "
        "which receiver.",
        "Coverage numbers come from Pro-Football-Reference and start in 2018.",
    )
    wrs = board[board["position"].isin(["WR", "TE"]) & board["opponent"].notna()]
    pick = st.selectbox("Receiver", wrs["player_name"].tolist() if not wrs.empty else [])
    if pick:
        opp = wrs.set_index("player_name").loc[pick, "opponent"]
        cb = query(
            """select defender_name, depth_position, depth_rank, games, targets, targets_per_game, completion_pct_allowed,
                      yards_allowed, yards_per_target_allowed, tds_allowed, interceptions,
                      avg_passer_rating_allowed_when_targeted, adot_allowed, missed_tackles
               from analytics.mart_matchup_cb_context where defense = %s
               order by array_position(array['LCB','RCB','NB','CB','SCB'], depth_position), depth_rank""",
            (opp,),
        )
        st.markdown(f"**{opp} cornerbacks**")
        show(cb)

# ------------------------------------------------------------- defense vs position table
st.subheader("Defense vs position")
howto(
    "**Start players against the defenses at the top** of the \"gives up the most\" list; be wary of the bottom one.",
    "**Pts allowed/G** is the fantasy points each defense gives up to that position per game this season, on one scale for every "
    "league. **Rank** 1 = gives up the most (the matchup you want), 32 = the stingiest.",
    "The **(L4)** columns use only the defense's last 4 games: they catch an injury or a new scheme sooner.",
    "Early in the season these ranks jump around; from about week 6 they settle.",
)
reference_scoring_note("Points allowed and ranks in this section")
dvp = query(
    """select defense, position, games, points_allowed_per_game_std, rank_std, points_allowed_per_game_l4, rank_l4
       from analytics.mart_defense_vs_position_current order by position, rank_std""",
)
dvp_positions = [p for p in league_slots(league_id) if p in ("QB", "RB", "WR", "TE", "K")]
pos = st.radio("Position", dvp_positions, horizontal=True)
sub = dvp[dvp["position"] == pos].sort_values("rank_std")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Gives up the most (start your players against these)**")
    show(sub.head(10), ["defense", "games", "points_allowed_per_game_std", "rank_std", "points_allowed_per_game_l4", "rank_l4"])
with c2:
    st.markdown("**Gives up the least**")
    show(sub.tail(10).sort_values("rank_std", ascending=False), ["defense", "games", "points_allowed_per_game_std", "rank_std", "points_allowed_per_game_l4", "rank_l4"])

pivot = dvp.pivot_table(index="defense", columns="position", values="rank_std")[dvp_positions]
pivot.index.name = "Defense"
st.markdown("**All defenses — rank by position (darker = gives up more)**")
st.dataframe(heat_style(pivot), width="stretch", height=600)

# ------------------------------------------------------------- any player lookup
st.subheader("Look up any player's next matchup")
name = st.text_input("Player name contains", "")
if name:
    res = query(
        """select player_name, position, team, roster_status, opponent, is_home, is_bye, kickoff_at,
                  opp_rank_std, opp_rank_l4, opp_points_allowed_pg_std, injury_status, injury, practice_status, depth_rank
           from analytics.mart_player_next_matchup where player_name ilike %s order by player_name limit 30""",
        (f"%{name}%",),
    )
    show(res)
