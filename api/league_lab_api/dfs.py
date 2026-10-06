"""DFS on the API (Wave I-M, IM-5; docs/DFS.md): the site's salary file in, values and lineups out. No league, no team,
no stored salary: every route works for a visitor who has opened no league.

* ``GET  /api/dfs/projections?site=dk|fd&week=``  this week's players in the site's scoring, ranked, with the range —
  before anyone adds a file.
* ``POST /api/dfs/slate?week=``                  the salary file's text as the body (or JSON ``{"text": …}``) →
  ``{site, contest, week, games, players, unmatched, fit, undervalued, overpriced, notes}``. Stateless: the file is
  parsed in memory, never stored or logged (no logging call here touches it).
* ``POST /api/dfs/lineups``                       the slate's players as returned + locks / excludes / mode / n →
  the lineups (salary, projection, range) and the site's lineup-upload CSV.

Wave I-N (IN-4): **context beyond the projection** on every board (the matchup from ``matchup_board.matchup_context``,
imported lazily; the role trend; the betting line and the weather) with "Worth a look"; **published slates** —
``GET /api/dfs/slates`` and ``GET /api/dfs/slate/{id}`` read ``dfs/slates/`` once (``LEAGUE_LAB_DFS_SLATES``) — and
``POST /api/dfs/lineups`` takes a published ``slate_id`` and **stacks** / **exposure** (docs/DFS.md).

Rate limiting: ``RATE_BUCKETS`` names the bucket of each route in IM-3's limiter terms (``heavy`` for the two POSTs:
they parse a file and solve integer programs) — the PO wires it at the merge. One ``league_lab.memo`` region
(``dfs``): the week's board priced per site (``dfs.price_site``), ~0.2 MB a site-week.
"""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from league_lab import anyleague as A
from league_lab import dfs as D
from league_lab import memo
from starlette.concurrency import run_in_threadpool

from . import availability
from .applib import cards, ui
from .db import query
from .settings import ROOT, env

router = APIRouter()
RATE_BUCKETS = {"/api/dfs/slate": "heavy", "/api/dfs/lineups": "heavy", "/api/dfs/projections": "read"}
# IN-4: the published slates' two GETs price a slate once and keep it: research (ratelimit.bucket_for, a marked block)
RATE_BUCKETS_IN4 = {"/api/dfs/slates": "research", "/api/dfs/slate/{slate_id}": "research"}
NO_STORE = {"Cache-Control": "no-store"}
_priced = memo.region("dfs", ttl=600.0, max_entries=8)
# ---- IM-5 fix (the security review): DFS work (parsing a file, pricing, solving) runs in the thread pool, never on the
# event loop, and ONE at a time per process: a second request waits up to BUSY_WAIT_S, then answers 429 `busy`
_WORK = threading.Semaphore(1)
BUSY_WAIT_S = 2.0
BUSY_WORDS = "Another lineup is being built right now. Try again in a few seconds."
LIMIT = {"str": 40, "name": 80}                 # the longest id / key, team-game string, name a request may carry
PROJ_RANGE = (-20.0, 150.0)                     # a projection, low-end or high-end outcome outside it is not ours


class Busy(Exception):
    pass


def _busy() -> JSONResponse:
    return JSONResponse({"error": BUSY_WORDS, "detail": BUSY_WORDS, "code": "busy", "retry_after_s": 5},
                        status_code=429, headers={**NO_STORE, "Retry-After": "5"})


async def _one_at_a_time(fn, *args, **kw):
    """``fn`` in the thread pool behind the process-wide DFS semaphore (a bounded wait, then ``Busy``)."""
    def run():
        if not _WORK.acquire(timeout=BUSY_WAIT_S):
            raise Busy
        try:
            return fn(*args, **kw)
        finally:
            _WORK.release()
    return await run_in_threadpool(run)

SCHEDULE_SQL = """select week, home_team, away_team, kickoff_at from analytics.dim_game
                  where season = %s and season_type = 'REG'"""
OPP_RANK_SQL = "select defense, position, rank_std from analytics.mart_defense_vs_position_current"
DIRECTORY_SQL = """select gsis_id as key, player_name, position, latest_team as team from analytics.dim_player
                   where position in ('QB', 'RB', 'WR', 'TE', 'K', 'FB') and latest_team is not null
                     and coalesce(last_season, 0) >= %s"""
POS_WORD = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "DEF": "DEF"}
OUT_FILE = {"O": "Out", "IR": "Injured reserve", "D": "Doubtful", "NA": "Not active", "SUS": "Suspended", "PUP": "PUP"}
KD_REASON = ("sacks", "takeaways", "points_allowed", "field_goals", "extra_points")
OUT_REPORT = ("Out", "Doubtful", "IR", "Injured Reserve", "PUP", "Suspended")


class Bad(Exception):
    def __init__(self, words: str, code: str, status: int = 400):
        super().__init__(words)
        self.code, self.status = code, status


def _err(exc: Bad | D.SlateError, status: int | None = None) -> JSONResponse:
    st = status or getattr(exc, "status", 400)
    return JSONResponse({"error": str(exc), "detail": str(exc), "code": exc.code}, status_code=st, headers=NO_STORE)


def _clean(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_clean(x) for x in v]
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    if hasattr(v, "item") and not isinstance(v, str):
        return _clean(v.item())
    try:
        return None if v is not None and not isinstance(v, str | bool | int) and pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def _site(site: str) -> str:
    s = (site or "").strip().lower()
    s = {"draftkings": "dk", "fanduel": "fd"}.get(s, s)
    if s not in D.SCORING:
        raise Bad("site is dk (DraftKings) or fd (FanDuel).", "bad_site")
    return s


