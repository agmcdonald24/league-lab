"""League Lab explorer — home: My Week (the lineup decisions), "Worth a look" (buried numbers for your team),
the pages as the questions they answer, what's new in plain words, the glossary, data & attribution.
Plain-words rules for every page's copy: docs/WORDS.md."""

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
from lib.ui import current_leagues, freshness_banner, league_seasons, perspective, setup

setup("League Lab")
freshness_banner()

league_id, roster_id, members = perspective(require_team=False)
season = int(current_leagues().set_index("league_id").loc[league_id, "season"])

st.markdown(
    """
League Lab looks at your Sleeper league and tells you who to start, who to pick up and how your team really
stacks up, in your league's own scoring. Pick your league and your team in the menu (the arrow at the top left
on a phone) and every page follows your team. Send someone the link and it opens on the same team.
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

# ---------------------------------------------------------------- worth a look (plan U-14): buried numbers, one line each
# Four one-line links to things a manager would not find on his own, with his team's number where it is one
# query away (three queries in all). The fifth candidate, "your closest call this week", is My Week's first card
# just above, so it is not repeated here.
PAGES = Path(__file__).resolve().parent / "pages"


def page(*files: str) -> str | None:
    """The first of these page files that exists (U-16 folds League Intel into League)."""
    return next((f"pages/{f}" for f in files if (PAGES / f).exists()), None)


def page_name(path: str) -> str:
    return Path(path).stem.split("_", 1)[-1].replace("_", " ")


def ordinal(k: int) -> str:
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


here = {"league": league_id, **({"team": str(roster_id)} if roster_id is not None else {})}


def link(path: str | None, text: str, params: dict | None = None) -> None:
    if path is None:
        st.markdown(text)
    else:
        st.page_link(path, label=f"{text} · **{page_name(path)}**", query_params=params or here)


LEAGUE_PAGE = page("7_League_Intel.py", "8_League.py")
# a page link is one line that clips at phone width; these are sentences, so let them wrap
st.markdown("""<style>[data-testid="stPageLink-NavLink"], [data-testid="stPageLink-NavLink"] > span { height: auto; }
[data-testid="stPageLink-NavLink"] > span, [data-testid="stPageLink-NavLink"] > span * { white-space: normal; overflow: visible; }</style>""",
            unsafe_allow_html=True)
st.subheader("Worth a look")
luck = query(
    """select roster_id, team_name, luck_wins, avg_bench_points_left,
              rank() over (order by luck_wins desc nulls last) as luck_rank,
              rank() over (order by avg_bench_points_left desc nulls last) as bench_rank,
              count(*) over () as n_teams
       from analytics.mart_league_manager_profile where league_id = %s""",
    (league_id,),
)
mine = luck[luck["roster_id"] == roster_id] if roster_id is not None else luck.iloc[0:0]
if not mine.empty and pd.notna(mine["luck_wins"].iloc[0]):
    r = mine.iloc[0]
    w = float(r["luck_wins"])
    said = ("your record is better than your points" if w > 0.05 else "your points deserve a better record" if w < -0.05
            else "your record is about what your points deserve")
    link(LEAGUE_PAGE, f"**Schedule luck:** {w:+.1f} wins, {said} ({ordinal(int(r['luck_rank']))} luckiest of {int(r['n_teams'])})".replace("-", "−"))
elif not luck.dropna(subset=["luck_wins"]).empty:
    top = luck.dropna(subset=["luck_wins"]).sort_values("luck_wins", ascending=False).iloc[0]
    link(LEAGUE_PAGE, f"**Schedule luck:** {top['team_name']} has {float(top['luck_wins']):.1f} wins more than its points deserve, the most in the league")
if not mine.empty and pd.notna(mine["avg_bench_points_left"].iloc[0]):
    r = mine.iloc[0]
    kb, nt = int(r["bench_rank"]), int(r["n_teams"])
    # the League page's wording for the same rank: "the most" / "the fewest", never "10th most of 10"
    bench_txt = "the most in the league" if kb == 1 else "the fewest in the league" if kb == nt else f"{ordinal(kb)} most of {nt}"
    link(LEAGUE_PAGE, f"**Points left on your bench:** {float(r['avg_bench_points_left']):.1f} a week ({bench_txt})")
elif not luck.dropna(subset=["avg_bench_points_left"]).empty:
    top = luck.dropna(subset=["avg_bench_points_left"]).sort_values("avg_bench_points_left", ascending=False).iloc[0]
    link(LEAGUE_PAGE, f"**Points left on the bench:** {top['team_name']} leaves the most, {float(top['avg_bench_points_left']):.1f} a week")
if roster_id is not None:
    ls = league_seasons(league_id)
    dynasty = not ls.empty and ls["league_type"].iloc[0] == "dynasty"
    kc = query(
        """select k.player_name, k.position, k.position_rank_ppg, k.draft_round, a.acquired_how, a.acquired_label
           from analytics.mart_league_keeper_candidates k
           left join analytics.mart_league_acquisitions a
                  on a.league_id = k.league_id and a.roster_id = k.roster_id and a.sleeper_player_id = k.sleeper_player_id
           where k.league_id = %s and k.roster_id = %s and k.position in ('QB', 'RB', 'WR', 'TE') and k.games_played > 0
             and k.position_rank_ppg <= case when k.position in ('QB', 'TE') then 12 else 24 end""",
        (league_id, roster_id),
    )
    # the cheapest price for a starter-level player: a free pickup, then the latest draft round (trades cost players)
    kc["cost"] = [99.0 if how in ("free_agent", "waiver") else (float(rd) if how == "draft" and pd.notna(rd) else None)
                  for how, rd in zip(kc["acquired_how"], kc["draft_round"], strict=True)]
    kc = kc.dropna(subset=["cost"]).sort_values(["cost", "position_rank_ppg"], ascending=[False, True])
    if not kc.empty:
        b = kc.iloc[0]
        how = f" ({b['acquired_label']})" if isinstance(b["acquired_label"], str) and b["acquired_label"] else ""
        link(page("1_Team_Hub.py"), f"**Best bargain on your roster:** {b['player_name']}{how} is the "
                                    f"{b['position']}{int(b['position_rank_ppg'])} by points per game")
    else:
        link(page("1_Team_Hub.py"), f"**{'How your players joined your team' if dynasty else 'Keeper facts'}:** "
                                    "what each player cost and what he has scored")
    fr = query(
        """select gsis_id, player_name, first_read_share_l3 from analytics.mart_player_availability
           where league_id = %s and rostered_by_roster_id = %s and first_read_share_l3 > 0
           order by first_read_share_l3 desc limit 1""",
        (league_id, roster_id),
    )
    if not fr.empty:
        f = fr.iloc[0]
        link(page("0_Player.py"), f"**The quarterback's first look:** {f['player_name']} gets {float(f['first_read_share_l3']):.0%} "
                                  "of the throws that go to his quarterback's first choice (last 3 games)",
             params={"name": f["player_name"], "id": f["gsis_id"], **here})
else:
    link(page("1_Team_Hub.py"), "**Keeper facts and bargains:** how every player joined his team and what he has scored")
    link(page("10_Receivers.py"), "**Who the quarterback looks to first**, receiver by receiver")

# ---------------------------------------------------------------- pages, as the questions they answer
st.subheader("What each page answers")
GUIDE = [
    ("Who do I start this week?", ("5_Matchups.py",)),
    ("Is anyone on waivers worth a claim, and who do I drop?", ("2_Waiver_Wire.py",)),
    ("How good is my team, really?", ("1_Team_Hub.py",)),
    ("Who should I trade for, and who should I sell?", ("6_Trade_Finder.py",)),
    ("Who is projected to score the most this week?", ("4_Rankings.py",)),
    ("Who is getting more work lately, and who less?", ("3_Trends.py",)),
    ("Who has been lucky, and who leaves points on the bench?", ("7_League_Intel.py", "8_League.py")),
    ("Standings, every score, trades and how the draft turned out", ("8_League.py",)),
    ("How is one player doing, and is he worth it?", ("0_Player.py",)),
    ("Which receivers have a real role?", ("10_Receivers.py",)),
    ("Season stats for every player", ("9_Players.py",)),
    ("Did streaming kickers pay off?", ("11_Kickers.py",)),
    ("Is the data up to date?", ("12_Data_Status.py",)),
]
seen: dict[str, list[str]] = {}
for question, files in GUIDE:
    path = page(*files)
    if path is not None:
        seen.setdefault(path, []).append(question)
for path, questions in seen.items():
    link(path, " ".join(questions))
st.caption("Tables show the columns most people need; the **Table detail** switch in the menu changes how many.")

# ---------------------------------------------------------------- what's new, in plain words (plan U-14)
# app/whats_new.md holds one entry per release written for a league-mate; CHANGELOG.md stays the technical record.
st.subheader("What's new")
news = Path(__file__).resolve().parent / "whats_new.md"
if news.exists():
    entries = [e.strip().split("\n", 1) for e in news.read_text().split("\n## ")[1:]]
    if entries:
        st.markdown(f"**{entries[0][0]}**\n\n{entries[0][1] if len(entries[0]) > 1 else ''}")
        if len(entries) > 1:
            with st.expander("Earlier updates"):
                st.markdown("\n\n".join(f"**{e[0]}**\n\n{e[1] if len(e) > 1 else ''}" for e in entries[1:]))

# ---------------------------------------------------------------- glossary + data
st.subheader("Glossary")
with st.expander("Every column in the explorer, in plain English"):
    st.dataframe(glossary_rows()[["Column", "Meaning"]], hide_index=True, width="stretch", height=500)

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
