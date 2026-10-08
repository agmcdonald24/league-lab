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

**The one tone** (``combine_tone``; docs/METRICS.md § "Matchups for everyone") is **the defense's alone** (the PO's
decision, Wave I-O fix round, after IO-1 graded the corner calls on 2,190 called receiver-games, 2025 and 2026 weeks
1-4, as-of ranks: a likely shutdown corner -0.39 points against the rest (-1.39 to +0.72), a likely easy corner -0.02
(-1.11 to +1.22) — no measurable effect). The corner is shown as information — his name, rank, quarter (``tier``) and
how sure the call is — and moves nothing: ``cb["tone"]`` is always None, ``context["words"]`` is the defense's sentence
and the corner's sentence is ``cb["words"]``. Without a defense read there is no tone (unknown is not neutral):

    defense \\ corner        any corner, any certainty, or none
    favorable                 favorable
    neutral                   neutral
    difficult                 difficult
    none                      none

**What is in the projection** (``IN_PROJECTION``, asserted against ``league_lab.projections.BASE_FEATURES`` by
api/tests/test_in3.py): the points the defense has allowed to his position (season, last 4 games, its rank, against the
league's average) and the betting lines are inputs; who plays cornerback is not. The corner calls are a lean from where
his targets go, checked on 2025 for which corner draws his targets (docs/METRICS.md § Cornerback matchups); graded as a
forecast by IO-1 (``context_record``): no measurable effect — so it is context, and it moves no tone.
"""

from __future__ import annotations

import copy
import re

import numpy as np
import pandas as pd
from fastapi import APIRouter, Response
from league_lab import clock, memo  # ---- IO-4: clock (the board's "Started" / "Final")

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
# ---- the memory budget (docs/DEPLOY.md § Memory): two regions, so cycling league scorings never evicts the week.
# `matchup_week` (≤ 8 entries, three per week): ("ctx", season, week) — the week's context, ~800 players, ~0.5 MB;
# ("pers", season, week) — the corners now of every defense (~30 KB); ("ev", season, week) — the matchup evidence of
# the players the board has shown (≤ ~800, ~3 KB each). Seasons and weeks come from the decision week (no user input).
# `matchup_board` (≤ 24 entries, least recently used first): ("board", <research._ctx_key>, season, week) — one league
# scoring's week frame (~600 rows, ~0.2 MB); keys are the research memo's (a house league, or one of the 20 reference
# scorings, or an on-demand league's scoring). Both 10 minutes; both inside the one byte budget.
WEEK_ENTRIES, BOARD_ENTRIES = 8, 24
_week = memo.region("matchup_week", ttl=CONTEXT_TTL_S, max_entries=WEEK_ENTRIES, published=True)
_cache = memo.region("matchup_board", ttl=CONTEXT_TTL_S, max_entries=BOARD_ENTRIES, published=True)


def clear() -> None:
    """Both regions emptied (tests; a data refresh would wait out the 10 minutes)."""
    _week.clear()
    _cache.clear()

NO_CALL_SHORT = {"too few targets with a direction to tell his side": "too few targets to tell his side"}
# ---- IO-4 fix round: the corner's quarter in plain words (information: graded, it made no measurable difference)
CORNER_KIND = {"shutdown": "a top-quarter corner", "target": "a bottom-quarter corner", "solid": "a middle-half corner"}
CORNER_KIND_SHORT = {"shutdown": "top quarter", "target": "bottom quarter", "solid": "middle half"}   # two in one sentence
IN_PROJECTION = ("opp_allowed_std", "opp_allowed_l4", "opp_rank_std", "f_opp_allowed_diff", "league_allowed_avg")
# ---- IO-4 fix round (Wave I-O): the corner moves nothing (the PO's decision on IO-1's grade). The honesty line is the
# projection's inputs + IO-1's graded sentence (``projection_words``); without the record, the inputs alone (they say the
# corner is not in the projection and is shown for context — never "not graded yet").
PROJECTION_HEAD = ("What the projection counts: the points each defense has allowed to the position (this season, the "
                   "last 4 games and its rank) and the betting lines. Who plays cornerback is not in it: the corner "
                   "call is a lean from where his targets go, shown for context.")
PROJECTION_WORDS = PROJECTION_HEAD
TONE_WORDS = ("Matchup = the defense against his position (favorable: one of the 10 that give up the most; difficult: one "
              "of the 10 that give up the fewest; the rest neutral). The cornerback is shown beside it and does not "
              "move it.")
POSITION_NOTE = {"TE": "Tight ends get the defense against the position only: they mostly draw linebackers and safeties.",
                 "RB": "Running backs get the defense against the position only: no cornerback call.",
                 "QB": "Quarterbacks get the defense against the position only: no cornerback call."}


# ------------------------------------------------------------------------------------------------------- the tone
def combine_tone(defense: str | None, corner: str | None, certainty: str | None) -> str | None:
    """The one-word read (the table in the module's docstring): the defense's alone — the corner and the certainty are
    accepted and ignored (IO-4 fix round: graded, the corner call made no measurable difference)."""
    del corner, certainty
    return defense if defense in TONES else None


# ------------------------------------------------------------------------------------------------------- the reads
WEEK_SQL = """select distinct on (p.gsis_id) p.gsis_id, p.position, p.team, p.player_name, p.report_status
              from analytics.mart_player_week_projections p
              where p.season = %s and p.week = %s and p.gsis_id is not null and p.position = any(%s)
              order by p.gsis_id, p.is_reference_league desc, p.league_id"""
GAMES_SQL = """select game_id, home_team, away_team, kickoff_at, is_final from analytics.dim_game
               where season = %s and week = %s and season_type = 'REG' order by kickoff_at, game_id"""   # IO-4: is_final
DEFENSE_SQL = """select defense, position, games, through_week, points_allowed_per_game_std, rank_std
                 from analytics.mart_defense_vs_position_current where season = %s and position = any(%s)"""
CB_SQL = "select * from analytics.mart_cb_matchups where season = %s and week = %s and position = 'WR'"


def _games(season: int, week: int) -> pd.DataFrame:
    """One row per team with a game: team, opponent, is_home, kickoff_at, game_id."""
    g = query(GAMES_SQL, (int(season), int(week)))
    cols = ["team", "opponent", "is_home", "kickoff_at", "game_id", "is_final"]           # ---- IO-4: is_final
    if g.empty:
        return pd.DataFrame(columns=cols)
    if "is_final" not in g:
        g = g.assign(is_final=False)
    home = g.rename(columns={"home_team": "team", "away_team": "opponent"}).assign(is_home=True)
    away = g.rename(columns={"away_team": "team", "home_team": "opponent"}).assign(is_home=False)
    return pd.concat([home, away], ignore_index=True)[cols]


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

    def who(c: dict, short: bool = False) -> str:
        name = c.get("name")
        if not name:
            return "an unnamed corner"
        return (cards.last_name(str(name)) or str(name)) if short else str(name)

    def tag(c: dict, short: bool = False) -> str:
        """'a top-quarter corner, #3 of 74' · 'a bottom-quarter corner, #66 of 69' · 'a middle-half corner, #30 of 74' ·
        'unranked' (#1 = the hardest to throw on)."""
        if c.get("rank") is None:
            return "unranked"
        kind = (CORNER_KIND_SHORT if short else CORNER_KIND).get(str(c.get("label")), "ranked")
        return f"{kind}, #{c['rank']}{f' of {n}' if n else ''}"

    # IN-3 fix (the merge's read of the home and DFS): short enough for a home row and a DFS chip; the board's opened
    # row keeps each corner's full rank words (cb_detail)
    if m["certainty"] == "likely" and first is not None:
        words = f"{who(first)} ({tag(first)}) is likely across from him"
    elif m["certainty"] == "unclear" and len(named) > 1:
        words = f"either {' or '.join(f'{who(c, True)} ({tag(c, True)})' for c in named)} could be across from him"
    elif m["certainty"] == "unclear" and named:
        words = f"{who(first)} ({tag(first)}) may be across from him; the other side is as likely"
    else:
        why = str(m["certainty_words"]).split(": ", 1)[-1]
        words = "no corner call: " + NO_CALL_SHORT.get(why, why)
    # ---- IO-4 fix round: information, not a tone — the corner moves nothing (``tone`` always None); ``tier`` = the
    # quarter of the first corner named (shutdown = the top quarter, target = the bottom, solid = the middle half)
    tier = first.get("label") if first is not None and first.get("rank") is not None else None
    ctx = {"tone": None, "certainty": m["certainty"],
           "corner": first.get("name") if first else None, "corner_rank": first.get("rank") if first else None,
           "shutdown": shutdown, "tier": tier if tier in ("shutdown", "solid", "target") else None, "words": words}
    detail = {"n_ranked": n, "certainty_words": m["certainty_words"], "history": m["history"],
              "named": [{"name": c.get("name"), "side": c.get("side"), "rank": c.get("rank"), "label": c.get("label"),
                         "words": c.get("words"), "tone": None} for c in named]}        # IO-4 fix: no tone
    return {"ctx": ctx, "detail": detail}


def _not_playing(season: int, week: int, defenses: list[str]) -> dict[str, dict[str, str]]:
    """defense -> {gsis_id: name} of its listed corners who are not expected to play this week (the availability
    overlay: Out, Doubtful, IR …; ``cards.corner_personnel``, the matchup evidence's own read). A defense without a
    depth chart before the game, or no overlay, has none."""
    try:
        pers = _personnel(season, week, defenses)
    except Exception:  # noqa: BLE001 - the overlay is never load-bearing: the depth chart's call stands
        return {}
    out = {}
    for d, p in pers.items():
        if p.get("kind") not in ("changed", "same"):
            continue
        exp = {e.get("gsis_id") for e in p.get("expected") or []}
        gone = {c["gsis_id"]: c.get("name") for c in p.get("listed") or [] if c.get("gsis_id") not in exp}
        if gone:
            out[d] = gone
    return out


def _sentence(defense: dict, cb: dict | None, tone: str | None) -> str | None:
    """The context's one sentence: the defense's only (IO-4 fix round); the corner's sentence is ``cb["words"]``."""
    del cb, tone
    d = defense.get("words")
    return f"{d}." if d else None


def _week_frame(season: int, week: int) -> dict | None:
    """The cached week: {"rows": {gsis_id: context}, "detail": {gsis_id: corner detail}, "frame": players, "games"}."""
    key = ("ctx", int(season), int(week))
    hit = _week.get(key)
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
    gone = _not_playing(season, week, sorted({str(r.get("opponent")) for r in cb_of.values() if r.get("opponent")}))
    rows: dict[str, dict] = {}
    detail: dict[str, dict] = {}
    for p in frame.to_dict("records"):
        g, pos, opp = p["gsis_id"], p["position"], p["opponent"]
        dread = dict(defense.get((opp, pos)) or {"tone": None, "tough_rank": None, "n_ranked": None, "words": None})
        cb = None
        if pos == "WR":
            r = cb_of.get(g)
            named: list = []
            if r is not None and r.get("call_status") == "called":
                named = [r.get("likely_cover_gsis_id")] + ([r.get("other_cover_gsis_id")] if r.get("call_strength") != "clear" else [])
            away = gone.get(opp) or {}
            absent = [str(away[x] or "a corner") for x in named if isinstance(x, str) and x in away]
            if r is not None and r.get("opponent") == opp and absent:
                # a corner the call names is not expected to play: no call (never "faces a shutdown corner" who is out);
                # the row's evidence says who is expected instead
                cb = {"tone": None, "certainty": "no call", "corner": None, "corner_rank": None, "shutdown": False, "tier": None,
                      "words": f"no corner call: {' and '.join(absent)}, named on his side, "
                               f"{'is' if len(absent) == 1 else 'are'} not expected to play"}
            elif r is not None and r.get("opponent") == opp:
                read = _corner_read(r)
                cb, detail[g] = read["ctx"], read["detail"]
            else:
                cb = {"tone": None, "certainty": "no call", "corner": None, "corner_rank": None, "shutdown": False,
                      "tier": None, "words": "no corner call: no depth chart for this game yet"}
        tone = combine_tone(dread["tone"], cb["tone"] if cb else None, cb["certainty"] if cb else None)
        rows[g] = {"opponent": opp, "home": None if pd.isna(p["is_home"]) else bool(p["is_home"]),
                   "defense": dread, "cb": cb, "tone": tone, "words": _sentence(dread, cb, tone)}
    out = {"rows": rows, "detail": detail, "frame": frame, "games": games}
    _week.put(key, out)
    return out


def matchup_context(season: int, week: int, gsis_ids: list[str] | None = None) -> dict[str, dict]:
    """gsis_id -> {"opponent": "KC", "home": bool | None,
                   "defense": {"tone": "favorable" | "neutral" | "difficult" | None, "tough_rank": int | None,
                               "n_ranked": int | None, "words": str | None},          # defense vs his position
                   "cb": {"tone": None,                      # IO-4 fix round: the corner moves nothing
                          "certainty": "likely" | "unclear" | "no call",
                          "corner": str | None, "corner_rank": int | None, "shutdown": bool,
                          "tier": "shutdown" | "solid" | "target" | None,   # his quarter (top / middle half / bottom)
                          "words": str | None} | None,               # wide receivers only: the corner's sentence
                   "tone": same | None,          # the defense's tone (combine_tone: the defense's alone)
                   "words": str | None}          # the defense's sentence, a screen prints it as it is

    Every QB / RB / WR / TE with a game in ``week`` (the week's projection rows, plus every receiver the cornerback mart
    lists) — or only ``gsis_ids``. Scoring-free (the marts' standard ranks: ``tough_rank`` 1 = the defense that gives up
    the fewest points to the position; ``corner_rank`` 1 = the corner hardest to throw on). **The tone** is the
    defense's alone (IO-1's grade: the corner call made no measurable difference); the corner is information — who,
    his rank and quarter, how sure the call is. A corner the call names who is not expected to play (the availability
    overlay, ``cards.corner_personnel``) makes it "no call". A player on a bye is
    absent. Never raises: a missing mart or week gives {}."""
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


# ---- IO-4 (Wave I-O): one screen, one rank per defense. In a real league the heatmap under the board ranks the
# defenses in the league's scoring (``research.league_dvp``); the board's defense read comes from the same frame there,
# so a house league never shows "7th-most" on a row and #9 in the cell under it. Browsing (a reference key) keeps the
# reference mart (``matchup_context``'s read: scoring-free, what the home and DFS read). The corner call is the same.
def league_defense(ctx: R.Ctx, season: int) -> dict[tuple[str, str], dict] | None:
    """(defense, position) -> the defense read in ``_defense``'s shape, from the league's own points allowed; None when
    the league's frame cannot be read (the board falls back on the reference read, said by ``defense_source``)."""
    try:
        d = R.league_dvp(ctx, int(season))
    except Exception:  # noqa: BLE001 - the reference read stands
        return None
    if d is None or d.empty or not {"defense", "position", "rank_std"} <= set(d.columns):
        return None
    d = d[d["position"].isin(POSITIONS)]
    if "rank_l4" not in d:
        d = d.assign(rank_l4=np.nan)
    d = R.defense_meaning(d)
    out = {}
    for r in d.to_dict("records"):
        out[(r["defense"], r["position"])] = {
            "tone": r.get("tone") if r.get("tone") in TONES else None, "tough_rank": R._rank(r.get("tough_rank")),
            "n_ranked": R._rank(r.get("n_ranked")) or None,
            "words": f"{R._place(r['defense'])} {r['rank_words']}" if isinstance(r.get("rank_words"), str) else None}
    return out


GAME_LENGTH = pd.Timedelta(hours=4)        # a game kicked off this long ago is over even before the data says final


def game_state(kickoff, is_final, now: pd.Timestamp) -> str | None:
    """None (still to play) · "started" (kicked off, not over) · "final" — from the one clock; the database's final
    flag counts only for a game that has kicked off by that clock (a pinned clock never sees a future game final)."""
    if kickoff is None or (not isinstance(kickoff, str) and pd.isna(kickoff)):
        return None
    k = pd.Timestamp(kickoff)
    k = k.tz_localize("UTC") if k.tzinfo is None else k.tz_convert("UTC")
    if k > now:
        return None
    return "final" if bool(is_final) is True or now >= k + GAME_LENGTH else "started"


def _record_words() -> str | None:
    """IO-1's context record (``context_record.summary()``, the interface fixed in the wave's brief): its sentence on
    how the corner calls have done, when graded; None without the module or the record (today's sentence stays)."""
    try:
        from . import context_record  # type: ignore[attr-defined]
        c = (context_record.summary() or {}).get("corner") or {}
        w = c.get("words")
        return w.strip() if c.get("graded") is True and isinstance(w, str) and w.strip() else None
    except Exception:  # noqa: BLE001 - absent, broken or slow to build: never load-bearing
        return None


def projection_words() -> str:
    """The honesty line: PROJECTION_HEAD + IO-1's graded sentence on the corner calls; without it, PROJECTION_HEAD."""
    rec = _record_words()
    if not rec:
        return PROJECTION_WORDS
    return f"{PROJECTION_HEAD} {rec if rec.endswith('.') else rec + '.'}"
# ---- end IO-4


def _week_rows(ctx: R.Ctx, season: int, week: int, wk: dict, league_def: dict | None = None) -> pd.DataFrame:
    """Every player with a game this week and a projection in this league's scoring: name, team, game, projection and
    range, and the context's sort keys (cached per league scoring and week). ``league_def`` (IO-4): the league's own
    defense read — the row's tone is formed from it (``def_*`` columns carry it for the page)."""
    key = ("board", R._ctx_key(ctx), int(season), int(week), league_def is not None)
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
    if league_def is not None:                                                          # ---- IO-4
        reads = [league_def.get((o, p)) or {"tone": None, "tough_rank": None, "n_ranked": None, "words": None}
                 for o, p in zip(df["opponent"], df["position"], strict=True)]
        df["def_tone"] = [d["tone"] for d in reads]
        df["def_rank"] = [d["tough_rank"] for d in reads]
        df["def_n"] = [d["n_ranked"] for d in reads]
        df["def_words"] = [d["words"] for d in reads]
        df["tone"] = [combine_tone(d["tone"], (rows[g]["cb"] or {}).get("tone"), (rows[g]["cb"] or {}).get("certainty"))
                      for g, d in zip(df["gsis_id"], reads, strict=True)]
    else:
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
    hit = _week.get(key)
    if hit is None:
        hit = {"defs": set(), "p": {}}
    want = [d for d in defenses if d not in hit["defs"]]
    if want:
        got = cards.corner_personnel(want, int(season), int(week))
        hit = {"defs": hit["defs"] | set(want), "p": {**hit["p"], **got}}
        _week.put(key, hit)
    return {d: copy.deepcopy(hit["p"][d]) for d in defenses if d in hit["p"]}


def _evidence(ctx: R.Ctx, rows: list[dict], season: int, week: int, own: bool = False) -> dict[str, dict | None]:
    """The matchup evidence each row opens (research.matchup_evidence, as the player card has it: the defense's history
    on the reference mart — the board's own rank — the corners now for a receiver, the forecast's treatment). ``own``
    (IO-4: a real league whose board reads the league's own defense rank): the history in the league's scoring too, so
    the opened row never shows a second rank; kept per league scoring in the board's region."""
    if not rows:
        return {}
    # the evidence does not depend on the league (its ranks are the reference mart's): kept per week for every league,
    # each player computed once (the answer is rebuilt by the JSON cleaner, so the cached objects are never changed)
    key = ("ev", int(season), int(week)) if not own else ("ev", R._ctx_key(ctx), int(season), int(week))   # IO-4
    region = _cache if own else _week                                                                   # IO-4
    have: dict = region.get(key) or {}
    want = [r for r in rows if r["gsis_id"] not in have]
    if not want:
        return {r["gsis_id"]: have[r["gsis_id"]] for r in rows}
    rows_all, rows = rows, want
    pos = sorted({r["position"] for r in rows})
    dvp = query("""select defense, position, games, through_week, points_allowed_per_game_std, rank_std
                   from analytics.mart_defense_vs_position_current where season = %s and position = any(%s)""",
                (int(season), pos))
    pers = _personnel(season, week, sorted({r["opponent"] for r in rows if r["position"] == "WR"}))
    scoring = f"{refleague.label(refleague.DEFAULT)} scoring"
    if own:                                    # ---- IO-4: the league's own ranks (matchup_evidence's default), its name
        dvp, scoring = None, None
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
    have = {**have, **out}
    region.put(key, have)                                                                               # IO-4
    return {r["gsis_id"]: have.get(r["gsis_id"]) for r in rows_all}


SHOWS = ("to_play", "all")             # ---- IO-4: "Still to play" (the default once a game has started) · "All games"


def board(league: str, *, position: str | None = None, q: str | None = None, game: str | None = None,
          tone: str | None = None, sort: str | None = None, limit: int | None = None, offset: int | None = None,
          source: str | None = None, show: str | None = None) -> dict:
    pos = _param_position(position)
    sh = (show or "").strip().lower() or None                                           # ---- IO-4
    if sh is not None and sh not in SHOWS:
        raise Bad("show is to_play or all.")
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
            "scoring": refleague.label(league) if ref else ctx.league_name, "projection_words": projection_words(),
            "tone_words": TONE_WORDS, "position_note": POSITION_NOTE.get(pos), "rank_note": R.RANK_NOTE,
            "show": sh or "all", "started_games": 0, "started_players": 0, "defense_source": "reference"}   # IO-4
    empty = {**meta, "rows": [], "total": 0, "games": [], "counts": {}}
    if week is None:
        return {**empty, "notice": "The regular season is over."}
    wk = _week_frame(season, week)
    if wk is None:
        return {**empty, "notice": "This week's matchups arrive with the next data refresh."}
    now = pd.Timestamp(clock.now())                                                     # ---- IO-4
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    gw = wk["games"]
    games = [{"game_id": r["game_id"], "home": r["team"], "away": r["opponent"], "kickoff_at": r["kickoff_at"],
              "state": game_state(r["kickoff_at"], r.get("is_final"), now)}                  # ---- IO-4
             for r in gw[gw["is_home"]].sort_values(["kickoff_at", "game_id"]).to_dict("records")]
    if g is not None and g not in {x["game_id"] for x in games}:
        raise Bad("That game is not on this week's schedule.")
    league_def = None if ref else league_defense(ctx, season)                           # ---- IO-4
    df = _week_rows(ctx, season, week, wk, league_def)
    df = df[df["position"] == pos]
    df, meta["not_playing"] = gate_week(df, season, week)                                  # ---- IR-1
    # ---- IO-4: a game that has kicked off moves below the games still to come; "Still to play" by default once one has
    state_of = {x["game_id"]: x["state"] for x in games}
    df = df.assign(game_state=[state_of.get(x) for x in df["game_id"]])
    started = int(df["game_state"].notna().sum())
    sh = sh or ("all" if g is not None or not any(x["state"] for x in games) else "to_play")   # a game picked: all of it
    meta.update(show=sh, started_games=sum(1 for x in games if x["state"]), started_players=started,
                defense_source="league" if league_def is not None else "reference")
    if sh == "to_play":
        df = df[df["game_state"].isna()]
    # ---- end IO-4
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
    df = pd.concat([df[df["game_state"].isna()], df[df["game_state"].notna()]])         # ---- IO-4: kicked off last
    total = int(len(df))
    page = df.iloc[off:off + n]
    page_rows = R._records(page.drop(columns=["tone_order", "corner_known", "corner_sort", "name_key"]))
    if not ref and page_rows:
        ro = R.rostered(ctx).set_index("gsis_id")
        for r in page_rows:
            o = ro.loc[r["gsis_id"]] if r["gsis_id"] in ro.index else None
            r["rostered_by_roster_id"] = None if o is None or pd.isna(o["rostered_by_roster_id"]) else int(o["rostered_by_roster_id"])
            r["rostered_by_team"] = None if o is None else o["rostered_by_team"]
    ev = _evidence(ctx, page_rows, season, week, own=league_def is not None)                      # ---- IO-4
    out_rows = []
    for r in page_rows:
        c = copy.deepcopy(wk["rows"][r["gsis_id"]])
        if league_def is not None:                       # ---- IO-4: the league's own defense read (the heatmap's rank)
            c["defense"] = {"tone": r.get("def_tone"), "tough_rank": R._rank(r.get("def_rank")),
                            "n_ranked": R._rank(r.get("def_n")) or None, "words": r.get("def_words")}
            c["tone"] = r.get("tone")
            c["words"] = _sentence(c["defense"], c["cb"], c["tone"])
        out_rows.append({
            **{k: r.get(k) for k in ("gsis_id", "player_name", "position", "team", "headshot_url", "report_status",
                                     "opponent", "is_home", "kickoff_at", "game_id", "proj_points", "p10", "p25", "p75",
                                     "p90", "game_state")},                              # ---- IO-4: game_state
            **({k: r.get(k) for k in ("rostered_by_roster_id", "rostered_by_team")} if not ref else {}),
            "context": c, "cb_detail": wk["detail"].get(r["gsis_id"]), "matchup_evidence": ev.get(r["gsis_id"])})
    return {**meta, "season": season, "week": week, "rows": out_rows, "total": total, "games": games, "counts": counts}


# ---- IR-1 (Wave I-R): nobody who cannot play is on a week's list (availability.statuses: the nightly's record +
# Sleeper + ESPN, freshest wins); listed apart with the status, its source and time — never a number
def gate_week(df: pd.DataFrame, season: int | None, week: int | None) -> tuple[pd.DataFrame, list[dict]]:
    """(the rows who can play, a status refreshed on a doubtful / questionable one; the "Not playing" list)."""
    from . import availability as AV
    if df is None or df.empty or week is None:
        return df, []
    st = AV.statuses(None, season, week)
    stored = set(AV.stored_status(season, week))
    g = df["gsis_id"].where(df["gsis_id"].map(lambda x: isinstance(x, str)), None)
    out = {k for k, s in st.items() if AV.sits(s)}                  # ---- IS-1: cannot play, or unlikely to play
    gone = g.isin(out | stored)
    rows = [AV.not_playing_row(r, st[r["gsis_id"]]) for r in df[gone & g.isin(out)].to_dict("records")]
    keep = df[~gone].copy()
    if "report_status" in keep:
        keep["report_status"] = [(st.get(x) or {}).get("status") or r if isinstance(x, str) else r
                                 for x, r in zip(keep["gsis_id"], keep["report_status"], strict=True)]
    would = {str(r.get("gsis_id")): r.get("proj_points") for r in df[gone].to_dict("records")}       # ---- IS-1
    return keep, AV.order_not_playing(rows, would, season)
# ---- end IR-1


@router.get("/api/matchups/board")
def board_route(league: str, response: Response, position: str = "WR", q: str | None = None, game: str | None = None,
                tone: str | None = None, sort: str | None = None, limit: int = DEFAULT_LIMIT, offset: int = 0,
                source: str | None = None, show: str | None = None):
    from .main import _research
    return _research(board(league, position=position, q=q, game=game, tone=tone, sort=sort, limit=limit, offset=offset,
                           source=source, show=show), league, response)
