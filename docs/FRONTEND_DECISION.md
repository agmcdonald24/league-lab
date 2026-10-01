# Front end: stay on Streamlit, or move to a phone-first web app? (plan D7, 2026-10-01)

**Recommendation: port page by page.** Start with My Week and the player card (built in this spike and ready to
put next to the Streamlit app), then Waiver Wire, Team Hub and Matchups: the pages you open on your phone every
week. Keep the research pages (Rankings, League, Trends, Receivers, Players, Kickers, Data Status) on Streamlit
until one of them has a reason to move. Move Trade Finder last. The rule for each move is at the end.

## What was built

* **A read-only API** (`api/`): the same tables on Neon, the same read-only login, the same beta password. It does
  not recalculate anything: it runs the Streamlit app's own code for My Week (`app/lib/cards.py`), so the cards say
  the same words with the same numbers, and a wording change there shows up in both. The player card's sentences
  live inside the Streamlit page, so they were copied. A test draws the real Streamlit page and checks every number
  and sentence against the API, for both leagues and ten players. All 39 API tests pass.
* **A web app** (`web/`): My Week and the player card, 36 KB in total. You can add it to your home screen, it
  follows your phone's light or dark mode, and your phone remembers your league and team.
* **One service**: the API also serves the app. One deploy, one address.

## Side by side

Same database, same machine, Chromium. Phone = iPhone size (390 × 844), desktop = 1300 × 900. Medians: 5 page loads,
10 taps of each kind. Streamlit was measured through a compressing proxy (the way a host serves it). Without
compression, `streamlit run` sends 5.5 MB.

| | Phone · web | Phone · Streamlit | Desktop · web | Desktop · Streamlit |
|---|---|---|---|---|
| The cards on screen, first visit | **0.37 s** | 1.9 s | **0.31 s** | 1.9 s |
| The cards on screen, next visit | **0.10 s** | 2.1 s | **0.11 s** | 1.8 s |
| Downloaded on the first visit | **36 KB** | 1,929 KB (5,528 uncompressed) | **36 KB** | 1,929 KB |
| Tap a name → his card | **0.15 s** | 1.8 s, in a new tab | **0.13 s** | 2.0 s, in a new tab |
| Back to My Week | **0.07 s** | 0.9 s (menu → Home) | **0.06 s** | 0.9 s |
| Switch team | **0.03 s** (0.2 s the first time) | 1.1 s | **0.03 s** (0.8 s) | 1.0 s |
| Cards fully on the first screen | **3 of 3** (first at 253 px) | **0 of 3** (first starts at 819 px) | 3 of 3 | 1 of 3 |
| On a slow phone network: first visit / tap a name | **0.54 s / 0.27 s** | 5.4 s / 2.3 s | | |

The sandbox was busy (other work ran on its 2 cores the whole time), so every number is slower than it will be on
a real host, for both apps. The gap is the point: about 10 times faster per tap, 50 times less to download. A
hosted app also waits on the network to Neon, which adds the same delay to both.

**What the numbers do not show:**

* **Names open a new tab in Streamlit.** A new tab is a new session: your team pick and table setting start over.
  With the beta password on, **every name you tap asks for the password again** (checked). From the home screen, a
  new tab leaves the app for Safari. In the web app a name stays in the same tab: one tap, and Back returns to the
  same spot. On the emulated phone, Streamlit's names took two taps with one test tool and one tap with the other.
  Your phone settles it.
* **Back in Streamlit is unreliable.** One move between pages adds three Back steps. The browser's Back returned to My
  Week 0 times in 10 on the phone and 3 in 10 on the desktop.
* **Releases.** Streamlit Community Cloud only restarts when `app/requirements.txt` changes, or the pages break until
  someone reboots. The web app has no such step: a push redeploys it.

## What we would lose

* **The table detail switch** (Phone / Essentials / Everything) and the column catalogue behind it (names, help text,
  formats). Each ported table needs its columns chosen; the catalogue can be shared through the API.
* **The quick page check.** Streamlit's built-in test runs every page in seconds with no browser. The web app needs
  browser tests (35 s for both pages at both sizes) plus the API tests.
* **One language per page.** A page becomes Python for the numbers plus TypeScript for the screen: roughly 1.5 to 2
  times the code.
* **Free, zero-effort hosting.** Community Cloud is free. The new service is free if a one-minute wake-up after 15 idle
  minutes is acceptable; otherwise it costs about $3 to $7 a month (below).
* **Ready-made pieces**: sortable tables with search and download, and Plotly charts. The web app needs its own table
  and a chart library.

## Cost to port each page

| Page | What it is | Cost | Why |
|---|---|---|---|
| Home (My Week) | cards, lineup | **done** | the rest of Home (Worth a look, page guide, what's new) is a few lines each |
| Player | five sections | **done** | its sentences should move from the page file into `app/lib` so both apps share them |
| Waiver Wire | cards + free-agent table | small | reads stored answers (`ops.waiver_moves`), one chart |
| Team Hub | cards + roster table | small–medium | stored answers; seven tables and a chart in expanders |
| Data Status | tables | small | six queries, no charts |
| Players | a query and a table | small | filters and a season table |
| Kickers | tables + 2 charts | small–medium | the first page that needs the chart library |
| Matchups | cards + board + comparison + cornerbacks + chart | medium | the cards are already done; nine controls, two charts |
| Trends | filters, tables, 2 charts | medium | |
| Receivers | filters, comparison, 3 charts | medium | |
| League | 7 charts + standings, scores, trades, draft | medium–large | the most charts on one page |
| Rankings | filters, board, how-good-is-the-model tables, 9 charts | large | the most text and charts |
| Trade Finder | partner cards + "try a trade" | large | the simulator runs the lineup solver (scipy) when you tick players, so it needs an API call that runs the solver, and the solver's code and libraries in the API |

## Hosting

| Option | Monthly | Notes |
|---|---|---|
| Render, free | $0 | 512 MB; sleeps after 15 minutes without visitors; about one minute to wake |
| Render, Starter | $7 | always on; deploys from GitHub on every push; the simplest setup |
| Fly.io | about $3 | a small machine always on (no free allowance; card required) |
| Railway, Hobby | $5 | includes $5 of usage |
| Google Cloud Run | $0 at our traffic | 2 million requests a month free; wakes in a few seconds |

The service uses about 125 MB of memory. Neon does not change: the same tables, the same read-only login. The
nightly does not change: it publishes the tables, and the API only reads them. Streamlit stays where it is during
a page-by-page port, so the extra cost is the new service alone. My pick: Render Starter ($7) for a season (simplest),
or Cloud Run ($0) if a few seconds' wake-up is fine.

## The rule for a page-by-page port

1. The page's numbers and sentences live in `app/lib` (a function with no Streamlit in it). The Streamlit page
   draws them, and the API serves them. If they live inside the page file today, they move first.
2. **The Streamlit page stays until the new page matches it on the headless check's numbers**: the API's comparison
   test draws the Streamlit page for both leagues, and every number and sentence must match.
3. The new page passes the browser checks at 390 and 1300 px: nothing scrolls sideways, the answer is on the first
   screen, a name opens on one tap in the same tab, and Back works.
4. Then the Streamlit page links to the new one, or is removed. One page per release.

## How to try it

The product owner deploys the branch (`api/README.md` → Render, Dockerfile `api/Dockerfile`, two settings: the
read-only database address and the beta password). Open the address on your phone, then Share → **Add to Home
Screen**. Open My Week in both apps, tap a few names, and come back. Then pick: stay, or port page by page.
