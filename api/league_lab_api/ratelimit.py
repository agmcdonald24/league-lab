"""Rate limits for a public site (Wave I-M, IM-3; docs/SECURITY_PUBLIC.md § "Rate limits").

One middleware (``RateLimit``, pure ASGI) in front of every ``/api/`` route but ``/api/health``; the web app's static
files are never limited. Three named buckets per client:

* ``read``  — every GET a screen makes (generous: a person clicking fast never meets it);
* ``heavy`` — what fans out to a provider or re-solves lineups: league setup (``/api/leagues?username= | mfl= |
  sleeper= | espn= | yahoo= …``, a league's rosters), My Week, Waivers, the Trade Finder and the calculator, Team, League,
  the week's odds, the scoring check, ``/api/ros?view=lineup``, Yahoo's sign-in, IM-5's DFS routes;
* ``write`` — every other POST / PUT / PATCH / DELETE (the usage count, sign-in, the account, ESPN connect).

Each bucket is a token bucket — ``per_minute`` tokens a minute, ``burst`` at once — the same rule as the usage and
accounts limiters (``usage.allow``, ``accounts.allow``), held as ONE number per client: the moment its bucket will be
full again (the "theoretical arrival time" of the generic cell rate algorithm, which is that token bucket written
differently). A client whose bucket is full again is the same as a client never seen, so it can be forgotten at no
cost: the memory holds only clients that spent tokens recently, at most ``LEAGUE_LAB_RATE_CLIENTS`` (default 5,000) per
bucket — past it the full ones go first, then the least recently seen (an LRU). Measured: ``api/tests/test_im3.py``.

**Who is "a client"** (``client_address``; the choice is ``LEAGUE_LAB_CLIENT_IP``, default ``auto``). On Render every
request reaches the service through Render's edge, which is Cloudflare (Render's own account: its answers carry
``cf-ray``; the domain's own Cloudflare records are DNS-only, so there is exactly one Cloudflare in the path). Cloudflare
sets ``CF-Connecting-IP`` to the address that connected to it and overwrites a value the client sent, so on Render
(``auto`` = ``edge`` when ``RENDER`` is set) that header comes first; without it, the **last** ``X-Forwarded-For`` entry
(``LEAGUE_LAB_PROXY_HOPS``-th from the right, default 1) — a client writes whatever it likes at the left of that
header, never the entry the proxy appends — so a spoofed ``X-Forwarded-For`` never buys a fresh bucket. Off Render
(local runs, the tests) ``auto`` is the socket's peer and no header is read. ``GET /api/ratelimit`` shows how a request
was keyed (docs/SECURITY_PUBLIC.md has the two curl lines that verify it live). IPv6 addresses
count by their /64 (one subscriber's block). The address itself is never stored: the key is an HMAC of it with a random
per-process key (gone at a restart, like the buckets).

Answer when refused: **429** ``{"error": "Too many requests from this connection. Try again in N seconds.",
"code": "rate_limited", "retry_after_s": N, "bucket": "<name>"}`` with ``Retry-After: N``.

Switches (Render → Environment; read at the first request, ``reset()`` re-reads): ``LEAGUE_LAB_RATE_LIMIT=off``;
``LEAGUE_LAB_RATE_READ`` / ``_HEAVY`` / ``_WRITE`` = ``"<per minute>,<burst>"``; ``LEAGUE_LAB_RATE_CLIENTS``;
``LEAGUE_LAB_CLIENT_IP`` = ``auto`` | ``cf-connecting-ip`` | ``true-client-ip`` | ``x-forwarded-for`` | ``peer``.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import math
import os
import secrets
import threading
import time
from collections.abc import Callable
from urllib.parse import parse_qs

log = logging.getLogger(__name__)

SWITCH_ENV = "LEAGUE_LAB_RATE_LIMIT"
CLIENTS_ENV = "LEAGUE_LAB_RATE_CLIENTS"
CLIENT_IP_ENV = "LEAGUE_LAB_CLIENT_IP"
HOPS_ENV = "LEAGUE_LAB_PROXY_HOPS"
# name -> (per minute, burst). read: 5 a second sustained, 150 at once — one screen is 2–8 calls and the web keeps its
# answers, so even a person tapping a new screen every second for a minute stays under it, and ten people behind
# one address (an office, a carrier's shared address) using the app normally do too. heavy: one every 3 seconds after
# 20 at once — every decision screen of four leagues opened in a row. write: one a second after 30 at once.
DEFAULTS: dict[str, tuple[float, float]] = {"read": (300.0, 150.0), "heavy": (20.0, 20.0), "write": (60.0, 30.0)}
MAX_CLIENTS = 5000
TEST_ADDRESS = "203.0.113.9"          # TEST-NET-3 (RFC 5737): the probe's address, never a real client's
WORDS = "Too many requests from this connection. Try again in {n} seconds."
WORDS_ONE = "Too many requests from this connection. Try again in a second."

# ------------------------------------------------------------------------------ which bucket a request spends
HEAVY_EXACT = frozenset({
    "/api/my-week", "/api/waivers", "/api/trades/evaluate", "/api/trades/partners", "/api/trades/lists", "/api/team",
    "/api/league", "/api/league/week-odds", "/api/league/scoring-check", "/api/yahoo/connect", "/api/yahoo/callback",
    "/api/yahoo/leagues",
})
HEAVY_PREFIX = ("/api/dfs/",)          # IM-5: the salary file and the lineups (stateless, but they solve)
LEAGUE_SETUP = frozenset({"username", "mfl", "mfl_search", "sleeper", "espn", "yahoo", "yahoo_me"})
UNLIMITED = frozenset({"/api/health"})
WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def bucket_for(method: str, path: str, query: str = "") -> str | None:
    """The bucket a request spends, or None (not limited: static files, the health check)."""
    if not path.startswith("/api/") or path in UNLIMITED:
        return None
    if path in HEAVY_EXACT or path.startswith(HEAVY_PREFIX):
        return "heavy"
    if path.startswith("/api/leagues/") and path.endswith("/rosters"):
        return "heavy"
    if path == "/api/leagues" and query and LEAGUE_SETUP & set(parse_qs(query, keep_blank_values=True)):
        return "heavy"
    if path == "/api/ros" and query and "lineup" in parse_qs(query).get("view", []):
        return "heavy"
    return "write" if method.upper() in WRITES else "read"


# ------------------------------------------------------------------------------ who the client is
def _ip(value: str | bytes | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    s = (value.decode("latin-1") if isinstance(value, bytes) else str(value)).strip().strip('"')
    if s.startswith("[") and "]" in s:                  # "[2001:db8::1]:443"
        s = s[1:s.index("]")]
    elif s.count(":") == 1 and "." in s:                # "198.51.100.7:443"
        s = s.split(":", 1)[0]
    try:
        ip = ipaddress.ip_address(s.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def _network(ip) -> bytes:
    """What one client is: an IPv4 address, an IPv6 /64."""
    if isinstance(ip, ipaddress.IPv6Address):
        return b"6" + ip.packed[:8]
    return b"4" + ip.packed


MODES = ("auto", "edge", "cf-connecting-ip", "true-client-ip", "x-forwarded-for", "peer")


def resolve_mode(mode: str) -> str:
    """``auto`` is ``edge`` on Render (Render sets ``RENDER`` in every service's environment) and ``peer`` elsewhere: off
    Render nothing stands in front of the server to write those headers, so a client could write them itself."""
    if mode != "auto":
        return mode
    return "edge" if os.environ.get("RENDER") else "peer"


def client_address(headers: dict[bytes, bytes], peer: str | None, mode: str = "auto",
                   hops: int = 1) -> tuple[str, object]:
    """(source, address) — the source is named in /api/status; the address is an ipaddress object, or the peer's text
    ("testclient") when that is not an address. ``headers``: lower-cased names -> the last value sent under that name.

    ``edge`` (Render): ``CF-Connecting-IP`` (Cloudflare writes it and overwrites a client's), else the ``hops``-th
    ``X-Forwarded-For`` entry from the right (the one our proxy appended; the client writes only the left part), else
    the peer. The peer is never read from ``X-Forwarded-For``'s left end: the image runs uvicorn with
    ``--proxy-headers --forwarded-allow-ips='*'``, which puts exactly that client-written entry in the scope's client,
    so on Render the peer is used only when no header is there at all."""
    mode = resolve_mode(mode)
    if mode in ("edge", "cf-connecting-ip"):
        ip = _ip(headers.get(b"cf-connecting-ip"))
        if ip is not None:
            return "cf-connecting-ip", ip
    if mode == "true-client-ip":
        ip = _ip(headers.get(b"true-client-ip"))
        if ip is not None:
            return "true-client-ip", ip
    if mode in ("edge", "x-forwarded-for"):
        parts = [p for p in (headers.get(b"x-forwarded-for") or b"").decode("latin-1").split(",") if p.strip()]
        if len(parts) >= hops:
            ip = _ip(parts[-hops])
            if ip is not None:
                return "x-forwarded-for", ip
    peer_ip = _ip(peer)
    return "peer", peer_ip if peer_ip is not None else str(peer or "unknown")


# ------------------------------------------------------------------------------ the limiter
class Bucket:
    """One named token bucket for every client: client key -> the moment its bucket is full again (monotonic s)."""

    def __init__(self, name: str, per_minute: float, burst: float, max_clients: int) -> None:
        self.name = name
        self.per_minute, self.burst = float(per_minute), max(1.0, float(burst))
        self.interval = 60.0 / max(self.per_minute, 1e-9)          # seconds one token takes to come back
        self.tolerance = self.interval * (self.burst - 1.0)        # how far ahead of now a client may run
        self.max_clients = max(10, int(max_clients))
        self.full_at: dict[int, float] = {}                        # insertion order = last-seen order (an LRU)
        self.refused = 0
        self.evicted = 0

    def take(self, key: int, now: float) -> float:
        """0.0 when the request may go ahead (a token spent), else the seconds until one is back."""
        tat = self.full_at.get(key, now)
        if tat < now:
            tat = now
        wait = tat - now - self.tolerance
        if wait > 1e-9:
            self.refused += 1
            return wait
        self.full_at.pop(key, None)                                # move to the end: most recently seen
        self.full_at[key] = tat + self.interval
        if len(self.full_at) > self.max_clients:
            self._sweep(now)
        return 0.0

    def _sweep(self, now: float) -> None:
        """Forget the clients whose bucket is full again (no change in behaviour); if that is not enough (more than
        ``max_clients`` clients in debt at once), the least recently seen until 90% of the bound."""
        d = self.full_at
        for k in [k for k, t in d.items() if t <= now]:
            del d[k]
        target = int(self.max_clients * 0.9)
        if len(d) > target:
            drop = len(d) - target
            for k in list(d)[:drop]:
                del d[k]
            self.evicted += drop
            self.full_at = dict(d)                                 # compact the table after a mass delete

    def clients(self) -> int:
        return len(self.full_at)


class Limiter:
    def __init__(self, buckets: dict[str, tuple[float, float]] | None = None, *, max_clients: int = MAX_CLIENTS,
                 mode: str = "auto", hops: int = 1, enabled: bool = True,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.enabled = enabled
        self.mode, self.hops = mode, max(1, int(hops))
        self.clock = clock
        self.buckets = {n: Bucket(n, pm, b, max_clients) for n, (pm, b) in (buckets or DEFAULTS).items()}
        self._key = secrets.token_bytes(32)                        # per process: the address is never stored
        self._lock = threading.Lock()
        self.sources: dict[str, int] = {}

    def key(self, address: object) -> int:
        raw = _network(address) if isinstance(address, ipaddress.IPv4Address | ipaddress.IPv6Address) \
            else b"p" + str(address).encode("utf-8", "replace")
        return int.from_bytes(hmac.new(self._key, raw, hashlib.sha256).digest()[:8], "big") >> 4

    def check(self, bucket: str, address: object) -> float:
        b = self.buckets.get(bucket)
        if b is None:
            return 0.0
        k = self.key(address)
        with self._lock:
            return b.take(k, self.clock())

    def info(self) -> dict:
        return {"enabled": self.enabled, "client_ip": self.mode, "proxy_hops": self.hops,
                "buckets": {n: {"per_minute": b.per_minute, "burst": b.burst, "clients": b.clients(),
                                "refused": b.refused, "evicted": b.evicted} for n, b in self.buckets.items()},
                "max_clients": next(iter(self.buckets.values())).max_clients if self.buckets else 0,
                "keyed_by": dict(self.sources)}


def _pair(raw: str | None, default: tuple[float, float], name: str) -> tuple[float, float]:
    if not raw:
        return default
    try:
        a, b = (float(x) for x in raw.replace("/", ",").split(",", 1))
        if a > 0 and b >= 1:
            return a, b
    except ValueError:
        pass
    log.warning("LEAGUE_LAB_RATE_%s=%r is not '<per minute>,<burst>': using %s", name.upper(), raw, default)
    return default


def from_env() -> Limiter:
    on = os.environ.get(SWITCH_ENV, "on").strip().lower() not in ("off", "0", "false", "no")
    buckets = {n: _pair(os.environ.get(f"LEAGUE_LAB_RATE_{n.upper()}"), d, n) for n, d in DEFAULTS.items()}
    try:
        cap = int(os.environ.get(CLIENTS_ENV) or MAX_CLIENTS)
    except ValueError:
        cap = MAX_CLIENTS
    mode = (os.environ.get(CLIENT_IP_ENV) or "auto").strip().lower()
    if mode not in MODES:
        log.warning("%s=%r is not known: auto", CLIENT_IP_ENV, mode)
        mode = "auto"
    try:
        hops = int(os.environ.get(HOPS_ENV) or 1)
    except ValueError:
        hops = 1
    return Limiter(buckets, max_clients=cap, mode=mode, hops=hops, enabled=on)


_limiter: Limiter | None = None


def limiter() -> Limiter:
    global _limiter
    if _limiter is None:
        _limiter = from_env()
    return _limiter


def reset(new: Limiter | None = None) -> Limiter:
    """A fresh limiter (tests; or after changing the environment): ``new`` or one read from the environment."""
    global _limiter
    _limiter = new if new is not None else from_env()
    return _limiter


def _headers(scope) -> dict[bytes, bytes]:
    out: dict[bytes, bytes] = {}
    for k, v in scope.get("headers") or []:
        k = k.lower()
        out[k] = out[k] + b", " + v if k == b"x-forwarded-for" and k in out else v   # several XFF lines: one list
    return out


def scope_client(scope, lim: Limiter | None = None) -> tuple[str, object]:
    lim = lim or limiter()
    peer = (scope.get("client") or (None, None))[0]
    return client_address(_headers(scope), peer, lim.mode, lim.hops)


def refusal(wait_s: float, bucket: str) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    n = max(1, math.ceil(wait_s))
    words = WORDS_ONE if n == 1 else WORDS.format(n=n)
    body = json.dumps({"error": words, "detail": words, "code": "rate_limited", "retry_after_s": n,
                       "bucket": bucket}).encode()
    return 429, [(b"content-type", b"application/json"), (b"retry-after", str(n).encode()),
                 (b"cache-control", b"no-store"), (b"content-length", str(len(body)).encode())], body


class RateLimit:
    """The middleware (pure ASGI: nothing is buffered, a refused request never reaches a route)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        lim = limiter()
        name = bucket_for(scope.get("method", "GET"), scope.get("path", ""),
                          (scope.get("query_string") or b"").decode("latin-1"))
        if name is None or not lim.enabled:
            return await self.app(scope, receive, send)
        source, address = scope_client(scope, lim)
        lim.sources[source] = lim.sources.get(source, 0) + 1
        wait = lim.check(name, address)
        if wait <= 0:
            return await self.app(scope, receive, send)
        status, headers, body = refusal(wait, name)
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def probe(scope) -> dict:
    """``GET /api/ratelimit``: how this request was keyed — the source's name and whether the address used is the
    documentation address ``203.0.113.9`` (send it in a spoofable header to see whether the edge kept it). Never the
    address itself."""
    lim = limiter()
    source, address = scope_client(scope, lim)
    return {"enabled": lim.enabled, "client_ip": lim.mode, "resolved": resolve_mode(lim.mode), "keyed_by": source,
            "test_address_used": str(address) == TEST_ADDRESS,
            "bucket_tag": format(lim.key(address) & 0xFFFF, "04x"),      # two devices, one tag = one bucket

            "buckets": {n: [b.per_minute, b.burst] for n, b in lim.buckets.items()}}
