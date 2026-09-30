"""Trends: who is trending up or down, by which metrics, and whether the move is bigger than noise."""

import pandas as pd
import streamlit as st
from lib.charts import line_chart
from lib.db import query, require_relations
from lib.table import Col, howto, show
from lib.ui import freshness_banner, next_week_info, perspective, reference_scoring_note, setup

setup("Trends")
freshness_banner()
require_relations("mart_player_trend_tags", "mart_player_trends", "mart_defense_trends")
league_id, roster_id, members = perspective(require_team=False)
cal = next_week_info()
current_season = int(cal["season"]) if not cal.empty else None
seasons = query("select distinct season from analytics.mart_player_trend_tags order by season desc")["season"].astype(int).tolist()

howto(
    "**Use it to spot a role change before the points show up**: add the risers off waivers, and think about moving the fallers.",
    "Each player's last **3 games** are compared with his games before that. A number is called **up** or **down** only when the "
    "change is big enough to matter (say, 3 points of target share) *and* bigger than his normal week-to-week swing.",
    "**Strength** says how unusual the change is for him: 1 is worth a look, 2 is a clear change. **Momentum** averages that over "
    "his work (targets, snaps, carries, how far downfield he is targeted, expected points) and ignores his fantasy points on "
    "purpose: three touchdowns can happen without the role changing at all.",
    "**Trend** names what moved: \"↑ targets, ↑ snaps\" is more work; \"↑ targets, ↑ aDOT\" (targeted deeper downfield) is a "
    "different, deeper role.",
    "Nothing is called a trend before a player's fourth game; until then the page shows an *early read* and says so.",
    title="How to use this page",
)
reference_scoring_note("Points, expected points and defense trends on this page")

# ---------------------------------------------------------------- scope filters
c0, c1, c2, c3, c4 = st.columns([0.8, 1.2, 1.2, 1, 1])
season = c0.selectbox("Season", seasons, index=seasons.index(current_season) if current_season in seasons else 0,
                      help="Past seasons show the trends as they stood at the end of that season — useful to see how the logic reads a full year.")
positions = c1.multiselect("Positions", ["QB", "RB", "WR", "TE"], default=["RB", "WR", "TE"])
scope_options = {"all": "Everyone", "fa": "Free agents in this league", "rostered": "Rostered in this league", "team": "Selected team only"}
scope = c2.selectbox("Who", list(scope_options), format_func=lambda k: scope_options[k], index=1 if season == current_season else 0, key="trends_scope")
min_games = c3.number_input("Min games", 1, 17, 4)
top_n = c4.number_input("Show", 5, 50, 15)
if season != current_season:
    st.caption(f"Showing NFL {season}. \"Rostered by\" and matchup columns reflect today's league rosters, not {season}'s.")

avail = query(
    """select gsis_id, rostered_by_roster_id, rostered_by_team, is_free_agent, injury_status, opponent, opp_rank_std, is_bye
       from analytics.mart_player_availability where league_id = %s""",
    (league_id,),
)
tags = query(
    """select gsis_id, player_name, position, team, games, latest_week, tags, momentum, opportunity_trend, n_up, n_down,
              target_share_l3, target_share_change, target_share_z, snap_share_l3, snap_share_change, snap_share_z,
              carry_share_change, carry_share_z, air_yards_share_change, adot_change,
              expected_points_l3, expected_points_change, expected_points_z, points_l3, points_change
       from analytics.mart_player_trend_tags where season = %s and position = any(%s)""",
    (season, positions),
)
df = tags.merge(avail, on="gsis_id", how="left")
if scope == "fa":
    df = df[df["is_free_agent"].fillna(True)]
elif scope == "rostered":
    df = df[df["rostered_by_roster_id"].notna()]
elif scope == "team" and roster_id is not None:
    df = df[df["rostered_by_roster_id"] == roster_id]
df = df[df["games"] >= min_games]

enough = df[df["opportunity_trend"] != "insufficient"]
if enough.empty:
    st.warning(
        f"No player in this scope has four games yet (NFL {season}). Trends are not called before game four because three "
        "data points cannot be separated from noise. Below is an **early read** — latest game versus the season so far — which is exactly as unreliable as it sounds."
    )
    early = query(
        """select gsis_id, player_name, position, team, games,
                  metric_label || case when display_kind = 'pct' then ' (%%)' else '' end as metric_label,
                  case when display_kind = 'pct' then value_latest * 100 else value_latest end as value_latest,
                  case when display_kind = 'pct' then value_season * 100 else value_season end as value_season,
                  case when display_kind = 'pct' then (value_latest - value_season) * 100 else value_latest - value_season end as change,
                  round((value_latest - value_season) / nullif(min_change, 0), 2) as change_vs_minimum
           from analytics.mart_player_trends where season = %s and position = any(%s) and metric in ('target_share','snap_share','carry_share','expected_points')
           order by abs(value_latest - value_season) / nullif(min_change, 0) desc nulls last""",
        (season, positions),
    )
    early = early.merge(avail[["gsis_id", "rostered_by_roster_id", "rostered_by_team", "is_free_agent"]], on="gsis_id", how="left")
    if scope == "fa":
        early = early[early["is_free_agent"].fillna(True)]
    elif scope == "rostered":
        early = early[early["rostered_by_team"].notna()]
    elif scope == "team" and roster_id is not None:
        early = early[early["rostered_by_roster_id"] == roster_id]
    early = early[early["games"] >= min(int(min_games), 2)]
    if int(min_games) > 2:
        st.caption("Early read: *Min games* is capped at 2 until the season has four games of data.")
    # the early read is about the latest game vs the season, so those columns stay visible whatever the detail level
    show(early.head(int(top_n) * 2), ["player_name", "position", "team", "rostered_by_team", "games", "metric_label", "value_season", "value_latest", "change", "change_vs_minimum"],
         overrides={"value_latest": Col("Latest game", "num2"), "change_vs_minimum": Col("Change vs minimum", "num2", "How many times the metric's minimum meaningful change the move is; 1 = just meaningful")})
