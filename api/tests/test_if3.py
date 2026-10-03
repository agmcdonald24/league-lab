"""Wave I-F (IF-3, the decision-quality review § Priority 1): historical matchup evidence connected to current personnel.

The review's case: Jameson Williams (00-0037240) vs Bhayshul Tuten (00-0040719) on League of Scrubs roster 6 in week 4 —
Carolina ranked near the bottom against receivers while its starting corners Jaycee Horn (00-0036944) and Mike Jackson
(00-0035277) went on injured reserve (Panthers, 2026-09-30). The main-database clone (2026-09-26) still lists Horn and
Jackson on Carolina's depth chart (Jackson left corner, Will Lee III right, Horn slot; Akayleb Evans and Chau Smith-Wade
behind them), so the as-of fixture is the overlay: ``fixtures/espn_if3/`` is ``fixtures/espn/`` (ESPN's feed as read
2026-10-03) plus two Carolina entries — Horn and Jackson "Injured Reserve", dated 2026-09-30 20:15Z — and the id-table
rows that map them to gsis. Their ESPN athlete ids (9900101 / 9900102) are placeholders: our id tables carry no ESPN id
for either corner, and the fixture maps them through its own csv, as the overlay does in fixture mode.

* ``research.matchup_evidence``: history (rank, games, period, scoring, not opponent-adjusted), changed (regulars vs the
  corners expected now, who is missing with the status, source and date, the replacements' rank), implication,
  ``forecast_treatment`` "contextual only; not in the forecast" — checked against the projection's feature list.
* The compare's verdict and the card's coin flip never use a less representative rank as the tiebreaker.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from league_lab import injury_feed as F

from league_lab_api import availability as AV
from league_lab_api import research
from league_lab_api.applib import capture, cards

from .conftest import SCRUBS, needs_db

ROOT = Path(__file__).resolve().parents[2]
ESPN_IF3 = Path(__file__).with_name("fixtures") / "espn_if3"
WILLIAMS, TUTEN = "00-0037240", "00-0040719"
HORN, JACKSON, LEE, EVANS = "00-0036944", "00-0035277", "00-0041063", "00-0038101"


@pytest.fixture
def corners_on_ir(monkeypatch):
    """The overlay on, reading the as-of fixture (Horn and Jackson on IR)."""
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN_IF3))
    monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    F.reset()
    AV._snap = None
    yield
    F.reset()
    AV._snap = None


# ------------------------------------------------------------------------------------------- pure: the forecast
def _list_literal(path: Path, name: str) -> list[str]:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise AssertionError(f"{name} not found in {path}")


def test_forecast_treatment_cites_the_projections_opponent_inputs():
    """The projection's inputs (src/league_lab/projections.py BASE_FEATURES; the personnel group is his own team's)
    hold the defense's points allowed and the betting lines, and nothing about who plays for the defense: so a corner
    change is "contextual only; not in the forecast". Adding an opponent-personnel input fails this test."""
    base = _list_literal(ROOT / "src" / "league_lab" / "projections.py", "BASE_FEATURES")
    for f in research.FORECAST_OPPONENT_FEATURES + research.FORECAST_LINE_FEATURES:
        assert f in base, f
    opp = {f for f in base if "opp" in f or "allowed" in f}
    assert opp == set(research.FORECAST_OPPONENT_FEATURES)
    src = (ROOT / "src" / "league_lab" / "feature_groups" / "personnel.py").read_text().lower()
    assert "corner" not in src and "opp_" not in src and "defender" not in src
    assert research.FORECAST_WORDS == "contextual only; not in the forecast"


# ------------------------------------------------------------------------------------------- pure: the card's coin flip
def _coin(caveat: str | None) -> tuple[dict, dict]:
    """The review's live numbers: Tuten 10.02 at FLEX, Williams 9.80 at Carolina (#31 of 32 vs WRs, 1 = gives up the
    most); Tuten's own matchup (Cincinnati, #20 vs RBs) is in the middle and says nothing."""
    d = {"slot": "FLEX", "gsis_id": TUTEN, "player_name": "Bhayshul Tuten", "position": "RB", "team": "JAX",
         "opponent": "CIN", "opp_rank": 20, "value": 10.02, "report_status": None,
         "alt_gsis_id": WILLIAMS, "alt_name": "Jameson Williams", "alt_player_name": "Jameson Williams",
         "alt_position": "WR", "alt_team": "DET", "alt_opponent": "CAR", "alt_opp_rank": 31, "alt_value": 9.80,
         "alt_report_status": None, "margin": 0.22, "p_win": 0.51}
    facts = {TUTEN: {"is_home": True}, WILLIAMS: {"is_home": False}}
    if caveat:
        facts[WILLIAMS].update(personnel_kind="changed", personnel_caveat=caveat)
    return d, facts


