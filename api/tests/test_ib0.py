"""Wave I-B, IB-0: one availability truth. Every screen reads the roster's context (``availability.roster_context``:
the nightly's rows + the overlay, re-solved when a status changed since the build), so My Week, Waivers, Team and the
trade calculator's "before" show the same lineup total, and a player who starts because of the overlay is never
"would not start". The ESPN fixture feed has Justin Jefferson Out (ankle); ``wilson_out`` adds Michael Wilson Out so
that Jacory Croskey-Merritt (9.19, the next man) is the one who starts at FLEX2 — the second review's case."""

from __future__ import annotations

import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import injury_feed as F

from league_lab_api import availability as AV
from league_lab_api import decisions
from league_lab_api.applib import cards

from .conftest import DYNASTY, SCRUBS, needs_db
from .test_i0a import ESPN, JEFFERSON, TEST_LEAGUE

MFL = "mfl:21861"
CM, WILSON = "00-0040242", "00-0038559"
CASES = [(SCRUBS, 2, None), (DYNASTY, 12, None), (TEST_LEAGUE, 10, None), (SCRUBS, 2, "sleeper"), (MFL, 4, None)]


def _switch(monkeypatch, on: bool) -> None:
    if on:
        monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
        monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    else:
        monkeypatch.setenv(AV.SWITCH_ENV, "off")
    F.reset()
    AV._snap = None
    AV._built = None
    AV.clear_context()
    decisions.clear_memo()


@pytest.fixture
def wilson_out(monkeypatch):
    """The fixture feed plus Michael Wilson Out (a copy of Jefferson's entry): Croskey-Merritt is the next man."""
    _switch(monkeypatch, True)
    real = AV.now

    def now(gsis_ids=None, sleeper_of=None):
        out = real(gsis_ids, sleeper_of)
        ids = None if gsis_ids is None else {str(g) for g in gsis_ids}
        if JEFFERSON in out and (ids is None or WILSON in ids):
            out[WILSON] = {**out[JEFFERSON], "gsis_id": WILSON, "name": "Michael Wilson", "note": "hamstring"}
        return out
    if JEFFERSON not in real([JEFFERSON]):
        pytest.skip("the ESPN fixture has no Jefferson entry")
    monkeypatch.setattr(AV, "now", now)
    yield
    AV.clear_context()


def _q(league, team, source) -> str:
    return f"league={league}&team={team}" + (f"&source={source}" if source else "")


def _totals(client, league, team, source) -> dict:
    q = _q(league, team, source)
    mw = client.get(f"/api/my-week?{q}").json()
    wv = client.get(f"/api/waivers?{q}&limit=200").json()
    tm = client.get(f"/api/team?{q}").json()
    rosters = A.sleeper().rosters(A.check_id(league))
    mine = next(r for r in rosters if int(r["roster_id"]) == int(team))
    other = next(r for r in rosters if int(r["roster_id"]) != int(team) and r.get("players"))
    body = {"league": league, "team": team, "partner": other["roster_id"], "give": [str(mine["players"][-1])],
            "get": [str(other["players"][-1])], "window": "week"}
    ev = client.post("/api/trades/evaluate" + (f"?source={source}" if source else ""), json=body).json()
    # IR-2: the calculator's primary basis fills an empty starting slot with the best free agent for the week; its
    # roster-only total (the separately labelled explanation) is the one every screen shares, and the basis's total is
    # that plus the named pickups
    d = ev["decision"]
    fills = sum(r["value"] or 0 for r in d["fills"]["mine"]["rows"] if r["state"] == "before" and r["week"] == ev["week"])
    assert d["mine"]["before"]["this_week"] == pytest.approx(d["unfilled"]["mine"]["before"]["this_week"] + fills, abs=0.011)
    return {"my_week": mw["lineup_value"], "waivers": wv.get("lineup_value"), "team": (tm.get("value") or {}).get("lineup_value"),
            "calculator": d["unfilled"]["mine"]["before"]["this_week"], "mw": mw, "wv": wv, "tm": tm, "ev": ev}


