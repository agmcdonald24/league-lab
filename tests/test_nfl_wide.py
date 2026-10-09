"""Plan F1 (Wave F): NFL-wide model outputs — the reference scorings, how a league is matched to one, the house
leagues' rows derived from the NFL-wide ones, the K / DEF ranges, the TE premium and the DDL (no database)."""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from league_lab import db, kdef, projections
from league_lab.projections import (
    ALL_COMPONENTS,
    LINE_COLUMNS,
    NFL_DDL,
    RANGE_COLUMNS,
    exact_reference,
    fit_scorings,
    house_rows,
    nfl_lines,
    price,
    reference_scorings,
)
from league_lab.scoring import compute_points, priced_keys, unmapped_keys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_kdef import SCRUBS as SCRUBS_KD  # noqa: E402 - the K / DEF fixtures, shared
from test_kdef import _synthetic  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REFS = reference_scorings(None)     # the seed file (what a fresh database reads before `dbt seed`)


def test_the_seed_holds_the_five_reference_scorings():
    with open(ROOT / "dbt/seeds/reference_scorings.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == ["name", "label", "scoring_settings"]
    assert sorted(REFS) == ["dynasty", "ppr", "scrubs", "standard", "te_premium"]
    for r in rows:   # valid JSON of a Sleeper scoring_settings dict
        assert isinstance(json.loads(r["scoring_settings"]), dict)
    sc = {k: v[1] for k, v in REFS.items()}
    assert (sc["scrubs"]["rec"], sc["scrubs"]["pass_td"]) == (0.5, 4.0)
    assert (sc["dynasty"]["rec"], sc["dynasty"]["pass_td"], sc["dynasty"]["bonus_rec_yd_100"]) == (1.0, 6.0, 3.0)
    assert (sc["ppr"]["rec"], sc["ppr"]["pass_td"], sc["standard"]["rec"], sc["standard"]["pass_td"]) == (1.0, 4.0, 0.0, 4.0)
    assert (sc["te_premium"]["rec"], sc["te_premium"]["bonus_rec_te"]) == (1.0, 0.5)
    # "standard everything else": ppr / standard / te_premium differ from Sleeper's defaults (= Scrubs) only per catch
    for name, extra in (("ppr", {"rec"}), ("standard", {"rec"}), ("te_premium", {"rec", "bonus_rec_te"})):
        diff = {k for k in set(sc[name]) | set(sc["scrubs"]) if sc[name].get(k) != sc["scrubs"].get(k)}
        assert diff == extra, name
    # labels are plain words, never a house league's name
    assert not any(re.search(r"scrubs|unclean|dynasty", v[0], re.I) for v in REFS.values())


def test_te_premium_prices_a_tight_end_catch_only_when_the_row_says_tight_end():
    sc = REFS["te_premium"][1]
    line = {"receptions": 5.0, "receiving_yards": 50.0}
    assert compute_points({**line, "position": "TE"}, sc) == pytest.approx(compute_points({**line, "position": "WR"}, sc) + 2.5)
    assert compute_points(line, sc) == compute_points({**line, "position": "WR"}, sc)   # no position: priced as before
    # still reported for the SQL side (the macro cannot condition on position), and part of the projection's keys
    assert "bonus_rec_te" in unmapped_keys(sc) and "bonus_rec_te" not in unmapped_keys(REFS["ppr"][1])
    assert priced_keys(sc, ALL_COMPONENTS)["bonus_rec_te"] == 0.5
    # projections.price passes the position, so a TE line prices the premium and a WR line does not
    df = pd.DataFrame([{**{f"proj_{c}": 0.0 for c in ALL_COMPONENTS}, "proj_receptions": 4.0, "position": p} for p in ("TE", "WR")])
    assert list(price(df, sc, "proj_")) == [6.0, 4.0]
    assert list(price(df.drop(columns="position"), sc, "proj_", "TE")) == [6.0, 6.0]


def test_a_house_league_is_matched_to_the_reference_that_prices_its_lines_identically():
    scrubs, dyn = dict(REFS["scrubs"][1]), dict(REFS["dynasty"][1])
    assert exact_reference(scrubs, REFS) == "scrubs" and exact_reference(dyn, REFS) == "dynasty"
    # keys the projected line cannot carry (kicking, long TDs, 2-pt, defense) do not decide the match
    assert exact_reference({**scrubs, "fgm_50p": 7.0, "pass_td_40p": 3.0, "sack": 4.0}, REFS) == "scrubs"
    # a float32-looking weight is the same weight; a real difference is not
    assert exact_reference({**scrubs, "rec_yd": 0.1 + 1e-12}, REFS) == "scrubs"
    assert exact_reference({**scrubs, "pass_td": 6.0}, REFS) is None
    assert exact_reference({**REFS["ppr"][1], "bonus_rec_te": 0.5}, REFS) == "te_premium"
    leagues = {"1": ("Scrubs", scrubs), "2": ("Dynasty", dyn), "3": ("Six-point", {**scrubs, "pass_td": 6.0})}
    fit, source = fit_scorings(leagues, REFS)
    assert source == {"1": "scrubs", "2": "dynasty", "3": "3"}       # no reference is league 3: fitted on its own
    assert list(fit) == [*REFS, "3"]


def _every(scorings: dict[str, dict[str, float]]) -> pd.DataFrame:
    """predict_position-shaped rows: one per scoring x player-week, the same stat line in each."""
    rng = np.random.default_rng(1)
    base = []
    for i, pos in enumerate(["QB", "RB", "WR", "TE"] * 3):
        r = {"gsis_id": f"00-{i:07d}", "season": 2026, "week": 5 + i % 2, "position": pos}
        r.update({f"proj_{c}": float(rng.uniform(0, 8)) for c in ALL_COMPONENTS})
        r["proj_receiving_yards"] = float(rng.uniform(40, 120))   # some cross the 100-yard bonus
        base.append(r)
    frames = []
    for key, sc in scorings.items():
        o = pd.DataFrame(base)
        o["league_id"] = key
        o["proj_points"] = price(o, sc, "proj_")
        o["p10"], o["p25"], o["p50"] = o["proj_points"] - 5, o["proj_points"] - 2, o["proj_points"]
        o["p75"], o["p90"] = o["proj_points"] + 3, o["proj_points"] + 7 + (key == "dynasty")
        frames.append(o)
    every = pd.concat(frames, ignore_index=True)
    every["model_version"], every["fitted_at"], every["train_seasons"] = "v3.0", datetime(2026, 10, 2, tzinfo=UTC), "2016-2025"
    return every


def test_house_rows_are_the_line_priced_in_the_league_with_the_references_ranges():
    every = _every({k: v[1] for k, v in REFS.items()})
    leagues = {"1": ("Scrubs", REFS["scrubs"][1]), "2": ("Dynasty", REFS["dynasty"][1])}
    _, source = fit_scorings(leagues, REFS)
    pred = house_rows(every, leagues, source)
    lines = nfl_lines(every)
    assert list(lines.columns) == LINE_COLUMNS and len(lines) == 12
    for lid, ref in (("1", "scrubs"), ("2", "dynasty")):
        p = pred[pred["league_id"] == lid].set_index("gsis_id")
        r = every[every["league_id"] == ref].set_index("gsis_id")
        ln = lines.set_index("gsis_id")
        assert np.array_equal(p["proj_points"], price(ln.loc[p.index].reset_index(), leagues[lid][1], "proj_").to_numpy())
        for c in ("proj_points", "p10", "p25", "p50", "p75", "p90", *[f"proj_{x}" for x in ALL_COMPONENTS]):
            assert np.array_equal(p[c].to_numpy(), r.loc[p.index, c].to_numpy()), (lid, c)
    # a wrong match (a reference that prices the line differently) is refused, never written
    with pytest.raises(ValueError, match="match is wrong"):
        house_rows(every, {"2": ("Dynasty", REFS["dynasty"][1])}, {"2": "scrubs"})


@pytest.mark.parametrize("position", ["K", "DEF"])
def test_kd_ranges_are_the_lines_priced_with_the_reference_offsets(position):
    """ops.kd_ranges rows for a scoring are exactly predict_kd's rows for a league with that scoring (the house
    leagues' ops.projections K / DEF rows), and a scoring that pays nothing for the position has none."""
    frame = _synthetic(position)
    refs = {"scrubs_like": ("ref", SCRUBS_KD), "nothing": ("no K / DEF keys", {"rec": 1.0, "pass_td": 4.0})}
    m = kdef.fit_kd(frame[frame["season"] < 2023], position, {"L": ("League", SCRUBS_KD), **refs})
    pred, lines = kdef.predict_kd(m, frame[frame["season"] == 2023], {"L": ("League", SCRUBS_KD)})
    assert m.offsets["L"] == m.offsets["scrubs_like"]
    rng = kdef.ranges_from_lines(lines.reindex(columns=["position", "unit_id", "season", "week", *kdef.KD_LINE_COLUMNS]),
                                 refs, {(n, position): m.offsets[n] for n in refs})
    assert set(rng["scoring_name"]) == {"scrubs_like"} and list(rng.columns) == kdef.KD_RANGE_COLUMNS
    a = pred.set_index(["unit_id", "week"]).sort_index()
    b = rng.set_index(["unit_id", "week"]).sort_index()
    for c in ("proj_points", "p10", "p50", "p90"):
        assert np.array_equal(a[c].to_numpy(dtype=float), b[c].to_numpy(dtype=float)), c
    assert (b["off_p10"] == m.offsets["L"][0]).all()
    assert not kdef.weighs({"rec": 1.0}, position) and kdef.weighs(SCRUBS_KD, position)


def _ddl_columns(text: str) -> list[str]:
    body = re.search(r"\((.*?)\);", text, re.S).group(1)
    return [part.split()[0] for part in body.replace("\n", " ").split(",")]


def test_nfl_wide_ddl_carries_the_freeze_labels_and_the_written_columns():
    cols = {t: _ddl_columns(ddl) for t, ddl in NFL_DDL.items()}
    for t, c in cols.items():
        assert c[-2:] == ["frozen_at", "frozen_source"], t
        assert "fitted_at" in c and "season" in c and "week" in c, t
    assert cols["ops.projection_lines"][:-2] == LINE_COLUMNS
    assert set(RANGE_COLUMNS) <= set(cols["ops.projection_ranges"])
    assert cols["ops.kd_lines"][:-2] == projections.KD_LINES_TABLE_COLUMNS
    assert set(kdef.KD_RANGE_COLUMNS) <= set(cols["ops.kd_ranges"])
    # every table is created by `league-lab db migrate` (dbt's source tests run before the first project)
    assert "*projections.NFL_DDL.values()" in Path(db.__file__).read_text()
    # and the nightly carries them as state
    nightly = (ROOT / "scripts/nightly.sh").read_text()
    state = re.search(r'^STATE_TABLES="(.*)"', nightly, re.M).group(1).split()
    # ---- IU-2: ops.projection_live is the live overlay (fr1.0), not state: empty with the default switch
    assert {t for t in NFL_DDL if t != projections.LIVE_TABLE} <= set(state)


def test_freeze_plan_works_on_a_whole_week_unit():
    """The line tables freeze per week: freeze_plan's league_id column carries one constant (WEEK_SCOPE)."""
    k = datetime(2026, 10, 2, 0, 15, tzinfo=UTC)
    now = datetime(2026, 10, 2, 5, tzinfo=UTC)
    new = pd.DataFrame({"league_id": projections.WEEK_SCOPE, "week": [4, 5]})
    stored = pd.DataFrame({"league_id": [projections.WEEK_SCOPE], "week": [4], "fitted_at": [datetime(2026, 10, 1, 19, tzinfo=UTC)],
                           "frozen_source": [None], "frozen_at": [None]})
    plan = projections.freeze_plan(new, stored, {4: k, 5: datetime(2026, 10, 9, tzinfo=UTC)}, now).set_index("week")
    assert plan.loc[4, "action"] == "keep" and plan.loc[4, "relabel"] and plan.loc[4, "frozen_source"] == "kickoff"
    assert plan.loc[5, "action"] == "write" and plan.loc[5, "frozen_source"] is None
    empty = projections.freeze_plan(new, stored.iloc[0:0], {4: k}, now).set_index("week")
    assert empty.loc[4, "action"] == "write" and empty.loc[4, "frozen_source"] == "refit"   # started, nothing stored
