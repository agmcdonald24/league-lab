# IM-4 — accounts that work tonight: passkeys (Wave I-M, hand-back)

**Task**: IM-4 of `/home/claude/waveIM/BRIEF.md` (Wave I-M). **Branch**: `dev/IM4` from `main` `ab50682`, worktree
`/home/claude/wt-im4`, database `league_lab_im4` (the only one written). **Docs touched**: `docs/ACCOUNTS.md`
§ "Passkeys" (new), `docs/HOSTING.md` § "Accounts" (the switch, one env row, a passkeys paragraph), `docs/WORDS.md`
§ "Passkeys" (new), `CHANGELOG.md` (one bullet under `## 2026-10-06 — Wave I-M`).

## Done / not done against the package

| # | Item | State |
|---|---|---|
| 1 | `passkeys.py` on py_webauthn: registration + authentication, discoverable credentials, UV preferred, attestation none; challenge server-side, single use, 5 min; sign count; rp id + origins from `LEAGUE_LAB_PASSKEY_ORIGINS`; another host → clear words; localhost only under the test switch | **done** |
| 2 | Schema: `accounts.passkeys`, `accounts.users.email` optional, a WebAuthn user handle per user, grants | **done** (+ `accounts.passkey_challenges`) |
| 3 | The switch: `auto` = secret + tables, methods `passkey` / `email`; status says why; no 500s before the nightly applies the SQL | **done** |
| 4 | The account in the app: create with a passkey (this browser's leagues, default, views, connection saved), sign in on another device, add another, list with labels and last use, remove (never the last way in), sign out, delete, no-WebAuthn line, email form when a mailer exists, both offered plainly | **done** |
| 5 | Session and limits as phase 1; ceremonies rate-limited per IP hash (10 / 30 an hour); an Origin check on every state-changing account route | **done** |
| 6 | `api/tests/test_im4.py` with a software authenticator; `web/e2e/im4/` with Chromium's virtual authenticator at 375 and 1300 | **done** |
| 7 | ACCOUNTS § Passkeys (flows, storage, recovery said on screen + "add an email" when a mailer exists), WORDS | **done** ("Add an email" is built: API + screen) |

## Files

* `api/league_lab_api/passkeys.py` (new): the four ceremony routes + `DELETE /api/account/passkeys/{id}`, registered on
  `accounts.router` (so **no edit to `main.py`**: accounts.py imports passkeys at its end; either import order works).
* `api/league_lab_api/accounts.py`: the switch by method (`READY_SQL`, `passkeys_ready`, `methods`, `why_not`), the
  status fields, `same_site` (the router's dependency), `allow(key, n, per_s)`, `me()` → `passkeys`, `sign_in`;
  `verify(…, attach_to)` ("add an email"); the email routes need a mailer (`email_off`).
* `scripts/hosted_accounts.sql`: the IM-4 part (below). `api/pyproject.toml`, `api/uv.lock`: `webauthn>=3.0.1`.
* `web/src/lib/account.svelte.ts`, `web/src/routes/Account.svelte`, `web/src/components/AccountEntry.svelte`.
* Tests: `api/tests/test_im4.py` (new, 20 tests), `web/e2e/im4/fixtures.spec.ts` (new, 2 tests × phone / desktop).
* Outside my files (smallest edits): `api/tests/test_ik4.py` (3 assertions follow the new switch / the script's
  allowed `alter`s / 10 tables; its recording test records an email-only server), `web/fixtures/ik4/*.json`
  (re-recorded: + `methods`, `why`, `passkey_home`, `passkey_here`, `passkeys`, `sign_in`), `docs/HOSTING.md`,
  `docs/WORDS.md`, `CHANGELOG.md`.

## Schema in / out (`scripts/hosted_accounts.sql`, idempotent, applied twice on the clone)

```
alter table accounts.users alter column email drop not null;                 -- keeps every row
alter table accounts.users add column if not exists webauthn_handle bytea;    -- + unique index, + a 16–64 byte check (DO block)
create table if not exists accounts.passkeys (id, user_id → users on delete cascade, credential_id unique, public_key,
  sign_count, transports text[], label, backed_up, created_at, last_used_at)
create table if not exists accounts.passkey_challenges (challenge_hash pk = sha256, purpose create|add|login, user_id,
  user_handle, browser_hash = sha256(ll_passkey cookie), rp_id, origin, ip_hash, created_at, expires_at, used_at)
grant select, insert, update, delete … accounts.passkeys, accounts.passkey_challenges to league_lab_app
delete from accounts.passkey_challenges where created_at < now() - interval '1 day';   -- retention
```

Sizes: a passkey row ≈ 300 B, a challenge row ≈ 250 B (kept a day). Nothing new for the analytics sync.

**What must run on Neon, and how the server notices.** Nothing new to add: the nightly's existing IK-4 block
(`scripts/sync_to_hosted.sh`: `psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction -f
scripts/hosted_accounts.sql`) runs the new part as the owner on the next nightly after the merge (or Actions → nightly →
Run workflow). The server runs `accounts.READY_SQL` once a minute until it sees both tables with the app role's INSERT,
`users.webauthn_handle` and a nullable `users.email`; then `/api/account/status` → `"enabled": true, "methods":
["passkey"]` and **accounts are on for everyone** (Render already has `LEAGUE_LAB_API_SECRET`). Before that: `enabled:
false, reason: "not_ready", why: {passkey: "not_ready", email: "no_mailer"}` — exactly today's behaviour (no sign-in
shown). Optional: the sync's log line could also print `(select count(*) from accounts.passkeys) || ' passkeys'`.

## Decisions (each reversible)

* **Challenge storage: a table, not a sealed cookie** — single use needs server state (a sealed cookie can be replayed
  until it expires). Looked up by the SHA-256 of the answer's challenge, spent under `select … for update` before any
  verification (a failed answer spends it too), then checked against purpose, browser cookie, site, expiry.
* **Bound to the browser** with a random value in `ll_passkey` (HttpOnly, SameSite=Strict, path `/api/account/passkey`,
  5 min) — another browser cannot finish a ceremony (login CSRF / relayed challenges).
* **The rp id** = the shortest allow-listed host the origin belongs to. A passkey is tied to it: moving the site off
  `isuckatfantasy.io` strands every passkey (said in HOSTING / ACCOUNTS).
* **Same-site guard** (`accounts.same_site`): Go 1.25's CrossOriginProtection rule with our allow-list —
  `Sec-Fetch-Site: same-origin|none` passes; otherwise `Origin` on the list, the public URL, or the request's own Host
  (no `Sec-Fetch-Site`); `Origin: null` never; neither header = not a browser (passes; carries nobody's cookie).
  Keeps Render's `*.onrender.com` address working for the emailed link.
* **Removing the last way in is refused** (409 `last_sign_in`, the screen shows "Your only way in"), rather than
  allowed with a warning: an account with no way in cannot be fixed later.
* **"Add an email"**: the existing link flow; opened while signed in to a passkey-only account it adds the address
  (`{ok, email, added: true}`), unless another account has it (409 `email_taken`, the link not spent).
* **py_webauthn imported lazily** (first ceremony): it brings `cryptography` + pyOpenSSL, measured **+16 MB RSS** next
  to the app's libraries (+26 MB alone); start-up imports none of it.
* `user.name` on the device: "isuckatfantasy · Oct 5, 2026" (or the email). Labels: fixed words from the User-Agent.
* The status recordings for IK-4's e2e stay an email-only server (its screens are the link flow).

## Commands and evidence

```
cd api && uv add webauthn                         # 3.0.1 (+ cbor2 6.1.5, cffi 2.1.1, cryptography 50.0.2, pyasn1 0.6.4,
                                                  #   pyasn1-modules 0.4.2, pycparser 3.0, pyopenssl 26.4.0)
psql "<pipeline dsn>" -v ON_ERROR_STOP=1 -q --single-transaction -f scripts/hosted_accounts.sql   # twice, both OK
cd api && OMP_NUM_THREADS=1 PYTHONPATH=. uv run pytest -q tests/test_im4.py tests/test_ik4.py tests/test_il5.py
cd web && npm run lint && npm run build
cd web && FIXTURES_PORT=8640 npx playwright test --config playwright.fixtures.config.ts e2e/im4 e2e/ik4 e2e/il5
uv run ruff check src app tests api ; uv run python scripts/copy_standard.py --check
```

* Dependency: wheels (x86_64, cp313 / abi3 / py3) **5.9 MB** (cryptography 4.75 MB), installed **≈ 19 MB** (cryptography
  15 MB). All are binary wheels: `python:3.13-slim` needs no compiler; **no Dockerfile change** (`uv sync --frozen`).
* RESULTS (filled in below).

## Limitations

* Verified live: **no** (needs the merge and a nightly). Real devices (iPhone Safari, Android Chrome, Windows Hello)
  were not tried: Chromium's virtual authenticator and a software ES256 key only.
* "Add an email" has no e2e (the stub mailer's link stays in the API process); `test_im4` covers it.
* The ⋯ menu's "Sign in to save your leagues" (TopBar, IM-3's file) and the watchlist's signed-out line ("…sign in with
  your email, then tap ☆ Watch…", `Watchlist.svelte`, not mine) still say email on a passkey-only server.
* No conditional mediation (autofill), no `signalUnknownCredential` after a removal (a removed passkey stays listed on
  the device; the screen says so).
* The client address for the limits is `accounts.client_ip` (the first `X-Forwarded-For` hop), as phase 1; IM-3 is
  deciding the trustworthy header — one place to change.

## Next task

The PO merges, the nightly applies the SQL, then on a phone: `/account` → Create an account with a passkey → a laptop
(same iCloud / Google account, or "use a phone" QR) → Sign in with a passkey → the leagues come back.
