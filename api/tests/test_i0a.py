"""Wave I-0, I0-A: the availability overlay (ESPN's injuries feed + Sleeper's directory, applied at request time).

Fixtures: ``fixtures/espn/injuries.json`` is ESPN's feed as read through the browser pane on 2026-10-03T03:58Z (its
shape; trimmed to QB / RB / WR / TE / K / FB entries that are not Active, Active ones since 2026-09-30 and ARI's two
QBs): Justin Jefferson (MIN, ESPN 4262921) Out (ankle) since 2026-10-02T18:35Z, a second Justin Jefferson (CLE
linebacker, 5150249) inactive, Jonah Coleman IR. ``fixtures/espn/db_playerids_espn.csv`` is the id table's rows for
those ESPN ids. Sleeper's directory is the fixture one (no espn_id, no news_updated: the id table maps ESPN to gsis).
Nothing here calls ESPN or Sleeper."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from league_lab import injury_feed as F
from league_lab.sleeper_client import TokenBucket

from league_lab_api import availability as AV
from league_lab_api import decisions

from .conftest import SCRUBS, needs_db

ESPN = Path(__file__).with_name("fixtures") / "espn"
TEST_LEAGUE = "9000000000000000001"
JEFFERSON, COLEMAN, BRISSETT = "00-0036322", "00-0041496", "00-0033119"


@pytest.fixture
def overlay(monkeypatch):
    """The overlay on, reading the ESPN fixture."""
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    F.reset()
    AV._snap = None
    AV._built = None
    decisions.clear_memo()
    yield
    F.reset()
    AV._snap = None
    decisions.clear_memo()


@pytest.fixture
def no_overlay(monkeypatch):
    monkeypatch.setenv(AV.SWITCH_ENV, "off")
    F.reset()
    AV._snap = None
    decisions.clear_memo()
    yield
    decisions.clear_memo()


# ------------------------------------------------------------------------------ the feed (no database)
def test_parse_reads_the_athlete_id_from_the_links():
    feed = json.loads((ESPN / "injuries.json").read_text())
    rows = {r["espn_id"]: r for r in F.parse(feed)}
    jj = rows["4262921"]
    assert (jj["name"], jj["team"], jj["status"], jj["injury"], jj["date"]) == (
        "Justin Jefferson", "MIN", "Out", "Ankle", "2026-10-02T18:35:00+00:00")
    other = rows["5150249"]                                   # the CLE linebacker of the same name: another id
    assert other["team"] == "CLE" and other["fantasy"] == "INACTIVE"
    assert rows["4702555"]["status"] == "Injured Reserve"     # Jonah Coleman
    assert F.athlete_id({"athlete": {"id": 7}}) == "7"
    assert F.athlete_id({"athlete": {"links": [{"href": "sportscenter://x?uid=s:20~l:28~a:42"}]}}) == "42"


def test_espn_statuses_map_to_codes():
    c = AV.espn_code
    assert c({"status": "Out"}) == "OUT"
    assert c({"status": "Out", "fantasy": "INACTIVE"}) == "OUT"
    assert c({"status": "Out", "fantasy": "PUP-R"}) == "PUP"
    assert c({"status": "Injured Reserve", "fantasy": "IR-R"}) == "IR"
    assert c({"status": "Doubtful"}) == "DOUBTFUL"
    assert c({"status": "Questionable"}) == "QUESTIONABLE"
    assert c({"status": "Active"}) == "ACTIVE"
    assert AV.sleeper_code({"injury_status": "IR", "team": "DEN"}) == "IR"
    assert AV.sleeper_code({"injury_status": "Sus", "team": "DEN"}) == "SUS"
    assert AV.sleeper_code({"injury_status": "NA", "team": "GB"}) is None          # unclear: ignored
    assert AV.sleeper_code({"status": "Inactive", "team": "DEN"}) == "INACTIVE"


def test_feed_polls_every_15_minutes_on_a_game_day_hourly_otherwise_and_keeps_the_last_copy(tmp_path):
    feed = json.loads((ESPN / "injuries.json").read_text())
    clock = {"t": datetime(2026, 10, 4, 15, 0, tzinfo=UTC).timestamp()}       # a Sunday
    calls = {"n": 0, "fail": False}

    def fetch(url):
        calls["n"] += 1
        if calls["fail"]:
            raise F.FeedUnavailable("down")
        return feed

    f = F.InjuryFeed(fixtures="", fetch=fetch, wall=lambda: clock["t"], cache_path=tmp_path / "espn_injuries.json",
                     is_game_day=lambda d: d.weekday() == 6, bucket=TokenBucket(1000))
    f.fixtures = None
    assert f.interval_s() == 15 * 60
    s = f.snapshot()
    assert calls["n"] == 1 and len(s["entries"]) == 158 and (tmp_path / "espn_injuries.json").exists()
    clock["t"] += 14 * 60
    f.snapshot()
    assert calls["n"] == 1                                    # within 15 minutes: the copy
    clock["t"] += 2 * 60
    f.snapshot()
    assert calls["n"] == 2                                    # 16 minutes: read again
    calls["fail"] = True
    clock["t"] += 20 * 60
    s = f.snapshot()
    assert calls["n"] == 3 and s is not None and f.stale_served == 1 and f.failures == 1   # ESPN down: the last copy
    g = F.InjuryFeed(fixtures="", fetch=fetch, wall=lambda: clock["t"], cache_path=tmp_path / "espn_injuries.json",
                     is_game_day=lambda d: False)
    g.fixtures = None
    assert g.interval_s() == 60 * 60
    assert len(g.snapshot(refresh=False)["entries"]) == 158  # a restart reads the disk copy


def test_live_server_serves_the_copy_while_a_thread_reads_espn(tmp_path):
    import time as _time
    feed = json.loads((ESPN / "injuries.json").read_text())
    clock = {"t": datetime(2026, 10, 4, 15, 0, tzinfo=UTC).timestamp()}
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        return feed

    f = F.InjuryFeed(fixtures="", fetch=fetch, wall=lambda: clock["t"], cache_path=tmp_path / "e.json",
                     is_game_day=lambda d: True, bucket=TokenBucket(1000), background=True)
    f.fixtures = None
    first = f.snapshot()                                     # no copy yet: this request reads ESPN itself
    assert calls["n"] == 1 and first is not None
    clock["t"] += 20 * 60
    again = f.snapshot()                                     # stale: the old copy at once, a thread reads ESPN
    assert again is first
    for _ in range(50):
        if calls["n"] == 2 and not f._refreshing:
            break
        _time.sleep(0.02)
    assert calls["n"] == 2 and f.snapshot(refresh=False)["fetched_at"] == clock["t"]


def test_off_without_espn_fixtures_in_fixture_mode(monkeypatch):
    monkeypatch.delenv(F.FIXTURES_ENV, raising=False)
    assert not AV.enabled()                                  # the tests' Sleeper fixtures and no ESPN ones: never ESPN
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    assert AV.enabled()
    monkeypatch.setenv(AV.SWITCH_ENV, "off")
    assert not AV.enabled()


def test_now_newest_source_wins(overlay):
    av = AV.now([JEFFERSON, COLEMAN, BRISSETT])
    assert av[JEFFERSON]["status"] == "Out" and av[JEFFERSON]["source"] == "ESPN" and av[JEFFERSON]["note"] == "ankle"
    assert av[JEFFERSON]["as_of"] == "2026-10-02T18:35:00Z"
    # Sleeper's fixture directory says Out for Coleman without news_updated: ESPN's dated IR wins
    assert av[COLEMAN]["code"] == "IR" and av[COLEMAN]["cannot_play"]
    assert av[BRISSETT]["code"] == "ACTIVE" and not av[BRISSETT]["cannot_play"]
    assert AV.checked_at() is not None
    # Sleeper's entry wins when it is newer (news_updated after ESPN's date)
    s = AV.snapshot()
    s.sleeper[JEFFERSON] = {"code": "QUESTIONABLE", "source": "Sleeper", "as_of": datetime(2026, 10, 2, 19, tzinfo=UTC),
                            "fetched_at": datetime(2026, 10, 2, 20, tzinfo=UTC), "note": None, "name": "Justin Jefferson"}
    assert AV.now([JEFFERSON])[JEFFERSON]["source"] == "Sleeper"
    AV._snap = None


# ------------------------------------------------------------------------------ the lineup rebuild (no database)
def _frame() -> pd.DataFrame:
    built = pd.Timestamp("2026-10-02 05:30", tz="UTC")
    st = [("QB", "QB", 1, "QB1", "A QB", "QB", 20.0, 5.0), ("RB", "RB", 2, "RB1", "A RB", "RB", 12.0, 3.0),
          ("WR1", "WR", 3, "JJ", "Justin Jefferson", "WR", 12.68, 3.48), ("WR2", "WR", 4, "WR2", "B WR", "WR", 11.0, 2.0),
          ("FLEX", "FLEX", 5, "FX", "C WR", "WR", 10.0, 0.8)]
    rows = [{"role": "starter", "slot": s, "slot_type": t, "slot_order": o, "bench_rank": None, "gsis_id": f"g-{sid}",
             "sleeper_player_id": sid, "player_name": n, "position": p, "value": v, "value_source": "proj_points",
             "margin": m, "is_locked": False, "is_empty_slot": False, "report_status": None, "reason": None,
             "is_weakest_slot": s == "FLEX", "lineup_value": 65.68, "bench_value": 19.2, "weakest_slot": "FLEX",
             "weakest_margin": 0.8, "n_unvalued": 0, "as_of": built, "locked_now": False, "kicked_off": False}
            for s, t, o, sid, n, p, v, m in st]
    rows[2]["gsis_id"] = JEFFERSON
    for k, (sid, n, p, v) in enumerate([("BR", "Bench RB", "RB", 9.2), ("BW", "Bench WR", "WR", 9.19)], 1):
        rows.append({"role": "bench", "slot": None, "slot_type": None, "slot_order": None, "bench_rank": k, "gsis_id": f"g-{sid}",
                     "sleeper_player_id": sid, "player_name": n, "position": p, "value": v, "value_source": "proj_points",
                     "margin": None, "is_locked": False, "is_empty_slot": False, "report_status": None, "reason": None,
                     "is_weakest_slot": False, "lineup_value": None, "bench_value": None, "weakest_slot": None,
                     "weakest_margin": None, "n_unvalued": None, "as_of": None, "locked_now": False, "kicked_off": False})
    rows.append({**rows[-1], "role": "unplayable", "bench_rank": None, "sleeper_player_id": "OUTRB", "gsis_id": "g-OUTRB",
                 "player_name": "Hurt RB", "position": "RB", "value": 14.0, "reason": "Out", "report_status": "Out"})
    return pd.DataFrame(rows)


def _entry(code, note=None, fetched=datetime(2026, 10, 2, 19, tzinfo=UTC)):
    return {"code": code, "status": AV.LABEL.get(code), "cannot_play": code in AV.CANNOT_PLAY, "flagged": code in AV.FLAGGED,
            "source": "ESPN", "as_of": "2026-10-02T18:35:00Z", "fetched_at": fetched.isoformat(), "note": note}


def test_an_out_starter_moves_to_cant_play_and_the_best_bench_player_starts():
    rows = _frame()
    new, meta = AV.apply_to_rows(rows, overlay={JEFFERSON: _entry("OUT", "ankle")}, players={})
    jj = new[new["player_name"] == "Justin Jefferson"].iloc[0]
    assert jj["role"] == "unplayable" and jj["chip"] == "OUT" and jj["reason"] == "Out"
    assert jj["why"].startswith("Out (ankle) · ESPN, Oct 2 2:35 PM ET")
    st = new[new["role"] == "starter"].set_index("slot")
    assert st.loc["FLEX", "player_name"] == "Bench RB"           # 9.20 beats 9.19: the best bench player
    assert st.loc["WR1", "player_name"] == "B WR" and st.loc["WR2", "player_name"] == "C WR"
    # the lineup loses exactly his margin (B1's margin is the re-solve without him)
    assert st["lineup_value"].iloc[0] == pytest.approx(65.68 - 3.48, abs=0.011)
    assert meta["changes"] == ["Justin Jefferson is out (ankle) — Bench RB starts at FLEX"]


def test_a_player_the_build_sat_as_out_who_is_active_again_starts():
    rows = _frame()
    new, meta = AV.apply_to_rows(rows, overlay={"g-OUTRB": _entry("ACTIVE")}, players={})
    st = new[new["role"] == "starter"].set_index("slot")
    assert "Hurt RB" in set(st["player_name"])
    assert meta["changes"][0].startswith("Hurt RB can play again") and "he starts at" in meta["changes"][0]


def test_a_copy_older_than_the_build_is_ignored_and_a_locked_starter_stays():
    rows = _frame()
    old = _entry("OUT", "ankle", fetched=datetime(2026, 10, 2, 4, tzinfo=UTC))      # read before the 05:30 build
    new, meta = AV.apply_to_rows(rows, overlay={JEFFERSON: old}, players={})
    assert meta["changes"] == [] and new["player_name"].tolist() == rows["player_name"].tolist()
    rows.loc[rows["player_name"] == "Justin Jefferson", "locked_now"] = True
    new, meta = AV.apply_to_rows(rows, overlay={JEFFERSON: _entry("OUT")}, players={})
    assert meta["changes"] == [] and "Justin Jefferson" in set(new.loc[new["role"] == "starter", "player_name"])


def test_one_qb_per_nfl_team_by_depth_chart(monkeypatch):
    # Sleeper's live directory, 2026-10-03: Brissett depth_chart_order 1, Minshew 2, Beck 3 (ARI)
    depth = {"3257": 1.0, "13272": 3.0}
    monkeypatch.setattr(AV, "depth_order", lambda sid: depth.get(str(sid), float("inf")))
    moves = [{"add": {"sleeper_id": "13272", "player_name": "Carson Beck", "position": "QB", "team": "ARI"}},
             {"add": {"sleeper_id": "999", "player_name": "A WR", "position": "WR", "team": "ARI"}},
             {"add": {"sleeper_id": "3257", "player_name": "Jacoby Brissett", "position": "QB", "team": "ARI"}},
             {"add": {"sleeper_id": "888", "player_name": "Other QB", "position": "QB", "team": "LV"}}]
    kept, gone = AV.one_qb_per_team(moves)
    assert [m["add"]["player_name"] for m in kept] == ["A WR", "Jacoby Brissett", "Other QB"]
    assert [m["add"]["player_name"] for m in gone] == ["Carson Beck"]
    depth.clear()                                               # no depth chart: the better-ranked claim stays
    kept, _ = AV.one_qb_per_team(moves)
    assert [m["add"]["player_name"] for m in kept] == ["Carson Beck", "A WR", "Other QB"]


def test_waivers_overlay_drops_claims_of_players_who_cannot_play(overlay):
    out = {"total_moves": 3, "cards": [], "free_agents": [{"gsis_id": COLEMAN, "player_name": "Jonah Coleman"},
                                                         {"gsis_id": BRISSETT, "player_name": "Jacoby Brissett"}],
           "moves": [{"add": {"gsis_id": JEFFERSON, "player_name": "Justin Jefferson", "position": "WR", "team": "MIN"},
                      "drop": None},
                     {"add": {"gsis_id": BRISSETT, "player_name": "Jacoby Brissett", "position": "QB", "team": "ARI"},
                      "drop": {"gsis_id": COLEMAN, "player_name": "Jonah Coleman"}}]}
    out = AV.waivers_overlay(out)
    assert [m["add"]["player_name"] for m in out["moves"]] == ["Jacoby Brissett"]
    assert out["moves"][0]["drop"]["this_week"] == 0.0 and out["moves"][0]["drop"]["cannot_play"] == "IR"
    assert [f["player_name"] for f in out["free_agents"]] == ["Jacoby Brissett"]
    assert out["availability"]["claims_left_out"] == [{"player_name": "Justin Jefferson", "status": "Out"}]
    assert out["total_moves"] == 2


# ------------------------------------------------------------------------------ the routes (database)
def _starters(d: dict) -> dict[str, str]:
    return {r["slot"]: r["player_name"] for r in d["lineup_full"] if r["role"] == "starter"}


def _cant(d: dict) -> dict[str, dict]:
    return {r["player_name"]: r for r in d["lineup_full"] if r["slot"] == "Can't play"}


@needs_db
def test_test_league_my_week_moves_jefferson_out(client, monkeypatch):
    monkeypatch.setenv(AV.SWITCH_ENV, "off")
    base = client.get(f"/api/my-week?league={TEST_LEAGUE}&team=10").json()
    jj = next(r for r in base["lineup_full"] if r["player_name"] == "Justin Jefferson")
    assert jj["role"] == "starter", "the fixture week starts Jefferson"
    monkeypatch.delenv(AV.SWITCH_ENV)
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    F.reset()
    AV._snap = None
    d = client.get(f"/api/my-week?league={TEST_LEAGUE}&team=10").json()
    assert "Justin Jefferson" not in _starters(d).values()
    row = _cant(d)["Justin Jefferson"]
    assert row["flag"] == "OUT" and row["reason"].startswith("Out (ankle) · ESPN")
    # his margin is what the lineup loses without him alone; the fixture feed has others out too, so at least that
    assert d["lineup_value"] <= base["lineup_value"] - jj["margin"] + 0.02
    ch = d["availability"]["changes"]
    print("test league roster 10:", ch)
    assert d["availability"]["checked_at"]
    line = next(c for c in ch if c.startswith("Justin Jefferson is out (ankle) — "))
    # the best bench player who can take his WR spot now starts, and the sentence names him
    bench = [r for r in base["lineup_full"] if r["role"] == "bench" and r["position"] == "WR"]
    best = max(bench, key=lambda r: r["value"] or -1)
    assert best["player_name"] in _starters(d).values() and best["player_name"] in line
    assert all(c["gsis_id"] != JEFFERSON for c in d["cards"])
    F.reset()


@needs_db
def test_scrubs_roster_2_my_week_with_jefferson_out(client, overlay, monkeypatch):
    monkeypatch.setenv(AV.SWITCH_ENV, "off")
    base = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()
    jj = next(r for r in base["lineup_full"] if r["player_name"] == "Justin Jefferson")
    assert jj["role"] == "starter"
    monkeypatch.delenv(AV.SWITCH_ENV)
    AV._snap = None
    d = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()
    # one starter out (Ferguson, the bench TE, is the other change): the lineup loses exactly Jefferson's margin
    assert d["lineup_value"] == pytest.approx(base["lineup_value"] - jj["margin"], abs=0.02)
    assert d["lineup"] and any(r["slot"] == "Flex 2" or r["slot"] == "FLEX2" for r in d["lineup"])
    assert d["source"] == "database"
    st = _starters(d)
    assert "Justin Jefferson" not in st.values()
    assert _cant(d)["Justin Jefferson"]["flag"] == "OUT"
    first = d["availability"]["changes"][0]
    assert first.startswith("Justin Jefferson is out (ankle) — ")
    who = first.split(" — ")[1].split(" starts at ")[0]
    assert st["FLEX2"] == who                                   # the clone, 2026-10-02 build: Michael Wilson (9.20)
    assert who in ("Michael Wilson", "Jacory Croskey-Merritt")  # 9.20 vs 9.19: whoever is best
    print("scrubs roster 2:", d["availability"]["changes"])


@needs_db
def test_trends_leave_out_players_who_cannot_play(client, monkeypatch):
    monkeypatch.setenv(AV.SWITCH_ENV, "off")
    base = client.get(f"/api/trends?league={SCRUBS}&limit=500&metrics=none").json()
    monkeypatch.delenv(AV.SWITCH_ENV)
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    F.reset()
    AV._snap = None
    d = client.get(f"/api/trends?league={SCRUBS}&limit=500&metrics=none").json()
    out = {p["gsis_id"] for p in d["availability"]["left_out_players"]}
    assert d["availability"]["left_out"] == len(out) > 0
    assert not out & {p["gsis_id"] for p in d["players"]}
    # IU-3: Trends asks the one gate, which also rules from the stored record and the week's own report with the live
    # sources off — so the base list leaves some out already, and the live sources add the rest
    base_out = {p["gsis_id"] for p in base["availability"]["left_out_players"]}
    assert base_out <= out
    assert {p["gsis_id"] for p in base["players"]} - {p["gsis_id"] for p in d["players"]} == out - base_out
    statuses = {p["status"] for p in d["availability"]["left_out_players"]}
    assert statuses <= {"Out", "IR", "PUP", "NFI", "Suspended", "Inactive", "Doubtful"}   # IU-3: unlikely to play sits too
    print("trends left out:", d["availability"]["left_out"], sorted(statuses))
    F.reset()


@needs_db
@pytest.mark.parametrize("league,team", [(TEST_LEAGUE, 10), (SCRUBS, 2)])
def test_waivers_no_claims_of_players_who_cannot_play_and_one_qb_per_team(client, overlay, league, team):
    d = client.get(f"/api/waivers?league={league}&team={team}&limit=200").json()
    av = AV.now([m["add"]["gsis_id"] for m in d["moves"] if m["add"].get("gsis_id")]
                + [f["gsis_id"] for f in d["free_agents"] if f.get("gsis_id")])
    assert not [m for m in d["moves"] if (av.get(m["add"].get("gsis_id")) or {}).get("cannot_play")]
    assert not [f for f in d["free_agents"] if (av.get(f.get("gsis_id")) or {}).get("cannot_play")]
    qbs = [m["add"]["team"] for m in d["moves"] if m["add"]["position"] == "QB" and m["add"].get("team")]
    assert len(qbs) == len(set(qbs))
    assert "availability" in d and d["availability"]["checked_at"]


@needs_db
def test_status_reports_the_stamp_and_drops_the_stale_warning(client, overlay):
    client.get(f"/api/my-week?league={SCRUBS}&team=2")
    d = client.get("/api/status").json()
    a = d["availability"]
    assert a["enabled"] and a["checked_at"] and a["source_ages"]["espn_s"] is not None and a["n_out"] > 0
    assert d["warning"] is None


@needs_db
def test_trades_an_out_player_is_worth_zero_this_week(client, overlay):
    rosters = json.loads((Path(__file__).with_name("fixtures") / "sleeper" / f"rosters_{SCRUBS}.json").read_text())
    other = next(r for r in rosters if r["roster_id"] == 1)
    body = {"league": SCRUBS, "team": 2, "partner": 1, "give": ["6794"], "get": [other["players"][0]]}
    d = client.post("/api/trades/evaluate", json=body).json()
    jj = d["give"][0]
    assert jj["this_week"] == 0.0 and jj["cannot_play"] == "Out"


@needs_db
def test_ros_carries_the_overlay_injury_status(client, overlay):
    d = client.get(f"/api/ros?league={SCRUBS}&position=WR&limit=100").json()
    assert all("injury_status" in p for p in d["players"])
    jj = [p for p in d["players"] if p["gsis_id"] == JEFFERSON]
    if jj:
        assert jj[0]["injury_status"] == "Out"
