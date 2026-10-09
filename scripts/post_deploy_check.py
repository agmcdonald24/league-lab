#!/usr/bin/env python3
"""The post-deploy synthetic journey (IR-3, Wave I-R): read only, one line per check, exit 1 if any check fails.

    python3 scripts/post_deploy_check.py https://isuckatfantasy.io
    python3 scripts/post_deploy_check.py http://localhost:8963 --expect-version 3dfa01d35312
    python3 scripts/post_deploy_check.py <base-url> --trade 1389709692405551104:2:3:650:421,11792

Checks, in order (each line: ok / FAIL, the check, the HTTP status, the seconds, what it found):
  health     /api/health: 200, ok, the database "ok" (and the version, with --expect-version)
  ready      /api/ready: 200 — the published numbers can be served (else the reason the server gives, in its words)
  web app    "/": the page with the product's title
  rankings   /api/rankings?league=ref:half&position=RB: a sane top — at least 10 ranked, ranks 1..n in order, every one
             of the top 10 with a projection between 3 and 45 points, and nobody who cannot play (IR-1's
             `availability.cannot_play` / `cannot_play`, or a report status of Out, IR, PUP, NFI or Suspended)
  trade      POST /api/trades/evaluate, a known house-league trade (default: League of Scrubs, MacZaddy gives Nick Folk
             to Run Bijan Run for Matthew Stafford and Will Reichard — the review's case): 200, the verdict present,
             every primary number reconciles (after − before = the change, this week and over the window, both teams;
             the weekly numbers sum to the window's), and the verdict's words carry those same changes
  reversed   the same trade from the partner's side: each team's change is the same number
Writes nothing anywhere (the trade route only reads). Needs python3 (standard library only); no password unless the
server has its gate on (--password, or POST_DEPLOY_PASSWORD). Exit: 0 all ok · 1 a check failed · 2 usage.
A trade whose players have since moved answers 400 "on X's roster, not Y's": pass a current one with --trade.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

DEFAULT_TRADE = "1389709692405551104:2:3:650:421,11792"
OUT = {"OUT", "IR", "PUP", "PUP-R", "PUP-P", "NFI", "NFI-R", "SUS", "SUSPENDED", "INJURED RESERVE", "RESERVE"}
TOL = 0.06          # the API rounds each total to 0.01; a difference of two rounded totals is within 0.02 of the change


class Journey:
    def __init__(self, base: str, timeout: float, token: str | None):
        self.base, self.timeout, self.token = base.rstrip("/"), timeout, token
        self.fails = 0

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, float, object]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                code, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            return 0, time.monotonic() - t0, f"no answer: {getattr(e, 'reason', e)}"
        secs = time.monotonic() - t0
        text = raw.decode("utf-8", "replace")
        try:
            return code, secs, json.loads(text)
        except ValueError:
            return code, secs, text

    def line(self, ok: bool, label: str, code: int, secs: float, text: str) -> bool:
        if not ok:
            self.fails += 1
        print(f"{'ok' if ok else 'FAIL':<4} {label:<10} {code:>3} {secs:5.2f}s  {text}", flush=True)
        return ok


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def cannot_play(row: dict) -> str | None:
    """Why a ranked row is someone who cannot play, or None."""
    av = row.get("availability")
    if isinstance(av, dict) and av.get("cannot_play"):
        return str(av.get("status") or av.get("code") or "cannot play")
    if row.get("cannot_play"):
        return "cannot play"
    status = str(row.get("report_status") or "").strip().upper()
    return status if status in OUT else None


def check_rankings(b: object) -> tuple[bool, str]:
    if not isinstance(b, dict) or not isinstance(b.get("rows"), list):
        return False, "no rows in the answer"
    rows = b["rows"]
    if len(rows) < 10:
        return False, f"only {len(rows)} ranked"
    ranks = [r.get("rank") for r in rows]
    if ranks != list(range(1, len(rows) + 1)):
        return False, f"ranks out of order: {ranks[:12]}"
    for r in rows[:10]:
        p = _num(r.get("proj_points"))
        if p is None or not 3 <= p <= 45:
            return False, f"#{r.get('rank')} {r.get('player_name')}: projection {r.get('proj_points')!r} is not a number from 3 to 45"
    out = [f"#{r.get('rank')} {r.get('player_name')} ({cannot_play(r)})" for r in rows if cannot_play(r)]
    if out:
        return False, "ranked though they cannot play: " + ", ".join(out[:5])
    top = rows[0]
    return True, (f"week {b.get('week')} of {b.get('season')}: {len(rows)} ranked, #1 {top.get('player_name')} "
                  f"{top.get('proj_points')}, nobody ranked who cannot play")


def _signed(x: float) -> str:
    return f"{x:+.1f}"


def check_trade(b: object) -> tuple[bool, str, dict | None]:
    if not isinstance(b, dict):
        return False, "not a JSON answer", None
    for k in ("before", "after", "fit", "verdict"):
        if k not in b:
            return False, f"no `{k}` in the answer (the decision object changed? update this check)", None
    if not isinstance(b["verdict"], str) or not b["verdict"].strip():
        return False, "no verdict in words", None
    fit, before, after = b["fit"], b["before"], b["after"]
    changes: dict = {}
    for side in ("mine", "theirs"):
        bw, aw = before[side].get("by_week") or [], after[side].get("by_week") or []
        if not bw or len(bw) != len(aw):
            return False, f"{side}: the weekly numbers are missing or uneven ({len(bw)} vs {len(aw)})", None
        for when, key in (("before", before), ("after", after)):
            s, h = sum(key[side]["by_week"]), _num(key[side].get("horizon"))
            if h is None or abs(s - h) > TOL * len(bw):
                return False, f"{side} {when}: the weeks sum to {s:.2f}, the window says {h}", None
        for span, total in (("this_week", "this_week"), ("window", "horizon")):
            d = _num(after[side].get(total)) - _num(before[side].get(total))
            f = _num(fit[span][side])
            if f is None or abs(d - f) > TOL:
                return False, f"{side} {span}: after − before = {d:+.2f}, the change shown is {fit[span][side]}", None
            changes[(side, span)] = f
    words = " ".join(str(b.get(k) or "") for k in ("verdict", "headline")) + " " + str(fit.get("words") or "")
    # PO (Wave I-T): every sentence of the decision writes the true minus sign since IT-1 ("−0.3", U+2212); the check
    # looked for "-0.3" and failed both trade lines on a correct answer (seen on the pooler check before delivery).
    words = words.replace("\u2212", "-")
    missing = [_signed(v) for v in changes.values() if _signed(v) not in words]
    if missing:
        return False, f"the words do not carry the changes {', '.join(missing)}: {b['verdict'][:120]}", changes
    return True, (f"yours {_signed(changes[('mine', 'this_week')])} this week, {_signed(changes[('mine', 'window')])} "
                  f"over {b.get('window_label') or 'the window'}; theirs {_signed(changes[('theirs', 'this_week')])} / "
                  f"{_signed(changes[('theirs', 'window')])}; reconciles, the verdict carries them"), changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="the server's address, e.g. https://isuckatfantasy.io")
    ap.add_argument("--trade", default=os.environ.get("POST_DEPLOY_TRADE", DEFAULT_TRADE),
                    help="league:team:partner:give ids:get ids (comma-separated ids), default the review's Folk case")
    ap.add_argument("--expect-version", default=os.environ.get("POST_DEPLOY_VERSION", ""),
                    help="the version /api/health must report (a prefix of it is enough: a short commit)")
    ap.add_argument("--password", default=os.environ.get("POST_DEPLOY_PASSWORD", ""),
                    help="only when the server's gate is on (never printed)")
    ap.add_argument("--expect-publication", default=os.environ.get("POST_DEPLOY_PUBLICATION", ""),
                    help="IT-4: wait until /api/ready names this publication id before checking (after a nightly publish)")
    ap.add_argument("--wait", type=float, default=float(os.environ.get("POST_DEPLOY_WAIT", "150")),
                    help="the most seconds to wait for --expect-publication (default 150: /api/ready keeps an answer 60 s)")
    ap.add_argument("--timeout", type=float, default=float(os.environ.get("POST_DEPLOY_TIMEOUT", "90")))
    a = ap.parse_args(argv)
    try:
        league, team, partner, give, get = a.trade.split(":")
        team_i, partner_i = int(team), int(partner)
        give_l, get_l = [x for x in give.split(",") if x], [x for x in get.split(",") if x]
        assert league and give_l and get_l
    except (ValueError, AssertionError):
        print("--trade is league:team:partner:give ids:get ids, e.g. " + DEFAULT_TRADE, file=sys.stderr)
        return 2

    j = Journey(a.base, a.timeout, None)
    print(f"post-deploy check: {j.base}")
    if a.password:
        code, secs, b = j.call("POST", "/api/login", {"password": a.password})
        if j.line(code == 200 and isinstance(b, dict) and bool(b.get("token")), "login", code, secs,
                  "signed in" if code == 200 else "refused: the password"):
            j.token = b["token"]

    # ---- IT-4: after a publish, check the new publication, not the cached one (bounded: --wait seconds)
    if a.expect_publication:
        t0, seen = time.monotonic(), None
        while True:
            code, secs, b = j.call("GET", "/api/ready")
            pub = ((b.get("checks") or {}).get("publication") or {}) if isinstance(b, dict) else {}
            seen = pub.get("id") if isinstance(pub, dict) else None
            if seen == a.expect_publication or time.monotonic() - t0 >= a.wait:
                break
            time.sleep(5)
        j.line(seen == a.expect_publication, "picked up", code, time.monotonic() - t0,
               f"publication {seen} is served" if seen == a.expect_publication
               else f"the server still names {seen or 'no publication'} after {a.wait:.0f} s (expected {a.expect_publication})")
    # ---- end IT-4

    code, secs, b = j.call("GET", "/api/health")
    ok = code == 200 and isinstance(b, dict) and b.get("ok") is True and b.get("database") == "ok"
    ver_ok = not a.expect_version or (isinstance(b, dict) and str(b.get("version", "")).startswith(a.expect_version[:12]))
    j.line(ok and ver_ok, "health", code, secs,
           (f"version {b.get('version')}, as_of {b.get('as_of')}, database {b.get('database')}, stale {b.get('stale')}"
            + ("" if ver_ok else f" — expected version {a.expect_version}")) if isinstance(b, dict) else str(b)[:160])

    code, secs, b = j.call("GET", "/api/ready")
    if isinstance(b, dict):
        c = b.get("checks") or {}
        pub = (c.get("publication") or {}).get("id") if isinstance(c.get("publication"), dict) else None
        wk = c.get("week") or {}
        text = (f"publication {pub or 'not recorded'}, as_of {c.get('as_of')}, week {wk.get('week')} of {wk.get('season')}"
                if b.get("ready") else f"not ready ({b.get('code')}): {b.get('reason')}")
    else:
        text = str(b)[:160]
    j.line(code == 200 and isinstance(b, dict) and b.get("ready") is True, "ready", code, secs, text)

    code, secs, b = j.call("GET", "/")
    ok = code == 200 and isinstance(b, str) and re.search(r"<title>[^<]*isuckatfantasy", b) is not None
    j.line(ok, "web app", code, secs, "the page is served" if ok else "not the web app's page")

    code, secs, b = j.call("GET", "/api/rankings?league=ref:half&position=RB&limit=30")
    ok, text = check_rankings(b) if code == 200 else (False, (b.get("error") if isinstance(b, dict) else str(b))[:160])
    j.line(ok, "rankings", code, secs, text)

    body = {"league": league, "team": team_i, "partner": partner_i, "give": give_l, "get": get_l}
    code, secs, b = j.call("POST", "/api/trades/evaluate", body)
    ok, text, fwd = check_trade(b) if code == 200 else (False, (b.get("error") if isinstance(b, dict) else str(b))[:200], None)
    j.line(ok, "trade", code, secs, text)

    if fwd is not None:
        rbody = {"league": league, "team": partner_i, "partner": team_i, "give": get_l, "get": give_l}
        code, secs, b = j.call("POST", "/api/trades/evaluate", rbody)
        rok, rtext, rev = check_trade(b) if code == 200 else (False, str(b)[:160], None)
        if rok and rev is not None:
            bad = [f"{span}: {fwd[(s1, span)]:+.2f} vs {rev[(s2, span)]:+.2f}" for span in ("this_week", "window")
                   for s1, s2 in (("mine", "theirs"), ("theirs", "mine")) if abs(fwd[(s1, span)] - rev[(s2, span)]) > TOL]
            rok, rtext = (not bad, "each team's change is the same from either side" if not bad
                          else "a team's change differs by side: " + "; ".join(bad))
        j.line(rok, "reversed", code, secs, rtext)
    else:
        j.line(False, "reversed", 0, 0.0, "not run: the trade check failed")

    print("All checks passed." if j.fails == 0 else f"FAILED: {j.fails} check(s).")
    return 0 if j.fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
