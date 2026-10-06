"""Wave I-N, IN-6 — the League screen's power rankings and the rest of the season (league_lab_api/outlook.py).

1. The simulation on hand-built leagues (no database): a team certain to win, two identical teams (equal odds within
   Monte Carlo error, fixed seed), the clinched / eliminated proofs, the tie-break (points for), the byes, the odds
   adding up to the playoff spots, the time budget (a 14-team league under 2 s), the first week reproducing the week's
   odds (``league_lab.decisions.lineup_win_probability``) within a point.
2. The words: the record-vs-points gap.
3. The route: a reference key is ``needs_league``; the bucket is ``heavy``; on the house leagues (needs_db) every team
   is ranked, the odds add up to the spots, my team is marked, a missing week of the schedule leaves the rankings and
   says why, the answer is cached per league and build; MyFantasyLeague: no playoff odds, with the reason.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from league_lab import decisions as WP
from scipy.stats import norm

from league_lab_api import outlook as O
from league_lab_api import ratelimit

from .conftest import DYNASTY, SCRUBS, needs_db


def _season(teams, weeks, mean_of, cv=0.2, drift=0.0, n=4000, seed=7):
    means = {(t, w): mean_of(t, w) for t in teams for w in weeks}
    level = {t: float(np.mean([mean_of(t, w) for w in weeks])) for t in teams}
    return O.season_totals(teams, weeks, means, {t: cv for t in teams}, level, n=n, seed=seed, drift=drift)


@pytest.fixture(autouse=True)
def _outlook_caches():
    """Every test starts with no kept outlook and no kept schedule (both are process-wide regions)."""
    O._cache.clear()
    O._schedules.clear()
    yield
    O._cache.clear()
    O._schedules.clear()


FOUR = [1, 2, 3, 4]
WEEKS = [5, 6, 7, 8, 9, 10]
GAMES = {w: [(1, 2), (3, 4)] if i % 3 == 0 else [(1, 3), (2, 4)] if i % 3 == 1 else [(1, 4), (2, 3)]
         for i, w in enumerate(WEEKS)}


# ------------------------------------------------------------------------------------------- 1. the simulation
def test_a_team_certain_to_win_wins_every_game_and_makes_the_playoffs():
    tot = _season(FOUR, WEEKS, lambda t, w: 300.0 if t == 1 else 100.0, cv=0.05)
    res = O.play_out(FOUR, WEEKS, tot, GAMES, {t: 0.0 for t in FOUR}, {t: 0.0 for t in FOUR}, spots=2,
                     calibrate_first=False)
    one = res["teams"][1]
    assert one["wins_mean"] == len(WEEKS) and one["wins_p10"] == len(WEEKS)
    assert one["playoff"] == 1.0 and one["top_seed"] == 1.0


def test_two_identical_teams_get_equal_odds_within_monte_carlo_error():
    tot = _season(FOUR, WEEKS, lambda t, w: 120.0 if t in (1, 2) else 100.0, cv=0.2, n=5000)
    res = O.play_out(FOUR, WEEKS, tot, GAMES, {t: 0.0 for t in FOUR}, {t: 0.0 for t in FOUR}, spots=2,
                     calibrate_first=False)
    p1, p2 = res["teams"][1]["playoff"], res["teams"][2]["playoff"]
    se = np.sqrt(p1 * (1 - p1) / 5000)
    assert abs(p1 - p2) < 4 * se + 1e-9
    assert p1 > res["teams"][3]["playoff"]
    # the same seed: the same answer
    tot2 = _season(FOUR, WEEKS, lambda t, w: 120.0 if t in (1, 2) else 100.0, cv=0.2, n=5000)
    assert np.array_equal(tot, tot2)


def test_odds_add_up_to_the_playoff_spots_and_the_byes_are_the_top_seeds():
    teams = list(range(1, 7))
    weeks = [5, 6, 7, 8, 9]
    games = {w: [(1 + (i + j) % 6, 1 + (i + 5 - j) % 6) for j in range(3)] for i, w in enumerate(weeks)}
    games = {w: [(a, b) for a, b in g if a != b] for w, g in games.items()}
    tot = _season(teams, weeks, lambda t, w: 100.0 + 3 * t, cv=0.2)
    res = O.play_out(teams, weeks, tot, games, {t: 0.0 for t in teams}, {t: 0.0 for t in teams}, spots=4, byes=O.byes_for(4))
    assert sum(r["playoff"] for r in res["teams"].values()) == pytest.approx(4.0, abs=1e-3)
    assert sum(r["top_seed"] for r in res["teams"].values()) == pytest.approx(1.0, abs=1e-3)
    assert all(r["bye"] is None for r in res["teams"].values())            # four spots: no byes
    res6 = O.play_out(teams, weeks, tot, games, {t: 0.0 for t in teams}, {t: 0.0 for t in teams}, spots=6, byes=O.byes_for(6))
    assert sum(r["bye"] for r in res6["teams"].values()) == pytest.approx(2.0, abs=1e-3)
    assert O.byes_for(6) == 2 and O.byes_for(4) == 0 and O.byes_for(8) == 0 and O.byes_for(None) == 0


def test_the_tie_break_is_points_for():
    """Equal wins at the end: the team with more points for takes the last spot, every season."""
    tot = _season(FOUR, [5], lambda t, w: {1: 150.0, 2: 100.0, 3: 140.0, 4: 90.0}[t], cv=0.0)
    wins0 = {1: 2.0, 2: 3.0, 3: 2.0, 4: 3.0}
    pf0 = {1: 300.0, 2: 300.0, 3: 400.0, 4: 290.0}
    # week 5: 1 beats 2, 3 beats 4 -> everyone on 3 wins; points for: 3 (540) > 1 (450) > 2 (400) > 4 (380)
    res = O.play_out(FOUR, [5], tot, {5: [(1, 2), (3, 4)]}, wins0, pf0, spots=2, calibrate_first=False)
    assert all(res["teams"][t]["wins_mean"] == 3.0 for t in FOUR)
    assert res["teams"][3]["playoff"] == 1.0 and res["teams"][1]["playoff"] == 1.0
    assert res["teams"][2]["playoff"] == 0.0 and res["teams"][3]["top_seed"] == 1.0


def test_clinched_and_eliminated_are_proven_on_wins_alone():
    wins = {1: 9.0, 2: 3.0, 3: 2.0, 4: 1.0}
    flags = O.clinch_flags(FOUR, wins, {t: 2 for t in FOUR}, spots=2)
    assert flags[1] == "clinched"                      # nobody else can reach 9 wins
    assert flags[4] is None                            # 1 + 2 = 3 wins can still tie team 2 for the 2nd spot
    flags = O.clinch_flags(FOUR, {1: 9.0, 2: 8.0, 3: 2.0, 4: 1.0}, {t: 2 for t in FOUR}, spots=2)
    assert flags[3] == "eliminated" and flags[4] == "eliminated" and flags[1] == "clinched"
    assert flags[2] == "clinched"                      # only team 1 can reach 8 wins: 2 is in the top 2
    flags = O.clinch_flags(FOUR, {t: 2.0 for t in FOUR}, {t: 4 for t in FOUR}, spots=2)
    assert set(flags.values()) == {None}               # nothing proven: the simulation decides
    # a clinched team reads 100% in the simulation too (every season it is in), an eliminated one 0%
    tot = _season(FOUR, [5, 6], lambda t, w: 100.0, cv=0.3)
    res = O.play_out(FOUR, [5, 6], tot, {5: [(1, 2), (3, 4)], 6: [(1, 3), (2, 4)]}, {1: 9.0, 2: 8.0, 3: 2.0, 4: 1.0},
                     {t: 0.0 for t in FOUR}, spots=2)
    assert res["teams"][1]["playoff"] == 1.0 and res["teams"][2]["playoff"] == 1.0
    assert res["teams"][3]["playoff"] == 0.0 and res["teams"][4]["playoff"] == 0.0


def _row(key, pos, team, opp, p50, sd=6.0):
    z10, z25 = norm.ppf(0.10), norm.ppf(0.25)
    return {"key": key, "position": pos, "team": team, "opponent": opp, "value": p50, "actual": None,
            "p10": p50 + z10 * sd, "p25": p50 + z25 * sd, "p50": p50, "p75": p50 - z25 * sd, "p90": p50 - z10 * sd}


def _lineup(prefix, shift, nfl):
    pos = ["QB", "RB", "RB", "WR", "WR", "TE", "WR", "K", "DEF"]
    base = [20, 13, 11, 14, 12, 9, 10, 8, 7]
    return [_row(f"{prefix}{i}", p, nfl[i % len(nfl)], nfl[(i + 1) % len(nfl)], b + shift, sd=4 + b / 3)
            for i, (p, b) in enumerate(zip(pos, base, strict=True))]


def test_the_first_week_reproduces_the_weeks_odds_within_a_point():
    """The whole league's joint draws, each game decided with the week's odds' calibration: the chance of each game is
    lineup_win_probability's p (both lineups, the same copula pieces) within a point."""
    nfl = ["KC", "BUF", "DAL", "PHI", "SF", "DET"]
    sides = {1: _lineup("a", 6.0, nfl), 2: _lineup("b", 0.0, nfl[::-1]), 3: _lineup("c", -4.0, nfl[2:] + nfl[:2]),
             4: _lineup("d", 2.0, nfl[3:] + nfl[:3])}
    sides[1][0]["actual"] = 31.0                       # a game already in: his points, no range
    fw = O.first_week_draws(sides, n=O.SEASONS)
    ix = {t: i for i, t in enumerate(fw["teams"])}
    for a, b in ((1, 2), (3, 4), (1, 3), (2, 4)):
        want = WP.lineup_win_probability(sides[a], sides[b])["p"]
        res, _raw, _p = O.calibrated_result(fw["totals"][:, ix[a]] - fw["totals"][:, ix[b]])
        assert abs(float(res.mean()) - want) < 0.01, (a, b, float(res.mean()), want)
    assert fw["expected"][ix[1]] == pytest.approx(31.0 + sum(r["value"] for r in sides[1][1:]))
    assert (fw["spread"] > 0).all() and (fw["ranged_share"] == 1.0).all()


