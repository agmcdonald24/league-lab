"""Matchups: this week's lineup decisions (B4), then — each as a one-line answer with its table in an expander —
the start/sit board, the cornerbacks your receivers face, and defense vs position (plan U-13: nothing wider
than five columns outside an expander)."""

import pandas as pd
import streamlit as st
from lib.cards import decision_cards, decision_week, howto_cards, lineup_rows, lineup_table
from lib.charts import heat_style
from lib.db import query
from lib.table import detail_level, howto, show
from lib.ui import (
    align_opponents,
    current_leagues,
    current_season,
    current_week,
    freshness_banner,
    league_slots,
    perspective,
    reference_scoring_note,
    setup,
    week_first_kickoff,
)

setup("Matchups")
freshness_banner()
league_id, roster_id, members = perspective(require_team=False)
# one week rule (C1): the week every page means by "this week" (lib.ui.current_week), not mart_nfl_calendar
season = current_season(league_id)
next_week = current_week(league_id)
if season is None or next_week is None:
    st.info("The regular season is over: no matchups left to play.")
    st.stop()
first_kick = week_first_kickoff(season, next_week)
kick = first_kick.tz_convert("America/New_York") if first_kick is not None else None
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
    board = align_opponents(board, season, next_week)      # this week's opponents (the mart keys them to the calendar week)
    with st.expander("Start / sit board: every player with his matchup"):
        st.markdown(
            "- Every player on the roster with next week's opponent and where that defense ranks in points allowed to his position "
            "(**Opp rank** 1 = gives up the most, 32 = the fewest). **Opp rank (L4)** uses only the defense's last four games.\n"
            "- Read matchup rank together with **xPPG** (the player's own opportunity) — a great matchup for a player nobody throws to is still a bad start.\n"
            "- **Injury** and **Practice** are the latest official report; a Questionable tag with full practice is usually fine, "
            "a Questionable with no practice is a real risk.\n"
            "- **BYE** means no game; the player scores zero if started."
        )
        show(board, ["player_name", "position", "nfl_team", "is_current_starter", "injury_status", "practice_status", "opponent", "is_home", "is_bye",
                     "opp_rank_std", "opp_rank_l4", "opp_points_allowed_pg_std", "ppg_std", "points_per_game_l3", "expected_per_game",
                     "target_share_l3", "snap_pct_l3", "depth_rank"], height=520,
             phone_cols=["player_name", "position", "opponent", "opp_rank_std", "expected_per_game"])

    # ------------------------------------------------------------- cornerbacks: the answer line, the table behind it
    st.subheader("Cornerbacks your receivers face")
    wrs = board[board["position"].isin(["WR", "TE"]) & board["opponent"].notna()].copy()
    wrs["_r"] = pd.to_numeric(wrs["opp_rank_std"], errors="coerce")
    starters = wrs[wrs["is_current_starter"].fillna(False).astype(bool)]
    focus = starters if not starters.empty else wrs
    cb_all = query(
        """select defense, gsis_id, defender_name, depth_position, depth_rank, games, targets, targets_per_game, completion_pct_allowed,
                  yards_allowed, yards_per_target_allowed, tds_allowed, interceptions,
                  avg_passer_rating_allowed_when_targeted, adot_allowed, missed_tackles, coverage_known
           from analytics.mart_matchup_cb_context
           order by defense, array_position(array['LCB','RCB','NB','CB','SCB'], depth_position), depth_rank"""
    )

    def corners_line(opp: str) -> str:
        """'DEN's starting corners (Surtain, Moss, McMillian) have allowed an 80.4 passer rating when targeted' (targets-weighted)."""
        c = cb_all[(cb_all["defense"] == opp) & (cb_all["depth_rank"] == 1) & cb_all["coverage_known"].fillna(False).astype(bool)].copy()
        c = c.drop_duplicates("gsis_id")
        c["targets"] = pd.to_numeric(c["targets"], errors="coerce")
        c["rating"] = pd.to_numeric(c["avg_passer_rating_allowed_when_targeted"], errors="coerce")
        c = c[(c["targets"].fillna(0) > 0) & c["rating"].notna()]
        if c.empty:
            return ""
        rating = float((c["rating"] * c["targets"]).sum() / c["targets"].sum())
        names = ", ".join(str(n).split(" ")[-1] if len(str(n).split(" ")) > 1 else str(n) for n in c["defender_name"])
        return (f"{opp}'s starting corners ({names}) have allowed a {rating:.1f} passer rating on {int(c['targets'].sum())} "
                "targets this season.")

    with st.container(border=True):
        if focus.empty:
            st.markdown("No receiver on your roster has a game this week.")
        else:
            f = focus.sort_values(["_r", "expected_per_game"], ascending=[True, False])
            ranked = f.dropna(subset=["_r"])
            h = ranked.iloc[-1] if not ranked.empty else f.iloc[0]
            rank = f" (#{int(h['_r'])} vs {h['position']})" if pd.notna(h["_r"]) else ""
            who = "your starting receivers" if not starters.empty else "your receivers"
            if f["opponent"].nunique() == 1:
                st.markdown(f"**All of {who} face {h['opponent']}{rank}.**")
            else:
                line = f"**Toughest matchup for {who}: {h['player_name']} vs {h['opponent']}{rank}**"
                if not ranked.empty and ranked.iloc[0]["player_name"] != h["player_name"]:
                    e = ranked.iloc[0]
                    line += f"; easiest: {e['player_name']} vs {e['opponent']} (#{int(e['_r'])} vs {e['position']})"
                st.markdown(line + ".")
            cl = corners_line(h["opponent"])
            if cl:
                st.caption(cl + " Which corner covers whom is not in public data.")
    with st.expander("The opposing cornerbacks, receiver by receiver"):
        howto(
            "Pick one of your receivers to see the cornerbacks on the opposing defense's latest depth chart and how they have fared when targeted this season.",
            "**Rating allowed** is the passer rating on throws at that defender (lower = tougher coverage); **Y/Tgt allowed** and **Comp % allowed** say the same thing in plainer units.",
            "This is context, not an assignment: public data does not record which corner covered which receiver, and shadow coverage is invisible here. "
            "Use it to judge *how tough the secondary is*, not to predict a specific one-on-one.",
            "Coverage data starts in 2018 and comes from Pro-Football-Reference.",
        )
        # the toughest matchup first (the one the line above names), then the rest of the receivers
        by_rank = wrs.sort_values("_r", ascending=False, na_position="last")
        names = [n for n in by_rank["player_name"] if n in set(focus["player_name"])] + [n for n in by_rank["player_name"] if n not in set(focus["player_name"])]
        pick = st.selectbox("Receiver", names)
        if pick:
            opp = wrs.set_index("player_name").loc[pick, "opponent"]
            opp = opp.iloc[0] if isinstance(opp, pd.Series) else opp
            cb = cb_all[cb_all["defense"] == opp]
            st.markdown(f"**{opp} cornerbacks**")
            show(cb, ["defender_name", "depth_position", "depth_rank", "games", "targets", "targets_per_game", "completion_pct_allowed",
                      "yards_allowed", "yards_per_target_allowed", "tds_allowed", "interceptions",
                      "avg_passer_rating_allowed_when_targeted", "adot_allowed", "missed_tackles"],
                 phone_cols=["defender_name", "depth_position", "targets", "yards_per_target_allowed", "avg_passer_rating_allowed_when_targeted"])

