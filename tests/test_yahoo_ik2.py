"""Wave I-K, IK-2: the Yahoo client's pure parts and its read path (league_lab.yahoo_client / yahoo_leagues /
player_ids' yahoo_id). No network: reads go through an injected ``fetch`` or the synthetic fixtures in
``api/tests/fixtures/yahoo/`` (built from Yahoo's documented shapes — see that directory's builder)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from league_lab import player_ids as PI
from league_lab import yahoo_client as Y
from league_lab import yahoo_leagues as YL
from league_lab.sleeper_client import LeagueNotFound, TokenBucket

ROOT = Path(__file__).resolve().parents[1]
YFX = ROOT / "api" / "tests" / "fixtures" / "yahoo"
IDS = ROOT / "api" / "tests" / "fixtures" / "ff" / "db_playerids.csv"


def _fx(name: str) -> dict:
    return json.loads((YFX / name).read_text())


@pytest.fixture
def session():
    s = Y.YahooSession(refresh_token="RT", access_token="AT", expires_at=4e9)
    token = Y.request_session.set(s)
    yield s
    Y.request_session.reset(token)


# ------------------------------------------------------------------ the normaliser
def test_normalise_collections_become_lists():
    assert Y.normalise({"0": {"team": [{"team_id": "1"}]}, "1": {"team": [{"team_id": "2"}]}, "count": 2}) == \
        [{"team": {"team_id": "1"}}, {"team": {"team_id": "2"}}]
    assert Y.normalise({"count": 0}) == []
    assert Y.normalise({"0": {"x": 1}, "count": 1}) == [{"x": 1}]


def test_normalise_merges_a_resource_and_splices_its_metadata_list():
    team = [[{"team_key": "461.l.1.t.3"}, {"team_id": "3"}, [], {"name": "T3"}, [], {"managers": [{"manager": {"guid": "G"}}]}],
            {"team_points": {"total": "10.5"}}]
    assert Y.normalise(team) == {"team_key": "461.l.1.t.3", "team_id": "3", "name": "T3",
                                 "managers": {"manager": {"guid": "G"}}, "team_points": {"total": "10.5"}}


def test_normalise_keeps_repeated_elements_as_a_list_and_a_real_count_field():
    assert Y.normalise([{"position": "QB"}, {"position": "Q/W/R/T"}]) == [{"position": "QB"}, {"position": "Q/W/R/T"}]
    assert Y.normalise({"position": "QB", "count": 1}) == {"position": "QB", "count": 1}


def test_normalise_merges_indexed_values_into_a_dict_with_other_keys():
    roster = {"coverage_type": "week", "week": "4", "0": {"players": {"0": {"player": [[{"player_id": "1"}]]}, "count": 1}}}
    assert Y.normalise(roster) == {"coverage_type": "week", "week": "4", "players": [{"player": {"player_id": "1"}}]}


def test_items_reads_one_or_many():
    assert Y.items([{"bonus": {"a": 1}}, {"bonus": {"a": 2}}], "bonus") == [{"a": 1}, {"a": 2}]
    assert Y.items({"bonus": {"a": 1}}, "bonus") == [{"a": 1}]
    assert Y.items(None, "bonus") == [] and Y.items("x", "bonus") == []


def test_normalise_the_fixture_shapes():
    st = Y.normalise(_fx("league_461.l.4242_settings.json")["fantasy_content"])["league"]
    assert st["league_key"] == "461.l.4242" and st["current_week"] == 4
    assert len(Y.items(st["settings"]["roster_positions"], "roster_position")) == 10
    tx = Y.items(Y.normalise(_fx("league_461.l.4242_transactions.json")["fantasy_content"])["league"]["transactions"],
                 "transaction")
    add = Y.items(tx[0]["players"], "player")[0]["transaction_data"]          # a list of one in Yahoo's JSON
    drop = Y.items(tx[1]["players"], "player")[0]["transaction_data"]         # an object in Yahoo's JSON
    assert add["type"] == "add" and drop["type"] == "drop"


# ------------------------------------------------------------------ keys and links
@pytest.mark.parametrize(("text", "want"), [
    ("https://football.fantasysports.yahoo.com/f1/4242", ("nfl.l.4242", None)),
    ("football.fantasysports.yahoo.com/f1/4242/3", ("nfl.l.4242", 3)),
    ("https://football.fantasysports.yahoo.com/2026/f1/4242/3/team?week=4", ("nfl.l.4242", 3)),
    ("461.l.4242", ("461.l.4242", None)), ("yahoo:461.l.4242", ("461.l.4242", None)),
    ("YAHOO:461.L.4242", ("461.l.4242", None)), ("461.l.4242.t.7", ("461.l.4242", 7))])
def test_parse_link(text, want):
    assert Y.parse_link(text) == want


@pytest.mark.parametrize("bad", ["", "4242", "espn:4242", "461.l.", "https://sleeper.com/leagues/1", "461.p.30121"])
def test_parse_link_refuses(bad):
    with pytest.raises(Y.YahooLinkInvalid) as e:
        Y.parse_link(bad)
    assert e.value.code == "yahoo_link_invalid"


def test_check_key_and_league_key():
    assert YL.check_key(" Yahoo:461.l.4242 ") == "yahoo:461.l.4242"
    assert YL.league_key("yahoo:461.l.4242") == "461.l.4242"
    assert YL.is_yahoo("yahoo:1.l.2") and not YL.is_yahoo("mfl:21861") and not YL.is_yahoo("1389709692405551104")
    with pytest.raises(LeagueNotFound):
        YL.check_key("mfl:21861")
    assert Y.fixture_name("league/461.l.4242/scoreboard;week=3") == "league_461.l.4242_scoreboard_week_3.json"
    assert Y.team_id_of("461.l.4242.t.12") == 12 and Y.player_id_of("461.p.30121") == "30121"


# ------------------------------------------------------------------ scoring and slots
def _settings(mods: list[dict], cats: list[dict] | None = None, positions: list[tuple[str, int]] | None = None) -> dict:
    return {"stat_modifiers": {"stats": [{"stat": m} for m in mods]},
            "stat_categories": {"stats": [{"stat": c} for c in (cats or [])]},
            "roster_positions": [{"roster_position": {"position": p, "count": n}} for p, n in (positions or [])]}


def test_scoring_maps_yahoo_stat_ids_onto_sleeper_keys():
    sc, rep = Y.scoring(_settings([{"stat_id": "4", "value": "0.04"}, {"stat_id": "11", "value": "1"},
                                   {"stat_id": "16", "value": "2"}, {"stat_id": "18", "value": "-2"},
                                   {"stat_id": "50", "value": "10"}, {"stat_id": "56", "value": "-4"},
                                   {"stat_id": "78", "value": "0.1"}]))
    assert sc == {"pass_yd": 0.04, "rec": 1.0, "pass_2pt": 2.0, "rush_2pt": 2.0, "rec_2pt": 2.0, "fum_lost": -2.0,
                  "pts_allow_0": 10.0, "pts_allow_35p": -4.0, "rec_tgt": 0.1}
    assert rep["unpriced"] == [] and rep["approximated"] == []


def test_scoring_bonuses_add_up_into_sleeper_bands():
    sc, rep = Y.scoring(_settings([{"stat_id": 9, "value": "0.1", "bonuses": [
        {"bonus": {"target": "100", "points": "3"}}, {"bonus": {"target": "200", "points": "3"}}]}]))
    assert sc["bonus_rush_yd_100"] == 3.0 and sc["bonus_rush_yd_200"] == 6.0
    assert rep["approximated"] and "cumulative" in rep["approximated"][0]
    sc, rep = Y.scoring(_settings([{"stat_id": 12, "value": "0.1", "bonuses": {"bonus": {"target": "150", "points": "2"}}}],
                                  [{"stat_id": 12, "name": "Receiving Yards"}]))
    assert "bonus_rec_yd_100" not in sc and rep["unpriced"] == ["Receiving Yards bonus at 150"]


def test_scoring_unknown_ids_are_listed_by_the_league_s_own_name():
    sc, rep = Y.scoring(_settings([{"stat_id": "38", "value": "1"}, {"stat_id": "999", "value": "1"},
                                   {"stat_id": "14", "value": "0"}],
                                  [{"stat_id": "999", "name": "Brand New Stat"}]))
    assert sc == {} and rep["unpriced"] == ["Tackle Solo", "Brand New Stat"] and rep["unpriced_stat_ids"] == [38, 999]


def test_slots_flex_superflex_and_idp():
    slots, note = Y.slots(_settings([], positions=[("QB", 1), ("RB", 2), ("WR", 2), ("TE", 1), ("W/R/T", 2),
                                                   ("Q/W/R/T", 1), ("W/R", 1), ("W/T", 1), ("K", 1), ("DEF", 1),
                                                   ("LB", 2), ("D", 1), ("BN", 5), ("IR", 2), ("XYZ", 1)]))
    assert slots == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "SUPER_FLEX", "WRRB_FLEX", "REC_FLEX", "K",
                     "DEF"] + ["BN"] * 5
    assert note["ir"] == 2 and note["idp"] == ["LB", "LB", "D"] and note["unknown"] == ["XYZ"]


def test_every_mapped_slot_is_one_the_solver_models():
    from league_lab.lineup import slot_eligibility
    for yahoo, ours in Y.SLOT.items():
        if ours not in ("BN", "IR"):
            assert slot_eligibility(ours) is not None, yahoo
    assert slot_eligibility("SUPER_FLEX") >= {"QB", "RB", "WR", "TE"}


def test_team_codes():
    assert [Y.team_code(x) for x in ("Jax", "Was", "KC", "LAR", "WSH", None)] == ["JAX", "WAS", "KC", "LAR", "WAS", None]


# ------------------------------------------------------------------ the read path (injected fetch)
class _Fetch:
    def __init__(self, answers: dict[str, tuple[int, dict, str]]) -> None:
        self.answers = answers
        self.seen: list[tuple[str, dict]] = []

    def __call__(self, url: str, headers: dict) -> tuple[int, dict, str]:
        self.seen.append((url, headers))
        for frag, ans in self.answers.items():
            if frag in url:
                return ans
        return 400, {}, json.dumps({"error": {"description": "not in this league"}})


def _ok(content: dict) -> tuple[int, dict, str]:
    return 200, {}, json.dumps({"fantasy_content": content})


def test_reads_send_bearer_and_format_json_and_cache_per_manager(session, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    f = _Fetch({"/game/nfl": _ok({"game": [{"game_key": "461", "code": "nfl"}]})})
    c = Y.Yahoo(fetch=f)
    assert c.resolve("nfl.l.4242") == "461.l.4242" and c.resolve("461.l.9") == "461.l.9"
    url, headers = f.seen[0]
    assert url == "https://fantasysports.yahooapis.com/fantasy/v2/game/nfl?format=json"
    assert headers["Authorization"] == "Bearer AT"
    c.game_key()
    assert len(f.seen) == 1 and c.calls == 1                               # cached
    other = Y.YahooSession(refresh_token="RT-other", access_token="AT2", expires_at=4e9)
    tok = Y.request_session.set(other)
    try:
        c.game_key()                                                       # another manager: not served from the cache
    finally:
        Y.request_session.reset(tok)
    assert len(f.seen) == 2 and f.seen[1][1]["Authorization"] == "Bearer AT2"


def test_no_session_means_sign_in(monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    with pytest.raises(Y.YahooSignInRequired):
        Y.Yahoo(fetch=_Fetch({})).game_key()


def test_token_expired_refreshes_once_and_retries(session, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    monkeypatch.setenv(Y.CLIENT_ID_ENV, "cid")
    monkeypatch.setenv(Y.CLIENT_SECRET_ENV, "sec")
    monkeypatch.setattr(Y, "TOKEN_POST", lambda form, headers: (200, {"access_token": "AT-new", "expires_in": 3600}))
    calls = {"n": 0}

    def fetch(url, headers):
        calls["n"] += 1
        if headers["Authorization"] == "Bearer AT":
            return 401, {"WWW-Authenticate": 'OAuth oauth_problem="token_expired"'}, ""
        return _ok({"game": [{"game_key": "461"}]})
    c = Y.Yahoo(fetch=fetch)
    assert c.game_key() == "461" and calls["n"] == 2
    assert session.access_token == "AT-new" and session.changed and session.refresh_token == "RT"
    assert c.refreshed == 1


def test_an_expiring_token_is_refreshed_before_the_read(session, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    monkeypatch.setenv(Y.CLIENT_ID_ENV, "cid")
    monkeypatch.setenv(Y.CLIENT_SECRET_ENV, "sec")
    session.expires_at = 0
    sent = []
    monkeypatch.setattr(Y, "TOKEN_POST", lambda form, headers: (sent.append(form) or 200,
                                                                 {"access_token": "AT-2", "expires_in": 3600})[0:2])
    c = Y.Yahoo(fetch=_Fetch({"/game/nfl": _ok({"game": [{"game_key": "461"}]})}))
    c.game_key()
    assert sent == [{"grant_type": "refresh_token", "refresh_token": "RT", "redirect_uri": "oob"}]
    assert session.access_token == "AT-2"


def test_a_refused_refresh_expires_the_session(session, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    monkeypatch.setenv(Y.CLIENT_ID_ENV, "cid")
    monkeypatch.setenv(Y.CLIENT_SECRET_ENV, "sec")
    session.expires_at = 0
    monkeypatch.setattr(Y, "TOKEN_POST", lambda form, headers: (400, {"error": "invalid_grant"}))
    with pytest.raises(Y.YahooSessionExpired) as e:
        Y.Yahoo(fetch=_Fetch({})).game_key()
    assert session.expired and e.value.code == "yahoo_session_expired"


def test_not_in_the_league_and_throttled_and_down(session, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    c = Y.Yahoo(fetch=_Fetch({"league/461.l.1/": (401, {}, "You are not allowed to view this page because you are not in this league"),
                              "league/461.l.2/": (999, {}, "Request denied"),
                              "league/461.l.3/": (503, {}, "")}))
    with pytest.raises(Y.YahooLeagueNotFound) as e:
        c.settings("461.l.1")
    assert e.value.code == "yahoo_league_unknown" and "461.l.1" in str(e.value)
    with pytest.raises(Y.YahooBusy):
        c.settings("461.l.2")
    with pytest.raises(Y.YahooBusy):                                       # backing off a minute
        c.settings("461.l.3")
    c._backoff_until = 0
    with pytest.raises(Y.YahooUnavailable):
        c.settings("461.l.3")


def test_stale_answer_served_when_yahoo_fails(session, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    now = {"t": 0.0}
    state = {"down": False}

    def fetch(url, headers):
        return (503, {}, "") if state["down"] else _ok({"game": [{"game_key": "461"}]})
    c = Y.Yahoo(fetch=fetch, clock=lambda: now["t"])
    c.game_key()
    now["t"] += Y.TTL_S["game"] + 1
    state["down"] = True
    assert c.game_key() == "461" and c.stale_served == 1


def test_the_bucket_refuses_when_spent(session, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    c = Y.Yahoo(fetch=_Fetch({"/game/": _ok({"game": [{"game_key": "461"}]})}),
                bucket=TokenBucket(1, capacity=1, clock=lambda: 0.0), clock=lambda: 0.0)
    c.game_key("nfl")
    with pytest.raises(Y.YahooBusy):
        c.game_key("mlb")


def test_setup_parts_cover_every_error():
    for exc, code in ((Y.YahooNotConfigured(), "yahoo_not_configured"), (Y.YahooSignInRequired(), "yahoo_sign_in_required"),
                      (Y.YahooSessionExpired(), "yahoo_session_expired"), (Y.YahooLeagueNotFound("461.l.1"), "yahoo_league_unknown"),
                      (Y.YahooLinkInvalid(), "yahoo_link_invalid"), (Y.YahooBusy("x"), "busy"),
                      (Y.YahooUnavailable("x"), "provider_down")):
        got = Y.setup_parts(exc)
        assert got[0] == code and got[1], code
    assert Y.setup_parts(Y.YahooNotConfigured())[1] == "Yahoo sign-in is not set up on this server yet"


def test_authorize_url_and_configured(monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    monkeypatch.delenv(Y.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(Y.CLIENT_SECRET_ENV, raising=False)
    assert not Y.configured()
    with pytest.raises(Y.YahooNotConfigured):
        Y.authorize_url("https://x/cb", "s")
    monkeypatch.setenv(Y.CLIENT_ID_ENV, "cid")
    monkeypatch.setenv(Y.CLIENT_SECRET_ENV, "sec")
    u = Y.authorize_url("https://isuckatfantasy.io/api/yahoo/callback", "st")
    assert u.startswith("https://api.login.yahoo.com/oauth2/request_auth?client_id=cid&redirect_uri=https%3A%2F%2F")
    assert "response_type=code" in u and "scope=fspt-r" in u and "state=st" in u and "sec" not in u


# ------------------------------------------------------------------ the id table
def test_player_ids_yahoo_lookups(monkeypatch):
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    PI.reset()
    try:
        t = PI.table()
        assert t.yahoo_to_sleeper("29235") == "3163"                       # Jared Goff (nflverse's real ids)
        assert t.yahoo_to_gsis("29235") == "00-0033106"
        assert t.row_by_yahoo("29235")["name"] == "Jared Goff"
        assert PI.yahoo_to_sleeper("nope") is None and PI.yahoo_to_gsis(None) is None
    finally:
        PI.reset()


def test_a_yahoo_id_on_two_players_is_quarantined(tmp_path):
    f = tmp_path / "ids.csv"
    f.write_text("mfl_id,gsis_id,sleeper_id,espn_id,name,position,team,yahoo_id\n"
                 "1,00-1,11,,A,WR,KC,500\n2,00-2,22,,B,WR,KC,500\n3,00-3,33,,C,RB,KC,600\n4,00-3,33,,C,RB,KC,600\n")
    t = PI.read(f)
    assert t.yahoo_to_sleeper("500") is None and "500" in t.yahoo_dupes
    assert t.yahoo_to_sleeper("600") == "33"                                # the same player twice: kept


def test_the_columns_old_readers_rely_on_are_unchanged():
    assert PI.COLUMNS[:7] == ("mfl_id", "gsis_id", "sleeper_id", "espn_id", "name", "position", "team")
    assert "yahoo_id" in PI.COLUMNS


# ------------------------------------------------------------------ the adapter on the fixtures
@pytest.fixture
def adapter(monkeypatch, session):
    monkeypatch.setenv(Y.FIXTURES_ENV, str(YFX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    PI.reset()
    directory = json.loads((ROOT / "api" / "tests" / "fixtures" / "sleeper" / "players_nfl.json").read_text())
    yield YL.YahooLeagues(Y.Yahoo(), lambda: directory)
    PI.reset()


def test_adapter_rosters_seat_starters_where_yahoo_has_them(adapter):
    key = "yahoo:461.l.4242"
    lg = adapter.league(key)
    starting = [s for s in lg["roster_positions"] if s != "BN"]
    for r in adapter.rosters(key):
        assert len(r["starters"]) == len(starting) and "0" not in r["starters"], r["roster_id"]
        assert len(r["players"]) == len(set(r["players"])) and len(r["reserve"] or []) == 1
    mine = next(r for r in adapter.rosters(key) if r["roster_id"] == 3)
    assert mine["starters"][0] == "3163"                                   # the QB slot: Goff, by Yahoo's own seat
    assert mine["starters"][starting.index("DEF")] == "ARI"                # the defense by its team code


def test_adapter_name_match_and_unmapped(adapter):
    key = "yahoo:461.l.4242"
    adapter.rosters(key)
    by = adapter.mapping["461.l.4242"]
    assert by["99002"][1] == "name" and by["99001"] == ("yahoo:99001", "unmapped")
    assert adapter.extra_players["yahoo:99001"]["full_name"] == "Synthetic Prospect"


def test_adapter_resolves_a_link_key(adapter):
    assert adapter.league("yahoo:nfl.l.4242")["league_id"] == "yahoo:461.l.4242"


def test_adapter_transactions_by_week(adapter):
    key = "yahoo:461.l.4242"
    assert [len(adapter.transactions(key, w)) for w in (1, 2, 3, 4, 5)] == [0, 1, 2, 2, 0]
    trade = next(t for t in adapter.transactions(key, 3) if t["type"] == "trade")
    assert trade["roster_ids"] == [2, 7] and len(trade["adds"]) == 2 and trade["adds"].keys() == trade["drops"].keys()


def test_adapter_my_leagues_with_an_explicit_session(monkeypatch):
    monkeypatch.setenv(Y.FIXTURES_ENV, str(YFX))
    yl = YL.YahooLeagues(Y.Yahoo(), lambda: {})
    rows = yl.my_leagues(Y.YahooSession(refresh_token="fixture-refresh", expires_at=4e9))
    assert rows[0]["key"] == "yahoo:461.l.4242" and rows[0]["roster_id"] == 3 and rows[0]["public"] is True
    assert Y.request_session.get() is None                                  # the explicit session is not left behind
