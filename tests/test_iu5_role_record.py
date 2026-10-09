"""IU-5 (Wave I-U): the role record (calibration rr1.0, context_record's horizon part). No database.

The recorded forecast stores, for the live market week, each QB's probability of starting in week T and v3.6's line
beside the mixture's; it is graded on hg1.0's cases (docs/METRICS.md § "The horizon grade that counts a missed week")."""

from __future__ import annotations

import numpy as np
import pandas as pd

from league_lab import calibration as CAL
from league_lab import context_record as CR


def _qb(seasons=(2020, 2021), weeks=range(1, 19)) -> pd.DataFrame:
    """Two teams, a starter and a backup each; team B's starter loses the job from week 8 on."""
    rows = []
    for s in seasons:
        for w in weeks:
            for team, st, bk in (("A", "a1", "a2"), ("B", "b1", "b2")):
                lost = team == "B" and w >= 8
                for g, starting in ((st, 0.0 if lost else 1.0), (bk, 1.0 if lost else 0.0)):
                    rows.append({"gsis_id": g, "player_name": g, "team": team, "season": s, "week": w,
                                 "pn_qb_starting": starting, "questionable": 0.0, "snap_pct_std": 0.9 * starting,
                                 "pn_qb_games_together": float(w), "pn_qb_changed": 0.0,
                                 "pn_qb_is_rookie_or_backup": 1.0 - starting, "pn_qb_prev_ppg_diff": 0.0,
                                 "ppg_std": 15.0 * starting + 2.0, "prev_ppg": 14.0, "games_to_date": float(w - 1),
                                 "prev_games": 16.0})
    return pd.DataFrame(rows)


def test_training_rows_read_the_target_weeks_role():
    d = CAL.role_training_rows(_qb(), [2020])
    assert set(d["h"]) == set(CAL.ROLE_RECORD_H)
    b1 = d[(d["gsis_id"] == "b1") & (d["week"] == 4)]          # as of W = 3: the market week is 4
    assert b1.set_index("h")["t_start"].to_dict() == {1: True, 2: True, 3: True, 4: True, 5: False, 6: False, 7: False,
                                                      8: False}
    assert d["mkt_start"].dtype == bool and len(d) == 4 * 4 * 8   # 4 QBs x 4 market weeks x 8 horizons


def test_role_record_rows_store_v36_beside_the_mixture():
    q = _qb(seasons=(2018, 2019, 2020, 2021))
    models = CAL.fit_role_record(q, 2021)
    assert set(models) == {True, False}
    proj = pd.DataFrame({"gsis_id": ["a1", "a2"] * 3, "week": [6, 6, 7, 7, 8, 8], "proj_points": [20.0, 3.0] * 3})
    playing = {(t, w) for t in ("A", "B") for w in range(1, 19) if w != 7}     # week 7: both teams on a bye
    r = CAL.role_record_rows(q, 2021, 6, proj, playing, (18.0, 2.0), models)
    assert set(r["target_week"]) == {6, 8, 9, 10, 11, 12, 13}                  # the bye week has no row
    assert r["p_start"].between(0, 1).all()
    a1 = r[(r["gsis_id"] == "a1") & (r["target_week"] == 8)].iloc[0]
    assert a1["mkt_start"] and a1["proj_v36"] == 20.0
    assert np.isclose(a1["proj_mix"], a1["p_start"] * 20.0 + (1 - a1["p_start"]) * 2.0)
    a2 = r[(r["gsis_id"] == "a2") & (r["target_week"] == 8)].iloc[0]
    assert not a2["mkt_start"] and np.isclose(a2["proj_mix"], a2["p_start"] * 18.0 + (1 - a2["p_start"]) * 3.0)
    assert r.loc[r["gsis_id"] == "b1", "proj_v36"].isna().all()               # no v3.6 line stored: NaN, not 0


def test_hg_cases():
    assert CR.hg_case(True, "ACT", "Out") == "played"
    for roster, report in (("ACT", "Out"), ("ACT", "Doubtful"), ("INA", "Questionable"), ("RES", None)):
        assert CR.hg_case(False, roster, report) == "excluded"
    for roster in ("ACT", "INA", "DEV", "CUT", "RET"):
        assert CR.hg_case(False, roster, None) == "zero"
    assert CR.hg_case(False, "EXE", None) == "excluded" and CR.hg_case(False, None, None) == "excluded"


def test_db_migrate_creates_the_table():
    assert "create table if not exists ops.horizon_record" in CR.DDL
    assert set(CR.HORIZON_COLUMNS) <= set(CR.HORIZON_DDL.replace(",", " ").split())