# ------------------------------------------------------------- defense vs position: the answer line, then the tables
st.subheader("Defense vs position")
dvp = query(
    """select defense, position, games, points_allowed_per_game_std, rank_std, points_allowed_per_game_l4, rank_l4
       from analytics.mart_defense_vs_position_current order by position, rank_std""",
)
dvp_positions = [p for p in league_slots(league_id) if p in ("QB", "RB", "WR", "TE", "K")]
with st.container(border=True):
    lineup = board[board["is_current_starter"].fillna(False).astype(bool) & board["opp_rank_std"].notna()] if roster_id is not None else pd.DataFrame()
    if not lineup.empty:
        lu = lineup.assign(_r=pd.to_numeric(lineup["opp_rank_std"], errors="coerce")).sort_values("_r")
        b, w = lu.iloc[0], lu.iloc[-1]
        st.markdown(f"**Best matchup in your lineup: {b['player_name']} ({b['position']}) vs {b['opponent']}, #{int(b['_r'])} vs {b['position']}; "
                    f"toughest: {w['player_name']} ({w['position']}) vs {w['opponent']}, #{int(w['_r'])} vs {w['position']}.**")
    else:
        top = dvp[dvp["rank_std"] == 1].drop_duplicates("position").set_index("position")
        parts = [f"{p}s: {top.loc[p, 'defense']} ({float(top.loc[p, 'points_allowed_per_game_std']):.1f}/game)" for p in dvp_positions if p in top.index]
        st.markdown("**Gives up the most so far — " + " · ".join(parts) + ".**")
    st.caption("Rank 1 = the defense that gives up the most points to the position this season (the matchup you want), 32 = the fewest.")
