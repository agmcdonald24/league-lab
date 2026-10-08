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
                                         ---- IK-3: + espn_private, yahoo_configured
    /api/leagues?espn=<link or id>       ---- IK-3: an ESPN league (`espn:<id>`): its card and team picker
    /api/leagues?yahoo=<link, key or id> ---- IK-3: a Yahoo league (`yahoo:<game>.l.<id>`): its card and team picker
    /api/leagues?yahoo_me=1              ---- IK-3: the signed-in user's Yahoo leagues (IK-2's `ll_yahoo` cookie)
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
    /api/account/watchlist?league=&team= ---- IL-5: the saved players in one league (the watchlist screen)
    /api/ratelimit                       ---- IM-3: how this request was keyed by the rate limiter (never the address)
---- IM-3 (Wave I-M): the gate is a switch (LEAGUE_LAB_GATE = open | password; auth.py), every /api/ route but the
health check is rate-limited (ratelimit.py), cross-site writes, oversized bodies and the response headers are the
Guard's (security.py), and `ref:ppr` / `ref:half` / `ref:std` are leagues for browsing without one (refleague.py):
the research routes answer them without ownership, the decision routes with 404 {"code": "needs_league"}.
docs/SECURITY_PUBLIC.md.
Errors are {"error": "<plain words>"} (plus the older "detail"): 404 unknown league / team / player / user,
502 Sleeper did not answer, 503 the numbers are not ready yet / busy (our Sleeper budget).
Everything else is the web app (web/dist): a real file, else index.html (the app routes itself).
"""

from __future__ import annotations

import logging  # ---- IM-3
import math
import mimetypes
import os as _os_env  # ---- IM-3 fix: LEAGUE_LAB_API_DOCS
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse  # IN-1: HTMLResponse
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


# ---- IM-3 fix (the Wave I-M review): the API's own documentation (Swagger UI and the OpenAPI schema) is off unless
# LEAGUE_LAB_API_DOCS=on — a public site does not publish its route map, and the gate does not cover these two paths.
API_DOCS = _os_env.environ.get("LEAGUE_LAB_API_DOCS", "").strip().lower() in ("on", "1", "true", "yes")
app = FastAPI(title=f"{APP_NAME} API (League Lab)", version="0.1.0", lifespan=lifespan,
              docs_url="/api/docs" if API_DOCS else None, openapi_url="/api/openapi.json" if API_DOCS else None,
              redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.middleware("http")
async def _give_memory_back(request: Request, call_next):
    """INF-2 (Wave I-J): after a request, hand the freed heap back to the system when the RSS grew since the last time
    (``memo.relieve``: glibc's malloc_trim, at most every few seconds; a no-op elsewhere)."""
    response = await call_next(request)
    memo.relieve()
    return response

JSON_CACHE = "private, max-age=120"
_log = logging.getLogger("league_lab_api")      # ---- IM-3

from . import ratelimit, refleague, security  # noqa: E402 - ---- IM-3 (Wave I-M): its own block, below

refleague.install()          # ---- IM-3: `ref:` keys answer through the platforms Router (refleague.py)


# errors: {"error": "<plain words>"} (the contract), "detail" kept for the D7 spike's web client
@app.exception_handler(NotFound)
async def _not_found(_req: Request, exc: NotFound):
    extra = {k: getattr(exc, k) for k in ("code", "fix", "provider", "private_form")   # ---- II-5 (IK-3: provider, private_form)
             if getattr(exc, k, None)}
    return JSONResponse({"error": str(exc), "detail": str(exc), **extra}, status_code=404, headers={"Cache-Control": "no-store"})


@app.exception_handler(ondemand.SleeperDown)
async def _sleeper_down(_req: Request, exc: ondemand.SleeperDown):
    who = "MyFantasyLeague" if "MyFantasyLeague" in str(exc) else "Sleeper"      # I0-B: an MFL league says so
    who = getattr(exc, "who", None) or next((w for w in ("ESPN", "Yahoo") if w in str(exc)), who)   # ---- IK-3
    # ---- IM-3: the cause (a provider's URL, an exception's text) goes to the server's log, not to a public answer
    _log.warning("provider down (%s): %s", who, exc)
    return JSONResponse({"error": f"{who} did not answer", "detail": f"{who} did not answer. Try again in a minute.",
                         "code": "provider_down"}, status_code=502, headers={"Cache-Control": "no-store"})  # II-5: code


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
    provider_gate(request.query_params.get("league") or request.path_params.get("league_id"))   # ---- IK-3


# ---- IK-3 (Wave I-K): ESPN / Yahoo per request. (1) A private ESPN league read with one user's cookies is never served
# from a cache to another: before any route (and its memo regions) answers for an `espn:` key, IK-1's
# `require_access` checks this request's cookies (``provider_gate``, from ``require_auth``, which every data route
# depends on; the trade POST checks its body's league). (2) STUB only: the stand-in Yahoo adapter's token
# (``ondemand.YAHOO_TOKEN``); the real Yahoo session is IK-2's middleware (``yahoo_connect``, below).
def provider_gate(league: str | None) -> None:
    if league and A.platforms.is_espn(league):
        try:
            A.sleeper().serving(A.check_id(league))         # the Router runs the adapter's require_access
        except A.LeagueNotFound as exc:
            raise ondemand.provider_error("espn", league, exc) from exc


@app.middleware("http")
async def _provider_context(request: Request, call_next):
    reset = ondemand.YAHOO_TOKEN.set(ondemand.yahoo_token_from(request.cookies.get("ll_yahoo")))   # STUB only
    try:
        return await call_next(request)
    finally:
        ondemand.YAHOO_TOKEN.reset(reset)
# ---- end IK-3


# ---- IM-3 (Wave I-M): a reference key (`ref:half`) on a decision route — My Week, Waivers, Trades, Team, League and the
# rest that need a roster — is not an error: 404 {"code": "needs_league", "error": "Open your league to see this."},
# which the web turns into an invitation card. A research route answers it without ownership (`_research`).
@app.exception_handler(refleague.NeedsLeague)
async def _needs_league(_req: Request, _exc: refleague.NeedsLeague):
    return refleague.needs_league()


def needs_league(request: Request) -> None:
    league = request.query_params.get("league") or request.path_params.get("league_id")
    if refleague.is_reference(league):
        raise refleague.NeedsLeague()


def _research(data, league: str | None, response: Response):
    """A research route's answer: as before, or — for a reference key — without any ownership field."""
    return _json(refleague.public(data) if refleague.is_reference(league) else data, response)
# ---- end IM-3


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


# ---- IS-4 (Wave I-S): a new publication refreshes as_of at the next health check (db.watch_publication's callback)
def _publication_changed(_new_id) -> None:
    _health_state["next"] = 0.0


db.on_publication.append(_publication_changed)
# ---- end IS-4


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
            sleeper: str | None = None, espn: str | None = None, yahoo: str | None = None, yahoo_me: str | None = None):
    # ---- IK-3: ESPN by link or id, Yahoo by link / key / id, the signed-in user's Yahoo leagues (never cached)
    if espn is not None:
        return _json(ondemand.espn_league(espn), response)
    if yahoo is not None:
        return _json(ondemand.yahoo_league(yahoo), response)
    if yahoo_me is not None:
        out = _json(ondemand.yahoo_me(), response)
        out.headers["Cache-Control"] = "no-store"
        return out
    # ---- end IK-3
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
    return _json({"providers": A.platforms.all_capabilities(), "features": list(A.platforms.FEATURES),
                  **ondemand.provider_flags()}, response)       # ---- IK-3: espn_private, yahoo_configured