def test_coin_flip_before_the_rank_breaks_the_tie():
    d, facts = _coin(None)
    tb = cards.tiebreak(d, facts, {"CAR": "Panthers", "CIN": "Bengals"})
    assert tb is not None and tb["kind"] == "matchup" and tb["pick"] == "Tuten" and not tb["matchup_uncertain"]
    assert "give up the 2nd-fewest points to receivers" in cards.reason_line(d, facts, {"CAR": "Panthers"})


def test_coin_flip_with_the_corners_changed_is_not_settled_by_the_rank():
    cav = "Carolina's starting corners changed (Jackson and Horn are on injured reserve)"
    d, facts = _coin(cav)
    tb = cards.tiebreak(d, facts, {"CAR": "Panthers", "CIN": "Bengals"})
    assert tb is None or (tb["kind"] != "matchup" and tb["matchup_uncertain"])
    line = cards.reason_line(d, facts, {"CAR": "Panthers", "CIN": "Bengals"})
    assert line.startswith("Too close to call: the projection says Tuten by 0.2, the ranges say either; the matchup "
                           "rank does not settle it this week: Carolina's starting corners changed (Jackson and Horn "
                           "are on injured reserve)."), line
    assert "Go with Tuten on the matchup" not in line
    assert cards.matchup_uncertain(d, facts) and not cards.matchup_uncertain(*_coin(None))


def test_the_matchup_piece_stays_a_fact_but_never_a_reason():
    d, facts = _coin("Carolina's starting corners changed (Horn is out)")
    pieces = cards.reason_pieces(d, "alt_", facts[WILLIAMS], {"CAR": "Panthers"})
    m = [p for p in pieces if p[1].startswith("matchup")]
    assert m == [(0.0, "matchup_caveat", "Williams is on the road against the Panthers, who give up the 2nd-fewest "
                                         "points to receivers, but Carolina's starting corners changed (Horn is out)")]


def test_missing_words_group_by_status():
    m = [{"name": "Jaycee Horn", "code": "IR", "reason": "status"}, {"name": "Mike Jackson", "code": "IR", "reason": "status"},
         {"name": "Will Lee III", "code": None, "reason": "depth chart"}]
    assert cards.missing_words(m) == "Horn and Jackson are on injured reserve; Lee is no longer listed as a starter"
    p = {"kind": "changed", "regulars": [{}, {}, {}], "missing": m[:1]}
    assert cards.personnel_caveat(p, "Carolina") == "one of Carolina's regular corners changed (Horn is on injured reserve)"
    assert cards.personnel_caveat({"kind": "same", "regulars": [{}], "missing": []}, "Carolina") is None


# ------------------------------------------------------------------------------------------- the database: the review's case
def _names(ps) -> set[str]:
    return {p["name"] for p in ps}


