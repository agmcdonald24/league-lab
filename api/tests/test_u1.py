"""Wave I-F, U-1: usage tracking — POST /api/usage writes one row in usage.events (its own read-write transaction on
its own connection; the read pool stays read-only), the day's session cookie, the rate limit, LEAGUE_LAB_USAGE=off,
the summary route, nothing about a person in a row, and the sync script's block (docs/HOSTING.md § "Usage").

The database tests apply scripts/hosted_usage.sql themselves (idempotent) with the pipeline role, write with the
API's read-only app role exactly as the server does, and delete their own rows (version "u1test") afterwards."""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from league_lab_api import auth, db, main, usage
from league_lab_api.main import app
from league_lab_api.settings import ROOT

from .conftest import SCRUBS, needs_db

SQL_FILE = ROOT / "scripts" / "hosted_usage.sql"
SYNC = ROOT / "scripts" / "sync_to_hosted.sh"
COLUMNS = ["at", "screen", "league_key", "roster_id", "platform", "version", "session"]
VERSION = "u1test"


def _pipeline_dsn() -> str:
    from league_lab.config import get_settings
    return get_settings().pipeline_dsn()


@pytest.fixture(scope="module")
def usage_table():
    """scripts/hosted_usage.sql applied by the test itself (twice: it is idempotent); the test rows removed after."""
    try:
        with psycopg.connect(_pipeline_dsn(), autocommit=True, connect_timeout=5) as conn:
            conn.execute(SQL_FILE.read_text())
            conn.execute(SQL_FILE.read_text())
    except psycopg.Error as exc:
        pytest.skip(f"cannot apply scripts/hosted_usage.sql with the pipeline role: {exc.__class__.__name__}")
    yield
    with psycopg.connect(_pipeline_dsn(), autocommit=True) as conn:
        conn.execute("delete from usage.events where version = %s", (VERSION,))


@pytest.fixture
def api(monkeypatch):
    """The API, gate off, usage on, a fresh rate limit, the version stamped "u1test" (the rows the test removes)."""
    monkeypatch.delenv("LEAGUE_LAB_APP_PASSWORD", raising=False)
    monkeypatch.delenv("LEAGUE_LAB_API_SECRET", raising=False)
    monkeypatch.delenv(usage.ENV, raising=False)
    monkeypatch.setattr(main, "_version", lambda: VERSION)
    usage.reset()
    t = [1000.0]
    monkeypatch.setattr(usage, "clock", lambda: t[0])
    with TestClient(app) as c:
        c.tick = lambda s: t.__setitem__(0, t[0] + s)      # advance the rate limit's clock
        yield c
    usage.reset()


def rows(session: str | None = None) -> list[dict]:
    assert usage.flush(), "the writer thread did not drain its queue"
    with psycopg.connect(_pipeline_dsn(), autocommit=True) as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        if session is None:
            cur.execute("select * from usage.events where version = %s order by at", (VERSION,))
        else:
            cur.execute("select * from usage.events where version = %s and session = %s order by at", (VERSION, session))
        return cur.fetchall()


def post(c: TestClient, body: dict | None = None, session: str | None = None, **kw):
    """One POST as a browser makes it: the day's cookie when it has one (the client's jar is reset each time)."""
    c.cookies.clear()
    if session is not None:
        c.cookies.set(usage.COOKIE, session)
    return c.post("/api/usage", json=body, **kw) if "content" not in kw else c.post("/api/usage", **kw)


def view(c: TestClient, session: str | None = None, **body) -> tuple[int, str | None]:
    r = post(c, body, session)
    return r.status_code, r.cookies.get(usage.COOKIE) or session