# ---- end II-5


@app.get("/api/leagues/{league_id}/rosters", dependencies=[Depends(require_auth), Depends(needs_league)])
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
        m = ({} if not ondemand.A.platforms.is_sleeper(league)          # ---- IE-0: Sleeper's number (IK-3: not ESPN / Yahoo)
             else why.market_points(season, week, [r.get("gsis_id") for r in rows], scoring))
    except Exception:  # noqa: BLE001 - My Week never fails for the market line
        m = {}
    for k in ("lineup", "lineup_full"):
        for r in out.get(k) or []:
            r["market_points"] = m.get(str(r.get("gsis_id"))) if r.get("gsis_id") else None
    return out
# ---- end IA-3


@app.get("/api/my-week", dependencies=[Depends(require_auth), Depends(needs_league)])
def my_week(league: str, team: int, response: Response, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league):
        return _json(why_market_rows(ondemand.my_week(league, team), league, house=False), response)   # ---- IA-3
    return _json(why_market_rows(myweek.my_week(league, team), league, house=True), response)         # ---- IA-3


@app.get("/api/player/{gsis}", dependencies=[Depends(require_auth)])
def player_card(gsis: str, league: str, response: Response, team: int | None = None, source: str | None = None):
    # ---- IP-4 fix round (Wave I-P): a team defense's card (a closed set of team codes; league_lab_api/unitcard.py)
    from . import unitcard as unitcard_mod
    if unitcard_mod.unit_code(gsis) is not None:
        return _research(unitcard_mod.defense_card(league, gsis, team), league, response)
    # ---- end IP-4
    if source == "sleeper" or not myweek.known_league(league):
        out = ondemand.player_card(league, gsis)
    else:
        out = player.player_card(league, gsis)
    out["viewer_roster_id"] = team
    if refleague.is_reference(league):                         # ---- IN-2: the scoring in the head, the value, no owner
        out = refleague.card(out, league)                      # ---- end IN-2
    out = provenance.with_card(out)                                                               # ---- IR-4
    return _research(out, league, response)                                                       # ---- IM-3


