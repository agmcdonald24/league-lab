"""The beta password gate: the app's LEAGUE_LAB_APP_PASSWORD, a signed cookie or a bearer token, no accounts."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from league_lab_api import auth
from league_lab_api.main import app

from .conftest import DYNASTY, needs_db

DATA = ["/api/leagues", f"/api/leagues/{DYNASTY}/rosters", f"/api/my-week?league={DYNASTY}&team=12",
        f"/api/player/00-0036963?league={DYNASTY}&team=12", f"/api/search?league={DYNASTY}&q=allen", "/api/status"]


@pytest.fixture
def gated(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "correct horse")
    monkeypatch.delenv("LEAGUE_LAB_API_SECRET", raising=False)
    with TestClient(app) as c:
        yield c


def test_every_data_endpoint_rejects_without_a_token(gated):
    for path in DATA:
        r = gated.get(path)
        assert r.status_code == 401, path
        assert r.json()["detail"].startswith("Private beta")
    assert gated.get("/api/session").json() == {"gate": True, "signed_in": False}
    assert gated.get("/api/health").status_code == 200


def test_wrong_password(gated):
    r = gated.post("/api/login", json={"password": "wrong"})
    assert r.status_code == 401 and r.json()["detail"] == "That is not it."
    assert "ll_auth" not in r.cookies


def test_bad_tokens(gated):
    good = auth.issue()
    exp, sig = good.split(".")
    for bad in ["", "abc", f"{exp}.{'0' * 64}", f"{int(exp) + 1}.{sig}", auth.issue(now=time.time() - 200 * 86400)]:
        assert gated.get("/api/leagues", headers={"Authorization": f"Bearer {bad}"}).status_code == 401, bad


@needs_db
def test_login_then_cookie_and_bearer(gated, monkeypatch):
    r = gated.post("/api/login", json={"password": "correct horse"})
    assert r.status_code == 200 and r.json()["ok"]
    token = r.json()["token"]
    set_cookie = r.headers["set-cookie"]
    assert "ll_auth=" in set_cookie and "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie
    for path in DATA:                                   # the TestClient keeps the cookie, like the browser
        assert gated.get(path).status_code == 200, path
    assert gated.get("/api/session").json() == {"gate": True, "signed_in": True}
    with TestClient(app) as fresh:                      # no cookie: the bearer token alone
        assert fresh.get("/api/leagues").status_code == 401
        assert fresh.get("/api/leagues", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        # a new password signs everyone out (the key is derived from it unless LEAGUE_LAB_API_SECRET is set)
        monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "battery staple")
        assert fresh.get("/api/leagues", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_open_without_a_password(client):
    assert client.get("/api/session").json() == {"gate": False, "signed_in": True}
    assert client.post("/api/login", json={"password": "anything"}).json() == {"ok": True, "token": None}