# ---------------------------------------------------------------- the table and the write path
@needs_db
def test_a_post_writes_one_row(usage_table, api):
    before = len(rows())
    r = post(api, {"screen": "waivers", "league": SCRUBS, "roster_id": 6})
    assert r.status_code == 204 and r.content == b""
    session = r.cookies.get(usage.COOKIE)
    got = rows(session)
    assert len(got) == 1 and len(rows()) == before + 1
    row = got[0]
    assert list(row) == COLUMNS
    assert {k: row[k] for k in COLUMNS[1:]} == {"screen": "waivers", "league_key": SCRUBS, "roster_id": 6,
                                                "platform": "sleeper", "version": VERSION, "session": session}
    assert abs(datetime.now(UTC) - row["at"]) < timedelta(minutes=1)
    # an MFL league: the platform from the key; text/plain (navigator.sendBeacon) is read the same
    api.tick(1.5)
    r = post(api, session=session, content=b'{"screen":"trades","league":"MFL:70587","roster_id":"8"}',
             headers={"content-type": "text/plain;charset=UTF-8"})
    assert r.status_code == 204
    second = rows(session)[-1]
    assert (second["screen"], second["league_key"], second["roster_id"], second["platform"]) == ("trades", "mfl:70587", 8, "mfl")


@needs_db
def test_the_insert_runs_outside_the_read_pool(usage_table, api):
    """The role stays read-only by default: a plain INSERT fails; the read pool's transactions stay read-only after a
    write; the write connection is not one of the pool's."""
    with psycopg.connect(main._app_dsn(), autocommit=True) as conn:
        assert conn.execute("show default_transaction_read_only").fetchone()[0] == "on"
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("insert into usage.events (screen) values ('week')")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):     # insert + select only: no delete, no update
            with conn.transaction():
                conn.execute("set transaction read write")
                conn.execute("delete from usage.events where false")
    assert view(api, screen="week", league=SCRUBS, roster_id=2)[0] == 204
    assert db.fresh("show transaction_read_only").iloc[0, 0] == "on"
    with db.pool().connection() as pooled:
        assert pooled is not db._writer
        assert pooled.execute("show transaction_read_only").fetchone()[0] == "on"


def test_a_failed_insert_never_fails_the_page(api, monkeypatch):
    def boom(*_a, **_k):
        raise psycopg.OperationalError("the database is asleep")
    monkeypatch.setattr(db, "write_one", boom)
    assert view(api, screen="week", league=SCRUBS, roster_id=2)[0] == 204
    assert usage.flush()
    assert usage.stats["failed"] == 1 and usage.stats["written"] == 0


def test_a_slow_database_never_holds_a_request(api, monkeypatch):
    """The insert runs on the writer thread: a database that takes 2 s per insert does not slow the 204, and a full
    queue drops the row (counted) instead of waiting."""
    import queue
    import threading
    import time
    gate = threading.Event()
    monkeypatch.setattr(db, "write_one", lambda *_a, **_k: gate.wait(2))
    t0 = time.monotonic()
    for i in range(3):
        api.tick(1.0)
        assert view(api, screen="week", league=SCRUBS, roster_id=i)[0] == 204
    assert time.monotonic() - t0 < 1.5
    gate.set()
    assert usage.flush() and usage.stats["written"] == 3
    monkeypatch.setattr(usage, "_queue", queue.Queue(maxsize=1))        # a full queue (the writer is elsewhere)
    assert usage.submit({"screen": "week"}) is True and usage.submit({"screen": "week"}) is False
    assert usage.stats["dropped"] == 1


def test_the_writer_reconnects_once(monkeypatch):
    """A connection Neon closed while idle: the insert is retried once on a new connection."""
    calls = []

    class Conn:
        closed = broken = False

        def __init__(self, fail):
            self.fail = fail

        def transaction(self):
            import contextlib
            return contextlib.nullcontext()

        def execute(self, sql, params=None):
            calls.append(sql)
            if self.fail and sql.startswith("insert"):
                raise psycopg.OperationalError("server closed the connection unexpectedly")

        def close(self):
            self.closed = True

    made = iter([Conn(True), Conn(False)])
    monkeypatch.setattr(db, "_writer", None)
    monkeypatch.setattr(db.psycopg, "connect", lambda *a, **k: next(made))
    db.write_one("insert into usage.events (screen) values (%s)", ("week",))
    assert calls == ["set transaction read write", "insert into usage.events (screen) values (%s)"] * 2
    monkeypatch.setattr(db, "_writer", None)


