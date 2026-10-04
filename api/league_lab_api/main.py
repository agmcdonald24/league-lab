"""League Lab read-only API + the phone web app's static files (plan D7 spike). One process, one deploy.

    uv run uvicorn league_lab_api.main:app --port 8581          # from api/

Endpoints (all GET but login/logout; JSON; read-only role; cached 10 minutes like the app):
    /api/session                         is the gate on, is this browser signed in
    /api/login  /api/logout              the beta password → a signed cookie (or a bearer token)
    /api/leagues                         current-season leagues (ui.current_leagues)
    /api/leagues?username=               a Sleeper user's leagues this season, their team in each (plan F3)
    /api/leagues?mfl=<link or id>        a MyFantasyLeague league: its card and team picker (Wave I-0, key mfl:<id>)
    /api/leagues/{league_id}/rosters     the team picker's options
    /api/my-week?league=&team=           Home's My Week: record line, the cards (numbers + the cards' own text), lineup;
                                         a league the database does not have is served on demand from Sleeper
                                         (plan E3: ondemand.py; `source=sleeper` forces that path for a known league)
    /api/player/{gsis}?league=&team=     the player card's sections (any league: on demand, plan F3) + rest of season
    /api/ros?league=&position=&limit=    rest of season: the mart for a house league, priced on request otherwise (F3)
    /api/record?league=                  our record vs Sleeper's projections (house leagues; F3)
    /api/search?league=&q=               the player card's search box (any league: Sleeper's directory, H1)
    /api/about?league=                   About the numbers: the model, what it leans on most, its grades (H1)
    /api/status                          the freshness line, the stale-injury warning, Sleeper's cache ages + budget
    /api/league/scoring-check?league=&week=  our points vs the league's own for a scored week (Wave I-C, IC-1)
    POST /api/usage, /api/usage/summary  ---- U-1: one count per screen view (its own read-write transaction), the counts
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

JSON_CACHE = "private, max-age=120"


# errors: {"error": "<plain words>"} (the contract), "detail" kept for the D7 spike's web client
@app.exception_handler(NotFound)
async def _not_found(_req: Request, exc: NotFound):
    return JSONResponse({"error": str(exc), "detail": str(exc)}, status_code=404, headers={"Cache-Control": "no-store"})


@app.exception_handler(ondemand.SleeperDown)
async def _sleeper_down(_req: Request, exc: ondemand.SleeperDown):
    who = "MyFantasyLeague" if "MyFantasyLeague" in str(exc) else "Sleeper"      # I0-B: an MFL league says so
    return JSONResponse({"error": f"{who} did not answer", "detail": f"{who} did not answer. Try again in a minute.",
                         "cause": str(exc)}, status_code=502, headers={"Cache-Control": "no-store"})


@app.exception_handler(A.SleeperBusy)
async def _sleeper_busy(_req: Request, exc: A.SleeperBusy):
    return JSONResponse({"error": "busy, try again in a minute", "detail": "busy, try again in a minute"}, status_code=503,
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
    return {"ok": True, "version": _version(), "as_of": _health_state["as_of"], "board_source": A.board_source(),
            "database": _health_state["database"]}
# ---- end H0 health


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
def leagues(response: Response, username: str | None = None, mfl: str | None = None, mfl_search: str | None = None):
    if mfl_search is not None:
        return _json(ondemand.mfl_search(mfl_search), response)
    if mfl is not None:
        return _json(ondemand.mfl_league(mfl), response)
    if username is None:
        return _json(myweek.leagues(), response)
    return _json(ondemand.leagues_for_user(username), response)


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
def record(league: str, response: Response):
    return _json(ondemand.record(league), response)


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
    out["sleeper"] = A.sleeper().stats()
    out["board_source"] = A.board_source()
    try:                                    # QA: the setting is "auto"; say which board the current week really uses
        season = int(ui.current_season())
        week = cards.decision_week(season)
        out["board_source_in_use"] = None if week is None else A.load_board(query, season, week).source
    except Exception as exc:  # noqa: BLE001 - a status line, never a failure
        out["board_source_in_use"] = f"unknown ({exc.__class__.__name__})"
    return _json(out, response)


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
            min_games: int = 1, source: str | None = None):
    return _json(research.players(league, season=season, position=position, sort=sort, dir=dir, limit=limit, offset=offset,
                                  q=q, season_type=season_type, min_games=min_games, source=source), response)


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
_scoring_checks: dict[tuple[str, int | None], tuple[float, dict]] = {}
SCORING_CHECK_TTL_S = 24 * 3600.0        # a scored week does not change; the stat corrections land overnight


@app.get("/api/league/scoring-check", dependencies=[Depends(require_auth)])
def scoring_check(league: str, response: Response, week: int | None = None):
    import time as _t

    from league_lab import scoring_audit
    key = (str(league), week)
    hit = _scoring_checks.get(key)
    if hit is not None and hit[0] > _t.monotonic():
        return _json(hit[1], response)
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
    if len(_scoring_checks) > 200:
        _scoring_checks.clear()
    _scoring_checks[key] = (_t.monotonic() + SCORING_CHECK_TTL_S, out)
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
