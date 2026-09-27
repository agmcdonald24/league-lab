"""Team Hub: one roster seen through every mart — record, luck, lineup discipline, roster usage,
next matchups, keeper facts, positional strength."""

import pandas as pd
import streamlit as st
from lib.charts import bar_chart, line_chart
from lib.db import query
from lib.table import howto, show
from lib.ui import freshness_banner, league_seasons, perspective, setup

setup("Team Hub")
freshness_banner()
league_id, roster_id, members = perspective(require_team=True)
team = members.set_index("roster_id").loc[roster_id]

# ---------------------------------------------------------------- header metrics
prof = query("select * from analytics.mart_league_manager_profile where league_id = %s and roster_id = %s", (league_id, roster_id))
st.subheader(f"{team['team_name']} · {team['manager_name']}")
if not prof.empty:
    p = prof.iloc[0]
    c = st.columns(6)
    c[0].metric("Record", f"{int(p['wins'] or 0)}-{int(p['losses'] or 0)}", help="Regular-season record over scored weeks")
    c[1].metric("Standing", int(p["standing"]) if pd.notna(p["standing"]) else "—")
    c[2].metric("All-play", f"{p['all_play_win_pct']:.0%}" if pd.notna(p["all_play_win_pct"]) else "—",
                help="Win rate if you had played every roster every week — the record your points deserve")
    c[3].metric("Luck", f"{p['luck_wins']:+.2f} wins" if pd.notna(p["luck_wins"]) else "—",
                help="Actual wins minus the wins your points deserve. Positive = the schedule has helped you")
    c[4].metric("Left on bench / wk", f"{p['avg_bench_points_left']:.1f}" if pd.notna(p["avg_bench_points_left"]) else "—",
                help="Points per week your best possible lineup would have added")
    c[5].metric("FAAB spent", int(p["faab_spent"] or 0))

# ---------------------------------------------------------------- roster table
st.subheader("Roster")
howto(
    "**PPG** is what the player has scored per game under this league's scoring; **xPPG** is what his opportunity "
    "(targets, air yards, carries, field position) was worth under the same scoring.",
    "**PPG − xPPG** below zero means he has been unlucky relative to his usage — that tends to improve. Above zero means "
    "he has been scoring more than his usage supports — that tends to cool off.",
    "**Target %** and **Snap %** are the usage that drives points. The **(L3)** versions cover the last three games; "
    "compare them with the season number to spot a changing role.",
    "**Trend / Momentum** come from the Trends page: which usage metrics moved over the last three games beyond the player's own noise, and the overall direction of his role. Blank until game four.",
    "**Opp rank**: where next week's opponent ranks in points allowed to this position. 1 = gives up the most (good matchup), 32 = the fewest.",
    "Team defenses are not listed — there is no per-player NFL id for them.",
)
roster = query(
    """select a.player_name, a.position, a.nfl_team, a.is_current_starter, a.is_on_ir, a.injury_status, a.practice_status,
              a.games_played, a.ppg_std, a.points_per_game_l3, a.expected_per_game, a.diff_per_game,
              a.target_share, a.target_share_l3, a.first_read_share_std, a.first_read_share_l3, a.carry_share, a.carry_share_l3, a.avg_offense_snap_pct, a.snap_pct_l3,
              a.opponent, a.is_bye, a.opp_rank_std, a.opp_rank_l4, t.tags, t.momentum
       from analytics.mart_player_availability a
       left join analytics.mart_player_trend_tags t on t.gsis_id = a.gsis_id and t.season = a.season
       where a.league_id = %s and a.rostered_by_roster_id = %s
       order by a.is_current_starter desc, array_position(array['QB','RB','WR','TE','K'], a.position), a.ppg_std desc nulls last""",
    (league_id, roster_id),
)
skill = roster[roster["position"].isin(["QB", "RB", "WR", "TE"])]
kick = roster[roster["position"] == "K"]
show(skill, ["player_name", "position", "nfl_team", "is_current_starter", "is_on_ir", "injury_status", "games_played",
             "tags", "momentum", "ppg_std", "points_per_game_l3", "expected_per_game", "diff_per_game", "target_share", "target_share_l3",
             "first_read_share_std", "first_read_share_l3", "carry_share", "carry_share_l3", "avg_offense_snap_pct", "snap_pct_l3", "opponent", "is_bye", "opp_rank_std", "opp_rank_l4"],
     height=min(80 + 36 * len(skill), 640))