@app.get("/api/ros", dependencies=[Depends(require_auth)])
def ros(league: str, response: Response, position: str = "ALL", limit: int = 50,
        view: str = "points", team: int | None = None, who: str = "all"):          # ---- IB-3: view=lineup&team=
    view = ratelimit.norm(view) or "points"           # ---- IM-3 fix: one spelling for the bucket, this rule and ondemand
    if ratelimit.lineup_view(view) and refleague.is_reference(league):                        # ---- IM-3
        raise refleague.NeedsLeague()
    return _research(provenance.with_ros(ondemand.ros(league, position, limit, view=view, team=team, who=who)), league, response)  # ---- IR-4


@app.exception_handler(ondemand.BadView)                                              # ---- IB-3
async def _bad_view(_req: Request, exc: ondemand.BadView):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/api/record", dependencies=[Depends(require_auth)])
def record(league: str, response: Response, team: int | None = None):   # ---- V-2: `team` -> decisions.team
    if refleague.is_reference(league):                         # ---- IM-3: the model's record, no lineup record
        return _research(refleague.record(league), league, response)
    return _json(ondemand.record(league, team=team), response)


@app.get("/api/search", dependencies=[Depends(require_auth)])
def search(league: str, q: str, response: Response, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league):     # H1: any league - Sleeper's directory (research.py)
        return _research(research.search_on_demand(league, q), league, response)                 # ---- IM-3
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
    out["odds_grades"] = _status_odds_grades()   # ---- IL-3: the latest grade of the week's odds and the ranges
    out["ratelimit"] = {**ratelimit.limiter().info(), "cpu": ratelimit.slots().info(),   # ---- IM-3 fix
                        "usage": ratelimit.usage_ceiling().info()}   # ---- IM-3: the buckets, clients held, refusals, how clients were keyed
    out["gate"] = auth.gate()                       # ---- IM-3: open | password
    return _json(out, response)


