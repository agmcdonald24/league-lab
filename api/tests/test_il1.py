"""IL-1 (Wave I-L): the advanced-data layer on the API — the drawer's Role block (league_lab.roles) and the Stats
Explorer's Next Gen Stats columns (analytics.mart_player_ngs_week): denominator-weighted windows, — under NGS's
qualification (never 0), the presets."""

from __future__ import annotations

import re
from urllib.parse import urlencode

import pytest

from league_lab_api import player as PL
from league_lab_api import stats as ST

from .conftest import DYNASTY, SCRUBS, needs_db

pytestmark = needs_db

NGS_IDS = ["time_to_throw", "ngs_cpoe", "ryoe_per_attempt", "separation", "yac_over_expected"]
NEVER = re.compile(r"regress|unsustainable|due for|will continue|probabilit", re.I)
A_RATE = re.compile(r"\b(targets|carries|points|yards) a (game|week)\b")      # the copy standard: "per game"


def _stats(client, **q) -> dict:
    r = client.get("/api/players?" + urlencode({"league": SCRUBS, **q}))
    assert r.status_code == 200, r.text
    return r.json()


def _words(sec: dict) -> str:
    return " ".join(b.get("text") or "" for b in sec["blocks"])


# ------------------------------------------------------------------------------------------------- the Role block
@pytest.mark.parametrize("league,team,gsis", [(SCRUBS, 2, "00-0036963"), (DYNASTY, 12, "00-0036919"),
                                              (SCRUBS, 2, "00-0038824")])
def test_the_card_carries_the_role_block_in_the_copy_standard(client, league, team, gsis):
    d = client.get(f"/api/player/{gsis}?league={league}&team={team}").json()
    sec = d["sections"]["role"]
    assert sec["title"].startswith("**Role**")
    text = _words(sec)
    assert "Opportunity vs production:" in text and "Contingent upside:" in text, text
    assert re.search(r"\*\*(Too early to say|Role steady|\w[\w -]* (up|down)):", text), text
    assert not NEVER.search(text) and not A_RATE.search(text), text
    assert any(b["kind"] == "caption" and "not a forecast" in b["text"] for b in sec["blocks"])
    # the console's five sections are untouched (test_parity compares them); the role block is the sixth
    assert list(d["sections"])[:5] == ["usage", "projection", "availability", "value", "signals"]


def test_a_kicker_gets_the_reason_not_a_blank(client):
    d = client.get(f"/api/player/00-0035358?league={SCRUBS}&team=2").json()         # Scrubs 2's kicker
    sec = d["sections"]["role"]
    assert [b["kind"] for b in sec["blocks"]] == ["unavailable"]
    assert "quarterbacks, running backs, receivers and tight ends" in sec["blocks"][0]["text"]


def test_the_role_block_on_a_season_with_games_names_or_holds_each_change(sql):
    """2025 through week 10 (enough games for the spread rule): every metric is named or steady with both numbers."""
    row = sql("""select gsis_id, team, position from analytics.fct_player_game
                 where season = 2025 and season_type = 'REG' and week <= 10 and position = 'WR' and played
                 group by 1, 2, 3 having count(*) >= 8 order by sum(targets) desc limit 1""")[0]
    sec = PL._section("Role")
    PL._role_blocks(sec, SCRUBS, row["gsis_id"], "WR", row["team"], 2025, 10, "League of Scrubs")
    text = _words(sec)
    head = sec["blocks"][0]["text"]
    assert re.match(r"\*\*(Role steady: |(Targets|Carries|Snap share|Red-zone touches) (up|down): )", head), head
    for m in ("Carries", "Targets", "Red-zone touches", "Snap share"):
        assert re.search(rf"{m} (up|down|steady): .* in his last 2, .* in the \d+ before", text), (m, text)
    assert "of their fantasy points in League of Scrubs scoring (weeks " in text
    assert not NEVER.search(text)


# ------------------------------------------------------------------------------------------------- the Stats columns
def test_ngs_columns_are_derived_with_their_inventory_rows_and_in_the_presets():
    for cid in NGS_IDS:
        c = ST.CAT[cid]
        assert c["status"] == "derived" and c["source"] == ST.NGS and "never a mean of means" in c["definition"], cid
        assert "unknown, not zero" in c["reason"], cid
    presets = {p["key"]: p for p in ST.PRESETS}
    assert {"time_to_throw", "cpoe"} <= set(presets["qb"]["columns"])
    assert "ryoe_per_attempt" in presets["rb"]["columns"]
    assert {"separation", "yac_over_expected"} <= set(presets["wrte"]["columns"])


