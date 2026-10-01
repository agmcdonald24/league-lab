"""Plan E1: Sleeper's projections loader and the pricing of Sleeper's line (no database, no network).

The answer is the hand-built fixture tests/fixtures/sleeper_projections/projections_2026_w04.json
(make_fixture.py: real Sleeper ids, invented lines, ``pts_*`` computed from Sleeper's own keys with Sleeper's
default weights — never through League Lab's mapping), served through ``httpx.MockTransport``; rows go to an
in-memory store that behaves like ``PgStore``.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from league_lab.config import PROJECT_ROOT
from league_lab.http import read_meta
from league_lab.ingest import sleeper_projections as sp

FIX = Path(__file__).parent / "fixtures" / "sleeper_projections" / "projections_2026_w04.json"
PAYLOAD = json.loads(FIX.read_text())
BASE = "https://sleeper.test/projections/nfl"
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

# League of Scrubs' scoring_settings (dim_league_season, 2026): Sleeper's standard half PPR for every
# offensive and kicking key (rec 0.5, pass_yd 0.04, pass_td 4, pass_int -1, fum_lost -2, 2-pt 2 ...)
SCRUBS = {"ff": 1.0, "fum": 0.0, "int": 2.0, "rec": 0.5, "xpm": 1.0, "sack": 1.0, "safe": 2.0, "st_ff": 1.0, "st_td": 6.0,
          "def_td": 6.0, "fgmiss": -1.0, "rec_td": 6.0, "rec_yd": 0.1, "xpmiss": -1.0, "fgm_50p": 5.0, "fum_rec": 2.0,
          "pass_td": 4.0, "pass_yd": 0.04, "rec_2pt": 2.0, "rush_td": 6.0, "rush_yd": 0.1, "blk_kick": 2.0, "fgm_0_19": 3.0,
          "fum_lost": -2.0, "pass_2pt": 2.0, "pass_int": -1.0, "rush_2pt": 2.0, "def_st_ff": 1.0, "def_st_td": 6.0,
          "fgm_20_29": 3.0, "fgm_30_39": 3.0, "fgm_40_49": 4.0, "fum_rec_td": 6.0, "st_fum_rec": 1.0, "pts_allow_0": 10.0,
          "pts_allow_1_6": 7.0, "pts_allow_35p": -4.0, "def_st_fum_rec": 1.0, "pts_allow_7_13": 4.0, "pts_allow_14_20": 1.0,
          "pts_allow_21_27": 0.0, "pts_allow_28_34": -1.0}
# Forever Unclean Dynasty: full PPR, 6-point and 0.05-a-yard passing, -2 interceptions, yardage and 40+ TD bonuses
DYNASTY = {**{k: v for k, v in SCRUBS.items() if not k.startswith(("fgm", "fgmiss", "xp"))},
           "rec": 1.0, "pass_td": 6.0, "pass_yd": 0.05, "pass_int": -2.0, "bonus_pass_yd_300": 3.0, "bonus_pass_yd_400": 6.0,
           "bonus_rush_yd_100": 3.0, "bonus_rush_yd_200": 6.0, "bonus_rec_yd_100": 3.0, "bonus_rec_yd_200": 6.0,
           "pass_td_40p": 2.0, "rush_td_40p": 2.0, "rec_td_40p": 2.0}


def priced_objects() -> list[dict]:
    """Fixture objects with a line and Sleeper's own points (a DEF's include points-allowed tiers: not priced)."""
    return [o for o in PAYLOAD if o.get("player_id") and isinstance(o.get("stats"), dict)
            and o["player"]["position"] != "DEF"]


# ------------------------------------------------------------------------------ the mapping
def test_line_columns_match_the_mart():
    sql = (PROJECT_ROOT / "dbt" / "models" / "marts" / "edge" / "mart_projection_record.sql").read_text()
    block = re.search(r"set line_columns = \[(.*?)\]", sql, re.S).group(1)
    assert tuple(re.findall(r"'([a-z0-9_]+)'", block)) == sp.LINE_COLUMNS


def test_parse_line_maps_sleeper_keys_to_stat_columns():
    line = sp.parse_line({"pass_yd": 250.5, "pass_att": 33, "rec_tgt": "n/a", "rush_att": None, "fgm_50p": 0.2,
                          "fgmiss": 0.3, "xpmiss": 0.1, "rec_td_40p": 0.05, "adp_dd_ppr": 12, "bonus_rec_te": 4})
    assert line["passing_yards"] == 250.5 and line["attempts"] == 33.0
    assert line["targets"] is None and line["carries"] is None          # non-numeric / null: unknown, not zero
    assert line["receptions"] is None                                   # not given: NULL
    assert line["fg_made_50_59"] == 0.2 and line["fg_missed"] == 0.3 and line["pat_missed"] == 0.1
    assert line["rec_tds_40p"] == 0.05
    assert set(line) == set(sp.LINE_COLUMNS)                            # unknown keys never become columns
    assert sp.parse_line(None) == dict.fromkeys(sp.LINE_COLUMNS)


# ------------------------------------------------------------------------------ the pricing (acceptance)
@pytest.mark.parametrize("rec_weight,pts_key", [(0.5, "pts_half_ppr"), (1.0, "pts_ppr"), (0.0, "pts_std")])
def test_pricing_reproduces_sleepers_own_points(rec_weight, pts_key):
    scoring = {**SCRUBS, "rec": rec_weight}
    objs = priced_objects()
    assert len(objs) == 29                                             # 6 QB, 8 RB, 6 TE, 8 WR, 1 K
    worst = max(abs(sp.price_line(o["stats"], scoring) - o["stats"][pts_key]) for o in objs)
    assert worst <= 0.05, worst


def test_pricing_worked_by_hand():
    allen = next(o for o in PAYLOAD if o.get("player_id") == "4984")["stats"]
    # 267.3 x 0.04 + 2.01 x 4 - 0.62 + 29.1 x 0.1 + 0.78 x 6 - 0.15 x 2 + 0.05 x 2 (a 2-pt pass) = 25.502
    assert sp.price_line(allen, SCRUBS) == pytest.approx(25.50, abs=0.005)
    assert allen["pts_half_ppr"] == pytest.approx(25.50, abs=0.005)
    # the dynasty's scoring: 267.3 x 0.05 + 2.01 x 6 - 0.62 x 2 + 2.91 + 4.68 - 0.30 + 0.10 = 31.575 (no 300-yard bonus)
    assert sp.price_line(allen, DYNASTY) == pytest.approx(31.575, abs=0.006)
    reichard = next(o for o in PAYLOAD if o.get("player_id") == "11792")["stats"]
    # 0.6 x 3 + 0.7 x 3 + 0.5 x 4 + 0.2 x 5 - 0.3 + 2.6 - 0.1 = 9.1
    assert sp.price_line(reichard, SCRUBS) == pytest.approx(9.1, abs=0.005)


def test_a_projected_bonus_pays_like_on_our_own_line():
    # the same threshold rule as League Lab's projection (scoring.compute_points on the projected line)
    big = {"rec": 7.0, "rec_yd": 104.0, "rec_td": 0.6}
    assert sp.price_line(big, DYNASTY) == pytest.approx(7 + 10.4 + 3.6 + 3.0, abs=0.005)
    assert sp.price_line({**big, "rec_yd": 99.9}, DYNASTY) == pytest.approx(7 + 9.99 + 3.6, abs=0.005)


# ------------------------------------------------------------------------------ rows
def test_projection_rows_are_defensive_and_keep_the_payload():
    rows = sp.projection_rows(PAYLOAD, 2026, 4, T0, "x.json.gz")
    assert len(rows) == len(PAYLOAD) - 1                                 # the object without player_id is skipped
    by = {r["player_id"]: r for r in rows}
    allen = by["4984"]
    assert allen["position"] == "QB" and allen["team"] == "BUF" and allen["opponent"] == "NE"
    assert allen["company"] == "rotowire" and allen["category"] == "proj" and allen["game_id"] == "2026_04_NE_BUF"
    assert allen["passing_yards"] == 267.3 and allen["pts_half_ppr"] == 25.5 and allen["fetched_at"] == T0
    assert allen["payload"]["stats"]["adp_dd_ppr"] == 10                 # unknown keys kept in the payload
    assert by["12526"]["targets"] is None and by["12526"]["receptions"] == 4.4
    assert by["MIN"]["position"] == "DEF" and by["MIN"]["pts_std"] == 8.4
    empty = by["9999999"]
    assert empty["pts_ppr"] is None and all(empty[c] is None for c in sp.LINE_COLUMNS)
    with pytest.raises(ValueError):
        sp.projection_rows({"error": "nope"}, 2026, 4, T0)


def test_request_url():
    url = sp.projections_url(BASE + "/", 2026, 4)
    assert url == (f"{BASE}/2026/4?season_type=regular&position[]=QB&position[]=RB&position[]=WR&position[]=TE"
                   "&position[]=K&position[]=DEF&order_by=ppr")


def test_next_week_is_the_first_not_kicked_off():
    k = {(2026, 4): datetime(2026, 10, 2, 0, 15, tzinfo=UTC), (2026, 5): datetime(2026, 10, 9, 0, 15, tzinfo=UTC)}
    assert sp.next_week(k, 2026, T0) == 4
    assert sp.next_week(k, 2026, datetime(2026, 10, 2, 1, 0, tzinfo=UTC)) == 5
    assert sp.next_week(k, 2026, datetime(2026, 12, 1, tzinfo=UTC)) is None


# ------------------------------------------------------------------------------ the loader: round trip
class MemStore:
    """PgStore without Postgres: rows keyed like the table, the manifest state per partition."""

    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.state: dict[tuple, dict] = {}
        self.records = []

    def partition_state(self, dataset, partition_key):
        return self.state.get((dataset, partition_key))

    def replace(self, rows, rec, season, week, fetched_at):
        for k in [k for k in self.rows if k[:3] == (season, week, fetched_at)]:
            del self.rows[k]
        for r in rows:
            self.rows[(season, week, fetched_at, r["player_id"])] = r
        rec.row_count = len(rows)
        self.record(rec)
        return len(rows)

    def record(self, rec):
        self.records.append(rec)
        if rec.status == "success":
            self.state[(rec.dataset, rec.partition_key)] = {"checksum_sha256": rec.checksum_sha256, "row_count": rec.row_count}


class Sleeper:
    """MockTransport serving the fixture (or whatever ``body`` is set to)."""

    def __init__(self, body=PAYLOAD, status=200):
        self.body, self.status, self.urls = body, status, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        return httpx.Response(self.status, json=self.body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def run(tmp_path, store, server=None, now=T0, force=False):
    return sp.ProjectionsRun(store=store, raw_dir=tmp_path / "raw", base_url=BASE, now=now, force=force,
                             client=(server or Sleeper()).client())


def table(store) -> dict:
    """The loaded rows without the run-dependent file path, comparable across stores."""
    return {k: {c: v for c, v in r.items() if c != "file_path"} for k, r in store.rows.items()}


def test_pull_archives_one_snapshot_and_replay_rebuilds_it(tmp_path):
    server, store = Sleeper(), MemStore()
    rec = run(tmp_path, store, server).pull(2026, 4)
    assert rec.status == "success" and rec.row_count == 31
    assert len(server.urls) == 1 and server.urls[0].startswith(f"{BASE}/2026/4?season_type=regular")
    assert server.urls[0].count("position") == 6 and server.urls[0].endswith("order_by=ppr")
    snap = tmp_path / "raw" / "sleeper" / "projections" / "2026" / "04_20261001T120000Z.json.gz"
    assert snap.exists() and read_meta(snap)["sha256"]
    assert {k[2] for k in store.rows} == {T0}                           # one fetched_at for the whole pull
    assert [r.dataset for r in store.records] == ["projections_pull", "projections"]
    # a fresh database: --offline rebuilds the same rows, without the network
    fresh = MemStore()
    sp.ProjectionsRun(store=fresh, raw_dir=tmp_path / "raw", base_url="http://unreachable.invalid").replay()
    assert table(fresh) == table(store)
    # replaying again changes nothing (the manifest holds these bytes)
    again = sp.ProjectionsRun(store=fresh, raw_dir=tmp_path / "raw", base_url="x").replay()
    assert [r.status for r in again] == ["skipped_unchanged"]


def test_an_unchanged_pull_writes_no_new_snapshot(tmp_path):
    store = MemStore()
    run(tmp_path, store).pull(2026, 4)
    later = T0 + timedelta(hours=20)
    rec = run(tmp_path, store, now=later).pull(2026, 4)
    files = sorted(p.name for p in (tmp_path / "raw" / "sleeper" / "projections" / "2026").glob("*.json.gz"))
    assert files == ["04_20261001T120000Z.json.gz"]
    assert rec.status == "skipped_unchanged" and len(store.rows) == 31
    assert read_meta(tmp_path / "raw" / "sleeper" / "projections" / "2026" / files[0])["checked_at"] == later.isoformat()


def test_a_changed_pull_is_a_second_snapshot_and_the_first_is_kept(tmp_path):
    store = MemStore()
    run(tmp_path, store).pull(2026, 4)
    changed = json.loads(json.dumps(PAYLOAD))
    changed[0]["stats"]["pass_yd"] = 280.0
    later = T0 + timedelta(hours=30)
    run(tmp_path, store, Sleeper(changed), now=later).pull(2026, 4)
    assert {k[2] for k in store.rows} == {T0, later} and len(store.rows) == 62
    assert store.rows[(2026, 4, T0, "4984")]["passing_yards"] == 267.3
    assert store.rows[(2026, 4, later, "4984")]["passing_yards"] == 280.0


@pytest.mark.parametrize("body,status", [({"error": "bad"}, 200), ([], 200), ({"error": "x"}, 404)])
def test_a_bad_answer_fails_and_leaves_no_file(tmp_path, body, status):
    store = MemStore()
    rec = run(tmp_path, store, Sleeper(body, status)).pull(2026, 4)
    assert rec.status in ("failed", "contract_failed") and rec.dataset == "projections_pull"
    assert not list((tmp_path / "raw").rglob("*.json*"))
    assert store.rows == {}


def test_a_hand_curled_json_replays_with_its_name_as_the_fetch_time(tmp_path):
    d = tmp_path / "raw" / "sleeper" / "projections" / "2026"
    d.mkdir(parents=True)
    shutil.copy(FIX, d / "04_20261001T221500Z.json")
    (d / "notes.txt").write_text("ignored")
    store = MemStore()
    res = sp.ProjectionsRun(store=store, raw_dir=tmp_path / "raw", base_url="x").replay()
    assert [r.status for r in res] == ["success"]
    assert {k[2] for k in store.rows} == {datetime(2026, 10, 1, 22, 15, tzinfo=UTC)}


def test_replay_can_be_narrowed_to_a_week(tmp_path):
    store = MemStore()
    run(tmp_path, store).pull(2026, 4)
    run(tmp_path, store, now=T0 + timedelta(days=7)).pull(2026, 5)
    fresh = MemStore()
    sp.ProjectionsRun(store=fresh, raw_dir=tmp_path / "raw", base_url="x").replay([2026], [5])
    assert {k[1] for k in fresh.rows} == {5}
