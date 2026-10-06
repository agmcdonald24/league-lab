"""Matchups for everyone (Wave I-N, IN-3): the week's matchup context of every player, and the board.

* ``matchup_context(season, week, gsis_ids=None)`` — gsis_id -> the defense against his position and, for a wide
  receiver, the cornerback call, with one tone for the two together and one sentence a screen prints as it is.
  **Scoring-free**: the defense read is ``mart_defense_vs_position_current``'s standard rank (one scale for every
  league), the corner read is ``mart_cb_matchups`` with ``mart_cb_rankings``' quarter (``research.cb_meaning``). Cheap:
  a handful of cached queries for the whole week, the answer kept per (season, week) in the memory budget's
  ``matchup_board`` region. Never raises: a missing mart, a week with no games or any failure gives ``{}``. DFS (IN-4)
  and the home (IN-1) read it.
* ``board(league, …)`` — ``GET /api/matchups/board``: every player at a position with a game this week, his projection
  and range in the league's scoring, and the context above; search by name, filter by game and tone, sort, paged.

**The one tone** (``combine_tone``; docs/METRICS.md § "Matchups for everyone"). The defense read is the base; the corner
read can only confirm it, move a neutral one, or cancel an opposite one — and only when the call is *likely* (his
located targets lean 15+ points to one side). An *unclear* call (either outside corner) or no call never moves it, a
"solid" corner (the middle half) never moves it, and without a defense read there is no tone (unknown is not neutral):

    defense \\ likely corner   favorable    neutral     difficult    unclear / no call / unranked
    favorable                 favorable    favorable   neutral      favorable
    neutral                   favorable    neutral     difficult    neutral
    difficult                 neutral      difficult   difficult    difficult
    none                      none         none        none         none

**What is in the projection** (``IN_PROJECTION``, asserted against ``league_lab.projections.BASE_FEATURES`` by
api/tests/test_in3.py): the points the defense has allowed to his position (season, last 4 games, its rank, against the
league's average) and the betting lines are inputs; who plays cornerback is not. The corner calls are a lean from where
his targets go, checked on 2025 for which corner draws his targets (docs/METRICS.md § Cornerback matchups) — whether a
tough corner lowers his points has not been graded.
"""

from __future__ import annotations

import copy
import re

import numpy as np
import pandas as pd
from fastapi import APIRouter, Response
from league_lab import memo

from . import refleague
from . import research as R
from .applib import cards
from .db import missing_relations, query

router = APIRouter()

TONES = ("favorable", "neutral", "difficult")
POSITIONS = ("WR", "TE", "RB", "QB")
SORTS = ("projection", "tone", "corner")
MAX_LIMIT, DEFAULT_LIMIT = 100, 25
Q_MIN, Q_MAX = 2, 40
GAME_ID = re.compile(r"^\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}$")
NAME_CHARS = re.compile(r"^(?:[^\W\d_]|[ .'\-])+$")     # what a player's name is made of: anything else (%, _, digits) matches nobody
TONE_ORDER = {"favorable": 0, "neutral": 1, "difficult": 2}
CONTEXT_TTL_S = 600.0
# ---- the memory budget (docs/DEPLOY.md § Memory): one region. Keys: ("ctx", season, week) — the week's context, ~600
# players, ~0.5 MB; ("board", <research._ctx_key>, season, week) — one league scoring's week frame (~600 rows, ~0.2 MB);
# ("pers", season, week) — the corners now of every defense (~30 KB). Seasons and weeks come from the decision week (no
# user input); league keys are the research memo's keys (a house league, or a scoring). At most 24 entries.
_cache = memo.region("matchup_board", ttl=CONTEXT_TTL_S, max_entries=24)

IN_PROJECTION = ("opp_allowed_std", "opp_allowed_l4", "opp_rank_std", "f_opp_allowed_diff", "league_allowed_avg")
PROJECTION_WORDS = ("What the projection counts: the points each defense has allowed to the position (this season, the "
                    "last 4 games and its rank) and the betting lines. Who plays cornerback is not in it: the corner "
                    "call is context, a lean from where his targets go. Whether a tough corner lowers a receiver's "
                    "points has not been graded yet.")
