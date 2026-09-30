"""Trade Finder (plan T-01 trade evaluator + T-02 simulator, on B1's exact lineup service and B2's roster value).

Phone first, answer first: three cards open the page — the best trade partner (the trade that raises *both* lineups,
`league_lab.trades.partners`), your best buy-low by position and your best sell-high (B2's lists) — then "Try a
trade" (pick a partner, tick players both ways: both lineups before / after this week and over four weeks, who starts
and who sits, depth and the closest call, the league rank change, the roster-size consequence, the fit next to the
market price and a one-sentence verdict), then the buy-low / sell-high lists in expanders, filterable by position and
owner. The package lives in the URL (`?partner=…&give=…&get=…`, Sleeper ids, next to the league / team that
`perspective()` writes) so a copied link reproduces it. Every table carries `gsis_id`, so names open the Player card.
"""

from datetime import UTC, date, datetime

import pandas as pd
import streamlit as st
from lib.cards import slot_label
from lib.db import query, require_relations
from lib.table import Col, detail_level, howto, show
from lib.ui import freshness_banner, league_seasons, perspective, player_link, setup

from league_lab import trades as T
from league_lab.lineup import Player
from league_lab.roster_value import RosterBoard, trade_candidates

setup("Trade Finder")
freshness_banner()
league_id, roster_id, members = perspective(require_team=True)
require_relations("mart_league_roster_horizon", "mart_player_availability", "mart_league_roster_rankings",
                  "mart_player_week_features", "dim_game", "mart_league_player_season", "dim_player")
labels = {int(r.roster_id): r.team_name for r in members.itertuples()}
managers = {int(r.roster_id): r.manager_name for r in members.itertuples()}
ss = st.session_state


def team(r) -> str:
    return labels.get(int(r), f"Team {r}")


def who(r) -> str:
    """Team (manager)."""
    m = managers.get(int(r), "")
    return f"{team(r)} ({m})" if m else team(r)


horizon = query(
    """select roster_id, week, this_week, horizon_first_week, horizon_last_week, role, slot, slot_type, sleeper_player_id,
              gsis_id, player_name, position, fantasy_positions, player_value, value_source, lineup_margin, is_locked, reason
       from analytics.mart_league_roster_horizon where league_id = %s""",
    (league_id,),
)
if horizon.empty:
    st.info("No lineups for the weeks ahead yet (the season is over, or the nightly refresh has not run since the last build).")
    st.stop()
this_week, first_w, last_w = (int(horizon[c].iloc[0]) for c in ("this_week", "horizon_first_week", "horizon_last_week"))
wk = f"wk {this_week}"
span = f"wks {first_w}–{last_w}" if last_w > first_w else wk
span_words = f"weeks {first_w}–{last_w}" if last_w > first_w else f"week {first_w}"
ls = league_seasons(league_id)
lrow = ls.loc[ls["league_id"] == league_id].iloc[0]
slots = list(lrow["roster_positions"] or [])
season = int(lrow["season"])

avail = query(
    """select sleeper_id as sleeper_player_id, gsis_id, player_name, position, rostered_by_roster_id, games_with_expected, ppg_std,
              expected_per_game, diff_per_game
       from analytics.mart_player_availability
       where league_id = %s and not is_free_agent and position in ('QB','RB','WR','TE')
         and coalesce(games_with_expected, 0) >= 2 and diff_per_game is not null""",
    (league_id,),
)
# the market side (kept apart from the lineups): rest-of-season projected points in this league's scoring, and the
# best free agent's at each position (the replacement level the market score is measured above)
market_rows = query(T.MARKET_SQL, (league_id, season, this_week))
points = dict(zip(market_rows["player_key"], market_rows["season_points"], strict=True)) if not market_rows.empty else {}
repl_rows = query(T.REPLACEMENT_SQL, (league_id, season, this_week, league_id))
replacement = dict(zip(repl_rows["position"], repl_rows["replacement"], strict=True)) if not repl_rows.empty else {}
repl_name = dict(zip(repl_rows["position"], repl_rows["replacement_name"], strict=True)) if not repl_rows.empty else {}

data_key = (len(horizon), round(float(horizon["player_value"].fillna(0).sum()), 2), round(float(horizon["lineup_margin"].fillna(0).sum()), 2),
            len(avail), round(float(avail["diff_per_game"].sum()), 3), len(points), round(float(sum(points.values())), 2),
            tuple(sorted((k, round(float(v), 2)) for k, v in replacement.items())))

PHONE = detail_level() == "phone"


def fit(widths: dict[str, int]) -> dict[str, int] | None:
    """Column widths in px that keep a table inside a 390 px screen (Phone level); desktop sizes itself."""
    return widths if PHONE else None


def board_of(rows: pd.DataFrame) -> RosterBoard:
    return RosterBoard(rows.to_dict("records"), tuple(slots))