def test_a_fourteen_team_season_fits_the_time_budget():
    teams = list(range(1, 15))
    nfl = ["KC", "BUF", "DAL", "PHI", "SF", "DET", "MIA", "CIN", "BAL", "LAC", "GB", "MIN", "SEA", "LA", "HOU", "NYJ"]
    sides = {t: _lineup(f"t{t}_", (t % 5) - 2.0, nfl[t % 8:] + nfl[: t % 8]) for t in teams}
    weeks = list(range(5, 15))
    games = {w: [(teams[i], teams[-1 - i]) for i in range(7)] for w in weeks}
    t0 = time.perf_counter()
    fw = O.first_week_draws(sides)
    tot = O.season_totals(teams, weeks, {(t, w): 110.0 + t for t in teams for w in weeks}, {t: 0.2 for t in teams},
                          {t: 110.0 + t for t in teams}, first=fw["totals"])
    res = O.play_out(teams, weeks, tot, games, {t: 1.0 for t in teams}, {t: 400.0 for t in teams}, spots=6, byes=2)
    took = time.perf_counter() - t0
    assert took < 2.0, f"14 teams, {O.SEASONS} seasons: {took:.2f} s"
    assert sum(r["playoff"] for r in res["teams"].values()) == pytest.approx(6.0, abs=1e-3)


