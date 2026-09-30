"""Receiver comparison and early/late windows. Phone first (U-13): filters in one row, the comparison as one line,
every table in an expander (≤ 5 columns at the Phone level); names open the player card (gsis_id)."""

import pandas as pd
import streamlit as st
from lib.charts import bar_chart, color_map, line_chart
from lib.db import query, require_relations
from lib.table import howto, show
from lib.ui import freshness_banner, reference_scoring_note, seasons_available, setup, unavailable

setup("Receivers")
freshness_banner()
require_relations("mart_player_context")
reference_scoring_note("Points on this page")

seasons = seasons_available()
c1, c2 = st.columns([1, 1], vertical_alignment="bottom")
season = c1.selectbox("Season", seasons)
with c2.popover("Weeks and playoffs", width="stretch"):
    season_type = st.radio("Season type", ["REG", "POST"], horizontal=True, format_func=lambda s: "Regular season" if s == "REG" else "Playoffs")
    if season_type == "POST":
        week_lo, week_hi = st.slider("Week window (playoffs are weeks 19-22)", 19, 22, (19, 22))
    else:
        week_lo, week_hi = st.slider("Week window", 1, 18, (1, 18))

candidates = query(
    """select player_name from analytics.mart_player_season
       where season = %s and season_type = %s and position in ('WR','TE','RB') and targets >= 10
       order by targets desc""",
    (season, season_type),
)["player_name"].tolist()
players = st.multiselect("Receivers to compare (up to 6)", candidates, default=candidates[:3], max_selections=6)
if len(players) < 1:
    st.stop()