def _season_week(week: int | None) -> tuple[int, int]:
    """The week asked, which must be this week (the app's week rule) or the next one: any other answers 400 in words
    (each week priced is ~0.4-1 s of CPU, and the memo keeps 8)."""
    season = ui.current_season()
    if season is None:
        raise Bad("The numbers are not ready yet. Try again in a few minutes.", "not_ready", 503)
    now = cards.decision_week(int(season))
    if now is None:
        raise Bad("No week to show: the regular season is over.", "no_week", 404)
    w = int(now) if week is None else int(week)
    if w not in (int(now), int(now) + 1):
        raise Bad(f"DFS shows this week (week {now}) and next week (week {int(now) + 1}) only.", "bad_week")
    return int(season), w


def priced(site: str, season: int, week: int) -> pd.DataFrame:
    """The week's board priced in the site's scoring (``dfs.price_site``), kept 10 minutes in the ``dfs`` region."""
    key = (site, season, week, A.board_source())
    hit = _priced.get(key)
    if hit is not None:
        return hit
    out = D.price_site(A.load_board(query, season, week), site)
    _priced.put(key, out)
    return out


def _opponents(season: int, week: int) -> dict[str, str]:
    g = query(SCHEDULE_SQL, (season,))
    g = g[g["week"].astype(int) == int(week)]
    out = {}
    for r in g.itertuples():
        out[r.home_team], out[r.away_team] = r.away_team, r.home_team
    return out


def _ranks() -> dict[tuple[str, str], int]:
    try:
        df = query(OPP_RANK_SQL)
    except Exception:  # noqa: BLE001 - no matchup mart: no matchup words
        return {}
    return {(r.defense, r.position): int(r.rank_std) for r in df.itertuples() if pd.notna(r.rank_std)}


def _statuses(df: pd.DataFrame) -> pd.DataFrame:
    """``status`` (words), ``out`` (cannot play: left out of lineups by default and off the lists) and ``status_source``
    — the availability overlay first (ESPN / Sleeper, fresher), then the nightly's injury report, then the site's own
    flag (FanDuel's injury indicator)."""
    ids = [g for g in df.get("gsis_id", pd.Series(dtype=object)).dropna().astype(str) if g]
    live = availability.now(ids) if ids else {}
    status, out, src = [], [], []
    for r in df.itertuples():
        a = live.get(str(getattr(r, "gsis_id", "") or ""))
        rep = getattr(r, "report_status", None)
        rep = rep if isinstance(rep, str) and rep and rep != "Healthy" else None
        fl = getattr(r, "injury", None)
        fl = str(fl).upper() if isinstance(fl, str) and fl.strip() else None
        if a is not None and (a.get("cannot_play") or a.get("flagged")):
            status.append(a.get("status"))
            out.append(bool(a.get("cannot_play")))
            src.append(a.get("source"))
        elif rep is not None:
            status.append(rep)
            out.append(rep in OUT_REPORT)
            src.append("Injury report")
        elif fl is not None:
            status.append(OUT_FILE.get(fl, "Questionable" if fl == "Q" else fl))
            out.append(fl in OUT_FILE)
            src.append("the salary file")
        else:
            status.append(None)
            out.append(False)
            src.append(None)
    return df.assign(status=status, out=out, status_source=src)


def _line(row: pd.Series) -> dict:
    return {s: row.get(s) for s in A.STAT_LINE.values()}


def _reasons(rows: pd.DataFrame, site: str, season: int, week: int) -> dict[str, str]:
    """One plain reason per player: the app's own pieces (``cards.reason_pieces``: injury, matchup rank, the betting
    line, his share of the team's work), the strongest in the direction of his call; else the projection's chain
    ("8.9 targets → 5.5 catches → 64 yards → 0.48 TDs → 15.4 points this week", ``why.explain``). Nothing invented."""
    from . import why
    if rows.empty:
        return {}
    ids = sorted({str(g) for g in rows["gsis_id"].dropna() if g})
    try:
        facts_df = query(cards.REASON_SQL, (ids, season, week, season, week)) if ids else pd.DataFrame()
        facts = {r["gsis_id"]: r for r in facts_df.to_dict("records")} if not facts_df.empty else {}
        nk = query(cards.TEAM_NICK_SQL)
        nicks = dict(zip(nk["team_abbr"], nk["team_nick"], strict=False)) if not nk.empty else {}
    except Exception:  # noqa: BLE001 - the marts are not there: the chain alone
        facts, nicks = {}, {}
    out: dict[str, str] = {}
    for r in rows.to_dict("records"):
        call = r.get("value_call")
        short = cards.last_name(r.get("player_name"), r.get("position"))
        d = {"player_name": r.get("player_name"), "position": r.get("position"), "report_status": r.get("status"),
             "opponent": r.get("opponent"), "opp_rank": r.get("opp_rank"), "team": r.get("team"), "_short_me": short}
        pieces = cards.reason_pieces(d, "", facts.get(r.get("gsis_id")) or {}, nicks) if r.get("position") != "K" else []
        pick = None
        if call == "overpriced":
            pick = min((p for p in pieces if p[0] <= -cards.STRONG), key=lambda p: p[0], default=None)
        else:
            pick = max((p for p in pieces if p[0] >= cards.STRONG), key=lambda p: p[0], default=None)
        if pick is not None:
            out[r["key"]] = pick[2][0].upper() + pick[2][1:] + "."
            continue
        site_words = f"{D.SITE_NAMES[site]} scoring"
        if r.get("position") == "DEF" and _ok(r.get("sacks")):
            out[r["key"]] = (f"Why this number: {r['sacks']:.1f} sacks, {r['takeaways']:.1f} takeaways, "
                             f"{r['points_allowed']:.0f} points allowed → {r['proj']:.1f} points this week ({site_words}).")
            continue
        if r.get("position") == "K" and _ok(r.get("field_goals")):
            out[r["key"]] = (f"Why this number: {r['field_goals']:.1f} field goals, {r['extra_points']:.1f} extra points → "
                             f"{r['proj']:.1f} points this week ({site_words}).")
            continue
        ex = why.explain(_line(pd.Series(r)), r.get("proj"), D.SCORING[site], r.get("position"))
        if ex is not None:
            out[r["key"]] = f"Why this number: {ex['sentence']} ({site_words})."
    return out


