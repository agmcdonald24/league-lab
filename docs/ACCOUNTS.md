# Accounts and profiles — the design (Wave I-I, II-5, 2026-10-04), phase 1 (Wave I-K, IK-4: § "Built, phase 1"), phase 2 (Wave I-L, IL-5: § "Built, phase 2") and passkeys (Wave I-M, IM-4: § "Passkeys")

*(The fifth review, § 9: "An account should save multiple provider connections, selected leagues/teams, a default
league, watchlists, and table preferences … Returning users should not repeat onboarding." Acceptance: "one account can
save and switch multiple leagues/providers without mixing scoring or teams; a failed sync in one league does not break
the others; reconnecting does not duplicate leagues; returning on another device restores saved selections." The PO
decides; this page is the model and a recommendation.)*

## Today (what an account would replace)

No accounts. The beta has one shared password (`api/league_lab_api/auth.py`: a signed `ll_auth` cookie, no server
state). Everything a manager picks lives in **this browser's** `localStorage` (`web/src/lib/prefs.ts`): the Sleeper
username and its league list (`ll.user`, `ll.userLeagues`), the leagues opened by link — MFL, and since II-5 a Sleeper
league by its link (`ll.mflLeagues`), the league and the team per league (`ll.league`, `ll.team.<league>`), the setup
screen's platform (`ll.platform`). That is **guest exploration**, and it stays: nobody has to make an account to use
the product; an account is offered when someone wants their leagues on another device.

## Principles (the review's requirements, made concrete)

1. **Sign-in identity is ours, apart from any provider.** A person signs in to isuckatfantasy (an email address, below);
   a provider is a *connection* that person adds. A public Sleeper username lookup is **not** proof of ownership: it is
   stored as a lookup ("leagues found for the Sleeper user `macz`"), never as "this is MacZaddy's account", and it
   unlocks nothing that is not public anyway.
2. **Stable external ids.** Sleeper: the `user_id` the username resolved to (a username can change; the id does not),
   league ids, roster ids. MFL: league id + franchise id. Yahoo (later): the user's GUID and league / team keys.
3. **Leagues namespaced by provider and season.** A league's key is `(provider, season, external_id)` — Sleeper gives a
   new league id each season (`previous_league_id` links them), MFL keeps the id and changes the year. The team
   selection is kept per league key, so a 2026 pick never leaks into 2027 and an MFL "4" never meets a Sleeper "4".
4. **Preferences scoped.** Global (theme), per league (default view, table presets), per user only — never stored on a
   shared row.
5. **Public caches stay public.** The player directory, a public league's settings and rosters are cached by provider +
   id as today and hold nothing about a user. Anything read through a user's private connection (a Yahoo token, an MFL
   league API key) is cached under that connection only and never enters the shared cache.
6. **Sync is per league, idempotent, isolated.** Upserts by natural keys; one league's failure marks that league, not
   the account; reconnecting a provider finds the same rows (unique keys) instead of adding new ones.
7. **Read only.** Sending trades or submitting claims is a separate product capability needing explicit user action and
   provider support (none of Sleeper / MFL-as-used / Yahoo offers it to us today: `docs/PROVIDERS.md`).

## The model (a new `accounts` schema on Neon)

