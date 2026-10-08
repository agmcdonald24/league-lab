# What's new

Written for the people in the league, newest first. Home shows the top entry. Every release adds one here
in plain words (docs/WORDS.md); CHANGELOG.md keeps the technical version.

## Oct 8 (afternoon) · nobody who cannot play is ranked, and one trade verdict

- **We ranked a player on injured reserve, and that was wrong.** De'Von Achane is out for the season and was our
  21st running back this week. The rankings read one injury source and his player card another. Now every list, the
  start question and both trade calculators use the same check: a player on injured reserve, suspended or ruled out
  gets no projection and no trade value, and is listed under "Not playing" with the reason and where it came from.
  About 80 players were affected.
- **The trade calculator gives one answer.** A review showed us a trade where the headline, the dial and the
  week-by-week table disagreed. Every part now reads the same comparison: an empty starting spot is filled from the
  waiver wire, for both teams. What happens if you leave the spot empty is shown separately and labelled.
- **Each screen says what has been checked.** One line under rankings and trade answers: the model version, when the
  data was published, which weeks it covers and how that kind of projection did on 2021–2025. Where we have not
  graded something, it says "not graded".
- **Quarterbacks beyond next week are still our weak spot.** Over five seasons, following our pick over a
  quarterback's own scoring record would not have scored more. For running backs, receivers and tight ends it
  would have.
- **No verdict when a team's starter is unclear.** The trade calculator gives the numbers and holds the
  recommendation. When we set a starter by hand, the verdict is marked "a lean".
- **Safer releases.** Every release now runs 798 checks of lineup and trade decisions, and the site checks its own
  rankings and a known trade after each nightly refresh.

## Oct 8 · the right starters, a better quarterback list, bye-week players back, and what we cut

- **Bye-week players were missing from every rest-of-season list.** This is the first bye week, and Patrick
  Mahomes, Travis Kelce, Kenneth Walker and every other Chief and Panther had no rest-of-season number, so the
  trade calculator had no value for them. Fixed, for every bye week to come.
- **Seattle's quarterback is Sam Darnold.** Our data source still lists Drew Lock, so we set Darnold by hand, and
  the Rankings row says so. We tested four ways to pick starters automatically from depth charts and injury
  reports; none was accurate enough to trust, so for now we check the disagreements ourselves every week.
- **Rest-of-season quarterbacks, second round.** For weeks beyond the next one, a quarterback's projection now
  leans partly on what he has actually done this season and last. Tested on five past seasons: closer in all five.
  It is better, not solved: the remaining error is mostly not knowing who will still be starting weeks from now.
- **Kickers and defenses have no rest-of-season ranking any more.** We graded ours for the first time: beyond next
  week their order was no better than chance. This week's kicker and defense rankings stay.
- **Every list is now checked every night** against what players have actually scored, so we find the odd ones
  before you do. Rest-of-season screens also say plainly how far off those projections have been.

## Oct 7 (evening) · rest-of-season quarterbacks, fixed

- **A reader caught us, and he was right.** Our rest-of-season quarterback list had Kyler Murray and Malik Willis
  ahead of Josh Allen. For weeks that have no betting line yet, the model was treating every team as average, so a
  quarterback's later weeks had little to do with this week's. That list also sets quarterback values in the trade
  calculator. This week's projections were not affected.
- **What changed.** Later weeks now use each team's own scoring level this season and this week's starter. We tested
  it on five past seasons, projecting two to eight weeks ahead: closer to what happened in all five. Allen is back in
  the top three.
- **What is still true.** A quarterback projection more than a week out misses by about 7.6 points per game, against
  6.4 for next week, and the order is less sure than at the other positions. We now check that every night.

## Oct 7 · rankings for everyone, "Who should I start?", the player card, and more honest grades

