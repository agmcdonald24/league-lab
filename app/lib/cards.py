"""Decision cards (plan B4): the week's lineup decisions, read from the exact lineup service (B1).

* ``decision_week(season)`` — the week the cards are about: ``lib.ui.current_week`` (C1, U-13: one week rule for
  every page), the first regular-season week whose last game has not kicked off (so a Thursday game does not end
  the week's decisions; its players show as locked).
* ``lineup_rows(league_id, season, week, roster_id)`` — ONE query: the proposed starters and empty slots
  (``analytics.mart_lineup_recommendation``), the bench and the players who cannot play (``ops.lineups``,
  same run), each with his game's kickoff and his opponent's rank against his position
  (``analytics.dim_game``, ``analytics.mart_defense_vs_position_current``). Cached like every query.
* ``decisions(rows)`` — pure: the smallest-margin unlocked, valued starters (B1's weakest-slot order:
  margin, then value, then slot order) with the named alternative (``alternative``) and (plan D6) how often the
  starter outscores him (``win_probability``: ``league_lab.decisions`` on both players' calibrated ranges).
* ``decision_cards(...)`` / ``lineup_table(...)`` — the Streamlit rendering, shared by Home (My Week), the
  Matchups page and the player card. Plan D6: a card leads with "A outscores B 54% of the time — a coin flip"
  (50-55% a coin flip, 55-65% a lean, 65%+ clear), the margin second, then both players' 50% range ("most
  weeks") and 80% range; without a probability (K, DEF, a points-per-game value) the margin's words stay.

The alternative is the bench player the lineup re-solve brings in when the starter sits. B1's margin is
exactly that re-solve, and removing one starter changes the best lineup along one alternating path
(teammates may slide between slots), so exactly one bench player enters — the one whose value is the
starter's value minus the margin. Almost always that is the best bench player eligible for the slot
("Start Gainwell over Wilson, 0.45"); when it is not, a teammate slid over and the card says who.
"""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from league_lab import decisions as D

from .db import missing_relations, query
from .ui import current_week, player_link

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
# ---- IC-2 (Wave I-C): the league's own slot names (MyFantasyLeague): combined slots "WR+TE1" and the team units
UNIT_SLOT_WORDS = {"TMQB": "team QB", "TMPK": "team K", "TMDEF": "team DEF"}
_COMBINED = re.compile(r"^([A-Z]+(?:\+[A-Z]+)+)(\d*)$")
_UNIT = re.compile(r"^(TMQB|TMPK|TMDEF)(\d*)$")
# positions a combined slot's parts admit (lineup.POSITION_ALIASES' offense / kicking / defense part)
_PART = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "PK": "K", "DEF": "DEF", "TMDEF": "DEF",
         "TMQB": "TMQB", "TMPK": "TMPK"}


def slot_elig(slot_type: str | None) -> frozenset[str]:
    """lineup.slot_eligibility for the slot types a lineup row carries (this module cannot import the solver):
    Sleeper's names, ``A+B[+C]`` (the union of the parts), the units ``TMQB`` / ``TMPK`` / ``TMDEF`` (= DEF);
    tests/test_lineup_ic2.py keeps the two equal."""
    t = str(slot_type or "").upper()
    if t in SLOT_ELIGIBILITY:
        return SLOT_ELIGIBILITY[t]
    if t in _PART:
        return frozenset({_PART[t]})
    if "+" in t:
        parts = [_PART.get(x) for x in t.split("+")]
        return frozenset(parts) if parts and all(parts) else frozenset()
    return frozenset()
# ---- end IC-2


def slot_label(slot: str | None) -> str:
    """RB2, FLEX, Superflex, FLEX2 ... as a manager reads them; IC-2: "WR+TE1" -> "WR/TE 1", "TMQB" -> "team QB"."""
    if not slot:
        return ""
    for key, word in SLOT_WORDS.items():
        if slot.startswith(key):
            return word + slot[len(key):]
    # ---- IC-2
    m = _UNIT.match(slot)
    if m:
        return UNIT_SLOT_WORDS[m.group(1)] + (f" {m.group(2)}" if m.group(2) else "")
    m = _COMBINED.match(slot)
    if m:
        words = "/".join({"PK": "K"}.get(x, x) for x in m.group(1).split("+"))
        return words + (f" {m.group(2)}" if m.group(2) else "")
    # ---- end IC-2
    return slot


def verdict(margin: float) -> str:
    if margin < COIN_FLIP:
        return "a coin flip"
    if margin < LEAN:
        return "a lean"
    return "clear"


QUANTILE_COLS = ("p10", "p25", "p50", "p75", "p90")
SKILL = frozenset({"QB", "RB", "WR", "TE"})


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def win_probability(me: pd.Series, alt: pd.Series) -> float | None:
    """Plan D6: how often the starter outscores the named alternative this week, from both calibrated ranges
    (``league_lab.decisions``; teammates / opponents correlated). Only for two QB-TE projections (the
    calibrated case); None otherwise (a K or DEF, a value from points per game, a row without a range)."""
    if me.get("value_source") != "proj_points" or alt.get("value_source") != "proj_points":
        return None
    if me.get("position") not in SKILL or alt.get("position") not in SKILL:
        return None
    rows = [{**{q: _num(r.get(q)) for q in QUANTILE_COLS}, "team": r.get("team"), "opponent": r.get("opponent"),
             "position": r.get("position")} for r in (me, alt)]
    return D.win_probability(rows[0], rows[1])


