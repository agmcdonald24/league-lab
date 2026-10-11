"""IX-5 (Wave I-X): what we claim, said once and truly.

1. The trust line names each position's verdict correctly in every combination of positions and spans (a table-driven
   test over all 63 position sets: the sentence is read back and compared with ``provenance.CHECKS``).
2. The window's caption says what the next four weeks are checked to be (no "near enough to trust").
3. A kicker or a defense is never the strongest move on a four-week gain (``decisions.ix5_kd_last``).
4. "Fit" is said as what it is: net lineup points over the window's weeks.
"""

from __future__ import annotations

import itertools
import re

import pytest

from league_lab_api import provenance as P

from .conftest import needs_db

BOARD = {"model_version": "v3.6", "kd_model_version": "kd1.0", "published_at": None, "versions": [], "source": "code"}
WORD_POS = {w: p for p, w in P.POS_WORDS.items()}
NAMES = "|".join(sorted(WORD_POS, key=len, reverse=True))
GROUP = re.compile(rf"((?:{NAMES})(?:(?:, | and )(?:{NAMES}))*) (weak|no better than chance|graded)")
TAIL_STATUS = {"weak": "graded_weak", "no better than chance": "chance", "graded": "graded"}
ALL_STATUS = {"graded": "graded", "graded, weak": "graded_weak", "no better than chance": "chance"}


@pytest.fixture(autouse=True)
def board(monkeypatch):
    monkeypatch.setattr(P, "board", lambda: dict(BOARD))


def read_back(words: str) -> dict[tuple[str, str], str]:
    """The sentence after "checked on 2021–2025: " -> {(span, position): status} for every position it covers.
    Raises if a span's words name no default and leave a position out (filled in by the caller's check)."""
    checked = words.split(f"checked on {P.GRADED_ON}: ", 1)[1].rstrip(".")
    out: dict[tuple[str, str], str] = {}
    for part in checked.split("; "):
        for sp, lead in (("next", P.SPAN_WORDS["next"]), ("later", P.SPAN_WORDS["later"])):
            if not part.startswith(lead):
                continue
            rest = part[len(lead):]
            if rest.startswith(" ") and rest[1:] in ALL_STATUS:
                out[(sp, "*")] = ALL_STATUS[rest[1:]]
                break
            if rest.startswith(" graded, "):
                out[(sp, "*")] = "graded"
                rest = rest[len(" graded, "):]
            else:
                assert rest.startswith(": "), part
                rest = rest[2:]
            named = GROUP.findall(rest)
            assert named, part
            for names, status in named:
                for w in re.split(r", | and ", names):
                    key = (sp, WORD_POS[w])
                    assert key not in out, f"{w} named twice in {part!r}"
                    out[key] = TAIL_STATUS[status]
            break
    return out


SETS = [list(c) for n in range(1, 7) for c in itertools.combinations(P.POSITIONS, n)]
HORIZONS = {"next only": (5, 5, 5), "later only": (6, 9, 5), "both": (5, 8, 5)}


@pytest.mark.parametrize("hz", list(HORIZONS))
@pytest.mark.parametrize("positions", SETS, ids=["+".join(s) for s in SETS])
def test_trust_line_says_each_positions_verdict(positions, hz):
    p = P.block(positions, *HORIZONS[hz], trade_gap=True)
    said = read_back(p["words"])
    for sp in P.spans(p["horizon"]):
        for pos in positions:
            want = P.CHECKS[(sp, pos)]["status"]
            got = said.get((sp, pos), said.get((sp, "*")))
            assert got == want, (positions, sp, pos, p["words"])
        for (s, pos), _ in said.items():                     # nothing named that is not in play
            assert pos == "*" or (s == sp and pos in positions) or s != sp
    assert p["words"].endswith("the trade's range not graded.")


def test_the_reviews_case_a_quarterback_and_a_kicker():
    """Stafford for Folk + Reichard (QB, K, weeks 5–8): the kicker's verdict no longer covers the quarterback."""
    w = P.block(["QB", "K"], 5, 8, 5, trade_gap=True, beta=True)["words"]
    assert "next week graded, kickers weak; two to eight weeks ahead: quarterbacks weak, kickers no better than chance" in w
    assert "two to eight weeks ahead no better than chance, quarterbacks weak" not in w


