# Words — how League Lab talks on its pages

The reader is a league-mate who plays fantasy football on Sleeper and has never heard of dbt, Spearman or
a quantile. Every string a page shows follows this file: the "How to read this" boxes, cards, captions,
column tooltips (`help=` in `app/lib/table.py`), Home's "What's new" (`app/whats_new.md`) and the model
explainer on Rankings. Docs for developers (`METRICS.md`, `STATUS.md`) keep the technical words.

## The rules

1. **Say what to do first.** A "How to read this" box is three to five bullets that answer "what do I do
   with this?": start him, claim him, sell him, check the news. Definitions come second.
2. **Short sentences, no hedging.** One idea per sentence. No "leverage", "robust", "signal" when "sign"
   will do. Colons and full stops over dashes.
3. **One gloss per technical number**, in brackets, the first time it appears on a page:
   "floor–ceiling (the range 8 weeks in 10 land in)".
4. **Never on a page**: model or table names (`v2`, `mart_…`, `gsis_id`, `P10`, `quantile`, `z-score`,
   `permutation`, `residual`, `as-of`, `walk-forward`, `denominator`, `proxy`). The one exception: Rankings'
   "The model" section names *Spearman* once, with its gloss, because the grade tables are headed with it.
5. **Numbers keep their units**: "+2.1 points this week", "0.45 apart", "43% of the time".
6. **Name the league's scoring** when a number depends on it ("in League of Scrubs scoring"); say "one scale
   for every league" for the NFL-wide pages, not "reference scoring".
7. **Unknown is not zero**, in words too: "no projection yet", "not charted before 2022", never a silent 0.

## Term → the words we use

