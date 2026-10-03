"""The API says what the Streamlit page says: each page is rendered headlessly with Streamlit's AppTest
(tests/streamlit_twin.py, in the repository's environment) and compared with the API's JSON —
the cards block by block, the lineup tables row by row, every player-card section's metrics and sentences.
Links differ on purpose (the page's `Player?…&id=` vs the app's `/player/<id>`), so they are compared as text.
Set LL_SKIP_PARITY=1 to skip (each page render takes 5-20 s)."""

from __future__ import annotations

from urllib.parse import parse_qs

import pytest

from league_lab_api.applib import strip_links

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db, twin
from .test_player import CASES

pytestmark = needs_db


def name(cell) -> str | None:
    """The page's player column is a LinkColumn: `Player?name=<name>&id=…` (display text = the name)."""
    if isinstance(cell, str) and cell.startswith("Player?"):
        return parse_qs(cell.split("?", 1)[1]).get("name", [None])[0]
    return cell


def norm_blocks(blocks: list[dict]) -> list:
    out = []
    for b in blocks:
        if b["kind"] == "metrics":
            out.append(("metrics", [(m["label"], m["value"], m.get("delta") or "") for m in b["metrics"]]))
        else:
            kind = "caption" if b["kind"] == "unavailable" else b["kind"]
            out.append((kind, strip_links(b["text"])))
    return out


@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_my_week_is_the_home_page(client, league):
    team = ANDREW[league]
    page = twin("home", league, str(team))
    api = client.get(f"/api/my-week?league={league}&team={team}").json()
    # the cards: same count, same blocks in the same order, same words and numbers
    assert len(page["cards"]) == len(api["cards"])
    for drawn, card in zip(page["cards"], api["cards"], strict=True):
        assert norm_blocks(drawn) == norm_blocks(card["blocks"])
        # Wave I-A (IA-1): the reason sentence sits under the call on both (cards.reason_line), the odds in the small print
        if card["alt_name"]:
            assert norm_blocks(drawn)[1] == ("markdown", strip_links(card["why"]))
            assert norm_blocks(drawn)[-1][0] == "caption" and "apart" in norm_blocks(drawn)[-1][1]
    if not api["cards"]:
        assert strip_links(page["notice"] or "") == strip_links(api["notice"] or "")
    # the record line and the league line are markdown lines of the page
    assert api["summary"] in page["markdown"]
    assert api["league_line"] in page["markdown"]
    # the lineup tables: the page's dataframes (whatever columns its detail level shows) row by row
    assert [(r["slot"], name(r["player_name"]), r["player_value"]) for r in page["lineup"]] == [
        (x["slot"], x["player_name"], x["value"]) for x in api["lineup"]]
    assert [(r["slot"], name(r["player_name"]), r["player_value"]) for r in page["lineup_full"]] == [
        (x["slot"], x["player_name"], x["value"]) for x in api["lineup_full"]]
    if page["lineup"] and "flag" in page["lineup"][0]:
        assert [r["flag"] or "" for r in page["lineup"]] == [x["flag"] for x in api["lineup"]]
    if page["lineup_full"] and "flag" in page["lineup_full"][0]:
        assert [r["flag"] or "" for r in page["lineup_full"]] == [x["flag"] for x in api["lineup_full"]]
    if page["lineup_full"] and "lineup_margin" in page["lineup_full"][0]:
        assert [r["lineup_margin"] for r in page["lineup_full"]] == pytest.approx(
            [x["margin"] if x["margin"] is not None else float("nan") for x in api["lineup_full"]], nan_ok=True)
    assert page["howto"] == api["howto"]
    status = client.get("/api/status").json()
    assert page["freshness"] == status["freshness"] and page["warning"] == status["warning"]


@pytest.mark.parametrize("league,team,gsis", CASES)
def test_player_card_is_the_player_page(client, league, team, gsis):
    page = twin("player", league, str(team), gsis)
    api = client.get(f"/api/player/{gsis}?league={league}&team={team}").json()
    assert page["name"] == api["player_name"]
    assert strip_links(page["header"]) == strip_links(api["header"])
    # the page draws Usage, Projection, Availability, Value, Signals in that order; the app reorders them
    order = ["usage", "projection", "availability", "value", "signals"]
    assert [s["title"] for s in page["sections"]] == [api["sections"][k]["title"] for k in order]
    for drawn, key in zip(page["sections"], order, strict=True):
        assert norm_blocks(drawn["blocks"]) == norm_blocks(api["sections"][key]["blocks"]), key
    assert page["howto"] == api["howto"]
