# MyFantasyLeague: what we read, how often, and who to contact (Wave I-0, I0-B, 2026-10-03)

**What League Lab does.** Reads a MyFantasyLeague league's public export (`https://api.myfantasyleague.com/<year>/export
?TYPE=…&L=<league>&JSON=1`, followed to the league's own `www4N.` host): the league settings, scoring rules, rosters,
schedule, standings, the week's live scoring and last week's results, the player list (`DETAILS=1`), the injury
report and (Wave I-L, IL-2) the transactions export, week by week (`TYPE=transactions&W=<week>&TRANS_TYPE=*`; for MFL's current week the next week's file too — MFL files a move made once a week's games have begun there). Read-only: no login, no API key, no writes, no lineup changes. Code: `src/league_lab/mfl_client.py`.

**Who can be read.** A league whose commissioner allows outside reads. MFL answers anything else with an `error` body;
League Lab then says: "MyFantasyLeague would not share this league: it may be private or the link may be wrong. Ask
the commissioner to allow API access". (MFL's own wording for the setting was not verified from here: the
commissioner looks in the league's setup for the API / privacy option.)

**How much we call.** One token bucket of **60 calls a minute** per process (`LEAGUE_LAB_MFL_PER_MIN`), stricter than
Sleeper's; caches by kind: league and rules a day, rosters and standings 10 minutes, schedule and live scoring 5
minutes, weekly results 10 minutes, players a day, injuries an hour, this week's transactions 10 minutes and a past
week's a day. An HTTP 429, or an `error` body that asks us
to slow down, stops all MFL calls for a minute (the last answer is served when there is one). A league opened once
costs about nine calls, then nothing for five to ten minutes; the League screen adds one transactions call per week of
the season so far the first time (a past week then holds a day).

**Who we are.** Every call carries `User-Agent: league-lab/0.1 (beta; contact in docs/MFL_TERMS.md)`. Contact: the
project owner (put the beta's public contact address here when it has one). The beta is free and charges nobody.

**Terms.** MyFantasyLeague publishes its export API for third-party tools; their developer terms (rate, attribution,
commercial use) were not read from this sandbox. Before anything is charged for, read them and record the clause
here, as `docs/SLEEPER_TERMS.md` does for Sleeper.

**The id table.** MFL ids become Sleeper ids through nflverse / dynastyprocess `db_playerids.csv`
(`https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv`, downloaded at most once a day
into `LEAGUE_LAB_CACHE_DIR`; `src/league_lab/player_ids.py`).
