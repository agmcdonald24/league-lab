"""Wave I-A, IA-1 — "say it like a person would" (My Week, Trends, Matchups, Compare).

* `shortName` (web/src/lib/names.svelte.ts): run under Node (type stripping; the module's `$state` rune stubbed), the cases
  the slot list meets — a suffix, a two-word last name, initials, a defense, two players who would read the same.
* the card's reason sentence (`app/lib/cards.reason_line`, shared with the Streamlit console): three cards built from the
  fixture weeks' own numbers — home / away, a role drop, a close call — plus an injury tiebreak, pinned word for word;
  then the API's cards on the database (both house leagues): every card has a reason, it is the card's second block,
  and the odds moved to the small print.
* Trends' sentence (`research.trend_why` / `trend_cause`) and the new per-row fields on /api/trends; the headshot and team
  on My Week's lineup rows.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from league_lab_api import research
from league_lab_api.applib import cards

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db

WEB = Path(__file__).resolve().parents[2] / "web"
NICKS = {"IND": "Colts", "SEA": "Seahawks", "LAC": "Chargers", "WAS": "Commanders", "GB": "Packers", "TB": "Buccaneers",
         "MIA": "Dolphins", "MIN": "Vikings", "SF": "49ers", "DEN": "Broncos", "NYG": "Giants", "ARI": "Cardinals"}


# ------------------------------------------------------------------------------ shortName (the web's helper)
SHORT_CASES = [
    (("Justin Jefferson", "WR", []), "J. Jefferson"),
    (("Michael Penix Jr.", "QB", []), "M. Penix Jr."),
    (("Amon-Ra St. Brown", "WR", []), "A. St. Brown"),
    (("Ja'Marr Chase", "WR", []), "J. Chase"),
    (("D.J. Moore", "WR", []), "D.J. Moore"),                         # already initials
    (("Buffalo Bills", "DEF", []), "Buffalo Bills"),                  # a defense keeps its name
    (("Cher", None, []), "Cher"),                                    # one word
    (("Michael Wilson", "WR", ["Emanuel Wilson", "Michael Wilson"]), "M. Wilson"),   # different initials: no clash
    (("Jameson Williams", "WR", ["Javonte Williams"]), "Jam. Williams"),           # same initial, same last name
    (("Javonte Williams", "RB", ["Jameson Williams", "Javonte Williams"]), "Jav. Williams"),
    (("Kenneth Walker III", "RB", ["Kyle Walker III"]), "Ke. Walker III"),
    (("Josh Allen", "QB", ["Josh Allen"]), "J. Allen"),               # himself in the list is not a clash
    ((None, None, []), ""),
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_short_name_cases(tmp_path):
    harness = tmp_path / "short.mjs"
    harness.write_text(
        "globalThis.$state = (v) => v;\n"
        f"const m = await import({json.dumps(str(WEB / 'src' / 'lib' / 'names.svelte.ts'))});\n"
        f"const cases = {json.dumps([list(c) for c, _ in SHORT_CASES])};\n"
        "console.log(JSON.stringify(cases.map(([n, p, o]) => m.shortName(n, p, o))));\n")
    out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(harness)], capture_output=True, text=True,
                         timeout=60)
    if out.returncode != 0 and "strip-types" in out.stderr:
        pytest.skip("this node cannot strip TypeScript types")
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [want for _, want in SHORT_CASES]


# ------------------------------------------------------------------------------ the card's reason
def card(**kw) -> dict:
    base = {"slot": "RB2", "gsis_id": "A", "alt_gsis_id": "B", "position": "RB", "alt_position": "RB",
            "report_status": None, "alt_report_status": None}
    return {**base, **kw}


def test_reason_home_and_away():
    """A clear call where the matchups split them: one at home against a soft run defense, one on the road against a
    tough one (the dynasty's week-4 numbers: IND #2 vs RB, SEA #26 vs RB)."""
    d = card(player_name="Jacory Croskey-Merritt", alt_name="Omarion Hampton", team="WAS", alt_team="LAC",
             opponent="IND", opp_rank=2, alt_opponent="SEA", alt_opp_rank=26, margin=2.4, p_win=0.66)
    facts = {"A": {"is_home": True}, "B": {"is_home": False}}
    assert cards.reason_line(d, facts, NICKS) == (
        "Croskey-Merritt is at home against the Colts, who give up the 2nd-most points to running backs; "
        "Hampton is on the road against the Seahawks, who give up the 7th-fewest points to running backs.")


def test_reason_role_drop():
    """Scrubs roster 2, RB2 (week 4): Hampton's carries up, Croskey-Merritt's down — from their games 1 and 2."""
    d = card(player_name="Omarion Hampton", alt_name="Jacory Croskey-Merritt", team="LAC", alt_team="WAS",
             opponent="SEA", opp_rank=26, alt_opponent="IND", alt_opp_rank=2, margin=2.09, p_win=0.622075)
    facts = {"A": {"is_home": False, "carry_shares": [0.57, 0.72], "carry_share_std": 0.66},
             "B": {"is_home": True, "carry_shares": [0.50, 0.38], "carry_share_std": 0.44}}
    assert cards.reason_line(d, facts, NICKS) == (
        "Hampton's share of the carries rose from 57% to 72% last game; "
        "Croskey-Merritt's share of the carries fell from 50% to 38% last game.")
    # three games falling in a row reads as a run, with the first and last share
    facts["B"]["carry_shares"] = [0.31, 0.25, 0.19]
    assert "Croskey-Merritt's share of the carries has dropped three games running (31% → 19%)" in cards.reason_line(d, facts, NICKS)


def test_reason_close_call():
    """Scrubs roster 2, FLEX2 (week 4): 9.20 vs 9.19, 51% — too close to call; the matchup breaks the tie."""
    d = card(slot="FLEX2", player_name="Michael Wilson", position="WR", alt_name="Jacory Croskey-Merritt", team="ARI",
             alt_team="WAS", opponent="NYG", opp_rank=11, alt_opponent="IND", alt_opp_rank=2, margin=0.01, p_win=0.508825)
    facts = {"A": {"is_home": False, "target_shares": [0.19, 0.27]}, "B": {"is_home": True, "carry_shares": [0.50, 0.38]}}
    assert cards.reason_line(d, facts, NICKS) == (
        "Too close to call: the projection has them level, the ranges say either. Go with Croskey-Merritt on the matchup: "
        "he is at home against the Colts, who give up the 2nd-most points to running backs.")
    # an injury breaks the tie first; same last names read in full
    d2 = card(player_name="Emanuel Wilson", alt_name="Michael Wilson", alt_position="WR", margin=0.46, p_win=0.51,
              alt_report_status="Questionable")
    assert cards.reason_line(d2, {"B": {"practice_status": "Limited Participation in Practice"}}, NICKS) == (
        "Too close to call: the projection says Emanuel Wilson by 0.5, the ranges say either. Go with Emanuel Wilson: "
        "Michael Wilson is questionable (limited in practice).")


def test_reason_without_the_extra_read():
    """No REASON_SQL row (the read failed or the mart is not built): the card's own columns still give a sentence,
    and nothing at all still says the gap — never an empty line."""
    d = card(player_name="Bhayshul Tuten", alt_name="Kenny Gainwell", opponent="CIN", opp_rank=24, alt_opponent="GB",
             alt_opp_rank=15, margin=1.2, p_win=0.6)
    assert cards.reason_line(d) == ("Tuten is against CIN, who give up the 9th-fewest points to running backs, but the "
                                    "projection still has him 1.2 points ahead.")
    assert cards.reason_line(card(player_name="A One", alt_name="B Two", margin=1.2, p_win=0.6)) == (
        "Nothing in the matchups or the roles splits them: the projection has One 1.2 points ahead.")


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_api_cards_say_why(client, league):
    d = client.get(f"/api/my-week?league={league}&team={ANDREW[league]}").json()
    for c in d["cards"]:
        if c["alt_name"] is None:
            continue
        assert c["why"], c
        kinds = [b["kind"] for b in c["blocks"]]
        assert kinds[:2] == ["markdown", "markdown"] and kinds[-1] == "caption"
        assert c["blocks"][1]["text"] == c["why"]                       # the reason is the line under the call
        assert "outscores" not in c["why"] and "**" not in c["why"]
        small = c["blocks"][-1]["text"]
        assert f"{c['margin']:.2f} apart" in small                      # the odds and the numbers are the small print
        if c.get("p_win") is not None:
            assert "outscores" in small
    # the slot list: a headshot and a team on every row (null when unknown, never missing)
    for r in d["lineup"] + d["lineup_full"]:
        assert "headshot_url" in r and "team" in r
    assert any(r["headshot_url"] for r in d["lineup"] if r["gsis_id"])


# ------------------------------------------------------------------------------ Trends
def test_trend_sentences():
    below = {"position": "WR", "ppg": 3.6, "xppg": 10.5, "gap": -6.9, "work_games": 3, "tds": 0, "rz_targets": 4}
    assert research.trend_why(below) == "Getting the targets of a 10.5-point player, scoring 3.6: no touchdowns on 4 red-zone targets."
    one = {**below, "rz_targets": 1, "target_shares": [0.25, 0.22, 0.12]}
    assert research.trend_cause(one) == "his share of the targets fell from 25% to 12%"
    qb = {"position": "QB", "ppg": 25.2, "xppg": 14.9, "gap": 10.3, "work_games": 2, "pass_tds": 4}
    assert research.trend_why(qb) == "Getting the throws and runs of a 14.9-point player, scoring 25.2: 4 touchdown passes in 2 games."
    hot = {"position": "RB", "ppg": 28.0, "xppg": 18.6, "gap": 9.4, "work_games": 2, "tds": 4, "rz_carries": 9, "rz_targets": 2}
    assert research.trend_why(hot) == ("Getting the carries and targets of an 18.6-point player, scoring 28.0: "
                                       "4 touchdowns in 2 games on 11 red-zone chances.")
    # no cause the numbers support: no guess
    assert research.trend_why({"position": "TE", "ppg": 8.0, "xppg": 11.2, "gap": -3.2, "work_games": 2, "tds": 1}) == (
        "Getting the targets of an 11.2-point player, scoring 8.0.")
    assert research.trend_why({"position": "WR", "ppg": None, "xppg": 4.0}) is None


@needs_db
def test_api_trends_rows_carry_the_work(client, sql):
    d = client.get(f"/api/trends?league={DYNASTY}&view=all&limit=200&metrics=none&min_games=2").json()
    rows = d["players"]
    assert rows
    for p in rows:
        for k in (*research.WORK_COLS, "why", "cause"):
            assert k in p
        if p["ppg"] is not None and p["xppg"] is not None:
            assert p["why"].startswith("Getting ")
    # one row checked by hand against fct_player_game: targets a game over the season
    p = next(p for p in rows if p["position"] == "WR" and p["targets_pg"] is not None)
    want = sql("""select avg(targets) as t from analytics.fct_player_game
                  where gsis_id = %s and season = %s and season_type = 'REG' and played""", (p["gsis_id"], d["season"]))[0]["t"]
    assert p["targets_pg"] == pytest.approx(float(want), abs=0.05)
    assert sum(1 for p in rows if p["cause"]) > 0
