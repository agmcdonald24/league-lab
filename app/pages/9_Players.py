"""Player explorer: season and game tables with filters."""

import streamlit as st
from lib.charts import line_chart
from lib.db import query
from lib.table import howto, show
from lib.ui import SKILL_POSITIONS, freshness_banner, seasons_available, setup

setup("Players")
freshness_banner()

seasons = seasons_available()
c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
position = c1.selectbox("Position", SKILL_POSITIONS, index=2)
season = c2.selectbox("Season", seasons)
season_type = c3.radio("Season type", ["REG", "POST"], horizontal=True, format_func=lambda s: "Regular season" if s == "REG" else "Playoffs")
min_games = c4.slider("Minimum games played", 1, 17, 1)

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
    "Season totals for every player at the position, ranked by fantasy points under this league's scoring.",
    "**Target % / Carry % / Air-yard %** divide the player's numbers by his *team's* totals in the games he played — so a player who missed "
    "games is not penalised, and a player whose team never throws is shown for what he is.",
    "**1st-read share** (2022+) is the player's share of the team's first-read targets — where the QB looks first. "
    "**Route %** and **TPRR / YPRR (proxy)** come from NFL participation data (completed seasons only) and are proxies: presence on a "
    "dropback is not proof of a route, so they read ~10–15% conservative. **Snap %** is share of all offensive snaps, runs included.",
    "Blank cells mean the number could not be computed (no targets, no snaps recorded, season not charted), never zero.",
)
season_df = query(
    f"""select player_name, teams, games_played, {cols}, points_current_scoring, points_current_scoring_per_game
        from analytics.mart_player_season
        where position = %s and season = %s and season_type = %s and games_played >= %s
        order by points_current_scoring desc nulls last""",
    (position, season, season_type, min_games),
)
st.subheader(f"{position} · {season} {'regular season' if season_type == 'REG' else 'playoffs'} · season totals")
show(season_df, height=420)

st.subheader("Game log")
names = season_df["player_name"].tolist()
player = st.selectbox("Player", names)
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
            where player_name = %s and season = %s and season_type = %s order by week""",
        (player, season, season_type),
    )
    show(games)
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
