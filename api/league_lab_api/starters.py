"""IP-1 (Wave I-P, fix round 2): "Starter unclear" -- the flag, the data half (the Rankings screen reads it; IP-2).

A team's quarterbacks are both flagged for week W when the schedule's listed starter for W took no dropback in the
team's newest played game of the season before W while another quarterback led that game's dropbacks. It is a label,
never a change to a number: the projection keeps assuming the listing (its "is he the starter?" input reads the
schedule), so the listed quarterback is projected as the starter and the other as his backup.

What it measured (docs/METRICS.md § "st1.1" -> "Starter unclear", played team-weeks 2022 - 2026 week 4, the same trigger
on the same data): about two team-weeks a week; it marks 32 of the 49 listings that turned out stale (the listed QB
did not drop back in the game itself) and 137 of its flags were not stale -- so the words say "unclear", never "wrong".

Reads only ``analytics`` relations the API's read-only role reads on the hosted copy: ``dim_game`` (the schedule's
listed starters ``home_qb_id`` / ``away_qb_id``; a game is played once a team has a box score) and ``fct_player_game``
(each player's ``dropbacks`` per game: pass attempts, sacks and scrambles), ``dim_player`` (names). As of the week: only
games with ``week < W`` count; W's own game never does. No new relation.

IQ-2 (Wave I-Q, 2026-10-07; docs/METRICS.md § "Who starts"): where ``analytics.mart_starter_check`` is built (one row per
team for its next unplayed game: the listing, the depth chart, the last game's dropback leader, the injury report, the
hand-kept override in force, what the projection assumes), two things change, and without it (a deploy before the
nightly) nothing does:

* ``unclear`` reads the trigger the rule kept, U1: the listing is not the depth chart's first available quarterback
  (``listing_disputed``; 2025 - 2026 week 4: it catches 12 of 12 stale listings with 27 flags, su1.0 7 with 42). A team
  the override list corrects is never "unclear".
* ``corrected`` names the quarterbacks of a team whose starter a hand-kept row set (seed ``starter_overrides``): the
  projection treats him as the starter, and both his row and the listed quarterback's carry one sentence saying so.
"""

from __future__ import annotations

import logging

import pandas as pd
from league_lab import memo

from .db import missing_relations, query

log = logging.getLogger(__name__)

RELATIONS = ("dim_game", "fct_player_game", "dim_player")
SEASONS = (2016, 2100)
WEEKS = (1, 22)
_cache = memo.region("starters", ttl=600.0, max_entries=32)   # two entries per (season, week) (IQ-2: + corrected): a few KB

# the team's listed starter for the week, and the newest game before it in which the team has a box score
LISTING_SQL = """
with listing as (
    select t.team, nullif(t.qb, '') as listed_id
    from analytics.dim_game as g
    cross join lateral (values (g.home_team, g.home_qb_id), (g.away_team, g.away_qb_id)) as t(team, qb)
    where g.season = %s and g.week = %s and g.season_type = 'REG'
),
last_game as (
    select distinct on (t.team) t.team, g.game_id, g.week
    from analytics.dim_game as g
    cross join lateral (values (g.home_team), (g.away_team)) as t(team)
    where g.season = %s and g.week < %s and g.season_type = 'REG'
      and exists (select 1 from analytics.fct_player_game as p
                  where p.game_id = g.game_id and p.team = t.team and p.season_type = 'REG' and p.played)
    order by t.team, g.week desc
)
select l.team, l.listed_id, lg.game_id, lg.week as last_week
from listing as l
join last_game as lg using (team)
where l.listed_id is not null"""

DROPBACKS_SQL = """select p.game_id, p.team, p.gsis_id, p.dropbacks::float8 as dropbacks
                   from analytics.fct_player_game as p
                   where p.game_id = any(%s) and p.season_type = 'REG' and coalesce(p.dropbacks, 0) > 0"""

NAMES_SQL = "select gsis_id, player_name from analytics.dim_player where gsis_id = any(%s)"