board = board_of(horizon)
market = T.market_by_player(board, points)
prices = T.price_by_player(board, market, replacement)
info = horizon.sort_values("week").drop_duplicates("sleeper_player_id").set_index("sleeper_player_id")
now_rows = horizon[horizon["week"] == this_week].set_index("sleeper_player_id")


def name(pid) -> str:
    return str(info.at[pid, "player_name"]) if pid in info.index and pd.notna(info.at[pid, "player_name"]) else str(pid)


def gsis(pid):
    return info.at[pid, "gsis_id"] if pid in info.index and pd.notna(info.at[pid, "gsis_id"]) else None


def pos(pid) -> str:
    return str(info.at[pid, "position"]) if pid in info.index and pd.notna(info.at[pid, "position"]) else ""


def link(pid) -> str:
    return player_link(gsis(pid), name(pid))


def names(ids) -> str:
    parts = [link(p) for p in ids]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def week_value(pid):
    """(this week's value, why he can't play) from his lineup row this week."""
    if pid not in now_rows.index:
        return None, None
    r = now_rows.loc[pid]
    if r["role"] == "unplayable":
        return None, (r["reason"] or "can't play")
    return (float(r["player_value"]) if pd.notna(r["player_value"]) else None), None


def label(pid) -> str:
    v, why = week_value(pid)
    wv = f"{v:.1f} this week" if v is not None else (why or "no value yet")
    return f"{name(pid)} ({pos(pid)}) · {wv}"


def whole_or_none(values: dict, pid):
    return T.whole(values[pid]) if pid in values else None


@st.cache_data(ttl=600, show_spinner="Looking for trades that help both teams …")
def partner_sweep(league: str, roster: int, slot_list: tuple[str, ...], key: tuple, _rows: pd.DataFrame):
    """league_lab.trades.partners for `roster`: the best 1-for-1 and 2-for-1 with every other team (every number a
    re-solved lineup). `key` stands for the frame in the cache key."""
    stats: dict = {}
    found = T.partners(board_of(_rows), roster, stats=stats)
    return found, stats


@st.cache_data(ttl=600, show_spinner="Solving lineups …")
def fits(league: str, roster: int, slot_list: tuple[str, ...], key: tuple, _rows: pd.DataFrame, _cands: pd.DataFrame):
    """Buy-low and sell-high lists for `roster` (league_lab.roster_value.trade_candidates): every number is
    a re-solved lineup, gain = best lineup with him - best lineup now, loss = his margin on his roster.
    `key` stands for the two frames in the cache key (they hold lists, which Streamlit cannot hash)."""
    b = RosterBoard(_rows.to_dict("records"), slot_list)
    buy_, sell_ = trade_candidates(b, roster, _cands.to_dict("records"))
    return pd.DataFrame(buy_), pd.DataFrame(sell_)


@st.cache_data(ttl=600, show_spinner=False)
def free_agent_pool(league: str, season_: int, weeks: tuple[int, ...]) -> tuple[dict, dict]:
    """Free agents on an active NFL roster (not Out / IR), each as the lineup would carry him per week: this league's
    projection; a bye (no projection), Out / Doubtful, NFL injured reserve or a game already kicked off = can't play."""
    fa = query(
        """select a.sleeper_id, a.gsis_id, a.player_name, a.position, p.week,
                  round(p.proj_points::numeric, 2)::double precision as value, f.report_status, f.roster_status,
                  coalesce(f.team, case when a.position = 'DEF' then a.sleeper_id else a.nfl_team end) as team
           from analytics.mart_player_availability a
           join ops.projections p
             on p.league_id = a.league_id and p.season = %s and p.week = any(%s) and p.gsis_id = coalesce(a.gsis_id, a.sleeper_id)
           left join analytics.mart_player_week_features f on f.gsis_id = a.gsis_id and f.season = p.season and f.week = p.week
           where a.league_id = %s and a.is_free_agent and a.roster_status = 'ACT' and a.sleeper_id is not null
             and a.injury_status is distinct from 'Out' and a.injury_status is distinct from 'IR'""",
        (season_, list(weeks), league),
    )
    games = query("""select home_team, away_team, kickoff_at from analytics.dim_game
                     where season = %s and week = %s and season_type = 'REG'""", (season_, weeks[0]))
    kick = {}
    for g in games.itertuples():
        kick[g.home_team] = kick[g.away_team] = pd.Timestamp(g.kickoff_at)
    now = pd.Timestamp(datetime.now(UTC))
    pool: dict[str, dict[int, Player]] = {}
    meta: dict[str, dict] = {}
    for r in fa.itertuples():
        t = {"LAR": "LA"}.get(r.team, r.team)
        why = ("Out" if r.report_status in ("Out", "Doubtful") else "NFL injured reserve" if r.roster_status == "RES"
               else "game started" if int(r.week) == weeks[0] and t in kick and kick[t] <= now else None)
        pool.setdefault(r.sleeper_id, {})[int(r.week)] = Player(
            id=r.sleeper_id, position=r.position, value=r.value, value_source="proj_points", playable=why is None, reason=why)
        meta[r.sleeper_id] = {"player_name": r.player_name, "position": r.position, "gsis_id": r.gsis_id}
    return pool, meta


