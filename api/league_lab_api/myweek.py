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
    return {"role": r["role"], "slot": r["slot"], "player_name": _str(r.get("player_name")),
            "gsis_id": _str(r.get("gsis_id")), "position": _str(r.get("position")),
            "value": _num(r.get("value")), "margin": _num(r.get("margin")), "flag": _str(r.get("flag")) or ""}


def lineup(rows: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """(the four-column table: cards.lineup_frame, the full list: + bench and can't-play rows, as
    cards.lineup_table(full=True) builds them — that function draws the table itself, so its six lines are mirrored)."""
    if rows is None or rows.empty:
        return [], []
    lu = cards.lineup_frame(rows)
    short = [_lineup_row(r) for _, r in lu.iterrows()]
    rest = rows[rows["role"] != "starter"].copy()
    if not rest.empty:
        rest["slot"] = rest.apply(lambda r: f"Bench {int(r['bench_rank'])}" if r["role"] == "bench" and pd.notna(r["bench_rank"])
                                  else "Can't play", axis=1)
        rest["flag"] = rest.apply(lambda r: r["reason"] if r["role"] == "unplayable" else ("locked (game started)" if r["locked_now"]
                                  else cards._flag(r["report_status"])), axis=1)
    full = short + [_lineup_row(r) for _, r in rest.iterrows()]
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
                 "record": None, "opponent": None, "summary": f"**{me['team_name']}**", "league_line": "",
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
    rows = cards.lineup_rows(league_id, season, week, roster_id)
    bits = [f"**{me['team_name']}**"]
    if not prof.empty and pd.notna(prof.iloc[0]["wins"]):
        r = prof.iloc[0]
        out["record"] = {"wins": int(r["wins"]), "losses": int(r["losses"]), "standing": int(r["standing"])}
        bits.append(f"{int(r['wins'])}-{int(r['losses'])}, #{int(r['standing'])} in the league")
    if not opp.empty and isinstance(opp.iloc[0]["opponent"], str):
        out["opponent"] = opp.iloc[0]["opponent"]
        bits.append(f"week {week} vs **{opp.iloc[0]['opponent']}**")
    out["summary"] = " · ".join(bits)
    # ---- end of the copy
    if not rows.empty:
        out["league_line"] = cards.league_line(league_id, roster_id, week, rows)
        lv = rows.loc[rows["role"] == "starter", "lineup_value"].dropna()
        out["lineup_value"] = None if lv.empty else float(lv.iloc[0])
    # the cards: numbers from decisions(), text from decision_cards() as drawn
    dec = cards.decisions(rows, 3) if not rows.empty else pd.DataFrame()
    _, calls = capture(cards.decision_cards, league_id, roster_id, week, season, rows=rows)
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
    out["notice"] = notices[0] if notices else None
    for i, (_, d) in enumerate(dec.iterrows()):
        out["cards"].append({
            "slot": d["slot"], "slot_label": cards.slot_label(d["slot"]),
            "gsis_id": _str(d["gsis_id"]), "player_name": d["player_name"], "value": _num(d["value"]),
            "alt_gsis_id": _str(d["alt_gsis_id"]), "alt_name": _str(d["alt_name"]), "alt_value": _num(d["alt_value"]),
            "margin": _num(d["margin"]), "verdict": d["verdict"], "how": d["how"],
            "blocks": blocks(drawn[i]) if i < len(drawn) else [],
        })
    out["lineup"], out["lineup_full"] = lineup(rows)
    _, how = capture(cards.howto_cards)
    out["howto"] = next((links(c[1][0]) for c in how if c[0] == "markdown" and c[1]), None)
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


def status() -> dict:
    """The freshness line and the stale-injury warning every page shows (ui.freshness_banner, captured)."""
    _, calls = capture(ui.freshness_banner)
    caption = next((c[1][0] for c in calls if c[0] == "caption" and c[1]), "")
    warning = next((c[1][0] for c in calls if c[0] == "warning" and c[1]), None)
    return {"freshness": caption, "warning": warning}
