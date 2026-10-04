# ESPN's public feeds: what we read, what we show, what we keep (Wave I-D, N1, 2026-10-03)

League Lab reads two of ESPN's public JSON feeds, read-only, with no key, no login and no account:

| Feed | Since | Code | What for |
|---|---|---|---|
| `https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries` | Wave I-0 (I0-A) | `src/league_lab/injury_feed.py` | who can play, minutes after a team's ruling (`docs/ANY_LEAGUE.md` § Availability) |
| `https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players?playerId=<espn_id>&limit=5` | Wave I-D (N1) | `src/league_lab/news_feed.py`, `api/league_lab_api/news.py` | the news line on the player card |

## What the feeds are

**Unofficial and undocumented.** ESPN publishes no developer documentation, no terms and no rate for
`site.api.espn.com`. These are the JSON answers ESPN's own pages and apps read (the player news feed is what ESPN's
fantasy player card shows). They can change shape, move or stop without notice; both clients treat any failure as "no
answer" and the product carries on without them (no line, the nightly's injuries).

**What the answer says about use: nothing.** The news answer is `{timestamp, resultsOffset, status, resultsLimit,
resultsCount, feed: [...]}`; it carries no terms, licence, attribution or rate field, and its only cache header is
`cache-control: max-age=1` (read through the browser pane 2026-10-03). ESPN's site-wide Terms of Use (the Disney terms
linked from espn.com's footer) were **not** read from this sandbox (espn.com is not reachable through the pane's
allowed hosts). Before anything is charged for, read them and record the clause here, as `docs/SLEEPER_TERMS.md` does
for Sleeper.

**Whose words.** Most player news items are RotoWire's (`type: "Rotowire"`: RotoWire writes the blurb, ESPN publishes
it); the rest are ESPN's own stories that name the player (`Story`, `HeadlineNews`, `Media`).

## The news feed, as found (2026-10-03, through the browser pane)

`GET https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players?playerId=4262921&limit=5` → 200, newest first:

```jsonc
{ "timestamp": "2026-10-03T18:47:20Z", "status": "success", "resultsOffset": 0, "resultsLimit": 5, "resultsCount": 5,
  "feed": [
    { "id": 64044628, "type": "Rotowire", "playerId": 4262921,
      "headline": "Jefferson (ankle) has been already been ruled out for Sunday's game against the Dolphins, but …",
      "description": "(the same sentence)", "story": "(RotoWire's analysis, ~300–700 characters)",
      "published": "2026-10-03T13:33:00Z", "lastModified": "2026-10-03T13:33:00Z",
      "links": { "mobile": { "href": "http://m.espn.go.com/wireless/story?storyId=64044628" }, "api": { "self": {} } } },
    { "id": 50077553, "type": "Story", "byline": "Michael F. Florio",
      "headline": "Fantasy football Week 4 inactives: Daniels, DeVonta to sit; McConkey questionable",
      "description": "…", "story": "(the whole article, ~10–35 KB of HTML)", "images": [ … ], "video": [ … ],
      "published": "2026-10-03T00:59:53Z",
      "links": { "web": { "href": "https://www.espn.com/fantasy/football/story/_/page/FFSundayInactives-50077553/…" }, … } } ] }
```

* An unknown id answers 200 with `feed: []`; no `playerId` answers 500. Without `limit` the feed goes back years (a
  retired player still has items); `days=` is accepted too.
* RotoWire items have no `links.web`: only an old `http://m.espn.go.com/wireless/story?storyId=` link (not checked:
  not an allowed host). We link those to the player's ESPN page instead (`https://www.espn.com/nfl/player/_/id/<id>`,
  the page that lists them; its address was not opened from here either).
* Size: about 1 KB per RotoWire item, 17–60 KB per ESPN story (its body and video); `limit=5` answers 5–50 KB.
* Tried and not used: `site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/<id>/news` and the same on
  `site.api.espn.com` (404); `site.api.espn.com/apis/site/v2/sports/football/nfl/news?athletes=<id>` (200, but the
  filter is ignored: league-wide news); `…/site/v2/sports/football/nfl/athletes/<id>/news` (200, always empty);
  `site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/<id>/overview` (has `news` and the latest
  `rotowire` item, but 241 KB a call, mostly video).

Fixtures: `api/tests/fixtures/espn/news_4262921.json` (Justin Jefferson, 5 items, the newest that morning) and
`news_3045147.json` (James Conner, nothing since 2026-08-30) — ESPN's answers with `story`, `images`, `video`,
`categories` and author details emptied (we never keep them, so the repository does not either).

