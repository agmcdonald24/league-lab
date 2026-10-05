"""Wave I-I, II-5: the setup flow's provider capabilities and error words (review § 9; docs/PROVIDERS.md).

* ``platforms.capabilities(provider)``: the eight features, explicit per provider — Sleeper and MFL as built, ESPN and
  Yahoo not supported; ``unavailable(provider, feature)`` is the sentence a screen says instead of substituting.
* ``GET /api/providers``; ``/api/leagues?sleeper=<link or id>`` (a Sleeper league without a username);
  ``capabilities`` on the username and MFL answers.
* The setup errors: ``{error, detail, code, fix}`` — specific, recoverable, keyed (``ondemand.SETUP_CODES``).
Fixtures only (the Sleeper and MFL fixtures under api/tests/fixtures/); no outside call.
"""

from __future__ import annotations

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import platforms as P

from league_lab_api import ondemand

from .conftest import needs_db

TEST_LEAGUE = "9000000000000000001"


# ------------------------------------------------------------------ the matrix
def test_every_provider_states_every_feature():
    assert P.FEATURES == ("scoring", "roster_slots", "matchups", "players", "waivers", "transactions", "team_assets", "news")
    for prov in P.PROVIDERS:
        c = P.capabilities(prov)
        assert c["provider"] == prov and c["name"] and c["short"] and c["status"] in ("supported", "not_supported",
                                                                                      "unverified")  # IK-3: ESPN / Yahoo
        assert set(c["connect"]) == {"kind", "label", "example", "where"}
        assert list(c["features"]) == list(P.FEATURES)
        for f, v in c["features"].items():
            assert set(v) == {"label", "status", "words", "unavailable"}
            assert v["status"] in ("yes", "partial", "no") and v["words"]
            # "not available" is said exactly when the feature is not read — never for a yes / partial
            assert (v["unavailable"] is not None) == (v["status"] == "no"), (prov, f)


def test_sleeper_and_mfl_as_built():
    s, m = P.capabilities("sleeper"), P.capabilities("mfl")
    assert s["status"] == m["status"] == "supported"
    assert s["connect"]["kind"] == "username" and m["connect"]["kind"] == "league_link"
    assert {f for f, v in s["features"].items() if v["status"] == "no"} == set()
    # MFL: transactions are not read (platforms.MFLLeagues.transactions answers []): said, not shown as "no moves"
    assert m["features"]["transactions"]["status"] == "no"
    assert P.unavailable("mfl", "transactions") == "Transactions: not available for MFL leagues yet"
    assert m["features"]["transactions"]["unavailable"] == "Transactions: not available for MFL leagues yet"
    assert m["features"]["matchups"]["status"] == "partial"          # the week's live points are not read
    assert m["features"]["team_assets"]["status"] == "partial"       # TMQB / TMPK priced; picks / budgets not read
    assert all(P.unavailable("sleeper", f) is None for f in P.FEATURES)


def test_mfl_transactions_really_are_not_read():
    """The matrix is a statement about the code: the MFL adapter's transactions call answers nothing."""
    mf = P.MFLLeagues(M.MFL(fixtures="/nonexistent"), lambda: {})
    assert mf.transactions("mfl:70587", 1) == []


def test_espn_and_yahoo_are_not_supported():
    """IK-3 (Wave I-K): ESPN and Yahoo are built — as built, not verified live (test_ik3 pins their rows); what stays
    true here: nothing on them says "yes" until the PO verifies a live league."""
    for prov in ("espn", "yahoo"):
        c = P.capabilities(prov)
        assert c["status"] == "unverified" and c["connect"]["kind"] in ("league_link", "oauth")
        assert all(v["status"] == "partial" for v in c["features"].values())


def test_capabilities_for_a_league_key_and_unknowns():
    assert P.capabilities_for("mfl:70587")["provider"] == "mfl"
    assert P.capabilities_for("1389709692405551104")["provider"] == "sleeper"
    with pytest.raises(KeyError):
        P.capabilities("fleaflicker")
    with pytest.raises(KeyError):
        P.unavailable("mfl", "trades")
    a, b = P.capabilities("mfl"), P.capabilities("mfl")
    a["features"]["news"]["status"] = "changed"
    assert b["features"]["news"]["status"] == "yes"                  # a fresh dict each call


def test_route_providers(client):
    r = client.get("/api/providers")
    assert r.status_code == 200, r.text
    d = r.json()
    assert [p["provider"] for p in d["providers"]] == ["sleeper", "mfl", "espn", "yahoo"]
    assert d["features"] == list(P.FEATURES)
    assert d["providers"][1] == P.capabilities("mfl")


# ------------------------------------------------------------------ the error words
def _err(r, status: int, code: str) -> dict:
    assert r.status_code == status, r.text
    d = r.json()
    assert d["code"] == code and d["code"] in ondemand.SETUP_CODES and d["error"] == d["detail"]
    return d


def test_unknown_sleeper_username_says_so(client):
    d = _err(client.get("/api/leagues", params={"username": "nobody_at_all"}), 404, "sleeper_user_unknown")
    assert d["error"] == "That Sleeper username does not exist: “nobody_at_all”."
    assert "the name you sign in to Sleeper with" in d["fix"] and "league's link" in d["fix"]


