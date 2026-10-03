"""My Week (Home's "My week" block) as JSON.

Same numbers and words as `app/Home.py`:
* the week: `cards.decision_week(season)` (= `ui.current_week`, the one week rule);
* the lineup: ONE call to `cards.lineup_rows` (LINEUP_SQL: `mart_lineup_recommendation` + `ops.lineups`);
* the cards: `cards.decisions(rows)` for the numbers and `cards.decision_cards(...)` run through the Streamlit
  stand-in for the text (so a wording change in cards.py shows up here unchanged);
* `cards.league_line`, `cards.lineup_frame` (the four-column table) and `cards.howto_cards` (captured);
* the record / opponent line and the movers query are inline in Home.py, so they are copied here verbatim
  (marked below) — the parity test in tests/test_parity.py compares them with the rendered page.
"""

from __future__ import annotations

import math

import pandas as pd

from . import availability
from .applib import blocks, capture, cards, links, ui
from .db import query


class NotFound(LookupError):
    pass


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _str(v) -> str | None:
    return v if isinstance(v, str) and v else None


def leagues() -> list[dict]:
    df = ui.current_leagues()
    return [{"league_id": r.league_id, "league_name": r.league_name, "season": int(r.season),
             "scoring_label": _str(r.scoring_label), "is_reference_league": bool(r.is_reference_league)}
            for r in df.itertuples()]


def league_row(league_id: str) -> pd.Series:
    df = ui.current_leagues()
    row = df[df["league_id"] == league_id]
    if row.empty:
        raise NotFound(f"no current-season league {league_id}")
    return row.iloc[0]


def rosters(league_id: str) -> list[dict]:
    league_row(league_id)
    # copied from lib/ui.py perspective() (the team picker's options)
    members = query(
        """select roster_id, team_name, manager_name from analytics.dim_league_member
               where league_id = %s order by team_name""",
        (league_id,),
    )
    return [{"roster_id": int(r.roster_id), "team_name": r.team_name, "manager_name": _str(r.manager_name)}
            for r in members.itertuples()]


def _lineup_row(r: pd.Series) -> dict:
    out = {"role": r["role"], "slot": r["slot"], "player_name": _str(r.get("player_name")),
           "gsis_id": _str(r.get("gsis_id")), "position": _str(r.get("position")),
           "value": _num(r.get("value")), "margin": _num(r.get("margin")), "flag": _str(r.get("flag")) or ""}
    # ---- I0-A: the availability overlay's chip (OUT / DOUBTFUL / IR) and its reason ("Out (ankle) · ESPN, Oct 2 2:35 PM ET")
    if _str(r.get("chip")):
        out["flag"], out["reason"] = r["chip"], _str(r.get("why"))
    # ---- end I0-A
    return out


HEADSHOT_SQL = "select gsis_id, headshot_url from analytics.dim_player where gsis_id = any(%s)"    # IA-1