| Term (code, docs) | On a page |
|---|---|
| projection v2, `proj_points` | the projection; "League Lab's own model" when contrasting with the old one |
| baseline (OLS formula) | the old formula |
| P10 / floor | floor: a bad week for him (1 week in 10 lands below it) |
| P90 / ceiling | ceiling: a good week for him (1 week in 10 lands above it) |
| P10–P90 interval, 80% interval | between floor and ceiling (8 weeks in 10 land there) |
| P50 | the middle outcome |
| P25–P75, 50% range (D6) | most weeks: "most weeks 9–16" (half his weeks land there: a quarter below, a quarter above); leads on a card and on the Rankings board, the floor–ceiling behind it |
| P(A outscores B), win probability (D6) | "Tucker outscores Monangai 54% of the time": whole percent, never 0 or 100 |
| 50–55% / 55–65% / 65%+ (D6) | a coin flip / a lean / clear (the card's headline word; the margin's words only when there is no percentage: a kicker, a defense) |
| same-game correlation (D6) | "teammates and players facing each other are not independent (a shootout lifts both)" |
| interval width | the gap between floor and ceiling; "Range" |
| coverage_80 | how often the real score landed between floor and ceiling (the aim is 8 in 10) |
| Spearman, rank correlation | the order score: how well the projected order matched the real one (1 = perfect, 0 = random) |
| top-N hit rate | how many of the week's real top 12 / top 24 it had in its top group |
| MAE | the average miss, in points |
| backtest, walk-forward, held-out season | graded on past seasons it never saw (trained on the past, graded on seasons it never saw) |
| kickoff board, frozen board (B5) | the projections as they stood at the week's first kickoff, locked since |
| refit values | a re-run of the same model (for weeks played before boards were locked) |
| drift | how the model is doing this season |
| gradient-boosted regressor | a gradient-boosted model: a few hundred small decision trees, each fixing the mistakes of the ones before it |
| component model | one small model per stat (targets, catches, yards, touchdowns …) |
| priced line, scoring map | the stat line counted your league's way |
| permutation importance | points of error added when the model can't use that number (we scramble it between players) |
| feature | input; "what the model looks at" |
| `targets_pg_l3` and the other inputs | `projections.FEATURE_LABELS` ("Targets per game, last 3 games") |
| xPPG, expected points | expected points per game: what his targets and carries are usually worth |
| PPG − xPPG | **below / above expectation** (IA-1; was "due" / "running hot"): "Getting the targets of a 10.5-point player, scoring 3.6" — then one cause the numbers support or none: "no touchdowns on 4 red-zone targets", "4 touchdown passes in 2 games", "his quarterback changed", "his share of the targets fell from 25% to 12%" |
| target share, carry share | his share of his team's targets / carries |
| snap % | share of plays he is on the field |
| first-read share | how often he is the quarterback's first look |
| route participation, routes proxy | how often he is on the field when the quarterback drops back (an estimate) |
| TPRR / YPRR | targets / yards per route |
| aDOT, air yards | how far downfield his targets travel |
| implied team total | the points Vegas expects his team to score |
| opp rank | the matchup rank: 1 = the defense that gives up the most to his position (the matchup you want); on the Matchups screen (IB-3) the tough rank instead, 1 = the toughest |
| opp rank in a sentence (IA-1) | "the Colts, who give up the 2nd-most points to running backs" (rank ≤ 10) / "the 7th-fewest" (rank ≥ 23); the middle is not worth a sentence |
| a decision card's reason (IA-1, `cards.reason_line`) | one sentence under the call: the strongest reason for the starter and the strongest against the other player ("Hampton's share of the carries rose from 57% to 72% last game; Croskey-Merritt's share of the carries fell from 50% to 38% last game"); under 55% (or under 1 point apart without a percentage): "Too close to call: the projection says A by 0.5, the ranges say either. Go with B on the matchup: …" (injury first, then matchup, role, betting line); last names, whole names when two share one |
| implied total in a sentence (IA-1) | "Vegas expects Willis's Dolphins to score only 16" (≤ 18) / "… to score 27" (≥ 26) |
| z / Strength, "beyond noise" | how unusual the change is for him (1 = worth a look, 2 = clear); bigger than his usual week-to-week swing |
| momentum | his role trend |
| lineup value (B1) | the projected points of your best lineup |
| margin (B1) | how much your lineup loses without him; "apart" on a card |
| weakest slot | your closest call |
| bench value / depth | what your bench alone could put out |
| lineup gain, fit (B2, B3) | what the move adds to your lineup, in points |
| all-play | your record if you had played every team every week |
| luck_wins | wins above (+) or below (−) what your points deserve |
| reference league / reference scoring | League of Scrubs scoring; "one scale for every league" on NFL-wide pages |
| partition (Data Status) | the pieces a source comes in, usually one per season |
| role alert (R-10), `direction` up / down | a bigger / smaller role; "Role alerts this week" |
| `kind` absence_beneficiary / depth_move / new_team / role_up / role_down | Filling in (or Taking over the work) / New starter · Lost his starting job / Bigger (smaller) role on his new team / Bigger role / Smaller role |
| `cause_text`, trigger | "Why: …" — a teammate out injured or back, benched, a depth-chart move, traded; "the coaches changed his role" when there is none |
| `games_held`, confidence | "one game so far" / "two games so far" / "three games: this is his role now"; column "Held" |
| expiry | "It ends when X returns" / "Check again after week N: by then his projection has caught up if it holds" |
| larger-role scenario (R-12), `presentation = 'what if'` | "What if the new role holds: 11.3 in week 4 (projection 7.1, +4.2)"; never a chance |
| scenario backtest hit rate | "tested on 2023–2025: after 285 alerts like this the next three games landed nearer it than the projection 46% of the time" |
| upside stash (`ops.waiver_upside`) | Upside stash: his role is growing before his points do |
| rest of season, ROS (E2), `ros_points` | rest of season: "Rest of season: 232 points over 13 games"; "through this league's final" when the window matters; "ROS rank" only as a column header |
| `ros_p10`–`ros_p90` (E2, weeks taken as independent) | likely: "(likely 190–273)"; the gloss "where 8 seasons in 10 would land if every week were its own roll of the dice; a role change or an injury moves the weeks together, so the real range is wider" |
| `ros_rank_pos` (E2) | "WR4 in this league" (every player at the position, rostered or free agent); "not ranked (on injured reserve)" |
| `weeks_with_lines` (E2) | "Only week 4 has betting lines yet: the later weeks lean on his usage and the schedule" |
| stat-line pieces × scoring (IA-3) | "Why this number": "8.9 targets → 5.5 catches → 96 yards → 0.48 TDs → 15.4 points a game × 12 games = 185", then one line a piece ("5.5 catches × 0.5 = +2.7", "8.9 targets (no points on their own)"); what a per-unit price cannot show is its own line: "yardage bonuses (a big game pays extra in this league)" or "the small pieces and rounding" |
| market line, `market_points` (IA-3) | "Sleeper has him at 16.2." (this week, this league's scoring); under 70% / over 140% of it: "We're well under (over) the market: our number follows his recent usage. Treat it with care."; none: "Sleeper's number for this week is not in yet." |
| `piece_columns` (IA-3) | per game, projected: Att · Pass yd · Pass TD · INT (QB); Car · Rush yd · Tgt · Rec · Rec yd · TD (RB); Tgt · Rec · Rec yd · TD (WR / TE) |
| the rankings' honesty line (IA-3, `about.RANKINGS_HOWTO`) | "How to read the rankings": from his work, not his name; superflex / 6-point passing TDs put quarterbacks on top by design; Sleeper's number is there to compare |
| matchup tone (IB-3) | **Favorable / Neutral / Difficult**: the word in the state color, ▲ / ▼ beside it; "No read" when no ranked corner is named |
| tough rank (IB-3) | one direction on the Matchups screen: "#1 = the toughest for the offense" ("#3 toughest vs RB", small and grey under the tone) |
| cornerback certainty (IB-3, `call_strength`) | **likely** (his targets lean 15+ points to one side) · **unclear** (either outside corner) · **no call**; beside the tone, never a "shutdown" badge: "the 17th-hardest of 74 starting corners to throw on" |
| value to my lineup (IB-3, `lineup_points`) | "Value to my lineup": what he adds to your best lineup over the weeks left; one of yours = what you lose without him; "Your QB2 only plays in week 7: 16 points over your next-best there", "Your backup QB never starts for you behind Mahomes: he adds nothing to your lineup (insurance only)", "Free agent: would start for you in 12 of 13 weeks left, +20 points to your lineup" |
| card status (IB-3, IB-0's `status`) | **Change needed** (the call is not in your Sleeper lineup) · **Already set** · **Close call** (a coin flip); the strength word: Clear · Lean · Coin flip |
| yardstick (Receivers, U-17) | what the season's top-12 at the position (the 12 with the most points a game) average |
| combined slot `WR+TE1` (IC-2, `cards.slot_label`) | "WR/TE 1" (the league's own slot, its parts joined by a slash; "RB/WR/TE 2") |
| team unit `TMQB` / `TMPK` (IC-2) | "team QB" / "team K" in the slot column; the player is "Kansas City Chiefs QB" / "… K" (his team's quarterbacks / kicker as one player, MyFantasyLeague's) |
| no eligible slot (IC-2, `lineup.no_slot_reason`) | **No slot** in the list, "No slot for a K in this league" as the reason — never "Can't play" (kept for injury, bye, IR, a locked bench player) |
| asset key (IE-0, the calculator's `give` / `get`) | never on a page; a key the analysis cannot use reads "Can't analyse **Houston Texans QB** (you get): on Big Mac Attack's roster, not Madeyes Revenge's." with "Take out of the trade" |
| a waiver reason in a later week (IE-0, `_bye_reason`) | only the candidate's own: "Fills your empty DEF in week 7, when Jacksonville Jaguars is on a bye" (a defense) · "Starts at WR/TE 3 in week 7, when McConkey is on a bye" (a starter he can stand in for) · else "Would not start for you this week; helps in week 7." |
| the platform in a sentence (IE-0) | the league's own: "on the bench in MFL", "starting in his MFL lineup"; Sleeper's number (the market line) only on a Sleeper league |
| points per game on an on-demand card (IE-0) | one statement with its source: "Points per game: 10.5 over 2 games, reconstructed in this league's MFL scoring from his stat lines" (the chart's number) |
| no NFL team (IE-0, `TeamBadge`) | no chip; never "FA" / "Free agent" for a missing team ("Free agent" is a player nobody in the league has) |

## The dictionary (Wave I-E, the casual-user review)

The outside review of 2026-10-03 (`docs/reviews/2026-10-03-mfl-70587-usability-review.md` § "use a consistent metric
dictionary") walked the app as a manager who knows football and does not enjoy analytics. These words win over the
older rows above wherever a term appears — pages, cards, the research pane, Season, the Finder, the calculator, the
help texts. The meaning column is what the words must keep true. Other developers append rows; nobody renames one
without changing every page that shows it.

| Old wording or display | The words we use | Short form (tiles, tight rows) | Meaning that must stay true |
|---|---|---|---|
| Proj / projected | **Projected points this week** | Projected this week | A forecast in the selected league's scoring, not a guarantee. One decimal by default. |
| You +9.5, weeks 4–7 | **About 10 extra starter points total over weeks 4–7** | +9.5 over weeks 4–7 in total | The sum of the change in the best legal starting lineup each week. Not 9.5 per week, not the incoming players' points. |
| Fit | **Improvement to your starting lineup** (weeks 4–7, best lineup each week) | Lineup improvement | Name the weeks, and whether the baseline is the best lineup (it is, everywhere today) or the submitted one. |
| Expected / work worth / xPPG | **Points suggested by his past opportunities** | From past opportunities | Looking back: what his targets and carries were worth. Not the upcoming-week forecast; said beside the chart. |
| Market (our projection-derived score) | **Projected value above available replacements** | Value above replacement | From our projections, not observed trade prices; respects the league's eligible replacement slots. Sleeper's own number stays "Sleeper's projection". |
| Most weeks | **Typical range** (the middle 50% of outcomes) | Typical range | The middle 50% of modeled outcomes; "most" overstated it. |
| Floor / ceiling | **Low-end / high-end outcome** | Low-end / high-end | Modeled percentiles (1 week in 10 below / above), not the minimum or maximum possible score. |
| Target share | **Share of team passes thrown to him** | Share of team passes | 20% = about one in five team targets in the games shown; keep the period. |
| Depth | **Backup coverage** (for <position>) | Backup coverage | Say which position the backup protects; a bench-only lineup sum is not an insurance value. |
| TMQB / TMPK / WR+TE2 | **Team QB / Team kicker / Receiver or tight end** | team QB / team K / WR/TE 2 | The league's roster rules, the same names on every page. |
| Interest (the trade dial) | **Effect on their starters** (IE-1: "Makes their lineup weaker" · "About even" · "Improves their lineup" · "Improves it a lot") | Effect on their starters | Their lineup's projected gain over the window, never an acceptance probability. |
| Above / below expectation | "{n} above / below what his opportunities suggest" | above / below his opportunities | The observed gap and its evidence; never "due" or "cool off". |
| Why? (the trade's arithmetic) | **How we calculated this** | How we calculated this | Under it: the scoring pieces ("0.42 rushing TDs × 6.98715"), the value above replacements, rest of season, ranks, roster size. |

**A trade, in words** (IE-2, `decisions.trade_story`): the package and any cut → one sentence on the effect ("Your
starting lineup: about 3.4 more points this week, about 10 more in total over weeks 4–7.") → who starts and who sits
by name ("Rice starts at WR/TE; McConkey to the bench.") — a starter who only moves from WR/TE 2 to WR/TE 3 is not a
change → the backup coverage it takes ("you lose Tuten, a backup RB") → the other side in the same words → standing
pat and the best free agent for the same need. "About N" is a whole number in a total, one decimal for this week.

**Freshness**: "Updated 2:51 PM ET" (the exact time on hover / tap); feed names only in the data details; the MFL
roster's freshness its own line.

| My Week's actions (IE-1, `myweek.build_actions`) | at most three, the most urgent first: **Change needed** ("Start Wilson at FLEX (or Croskey-Merritt: a coin flip) in place of Jefferson.") · **Close call** ("Keep Addison and Nabers ahead of McConkey for now.") · **Waiver claim** ("Claim Dalton Schultz: about 3 more starter points this week."); one sentence naming the players, then the reason and what could change it ("Check his status again before kickoff."); the numbers behind "Why? The numbers behind it" |
| set line (IE-1) | "Your lineup is set — nothing to change." (a complete answer) / "The rest of your lineup is set — nothing to change." — never three reassurance cards |
| submitted or not (IE-1) | "Already in your MFL lineup — nothing to change." / "Not in your Sleeper lineup yet: make the change in Sleeper." (the league's own app named); "Nothing is claimed from here: put the claim in on MFL." |
| nothing is submitted from here (IE-1) | "League Lab never changes your lineup or claims; it tells you what to do in your league's app." beside **Open MFL to edit your lineup ↗** / **Open Sleeper to edit your lineup ↗** |
| lock time (IE-1, `myweek.lock_words`) | "before Sun 1:00 PM ET": the first kickoff among the players an action swaps |
| waiver card, this week first (IE-1, `decisions.claim_lead`) | "Falcons defense instead of Jaguars: about 1 more starter point this week" (the big number: this week's, labelled "this week"); then "+12.8 over weeks 4–7 in total" (a total over the weeks, never per week); "Instead of Devaughn Vele:" on a claim for the same spot; "Each claim is weighed on its own …: two claims do not add up beyond your 1 open roster spot" |
| the trade dial (IE-1; was "Their interest" / No deal · Maybe · Likely · Hard to say no) | **Effect on their starters**: Makes their lineup weaker · About even · Improves their lineup · Improves it a lot; "It starts at their WR/TE over Robinson." (the need); no 0–100 number, never "interest" or "hard to say no" |
| the cheaper package (IE-1) | "Same gain for you without RJ Harvey." on the lead; "Adding RJ Harvey does not change your gain; it costs you RB depth (RJ Harvey: 97 season points)." on the bigger package |
| matchup evidence (IF-3, `research.matchup_evidence`) | two sentences: "Carolina gives up the 12th-fewest points to receivers (weeks 1–2, 2 games, League of Scrubs scoring, not adjusted for the offenses it faced), but with different corners: Jackson and Horn are on injured reserve (ESPN, Sep 30); Evans, Lee and Smith-Wade are expected to start (…)." / "The historical rank is less representative this week (both starting corners changed), so treat it cautiously: it does not settle a close call. Who plays corner is contextual only; not in the forecast."; the badge **Corners changed**; "The rank stands: the same corners." when they did not; "unranked (insufficient snaps)" for a corner without enough coverage snaps; never "the matchup favors" a side from a rank earned by other corners |
| forecast treatment (IF-3) | "contextual only; not in the forecast" — the projection counts the points a defense has allowed and the betting lines, not who plays for it; never "the model knows" |

| a trade against the alternatives (IF-2, `decisions.trade_vs_alternative`) | "+14.6 over weeks 4–7: 1.8 more than your best waiver move (the Atlanta Falcons defense claim gives +12.8 over weeks 4–7 for an open spot)." · "+7.9 over weeks 4–7; the Atlanta Falcons defense claim gives +12.8 over weeks 4–7 for an open spot: the trade does not beat it on starter points." + a reason only from the numbers ("It gives more this week: +1.7 against the claim's +1.2." / "It brings in more season value above replacement: 121 for 61 — the season beyond these weeks.") · "The trade also takes the open roster spot the claim would use." · the card's mark: **Below your best waiver move.** |
| the Finder's order (IF-2) | "Ranked by gain beyond your best waiver move over weeks 4–7 (Atlanta Falcons defense, +12.8); trades that do not beat it come last." — the first card is the headline |
| the week strip (IF-2) | "Starter points, week by week": Week 4 · 5 · 6 · 7, a row for you and one for them, signed ("+5.1 −0.5 +5.3 +4.6") |
| the value concepts (IF-2, `trades.VALUE_CONCEPTS`) | **Projected points** (one player, one week) · **Starter points** (what enters the best legal lineup over the weeks) · **Backup coverage** (the bench's best lineup) · **Season value above replacement** (the dictionary's "projected value above available replacements", rest of season: the fairness test — "Season value above replacement: you give 14, you get 7 (about even). You give 2 players for 1: 1 roster spot freed." — IG-1: the team QB is counted; a player with none is named: "Not counted (no season projection): Josh Jacobs.") · **Rest-of-season projected points** ("…, all positions added up — not a fairness test"): never added together; never "you give 493 rest-of-season points for 134" as a verdict |

## Decision quality (Wave I-F, IF-4: the fourth review § Priority 4 and its table)

The review of 2026-10-03 late evening (`docs/reviews/2026-10-03-decision-quality-review.md`): a correct optimizer output
does not remove the uncertainty, and every label must say what it compares. These rows win over the older ones above.

| Where | The words we use | Never |
|---|---|---|
| a close call the submitted lineup already follows (`myweek.build_actions` → `review`) | **No clear upgrade**: "Tuten or Williams at FLEX: a coin flip, 0.3 points apart; your lineup has Williams — no clear upgrade." + Compare ›; with IF-3's `matchup_uncertain`: "…; your lineup has Williams; the matchup rank does not settle it — no clear upgrade." ("our lineup has" when the submitted lineup is unknown) | "nothing to change" beside a close call |
| the set line (IF-4) | "No clear upgrade elsewhere." (close calls are shown above it) · "The rest of your lineup is set." (an action is shown, no close call) · "Your lineup is set — nothing to change." (no action, no close call: a complete answer) | |
| What changed (My Week) | the overlay's move ("Justin Jefferson is out (ankle) — Michael Wilson starts at FLEX2 · Injury report (ESPN) · 2 h ago") then the week's news from the last 24 hours ("Justin Jefferson: <RotoWire's headline> · RotoWire via ESPN ↗ · 5 h ago"), at most five; none: "Nothing has changed since the morning build." | a feed name without a time |
| the news line (card, pane) | the item about him first (RotoWire's blurb, or a headline that names him); an article-level headline is labelled **League news** | a league story as "News" about him |
| the matchup rank, anywhere (`cards.rank_words`, `lib/words.ts rankWords`) | "2nd-fewest WR points allowed" (31 of 32) · "5th-most RB points allowed" (5) · "the most / the fewest …" | a bare "#31", or a "#" whose direction changes by screen |
| a starter's margin (My Week's lineup) | "4.63 over Lloyd" (the bench player who would come in: `cards.alternative`) · "no eligible reserve" (the slot would be empty: the number is his whole projection, not a gap) | "Margin" with no comparator |
| the bench expander | the bench and who can't play only | the starters again |
| Compare's bold | the better number where it bears on the call: projected points, the low-end / high-end outcome, points a game, the rest of the season; the usage rows only between two players of the same position ("bold: the better number in points (usage is not compared across positions)") | more carries for an RB bolded against a WR |
| Compare's sections | "This season (2 games)" — the sample size once; the "Last 3 games" section dropped when it is the same games | the same numbers twice |
| the range, everywhere (Compare, About, Waivers, the console's cards) | **Typical range** (the middle 50% of outcomes) · **Low-end / high-end outcome** | "most weeks", "floor", "ceiling" on a page |
| the role line (card, pane) | before his fourth game "Role: **not enough games to say** — 2 games so far; a change is called against his own earlier games, from his fourth game."; after it "Role: **role steady over N games** — …" | "no role change detected" beside "not enough games" |
| a metric tile with no value | its definition (first-read share: his first-read targets ÷ his team's charted dropbacks with a first read; red-zone share: his share of his team's red-zone targets / carries) + "Not available for this player: no charted plays for him yet (unknown, not zero)." | a greyed tile with no words |
| below / above expectation (Trends, the game log) | "1.2 below what his opportunities suggest: an observed gap, not a forecast"; Trends' help: "a buy needs a price, which this screen does not have" | "expect him to pick up / cool off", "buy him while he is cheap" |
| the drawer (research pane) | the projection and its range, where he stands, the news, his role, his usage, his lineup line; behind expanders: "Week by week and season numbers", "Schedule" (week · opponent · projected), "Game by game this season" | the whole player page |
| freshness (My Week's footer) | "Updated 7 d ago ›" → "Last data load Sat, Sep 26, 5:26 PM ET." and the feed names | the feed list as the first line |
| how a week was priced (M4, Wave I-G; About's record, the console's Record page; `scoring.record_pricing_sentence`) | "Weeks 1–4 were priced flat; from week 5 the bonuses are priced at their odds." — **priced flat**: a bonus counts only when the projected line reaches it; **at their odds**: the bonus × its chance of happening; nothing at all for a league without a bonus | "expected value", "EV", "the flag" on a page |

## Unknown is not zero, team units, the Finder's rule (Wave I-G, IG-1)

| Where | The words we use | Never |
|---|---|---|
| a player with no projection row (My Week's lineup and bench, Team, the trade lineups, a Waivers drop; the console) | a dash **—** titled "No projection for him this week: unknown, not 0" and the words **no projection** under his name (the console: a blank and the flag "no projection") | "0.00" (the solver counts him 0; the screen never says it) |
| the lineup total with a starter who has none (My Week, `unvalued_words`) | "1 starter has no projection and counts as 0 in this total." | a total with no word about it |
| a team unit's season value (MFL's team QB / team kicker) | **Season value above replacement**, against the best **free unit of the same kind** — "Houston Texans QB: 355 season points; the best free team QB, Arizona Cardinals QB, 378: 0 above" | a player as a team unit's replacement; "Not counted" for a unit that has a projection |
| the Finder's "left out" (`sanity.words`) | "We do not suggest a trade that gives away much more season value above replacement than it brings back (over a quarter of what you give, and not about even), or one that only works because our number for a player you give is far under Sleeper's. A player with no season projection is not judged." · a row: "you give 20 season value above replacement for 3: 17 more, over 25% of what you give" | "rest-of-season points" as the reason (a volume gap: all positions added up) |

## Adding to it

A new metric or page adds its row here in the same change as its `help=` text. A release adds one entry to
`app/whats_new.md` (three to six bullets, newest on top) next to its `CHANGELOG.md` entry.