# ---------------------------------------------------------------- the cookie
@needs_db
def test_the_session_cookie_lasts_the_day(usage_table, api):
    r = post(api, {"screen": "week", "league": SCRUBS, "roster_id": 2}, headers={"x-forwarded-proto": "https"})
    cookie = r.headers["set-cookie"]
    session = r.cookies.get(usage.COOKIE)
    assert re.fullmatch(r"[0-9a-f]{32}", session)
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/api/usage" in cookie and "Secure" in cookie
    max_age = int(re.search(r"Max-Age=(\d+)", cookie).group(1))
    assert abs(max_age - usage.seconds_left_today()) <= 5 and 60 <= max_age <= 25 * 3600
    # the browser sends it back: the same session, no new cookie
    api.tick(2)
    r2 = post(api, {"screen": "trades", "league": SCRUBS, "roster_id": 2}, session)
    assert "set-cookie" not in r2.headers
    assert [x["screen"] for x in rows(session)] == ["week", "trades"]
    # a cookie we did not mint is replaced
    api.tick(2)
    r3 = post(api, {"screen": "week"}, "andrew")
    assert r3.cookies.get(usage.COOKIE) not in (None, "andrew", session)


def test_midnight_in_new_york():
    ny = usage.NY
    assert usage.seconds_left_today(datetime(2026, 10, 3, 23, 0, tzinfo=ny)) == 3600
    assert usage.seconds_left_today(datetime(2026, 10, 3, 23, 59, 30, tzinfo=ny)) == 60          # at least a minute
    assert usage.seconds_left_today(datetime(2026, 10, 4, 3, 0, tzinfo=UTC)) == 3600              # 23:00 EDT


# ---------------------------------------------------------------- the rate limit
@needs_db
def test_one_row_a_second_per_session_with_a_burst_of_five(usage_table, api):
    """Five quick screens are five views (tapping through tabs); the sixth inside the same second is dropped; the
    bucket refills one a second."""
    _, session = view(api, screen="week", league=SCRUBS, roster_id=2)
    for screen in ("waivers", "trades", "team", "league", "players"):
        api.tick(0.1)
        assert post(api, {"screen": screen}, session).status_code == 204
    assert [x["screen"] for x in rows(session)] == ["week", "waivers", "trades", "team", "league"]
    assert usage.stats["limited"] == 1
    api.tick(0.5)                                                  # 1.0 s after the first: one token back
    assert post(api, {"screen": "compare"}, session).status_code == 204
    assert post(api, {"screen": "about"}, session).status_code == 204
    assert [x["screen"] for x in rows(session)][-1] == "compare" and usage.stats["limited"] == 2
    api.tick(10)                                                   # a quiet session is back to five
    for screen in ("week", "waivers", "trades", "team", "league"):
        assert post(api, {"screen": screen}, session).status_code == 204
    assert len(rows(session)) == 11


def test_all_sessions_together_are_capped(monkeypatch):
    usage.reset()
    monkeypatch.setattr(usage, "clock", lambda: 5000.25)
    allowed = [usage.allow(usage.new_session()) for _ in range(usage.GLOBAL_PER_S + 5)]
    assert allowed.count(True) == usage.GLOBAL_PER_S and usage.stats["limited"] == 5
    monkeypatch.setattr(usage, "clock", lambda: 5001.25)
    assert usage.allow(usage.new_session())
    usage.reset()


# ---------------------------------------------------------------- the off switch, the gate
@needs_db
@pytest.mark.parametrize("value", ["off", "OFF", "0", "false"])
def test_usage_off_writes_nothing(usage_table, api, monkeypatch, value):
    monkeypatch.setenv(usage.ENV, value)
    before = len(rows())
    r = post(api, {"screen": "week", "league": SCRUBS, "roster_id": 2})
    assert r.status_code == 204 and "set-cookie" not in r.headers
    assert len(rows()) == before and usage.stats == {"written": 0, "failed": 0, "limited": 0, "dropped": 0}
    assert api.get("/api/usage/summary").json()["enabled"] is False