def _ok(v) -> bool:
    try:
        return v is not None and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _matchup(r: dict, ranks: dict) -> str | None:
    opp, pos = r.get("opponent"), r.get("position")
    if not opp or pos not in ("QB", "RB", "WR", "TE"):
        return None
    k = ranks.get((opp, pos))
    words = cards.rank_words(k, pos) if k is not None else ""
    return f"vs {opp}" + (f" ({words})" if words else "")


# ------------------------------------------------------------------------------------------------ projections (no file)
@router.get("/api/dfs/projections")
def projections(site: str = "dk", week: int | None = None, position: str | None = None, limit: int = 300):
    try:
        s = _site(site)
        season, w = _season_week(week)
    except Bad as exc:
        return _err(exc)
    df = _statuses(priced(s, season, w).copy())
    opp = _opponents(season, w)
    ranks = _ranks()
    df["opponent"] = df["team"].map(opp)
    df = df[df["opponent"].notna()]                    # a team on a bye is not on a slate this week
    if position and position.upper() in POS_WORD:
        df = df[df["position"] == position.upper()]
    if s == "fd":
        df = df[df["position"] != "K"]
    df = df.sort_values(["proj", "key"], ascending=[False, True]).head(max(1, min(int(limit), 1000)))
    players = []
    for r in df.to_dict("records"):
        players.append({k: r.get(k) for k in ("key", "gsis_id", "player_name", "position", "team", "opponent", "proj",
                                               "p10", "p25", "p75", "p90", "status", "out")}
                       | {"matchup": _matchup(r, ranks)})
    refs = sorted({str(x) for x in priced(s, season, w)["reference"].dropna() if x != "lines"})
    players, worth_list, ctx_meta = _with_context(players, season, w, "proj")     # ---- IN-4: context, Worth a look
    body = {"site": s, "site_name": D.SITE_NAMES[s], "season": season, "week": w, "players": players,
            "count": len(players), "reference": refs[0] if refs else None,
            "scoring": scoring_words(s), "bonus_at_odds": D.BONUS_AT_ODDS and s == "dk",
            "worth_a_look": worth_list, "context_meta": ctx_meta}
    return JSONResponse(_clean(body), headers={"Cache-Control": "private, max-age=120"})


def scoring_words(site: str) -> list[str]:
    """The scoring in one line a rule (the screen's "How we score it"), from ``dfs.SCORING``."""
    sc = D.SCORING[site]
    out = [f"Passing: {sc['pass_yd'] * 25:g} point per 25 yards, {sc['pass_td']:g} per touchdown, {sc['pass_int']:g} per "
           "interception",
           f"Rushing and receiving: {sc['rush_yd'] * 10:g} point per 10 yards, {sc['rush_td']:g} per touchdown, "
           f"{sc['rec']:g} per catch",
           f"Fumble lost {sc['fum_lost']:g}; 2-point conversion +{sc['pass_2pt']:g}"]
    if sc.get("bonus_rush_yd_100"):
        out.append("+3 at 300 passing yards, 100 rushing yards, 100 receiving yards (priced at their odds: the chance "
                   "of reaching the mark × 3)")
    out.append("Defense: sack 1, interception 2, fumble recovery 2, touchdown 6, safety 2, blocked kick 2; points allowed "
               "0 → 10, 1–6 → 7, 7–13 → 4, 14–20 → 1, 21–27 → 0, 28–34 → −1, 35+ → −4")
    if site == "dk":
        out.append("Kicker (showdown): field goal 3 up to 39 yards, 4 for 40–49, 5 for 50+; extra point 1")
    return out


# ------------------------------------------------------------------------------------------------ the salary file
async def _body_text(request: Request) -> str:
    n = request.headers.get("content-length")
    if n and n.isdigit() and int(n) > D.MAX_BYTES + 4096:
        raise D.SlateError(f"That file is {int(n) / 1e6:.1f} MB: a salary file is under 1 MB. Export the contest's "
                           "player list again and add that file.", "too_large")
    raw = await request.body()
    if len(raw) > D.MAX_BYTES + 4096:
        raise D.SlateError(f"That file is {len(raw) / 1e6:.1f} MB: a salary file is under 1 MB.", "too_large")
    ctype = (request.headers.get("content-type") or "").lower()
    if "json" in ctype:
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise D.SlateError("The request was not the file's text.", "bad_request") from exc
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str):
            raise D.SlateError("The request was not the file's text.", "bad_request")
        return text
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


@router.post("/api/dfs/slate")
async def slate(request: Request, week: int | None = Query(default=None)):
    try:
        text = await _body_text(request)
        out = await _one_at_a_time(_slate_work, text, week)
    except Busy:
        return _busy()
    except D.SlateError as exc:
        return _err(exc, 413 if exc.code == "too_large" else 400)
    except Bad as exc:
        return _err(exc)
    # ---- IN-4: the answer grew with the context (~0.6 MB): cleaned and rendered in the thread pool
    return await run_in_threadpool(lambda: JSONResponse(_clean(out), headers=NO_STORE))


def _slate_work(text: str, week: int | None) -> dict:
    """The slate's whole answer, in a worker thread (parse, the week, price, match, value, the reasons)."""
    sl = D.parse(text)
    del text                                             # nothing of the file is kept past this request
    season = ui.current_season()
    if season is None:
        raise Bad("The numbers are not ready yet. Try again in a few minutes.", "not_ready", 503)
    sched = query(SCHEDULE_SQL, (int(season),))
    found = D.detect_week(sl.games, sched)
    try:
        season, w = _season_week(week if week is not None else found)
    except Bad as exc:
        if exc.code == "bad_week" and week is None and found is not None:
            raise Bad(f"That file's games are week {found}'s: {exc}", "bad_week") from exc
        raise
    return build_slate(sl, season, w, week_from_file=found is not None and week is None)


