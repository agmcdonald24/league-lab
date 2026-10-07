"""IN-3 (Wave I-N): matchups for everyone — `matchup_board.matchup_context` (the interface DFS and the home read) and
`GET /api/matchups/board` (the board: every player at a position this week, search, filters, paging)."""

from __future__ import annotations

import ast
import itertools

import pytest

from league_lab_api import matchup_board as MB
from league_lab_api import ratelimit, refleague
from league_lab_api.settings import ROOT

from .conftest import SCRUBS, needs_db

BOARD = "/api/matchups/board"
CTX_KEYS = {"opponent", "home", "defense", "cb", "tone", "words"}
DEF_KEYS = {"tone", "tough_rank", "n_ranked", "words"}
CB_KEYS = {"tone", "certainty", "corner", "corner_rank", "shutdown", "tier", "words"}   # IO-4 fix round: + tier


# ------------------------------------------------------------------------------------------- pure: the one tone
# IO-4 fix round (Wave I-O, the PO's decision on IO-1's grade: no measurable effect): the tone is the defense's alone —
# the same 42 cases, the four a likely corner used to move now the defense's (changed on purpose)
@pytest.mark.parametrize(("defense", "corner", "certainty", "want"), [
    # a likely call: never moves it (was: confirms, moves a neutral defense, cancels the opposite read)
    ("favorable", "favorable", "likely", "favorable"), ("favorable", "neutral", "likely", "favorable"),
    ("favorable", "difficult", "likely", "favorable"), ("neutral", "favorable", "likely", "neutral"),
    ("neutral", "neutral", "likely", "neutral"), ("neutral", "difficult", "likely", "neutral"),
    ("difficult", "favorable", "likely", "difficult"), ("difficult", "neutral", "likely", "difficult"),
    ("difficult", "difficult", "likely", "difficult"),
    # an unclear call (either outside corner), no call, an unranked corner: never moves it
    *[(d, c, "unclear", d) for d in MB.TONES for c in (*MB.TONES, None)],
    *[(d, None, cert, d) for d in MB.TONES for cert in ("no call", "likely", None)],
    # no defense read: no tone (unknown is not neutral), whatever the corner says
    *[(None, c, cert, None) for c in (*MB.TONES, None) for cert in ("likely", "unclear", "no call")],
])
def test_the_tone_table(defense, corner, certainty, want):
    assert MB.combine_tone(defense, corner, certainty) == want


def test_an_unclear_call_never_moves_the_tone():
    for d, c in itertools.product(MB.TONES, (*MB.TONES, None)):
        assert MB.combine_tone(d, c, "unclear") == d
        assert MB.combine_tone(d, c, "no call") == d