@needs_db
def test_williams_compare_flags_the_changed_corners(client, corners_on_ir):
    r = client.get(f"/api/compare?league={SCRUBS}&a={WILLIAMS}&b={TUTEN}")
    assert r.status_code == 200, r.text
    d = r.json()
    ev = d["a"]["matchup_evidence"]
    assert ev["opponent"] == "CAR" and ev["opponent_name"] == "Carolina" and ev["week"] == d["week"]
    h = ev["history"]       # 1. historical results: games, scoring, period, not opponent-adjusted
    assert h["games"] >= 2 and h["period"].startswith(f"{d['season']}, weeks 1–") and h["scoring"] == "League of Scrubs scoring"
    assert h["adjusted"] is False and h["adjusted_words"] == "not adjusted for the offenses it faced"
    assert h["rank_most"] + h["tough_rank"] == h["n"] + 1 and h["words"].endswith("points to receivers")
    c = ev["changed"]       # 2. what changed: both regulars on IR, with the source and the date; the replacements
    assert c["kind"] == "changed" and _names(c["regulars"]) == {"Jaycee Horn", "Mike Jackson"}
    miss = {m["gsis_id"]: m for m in c["missing"]}
    assert set(miss) == {HORN, JACKSON}
    for m in miss.values():
        assert (m["status"], m["code"], m["source"], m["date_words"], m["reason"]) == ("IR", "IR", "ESPN", "Sep 30", "status")
        assert m["as_of"].startswith("2026-09-30T20:15")
    exp = {e["gsis_id"]: e for e in c["expected"]}
    assert {LEE, EVANS} <= set(exp) and HORN not in exp and JACKSON not in exp
    assert exp[EVANS]["replaces"] == "Mike Jackson" and exp[EVANS]["slot"] == "LCB" and exp[LEE]["slot"] == "RCB"
    for g in (LEE, EVANS):
        assert exp[g]["rank"] is None and exp[g]["rank_words"] == "unranked (insufficient snaps)" and exp[g]["is_new"]
    assert c["depth_chart_at"].startswith("2026-09-26")
    # 3. the implication, and the forecast's treatment said honestly
    assert ev["implication"] == {"kind": "less_representative",
                                 "words": "the historical rank is less representative this week: both starting corners changed"}
    assert ev["forecast_treatment"]["words"] == "contextual only; not in the forecast"
    assert "opp_allowed_std" in ev["forecast_treatment"]["features"]
    assert ev["matchup_uncertain"] is True
    s1, s2 = ev["sentences"]
    assert s1.startswith("Carolina gives up the ") and "but with different corners: Jackson and Horn are on injured reserve (ESPN, Sep 30)" in s1
    assert "Evans" in s1 and "Lee" in s1 and "unranked" in s1
    assert "does not settle a close call" in s2 and "contextual only; not in the forecast" in s2
    # the comparison's call is not the matchup rank
    assert "the matchup leans" not in d["verdict"] and "the matchup agrees" not in d["verdict"]
    assert "the matchup rank does not settle it this week: Carolina's starting corners changed" in d["verdict"]
    # Tuten's side: a running back's matchup is history only, said so
    t = d["b"]["matchup_evidence"]
    assert t["implication"]["kind"] == "unchecked" and t["matchup_uncertain"] is False and len(t["sentences"]) == 2


@needs_db
def test_a_defense_that_kept_its_corners_reads_the_rank_stands(client):
    """The clone's own state (no overlay): Carolina's depth chart still starts Jackson and Horn — the same corners."""
    d = client.get(f"/api/compare?league={SCRUBS}&a={WILLIAMS}&b={TUTEN}").json()
    ev = d["a"]["matchup_evidence"]
    assert ev["changed"]["kind"] == "same" and ev["changed"]["missing"] == []
    assert ev["implication"] == {"kind": "stands", "words": "the historical rank stands: the same corners"}
    assert ev["matchup_uncertain"] is False and ev["caveat"] is None
    assert "The rank stands: the same corners." in ev["sentences"][1]
    assert "does not settle" not in d["verdict"]


@needs_db
def test_the_card_and_the_cornerback_rows_carry_the_evidence(client, corners_on_ir):
    card = client.get(f"/api/player/{WILLIAMS}?league={SCRUBS}&team=6").json()
    ev = card["matchup_evidence"]
    assert ev["opponent"] == "CAR" and ev["implication"]["kind"] == "less_representative"
    assert ev["history"]["scoring"].endswith("scoring") and len(ev["sentences"]) == 2
    cb = client.get(f"/api/matchups/cb?league={SCRUBS}&team=6").json()
    row = next(r for r in cb["matchups"] if r["gsis_id"] == WILLIAMS)
    assert row["matchup_evidence"]["matchup_uncertain"] is True
    assert {e["gsis_id"] for e in row["matchup_evidence"]["changed"]["expected"]} >= {LEE, EVANS}
    tes = [r for r in cb["matchups"] if r["position"] == "TE"]
    assert all(r["matchup_evidence"] is None for r in tes)