else:
    cols = ["player_name", "position", "team", "rostered_by_team", "games", "tags", "momentum", "target_share_l3", "target_share_change",
            "snap_share_l3", "snap_share_change", "expected_points_l3", "expected_points_change", "points_l3", "points_change",
            "injury_status", "opponent", "opp_rank_std"]
    st.subheader("Trending up — opportunity growing")
    show(enough.sort_values("momentum", ascending=False).head(int(top_n)), cols)
    st.subheader("Trending down — opportunity shrinking")
    show(enough.sort_values("momentum").head(int(top_n)), cols)

# ---------------------------------------------------------------- player detail
st.subheader("One player, every metric")
names = sorted(tags["player_name"].dropna().unique().tolist())
pick = st.selectbox("Player", names, index=None, placeholder="Choose a player")
if pick:
    detail = query(
        """select metric_label, games_with_metric, value_prior, value_l3, value_season, change, z, slope_per_game, direction, confidence, display_kind, metric
           from analytics.mart_player_trends where season = %s and player_name = %s
           order by direction in ('up','down') desc, abs(z) desc nulls last""",
        (season, pick),
    )
    # show shares as percentages
    pct_rows = detail["display_kind"] == "pct"
    for c in ("value_prior", "value_l3", "value_season", "change", "slope_per_game"):
        detail.loc[pct_rows, c] = pd.to_numeric(detail.loc[pct_rows, c], errors="coerce") * 100
    detail["metric_label"] = detail["metric_label"] + detail["display_kind"].map({"pct": " (%)", "num1": ""}).fillna("")
    show(detail, ["metric_label", "games_with_metric", "value_prior", "value_l3", "value_season", "change", "z", "slope_per_game", "direction", "confidence"])

    series = query(
        """select p.week, 'target_share' as metric, 'Target share' as metric_label, p.target_share as value
             from analytics.fct_player_game p where p.season = %s and p.player_name = %s and p.played and p.season_type = 'REG'
           union all
           select p.week, 'snap_share', 'Snap share', p.offense_snap_pct
             from analytics.fct_player_game p where p.season = %s and p.player_name = %s and p.played and p.season_type = 'REG' and p.snaps_known
           union all
           select p.week, 'carry_share', 'Carry share', p.carry_share
             from analytics.fct_player_game p where p.season = %s and p.player_name = %s and p.played and p.season_type = 'REG'
           union all
           select e.week, 'expected_points', 'Expected points', e.points_expected
             from analytics.mart_player_expected_points e where e.season = %s and e.player_name = %s and e.played and e.season_type = 'REG'
           order by 1""",
        (season, pick, season, pick, season, pick, season, pick),
    )
    if not series.empty:
        c1, c2 = st.columns(2)
        shares = series[series["metric"].isin(["target_share", "snap_share", "carry_share"])].dropna(subset=["value"])
        if not shares.empty:
            c1.plotly_chart(line_chart(shares, "week", "value", "metric_label", f"{pick}: usage by week", "share", y_format=".1%"), width="stretch")
        xp = series[series["metric"] == "expected_points"].dropna(subset=["value"])
        if not xp.empty:
            c2.plotly_chart(line_chart(xp, "week", "value", "metric_label", f"{pick}: expected points by week", "points", y_format=".1f"), width="stretch")

# ---------------------------------------------------------------- defenses
st.subheader("Defenses getting softer or stiffer")
howto("**Softer** means the defense has given up more to that position over its last 3 games than before: a better matchup "
      "than its season rank says, so lean toward starting players against it.",
      "**Stiffer** means it has tightened up: be careful with players facing it, even if the season numbers look friendly.",
      "Only changes bigger than the defense's normal week-to-week swing are listed (**Strength** 1 = worth a look, 2 = clear). "
      "A defense needs four games before it shows up here.")
dt = query(
    """select defense, position, games, allowed_prior, allowed_l3, allowed_season, change, z, direction
       from analytics.mart_defense_trends where season = %s and direction in ('softer','stiffer') order by abs(z) desc""",
    (season,),
)
if dt.empty:
    st.caption("No defense has four games yet, or none has moved beyond noise.")
else:
    show(dt.head(20))
