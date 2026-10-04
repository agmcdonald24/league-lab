"""IG-3 (Wave I-G): the small opens — the waiver deadline on Waivers, MFL's own roster-freshness line on My Week, the
MFL grade's qualification next to the headline grade on About, the stash writer's call shown as written, usage
retention. MFL 70587 / 21861 and the Sleeper leagues answer from the fixtures (no outside call); the screens that read
the database need it (`needs_db`, the clone `league_lab_i0b`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import psycopg
import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import player_ids as PI

from league_lab_api import about, decisions, ondemand

from .conftest import DYNASTY, SCRUBS, SLEEPER_FIXTURES, needs_db
from .test_i0b import IDS, MFL_FX

DAD = "mfl:70587"            # FCFS, no waiver time in the export
BBID = "mfl:21861"           # BBID_FCFS
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _mfl_fixtures(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    decisions.clear_memo()
    yield
    PI.reset()
    A._default = None
    decisions.clear_memo()


def _league(lid: str) -> dict:
    return json.loads((SLEEPER_FIXTURES / f"league_{lid}.json").read_text())


NOW = pd.Timestamp("2026-10-04 07:50", tz="UTC")       # Sunday 3:50 AM ET


# ------------------------------------------------------------------ the waiver deadline (pure, on the fixtures' settings)
def test_sleeper_weekly_waivers_say_the_day_and_time():
    """League of Scrubs: rolling waivers (waiver_type 0), weekly (daily_waivers 0) on day 2 = Wednesday at hour 0 Pacific
    = 3:00 AM ET; a dropped player clears in a day."""
    d = decisions.waiver_deadline(_league(SCRUBS), now=NOW)
    assert d["kind"] == "rolling" and d["daily"] is False and d["clear_days"] == 1
    assert d["runs_words"] == "Wednesday 3:00 AM ET" and d["runs_at"] == "2026-10-07T07:00:00+00:00"
    assert d["words"] == "Claims run Wednesday 3:00 AM ET (rolling waivers)." and d["source"] == "Sleeper league settings"


def test_sleeper_daily_faab_waivers():
    """The dynasty: FAAB (waiver_type 2), daily waivers at hour 2 Pacific = 5:00 AM ET — the next run is this morning."""
    d = decisions.waiver_deadline(_league(DYNASTY), now=NOW)
    assert d["kind"] == "faab" and d["daily"] is True
    assert d["runs_words"] == "every day at 5:00 AM ET" and d["runs_at"] == "2026-10-04T09:00:00+00:00"
    assert d["words"].startswith("Claims run every day at 5:00 AM ET (FAAB blind bids)")


def test_the_next_run_rolls_to_next_week_once_passed():
    after = pd.Timestamp("2026-10-07 07:30", tz="UTC")              # Wednesday 3:30 AM ET: this week's run is over
    assert decisions.waiver_deadline(_league(SCRUBS), now=after)["runs_at"] == "2026-10-14T07:00:00+00:00"


def test_no_settings_no_line():
    """Unknown is not a time: a league whose settings say nothing gets no line; the database's waiver type alone gives
    the kind and "see Sleeper"."""
    assert decisions.waiver_deadline({"settings": {}}, now=NOW) is None
    d = decisions.waiver_deadline({"settings": {}}, now=NOW, kind_fallback=2)
    assert d["runs_at"] is None and d["words"] == "Claims run on Sleeper's schedule (FAAB blind bids): see Sleeper for the time."


@pytest.mark.parametrize("raw, kind", [("FCFS", "fcfs"), ("BBID_FCFS", "blind_bid_fcfs"), ("BBID", "blind_bid"),
                                       ("NONE", "none"), ("", None), (None, None)])
def test_mfl_waiver_types(raw, kind):
    assert decisions.mfl_waiver_kind(raw) == kind


def test_mfl_deadline_from_the_export():
    """Dad's league (FCFS): no claim time — a free agent is yours when MFL takes the claim; 21861 (blind bids, then FCFS):
    MFL's schedule, "see MFL"."""
    d = decisions.waivers_deadline_for(DAD, None, None, False)
    assert d["platform"] == "mfl" and d["kind"] == "fcfs" and d["runs_at"] is None and d["source"] == "MFL league export"
    assert d["words"] == "Free agents are first come, first served on MFL: a claim is yours as soon as MFL takes it."
    d = decisions.waivers_deadline_for(BBID, None, None, False)
    assert d["kind"] == "blind_bid_fcfs"
    assert d["words"] == ("Claims run on MFL's schedule for this league (blind bids, then first come, first served): "
                          "see MFL for the time.")


