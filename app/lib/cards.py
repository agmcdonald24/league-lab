"""Decision cards (plan B4): the week's lineup decisions, read from the exact lineup service (B1).

* ``decision_week(season)`` — the week the cards are about: the first regular-season week with a game
  still to kick off (so a Thursday game does not end the week's decisions; its players show as locked).
* ``lineup_rows(league_id, season, week, roster_id)`` — ONE query: the proposed starters and empty slots
  (``analytics.mart_lineup_recommendation``), the bench and the players who cannot play (``ops.lineups``,
  same run), each with his game's kickoff and his opponent's rank against his position
  (``analytics.dim_game``, ``analytics.mart_defense_vs_position_current``). Cached like every query.
* ``decisions(rows)`` — pure: the smallest-margin unlocked, valued starters (B1's weakest-slot order:
  margin, then value, then slot order) with the named alternative (``alternative``).
* ``decision_cards(...)`` / ``lineup_table(...)`` — the Streamlit rendering, shared by Home (My Week), the
  Matchups page and the player card.

The alternative is the bench player the lineup re-solve brings in when the starter sits. B1's margin is
exactly that re-solve, and removing one starter changes the best lineup along one alternating path
(teammates may slide between slots), so exactly one bench player enters — the one whose value is the
starter's value minus the margin. Almost always that is the best bench player eligible for the slot
("Start Gainwell over Wilson, 0.45"); when it is not, a teammate slid over and the card says who.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .db import missing_relations, query
from .ui import player_link

# Slot -> positions that may fill it. A copy of league_lab.lineup.SLOT_ELIGIBILITY: the hosted app does
# not install scipy, so it cannot import the solver module; tests/test_cards.py keeps the two equal.
SLOT_ELIGIBILITY: dict[str, frozenset[str]] = {
    "QB": frozenset({"QB"}),
    "RB": frozenset({"RB"}),
    "WR": frozenset({"WR"}),
    "TE": frozenset({"TE"}),
    "K": frozenset({"K"}),
    "DEF": frozenset({"DEF"}),
    "FLEX": frozenset({"RB", "WR", "TE"}),
    "SUPER_FLEX": frozenset({"QB", "RB", "WR", "TE"}),
    "REC_FLEX": frozenset({"WR", "TE"}),
    "WRRB_FLEX": frozenset({"RB", "WR"}),
}
# values and margins are stored to the cent (lineup._r2); a K's season PPG is solved unrounded, so the
# starter value minus the margin can miss the alternative's stored value by one cent
TOL = 0.011
# words on a card for how close a call is (points of projected difference)
COIN_FLIP, LEAN = 1.0, 3.0

SLOT_WORDS = {"SUPER_FLEX": "Superflex", "REC_FLEX": "WR/TE flex", "WRRB_FLEX": "RB/WR flex"}


def slot_label(slot: str | None) -> str:
    """RB2, FLEX, Superflex, FLEX2 ... as a manager reads them."""
    if not slot:
        return ""
    for key, word in SLOT_WORDS.items():
        if slot.startswith(key):
            return word + slot[len(key):]
    return slot


def verdict(margin: float) -> str:
    if margin < COIN_FLIP:
        return "a coin flip"
    if margin < LEAN:
        return "a lean"
    return "clear"


# ------------------------------------------------------------------------------ data
def decision_week(season: int) -> int | None:
    """The first regular-season week of `season` whose last game has not kicked off yet (None after it)."""
    df = query(
        """select week from analytics.dim_game
           where season = %s and season_type = 'REG'
           group by week having max(kickoff_at) > now() order by week limit 1""",
        (int(season),),
    )
    return None if df.empty else int(df["week"].iloc[0])


LINEUP_SQL = """
with lr as (
    select 'starter' as role, r.slot, r.slot_type, r.slot_order, null::integer as bench_rank,
           r.gsis_id, r.sleeper_player_id, r.player_name, r.position, r.player_value as value, r.value_source,
           r.lineup_margin as margin, r.is_locked, r.is_empty_slot, r.report_status, null::text as reason,
           r.is_weakest_slot, r.lineup_value, r.bench_value, r.weakest_slot, r.weakest_margin, r.n_unvalued, r.as_of
    from analytics.mart_lineup_recommendation r
    where r.league_id = %s and r.season = %s and r.week = %s and r.roster_id = %s
    union all
    select l.role, null, null, null, l.bench_rank,
           l.gsis_id, l.sleeper_player_id, coalesce(p.player_name, l.player_name), l.position, l.value, l.value_source,
           l.margin, l.is_locked, false, l.report_status, l.reason,
           false, null, null, null, null, null, null
    from ops.lineups l
    left join analytics.dim_player p on p.gsis_id = l.gsis_id
    where l.league_id = %s and l.season = %s and l.week = %s and l.roster_id = %s
      and not l.is_realised and l.role in ('bench', 'unplayable')
),
tm as (
    select lr.*,
           coalesce(pr.team, dp.latest_team,
                    case when lr.position = 'DEF' then case lr.sleeper_player_id when 'LAR' then 'LA' else lr.sleeper_player_id end end) as team
    from lr
    left join analytics.mart_player_week_projections pr
           on pr.league_id = %s and pr.season = %s and pr.week = %s and pr.gsis_id = lr.gsis_id
    left join analytics.dim_player dp on dp.gsis_id = lr.gsis_id
)
select tm.*, g.kickoff_at, coalesce(g.kickoff_at <= now(), false) as kicked_off, g.opponent, d.rank_std as opp_rank
from tm
left join lateral (
    select g.kickoff_at, case when g.home_team = tm.team then g.away_team else g.home_team end as opponent
    from analytics.dim_game g
    where g.season = %s and g.week = %s and g.season_type = 'REG' and tm.team in (g.home_team, g.away_team)
    order by g.kickoff_at limit 1
) g on true
left join analytics.mart_defense_vs_position_current d on d.defense = g.opponent and d.position = tm.position
order by case tm.role when 'starter' then 0 when 'bench' then 1 else 2 end, tm.slot_order, tm.bench_rank, tm.value desc nulls last
"""


def lineup_rows(league_id: str, season: int, week: int, roster_id: int) -> pd.DataFrame:
    """Every player of one roster-week of the proposed lineup: role starter (incl. empty slots) / bench /
    unplayable, value, margin, lock, injury, kickoff, opponent and its rank vs his position. One query."""
    s, w, r = int(season), int(week), int(roster_id)
    df = query(LINEUP_SQL, (league_id, s, w, r, league_id, s, w, r, league_id, s, w, s, w))
    if not df.empty:
        for c in ("is_locked", "is_empty_slot", "kicked_off", "is_weakest_slot"):
            df[c] = df[c].fillna(False).astype(bool)
        # locked = B1 locked him when the lineup was solved, or his game has kicked off since
        df["locked_now"] = df["is_locked"] | df["kicked_off"]
    return df


# ------------------------------------------------------------------------------ pure logic
def _eligible(position: str | None, slot_type: str | None) -> bool:
    return bool(position) and position in SLOT_ELIGIBILITY.get(slot_type or "", frozenset())


def alternative(starter: pd.Series, rows: pd.DataFrame) -> dict:
    """Who replaces `starter` in the best lineup if he sits, and how that was found.

    Returns {"alt": row or None, "mover": row or None, "how": text}. The bench player who enters has
    value = starter value - margin (B1's margin is the re-solve). First choice: the best bench player
    eligible for the slot, if his value is that one (no reshuffle). Otherwise the bench player with that
    value enters after a teammate slides into this slot (`mover`); none means nobody can fill it."""
    bench = rows[(rows["role"] == "bench") & ~rows["locked_now"]].copy()
    target = float(starter["value"]) - float(starter["margin"])
    elig = bench[bench["position"].map(lambda p: _eligible(p, starter["slot_type"])).astype(bool)]
    elig = elig.sort_values(["value", "bench_rank"], ascending=[False, True])
    best = elig.iloc[0] if not elig.empty else None
    if best is not None and abs(float(best["value"]) - target) <= TOL:
        return {"alt": best, "mover": None,
                "how": f"best bench player who can play {slot_label(starter['slot'])}"}
    if abs(target) <= TOL:
        # margin = his whole value: the re-solve leaves the slot empty (or seats a player worth 0 after a
        # reshuffle, which the margin cannot tell apart) - nobody on the bench replaces him
        return {"alt": None, "mover": None, "how": f"nobody on the bench can play {slot_label(starter['slot'])}"}
    entering = bench[(bench["value"].astype(float) - target).abs() <= TOL]
    if not entering.empty:
        entering = entering.assign(_e=entering["position"].map(lambda p: _eligible(p, starter["slot_type"])).astype(bool))
        e = entering.sort_values(["_e", "bench_rank"], ascending=[False, True]).iloc[0]
        others = rows[(rows["role"] == "starter") & ~rows["is_empty_slot"] & ~rows["locked_now"]
                      & (rows["slot"] != starter["slot"])]
        movers = others[others["position"].map(lambda p: _eligible(p, starter["slot_type"])).astype(bool)
                        & others["slot_type"].map(lambda t: _eligible(e["position"], t)).astype(bool)]
        mover = movers.sort_values("slot_order").iloc[0] if not movers.empty else None
        how = ("comes in after a teammate slides over: " + (f"{mover['player_name']} moves to {slot_label(starter['slot'])}, "
               f"{e['player_name']} takes {slot_label(mover['slot'])}" if mover is not None else "the lineup reshuffles"))
        return {"alt": e, "mover": mover, "how": how}
    # not expected (the margin is the re-solve); name the slot's best bench player and say it is approximate
    return {"alt": best, "mover": None, "how": "best bench player for the slot (the lineup would shuffle more than one player)"}


def decisions(rows: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """The n unlocked, valued starters with the smallest margins (B1's weakest-slot order: margin, value,
    slot order) that someone on the bench could replace, with that alternative; one row each: slot,
    starter, value, margin, verdict, alt_*, mover_*, how, flags. A starter nobody can replace (the only
    DEF, the only K) is not a decision and is skipped."""
    if rows is None or rows.empty:
        return pd.DataFrame()
    st_ = rows[(rows["role"] == "starter") & ~rows["is_empty_slot"] & rows["margin"].notna() & ~rows["locked_now"]
               & (rows["value_source"] != "unvalued")]
    # margins are stored to the cent, so two can tie here that B1 told apart: its weakest slot goes first
    st_ = st_.assign(_w=~st_["is_weakest_slot"].astype(bool)).sort_values(["margin", "_w", "value", "slot_order"])
    out = []
    for _, s in st_.iterrows():
        if len(out) >= n:
            break
        a = alternative(s, rows)
        alt, mover = a["alt"], a["mover"]
        if alt is None:
            continue
        out.append({
            "slot": s["slot"], "slot_type": s["slot_type"], "sleeper_player_id": s.get("sleeper_player_id"),
            "gsis_id": s["gsis_id"], "player_name": s["player_name"],
            "position": s["position"], "value": float(s["value"]), "value_source": s["value_source"],
            "margin": float(s["margin"]),
            "verdict": verdict(float(s["margin"])), "report_status": s["report_status"],
            "opponent": s["opponent"], "opp_rank": s["opp_rank"],
            "alt_sleeper_player_id": alt.get("sleeper_player_id") if alt is not None else None,
            "alt_gsis_id": alt["gsis_id"] if alt is not None else None,
            "alt_name": alt["player_name"] if alt is not None else None,
            "alt_position": alt["position"] if alt is not None else None,
            "alt_value": float(alt["value"]) if alt is not None else None,
            "alt_value_source": alt["value_source"] if alt is not None else None,
            "alt_report_status": alt["report_status"] if alt is not None else None,
            "alt_opponent": alt["opponent"] if alt is not None else None,
            "alt_opp_rank": alt["opp_rank"] if alt is not None else None,
            "mover_name": mover["player_name"] if mover is not None else None,
            "mover_slot": mover["slot"] if mover is not None else None,
            "how": a["how"],
        })
    return pd.DataFrame(out)


def bench_gap(player: pd.Series, rows: pd.DataFrame) -> pd.Series | None:
    """For a bench player: the lowest-valued unlocked starter in a slot he can play (who he would have to
    beat for a direct swap). None when no such starter exists."""
    cand = rows[(rows["role"] == "starter") & ~rows["is_empty_slot"] & ~rows["locked_now"]
                & rows["slot_type"].map(lambda t: _eligible(player["position"], t)).astype(bool)]
    return None if cand.empty else cand.sort_values(["value", "slot_order"]).iloc[0]


# ------------------------------------------------------------------------------ rendering
def _matchup(name: str, opp, rank, position) -> str:
    if opp is None or (isinstance(opp, float) and pd.isna(opp)):
        return ""
    r = f" (#{int(rank)} vs {position})" if rank is not None and pd.notna(rank) else ""
    return f"{name} vs {opp}{r}"


def _flag(status) -> str:
    return f"{status}" if isinstance(status, str) and status and status != "Healthy" else ""


def render_decision(d: pd.Series | dict) -> None:
    """One decision as a bordered card: the call, the numbers, the matchups, any injury flag."""
    d = pd.Series(d)
    slot = slot_label(d["slot"])
    me = player_link(d["gsis_id"], d["player_name"])
    with st.container(border=True):
        if d["alt_name"] is None or (isinstance(d["alt_name"], float) and pd.isna(d["alt_name"])):
            st.markdown(f"**{slot}: start {me}** — {d['how']}.")
            return
        alt = player_link(d["alt_gsis_id"], d["alt_name"])
        st.markdown(f"**{slot}: start {me} over {alt}**")
        basis = ("projected" if d.get("value_source") == "proj_points" and d.get("alt_value_source") == "proj_points"
                 else "points per game this season" if {d.get("value_source"), d.get("alt_value_source")} <= {"season_ppg", "observed_ppg"}
                 else "for the lineup")
        st.markdown(f"{d['value']:.2f} vs {d['alt_value']:.2f} {basis} — **{d['margin']:.2f} apart, {d['verdict']}**.")
        extra = []
        if d.get("mover_name") and isinstance(d["mover_name"], str):
            extra.append(f"{d['alt_name']} would come in at {slot_label(d['mover_slot'])} and {d['mover_name']} would move to {slot}.")
        m = " · ".join(x for x in (_matchup(d["player_name"], d["opponent"], d["opp_rank"], d["position"]),
                                   _matchup(d["alt_name"], d["alt_opponent"], d["alt_opp_rank"], d["alt_position"])) if x)
        if m:
            extra.append(m)
        for who, s in ((d["player_name"], d["report_status"]), (d["alt_name"], d["alt_report_status"])):
            if _flag(s):
                extra.append(f"⚠️ {who} is {s}.")
        if extra:
            st.caption("  \n".join(extra))


def league_season(league_id: str) -> int | None:
    df = query("select season from analytics.dim_league_season where league_id = %s", (league_id,))
    return None if df.empty else int(df["season"].iloc[0])


def decision_cards(league_id: str, roster_id: int, week: int, season: int | None = None, n: int = 3,
                   rows: pd.DataFrame | None = None) -> pd.DataFrame:
    """Render the week's closest lineup calls for one roster as cards; returns the decisions frame."""
    if rows is None:
        season = season if season is not None else league_season(league_id)
        rows = lineup_rows(league_id, season, week, roster_id)
    if rows.empty:
        st.info(f"Lineup decisions unavailable: no proposed lineup for week {week} yet (the nightly refresh writes it).")
        return pd.DataFrame()
    dec = decisions(rows, n)
    if dec.empty:
        locked = int(rows.loc[rows["role"] == "starter", "locked_now"].sum())
        bench = int(((rows["role"] == "bench") & ~rows["locked_now"]).sum())
        st.info("No lineup calls this week: " + ("nobody on your bench can play (byes, injuries)." if bench == 0
                else f"{locked} starters are locked and nobody on the bench can replace the rest." if locked
                else "nobody on the bench can replace a starter."))
        return dec
    for _, d in dec.iterrows():
        render_decision(d)
    return dec


def lineup_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """The proposed lineup as displayed: slot, player, value, one flag (starters and empty slots only)."""
    lu = rows[rows["role"] == "starter"].copy()

    def flag(r) -> str:
        if r["is_empty_slot"]:
            return "EMPTY: nobody can play"
        if r["locked_now"]:
            return "locked (game started)"
        if _flag(r["report_status"]):
            return str(r["report_status"])
        if r["value_source"] == "unvalued":
            return "no value yet"
        return ""

    lu["flag"] = lu.apply(flag, axis=1) if not lu.empty else []
    lu["slot"] = lu["slot"].map(slot_label)
    return lu


def lineup_table(rows: pd.DataFrame, full: bool = False) -> None:
    """Render the proposed lineup: four columns (slot, player, value, flag); `full` adds the margin and
    lists the bench and the players who cannot play (for an expander)."""
    from .table import C, show

    if rows is None or rows.empty:
        st.caption("No proposed lineup for this week yet.")
        return
    ov = {"slot": C("Slot"),
          "player_value": C("Proj", "num2", "His value to the lineup this week: the projection in this league's scoring "
                                            "(a kicker or defense: points per game this season)"),
          "flag": C("Flag", help="Injury tag, locked (his game has started), or an empty slot"),
          "lineup_margin": C("Margin", "num2", "What the lineup loses without him (re-solved); small = a close call")}
    lu = lineup_frame(rows).rename(columns={"value": "player_value", "margin": "lineup_margin"})
    if not full:
        show(lu, ["slot", "player_name", "player_value", "flag"], overrides=ov)
        return
    rest = rows[rows["role"] != "starter"].copy()
    rest["slot"] = rest.apply(lambda r: f"Bench {int(r['bench_rank'])}" if r["role"] == "bench" and pd.notna(r["bench_rank"])
                              else "Can't play", axis=1)
    rest["flag"] = rest.apply(lambda r: r["reason"] if r["role"] == "unplayable" else ("locked (game started)" if r["locked_now"]
                              else _flag(r["report_status"])), axis=1)
    rest = rest.rename(columns={"value": "player_value", "margin": "lineup_margin"})
    both = pd.concat([lu, rest], ignore_index=True)
    show(both, ["slot", "player_name", "player_value", "lineup_margin", "flag"], overrides=ov)


def league_line(league_id: str, roster_id: int, week: int, rows: pd.DataFrame) -> str:
    """One line on the whole-league picture: the lineup value and, when B2's
    `analytics.mart_league_roster_rankings` is on this database, its league rank (horizon named)."""
    total = rows.loc[rows["role"] == "starter", "lineup_value"].dropna()
    if total.empty:
        return ""
    line = f"Your best lineup projects **{float(total.iloc[0]):.2f}** in week {week}"
    if not missing_relations(("mart_league_roster_rankings",)):
        rk = query("select * from analytics.mart_league_roster_rankings where league_id = %s and roster_id = %s",
                   (league_id, int(roster_id)))
        line += rank_phrase(rk, week)
    return line + "."


def rank_phrase(rk: pd.DataFrame, week: int | None = None) -> str:
    """', 3rd of 12 in the league (week 4)' from B2's rankings rows (measure = lineup_value, same week when
    the rows carry one), '' when absent or about another week."""
    need = {"measure", "league_rank", "n_rosters"}
    if rk is None or rk.empty or not need <= set(rk.columns):
        return ""
    r = rk[rk["measure"] == "lineup_value"]
    if week is not None and "week" in r.columns:
        r = r[pd.to_numeric(r["week"], errors="coerce") == int(week)]
    if r.empty or pd.isna(r["league_rank"].iloc[0]):
        return ""
    n, k = int(r["n_rosters"].iloc[0]), int(r["league_rank"].iloc[0])
    suffix = "th" if 10 <= k % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(k % 10, "th")
    hz = r["horizon"].iloc[0] if "horizon" in r.columns and pd.notna(r["horizon"].iloc[0]) else None
    same = week is not None and hz == f"week {int(week)}"      # the line already names the week
    return f", {k}{suffix} of {n} in the league" + (f" ({hz})" if hz and not same else "")


def howto_cards() -> None:
    with st.expander("How to read this"):
        st.markdown(
            "- The lineup is the best legal one your roster can start this week, every slot solved together "
            "(FLEX and superflex included), on this week's projections in your league's scoring.\n"
            "- A card is one of the week's closest calls: the starter whose absence would cost the least. "
            "**Apart** is how much the lineup loses if you swap him for the named player: under "
            f"{COIN_FLIP:.0f} point is a coin flip (go with the news), under {LEAN:.0f} a lean, more is clear.\n"
            "- The named player is the one who would actually come in: the best bench player who can play "
            "that slot, or, when moving a teammate over works better, the card says who moves.\n"
            "- **#28 vs WR** is the opponent's rank in points allowed to that position this season "
            "(1 = gives up the most, the matchup you want).\n"
            "- Players whose game has started are locked, and a starter nobody on your bench can replace (your only "
            "kicker or defense) is not a call: neither gets a card."
        )