def test_later_weeks_widen_with_the_drift():
    """The further out, the wider: the spread of a team's week grows with the weeks ahead when the drift is on."""
    weeks = list(range(5, 15))
    tot = _season([1, 2], weeks, lambda t, w: 100.0, cv=0.15, drift=O.DRIFT, n=20000)
    sd = tot[:, 0, :].std(axis=0)
    assert sd[-1] > sd[1] * 1.05
    flat = _season([1, 2], weeks, lambda t, w: 100.0, cv=0.15, drift=0.0, n=20000)
    assert flat[:, 0, -1].std() == pytest.approx(flat[:, 0, 1].std(), rel=0.05)
    assert flat[:, 0, 1].std() == pytest.approx(0.15 * 100 / WP.WEEK_SHRINK, rel=0.05)    # widened by 1 / 0.60


# ------------------------------------------------------------------------------------------- 2. the words
def test_the_gap_between_record_and_points_in_words():
    assert O.gap_words(3, 1, 0, 1, 8, 12) == "3–1 on the 8th-most points: a soft schedule so far"
    assert O.gap_words(1, 3, 0, 10, 2, 12) == "1–3 on the 2nd-most points: a hard schedule so far"
    assert O.gap_words(0, 3, 0, 10, 1, 10) == "0–3 on the most points: a hard schedule so far"
    assert O.gap_words(2, 2, 0, 5, 6, 12) is None                  # a place or two apart is not a story
    assert O.order_rank({1: (2.0, 300.0), 2: (2.0, 310.0), 3: (3.0, 100.0)}) == {3: 1, 2: 2, 1: 3}


