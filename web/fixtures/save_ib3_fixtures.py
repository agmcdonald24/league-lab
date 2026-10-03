"""Wave I-B (IB-3): bring the saved fixtures to the new answers, in place (the other screens' tests read the same files):

* Matchups (`matchups_defense_*.json`, `matchups_cb_*.json`): every defense row gets `n_ranked`, `tough_rank`,
  `tough_rank_l4`, `tone`, `rank_words` (`research.defense_meaning`); every cornerback row gets `tone`, `certainty`,
  `certainty_words`, `cover_rank_words`, `named_corners`, `history` (`research.cb_meaning`); both answers `rank_note`.
  Pure: the API's own functions on the saved rows, no database.
* Rest of season, "Value to my lineup" (`ros-lineup_<league>_<team>_<position>.json`): the API's answer in process
  (`ondemand.ros(..., view="lineup", team=...)`) for the three fixture leagues' teams, ALL (everyone and yours).
* My Week (`my-week_*.json`): every card gets `status` / `strength` as IB-0's API will send them (`week.ts` derives
  them for an answer without them): the house leagues from the database's current Sleeper lineup
  (`mart_player_availability.is_current_starter`); the Test League's lineup rows get `is_current_starter` from the
  Sleeper fixture's `starters` instead, so the web's own derivation is exercised too.

    cd api && LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper uv run python ../web/fixtures/save_ib3_fixtures.py [matchups|ros|week]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[1] / "api"))
os.environ.pop("LEAGUE_LAB_APP_PASSWORD", None)
os.environ.pop("LEAGUE_LAB_API_SECRET", None)

from league_lab_api import research  # noqa: E402

DYN, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
TEAMS = {SCRUBS: 2, DYN: 12, TEST: 3}


def _write(path: Path, d: dict, *, indent: int | None = None) -> None:
    """The file's own format: compact (the research answers) or one-space indented (My Week, ROS)."""
    path.write_text(json.dumps(d, ensure_ascii=False, indent=indent, separators=(",", ": ") if indent else (",", ":"))
                    + "\n")


def matchups() -> None:
    for f in sorted(OUT.glob("matchups_defense_*.json")):
        d = json.loads(f.read_text())
        rows = research.defense_meaning(pd.DataFrame(d["teams"]))
        d["teams"] = [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()}
                      for r in research._records(rows)]                     # unknown is null, never NaN
        d["rank_note"] = research.RANK_NOTE
        _write(f, d)
        print(f.name, len(d["teams"]))
    for f in sorted(OUT.glob("matchups_cb_*.json")):
        d = json.loads(f.read_text())
        for r in d.get("matchups", []):
            r.update(research.cb_meaning(r))
        d["rank_note"] = research.RANK_NOTE
        _write(f, d)
        print(f.name, len(d.get("matchups", [])))


def ros() -> None:
    from league_lab_api import ondemand
    for league, team in TEAMS.items():
        for pos in ("ALL",):
            for who in ("all", "mine"):
                d = ondemand.ros(league, pos, 50, view="lineup", team=team, who=who)
                name = f"ros-lineup_{league}_{team}_{pos}{'' if who == 'all' else '_' + who}.json"
                (OUT / name).write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str) + "\n")
                print(name, len(d["players"]))


CURRENT_SQL = """select gsis_id, is_current_starter from analytics.mart_player_availability
                 where league_id = %s and rostered_by_roster_id = %s and gsis_id is not null"""


def week() -> None:
    from league_lab_api.applib import cards
    from league_lab_api.db import query
    for f in [*sorted(OUT.glob("my-week_*.json")), *sorted((OUT.parent / "e2e" / "i0a").glob("my-week_*.json"))]:
        d = json.loads(f.read_text())
        league, team = str(d["league_id"]), int(d["roster_id"])
        if league == TEST:                       # the web's own derivation: is_current_starter on the rows
            sl = json.loads((OUT.parents[1] / "api" / "tests" / "fixtures" / "sleeper" / f"rosters_{league}.json").read_text())
            starters = {str(x) for r in sl if int(r["roster_id"]) == team for x in (r.get("starters") or [])}
            idm = query("select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)", (sorted(starters),))
            cur = set(idm["gsis_id"]) if not idm.empty else set()
            for key in ("lineup", "lineup_full"):
                for r in d.get(key, []):
                    if r.get("gsis_id"):
                        r["is_current_starter"] = r["gsis_id"] in cur
            for c in d.get("cards", []):
                c.pop("status", None)
                c.pop("strength", None)
        else:                                    # IB-0's fields, as its API computes them
            cur_df = query(CURRENT_SQL, (league, team))
            cur = {g for g, s in zip(cur_df["gsis_id"], cur_df["is_current_starter"], strict=True) if s}
            for c in d.get("cards", []):
                close = cards.is_coin_flip(c)
                c["status"] = "close" if close else ("set" if c.get("gsis_id") in cur else "change")
                pw, m = c.get("p_win"), c.get("margin") or 0.0
                c["strength"] = "coin flip" if close else ("clear" if m >= 3 or (pw or 0) >= 0.7 else "lean")
        raw = f.read_text()
        second = raw.split("\n", 2)[1] if "\n" in raw else ""
        indent = len(second) - len(second.lstrip(" ")) or 1
        f.write_text(json.dumps(d, ensure_ascii="\\u" in raw, indent=indent) + ("\n" if raw.endswith("\n") else ""))
        print(f.name, [(c["slot"], c.get("status")) for c in d.get("cards", [])])


if __name__ == "__main__":
    what = sys.argv[1:] or ["matchups", "ros", "week"]
    if "matchups" in what:
        matchups()
    if "ros" in what:
        ros()
    if "week" in what:
        week()
