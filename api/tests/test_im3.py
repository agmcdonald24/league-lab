"""IM-3 (Wave I-M): the open door — the gate switch, the rate limiter, the Guard (CSRF, body sizes, headers), SSRF,
the reference league keys (docs/SECURITY_PUBLIC.md)."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
import tracemalloc
import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient

from league_lab_api import auth, ratelimit, refleague, security
from league_lab_api.main import app

from .conftest import DYNASTY, needs_db

STAR = "00-0036963"          # Amon-Ra St. Brown (WR, DET): on the database's 2026 board
OTHER = "00-0036322"


# ====================================================================================== 1. the gate as a switch
@pytest.fixture
def api(monkeypatch):
    for k in ("LEAGUE_LAB_APP_PASSWORD", "LEAGUE_LAB_API_SECRET", "LEAGUE_LAB_GATE"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(app) as c:
        yield c


def _gate_state(c) -> tuple[dict, int]:
    return c.get("/api/session").json(), c.get("/api/providers").status_code


def test_gate_default_follows_the_password(api, monkeypatch):
    assert auth.gate() == "open" and _gate_state(api) == ({"gate": False, "signed_in": True}, 200)
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "correct horse")
    assert auth.gate() == "password" and _gate_state(api) == ({"gate": True, "signed_in": False}, 401)
    assert api.get("/api/providers").json()["detail"].startswith("Private beta")


def test_gate_open_ignores_the_password(api, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "correct horse")
    monkeypatch.setenv("LEAGUE_LAB_GATE", "open")
    assert _gate_state(api) == ({"gate": False, "signed_in": True}, 200)
    assert api.post("/api/login", json={"password": "correct horse"}).json() == {"ok": True, "token": None}
    assert "ll_auth" not in api.cookies
    monkeypatch.setenv("LEAGUE_LAB_GATE", " OPEN ")                          # case and spaces
    assert auth.gate() == "open"


def test_gate_password_brings_it_back(api, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "correct horse")
    monkeypatch.setenv("LEAGUE_LAB_GATE", "password")
    assert _gate_state(api) == ({"gate": True, "signed_in": False}, 401)
    r = api.post("/api/login", json={"password": "correct horse"})
    assert r.status_code == 200 and r.json()["ok"] and "ll_auth=" in r.headers["set-cookie"]
    assert api.get("/api/providers").status_code == 200                       # the cookie, as before
    monkeypatch.setenv("LEAGUE_LAB_GATE", "pasword")                          # a typo: the old rule (password set)
    assert auth.gate() == "password"


def test_gate_password_without_a_password_stays_shut(api, monkeypatch):
    """Asked for a password gate with no password: nobody gets in — not with a token signed by the public fallback key."""
    monkeypatch.setenv("LEAGUE_LAB_GATE", "password")
    assert _gate_state(api) == ({"gate": True, "signed_in": False}, 401)
    assert api.post("/api/login", json={"password": ""}).status_code == 401
    forged = auth.issue()                                                     # signed with sha256("league-lab-api|")
    assert api.get("/api/providers", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_token_with_non_ascii_parts_is_refused_not_a_500(api, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "pw")
    for bad in ["²³.abc", "123.é", f"{auth.issue().split('.')[0]}.éé"]:
        assert auth.valid(bad) is False


# ====================================================================================== 2. the rate limiter
class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def limited(api, monkeypatch):
    """The limiter on with small numbers and a clock the test moves; off again afterwards (the suite runs it off)."""
    monkeypatch.delenv("RENDER", raising=False)
    clock = Clock()
    lim = ratelimit.reset(ratelimit.Limiter({"read": (60, 5), "heavy": (6, 2), "write": (30, 3)}, clock=clock))
    yield api, lim, clock
    ratelimit.reset()


def test_buckets_by_route():
    b = ratelimit.bucket_for
    assert b("GET", "/api/health") is None and b("GET", "/") is None and b("GET", "/assets/x.js") is None
    assert b("GET", "/api/players", "league=1&position=WR") == "read"
    assert b("GET", "/api/leagues") == "read" and b("GET", "/api/leagues", "username=andrew") == "heavy"
    for q in ("mfl=70587", "sleeper=1", "espn=4242", "yahoo=461.l.1", "yahoo_me=1", "mfl_search=addicts"):
        assert b("GET", "/api/leagues", q) == "heavy", q
    for p in ("/api/my-week", "/api/waivers", "/api/trades/partners", "/api/team", "/api/league", "/api/league/week-odds",
              "/api/league/scoring-check", "/api/leagues/123/rosters", "/api/yahoo/connect", "/api/dfs/slate"):
        assert b("GET", p) == "heavy", p
    assert b("POST", "/api/trades/evaluate") == "heavy" and b("POST", "/api/dfs/lineups") == "heavy"
    assert b("GET", "/api/ros", "league=1&view=lineup&team=2") == "heavy" and b("GET", "/api/ros", "league=1") == "read"
    for m, p in (("POST", "/api/usage"), ("POST", "/api/login"), ("PUT", "/api/account/leagues"),
                 ("DELETE", "/api/account"), ("POST", "/api/espn/connect")):
        assert b(m, p) == "write", (m, p)


def test_a_burst_is_refused_then_the_bucket_refills(limited):
    c, lim, clock = limited
    codes = [c.get("/api/ratelimit/none").status_code for _ in range(5)]     # 5 at once (burst), the 6th refused
    assert codes == [404] * 5
    r = c.get("/api/ratelimit/none")
    assert r.status_code == 429
    body = r.json()
    assert body["code"] == "rate_limited" and body["retry_after_s"] == 1 and body["bucket"] == "read"
    assert body["error"] == "Too many requests from this connection. Try again in a second."
    assert r.headers["retry-after"] == "1" and r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"                  # the Guard's headers on a 429 too
    clock.t += 1.0                                                            # 60 a minute: one token a second
    assert c.get("/api/ratelimit/none").status_code == 404
    assert c.get("/api/ratelimit/none").status_code == 429
    clock.t += 60
    assert [c.get("/api/ratelimit/none").status_code for _ in range(5)] == [404] * 5
    # the health check and the web app's files are never limited
    assert all(c.get("/api/health").status_code == 200 for _ in range(20))


def test_retry_after_counts_whole_seconds(limited):
    c, lim, clock = limited
    for _ in range(2):
        assert c.get("/api/waivers?league=1").status_code != 429                # heavy: 6 a minute, 2 at once
    r = c.get("/api/waivers?league=1")
    assert r.status_code == 429 and r.json()["retry_after_s"] == 10 and r.headers["retry-after"] == "10"
    assert r.json()["error"] == "Too many requests from this connection. Try again in 10 seconds."
    assert c.get("/api/ratelimit/none").status_code == 404                   # read is its own bucket


def test_a_spoofed_forwarded_for_buys_nothing(limited, monkeypatch):
    c, lim, clock = limited
    # off Render: the socket's peer, no header read at all
    for i in range(5):
        assert c.get("/api/x", headers={"X-Forwarded-For": f"198.51.100.{i}", "CF-Connecting-IP": f"203.0.113.{i}"}
                     ).status_code == 404
    assert c.get("/api/x", headers={"X-Forwarded-For": "198.51.100.99"}).status_code == 429
    # on Render: CF-Connecting-IP (Cloudflare writes it) — a new X-Forwarded-For each time changes nothing
    monkeypatch.setenv("RENDER", "true")
    ratelimit.reset(ratelimit.Limiter({"read": (60, 5)}, clock=clock))
    for i in range(5):
        assert c.get("/api/x", headers={"CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": f"10.9.{i}.1"}
                     ).status_code == 404
    assert c.get("/api/x", headers={"CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": "1.1.1.1"}).status_code == 429
    assert c.get("/api/x", headers={"CF-Connecting-IP": "198.51.100.8"}).status_code == 404       # another client
    # on Render without the header: the LAST X-Forwarded-For entry (the proxy's); the client writes only the left
    for i in range(5):
        assert c.get("/api/x", headers={"X-Forwarded-For": f"203.0.113.{i}, 192.0.2.44"}).status_code == 404
    assert c.get("/api/x", headers={"X-Forwarded-For": "203.0.113.200, 192.0.2.44"}).status_code == 429
    # IPv6: a /64 is one client (a subscriber's block: 2^64 addresses would otherwise be 2^64 buckets)
    ratelimit.reset(ratelimit.Limiter({"read": (60, 2)}, clock=clock))
    assert c.get("/api/x", headers={"CF-Connecting-IP": "2001:db8:1:2::1"}).status_code == 404
    assert c.get("/api/x", headers={"CF-Connecting-IP": "2001:db8:1:2:ffff::9"}).status_code == 404
    assert c.get("/api/x", headers={"CF-Connecting-IP": "2001:db8:1:2:abcd::5"}).status_code == 429
    assert c.get("/api/x", headers={"CF-Connecting-IP": "2001:db8:1:3::1"}).status_code == 404


def test_the_probe_names_the_source_never_the_address(limited, monkeypatch):
    c, lim, clock = limited
    monkeypatch.setenv("RENDER", "true")
    d = c.get("/api/ratelimit", headers={"CF-Connecting-IP": ratelimit.TEST_ADDRESS}).json()
    assert d["keyed_by"] == "cf-connecting-ip" and d["test_address_used"] is True and d["resolved"] == "edge"
    assert ratelimit.TEST_ADDRESS not in str(d) and re.fullmatch(r"[0-9a-f]{4}", d["bucket_tag"])
    d = c.get("/api/ratelimit", headers={"X-Forwarded-For": f"{ratelimit.TEST_ADDRESS}, 192.0.2.9"}).json()
    assert d["keyed_by"] == "x-forwarded-for" and d["test_address_used"] is False


def test_switch_off(api, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_RATE_LIMIT", "off")
    monkeypatch.setenv("LEAGUE_LAB_RATE_READ", "60,1")
    lim = ratelimit.reset()
    try:
        assert lim.enabled is False and lim.buckets["read"].burst == 1
        assert all(api.get("/api/x").status_code == 404 for _ in range(5))
    finally:
        ratelimit.reset()


def test_numbers_by_env(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_RATE_LIMIT", "on")
    monkeypatch.setenv("LEAGUE_LAB_RATE_HEAVY", "10/4")
    monkeypatch.setenv("LEAGUE_LAB_RATE_WRITE", "nonsense")
    monkeypatch.setenv("LEAGUE_LAB_RATE_CLIENTS", "777")
    lim = ratelimit.from_env()
    assert lim.enabled and (lim.buckets["heavy"].per_minute, lim.buckets["heavy"].burst) == (10, 4)
    assert (lim.buckets["write"].per_minute, lim.buckets["write"].burst) == ratelimit.DEFAULTS["write"]
    assert lim.buckets["read"].max_clients == 777
    assert ratelimit.DEFAULTS == {"read": (300.0, 150.0), "heavy": (20.0, 20.0), "write": (60.0, 30.0)}


def test_memory_is_bounded():
    """5,000 clients in each of the three buckets: the bound holds and the memory stays a few hundred KB a bucket."""
    clock = Clock()
    lim = ratelimit.Limiter(clock=clock)
    tracemalloc.start()
    before = tracemalloc.take_snapshot()
    for n in range(20_000):                                   # 20,000 distinct addresses, each one request in debt
        ip = ipaddress.IPv4Address(0x0A000000 + n)
        for b in ("read", "heavy", "write"):
            lim.check(b, ip)
        clock.t += 0.000001                     # all in debt at once: the LRU has to evict
    after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    size = sum(s.size_diff for s in after.compare_to(before, "filename"))
    held = {n: b.clients() for n, b in lim.buckets.items()}
    assert all(v <= ratelimit.MAX_CLIENTS for v in held.values()), held
    assert all(b.evicted > 0 for b in lim.buckets.values())
    print(f"\nlimiter memory, 3 buckets x {held}: {size / 1024:.0f} KB")
    assert size < 1.6 * 1024 * 1024
    # a client whose bucket is full again is forgotten at no cost: after a quiet minute the sweep empties the table
    clock.t += 3600
    for b in lim.buckets.values():
        b._sweep(clock.t)
    assert all(b.clients() == 0 for b in lim.buckets.values())


def test_status_reports_the_limiter(limited):
    c, lim, clock = limited
    c.get("/api/x")
    info = ratelimit.limiter().info()
    assert info["enabled"] and info["buckets"]["read"]["clients"] == 1 and info["keyed_by"] == {"peer": 1}


# ====================================================================================== 3. the Guard
def test_cross_site_writes_are_refused(api):
    evil = {"Origin": "https://evil.example"}
    for method, path, body in (("post", "/api/usage", None), ("post", "/api/trades/evaluate", {"league": "1", "team": 1}),
                               ("post", "/api/espn/connect", {}), ("post", "/api/logout", None),
                               ("put", "/api/account/leagues", {"leagues": []}), ("delete", "/api/account", None),
                               ("post", "/api/yahoo/disconnect", None), ("post", "/api/login", {"password": "x"})):
        r = getattr(api, method)(path, headers=evil, **({"json": body} if body is not None else {}))
        assert r.status_code == 403 and r.json()["code"] == "cross_site", (method, path, r.text)
    assert api.post("/api/usage", headers={"Origin": "null"}).status_code == 403
    assert api.post("/api/usage", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    # the same site: allowed (the request's own host, the public hosts, or no browser header at all)
    assert api.post("/api/usage", headers={"Origin": "http://testserver"}).status_code == 204
    assert api.post("/api/usage", headers={"Origin": "https://isuckatfantasy.io",
                                           "Sec-Fetch-Site": "same-origin"}).status_code == 204
    assert api.post("/api/usage", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 204
    assert api.post("/api/usage").status_code == 204
    # a look-alike host is another host
    for o in ("https://isuckatfantasy.io.evil.example", "https://evil-isuckatfantasy.io", "https://testserver.evil"):
        assert api.post("/api/usage", headers={"Origin": o}).status_code == 403, o
    # reads are never refused for their origin (a link from anywhere opens the app)
    assert api.get("/api/session", headers=evil).status_code == 200


def test_allowed_hosts_by_env(api, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_ALLOWED_HOSTS", "app.example")
    assert api.post("/api/usage", headers={"Origin": "https://app.example"}).status_code == 204
    assert api.post("/api/usage", headers={"Origin": "https://isuckatfantasy.io"}).status_code == 403


def test_request_size_limits(api, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_MAX_BODY_KB", "4")
    big = b"x" * 5000
    r = api.post("/api/usage", content=big, headers={"Content-Type": "text/plain"})
    assert r.status_code == 413 and r.json()["code"] == "too_large"
    assert api.post("/api/usage", content=b"x" * 3000).status_code == 204

    def chunks():                                  # no Content-Length: read up to the bound, refused past it
        for _ in range(10):
            yield b"y" * 1000
    r = api.post("/api/usage", content=chunks())
    assert r.status_code == 413
    def small():
        yield b'{"screen": "week"}'
    assert api.post("/api/usage", content=small()).status_code == 204
    # the DFS upload route has its own, larger bound (IM-5's file: 1 MB): past the Guard (404 here: no route yet)
    assert api.post("/api/dfs/slate", content=b"z" * 20000).status_code in (404, 405, 400, 422, 200)
    assert security.body_limit("/api/dfs/slate") == 2048 * 1024


def test_response_headers(api):
    r = api.get("/api/health")
    h = r.headers
    assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert h["x-frame-options"] == "DENY" and "camera=()" in h["permissions-policy"]
    csp = h["content-security-policy"]
    for part in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'",
                 "https://*.googletagmanager.com", "https://*.google-analytics.com"):
        assert part in csp, part
    assert "strict-transport-security" not in h
    assert "max-age" in api.get("/api/health", headers={"X-Forwarded-Proto": "https"}).headers["strict-transport-security"]


def test_csp_allows_the_inline_prefetch_by_its_hash(tmp_path):
    index = tmp_path / "index.html"
    index.write_text('<html><head><script>var a = 1;</script><script type="module" src="/x.js"></script></head></html>')
    want = "'sha256-" + base64.b64encode(hashlib.sha256(b"var a = 1;").digest()).decode() + "'"
    assert security.inline_hashes(index) == [want]


def test_provider_errors_keep_their_cause_to_the_log(api, monkeypatch):
    from league_lab import anyleague as A

    from league_lab_api import ondemand

    def down(*_a, **_k):
        raise ondemand.SleeperDown("MyFantasyLeague https://www45.myfantasyleague.com/2026/export?TYPE=x: [Errno -2]")
    monkeypatch.setattr(ondemand, "mfl_league", down)
    r = api.get("/api/leagues", params={"mfl": "70587"})
    assert r.status_code == 502 and "cause" not in r.json() and "Errno" not in r.text
    assert A is not None


# ====================================================================================== 3b. SSRF
ALLOWED_HOSTS = {"api.sleeper.app", "api.myfantasyleague.com", "lm-api-reads.fantasy.espn.com", "site.api.espn.com",
                 "fantasysports.yahooapis.com", "api.login.yahoo.com", "raw.githubusercontent.com"}


@pytest.fixture
def outbound(api, monkeypatch):
    """No fixtures: every outbound request is recorded (host only) and refused before it leaves."""
    from league_lab import anyleague as A
    for k in ("LEAGUE_LAB_SLEEPER_FIXTURES", "LEAGUE_LAB_MFL_FIXTURES", "LEAGUE_LAB_ESPN_LEAGUE_FIXTURES",
              "LEAGUE_LAB_YAHOO_FIXTURES", "LEAGUE_LAB_SLEEPER_API", "LEAGUE_LAB_ESPN_LEAGUE_API"):
        monkeypatch.delenv(k, raising=False)
    seen: list[str] = []

    def record(self, fullurl, data=None, timeout=None):  # noqa: ANN001 - urllib's signature
        url = fullurl.full_url if hasattr(fullurl, "full_url") else str(fullurl)
        seen.append(urllib.request.urlparse(url).hostname or "")
        raise urllib.error.URLError("refused by the test")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", record)
    A._default = None
    yield api, seen
    A._default = None


HOSTILE = ["http://169.254.169.254/latest/meta-data/", "https://127.0.0.1:5432/leagues/123", "http://localhost/2026/home/70587",
           "https://www45.myfantasyleague.com.evil.example/2026/home/70587", "https://evil.example/?u=myfantasyleague.com/2026/home/70587",
           "https://user@evil.example/football/league?leagueId=4242", "https://[::1]/leagues/1389709692405551104",
           "file:///etc/passwd", "gopher://evil.example:70/_x", "https://evil.example/f1/123"]


def test_hostile_links_never_reach_another_host(outbound):
    c, seen = outbound
    for link in HOSTILE:
        for param in ("mfl", "mfl_search", "sleeper", "espn", "yahoo", "username"):
            r = c.get("/api/leagues", params={param: link})
            assert r.status_code != 500, (param, link, r.status_code, r.text[:200])     # 502: the platform's host refused
    assert seen, "some links are valid ids for their platform: they must have tried the platform's own host"
    assert set(seen) <= ALLOWED_HOSTS, sorted(set(seen) - ALLOWED_HOSTS)


def test_mfl_remembers_only_its_own_hosts():
    from league_lab import mfl_client as M
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        if "TYPE=league" in url:          # a redirect that ended elsewhere: never remembered
            return "https://evil.example:443/2026/export", '{"league": {"baseURL": "https://10.0.0.1"}}'
        return url, "{}"
    mfl = M.MFL(fetch=fetch) if "fetch" in M.MFL.__init__.__code__.co_varnames else None
    if mfl is None:
        pytest.skip("MFL has no fetch hook")
    mfl.fixtures = None
    try:
        mfl.league("70587")
    except Exception:  # noqa: BLE001 - the answer's shape does not matter here
        pass
    assert "70587" not in mfl.hosts
    try:
        mfl.rosters("70587")
    except Exception:  # noqa: BLE001
        pass
    assert all(urllib.request.urlparse(u).hostname == "api.myfantasyleague.com" for u in calls), calls
    for link in HOSTILE[:5]:
        try:
            lid, *_ = M.parse_link(link)
        except Exception:  # noqa: BLE001 - refused: fine
            continue
        assert re.fullmatch(r"\d{1,8}", lid)


def test_mfl_follows_redirects_only_to_mfl():
    from league_lab import mfl_client as M
    h = M._MFLRedirects()
    req = urllib.request.Request("https://api.myfantasyleague.com/2026/export?TYPE=league&L=1")
    ok = h.redirect_request(req, None, 302, "Found", {}, "https://www45.myfantasyleague.com/2026/export?TYPE=league&L=1")
    assert ok is not None and ok.full_url.startswith("https://www45.myfantasyleague.com/")
    for bad in ("http://www45.myfantasyleague.com/x", "https://169.254.169.254/latest", "https://www45.myfantasyleague.com.evil.example/",
                "https://evil.example/www45.myfantasyleague.com", "https://myfantasyleague.com@evil.example/",
                "https://www45.myfantasyleague.com:8443/x"):
        with pytest.raises(urllib.error.URLError):
            h.redirect_request(req, None, 302, "Found", {}, bad)


def test_sleeper_usernames_of_dots_are_refused():
    from league_lab.sleeper_client import LeagueNotFound, check_username
    for bad in (".", "..", "...", "a/b", "../x"):
        with pytest.raises(LeagueNotFound):
            check_username(bad)
    assert check_username("Andrew.C-1") == "andrew.c-1"


@needs_db
def test_private_espn_league_stays_gated_with_the_door_open(api, monkeypatch):
    """IK-1's access check runs on every route for an ESPN key with LEAGUE_LAB_GATE=open (and a password set)."""
    from league_lab import anyleague as A
    from league_lab import platforms as P
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "pw")
    monkeypatch.setenv("LEAGUE_LAB_GATE", "open")
    monkeypatch.setenv(P.STUBS_ENV, "1")
    monkeypatch.delenv("LEAGUE_LAB_ESPN_PRIVATE", raising=False)
    A._default = None
    try:
        for path, params in (("/api/my-week", {"league": "espn:5150", "team": 1}), ("/api/waivers", {"league": "espn:5150"}),
                             ("/api/players", {"league": "espn:5150"}), ("/api/trends", {"league": "espn:5150"})):
            r = api.get(path, params=params)
            assert r.status_code == 404 and r.json().get("code") == "espn_league_private", (path, r.text[:200])
    finally:
        A._default = None


