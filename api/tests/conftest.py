"""Shared fixtures. The data tests run against the database in the repository's `.env` (or
LEAGUE_LAB_APP_DB_URL) with the read-only role, and skip when it cannot be reached."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from league_lab_api import db
from league_lab_api.main import app
from league_lab_api.settings import ROOT, app_dsn

DYNASTY, SCRUBS = "1321941740235550720", "1389709692405551104"
ANDREW = {DYNASTY: 12, SCRUBS: 2}          # the two rosters the plan's acceptance names (dynasty 12, Scrubs 2)
TWIN = Path(__file__).with_name("streamlit_twin.py")


def _db_ok() -> bool:
    try:
        with psycopg.connect(app_dsn(), connect_timeout=5) as conn:
            conn.execute("select 1")
        return True
    except Exception:  # noqa: BLE001
        return False


DB_OK = _db_ok()
needs_db = pytest.mark.skipif(not DB_OK, reason="database not reachable with the app role")


@pytest.fixture
def client(monkeypatch):
    """The API with the gate off (a developer's .env may set a password: tests decide it themselves)."""
    monkeypatch.delenv("LEAGUE_LAB_APP_PASSWORD", raising=False)
    monkeypatch.delenv("LEAGUE_LAB_API_SECRET", raising=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def sql():
    """Run SQL directly (independent of the API's code) with the same read-only role."""
    def run(q: str, params: tuple = ()) -> list[dict]:
        with psycopg.connect(app_dsn(), autocommit=True) as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(q, params)
            return cur.fetchall()
    return run


_twins: dict[tuple, dict] = {}


def twin(*args: str) -> dict:
    """What the Streamlit page shows (tests/streamlit_twin.py run in the repository's environment)."""
    if args in _twins:
        return _twins[args]
    if os.environ.get("LL_SKIP_PARITY") or not shutil.which("uv") or not (ROOT / "pyproject.toml").exists():
        pytest.skip("no repository environment for the Streamlit twin (LL_SKIP_PARITY set, or uv missing)")
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")}
    res = subprocess.run(["uv", "run", "--project", str(ROOT), "python", str(TWIN), *args], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=600)
    line = next((x for x in res.stdout.splitlines() if x.startswith("TWIN-JSON ")), None)
    if res.returncode != 0 or line is None:
        raise AssertionError(f"streamlit twin failed ({res.returncode}): {res.stderr[-2000:]}")
    _twins[args] = json.loads(line[len("TWIN-JSON "):])
    return _twins[args]


SLEEPER_FIXTURES = Path(__file__).with_name("fixtures") / "sleeper"


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    """Every test: an empty query cache, a fresh Sleeper client reading the fixtures (a test never calls Sleeper:
    the database path's opponent reads the matchups call too), the priced-week cache emptied."""
    from league_lab import anyleague as A
    monkeypatch.setenv(A.FIXTURES_ENV, str(SLEEPER_FIXTURES))
    # Wave I-B (PO): MyFantasyLeague answers from the fixtures too — a test never calls MFL (test_ib0 reads mfl:21861)
    monkeypatch.setenv("LEAGUE_LAB_MFL_FIXTURES", str(SLEEPER_FIXTURES.with_name("mfl")))
    # Wave I-0: the availability overlay stays off unless a test turns it on (test_i0a sets LEAGUE_LAB_ESPN_FIXTURES
    # itself); a developer's .env with the ESPN fixtures set would otherwise move the house lineups the parity
    # tests pin (Jefferson Out in the fixture feed)
    monkeypatch.delenv("LEAGUE_LAB_ESPN_FIXTURES", raising=False)
    monkeypatch.delenv("LEAGUE_LAB_AVAILABILITY", raising=False)
    db.clear_cache()
    A._default = None
    A.clear_priced()
    from league_lab_api import availability
    availability.clear_context()                  # IB-0: the roster contexts are kept in process
    yield
    A._default = None
    A.clear_priced()
