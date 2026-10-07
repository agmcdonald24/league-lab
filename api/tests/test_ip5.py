"""Wave I-P, IP-5 — robustness and reach.

1. A refused provider read is never remembered as "nothing there" (``league_lab.provider_trouble``; SECURITY_PUBLIC
   § 15): every cache on a request path that stores a provider read, refused / failed / nonsense, then the next reader.
2. MFL's League screen, first content under 2 s cold, the same numbers (``test_mfl_*``).
3. The "best corners" split, as-of (``test_corners_*``).
4. Player pages that share: the shell's meta from cache only, the sitemap, ``noindex`` (``test_player_shell_*``).
"""

from __future__ import annotations

import contextvars
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import memo
from league_lab import provider_trouble as PT
from league_lab.mfl_client import MFL, MFLBusy, MFLUnavailable
from league_lab.sleeper_client import Sleeper, SleeperBusy, SleeperUnavailable, TokenBucket

from league_lab_api import availability, db
from league_lab_api import decisions as D

from .conftest import needs_db

ON_DEMAND = "9000000000000000001"             # the fixtures' Sleeper league the database does not keep


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class _Empty(TokenBucket):
    """A bucket that refuses every call (everyone's budget spent)."""

    def take(self, n: float = 1.0) -> bool:
        self.refused += 1
        return False


# ------------------------------------------------------------------ 1a. the clients: nonsense is a failure, held answers win
def test_sleeper_an_empty_directory_is_a_failure_never_kept():
    answers = [{}, {"4046": {"player_id": "4046", "full_name": "Patrick Mahomes", "position": "QB", "team": "KC"}}]
    sl = Sleeper(fetch=lambda path: answers.pop(0), bucket=TokenBucket(1000), cache_path=None)
    with PT.watch() as w, pytest.raises(SleeperUnavailable):
        sl.players()
    assert w.failed == 1 and "/players/nfl" not in sl._cache            # nothing kept as "nobody there"
    assert sl.players()["4046"]["full_name"] == "Patrick Mahomes"      # the next reader: the real directory


def test_sleeper_a_null_roster_answer_serves_the_held_rosters():
    clk = _Clock()
    answers = [[{"roster_id": 1, "players": ["4046"]}], None]
    sl = Sleeper(fetch=lambda path: answers.pop(0), bucket=TokenBucket(1000), clock=clk, cache_path=None)
    assert sl.rosters("1111111111")[0]["players"] == ["4046"]
    clk.t += 3600                                                      # past the 10-minute TTL
    with PT.watch() as w:
        got = sl.rosters("1111111111")                                 # Sleeper sent an empty body: the held one
    assert got[0]["players"] == ["4046"] and w.clean and sl.stale_served == 1


def test_sleeper_a_refusal_with_nothing_held_is_noted_and_busy():
    sl = Sleeper(fetch=lambda path: [], bucket=_Empty(1), cache_path=None)
    with PT.watch() as w, pytest.raises(SleeperBusy):
        sl.rosters("1111111111")
    assert w.busy == 1 and w.failed == 0


def test_the_directory_disk_copy_of_any_age_answers_a_refusal(tmp_path):
    import json
    f = tmp_path / "sleeper_players_nfl.json"
    f.write_text(json.dumps({"4046": {"player_id": "4046", "full_name": "Patrick Mahomes", "position": "QB"}}))
    old = time.time() - 3 * 86400
    os.utime(f, (old, old))                                            # three days old: past the day's TTL
    sl = Sleeper(fetch=lambda path: {}, bucket=_Empty(1), cache_path=tmp_path)
    with PT.watch() as w:
        d = sl.players()
    assert d["4046"]["full_name"] == "Patrick Mahomes" and w.clean    # the last good copy, not an empty directory


def test_mfl_an_empty_body_is_a_failure_never_kept():
    answers = [("https://api.myfantasyleague.com/x", ""),
               ("https://api.myfantasyleague.com/x", '{"players": {"player": [{"id": "13604", "name": "Nacua, Puka"}]}}')]
    m = MFL(fetch=lambda url: answers.pop(0), bucket=TokenBucket(1000), year=2026)
    with PT.watch() as w, pytest.raises(MFLUnavailable):
        m.players()
    assert w.failed == 1 and not m._cache
    assert m.players()[0]["name"] == "Nacua, Puka"