@st.cache_data(ttl=600, show_spinner="Re-solving both lineups …")
def simulate(league: str, season_: int, me: int, give: tuple[str, ...], get: tuple[str, ...], key: tuple,
             _rows: pd.DataFrame, _market: dict, _prices: dict):
    """league_lab.trades.evaluate; with the free agents for the fill only when the trade opens a roster spot."""
    b = board_of(_rows)
    t = T.evaluate(b, give, get, market=_market, prices=_prices)
    fa_meta = {}
    if t.mine.opened or t.theirs.opened:
        pool, fa_meta = free_agent_pool(league, season_, tuple(b.weeks))
        t = T.evaluate(b, give, get, market=_market, prices=_prices, free_agents=pool)
    return t, fa_meta


found, sweep_stats = partner_sweep(league_id, roster_id, tuple(slots), data_key, horizon)
ranked = [p for p in found if p.best is not None]
buy, sell = fits(league_id, roster_id, tuple(slots), data_key, horizon, avail)


def market_caption(pk: T.Package) -> str:
    out, unk_o = T.season_value(prices, pk.give)
    inc, unk_i = T.season_value(prices, pk.get)
    extra = " (some players have no projection yet)" if unk_o or unk_i else ""
    return f"Market (season points above the best free agent at the position): you give {out}, you get {inc}{extra}."


# ------------------------------------------------------------- the answer: three cards
with st.container(border=True):
    if ranked:
        pk = ranked[0].best
        st.markdown(f"**Best partner: {who(ranked[0].roster_id)}.** Your {names(pk.give)} for their {names(pk.get)}: you "
                    f"**{pk.my_week:+.1f}** this week and **{pk.my_horizon:+.1f}** over {span_words}, them "
                    f"**{pk.their_week:+.1f}** and **{pk.their_horizon:+.1f}**.")
        st.caption(market_caption(pk))
        if st.button("Try this trade", key="tf_card_0", width="content"):
            ss["tf_pending"] = (ranked[0].roster_id, list(pk.give), list(pk.get))
            st.toast("Loaded in \"Try a trade\" below.")
    else:
        st.markdown(f"**No trade raises both lineups.** Nobody in the league has a player who would improve your lineup over "
                    f"{span_words} and also needs one of yours. Try a trade you have in mind below.")

POSITIONS = ["QB", "RB", "WR", "TE"]


def best_by_position(df: pd.DataFrame) -> dict[str, pd.Series]:
    """The first row per position with a positive fit over the horizon (the lists are sorted best first)."""
    out = {}
    if df.empty:
        return out
    for p in POSITIONS:
        sub = df[(df["position"] == p) & (df["fit_horizon"] > 0)]
        if not sub.empty:
            out[p] = sub.iloc[0]
    return out


with st.container(border=True):
    top = best_by_position(buy)
    if not top:
        st.markdown(f"**Buy low:** nobody scoring below his usage would add more to your lineup than he is worth to his "
                    f"own over {span_words}.")
    else:
        t = max(top.values(), key=lambda r: (r["fit_horizon"], r["gain_horizon"]))
        st.markdown(f"**Buy low: ask {who(t['owner'])} about {player_link(t['gsis_id'], t['player_name'])} ({t['position']}).** "
                    f"He scores {abs(t['diff_per_game']):.1f} a game below what his usage is worth, adds **{t['gain_week']:+.1f}** "
                    f"to your week-{this_week} lineup and costs them **{t['loss_week']:.1f}** (fit **{t['fit_horizon']:+.1f}** "
                    f"over {span_words}).")
        bits = []
        for p in POSITIONS:
            if p in top:
                r = top[p]
                bits.append(f"{p} {player_link(r['gsis_id'], r['player_name'])} ({team(r['owner'])}: "
                            f"{r['gain_week']:+.1f} this week, fit {r['fit_horizon']:+.1f})")
            else:
                bits.append(f"{p}: nobody")
        st.markdown("Best by position: " + " · ".join(bits) + ".")

with st.container(border=True):
    stop_ = sell[sell["fit_horizon"] > 0].head(1) if not sell.empty else sell
    if stop_.empty:
        st.markdown(f"**Sell high:** none of your players scoring above his usage is worth more to another lineup than to "
                    f"yours over {span_words}.")
    else:
        t = stop_.iloc[0]
        st.markdown(f"**Sell high: shop {player_link(t['gsis_id'], t['player_name'])} ({t['position']}) to {who(t['partner'])}.** "
                    f"He scores {t['diff_per_game']:.1f} a game above what his usage is worth. Their week-{this_week} lineup "
                    f"gains **{t['gain_week']:+.1f}**, yours loses **{t['loss_week']:.1f}** (fit **{t['fit_horizon']:+.1f}** "
                    f"over {span_words}).")


