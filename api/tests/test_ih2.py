"""Wave I-H, IH-2 — the small opens from I-G.

1. Waivers' drop cost on team units: `_moves_on_demand` prices a dropped MFL team unit (TMQB / TMPK) with IG-1's
   `unit_market` (its season points above the best FREE unit of its kind), so its future starts are no longer measured
   against a free unit worth 0. The trade verdict leans on no partial season-value sum (a side with an uncounted player).
2. The console's Waiver Wire stash region reads the writer's call (`stash_action`): a watch names no drop and says the
   API's words (one source: `signals.watch_words`); the console twin renders the page and says what the API says.
3. The Team page's MFL roster-freshness line (`roster_updated_at`); Sleeper's `daily_waivers_days` decoded in the
   waiver deadline ("Claims run every day except Saturday at 5:00 AM ET").
4. "What changed": a Questionable tag that changed no lineup shows once ("Questionable: Flowers (hamstring) — your lineup
   is unchanged").
5. `game_key` on availability events: the player's team's game in the week in play (nflverse `game_id`, `dim_game`).

The MFL cases run on the fixtures (dad's league `mfl:70587`, IG-1's setup); the Scrubs / dynasty cases read the clone
`league_lab_i0b` (needs_db). Recording for web/e2e/ih2: `IH2_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_ih2.py -k record`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from league_lab import trades as T
from league_lab import waivers as W

from league_lab_api import availability as AV
from league_lab_api import decisions, events, myweek
from league_lab_api.settings import ROOT

from .conftest import DYNASTY, SCRUBS, SLEEPER_FIXTURES, needs_db
from .test_if4 import overlay  # noqa: F401 - the ESPN overlay on the fixtures
from .test_ig1 import mfl  # noqa: F401 - dad's league on the MFL fixtures

# PO (2026-10-04): the three on-demand MFL waiver pins below read the clock through the on-demand path (locked
# players after a kickoff change the legal moves: 41 -> 40 on a Sunday afternoon, and which drop is cheapest).
# ---- INF-1 (Wave I-I): the suite's clock is pinned (api/tests/conftest.py `PINNED_NOW`, league_lab.clock): the
# xfail(strict=False) marks are gone — they pass at any hour.

DAD = "mfl:70587"
sys.path.insert(0, str(ROOT / "app"))
from lib import signals as SG  # noqa: E402 - the console's module (the API loads the same file through applib)


def _league(lid: str) -> dict:
    return json.loads((SLEEPER_FIXTURES / f"league_{lid}.json").read_text())


NOW = pd.Timestamp("2026-10-04 07:50", tz="UTC")       # Sunday 3:50 AM ET


# ------------------------------------------------------------------ 1. units' drop cost (dad's league, fixtures)
def _row(mv: pd.DataFrame, add: str, drop: str) -> pd.Series:
    r = mv[(mv["add_name"] == add) & (mv["drop_name"] == drop)]
    assert len(r) == 1, (add, drop, len(r))
    return r.iloc[0]


def test_a_dropped_team_unit_has_a_season_value(mfl):  # noqa: F811
    """Team 8 "Big Mac Attack": dropping the Chicago Bears QB (a team QB) for the Atlanta Falcons defense. Before, the
    unit had no season points and its later starts were measured against a free team QB worth 0 (cost 28.22, future
    starts; net −15.41 over the horizon). Now: 345.93 season points against the best free team QB's 378.22 (0 above
    replacement), and the later starts against that replacement — cost 4.09 (the lineup loss), net +8.72."""
    mv, _ = decisions._moves_on_demand(DAD, 8)
    r = _row(mv, "Atlanta Falcons", "Chicago Bears QB")
    assert r["drop_position"] == "TMQB"
    assert r["drop_season_points"] == pytest.approx(345.93) and r["drop_replacement_points"] == pytest.approx(378.22)
    assert r["drop_season_value"] == 0 and r["drop_future_starts"] == pytest.approx(0.20)
    assert (r["drop_cost"], r["drop_cost_piece"]) == (pytest.approx(4.09), "lineup_loss")
    assert r["net_horizon_gain"] == pytest.approx(8.72)
    k = _row(mv, "New Orleans Saints K", "Houston Texans K")              # a team kicker: 118.55 → 2.14
    assert k["drop_replacement_points"] == pytest.approx(169.47) and k["drop_cost"] == pytest.approx(2.14)
    # every unit drop has a season value now; no player's drop moved
    units = mv[mv["drop_position"].isin(["TMQB", "TMPK"])]
    assert len(units) == 35 and units["drop_season_points"].notna().all()
    assert units["drop_replacement_points"].gt(0).all()


def test_team_8s_waivers_answer_has_no_drop_to_price(client, mfl):  # noqa: F811
    """Team 8 has an open roster spot: every best claim is "no drop needed", so its Waivers numbers do not move (the
    hand-back's before / after); the first move stays the Falcons defense, +1.2 this week, +12.8 over the horizon."""
    w = client.get("/api/waivers", params={"league": DAD, "team": 8}).json()
    assert len(w["moves"]) == 41 and all(m["drop"] is None for m in w["moves"])
    m = w["moves"][0]
    assert (m["add"]["player_name"], m["net_weekly_gain"], m["net_horizon_gain"]) == ("Atlanta Falcons", 1.2, 12.81)


def test_a_kicker_claim_drops_the_kicker_it_replaces(client, mfl):  # noqa: F811
    """Team 2: claiming the New Orleans Saints kicker now drops the Jacksonville Jaguars kicker it replaces (before: Cooper
    Kupp — the unit's drop looked expensive against a free kicker worth 0). Same gains, the cost 0 either way."""
    w = client.get("/api/waivers", params={"league": DAD, "team": 2}).json()
    m = next(x for x in w["moves"] if x["add"]["player_name"] == "New Orleans Saints K")
    assert m["drop"]["player_name"] == "Jacksonville Jaguars K" and m["drop"]["position"] == "TMPK"
    assert (m["net_weekly_gain"], m["net_horizon_gain"]) == (2.55, 17.06)


def _side(po, pi, uo=(), ui=(), gw=0.0, gh=0.0):
    return SimpleNamespace(gain_week=gw, gain_horizon=gh, price_out=po, price_in=pi, unknown_out=tuple(uo), unknown_in=tuple(ui))


def test_the_verdict_leans_on_no_partial_season_value():
    """A side with a player the season value cannot count has no sum: the verdict says so and leans nowhere (it said
    "you give up more season value" from the counted players alone)."""
    known = SimpleNamespace(mine=_side(40, 7, gw=2.0, gh=5.0), theirs=_side(7, 40, gw=-1.0, gh=-3.0))
    assert T.verdict(known, "weeks 4–7").endswith("you give up more season value: a lineup loss for them; the value is on their side.")
    part = SimpleNamespace(mine=_side(40, 7, uo=["mfl:0682"], gw=2.0, gh=5.0), theirs=_side(7, 40, gw=-1.0, gh=-3.0))
    v = T.verdict(part, "weeks 4–7")
    assert v.endswith("season value not compared (1 player in it has no season projection): a lineup loss for them.")
    two = SimpleNamespace(mine=_side(3, 30, uo=["a"], ui=["b"]), theirs=_side(30, 3))
    assert "season value not compared (2 players in it have no season projection): not worth it for your lineup." in T.verdict(two, "x")


# ------------------------------------------------------------------ 2. the console's stash words (stash_action)
def _stash_row(**kw) -> pd.Series:
    base = {"week": 4, "horizon_last_week": 7, "base_value": 2.5, "scenario_value": 2.9, "holds_weekly_gain": 0.0,
            "holds_horizon_gain": 0.0, "holds_slot": None, "drop_name": "Marvin Harrison Jr.", "drop_position": "WR",
            "drop_horizon_loss": 0.0, "since_week": 2, "games_held": 1, "kind": "teammate_out", "expires_after_week": None,
            "expiry_rule": None, "trigger_name": None, "net_horizon_gain": None}
    return pd.Series({**base, **kw})


def test_a_watch_names_no_drop_a_claim_keeps_it():
    w = _stash_row(stash_action="watch")
    assert not any(x.startswith("Drop ") for x in SG.upside_detail(w))
    assert SG.stash_call_words(w) == ("Watch, no claim yet: if his role holds he adds +0.0 to your lineup over weeks 4–7 "
                                      "with Harrison Jr. dropped — under 1 this week and 3 over the weeks. Claim him when his "
                                      "role would put him in your lineup for more, or when a roster spot opens.")
    c = _stash_row(stash_action="claim", holds_horizon_gain=6.4, net_horizon_gain=4.1, drop_horizon_loss=2.3)
    assert "Drop Marvin Harrison Jr. (WR): costs your lineup 2.3 over weeks 4–7." in SG.upside_detail(c)
    assert SG.stash_call_words(c) == "Claim: if his role holds he adds +6.4 to your lineup over weeks 4–7; after what dropping Harrison Jr. costs, +4.1."
    old = _stash_row()                                              # a row written before the call: the older words
    assert any(x.startswith("Drop ") for x in SG.upside_detail(old)) and SG.stash_call_words(old) is None
    assert SG.STASH_CAPTION[SG.stash_call(w)].startswith("Upside stash · watch")
    opened = _stash_row(stash_action="watch", drop_name=None)       # an open spot: no drop either way
    assert "You have an open roster spot, so nobody has to go." in SG.upside_detail(opened)


def test_the_watch_words_are_one_source():
    """The API's watch line (`decisions.ig3_watch_words`) is the console's `signals.watch_words`; the short names and the
    claims' bar agree."""
    s = {"holds_horizon_gain": 0.0, "net_horizon_gain": None, "cheapest_drop": {"player_name": "Marvin Harrison Jr."}}
    assert decisions.ig3_watch_words(s, "weeks 4–7") == SG.watch_words(0.0, None, "Harrison Jr.", "weeks 4–7")
    s = {"holds_horizon_gain": 2.0, "net_horizon_gain": -1.5, "cheapest_drop": {"player_name": "Kansas City Chiefs"}}
    assert decisions.ig3_watch_words(s, "weeks 4–7") == SG.watch_words(2.0, -1.5, "Kansas City Chiefs", "weeks 4–7")
    for n in ["Jacory Croskey-Merritt", "Marvin Harrison Jr.", "Amon-Ra St. Brown", "Kenneth Walker III", "Jets", None, "",
              *[f"Somewhere {k}" for k in decisions.NICKNAMES]]:
        assert SG.short_name(n) == decisions._last(n), n
    assert SG.TEAM_NICKNAMES == decisions.NICKNAMES
    assert (SG.WORTH_WEEK, SG.WORTH_HORIZON) == (W.WORTH_WEEK, W.WORTH_HORIZON)


def _plain(t: str | None) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t or "").replace("**", "")


