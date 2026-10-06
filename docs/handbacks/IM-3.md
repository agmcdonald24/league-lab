# Hand-back — IM-3 (Wave I-M): open the doors — no password, browse without a league, safe to be public

**Branch** `dev/IM3` (from `main` `ab50682`), worktree `/home/claude/wt-im3`. Plan section: Wave I-M brief § IM-3.
The security write-up is `docs/SECURITY_PUBLIC.md` (what was checked, changed, left by severity).

## Done / not done (the package's numbered list)

1. **The gate as a switch — done.** `LEAGUE_LAB_GATE` = `open` | `password` (`auth.gate()`); unset or misspelt = the old
   rule; `open` ignores the password; `password` without a password keeps the door shut (a token signed with the
   empty-password key is refused — that was a real hole for that state). `/api/session` keeps its shape
   (`gate: true|false`, so `test_auth`'s exact asserts hold and the web follows it unchanged); `/api/status` adds
   `gate: "open"|"password"`.
2. **Rate limits — done.** `api/league_lab_api/ratelimit.py`, one pure-ASGI middleware; buckets read 300/min burst 150,
   heavy 20/min burst 20, write 60/min burst 30 (reasons in SECURITY_PUBLIC § 2); 429 + `Retry-After` + the JSON;
   `ErrorCard` kind `limited` with the calm line; `/api/health` and static files not limited; the client = HMAC of
   `CF-Connecting-IP` on Render (`RENDER` set), else the last `X-Forwarded-For` entry, else the peer; IPv6 by /64;
   bounded (5,000 per bucket, LRU after the free sweep); `GET /api/ratelimit` probe; `/api/status` → `ratelimit`.
3. **Security pass — done**, `docs/SECURITY_PUBLIC.md`: route inventory; CSRF (the Guard, `security.py`); SSRF
   (hostile links through every setup parameter, outbound recorded; MFL redirects pinned to MFL; dot usernames
   refused); error bodies (the 502's `cause` → log; non-ASCII tokens no longer 500); headers incl. a CSP tested on the
   built app with GA on (0 violations); private-league caches with the door open (re-tested); body limits; SQL params
   (read, nothing to change). Left: 2 Medium, 7 Low/Info (the table at the end of the doc).
4. **Reference league keys — done.** `api/league_lab_api/refleague.py` (+ a hook in `platforms.py`): `ref:ppr` /
   `ref:half` / `ref:std` on Stats, Trends, Matchups (defense, corners), Compare, a player's card and games, search,
   receivers, About, the record (the reference league's model record, Half PPR, no lineup record), `/api/ros` (points
   views); every ownership field absent; decision routes (`/api/my-week`, waivers, trades partners / lists /
   evaluate, team, league, `ros?view=lineup`, week-odds, scoring-check, events, a league's rosters) → 404
   `{"code": "needs_league", "error": "Open your league to see this."}`. `stats.py` / `research.py` / `player.py`
   untouched (the Router resolves the key).
5. **The web without a league — done.** Front door on `Leagues.svelte` (two lines, **Browse the lab** →
   `/players?league=ref:half`, **Open your league**, the record's line + About); the bar's "No league · Half PPR ▾"
   (PPR / Half PPR / Standard) + **Open your league**; My Team / Waivers / Trades (and Team, League, Calculator,
   Watchlist) show the invitation card; ref keys never stored (`prefs` untouched, App skips them); `?league=ref:half`
   in the URL; GA `platform: "none"`. DFS: no tab added (IM-5 owns it; its routes take no league, so it works).
   **Not done (IM-2's file)**: Players · Stats still shows the "Everyone / Yours / Free agents / Other teams" chips and
   the "Team in league" column for a reference key; the column reads "—" now (`research.ownerWord` with no owner field),
   not "free agent". The line IM-2 / the PO needs: in `Players.svelte`, wrap the `who` chips and the "Team in league"
   header + cell in `{#if !isRef(league)}` (`import { isRef } from "../lib/refleague"`).
6. **Search engines — done.** `web/index.html`: description, canonical `https://isuckatfantasy.io/`, Open Graph +
   `twitter:card`; `web/public/robots.txt` (allow `/`, disallow `/api/`). About's GA words checked: still true.
7. **Tests — done.** `api/tests/test_im3.py` 53 tests; `web/e2e/im3/fixtures.spec.ts` 4 tests × 2 projects (375 /
   1300), recordings `web/fixtures/im3/api_im3.json` (464 KB; lists trimmed to 60 rows).

## Files

Mine: `api/league_lab_api/{auth,main}.py`, new `ratelimit.py`, `refleague.py`, `security.py`; `web/src/App.svelte`,
`components/TopBar.svelte`, `routes/Leagues.svelte`, new `lib/refleague.ts`, `web/index.html`, `web/public/robots.txt`;
`api/tests/test_im3.py`, `web/e2e/im3/`, `web/fixtures/im3/`; docs `SECURITY_PUBLIC.md` (new), `WORDS.md` § "The open
door", `ANY_LEAGUE.md` § "Reference league keys", `CHANGELOG.md` (the Wave I-M heading, created).

Edits outside my files (each a few lines inside `IM-3` markers): `src/league_lab/platforms.py` (`REF_PREFIX`,
`REFERENCE`, `is_reference`, `provider_of` → `reference`, `check_key`, `Router.serving`, SHORT / LONG),
`src/league_lab/mfl_client.py` (redirect handler), `src/league_lab/sleeper_client.py` (dot usernames),
`api/tests/conftest.py` (`LEAGUE_LAB_RATE_LIMIT=off` for the suite), `web/src/lib/api.ts` (`get()` keeps the error's
JSON on `ApiError`), `web/src/lib/remote.svelte.ts` (`limited`, `needsleague` kinds), `web/src/components/ErrorCard.svelte`
(the needs-league invite), `web/src/lib/analytics.ts` (platform `none`), `web/src/lib/research.ts` (`ownerWord` "—").

## Schema in / out

No database change, nothing written. New answers: `GET /api/ratelimit`; `/api/status` `ratelimit`, `gate`; 429 / 403 /
413 bodies (`code` `rate_limited` / `cross_site` / `too_large`); 404 `needs_league`; the 502 `provider_down` body no
longer has `cause`.

## New environment variables (all optional)

`LEAGUE_LAB_GATE` (unset = old rule) · `LEAGUE_LAB_RATE_LIMIT` (on) · `LEAGUE_LAB_RATE_READ` (`300,150`) ·
`LEAGUE_LAB_RATE_HEAVY` (`20,20`) · `LEAGUE_LAB_RATE_WRITE` (`60,30`) · `LEAGUE_LAB_RATE_CLIENTS` (5000) ·
`LEAGUE_LAB_CLIENT_IP` (`auto` = `edge` on Render, `peer` elsewhere) · `LEAGUE_LAB_PROXY_HOPS` (1) ·
`LEAGUE_LAB_ALLOWED_HOSTS` (the three public hosts) · `LEAGUE_LAB_MAX_BODY_KB` (256) · `LEAGUE_LAB_MAX_UPLOAD_KB`
(2048) · `LEAGUE_LAB_CSP` (on). No new dependency.

## The PO lines I need

* `render.yaml`, under the service's `envVars`: `- key: LEAGUE_LAB_GATE` / `value: open` (the switch; `password` brings
  the beta back). Keep `LEAGUE_LAB_APP_PASSWORD` as it is (ignored while open; the way back). Optional, not needed:
  `LEAGUE_LAB_RATE_LIMIT` (on by default).
* `api/Dockerfile`: no change required. Recommended comment above `CMD`: "`--forwarded-allow-ips='*'` makes
  request.client the client-written first X-Forwarded-For hop: never key anything on it (ratelimit.py reads
  CF-Connecting-IP)".
* After the deploy: the two-line live check in SECURITY_PUBLIC § 2 (`/api/ratelimit`).
* IM-5's merge: its `POST /api/dfs/*` routes are already in the heavy bucket (`ratelimit.HEAVY_PREFIX`) and their
  bodies up to 2 MB (`security.body_limit`); no constant to wire.

## Evidence (commands run, results)

* `cd api && OMP_NUM_THREADS=1 PYTHONPATH=. uv run pytest -q tests/test_im3.py tests/test_auth.py tests/test_static.py`
  → **60 passed** (test_im3: 53 — the gate ×5, the limiter ×9, the Guard ×6, SSRF ×4, the private ESPN league with the
  door open, reference keys: 13 research routes without owners, the three scorings priced PPR > Half > Standard for 20+
  receivers, 10 decision routes + the trade POST / rosters → `needs_league`, `ref:bogus` 404, a house league keeps its
  owners, the league's shape).
* The limiter's memory (`test_memory_is_bounded`, tracemalloc): 20,000 addresses, all in debt in all three buckets →
  **4,970 held per bucket, 1,307 KB in all** (≈ 436 KB a bucket; a bucket keeps only clients in debt, so an ordinary
  day holds a few hundred).
* `/home/claude/waveIM/check_api.sh /home/claude/wt-im3` → `92 failed, 752 passed, 13 skipped, 41 deselected in
  995.03s`; **NEW failures**: `tests/test_ia2.py::test_partners_route_applies_both_rules`,
  `tests/test_ib0.py::test_one_lineup_total_on_every_screen[dynasty-overlay-off]` / `[dynasty-overlay-on]`,
  `tests/test_ii1.py::test_folk_package_is_not_promoted`, `tests/test_ii1.py::test_folk_package_on_the_clone_rosters`.
  **Not mine**: the same five fail with `main`'s `main.py`, `auth.py`, `platforms.py`, `mfl_client.py`,
  `sleeper_client.py` and `conftest.py` checked out in this worktree (10 failed / 3 passed on that selection, the same
  assertions: `market_note` None, Team 120.17 vs My Week 106.71 on the dynasty, the Folk package) — data-state
  failures missing from the known list. 3 known failures passed.
* `/home/claude/waveIM/check_root.sh /home/claude/wt-im3` → `4 failed, 1314 passed, 3 skipped`; **NEW failures: none**.
* `cd web && npm run lint && npm run build` clean; `uv run ruff check src app tests api` clean;
  `uv run python scripts/copy_standard.py --check` clean.
* `FIXTURES_PORT=8630 npx playwright test --config playwright.fixtures.config.ts e2e/im3` → 8 passed (fixtures);
  `IM3_LIVE=http://localhost:8753 …` (the fixture API serving web/dist, the real headers, GA on) → 4 passed, **0 CSP
  violations**, gtag.js requested. Screenshots looked at, 375 and 1300: the front door, Stats on `ref:half` with the
  picker, the invitation card (`web/e2e/.out/im3-*.png`; one fix made after looking: the picker's select was clipped
  at 1300).
* The whole fixtures e2e → **401 passed, 1 failed** (`[desktop] e2e/ib1 … the player's page keeps the tab bar and the
  search field; Back goes where you came from`: the URL kept `&q=st.+brown` for a moment); re-run alone → **1 passed**.
* Seen while running the fixture API (the PO's recipe): the web's `POST /api/usage` makes the server try an insert that
  fails with `UndefinedTable` (nothing written: `league_lab` has no `usage.events`); the availability overlay tried
  `site.api.espn.com` (refused by the sandbox's proxy) — the recipe does not set `LEAGUE_LAB_AVAILABILITY=off`.
  Playwright closing pages mid-request logs `ClientDisconnect` tracebacks from `POST /api/usage` (harmless).

## Limitations

* The client address on Render is decided from what Render's edge is known to do (Cloudflare, `CF-Connecting-IP`), not
  observed: verify with `/api/ratelimit` after the deploy (SECURITY_PUBLIC § 2).
* The Stats screen's "whose players" chips and "Team in league" column still show for a reference key (IM-2's file; the
  line is above). Season (`/ros`) works for points; its "Value to my lineup" view answers `needs_league` through the
  error card's invitation.
* `/api/record` for `ref:ppr` / `ref:std` is the Half PPR record, said in `scoring_note`.

## Next

The PO's merge (`render.yaml` `LEAGUE_LAB_GATE: open`), the live `/api/ratelimit` check, IM-2's two-line hide on Stats,
then Accounts' `client_ip` onto `ratelimit.scope_client` (IM-4).
