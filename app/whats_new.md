# What's new

Written for the people in the league, newest first. Home shows the top entry. Every release adds one here
in plain words (docs/WORDS.md); CHANGELOG.md keeps the technical version.

## Oct 5 (evening) · a player's role, Next Gen Stats, MyFantasyLeague moves and live scores, a watchlist

- **A player's card has a "Role" block**: his last two games against the games before them (targets, carries, snap
  share, red-zone touches — a change is named only when it is bigger than his usual week-to-week swing; otherwise
  "steady" or "too early to say" with the counts), whether his points run ahead of or behind his share of the work
  (said as a fact, never "due for regression"), and what he did in the games a teammate missed, when there are at
  least two.
- **Next Gen Stats on Players → Stats**: time to throw and completion % over expected for quarterbacks, rushing yards
  over expected per carry for running backs, separation and yards after catch over expected for receivers and tight
  ends — weighted by the plays they are measured on; a dash under NGS's own minimums, never a zero. They arrive with
  the next nightly update.
- **MyFantasyLeague leagues** now show the league's latest moves and every team's score so far during a game window;
  the week's odds narrow as MFL's games finish; the waiver line names your place in the waiver order or your blind-bid
  balance when MFL shares it. New, built from MFL's documentation — say so if a move looks wrong.
- **Waivers shows "Recently added in this league"** on every platform: who every team added this week and last.
- **Receivers on a new team**: a receiver's first games with a new team used to be projected about a point a game too
  high; until his third game the line is scaled down by the same share for everyone (0.79 this season). Graded on
  five past seasons it missed by 0.18 points per game less on those games.
- **The week's odds are graded**: from this week on, every past week's win probability and ranges are scored against
  what happened; the grade is on the Record page as the weeks come in.
- **A watchlist, when you are signed in**: ☆ Watch on any player's card; `/watchlist` shows his status, this week's
  projection and who has him, on any device.
- **Faster and lighter**: the first trade search on a league you open on demand answers in about a third of the time;
  the server carries a quarter of the player directory it used to.

## Oct 5 (afternoon) · ESPN and Yahoo leagues, and an account that remembers your leagues

- **ESPN leagues** open by league id or link — public leagues only, read-only, through the same unofficial path every
  ESPN tool uses, so it says "unofficial" and "new: not verified on a live league yet" until we have checked one.
- **Yahoo leagues** through Yahoo's own sign-in ("Connect with Yahoo", read-only). The button says "coming soon" until
  the app is registered with Yahoo.
- **Sign in to save your leagues** (⋯ → Sign in): an emailed link, no password; your leagues, teams and saved views
  come back on any device. Off until the mail service is switched on; nobody has to sign in to use the app.
- The server uses a third less memory after Sunday's restart, and tells us how much it holds.

## Oct 5 · The numbers agree with the words, trades you could actually propose, one player card everywhere

- **Team's "Strength by slot" is one comparison**: the player you start at each slot (RB1 and RB2, each FLEX apart)
  against what every other team starts there, in the same projected points — the old card compared your points with
  everyone's *margins*, which is why a 14.8 could sit beside "best 7.3". Group totals and usable depth under it.
- **Replacements are legal lineups**: "Tuten moves from FLEX to RB2; Wilson fills the open FLEX" — locks respected,
  full names when two players share one.
- **Trades says "No compelling trade found" when that is the truth.** A trade is proposed only when it is legal, beats
  both teams' best waiver move, and is an offer the other manager might consider (a kicker for a starter is not). Each
  card: what you give and get, the drops, both lineups' effect, why they might consider it, why they might refuse.
- **Tap any player name, anywhere, and his card opens beside the screen** (a full sheet on a phone) with Overview,
  Usage, Game log and News; the screen under it keeps your search, filters and scroll. Back closes it.
- **Players → Stats**: presets for WR/TE, RB and QB, season or last 3 / 5 games, totals or per game, pick your
  columns, save a view, compare 2–4. A dash with the reason where a number is not available — never a 0.
- **Season has three views**: My roster outlook (your players; what the lineup loses without each), Potential upgrades
  (before acquisition cost; free agents lead to a claim, rostered players to the calculator), Rest-of-season projections.
