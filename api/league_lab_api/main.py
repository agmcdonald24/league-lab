"""League Lab read-only API + the phone web app's static files (plan D7 spike). One process, one deploy.

    uv run uvicorn league_lab_api.main:app --port 8581          # from api/

Endpoints (all GET but login/logout; JSON; read-only role; cached 10 minutes like the app):
    /api/session                         is the gate on, is this browser signed in
    /api/login  /api/logout              the beta password → a signed cookie (or a bearer token)
    /api/leagues                         current-season leagues (ui.current_leagues)
    /api/leagues/{league_id}/rosters     the team picker's options
    /api/my-week?league=&team=           Home's My Week: record line, the cards (numbers + the cards' own text), lineup;
                                         a league the database does not have is served on demand from Sleeper
                                         (plan E3: ondemand.py; `source=sleeper` forces that path for a known league)
    /api/player/{gsis}?league=&team=     the player card's sections
    /api/search?league=&q=               the player card's search box
    /api/status                          the freshness line and the stale-injury warning
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
from pydantic import BaseModel

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


@app.exception_handler(NotFound)
async def _not_found(_req: Request, exc: NotFound):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(ondemand.SleeperDown)
async def _sleeper_down(_req: Request, exc: ondemand.SleeperDown):
    return JSONResponse({"detail": "Sleeper did not answer. Try again in a minute.", "error": str(exc)}, status_code=502)


@app.exception_handler(DataNotReady)
async def _not_ready(_req: Request, exc: DataNotReady):
    return JSONResponse({"detail": "This table is not on this database right now. If the data is being refreshed "
                                   "(nightly), reload in a minute or two.", "relation": str(exc)}, status_code=503)


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
def leagues(response: Response):
    return _json(myweek.leagues(), response)


@app.get("/api/leagues/{league_id}/rosters", dependencies=[Depends(require_auth)])
def rosters(league_id: str, response: Response):
    return _json(myweek.rosters(league_id), response)


@app.get("/api/my-week", dependencies=[Depends(require_auth)])
def my_week(league: str, team: int, response: Response, source: str | None = None):
    if source == "sleeper" or not myweek.known_league(league):
        return _json(ondemand.my_week(league, team), response)
    return _json(myweek.my_week(league, team), response)


@app.get("/api/player/{gsis}", dependencies=[Depends(require_auth)])
def player_card(gsis: str, league: str, response: Response, team: int | None = None):
    out = player.player_card(league, gsis)
    out["viewer_roster_id"] = team
    return _json(out, response)


@app.get("/api/search", dependencies=[Depends(require_auth)])
def search(league: str, q: str, response: Response):
    return _json(player.search(league, q), response)


@app.get("/api/status", dependencies=[Depends(require_auth)])
def status(response: Response):
    return _json(myweek.status(), response)


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