# ---- IL-3 (Wave I-L): the week's win probability and the ranges, graded nightly on the decision record
# (league_lab.odds_grade, `league-lab grade-odds` writes analytics.odds_grades). Read only: the newest season-to-date
# pooled rows, {season, through_week, brier, coverage_50, coverage_80, graded_at}; None when no row (or no table).
def _status_odds_grades() -> dict | None:
    from league_lab import odds_grade as _og
    try:
        return _og.status(query)
    except Exception:  # noqa: BLE001 - a status line, never a failure
        return None
# ---- end IL-3


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
    try:                                    # ---- IL-4: Sleeper's player directory as kept (trimmed at the load)
        sl = getattr(A.sleeper(), "sleeper", None)
        out["directory"] = sl.directory_info() if sl is not None and hasattr(sl, "directory_info") else None
    except Exception:  # noqa: BLE001 - a status line, never a failure
        out["directory"] = None
    return out


# ---- G1 research (plan G1, Wave G: league_lab_api/research.py; README § Research (G1)) ---------------------------
@app.exception_handler(research.BadRequest)
async def _bad_request(_req: Request, exc: research.BadRequest):
    return JSONResponse({"error": str(exc), "detail": str(exc)}, status_code=400, headers={"Cache-Control": "no-store"})


@app.get("/api/trends", dependencies=[Depends(require_auth)])
def trends(league: str, response: Response, position: str = "ALL", limit: int = 50, view: str = "all",
           season: int | None = None, who: str = "all", team: int | None = None, min_games: int = 1,
           sort: str | None = None, dir: str | None = None, metrics: str = "moved", source: str | None = None):
    return _research(research.trends(league, position=position, limit=limit, view=view, season=season, who=who, team=team,
                                     min_games=min_games, sort=sort, dir=dir, metrics=metrics, source=source),
                     league, response)                                                            # ---- IM-3


@app.get("/api/matchups/defense", dependencies=[Depends(require_auth)])
def matchups_defense(league: str, response: Response, position: str = "ALL", source: str | None = None, team: int | None = None):
    return _research(research.matchups_defense(league, position=position, source=source, team=team), league, response)


@app.get("/api/matchups/cb", dependencies=[Depends(require_auth)])
def matchups_cb(league: str, response: Response, team: int | None = None, limit: int = 50, source: str | None = None):
    return _research(research.matchups_cb(league, team=team, limit=limit, source=source), league, response)


@app.get("/api/players", dependencies=[Depends(require_auth)])
def players(league: str, response: Response, season: int | None = None, position: str = "ALL", sort: str | None = None,
            dir: str | None = None, limit: int = 50, offset: int = 0, q: str | None = None, season_type: str = "REG",
            min_games: int = 1, source: str | None = None, window: str | None = None, basis: str | None = None,
            weeks: str | None = None, who: str | None = None, team: int | None = None, nfl: str | None = None):  # ---- II-3
    vsort = refleague.is_reference(league) and window is not None and sort == refleague.VALUE_COLUMN      # ---- IN-2
    out = research.players(league, season=season, position=position, sort=None if vsort else sort, dir=dir,
                           limit=1000 if vsort else limit, offset=0 if vsort else offset, q=q, season_type=season_type,
                           min_games=min_games, source=source, window=window, basis=basis, weeks=weeks, who=who,
                           team=team, nfl=nfl)
    if refleague.is_reference(league) and window is not None:                # ---- IN-2: the value column, browsing
        out = refleague.stats_values(out, league, sort, dir, (offset, limit) if vsort else None)   # ---- end IN-2
    return _research(out, league, response)                                                       # ---- IM-3