@needs_db
def test_the_cards_carry_the_flag_for_my_week(corners_on_ir):
    dec, _ = capture(cards.decision_cards, SCRUBS, 6, cards.decision_week(2026), 2026)
    assert "matchup_uncertain" in dec
    for d in dec.to_dict("records"):
        assert d["matchup_uncertain"] == (WILLIAMS in (d["gsis_id"], d["alt_gsis_id"])), d["player_name"]


# ------------------------------------------------------------------------------------------- pure: the depth chart path
def test_a_depth_chart_that_already_moved_on_flags_the_missing_regulars(monkeypatch):
    """The live state the review saw (Carolina's depth chart after the IR moves: Evans and Lee outside, Horn and Jackson
    gone): the regulars are missing because the depth chart no longer starts them — with the overlay's status when it
    has one, "no longer listed as a starter" when it does not. The SQL answers are stand-ins (no database)."""
    import pandas as pd

    at = pd.Timestamp("2026-10-03T12:00:00Z")
    answers = {
        "mart_cb_rankings\nwhere season = %s and window_label = 'season'": pd.DataFrame(
            [{"defense": "CAR", "gsis_id": JACKSON, "defender_name": "Mike Jackson", "coverage_snaps": 110.0, "games_at_cb": 3, "team_games": 3},
             {"defense": "CAR", "gsis_id": HORN, "defender_name": "Jaycee Horn", "coverage_snaps": 101.0, "games_at_cb": 3, "team_games": 3},
             {"defense": "CAR", "gsis_id": LEE, "defender_name": "Will Lee III", "coverage_snaps": 40.0, "games_at_cb": 3, "team_games": 3}]),
        "from analytics.mart_cb_matchups": pd.DataFrame(
            [{"defense": "CAR", "depth_chart_at": at, "lcb_gsis_id": EVANS, "lcb_name": "Akayleb Evans", "rcb_gsis_id": LEE,
              "rcb_name": "Will Lee III", "nb_gsis_id": "00-0039380", "nb_name": "Chau Smith-Wade"}]),
        "mart_matchup_cb_context": pd.DataFrame(columns=["defense", "snapshot_at", "gsis_id", "defender_name", "depth_position", "depth_rank"]),
        "window_label = 'two_seasons'": pd.DataFrame(columns=["gsis_id", "quality_rank", "quality_label", "n_ranked"]),
    }

    def fake(sql, params=()):
        return next(v for k, v in answers.items() if k in sql).copy()

    monkeypatch.setattr(cards, "query", fake)
    monkeypatch.setattr(cards, "missing_relations", lambda names: [])
    ir = {HORN: {"status": "IR", "code": "IR", "cannot_play": True, "source": "Sleeper", "as_of": "2026-09-30T21:00:00Z"}}
    p = cards.corner_personnel(["CAR"], 2026, 4, ir)["CAR"]
    assert p["kind"] == "changed" and _names(p["regulars"]) == {"Mike Jackson", "Jaycee Horn"}   # Lee: 40 of 110 snaps
    miss = {m["gsis_id"]: m for m in p["missing"]}
    assert (miss[HORN]["reason"], miss[HORN]["source"]) == ("status", "Sleeper")
    assert (miss[JACKSON]["reason"], miss[JACKSON]["status"]) == ("depth chart", None)
    assert [e["name"] for e in p["expected"] if e["is_new"]] == ["Akayleb Evans", "Will Lee III", "Chau Smith-Wade"]
    assert cards.personnel_caveat(p, "Carolina") == ("Carolina's starting corners changed (Jackson is no longer listed "
                                                      "as a starter; Horn is on injured reserve)")
    same = cards.corner_personnel(["CAR"], 2026, 4, {})["CAR"]
    assert same["kind"] == "changed" and all(m["reason"] == "depth chart" for m in same["missing"])
