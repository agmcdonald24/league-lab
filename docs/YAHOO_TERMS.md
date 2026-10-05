# Yahoo Fantasy: what we read, with whose permission, and what the terms say (Wave I-K, IK-2, 2026-10-05)

**What isuckatfantasy does.** Reads a Yahoo league through Yahoo's **official Fantasy Sports API**
(`https://fantasysports.yahooapis.com/fantasy/v2/…?format=json`), **read-only** (OAuth scope `fspt-r`, "Fantasy Sports —
Read"), with the **manager's own permission**: the manager taps *Connect with Yahoo*, signs in at Yahoo and allows the
app; Yahoo hands us a token for that manager. What we read: the league's settings (scoring, roster positions,
playoffs, FAAB), its teams and managers' nicknames, each team's roster for the week, the scoreboard by week, the
standings, the recent transactions, the first 25 free agents, and the manager's own NFL leagues this season. No writes,
no lineup changes, no trades. Code: `src/league_lab/yahoo_client.py` (the client), `src/league_lab/yahoo_leagues.py` (the
translation into Sleeper's shapes), `api/league_lab_api/yahoo_connect.py` (the sign-in routes and the cookie).

**Whose leagues.** Yahoo's docs: "A particular user can only retrieve data for private leagues of which they are a
member, or for public leagues." Yahoo's OAuth 2.0 guide lists one grant, the authorization code — there is no app-only
(client-credentials) token — so **every read needs a signed-in Yahoo manager, even for a public league**. Once
connected, a manager can open his own leagues (picked from the list) and any public league by its link.
(Note: the `yfpy` README says public leagues need no app setup; that is not in Yahoo's OAuth 2.0 docs and could not be
tried from here — the PO's check in HOSTING § Yahoo settles it; until then: sign-in required.)

**Where the tokens live.** Only in the manager's browser: the `ll_yahoo` cookie, encrypted and signed with the server's
`LEAGUE_LAB_API_SECRET` (HttpOnly, SameSite=Lax, Secure, 60 days). Never in the database, a log line, an analytics event
or a response body; nothing about the connection is kept on the server this wave (accounts persist it next wave —
`docs/ACCOUNTS.md`). *Disconnect Yahoo* clears the cookie; Yahoo documents no revocation endpoint for OAuth 2.0, so a
manager who wants Yahoo itself to forget the app removes it in his Yahoo account's app permissions.

**How much we call.** One token bucket of **60 calls a minute** per process (`LEAGUE_LAB_YAHOO_PER_MIN`); HTTP 429 or
Yahoo's 999 ("Request denied") stops all Yahoo calls for a minute (the last answer is served when there is one). Caches
in memory only, by kind: the game key and game weeks a day (not user data), settings an hour, teams and standings 10
minutes, rosters, scoreboard and transactions 5 minutes, free agents 15 minutes, the manager's leagues 10 minutes; at
most 400 answers held. **Each answer is cached for the manager who read it** — one manager's private league is never
served to another from the cache. A league opened once costs about 18 calls (settings, teams, 12 rosters, scoreboard,
standings, game weeks), then nothing for five minutes.

**Who we are.** Every call carries `User-Agent: league-lab/0.1 (isuckatfantasy beta; docs/YAHOO_TERMS.md)` and our app's
token. The beta is free and charges nobody.

## What the terms say (read 2026-10-05 through WebFetch; nothing was sent to Yahoo)

* **Yahoo Developer API Terms of Use** (`legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/`):
  - § 1.e.iv — no "derive income from the use or provision of the Yahoo APIs, whether for direct commercial or monetary
    gain or otherwise, unless the API Documents specifically permit otherwise or Yahoo gives prior, express, written
    permission". **A paid isuckatfantasy needs Yahoo's written permission before Yahoo leagues are part of it.**
  - § 1.g.v — no use that "exceeds reasonable request volume, constitutes excessive or abusive usage". No number is
    published; the Fantasy page says Yahoo "may temporarily throttle or limit access" if usage is excessive.
  - § 1.g — no use "in a product or service that competes with products or services offered by Yahoo, unless the API
    Documents specifically permit otherwise". **A risk to name**: lineup and waiver advice overlaps Yahoo Fantasy's own
    features; the Fantasy developer program exists for third-party tools, which is the argument the other way. The
    application to Yahoo (below) should describe the product plainly.
  - § 2.a — Yahoo user data not marked storable must be removed "within 24 hours after the time at which you obtained
    the data". **We hold it minutes to an hour, in memory.** Nothing Yahoo returns reaches the database or the nightly.
  - § 2.a–b — no storing Yahoo user data "in any data repository that enables any third party (other than the Yahoo
    user) access" unless the user permits it. **Hence the per-manager cache.**
  - § 2.d–e — "an easily accessible privacy policy … [that] accurately discloses your data collection, use, sharing,
    and retention practices", and "clear, express consent from the user" for OAuth access. Consent: Yahoo's own consent
    screen plus our words on the button. **The privacy line on About must say what this file says** (For the PO).
  - § 1.e.i–ii — the attribution policy, and one API key per application sent with every request.
* **Fantasy Sports developer page** (`sports.yahoo.com/developer/`): attribution — "Fantasy data provided by Yahoo
  Fantasy" with a link back to Yahoo Fantasy, the official logo unmodified when the API is referenced; throttling as
  above. **A Yahoo league's screens must carry that line** (the web is IK-3's; the words are in INTERFACES § IK-2).
* **Access** (`sports.yahoo.com/developer/access/`, read by II-5 on 2026-10-04): "Each application is reviewed by the
  Yahoo Fantasy Sports team … incomplete or insufficiently detailed submissions cannot be evaluated and will be closed";
  the application states the product, the data needed and the user base; read access only.
* **OAuth 2.0** (`developer.yahoo.com/oauth2/guide/`, `/flows_authcode/`): the authorization-code grant;
  `https://api.login.yahoo.com/oauth2/request_auth` (`client_id`, `redirect_uri`, `response_type=code`, `state`,
  `language`); `https://api.login.yahoo.com/oauth2/get_token` with `Authorization: Basic base64(client_id:client_secret)`
  and a form body (`grant_type=authorization_code`, `code`, `redirect_uri`; `grant_type=refresh_token`, `refresh_token`);
  the access token lives one hour, the refresh token "has a long lifetime" and survives a password change; the user can
  revoke it in his Yahoo account. Yahoo calls the client id / secret "Consumer Key / Consumer Secret" on the app page.

## What we do not do

No writes (Yahoo's API is read-only anyway). No Yahoo data in the database, the nightly, `usage.events`,
`events.events` or Google Analytics (no league key, team name or player list is sent as an event parameter). No sharing
of one manager's Yahoo data with another. No charging for anything that includes Yahoo leagues without Yahoo's written
permission. No scraping of Yahoo's website: only the documented API.

## Unverified until the PO opens a live league

Everything Yahoo-shaped here was built from Yahoo's docs and the open-source clients' documented shapes (`yfpy`,
`yahoo_fantasy_api`), against **synthetic** fixtures (`api/tests/fixtures/yahoo/`, built by
`api/tests/fixtures/make_ik2_yahoo_fixtures.py`): the JSON nesting of every resource, the stat id table
(`yahoo_client.STAT_KEYS`), the error answers (401 `token_expired`, a private league's refusal, 999), the 2026 game key
(read live from `game/nfl`; the fixture uses 461), the `W/R/T` / `Q/W/R/T` / `W/R` / `W/T` position names, and whether
an anonymous read of a public league works. HOSTING § Yahoo has the PO's check list.