- **News says what it changes**: what changed, why it matters here, whether the recommendation changed, whether the
  projection already includes it, and the next step. The home's clocks are separate: data built, injuries checked, news.
- **One setup flow**: pick your platform, paste a Sleeper username or league link (or an MFL league), pick your team.
  Plain errors ("That Sleeper username does not exist"). What each platform gives is listed; nothing is substituted.
- Rates say "per game", "per target", "per attempt" everywhere; every number names its denominator in the help.
- isuckatfantasy now counts screen views with Google Analytics (league ids and roster numbers only — never names);
  About says so.

## Oct 4 (afternoon) · Your calls, your odds, and rookies priced honestly

- **Your calls this season** on the Team page: week by week, what you started, what our lineup would have scored, the
  best possible, and how the close calls landed. The About page's record links there.
- **Your odds this week** under the opponent line on My Week ("You're a slight favorite this week: 64%, 120 to 104
  expected") and for every matchup on the League screen. It describes; it never picks for you.
- **Rookies and other newcomers** are projected from where they were drafted until the games say otherwise, instead
  of from a model that had never seen them. Every screen shows the same number.
- Clearer messages when the app cannot reach the server; a kicker claim in your dad's league drops the kicker it
  replaces.

## Oct 4 · The record grades our calls, and a few things said plainly

- **Our lineups, graded.** About's record now keeps the lineup the app would have started each week (frozen before the
  week's first game) and grades it against what you actually started and the best lineup in hindsight. The first
  numbers come from rebuilt weeks and are not flattering — About says so in plain words; the real record starts in
  week 5.
- **No more "0.00" for a player we have no number for.** A dash and "no projection" instead, and the lineup total
  says when it counts a starter at 0.
- **Waivers says when claims run** ("Claims run Wednesday 3:00 AM ET") and MFL leagues see when their rosters were
  last read.
- **What changed now cites its sources**: an injury-report move names the report and its time; a hand-checked brief
  shows there too.
- **Team QB / team kicker have a season value** in trades, measured against the best free unit; the trade finder's
  "left out" rule now looks at season value above replacement, not raw totals.
- **From week 5 the bonuses are priced at their odds** in every league with one; About's record says which weeks were
  priced which way.

## Oct 4 · A new name and address: isuckatfantasy.io

- The app is now called **isuckatfantasy** and lives at **isuckatfantasy.io** — same app, same numbers, new name on
  the sign-in screen, the home-screen icon and the top bar. The old address keeps working. If you added it to your
  home screen, remove it and add it again from the new address to pick up the new icon; you sign in once more there.
- A player's news line can now lead with a hand-checked brief (its source named, a link, and whether the news is
  official, reported, corroborated or disputed) when one exists; ESPN's headlines fill the rest, the one about him
  first.

## Oct 4 · Better reasons: the drop, the alternative, the matchup

