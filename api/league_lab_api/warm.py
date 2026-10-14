"""JB-3 (Wave J-B): warm the heavy routes once when a new publication is seen — in this process, never from the nightly.

On run #47 (2026-10-14, the publish at 08:24) the after-publish check read `pool 6/10 at peak, longest wait 6.623 s on
/api/leagues; CPU slots 4/4 at peak, longest wait 20.104 s on /api/team, 1 answered busy`: a new publication drops
every published cache (IS-4), so the first visitors after it each rebuild the same boards at once. Here, when
`db` sees a new publication (its watcher, or `/api/ready`'s probe), one pass asks this process's own address for the
house leagues' heavy screens, **one request at a time**, each only while at least two CPU slots are free (a visitor
is never queued behind the warm-up), bounded (MAX_ROUTES requests, BUDGET_S seconds, one pass at a time; a new
publication during a pass waits for the next one). The requests are ordinary GETs: they go through the rate limiter,
the slots and the caches like any visitor's; the answers are thrown away.

Where: `http://127.0.0.1:$PORT` (Render passes PORT; `LEAGUE_LAB_WARM_PORT` overrides). No port, or
`LEAGUE_LAB_WARM=off`: no warm-up (one log line says so). Writes nothing.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

MAX_ROUTES = 16
BUDGET_S = 240.0
REQUEST_TIMEOUT_S = 60.0
FREE_SLOTS = 2
HOUSE_LEAGUES_MAX = 2
_running = threading.Lock()
state: dict = {"passes": 0, "running": None, "last": None}


def _port() -> str | None:
    p = (os.environ.get("LEAGUE_LAB_WARM_PORT") or os.environ.get("PORT") or "").strip()
    return p if p.isdigit() else None


def enabled() -> bool:
    return os.environ.get("LEAGUE_LAB_WARM", "on").strip().lower() not in ("off", "0", "no") and _port() is not None


def _get(base: str, path: str):
    req = urllib.request.Request(base + path, headers={"Accept": "application/json", "X-League-Lab-Warm": "1"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
            body = r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        code, body = e.code, b""
    except (urllib.error.URLError, OSError):
        return 0, None, time.monotonic() - t0
    try:
        data = json.loads(body) if body else None
    except ValueError:
        data = None
    return code, data, time.monotonic() - t0


def _slots_free() -> bool:
    from . import ratelimit
    g = ratelimit.slots()
    return g.n <= 0 or (g.n - g.busy) >= FREE_SLOTS


def routes(base: str) -> list[str]:
    """The pass: the check's reference list, the house leagues, and per house league its first team's heavy screens."""
    out = ["/api/rankings?league=ref:half&position=RB&limit=30", "/api/leagues"]
    code, data, _ = _get(base, "/api/leagues")
    leagues = []
    if code == 200 and isinstance(data, (list, dict)):
        rows = data if isinstance(data, list) else (data.get("leagues") or [])
        leagues = [str(r.get("league_id")) for r in rows if isinstance(r, dict) and r.get("league_id")][:HOUSE_LEAGUES_MAX]
    for lg in leagues:
        code, teams, _ = _get(base, f"/api/leagues/{lg}/rosters")
        rid = teams[0].get("roster_id") if code == 200 and isinstance(teams, list) and teams else None
        if not isinstance(rid, int):
            continue
        out += [f"/api/my-week?league={lg}&team={rid}", f"/api/team?league={lg}&team={rid}",
                f"/api/trades/partners?league={lg}&team={rid}", f"/api/waivers?league={lg}&team={rid}"]
    return out[:MAX_ROUTES]


def run_pass(publication: str | None, base: str | None = None) -> dict:
    """One pass (blocking): the routes in order, each only while two slots are free; the report."""
    base = base or f"http://127.0.0.1:{_port()}"
    t0 = time.monotonic()
    done, skipped, failed = 0, 0, 0
    for path in routes(base):
        if time.monotonic() - t0 > BUDGET_S:
            skipped += 1
            continue
        waited = 0.0
        while not _slots_free() and waited < 20.0:            # visitors first
            time.sleep(0.5)
            waited += 0.5
        if not _slots_free():
            skipped += 1
            continue
        code, _, _ = _get(base, path)
        if code == 200:
            done += 1
        else:
            failed += 1
    rep = {"publication": publication, "warmed": done, "skipped": skipped, "failed": failed,
           "seconds": round(time.monotonic() - t0, 1)}
    state.update(passes=state["passes"] + 1, last=rep)
    log.warning("warm-up after publication %s: %d routes warmed, %d skipped, %d failed in %.1f s",
             publication, done, skipped, failed, rep["seconds"])
    return rep


def on_publication(new_id) -> None:
    """db.on_publication's callback: one pass in a daemon thread (never in the request that saw the publication)."""
    if not enabled():
        log.info("no warm-up after publication %s (LEAGUE_LAB_WARM off or no PORT)", new_id)
        return
    if not _running.acquire(blocking=False):
        return                                                 # a pass is running: it is warm enough

    def work():
        try:
            state["running"] = new_id
            time.sleep(1.0)                                    # let the request that saw it finish first
            run_pass(new_id)
        except Exception:  # noqa: BLE001 - a warm-up never fails anything
            log.exception("warm-up failed")
        finally:
            state["running"] = None
            _running.release()
    threading.Thread(target=work, name="league-lab-warm", daemon=True).start()


def install() -> None:
    from . import db
    if on_publication not in db.on_publication:
        db.on_publication.append(on_publication)


def status() -> dict:
    """/api/status `warm`: on or off, the pass running (its publication) and the last one's report."""
    return {"enabled": enabled(), "passes": state["passes"], "running": state["running"], "last": state["last"]}