# ------------------------------------------------------------------------------------------- 3. the route
def test_a_reference_key_needs_a_league_and_the_route_is_heavy(client):
    r = client.get("/api/league/outlook?league=ref:half")
    assert r.status_code == 404 and r.json()["code"] == "needs_league"
    assert ratelimit.bucket_for("GET", "/api/league/outlook", "league=1") == "heavy"


@needs_db
@pytest.mark.parametrize("league,spots", [(SCRUBS, 4), (DYNASTY, 6)])
def test_the_house_leagues_outlook(client, league, spots):
    O._cache.clear()
    d = client.get(f"/api/league/outlook?league={league}&team=2").json()
    rows = d["power"]["rows"]
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    assert all(r["per_week"] > 0 for r in rows) and [r["per_week"] for r in rows] == sorted((r["per_week"] for r in rows), reverse=True)
    assert sum(r["mine"] for r in rows) == 1 and next(r for r in rows if r["mine"])["roster_id"] == 2
    assert d["power"]["movement"] is None and "No movement arrows" in d["power"]["movement_note"]
    ol = d["outlook"]
    assert ol["available"], ol["reason"]
    assert ol["playoff_teams"] == spots and ol["tiebreak"] == "points for"
    assert sum(r["playoff"] for r in ol["rows"]) == pytest.approx(spots, abs=0.02)
    assert sum(r["top_seed"] for r in ol["rows"]) == pytest.approx(1.0, abs=0.01)
    assert all(r["wins_p10"] <= r["wins_mean"] <= r["wins_p90"] for r in ol["rows"])
    assert (ol["byes"] == 2) == (spots == 6)
    assert len(d["definitions"]) >= 5 and len(ol["assumptions"]) == 4
    # a second ask is the cache's answer (per league and build)
    t0 = time.perf_counter()
    again = client.get(f"/api/league/outlook?league={league}").json()
    assert time.perf_counter() - t0 < 0.5
    assert again["power"]["rows"][0]["roster_id"] == rows[0]["roster_id"] and not any(r["mine"] for r in again["power"]["rows"])


@needs_db
def test_the_cache_is_keyed_by_league_and_build(monkeypatch):
    O._cache.clear()
    a = O.outlook(SCRUBS)
    assert O.outlook(SCRUBS)["timings_ms"] == a["timings_ms"]                 # the same build: the kept answer
    monkeypatch.setattr(O, "_stamp", lambda: ("2026-10-07T11:00:00Z", None))  # a new build
    b = O.outlook(SCRUBS)
    assert len(O._cache) == 2 and b["power"]["rows"] == a["power"]["rows"]
    assert {k[0] for k in O._cache.keys()} == {SCRUBS}


@needs_db
def test_a_missing_week_of_the_schedule_keeps_the_rankings_and_says_why(client, monkeypatch):
    from league_lab import anyleague as A
    O._cache.clear()
    real = A.sleeper().matchups
    monkeypatch.setattr(type(A.sleeper()), "matchups", lambda self, lid, w: [] if int(w) == 9 else real(lid, w))
    d = client.get(f"/api/league/outlook?league={SCRUBS}").json()
    assert len(d["power"]["rows"]) == 10
    assert not d["outlook"]["available"] and "week 9" in d["outlook"]["reason"] and d["outlook"]["rows"] == []
    O._cache.clear()


@needs_db
def test_myfantasyleague_has_no_playoff_odds_and_says_why(client):
    O._cache.clear()
    d = client.get("/api/league/outlook?league=mfl:70587").json()
    ol = d["outlook"]
    assert len(d["power"]["rows"]) == 12
    if ol["available"]:
        assert ol["playoff_teams"] is None and "MyFantasyLeague" in ol["playoff_reason"]
        assert all(r["playoff"] is None and r["bye"] is None for r in ol["rows"])
    else:
        assert ol["reason"]


