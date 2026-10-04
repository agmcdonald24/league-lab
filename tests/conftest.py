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
