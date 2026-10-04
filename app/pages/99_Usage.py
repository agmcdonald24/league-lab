"""Usage: which screens of the phone web app get used (Wave I-F, U-1; plan § 17 E; docs/HOSTING.md § "Usage").

Reads usage.events on the database this console points at (hosted: the Neon copy the API writes to). One row per
screen view: which screen, which league and team number, when, and a random id the browser keeps for one day —
nothing about a person. The API's GET /api/usage/summary answers the same questions.
"""

import pandas as pd
import streamlit as st
from lib.db import query
from lib.table import howto, show
from lib.ui import setup

setup("Usage", icon="📊")

ready = query("select exists (select 1 from information_schema.tables where table_schema = 'usage' "
              "and table_name = 'events') as ok")
if ready.empty or not bool(ready.iloc[0, 0]):
    st.info("Usage is not set up on this database yet. The hosted copy gets it from the next nightly (the sync runs "
            "`scripts/hosted_usage.sql`); a local database: `psql <pipeline DSN> -f scripts/hosted_usage.sql` "
            "(docs/HOSTING.md § Usage).")
    st.stop()

days = st.segmented_control("Window", [7, 14, 30], default=7, format_func=lambda d: f"Last {d} days") or 7
SINCE = ("at >= ((now() at time zone 'America/New_York')::date - %s::int)::timestamp "
         "at time zone 'America/New_York'")
DAY = "(at at time zone 'America/New_York')::date"
back = (days - 1,)

per = query(f"select {DAY} as day, screen, count(*)::int as views from usage.events where {SINCE} group by 1, 2", back)
by_day = query(f"select {DAY} as day, count(*)::int as views, count(distinct league_key)::int as leagues, "
               f"count(distinct session)::int as sessions from usage.events where {SINCE} group by 1 order by 1 desc", back)
tot = query(f"select count(*)::int as views, count(distinct league_key)::int as leagues, "
            f"count(distinct session)::int as sessions, count(distinct league_key) filter (where platform = 'mfl')::int "
            f"as mfl_leagues from usage.events where {SINCE}", back).iloc[0]

def n(k: int, word: str) -> str:
    return f"{k} {word}" if k == 1 else f"{k} {word}s"


with st.container(border=True):          # the answer first
    if int(tot["views"]) == 0:
        st.markdown(f"**No screen views in the last {days} days.**")
    else:
        top = per.groupby("screen")["views"].sum().sort_values(ascending=False)
        most = ", ".join(f"{s} ({int(v)})" for s, v in top.head(4).items())
        st.markdown(f"**{n(int(tot['views']), 'screen view')} in the last {days} days, from "
                    f"{n(int(tot['sessions']), 'browser-day')} in {n(int(tot['leagues']), 'league')} "
                    f"({int(tot['mfl_leagues'])} on MyFantasyLeague).** Most used: {most}.")
    st.caption("Days in New York time. A browser-day is one browser on one day (the random id resets at midnight): the "
               "same person on two days counts twice, two people on one phone once. Up to 10 minutes old.")

st.subheader("Views per screen per day")
howto("One row per screen of the web app (the router's names: **week** = My Week, **trade-calc** = the trade calculator, "
      "**player** = a player's page; **other** = a name the app did not send).",
      "One column per day, newest first; the last column is the window's total.",
      title="How to read this table")
if per.empty:
    st.caption("Nothing to show yet.")
else:
    grid = per.pivot_table(index="screen", columns="day", values="views", aggfunc="sum", fill_value=0)
    grid = grid[sorted(grid.columns, reverse=True)]
    grid.columns = [pd.Timestamp(c).strftime("%a %b %-d") for c in grid.columns]
    grid["Total"] = grid.sum(axis=1)
    grid = grid.sort_values("Total", ascending=False).reset_index().rename(columns={"screen": "Screen"})
    st.dataframe(grid, hide_index=True, width="stretch")

st.subheader("Per day")
with st.expander("Views, leagues and browser-days per day", expanded=True):
    show(by_day.rename(columns={"day": "Day", "views": "Views", "leagues": "Leagues", "sessions": "Browser-days"}))
st.caption("What a row holds: the time, the screen, the league id and team number, the platform, the release and the "
           "browser-day id. No names, usernames or IP addresses are kept. `LEAGUE_LAB_USAGE=off` on the server stops "
           "the counting. Views older than 180 days are deleted every night (the sync runs `scripts/hosted_usage.sql`).")