def test_statuses_match_the_metrics_table():
    """docs/METRICS.md § "What each number has been checked against (IR-4)": next week QB 0.587 … DEF 0.257; two to
    eight weeks ahead QB 0.495 weak, K 0.028 and DEF 0.040 no better than chance."""
    table = {("next", "QB"): (0.587, "graded"), ("next", "RB"): (0.686, "graded"), ("next", "WR"): (0.618, "graded"),
             ("next", "TE"): (0.599, "graded"), ("next", "K"): (0.095, "graded_weak"), ("next", "DEF"): (0.257, "graded_weak"),
             ("later", "QB"): (0.495, "graded_weak"), ("later", "K"): (0.028, "chance"), ("later", "DEF"): (0.040, "chance")}
    for key, (order, status) in table.items():
        assert P.CHECKS[key]["order"] == pytest.approx(order, abs=0.001) and P.CHECKS[key]["status"] == status, key
    for pos in ("RB", "WR", "TE"):
        assert P.CHECKS[("later", pos)]["status"] == "graded"


# ------------------------------------------------------------------------------------------------ 2. the window's caption
def test_window_caption_says_what_the_next_four_weeks_are_checked_to_be():
    """METRICS § "The trade calculator's windows": next four weeks RB 0.660, WR 0.594, TE 0.564 (graded); QB 0.538
    against his own record's 0.537 (level: a lean); K / DEF not pooled by window, 0.095 / 0.257 next week and no better
    than chance after."""
    from pathlib import Path

    from league_lab_api import decisions as D
    w = D.WINDOW_WHY["next4"]
    assert "trust" not in w and "enough" not in w
    assert w == ("the next four weeks: running backs, receivers and tight ends graded; quarterbacks a lean, level with "
                 "their own record; kickers and defenses a rough guide, no better than chance after next week")
    ts = (Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "decisions.ts").read_text()
    assert f'next4: "{w}"' in ts                               # the page's copy is the API's
    assert all(not c["status"] == "graded" for c in [P.CHECKS[("later", "K")], P.CHECKS[("later", "DEF")]])


# ------------------------------------------------------------------------------------------------ 3. kickers and defenses
def _row(pos, horizon, weekly, rank, name):
    return {"add_position": pos, "horizon_gain": horizon, "weekly_gain": weekly, "add_rank": rank, "add_name": name}


def test_a_defense_is_never_the_strongest_on_the_window_gain():
    """The review's case: a defense +4.7 over four weeks. It is chosen only on this week's gain, after the graded
    positions, and its card's number is this week's."""
    import pandas as pd

    from league_lab_api import decisions as D
    best = pd.DataFrame([_row("DEF", 4.7, 0.8, 1, "Buccaneers"), _row("RB", 2.0, 1.0, 2, "Back"),
                         _row("K", 3.0, 0.0, 3, "Kicker"), _row("WR", 1.0, 0.0, 4, "Receiver")])
    seen = {"RB", "WR"}
    picked = D.ix5_kd_last(best, seen, 1, lambda r: {"add": {"position": r["add_position"], "player_name": r["add_name"]},
                                                     "weekly_gain": r["weekly_gain"], "horizon_gain": r["horizon_gain"]})
    assert [m["add"]["position"] for m in picked] == ["DEF"]          # the kicker gains nothing this week: not listed
    assert D.ix5_kd_last(best, {"RB", "WR"}, 0, lambda r: r) == []    # no room after the graded positions: none
    c = D.ix5_guide_card({"move": picked[0], "gain": 4.7, "gain_label": "weeks 5–8", "this_week": 0.8}, 5)
    assert c["gain"] == 0.8 and c["gain_label"] == "week 5" and c["guide"] == D.KD_GUIDE_WORDS
    rb = {"move": {"add": {"position": "RB"}}, "gain": 2.0, "gain_label": "weeks 5–8", "this_week": 1.0}
    assert D.ix5_guide_card(rb, 5) is rb
    assert "rough guide" in D.KD_GUIDE_WORDS and "no better than chance" in D.KD_GUIDE_WORDS


def test_the_intro_says_the_guide():
    from league_lab_api import decisions as D
    rb = {"move": {"weekly_gain": 1.0}, "this_week": 1.0}
    df = {"move": {"weekly_gain": 0.8}, "this_week": 0.8, "guide": D.KD_GUIDE_WORDS}
    assert D.top_intro([rb, df], 5, 8) == ("The strongest claim below: it helps this week. Each card's total is its gain "
                                           "over weeks 5–8. After them, a kicker or defense for this week only: a rough guide.")
    assert D.top_intro([df], 5, 8) == "This week's kicker or defense claim below: it counts this week only, a rough guide."
    assert D.top_intro([rb], 5, 8).endswith("weeks 5–8.")


