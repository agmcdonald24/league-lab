"""The starter record (Wave I-W, IW-1 round 3): the site grades its own pick of who starts at quarterback.

The PO shipped S7 as a product decision (docs/METRICS.md § "Who starts, decided by the data", sq1.1) and asked that
S4 be recorded beside it and both graded every week. ``ops.starter_record`` keeps, per team-game:

* until kickoff, rewritten by every run (``write``): the schedule's listing (``listed_qb_id``), S4's pick, S7's pick,
  the quarterback the site projects (``projected_qb_id``: ``int_pn_team_game.starting_qb_id``) and which rule shipped
  (``shipped``: ``s7``, ``s4``, ``listing`` or ``override``). After kickoff the row is never rewritten: it holds the
  pick as the last run before kickoff left it (the nightly runs once a day, so "at kickoff" means the last refresh
  before it, the same freeze as ``ops.lineup_record`` and ``ops.context_record``);
* once the game is in (``grade``): the quarterback who led the team's dropbacks (``truth_qb_id``, the same leader
  ``mart_starter_check`` reads) and whether each pick was right (``listed_right``, ``s4_right``, ``s7_right``,
  ``projected_right``).

``mart_starter_check`` shows it per team; About says "Our projected starter was the game's quarterback in N of M
games since week 5" (nothing while M is 0). ``league-lab starter-record`` runs it (idempotent, safe every night).
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

FIRST_WEEK = 5   # the record starts with the first week the data's pick was shipped for (2026 week 5)

DDL = """
create table if not exists ops.starter_record (
    season           int         not null,
    week             int         not null,
    game_id          text        not null,
    team             text        not null,
    kickoff_at       timestamptz,
    listed_qb_id     text,
    s4_qb_id         text,
    s7_qb_id         text,
    projected_qb_id  text,
    shipped          text,
    recorded_at      timestamptz not null default now(),
    truth_qb_id      text,
    listed_right     boolean,
    s4_right         boolean,
    s7_right         boolean,
    projected_right  boolean,
    graded_at        timestamptz,
    primary key (season, week, team)
)
"""

# every unplayed game with a listing, rewritten while it has not kicked off; a row whose kickoff has passed is kept
WRITE_SQL = """
insert into ops.starter_record as r (season, week, game_id, team, kickoff_at, listed_qb_id, s4_qb_id, s7_qb_id,
                                     projected_qb_id, shipped, recorded_at)
select t.season, t.week, t.game_id, t.team, t.kickoff_at, t.listed_qb_id,
       to_jsonb(t) ->> 's4_qb_id', to_jsonb(t) ->> 's7_qb_id', t.starting_qb_id,
       case when to_jsonb(t) ->> 'starter_source' = 'override' then 'override'
            else coalesce(to_jsonb(t) ->> 'starter_rule', 'listing') end,
       now()
from intermediate.int_pn_team_game as t
where not t.is_played and t.listed_qb_id is not null and t.kickoff_at > %(now)s
  and (t.season, t.week) >= (%(season)s, %(first_week)s)
on conflict (season, week, team) do update
   set game_id = excluded.game_id, kickoff_at = excluded.kickoff_at, listed_qb_id = excluded.listed_qb_id,
       s4_qb_id = excluded.s4_qb_id, s7_qb_id = excluded.s7_qb_id, projected_qb_id = excluded.projected_qb_id,
       shipped = excluded.shipped, recorded_at = excluded.recorded_at
 where r.kickoff_at > %(now)s and r.truth_qb_id is null
"""

# the game's quarterback = the team's dropback leader (mart_starter_check's ``leaders``)
GRADE_SQL = """
with leaders as (
    select distinct on (p.season, p.week, p.team) p.season, p.week, p.team, p.gsis_id as leader_id
    from analytics.fct_player_game as p
    where p.season_type = 'REG' and coalesce(p.dropbacks, 0) > 0
    order by p.season, p.week, p.team, p.dropbacks desc, p.gsis_id
)
update ops.starter_record as r
   set truth_qb_id = l.leader_id,
       listed_right = (r.listed_qb_id = l.leader_id),
       s4_right = (coalesce(r.s4_qb_id, r.listed_qb_id) = l.leader_id),
       s7_right = (coalesce(r.s7_qb_id, r.listed_qb_id) = l.leader_id),
       projected_right = (r.projected_qb_id = l.leader_id),
       graded_at = now()
  from leaders as l
 where l.season = r.season and l.week = r.week and l.team = r.team and r.truth_qb_id is null
   and r.kickoff_at <= %(now)s
"""

SEASON_SQL = "select max(season) from intermediate.int_pn_team_game"


@dataclass
class Run:
    season: int | None
    written: int
    graded: int
    rows: int


def ensure_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def run(conn: psycopg.Connection, now: str = "now") -> Run:
    """Write the unplayed games' picks (until kickoff) and grade the games that are in. Idempotent."""
    ensure_table(conn)
    with conn.cursor() as cur:
        cur.execute("select %s::timestamptz", (now,))
        at = cur.fetchone()[0]
        cur.execute(SEASON_SQL)
        season = cur.fetchone()[0]
        if season is None:
            return Run(None, 0, 0, 0)
        cur.execute(WRITE_SQL, {"now": at, "season": season, "first_week": FIRST_WEEK})
        written = cur.rowcount
        cur.execute(GRADE_SQL, {"now": at})
        graded = cur.rowcount
        cur.execute("select count(*) from ops.starter_record")
        rows = cur.fetchone()[0]
    conn.commit()
    return Run(season, written, graded, rows)


def tally(cur: psycopg.Cursor) -> tuple[int, int] | None:
    """(right, graded) for the projected starter since week 5 of the newest season in the record; None when the table
    is not there yet (the deploy lands before the refresh)."""
    cur.execute("select to_regclass('ops.starter_record') is not null")
    if not cur.fetchone()[0]:
        return None
    cur.execute("""select count(*) filter (where projected_right), count(*)
                   from ops.starter_record
                   where truth_qb_id is not null and week >= %s
                     and season = (select max(season) from ops.starter_record)""", (FIRST_WEEK,))
    n, m = cur.fetchone()
    return int(n or 0), int(m or 0)


def sentence(n: int, m: int) -> str | None:
    """About's line; nothing while no game since week 5 is graded."""
    if not m:
        return None
    return f"Our projected starter was the game's quarterback in {n} of {m} games since week {FIRST_WEEK}."