with st.expander("Defense vs position: every defense, by position"):
    howto(
        "**Pts allowed/G** is how many fantasy points each defense has given up to opposing players at the position, per game, this season — "
        "in the reference league's scoring, like every NFL research table, so the ranks are the same for every league.",
        "**Rank** 1 = gives up the most = the matchup you want; 32 = the stingiest. The **(L4)** columns use the defense's last four games, which catches injuries and scheme changes faster.",
        "Early in the season these ranks move a lot week to week; from about week 6 they settle.",
    )
    reference_scoring_note("Points allowed and ranks in this section")
    pos = st.radio("Position", dvp_positions, horizontal=True)
    sub = dvp[dvp["position"] == pos].sort_values("rank_std")
    dvp_cols = ["defense", "games", "points_allowed_per_game_std", "rank_std", "points_allowed_per_game_l4", "rank_l4"]
    dvp_phone = ["defense", "points_allowed_per_game_std", "rank_std", "points_allowed_per_game_l4", "rank_l4"]
    st.markdown("**Gives up the most (start your players against these)**")
    show(sub.head(10), dvp_cols, phone_cols=dvp_phone)
    st.markdown("**Gives up the least**")
    show(sub.tail(10).sort_values("rank_std", ascending=False), dvp_cols, phone_cols=dvp_phone)
    # at the Phone level the heat table keeps four positions (with the defense, five columns)
    heat_positions = dvp_positions[:4] if detail_level() == "phone" else dvp_positions
    pivot = dvp.pivot_table(index="defense", columns="position", values="rank_std")[heat_positions]
    pivot.index.name = "Defense"
    st.markdown("**All defenses — rank by position (darker = gives up more)**")
    st.dataframe(heat_style(pivot), width="stretch", height=600)

# ------------------------------------------------------------- any player lookup
with st.expander("Look up any player's next matchup"):
    name = st.text_input("Player name contains", "")
    if name:
        res = query(
            """select gsis_id, player_name, position, team, roster_status, opponent, is_home, is_bye, kickoff_at,
                      opp_rank_std, opp_rank_l4, opp_points_allowed_pg_std, injury_status, injury, practice_status, depth_rank
               from analytics.mart_player_next_matchup where player_name ilike %s order by player_name limit 30""",
            (f"%{name}%",),
        )
        res = align_opponents(res, season, next_week, team_col="team")
        show(res, [c for c in res.columns if c != "gsis_id"],
             phone_cols=["player_name", "position", "opponent", "opp_rank_std", "kickoff_at"])
