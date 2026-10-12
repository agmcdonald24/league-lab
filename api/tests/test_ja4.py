"""JA-4 (Wave J-A): small faults on game-day screens — the news on Waivers' claims (a second, small read after the
claims show; nothing reads it), the depth and refuse reasons as sentences, the trade's role notes."""

from __future__ import annotations

from league_lab_api import decision_news, decisions, news, ratelimit

from .conftest import SCRUBS, needs_db

JEFFERSON = "00-0036322"


def _item(headline: str) -> dict:
    return {"headline": headline, "date": "2026-10-10T14:00:00Z", "source": "RotoWire via ESPN", "url": None, "about": "player"}


# ------------------------------------------------------------------------------------------------ 1. Waivers' claims
def test_the_claim_news_route_is_bounded_validated_and_a_read(client, monkeypatch):
    assert ratelimit.bucket_for("GET", "/api/news/players", "ids=00-0036322") == "read"
    for bad in ("", "x", "00-0036322,00-0036323,00-0036324,00-0036325,00-0036326", "00-003632", "1;drop"):
        assert client.get(f"/api/news/players?ids={bad}").status_code == 400
    monkeypatch.setattr(news, "recent", lambda ids, **k: [(JEFFERSON, _item("Jefferson (ankle) ruled out"))] if JEFFERSON in ids else [])
    r = client.get(f"/api/news/players?ids={JEFFERSON},00-0039075")
    assert r.status_code == 200 and "max-age" in r.headers["cache-control"]
    ln = r.json()["lines"][JEFFERSON][0]
    assert ln["text"] == "Jefferson (ankle) ruled out" and ln["source"] == "RotoWire via ESPN" and ln["why_here"] is None
    assert ln["forecast_words"] == "Context only: not in the projection"
    assert "00-0039075" not in r.json()["lines"]
    monkeypatch.setattr(news, "recent", lambda ids, **k: [])
    assert client.get(f"/api/news/players?ids={JEFFERSON}").json() == {"lines": {}}


def test_a_failing_reader_is_no_line_not_an_error(client, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("feed down")
    monkeypatch.setattr(decision_news, "lines_for", boom)
    r = client.get(f"/api/news/players?ids={JEFFERSON}")
    assert r.status_code == 200 and r.json() == {"lines": {}}


@needs_db
def test_waivers_answer_is_identical_with_the_news_on_and_off(client, monkeypatch):
    url = f"/api/waivers?league={SCRUBS}&team=2"
    monkeypatch.setattr(news, "recent", lambda ids, **k: [])
    off = client.get(url).json()
    monkeypatch.setattr(news, "recent", lambda ids, **k: [(g, _item("a headline")) for g in ids])
    on = client.get(url).json()
    for k in ("top3", "moves", "answer", "views"):
        assert on.get(k) == off.get(k)                       # no number, order or verdict moves on a headline


# ------------------------------------------------------------------------------------------------ 2. sentences
def test_why_a_player_cannot_play_is_a_sentence():
    assert decisions.cannot_sentence("Jaylen Warren", "game started (bench)", 4) == (
        "Jaylen Warren's game has started, so he cannot be moved this week")
    assert decisions.cannot_sentence("Breece Hall", "Out", 4) == "Breece Hall cannot play in week 4: he is ruled out"
    assert decisions.because_words("bye") == "he is on a bye"
    assert decisions.because_words("game started (bench)") == "his game has started"
    for r in ("game started (bench)", "Out", "bye", "IR slot", "taxi squad", "no NFL team", "Doubtful", "weird"):
        s = decisions.cannot_sentence("X", r, 4)
        assert "(" not in s and ")" not in s and "cannot)" not in s


# ------------------------------------------------------------------------------------------------ 3. the role note
CHASE = "00-0036900"           # left in the 2nd quarter of week 4 (IX-1's case), hurt on a play


@needs_db
def test_the_trade_role_note_is_the_cards_own():
    from league_lab import roles

    from league_lab_api.db import query
    n = decision_news.role_note(CHASE, "WR", 2026, 4)
    rc = roles.role_change(query(roles.PLAYER_SEASON_SQL, (CHASE, 2026, 4)), "WR")
    assert n["role"] == rc["headline"] and n["status"] == rc["status"]            # the card's Role block's headline
    assert n["left_early"].startswith("Week 4: ") and "2nd quarter" in n["left_early"]
    assert decision_news.role_note("00-0033000", "K", 2026, 4) is None             # a kicker has no role note
    ans = {"week": 5, "give": [{"gsis_id": CHASE, "sleeper_id": "7564", "position": "WR"}], "get": [], "cut": []}
    out = decision_news.with_trade_roles(dict(ans))
    assert list(out["roles"]) == ["7564"] and out["roles"]["7564"]["left_early"] == n["left_early"]


def test_a_failing_read_is_no_role_note(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("database gone")
    monkeypatch.setattr(decision_news, "role_note", boom)
    assert decision_news.with_trade_roles({"week": 5, "give": [{"gsis_id": CHASE, "sleeper_id": "1", "position": "WR"}]})["roles"] == {}