def short(ids) -> str:
    """Last names for a two-player side ("Hall + Judkins"), the full name for one."""
    return " + ".join(name(x).split(" ", 1)[-1] if len(ids) > 1 else name(x) for x in ids)


with st.expander(f"Every team: the best trade that helps both lineups ({span_words})", expanded=False):
    rows = []
    for p in found:
        for shape, pk in (("1-for-1", p.one_for_one), ("2-for-1", p.two_for_one)):
            if pk is None:
                continue
            first_in = max(pk.get, key=lambda x: (market.get(x, 0.0), x))
            rows.append({"partner": team(p.roster_id), "you_get": " + ".join(name(x) for x in pk.get),
                         "package": f"{short(pk.get)} for {short(pk.give)}",
                         "get_name": name(first_in), "gsis_id": gsis(first_in),
                         "you_give": " + ".join(name(x) for x in pk.give), "you_gain_h": pk.my_horizon, "they_gain_h": pk.their_horizon,
                         "you_gain_w": pk.my_week, "they_gain_w": pk.their_week, "shape": shape,
                         "price_out": T.season_value(prices, pk.give)[0], "price_in": T.season_value(prices, pk.get)[0]})
    if rows:
        ov = {"partner": Col("Team"),
              "you_get": Col("You get", help="The player(s) you would ask for (the link opens the one worth most over the season)"),
              "you_give": Col("You give"),
              "you_gain_h": Col(f"You · {span}", "signed1", f"What your best lineups over {span_words} gain, added up"),
              "they_gain_h": Col(f"Them · {span}", "signed1", f"What their best lineups over {span_words} gain, added up"),
              "you_gain_w": Col(f"You · {wk}", "signed1"), "they_gain_w": Col(f"Them · {wk}", "signed1"),
              "shape": Col("Shape"),
              "price_out": Col("Market out", "int", "Season points above a free agent that you give"),
              "price_in": Col("Market in", "int", "Season points above a free agent that you get"),
              "package": Col("Trade", help="What you get for what you give (the link opens the player you get who is worth most over the season)")}
        cols = ["partner", "you_get", "you_give", "you_gain_h", "they_gain_h"]
        show(pd.DataFrame(rows), cols + (["you_gain_w", "they_gain_w", "price_out", "price_in", "shape"] if detail_level() == "everything" else []),
             overrides=ov, links={"you_get": ("gsis_id", "get_name"), "package": ("gsis_id", "get_name")}, pin=True,
             phone_cols=["partner", "package", "you_gain_h", "they_gain_h"],
             widths=fit({"partner": 84, "package": 118, "you_gain_h": 58, "they_gain_h": 58})
             or {"partner": "medium", "you_get": "medium", "you_give": "medium", "you_gain_h": 90, "they_gain_h": 90})
    missing = [team(p.roster_id) for p in found if p.best is None]
    if missing:
        st.caption("No trade helps both lineups with: " + ", ".join(missing) + ".")
    st.caption(f"Checked every one-for-one and two-for-one with {len(found)} teams in {sweep_stats.get('seconds', 0):.1f} s "
               f"({sweep_stats.get('evaluated', 0)} trades re-solved in full; the rest ruled out by what each player could add).")

# ------------------------------------------------------------- try a trade (the simulator)
st.subheader("Try a trade")
order = [p.roster_id for p in found]                       # best partner first
partner_opts = order + [r for r in sorted(labels) if r not in order and r != roster_id]
ctx = (league_id, roster_id)
qp = st.query_params
url_state = (qp.get("partner"), tuple(T.parse_ids(qp.get("give"))), tuple(T.parse_ids(qp.get("get"))))
has_url = any(k in qp for k in ("partner", "give", "get"))
external = has_url and url_state != ss.get("tf_url_written")
default = (ranked[0].roster_id, list(ranked[0].best.give), list(ranked[0].best.get)) if ranked else (partner_opts[0], [], [])
pending = ss.pop("tf_pending", None)
seed, dropped = None, []
if pending is not None:
    seed = pending
elif external:
    try:
        p_url = int(url_state[0]) if url_state[0] is not None else None
    except ValueError:
        p_url = None
    if p_url not in partner_opts:
        if url_state[0] is not None:
            dropped.append(f"team {url_state[0]}")
        # no usable team in the link: the team that owns the players it asks for, else the best partner
        owners = [board.owner(x) for x in url_state[2] if board.owner(x) in partner_opts]
        p_url = owners[0] if owners else default[0]
    seed = (p_url, list(url_state[1]), list(url_state[2]))
elif ss.get("tf_ctx") != ctx or ss.get("tf_partner") not in partner_opts:
    seed = default
if seed is not None:
    p0 = seed[0] if seed[0] in partner_opts else default[0]
    g0, t0, bad = T.clean_package(board, roster_id, p0, seed[1], seed[2])
    dropped += [name(x) if board.owner(x) is not None else f"id {x}" for x in bad]
    ss["tf_partner"], ss["tf_give"], ss["tf_get"], ss["tf_ctx"] = p0, g0, t0, ctx
