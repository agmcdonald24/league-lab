"""Wave I-H, IH-3 — the week's win probability on My Week (`win`), information only.

1. The words and the line (no database): favourite / underdog / coin flip, the played count, no range -> no line.
2. Played games use the week's points: the nightly scored his team's game -> his points (Sleeper's own number), a
   starter missing from the points scored 0; a game in progress keeps his range; an MFL league whose live scores are
   not read steps aside once a game is in.
3. League of Scrubs roster 6 "GoodGameBuddy" and his opponent on the main database (needs_db): a number between 0 and
   1, the words, `n_played`, the expected totals = the two lineup totals the page shows.
4. A double header (MFL 70587, week 4 in the fixtures): two probabilities.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import decisions as D
from league_lab import mfl_client as M
from league_lab import player_ids as PI
from scipy.stats import norm

from league_lab_api import myweek, ondemand

from .conftest import SCRUBS, needs_db
from .test_i0b import IDS, MFL_FX

WORDS = {"a coin flip", "a slight favorite", "a clear favorite", "a slight underdog", "a clear underdog"}


def _row(key, pos, team, opp, p50, sd=6.0, role="starter", **kw):
    z10, z25 = norm.ppf(0.10), norm.ppf(0.25)
    return {"role": role, "is_empty_slot": False, "gsis_id": key, "sleeper_player_id": f"s{key}", "player_name": key,
            "position": pos, "team": team, "opponent": opp, "value": p50,
            "p10": p50 + z10 * sd, "p25": p50 + z25 * sd, "p50": p50, "p75": p50 - z25 * sd, "p90": p50 - z10 * sd, **kw}


def _frame(prefix, shift, teams):
    pos = ["QB", "RB", "RB", "WR", "WR", "TE"]
    base = [20.0, 13.0, 11.0, 14.0, 12.0, 9.0]
    rows = [_row(f"{prefix}{i}", p, t, f"X{t}", b + shift) for i, (p, t, b) in enumerate(zip(pos, teams, base, strict=True))]
    rows.append({**_row(f"{prefix}b", "WR", "ZZ", "XZ", 30.0), "role": "bench"})                    # the bench never counts
    rows.append({"role": "starter", "is_empty_slot": True, "gsis_id": None, "sleeper_player_id": None, "player_name": None,
                 "position": None, "team": None, "opponent": None, "value": None})                 # an empty slot: nothing
    return pd.DataFrame(rows)


MINE = _frame("a", 1.5, ["A1", "A2", "A3", "A4", "A5", "A6"])
THEIRS = _frame("b", 0.0, ["B1", "B2", "B3", "B4", "B5", "B6"])


def _win(monkeypatch, mine=MINE, theirs=THEIRS, scored=(), points=None, house=True, opp=None):
    monkeypatch.setattr(myweek, "scored_teams", lambda season, week: set(scored))
    if house:
        def fake_query(sql, args=()):
            assert sql == myweek.OBSERVED_SQL
            return pd.DataFrame([{"sleeper_player_id": k, "points": v} for k, v in (points or {}).items()],
                                columns=["sleeper_player_id", "points"])
        monkeypatch.setattr(myweek, "query", fake_query)
    ctx = {7: SimpleNamespace(rows=theirs), 8: SimpleNamespace(rows=theirs)}
    return myweek.win("L1", 1, 2026, 4, mine, opp or {"roster_id": 7}, house=house, context_fn=lambda rid: ctx[rid],
                      points_fn=None if house else (lambda rids: points))


def test_the_words_and_the_line(monkeypatch):
    w = _win(monkeypatch)
    assert 0.5 < w["p"] < 1 and w["words"] in WORDS and w["side"] == "favorite"
    assert w["percent"] == D.percent(w["p"])
    assert (w["n_starters"], w["opp_n_starters"], w["n_played"], w["opp_n_played"]) == (6, 6, 0, 0)
    assert w["mine"] == pytest.approx(79.0 + 9.0) and w["theirs"] == pytest.approx(79.0)
    assert w["line"] == f"You're {w['words']} this week: {w['percent']}%, 88 to 79 expected."
    assert w["assumptions"] == "assuming the players' weeks are independent except teammates and opponents"
    assert w["played_words"] is None and w["early"] is False and "also" not in w
    u = _win(monkeypatch, mine=THEIRS.assign(team=[f"C{i}" for i in range(len(THEIRS))]), theirs=MINE)
    assert u["side"] == "underdog" and u["words"].endswith("underdog")
    assert u["line"].startswith(f"You're {u['words']} this week: {u['percent']}%, 79 to 88 expected.")
    even = _win(monkeypatch, mine=THEIRS.assign(team=[f"C{i}" for i in range(len(THEIRS))]))
    assert even["words"] == "a coin flip" and even["line"].startswith("This week is a coin flip: ")
    # never an instruction: the line has no verb aimed at a player
    for x in (w, u, even):
        assert not any(v in x["line"].lower() for v in ("start ", "sit ", "bench", "ceiling", "chase", "swap"))


def test_no_opponent_and_no_range(monkeypatch):
    assert myweek.win("L1", 1, 2026, 4, MINE, None, house=True) is None
    bare = THEIRS.assign(p10=None, p25=None, p50=None, p75=None, p90=None)
    w = _win(monkeypatch, theirs=bare)
    assert w["p"] is None and w["line"] is None and w["note"] == myweek.WIN_NO_RANGE


def test_played_games_use_the_weeks_points(monkeypatch):
    # A1 (my QB) and B1 (their QB) played: Sleeper's numbers 31.5 and 6.0; B2's game is in too and he is missing from
    # the points: he scored 0 (did not play)
    w = _win(monkeypatch, scored={"A1", "B1", "B2"}, points={"sa0": 31.5, "sb0": 6.0})
    assert (w["n_played"], w["opp_n_played"]) == (1, 2)
    assert w["mine"] == pytest.approx(88.0 - 21.5 + 31.5)
    assert w["theirs"] == pytest.approx(79.0 - 20.0 + 6.0 - 13.0)
    assert w["played_words"] == "1 of your 6 have played, 2 of theirs"
    assert w["line"].endswith("1 of your 6 have played, 2 of theirs.")
    assert w["p"] > _win(monkeypatch)["p"]
    # nothing scored yet (a game in progress is not "in"): the ranges
    assert _win(monkeypatch, scored=set())["n_played"] == 0


def test_on_demand_points_and_mfl_without_live_scores(monkeypatch):
    w = _win(monkeypatch, scored={"A1"}, points={"sa0": 25.0}, house=False)
    assert w["n_played"] == 1 and w["mine"] == pytest.approx(88.0 - 21.5 + 25.0)
    m = _win(monkeypatch, scored={"A1"}, points=None, house=False)              # an MFL league: points unknown
    assert m["p"] is None and m["note"] == myweek.WIN_NO_LIVE
    assert ondemand.week_points(None, "mfl:70587", 4, [1]) is None
    # before any game: MFL is priced like everyone
    assert _win(monkeypatch, scored=set(), points=None, house=False)["p"] is not None


def test_a_double_header_gets_two_probabilities(monkeypatch):
    w = _win(monkeypatch, opp={"roster_id": 7, "also": [{"roster_id": 8}]})
    assert w["opponent_roster_id"] == 7 and len(w["also"]) == 1
    assert w["also"][0]["opponent_roster_id"] == 8 and w["also"][0]["p"] == pytest.approx(w["p"])


def test_sleeper_week_points_read_the_matchups_call():
    class C:
        def matchups(self, league_id, week):
            return [{"roster_id": 1, "players_points": {"x": 12.5, "y": None}}, {"roster_id": 2, "players_points": {"z": 3.0}},
                    {"roster_id": 3, "players_points": {"q": 9.0}}]
    assert ondemand.week_points(C(), "1389709692405551104", 4, [1, 2]) == {"x": 12.5, "z": 3.0}


# ------------------------------------------------------------------------------ the main database
@needs_db
def test_scrubs_roster_6_and_his_opponent(client):
    r = client.get(f"/api/my-week?league={SCRUBS}&team=6")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    if d.get("opponent") is None:
        pytest.skip("no opponent this week in the database / fixtures")
    w = d["win"]
    assert w is not None and w["opponent_roster_id"] == d["opponent"]["roster_id"]
    assert 0 < w["p"] < 1 and w["words"] in WORDS
    assert isinstance(w["n_played"], int) and isinstance(w["opp_n_played"], int)
    assert w["n_starters"] >= 9
    # the expected totals are the totals the page shows (before any game is in)
    if w["n_played"] == 0 and w["opp_n_played"] == 0:
        assert w["mine"] == pytest.approx(d["lineup_value"], abs=0.01)
        assert w["theirs"] == pytest.approx(d["opponent"]["lineup_value"], abs=0.01)
    assert f"{w['percent']}%" in w["line"]


@pytest.fixture
def mfl(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


@needs_db
def test_dads_double_header_on_my_week(client, mfl):
    r = client.get("/api/my-week?league=mfl:70587&team=1")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    if d["week"] != 4:
        pytest.skip(f"the fixture's week is {d['week']}, not a double-header week")
    w = d["win"]
    assert w is not None and len(w.get("also") or []) == 1
    for x in (w, w["also"][0]):
        assert (x["p"] is None and x["note"]) or (0 < x["p"] < 1 and x["words"] in WORDS)


# ------------------------------------------------------------------ the web's e2e recordings (web/e2e/ih3)
@needs_db
@pytest.mark.skipif(not __import__("os").environ.get("IH3_RECORD"), reason="records web/fixtures/ih3/api_ih3.json: IH3_RECORD=1")
def test_record_e2e_answers(client, mfl):
    """The answers web/e2e/ih3 replays: League of Scrubs roster 6's My Week (one game), dad's league team 1 (Knight
    Train: the week-4 double header, two lines), the MFL pick and the status."""
    import json
    from urllib.parse import urlencode

    from league_lab_api.settings import ROOT

    def key(path: str, **q) -> str:
        return path + ("?" + urlencode(sorted((k, str(v)) for k, v in q.items())) if q else "")

    out: dict = {}

    def rec(path: str, **q):
        r = client.get(key(path, **q))
        out[key(path, **q)] = {"status": r.status_code, "body": r.json()}

    rec("/api/my-week", league=SCRUBS, team=6)
    rec("/api/leagues", mfl_search="70587")
    rec("/api/leagues/mfl%3A70587/rosters")
    rec("/api/my-week", league="mfl:70587", team=1)
    rec("/api/status")
    f = ROOT / "web" / "fixtures" / "ih3" / "api_ih3.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    assert all(v["status"] == 200 for v in out.values()), {k: v["status"] for k, v in out.items()}
    assert out[key("/api/my-week", league=SCRUBS, team=6)]["body"]["win"]["line"]
