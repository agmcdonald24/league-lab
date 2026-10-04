"""B4: decision cards (app/lib/cards.py) and the player links every table gets (app/lib/table.py show()).

No database: the cards' logic is checked against the real solver (league_lab.lineup.solve) on synthetic
and random rosters, and show() is called with st.dataframe captured.
"""

import random
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from lib import cards, table  # noqa: E402
from lib import ui as app_ui  # noqa: E402

from league_lab import lineup as lu  # noqa: E402

DYNASTY = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", "BN", "BN", "BN", "BN", "BN", "BN", "TAXI", "IR"]
SCRUBS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN", "BN", "BN", "BN", "BN", "IR"]
MIXED = ["QB", "RB", "WR", "TE", "WRRB_FLEX", "REC_FLEX", "FLEX", "BN", "BN", "BN", "BN"]


def r2(x):
    return None if x is None else round(float(x) + 0.0, 2) + 0.0


def rows_from(lineup: lu.Lineup) -> pd.DataFrame:
    """The frame lib.cards.lineup_rows() returns, built from a solved lineup (values stored to the cent)."""
    out, weakest = [], lineup.weakest
    for s in lineup.starts:
        p = s.player
        out.append({"role": "starter", "slot": s.slot.label, "slot_type": s.slot.type, "slot_order": s.slot.order,
                    "bench_rank": None, "gsis_id": p.id if p else None, "player_name": f"P{p.id}" if p else None,
                    "position": p.position if p else None, "value": r2(p.value) if p else None,
                    "value_source": p.value_source if p else None, "margin": r2(s.margin), "is_locked": s.locked,
                    "is_empty_slot": p is None, "report_status": p.status if p else None, "reason": None,
                    "kicked_off": False, "opponent": None, "opp_rank": None,
                    "is_weakest_slot": weakest is not None and s.slot.label == weakest.slot.label})
    for i, p in enumerate(lineup.bench, 1):
        out.append({"role": "bench", "slot": None, "slot_type": None, "slot_order": None, "bench_rank": i,
                    "gsis_id": p.id, "player_name": f"P{p.id}", "position": p.position, "value": r2(p.value),
                    "value_source": p.value_source, "margin": None, "is_locked": False, "is_empty_slot": False,
                    "report_status": p.status, "reason": None, "kicked_off": False, "opponent": None, "opp_rank": None,
                    "is_weakest_slot": False})
    df = pd.DataFrame(out)
    df["locked_now"] = df["is_locked"] | df["kicked_off"]
    return df


def P(pid, pos, value, **kw):
    return lu.Player(id=str(pid), position=pos, value=value, value_source=kw.pop("value_source", "proj_points"), **kw)


def test_slot_eligibility_is_the_solvers():
    assert cards.SLOT_ELIGIBILITY == lu.SLOT_ELIGIBILITY


def test_direct_swap_named_and_ordered_like_the_weakest_slot():
    players = [P(1, "QB", 20.6), P(2, "QB", 17.86), P(3, "RB", 9.57), P(4, "RB", 7.54), P(5, "RB", 7.09),
               P(6, "WR", 16.97), P(7, "WR", 14.65), P(8, "WR", 11.08), P(9, "WR", 9.21), P(10, "TE", 9.47),
               P(11, "TE", 8.84), P(12, "QB", 19.81)]
    solved = lu.solve(players, DYNASTY)
    dec = cards.decisions(rows_from(solved))
    assert list(dec["slot"]) == ["RB2", "TE", "FLEX"]                      # Andrew's dynasty week 4, by hand
    assert list(dec["alt_name"]) == ["P5", "P11", "P9"]
    assert [round(m, 2) for m in dec["margin"]] == [0.45, 0.63, 1.87]
    assert list(dec["verdict"]) == ["a coin flip", "a coin flip", "a lean"]
    assert dec.iloc[0]["slot"] == solved.weakest.slot.label
    assert all(dec["how"].str.startswith("best bench player"))


def test_reshuffle_names_who_comes_in_and_who_slides():
    # WR2 starter W2 (10.0); bench has only an RB (8.0) and a WR at 7.0. Benching W2: the FLEX WR (9.5)
    # slides to WR2 and the RB comes in at FLEX -> loses 2.0, not 3.0 (the best bench WR).
    slots = ["WR", "WR", "FLEX", "BN", "BN"]
    players = [P("W1", "WR", 12.0), P("W2", "WR", 10.0), P("W3", "WR", 9.5), P("R1", "RB", 8.0), P("W4", "WR", 7.0)]
    solved = lu.solve(players, slots)
    rows = rows_from(solved)
    w2 = rows[rows["gsis_id"] == "W2"].iloc[0]
    assert w2["margin"] == pytest.approx(2.0)
    a = cards.alternative(w2, rows)
    assert a["alt"]["gsis_id"] == "R1" and a["mover"]["gsis_id"] == "W3"
    assert "PW3 (WR) moves from FLEX to WR; PR1 (RB) fills the open FLEX" in a["how"]   # ---- II-0: the legal chain


def test_forced_locked_and_unvalued_starters_are_not_decisions():
    slots = ["QB", "RB", "K", "DEF", "BN", "BN"]
    players = [P("Q", "QB", 20.0), P("Q2", "QB", 19.0), P("R", "RB", 10.0), P("R2", "RB", 3.0),
               P("K1", "K", 1.0, value_source="season_ppg"),                     # only K: margin = value, forced
               P("D1", "DEF", None, value_source="unvalued")]                     # unvalued DEF: margin 0
    rows = rows_from(lu.solve(players, slots))
    dec = cards.decisions(rows)
    assert list(dec["slot"]) == ["QB", "RB"]                                    # K (1.0, nobody else) skipped
    rows.loc[rows["gsis_id"] == "Q", "kicked_off"] = True                       # his game started since the solve
    rows["locked_now"] = rows["is_locked"] | rows["kicked_off"]
    assert list(cards.decisions(rows)["slot"]) == ["RB"]


