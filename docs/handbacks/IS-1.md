# IS-1 — a status that rarely plays is not ranked as if it will (Wave I-S, 2026-10-08; continues IR-1)

Branch `dev/IS1` (from `main` `76b98df`), worktree `/home/claude/wt-iq4`, database `league_lab_iq4`.
METRICS § "A status that rarely plays" (av1.1: the rule first, then the tables), WORDS § "A status that rarely plays".

## 1. Done / not done / cut

**Done.** (1) Measured (2016–2025) before ruling. (2) The 25 % rule: **Doubtful is `unlikely`** (6 of 520 played,
1.2 %; `p_play` 0.01) — `sits()` true: 0 this week from `project` with the reason, out of this week's rankings and
tiers, "He is doubtful" in "Who should I start?", the same request-time gate on the board, Compare, DFS, the free
calculator's week, the player page's preview — and **not** out indefinitely (his later weeks and his season stay).
Questionable (66.6 %) stays ranked and flagged with `p_play` 0.67 and words; **not scaled** (its stored number is off
by ≈ +58 % zeros included — the PO's number, below). (3) The overlay's `CANNOT_PLAY` / `NOT_IN_TRENDS` / `FLAGGED` are
views of the gate (`SITS_CODES` / `CANNOT_PLAY` / `FLAGGED`); Sleeper "Inactive" with a team is one rule now
(`INACTIVE` in the gate). (4) "Not playing": two labelled parts ("Out", "Unlikely to play"), each ordered by his
projection when he still has one, else his points per game this season; Rankings (week and season), `/api/ros`
(a house league's list also lists the players its mart withholds), the board; one component (`NotPlaying.svelte`).
(5) Left over, all three: kickers' league-free lines (`ops.kd_lines`, and `ops.kd_ranges` built from them) gated in
`project`; `refleague.value_of` (the value without a league: card, Stats' value column, Compare) and `player_share`
(the player page's preview and the sitemap's top players) gated at request time; the house ROS mart withholds a player
out indefinitely (`ros_points` NULL, `out_indefinitely` column, unranked) instead of 0.0 over 1 game. (6) The audit's
first line counts "cannot play **or are unlikely to play**" and reads Sleeper's directory alone (no longer the stored
record it checks); the stored check knows Doubtful (dated after the previous week's last kickoff) and reads
`raw.sleeper_player`'s own payload.

**Not done / cut for the clock.** No Questionable scaling (by the rule; the PO's call). Trends keep a Doubtful player
(`NOT_IN_TRENDS` = the gate's `CANNOT_PLAY`, as before). The Questionable label's words (`availability.words`) are in
the Rankings answer but the row shows only "Questionable" (no tooltip). Kickers: none on this copy sits, so the
`ops.kd_lines` gate removed 0 rows here (the rule is unit-tested). No re-recording of saved e2e answers was needed.

## 2. Commits

`b500f94`, `8afd8e7`, plus the hand-back commit (see the final message for the last hash).

## 3. Evidence (`league_lab_iq4`)

**The live fact, reproduced.** This copy's directory (Oct 5) has Breece Hall "Out (quadriceps)" dated Oct 2 — last
week's game status, so he was ranked: **RB18, 11.8 (Half PPR)**. I set his directory row to the live site's entry
("Doubtful", news Oct 7 17:00 UTC), ran the guards and `project`, then **restored the row** (the stored board keeps the
run's result; the check still passes).

| Step | Result |
|---|---|
| `assert_nobody_who_cannot_play_is_projected` (error), before `project` | **FAIL 2** — Hall 12.94 / 11.75, Doubtful (the guard reads the directory) |
| `audit-lists` first lines, before | "…cannot play or are unlikely to play and are still ranked or valued: **1**" — "Breece Hall (NYJ, RB): Doubtful (quadriceps) · Sleeper, Oct 7 — this week rank 18, 12.9 [PPR, Standard, Half PPR]" |
| `project` | EXIT 0: "80 players who cannot play or are unlikely to play get 0 this week, 79 of them out indefinitely" |
| Hall, `ops.projections` | week 5: **0** with `availability` = `{"code": "DOUBTFUL", "why": "Doubtful (quadriceps) · Sleeper, Oct 7", "out_indefinitely": false, …}`; week 6: 13.16 / 11.96, week 7: 13.66 / 12.46 (kept) |
| Hall, house ROS mart | 145.94 over 12 / 120.90 over 11, ranked (his season stays) |
| Achane, house ROS mart | **NULL** over 1 game, unranked, `out_indefinitely` (was 0.0); 158 rows (79 × 2 leagues) withheld |
| Projection marts + guards | PASS=144 WARN=0 (incl. `ros_points_known_unless_out_indefinitely`, the stored check) |
| The check, after | PASS (error severity) |
| Audit, after | "…: **0**" |
| Frozen weeks 1–4 | `ops.projection_lines` 2,396 rows, `ops.projections` 4,856: **0 cells changed** |
| `ops.kd_lines` | 1,088 → 1,088 (no kicker sits on this copy) |

**Rankings on week 5, the API code, overlay off (stored record alone)**: RB 109 ranked / 14 tiers / not playing 24
(Out 23, Unlikely to play 1: Hall, "Doubtful: players listed doubtful have played about 1 in 100 times; not ranked this
week."); top 24 RB: Gibbs 20.6, B. Robinson 19.6, K. Williams 19.2, Ja. Williams 17.7, Taylor 16.9, Cook 16.4,
McCaffrey 15.5, Henry 15.2, C. Brown 14.3, Warren 14.1, Swift 13.9, A. Jones 13.7, Jeanty 13.4, Love 13.3, Skattebo
12.7, Hampton 11.9, Monangai 11.9, **Irving 11.8 (18, was Hall)**, Judkins 11.7, Tuten 10.7, Pollard 10.0, White 9.8,
Stevenson 9.8, **E. Wilson 9.6 (new)**. WR 170 / 33 out; TE 116 / 19; QB 83 / 4 — unchanged from this morning's after
list except their own refit noise. "Not playing" leads with Jordan Mason, Travis Etienne, De'Von Achane (points per
game), not Adam Randall. Season: Hall ranked #20 at 132.7. Start: "Hall is doubtful — players listed doubtful have
played about 1 in 100 times (Doubtful (quadriceps) · Sleeper, Oct 7). Start Irving." House `/ros` RB (League of
Scrubs): 50 players, not playing 23 (Achane listed: "IR (knee - acl) · Sleeper, Sep 28"). `refleague.value_of` leaves
Achane out (a dash).

**Item 3 — what changes because the overlay and the gate are one** (before → after):

| Place | Before | After |
|---|---|---|
| My Week / roster context / Waivers' overlay / trade board's week (`availability.CANNOT_PLAY`) | Doubtful benched | the same (by value the set is unchanged) |
| Trends (`NOT_IN_TRENDS`) | Doubtful listed | the same |
| Rankings week, start, board, Compare, the calculator's week, player preview, `project` (the gate, `sits()`) | Doubtful ranked with a full projection | not ranked; 0 this week; "He is doubtful" |
| DFS (`dfs._statuses`) | Doubtful out (overlay set) | Doubtful out (`sits()`) — the same result, one rule |
| The gate on Sleeper "Inactive" with a team | ranked (no word) | cannot play — matches the overlay; 13 directory rows, none projected |

## 4. Tests

Own: `tests/test_is1_unlikely.py` 13 + `tests/test_ir1_availability_gate.py` 30 (one expectation updated on purpose:
a Doubtful block now has week words) → 43 passed; `api/tests/test_is1.py` 6 + `api/tests/test_ir1.py` 14 (one updated on
purpose: Doubtful sits) → 20 passed. Edited modules' API files (is1, ir1, ip2, in2, in3, io4, im5, in4, i0a, ib0,
research, im3, iq4, io2, ip5, ia3, ii4, ib3): 447 passed, 20 failed, 9 skipped — 14 on the known list, 6 not:
`test_ib0::…would_not_start[None]`, `test_im5::test_dk_classic_slate`, `::test_fd_full_slate`,
`test_in3::test_board_without_a_league`, `test_in4::test_published_slates_listed`, `::test_the_listing_never_builds_a_slate`
— the same six as IR-1's hand-back on this database (the waiver mart is week 5 while tests pin week 4; a grade
sentence; slate counts on this week-5 board; a player named Lock), not this change. `check_root.sh`: 1,682 passed, 4
failed, all known, 0 new. ruff clean; copy standard clean; `npm run lint` 0 errors; build OK; `scripts/gate.sh
python` **PASSED** (root 780, api 25, ruff). e2e on port 8918, every spec that opens Rankings, Compare, `/ros`, the
board, the calculator, the home: e2e/fixtures.spec.ts, ia3, ib2, ib3, ic3, ic4, ie0, ie1, if2, if3, if4, ig1, ii1,
ii4, in1, in2, in3, inf1, io4, ip2, iq2, iq4, ir1, ir2, ir4, decisions — **223 passed, 9 skipped (their `fixme`s), 0
failed** on phone and desktop; `e2e/is1` 2 passed (375, 1300; screenshots `docs/handbacks/is1/`).

## 5. Edits outside my files

`api/league_lab_api/ondemand.py:237` (`order by r.ros_points desc nulls last`: the mart's withheld totals sort last —
IS-2 owns the file); `api/league_lab_api/refleague.py` `value_of` (item 5); `api/league_lab_api/player_share.py`
(`_sitting`, item 5); `dbt/models/marts/nfl/mart_player_week_projections.sql` (passes `p.availability`, pre_hook adds the
column) and `dbt/models/marts/edge/mart_player_ros_projection.sql` / `.yml` (item 5: NULL, `out_indefinitely`, the
not-null test replaced by `ros_points_known_unless_out_indefinitely`); `dfs.py`, `research.py`, `freetrade.py`,
`matchup_board.py` (my IR-1 blocks: `sits()`); `src/league_lab/cli.py` (the gate line); `web/src/lib/api.ts` (types at
the end); `CHANGELOG.md`, `docs/WORDS.md`, `docs/METRICS.md`, `dbt/seeds/metric_registry.csv` (av1.1).

## 6. The PO's lines

None required. The nightly's `availability-gate` step (soft) now also fails on a Doubtful player projected in the live
week. **The Questionable number for the PO / Andrew**: the stored number for a Questionable player is ≈ +58 % too high
zeros included (history; +75 % on 2026 weeks 1–4, n = 55); a scaling by ≈ 0.62 is the candidate — not shipped.

## 7. Found, not mine (IS-2's list)

`src/league_lab/lineup.py:854` benches on nflverse's `report_status` Out / Doubtful (the week's own report — fine on
Friday, empty midweek) and `mart_player_week_projections.is_rankable` reads the same field; both should take the gate
(`sits()`) through the stored `availability` record (now in the mart). `api/league_lab_api/ondemand.py`'s house `/ros`
query is the place to fetch the withheld players itself (I added `availability._withheld` for it).

## 8. Next

Decide the Questionable scaling with the bias table; a measured `p_play` per position once the counts allow (QB
Questionable 45.8 %); Trends' Doubtful policy; grade the 25 % rule's effect on lineups after week 5.
