"""Our record (plan E1): League Lab's projections against Sleeper's own (the numbers every Sleeper user already
gets for free) and what really happened, week by week, in the selected league's scoring.

Answer first: the start/sit calls each side got right and the average miss, in sentences and three numbers; the
tables (by position for the season, week by week) in expanders; "How to read this" says what the record is and is
not. Reads analytics.mart_projection_record (one row per league x season x week x position; scope 'season' = the
weeks scored so far). The record starts the first week Sleeper's projections were saved before kickoff; until then
the page says so instead of showing zeros."""

import pandas as pd
import streamlit as st
from lib.db import missing_relations, query
from lib.table import Col, show
from lib.ui import current_season, freshness_banner, perspective, setup

setup("Our record")
freshness_banner()
league_id, roster_id, members = perspective(require_team=False)
season = current_season(league_id)
league_name = query("select league_name from analytics.dim_league_season where league_id = %s", (league_id,))["league_name"].iloc[0]

STARTS = ("The record starts the first week Sleeper's projections are archived before kickoff: every week we save "
          "Sleeper's numbers next to ours before the first game, then check after the games whose were closer.")

rec = pd.DataFrame()
if not missing_relations(("mart_projection_record",)):
    rec = query(
        """select * from analytics.mart_projection_record
           where league_id = %s and season = %s order by scope, week, position""",
        (league_id, int(season) if season is not None else None),
    )

weeks = rec[rec["scope"] == "week"] if not rec.empty else rec
season_rows = rec[rec["scope"] == "season"] if not rec.empty else rec
scored_weeks = sorted(weeks.loc[weeks["status"] == "scored", "week"].astype(int).unique()) if not weeks.empty else []
in_play = sorted(weeks.loc[weeks["status"] == "in_play", "week"].astype(int).unique()) if not weeks.empty else []


def n(v) -> int:
    return 0 if v is None or pd.isna(v) else int(v)