def range_text(r, prefix: str = "") -> tuple[str | None, str | None]:
    """('6–14', '3–19'): the 50% range ("most weeks") and the 80% range (a bad week to a good week), whole points;
    None where the row has no such range (p25 / p75 are NULL on weeks frozen before they existed)."""
    lo50, hi50, lo80, hi80 = (_num(r.get(prefix + k)) for k in ("p25", "p75", "p10", "p90"))
    mid = f"{lo50:.0f}–{hi50:.0f}" if lo50 is not None and hi50 is not None else None
    wide = f"{lo80:.0f}–{hi80:.0f}" if lo80 is not None and hi80 is not None else None
    return mid, wide


# ------------------------------------------------------------------------------ data
def decision_week(season: int) -> int | None:
    """The first regular-season week of `season` whose last game has not kicked off yet (None after it):
    ``lib.ui.current_week``, the rule every page uses."""
    return current_week(season=int(season))


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
                    case when lr.position = 'DEF' then case lr.sleeper_player_id when 'LAR' then 'LA' else lr.sleeper_player_id end end) as team,
           -- plan D6: his calibrated range this week (p25 / p75 NULL on weeks frozen before they existed)
           pr.p10, pr.p25, pr.p50, pr.p75, pr.p90
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
    return bool(position) and position in slot_elig(slot_type)          # IC-2: combined slots and units too


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
        pw = win_probability(s, alt)
        out.append({
            "p_win": pw, "win_words": D.words(pw) if pw is not None else None,
            **{q: _num(s.get(q)) for q in QUANTILE_COLS}, **{f"alt_{q}": _num(alt.get(q)) for q in QUANTILE_COLS},
            "slot": s["slot"], "slot_type": s["slot_type"], "sleeper_player_id": s.get("sleeper_player_id"),
            "gsis_id": s["gsis_id"], "player_name": s["player_name"],
            "team": s.get("team"), "alt_team": alt.get("team"),            # IA-1: the reason line's team words
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
        # ---- IB-0 (Wave I-B): the call's strength, and (when the rows say who Sleeper starts now) its status
        d = out[-1]
        d["strength"] = strength(d)
        if SLEEPER_STARTER in rows:
            d["sleeper_starter"], d["alt_sleeper_starter"] = bool(s.get(SLEEPER_STARTER)), bool(alt.get(SLEEPER_STARTER))
        d["status"] = call_status(d) if SLEEPER_STARTER in rows else ("close" if is_coin_flip(d) else None)
        # ---- end IB-0
    return pd.DataFrame(out)


# ---- IB-0 (Wave I-B, the second review's #3): a call that needs a change vs one that is already set. ``status``:
# "close" = a coin flip (``is_coin_flip``: either is fine), "set" = Sleeper already starts the recommended player and
# not the other one, "change" = it does not (he sits in Sleeper, or the other one starts). Who Sleeper starts now is
# the rows' ``SLEEPER_STARTER`` column (the API: Sleeper's roster ``starters``; a page may fill it from
# ``mart_player_availability.is_current_starter``); without it the status is only known for a coin flip.
# ``strength``: "clear" (3+ points apart, or he outscores the other player 70% of the time or more), "lean", "coin flip".
SLEEPER_STARTER = "sleeper_starter"
CLEAR_PWIN = 0.7


def strength(d) -> str:
    if is_coin_flip(d):
        return "coin flip"
    pw = _num(d.get("p_win"))
    margin = _num(d.get("margin")) or 0.0
    return "clear" if margin >= LEAN or (pw is not None and pw >= CLEAR_PWIN) else "lean"


def call_status(d) -> str:
    if is_coin_flip(d):
        return "close"
    return "set" if d.get("sleeper_starter") and not d.get("alt_sleeper_starter") else "change"
# ---- end IB-0


def bench_gap(player: pd.Series, rows: pd.DataFrame) -> pd.Series | None:
    """For a bench player: the lowest-valued unlocked starter in a slot he can play (who he would have to
    beat for a direct swap). None when no such starter exists."""
    cand = rows[(rows["role"] == "starter") & ~rows["is_empty_slot"] & ~rows["locked_now"]
                & rows["slot_type"].map(lambda t: _eligible(player["position"], t)).astype(bool)]
    return None if cand.empty else cand.sort_values(["value", "slot_order"]).iloc[0]


# ------------------------------------------------------------------------------ the reason (Wave I-A, IA-1)
# Andrew (2026-10-02): "I don't know if that's helpful week to week ... reasons why". Each card gets ONE plain sentence
# saying why, from data the card already has (the opponent and its rank against the position, the injury tag) plus one
# cheap read per card set (REASON_SQL: the week's betting line and his share of the team's work, game by game). The
# pieces are scored (+ = good for him this week); the sentence names the strongest piece for the starter and the
# strongest piece against the other player. A coin flip says so and names the tiebreaker instead.
REASON_SQL = """
select x.gsis_id, f.is_home, f.implied_team_total, f.practice_status, f.target_share_std, f.carry_share_std,
       g.target_shares, g.carry_shares
from unnest(%s::text[]) as x(gsis_id)
left join analytics.mart_player_week_features f on f.gsis_id = x.gsis_id and f.season = %s and f.week = %s
left join lateral (
    select array_agg(p.target_share::float order by p.week) as target_shares,
           array_agg(p.carry_share::float order by p.week) as carry_shares
    from analytics.fct_player_game p
    where p.gsis_id = x.gsis_id and p.season = %s and p.season_type = 'REG' and p.week < %s and p.played
) g on true
"""
TEAM_NICK_SQL = "select team_abbr, team_nick from analytics.dim_team"
POS_PLURAL = {"QB": "quarterbacks", "RB": "running backs", "WR": "receivers", "TE": "tight ends", "K": "kickers",
              "DEF": "defenses"}
PRACTICE_WORDS = {"Did Not Participate In Practice": "did not practice", "Limited Participation in Practice": "limited in practice"}
SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"})
STRONG = 0.4          # a piece this strong (of 1) is worth a sentence
CLOSE_PWIN = 0.55     # under this (or a margin under COIN_FLIP without a percentage) the card is a coin flip


def _ordinal(k: int) -> str:
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


def last_name(name: str | None, position: str | None = None) -> str:
    """'Jacory Croskey-Merritt' -> 'Croskey-Merritt', 'Michael Penix Jr.' -> 'Penix', 'Amon-Ra St. Brown' -> 'St. Brown';
    a defense keeps its name."""
    if not isinstance(name, str) or not name.strip():
        return ""
    parts = name.split()
    if position == "DEF" or len(parts) < 2:
        return name
    while len(parts) > 2 and parts[-1].lower() in SUFFIXES:
        parts = parts[:-1]
    return " ".join(parts[1:])


def _nick(team, nicks: dict) -> str:
    if not isinstance(team, str) or not team:
        return ""
    return f"the {nicks[team]}" if team in nicks else team


def _shares(f: dict, position: str | None) -> tuple[str, list[float]]:
    """('carries' | 'targets', his share of the team's carries / targets game by game, this season before this week)."""
    key, word = ("carry_shares", "carries") if position == "RB" else ("target_shares", "targets")
    vals = [float(v) for v in (f.get(key) or []) if v is not None and not pd.isna(v)]
    return word, vals


def reason_pieces(d: dict, side: str, f: dict, nicks: dict) -> list[tuple[float, str, str]]:
    """The reasons for one side of a card ('' = the starter, 'alt_' = the other player): (score, kind, clause), score in
    [-1, 1] (+ = good for him this week). `d` is a decisions() row, `f` his REASON_SQL row (may be empty)."""
    name = last_name(d.get(side + "player_name") if side else d.get("player_name"), d.get(side + "position"))
    name = d.get("_short_" + (side or "me"), name)
    pos = d.get(side + "position")
    out: list[tuple[float, str, str]] = []
    status = d.get(side + "report_status")
    practice = PRACTICE_WORDS.get(f.get("practice_status") or "")
    if _flag(status):
        out.append((-1.0, "injury", f"{name} is {str(status).lower()}" + (f" ({practice})" if practice else "")))
    elif practice:
        out.append((-0.5, "injury", f"{name} {practice} this week"))
    opp, rank = d.get(side + "opponent"), _num(d.get(side + "opp_rank"))
    home = f.get("is_home")
    home = None if home is None or (isinstance(home, float) and pd.isna(home)) else bool(home)
    where = "at home against" if home is True else "on the road against" if home is False else "against"
    n_before = len(out)                                                      # ---- IF-3
    if isinstance(opp, str) and opp and rank is not None:
        r = int(rank)
        plural = POS_PLURAL.get(pos or "", "his position")
        if r <= 10:
            most = "the most" if r == 1 else f"the {_ordinal(r)}-most"
            out.append(((16.5 - r) / 15.5, "matchup", f"{name} is {where} {_nick(opp, nicks)}, who give up {most} points to {plural}"))
        elif r >= 23:
            k = 33 - r
            fewest = "the fewest" if k == 1 else f"the {_ordinal(k)}-fewest"
            out.append(((16.5 - r) / 15.5, "matchup", f"{name} is {where} {_nick(opp, nicks)}, who give up {fewest} points to {plural}"))
    # ---- IF-3: the defense's regular corners changed: the rank stays a fact on the card but is never a reason (score 0,
    # its own kind: `_tiebreak` never picks it, `reason_line` never leads with it)
    if f.get("personnel_caveat") and len(out) > n_before and out[-1][1] == "matchup":
        out[-1] = (0.0, "matchup_caveat", f"{out[-1][2]}, but {f['personnel_caveat']}")
    # ---- end IF-3
    implied = _num(f.get("implied_team_total"))
    team = _nick(d.get(side + "team"), nicks)
    if implied is not None and team and pos in SKILL:
        whose = team.replace("the ", f"{name}'s ", 1) if team.startswith("the ") else f"{name}'s {team}"
        if implied >= 26:
            out.append((0.45, "line", f"Vegas expects {whose} to score {implied:.0f}"))
        elif implied <= 18:
            out.append((-0.45, "line", f"Vegas expects {whose} to score only {implied:.0f}"))
    if pos in ("RB", "WR", "TE"):
        word, s = _shares(f, pos)
        last3 = s[-3:]
        if len(last3) >= 2:
            delta = last3[-1] - last3[0]
            steps = [b - a for a, b in zip(last3, last3[1:], strict=False)]
            running = len(last3) == 3 and (all(x < 0 for x in steps) or all(x > 0 for x in steps))
            if abs(delta) >= (0.06 if running else 0.10):
                verb = "dropped" if delta < 0 else "climbed"
                how = (f"has {verb} three games running" if running else
                       f"{'fell' if delta < 0 else 'rose'} from {last3[0]:.0%} to {last3[-1]:.0%} last game")
                tail = f" ({last3[0]:.0%} → {last3[-1]:.0%})" if running else ""
                out.append((max(-1.0, min(1.0, delta / 0.15)), "role", f"{name}'s share of the {word} {how}{tail}"))
        level = _num(f.get("carry_share_std" if pos == "RB" else "target_share_std"))
        if level is None and s:
            level = sum(s) / len(s)
        if level is not None:
            hi, lo = (0.55, 0.25) if pos == "RB" else (0.25, 0.12)
            if level >= hi:
                out.append((0.5, "level", f"{name} gets {level:.0%} of his team's {word}"))
            elif level <= lo:
                out.append((-0.4, "level", f"{name} is in a part-time role ({level:.0%} of his team's {word})"))
    return out


def _as_him(clause: str, name: str) -> str:
    """'Wilson is at home …' -> 'he is at home …', "Wilson's share …" -> 'his share …' (the name was just said)."""
    if clause.startswith(name + "'s "):
        return "his " + clause[len(name) + 3:]
    if clause.startswith(name + " "):
        return "he " + clause[len(name) + 1:]
    return clause


def is_coin_flip(d) -> bool:
    """The card's own rule for "too close to call": under CLOSE_PWIN when the odds exist, else a margin under COIN_FLIP."""
    pw = _num(d.get("p_win") if hasattr(d, "get") else d["p_win"])
    margin = _num(d.get("margin") if hasattr(d, "get") else d["margin"]) or 0.0
    return (pw < CLOSE_PWIN) if pw is not None else margin < COIN_FLIP


def reason_line(d: dict, facts: dict | None = None, nicks: dict | None = None) -> str:
    """The card's one-sentence reason. `facts` = {gsis_id: REASON_SQL row}, `nicks` = {team: nickname}; both optional
    (without them the sentence uses only the card's own matchup and injury columns)."""
    d = {k: (None if not isinstance(v, (list, tuple, dict)) and pd.isna(v) else v) for k, v in dict(d).items()}
    facts, nicks = facts or {}, nicks or {}
    a_full, b_full = d.get("player_name") or "", d.get("alt_name") or ""
    a, b = last_name(a_full, d.get("position")), last_name(b_full, d.get("alt_position"))
    if a == b:                                   # Michael Wilson vs Emanuel Wilson: the whole names
        a, b = a_full, b_full
    d["_short_me"], d["_short_alt_"] = a, b
    mine = reason_pieces(d, "", facts.get(d.get("gsis_id")) or {}, nicks)
    theirs = reason_pieces(d, "alt_", facts.get(d.get("alt_gsis_id")) or {}, nicks)
    # every piece seen from the starter's side: + = a reason to start him, - = a reason to start the other player
    both = [(s, k, c, a) for s, k, c in mine] + [(-s, k, c, b) for s, k, c in theirs]
    margin = _num(d.get("margin")) or 0.0
    if is_coin_flip(d):
        gap = "the projection has them level" if margin < 0.05 else f"the projection says {a} by {margin:.1f}"
        head = f"Too close to call: {gap}, the ranges say either"
        cav = [c for c in ((facts.get(d.get(k)) or {}).get("personnel_caveat") for k in ("gsis_id", "alt_gsis_id")) if c]
        if cav:                                                          # ---- IF-3: the old rank does not settle it
            head += f"; the matchup rank does not settle it this week: {'; '.join(cav)}"
        tb = _tiebreak(both, a, b)                                       # ---- IE-1: the tiebreaker, its own function
        if tb is not None:
            return f"{head}. Go with {tb['pick']}{tb['words']}: {tb['text']}."
        return f"{head}. Check the news before kickoff."
    pro = max((p for p in both if p[0] >= STRONG and p[3] == a), key=lambda p: p[0], default=None)
    con = max((p for p in both if p[0] >= STRONG and p[3] == b), key=lambda p: p[0], default=None)
    ahead = f"the projection has him {margin:.1f} points ahead"
    if pro and con:
        return f"{pro[2]}; {con[2]}."
    if pro:
        return f"{pro[2]}, and {ahead}."
    if con:
        return f"{con[2]}, and the projection has {a} {margin:.1f} points ahead."
    counter = min((p for p in both if p[0] <= -STRONG), key=lambda p: p[0], default=None)
    if counter:
        return f"{counter[2]}, but the projection still has {'him' if counter[3] == a else a} {margin:.1f} points ahead."
    return f"Nothing in the matchups or the roles splits them: the projection has {a} {margin:.1f} points ahead."


# ---- IE-1 (Wave I-E, the casual-user review): the coin flip's tiebreaker as data, so My Week's actions can say who
# sits ("Keep Addison and Nabers ahead of McConkey for now") from the same pieces the card's sentence reads
TIE_KINDS = (("injury", ""), ("matchup", " on the matchup"), ("role", " on the role"), ("line", " on the betting line"))


def _tiebreak(both: list, a: str, b: str) -> dict | None:
    """The coin flip's tiebreaker: an injury first, then the matchups, the roles, the betting lines (the side they add up
    for). {kind, pick (a short name), side ('me' | 'alt'), words, text} or None (nothing splits them)."""
    uncertain = any(p[1] == "matchup_caveat" for p in both)              # ---- IF-3: never the matchup then
    for kind, words in TIE_KINDS:
        if kind == "matchup" and uncertain:
            continue
        ps = [p for p in both if p[1] == kind]
        net = sum(p[0] for p in ps)
        if not ps or abs(net) < 0.5:
            continue
        pick = a if net > 0 else b
        clause = max((p for p in ps if (p[0] > 0) == (net > 0)), key=lambda p: abs(p[0]))
        text = _as_him(clause[2], pick) if clause[3] == pick else clause[2]
        return {"kind": kind, "pick": pick, "side": "me" if net > 0 else "alt", "words": words, "text": text,
                "clause": clause[2], "matchup_uncertain": uncertain}                # ---- IF-3
    return None


def tiebreak(d: dict, facts: dict | None = None, nicks: dict | None = None) -> dict | None:
    """`reason_line`'s tiebreaker for a coin-flip card (None for a card that is not one, or when nothing splits them)."""
    d = {k: (None if not isinstance(v, (list, tuple, dict)) and pd.isna(v) else v) for k, v in dict(d).items()}
    if not is_coin_flip(d):
        return None
    facts, nicks = facts or {}, nicks or {}
    a_full, b_full = d.get("player_name") or "", d.get("alt_name") or ""
    a, b = last_name(a_full, d.get("position")), last_name(b_full, d.get("alt_position"))
    if a == b:
        a, b = a_full, b_full
    d["_short_me"], d["_short_alt_"] = a, b
    mine = reason_pieces(d, "", facts.get(d.get("gsis_id")) or {}, nicks)
    theirs = reason_pieces(d, "alt_", facts.get(d.get("alt_gsis_id")) or {}, nicks)
    tb = _tiebreak([(s, k, c, a) for s, k, c in mine] + [(-s, k, c, b) for s, k, c in theirs], a, b)
    if tb is not None:                                                   # ---- IF-3: the card's flag, either player
        tb["matchup_uncertain"] = tb["matchup_uncertain"] or matchup_uncertain(d, facts)
    return tb
# ---- end IE-1


# ---- IF-3 (Wave I-F, the decision-quality review § Priority 1): a defense's rank against receivers was earned by the
# corners who played its games; when they are not the corners expected this week, the rank is less representative and
# must not settle a close call. `corner_personnel` compares, per defense and week:
#   * the regulars: its corners with at least REGULAR_SHARE of the leading corner's coverage snaps this season
#     (mart_cb_rankings, window "season": the games played so far; at most three);
#   * the listed starters: its depth chart as of the game (mart_cb_matchups' left / right / slot corner, rank 1);
#   * who cannot play: `STATUSES` (the API sets it to the availability overlay, availability.now: ESPN / Sleeper with
#     the date; the console has no overlay and reads the depth chart only). A listed starter who cannot play gives his
#     spot to the next corner at that spot on the same depth chart (mart_matchup_cb_context, depth rank 2+).
# kind: "changed" (a regular is missing: he cannot play, or the depth chart no longer starts him), "same", "unknown"
# (no depth chart before the game, or no games this season). Receivers only: corners are what the evidence covers.
# No number moves: the projection is untouched; a changed defense only stops the matchup rank breaking a tie.
STATUSES = None                  # callable(list[gsis]) -> {gsis: {status, code, cannot_play, source, as_of, note}}
REGULAR_SHARE = 0.5
OUT_WORDS = {"IR": "on injured reserve", "OUT": "out", "DOUBTFUL": "doubtful", "PUP": "on the PUP list", "NFI": "on the NFI list",
             "SUS": "suspended", "INACTIVE": "inactive"}
REGULARS_SQL = """
select latest_team as defense, gsis_id, defender_name, coverage_snaps::float as coverage_snaps, games_at_cb, team_games
from analytics.mart_cb_rankings
where season = %s and window_label = 'season' and latest_team = any(%s) and coverage_snaps > 0
"""
LISTED_SQL = """
select distinct on (opponent) opponent as defense, depth_chart_at, lcb_gsis_id, lcb_name, rcb_gsis_id, rcb_name, nb_gsis_id, nb_name
from analytics.mart_cb_matchups
where season = %s and week = %s and opponent = any(%s)
order by opponent, depth_chart_at desc nulls last
"""
BACKUPS_SQL = """
select defense, snapshot_at, gsis_id, defender_name, depth_position, depth_rank
from analytics.mart_matchup_cb_context
where defense = any(%s) and depth_position in ('LCB', 'RCB', 'NB')
order by defense, depth_position, depth_rank
"""
CB_RANK_SQL = """
select gsis_id, quality_rank, quality_label, n_ranked from analytics.mart_cb_rankings
where season = %s and window_label = 'two_seasons' and gsis_id = any(%s)
"""


def _names(people: list[dict]) -> str:
    """'Horn' / 'Horn and Jackson' / 'Evans, Lee and Smith-Wade' (last names)."""
    ns = [last_name(p.get("name")) or str(p.get("name") or "") for p in people]
    return ns[0] if len(ns) == 1 else f"{', '.join(ns[:-1])} and {ns[-1]}" if ns else ""


def corner_personnel(defenses, season: int, week: int, statuses: dict | None = None) -> dict[str, dict]:
    """{defense: {kind, depth_chart_at, regulars, listed, expected, missing}} for the defenses' games of `week`."""
    defs = sorted({str(x) for x in defenses if isinstance(x, str) and x})
    if not defs or season is None or week is None:
        return {}
    if missing_relations(("mart_cb_rankings", "mart_cb_matchups")):
        return {d: {"kind": "unknown", "why": "no corner data on this copy", "regulars": [], "listed": [], "expected": [],
                    "missing": [], "depth_chart_at": None} for d in defs}
    reg = query(REGULARS_SQL, (int(season), defs))
    lst = query(LISTED_SQL, (int(season), int(week), defs))
    bk = pd.DataFrame() if missing_relations(("mart_matchup_cb_context",)) else query(BACKUPS_SQL, (defs,))   # optional
    listed_of = {r["defense"]: r for r in lst.to_dict("records")} if not lst.empty else {}
    ids: set[str] = set()
    pre: dict[str, dict] = {}
    for d in defs:
        rr = reg[reg["defense"] == d] if not reg.empty else reg
        regulars = []
        if not rr.empty:
            top = float(rr["coverage_snaps"].max())
            rr = rr[rr["coverage_snaps"] >= REGULAR_SHARE * top].sort_values("coverage_snaps", ascending=False).head(3)
            regulars = [{"gsis_id": r["gsis_id"], "name": r["defender_name"], "share": round(float(r["coverage_snaps"]) / top, 2),
                         "coverage_snaps": round(float(r["coverage_snaps"]), 1), "games": int(r["games_at_cb"] or 0)}
                        for r in rr.to_dict("records")]
        L = listed_of.get(d)
        at = None if L is None or pd.isna(L.get("depth_chart_at")) else L["depth_chart_at"]
        listed = [] if at is None else [{"gsis_id": L[f"{s}_gsis_id"], "name": L[f"{s}_name"], "slot": s.upper()}
                                        for s in ("lcb", "rcb", "nb") if isinstance(L.get(f"{s}_gsis_id"), str)]
        backups: dict[str, list[dict]] = {}
        if at is not None and not bk.empty:
            b = bk[(bk["defense"] == d) & (bk["depth_rank"] > 1)]
            b = b[pd.to_datetime(b["snapshot_at"], utc=True) == pd.to_datetime(at, utc=True)]   # the same depth chart only
            for r in b.to_dict("records"):
                backups.setdefault(r["depth_position"], []).append({"gsis_id": r["gsis_id"], "name": r["defender_name"]})
        pre[d] = {"regulars": regulars, "listed": listed, "backups": backups, "depth_chart_at": at}
        ids |= {p["gsis_id"] for p in regulars + listed} | {p["gsis_id"] for v in backups.values() for p in v}
    if statuses is None and STATUSES is not None and ids:
        try:
            statuses = STATUSES(sorted(ids))
        except Exception:  # noqa: BLE001 - the overlay is never load-bearing: the depth chart alone still answers
            statuses = {}
    statuses = statuses or {}

    def out_of(g) -> dict | None:
        s = statuses.get(g)
        return s if s and s.get("cannot_play") else None

    out: dict[str, dict] = {}
    for d, p in pre.items():
        regulars, listed = p["regulars"], p["listed"]
        if p["depth_chart_at"] is None or not regulars:
            out[d] = {"kind": "unknown", "why": "no depth chart before this game" if p["depth_chart_at"] is None
                      else "no games this season yet", "regulars": regulars, "listed": listed, "expected": [],
                      "missing": [], "depth_chart_at": p["depth_chart_at"]}
            continue
        expected = []
        for c in listed:
            if out_of(c["gsis_id"]) is None:
                expected.append({**c, "replaces": None})
                continue
            nxt = next((b for b in p["backups"].get(c["slot"], []) if out_of(b["gsis_id"]) is None
                        and b["gsis_id"] not in {e["gsis_id"] for e in expected}), None)
            if nxt is not None:
                expected.append({**nxt, "slot": c["slot"], "replaces": c["name"]})
        exp_ids = {e["gsis_id"] for e in expected}
        reg_ids = {r["gsis_id"] for r in regulars}
        missing = []
        for r in regulars:
            if r["gsis_id"] in exp_ids:
                continue
            s = out_of(r["gsis_id"])
            missing.append({"gsis_id": r["gsis_id"], "name": r["name"],
                            "status": None if s is None else s.get("status"), "code": None if s is None else s.get("code"),
                            "source": None if s is None else s.get("source"), "as_of": None if s is None else s.get("as_of"),
                            "note": None if s is None else s.get("note"),
                            "reason": "status" if s is not None else "depth chart"})
        for e in expected:
            e["is_new"] = e["gsis_id"] not in reg_ids
        out[d] = {"kind": "changed" if missing else "same", "regulars": regulars, "listed": listed, "expected": expected,
                  "missing": missing, "depth_chart_at": p["depth_chart_at"]}
    ranks = query(CB_RANK_SQL, (int(season), sorted({e["gsis_id"] for v in out.values() for e in v["expected"]})))
    rk = {r["gsis_id"]: r for r in ranks.to_dict("records")} if not ranks.empty else {}
    for v in out.values():
        for e in v["expected"]:
            r = rk.get(e["gsis_id"]) or {}
            q = r.get("quality_rank")
            e["rank"] = None if q is None or pd.isna(q) else int(q)
            e["label"] = r.get("quality_label") if e["rank"] is not None else None
            e["n_ranked"] = None if r.get("n_ranked") is None or pd.isna(r.get("n_ranked")) else int(r["n_ranked"])
    return out


def missing_words(m: list[dict]) -> str:
    """'Horn and Jackson are on injured reserve' / 'Horn is out; Jackson is not on the depth chart's starting spots'."""
    by: dict[str, list[dict]] = {}
    for x in m:
        by.setdefault(OUT_WORDS.get(str(x.get("code")), "") if x["reason"] == "status" else "no longer listed as a starter", []).append(x)
    parts = []
    for what, people in by.items():
        verb = "is" if len(people) == 1 else "are"
        parts.append(f"{_names(people)} {verb} {what or 'unable to play'}")
    return "; ".join(parts)


def personnel_caveat(p: dict | None, place: str) -> str | None:
    """The card's short words for a changed defense: "Carolina's starting corners changed (Horn and Jackson are on
    injured reserve)". None unless kind == "changed"."""
    if not p or p.get("kind") != "changed":
        return None
    n, k = len(p["regulars"]), len(p["missing"])
    who = (f"{place}'s starting corners changed" if k >= 2 and k == n else
           f"{k} of {place}'s {n} regular corners changed" if k >= 2 else f"one of {place}'s regular corners changed")
    return f"{who} ({missing_words(p['missing'])})"


def personnel_facts(dec: pd.DataFrame, season, week) -> dict[str, dict]:
    """{receiver gsis: {kind, caveat, defense}} for the WRs on a set of cards (one corner read for every defense)."""
    if dec is None or dec.empty or season is None or week is None:
        return {}
    pairs = []
    for d in dec.to_dict("records"):
        for side in ("", "alt_"):
            g, pos, opp = d.get(side + "gsis_id"), d.get(side + "position"), d.get(side + "opponent")
            if isinstance(g, str) and pos == "WR" and isinstance(opp, str) and opp:
                pairs.append((g, opp))
    if not pairs:
        return {}
    pers = corner_personnel({o for _, o in pairs}, int(season), int(week))
    places = query("select team_abbr, team_name, team_nick from analytics.dim_team where team_abbr = any(%s)",
                   (sorted({o for _, o in pairs}),))
    place = {r["team_abbr"]: str(r["team_name"]).removesuffix(" " + str(r["team_nick"])).strip() or r["team_abbr"]
             for r in places.to_dict("records")} if not places.empty else {}
    return {g: {"kind": pers.get(o, {}).get("kind", "unknown"), "defense": o,
                "caveat": personnel_caveat(pers.get(o), place.get(o, o))} for g, o in pairs}


def matchup_uncertain(d: dict, facts: dict) -> bool:
    """A card whose receiver faces a defense whose regular corners changed: the matchup rank does not settle it."""
    return any(bool((facts.get(d.get(k)) or {}).get("personnel_caveat")) for k in ("gsis_id", "alt_gsis_id"))
# ---- end IF-3


def reason_facts(dec: pd.DataFrame, season: int | None, week: int | None) -> tuple[dict, dict]:
    """({gsis_id: REASON_SQL row}, {team: nickname}) for a set of cards: one query (and the 32 team names)."""
    if dec is None or dec.empty or season is None or week is None:
        return {}, {}
    if missing_relations(("mart_player_week_features", "fct_player_game", "dim_team")):
        return {}, {}
    ids = sorted({str(g) for g in pd.concat([dec["gsis_id"], dec["alt_gsis_id"]]).dropna()})
    s, w = int(season), int(week)
    df = query(REASON_SQL, (ids, s, w, s, w)) if ids else pd.DataFrame()
    nk = query(TEAM_NICK_SQL)
    facts = {r["gsis_id"]: r for r in df.to_dict("records")} if not df.empty else {}
    for g, p in personnel_facts(dec, s, w).items():                     # ---- IF-3: the opponent's corners now
        facts.setdefault(g, {"gsis_id": g}).update(personnel_kind=p["kind"], personnel_caveat=p["caveat"])
    return facts, dict(zip(nk["team_abbr"], nk["team_nick"], strict=False)) if not nk.empty else {}
# ---- end IA-1


# ------------------------------------------------------------------------------ rendering
# ---- IF-4 (Wave I-F, the decision-quality review's table: "Matchup rank direction changes between screens"): one direction
# everywhere, always said in words — "2nd-fewest WR points allowed" (rank 31 of 32), "5th-most RB points allowed" (rank 5)
def rank_words(rank, position, n: int = 32) -> str:
    """The opponent's rank against the position (1 = gives up the most) in words; '' when unknown."""
    if rank is None or (isinstance(rank, float) and pd.isna(rank)):
        return ""
    k, n = int(rank), int(n or 32)
    pos = str(position or "").upper() or "his position's"
    if k <= (n + 1) // 2:
        return f"the most {pos} points allowed" if k == 1 else f"{_ordinal(k)}-most {pos} points allowed"
    f = n + 1 - k
    return f"the fewest {pos} points allowed" if f == 1 else f"{_ordinal(f)}-fewest {pos} points allowed"
# ---- end IF-4


def _matchup(name: str, opp, rank, position) -> str:
    if opp is None or (isinstance(opp, float) and pd.isna(opp)):
        return ""
    r = f" ({rank_words(rank, position)})" if rank is not None and pd.notna(rank) else ""        # IF-4: was "(#31 vs WR)"
    return f"{name} vs {opp}{r}"


def _flag(status) -> str:
    return f"{status}" if isinstance(status, str) and status and status != "Healthy" else ""


def render_decision(d: pd.Series | dict, why: str | None = None) -> None:
    """One decision as a bordered card: the call, the reason in one sentence (IA-1: `reason_line`), then in small print
    how often he outscores the other player, the numbers, the ranges, the matchups, any injury flag."""
    d = pd.Series(d)
    slot = slot_label(d["slot"])
    me = player_link(d["gsis_id"], d["player_name"])
    with st.container(border=True):
        if d["alt_name"] is None or (isinstance(d["alt_name"], float) and pd.isna(d["alt_name"])):
            st.markdown(f"**{slot}: start {me}** — {d['how']}.")
            return
        alt = player_link(d["alt_gsis_id"], d["alt_name"])
        if is_coin_flip(d):
            # PO, Wave I-A: a coin flip is said as one ("A or B"), so the reason's tiebreaker ("Go with B on the
            # matchup") never contradicts the headline; the lineup table still shows the projection's pick
            st.markdown(f"**{slot}: {me} or {alt} — a coin flip**")
        else:
            st.markdown(f"**{slot}: start {me} over {alt}**")
        if why:
            # Wave I-A (Andrew: "reasons why"): the matchup, the role, the injury, the gap — a sentence a manager reads
            st.markdown(why)
        basis = ("projected" if d.get("value_source") == "proj_points" and d.get("alt_value_source") == "proj_points"
                 else "points per game this season" if {d.get("value_source"), d.get("alt_value_source")} <= {"season_ppg", "observed_ppg"}
                 else "for the lineup")
        pw = _num(d.get("p_win"))
        extra = []
        numbers = f"{d['value']:.2f} vs {d['alt_value']:.2f} {basis}: {d['margin']:.2f} apart."
        if pw is not None:
            # plan D6's odds, now the small print under the reason (Wave I-A): how often he outscores the other player,
            # then the margin the lineup is solved on
            if pw >= 0.5:
                extra.append(f"{d['player_name']} outscores {d['alt_name']} {D.percent(pw)}% of the time — {D.words(pw)}. {numbers}")
            else:
                # the range (how often) and the projection (how many points on average) disagree on this close call:
                # the lineup is built on the projection, so the recommendation leads and the odds explain
                extra.append(f"{d['player_name']} projects {d['margin']:.2f} more on average; {d['alt_name']} outscores him "
                             f"{D.percent(1 - pw)}% of the time — {D.words(1 - pw)}. {numbers}")
            (m1, w1), (m2, w2) = range_text(d), range_text(d, "alt_")
            if m1 and m2:
                extra.append(f"Typical range (the middle 50%): {d['player_name']} {m1}, {d['alt_name']} {m2}.")   # IF-4
            if w1 and w2:
                extra.append(f"A bad week to a good week: {d['player_name']} {w1}, {d['alt_name']} {w2}.")
        else:
            extra.append(f"{d['value']:.2f} vs {d['alt_value']:.2f} {basis} — **{d['margin']:.2f} apart, {d['verdict']}**.")
        if d.get("mover_name") and isinstance(d["mover_name"], str):
            extra.append(f"{d['alt_name']} would come in at {slot_label(d['mover_slot'])} and {d['mover_name']} would move to {slot}.")
        m = " · ".join(x for x in (_matchup(d["player_name"], d["opponent"], d["opp_rank"], d["position"]),
                                   _matchup(d["alt_name"], d["alt_opponent"], d["alt_opp_rank"], d["alt_position"])) if x)
        if m:
            extra.append(m)
        for who, s in ((d["player_name"], d["report_status"]), (d["alt_name"], d["alt_report_status"])):
            if _flag(s):
                extra.append(f"⚠️ {who} is {s}.")
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
    # IA-1: one read for the reasons of every card (the betting line, the shares game by game, the team names)
    facts, nicks = reason_facts(dec, season if season is not None else league_season(league_id), week)
    dec["why"] = [reason_line(d, facts, nicks) for d in dec.to_dict("records")]
    dec["tiebreak"] = [tiebreak(d, facts, nicks) for d in dec.to_dict("records")]       # ---- IE-1 (the actions read it)
    dec["matchup_uncertain"] = [matchup_uncertain(d, facts) for d in dec.to_dict("records")]   # ---- IF-3 (IF-4 reads it)
    for _, d in dec.iterrows():
        render_decision(d, d["why"])
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


NO_SLOT = "No slot for"          # IC-2: lineup.NO_SLOT, the reason of a player no slot of the league admits


def no_slot_or_cant(reason) -> str:
    """The list's word for a player out of the lineup: "No slot" (the league's lineup has no place for his position;
    he is not hurt) or "Can't play" (injury, bye, IR, locked)."""
    return "No slot" if isinstance(reason, str) and reason.startswith(NO_SLOT) else "Can't play"


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
                              else no_slot_or_cant(r.get("reason")), axis=1)          # IC-2
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
            "- The lineup is the best one your roster can start this week, in your league's scoring, with FLEX and "
            "superflex filled by whoever is worth most there. Start it, then check the cards.\n"
            "- Each card is one of the week's closest calls: who to start, then **why** in one sentence (the matchup, his "
            "share of his team's carries or targets, an injury, the betting line). On a coin flip the card says so and names "
            "the tiebreaker.\n"
            "- The small print starts with **how often your starter outscores the other player** this week, from both "
            "players' ranges: 50–55% is a coin flip (go with the latest news), 55–65% a lean, 65% or more clear. Teammates "
            "and players facing each other are not independent (a shootout lifts both), and the percentage allows for that.\n"
            "- **Apart** is how many projected points separate them: the lineup is built on those averages. On a coin flip "
            "the two can disagree (under 50% but more points): the card then says both.\n"
            "- **Typical range** is the middle 50% of his outcomes: half of his weeks land in it (a quarter below, a quarter above). **A bad week to a "
            "good week** is the wider range 8 weeks in 10 land in. A card without a percentage (a kicker, a defense) "
            f"falls back on the points: under {COIN_FLIP:.0f} point apart is a coin flip, under {LEAN:.0f} a lean.\n"
            "- The named player is the one who would really come in: your best bench player for that spot, or, when "
            "moving a teammate over works better, the card says who moves.\n"
            "- **5th-fewest WR points allowed** is the opponent's rank against that position this season, said one way "
            "everywhere: the most points allowed is the matchup you want, the fewest the toughest.\n"
            "- No card for a player whose game has started (he is locked) or for a starter nobody on your bench can "
            "replace, like your only kicker."
        )
