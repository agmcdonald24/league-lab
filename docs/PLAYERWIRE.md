# PlayerWire briefs on the player card (plan N2)

PlayerWire is Andrew's own NFL player-news service: hand-reviewed, sourced briefs ("Jefferson (ankle) ruled out for
Sunday", with the evidence and how well it is verified). Since N2 the player card's news line shows PlayerWire's
briefs first and fills the rest from ESPN's public headlines (N1, `docs/ANY_LEAGUE.md` § "News").

## How it fits

```
Andrew's Mac                                                          Neon (hosted Postgres)              Render
──────────────────────────────────────────────                        ───────────────────────────         ─────────────────────
PlayerWire (its own repo, loopback only)
  read API http://127.0.0.1:8790 (production mode, bearer key)
        │  GET /v1/briefs (snapshot) · /v1/brief-changes?cursor=…
        ▼
scripts/playerwire_sync.py  (launchd every 15 min, role playerwire_writer) ──► schema playerwire  ◄──┐
                                                                           briefs, brief_players,   │ read-only role
                                                                           sync_state               │ league_lab_app
GitHub Actions nightly (07:37 ET, the marts' one writer) ───────────────► analytics, analytics_     ├── the API: /api/player/{gsis}
                                                                           seeds, ops (dropped and   │    → news: PlayerWire first,
                                                                           restored every night)  ◄──┘      ESPN fills to 3
```