# ---- IM-1 (Wave I-M): the Stats table as a CSV — /api/players?window=…'s parameters + the columns (cols= | preset= +
# view=key|full) and per_game=1; every row of the selection (limit up to 1000), a header row of labels, streamed
@app.get("/api/players.csv", dependencies=[Depends(require_auth)])
def players_csv(league: str, season: int | None = None, position: str = "ALL", sort: str | None = None,
                dir: str | None = None, limit: int = 1000, offset: int = 0, q: str | None = None, season_type: str = "REG",
                min_games: int = 1, source: str | None = None, window: str = "season", basis: str | None = None,
                weeks: str | None = None, who: str | None = None, team: int | None = None, nfl: str | None = None,
                preset: str | None = None, cols: str | None = None, view: str | None = None, per_game: int = 0):
    from fastapi.responses import StreamingResponse

    from . import stats as stats_mod
    vsort = refleague.is_reference(league) and sort == refleague.VALUE_COLUMN                        # ---- IN-2
    d = research.players(league, season=season, position=position, sort=None if vsort else sort, dir=dir,
                         limit=1000 if vsort else limit, offset=0 if vsort else offset, q=q, season_type=season_type,
                         min_games=min_games, source=source, window=window, basis=basis, weeks=weeks, who=who,
                         team=team, nfl=nfl)
    if refleague.is_reference(league):                                       # ---- IN-2: the value column, no owner
        d = refleague.public(refleague.stats_values(d, league, sort, dir, (offset, limit) if vsort else None))   # ---- end IN-2
    try:
        columns = stats_mod.csv_columns(d, preset=preset, cols=cols, view=view)
    except ValueError as exc:
        raise research.BadRequest(str(exc)) from exc
    return StreamingResponse(stats_mod.csv_lines(d, columns, per_game=bool(per_game)), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{stats_mod.csv_filename(d)}"',
                                      "Cache-Control": "no-store"})
# ---- end IM-1


@app.get("/api/receivers", dependencies=[Depends(require_auth)])
def receivers(league: str, response: Response, season: int | None = None, limit: int = 50, season_type: str = "REG",
              weeks: str | None = None, players: str | None = None, context: str = "half", source: str | None = None):
    return _research(research.receivers(league, season=season, limit=limit, season_type=season_type, weeks=weeks,
                                        players=players, context_type=context, source=source), league, response)


@app.get("/api/compare", dependencies=[Depends(require_auth)])
def compare(league: str, a: str, b: str, response: Response, source: str | None = None):
    out = research.compare(league, a, b, source=source)
    if refleague.is_reference(league):                         # ---- IN-2: each side's value without a league
        out = refleague.compare_values(out, league)            # ---- end IN-2
    return _research(out, league, response)


@app.get("/api/player/{gsis}/games", dependencies=[Depends(require_auth)])
def player_games(gsis: str, league: str, response: Response, season: int | None = None, season_type: str = "ALL",
                 source: str | None = None):
    return _research(research.player_games(league, gsis, season=season, season_type=season_type, source=source),
                     league, response)
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


@app.get("/api/waivers", dependencies=[Depends(require_auth), Depends(needs_league)])
def waivers(league: str, response: Response, team: int | None = None, position: str | None = None, limit: int = 50,
            offset: int = 0, source: str | None = None):
    return _json(decisions.waivers(league, team, position, limit, offset, source=source), response)


@app.post("/api/trades/evaluate", dependencies=[Depends(require_auth)])
def trades_evaluate(body: TradeBody, response: Response, source: str | None = None):
    if refleague.is_reference(body.league):                                                      # ---- IM-3
        raise refleague.NeedsLeague()
    provider_gate(body.league)                                                                   # ---- IK-3
    out = decisions.evaluate(body.league, body.team, body.partner, body.give, body.get, source=source, window=body.window)
    out = provenance.with_trade(out)                          # ---- IR-4: provenance + the starter caveats (data)
    out = provenance.rule_trade(out)                          # ---- PO (Wave I-R): the caveat rule applied to the one decision
    response.headers["Cache-Control"] = "no-store"
    return JSONResponse(clean(out), headers={"Cache-Control": "no-store"})


@app.get("/api/trades/partners", dependencies=[Depends(require_auth), Depends(needs_league)])
def trades_partners(league: str, team: int, response: Response, want: str | None = None, source: str | None = None,
                    window: str | None = None):
    return _json(decisions.partners(league, team, want, source=source, window=window), response)


