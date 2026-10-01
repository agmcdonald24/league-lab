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

# ---- U-17 (C6): the yardsticks and worked examples the "why it matters" lines quote (copy only: one query, no layout)
YS_METRICS = ["target_share", "targets_per_game", "air_yards_share", "adot", "yac_per_reception", "avg_offense_snap_pct",
              "first_read_target_share", "route_participation", "tprr_proxy", "yprr_proxy"]
ys_rows = query(
    f"""select player_name, position, games_played, points_current_scoring_per_game as ppg, {", ".join(YS_METRICS)}
        from analytics.mart_player_season
        where season = %s and season_type = %s and position in ('WR', 'TE') and games_played > 0""",
    (season, season_type),
)
if not ys_rows.empty:
    ys_rows = ys_rows[ys_rows["games_played"] >= max(1, int(ys_rows["games_played"].max()) // 2)]   # regulars: half the games or more
ys_top = ys_rows.sort_values("ppg", ascending=False).groupby("position").head(12) if not ys_rows.empty else ys_rows


def ys(pos: str, metric: str) -> float | None:
    """The average of this season's top 12 at the position (by points a game, one scale for every league)."""
    if ys_top.empty:
        return None
    v = pd.to_numeric(ys_top.loc[ys_top["position"] == pos, metric], errors="coerce").mean()
    return None if pd.isna(v) else float(v)


def ys_pct(pos: str, metric: str, fallback: str) -> str:
    v = ys(pos, metric)
    return f"{v:.0%}" if v is not None else fallback


def ys_num(pos: str, metric: str, fallback: str, spec: str = ".1f") -> str:
    v = ys(pos, metric)
    return format(v, spec) if v is not None else fallback


def leader(metric: str, spec: str) -> str | None:
    """ "Puka Nacua (46%)": this season's leader among the regulars, for a worked example."""
    if ys_rows.empty or ys_rows[metric].isna().all():
        return None
    r = ys_rows.assign(_v=pd.to_numeric(ys_rows[metric], errors="coerce")).dropna(subset=["_v"]).sort_values("_v", ascending=False).iloc[0]
    return f"{r['player_name']} ({format(float(r['_v']), spec)})"


YS_LABEL = f"the {season} top-12"      # "the 2026 top-12 wide receivers": the 12 with the most points a game


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
def example(metric: str, spec: str) -> str | None:
    """ "Ja'Marr Chase, 27%": the selected receiver with the highest value, for a worked example from the table below."""
    d = summary.assign(_v=pd.to_numeric(summary[metric], errors="coerce")).dropna(subset=["_v"]) if not summary.empty else summary
    if d.empty:
        return None
    r = d.sort_values("_v", ascending=False).iloc[0]
    return f"{r['player_name']}, {format(float(r['_v']), spec)}"


ex_ts, ex_tpg, ex_ay, ex_adot, ex_snap = (example("target_share", ".0%"), example("targets_per_game", ".1f"),
                                           example("air_yards_share", ".0%"), example("adot", ".1f"), example("snap_pct", ".0%"))
ts_top = summary.dropna(subset=["target_share"]).sort_values("target_share", ascending=False) if not summary.empty else summary
one_in = (f": about 1 throw in {max(1, round(1 / float(ts_top.iloc[0]['target_share'])))} goes his way"
          if not ts_top.empty and float(ts_top.iloc[0]["target_share"]) > 0 else "")
howto(
    "**Start the receiver the offense is built around, not last week's box score.** Each number below is over the weeks you "
    f"picked. The yardsticks are what {YS_LABEL} at each position average (the 12 with the most points a game, one scale for "
    "every league); the examples are from your selection.",
    "**Target %** (his share of his team's targets). Why it matters: targets turn into points more reliably than anything else, "
    "and a share holds when the team throws more or less. "
    + (f"Example: {ex_ts}{one_in}. " if ex_ts else "")
    + f"Yardstick: the top-12 wide receivers average {ys_pct('WR', 'target_share', '28%')}, tight ends "
    f"{ys_pct('TE', 'target_share', '21%')}; under 15% is a depth piece.",
    "**Targets/G** is the same thing as a count. Why it matters: it is the volume behind the share. "
    + (f"Example: {ex_tpg} a game. " if ex_tpg else "")
    + f"Yardstick: {ys_num('WR', 'targets_per_game', '9.2')} for the top-12 wide receivers, "
    f"{ys_num('TE', 'targets_per_game', '6.3')} for tight ends.",
    "**Air-yard %** (his share of the yards his team's throws travel in the air). Why it matters: it says who gets the deep, "
    "valuable targets, the ones that become long touchdowns. "
    + (f"Example: {ex_ay}. " if ex_ay else "")
    + f"Yardstick: {ys_pct('WR', 'air_yards_share', '35%')} for the top-12 wide receivers; 30%+ is the main downfield option.",
    "**aDOT** (how far downfield his targets travel, on average) is a style, not a grade. Why it matters: 12+ yards means big "
    "weeks and duds; under 8 means short, steady catches (worth more in full PPR). "
    + (f"Example: {ex_adot} yards. " if ex_adot else "")
    + "**YAC/Rec** (yards after the catch per catch): 5+ means he makes yards on his own.",
    "**Snap %** (share of plays he is on the field) is the ceiling on everything else. Why it matters: he cannot be targeted from "
    "the sideline. " + (f"Example: {ex_snap}. " if ex_snap else "")
    + "80%+ is a full-time starter. On the field 95% of the time but only 12% of the targets means he is out there, not in the "
    "plan: don't count on him.",
)
with st.expander("The window, every column", expanded=True):
    show(summary, ["player_name", "games", "targets", "targets_per_game", "target_share", "air_yards_share", "adot",
                   "receptions", "receiving_yards", "yac_per_rec", "receiving_tds", "snap_pct", "points_per_game"],
         phone_cols=["player_name", "games", "target_share", "adot", "points_per_game"])

metric_labels = {"target_share": "Target %", "targets": "Targets", "air_yards_share": "Air-yard %", "adot": "aDOT", "offense_snap_pct": "Snap %", "points_current_scoring": "Points"}
metric = st.selectbox("Chart", list(metric_labels), format_func=lambda k: metric_labels[k])
fmt = ".1%" if metric in ("target_share", "air_yards_share", "offense_snap_pct") else ".1f"
st.plotly_chart(line_chart(games.dropna(subset=[metric]), "week", metric, "player_name", f"{metric_labels[metric]} by week", metric_labels[metric], y_format=fmt, colors=colors), width="stretch")
chart_reading = {   # U-17: what a good position on the chart looks like
    "target_share": f"A good line sits high and flat: {ys_pct('WR', 'target_share', '28%')} or more week after week is what "
                    f"{YS_LABEL} wide receivers average. A line that steps up and stays up for two or three weeks is a new "
                    "role: add or start him before the points catch up (Trends lists them as role alerts).",
    "targets": f"A good line stays at 8 or more a game ({YS_LABEL} wide receivers average {ys_num('WR', 'targets_per_game', '9.2')}). "
               "One spike is a game plan; three weeks at a new level is a role.",
    "air_yards_share": "A good line stays above 30%: he gets the deep, valuable throws. A drop while his targets hold means a "
                       "shorter role (fewer long touchdowns).",
    "adot": "Neither high nor low is good on its own: a line around 12+ is a deep threat (big weeks and duds), around 7 or less "
            "is a short-area role. A sudden change means a new job in the offense.",
    "offense_snap_pct": "A good line is flat near the top: 80%+ every week is a full-time starter. A jump from about 60% to 80% "
                        "that holds is the first sign of a bigger role (Trends lists them as role alerts).",
    "points_current_scoring": "Points bounce around; read them next to Target %. Points well above a flat target line usually "
                              "mean touchdowns that will not repeat; a rising target line with flat points means points are coming.",
}
st.caption(chart_reading[metric])

# ---- early vs late ------------------------------------------------------------------------
st.subheader("Early vs late window")
howto("**Use it to tell a new role from a busy stretch.** Pick two stretches of weeks and compare the same receivers across them.",
      "If his **Target %** moved, his role changed. If only **Team tgt** (all his team's targets) moved, his team just threw more "
      "or less: the box score looks the same either way, this table tells them apart. Example: 5 targets a game both times, but "
      "18% → 26% of the team's: the offense now runs through him, and when the team throws more again, he gets more.",
      "A role change is worth acting on (add, start, or sell); a team that threw more for a few weeks usually goes back.")
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
howto("**Use it to catch a role changing now.** Each receiver's share of his team's targets over his last 3 and last 5 games, "
      "next to his whole season.",
      "Last 3 well above the season number is the earliest sign of a bigger role you can get from the box score: a waiver add "
      "or a player to start. Example: 17% for the season, 26% over the last 3: about 3 more targets a game if it holds.",
      "Last 3 well below it is the warning sign: check for an injury or a new receiver in the offense before you start him.",
      "Trends' **Role alerts** do this check for every player every week, with the snaps and the reason (a teammate out, a trade).")
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
    "**First-read share**: when the quarterback throws to the receiver he looked at first, how often it is this player. It shows "
    "who the play is drawn up for, which plain targets hide (a checkdown counts the same as a first look in the box score).",
    "Why it matters: it is the strongest usage sign we have. A high first-read share is the best sign a receiver's targets will "
    "last: start him, and trust a quiet week less. "
    + (f"Example: {leader('first_read_target_share', '.0%')} leads the regulars this season: that share of his team's "
       "first-look throws go to him. " if leader("first_read_target_share", ".0%") else "")
    + f"Yardstick: {YS_LABEL} wide receivers average {ys_pct('WR', 'first_read_target_share', '35%')}, tight ends "
    f"{ys_pct('TE', 'first_read_target_share', '22%')}; above 30% is the offense's first choice.",
    "**1st read of own tgt** asks something else: of *his* targets, how many came as the first look. High there but low overall "
    "= a specialist; low there with lots of targets = a safety valve.",
    "**Designed** throws (screens and the like) are counted apart. **Charting coverage** is the share of throws that were charted: "
    "below 90%, treat the numbers as partial. Charting by FTN Data (CC BY-SA 4.0) starts in 2022; earlier seasons show blank, not zero.",
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
st.subheader("Routes (estimated from who is on the field)")
howto(
    "**Route %** is how often he is on the field when the quarterback drops back to pass: the passing-play version of snap share. "
    "Why it matters: a receiver who runs a route on most pass plays gets chances every week. "
    f"Yardstick: 85%+ is a full-time role ({YS_LABEL if ys('WR', 'route_participation') is not None else 'the 2025 top-12'} "
    f"wide receivers: {ys_pct('WR', 'route_participation', '88%')}); "
    "under 70% he sits out a third of the pass plays.",
    "**TPRR** (targets per route) is how often he gets the ball thrown his way when he is out there: the stickiest receiver skill. "
    + (f"Example: {leader('tprr_proxy', '.0%')} leads this season: targeted on that share of his routes. " if leader("tprr_proxy", ".0%") else
       "Example: 28% means he is targeted on 28% of his routes. ")
    + f"Above 25% is WR1 territory ({YS_LABEL if ys('WR', 'tprr_proxy') is not None else 'the 2025 top-12'} wide receivers: "
    f"{ys_pct('WR', 'tprr_proxy', '28%')}). A high TPRR on a "
    "low Route % is a player to stash: more routes, more targets.",
    "**YPRR** (yards per route) adds what he does with them: 2.0+ is a top-24 receiver "
    f"({YS_LABEL if ys('WR', 'yprr_proxy') is not None else 'the 2025 top-12'} wide receivers: "
    f"{ys_num('WR', 'yprr_proxy', '2.4', '.1f')}), under 1.3 is a backup's number.",
    "These are estimates (a tight end who stayed in to block still counts as out there), so they run 10–15% low. Compare players "
    "with each other, not with numbers from other sites.",
    "The NFL publishes this data after the season, so the current season is blank here until then.",
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
    "Each row is one situation (a half, the score, the down, the field zone, or who played quarterback), with his share of the "
    "team's targets in that situation, in the games he played.",
    "Read it as a story: a receiver whose share jumps only when his team trails by 9+ is a garbage-time scorer, a risky start "
    "when his team is favoured. One whose share holds when leading is in the plan whatever the score.",
    "**QB on the play** splits the numbers by quarterback: the first thing to check after a quarterback change. Example: 28% of "
    "the targets with the starter, 17% with the backup: bench him while the backup plays.",
    "**Yds/Tgt** (yards per target) says how much each look is worth: 9+ is excellent, under 6 is short, low-value work.",
    "The score is the score *before* the snap; third and fourth down are grouped together.",
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