* **The sync** (`scripts/playerwire_sync.py`) is PlayerWire's reference consumer (`playerwire/examples/
  league_lab_sync.py`) ported to Postgres: bootstrap from a pinned snapshot, then change pages; every page and its
  cursor commit in one transaction; a version never overwrites a newer one; a tombstone keeps the row and clears its
  text; 410 `cursor_expired` / 409 `cursor_filter_mismatch` → bootstrap again; 429 / 503 → wait `Retry-After`. It
  replicates **every** brief (no player filter) and never writes PlayerWire's synthetic fixture briefs. One run at a
  time (a Postgres advisory lock); it refuses to run as any role but `playerwire_writer`.
* **The API** (`api/league_lab_api/playerwire.py`, called from `news.py`) reads `playerwire.briefs` for the card's
  player: his own briefs and the briefs that name him as a related player, live (`deleted = false`) and published,
  newest first, none older than 14 days, at most 3. ESPN fills the slots left (ESPN is not asked when PlayerWire fills
  all three). Cached a minute. No schema, no grant, or the marts mid-restore → ESPN only, one warning in the log.
* **The card** (`web/src/components/NewsLine.svelte`): "News · 2 h ago · *headline* · Minnesota Vikings via PlayerWire ›
  OFFICIAL", the brief's news under it (muted, full width, cut at a word to 220 characters). ESPN items unchanged.

## One writer per schema — an extension of HOSTING.md § 5 (for Andrew to confirm)

HOSTING.md § 5 says GitHub Actions is the one writer of the hosted copy. That rule exists because the nightly's
`sync_to_hosted.sh` **drops and restores** `analytics` and `analytics_seeds` (and swaps `ops` in one transaction):
a second publisher would overwrite the record or drop schemas mid-restore. PlayerWire cannot follow that rule — its
API runs only on the Mac, and briefs have to reach the server within minutes, not once a night — so N2 proposes:

> **One writer per schema.** GitHub Actions' nightly is the only writer of `analytics`, `analytics_seeds` and `ops`
> (unchanged). The Mac's `playerwire_sync.py`, connected as role `playerwire_writer`, is the only writer of schema
> `playerwire`. Neither touches the other's schemas.

What makes that safe, and what was checked:

| Concern | Why it holds | Checked |
|---|---|---|
| The nightly drops the briefs | `sync_to_hosted.sh` drops only `analytics`, `analytics_seeds`, `ops`, `hosted_slim`; `playerwire` is not in its dump, its drop, its grants or its relation audit (`hosted_relations.py` knows six schemas, not this one) | `tests/test_playerwire_sync.py::test_the_schema_sql_keeps_the_marts_and_the_briefs_apart`; `api/tests/test_n2.py::test_the_hosted_audit_does_not_see_the_playerwire_schema`; on a Postgres 16 stand-in for Neon, `drop schema analytics cascade` left all 7 brief rows in place |
| A `cascade` reaches into `playerwire` | nothing in `playerwire` references `analytics` (no view, no foreign key); the API joins `analytics.player_id_map` at request time | the schema SQL has no `analytics.` in a statement (test above) |
| The Mac writes the marts | `playerwire_writer` owns `playerwire` and has no privilege anywhere else | on the stand-in: `select … from analytics.player_id_map`, `create table analytics.x`, `create table public.x` → `permission denied` |
| The briefs' writer runs as the owner by mistake | the sync checks `current_user` and refuses anything but `playerwire_writer` (exit 2) | `_sync_cycle` |
| Two syncs at once | `pg_try_advisory_lock`: the second exits 0 ("another playerwire sync holds the lock") | — |
| The app role can write | `league_lab_app` keeps `default_transaction_read_only`; it gets `USAGE` + `SELECT` (and default privileges for future tables) on `playerwire` | on the stand-in: an `insert` as `league_lab_app` → `cannot execute INSERT in a read-only transaction` |
| The 0.5 GB Neon cap | the briefs are small (a payload is ~1.5–4 KB; a thousand briefs ≈ 5 MB with indexes); the nightly's 480 MB budget counts only what it publishes, so it does not see them | measured on the stand-in (`pg_column_size(payload)` 1.4–1.6 KB per test brief) |

**The question for Andrew**: *Do you accept a second writer on Neon — the Mac's `playerwire_sync.py`, as role
`playerwire_writer`, writing only schema `playerwire` — next to GitHub Actions as the only writer of `analytics`,
`analytics_seeds` and `ops`? Yes makes HOSTING.md § 5 read "one writer per schema".* Until you say yes, nothing is
installed: the schema, the role and the launchd job are the three set-up steps below, and the API shows ESPN only
while the schema does not exist.

## Tables (`scripts/init_playerwire_schema.sql`, idempotent)

| Table | Columns | Notes |
|---|---|---|
| `playerwire.briefs` | `brief_id` (PK), `version`, `status` (`published` / `withdrawn`), `pw_player_id`, `primary_sleeper_id`, `primary_gsis_id`, `category`, `headline`, `news`, `analysis` (`analysis.text`), `verification_status`, `published_at`, `updated_at`, `evidence_url`, `evidence_publisher`, `evidence_published_at` (the first evidence item), `payload` jsonb, `synced_at`, `deleted`, `deleted_reason`, `deleted_at` | The full payload as served (AGENTS.md rule 6); display columns derived from it. A withdrawn brief keeps its row with the tombstone's version and reason, its text and evidence NULL and `payload` = the tombstone (`briefs_withdrawn_text_gone` check) |
| `playerwire.brief_players` | `brief_id`, `pw_player_id`, `sleeper_id`, `gsis_id`, `role` (`primary` / `related`) | The players a live brief names, with the external ids PlayerWire carried |
| `playerwire.sync_state` | `id = 1`, `sync_cursor`, `high_watermark`, `snapshot_watermark`, `filter_signature`, `bootstrapped_at`, `last_sync_at`, `last_error`, `last_error_at`, `api_url` | The cursor is written in the same transaction as the briefs it covers |

**Identity** (AGENTS.md rule 3: ids, never names): a brief belongs to the player its `primary_sleeper_id` maps to in
`analytics.player_id_map`; with no mapped Sleeper id, to the player its `primary_gsis_id` maps to there. If the Sleeper
id maps to one player and the brief's gsis id names another, it is a conflict and nobody sees it. A brief that maps to
nobody is stored, not shown, and counted (`/api/status` → `news.playerwire.unmapped`, conflicts also in
`conflicting`). Related players map the same way through `brief_players`.

## Environment

| Variable | Where | Meaning |
|---|---|---|
| `PLAYERWIRE_API_URL` | Mac `.env` | PlayerWire's read API (default `http://127.0.0.1:8790`) |
| `PLAYERWIRE_API_KEY` | Mac `.env` | its bearer key: `python3 -m pw client create --name league-lab --scopes read --db <PlayerWire's database>` prints it once |
| `PLAYERWIRE_WRITER_PASSWORD` | Mac `.env` | the password `make playerwire-schema` sets for `playerwire_writer` (hex, so it needs no URL escaping) |
| `PLAYERWIRE_HOSTED_URL` | Mac `.env` | the writer's DSN: `postgresql://playerwire_writer:<PLAYERWIRE_WRITER_PASSWORD>@<Neon direct host>/neondb?sslmode=require` |
| `LEAGUE_LAB_HOSTED_ADMIN_URL` | Mac `.env` (already there) | the Neon owner's DSN; `make playerwire-schema` uses it once |
| `LEAGUE_LAB_PLAYERWIRE` | Render (optional) | `off` hides PlayerWire's briefs (ESPN only). Default on; nothing to set |
| `LEAGUE_LAB_PLAYERWIRE_FIXTURES` | tests | a JSON file of rows (`api/tests/fixtures/playerwire/briefs.json`); in fixture mode PlayerWire is off without it |

Nothing changes on GitHub Actions or in `render.yaml`.

## Set up (on the Mac, from the repo root; after the branch is merged and you have said yes above)

PlayerWire's API must be running on the Mac in production mode on port 8790 (PlayerWire's own `docs/API.md`).