# ---- IA-2 (Wave I-A): buy low / sell high moved from /api/waivers to the Trades screen
#   /api/trades/lists?league=&team=&position=               buy low (other rosters), sell high (yours), the best per position
@app.get("/api/trades/lists", dependencies=[Depends(require_auth), Depends(needs_league)])
def trades_lists(league: str, team: int, response: Response, position: str | None = None, source: str | None = None):
    return _json(decisions.trade_lists(league, team, position, source=source), response)
# ---- end IA-2


@app.get("/api/team", dependencies=[Depends(require_auth), Depends(needs_league)])
def team_hub(league: str, team: int, response: Response, source: str | None = None):
    return _json(decisions.team(league, team, source=source), response)


@app.get("/api/league", dependencies=[Depends(require_auth), Depends(needs_league)])
def league_page(league: str, response: Response, team: int | None = None, limit: int = 50, offset: int = 0,
                source: str | None = None):
    return _json(decisions.league(league, team, limit, offset, source=source), response)


# ---- H1 (Wave H): "About the numbers" - the model, what it leans on most, its grades (league_lab_api/about.py)
#   /api/about?league=          importance (mart_projection_importance) + grades (mart_projection_drift / _backtest)
from . import about as about_mod  # noqa: E402 - the block stays self-contained (Wave H devs append in parallel)


@app.get("/api/about", dependencies=[Depends(require_auth)])
def about(league: str, response: Response, source: str | None = None):
    return _research(about_mod.about(league, source=source), league, response)                    # ---- IM-3
# ---- end H1

# ---- IC-1 (Wave I-C): the scoring check — our points against the league's own for a scored week
#   /api/league/scoring-check?league=&week=     league_lab.scoring_audit.check (default: the last complete week)
SCORING_CHECK_TTL_S = 24 * 3600.0        # a scored week does not change; the stat corrections land overnight
_scoring_checks = memo.region("scoring_checks", ttl=SCORING_CHECK_TTL_S)   # INF-2: in the memory budget (was 200 entries)


@app.get("/api/league/scoring-check", dependencies=[Depends(require_auth), Depends(needs_league)])
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
    # ---- IM-3 fix: a fresh cookie per request no longer buys rows — an hourly ceiling in all and per visitor
    # (ratelimit.usage_ceiling, keyed by ratelimit.client_group); a refused count is as silent as an accepted one
    if usage_mod.allow(session) and ratelimit.usage_ceiling().allow(ratelimit.client_group(request.scope)):
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


@app.get("/api/events", dependencies=[Depends(require_auth), Depends(needs_league)])
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


@app.get("/api/league/week-odds", dependencies=[Depends(require_auth), Depends(needs_league)])
def league_week_odds(league: str, response: Response, source: str | None = None):
    return _json(myweek.week_odds(league, house=False if source == "sleeper" else None), response)
# ---- end IH-3


# ---- IK-1 (Wave I-K): a private ESPN league read with the manager's own cookies — off unless LEAGUE_LAB_ESPN_PRIVATE=on
# (espn_connect: POST /api/espn/connect | disconnect, GET /api/espn/status; the middleware puts this request's ll_espn
# cookie in espn_client.AUTH for this request only; nothing is stored or logged)
from . import espn_connect  # noqa: E402

app.middleware("http")(espn_connect.auth_middleware)
app.include_router(espn_connect.router, dependencies=[Depends(require_auth)])
# ---- end IK-1

# ---- IK-2 (Wave I-K): Connect with Yahoo — /api/yahoo/* (connect, callback, disconnect, status, leagues) and the
# ll_yahoo session middleware; the routes go ahead of the /api catch-all whatever the line's place
from . import yahoo_connect  # noqa: E402 - the block stays self-contained

yahoo_connect.install(app)
# ---- end IK-2

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