@needs_db
@pytest.mark.parametrize("league,team", [("1389709692405551104", "2"), ("1321941740235550720", "12")])
def test_waivers_three_put_kickers_and_defenses_last_on_this_week(client, league, team):
    from league_lab_api import decisions as D
    r = client.get("/api/waivers", params={"league": league, "team": team})
    assert r.status_code == 200, r.text[:300]
    top = r.json().get("top3") or []
    kd = [((c.get("move") or {}).get("add") or {}).get("position") in D.KD_GUIDE_POSITIONS for c in top]
    assert kd == sorted(kd), "a kicker or defense listed before a graded position"
    for c, is_kd in zip(top, kd, strict=True):
        if is_kd:
            assert c.get("guide") and c["gain"] == c["this_week"] and not c.get("total_words")
            assert (c["this_week"] or 0) >= D.GAIN_EPS
        else:
            assert not c.get("guide")
    src = (r.json().get("recent_adds") or {}).get("source")              # 5. no internal names on Waivers
    assert src is None or ("mart_" not in src and "analytics." not in src and src.endswith(" transactions")), src


# ------------------------------------------------------------------------------------------------ 4. "Fit", said as what it is
def test_fit_is_net_lineup_points_with_its_weeks():
    from league_lab_api import decisions as DC
    t = {"player": {"player_name": "Kenneth Walker III", "position": "RB"}, "team_name": "Run Bijan Run",
         "diff_per_game": -1.5, "gain_week": 8.0, "loss_week": 7.9, "fit_horizon": 9.9}
    b = DC.below_line(t, "weeks 5–8", 5)
    assert "(net **+9.9** lineup points over weeks 5–8: your gain minus their loss)" in b
    a = DC.above_line({**t, "diff_per_game": 5.0}, "weeks 5–8", 5)
    assert "(net **+9.9** lineup points over weeks 5–8: their gain minus your loss)" in a
    for line in (a, b, *DC.TRADE_HOWTO, DC.GAP_LINE_NO_RECORD):
        assert not re.search(r"\bfit\b", line, re.I), line


def test_no_screen_says_fit():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "web" / "src" / "routes"
    trades = (root / "Trades.svelte").read_text()
    assert 'valueLabel="Fit"' not in trades and "**Fit**" not in trades and "best fit" not in trades


# ------------------------------------------------------------------------------------------------ 8. the known trade stays fixed
SCRUBS = "1389709692405551104"
FOLK, STAFFORD, REICHARD = "650", "421", "11792"


@needs_db
def test_the_known_trade_stays_fixed(monkeypatch):
    """The review's case (League of Scrubs, team 2 gives Folk to team 3 for Stafford + Reichard, the next four weeks):
    the headline, the summary and the weekly table agree; no explanation crosses positions; the package stays rejected
    as implausible; its trust line names the quarterback's and the kicker's verdicts separately."""
    from league_lab_api import decisions as D

    from .test_ir2 import assert_reconciles, assert_slot_pairs
    monkeypatch.setenv("LEAGUE_LAB_AVAILABILITY", "off")
    D.clear_memo()
    ctx = D.trade_context(SCRUBS)
    if ctx.board.owner(FOLK) != 2 or ctx.board.owner(STAFFORD) != 3 or ctx.board.owner(REICHARD) != 3:
        pytest.skip("the database's rosters do not hold the Folk package")
    out = D.evaluate(SCRUBS, 2, 3, [FOLK], [STAFFORD, REICHARD], window="next4")
    d = out["decision"]
    assert_reconciles(d, out["card"])                                    # the weekly table, the strip, the totals
    span = d["span"]
    for k in ("mine", "theirs"):
        g = d[k]["gain_window"]
        assert sum(d["strip"][k]) == pytest.approx(g, abs=0.03)
        assert out["fit"]["window"][k] == g                              # the summary tiles read the decision
    gm, gt = d["mine"]["gain_window"], d["theirs"]["gain_window"]
    v = d["verdict"]                                                     # the headline says the same numbers
    assert f"{gm:+.1f} over {span}".replace("-", "−") in v or f"{gm:+.1f} over {span}" in v, v
    assert f"{abs(gt):.1f} over {span}" in v, v
    assert out["verdict"] == v
    assert_slot_pairs(d, ctx.slots)                                      # no explanation crosses positions
    for k in ("mine", "theirs"):
        for ch in d["changes"][k]:
            pin, pout = ch.get("in_player") or {}, ch.get("out_player") or {}
            if pin.get("position") and pout.get("position") and ch["slot_word"] in ("QB", "K"):
                assert pin["position"] == pout["position"] == ch["slot_word"], ch["words"]
    assert out["card"]["plausibility"]["key"] == "implausible"           # rejected as implausible
    assert out["card"]["credible"] is False and d["recommendation"]["credible"] is False
    assert d["recommendation"]["plausibility"] == "Implausible"
    from league_lab_api import provenance as PV
    w = PV.with_trade(out)["provenance"]["words"]
    assert "two to eight weeks ahead: quarterbacks weak, kickers no better than chance" in w, w
    assert "two to eight weeks ahead no better than chance, quarterbacks weak" not in w