def build_slate(sl: D.Slate, season: int, w: int, *, week_from_file: bool) -> dict:
    """The slate's answer (the route's body): matched players valued, the unmatched listed, the lists."""
    site, contest = sl.site, sl.contest
    pr = priced(site, season, w)
    pool = pr[["key", "player_name", "position", "team"]]
    try:
        directory = query(DIRECTORY_SQL, (int(season) - 1,))
    except Exception:  # noqa: BLE001 - no directory: a player we do not project reads "not found"
        directory = None
    matched, unmatched, how = D.match(sl.players, pool, directory)
    by = pr.set_index("key")
    rows = []
    for p in sl.players:
        k = matched.get(p.key)
        if k is None:
            continue
        r = by.loc[k]
        rows.append({"key": p.key, "site_id": p.site_id, "name_id": p.name_id, "name": p.name, "our_key": k,
                     "gsis_id": r.get("gsis_id"), "player_name": r.get("player_name") or p.name, "position": p.position,
                     "team": p.team, "opponent": p.opponent, "game": p.game, "kickoff": p.kickoff,
                     "salary": p.salary, "cpt_id": p.cpt_id, "cpt_salary": p.cpt_salary, "injury": p.injury,
                     "site_avg": p.site_avg, "proj": r.get("proj"), **{q: r.get(q) for q in D.QUANTILES},
                     "report_status": r.get("report_status"), "implied_team_total": r.get("implied_team_total"),
                     "reference": r.get("reference"), **{s: r.get(s) for s in A.STAT_LINE.values()},
                     **{s: r.get(s) for s in KD_REASON if s in r.index}})
    df = pd.DataFrame(rows)
    notes = list(sl.notes)
    if df.empty:
        return {"site": site, "site_name": D.SITE_NAMES[site], "contest": contest,
                "contest_label": D.CONTESTS[contest].label, "season": season, "week": w, "games": sl.games,
                "players": [], "unmatched": unmatched, "skipped": sl.skipped, "matched_by": how, "fit": {},
                "undervalued": [], "overpriced": [], "notes": notes + ["No player on the file matched ours."],
                "cap": D.CONTESTS[contest].cap, "counts": {"on_file": len(sl.players), "matched": 0,
                                                          "unmatched": len(unmatched), "skipped": len(sl.skipped)},
                "worth_a_look": {}, "context_meta": None, "published": False, "slate_id": None}
    df = _statuses(df)
    ranks = _ranks()
    df["opp_rank"] = [ranks.get((o, p)) for o, p in zip(df["opponent"], df["position"], strict=True)]
    df, fits = D.value(df, contest)
    lists = df[df["value_call"].notna()]
    reasons = _reasons(lists, site, season, w)
    keep = ["key", "site_id", "name_id", "name", "our_key", "gsis_id", "player_name", "position", "team", "opponent",
            "game", "kickoff", "salary", "cpt_id", "cpt_salary", "proj", "p10", "p25", "p75", "p90", "pts_per_k",
            "ceil_per_k", "line_points", "value_gap", "value_z", "value_rank", "value_call", "status", "status_source",
            "out", "site_avg"]
    players = []
    for r in df.to_dict("records"):
        o = {k: r.get(k) for k in keep}
        o["matchup"] = _matchup(r, ranks)
        o["reason"] = reasons.get(r["key"])
        players.append(o)
    players.sort(key=lambda o: (-(o["proj"] or 0), o["key"]))
    players, worth_list, ctx_meta = _with_context(players, season, w, "pts_per_k")  # ---- IN-4: by value per $1,000

    def top(call: str) -> list[dict]:
        sel = [o for o in players if o["value_call"] == call]
        sel.sort(key=lambda o: (o["value_gap"] if call == "overpriced" else -o["value_gap"], o["key"]))
        return sel                                  # the screen shows 8 (by position chips); all are returned
    n_out = int(df["out"].sum())
    if n_out:
        notes.append(f"{n_out} player{'s' if n_out != 1 else ''} on the file cannot play this week (the injury report): "
                     "left out of lineups unless you lock them, and off the lists.")
    no_fit = [p for p, f in fits.items() if f is None]
    if no_fit and contest != "dk_showdown":
        notes.append(f"No salary line at {', '.join(sorted(no_fit))}: fewer than {D.FIT_MIN_PLAYERS} priced players there "
                     "on this slate.")
    elif no_fit:
        notes.append(f"No salary line: fewer than {D.FIT_MIN_PLAYERS} priced players on this slate.")
    if week_from_file:
        notes.append(f"Week {w}: the week whose games the file lists.")
    return {"site": site, "site_name": D.SITE_NAMES[site], "contest": contest, "contest_label": D.CONTESTS[contest].label,
            "cap": D.CONTESTS[contest].cap, "season": season, "week": w, "games": sl.games,
            "players": players, "unmatched": unmatched, "skipped": sl.skipped, "matched_by": how,
            "counts": {"on_file": len(sl.players), "matched": len(players), "unmatched": len(unmatched),
                       "skipped": len(sl.skipped)},
            "fit": {p: (None if f is None else {**f, "words": fit_words(p, f, site)}) for p, f in fits.items()},
            "undervalued": [o["key"] for o in top("undervalued")], "overpriced": [o["key"] for o in top("overpriced")],
            "notes": notes, "scoring": scoring_words(site), "bonus_at_odds": D.BONUS_AT_ODDS and site == "dk",
            "worth_a_look": worth_list, "context_meta": ctx_meta, "published": False, "slate_id": None}


def fit_words(position: str, f: dict, site: str) -> str:
    where = "on this slate" if position == "ALL" else f"at {position} on this slate"
    return (f"{where[0].upper()}{where[1:]}, each $1,000 of salary buys {f['slope_per_1000']:.1f} projected points "
            f"(a straight line through {f['n']} priced players; a typical player sits {f['rmse']:.1f} points off it).")


