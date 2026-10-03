"""Wave I-0, I0-B: MyFantasyLeague, read-only, on demand (league_lab.mfl_client / platforms / player_ids).

Fixtures (`fixtures/mfl/`): the public league 21861 ("Addicts 1 Redraft $300 No Trade": 12 teams, QB / RB 2-4 /
WR 2-4 / TE 1-3 / PK / Def, TE-premium full PPR) fetched 2026-10-03 through the browser pane (league, rules,
rosters, schedule weeks 1-8, standings, live scoring week 4, weekly results week 3; players and injuries from the
`api.` host), trimmed to the fields the code reads; the IDP league 10015 ("Dynasty Pioneer": league + the offense /
LB / CB / S rule group) for the unpriced path; `99999999/league.json` is MFL's own error body for a league it will
not share. `fixtures/ff/db_playerids.csv` is the id table trimmed to the fixtures' players.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import platforms as P
from league_lab import player_ids as PI
from league_lab.sleeper_client import TokenBucket

from .conftest import needs_db

FX = Path(__file__).with_name("fixtures")
MFL_FX = FX / "mfl"
IDS = FX / "ff" / "db_playerids.csv"
KEY = "mfl:21861"


@pytest.fixture(autouse=True)
def _mfl_fixtures(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


def _fx(path: str) -> dict:
    return json.loads((MFL_FX / path).read_text())


# ------------------------------------------------------------------ translation
def test_slots_21861_ranges_become_flex():
    slots, note = M.slots(_fx("21861/league.json")["league"])
    starters = [s for s in slots if s != "BN"]
    assert starters == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF"]
    assert slots.count("BN") == 8                       # rosterSize 18 - 10 starters
    assert note["ranges"] == {"RB": "2-4", "WR": "2-4", "TE": "1-3"} and note["idp"] == []


def test_slots_superflex_and_idp():
    lg = {"starters": {"count": "10", "position": [{"name": "QB", "limit": "1-2"}, {"name": "RB", "limit": "2"},
                                                     {"name": "WR", "limit": "3"}, {"name": "TE", "limit": "1"},
                                                     {"name": "PK", "limit": "1"}, {"name": "Def", "limit": "1"}]},
          "rosterSize": "20"}
    slots, note = M.slots(lg)
    assert [s for s in slots if s != "BN"] == ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "SUPER_FLEX", "K", "DEF"]
    assert note["super_flex"] == 1
    idp_slots, idp_note = M.slots(_fx("10015/league.json")["league"])
    assert [s for s in idp_slots if s != "BN"] == ["QB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K"]
    assert idp_note["idp"] == ["DT", "DE", "LB", "CB", "S"]


def test_scoring_21861_expected_numbers():
    sc, rep = M.scoring(_fx("21861/rules.json")["rules"])
    expect = {"pass_yd": 0.05, "pass_td": 4, "pass_int": -1, "rec": 1, "bonus_rec_te": 0.5, "rush_yd": 0.1,
              "rush_td": 6, "rec_yd": 0.1, "rec_td": 6, "xpm": 1, "fum_rec_td": 6,
              # FG: 3 to 29 yards, then 3 + 0.1 a yard over 30 at each Sleeper band's middle
              "fgm_0_19": 3, "fgm_20_29": 3, "fgm_30_39": 3.45, "fgm_40_49": 4.45, "fgm_50p": 5.5,
              # points allowed: MFL 0 / 1-6 / 7-10 / 11+ -> Sleeper's bands, averaged over each band's points
              "pts_allow_0": 12, "pts_allow_1_6": 8, "pts_allow_7_13": 2.857, "pts_allow_14_20": 0, "pts_allow_35p": 0,
              "ff": 2, "int": 2, "sack": 1, "safe": 5, "def_td": 6}
    for k, v in expect.items():
        assert sc.get(k) == pytest.approx(v, abs=1e-3), k
    assert any("field goals" in a for a in rep["approximated"]) and any("points allowed" in a for a in rep["approximated"])
    assert rep["unpriced"] == ["touchdowns (returns)"]         # the offense group's #T
    label = A.scoring_label({"settings": {"num_teams": 12}, "roster_positions": [], "scoring_settings": sc})
    assert label == "12-team redraft · full PPR · 4‑pt pass TD · TE premium 0.5"


def test_scoring_idp_league_reports_unpriced():
    sc, rep = M.scoring(_fx("10015/rules.json")["rules"])
    assert sc["pass_td"] == 4 and sc["pass_td_40p"] == 2 and sc["bonus_pass_yd_300"] == 2 and sc["bonus_pass_yd_400"] == 4
    assert sc["rec"] == 1 and "bonus_rec_te" not in sc
    for name in ("tackles", "sacks (player)", "passes defended", "punt return TD"):
        assert name in rep["unpriced"]
    assert any("30 yards" in a for a in rep["approximated"])    # rushing TD by length: MFL's band starts at 30


@pytest.mark.parametrize("text,lid,fid", [
    ("21861", "21861", None),
    ("https://www45.myfantasyleague.com/2026/home/21861#0", "21861", None),
    ("www45.myfantasyleague.com/2026/options?L=21861&F=0004&O=07", "21861", "0004"),
    ("https://api.myfantasyleague.com/2026/export?TYPE=league&L=21861&JSON=1", "21861", None),
])
def test_parse_link(text, lid, fid):
    got = M.parse_link(text)
    assert got[0] == lid and got[1] == fid


def test_parse_link_rejects_junk():
    with pytest.raises(A.LeagueNotFound):
        M.parse_link("https://sleeper.com/leagues/123")


# ------------------------------------------------------------------ the Sleeper shapes
def test_router_answers_in_sleeper_shapes():
    sl = A.sleeper()
    assert A.check_id("MFL:21861") == KEY and A.check_id("1389709692405551104") == "1389709692405551104"
    lg = sl.league(KEY)
    assert lg["league_id"] == KEY and lg["platform"] == "mfl" and lg["total_rosters"] == 12
    assert lg["settings"]["leg"] == 4 and lg["settings"]["playoff_week_start"] == 15
    users, rosters = sl.users(KEY), sl.rosters(KEY)
    names = A.team_names(rosters, users)
    assert names[4]["team_name"] == "Matt and Doug's Team"           # MFL's &apos; unescaped
    assert A.records(rosters)[7] == {"wins": 3, "losses": 0, "standing": 1}
    r4 = next(r for r in rosters if r["roster_id"] == 4)
    assert len(r4["players"]) == 18 and len(r4["starters"]) == 10 and "SEA" in r4["starters"]   # a defense: its team code
    assert set(r4["starters"]) <= set(r4["players"])
    ms = sl.matchups(KEY, 4)
    mine = next(m for m in ms if m["roster_id"] == 4)
    assert next(m for m in ms if m["matchup_id"] == mine["matchup_id"] and m["roster_id"] != 4)["roster_id"] == 2
    assert sl.season_matchups(KEY, 3)[1][0]["points"] == pytest.approx(123.15)
    assert sl.transactions(KEY, 1) == []


def test_at_least_95_percent_of_rostered_players_map_to_sleeper():
    sl = A.sleeper()
    rosters = sl.rosters(KEY)
    ids = [p for r in rosters for p in r["players"]]
    mapped = [p for p in ids if not P.is_mfl(p)]
    by = sl.mfl.mapped_by(KEY)
    print(f"\nMFL 21861: {len(mapped)} of {len(ids)} rostered players mapped to Sleeper ids ({by}); "
          f"unmapped {sl.mfl.unmapped(KEY)}")
    assert len(ids) == 216 and len(mapped) / len(ids) >= 0.95
    directory = sl.players()
    assert all(p in directory for p in ids)                     # names / positions for every one of them


def test_unmapped_starter_is_kept_and_reported(monkeypatch, tmp_path):
    """A player the id table does not know stays on the roster as mfl:<id> (with his MFL name), and is reported."""
    rows = IDS.read_text().splitlines()
    kept = [rows[0]] + [r for r in rows[1:] if not r.startswith("14836,")]       # forget Justin Jefferson's row
    (tmp_path / "ids.csv").write_text("\n".join(kept) + "\n")
    monkeypatch.setenv(PI.CSV_ENV, str(tmp_path / "ids.csv"))
    PI.reset()
    A._default = None
    sl = A.sleeper()
    rosters = sl.rosters(KEY)
    r9 = next(r for r in rosters if r["roster_id"] == 9)
    # the name fallback finds him in Sleeper's directory (unique name + position): mapped, and said so
    assert sl.mfl.mapped_by(KEY).get("name") == 1 and "mfl:14836" not in r9["players"]
    assert "mfl:14836" not in sl.players()


def test_unmapped_starter_stays_in_the_lineup_rows(monkeypatch, tmp_path):
    """No table row and no unique name match: the starter stays on the roster and in the starters as mfl:<id>, with his
    MFL name in the directory, and is listed as unmapped — never silently dropped."""
    rows = IDS.read_text().splitlines()
    (tmp_path / "ids.csv").write_text("\n".join([rows[0]] + [r for r in rows[1:] if not r.startswith("14836,")]) + "\n")
    monkeypatch.setenv(PI.CSV_ENV, str(tmp_path / "ids.csv"))
    monkeypatch.setattr(P, "_norm", lambda name: "no-match:" + (name or ""))
    PI.reset()
    A._default = None
    sl = A.sleeper()
    r9 = next(r for r in sl.rosters(KEY) if r["roster_id"] == 9)
    assert "mfl:14836" in r9["players"] and "mfl:14836" in r9["starters"]
    assert sl.mfl.unmapped(KEY) == [{"mfl_id": "14836", "name": "Justin Jefferson", "position": "WR"}]
    assert sl.players()["mfl:14836"]["full_name"] == "Justin Jefferson"


def test_private_league_is_not_found_with_the_sentence():
    with pytest.raises(A.LeagueNotFound) as exc:
        A.sleeper().league("mfl:99999999")
    assert "Ask the commissioner to allow API access" in str(exc.value)


# ------------------------------------------------------------------ the client: hosts, budget, refusals
def _fake(routes: dict):
    calls = []

    def fetch(url: str):
        calls.append(url)
        for frag, (final, body) in routes.items():
            if frag in url:
                return final.format(url=url), json.dumps(body)
        raise M.MFLUnavailable("down")
    return fetch, calls


def test_client_follows_redirect_and_remembers_the_host():
    league = _fx("21861/league.json")
    fetch, calls = _fake({"TYPE=league": ("https://www45.myfantasyleague.com/2026/export?TYPE=league&L=21861&JSON=1", league),
                          "TYPE=rosters": ("https://www45.myfantasyleague.com/x", _fx("21861/rosters.json"))})
    c = M.MFL(fixtures=None, year=2026, fetch=fetch)
    c.fixtures = None
    c.league("21861")
    assert calls[0].startswith("https://api.myfantasyleague.com/2026/export?TYPE=league&L=21861")
    assert c.hosts["21861"] == "https://www45.myfantasyleague.com"
    c.rosters("21861")
    assert calls[1].startswith("https://www45.myfantasyleague.com/2026/export?TYPE=rosters&L=21861")
    c.league("21861")
    assert len(calls) == 2                                          # cached a day


def test_client_budget_error_body_and_stale_on_error():
    t = [0.0]
    fetch, calls = _fake({"TYPE=league&L=21861": ("{url}", _fx("21861/league.json")),
                          "TYPE=league&L=5": ("{url}", {"error": {"$t": "API requires logged in user"}})})
    c = M.MFL(fixtures=None, year=2026, fetch=fetch, clock=lambda: t[0], bucket=TokenBucket(60, capacity=2, clock=lambda: t[0]))
    c.fixtures = None
    with pytest.raises(A.LeagueNotFound):
        c.league("5")
    c.league("21861")
    with pytest.raises(M.MFLBusy):                                 # the bucket (2) is spent
        c.rules("21861")
    assert isinstance(M.MFLBusy("x"), A.SleeperBusy)              # the API answers 503 "busy, try again in a minute"
    t[0] += 24 * 3600 + 60                                          # a day later: league expired, MFL down
    c._fetch = lambda url: (_ for _ in ()).throw(M.MFLUnavailable("down"))
    assert c.league("21861")["id"] == "21861" and c.stale_served == 1


# ------------------------------------------------------------------ the id table
def test_player_ids_lookups_and_daily_download(monkeypatch, tmp_path):
    t = PI.read(IDS)
    assert t.mfl_to_sleeper("14836") == "6794" and t.mfl_to_gsis("14836") == "00-0036322"
    assert t.sleeper_to_gsis("6794") == "00-0036322" and t.espn_to_gsis("4262921") == "00-0036322"
    monkeypatch.delenv(PI.CSV_ENV)
    monkeypatch.setenv("LEAGUE_LAB_CACHE_DIR", str(tmp_path))
    body = IDS.read_bytes()
    got = []
    assert PI.download_if_stale(fetch=lambda u, _t: got.append(u) or body) == tmp_path / PI.FILE
    assert got == [PI.CSV_URL]
    PI.download_if_stale(fetch=lambda u, _t: got.append(u) or body)            # a fresh copy: no second download
    assert len(got) == 1
    later = (tmp_path / PI.FILE).stat().st_mtime + PI.MAX_AGE_S + 1
    down = PI.download_if_stale(fetch=lambda u, _t: (_ for _ in ()).throw(OSError("down")), wall=lambda: later)
    assert down == tmp_path / PI.FILE                                            # a failed download keeps the last copy


# ------------------------------------------------------------------ the routes
def test_leagues_mfl_card_and_private_404(client):
    r = client.get("/api/leagues", params={"mfl": "https://www45.myfantasyleague.com/2026/options?L=21861&F=0004"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["platform"] == "mfl" and d["league"]["league_id"] == KEY and d["roster_id"] == 4
    assert len(d["teams"]) == 12 and d["unmapped"] == [] and d["mapped"] == d["players"] == 216
    assert "FLEX" in d["scoring_note"] and "not projected" in d["scoring_note"]   # I-C: the spec's words
    bad = client.get("/api/leagues", params={"mfl": "99999999"})
    assert bad.status_code == 404 and "Ask the commissioner to allow API access" in bad.json()["error"]
    assert client.get("/api/my-week?league=mfl:99999999&team=1").status_code == 404
    assert client.get("/api/leagues/mfl:21861/rosters").status_code == 200
    assert client.get("/api/leagues/mfl:abc/rosters").status_code == 404


@needs_db
def test_every_route_answers_for_an_mfl_league(client):
    mw = client.get(f"/api/my-week?league={KEY}&team=4")
    assert mw.status_code == 200, mw.text
    d = mw.json()
    assert d["platform"] == "mfl" and d["league_name"] == "Addicts 1 Redraft $300 No Trade"
    assert [x["slot"] for x in d["lineup"]][:3] == ["QB", "RB1", "RB2"] and len(d["lineup"]) == 10
    assert d["opponent"]["roster_id"] == 2 and d["on_demand"]["mfl_unmapped"] == []
    gsis = [x["gsis_id"] for x in d["lineup"] if x.get("gsis_id")]
    routes = [f"/api/team?league={KEY}&team=4", f"/api/waivers?league={KEY}&team=4",
              f"/api/trades/partners?league={KEY}&team=4", f"/api/ros?league={KEY}", f"/api/league?league={KEY}&team=4",
              f"/api/search?league={KEY}&q=jeff", f"/api/about?league={KEY}", f"/api/trends?league={KEY}",
              f"/api/matchups/defense?league={KEY}", f"/api/matchups/cb?league={KEY}&team=4",
              f"/api/players?league={KEY}", f"/api/receivers?league={KEY}", f"/api/record?league={KEY}",
              f"/api/player/{gsis[0]}?league={KEY}&team=4", f"/api/compare?league={KEY}&a={gsis[0]}&b={gsis[1]}",
              f"/api/player/{gsis[0]}/games?league={KEY}", "/api/status"]
    for path in routes:
        r = client.get(path)
        assert r.status_code == 200, (path, r.text[:300])
    assert client.get(f"/api/record?league={KEY}").json()["available"] is False
    ros = client.get(f"/api/ros?league={KEY}").json()
    assert ros["players"] and any(p["rostered_by_roster_id"] for p in ros["players"])
    partner = client.get(f"/api/leagues/{KEY}/rosters").json()
    other = next(t["roster_id"] for t in partner if t["roster_id"] not in (4,))
    theirs = client.get(f"/api/my-week?league={KEY}&team={other}").json()
    get = [x["gsis_id"] for x in theirs["lineup"] if x.get("gsis_id")][:1]
    ev = client.post("/api/trades/evaluate", json={"league": KEY, "team": 4, "partner": other, "give": gsis[:1], "get": get})
    assert ev.status_code == 200, ev.text[:300]
