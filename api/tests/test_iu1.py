"""Wave I-U, IU-1 — the Trade Finder searches on the basis; the basis waiver move nets its drop.

(1) The Finder proposes packages on the replacement frame (`stats.search_basis`), and on the switch back to the
roster-only search (`LEAGUE_LAB_FINDER_SEARCH=roster`) the worth-proposing list is never longer — the rule committed in
docs/handbacks/IU-1.md before its numbers. (3) The best waiver move on the frame nets a drop the way the roster-only move
does (`waivers.choose_drops`: the drop's cost beyond his lineup loss) and its sentence names the drop and the netting:
the Folk case (tests/test_ii1.py's clone rosters). Meaning, never today's numbers beyond the case's own."""

from __future__ import annotations

import pytest

from league_lab_api import decisions as D

from .conftest import SCRUBS, needs_db
from .test_ii1 import FOLK, REICHARD, STAFFORD, YOUNG, folk_context


@pytest.fixture(autouse=True)
def _fresh():
    D.clear_memo()
    yield
    D.clear_memo()


def _worth(p: dict) -> list[tuple]:
    return [(r["partner_team"], tuple(x["sleeper_id"] for x in r["give"]), tuple(x["sleeper_id"] for x in r["get"]))
            for r in p["partners"] if r["decision"]["recommendation"]["credible"]]


@needs_db
def test_the_finder_searches_on_the_basis_and_finds_no_fewer_worth_proposing(client, monkeypatch):
    p = client.get("/api/trades/partners", params={"league": SCRUBS, "team": 2}).json()
    assert p["search"]["search_basis"] == "replacement"
    assert "rank_partners" not in p["search"]                       # IF-2's roster-only ladder is not computed
    for r in p["partners"]:                                         # every row raises both lineups on the basis
        assert r["decision"]["mine"]["gain_window"] > 0 and r["decision"]["theirs"]["gain_window"] > 0
    D.clear_memo()
    monkeypatch.setenv(D.IU1_SEARCH_ENV, "roster")
    q = client.get("/api/trades/partners", params={"league": SCRUBS, "team": 2}).json()
    assert q["search"]["search_basis"] == "roster"
    assert len(_worth(p)) >= len(_worth(q))


def test_the_alternative_sentence_says_the_drop_and_its_netting_once():
    a = {"kind": "waiver", "player": {"player_name": "Washington Commanders", "position": "DEF"},
         "drop": {"player_name": "Jacory Croskey-Merritt"}, "gain_week": 0.0, "gain_window": 1.5,
         "drop_cost": {"piece": "season_value", "cost": 5.19, "excess": 5.19}}
    w = D.alternative_words(a, "weeks 5–8", "window")
    assert w == ("the Washington Commanders defense claim gives +1.5 over weeks 5–8 "
                 "(drop Jacory Croskey-Merritt; netted: his season value above replacement, 5.2)")
    assert D.iu1_drop_words(a) == ", drop Jacory Croskey-Merritt (netted: his season value above replacement, 5.2)"
    a["drop_cost"] = {"piece": None, "cost": 0.0, "excess": 0.0}            # a drop that costs nothing more
    assert D.alternative_words(a, "weeks 5–8", "window").endswith("(drop Jacory Croskey-Merritt)")
    assert D.iu1_drop_words({"drop": None}) == ""
    # the PO's clause about Waivers' first claim reads what he adds on the frame BEFORE his drop is netted: a pick whose
    # gain and drop cost cancel (net 0) does not fill an empty spot, and the sentence does not say it does
    rop = {"player": {"player_name": "Jacoby Brissett"}, "covered_window": 0.0, "covered_gross_window": 5.0}
    assert "already counted" not in D.alternative_words({**a, "roster_only_pick": rop}, "weeks 5–8", "window")
    rop["covered_gross_window"] = 0.0
    assert D.alternative_words({**a, "roster_only_pick": rop}, "weeks 5–8", "window").endswith(
        "; Jacoby Brissett is already counted in every number here (he fills a starting spot that is empty)")


@needs_db
def test_the_folk_case_nets_the_drop_on_the_basis(monkeypatch):
    """The clone rosters (MacZaddy's backup QBs kept): a full roster. IT-1's basis move dropped the cheapest bench
    player by the market (Croskey-Merritt, 5.2 of season value above replacement, not netted); netted, the same claim
    drops Bryce Young (no starts, no season value, no backup cover) — and the partner's roster-only pick, a kicker the
    frame already uses to cover a bye, is priced over the next free kicker and netted for the running back it drops."""
    folk_context(monkeypatch, as_reviewed=False)
    out = D.evaluate(SCRUBS, 2, 3, [FOLK], [STAFFORD, REICHARD])
    alt = out["card"]["waiver_alternative"]
    mine, theirs = alt["mine"], alt["theirs"]
    print("\nmine:", mine["words"], mine.get("drop_cost"), "\ntheirs:", theirs["words"], theirs.get("drop_cost"))
    print("decision:", out["decision"]["alternative"]["words"], "\n", out["decision"]["recommendation"]["words"])
    assert mine["source"] == "basis search" and (mine["drop"] or {}).get("sleeper_id") == YOUNG
    dc = mine["drop_cost"]
    assert dc["excess"] == 0.0 and dc["net_window"] == mine["covered_window"] == mine["gain_window"]
    assert "drop Bryce Young" in mine["words"]
    # the roster-only pick kept beside it, priced on the frame (he fills an empty starting spot: 0)
    assert mine["roster_only_pick"]["covered_window"] == pytest.approx(0.0, abs=0.05)
    assert mine["roster_only_pick"]["covered_gross_window"] == pytest.approx(0.0, abs=0.05)
    # the partner: the roster-only pick netted on the frame (the drop's season value beyond his lineup loss)
    tdc = theirs.get("drop_cost") or {}
    assert tdc.get("piece") == "season_value" and tdc["excess"] > 0
    assert theirs["covered_window"] == pytest.approx(tdc["net_window"], abs=0.01)
    name = theirs["drop"]["player_name"]
    assert f"drop {name} (netted: his season value above replacement, {tdc['cost']:.1f})" in str(out["decision"])
    # never a nested parenthesis in a sentence that names a drop
    for s in (mine["words"], theirs["words"], out["decision"]["alternative"]["words"]):
        assert "((" not in s and "))" not in s