def lineup(rows: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """(the four-column table: cards.lineup_frame, the full list: + bench and can't-play rows, as
    cards.lineup_table(full=True) builds them — that function draws the table itself, so its six lines are mirrored)."""
    if rows is None or rows.empty:
        return [], []
    lu = cards.lineup_frame(rows)
    short = [_lineup_row(r) for _, r in lu.iterrows()]
    # ---- IA-1: the headshot and the NFL team on every row (the player card unit's small size in the slot list)
    ids = sorted({str(g) for g in rows["gsis_id"].dropna()})
    heads = query(HEADSHOT_SQL, (ids,)) if ids else pd.DataFrame()
    face = dict(zip(heads["gsis_id"], heads["headshot_url"], strict=False)) if not heads.empty else {}
    # ---- end IA-1
    rest = rows[rows["role"] != "starter"].copy()
    if not rest.empty:
        rest["slot"] = rest.apply(lambda r: f"Bench {int(r['bench_rank'])}" if r["role"] == "bench" and pd.notna(r["bench_rank"])
                                  else "Can't play", axis=1)
        rest["flag"] = rest.apply(lambda r: r["reason"] if r["role"] == "unplayable" else ("locked (game started)" if r["locked_now"]
                                  else cards._flag(r["report_status"])), axis=1)
    full = short + [_lineup_row(r) for _, r in rest.iterrows()]
    # ---- IA-1
    team_of = {str(r["gsis_id"]): _str(r.get("team")) for _, r in rows.iterrows() if _str(r.get("gsis_id"))}
    for x in full:
        x["headshot_url"] = _str(face.get(x["gsis_id"])) if x["gsis_id"] else None
        x["team"] = team_of.get(x["gsis_id"]) if x["gsis_id"] else None
    # ---- end IA-1
    return short, full


def my_week(league_id: str, roster_id: int) -> dict:
    lrow = league_row(league_id)
    season = int(lrow["season"])
    members = query("""select roster_id, team_name, manager_name from analytics.dim_league_member
               where league_id = %s order by team_name""", (league_id,))
    me = members[members["roster_id"] == int(roster_id)]
    if me.empty:
        raise NotFound(f"no team {roster_id} in league {league_id}")
    me = me.iloc[0]
    week = cards.decision_week(season)
    out: dict = {"league_id": league_id, "league_name": lrow["league_name"], "season": season,
                 "scoring_label": _str(lrow["scoring_label"]), "roster_id": int(roster_id),
                 "team_name": me["team_name"], "manager_name": _str(me["manager_name"]), "week": week,
                 "record": None, "opponent": None, "source": "database", "summary": f"**{me['team_name']}**", "league_line": "",
                 "cards": [], "notice": None, "lineup": [], "lineup_full": [], "howto": None, "movers": []}
    if week is None:
        out["notice"] = "The regular season is over: no lineup decisions left."
        return out
    # ---- copied from app/Home.py (the record and the opponent)
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
    # ---- I0-A + IB-0: the roster's context (the nightly's rows + the availability overlay, re-solved when a status
    # changed since the build) - the same rows Waivers, Team, the player card and the trade board read
    ctx = availability.roster_context(league_id, int(roster_id), week, house=True)
    rows, out["availability"] = ctx.rows, ctx.meta
    # ---- end I0-A + IB-0
    bits = [f"**{me['team_name']}**"]
    if not prof.empty and pd.notna(prof.iloc[0]["wins"]):
        r = prof.iloc[0]
        out["record"] = {"wins": int(r["wins"]), "losses": int(r["losses"]), "standing": int(r["standing"])}
        bits.append(f"{int(r['wins'])}-{int(r['losses'])}, #{int(r['standing'])} in the league")
    if not opp.empty and isinstance(opp.iloc[0]["opponent"], str):
        bits.append(f"week {week} vs **{opp.iloc[0]['opponent']}**")
    out["summary"] = " · ".join(bits)
    # ---- end of the copy
    out["opponent"] = opponent(league_id, int(roster_id), season, week)
    if not rows.empty:
        out["league_line"] = cards.league_line(league_id, roster_id, week, rows)
        lv = rows.loc[rows["role"] == "starter", "lineup_value"].dropna()
        out["lineup_value"] = None if lv.empty else float(lv.iloc[0])
    # the cards: numbers from decisions(), text from decision_cards() as drawn
    out["notice"], out["cards"] = cards_from_rows(league_id, roster_id, week, season, rows,
                                                  current=current_starters(league_id, int(roster_id), house=True))  # IB-0
    out["lineup"], out["lineup_full"] = lineup(rows)
    out["howto"] = howto()
    # ---- copied from app/Home.py (Movers on your roster)
    mv = query(
        """select t.gsis_id, t.player_name, t.position, t.tags, t.momentum
                   from analytics.mart_player_trend_tags t
                   join analytics.mart_player_availability a on a.gsis_id = t.gsis_id and a.league_id = %s
                   where t.season = %s and a.rostered_by_roster_id = %s and t.opportunity_trend in ('rising', 'falling')
                   order by abs(t.momentum) desc limit 9""",
        (league_id, season, roster_id),
    )
    out["movers"] = [{"gsis_id": _str(r.gsis_id), "player_name": r.player_name, "position": r.position,
                      "tags": _str(r.tags), "momentum": _num(r.momentum)} for r in mv.itertuples()]
    return out


LINEUP_TOTAL_SQL = """select lineup_value from ops.lineup_totals
                       where league_id = %s and season = %s and week = %s and roster_id = %s and not is_realised
                       order by run_at desc limit 1"""
MATCHUP_DB_SQL = """select m.opponent_roster_id as roster_id, o.team_name, o.manager_name, m.matchup_id
                    from analytics.fct_league_matchup m
                    left join analytics.dim_league_member o on o.league_id = m.league_id and o.roster_id = m.opponent_roster_id
                    where m.league_id = %s and m.roster_id = %s and m.week = %s and m.opponent_roster_id is not null"""


def opponent(league_id: str, roster_id: int, season: int, week: int) -> dict | None:
    """Plan F3: the week's opponent {roster_id, team_name, manager, lineup_value} for a house league. Who: Sleeper's
    matchups call (cached 5 minutes), else the nightly's fct_league_matchup (Sleeper down / our budget spent);
    names from dim_league_member; lineup_value = the opponent's best lineup the nightly solved (ops.lineup_totals,
    the number mart_lineup_recommendation shows him). None when the week has no matchup."""
    from .ondemand import opponent_safe
    opp, _ = opponent_safe(league_id, roster_id, week, solve=False)
    if opp is None:
        m = query(MATCHUP_DB_SQL, (league_id, roster_id, week))
        if m.empty:
            return None
        opp = {"roster_id": int(m.iloc[0]["roster_id"]), "matchup_id": int(m.iloc[0]["matchup_id"])}
    mem = query("select team_name, manager_name from analytics.dim_league_member where league_id = %s and roster_id = %s",
                (league_id, int(opp["roster_id"])))
    lv = query(LINEUP_TOTAL_SQL, (league_id, int(season), int(week), int(opp["roster_id"])))
    # ---- IB-0: the opponent's total through the same overlay (his context), the nightly's total when he has no rows
    octx = availability.roster_context(league_id, int(opp["roster_id"]), week, house=True)
    total = octx.lineup_value if octx is not None and octx.lineup_value is not None else (
        None if lv.empty else _num(lv.iloc[0]["lineup_value"]))
    # ---- end IB-0
    return {"roster_id": int(opp["roster_id"]),
            "team_name": _str(mem.iloc[0]["team_name"]) if not mem.empty else opp.get("team_name"),
            "manager": _str(mem.iloc[0]["manager_name"]) if not mem.empty else opp.get("manager"),
            "matchup_id": opp.get("matchup_id"),
            "lineup_value": total,
            "changes": octx.changes if octx is not None else []}                                   # IB-0


def cards_from_rows(league_id: str, roster_id: int, week: int, season: int, rows: pd.DataFrame,
                    current: dict[str, str] | None = None) -> tuple[str | None, list[dict]]:
    """(the notice line, the cards) for a lineup frame in `cards.lineup_rows`' shape: the numbers from
    `cards.decisions(rows)`, the text from `cards.decision_cards(..., rows=rows)` as drawn. Shared by the database
    path (`my_week`) and the on-demand path (`ondemand.my_week`), which builds the same frame without the marts.
    IB-0: ``current`` = the roster's lineup in Sleeper now ({Sleeper id: slot}): each card's ``status`` (change / set /
    close) and ``strength`` come from `cards.decisions` (the column `cards.SLEEPER_STARTER` on a copy of the rows)."""
    if current is not None and not rows.empty:                                                   # ---- IB-0
        rows = rows.assign(**{cards.SLEEPER_STARTER: rows["sleeper_player_id"].map(lambda s: isinstance(s, str) and s in current)})
    dec = cards.decisions(rows, 3) if not rows.empty else pd.DataFrame()
    drawn_dec, calls = capture(cards.decision_cards, league_id, roster_id, week, season, rows=rows)
    # ---- IA-1: the card's reason sentence, as its own field too (the same words as its second block)
    whys = list(drawn_dec["why"]) if isinstance(drawn_dec, pd.DataFrame) and "why" in drawn_dec else []
    # ---- end IA-1
    drawn: list[list[tuple]] = []
    loose: list[tuple] = []
    cur: list[tuple] | None = None
    for c in calls:
        if c[0] == "container":
            cur = []
        elif c[0] == "end" and cur is not None:
            drawn.append(cur)
            cur = None
        elif cur is not None:
            cur.append(c)
        else:
            loose.append(c)
    notices = [b["text"] for b in blocks(loose) if b["kind"] in ("info", "warning", "markdown", "caption")]
    out = []
    for i, (_, d) in enumerate(dec.iterrows()):
        out.append({
            "slot": d["slot"], "slot_label": cards.slot_label(d["slot"]),
            "gsis_id": _str(d["gsis_id"]), "player_name": d["player_name"], "value": _num(d["value"]),
            "alt_gsis_id": _str(d["alt_gsis_id"]), "alt_name": _str(d["alt_name"]), "alt_value": _num(d["alt_value"]),
            "margin": _num(d["margin"]), "verdict": d["verdict"], "how": d["how"],
            "p_win": _num(d.get("p_win")),
            "why": links(whys[i]) if i < len(whys) and whys[i] else None,     # ---- IA-1
            # ---- IB-0: the call's status (change / set / close; None when Sleeper's lineup is unknown), its strength
            # (clear / lean / coin flip) and who of the two Sleeper starts now
            "status": _str(d.get("status")), "strength": _str(d.get("strength")),
            "in_sleeper_lineup": None if current is None else {"player": bool(d.get("sleeper_starter")),
                                                               "alt": bool(d.get("alt_sleeper_starter"))},
            "blocks": blocks(drawn[i]) if i < len(drawn) else [],
        })
    return (notices[0] if notices else None), out


# ---- IB-0: the roster's lineup in Sleeper right now (the card's status): Sleeper's roster `starters`, each paired with
# the league's starting slot (`roster_positions` without the bench); a house league whose Sleeper call fails falls
# back on the nightly's `mart_player_availability.is_current_starter` (the slot unknown: "").
CURRENT_STARTERS_SQL = """select sleeper_id from analytics.mart_player_availability
                          where league_id = %s and rostered_by_roster_id = %s and is_current_starter"""


def current_starters(league_id: str, roster_id: int, *, house: bool) -> dict[str, str] | None:
    from league_lab import anyleague as A
    try:
        sl = A.sleeper()
        lid = A.check_id(league_id)
        slots = [s for s in (sl.league(lid).get("roster_positions") or []) if s not in ("BN", "IR", "TAXI")]
        r = next((x for x in sl.rosters(lid) if int(x.get("roster_id", -1)) == int(roster_id)), None)
        if r is not None:
            return {str(p): (slots[i] if i < len(slots) else "") for i, p in enumerate(r.get("starters") or [])
                    if p not in (None, "", "0")}
    except Exception:  # noqa: BLE001 - Sleeper busy / down / no such league: the nightly's flag, else unknown
        pass
    if not house:
        return None
    try:
        df = query(CURRENT_STARTERS_SQL, (league_id, int(roster_id)))
    except Exception:  # noqa: BLE001
        return None
    return {str(s): "" for s in df["sleeper_id"].dropna()} if not df.empty else None
# ---- end IB-0


def howto() -> str | None:
    _, how = capture(cards.howto_cards)
    return next((links(c[1][0]) for c in how if c[0] == "markdown" and c[1]), None)


def known_league(league_id: str) -> bool:
    """Is this a current-season league of the database (else /api/my-week serves it on demand from Sleeper)?"""
    if str(league_id or "").strip().lower().startswith("mfl:"):     # I0-B: a MyFantasyLeague key is always on demand
        return False
    df = ui.current_leagues()
    return bool((df["league_id"] == str(league_id)).any())


def status() -> dict:
    """The freshness line and the stale-injury warning every page shows (ui.freshness_banner, captured)."""
    _, calls = capture(ui.freshness_banner)
    caption = next((c[1][0] for c in calls if c[0] == "caption" and c[1]), "")
    warning = next((c[1][0] for c in calls if c[0] == "warning" and c[1]), None)
    return {"freshness": caption, "warning": warning}
