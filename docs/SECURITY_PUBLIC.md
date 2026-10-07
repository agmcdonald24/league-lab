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

## 13. Each client's own share of the providers' budget (Wave I-O, IO-4; was "left", Medium, twice)

**The finding**: Sleeper's and MyFantasyLeague's token buckets are one per process (`sleeper_client.TokenBucket`:
300 Sleeper calls a minute, 60 MFL calls), spent by every visitor together; one client opening many unknown leagues
emptied them and league setup said "busy" for everyone. The League outlook's first build reads a league's remaining
weeks (12–20 calls), so fewer requests reached the same effect.

**Fixed by** `src/league_lab/provider_share.py`: under the global bucket, each client has its own ceiling per provider.

* **Who the client is**: the limiter's `client_group` (an IPv4 address, an IPv6 /64), which the limiter's middleware
  sets in a context variable (`provider_share.CLIENT`) once a request is admitted and resets after it; the provider
  clients read it where they take their bucket (`Sleeper._get`, `MFL._get`) — no parameter threaded through any call.
  Starlette carries the variable into a sync route's worker thread; the one thread pool that fans out provider calls
  on a request (`anyleague.user_leagues`, league setup) now hands it on (`contextvars.copy_context`), so league setup
  cannot dodge it (tested: a 3-call share refuses `user_leagues` for the fixture user, a 1,000-call share counts every call of it).
  **Fix round (review L3)**: `availability.contexts` (the roster contexts, reached from `decisions` through
  `A.lineup_rows`) started its pool without the context; it carries it now. Every pool / thread in `api/` and `src/`:
  carries the client — `availability.contexts`, `anyleague.user_leagues`, Starlette's threadpool (sync routes,
  `run_in_threadpool` in DFS and the blog editor: anyio copies the context); does not need to — the writer threads of
  `events`, `usage` and `outlook_store` (database writes, no provider call), `news.recent` (ESPN's player news, its own
  bucket), `injury_feed.snapshot` (one ESPN copy for everyone). `test_every_pool_carries_the_client_or_says_why_not`
  fails on a new pool that is neither.
* **No client, no limit**: the nightly and the CLI (no middleware), the tests (the limiter is off there:
  `LEAGUE_LAB_RATE_LIMIT=off` in `api/tests/conftest.py`) and anything run outside a request see `CLIENT = None` and
  are limited by the global bucket only, exactly as before. With the limiter switched off on Render, the share is off
  too.
* **The numbers** (`provider_share.DEFAULTS`; a token bucket in its virtual-scheduling form, one number per client in
  debt, HMAC-keyed with a random per-process key, ≤ 5,000 clients per provider, full ones dropped first):

| Provider | At once | Then, a minute | Why |
|---|---|---|---|
| Sleeper | 150 | 60 | one unknown league opened cold — My Week, Team, League with its outlook — costs **11 calls** on the fixtures (whose schedule stops at a missing week 3) and **~25–35 live** (+ the outlook's 12–20 remaining weeks: the PO's measurement, Wave I-N § "Verified live"); three leagues ≈ 105 at most < 150. Measured: three cold openings 15 s apart → 33 calls on the share, **0 refused**; fifty in a minute (1.2 s apart) → refused from the **16th** league on the fixtures, 140 of 200 answers "busy"; at 25 / 35 calls a league, fifty → 6 / 4 built in full, then about two a minute. One client can hold at most half of Sleeper's per-minute budget at once and a fifth of it after that |
| MFL | 50 | 12 | `mfl:70587` opened cold costs **14 calls** (fixtures); three = 42 < 50 (measured: three openings 15 s apart, 0 refused). MFL's own budget is 60 a minute: one client can take 50 at once, then 12 a minute leaves 48 for everyone else |

* **A refusal** is the provider client's own: a cached answer, even an expired one, is served first; otherwise
  `SleeperBusy` / `MFLBusy`, which the API answers **503** `{"error": "busy, try again in a minute", "code": "busy"}`
  (main.py's handler) and the web says "Busy right now. Try again in a minute." — never a 500 (tested: fifty leagues,
  every answer 200 or 503). Another visitor is not refused (tested).
