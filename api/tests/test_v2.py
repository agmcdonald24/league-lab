"""V-2 (Wave I-H): the decision record, personal and live, on /api/record (needs_db: the clone `league_lab_i0a` with
`league-lab validate` run and the two marts built; the main database once the PO has applied them).

* ``decisions.team`` for Scrubs roster 6 ("GoodGameBuddy"): its graded weeks, the sums, the sentence, the close calls;
  every roster's weeks add up to the league's, to the cent.
* Dad's league (MFL 70587) from the fixtures: its record rows are built in memory by ``lineup.mfl_record_rows`` on the
  MFL fixtures (the reads go through the API's read-only role; nothing is written) and graded from the fixtures'
  ``weeklyResults``: weeks 1-3 rebuilt and said so, the submitted points are MFL's franchise scores, a double header
  counted once.
* The event store's news flag reaches the answer (``news_source``)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from .conftest import SCRUBS, needs_db

pytestmark = needs_db
DAD = "mfl:70587"
MFL_FIX = Path(__file__).with_name("fixtures") / "mfl" / "70587"


def _have_marts(sql) -> bool:
    return sql("select to_regclass('analytics.mart_decision_record') is not null and "
               "to_regclass('analytics.mart_decision_calls') is not null as ok")[0]["ok"]


@pytest.fixture
def scrubs(client, sql):
    if not _have_marts(sql):
        pytest.skip("mart_decision_record not built on this database (league-lab validate + dbt build first)")
    return lambda team=None: client.get(f"/api/record?league={SCRUBS}" + (f"&team={team}" if team is not None else "")).json()


def test_scrubs_roster_6_has_its_calls_this_season(scrubs):
    d = scrubs(6)["decisions"]
    t = d["team"]
    assert t["roster_id"] == 6 and t["available"] is True and t["team_name"]
    weeks = [w["week"] for w in t["weeks"]]
    assert weeks == [w["week"] for w in d["weeks"]]                    # every graded league week has this team in it
    for w in t["weeks"]:
        assert w["edge"] == pytest.approx(w["app"] - w["submitted"], abs=0.011)
        assert w["regret"] == pytest.approx(w["optimum"] - w["submitted"], abs=0.011) and w["regret"] >= 0
        assert w["record_source"] in ("kickoff", "reconstructed") and w["news_source"] in ("events", "report")
        for c in w["calls"]:
            assert c["words"].startswith(f"{c['player_name']} over {c['alt_player_name']}")
    tot = t["season_totals"]
    for k in ("submitted", "app", "optimum", "edge", "regret"):
        assert tot[k] == pytest.approx(sum(w[k] for w in t["weeks"]), abs=0.001), k
    s = t["sentences"]["season"]
    assert s == (f"{'Weeks 1–2' if weeks == [1, 2] else s.split(':')[0]}: you started {tot['submitted']:.1f}; our lineup "
                 f"would have scored {tot['app']:.1f}; the best possible was {tot['optimum']:.1f}.")
    print("Scrubs roster 6:", s, "| calls:", t["sentences"]["calls"], "|", t["calls"])


def test_every_teams_weeks_add_up_to_the_league(scrubs, sql):
    league = scrubs()["decisions"]
    assert league["team"] is None                                       # no team asked: no team block
    rosters = [r["roster_id"] for r in sql("""select distinct roster_id from analytics.mart_decision_record
                                               where league_id = %s and season = 2026 order by 1""", (SCRUBS,))]
    sums: dict[int, dict[str, float]] = {}
    for rid in rosters:
        for w in scrubs(rid)["decisions"]["team"]["weeks"]:
            acc = sums.setdefault(w["week"], {k: 0.0 for k in ("submitted", "app", "optimum", "edge", "regret")})
            for k in acc:
                acc[k] += w[k]
    assert sorted(sums) == [w["week"] for w in league["weeks"]]
    for w in league["weeks"]:
        for k in ("submitted", "app", "optimum", "edge", "regret"):
            assert sums[w["week"]][k] == pytest.approx(w[k], abs=0.011), (w["week"], k)


def test_a_team_with_no_record_says_why(scrubs):
    t = scrubs(99)["decisions"]["team"]
    assert t["available"] is False and t["weeks"] == [] and "no lineup on the record" in t["why"]


def test_the_event_store_flag_reaches_the_answer(scrubs, monkeypatch):
    from league_lab_api import ondemand
    monkeypatch.setattr(ondemand, "event_news", lambda league_id, season: {(SCRUBS, 1, 6): 1})
    d = scrubs(6)["decisions"]
    w1 = next(w for w in d["weeks"] if w["week"] == 1)
    assert w1["news_rosters"] == 1 and w1["news_source"] == "mixed" and d["news"]["roster_weeks"] == 1
    t1 = next(w for w in d["team"]["weeks"] if w["week"] == 1)
    assert t1["news"] is True and t1["news_source"] == "events" and d["team"]["news"]["weeks"] == [1]


# ------------------------------------------------------------------------------ dad's league (MFL 70587)
def _fixture_scores() -> dict[int, dict[str, float]]:
    out = {}
    for w in (1, 2, 3):
        res = json.loads((MFL_FIX / f"weeklyResults_{w}.json").read_text())["weeklyResults"]
        out[w] = {f["id"]: float(f["score"]) for m in res["matchup"] for f in m["franchise"]}
    return out


@pytest.fixture
def dad(client, monkeypatch):
    """/api/record for dad's league with its record rows built in memory from the fixtures (nothing written)."""
    from league_lab import lineup as LU
    from league_lab_api import ondemand

    rows, plan = LU.mfl_record_rows(ondemand.query, DAD, datetime(2026, 10, 4, 16, 0, tzinfo=UTC))
    rec = pd.DataFrame(rows)
    rec = rec[rec["role"] == "starter"].assign(run_at=rec["as_of"])
    real = ondemand.query

    def q(sql, params=(), **kw):
        if sql == ondemand.MFL_RECORD_SQL:
            return rec[rec["league_id"] == params[0]].reset_index(drop=True)
        return real(sql, params, **kw)
    monkeypatch.setattr(ondemand, "query", q)
    return (lambda team=None: client.get(f"/api/record?league={DAD}" + (f"&team={team}" if team else "")).json()), plan


