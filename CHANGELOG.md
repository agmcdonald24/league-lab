# Changelog

Newest first. The Home page shows the top entry as "What's new".

## 2026-09-29 — Wave B (decision engine)

- Behind the pages, League Lab now works out the **best legal lineup** for every team in both leagues, every
  week: all slots solved together (FLEX and superflex included — a WR who beats your QB2 goes in the superflex),
  byes, Out / Doubtful, IR and taxi left out, Questionable flagged, players whose game has started kept where
  they are. A kicker or defense you just picked up still fills its slot, counted as 0 until Sleeper has scored him
  in your league, and never ahead of anyone with a value; an empty slot now means nobody on the roster can play
  there. Each starter gets a **margin** — how many points the lineup loses without him — so the closest call
  of the week is named. For weeks already played it also computes the best lineup you could have started; it
  matches Sleeper's own max points (weeks 1–2: all 22 teams, to the cent, except one where it is 1 point higher
  by leaving a −1 defense out). No page shows it yet: the start/sit, waiver and roster views are being rebuilt on it.
- **What the board said before kickoff is now kept.** From week 4 on, each week's projection v2 board (Rankings)
  is frozen when the week's first game kicks off: later refreshes no longer rewrite it, the page says "the board as
  published before the first kickoff (Thu …)", and the "How the model is doing this season" strip is scored on that
  frozen board. Weeks 1–3 were played before this existed, so their projections are labelled as **refit values**
  (from a later run of the same model), on the board and in the strip. Every page also warns when the injury report
  is stale ("Injury report last loaded Sat Sep 26, 7:02 AM ET; treat Questionable tags as stale.") — when it was
  loaded before the last final game's date or more than 48 hours before the next kickoff.
- Behind the scenes: the nightly data refresh can now run on GitHub's servers (about 7:40 a.m. Eastern) instead of
  Andrew's laptop, so a closed laptop no longer means yesterday's numbers. Same steps, same checks; the banner on every
  page still says when the data was last published.
- The "loaded" line under every page title now shows Eastern time with the label ("**nflverse** loaded Tue Sep 29,
  4:34 PM ET"), like the injury warning below it, and it means when that data arrived from the source: a nightly
  rebuild no longer makes week-old files look like they loaded this morning.
- The live board no longer jitters between refreshes with no news: two fits of the same data now give the same
  numbers (the training rows were read in an unordered scan, which moved the model's internal validation split;
  differences reached 1.5 points on a player).
- **Waiver Wire now answers "who should I claim, and who goes?"** Pick your team and the page opens with the claim
  that improves your lineup most, in one line: "Claim Michael Mayer (TE), drop Dylan Sampson: +1.1 this week at TE,
  +2.4 over the next 4 weeks", with the player he pushes out of your lineup and his projection (the same numbers as
  your lineup elsewhere, no second model). Every free agent is tried against every player you could drop, and your
  whole lineup is rebuilt each time — FLEX and superflex included, byes and the dropped player's own future starts
  counted over four weeks. Then the best **cover** for a coming bye, a **flyer** on someone with no games yet, or a
  plain "Nothing beats what you have". The full ranked list is one tap away; browsing every free agent moved under
  it. The "Adds worth a claim" position-by-position shortlist is gone.

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
- Waiver Wire opens with **Adds worth a claim** for your team: per position your league starts, up to three free
  agents who beat your weakest projected starter this week (projection v2, your league's scoring) or your best
  bench player's PPG, each saying so in words ("+0.3 over your TE1 this week (Proj 7.9 vs 7.6)") with floor and
  ceiling; otherwise "Nothing on the wire beats what you have at RB." The free-agent table now ranks by projection
  v2 for next week by default; every other ranking and filter is still there.
- Rankings (projection v2) has a new strip, **"How the model is doing this season"**: once a week is complete, the live
  board is scored like the backtest — per position, this season's rank correlation and floor–ceiling coverage next
  to the backtest's, with the number of weeks scored. After weeks 1–2 of 2026 RB is at or above its backtest in both
  leagues, WR and QB below (QB 0.43 vs 0.54 in League of Scrubs) — two weeks is a small sample.

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
