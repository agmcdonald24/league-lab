"""IL-4 (Wave I-L): the next memory lever and the Finder's cold cost.

* Sleeper's player directory trimmed at the load (`league_lab.sleeper_client.DIRECTORY_FIELDS`): a recording directory
  run through the on-demand screens of the Test League (with the availability overlay on) asks for no field outside
  the kept list — the list is the readers' own; `/api/status` `memory.directory` says what is kept.
* The Finder's partners' alternatives, lazily (`decisions.il4_partners_to_compare`, `LEAGUE_LAB_FINDER_LAZY_THEIRS`):
  the lazy and the eager answers agree — the order, the tiers, every `credible` flag, the verdict and its reason, the
  headline, and every card whose partner was compared, in full; a card whose partner was not compared differs only in
  the partner's alternative, said in words — and the lazy path prices fewer partners' waiver moves."""

from __future__ import annotations

from pathlib import Path

import pytest
from league_lab import injury_feed as F
from league_lab import sleeper_client as SC

from league_lab_api import availability as AV
from league_lab_api import decisions

from .conftest import needs_db

TEST_LEAGUE = "9000000000000000001"
ESPN = Path(__file__).with_name("fixtures") / "espn"
# asked of a directory row, never a Sleeper field: MFL's / ESPN's / Yahoo's own rows carry them (Router.players' extras)
NOT_SLEEPERS = {"mfl_id", "unit", "player_name", "yahoo_id"}


class _Recording(dict):
    asked: set[str] = set()

    def get(self, k, default=None):
        _Recording.asked.add(k)
        return super().get(k, default)

    def __getitem__(self, k):
        _Recording.asked.add(k)
        return super().__getitem__(k)

    def __contains__(self, k):
        _Recording.asked.add(k)
        return super().__contains__(k)


@pytest.fixture
def overlay(monkeypatch):
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    F.reset()
    AV._snap = None
    decisions.clear_memo()
    yield
    F.reset()
    AV._snap = None
    decisions.clear_memo()


@needs_db
def test_the_readers_ask_only_for_the_fields_kept(client, monkeypatch, overlay):
    trim = SC.trim_row
    monkeypatch.setattr(SC, "trim_row", lambda p: _Recording(trim(p)))
    _Recording.asked = set()
    q = f"league={TEST_LEAGUE}&team=3"
    for u in (f"/api/my-week?{q}", f"/api/team?{q}", f"/api/waivers?{q}", f"/api/trades/partners?{q}",
              f"/api/league?{q}", f"/api/players?{q}&window=season", f"/api/search?league={TEST_LEAGUE}&q=jo",
              f"/api/ros?{q}"):
        r = client.get(u)
        assert r.status_code == 200, (u, r.status_code, r.text[:300])
    d = SC.Sleeper(fixtures=SC.Path(str(Path(__file__).with_name("fixtures") / "sleeper"))).players()
    assert all(isinstance(v, _Recording) for v in d.values())
    asked = _Recording.asked
    assert {"full_name", "position", "team", "fantasy_positions", "injury_status", "status", "espn_id",
            "gsis_id"} <= asked, sorted(asked)                         # the recording saw the readers
    assert asked - NOT_SLEEPERS <= set(SC.DIRECTORY_FIELDS), sorted(asked - NOT_SLEEPERS - set(SC.DIRECTORY_FIELDS))


@needs_db
def test_status_says_what_the_directory_holds(client):
    assert client.get(f"/api/search?league={TEST_LEAGUE}&q=jo").status_code == 200       # reads the directory
    m = client.get("/api/status").json()["memory"]
    d = m["directory"]
    assert d["loaded"] and d["rows"] > 800 and 0 < d["fields"] <= len(SC.DIRECTORY_FIELDS) and d["kept"] == 15
    assert d["mb"] >= 0 and "sleeper" in m["outside_mb"]


# ------------------------------------------------------------------------------ the Finder's partners, lazily
THEIRS_FIELDS = ("waiver_alternative", "beyond", "why_consider", "why_refuse")


def _finder(client, monkeypatch, lazy: bool, url: str) -> tuple[dict, set[int]]:
    monkeypatch.setenv(decisions.IL4_LAZY_ENV, "on" if lazy else "off")
    decisions.clear_memo()
    from league_lab import anyleague as A
    A.clear_league_weeks()
    A.clear_priced()
    teams: set[int] = set()
    orig = decisions.best_alternative

    def counted(ctx, board, weeks, team, *a, **k):
        teams.add(int(team))
        return orig(ctx, board, weeks, team, *a, **k)
    monkeypatch.setattr(decisions, "best_alternative", counted)
    r = client.get(url)
    assert r.status_code == 200, r.text[:300]
    monkeypatch.setattr(decisions, "best_alternative", orig)
    return r.json(), teams


