"""The beta password gate, the Streamlit app's semantics without its session state.

* ---- IM-3 (Wave I-M): the gate is a switch, ``LEAGUE_LAB_GATE`` = ``open`` | ``password``. Unset (or not one of the
  two): ``password`` when LEAGUE_LAB_APP_PASSWORD is set, else ``open`` — exactly the behaviour before the switch.
  ``open`` ignores the password (no sign-in screen, no 401 "Private beta"); ``password`` with no password set keeps
  the door shut (nobody can sign in — set the password) rather than opening it by accident.
* LEAGUE_LAB_APP_PASSWORD unset (and no switch) → open (like the app: "optional gate; remove for open access").
* Gate on → every /api/* call but /api/login and /api/health needs a token: the `ll_auth` cookie (what the web app
  uses; HttpOnly, so page scripts never see it) or `Authorization: Bearer <token>` (curl, tests).
* POST /api/login {"password": …} → the token, also set as the cookie. Wrong password → 401 "That is not it."
* A token is `<expiry>.<HMAC-SHA256(expiry)>`, signed with LEAGUE_LAB_API_SECRET, else with a key derived
  from the password itself — so changing the password signs everyone out. No accounts, no server state.

Same caveat as the app: a closed door for a link, not authentication; the database role is read-only anyway.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

from .settings import env

COOKIE = "ll_auth"
TOKEN_DAYS = 180


def password() -> str:
    return env("APP_PASSWORD")


# ---- IM-3 (Wave I-M): the switch
GATES = ("open", "password")
log = logging.getLogger(__name__)
_warned: set[str] = set()


def gate() -> str:
    """``open`` | ``password``: LEAGUE_LAB_GATE when it is one of the two, else the old rule (a password set = password)."""
    raw = env("GATE").strip().lower()
    if raw in GATES:
        if raw == "password" and not password() and "nopw" not in _warned:
            _warned.add("nopw")
            log.warning("LEAGUE_LAB_GATE=password but LEAGUE_LAB_APP_PASSWORD is not set: nobody can sign in")
        return raw
    if raw and raw not in _warned:
        _warned.add(raw)
        log.warning("LEAGUE_LAB_GATE=%r is not open or password: following LEAGUE_LAB_APP_PASSWORD", raw)
    return "password" if password() else "open"


def gate_on() -> bool:
    return gate() == "password"
# ---- end IM-3


def _key() -> bytes:
    secret = env("API_SECRET")
    if secret:
        return secret.encode()
    return hashlib.sha256(b"league-lab-api|" + password().encode()).digest()


def _sign(payload: str) -> str:
    return hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()


def issue(now: float | None = None, days: int = TOKEN_DAYS) -> str:
    exp = int((now if now is not None else time.time()) + days * 86400)
    return f"{exp}.{_sign(str(exp))}"


def valid(token: str | None, now: float | None = None) -> bool:
    if not gate_on():
        return True
    if not password():          # ---- IM-3: password gate without a password: shut (the key would be a public one)
        return False
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    # IM-3: ASCII only (a non-ASCII digit or signature raised a 500 in int() / compare_digest)
    if not (exp.isascii() and exp.isdigit()) or not hmac.compare_digest(sig.encode("utf-8", "replace"), _sign(exp).encode()):
        return False
    return int(exp) > (now if now is not None else time.time())


def check_password(entered: str | None) -> bool:
    pw = password()
    return gate_on() and bool(pw) and entered is not None and hmac.compare_digest(entered.encode(), pw.encode())


def token_from(cookie: str | None, authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return cookie