# Sleeper's team codes name the teams (league_lab.platforms.NFL_TEAMS); the schedule writes the Rams "LA"
TEAM_NAMES = {"ARI": "Arizona", "ATL": "Atlanta", "BAL": "Baltimore", "BUF": "Buffalo", "CAR": "Carolina", "CHI": "Chicago",
              "CIN": "Cincinnati", "CLE": "Cleveland", "DAL": "Dallas", "DEN": "Denver", "DET": "Detroit", "GB": "Green Bay",
              "HOU": "Houston", "IND": "Indianapolis", "JAX": "Jacksonville", "KC": "Kansas City", "LAC": "the Chargers",
              "LA": "the Rams", "LAR": "the Rams", "LV": "Las Vegas", "MIA": "Miami", "MIN": "Minnesota", "NE": "New England",
              "NO": "New Orleans", "NYG": "the Giants", "NYJ": "the Jets", "PHI": "Philadelphia", "PIT": "Pittsburgh",
              "SEA": "Seattle", "SF": "San Francisco", "TB": "Tampa Bay", "TEN": "Tennessee", "WAS": "Washington"}


def last_name(name: str) -> str:
    parts = [p for p in str(name).split() if p.rstrip(".") not in {"Jr", "Sr", "II", "III", "IV"}]
    return parts[-1] if parts else str(name)


def words(team: str, listed: str, played: str, last_week: int) -> str:
    """The one sentence a screen prints as it is (docs/WORDS.md § "Starter unclear")."""
    who = TEAM_NAMES.get(team, team)
    lead = who[0].upper() + who[1:]
    verb = "list" if who.startswith("the ") else "lists"          # "the Rams list", "Seattle lists"
    return (f"Starter unclear: {lead} {verb} {listed} as the starter, but he did not drop back once in week {last_week}; "
            f"{played} took most of the dropbacks. Our projections assume the listing: {last_name(listed)} as the starter, "
            f"{last_name(played)} as his backup.")


def flags_from(listing: pd.DataFrame, dropbacks: pd.DataFrame, names: dict[str, str]) -> dict[str, dict]:
    """The pure part: ``listing`` (team, listed_id, game_id, last_week: the team's newest played game before the week)
    and ``dropbacks`` (game_id, team, gsis_id, dropbacks of that game, > 0) -> the flags, both quarterbacks of a team."""
    out: dict[str, dict] = {}
    for r in listing.itertuples():
        d = dropbacks[(dropbacks["game_id"] == r.game_id) & (dropbacks["team"] == r.team)]
        if d.empty or r.listed_id in set(d["gsis_id"]):
            continue                                       # no box score to read, or the listed QB dropped back
        lead = d.sort_values(["dropbacks", "gsis_id"], ascending=[False, True]).iloc[0]["gsis_id"]
        listed, played = names.get(r.listed_id, r.listed_id), names.get(lead, lead)
        sentence = words(r.team, listed, played, int(r.last_week))
        base = {"team": r.team, "listed": listed, "played": played, "words": sentence, "last_week": int(r.last_week)}
        out[r.listed_id] = {**base, "role": "listed"}
        out[lead] = {**base, "role": "played"}
    return out


