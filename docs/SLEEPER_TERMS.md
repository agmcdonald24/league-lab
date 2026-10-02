# Sleeper's API terms, and what League Lab spends (plan F3, 2026-10-02)

## The clause

Sleeper's API is read-only and needs no key. The terms Andrew quoted to the PO say, in substance:

* **free for non-commercial use**;
* **commercial use needs a licence from Sleeper** (Andrew has asked them);
* **stay under 1,000 calls a minute**, or the calling IP may be blocked.

(The exact wording is Andrew's quote from Sleeper's developer documentation and terms; paste it here verbatim
when it is to hand, with the date it was read and the URL.)

## What it means

**For the beta (now).** The beta is free, behind a password, and charges nobody: non-commercial use, inside the
free terms. Nothing in Wave F charges anyone or advertises a price. We do not use Sleeper's name or logo as a brand
("for Sleeper leagues" in marketing is a question for the licence, not assumed).

**For Wave G (accounts, payments).** Taking money for a product that reads Sleeper is commercial use: **no payment
switch goes live before Sleeper's licence is signed** (or the answer is "no", and then the same design reads ESPN /
Yahoo / MFL, which have their own terms: `docs/ANY_LEAGUE.md` § Risks). The licence may set its own call limit and
attribution rules; this page and `LEAGUE_LAB_SLEEPER_PER_MIN` change with it. Wave G also needs one shared cache and
one shared bucket when there is more than one API process (today each process holds its own: two processes could
spend 2 × 300 a minute — still under 1,000).

## What we spend (this API, plan F3)

One process, one client (`src/league_lab/sleeper_client.py`), a token bucket of **300 calls a minute** (under a
third of the limit; `LEAGUE_LAB_SLEEPER_PER_MIN`), burst = a minute's worth. When it is empty and nothing is cached
the API answers 503 `{"error": "busy, try again in a minute"}`; when something is cached (even expired) it answers
with that. A failed call to Sleeper also falls back to the last good answer.

| Call | Cached | When |
|---|---|---|
| `GET /v1/players/nfl` (~15 MB) | a day, in memory and on disk (`LEAGUE_LAB_CACHE_DIR`) | once a day per process, for every league |
| `GET /v1/league/<id>` | a day | first open of a league |
| `GET /v1/league/<id>/users` | a day | first open (team names) |
| `GET /v1/league/<id>/rosters` | 10 minutes | My Week, the player card, rest of season, the picker |
| `GET /v1/league/<id>/matchups/<week>` | 5 minutes | the week's opponent (My Week) |
| `GET /v1/user/<username>` | an hour | the league picker |
| `GET /v1/user/<id>/leagues/nfl/<season>` | an hour | the league picker |

**Per active league** (someone has it open):

* first open of My Week: **4 calls** (league, rosters, users, matchups) + the directory once a day for the process;
  the player card and rest of season of the same league then cost **0** (same caches);
* the league picker for a user with *n* leagues: **2 + 2n calls** the first time (5 leagues: 12), then 0 for an hour
  (user, leagues) / 10 minutes (rosters) / a day (users);
* kept open: rosters every 10 minutes + matchups every 5 minutes = **0.3 calls a minute**, + league and users once a
  day.

**Head-room**: 300 a minute ÷ 0.3 = **~1,000 leagues open at the same time** in one process before the bucket binds
(≈ 3,300 at Sleeper's full 1,000); first opens cost 4 each, so a Sunday-morning burst of 75 new leagues a minute fills
the minute's budget. The bucket and the stale-answer fallback make that a slower page, not a ban. Raising the roster
TTL to 15 minutes (the spike's) and matchups to 10 on weekdays would double the head-room; the numbers above are
what `TTL_S` sets today.

**Never from tests or the sandbox**: tests read fixtures (`LEAGUE_LAB_SLEEPER_FIXTURES`, set for every API test by
`api/tests/conftest.py`); the sandbox cannot reach Sleeper at all.