TONE_WORDS = ("Matchup = the defense against his position (favorable: one of the 10 that give up the most; difficult: one "
              "of the 10 that give up the fewest), moved by the cornerback only when the call is likely: a shutdown "
              "corner turns neutral into difficult, an easy one turns it favorable, and a corner against the defense's "
              "read makes it neutral. An unclear call never moves it.")
POSITION_NOTE = {"TE": "Tight ends get the defense against the position only: they mostly draw linebackers and safeties.",
                 "RB": "Running backs get the defense against the position only: no cornerback call.",
                 "QB": "Quarterbacks get the defense against the position only: no cornerback call."}


# ------------------------------------------------------------------------------------------------------- the tone
def combine_tone(defense: str | None, corner: str | None, certainty: str | None) -> str | None:
    """The one-word read of the two together (the table in the module's docstring)."""
    if defense not in TONES:
        return None
    if certainty != "likely" or corner not in ("favorable", "difficult"):
        return defense
    if defense == "neutral" or defense == corner:
        return corner
    return "neutral"                                   # the two reads point opposite ways: they cancel


# ------------------------------------------------------------------------------------------------------- the reads
WEEK_SQL = """select distinct on (p.gsis_id) p.gsis_id, p.position, p.team, p.player_name, p.report_status
              from analytics.mart_player_week_projections p
              where p.season = %s and p.week = %s and p.gsis_id is not null and p.position = any(%s)
              order by p.gsis_id, p.is_reference_league desc, p.league_id"""
GAMES_SQL = """select game_id, home_team, away_team, kickoff_at from analytics.dim_game
               where season = %s and week = %s and season_type = 'REG' order by kickoff_at, game_id"""
DEFENSE_SQL = """select defense, position, games, through_week, points_allowed_per_game_std, rank_std
                 from analytics.mart_defense_vs_position_current where season = %s and position = any(%s)"""
CB_SQL = "select * from analytics.mart_cb_matchups where season = %s and week = %s and position = 'WR'"


def _games(season: int, week: int) -> pd.DataFrame:
    """One row per team with a game: team, opponent, is_home, kickoff_at, game_id."""
    g = query(GAMES_SQL, (int(season), int(week)))
    if g.empty:
        return pd.DataFrame(columns=["team", "opponent", "is_home", "kickoff_at", "game_id"])
    home = g.rename(columns={"home_team": "team", "away_team": "opponent"}).assign(is_home=True)
    away = g.rename(columns={"away_team": "team", "home_team": "opponent"}).assign(is_home=False)
    return pd.concat([home, away], ignore_index=True)[["team", "opponent", "is_home", "kickoff_at", "game_id"]]


def _defense(season: int) -> dict[tuple[str, str], dict]:
    """(defense, position) -> tone, tough_rank, n_ranked, words (research.defense_meaning on the reference mart)."""
    d = query(DEFENSE_SQL, (int(season), list(POSITIONS)))
    if d.empty:
        return {}
    d = R.defense_meaning(d.assign(rank_l4=np.nan))
    out = {}
    for r in d.to_dict("records"):
        k = R._rank(r.get("tough_rank"))
        n = R._rank(r.get("n_ranked"))
        out[(r["defense"], r["position"])] = {
            "tone": r.get("tone") if r.get("tone") in TONES else None, "tough_rank": k, "n_ranked": n or None,
            "words": f"{R._place(r['defense'])} {r['rank_words']}" if isinstance(r.get("rank_words"), str) else None}
    return out


