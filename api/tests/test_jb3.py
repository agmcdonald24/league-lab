"""JB-3 (Wave J-B): a request waiting on the database holds no CPU slot (ratelimit.Lease around db.connection)."""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager

import pytest

from league_lab_api import db
from league_lab_api import ratelimit as R

from .conftest import needs_db


@pytest.fixture
def fake_statement(monkeypatch):
    """db.connection's statement part without a database: `hold` seconds 'in the database'."""
    box = {"hold": 0.0, "fail": False}

    @contextmanager
    def stmt(what=""):
        time.sleep(box["hold"])
        if box["fail"]:
            raise RuntimeError("the statement failed")
        yield object()
    monkeypatch.setattr(db, "_statement", stmt)
    return box


def _with_lease(gate, shape, fn):
    lease = R.Lease(gate, shape)
    tok = R.LEASE.set(lease)
    try:
        return fn(lease)
    finally:
        R.LEASE.reset(tok)


def test_the_slot_is_given_back_while_the_statement_runs_and_taken_again_after(fake_statement):
    gate = R.Slots(1, 5.0)
    assert asyncio.run(gate.acquire("/api/team"))
    fake_statement["hold"] = 0.3
    seen = {}

    def other():                                  # a new request during the statement gets the slot at once
        time.sleep(0.1)
        seen["other"] = gate._try()
        time.sleep(0.05)
        gate.release("/api/players", 0.05)
    t = threading.Thread(target=other)
    t.start()

    def run(lease):
        with db.connection("select 1"):
            pass
        return gate.busy, lease.held
    busy, held = _with_lease(gate, "/api/team", run)
    t.join()
    assert seen["other"] is True and busy == 1 and held is True
    assert gate.status()["released_for_statements"] == 1


def test_a_request_coming_back_from_a_statement_goes_ahead_of_a_new_one():
    gate = R.Slots(1, 5.0)
    gate.busy = 1                                  # the slot is someone else's
    gate.returning = 1                             # and a request is coming back from its statement
    assert gate._try() is False                    # a new request waits behind it
    gate.returning = 0
    gate.busy = 0
    assert gate._try() is True


def test_a_request_that_fails_mid_statement_never_leaks_its_slot(fake_statement):
    gate = R.Slots(2, 5.0)
    assert asyncio.run(gate.acquire("/api/team"))
    fake_statement["fail"] = True

    def run(lease):
        with pytest.raises(RuntimeError):
            with db.connection("select 1"):
                pass
        lease.end()                                # the middleware's end of the request
        return gate.busy
    assert _with_lease(gate, "/api/team", run) == 0


def test_a_request_that_ended_while_its_statement_ran_takes_no_slot_after_it(fake_statement):
    gate = R.Slots(2, 5.0)
    assert asyncio.run(gate.acquire("/api/team"))
    fake_statement["hold"] = 0.2

    def run(lease):
        t = threading.Timer(0.05, lease.end)       # the client went away mid-statement
        t.start()
        with db.connection("select 1"):
            pass
        t.join()
        return gate.busy
    assert _with_lease(gate, "/api/team", run) == 0


def test_taking_the_slot_back_is_never_refused():
    gate = R.Slots(1, 0.05)                        # a tiny wait: past 3 x max(wait, 1 s) it goes over the ceiling
    gate.busy = 1
    t0 = time.monotonic()
    gate.take_back("/api/team")
    assert gate.busy == 2 and 2.9 < time.monotonic() - t0 < 4.5
    assert gate.status()["busy_answers"] == 0


def test_no_lease_outside_a_slotted_request(fake_statement):
    assert R.LEASE.get() is None
    with db.connection("select 1"):
        pass


@needs_db
def test_a_research_request_gives_its_slot_back_around_statements_and_ends_with_none(client):
    R._slots = None
    try:
        client.get("/api/players?league=ref:half&position=RB&limit=5")
        sl = client.get("/api/status").json()["slots"]
    finally:
        R._slots = None
    assert sl["released_for_statements"] >= 1 and sl["busy_answers"] == 0
    assert sl["in_use"] == 0                                 # /api/status itself is not slotted: nothing left held