def test_mfl_an_http_429_serves_the_held_answer():
    clk = _Clock()
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) > 1:
            m._backoff_until = 0.0
            raise MFLBusy("busy, try again in a minute")              # what ``_http`` raises on a 429
        return url, '{"players": {"player": [{"id": "13604", "name": "Nacua, Puka"}]}}'
    m = MFL(fetch=fetch, bucket=TokenBucket(1000), year=2026, clock=clk)
    m.players()
    clk.t += 2 * 86400
    with PT.watch() as w:
        assert m.players()[0]["id"] == "13604"                         # was: MFLBusy raised past a held answer
    assert w.clean and m.stale_served == 1


def test_mfl_translate_refused_is_busy_never_an_unmapped_player():
    from league_lab import platforms

    class Refusing:
        year = 2026
        hosts: dict = {}

        def players(self, ids=None):
            PT.note("busy")
            raise MFLBusy("busy, try again in a minute")
    mf = platforms.MFLLeagues(Refusing(), lambda: {})
    with pytest.raises(MFLBusy):
        mf.translate("70587", ["99999"])                               # an id the table cannot map: needs MFL's info
    assert mf.mapping == {} and mf.extra_players == {}                 # nothing remembered as "MFL player 99999"


# ------------------------------------------------------------------ 1b. the watch and kept()
def test_a_watch_counts_in_a_pool_that_carries_the_context_and_nested_watches_both_count():
    with PT.watch() as outer:
        with PT.watch() as inner:
            ctx = contextvars.copy_context()
            with ThreadPoolExecutor(2) as ex:
                list(ex.map(lambda k: ctx.copy().run(PT.note, k), ["busy", "failed"]))
        assert (inner.busy, inner.failed) == (1, 1)
    assert (outer.busy, outer.failed) == (1, 1) and not outer.clean
    with PT.watch() as after:
        pass
    assert after.clean


def test_kept_never_keeps_a_troubled_build_and_serves_the_held_one():
    region = memo.Budget(64).region("ip5_test", ttl=60)
    clk = _Clock()
    trouble = {"on": True}

    def build():
        if trouble["on"]:
            PT.note("busy")                                            # a refusal swallowed below ("no opponent")
            return {"lineup": []}
        return {"lineup": ["Mahomes"]}
    with pytest.raises(SleeperBusy):                                   # nothing held: busy, never the empty lineup
        PT.kept(region, "k", build, ttl=60, stamp="s1", clock=clk)
    assert region.get("k") is None
    trouble["on"] = False
    assert PT.kept(region, "k", build, ttl=60, stamp="s1", clock=clk) == {"lineup": ["Mahomes"]}
    trouble["on"] = True
    clk.t += 120                                                       # past its TTL (and a new stamp)
    with PT.watch() as outer:
        got = PT.kept(region, "k", build, ttl=60, stamp="s2", clock=clk)
    assert got == {"lineup": ["Mahomes"]} and outer.clean              # the last good one; the outer cache keeps it
    assert region.get("k")[0] == "s1"                                  # the troubled build replaced nothing


def test_the_decisions_memo_keeps_nothing_built_in_trouble():
    D.clear_memo()
    key = ("ip5_test", "x")

    def troubled():
        PT.note("failed")
        return "half an answer"
    with pytest.raises(SleeperBusy):
        D._memo(key, False, troubled)
    assert D._memo_cache.get(key) is None
    assert D._memo(key, False, lambda: "the answer") == "the answer"
    assert D._memo_cache.get(key) == "the answer"
    D.clear_memo()


# ------------------------------------------------------------------ 1c. the caches on the request path (fixtures + database)
@needs_db
def test_the_roster_context_is_not_kept_from_a_troubled_build_and_the_next_reader_gets_it(monkeypatch):
    availability.clear_context()
    real = availability.apply_to_rows
    hits = {"n": 0}

    def troubled(*a, **k):                                             # the overlay's directory read refused
        hits["n"] += 1
        PT.note("busy")
        return real(*a, **k)
    monkeypatch.setattr(availability, "apply_to_rows", troubled)
    with pytest.raises(SleeperBusy):
        availability.roster_context(ON_DEMAND, 1, 4, house=False)
    assert len(availability._ctx_cache) == 0                           # nothing kept for the next manager
    monkeypatch.setattr(availability, "apply_to_rows", real)
    ctx = availability.roster_context(ON_DEMAND, 1, 4, house=False)
    assert ctx is not None and len(ctx.players()) > 5 and len(availability._ctx_cache) == 1
    # a new stamp (the nightly rebuilt) and a troubled rebuild: the held context, with its own stamps
    monkeypatch.setattr(availability, "build_time", lambda: pd.Timestamp("2026-10-03T12:00:00Z").to_pydatetime())
    monkeypatch.setattr(availability, "apply_to_rows", troubled)
    again = availability.roster_context(ON_DEMAND, 1, 4, house=False)
    assert again is ctx and hits["n"] == 2