else:
    ss["tf_partner"] = ss["tf_partner"]            # re-assigned: survives a page change (see perspective())
if dropped:
    st.caption("Left out from the link (not on these rosters any more): " + ", ".join(dropped) + ".")

partner = st.selectbox("Trade partner", partner_opts, key="tf_partner", format_func=who)
mine_ids = sorted(board.roster(roster_id), key=lambda x: (-(week_value(x)[0] or -1.0), name(x)))
theirs_ids = sorted(board.roster(partner), key=lambda x: (-(week_value(x)[0] or -1.0), name(x)))
ss["tf_give"] = [x for x in ss.get("tf_give", []) if x in mine_ids]
ss["tf_get"] = [x for x in ss.get("tf_get", []) if x in theirs_ids]
give = st.multiselect("You give", mine_ids, key="tf_give", format_func=label, placeholder="Tick your players")
get = st.multiselect("You get", theirs_ids, key="tf_get", format_func=label, placeholder=f"Tick {team(partner)}'s players")

# the package is the URL: a copied link opens the same trade (league and team come from perspective())
written = (str(partner), tuple(give), tuple(get))
st.query_params["partner"] = str(partner)
for k, v in (("give", give), ("get", get)):
    if v:
        st.query_params[k] = ",".join(v)
    elif k in st.query_params:
        del st.query_params[k]
ss["tf_url_written"] = written


def rank_words(k: int) -> str:
    suffix = "th" if 10 <= k % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(k % 10, "th")
    return f"{k}{suffix}"


def lineup_frame(side: T.Side) -> tuple[pd.DataFrame, list[str]]:
    """This week's lineup after the trade, slot by slot, with the change against the same slot before (blank: no
    change; a teammate may slide from another slot, and the changes add up to the lineup's change); who starts that
    did not (new, from the bench) and who left the lineup (traded, cut, or to the bench)."""
    before = {s.slot.label: s for s in side.lineup_before.starts}
    cut = {c.player_id for c in side.cuts}
    rows = []
    for s in side.lineup_after.starts:
        b = before.get(s.slot.label)
        bv = (b.value or 0.0) if b is not None and b.player is not None else 0.0
        pid = s.player.id if s.player is not None else None
        av = (s.value or 0.0) if pid is not None else None
        shown = None
        if pid is not None:
            shown = name(pid) + (" (new)" if pid in side.gets else " (locked)" if s.locked else "")
        change = (av or 0.0) - bv
        rows.append({"slot": slot_label(s.slot.label), "player_name": shown, "gsis_id": gsis(pid) if pid else None,
                     "trade_value": av, "trade_change": change if abs(change) >= 0.005 else None})
    why = {p: "traded" for p in side.gives} | {p: "cut" for p in cut}
    by_id = {s.player.id: s for s in side.lineup_before.starts if s.player is not None}
    after_id = {s.player.id: s for s in side.lineup_after.starts if s.player is not None}
    starts = [f"{name(p)} ({slot_label(after_id[p].slot.label)}, {after_id[p].value or 0.0:.2f}, "
              f"{'new' if p in side.gets else 'from the bench'})" for p in side.starts]
    sits = [f"{name(p)} ({slot_label(by_id[p].slot.label)}, {by_id[p].value or 0.0:.2f}, {why.get(p, 'to the bench')})"
            for p in side.sits]
    empty = [slot_label(s.slot.label) for s in side.lineup_after.starts if s.player is None]
    lines = []
    if starts:
        lines.append("Starts after the trade: " + ", ".join(starts) + ".")
    if sits:
        lines.append("Sits after the trade: " + ", ".join(sits) + ".")
    if empty:
        lines.append("Empty after the trade: " + ", ".join(empty) + " (nobody left who can play there this week).")
    return pd.DataFrame(rows), lines


def closest(side: T.Side) -> str:
    w = side.weakest_after
    if w is None:
        return "no starter is a decision this week"
    return f"{name(w.player.id)} at {slot_label(w.slot.label)}, {w.margin:.2f} ahead of the next option"


def size_words(side: T.Side, fa_meta: dict, who_: str, verb_s: str) -> list[str]:
    out = []
    for c in side.cuts:
        sv = f", {T.whole(c.market)} season points" if c.market is not None else ""
        out.append(f"{who_} must cut {link(c.player_id)} ({pos(c.player_id)}{sv}; costs {c.horizon_loss:.1f} over {span_words}) "
                   f"to stay at {side.limit} players")
    if side.opened:
        spot = "a spot" if side.opened == 1 else f"{side.opened} spots"
        if side.fill is not None:
            m = fa_meta.get(side.fill.player_id, {})
            fa = player_link(m.get("gsis_id"), m.get("player_name", side.fill.player_id))
            out.append(f"{who_} open{verb_s} {spot}: the best free agent for it is {fa} ({m.get('position', '')}, "
                       f"{side.fill.horizon_gain:+.1f} over {span_words})")
        else:
            out.append(f"{who_} open{verb_s} {spot}: no free agent would add to that lineup over {span_words}")
    return out