## What we show

One line on the player card, page and research pane, under the availability lines:
**News** · 2 h ago · *Jefferson (ankle) has been ruled out for Sunday's game versus the Dolphins.* · RotoWire via ESPN ›

* the newest headline only (a long RotoWire blurb is cut at a word to 110 characters, the whole headline in the
  link's label), how old it is, **the source named** ("RotoWire via ESPN" or "ESPN"), and a link out to ESPN's page
  (a new tab). The API sends at most 3 items (`news: [{headline, date, source, url}]`), newest first, none older than
  14 days; nothing older than 14 days = no line.
* Never shown: the description, the story or blurb body, images, video, authors.

## What we keep

* **Nothing in the database, nothing in the nightly, nothing in git** beyond the trimmed test fixtures.
* A per-athlete cache file `LEAGUE_LAB_CACHE_DIR/espn_news/<espn_id>.json` with only `{headline, date, source, url}`
  per item, `fetched_at` and the answer's `timestamp`: read again after an hour, 15 minutes on a game day. A failed
  read serves the last copy (still subject to the 14-day rule), or no line. The body is dropped before the cache.
* **Since Wave I-G (IG-2, 2026-10-04): the event store.** The hosted database keeps a row per item a screen *showed*
  (`events.events`, `docs/HOSTING.md` § "Events") with the same four fields — headline, date, source, link — plus the
  player's id; never the description, body, images or authors. And a row per injury-report status move read from the
  injuries feed (the status, the body part, the entry's date, the player's ESPN page). The decision-quality review
  asks for it (a recommendation cites the event behind it). Kept until a retention is decided. **Switch**:
  `LEAGUE_LAB_EVENTS_ESPN_NEWS=off` keeps ESPN's news items out of the store (status moves and PlayerWire's briefs
  stay); `LEAGUE_LAB_EVENTS=off` stores nothing. The first bullet ("nothing in the database") holds for the nightly
  and git only. Read ESPN's terms before anything is charged for, as above — keeping headlines is part of that check.

## How much we call

* **On demand only**: one athlete when a card is opened (`/api/player/{gsis}`); never in bulk — Trends', Waivers' and
  every other screen's rows do not call it (`api/tests/test_n1.py::test_rows_never_fetch_news`).
* Then at most once an hour per athlete (15 minutes on a game day) per process.
* A token bucket of **60 calls a minute** per process (`LEAGUE_LAB_ESPN_NEWS_PER_MIN`); an empty bucket serves the
  last copy or no line. The injuries feed keeps its own bucket (2 a minute, `LEAGUE_LAB_ESPN_PER_MIN`): one process asks
  `site.api.espn.com` at most 62 times a minute, in practice a few an hour per open card.
* Every call carries `User-Agent: league-lab/api (beta; player news line, one athlete per card opened)`, a 3-second
  timeout (a slow ESPN delays the card by at most that, once an hour per athlete).

## Switches

* `LEAGUE_LAB_NEWS=off` turns the line off (the card answers `news: []`, no call). **Default: on** — the PO and Andrew
  decide whether it ships on; flipping it is the env on Render.
* In fixture mode (`LEAGUE_LAB_SLEEPER_FIXTURES`) it is off unless `LEAGUE_LAB_ESPN_FIXTURES` is set (then it reads
  `<dir>/news_<espn_id>.json` and measures age from the answer's own `timestamp`); no test and no sandbox run calls ESPN.
* `/api/status` → `news`: `{enabled, mode, calls, failures, stale_served, athletes_cached, per_minute, last_error}`.

## Disney's terms, read (Wave I-I, II-5, 2026-10-04)

The Terms of Use above were read through WebFetch at <https://disneytermsofuse.com/english/>. Three clauses bear on
the two feeds and on any ESPN league adapter: you may not "access, monitor, copy or extract the Disney Products using a
robot, spider, script, or other automated means"; not "use the Disney Products for any commercial or business-related
use or build a business utilizing the Disney Products"; and "you will not share your account or account information
with others". So the news line and the injury overlay are outside those terms as written (free beta or not), and a
paid product needs ESPN's written permission or another source. The decision is the PO's and Andrew's; the switches
above (`LEAGUE_LAB_NEWS`, `LEAGUE_LAB_AVAILABILITY`) turn both off. ESPN leagues: `docs/PROVIDERS.md` § ESPN.