@needs_db
def test_the_console_twin_says_what_the_api_says(client):
    """League of Scrubs roster 6 (the clone: every stash a watch): the console's stash card (Streamlit, headless) and the
    API's first stash — the same detail lines (no drop named), the same watch line; the caption says watch."""
    w = client.get("/api/waivers", params={"league": SCRUBS, "team": 6}).json()
    st0 = w["upside"]["stashes"][0]
    assert st0["stash_action"] == "watch" and st0["drop"] is None
    tw = _twin_waivers(SCRUBS, 6)
    assert tw["caption"].startswith("Upside stash · watch, no claim yet")
    assert [_plain(x) for x in tw["lines"]] == [_plain(x) for x in st0["lines"]]
    assert not any(x.startswith("Drop ") for x in tw["lines"])
    assert tw["call"] == st0["watch_words"]


def _twin_waivers(league: str, team: int) -> dict:
    import os
    import shutil
    import subprocess

    if os.environ.get("LL_SKIP_PARITY") or not shutil.which("uv"):
        pytest.skip("no repository environment for the Streamlit twin")
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")}
    res = subprocess.run(["uv", "run", "--project", str(ROOT), "python", str(Path(__file__).with_name("twin_ih2.py")),
                          "waivers", league, str(team)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    line = next((x for x in res.stdout.splitlines() if x.startswith("TWIN-JSON ")), None)
    assert res.returncode == 0 and line is not None, res.stderr[-2000:]
    return json.loads(line[len("TWIN-JSON "):])


# ------------------------------------------------------------------ 3. MFL freshness on Team; daily_waivers_days
def test_daily_waivers_days_decoded():
    """Two bits a day, the low bit = claims run that day (Monday first): Sleeper's default 5461 = every day; the
    dynasty's 15359 = every day except Saturday; its 2022–2024 value 15356 (and 2023's 6484) = except Monday and
    Saturday; not a number = unknown."""
    assert decisions.waiver_days(5461) == frozenset(range(7))
    assert decisions.waiver_days(15359) == frozenset({0, 1, 2, 3, 4, 6})
    assert decisions.waiver_days(15356) == decisions.waiver_days(6484) == frozenset({1, 2, 3, 4, 6})
    assert decisions.waiver_days(None) is None and decisions.waiver_days("x") is None and decisions.waiver_days(-1) is None
    assert decisions.waiver_days(0) == frozenset()
    assert decisions.daily_days_words(frozenset(range(7))) == "every day"
    assert decisions.daily_days_words(frozenset({0, 1, 2, 3, 4, 6})) == "every day except Saturday"
    assert decisions.daily_days_words(frozenset({1, 2, 3, 4, 6})) == "every day except Monday and Saturday"
    assert decisions.daily_days_words(frozenset({0, 2, 3})) == "on Monday, Wednesday and Thursday"
    assert decisions.daily_days_words(frozenset()) == "on no day of the week (see Sleeper)"


def test_the_dynasty_says_which_days():
    """Forever Unclean Dynasty (fixture settings): FAAB, daily at hour 2 Pacific = 5:00 AM ET, every day but Saturday."""
    d = decisions.waiver_deadline(_league(DYNASTY), now=NOW)
    assert d["words"] == "Claims run every day except Saturday at 5:00 AM ET (FAAB blind bids)."
    assert d["runs_words"] == "every day except Saturday at 5:00 AM ET" and d["runs_at"] == "2026-10-04T09:00:00+00:00"
    assert d["days"] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"] and d["days_mask"] == 15359
    # Friday night: the next run skips Saturday and is Sunday's
    fri = pd.Timestamp("2026-10-03 03:00", tz="UTC")                   # Friday 11 PM ET
    assert decisions.waiver_deadline(_league(DYNASTY), now=fri)["runs_at"] == "2026-10-04T09:00:00+00:00"
    # a weekly league: no days (the mask is Sleeper's default, unused)
    s = decisions.waiver_deadline(_league(SCRUBS), now=NOW)
    assert s["days"] is None and s["days_mask"] == 5461 and s["words"] == "Claims run Wednesday 3:00 AM ET (rolling waivers)."


def test_a_late_pacific_run_is_named_by_its_et_day():
    """10 PM Pacific on Saturday is 1:00 AM ET on Sunday: the day off is named in ET."""
    lg = {"settings": {"waiver_type": 2, "daily_waivers": 1, "daily_waivers_days": 15359, "daily_waivers_hour": 22}}
    assert decisions.waiver_deadline(lg, now=NOW)["words"] == "Claims run every day except Sunday at 1:00 AM ET (FAAB blind bids)."
    every = {"settings": {"waiver_type": 2, "daily_waivers": 1, "daily_waivers_hour": 2}}           # no mask: IG-3's words
    assert decisions.waiver_deadline(every, now=NOW)["words"] == "Claims run every day at 5:00 AM ET (FAAB blind bids)."


def test_team_says_when_mfl_was_read(client, mfl):  # noqa: F811
    """Dad's league team 8: the Team answer carries My Week's MFL freshness fields (read just now, from the fixtures)."""
    t = client.get("/api/team", params={"league": DAD, "team": 8}).json()
    assert t["roster_source"] == "MFL"
    at = datetime.fromisoformat(t["roster_updated_at"])
    assert abs((datetime.now(UTC) - at).total_seconds()) < 600
    assert decisions.team_roster_freshness(SCRUBS) == {}


@needs_db
def test_a_sleeper_team_has_no_mfl_line(client):
    t = client.get("/api/team", params={"league": SCRUBS, "team": 6}).json()
    assert "roster_updated_at" not in t and "roster_source" not in t


# ------------------------------------------------------------------ 4. "What changed": a Questionable tag
def _rows(*players) -> pd.DataFrame:
    return pd.DataFrame([{"gsis_id": g, "sleeper_player_id": s, "player_name": n, "position": p, "role": role,
                          "report_status": st} for g, s, n, p, role, st in players])


FLOWERS = ("00-0039064", "9488", "Zay Flowers", "WR", "starter", "Questionable")
EVANS = ("00-0031408", "2216", "Mike Evans", "WR", "bench", "Questionable")


def test_a_questionable_starter_shows_once(monkeypatch):
    """The overlay's flag (a copy newer than the build moved him to Questionable): one line, his last name and the note,
    "your lineup is unchanged", cited by the overlay entry; a bench player gets none; the same player twice, one line."""
    monkeypatch.setattr(AV, "now", lambda gs, *a, **k: {"00-0039064": {"note": "hamstring", "source": "ESPN",
                                                                       "as_of": "2026-10-02T20:16:00Z"}})
    meta = {"checked_at": "2026-10-04T15:00:00Z", "changes": [], "cites": [],
            "flags": ["Zay Flowers is questionable (hamstring) — he can play; check before kickoff",
                      "Mike Evans is questionable (ribs) — he can play; check before kickoff"]}
    out = myweek.what_changed(meta, _rows(FLOWERS, FLOWERS, EVANS), None)
    (line,) = out["lines"]
    assert line["text"] == "Questionable: Flowers (hamstring) — your lineup is unchanged"
    assert (line["kind"], line["flag"], line["gsis_id"]) == ("status", "questionable", "00-0039064")
    assert line["source"] == "Injury report (ESPN)" and line["at"] == "2026-10-02T20:16:00Z"
    # Evans starts in the submitted lineup: his line too
    out = myweek.what_changed(meta, _rows(FLOWERS, EVANS), {"2216": "WR"})
    assert [x["player_name"] for x in out["lines"]] == ["Zay Flowers", "Mike Evans"]
    assert out["lines"][1]["text"] == "Questionable: Evans — your lineup is unchanged"


def test_a_tag_the_build_knew_is_not_a_change(monkeypatch):
    """No flag and no event: the tag was in the morning build (Questionable since last week) — nothing changed."""
    monkeypatch.setattr(AV, "now", lambda gs, *a, **k: {})
    meta = {"checked_at": None, "changes": [], "cites": [], "flags": []}
    assert myweek.what_changed(meta, _rows(FLOWERS), None)["lines"] == []


def test_a_stored_questionable_event_is_cited(monkeypatch):
    """With the store on, a live QUESTIONABLE availability event of the last 24 hours is the line's citation (source,
    time, his ESPN page, the event id); the note comes from the stored headline when the overlay has none."""
    ev = {"id": 41, "kind": "availability", "gsis_id": "00-0039064", "status": "QUESTIONABLE", "source": "ESPN",
          "source_url": "https://www.espn.com/nfl/player/_/id/4429615", "at": "2026-10-04T14:00:00Z",
          "headline": "Zay Flowers is questionable (hamstring)", "live": True}
    monkeypatch.setattr(events, "enabled", lambda: True)
    monkeypatch.setattr(events, "recent", lambda gs, hours=24, kinds=None, **k: [ev] if "availability" in (kinds or ()) else [])
    monkeypatch.setattr(AV, "now", lambda gs, *a, **k: {})
    monkeypatch.setattr(myweek, "_with_events", lambda items, names: items)
    from league_lab_api import news
    monkeypatch.setattr(news, "recent", lambda gs, names=None, **k: [])
    meta = {"checked_at": None, "changes": [], "cites": [], "flags": []}
    (line,) = myweek.what_changed(meta, _rows(FLOWERS), None)["lines"]
    assert line["text"] == "Questionable: Flowers (hamstring) — your lineup is unchanged"
    assert (line["event_id"], line["url"], line["at"]) == (41, ev["source_url"], "2026-10-04T14:00:00Z")


def test_no_second_line_for_a_player_with_one(monkeypatch):
    """A player whose status already has a line (he can play again) gets no Questionable line on top."""
    monkeypatch.setattr(AV, "now", lambda gs, *a, **k: {})
    meta = {"checked_at": None, "changes": ["Zay Flowers can play again (Questionable, ESPN) — he starts at WR1"],
            "cites": [{"gsis_id": "00-0039064", "code": "QUESTIONABLE", "source": "ESPN", "as_of": None}],
            "flags": ["Zay Flowers is questionable (hamstring) — he can play; check before kickoff"]}
    lines = myweek.what_changed(meta, _rows(FLOWERS), None)["lines"]
    assert len(lines) == 1 and lines[0]["text"].startswith("Zay Flowers can play again")


@needs_db
def test_scrubs_roster_3_sees_flowers(client, overlay):  # noqa: F811
    """League of Scrubs roster 3 with the ESPN fixtures' overlay: Zay Flowers (a starter) is Questionable in a copy newer
    than the build — My Week's "What changed" says so once; McLaurin (bench) has no line."""
    w = client.get("/api/my-week", params={"league": SCRUBS, "team": 3}).json()
    q = [x for x in w["changed"]["lines"] if x.get("flag") == "questionable"]
    assert [x["text"] for x in q] == ["Questionable: Flowers (hamstring) — your lineup is unchanged"]
    assert q[0]["source"] == "Injury report (ESPN)"


# ------------------------------------------------------------------ 5. game_key on availability events
@pytest.fixture
def games(monkeypatch):
    monkeypatch.setattr(events, "_games", None)
    yield
    events._games = None


def test_the_game_key_is_the_teams_game_this_week(monkeypatch, games):
    calls = []

    def fresh(sql, params=()):
        calls.append(params)
        return pd.DataFrame([{"game_id": "2026_04_MIA_MIN", "home_team": "MIN", "away_team": "MIA"},
                             {"game_id": "2026_04_LA_PHI", "home_team": "PHI", "away_team": "LA"}])
    monkeypatch.setattr(events.db, "fresh", fresh)
    assert events.game_key_for("MIN") == "2026_04_MIA_MIN" and events.game_key_for("LAR") == "2026_04_LA_PHI"
    assert events.game_key_for("NYJ") is None and events.game_key_for(None) is None        # a bye; no team
    assert len(calls) == 1                                                                   # cached
    t0 = datetime(2026, 10, 2, 18, 35, tzinfo=UTC)
    ent = {"code": "QUESTIONABLE", "source": "ESPN", "as_of": t0, "fetched_at": t0, "note": "ankle",
           "name": "Justin Jefferson", "team": "MIN", "espn_id": "4262921"}
    snap = SimpleNamespace(espn={"00-0036322": ent}, sleeper={}, espn_fetched=t0, sleeper_fetched=t0,
                           espn_timestamp="2026-10-02T19:00:00Z", _players={"6794": {}})
    events.reset(availability_baseline={"00-0036322": {"code": "ACTIVE", "source": "ESPN", "team": "MIN"}})
    try:
        (r,) = events.availability_rows(snap)
        assert (r["status"], r["team"], r["game_key"]) == ("QUESTIONABLE", "MIN", "2026_04_MIA_MIN")
        before = r["fingerprint"]
        assert before == events.fingerprint("availability", "00-0036322", "QUESTIONABLE", r["source_url"], t0)  # unchanged
    finally:
        events.reset()


def test_no_schedule_no_game_key(monkeypatch, games):
    def boom(sql, params=()):
        raise RuntimeError("no database")
    monkeypatch.setattr(events.db, "fresh", boom)
    assert events.game_key_for("MIN") is None
    monkeypatch.setattr(events.db, "fresh", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked again")))
    assert events.game_key_for("MIN") is None                                                # not asked again for 5 min


@needs_db
def test_the_week_in_play_on_the_clone():
    """The clone's schedule: Saturday of week 4 → week 4's games (Minnesota hosts Miami); Tuesday after → week 5's."""
    g4 = events.week_games(datetime(2026, 10, 3, 12, tzinfo=UTC))
    assert g4.get("MIN") == "2026_04_MIA_MIN" and all(v.startswith("2026_04_") for v in g4.values())
    g5 = events.week_games(datetime(2026, 10, 6, 15, tzinfo=UTC))
    assert g5 and all(v.startswith("2026_05_") for v in g5.values()) and len(g5) < 32          # week 5 has byes
    assert events.week_games(datetime(2026, 10, 2, 3, tzinfo=UTC)).get("PIT") == "2026_04_PIT_CLE"   # Thursday night


# ------------------------------------------------------------------ the web's e2e recordings (web/e2e/ih2)
@needs_db
@pytest.mark.skipif(not __import__("os").environ.get("IH2_RECORD"), reason="records web/fixtures/ih2/api_ih2.json: IH2_RECORD=1")
def test_record_e2e_answers(client, mfl, overlay):  # noqa: F811
    """The answers web/e2e/ih2 replays: dad's league team 8's Team page (the MFL line) and Scrubs roster 6's (none), the
    dynasty's Waivers (which days
    claims run), League of Scrubs roster 3's My Week (the Questionable line), the status."""
    from urllib.parse import urlencode

    def key(path: str, **q) -> str:
        return path + ("?" + urlencode(sorted((k, str(v)) for k, v in q.items())) if q else "")

    out: dict = {}

    def rec(path: str, **q):
        r = client.get(key(path, **q))
        out[key(path, **q)] = {"status": r.status_code, "body": r.json()}

    rec("/api/leagues", mfl_search="70587")
    rec("/api/leagues/mfl%3A70587/rosters")
    rec("/api/team", league=DAD, team=8)
    rec("/api/team", league=SCRUBS, team=6)
    rec("/api/waivers", league=DYNASTY, team=12, position="ALL")
    rec("/api/my-week", league=SCRUBS, team=3)
    rec("/api/status")
    f = ROOT / "web" / "fixtures" / "ih2" / "api_ih2.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    assert all(v["status"] == 200 for v in out.values()), {k: v["status"] for k, v in out.items()}


# ------------------------------------------------------------------ found on the way: team units in the bye words
def test_units_on_a_bye_are_named_by_their_team(client, mfl):  # noqa: F811
    """Dad's league team 12: "Fills your empty team QB in week 5, when QB and QB are on a bye." — two team QBs read by
    `_last` as "QB"; now named as IC-4 names a unit ("Ravens QB")."""
    assert decisions._name_list(["Houston Texans QB", "Chicago Bears QB"]) == "Texans QB and Bears QB"
    assert decisions._name_list(["Justin Jefferson", "Houston Texans K"]) == "Jefferson and Texans K"
    assert decisions._name_list(["Kansas City Chiefs"]) == "Kansas City Chiefs"
    w = client.get("/api/waivers", params={"league": DAD, "team": 12}).json()
    words = " ".join(c.get("reason") or "" for c in [*w["top3"], *w["views"]["help"]["moves"], *w["views"]["bye"]["moves"]])
    assert "QB and QB" not in words and "when QB " not in words
    r = next(c["reason"] for c in w["top3"] if c["move"]["add"]["player_name"] == "Arizona Cardinals QB")
    assert re.match(r"^Fills your empty team QB in week 5, when \w+ QB and \w+ QB are on a bye", r), r