@st.cache_data(ttl=600, show_spinner=False)
def market_line(league: str, season_: int, gsis_ids: tuple[str, ...]) -> pd.DataFrame:
    """PPG, xPPG and position rank this season in this league's scoring (mart_league_player_season), age and NFL
    season (dim_player), per gsis id."""
    if not gsis_ids:
        return pd.DataFrame(columns=["gsis_id"])
    st_ = query("""select gsis_id, games_played, ppg, expected_per_game, position_rank_points
                   from analytics.mart_league_player_season where league_id = %s and season = %s and gsis_id = any(%s)""",
                (league, season_, list(gsis_ids)))
    bio = query("select gsis_id, birth_date, rookie_season from analytics.dim_player where gsis_id = any(%s)", (list(gsis_ids),))
    return pd.DataFrame({"gsis_id": list(gsis_ids)}).merge(st_, on="gsis_id", how="left").merge(bio, on="gsis_id", how="left")


def age_on(birth, today: date) -> int | None:
    if birth is None or pd.isna(birth):
        return None
    b = pd.Timestamp(birth).date()
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


ov_lineup = {"slot": Col("Slot"),
             "trade_value": Col("Value", "num2", f"His value to this lineup in week {this_week}: the projection in this league's scoring"),
             "trade_change": Col("Change", "signed1", "This slot after the trade minus before (blank: no change; the changes add up to "
                                                      "the lineup's change)")}

if not give or not get:
    st.info("Tick at least one player on each side to see what the trade does to both lineups.")
