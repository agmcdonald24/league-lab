"""League Lab explorer — home: My Week (the lineup decisions), the pages, what's new, data & attribution."""

from pathlib import Path

import pandas as pd
import streamlit as st
from lib.cards import (
    decision_cards,
    decision_week,
    howto_cards,
    league_line,
    lineup_rows,
    lineup_table,
)
from lib.db import query
from lib.table import glossary_rows, show
from lib.ui import current_leagues, freshness_banner, perspective, setup

setup("League Lab")
freshness_banner()

league_id, roster_id, members = perspective(require_team=False)
season = int(current_leagues().set_index("league_id").loc[league_id, "season"])

st.markdown(
    """
League Lab reads your Sleeper league and the NFL's numbers and tells you who to start, who to pick up and how
your team stacks up against the rest of the league. Pick your league and team in the sidebar (the arrow at the
top left on a phone), and every page follows your team — send the link and it opens on the same team.
"""
)

# ---------------------------------------------------------------- my week (plan B4): the lineup decisions
# One projection everywhere (round-2 convention 3): the proposed lineup of the exact lineup service (B1,
# projection v2 in this league's scoring). The old "Your week" table (baseline model, reference scoring)
# is gone from Home; that model is only on Rankings behind its switch.
if roster_id is not None:
    me = members.set_index("roster_id").loc[roster_id]
    week = decision_week(season)
    st.subheader(f"My week — week {week}" if week else "My week")
    if week is None:
        st.info("The regular season is over: no lineup decisions left.")
    else:
        prof = query(
            """select wins, losses, standing from analytics.mart_league_manager_profile where league_id = %s and roster_id = %s""",
            (league_id, roster_id),
        )
        opp = query(
            """select o.team_name as opponent from analytics.fct_league_matchup m
               left join analytics.dim_league_member o on o.league_id = m.league_id and o.roster_id = m.opponent_roster_id
               where m.league_id = %s and m.roster_id = %s and m.week = %s""",
            (league_id, roster_id, week),
        )
        rows = lineup_rows(league_id, season, week, roster_id)
        bits = [f"**{me['team_name']}**"]
        if not prof.empty and pd.notna(prof.iloc[0]["wins"]):
            r = prof.iloc[0]
            bits.append(f"{int(r['wins'])}-{int(r['losses'])}, #{int(r['standing'])} in the league")
        if not opp.empty and isinstance(opp.iloc[0]["opponent"], str):
            bits.append(f"week {week} vs **{opp.iloc[0]['opponent']}**")
        st.markdown(" · ".join(bits))
        if not rows.empty:
            st.markdown(league_line(league_id, roster_id, week, rows))
        st.markdown("**The calls that matter**")
        decision_cards(league_id, roster_id, week, season, rows=rows)
        st.markdown("**Your lineup**")
        lineup_table(rows)
        with st.expander("Your full lineup: every slot, how close each call is, the bench, and who can't play"):
            lineup_table(rows, full=True)
        howto_cards()
        with st.expander("Movers on your roster (last 3 games vs before)"):
            mv = query(
                """select t.gsis_id, t.player_name, t.position, t.tags, t.momentum
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
else:
    st.info("Pick your team in the sidebar to see your week: the lineup to start and the closest calls. Without a team, the pages show the whole league.")

# ---------------------------------------------------------------- pages
st.subheader("Pages")
st.markdown(
    """
| Page | What it answers |
|---|---|
| **Player** | One player on one screen: how much he is used, this week's projection, whether he is available, and where he sits in his team's lineup. Tap a player's name in any table to open it |
| **Team Hub** | One roster through every lens: record, luck, lineup discipline, usage trends, keeper facts. Pick any team — the URL carries it |
| **Waiver Wire** | Free agents ranked by opportunity (shares, first-read share, snaps, expected points), not last week's box score |
| **Trends** | Who is trending up or down, by which usage metrics, with a noise check; defenses getting softer or stiffer |
| **Rankings** | Weekly projection per position with every term visible (form, usage, matchup, Vegas, home) and a backtest that says how far to trust it |
| **Matchups** | Your closest lineup calls of the week first, then defense-vs-position ranks, cornerback coverage context and the start/sit board |
| **Trade Finder** | Positional surplus/need across rosters, buy-low and sell-high lists from expected vs actual points |
| **League** | Schedule luck, points left on the bench and the weekly scoring rank for every team; roster rankings; standings, manager profiles, matchups, transactions and draft review per season |
| **Players** | Season and game tables for QB/RB/WR/TE/K: shares against independent team totals, first-read share, routes proxy, red-zone share |
| **Receivers** | Compare receivers: target/air-yard share, aDOT, first-read share, routes proxy (TPRR/YPRR), context splits by half / score state / down / QB |
| **Kickers** | Kicker streaming: realized points in common eligible weeks, variability, changes |
| **Data Status** | Source freshness, coverage by season, identity quarantine, metric registry |

Tables start in **Phone** mode on a phone (at most five columns) and **Essentials** elsewhere (sidebar) — switch to **Everything** for denominators, noise statistics and every count.
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