# ====================================================================================== 4. reference league keys
RESEARCH = [
    ("/api/players", {"position": "WR", "limit": 5}),
    ("/api/players", {"position": "WR", "window": "season", "limit": 5}),
    ("/api/trends", {"limit": 5}),
    ("/api/matchups/defense", {}),
    ("/api/matchups/cb", {"limit": 5}),
    ("/api/compare", {"a": STAR, "b": OTHER}),
    (f"/api/player/{STAR}", {}),
    (f"/api/player/{STAR}/games", {}),
    ("/api/search", {"q": "brown"}),
    ("/api/receivers", {"limit": 5}),
    ("/api/about", {}),
    ("/api/record", {}),
    ("/api/ros", {"limit": 5}),
]
DECISIONS = [
    ("get", "/api/my-week", {"team": 1}), ("get", "/api/waivers", {"team": 1}), ("get", "/api/trades/partners", {"team": 1}),
    ("get", "/api/trades/lists", {"team": 1}), ("get", "/api/team", {"team": 1}), ("get", "/api/league", {}),
    ("get", "/api/ros", {"view": "lineup", "team": 1}), ("get", "/api/league/week-odds", {}),
    ("get", "/api/league/scoring-check", {}), ("get", "/api/events", {"team": 1}),
]


def _keys(o, acc: set) -> set:
    if isinstance(o, dict):
        for k, v in o.items():
            acc.add(k)
            _keys(v, acc)
    elif isinstance(o, list):
        for v in o:
            _keys(v, acc)
    return acc