# ------------------------------------------------------------------------------------------------ lineups
@router.post("/api/dfs/lineups")
async def lineups(request: Request):
    try:
        raw = await request.body()
        if len(raw) > 2_000_000:
            raise Bad("Too many players in the request.", "too_large", 413)
        contest, players, mode, n, locks, excludes, stack, exposure, sid = _lineups_in(raw)
        outs_from = None
        if sid is not None:                              # ---- IN-4: a published slate's players, from the server
            built = await run_in_threadpool(_cached_slate, sid) or await _one_at_a_time(built_slate, sid)
            contest = built["contest"]
            players = _published_pool(built, locks)
            outs_from = built["players"]
        res = await _one_at_a_time(D.solve_lineups, players, contest, mode=mode, n=n, locks=locks, excludes=excludes,
                                   stack=stack, max_exposure=exposure)
    except Busy:
        return _busy()
    except (ValueError, TypeError, UnicodeDecodeError):
        return _err(Bad("The request was not a slate.", "bad_request"))
    except Bad as exc:
        return _err(exc)
    by = {p["key"]: p for p in players}
    out = []
    for lu in res.lineups:
        lu = dict(lu)
        lu["slots"] = [s | {"name": by[s["key"]].get("name"), "position": by[s["key"]]["position"],
                            "team": by[s["key"]].get("team"), "gsis_id": by[s["key"]].get("gsis_id"),
                            "opponent": by[s["key"]].get("opponent")} for s in lu["slots"]]
        out.append(lu)
    left_out = [{"key": p["key"], "name": p.get("name"), "status": p.get("status")} for p in (outs_from or players)
                if p.get("out") and p["key"] not in set(locks)]
    c = D.CONTESTS[contest]
    body_out = {"contest": contest, "contest_label": c.label, "cap": c.cap, "mode": mode, "lineups": out,
                "notes": res.notes, "solve_ms": res.solve_ms, "left_out": left_out, "slate_id": sid,
                "stack": None if stack is None else {"with_qb": stack.with_qb, "bring_back": stack.bring_back,
                                                     "no_def_vs_qb": stack.no_def_vs_qb},
                "max_exposure": exposure,
                "upload_csv": D.upload_csv(contest, out) if out else None,
                "filename": f"isuckatfantasy-{contest}-{len(out)}-lineups.csv"}
    return JSONResponse(_clean(body_out), headers=NO_STORE)


def _lineups_in(raw: bytes) -> tuple:
    """The lineups request, checked BEFORE any solve: a contest we know, 1-800 players each well formed, at most 16 games
    and 32 teams (a showdown: 1 game, 2 teams), 1-20 lineups, the always-in / left-out lists bounded."""
    body = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(body, dict):
        raise Bad("The request was not a slate.", "bad_request")
    stack, exposure = _stack_in(body.get("stack")), _exposure_in(body.get("max_exposure"))   # ---- IN-4
    sid = body.get("slate_id")
    if sid is not None:
        if not isinstance(sid, str) or not D.slate_id_ok(sid):
            raise Bad(NOT_PUBLISHED, "not_published", 404)
    contest = str(body.get("contest") or "")
    if sid is None and contest not in D.CONTESTS:
        raise Bad("contest is dk_classic, dk_showdown or fd_full.", "bad_contest")
    ps = body.get("players")
    if sid is not None:
        ps = None                                        # the published slate's players come from the server
    elif not isinstance(ps, list) or not ps:
        raise Bad("Add the salary file first: no players in the request.", "no_players")
    if ps is None:
        mode = "tournament" if str(body.get("mode") or "cash") == "tournament" else "cash"
        n = _n_in(body)
        locks, excludes = _picks_in(body)
        return None, [], mode, n, locks, excludes, stack, exposure, sid
    if len(ps) > D.MAX_PLAYERS:
        raise Bad(f"Too many players for one build: at most {D.MAX_PLAYERS:,} (a full Sunday slate is about 600).",
                  "too_many_players")
    players = [_player_in(p) for p in ps]
    games = {p["game"] or p["team"] for p in players}
    teams = {p["team"] for p in players}
    max_g, max_t = (1, 2) if contest == "dk_showdown" else (D.MAX_GAMES, D.MAX_TEAMS)
    if len(games) > max_g or len(teams) > max_t:
        raise Bad(f"That is {len(games)} games and {len(teams)} teams: this contest has at most {max_g} game"
                  f"{'s' if max_g != 1 else ''} and {max_t} teams.", "too_many_games")
    mode = "tournament" if str(body.get("mode") or "cash") == "tournament" else "cash"
    n = _n_in(body)
    locks, excludes = _picks_in(body)
    return contest, players, mode, n, locks, excludes, stack, exposure, None


def _n_in(body: dict) -> int:
    n = int(body.get("n") or 1)
    if not 1 <= n <= D.MAX_LINEUPS:
        raise Bad(f"Build 1 to {D.MAX_LINEUPS} lineups.", "bad_n")
    return n


def _picks_in(body: dict) -> tuple[list[str], list[str]]:
    locks, excludes = body.get("locks") or [], body.get("excludes") or []
    if not isinstance(locks, list) or not isinstance(excludes, list) or len(locks) > 9 or len(excludes) > D.MAX_PLAYERS:
        raise Bad("At most 9 players always in, and a left-out list no longer than the slate.", "bad_request")
    return [_bounded(x, "key") for x in locks], [_bounded(x, "key") for x in excludes]


def _stack_in(v: Any) -> D.Stack | None:
    """IN-4: ``{"with_qb": 0|1|2, "bring_back": bool, "no_def_vs_qb": bool}`` (a closed set), or None."""
    if v is None:
        return None
    if not isinstance(v, dict) or set(v) - {"with_qb", "bring_back", "no_def_vs_qb"}:
        raise Bad("stack is {with_qb: 0, 1 or 2, bring_back: true or false, no_def_vs_qb: true or false}.", "bad_stack")
    k = v.get("with_qb", 0)
    if isinstance(k, bool) or k not in (0, 1, 2):
        raise Bad("A stack is the quarterback with 0, 1 or 2 of his pass catchers.", "bad_stack")
    bb, nd = v.get("bring_back", False), v.get("no_def_vs_qb", False)
    if not isinstance(bb, bool) or not isinstance(nd, bool):
        raise Bad("bring_back and no_def_vs_qb are true or false.", "bad_stack")
    s = D.Stack(int(k), bb, nd)
    return s if s.any else None


