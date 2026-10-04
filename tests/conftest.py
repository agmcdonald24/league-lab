import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


# ---- M4 (Wave I-G): `scoring.ev_pricing()` follows the database's record (the newest build's `pricing`) when
# LEAGUE_LAB_EV_PRICING is unset. A root test never follows it by accident: every test starts with an empty record
# (flat, the pre-I-G default); a test that wants the record installs a reader itself (tests/test_m4.py); the env still
# overrides either way.
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_pricing_record():
    from league_lab import scoring as S
    S.set_record_reader(list)
    yield
    S.set_record_reader(list)
# ---- end M4


# ---- INF-1 (Wave I-I): the suites run at one pinned moment (league_lab.clock). Saturday 2026-10-03 16:00 UTC: week 4's
# Thursday game played, nothing else — so a run on a Sunday afternoon does not see players lock as the games kick off.
# Set in the environment (a subprocess — the Streamlit twin — sees it too); a shell that sets LEAGUE_LAB_NOW wins.
# A test that needs another moment: `with clock.pinned(...)`; one that needs the real time: the `real_clock` fixture.
import os  # noqa: E402

PINNED_NOW = "2026-10-03T16:00:00Z"
os.environ.setdefault("LEAGUE_LAB_NOW", PINNED_NOW)


@pytest.fixture(autouse=True)
def _clock_unpinned_after():
    """A test's `clock.pin(...)` never leaks into the next test."""
    yield
    from league_lab import clock
    clock.unpin()


@pytest.fixture
def real_clock(monkeypatch):
    """The production clock for one test: no pin, no LEAGUE_LAB_NOW."""
    from league_lab import clock
    monkeypatch.delenv(clock.ENV, raising=False)
    clock.unpin()
    yield clock
# ---- end INF-1
