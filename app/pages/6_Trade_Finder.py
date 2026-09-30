"""Trade Finder (plan B2): buy-low and sell-high lists where every candidate carries his lineup gain,
from the exact lineup service (B1). A player's "shape fit" is no longer a position rank but lineup
points: what the receiving roster's best lineup gains with him minus what the giving roster's loses
without him (his margin there), this week and over the next four weeks. Superflex and FLEX count by
eligibility: a QB3 behind two better QBs adds nothing; a WR who beats your FLEX adds the difference."""

import pandas as pd
import streamlit as st
from lib.db import query, require_relations
from lib.table import Col, detail_level, howto, prepare
from lib.ui import freshness_banner, league_seasons, perspective, setup

from league_lab.roster_value import RosterBoard, trade_candidates

setup("Trade Finder")
freshness_banner()
league_id, roster_id, members = perspective(require_team=True)
require_relations("mart_league_roster_horizon", "mart_player_availability")
labels = {int(r.roster_id): r.team_name for r in members.itertuples()}
managers = {int(r.roster_id): r.manager_name for r in members.itertuples()}


def narrow_table(df: pd.DataFrame, cols: list[str], overrides: dict, widths: dict[str, str | int], height: int | None = None) -> None:
    """A phone-first table: the registry's labels and formats (lib.table.prepare), the first column
    pinned and narrow widths, so the numbers stay on screen at 390 px (plan B2, round-2 convention 2)."""
    out, config = prepare(df, cols, overrides)
    for c, w in widths.items():
        if c in config:
            config[c]["width"] = w
    config[cols[0]]["pinned"] = True
    st.dataframe(out, column_config=config, hide_index=True, width="stretch", placeholder="", **({"height": height} if height else {}))

horizon = query(
    """select roster_id, week, this_week, horizon_first_week, horizon_last_week, role, slot, slot_type, sleeper_player_id,
              player_name, position, fantasy_positions, player_value, value_source, lineup_margin, is_locked, reason
       from analytics.mart_league_roster_horizon where league_id = %s""",
    (league_id,),
)
if horizon.empty:
    st.info("No lineups for the weeks ahead yet (the season is over, or `league-lab project` has not run since the last build).")
    st.stop()
this_week, first_w, last_w = (int(horizon[c].iloc[0]) for c in ("this_week", "horizon_first_week", "horizon_last_week"))
wk = f"wk {this_week}"
span = f"wks {first_w}–{last_w}" if last_w > first_w else wk
span_words = f"weeks {first_w}–{last_w}" if last_w > first_w else f"week {first_w}"
ls = league_seasons(league_id)
slots = list(ls.loc[ls["league_id"] == league_id, "roster_positions"].iloc[0] or [])

avail = query(
    """select sleeper_id as sleeper_player_id, player_name, position, rostered_by_roster_id, games_with_expected, ppg_std,
              expected_per_game, diff_per_game
       from analytics.mart_player_availability
       where league_id = %s and not is_free_agent and position in ('QB','RB','WR','TE')
         and coalesce(games_with_expected, 0) >= 2 and diff_per_game is not null""",
    (league_id,),
)


@st.cache_data(ttl=600, show_spinner="Solving lineups …")
def evaluate(league: str, roster: int, slot_list: tuple[str, ...], key: tuple, _rows: pd.DataFrame, _cands: pd.DataFrame):
    """Buy-low and sell-high lists for `roster` (league_lab.roster_value.trade_candidates): every number is
    a re-solved lineup, gain = best lineup with him - best lineup now, loss = his margin on his roster.
    `key` stands for the two frames in the cache key (they hold lists, which Streamlit cannot hash)."""
    board = RosterBoard(_rows.to_dict("records"), slot_list)
    buy, sell = trade_candidates(board, roster, _cands.to_dict("records"))
    return pd.DataFrame(buy), pd.DataFrame(sell)


data_key = (len(horizon), round(float(horizon["player_value"].fillna(0).sum()), 2), round(float(horizon["lineup_margin"].fillna(0).sum()), 2),
            len(avail), round(float(avail["diff_per_game"].sum()), 3))
buy, sell = evaluate(league_id, roster_id, tuple(slots), data_key, horizon, avail)

# ------------------------------------------------------------- filters (one row)
positions = ["All", "QB", "RB", "WR", "TE"]
f1, f2 = st.columns([3, 2])
with f1:
    pos = st.segmented_control("Position", positions, default="All", key="tf_position") or "All"
with f2:
    partner_opts = [None] + [r for r in sorted(labels, key=lambda r: labels[r]) if r != roster_id]
    partner = st.selectbox("Trade partner", partner_opts, format_func=lambda r: "Anyone" if r is None else labels[int(r)], key="tf_partner")