# ------------------------------------------------------------------------------ the four screens, one total
@needs_db
@pytest.mark.parametrize("on", [False, True], ids=["overlay-off", "overlay-on"])
@pytest.mark.parametrize("league,team,source", CASES, ids=["scrubs", "dynasty", "test-league", "scrubs-on-demand", "mfl"])
def test_one_lineup_total_on_every_screen(client, monkeypatch, league, team, source, on):
    _switch(monkeypatch, on)
    t = _totals(client, league, team, source)
    print(league, team, source, "overlay", on, {k: t[k] for k in ("my_week", "waivers", "team", "calculator")})
    assert t["my_week"] is not None
    for k in ("waivers", "team", "calculator"):
        assert t[k] == pytest.approx(t["my_week"], abs=0.011), k
    if on and league in (SCRUBS, TEST_LEAGUE):
        assert t["mw"]["availability"]["changes"], "the fixture feed moves this roster"
        assert t["tm"]["roster_context"]["changed"] and t["wv"]["roster_context"]["changed"]
        # the Team Hub's roster and its first sentence are the context's
        st = {r["slot"]: r["player_name"] for r in t["tm"]["roster"] if r["role"] == "starter"}
        mw = {r["slot"]: r["player_name"] for r in t["mw"]["lineup_full"] if r["role"] == "starter"}
        assert {cards.slot_label(k): v for k, v in st.items()} == {k: v for k, v in mw.items() if v}
        assert f"{t['my_week']:.1f}" in t["tm"]["words"]["lineup"][0]


@needs_db
@pytest.mark.parametrize("league,team", [(SCRUBS, 2), (TEST_LEAGUE, 10)])
def test_the_opponent_total_goes_through_the_overlay(client, monkeypatch, league, team):
    _switch(monkeypatch, True)
    d = client.get(f"/api/my-week?league={league}&team={team}").json()
    opp = d["opponent"]
    assert opp is not None and opp["lineup_value"] is not None
    theirs = client.get(f"/api/my-week?league={league}&team={opp['roster_id']}").json()
    assert opp["lineup_value"] == pytest.approx(theirs["lineup_value"], abs=0.011)
    assert opp["changes"] == theirs["availability"]["changes"]


def test_the_context_is_kept_for_the_overlays_interval(monkeypatch):
    calls = {"n": 0}
    frame = pd.DataFrame()

    def rows(*a, **k):
        calls["n"] += 1
        return frame
    monkeypatch.setattr(cards, "lineup_rows", rows)
    monkeypatch.setattr(cards, "league_season", lambda lid: 2026)
    monkeypatch.setattr(AV, "build_time", lambda: None)
    monkeypatch.setenv(AV.SWITCH_ENV, "off")
    AV.clear_context()
    a = AV.roster_context("L", 1, 4, house=True)
    b = AV.roster_context("L", 1, 4, house=True)
    assert a is b and calls["n"] == 1                          # one build per (league, roster, week, stamp)
    AV.roster_context("L", 2, 4, house=True)
    assert calls["n"] == 2
    AV.clear_context()