def _corner_read(r: dict) -> dict:
    """A wide receiver's cornerback call in the interface's shape (+ the detail the board shows)."""
    m = R.cb_meaning(r)
    named = m["named_corners"]
    first = named[0] if named else None
    shutdown = bool(named) and all(c.get("label") == "shutdown" and c.get("rank") is not None for c in named)
    n = R._rank(r.get("cb_n_ranked"))

    def who(c: dict) -> str:
        return str(c.get("name") or "an unnamed corner")

    if m["certainty"] == "likely" and first is not None:
        ranked = first.get("rank") is not None
        words = (f"{who(first)} is likely across from him: {first['words']}" if ranked
                 else f"{who(first)} is likely across from him: unranked (too few snaps to rank)")
        if shutdown:
            words += " (a shutdown corner)"
    elif m["certainty"] == "unclear" and named:
        names = " or ".join(f"{who(c)} ({c['words']})" if c.get("rank") is not None else f"{who(c)} (unranked)"
                            for c in named)
        words = f"either {names} could be across from him: his targets split about evenly"
    else:
        words = "no corner call: " + str(m["certainty_words"]).split(": ", 1)[-1]
    ctx = {"tone": m["tone"] if m["tone"] in TONES else None, "certainty": m["certainty"],
           "corner": first.get("name") if first else None, "corner_rank": first.get("rank") if first else None,
           "shutdown": shutdown, "words": words}
    detail = {"n_ranked": n, "certainty_words": m["certainty_words"], "history": m["history"],
              "named": [{"name": c.get("name"), "side": c.get("side"), "rank": c.get("rank"), "label": c.get("label"),
                         "words": c.get("words"), "tone": c.get("tone")} for c in named]}
    return {"ctx": ctx, "detail": detail}


def _sentence(defense: dict, cb: dict | None, tone: str | None) -> str | None:
    d = defense.get("words")
    if cb is None:
        return f"{d}." if d else None
    c = cb["words"]
    if not d:
        return f"{c[0].upper()}{c[1:]}."
    joint = ", but " if {defense.get("tone"), cb.get("tone")} == {"favorable", "difficult"} and cb["certainty"] == "likely" \
        else "; "
    return f"{d}{joint}{c}."


def _week_frame(season: int, week: int) -> dict | None:
    """The cached week: {"rows": {gsis_id: context}, "detail": {gsis_id: corner detail}, "frame": players, "games"}."""
    key = ("ctx", int(season), int(week))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    if missing_relations(("mart_player_week_projections", "dim_game", "mart_defense_vs_position_current")):
        return None
    games = _games(season, week)
    if games.empty:
        return None
    players = query(WEEK_SQL, (int(season), int(week), list(POSITIONS)))
    cbm = (query(CB_SQL, (int(season), int(week)))
           if not missing_relations(("mart_cb_matchups", "mart_cb_rankings")) else pd.DataFrame())
    cb_of = {r["gsis_id"]: r for r in R._records(cbm)} if not cbm.empty else {}
    # a receiver the cornerback mart lists with this week's team, even without a projection row, keeps his team
    if cb_of:
        extra = [{"gsis_id": g, "position": "WR", "team": r.get("team"), "player_name": r.get("player_name"),
                  "report_status": None} for g, r in cb_of.items() if g not in set(players["gsis_id"])]
        if extra:
            players = pd.concat([players, pd.DataFrame(extra)], ignore_index=True)
    frame = players.merge(games, on="team", how="inner")
    defense = _defense(season)
    rows: dict[str, dict] = {}
    detail: dict[str, dict] = {}
    for p in frame.to_dict("records"):
        g, pos, opp = p["gsis_id"], p["position"], p["opponent"]
        dread = dict(defense.get((opp, pos)) or {"tone": None, "tough_rank": None, "n_ranked": None, "words": None})
        cb = None
        if pos == "WR":
            r = cb_of.get(g)
            if r is not None and r.get("opponent") == opp:
                read = _corner_read(r)
                cb, detail[g] = read["ctx"], read["detail"]
            else:
                cb = {"tone": None, "certainty": "no call", "corner": None, "corner_rank": None, "shutdown": False,
                      "words": "no corner call: no depth chart for this game yet"}
        tone = combine_tone(dread["tone"], cb["tone"] if cb else None, cb["certainty"] if cb else None)
        rows[g] = {"opponent": opp, "home": None if pd.isna(p["is_home"]) else bool(p["is_home"]),
                   "defense": dread, "cb": cb, "tone": tone, "words": _sentence(dread, cb, tone)}
    out = {"rows": rows, "detail": detail, "frame": frame, "games": games}
    _cache.put(key, out)
    return out


