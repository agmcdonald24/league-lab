"""League Lab read-only API + the phone web app's static files (plan D7 spike). One process, one deploy.

    uv run uvicorn league_lab_api.main:app --port 8581          # from api/

Endpoints (all GET but login/logout; JSON; read-only role; cached 10 minutes like the app):
    /api/session                         is the gate on, is this browser signed in
    /api/login  /api/logout              the beta password → a signed cookie (or a bearer token)
    /api/leagues                         current-season leagues (ui.current_leagues)
    /api/leagues?username=               a Sleeper user's leagues this season, their team in each (plan F3)
    /api/leagues?mfl=<link or id>        a MyFantasyLeague league: its card and team picker (Wave I-0, key mfl:<id>)
    /api/leagues?sleeper=<link or id>    ---- II-5: a Sleeper league by its link or id: its card and team picker
    /api/providers                       ---- II-5: each provider's capabilities (platforms.capabilities)
    /api/leagues/{league_id}/rosters     the team picker's options
    /api/my-week?league=&team=           Home's My Week: record line, the cards (numbers + the cards' own text), lineup;
                                         a league the database does not have is served on demand from Sleeper
                                         (plan E3: ondemand.py; `source=sleeper` forces that path for a known league)
    /api/player/{gsis}?league=&team=     the player card's sections (any league: on demand, plan F3) + rest of season
    /api/ros?league=&position=&limit=    rest of season: the mart for a house league, priced on request otherwise (F3)
    /api/record?league=                  our record vs Sleeper's projections (house leagues; F3)
    /api/search?league=&q=               the player card's search box (any league: Sleeper's directory, H1)
    /api/about?league=                   About the numbers: the model, what it leans on most, its grades (H1)
    /api/status                          the freshness line, the stale-injury warning, Sleeper's cache ages + budget;
                                         ---- IH-1: `nightly` = the stale state (a missed morning update: 30 hours)
                                         ---- INF-2: `memory` = the RSS and the caches' byte budget by region
    /api/league/scoring-check?league=&week=  our points vs the league's own for a scored week (Wave I-C, IC-1)
    POST /api/usage, /api/usage/summary  ---- U-1: one count per screen view (its own read-write transaction), the counts
    /api/events?league=&team=&hours=     ---- IG-2: this roster's stored events (status moves, news, briefs; the PO's QA)
    /api/account/*                       ---- IK-4: accounts (sign-in by an emailed link, saved leagues, preferences)
Errors are {"error": "<plain words>"} (plus the older "detail"): 404 unknown league / team / player / user,
502 Sleeper did not answer, 503 the numbers are not ready yet / busy (our Sleeper budget).
Everything else is the web app (web/dist): a real file, else index.html (the app routes itself).
"""

from __future__ import annotations

import math
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from league_lab import anyleague as A
from league_lab import memo  # ---- INF-2: the memory budget
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, availability, db, myweek, news, ondemand, player, research  # availability: I0-A; news: N1
from .applib import cards, ui
from .db import DataNotReady, query
from .myweek import NotFound
from .settings import APP_NAME, web_dist

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    db.close()


app = FastAPI(title=f"{APP_NAME} API (League Lab)", version="0.1.0", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.middleware("http")
async def _give_memory_back(request: Request, call_next):
    """INF-2 (Wave I-J): after a request, hand the freed heap back to the system when the RSS grew since the last time
    (``memo.relieve``: glibc's malloc_trim, at most every few seconds; a no-op elsewhere)."""
    response = await call_next(request)
    memo.relieve()
    return response

JSON_CACHE = "private, max-age=120"


# errors: {"error": "<plain words>"} (the contract), "detail" kept for the D7 spike's web client
@app.exception_handler(NotFound)
async def _not_found(_req: Request, exc: NotFound):
    extra = {k: getattr(exc, k) for k in ("code", "fix") if getattr(exc, k, None)}   # ---- II-5: the setup errors' key
    return JSONResponse({"error": str(exc), "detail": str(exc), **extra}, status_code=404, headers={"Cache-Control": "no-store"})


@app.exception_handler(ondemand.SleeperDown)
async def _sleeper_down(_req: Request, exc: ondemand.SleeperDown):
    who = "MyFantasyLeague" if "MyFantasyLeague" in str(exc) else "Sleeper"      # I0-B: an MFL league says so
    return JSONResponse({"error": f"{who} did not answer", "detail": f"{who} did not answer. Try again in a minute.",
                         "cause": str(exc), "code": "provider_down"}, status_code=502, headers={"Cache-Control": "no-store"})  # II-5: code


@app.exception_handler(A.SleeperBusy)
async def _sleeper_busy(_req: Request, exc: A.SleeperBusy):
    return JSONResponse({"error": "busy, try again in a minute", "detail": "busy, try again in a minute", "code": "busy"}, status_code=503,  # II-5: code
                        headers={"Cache-Control": "no-store", "Retry-After": "60"})


@app.exception_handler(DataNotReady)
async def _not_ready(_req: Request, exc: DataNotReady):
    return JSONResponse({"error": "the numbers are not ready yet",
                         "detail": "This table is not on this database right now. If the data is being refreshed "
                                   "(nightly), reload in a minute or two.", "relation": str(exc)}, status_code=503,
                        headers={"Cache-Control": "no-store"})


@app.exception_handler(StarletteHTTPException)
async def _http(_req: Request, exc: StarletteHTTPException):
    return JSONResponse({"error": str(exc.detail), "detail": exc.detail}, status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))