def test_behind_the_beta_gate(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "correct horse")
    monkeypatch.delenv("LEAGUE_LAB_API_SECRET", raising=False)
    written = []
    monkeypatch.setattr(usage, "write", written.append)
    with TestClient(app) as c:
        assert c.post("/api/usage", json={"screen": "week"}).status_code == 401
        assert c.get("/api/usage/summary").status_code == 401
        token = c.post("/api/login", json={"password": "correct horse"}).json()["token"]
        usage.reset()
        assert c.cookies.get(auth.COOKIE) == token                     # the beta cookie: what sendBeacon sends along
        assert c.post("/api/usage", json={"screen": "week"}).status_code == 204
        c.cookies.clear()
        usage.reset()
        assert c.post("/api/usage", json={"screen": "trades"}, headers={"Authorization": f"Bearer {token}"}).status_code == 204
    assert usage.flush()
    assert [r["screen"] for r in written] == ["week", "trades"]
    usage.reset()


# ---------------------------------------------------------------- nothing about a person
@needs_db
def test_no_name_username_or_ip_in_a_row(usage_table, api):
    who = ["Andrew", "andycatmac", "GoodGameBuddy", "203.0.113.7", "Mozilla/5.0 (iPhone)"]
    r = post(api, {"screen": "Andrew", "league": "andycatmac", "roster_id": "GoodGameBuddy", "username": "andycatmac",
                   "name": "Andrew", "ip": "203.0.113.7"},
             headers={"x-forwarded-for": "203.0.113.7", "user-agent": "Mozilla/5.0 (iPhone)"})
    assert r.status_code == 204
    (row,) = rows(r.cookies.get(usage.COOKIE))
    assert {k: row[k] for k in COLUMNS[1:6]} == {"screen": "other", "league_key": None, "roster_id": None,
                                                 "platform": None, "version": VERSION}
    text = " ".join(str(v) for v in row.values())
    assert not any(w.lower() in text.lower() for w in who)
    # the table has no column a person could land in, and refuses free text where a word goes
    with psycopg.connect(_pipeline_dsn(), autocommit=True) as conn:
        cols = [c for (c,) in conn.execute("select column_name from information_schema.columns where table_schema = "
                                           "'usage' and table_name = 'events' order by ordinal_position")]
        assert cols == COLUMNS
        for col, bad in (("screen", "Andrew Smith"), ("league_key", "andycatmac"), ("session", "andrew"),
                         ("platform", "espn"), ("version", "a b")):
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(f"insert into usage.events (screen, {col}) values ('week', %s)"
                             if col != "screen" else "insert into usage.events (screen) values (%s)", (bad,))


def test_the_row_is_allow_listed():
    e = usage.event({"screen": "trade-calc", "league": 1321941740235550720, "roster_id": 12}, version="abc123", session="0" * 32)
    assert (e["screen"], e["league_key"], e["roster_id"], e["platform"], e["version"]) == (
        "trade-calc", "1321941740235550720", 12, "sleeper", "abc123")
    e = usage.event({"screen": "week", "roster_id": 3}, version="dev; drop table", session="x")
    assert (e["league_key"], e["roster_id"], e["platform"], e["version"], e["session"]) == (None, None, None, None, None)
    assert usage.event({"screen": "week", "league": SCRUBS, "roster_id": True}, version=None, session="0" * 32)["roster_id"] is None
    assert usage.parse(b"[1]") == {} and usage.parse(b"\xff") == {} and usage.parse(b"x" * 5000) == {}
    # every screen the web router names is on the allow-list (and nothing else)
    router = (ROOT / "web" / "src" / "lib" / "router.svelte.ts").read_text()
    names = set(re.findall(r'\|\s*"([a-z-]+)"', router.split("export type RouteName")[1].split(";")[0]))
    assert names == usage.SCREENS


# ---------------------------------------------------------------- reading it
@needs_db
def test_the_summary(usage_table, api, sql):
    a = view(api, screen="week", league=SCRUBS, roster_id=6)[1]
    api.tick(1.1)
    view(api, a, screen="waivers", league=SCRUBS, roster_id=6)
    view(api, screen="week", league="mfl:70587", roster_id=8)
    s = api.get("/api/usage/summary?days=7")
    assert s.status_code == 200 and s.headers["cache-control"] == "no-store"
    body = s.json()
    assert body["enabled"] is True and body["ready"] is True and body["days"] == 7
    since = ("at >= ((now() at time zone 'America/New_York')::date - 6)::timestamp at time zone 'America/New_York'")
    want = sql(f"select count(*)::int as views, count(distinct league_key)::int as leagues, "
               f"count(distinct session)::int as sessions from usage.events where {since}")[0]
    assert body["totals"] == want and want["views"] >= 3 and want["sessions"] >= 2 and want["leagues"] >= 2
    today = datetime.now(usage.NY).date().isoformat()
    assert body["by_day"][0]["day"] == today and body["by_day"][0]["views"] >= 3
    per = {(x["day"], x["screen"]): x["views"] for x in body["views_by_screen_day"]}
    assert per[(today, "week")] >= 2 and per[(today, "waivers")] >= 1
    assert sum(x["views"] for x in body["by_screen"]) == want["views"]
    assert sum(x["views"] for x in body["by_day"]) == want["views"]


