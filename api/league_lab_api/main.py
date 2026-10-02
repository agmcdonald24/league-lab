"""League Lab read-only API + the phone web app's static files (plan D7 spike). One process, one deploy.

    uv run uvicorn league_lab_api.main:app --port 8581          # from api/

Endpoints (all GET but login/logout; JSON; read-only role; cached 10 minutes like the app):
    /api/session                         is the gate on, is this browser signed in
    /api/login  /api/logout              the beta password → a signed cookie (or a bearer token)
    /api/leagues                         current-season leagues (ui.current_leagues)
    /api/leagues?username=               a Sleeper user's leagues this season, their team in each (plan F3)
    /api/leagues/{league_id}/rosters     the team picker's options
    /api/my-week?league=&team=           Home's My Week: record line, the cards (numbers + the cards' own text), lineup;
                                         a league the database does not have is served on demand from Sleeper
                                         (plan E3: ondemand.py; `source=sleeper` forces that path for a known league)
    /api/player/{gsis}?league=&team=     the player card's sections (any league: on demand, plan F3) + rest of season
    /api/ros?league=&position=&limit=    rest of season: the mart for a house league, priced on request otherwise (F3)
    /api/record?league=                  our record vs Sleeper's projections (house leagues; F3)
    /api/search?league=&q=               the player card's search box
    /api/status                          the freshness line, the stale-injury warning, Sleeper's cache ages + budget
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

from . import auth, db, myweek, ondemand, player
from .db import DataNotReady
from .myweek import NotFound
from .settings import web_dist

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    db.close()


app = FastAPI(title="League Lab API", version="0.1.0", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=500)

JSON_CACHE = "private, max-age=120"


# errors: {"error": "<plain words>"} (the contract), "detail" kept for the D7 spike's web client
@app.exception_handler(NotFound)
async def _not_found(_req: Request, exc: NotFound):
    return JSONResponse({"error": str(exc), "detail": str(exc)}, status_code=404, headers={"Cache-Control": "no-store"})


@app.exception_handler(ondemand.SleeperDown)
async def _sleeper_down(_req: Request, exc: ondemand.SleeperDown):
    return JSONResponse({"error": "Sleeper did not answer", "detail": "Sleeper did not answer. Try again in a minute.",
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


@app.get("/api/health", include_in_schema=False)
def health() -> dict:
    return {"ok": True}


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
@app.get("/api/leagues", dependencies=[Depends(require_auth)])
def leagues(response: Response, username: str | None = None):
    if username is None:
        return _json(myweek.leagues(), response)
    return _json(ondemand.leagues_for_user(username), response)


@app.get("/api/leagues/{league_id}/rosters", dependencies=[Depends(require_auth)])
def rosters(league_id: str, response: Response, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league_id):
        return _json(ondemand.rosters_for_league(league_id), response)
    return _json(myweek.rosters(league_id), response)


@app.get("/api/my-week", dependencies=[Depends(require_auth)])
def my_week(league: str, team: int, response: Response, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league):
        return _json(ondemand.my_week(league, team), response)
    return _json(myweek.my_week(league, team), response)


@app.get("/api/player/{gsis}", dependencies=[Depends(require_auth)])
def player_card(gsis: str, league: str, response: Response, team: int | None = None, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league):
        out = ondemand.player_card(league, gsis)
    else:
        out = player.player_card(league, gsis)
    out["viewer_roster_id"] = team
    return _json(out, response)


@app.get("/api/ros", dependencies=[Depends(require_auth)])
def ros(league: str, response: Response, position: str = "ALL", limit: int = 50):
    return _json(ondemand.ros(league, position, limit), response)


@app.get("/api/record", dependencies=[Depends(require_auth)])
def record(league: str, response: Response):
    return _json(ondemand.record(league), response)


@app.get("/api/search", dependencies=[Depends(require_auth)])
def search(league: str, q: str, response: Response):
    return _json(player.search(league, q), response)


@app.get("/api/status", dependencies=[Depends(require_auth)])
def status(response: Response):
    out = myweek.status()
    out["sleeper"] = A.sleeper().stats()
    out["board_source"] = A.board_source()
    return _json(out, response)


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