def test_the_schedule_reader_keeps_double_headers_and_names_the_missing_week():
    class Fake:
        def matchups(self, lid, w):
            if w == 7:
                return []
            # a double header: roster 1 plays 2 (matchup 1) and 3 (matchup 2); a bye row has no matchup_id
            return [{"roster_id": 1, "matchup_id": 1}, {"roster_id": 2, "matchup_id": 1}, {"roster_id": 1, "matchup_id": 2},
                    {"roster_id": 3, "matchup_id": 2}, {"roster_id": 4, "matchup_id": None}]
    games, missing = O.schedule(Fake(), "x", [5, 6])
    assert missing is None and games[5] == [(1, 2), (1, 3)]
    games, missing = O.schedule(Fake(), "x", [5, 6, 7, 8])
    assert missing == 7 and set(games) == {5, 6}


@needs_db
def test_sleeper_not_answering_the_house_league_reads_its_settings_from_the_nightly(client, monkeypatch):
    from league_lab import anyleague as A
    O._cache.clear()
    def down(self, lid):
        raise A.SleeperUnavailable("down")
    monkeypatch.setattr(type(A.sleeper()), "league", down)
    ins = O._league_inputs(SCRUBS, True)
    assert ins["lg"]["settings"]["playoff_week_start"] == 15 and ins["lg"]["settings"]["playoff_teams"] == 4
    O._cache.clear()


# ------------------------------------------------------------------------------------------- the fix round (M2, L1, the fan-out)
def test_the_quantile_step_for_many_ranges_is_predictive_ppf():
    rng = np.random.default_rng(3)
    u = np.concatenate([rng.uniform(1e-12, 1 - 1e-12, 2000), [1e-12, 0.1, 0.25, 0.5, 0.75, 0.9, 1 - 1e-12]])
    for five in (True, False):
        ds = []
        for _ in range(20):
            p10 = rng.uniform(-2, 10)
            p50, p90 = p10 + rng.uniform(0, 10), p10 + rng.uniform(10, 25)
            ds.append(WP.Predictive.from_quantiles(p10, p50, p90, *((rng.uniform(p10, p50), rng.uniform(p50, p90)) if five else ())))
        got = O.ppf_group(np.asarray(ds[0].levels), np.array([d.values for d in ds]), np.tile(u[:, None], (1, len(ds))))
        assert np.abs(got - np.column_stack([d.ppf(u) for d in ds])).max() < 1e-9


def test_the_season_count_is_capped_by_the_league_size():
    assert O.seasons_for(12, 11, 10) == 10_000 and O.seasons_for(14, 10, 10) == 10_000
    assert O.seasons_for(32, 11, 10) == 4_500 and O.seasons_for(32, 17, 24) == 2_000
    assert O.seasons_for(32, 18, 30) == 1_500 and O.seasons_for(10_000, 18, 30) == O.MIN_SEASONS


def test_memory_is_flat_in_the_season_count():
    """Chunks of seasons, only the tallies kept: 10,000 seasons peak within a few MB of 1,000."""
    import tracemalloc
    nfl = ["KC", "BUF", "DAL", "PHI", "SF", "DET", "MIA", "CIN", "BAL", "LAC", "GB", "MIN", "SEA", "LA", "HOU", "NYJ"]
    teams = list(range(1, 13))
    sides = {t: _lineup(f"t{t}_", 0.0, nfl[t % 8:] + nfl[: t % 8]) for t in teams}
    weeks = list(range(5, 16))
    games = {w: [(teams[i], teams[-1 - i]) for i in range(6)] for w in weeks}
    peaks = {}
    for n in (1_000, 10_000):
        tracemalloc.start()
        fw = O.first_week_draws(sides, n=n)
        O.simulate(teams, weeks, {(t, w): 110.0 for t in teams for w in weeks}, {t: 0.2 for t in teams},
                   {t: 110.0 for t in teams}, games, {t: 1.0 for t in teams}, {t: 300.0 for t in teams}, 6, 2,
                   first=fw["totals"], n=n)
        peaks[n] = tracemalloc.get_traced_memory()[1] / 2 ** 20
        tracemalloc.stop()
        del fw
    assert peaks[10_000] < 16 and peaks[10_000] - peaks[1_000] < 4, peaks