def _exposure_in(v: Any) -> float | None:
    """IN-4: the most of the lineups one player may be in, a share in [0.1, 1] (1 = no limit), or None."""
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(float(v)) or not 0.1 <= float(v) <= 1:
        raise Bad("Exposure is a share between 10% and 100% of the lineups.", "bad_exposure")
    return None if float(v) >= 1 else round(float(v), 3)


def _published_pool(built: dict, locks: list[str]) -> list[dict]:
    """A published slate's players for a solve: those who can play (or are set always in) with a projection, checked
    like a client's, the highest projected first past ``MAX_PLAYERS``."""
    keep = set(locks)
    ps = [p for p in built["players"] if p.get("proj") is not None and (not p.get("out") or p["key"] in keep)]
    ps.sort(key=lambda p: (p["key"] not in keep, -(p.get("proj") or 0), p["key"]))
    trim = {"name": 80, "player_name": 80, "status": 30}
    return [_player_in({k: (v[: trim[k]] if k in trim and isinstance(v, str) else v) for k, v in _clean(p).items()})
            for p in ps[: D.MAX_PLAYERS]]


def _bounded(v: Any, what: str, size: int = LIMIT["str"]) -> str:
    s = "" if v is None else str(v)
    if len(s) > size:
        raise Bad(f"A player's {what} is longer than a salary file's.", "bad_player")
    return s


def _num(v, *, name: str, required: bool = False) -> float | None:
    if v is None:
        if required:
            raise Bad(f"A player has no {name}.", "bad_player")
        return None
    x = float(v)
    if not math.isfinite(x):
        raise Bad(f"A player's {name} is not a number.", "bad_player")
    return x


def _player_in(p: Any) -> dict:
    """One player of the slate as the client sends it back: checked, never trusted for anything but this solve."""
    if not isinstance(p, dict):
        raise Bad("A player in the request is not one.", "bad_player")
    pos = str(p.get("position") or "")
    if pos not in ("QB", "RB", "WR", "TE", "K", "DEF"):
        raise Bad("A player in the request has no position we value.", "bad_player")
    sal = _num(p.get("salary"), name="salary", required=True)
    if not 0 < sal <= 100_000:
        raise Bad("A player's salary is out of range.", "bad_player")
    cpt = _num(p.get("cpt_salary"), name="captain salary")
    if cpt is not None and not 0 < cpt <= 150_000:
        raise Bad("A player's captain salary is out of range.", "bad_player")
    nums = {k: _num(p.get(k), name=w) for k, w in (("proj", "projection"), ("p10", "low-end outcome"),
                                                   ("p90", "high-end outcome"))}
    if any(v is not None and not PROJ_RANGE[0] <= v <= PROJ_RANGE[1] for v in nums.values()):
        raise Bad("A player's projection is out of range.", "bad_player")
    key = _bounded(p.get("key"), "key")
    if not key:
        raise Bad("A player in the request has no key.", "bad_player")
    return {"key": key, "site_id": _bounded(p.get("site_id") or key, "id"),
            "cpt_id": None if p.get("cpt_id") is None else _bounded(p.get("cpt_id"), "id"),
            "name": _bounded(p.get("name") or p.get("player_name"), "name", LIMIT["name"]), "position": pos,
            "salary": int(sal), "cpt_salary": None if cpt is None else int(cpt),
            "team": _bounded(p.get("team"), "team", 4) or None, "game": _bounded(p.get("game"), "game", 20) or None,
            "opponent": _bounded(p.get("opponent"), "opponent", 4) or None,
            "gsis_id": _bounded(p.get("gsis_id"), "id", 16) or None, **nums,
            "out": bool(p.get("out")), "status": _bounded(p.get("status"), "status", 30) or None}


# ================================================================================================ IN-4 (Wave I-N)
# ------------------------------------------------------------------------------------------------ context
# The context the projection does not hold (and the parts it does, labelled): docs/DFS.md § "Context". One memo region
# (``dfs_context``): per (season, week, board source) the role trends (per player), the betting lines and the
# forecasts (per team) — ~1,300 game rows read once; the matchup comes from IN-3's ``matchup_context`` (its own cache).
ROLE_SQL = """select gsis_id, position, week, targets, team_targets, carries, team_carries, offense_snaps, offense_snap_pct,
                     routes, team_dropbacks_with_participation
              from analytics.fct_player_game
              where season = %s and season_type = 'REG' and week < %s and played
                and position in ('RB', 'WR', 'TE')"""
LINES_SQL = """select game_id, home_team, away_team, spread_line, total_line from analytics.dim_game
               where season = %s and week = %s and season_type = 'REG'"""
# Weather: the forecast is in the database (``intermediate.int_game_weather``) but the site's database role reads
# ``analytics`` / ``ops`` only and no analytics relation carries it — so no weather column (docs/DFS.md § Context;
# ``dfs.weather_flag`` is ready for the day a mart publishes the forecast). This wave ships no new relation.
_context = memo.region("dfs_context", ttl=600.0, max_entries=4)
CONTEXT_WORDS = ("Context, not a forecast: these signals sit beside the projection and do not change it. "
                 "\"Worth a look\" has no record behind it yet (no backtest).")
MATCHUP_MISSING = "Matchup: not available here."


