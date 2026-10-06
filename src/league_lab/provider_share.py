"""Each client's own share of the providers' budget (Wave I-O, IO-4; docs/SECURITY_PUBLIC.md § 13).

Sleeper's and MyFantasyLeague's clients each hold ONE token bucket per process (``sleeper_client.TokenBucket``: 300
Sleeper calls a minute, 60 MFL calls): every visitor spends the same budget, so one visitor opening many unknown leagues
made league setup say "busy" for everyone. Under that global bucket, each client now has its own ceiling per provider:

* **Who the client is**: the rate limiter's ``client_group`` (an IPv4 address, an IPv6 /64), set by the limiter's
  middleware in a context variable (``CLIENT``) for the request and read here where the provider bucket is taken — no
  parameter threaded through every call. Starlette carries a context variable into the route's worker thread; a thread
  pool a route starts itself must hand it on (``anyleague.user_leagues`` does, ``contextvars.copy_context``).
* **No client, no limit**: the nightly, the CLI, the tests (the limiter is off there) and a background refresh read
  ``CLIENT`` as None and are limited by the global bucket only — exactly as before.
* **The numbers** (``DEFAULTS``; why: docs/SECURITY_PUBLIC.md § 13, measured on the fixtures): Sleeper 150 calls at
  once and 60 a minute after that; MFL 50 at once and 12 a minute. A token bucket in its "virtual scheduling" form:
  one number per client in debt (the moment its share is full again), keyed by an HMAC of the client with a random
  per-process key (the address is never held), at most ``MAX_CLIENTS`` per provider (full ones dropped first, then the
  least recently seen).
* **A refusal** is the provider client's own: ``SleeperBusy`` / ``MFLBusy`` (a cached answer, even an expired one, is
  served first), which the API answers 503 "busy, try again in a minute" and the web says "Busy right now. Try again in
  a minute." — never a 500.

Switches: ``LEAGUE_LAB_PROVIDER_SHARE`` = ``off`` or ``"<per minute>,<at once>"`` for Sleeper;
``LEAGUE_LAB_PROVIDER_SHARE_MFL`` the same for MFL.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

CLIENT: ContextVar[str | None] = ContextVar("league_lab_provider_client", default=None)
ENV = "LEAGUE_LAB_PROVIDER_SHARE"
ENVS = {"sleeper": ENV, "mfl": f"{ENV}_MFL"}
# provider -> (calls a minute after the first ones, calls at once). Sleeper: an unknown league opened cold (My Week,
# Team, League with its outlook) costs 11 calls on the fixtures and ~25-35 live (the outlook's 12-20 remaining weeks),
# three ~105 at most, so 150 at once never refuses that person; a script
# opening fifty leagues (~1,300 calls) is refused after about five and then gets about two leagues a minute. MFL: one
# league opened cold costs 14 calls on the fixtures (mfl:70587), three 42: 50 at once, 12 a minute after.
DEFAULTS: dict[str, tuple[float, float]] = {"sleeper": (60.0, 150.0), "mfl": (12.0, 50.0)}
MAX_CLIENTS = 5000


class Share:
    """One provider's per-client ceilings: client key -> the moment its share is full again (monotonic seconds)."""

    def __init__(self, provider: str, per_minute: float, burst: float, max_clients: int = MAX_CLIENTS) -> None:
        self.provider = provider
        self.per_minute, self.burst = float(per_minute), max(1.0, float(burst))
        self.interval = 60.0 / max(self.per_minute, 1e-9)
        self.tolerance = self.interval * (self.burst - 1.0)
        self.max_clients = max(10, int(max_clients))
        self.full_at: dict[int, float] = {}
        self.taken = 0
        self.refused = 0
        self.evicted = 0

    def take(self, key: int, now: float) -> bool:
        tat = max(self.full_at.get(key, now), now)
        if tat - now - self.tolerance > 1e-9:
            self.refused += 1
            return False
        self.full_at.pop(key, None)                                  # the end of the dict: most recently seen
        self.full_at[key] = tat + self.interval
        self.taken += 1
        if len(self.full_at) > self.max_clients:
            d = {k: t for k, t in self.full_at.items() if t > now}  # a full share is the same as one never seen
            target = int(self.max_clients * 0.9)
            if len(d) > target:
                drop = len(d) - target
                d = dict(list(d.items())[drop:])
                self.evicted += drop
            self.full_at = d
        return True

    def info(self) -> dict:
        return {"per_minute": self.per_minute, "at_once": self.burst, "clients_in_debt": len(self.full_at),
                "calls": self.taken, "refused": self.refused, "evicted": self.evicted}


class Shares:
    def __init__(self, numbers: dict[str, tuple[float, float]] | None = None, *, enabled: bool = True,
                 clock: Callable[[], float] = time.monotonic, max_clients: int = MAX_CLIENTS) -> None:
        self.enabled = enabled
        self.clock = clock
        self.shares = {p: Share(p, pm, b, max_clients) for p, (pm, b) in (numbers or DEFAULTS).items()}
        self._key = secrets.token_bytes(32)
        self._lock = threading.Lock()

    def key(self, client: str) -> int:
        return int.from_bytes(hmac.new(self._key, client.encode("utf-8", "replace"), hashlib.sha256).digest()[:8], "big")

    def take(self, provider: str, client: str | None) -> bool:
        """True when this client may make one more call to ``provider`` now (a call is counted); always True with no
        client, a provider without a share, or the switch off."""
        s = self.shares.get(provider)
        if client is None or s is None or not self.enabled:
            return True
        k = self.key(client)
        with self._lock:
            return s.take(k, self.clock())

    def info(self) -> dict:
        return {"enabled": self.enabled, **{p: s.info() for p, s in self.shares.items()}}


def _pair(raw: str | None, default: tuple[float, float]) -> tuple[float, float]:
    try:
        a, b = (float(x) for x in str(raw).replace("/", ",").split(",", 1))
        return (a, b) if a > 0 and b >= 1 else default
    except ValueError:
        return default


def from_env() -> Shares:
    raw = (os.environ.get(ENV) or "").strip().lower()
    on = raw not in ("off", "0", "false", "no")
    numbers = {}
    for p, d in DEFAULTS.items():
        v = (os.environ.get(ENVS[p]) or "").strip()
        numbers[p] = _pair(v, d) if v and v.lower() not in ("on", "off") else d
    return Shares(numbers, enabled=on)


_shares: Shares | None = None


def shares() -> Shares:
    global _shares
    if _shares is None:
        _shares = from_env()
    return _shares


def reset(new: Shares | None = None) -> Shares:
    """A fresh set of shares (tests; after changing the environment)."""
    global _shares
    _shares = new if new is not None else from_env()
    return _shares


def take(provider: str) -> bool:
    """The provider clients' one call: the request's client (``CLIENT``) may spend one more call to ``provider``."""
    c = CLIENT.get()
    return True if c is None else shares().take(provider, c)


@contextmanager
def acting_for(client: str | None) -> Iterator[None]:
    """``CLIENT`` set for the block (the limiter's middleware; tests)."""
    token = CLIENT.set(client)
    try:
        yield
    finally:
        CLIENT.reset(token)
