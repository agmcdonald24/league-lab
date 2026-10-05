"""The API's memory, league by league (INF-2, Wave I-J — the PO's measure.py from the night of the out-of-memory event,
cleaned up so every later wave re-measures the same way).

Starts the API (``uv run uvicorn`` from ``api/``) in the fixture environment — the database in the repository's
``.env`` (read only), Sleeper / MFL / ESPN from ``api/tests/fixtures``, the clock pinned to Saturday 2026-10-03 16:00
UTC — calls each league's screens in turn and reads the server's resident memory (RSS, from ``ps``) after each group.

    uv run python scripts/measure_memory.py --port 8752 --label after            # the PO's nine steps
    uv run python scripts/measure_memory.py --port 8752 --label plateau --plateau  # + mfl:21861 + the leagues again
    LEAGUE_LAB_CACHE_MB=60 uv run python scripts/measure_memory.py --plateau --cycles 2
    MALLOC_ARENA_MAX=2 uv run python scripts/measure_memory.py --label arena2      # what the Dockerfile's ENV does
    uv run python scripts/measure_memory.py --synthetic-directory --label il4      # Sleeper's directory at its real size

``--synthetic-directory`` (IL-4, Wave I-L): the fixtures' player directory is 842 players and 11 fields (1 MB); live,
Sleeper's is ~12,200 players and 53 fields (16 MB of JSON, 37 MB once parsed). The flag writes a directory of that size
and shape into the run's own fixtures copy (``synthetic_directory``: the fixture's 842 rows with every other field
Sleeper sends added — null where the readers would see a value the fixture does not have, so the screens' answers stay
the fixture's —, plus generated players with generated ids, fields and null rates as ``raw.sleeper_player``'s payloads
of 2026-09-26 have them; no team defenses, no units: those stay the fixture's 32 + MFL's own) and reads it through the
same Sleeper fixtures path. ``--repo`` runs another checkout's server with this script's directory (the before figure).

Two figures per step: ``tree`` is the PO's (the ``uv run`` process plus the uvicorn python under it: Wave I-J's
before / after table is in this column), ``server`` is the python process alone (what Render meters: the image runs
uvicorn without uv). The run ends with ``/api/status``'s ``memory`` block (the caches' budget, region by region).
Prints a Markdown table; ``--json`` writes the rows. Needs Postgres up and ``api/.venv`` (``uv run`` makes it).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRUBS, DYNASTY, TEST, MFL, MFL2 = ("1389709692405551104", "1321941740235550720", "9000000000000000001",
                                    "mfl%3A70587", "mfl%3A21861")
PINNED_NOW = "2026-10-03T16:00:00Z"


def screens(league: str, team: int) -> list[str]:
    q = f"league={league}&team={team}"
    return [f"/api/my-week?{q}", f"/api/team?{q}", f"/api/ros?{q}", f"/api/waivers?{q}", f"/api/league?{q}",
            f"/api/players?{q}&window=season", f"/api/trades/partners?{q}", f"/api/research/matchups?{q}",
            f"/api/research/trends?{q}"]


def fixture_env(api: Path, cache_dir: str) -> dict[str, str]:
    env = dict(os.environ)
    for k in ("LEAGUE_LAB_APP_PASSWORD", "LEAGUE_LAB_API_SECRET", "LEAGUE_LAB_AVAILABILITY"):
        env.pop(k, None)
    fx = api / "tests" / "fixtures"
    env.update({"LEAGUE_LAB_NOW": PINNED_NOW, "LEAGUE_LAB_EVENTS": "off",
                "LEAGUE_LAB_ESPN_FIXTURES": str(fx / "espn"), "LEAGUE_LAB_SLEEPER_FIXTURES": str(fx / "sleeper"),
                "LEAGUE_LAB_MFL_FIXTURES": str(fx / "mfl"), "LEAGUE_LAB_PLAYER_IDS_CSV": str(fx / "ff" / "db_playerids.csv"),
                "LEAGUE_LAB_MFL_YEAR": "2026", "LEAGUE_LAB_CACHE_DIR": cache_dir})
    return env


# ---- IL-4 (Wave I-L): Sleeper's player directory at its real size and shape
DIRECTORY_ROWS = 12229                     # raw.sleeper_player, 2026-09-26 (Sleeper's /players/nfl that morning)
SLEEPER_FIELDS = (                          # every field Sleeper sends (raw.sleeper_player.payload's keys)
    "active", "age", "birth_city", "birth_country", "birth_date", "birth_state", "college", "competitions",
    "depth_chart_order", "depth_chart_position", "espn_id", "fantasy_data_id", "fantasy_positions", "first_name",
    "full_name", "gsis_id", "hashtag", "height", "high_school", "injury_body_part", "injury_notes", "injury_start_date",
    "injury_status", "kalshi_id", "last_name", "metadata", "news_updated", "number", "oddsjam_id", "opta_id",
    "pandascore_id", "player_id", "player_shard", "position", "practice_description", "practice_participation",
    "rotowire_id", "rotoworld_id", "search_first_name", "search_full_name", "search_last_name", "search_rank",
    "sport", "sportradar_id", "stats_id", "status", "swish_id", "team", "team_abbr", "team_changed_at", "weight",
    "yahoo_id", "years_exp")
_POSITIONS = (("WR", 18), ("RB", 12), ("TE", 8), ("QB", 7), ("K", 2), ("P", 2), ("LS", 1), ("OL", 6), ("OT", 4),
              ("G", 3), ("C", 2), ("DL", 6), ("DE", 5), ("DT", 4), ("LB", 9), ("OLB", 2), ("ILB", 1), ("CB", 9),
              ("S", 6), ("DB", 3), ("FB", 1))
_TEAMS = ("ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
          "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS")
_SYL = ("an", "ber", "cal", "dar", "el", "fen", "gor", "hal", "is", "jo", "ka", "lin", "mar", "nor", "os", "pel",
        "quin", "ros", "sen", "tor", "ul", "van", "wes", "xan", "yor", "zek", "tre", "von", "mic", "dez")


def _name(rng: random.Random, lo: int, hi: int) -> str:
    return "".join(rng.choice(_SYL) for _ in range(rng.randint(lo, hi))).capitalize()


def synthetic_row(rng: random.Random, pid: str) -> dict:
    """One generated player: every field Sleeper sends, the null rates and lengths of the real payloads."""
    pos = rng.choices([p for p, _ in _POSITIONS], [w for _, w in _POSITIONS])[0]
    first, last = _name(rng, 1, 3), _name(rng, 2, 4)
    team = rng.choice(_TEAMS) if rng.random() < 0.22 else None
    maybe = lambda p, v: v if rng.random() < p else None  # noqa: E731 - a null rate
    meta = maybe(0.78, {"channel_id": str(rng.randrange(10**18, 10**19)), "rookie_year": str(rng.randint(2000, 2026)),
                        **({"genius_id": f"{rng.randrange(16**24):024x}"} if rng.random() < 0.35 else {})})
    return {
        "active": rng.random() < 0.77, "age": maybe(0.9, rng.randint(21, 40)), "birth_city": None, "birth_country": None,
        "birth_date": maybe(0.9, f"{rng.randint(1980, 2004)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"),
        "birth_state": None, "college": maybe(0.97, f"{_name(rng, 2, 3)} State"), "competitions": [],
        "depth_chart_order": maybe(0.13, rng.randint(1, 4)), "depth_chart_position": maybe(0.16, pos),
        "espn_id": maybe(0.55, rng.randint(10**5, 5 * 10**6)), "fantasy_data_id": maybe(0.83, rng.randint(1000, 99999)),
        "fantasy_positions": maybe(0.97, [pos]), "first_name": first, "full_name": f"{first} {last}",
        "gsis_id": maybe(0.32, f"00-00{rng.randint(10000, 99999)}"),
        "hashtag": f"#{first}{last}-NFL-{team or 'FA'}-{rng.randint(0, 99)}".lower(),
        "height": maybe(0.99, str(rng.randint(68, 80))), "high_school": maybe(0.89, f"{_name(rng, 2, 4)} High School "
                                                                                    f"({_name(rng, 2, 3)}, TX)"),
        "injury_body_part": maybe(0.055, rng.choice(("Knee", "Ankle", "Hamstring", "Shoulder", "Concussion"))),
        "injury_notes": maybe(0.008, "Day-to-day"), "injury_start_date": None,
        "injury_status": maybe(0.06, rng.choice(("Questionable", "Out", "IR", "PUP", "Doubtful"))),
        "kalshi_id": maybe(0.33, f"{rng.randrange(16**32):032x}"[:36]), "last_name": last, "metadata": meta,
        "news_updated": maybe(0.67, rng.randint(1_600_000_000_000, 1_760_000_000_000)),
        "number": maybe(0.93, rng.randint(0, 99)), "oddsjam_id": maybe(0.35, f"{rng.randrange(16**16):016X}"),
        "opta_id": None, "pandascore_id": None, "player_id": pid, "player_shard": f"{rng.randrange(16**3):03x}",
        "position": maybe(0.98, pos), "practice_description": None, "practice_participation": None,
        "rotowire_id": maybe(0.84, rng.randint(1000, 20000)), "rotoworld_id": maybe(0.17, rng.randint(1000, 20000)),
        "search_first_name": first.lower(), "search_full_name": f"{first}{last}".lower(),
        "search_last_name": last.lower(), "search_rank": maybe(0.98, rng.randint(1, 9_999_999)), "sport": "nfl",
        "sportradar_id": maybe(0.99, f"{rng.randrange(16**32):032x}"), "stats_id": maybe(0.24, rng.randint(10**5, 10**6)),
        "status": maybe(0.996, rng.choice(("Active", "Inactive", "Injured Reserve", "Practice Squad", "Retired"))),
        "swish_id": maybe(0.43, rng.randint(10**5, 2 * 10**6)), "team": team, "team_abbr": None, "team_changed_at": None,
        "weight": maybe(0.99, str(rng.randint(170, 340))), "yahoo_id": maybe(0.55, rng.randint(10**4, 4 * 10**4)),
        "years_exp": maybe(0.99, rng.randint(0, 18)),
    }


def synthetic_directory(fixture: dict, rows: int = DIRECTORY_ROWS, seed: int = 4) -> dict:
    """The fixture's rows (every other Sleeper field added: generated where no reader reads it, null where one does —
    the fields the API keeps, so the answers stay the fixture's) plus generated players up to ``rows``."""
    rng = random.Random(seed)
    kept = {"player_id", "full_name", "first_name", "last_name", "position", "fantasy_positions", "team", "status",
            "injury_status", "active", "gsis_id", "espn_id", "news_updated", "injury_body_part", "depth_chart_order"}
    out: dict[str, dict] = {}
    for pid, p in fixture.items():
        full = synthetic_row(rng, str(pid))
        out[pid] = {f: (p[f] if f in p else (None if f in kept else full[f])) for f in SLEEPER_FIELDS}
    n = 0
    while len(out) < rows:
        pid = str(9_000_000 + n)
        n += 1
        if pid not in out:
            out[pid] = synthetic_row(rng, pid)
    return out