# ---- IH-1 (Wave I-H): a 500 in the error contract's shape — plain words that name the status page (the web card
# says the same); never the exception's text. Starlette still logs the traceback and re-raises it to the server.
@app.exception_handler(Exception)
async def _server_error(_req: Request, exc: Exception):
    words = "Something broke on our side. /api/status says whether the data is up and when it was last updated."
    return JSONResponse({"error": words, "detail": words, "status": "/api/status"}, status_code=500,
                        headers={"Cache-Control": "no-store"})
# ---- end IH-1


def require_auth(request: Request) -> None:
    token = auth.token_from(request.cookies.get(auth.COOKIE), request.headers.get("authorization"))
    if not auth.valid(token):
        raise HTTPException(status_code=401, detail="Private beta. Enter the password from your invite.")


def clean(v):
    """JSON-safe: NaN / NaT → null, numpy and pandas scalars → Python (unknown is null, never 0)."""
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [clean(x) for x in v]
    if v is None or isinstance(v, str | bool):
        return v
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, int):
        return v
    if hasattr(v, "isoformat"):
        return None if pd.isna(v) else v.isoformat()
    if hasattr(v, "item"):                                  # numpy scalar
        return clean(v.item())
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def _json(data, response: Response):
    response.headers["Cache-Control"] = JSON_CACHE
    return JSONResponse(clean(data), headers={"Cache-Control": JSON_CACHE})


# ---------------------------------------------------------------- session
class Login(BaseModel):
    password: str


# ---- H0 health (plan H0, Wave H): what the host's health check and scripts/smoke.sh read --------------------------
#   GET /api/health (no password) → {"ok": true, "version": "<release stamp or git sha>", "as_of": "<the newest
#   ops.projections.fitted_at>", "board_source": "auto" | "nfl_wide" | "borrow", "database": "ok" | "unreachable: …"}
#   Always 200 while the process runs: the host restarts a process whose health check fails, and a restart does not
#   fix a database that is waking up or down — the database's state is in the body, and the smoke script fails on it.
#   as_of is read on its own short connection at most once an hour (once a minute while it fails): a health check
#   every few seconds must neither keep Neon's compute awake nor wait on the pool. version: LEAGUE_LAB_VERSION (the
#   image's build argument: the commit the GitHub workflow built), else Render's RENDER_GIT_COMMIT, else this
#   checkout's `git rev-parse`, else "dev".
import os as _os  # noqa: E402 - the block stays self-contained
import subprocess as _subprocess  # noqa: E402
import threading as _threading  # noqa: E402
import time as _time  # noqa: E402

import psycopg as _psycopg  # noqa: E402

from .settings import ROOT as _ROOT  # noqa: E402
from .settings import app_dsn as _app_dsn  # noqa: E402

_HEALTH_TTL_S, _HEALTH_RETRY_S = 3600.0, 60.0
_health_state: dict = {"as_of": None, "database": "not checked yet", "next": 0.0, "version": None}
_health_lock = _threading.Lock()


