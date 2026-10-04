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
import re

import pandas as pd

from . import availability
from .applib import blocks, capture, cards, links, ui
from .db import query
from .settings import APP_NAME


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
           "value": _num(r.get("value")), "margin": _num(r.get("margin")), "flag": _str(r.get("flag")) or "",
           "key": _str(r.get("sleeper_player_id"))}        # PO (I-E): the roster key the actions use (annotate_swaps)
    # ---- I0-A: the availability overlay's chip (OUT / DOUBTFUL / IR) and its reason ("Out (ankle) · ESPN, Oct 2 2:35 PM ET")
    if _str(r.get("chip")):
        out["flag"], out["reason"] = r["chip"], _str(r.get("why"))
    # ---- end I0-A
    out.update(no_projection_fields(r))                                                             # ---- IG-1
    return out


# ---- IG-1 (Wave I-G, AGENTS.md rule 5 "unknown is not zero"): a player with no projection row (the solver's
# `value_source = 'unvalued'`: no projection this week, a K / DEF with no value yet) is carried at 0 by the solver and was
# sent as `value: 0.0` ("0.00" on the screen: Jacobs on GoodGameBuddy's bench). The API sends `null` and says why; the
# lineup total says how many starters it counts at 0 (`n_unvalued`). INTERFACES.md § IG-1.
UNVALUED = "unvalued"
NO_PROJECTION = "no projection"


def unvalued(r) -> bool:
    """A lineup row with no projection (the solver's source `unvalued`)."""
    return _str(r.get("value_source")) == UNVALUED


def no_projection_fields(r) -> dict:
    """`value` / `margin` null and `no_projection` true for a row with no projection; `no_projection` false otherwise."""
    if not unvalued(r):
        return {"no_projection": False}
    return {"value": None, "margin": None, "no_projection": True}


def n_unvalued(rows: pd.DataFrame | None) -> int:
    """Starters with no projection (counted as 0 in the lineup total) — ops.lineup_totals.n_unvalued's rule on the rows
    the screen shows (the overlay may have re-solved them)."""
    if rows is None or rows.empty or "value_source" not in rows:
        return 0
    st = rows[(rows["role"] == "starter") & ~rows.get("is_empty_slot", pd.Series(False, index=rows.index)).fillna(False).astype(bool)]
    return int((st["value_source"] == UNVALUED).sum())


def unvalued_words(n: int) -> str | None:
    """The lineup total's caveat when it counts a starter with no projection as 0."""
    if not n:
        return None
    return (f"{n} starter{'s have' if n > 1 else ' has'} no projection and {'count' if n > 1 else 'counts'} as 0 in "
            f"this total.")
# ---- end IG-1


HEADSHOT_SQL = "select gsis_id, headshot_url from analytics.dim_player where gsis_id = any(%s)"    # IA-1