else:
    try:
        trade, fa_meta = simulate(league_id, season, roster_id, tuple(give), tuple(get), data_key, horizon, market, prices)
    except ValueError as exc:       # not expected: the widgets only offer players of the two rosters
        st.warning(f"This trade cannot be evaluated: {exc}")
        st.stop()
    me_s, th_s = trade.mine, trade.theirs
    them_name = team(partner)
    with st.container(border=True):
        st.markdown(f"**You give {names(give)}; you get {names(get)}.** {T.verdict(trade, span_words)}")
        st.markdown(T.fit_line(trade, span_words))
        st.markdown(T.fairness_line(trade))
        # league rank before / after (mart_league_roster_rankings, the two rosters' values replaced)
        rk = query("""select roster_id, measure, value from analytics.mart_league_roster_rankings
                      where league_id = %s and measure in ('lineup_value', 'horizon_value', 'bench_value')""", (league_id,))
        rank_bits = []
        for measure, after_me, after_th, when in (("lineup_value", me_s.after[0], th_s.after[0], f"week {this_week}"),
                                                   ("horizon_value", me_s.after_horizon, th_s.after_horizon, span_words),
                                                   ("bench_value", me_s.bench_after, th_s.bench_after, "depth")):
            vals = {int(r.roster_id): float(r.value) for r in rk[rk["measure"] == measure].itertuples()}
            if roster_id in vals and partner in vals and after_me is not None and after_th is not None:
                ch = T.rank_change(vals, {roster_id: after_me, partner: after_th})
                rank_bits.append(f"{when}: you {rank_words(ch[roster_id][0])} → **{rank_words(ch[roster_id][1])}** of {len(vals)}, "
                                 f"{them_name} {rank_words(ch[partner][0])} → {rank_words(ch[partner][1])}")
        if rank_bits:
            st.markdown("League rank, " + "; ".join(rank_bits) + ".")
        size = size_words(me_s, fa_meta, "you", "") + size_words(th_s, fa_meta, "they", "")
        st.markdown(("Roster size: " + "; ".join(size) + ".") if size
                    else f"Roster size: no change ({len(give)} for {len(get)}).")

    # the market line of every player in the package: next to the lineups, never added to them
    moving_ids = [*give, *get]
    ml = market_line(league_id, season, tuple(sorted({g for g in (gsis(x) for x in moving_ids) if g})))
    ml = ml.set_index("gsis_id") if not ml.empty else ml
    today = datetime.now(UTC).date()

    def ml_get(pid, col):
        g = gsis(pid)
        if g is None or ml.empty or g not in ml.index or col not in ml.columns:
            return None
        v = ml.at[g, col]
        return None if v is None or (not isinstance(v, str) and pd.isna(v)) else v

    moving = pd.DataFrame([{
        "player_name": f"{name(x)} ({pos(x)})", "gsis_id": gsis(x), "moving_to": them_name if x in give else "You",
        "market_price": whole_or_none(prices, x), "season_points": whole_or_none(market, x),
        "ppg_std": ml_get(x, "ppg"), "expected_per_game": ml_get(x, "expected_per_game"),
        "position_rank_points": ml_get(x, "position_rank_points"), "games_played": ml_get(x, "games_played"),
        "trade_age": age_on(ml_get(x, "birth_date"), today),
        "nfl_year": (season - int(ml_get(x, "rookie_season")) + 1) if ml_get(x, "rookie_season") is not None else None,
        "trade_value": week_value(x)[0]} for x in moving_ids])
    ov_market = {"moving_to": Col("Goes to"),
                 "market_price": Col("Market", "int", "Season points above the best free agent at his position (rest-of-season "
                                                       "projection in this league's scoring, minus the best free agent's): what the "
                                                       "fairness line adds up. Blank: no projection yet"),
                 "season_points": Col("Season pts", "int", "Rest-of-season projected points in this league's scoring (every "
                                                           "remaining week, injured or not)"),
                 "ppg_std": Col("PPG", "num1", "Points per game this season, this league's scoring: what his box scores show"),
                 "expected_per_game": Col("xPPG", "num1", "Expected points per game: what his targets and carries are usually worth"),
                 "position_rank_points": Col("Pos rank", "int", "Rank at his position by season points so far, this league's scoring"),
                 "games_played": Col("Games", "int"),
                 "trade_age": Col("Age", "int"), "nfl_year": Col("NFL yr", "int", "His NFL season: 1 = rookie"),
                 "trade_value": Col(f"Wk {this_week}", "num2", f"His projection in week {this_week} (blank: he can't play that week)")}
    show(moving, ["player_name", "moving_to", "market_price", "ppg_std", "expected_per_game"], overrides=ov_market,
         widths=fit({"player_name": 146, "moving_to": 64, "market_price": 52, "ppg_std": 46, "expected_per_game": 46}))

    c1, c2 = st.columns(2)
    for col, side, whose in ((c1, me_s, "Your lineup"), (c2, th_s, f"{them_name}'s lineup")):
        with col:
            st.markdown(f"**{whose}, week {this_week}: {side.before[0]:.2f} → {side.after[0]:.2f} ({side.gain_week:+.1f})**")
            st.caption(f"{span_words.capitalize()}: {side.before_horizon:.2f} → {side.after_horizon:.2f} ({side.gain_horizon:+.1f}). "
                       f"Depth (the bench's own lineup): {side.bench_before:.2f} → {side.bench_after:.2f}. "
                       f"Closest call after: {closest(side)}.")
            frame, notes = lineup_frame(side)
            show(frame, ["slot", "player_name", "trade_value", "trade_change"], overrides=ov_lineup,
                 widths=fit({"slot": 70, "player_name": 138, "trade_value": 62, "trade_change": 62}))
            for line in notes:
                st.caption(line)

    with st.expander("Market line: every number", expanded=False):
        show(moving, ["player_name", "moving_to", "market_price", "season_points", "ppg_std", "expected_per_game",
                      "position_rank_points", "games_played", "trade_age", "nfl_year", "trade_value"], overrides=ov_market)
        repl = ", ".join(f"{p} {T.whole(v)} ({repl_name.get(p, '')})" for p, v in sorted(replacement.items()))
        st.caption(f"The best free agent's season points by position, the bar the market column is measured above: {repl}."
                   if repl else "No free agent has a projection yet: the market column is the season points.")

    with st.expander(f"Week by week ({span_words})", expanded=False):
        wkly = pd.DataFrame({"week": list(trade.weeks), "you_before": list(me_s.before), "you_after": list(me_s.after),
                             "them_before": list(th_s.before), "them_after": list(th_s.after)})
        show(wkly, ["week", "you_before", "you_after", "them_before", "them_after"],
             widths=fit({"week": 44, "you_before": 68, "you_after": 68, "them_before": 68, "them_after": 68}),
             overrides={"you_before": Col("You now", "num2"), "you_after": Col("You after", "num2"),
                        "them_before": Col("Them now", "num2"), "them_after": Col("Them after", "num2")})
        st.caption("Each week is re-solved on its own: byes, injuries and taxi squads as in that week's lineup; a player whose "
                   "game has started stays with his team that week and moves the next.")

howto(
    "**Who to call**: the first card names the team where one trade raises *both* lineups the most over the next four weeks, "
    "and the trade. Teams are ranked by the smaller of the two gains, so the other manager has a reason to say yes too.",
    "**Try a trade**: pick the team, tick players both ways. You see both best lineups this week before and after (every slot "
    "re-picked, FLEX and superflex included), who starts and who sits, the four-week totals, the depth, and where both teams "
    "would rank in the league.",
    "**Fit** is what the starting lineups gain. **Market** is what the players are worth on the market: their projected points "
    "for the rest of the season above the best free agent at their position (a kicker anyone can pick up is worth about 0). "
    "They are not the same thing and are never added together: a player can be worth a lot and still sit on your bench. The "
    "verdict reads both. It is a rough guide: it knows nothing of draft picks, next season or what the other manager believes.",
    "**Roster size**: if a team gets more players than it gives, it has to cut someone: the player it would miss least, and that "
    "loss is in the numbers. If it gets fewer, it opens a spot, and the best free agent to fill it is named.",
    "Copy the page's link to share a trade: the link opens the same trade.",
    title="How to read this",
)

