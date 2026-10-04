"""Wave I-I, II-1 — credible trades (docs/reviews/2026-10-04-product-and-analytics-handoff.md § 2).

The review's regression: the Finder suggested "Nick Folk -> Run Bijan Run for Matthew Stafford + Will Reichard" with
+19.4 for MacZaddy in week 5 (Mahomes's bye, no backup QB: the QB slot priced at zero) and −8.4 in week 6 (Reichard's
bye: the kicker slot empty), "Improves it a lot" for the other side. The fixture is built from the Scrubs rosters on the
clone (2026-09-26): Folk takes Chase McLaughlin's place on roster 2, Reichard takes Trey Smack's on roster 3 (Run Bijan
Run, who have Stafford); `as_reviewed` also takes MacZaddy's backup QBs (Bryce Young, Tyler Shough) off, as the live
roster was when the review ran (its Brissett claim, +19.9, covered the same bye). The engine must not promote it.
"""

from __future__ import annotations

import pandas as pd
import pytest
from league_lab import trades as T
from league_lab.roster_value import RosterBoard

from league_lab_api import decisions as D

from .conftest import SCRUBS, needs_db

FOLK, REICHARD, STAFFORD = "650", "11792", "421"
MCLAUGHLIN, SMACK, YOUNG, SHOUGH = "6650", "13545", "9228", "12545"
FOLK_GSIS, REICHARD_GSIS = "00-0025565", "00-0039404"


def _proj(gsis: str) -> dict[int, float]:
    df = D.query("""select week, round(proj_points::numeric, 2)::double precision as v from ops.projections
                    where league_id = %s and season = 2026 and gsis_id = %s""", (SCRUBS, gsis))
    return {int(w): float(v) for w, v in zip(df["week"], df["v"], strict=True)}


def _swap(h: pd.DataFrame, old: str, new: str, gsis: str, name: str) -> pd.DataFrame:
    pts = _proj(gsis)
    h = h.copy()
    m = h["sleeper_player_id"] == old
    for i in h.index[m]:
        w = int(h.at[i, "week"])
        h.loc[i, ["sleeper_player_id", "gsis_id", "player_name"]] = [new, gsis, name]
        v = pts.get(w)
        if v is None:                       # his bye: unplayable that week (the solver sees an empty kicker slot)
            h.loc[i, ["role", "slot", "slot_type", "player_value", "lineup_margin", "reason"]] = [
                "unplayable", None, None, None, None, "bye"]
        else:
            h.at[i, "player_value"] = v
    return h


def folk_context(monkeypatch, *, as_reviewed: bool = True) -> D.TradeContext:
    D.clear_memo()
    ctx = D.TradeContext(SCRUBS)
    h = _swap(ctx.horizon, MCLAUGHLIN, FOLK, FOLK_GSIS, "Nick Folk")
    h = _swap(h, SMACK, REICHARD, REICHARD_GSIS, "Will Reichard")
    if as_reviewed:
        h = h[~h["sleeper_player_id"].isin([YOUNG, SHOUGH])]
    ctx.horizon = h.reset_index(drop=True)
    ctx.board = RosterBoard(ctx.horizon.to_dict("records"), tuple(ctx.slots))
    ctx.market = T.market_by_player(ctx.board, ctx.points)
    ctx.prices = T.price_by_player(ctx.board, ctx.market, ctx.replacement)
    ctx.info = ctx.horizon.sort_values("week").drop_duplicates("sleeper_player_id").set_index("sleeper_player_id")
    ctx.now_rows = ctx.horizon[ctx.horizon["week"] == ctx.this_week].set_index("sleeper_player_id")
    ctx.window_cache = {}
    monkeypatch.setattr(D, "trade_context", lambda *a, **k: ctx)
    return ctx


@needs_db
def test_folk_package_is_not_promoted(monkeypatch):
    """What the engine says about the Folk package now (the hand-back quotes this test's print)."""
    folk_context(monkeypatch)
    out = D.evaluate(SCRUBS, 2, 3, [FOLK], [STAFFORD, REICHARD])
    c = out["card"]
    raw = out["strip"]["mine"]
    print("\nraw strip (as before):", out["strip"])
    print("covered:", c["your_effect"]["by_week"], c["their_effect"]["by_week"])
    print("beyond:", c["beyond"], "| plausibility:", c["plausibility"])
    print("consider:", c["why_consider"], "\nrefuse:", c["why_refuse"], "\nlegal:", c["legal"]["notes"])
    print("alternatives:", c["waiver_alternative"]["words"])
    # the review's shape: the raw week 5 gain is the empty QB slot (Mahomes's bye) priced at zero; week 6 Reichard's bye
    assert raw[1] >= 15 and raw[2] <= -7
    # on the covered frame the bye is filled from the free pool for both teams: the week-5 gain is Stafford over the best
    # free QB, the week-6 loss is the free kicker against Folk — no manufactured swing
    cov = c["your_effect"]["by_week"]
    assert abs(cov[1]) < 5 and abs(cov[2]) < 3
    assert c["your_effect"]["raw_window"] == pytest.approx(sum(raw), abs=0.02)
    # the K / DEF guardrail fires (a kicker for a starter; their kicker slot is filled every week and the free pool
    # holds one as good) - derived from the slots and the free pool, no names in the rule
    assert c["plausibility"]["key"] == "implausible"
    assert any(g["rule"] == "streamable_for_starter" for g in c["guardrails"])
    assert c["guardrails"][0]["starter"] == STAFFORD
    assert not c["credible"]
    # "Improves it a lot" was the old dial's word for their side; the card says why they would refuse
    assert c["why_refuse"] and any("kicker" in r.lower() or " K " in r for r in c["why_refuse"])
    assert "probab" not in str(c).lower() and "%" not in " ".join(c["why_consider"] + c["why_refuse"])