def test_dads_league_shows_its_record_rebuilt_from_mfl_results(dad):
    get, plan = dad
    assert {w: a for (_, w), a in plan.items()} == {1: "reconstruct", 2: "reconstruct", 3: "reconstruct", 4: "reconstruct",
                                                    5: "write"}
    out = get()
    assert out["available"] is False and out["results"]                  # IC-4's results stay
    d = out["decisions"]
    assert d["available"] is True and d["platform"] == "mfl" and d["season"] == 2026
    assert [w["week"] for w in d["weeks"]] == [1, 2, 3]                    # week 4 waits for MFL's results; 5 is in play
    assert all(w["record_source"] == "reconstructed" and w["rosters"] == 12 for w in d["weeks"])
    assert d["reconstructed_weeks"][:3] == [1, 2, 3] and "rebuilt" in d["note"]
    scores = _fixture_scores()
    for w in d["weeks"]:                       # MFL's franchise scores, each team once (a double header counts once)
        assert w["submitted"] == pytest.approx(sum(scores[w["week"]].values()), abs=0.011)
        assert w["regret"] >= 0 and w["edge"] == pytest.approx(w["app"] - w["submitted"], abs=0.011)
    tot = d["season_totals"]
    assert tot["roster_weeks"] == 36 and tot["edge"] == pytest.approx(sum(w["edge"] for w in d["weeks"]), abs=0.001)
    print("dad's league:", d["sentences"]["edge"], "|", d["sentences"]["calls"])


def test_dads_league_team_1_knight_train(dad):
    get, _ = dad
    t = get(1)["decisions"]["team"]
    assert t["roster_id"] == 1 and t["team_name"] == "Knight Train" and [w["week"] for w in t["weeks"]] == [1, 2, 3]
    scores = _fixture_scores()
    assert [w["submitted"] for w in t["weeks"]] == [scores[w]["0001"] for w in (1, 2, 3)]
    assert t["sentences"]["season"].startswith("Weeks 1–3: you started ")
    print("Knight Train:", t["sentences"]["season"])


def test_an_mfl_league_with_no_record_rows_says_so(client, monkeypatch):
    from league_lab_api import ondemand
    real = ondemand.query
    monkeypatch.setattr(ondemand, "query", lambda sql, params=(), **kw: pd.DataFrame(columns=["week"])
                        if sql == ondemand.MFL_RECORD_SQL else real(sql, params, **kw))
    d = client.get(f"/api/record?league={DAD}").json()["decisions"]
    assert d["available"] is False and d["platform"] == "mfl" and d["why"] == ondemand.MFL_NO_RECORD
