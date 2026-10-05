# Fantasy platforms: what each one gives League Lab, and whether to build ESPN / Yahoo (Wave I-I, II-5, 2026-10-04)

*(The fifth review, § 9: "Use reusable provider adapters with explicit capabilities … Unsupported data should be clearly
unavailable rather than silently substituted", and "ESPN: … Run an access/authentication feasibility task covering
public and private leagues, synchronization, scoring, and permitted use." This page is the answer. It informs; it is not
a request to any provider — Andrew has no licence conversation open and plans none before something is
production-ready.)*

## The matrix as built (Wave I-K, IK-3, 2026-10-05)

All four providers are built (`src/league_lab/platforms.py` `Router` + `capabilities()`, served at `GET /api/providers`,
pinned by `api/tests/test_ii5.py` / `test_ik3.py`). **ESPN and Yahoo are "as built, unverified live"**: their adapters
(IK-1 `espn_leagues.ESPNLeagues`, IK-2 `yahoo_leagues.YahooLeagues`) pass synthetic fixtures built from the documented
shapes, and nothing has been read from a real ESPN or Yahoo league yet. Their `status` is `unverified` and every feature
is `partial` with the words "— as built, not verified on a live league yet" (`platforms.UNVERIFIED`); the setup screen
says "New: not verified on a live league yet". **The PO flips a row** after opening a live league of that provider on
isuckatfantasy.io: `status` → `supported`, each verified feature's words without `UNVERIFIED` (and `yes` where it holds),
this table's cells without "(unverified live)".

**The switches (Wave I-L, IL-5)** — `platforms.provider_status()`, read on every `/api/providers` answer, so a flip is a
Render environment change and not a deploy:
* **`LEAGUE_LAB_PROVIDER_VERIFIED=espn,yahoo`** (default empty; any subset, comma-separated): after the PO's live check,
  the named provider's `status` is `supported` and the `UNVERIFIED` tail leaves every feature's words; the setup screen
  drops "New: not verified on a live league yet". A feature keeps its own status (`partial` stays partial — a `yes`
  is still a code change in `_CAPS`, with this table). Unset it to go back. Pinned by `test_ik3` / `test_ii5` /
  `test_il5` in both states.
* **`LEAGUE_LAB_ESPN_LEAGUES=off`** (IK-1's kill switch): ESPN's `status` is `off` with `off: "ESPN leagues: not
  available right now"`; the setup screen says it in place of the ESPN form ("… Sleeper and MyFantasyLeague leagues
  work as before."). `off` wins over verified.
* **Yahoo without its two secrets** stays `unverified` and its button says "Connect with Yahoo — coming soon" (the
  screen reads `yahoo_configured`): "coming soon" is the right word while the app is not registered.

| | Connect | Scoring | Lineup slots | Matchups | Players | Waivers | Transactions | Team assets | News |
|---|---|---|---|---|---|---|---|---|---|
| **Sleeper** (supported) | username, or a league link / id | yes | yes | yes | yes | yes | yes | partial (picks, FAAB not read on demand) | yes |
| **MyFantasyLeague** (supported) | league link, id or name | partial | partial (ranges as minimum + FLEX; exact on the three fixture leagues — `slots` note `range_gaps` names any difference) | yes: the schedule, every played week's points, **this week's live points** from MFL's live scoring (IL-2) | partial | partial: free agents = unrostered; waiver type, waiver order and blind-bid balance (when MFL's export carries them); MFL states no claim time | **yes: adds, drops, trades and waiver claims from MFL's transactions export** (IL-2; **verified live 2026-10-05** on `mfl:70587` and `mfl:21861` against MFL's own export — every move, time, team and blind bid; neither league has made a trade yet, so the trade rows rest on MFL's documented shape. MFL files a move made once a week's games have begun under the next week: the current week lists that file too) | partial | yes |
| **ESPN** (unverified) | league id or link (`fantasy.espn.com/football/league?leagueId=4242`); public leagues; private only behind `LEAGUE_LAB_ESPN_PRIVATE=on` with the user's own cookies | partial: ESPN's scoring items → our keys, the rest listed unpriced (as built, unverified live) | partial: slot ids → ours (OP → superflex, D/ST → DEF), IDP left out and said (as built, unverified live) | partial: schedule + each week's points from `mMatchupScore` (as built, unverified live) | partial: ESPN id → gsis → Sleeper (nflverse), else a unique name + position, else `espn:<id>` listed, unvalued (as built, unverified live) | partial: free agents = unrostered; waiver order / budget not read (as built, unverified live) | partial: adds, drops, trades from `mTransactions2` (as built, unverified live) | partial: D/ST as team defenses; picks / FAAB not read (as built, unverified live) | partial: the same feed, for matched players (as built, unverified live) |
| **Yahoo** (unverified) | "Connect with Yahoo" (OAuth 2.0, read-only `fspt-r`) → your leagues; or a link `football.fantasysports.yahoo.com/f1/12345` once connected; "coming soon" until the two secrets exist | partial: stat modifiers → our keys, the rest listed unpriced (as built, unverified live) | partial: `W/R/T` → FLEX, `Q/W/R/T` → superflex, IDP left out and said (as built, unverified live) | partial: scoreboard by week (as built, unverified live) | partial: Yahoo id → nflverse `yahoo_id` → Sleeper, else a unique name + position, else `yahoo:<id>` listed (as built, unverified live) — **no 2025 / 2026 rookie has a `yahoo_id` in nflverse** (the audit below) | partial: free agents from Yahoo's list; priority / FAAB not read (as built, unverified live) | partial: adds, drops, trades (as built, unverified live) | partial: DEF as team defenses; picks / FAAB not read (as built, unverified live) | partial: the same feed, for matched players (as built, unverified live) |