- A waiver claim now says what the drop costs and why that player — the player he replaces goes first, and a bench
  player who is worth more than anyone on the waiver wire is no longer a free drop ("Drop McPherson: Carlson
  replaces him at K"). When no claim is worth a roster spot, it says so. Stashes are a watchlist until a scenario
  is worth the drop.

- Trades are ranked against your best waiver move over the same weeks: "+14.6 over weeks 4–7: 1.8 more than your
  best waiver move". A trade that a free claim beats says so and drops down the list. The value words are kept
  apart — projected points, starter points, backup coverage, season value above replacement — and both sides' weeks
  are shown.

- A matchup rank comes with what changed: when a defense's starting corners are out, the card says the historical
  rank is less representative this week, names the replacements, and says that the forecast does not carry it. A
  coin flip is never settled by a rank like that.

- My Week keeps close calls in view: "Tuten or Williams at FLEX: a coin flip, 0.3 points apart — no clear upgrade"
  instead of "nothing to change", plus "What changed" since the morning build. League Lab now counts screen views
  (which screen, which league and team, when — nothing about you; About says so).

## Oct 3 · What to do this week, in three lines or fewer

- My Week now opens with the actions that matter — at most three, the most urgent first: a change your submitted
  lineup needs, a close call with an injury in it, or the waiver claim that raises this week's starters. Each one
  says who, why, whether it is already in your lineup, and the kickoff it has to beat; "Why? The numbers behind
  it" holds the detail. When there is nothing to do it says so. A green button opens your league's app to make the
  change — League Lab never changes your lineup or claims for you.

- Trades are explained the way you would tell a friend: who starts, who sits, what you give up on the bench, what
  the other team gets, over which weeks — and whether standing pat or a waiver claim does the same job. The dial is
  now "Effect on their starters": what their lineup gains or loses, not a guess at their answer. Waiver cards lead
  with this week's gain; the four-week total comes second and says "in total".

- Plainer names everywhere: "Projected points this week", "Typical range (the middle 50% of outcomes)", "Low-end /
  high-end outcome", "Share of team passes thrown to him", "Backup coverage", "Team QB / Team kicker". The setup
  screen puts your team first and folds the scoring detail behind one line.

## Oct 3 · News on the card, and team QB / team K everywhere

- Every player's card and the slide-up panel now carry a **News** line: his latest headline from ESPN's feed
  (most are RotoWire's blurbs), how long ago, and a link out. Nothing else is stored — the headline refreshes
  every hour, every 15 minutes on game days.

- Leagues with a team quarterback or team kicker spot (MyFantasyLeague) see them on Season (rest of season per
  team, priced from each week's starter), on Team, and in a week where you play two opponents the League screen
  shows both games.

## Oct 3 · Your league's scoring, read back to you — and checked

- Pick a league and the card now tells you what League Lab read: your lineup in your league's own words ("TMQB · 2
  RB · 3 WR/TE · TMPK · DEF") and your scoring in one line ("TDs by distance 6 / 9 / 12 · 1 pt per 10 rushing /
  receiving yards · +10 at 100 rushing · INT −3 · FG by distance 3 / 5 / 10 / 15"), plus what the projections
  cannot price yet. Under it, **the scoring check**: for the last played week, we count every rostered player your
  league's way and compare with the points your league actually gave him — "we match your league's points for 155
  of 156 players within 1 point", and the misses named with the rule behind them. In League of Scrubs and the
  dynasty it is 100%.

- MyFantasyLeague leagues with their own kind of scoring and lineup now work: touchdowns paid by distance, "1 point
  per 10 yards", bonuses at any threshold, field goals by distance, team quarterback and team kicker spots, combined
  spots like WR/TE, and weeks where you play two opponents. A team QB or team K is a player here, priced from that
  team's starter.

## Oct 2 · Rest of season, and our record

- A new page, **Our record**, keeps score on us: every week we save Sleeper's own projections before kickoff,
  count them your league's way, and after the games check whose numbers were closer and who called the
  start/sit decisions right. It starts the first week the numbers are saved; nothing is filled in after the fact.

- Every player now has a **rest of season** number: his projection added up over every week left in your league,
  up to your final (week 16 in League of Scrubs, week 17 in the dynasty), with his bye counted as a week off, the
  playoff weeks on their own, and where he ranks at his position in your league, rostered or free agent. It is
  one line on his page, a list under the weekly board on Rankings, and next to every trade you try on Trade
  Finder ("you give 232 points, you get 120"). Only this week knows the betting lines yet, so the later weeks lean
  on his role and the schedule.

## Oct 1 · Projections that know who is playing, and ranges you can use

- The projections now know who starts at quarterback and whether a player's top teammate is out: a backup
  quarterback who starts is projected like a starter (and one who sits, like a backup), and a receiver or back
  whose team's top target is out this week gets the bigger share he is likely to see. Every card leads with
  "most weeks" (the middle half of his outcomes) instead of a 20-point spread, and a start/sit call now says how
  often one player outscores the other ("A beats B 58% of the time"). In your leagues this starts with week 5's
  projections (week 4's were already locked when it shipped).

## Sep 30 · Built for your phone, plainer words, kickers and defenses

- Matchups answers "who is my receiver up against?": the cornerback most likely across from him (from where his
  targets go, so a good guess, not a promise), where that corner ranks among the league's starters (shutdown, solid
  or target) and how your receiver did against him before. It also puts two of your players side by side on your
  closest lineup call, and shows defense vs position as a color chart with your opponents at the top.
- Open League Lab on your phone: every table shows at most five columns (a **Phone** setting next to Essentials
  and Everything), every page starts with its answer, and the big tables sit one tap below. League Intel is
  gone: its charts (schedule luck, points left on the bench, each week's scoring rank, every team) now open the
  League page. Tap a player's name almost anywhere to open his page.
- Kickers and defenses have real projections now, from what their team is expected to score, how often it
  kicks, the offense or defense they face, and the kicker's own range. Your lineup and the waiver list use them
  (a kicker or defense you just picked up is no longer counted as 0), and free-agent defenses show up on
  Waiver Wire.
- Every "How to read this" box now tells you what to do with the page, in a few short lines.
- **Worth a look** on this page: your schedule luck, the points you leave on your bench, the best bargain on
  your roster and which of your players is most often his quarterback's first look, each one tap from the page
  that explains it.
- Rankings answers "is this a model you trained?" Yes: League Lab's own model, trained on ten seasons of NFL
  games. Its "The model" section says what it learned from, how it was graded and what it can't know (late
  injury news, weather, a blowout).
- It also shows what the model leans on, in points: how much a player has been on the field over his last 3
  games matters most for QBs and WRs, his share of the carries for RBs and of the targets for TEs. The old
  "price line 0.017" table described a small side model, not the projection, and is gone.
- **Trade Finder can try a trade for you.** It opens on the team where one trade helps both lineups most, and your
  best buy-low at each position. Tick players both ways and see both lineups this week and over four weeks, who
  starts and who sits, who has to be cut, where both teams would rank, and what the players are worth on the market
  (projected points for the rest of the season above the best free agent at their position), with a one-line
  verdict like "Helps your lineup +5.4 this week, them +6.8; about even by season value: helps both lineups". Copy the link to share the trade.
- **Role alerts**: Trends now opens with the players whose role changed this week, and why (last October it would
  have said "Filling in: Rico Dowdle, snap share 36% → 67%, Chuba Hubbard out injured"). A player's own page says it too, with a what-if for
  his points if the new role holds, and Waiver Wire lists **upside stashes**: free agents whose role is growing
  before their points do. Receivers and Kickers now say why each number matters, with an example.

## Sep 30 · Your week, answered

- Home opens on your week: your best lineup and the two or three closest calls, like "RB2: start Kenny Gainwell
  over Emanuel Wilson, 0.45 apart, a coin flip", with each player's opponent.
- Tap any player's name for his own page: how much he is used, this week's projection with a bad and a good
  week, whether he is available, and where he fits in his team's lineup.
- Waiver Wire says who to claim and who to drop, and how many points it adds this week and over the next four.
- Team Hub, Trade Finder and League Intel use your real best lineup, FLEX and superflex included. "Acquired" is
  right for dynasty rosters now (a 2023 trade shows as a trade).
- Each week's projections are locked when its first game kicks off, so "how is the model doing" grades what
  you actually saw.
- The numbers refresh every morning around 7:40 a.m. Eastern, laptop or no laptop.

## Sep 27 · Your league's scoring everywhere

- Every league page counts points your league's way. Josh Allen showed 38.2 per game on the dynasty's Team Hub;
  it says 49.6 now, exactly what Sleeper says.
- The NFL-wide pages (Players, Trends, Receivers, defense vs position) use one scale for everyone and say so.
- Rankings shows how the projections are doing this season next to how they did in past seasons.

## Sep 26 · Better projections

- Rankings has a new projection. It predicts the stat line (targets, catches, yards, touchdowns) and turns it
  into points your league's way, with a bad-week and a good-week number for each player.
- The old formula stays as a check, and past seasons show which one did better at each position.

## Sep 26 · Two leagues

- League of Scrubs and Forever Unclean Dynasty in one app: pick one in the menu. A link you send opens on the
  same league and team.
- Yardage bonuses and long-touchdown bonuses are scored like Sleeper scores them.

## Sep 26 · First shared version

- Online for the league, with a feedback button and a switch for how many columns tables show.
- Rankings, Trends (who is getting more work), and the receiver pages: who the quarterback looks to first,
  and how often a receiver is on the field when his quarterback drops back.