def keep(df: pd.DataFrame, owner_col: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df if pos == "All" else df[df["position"] == pos]
    if partner is not None:
        out = out[out[owner_col] == partner]
    return out


buy_f, sell_f = keep(buy, "owner"), keep(sell, "partner")

# ------------------------------------------------------------- the answer: cards
with st.container(border=True):
    top = buy_f[buy_f["fit_horizon"] > 0].head(1) if not buy_f.empty else buy_f
    if top.empty:
        st.markdown("**Buy low:** nobody scoring below his usage" + (f" at {pos}" if pos != "All" else "")
                    + (f" on {labels[int(partner)]}" if partner is not None else "")
                    + f" would add more to your lineup than he is worth to his own over {span_words}.")
    else:
        t = top.iloc[0]
        st.markdown(f"**Buy low: ask {labels[int(t['owner'])]} ({managers[int(t['owner'])]}) about {t['player_name']} ({t['position']}).** "
                    f"He scores {abs(t['diff_per_game']):.1f} a game below what his usage is worth.")
        st.markdown(f"He adds **{t['gain_week']:+.1f}** to your week-{this_week} lineup and costs them **{t['loss_week']:.1f}**; "
                    f"over {span_words}: **{t['gain_horizon']:+.1f}** for you, **{t['loss_horizon']:.1f}** for them "
                    f"(fit {t['fit_horizon']:+.1f}).")
with st.container(border=True):
    top = sell_f[sell_f["fit_horizon"] > 0].head(1) if not sell_f.empty else sell_f
    if top.empty:
        st.markdown("**Sell high:** none of your players scoring above his usage" + (f" at {pos}" if pos != "All" else "")
                    + f" is worth more to another lineup than to yours over {span_words}.")
    else:
        t = top.iloc[0]
        st.markdown(f"**Sell high: shop {t['player_name']} ({t['position']}) to {labels[int(t['partner'])]} ({managers[int(t['partner'])]}).** "
                    f"He scores {t['diff_per_game']:.1f} a game above what his usage is worth.")
        st.markdown(f"Their week-{this_week} lineup gains **{t['gain_week']:+.1f}**, yours loses **{t['loss_week']:.1f}**; "
                    f"over {span_words}: **{t['gain_horizon']:+.1f}** for them, **{t['loss_horizon']:.1f}** for you "
                    f"(fit {t['fit_horizon']:+.1f}).")

howto(
    "**Buy low** lists players on other rosters scoring *below* what their usage is worth (PPG − xPPG under zero): their manager "
    "sees a disappointing box score, the usage says it should improve. **Sell high** lists your players scoring *above* it.",
    f"**You gain** is how much your best lineup goes up with him, every slot re-picked (a WR who beats your FLEX counts; a QB3 behind "
    f"your two starting QBs adds nothing, even in superflex). **They lose** is how much their best lineup drops without him (0 if he "
    f"sits on their bench). Both are this week ({wk}) and over the next four weeks ({span}), from this league's projections.",
    "**Fit** = what the receiving lineup gains minus what the giving lineup loses: the lineup points the move creates. A big positive "
    "fit is a player who matters more to the other roster than to his own: an easier ask, or a better sale.",
    "This is not a valuation: it ignores what you would send back and who you would drop. It tells you where to look and what to say.",
    title="How to read this",
)

# the decision columns first, so they stay on screen at phone width; the owner last
base = ["player", "gain_week", "fit_horizon", "diff_per_game", "manager"]
extra = ["ppg_std", "expected_per_game", "loss_week", "gain_horizon", "loss_horizon", "fit_week"]
ov = {"player": Col("Player"), "manager": Col("Owner"),
      "gain_week": Col(f"You gain · {wk}", "signed1", f"What your best week-{this_week} lineup gains by adding him (his margin in your re-picked lineup)"),
      "gain_horizon": Col(f"You gain · {span}", "signed1", f"The same over {span_words}"),
      "loss_week": Col(f"They lose · {wk}", "num1", f"What his roster's best week-{this_week} lineup loses without him (0 on their bench)"),
      "loss_horizon": Col(f"They lose · {span}", "num1", f"The same over {span_words}"),
      "fit_week": Col(f"Fit · {wk}", "signed1", "You gain minus they lose, this week"),
      "fit_horizon": Col(f"Fit · {span}", "signed1", f"You gain minus they lose over {span_words}: the lineup points the trade creates")}
with st.expander(f"Buy low · {len(buy_f)} players scoring below their usage" + (f" ({pos})" if pos != "All" else ""), expanded=False):
    if buy_f.empty:
        st.caption("Nothing to show.")
    else:
        b = buy_f.copy()
        b["player"] = b["player_name"] + " (" + b["position"] + ")"
        b["manager"] = b["owner"].map(lambda r: labels.get(int(r), str(r)))
        narrow_table(b, base + (extra if detail_level() == "everything" else []), overrides=ov, height=min(80 + 35 * len(b), 600),
                     widths={"player": 150, "gain_week": 72, "fit_horizon": 72, "diff_per_game": 72, "manager": "medium"})

ov_s = {**ov, "manager": Col("Best fit", help=f"The roster whose lineup gains the most from him over {span_words}"),
        "gain_week": Col(f"They gain · {wk}", "signed1", f"What the best-fit roster's week-{this_week} lineup gains with him"),
        "gain_horizon": Col(f"They gain · {span}", "signed1", f"The same over {span_words}"),
        "loss_week": Col(f"You lose · {wk}", "num1", f"What your best week-{this_week} lineup loses without him (0 if he is on your bench)"),
        "loss_horizon": Col(f"You lose · {span}", "num1", f"The same over {span_words}"),
        "fit_week": Col(f"Fit · {wk}", "signed1", "They gain minus you lose, this week"),
        "fit_horizon": Col(f"Fit · {span}", "signed1", f"They gain minus you lose over {span_words}")}
with st.expander(f"Sell high · {len(sell_f)} of your players scoring above their usage" + (f" ({pos})" if pos != "All" else ""), expanded=False):
    if sell_f.empty:
        st.caption("Nothing to show.")
    else:
        s = sell_f.copy()
        s["player"] = s["player_name"] + " (" + s["position"] + ")"
        s["manager"] = s["partner"].map(lambda r: labels.get(int(r), str(r)) if pd.notna(r) else "")
        narrow_table(s, ["player", "loss_week", "fit_horizon", "manager", "diff_per_game"]
                     + (["ppg_std", "expected_per_game", "gain_week", "gain_horizon", "loss_horizon", "fit_week"] if detail_level() == "everything" else []),
                     overrides=ov_s, height=min(80 + 35 * len(s), 600),
                     widths={"player": 150, "loss_week": 72, "fit_horizon": 72, "manager": "medium", "diff_per_game": 72})