* **Memory**: 20,000 clients in debt → at most 5,000 held per provider (a few hundred KB; tested).
* **Switches**: `LEAGUE_LAB_PROVIDER_SHARE` = `off`, or `"<per minute>,<at once>"` for Sleeper;
  `LEAGUE_LAB_PROVIDER_SHARE_MFL` the same for MFL. ESPN and Yahoo are read with the visitor's own connection (their
  budgets are per user at the provider) and keep their own limits.

## 14. Wave I-O: the site's first writing surface, a third independent review, its fix round (2026-10-06)

Wave I-O (docs/STATUS.md § "Wave I-O") added the blog editor (accounts listed in `LEAGUE_LAB_EDITORS` write posts and
pictures into the `blog` schema), the League outlook's store, share link and preview card (the `outlook` schema), the
per-client provider share (§ 13), the context record's route and weather. A fifth agent that wrote none of it
reviewed the merged tree (`72d959b`) on fixtures with two editor accounts and one ordinary account it made and
removed.

**Every new or changed route**:

| Method and route | Who may call it | Bucket |
|---|---|---|
| GET `/api/blog/mine`, `/api/blog/posts/{id}`, `…/revisions/{rid}` | an editor (else 404 / 401 / 403) | read |
| GET `/api/blog/export` | an editor | research |
| POST `/api/blog/posts`; PUT `/api/blog/posts/{id}`; POST `…/publish`, `…/unpublish`, `…/restore`; DELETE `/api/blog/posts/{id}` | an editor + same-site | write (+ 60 a minute a session, one save per post per 5 s) |
| POST `/api/blog/images` (≤ 320 KB at the Guard); DELETE `/api/blog/images/{id}` | an editor + same-site | write |
| GET `/blog/img/db/{id}` | public | read |
| GET `/api/context/record` | public | read |
| GET `/api/league/outlook` (`part=power`) | public | heavy |
| GET `/api/matchups/board` (`show=`) | public | research |
| GET `/league?league=` (the page shell's card) | public | not limited; a set lookup for an unknown key, never a provider call or a simulation |

There is no write a visitor without an account can reach except the outlook store's capped rows.

**Findings and fixes** (nothing Critical or High):

| # | Finding (severity) | Fixed by |
|---|---|---|
| M1 | Any account could bypass the outlook store's cap: rows for leagues "saved by an account" were exempt, and an account can save and remove leagues at will (run: 20 of 25 visitor leagues written, then all 50 of an ordinary account's). A few addresses could have filled Neon's free space in days | no exemption: every league that is not a house league sits under 20 new a day and 200 held; a size guard (`pg_total_relation_size` at most once a minute; above 40 MB nothing new is written); a league-week replaced at most once an hour. Worst case 34 MB |
| M2 | One client's refused provider calls were cached as a broken outlook for everyone: with client X's share spent, X's build answered "the schedule for week 12 is not available" and client Y got that from the cache for 600 s (house) / 120 s | a refused or failed schedule read is raised; a build during which any provider refusal happened is neither cached nor stored and its board contexts are dropped; the requester gets 503 `busy` (502 for a provider failure) and the screen retries three times. Measured: X refused → Y gets the full answer |
| L1 | An editor session could churn the database faster than the storage cap counts (26 saves of 200 KB in 0.9 s; dead row versions are not in the cap) | an unchanged save writes nothing; one save per post per 5 s (429 `too_fast`, `Retry-After`; the editor waits and retries); a revision only when the text changed and the newest kept one is 30 s (2 min for an autosave) old |
| L2 | A slug whose cut ended in a dash made `--` and a 500 (`CheckViolation`) | the suffix strips the dash; every `IntegrityError` / `DataError` on the editor's routes is 409 / 422 with words |
| L3 | The provider share leaked through `availability.contexts`' thread pool (no `copy_context`) | carries the client; `test_io4` lists every pool or thread on a request path and fails on a new one that neither carries the client nor says why not |
| L4 | Anyone could spend the preview card's read budget (120 a minute, shared) with `/league?league=<random>` and turn real links' cards off | the shell looks up only keys this process built or the stored-key set (≤ 2,000, re-read at most once a minute); the shared budget is gone |
| L5 | Invisible direction and zero-width characters were accepted in the title and the author line | U+200B–200F, U+202A–202E, U+2066–2069, U+FEFF stripped from single-line fields (the body keeps them: emoji joiners) |