def _version() -> str:
    if _health_state["version"] is None:
        stamp = _os.environ.get("LEAGUE_LAB_VERSION", "").strip()
        if not stamp or stamp == "dev":
            stamp = _os.environ.get("RENDER_GIT_COMMIT", "").strip()[:12]
        if not stamp:
            try:
                stamp = _subprocess.run(["git", "-C", str(_ROOT), "rev-parse", "--short=12", "HEAD"], capture_output=True,
                                        text=True, timeout=2, check=True).stdout.strip()
            except (OSError, _subprocess.SubprocessError):
                stamp = ""
        _health_state["version"] = stamp or "dev"
    return _health_state["version"]


def _refresh_as_of() -> None:
    """The newest fitted_at of the decision record, on a short connection of its own (5 s to connect)."""
    try:
        with _psycopg.connect(_app_dsn(), connect_timeout=5, autocommit=True) as conn:
            row = conn.execute("select max(fitted_at) from ops.projections").fetchone()
        _health_state.update(as_of=None if row is None or row[0] is None else row[0].isoformat(), database="ok",
                             next=_time.monotonic() + _HEALTH_TTL_S)
    except _psycopg.Error as exc:
        _health_state.update(database=f"unreachable: {exc.__class__.__name__}", next=_time.monotonic() + _HEALTH_RETRY_S)


