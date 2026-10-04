"""Wave I-I, II-0 (the fifth review § 1): the calculation audit on the API.

* Team → strength by slot reads one metric over one population: each slot apart (RB1, RB2, each FLEX), the player each
  roster starts there this week, his projected points; the league's average / best / worst / rank over those numbers
  (recomputed here from the mart, independently); the displayed best is never below a member; group totals add the
  slots; usable depth is the bench's own best lineup (`bench_value`). The old `slot_strength` block's league line is on
  its bar's own metric (the best starter's projected points), never on margins.
* The lineup margins (My Week), the player card's "without him the lineup loses x" and the chain's words are one answer.
* The partner card's story is the strip's numbers: a week that loses is never "Nothing changes this week".
* An MFL team QB (dad's league fixtures): the slot is the unit's, named with its team.

The house-league tests read the clone's marts (Scrubs, MacZaddy roster 2). On a Sunday afternoon games lock as they
kick off; the assertions hold either way (they compare the answers with each other, not with pinned numbers).
"""

from __future__ import annotations

import re
from collections import defaultdict

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import player_ids as PI

from league_lab_api import decisions

from .conftest import SCRUBS, needs_db
from .test_i0b import IDS, MFL_FX

TEAM = 2


def _team(client, league=SCRUBS, team=TEAM) -> dict:
    r = client.get(f"/api/team?league={league}&team={team}")
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ------------------------------------------------------------------ strength by slot
@needs_db
def test_strength_by_slot_is_one_metric_over_one_population(client, sql):
    d = _team(client)
    sb = d["strength_by_slot"]
    assert sb["metric"] == "projected_points" and sb["n_rosters"] == 10
    starters = [r for r in d["roster"] if r["role"] in ("starter", "empty")]
    assert len(sb["slots"]) == len(starters)                      # every slot of the allotment, apart
    by_type = defaultdict(list)
    for s in sb["slots"]:
        by_type[s["slot_type"]].append(s)
        lg = s["league"]
        if s["value"] is not None:
            assert lg["best"] >= s["value"] - 1e-9 and lg["worst"] <= s["value"] + 1e-9     # the best is never below
            assert lg["worst"] - 1e-9 <= lg["avg"] <= lg["best"] + 1e-9
            assert 1 <= lg["rank"] <= lg["n"]
    for t, ss in by_type.items():
        vals = [s["value"] for s in ss if s["value"] is not None]
        assert vals == sorted(vals, reverse=True), t                 # RB1 >= RB2, FLEX1 >= FLEX2
        if len(ss) > 1:
            assert [s["slot"] for s in ss] == [f"{t}{k}" for k in range(1, len(ss) + 1)]
    # my bars are my starters' projections (the Team roster rows)
    mine = sorted(round(r["value"], 2) for r in starters if r.get("value") is not None)
    assert sorted(s["value"] for s in sb["slots"] if s["value"] is not None and not s["empty"]) == mine
    # groups add their slots; usable depth is the bench's own best lineup
    for g in sb["groups"]:
        assert g["total"] == pytest.approx(sum(s["value"] or 0.0 for s in by_type[g["slot_type"]]), abs=0.011)
        assert g["league"]["best"] >= g["total"] - 1e-9
    assert sb["depth"]["usable"] == pytest.approx(d["value"]["bench_value"], abs=0.01)
    assert sb["depth"]["raw_bench"] >= sb["depth"]["usable"] - 0.01
    # the population, independently from the mart (when the overlay moved no roster this week)
    if (d.get("roster_context") or {}).get("changed"):
        pytest.skip("the overlay moved a lineup: the mart is not the population this week")
    rows = sql("""select roster_id, slot_type, role, player_value from analytics.mart_league_roster_horizon
                  where league_id = %s and is_this_week and role in ('starter', 'empty')""", (SCRUBS,))
    pop: dict[str, dict[int, float]] = defaultdict(dict)
    per = defaultdict(list)
    for r in rows:
        per[(r["roster_id"], r["slot_type"])].append(0.0 if r["role"] == "empty" else r["player_value"])
    for (rid, t), vs in per.items():
        known = sorted((float(v) for v in vs if v is not None), reverse=True)
        for k, v in enumerate(known, 1):
            pop[f"{t}{k}" if len(vs) > 1 else t][rid] = v
    for s in sb["slots"]:
        vals = list(pop[s["slot"]].values())
        assert s["league"]["n"] == len(vals)
        assert s["league"]["avg"] == pytest.approx(sum(vals) / len(vals), abs=0.006)
        assert s["league"]["best"] == pytest.approx(max(vals), abs=0.006)
        if s["value"] is not None:
            assert s["league"]["rank"] == 1 + sum(1 for v in vals if v > s["value"] + 1e-9)