Notes fixed: unsent drafts on the device are keyed by account, never kept for a signed-out visitor and cleared on
sign-out; `/blog/img/db/<id>` is cached a day with an ETag (was a year, immutable: a deleted picture lived on).

**Attacked and sound as built**: editor permissions (no cookie or a forged one 401, a non-editor 403, another
editor's post / revision / picture 404; an empty, whitespace or malformed `LEAGUE_LAB_EDITORS` makes every route 404
— nothing fails open); cross-site writes (`Origin` of a look-alike host, `null`, `text/plain` bodies: refused or
nothing written; the session cookie is SameSite=Lax); stored XSS through title, summary, author and body at RSS, the
sitemap, the shell's meta tags, the preview and the public post (raw only inside JSON served with `nosniff`); the
picture upload (a PNG-header-plus-HTML file is served as `image/png` with `nosniff` under `default-src 'self'`; SVG
refused; the server never decodes an image); SQL (every query parameterised; slugs by a regex and a CHECK); the
export zip's names (no zip-slip); the account id in `/api/account/me` (your own only; writing still needs the signed
session cookie); the outlook's keys and provider-supplied names in the `og:` tags (escaped; crafted keys get the
default card); private leagues (never shareable, stored or carded); the store's cap lives in the database (a restart
does not reset it), its queue is bounded at 64 and off the request thread.
New environment variables: `LEAGUE_LAB_EDITORS` (set in Render's dashboard), `LEAGUE_LAB_OUTLOOK_STORE`,
`LEAGUE_LAB_PROVIDER_SHARE`, `LEAGUE_LAB_PROVIDER_SHARE_MFL` (unset on Render: the defaults).

## 15. Wave I-P (IP-5): a refused read is never kept as data; player pages that share

**Why**: § 13 gave each visitor a share of Sleeper's and MFL's budget, so a refused read is common now — the visitor
whose share is spent is refused while everyone else is served. Many readers turn a refusal into a default (no
opponent, an empty directory, "unmapped" players, 0-0 records), which is right for that one answer and wrong for a
cache the next manager reads. § 14's M2 was this class in the outlook; IO-2 saw it in the roster contexts and the
player directory.

**The mechanism** (`src/league_lab/provider_trouble.py`): the Sleeper and MFL clients `note()` every read that raises —
refused with nothing held, or failed with nothing held (a read served from what the client holds, even past its TTL,
is not trouble). A cache builds inside `watch()`; notes made in pools that carry the request's context (§ 13's rule,
`test_every_pool_carries_the_client_or_says_why_not`) land on it. A troubled build is **not kept**; `kept()` serves the
last good value held for the key (its own stamps ride with it — never a "stale" warning), else **503 `busy`** in the
app's words (the web retries). A held value served for a troubled rebuild is taken back off the watches around it, so
an outer cache still keeps its answer.

**Every cache on a request path that stores a provider read** (Sleeper, MFL, ESPN, Yahoo, the injury and news feeds):