```bash
cd ~/PycharmProjects/league-lab
git pull && make sync

# 1. a password for the writer role, straight into .env (never printed)
echo "PLAYERWIRE_WRITER_PASSWORD=$(openssl rand -hex 24)" >> .env

# 2. the schema, the role and the read grants on Neon (uses LEAGUE_LAB_HOSTED_ADMIN_URL from .env; safe to re-run)
make playerwire-schema
#    -> playerwire schema ready: 3 tables, owner playerwire_writer
#    -> PLAYERWIRE_HOSTED_URL=postgresql://playerwire_writer:<PLAYERWIRE_WRITER_PASSWORD>@ep-….neon.tech/neondb?sslmode=require

# 3. a read key from PlayerWire (in the PlayerWire repo; it prints the key once)
( cd ~/PycharmProjects/playerwire && python3 -m pw client create --name league-lab --scopes read --db <PlayerWire's database> )
```

Add three lines to `.env` (replace the `<…>`: the password is the `PLAYERWIRE_WRITER_PASSWORD` value already in
`.env`, the host is the one step 2 printed):

```
PLAYERWIRE_API_URL=http://127.0.0.1:8790
PLAYERWIRE_API_KEY=pwk_<the key step 3 printed>
PLAYERWIRE_HOSTED_URL=postgresql://playerwire_writer:<PLAYERWIRE_WRITER_PASSWORD>@<host from step 2>/neondb?sslmode=require
```

```bash
# 4. look first (reads PlayerWire and the database, writes nothing), then the first real sync
make playerwire-sync DRY=1
make playerwire-sync           # one JSON line: {"bootstrapped": true, "bootstrap": {"briefs": N, ...}, ...}
make playerwire-status         # counts, the last sync, whether PlayerWire's API answers

# 5. every 15 minutes from now on
mkdir -p logs
sed "s|__ROOT__|$PWD|g" scripts/launchd/com.leaguelab.playerwire-sync.plist > ~/Library/LaunchAgents/com.leaguelab.playerwire-sync.plist
launchctl load ~/Library/LaunchAgents/com.leaguelab.playerwire-sync.plist
tail -n 5 logs/playerwire-sync.log
```

Then, once Render has deployed the branch: open `https://league-lab.onrender.com/api/status` while signed in and look
at `news.playerwire` (`rows`, `newest_published_at`, `unmapped`, `last_sync_at`); open a player PlayerWire has a
brief on and the card leads with it.

**Stop it**: `launchctl unload ~/Library/LaunchAgents/com.leaguelab.playerwire-sync.plist` (the briefs on Neon age
out of the 14-day window by themselves); to hide them at once, set `LEAGUE_LAB_PLAYERWIRE=off` on Render.
**Remove it entirely**: as the owner, `drop schema playerwire cascade; drop role playerwire_writer;`.

## Running it

* `logs/playerwire-sync.log`: one JSON line per run (`changes.upserts / deletes / stale`, `seconds`), errors with
  their HTTP code (`HTTP 401 missing_credentials` = the key; `unreachable` = PlayerWire's server is not running).
  A failure is also written to `playerwire.sync_state.last_error` and shows in `/api/status`; the next good run clears it.
* Exit codes: 0 done (or the lock was taken), 1 PlayerWire or the database failed, 2 configuration (a variable
  missing, connected as the wrong role).
* A 410 / 409 (the cursor expired after 30 days of sleep, PlayerWire's database was restored, its mode changed) is
  handled: the next run bootstraps again and marks any brief the new snapshot lacks as withdrawn
  (`deleted_reason = absent_from_snapshot`).

## Limitations

* **Freshness is the Mac's.** A brief reaches the card at most ~16 minutes after it is published (the 15-minute
  launchd cadence + the API's one-minute cache) — **only while the Mac is awake** and PlayerWire's server is running.
  A sleeping Mac runs once on wake and catches up; while it sleeps, the card keeps showing what was synced (and ESPN).
* **Withdrawals follow the same clock.** A withdrawn brief disappears from the card on the next sync after the
  withdrawal (+ up to a minute); until then the card can still show it. The withdrawn text is gone from Neon on that
  sync (the row keeps only ids and the tombstone).
* **Only published, hand-reviewed briefs appear**: PlayerWire's production mode serves nothing else (no drafts, no
  synthetic fixtures; today it has no real source yet, so the replica is empty until PlayerWire publishes real
  briefs — the card shows ESPN meanwhile).
* **PlayerWire first means first**: a 13-day-old brief leads a same-day ESPN headline (the order the plan asked for).
  The two feeds are not de-duplicated (the same story can appear from both).
* **Unmapped briefs are invisible** until `analytics.player_id_map` knows the player (rookies the nightly has not
  mapped, practice-squad players); `unmapped` in `/api/status` counts them.
* **No retention yet**: the replica keeps every brief and tombstone it ever received (≈ 5 MB per thousand). Add a
  prune once it matters for the 0.5 GB Neon cap.
* The card shows the newest item only (as N1); the other two are in the API's answer.
