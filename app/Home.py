"""League Lab explorer — home: what it is, your week at a glance, what's new, data & attribution."""

from pathlib import Path

import pandas as pd
import streamlit as st
from lib.db import query
from lib.table import glossary_rows, show
from lib.ui import freshness_banner, league_seasons, next_week_info, perspective, setup

setup("League Lab")
freshness_banner()

league_id, roster_id, members = perspective(require_team=False)
cal = next_week_info()
ls = league_seasons()
cur = ls.iloc[0] if not ls.empty else None

st.markdown(
    """
**League Lab** turns the public NFL data (nflverse, FTN charting, play-by-play) and your Sleeper league
into one place to look for value the box score hides: who is getting the opportunity, who is trending,
what the matchup and the market say, and how your league actually plays. Every number is built from
validated tables; nothing on these pages writes anywhere or calls an API. Pick your team in the sidebar
— the link then carries it, so you can send any page to a leaguemate.
"""
)

# ---------------------------------------------------------------- your week at a glance
if cur is not None and roster_id is not None:
    st.subheader("Your week at a glance")
    me = members.set_index("roster_id").loc[roster_id]
    prof = query(
        """select wins, losses, standing, all_play_win_pct, luck_wins, avg_bench_points_left, avg_lineup_efficiency as lineup_efficiency
           from analytics.mart_league_manager_profile where league_id = %s and roster_id = %s""",
        (league_id, roster_id),
    )
    nxt = query(
        """select m.week, o.team_name as opponent, m.opponent_roster_id
           from analytics.fct_league_matchup m
           left join analytics.dim_league_member o on o.league_id = m.league_id and o.roster_id = m.opponent_roster_id
           where m.league_id = %s and m.roster_id = %s and not m.is_scored order by m.week limit 1""",
        (league_id, roster_id),
    )
    c1, c2, c3, c4 = st.columns(4)
    if not prof.empty:
        r = prof.iloc[0]
        c1.metric(f"{me['team_name']}", f"{int(r['wins'])}-{int(r['losses'])}", f"#{int(r['standing'])} in the league", delta_color="off")
        c2.metric("All-play win %", f"{float(r['all_play_win_pct'] or 0):.0%}", f"{float(r['luck_wins'] or 0):+.1f} luck wins")
        c3.metric("Lineup efficiency", f"{float(r['lineup_efficiency'] or 0):.0%}", f"{float(r['avg_bench_points_left'] or 0):.1f} bench pts/wk left", delta_color="off")
    if not nxt.empty:
        c4.markdown(f"<div style='font-size:0.85rem;color:#6b6f76'>Week {int(nxt.iloc[0]['week'])} opponent</div>"
                    f"<div style='font-size:1.5rem;font-weight:600;line-height:1.3'>{nxt.iloc[0]['opponent'] or '—'}</div>", unsafe_allow_html=True)
    season = int(cal["season"]) if not cal.empty else None
    week = int(cal["next_week"]) if not cal.empty and pd.notna(cal["next_week"]) else None
    if season and week:
        g1, g2 = st.columns(2)
        with g1:
            st.markdown(f"**Your highest projections for NFL week {week}** (baseline formula, reference league's scoring; "
                        "the Rankings page has projection v2 in this league's scoring and how far to trust each)")
            proj = query(
                """select k.player_name, k.position, k.opponent, k.report_status, k.proj_points, k.rank_pos
                   from analytics.mart_player_week_rankings k
                   join analytics.mart_player_availability a on a.gsis_id = k.gsis_id and a.league_id = %s
                   where k.season = %s and k.week = %s and a.rostered_by_roster_id = %s and k.is_rankable
                   order by k.proj_points desc nulls last limit 9""",
                (league_id, season, week, roster_id),
            )
            show(proj, ["player_name", "position", "opponent", "report_status", "proj_points", "rank_pos"])
        with g2:
            st.markdown("**Movers on your roster** (last 3 games vs before)")
            mv = query(
                """select t.player_name, t.position, t.tags, t.momentum
                   from analytics.mart_player_trend_tags t
                   join analytics.mart_player_availability a on a.gsis_id = t.gsis_id and a.league_id = %s
                   where t.season = %s and a.rostered_by_roster_id = %s and t.opportunity_trend in ('rising', 'falling')
                   order by abs(t.momentum) desc limit 9""",
                (league_id, season, roster_id),
            )
            if mv.empty:
                st.caption("No trend calls yet — nothing is called before a player's fourth game. The Trends page shows an early read.")
            else:
                show(mv, ["player_name", "position", "tags", "momentum"])