# ------------------------------------------------------------------------------ Croskey-Merritt, the review's case
@needs_db
@pytest.mark.parametrize("source", [None, "sleeper"])
def test_waivers_never_calls_an_overlay_starter_would_not_start(client, wilson_out, source):
    mw = client.get(f"/api/my-week?{_q(SCRUBS, 2, source)}").json()
    st = {r["slot"]: r["player_name"] for r in mw["lineup_full"] if r["role"] == "starter"}
    assert "Jacory Croskey-Merritt" in st.values(), "Jefferson and Wilson out: Croskey-Merritt starts"
    wv = client.get(f"/api/waivers?{_q(SCRUBS, 2, source)}&limit=500").json()
    assert wv["lineup_value"] == pytest.approx(mw["lineup_value"], abs=0.011)
    moves = [*wv["moves"], *[c["move"] for c in wv["cards"]]]
    drops_cm = [m for m in moves if (m.get("drop") or {}).get("gsis_id") == CM]
    for m in moves:
        d = m.get("drop") or {}
        if d.get("starts_this_week"):
            assert not [x for x in m["words"]["lines"] if "would not start" in x], m["words"]
    for m in drops_cm:
        assert m["drop"]["starts_this_week"] and m["drop"]["slot_this_week"]
        assert m["drop"]["horizon_loss"] > 0.05            # he is the only FLEX left: dropping him costs his points
    print("drops of Croskey-Merritt:", [(m["add"]["player_name"], m["words"]["headline"]) for m in drops_cm][:3])


@needs_db
def test_the_player_card_says_the_overlays_truth(client, wilson_out):
    d = client.get(f"/api/player/{CM}?league={SCRUBS}").json()
    avail = " ".join(b["text"] for b in d["sections"]["availability"]["blocks"] if b.get("text"))
    value = " ".join(b["text"] for b in d["sections"]["value"]["blocks"] if b.get("text"))
    assert "Justin Jefferson is out (ankle): he starts at FLEX2 this week" in avail
    assert "**starts at FLEX2**" in value and "'s bench" not in value
    jj = client.get(f"/api/player/{JEFFERSON}?league={SCRUBS}").json()
    text = " ".join(b["text"] for b in jj["sections"]["availability"]["blocks"] if b.get("text"))
    assert jj["injury_status"] == "Out" and "Out (ankle) · ESPN" in text and "Not in this week's lineup" in text


@needs_db
def test_the_player_card_on_demand_reads_the_context(client, monkeypatch):
    _switch(monkeypatch, True)
    d = client.get(f"/api/player/{WILSON}?league={SCRUBS}&source=sleeper").json()
    avail = " ".join(b["text"] for b in d["sections"]["availability"]["blocks"] if b.get("text"))
    value = " ".join(b["text"] for b in d["sections"]["value"]["blocks"] if b.get("text"))
    assert "Justin Jefferson is out (ankle): he starts at FLEX2 this week" in avail
    assert "**starts at FLEX2**" in value


@needs_db
def test_the_trade_board_this_week_is_the_context(client, monkeypatch):
    _switch(monkeypatch, True)
    ctx = decisions.trade_context(SCRUBS)
    now = ctx.now_rows
    me = now[now["roster_id"] == 2]
    starters = set(me.loc[me["role"] == "starter", "player_name"])
    assert "Michael Wilson" in starters and "Justin Jefferson" not in starters
    assert 2 in ctx.contexts and ctx.contexts[2].changed


# ------------------------------------------------------------------------------ the card's status (no database)
def _rows() -> pd.DataFrame:
    st = [("QB", "QB", 1, "QB1", "A QB", "QB", 20.0, 5.0), ("RB", "RB", 2, "RB1", "A RB", "RB", 12.0, 3.5),
          ("WR", "WR", 3, "WR1", "A WR", "WR", 11.0, 2.0), ("FLEX", "FLEX", 4, "FX", "C WR", "WR", 10.0, 0.4)]
    rows = [{"role": "starter", "slot": s, "slot_type": t, "slot_order": o, "bench_rank": None, "gsis_id": f"g-{sid}",
             "sleeper_player_id": sid, "player_name": n, "position": p, "value": v, "value_source": "season_ppg",
             "margin": m, "is_locked": False, "is_empty_slot": False, "report_status": None, "reason": None,
             "is_weakest_slot": s == "FLEX", "locked_now": False, "opponent": None, "opp_rank": None, "team": None}
            for s, t, o, sid, n, p, v, m in st]
    for k, (sid, n, p, v) in enumerate([("BR", "Bench RB", "RB", 8.5), ("BW", "Bench WR", "WR", 9.6)], 1):
        rows.append({**rows[0], "role": "bench", "slot": None, "slot_type": None, "slot_order": None, "bench_rank": k,
                     "gsis_id": f"g-{sid}", "sleeper_player_id": sid, "player_name": n, "position": p, "value": v,
                     "margin": None, "is_weakest_slot": False})
    return pd.DataFrame(rows)


