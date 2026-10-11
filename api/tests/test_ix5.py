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