@needs_db
@pytest.mark.parametrize("path,params", RESEARCH, ids=[p + ("?" + "&".join(f"{k}={v}" for k, v in q.items()) if q else "")
                                                       for p, q in RESEARCH])
def test_research_routes_answer_a_reference_key_without_owners(api, path, params):
    r = api.get(path, params={"league": "ref:half", **params})
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    owners = _keys(d, set()) & refleague.OWNERSHIP
    assert not owners, owners


@needs_db
def test_reference_points_are_in_the_reference_scoring(api):
    rows = {k: api.get("/api/players", params={"league": k, "position": "WR", "limit": 40}).json() for k in refleague.KEYS}
    assert rows["ref:half"]["league_name"] == "No league · Half PPR"
    pts = {k: {p["gsis_id"]: p["points"] for p in v["players"]} for k, v in rows.items()}
    common = set(pts["ref:ppr"]) & set(pts["ref:half"]) & set(pts["ref:std"])
    assert len(common) >= 20
    for g in common:                                   # PPR > Half > Standard for a receiver with catches
        assert pts["ref:ppr"][g] > pts["ref:half"][g] > pts["ref:std"][g], g
    card = api.get(f"/api/player/{STAR}", params={"league": "ref:ppr"}).json()
    assert card.get("player_name") and _keys(card, set()) & {"proj_points", "projection", "why"}
    # the half-PPR key prices exactly as the house reference league (League of Scrubs: half PPR, 4-pt pass TD)
    assert rows["ref:half"].get("expected_points_exact") is True


