"""Player explorer: season and game tables with filters. Phone first (U-13): the leaders as one line, the season
table (≤ 5 columns at the Phone level) and the game log in expanders; names open the player card."""

import pandas as pd
import streamlit as st
from lib.charts import line_chart
from lib.db import query
from lib.table import howto, show
from lib.ui import (
    SKILL_POSITIONS,
    freshness_banner,
    reference_scoring_note,
    seasons_available,
    setup,
)

setup("Players")
freshness_banner()

seasons = seasons_available()
c1, c2, c3 = st.columns([1.2, 1, 1], vertical_alignment="bottom")
position = c1.selectbox("Position", SKILL_POSITIONS, index=2)
season = c2.selectbox("Season", seasons)
with c3.popover("More filters", width="stretch"):
    season_type = st.radio("Season type", ["REG", "POST"], horizontal=True, format_func=lambda s: "Regular season" if s == "REG" else "Playoffs")
    min_games = st.slider("Minimum games played", 1, 17, 1)

POSITION_COLUMNS = {
    "QB": ["attempts", "completions", "completion_rate", "passing_yards", "yards_per_attempt", "passing_tds",
           "passing_interceptions", "sacks_suffered", "dropbacks", "scrambles", "carries", "rushing_yards", "rushing_tds"],
    "RB": ["carries", "carry_share", "red_zone_carry_share", "rushing_yards", "yards_per_carry", "rushing_tds", "targets", "target_share",
           "first_read_target_share", "route_participation", "tprr_proxy", "receptions", "receiving_yards", "receiving_tds", "avg_offense_snap_pct"],
    "WR": ["targets", "target_share", "first_read_target_share", "air_yards_share", "adot", "route_participation", "tprr_proxy", "yprr_proxy",
           "red_zone_target_share", "receptions", "catch_rate", "receiving_yards", "yards_per_target", "yac_per_reception", "receiving_tds", "avg_offense_snap_pct"],
    "TE": ["targets", "target_share", "first_read_target_share", "air_yards_share", "adot", "route_participation", "tprr_proxy", "yprr_proxy",
           "red_zone_target_share", "receptions", "catch_rate", "receiving_yards", "yards_per_target", "receiving_tds", "avg_offense_snap_pct"],
    "K": ["fg_att", "fg_made", "fg_pct", "fg_made_under_40", "fg_made_40_49", "fg_made_50p", "fg_long", "pat_att", "pat_made"],
}
cols = ", ".join(POSITION_COLUMNS[position])

howto(
    "Season totals for every player at a position, ranked by fantasy points on one scale for every league and season. Use it to "
    "compare anyone with anyone, this year or past years.",
    "**Target %**, **Carry %** and **Air-yard %** are his share of his *team's* targets, carries and downfield throws in the games "
    "he played: a player who missed games is not marked down for it.",
    "**1st-read share** (2022 on) is how often he is the quarterback's first look. **Route %** is how often he is on the field when "
    "the quarterback drops back to pass; **TPRR / YPRR** are targets and yards per route. Those three are estimates from completed "
    "seasons and run a little low. **Snap %** counts every play, runs included.",
    "A blank cell means the number could not be worked out (no targets, no snaps recorded, a season before charting), never zero.",
)
reference_scoring_note()
season_df = query(
    f"""select gsis_id, player_name, teams, games_played, {cols}, points_current_scoring, points_current_scoring_per_game
        from analytics.mart_player_season
        where position = %s and season = %s and season_type = %s and games_played >= %s
        order by points_current_scoring desc nulls last""",
    (position, season, season_type, min_games),
)
st.subheader(f"{position} · {season} {'regular season' if season_type == 'REG' else 'playoffs'} · season totals")
PHONE = {"QB": ["passing_yards", "passing_tds"], "RB": ["carries", "carry_share"], "WR": ["targets", "target_share"],
         "TE": ["targets", "target_share"], "K": ["fg_made", "fg_pct"]}[position]
VOLUME_WORDS = {"passing_yards": "passing yards", "carries": "carries", "targets": "targets", "fg_made": "field goals made"}
with st.container(border=True):
    if season_df.empty:
        st.markdown(f"**No {position} has {min_games}+ games in {season} yet.**")
    else:
        lead = season_df.iloc[0]
        vol = PHONE[0]
        top_vol = season_df.sort_values(vol, ascending=False, na_position="last").iloc[0]
        st.markdown(f"**Most points: {lead['player_name']}, {float(lead['points_current_scoring'] or 0):.1f} "
                    f"({float(lead['points_current_scoring_per_game'] or 0):.1f} a game).** "
                    + (f"Most {VOLUME_WORDS[vol]}: {top_vol['player_name']} ({int(top_vol[vol])}). " if pd.notna(top_vol[vol]) else "")
                    + f"{len(season_df)} players.")
with st.expander("Season totals, every player", expanded=True):
    show(season_df, [c for c in season_df.columns if c != "gsis_id"], height=420,
         phone_cols=["player_name", "games_played", *PHONE, "points_current_scoring_per_game"])

st.subheader("Game log")
pick = st.selectbox("Player", season_df["gsis_id"].tolist(),
                    format_func=lambda g: season_df.set_index("gsis_id").loc[g, "player_name"] if g in set(season_df["gsis_id"]) else g)
player = season_df.set_index("gsis_id").loc[pick, "player_name"] if pick else None
if player:
    counting = [c for c in POSITION_COLUMNS[position] if c not in (
        "carry_share", "target_share", "air_yards_share", "avg_offense_snap_pct", "completion_rate", "yards_per_attempt",
        "yards_per_carry", "catch_rate", "yards_per_target", "yac_per_reception", "adot", "fg_pct", "fg_made_under_40",
        "first_read_target_share", "route_participation", "tprr_proxy", "yprr_proxy", "red_zone_target_share", "red_zone_carry_share")]
    games = query(
        f"""select week, team, opponent_team, game_date, roster_status, offense_snap_pct, played,
                   {", ".join(counting)}, team_targets, target_share, team_carries, carry_share, air_yards_share, adot,
                   first_read_targets, team_first_read_targets, first_read_target_share, routes_proxy, route_participation, tprr_proxy,
                   red_zone_targets, red_zone_carries, points_current_scoring, went_to_overtime
            from analytics.fct_player_game
            where gsis_id = %s and season = %s and season_type = %s order by week""",
        (pick, season, season_type),
    )
    with st.expander(f"{player}: every game", expanded=False):
        show(games, phone_cols=["week", "opponent_team", "offense_snap_pct", PHONE[0], "points_current_scoring"])
    if position in ("WR", "TE", "RB"):
        metric = "target_share" if position != "RB" else "carry_share"
        chart = games[["week", metric]].assign(series=player).dropna()
        st.plotly_chart(line_chart(chart, "week", metric, "series", f"{'Target' if metric == 'target_share' else 'Carry'} share by week", "share", y_format=".1%"), width="stretch")
    elif position == "QB":
        chart = games[["week", "attempts"]].assign(series=player)
        st.plotly_chart(line_chart(chart, "week", "attempts", "series", "Pass attempts by week", "attempts", y_format=".0f"), width="stretch")
    else:
        chart = games[["week", "points_current_scoring"]].assign(series=player)
        st.plotly_chart(line_chart(chart, "week", "points_current_scoring", "series", "Points by week", "points"), width="stretch")