def _agree(eager: dict, lazy: dict) -> int:
    """The lazy answer is the eager one but for the not-compared partners' alternatives; returns how many cards say so."""
    for k in ("verdict", "credible_count", "explore_count", "headline_rank", "words", "best_alternative", "weeks",
              "guard_positions", "rejected_count"):
        assert lazy[k] == eager[k], k
    assert len(lazy["partners"]) == len(eager["partners"])
    stubs = 0
    for e, z in zip(eager["partners"], lazy["partners"], strict=True):
        for k in ("partner", "give", "get", "rank", "tier", "credible_rank", "story"):
            assert z[k] == e[k], k
        ce, cz = e["card"], z["card"]
        assert cz["credible"] == ce["credible"]
        if cz["waiver_alternative"]["theirs"]["kind"] != decisions.IL4_NOT_COMPARED:
            assert cz == ce                                    # a compared partner: the eager card, in full
            continue
        stubs += 1
        assert not ce["credible"]                              # never a card that could have been credible
        assert {k: v for k, v in cz.items() if k not in THEIRS_FIELDS} == \
               {k: v for k, v in ce.items() if k not in THEIRS_FIELDS}
        assert cz["waiver_alternative"]["mine"] == ce["waiver_alternative"]["mine"]
        assert cz["beyond"]["mine"] == ce["beyond"]["mine"]
        assert cz["beyond"]["theirs"] >= ce["beyond"]["theirs"]   # standing pat in his place: an upper bound
        assert "their own best waiver move was not compared: " in cz["waiver_alternative"]["words"]
        assert all("Their best waiver move" not in x for x in cz["why_refuse"])
    return stubs


@needs_db
def test_lazy_and_eager_finder_agree_on_the_test_league(client, monkeypatch):
    url = f"/api/trades/partners?league={TEST_LEAGUE}&team=3"
    eager, t_eager = _finder(client, monkeypatch, False, url)
    lazy, t_lazy = _finder(client, monkeypatch, True, url)
    stubs = _agree(eager, lazy)
    assert eager["verdict"]["kind"] == "compelling" and eager["credible_count"] >= 1
    assert t_lazy < t_eager and 3 in t_lazy, (sorted(t_lazy), sorted(t_eager))   # fewer partners' waiver moves priced
    assert stubs >= 1


@needs_db
def test_lazy_keeps_the_no_compelling_reason_exact(client, monkeypatch):
    """A team with nothing credible: the reason counts "N do not beat the other team's" — the same lazily."""
    for team in range(1, 11):
        url = f"/api/trades/partners?league={TEST_LEAGUE}&team={team}"
        eager, _ = _finder(client, monkeypatch, False, url)
        if eager["verdict"]["kind"] != "none" or not eager["partners"]:
            continue
        lazy, _ = _finder(client, monkeypatch, True, url)
        _agree(eager, lazy)
        assert lazy["verdict"]["reason"] == eager["verdict"]["reason"]
        return
    pytest.skip("no Test League team without a credible trade at the pinned moment")


@needs_db
def test_the_calculator_always_compares(client, monkeypatch):
    """The calculator's card is never the lazy stub, even after the Finder kept a stub card on the same frame."""
    monkeypatch.setenv(decisions.IL4_LAZY_ENV, "on")
    fin = client.get(f"/api/trades/partners?league={TEST_LEAGUE}&team=3").json()
    stub = next((r for r in fin["partners"] if r["card"]["waiver_alternative"]["theirs"]["kind"] == decisions.IL4_NOT_COMPARED),
                None)
    if stub is None:
        pytest.skip("every partner was compared")
    body = {"league": TEST_LEAGUE, "team": 3, "partner": stub["partner"], "give": [x["sleeper_id"] for x in stub["give"]],
            "get": [x["sleeper_id"] for x in stub["get"]]}
    r = client.post("/api/trades/evaluate", json=body)
    assert r.status_code == 200, r.text[:300]
    card = r.json().get("card") or {}
    assert card and card["waiver_alternative"]["theirs"]["kind"] != decisions.IL4_NOT_COMPARED
