"""DFS on the API (Wave I-M, IM-5; docs/DFS.md): the site's salary file in, values and lineups out. No league, no team,
no stored salary: every route works for a visitor who has opened no league.

* ``GET  /api/dfs/projections?site=dk|fd&week=``  this week's players in the site's scoring, ranked, with the range —
  before anyone adds a file.
* ``POST /api/dfs/slate?week=``                  the salary file's text as the body (or JSON ``{"text": …}``) →
  ``{site, contest, week, games, players, unmatched, fit, undervalued, overpriced, notes}``. Stateless: the file is
  parsed in memory, never stored or logged (no logging call here touches it).
* ``POST /api/dfs/lineups``                       the slate's players as returned + locks / excludes / mode / n →
  the lineups (salary, projection, range) and the site's lineup-upload CSV.

Rate limiting: ``RATE_BUCKETS`` names the bucket of each route in IM-3's limiter terms (``heavy`` for the two POSTs:
they parse a file and solve integer programs) — the PO wires it at the merge. One ``league_lab.memo`` region
(``dfs``): the week's board priced per site (``dfs.price_site``), ~0.2 MB a site-week.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from league_lab import anyleague as A
from league_lab import dfs as D
from league_lab import memo

from . import availability
from .applib import cards, ui
from .db import query

router = APIRouter()
RATE_BUCKETS = {"/api/dfs/slate": "heavy", "/api/dfs/lineups": "heavy", "/api/dfs/projections": "read"}
NO_STORE = {"Cache-Control": "no-store"}
_priced = memo.region("dfs", ttl=600.0, max_entries=8)

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
    season = ui.current_season()
    if season is None:
        raise Bad("The numbers are not ready yet. Try again in a few minutes.", "not_ready", 503)
    w = int(week) if week is not None else cards.decision_week(int(season))
    if w is None or not 1 <= int(w) <= 22:
        raise Bad("No week to show: the regular season is over.", "no_week", 404)
    return int(season), int(w)


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
    body = {"site": s, "site_name": D.SITE_NAMES[s], "season": season, "week": w, "players": players,
            "count": len(players), "reference": refs[0] if refs else None,
            "scoring": scoring_words(s), "bonus_at_odds": D.BONUS_AT_ODDS and s == "dk"}
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
        sl = D.parse(text)
        del text                                         # nothing of the file is kept past this request
        season = ui.current_season()
        if season is None:
            raise Bad("The numbers are not ready yet. Try again in a few minutes.", "not_ready", 503)
        sched = query(SCHEDULE_SQL, (int(season),))
        found = D.detect_week(sl.games, sched)
        season, w = _season_week(week if week is not None else found)
    except D.SlateError as exc:
        return _err(exc, 413 if exc.code == "too_large" else 400)
    except Bad as exc:
        return _err(exc)
    out = build_slate(sl, season, w, week_from_file=found is not None and week is None)
    return JSONResponse(_clean(out), headers=NO_STORE)


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
                "cap": D.CONTESTS[contest].cap}
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
            "notes": notes, "scoring": scoring_words(site), "bonus_at_odds": D.BONUS_AT_ODDS and site == "dk"}


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
        body = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(body, dict):
            raise Bad("The request was not a slate.", "bad_request")
        contest = str(body.get("contest") or "")
        if contest not in D.CONTESTS:
            raise Bad("contest is dk_classic, dk_showdown or fd_full.", "bad_contest")
        ps = body.get("players")
        if not isinstance(ps, list) or not ps or len(ps) > D.MAX_ROWS:
            raise Bad("Add the salary file first: no players in the request.", "no_players")
        players = [_player_in(p) for p in ps]
        mode = "tournament" if str(body.get("mode") or "cash") == "tournament" else "cash"
        n = int(body.get("n") or 1)
        if not 1 <= n <= D.MAX_LINEUPS:
            raise Bad(f"Build 1 to {D.MAX_LINEUPS} lineups.", "bad_n")
        locks = [str(x) for x in (body.get("locks") or [])][:9]
        excludes = [str(x) for x in (body.get("excludes") or [])][: D.MAX_ROWS]
    except (ValueError, TypeError, UnicodeDecodeError):
        return _err(Bad("The request was not a slate.", "bad_request"))
    except Bad as exc:
        return _err(exc)
    res = D.solve_lineups(players, contest, mode=mode, n=n, locks=locks, excludes=excludes)
    by = {p["key"]: p for p in players}
    out = []
    for lu in res.lineups:
        lu = dict(lu)
        lu["slots"] = [s | {"name": by[s["key"]].get("name"), "position": by[s["key"]]["position"],
                            "team": by[s["key"]].get("team"), "gsis_id": by[s["key"]].get("gsis_id"),
                            "opponent": by[s["key"]].get("opponent")} for s in lu["slots"]]
        out.append(lu)
    left_out = [{"key": p["key"], "name": p.get("name"), "status": p.get("status")} for p in players
                if p.get("out") and p["key"] not in set(locks)]
    c = D.CONTESTS[contest]
    body_out = {"contest": contest, "contest_label": c.label, "cap": c.cap, "mode": mode, "lineups": out,
                "notes": res.notes, "solve_ms": res.solve_ms, "left_out": left_out,
                "upload_csv": D.upload_csv(contest, out) if out else None,
                "filename": f"isuckatfantasy-{contest}-{len(out)}-lineups.csv"}
    return JSONResponse(_clean(body_out), headers=NO_STORE)


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
    return {"key": str(p.get("key"))[:40], "site_id": str(p.get("site_id") or p.get("key"))[:40],
            "cpt_id": None if p.get("cpt_id") is None else str(p.get("cpt_id"))[:40],
            "name": str(p.get("name") or p.get("player_name") or "")[:80], "position": pos, "salary": int(sal),
            "cpt_salary": None if cpt is None else int(cpt), "team": str(p.get("team") or "")[:4] or None,
            "game": str(p.get("game") or "")[:20] or None, "opponent": str(p.get("opponent") or "")[:4] or None,
            "gsis_id": str(p.get("gsis_id") or "")[:16] or None, "proj": _num(p.get("proj"), name="projection"),
            "p10": _num(p.get("p10"), name="low-end outcome"), "p90": _num(p.get("p90"), name="high-end outcome"),
            "out": bool(p.get("out")), "status": str(p.get("status") or "")[:30] or None}