def synthetic_fixtures(api: Path, cache_dir: str) -> tuple[Path, dict]:
    """A copy of the Sleeper fixtures with the synthetic directory in ``players_nfl.json``; (the directory, its stats)."""
    src = api / "tests" / "fixtures" / "sleeper"
    dst = Path(cache_dir) / "sleeper_fixtures"
    shutil.copytree(src, dst)
    d = synthetic_directory(json.loads((src / "players_nfl.json").read_text()))
    text = json.dumps(d)
    (dst / "players_nfl.json").write_text(text)
    return dst, {"rows": len(d), "fields": len(SLEEPER_FIELDS), "json_mb": round(len(text) / 1048576, 1)}
# ---- end IL-4


def _ps(args: list[str]) -> list[tuple[int, int, str]]:
    out = subprocess.run(["ps", "-o", "pid=,rss=,args=", *args], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2:
            rows.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) > 2 else ""))
    return rows


def rss(pid: int) -> tuple[float, float]:
    """(tree, server) in MB: the PO's sum (``uv run`` + its uvicorn children) and the uvicorn python alone."""
    me = _ps(["-p", str(pid)])
    kids = _ps(["--ppid", str(pid)])
    tree = sum(r for _, r, cmd in me + kids if "uvicorn" in cmd)
    server = max((r for _, r, cmd in kids if "uvicorn" in cmd), default=0)
    for kpid, _, _ in kids:                        # anything the server started (none today)
        tree += sum(r for _, r, _ in _ps(["--ppid", str(kpid)]))
    return round(tree / 1024, 1), round(server / 1024, 1)