@needs_db
def test_the_lock_is_the_weeks_next_kickoff():
    """The lock half reads the NFL schedule: the decision week's next kickoff after now, in ET."""
    lk = decisions.next_kickoff(2026, 4, pd.Timestamp("2026-10-03 12:00", tz="UTC"))
    assert lk is not None and lk["words"].startswith("Sunday ") and lk["words"].endswith(" ET")
    d = decisions.waiver_deadline(_league(SCRUBS), season=2026, week=4, now=pd.Timestamp("2026-10-03 12:00", tz="UTC"))
    assert d["words"] == f"Claims run Wednesday 3:00 AM ET (rolling waivers); players lock at their own kickoff — the next game starts {lk['words']}."
    assert decisions.next_kickoff(2026, 4, pd.Timestamp("2026-10-07 12:00", tz="UTC")) is None    # the week is played


@needs_db
def test_waivers_answer_carries_the_deadline(client):
    """/api/waivers: Scrubs (the house path) — Sleeper's settings from the fixture; dad's league on demand — MFL's."""
    w = client.get("/api/waivers", params={"league": SCRUBS, "team": 6}).json()
    assert w["deadline"]["words"].startswith("Claims run Wednesday 3:00 AM ET (rolling waivers)")
    w = client.get("/api/waivers", params={"league": DAD, "team": 8}).json()
    assert w["deadline"]["words"].startswith("Free agents are first come, first served on MFL")


# ------------------------------------------------------------------ MFL's roster freshness
def test_the_client_keeps_the_exports_read_time():
    """``fetched_at`` = when the cached export was read (wall clock); a cache hit keeps it, a re-read after the TTL moves it."""
    mono = [100.0]
    c = M.MFL(fixtures=MFL_FX, year=2026, clock=lambda: mono[0])
    c.wall = lambda: 1_790_000_000.0
    assert c.fetched_at("rosters", "70587") is None
    c.rosters("70587")
    assert c.fetched_at("rosters", "70587") == 1_790_000_000.0
    c.wall = lambda: 1_790_000_300.0
    mono[0] += 60                                                    # within the 10-minute TTL: the cached answer
    c.rosters("70587")
    assert c.fetched_at("rosters", "70587") == 1_790_000_000.0
    mono[0] += M.TTL_S["rosters"]                                    # expired: read again
    c.rosters("70587")
    assert c.fetched_at("rosters", "70587") == 1_790_000_300.0


def test_freshness_fields_only_for_mfl():
    class Router:
        class mfl:                                                   # noqa: N801 - the router's attribute
            class client:                                            # noqa: N801
                @staticmethod
                def fetched_at(type_, lid):
                    assert (type_, lid) == ("rosters", "70587")
                    return 1_790_000_000.5
    out = ondemand.mfl_roster_freshness(Router, DAD)
    assert out == {"roster_updated_at": "2026-09-21T14:13:20+00:00", "roster_source": "MFL"}
    assert ondemand.mfl_roster_freshness(Router, SCRUBS) == {}


@needs_db
def test_my_week_says_when_mfl_was_read(client):
    """Dad's league, team 8: the answer says when the rosters export was read (just now, from the fixtures) and names
    MFL; a Sleeper league's answer has no such field (IF-4's line is unchanged)."""
    before = datetime.now(UTC).replace(microsecond=0)
    w = client.get("/api/my-week", params={"league": DAD, "team": 8}).json()
    assert w["roster_source"] == "MFL"
    t = datetime.fromisoformat(w["roster_updated_at"])
    assert before - pd.Timedelta(seconds=1) <= t <= datetime.now(UTC)
    s = client.get("/api/my-week", params={"league": SCRUBS, "team": 6}).json()
    assert "roster_updated_at" not in s and "roster_source" not in s