- **Rankings for everyone.** Every player ranked for this week or the rest of the season in your scoring, in tiers.
  Pick two to four and see who to start, with how sure that is ("Lean Olave: he outscores Nacua in 57 of 100 such
  weeks — close; either is fine.").
- **The player card.** Every player's page leads with a card: his picture on his team's colour, this week's
  projection and its range, his value in your scoring, ratings that say where he ranks this season among players at
  his position (0–99, from his own numbers, not a projection), and charts of his points against the projection made
  before each game and of his role by week. Defenses have a card now too.
- **We said quarterbacks were our weak spot. That was not a fair comparison.** The home page set this season's first
  weeks against a newer model's past results. Against the same model's own past, the gap is too small to call on
  this few weeks, and the home page now says so. We did find one real improvement (a quarterback's passing
  touchdowns now lean on his team's expected points) and it is in this week's numbers.
- **Starter unclear.** When a team's listed quarterback did not play its last game and another one did, both show
  **Starter unclear** on Rankings and get no start / sit call. This week: Chicago, Seattle and Washington. Seattle
  is the clearest case: the listing says Drew Lock and Sam Darnold has been playing, so Lock's projection is likely
  too high and Darnold's too low. We tested two rules to correct it and neither was accurate enough to ship, so for
  now the label says what we do not know.
- **Trends, graded.** Players scoring below what their work usually earns did score more the next week, and their
  projections already expected it. So the gap is what happened, not a reason to buy or sell on its own; Trends and
  Trades say that now, and Trades' lists are named for what they are ("Scoring below his work", "Scoring above his
  work"). A role change (more targets, carries or snaps over two games) holds about half of its move, and the
  projection already counts most of it.
- **Small things.** A shared link to a player shows his card; when a league's site is slow to answer, the app says
  "busy" and tries again instead of showing an empty lineup; a MyFantasyLeague league's League screen opens a
  little faster again.

## Oct 6 (evening) · share your league, see who moved, write on the blog, and an honest grade

- **Share your league.** League has a **Share** button: your league-mates open the link and see the power rankings
  and the rest of the season without setting anything up, then pick their team. (Sleeper and MyFantasyLeague
  leagues.) From next week the rankings show who moved up or down and how each team's playoff odds changed, and
  Sleeper leagues get **title odds**.
- **We graded the cornerback matchup, and it did not hold up.** Over 2,190 receiver-games in 2025 and this season,
  receivers facing a "shutdown" corner finished about as close to their projection as everyone else, and so did
  receivers facing an easy one. So the matchup read is now the defense alone; the corner is still shown, for
  context, with that grade beside it. The DFS "Worth a look" list is off for the same reason: its picks did no
  better than chance. We keep the record every week now and will say so if that changes.
- **The blog has an editor.** Posts can be written on the site (on a phone too), with a live preview, a button that
  links a player's name to his card, tables of players, pictures, drafts that save themselves and three drafts
  started from the week's numbers.
- **Small things.** My Week tells two players with one last name apart ("P. Washington"); the matchup board shows
  the games still to play first; Stats has a **Role change** group (target, carry and snap share in a player's last
  two games against his games before them); DFS shows wind, rain and cold for outdoor games; a MyFantasyLeague
  league's League screen opens in about 3 seconds, not 12.

## Oct 6 (afternoon) · a home page and a blog, trades and values without a league, matchups for everyone, power rankings

- **A home page.** isuckatfantasy.io now opens on this week's top projections, the matchups to target, how our
  projections have actually done (the bad numbers too), and the tools — before it asks you for anything.
- **A blog.** Analysis lives at isuckatfantasy.io/blog; a link to a post shows a proper preview when you share it.
- **Browse in your scoring.** Pick PPR, Half PPR, Standard, ESPN's or Yahoo's default, add superflex, TE premium,
  6-point passing touchdowns and your league's size. Every player gets a **value**, and the **trade calculator works
  without a league**: add players to each side and it says who gets more, by how much, and whether the gap is bigger
  than the uncertainty.
- **Matchups for everyone.** Players · Matchups lists every receiver this week, player by player: the defense he
  faces, the cornerback likely across from him and how sure we are, with a search. Tight ends, running backs and
  quarterbacks too. With your league open, switch between **My players** and **Everyone**.
- **DFS with no upload to start.** The DFS tab opens on this week's projections in DraftKings or FanDuel scoring with
  what the projection does *not* hold beside each player — the cornerback matchup, a rising or falling role, the
  betting total — and a short **Worth a look** list. Lineups can now **stack** a quarterback with his receivers.
  Salaries still come from the site's own file; when a week's file is published here, nobody has to upload it.
- **My Week speaks plainly.** "Change needed" is now **Roster alert**, "What changed" is the **News feed**, and an
  empty lineup spot says what to do: "Your quarterback spot is open: Mahomes and Young are on a bye. Add a
  quarterback before Sunday 1:00 PM ET," with a link to the waiver wire. The Team screen no longer goes blank when
  two spots are open (that was a bug this morning), and no screen can hang on its loading blocks any more.
- **League: power rankings and the rest of the season.** Every team ranked by what its best lineup should score per
  week from here, and the season played out up to 10,000 times: projected record, playoff odds, top seed. Context,
  not a promise — the screen says what it assumes.
- **Finding your leagues.** On a computer your leagues now appear right beside the box you typed your username in.

## Oct 6 · no password, the full stat tables, accounts with a passkey, DFS

- **No password any more, and no league needed to look around.** Open isuckatfantasy.io and tap **Browse the lab**:
  every player's stats, trends, matchups and projections in PPR, Half PPR or Standard scoring. Open your league (as
  before) when you want your lineup, waivers and trades.
- **Stats: the full table.** Players · Stats has two views now: **Key stats** and **Full table** — every number we
  have for the position, grouped (Receiving, Air yards, Red zone, Efficiency, Next Gen Stats, …). Sort any column, tap
  a group to hide it, show every player, download the table as a CSV. Fifty new numbers: EPA per target and per
  carry, success rate, first downs, WOPR, deep targets, points over expected, drops, broken tackles, yards after
  contact, pressure rate and more. They fill in with the next nightly update; a dash always says why.
- **An account, if you want one: a passkey, no password and no email.** "Create an account with a passkey" uses your
  phone's or computer's own lock (Face ID, a fingerprint or its PIN) and keeps your leagues, your team in each and your
  saved views on any device. It appears after the next nightly update. Lose every device and the account is gone:
  add a second passkey.
- **DFS (new tab).** This week's projections in DraftKings or FanDuel scoring; add the contest's salary file (the
  site's own "Export to CSV") to see points per $1,000, who is **undervalued** against that slate's salaries and why,
  and lineups you can download for the site's upload. The file stays in your browser. Estimates, not promises: the
  model's record is on About.

## Oct 5 (evening) · a player's role, Next Gen Stats, MyFantasyLeague moves and live scores, a watchlist

- **Yahoo leagues are "coming soon" again.** Yahoo has to switch on our access to fantasy data and has not yet, so
  connecting worked and then no league opened (it said your connection had expired, or that the league was private:
  neither was true). The Connect button is off until Yahoo opens it; nothing is wrong with your league or your Yahoo
  account.
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
  balance when MFL shares it. Checked against MFL's own list on two leagues: a move made during the week's games
  now shows right away (MFL files it under the following week, so the weekend's adds were missing until Tuesday).
- **Waivers shows "Recently added in this league"** on every platform: who every team added this week and last.
- **Receivers on a new team**: a receiver's first games with a new team used to be projected about a point per game too
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