| Table | Columns (key first) | Notes |
|---|---|---|
| `users` | `id uuid`, `email citext unique`, `created_at`, `last_seen_at`, `deleted_at` | the sign-in identity; nothing else about a person |
| `login_links` | `token_hash bytea`, `user_email citext`, `created_at`, `expires_at` (15 min), `used_at`, `ip_hash` | the email link (below); single use; the token itself is never stored |
| `sessions` | `id uuid`, `user_id`, `created_at`, `expires_at`, `revoked_at`, `user_agent_family` | server-side so "sign out everywhere" works; the cookie carries `id` + an HMAC |
| `connections` | `id uuid`, `user_id`, `provider` (`sleeper` / `mfl` / `yahoo`), `external_user_id`, `label`, `kind` (`lookup` / `league_key` / `oauth`), `secret_enc bytea null`, `status` (`active` / `expired` / `revoked` / `failing`), `last_sync_at`, `last_error`, `created_at`; **unique (`user_id`, `provider`, `external_user_id`)** | `lookup` = a public username (no secret); `league_key` = MFL's per-league API key; `oauth` = Yahoo's refresh token; secrets encrypted with a key held on Render only |
| `leagues` | `league_key text` (`sleeper:2026:1389709692405551104`, `mfl:2026:70587`), `provider`, `season`, `external_id`, `name`, `scoring_label`, `total_rosters`, `public bool`, `last_sync_at`, `sync_status`, `sync_error` | shared metadata of a league — only what anyone could read |
| `user_leagues` | `user_id`, `league_key`, `connection_id null`, `team_external_id` (roster / franchise id), `is_default bool`, `hidden bool`, `added_at`; **unique (`user_id`, `league_key`)**; one default per user (partial unique index) | the profile's league list |
| `preferences` | `user_id`, `scope` (`global` or a `league_key`), `key`, `value jsonb`, `updated_at`; unique (`user_id`, `scope`, `key`) | table presets (II-3's saved presets move here), default views |
| `watchlist` | `user_id`, `league_key null`, `player_key`, `added_at`; unique (`user_id`, `league_key`, `player_key`) | |

**The profile page** (the review): one compact list from `user_leagues` ⨝ `leagues` ⨝ `connections` — provider, season,
league name, the selected team, scoring / format, last successful sync, connection status ("Reconnect Yahoo" on that row
only when its connection is `expired`).

**Flows.**
* *First sign-in on a device with guest picks*: offer "Save these N leagues to your account" (the `prefs` lists above);
  the import is an upsert by `league_key` — doing it twice changes nothing.
* *Add a provider*: Sleeper username → resolve to `user_id` → `connections` upsert (`kind = lookup`) → the user's leagues
  upserted into `leagues`, the user's roster pre-selected in `user_leagues` (they confirm). MFL link → `leagues` upsert;
  the user picks the team; a private league asks for the league's API key (`kind = league_key`). Yahoo → OAuth.
* *Sync*: a league is re-read when opened (today's on-demand path, unchanged) and, for the profile's "last sync", by a
  small job per league with a per-league timeout; its error lands on that league's row.
* *Disconnect*: `status = revoked`, secret wiped, the leagues read through it hidden (kept for a reconnect, deleted on
  request); a public-lookup connection simply goes.
* *Delete account*: rows deleted, `users.deleted_at` for the audit window, then gone.

**What it needs from the server.** Today the API's database role is read-only except two tables (`usage.events`,
`events.events`, each written in its own read-write transaction — `docs/HOSTING.md` § Usage). Accounts are the first
read-write *product* data: a separate role `league_lab_accounts` with rights on the `accounts` schema only, its own
small pool, and the schema created by a `scripts/hosted_accounts.sql` the nightly runs like `hosted_events.sql` —
**never dropped or replaced by the nightly's publish** (the publish swaps the analytics schemas only).

## Sign-in: the recommendation

| Option | What it is | Cost | Work | Fit |
|---|---|---|---|---|
| **A. Email link (passwordless), in our API** | "Email me a sign-in link" → a single-use link (15 minutes) → a session cookie | Mail: Resend's free tier — "3,000 emails / mo", "100 emails a day" (resend.com/pricing, read 2026-10-04); Pro "$20 / mo" for 50,000. Neon: a few MB in the free tier. Render: nothing new | ~1–2 days: two routes (`POST /api/auth/link`, `GET /api/auth/callback`), the three tables, rate limits per email and IP, the mail template | Works for every manager whatever their platform; no password to store or reset |
| B. Sign in with Google (OIDC) | A Google button; we keep `sub` + email | Free (non-sensitive scopes `openid email profile`) | ~1 day + a Google Cloud OAuth client and consent screen | Good second button; not everyone wants Google |
| C. A hosted auth service | e.g. Neon Auth ("Managed Better Auth … All authentication data is stored in the `neon_auth` schema"; free "Up to 60,000 MAU"; AWS regions only) | Free at beta scale | Its SDKs are JavaScript (Next.js / React); our server is FastAPI — the session check would cross into a JS service or verify its tokens by hand | Less code, but a second stack for one feature |
| D. Sign in with a provider | Sleeper / MFL / ESPN have no OAuth; Yahoo's would only serve Yahoo users | — | — | Not possible as the identity (principle 1) |

**Recommendation: A, the email link, built in our FastAPI with Resend for mail and the `accounts` schema on Neon; add
Google (B) as a second button once there are users asking for it.** It costs nothing at beta scale (the 100-a-day free
limit covers ~100 sign-ins a day; the $20 plan is the step after), keeps one stack, and keeps the shared beta password
as the door in front of it until the PO removes the gate.

**What A needs on Render / Neon / Cloudflare:**
* Render (env, secrets): `LEAGUE_LAB_RESEND_API_KEY`, `LEAGUE_LAB_MAIL_FROM` (`signin@isuckatfantasy.io`),
  `LEAGUE_LAB_SESSION_SECRET` (the HMAC key; `LEAGUE_LAB_API_SECRET` can serve), `LEAGUE_LAB_ACCOUNTS_DB_URL` (the new
  role), and later `LEAGUE_LAB_CONNECTION_KEY` (encrypts connection secrets).
* Neon: the `accounts` schema and role (above); backups are Neon's point-in-time restore — accounts are the first data
  that cannot be rebuilt from the nightly, so the PO checks the plan's restore window before launch.
* Cloudflare DNS for `isuckatfantasy.io`: Resend's SPF / DKIM records (and DMARC) so links land in inboxes.
* The privacy line on About: what an account stores (email, the leagues and teams picked, preferences) and how to
  delete it; usage counting stays anonymous (`usage.events` never gets a user id).

**Not decided here (the PO / Andrew):** whether accounts ship before the Sleeper licence question (accounts alone are not
commercial use; charging is); whether the beta password stays once accounts exist; retention for deleted accounts.

## Built, phase 1 (Wave I-K, IK-4, 2026-10-05)

Option A as recommended: an emailed link, in our FastAPI, Resend for mail, the `accounts` schema on Neon. Operating it
(secrets, Resend, DNS, the nightly's lines, the rollout): `docs/HOSTING.md` § "Accounts". Verified live: **no** — it
is off on the server until `LEAGUE_LAB_RESEND_API_KEY` is set and the nightly has created the schema.

**What a manager sees.** The ⋯ menu ("Sign in to save your leagues" / "Your account") and one line at the foot of the
setup screen ("Want your leagues on another phone or computer? Sign in with your email — no password") open `/account`:
an email field → "Check your email" → the link → "Sign in on this device" (one tap) → the account: the saved leagues
(platform · season · the team · the scoring line · when it was last read), the default, "Make default", "Remove",
"Save these N leagues" for the leagues this device knows that the account does not, Sign out, Sign out everywhere,
Delete my account (a second tap confirms). About's privacy line says what an account keeps. Nothing shows when the
server has accounts off; guest use is unchanged.

**What follows the account.** The leagues and the team in each (`user_leagues`), the default league (`is_default`;
the first league saved until another is chosen), the saved Stats views (`preferences`, scope `global`, key
`stats.views`). On a new device, signing in writes them into the browser's lists (`ll.mflLeagues`, `ll.team.<league>`,
`ll.league` when the browser had none, `ll.stats.views`): the switcher lists them and `/` opens the default league's
week with no setup — the review's acceptance ("returning on another device restores saved selections"), checked by
`web/e2e/ik4` at 375 and 1300. Signed in, a league picked on the setup screen, a new team in a saved league and the
Stats views also go to the server; the browser's copy stays the cache the screens read.

**Decisions taken while building** (each reversible):
* **The link carries its token in the URL fragment** (`/account#signin=<token>`), and the page posts it (`POST
  /api/account/verify`) after one tap — not `GET /api/account/login/<token>`. A path or query string lands in Render's
  and uvicorn's access logs (the rule: a link is never logged), and a mail scanner that opens links would spend a
  single-use link before the manager taps it.
* **The link's host is `LEAGUE_LAB_PUBLIC_URL`**, never the request's `Host` (a forged header would mail a link to
  someone else's site).
* **No new role, no new connection string** (the design had `league_lab_accounts`): the app role gets `SELECT /
  INSERT / UPDATE / DELETE` on the eight tables only and writes in its own read-write transaction (`db.run_rw`, U-1's
  writer generalised), like `usage.events` and `events.events`.
* **`ll_session`** = `<session id>.<HMAC-SHA256(LEAGUE_LAB_API_SECRET, id)>`; HttpOnly, SameSite=Lax, Secure on https
  (always on Render), path `/api/account`, **90 days** fixed from sign-in; a server row per session, so Sign out and
  Sign out everywhere revoke at once. A forged cookie is refused before any database read.
* **Email is lower-cased text** (no `citext` extension); a user row is made when a link is first used, not when one is
  asked for (a typo makes no account); the answer to "email me a link" is the same for any address.
* **The display fields of a saved league are per user** (`user_leagues.name`, `team_name`, `scoring_label`,
  `total_rosters`): one account can never change what another sees. The shared `leagues` row holds the key, the
  provider, the season, the external id and (later) the sync status.
* **Delete is immediate and total** (every row of the account, its links), no audit window.
* **Limits**: 5 links an hour per address, 30 per IP address, 90 a day in all (Resend's free tier: 100), counted in
  the table (a restart forgets nothing); 20 link checks a minute per IP address and 60 changes a minute per session
  in memory. 50 leagues, 200 preferences of 8 KB, 200 watchlist rows per account.
* **A username's league list is not pushed by itself** (it is re-read at every load and would put back a league the
  manager removed): those leagues go in with the one tap "Save these N leagues".
* **The per-league default view**: the web has no stored per-league view today (a screen remembers nothing per league
  but the team); the team per league and the default league are what move. `preferences` takes any scope (`global`
  or a `league_key`) and key, so a per-league default view is one call when the web grows one.
* **`connections` exists and nothing writes it** (Yahoo's refresh token and an ESPN connection stay in their
  encrypted cookies this wave, IK-1 / IK-2); the watchlist has its routes and no screen yet.

**The routes** (all behind the beta password; JSON; `no-store`; errors `{error, detail, code}`):

| Route | Answer |
|---|---|
| `GET /api/account/status` | `{enabled, reason, signed_in, email, mailer, session_days}` |
| `POST /api/account/login {email}` | 202 `{ok, sent, minutes}` for any address · 400 `bad_email` · 429 `rate_limited` · 502 `mail_failed` |
| `POST /api/account/verify {token}` | `{ok, email}` + the cookie · 400 `link_invalid` |
| `POST /api/account/logout {everywhere}` | `{ok, revoked}`, the cookie cleared |
| `GET /api/account/me` | `{email, created_at, default_league, leagues: [...], preferences: [...], watchlist: [...]}` · 401 `signed_out` |
| `PUT /api/account/leagues {leagues: [{league, season, name, team_id, team_name, scoring_label, total_rosters, default}]}` | upsert by `league_key`; `team_id` only changes when sent |
| `DELETE /api/account/leagues/{league_key}` · `PUT /api/account/default {league, season}` | the default passes to the next league when the default is removed |
| `PUT / DELETE /api/account/preferences` | `{scope, key, value}` · `?scope=&key=` |
| `PUT / DELETE /api/account/watchlist` | `{player_key, league}` · `?player_key=&league=` |
| `DELETE /api/account` | every row of the account gone; the cookie cleared |
| off | every route but `status`: 404 `accounts_off` |

**League keys** (`provider:season:external_id`, from the app's key): `1389709692405551104` → `sleeper:2026:1389709692405551104`,
`mfl:70587` → `mfl:2026:70587`, `espn:4242` (or IK-1's `espn:2026:4242`) → `espn:2026:4242`, `yahoo:461.l.4242` →
`yahoo:2026:461.l.4242`; the season is the one sent, else the current NFL season.

**Next (phase 2)**: Google as a second button (B); `connections` for Yahoo (the refresh token encrypted with a
`LEAGUE_LAB_CONNECTION_KEY`, so a connection follows the account) and ESPN; the profile's "last sync" from a small
per-league job; a watchlist button on the player card; the team picker's change on a shared link's league offered,
not pushed; the beta password's future (once accounts are live, the PO decides whether the gate stays).


## Built, phase 2 (Wave I-L, IL-5, 2026-10-05)

Connections follow the account, the watchlist has its screen. Verified live: **no** (accounts are off on the server
until the Resend key; Yahoo until the app is registered; ESPN private until `LEAGUE_LAB_ESPN_PRIVATE=on`).

**Connections** (`api/league_lab_api/connections.py`; the table IK-4 reserved, unchanged — no `alter`). The cookies
stay the request-path carriers (IK-2's `ll_yahoo`, IK-1's `ll_espn`); for a signed-in person the row in
`accounts.connections` is the durable copy:

| When | What happens to the row | The cookie |
|---|---|---|
| Connect with Yahoo (`/api/yahoo/callback`) / "Read my private league" (`POST /api/espn/connect`), signed in | stored (one per provider per account: a new identity replaces the old), `status = active` | set as before |
| the same, as a guest | nothing | set as before (guests unchanged) |
| sign in (`POST /api/account/verify`) on a device that carries a connection cookie | stored: the guest's connection joins the account | kept |
| sign in on a device without one, the account has an `active` row | — | **re-issued from the row** (Yahoo: the refresh token only — its first read refreshes the hour-long access token) |
| `GET /api/account/me` (every page load, signed in) | updated when the cookie carries a newer Yahoo refresh token; **never created** (a device that kept its cookie after a disconnect elsewhere does not put it back) | re-issued when missing (60 / 30 days < the 90-day session) |
| Yahoo refuses the refresh (IK-2's middleware clears the cookie) | `status = expired`, never restored; the account page says "needs reconnecting" with the link | cleared |
| Disconnect (`POST /api/yahoo/disconnect` / `POST /api/espn/disconnect`), signed in | deleted (`removed: 1` in the answer) | cleared |
| `DELETE /api/account` | gone with the user (`connections.user_id … on delete cascade`, in the schema; `test_il5` checks the constraint and the rows) | — |

* **At rest**: `secret_enc` = `sealed.seal("account-connection|<provider>", …)` (IK-1's encrypt-then-MAC, keys
  derived from `LEAGUE_LAB_API_SECRET`; a cookie never opens as a row, a row never as a cookie), re-sealed at every
  write, 400 days at most. Sealed: Yahoo `{r: refresh token, g: guid}`, ESPN `{s2, swid}` — the least that restores the
  connection. `external_user_id`: Yahoo's GUID; ESPN `espn-<16 hex>` = an HMAC of the SWID (never the SWID). No token,
  cookie or sealed value is logged, returned or printed; a failed write logs the exception's class and never fails the
  request it rides on. The design's separate `LEAGUE_LAB_CONNECTION_KEY` was not needed: one secret, a purpose per use.
* **ESPN** only behind its switch: with `LEAGUE_LAB_ESPN_PRIVATE` off nothing is stored or restored (rows already
  there stay, unused). **Yahoo** is restored only when this server can talk to Yahoo (`yahoo_connect.configured()`).
* **`ll_session`'s path is `/api`** (was `/api/account`): the Yahoo callback and the two disconnect routes have to
  know who is signed in. Sign-out clears the cookie at both paths. No live session existed under the old path
  (accounts were never on).
* `GET /api/account/me` gains `connections: [{provider, external_user_id, connected_at, status, last_sync_at}]`; the
  account page lists them ("Yahoo: connected 2026-10-05 — it comes back on any device you sign in on.") with
  "Reconnect" on an expired one, and says what an account keeps (the watchlist and a connection only if you make one,
  encrypted — "nothing else"; About's line too).

**The watchlist** (`/watchlist`, `web/src/routes/Watchlist.svelte`; `GET /api/account/watchlist?league=&team=`,
`api/league_lab_api/watchlist.py`):

* The drawer's **☆ Watch / ★ Watching** (signed in only) saves the player for the account with `league: null` — a
  player, whatever league is on screen; un-watching removes every row of him (one saved with a league too). The ⋯
  menu's **Watchlist** (accounts on); the account page links it with the count.
* Each row: the name (a tap opens the drawer — II-2's link hook), the position, the NFL team, **his status today** (the
  card's injury designation after the availability overlay; "No injury designation" when none), **this week's
  projected points in the league on screen** ("8.3 projected · week 4"), the **league-relative note** ("Free agent" /
  "Rostered by Run Bijan Run" / "On your team" / "Not in this league's player pool"), **Remove**. The head: "5 players
  · projected points in League of Scrubs scoring, week 4. Tap a name for his card."
* **The league**: the one on screen (the switcher's — after a sign-in on a new device that is the default league); the
  API takes `league`, else the account's default. Decided so the drawer a row opens shows the same number as the row
  (both go through the card's code path: a house league from the database, any other on demand — Sleeper, MFL, ESPN,
  Yahoo).
* **Cost**: one card per player, 30 at most per answer (`count` says how many are saved; the head says "the first 30
  of N"); a row that cannot be read says why and the others answer.
* Signed out: "Sign in to keep a watchlist on any device: sign in with your email, then tap ☆ Watch on any player's
  card." (no Watch in the drawer). Accounts off: "A watchlist comes with an account, and accounts are not on for this
  server yet." (no menu item).
* GA (INF-1's `track`): `watchlist_add` / `watchlist_remove` with `content_type: "player"`, `item_id` (the gsis id or
  unit key) and `origin` (the screen) — ids only.

**Next**: the profile's "last sync" (still nothing writes `leagues.last_sync_at`); a watchlist row's news line and
"what changed since you saved him"; Google sign-in (B); a per-league watchlist view if managers ask for one (the rows
can carry a league already).


## Passkeys (Wave I-M, IM-4, 2026-10-06)

Andrew: "some sort of login/account so people can save their stuff and not have to reconnect each time." The emailed
link waits for a Resend key; a **passkey** needs no email and no third party, so accounts can be on tonight. A passkey
is a key pair the person's own device makes for this site and unlocks with its own lock (Face ID, a fingerprint, a PIN);
the private key never leaves the device (or the person's iCloud Keychain / Google Password Manager, which sync it); we
keep the public key. Verified live: **no** (the nightly must first apply the new part of `scripts/hosted_accounts.sql`:
`docs/HOSTING.md` § "Accounts").

**The switch.** `LEAGUE_LAB_ACCOUNTS=auto` (the default) turns accounts on when `LEAGUE_LAB_API_SECRET` is set and the
tables exist, **with the ways in the server has**: `passkey` when the passkey part of the script has run (the two tables,
the user handle column, an optional email; one query, re-checked every minute until it is there), `email` when
`LEAGUE_LAB_RESEND_API_KEY` is set. `GET /api/account/status` adds `methods` (`["passkey"]`, `["email"]`, both, or `[]`),
`why` (per method: `not_ready` / `no_mailer` / null), `passkey_home` (where passkeys work) and `passkey_here` (a hint:
this page's address is one of them). No method → `enabled: false, reason: "not_ready"` (the passkey tables are missing)
and the web shows no sign-in, as before. A passkey-only server answers the link routes with 404 `email_off`; a server
whose passkey tables are missing answers the passkey routes with 404 `passkeys_off` — never a 500. `off` and `on` are as
in phase 1 (`on`: also `http://localhost:<port>` for passkeys — tests and the fixture API only).

**The flows** (`api/league_lab_api/passkeys.py`, `web/src/lib/account.svelte.ts`, `routes/Account.svelte`):

| What the person does | What happens |
|---|---|
| **Create an account with a passkey** (signed out) | `POST /api/account/passkey/register/options` → the device's sheet (`navigator.credentials.create`) → `POST …/register/verify` → a new account with no email, the passkey, a session (`ll_session`, 90 days, as the link's); then, by themselves, this browser's leagues (the league on screen as the default), its Stats views (the phase-1 save and restore) and its Yahoo / ESPN connection (IL-5's sync, `adopt`) go to the account |
| **Sign in with a passkey** (any device) | `POST …/login/options` (no account named: discoverable credentials) → the device offers the passkeys it holds for this site (`navigator.credentials.get`) → `POST …/login/verify` → a session; the account's leagues, teams, default and views come into the browser (phase 1's restore); the account's connection comes back (IL-5) |
| **Add another passkey** (signed in) | the same register ceremony with `purpose: add`: the account's user handle, its passkeys excluded (a device that already holds one says so) |
| the list | label ("iPhone · Safari"), added, last used (`GET /api/account/me` → `passkeys: [{id, label, created_at, last_used_at, synced}]`, `sign_in: {passkeys, email}`) |
| **Remove** | `DELETE /api/account/passkeys/{id}`; the account's **only way in** cannot be removed (409 `last_sign_in`, the screen shows "Your only way in" instead of Remove); a removed passkey stays in the device's list but opens nothing |
| **Add an email** (passkey-only, the server has a mailer) | the link form; the link opened while signed in adds the address to this account (`POST /api/account/verify` → `{ok, email, added: true}`) unless another account has it (409 `email_taken`, and the link is kept for signing in to that account) |
| sign out, sign out everywhere, delete | phase 1's routes; delete takes the passkeys and any open challenge with the account (`on delete cascade`) |

**What is stored** (`scripts/hosted_accounts.sql`, IM-4 part; the app role gets `SELECT / INSERT / UPDATE / DELETE` on
the two new tables like the other eight):

* `accounts.users`: `email` becomes optional (`alter … drop not null`: every row kept; the unique constraint and the
  shape check let NULL through); `webauthn_handle bytea` (32 random bytes, unique; made with the account, or when an email
  account adds its first passkey) — the WebAuthn user handle, never the email.
* `accounts.passkeys`: `id`, `user_id` (cascade), `credential_id` (unique), `public_key` (COSE, as the authenticator sent
  it), `sign_count`, `transports` (the browser's hint, from a fixed list), `label` (fixed words from the User-Agent at
  creation — never the User-Agent), `backed_up` (a synced passkey), `created_at`, `last_used_at`. No secret.
* `accounts.passkey_challenges`: `challenge_hash` (SHA-256 of the 32-byte challenge — never the challenge), `purpose`
  (`create` / `add` / `login`), `user_id` (`add` only), `user_handle`, `browser_hash` (SHA-256 of the HttpOnly
  `ll_passkey` cookie's random value), `rp_id`, `origin`, `ip_hash` (HMAC), `created_at`, `expires_at` (5 minutes),
  `used_at`. Deleted after a day by the script's retention.
* Size: a few hundred bytes per passkey, a few hundred per challenge for a day.

**The checks, in order** (each refusal has its own words: docs/WORDS.md § "Passkeys"): the request is same-site (below);
the `Origin` is on the allow-list (`passkey_wrong_site`); the per-address limit; the answer's shape and size (32 KB;
`passkey_bad`); its challenge, looked up by hash and **spent under a row lock before anything else** (unknown or used:
`passkey_challenge`; older than 5 minutes: `passkey_expired`; another purpose: `passkey_challenge`); the `ll_passkey`
cookie matches (`passkey_browser`); the request's `Origin` is the one the challenge was made for; then py_webauthn: the
client data's type, challenge and origin, the rp id hash, user presence, the attestation (`none`) or the signature over
the stored public key, and the **counter** (a counter that does not go up while either is above zero: `passkey_cloned`,
logged with the passkey's row id). Sign-in also requires the returned user handle to be the account's
(`passkey_unknown`); `add` requires the session to be the account's (`signed_out`).

**Where passkeys work.** `LEAGUE_LAB_PASSKEY_ORIGINS` — comma-separated origins, https only, default
`https://isuckatfantasy.io`. A ceremony's origin is the request's `Origin` header only when it is on the list; the rp
id is the shortest listed host it belongs to (add `https://www.isuckatfantasy.io` and both share `isuckatfantasy.io`). A
passkey belongs to its rp id: one made on `isuckatfantasy.io` does not work on any other domain, so **the domain is part
of every account** — changing it later strands the passkeys (the email, when there is one, still works). Render's own
`*.onrender.com` address is not on the list: it says "Passkeys work on isuckatfantasy.io only. Open
https://isuckatfantasy.io/account to use one."

**Same site** (item 5: safe with the beta gate open, by itself). Every state-changing route under `/api/account` —
phase 1's, IL-5's and these — refuses with 403 `cross_site` a request a browser marks as cross-site: `Sec-Fetch-Site`
`same-origin` / `none` passes; otherwise the `Origin` must be on the allow-list, `LEAGUE_LAB_PUBLIC_URL`, or this
request's own `Host` (no `Sec-Fetch-Site` sent); `Origin: null` never passes. A request with neither header is not a
browser's, so it carries nobody's cookie by accident (tests, curl). Limits (the in-memory bucket, keyed by an HMAC of
the address): registration options 10 an hour, sign-in options 30 an hour, answers 20 a minute (the link checks'
bucket); 10 passkeys per account.

**Recovery, honestly.** A passkey-only account whose person loses every device that holds a passkey for it is gone: we
hold no email to send a link to, and nothing else proves who they are. The screen says so in one line under the list
("If you lose every device that holds your passkeys, this account cannot be recovered: add one on a second device, or
add your email below") and offers "Add an email" when the server has a mailer. Synced passkeys (iCloud Keychain,
Google Password Manager — `backed_up`) survive a lost phone.

**The browser.** `navigator.credentials` and `PublicKeyCredential` only (no npm dependency; base64url by hand, so
browsers without `PublicKeyCredential.parseCreationOptionsFromJSON` work). A browser without them (an app's built-in
browser often has none) gets one line and no button; the email form stays when the server has a mailer. No password
field anywhere.

**Tests.** `api/tests/test_im4.py` (a software ES256 authenticator: every ceremony and every refusal above, an account
without email through every account route, the cross-site guard on every state-changing route, the limits, localhost
only under the test switch, the status matrix, the schema); `web/e2e/im4/fixtures.spec.ts` (Chromium's virtual
authenticator through CDP against the real API on `http://localhost:8754`, at 375 and 1300: create with two leagues, sign
out and in, a second device with the synced passkey gets the leagues back, add a passkey, remove one, the removed one
refused in words, delete; and a browser without WebAuthn).

**Next**: the profile's "last sync" (still open from phase 2); `PublicKeyCredential.signalUnknownCredential` (Chrome,
Safari) to tell the device a removed passkey is gone; conditional mediation (the passkey offered in the browser's
autofill) once there is a sign-in field to hang it on; Google sign-in (B) if people ask.