# ------------------------------------------------------------------ About: the grade's qualification next to the grade
def test_grade_note_words():
    n = about.grade_note(DAD, "Big Mac's league", "League of Scrubs", False)
    assert n.startswith("These grades use League of Scrubs's scoring, not Big Mac's league's")
    assert "no direct projection record for this MyFantasyLeague league" in n
    assert about.grade_note(SCRUBS, "League of Scrubs", "League of Scrubs", True) is None
    assert "keeps no projection record" in about.grade_note("9000000000000000001", "Test League", None, False)


@needs_db
def test_about_carries_the_qualification(client):
    """Dad's league: the qualification rides with the grades (About shows it under the headline grade); Scrubs: none."""
    a = client.get("/api/about", params={"league": DAD}).json()
    assert a["grades"] is not None and "no direct projection record for this MyFantasyLeague league" in a["grade_note"]
    assert client.get("/api/about", params={"league": SCRUBS}).json()["grade_note"] is None
    svelte = (ROOT / "web/src/routes/About.svelte").read_text()
    head, tail = svelte.split('data-testid="grades-answer"', 1)
    assert 'data-testid="grades-qualification"' in tail.split("grade-card", 1)[0]        # before the metrics


# ------------------------------------------------------------------ the stash writer's call
def test_the_writers_call_is_shown_as_written(monkeypatch):
    """A mart row that carries ``stash_action`` keeps it: 'watch' shows no drop and the watch line from the row's numbers;
    'claim' keeps the drop. The API does not re-decide (if1_stashes leaves writer rows alone)."""
    rows = [{"upside_rank": 1, "stash_action": "watch", "drop_cost": 30.0, "drop_cost_piece": "season_value",
             "net_weekly_gain": 2.0, "net_horizon_gain": -24.0},
            {"upside_rank": 2, "stash_action": "claim", "drop_cost": 0.0, "drop_cost_piece": None,
             "net_weekly_gain": 2.0, "net_horizon_gain": 6.0}]
    up = pd.DataFrame([{"upside_rank": 1, "add_name": "A"}, {"upside_rank": 2, "add_name": "B"}])

    def fake(q, params=()):
        if q == decisions.IG3_HAS_CALL_SQL:
            return pd.DataFrame([{"?column?": 1}])
        if q == decisions.IG3_CALL_SQL:
            return pd.DataFrame(rows)
        raise AssertionError(q)
    monkeypatch.setattr(decisions, "query", fake)
    got = decisions.ig3_with_call(up, SCRUBS, 6, 4)
    assert list(got["stash_action"]) == ["watch", "claim"]
    out = {"upside": {"stashes": [
        {"drop": {"player_name": "Marvin Harrison Jr."}, "holds_horizon_gain": 6.0,
         **decisions.ig3_stash_fields({**rows[0], "drop_name": "Marvin Harrison Jr.", "drop_sleeper_id": "11"})},
        {"drop": {"player_name": "Kaelon Black"}, "holds_horizon_gain": 6.0,
         **decisions.ig3_stash_fields({**rows[1], "drop_name": "Kaelon Black", "drop_sleeper_id": "12"})}]}}
    decisions.if1_stashes(out, pd.DataFrame(), 4, 7)
    w, c = out["upside"]["stashes"]
    assert w["stash_action"] == "watch" and w["drop"] is None and w["drop_cost"]["cost"] == 30.0
    assert w["watch_words"].startswith("Watch, no claim yet: if his role holds he adds +6.0 to your lineup over weeks 4–7")
    assert "after what dropping Harrison Jr. costs, -24.0" in w["watch_words"]
    assert c["stash_action"] == "claim" and c["drop"]["player_name"] == "Kaelon Black" and c["watch_words"] is None


def test_a_mart_before_the_call_is_left_to_the_old_path(monkeypatch):
    monkeypatch.setattr(decisions, "query", lambda q, params=(): pd.DataFrame())
    up = pd.DataFrame([{"upside_rank": 1}])
    assert decisions.ig3_with_call(up, SCRUBS, 6, 4).equals(up)
    assert decisions.ig3_stash_fields({"upside_rank": 1}) == {}