def plural(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def span(ws: list[int]) -> str:
    return f"week {ws[0]}" if len(ws) == 1 else f"weeks {ws[0]}–{ws[-1]}"


# ---------------------------------------------------------------- the answer
if rec.empty:
    st.info(f"**No week on the record yet.** {STARTS} Sleeper is only asked from the nightly refresh, so the first "
            "week that refresh runs before a Thursday kickoff is the first week here. Nothing is filled in after the fact.")
elif not scored_weeks:
    first = in_play[0]
    a = weeks[(weeks["week"] == first) & (weeks["position"] == "ALL")]
    a = a.iloc[0] if not a.empty else None
    with st.container(border=True):
        st.markdown(f"**The record starts with week {first}.** Our projections and Sleeper's were both saved before the "
                    "week's first kickoff" + (f": {n(a['n_both'])} players projected by both, {n(a['pairs_listed'])} start/sit "
                                              "calls across the league." if a is not None else "."))
        st.caption(f"It is scored once the week's last game is in, in {league_name} scoring. {STARTS}")
else:
    last = scored_weeks[-1]
    a = season_rows[season_rows["position"] == "ALL"]
    a = a.iloc[0] if not a.empty else None
    pos = season_rows[season_rows["position"] != "ALL"]
    with st.container(border=True):
        lines = []
        if a is not None and n(a["pairs_n"]):
            pn, po, ps = n(a["pairs_n"]), n(a["pairs_ours_right"]), n(a["pairs_sleeper_right"])
            pdis, pod = n(a["pairs_disagree"]), n(a["pairs_ours_right_disagree"])
            psd = ps - n(a["pairs_both_right"])
            lines.append(f"**Through week {last}, we called {po} of {pn} start/sit calls right; Sleeper's numbers called {ps}.**")
            if pdis:
                lines.append(f"Where we and Sleeper disagreed ({plural(pdis, 'call')}), we were right {pod} "
                             f"time{'s' if pod != 1 else ''} and Sleeper {psd}.")
            else:
                lines.append("We and Sleeper made the same call every time.")
        else:
            lines.append(f"**Through week {last}:** no start/sit call could be graded yet.")
        if a is not None and pd.notna(a["ours_mae"]) and pd.notna(a["sleeper_mae"]):
            lines.append(f"Our projections missed by **{float(a['ours_mae']):.2f} points** a player on average; "
                         f"Sleeper's by **{float(a['sleeper_mae']):.2f}**.")
        both_sp = pos.dropna(subset=["ours_spearman", "sleeper_spearman"])
        if not both_sp.empty:
            better = int((both_sp["ours_spearman"] > both_sp["sleeper_spearman"]).sum())
            lines.append(f"Our order of players was closer to how they finished at {better} of {len(both_sp)} positions.")
        st.markdown("  \n".join(lines))
        with st.container(horizontal=True, wrap=True, gap="medium"):
            if a is not None and n(a["pairs_n"]):
                level = {"delta": "level with Sleeper", "delta_color": "off", "delta_arrow": "off"} if po == ps else \
                    {"delta": f"{po - ps:+d} vs Sleeper", "delta_color": "normal"}
                st.metric("Calls right", f"{po} of {pn}", width="content", **level,
                          help="Start/sit calls (the closest three per team each week) where the player we said to start outscored the other")
            if a is not None and pd.notna(a["ours_mae"]) and pd.notna(a["sleeper_mae"]):
                diff = float(a["ours_mae"]) - float(a["sleeper_mae"])
                level = {"delta": "level with Sleeper", "delta_color": "off", "delta_arrow": "off"} if abs(diff) < 0.005 else \
                    {"delta": f"{diff:+.2f} vs Sleeper", "delta_color": "inverse"}
                st.metric("Average miss", f"{float(a['ours_mae']):.2f} pts", width="content", **level,
                          help="How far our projection landed from the real score, in points, averaged over the players both projected")
        small = (f" {['One week is', 'Two weeks are', 'Three weeks are'][len(scored_weeks) - 1]} a small sample: one odd "
                 "Sunday moves these numbers a lot." if len(scored_weeks) < 4 else "")
        pending = (f" Week {in_play[-1]} is being played: both sides' numbers are saved, and it counts once its last game is in."
                   if in_play else "")
        st.caption(f"The record runs from week {scored_weeks[0]} ({span(scored_weeks)} scored), in {league_name} scoring: "
                   f"the first week Sleeper's projections were saved before kickoff.{small}{pending}")

# ---------------------------------------------------------------- the tables
# the record's columns are registered in lib/table.py (block "E1 record"); only the shared ones are relabelled here
LABELS = {"weeks_scored": Col("Weeks", "int", "Weeks scored so far"), "position": Col("Pos")}
if not rec.empty:
    sc = weeks[weeks["status"] == "scored"]
    with st.expander("The record by position, season so far"):
        if not season_rows.empty:
            p = season_rows[season_rows["position"] != "ALL"].copy()
            p["position"] = pd.Categorical(p["position"], ["QB", "RB", "WR", "TE"], ordered=True)
            show(p.sort_values("position"), ["position", "n_players", "ours_spearman", "sleeper_spearman", "ours_mae", "sleeper_mae",
                                             "ours_hit_rate", "sleeper_hit_rate", "weeks_scored"],
                 phone_cols=["position", "ours_spearman", "sleeper_spearman", "ours_mae", "sleeper_mae"], overrides=LABELS)
        else:
            st.caption("Nothing scored yet" + (f": week {in_play[0]} counts once its last game is in." if in_play else "."))
    with st.expander("Week by week"):
        calls = sc[sc["position"] == "ALL"]
        if not calls.empty:
            st.markdown("**Start/sit calls**")
            show(calls, ["week", "pairs_n", "pairs_ours_right", "pairs_sleeper_right", "pairs_disagree", "pairs_ours_right_disagree"],
                 phone_cols=["week", "pairs_n", "pairs_ours_right", "pairs_sleeper_right", "pairs_disagree"], overrides=LABELS)
        ranks = sc[sc["position"] != "ALL"]
        if not ranks.empty:
            st.markdown("**Projections by position**")
            show(ranks, ["week", "position", "n_players", "ours_spearman", "sleeper_spearman", "ours_mae", "sleeper_mae",
                         "ours_hit_rate", "sleeper_hit_rate"],
                 phone_cols=["week", "position", "ours_mae", "sleeper_mae", "ours_spearman"], overrides=LABELS)
        if calls.empty and ranks.empty:
            st.caption("No week scored yet" + (f": week {in_play[0]} counts once its last game is in." if in_play else "."))

# ---- V-1 (Wave I-G): our lineups against the ones started — the decision record graded (league_lab.validation over
# mart_decision_record / mart_decision_calls; the same block /api/record's `decisions` sends; METRICS § "The decision record")
st.subheader("Our lineups against the ones started")
if missing_relations(("mart_decision_record", "mart_decision_calls")):
    st.caption("The decision record is not built on this database yet (`league-lab validate`, then the dbt marts).")
else:
    from league_lab import validation as V

    s_ = int(season) if season is not None else None
    dec = V.summary(query("select * from analytics.mart_decision_record where league_id = %s and season = %s order by week, roster_id",
                          (league_id, s_)),
                    query("select * from analytics.mart_decision_calls where league_id = %s and season = %s "
                          "order by week, roster_id, call_rank", (league_id, s_)))
    if not dec["available"]:
        st.caption("Our lineups are graded against the ones started once a week on the record has been scored.")
    else:
        tot, cal = dec["season_totals"], dec["calls"]
        with st.container(border=True):
            st.markdown("  \n".join(x for x in (dec["sentences"]["edge"], dec["sentences"]["calls"]) if x))
            with st.container(horizontal=True, wrap=True, gap="medium"):
                st.metric("Our lineups would have added", f"{tot['edge']:+.1f} pts", width="content",
                          help="Ours minus started, summed over every team and scored week: what following the lineups we "
                               "recommended before kickoff would have added")
                st.metric("Best lineup in hindsight", f"+{tot['regret']:.1f} pts", width="content",
                          help="The best lineup each roster could have started knowing the scores, minus the one started")
                cf = cal["coin_flips"]
                if cf["n"]:
                    st.metric("Coin flips landed", f"{100 * cf['won'] / cf['n']:.0f}%", width="content",
                              delta=f"{100 * (cf['won'] - cf['expected']) / cf['n']:+.0f} pts vs expected", delta_color="off",
                              help="The cards' closest calls (under 55%): how often the player we started outscored the one on the bench")
            if dec["sentences"]["news"]:
                st.caption(dec["sentences"]["news"])
            if dec["note"]:
                st.caption(dec["note"])
        DEC_COLS = {"week": Col("Week", "int"), "record_source": Col("Record", "text", "kickoff = recorded before the week's "
                    "first kickoff; reconstructed = rebuilt after the fact from the projections locked then"),
                    "rosters": Col("Teams", "int"), "submitted": Col("Started", "num1", "Points of the lineups started"),
                    "app": Col("Ours", "num1", "Points our recorded lineups would have scored"),
                    "optimum": Col("Best", "num1", "Points of the best lineups in hindsight"),
                    "edge": Col("Added", "signed1", "Ours minus started"), "regret": Col("Left on bench", "num1", "Best minus started"),
                    "news_rosters": Col("News", "int", "Lineups with a starter whose injury report changed after our build")}
        with st.expander("Our lineups week by week, and how the close calls landed"):
            show(pd.DataFrame(dec["weeks"]), list(DEC_COLS), phone_cols=["week", "submitted", "app", "edge"], overrides=DEC_COLS)
            if cal["table"]:
                st.markdown(f"**The close calls: {cal['n']} graded, Brier score {cal['brier']:.3f}** (0 = perfect; 0.25 = "
                            "a coin flip every time). Calls grouped by the percentage the card gave, lowest first:")
                CAL_COLS = {"bin": Col("Group", "int"), "n": Col("Calls", "int"),
                            "predicted": Col("We said", "pct", "The average percentage the cards gave the player we started"),
                            "observed": Col("Landed", "pct", "How often he outscored the player on the bench (a tie counts half)")}
                show(pd.DataFrame(cal["table"]), list(CAL_COLS), overrides=CAL_COLS)
# ---- end V-1

# ---------------------------------------------------------------- how to read this
with st.expander("How to read this"):
    st.markdown(
        "- **Use it to decide how much to trust us.** If we call more start/sit decisions right than Sleeper's free numbers, "
        "follow the cards on close calls; if not, treat them as a second opinion.\n"
        "- **What is compared.** Every week, before the first game kicks off, we save our projections and Sleeper's (the ones "
        f"in the Sleeper app). After the games we check whose were closer. Both are counted in {league_name} scoring: "
        "Sleeper's stat line (yards, catches, touchdowns) is counted your league's way, not Sleeper's default.\n"
        "- **Start/sit calls** are the three closest calls per team each week, the ones on the My Week cards (start A over B). "
        "We said start A; Sleeper's call is whichever of the two it projected higher. The right call is whoever scored more.\n"
        "- **The average miss** is how far a projection landed from the real score, in points, over every player both "
        "projected who played (Out and Doubtful players left out). **Order** is the order score: how well the projected "
        "order matched the real one (1 = perfect, 0 = random). **Top group**: how many of the week's real top 12 QBs, "
        "24 RBs, 36 WRs and 12 TEs each side had in its own top group.\n"
        "- **What it is not.** It is not a test on past seasons (that is Rankings' backtest), and it does not go back "
        "before the first week Sleeper's numbers were saved before kickoff: earlier weeks are not filled in after the fact. "
        "It covers players both sides projected, not every name Sleeper lists; a defense is left out (its points are not "
        "counted from a stat line). A few weeks are a small sample.\n"
        "- **Same moment for both.** Sleeper's numbers are the last ones saved before the week's first kickoff, the moment "
        "ours are locked. News after that (a Sunday inactive) is in neither."
    )
