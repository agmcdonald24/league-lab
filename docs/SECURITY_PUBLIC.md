# Opening the door: the security pass before isuckatfantasy goes public (Wave I-M, IM-3, 2026-10-06)

Until now every `/api/` route sat behind the beta password (`require_auth`, `auth.py`). Andrew: "lets lose the
password". This is what was checked before the door opens, what changed, and what is left — each left item with its
severity (**High**: fix before opening; **Medium**: fix soon after; **Low**: note it). Tests: `api/tests/test_im3.py`
(53) and `web/e2e/im3/fixtures.spec.ts` (the built app under the real headers: `IM3_LIVE=http://localhost:8753`).

**Verdict: nothing High is left.** The door can open with `LEAGUE_LAB_GATE: open`. Two Medium items (the client
address on Render must be verified live once — § 2; the provider budgets are global, not per visitor — § 1) and a
handful of Low ones are listed at the end. **§ 11** is the fix round after the independent review of the merged tree
(seven findings, all fixed).

## 1. The gate, and every route with the door open

`LEAGUE_LAB_GATE` = `open` | `password` (`auth.gate()`). Unset or misspelt: the old rule (password when
`LEAGUE_LAB_APP_PASSWORD` is set). `open` ignores the password: no sign-in screen, no 401, `/api/session` →
`{"gate": false, "signed_in": true}` (the same shape as before, so the web follows it unchanged). `password` brings the
beta password back with no code change. `password` **with no password set keeps the door shut** — before this change the
token key would have been derived from an empty password (`sha256("league-lab-api|")`, a public value), so a forged
token would have passed; `valid()` now refuses every token in that state (tested).

Who can call what, with the door open (everyone, anonymously, unless the route says otherwise):

