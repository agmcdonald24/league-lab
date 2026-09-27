# Known limitations of the 2026-09-26 build

Everything here is a deliberate scope decision or a source constraint, tracked in
`PROJECT_PLAN.md`. Nothing on this list is hidden in the numbers: where a metric is missing it is
NULL or labelled "unavailable".

## Metrics and models

1. **Play-by-play (Phase 2, 2026-09-26).** Loaded as a core column subset (~190 of ~370 columns;
   `LEAGUE_LAB_PBP_COLUMNS=all` for everything — the archived parquet always has every column).
   Defensive participation (who was on the field on defense) is not modelled yet (P2-14).
2. **Routes are a proxy.** `routes_proxy` counts dropbacks a receiver was on the field for; it runs
   ≈10–15% above charting-service route counts, so TPRR/YPRR proxies are lower bounds. Participation
   files are published after each postseason, so the **current season has no routes proxy in-season**;
   `routes` / TPRR / YPRR without the proxy label stay NULL until a licensed feed is imported
   (`league-lab import-routes`). Nothing is inferred from snaps.
2a. **First reads depend on FTN coverage** (≈98–99% of targets carry a read code; per-game coverage
   is shown and a <90% warning appears). 2016–2021 are not charted (blank, not zero). The `read_thrown`
   coding follows the data (`1` = first read), not the nflreadr dictionary's "0 from 2023" — see METRICS.md.
3. **Snap counts are keyed by PFR id** and joined through `nfl_players.pfr_id`. A player whose
   PFR id is missing or ambiguous has `snaps_known = false` (unknown, not zero).
4. **Team defense is observed only.** DEF points come from Sleeper's `players_points`; League Lab
   does not recompute defensive scoring and does not model individual defenders.
5. **Recomputed points are an approximation** of Sleeper's scoring (blocked kicks in distance
   buckets, position-conditional bonuses, first-down keys — see `METRICS.md`; yardage-game and
   long-touchdown bonuses *are* modelled). Observed points remain the source of truth for league
   history. Expected points leave bonus keys out by design.
6. **`player_team_history` grain is player-week**, not a validity interval; a mid-week
   transaction shows the roster the file captured for that week.
7. **Postseason league weeks** (Sleeper playoffs) are included in `league_player_week` and
   flagged in `fct_league_matchup`; standings use regular-season weeks only. Median-scoring or
   bye rules, if the league ever used them, are not modelled.
8. **Draft value uses current scoring** for NFL season totals so seasons are comparable; the
   league-observed columns show what the player scored while actually started.

## Manager's Edge specifics (2026-09-26)

9a. **Expected points are a model's opinion** (ffverse/ffopportunity, pass/rush/receive only). Kickers have
    no expected points; DEF has none. Treat `diff_per_game` as a prompt to look, not a verdict.
9b. **Cornerback context is not coverage assignment.** PFR records what happened when a defender was
    targeted; nobody in public data records who covered whom, and shadow coverage is invisible here.
9c. **Depth charts** are the latest snapshot only; "who was CB1 in week 5" is not modelled (snapshots
    are stored from 2025 on, so it can be).
9d. **Availability ignores team defenses** and any Sleeper player with no NFL id (see quarantine).
9e. **Optimal lineups** use Sleeper observed points and greedy slot filling; with more than one flex
    type the result can be suboptimal (this league has one). Validated against Sleeper `ppts`.
9f. **Share trends need four games**; early in the season L3 equals season-to-date.
9h. **Trends (2026-09-26)**: nothing is called before a player's fourth played game — the Trends page shows an
    *early read* (latest game vs season) instead and says so. The noise scale is the player's own season sd, so a
    player with 4 games has a rough sd and a `z` that is easy to clear or miss; `confidence` reflects it. Trends are
    season-to-date only (no "as of week N" history yet — T-11). No route-based trends until routes exist (P2-12).
    Defense trends use points allowed under current scoring, so a rule change would move every season.
9g. **FAAB** shows amount spent (from transactions); Sleeper does not expose remaining budget per roster
    beyond `waiver_budget_used`.

## Rankings specifics (2026-09-26)

