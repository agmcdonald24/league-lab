"""Wave I-K, IK-1: ESPN's tables, keys and client (league_lab.espn_client) and the adapter in Sleeper's shapes
(league_lab.espn_leagues) — on synthetic settings and the synthetic fixture leagues (api/tests/fixtures/espn_leagues/:
4242 public, 5150 private; built from cwendt94/espn-api's documented shapes, never an ESPN answer). No test calls ESPN.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from league_lab import espn_client as E
from league_lab import espn_leagues as L
from league_lab import player_ids as PI
from league_lab.sleeper_client import LeagueNotFound, TokenBucket

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "api" / "tests" / "fixtures"
LEAGUES = FX / "espn_leagues"
SECRET = "s" * 32


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(E.FIXTURES_ENV, str(LEAGUES))
    monkeypatch.setenv(E.SEASON_ENV, "2026")
    monkeypatch.setenv(PI.CSV_ENV, str(FX / "ff" / "db_playerids.csv"))
    monkeypatch.delenv(E.PRIVATE_ENV, raising=False)
    monkeypatch.delenv(E.SECRET_ENV, raising=False)
    monkeypatch.delenv(E.ENABLED_ENV, raising=False)
    PI.reset()
    yield
    PI.reset()


@pytest.fixture(scope="module")
def directory() -> dict:
    return json.loads((FX / "sleeper" / "players_nfl.json").read_text())


def _adapter(directory, **kw) -> L.ESPNLeagues:
    return L.ESPNLeagues(E.ESPN(**kw), lambda: directory)


def _items(*rows) -> dict:
    """scoringSettings from (statId, points[, {slot: points}]) rows."""
    out = []
    for r in rows:
        d = {"statId": r[0], "points": r[1]}
        if len(r) > 2:
            d["pointsOverrides"] = r[2]
        out.append(d)
    return {"scoringSettings": {"scoringItems": out, "scoringType": "H2H_POINTS"}}


# ------------------------------------------------------------------ the tables
def test_slot_table_matches_espn_api_constants():
    # espn-api football/constant.py POSITION_MAP (0 QB … 23 FLEX); ours: the slot League Lab solves, or None
    assert {k: v[0] for k, v in E.SLOT_IDS.items() if k in (0, 2, 4, 6, 7, 16, 17, 20, 21, 23)} == {
        0: "QB", 2: "RB", 4: "WR", 6: "TE", 7: "OP", 16: "D/ST", 17: "K", 20: "BE", 21: "IR", 23: "FLEX"}
    assert E.slot_name(7) == "SUPER_FLEX" and E.slot_name(3) == "WRRB_FLEX" and E.slot_name(5) == "REC_FLEX"
    assert E.slot_name(16) == "DEF" and E.slot_name(20) == "BN" and E.slot_name(10) is None


def test_slots_default_league_and_superflex_idp():
    counts = {str(i): 0 for i in range(25)}
    counts.update({"0": 1, "2": 2, "4": 2, "6": 1, "16": 1, "17": 1, "20": 7, "21": 1, "23": 1})
    slots, note = E.slots({"rosterSettings": {"lineupSlotCounts": counts}})
    assert slots == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"] + ["BN"] * 7
    assert note == {"left_out": [], "idp": False, "bench": 7, "ir": 1}
    counts.update({"7": 1, "10": 2, "14": 1, "5": 1, "18": 1})
    slots, note = E.slots({"rosterSettings": {"lineupSlotCounts": counts}})
    assert [s for s in slots if s != "BN"] == ["QB", "RB", "RB", "WR", "WR", "TE", "REC_FLEX", "FLEX", "SUPER_FLEX",
                                              "K", "DEF"]
    assert note["idp"] is True and note["left_out"] == ["LB", "LB", "DB", "P"]


def test_scoring_standard_items_on_sleeper_keys():
    sc, rep = E.scoring(_items((3, 0.04), (4, 4), (20, -2), (24, 0.1), (25, 6), (42, 0.1), (43, 6), (53, 1),
                               (72, -2), (74, 5), (77, 4), (80, 3), (85, -1), (86, 1), (88, -1), (19, 2),
                               (17, 2), (37, 3), (56, 3), (15, 2), (64, -1), (211, 0.5)))
    assert sc == pytest.approx({"pass_yd": 0.04, "pass_td": 4, "pass_int": -2, "rush_yd": 0.1, "rush_td": 6,
                                "rec_yd": 0.1, "rec_td": 6, "rec": 1, "fum_lost": -2, "fgm_50p": 5, "fgm_40_49": 4,
                                "fgm_0_19": 3, "fgm_20_29": 3, "fgm_30_39": 3, "fgmiss": -1, "xpm": 1, "xpmiss": -1,
                                "pass_2pt": 2, "bonus_pass_yd_300": 2, "bonus_rush_yd_100": 3, "bonus_rec_yd_100": 3,
                                "pass_td_40p": 2, "pass_sack": -1, "pass_fd": 0.5})
    assert rep["unpriced"] == [] and rep["approximated"] == [] and rep["categories"] is False


def test_scoring_dst_overrides_bands_and_returns():
    sc, rep = E.scoring(_items((89, 0, {"16": 10}), (90, 0, {"16": 7}), (91, 0, {"16": 4}), (92, 0, {"16": 1}),
                               (121, 0, {"16": 0}), (122, 0, {"16": 0}), (123, 0, {"16": -1}), (124, 0, {"16": -4}),
                               (125, 0, {"16": -5}), (99, 0, {"16": 1}), (95, 0, {"16": 2}), (96, 0, {"16": 2}),
                               (98, 0, {"16": 2}), (97, 0, {"16": 2}), (101, 6, {"16": 6}), (102, 6, {"16": 6}),
                               (103, 0, {"16": 6}), (104, 0, {"16": 6}), (93, 6, {"16": 6}), (100, 0, {"16": 0.5})))
    # the D/ST's points are the slot-16 override; 1/2 sack -> one more point a sack
    assert sc["sack"] == pytest.approx(2.0) and sc["int"] == 2 and sc["fum_rec"] == 2 and sc["safe"] == 2
    assert sc["def_td"] == 6 and sc["def_st_td"] == 6 and sc["st_td"] == 6        # player KR / PR TDs: st_td
    # ESPN 14-17 (1) and 18-21 (0) averaged over Sleeper's 14-20 point by point: (4*1 + 3*0) / 7
    assert sc["pts_allow_0"] == 10 and sc["pts_allow_1_6"] == 7 and sc["pts_allow_14_20"] == pytest.approx(0.571, abs=1e-3)
    assert sc["pts_allow_28_34"] == -1 and sc["pts_allow_35p"] == -4
    assert "pts_allow_21_27" not in sc
    assert any("points allowed" in a for a in rep["approximated"])
    assert rep["pa_bands"][0] == [0, 0, 10.0] and rep["pa_bands"][-1] == [46, None, -5.0]


def test_scoring_te_premium_per_n_unpriced_and_categories():
    sc, rep = E.scoring({"scoringSettings": {"scoringType": "H2H_CATEGORY", "scoringItems": [
        {"statId": 53, "points": 0.5, "pointsOverrides": {"6": 1.0, "0": 0.0}},     # half PPR, TE full, QB none
        {"statId": 8, "points": 1.0},                                              # a point every 25 passing yards
        {"statId": 214, "points": 0.1},                                            # FG made yards: no Sleeper key
        {"statId": 198, "points": 5}, {"statId": 201, "points": 6},               # 50-59 and 60+
        {"statId": 155, "points": 5}]}})                                          # head coach win
    assert sc["rec"] == 0.5 and sc["bonus_rec_te"] == 0.5 and sc["pass_yd"] == pytest.approx(0.04)
    assert sc["fgm_50p"] == 5
    assert set(rep["unpriced"]) == {"FG made yards", "team win"}
    assert any("every 25 passing yards" in a for a in rep["approximated"])
    assert any("at QB" in a for a in rep["approximated"]) and any("60+" in a for a in rep["approximated"])
    assert rep["categories"] is True


def test_dst_ids_teams_and_positions():
    assert E.dst_team(-16012) == "KC" and E.dst_team(-16028) == "WAS" and E.dst_team(-16034) == "HOU"
    assert E.dst_team(3916387) is None and E.dst_team("x") is None
    assert E.player_position({"defaultPositionId": 5}) == "K"
    assert E.player_position({"defaultPositionId": 99, "eligibleSlots": [3, 4, 5, 23]}) == "WR"
    assert E.player_position({"eligibleSlots": [16, 20]}) == "DEF"


# ------------------------------------------------------------------ keys and links
@pytest.mark.parametrize("text,lid,tid,season", [
    ("4242", "4242", None, None), ("espn:4242", "4242", None, None), ("ESPN:2025:4242", "4242", None, 2025),
    ("fantasy.espn.com/football/league?leagueId=4242", "4242", None, None),
    ("https://fantasy.espn.com/football/team?leagueId=4242&teamId=3&seasonId=2026", "4242", "3", 2026),
    ("https://fantasy.espn.com/football/league/standings?seasonId=2025&leagueId=0042", "42", None, 2025),
])
def test_parse_link(text, lid, tid, season):
    assert E.parse_link(text) == (lid, tid, season)


@pytest.mark.parametrize("text", ["", "abc", "espn:", "espn:12a", "espn:2017:4242", "https://example.com/?leagueId=4242",
                                  "fantasy.espn.com/football/league", "1234567890123"])
def test_parse_link_rejects_junk(text):
    with pytest.raises(LeagueNotFound) as e:
        E.parse_link(text)
    assert e.value.code == "espn_link_invalid" and "leagueId=" in e.value.fix


def test_keys():
    assert E.check_key(" espn:04242 ") == "espn:4242" and E.check_key("espn:2025:4242") == "espn:2025:4242"
    assert E.parse_key("espn:2025:4242") == ("4242", 2025) and E.is_espn("ESPN:1") and not E.is_espn("mfl:1")
    assert E.make_key(4242) == "espn:4242" and E.make_key("4242", 2024) == "espn:2024:4242"


def test_season_now(monkeypatch):
    monkeypatch.delenv(E.SEASON_ENV)
    from league_lab import clock
    with clock.pinned("2027-02-01T12:00:00Z"):
        assert E.season_now() == 2026
    with clock.pinned("2027-03-05T12:00:00Z"):
        assert E.season_now() == 2027


# ------------------------------------------------------------------ the client
def test_client_fixture_reads_go_through_cache_and_bucket():
    c = E.ESPN()
    s = c.settings("4242")
    assert s["_synthetic"].startswith("SYNTHETIC") and s["settings"]["name"] == "Synthetic Public League"
    c.settings("4242")
    assert c.calls == 1
    st = c.stats()
    assert st["mode"] == "fixtures" and st["cache"]["settings"]["entries"] == 1 and st["private_enabled"] is False


def test_client_unknown_and_private(monkeypatch):
    c = E.ESPN()
    with pytest.raises(LeagueNotFound) as e:
        c.settings("777")
    assert e.value.code == "espn_league_unknown" and "777" in str(e.value)
    with pytest.raises(E.LeaguePrivate) as e:
        c.settings("5150")
    assert e.value.code == "espn_league_private" and str(e.value).startswith("ESPN league 5150 is private.")
    assert "Settings → Basic Settings → League Visibility" in str(e.value)
    assert "commissioner" in e.value.fix                         # the switch is off: no cookie form offered
    code, words, fix = E.setup_words(e.value, "5150")
    assert code == "espn_league_private" and words == str(e.value)
    assert E.setup_words(ValueError("x"), None)[0] == "espn_link_invalid"


def _stub(log: list, answers: dict):
    def fetch(url, headers):
        log.append((url, dict(headers)))
        for k, v in answers.items():
            if k in url:
                return v
        return 404, ""
    return fetch


def test_client_live_shape_url_filter_and_no_cookie_when_off(monkeypatch):
    log: list = []
    body = json.dumps({"id": 4242, "transactions": []})
    c = E.ESPN(fixtures="", fetch=_stub(log, {"mTransactions2": (200, body)}))
    with E.using_cookies(("x" * 60, "{11111111-2222-3333-4444-555555555555}")):     # switch off: ignored
        c.transactions("4242", 2026, 3)
    url, headers = log[0]
    assert url == ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/4242"
                   "?view=mTransactions2&scoringPeriodId=3")
    assert json.loads(headers["x-fantasy-filter"]) == E.TRANSACTION_FILTER
    assert "Cookie" not in headers and headers["User-Agent"].startswith("league-lab/")


def test_client_private_with_cookies_when_on(monkeypatch):
    monkeypatch.setenv(E.PRIVATE_ENV, "on")
    monkeypatch.setenv(E.SECRET_ENV, SECRET)
    log: list = []
    priv = json.dumps({"id": 5150, "settings": {"name": "P", "isPublic": False}})

    pair = E.clean_cookies("AEB" + "x" * 60, "11111111-2222-3333-4444-555555555555")

    def fetch(url, headers):                                       # ESPN: only the manager's own cookies open it
        log.append(headers)
        return (200, priv) if pair[0] in headers.get("Cookie", "") else (401, "")
    c = E.ESPN(fixtures="", fetch=fetch)
    with pytest.raises(E.LeaguePrivate) as e:
        c.settings("5150")
    assert "“Private league?”" in e.value.fix                      # the switch is on: the form is offered
    assert pair[1] == "{11111111-2222-3333-4444-555555555555}"
    with E.using_cookies(pair):
        assert c.settings("5150")["settings"]["name"] == "P"
        c.require_access("5150")                                   # the reader passes
    assert log[-1]["Cookie"] == f"espn_s2={pair[0]}; SWID={pair[1]}"
    with pytest.raises(E.LeaguePrivate):                           # no cookies: the cached answer is not served
        c.require_access("5150")
    with pytest.raises(E.LeaguePrivate):
        c.settings("5150")
    other = E.clean_cookies("ZZZ" + "y" * 60, "{99999999-2222-3333-4444-555555555555}")
    with E.using_cookies(other), pytest.raises(E.LeaguePrivate) as e:
        c.require_access("5150")                                   # someone else's cookies: ESPN says no
    assert e.value.with_cookies is True
    # the cache never holds the cookies themselves
    assert pair[0] not in json.dumps(list(c._cache)) and pair[0] not in repr(c.access)


def test_client_wrong_cookies_say_so(monkeypatch):
    monkeypatch.setenv(E.PRIVATE_ENV, "on")
    monkeypatch.setenv(E.SECRET_ENV, SECRET)
    c = E.ESPN(fixtures="", fetch=lambda url, headers: (401, ""))
    with E.using_cookies(E.clean_cookies("A" * 64, "{11111111-2222-3333-4444-555555555555}")), \
            pytest.raises(E.LeaguePrivate) as e:
        c.settings("5150")
    assert "cookies you gave" in str(e.value) and e.value.code == "espn_league_private"


def test_clean_cookies_rejects_junk():
    assert E.clean_cookies("short", "{11111111-2222-3333-4444-555555555555}") is None
    assert E.clean_cookies("A" * 64, "not-a-swid") is None
    assert E.clean_cookies("A" * 64 + "<script>", "{11111111-2222-3333-4444-555555555555}") is None
    assert E.private_enabled() is False


def test_switch_needs_the_secret(monkeypatch):
    monkeypatch.setenv(E.PRIVATE_ENV, "on")
    assert E.private_enabled() is False                            # no LEAGUE_LAB_API_SECRET: off
    monkeypatch.setenv(E.SECRET_ENV, SECRET)
    assert E.private_enabled() is True
    monkeypatch.setenv(E.PRIVATE_ENV, "off")
    assert E.private_enabled() is False


def test_client_budget_backoff_and_stale_on_error():
    t = [0.0]
    answers = {"n": 0}

    def fetch(url, headers):
        answers["n"] += 1
        if answers["n"] == 2:
            return 429, ""
        if answers["n"] == 3:
            return 503, ""
        return 200, json.dumps({"id": 4242, "status": {}, "scoringPeriodId": 4})
    c = E.ESPN(fixtures="", fetch=fetch, clock=lambda: t[0], bucket=TokenBucket(1, clock=lambda: t[0]))
    assert c.status("4242")["scoringPeriodId"] == 4
    t[0] += E.TTL_S["status"] + 1
    assert c.status("4242")["scoringPeriodId"] == 4 and c.stale_served == 1       # 429: the old answer, back off
    t[0] += 61
    assert c.status("4242")["scoringPeriodId"] == 4 and c.stale_served == 2       # ESPN 503: stale on error
    with pytest.raises(E.ESPNBusy):
        c.settings("4242")                                                        # bucket empty, nothing cached
    c2 = E.ESPN(fixtures="", fetch=lambda u, h: (500, ""))
    with pytest.raises(E.ESPNUnavailable):
        c2.settings("4242")


# ------------------------------------------------------------------ the adapter on the fixture league
def test_league_in_sleeper_shape(directory):
    x = _adapter(directory)
    lg = x.league("espn:4242")
    assert lg["league_id"] == "espn:4242" and lg["platform"] == "espn" and lg["season"] == "2026"
    assert lg["name"] == "Synthetic Public League" and lg["total_rosters"] == 10
    assert lg["roster_positions"] == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"] + ["BN"] * 7
    s = lg["settings"]
    assert (s["leg"], s["last_scored_leg"], s["playoff_week_start"], s["playoff_teams"], s["reserve_slots"]) == (4, 3, 15, 4, 1)
    assert s["waiver_type"] == 2 and s["waiver_budget"] == 100
    sc = lg["scoring_settings"]
    assert sc["rec"] == 0.5 and sc["bonus_rec_te"] == 0.5 and sc["pass_td"] == 4 and sc["pass_yd"] == 0.04
    assert lg["espn"]["unofficial"] is True and lg["espn"]["public"] is True
    assert lg["espn"]["url"] == "https://fantasy.espn.com/football/league?leagueId=4242&seasonId=2026"
    assert x.week("espn:4242") == 4 and x.week("4242") == 4 and x.league_name("espn:4242") == "Synthetic Public League"


def test_users_and_rosters(directory):
    x = _adapter(directory)
    users = x.users("espn:4242")
    assert [u["user_id"] for u in users] == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "11"]
    assert users[2]["metadata"]["team_name"] == "Mighty Ducks"                     # location + nickname
    assert users[0]["display_name"] == "espn_manager_01"
    rosters = x.rosters("espn:4242")
    assert [r["roster_id"] for r in rosters] == list(range(1, 11))
    assert rosters[-1]["owner_id"] == "11" and rosters[-1]["espn_team_id"] == 11
    assert x.roster_id_of("espn:4242", 11) == 10 and x.team_id_of("espn:4242", 10) == 11
    assert x.roster_id_of("espn:4242", 10) is None
    for r in rosters:
        assert len(r["starters"]) == 9                                             # one per starting slot
        assert r["starters"][-1] in directory and directory[r["starters"][-1]]["position"] == "DEF"
        assert set(x for x in r["starters"] if x != "0") <= set(r["players"])
        assert r["settings"]["wins"] + r["settings"]["losses"] == 3
    # team 2's FLEX is a player the id table cannot map: kept, as espn:<id>, in the FLEX place
    assert rosters[1]["starters"][6] == "espn:99990002"
    assert x.extra_players["espn:99990002"]["full_name"] == "Practice Squad Callup"
    assert {u["espn_id"] for u in x.unmapped("espn:4242")} == {"99990001", "99990002"}
    by = x.mapped_by("espn:4242")
    assert by["defense"] == 11 and by["name"] == 1 and by["unmapped"] == 2
    assert by["table"] / sum(by.values()) > 0.9


def test_matchups_and_season(directory):
    x = _adapter(directory)
    w1 = x.matchups("espn:4242", 1)
    assert len(w1) == 10 and all(r["points"] > 0 for r in w1)
    pairs = {}
    for r in w1:
        pairs.setdefault(r["matchup_id"], []).append(r["roster_id"])
    assert sorted(len(v) for v in pairs.values()) == [2] * 5
    assert sorted(pairs.values())[0] == [1, 10]                                    # ESPN team 1 v team 11
    w4 = x.matchups("espn:4242", 4)
    assert any(r["points"] > 0 for r in w4) and any(r["points"] == 0 for r in w4)    # the Thursday game only
    assert all(r["points"] == 0 for r in x.matchups("espn:4242", 9))
    season = x.season_matchups("espn:4242", 3)
    assert sorted(season) == [1, 2, 3]
    ros = {r["roster_id"]: r for r in x.rosters("espn:4242")}
    for rid in ros:
        pf = sum(r["points"] for w in season.values() for r in w if r["roster_id"] == rid)
        st = ros[rid]["settings"]
        assert pf == pytest.approx(st["fpts"] + st["fpts_decimal"] / 100, abs=0.011)


def test_transactions(directory):
    x = _adapter(directory)
    t1 = x.transactions("espn:4242", 1)
    assert len(t1) == 1 and t1[0]["type"] == "waiver" and t1[0]["settings"] == {"waiver_bid": 3}
    assert t1[0]["adds"] == {"NE": 1} and list(t1[0]["drops"].values()) == [1]
    t2 = x.transactions("espn:4242", 2)
    assert len(t2) == 2                                                            # the cancelled claim is left out
    t3 = x.transactions("espn:4242", 3)
    assert [t["type"] for t in t3] == ["trade"]                                    # the lineup move is left out
    tr = t3[0]
    assert tr["roster_ids"] == [3, 5] and set(tr["adds"]) == set(tr["drops"])
    ros = {r["roster_id"]: set(r["players"]) for r in x.rosters("espn:4242")}
    for sid, rid in tr["adds"].items():
        assert sid in ros[rid]                                                     # the traded player is on his new team
    t4 = x.transactions("espn:4242", 4)
    assert t4[0]["type"] == "free_agent" and t4[0]["leg"] == 4 and t4[0]["created"] > t1[0]["created"]
    fresh = _adapter(directory)
    fresh.transactions("espn:4242", 1)
    assert fresh.mapped_by("espn:4242") == {}                                     # transactions are not the roster count


def test_free_agents_espn_list(directory):
    x = _adapter(directory)
    fa = x.free_agents("espn:4242")
    assert len(fa) == 31 and fa[-1] == "espn:99990004"
    taken = {p for r in x.rosters("espn:4242") for p in r["players"]}
    assert not taken & set(fa)
    assert "espn:99990004" not in {f"espn:{u['espn_id']}" for u in x.unmapped("espn:4242")}


def test_season_key_and_private_league(directory, monkeypatch):
    x = _adapter(directory)
    assert x.ids("espn:2025:4242") == ("4242", 2025)
    assert x.league("espn:2025:4242")["league_id"] == "espn:2025:4242"           # fixtures: one file per league
    with pytest.raises(E.LeaguePrivate):
        x.league("espn:5150")
    monkeypatch.setenv(E.PRIVATE_ENV, "on")
    monkeypatch.setenv(E.SECRET_ENV, SECRET)
    pair = E.clean_cookies("A" * 64, "{11111111-2222-3333-4444-555555555555}")
    with E.using_cookies(pair):
        lg = x.league("espn:5150")
        x.require_access("espn:5150")
        assert lg["name"] == "Synthetic Private League" and lg["espn"]["public"] is False
        assert len(x.rosters("espn:5150")) == 10
    with pytest.raises(E.LeaguePrivate):
        x.require_access("espn:5150")
    x.require_access("espn:4242")                                                  # public: always fine


def test_fixture_files_say_synthetic():
    for f in LEAGUES.rglob("*.json"):
        assert json.loads(f.read_text())["_synthetic"].startswith("SYNTHETIC"), f


def test_kill_switch(monkeypatch):
    monkeypatch.setenv(E.ENABLED_ENV, "off")
    with pytest.raises(LeagueNotFound) as e:
        E.ESPN().settings("4242")
    assert e.value.code == "espn_not_configured" and E.setup_words(e.value)[0] == "espn_not_configured"
    monkeypatch.setenv(E.ENABLED_ENV, "on")
    assert E.ESPN().settings("4242")["id"] == 4242


def test_answers_are_trimmed_before_the_cache():
    """A roster entry's season of stat lines, rankings and ownership never reach the cache (the server has 512 MB)."""
    big = {"id": 4242, "seasonId": 2026, "teams": [{"id": 1, "roster": {"entries": [{
        "playerId": 13934, "lineupSlotId": 4, "acquisitionType": "DRAFT", "injuryStatus": "NORMAL",
        "playerPoolEntry": {"id": 13934, "appliedStatTotal": 9.9, "ratings": {"0": {}}, "player": {
            "id": 13934, "fullName": "Antonio Brown", "defaultPositionId": 3, "eligibleSlots": [3, 4, 5], "proTeamId": 23,
            "stats": [{"stats": {str(i): i for i in range(200)}}] * 20, "rankings": {"0": [1] * 50},
            "ownership": {"percentOwned": 99.1}, "draftRanksByRankType": {"PPR": {"rank": 5}}}}}]}}]}
    c = E.ESPN(fixtures="", fetch=lambda u, h: (200, json.dumps(big)))
    got = c.rosters("4242")
    p = got["teams"][0]["roster"]["entries"][0]["playerPoolEntry"]["player"]
    assert p == {"id": 13934, "fullName": "Antonio Brown", "defaultPositionId": 3, "eligibleSlots": [3, 4, 5],
                 "proTeamId": 23}
    assert len(json.dumps(got)) < 400 < len(json.dumps(big))