| Route | Cost to us | Writes | Bucket |
|---|---|---|---|
| `GET /api/health` | one query an hour | — | not limited |
| `GET /api/session`, `/api/providers`, `/api/status`, `/api/ratelimit` | in memory / cached | — | read |
| research: `/api/players`, `/trends`, `/matchups/*`, `/compare`, `/player/{id}` (+ `/games`), `/search`, `/receivers`, `/about`, `/record`, `/ros` | cached SQL + pricing (10 min memo, the memory budget) | — | read |
| setup: `/api/leagues?username= | sleeper= | mfl= | mfl_search= | espn= | yahoo= | yahoo_me=`, `/api/leagues/{id}/rosters` | **outbound calls to the provider** (each client's token bucket: Sleeper's, MFL's) | — | heavy |
| decisions: `/api/my-week`, `/waivers`, `/trades/partners`, `/trades/lists`, `/team`, `/league`, `/league/week-odds`, `/league/scoring-check`, `/ros?view=lineup`, `POST /api/trades/evaluate` | lineup solves, provider reads, 1–3 s cold | — | heavy |
| `GET /api/usage/summary`, `/api/events` (the PO's QA) | uncached queries | — | heavy |
| `POST /api/usage` | a queued insert (dropped when the queue is full) | one `usage.events` row per screen view (per-session 1/s) | write |
| `POST /api/login`, `/api/logout` | — | a cookie | write |
| `POST /api/espn/connect`, `/disconnect` (off unless `LEAGUE_LAB_ESPN_PRIVATE=on`) | — | a sealed cookie (the account's row when signed in) | write |
| `GET /api/yahoo/connect`, `/callback`, `/leagues`; `POST /disconnect` | a token exchange with Yahoo | a sealed cookie | heavy / write |
| `/api/account/*` (IM-4; off until the accounts switch) | database | the account's rows | write (reads: read) |
| `POST /api/dfs/*` (IM-5) | parse + solve | nothing stored | heavy |

What a stranger can write: usage rows (bounded per session and per address; 180 days' retention), and his own
cookies. Nothing else: the database role is read-only apart from `usage` and `accounts`.

**Left (Medium): the provider budgets are global.** Sleeper's and MFL's token buckets (`LEAGUE_LAB_SLEEPER_PER_MIN`,
MFL's) are one per process: a visitor who opens many unknown leagues spends everyone's budget (the heavy bucket bounds
one address to 20 at once, then one every 3 s; many addresses are not bounded). A spent budget answers "busy, try again
in a minute" — the house leagues and every cached league keep working. A per-address share of the provider budget is
the fix if it happens.

## 2. Rate limits (`api/league_lab_api/ratelimit.py`)

One pure-ASGI middleware ahead of every route; `/api/health` and the web app's files are never limited.

| Bucket | Per minute | At once | Why these numbers |
|---|---|---|---|
| read | 300 | 150 | the cheap answers (session, status, search, providers, the account): one screen asks 2–8 things and the web keeps its answers 5 minutes, so a person tapping a new screen every second for a minute stays under it, and ten people behind one address using the app normally do too |
| research | 60 | 40 | (review fix) the answers that aggregate or price on request — Stats and its CSV, Trends, Matchups, Compare, a player's card and games, Receivers, About, the record, Season's points views, DFS projections — cost 0.3–1.2 s of CPU cold; a person opening Stats, "Show all", the CSV, a dozen player cards (two calls each) and a few filters in one minute stays under 40; one a second after that |
| heavy | 20 | 20 | every decision screen of four leagues opened in a row, then one every 3 seconds — each can cost a provider call or 1–3 s of the one CPU |
| write | 60 | 30 | a usage count per screen view, sign-ins and account saves; no one taps 30 screens in a second |

Refused: **429** `{"error": "Too many requests from this connection. Try again in N seconds.", "code": "rate_limited",
"retry_after_s": N, "bucket": …}` + `Retry-After: N`; the web shows the line through `ErrorCard` (kind `limited`).
Switches: `LEAGUE_LAB_RATE_LIMIT=off`; `LEAGUE_LAB_RATE_READ` / `_RESEARCH` / `_HEAVY` / `_WRITE` = `"<per minute>,<burst>"`;
`LEAGUE_LAB_RATE_HEAVY_48` / `_WRITE_48` (an IPv6 /48); `LEAGUE_LAB_RATE_HEAVY_ALL` / `_RESEARCH_ALL` / `_WRITE_ALL`
(every client together); `LEAGUE_LAB_RATE_CLIENTS` (default 5,000 per bucket); `LEAGUE_LAB_CLIENT_IP`;
`LEAGUE_LAB_PROXY_HOPS`; `LEAGUE_LAB_CPU_SLOTS` / `LEAGUE_LAB_CPU_WAIT_S`. The full table is § 11.
`/api/status` → `ratelimit` (buckets, clients held, refusals, evictions, how requests were keyed).

**Memory.** Each bucket keeps one number per client — the moment its bucket is full again (the token bucket in its
"virtual scheduling" form) — keyed by a 60-bit HMAC of the address with a random per-process key; a client whose bucket
is full again is the same as one never seen and is dropped at no cost, so only clients in debt are held. Past 5,000 in a
bucket the full ones go, then the least recently seen (an LRU). Measured (`test_memory_is_bounded`, tracemalloc):
**20,000 addresses, each in debt in all three buckets at once → 4,970 held per bucket, 1,308 KB in all (≈ 436 KB a
bucket)**; an ordinary day holds a few hundred clients.

**Who "a client" is — decided for Render.** The domain's Cloudflare records are DNS-only, but Render's own edge is
Cloudflare (Render's answers carry `cf-ray`), so every request passes exactly one Cloudflare, which **sets
`CF-Connecting-IP` to the address that connected and overwrites a value the client sent**. On Render (`RENDER` is set in
every Render service's environment) the limiter keys on that header; without it, on the **last** `X-Forwarded-For`
entry (the one the proxy appended — the client controls only the left part); without either, the socket's peer. Off
Render (local runs, tests) only the peer is used: nothing in front writes those headers, so a client could. IPv6 counts
by its /64 (one subscriber's block — otherwise one machine has 2^64 fresh buckets).

Found on the way, **important**: the image runs `uvicorn --proxy-headers --forwarded-allow-ips='*'`, which makes
`request.client.host` the **leftmost** `X-Forwarded-For` entry — written by the client. Anything keyed on
`request.client` or on the first `X-Forwarded-For` hop is spoofable on Render; the limiter reads neither. (Accounts'
`client_ip` — IM-4's file — takes the first hop: its per-address limits are spoofable; its per-email and daily limits
are not. **Low**, said to the PO.)

**Verify it live (Medium until done, 2 minutes after the deploy)** — the probe never shows an address:

```bash
curl -s -H 'CF-Connecting-IP: 203.0.113.9' -H 'X-Forwarded-For: 203.0.113.9' https://isuckatfantasy.io/api/ratelimit
# want: "keyed_by": "cf-connecting-ip", "test_address_used": false   (Cloudflare replaced the header)
```

Then open `/api/ratelimit` on the phone (mobile data) and on a laptop (Wi-Fi): two different `bucket_tag`s = two
buckets. If `keyed_by` says `x-forwarded-for` or `peer`, or both devices show one tag, set `LEAGUE_LAB_CLIENT_IP`
(`x-forwarded-for` with `LEAGUE_LAB_PROXY_HOPS=2`, or `true-client-ip`) on Render — no deploy — or switch the limiter
off with `LEAGUE_LAB_RATE_LIMIT=off` while it is sorted out. `test_address_used: true` means the header was taken from
the client: change `LEAGUE_LAB_CLIENT_IP` at once.

Tested: a burst is refused and the bucket refills on a fake clock; `Retry-After` in whole seconds; a new
`X-Forwarded-For` (and on Render a new left part) never buys a fresh bucket; another `CF-Connecting-IP` is another
client; an IPv6 /64 is one client; the switch and the numbers by env; the memory bound.

## 3. Cross-site writes (CSRF) — `api/league_lab_api/security.py`

Cookies that authenticate: `ll_auth` (the beta password), `ll_session` (accounts), `ll_espn`, `ll_yahoo` (sealed
provider sessions), `ll_usage`. All SameSite=Lax, HttpOnly. SameSite alone is not the answer (a same-site sibling, an
old browser), so the Guard refuses — before any route runs — every POST / PUT / PATCH / DELETE to `/api/` whose
`Origin` is not this request's own `Host` nor one of `LEAGUE_LAB_ALLOWED_HOSTS` (default `isuckatfantasy.io`,
`www.isuckatfantasy.io`, `league-lab.onrender.com`), whose `Origin` is `null`, or that has no `Origin` but
`Sec-Fetch-Site: cross-site`: **403** `{"code": "cross_site"}`. A request with neither header is not a browser's
cross-site request (curl, the smoke script) and passes. Look-alike hosts (`isuckatfantasy.io.evil.example`) are other
hosts. GETs are never refused for their origin (a link from anywhere opens the app) and none of them writes — the only
GETs with an effect are Yahoo's connect / callback, which set cookies bound to a signed `state` (IK-2). IM-4 is adding
an `Origin` check inside the account routes as well (its package; not verified here). Tested on usage, the trade POST, ESPN connect, logout, login, the account
PUT / DELETE and Yahoo disconnect.

## 4. SSRF — what a user-supplied link can make us call

Every outbound client has a fixed https base (operator env overrides only): Sleeper `api.sleeper.app`, MFL
`api.myfantasyleague.com` (+ the league's `www4N` host), ESPN `lm-api-reads.fantasy.espn.com`, ESPN news / injuries
`site.api.espn.com`, Yahoo `fantasysports.yahooapis.com` / `api.login.yahoo.com`, the id table on
`raw.githubusercontent.com`. What a user supplies becomes an **id** checked by a regex before it reaches a path (Sleeper
digits and usernames, MFL digits, ESPN digits, Yahoo `game.l.id`); a link's host is never used.

* MFL: `parse_link` keeps only the league id; a remembered host must match `^https://(api|www\d{1,3})\.myfantasyleague\.com$`
  (from the redirect's final URL, the league's `baseURL`, the search's `homeURL`). **Changed**: urllib followed a
  redirect to any host; MFL's client now follows redirects only to `https://*.myfantasyleague.com` (port 443) and
  refuses the rest before a request leaves (`mfl_client._MFLRedirects`).
* Sleeper: a username of dots (`.`, `..`) reached the URL path as `/user/..`; **refused now** (`check_username`).
* Tested: ten hostile links (cloud metadata `169.254.169.254`, `127.0.0.1:5432`, `localhost`, `[::1]`, look-alike and
  userinfo hosts, `file:` / `gopher:`) through every setup parameter, with every outbound request recorded and refused
  in the test: only the platforms' own hosts were asked; MFL never remembers a foreign host; its redirect rule.

**Left (Low)**: the other clients (Sleeper, ESPN, Yahoo, news, injuries) still follow redirects with urllib's defaults —
only their own fixed hosts could send one.

## 5. Error bodies

The 500 handler never sends an exception's text (IH-1). **Changed**: the 502 "did not answer" answer carried `cause`
(a provider URL and the exception's text); it goes to the server log now, not to the visitor. A token with non-ASCII
parts raised a 500 in `auth.valid` (`int('²')`, `compare_digest` on non-ASCII); refused cleanly now. FastAPI's 422
echoes the request's own input back to the same requester (not a leak to anyone else: **Low**, left).

## 6. Response headers

On every answer (a 429 / 403 / 413 included): `X-Content-Type-Options: nosniff`, `Referrer-Policy:
strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, `Permissions-Policy: camera=(), microphone=(), geolocation=(),
payment=(), usb=()` (WebAuthn is left alone for IM-4's passkeys), `Strict-Transport-Security: max-age=31536000` on
https, and:

```
default-src 'self'; script-src 'self' 'sha256-<the inline prefetch in index.html>' https://*.googletagmanager.com;
style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://*.google-analytics.com
https://*.analytics.google.com https://*.googletagmanager.com; font-src 'self' data:; manifest-src 'self';
worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

The inline script's hash is computed from the served `index.html` (cached by its mtime), so an edit to the prefetch
script never breaks the page. `style-src 'unsafe-inline'`: Svelte's `style=""` attributes (bar widths, team colours).
`img-src https:`: headshots and logos come from the NFL's and the platforms' CDNs. Tested: the built app on the fixture
API with GA switched on — every screen of the e2e walk, **zero CSP violations**, gtag.js requested (not blocked).
`LEAGUE_LAB_CSP=off` drops the CSP alone (never needed). **Low**: `/api/docs` (Swagger UI, scripts from
cdn.jsdelivr.net) renders blank under the CSP; `/api/openapi.json` still answers.

## 7. Caches and private leagues, with the door open

The in-process caches are per league (and per scoring), shared by every visitor — fine for public data. A private ESPN
league is read with one visitor's cookies: IK-1's `require_access` runs in `require_auth` → `provider_gate` for every
`espn:` key **before** any route or memo answers, and that dependency still runs with the door open (`auth.valid` is
true, `provider_gate` is called after it). Re-verified: `test_private_espn_league_stays_gated_with_the_door_open`
(`LEAGUE_LAB_GATE=open` with a password set: My Week, Waivers, Stats and Trends all answer `espn_league_private` for a
visitor without the cookies). Yahoo's caches are per manager (IK-2). The JSON answers are `Cache-Control: private` (no
shared cache stores them; Cloudflare does not cache JSON by default), the session / account / provider answers
`no-store`.

## 8. Request sizes

`LEAGUE_LAB_MAX_BODY_KB` (default 256) on `/api/` writes, `LEAGUE_LAB_MAX_UPLOAD_KB` (default 2,048) under `/api/dfs/`
(IM-5's salary file; its parser caps at 1 MB). A declared `Content-Length` over the bound → **413** at once; a chunked
body is read up to the bound and refused past it, never held whole. The largest body the app sends today is the saved
leagues (≤ 51 × 2 KB). Header and URL sizes are uvicorn's (h11) limits.

## 9. Query parameters that reach SQL

Read every route's path to the database: `position` → `_positions()` against a fixed list (then the column list comes
from `POSITION_COLUMNS`), `sort` / `dir` → checked against the frame's columns and `asc|desc` and applied in pandas,
`window` / `basis` / `who` / `season_type` / `view` → fixed sets, `weeks` → `parse_weeks`, `nfl` / `q` → pandas filters,
`limit` / `offset` / `season` / `team` → ints (FastAPI), every value in SQL is a `%s` parameter; the f-strings in SQL
interpolate module constants only. Nothing to change.

## 10. Browse without a league

`ref:ppr` / `ref:half` / `ref:std` (`refleague.py`) answer the research routes with every ownership field taken out
(`OWNERSHIP`, at any depth) and the decision routes with 404 `needs_league` — tested on every route; a house league keeps
its owners. A reference key is never stored on the device.

## 11. The fix round after the independent review (2026-10-06)

| # | Finding (severity) | Fixed by |
|---|---|---|
| 1 | `view=LINEUP` escaped the heavy bucket and the `ref:` rule (Medium) | `ratelimit.norm` / `lineup_view`: one spelling (stripped, lower-cased; `+` / `%20` decoded; any of a repeated `view=`) for the bucket, `needs_league` and `ondemand.ros`; `outlook` / `upgrades` (they solve a roster's lineups too) are heavy and need a league. Checked the same class elsewhere: the league key is stripped / lower-cased in `is_reference`; the router is case-sensitive (`/API/…` and `//api/…` reach the web app, never a route); a trailing slash is a 307 to the classified path; parameter names are case-sensitive in FastAPI (an unknown name is ignored, not routed) |
| 2 | The read bucket did not match what research costs (Medium) | the `research` bucket (60 a minute, 40 at once — § 2); a research request for a league this process has not answered in the last 10 minutes (an on-demand league: provider fan-out) is charged to `heavy` (`ratelimit.Seen`: any client, 5,000 leagues, oldest first); **CPU slots**: at most `LEAGUE_LAB_CPU_SLOTS` (4) research / heavy requests in flight across every client, the rest wait — holding no worker thread — up to 20 s, then 503 "busy"; a slot is given back when the answer starts (a slow reader never holds one). Four: one process on a fraction of a core gains nothing from more CPU work at once, and four keeps provider waits overlapping |
| 3 | IPv6 rotation inside a /48 (Medium) | a second key for `heavy` (60 a minute, 60 at once) and `write` (180, 90) per IPv6 /48 (IPv4: the address is already the key); a ceiling for every client together — heavy 300 / 150, research 1,200 / 600, write 3,000 / 1,000 — answered 503 "busy" (the web's "Busy right now. Try again in a minute."). Memory, measured: IPv4, 20,000 addresses in debt in all four buckets → 1,741 KB; IPv6, each in its own /48 → 2,606 KB (four buckets + two /48 tables, 4,970 held each) |
| 4 | The Sleeper client's answer cache grew without end (Medium) | `sleeper_client.prune_cache`: an expired answer is kept one hour past its expiry (what "busy" or a provider failure serves instead of an error), then dropped at the next insert; past `LEAGUE_LAB_PROVIDER_CACHE_MAX` (1,500 entries ≈ 500 leagues) the least recently fetched go; the player directory is never dropped by count. **MFL** and **ESPN** had the same cache: the same rule, and their read-time maps are capped too. **Yahoo**: already bounded (400 entries, expired first). **The injury feed**: one answer. **The news feed**: one entry per ESPN athlete asked for — an ESPN id comes only from our id table (a request names a player id, never an ESPN id), so bounded by the players who have one (a few thousand, a few KB each) |
| 5 | Usage rows: a fresh cookie per request bought a row (Medium) | `ratelimit.usage_ceiling`: 1,200 rows an hour in all (≈ 30 times a Sunday's busiest real hour: ~50 managers × 20 screens a day) and 120 an hour per visitor (`client_group`); a refused count answers 204 like an accepted one. At the ceiling: ~29,000 rows a day, ~4 MB |
| 6 | `/api/docs` and `/api/openapi.json` open in both modes (Low) | off unless `LEAGUE_LAB_API_DOCS=on` |
| 7 | `md.ts` took `//evil.example` and `/\evil.example` for in-app links; provider text flows into the sentences (Low) | an in-app path is `/` followed by neither `/` nor `\`; an outside link stays a link only when https to a host the app links to itself (espn.com, sleeper.com / .app, myfantasyleague.com, yahoo.com, nfl.com, draftkings.com, fanduel.com, isuckatfantasy.io; no user, no port) — anything else renders as its label, plain text. Provider names are not escaped further: with links pinned, the worst a team name can do is bold its own text or link to one of our own paths. Tested with six hostile team names |

New environment variables (all optional; defaults in brackets): `LEAGUE_LAB_RATE_RESEARCH` [`60,40`] ·
`LEAGUE_LAB_RATE_HEAVY_48` [`60,60`] · `LEAGUE_LAB_RATE_WRITE_48` [`180,90`] · `LEAGUE_LAB_RATE_HEAVY_ALL` [`300,150`] ·
`LEAGUE_LAB_RATE_RESEARCH_ALL` [`1200,600`] · `LEAGUE_LAB_RATE_WRITE_ALL` [`3000,1000`] · `LEAGUE_LAB_CPU_SLOTS` [4; 0 =
off] · `LEAGUE_LAB_CPU_WAIT_S` [20] · `LEAGUE_LAB_USAGE_PER_HOUR` [1200] · `LEAGUE_LAB_USAGE_PER_CLIENT_HOUR` [120] ·
`LEAGUE_LAB_PROVIDER_CACHE_MAX` [1500] · `LEAGUE_LAB_API_DOCS` [off]. Earlier: `LEAGUE_LAB_GATE`, `LEAGUE_LAB_RATE_LIMIT`
[on], `LEAGUE_LAB_RATE_READ` [`300,150`], `_HEAVY` [`20,20`], `_WRITE` [`60,30`], `LEAGUE_LAB_RATE_CLIENTS` [5000],
`LEAGUE_LAB_CLIENT_IP` [auto], `LEAGUE_LAB_PROXY_HOPS` [1], `LEAGUE_LAB_ALLOWED_HOSTS`, `LEAGUE_LAB_MAX_BODY_KB` [256],
`LEAGUE_LAB_MAX_UPLOAD_KB` [2048], `LEAGUE_LAB_CSP` [on]. `/api/status` → `ratelimit` adds `coarse`, `all_clients`,
`cpu` and `usage`.

## 12. Wave I-N: the new routes, a second independent review, its fix round (2026-10-06)

Wave I-N (docs/STATUS.md § "Wave I-N") added a home page, a blog, 160 reference scoring keys, a trade calculator
without a league, the matchup board, published DFS slates with stacks, and the League outlook. A seventh agent that
wrote none of it reviewed the merged tree (`cd56421`) on fixtures with the limiter off to measure raw cost.

**Every new route and its bucket** (`ratelimit.bucket_for`):

| Route | Bucket | Cost, measured |
|---|---|---|
| GET `/api/blog`, `/api/blog/{slug}`, `/blog/rss.xml`, `/blog/img/{name}`, `/sitemap.xml` | read | 2–3 ms (the index is cached hourly) |
| GET `/{path}` (the page shell, now with per-path meta tags) | not limited, as before | one stat + string joins |
| GET `/api/trade-calc/free` | research (heavy for a league this process has not seen → 400) | 0.6–1.7 s cold per scoring, 10–20 ms warm |
| GET `/api/matchups/board` | research (heavy for an unseen league) | 0.6 s cold, 15–19 ms warm; 435 KB at `limit=100` |
| GET `/api/dfs/slates`, `/api/dfs/slate/{id}` | research | 3–4 ms; one build per slate, then cached (16 × ~1.4 MB) |
| POST `/api/dfs/lineups` (+ `slate_id`, stacks, exposure) | heavy | 3.7–4.1 s with every option on 768 players, +10 MB; one at a time |
| GET `/api/league/outlook` | heavy + needs a league | 0.7 s cold for a 12-team house league; 7 MB + 4 MB at every size; one simulation at a time |

**Findings and fixes** (nothing Critical or High; Wave I-M's two High fixes — the parser limits, the solver's budget
and one-at-a-time lock — still hold):

| # | Finding (severity) | Fixed by |
|---|---|---|
| M1 | `GET /api/dfs/slates` rebuilt every offered slate on every call once more than 4 were offered (a 4-entry cache under a 16-file limit: 3.0 s / 1.3 s / 1.4 s per call with 8 files, each holding the DFS lock and a CPU slot). Dormant: `dfs/slates/` ships empty | the listing never builds a slate — the matched / unmatched counts come from one match per file, kept with the file; the built-slate cache holds `MAX_PUBLISHED` (16). A test: 8 files, three listings, 0 builds |
| M2 | A cold `/api/league/outlook` grew with league size (32 teams × 24 starters × 17 weeks: 249 MB + 210 MB, 1.5 s), drew before checking it could answer, and four could run at once; ~15–20 provider calls per unknown league | simulated in chunks keeping tallies only (7 MB + 4 MB at every size); the season count capped by size (10,000 → 2,000 for the largest; the number run is in the answer); every check before any draw; one simulation at a time (wait 5 s, then 429 `busy`); hard limits (32 teams, 30 starters, 18 weeks: the rankings still answer); the schedule cached 6 h per league (a second cold build: 12 calls → 0) |
| L1 | The outlook's cache key and house check used the raw `league` string (`…%20`, a tab: a fresh build each, and a padded house id took the on-demand path) | `A.check_id` first; a key that names no league is 404 |
| L2 | The matchup board's 24-entry region held both the per-scoring boards and the week-wide entries (cycling 20 scorings evicted the week) | the week-wide entries have their own region (`matchup_week`, 8 entries) |
| L3 | `myweek`'s chain check in the pairing loop scaled badly with starting slots (45 slots: 1.9 s) | Hall's condition over position kinds, memoised per call; direct eligibility only above 24 slots (45 slots: 0.01 s) |
| L4 | `_published_pool` ran on the event loop (18 ms) | in the threadpool |
| L5 | `re.match` + `$` accepted a trailing newline in the blog's slug and picture name and the slate id (harmless: an exact lookup followed) | `fullmatch` everywhere; tests with `\n` and `%0a` |

**Checked and sound as built**: the page shell (the path only selects from a fixed set or a slug in the post index;
every value escaped; `/blog/%22%3E%3Cscript%3E…`, an encoded CR/LF and `..%2f` give the default, the blog's preview
or 404; the CSP header and the inline-script hash intact); blog pictures (traversal, `.svg`, symlinks, the resolved
folder, the first bytes, 2 MB); the blog's limits (300 posts of 200 KB, drafts off unless
`LEAGUE_LAB_BLOG_DRAFTS=on` — **never set it on Render**); `mdDoc` (escape-first; links only in-app or https to the
allow-listed hosts; pictures only from `/blog/img/`; placeholders cannot be forged; a link's target with a
placeholder in it is not made a link); the reference keys (exactly 160 parse; caches use the canonical key; at most
20 priced scorings); the free calculator (ids `^00-\d{7}$`, ≤ 6 a side, parameterised SQL); the board's `q=` (a
pandas substring, `%` and `_` are text; `limit` 1–100, `offset` ≤ 5,000); the slate id (looked up in what was read,
never joined to a path); the crash card (a fixed sentence; analytics gets the route's name from a closed set).
New environment variables: `LEAGUE_LAB_BLOG_DIR`, `LEAGUE_LAB_BLOG_DRAFTS`, `LEAGUE_LAB_DFS_SLATES` — none is set on
Render.

## What is left, by severity

| Severity | Item | Where |
|---|---|---|
| Medium | Verify the limiter's keying live (§ 2, two curl lines) before trusting the numbers | the PO, after the deploy |
| Medium | Provider budgets are global: many addresses opening unknown leagues spend Sleeper's / MFL's budget for everyone ("busy"). Wave I-N's League outlook reads a league's remaining weeks (~12–20 calls on its first build; cached 6 h after) — the same budget, reached with fewer requests | `sleeper_client` / `mfl_client` buckets |
| Low | `--forwarded-allow-ips='*'` makes `request.client` client-written on Render; nothing in the app trusts it now, but a future reader would | `api/Dockerfile` (the PO): keep, and say so in the Dockerfile's comment, or set Render's proxy range if Render publishes one |
| Low | Other clients follow redirects anywhere (only their fixed hosts could send one) | `sleeper_client`, `espn_client`, `yahoo_client`, `news_feed`, `injury_feed` |
| Low | `/api/status` and `/api/usage/summary` are public: operational numbers (memory, cache ages, counts) — no secret, no league id | consider a token for them later |
| Low | 422 answers echo the requester's own input | FastAPI default |
| Info | GA: no cookie banner (PO call 2026-10-04); About says GA is used and what is sent — still true with no password. A public launch to EU / UK visitors needs Consent Mode first (HOSTING § Google Analytics) | Andrew's call |