def _list_literal(name: str) -> list[str]:
    tree = ast.parse((ROOT / "src" / "league_lab" / "projections.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise AssertionError(name)


def test_what_the_screen_says_is_in_the_projection_is_true():
    """The defense against his position is an input (the five opponent features); nothing about who plays corner is.
    Adding a corner or opponent-personnel input to the projection fails this test (and the board's words must change)."""
    base = _list_literal("BASE_FEATURES")
    assert set(MB.IN_PROJECTION) <= set(base)
    assert {f for f in base if "opp" in f or "allowed" in f} == set(MB.IN_PROJECTION)
    assert not [f for f in base if any(w in f for w in ("cb", "corner", "cover", "defender"))]
    assert "Who plays cornerback is not in it" in MB.PROJECTION_WORDS
    assert "points each defense has allowed to the position" in MB.PROJECTION_WORDS


def test_the_route_is_in_the_research_bucket():
    assert ratelimit.bucket_for("GET", BOARD, "league=ref:half&q=chase") == "research"


# ------------------------------------------------------------------------------------------- matchup_context
def test_matchup_context_with_a_missing_mart_is_empty(monkeypatch):
    MB.clear()
    monkeypatch.setattr(MB, "missing_relations", lambda names: list(names))
    assert MB.matchup_context(2026, 4) == {}
    assert MB.matchup_context(2026, 4, ["00-0036963"]) == {}


def test_matchup_context_never_raises(monkeypatch):
    MB.clear()

    def boom(*_a, **_k):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(MB, "query", boom)
    monkeypatch.setattr(MB, "missing_relations", lambda names: [])
    assert MB.matchup_context(2026, 4) == {}
    assert MB.matchup_context("not a season", None) == {}          # type: ignore[arg-type]


@needs_db
def test_matchup_context_shape_and_tone_rule():
    MB.clear()
    assert MB.matchup_context(2026, 40) == {}                         # a week with no games
    ctx = MB.matchup_context(2026, 4)
    assert len(ctx) > 300
    n_wr = 0
    for g, c in ctx.items():
        assert set(c) == CTX_KEYS, g
        assert set(c["defense"]) == DEF_KEYS
        assert c["tone"] in (*MB.TONES, None)
        if c["cb"] is not None:
            n_wr += 1
            assert set(c["cb"]) == CB_KEYS
            assert c["cb"]["certainty"] in ("likely", "unclear", "no call")
            assert isinstance(c["cb"]["shutdown"], bool)
            assert c["cb"]["tone"] is None and c["cb"]["tier"] in ("shutdown", "solid", "target", None)   # IO-4 fix
            assert c["words"] is None or c["cb"]["words"] is None or c["cb"]["words"] not in c["words"]
        assert c["tone"] == c["defense"]["tone"]                                                       # IO-4 fix
        assert c["tone"] == MB.combine_tone(c["defense"]["tone"], (c["cb"] or {}).get("tone"), (c["cb"] or {}).get("certainty"))
        if c["defense"]["tough_rank"] is not None:
            assert 1 <= c["defense"]["tough_rank"] <= c["defense"]["n_ranked"]
    assert n_wr > 100
    some = list(ctx)[:3]
    assert set(MB.matchup_context(2026, 4, [*some, "00-nobody"])) == set(some)
    # the reader's copy is its own: changing it never changes the next answer
    ctx[some[0]]["tone"] = "changed"
    assert MB.matchup_context(2026, 4, [some[0]])[some[0]]["tone"] != "changed"


# ------------------------------------------------------------------------------------------- the board
def _owner_keys(v, found: set[str]) -> set[str]:
    if isinstance(v, dict):
        for k, x in v.items():
            if k in refleague.OWNERSHIP:
                found.add(k)
            _owner_keys(x, found)
    elif isinstance(v, list):
        for x in v:
            _owner_keys(x, found)
    return found


@needs_db
def test_board_without_a_league(client):
    r = client.get(BOARD, params={"league": "ref:half"})
    assert r.status_code == 200
    j = r.json()
    assert j["position"] == "WR" and j["scoring"] == "Half PPR" and j["total"] > 50 and len(j["rows"]) == MB.DEFAULT_LIMIT
    assert "No league" not in j["scoring"] and j["projection_words"] == MB.PROJECTION_WORDS
    assert _owner_keys(j, set()) == set()                              # no "rostered by" at any depth
    proj = [x["proj_points"] for x in j["rows"]]
    assert proj == sorted(proj, reverse=True)                          # the default sort
    for x in j["rows"]:
        assert x["position"] == "WR" and x["opponent"] and x["game_id"]
        assert set(x["context"]) == CTX_KEYS and x["context"]["cb"] is not None
        assert x["p10"] is None or x["p10"] <= x["p90"]
    assert any(x["matchup_evidence"] and x["matchup_evidence"]["sentences"] for x in j["rows"])
    assert {g["game_id"] for g in j["games"]} >= {x["game_id"] for x in j["rows"]}
    te = client.get(BOARD, params={"league": "ref:half", "position": "te"}).json()
    assert te["position"] == "TE" and all(x["context"]["cb"] is None for x in te["rows"])
    assert "linebackers and safeties" in te["position_note"]


@needs_db
def test_board_in_a_house_league_says_who_has_him(client):
    j = client.get(BOARD, params={"league": SCRUBS, "limit": 50}).json()
    assert j["rows"] and all("rostered_by_roster_id" in x and "rostered_by_team" in x for x in j["rows"])
    assert any(x["rostered_by_roster_id"] is not None for x in j["rows"])
    assert j["scoring"] == j["league_name"]


@needs_db
def test_board_search_is_text(client):
    first = client.get(BOARD, params={"league": "ref:half"}).json()["rows"][0]
    last = first["player_name"].split()[-1]
    hit = client.get(BOARD, params={"league": "ref:half", "q": last.upper()}).json()
    assert hit["total"] >= 1 and first["gsis_id"] in {x["gsis_id"] for x in hit["rows"]}
    assert all(last.lower().replace("'", "") in x["player_name"].lower().replace("'", "") for x in hit["rows"])
    for hostile in ("%%", "%a%", "a_", "__", "'; drop table x; --", "\\\\", "a%", "*?", "12", "<script>"):
        r = client.get(BOARD, params={"league": "ref:half", "q": hostile})
        assert r.status_code == 200, hostile
        assert r.json()["total"] == 0, hostile                         # a wildcard is a character no name has
    assert client.get(BOARD, params={"league": "ref:half", "q": "a"}).status_code == 400
    assert client.get(BOARD, params={"league": "ref:half", "q": "x" * 41}).status_code == 400
    assert client.get(BOARD, params={"league": "ref:half", "q": "   "}).json()["q"] is None   # blank = no search


@needs_db
def test_board_paging_and_bounds(client):
    a = client.get(BOARD, params={"league": "ref:half", "limit": 5}).json()
    b = client.get(BOARD, params={"league": "ref:half", "limit": 5, "offset": 5}).json()
    ab = client.get(BOARD, params={"league": "ref:half", "limit": 10}).json()
    assert a["total"] == b["total"] == ab["total"]
    assert [x["gsis_id"] for x in a["rows"] + b["rows"]] == [x["gsis_id"] for x in ab["rows"]]
    far = client.get(BOARD, params={"league": "ref:half", "offset": 4000}).json()
    assert far["rows"] == [] and far["total"] == a["total"]
    for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 5001}, {"limit": "x"}, {"position": "K"},
                {"tone": "great"}, {"sort": "name"}, {"game": "KC"}, {"game": "2026_04_ZZZ_YYY"}):
        r = client.get(BOARD, params={"league": "ref:half", **bad})
        assert r.status_code in (400, 422), bad
    assert client.get(BOARD, params={"league": "ref:nope"}).status_code == 404


