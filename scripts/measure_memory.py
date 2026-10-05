"""The API's memory, league by league (INF-2, Wave I-J — the PO's measure.py from the night of the out-of-memory event,
cleaned up so every later wave re-measures the same way).

Starts the API (``uv run uvicorn`` from ``api/``) in the fixture environment — the database in the repository's
``.env`` (read only), Sleeper / MFL / ESPN from ``api/tests/fixtures``, the clock pinned to Saturday 2026-10-03 16:00
UTC — calls each league's screens in turn and reads the server's resident memory (RSS, from ``ps``) after each group.

    uv run python scripts/measure_memory.py --port 8752 --label after            # the PO's nine steps
    uv run python scripts/measure_memory.py --port 8752 --label plateau --plateau  # + mfl:21861 + the leagues again
    LEAGUE_LAB_CACHE_MB=60 uv run python scripts/measure_memory.py --plateau --cycles 2
    MALLOC_ARENA_MAX=2 uv run python scripts/measure_memory.py --label arena2      # what the Dockerfile's ENV does

Two figures per step: ``tree`` is the PO's (the ``uv run`` process plus the uvicorn python under it: Wave I-J's
before / after table is in this column), ``server`` is the python process alone (what Render meters: the image runs
uvicorn without uv). The run ends with ``/api/status``'s ``memory`` block (the caches' budget, region by region).
Prints a Markdown table; ``--json`` writes the rows. Needs Postgres up and ``api/.venv`` (``uv run`` makes it).
"""

from __future__ import annotations

import argparse
import json
import os
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
    a = ap.parse_args(argv)
    api = Path(a.repo) / "api"
    cache_dir = tempfile.mkdtemp(prefix=f"measure_{a.label}_")
    log = open(Path(cache_dir) / "api.log", "w")
    proc = subprocess.Popen(["uv", "run", "uvicorn", "league_lab_api.main:app", "--port", str(a.port)], cwd=api,
                            env=fixture_env(api, cache_dir), stdout=log, stderr=subprocess.STDOUT)
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
    if a.json:
        Path(a.json).write_text(json.dumps({"label": a.label, "rows": rows, "memory": memory}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