def matchup_context(season: int, week: int, gsis_ids: list[str] | None = None) -> dict[str, dict]:
    """gsis_id -> {"opponent": "KC", "home": bool | None,
                   "defense": {"tone": "favorable" | "neutral" | "difficult" | None, "tough_rank": int | None,
                               "n_ranked": int | None, "words": str | None},          # defense vs his position
                   "cb": {"tone": same | None, "certainty": "likely" | "unclear" | "no call",
                          "corner": str | None, "corner_rank": int | None, "shutdown": bool,
                          "words": str | None} | None,                               # wide receivers only
                   "tone": same | None,          # the one-word read of the two together (combine_tone)
                   "words": str | None}          # one sentence a screen can print as it is

    Every QB / RB / WR / TE with a game in ``week`` (the week's projection rows, plus every receiver the cornerback mart
    lists) — or only ``gsis_ids``. Scoring-free (the marts' standard ranks: ``tough_rank`` 1 = the defense that gives up
    the fewest points to the position; ``corner_rank`` 1 = the corner hardest to throw on). **The tone**: the defense's,
    moved by the corner only on a likely call — a likely shutdown corner (difficult) or an easy one (favorable) moves a
    neutral defense to its side, confirms the same side, and cancels the opposite side to neutral; an unclear call, no
    call, a solid or unranked corner never moves it; no defense read, no tone. A player on a bye is absent. Never raises:
    a missing mart or week gives {}."""
    try:
        wk = _week_frame(int(season), int(week))
        if wk is None:
            return {}
        rows = wk["rows"]
        ids = rows.keys() if gsis_ids is None else [str(g) for g in gsis_ids if str(g) in rows]
        return {g: copy.deepcopy(rows[g]) for g in ids}
    except Exception:  # noqa: BLE001 - context is never load-bearing for its readers (the interface: never raises)
        return {}


# ------------------------------------------------------------------------------------------------------- the board
class Bad(R.BadRequest):
    pass


def _param_position(position: str | None) -> str:
    p = (position or "WR").strip().upper()
    if p not in POSITIONS:
        raise Bad("position is WR, TE, RB or QB.")
    return p


def _param_q(q: str | None) -> str | None:
    if q is None or not q.strip():
        return None
    s = q.strip()
    if len(s) < Q_MIN:
        raise Bad("Type at least 2 letters of a name.")
    if len(s) > Q_MAX:
        raise Bad("A name is at most 40 characters.")
    return s


def _param_choice(v: str | None, allowed: tuple[str, ...], what: str, default: str | None) -> str | None:
    s = (v or "").strip().lower()
    if not s or s == "all":
        return default
    if s not in allowed:
        raise Bad(f"{what} is {', '.join(allowed)}.")
    return s


def _week_rows(ctx: R.Ctx, season: int, week: int, wk: dict) -> pd.DataFrame:
    """Every player with a game this week and a projection in this league's scoring: name, team, game, projection and
    range, and the context's sort keys (cached per league scoring and week)."""
    key = ("board", R._ctx_key(ctx), int(season), int(week))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    frame = wk["frame"]
    ids = sorted(set(frame["gsis_id"]))
    pj = R.projections(ctx, week, ids)
    df = frame.merge(pj, on="gsis_id", how="inner")
    df = df[df["proj_points"].notna()]
    dim = query(R.DIM_SQL, (sorted(set(df["gsis_id"])),)) if not df.empty else pd.DataFrame(
        columns=["gsis_id", "dim_player_name", "dim_position", "dim_team", "headshot_url"])
    df = df.merge(dim[["gsis_id", "dim_player_name", "headshot_url"]], on="gsis_id", how="left")
    df["player_name"] = df["dim_player_name"].where(df["dim_player_name"].notna(), df["player_name"])
    df = df.drop(columns=["dim_player_name"])
    rows = wk["rows"]
    df["tone"] = [rows[g]["tone"] for g in df["gsis_id"]]
    df["tone_order"] = [TONE_ORDER.get(t, 3) for t in df["tone"]]
    df["corner_rank"] = [(rows[g]["cb"] or {}).get("corner_rank") if rows[g]["cb"] else None for g in df["gsis_id"]]
    df["corner_known"] = df["corner_rank"].notna()
    df["corner_sort"] = pd.to_numeric(df["corner_rank"], errors="coerce")
    df["name_key"] = [R._norm(n) for n in df["player_name"]]
    df = df.sort_values(["proj_points", "gsis_id"], ascending=[False, True]).reset_index(drop=True)
    _cache.put(key, df)
    return df