**The PO's calls (Wave I-K brief)** — they replace the II-5 verdicts below where they differ: (1) ESPN public leagues
read-only by id, labelled "unofficial"; private ESPN leagues through the user's own cookies **exist in the code and ship
off** (`LEAGUE_LAB_ESPN_PRIVATE=off`; Andrew flips it; the cookies live only in the user's sealed `ll_espn` cookie, never
on the server); (2) Yahoo through the official OAuth flow, the refresh token in the sealed `ll_yahoo` cookie, "coming
soon" until Andrew registers the app; (3) nothing is "supported" until verified live after the deploy.

**The id map** (IK-3's audit, `scripts/id_map_audit.py`, `league_lab_m1` 2026-09-26 snapshot): of the 286 QB–TE rostered
in the house leagues, `espn_id` 100%, `mfl_id` 100%, `yahoo_id` 65.7% — every 2025 and 2026 draft-class player lacks a
`yahoo_id` in nflverse's `ff_playerids` (and in Sleeper's directory). Details: `docs/ANY_LEAGUE.md` § "The id map".

**The duplicate-id rule (Wave I-L, IL-5)** — `player_ids.read`: an `mfl_id`, `espn_id` or `yahoo_id` that two players'
rows carry (two gsis ids, or a gsis id and none) maps to **nobody** — quarantined (`IdTable.mfl_dupes` /
`espn_dupes` / `yahoo_dupes`, `player_ids.duplicates()`), logged once per process with the ids; the same player on two
rows is not a duplicate (IK-2's `yahoo_id` rule, applied to all three, as `int_player_id_map` keeps an ambiguous
`sleeper_id` out of the map). On nflverse's table of 2026-10-02 (12,518 rows): **4 `espn_id` values** are on two
players (16094, 2516049, 2574010, 2582138 — all retired or free agents: Steven Miller / Marqueston Huff, Quinton Dunbar
/ Houston Bates, Aaron Ripkowski / Alonzo Harris, Kyle Carter / David Morgan), **0 `mfl_id`, 0 `yahoo_id`**. Before
the rule, ESPN's lookup gave the last row's gsis id.

## The matrix as researched (Wave I-I, II-5, 2026-10-04)

*(History: the research before Wave I-K built ESPN and Yahoo. The as-built table above is the current one.)*

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
the `unavailable` line instead (League's "Latest moves" on an MFL league said "Transactions: not available for MFL leagues
yet." until Wave I-L read MFL's transactions — it said "No completed moves yet this season" before that). Statuses: `yes` (read as the provider has it), `partial`
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

**What is read now (Wave I-L, IL-2, 2026-10-05)**: the league, rules, rosters, schedule, standings, weekly results, the
player list, the injury report, **the transactions export** (`TYPE=transactions&L=&W=<week>&TRANS_TYPE=*`, one call per
week, a past week cached a day, this week 10 minutes — `MFL.transactions`; `MFLLeagues.transactions` answers Sleeper's
`/transactions/<round>` shape: `FREE_AGENT` → `free_agent`, `WAIVER` / `BBID_WAIVER` → `waiver` with the bid in
`settings.waiver_bid`, `TRADE` → `trade` both ways with future picks `FP_<franchise>_<year>_<round>` in `draft_picks`;
IR, taxi, auction and pool rows move nobody between teams and are left out; MFL has no transaction id, so the id is
`mfl-<timestamp>-<franchise>-<hash of the row>`) and **the live scoring** (`TYPE=liveScoring&W=<week>`: each listed
player's points so far and `gameSecondsRemaining`; a player with 0 seconds left is in — his game is over —, a game in
progress keeps its full range in the week's odds, IH-3's rule; this week's matchups rows carry each franchise's score so
far as Sleeper's call does). The shapes are MFL's documented ones (the export's `api_info` page is robots-blocked from
here; ffscrapr's `mfl_transactions` reads them the same way): **the transactions were built on a synthetic fixture**
(`api/tests/fixtures/mfl/70587/transactions*.json`) — the PO checks `mfl:70587`'s League "Latest moves" against MFL's
own Transactions report after the deploy; the live scoring parse runs on MFL's own recording (`liveScoring_4`). Waivers:
the waiver type (`currentWaiverType`), the team's place in the waiver order (`waiverSortOrder`, a waiver-order league)
and its blind-bid balance (`bbidAvailableBalance`, a blind-bid league: MFL's documented field — **not in any fixture**:
21861's public export, a blind-bid league, carries none, and the line says so). MFL's export states no claim time.
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