def test_the_hard_limits_answer_why_before_anything_is_read(monkeypatch):
    monkeypatch.setattr(O, "schedule", lambda *a, **k: pytest.fail("the schedule was read"))
    common = dict(lid="1", is_house=True, season=2026, settings={"playoff_week_start": 15, "playoff_teams": 4},
                  platform="sleeper", played=3, weeks=tuple(range(4, 17)), lineup={}, level={}, rec={}, pf={},
                  seasons=O.SEASONS)
    why = O._season_outlook({}, [], {}, {}, rids=list(range(1, 34)), **common)
    assert why == "this league has 33 teams: the outlook simulates leagues of up to 32"
    why = O._season_outlook({}, [], {}, {}, rids=[1, 2], **{**common, "settings": {"playoff_week_start": 21}, "played": 0})
    assert why == "20 regular-season weeks are left: the outlook simulates up to 18"


def test_no_range_and_too_many_starters_are_answered_before_a_single_draw(monkeypatch):
    monkeypatch.setattr(O, "first_week_draws", lambda *a, **k: pytest.fail("drew before the checks"))
    monkeypatch.setattr(O, "schedule", lambda client, lid, weeks: ({w: [(1, 2)] for w in weeks}, None))
    monkeypatch.setattr(O.cards, "decision_week", lambda season: 4)
    common = dict(lid="1", is_house=True, season=2026, settings={"playoff_week_start": 8, "playoff_teams": 2},
                  platform="sleeper", played=3, weeks=(4, 5, 6, 7), lineup={}, level={}, rec={}, pf={}, seasons=O.SEASONS)
    no_range = {1: [{"key": "a", "position": "WR", "value": 10.0, "actual": None}], 2: [{"key": "b", "position": "WR", "value": 9.0, "actual": None}]}
    monkeypatch.setattr(O, "week_sides", lambda *a, **k: (no_range, None))
    assert O._season_outlook({}, [], {}, {}, rids=[1, 2], **common) == O.MW.WIN_NO_RANGE
    big = {1: [_row(f"a{i}", "WR", "KC", "BUF", 5.0) for i in range(31)], 2: [_row("b", "WR", "DAL", "PHI", 9.0)]}
    monkeypatch.setattr(O, "week_sides", lambda *a, **k: (big, None))
    assert O._season_outlook({}, [], {}, {}, rids=[1, 2], **common) == "a lineup here has 31 starters: the outlook simulates up to 30"


@needs_db
def test_padded_league_keys_are_the_same_league_and_one_build(client, monkeypatch):
    builds = []
    real = O._build
    monkeypatch.setattr(O, "_build", lambda *a, **k: builds.append(a[0]) or real(*a, **k))
    a = client.get(f"/api/league/outlook?league={SCRUBS}").json()
    for padded in (f"{SCRUBS}%20", f"%20{SCRUBS}", f"{SCRUBS}%09", f"%0A{SCRUBS}%20"):
        b = client.get(f"/api/league/outlook?league={padded}")
        assert b.status_code == 200 and b.json()["power"]["rows"] == a["power"]["rows"]
        assert b.json()["outlook"]["available"] and b.json()["league_id"] == SCRUBS
    assert builds == [SCRUBS]
    assert client.get("/api/league/outlook?league=13897096924055511x").status_code == 404
    assert builds == [SCRUBS]


@needs_db
def test_a_second_cold_outlook_makes_no_provider_call(client):
    from league_lab import anyleague as A
    before = A.sleeper().calls
    assert client.get(f"/api/league/outlook?league={SCRUBS}").json()["outlook"]["available"]
    first = A.sleeper().calls - before
    assert first == 1 + 11                    # the league's settings + the pairings of weeks 4-14, once
    O._cache.clear()                           # the answer gone, the schedule kept
    before = A.sleeper().calls
    assert client.get(f"/api/league/outlook?league={SCRUBS}").json()["outlook"]["available"]
    assert A.sleeper().calls - before == 0
    assert len(O._schedules) == 1


@needs_db
def test_one_simulation_at_a_time_then_429_busy_and_nothing_kept(client, monkeypatch):
    monkeypatch.setattr(O, "BUSY_WAIT_S", 0.05)
    assert O._SIM.acquire(timeout=1)
    try:
        r = client.get(f"/api/league/outlook?league={SCRUBS}")
    finally:
        O._SIM.release()
    assert r.status_code == 429 and r.json()["code"] == "busy" and r.headers["retry-after"] == "3"
    assert r.json()["error"] == O.BUSY_WORDS and len(O._cache) == 0
    assert client.get(f"/api/league/outlook?league={SCRUBS}").json()["outlook"]["available"]
