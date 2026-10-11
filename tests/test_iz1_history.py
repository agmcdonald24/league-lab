"""IZ-1 (Wave I-Z): Sleeper's past weeks -> ops.sleeper_history (no database, no network).

The saved answers are built here in the shape the PO measured on 2026-10-11 (docs/METRICS.md § hh1.0): every object
of the existing fixture (real Sleeper ids, invented lines: tests/fixtures/sleeper_projections) plus the players
Sleeper lists without a line (``stats`` holds only ``adp_dd_ppr``), the key ``week_shard``, and one ``updated_at`` /
``last_modified`` for the whole week, minutes after its last game; the 2023 shape carries neither. Served through
``httpx.MockTransport``; rows go to an in-memory store that behaves like ``PgStore``.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from league_lab.ingest import sleeper_history as sh
from league_lab.ingest import sleeper_projections as sp

FIX = Path(__file__).parent / "fixtures" / "sleeper_projections" / "projections_2026_w04.json"
BASE = "https://sleeper.test/projections/nfl"
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
CLOSED_MS = 1762232420000          # 2025-11-04 05:00:20 UTC: one instant for the whole week (the PO's 2025 week 9)


def answer(season: int, week: int, *, stamped: bool = True, no_line: int = 5) -> list[dict]:
    """A week's answer in the real shape: the fixture's objects re-labelled, plus players without a line."""
    out = []
    for o in json.loads(FIX.read_text()):
        if not o.get("player_id"):
            continue
        o = copy.deepcopy(o)
        o.update({"season": str(season), "week": week, "week_shard": f"{season}_{week}"})
        if stamped:
            o["updated_at"] = o["last_modified"] = CLOSED_MS
        else:
            o.pop("updated_at", None)
            o.pop("last_modified", None)
        out.append(o)
    for i in range(no_line):
        out.append({"status": None, "date": None, "category": "proj", "sport": "nfl", "season": str(season),
                    "season_type": "regular", "week": week, "player_id": str(90000 + i), "team": None, "opponent": None,
                    "company": "rotowire", "game_id": None, "week_shard": f"{season}_{week}",
                    **({"updated_at": CLOSED_MS, "last_modified": CLOSED_MS} if stamped else {}),
                    "player": {"position": "WR", "first_name": "No", "last_name": f"Line{i}"},
                    "stats": {"adp_dd_ppr": 400 + i}})
    return out


OBJECTS = 31   # the fixture's objects with a player_id (one of them with stats null)
KEPT = 30      # ... with a projected line


class MemStore:
    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.weeks: dict[tuple, dict] = {}

    def held(self):
        return {k for k, v in self.weeks.items() if v["status"] == "ok"}

    def attempts(self, season, week):
        return int((self.weeks.get((season, week)) or {}).get("attempts") or 0)

    def save(self, season, week, rows, week_row):
        for k in [k for k in self.rows if k[:2] == (season, week)]:
            del self.rows[k]
        for r in rows:
            self.rows[(season, week, r["player_id"])] = r
        self.weeks[(season, week)] = week_row

    def fail(self, week_row):
        for k in [k for k in self.rows if k[:2] == (week_row["season"], week_row["week"])]:
            del self.rows[k]
        self.weeks[(week_row["season"], week_row["week"])] = week_row


def transport(calls: list, broken: set | None = None, empty: set | None = None):
    def handler(req: httpx.Request) -> httpx.Response:
        parts = req.url.path.rstrip("/").split("/")
        season, week = int(parts[-2]), int(parts[-1])
        calls.append((season, week))
        if broken and (season, week) in broken:
            return httpx.Response(404, text="nope")      # (a 5xx is retried by the client, with its backoff)
        if empty and (season, week) in empty:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=answer(season, week, stamped=season != 2023))
    return httpx.MockTransport(handler)


def run(tmp_path, store, calls, **kw):
    pauses = []
    r = sh.HistoryRun(store=store, raw_dir=tmp_path, base_url=BASE, now=NOW,
                      client=httpx.Client(transport=transport(calls, **kw)), pause=pauses.append)
    return r, pauses


# ------------------------------------------------------------------------------ parsing
def test_only_players_with_a_line_are_kept_and_marked_after_the_week():
    p = sh.history_rows(answer(2025, 9), 2025, 9, NOW)
    assert p.n_objects == OBJECTS + 5                   # + 5 players without a line
    assert len(p.rows) == KEPT                          # the stats-null object and the no-line players are counted, not kept
    assert all(r["served"] == "after_week" for r in p.rows)
    assert p.updated_min == p.updated_max == datetime(2025, 11, 4, 5, 0, 20, tzinfo=UTC)
    assert all(r["updated_at"] == p.updated_max and r["fetched_at"] == NOW for r in p.rows)
    allen = next(r for r in p.rows if r["player_id"] == "4984")
    assert allen["passing_yards"] == 267.3 and allen["pts_half_ppr"] == 25.5 and allen["position"] == "QB"
    assert "payload" not in allen and set(allen) <= {c for c, _ in sh.COLUMNS}
    assert p.by_position["QB"] == 6 and "?" not in p.by_position


def test_2023_answers_carry_no_updated_at():
    p = sh.history_rows(answer(2023, 5, stamped=False), 2023, 5, NOW)
    assert p.rows and all(r["updated_at"] is None for r in p.rows) and p.updated_max is None


@pytest.mark.parametrize("bad", [[], {"error": "x"}, None])
def test_an_answer_that_is_not_a_list_is_refused(bad):
    with pytest.raises(ValueError):
        sh.history_rows(bad, 2025, 1, NOW)


# ------------------------------------------------------------------------------ which weeks
def test_wanted_weeks_are_the_history_seasons_and_this_seasons_weeks_without_a_pre_kickoff_snapshot():
    first = {(2026, w): datetime(2026, 9, 10, tzinfo=UTC) + timedelta(days=7 * (w - 1)) for w in range(1, 19)}
    last = {k: v + timedelta(days=4) for k, v in first.items()}
    pre = {(2026, 5)}                                    # the record's first week
    now = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)       # week 5's last game (Oct 12, 00:00) is not 5 hours old yet
    w = sh.wanted_weeks(2026, first, last, pre, now)
    assert w[:54] == [(s, k) for s in (2023, 2024, 2025) for k in range(1, 19)]
    assert w[54:] == [(2026, 1), (2026, 2), (2026, 3), (2026, 4)]
    later = sh.wanted_weeks(2026, first, last, pre, datetime(2026, 10, 25, tzinfo=UTC))
    assert (2026, 5) not in later and (2026, 6) in later                 # a missed snapshot is filled after the week
    assert sh.wanted_weeks(2025, first, last, pre, now)[-1] == (2024, 18)  # only seasons before the current one


# ------------------------------------------------------------------------------ the run: once, politely, never failing
def test_a_night_pulls_each_week_once_a_second_apart_and_the_next_night_only_what_failed(tmp_path):
    want = [(2023, 1), (2023, 2), (2024, 1), (2025, 9), (2026, 4)]
    store, calls = MemStore(), []
    r, pauses = run(tmp_path, store, calls, broken={(2024, 1)})
    r.pull(want)
    assert calls == want                                 # one request a week
    assert pauses == [1.0] * (len(want) - 1)             # at least a second between two requests
    assert store.held() == set(want) - {(2024, 1)}
    bad = store.weeks[(2024, 1)]
    assert bad["status"] == "failed" and "404" in bad["error"] and bad["attempts"] == 1
    assert not (tmp_path / "sleeper" / "projections_history" / "2024").exists() or \
        not list((tmp_path / "sleeper" / "projections_history" / "2024").iterdir())     # no file left behind
    assert store.weeks[(2025, 9)]["n_lines"] == KEPT and store.weeks[(2025, 9)]["n_objects"] == OBJECTS + 5
    # the next night: only the failed week is asked again
    calls2 = []
    r2, _ = run(tmp_path, store, calls2)
    r2.pull(want)
    assert calls2 == [(2024, 1)] and store.held() == set(want)
    assert store.weeks[(2024, 1)]["attempts"] == 2
    # and the night after: nothing
    calls3 = []
    r3, _ = run(tmp_path, store, calls3)
    r3.pull(want)
    assert calls3 == []


def test_an_empty_answer_is_a_failed_week_not_an_empty_one(tmp_path):
    store, calls = MemStore(), []
    r, _ = run(tmp_path, store, calls, empty={(2025, 18)})
    r.pull([(2025, 18)])
    assert store.weeks[(2025, 18)]["status"] == "failed" and (2025, 18) not in store.held()
    assert not store.rows


def test_three_failures_in_a_row_stop_the_night(tmp_path):
    want = [(2023, w) for w in range(1, 8)]
    store, calls = MemStore(), []
    r, _ = run(tmp_path, store, calls, broken=set(want))
    r.pull(want)
    assert calls == want[:3] and "4 weeks left for the next night" in r.log_lines[0]


def test_a_fresh_database_takes_the_archive_before_asking(tmp_path):
    want = [(2023, 5), (2025, 9)]
    store, calls = MemStore(), []
    r, _ = run(tmp_path, store, calls)
    r.pull(want)
    rows_before = dict(store.rows)
    fresh, calls2 = MemStore(), []                     # tomorrow: a fresh database, the archive in the cache
    r2, _ = run(tmp_path, fresh, calls2)
    r2.replay(want)
    r2.pull(want)
    assert calls2 == [] and fresh.held() == set(want) and r2.replayed == want
    assert {k: v["passing_yards"] for k, v in fresh.rows.items()} == {k: v["passing_yards"] for k, v in rows_before.items()}


def test_the_history_archive_is_never_the_records_snapshot_folder(tmp_path):
    store, calls = MemStore(), []
    r, _ = run(tmp_path, store, calls)
    r.pull([(2026, 4)])
    files = list((tmp_path / "sleeper" / "projections_history" / "2026").glob("04_*.json.gz"))
    assert len(files) == 1
    assert sp.archived_snapshots(tmp_path) == []        # the nightly's replay-projections never sees a history file


def test_the_report_says_weeks_held_of_wanted_by_season():
    res = {"wanted": [(2023, 1), (2023, 2), (2026, 1)], "held": [(2023, 1)], "replayed": [], "pulled": [(2023, 1)],
           "failed": [((2023, 2), "FetchError: 500")], "notes": [], "offline": False}
    lines = sh.report_lines(res)
    assert lines[0] == "weeks held: 1 of 3 (2023 1/2, 2026 0/1)"
    assert lines[1] == "tonight: 1 pulled, 0 from the archive, 1 failed"
    assert "failed 2023 week 2" in lines[2] and "asked again next night" in lines[2]