@pytest.mark.parametrize("slots", [DYNASTY, SCRUBS, MIXED])
def test_named_alternative_is_who_the_re_solve_brings_in(slots):
    """For random rosters: the card's alternative is exactly the player who enters the best lineup when the
    starter is removed and the lineup re-solved, and starter value - alternative value = the margin."""
    rng = random.Random(7)
    positions = ["QB", "RB", "WR", "TE"] + (["K", "DEF"] if "K" in slots else [])
    checked = shuffles = 0
    for trial in range(120):
        players = [P(f"{trial}-{i}", rng.choice(positions), round(rng.uniform(0, 25), 2)) for i in range(rng.randint(9, 16))]
        solved = lu.solve(players, slots)
        rows = rows_from(solved)
        for _, d in cards.decisions(rows).iterrows():
            rest = lu.solve([p for p in players if p.id != d["gsis_id"]], slots, margins=False)
            entering = set(rest.starter_ids) - set(solved.starter_ids)
            by_id = {p.id: p for p in players}
            assert len(entering) == 1                                   # one alternating path: one player comes in
            (e,) = entering
            assert e == d["alt_gsis_id"] or by_id[e].value == d["alt_value"]   # (or an exact tie in value)
            assert d["value"] - d["alt_value"] == pytest.approx(d["margin"], abs=0.011)
            assert solved.total - rest.total == pytest.approx(d["margin"], abs=0.011)
            if isinstance(d["mover_name"], str):                        # a teammate slid into the starter's slot
                assert by_id[d["alt_gsis_id"]].position not in lu.SLOT_ELIGIBILITY[d["slot_type"]]
            checked += 1
            shuffles += isinstance(d["mover_name"], str)
    assert checked > 150 and (shuffles > 0 or slots is not DYNASTY)


def test_lineup_frame_flags():
    solved = lu.solve([P("Q", "QB", 20.0, status="Questionable"), P("R", "RB", 10.0)], ["QB", "RB", "WR"])
    rows = rows_from(solved)
    f = cards.lineup_frame(rows).set_index("slot")["flag"]
    assert f["QB"] == "Questionable" and f["RB"] == "" and f["WR"].startswith("EMPTY")


def test_rank_phrase_reads_b2s_rankings_when_present():
    rk = pd.DataFrame({"measure": ["lineup_value", "horizon_value"], "league_rank": [3, 5], "n_rosters": [12, 12],
                       "horizon": ["week 4", "weeks 4–7"], "week": [4, 4]})
    assert cards.rank_phrase(rk, 4) == ", 3rd of 12 in the league"               # "in week 4" is already said
    assert cards.rank_phrase(rk.assign(week=None), None) == ", 3rd of 12 in the league (week 4)"
    assert cards.rank_phrase(rk, 5) == ""                                  # another week's rank is not shown
    assert cards.rank_phrase(pd.DataFrame({"x": [1]}), 4) == ""            # columns not as expected -> no rank
    assert cards.slot_label("SUPER_FLEX") == "Superflex" and cards.slot_label("FLEX2") == "FLEX2"


# ------------------------------------------------------------------------------ links in every table
def _capture(monkeypatch):
    seen = {}
    monkeypatch.setattr(table.st, "dataframe", lambda data, **kw: seen.update(data=data, **kw))
    monkeypatch.setattr(app_ui, "_link_context", lambda: {"league": "L1", "team": "12"})
    return seen


def test_show_links_player_names_when_the_frame_has_gsis_id(monkeypatch):
    seen = _capture(monkeypatch)
    df = pd.DataFrame({"gsis_id": ["00-0036963", None], "player_name": ["Amon-Ra St. Brown", "Kansas City Chiefs"],
                       "position": ["WR", "DEF"], "ppg_std": [33.5, 1.0]})
    table.show(df, ["player_name", "position", "ppg_std"])       # gsis_id not displayed, still used
    urls = list(seen["data"]["player_name"])
    q = parse_qs(urlsplit(urls[0]).query)
    assert urls[0].startswith("Player?name=") and q == {"name": ["Amon-Ra St. Brown"], "id": ["00-0036963"], "league": ["L1"], "team": ["12"]}
    assert parse_qs(urlsplit(urls[1]).query) == {"name": ["Kansas City Chiefs"], "league": ["L1"], "team": ["12"]}   # search
    cfg = seen["column_config"]["player_name"]
    assert cfg["type_config"]["type"] == "link" and cfg["label"] == "Player"
    assert cfg["type_config"]["display_text"] == r"^Player\?name=([^&]*)"
    assert list(seen["data"].columns) == ["player_name", "position", "ppg_std"]


def test_show_leaves_frames_without_gsis_id_alone(monkeypatch):
    seen = _capture(monkeypatch)
    table.show(pd.DataFrame({"player_name": ["Amon-Ra St. Brown"], "ppg_std": [33.5]}))
    assert list(seen["data"]["player_name"]) == ["Amon-Ra St. Brown"]
    assert seen["column_config"]["player_name"].get("type_config", {}).get("type") != "link"


def test_player_link_markdown(monkeypatch):
    monkeypatch.setattr(app_ui, "_link_context", lambda: {"league": "L1"})
    assert app_ui.player_link("00-1", "Ja'Marr Chase") == "[Ja'Marr Chase](Player?name=Ja%27Marr+Chase&id=00-1&league=L1)"
    assert app_ui.player_link(None, "Kansas City Chiefs") == "Kansas City Chiefs"