# ---- IL-5 (Wave I-L): accounts phase 2 — GET /api/account/watchlist?league=&team= (the watchlist screen: each saved
# player as the drawer's card has him in that league; league_lab_api/watchlist.py). The connections (Yahoo / ESPN rows
# under an account) ride on the routes above and IK-1's / IK-2's (league_lab_api/connections.py).
from . import watchlist as watchlist_mod  # noqa: E402 - the block stays self-contained

app.include_router(watchlist_mod.router, dependencies=[Depends(require_auth)])
# ---- end IL-5


# ---- IM-5 (Wave I-M): DFS — GET /api/dfs/projections, POST /api/dfs/slate, POST /api/dfs/lineups (league_lab_api/dfs.py)
from . import dfs as dfs_mod  # noqa: E402 - the block stays self-contained

app.include_router(dfs_mod.router, dependencies=[Depends(require_auth)])
# ---- end IM-5

# ---- IN-3 (Wave I-N): matchups for everyone — GET /api/matchups/board (league_lab_api/matchup_board.py; research bucket)
from . import matchup_board as matchup_board_mod  # noqa: E402 - the block stays self-contained

app.include_router(matchup_board_mod.router, dependencies=[Depends(require_auth)])
# ---- end IN-3


# ---- IN-2 (Wave I-N): the trade calculator without a league — GET /api/trade-calc/free (league_lab_api/freetrade.py)
from . import freetrade as freetrade_mod  # noqa: E402 - the block stays self-contained

app.include_router(freetrade_mod.router, dependencies=[Depends(require_auth)])
# ---- end IN-2


# ---- IN-1 (Wave I-N): the blog — GET /api/blog, /api/blog/{slug}, /blog/rss.xml, /blog/img/{name}, /sitemap.xml
# (league_lab_api/blog.py; docs/BLOG.md). Registered ahead of the web app's catch-all below.
from . import blog as blog_mod  # noqa: E402 - the block stays self-contained

app.include_router(blog_mod.router, dependencies=[Depends(require_auth)])
app.include_router(blog_mod.pages)          # the feed, the pictures, the sitemap: public like the web app's files
# ---- end IN-1


# ---- IN-6 (Wave I-N): the League screen's power rankings and the rest of the season (league_lab_api/outlook.py)
from . import outlook as outlook_mod  # noqa: E402 - the block stays self-contained

app.include_router(outlook_mod.router, dependencies=[Depends(require_auth), Depends(needs_league)])
# ---- end IN-6


# ---- IO-1 (Wave I-O): the context record — GET /api/context/record (league_lab_api/context_record.py; read bucket)
from . import context_record as context_record_mod  # noqa: E402 - the block stays self-contained

app.include_router(context_record_mod.router, dependencies=[Depends(require_auth)])
# ---- end IO-1


# ---- IP-2 (Wave I-P): rankings for everyone — GET /api/rankings, GET /api/rankings/start (rankings_api.py; research)
from . import rankings_api as rankings_mod  # noqa: E402 - the block stays self-contained

app.include_router(rankings_mod.router, dependencies=[Depends(require_auth)])
rankings_mod.install_pages(blog_mod)        # /rankings in the sitemap and the shell's fixed previews
# ---- end IP-2


# ---- IP-4 (Wave I-P): the player card's ratings and past projections — GET /api/player/{gsis}/ratings,
# /api/player/{gsis}/projections (league_lab_api/ratings.py; research bucket: the /api/player/ prefix)
from . import ratings as ratings_mod  # noqa: E402 - the block stays self-contained

app.include_router(ratings_mod.router, dependencies=[Depends(require_auth)])
# ---- end IP-4


# ---- IR-3 (Wave I-R): readiness apart from liveness — GET /api/ready (league_lab_api/ready.py; the read bucket, no
# password like /api/health: 200 only when the published numbers can be served, else 503 with the reason in words)
from . import ready as ready_mod  # noqa: E402 - the block stays self-contained

app.include_router(ready_mod.router)
# ---- end IR-3