10a. **The projection is a linear baseline**, fitted once on 2019–2022 and frozen. It knows nothing about
     a quarterback change, a trade, a new offensive coordinator or weather until they show up in usage.
     Weekly fantasy points are mostly noise: the out-of-sample rank correlation is 0.50–0.67, so read the
     board as "more likely than not", never as a verdict on one player.
10b. **Injury status is the week's report**, which lands late in the week; a Tuesday board has no `Out`
     flags yet. IR (`RES`) players are excluded from the rank at all times.
10c. **Vegas lines** come from nflverse's schedule file and only appear for games the market has priced
     (the next week, sometimes two); weeks without a line fall back to 22 implied points.
10d. **The universe for an upcoming week is the latest published roster**, so a player promoted or signed
     mid-week appears once the roster file updates (weekly, around game day).
10e. **No rest-of-season projection, no lineup optimizer yet** (R-08).

## Operations

9. **No orchestrator.** Refresh is a CLI (`league-lab refresh`) plus an optional launchd job.
   Run history lives in `ops.load_manifest` (survives restarts); there is no asset lineage UI.
10. **No blue/green publication.** dbt replaces each model transactionally, but a failed build in
    the middle of a run can leave marts from two builds side by side until the next successful
    build. The explorer does not pin a publication id. Phase 3 (P3-01) fixes this.
11. **Missed-refresh recovery is manual** (`make refresh`); launchd catches up on wake, but there
    is no reconciliation of "expected vs loaded" partitions on startup (P3-03).
12. **Backup restore has not been drilled.** `scripts/restore_test.sh` exists; run it (P3-04).
13. **Sleeper corrections**: the live season's weeks ≤ current week are re-fetched every refresh and
    replaced only when changed, so stat corrections are picked up; completed seasons are
    re-fetched every run too (cheap) — there is no separate Thursday job yet.
14. **The Mac is still the pipeline.** Hosting (docs/HOSTING.md) publishes marts after each refresh; if the Mac
    does not refresh, the hosted copy goes stale (the banner says when it was published). GitHub Actions (I-01) removes this.
14c. **Publishing is not atomic on the free tier** (0.5 GB cannot hold two copies): pages show "not built yet" for the
    minute or two of a restore. The publication contract (I-02) fixes this once the database has room for two copies.
14a. **Several leagues, two scales.** Several leagues can be loaded (comma-separated ids). Since S-01a (2026-09-27)
    league pages (Team Hub, Waiver Wire, Matchups start/sit, Trade Finder, League Intel, League draft) price PPG, xPPG,
    positional strength, keeper ranks and draft outcomes in the selected league's **current** scoring
    (`fct_player_game_league`). The NFL research pages (Players, Trends, Receivers), defense vs position — and the
    **Opp rank** columns derived from it on league pages — the baseline projection formula (Home's projection panel, the
    Rankings page's baseline option, the packs' baseline tables) and the as-of projection *features* stay in the
    **reference league's** scoring — the first id in `LEAGUE_LAB_SLEEPER_LEAGUE_ID`; the pages say so. Past seasons on a
    league page are priced under that league's current scoring (so years compare), not the scoring each season used —
    Sleeper's observed points and `points_recomputed` carry the historical scoring. Only leagues in the newest season are
    priced (a chain that did not renew has no per-league rows).
14b. **Beta password is not authentication.** It is a closed door for a link; the database role is read-only regardless.

## Verification caveats specific to this build

15. Phase 1 was verified in a sandbox with a synthetic Sleeper league; since 2026-09-26 the sandbox
    replays the **real league archive** fetched by Andrew's Mac (`data/raw/sleeper`), so every
    number in STATUS.md is from League of Scrubs data. Live Sleeper fetches still only happen on the Mac.
16. The sandbox ran PostgreSQL 16; the Mac runs 17. Nothing used is version-specific.
17. Sandbox Python could not perform TLS downloads through its proxy, so nflverse files were
    mirrored with `curl` and loaded with `--offline`. The HTTP layer (conditional requests,
    retries, atomic archive writes) is covered by unit tests with a mock transport; its first live
    run is also the bootstrap.