def _matchup_fn():
    """IN-3's ``matchup_board.matchup_context``, or None when the module is not in this build (imported lazily)."""
    try:
        from . import matchup_board  # type: ignore[attr-defined]
        fn = getattr(matchup_board, "matchup_context", None)
        return fn if callable(fn) else None
    except Exception:  # noqa: BLE001 - absent or broken: the screen says "not available here"
        return None


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _context_parts(season: int, week: int) -> dict:
    """{role: {gsis: trend | None}, game: {team: env}, wx: {team: row}, lines: bool, forecast: bool} for the week,
    kept in the ``dfs_context`` region (a closed key: this week or the next, the board source)."""
    key = (int(season), int(week), A.board_source())
    hit = _context.get(key)
    if hit is not None:
        return hit
    role: dict[str, dict | None] = {}
    try:
        g = query(ROLE_SQL, (int(season), int(week)))
    except Exception:  # noqa: BLE001 - no game table: no role trend (said)
        g = pd.DataFrame()
    if not g.empty:
        g = g.copy()
        pct = pd.to_numeric(g["offense_snap_pct"], errors="coerce")
        snaps = pd.to_numeric(g["offense_snaps"], errors="coerce")
        g["team_snaps"] = (snaps / pct).where(pct > 0).round()      # the team's offensive snaps that game
        for gid, games in g.groupby("gsis_id"):
            role[str(gid)] = D.role_trend(games, str(games["position"].iloc[-1]))
    lines: dict[str, dict] = {}
    wx: dict[str, dict] = {}
    has_lines = has_wx = False
    try:
        ln = query(LINES_SQL, (int(season), int(week)))
    except Exception:  # noqa: BLE001
        ln = pd.DataFrame()
    wmap: dict = {}
    for r in ln.to_dict("records"):
        for team, home in ((r["home_team"], True), (r["away_team"], False)):
            env_ = D.game_environment(team, _f(r.get("total_line")), _f(r.get("spread_line")), home)
            if env_ is not None:
                lines[team] = env_
                has_lines = True
            if r["game_id"] in wmap:
                wx[team] = wmap[r["game_id"]]
                has_wx = has_wx or wmap[r["game_id"]].get("wx_source") == "forecast"
    out = {"role": role, "game": lines, "wx": wx, "lines": has_lines, "forecast": has_wx}
    _context.put(key, out)
    return out


def context_for(season: int, week: int, rows: list[dict], by: str = "proj") -> tuple[dict[str, dict], dict]:
    """Each row (``key``, ``gsis_id``, ``position``, ``team``, ``out`` and ``by``) -> ``{key: {context: [signals],
    worth, worth_reasons}}`` and the meta the screen states (what is available this week, what the projection holds)."""
    parts = _context_parts(season, week)
    fn = _matchup_fn()
    mc: dict[str, dict] = {}
    if fn is not None:
        try:
            ids = sorted({str(r["gsis_id"]) for r in rows if r.get("gsis_id") and r.get("position") in D.SKILL})
            mc = fn(int(season), int(week), ids) or {}
        except Exception:  # noqa: BLE001 - "never raises" is IN-3's promise; we hold it too
            mc = {}
    out: dict[str, dict] = {}
    for r in rows:
        p = r.get("position")
        if p not in D.SKILL:
            out[r["key"]] = {"context": [], "worth": False, "worth_reasons": []}
            continue
        w = parts["wx"].get(r.get("team"))
        wf = None if w is None else D.weather_flag(w.get("wx_source"), w.get("wx_dome"), _f(w.get("wx_wind_mph")),
                                                   _f(w.get("wx_precip_in")), _f(w.get("wx_temp_f")),
                                                   w.get("wx_snow"), p)
        sig = D.signals(p, mc.get(str(r.get("gsis_id"))), parts["role"].get(str(r.get("gsis_id"))),
                        parts["game"].get(r.get("team")), wf)
        ok, why = D.worth(sig)
        out[r["key"]] = {"context": sig, "worth": ok, "worth_reasons": why}
    meta = {"matchup": fn is not None and bool(mc), "matchup_words": None if fn is not None and mc else MATCHUP_MISSING,
            "lines": parts["lines"], "forecast": parts["forecast"], "projection": D.projection_table(),
            "in_words": D.IN_WORDS, "out_words": D.OUT_WORDS, "words": CONTEXT_WORDS,
            "worth_rule": (f"Worth a look: at least {D.WORTH_MIN_FAVOURABLE} favourable signals, at least "
                           f"{D.WORTH_MIN_OUTSIDE} of them not in the projection, and no difficult signal outside it.")}
    return out, meta


def _with_context(players: list[dict], season: int, week: int, by: str) -> tuple[list[dict], dict, dict]:
    ctx, meta = context_for(season, week, players, by)
    for o in players:
        o.update(ctx.get(o["key"]) or {"context": [], "worth": False, "worth_reasons": []})
    return players, D.worth_a_look(players, by=by), meta


# ------------------------------------------------------------------------------------------------ published slates
# One salary file per site per week in the repo (``dfs/slates/``; ``LEAGUE_LAB_DFS_SLATES``; ``/srv/dfs/slates`` in the
# image). Read ONCE per process (the folder ships with the image: a new file is a new deploy), parsed with the same
# parser and limits as an upload; an unreadable file is listed with its reason and never served. The id comes from a
# strict pattern (``dfs.SLATE_ID_RE``) and is looked up in what was read — never joined to a path.
_published_lock = threading.Lock()
_published: dict | None = None
_built = memo.region("dfs_published", ttl=600.0, max_entries=4)      # ~1.4 MB a built slate (measured): 4 = ~6 MB
NOT_PUBLISHED = "No published slate by that name for this week."


def slates_dir() -> Path:
    return Path(env("DFS_SLATES") or ROOT / "dfs" / "slates")


def reset_published() -> None:
    """Forget what was read (tests; a process reads the folder once)."""
    global _published
    with _published_lock:
        _published = None