@needs_db
def test_board_filters_and_sorts(client):
    base = client.get(BOARD, params={"league": "ref:half", "limit": 100}).json()
    g = base["games"][0]["game_id"]
    j = client.get(BOARD, params={"league": "ref:half", "game": g.lower()}).json()
    assert j["rows"] and all(x["game_id"] == g for x in j["rows"])
    for t in MB.TONES:
        j = client.get(BOARD, params={"league": "ref:half", "tone": t, "limit": 100}).json()
        assert j["total"] == base["counts"][t]
        assert all(x["context"]["tone"] == t for x in j["rows"])
    j = client.get(BOARD, params={"league": "ref:half", "sort": "tone", "limit": 100}).json()
    order = [MB.TONE_ORDER.get(x["context"]["tone"], 3) for x in j["rows"]]
    assert order == sorted(order)
    j = client.get(BOARD, params={"league": "ref:half", "sort": "corner", "limit": 100}).json()
    ranks = [x["context"]["cb"]["corner_rank"] for x in j["rows"]]
    known = [k for k in ranks if k is not None]
    assert known == sorted(known, reverse=True)                        # the easiest corner first
    assert ranks[: len(known)] == known                                 # no ranked corner: last


@needs_db
def test_a_corner_who_is_not_expected_to_play_is_no_call(monkeypatch):
    """The call names a corner the overlay says cannot play (cards.corner_personnel: listed, not expected): the read is
    "no call" — never "faces a shutdown corner" who is out — and the tone is the defense's alone."""
    MB.clear()
    row = MB.query("""select gsis_id, opponent, likely_cover_gsis_id, likely_cover_name, likely_cover_slot
                      from analytics.mart_cb_matchups where season = 2026 and week = 4 and position = 'WR'
                        and call_status = 'called' and call_strength = 'clear' order by gsis_id limit 1""").iloc[0]
    before = MB.matchup_context(2026, 4, [row.gsis_id])[row.gsis_id]
    assert before["cb"]["certainty"] == "likely" and before["cb"]["corner"] == row.likely_cover_name

    def personnel(defenses, season, week, statuses=None):
        return {d: {"kind": "changed" if d == row.opponent else "same", "regulars": [], "missing": [],
                    "listed": [{"gsis_id": row.likely_cover_gsis_id, "name": row.likely_cover_name,
                                "slot": row.likely_cover_slot}] if d == row.opponent else [],
                    "expected": [], "depth_chart_at": "2026-10-01T00:00:00Z"} for d in defenses}

    monkeypatch.setattr(MB.cards, "corner_personnel", personnel)
    MB.clear()
    after = MB.matchup_context(2026, 4, [row.gsis_id])[row.gsis_id]
    assert after["cb"] == {"tone": None, "certainty": "no call", "corner": None, "corner_rank": None, "shutdown": False,
                           "tier": None,
                           "words": f"no corner call: {row.likely_cover_name}, named on his side, is not expected to play"}
    assert after["tone"] == after["defense"]["tone"]
    assert "not expected to play" in after["cb"]["words"] and "not expected" not in (after["words"] or "")   # IO-4 fix
    MB.clear()


@needs_db
def test_cycling_league_scorings_keeps_the_week_cached(client, monkeypatch):
    """Review L2 (the merge): the per-scoring boards have their own bounded region, so paging every reference scoring
    and both house leagues (22 boards) never evicts the week-wide entries — the context, the corners, the evidence.
    The boards' region is cut to 10 here so the 22 boards do evict each other: the week stays."""
    from league_lab import platforms

    MB.clear()
    monkeypatch.setattr(MB._cache, "max_entries", 10)
    scorings = sorted({platforms.ref_key(b, tep=t, p6=p) for b in platforms.REF_BASES for t in (False, True)
                       for p in (False, True)})
    leagues = [*scorings, SCRUBS, "1321941740235550720"]
    assert len(leagues) == 22
    week = None
    for lg in leagues:
        j = client.get(BOARD, params={"league": lg, "limit": 3}).json()
        assert j["rows"], lg
        week = j["week"]
    assert len(MB._cache) == 10                                        # the boards evicted each other
    assert len(MB._week) <= MB.WEEK_ENTRIES
    for kind in ("ctx", "pers", "ev"):
        assert MB._week.get((kind, 2026, week)) is not None, kind      # the week did not move
    assert MB.BOARD_ENTRIES >= 22                                      # in production every scoring fits
    MB.clear()