def unclear(season: int, week: int) -> dict[str, dict]:
    """gsis_id -> {"team", "listed", "played", "role": "listed" | "played", "words", "last_week"} for both quarterbacks of
    every team whose listed starter for ``week`` took no dropback in the team's newest played game while another
    quarterback led its dropbacks. As of the week: only games before ``week``. Never raises: a missing relation, a
    week outside 1-22 or a failed read gives {}. Cached per (season, week) in the ``starters`` memo region."""
    try:
        season, week = int(season), int(week)
    except (TypeError, ValueError):
        return {}
    if not (SEASONS[0] <= season <= SEASONS[1] and WEEKS[0] <= week <= WEEKS[1]):
        return {}
    key = (season, week)
    hit = _cache.get(key)
    if hit is not None:
        return dict(hit)
    chk = check(season, week)                    # ---- IQ-2: U1 and the override list, where the mart is built
    if chk is not None:
        out = disputed_from(chk)
        _cache.put(key, out)
        return dict(out)
    try:
        if missing_relations(RELATIONS):
            return {}
        listing = query(LISTING_SQL, (season, week, season, week))
        if listing.empty:
            out: dict[str, dict] = {}
        else:
            dropbacks = query(DROPBACKS_SQL, (sorted(listing["game_id"].unique().tolist()),))
            ids = sorted(set(listing["listed_id"]) | set(dropbacks["gsis_id"] if not dropbacks.empty else []))
            names = dict(query(NAMES_SQL, (ids,)).itertuples(index=False, name=None)) if ids else {}
            if dropbacks.empty:
                dropbacks = pd.DataFrame(columns=["game_id", "team", "gsis_id", "dropbacks"])
            out = flags_from(listing, dropbacks, names)
    except Exception:  # noqa: BLE001 - a label must never cost a screen
        log.warning("starters.unclear(%s, %s) failed: no flags", season, week, exc_info=True)
        return {}
    _cache.put(key, out)
    return dict(out)


# ---- IQ-2 (Wave I-Q, 2026-10-07): who starts -- the override list and the depth chart (docs/METRICS.md § "Who starts")
CHECK = "mart_starter_check"
CHECK_SQL = """select team, week, listed_qb_id, listed_name, depth_available_qb_id, depth_available_name, last_week,
                      override_qb_id, override_name, override_added_on, override_led_since_week, projected_qb_id,
                      starter_source, listing_disputed
               from analytics.mart_starter_check where season = %s and week = %s"""
CHECK_COLS = ("team", "week", "listed_qb_id", "listed_name", "depth_available_qb_id", "depth_available_name", "last_week",
              "override_qb_id", "override_name", "override_added_on", "override_led_since_week", "projected_qb_id",
              "starter_source", "listing_disputed")


def _str(v) -> str | None:
    return v if isinstance(v, str) and v.strip() else None


def _int(v) -> int | None:
    try:
        return None if v is None or pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def check(season: int, week: int) -> pd.DataFrame | None:
    """The mart's rows for (season, week); None when it is not built, has no row for the week, or the read fails --
    the callers then do exactly what they did before IQ-2. Not cached here (its callers are)."""
    try:
        season, week = int(season), int(week)
    except (TypeError, ValueError):
        return None
    if not (SEASONS[0] <= season <= SEASONS[1] and WEEKS[0] <= week <= WEEKS[1]):
        return None
    try:
        if missing_relations((CHECK,)):
            return None
        df = query(CHECK_SQL, (season, week))
    except Exception:  # noqa: BLE001 - a label must never cost a screen
        log.warning("starters.check(%s, %s) failed: the screens keep su1.0", season, week, exc_info=True)
        return None
    if df is None or df.empty or not set(CHECK_COLS) <= set(df.columns):
        return None
    return df


def team_name(team: str) -> str:
    who = TEAM_NAMES.get(team, team)
    return who[0].upper() + who[1:]


def disputed_words(team: str, listed: str, depth: str) -> str:
    """U1's sentence (docs/WORDS.md § "Starter unclear")."""
    lead = team_name(team)
    verb = "list" if lead.startswith("The ") else "lists"
    return (f"Starter unclear: {lead} {verb} {listed} as the starter, but the depth chart puts {depth} first. Our "
            f"projections assume the listing: {last_name(listed)} as the starter, {last_name(depth)} as his backup.")