@needs_db
def test_league_weeks_and_rest_of_season_keep_nothing_built_in_trouble(monkeypatch):
    A.clear_league_weeks()
    real = A.league_inputs

    def troubled(*a, **k):
        PT.note("busy")
        return real(*a, **k)
    monkeypatch.setattr(A, "league_inputs", troubled)
    A.league_weeks(db.query, ON_DEMAND, 4)
    assert len(A._league_weeks) == 0
    monkeypatch.setattr(A, "league_inputs", real)
    lw = A.league_weeks(db.query, ON_DEMAND, 4)
    assert lw.rows and len(A._league_weeks) == 1
    # rest of season: a unit's name read refused (MFL) -> busy, nothing kept; then kept
    real_ros = A._ros_table

    def troubled_ros(*a, **k):
        PT.note("busy")
        return real_ros(*a, **k)
    A._ros_cache.clear()
    monkeypatch.setattr(A, "_ros_table", troubled_ros)
    lg = A.sleeper().league(ON_DEMAND)
    with pytest.raises(SleeperBusy):
        A.ros_table(db.query, ON_DEMAND, lg, 5, 17, None)
    assert len(A._ros_cache) == 0
    monkeypatch.setattr(A, "_ros_table", real_ros)
    assert not A.ros_table(db.query, ON_DEMAND, lg, 5, 17, None).empty and len(A._ros_cache) == 1


@needs_db
def test_my_week_refused_answers_busy_then_the_next_reader_gets_the_lineup(client, monkeypatch):
    from league_lab import sleeper_client
    real = sleeper_client.Sleeper.players
    state = {"refuse": True}

    def players(self):
        if state["refuse"]:
            PT.note("busy")
            raise SleeperBusy("busy, try again in a minute")
        return real(self)
    monkeypatch.setattr(sleeper_client.Sleeper, "players", players)
    r = client.get(f"/api/my-week?league={ON_DEMAND}&team=1")
    assert r.status_code == 503 and r.json()["code"] == "busy"         # never a 500, never an empty roster
    state["refuse"] = False
    r = client.get(f"/api/my-week?league={ON_DEMAND}&team=1")
    assert r.status_code == 200 and len(r.json()["lineup"]) > 5


@needs_db
def test_mfl_a_refused_id_lookup_is_busy_then_the_full_roster(client, monkeypatch):
    real = MFL.players
    state = {"refuse": True}

    def players(self, ids=None):
        if state["refuse"] and ids:
            PT.note("busy")
            raise MFLBusy("busy, try again in a minute")
        return real(self, ids)
    monkeypatch.setattr(MFL, "players", players)
    r = client.get("/api/my-week?league=mfl:70587&team=1")
    assert r.status_code == 503 and r.json()["code"] == "busy"
    state["refuse"] = False
    r = client.get("/api/my-week?league=mfl:70587&team=1")
    assert r.status_code == 200
    names = [x.get("player_name") or "" for x in r.json()["lineup"]]
    assert names and not any(n.startswith("MFL player") for n in names)


def test_the_injury_feed_keeps_its_held_copy_over_an_empty_answer(tmp_path):
    from league_lab import injury_feed as F
    answers = [{"timestamp": "2026-10-03T12:00:00Z", "injuries": []}]
    fd = F.InjuryFeed(fetch=lambda url: answers[0], cache_path=tmp_path / "inj.json", background=False)
    fd._data = {"fetched_at": 0.0, "source_timestamp": None,
                "entries": [{"espn_id": "4262921", "name": "Justin Jefferson", "status": "Out"}]}
    d = fd.snapshot()
    assert d["entries"] and d["entries"][0]["name"] == "Justin Jefferson" and fd.failures == 1