| Cache (where; life) | Refused (`…Busy`) | Failed (`…Unavailable`, a timeout) | Nonsense (an empty body, a 200 error page) | Test (`api/tests/test_ip5.py`) |
|---|---|---|---|---|
| Sleeper client, per path (`Sleeper._get`; 5 min – a day by kind) | held served, else raised; now **noted**, and (fix round) a held answer past its TTL only inside the age bound below, noted `stale` | the same | before: an empty body (`null`) was **kept as data** — rosters / users `[]` ("nobody on this roster") for 10 min / a day, the directory `{}` for a day; now a failure: held served, else raised (an HTML page was already a failure) | `…empty_directory_is_a_failure…`, `…null_roster_answer_serves_the_held…`, `…refusal_with_nothing_held_is_noted…` |
| Sleeper's directory on disk (`.cache/sleeper_players_nfl.json`) | before: read only under a day old, else the refusal raised and readers swallowed it into an empty directory; now a copy up to **2 days** old answers (noted `stale`) | the same | an empty directory is never written (unchanged) | `…disk_copy_of_any_age_answers_a_refusal` |
| MFL client, per URL (`MFL._get`; 5 min – a day) | empty bucket / share / backoff: held, else raised; **an HTTP 429 raised past a held answer** → now held served; noted | held, else raised; noted | an empty body was **kept a day** (players: every id "unknown") → now a failure | `…mfl_an_empty_body…`, `…mfl_an_http_429_serves_the_held…` |
| MFL id mapping (`platforms.MFLLeagues.mapping`, `extra_players`; process life) | `players()` refused → every id it could not map **recorded as "MFL player <id>"** with no position (a defense lost, an empty slot) and the roster built on it → now **busy**, nothing recorded | the same | — | `…translate_refused_is_busy…`, `…mfl_a_refused_id_lookup_is_busy_then_the_full_roster` |
| ESPN client (per league, per visitor's cookies) | held or raised | held or raised | not a dict → a failure | sound as built; not noted (read with the visitor's own connection; its two swallow sites are Low, below) |
| Yahoo client (per manager) | **an HTTP 429 / 999 (`YahooBusy`) was raised past a held answer** (as MFL's was) → now held served, else busy | held or raised (unchanged) | not an object → a failure (unchanged) | `tests/test_ip5_providers.py` |
| ESPN injury report (`injury_feed`; memory + disk; 15 min / 1 h) | held copy (unchanged) | held copy (unchanged) | before: a copy with **no entries replaced the held one** ("nobody is injured") and was written to disk → now the held copy stays, the read counts as failed | `…injury_feed_keeps_its_held_copy…` |
| ESPN news per athlete (`news_feed`) | held (unchanged) | held (unchanged) | an empty body `{}` replaced the held items with none → now a failure | `…news_feed_keeps_its_held_items…` |
| the overlay's snapshot (`availability._snap`; 120 s) | the directory refused cold → the Sleeper side empty, kept under a key that changes once the directory reads again (self-healing per call); now noted, so nothing built on it is kept | the same | (the client's rule) | via the contexts' test |
| **roster contexts** (`availability` → region `contexts`; 10 min house, 2 min on demand; My Week, Team, Waivers, the card, trades, the outlook's week) | before: a refusal swallowed in the build (the directory, `_resolve`, MFL's standings / live scoring / ids) was **kept for the TTL** under a key without the directory's stamp — the next manager's lineup; now never kept: the roster's **last good context** (held ≤ 1 h) answers with its own stamps, else 503 busy; a raised refusal: the held context answers | the same | (the clients' rule) | `…roster_context_is_not_kept…`, `…my_week_refused_answers_busy_then…` |
| decision memos (`decisions._memo` → region `decisions`; trade context, waiver sweep, partners, trade lists, rest of season, the outlook's context) | swallowed → kept → now not kept, 503 busy (the clients hold their reads: the next build is whole) | the same | — | `…decisions_memo_keeps_nothing…` |
| a league's solved weeks (`anyleague.league_weeks` → `league_weeks`; 5 min) | swallowed → kept → now not kept (the cache around it answers busy) | the same | — | `…league_weeks_and_rest_of_season…` |
| rest of season (`anyleague.ros_table` → `ros`; 10 min) | a unit's directory read refused (`unit_directory` → `{}`: units keyed `TMQB-KC`, names lost) → kept → now busy, nothing kept | the same | — | the same test |
| the outlook (`outlook` + `outlook_schedule`; IO-2) | not kept (IO-2) | before: **a failure was not counted** (IO-2 counted refusals): MFL's standings down → records 0-0 kept 2 minutes; now counted → not kept (the requester: busy) | — | `…outlook_keeps_nothing_built_while_a_provider_failed` |
| `il4_free_agents`, the outlook's cards and store, scoring checks, research's priced boards and memos, the matchup board | sound as built: keyed by the directory's fetch and size, written from a clean build only, or every provider error raised (nothing kept) | | | — |
| priced weeks, boards, stats, About, DFS, the blog, reference values | no provider read | | | — |

**A behaviour change to know**: an MFL league whose standings or live-scoring export fails **with nothing held** (cold)
now answers busy where it showed 0-0 records or last week's starters; a held copy (10 minutes, then up to an hour
past it) answers as before.

