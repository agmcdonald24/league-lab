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
| PPG − xPPG | scoring above / below what his work is worth (below = due to pick up, above = due to cool off) |
| target share, carry share | his share of his team's targets / carries |
| snap % | share of plays he is on the field |
| first-read share | how often he is the quarterback's first look |
| route participation, routes proxy | how often he is on the field when the quarterback drops back (an estimate) |
| TPRR / YPRR | targets / yards per route |
| aDOT, air yards | how far downfield his targets travel |
| implied team total | the points Vegas expects his team to score |
| opp rank | the matchup rank: 1 = the defense that gives up the most to his position (the matchup you want) |
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

## Adding to it

A new metric or page adds its row here in the same change as its `help=` text. A release adds one entry to
`app/whats_new.md` (three to six bullets, newest on top) next to its `CHANGELOG.md` entry.