def test_the_news_feed_keeps_its_held_items_over_an_empty_body():
    from league_lab import news_feed as N
    fd = N.NewsFeed(fetch=lambda url: {})
    held = {"fetched_at": 0.0, "as_of": None, "items": [{"headline": "Nacua returns to practice"}]}
    fd._mem["4426515"] = held
    assert fd.copy("4426515") is held and fd.failures == 1


# ------------------------------------------------------------------ 2. MFL's League screen: the same numbers, faster
def _unit_lines_loop(b, proj):
    """``unit_lines``' starter rule as main had it (one team at a time): the reference for the vectorised pass."""
    from league_lab.anyleague import STAT_LINE, UNIT_SKIP_STATUS
    qb = b.line[b.line["position"] == "QB"]
    st = b.status.reindex(qb.index)
    out_ = st["report_status"].isin(UNIT_SKIP_STATUS) | st["roster_status"].eq("RES")
    rank = proj.reindex(qb.index).astype(float).fillna(-1e9)
    num = qb[list(STAT_LINE)].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    rows = {}
    for t, idx in qb.groupby(st["team"]).groups.items():
        if not isinstance(t, str) or not t:
            continue
        keep = [g for g in idx if not out_.get(g, False)] or list(idx)
        starter = rank.loc[keep].idxmax()
        rows[t] = {"position": "TMQB", **num.loc[[starter]].sum().to_dict(), "starter_gsis": starter, "n_players": 1}
    return pd.DataFrame.from_dict(rows, orient="index", columns=["position", *STAT_LINE, "starter_gsis", "n_players"])


def test_unit_lines_vectorised_is_the_loop_to_the_bit():
    from types import SimpleNamespace

    import numpy as np
    from league_lab.anyleague import STAT_LINE, unit_lines
    rng = np.random.default_rng(5)
    ids = [f"00-00{i:05d}" for i in range(60)]
    teams = ["KC", "BUF", "DET", None, "", "SF"] * 10
    line = pd.DataFrame({c: rng.uniform(0, 300, 60).round(3) for c in STAT_LINE}, index=ids)
    line["position"] = ["QB"] * 50 + ["RB"] * 10
    line.iloc[3, 0] = np.nan                                           # a missing stat: 0
    status = pd.DataFrame({"team": teams, "report_status": rng.choice([None, "Out", "Questionable", "Doubtful"], 60),
                           "roster_status": rng.choice(["ACT", "RES"], 60), "player_name": ids}, index=ids)
    status.loc[[i for i, t in zip(ids, teams, strict=True) if t == "SF"], "report_status"] = "Out"   # all out: all kept
    proj = pd.Series(rng.choice([10.0, 12.5, 12.5, np.nan], 60), index=ids)                          # ties and NaN
    b = SimpleNamespace(line=line, status=status)
    got, want = unit_lines(b, proj), _unit_lines_loop(b, proj)
    pd.testing.assert_frame_equal(got, want, check_dtype=False)
    assert list(got.index) == sorted(got.index) and got["starter_gsis"].notna().all()


# ------------------------------------------------------------------ 3. the "best corners" split
@needs_db
def test_corners_the_look_ahead_split_is_gone_and_the_page_still_stands(client):
    from .conftest import SCRUBS
    r = client.get(f"/api/matchups/cb?league={SCRUBS}&team=2")
    assert r.status_code == 200
    rows = r.json()["matchups"]
    assert all(m.get("cover_split") is None for m in rows)
    assert "season to date" not in r.text                               # the look-ahead note went with it


# ------------------------------------------------------------------ 4. player pages that share
@pytest.fixture
def dist(tmp_path, monkeypatch):
    from league_lab_api.settings import ROOT
    d = tmp_path / "dist"
    d.mkdir()
    (d / "index.html").write_text((ROOT / "web" / "index.html").read_text())
    monkeypatch.setenv("LEAGUE_LAB_WEB_DIST", str(d))
    return d


def _meta(text: str, prop: str) -> str | None:
    import re
    m = re.search(rf'<meta (?:property|name)="{re.escape(prop)}" content="([^"]*)"', text)
    return m.group(1) if m else None


def _counting(monkeypatch) -> list:
    from league_lab_api import db as DB
    seen: list = []
    real = DB._run
    monkeypatch.setattr(DB, "_run", lambda sql, params: seen.append(sql) or real(sql, params))
    return seen