**A 500 fixed on the way** (on `main` too): with the availability overlay on (the site's default), a roster frame with
no status at all (`report_status` all NaN: float64) could not take "Questionable" — MFL 70587's whole outlook was a 500
on the fixtures. `availability.apply_to_rows` makes the column objects first (the same values; tested).

**Fix round after the independent review of the merged wave (`integ/IP` 3d1b76b)**:

| # | Finding (severity) | Fixed by |
|---|---|---|
| M1 | A client whose share was spent was served the client's held answer **past its TTL** without a note, so `kept()` stored the build with a fresh TTL and every other manager got it (the reviewer's run: good-2 got the attacker's 16-player roster after Sleeper had 15; repeatable every 2 minutes, ~70 minutes behind) | the Sleeper, MFL, ESPN and Yahoo clients `note("stale")` whenever they serve a held answer past its TTL (`provider_trouble.serve_held` / `_held_ok`; `TOTALS["stale_served"]`, not trouble); a watch that saw it is not clean, so `kept()`, `decisions._memo`, `league_weeks`, `ros_table` and the outlook **serve that requester and keep nothing**; a cache's own held value served for a troubled rebuild counts stale for the caches around it; the caches' hold is an hour. **The age bound** (`provider_trouble.STALE_MAX_S`, since the answer was read; older → busy, or the failure; the same on every day): rosters and live scores **an hour** (Sleeper `rosters` / `matchups`, MFL `rosters` / `live_scoring`, ESPN `rosters` / `schedule`, Yahoo `roster` / `scoreboard`), standings / status / transactions an hour, MFL injuries 6 h, played weeks / schedules / weekly results / users' leagues / state / teams / free agents a day, settings / league / rules / users / players / the directory (and its disk copy) 2 days; a kind not listed an hour. Why an hour and no game-day tightening (fix round 2, the PO): a provider outage must not turn into "busy" while a last good answer with its stamp exists (`test_f3`'s rule) — M1 is answered by "a build that saw a stale answer is kept by nobody", not by a short bound. Test: the reviewer's script as `test_review_m1_…` (attacker: 16 players, stale, not kept; good-2: 15, Sleeper read again; 61 minutes later the refused attacker gets busy) |
| M2 | The outlook judged a build by the **process's** refusal counters (and IP-5 had added `provider_trouble`'s totals): any client's refusal during any build made it "degraded" — uncached, rebuilt per request, 429s at the one-at-a-time simulation | `outlook()` builds inside its own `provider_trouble.watch()`: only trouble THIS build met makes it degraded; a stale-only build is served `not_kept` (no cache, no store, no card). Test: client X refused (in its own thread) during Y's build → Y's build kept |
| L1 | `/api/league/week-odds` answered a refused client 200 `"games": []` (`myweek.week_odds` swallowed the matchups refusal) | an on-demand league re-raises (503 busy / 502); a house league still falls back on the database. Test |

**Swallowed refusals that reached an answer, grepped again** (`except (…Busy | …Unavailable …)` then a default):
fixed — `myweek.week_odds` (L1); `ondemand.mfl_results` (was "no results"); `decisions` `_waiver_context`, the trade
board's this-week overlay and the team's contexts (were the page without the roster's week: now busy / 502);
`MFLLeagues.rosters` (standings refused → was 0-0 records; live scoring and last week's results both refused → was
"no starters"; last week's results still stand in for live scoring); `MFLLeagues._with_live` (was the schedule's 0 as
the live score); `ESPNLeagues.league` (week refused → was week 1; status → `{}`); `YahooLeagues._records` (was 0-0)
and `_week_of` (was week 1) — a fixture file never recorded keeps the old default (`provider_trouble.fixture_gap`).
Listed, not changed (each answers "unknown" in words, or is cosmetic): `ondemand.opponent_safe` / the opponent's
context (opponent null with the note "busy" / "sleeper_unavailable"), `week_points` / `mfl_week_points` /
`mfl_teams_done` (None / unknown, never 0), `win_on_demand` (no win block), `with_cards` and the Yahoo league rows
(card null), `MFLLeagues.users` (team names from the league export), `MFLLeagues.transactions`' next-week file (this
week's moves), `availability` (`snapshot`, `_resolve`, `depth_order`, `moves_on_context`: the overlay without
Sleeper's side, cold only — noted, so nothing built on it is kept), `outlook._league_inputs` (the nightly's settings,
marked degraded).

**Player pages that share** (`api/league_lab_api/player_share.py`; `main.web` and `blog.sitemap`, marked IP-5):
`/player/<gsis>` previews as "Josh Allen (QB, BUF): 23.8 projected this week, 14–35 · isuckatfantasy" with the
opponent, kickoff and rank at the position — **from the matchup board's week frame for the default scoring that this
process already holds, and nothing else**: a crawler's hit reads that region's keys and one entry (tested: 0 database
queries, 0 provider calls, nothing built or kept); not held → the default card. The default scoring's key is computed
only when the reference scorings are already loaded. Ids `fullmatch` `^00-\d{7}$` (`%22%3E`, `..%2f`, `%0a`, a
Sleeper id: the default card or the router's 404); every value through `blog.seo_tags` (escaped; tested with
`"><script>`); the inline script untouched (the CSP hash holds). The sitemap lists the 200 highest projections from the
same frame (none when nothing is held). A page whose query string names a league (`?league=`) answers
`X-Robots-Tag: noindex` and carries `<meta name="robots" content="noindex">` (the League link's card included).
No new route, no new environment variable, no new relation.

## 16. Wave I-P: the new routes, a fourth independent review, its fix round (2026-10-07)

**What was reviewed**: the merged tree of Wave I-P (`integ/IP` `0551b7d` against `main` `e4b5eec`) by an agent that
wrote none of it, with the limiter on and a spent provider share to play the refused client. Nothing Critical or
High; two Mediums and four Lows, all fixed in the round (§ 15's fix-round paragraph has IP-5's detail).

**New routes** (all public with the gate open):

| Method and route | Bucket | Notes |
|---|---|---|
| GET `/api/rankings` | research (heavy for an unseen league) | `position` ∈ 7, `view` ∈ 2, `limit` 1–200, `offset` 0–1000, `q` 2–40 letters matched as text; cache: the `rankings` region, ≤ 64 frames, never keyed by `q` |
| GET `/api/rankings/start` | research | `ids` 2–4 distinct gsis ids; reads `ranked`'s frames, no cache of its own |
| GET `/api/player/{gsis}/ratings` | read | no `league` parameter (L2); the Stats table's cached season frame |
| GET `/api/player/{gsis}/projections` | read | a gsis id or one of 33 team codes (a closed set) |
| GET `/rankings`, `/player/{gsis}` (shells) | not limited | titles from a closed set / from the board the process already holds: no query, no provider call; `?league=` → `X-Robots-Tag: noindex` |

**Found and fixed**

* **M1 — a spent client could pin everyone to expired roster data.** The Sleeper and MFL clients serve a held answer
  past its TTL to a refused client; that path made no note, so `provider_trouble.kept()` took the build as clean and
  stored it fresh. Run: good-1 builds a 16-player context, Sleeper's roster changes, 11 minutes pass, the attacker
  spends his share and asks → good-2 (share intact) is served the attacker's 16 players and Sleeper is never read
  again. **Fix**: a held answer served past its TTL is noted `stale` (not trouble) by the Sleeper, MFL, ESPN and
  Yahoo clients; a build that saw one is served to its requester and kept by nobody; an age bound per kind
  (`STALE_MAX_S`: rosters 30 minutes, 15 on Thursday / Sunday / Monday; live scores 15 / 10; standings and status an
  hour; schedules and settled weeks a day; settings and the directory two days) past which the answer is busy. The
  reviewer's script is a test.
* **M2 — any client's refusals made the outlook uncacheable for everyone.** `outlook._refusals()` compared
  process-wide counters around a build. **Fix**: the build's own `watch()`; a test refuses client X in its own
  thread during Y's build and Y's build is kept.
* **L1 — week odds answered a refused client with an empty 200** ("no games", not "busy"): re-raised for on-demand
  leagues; the same grep found and fixed `mfl_results`, three context sites in `decisions`, `MFLLeagues.rosters` and
  `_with_live`, `ESPNLeagues.league`, `YahooLeagues._records` / `_week_of`.
* **L2 — the ratings route marked any league "seen"**: it took a `league=` it never read, and the limiter bills a
  seen league `research`, not `heavy`. The route has no `league` parameter and is in `read`; outside `research` the
  limiter never reads a `league=` (`test_card_reads_never_mark_a_league_seen`).
* **L3 — Rankings' frames for one scoring were shared between a reference key and a real league** (whichever built
  first decided the defense words for both; they differ on 123 of 219 receivers in week 4): the key carries the
  tone's source.
* **L4 — model versions compared as text** in `mart_projection_drift` ('v3.10' sorts below 'v3.4'): `version_key`
  compares the numbers; a dbt test pins it.

**Attacked and found sound**: Rankings' parameters (a newline in `position`, `limit` 0 / 201 / `abc`, `q` of `.*`,
a null byte, 5,000 characters, an empty or ESPN league: 400 / 422 / 404 / 502 as they should) and its cost (cold
0.07–0.66 s, warm 9 ms; four players on an unseen scoring 0.2 s; 20 scorings × 2 views × 7 positions against a
64-frame cache, each refill under 0.7 s inside the research bucket); reference keys never carry ownership; the
shells escape and read only what the process holds; every pool on a request path carries the client; refused MFL
lookups and busy builds answer 503, never 500; empty provider bodies are failures.

