# Interfaces between packages

What one package builds for another to read, in the shape the readers code against. Each section is owned by the
package that builds it; a change to a shape is announced here first.

## IN-3 — matchup context and the matchup board (Wave I-N, 2026-10-06; `api/league_lab_api/matchup_board.py`)

### `matchup_context(season: int, week: int, gsis_ids: list[str] | None = None) -> dict[str, dict]`

Read by DFS (IN-4) and the home (IN-1). Import it lazily and treat any failure as "not available":

```python
try:
    from .matchup_board import matchup_context
    ctx = matchup_context(season, week, ids)      # {} when the marts or the week are missing
except Exception:
    ctx = {}
```

```text
gsis_id -> {"opponent": "KC", "home": bool | None,
            "defense": {"tone": "favorable" | "neutral" | "difficult" | None, "tough_rank": int | None,
                        "n_ranked": int | None, "words": str | None},          # defense vs his position
            "cb": {"tone": same | None, "certainty": "likely" | "unclear" | "no call",
                   "corner": str | None, "corner_rank": int | None, "shutdown": bool,
                   "words": str | None} | None,                               # wide receivers only
            "tone": same | None,          # the one read of the two together
            "words": str | None}          # one sentence a screen can print as it is
```

* **Who is in it**: every QB / RB / WR / TE with a game in `week` (the week's projection rows, plus every receiver the
  cornerback mart lists), or only the `gsis_ids` asked for that are among them. A player on a bye, or without a row, is
  absent — say "matchup: not available here", never a neutral read.
* **Scoring-free**: `tough_rank` 1 = the defense that gives up the fewest points to the position (one scale for every
  league, `mart_defense_vs_position_current`); `corner_rank` 1 = the corner hardest to throw on (of `cb_n_ranked`,
  two seasons). `cb` is `None` for TE / RB / QB; for a WR without a call it is `{"certainty": "no call", "tone": None,
  "corner": None, "corner_rank": None, "shutdown": False, "words": "no corner call: …"}` — also when a corner the call
  names is not expected to play (the availability overlay): "no corner call: X, named on his side, is not expected to
  play".
* **`tone`**: the defense's tone, moved by the corner only on a likely call (a likely shutdown corner turns neutral
  into difficult, a likely easy one turns it favorable, a corner against the defense's read cancels it to neutral); an
  unclear call, no call, a solid or unranked corner never moves it; no defense read, no tone. The table: METRICS §
  "Matchups for everyone".
* **In the projection?** The defense against the position is (the projection's opponent features); the corner is not.
  A screen that shows the corner says "not in the projection" (`matchup_board.PROJECTION_WORDS` has the sentence).
* **Cost**: a few cached queries per (season, week), kept 10 minutes in the `matchup_board` memory region; ~170 ms
  cold, ~6 ms warm. Each call returns its own copy. Never raises.

### `GET /api/matchups/board`

`?league=&position=WR|TE|RB|QB&q=&game=&tone=&sort=&limit=&offset=` (the `research` bucket; a reference key answers
without ownership, a house or on-demand league adds `rostered_by_roster_id` / `rostered_by_team`).

```text
{league_id, league_name, season, week, position, q, game, tone, sort, limit, offset, scoring,
 projection_words, tone_words, position_note, rank_note,
 total,                                  # rows matching the filters (before paging)
 counts: {favorable, neutral, difficult, none},   # at the position, before the game / q / tone filters
 games: [{game_id, home, away, kickoff_at}],
 rows: [{gsis_id, player_name, position, team, headshot_url, report_status, opponent, is_home, kickoff_at, game_id,
         proj_points, p10, p25, p75, p90, [rostered_by_roster_id, rostered_by_team],
         context: <matchup_context's entry>, cb_detail: {n_ranked, certainty_words, history, named: [...]} | null,
         matchup_evidence: <research.matchup_evidence> | null}],
 notice?: "The regular season is over." | "This week's matchups arrive with the next data refresh."}
```

Defaults: `position=WR`, `sort=projection` (else `tone`: favorable first; `corner`: the easiest corner first), `limit=25`
(1–100), `offset=0` (0–5,000). `q`: 2–40 characters, a name as text. `game`: a `games[].game_id`. `tone`:
favorable / neutral / difficult / none. A bad parameter is 400 with the words; an unknown league 404. The home's
"Matchups to target this week": `?league=ref:half&sort=tone&tone=favorable&limit=5`.