@needs_db
def test_the_old_slot_block_reads_its_bars_own_metric(client):
    """`slot_strength[].league` was every roster's margin beside my best starter's points (12.75 vs "average 4.13,
    best 6.83"); it is the best starter's projected points now, the same population as `strength_by_slot`'s first slot
    of each type."""
    d = _team(client)
    first = {}
    for s in d["strength_by_slot"]["slots"]:
        first.setdefault(s["slot_type"], s)
    for s in d["slot_strength"]:
        v = (s["top"] or {}).get("value")
        if v is None or s["league"] is None:
            continue
        assert s["league"]["best"] >= v - 1e-9
        f = first[s["slot_type"]]
        assert s["league"]["best"] == pytest.approx(f["league"]["best"], abs=0.011), s["slot_type"]
        assert s["league"]["rank"] == f["league"]["rank"], s["slot_type"]


# ------------------------------------------------------------------ the lineup, the card, the chain: one answer
@needs_db
def test_lineup_margins_and_the_card_say_the_same_number(client):
    w = client.get(f"/api/my-week?league={SCRUBS}&team={TEAM}")
    assert w.status_code == 200, w.text[:300]
    rows = [x for x in w.json()["lineup"] if x.get("margin") is not None and x.get("margin_words")
            and x.get("gsis_id") and "no eligible reserve" not in x["margin_words"]]
    if not rows:
        pytest.skip("every starter is locked or has no reserve this hour")
    for x in rows[:3]:
        c = client.get(f"/api/player/{x['gsis_id']}?league={SCRUBS}&team={TEAM}")
        assert c.status_code == 200
        text = c.text
        m = re.search(r"without him the lineup loses \*\*(\d+\.\d\d)\*\*", text)
        assert m, f"no lineup sentence for {x['gsis_id']}"
        assert float(m.group(1)) == pytest.approx(x.get("margin_now", x["margin"]), abs=0.006)   # the re-solve after a lock
        if x.get("margin_chain"):                                  # a cascade: the card says the same moves
            plain = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", c.json().get("lineup_line") or text)
            assert x["margin_chain"] in plain or x["margin_chain"] in re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)


# ------------------------------------------------------------------ one frame, one story
@needs_db
def test_partner_story_is_the_strips_numbers(client):
    r = client.get(f"/api/trades/partners?league={SCRUBS}&team={TEAM}")
    assert r.status_code == 200, r.text[:300]
    rows = r.json()["partners"]
    assert rows
    for p in rows:
        st, s = p["story"], p["strip"]
        assert [x["change"] for x in st["by_week"]] == s["mine"]
        w0 = s["mine"][0]
        if w0 is not None and w0 <= -0.05:
            assert f"loses {abs(w0):.1f} this week" in st["words"] and "Nothing changes" not in st["words"]
        assert st["window"]["change"] == pytest.approx(sum(x for x in s["mine"] if x is not None), abs=0.011)
        assert st["window"]["change"] == pytest.approx(p["you_gain_horizon"], abs=0.02)
    # the calculator's answer for the first package: the story is its own strip
    p = rows[0]
    body = {"league": SCRUBS, "team": TEAM, "partner": p["partner"], "give": [x["sleeper_id"] for x in p["give"]],
            "get": [x["sleeper_id"] for x in p["get"]]}
    e = client.post("/api/trades/evaluate", json=body)
    assert e.status_code == 200, e.text[:300]
    e = e.json()
    assert [x["change"] for x in e["story"]["by_week"]] == e["strip"]["mine"]
    w0 = e["strip"]["mine"][0]                       # the effect sentence's "this week" is the strip's first week
    if e["story"]["this_week"]["kind"] in ("gain", "loss"):
        assert f"{abs(w0):.1f} {'more' if w0 > 0 else 'fewer'} points this week" in e["effect_words"]
        assert e["fit"]["this_week"]["mine"] == pytest.approx(w0, abs=0.006)


