"""The doors of a public site (Wave I-M, IM-3; docs/SECURITY_PUBLIC.md): one pure-ASGI middleware, outermost.

* **Cross-site writes are refused** (CSRF): a POST / PUT / PATCH / DELETE to ``/api/`` whose ``Origin`` names a host
  that is not this request's own ``Host`` nor one of ``LEAGUE_LAB_ALLOWED_HOSTS`` (default ``isuckatfantasy.io``,
  ``www.isuckatfantasy.io``, ``league-lab.onrender.com``), or that has no ``Origin`` but ``Sec-Fetch-Site:
  cross-site``, answers **403** ``{"code": "cross_site"}`` before any route runs. Every browser in use sends ``Origin``
  on a cross-site POST, so SameSite cookies are not the only line; a request with neither header is not a browser's
  cross-site request (curl, the smoke script, the tests) and passes. ``Origin: null`` (a sandboxed frame, a
  ``data:`` page) is refused.
* **Request bodies are bounded**: ``LEAGUE_LAB_MAX_BODY_KB`` (default 256) on ``/api/``, ``LEAGUE_LAB_MAX_UPLOAD_KB``
  (default 2048) under ``/api/dfs/`` (IM-5's salary file, capped at 1 MB by its parser). A declared
  ``Content-Length`` over the bound answers **413** at once; a body without one (chunked) is read up to the bound and
  refused past it, never held whole.
* **Response headers** on every answer: ``X-Content-Type-Options: nosniff``, ``Referrer-Policy:
  strict-origin-when-cross-origin``, ``X-Frame-Options: DENY``, a ``Permissions-Policy`` that switches off what the app
  never uses, ``Strict-Transport-Security`` on https, and a ``Content-Security-Policy`` the app and Google Analytics
  pass (``frame-ancestors 'none'``; the inline prefetch script in ``index.html`` allowed by its hash, computed from the
  served file). ``LEAGUE_LAB_CSP=off`` drops the CSP alone (an escape hatch, never needed so far).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from .settings import web_dist

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
DEFAULT_HOSTS = ("isuckatfantasy.io", "www.isuckatfantasy.io", "league-lab.onrender.com")
CROSS_SITE = "This request came from another site, so it was refused."
TOO_BIG = "That is more than this server takes in one request."

GA_SCRIPT = "https://*.googletagmanager.com"
GA_CONNECT = "https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com"
_INLINE = re.compile(rb"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)
_hashes: dict[str, tuple[float, list[str]]] = {}


def allowed_hosts() -> set[str]:
    raw = os.environ.get("LEAGUE_LAB_ALLOWED_HOSTS")
    hosts = [h.strip().lower() for h in (raw.split(",") if raw else DEFAULT_HOSTS) if h.strip()]
    return set(hosts)


def _limit_kb(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name) or default))
    except ValueError:
        return default


def body_limit(path: str) -> int:
    if path.startswith("/api/dfs/"):
        return _limit_kb("LEAGUE_LAB_MAX_UPLOAD_KB", 2048) * 1024
    if path == "/api/blog/images":                     # ---- IO-3: a picture, ≤ 300 KB (blog_store.MAX_IMAGE_BYTES)
        return 320 * 1024
    return _limit_kb("LEAGUE_LAB_MAX_BODY_KB", 256) * 1024


def inline_hashes(index: Path | None = None) -> list[str]:
    """'sha256-…' of every inline <script> in the served index.html (cached by the file's mtime)."""
    index = index or web_dist() / "index.html"
    try:
        mtime = index.stat().st_mtime
    except OSError:
        return []
    hit = _hashes.get(str(index))
    if hit and hit[0] == mtime:
        return hit[1]
    out = [f"'sha256-{base64.b64encode(hashlib.sha256(m).digest()).decode()}'" for m in _INLINE.findall(index.read_bytes())]
    _hashes[str(index)] = (mtime, out)
    return out


def csp() -> str:
    script = " ".join(["'self'", *inline_hashes(), GA_SCRIPT])
    return "; ".join([
        "default-src 'self'",
        f"script-src {script}",
        "style-src 'self' 'unsafe-inline'",          # Svelte's style="" attributes (bar widths, team colours)
        "img-src 'self' data: https:",               # headshots and team logos from the leagues' and the NFL's CDNs
        f"connect-src 'self' {GA_CONNECT}",
        "font-src 'self' data:",
        "manifest-src 'self'",
        "worker-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


def security_headers(scope) -> list[tuple[bytes, bytes]]:
    out = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"strict-origin-when-cross-origin"),
           (b"x-frame-options", b"DENY"),
           (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()")]
    if os.environ.get("LEAGUE_LAB_CSP", "on").strip().lower() != "off":
        out.append((b"content-security-policy", csp().encode()))
    https = scope.get("scheme") == "https" or any(k.lower() == b"x-forwarded-proto" and v == b"https"
                                                  for k, v in scope.get("headers") or [])
    if https:
        out.append((b"strict-transport-security", b"max-age=31536000"))
    return out


def cross_site(scope) -> bool:
    """True when an unsafe request to /api/ comes from another site (see the module's docstring)."""
    if scope.get("method", "GET").upper() not in UNSAFE or not str(scope.get("path", "")).startswith("/api/"):
        return False
    headers = {k.lower(): v for k, v in scope.get("headers") or []}
    origin = headers.get(b"origin")
    if origin is not None:
        o = origin.decode("latin-1").strip()
        if not o or o.lower() == "null":
            return True
        host = (urlsplit(o).netloc or "").lower()
        own = headers.get(b"host", b"").decode("latin-1").strip().lower()
        return not host or (host != own and host not in allowed_hosts())
    return headers.get(b"sec-fetch-site", b"").strip().lower() == b"cross-site"


async def _answer(send, status: int, words: str, code: str, extra: list[tuple[bytes, bytes]]) -> None:
    body = json.dumps({"error": words, "detail": words, "code": code}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                            (b"content-length", str(len(body)).encode()), *extra]})
    await send({"type": "http.response.body", "body": body})


class Guard:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        extra = security_headers(scope)

        async def send_with_headers(message):
            if message.get("type") == "http.response.start":
                have = {k.lower() for k, _ in message.get("headers") or []}
                message = {**message, "headers": [*(message.get("headers") or []),
                                                  *[(k, v) for k, v in extra if k not in have]]}
            await send(message)

        if cross_site(scope):
            return await _answer(send, 403, CROSS_SITE, "cross_site", extra)
        path = str(scope.get("path", ""))
        if path.startswith("/api/") and scope.get("method", "GET").upper() in UNSAFE:
            limit = body_limit(path)
            headers = {k.lower(): v for k, v in scope.get("headers") or []}
            declared = headers.get(b"content-length")
            if declared is not None:
                try:
                    too_big = int(declared) > limit
                except ValueError:
                    too_big = True
                if too_big:
                    return await _answer(send, 413, TOO_BIG, "too_large", extra)
            else:                                   # no length declared (chunked): read it here, up to the bound
                chunks, size, more = [], 0, True
                while more:
                    message = await receive()
                    if message["type"] != "http.request":
                        break
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > limit:
                        return await _answer(send, 413, TOO_BIG, "too_large", extra)
                    chunks.append(chunk)
                    more = message.get("more_body", False)
                body = b"".join(chunks)
                sent = False

                async def replay():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await receive()

                return await self.app(scope, replay, send_with_headers)
        return await self.app(scope, receive, send_with_headers)