def _personnel(season: int, week: int, defenses: list[str]) -> dict:
    key = ("pers", int(season), int(week))
    hit = _cache.get(key)
    if hit is None:
        hit = {"defs": set(), "p": {}}
    want = [d for d in defenses if d not in hit["defs"]]
    if want:
        got = cards.corner_personnel(want, int(season), int(week))
        hit = {"defs": hit["defs"] | set(want), "p": {**hit["p"], **got}}
        _cache.put(key, hit)
    return {d: copy.deepcopy(hit["p"][d]) for d in defenses if d in hit["p"]}


def _evidence(ctx: R.Ctx, rows: list[dict], season: int, week: int) -> dict[str, dict | None]:
    """The matchup evidence each row opens (research.matchup_evidence, as the player card has it: the defense's history
    on the reference mart — the board's own rank — the corners now for a receiver, the forecast's treatment)."""
    if not rows:
        return {}
    pos = sorted({r["position"] for r in rows})
    dvp = query("""select defense, position, games, through_week, points_allowed_per_game_std, rank_std
                   from analytics.mart_defense_vs_position_current where season = %s and position = any(%s)""",
                (int(season), pos))
    pers = _personnel(season, week, sorted({r["opponent"] for r in rows if r["position"] == "WR"}))
    scoring = f"{refleague.label(refleague.DEFAULT)} scoring"
    shared: dict = {}
    out = {}
    for r in rows:
        try:
            out[r["gsis_id"]] = R.matchup_evidence(
                ctx, r["gsis_id"], int(week), dvp=dvp, personnel=pers, scoring=scoring, memo=shared,
                head={"gsis_id": r["gsis_id"], "player_name": r["player_name"], "position": r["position"], "team": r["team"]},
                game=(r["opponent"], r["is_home"]))
        except Exception:  # noqa: BLE001 - the evidence is context: a row without it still stands
            out[r["gsis_id"]] = None
    return out