# ------------------------------------------------------------------ an MFL team QB (dad's league fixtures)
@pytest.fixture
def _mfl(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    decisions.clear_memo()
    yield
    PI.reset()
    A._default = None
    decisions.clear_memo()


@needs_db
def test_mfl_team_qb_slot_is_the_units(client, _mfl):
    r = client.get("/api/team?league=mfl:70587&team=1")
    if r.status_code != 200 or not (r.json().get("strength_by_slot") or {}).get("slots"):
        pytest.skip("no lineup ahead on the fixtures at this hour")
    sb = r.json()["strength_by_slot"]
    qb = next(s for s in sb["slots"] if s["slot_type"] == "TMQB")
    if qb["empty"]:          # on a Sunday afternoon the on-demand path locks the units whose game started: empty = 0
        assert qb["player"] is None and qb["value"] == 0.0 and qb["league"]["n_empty"] >= 1
    else:
        assert qb["player"]["unit"] is True and qb["player"]["short_name"].endswith(" QB") and qb["player"]["team"]
    assert qb["league"]["best"] >= (qb["value"] or 0.0) - 1e-9
    assert all(s["league"]["best"] >= (s["value"] or 0.0) - 1e-9 for s in sb["slots"])
    assert {s["slot"] for s in sb["slots"] if s["slot_type"] == "WR+TE"} == {"WR+TE1", "WR+TE2", "WR+TE3"}


# ------------------------------------------------------------------ the answers web/e2e/ii0 replays
@needs_db
@pytest.mark.skipif(not __import__("os").environ.get("II0_RECORD"), reason="records web/fixtures/ii0 (II0_RECORD=1)")
def test_record_e2e_answers(client):
    """League of Scrubs roster 2 (MacZaddy) on the clone: the Team screen (strength by slot) and the partner finder
    (the stories). Re-record: cd api && II0_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_ii0.py -k record"""
    import json
    from urllib.parse import urlencode

    from league_lab_api.settings import ROOT

    def key(path: str, **q) -> str:
        return path + ("?" + urlencode(sorted((k, str(v)) for k, v in q.items())) if q else "")

    out: dict = {}
    for path, q in (("/api/team", {"league": SCRUBS, "team": TEAM}), ("/api/trades/partners", {"league": SCRUBS, "team": TEAM})):
        r = client.get(key(path, **q))
        out[key(path, **q)] = {"status": r.status_code, "body": r.json()}
    f = ROOT / "web" / "fixtures" / "ii0" / "api_ii0.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    assert all(v["status"] == 200 for v in out.values()), {k: v["status"] for k, v in out.items()}


def test_team_closest_call_names_the_legal_chain():
    """The Team card's closest call: when the replacement cannot play the slot himself, the chain that makes it legal."""
    import pandas as pd

    def r(role, slot, stype, order, name, pos, value, margin=None, rank=None):
        return {"role": role, "slot": slot, "slot_type": stype, "slot_order": order, "bench_rank": rank,
                "sleeper_player_id": name, "gsis_id": name, "player_name": name, "position": pos, "player_value": value,
                "value_source": "proj_points", "lineup_margin": margin, "is_locked": False}
    rows = pd.DataFrame([r("starter", "RB", "RB", 1, "Kyren Williams", "RB", 9.0, 0.5),
                         r("starter", "WR", "WR", 2, "Puka Nacua", "WR", 14.8, 5.0),
                         r("starter", "FLEX", "FLEX", 3, "Bhayshul Tuten", "RB", 8.6, 0.6),
                         r("bench", None, None, None, "Malik Washington", "WR", 8.5, rank=1)])
    v = {"weakest_slot": "RB", "weakest_player_name": "Kyren Williams", "weakest_position": "RB",
         "weakest_replacement_name": "Malik Washington", "weakest_margin": 0.5}
    assert decisions._weakest_chain_words(v, rows) == (" Without him, Bhayshul Tuten (RB) moves from FLEX to RB; "
                                                       "Malik Washington (WR) fills the open FLEX.")
    v2 = dict(v, weakest_slot="FLEX", weakest_player_name="Bhayshul Tuten")
    assert decisions._weakest_chain_words(v2, rows) == ""            # a direct swap needs no chain