elif cur is not None:
    st.info("Pick your team in the sidebar to see your week at a glance. Without a team, the pages show the whole league.")

# ---------------------------------------------------------------- pages
st.subheader("Pages")
st.markdown(
    """
| Page | What it answers |
|---|---|
| **Team Hub** | One roster through every lens: record, luck, lineup discipline, usage trends, keeper facts. Pick any team — the URL carries it |
| **Waiver Wire** | Free agents ranked by opportunity (shares, first-read share, snaps, expected points), not last week's box score |
| **Trends** | Who is trending up or down, by which usage metrics, with a noise check; defenses getting softer or stiffer |
| **Rankings** | Weekly projection per position with every term visible (form, usage, matchup, Vegas, home) and a backtest that says how far to trust it |
| **Matchups** | Next week's opponents, defense-vs-position ranks, cornerback coverage context, start/sit board |
| **Trade Finder** | Positional surplus/need across rosters, buy-low and sell-high lists from expected vs actual points |
| **League Intel** | Manager profiles: all-play luck, bench points left, FAAB/adds/trades, roster shape |
| **League** | Standings, weekly scores, matchups, transactions and draft review per season |
| **Players** | Season and game tables for QB/RB/WR/TE/K: shares against independent team totals, first-read share, routes proxy, red-zone share |
| **Receivers** | Compare receivers: target/air-yard share, aDOT, first-read share, routes proxy (TPRR/YPRR), context splits by half / score state / down / QB |
| **Kickers** | Kicker streaming: realized points in common eligible weeks, variability, changes |
| **Data Status** | Source freshness, coverage by season, identity quarantine, metric registry |

Tables start in **Essentials** mode (sidebar) — switch to **Everything** for denominators, noise statistics and every count.
"""
)

# ---------------------------------------------------------------- what's new
st.subheader("What's new")
changelog = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
if changelog.exists():
    text = changelog.read_text()
    parts = text.split("\n## ")
    if len(parts) > 1:
        latest = parts[1]
        st.markdown("### " + latest.strip())
        if len(parts) > 2:
            with st.expander("Earlier"):
                st.markdown("## " + "\n## ".join(p.strip() for p in parts[2:]))

# ---------------------------------------------------------------- glossary + data
st.subheader("Glossary")
with st.expander("Every column in the explorer, in plain English"):
    st.dataframe(glossary_rows(), hide_index=True, width="stretch", height=500)

st.subheader("Data & attribution")
st.markdown(
    """
* **NFL statistics, schedules, rosters, snap counts, play-by-play, participation, Next Gen Stats, PFR advanced stats** — the
  [nflverse](https://github.com/nflverse/nflverse-data) releases. Player id crosswalk from [dynastyprocess](https://github.com/dynastyprocess/data).
* **Play charting (first reads, throwaways, drops, play action, motion)** — [FTN Data](https://www.ftndata.com/) via nflverse,
  licensed **CC BY-SA 4.0**: first-read shares and the other charting-derived numbers on these pages are adaptations of FTN's
  work and are shared under the same licence, with attribution.
* **Expected points** — the [ffverse/ffopportunity](https://github.com/ffverse/ffopportunity) model, priced under this league's scoring.
* **League history, rosters, matchups, transactions** — the public [Sleeper](https://sleeper.com) API, read only.
* **Lines** — closing spreads and totals as published in the nflverse schedule file.

Nothing here is affiliated with the NFL, Sleeper, FTN or nflverse. Definitions for every metric are in `docs/METRICS.md`;
known limits in `docs/LIMITATIONS.md`. Freshness of each source is on the Data Status page.
"""
)