def board(league: str, *, position: str | None = None, q: str | None = None, game: str | None = None,
          tone: str | None = None, sort: str | None = None, limit: int | None = None, offset: int | None = None,
          source: str | None = None) -> dict:
    pos = _param_position(position)
    qq = _param_q(q)
    tn = _param_choice(tone, (*TONES, "none"), "tone", None)
    so = _param_choice(sort, SORTS, "sort", "projection") or "projection"
    try:
        n = DEFAULT_LIMIT if limit is None else int(limit)
        off = 0 if offset is None else int(offset)
    except (TypeError, ValueError) as exc:
        raise Bad("limit and offset are numbers.") from exc
    if not 1 <= n <= MAX_LIMIT:
        raise Bad(f"limit is 1 to {MAX_LIMIT}.")
    if not 0 <= off <= 5000:
        raise Bad("offset is 0 to 5000.")
    g = (game or "").strip().upper() or None
    if g is not None and g != "ALL" and not GAME_ID.match(g):
        raise Bad("game is one of this week's games (its id, as the board's games list gives it).")
    g = None if g == "ALL" else g
    ctx = R.context(league, source)
    season, week = ctx.season, ctx.week
    ref = refleague.is_reference(league)
    meta = {**ctx.meta(), "position": pos, "q": qq, "game": g, "tone": tn, "sort": so, "limit": n, "offset": off,
            "scoring": refleague.label(league) if ref else ctx.league_name, "projection_words": PROJECTION_WORDS,
            "tone_words": TONE_WORDS, "position_note": POSITION_NOTE.get(pos), "rank_note": R.RANK_NOTE}
    empty = {**meta, "rows": [], "total": 0, "games": [], "counts": {}}
    if week is None:
        return {**empty, "notice": "The regular season is over."}
    wk = _week_frame(season, week)
    if wk is None:
        return {**empty, "notice": "This week's matchups arrive with the next data refresh."}
    games = [{"game_id": r["game_id"], "home": r["team"], "away": r["opponent"], "kickoff_at": r["kickoff_at"]}
             for r in wk["games"][wk["games"]["is_home"]].sort_values(["kickoff_at", "game_id"]).to_dict("records")]
    if g is not None and g not in {x["game_id"] for x in games}:
        raise Bad("That game is not on this week's schedule.")
    df = _week_rows(ctx, season, week, wk)
    df = df[df["position"] == pos]
    counts = {t: int((df["tone"] == t).sum()) for t in TONES} | {"none": int(df["tone"].isna().sum())}
    if g is not None:
        df = df[df["game_id"] == g]
    if qq is not None:              # text, never a pattern: `%` or `_` is a character no name has (pandas, no SQL)
        key = R._norm(qq) if NAME_CHARS.match(qq.lower()) else ""
        df = df[df["name_key"].str.contains(key, regex=False)] if key else df.iloc[0:0]
    if tn is not None:
        df = df[df["tone"].isna()] if tn == "none" else df[df["tone"] == tn]
    if so == "tone":
        df = df.sort_values(["tone_order", "proj_points", "gsis_id"], ascending=[True, False, True])
    elif so == "corner":           # the easiest corner to throw on first (the highest rank); no ranked corner last
        df = df.sort_values(["corner_known", "corner_sort", "proj_points", "gsis_id"], ascending=[False, False, False, True])
    total = int(len(df))
    page = df.iloc[off:off + n]
    page_rows = R._records(page.drop(columns=["tone_order", "corner_known", "corner_sort", "name_key"]))
    if not ref and page_rows:
        ro = R.rostered(ctx).set_index("gsis_id")
        for r in page_rows:
            o = ro.loc[r["gsis_id"]] if r["gsis_id"] in ro.index else None
            r["rostered_by_roster_id"] = None if o is None or pd.isna(o["rostered_by_roster_id"]) else int(o["rostered_by_roster_id"])
            r["rostered_by_team"] = None if o is None else o["rostered_by_team"]
    ev = _evidence(ctx, page_rows, season, week)
    out_rows = []
    for r in page_rows:
        c = copy.deepcopy(wk["rows"][r["gsis_id"]])
        out_rows.append({
            **{k: r.get(k) for k in ("gsis_id", "player_name", "position", "team", "headshot_url", "report_status",
                                     "opponent", "is_home", "kickoff_at", "game_id", "proj_points", "p10", "p25", "p75",
                                     "p90")},
            **({k: r.get(k) for k in ("rostered_by_roster_id", "rostered_by_team")} if not ref else {}),
            "context": c, "cb_detail": wk["detail"].get(r["gsis_id"]), "matchup_evidence": ev.get(r["gsis_id"])})
    return {**meta, "season": season, "week": week, "rows": out_rows, "total": total, "games": games, "counts": counts}


@router.get("/api/matchups/board")
def board_route(league: str, response: Response, position: str = "WR", q: str | None = None, game: str | None = None,
                tone: str | None = None, sort: str | None = None, limit: int = DEFAULT_LIMIT, offset: int = 0,
                source: str | None = None):
    from .main import _research
    return _research(board(league, position=position, q=q, game=game, tone=tone, sort=sort, limit=limit, offset=offset,
                           source=source), league, response)
