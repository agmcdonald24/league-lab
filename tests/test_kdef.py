"""K and D/ST projections (plan R-13, kd1.0): pricing, the as-of feature builders, the PPG
baselines, a fit/predict smoke test, and the lineup value paths - all on fixtures, no database."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from league_lab import kdef
from league_lab.lineup import LineupInputs, _kd_maps, _proposed_player
from league_lab.scoring import compute_points

ROOT = Path(__file__).resolve().parents[1]

# League of Scrubs' kicking and D/ST keys (2026), plus a few zeros and offensive keys that must not leak in
SCRUBS = {"fgm_0_19": 3.0, "fgm_20_29": 3.0, "fgm_30_39": 3.0, "fgm_40_49": 4.0, "fgm_50p": 5.0, "fgmiss": -1.0,
          "xpm": 1.0, "xpmiss": -1.0, "sack": 1.0, "int": 2.0, "fum_rec": 2.0, "ff": 1.0, "def_td": 6.0, "def_st_td": 6.0,
          "safe": 2.0, "blk_kick": 2.0, "pts_allow_0": 10.0, "pts_allow_1_6": 7.0, "pts_allow_7_13": 4.0,
          "pts_allow_14_20": 1.0, "pts_allow_21_27": 0.0, "pts_allow_28_34": -1.0, "pts_allow_35p": -4.0,
          "def_st_ff": 1.0, "def_st_fum_rec": 1.0, "rec": 0.5, "pass_td": 4.0, "fgmiss_40_49": 0.0}


# ------------------------------------------------------------------------------ pricing
def test_price_k_equals_compute_points_on_the_nflverse_columns():
    rng = np.random.default_rng(0)
    lines = pd.DataFrame(rng.integers(0, 4, size=(40, len(kdef.K_LINE))), columns=[f"out_{c}" for c in kdef.K_LINE]).astype(float)
    got = kdef.price_k(lines, SCRUBS, "out_")
    for i, r in enumerate(lines.to_dict("records")):
        stats = {kdef.K_STAT_COLUMN[c]: r[f"out_{c}"] for c in kdef.K_LINE}      # 50+ -> fg_made_50_59, 60+ = 0
        assert got[i] == pytest.approx(compute_points(stats, SCRUBS))
    # a worked line: 1 FG 20-29, 1 FG 40-49, 1 FG 50+, 1 miss, 3 PAT, 1 PAT miss = 3 + 4 + 5 - 1 + 3 - 1
    one = pd.DataFrame([{"p_fg_made_20_29": 1, "p_fg_made_40_49": 1, "p_fg_made_50p": 1, "p_fg_missed": 1, "p_pat_made": 3, "p_pat_missed": 1}])
    assert kdef.price_k(one, SCRUBS, "p_")[0] == 13.0
    # per-distance miss keys price the split buckets (Scrubs weights them 0 -> no effect; another league would)
    other = {**SCRUBS, "fgmiss": 0.0, "fgmiss_40_49": -2.0}
    assert kdef.price_k(pd.DataFrame([{"p_fg_missed": 1, "p_fg_missed_40_49": 0.5}]), other, "p_")[0] == -1.0


def test_price_def_outcome_and_expected_buckets():
    out = pd.DataFrame([{"o_sacks": 3, "o_interceptions": 1, "o_fumble_recoveries": 1, "o_forced_fumbles": 1, "o_def_tds": 0,
                         "o_st_tds": 1, "o_safeties": 0, "o_blocked_kicks": 0, "o_points_allowed": 17},
                        {"o_sacks": 0, "o_interceptions": 0, "o_fumble_recoveries": 0, "o_forced_fumbles": 0, "o_def_tds": 0,
                         "o_st_tds": 0, "o_safeties": 0, "o_blocked_kicks": 0, "o_points_allowed": 38},
                        {"o_sacks": 2, "o_interceptions": 0, "o_fumble_recoveries": 0, "o_forced_fumbles": 0, "o_def_tds": 1,
                         "o_st_tds": 0, "o_safeties": 1, "o_blocked_kicks": 1, "o_points_allowed": 0}])
    got = kdef.price_def(kdef.with_pa_buckets(out, "o_"), SCRUBS, "o_")
    # 3 sacks + INT 2 + fum rec 2 + FF 1 + ST TD 6 + 14-20 bucket 1 = 15; a 38-point game = -4; shutout 2 + 6 + 2 + 2 + 10
    assert list(got) == [15.0, -4.0, 22.0]
    # expected points: bucket weights x probabilities
    proj = pd.DataFrame([{"p_" + c: 0.0 for c in kdef.DEF_COUNTS} | {"p_" + c: p for c, p in zip(kdef.PA_COLUMNS, [0, 0, 0.5, 0.5, 0, 0, 0], strict=True)}])
    assert kdef.price_def(proj, SCRUBS, "p_")[0] == pytest.approx(0.5 * 4 + 0.5 * 1)
    assert kdef.unmodelled_def_keys(SCRUBS) == ["def_st_ff", "def_st_fum_rec"]


def test_pa_probabilities_are_a_distribution_over_whole_points():
    p = kdef.pa_probabilities(np.array([10.0, 30.0, -3.0]), np.zeros(5))
    assert np.allclose(p.sum(axis=1), 1)
    assert list(p.argmax(axis=1)) == [2, 5, 0]          # 10 -> 7-13, 30 -> 28-34, below 0.5 -> shutout
    p = kdef.pa_probabilities(np.array([20.0]), np.array([-7.0, 0.0, 7.0, 16.0]))
    assert p[0].tolist() == pytest.approx([0, 0, 0.25, 0.25, 0.25, 0, 0.25])   # 13, 20, 27, 36
    edge = kdef.pa_probabilities(np.array([6.4, 6.6]), np.zeros(1))
    assert edge.argmax(axis=1).tolist() == [1, 2]        # 6.4 rounds to 6 (1-6), 6.6 to 7 (7-13)


def test_def_points_macro_lists_the_same_keys_as_python():
    macro = (ROOT / "dbt/macros/def_points.sql").read_text()
    pairs = dict(re.findall(r"'(\w+)': '(\w+)'", macro))
    assert pairs == kdef.DEF_STAT_MAP
    buckets = re.findall(r"\('(pts_allow_\w+)', (\d+), (\d+|none)\)", macro)
    assert [(k, int(lo), None if hi == "none" else int(hi)) for k, lo, hi in buckets] == kdef.PTS_ALLOW_BUCKETS


# ------------------------------------------------------------------------------ features: nothing from the week itself or later
def _team_games() -> pd.DataFrame:
    """Two teams, 2025 weeks 1-3 (KC bye in 2) and 2026 weeks 1-4 (week 3-4 not played yet)."""
    rows = []
    games = [(2025, 1, True), (2025, 3, True), (2026, 1, True), (2026, 2, True), (2026, 3, False), (2026, 4, False)]
    for season, week, played in games:
        gid = f"{season}_{week:02d}_KC_BUF"
        for team, opp, pf, pa in (("KC", "BUF", 10 * week, 3 * week), ("BUF", "KC", 3 * week, 10 * week)):
            base = dict.fromkeys(kdef.TEAM_GAME_COLUMNS, None)
            vals = {"points_for": pf, "points_allowed": pa, "fg_att": week, "fg_made": week, "pat_att": 2, "red_zone_plays": 5,
                    "offense_epa": 6.0, "plays": 60, "sacks": week, "interceptions": 1, "fumble_recoveries": 0, "forced_fumbles": 1,
                    "def_tds": 0, "st_tds": 0, "blocked_kicks": 0, "sacks_suffered": 2, "giveaways": 1}
            rows.append({**base, **(vals if played else {}), "team": team, "opponent": opp, "game_id": gid, "season": season,
                         "week": week, "played": played})
    return pd.DataFrame(rows)


def test_team_asof_uses_only_earlier_played_games():
    ta = kdef.team_asof(_team_games()).set_index(["team", "season", "week"])
    # 2025 week 3: one earlier game (week 1)
    assert ta.loc[("KC", 2025, 3), "std_points_for"] == 10 and ta.loc[("KC", 2025, 3), "team_games_std"] == 1
    # 2026 week 1: nothing this season yet; last season's per game = (10 + 30) / 2
    assert np.isnan(ta.loc[("KC", 2026, 1), "std_points_for"]) and ta.loc[("KC", 2026, 1), "prev_points_for"] == 20
    # 2026 week 2 sees week 1 only; weeks 3 and 4 (not played) see weeks 1-2 - the latest known, not their own
    assert ta.loc[("KC", 2026, 2), "std_points_for"] == 10
    for w in (3, 4):
        assert ta.loc[("KC", 2026, w), "std_points_for"] == 15 and ta.loc[("KC", 2026, w), "l3_sacks"] == 1.5
        assert ta.loc[("KC", 2026, w), "team_games_std"] == 2
    # the FG attempts a defense allowed are the opponent's attempts in that game
    assert ta.loc[("BUF", 2026, 3), "std_fg_att_allowed"] == 1.5 and ta.loc[("BUF", 2026, 3), "std_epa_per_play"] == pytest.approx(0.1)


def _kicker_units() -> pd.DataFrame:
    rows = []
    for season, week, played, made30, miss30, made50, miss50 in [(2025, 1, True, 2, 0, 1, 1), (2025, 2, True, 1, 1, 0, 0),
                                                                  (2026, 1, True, 0, 0, 2, 0), (2026, 2, False, 0, 0, 0, 0)]:
        r = {f"out_{c}": 0.0 for c in kdef.K_LINE}
        r.update({"out_fg_made_30_39": made30, "out_fg_missed_30_39": miss30, "out_fg_made_50p": made50, "out_fg_missed_50p": miss50,
                  "out_fg_missed": miss30 + miss50, "out_pat_made": 3.0, "out_pat_missed": 0.0})
        if not played:
            r = dict.fromkeys(r)
        rows.append({"unit_id": "k1", "season": season, "week": week, "played": played, **r})
    return pd.DataFrame(rows)


def test_kicker_asof_shrinks_career_accuracy_before_the_week():
    ka = kdef.kicker_asof(_kicker_units()).set_index(["season", "week"])
    first = ka.loc[(2025, 1)]
    assert first["k_games"] == 0 and first["k_acc_short"] == pytest.approx(kdef.K_PRIOR["short"])   # no history: the prior
    # 2026 week 2 (not played): career before it = 3 short made of 4, 3 long made of 4
    w = ka.loc[(2026, 2)]
    assert w["k_games"] == 3 and w["k_att_short"] == 4
    assert w["k_acc_short"] == pytest.approx((3 + 10 * kdef.K_PRIOR["short"]) / (4 + 10))
    assert w["k_acc_long"] == pytest.approx((3 + 10 * kdef.K_PRIOR["long"]) / (4 + 10))
    assert w["k_share_long"] == pytest.approx((4 + 1) / (8 + 6))


def test_ppg_baselines_season_to_date_falls_back_to_last_season_and_last3_crosses_seasons():
    frame = _kicker_units().assign(position="K")
    b = kdef.ppg_baselines(frame, "K", SCRUBS).set_index(["season", "week"])
    pts = {(2025, 1): 2 * 3 + 5 - 1 + 3, (2025, 2): 3 - 1 + 3, (2026, 1): 10 + 3}
    assert np.isnan(b.loc[(2025, 1), "season_ppg"]) and np.isnan(b.loc[(2025, 1), "last3_ppg"])
    assert b.loc[(2025, 2), "season_ppg"] == pts[(2025, 1)]
    assert b.loc[(2026, 1), "season_ppg"] == pytest.approx((pts[(2025, 1)] + pts[(2025, 2)]) / 2)   # last season's
    assert b.loc[(2026, 2), "season_ppg"] == pts[(2026, 1)]
    assert b.loc[(2026, 2), "last3_ppg"] == pytest.approx(sum(pts.values()) / 3)


# ------------------------------------------------------------------------------ fit / predict (synthetic, small)
def _synthetic(position: str, n_seasons: int = 4, units: int = 30, weeks: int = 12) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for s in range(2020, 2020 + n_seasons):
        for u in range(units):
            for w in range(1, weeks + 1):
                itt = rng.uniform(15, 30)
                r = {"position": position, "unit_id": f"{position}{u}", "season": s, "week": w, "played": True,
                     "implied_team_total": itt, "opp_implied_total": 45 - itt}
                for f in kdef.FEATURES[position]:
                    r.setdefault(f, rng.normal())
                if position == "K":
                    for c in kdef.K_LINE:
                        r[f"out_{c}"] = float(rng.poisson(0.3 + itt / 60))
                else:
                    for c in kdef.DEF_COUNTS:
                        r[f"out_{c}"] = float(rng.poisson(0.5))
                    r["out_points_allowed"] = float(max(0, round(r["opp_implied_total"] + rng.normal(0, 8))))
                rows.append(r)
    return pd.DataFrame(rows)


@pytest.mark.parametrize("position", ["K", "DEF"])
def test_fit_and_predict_give_ordered_intervals_priced_per_league(position):
    frame = _synthetic(position)
    scorings = {"L": ("League", SCRUBS)}
    m = kdef.fit_kd(frame[frame["season"] < 2023], position, scorings)
    assert m.n_rows == 3 * 30 * 12 and set(m.offsets) == {"L"}
    lo, mid, hi = m.offsets["L"]
    assert lo < mid < hi
    pred, lines = kdef.predict_kd(m, frame[frame["season"] == 2023], scorings)
    assert len(pred) == len(lines) == 30 * 12
    assert (pred["p10"] <= pred["p50"]).all() and (pred["p50"] <= pred["p90"]).all() and (pred["p10"] >= 0).all()
    assert (pred["p90"] >= pred["proj_points"]).all()
    # the priced line is the league's price of the stat line
    assert np.allclose(pred["proj_points"], kdef.price(lines, position, SCRUBS, "proj_"))
    if position == "DEF":
        assert np.allclose(lines[[f"proj_{c}" for c in kdef.PA_COLUMNS]].sum(axis=1), 1)
    else:
        assert np.allclose(lines[[f"proj_{b}" for b in kdef.K_MISS_BUCKETS]].sum(axis=1), lines["proj_fg_missed"])
    # deterministic: the same fit twice gives the same numbers
    m2 = kdef.fit_kd(frame[frame["season"] < 2023], position, scorings)
    pred2, _ = kdef.predict_kd(m2, frame[frame["season"] == 2023], scorings)
    pd.testing.assert_frame_equal(pred, pred2)


def test_weather_hook_is_off_by_default_and_adds_wind_and_dome_when_asked():
    """Plan D3: kd1.0 is unchanged unless weather is asked for; then the game's wind and dome join the
    inputs (by game_id; a game without weather is NULL = unknown, never 0)."""
    frame = _synthetic("K")
    frame["game_id"] = (frame["season"].astype(str) + "_" + frame["week"].astype(str) + "_"
                        + (frame["unit_id"].str[1:].astype(int) // 2).astype(str))      # two kickers per game
    assert kdef.features_for("K") == kdef.FEATURES["K"] and "wx_wind_mph" not in kdef.FEATURES["K"]
    games = frame[["game_id"]].drop_duplicates().reset_index(drop=True)
    wx = games.assign(wx_dome=(games.index % 4 == 0).astype(float), wx_wind_mph=(games.index % 7) * 3.0, wx_gust_mph=None,
                      wx_precip_in=None, wx_temp_f=50.0, wx_source="nflverse_observed").iloc[:-1]   # the last game: no weather
    f = kdef.with_weather(frame, wx)
    assert len(f) == len(frame) and f["wx_wind_mph"].isna().sum() == (frame["game_id"] == games["game_id"].iloc[-1]).sum()
    scorings = {"L": ("League", SCRUBS)}
    m = kdef.fit_kd(f[f["season"] < 2023], "K", scorings, weather=True)
    assert m.features == kdef.FEATURES["K"] + ["wx_wind_mph", "wx_dome"]
    pred, _ = kdef.predict_kd(m, f[f["season"] == 2023], scorings)
    assert len(pred) == 30 * 12 and pred["proj_points"].notna().all()
    off = kdef.fit_kd(frame[frame["season"] < 2023], "K", scorings)
    assert off.features == kdef.FEATURES["K"]


# ------------------------------------------------------------------------------ lineup value paths (B1)
def _inp(kd_rows: list[dict], k_ppg: dict | None = None) -> LineupInputs:
    sleeper = {"k1": {"position": "K", "fantasy_positions": ["K"], "team": "KC"},
               "k2": {"position": "K", "fantasy_positions": ["K"], "team": "GB"},
               "k3": {"position": "K", "fantasy_positions": ["K"], "team": "DAL"},
               "LAR": {"position": "DEF", "fantasy_positions": ["DEF"], "team": "LAR"}}
    kick = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)
    return LineupInputs(season=2026, leagues=[], weeks={}, proj={}, weekly={}, current={}, sleeper=sleeper,
                        k_ppg=k_ppg or {}, games={4: {"KC": kick, "GB": kick, "DAL": kick, "LA": kick}}, **_kd_maps(kd_rows))


def _kd(unit, pos, team, pts, status=None, roster="ACT"):
    return {"league_id": "L", "week": 4, "position": pos, "unit_id": unit, "proj_points": pts, "team": team,
            "report_status": status, "roster_status": roster}


def test_lineup_values_k_and_def_from_their_projection_with_fallbacks():
    as_of = datetime(2026, 10, 1, tzinfo=UTC)
    rows = [_kd("g-k1", "K", "KC", 8.4), _kd("g-gb", "K", "GB", 7.1), _kd("LAR", "DEF", "LA", 6.3),
            _kd("g-d1", "K", "DAL", 7.0), _kd("g-d2", "K", "DAL", 6.0)]
    inp = _inp(rows, k_ppg={("L", "g-k3"): 9.9})

    def player(sid, gsis, pos):
        return _proposed_player(inp, "L", 4, {"sleeper_player_id": sid, "gsis_id": gsis, "position": pos}, None, {}, True, as_of)

    k = player("k1", "g-k1", "K")
    assert (k.value, k.value_source, k.playable) == (8.4, "proj_points", True)
    # a Sleeper kicker without an NFL id: his NFL team's only projected kicker that week
    smack = player("k2", None, "K")
    assert (smack.value, smack.value_source) == (7.1, "proj_points")
    # two projected kickers on his team: ambiguous -> no projection (never guessed); no PPG either -> unvalued
    amb = player("k3", None, "K")
    assert amb.value_source == "unvalued" and amb.playable
    # a mapped kicker without a projection row keeps the season-PPG path
    vet = player("k3", "g-k3", "K")
    assert (vet.value, vet.value_source) == (9.9, "season_ppg")
    d = player("LAR", None, "DEF")
    assert (d.value, d.value_source, d.playable) == (6.3, "proj_points", True)


def test_lineup_k_out_or_on_ir_cannot_play():
    as_of = datetime(2026, 10, 1, tzinfo=UTC)
    inp = _inp([_kd("g-k1", "K", "KC", 8.4, status="Out"), _kd("g-gb", "K", "GB", 7.1, roster="RES")])
    out = _proposed_player(inp, "L", 4, {"sleeper_player_id": "k1", "gsis_id": "g-k1", "position": "K"}, None, {}, True, as_of)
    assert (out.playable, out.reason, out.value) == (False, "Out", 8.4)
    ir = _proposed_player(inp, "L", 4, {"sleeper_player_id": "k2", "gsis_id": "g-gb", "position": "K"}, None, {}, True, as_of)
    assert (ir.playable, ir.reason) == (False, "NFL injured reserve")