if not kick.empty:
    st.markdown("**Kicker**")
    show(kick, ["player_name", "nfl_team", "is_current_starter", "injury_status", "games_played", "ppg_std", "points_per_game_l3", "opponent", "is_bye", "opp_rank_std"])

# ---------------------------------------------------------------- lineup discipline
st.subheader("Started vs best possible lineup, by week")
howto(
    "**Best possible** is the highest-scoring lineup you could have set from the players on your roster that week, using Sleeper's own points.",
    "**Left on bench** is the gap. It is hindsight, not a mistake — but a roster that leaves 10+ points every week is either "
    "not watching the start/sit board or is deeper than its lineup slots.",
    "These totals match Sleeper's 'max points' figure for the regular season.",
)
lu = query(
    """select week, points_started, points_optimal, bench_points_left, lineup_efficiency
       from analytics.mart_league_optimal_lineup where league_id = %s and roster_id = %s order by week""",
    (league_id, roster_id),
)
if not lu.empty:
    long = pd.concat([
        lu[["week", "points_started"]].rename(columns={"points_started": "points"}).assign(series="started"),
        lu[["week", "points_optimal"]].rename(columns={"points_optimal": "points"}).assign(series="best possible"),
    ])
    st.plotly_chart(line_chart(long, "week", "points", "series", "Started vs best possible", "points", y_format=".1f"), width="stretch")
    show(lu, ["week", "points_started", "points_optimal", "bench_points_left", "lineup_efficiency"])

# ---------------------------------------------------------------- positional strength
st.subheader("Positional strength vs the league")
howto(
    "**Starter PPG** adds up season points-per-game for the players who would start at each position (two RBs, two WRs, one QB/TE/K).",
    "**vs median** compares that with the league's middle roster. Negative = you are thin there; positive = you have surplus.",
    "**Best bench PPG** is your best player at that position who is *not* in the starting group — the piece you could trade from surplus.",
    "This is a rough shape check for trades and waivers, not a projection.",
)
ps = query(
    """select position, players, starter_ppg, league_median_starter_ppg, starter_ppg_vs_median, position_rank, best_bench_ppg, top_players
       from analytics.mart_league_positional_strength where league_id = %s and roster_id = %s
       order by array_position(array['QB','RB','WR','TE','K'], position)""",
    (league_id, roster_id),
)
show(ps, ["position", "players", "starter_ppg", "league_median_starter_ppg", "starter_ppg_vs_median", "position_rank", "best_bench_ppg", "top_players"])
if not ps.empty:
    st.plotly_chart(bar_chart(ps, "position", "starter_ppg_vs_median", "Starter PPG vs league median", "PPG vs median", y_format="+.1f", x_title=""), width="stretch")

# ---------------------------------------------------------------- keeper facts (redraft / keeper leagues; a dynasty keeps everyone)
league_type = league_seasons(league_id)["league_type"].iloc[0] if not league_seasons(league_id).empty else "redraft"
if league_type == "dynasty":
    st.subheader("Roster value (dynasty)")
    howto(
        "A dynasty league keeps the whole roster, so there is no keeper decision; this table is the same facts read as roster value: "
        "how each player was acquired, what he has produced, and where that ranks among all NFL players at his position this season.",
        "**xPPG** matters more than PPG for next year: a player scoring far above his opportunity is a riskier hold than his points suggest.",
    )
else:
    st.subheader("Keeper facts")
    howto(
        "The table lists how each player was acquired (draft round and pick, or a waiver/free-agent add), "
        "what he has produced, and where that ranks among all NFL players at his position this season.",
        "**xPPG** is included because a keeper decision is about next year: a player scoring far above his opportunity is a riskier keep than his points suggest.",
        "Apply your league's keeper cost rule yourself — League Lab only supplies the facts.",
    )
kc = query(
    """select player_name, position, nfl_team,
              case when was_keeper then 'Kept last year'
                   when draft_round is not null and acquired_after_draft then 'Draft R' || draft_round || ' P' || draft_pick || ' (by another roster), then acquired'
                   when draft_round is not null then 'Draft R' || draft_round || ' P' || draft_pick
                   else 'Waiver / free agent' end as acquired,
              games_played, points_std, ppg_std, position_rank_std, position_rank_ppg, expected_per_game, diff_per_game
       from analytics.mart_league_keeper_candidates where league_id = %s and roster_id = %s
       order by ppg_std desc nulls last""",
    (league_id, roster_id),
)
show(kc, ["player_name", "position", "nfl_team", "acquired", "games_played", "points_std", "ppg_std", "position_rank_std", "position_rank_ppg", "expected_per_game", "diff_per_game"])