@needs_db
def test_player_shell_is_the_default_card_when_nothing_is_held_and_reads_nothing(client, dist, monkeypatch):
    from league_lab_api import matchup_board
    matchup_board.clear()
    queries = _counting(monkeypatch)
    calls = A.sleeper().calls
    t = client.get("/player/00-0039075").text
    assert _meta(t, "og:title") == "isuckatfantasy" and t == (dist / "index.html").read_text()
    assert queries == [] and A.sleeper().calls == calls and len(matchup_board._cache) == 0   # nothing read, built or kept
    sm = client.get("/sitemap.xml").text
    assert "/player/" not in sm


@needs_db
def test_player_shell_carries_his_card_from_the_held_board(client, dist, monkeypatch):
    from league_lab_api import matchup_board
    from league_lab_api import player_share as P
    matchup_board.clear()
    b = client.get("/api/matchups/board?league=ref:half&limit=5")
    assert b.status_code == 200
    df = P.held_frame()
    assert df is not None and len(df) > 100
    top = df.sort_values("proj_points", ascending=False).iloc[0]
    queries = _counting(monkeypatch)
    calls = A.sleeper().calls
    t = client.get(f"/player/{top['gsis_id']}").text
    assert queries == [] and A.sleeper().calls == calls                  # the crawler's hit: no query, no provider
    title = _meta(t, "og:title")
    print("card:", title, "|", _meta(t, "og:description"))
    assert title.startswith(f"{top['player_name']} ({top['position']}, {top['team']}): {float(top['proj_points']):.1f} "
                            "projected this week") and title.endswith(" · isuckatfantasy")
    desc = _meta(t, "og:description")
    assert desc.startswith("Week ") and "Half PPR" in desc and "the highest projection of" in desc
    assert f"/player/{top['gsis_id']}" in t and t.count("<title>") == 1 and 'content="noindex"' not in t
    # a league in the query string: noindex (header and tag), still his card
    r = client.get(f"/player/{top['gsis_id']}?league=1389709692405551104")
    assert r.headers.get("x-robots-tag") == "noindex" and 'name="robots" content="noindex"' in r.text
    # the sitemap: the 200 highest projections, from the held board
    sm = client.get("/sitemap.xml").text
    n = sm.count("/player/")
    assert n == min(200, df["gsis_id"].nunique()) and f"/player/{top['gsis_id']}<" in sm


@pytest.mark.parametrize("path", ["/player/00-00390755", "/player/00-003907%22%3E", "/player/%2e%2e%2fsecret",
                                  "/player/00-00%0a39075", "/player/4046", "/player/<script>"])
def test_player_shell_ids_outside_the_pattern_get_the_default_card(client, dist, path):
    r = client.get(path)
    assert r.status_code == 404 or _meta(r.text, "og:title") == "isuckatfantasy"      # a newline: the router's 404
    assert "<script>alert" not in r.text and "projected this week" not in r.text


def test_player_shell_text_is_escaped(monkeypatch, dist):
    from league_lab_api import player_share as P
    df = pd.DataFrame([{"gsis_id": "00-0000001", "player_name": 'Evil "><script>x</script>', "position": "WR",
                        "team": "LAR", "proj_points": 18.44, "p10": 9.2, "p90": 31.6, "opponent": "SF", "is_home": False,
                        "kickoff_at": pd.Timestamp("2026-10-04T17:00:00Z")}])
    df.attrs["ip5_week"] = (2026, 5)
    monkeypatch.setattr(P, "held_frame", lambda: df)
    t = P.shell(dist / "index.html", "player/00-0000001", False)
    assert "<script>x</script>" not in t and "&lt;script&gt;" in t
    c = P.card("00-0000001")
    assert c["title"] == 'Evil "><script>x</script> (WR, LAR): 18.4 projected this week, 9–32 · isuckatfantasy'
    assert c["description"] == ("Week 5, Half PPR: at SF, Sun 1 PM ET; the highest projection of 1 wide receivers "
                                "this week. 8 in 10 weeks like this land between 9 and 32 points.")


def test_a_league_in_the_query_string_is_noindex_everywhere(client, dist):
    for path in ("/week?league=1389709692405551104&team=2", "/players?league=mfl:70587", "/blog?league=x"):
        r = client.get(path)
        assert r.headers.get("x-robots-tag") == "noindex" and 'name="robots" content="noindex"' in r.text, path
    r = client.get("/players")
    assert "x-robots-tag" not in r.headers and 'content="noindex"' not in r.text