def disputed_from(chk: pd.DataFrame) -> dict[str, dict]:
    """The pure part of U1: both quarterbacks of a team whose listing is not the depth chart's first available
    quarterback, unless a hand-kept row sets the team's starter (``starter_source`` 'override')."""
    out: dict[str, dict] = {}
    for r in chk.to_dict("records"):
        lid, did = _str(r.get("listed_qb_id")), _str(r.get("depth_available_qb_id"))
        flag = r.get("listing_disputed")
        if flag is None or pd.isna(flag) or not bool(flag) or r.get("starter_source") == "override":
            continue
        if lid is None or did is None or lid == did:
            continue
        listed, depth = _str(r.get("listed_name")) or lid, _str(r.get("depth_available_name")) or did
        base = {"team": r["team"], "listed": listed, "played": depth, "last_week": _int(r.get("last_week")),
                "words": disputed_words(str(r["team"]), listed, depth)}
        out[lid] = {**base, "role": "listed"}
        out[did] = {**base, "role": "depth"}
    return out


def day_month(d) -> str | None:
    """2026-10-07 -> "7 Oct" (the site's short date)."""
    try:
        t = pd.Timestamp(d)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(t) else f"{t.day} {t.strftime('%b')}"


def corrected_words(team: str, listed: str | None, qb: str, since: int | None, last_week: int | None, added_on) -> str:
    """The corrected quarterback's sentence (docs/WORDS.md § "Starter set by hand")."""
    lead = team_name(team)
    own = lead + ("'" if lead.endswith("s") else "'s")
    head = f"{own} listing says {listed}" if listed else f"{own} schedule names no starter yet"
    if since is not None and last_week is not None and since < last_week:
        why = f"{qb} has led the team's dropbacks since week {since}, so we project {last_name(qb)} as the starter"
    elif since is not None:
        why = f"{qb} led the team's dropbacks in week {since}, so we project {last_name(qb)} as the starter"
    else:
        why = f"we project {qb} as the starter"
    when = day_month(added_on)
    return f"{head}; {why}." + (f" Set by hand on {when}." if when else " Set by hand.")


def corrected_from(chk: pd.DataFrame) -> dict[str, dict]:
    """The pure part: gsis -> {"team", "listed", "set", "role": "set" | "listed", "words", "added_on", "since_week"} for
    the quarterback a hand-kept row sets as the starter and the listed one, where the two differ."""
    out: dict[str, dict] = {}
    for r in chk.to_dict("records"):
        oid, lid = _str(r.get("override_qb_id")), _str(r.get("listed_qb_id"))
        if r.get("starter_source") != "override" or oid is None or oid == lid:
            continue
        qb, listed = _str(r.get("override_name")) or oid, (_str(r.get("listed_name")) or lid) if lid else None
        since, last = _int(r.get("override_led_since_week")), _int(r.get("last_week"))
        added = r.get("override_added_on")
        base = {"team": r["team"], "listed": listed, "set": qb, "since_week": since,
                "added_on": None if added is None or pd.isna(added) else str(pd.Timestamp(added).date()),
                "words": corrected_words(str(r["team"]), listed, qb, since, last, added)}
        out[oid] = {**base, "role": "set"}
        if lid:
            out[lid] = {**base, "role": "listed"}
    return out


def corrected(season: int, week: int) -> dict[str, dict]:
    """gsis_id -> the corrected starter's sentence (see ``corrected_from``) for ``week``; {} without the mart (a deploy
    before the nightly), for a week it has no row for, or on any failure. Cached per (season, week) in ``starters``."""
    try:
        season, week = int(season), int(week)
    except (TypeError, ValueError):
        return {}
    if not (SEASONS[0] <= season <= SEASONS[1] and WEEKS[0] <= week <= WEEKS[1]):
        return {}
    key = ("corrected", season, week)
    hit = _cache.get(key)
    if hit is not None:
        return dict(hit)
    chk = check(season, week)
    try:
        out = {} if chk is None else corrected_from(chk)
    except Exception:  # noqa: BLE001 - a label must never cost a screen
        log.warning("starters.corrected(%s, %s) failed: no sentence", season, week, exc_info=True)
        return {}
    _cache.put(key, out)
    return dict(out)
# ---- end IQ-2