**The nightly**: the review ran the PO's fresh-database check ("every state table exists after db migrate") and
found no new step that stops the night under v3.4 (`backtest-v2` once, as a hard step, is the one to watch).

## What is left, by severity

| Severity | Item | Where |
|---|---|---|
| Medium | Verify the limiter's keying live (§ 2, two curl lines) before trusting the numbers | the PO, after the deploy |
| Low | Provider budgets: each client now has its own share (§ 13), but **many addresses** together (a botnet, an IPv6 range wider than a /64 per client) still spend Sleeper's / MFL's global budget; one address cannot | `provider_share` (§ 13); a per-/48 share like the limiter's `heavy` /48 key if it is ever seen |
| Low | `--forwarded-allow-ips='*'` makes `request.client` client-written on Render; nothing in the app trusts it now, but a future reader would | `api/Dockerfile` (the PO): keep, and say so in the Dockerfile's comment, or set Render's proxy range if Render publishes one |
| Low | Other clients follow redirects anywhere (only their fixed hosts could send one) | `sleeper_client`, `espn_client`, `yahoo_client`, `news_feed`, `injury_feed` |
| Low | When **everyone's** budget is spent (Sleeper's 300 a minute, not one client's share), every on-demand build is stale-only and kept for nobody (§ 15 fix round): each request rebuilds — CPU on a busy Sunday. Noting `stale` only for a client's own share refusal would keep those builds (everyone gets the same held answer then); the PO's call | `provider_trouble`, the clients (§ 15) |
| Low | `/api/status` and `/api/usage/summary` are public: operational numbers (memory, cache ages, counts) — no secret, no league id | consider a token for them later |
| Low | 422 answers echo the requester's own input | FastAPI default |
| Info | GA: no cookie banner (PO call 2026-10-04); About says GA is used and what is sent — still true with no password. A public launch to EU / UK visitors needs Consent Mode first (HOSTING § Google Analytics) | Andrew's call |
