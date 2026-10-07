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
| decision record, `ops.lineup_record` (V-1, Wave I-G) | **our lineup** / **ours**: the lineup we recommended before the week's first kickoff, kept since (later news does not change it) |
| `submitted_points` (V-1) | **started**: what the team really started, at Sleeper's points |
| `app_edge` (V-1) | **added** · "our lineups would have added": ours minus started (below zero: the managers' own lineups did better) |
| `regret`, the hindsight optimum (V-1) | **best lineup in hindsight** ("+313.7 pts over the ones started") · the console's column **left on bench**; never "regret" on a page |
| `record_source = 'reconstructed'` (V-1) | **rebuilt**: a week played before the record existed, its lineups rebuilt from the projections locked then, with the final injury report (a star on the week) |
| the close calls graded (V-1, `validation.calibration`) | "The coin flips landed 54% for the side we leaned (52% expected, 31 calls)": **landed** = the player we started outscored the one on the bench (a tie counts half); the console's **Brier score**: 0 = perfect, 0.25 = a coin flip every time |
| `is_news_affected` (V-1) | "a starter's injury report changed after our build" |
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
| stat-line pieces × scoring (IA-3) | "Why this number": "8.9 targets → 5.5 catches → 96 yards → 0.48 TDs → 15.4 points per game × 12 games = 185", then one line a piece ("5.5 catches × 0.5 = +2.7", "8.9 targets (no points on their own)"); what a per-unit price cannot show is its own line: "yardage bonuses (a big game pays extra in this league)" or "the small pieces and rounding" |
| market line, `market_points` (IA-3) | "Sleeper has him at 16.2." (this week, this league's scoring); under 70% / over 140% of it: "We're well under (over) the market: our number follows his recent usage. Treat it with care."; none: "Sleeper's number for this week is not in yet." |
| `piece_columns` (IA-3) | per game, projected: Att · Pass yd · Pass TD · INT (QB); Car · Rush yd · Tgt · Rec · Rec yd · TD (RB); Tgt · Rec · Rec yd · TD (WR / TE) |
| the rankings' honesty line (IA-3, `about.RANKINGS_HOWTO`) | "How to read the rankings": from his work, not his name; superflex / 6-point passing TDs put quarterbacks on top by design; Sleeper's number is there to compare |
| matchup tone (IB-3) | **Favorable / Neutral / Difficult**: the word in the state color, ▲ / ▼ beside it; "No read" when no ranked corner is named |
| tough rank (IB-3) | one direction on the Matchups screen: "#1 = the toughest for the offense" ("#3 toughest vs RB", small and grey under the tone) |
| cornerback certainty (IB-3, `call_strength`) | **likely** (his targets lean 15+ points to one side) · **unclear** (either outside corner) · **no call**; beside the tone, never a "shutdown" badge: "the 17th-hardest of 74 starting corners to throw on" |
| value to my lineup (IB-3, `lineup_points`) | "Value to my lineup": what he adds to your best lineup over the weeks left; one of yours = what you lose without him; "Your QB2 only plays in week 7: 16 points over your next-best there", "Your backup QB never starts for you behind Mahomes: he adds nothing to your lineup (insurance only)", "Free agent: would start for you in 12 of 13 weeks left, +20 points to your lineup" |
| card status (IB-3, IB-0's `status`) | **Roster alert** (IN-5; was "Change needed": the call is not in your Sleeper lineup) · **Already set** · **Close call** (a coin flip); the strength word: Clear · Lean · Coin flip |
| yardstick (Receivers, U-17) | what the season's top-12 at the position (the 12 with the most points per game) average |
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

| My Week's actions (IE-1, `myweek.build_actions`) | at most three, the most urgent first: **Roster alert** (IN-5; was "Change needed") ("Start Wilson at FLEX (or Croskey-Merritt: a coin flip) in place of Jefferson.") · **Close call** ("Keep Addison and Nabers ahead of McConkey for now.") · **Waiver claim** ("Claim Dalton Schultz: about 3 more starter points this week."); one sentence naming the players, then the reason and what could change it ("Check his status again before kickoff."); the numbers behind "Why? The numbers behind it" |
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
| **News feed** (My Week; IN-5, was "What changed") | the overlay's move ("Justin Jefferson is out (ankle) — Michael Wilson starts at FLEX2 · Injury report (ESPN) · 2 h ago") then the week's news from the last 24 hours ("Justin Jefferson: <RotoWire's headline> · RotoWire via ESPN ↗ · 5 h ago"), at most five; none: "Nothing has changed since the morning build." | a feed name without a time |
| the news line (card, pane) | the item about him first (RotoWire's blurb, or a headline that names him); an article-level headline is labelled **League news** | a league story as "News" about him |
| the matchup rank, anywhere (`cards.rank_words`, `lib/words.ts rankWords`) | "2nd-fewest WR points allowed" (31 of 32) · "5th-most RB points allowed" (5) · "the most / the fewest …" | a bare "#31", or a "#" whose direction changes by screen |
| a starter's margin (My Week's lineup) | "4.63 over Lloyd" (the bench player who would come in: `cards.alternative`) · "no eligible reserve" (the slot would be empty: the number is his whole projection, not a gap) | "Margin" with no comparator |
| the bench expander | the bench and who can't play only | the starters again |
| Compare's bold | the better number where it bears on the call: projected points, the low-end / high-end outcome, points per game, the rest of the season; the usage rows only between two players of the same position ("bold: the better number in points (usage is not compared across positions)") | more carries for an RB bolded against a WR |
| Compare's sections | "This season (2 games)" — the sample size once; the "Last 3 games" section dropped when it is the same games | the same numbers twice |
| the range, everywhere (Compare, About, Waivers, the console's cards) | **Typical range** (the middle 50% of outcomes) · **Low-end / high-end outcome** | "most weeks", "floor", "ceiling" on a page |
| the role line (card, pane) | before his fourth game "Role: **not enough games to say** — 2 games so far; a change is called against his own earlier games, from his fourth game."; after it "Role: **role steady over N games** — …" | "no role change detected" beside "not enough games" |
| a metric tile with no value | its definition (first-read share: his first-read targets ÷ his team's charted dropbacks with a first read; red-zone share: his share of his team's red-zone targets / carries) + "Not available for this player: no charted plays for him yet (unknown, not zero)." | a greyed tile with no words |
| below / above expectation (Trends, the game log) | "1.2 below what his opportunities suggest: an observed gap, not a forecast" (the game log); Trends since Wave I-P: § "Trends, graded" (IP-3) | "expect him to pick up / cool off", "buy him while he is cheap" |
| the drawer (research pane) | the projection and its range, where he stands, the news, his role, his usage, his lineup line; behind expanders: "Week by week and season numbers", "Schedule" (week · opponent · projected), "Game by game this season" | the whole player page |
| freshness (My Week's footer) | "Updated 7 d ago ›" → "Last data load Sat, Sep 26, 5:26 PM ET." and the feed names | the feed list as the first line |
| MFL's roster freshness (My Week, an MFL league; IG-3) | "MFL rosters updated 4:05 AM ET ›" → "Rosters and lineups read from MyFantasyLeague Sun, Oct 4, 4:05 AM ET (1 min ago); isuckatfantasy reads them again after 10 minutes. The projections are the morning build's." — above IF-4's line, which stays the morning build's | the morning build's time as the roster's |
| when claims run (Waivers, under the title; IG-3, `decisions.waiver_deadline`) | Sleeper: "Claims run Wednesday 3:00 AM ET (rolling waivers); players lock at their own kickoff — the next game starts Sunday 1:00 PM ET." · "Claims run every day at 5:00 AM ET (FAAB blind bids); …" · MFL: "Free agents are first come, first served on MFL: a claim is yours as soon as MFL takes it; …" · "Claims run on MFL's schedule for this league (blind bids, then first come, first served): see MFL for the time; …" | a guessed time where the league's settings do not give one ("see MFL" / "see Sleeper" instead) |
| the grades for a league we do not score (About, under the headline grade; IG-3) | "These grades use Forever Unclean Dynasty's scoring, not Make Football Great Again's, and there is no direct projection record for this MyFantasyLeague league: read them as how the model does in general." | the qualification below the metrics only |
| a stash written by the nightly (Waivers' Stashes; IG-3) | the writer's call: **claim** (the cheapest drop by IF-1's cost) or "Watch, no claim yet: if his role holds he adds +0.0 to your lineup over weeks 4–7 — under 1 this week and 3 over the weeks. Claim him when his role would put him in your lineup for more, or when a roster spot opens." | a drop on a watch |
| how a week was priced (M4, Wave I-G; About's record, the console's Record page; `scoring.record_pricing_sentence`) | "Weeks 1–4 were priced flat; from week 5 the bonuses are priced at their odds." — **priced flat**: a bonus counts only when the projected line reaches it; **at their odds**: the bonus × its chance of happening; nothing at all for a league without a bonus | "expected value", "EV", "the flag" on a page |

## Unknown is not zero, team units, the Finder's rule (Wave I-G, IG-1)

| Where | The words we use | Never |
|---|---|---|
| a player with no projection row (My Week's lineup and bench, Team, the trade lineups, a Waivers drop; the console) | a dash **—** titled "No projection for him this week: unknown, not 0" and the words **no projection** under his name (the console: a blank and the flag "no projection") | "0.00" (the solver counts him 0; the screen never says it) |
| the lineup total with a starter who has none (My Week, `unvalued_words`) | "1 starter has no projection and counts as 0 in this total." | a total with no word about it |
| a team unit's season value (MFL's team QB / team kicker) | **Season value above replacement**, against the best **free unit of the same kind** — "Houston Texans QB: 355 season points; the best free team QB, Arizona Cardinals QB, 378: 0 above" | a player as a team unit's replacement; "Not counted" for a unit that has a projection |
| the Finder's "left out" (`sanity.words`) | "We do not suggest a trade that gives away much more season value above replacement than it brings back (over a quarter of what you give, and not about even), or one that only works because our number for a player you give is far under Sleeper's. A player with no season projection is not judged." · a row: "you give 20 season value above replacement for 3: 17 more, over 25% of what you give" | "rest-of-season points" as the reason (a volume gap: all positions added up) |

## The decision record, personal (Wave I-H, V-2)

| Where | The words we use | Never |
|---|---|---|
| the Team page's block (title) | **Your calls this season** | "decision record", "regret", "edge" on a manager's screen |
| its sentence (`decisions.team.sentences.season`) | "Weeks 1–2: you started 265.0; our lineup would have scored 253.9; the best possible was 281.7." | "you lost 16.7 points"; "you should have" |
| its table | Week · You · Ours · Best · Sleeper; a rebuilt week starred, the footnote "Played before this record existed: rebuilt after kickoff from the projections locked then, with the final injury report — kinder to us than a real Thursday call." | "optimum", "app", "submitted" |
| one close call | "Chris Olave over Xavier Worthy (we gave it 64%): 18.6 to 11.0 — the right call." / "… — Xavier Worthy scored more." / "… — a tie." | "wrong", "bad call" |
| the calls line | "Our closest calls for you landed 3 of 6 (3.3 expected)." | "accuracy" |
| Sleeper as a comparator | **Sleeper's projections as a lineup** — "had every team started Sleeper's projections, the league would have scored …" | "the market's lineup"; "Sleeper's AI" |
| the news cases from the event store | "2 lineups had a starter's injury status change between our build and his kickoff; there our lineups scored −4.1 against the ones started. They are graded apart: we could not have known." | "news-affected" on a screen |
| About → Team | "Your team's calls this season ›" | |

## The stale state and the error states (Wave I-H, IH-1)

| Where | The words we use | Never |
|---|---|---|
| the morning update did not run (My Week: one line above the actions; `league_lab/freshness.py`, 30 hours) | "Yesterday's numbers: the morning update did not run. Injury statuses are still live." — two or more mornings missed: "Numbers from Friday, Oct 2: the morning update has not run since. Injury statuses are still live." · the footer: "Updated 1 d ago · the morning update did not run ›" with the same sentence on tap | "stale data", "the nightly", "ETL", a time with no word on what it means for the numbers |
| the same on the console's Data Status page (it has no live injury feed) | "… the morning update did not run. This console's injury tags are from that update too." | "Injury statuses are still live" on the console |
| the API down (no answer; the host's own 502 / 503 / 504 page) | "Cannot reach isuckatfantasy right now. Check your connection, then try again." · "isuckatfantasy is not answering right now (error 502). It is usually back within a few minutes." + **Try again** | a spinner forever; "Failed to fetch"; "Bad Gateway" |
| a 500 | **Something broke on our side** — "Our server hit an error (500). The status page says whether the data is up and when it was last updated." + "The status page: /api/status" + **Try again** | "Internal Server Error" |
| still waiting (25 s, the request keeps going) | **Still waiting** — "isuckatfantasy is taking longer than usual to answer." + **Try again** | a skeleton with no end |
| our own 502 / 503 | "Sleeper did not answer. Try again in a minute." (MyFantasyLeague's name for an MFL league) · "The numbers are not ready yet. Try again in a few minutes." · "Busy right now. Try again in a minute." | — |
| a 401 after this browser was signed in (the cookie expired) | the password screen with "Signed out — sign in again." above "Private beta. Enter the password from your invite."; signing in goes back to the same screen | the plain password screen with no word on why |

## The small opens (Wave I-H, IH-2)

| Where | The words we use | Never |
|---|---|---|
| when daily claims run (Waivers, under the title; `decisions.waiver_deadline` + `daily_waivers_days`) | "Claims run every day except Saturday at 5:00 AM ET (FAAB blind bids); players lock at their own kickoff — …" (the dynasty; IG-3's "every day" stays for a league whose settings leave no day out) · "every day except Monday and Saturday" · "on Monday, Wednesday and Thursday" (three days or fewer: named) — ET day names | "every day" when the league's settings leave a day out |
| a Questionable tag that changes no lineup (My Week's "What changed") | "Questionable: Flowers (hamstring) — your lineup is unchanged · Injury report (ESPN) · 1 d ago" — once per player, only when the tag is news since the morning build (the store's event of the last 24 hours, or a copy newer than the build) | nothing at all; a second line for the same tag; "check before kickoff" as an instruction to bench him |
| MFL's roster freshness (Team, under the roster) | "MFL rosters updated 12:16 PM ET ›" → "This roster was read from MyFantasyLeague Sun, Oct 4, 12:16 PM ET (just now); isuckatfantasy reads it again after 10 minutes. The projections are the morning build's." | the morning build's time as the roster's |
| the console's stash card (Waiver Wire; `signals.stash_call_words`) | the caption "Upside stash · watch, no claim yet: his role is growing before his points do" (or "· claim: …"); a watch names no drop and says the web's watch line word for word; a claim: "Claim: if his role holds he adds +6.4 to your lineup over weeks 4–7; after what dropping Harrison Jr. costs, +4.1." | "Drop X: …" on a watch |
| a trade verdict with a player the season value cannot count (`trades.verdict`) | "…; season value not compared (1 player in it has no season projection): a lineup loss for them." | a lean ("you give up more season value") from the counted players alone |
| a dropped team unit (Waivers, MFL) | its cost reads as a player's: season value above the best **free unit of its kind** (IG-1), its later starts against that unit — a kicker claim drops the kicker it replaces ("New Orleans Saints K … Jacksonville Jaguars K") | a unit's later starts measured against a free unit worth 0 |

## The week's win probability (Wave I-H, IH-3)

| Where | The words we use | Never |
|---|---|---|
| My Week, under the opponent line (`myweek.week_line`) | "This week is a coin flip: 53%, 120 to 117 expected." · "You're a slight favorite this week: 58%, 121 to 117 expected." · "You're a clear underdog this week: 34%, 96 to 115 expected." · with games in: "… 2 of your 9 have played, 3 of theirs." · a double header: one line per game, the opponent's name first ("Big Mac Attack: You're …") · on hover: "assuming the players' weeks are independent except teammates and opponents" | a recommendation from it ("you're an underdog, start the boom-or-bust receiver"); "win probability" as a label on the page; 0% / 100% |
| 50–55% / 55–65% / 65%+ either way (`decisions.week_words`) | a coin flip / a slight favorite (underdog) / a clear favorite (underdog) | "a lean" for a week (the card's word for one call) |
| no number (`win.note`) | "no range for this league yet" · "the week has started and this league's live scores are not read yet" (an MFL league after the first kickoff): the page shows nothing | a 50% stand-in |
| the League screen, per team of a game this week | "53% · 120 expected" under each team; the note "How often each team wins, from both best lineups' ranges (assuming the players' weeks are independent except teammates and opponents)." | a favourite's name in bold as a pick |

## The calculation audit (Wave I-I, II-0)

| Where | The words we use | Never |
|---|---|---|
| Team, "Strength by slot vs the league" (`strength_by_slot`) | one bar per slot: "RB1 · Kyren Williams — 12.8 · 8th of 10", under it "League average 16.5, best 21.8 at RB1."; an empty slot "empty"; no projection "—" and "No projection for him yet: not ranked."; the card's line "Each bar is the player you start at that slot in week 4, his projected points; the tick is the league's average starter at the same slot, the end of the scale its best." | a league line in another unit than the bar (margins beside points); "RB" for two slots at once; a best below the bar |
| Team, under the bars | "By position, starters added up: RB 24.1 (9th of 10, average 29.5) · …"; "Usable depth 42.4: the best lineup your bench alone could field this week (4th of 10). Your bench players' projections add up to 59.6, but only 42.4 of it fits the starting slots: the rest is surplus no starting slot could use." | raw bench points as depth |
| the replacement chain (cards, the player card, My Week's margins) | "Bhayshul Tuten (RB) moves from FLEX to RB; Michael Wilson (WR) fills the open FLEX" · "an RB comes off the bench into RB" · "no legal move: RB goes empty" · the margin "over Michael Wilson (WR) after Tuten moves to RB1" | a WR named as an RB's replacement without the move that makes it legal; a locked player moving |
| names on one roster (`cards.display_name`) | the last name ("Williams"), the full name when the roster has two (Parker Washington / Malik Washington) | "over Washington" with two Washingtons |
| the partner card and the calculator (`trades.week_story`) | "Your lineup loses 0.5 this week but gains 7.2 over weeks 4–7 in total (week 6 loses 0.6)." · "Nothing changes this week; your lineup gains 2.0 over …" only when this week's number is under 0.05 either way | "Nothing changes this week" beside a −1.5 |

## Credible trades (Wave I-I, II-1)

| Where | The words we use | Never |
|---|---|---|
| the Finder when no trade passes (`verdict`) | **No compelling trade found.** "None of the 18 trades that raise both starting lineups over weeks 4–7 is worth proposing: 16 do not beat your own best alternative by a point, 10 do not beat the other team's and 4 are not a plausible offer. Your best move: …" | "Best partner" on a trade that loses to its own waiver comparison; a quota of weak trades |
| the trades that did not pass | **Explore alternatives** · "ideas to look at, not trades to propose" | a ranked list that reads as recommendations |
| the card's label (`plausibility.label`) | **Plausible offer** / **A roster-fit idea** (no market price for a player: "this is how the rosters fit, not what the players would fetch") / **Implausible** | "Likely", "Hard to say no", any percentage or chance of acceptance |
| a bye on the card (`your_effect.words`) | "+17.7 if an empty slot were left empty: the difference is bye cover the free pool gives anyway" | a gain from a slot priced at zero |
| the alternatives (`waiver_alternative.words`) | "Yours: … (a waiver claim (rolling waivers): it can be lost to a team ahead of you). Theirs: …" · "first come, first served: he is yours if you add him before anyone else" | a claim presented as certain |
| the K / DEF guardrail | "A K for a starter (Matthew Stafford): they have a K and the free pool holds one about as good, so a K is not worth a starter to them." | a rule naming a player |
| the card's two lists | **Why they might consider it** · **Reasons they might refuse** | "they will accept", "they would say yes" |
| their alternative not priced (Wave I-L, IL-4: `LEAGUE_LAB_FINDER_LAZY_THEIRS`) | "Theirs: their own best waiver move was not compared: the trade does not beat your own best alternative by a point, so no move of theirs changes the answer." (or "… adds +0.6 to their starters over weeks 4–7, under the 1-point bar" / "… is not a plausible offer" / "… is not legal now") | silence, or a 0 shown as their move |

## The setup flow and the platforms (Wave I-I, II-5)

| Where | The words we use | Never |
|---|---|---|
| the setup screen (`/leagues`) | "Fantasy platform" · Sleeper / MyFantasyLeague · the steps "Platform › League › Team › My Week" · "Your Sleeper username, or a league link" · "Find your MyFantasyLeague league" · "Where do I find these?" with the example `sleeper.com/leagues/1389709692405551104/team` / "Where do I find the league id?" with `www45.myfantasyleague.com/2026/home/70587` · "No account needed: isuckatfantasy remembers your leagues on this device." | "log in with Sleeper" (Sleeper has no sign-in for us); "connect" for a public lookup |
| ESPN / Yahoo (`other-platforms`) | "Not supported yet." and why in one sentence each (ESPN: only your login cookies, which we will not ask for; Yahoo: an approved app and your Yahoo sign-in) | a "coming soon" badge, a disabled ESPN button, "supported" for anything not built |
| setup errors (`ondemand.SetupError`, the API's `code`) | `sleeper_user_unknown` "That Sleeper username does not exist: “x”." + the fix · `sleeper_username_invalid` "“x” cannot be a Sleeper username: they are letters, numbers and _ . - only." · `sleeper_league_unknown` "Sleeper has no football league 123…." · `sleeper_link_invalid` "That is not a Sleeper league link or id." · `mfl_league_private` "MFL league 70587 is private or does not exist. Ask the commissioner to allow API access to the league's data (MFL's league setup, the privacy option)." · `mfl_link_invalid` "That is not a MyFantasyLeague league link or id." — each with one line of what to do next (`fix`) | "Not found", "invalid input", an HTTP code, blaming the user |
| what a platform gives (`platforms.capabilities`) | "What isuckatfantasy reads from MFL leagues — 1 not available yet" · Yes / Partly / Not yet · "Transactions: not available for MFL leagues yet." wherever a screen would otherwise show an empty list (League's Latest moves) | an empty list or "No completed moves" for data we do not read; a substitute from another source without saying so |

## The copy standard (Wave I-I, II-4: the fifth review § 5–8)

*(II-4 owns this section; the other tasks add rows to theirs.)* One way to say a rate, everywhere — headings, chart
labels, tooltips, summaries, accessibility labels and generated text, the console too:

1. **Rates say "per"**: **per game**, **per target**, **per route run**, **per attempt**, **per carry**, **per week**
   ("8.9 targets per game", "yards per target", "+2.1 per week", "−1.2 per team per week"). Never "targets a game", <!-- copy-standard: keep -->
   "points a game", "yards a target", "a team a week". A noun stays a noun ("a game in progress", "they share a game"). <!-- copy-standard: keep -->
   Compact headers keep an abbreviation (Tgt/g, Car/g, YPRR) with the full name and definition in the tooltip.
2. **Every rate names its denominator and how it adds up.** A share over several games is the **summed numerator ÷
   the summed denominator over the same games** — never the average of weekly percentages.
3. **A window says what it counts**: games played vs calendar weeks; a "last 5" with three games played says
   "3 games", never five.
4. **The help layer carries the sample** (games), **the source and coverage**, and **the refresh time**.
5. **A share says share of what** (carries, targets, opportunities) and where (the red zone: inside the opponent's 20).
6. **Expected points** is the opportunity-based estimate (what his targets and carries are usually worth); **projected
   points** is the forecast for a coming week. Never one for the other.
7. The sweep: `scripts/copy_standard.py` rewrites rate phrasing in every user-facing file and the tests that pin it
   (idempotent; `--check` exits 1 while any is left). Run it after a merge.

| Label | Meaning (numerator ÷ denominator) | How it adds up | What we have |
|---|---|---|---|
| Receiving yards per game | his receiving yards ÷ the games he played (a game counts when he took an offensive snap or had a pass, carry, target or kick: `fct_player_game.played`) | summed yards ÷ games played in the window | verified present (nflverse weekly stats) |
| Target share | his targets ÷ his team's targets in the games he played (games he missed are out of both) | summed ÷ summed | verified present |
| Carry share | his rush attempts ÷ his team's rush attempts in the games he played — every rusher, quarterbacks included, as nflverse's weekly stats count them; kneel-downs are not removed by us | summed ÷ summed | verified present (the card's tile has this definition: Kyren Williams's 47.5%) |
| RB backfield carry share | his carries ÷ his team's running backs' carries in the same games — **apart** from carry share, which counts every rusher | summed ÷ summed | planned (not computed today) |
| Route participation | routes run ÷ team dropbacks in the games with participation data | summed ÷ summed | the participation **proxy** only (nflverse participation ends at 2025; unavailable in-season) — labelled as a proxy where shown |
| Targets per route run | targets ÷ routes run, both from the same games with route data | summed ÷ summed | proxy, 2025 and before; unavailable in-season |
| Yards per route run | receiving yards ÷ routes run, the same games | summed ÷ summed | proxy, 2025 and before; unavailable in-season |
| First-read target share | his first-read targets ÷ his team's charted first-read targets (FTN charting, from 2022; 2026 weeks 1–3) | summed ÷ summed, with the charting coverage beside it | derived from charted targeted plays — it is not every first-read assignment, and the words never imply it |
| Red-zone share | **red-zone carry share** (RB, QB: his carries inside the opponent's 20 ÷ his team's) or **red-zone target share** (WR, TE: targets inside the 20 ÷ the team's) — never a combined percentage | summed ÷ summed | verified present (play-by-play) |
| Expected fantasy points | what his targets and carries are usually worth (depth, field position), in the league's scoring — an opportunity-based estimate of the past | per game over the games played | verified present |
| Projected points | the forecast for a coming week in the league's scoring (the range beside it) | one week; rest of season = the sum of the weeks left | verified present |

### Season, news and the home (review § 6–8)

| Where | The words we use | Never |
|---|---|---|
| Season's three views (`/api/ros?view=`) | **My roster outlook** (default): "Your players only. Each number is what your best lineup loses over the weeks left without him …" · **Potential upgrades**: "Before acquisition cost: what each player would add to your best lineup … with nobody dropped and nothing sent … This is not his trade value." + "Not included: the drop a free agent needs, the players a trade sends, a waiver claim that might be lost." · **Rest-of-season projections**: "Projected points in this league's scoring over the weeks left, whoever rosters him: no roster, no lineup and no cost considered." | "Value to my lineup" over everyone at once; a hypothetical starter-point gain called trade value or market value |
| injury cover (My roster outlook, a reserve) | "Injury cover: if a starting RB misses a week, he projects +2.3 per week over the best free agent (6 bench weeks; not counted in his value above)." | adding cover into the lineup value |
| an upgrade's next step | "Free agent: compare the add / drop on Waivers (the drop is the cost) ›" · "On Run Bijan Run: price a trade (what you send is subtracted) ›" | a trade value |
| a news item's decision status | **Recommendation changed** · **Watch for confirmation** · **No action currently indicated** | "act now", a probability |
| its forecast status | "Included in the current projection: the injury report's status is applied to this week" — only with a recorded update (the overlay's applied status, or the report already in the rows) · "Context only: not in the projection" (news, briefs; "a Questionable tag does not change the projection"; a recap: "a game already played is in his stats") · "Update pending: the next injury check may move his projection" (an injury item newer than the last check) | "included" for a headline alone; counting an injury twice (the item and the status) |
| why it matters here | "Starts at WR1 in your best lineup this week" · "In the lineup you submitted, and he cannot play this week" · "On your bench this week" | — |
| the home's clocks (the footer) | "Data built 1 d ago · Injuries checked 3:32 PM ET · News 2 h ago ›" (the exact times on tap) | "Updated 1 d ago" alone; a stale warning (PO 2026-10-04: never tell users the data is stale) |
| Waivers' top claims | each card labelled **Helps this week (+3.0)** / **Covers a bye in week 7** / **Helps from week 6** / **Upside stash: no lineup gain yet**; the intro "The three strongest claims below: 2 help this week, 1 covers a bye (week 7). Each card's total is its gain over weeks 4–7."; "Vele and Schultz compete for the same roster spot (each drops McConkey): claim one of them." | "each with what it adds this week" when one adds nothing this week |
| Team | **Depth (bench lineup)**: "the best legal lineup your bench alone could field this week if every starter sat: usable depth, not raw bench points" | "Depth (the bench alone)" undefined |
| League | "Past luck says nothing about the weeks left: they depend on your points and the schedule ahead." · **Points left on the bench (hindsight)**: "the best lineup *knowing the final scores* … hindsight, not an avoidable mistake" | "It evens out over a season" |
| the player card's role line | "Upside: no additional modeled upside scenario available." | "Upside: nothing beyond the projection above" (an absent scenario is not an absence of upside) |

## The presentation list (Wave I-J, II-6)

| Where | The words we use | Never |
|---|---|---|
| Trades, when the answer at the top is "No compelling trade found" | the answer says it once, with its reason and "Your best move: …"; the Finder under it adds nothing for **Any** (Explore alternatives follows the chips); under a position chip one line, that position's reason: "**For a WR:** none of the 5 trades that raise both starting lineups over weeks 4–7 is worth proposing: …" | "No compelling trade found" twice on one screen; "Your best move" twice |
| Waivers' top three (a narrow card: three across, the drawer open, a phone) | the whole name (it wraps), then the badges, then the number with its label on one line: "+9.8 WEEKS 4–7 IN TOTAL" | a cut name ("Tyler …"); a badge under the label |

## Other platforms (Wave I-K, IK-3)

| Where | The words we use | Never |
|---|---|---|
| the platform choice (`/leagues`) | four choices, two by two: **Sleeper · MyFantasyLeague · ESPN · Yahoo**; under ESPN: "Unofficial: ESPN has no public API for fantasy leagues. isuckatfantasy reads what a public league shows anyone, read-only. New: not verified on a live league yet." · under Yahoo: "Through Yahoo's official Fantasy Sports API, read-only, after you allow it with your Yahoo sign-in. New: not verified on a live league yet." | "supported" for ESPN / Yahoo before the PO verifies a live league |
| what a provider gives (an unverified provider) | each line ends "— as built, not verified on a live league yet" (`platforms.UNVERIFIED`); "Partly" for all eight | "Yes" before verification |
| ESPN's box | "Your ESPN league link or id" · "A public ESPN league opens by its id. No password to ESPN: isuckatfantasy only reads what the league shows anyone." | — |
| a private ESPN league | "ESPN league 5150 is private. ESPN has no sign-in for other apps; a public league works by its id (Settings → Basic Settings → League Visibility in ESPN)" + the fix (switch off: "Ask the commissioner to make the league public, then try again."; on: "Or use “Private league?” …") | asking for cookies when the switch is off |
| "Private league?" (switch on only) | "Your ESPN cookies stay in your browser; isuckatfantasy reads your league with them and never stores them." · the button **Read my private league** | "log in with ESPN" (there is no such sign-in) |
| Yahoo, set up | **Connect with Yahoo** · "Yahoo asks you to allow read-only access to your fantasy leagues; isuckatfantasy keeps the connection in this browser only." · then "Your Yahoo leagues, 2026" with "Your team: …" and **Disconnect Yahoo** · "Or a Yahoo league link" | — |
| Yahoo, set up but Yahoo's approval of the app pending (`yahoo_pending`) | **Connect with Yahoo — coming soon** (disabled) · "Yahoo leagues are coming soon: Yahoo has not switched on this app's access to fantasy data yet. Nothing is wrong with your league or your Yahoo sign-in. Sleeper and MyFantasyLeague leagues work today." · a pasted link: "Yahoo leagues are not open here yet: Yahoo has not switched on this app's access to fantasy data." | "Your Yahoo connection has expired" or "league … is private or does not exist" for Yahoo's refusal of the app; a Connect button that sends a manager round the sign-in |
| Yahoo, connected, the league list refused for another reason | "Yahoo did not share your leagues just now. Your connection is fine: try again in a minute." | "expired … connect again" unless Yahoo refused the token itself |
| Yahoo, not set up | **Connect with Yahoo — coming soon** (disabled) · "Yahoo sign-in is not set up on this server yet. Sleeper and MyFantasyLeague leagues work today." | a button that leads nowhere |
| a league's provider after its name | "Synthetic Public League **ESPN**"; the switcher: "… · ESPN" / "… · Yahoo" (as "· MFL") | — |
| the league's own app (My Week, Waivers) | "Open ESPN to edit your lineup ↗" / "Open Yahoo to edit your lineup ↗" · "Claims run on ESPN's schedule for this league: see ESPN for the time; …" | a guessed claim time |
| a provider that did not answer | "ESPN did not answer. Try again in a minute." / "Yahoo did not answer. …" | "Sleeper did not answer" for another provider |

## MyFantasyLeague, complete (Wave I-L, IL-2)

| Where | The words we use | Never |
|---|---|---|
| League, this week's matchups card (any league whose platform gives live points: Sleeper's matchups call, MFL's live scoring) | under a team's name: "**8.0 so far**" (its score so far; nothing before its first points) beside "24% · 85 expected" | a live score on last week's results (final scores only); "live" without a number |
| My Week's win line after a game is over | "… 1 of your 7 have played, 0 of theirs." (IH-3's words; MFL counts a starter whose game MFL says is over) | a game in progress counted as played |
| Waivers, the stamp line (MFL) | first come: "Free agents are first come, first served on MFL: a claim is yours as soon as MFL takes it; players lock …" · blind bids: "Claims run on MFL's schedule for this league (blind bids): see MFL for the time; your blind-bid balance is $87.5; …" or "… your blind-bid balance is not in MFL's league export; …" · waiver order: "…: see MFL for the time; you are 4th in the waiver order; …" | a guessed claim time |
| League, "Latest moves" on an MFL league | a move made once the week's games have begun reads under the week in progress ("Week 4 · Oct 4") until MFL's week turns, then under the week MFL files it ("Week 5 · Oct 4"); a team unit by its name ("New York Giants QB") | a weekend's move missing until Tuesday; a player listed by an id (`mfl:0667`) |
| Waivers, "Recently added in this league" | each add: "Ja'Kobi Lane · WR — Knight Train (you) · week 3 · $12" (the bid when the league has one); the note "1 add in weeks 3–4 · MyFantasyLeague transactions"; none: "No adds in weeks 3–4."; not read: "Transactions: not available for … leagues yet." | an empty card when the moves are not read |

## Accounts, phase 2 (Wave I-L, IL-5)

| Where | The words we use | Never |
|---|---|---|
| the drawer, signed in | **☆ Watch** / **★ Watching** (a toggle; "Not saved: try again in a minute." if the server refused) | a Watch button for a guest |
| the watchlist's head | "5 players · projected points in League of Scrubs scoring, week 4. Tap a name for his card." ("(the first 30 of 42)" past the cap) | a count without the league and the week |
| a watchlist row | the name · position · NFL team · his status ("Questionable"; **"No injury designation"** when the report has none) · "8.3 projected · week 4" (or "not projected this week") · **"Free agent"** / **"Rostered by Run Bijan Run"** / **"On your team"** / "Not in this league's player pool" · **Remove** | "Healthy" (we only know there is no designation); 0 for a missing projection |
| the watchlist, signed out / off / empty | "Sign in to keep a watchlist on any device: sign in with your email, then tap ☆ Watch on any player's card." · "A watchlist comes with an account, and accounts are not on for this server yet." · "No players on your watchlist yet. Open any player's card and tap ☆ Watch." | a wall in front of the screen |
| where a connection is kept, signed in | Yahoo: "… keeps the connection in this browser and, encrypted, with your account (your other devices get it when you sign in)." · ESPN: "Your ESPN cookies stay in this browser and, encrypted, with your account, so your other devices read your league too; Disconnect removes them from both." (signed out: IK-1's / IK-2's words, unchanged) | "never stores them" to a signed-in person |
| the account page | "Yahoo: connected 2026-10-05 — it comes back on any device you sign in on." · "ESPN: needs reconnecting (it no longer opens your leagues)." + **Reconnect ESPN** · "No Yahoo or ESPN connection saved. Connect one on the league setup screen while signed in and it follows you." | a token, a GUID or a cookie value on screen |
| a provider switched off (`/api/providers` status `off`) | "ESPN leagues: not available right now. Sleeper and MyFantasyLeague leagues work as before." in place of the form | a form that can only fail |

## The Stats tables' columns (Wave I-M, IM-1)

The catalogue's labels are the words (`api/league_lab_api/stats.py`: `label` for the header's tooltip and the CSV,
`short` for the header, `definition` and `reason` for the hover). Rates say "per" (the copy standard above); a share says
share of what.

| Where | The words we use | Never |
|---|---|---|
| the group headers (IM-2 draws them over the Full table, in this order) | **Games and points** · **Receiving** · **Rushing** · **Passing** · **Air yards** · **Red zone** · **Efficiency** · **Expected points** · **Next Gen Stats** · **Charting** · **Snaps and routes** · **Advanced (PFR)** | other spellings ("NGS", "PFR advanced") as a group name |
| EPA | **Receiving EPA** / **Rushing EPA** / **EPA on dropbacks**, **EPA per target** / **per carry** / **per dropback**; the gloss once: "expected points added: how much each play moved his team's expected score" | "EPA/play" without the denominator; "value added" |
| success | **Receiving success rate** / **Rushing success rate** / **Dropback success rate**: "plays that gained expected points (EPA above 0) per target / carry / dropback" | "efficient" or "good" plays |
| first downs, touchdowns | **First downs per target** · **First downs per carry** · **Touchdowns per target** · **Touchdowns per carry** · **Touchdown passes per attempt** · **Interceptions per attempt** · **Sacks per dropback** | "TD rate" alone (rate of what) |
| air yards | **Weighted opportunity rating (WOPR)** ("1.5 × target share + 0.7 × air-yard share") · **Receiver air conversion ratio (RACR)** ("receiving yards per air yard thrown his way") · **Deep targets (20+ air yards)** · **Deep-target share (of his team's deep targets)** · **Deep targets, share of his targets** | "deep share" without saying of what |
| red zone | **Targets inside the 10** · **Carries inside the 10** | — |
| lines | **Receiving yards per reception** · **Yards per touch** ("rushing + receiving yards per carry or catch") · **Adjusted yards per attempt** · **Scramble yards** · **Share of his fantasy points from rushing** ("in this league's scoring; above 100% when his passing points are below zero") | — |
| expected points | **Expected fantasy points** (a total) · **Points over expected** ("his points minus his expected points over the same games: positive = more than his opportunities usually bring") — looking back, not a forecast (the copy standard's rule 6) | "due", "unlucky", "regression" |
| Next Gen Stats | **Average cushion (yards)** · **Intended air yards per target (Next Gen Stats)** · **Rushing efficiency (Next Gen Stats)** ("distance travelled per rushing yard: lower is more north–south") · **Carries against 8+ defenders in the box** · **Time to the line of scrimmage (seconds)** · **Aggressiveness (throws into tight windows)** · **Intended air yards per attempt (Next Gen Stats)**; the dash's reason is NGS's qualification ("… so this is unknown, not zero.") | a talent score |
| Pro Football Reference | **Drops** · **Drops per target** · **Broken tackles** · **Broken tackles per touch** · **Yards before contact per carry** · **Yards after contact per carry** · **Bad throws per attempt** · **Times pressured** · **Pressured per dropback**; the dash: "Pro Football Reference has no row for his games in this window (it lists a player once he has a target, carry or pass), so this is unknown, not zero." | 0 for a game PFR did not cover |
| unavailable (picker, disabled) | **Receiving yards after contact**: "Pro Football Reference publishes receiving yards after contact per season, not per game, so a window cannot use it." · **On-target throws per attempt**: "… per season only, so a window cannot use it." | an empty column |
| before the nightly builds the new table | "These columns arrive with the nightly update; they are not on this copy yet." | "stale", "missing data" |
| the CSV (`/api/players.csv`) | file `isuckatfantasy-stats-2026-wr-te-season-weeks-1-4.csv`; the header is the labels above ("Targets per game" with `per_game=1`); an unknown number is an empty cell | 0 for unknown |
## The open door (Wave I-M, IM-3)

| Where | The words we use | Never |
|---|---|---|
| the front door (first visit, no league) | "Our own projections for every player, his trends and his matchups, priced in your scoring — then your lineup, waivers and trades once you open your league." · **Browse the lab** · **Open your league** · the record's line (scored: "Through week 4, we called … right; Sleeper's numbers called …"; before: "Our record against Sleeper's own projections is kept week by week, from the first week both are saved before kickoff.") + **How we keep score** (About) | "sign up", "free trial", a wall in front of the screens |
| the bar, browsing without a league | IN-2 (Wave I-N): the scoring picker — "**Half PPR** ▾" and **Open your league** (§ "The lab without a league") | "No league", "Demo", "Guest", a made-up league name |
| My Team / Waivers without a league (IN-2: Trades opens the calculator) | "Open your league to see your lineup, waivers and trades." · "You are browsing without a league, in Half PPR scoring. Open your league on Sleeper, MyFantasyLeague, ESPN or Yahoo and this screen shows your own team." · **Open your league** · **Keep browsing players** | an error, a warning sign, "not found" |
| a decision answer for a reference key (API) | "Open your league to see this." (`code: needs_league`) | "league not found" |
| "Team in league" without a league | "—" (the API sends no owner) | "free agent" for every player |
| the rate limit (429) | "Too many requests from this connection. Try again in N seconds." ("… in a second." for one) | "rate limited", "abuse", "banned", a blank screen |
| a cross-site write refused (403, API only) | "This request came from another site, so it was refused." | — |
| a body too large (413, API only) | "That is more than this server takes in one request." | — |
| the record for PPR / Standard | "Our record is kept in Half PPR scoring (4 points per passing touchdown): the scoring of the league we project every morning." | a record that seems to be in a scoring it was not kept in |
## Passkeys (Wave I-M, IM-4)

| Where | The words we use | Never |
|---|---|---|
| the account page, signed out (passkeys on) | "An account keeps your leagues, your team in each and your saved Stats views, on any phone or computer." · **Create an account with a passkey** · "A passkey is your phone's or computer's own lock: Face ID, a fingerprint or its PIN. No password, no email." · **Sign in with a passkey** · with a mailer too: "Or use your email" + "No password: we email you a link." | a password field, ever; "biometric data" (it never leaves the device) |
| the setup screen's line | "Want your leagues on another phone or computer? **Save them with a passkey** — no password, no email." (both: "**Save them with a passkey or your email** — no password."; email only: IK-4's line) | |
| a browser without WebAuthn | "This browser cannot use passkeys (an app's built-in browser often cannot). Open isuckatfantasy.io in Safari, Chrome, Edge or Firefox to use one." | a button that can only fail |
| another address (Render's own) | "Passkeys work on isuckatfantasy.io only. Open https://isuckatfantasy.io/account to use one." (the API answers the same) | a cryptic failure |
| signed in | "Signed in with a passkey." (no email) · after the first tap: "Your account is made and this device's leagues are saved to it." · "Passkey added." | |
| the passkey list | "iPhone · Safari" — "added Oct 5, 2026 · last used Oct 5, 2026" / "not used to sign in yet" · **Remove** → "It stays in that device's passkey list until you delete it there, but it no longer opens this account." **Remove** / **Keep** · the only way in: "Your only way in" (no Remove) · **Add another passkey** (none yet: **Add a passkey**) | a credential id or a key on screen |
| recovery (no working email) | "If you lose every device that holds your passkeys, this account cannot be recovered: add one on a second device, or add your email below." (no mailer: "…on a second device.") | a promise of recovery we cannot keep |
| add an email (mailer on, no email) | label "Add an email" · **Email me a link** · "Check your email: open the link on this device to add **you@…** to your account. It works once, for 15 minutes." · the link: "Add this email to your isuckatfantasy account?" **Add my email** · "Your email is added: it is a second way into your account." | |
| the browser's sheet closed / refused | "Nothing changed: the passkey sheet was closed or timed out." · "This device already holds a passkey for your account." · "This browser could not use a passkey just now. Try again, or use another browser." | the browser's exception name |
| the API's refusals (`code`) | `passkey_challenge` "That passkey request is not one we made, or it was already used. Start again." · `passkey_expired` "That took longer than 5 minutes. Start again." · `passkey_browser` "That passkey request was started in another browser or tab. Start again here." · `passkey_refused` "Your device's answer did not check out, so nothing changed. Try again." · `passkey_cloned` "This passkey's counter went backwards, which can mean it was copied. You are not signed in. Use another passkey, or remove this one from your account." · `passkey_unknown` "That passkey is not saved to any isuckatfantasy account (it may have been removed). Sign in another way, or create a new account." · `passkey_taken` "That passkey is already saved to an account." · `last_sign_in` "This passkey is the only way into your account: without it nobody could sign in to it again. Add another passkey first, or delete the account." · `email_taken` "That email already has its own account. Sign out, then open the link again to sign in to that account." · `email_off` "Signing in by email is not on for this server. Use a passkey." · `passkeys_off` "Passkeys are not on for this server yet." · `cross_site` "This request came from another site, so it was refused." (IM-3's Guard's words: the same whichever layer refuses) · `accounts_paused` "New accounts are paused for a little while. Try again later." · `passkeys_busy` "Passkeys are busy just now. Try again in a few minutes." · `passkey_too_big` "We cannot keep that passkey: its id or key is longer than a passkey's may be. Try another device or browser." · limits: "Too many new passkeys from here. Try again in an hour." / "Too many passkey sign-ins from here. Try again in an hour." | the library's message (it can quote what the browser sent) |
| the privacy lines (Account; About: "…keeps your email address if you give one, the names and public keys of your passkeys, …") | "An account keeps your email address if you give one, the names of your passkeys (never anything that unlocks your device), the leagues and teams you save, your saved views and watchlist, and a Yahoo or ESPN connection only if you make one (encrypted) — nothing else." | |
## DFS (Wave I-M, IM-5; docs/DFS.md)

| Where | The words we use | Never |
|---|---|---|
| the screen's head (`/dfs`) | **Daily fantasy values** · before a file: "This week's projections in DraftKings scoring. Add the contest's salary file to see who is undervalued against its salaries." · after: "597 of 599 players on your DraftKings file valued; 89 project above what their salary buys on this slate." (a published file, IN-4: "… on the published DraftKings file valued; …") | "picks", "plays of the day" |
| the honesty line, under the site switch | "Projections are estimates, not promises: the model's record is on About." (a link to About) | a promise of any outcome |
| undervalued (the list's head) | **Undervalued** · "Projected well above what his salary buys at his position on this slate. Against this slate's salaries, not a promise." | "lock", "guaranteed", "free money", "beat", "can't miss", "smash" |
| overpriced | **Overpriced** · "Projected well below what his salary buys at his position on this slate." | "fade" as an order |
| a value row | "▲ +5.8 vs the slate's line (12.8) · 2.73 pts per $1,000" then the app's own reason (the matchup, the role, the betting line, an injury tag) or "Why this number: 7.7 targets → 4.7 catches → 67 yards → 0.39 TDs → 14.3 points this week (DraftKings scoring)." | a reason the numbers do not carry |
| the slate's line (the expander "How the slate's line is drawn") | "At WR on this slate, each $1,000 of salary buys 3.0 projected points (a straight line through 206 priced players; a typical player sits 1.6 points off it)." · none: "fewer than 8 priced players, no line." | "regression", "residual", "z-score" |
| the slate's head | "DraftKings classic · week 5 · 15 games" · "597 players matched to ours, 2 not matched (not valued). Salary cap $50,000." · "Week 5: the week whose games the file lists." · **See unmatched (2)**: "We never guess a player: these are not valued and not in lineups." then each reason ("no projection for him this week (unknown, not 0)", "listed as WR on MIA; we have that name as WR on LA", "ambiguous: 2 of our WRs on PIT match (…); not valued") | a silent drop; a guessed match |
| a refused file | "That does not look like a DraftKings or FanDuel salary file: expected a column named Salary and either Name + ID and TeamAbbrev (DraftKings) or First Name and Last Name (FanDuel). …" · "That file is 3.6 MB: a salary file is under 1 MB. …" · "That looks like a FanDuel single-game file …: only the full-roster contest is read yet." | "invalid input", an HTTP code |
| the file box | "Add the DraftKings salary file to see value" · "Drop the CSV here, choose it, or paste its text. It stays in this tab." · **Choose the file** · **Paste the text** · **Remove file** | "upload" (nothing is kept) |
| where the file is (three steps) | DraftKings: "… open the contest and go to its draft page …" · "Above the player list, tap Export to CSV: the file is DKSalaries.csv." · FanDuel: "… Download players list …" · "Add that file here (or paste its text). We read it in this tab and keep nothing." | — |
| the table's control | **Lineups**: **Either** / **Always in** / **Leave out** (the optimiser's locks and excludes) | "lock" |
| build | **Build lineups** · **Cash: projected points** / **Tournament: high-end outcome** · "The best lineups under the $50,000 cap and DraftKings' roster rules, each different by at least one player. … Players who cannot play are left out unless you put them in." | "optimal", "winning lineup" |
| a lineup card | "Lineup 1 · 123.7 projected · $0 left" · "Low-end to high-end outcome: 94.6–152.7 (if the players' weeks were independent; teammates and opponents move together, so the real range is wider)." · on a timeout: "The solver's budget ran out: the best lineup it found, not proven the best." · **Copy** · **Download for upload (3 lineups)** "The CSV DraftKings' lineup upload takes, with the file's own player ids." | a win chance; "cash line" |
| two people building lineups at once | "Another lineup is being built right now. Try again in a few seconds." (the server builds one at a time; the wait is seconds) | a spinner that never ends; an error code |
| the scoring expander | **How DraftKings scores it** — one line a rule, then "As DraftKings publishes it, October 2026: check the site's rules page." | — |
| the footer (every DFS screen) | "isuckatfantasy is not affiliated with DraftKings or FanDuel. Daily fantasy contests are not offered or legal everywhere and are for adults: check your state's rules." | — |
## DFS without the homework (Wave I-N, IN-4; docs/DFS.md § Context, § Published slates)

| Where | The words we use | Never |
|---|---|---|
| a context chip (beside a player; its sentence in the title and one tap away) | **Role up** / **Role down** · **Soft corner** / **Tough corner** / **Shutdown corner** / **Corner unclear** · **Soft defense** / **Tough defense** · **Team total 28.0** (the points Vegas expects his team to score) · a solid border: in the projection; a dashed border: not in it | "smash spot", "lock", "fade" |
| a signal's sentence | "Role up in his last two games (the 2 before in brackets): 27% of the targets (12%), 89% of the snaps (67%)." · "Over/under 47.5, BUF favoured by 2.5: Vegas expects BUF to score 25.0." · IN-3's matchup words as they come · then **In the projection** / **Not in the projection** | a share without "of what"; an average of weekly percentages |
| what the projection holds (the expander **What the projection already holds**) | "Context, not a forecast: these signals sit beside the projection and do not change it. "Worth a look" has no record behind it yet (no backtest)." · one line a signal: defense against his position — in the projection; the cornerback — not in the projection; role trend — in the projection (it reads his last 3 games and the season), routes run per dropback not available during the season; the betting line — in the projection; weather — not in the projection, not shown here yet · without IN-3's module: "Matchup: not available here." | "the model ignores" |
| **Worth a look** | "Players with at least two signals in their favour, one of them something the projection does not hold. Context, not a graded forecast: there is no record behind this list yet. Ordered by projection." (on a slate: "… by points per $1,000.") · each reason followed by "(not in the projection)" / "(in the projection)" · empty: "Nobody this week: the cornerback call is the signal the projection does not hold, and it is not available here." | "sleepers", "values you can't miss", "picks" |
| a published slate | the head "DraftKings classic · week 5 · 15 games" · "DraftKings' salary file for week 5, published here so you do not have to add one: the salaries are the site's own, for its main contest. Another contest (a different slate or game) has its own salaries." · **Use a different contest's file** · after an upload over it: **Back to the published slate** · an id we do not have: "No published slate by that name for this week." | "official", "live salaries" |
| stacks (Build lineups) | **No stack** / **QB + 1 pass catcher** / **QB + 2 pass catchers** · **Bring-back: one from his opponent** · **No defense against my quarterback** · **Most lineups per player** (%) · "A stack is a quarterback with his own receivers or tight end (and a bring-back, one player from the other side of his game). The rules only choose which lineups count; the projections are unchanged." | "correlation boost", "optimal stack" |
| a stack note | "Stacks: every lineup has the quarterback with at least 2 of his own pass catchers (WR or TE); a bring-back: at least one RB, WR or TE from the quarterback's opponent." · "Exposure: each player in at most 6 of the 20 lineups." · a rule that cannot be met: "No lineup can meet the quarterback with at least 2 of his own pass catchers (WR or TE) on this slate with these players set to always in and left out. Turn that rule off or change who is in." · showdown: "Stacks apply to classic and full-roster contests (one quarterback slot): not to showdown." | an infeasible-model message |

## The context record on DFS (Wave I-O, IO-1; docs/METRICS.md § "The context record")

| Where | The words we use | Never |
|---|---|---|
| **Worth a look — off (fix round)** | one quiet line under the board's intro and a published slate's notes, from the record: "We tried a "Worth a look" list and graded it on 2025 and 2026 weeks 1–4: it listed a receiver 37 times (in 29 games), and they finished 0.7 points better than everyone else against their projection (−1.1 to +2.7) — not distinguishable from chance. It is off until a rule earns its place in the record; the context chips stay beside each player." (a verdict of "more than chance would give" ends "It stays off until the record has more weeks") · without the record: nothing | a card with an empty list; "coming soon" |
| (retired by the fix round) **Worth a look**, with the record | "Players with at least two signals in their favour, one of them something the projection does not hold. Ordered by projection." then the record's sentence, e.g. "Graded on 2025 and 2026 weeks 1–4 with the cornerback counting (the rule until 6 October 2026), listed players scored above their projection in 15 of 37 games (41%; everyone else at the position 35%) and finished 0.7 points better than everyone else against it (−1.1 to +2.7) — not distinguishable from chance." · once kickoff rows are graded: "Since 2026 week 5, listed players scored above …" · the verdict is one of "not distinguishable from chance" / "more than chance would give" / "less than chance would give" / "too few games to tell" | a hit rate without n; a share compared with 50%; "beat" in a DFS line (the NEVER list of the e2e) |
| (retired) **Worth a look**, empty | "Nobody this week. The one signal outside the projection that could put a player here, the cornerback call, made no measurable difference when graded, so it no longer counts; nothing else outside the projection is available during the season." | "no picks this week" |
| (retired) the rule (What the projection already holds) | "Worth a look: at least 2 favourable signals, at least 1 of them not in the projection, and no difficult signal outside it. The cornerback call no longer counts: graded on 2025 and 2026 weeks 1–4 it made no measurable difference to how receivers scored against their projection." | |
| the corner's grade (What the projection already holds; IO-4's board reads the same `summary()["corner"]["words"]`) | "Graded on 2025 and 2026 weeks 1–4 (Half PPR): receivers with a likely shutdown corner finished 0.4 points below the other receivers against their projection (−1.4 to +0.7; 99 games), those with a likely easy one level with them (−1.1 to +1.2; 79 games) — no measurable effect either way." | "a shutdown corner costs him …" |
| the corner chip (its title and the row's detail) | from its quarter, never coloured (fix round): **Shutdown corner** · **Soft corner** · **Average corner** · **Corner unranked** (an unclear call shows in the row's detail only) · "Graded: no measurable effect (−0.4 points against the projection vs other receivers, −1.4 to +0.7, 99 games)." · "Graded: measurably above / below (…)" when the interval excludes 0 | a coloured chip for a tier graded with no effect |
| the weather chip | the forecast's numbers: **Wind 20 mph** · **Rain (0.13 in)** · **Snow** · **28°F**; its sentence "Forecast at kickoff (outdoors): wind 20 mph." · **Not in the projection** (dashed border) | "bad weather game", "fade the passing game" |
| the weather line (What the projection already holds) | "Weather: Not in the projection; outdoor games carry the forecast at kickoff when it is unusual: wind 15 mph or more, rain 0.1 in or more, snow, below freezing. Since 2016, passers averaged 7.1 yards per attempt under 10 mph of wind, 6.8 at 15–20 mph and 6.2 at 20+ (observed weather, 2,639 games); the forecast can miss." · no forecast: "no forecast for this week's games yet." | "the forecast is not shown here yet" (retired) |

## The Stats tables (Wave I-M, IM-2)

Players · Stats is the full table Andrew asked for ("a full table of that shown instead of … you have to click into
them"). The words on the screen (`routes/Players.svelte`, `components/stats/`):

| Where | The words we use | Never |
|---|---|---|
| the view switch (above the table) | **Key stats** · **Full table**, then "31 columns" (the count on screen) | "Basic / Advanced", "Pro view" |
| the group headers and toggles (IM-1's names; the client's map until the API sends them) | Games and points · Receiving · Rushing · Passing · Air yards · Red zone · Efficiency · Expected points · Next Gen Stats · Charting · Snaps and routes · Advanced (PFR); a chip reads "✓ Receiving" (shown) or "+ Receiving" (hidden: tap to show); a group of one or two columns shows a short form in its header — **Games**, **Expected**, **Snaps**, **Next Gen**, **PFR** — the whole name on hover and to a screen reader | color alone for shown / hidden |
| every group hidden | "Every column group is hidden. Tap a group above to show its columns." | an empty table |
| the rows | "Showing 50 of 291" + **Show all 291** · after it **Show the first 50** | "Load more", "Page 2" |
| the file | **↓ Download CSV**; the file's header row is the column labels ("Target share (%)", "Receiving yards per game"), unknown is an empty cell, never 0; its name `isuckatfantasy-stats-2026-season-wr-te-full.csv` | a 0 for unknown |
| a phone, the table wider than the screen | "Swipe for more →" (until the first sideways scroll) | — |
| a greyed number (a rate on a small sample) | on hover and on a tap: "6 targets in his 2 games. Small sample: 6 targets (under 10), so this rate moves a lot." — per target / per reception / per carry / per pass attempt rates, charted and Next Gen Stats rates (`SMALL` in `components/stats/columns.ts`: targets < 10, receptions < 8, carries < 15, pass attempts < 30, charted targets < 10, NGS targets < 10 / receptions < 8 / carries < 20 / pass attempts < 50) | "unreliable", "noisy" |
| a dash | on hover and on a tap: the column's reason ("No Next Gen Stats week in this window: … unknown, not zero.") | 0 |
| How to read this (added line) | "**Key stats** are the numbers to read first. **Full table** shows every column we have for the position, grouped (Receiving, Air yards, Red zone…): tap a group above the table to hide or show it. A greyed number rests on a small sample: tap it, or a dash, for the reason." | — |

## Matchups for everyone (Wave I-N, IN-3)

The board on `/matchups` (`components/matchups/Board.svelte`, `GET /api/matchups/board`; METRICS § "Matchups for
everyone"). Browsing it is the screen; with a league and a team it is one of two views.

| Where | The words we use | Never |
|---|---|---|
| the views (a league and a team) | **My players** (default: the screen as before) · **Everyone** (the board, plus who has him) | "All players", "League-wide" |
| the answer under the title | "Every player's matchup this week: the defense against his position and, for a receiver, the corner likely across from him." Title: "Matchups, week 4" (Everyone) / "Your matchups, week 4" (My players) | "No league", "Demo" |
| the controls | WR · TE · RB · QB; "Search a player"; **All** · **▲ Favorable (69)** · **Neutral (81)** · **▼ Difficult (69)**; "All games" / "DAL at HOU · Sun 1:00 PM ET"; "Sort: projected points" · "Sort: best matchup first" · "Sort: easiest corner first" (WR only) | "Filter", "Advanced" |
| the line under the controls | "Projected points in Half PPR scoring. The defense is in the projection; the corner is not (context only)." (+ for TE / RB / QB: "Tight ends get the defense against the position only: they mostly draw linebackers and safeties." / "… no cornerback call.") | "the model knows the matchup" |
| the line under the board (once) | (IO-4 fix round, mb1.1) "Projected points this week in Half PPR scoring, with the range 8 weeks in 10 land in (low-end to high-end). What the projection counts: the points each defense has allowed to the position (this season, the last 4 games and its rank) and the betting lines. Who plays cornerback is not in it: the corner call is a lean from where his targets go, shown for context." + IO-1's graded sentence when the record exists ("Graded on 2025 and 2026 weeks 1–4 (Half PPR): receivers with a likely shutdown corner finished 0.4 points below … — no measurable effect either way.") + the tone rule: "Matchup = the defense against his position (favorable: one of the 10 that give up the most; difficult: one of the 10 that give up the fewest; the rest neutral). The cornerback is shown beside it and does not move it." | a graded-sounding "edge", "boost", "downgrade"; "has not been graded yet" (it has: no measurable effect) |
| the columns (1300) | Player · Game · Projected · Defense vs WR · Corner across · Matchup; on a phone the row's own labels: "Projects 14.8 5.6–25.0", "Defense", "Corner" | "DvP", "CB" |
| a row | "vs ATL / at PHI" + "Sun 1:00 PM ET"; the defense chip + "gives up the 7th-most to WRs"; the corner "McDuffie #3 of 74" (likely) · "Woolen #8 or Mitchell #9" (unclear) · "No call", with **likely** / **unclear** / **no call** beside it and "top-quarter corner" in plain grey text when every named corner is in the top quarter (IO-4 fix round: no red badge); the Matchup chip — the defense's tone (▲ Favorable / Neutral / ▼ Difficult / No read) | "covered by", "shadowed by"; a red **Shutdown corner** badge; a corner that colours the row |
| a corner who is out | "no corner call: Trent McDuffie, named on his side, is not expected to play" (the corner column: "No call") | "faces a shutdown corner" about a corner who will not play |
| a row opened | the defense's sentence ("Philadelphia gives up the 9th-most points to receivers.") and, for a receiver, the corner's in plain words for his quarter ("Quinyon Mitchell (a top-quarter corner, #9 of 69) is likely across from him" · "either Woolen (top quarter, #8 of 69) or Mitchell (top quarter, #9 of 69) could be across from him" · "no corner call: too few targets to tell his side"; IO-4 fix round, was "a shutdown corner" / "easy to throw on" / "an average corner"), the named corners with their side, the certainty in words, his history against the likely corner, the matchup evidence, "Who has him: …" (a league only), **<name>: his numbers ›** | ", but …" joining the corner to the defense |
| the pager | "Showing 1–25 of 219 wide receivers" · **Previous** · **Next** | "Page 2 of 9", "Load more" |
| nothing found | "No wide receivers named like “Nacua” with a game this week." · "No wide receivers match these filters this week." · "The regular season is over." · "This week's matchups arrive with the next data refresh." | an error card, a 0 |
| refused parameters (API, 400) | "position is WR, TE, RB or QB." · "Type at least 2 letters of a name." · "A name is at most 40 characters." · "That game is not on this week's schedule." · "limit is 1 to 100." | — |
## The lab without a league (Wave I-N, IN-2)

Andrew: "It references that you don't, like, no league, which is just kind of a weird, not something that you would
really expect to see." Browsing, a screen says the **scoring** where the scoring matters and what a league would add
where it would add something. "No league" is never shown (the API's `league_name` for a reference key is the scoring).

| Where | The words we use | Never |
|---|---|---|
| the picker's button (where the league picker is) | the key in words: **Half PPR** · **PPR · superflex · 10 teams** (a phone: **PPR +2**, the options and the size counted) ▾ | "No league", "Demo" |
| the picker's panel | **Scoring**: PPR · Half PPR · Standard · ESPN default · Yahoo default, the picked one's rule line ("1 point per catch, 4 per passing touchdown, −1 per interception." · "ESPN's default: 1 point per catch, 4 per passing touchdown, −2 per interception." · "Yahoo's default: half a point per catch, 4 per passing touchdown, −1 per interception (the same points as Half PPR).") and "Sleeper has no single default: a Sleeper league picks PPR, Half PPR or Standard when it is made." · **Options**: Superflex "A second spot a quarterback can fill" · TE premium "+0.5 per tight-end catch" · 6-pt pass TD "6 points per passing touchdown instead of 4" · **League size**: 8 teams · 10 teams · 12 teams · 14 teams, "The size and superflex change a player's value (who is left on waivers), not his points." · **Open your league** · **Done** | a "Sleeper" preset, "custom scoring" |
| the tabs while browsing | Home · Players · Trades · DFS (My Team and Waivers are behind **Open your league**) | an invitation card on Trades |
| a player's pane / page head | the key in words + "· week 4" ("PPR · superflex · 10 teams · week 4") | "No league · Half PPR scoring" |
| the Value block (pane, page) | title "**Value** — in a 12-team Half PPR league, one quarterback"; tiles **Value** (season points above replacement), **Points, wk 4–18**, **Rank** (WR3 by value); the line "Value in a 12-team Half PPR league, one quarterback: his points above the best free WR (Kendrick Bourne, 90 points)." | "trade value", "worth", "free agent" |
| the foot of the pane / page | "Open your league to see who has him and what he is worth to your team." (the page: "Priced in Half PPR." before it) | "free agent", "rostered by", "your team" lines (absent, not empty) |
| the calculator's head | **Trade calculator** · "Any two sides, in Half PPR: what each side is worth over the rest of the regular season, and whether the gap is bigger than the uncertainty." | "fair / unfair", "win / lose the trade" |
| the calculator's answer | "You get more: 188 points of season value (likely +120 to +256)." · "You give more: …" · "About even: you get 30 points more season value than you give, inside the uncertainty (likely −24 to +84)." · "Add a player to each side to compare them." · "Not comparable yet: X has no rest-of-season projection (unknown, not zero)." | "smash accept", "fleece", a verdict without its range |
| how much of the gap is one player | "Bijan Robinson alone is worth more than the gap (202 points)." · "Bijan Robinson is 48 of the 64-point gap (75%)." | — |
| an uneven trade | "You get 1 roster spot back: worth one replacement-level player — about 90 points over weeks 4–18 (Kendrick Bourne, the best WR such a league leaves free), which is 0 above replacement, so the values above do not count it." · "You need 1 more roster spot: you drop a player worth about one replacement-level player — …" | a spot silently added to a side |
| a player row in the calculator | "WR1 by value · week 4: 14.8 (6–25) · 16.4 per game over the season left"; "bye in week N"; "no projection: unknown, not zero" | 0 for unknown |
| a side's total | "Value 140 · 230 season points, likely 192–268" | — |
| what a league would add | "Value in a 12-team Half PPR league, one quarterback. **Open your league to see what this does to your lineup.**" | — |
| How this is priced | fitted: "Priced in Half PPR: the ranges are fitted for this scoring every night." · on request: "Priced on request in ESPN default: the same projected stat lines, this scoring's points; the ranges are the nearest scoring we fit every night (PPR), stretched by how much more or less this one pays for the same line." + the value's definition + "The likely range is the middle 80% of the season points each side could score (each player's weeks read as independent): “about even” means the gap's range holds zero, or the two sides are within 10 points or 10%. A value is this season only: no draft picks, no keeper costs, no seasons after this one." | "accurate", "guaranteed" |
| the API's refusals (`/api/trade-calc/free`) | "give: at most 6 players" · "give: '…' is not a player id" · "a player cannot be on both sides" · "This calculator is for browsing without a league: open your league's own calculator." · "Not a scoring we know." | — |
<!-- ---- IN-1 -->
## The home page, the setup screen, the blog (Wave I-N, IN-1)

| Where | The words we use | Never |
|---|---|---|
| the home's head (`/home`, `/` with no league remembered) | **isuckatfantasy** · "Our own projections for every player, his trends and his matchups, priced in your scoring — then your lineup, waivers and trades once you open your league." · **Open your league** · **Browse players** · (from 900 px) "Sleeper, MyFantasyLeague, ESPN or Yahoo. No account, no password to your league." | "No league", "sign up", "free trial", marketing blocks before anything real |
| this week's top projections | **This week's top projections** · Half PPR; QB · RB · WR · TE; the number + "this week"; with IN-3's board "range 9.4–25.4" and "Projected points this week in Half PPR scoring, with the low-end to high-end outcome (8 weeks in 10 land between)."; without it "season 173 (141–204)" and "…; beside it the rest of the season and its low-end to high-end range (8 in 10 land between)." · none: "No projections to show at wide receivers right now." | a range without saying which one |
| matchups to target (IN-3's board) | **Matchups to target this week** · "Wide receivers in a favorable matchup, the highest projection first. The defense he faces is already in his projection; who plays cornerback is not." (favorable rows only) · "vs ATL" / "at PHI" · the tone chip ▲ Favorable + "16.8 this week" · one line: the defense's sentence ("Atlanta gives up the 7th-most points to receivers."), the corner's added only when the call is likely · **Every matchup ›** | "smash spot", "the matchup favors"; "context, not added to it" (the defense is in the projection) |
| how the projections have done | **How the projections have done** · the lead, the bad news first: "Through weeks 1–3 of this season, quarterbacks are our weak spot: 6.5 points off on average, against 5.4 in past seasons. Tight ends miss more than before too." (else "…the projections miss by about as much as in past seasons at every position, or less.") · columns **Average miss** "6.5 (before 5.4)" (worse than before by more than 10%: in the bad color) and **Inside the range** "79% (aim 80%)" · the gloss "Average miss: points between the projection and what he scored, per player. Inside the range: how often he landed between the low-end and high-end outcome. "Before": the same model on 2021–2025." · the record's line (About's) · **How we keep score ›** | hiding a bad position; "accuracy" |
| from the blog | **From the blog** · "Oct 6, 2026 · 4 min read" · **All posts ›** | — |
| the tools | **The tools, open to everyone** · Players "Every player's stats, trends and this week's projection." · Trade calculator "Weigh a trade in PPR, Half PPR or Standard." · Matchups "Who each receiver faces this week, and how tough it is." · DFS "DraftKings and FanDuel values for this week's slate." · "Every number here is in Half PPR scoring. Open your league and they are priced in its own rules." | "no league needed" (rule 9) |
| the setup screen (`/leagues`) | "‹ Home" (no league) / "‹ My week"; the results beside the form from 900 px, "Your leagues show here once you find them. **Or look around first ›**" (→ /home) before a search; **Find my leagues** → "Looking…"; none: "No leagues for that username this season. A league <username> joins on Sleeper shows up here; a league link works too." | a list that appears below the fold with nothing said |
| the blog's list (`/blog`) | **Blog** · "Fantasy football analysis: what the numbers say, and how far to trust them." · the aside **About this blog** "Analysis from isuckatfantasy: what the numbers say, how they are made, and where they have been wrong. Every player number links to his card." · **RSS feed** · **The tools** · empty: "No posts yet. The first one is on its way." · failed: "The posts did not load. Try again in a minute." | — |
| a post (`/blog/<slug>`) | "‹ Blog" · "By isuckatfantasy · Oct 6, 2026 · 4 min read" · **Copy link** → "Link copied" (no clipboard: "Copy this link:" + the address) · **More from the blog** · missing: "No post at that address." "It may have been renamed. See every post." · a draft (drafts on): **Draft** | "share" buttons for networks we do not use |
| link previews (`blog.py` `PAGES`) | "/blog": "Blog · isuckatfantasy" / "Fantasy football analysis from isuckatfantasy: what the numbers say, how they are made, and where they have been wrong." · "/players": "Every player's numbers · isuckatfantasy" · "/matchups": "This week's matchups · isuckatfantasy" · "/trade-calc": "Trade calculator · isuckatfantasy" · "/dfs": "Daily fantasy values · isuckatfantasy" · a post: its title and summary | a promise ("win your league") |
| posts written by the site | author **isuckatfantasy**, never Andrew's voice; Andrew's own posts carry his name | — |
<!-- ---- end IN-1 -->
<!-- ---- IN-6 (Wave I-N) -->
## Power rankings and the rest of the season (Wave I-N, IN-6; METRICS § "Power rankings and the season outlook")

| Where | The words we use | Never |
|---|---|---|
| League, the first block's title and line | **Power rankings** · "Ranked by the points each team's best lineup is expected to score per week over the rest of the season (weeks 5–16), with today's rosters and injuries." | a blend, a "power score", a secret formula; "best team" |
| its columns | **Per week** (the rank before the number: "1. 119.5") · **Record · points for** ("2–1 · 383 (5th)") · **Against** · **Schedule left** ("111.9 · 7th-hardest", "hardest", "easiest") | luck words in this table (the luck card has them) |
| the record against the points, when 3 places or more apart | "3–0 on the 7th-most points: a soft schedule so far" / "1–2 on the most points: a hard schedule so far"; the row's tag **Soft schedule so far** / **Hard schedule so far** | "lucky", "fraud", "due" |
| no arrows | "No movement arrows: last week's rest-of-season projections are not kept, so last week's ranking cannot be rebuilt." | an arrow made from anything else |
| the second block | **Rest of season** · "10,000 simulated seasons of weeks 4–14: each game drawn from both lineups' ranges, the same pieces as this week's odds. 4 teams make the playoffs; a tie on wins goes to points for." | "forecast", "prediction", "will make the playoffs" |
| what it assumes (once) | "It assumes rosters as they are today (no trades, claims or drops ahead); every team starts its best lineup; known injuries only (a player out today is out this week; injured reserve stays out); the further out the week, the wider its range." | — |
| honesty | "Context, not a graded forecast: the weekly pieces are graded; the season outlook has only been replayed on two past seasons of two leagues." · "No title odds: the playoff bracket is not simulated." | title odds; a percentage as a promise |
| its columns | **Projected record** ("8.5–5.5", under it "6 to 11 wins") · **Playoffs** ("73%"; "In" when clinched, "Out" when eliminated — proven on wins; "<1%" / ">99%" otherwise at the ends) · **Top seed** · **Bye** (a league with byes only) | 0% / 100% from the simulation alone |
| no playoff odds | "No playoff odds: MyFantasyLeague does not share how many teams make the playoffs, so playoff odds are left out." · "… this league has divisions: division winners' places are not simulated." | a guessed number of spots |
| no outlook | "No outlook for the rest of the season: week 3's results are not final yet: the outlook returns once the league has scored it." · "… the schedule for week 9 is not available from the league." · "… the regular season is over." · "… no range for this league yet." | an empty table; an error card |
| the definitions (a tap on a column's ⓘ) | **Power ranking**: "teams in order of the points their best lineup is expected to score per week over the rest of the season (each week's best legal lineup from today's roster, this league's scoring, the weeks to the league's final). Record and points so far are beside it, not in it." · **Record · points for** ("… \"Soft schedule so far\" / \"Hard schedule so far\" when the record's place and the points' place are 3 or more apart.") · **Against** · **Schedule left** ("Rank 1 = the hardest schedule left.") · **Projected record** ("the middle 80% of the win totals (1 season in 10 ends below, 1 in 10 above)") · **Playoff odds** ("100% and out only when it is certain on wins alone.") · **Top seed** · **Bye** | — |
<!-- ---- end IN-6 -->

<!-- ---- IP-1 (Wave I-P) -->
## How the projections have done, honestly (Wave I-P, IP-1; METRICS § "v3.4: the quarterback weak spot")

Proposed words for the home's "How the projections have done" lead and About's grades (`web/src/components/home/home.ts`
`gradeLead` is not IP-1's file: the PO places them). The rule behind them: a gap the sample cannot tell from the past is
said as that, with the past range beside it; a weak spot is named only when the interval says so.

| Where | The words we use | Never |
|---|---|---|
| the lead, a position worse on the means but inside the past range | "Through week 3, quarterbacks are where our projections miss most: 6.5 points per game. The model that made those weeks missed by 5.6 to 6.4 in the first three weeks of past seasons, so three weeks cannot tell this from a normal start." | "our weak spot" for a gap three weeks cannot measure |
| the lead, a position worse and measurably so | "Tight ends: 3.5 points per game, against 2.6 to 3.4 in past seasons' first three weeks — they caught more touchdowns than projected." | a cause the numbers do not show |
| "before" in the grades | the backtest of the model that made the weeks shown (`mart_projection_drift`, IP-1): "6.5 (before 5.9)" | the newest model's backtest beside an older model's weeks |
<!-- ---- end IP-1 -->

## Adding to it

A new metric or page adds its row here in the same change as its `help=` text. A release adds one entry to
`app/whats_new.md` (three to six bullets, newest on top) next to its `CHANGELOG.md` entry.

<!-- ---- IN-5 -->
## My Week says what it means (Wave I-N, IN-5)

Andrew, 2026-10-06: "you could probably just say, like, roster alert instead of change needed"; "the What Changed below
… you could probably just call that a news feed"; "Start Kelce out of your lineup — what does that mean?"

| Where | The words we use | Never |
|---|---|---|
| the status / action word (My Week's action chip, a card's chip; `lib/week.ts` `ACTION_WORD` / `STATUS_WORD`) | **Roster alert** · Close call · Waiver claim · Already set | "Change needed" |
| more actions than three (`myweek.more_words`) | "1 more roster alert: the lineup below shows every slot." · "2 more roster alerts and 1 close call: …" · "1 more close call: …" | "1 more change" for a close call |
| a starting spot nobody on the roster can fill (`myweek.open_spots`; kind `change`, counted with the roster alerts) | "Your quarterback spot is open: Mahomes and Young are on a bye. Add a quarterback before Sun 1:00 PM ET." (who cannot play and why, from the same words as every action: "is on a bye", "is out", "is on injured reserve"; the lineup's own players first; at most four named, "; 2 more can't play") · two spots of one kind: "Your 2 quarterback spots are open: … Add 2 quarterbacks before …" · nobody at the position: "Your kicker spot is open: nobody on your roster can play there this week." · a flex: "Your FLEX spot is open: Tuten is on a bye. Add a running back, wide receiver or tight end before …" · the reason: "Nobody else on your roster can play quarterback this week. Mahomes is still in your Sleeper lineup: start the player you add in his place." · "Nothing is claimed from here: add a quarterback in Sleeper." · the link: **Find a quarterback on Waivers ›** (`/waivers?position=QB`) | "Start Kelce out of your lineup"; a receiver "in place of" a quarterback; "Take Mahomes out" with nobody to put in |
| why a player cannot play (`myweek.cant_words`; the lineup build's reasons, `REASON_WORDS`) | "is on a bye" · "is out" · "is on injured reserve" · "is in your IR slot" · "is on your taxi squad" · "has no NFL team" · "is locked on your bench (his game has started)"; two players with one reason: "Mahomes and Young are on a bye" | "can't play (IR slot)" |
| Team's open row (`routes/Team.svelte`, `lib/week.ts` `waiversFor`) | "QB: nobody can play it this week" + **Find one on Waivers ›** (Waivers at the slot's position; a flex: every free agent) | — |
| the deadline of an open spot (`myweek.open_deadline`) | "before Sun 1:00 PM ET": the kickoff most of the roster's games still to start share (the main slate; the earliest on a tie); "before his game kicks off" when none is left | a Thursday time when the manager can add a Sunday player |
| a swap (unchanged words) | "Start Jefferson at FLEX (or Boston: a coin flip) in place of Croskey-Merritt." — an incoming player is paired only with an outgoing one he can legally replace (his slot, or the slot chain: an RB slides from FLEX to RB); the coin-flip clause once per action, never for a player the same action takes out | — |
| the news block's heading (My Week; `lib/feed.ts` `NEWS_FEED`) | **News feed** (its empty line stays "Nothing has changed since the morning build.") | "What changed" (the matchup evidence keeps "What changed" for its own corners line: another thing) |
| a screen that hit a render error (`ErrorCard crashed`, App.svelte's boundaries) | **This screen hit a problem** — "Something on this screen did not load. Reload the page; the other screens still work." + **Reload** | a blank screen; loading blocks forever |
<!-- ---- end IN-5 -->

<!-- ---- IO-4 -->
## The fix list (Wave I-O, IO-4)

Andrew, 2026-10-06 (the live check): "Start Washington ahead of Jefferson…" with Malik and Parker Washington on one
roster; a finished week's "Take player no longer on your roster out of your lineup."; games that already kicked off
still on the matchup board.

| Where | The words we use | Never |
|---|---|---|
| a player named by his last name in My Week (actions, reasons, the review lines, the news feed's "Inspect …"; `myweek.short_name`) | "Washington" when he is the only Washington on the roster; **"P. Washington"** / **"M. Washington"** when another player on the roster shares the last name (`cards.display_name` decides the collision); the full name when the two share the first initial too ("Josh Allen" beside Jaylen Allen); a defense keeps its name | "Washington" for one of two Washingtons; a first initial for a player whose last name nobody else has |
| a submitted lineup spot whose player has left the roster (`myweek.gone_actions`; a roster alert, one per spot) | "A player in your Sleeper lineup is no longer on your roster — set that spot again." (the platform's name: Sleeper, MyFantasyLeague …) · the reason: "Our lineup starts Washington there (your FLEX spot)." or "Start someone from your bench there (your RB spot), or add a player." · "Not in your Sleeper lineup yet: set that spot in Sleeper." | "Take player no longer on your roster out of your lineup." |
| the matchup board's games filter, once a game has kicked off (`Board.svelte`, `show=`) | **Still to play** (the default once a game has started) · **All games** · the count: "Showing 1–25 of 206 wide receivers still to play" | the board listing a played game's receivers as if they were still to come |
| a row whose game has kicked off (the badge; the game list's option) | **Started** · **Final** ("PIT at CLE · Thu 8:15 PM ET · Final") | — |
| the board's honesty line (`matchup_board.projection_words`; IO-4 fix round) | the projection's inputs, "Who plays cornerback is not in it: the corner call is a lean from where his targets go, shown for context." and IO-1's graded sentence when the record exists; without the record the inputs alone | "has not been graded yet"; a grade that is not there |
| Stats, the Role change group (`stats.py` CATALOGUE; `columns.ts` `sharePts`) | **Target share change** (Tgt % chg) · **Carry share change** (Car % chg, running backs) · **Snap share change** (Snap % chg); a cell: "+5.2 pts" / "−3.1 pts" (points of share, signed); its hover: "27.1% in his last 2 games against 12.0% in his 2 before them"; a dash: "Needs his last 2 games played in the window and at least 2 before them, each with the numbers, and enough team volume (20 team targets or carries, 60 team snaps per 2 games): pick a longer window." · the CSV header: "Target share change (points of share)" | "+5.2%" for a change of share (a percent of a percent); 0 for a short sample |
| My players' corner card (`Matchups.svelte` `cornerInfo`; IO-4 fix round) | a neutral chip: **Top-quarter corner** · **Middle-half corner** · **Bottom-quarter corner** · **Unranked corner** · **Either corner** (an unclear call) · **No call**, the certainty under it; the caption: "Top quarter = among the quarter of 74 starting corners hardest to throw on since the start of last season (#1 = the hardest); bottom quarter = the easiest quarter. The corner is shown for context: it is not in the projection and does not move the matchup." · How to read this: "The cornerback is context, not a reason to start or sit someone: graded against past games, a likely shutdown or easy corner made no measurable difference to a receiver's points against his projection, so it moves no matchup here." | a green / red chip from the corner; "Start the receiver whose likely corner is easier" |
| the home's "Matchups to target" line (`home.ts` `homeWords`) | the defense's sentence only: "Kansas City is in the middle against receivers." | the corner's sentence on the home |
| the best-corners split (`/api/matchups/cb` `cover_split.note`) | "Shutdown here = the corner's rank over the season to date, not what was known in the week of the game." | — |
<!-- ---- end IO-4 -->
<!-- ---- IO-2 -->
## The League link and movement (Wave I-O, IO-2)

Andrew, 2026-10-06: "make the League page shareable" — the link a league-mate opens from the group chat.

| Where | The words we use | Never |
|---|---|---|
| League, under the screen's answer (Sleeper and MyFantasyLeague leagues only) | **Share** (↗; "Link copied" for 2.5 s; no clipboard: "Copy this link:" and the address) · "The power rankings and the rest of the season, for anyone in the league." | a share button on an ESPN or Yahoo league (read with someone's own connection) |
| the link opened with no team (`guest-strip`) | **Is this your league?** + a picker whose first line is **Pick your team** (then it is the normal app) | "No league", "Sign in" |
| the link's preview card (the page shell; `outlook.preview`) | title "League of Scrubs: power rankings, week 5"; description "1. Run Bijan Run 119.5 (72% playoffs); 2. … 3. …. Points per week each team's best lineup should score over the rest of the season, and playoff odds from simulated seasons." (without playoff odds: the sentence ends at "season.") | a number not from the league's last build or stored row; a card for a private league |
| the arrows (Power rankings, before the per-week number) | **▲ 2** / **▼ 1** / **–** (the same place); tooltip and screen reader: "Up 2 places since last week's ranking" · "Down 1 place since last week's ranking" · "The same place as last week's ranking" | an arrow from anything but last week's kept ranking |
| the playoff odds' change (under the Playoffs number) | "+6 since last week" / "−4 since last week" (points of percentage; hidden under 1) | "+6%" (a relative change) |
| the line under Power rankings | with arrows: "▲ ▼: places moved since the ranking kept before week 4." · this week's kept, last week's not: "Movement shows from next week: this week's ranking is kept." · the store on, neither kept: "No movement arrows yet: each week's ranking is kept before its first game, and the arrows compare with last week's." · the store off (a server without the table): IN-6's "No movement arrows: last week's rest-of-season projections are not kept, so last week's ranking cannot be rebuilt." | — |
| title odds (Rest of season, a Sleeper league whose bracket its settings describe) | column **Title** (as the other chances: "<1%", ">99%", "Out" once eliminated); under the table: "Title: the 6-team bracket played out in every simulated season (weeks 15–17, the top 2 seeds skip the first round), re-seeded before each round (the best seed left plays the worst), as the league's Sleeper settings say; a round's points decide it, a tie goes to the higher seed. Context only: the title odds have not been replayed on past seasons." (a fixed bracket: "a fixed bracket (no re-seeding)"); its ⓘ: "Title: how often the team wins the league's playoff bracket in the simulated seasons …"; none: "No title odds: <why>." (MyFantasyLeague, divisions, a playoff week not projected yet) — this replaces IN-6's "No title odds: the playoff bracket is not simulated." where the bracket is known | a title percentage as a prediction; title odds on a league whose bracket is guessed |
| the season block while it is simulated (the power rankings already on screen) | "Playing out the rest of the season…" (a skeleton under it); failed: "No outlook for the rest of the season right now: <the reason>" | a spinner with no words; the whole block replaced by an error |
<!-- ---- end IO-2 -->
<!-- ---- IO-3 (Wave I-O) -->
## The blog editor (Wave I-O, IO-3; docs/BLOG.md § "The editor")

Andrew: "a blog that needs a file and a push won't get written". Only an editor (an account listed by the server) ever
sees these; a visitor sees the blog as before.

| Where | The words we use | Never |
|---|---|---|
| the ⋯ menu, `/blog` (an editor only) | **Write** · **Write a post** · **Your posts** with **Draft** / **Published** / **Deleted** and the date · on a post of theirs: **Edit** | a Write link for anyone else; "admin", "CMS", "dashboard" |
| the editor's head | **Write a post** (new) / **Edit post** · the chip **Draft** / **Published** / **Deleted** · "Saving soon…" · "Saving…" · "Saved 6:48 PM" · "Changes not saved yet" (a published post) · "Not saved" | "autosave failed", a spinner with no words |
| the fields | **Title** · **Summary** "(the list, link previews and the feed show it)" · **Tags** "(commas between)" · **Author line** (empty: the site's name) · **Address** "/blog/…" ("A published post keeps its address.") · **The post** "(markdown)" · "4.7 KB of 200 KB" · **Preview** "The post shows here as readers will see it." | "slug", "front matter", "body" |
| the toolbar | **Bold** · **Heading** · **List** · **Quote** · **Link** · **Table** · **Player** ("Link a player", "Search a name") · **Players table** ("Players for the table (up to 12)", "Columns (up to 8)", **Insert the table**, "The table shows each player's Stats row, Half PPR, season to date — it updates with every nightly.", "This post already has a players table: only the first one becomes a table.") | — |
| on a phone | **Write** · **Preview** (the switch) | — |
| pictures | **Picture** · "Add a picture (PNG, JPEG or WebP, 300 KB at most)" · "Uploading…" · **Your pictures** "(3 of 50)" · **Insert** · **Delete** · under the body: "Pictures: **Picture** above uploads one (PNG, JPEG or WebP, 300 KB at most). A file in blog/img/ in the repository works too: ![words](/blog/img/name.png)." · refusals: "A picture is a PNG, JPEG or WebP file." · "A picture is 300 KB at most. Make it smaller first." · "The blog holds 50 pictures at most. Delete one first." | "upload failed", a code |
| earlier versions | **Earlier versions** "(the last 20 kept)" · "Oct 6, 6:41 PM · 4.7 KB" · **Put this one back** → "The version saved Oct 6, 6:41 PM is back in the editor. It saves as a new version: nothing is lost." · none: "No earlier versions yet." | "revision", "rollback" |
| the starters | **New post from…** · **Matchups to target and avoid** "The board's favorable and difficult receivers" · **This week's top projections and their ranges** "By position, Half PPR" · **Players whose role is changing** "Targets, carries and snaps lately" · "Filling in…" · "A starter fills a draft with this week's numbers written in, on Half PPR. It never publishes by itself." · in the draft: "*As of Tuesday, October 6, 2026, week 5. The numbers are written in: they will not change after this is published.*" · "*Your take: …*" · the range: "projected 16.8 (7.3 to 28.8)" · "Range (10th to 90th)" · "Half PPR points. The range is the projection's 10th to 90th percentile: eight weeks in ten land inside it." · roles: "A bigger role lately" / "A smaller role lately" / "His share of his team's targets, carries and snaps in his last two games, against his games before them. It is context: the projection does not lean on these two games alone." | a starter that publishes; numbers that move after publishing; "smash", "fade" |
| the actions | **Publish** · **Save changes** (published) · **Unpublish** · **Delete** → **Delete it** / "Keep it" · **Restore as a draft** "Deleted posts can be restored for 30 days." · **Download every post** · after publishing: "Live at /blog/…" **Copy link** → "Link copied" | — |
| two tabs, one post | "This post was changed in another tab or on another device (saved version 3). Nothing was overwritten." · **Use the newer version** · **Keep mine and save it over** | a silent overwrite |
| a dropped connection | "No connection. Your text is kept on this device." · on the next visit: "This device kept text that was not saved (Oct 6, 6:52 PM)." **Put it back** · "Discard it" | "error", "sync failed" |
| refusals (the API's words) | "Sign in to write." · "This account cannot write on the blog." · "A post needs a title before it is published." · "The post is over 200 KB. Split it in two." · "The blog's storage is full. Delete old drafts, or export and tidy up." · "The blog holds 500 posts at most. Delete one first." · "Too many changes at once. Wait a minute." · "Saving again in a moment: your text is kept." (the 5-second floor; the editor waits it out and shows "Saving soon…") · "That could not be saved: a field is longer or shaped differently than the blog allows." · the address: "An address is lower-case letters and numbers joined by single dashes, at most 80 characters." · "That address is one the site uses. Pick another." · "A post in the repository already has that address. Pick another." · "Another post already has that address. Pick another." · "A published post keeps its address. Unpublish it to change the address." | a code or a status number on screen |
| the editor's address, not an editor | **Sign in to write** "Writing on the blog needs the editor's account. Sign in" · **This account does not write on the blog** "The blog has one editor for now. Read the blog" | — |
| the Account screen | **Your account id** · the id · **Copy** → "Copied" · "Only needed to be made a writer on the blog. It is not a password." | "user id", "uuid" |
<!-- ---- end IO-3 -->
<!-- ---- IP-5 (Wave I-P) -->
## Player pages that share, and "busy" for a refused read (Wave I-P, IP-5; SECURITY_PUBLIC § 15)

| Where | The words we use | Never |
|---|---|---|
| a player page's link preview (`/player/<gsis>`, the page shell; `player_share.card`) | title "Josh Allen (QB, BUF): 23.8 projected this week, 14–35 · isuckatfantasy" (the projection and its 80 % range in the default scoring, Half PPR); description "Week 4, Half PPR: vs NE, Sun 1 PM ET; the highest projection of 93 quarterbacks this week. 8 in 10 weeks like this land between 14 and 35 points." (a lower rank: "the 7th-highest projection of 120 wide receivers this week"; away: "at SF"; no range: the last sentence is left out) | a number this process does not already hold (the default card instead); "No league"; "stale" |
| a page whose address names a league (`?league=`) | (nothing on screen: `X-Robots-Tag: noindex` and `<meta name="robots" content="noindex">`) | — |
| any screen whose provider read was refused or failed and nothing good is held | the app's existing "Busy right now. Try again in a minute." (503 `busy`; the screen retries) — a held good answer is served instead, with its own stamps | "stale", "data may be out of date", an empty roster, a lineup built from an empty directory, "MFL player 12345" for a player MyFantasyLeague would not describe |
| the matchup evidence's "best corners" split (`/api/matchups/cb` → `cover_split`) | removed: always null (it ranked past weeks by the season to date; rebuilt as-of it is 3 games against top-quarter corners for the median receiver) | "vs shutdown corners 14.2 per game (5 games)" |
<!-- ---- end IP-5 -->

<!-- ---- IP-3 -->
## Trends, graded (Wave I-P, IP-3; docs/METRICS.md § "Trends and the role trend, graded")

Graded against the projection made before each next game: below-expectation players scored more the next week and
above-expectation players less, about as much as (or a little more than) their projection already expected. So the
words describe what happened and send the reader to the projection; nothing says "due", "buy" or "sell".

| Where | The words we use | Never |
|---|---|---|
| Trends' head, under the title (from the record; nothing without it) | "Graded on 2025 and 2026 weeks 1–4 (Half PPR): in their next game, players below expectation scored 1.5 points more than their average before and players above it 1.9 less — and their projections already expected that (no measurable difference against them; 4,282 games)." · when one side is measured: "…; those below expectation finished 0.3 points below the rest against their projection (−0.4 to −0.1; 11,129 games) and those above expectation level with their projection." | "due to bounce back", "running hot", "buy low" |
| the picked player's line (Trends' detail) | "Getting the targets of a 20.0-point player, scoring 39.4: 4 touchdowns in 2 games on 6 red-zone targets. 19.4 above what his opportunities suggest: what happened, and his projection already counts it." | "an observed gap" alone (it said what it is not, never where to look) |
| How to read this (Trends) | "**Below expectation** scores less than his opportunities suggest: his targets and carries usually bring more points. Graded on past weeks, players like him scored more the next week, about as much as their projection already expected: the gap is what happened, not a reason to buy on its own — look at his projection." · "**Above expectation** … Players like him scored less the next week, again about as much as their projection expected: not a reason to sell on its own." · with the record: "**Graded**: " + the record's full sentence | "a buy needs a price, which this screen does not have" (retired: true, but it implied the gap was a buy) |
| the record's full sentence (`summary()["trend"]["words"]`) | "Graded on 2025 and 2026 weeks 1–4 (Half PPR), in their next game: players below expectation scored 1.5 points more than their points per game before and finished 0.2 points above the other players against their projection (−0.1 to +0.5; 2,467 games) — no measurable difference; players above expectation scored 1.9 points less than before and finished 0.1 points below the others against their projection (−0.5 to +0.1; 1,815 games) — no measurable difference. The projection already counts a player's work and his points: a gap here is what happened, not a reason to buy or sell on its own." · a measured side: "— more / less than their projection gave them" | a share compared with 50%; a rate without n |
| the role trend's sentence (`summary()["role"]["words"]`; the role chip's words are the PO's to place) | "Graded on 2025 weeks 5–18 (Half PPR), in their next game: after "role up" players finished 0.2 points above the other players against their projection (−0.2 to +0.6; 1,022 games) — no measurable difference; after "role down" level with the others against their projection (−0.4 to +0.5; 815 games) — no measurable difference." | "role up: start him" |
| the API's Trends help (`TRENDS_HOWTO`) | "It is what happened, not a forecast: graded on past weeks, players below expectation scored more the next week and players above it less, about as much as their projection already expected." | "Above = running hot, below = due." (retired) |
<!-- ---- end IP-3 -->

<!-- ---- IP-2 -->
## Rankings for everyone and "Who should I start?" (Wave I-P, IP-2; METRICS § "Rankings and tiers")
Andrew: the most asked question in fantasy is "who do I start?" — a visitor without a league gets the answer too. The
screen says the scoring (never "No league"), the tier rule in one sentence, and how sure a start call is.

| Where | The words we use | Never |
|---|---|---|
| the tab (browsing) / the sub-tab (a league) | **Rankings** (browsing: Home · **Rankings** · Players · Trades · DFS; a league: Players → Stats · **Rankings** · Trends · Matchups · Compare) | "Leaderboard", "Board" |
| the head | eyebrow **Rankings · Half PPR** (browsing) / **Players · Rankings**; title **Who to start this week** / **Rest-of-season rankings**; "219 wide receivers ranked by week 4's projection in Half PPR scoring, in 16 tiers. Pick two to four to see who to start." | "No league"; "consensus", "ECR" |
| the switches | **This week** · **Rest of season**; QB · RB · WR · TE · **Flex** · K · DEF (K and DEF only where the scoring starts them) · "Search a player" | — |
| the tiers (one sentence under the switches) | "A tier is a run of players the first of them outscores in fewer than 55 weeks in 100: their order is a coin flip, so start whichever you like inside one." · the line between tiers: **Tier 2** · the rule at the foot: "A new tier starts at the first player the tier's first player outscores in 55 weeks in 100 or more (each from his range, centred on his projection)." | "tier 1 = must start", "elite", "sleeper" |
| the columns | **#** · **Player** · **Game** ("vs ATL", "Mon 8:15 PM ET", **Started** / **Final**) · **Projected · range 8 weeks in 10** (the number, a bar from the low end to the high end with a tick at the projection, "7–29") · **Matchup** (the defense's tone chip: **▲ Favorable** / **Neutral** / **▼ Difficult**, "No read" when there is none; its title is the defense's sentence) · **Who has him** ("Yours", a team's name, "Free agent"; a league only) / **Status** (browsing) · season: **Rest of season · the range around it** (the bar is the spread around his projection, the tick in the middle and the widest spread on the page reaching the edges: a season's range is narrow against its total), **Games left** "13 · 20.1 per game" | a cornerback, a shutdown tag or a "best matchup" sort on this screen (Wave I-O: graded, no measurable effect); "P10", "P90", "percentile" |
| the foot | week: "Projected points this week in Half PPR scoring, with the range 8 weeks in 10 land in. The matchup is the defense against his position (it is in the projection); who plays cornerback is not, and is not shown here." · season: "Projected points over the weeks left (weeks 4–17) in Half PPR scoring, whoever rosters him: no roster, no lineup and no cost considered. The range is 8 seasons in 10, the weeks read as independent." · browsing: "Open your league to see who has him, in your league's own scoring." | — |
| picking | the box on each row ("Pick Chris Olave to compare" / "Unpick …"), up to four · the bar: "1 picked: Chris Olave — pick one more" · **Clear** · **Who should I start? Compare 2 ›** | — |
| the answer (Compare's first card; `/compare?a=&b=&c=&d=`) | heading **Who should I start?** · the call, one sentence, by D6's scale on the whole percent it prints: 65+ "**Start Olave: he outscores Nacua in 71 of 100 such weeks — a clear call, not a sure one.**" · 55–64 "**Lean Olave: he outscores Nacua in 57 of 100 such weeks — close; either is fine.**" · under 55 "**A coin flip: Olave outscores Nacua in 52 of 100 such weeks — either is fine.**" · three or four: "… he outscores Smith-Njigba in 55 and Nacua in 57 of 100 such weeks — close; either is fine. Of the three, he scores the most in 41 of 100." · each player: "57 in 100" with a bar · "How often each outscores the other this week, in Half PPR scoring." / "How often each scores the most of the three this week …" | "lock", "must start", "100%", "0%", "guaranteed" |
| how sure | "How sure this is: the ranges are built to hold 8 weeks in 10 (through week 3 of 2026 they held 79 in 100); graded on 4,895 start-or-sit pairs from 2024–2025, calls we put at 55–65% came true 58 times in 100. Read anything under 65 as a lean, not a verdict." · three or four: "The chance of being the highest of three or four is not graded yet; each pair's chance is." · "Each player's range this week, centred on his projection; teammates and players facing each other move together, everyone else independently. The ranges are "if he plays"." | a call that sounds surer than 58 in 100 |
| a picked game under way | "Metcalf's game has kicked off: these chances are from before kickoff and do not count what has happened since." (two: "Metcalf and Boston's games have …") | live odds; a stale warning |
| Compare's head (browsing) | "… in Half PPR scoring." (was "in this league scoring" without a league) | "this league" without a league |
| the link preview | "Wide receiver rankings this week · isuckatfantasy" / "… for the rest of the season …" · "Every wide receiver ranked by this week's projection in PPR, Half PPR or Standard scoring, with his range, his matchup and tiers — and the chance one outscores another." | — |
| the home | "Every player ›" opens **Rankings** | — |
<!-- ---- end IP-2 -->
