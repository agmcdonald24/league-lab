"""Wave I-K, IK-3: the four-provider seam (``platforms.Router``), ESPN / Yahoo capabilities, the setup answers.

* ``provider_of`` / ``check_key`` / the old names; the Router dispatching ``espn:`` / ``yahoo:`` keys to their adapters
  and a provider whose module is missing answering ``ProviderNotConfigured`` (never a crash);
* ``capabilities("espn")`` / ``("yahoo")``: as built, every feature partial and said unverified;
* ``/api/providers`` (``espn_private``, ``yahoo_configured``), ``/api/leagues?espn=`` / ``?yahoo=`` / ``?yahoo_me=1``,
  the II-5-style setup errors, the league card, the team a link names, the private-league gate.

The ESPN / Yahoo leagues here are ``league_lab.provider_stubs`` (``LEAGUE_LAB_PROVIDER_STUBS=1``): synthetic, the
Sleeper fixture "Test League" re-keyed as ``espn:4242`` / ``yahoo:461.l.4242`` — they prove the seam, not a provider's
translation (IK-1's / IK-2's tests). Fixtures only; no outside call.
"""

from __future__ import annotations

import pytest
from league_lab import anyleague as A
from league_lab import platforms as P

from league_lab_api import ondemand

from .conftest import needs_db

TEST_LEAGUE = "9000000000000000001"
ESPN, YAHOO = "espn:4242", "yahoo:461.l.4242"