games = query(
    """select gsis_id, player_name, position, week, team, opponent_team, played, offense_snap_pct, snaps_known,
              targets, team_targets, receptions, receiving_yards, receiving_air_yards, team_air_yards,
              receiving_yards_after_catch, receiving_tds, target_share, air_yards_share, adot,
              points_current_scoring, roster_status
       from analytics.fct_player_game
       where season = %s and season_type = %s and player_name = any(%s) and week between %s and %s
       order by player_name, week""",
    (season, season_type, players, week_lo, week_hi),
)
colors = color_map(sorted(players))


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Sum numerators and denominators over the same games, then divide."""
    df = df.assign(_snap=df["offense_snap_pct"].where(df["snaps_known"].astype(bool)))
    g = df.groupby(["player_name", "gsis_id"], dropna=False)
    out = pd.DataFrame({
        "games": g["played"].sum(),
        "targets": g["targets"].sum(),
        "team_targets": g["team_targets"].sum(),
        "receptions": g["receptions"].sum(),
        "receiving_yards": g["receiving_yards"].sum(),
        "receiving_air_yards": g["receiving_air_yards"].sum(),
        "team_air_yards": g["team_air_yards"].sum(),
        "yac": g["receiving_yards_after_catch"].sum(),
        "receiving_tds": g["receiving_tds"].sum(),
        "points": g["points_current_scoring"].sum(),
        "snap_pct": g["_snap"].mean(),
    })
    out["target_share"] = out["targets"] / out["team_targets"].where(out["team_targets"] > 0)
    out["air_yards_share"] = out["receiving_air_yards"] / out["team_air_yards"].where(out["team_air_yards"] != 0)
    out["adot"] = out["receiving_air_yards"] / out["targets"].where(out["targets"] > 0)
    out["yac_per_rec"] = out["yac"] / out["receptions"].where(out["receptions"] > 0)
    out["targets_per_game"] = out["targets"] / out["games"].where(out["games"] > 0)
    out["points_per_game"] = out["points"] / out["games"].where(out["games"] > 0)
    return out.reset_index()


st.subheader(f"Window summary · weeks {week_lo}–{week_hi}")
summary = summarize(games)
with st.container(border=True):
    if summary.empty or summary["games"].fillna(0).sum() == 0:
        st.markdown(f"**No games for these receivers in weeks {week_lo}–{week_hi}.**")
    else:
        ts = summary.dropna(subset=["target_share"]).sort_values("target_share", ascending=False)
        ad = summary.dropna(subset=["adot"]).sort_values("adot", ascending=False)
        pp = summary.dropna(subset=["points_per_game"]).sort_values("points_per_game", ascending=False)
        bits = []
        if not ts.empty:
            bits.append(f"**Biggest share of his team's targets: {ts.iloc[0]['player_name']} ({ts.iloc[0]['target_share']:.1%})**")
        if not ad.empty and len(summary) > 1:
            bits.append(f"deepest role: {ad.iloc[0]['player_name']} (aDOT {ad.iloc[0]['adot']:.1f})")
        if not pp.empty and len(summary) > 1:
            bits.append(f"most points a game: {pp.iloc[0]['player_name']} ({pp.iloc[0]['points_per_game']:.1f})")
        st.markdown("; ".join(bits) + ".")
howto(
    "Each receiver's numbers over the selected weeks. Shares are computed the right way: total targets ÷ total *team* targets over the same games, not an average of weekly percentages.",
    "**aDOT** is average depth of target — how far downfield the throws go. **YAC/Rec** is yards after the catch per reception. "
    "Together they describe the role: a low-aDOT / high-YAC receiver lives on screens and slants; a high-aDOT receiver on deep shots.",
    "**Snap %** is participation, not routes; a receiver at 95% snaps with a 12% target share is on the field but not in the plan.",
)
with st.expander("The window, every column", expanded=True):
    show(summary, ["player_name", "games", "targets", "targets_per_game", "target_share", "air_yards_share", "adot",
                   "receptions", "receiving_yards", "yac_per_rec", "receiving_tds", "snap_pct", "points_per_game"],
         phone_cols=["player_name", "games", "target_share", "adot", "points_per_game"])

metric_labels = {"target_share": "Target %", "targets": "Targets", "air_yards_share": "Air-yard %", "adot": "aDOT", "offense_snap_pct": "Snap %", "points_current_scoring": "Points"}
metric = st.selectbox("Chart", list(metric_labels), format_func=lambda k: metric_labels[k])
fmt = ".1%" if metric in ("target_share", "air_yards_share", "offense_snap_pct") else ".1f"
st.plotly_chart(line_chart(games.dropna(subset=[metric]), "week", metric, "player_name", f"{metric_labels[metric]} by week", metric_labels[metric], y_format=fmt, colors=colors), width="stretch")

# ---- early vs late ------------------------------------------------------------------------
st.subheader("Early vs late window")
howto("Pick two week ranges and compare the same receivers across them. Use it to see whether a role changed "
      "(target share moved) or the team changed (team targets moved) — the two look identical in the box score.")
e1, e2 = st.columns(2)
early = e1.slider("Early weeks", 1, 22, (1, 6))
late = e2.slider("Late weeks", 1, 22, (12, 18))
ew = summarize(games[games["week"].between(*early)]).assign(window="early")
lw = summarize(games[games["week"].between(*late)]).assign(window="late")
both = pd.concat([ew, lw]).sort_values(["player_name", "window"])
with st.expander("Early vs late, every column"):
    show(both, ["player_name", "window", "games", "targets_per_game", "team_targets", "target_share", "air_yards_share", "adot", "snap_pct", "points_per_game"],
         phone_cols=["player_name", "window", "target_share", "adot", "points_per_game"])

# ---- recent form ----------------------------------------------------------------------------
st.subheader("Recent form — last 3 / last 5 games vs season")
howto("As of each receiver's latest game: target share over his last three and last five games next to his season-to-date share. "
      "A rising L3 with a flat season number is the earliest usage signal you can get from box-score data.")
recent = query(
    """select gsis_id, player_name, week, target_share_l3, target_share_l5, target_share_std,
              targets_l3, team_targets_l3, snap_pct_l3, points_per_game_l3, points_per_game_std
       from analytics.mart_player_recent_form
       where season = %s and season_type = %s and player_name = any(%s) and week between %s and %s
       order by player_name, week""",
    (season, season_type, players, week_lo, week_hi),
)
latest = recent.sort_values("week").groupby("player_name").tail(1)
with st.expander("Last 3 / last 5 vs season, every column"):
    show(latest, [c for c in latest.columns if c != "gsis_id"],
         phone_cols=["player_name", "target_share_l3", "target_share_l5", "target_share_std", "points_per_game_l3"])

# ---- first reads (FTN charting, 2022+) --------------------------------------------------------
st.subheader("First-read target share")
howto(
    "**First-read share** = this player's first-read targets ÷ the *team's* first-read targets over the same games. "
    "It answers *where does the quarterback look first* — a role signal that target share hides, because checkdowns and "
    "scramble-drill throws count the same as a designed primary read in the box score.",
    "**1st read of own tgt** is a different question: of *this player's* targets, how many were first reads. A high number "
    "with a low first-read share is a specialist; a low number with a high target share is a safety valve.",
    "**Designed** throws (screens, many RPOs) are kept separate and never counted as first reads. **Charting coverage** is the share "
    "of the team's targets that carry a read code; nothing is inferred for uncharted throws.",
    "Source: FTN Data charting via nflverse (CC-BY-SA 4.0). Seasons before 2022 are not charted and show blank, not zero.",
)
if season < 2022:
    unavailable("First-read target share", f"FTN charting starts in 2022; {season} has no read codes. Never shown as zero.")
else:
    fr = query(
        """select gsis_id, player_name, count(*) filter (where played) as games, sum(targets) as targets,
                  sum(charted_targets) as charted_targets, sum(first_read_targets) as first_read_targets,
                  sum(designed_targets) as designed_targets, sum(checkdown_targets) as checkdown_targets,
                  sum(later_read_targets) as later_read_targets, sum(scramble_drill_targets) as scramble_drill_targets,
                  sum(team_first_read_targets) filter (where played) as team_first_read_targets,
                  case when sum(team_first_read_targets) filter (where played) > 0
                       then sum(first_read_targets)::numeric / sum(team_first_read_targets) filter (where played) end as first_read_target_share,
                  case when sum(charted_targets) > 0 then sum(first_read_targets)::numeric / sum(charted_targets) end as first_read_rate_of_targets,
                  case when sum(charted_targets) > 0 then sum(designed_targets)::numeric / sum(charted_targets) end as designed_rate_of_targets,
                  case when sum(team_targets) filter (where played) > 0
                       then sum(team_charted_targets) filter (where played)::numeric / sum(team_targets) filter (where played) end as charting_coverage,
                  sum(drops) as drops, sum(contested_targets) as contested_targets
           from analytics.fct_player_game
           where season = %s and season_type = %s and player_name = any(%s) and week between %s and %s
           group by 1, 2 order by first_read_target_share desc nulls last""",
        (season, season_type, players, week_lo, week_hi),
    )
    with st.expander("First reads, every column"):
        show(fr, ["player_name", "games", "targets", "charted_targets", "first_read_targets", "team_first_read_targets", "first_read_target_share",
                  "first_read_rate_of_targets", "designed_targets", "designed_rate_of_targets", "checkdown_targets", "later_read_targets",
                  "scramble_drill_targets", "drops", "contested_targets", "charting_coverage"],
             phone_cols=["player_name", "targets", "first_read_targets", "first_read_target_share", "first_read_rate_of_targets"])
    low = fr[fr["charting_coverage"].fillna(0) < 0.9]
    if not low.empty:
        st.caption("⚠️ Charting coverage below 90% for: " + ", ".join(low["player_name"]) + " — treat their first-read rates as partial.")
    frw = query(
        """select player_name, week, first_read_targets, team_first_read_targets, first_read_target_share, target_share
           from analytics.fct_player_game
           where season = %s and season_type = %s and player_name = any(%s) and week between %s and %s and played and team_charted_targets > 0
           order by player_name, week""",
        (season, season_type, players, week_lo, week_hi),
    )
    if not frw.empty:
        st.plotly_chart(line_chart(frw.dropna(subset=["first_read_target_share"]), "week", "first_read_target_share", "player_name",
                                   "First-read share by week", "1st-read share", y_format=".0%", colors=colors), width="stretch")

# ---- routes proxy (participation, completed seasons) ------------------------------------------
st.subheader("Routes (participation proxy)")
howto(
    "**Routes (proxy)** counts the dropbacks a receiver was on the field for, from the NFL's participation data. It is a proxy, "
    "not a charted route count: a tight end who stayed in to block is counted, so the proxy runs about 10–15% above the charting "
    "services' numbers and **TPRR / YPRR (proxy)** are lower bounds. Compare players against each other, not against published TPRR.",
    "**Route %** = routes proxy ÷ team dropbacks with participation data: how often the player is on the field when the QB drops back. "
    "Snap % includes run plays; route % is the passing-down version.",
    "Participation files are published after each season's postseason, so the current season shows blank here until then. "
    "A licensed in-season routes feed drops in through `league-lab import-routes` and appears as **Routes** / **TPRR** / **YPRR** without the proxy label.",
)
rp = query(
    """select gsis_id, player_name, count(*) filter (where routes_proxy is not null) as games_with_participation,
              sum(routes_proxy) as routes_proxy,
              case when count(*) filter (where routes_proxy is not null) > 0 then sum(routes_proxy)::numeric / count(*) filter (where routes_proxy is not null) end as routes_proxy_per_game,
              sum(team_dropbacks_with_participation) filter (where routes_proxy is not null) as team_dropbacks_with_participation,
              case when sum(team_dropbacks_with_participation) filter (where routes_proxy is not null) > 0
                   then sum(routes_proxy)::numeric / sum(team_dropbacks_with_participation) filter (where routes_proxy is not null) end as route_participation,
              case when sum(routes_proxy) > 0 then sum(targets) filter (where routes_proxy is not null)::numeric / sum(routes_proxy) end as tprr_proxy,
              case when sum(routes_proxy) > 0 then sum(receiving_yards) filter (where routes_proxy is not null)::numeric / sum(routes_proxy) end as yprr_proxy,
              sum(routes) as routes, max(routes_provider) as routes_provider,
              case when sum(routes) > 0 then sum(targets) filter (where routes is not null)::numeric / sum(routes) end as tprr,
              case when sum(routes) > 0 then sum(receiving_yards) filter (where routes is not null)::numeric / sum(routes) end as yprr
       from analytics.fct_player_game
       where season = %s and season_type = %s and player_name = any(%s) and week between %s and %s and played
       group by 1, 2 order by yprr_proxy desc nulls last""",
    (season, season_type, players, week_lo, week_hi),
)
if rp["routes_proxy"].isna().all() and rp["routes"].isna().all():
    unavailable("Routes for this window", f"No participation data for these games: NFL {season}'s participation file arrives after the postseason "
                "(and does not cover playoff games for some seasons), and no licensed routes feed has been imported.")
else:
    cols = ["player_name", "games_with_participation", "routes_proxy", "routes_proxy_per_game", "route_participation", "tprr_proxy", "yprr_proxy"]
    if rp["routes"].notna().any():
        cols += ["routes", "routes_provider", "tprr", "yprr"]
    with st.expander("Routes, every column"):
        show(rp, cols, phone_cols=["player_name", "routes_proxy_per_game", "route_participation", "tprr_proxy", "yprr_proxy"])

# ---- context splits ---------------------------------------------------------------------------
st.subheader("Context splits — where the usage comes from")
howto(
    "Each row is one situation. **Team tgt** / **Team dropbacks** are the team's totals *in that situation, in the games this receiver played*, "
    "so the share is a real share, not a mix of games. Halves keep overtime separate; the score state is the score *before* the snap "
    "(never the final score); down-and-distance groups third and fourth down together.",
    "Read it as a story: a receiver whose target share jumps when trailing by 9+ is a garbage-time producer; one whose share holds when "
    "leading is in the plan regardless of script. **QB on the play** splits the same numbers by who was under center — the first thing to "
    "check after a quarterback change.",
    "Routes proxy per situation needs participation data (completed seasons only).",
)
ctx_labels = {"half": "Half", "score_state": "Score state (pre-snap)", "down_distance": "Down & distance", "field_zone": "Field zone", "qb": "QB on the play"}
ctx = st.selectbox("Split by", list(ctx_labels), format_func=lambda k: ctx_labels[k])
cx = query(
    """select c.gsis_id, c.player_name, c.context_type, case when c.context_type = 'qb' then coalesce(q.player_name, c.bucket) else c.bucket end as bucket,
              c.games, c.targets, c.team_targets, c.target_share, c.first_read_targets, c.team_first_read_targets, c.first_read_target_share,
              c.receptions, c.receiving_yards, c.yards_per_target, c.adot, c.carries, c.team_carries, c.carry_share,
              c.routes_proxy, c.team_dropbacks, c.route_participation, c.tprr_proxy, c.yprr_proxy
       from analytics.mart_player_context c
       left join analytics.dim_player q on q.gsis_id = c.bucket and c.context_type = 'qb'
       where c.season = %s and c.season_type = %s and c.player_name = any(%s) and c.context_type = %s
       order by c.player_name, c.bucket""",
    (season, season_type, players, ctx),
)
order = {"half": ["H1", "H2", "OT"], "score_state": ["trailing_9plus", "trailing_1_8", "tied", "leading_1_8", "leading_9plus"],
         "down_distance": ["1st", "2nd_short", "2nd_medium", "2nd_long", "3rd_4th_short", "3rd_4th_medium", "3rd_4th_long"],
         "field_zone": ["own_half", "opp_half", "red_zone_11_20", "inside_10"]}
pretty = {"trailing_9plus": "Trailing 9+", "trailing_1_8": "Trailing 1–8", "tied": "Tied", "leading_1_8": "Leading 1–8", "leading_9plus": "Leading 9+",
          "2nd_short": "2nd & short (≤3)", "2nd_medium": "2nd & medium (4–6)", "2nd_long": "2nd & long (7+)", "3rd_4th_short": "3rd/4th & short (≤3)",
          "3rd_4th_medium": "3rd/4th & medium (4–6)", "3rd_4th_long": "3rd/4th & long (7+)", "own_half": "Own half", "opp_half": "Opp. half (21–50)",
          "red_zone_11_20": "Red zone (11–20)", "inside_10": "Inside the 10", "H1": "1st half", "H2": "2nd half", "OT": "Overtime"}
if not cx.empty:
    if ctx in order:
        cx["_o"] = cx["bucket"].map({b: i for i, b in enumerate(order[ctx])})
        cx = cx.sort_values(["player_name", "_o"]).drop(columns="_o")
    cx["bucket"] = cx["bucket"].map(lambda b: pretty.get(b, b))
    with st.expander(f"{ctx_labels[ctx]}, every column"):
        show(cx, ["player_name", "bucket", "games", "targets", "team_targets", "target_share", "first_read_target_share", "receptions", "receiving_yards",
                  "yards_per_target", "adot", "routes_proxy", "team_dropbacks", "route_participation", "tprr_proxy", "carries", "carry_share"],
             phone_cols=["player_name", "bucket", "targets", "target_share", "yards_per_target"])
    chart = cx.dropna(subset=["target_share"])
    if not chart.empty and ctx != "qb":
        st.plotly_chart(bar_chart(chart, "bucket", "target_share", f"Target share by {ctx_labels[ctx].lower()}", "Target %", series="player_name",
                                  y_format=".0%", colors=colors, x_title=""), width="stretch")
else:
    st.caption("No plays in this split for the selected receivers.")
