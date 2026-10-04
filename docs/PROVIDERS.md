# Fantasy platforms: what each one gives League Lab, and whether to build ESPN / Yahoo (Wave I-I, II-5, 2026-10-04)

*(The fifth review, § 9: "Use reusable provider adapters with explicit capabilities … Unsupported data should be clearly
unavailable rather than silently substituted", and "ESPN: … Run an access/authentication feasibility task covering
public and private leagues, synchronization, scoring, and permitted use." This page is the answer. It informs; it is not
a request to any provider — Andrew has no licence conversation open and plans none before something is
production-ready.)*

## The matrix

Sleeper and MyFantasyLeague **as built** (the code is the source: `src/league_lab/platforms.py` `capabilities()`,
served at `GET /api/providers`, pinned by `api/tests/test_ii5.py`). ESPN and Yahoo **as researched** — nothing is built
for them, and the product says "not supported yet" (the setup screen's "ESPN or Yahoo?").

| | Sleeper (built) | MyFantasyLeague (built) | ESPN (researched) | Yahoo (researched) |
|---|---|---|---|---|
| **Official API** | Yes, documented, read-only, no key | Yes, documented export API, read-only for us | **No.** Undocumented endpoints only | Yes, documented (OAuth 2.0) |
| **How a user connects** | Username (public lookup → stable `user_id`) or a league link / id | League link, id or name (MFL's public league search) | Public league: league id. Private: the manager's login cookies (`espn_s2`, `SWID`) | OAuth sign-in to Yahoo, per user, after Yahoo approves our app |
| **Private leagues** | None: every Sleeper league is readable | The commissioner allows API access; MFL also issues a per-league API key (not used) | Cookies only — we will not ask for them | Yes, with the user's OAuth grant |
| **Scoring** | Yes — the league's settings; an unpriced setting is listed on the card | Partly — MFL rules read into our scoring spec; estimated / unpriced pieces listed | In the league settings payload (community libraries) — not verified here | League settings resource (stat categories / modifiers) |
| **Lineup slots** | Yes — every offensive slot, superflex; IDP left out and said | Partly — ranges (2–4 WR) as minimum + FLEX; IDP left out and said | Settings payload — not verified | `roster_positions` in settings |
| **Matchups** | Yes — opponent, every played week's points | Partly — schedule and opponent; the week's live points not read | Box scores / matchups (public leagues: "Box Scores" are among the pages a public league shows) | Scoreboard resource |
| **Players** | Yes — Sleeper's directory → nflverse ids | Partly — MFL ids → Sleeper ids; an unmatched player is listed, unvalued | ESPN player ids — a new id map needed | Yahoo player keys — a new id map needed |
| **Waivers** | Yes — free agents; claim type and time from the settings | Partly — free agents = unrostered; MFL's waiver type read; claim time not shared | Free agents in the community libraries — not verified | Players collection with status filters |
| **Transactions** | Yes — adds, drops, trades | **No — "Transactions: not available for MFL leagues yet"** | "Recent activity" in the community libraries — not verified | Transactions resource (adds, drops, trades) |
| **Team assets** | Partly — team defenses; draft picks and FAAB budgets not read on demand | Partly — team QB / K / DEF priced as players; picks and blind-bid budgets not read | Unknown | Draft results resource; FAAB in team data — not verified |
| **News** | Yes — ESPN's player news by player (provider-independent) | Yes — the same | (the same feed) | (the same feed) |
| **Writes (lineups, claims, trades)** | None: the API cannot write | Not used (MFL has import calls; we never write) | None that is authorized | "Read access only. Write access is not available at this time" |
| **Terms for commercial use** | "free to use for non-commercial purposes"; commercial use → "reach out to us directly to discuss licensing" | Not read from primary source (robots-blocked from here) | Disney terms prohibit automated access and commercial use | API terms: no deriving income without Yahoo's written permission |
| **Our verdict** | Keep; licence before charging | Keep; read the terms before charging | **Public leagues read-only at most, not built now; never cookies** | Feasible after accounts + Yahoo's approval; not built now |

How the product uses it: the setup screen lists what the chosen platform gives ("What isuckatfantasy reads from MFL
leagues — 1 not available yet"), and a screen that would show an empty list for a feature a platform does not give says
the `unavailable` line instead (League's "Latest moves" on an MFL league: "Transactions: not available for MFL leagues
yet." — it said "No completed moves yet this season" before). Statuses: `yes` (read as the provider has it), `partial`
(read, with the gap stated in `words`), `no` (not read; `unavailable` is the sentence). Adding a provider = an adapter
that answers the `Router` calls in Sleeper's shapes (`platforms.py` module docstring) + its `_CAPS` entry; **no
"supported" badge for a placeholder** (the review): ESPN and Yahoo are `not_supported` with every feature `no`.

## Sleeper

**Built**: `sleeper_client.py` (caches, a token bucket of 300 calls a minute, stale-on-error) — `docs/SLEEPER_TERMS.md`.
**Read 2026-10-04** at <https://docs.sleeper.com/>: "The Sleeper API is a read-only HTTP API that is free to use for
non-commercial purposes"; "For commercial use of the Sleeper API, please reach out to us directly to discuss
licensing"; "No API Token is necessary, as you cannot modify contents via this API"; "stay under 1000 API calls per
minute, otherwise, you risk being IP-blocked"; `GET /v1/user/<username>` → the user (and `user_id`), `GET
/v1/user/<user_id>/leagues/nfl/<season>`. No OAuth, so a username lookup is **not** proof of who someone is
(`docs/ACCOUNTS.md`). Next: when accounts exist, store the `user_id` the username resolved to (stable across a
username change), not the username.

## MyFantasyLeague

**Built**: `mfl_client.py` + `platforms.MFLLeagues` — `docs/MFL_TERMS.md`, `docs/ANY_LEAGUE.md` § MyFantasyLeague.
**Read 2026-10-04**: MFL's own API page (`api.myfantasyleague.com/<year>/api_info`) refuses automated readers
(robots.txt), so it was **not** read from here. Secondary source — the ffverse `ffscrapr` package's MFL connection
(<https://ffscrapr.ffverse.com/reference/mfl_connect.html>): `APIKEY` "allows access to private leagues. Key is unique for
each league and accessible from Developer's API page"; a `user_name` + `password` "will attempt to retrieve [an]
authentication token"; a `user_agent` "may find improved rate_limits if verified"; "suggested is 60 calls per 60
seconds" (ours: 60 a minute). So an **authorized private-league path exists on MFL**: the per-league API key, which the
league's owner copies from MFL's developer page — a credential MFL designed for exactly this, scoped to one league,
revocable. If a beta user's MFL league is private, that key is the path to offer (stored as a connection secret,
`docs/ACCOUNTS.md`); we never ask for an MFL password. Before charging, read MFL's terms from a browser and record the
clause in `docs/MFL_TERMS.md` (what a commercial reader owes; whether to register our user agent).

## ESPN — the feasibility outcome

**What was read (2026-10-04, WebFetch):**
* ESPN support, "Making a Private League Viewable to the Public"
  (<https://support.espn.com/hc/en-us/articles/360000991871-Making-a-Private-League-Viewable-to-the-Public>): only
  "League managers" change it (web only: League → Settings → Basic Settings → Edit → viewable to public **Yes**); then
  "non-members with a direct link can access League Office, Standings, Box Scores, and Team Pages"; "The list of team
  managers and league message boards is never visible to non-members"; "Making your league viewable does not make it
  joinable." This is a **visibility setting for web pages**, not an API or an integration contract (the review says the
  same).
* The community clients — `cwendt94/espn-api` (README and wiki, <https://github.com/cwendt94/espn-api/wiki>): "For
  private leagues you will also need two more parameters; your swid and espn_s2", found by "Right click … inspect …
  Application … Cookies … fantasy.espn.com" (discussion #150; the values "remain the same through different sessions";
  a Chrome extension now automates copying them). `ffscrapr`'s ESPN vignette
  (<https://ffscrapr.ffverse.com/articles/espn_authentication.html>): the two cookies, copied by hand from developer
  tools, "cannot be done programmatically at this time". `fflr` (<https://k5cents.github.io/fflr/>): base
  `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl`; "Data is only available for public leagues"; "As of
  August 1, 2025" ESPN restricted historical data and the `espn_s2` cookie is needed for it.
* Disney's Terms of Use (<https://disneytermsofuse.com/english/>, the terms ESPN's site links): you may not "access,
  monitor, copy or extract the Disney Products using a robot, spider, script, or other automated means"; not "use the
  Disney Products for any commercial or business-related use or build a business utilizing the Disney Products"; "you
  will not share your account or account information with others".
* No ESPN developer program, OAuth or API terms for fantasy leagues was found (none is linked from the support pages;
  the community libraries all describe the undocumented `lm-api-reads` endpoints).

**What it means:**
* **Public leagues**: readable without a login through undocumented endpoints that ESPN changes without notice (the
  August 2025 history change is one). Scoring, slots, rosters, matchups and box scores are in those payloads per the
  community libraries — not verified from here (ESPN's fantasy hosts are not reachable from the sandbox). A league is
  public only if its manager flips the setting; most are private by default.
* **Private leagues**: the only path is the manager's own session cookies — their logged-in ESPN identity, long-lived,
  not scoped to a league or to reading, and copied out of developer tools. Asking for them asks a user to break
  Disney's "will not share your account" clause and hands us a credential we could not protect well enough to justify.
* **Synchronization**: polling only (no webhooks, no change feed), against endpoints with no published limits.
* **Permitted use**: Disney's terms prohibit automated access and commercial use outright. Even public-league reads are
  outside them; a paid product reading ESPN needs a written agreement with ESPN / Disney, and no public path to one
  exists.

**The verdict.** We would support, at most, **ESPN public leagues, read-only, by league id**, labelled as an unofficial
read that may break, for the free beta only — and we are **not building even that now** (nothing on the setup screen
offers it; the matrix says "not supported yet"). We would **not** support pasting `espn_s2` / `SWID` cookies — not as the
normal path and not as a hidden option — nor any ESPN write, nor ESPN in a paid product without a written agreement.
**Related, already shipped**: the player news line and the injury overlay read ESPN's public `site.api.espn.com` feeds
(`docs/ESPN_TERMS.md`); the same Disney clauses apply to them — a PO / Andrew decision before anything is charged for.

## Yahoo — the note

**Read 2026-10-04**: <https://sports.yahoo.com/developer/access/> — "Each application is reviewed by the Yahoo Fantasy
Sports team … incomplete or insufficiently detailed submissions cannot be evaluated and will be closed without further
correspondence"; the application states the product, the data needed and the user base ("whether access is limited to
personal or single league use"); "The Yahoo Fantasy Sports API currently provides read access only. Write access is not
available at this time." <https://sports.yahoo.com/developer/> — "uses OAuth 2.0 to authorize access to fantasy data";
throttling "if individual usage is excessive"; attribution "Fantasy data provided by Yahoo Fantasy" with a link.
<https://sports.yahoo.com/developer/docs/> — `https://fantasysports.yahooapis.com/fantasy/v2`: game, league (settings,
standings, scoreboard, teams, players, draft results, transactions), team (roster), player, transaction resources.
Yahoo's developer API terms (<https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html>): no
"derive income from the use or provision of the Yahoo APIs" without written permission; Yahoo user data not marked
storable may not be kept "within 24 hours after the time at which you obtained the data" (i.e. beyond 24 hours);
rate limits "at Yahoo's absolute and sole discretion".

**What it means**: technically the cleanest provider to add (documented, OAuth, every resource the matrix needs), but it
needs three things we do not have: **accounts** (an OAuth token belongs to a signed-in user — `docs/ACCOUNTS.md`),
**Yahoo's approval** of an application, and for a paid product **written permission**. The 24-hour rule means our
caches of Yahoo league data are short-lived by contract (the on-demand design already caches minutes, not days).
What it needs on Render: `LEAGUE_LAB_YAHOO_CLIENT_ID` / `_SECRET` (secrets), the redirect URI
`https://isuckatfantasy.io/api/connect/yahoo/callback` registered with Yahoo; on Neon: the encrypted refresh token per
connection. **Verdict**: not built now; the next provider after accounts exist, by an honest application ("a beta
for a few leagues") when Andrew wants it.

## Other platforms

Fleaflicker, NFL.com, CBS and the rest: not assessed. Add one only after the same table is filled from its official
docs and there is demand; never a "supported" badge before the adapter passes the fixtures.

## Sources read (2026-10-04, through WebFetch; nothing was sent to any provider)

docs.sleeper.com · support.espn.com (the article above) · disneytermsofuse.com/english · github.com/cwendt94/espn-api
(README, wiki, discussion #150) · ffscrapr.ffverse.com (MFL `mfl_connect`, MFL `get_endpoint`, ESPN authentication) ·
k5cents.github.io/fflr · sports.yahoo.com/developer, /developer/access, /developer/docs · legal.yahoo.com (developer API
terms). Refused by robots.txt: api.myfantasyleague.com / www.myfantasyleague.com `api_info`.