@pytest.fixture
def stubs(monkeypatch):
    monkeypatch.setenv(P.STUBS_ENV, "1")
    for k in ("LEAGUE_LAB_ESPN_PRIVATE", "LEAGUE_LAB_YAHOO_CLIENT_ID", "LEAGUE_LAB_YAHOO_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    A._default = None
    yield
    A._default = None


@pytest.fixture
def no_adapters(monkeypatch):
    """A server without IK-1's / IK-2's modules (whatever is in the tree): the adapters' import fails."""
    monkeypatch.delenv(P.STUBS_ENV, raising=False)
    monkeypatch.setattr(P, "ADAPTERS", {"espn": ("no_such_espn_client", "ESPN", "no_such_espn_leagues", "ESPNLeagues"),
                                        "yahoo": ("no_such_yahoo_client", "Yahoo", "no_such_yahoo_leagues", "YahooLeagues")})
    A._default = None
    yield
    A._default = None


def _err(r, status: int, code: str) -> dict:
    assert r.status_code == status, r.text
    d = r.json()
    assert d["code"] == code and d["code"] in ondemand.SETUP_CODES and d["error"] == d["detail"], d
    return d


# ------------------------------------------------------------------ keys
def test_provider_of_and_the_old_names():
    assert [P.provider_of(k) for k in ("1389709692405551104", "mfl:70587", "ESPN:4242", "yahoo:461.l.4242", "", None)] == \
        ["sleeper", "mfl", "espn", "yahoo", "sleeper", "sleeper"]
    assert P.platform("mfl:70587") == "mfl" and P.platform("espn:1") == "espn"         # platform = provider_of
    assert P.is_mfl("MFL:70587") and not P.is_mfl("espn:4242") and P.is_espn("espn:4242") and P.is_yahoo(YAHOO)
    assert P.is_sleeper(TEST_LEAGUE) and not P.is_sleeper("mfl:1")
    assert [P.provider_short(k) for k in (TEST_LEAGUE, "mfl:1", ESPN, YAHOO)] == ["Sleeper", "MFL", "ESPN", "Yahoo"]


def test_check_key_four_providers():
    assert P.check_key(" 1389709692405551104 ") == "1389709692405551104"
    assert P.check_key("MFL:70587") == "mfl:70587"
    assert P.check_key("ESPN:4242") == "espn:4242" and P.check_key("espn:2025:4242") == "espn:2025:4242"
    assert P.check_key("Yahoo:461.L.4242") == "yahoo:461.l.4242"
    assert P.espn_id("espn:2025:4242") == "4242" and P.yahoo_key("yahoo:461.l.4242") == "461.l.4242"
    assert P.check_key("yahoo:NFL.l.42") == "yahoo:nfl.l.42"            # Yahoo's code for this season's game (IK-2)
    for bad in ("espn:", "espn:abc", "espn:42/../x", "yahoo:4242", "yahoo:nhl.l.42", "yahoo:461.l.", "mfl:x", "../x"):
        with pytest.raises(A.LeagueNotFound):
            P.check_key(bad)


# ------------------------------------------------------------------ the Router
def test_router_dispatches_espn_and_yahoo_to_their_adapters(stubs):
    r = A.sleeper()
    lg = r.league(ESPN)
    assert lg["league_id"] == ESPN and lg["platform"] == "espn" and lg["espn"]["url"].endswith("leagueId=4242")
    assert r.league(YAHOO)["platform"] == "yahoo"
    ros = r.rosters(ESPN)
    assert {x["league_id"] for x in ros} == {ESPN} and len(ros) == 10
    assert [x["roster_id"] for x in ros] == [x["roster_id"] for x in r.rosters(TEST_LEAGUE)]   # the stub re-keys
    assert {u["platform"] for u in r.users(YAHOO)} == {"yahoo"}
    assert set(r.stats()) >= {"espn", "yahoo"}
    assert r.serving(ESPN) is r.espn and r.serving(YAHOO) is r.yahoo and r.serving(TEST_LEAGUE) is r.sleeper


def test_router_sleeper_and_mfl_answers_unchanged(stubs):
    """A new provider adds; it never changes a Sleeper or MFL answer (Rule 2)."""
    from league_lab.sleeper_client import Sleeper
    r = A.sleeper()
    plain = Sleeper()
    assert r.league(TEST_LEAGUE) == plain.league(TEST_LEAGUE)
    assert r.rosters(TEST_LEAGUE) == plain.rosters(TEST_LEAGUE)
    assert r.league("mfl:70587") == P.MFLLeagues(r.mfl.client, r.sleeper.players).league("mfl:70587")
    r.league(ESPN)                                     # an adapter built: Sleeper's directory is still Sleeper's
    assert set(r.players()) >= set(plain.players())


def test_a_provider_without_its_module_says_not_configured(no_adapters, client):
    r = A.sleeper()
    with pytest.raises(P.ProviderNotConfigured) as e:
        r.league(ESPN)
    assert e.value.code == "espn_not_configured" and isinstance(e.value, A.LeagueNotFound)
    with pytest.raises(P.ProviderNotConfigured) as e:
        r.rosters(YAHOO)
    assert e.value.code == "yahoo_not_configured"
    assert r.league(TEST_LEAGUE)["league_id"] == TEST_LEAGUE                # Sleeper unaffected
    d = _err(client.get("/api/leagues", params={"espn": "4242"}), 404, "espn_not_configured")
    assert d["error"] == "ESPN leagues are not set up on this server yet." and "Coming soon" in d["fix"]
    _err(client.get("/api/leagues", params={"yahoo": "461.l.4242"}), 404, "yahoo_not_configured")
    # a screen asked for an ESPN league on such a server: a clean 404 in words, never a 500
    r2 = client.get("/api/my-week", params={"league": ESPN, "team": 1})
    assert r2.status_code == 404 and "not set up" in r2.json()["error"]


# ------------------------------------------------------------------ capabilities
def test_espn_and_yahoo_capabilities_as_built_unverified():
    for prov, kind in (("espn", "league_link"), ("yahoo", "oauth")):
        c = P.capabilities(prov)
        assert c["status"] == "unverified" and c["connect"]["kind"] == kind and c["note"]
        assert set(c["connect"]) == {"kind", "label", "example", "where"}
        for f, v in c["features"].items():
            assert v["status"] == "partial", (prov, f)
            assert v["words"].endswith(P.UNVERIFIED) and v["unavailable"] is None
            assert P.unavailable(prov, f) is None
    assert "leagueId=" in P.capabilities("espn")["connect"]["example"]
    assert "/f1/" in P.capabilities("yahoo")["connect"]["example"]
    assert "Unofficial" in P.capabilities("espn")["note"]
    # Sleeper / MFL carry no unverified words
    assert not any(P.UNVERIFIED in v["words"] for p in ("sleeper", "mfl") for v in P.capabilities(p)["features"].values())


def test_providers_route_flags(client, monkeypatch):
    for k in ("LEAGUE_LAB_ESPN_PRIVATE", "LEAGUE_LAB_YAHOO_CLIENT_ID", "LEAGUE_LAB_YAHOO_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    d = client.get("/api/providers").json()
    assert [p["provider"] for p in d["providers"]] == ["sleeper", "mfl", "espn", "yahoo"]
    assert d["espn_private"] is False and d["yahoo_configured"] is False
    assert d["providers"][2] == P.capabilities("espn")
    monkeypatch.setenv("LEAGUE_LAB_ESPN_PRIVATE", "on")
    assert ondemand.espn_private() is False                   # the switch without a secret to seal the cookie: off
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "x" * 32)
    monkeypatch.setenv("LEAGUE_LAB_YAHOO_CLIENT_ID", "id")
    monkeypatch.setenv("LEAGUE_LAB_YAHOO_CLIENT_SECRET", "secret")
    assert ondemand.provider_flags() == {"espn_private": True, "yahoo_configured": True}


# ------------------------------------------------------------------ the links
@pytest.mark.parametrize("text,key,team", [
    ("4242", "espn:4242", None),
    ("espn:4242", "espn:4242", None),
    ("https://fantasy.espn.com/football/league?leagueId=4242", "espn:4242", None),
    ("fantasy.espn.com/football/team?leagueId=4242&teamId=3&seasonId=2026", "espn:2026:4242", "3"),
    ("https://fantasy.espn.com/football/league/standings?seasonId=2025&leagueId=4242", "espn:2025:4242", None),
])
def test_espn_links(text, key, team):
    assert ondemand.espn_parse(text) == (key, team)


@pytest.mark.parametrize("text,key,team", [
    ("461.l.4242", "yahoo:461.l.4242", None),
    ("yahoo:461.l.4242", "yahoo:461.l.4242", None),
    ("461.l.4242.t.3", "yahoo:461.l.4242", "3"),
    ("https://football.fantasysports.yahoo.com/f1/4242", "yahoo:461.l.4242", None),
    ("football.fantasysports.yahoo.com/f1/4242/3", "yahoo:461.l.4242", "3"),
    ("4242", "yahoo:461.l.4242", None),
])
def test_yahoo_links(text, key, team, monkeypatch):
    monkeypatch.setattr(ondemand, "yahoo_game_key", lambda: "461")
    assert ondemand.yahoo_parse(text) == (key, team)


# ------------------------------------------------------------------ the setup answers (stubs)
def test_espn_setup_errors(stubs, client, monkeypatch):
    d = _err(client.get("/api/leagues", params={"espn": "https://example.com/x"}), 404, "espn_link_invalid")
    assert d["error"] == "That is not an ESPN league link or id." and "leagueId=" in d["fix"]
    d = _err(client.get("/api/leagues", params={"espn": "999"}), 404, "espn_league_unknown")
    assert d["error"].startswith("ESPN has no league 999") and "leagueId=" in d["fix"]
    d = _err(client.get("/api/leagues", params={"espn": "5150"}), 404, "espn_league_private")
    assert "ESPN league 5150 is private" in d["error"] and "private_form" not in d
    monkeypatch.setenv("LEAGUE_LAB_ESPN_PRIVATE", "on")
    monkeypatch.setattr(ondemand, "espn_private", lambda: True)
    d = _err(client.get("/api/leagues", params={"espn": "5150"}), 404, "espn_league_private")
    assert d["private_form"] is True and d["provider"] == "espn"


def test_yahoo_setup_errors(stubs, client):
    d = _err(client.get("/api/leagues", params={"yahoo": "not a league"}), 404, "yahoo_link_invalid")
    assert d["error"].startswith("That is not a Yahoo league link") and "/f1/" in d["fix"]
    d = _err(client.get("/api/leagues", params={"yahoo": "461.l.999"}), 404, "yahoo_league_unknown")
    assert d["error"].startswith("Yahoo has no league")


@needs_db
def test_espn_league_card_by_id_and_by_link(stubs, client):
    a = client.get("/api/leagues", params={"espn": "4242"})
    b = client.get("/api/leagues", params={"espn": "https://fantasy.espn.com/football/league?leagueId=4242"})
    assert a.status_code == b.status_code == 200, a.text
    d = a.json()
    assert d == b.json()
    assert d["platform"] == "espn" and d["roster_id"] is None and d["league"]["league_id"] == ESPN
    assert d["league"]["platform"] == "espn" and d["league"]["url"].startswith("https://fantasy.espn.com/")
    assert len(d["teams"]) == 10 and set(d["teams"][0]) == {"roster_id", "team_name", "manager_name"}
    assert d["card"]["lineup"]["text"].startswith("Your lineup: ") and d["card"]["check_path"].endswith("espn%3A4242")
    assert d["capabilities"]["provider"] == "espn" and d["espn_private"] is False
    assert d["players"] == d["mapped"] and d["unmapped"] == []
    # a team link preselects the team
    t = client.get("/api/leagues", params={"espn": "fantasy.espn.com/football/team?leagueId=4242&teamId=3"}).json()
    assert t["roster_id"] == 3


@needs_db
def test_yahoo_league_card_by_link(stubs, client):
    r = client.get("/api/leagues", params={"yahoo": "https://football.fantasysports.yahoo.com/f1/4242/3"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["platform"] == "yahoo" and d["league"]["league_id"] == YAHOO and d["roster_id"] == 3
    assert d["league"]["url"] == "https://football.fantasysports.yahoo.com/f1/4242"
    assert d["capabilities"]["provider"] == "yahoo" and len(d["teams"]) == 10 and d["card"]


@needs_db
def test_yahoo_me_not_configured_not_connected_connected(stubs, client, monkeypatch):
    monkeypatch.delenv(P.STUBS_ENV)                   # a real server without Yahoo's keys: "coming soon"
    d = client.get("/api/leagues", params={"yahoo_me": "1"})
    assert d.status_code == 200 and d.headers["cache-control"] == "no-store"
    d = d.json()
    assert d["configured"] is False and d["connected"] is False and d["leagues"] == []
    assert d["note"] == ondemand.YAHOO_NOTES["not_configured"]
    monkeypatch.setenv(P.STUBS_ENV, "1")
    monkeypatch.setenv("LEAGUE_LAB_YAHOO_CLIENT_ID", "id")
    monkeypatch.setenv("LEAGUE_LAB_YAHOO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "s" * 40)            # IK-2: the cookie is sealed with it
    d = client.get("/api/leagues", params={"yahoo_me": "1"}).json()
    assert d["configured"] is True and d["connected"] is False and d["note"] == ondemand.YAHOO_NOTES["not_connected"]
    client.cookies.set("ll_yahoo", "stub-token")
    d = client.get("/api/leagues", params={"yahoo_me": "1"}).json()
    assert d["connected"] is True and d["note"] is None
    (row,) = d["leagues"]
    assert row["league_id"] == YAHOO and row["roster_id"] == 3 and row["team_name"] and row["card"]
    assert row["total_rosters"] == 10 and row["scoring_label"]


# ------------------------------------------------------------------ the screens on a prefixed key (stubs)
@needs_db
def test_my_week_on_an_espn_key(stubs, client):
    r = client.get("/api/my-week", params={"league": ESPN, "team": 3})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["league_id"] == ESPN and d["platform"] == "espn" and d["source"] == "sleeper"
    assert d["edit_link"]["platform"] == "ESPN" and d["edit_link"]["url"].endswith("leagueId=4242")
    assert d["on_demand"]["espn_unmapped"] == [] and "provider_scoring_note" in d["on_demand"]
    assert d["lineup"], "the lineup is solved for the re-keyed league"
    rost = client.get(f"/api/leagues/{ESPN}/rosters")
    assert rost.status_code == 200 and len(rost.json()) == 10


def test_private_espn_league_is_gated_before_any_route(stubs, client):
    """A private league answers its setup error on every route (IK-1's require_access runs before the memo)."""
    for path, params in (("/api/my-week", {"league": "espn:5150", "team": 1}), ("/api/waivers", {"league": "espn:5150"}),
                         ("/api/leagues/espn:5150/rosters", {})):
        _err(client.get(path, params=params), 404, "espn_league_private")
    r = client.post("/api/trades/evaluate", json={"league": "espn:5150", "team": 1, "give": [], "get": []})
    _err(r, 404, "espn_league_private")


def test_provider_down_names_the_provider(stubs, client, monkeypatch):
    def down(*_a, **_k):
        raise A.SleeperUnavailable("ESPN did not answer (stub)")
    monkeypatch.setattr(A.sleeper().espn, "league", down)
    r = client.get("/api/leagues", params={"espn": "4242"})
    assert r.status_code == 502 and r.json()["error"] == "ESPN did not answer" and r.json()["code"] == "provider_down"


def test_waiver_words_for_espn_and_yahoo():
    from league_lab_api import decisions as D
    for p, w in (("espn", "ESPN"), ("yahoo", "Yahoo")):
        out = D.waiver_deadline(None, platform=p, season=2026, week=4)
        assert out["words"].startswith(f"Claims run on {w}'s schedule for this league: see {w} for the time")
        assert out["kind"] is None and out["source"] == f"{w} league"


# ------------------------------------------------------------------ the real adapters (IK-1's / IK-2's fixtures)
@pytest.fixture
def real(monkeypatch):
    """IK-1's ESPN fixture leagues (``fixtures/espn_leagues``: 4242 public, 5150 private) and IK-2's Yahoo fixture league
    (``fixtures/yahoo``: 461.l.4242, 12 teams, superflex) through IK-3's wiring; synthetic, from the documented shapes."""
    from pathlib import Path

    from league_lab import player_ids as PI
    fx = Path(__file__).with_name("fixtures")
    monkeypatch.delenv(P.STUBS_ENV, raising=False)
    monkeypatch.setenv("LEAGUE_LAB_ESPN_LEAGUE_FIXTURES", str(fx / "espn_leagues"))
    monkeypatch.setenv("LEAGUE_LAB_ESPN_SEASON", "2026")
    monkeypatch.setenv("LEAGUE_LAB_YAHOO_FIXTURES", str(fx / "yahoo"))
    monkeypatch.setenv(PI.CSV_ENV, str(fx / "ff" / "db_playerids.csv"))
    for k in ("LEAGUE_LAB_ESPN_PRIVATE", "LEAGUE_LAB_YAHOO_CLIENT_ID", "LEAGUE_LAB_YAHOO_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    PI.reset()
    A._default = None
    yield
    A._default = None
    PI.reset()


def connect_yahoo(client) -> None:
    """IK-2's Connect with Yahoo in fixture mode: /api/yahoo/connect → the callback (code "fixture") → ll_yahoo."""
    r = client.get("/api/yahoo/connect", follow_redirects=True)
    assert r.status_code == 200 and client.cookies.get("ll_yahoo"), r.status_code


def test_real_router_builds_ik1_and_ik2_adapters(real):
    r = A.sleeper()
    assert type(r.espn).__name__ == "ESPNLeagues" and type(r.yahoo).__name__ == "YahooLeagues"
    assert r.league(ESPN)["platform"] == "espn" and r.league(ESPN)["name"] == "Synthetic Public League"
    assert len(r.rosters(ESPN)) == 10


def test_real_espn_setup(real, client):
    d = client.get("/api/leagues", params={"espn": "4242"}).json()
    assert d["league"]["name"] == "Synthetic Public League" and len(d["teams"]) == 10 and d["roster_id"] is None
    assert {u["espn_id"] for u in d["unmapped"]} == {"99990001", "99990002"}     # IK-1's two unmatched players
    assert d["mapped"] == d["players"] - 2 and d["card"]["lineup"]["text"].startswith("Your lineup:")
    # ESPN team ids skip 10 (1–9, 11): team 11 is the tenth roster
    t = client.get("/api/leagues", params={"espn": "fantasy.espn.com/football/team?leagueId=4242&teamId=11"}).json()
    assert t["roster_id"] == 10
    d = _err(client.get("/api/leagues", params={"espn": "5150"}), 404, "espn_league_private")
    assert d["error"].startswith("ESPN league 5150 is private")
    _err(client.get("/api/leagues", params={"espn": "777"}), 404, "espn_league_unknown")


def test_real_yahoo_setup_needs_the_connection(real, client):
    d = _err(client.get("/api/leagues", params={"yahoo": "461.l.4242"}), 404, "yahoo_sign_in_required")
    assert "Connect" in d["fix"]
    me = client.get("/api/leagues", params={"yahoo_me": "1"}).json()
    assert me["configured"] is True and me["connected"] is False                  # fixture mode counts as set up
    connect_yahoo(client)                               # IK-2's connect in fixture mode: the sealed ll_yahoo cookie
    d = client.get("/api/leagues", params={"yahoo": "https://football.fantasysports.yahoo.com/f1/4242/3"}).json()
    assert d["league"]["league_id"] == YAHOO and d["roster_id"] == 3 and len(d["teams"]) == 12
    me = client.get("/api/leagues", params={"yahoo_me": "1"}).json()
    assert me["connected"] is True and [(x["league_id"], x["roster_id"]) for x in me["leagues"]] == [(YAHOO, 3)]
    assert me["leagues"][0]["card"] and me["leagues"][0]["team_name"]


def test_real_yahoo_without_keys_is_coming_soon(real, client, monkeypatch):
    monkeypatch.delenv("LEAGUE_LAB_YAHOO_FIXTURES")
    A._default = None
    me = client.get("/api/leagues", params={"yahoo_me": "1"}).json()
    assert me["configured"] is False and me["note"] == ondemand.YAHOO_NOTES["not_configured"]
    d = _err(client.get("/api/leagues", params={"yahoo": "461.l.4242"}), 404, "yahoo_not_configured")
    assert d["error"] == "Yahoo sign-in is not set up on this server yet."
    assert client.get("/api/providers").json()["yahoo_configured"] is False


@needs_db
@pytest.mark.parametrize("key,team,cookie", [(ESPN, 1, None), (YAHOO, 3, "fixture")])
def test_real_my_week_and_screens(real, client, key, team, cookie):
    if cookie:
        connect_yahoo(client)
    r = client.get("/api/my-week", params={"league": key, "team": team})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["platform"] == P.provider_of(key) and d["lineup"] and d["edit_link"]["platform"] == P.provider_short(key)
    for path, params in (("/api/team", {"league": key, "team": team}), ("/api/waivers", {"league": key, "team": team}),
                         ("/api/trades/lists", {"league": key, "team": team}), ("/api/league", {"league": key, "team": team})):
        rr = client.get(path, params=params)
        assert rr.status_code == 200, (path, rr.text[:300])