def test_the_summary_before_the_table_exists(api, monkeypatch):
    def missing(*_a, **_k):
        raise db.DataNotReady('relation "usage.events" does not exist')
    monkeypatch.setattr(db, "fresh", missing)
    body = api.get("/api/usage/summary").json()
    assert body["ready"] is False and "next nightly" in body["words"]


# ---------------------------------------------------------------- the sync script's block (the PO reviews it)
def test_the_sync_keeps_and_creates_the_usage_schema():
    text = SYNC.read_text()
    assert subprocess.run(["bash", "-n", str(SYNC)], capture_output=True).returncode == 0
    drops = re.findall(r"drop schema[^;\"\n]*", text)
    assert drops and not any("usage" in d for d in drops)                   # never dropped
    block = text.split("# ---- U-1")[1].split("# ---- end U-1")[0]
    assert "scripts/hosted_usage.sql" in block and "LEAGUE_LAB_HOSTED_ADMIN_URL" in block
    # its own psql call on the owner connection, never piped into the restore's transaction
    assert re.search(r'psql "\$LEAGUE_LAB_HOSTED_ADMIN_URL"[^\n|]*-f scripts/hosted_usage\.sql; then', block)
    assert text.index("# ---- U-1") > text.index('echo "restored in')       # after the grants
    assert "PASSWORD" not in block                                         # no new secret
    sql = SQL_FILE.read_text().lower()
    assert "grant usage on schema usage to league_lab_app" in sql
    assert "grant select, insert on usage.events to league_lab_app" in sql
    assert "drop " not in sql and "alter role" not in sql                  # never drops, never changes the role


def test_the_web_counts_each_screen_once():
    ts = (ROOT / "web" / "src" / "lib" / "usage.ts").read_text()
    assert "sendBeacon" in ts and "/api/usage" in ts
    app_svelte = (ROOT / "web" / "src" / "App.svelte").read_text()
    assert len(re.findall(r"countView\(", app_svelte)) == 1
    assert Path(ROOT / "web" / "src" / "routes" / "About.svelte").read_text().count("counts screen views") == 1


# ---------------------------------------------------------------- the console's Usage page (app/pages/99_Usage.py)
PAGE_CHECK = """
import sys
sys.path.insert(0, "app")
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app/pages/99_Usage.py", default_timeout=120)
at.run()
assert not at.exception, [e.value for e in at.exception]
print("U1-PAGE", at.markdown[0].value)
print("U1-TABLES", len(at.dataframe), list(at.dataframe[0].value.columns))
"""


@needs_db
def test_the_console_page(usage_table, api):
    import os
    import shutil
    if os.environ.get("LL_SKIP_PARITY") or not shutil.which("uv"):
        pytest.skip("no repository environment for the console (LL_SKIP_PARITY set, or uv missing)")
    view(api, screen="waivers", league=SCRUBS, roster_id=6)
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")}
    res = subprocess.run(["uv", "run", "--project", str(ROOT), "python", "-c", PAGE_CHECK], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr[-2000:]
    line = next(x for x in res.stdout.splitlines() if x.startswith("U1-PAGE "))
    assert re.search(r"\*\*\d+ screen views? in the last 7 days, from \d+ browser-days? in \d+ leagues?", line), line
    assert "waivers" in line
    tables = next(x for x in res.stdout.splitlines() if x.startswith("U1-TABLES "))
    assert tables.startswith("U1-TABLES 2 ['Screen', ") and tables.endswith("'Total']")
