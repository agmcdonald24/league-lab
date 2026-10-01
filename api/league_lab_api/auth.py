"""The beta password gate, the Streamlit app's semantics without its session state.

* LEAGUE_LAB_APP_PASSWORD unset → open (like the app: "optional gate; remove for open access").
* Set → every /api/* call but /api/login and /api/health needs a token: the `ll_auth` cookie (what the web app
  uses; HttpOnly, so page scripts never see it) or `Authorization: Bearer <token>` (curl, tests).
* POST /api/login {"password": …} → the token, also set as the cookie. Wrong password → 401 "That is not it."
* A token is `<expiry>.<HMAC-SHA256(expiry)>`, signed with LEAGUE_LAB_API_SECRET, else with a key derived
  from the password itself — so changing the password signs everyone out. No accounts, no server state.

Same caveat as the app: a closed door for a link, not authentication; the database role is read-only anyway.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from .settings import env

COOKIE = "ll_auth"
TOKEN_DAYS = 180


def password() -> str:
    return env("APP_PASSWORD")


def gate_on() -> bool:
    return bool(password())


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
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    if not exp.isdigit() or not hmac.compare_digest(sig, _sign(exp)):
        return False
    return int(exp) > (now if now is not None else time.time())


def check_password(entered: str | None) -> bool:
    pw = password()
    return bool(pw) and entered is not None and hmac.compare_digest(entered.encode(), pw.encode())


def token_from(cookie: str | None, authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return cookie
