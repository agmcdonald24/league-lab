"""Sealed cookies (Wave I-K, IK-1): a small JSON payload encrypted and authenticated with ``LEAGUE_LAB_API_SECRET``,
for a browser cookie the server reads back and never stores (ESPN's ``ll_espn``; IK-2's ``ll_yahoo`` may use it).

Standard library only (the lock has no ``cryptography``): encrypt-then-MAC with HMAC-SHA256 as the PRF —

* two keys per purpose from the secret: ``enc = HMAC(secret, "league-lab sealed|enc|<purpose>")``, ``mac`` likewise;
* a 16-byte random nonce; the keystream is ``HMAC(enc, nonce || counter)`` blocks (counter mode), XORed with the
  payload ``{"v": 1, "t": <issued, epoch s>, "d": <data>}``;
* the tag is ``HMAC(mac, purpose || "." || version || nonce || ciphertext)`` (32 bytes), checked in constant time
  before anything is decrypted;
* the token: ``v1.<base64url(nonce || ciphertext || tag)>``.

No secret (or one under 16 characters): ``seal`` raises ``SealUnavailable`` and ``unseal`` answers None — the
features that need it say they are off. A token older than ``max_age_s``, tampered with, sealed for another purpose
or with another secret: None. The payload is never logged here; callers must not log it either.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

SECRET_ENV = "LEAGUE_LAB_API_SECRET"
VERSION = "v1"
MIN_SECRET = 16
_NONCE, _TAG, _BLOCK = 16, 32, 32


class SealUnavailable(RuntimeError):
    """No ``LEAGUE_LAB_API_SECRET`` (16+ characters) to seal with."""


def available() -> bool:
    return len(os.environ.get(SECRET_ENV) or "") >= MIN_SECRET


def _keys(purpose: str) -> tuple[bytes, bytes]:
    secret = (os.environ.get(SECRET_ENV) or "").encode()
    if len(secret) < MIN_SECRET:
        raise SealUnavailable("LEAGUE_LAB_API_SECRET is not set")
    enc = hmac.new(secret, f"league-lab sealed|enc|{purpose}".encode(), hashlib.sha256).digest()
    mac = hmac.new(secret, f"league-lab sealed|mac|{purpose}".encode(), hashlib.sha256).digest()
    return enc, mac


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:n])


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b, strict=True))


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def seal(purpose: str, data: Any, *, now: float | None = None) -> str:
    """The token for ``data`` (JSON-able), bound to ``purpose``."""
    enc, mac = _keys(purpose)
    body = json.dumps({"v": 1, "t": int(now if now is not None else time.time()), "d": data},
                      separators=(",", ":")).encode()
    nonce = secrets.token_bytes(_NONCE)
    ct = _xor(body, _stream(enc, nonce, len(body)))
    tag = hmac.new(mac, f"{purpose}.{VERSION}".encode() + nonce + ct, hashlib.sha256).digest()
    return f"{VERSION}.{_b64(nonce + ct + tag)}"


def unseal(purpose: str, token: str | None, *, max_age_s: float, now: float | None = None) -> Any | None:
    """``data`` back, or None (no secret, malformed, wrong purpose / secret, tampered, expired)."""
    if not token or not isinstance(token, str) or not token.startswith(VERSION + ".") or len(token) > 8192:
        return None
    try:
        enc, mac = _keys(purpose)
        raw = _unb64(token[len(VERSION) + 1:])
    except (SealUnavailable, ValueError):
        return None
    if len(raw) < _NONCE + _TAG + 1:
        return None
    nonce, ct, tag = raw[:_NONCE], raw[_NONCE:-_TAG], raw[-_TAG:]
    want = hmac.new(mac, f"{purpose}.{VERSION}".encode() + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, want):
        return None
    try:
        body = json.loads(_xor(ct, _stream(enc, nonce, len(ct))).decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict) or body.get("v") != 1:
        return None
    t = body.get("t")
    if not isinstance(t, int) or (now if now is not None else time.time()) - t > max_age_s:
        return None
    return body.get("d")