def published() -> dict:
    """``{"slates": {id: {meta…, "slate": dfs.Slate}}, "unreadable": [{file, reason}]}`` — the folder, read once."""
    global _published
    with _published_lock:
        if _published is not None:
            return _published
        slates: dict[str, dict] = {}
        bad: list[dict] = []
        root = slates_dir()
        files = sorted(p for p in root.iterdir() if p.is_file()) if root.is_dir() else []
        for p in files:
            if p.name.lower() in ("readme.md", ".gitkeep") or p.name.startswith("."):
                continue
            if len(slates) + len(bad) >= D.MAX_PUBLISHED:
                bad.append({"file": p.name[:80], "reason": f"more than {D.MAX_PUBLISHED} files in the folder: this one "
                                                          "and the ones after it (by name) are not read"})
                break
            meta = D.slate_name(p.name)
            if meta is None:
                bad.append({"file": p.name[:80], "reason": "the name is not <season>-w<week>-<dk|fd>[-<label>].csv "
                                                          "(for example 2026-w05-dk.csv)"})
                continue
            if meta["id"] in slates:
                bad.append({"file": p.name, "reason": f"a second file for {meta['id']}"})
                continue
            try:
                if p.is_symlink() or p.stat().st_size > D.MAX_BYTES:
                    raise D.SlateError("over 1 MB (or a link): not a salary file", "too_large")
                sl = D.parse(p.read_bytes())
            except D.SlateError as exc:
                bad.append({"file": p.name, "reason": str(exc)})
                continue
            except OSError:
                bad.append({"file": p.name, "reason": "the file could not be read"})
                continue
            if sl.site != meta["site"]:
                bad.append({"file": p.name, "reason": f"named {D.SITE_NAMES[meta['site']]} but it is a "
                                                      f"{D.SITE_NAMES[sl.site]} file"})
                continue
            slates[meta["id"]] = {**meta, "file": p.name, "contest": sl.contest,
                                  "contest_label": D.CONTESTS[sl.contest].label, "on_file": len(sl.players), "slate": sl}
        _published = {"slates": slates, "unreadable": bad}
        return _published


def _offered(meta: dict, season: int, now: int) -> bool:
    """A published slate is offered for this week and the next only: a past week's is never offered as this week's."""
    return meta["season"] == int(season) and meta["week"] in (int(now), int(now) + 1)


def _this_week() -> tuple[int, int]:
    season = ui.current_season()
    if season is None:
        raise Bad("The numbers are not ready yet. Try again in a few minutes.", "not_ready", 503)
    now = cards.decision_week(int(season))
    if now is None:
        raise Bad("No week to show: the regular season is over.", "no_week", 404)
    return int(season), int(now)


def built_slate(slate_id: str) -> dict:
    """The published slate's answer (``build_slate`` + its id), kept in the ``dfs_published`` region (ids: a closed set,
    the files read). Raises ``Bad`` 404 for an id that is not offered."""
    if not D.slate_id_ok(slate_id):
        raise Bad(NOT_PUBLISHED, "not_published", 404)
    pub = published()["slates"].get(slate_id)
    season, now = _this_week()
    if pub is None or not _offered(pub, season, now):
        raise Bad(NOT_PUBLISHED, "not_published", 404)
    key = (slate_id, season, now, A.board_source())
    hit = _built.get(key)
    if hit is not None:
        return hit
    out = build_slate(pub["slate"], season, pub["week"], week_from_file=False)
    out.update({"slate_id": slate_id, "published": True, "label": pub["label"]})
    _built.put(key, out)
    return out


def _cached_slate(slate_id: str, week: tuple[int, int] | None = None) -> dict | None:
    """The built slate if it is kept (no build). ``week``: (season, this week) when the caller has it; otherwise read
    here — a database read, so an async route calls this through the thread pool."""
    try:
        season, now = week if week is not None else _this_week()
    except Bad:
        return None
    return _built.get((slate_id, season, now, A.board_source()))


@router.get("/api/dfs/slates")
async def slates(site: str | None = None):
    """What is published for this week (and the next): site, label, contest, the players on the file and how many we
    matched. Files of other weeks are listed as not offered; unreadable files with their reason."""
    try:
        s = _site(site) if site else None
        season, now = await run_in_threadpool(_this_week)          # database reads: off the event loop
        pub = await run_in_threadpool(published)
    except Bad as exc:
        return _err(exc)
    offered, other = [], []
    for sid, m in sorted(pub["slates"].items()):
        if s and m["site"] != s:
            continue
        if not _offered(m, season, now):
            other.append({"id": sid, "reason": f"week {m['week']} of {m['season']}: DFS offers this week (week {now}) "
                                                f"and next week only"})
            continue
        row = {k: m[k] for k in ("id", "site", "label", "season", "week", "contest", "contest_label", "on_file")}
        row["site_name"] = D.SITE_NAMES[m["site"]]
        b = _cached_slate(sid, (season, now))
        if b is None:
            try:
                b = await _one_at_a_time(built_slate, sid)
            except Busy:
                b = None
            except Bad:
                b = None
        row["matched"] = None if b is None else b["counts"]["matched"]
        row["unmatched"] = None if b is None else b["counts"]["unmatched"]
        offered.append(row)
    offered.sort(key=lambda r: (r["week"], r["site"], r["label"] != "main", r["label"]))
    return JSONResponse(_clean({"season": season, "week": now, "slates": offered, "not_offered": other,
                                "unreadable": pub["unreadable"]}),
                        headers={"Cache-Control": "private, max-age=120"})


@router.get("/api/dfs/slate/{slate_id}")
async def slate_published(slate_id: str):
    """The published slate's answer: exactly what ``POST /api/dfs/slate`` gives for that file, plus its id."""
    if not D.slate_id_ok(slate_id):
        return _err(Bad(NOT_PUBLISHED, "not_published", 404))
    hit = await run_in_threadpool(_cached_slate, slate_id)
    if hit is None:
        try:
            hit = await _one_at_a_time(built_slate, slate_id)
        except Busy:
            return _busy()
        except Bad as exc:
            return _err(exc)
    # ~0.6 MB of JSON: cleaned and rendered in the thread pool, never on the event loop
    return await run_in_threadpool(lambda: JSONResponse(_clean(hit), headers={"Cache-Control": "private, max-age=120"}))