def test_impossible_sleeper_username(client):
    d = _err(client.get("/api/leagues", params={"username": "../etc"}), 404, "sleeper_username_invalid")
    assert d["error"].startswith("“../etc” cannot be a Sleeper username")


@needs_db
def test_sleeper_league_by_id_and_by_link(client):
    by_id = client.get("/api/leagues", params={"sleeper": TEST_LEAGUE})
    by_link = client.get("/api/leagues", params={"sleeper": f"https://sleeper.com/leagues/{TEST_LEAGUE}/team"})
    assert by_id.status_code == by_link.status_code == 200, by_id.text
    d = by_id.json()
    assert d == by_link.json()
    assert d["platform"] == "sleeper" and d["roster_id"] is None
    assert d["league"]["league_id"] == TEST_LEAGUE and d["league"]["platform"] == "sleeper"
    assert d["league"]["total_rosters"] == 10 and len(d["teams"]) == 10
    assert [t["roster_id"] for t in d["teams"]] == list(range(1, 11))
    assert set(d["teams"][0]) == {"roster_id", "team_name", "manager_name"}
    assert set(d["card"]) >= {"lineup", "scoring", "check_path"}
    assert d["capabilities"] == P.capabilities("sleeper")


def test_sleeper_league_errors(client):
    d = _err(client.get("/api/leagues", params={"sleeper": "my league"}), 404, "sleeper_link_invalid")
    assert d["error"] == "That is not a Sleeper league link or id." and "/leagues/" in d["fix"]
    d = _err(client.get("/api/leagues", params={"sleeper": "1234567890123"}), 404, "sleeper_league_unknown")
    assert d["error"] == "Sleeper has no football league 1234567890123."


def test_sleeper_league_id_parsing():
    f = ondemand.sleeper_league_id
    assert f("1389709692405551104") == "1389709692405551104"
    assert f("https://sleeper.com/leagues/1389709692405551104/team") == "1389709692405551104"
    assert f("sleeper.app/leagues/1389709692405551104") == "1389709692405551104"
    assert f("MacZaddy") is None and f("12345") is None and f("") is None


def test_private_mfl_league_names_the_league_and_the_commissioner(client):
    d = _err(client.get("/api/leagues", params={"mfl": "99999999"}), 404, "mfl_league_private")
    assert d["error"].startswith("MFL league 99999999 is private or does not exist. Ask the commissioner to allow API access")
    assert "/home/" in d["fix"]
    # the one MFL box (a link) answers the same
    d2 = _err(client.get("/api/leagues", params={"mfl_search": "https://www45.myfantasyleague.com/2026/home/99999999"}),
              404, "mfl_league_private")
    assert d2 == d


def test_mfl_link_that_is_not_one(client):
    d = _err(client.get("/api/leagues", params={"mfl": "https://example.com/nothing"}), 404, "mfl_link_invalid")
    assert d["error"] == "That is not a MyFantasyLeague league link or id." and "league's name" in d["fix"]


def test_provider_down_and_busy_carry_a_code(client, monkeypatch):
    def down(self, text):
        raise M.MFLUnavailable("MyFantasyLeague https://api.myfantasyleague.com/…: HTTP 500")
    monkeypatch.setattr(M.MFL, "league_search", down)
    r = client.get("/api/leagues", params={"mfl_search": "addicts"})
    assert r.status_code == 502 and r.json()["code"] == "provider_down" and r.json()["error"] == "MyFantasyLeague did not answer"

    def busy(*_a, **_k):
        raise A.SleeperBusy("busy, try again in a minute")
    monkeypatch.setattr(ondemand, "sleeper_league", busy)
    r = client.get("/api/leagues", params={"sleeper": TEST_LEAGUE})
    assert r.status_code == 503 and r.json()["code"] == "busy"


@needs_db
def test_setup_answers_carry_their_providers_capabilities(client):
    d = client.get("/api/leagues", params={"mfl": "https://www45.myfantasyleague.com/2026/home/70587"}).json()
    assert d["platform"] == "mfl" and d["capabilities"] == P.capabilities("mfl")
    assert d["capabilities"]["features"]["transactions"]["unavailable"] == "Transactions: not available for MFL leagues yet"
    u = client.get("/api/leagues", params={"username": "test_manager"}).json()
    assert u["capabilities"] == P.capabilities("sleeper")


# ---- IL-5 (Wave I-L): the matrix under the switches — ESPN's kill switch says "off"; verified providers say supported
def test_the_matrix_under_the_switches(monkeypatch):
    monkeypatch.setenv(P.ESPN_SWITCH_ENV, "off")
    monkeypatch.setenv(P.VERIFIED_ENV, "yahoo")
    got = {c["provider"]: c["status"] for c in P.all_capabilities()}
    assert got == {"sleeper": "supported", "mfl": "supported", "espn": "off", "yahoo": "supported"}
    assert P.capabilities("espn")["off"] == "ESPN leagues: not available right now"
    assert all(v["status"] in ("yes", "partial", "no") for v in P.capabilities("espn")["features"].values())
# ---- end IL-5
