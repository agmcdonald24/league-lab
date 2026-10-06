"""Wave I-O, IO-2 — the League page: movement, and a link worth sharing (outlook_store.py, outlook.py § IO-2).

1. The store (``outlook.snapshots``, scripts/hosted_outlook.sql): the first build of a league-week writes; a later
   build before the week's first kickoff replaces it; after the kickoff never; without the table (or switched off)
   it is off and quiet; the daily cap on leagues nobody keeps (house leagues always); a private (ESPN / Yahoo) key is
   never stored; the row's size bound.
2. Movement from two stored weeks: places moved and the playoff odds' change, only from the stored row.
3. The guest view: every League-screen call answers with no team; ``part=power`` (no simulation) first.
4. The private league's link: an ESPN key is refused to a stranger on the League routes, never shareable, never a
   preview card even when the process holds one.
5. The page shell's card for ``/league?league=<key>``: from the last build or the stored row only, escaped, the
   default without them — and no provider call, no build (the fixture client's call count, the outlook cache).
6. The MFL timing: a league not kept every night is read without the trade market; the power part runs no
   simulation; the whole answer after it reuses the board.

Rows written here use the fixture leagues' keys and are deleted again with the owner's role (the app role cannot
delete): the store tests use made-up league keys (``9100…``) and season 2026's week 5 (first kickoff Fri 2026-10-09
00:15 UTC; the suite's pinned clock is Sat 2026-10-03, before it).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient

from league_lab_api import outlook as O
from league_lab_api import outlook_store as S
from league_lab_api import ratelimit
from league_lab_api.main import app
from league_lab_api.settings import ROOT

from .conftest import SCRUBS, needs_db

BEFORE = datetime(2026, 10, 3, 16, 0, tzinfo=UTC)          # the pinned clock: week 5 not kicked off
AFTER = datetime(2026, 10, 10, 16, 0, tzinfo=UTC)          # week 5 under way
FAKE = [f"91000000000000000{i:02d}" for i in range(10)]


def _owner():
    from league_lab.config import get_settings
    return psycopg.connect(get_settings().pipeline_dsn(), autocommit=True)


def _store_ready() -> bool:
    S.reset()
    return S.ready()


needs_store = pytest.mark.skipif(not _store_ready(), reason="outlook.snapshots not applied (scripts/hosted_outlook.sql)")


def _clean(*keys: str) -> None:
    with _owner() as c:
        c.execute("delete from outlook.snapshots where league_key = any(%s)", (list(keys),))


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv(S.ENV, raising=False)
    O._cache.clear()
    O._schedules.clear()
    S.reset()
    yield
    S.flush()
    O._cache.clear()
    O._schedules.clear()
    S.reset()


@pytest.fixture
def api(monkeypatch):
    for k in ("LEAGUE_LAB_APP_PASSWORD", "LEAGUE_LAB_API_SECRET", "LEAGUE_LAB_GATE"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(app) as c:
        yield c


def _row(key: str, *, week: int = 5, teams: int = 4, per_week: float = 100.0, name: str = "Test league",
         team: str | None = None) -> dict:
    ans = {"league_id": key, "season": 2026, "version": "ol1.0",
           "power": {"rows": [{"roster_id": r, "rank": r, "per_week": per_week - r, "team_name": team or f"Team {r}"}
                              for r in range(1, teams + 1)]},
           "outlook": {"rows": [{"roster_id": r, "wins_mean": 7.5, "playoff": 0.5, "top_seed": 0.25}
                                for r in range(1, teams + 1)]}}
    return S.snapshot(ans, league_name=name, week=week, built_at=BEFORE)


def _stored(key: str) -> list[dict]:
    with _owner() as c, c.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("select * from outlook.snapshots where league_key = %s order by week", (key,))
        return cur.fetchall()


# ================================================================================================== 1. the store
@needs_db
@needs_store
def test_first_build_writes_a_later_build_replaces_until_kickoff_then_never():
    key = FAKE[0]
    _clean(key)
    try:
        assert S.offer(_row(key, per_week=100.0), house=True, now=BEFORE) == "queued"
        S.flush()
        got = _stored(key)
        assert len(got) == 1 and got[0]["kind"] == "house" and got[0]["power"][0]["per_week"] == 99.0
        assert got[0]["closes_at"] == datetime(2026, 10, 9, 0, 15, tzinfo=UTC)          # week 5's first kickoff
        assert S.offer(_row(key, per_week=120.0), house=True, now=BEFORE) == "queued"     # before kickoff: replaced
        S.flush()
        assert _stored(key)[0]["power"][0]["per_week"] == 119.0
        assert S.offer(_row(key, per_week=140.0), house=True, now=AFTER) == "closed"      # after: never offered
        # and the table's own rule, if a row reached the writer late (queued before the kickoff, written after)
        item = {**_row(key, per_week=160.0), "power": "[]", "rows": "[]", "kind": "house", "now": AFTER,
                "closes_at": datetime(2026, 10, 9, 0, 15, tzinfo=UTC)}
        assert S.write(item) == "closed"
        assert _stored(key)[0]["power"][0]["per_week"] == 119.0
    finally:
        _clean(key)


@needs_db
def test_without_the_table_the_store_is_off_and_the_outlook_answers_as_before(api, monkeypatch):
    """Rule 10: the deploy lands before the nightly applies hosted_outlook.sql — no arrows, no write, no error."""
    monkeypatch.setattr(S, "READY_SQL", "select coalesce(has_table_privilege(to_regclass('outlook.no_such_table'), "
                                         "'insert'), false)")
    S.reset()
    assert not S.ready()
    assert S.offer(_row(FAKE[1]), house=True, now=BEFORE) == "off"
    assert S.stored(SCRUBS, 2026, 4) == {"prev": None, "current": False}
    d = api.get(f"/api/league/outlook?league={SCRUBS}&team=2")
    assert d.status_code == 200
    j = d.json()
    assert j["power"]["movement"] is None and j["power"]["movement_note"] == O.NO_ARROWS
    assert all(r["moved"] is None for r in j["power"]["rows"]) and j["power"]["kept"] == "off"
    assert j["shareable"] is True and j["league_name"] == "League of Scrubs"
    # the link and its preview still work: the card from this process's build
    assert S.card(SCRUBS)["name"] == "League of Scrubs"
    # switched off by name: the same
    monkeypatch.setenv(S.ENV, "off")
    S.reset()
    assert not S.ready() and S.offer(_row(FAKE[1]), house=True, now=BEFORE) == "off"


@needs_db
@needs_store
def test_the_daily_cap_on_leagues_nobody_keeps(monkeypatch):
    monkeypatch.setattr(S, "NEW_PER_DAY", 2)
    keys = FAKE[2:7]
    _clean(*keys)
    try:
        for k in keys[:3]:
            assert S.offer(_row(k), house=False, now=BEFORE) == "queued"
        S.flush()
        assert [bool(_stored(k)) for k in keys[:3]] == [True, True, False]          # the third new league: capped
        assert S.stats["capped"] >= 1
        assert all(_stored(k)[0]["kind"] == "visitor" for k in keys[:2])
        # a league already kept is not new: its next week still writes
        assert S.offer(_row(keys[0], week=6), house=False, now=BEFORE) == "queued"
        # a house league always
        assert S.offer(_row(keys[3]), house=True, now=BEFORE) == "queued"
        S.flush()
        assert len(_stored(keys[0])) == 2 and _stored(keys[3])[0]["kind"] == "house"
        # the total held: past VISITOR_MAX nothing new either
        monkeypatch.setattr(S, "NEW_PER_DAY", 100)
        monkeypatch.setattr(S, "VISITOR_MAX", 2)
        assert S.offer(_row(keys[4]), house=False, now=BEFORE) == "queued"
        S.flush()
        assert not _stored(keys[4])
    finally:
        _clean(*keys)


@needs_db
@needs_store
def test_a_private_league_is_never_stored_and_the_row_is_bounded():
    for key in ("espn:5150", "yahoo:461.l.4242", "ref:half"):
        assert not S.shareable(key)
        assert S.offer({**_row(FAKE[0]), "league_key": key}, house=False, now=BEFORE) == "private"
    assert S.shareable(SCRUBS) and S.shareable("mfl:70587") and S.shareable(" MFL:70587 ")
    big = _row(FAKE[8], teams=32, team="W" * 200)           # every name cut to NAME_MAX
    assert all(len(p["team_name"]) == S.NAME_MAX for p in big["power"])
    size = len(json.dumps(big["power"], separators=(",", ":"))) + len(json.dumps(big["rows"], separators=(",", ":")))
    assert size <= S.MAX_BYTES                               # the largest league the outlook simulates fits
    huge = {**big, "power": big["power"] * 3}
    assert S.offer(huge, house=True, now=BEFORE) == "too_big"


# ========================================================================================== 2. movement, stored
def _seed_prev(key: str, season: int, week: int, power: list[dict], rows: list[dict], name: str = "League of Scrubs"):
    with _owner() as c:
        c.execute("""insert into outlook.snapshots (league_key, season, week, kind, league_name, model_version, built_at,
                                                     closes_at, teams, power, rows)
                     values (%s, %s, %s, 'house', %s, 'ol1.0', %s, %s, %s, %s::jsonb, %s::jsonb)""",
                  (key, season, week, name, datetime(2026, 9, 29, 12, tzinfo=UTC), datetime(2026, 9, 25, 0, 15, tzinfo=UTC),
                   len(power), json.dumps(power), json.dumps(rows)))


@needs_db
@needs_store
def test_movement_comes_from_last_weeks_stored_row_only(api):
    _clean(SCRUBS)
    try:
        cold = api.get(f"/api/league/outlook?league={SCRUBS}&team=2").json()
        week = cold["week"]
        assert cold["power"]["movement"] is None and all(r["moved"] is None for r in cold["power"]["rows"])
        assert cold["power"]["kept"] == "closed"            # the pinned Saturday: this week has kicked off
        assert cold["power"]["movement_note"] == O.WAIT_NOTE
        rows = cold["power"]["rows"]
        # last week: the order reversed, every team at 50% playoff odds
        prev = [{"roster_id": r["roster_id"], "rank": len(rows) + 1 - r["rank"], "per_week": 100.0, "team_name": "x"}
                for r in rows]
        _seed_prev(SCRUBS, cold["season"], week - 1, prev, [{"roster_id": r["roster_id"], "playoff": 0.5} for r in rows])
        O._cache.clear()
        d = api.get(f"/api/league/outlook?league={SCRUBS}&team=2").json()
        assert d["power"]["movement"]["week"] == week - 1
        assert d["power"]["movement_note"] == O.MOVED_NOTE.format(week=week - 1)
        for r in d["power"]["rows"]:
            assert r["moved"] == (len(rows) + 1 - r["rank"]) - r["rank"]
        for o in d["outlook"]["rows"]:
            assert o["playoff_change"] == round((o["playoff"] - 0.5) * 100)
        # a team missing from last week's row: no arrow (never a guess)
        _clean(SCRUBS)
        _seed_prev(SCRUBS, cold["season"], week - 1, prev[1:], [])
        O._cache.clear()
        d = api.get(f"/api/league/outlook?league={SCRUBS}&team=2").json()
        missing = {r["roster_id"]: r["moved"] for r in d["power"]["rows"]}[prev[0]["roster_id"]]
        assert missing is None and all(o["playoff_change"] is None for o in d["outlook"]["rows"])
        # this week's row stored, last week's not: "from next week"
        _clean(SCRUBS)
        _seed_prev(SCRUBS, cold["season"], week, prev, [])
        O._cache.clear()
        d = api.get(f"/api/league/outlook?league={SCRUBS}&team=2").json()
        assert d["power"]["movement"] is None and d["power"]["movement_note"] == O.FIRST_NOTE
    finally:
        _clean(SCRUBS)


# ============================================================================================ 3. the guest view
@needs_db
def test_every_league_screen_call_answers_with_no_team(api):
    for path in ("/api/league", "/api/league/week-odds", "/api/league/outlook"):
        r = api.get(path, params={"league": SCRUBS})
        assert r.status_code == 200, (path, r.text[:200])
    o = api.get("/api/league/outlook", params={"league": SCRUBS}).json()
    assert o["roster_id"] is None and not any(r["mine"] for r in o["power"]["rows"])
    assert not any(r["mine"] for r in o["outlook"]["rows"])
    # the reference key still needs a league; part is a closed set
    assert api.get("/api/league/outlook", params={"league": "ref:half"}).json()["code"] == "needs_league"
    assert api.get("/api/league/outlook", params={"league": SCRUBS, "part": "season"}).status_code == 400
    assert ratelimit.bucket_for("GET", "/api/league/outlook", "league=1&part=power") == "heavy"


@needs_db
def test_the_power_part_runs_no_simulation_and_the_whole_answer_follows(api):
    O.D.clear_memo()
    p = api.get("/api/league/outlook", params={"league": "mfl:70587", "part": "power"}).json()
    assert p["outlook"]["pending"] is True and p["outlook"]["rows"] == [] and len(p["power"]["rows"]) == 12
    assert "simulation_ms" not in p["timings_ms"] and p["power"]["kept"] is None       # the power part keeps nothing
    ctx = O.D._memo_cache.get(("outlook_context", "mfl:70587"))
    assert ctx is not None and ctx.points == {}               # the market-free context (no free agents priced)
    assert O.D._memo_cache.get(("trade_context", "mfl:70587", False)) is None
    f = api.get("/api/league/outlook", params={"league": "mfl:70587"}).json()
    assert not f["outlook"].get("pending") and f["timings_ms"]["board_ms"] < 200      # the board kept from the part
    assert [r["roster_id"] for r in f["power"]["rows"]] == [r["roster_id"] for r in p["power"]["rows"]]
    # the power part after the whole answer: the whole answer (one build, nothing pending)
    again = api.get("/api/league/outlook", params={"league": "mfl:70587", "part": "power"}).json()
    assert not again["outlook"].get("pending")


# ================================================================================== 4. the private league's link
def test_a_private_espn_league_shows_nothing_to_a_stranger(api, monkeypatch):
    from league_lab import anyleague as A
    from league_lab import platforms as P
    monkeypatch.setenv("LEAGUE_LAB_GATE", "open")
    monkeypatch.setenv(P.STUBS_ENV, "1")
    monkeypatch.delenv("LEAGUE_LAB_ESPN_PRIVATE", raising=False)
    A._default = None
    try:
        for path, params in (("/api/league/outlook", {"league": "espn:5150"}), ("/api/league", {"league": "espn:5150"}),
                             ("/api/league/outlook", {"league": "espn:5150", "part": "power"})):
            r = api.get(path, params=params)
            assert r.status_code == 404 and r.json().get("code") == "espn_league_private", (path, r.text[:200])
    finally:
        A._default = None
    # even when this process holds a card for it (an owner opened it), the link's preview is the default
    S._cards.put("espn:5150", {"name": "Secret", "week": 5, "top": [{"team": "A", "per_week": 1.0, "playoff": None}]})
    assert S.card("espn:5150") is None and O.preview("espn:5150") is None
    assert O.preview("yahoo:461.l.4242") is None and O.preview("ref:half") is None


# =================================================================================== 5. the page shell's card
@pytest.fixture
def dist(tmp_path, monkeypatch):
    d = tmp_path / "dist"
    d.mkdir()
    (d / "index.html").write_text((ROOT / "web" / "index.html").read_text())
    monkeypatch.setenv("LEAGUE_LAB_WEB_DIST", str(d))
    return d


def _meta(text: str, prop: str) -> str | None:
    m = re.search(rf'<meta (?:property|name)="{re.escape(prop)}" content="([^"]*)"', text)
    return m.group(1) if m else None


@needs_db
def test_the_league_links_card_comes_from_the_cache_and_never_calls_a_provider(api, dist):
    from league_lab import anyleague as A
    calls = A.sleeper().calls
    t = api.get("/league", params={"league": SCRUBS}).text
    assert _meta(t, "og:title") == "isuckatfantasy" and t == (dist / "index.html").read_text()   # nothing kept: default
    assert A.sleeper().calls == calls and len(O._cache) == 0                     # no provider call, no build
    o = api.get(f"/api/league/outlook?league={SCRUBS}&team=2").json()
    calls = A.sleeper().calls
    builds = len(O._cache)
    t = api.get("/league", params={"league": SCRUBS}).text
    assert A.sleeper().calls == calls and len(O._cache) == builds
    week = o["week"]
    assert f"<title>League of Scrubs: power rankings, week {week}</title>" in t
    top = o["power"]["rows"][:3]
    desc = _meta(t, "og:description")
    assert desc.startswith(f"1. {top[0]['team_name']} {top[0]['per_week']:.1f}")
    assert f"3. {top[2]['team_name']}" in desc and "4. " not in desc
    assert _meta(t, "og:url") == f"https://isuckatfantasy.io/league?league={SCRUBS}"
    assert t.count("<title>") == 1 and t.count('property="og:title"') == 1
    # a padded or odd spelling is the same league; junk is the default
    assert "power rankings" in api.get("/league", params={"league": f" {SCRUBS} "}).text
    for junk in ('"><script>alert(1)</script>', "../../etc/passwd", "1" * 400, "espn:5150", "ref:half"):
        assert _meta(api.get("/league", params={"league": junk}).text, "og:title") == "isuckatfantasy", junk


@needs_db
@needs_store
def test_the_card_from_the_stored_row_alone_is_escaped(api, dist):
    key = FAKE[9]
    _clean(key)
    try:
        power = [{"roster_id": 1, "rank": 1, "per_week": 121.25, "team_name": '"><script>alert(1)</script>'},
                 {"roster_id": 2, "rank": 2, "per_week": 110.0, "team_name": "Two & <b>Two</b>"}]
        _seed_prev(key, 2026, 5, power, [{"roster_id": 1, "playoff": 0.84}, {"roster_id": 2, "playoff": None}],
                   name="Night <League>")
        t = api.get("/league", params={"league": key}).text
        assert "<script>alert" not in t and "<b>Two" not in t
        assert "<title>Night &lt;League&gt;: power rankings, week 5</title>" in t
        assert _meta(t, "og:description").startswith("1. &quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt; 121.2 (84% playoffs)")
        # the stored row is read once, then kept (a crawler's repeated hit does not repeat the query)
        assert S._card_reads.get(key, "miss") != "miss"
    finally:
        _clean(key)


# ================================================================================================ 7. title odds
def test_the_bracket_order_and_rounds():
    assert O.bracket_order(4) == [1, 4, 2, 3] and O.bracket_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    assert O.bracket_rounds({"playoff_week_start": 15, "playoff_round_type": 0}, 6) == [[15], [16], [17]]
    assert O.bracket_rounds({"playoff_week_start": 15, "playoff_round_type": 1}, 4) == [[15], [16, 17]]
    assert O.bracket_rounds({"playoff_week_start": 14, "playoff_round_type": 2}, 4) == [[14, 15], [16, 17]]
    weeks = set(range(5, 18))
    b, why = O.title_bracket({"playoff_week_start": 15, "playoff_teams": 6, "playoff_seed_type": 1}, "sleeper", weeks)
    assert why is None and b == {"rounds": [[15], [16], [17]], "reseed": True}
    assert O.title_bracket({"playoff_week_start": 15, "playoff_teams": 6}, "mfl", weeks)[0] is None
    assert O.title_bracket({"playoff_week_start": 15, "playoff_teams": 6, "divisions": 2}, "sleeper", weeks)[0] is None
    b, why = O.title_bracket({"playoff_week_start": 15, "playoff_teams": 6}, "sleeper", set(range(5, 17)))
    assert b is None and "week 17" in why


def test_the_bracket_is_reseeded_or_fixed_as_the_settings_say():
    """Six teams (index = seed − 1 by wins). Round 1: 6 beats 3, 4 beats 5. Re-seeded: 1 meets 6 and 2 meets 4 (as the
    house dynasty's 2022, 2024 and 2025 brackets paired); fixed: 1 meets the 4–5 winner, 2 the 3–6 winner."""
    wins = np.array([[10.0, 9, 8, 7, 6, 5]])
    pf = np.zeros((1, 6))
    pts = np.zeros((1, 6, 3))
    pts[0, :, 0] = [0, 0, 10, 20, 10, 20]            # round 1: 3 v 6 → 6; 4 v 5 → 4 (1 and 2 on byes)
    pts[0, :, 1] = [15, 15, 0, 30, 0, 5]             # round 2
    pts[0, :, 2] = [50, 0, 0, 10, 0, 0]              # the final
    rounds = {"rounds": [[15], [16], [17]]}
    assert O.play_bracket(wins, pf, pts, {**rounds, "reseed": True}, 6).tolist() == [0]    # 1 v 6, 2 v 4 → 1 v 4 → 1
    assert O.play_bracket(wins, pf, pts, {**rounds, "reseed": False}, 6).tolist() == [3]   # 1 v 4, 2 v 6 → 4 v 2 → 4
    # a tie goes to the higher seed
    tie = np.zeros((1, 4, 2))
    assert O.play_bracket(np.array([[4.0, 3, 2, 1]]), np.zeros((1, 4)), tie, {"rounds": [[15], [16]], "reseed": False}, 4).tolist() == [0]


def test_title_odds_add_up_and_a_certain_team_wins_it():
    teams, weeks, pw = [1, 2, 3, 4], [5, 6, 7, 8, 9, 10], [11, 12]
    games = {w: [(1, 2), (3, 4)] if i % 3 == 0 else [(1, 3), (2, 4)] if i % 3 == 1 else [(1, 4), (2, 3)]
             for i, w in enumerate(weeks)}
    mean = {(t, w): (300.0 if t == 1 else 100.0) for t in teams for w in [*weeks, *pw]}
    res = O.simulate(teams, weeks, mean, {t: 0.05 for t in teams}, {t: 100.0 for t in teams}, games,
                     {t: 0.0 for t in teams}, {t: 0.0 for t in teams}, 4, 0, n=2000,
                     bracket={"rounds": [[11], [12]], "reseed": False})
    titles = [res["teams"][t]["title"] for t in teams]
    assert abs(sum(titles) - 1.0) < 1e-3 and res["teams"][1]["title"] == 1.0
    res = O.simulate(teams, weeks, mean, {t: 0.05 for t in teams}, {t: 100.0 for t in teams}, games,
                     {t: 0.0 for t in teams}, {t: 0.0 for t in teams}, 2, 0, n=500)
    assert res["teams"][1]["title"] is None                                    # no bracket: no title odds


@needs_db
def test_title_odds_on_the_house_leagues_and_none_for_mfl(api):
    s = api.get(f"/api/league/outlook?league={SCRUBS}&team=2").json()["outlook"]
    assert s["title"] and s["bracket"] == {"rounds": [[15], [16]], "reseed": False}
    assert abs(sum(r["title"] for r in s["rows"]) - 1.0) < 2e-3
    assert all(r["title"] <= r["playoff"] + 1e-9 for r in s["rows"])
    d = api.get("/api/league/outlook?league=1321941740235550720&team=12").json()["outlook"]
    assert d["title"] and d["bracket"]["reseed"] is True and len(d["bracket"]["rounds"]) == 3     # 6 teams, re-seeded
    m = api.get("/api/league/outlook?league=mfl:70587").json()["outlook"]
    assert not m["title"] and all(r["title"] is None for r in m["rows"])
