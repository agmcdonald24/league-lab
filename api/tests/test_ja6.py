"""JA-6 (Wave J-A): the CPU-slot limiter made visible — /api/status `slots`, one log line for a wait over a second or a
"busy" answer — and nothing it answers changed."""

from __future__ import annotations

import asyncio
import logging

from league_lab_api import ratelimit as R

from .conftest import needs_db


def test_a_slot_taken_at_once_counts_in_use_peak_and_its_hold():
    s = R.Slots(2, 1.0)
    assert asyncio.run(s.acquire("/api/trades/partners")) is True
    st = s.status()
    assert st["in_use"] == 1 and st["peak_in_use"] == 1 and st["longest_wait_s"] == 0.0
    s.release("/api/trades/partners", 2.5)
    st = s.status()
    assert st["in_use"] == 0 and st["longest_hold_s"] == 2.5 and st["longest_hold_route"] == "/api/trades/partners"


def test_a_wait_over_a_second_is_one_log_line_in_the_pools_form(caplog):
    s = R.Slots(1, 5.0)

    async def run():
        assert await s.acquire("/api/players")
        async def later():
            await asyncio.sleep(1.15)
            s.release("/api/players", 1.15)
        t = asyncio.create_task(later())
        ok = await s.acquire("/api/trades/partners")
        await t
        return ok
    with caplog.at_level(logging.WARNING, logger=R.log.name):
        assert asyncio.run(run()) is True
    lines = [r.getMessage() for r in caplog.records if "CPU slot" in r.getMessage()]
    assert len(lines) == 1 and lines[0].startswith("waited 1.") and lines[0].endswith(
        "s for a CPU slot (1 of 1 in use) on /api/trades/partners")
    st = s.status()
    assert st["longest_wait_route"] == "/api/trades/partners" and st["longest_wait_s"] >= 1.1 and st["waiting"] == 0


def test_a_busy_answer_is_counted_by_route_and_logged_and_the_answer_is_unchanged(caplog):
    s = R.Slots(1, 0.2)
    with caplog.at_level(logging.WARNING, logger=R.log.name):
        assert asyncio.run(s.acquire("/api/players")) is True
        assert asyncio.run(s.acquire("/api/trades/evaluate")) is False         # still refused, as before
    st = s.status()
    assert st["busy_answers"] == 1 and st["busy_by_route"] == {"/api/trades/evaluate": 1} and st["waiting"] == 0
    msg = [r.getMessage() for r in caplog.records if "busy" in r.getMessage()][0]
    assert msg.startswith("answered busy after 0.2 s waiting for a CPU slot (1 of 1 in use) on /api/trades/evaluate")


def test_busy_by_route_is_bounded():
    s = R.Slots(1, 0.0)
    asyncio.run(s.acquire("/api/x"))
    for i in range(R.BUSY_ROUTES_MAX + 5):
        asyncio.run(s.acquire(f"/api/r{chr(97 + i % 26)}{chr(97 + i // 26)}"))
    st = s.status()
    assert len(st["busy_by_route"]) <= R.BUSY_ROUTES_MAX + 1 and st["busy_by_route"].get("other", 0) >= 5


def test_the_route_is_a_shape_never_an_id_a_team_or_a_key():
    assert R.route_shape("/api/player/00-0039139/games") == "/api/player/*/games"
    assert R.route_shape("/api/player/LV") == "/api/player/*"
    assert R.route_shape("/api/trades/partners") == "/api/trades/partners"
    assert R.route_shape("/api/leagues/1389709692405551104/rosters") == "/api/leagues/*/rosters"


def test_off_is_untouched():
    s = R.Slots(0, 1.0)
    assert asyncio.run(s.acquire("/api/players")) is True and s.status()["in_use"] == 0


@needs_db
def test_status_carries_the_slots_beside_the_pool_with_no_ids(client):
    R._slots = None
    try:
        client.get("/api/players?league=ref:half&position=RB&limit=5")       # a research request takes a slot
        body = client.get("/api/status").json()
    finally:
        R._slots = None
    sl = body["slots"]
    for k in ("size", "in_use", "waiting", "peak_in_use", "longest_wait_s", "longest_wait_route", "busy_answers",
              "busy_by_route", "longest_hold_s", "longest_hold_route"):
        assert k in sl
    assert "pool" in body and sl["longest_hold_route"] == "/api/players" and "ref:half" not in str(sl)