@needs_db
def test_folk_package_on_the_clone_rosters(monkeypatch):
    """With MacZaddy's backup QBs kept (the clone's rosters), the same verdict: not credible, the guardrail named."""
    folk_context(monkeypatch, as_reviewed=False)
    c = D.evaluate(SCRUBS, 2, 3, [FOLK], [STAFFORD, REICHARD])["card"]
    assert c["plausibility"]["key"] == "implausible" and not c["credible"]


@needs_db
def test_finder_never_headlines_the_folk_package(monkeypatch):
    folk_context(monkeypatch)
    p = D.partners(SCRUBS, 2)
    print("\nverdict:", p["verdict"], "| credible", p["credible_count"], "explore", p["explore_count"])
    for r in p["partners"]:
        if [x["sleeper_id"] for x in r["give"]] == [FOLK]:
            assert r["tier"] == "explore"
    cred = [r for r in p["partners"] if r["tier"] == "credible"]
    assert len(cred) <= T.CREDIBLE_MAX and p["credible_count"] == len(cred)
    assert all(r["card"]["credible"] for r in cred)
    # IF-2's order and ranks are kept; the credible rows are numbered in that order and the headline is the first one,
    # or the honest empty state
    assert [r["rank"] for r in p["partners"]] == list(range(1, len(p["partners"]) + 1))
    assert [r["credible_rank"] for r in cred] == list(range(1, len(cred) + 1))
    if cred:
        assert p["headline_rank"] == cred[0]["rank"]
    if not cred:
        assert p["verdict"]["kind"] == "none" and p["verdict"]["headline"] == T.NO_COMPELLING
        assert p["words"]["headline"].startswith(f"**{T.NO_COMPELLING}.**") and p["verdict"]["reason"]


@needs_db
def test_scrubs_roster_2_finder(client):
    """The review's team on the clone: the answer, and every row's card has the review's fields."""
    p = client.get(f"/api/trades/partners?league={SCRUBS}&team=2").json()
    print("\nheadline:", p["words"]["headline"], "| credible", p["credible_count"], "explore", p["explore_count"])
    assert p["credible_count"] + p["explore_count"] == len(p["partners"])
    for r in p["partners"]:
        c = r["card"]
        for k in ("give", "get", "drops", "your_effect", "their_effect", "depth_cost", "waiver_alternative",
                  "why_consider", "why_refuse", "plausibility", "beyond", "legal", "credible"):
            assert k in c, k
        # the headline trade never loses to its own waiver comparison (the review's Mahomes-for-Maye)
        if r["tier"] == "credible":
            assert c["beyond"]["mine"] >= T.CREDIBLE_MARGIN and c["beyond"]["theirs"] >= T.CREDIBLE_MARGIN
            assert r["beats_alternative"] and not r["demoted"]       # never a trade its own IF-2 line marks below
        # both alternatives are named with whether they are guaranteed or a claim that might be lost
        for side in ("mine", "theirs"):
            assert c["waiver_alternative"][side]["availability"] in ("guaranteed", "claim")
    if p["verdict"]["kind"] == "compelling":
        first = next(r for r in p["partners"] if r["tier"] == "credible")
        assert all(x["player_name"] in p["words"]["headline"] for x in first["give"])
    else:
        assert p["words"]["headline"].startswith("**No compelling trade found.**")


@needs_db
def test_both_teams_get_the_same_free_agent_treatment(monkeypatch):
    """Symmetric: the card of A giving x for y, read from B's side (B gives y for x), swaps mine and theirs exactly."""
    ctx = folk_context(monkeypatch, as_reviewed=False)
    board, weeks, span = D.window_board(ctx, "next4")
    frame = D.ii1_frame(ctx, board, weeks, "next4")
    give, get = [FOLK], [STAFFORD]
    a = D.ii1_card(ctx, board, weeks, span, "next4", frame, 2, give, get)
    b = D.ii1_card(ctx, board, weeks, span, "next4", frame, 3, get, give)
    assert a["your_effect"]["by_week"] == b["their_effect"]["by_week"]
    assert a["their_effect"]["by_week"] == b["your_effect"]["by_week"]
    assert a["beyond"]["mine"] == b["beyond"]["theirs"] and a["beyond"]["theirs"] == b["beyond"]["mine"]
    for k in ("covered_window", "availability", "gain_window"):
        assert a["waiver_alternative"]["mine"][k] == b["waiver_alternative"]["theirs"][k]
        assert a["waiver_alternative"]["theirs"][k] == b["waiver_alternative"]["mine"][k]
    assert a["plausibility"]["key"] == b["plausibility"]["key"]
