"""Wave I-P, IP-5: Yahoo's 429 / 999 serves the answer it holds (as an empty bucket and a failure already did).
The API side of the cache audit is api/tests/test_ip5.py; docs/SECURITY_PUBLIC.md § 15."""

from __future__ import annotations

import json

import pytest

from league_lab import yahoo_client as Y


@pytest.fixture
def session():
    s = Y.YahooSession(refresh_token="RT", access_token="AT", expires_at=4e9)
    token = Y.request_session.set(s)
    yield s
    Y.request_session.reset(token)


def test_yahoo_throttled_serves_the_held_answer(session, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    now = {"t": 0.0}
    state = {"throttled": False}

    def fetch(url, headers):
        if state["throttled"]:
            return 999, {}, "Request denied"
        return 200, {}, json.dumps({"fantasy_content": {"game": [{"game_key": "461"}]}})
    c = Y.Yahoo(fetch=fetch, clock=lambda: now["t"])
    assert c.game_key() == "461"
    now["t"] += Y.TTL_S["game"] + 1
    state["throttled"] = True
    assert c.game_key() == "461" and c.stale_served == 1          # was: YahooBusy past the held answer
    c._backoff_until = 0
    with pytest.raises(Y.YahooBusy):                                # nothing held for another game: busy, as before
        c.game_key("mlb")