def lineup(rows: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """(the four-column table: cards.lineup_frame, the full list: + bench and can't-play rows, as
    cards.lineup_table(full=True) builds them — that function draws the table itself, so its six lines are mirrored)."""
    if rows is None or rows.empty:
        return [], []
    lu = cards.lineup_frame(rows)
    short = [_lineup_row(r) for _, r in lu.iterrows()]
    # ---- IF-4 (the decision-quality review's table: '"Margin" repeats an entire projection when no eligible reserve
    # exists'): each starter's margin names its comparator — the bench player who would come in (cards.alternative, the
    # cards' own rule) or "no eligible reserve" (the slot would be empty: the margin is his whole projection)
    for x, i in zip(short, lu.index, strict=True):
        x.update(margin_comparator(rows.loc[i], rows))               # the row as the rows hold it (its own slot code)
        if x.get("no_projection"):                                    # ---- IG-1: no projection, no margin to name
            x.update({"margin": None, "margin_vs": None, "margin_words": ""})
    # ---- end IF-4
    # ---- IA-1: the headshot and the NFL team on every row (the player card unit's small size in the slot list)
    ids = sorted({str(g) for g in rows["gsis_id"].dropna()})
    heads = query(HEADSHOT_SQL, (ids,)) if ids else pd.DataFrame()
    face = dict(zip(heads["gsis_id"], heads["headshot_url"], strict=False)) if not heads.empty else {}
    # ---- end IA-1
    rest = rows[rows["role"] != "starter"].copy()
    if not rest.empty:
        rest["slot"] = rest.apply(lambda r: f"Bench {int(r['bench_rank'])}" if r["role"] == "bench" and pd.notna(r["bench_rank"])
                                  else cards.no_slot_or_cant(r.get("reason")), axis=1)     # ---- IC-2: "No slot"
        rest["flag"] = rest.apply(lambda r: r["reason"] if r["role"] == "unplayable" else ("locked (game started)" if r["locked_now"]
                                  else cards._flag(r["report_status"])), axis=1)
    full = short + [_lineup_row(r) for _, r in rest.iterrows()]
    for x in full:                                  # ---- IG-1: the console's flag (cards.no_projection_blank), mirrored
        if x.get("no_projection"):
            x["flag"] = NO_PROJECTION if not x["flag"] or x["flag"] == NO_PROJECTION else f"{x['flag']} · {NO_PROJECTION}"
    # ---- IA-1
    team_of = {str(r["gsis_id"]): _str(r.get("team")) for _, r in rows.iterrows() if _str(r.get("gsis_id"))}
    for x in full:
        x["headshot_url"] = _str(face.get(x["gsis_id"])) if x["gsis_id"] else None
        x["team"] = team_of.get(x["gsis_id"]) if x["gsis_id"] else None
    # ---- end IA-1
    # ---- IC-2: a team unit (MFL's team QB / kicker) or a defense has no gsis id: its team from its own row
    team_no_id = {_str(r.get("player_name")): _str(r.get("team")) for _, r in rows.iterrows()
                  if not _str(r.get("gsis_id")) and _str(r.get("player_name"))}
    for x in full:
        if not x["gsis_id"] and x["player_name"]:
            x["team"] = team_no_id.get(x["player_name"])
    # ---- end IC-2
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
    out["n_unvalued"] = n_unvalued(rows)                                                                   # ---- IG-1
    out["unvalued_words"] = unvalued_words(out["n_unvalued"])                                              # ---- IG-1
    # the cards: numbers from decisions(), text from decision_cards() as drawn
    cur = current_starters(league_id, int(roster_id), house=True)                                         # IB-0
    out["notice"], out["cards"] = cards_from_rows(league_id, roster_id, week, season, rows, current=cur)
    out.update(build_actions(rows, out["cards"], cur, league_id))                                          # ---- IE-1
    out.update({"edit_link": edit_link(league_id), "nothing_submitted": NOTHING_SUBMITTED})               # ---- IE-1
    out["changed"] = what_changed(ctx.meta, rows, cur)                                                     # ---- IF-4
    out["clocks"] = clocks(ctx.meta, out["changed"])                                                      # ---- II-4
    out["lineup"], out["lineup_full"] = lineup(rows)
    annotate_swaps(out["lineup"], out["lineup_full"], out.get("swaps") or [])                              # ---- PO I-E
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
    out["win"] = win(league_id, int(roster_id), season, week, rows, out["opponent"], house=True)          # ---- IH-3
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
    ties = list(drawn_dec["tiebreak"]) if isinstance(drawn_dec, pd.DataFrame) and "tiebreak" in drawn_dec else []  # IE-1
    # ---- IF-4: IF-3's flag (cards.decision_cards' column `matchup_uncertain`; absent = False)
    mus = list(drawn_dec["matchup_uncertain"]) if isinstance(drawn_dec, pd.DataFrame) and "matchup_uncertain" in drawn_dec else []
    # ---- end IF-4
    out = []
    for i, (_, d) in enumerate(dec.iterrows()):
        out.append({
            "slot": d["slot"], "slot_label": cards.slot_label(d["slot"]),
            "gsis_id": _str(d["gsis_id"]), "player_name": d["player_name"], "value": _num(d["value"]),
            "alt_gsis_id": _str(d["alt_gsis_id"]), "alt_name": _str(d["alt_name"]),
            "alt_value": None if _str(d.get("alt_value_source")) == UNVALUED else _num(d["alt_value"]),   # ---- IG-1
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
        # ---- IE-1: the two players' roster keys (Sleeper id / MFL key) and the coin flip's tiebreaker as data
        tb = ties[i] if i < len(ties) and isinstance(ties[i], dict) else None
        out[-1].update({"key": _str(d.get("sleeper_player_id")), "alt_key": _str(d.get("alt_sleeper_player_id")),
                        "tiebreak": None if tb is None else {"kind": tb["kind"], "pick": tb["pick"], "side": tb["side"]},
                        "action": None})
        # ---- end IE-1
        out[-1]["matchup_uncertain"] = i < len(mus) and _num(mus[i]) is not None and bool(mus[i])              # IF-4
    return (notices[0] if notices else None), out


# ---- IE-1 (Wave I-E, the casual-user review § "make the default experience a weekly action list"): My Week's first
# layer. At most three actions, the most urgent first: a change the submitted lineup needs before the next kickoff, then
# a close call (a status breaks the tie), then (the web adds it from /api/waivers' `home_action`) a claim that changes
# this week's starters. Cards that share a player are ONE action ("Keep Addison and Nabers ahead of McConkey for now");
# a clear / lean call the submitted lineup already follows is not an action (the `set_line` says so); a difference
# under ACTION_MIN_GAIN projected points with nobody hurt is not one either. No number moves: the projections, the
# lineup and the cards are the ones below; an action only names who starts and what the submitted lineup still needs.
ACTION_MIN_GAIN = 0.5
MAX_ACTIONS = 3
NOTHING_SUBMITTED = f"{APP_NAME} never changes your lineup or claims; it tells you what to do in your league's app."
SET_ALL = "Your lineup is set — nothing to change."
# ---- IF-4 (the decision-quality review § Priority 4: "No clear upgrade" is more accurate than "nothing to change" when a
# close call exists): the rest is "set" (no tail), and "No clear upgrade elsewhere" when the review lines are shown
SET_REST = "The rest of your lineup is set."
SET_ELSEWHERE = "No clear upgrade elsewhere."
MAX_REVIEW = 3
# ---- end IF-4
CANT_WORDS = {"OUT": "is out", "IR": "is on injured reserve", "PUP": "is on the PUP list", "SUS": "is suspended",
              "DOUBTFUL": "is doubtful", "BYE": "is on a bye"}


def platform_name(league_id: str) -> str:
    from league_lab import platforms
    return "MFL" if platforms.is_mfl(league_id) else "Sleeper"


def edit_link(league_id: str, league: dict | None = None) -> dict:
    """Where the manager changes his lineup: MFL's lineup page on the league's own host (`league["mfl"]["url"]` =
    `<host>/<year>/home/<id>` → `<host>/<year>/options?L=<id>&O=02`, MFL's "Submit lineup"), Sleeper's league."""
    name = platform_name(league_id)
    if name == "MFL":
        lid = str(league_id).split(":", 1)[-1]
        home = str(((league or {}).get("mfl") or {}).get("url") or "")
        base = home.rsplit("/home/", 1)[0] if "/home/" in home else ""
        url = f"{base}/options?L={lid}&O=02" if base else f"https://www.myfantasyleague.com/{ui.current_season()}/home/{lid}"
    else:
        url = f"https://sleeper.com/leagues/{league_id}"
    return {"label": f"Open {name} to edit your lineup", "url": url, "platform": name}


def lock_words(ts) -> str | None:
    """'before Sun 1:00 PM ET' for a kickoff (UTC)."""
    if ts is None or (not isinstance(ts, str) and pd.isna(ts)):
        return None
    t = pd.Timestamp(ts)
    t = (t.tz_localize("UTC") if t.tzinfo is None else t).tz_convert("America/New_York")
    return f"before {t:%a} {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'} ET"


def _and(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def build_actions(rows: pd.DataFrame, cards_out: list[dict], current: dict[str, str] | None, league_id: str) -> dict:
    """{actions, set_line, next_lock, platform_name} from the lineup rows, the cards (`cards_from_rows`, with their
    IE-1 `key` / `alt_key` / `tiebreak`) and the submitted lineup ({key: slot}; None = unknown). Marks each card's
    `action` (the index of the action it explains)."""
    pname = platform_name(league_id)
    res: dict = {"actions": [], "set_line": None, "next_lock": None, "platform_name": pname,
                 "review": []}                                                              # ---- IF-4
    if rows is None or rows.empty:
        return res
    info: dict[str, dict] = {}
    for r in rows.to_dict("records"):
        k = _str(r.get("sleeper_player_id"))
        if k and r.get("role") in ("starter", "bench", "unplayable") and not r.get("is_empty_slot"):
            info[k] = r
    best = [k for k, r in info.items() if r["role"] == "starter"]

    def val(k) -> float:
        return _num((info.get(k) or {}).get("value")) or 0.0

    def plays(k) -> bool:
        return k in info and info[k]["role"] != "unplayable"

    def locked(k) -> bool:
        return bool((info.get(k) or {}).get("locked_now"))

    def status(k) -> str | None:
        r = info.get(k) or {}
        s = _str(r.get("chip")) or cards._flag(r.get("report_status"))
        return s or None

    def name(k, short=True) -> str:
        r = info.get(k) or {}
        full = _str(r.get("player_name")) or "a player no longer on your roster"
        n = cards.last_name(full, r.get("position")) if short and r.get("position") not in ("DEF", "TMQB", "TMPK", "TMDEF") else full
        g = _str(r.get("gsis_id"))
        return f"[{n}](/player/{g})" if g else n

    def plain(k) -> str:
        r = info.get(k) or {}
        full = _str(r.get("player_name")) or "a player no longer on your roster"
        return cards.last_name(full, r.get("position")) if r.get("position") not in ("DEF", "TMQB", "TMPK", "TMDEF") else full

    def cant_words(k) -> str:
        r = info.get(k) or {}
        s = (_str(r.get("chip")) or _str(r.get("report_status")) or "").upper()
        why = str(r.get("reason") or "").lower()
        return CANT_WORDS.get("BYE" if why == "bye" else s, f"can't play ({r.get('reason') or s.lower() or 'not active'})")

    # the groups: cards that share a player (union-find over the keys); the submitted lineup's differences join them
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str | None, b: str | None) -> None:
        if a and b:
            parent[find(a)] = find(b)
        elif a or b:
            find(a or b)
    for c in cards_out:
        union(c.get("key"), c.get("alt_key"))
    # the suggested lineup: the best lineup, except where a coin flip's tiebreaker is an injury (the healthy one starts:
    # "McConkey's questionable status breaks the tie") - the card already says "Go with Addison"
    suggested, swapped = set(best), set()
    res["swaps"] = []           # PO (I-E): the lineup table says the same as the call (annotate_swaps)
    for c in cards_out:
        tb = c.get("tiebreak") or {}
        if tb.get("kind") == "injury" and tb.get("side") == "alt" and c.get("alt_key") and c.get("key") in suggested \
                and c["alt_key"] not in suggested and plays(c["alt_key"]) and not locked(c["key"]):
            suggested.discard(c["key"])
            suggested.add(c["alt_key"])
            swapped.add(c["alt_key"])
            res["swaps"].append({"in": c["alt_key"], "in_name": plain(c["alt_key"]), "out": c["key"], "out_name": plain(c["key"]),
                                 "status": status(c["key"])})
    known = current is not None
    sub = set(current or {})
    if known and best and not (sub & set(info)):
        # nothing of this roster is in the submitted lineup (a new week MFL has no lineup for yet): ONE action, not eight
        kicks = [info[k].get("kickoff_at") for k in best if not locked(k) and info[k].get("kickoff_at") is not None
                 and not pd.isna(info[k].get("kickoff_at"))]
        first = min(kicks) if kicks else None
        lock = None if first is None else {"kickoff": pd.Timestamp(first).isoformat(), "words": lock_words(first)}
        res["actions"] = [{"kind": "change", "urgency": 1, "slots": [], "slot_label": "",
                           "action": f"Set your {pname} lineup: nothing is in it for this week yet.",
                           "reason": "Start the lineup below (the best one by our projection) before the first kickoff.",
                           "start": [{"key": k, "name": plain(k), "link": name(k)} for k in best], "sit": [],
                           "submitted": False, "submitted_words": f"Not in your {pname} lineup yet: set it in {pname}.",
                           "lock": lock, "cards": list(range(len(cards_out))), "gain": None, "href": None}]
        for c in cards_out:
            c["action"] = 0
        res["next_lock"] = None if lock is None else {**lock, "players": []}
        return res
    pairs: list[tuple[str | None, str | None]] = []
    if known:
        ins = sorted((k for k in suggested if k not in sub and not locked(k)), key=lambda k: -val(k))
        outs = sorted((k for k in sub if k not in suggested and not locked(k)), key=lambda k: (plays(k), val(k)))
        for o in outs:
            ok = cards.slot_elig(cards._PART.get(str(current.get(o) or "").upper()) or current.get(o)) if current.get(o) else frozenset()
            pick = next((i for i in ins if ok and (info.get(i) or {}).get("position") in ok), ins[0] if ins else None)
            if pick is not None:
                ins.remove(pick)
            pairs.append((pick, o))
        pairs += [(i, None) for i in ins]
        for i, o in pairs:
            union(i, o)
    groups: dict[str, set[str]] = {}
    for k in list(parent):
        groups.setdefault(find(k), set()).add(k)
    acts, tiny = [], False
    review: list[dict] = []                                                                # ---- IF-4
    for members in groups.values():
        g_cards = [i for i, c in enumerate(cards_out) if c.get("key") in members or c.get("alt_key") in members]
        g_pairs = [p for p in pairs if p[0] in members or p[1] in members]
        start = sorted((k for k in members if k in suggested), key=lambda k: (k not in swapped, -val(k)))
        sit = sorted((k for k in members if k not in suggested), key=lambda k: -val(k))
        submitted = None if not known else (all(k in sub or locked(k) for k in start) and not any(k in sub for k in sit))
        cant = [k for k in sit if k in sub and not plays(k)]
        gain = None if submitted is not False else round(sum(val(k) for k in start if k not in sub)
                                                         - sum(val(k) for k in sit if k in sub and plays(k)), 2)
        coin = [cards_out[i] for i in g_cards if cards_out[i].get("status") == "close" or cards_out[i].get("strength") == "coin flip"]
        hurt = [k for k in members if status(k) and plays(k)]
        if submitted is False and (cant or (gain or 0.0) >= ACTION_MIN_GAIN):
            kind = "change"
        elif coin and hurt:
            kind = "close"
        else:
            tiny = tiny or submitted is False
            review += _review_items(coin, cards_out, sub if known else None, info, name=name, plain=plain)   # ---- IF-4
            continue
        a = _action(kind, start, sit, submitted, gain, cant, coin, hurt, g_pairs, swapped, pname,
                    name=name, plain=plain, status=status, cant_words=cant_words, val=val,
                    slot_of=lambda k: re.sub(r"\s*\d+$", "", cards.slot_label(_str((info.get(k) or {}).get("slot")))))
        # who the action's time hangs on: the swapped pairs, and the close calls (those with the hurt player first: the
        # call between McConkey and Addison is open until Addison's kickoff, whatever time Nabers plays)
        hot = [c for c in coin if c.get("key") in hurt or c.get("alt_key") in hurt] if kind == "close" else coin
        involved = {k for p in g_pairs for k in p if k} | {k for c in (hot or coin) for k in (c.get("key"), c.get("alt_key")) if k}
        kicks = [info[k].get("kickoff_at") for k in involved if k in info and not locked(k)
                 and info[k].get("kickoff_at") is not None and not pd.isna(info[k].get("kickoff_at"))]
        first = min(kicks) if kicks else None
        a["lock"] = None if first is None else {"kickoff": pd.Timestamp(first).isoformat(), "words": lock_words(first)}
        a["_lock_players"] = [plain(k) for k in sorted(involved, key=lambda k: -val(k))]
        named = ({k for p in g_pairs for k in p if k} if kind == "change" and g_pairs else
                 {k for c in coin for k in (c.get("key"), c.get("alt_key")) if k})
        a["slots"] = sorted({str(info[k]["slot"]) for k in (named or members) if k in info and info[k]["role"] == "starter"
                             and isinstance(info[k].get("slot"), str)}, key=str)
        a["slot_label"] = " · ".join(cards.slot_label(s) for s in a["slots"])
        a["cards"] = g_cards
        a["_order"] = (a["urgency"], first if first is not None else pd.Timestamp.max.tz_localize("UTC"), -(gain or 0.0))
        acts.append(a)
    acts.sort(key=lambda a: a.pop("_order"))
    more = acts[MAX_ACTIONS:]
    acts = acts[:MAX_ACTIONS]
    for n, a in enumerate(acts):
        for i in a["cards"]:
            cards_out[i]["action"] = n
    res["actions"] = acts
    # ---- IF-4: the close calls the lineup already follows, kept in view (the most uncertain first)
    review.sort(key=lambda r: (r["margin"] if r["margin"] is not None else 99.0, r["slot"] or ""))
    res["review"] = review[:MAX_REVIEW]
    # ---- end IF-4
    if known:
        if more:
            res["set_line"] = f"{len(more)} more {'change' if len(more) == 1 else 'changes'}: the lineup below shows every slot."
        else:
            res["set_line"] = (SET_ELSEWHERE if review else SET_REST if acts else SET_ALL) + (     # IF-4: SET_ELSEWHERE
                " (Where your lineup differs from ours, it is by less than half a point.)" if tiny else "")
    locks = [(a["lock"]["kickoff"], a) for a in acts if a.get("lock")]
    if locks:
        k, a = min(locks, key=lambda x: x[0])
        res["next_lock"] = {"kickoff": k, "words": a["lock"]["words"], "players": a.pop("_lock_players", [])}
    for a in acts:
        a.pop("_lock_players", None)
    return res


def annotate_swaps(lineup_rows: list[dict], full_rows: list[dict], swaps: list[dict]) -> None:
    """PO (Wave I-E, the casual-user review): when a close call's injury tiebreak keeps the healthy player (the action
    says "Keep Addison ahead of McConkey"), the lineup table below must not read as the opposite — its rows are the
    best lineup on paper, so the two rows say so in words (the numbers stay: the table is still the best lineup)."""
    for sw in swaps or []:
        for rows in (lineup_rows, full_rows):
            for r in rows:
                k = r.get("sleeper_player_id") or r.get("key")
                if k == sw["out"] and r.get("role") == "starter":
                    st = (sw.get("status") or "questionable").lower()
                    r["flag"] = f"{st.capitalize()} — the call above keeps {sw['in_name']} here for now"
                elif k == sw["in"] and r.get("role") == "bench":
                    r["flag"] = f"starts for {sw['out_name']} by the call above"


def _action(kind, start, sit, submitted, gain, cant, coin, hurt, pairs, swapped, pname, *, name, plain, status,
            cant_words, val, slot_of) -> dict:
    """One action's words: layer 1 (`action`, one sentence naming the players) and layer 2 (`reason`: why, who moves,
    what could change it), `submitted_words`."""
    def who(ks):
        return [{"key": k, "name": plain(k), "link": name(k)} for k in ks]
    coin_alt = {}                    # a starter in a coin flip -> the bench player he is level with
    for c in coin:
        for a, b in ((c.get("key"), c.get("alt_key")), (c.get("alt_key"), c.get("key"))):
            if a in start and b in sit and b not in cant:
                coin_alt.setdefault(a, b)
    if kind == "change":
        bits, flips = [], []
        for i, o in pairs:
            alt = coin_alt.get(i) if coin_alt.get(i) not in (None, o) else None
            at = f" at {slot_of(i)}" if i and slot_of(i) else ""
            if i and o:
                bits.append(f"{name(i)}{at}" + (f" (or {name(alt)}: a coin flip)" if alt else "") + f" in place of {name(o)}")
            elif i:
                bits.append(f"{name(i)}{at} (an open spot in your {pname} lineup)")
            elif o:
                bits.append(f"{name(o)} out of your lineup")
            # the close call behind the swap: the starter and his bench double, or the two players swapped
            flips += [c for c in coin if i in (c.get("key"), c.get("alt_key"))
                      and ({c.get("key"), c.get("alt_key")} - {i}) & {alt, o} - {None}]
        if not bits:
            bits = [f"{_and([name(k) for k in start])} ahead of {_and([name(k) for k in sit])}"]
        action = (f"Start {bits[0]}." if len(bits) == 1 else f"Make {len(bits)} changes: " + "; ".join(bits) + ".")
        why = [f"{plain(k)} {cant_words(k)}" for k in cant]
        if gain is not None and gain >= ACTION_MIN_GAIN:
            k = int(round(gain))
            why.append(f"the change is worth about {k} more projected point{'s' if k != 1 else ''} this week" if gain >= 1
                       else "the change is worth about half a point this week")
        reason = (why[0][0].upper() + why[0][1:] + ("; " + "; ".join(why[1:]) if why[1:] else "") + ".") if why else ""
        if flips:
            c = flips[0]
            tb = c.get("tiebreak") or {}
            a, b = plain(c["key"]), plain(c["alt_key"])
            lean = {"matchup": "the matchup", "role": "the role", "line": "the betting line"}.get(tb.get("kind"))
            reason += f" {a} and {b} are level by the projection" + (f"; {lean} leans {tb['pick']}." if lean else ".")
            reason += " Check the news again before kickoff."
        done = f"Not in your {pname} lineup yet: make the change in {pname}."
    else:
        keep = [k for k in start if k in swapped or any(k in (c.get("key"), c.get("alt_key")) for c in coin)]
        verb = "Keep" if submitted else "Start"
        action = f"{verb} {_and([name(k) for k in keep])} ahead of {_and([name(k) for k in sit])} for now."
        margins = sorted(_num(c.get("margin")) or 0.0 for c in coin)
        st_ = [k for k in hurt]
        hurt_words = "; ".join(f"{plain(k)}'s {status(k).lower()} status breaks the tie" for k in st_[:2])
        reason = (f"Their projections are close (within {max(margins):.1f} points); {hurt_words}. "
                  f"Check {'his' if len(st_) == 1 else 'their'} status again before kickoff.")
        done = (f"Already in your {pname} lineup — nothing to change." if submitted else
                f"Not in your {pname} lineup yet: make the change in {pname}." if submitted is False else None)
    return {"kind": kind, "urgency": 1 if kind == "change" else 2, "action": action, "reason": reason.strip(),
            "start": who(start), "sit": who(sit), "submitted": submitted, "submitted_words": done,
            "gain": gain if kind == "change" else None, "href": None}
# ---- end IE-1


# ---- IF-4 (Wave I-F, the decision-quality review § Priority 4 "use clarity to expose the difficult decisions"): a close
# call the submitted lineup already follows stays in view as a "No clear upgrade" line — not an action (nothing to do),
# not "nothing to change" (a correct optimizer output does not remove the uncertainty). One line per coin-flip card with
# nobody hurt in it, naming whom the submitted lineup starts ("our lineup" when it is unknown); IF-3's
# `matchup_uncertain` on the card adds "the matchup rank does not settle it". No number moves: the margin is the card's.
def _review_items(coin: list[dict], cards_out: list[dict], sub: set[str] | None, info: dict[str, dict], *,
                  name, plain) -> list[dict]:
    out = []
    for c in coin:
        k, alt = c.get("key"), c.get("alt_key")
        if not k or not alt or k not in info or alt not in info:
            continue
        if sub is None:
            start, other, whose = k, alt, "our lineup has"
        elif (k in sub) == (alt in sub):
            continue                     # both start (other slots) or neither does: not a choice between the two here
        else:
            start, other = (k, alt) if k in sub else (alt, k)
            whose = "your lineup has"
        slot = _str(c.get("slot")) or _str((info.get(k) or {}).get("slot"))
        label = re.sub(r"\s*\d+$", "", cards.slot_label(slot)) if slot else ""
        margin = _num(c.get("margin"))
        mu = bool(c.get("matchup_uncertain") or (c.get("tiebreak") or {}).get("matchup_uncertain"))
        gap = "level by the projection" if margin is None or margin < 0.05 else f"{margin:.1f} points apart"
        words = (f"{name(other)} or {name(start)}{f' at {label}' if label else ''}: a coin flip, {gap}; {whose} {name(start)}"
                 + ("; the matchup rank does not settle it" if mu else "") + " — no clear upgrade.")

        def who(x: str) -> dict:
            r = info.get(x) or {}
            return {"key": x, "name": plain(x), "link": name(x), "gsis_id": _str(r.get("gsis_id")), "value": _num(r.get("value"))}
        g_a, g_b = (info.get(other) or {}).get("gsis_id"), (info.get(start) or {}).get("gsis_id")
        out.append({"kind": "no_clear_upgrade", "slot": slot, "slot_label": label, "start": who(start), "other": who(other),
                    "margin": margin, "strength": _str(c.get("strength")) or "coin flip", "matchup_uncertain": mu,
                    "words": words, "submitted": None if sub is None else True,
                    "compare": {"a": _str(g_a), "b": _str(g_b)} if _str(g_a) and _str(g_b) else None,
                    "cards": [i for i, x in enumerate(cards_out) if x is c]})
    return out


def margin_comparator(r: pd.Series, rows: pd.DataFrame) -> dict:
    """{margin_vs: the bench player who would replace him (short name) | None, margin_words}: '' words when the row
    has no margin (locked, an empty slot, no value)."""
    if _num(r.get("margin")) is None or bool(r.get("is_empty_slot")) or bool(r.get("locked_now")):
        return {"margin_vs": None, "margin_words": ""}
    try:
        a = cards.alternative(r, rows)
    except (KeyError, TypeError, ValueError):
        return {"margin_vs": None, "margin_words": ""}
    alt = a.get("alt")
    if alt is None:
        return {"margin_vs": None, "margin_words": "no eligible reserve: the slot would be empty"}
    nm = cards.last_name(_str(alt.get("player_name")) or "", alt.get("position"))
    return {"margin_vs": nm, "margin_words": f"over {nm}"}          # (a teammate may slide over: the card says how)


# What changed: the overlay's changes since the morning build (with the feed and the time it was checked) and the news
# of this week's starters from the last 24 hours (the item about him first: news.recent), at most five lines.
MAX_CHANGED = 5
NOTHING_CHANGED = "Nothing has changed since the morning build."


def what_changed(meta: dict | None, rows: pd.DataFrame | None, current: dict[str, str] | None = None) -> dict:
    """{lines: [{kind: status | news, gsis_id, text, source, at, url}], empty}: the week's players = the best lineup's
    starters and whoever the submitted lineup starts (``current``)."""
    lines: list[dict] = []
    at = (meta or {}).get("checked_at")
    cites = (meta or {}).get("cites") or []                                                              # ---- IG-2
    stored = _status_events(cites)                                                                       # ---- IG-2
    for k, text in enumerate((meta or {}).get("changes") or []):
        line = {"kind": "status", "gsis_id": None, "text": str(text), "source": "Injury report (ESPN)", "at": at,
                "url": None}
        line.update(_status_cite(cites[k] if k < len(cites) else {}, stored, at))                       # ---- IG-2
        lines.append(line)
    lines += questionable_lines(meta, rows, current, lines, at)[:max(0, MAX_CHANGED - len(lines))]       # ---- IH-2
    if rows is not None and not rows.empty and len(lines) < MAX_CHANGED:
        sub = set(current or {})
        st_ = rows[((rows["role"] == "starter") | rows["sleeper_player_id"].map(lambda k: isinstance(k, str) and k in sub))
                   & rows["gsis_id"].map(lambda g: isinstance(g, str) and bool(g))]
        names = dict(zip(st_["gsis_id"], st_["player_name"], strict=False))
        from . import news
        items = news.recent(list(names), names=names)
        items = _with_events(items, names)                                                               # ---- IG-2
        for g, it in items:
            if len(lines) >= MAX_CHANGED:
                break
            line = {"kind": "news", "gsis_id": g, "player_name": _str(names.get(g)), "text": it["headline"],
                    "source": it.get("source"), "at": it.get("date"), "url": it.get("url"), "about": it.get("about")}
            if "event_id" in it:                                                                         # ---- IG-2
                line.update({"event_id": it["event_id"], "origin": "playerwire" if it.get("kind") == "playerwire" else "espn",
                             "verification": it.get("verification")})
            lines.append(line)
    return {"lines": decision_feed(lines[:MAX_CHANGED], meta, rows, current), "empty": NOTHING_CHANGED}  # ---- II-4
# ---- end IF-4


# ---- II-4 (Wave I-I; the product and analytics review § 7): "What changed" as a decision-impact feed. Every line keeps
# IF-4 / IG-2 / IH-2's keys and gains five parts (INTERFACES.md § II-4; docs/WORDS.md § "News as a decision feed"):
#   what_changed   — the sourced fact with its times: {text, source, event_at, published_at, checked_at}
#   why_here       — where he is in this roster's week (starts at a slot / in the lineup you submitted / on your bench)
#   decision_status — "changed" (the overlay re-solved the lineup around him), "watch" (a Questionable tag, an injury
#                    item the report has not settled), "none" (no action currently indicated)
#   forecast_status — "included" ONLY with a recorded update: the overlay's recorded status change (availability
#                    `changes`, applied to this week's numbers); "contextual" for news, briefs, recaps and a Questionable
#                    tag (the projection reads no news: IF-3's `forecast_treatment` model — the forecast's inputs are
#                    listed, nothing in them is a headline); "pending" for an injury item published after the last
#                    injury check (the next check may move him)
#   next_step      — inspect the player / compare alternatives (a changed lineup)
# plus `item_kind` ("development" | "recap": a game recap is ranked after every development) and `priority` (1 = most
# urgent); the lines come sorted by it — changed, then watch, then none; developments before recaps; IF-4's order kept
# within (a stable sort). The same event reported twice (one player, one fingerprint or the same headline) shows once.
DECISION_WORDS = {"changed": "Recommendation changed", "watch": "Watch for confirmation",
                  "none": "No action currently indicated"}
FORECAST_WORDS = {"included": "Included in the current projection",
                  "contextual": "Context only: not in the projection",
                  "pending": "Update pending: the next injury check may move his projection"}
INJURY_WORDS = re.compile(r"\b(injur\w*|questionable|doubtful|ruled out|out for|inactive|limited|did not practice|"
                          r"DNP|sidelined|hamstring|ankle|knee|hip|groin|calf|concussion|shoulder|back|foot|toe|"
                          r"illness|IR|injured reserve|game-time decision|week-to-week|day-to-day)\b", re.IGNORECASE)
RECAP_WORDS = re.compile(r"\b(caught|hauled in|rushed|carried|completed|threw for|finished with|totaled|recorded|"
                         r"\d+ (catches|receptions|carries|rushes|yards|touchdowns?))\b.*\b(win|loss|victory|defeat|"
                         r"Sunday|Monday|Thursday|Saturday|game|week \d+)\b", re.IGNORECASE)


def _why_here(g: str | None, rows: pd.DataFrame | None, current: dict[str, str] | None) -> str:
    if not g or rows is None or rows.empty or "gsis_id" not in rows:
        return "Your lineup this week"
    r = rows[rows["gsis_id"] == g]
    if r.empty:
        return "Your lineup this week"
    r = r.iloc[0]
    sid = r.get("sleeper_player_id")
    if r.get("role") == "starter":
        return f"Starts at {cards.slot_label(r.get('slot'))} in your best lineup this week"
    if isinstance(sid, str) and sid in (current or {}):
        if r.get("role") == "unplayable":
            return "In the lineup you submitted, and he cannot play this week"
        return "In the lineup you submitted (not your best lineup)"
    if r.get("role") == "unplayable":
        return "On your roster, unable to play this week"
    return "On your bench this week"


def _item_kind(line: dict) -> str:
    if line.get("kind") != "news":
        return "development"
    return "recap" if RECAP_WORDS.search(str(line.get("text") or "")) and not INJURY_WORDS.search(
        str(line.get("text") or "")) else "development"


def decision_parts(line: dict, meta: dict | None, rows: pd.DataFrame | None, current: dict[str, str] | None,
                   recorded: set | None = None) -> dict:
    """The five parts of one "What changed" line (see the block's head)."""
    from .events import iso
    g = line.get("gsis_id")
    checked = (meta or {}).get("checked_at")
    text = str(line.get("text") or "")
    kind = _item_kind(line)
    status = None
    if g and rows is not None and not rows.empty and "report_status" in rows:
        st = rows.loc[rows["gsis_id"] == g, "report_status"]
        status = st.iloc[0] if not st.empty and isinstance(st.iloc[0], str) else None
    if line.get("kind") == "status" and line.get("flag") == "questionable":
        dec, fc = "watch", "contextual"
        fc_words = "Context only: a Questionable tag does not change the projection"
    elif line.get("kind") == "status":
        # the overlay's own recorded change (availability `changes`): applied to this week's rows and re-solved
        dec = "none" if "the lineup does not change" in text else "changed"
        fc, fc_words = "included", "Included in the current projection: the injury report's status is applied to this week"
    elif kind == "recap":
        dec, fc, fc_words = "none", "contextual", "Context only: a game already played is in his stats, not news"
    else:
        injury = bool(INJURY_WORDS.search(text))
        role = None
        if g and rows is not None and not rows.empty and "role" in rows:
            rl = rows.loc[rows["gsis_id"] == g, "role"]
            role = rl.iloc[0] if not rl.empty else None
        at, chk = iso(line.get("at")), iso(checked)
        if injury and (g in (recorded or set()) or role == "unplayable"):
            # the injury report's status for him is already applied to this week's rows (the overlay's recorded change,
            # or the build's own report): the item is reflected, never counted twice
            dec, fc = "none", "included"
            fc_words = "Included in the current projection: his injury-report status is applied to this week"
        elif injury and at and chk and at > chk:
            dec, fc, fc_words = "watch", "pending", FORECAST_WORDS["pending"]
        else:
            dec = "watch" if injury or status in ("Questionable", "Doubtful") else "none"
            fc, fc_words = "contextual", FORECAST_WORDS["contextual"]
    name = line.get("player_name")
    if not name and g and rows is not None and not rows.empty:
        nm = rows.loc[rows["gsis_id"] == g, "player_name"]
        name = nm.iloc[0] if not nm.empty and isinstance(nm.iloc[0], str) else None
    who = cards.last_name(name) if name else None
    if dec == "changed":
        nxt = {"kind": "compare", "label": "Compare your options for the slot", "gsis_id": g}
    elif g:
        nxt = {"kind": "player", "label": f"Inspect {who}" if who else "Inspect the player", "gsis_id": g}
    else:
        nxt = {"kind": "player", "label": "See your lineup", "gsis_id": None}
    status_line = line.get("kind") == "status"
    return {"what_changed": {"text": text, "source": line.get("source"),
                             "event_at": iso(line.get("at")) if status_line else None,
                             "published_at": None if status_line else iso(line.get("at")),
                             "checked_at": iso(checked)},
            "why_here": _why_here(g, rows, current),
            "decision_status": dec, "decision_words": DECISION_WORDS[dec],
            "forecast_status": fc, "forecast_words": fc_words,
            "next_step": nxt, "item_kind": kind}


def decision_feed(lines: list[dict], meta: dict | None, rows: pd.DataFrame | None,
                  current: dict[str, str] | None) -> list[dict]:
    """The lines with their five parts, deduplicated (one event once) and ranked by decision relevance and urgency."""
    seen: set = set()
    out: list[dict] = []
    recorded = {ln.get("gsis_id") for ln in lines if ln.get("kind") == "status" and ln.get("flag") != "questionable"
                and ln.get("gsis_id")}
    for ln in lines:
        k = ln.get("event_id") or (ln.get("gsis_id"), re.sub(r"\W+", " ", str(ln.get("text") or "")).strip().lower())
        if k in seen:
            continue
        seen.add(k)
        try:
            out.append({**ln, **decision_parts(ln, meta, rows, current, recorded)})
        except Exception:  # noqa: BLE001 - the feed never fails My Week: the line as IF-4 had it
            out.append(ln)
    rank = {"changed": 0, "watch": 1, "none": 2}
    out.sort(key=lambda x: (rank.get(x.get("decision_status"), 2), 1 if x.get("item_kind") == "recap" else 0))
    for i, x in enumerate(out, start=1):
        x["priority"] = i
    return out


def clocks(meta: dict | None, changed: dict | None) -> dict:
    """The home's three stamps, apart (never a stale warning — PO 2026-10-04): the morning build's newest data load, the
    injury report's last check, the newest news item's publication time among the lines."""
    from .events import iso
    news = [iso(x.get("at")) for x in (changed or {}).get("lines") or [] if x.get("kind") == "news" and x.get("at")]
    news = [t for t in news if t]
    return {"data_built": updated_at(), "injuries_checked": iso((meta or {}).get("checked_at")),
            "news": max(news) if news else None}
# ---- end II-4


# ---- IG-2 (Wave I-G): "What changed" reads the event store. A status line cites its own source and the report's time
# (the stored availability event when there is one — with the player's ESPN page — else the overlay entry), not the
# time the feed was checked. The news lines: ESPN's items (news.recent, IF-4's order) and PlayerWire's briefs of the
# last 24 hours (playerwire.recent), each written as an event, merged with the store's live news / brief events of the
# week's players (an item the live read missed this time — ESPN's one-second budget — still shows); one line per player:
# his own brief first, then a brief naming him (N2's order), else ESPN's item; about-him first, newest first. Store off /
# unreachable: IF-4's lines.
def _status_events(cites: list[dict]) -> dict[str, dict]:
    from . import events
    gs = [c.get("gsis_id") for c in cites if c.get("gsis_id")]
    if not gs or not events.enabled():
        return {}
    out: dict[str, dict] = {}
    for ev in events.recent(gs, hours=24 * 60, kinds=("availability",)):      # the report may be weeks old (IR)
        out.setdefault(ev["gsis_id"], ev)
    return out


def _status_cite(c: dict, stored: dict[str, dict], checked_at) -> dict:
    from . import events
    g = c.get("gsis_id")
    ev = stored.get(g) if g else None
    if ev is not None and ev.get("status") == c.get("code"):
        return {"gsis_id": g, "source": f"Injury report ({ev['source']})", "at": ev.get("at"), "url": ev.get("source_url"),
                "event_id": ev.get("id")}
    if not c.get("source"):
        return {"gsis_id": g} if g else {}
    return {"gsis_id": g, "source": f"Injury report ({c['source']})", "at": events.iso(c.get("as_of")) or checked_at}


def _event_item(ev: dict) -> dict:
    brief = ev.get("kind") == "brief"
    return {"headline": ev.get("headline") or "", "date": ev.get("published_at") or ev.get("at"), "source": ev.get("source"),
            "url": ev.get("source_url"), "about": "player" if brief else (ev.get("status") or "player"),
            "kind": "playerwire" if brief else "espn", "verification": ev.get("status") if brief else None,
            "summary": ev.get("summary"), "event_id": ev.get("id")}


def _with_events(items: list[tuple[str, dict]], names: dict[str, str]) -> list[tuple[str, dict]]:
    from . import events, news
    from . import playerwire as PW
    if not events.enabled() or not names:
        return items
    try:
        briefs = PW.recent(list(names), hours=news.RECENT_HOURS) if news.playerwire_enabled() else []
        live = [(g, {**it, "kind": it.get("kind") or "espn"}) for g, it in items] + \
               [(g, {**it, "about": "player"}) for g, it in briefs]                     # N2: a brief is his by id
        for g, it in live:
            events.observe_items(g, [it])
        fp: dict[str, tuple[str, dict]] = {}
        for g, it in live:
            r = events.item_row(g, it)
            if r is not None:
                fp.setdefault(r["fingerprint"], (g, {**it, "event_id": None}))
        for ev in events.recent(list(names), hours=news.RECENT_HOURS, kinds=("news", "brief"), live_only=False):
            if ev.get("fingerprint") in fp:                           # an item shown now: its stored event's id
                fp[ev["fingerprint"]][1]["event_id"] = ev["id"]
            elif ev.get("live") and ev.get("gsis_id") in names:       # the store's own: live events only
                fp[ev["fingerprint"]] = (ev["gsis_id"], _event_item(ev))
        cands = sorted(fp.values(), key=lambda x: x[1].get("date") or "", reverse=True)          # newest first, then
        cands.sort(key=lambda x: (0 if not x[1].get("related") else 1) if x[1].get("kind") == "playerwire"
                   else 2 if x[1].get("about") == "player" else 3)
        best: dict[str, dict] = {}
        for g, it in cands:              # his brief, else a brief naming him, else the item about him, else league news
            best.setdefault(g, it)
        got = list(best.items())
        mine = sorted((x for x in got if x[1].get("about") == "player"), key=lambda x: x[1].get("date") or "", reverse=True)
        rest = sorted((x for x in got if x[1].get("about") != "player"), key=lambda x: x[1].get("date") or "", reverse=True)
        return mine + rest
    except Exception:  # noqa: BLE001 - the store never fails My Week: IF-4's lines
        return items
# ---- end IG-2


# ---- IH-2 (Wave I-H): a Questionable tag that changes no lineup, shown once in "What changed" (IG-2 stored it, IF-4's
# rule showed nothing: the lines were the lineup's moves and the news). A week's player (the best lineup's starters and
# whoever the submitted lineup starts) tagged Questionable gets one line — "Questionable: Jefferson (ankle) — your lineup
# is unchanged" — when the tag is news since the morning build: a live QUESTIONABLE availability event of the last 24
# hours (the store; cited by it), else the overlay's own flag (a copy newer than the build moved him to Questionable;
# cited by the overlay entry). A tag the build already knew (Questionable since last week) is not a change: no line.
# Never a second line for a player who already has one (a "can play again" move); a Questionable never moves a lineup
# (only Out / Doubtful / IR do), so the words can say so.
QUESTIONABLE_TAIL = "your lineup is unchanged"
_NOTE = re.compile(r"\(([^()]{1,60})\)\s*$")


def questionable_lines(meta: dict | None, rows: pd.DataFrame | None, current: dict[str, str] | None,
                       have: list[dict], checked_at) -> list[dict]:
    if rows is None or rows.empty or "report_status" not in rows.columns:
        return []
    sub = set(current or {})
    wk = rows[((rows["role"] == "starter") | rows["sleeper_player_id"].map(lambda k: isinstance(k, str) and k in sub))
              & rows["gsis_id"].map(lambda g: isinstance(g, str) and bool(g))
              & (rows["report_status"] == "Questionable")].drop_duplicates("gsis_id")
    if wk.empty:
        return []
    from . import events, news
    done = {x.get("gsis_id") for x in have if x.get("gsis_id")}
    flags = [str(f) for f in ((meta or {}).get("flags") or [])]
    stored: dict[str, dict] = {}
    if events.enabled():
        for ev in events.recent(list(wk["gsis_id"]), hours=news.RECENT_HOURS, kinds=("availability",)):
            if ev.get("status") == "QUESTIONABLE":
                stored.setdefault(ev["gsis_id"], ev)
    try:
        live = availability.now(list(wk["gsis_id"]))
    except Exception:  # noqa: BLE001 - the note is a nicety
        live = {}
    out: list[dict] = []
    for _, r in wk.iterrows():
        g, name = r["gsis_id"], _str(r.get("player_name")) or "A player"
        if g in done:
            continue
        ev = stored.get(g)
        flagged = any(f.startswith(f"{name} is questionable") for f in flags)
        if ev is None and not flagged:
            continue
        a = live.get(g) or {}
        note = a.get("note")
        if not note and ev is not None:
            m = _NOTE.search(str(ev.get("headline") or ""))
            note = m.group(1) if m else None
        last = cards.last_name(name, _str(r.get("position"))) or name
        line = {"kind": "status", "flag": "questionable", "gsis_id": g, "player_name": name,
                "text": f"Questionable: {last}" + (f" ({note})" if note else "") + f" — {QUESTIONABLE_TAIL}",
                "source": f"Injury report ({a.get('source') or 'ESPN'})", "at": checked_at, "url": None}
        if ev is not None:
            line.update({"source": f"Injury report ({ev['source']})", "at": ev.get("at"), "url": ev.get("source_url"),
                         "event_id": ev.get("id")})
        elif a.get("as_of"):
            from .events import iso
            line["at"] = iso(a.get("as_of")) or checked_at
        out.append(line)
        done.add(g)
    return out
# ---- end IH-2


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
    return {"freshness": caption, "warning": warning, "updated_at": updated_at()}      # ---- IF-4: updated_at


# ---- IF-4 (the I-E review's leftover: "Updated 2:51 PM ET", the exact time on tap, the feed names in the details): the
# newest load of the data the screens read (the morning build's sources), ISO UTC; None when nothing was recorded
UPDATED_SQL = "select max(last_loaded_at) as t from analytics.mart_data_status"


def updated_at() -> str | None:
    try:
        df = query(UPDATED_SQL)
    except Exception:  # noqa: BLE001 - a status line, never a failure
        return None
    if df.empty or df["t"].iloc[0] is None or pd.isna(df["t"].iloc[0]):
        return None
    return pd.Timestamp(df["t"].iloc[0]).tz_convert("UTC").isoformat() if pd.Timestamp(df["t"].iloc[0]).tzinfo else \
        pd.Timestamp(df["t"].iloc[0]).tz_localize("UTC").isoformat()
# ---- end IF-4


# ---- IH-3 (Wave I-H; the decision-quality review § "The analytics worth building next" item 5, the game objective as
# information): `win` on My Week — how often my starters outscore the opponent's this week, from both lineups' ranges
# (`league_lab.decisions.lineup_win_probability`), the expected totals and one line of words. It describes the week;
# it never chooses a player (the cards decide on expected points, and "underdog" is not an instruction to chase
# ceilings). A starter's game is "in" once the nightly has scored it (his NFL team has rows in fct_player_game_league
# for the week): his points are then Sleeper's own (`league_player_week.points_observed`, the league's scoring; a
# starter who did not play scores 0); a game in progress still counts as his range.
WIN_NO_RANGE = "no range for this league yet"
WIN_NO_LIVE = "the week has started and this league's live scores are not read yet"
WIN_EARLY = False            # True: the line says "early: N weeks graded" instead of a percentage (see METRICS § Win probability)
WIN_GRADED_WEEKS = 2         # the 2026 weeks the calibration graded (METRICS § Win probability — the week): 1-2
MIN_RANGED_SHARE = 0.5       # fewer of a side's expected points carried by ranges than this: no probability
SCORED_TEAMS_SQL = """select distinct team from analytics.fct_player_game_league
                      where season = %s and week = %s and season_type = 'REG' and team is not null"""
OBSERVED_SQL = """select sleeper_player_id, points_observed as points from analytics.league_player_week
                  where league_id = %s and season = %s and week = %s and roster_id = any(%s) and sleeper_player_id is not null"""


def win_starters(rows: pd.DataFrame | None) -> list[dict]:
    """The starters of a lineup frame (`cards.lineup_rows`' shape) as `lineup_win_probability` reads them; empty slots
    are left out (they score nothing)."""
    if rows is None or rows.empty:
        return []
    st = rows[(rows["role"] == "starter") & ~rows["is_empty_slot"].fillna(False).astype(bool)]
    out = []
    for _, r in st.iterrows():
        key = _str(r.get("gsis_id")) or _str(r.get("sleeper_player_id")) or _str(r.get("player_name"))
        out.append({"key": key, "sleeper_player_id": _str(r.get("sleeper_player_id")), "position": _str(r.get("position")),
                    "team": _str(r.get("team")), "opponent": _str(r.get("opponent")), "value": _num(r.get("value")),
                    **{q: _num(r.get(q)) for q in ("p10", "p25", "p50", "p75", "p90")}, "actual": None})
    return out


def scored_teams(season: int, week: int) -> set[str]:
    try:
        df = query(SCORED_TEAMS_SQL, (int(season), int(week)))
    except Exception:  # noqa: BLE001 - a missing table on a fresh copy: nobody has played
        return set()
    return {str(t) for t in df["team"]} if not df.empty else set()


def _team_code(t: str | None) -> str | None:
    return {"LAR": "LA", "JAC": "JAX", "WSH": "WAS"}.get(t, t) if t else t


def with_actuals(starters: list[dict], scored: set[str], points: dict[str, float] | None) -> bool:
    """Set ``actual`` on every starter whose team's game is in (``points``: Sleeper id -> his points this week; a
    starter missing from it scored 0). Returns False when a game is in but the league's points are unknown (None)."""
    if not scored:
        return True
    for s in starters:
        if _team_code(s.get("team")) not in scored:
            continue
        if points is None:
            return False
        s["actual"] = float(points.get(s.get("sleeper_player_id") or "", 0.0) or 0.0)
    return True


def week_line(w: dict) -> str | None:
    """"You're a slight favorite this week: 58%, 121 to 117 expected." (+ "2 of your 9 have played, 3 of theirs.")"""
    if w.get("p") is None:
        return None
    mine, theirs = f"{w['mine']:.0f}", f"{w['theirs']:.0f}"
    if w.get("early"):
        head = f"Early: {WIN_GRADED_WEEKS} weeks graded — {mine} to {theirs} expected."
    elif w["words"] == "a coin flip":
        head = f"This week is a coin flip: {w['percent']}%, {mine} to {theirs} expected."
    else:
        head = f"You're {w['words']} this week: {w['percent']}%, {mine} to {theirs} expected."
    return f"{head} {w['played_words']}." if w.get("played_words") else head


def played_words(r: dict) -> str | None:
    if not r.get("n_played") and not r.get("opp_n_played"):
        return None
    return f"{r['n_played']} of your {r['n_starters']} have played, {r['opp_n_played']} of theirs"


def win_answer(mine: list[dict], theirs: list[dict], opponent_roster_id: int | None) -> dict:
    """The `win` object for one opponent (INTERFACES.md § IH-3)."""
    from league_lab import decisions as D

    base = {"opponent_roster_id": opponent_roster_id, "p": None, "percent": None, "words": None, "side": None,
            "line": None, "note": None, "assumptions": D.WEEK_ASSUMPTIONS, "early": WIN_EARLY, "played_words": None}

    def ranged_share(side: list[dict]) -> float:
        tot = sum(abs(s["value"] or 0.0) for s in side if s["actual"] is None)
        rng = sum(abs(s["value"] or 0.0) for s in side if s["actual"] is None and s.get("p10") is not None and s.get("p90") is not None)
        return 1.0 if tot == 0 else rng / tot

    if not mine or not theirs or min(ranged_share(mine), ranged_share(theirs)) < MIN_RANGED_SHARE:
        return {**base, "note": WIN_NO_RANGE}
    r = D.lineup_win_probability(mine, theirs)
    out = {**base, **{k: r[k] for k in ("mine", "theirs", "n_played", "n_starters", "opp_n_played", "opp_n_starters",
                                         "n_no_range", "opp_n_no_range")}}
    if r["p"] is None:
        return {**out, "note": WIN_NO_RANGE}
    p = float(r["p"])
    pct = D.percent(p)
    words = D.week_words(pct / 100)        # the words of the percent printed beside them (64.96% is "65%": clear)
    out.update({"p": round(p, 4), "percent": pct, "words": words,
                "side": "even" if words == "a coin flip" else ("favorite" if p > 0.5 else "underdog"),
                "played_words": played_words(r)})
    out["line"] = week_line(out)
    return out


def win(league_id: str, roster_id: int, season: int, week: int, rows: pd.DataFrame | None, opp: dict | None, *,
        house: bool, points_fn=None, context_fn=None) -> dict | None:
    """`win` on My Week: None without an opponent; one object per opponent (a double header's second in ``also``).
    ``points_fn(roster_ids) -> {Sleeper id: points} | None`` reads the week's points for the on-demand path (None: not
    known, e.g. an MFL league); the database path reads `league_player_week`. ``context_fn(roster_id)`` = the
    opponent's roster context (default `availability.roster_context`, the same rows his total on the page comes from)."""
    if opp is None:
        return None
    opps = [opp, *(opp.get("also") or [])]
    context_fn = context_fn or (lambda rid: availability.roster_context(league_id, int(rid), week, house=house))
    try:
        ctxs = {int(o["roster_id"]): context_fn(int(o["roster_id"])) for o in opps}
    except Exception:  # noqa: BLE001 - the opponent is a nicety: his rows not readable leaves the line out
        return None
    scored = scored_teams(season, week)
    rids = [int(roster_id), *ctxs]
    points: dict[str, float] | None = {}
    if scored:
        if house:
            df = query(OBSERVED_SQL, (league_id, int(season), int(week), rids))
            points = {str(r.sleeper_player_id): float(r.points) for r in df.itertuples() if r.points is not None and not pd.isna(r.points)}
        else:
            points = points_fn(rids) if points_fn is not None else None
        points = points or None            # no points at all for the week (the league's load failed): unknown, not 0
    mine = win_starters(rows)
    live_ok = with_actuals(mine, scored, points)
    answers = []
    for o in opps:
        oc = ctxs.get(int(o["roster_id"]))
        theirs = win_starters(oc.rows if oc is not None else None)
        ok = live_ok and with_actuals(theirs, scored, points)
        if not ok:
            answers.append({"opponent_roster_id": int(o["roster_id"]), "p": None, "line": None, "note": WIN_NO_LIVE,
                            "early": WIN_EARLY})
            continue
        answers.append(win_answer(mine, theirs, int(o["roster_id"])))
    head = answers[0]
    if len(answers) > 1:
        head["also"] = answers[1:]
    return head


MATCHUPS_DB_SQL = """select matchup_id, roster_id from analytics.fct_league_matchup
                     where league_id = %s and season = %s and week = %s and matchup_id is not null"""


def week_odds(league_id: str, *, house: bool | None = None) -> dict:
    """The League screen: this week's games, each with both teams' chance (a's p, b's 1 - p) and expected totals —
    every roster's context read side by side (the house path: one query each; on demand: one solve each, ~1-3 s cold,
    so the screen asks for it after it shows). Games from Sleeper's matchups call (MFL's schedule), else the nightly's
    fct_league_matchup; a double header's games each once."""
    from league_lab import anyleague as A
    from league_lab import decisions as D

    from .ondemand import week_points

    league_id = str(league_id)
    house = known_league(league_id) if house is None else bool(house)
    client = A.sleeper()
    season = int(cards.league_season(league_id)) if house else int(client.league(A.check_id(league_id))["season"])
    week = cards.decision_week(season)
    out: dict = {"league_id": league_id, "season": season, "week": week, "games": [], "assumptions": D.WEEK_ASSUMPTIONS,
                 "note": None}
    if week is None:
        return out
    try:
        ms = client.matchups(league_id, int(week))
    except (A.SleeperBusy, A.SleeperUnavailable):
        ms = []
    if not ms and house:
        ms = query(MATCHUPS_DB_SQL, (league_id, int(season), int(week))).to_dict("records")
    by: dict = {}
    for m in ms or []:
        if m.get("matchup_id") is not None and m.get("roster_id") is not None:
            by.setdefault(int(m["matchup_id"]), []).append(int(m["roster_id"]))
    pairs = [(mid, sorted(set(r))) for mid, r in sorted(by.items()) if len(set(r)) == 2]
    if not pairs:
        return out
    rids = sorted({r for _, pr in pairs for r in pr})
    if house:
        ctxs = availability.contexts(league_id, rids, week, house=True)
    else:
        ctxs = {r: availability.roster_context(league_id, r, week, house=False, client=client) for r in rids}
    scored = scored_teams(season, week)
    points: dict[str, float] | None = {}
    if scored:
        if house:
            df = query(OBSERVED_SQL, (league_id, int(season), int(week), rids))
            points = {str(r.sleeper_player_id): float(r.points) for r in df.itertuples() if r.points is not None and not pd.isna(r.points)}
        else:
            points = week_points(client, league_id, week, rids)
        points = points or None            # no points at all for the week: unknown, not 0
    names = {int(r["roster_id"]): r["team_name"] for r in rosters(league_id)} if house else {
        int(k): v.get("team_name") for k, v in A.team_names(client.rosters(league_id), client.users(league_id)).items()}
    starters = {}
    live_ok = True
    for r in rids:
        c = ctxs.get(r)
        starters[r] = win_starters(c.rows if c is not None else None)
        live_ok = with_actuals(starters[r], scored, points) and live_ok
    for mid, (a, b) in pairs:
        side = {"a": {"roster_id": a, "team_name": names.get(a)}, "b": {"roster_id": b, "team_name": names.get(b)}}
        g = {"matchup_id": mid, **side, "p": None, "words": None, "note": None}
        if not live_ok:
            g["note"] = WIN_NO_LIVE
        else:
            w = win_answer(starters[a], starters[b], b)
            g["note"] = w.get("note")
            if w.get("p") is not None:
                p = float(w["p"])
                g["p"] = round(p, 4)
                g["a"].update({"percent": D.percent(p), "expected": w["mine"], "n_played": w["n_played"]})
                g["b"].update({"percent": 100 - D.percent(p), "expected": w["theirs"], "n_played": w["opp_n_played"]})
                g["words"] = w["words"].replace("underdog", "favorite")          # read from the favourite's side
                g["favorite"] = None if w["words"] == "a coin flip" else (a if p > 0.5 else b)
        out["games"].append(g)
    if out["games"] and all(g["p"] is None for g in out["games"]):
        out["note"] = out["games"][0]["note"]
    return out
# ---- end IH-3
