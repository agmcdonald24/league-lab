# Hosting League Lab for the league (beta)

Goal: a link leaguemates can open. Cost: **$0** on free tiers. Your Mac stays the pipeline (it
already refreshes nightly); after each refresh it publishes the marts to a hosted Postgres, and
Streamlit Community Cloud serves the explorer from GitHub against that database.

```
Mac: ingest → dbt build → backup → sync_to_hosted.sh ──► hosted Postgres (marts only, ~400 MB)
                                                                 ▲
GitHub repo ──► Streamlit Community Cloud (app/Home.py) ─────────┘  read-only role
```

What leaves your machine: the analytics marts the pages and packs read (the script derives the list
from the code — 35 relations, ~290 MB), the seeds and the `ops` schema — never `raw`, `staging`,
`intermediate`, the play-level tables, `.env` or the archive.

## 1. Hosted Postgres (15 minutes)

Either provider works; both have a free tier that fits (~290 MB today, +≈30 MB per season; Neon's cap is 0.5 GB).

**Neon** (recommended: cheap, Postgres 17, no sleeping issues for a read-only workload)
1. neon.tech → sign up → New project → name `league-lab`, region closest to you, Postgres 17.
2. Dashboard → *Connection string* → choose the **owner** role (`neondb_owner`) → copy the URL.
   It looks like `postgresql://neondb_owner:...@ep-...-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require`.
   Use the **direct** (non-pooler) host for the sync; either for the app.

**Supabase** (alternative): New project → Project settings → Database → connection string (URI,
"session" mode, the `postgres` role). Same steps below.

Then in `.env` on the Mac:

```
LEAGUE_LAB_HOSTED_ADMIN_URL=postgresql://neondb_owner:...@ep-....neon.tech/neondb?sslmode=require
LEAGUE_LAB_HOSTED_APP_PASSWORD=<a long random password for the read-only app role>
```

Publish:

```bash
make sync-hosted        # ~1-3 minutes: dumps the marts the pages read, creates the read-only role, restores
```

Every `make refresh` (and the nightly launchd job) now ends with the same sync. If the sync fails
the local data is untouched; run `make sync-hosted` again.

The app's connection string is the same host and database with the **app** role:

```
postgresql://league_lab_app:<LEAGUE_LAB_HOSTED_APP_PASSWORD>@<host>/<db>?sslmode=require
```

## 2. GitHub repository (10 minutes)

Streamlit Community Cloud deploys from GitHub. The repo holds code and config only; `.gitignore`
already excludes `.env`, `data/`, `backups/`, `logs/`, `reports/`, `.state/` and every secrets file.

```bash
cd ~/PycharmProjects/league-lab
git init && git add -A && git commit -m "League Lab beta"
gh repo create league-lab --private --source=. --push       # or create it on github.com and push
```

Check before pushing: `git status --ignored | grep -E "\.env$|data/"` must list them as ignored.

## 3. Streamlit Community Cloud (10 minutes)

1. share.streamlit.io → sign in with GitHub → **New app**.
2. Repository `you/league-lab`, branch `main`, **main file path `app/Home.py`**.
3. *Advanced settings* → Python 3.13 → **Secrets** (TOML):

   ```toml
   LEAGUE_LAB_APP_DB_URL = "postgresql://league_lab_app:<password>@<host>/<db>?sslmode=require"
   LEAGUE_LAB_APP_PASSWORD = "the-beta-password-you-give-people"     # optional gate; remove for open access
   LEAGUE_LAB_FEEDBACK_URL = "https://forms.gle/..."                  # optional; shows a sidebar button
   ```

4. Deploy. Dependencies come from `app/requirements.txt` (the explorer's runtime only; Community
   Cloud uses the entrypoint directory's file before the repo's `uv.lock`). First build ≈ 2 minutes.
5. Settings → *Sharing*: **Public** (anyone with the link; the password gate keeps it to invitees)
   or **Private** (viewers must sign in with an email you list — up to a handful on the free tier).

The URL is `https://<app-name>.streamlit.app`; you can rename it in the app settings.

## 3b. Adding another Sleeper league

```
LEAGUE_LAB_SLEEPER_LEAGUE_ID=1389709692405551104,<other league id>     # in .env; first id = reference scoring
make ingest-sleeper && make build && make sync-hosted
```

The league id is the number in the Sleeper URL (`sleeper.com/leagues/<id>/...`). Its whole chain of
previous seasons is fetched too. Leaguemates of the second league pick it in the sidebar; the link
`?league=<id>&team=<roster>` opens straight on their team. League pages use that league's scoring;
NFL pages use the reference league's, and the sidebar lists any scoring differences.

## 4. What to expect

* **Freshness** = your Mac's last refresh + sync (the banner on every page says when). If the Mac
  is asleep at 08:00 the launchd job runs when it wakes.
* **Cold start**: Community Cloud sleeps an app after a few days without visitors; the first
  visitor waits ~30 s. Neon free tier suspends compute after 5 minutes idle; the first query
  waits ~1 s.
* **Limits**: 1 GB RAM on Community Cloud is plenty (pages read marts, never raw). Neon free:
  0.5 GB storage, 190 compute-hours/month — a read-only explorer for a 10-team league uses a
  fraction of that. If the marts outgrow 0.5 GB (several seasons from now), Neon's paid tier is
  ~$19/month; before that, the play-level tables are already excluded and `fct_player_game` can be
  slimmed.
* **A refresh in progress**: the sync drops the previous copy and restores the new one (free
  tiers cannot hold two copies at once — Neon caps a project at 0.5 GB), so for the length of the
  restore (a minute or two) pages say "marts not built on this machine yet" instead of failing.
  The nightly job runs at 08:00, before anyone is looking. If a restore ever fails midway, run
  `make sync-hosted` again; local data is never touched.
* **Security model**: the hosted role is read-only (`default_transaction_read_only`), sees only the
  three published schemas and has a 30 s statement timeout. The beta password is a closed door for
  a link, not authentication; use Community Cloud's private sharing if that matters.

## 5. Moving the pipeline off the Mac (later, plan I-01)

A GitHub Actions workflow can run the whole nightly job (ingest → build → sync) on a free runner
with an ephemeral Postgres, so the Mac is no longer infrastructure. Not needed for the beta.

## Licences to keep in mind when sharing

* nflverse data: free to use with attribution (kept on Home → Data & attribution).
* FTN Data charting via nflverse: **CC BY-SA 4.0** — first-read shares and other charting-derived
  numbers are adaptations and carry the same licence and attribution (they do).
* Sleeper: public, read-only API; league data belongs to the league.
* Do not redistribute the raw files; the hosted copy holds only derived marts.