@needs_db
def test_the_clones_stash_rows_follow_choose_drops(sql):
    """On the clone after the writer ran (Wave I-G): every stash row carries the call, and its drop is the cheapest by
    the cost the moves' rows carry for the same player (``ops.waiver_moves``' pieces)."""
    has = sql("""select count(*) as n from information_schema.columns where table_schema = 'analytics'
                 and table_name = 'mart_waiver_upside' and column_name = 'stash_action'""")[0]["n"]
    if not has:
        pytest.skip("the clone's mart_waiver_upside predates the stash writer's call (the PO's view change)")
    rows = sql("select stash_action, drop_sleeper_id, open_roster_spots, net_horizon_gain, drop_cost from analytics.mart_waiver_upside")
    assert rows and all(r["stash_action"] in ("claim", "watch") for r in rows)
    assert all(r["drop_sleeper_id"] is not None or (r["open_roster_spots"] or 0) > 0 for r in rows)


# ------------------------------------------------------------------ usage retention
def test_retention_statement_in_the_hosted_file():
    text = (ROOT / "scripts/hosted_usage.sql").read_text()
    assert "delete from usage.events where at < now() - interval '180 days';" in text
    assert text.index("create table if not exists usage.events") < text.index("delete from usage.events")


@needs_db
def test_retention_keeps_six_months():
    """The file's delete on a temporary copy of the table: a row 181 days old goes, 179 days old stays (rolled back)."""
    from league_lab.config import get_settings
    stmt = next(ln for ln in (ROOT / "scripts/hosted_usage.sql").read_text().splitlines() if ln.startswith("delete from usage.events"))
    try:
        conn = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=5)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"the pipeline role is not reachable: {e}")
    with conn:
        cur = conn.cursor()
        cur.execute("create temp table events (at timestamptz not null, screen text) on commit drop")
        cur.execute("insert into events values (now() - interval '181 days', 'week'), (now() - interval '179 days', 'waivers'), (now(), 'about')")
        cur.execute(stmt.replace("usage.events", "pg_temp.events"))
        cur.execute("select screen from events order by at")
        assert [r[0] for r in cur.fetchall()] == ["waivers", "about"]
        conn.rollback()


def test_the_console_guide_names_the_usage_page():
    home = (ROOT / "app/Home.py").read_text()
    assert '("Which screens of the web app get used?", ("99_Usage.py",))' in home
    assert "older than 180 days are deleted every night" in (ROOT / "app/pages/99_Usage.py").read_text()


# ------------------------------------------------------------------ the web's e2e recordings (web/e2e/ig3)
@needs_db
@pytest.mark.skipif(not __import__("os").environ.get("IG3_RECORD"), reason="records web/fixtures/ig3/api_ig3.json: IG3_RECORD=1")
def test_record_e2e_answers(client):
    """The answers web/e2e/ig3 replays: dad's league team 8 (the MFL pick, My Week with the MFL line, Waivers with the
    FCFS line, About with the qualification), League of Scrubs roster 6's Waivers (Sleeper's Wednesday line), the status."""
    from urllib.parse import urlencode

    def key(path: str, **q) -> str:
        return path + ("?" + urlencode(sorted((k, str(v)) for k, v in q.items())) if q else "")

    out: dict = {}

    def rec(path: str, **q):
        r = client.get(key(path, **q))
        out[key(path, **q)] = {"status": r.status_code, "body": r.json()}

    rec("/api/leagues", mfl_search="70587")
    rec("/api/leagues/mfl%3A70587/rosters")
    rec("/api/my-week", league=DAD, team=8)
    rec("/api/waivers", league=DAD, team=8, position="ALL")
    rec("/api/about", league=DAD)
    rec("/api/record", league=DAD)
    rec("/api/waivers", league=SCRUBS, team=6, position="ALL")
    rec("/api/status")
    f = ROOT / "web" / "fixtures" / "ig3" / "api_ig3.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    assert all(v["status"] == 200 for v in out.values()), {k: v["status"] for k, v in out.items()}