def test_time_to_throw_is_the_attempt_weighted_mean_and_unqualified_is_null(client, sql):
    d = _stats(client, window="season", season=2026, position="QB", min_games=0, limit=1000)
    cat = {c["id"]: c for c in d["catalogue"]}
    assert cat["time_to_throw"]["available"] and "15+ pass attempts" in cat["time_to_throw"]["reason"]
    rows = {p["gsis_id"]: p for p in d["players"]}
    ngs = sql("""select gsis_id, sum(avg_time_to_throw * ngs_pass_attempts) / sum(ngs_pass_attempts) as ttt,
                        sum(completion_percentage_above_expectation * ngs_pass_attempts) / sum(ngs_pass_attempts) as cpoe,
                        sum(ngs_pass_attempts) as att, count(*) as weeks
                 from analytics.mart_player_ngs_week
                 where season = 2026 and week between 1 and 18 and has_passing group by 1""")
    by = {r["gsis_id"]: r for r in ngs}
    checked = 0
    for gid, r in by.items():
        if gid not in rows:
            continue
        assert rows[gid]["time_to_throw"] == pytest.approx(round(float(r["ttt"]), 2), abs=0.006), gid
        assert rows[gid]["ngs_cpoe"] == pytest.approx(round(float(r["cpoe"]), 2), abs=0.006), gid
        assert rows[gid]["ngs_pass_attempts"] == r["att"] and rows[gid]["ngs_pass_weeks"] == r["weeks"]
        checked += 1
    assert checked >= 30
    # a QB with games and no NGS week: null (the screen's —), never 0
    unq = [p for gid, p in rows.items() if gid not in by and (p.get("games") or 0) > 0]
    assert unq and all(p["time_to_throw"] is None and p["ngs_pass_weeks"] == 0 for p in unq)
    assert all(p["time_to_throw"] != 0 for p in rows.values())


def test_a_window_reads_only_its_weeks(client, sql):
    """Week 2 alone: RYOE per carry is that week's NGS value (one week: the weighted mean is the value)."""
    d = _stats(client, window="weeks", weeks="2-2", season=2026, position="RB", min_games=0, limit=1000)
    rows = {p["gsis_id"]: p for p in d["players"]}
    wk = sql("""select gsis_id, rush_yards_over_expected_per_att as v, ngs_rush_attempts as n
                from analytics.mart_player_ngs_week where season = 2026 and week = 2 and has_rushing""")
    hits = [r for r in wk if r["gsis_id"] in rows]
    assert hits
    for r in hits:
        assert rows[r["gsis_id"]]["ryoe_per_attempt"] == pytest.approx(round(float(r["v"]), 2), abs=0.006)
        assert rows[r["gsis_id"]]["ngs_rush_weeks"] == 1 and rows[r["gsis_id"]]["ngs_rush_attempts"] == r["n"]


def test_receiving_ngs_weights_separation_by_targets_and_yacoe_by_receptions(client, sql):
    d = _stats(client, window="season", season=2025, position="WR", min_games=0, limit=1000)
    rows = {p["gsis_id"]: p for p in d["players"]}
    ngs = sql("""select gsis_id, sum(avg_separation * ngs_targets) / sum(ngs_targets) as sep,
                        sum(avg_yac_above_expectation * ngs_receptions)
                          / nullif(sum(ngs_receptions) filter (where avg_yac_above_expectation is not null), 0) as yacoe
                 from analytics.mart_player_ngs_week
                 where season = 2025 and week between 1 and 18 and has_receiving group by 1""")
    checked = 0
    for r in ngs:
        if r["gsis_id"] in rows and r["yacoe"] is not None:
            assert rows[r["gsis_id"]]["separation"] == pytest.approx(round(float(r["sep"]), 2), abs=0.006)
            assert rows[r["gsis_id"]]["yac_over_expected"] == pytest.approx(round(float(r["yacoe"]), 2), abs=0.006)
            checked += 1
    assert checked >= 50


def test_ngs_columns_say_why_outside_the_regular_season_and_before_2018(client):
    post = {c["id"]: c for c in _stats(client, window="season", season=2025, season_type="POST", position="QB")["catalogue"]}
    assert not post["time_to_throw"]["available"] and "regular season" in post["time_to_throw"]["reason"]
    old = {c["id"]: c for c in _stats(client, window="season", season=2017, position="RB")["catalogue"]}
    assert not old["ryoe_per_attempt"]["available"] and "2018" in old["ryoe_per_attempt"]["reason"]


# ------------------------------------------------------------------------------------------------- the e2e recording
WAN = "00-0038117"            # Wan'Dale Robinson: a Scrubs free agent the shared fixtures already have a card for


@pytest.mark.skipif(not __import__("os").environ.get("IL1_RECORD"), reason="records web/fixtures/il1 (IL1_RECORD=1)")
def test_record_e2e_answers(client):
    """The answers web/e2e/il1 replays (League of Scrubs roster 2, this clone, the pinned clock): Wan'Dale Robinson's
    card with its Role block, and the Stats frame of the QB preset. Re-record:
    cd api && IL1_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_il1.py -k record"""
    import json

    from league_lab_api.settings import ROOT
    out_dir = ROOT / "web" / "fixtures" / "il1"
    out_dir.mkdir(parents=True, exist_ok=True)
    card = client.get(f"/api/player/{WAN}?league={SCRUBS}&team=2")
    frame = client.get("/api/players?" + urlencode({"league": SCRUBS, "limit": 1000, "position": "QB", "window": "season"}))
    assert card.status_code == 200 and frame.status_code == 200
    assert card.json()["sections"]["role"]["blocks"]
    (out_dir / f"player_{SCRUBS}_{WAN}.json").write_text(json.dumps(card.json(), separators=(",", ":"), default=str) + "\n")
    (out_dir / "players_qb_season.json").write_text(json.dumps(frame.json(), separators=(",", ":"), default=str) + "\n")
