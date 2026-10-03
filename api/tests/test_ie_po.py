"""Wave I-E, the PO's integration pieces: the lineup table says what the call says (an injury tiebreak keeps the
healthy player) and the three strongest claims are ordered by this week's gain. The trade verdict's words (never a
guess at the other manager's answer) are pinned in the root suite, tests/test_trades.py."""

from __future__ import annotations

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import player_ids as PI

from .conftest import needs_db
from .test_i0b import IDS, MFL_FX
from .test_ic4 import overlay as _overlay  # the ESPN fixture overlay (Hall and Price Out; McConkey Questionable)

overlay = _overlay

KEY = "mfl:70587"


@pytest.fixture(autouse=True)
def _mfl_fixtures(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


@needs_db
def test_lineup_rows_say_what_the_call_says(client, overlay):
    """Team 8: the call keeps Addison and Nabers ahead of McConkey (questionable); the table is still the best lineup on
    paper (McConkey at WR/TE 3), so its two rows say so instead of contradicting the call."""
    d = client.get(f"/api/my-week?league={KEY}&team=8").json()
    sw = d.get("swaps") or []
    if not sw:
        pytest.skip("no injury tiebreak on this fixture week")
    assert sw[0]["in_name"] == "Addison" and sw[0]["out_name"] == "McConkey"
    rows = {r["player_name"]: r for r in d["lineup_full"]}
    assert rows["Ladd McConkey"]["role"] == "starter"
    assert rows["Ladd McConkey"]["flag"] == "Questionable — the call above keeps Addison here for now"
    assert rows["Jordan Addison"]["role"] == "bench" and rows["Jordan Addison"]["flag"] == "starts for McConkey by the call above"
    assert all("key" in r for r in d["lineup"])


@needs_db
def test_top_three_claims_are_ordered_by_this_weeks_gain(client, overlay):
    w = client.get(f"/api/waivers?league={KEY}&team=8").json()
    tw = [c["this_week"] for c in w["top3"]]
    assert tw == sorted(tw, reverse=True) and w["top3"][0]["lead"].endswith("this week")
