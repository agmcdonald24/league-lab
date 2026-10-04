"""V-2 (Wave I-H): the decision record, personal and live — no database needed.

* the news flag from the event store on synthetic events (after the build and before HIS kickoff, a different status;
  the store not running across the week = the report rule; reconstructed weeks never);
* one team's weeks add up to the league's (``team_summary`` against ``summary``);
* MyFantasyLeague: the grade on the 70587 fixture's weeks 1-2 (``mfl_weekly``: MFL's scores, ``opt_pts``, a double
  header once; a changed starter moves the edge by the difference);
* Sleeper's projections as a lineup (``market_rows``: the roster the record saw, Sleeper's numbers, a DEF keeps ours);
* ``LEAGUE_LAB_RECORD_MFL``."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from league_lab import lineup, validation

from .test_v1 import _grade_inputs

ROOT = Path(__file__).resolve().parents[1]
MFL = ROOT / "api/tests/fixtures/mfl/70587"
RUN = datetime(2026, 10, 8, 11, 37, tzinfo=UTC)         # the Thursday-morning build
K0 = datetime(2026, 10, 9, 0, 15, tzinfo=UTC)           # the week's first kickoff (Thursday night)
SUN = datetime(2026, 10, 11, 17, 0, tzinfo=UTC)         # the starters' own Sunday game


# ------------------------------------------------------------------------------ the news flag
def _rec(**over) -> pd.DataFrame:
    rows = [{"league_id": "L", "season": 2026, "week": 5, "roster_id": 1, "record_source": "kickoff", "run_at": RUN,
             "first_kickoff_at": K0, "gsis_id": g, "report_status": s}
            for g, s in (("00-0000001", None), ("00-0000002", "Questionable"), ("00-0000003", None))]
    df = pd.DataFrame(rows)
    for k, v in over.items():
        df[k] = v
    return df


KICK = pd.DataFrame([(5, "00-0000001", SUN), (5, "00-0000002", SUN), (5, "00-0000003", K0)],
                    columns=["week", "gsis_id", "kickoff_at"])
SPAN = (RUN - timedelta(days=3), SUN + timedelta(days=1))
NO_REPORT = pd.DataFrame(columns=["week", "gsis_id", "report_status", "roster_status"])


def _ev(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["gsis_id", "status", "at"])


def test_a_status_move_after_the_build_and_before_his_kickoff_flags_him():
    ev = _ev(("00-0000001", "OUT", RUN + timedelta(days=2)),               # Saturday: Out -> news-affected
             ("00-0000002", "QUESTIONABLE", RUN + timedelta(hours=3)),     # the same status he had: not news
             ("00-0000003", "DOUBTFUL", K0 + timedelta(hours=2)))          # after his own (Thursday) kickoff: too late
    nb = validation.news_by_starter(_rec(), NO_REPORT, ev, KICK, SPAN)
    assert nb["flag"].tolist() == [True, False, False] and set(nb["source"]) == {"events"}


def test_a_move_before_the_build_is_what_the_build_saw():
    ev = _ev(("00-0000001", "OUT", RUN - timedelta(hours=1)))
    assert not validation.news_by_starter(_rec(), NO_REPORT, ev, KICK, SPAN)["flag"].any()
    # back to the report it had: Questionable -> ACTIVE on Friday is a move
    ev = _ev(("00-0000002", "ACTIVE", RUN + timedelta(days=1)))
    assert validation.news_by_starter(_rec(), NO_REPORT, ev, KICK, SPAN)["flag"].tolist() == [False, True, False]


def test_no_store_across_the_week_falls_back_to_the_report_rule():
    report = pd.DataFrame([(5, "00-0000001", "Out", "ACT")], columns=["week", "gsis_id", "report_status", "roster_status"])
    ev = _ev(("00-0000003", "OUT", RUN + timedelta(hours=1)))
    late = (K0 + timedelta(hours=1), SUN)                                  # the store started after the first kickoff
    for span in (None, late):
        nb = validation.news_by_starter(_rec(), report, ev, KICK, span)
        assert nb["flag"].tolist() == [True, False, False] and set(nb["source"]) == {"report"}
    # a reconstructed week is never flagged, whatever the store says
    nb = validation.news_by_starter(_rec(record_source="reconstructed"), report, ev, KICK, SPAN)
    assert not nb["flag"].any()


def test_an_unknown_game_time_uses_the_weekend():
    ev = _ev(("00-0000001", "OUT", K0 + timedelta(days=3)))               # Sunday night, his game time unknown
    nb = validation.news_by_starter(_rec(), NO_REPORT, ev, KICK.iloc[0:0], SPAN)
    assert nb["flag"].tolist() == [True, False, False]


def test_the_grade_counts_and_nets_the_event_cases():
    g = _grade_inputs()                                        # V-1's synthetic week: roster 1 edge +8, roster 2 -2
    g.record["run_at"], g.record["first_kickoff_at"] = RUN, K0
    g.status = NO_REPORT
    g.events = _ev(("gR2", "OUT", RUN + timedelta(hours=5)))   # roster 2's R2 went Out after the build
    g.events_span = SPAN
    rw = validation.grade_roster_weeks(g).set_index("roster_id")
    assert rw.loc[2, "is_news_affected"] and not rw.loc[1, "is_news_affected"]
    assert set(rw["news_source"]) == {"events"}
    s = validation.summary(rw.reset_index(), validation.grade_calls(g))
    assert s["news"] == {"roster_weeks": 1, "edge": -2.0, "regret": 0.0, "source": "events"}
    assert s["sentences"]["news"].startswith("1 lineup had a starter's injury status change between our build and his "
                                             "kickoff; there our lineups scored −2.0")
    # the request side: the same flags as overrides on a mart's rows (report rule there)
    ov = validation.news_overrides(g.record, g.events, None, SPAN)
    assert ov == {("L", 1, 1): 0, ("L", 1, 2): 1}
    mart = validation.grade_roster_weeks(_grade_inputs()).drop(columns=["news_source"])
    applied = validation.apply_news(mart, ov).set_index("roster_id")
    assert applied.loc[2, "is_news_affected"] and not applied.loc[1, "is_news_affected"]   # W1's report flag replaced


# ------------------------------------------------------------------------------ one team
def test_the_teams_add_up_to_the_league_and_the_sentence():
    g = _grade_inputs()
    rw, calls = validation.grade_roster_weeks(g), validation.grade_calls(g)
    league = validation.summary(rw, calls)
    teams = [validation.team_summary(rw, calls, r) for r in (1, 2)]
    for k in ("submitted", "app", "optimum", "edge", "regret"):
        assert sum(t["season_totals"][k] for t in teams) == pytest.approx(league["season_totals"][k], abs=1e-9)
    t1 = teams[0]
    assert t1["sentences"]["season"] == "Week 1: you started 25.0; our lineup would have scored 33.0; the best possible was 33.0."
    assert t1["weeks"][0]["calls"][0]["words"] == "x over y (we gave it 53%): 20.0 to 12.0 — the right call."
    assert t1["sentences"]["calls"] == "Our closest calls for you landed 1 of 1 (0.5 expected)."
    assert validation.team_summary(rw, calls, 7)["why"] == "this team has no lineup on the record"


# ------------------------------------------------------------------------------ MyFantasyLeague
def _results(*weeks) -> dict:
    return {w: json.loads((MFL / f"weeklyResults_{w}.json").read_text())["weeklyResults"] for w in weeks}


def _ident(ids):
    return {i: (i, "table") for i in ids}


RID = {f"{i:04d}": i for i in range(1, 13)}


def test_the_mfl_grade_on_the_fixture_weeks_1_and_2():
    res = _results(1, 2)
    weekly, opt = validation.mfl_weekly("mfl:70587", res, _ident, RID, [1, 2])
    # the record = what each franchise started (MFL's own lineups): the edge is 0, the regret MFL's opt_pts - score
    rec = weekly[weekly["is_starter"]].rename(columns={})[["league_id", "week", "roster_id", "sleeper_player_id"]].copy()
    rec = rec.assign(season=2026, role="starter", record_source="reconstructed", model_version="v3.0", pricing="flat",
                     gsis_id=None, report_status=None, call_rank=None, alt_sleeper_player_id=None, alt_gsis_id=None,
                     p_win=None, is_coin_flip=None, slot="X", player_name="x", value=1.0, margin=1.0, alt_player_name=None,
                     alt_value=None)
    rw = validation.grade_roster_weeks(validation.mfl_inputs(rec, weekly, opt))
    assert len(rw) == 24 and set(rw["status"]) == {"scored"} and (rw["app_edge"] == 0).all()
    for w in (1, 2):
        fr = {f["id"]: f for m in res[w]["matchup"] for f in m["franchise"]}
        got = rw[rw["week"] == w].set_index("roster_id")
        for fid, f in fr.items():
            assert got.loc[RID[fid], "submitted_points"] == float(f["score"])
            assert got.loc[RID[fid], "regret"] == float(f["opt_pts"]) - float(f["score"])
    # swap one of Knight Train's week-1 starters for a bench player: the edge moves by the difference
    w1 = weekly[(weekly["week"] == 1) & (weekly["roster_id"] == 1)]
    a = w1[w1["is_starter"]].iloc[1]
    b = w1[~w1["is_starter"]].iloc[0]
    rec2 = rec.copy()
    rec2.loc[(rec2["week"] == 1) & (rec2["roster_id"] == 1) & (rec2["sleeper_player_id"] == a.sleeper_player_id),
             "sleeper_player_id"] = b.sleeper_player_id
    r1 = validation.grade_roster_weeks(validation.mfl_inputs(rec2, weekly, opt)).set_index(["week", "roster_id"]).loc[(1, 1)]
    assert r1.app_edge == pytest.approx(b.points_observed - a.points_observed) and r1.n_changed == 1
    # a starter on no franchise that week has no number in MFL: unknown, never 0
    rec3 = rec.copy()
    i = rec3[(rec3["week"] == 1) & (rec3["roster_id"] == 1)].index[0]
    rec3.loc[i, "sleeper_player_id"] = "nobody"
    r = validation.grade_roster_weeks(validation.mfl_inputs(rec3, weekly, opt)).set_index(["week", "roster_id"]).loc[(1, 1)]
    assert pd.isna(r.app_points) and r.n_app_unknown == 1


def test_a_double_header_counts_each_franchise_once():
    res = _results(1)
    m = res[1]["matchup"]
    doubled = {1: {**res[1], "matchup": [*m, m[0]]}}                      # franchise pair listed twice (a second game)
    weekly, opt = validation.mfl_weekly("mfl:70587", doubled, _ident, RID, [1])
    single, _ = validation.mfl_weekly("mfl:70587", res, _ident, RID, [1])
    assert len(weekly) == len(single) and len(opt) == 12
    unscored, _ = validation.mfl_weekly("mfl:70587", res, _ident, RID, [])
    assert not unscored["is_scored_week"].any()


# ------------------------------------------------------------------------------ Sleeper's projections as a lineup
def test_sleeper_s_lineup_is_the_roster_the_record_saw_at_sleeper_s_numbers():
    roster = pd.DataFrame([
        ("Q1", "g1", "QB", "starter", 20.0), ("Q2", "g2", "QB", "bench", 15.0),
        ("R1", "g3", "RB", "starter", 12.0), ("R2", "g4", "RB", "bench", 8.0), ("R3", "g5", "RB", "unplayable", None),
        ("D1", None, "DEF", "starter", 7.0), ("D2", None, "DEF", "bench", 6.0),
    ], columns=["sleeper_player_id", "gsis_id", "position", "role", "value"])
    roster = roster.assign(league_id="L", season=2026, week=5, roster_id=1, record_source="kickoff", slot=None,
                           player_name=roster["sleeper_player_id"], value_source="proj_points", reason=None, pricing="flat")
    lines = pd.DataFrame([("g1", "QB", 200.0), ("g2", "QB", 300.0), ("g3", "RB", 50.0), ("g4", "RB", 90.0),
                          ("g5", "RB", 500.0)], columns=["gsis_id", "position", "passing_yards"])
    lines = lines.assign(week=5, fetched_at=RUN, rushing_yards=lines["passing_yards"])
    leagues = {"L": {"scoring": {"pass_yd": 0.04, "rush_yd": 0.1}, "slots": ["QB", "RB", "DEF", "BN", "BN"]}}
    rows = validation.market_rows(roster, lines, leagues)
    got = {r["slot"]: (r["sleeper_player_id"], r["value_source"]) for r in rows}
    # Sleeper prefers Q2 (300 yds) and R2 (90); R3 is out whatever Sleeper says; the DEF keeps our pick
    assert got == {"QB": ("Q2", "sleeper"), "RB": ("R2", "sleeper"), "DEF": ("D1", "ours")}
    # graded like ours: the points they scored, the edge over the submitted
    g = _grade_inputs()
    g.market = pd.DataFrame([{"league_id": "L", "week": 1, "roster_id": 1, "sleeper_player_id": s, "gsis_id": "g" + s}
                             for s in ("A", "R1", "W1")])
    rw = validation.grade_roster_weeks(g).set_index("roster_id")
    assert rw.loc[1, "market_points"] == 25.0 and rw.loc[1, "market_edge"] == 0.0 and pd.isna(rw.loc[2, "market_points"])
    s = validation.summary(rw.reset_index(), validation.grade_calls(g))
    assert s["weeks"][0]["market"] is None                     # one team without Sleeper's lineup: no league sum
    g.market = pd.concat([g.market, pd.DataFrame([{"league_id": "L", "week": 1, "roster_id": 2, "sleeper_player_id": x,
                                                   "gsis_id": "g" + x} for x in ("Q2", "R2", "X2")])])
    s = validation.summary(validation.grade_roster_weeks(g), validation.grade_calls(g))
    assert s["weeks"][0]["market"] == 55.0 and s["season_totals"]["market"] == 55.0
    assert s["sentences"]["market"] == ("Week 1: had every team started Sleeper's projections, the league would have "
                                        "scored 55.0 — 6.0 fewer than our lineups and 0.0 more than the ones started.")


def test_the_mfl_record_keys_come_from_the_env(monkeypatch):
    assert lineup.mfl_record_keys("mfl:70587, 1389709692405551104,mfl:21861,") == ["mfl:21861", "mfl:70587"]
    monkeypatch.setenv(lineup.MFL_RECORD_ENV, "mfl:70587")
    assert lineup.mfl_record_keys() == ["mfl:70587"]
    monkeypatch.delenv(lineup.MFL_RECORD_ENV)
    assert lineup.mfl_record_keys() == []


def test_the_market_table_is_in_the_ddl_and_the_dbt_pre_hook():
    assert "ops.decision_market" in lineup.DDL
    cols = [c.split()[0] for c in lineup.MARKET_DDL.split("(", 1)[1].split(");")[0].replace("\n", " ").split(",")]
    assert cols == validation.MARKET_COLUMNS
    assert "create table if not exists ops.decision_market" in (ROOT / "dbt/models/marts/edge/mart_decision_record.sql").read_text()