# ------------------------------------------------------------- buy low / sell high (B2), whole league, by position and owner
st.subheader("Buy low, sell high")
f1, f2 = st.columns([3, 2])
with f1:
    pos_f = st.segmented_control("Position", ["All", *POSITIONS], default="All", key="tf_position") or "All"
with f2:
    owner_opts = [None] + [r for r in sorted(labels, key=lambda r: labels[r]) if r != roster_id]
    owner = st.selectbox("Owner", owner_opts, format_func=lambda r: "Anyone" if r is None else labels[int(r)], key="tf_owner")


def keep(df: pd.DataFrame, owner_col: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df if pos_f == "All" else df[df["position"] == pos_f]
    if owner is not None:
        out = out[out[owner_col] == owner]
    return out


buy_f, sell_f = keep(buy, "owner"), keep(sell, "partner")
where = (f" at {pos_f}" if pos_f != "All" else "") + (f" on {labels[int(owner)]}" if owner is not None else "")

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
with st.expander(f"Buy low · {len(buy_f)} players scoring below their usage{where}", expanded=False):
    if not buy_f.empty:
        b = buy_f.copy()
        b["player"] = b["player_name"] + " (" + b["position"] + ")"
        b["manager"] = b["owner"].map(lambda r: labels.get(int(r), str(r)))
        show(b, base + (extra if detail_level() == "everything" else []), overrides=ov, height=min(80 + 35 * len(b), 600),
             pin=True, links={"player": ("gsis_id", "player_name")},
             phone_cols=["player", "gain_week", "fit_horizon", "manager"],   # inside an expander: four fit at 390 px
             widths=fit({"player": 118, "gain_week": 56, "fit_horizon": 56, "manager": 92})
             or {"player": 150, "gain_week": 72, "fit_horizon": 72, "diff_per_game": 72, "manager": "medium"})
    else:
        st.caption(f"Nobody on another team is scoring below his usage{where}.")

ov_s = {**ov, "manager": Col("Best fit", help=f"The roster whose lineup gains the most from him over {span_words}"),
        "gain_week": Col(f"They gain · {wk}", "signed1", f"What the best-fit roster's week-{this_week} lineup gains with him"),
        "gain_horizon": Col(f"They gain · {span}", "signed1", f"The same over {span_words}"),
        "loss_week": Col(f"You lose · {wk}", "num1", f"What your best week-{this_week} lineup loses without him (0 if he is on your bench)"),
        "loss_horizon": Col(f"You lose · {span}", "num1", f"The same over {span_words}"),
        "fit_week": Col(f"Fit · {wk}", "signed1", "They gain minus you lose, this week"),
        "fit_horizon": Col(f"Fit · {span}", "signed1", f"They gain minus you lose over {span_words}")}
with st.expander(f"Sell high · {len(sell_f)} of your players scoring above their usage{where}", expanded=False):
    if not sell_f.empty:
        s = sell_f.copy()
        s["player"] = s["player_name"] + " (" + s["position"] + ")"
        s["manager"] = s["partner"].map(lambda r: labels.get(int(r), str(r)) if pd.notna(r) else "")
        show(s, ["player", "loss_week", "fit_horizon", "manager", "diff_per_game"]
             + (["ppg_std", "expected_per_game", "gain_week", "gain_horizon", "loss_horizon", "fit_week"] if detail_level() == "everything" else []),
             overrides=ov_s, height=min(80 + 35 * len(s), 600), pin=True, links={"player": ("gsis_id", "player_name")},
             phone_cols=["player", "loss_week", "fit_horizon", "manager"],
             widths=fit({"player": 118, "loss_week": 56, "fit_horizon": 56, "manager": 92})
             or {"player": 150, "loss_week": 72, "fit_horizon": 72, "manager": "medium", "diff_per_game": 72})
    else:
        st.caption(f"None of your players is scoring above his usage{where}.")

howto(
    "**Buy low**: players on other teams scoring *less* than their work is worth (**PPG − xPPG**, points minus expected points "
    "per game, below zero). Their manager sees a bad box score; the work says it should turn around. **Sell high**: your "
    "players scoring *more* than their work supports. Filter by position and by owner to see the whole league.",
    f"**You gain** is how much your best lineup goes up with him (a WR who beats your FLEX counts; a QB who would sit on your bench adds nothing). "
    f"**They lose** is how much their lineup drops without him, 0 if he sits on their bench. Both are for this week ({wk}) and "
    f"the next four ({span}), in your league's scoring.",
    "**Fit** is what the new team gains minus what the old team loses. A big positive fit means he matters more to the other "
    "team than to his own: an easier ask when you buy, a better sale when you sell.",
    "These lists look at one player at a time. To see a whole offer, with what you send back and who gets cut, use \"Try a trade\" above.",
    title="How to read the buy-low and sell-high lists",
)