# ---- IM-3 (Wave I-M): the public site's doors. The rate limiter (ratelimit.py) inside the Guard (security.py: cross-site
# writes, body sizes, the response headers on every answer, a 429 included); both outermost, ahead of the routes.
#   GET /api/ratelimit   how this request was keyed ({keyed_by, test_address_used, bucket_tag}; never the address)
@app.get("/api/ratelimit", include_in_schema=False)
def ratelimit_probe(request: Request) -> JSONResponse:
    return JSONResponse(ratelimit.probe(request.scope), headers={"Cache-Control": "no-store"})


app.add_middleware(ratelimit.RateLimit)
app.add_middleware(security.Guard)
# ---- end IM-3


# ---------------------------------------------------------------- the web app
ASSET_CACHE = "public, max-age=31536000, immutable"     # vite's hashed file names
SHELL_CACHE = "no-cache"                                # index.html, sw.js, manifest: revalidate every load


@app.api_route("/api/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
def api_404(rest: str):
    raise HTTPException(status_code=404, detail=f"no endpoint /api/{rest}")


@app.get("/{path:path}", include_in_schema=False)
def web(path: str, request: Request):  # ---- IO-2: the request (a League link's ?league=)
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
        if path.startswith("blog/img/"):            # ---- IN-1: a picture the blog's route did not serve is missing
            raise HTTPException(status_code=404)
    # ---- IO-2 (Wave I-O): a League link (/league?league=<key>) previews the league's power rankings — from what is
    # cached or stored only (outlook.shell; a private league, nothing kept → the default card below)
    if path.strip("/") == "league" and request.query_params.get("league"):
        shaped_league = outlook_mod.shell(index, request.query_params.get("league"))
        if shaped_league is not None:
            from . import player_share  # ---- IP-5: noindex
            return HTMLResponse(player_share.noindex(shaped_league), headers={"Cache-Control": SHELL_CACHE,
                                                                              "X-Robots-Tag": "noindex"})
    # ---- end IO-2
    # ---- IP-5 (Wave I-P): a player's page shares as his card (player_share: from what this process holds, never a
    # query); a page with a league in its query string is not for search engines (noindex)
    from . import player_share
    league_q = bool(request.query_params.get("league"))
    robots = {"X-Robots-Tag": "noindex"} if league_q else {}
    shaped_player = player_share.shell(index, path, league_q)
    if shaped_player is not None:
        return HTMLResponse(shaped_player, headers={"Cache-Control": SHELL_CACHE, **robots})
    # ---- end IP-5
    # ---- IP-2 (Wave I-P): /rankings previews per position and view (a closed set: rankings_api.preview)
    if path.strip("/") == "rankings":
        shaped_rankings = rankings_mod.shell(index, request.query_params)
        if shaped_rankings is not None:
            return HTMLResponse(player_share.noindex(shaped_rankings) if league_q else shaped_rankings,
                                headers={"Cache-Control": SHELL_CACHE, **robots})      # PO (I-P merge): IP-5's robots
    # ---- end IP-2
    # ---- IN-1 (Wave I-N): the link preview for this path (title, description, canonical, Open Graph, Twitter) in the
    # shell's head — a shared post or tool unfurls in iMessage / X / Reddit / Discord; an unknown post answers 404
    shaped = blog_mod.shell(index, path)
    if shaped is not None:
        return HTMLResponse(player_share.noindex(shaped[0]) if league_q else shaped[0], status_code=shaped[1],
                            headers={"Cache-Control": SHELL_CACHE, **robots})          # ---- IP-5: robots
    # ---- end IN-1
    if league_q:                                                                       # ---- IP-5
        return HTMLResponse(player_share.noindex(player_share._index_text(index)), headers={"Cache-Control": SHELL_CACHE, **robots})
    return FileResponse(index, headers={"Cache-Control": SHELL_CACHE})


# ---- IR-4 (Wave I-R): what is verified, with every analysis (league_lab_api/provenance.py; no route of its own)
from . import provenance  # noqa: E402 - the block stays self-contained
# ---- end IR-4
