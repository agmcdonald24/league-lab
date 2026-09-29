# Changelog

Newest first. The Home page shows the top entry as "What's new".

## 2026-09-27 — Your league's scoring on every league page

- Team Hub, Waiver Wire, the Matchups start/sit board, Trade Finder, League Intel and the League page's draft review
  now price every player in **the league you picked**: PPG, PPG over the last 3 and 5 games, xPPG and PPG − xPPG,
  positional strength, roster-value and keeper ranks, draft season points. Until now a second league saw those in
  League of Scrubs scoring — Josh Allen showed 38.2 PPG on the Forever Unclean Dynasty Team Hub; it is 49.6 there
  now, exactly his Sleeper points per game. Nothing changes for League of Scrubs.
- The NFL research pages — Players, Trends, Receivers and defense vs position (with the Opp rank columns built from
  it) — keep one scale for everyone, League of Scrubs scoring, and each now says so. The sidebar notice is down to
  that one line.
- Home's "highest projections" panel is labelled for what it is: the baseline formula in League of Scrubs scoring.
  Projection v2 in your league's scoring is on the Rankings page.
- The sidebar says what kind of league you picked in one line under the league name, on every page
  ("12-team superflex dynasty · full PPR · 6-pt pass TD · yardage bonuses"); the key-by-key scoring differences
  moved into a collapsed "Scoring differences vs the reference league" section, one click away.

## 2026-09-26 — Projection v2

- Rankings now default to **Projection v2**: a projected stat line (targets, receptions, yards, TDs, carries,
  attempts, INTs) per player-week from a gradient-boosted model, priced in **your league's** scoring, with a
  **floor (P10) and ceiling (P90)** calibrated so about 80% of outcomes land inside. The baseline formula stays
  as the check; the backtest section scores both on seasons the model never saw, per league.
- Fixes from the first two-league walkthrough: League and Kickers pages pick the season within the selected
  league; League Intel history is per league; blank cells are blank (not "None"); no kicker options in a league
  without a kicker slot; superflex counts as a second QB starter; dynasty leagues get "roster value" instead of
  "keeper facts"; dates render as dates; Rankings only offers played weeks and the next one.

## 2026-09-26 — Second league

- Several Sleeper leagues at once: `LEAGUE_LAB_SLEEPER_LEAGUE_ID=<id>,<id>`; the first is the
  *reference* league whose scoring prices NFL-wide pages. `?league=<id>` opens the app on a league;
  the sidebar lists where a league's scoring differs from the reference.
- Scoring keys a league might use that were unmapped are now recomputed: yardage-game bonuses
  (`bonus_rec_yd_100` …, exclusive buckets), 40+/50+ yard touchdowns (from play-by-play) and
  distance-bucketed missed field goals. Expected points leave bonuses out on purpose.
- Sleeper's "no previous league" marker (`"0"`) no longer produces a failed partition.
- The league and team you pick now carry across pages (Streamlit drops the URL's `?league=&team=`
  when you switch pages; the choice is remembered for the browser session, and a shared link still
  wins when it carries one).
- A league without kicker slots no longer breaks Trade Finder and League Intel; a table missing
  during a hosted refresh shows a notice instead of a traceback; the Rankings guard no longer
  demands a mart the page does not read.

## 2026-09-26 — Share-ready beta

- Hosted publishing: `make sync-hosted` pushes the marts (never raw data) to a hosted Postgres in one
  atomic transaction; the app reads Streamlit secrets; optional beta password; feedback link.
- Sidebar **Table detail** toggle: *Essentials* hides denominators, noise statistics and fine-grained
  counts on every table; *Everything* shows every column.
- Home is a landing page: your week at a glance, what's new, data sources and licences.
- Rankings (page 4): a transparent weekly projection per position with form / usage / matchup / Vegas /
  home terms and a backtest scoreboard (2023–2025 out of sample).
- Play-by-play layer: first-read target share, routes proxy (TPRR / YPRR), context splits by half,
  score state, down & distance and QB on the play; true dropbacks; red-zone shares.
- Trends (page 3): which usage metrics moved over the last three games beyond a player's own noise;
  momentum; defenses getting softer or stiffer.