@needs_db
@pytest.mark.parametrize("method,path,params", DECISIONS, ids=[p for _m, p, _q in DECISIONS])
def test_decision_routes_ask_for_a_league(api, method, path, params):
    r = getattr(api, method)(path, params={"league": "ref:half", **params})
    assert r.status_code == 404 and r.json() == {"error": "Open your league to see this.",
                                                 "detail": "Open your league to see this.", "code": "needs_league"}


def test_decision_posts_and_rosters_ask_for_a_league(api):
    r = api.post("/api/trades/evaluate", json={"league": "ref:std", "team": 1, "give": [], "get": []})
    assert r.status_code == 404 and r.json()["code"] == "needs_league"
    r = api.get("/api/leagues/ref:ppr/rosters")
    assert r.status_code == 404 and r.json()["code"] == "needs_league"


@needs_db
def test_unknown_reference_keys_are_not_found(api):
    for path in ("/api/players", "/api/record", "/api/about"):
        r = api.get(path, params={"league": "ref:bogus"})
        assert r.status_code == 404 and r.json().get("code") != "needs_league", (path, r.text[:200])


@needs_db
def test_house_leagues_still_have_owners(api):
    """A real league keeps its ownership columns (the strip is for reference keys only)."""
    d = api.get("/api/players", params={"league": DYNASTY, "position": "WR", "limit": 30}).json()
    assert "rostered_by_roster_id" in _keys(d, set())


def test_reference_league_shape():
    lg = refleague.league("REF:HALF ")
    assert lg["league_id"] == "ref:half" and lg["scoring_settings"]["rec"] == 0.5
    assert refleague.league("ref:ppr")["scoring_settings"]["rec"] == 1.0
    assert refleague.league("ref:std")["scoring_settings"]["rec"] == 0.0
    assert lg["roster_positions"][:9] == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"]
    from league_lab import platforms as P
    assert P.provider_of("ref:half") == "reference" and P.check_key("Ref:Std") == "ref:std"
    with pytest.raises(P.LeagueNotFound):
        P.check_key("ref:xyz")