def get(port: int, path: str, timeout: float = 240) -> tuple[int | str, float, bytes]:
    t0 = time.time()
    body = b""
    try:
        with urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=timeout) as r:
            body, code = r.read(), r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:  # noqa: BLE001
        code = str(e)[:40]
    return code, round(time.time() - t0, 1), body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=str(ROOT), help="the repository (default: this one)")
    ap.add_argument("--port", type=int, default=8752)
    ap.add_argument("--label", default="run")
    ap.add_argument("--plateau", action="store_true", help="add mfl:21861 (a fifth league) and the leagues again")
    ap.add_argument("--cycles", type=int, default=1, help="with --plateau: how many more rounds of the five leagues")
    ap.add_argument("--json", help="write the rows here")
    ap.add_argument("--synthetic-directory", action="store_true",
                    help="IL-4: Sleeper's player directory at its real size and shape (~12,200 players, 53 fields)")
    a = ap.parse_args(argv)
    api = Path(a.repo) / "api"
    cache_dir = tempfile.mkdtemp(prefix=f"measure_{a.label}_")
    log = open(Path(cache_dir) / "api.log", "w")
    env = fixture_env(api, cache_dir)
    directory = None
    if a.synthetic_directory:                                    # ---- IL-4: the fixtures, with the real-size directory
        fx, directory = synthetic_fixtures(Path(ROOT) / "api", cache_dir)
        env["LEAGUE_LAB_SLEEPER_FIXTURES"] = str(fx)
        print(f"synthetic directory: {directory}", file=sys.stderr, flush=True)
    proc = subprocess.Popen(["uv", "run", "uvicorn", "league_lab_api.main:app", "--port", str(a.port)], cwd=api,
                            env=env, stdout=log, stderr=subprocess.STDOUT)
    rows: list[dict] = []
    try:
        for _ in range(90):
            if get(a.port, "/api/health", 5)[0] == 200:
                break
            time.sleep(1)

        def mark(step: str, paths: list[str]) -> None:
            calls = [get(a.port, p)[:2] for p in paths]
            tree, server = rss(proc.pid)
            rows.append({"step": step, "tree_mb": tree, "server_mb": server, "calls": calls,
                         "seconds": round(sum(c[1] for c in calls), 1)})
            print(f"{tree:7.1f} MB tree {server:7.1f} MB server  {step}  {calls}", file=sys.stderr, flush=True)

        mark("start (health)", ["/api/health"])
        if a.synthetic_directory:                                # ---- IL-4: the directory alone, before any league
            mark("player directory (a search on demand)", [f"/api/search?league={TEST}&q=jo"])
        mark("scrubs", screens(SCRUBS, 2))
        mark("dynasty", screens(DYNASTY, 12))
        mark("test league (on demand, sleeper fixtures)", screens(TEST, 3))
        mark("mfl 70587 (fixtures)", screens(MFL, 8))
        mark("scrubs again (warm)", screens(SCRUBS, 2))
        mark("scrubs other teams", [f"/api/my-week?league={SCRUBS}&team={t}" for t in (1, 3, 4, 5, 6)]
             + [f"/api/trades/partners?league={SCRUBS}&team=6"])
        mark("players: a few cards", [f"/api/player/{g}?league={SCRUBS}&team=2"
                                      for g in ("00-0037840", "00-0036322", "00-0033873", "00-0040124")])
        mark("compare + week odds", [f"/api/research/compare?league={SCRUBS}&team=2&a=00-0037840&b=00-0040666",
                                     f"/api/league/week-odds?league={SCRUBS}"])
        if a.plateau:
            mark("mfl 21861 (fixtures, a fifth league)", screens(MFL2, 1))
            for n in range(1, a.cycles + 1):
                for name, lg, team in (("test league", TEST, 3), ("mfl 70587", MFL, 8), ("dynasty", DYNASTY, 12),
                                       ("scrubs", SCRUBS, 2), ("mfl 21861", MFL2, 1)):
                    mark(f"cycle {n}: {name}", screens(lg, team))
        code, _, body = get(a.port, "/api/status")
        memory = json.loads(body).get("memory") if code == 200 else {"status": code}
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(f"\n| step ({a.label}) | tree MB | server MB | seconds |\n|---|---|---|---|")
    for r in rows:
        print(f"| {r['step']} | {r['tree_mb']} | {r['server_mb']} | {r['seconds']} |")
    print(f"\nmemory (/api/status): {json.dumps(memory)}")
    if directory is not None:
        print(f"synthetic directory: {json.dumps(directory)}")
    if a.json:
        Path(a.json).write_text(json.dumps({"label": a.label, "rows": rows, "memory": memory, "directory": directory},
                                           indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