def test_card_status_change_set_close():
    rows = _rows()
    # Sleeper starts the QB and the RB as we do; at WR it starts the bench WR instead of A WR
    sleeper = {"QB1", "RB1", "BW", "FX"}
    rows[cards.SLEEPER_STARTER] = rows["sleeper_player_id"].isin(sleeper)
    dec = cards.decisions(rows, 4).set_index("slot")
    assert dec.loc["FLEX", "status"] == "close" and dec.loc["FLEX", "strength"] == "coin flip"    # 0.4 apart
    assert dec.loc["WR", "status"] == "change" and dec.loc["WR", "strength"] == "lean"            # the bench WR starts
    assert dec.loc["RB", "status"] == "set" and dec.loc["RB", "strength"] == "clear"              # 3.5 apart
    assert cards.strength({"margin": 1.5, "p_win": 0.72}) == "clear"
    assert cards.strength({"margin": 1.5, "p_win": 0.6}) == "lean"
    assert cards.call_status({"margin": 2.0, "p_win": None, "sleeper_starter": True, "alt_sleeper_starter": True}) == "change"
    no_sleeper = cards.decisions(_rows(), 4).set_index("slot")             # without Sleeper's lineup: only a coin flip
    assert no_sleeper.loc["FLEX", "status"] == "close" and pd.isna(no_sleeper.loc["WR", "status"])


@needs_db
def test_my_week_cards_carry_the_status(client):
    seen = {}
    for league, team in ((SCRUBS, 2), (DYNASTY, 12), (MFL, 4)):
        d = client.get(f"/api/my-week?league={league}&team={team}").json()
        for c in d["cards"]:
            assert c["status"] in ("change", "set", "close") and c["strength"] in ("clear", "lean", "coin flip")
            assert c["in_sleeper_lineup"] is not None
            if c["status"] == "set":
                assert c["in_sleeper_lineup"] == {"player": True, "alt": False}
            seen.setdefault(c["status"], (league, c["slot"], c["player_name"]))
    print("status per fixture card:", seen)
    assert set(seen) == {"change", "set", "close"}


def test_a_drop_who_starts_with_an_equal_player_behind_him_is_not_would_not_start():
    """The page's rule ("would not start" when dropping him costs under 0.05) misreads a starter whose backup is as
    good (Wilson 9.20, Croskey-Merritt 9.19): the context says he starts, so the sentence says so."""
    class Ctx:
        def row_of(self, key):
            return pd.Series({"role": "starter", "is_empty_slot": False, "slot": "FLEX2"}) if key == WILSON else None
    m = {"drop": {"gsis_id": WILSON, "player_name": "Michael Wilson", "horizon_loss": 0.01},
         "words": {"lines": ["Claim him.", "Michael Wilson would not start for you in the next 4 weeks."]}}
    AV.drop_words(m, Ctx())
    assert m["drop"]["starts_this_week"] and m["drop"]["slot_this_week"] == "FLEX2"
    assert m["words"]["lines"][1] == ("Michael Wilson starts at FLEX2 for you this week, but the player behind him is as "
                                      "good: dropping him costs your lineup 0.0 over the next 4 weeks (already counted).")
    bench = {"drop": {"gsis_id": CM, "player_name": "Jacory Croskey-Merritt", "horizon_loss": 0.0},
             "words": {"lines": ["Jacory Croskey-Merritt would not start for you in the next 4 weeks."]}}
    AV.drop_words(bench, Ctx())
    assert bench["drop"]["starts_this_week"] is False and "would not start" in bench["words"]["lines"][0]