@app.get("/api/health", include_in_schema=False)
def health(response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    if _time.monotonic() >= _health_state["next"] and _health_lock.acquire(blocking=False):
        try:                                # one refresh at a time; the others answer with the last value
            _refresh_as_of()
        finally:
            _health_lock.release()
    out = {"ok": True, "version": _version(), "as_of": _health_state["as_of"], "board_source": A.board_source(),
           "database": _health_state["database"]}
    # ---- IH-1: `stale` (true when as_of is older than 30 hours: a missed nightly; null when as_of is unknown) and
    # `age_hours` - the age at the moment of the answer, so the hour-long cache of as_of never hides a missed morning
    nightly = _freshness.nightly_state(_health_state["as_of"])
    out.update(stale=nightly["stale"], age_hours=nightly["age_hours"])
    # ---- end IH-1
    return out
# ---- end H0 health


# ---- IH-1 (Wave I-H): the stale state (league_lab/freshness.py; docs/HOSTING.md § 5 "When the nightly is late or
# fails"). /api/status reads as_of on the pool at every call (it is behind the password and asked once a screen
# load, not every few seconds like the health check) and hands the newer value to the health state, so the two
# never disagree for long; a failed read falls back to the health state's last value.
from league_lab import freshness as _freshness  # noqa: E402 - the block stays self-contained


def _status_nightly() -> dict:
    try:
        df = query("select max(fitted_at) as t from ops.projections")
        t = None if df.empty or pd.isna(df["t"].iloc[0]) else pd.Timestamp(df["t"].iloc[0])
        if t is not None:
            t = (t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")).to_pydatetime()
            _health_state["as_of"] = t.isoformat()
        as_of = None if t is None else t.isoformat()
    except Exception:  # noqa: BLE001 - a status line, never a failure
        as_of = _health_state["as_of"]
    try:                                    # the words say injury statuses are live only when the overlay is on
        live = availability.enabled()
    except Exception:  # noqa: BLE001
        live = False
    return _freshness.nightly_state(as_of, live_injuries=live)
# ---- end IH-1


@app.get("/api/session")
def session(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    token = auth.token_from(request.cookies.get(auth.COOKIE), request.headers.get("authorization"))
    return {"gate": auth.gate_on(), "signed_in": auth.valid(token)}


@app.post("/api/login")
def login(body: Login, request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    if not auth.gate_on():
        return {"ok": True, "token": None}
    if not auth.check_password(body.password):
        raise HTTPException(status_code=401, detail="That is not it.")
    token = auth.issue()
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(auth.COOKIE, token, max_age=auth.TOKEN_DAYS * 86400, httponly=True, samesite="lax",
                        secure=secure, path="/")
    return {"ok": True, "token": token}


@app.post("/api/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


# ---------------------------------------------------------------- data (read-only)
# ---- I0-B (Wave I-0): `?mfl=<league link or id>` = a MyFantasyLeague league (ondemand.mfl_league); league keys may be
# `mfl:<id>` (anyleague.check_id accepts both; known_league is false for them: always served on demand).
# I0-C: `?mfl_search=<link, id or the league's name>` (ondemand.mfl_search): a link or an id answers as `?mfl=`.
@app.get("/api/leagues", dependencies=[Depends(require_auth)])
def leagues(response: Response, username: str | None = None, mfl: str | None = None, mfl_search: str | None = None,
            sleeper: str | None = None):
    if sleeper is not None:                    # ---- II-5: a Sleeper league link or id -> its card and team picker
        return _json(ondemand.sleeper_league(sleeper), response)
    if mfl_search is not None:
        return _json(ondemand.mfl_search(mfl_search), response)
    if mfl is not None:
        return _json(ondemand.mfl_league(mfl), response)
    if username is None:
        return _json(myweek.leagues(), response)
    return _json(ondemand.leagues_for_user(username), response)


# ---- II-5 (Wave I-I): what each provider gives (platforms.capabilities; docs/PROVIDERS.md) — the setup screen's
# "what works on MFL" lines and any screen's "not available for MFL leagues yet". Static: cached like the app's JSON.
@app.get("/api/providers", dependencies=[Depends(require_auth)])
def providers(response: Response):
    return _json({"providers": A.platforms.all_capabilities(), "features": list(A.platforms.FEATURES)}, response)
# ---- end II-5


@app.get("/api/leagues/{league_id}/rosters", dependencies=[Depends(require_auth)])
def rosters(league_id: str, response: Response, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league_id):
        return _json(ondemand.rosters_for_league(league_id), response)
    return _json(myweek.rosters(league_id), response)
# ---- end I0-B


# ---- IA-3 (Wave I-A): `market_points` on My Week's lineup rows (Sleeper's number for the week, this league's
# scoring; None where the market mart has no row — why.market_points)
def why_market_rows(out: dict, league: str, *, house: bool) -> dict:
    from . import why
    try:
        rows = [r for k in ("lineup", "lineup_full") for r in (out.get(k) or [])]
        if not rows:
            return out
        if house:
            season, scoring = ondemand._scoring_of(league, None, True)
        else:
            season, scoring = ondemand._scoring_of(league, ondemand.A.sleeper().league(league), False)
        week = out.get("week")
        m = ({} if ondemand.A.platforms.is_mfl(league)                   # ---- IE-0: Sleeper's number, not on MFL
             else why.market_points(season, week, [r.get("gsis_id") for r in rows], scoring))
    except Exception:  # noqa: BLE001 - My Week never fails for the market line
        m = {}
    for k in ("lineup", "lineup_full"):
        for r in out.get(k) or []:
            r["market_points"] = m.get(str(r.get("gsis_id"))) if r.get("gsis_id") else None
    return out
# ---- end IA-3


@app.get("/api/my-week", dependencies=[Depends(require_auth)])
def my_week(league: str, team: int, response: Response, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league):
        return _json(why_market_rows(ondemand.my_week(league, team), league, house=False), response)   # ---- IA-3
    return _json(why_market_rows(myweek.my_week(league, team), league, house=True), response)         # ---- IA-3


@app.get("/api/player/{gsis}", dependencies=[Depends(require_auth)])
def player_card(gsis: str, league: str, response: Response, team: int | None = None, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league):
        out = ondemand.player_card(league, gsis)
    else:
        out = player.player_card(league, gsis)
    out["viewer_roster_id"] = team
    return _json(out, response)


@app.get("/api/ros", dependencies=[Depends(require_auth)])
def ros(league: str, response: Response, position: str = "ALL", limit: int = 50,
        view: str = "points", team: int | None = None, who: str = "all"):          # ---- IB-3: view=lineup&team=
    return _json(ondemand.ros(league, position, limit, view=view, team=team, who=who), response)


@app.exception_handler(ondemand.BadView)                                              # ---- IB-3
async def _bad_view(_req: Request, exc: ondemand.BadView):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/api/record", dependencies=[Depends(require_auth)])
def record(league: str, response: Response, team: int | None = None):   # ---- V-2: `team` -> decisions.team
    return _json(ondemand.record(league, team=team), response)


@app.get("/api/search", dependencies=[Depends(require_auth)])
def search(league: str, q: str, response: Response, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league):     # H1: any league - Sleeper's directory (research.py)
        return _json(research.search_on_demand(league, q), response)
    return _json(player.search(league, q), response)


@app.get("/api/status", dependencies=[Depends(require_auth)])
def status(response: Response):
    out = myweek.status()
    # ---- I0-A: the availability overlay's stamp; the stale-injury warning goes when ESPN was read within the hour
    try:
        out["availability"] = availability.info()
        if availability.fresh():
            out["warning"] = None
    except Exception as exc:  # noqa: BLE001 - a status line, never a failure
        out["availability"] = {"enabled": availability.enabled(), "error": exc.__class__.__name__}
    # ---- end I0-A
    try:                                    # ---- N1: the news line's feed (calls, failures, cached athletes)
        out["news"] = news.info()
    except Exception as exc:  # noqa: BLE001 - a status line, never a failure
        out["news"] = {"enabled": news.enabled(), "error": exc.__class__.__name__}
    try:                                    # ---- IG-2: the event store (rows, the newest, this process's writer)
        from . import events as _events
        out["events"] = _events.info()
    except Exception as exc:  # noqa: BLE001 - a status line, never a failure
        out["events"] = {"enabled": False, "error": exc.__class__.__name__}
    out["nightly"] = _status_nightly()      # ---- IH-1: {as_of, age_hours, stale, limit_hours, words}
    out["sleeper"] = A.sleeper().stats()
    out["board_source"] = A.board_source()
    try:                                    # QA: the setting is "auto"; say which board the current week really uses
        season = int(ui.current_season())
        week = cards.decision_week(season)
        out["board_source_in_use"] = None if week is None else A.load_board(query, season, week).source
    except Exception as exc:  # noqa: BLE001 - a status line, never a failure
        out["board_source_in_use"] = f"unknown ({exc.__class__.__name__})"
    out["memory"] = memory_status()          # ---- INF-2: the server's RSS and the caches' budget, region by region
    return _json(out, response)


def memory_status() -> dict:
    """INF-2 (Wave I-J, the memory diet): {rss_mb, cache_mb, budget_mb, regions: {name: MB}, entries, evictions, trims,
    malloc_arena_max, outside_mb} — the process's resident memory (what Render meters against the plan's 512 MB) next to what the
    in-process caches hold in ``league_lab.memo``'s one budget (``LEAGUE_LAB_CACHE_MB``)."""
    import os
    try:
        out = {"rss_mb": memo.rss_mb(), **memo.BUDGET.report(), **memo.relief(),
               "malloc_arena_max": os.environ.get("MALLOC_ARENA_MAX")}
    except Exception as exc:  # noqa: BLE001 - a status line, never a failure
        return {"error": exc.__class__.__name__}
    # outside the budget: the platform clients' own caches (Sleeper's player directory for the day, MFL's payloads)
    try:
        router = A.sleeper()
        mfl = getattr(getattr(router, "_mfl", None), "client", None) or getattr(router, "_mfl_client", None)
        out["outside_mb"] = {name: round(memo.sizeof(c._cache) / 1048576, 1)
                             for name, c in (("sleeper", getattr(router, "sleeper", None)), ("mfl", mfl))
                             if isinstance(getattr(c, "_cache", None), dict)}
    except Exception:  # noqa: BLE001
        out["outside_mb"] = {}
    return out


# ---- G1 research (plan G1, Wave G: league_lab_api/research.py; README § Research (G1)) ---------------------------
@app.exception_handler(research.BadRequest)
async def _bad_request(_req: Request, exc: research.BadRequest):
    return JSONResponse({"error": str(exc), "detail": str(exc)}, status_code=400, headers={"Cache-Control": "no-store"})


@app.get("/api/trends", dependencies=[Depends(require_auth)])
def trends(league: str, response: Response, position: str = "ALL", limit: int = 50, view: str = "all",
           season: int | None = None, who: str = "all", team: int | None = None, min_games: int = 1,
           sort: str | None = None, dir: str | None = None, metrics: str = "moved", source: str | None = None):
    return _json(research.trends(league, position=position, limit=limit, view=view, season=season, who=who, team=team,
                                 min_games=min_games, sort=sort, dir=dir, metrics=metrics, source=source), response)


@app.get("/api/matchups/defense", dependencies=[Depends(require_auth)])
def matchups_defense(league: str, response: Response, position: str = "ALL", source: str | None = None, team: int | None = None):
    return _json(research.matchups_defense(league, position=position, source=source, team=team), response)


@app.get("/api/matchups/cb", dependencies=[Depends(require_auth)])
def matchups_cb(league: str, response: Response, team: int | None = None, limit: int = 50, source: str | None = None):
    return _json(research.matchups_cb(league, team=team, limit=limit, source=source), response)


@app.get("/api/players", dependencies=[Depends(require_auth)])
def players(league: str, response: Response, season: int | None = None, position: str = "ALL", sort: str | None = None,
            dir: str | None = None, limit: int = 50, offset: int = 0, q: str | None = None, season_type: str = "REG",
            min_games: int = 1, source: str | None = None, window: str | None = None, basis: str | None = None,
            weeks: str | None = None, who: str | None = None, team: int | None = None, nfl: str | None = None):  # ---- II-3
    return _json(research.players(league, season=season, position=position, sort=sort, dir=dir, limit=limit, offset=offset,
                                  q=q, season_type=season_type, min_games=min_games, source=source, window=window,
                                  basis=basis, weeks=weeks, who=who, team=team, nfl=nfl), response)


@app.get("/api/receivers", dependencies=[Depends(require_auth)])
def receivers(league: str, response: Response, season: int | None = None, limit: int = 50, season_type: str = "REG",
              weeks: str | None = None, players: str | None = None, context: str = "half", source: str | None = None):
    return _json(research.receivers(league, season=season, limit=limit, season_type=season_type, weeks=weeks,
                                    players=players, context_type=context, source=source), response)


@app.get("/api/compare", dependencies=[Depends(require_auth)])
def compare(league: str, a: str, b: str, response: Response, source: str | None = None):
    return _json(research.compare(league, a, b, source=source), response)


@app.get("/api/player/{gsis}/games", dependencies=[Depends(require_auth)])
def player_games(gsis: str, league: str, response: Response, season: int | None = None, season_type: str = "ALL",
                 source: str | None = None):
    return _json(research.player_games(league, gsis, season=season, season_type=season_type, source=source), response)
# ---- end G1 research

# ---- G2 decisions (Wave G): waivers, trades, the Team Hub, the league - a house league from the marts, any other on demand
#   /api/waivers?league=&team=&position=&limit=&offset=   the claims that improve a lineup + the priced free agents
#   POST /api/trades/evaluate {league, team, partner, give, get}   both rosters before / after, fit, market, verdict
#   /api/trades/partners?league=&team=&want=              the partner finder (the best trade both lineups gain from)
#   /api/team?league=&team=                               Team Hub: roster value, ranks, slot strength, the horizon
#   /api/league?league=&team=&limit=&offset=              standings, all-play and luck, transactions
from . import decisions  # noqa: E402 - the block stays self-contained (G1 / G2 append to this file in parallel)


class TradeBody(BaseModel):
    league: str
    team: int
    partner: int | None = None
    give: list[str] = []
    get: list[str] = []
    window: str | None = None          # ---- IA-2: week | next4 (default) | ros | playoffs


@app.exception_handler(decisions.BadRequest)
async def _bad_request(_req: Request, exc: decisions.BadRequest):
    extra = {"unavailable": exc.items} if isinstance(exc, decisions.Unavailable) else {}      # ---- IE-0
    return JSONResponse({"error": str(exc), "detail": str(exc), **extra}, status_code=400, headers={"Cache-Control": "no-store"})


@app.get("/api/waivers", dependencies=[Depends(require_auth)])
def waivers(league: str, response: Response, team: int | None = None, position: str | None = None, limit: int = 50,
            offset: int = 0, source: str | None = None):
    return _json(decisions.waivers(league, team, position, limit, offset, source=source), response)


@app.post("/api/trades/evaluate", dependencies=[Depends(require_auth)])
def trades_evaluate(body: TradeBody, response: Response, source: str | None = None):
    out = decisions.evaluate(body.league, body.team, body.partner, body.give, body.get, source=source, window=body.window)
    response.headers["Cache-Control"] = "no-store"
    return JSONResponse(clean(out), headers={"Cache-Control": "no-store"})


@app.get("/api/trades/partners", dependencies=[Depends(require_auth)])
def trades_partners(league: str, team: int, response: Response, want: str | None = None, source: str | None = None,
                    window: str | None = None):
    return _json(decisions.partners(league, team, want, source=source, window=window), response)


# ---- IA-2 (Wave I-A): buy low / sell high moved from /api/waivers to the Trades screen
#   /api/trades/lists?league=&team=&position=               buy low (other rosters), sell high (yours), the best per position
@app.get("/api/trades/lists", dependencies=[Depends(require_auth)])
def trades_lists(league: str, team: int, response: Response, position: str | None = None, source: str | None = None):
    return _json(decisions.trade_lists(league, team, position, source=source), response)
# ---- end IA-2


@app.get("/api/team", dependencies=[Depends(require_auth)])
def team_hub(league: str, team: int, response: Response, source: str | None = None):
    return _json(decisions.team(league, team, source=source), response)


@app.get("/api/league", dependencies=[Depends(require_auth)])
def league_page(league: str, response: Response, team: int | None = None, limit: int = 50, offset: int = 0,
                source: str | None = None):
    return _json(decisions.league(league, team, limit, offset, source=source), response)


# ---- H1 (Wave H): "About the numbers" - the model, what it leans on most, its grades (league_lab_api/about.py)
#   /api/about?league=          importance (mart_projection_importance) + grades (mart_projection_drift / _backtest)
from . import about as about_mod  # noqa: E402 - the block stays self-contained (Wave H devs append in parallel)


@app.get("/api/about", dependencies=[Depends(require_auth)])
def about(league: str, response: Response, source: str | None = None):
    return _json(about_mod.about(league, source=source), response)
# ---- end H1

# ---- IC-1 (Wave I-C): the scoring check — our points against the league's own for a scored week
#   /api/league/scoring-check?league=&week=     league_lab.scoring_audit.check (default: the last complete week)
SCORING_CHECK_TTL_S = 24 * 3600.0        # a scored week does not change; the stat corrections land overnight
_scoring_checks = memo.region("scoring_checks", ttl=SCORING_CHECK_TTL_S)   # INF-2: in the memory budget (was 200 entries)


@app.get("/api/league/scoring-check", dependencies=[Depends(require_auth)])
def scoring_check(league: str, response: Response, week: int | None = None):
    from league_lab import scoring_audit
    key = (str(league), week)
    hit = _scoring_checks.get(key)
    if hit is not None:
        return _json(hit, response)
    try:
        lid = A.check_id(league)
        lg = A.sleeper().league(lid)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc)) from exc
    except A.SleeperUnavailable as exc:
        raise ondemand.SleeperDown(str(exc)) from exc
    router = A.sleeper()
    mfl = router.mfl.client if str(lid).startswith("mfl:") else None
    try:
        out = scoring_audit.check(query, lg, week, client=router, mfl_client=mfl)
    except A.SleeperUnavailable as exc:
        raise ondemand.SleeperDown(str(exc)) from exc
    out["name"] = lg.get("name")
    _scoring_checks.put(key, out)
    return _json(out, response)
# ---- end IC-1

# ---- U-1 (Wave I-F): usage tracking (league_lab_api/usage.py; docs/HOSTING.md § "Usage")
#   POST /api/usage {screen, league, roster_id}   one row in usage.events per screen view; always 204. The server adds
#                                                 the time, the platform, the version and the day's session cookie.
#   GET  /api/usage/summary?days=7                views per screen per day, leagues and sessions per day (the PO's QA)
from . import usage as usage_mod  # noqa: E402 - the block stays self-contained


@app.post("/api/usage", status_code=204, dependencies=[Depends(require_auth)], include_in_schema=False)
async def usage_count(request: Request):
    resp = Response(status_code=204, headers={"Cache-Control": "no-store"})
    if not usage_mod.enabled():
        return resp
    body = await request.body()
    session = usage_mod.session_from(request.cookies.get(usage_mod.COOKIE))
    if session is None:
        session = usage_mod.new_session()
        secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        resp.set_cookie(usage_mod.COOKIE, session, max_age=usage_mod.seconds_left_today(), httponly=True,
                        samesite="lax", secure=secure, path="/api/usage")
    if usage_mod.allow(session):
        usage_mod.submit(usage_mod.event(usage_mod.parse(body), version=_version(), session=session))   # its own thread
    return resp


@app.get("/api/usage/summary", dependencies=[Depends(require_auth)])
def usage_summary(response: Response, days: int = 7):
    response.headers["Cache-Control"] = "no-store"
    return JSONResponse(clean(usage_mod.summary(days)), headers={"Cache-Control": "no-store"})
# ---- end U-1

# ---- IG-2 (Wave I-G): the event store (league_lab_api/events.py; docs/HOSTING.md § "Events")
#   GET /api/events?league=&team=&hours=72   this roster's players' stored events of the last `hours` (1–720), newest
#                                            first, live and superseded (`live` says which): the PO's QA of the store
from . import events as events_mod  # noqa: E402 - the block stays self-contained


@app.get("/api/events", dependencies=[Depends(require_auth)])
def events_list(league: str, team: int, response: Response, hours: int = 72):
    hours = max(1, min(int(hours), 720))
    out: dict = {"league": league, "team": int(team), "hours": hours, "enabled": events_mod.enabled(), "players": 0,
                 "events": []}
    ctx = availability.roster_context(league, int(team))
    if ctx is None:
        return JSONResponse(clean(out), headers={"Cache-Control": "no-store"})
    rows = ctx.rows[ctx.rows["role"].isin(["starter", "bench", "unplayable"]) & ctx.rows["gsis_id"].map(
        lambda g: isinstance(g, str) and bool(g))]
    names = dict(zip(rows["gsis_id"], rows["player_name"], strict=False))
    out["players"] = len(names)
    evs = events_mod.recent(list(names), hours=hours, live_only=False)
    out["events"] = [{**{k: v for k, v in e.items() if k != "fingerprint"}, "player_name": names.get(e["gsis_id"])}
                     for e in evs]
    out["live"] = sum(1 for e in evs if e["live"])
    return JSONResponse(clean(out), headers={"Cache-Control": "no-store"})
# ---- end IG-2

# ---- IH-3 (Wave I-H): the League screen's odds for this week's games (myweek.week_odds; information, never a pick),
#   /api/league/week-odds?league=      asked by the screen after it shows (on demand: one solve per roster, 1-3 s cold)


@app.get("/api/league/week-odds", dependencies=[Depends(require_auth)])
def league_week_odds(league: str, response: Response, source: str | None = None):
    return _json(myweek.week_odds(league, house=False if source == "sleeper" else None), response)
# ---- end IH-3


# ---- IK-4 (Wave I-K): accounts, phase 1 (league_lab_api/accounts.py; docs/ACCOUNTS.md § "Built, phase 1")
#   GET  /api/account/status                {enabled, reason, signed_in, email, mailer}: the web shows sign-in when enabled
#   POST /api/account/login {email}         a single-use sign-in link by email (Resend); the same answer for any address
#   POST /api/account/verify {token}        the link's token (from the page's URL fragment) -> the ll_session cookie
#   POST /api/account/logout {everywhere}   this session, or every session of the account
#   GET  /api/account/me                    the saved leagues, the default, preferences, the watchlist
#   PUT  /api/account/leagues, DELETE /api/account/leagues/{league}, PUT /api/account/default
#   PUT / DELETE /api/account/preferences, PUT / DELETE /api/account/watchlist, DELETE /api/account
# Behind the beta password like every route (the gate stays in front). LEAGUE_LAB_ACCOUNTS=off|auto|on.
from . import accounts as accounts_mod  # noqa: E402 - the block stays self-contained


@app.exception_handler(accounts_mod.AccountError)
async def _account_error(_req: Request, exc: accounts_mod.AccountError):
    return accounts_mod.error_response(exc)


app.include_router(accounts_mod.router, dependencies=[Depends(require_auth)])
# ---- end IK-4


# ---------------------------------------------------------------- the web app
ASSET_CACHE = "public, max-age=31536000, immutable"     # vite's hashed file names
SHELL_CACHE = "no-cache"                                # index.html, sw.js, manifest: revalidate every load


@app.api_route("/api/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
def api_404(rest: str):
    raise HTTPException(status_code=404, detail=f"no endpoint /api/{rest}")


@app.get("/{path:path}", include_in_schema=False)
def web(path: str):
    dist = web_dist().resolve()
    index = dist / "index.html"
    if not index.exists():
        return PlainTextResponse("The web app is not built: cd web && npm ci && npm run build", status_code=404)
    if path:
        f = (dist / path).resolve()
        if f.is_file() and dist in f.parents:
            cache = ASSET_CACHE if Path(path).parts[0] == "assets" else SHELL_CACHE
            return FileResponse(f, headers={"Cache-Control": cache})
        if Path(path).suffix and Path(path).parts[0] in ("assets", "icons"):
            raise HTTPException(status_code=404)
    return FileResponse(index, headers={"Cache-Control": SHELL_CACHE})
