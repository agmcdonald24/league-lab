"""The research, on demand (plan G1, Iteration 15, Wave G): Trends, Matchups (defense vs position, cornerbacks),
Players, Receivers, two players side by side and a player's game log — for ANY Sleeper league.

Rules (the brief's contract):
* a route returns the mart's rows with the mart's column names (`docs/DATA_MODEL.md`), plus `headshot_url`, `team`
  and `position` on every player row (`dim_player`), plus `rostered_by_roster_id` / `rostered_by_team` in this league
  (a house league: `mart_player_availability`; any other league: Sleeper's rosters through `player_id_map`);
* points in the league's scoring wherever a point appears: a house league reads its league marts
  (`fct_player_game_league`, `mart_league_player_season`, `mart_player_week_projections`), any other league is priced
  on request from the NFL-wide stat columns (`league_lab.research.price_games` = `scoring.compute_points` with the
  position; equal to the league marts to the cent for a house league: api/tests/test_research.py);
* the NFL research marts are scored in the reference league's scoring: such a field is named `<mart column>_ref`, and
  the league's own number sits next to it under the mart's name where it can be priced (README § Research (G1) lists
  the fields that cannot);
* the "How to read this" words of each Streamlit page travel in `howto` (markdown bullets), so the screen reuses them;
  `app/lib/matchups.py` (pure: the cornerback and comparison sentences) and `app/lib/signals.py` (the role alerts)
  write the sentences, as on the pages.

`source=sleeper` serves a house league through the on-demand path (the parity tests use it).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd
from league_lab import anyleague as A
from league_lab import memo as budget  # ---- INF-2: the memory budget
from league_lab import research as R

from . import availability
from . import stats as ST  # ---- II-3: the Stats Explorer
from .applib import PKG as APPLIB_PKG
from .applib import cards, links, signals
from .applib import ros as ROS
from .db import missing_relations, query
from .myweek import NotFound, known_league, league_row
from .ondemand import SleeperDown, ros_card
from .settings import APP_LIB


class BadRequest(ValueError):
    """A parameter the route cannot use (400, {"error": "<plain words>"})."""


def _load_matchups():
    """app/lib/matchups.py (pure: pandas + math) unchanged, as a member of applib's private package — so its own
    relative imports (``from .cards import rank_words``, the PO's I-F verdict words) resolve to the modules applib
    loaded (``cards``), exactly as ``lib.matchups`` does on the console."""
    name = f"{APPLIB_PKG}.matchups"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, APP_LIB / "matchups.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    sys.modules[APPLIB_PKG].matchups = mod
    return mod


M = _load_matchups()
SKILL = ("QB", "RB", "WR", "TE")
POSITIONS = ("QB", "RB", "WR", "TE", "K")
MAX_LIMIT = 500
PRICED_TTL_S = 600


def _limit(limit: int | None, default: int = 50) -> int:
    try:
        n = int(limit if limit is not None else default)
    except (TypeError, ValueError) as exc:
        raise BadRequest("limit must be a number") from exc
    return max(1, min(n, MAX_LIMIT))


def _positions(position: str | None, allowed=POSITIONS, default=None) -> list[str]:
    p = (position or "ALL").upper()
    if p == "ALL":
        return list(default or allowed)
    out = [x.strip() for x in p.split(",") if x.strip()]
    bad = [x for x in out if x not in allowed]
    if bad:
        raise NotFound(f"no position {', '.join(bad)} ({', '.join(allowed)} or ALL)")
    return out


# counts, ranks, ids and weeks that a merge turned into floats (39.0) go back to whole numbers
INT_COL = re.compile(r"(^|_)(rank|games|week|season|roster_id|n|count|targets|receptions|carries|attempts|completions|"
                     r"snaps|tds|yards|made|att|long|first_season|last_season)($|_)|^n_|_rank$|^rank_|^games")


def _records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    df = df.copy()
    for c in df.columns:
        if df[c].dtype.kind == "f" and INT_COL.search(str(c)) and "share" not in c and "per_" not in c and "_pg" not in c:
            v = df[c].dropna()
            if not v.empty and (v == v.round()).all():
                df[c] = df[c].astype("Int64")
    return df.to_dict("records")


def _grouped(df: pd.DataFrame, key: str) -> dict[str, list[dict]]:
    """Rows of `df` as records grouped by `key` (the key dropped), converted once."""
    out: dict[str, list[dict]] = {}
    if df is None or df.empty:
        return out
    for r in _records(df):
        out.setdefault(r.pop(key), []).append(r)
    return out


# ------------------------------------------------------------------------------ the league
@dataclass
class Ctx:
    """One league as the research routes need it: a house league (the database scores it) or any Sleeper league."""
    league_id: str
    season: int
    league_name: str
    house: bool
    scoring: dict
    slots: list[str]
    week: int | None
    rosters: list = field(default_factory=list)
    names: dict = field(default_factory=dict)
    _rostered: pd.DataFrame | None = None

    @property
    def source(self) -> str:
        return "database" if self.house else "sleeper"

    def meta(self) -> dict:
        out = {"league_id": self.league_id, "league_name": self.league_name, "season": self.season,
               "league_season": self.season, "week": self.week, "source": self.source,
               "points_source": "league marts" if self.house else "priced on request (scoring.compute_points)"}
        if not self.house:
            ref, exact = expected_ref(self)
            out["expected_points_reference"] = ref
            out["expected_points_exact"] = exact
        return out


def context(league_id: str, source: str | None = None) -> Ctx:
    if source != "sleeper" and known_league(league_id):
        lrow = league_row(league_id)
        ls = query("select scoring_settings, roster_positions from analytics.dim_league_season where league_id = %s",
                   (league_id,)).iloc[0]
        scoring = {k: float(v) for k, v in (ls["scoring_settings"] or {}).items() if v is not None}
        season = int(lrow["season"])
        return Ctx(league_id, season, str(lrow["league_name"]), True, scoring, [str(s) for s in ls["roster_positions"] or []],
                   cards.decision_week(season))
    try:
        lid = A.check_id(league_id)
        cl = A.sleeper()
        lg = cl.league(lid)
        rosters, users = cl.rosters(lid), cl.users(lid)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc)) from exc
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    scoring, slots = A.league_scoring(lg)
    season = int(lg["season"])
    return Ctx(lid, season, str(lg.get("name") or f"League {lid}"), False, scoring, slots, cards.decision_week(season),
               rosters, A.team_names(rosters, users))


def rostered(ctx: Ctx) -> pd.DataFrame:
    """gsis_id -> rostered_by_roster_id, rostered_by_team, is_free_agent (this league's rosters now)."""
    if ctx._rostered is not None:
        return ctx._rostered
    if ctx.house:
        df = query("""select gsis_id, rostered_by_roster_id, rostered_by_team, coalesce(is_free_agent, false) as is_free_agent
                      from analytics.mart_player_availability where league_id = %s and gsis_id is not null""", (ctx.league_id,))
    else:
        sids = sorted({str(p) for r in ctx.rosters for p in (r.get("players") or [])})
        idm = query("select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)", (sids,))
        gsis_of = dict(zip(idm["sleeper_id"], idm["gsis_id"], strict=False)) if not idm.empty else {}
        rows = []
        for r in ctx.rosters:
            rid = int(r["roster_id"])
            for p in r.get("players") or []:
                g = gsis_of.get(str(p))
                if g:
                    rows.append({"gsis_id": g, "rostered_by_roster_id": rid,
                                 "rostered_by_team": ctx.names.get(rid, {}).get("team_name"), "is_free_agent": False})
        df = pd.DataFrame(rows, columns=["gsis_id", "rostered_by_roster_id", "rostered_by_team", "is_free_agent"])
    df = df.drop_duplicates("gsis_id")
    ctx._rostered = df
    return df


DIM_SQL = """select gsis_id, player_name as dim_player_name, position as dim_position, latest_team as dim_team, headshot_url
             from analytics.dim_player where gsis_id = any(%s)"""


def decorate(df: pd.DataFrame, ctx: Ctx, id_col: str = "gsis_id") -> pd.DataFrame:
    """+ headshot_url, team, position (dim_player; the mart's own team / position when it has one) and whose team he is
    on in this league (rostered_by_roster_id, rostered_by_team; null = nobody's)."""
    if df.empty:
        for c in ("headshot_url", "team", "position", "rostered_by_roster_id", "rostered_by_team"):
            if c not in df:
                df[c] = pd.Series(dtype=object)
        return df
    ids = sorted({str(x) for x in df[id_col].dropna()})
    dim = query(DIM_SQL, (ids,))
    out = df.merge(dim, left_on=id_col, right_on="gsis_id", how="left", suffixes=("", "_dim"))
    if id_col != "gsis_id" and "gsis_id_dim" in out:
        out = out.drop(columns=["gsis_id_dim"])
    for col, src in (("team", "dim_team"), ("position", "dim_position"), ("player_name", "dim_player_name")):
        out[col] = out[col].where(out[col].notna(), out[src]) if col in out else out[src]
    out = out.drop(columns=[c for c in ("dim_team", "dim_position", "dim_player_name") if c in out])
    ro = rostered(ctx)[["gsis_id", "rostered_by_roster_id", "rostered_by_team"]]
    out = out.drop(columns=[c for c in ("rostered_by_roster_id", "rostered_by_team") if c in out])
    out = out.merge(ro.rename(columns={"gsis_id": "_rid"}), left_on=id_col, right_on="_rid", how="left").drop(columns="_rid")
    out["rostered_by_roster_id"] = out["rostered_by_roster_id"].astype("Int64")
    return out


# ------------------------------------------------------------------------------ points in the league's scoring
GAME_KEYS = ("p.gsis_id, p.game_id, p.season, p.season_type, p.week, p.team, p.opponent_team, p.position, p.player_name, "
             "p.played, p.has_stat_row")
HOUSE_GAMES_SQL = f"""select {GAME_KEYS}, l.points, l.points_expected, coalesce(l.expected_known, false) as expected_known
    from analytics.fct_player_game p
    left join analytics.fct_player_game_league l on l.league_id = %s and l.gsis_id = p.gsis_id and l.game_id = p.game_id
    where p.season = %s {{where}}"""
PRICE_GAMES_SQL = f"""select {GAME_KEYS}, {", ".join("p." + c for c in R.PRICE_COLUMNS)},
           {", ".join("e." + c for c in R.EXPECTED_COLUMNS.values())},
           r.points_expected as ref_expected, coalesce(r.expected_known, false) as expected_known
    from analytics.fct_player_game p
    left join analytics.mart_player_expected_points e on e.gsis_id = p.gsis_id and e.game_id = p.game_id
    left join analytics.fct_player_game_league r on r.league_id = %s and r.gsis_id = p.gsis_id and r.game_id = p.game_id
    where p.season = %s {{where}}"""
GAMES_OUT = ["gsis_id", "game_id", "season", "season_type", "week", "team", "opponent_team", "position", "player_name",
             "played", "has_stat_row", "points", "points_expected", "expected_known"]
_priced = budget.region("research_priced", ttl=PRICED_TTL_S)   # INF-2: in the memory budget (was cleared past 50)


def house_scorings() -> dict[str, dict]:
    df = query("select league_id, scoring_settings from analytics.dim_league_season where is_current_season")
    return {str(r.league_id): {k: float(v) for k, v in (r.scoring_settings or {}).items() if v is not None}
            for r in df.itertuples()}


def expected_ref(ctx: Ctx) -> tuple[str | None, bool]:
    return R.expected_reference(ctx.scoring, house_scorings())


def league_games(ctx: Ctx, season: int, gsis: list[str] | None = None) -> pd.DataFrame:
    """Every NFL game row of `season` (fct_player_game, regular season and playoffs) with `points` and
    `points_expected` in this league's scoring: the league mart for a house league, priced on request otherwise
    (a whole season is cached 10 minutes per scoring; one player's games are priced on the spot)."""
    where, params = ("and p.gsis_id = any(%s)", (list(gsis),)) if gsis is not None else ("", ())
    if ctx.house:
        return query(HOUSE_GAMES_SQL.format(where=where), (ctx.league_id, int(season), *params))[GAMES_OUT]
    ref, _exact = expected_ref(ctx)
    key = (A._scoring_key(ctx.scoring), ref, int(season))
    if gsis is None:
        hit = _priced.get(key)
        if hit is not None:
            return hit.copy()
    df = query(PRICE_GAMES_SQL.format(where=where), (ref, int(season), *params))
    scorings = house_scorings()
    df["points"] = R.price_games(df, ctx.scoring)
    df["points_expected"] = R.price_expected(df, ctx.scoring, scorings.get(ref, {})) if ref else np.nan
    df["points_expected"] = df["points_expected"].where(df["expected_known"].astype(bool))
    out = df[GAMES_OUT]
    if gsis is None:
        _priced.put(key, out)
        return out.copy()
    return out


def clear_priced() -> None:
    _priced.clear()
    _memo.clear()


_memo = budget.region("research_memo", ttl=PRICED_TTL_S)       # INF-2: in the memory budget (was cleared past 200)


def _ctx_key(ctx: Ctx) -> tuple:
    return ("house", ctx.league_id) if ctx.house else ("priced", A._scoring_key(ctx.scoring), expected_ref(ctx)[0])


def memo(kind: str, ctx: Ctx, season: int, fn) -> pd.DataFrame:
    """A derived per-season frame (season table, trend windows, points allowed), kept 10 minutes like the priced games."""
    key = (kind, _ctx_key(ctx), int(season))
    hit = _memo.get(key)
    if hit is not None:
        return hit.copy()
    return _memo.put(key, fn()).copy()


LPS_COLS = ["gsis_id", "games_played", "points", "ppg", "points_per_game_l3", "points_per_game_l5", "games_with_expected",
            "points_expected", "expected_per_game", "diff_per_game", "position_rank_points", "position_rank_ppg"]


def league_season(ctx: Ctx, season: int) -> pd.DataFrame:
    """mart_league_player_season's columns for this league and season (house: the mart; else the same arithmetic over
    the priced games: `research.season_table`)."""
    if ctx.house:
        return query(f"select {', '.join(LPS_COLS)} from analytics.mart_league_player_season where league_id = %s and season = %s",
                     (ctx.league_id, int(season)))
    def build() -> pd.DataFrame:
        g = league_games(ctx, season)
        return R.season_table(g[g["season_type"] == "REG"])[LPS_COLS]
    return memo("season", ctx, season, build)


def league_dvp(ctx: Ctx, season: int) -> pd.DataFrame:
    """Points allowed by defense × position in this league's scoring (`research.defense_allowed`)."""
    def build() -> pd.DataFrame:
        g = league_games(ctx, season)
        return R.defense_allowed(g[g["season_type"] == "REG"])
    return memo("dvp", ctx, season, build)


def league_trend_windows(ctx: Ctx, season: int) -> pd.DataFrame:
    def build() -> pd.DataFrame:
        g = league_games(ctx, season)
        return R.trend_windows(g[g["season_type"] == "REG"])
    return memo("trends", ctx, season, build)


def projections(ctx: Ctx, week: int | None, gsis: list[str]) -> pd.DataFrame:
    """This week's projection + range in the league's scoring (house: mart_player_week_projections, the card's numbers;
    else the NFL-wide lines priced on request: anyleague.price_week, as /api/player on demand)."""
    cols = ["gsis_id", "proj_points", "p10", "p25", "p75", "p90"]
    if week is None or not gsis:
        return pd.DataFrame(columns=cols)
    if ctx.house:
        return query("""select gsis_id, proj_points, p10, p25, p75, p90 from analytics.mart_player_week_projections
                        where league_id = %s and season = %s and week = %s and gsis_id = any(%s)""",
                     (ctx.league_id, ctx.season, int(week), list(gsis)))[cols]
    pr = A.price_week(query, ctx.league_id, ctx.scoring, ctx.slots, ctx.season, int(week))
    ids = [g for g in gsis if g in pr.proj.index]
    if not ids:
        return pd.DataFrame(columns=cols)
    rg = pr.ranges.reindex(ids)
    return pd.DataFrame({"gsis_id": ids, "proj_points": [round(float(pr.proj[g]), 2) for g in ids],
                         **{q: rg[q].to_numpy() for q in ("p10", "p25", "p75", "p90")}})[cols]


def _sort(df: pd.DataFrame, sort: str | None, direction: str | None, default: str, default_dir: str = "desc") -> pd.DataFrame:
    col = sort or default
    if col not in df.columns:
        raise BadRequest(f"cannot sort by {col}")
    d = (direction or default_dir).lower()
    if d not in ("asc", "desc"):
        raise BadRequest("dir is asc or desc")
    key = df[col]
    if key.dtype == object:
        num = pd.to_numeric(key, errors="coerce")
        key = key.astype(str).str.lower() if num.isna().all() and key.notna().any() else num
    return df.assign(_k=key).sort_values(["_k", "player_name"] if "player_name" in df else ["_k"],
                                         ascending=[d == "asc", True] if "player_name" in df else [d == "asc"],
                                         na_position="last").drop(columns="_k")


def _norm(s) -> str:
    return re.sub(r"[^a-z]", "", str(s or "").lower())


# ------------------------------------------------------------------------------ /api/trends
TRENDS_HOWTO = (
    "- **Use it to spot a role change before the points show up**: add the risers off waivers, and think about moving the fallers.\n"
    "- Each player's last **3 games** are compared with his games before that. A number is called **up** or **down** only when the "
    "change is big enough to matter (say, 3 points of target share) *and* bigger than his normal week-to-week swing.\n"
    "- **Strength** says how unusual the change is for him: 1 is worth a look, 2 is a clear change. **Momentum** averages that over "
    "his work (targets, snaps, carries, how far downfield he is targeted, expected points) and ignores his fantasy points on "
    "purpose: three touchdowns can happen without the role changing at all.\n"
    "- **Trend** names what moved: \"↑ targets, ↑ snaps\" is more work; \"↑ targets, ↑ aDOT\" (targeted deeper downfield) is a "
    "different, deeper role.\n"
    "- Nothing is called a trend before a player's fourth game; until then the page shows an *early read* and says so.\n"
    "- **Over / under**: points per game in this league's scoring against expected points per game (what his targets and "
    # ---- IP-3 (Wave I-P): graded — the gap closes in part, and the projection already expects it (no "due" / "hot")
    "carries are usually worth). It is what happened, not a forecast: graded on past weeks, players below expectation "
    "scored more the next week and players above it less, about as much as their projection already expected.")
ROLE_HOWTO = (
    "- **Act on a bigger role before the points show up**: a free agent here is a stash (Waiver Wire values him for your "
    "lineup); one of your bench players here may be worth a start. A smaller role is a reason to bench or sell.\n"
    "- An alert means his share of the snaps, the targets or the carries jumped (or fell) in his last one to three games, well "
    "past his usual week-to-week swing, and held in every one of those games. A single big game is not an alert: three "
    "touchdowns can happen without the role changing.\n"
    "- **Why** is the reason we can name: an injured starter (he is filling in), a benching or a depth-chart move, a trade. "
    "\"The coaches changed his role\" means none of those: fine, but check the news.\n"
    "- **Held**: one game is a first look, three games is his role now. A fill-in's role ends when the starter returns: the "
    "card says so once the starter is off the injury report.\n"
    "- How often they last: in the 2025 season, 67% of the bigger roles and 64% of the smaller ones were still there three "
    "games later (a fill-in counted only while the starter stayed out).")
EARLY_READ = ("No player in this list has four games yet (NFL {season}). Trends are not called before game four because three "
              "data points cannot be separated from noise. The `metrics` are an **early read** — latest game versus the "
              "season so far — which is exactly as unreliable as it sounds.")
REF_NOTE = ("Fields ending in `_ref` are in the reference league's scoring ({ref}), one scale for every league and season; "
            "the same field without `_ref` is this league's scoring.")

TAG_COLS = ["gsis_id", "player_name", "position", "team", "games", "latest_week", "tags", "momentum", "opportunity_trend",
            "n_up", "n_down", "target_share_l3", "target_share_change", "target_share_z", "snap_share_l3", "snap_share_change",
            "snap_share_z", "carry_share_change", "carry_share_z", "air_yards_share_change", "adot_change",
            "expected_points_l3", "expected_points_change", "expected_points_z", "points_l3", "points_change"]
TREND_REF = {"expected_points_l3": "expected_points_l3_ref", "expected_points_change": "expected_points_change_ref",
             "points_l3": "points_l3_ref", "points_change": "points_change_ref"}
METRIC_COLS = ["gsis_id", "metric", "metric_label", "display_kind", "games_with_metric", "value_prior", "value_l3", "value_season",
               "value_latest", "change", "z", "slope_per_game", "direction", "confidence"]
ALERT_COLS = ("gsis_id, player_name, position, team, direction, direction_label, kind, cause_text, since_week, week, games_held, "
              "change_text, trigger_name, trigger_status, trigger_ended, expires_after_week, z, confidence, primary_metric")


def reference_name() -> str:
    ref = query("select league_name from analytics.dim_league_season where is_reference_league")
    return str(ref["league_name"].iloc[0]) if not ref.empty else "the reference league"


def _alert(r: dict, roster_id: int | None = None) -> dict:
    out = {k: r.get(k) for k in ("direction", "direction_label", "kind", "cause_text", "change_text", "games_held", "since_week",
                                 "week", "z", "confidence", "primary_metric", "trigger_name", "trigger_status", "expires_after_week")}
    out["kind_label"] = signals.kind_label(r)
    out["headline"] = links(signals.alert_headline(r, r.get("player_name")))
    out["lines"] = links(signals.alert_lines(r))
    if "rostered_by_team" in r:
        out["who"] = signals.who_has_him(r, roster_id) or None
    return out


def role_alerts(ctx: Ctx, season: int, gsis: list[str] | None = None) -> pd.DataFrame:
    if missing_relations(("mart_player_role_alerts",)):
        return pd.DataFrame()
    where, params = ("and gsis_id = any(%s)", (list(gsis),)) if gsis is not None else ("", ())
    al = query(f"select {ALERT_COLS} from analytics.mart_player_role_alerts where season = %s and is_live {where} "
               "order by direction = 'up' desc, kind in ('role_up', 'role_down'), abs(z) desc, player_name",
               (int(season), *params))
    # ---- IT-3: no role alert for a player the one definition leaves out this week (the mart is built from the
    # nightly's game data and knows nothing of today's status: a role change of a player who sits is not a pickup or a
    # start); league_gate at request time, the same path every league screen asks
    if not al.empty and "gsis_id" in al:
        from . import league_gate as LG
        gate = LG.blocks([g for g in al["gsis_id"] if isinstance(g, str)])
        al = al[[not LG.sits(gate.get(g)) for g in al["gsis_id"]]].reset_index(drop=True)
    # ---- end IT-3
    return al


# ---- IA-1: Trends in plain words — the work per game per row, and the reason in a sentence (Wave I-A)
NEAR = 0.5            # points per game: closer than this to his work is "about what his work is worth" (web: research.ts)
WORK_SQL = """
with g as (
    select p.gsis_id, p.week, p.targets, p.carries, p.offense_snap_pct, p.snaps_known, p.red_zone_targets,
           p.red_zone_carries, coalesce(p.receiving_tds, 0) + coalesce(p.rushing_tds, 0) as tds, p.passing_tds,
           p.target_share, p.carry_share, row_number() over (partition by p.gsis_id order by p.week desc) as rn
    from analytics.fct_player_game p
    where p.season = %s and p.season_type = 'REG' and p.played and p.gsis_id = any(%s)
)
select g.gsis_id, count(*) as work_games,
       avg(g.targets) as targets_pg, avg(g.targets) filter (where g.rn <= 3) as targets_pg_l3,
       avg(g.carries) as carries_pg, avg(g.carries) filter (where g.rn <= 3) as carries_pg_l3,
       avg(g.offense_snap_pct) filter (where g.rn <= 3 and g.snaps_known) as snap_pct_l3,
       sum(g.red_zone_targets) as rz_targets, sum(g.red_zone_carries) as rz_carries, sum(g.tds) as tds,
       sum(g.passing_tds) as pass_tds,
       array_agg(g.target_share::float order by g.week) as target_shares,
       array_agg(g.carry_share::float order by g.week) as carry_shares,
       bool_or(f.pn_qb_changed = 1) as qb_changed
from g
left join analytics.mart_player_week_features f on f.gsis_id = g.gsis_id and f.season = %s and f.week = %s
group by g.gsis_id
"""
WORK_WORDS = {"QB": "the throws and runs", "RB": "the carries and targets", "WR": "the targets", "TE": "the targets"}
WORK_COLS = ["targets_pg", "targets_pg_l3", "carries_pg", "carries_pg_l3", "snap_pct_l3", "rz_targets", "rz_carries",
             "tds", "pass_tds"]


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def _share_move(r: dict) -> tuple[str, float, float] | None:
    """(word, first, last): his share of the team's targets (carries for a running back) from his first game of the season
    to his last, when it moved 6 points or more; None otherwise."""
    word, key = ("carries", "carry_shares") if r.get("position") == "RB" else ("targets", "target_shares")
    vals = [x for x in (_f(v) for v in (r.get(key) or [])) if x is not None]
    if len(vals) < 2 or abs(vals[-1] - vals[0]) < 0.06:
        return None
    return word, vals[0], vals[-1]


def trend_cause(r: dict) -> str | None:
    """One cause the numbers support, or None (we do not guess): touchdowns against red-zone chances, a quarterback
    change, a share of the team's work that moved."""
    gap, pos = _f(r.get("gap")), r.get("position")
    if gap is None or abs(gap) <= NEAR:
        return None
    games = int(_f(r.get("work_games")) or 0)
    tds = int(_f(r.get("tds")) or 0)
    rz = int((_f(r.get("rz_targets")) or 0) + ((_f(r.get("rz_carries")) or 0) if pos in ("RB", "QB") else 0))
    chances = ("red-zone target" if pos in ("WR", "TE") else "red-zone chance") + ("" if rz == 1 else "s")
    move = _share_move(r)
    if gap < 0:
        if pos == "QB":
            ptd = int(_f(r.get("pass_tds")) or 0)
            if ptd == 0 and games >= 2:
                return f"no touchdown passes in {games} games"
        elif tds == 0 and rz >= 2:
            return f"no touchdowns on {rz} {chances}"
        if r.get("qb_changed") and pos != "QB":
            return "his quarterback changed"
        if move and move[2] < move[1]:
            return f"his share of the {move[0]} fell from {move[1]:.0%} to {move[2]:.0%}"
        return None
    if pos == "QB":
        ptd = int(_f(r.get("pass_tds")) or 0)
        if games and ptd >= 2 * games:
            return f"{ptd} touchdown passes in {games} games"
    elif tds >= 2 and games and tds / games >= 0.6:
        return f"{tds} touchdowns in {games} games" + (f" on {rz} {chances}" if rz else "")
    if move and move[2] > move[1]:
        return f"his share of the {move[0]} rose from {move[1]:.0%} to {move[2]:.0%}"
    if r.get("qb_changed") and pos != "QB":
        return "his quarterback changed"
    return None


def trend_why(r: dict) -> str | None:
    """'Getting the targets of a 10.5-point player, scoring 3.6: no touchdowns on 4 red-zone targets.'"""
    ppg, xppg = _f(r.get("ppg")), _f(r.get("xppg"))
    if ppg is None or xppg is None:
        return None
    x = f"{xppg:.1f}"
    an = "an" if x.startswith(("8", "11.", "18.")) else "a"            # an 8.4-point, an 11.2-point, an 18.6-point player
    line = f"Getting {WORK_WORDS.get(r.get('position') or '', 'the work')} of {an} {x}-point player, scoring {ppg:.1f}"
    cause = trend_cause(r)
    return f"{line}: {cause}." if cause else f"{line}."


def trend_work(season: int, week: int | None, ids: list[str]) -> pd.DataFrame:
    """Per player: targets and carries per game (last 3 and the season), snap share over his last 3, red-zone chances,
    touchdowns, his share of the team's work game by game, a quarterback change this week. One query."""
    cols = ["gsis_id", "work_games", *WORK_COLS, "target_shares", "carry_shares", "qb_changed"]
    if not ids:
        return pd.DataFrame(columns=cols)
    s = int(season)
    return query(WORK_SQL, (s, list(ids), s, int(week) if week is not None else -1))[cols]
# ---- end IA-1


def trends(league_id: str, *, position: str | None = None, limit: int | None = None, view: str = "all",
           season: int | None = None, who: str = "all", team: int | None = None, min_games: int = 1,
           sort: str | None = None, dir: str | None = None, metrics: str = "moved", source: str | None = None) -> dict:
    ctx = context(league_id, source)
    view = (view or "all").lower()
    if view not in ("over", "under", "all"):
        raise BadRequest("view is over, under or all")
    who = (who or "all").lower()
    if who not in ("all", "fa", "rostered", "team"):
        raise BadRequest("who is all, fa, rostered or team")
    if who == "team" and team is None:
        raise BadRequest("who=team needs team=<roster_id>")
    n = _limit(limit)
    season = int(season or ctx.season)
    pos = _positions(position, SKILL)
    tags = query(f"select {', '.join(TAG_COLS)} from analytics.mart_player_trend_tags where season = %s and position = any(%s)",
                 (season, pos)).rename(columns=TREND_REF)
    ls = league_season(ctx, season).rename(columns={"expected_per_game": "xppg", "diff_per_game": "gap",
                                                     "games_played": "league_games"})
    df = tags.merge(ls[["gsis_id", "league_games", "ppg", "xppg", "gap", "games_with_expected"]], on="gsis_id", how="left")
    tw = league_trend_windows(ctx, season)
    tw[tw.columns[1:]] = tw[tw.columns[1:]].astype(float).round(2)
    df = df.merge(tw.drop(columns=["games"]), on="gsis_id", how="left")
    df["gap_direction"] = np.select([df["gap"] > 0, df["gap"] < 0, df["gap"] == 0], ["over", "under", "even"], default=None)
    df["gap_direction"] = df["gap_direction"].where(df["gap"].notna(), None)
    ro = rostered(ctx)
    df = df.merge(ro, on="gsis_id", how="left")
    df["is_free_agent"] = df["rostered_by_roster_id"].isna()
    if who == "fa":
        df = df[df["is_free_agent"]]
    elif who == "rostered":
        df = df[~df["is_free_agent"]]
    elif who == "team":
        df = df[df["rostered_by_roster_id"] == int(team)]
    df = df[df["games"] >= int(min_games or 1)]
    if view == "over":
        df = df[df["gap"] > 0]
    elif view == "under":
        df = df[df["gap"] < 0]
    # ---- I0-A: nobody who cannot play this week in "due" or "hot" (Out / IR / PUP / suspended: the availability overlay)
    # ---- IU-3 (the rule the Rankings imply): a player who sits this week — cannot play, or a status that rarely plays
    # (Doubtful) — is not a "due" or "hot" call this week; he is listed under `left_out_players` with his reason, and
    # his season trend is not touched. One question, `league_gate` (the stored record + Sleeper + ESPN + the week's
    # report), not the older overlay's snapshot with its own code set (`NOT_IN_TRENDS`, which kept Doubtful listed)
    from . import league_gate as LG
    gate = LG.blocks([g for g in df["gsis_id"] if isinstance(g, str)]) if not df.empty else {}
    out_now = {g: b for g, b in gate.items() if LG.sits(b)}
    names = dict(zip(df["gsis_id"], df["player_name"], strict=False)) if "player_name" in df else {}
    left_out = [{"gsis_id": g, "player_name": names.get(g), "status": b.get("status"), "why": b.get("why")}
                for g, b in out_now.items()]
    # ---- end IU-3
    df = df[~df["gsis_id"].isin(set(out_now))]
    # ---- end I0-A
    default_sort, default_dir = {"over": ("gap", "desc"), "under": ("gap", "asc"), "all": ("momentum", "desc")}[view]
    total = int(len(df))
    df = _sort(df, sort, dir, default_sort, default_dir if sort is None else "desc").head(n)
    ids = list(df["gsis_id"])
    page = decorate(df.drop(columns=["rostered_by_roster_id", "rostered_by_team"]), ctx)
    met = query(f"select {', '.join(METRIC_COLS)} from analytics.mart_player_trends where season = %s and gsis_id = any(%s) "
                "order by direction in ('up', 'down') desc, abs(z) desc nulls last", (season, ids)) if ids else pd.DataFrame()
    if metrics == "none":                    # the screens filter and sort on the phone and never read the metrics (716 KB saved)
        met = met.iloc[0:0]
    if not met.empty and metrics != "all":
        early = (met["direction"] != "insufficient").groupby(met["gsis_id"]).transform("sum") == 0
        met = met[met["direction"].isin(["up", "down"]) | early]
    if not met.empty:
        met["ref_scored"] = met["metric"].isin(["points", "expected_points"])
    by_player = _grouped(met, "gsis_id")
    al = role_alerts(ctx, season, ids) if ids else pd.DataFrame()
    alerts = {r["gsis_id"]: _alert(r) for r in _records(al)}
    # ---- IA-1: the work per game and the reason in a sentence
    work = {r["gsis_id"]: r for r in trend_work(season, ctx.week, ids).to_dict("records")}
    # ---- end IA-1
    players = []
    for r in _records(page):
        r["metrics"] = by_player.get(r["gsis_id"], [])
        r["role_alert"] = alerts.get(r["gsis_id"])
        # ---- IA-1
        w = work.get(r["gsis_id"], {})
        for c in WORK_COLS:
            v = _f(w.get(c))
            r[c] = None if v is None else (round(v, 2) if c in ("snap_pct_l3",) else round(v, 1) if c.endswith(("_pg", "_l3")) else int(v))
        r["why"] = trend_why({**r, **w})
        r["cause"] = trend_cause({**r, **w})
        # ---- end IA-1
        players.append(r)
    # the page's first section: this week's role alerts among this league's players (rostered or free agents)
    every = role_alerts(ctx, season)
    if not every.empty:
        every = every[every["position"].isin(pos)].merge(ro, on="gsis_id", how="left")
        every["is_free_agent"] = every["rostered_by_roster_id"].isna()
        if ctx.house:   # the page joins mart_player_availability: players in this league's pool
            pool = query("select gsis_id from analytics.mart_player_availability where league_id = %s", (ctx.league_id,))
            every = every[every["gsis_id"].isin(set(pool["gsis_id"]))]
    alert_rows = [{**{k: r.get(k) for k in ("gsis_id", "player_name", "position", "team")}, **_alert(r, team)}
                  for r in _records(every)]
    enough = (tags["opportunity_trend"] != "insufficient").any() if not tags.empty else False
    from . import context_record as CR  # ---- IP-3: what the tag has meant for the next game (the record's grade)
    return {**ctx.meta(), "season": season, "view": view, "positions": pos, "total": total,
            "record": CR.summary()["trend"],    # ---- IP-3: graded False / words None without the record
            "early_read": not bool(enough), "notice": None if enough else EARLY_READ.format(season=season),
            "players": players, "role_alerts": alert_rows,
            "howto": TRENDS_HOWTO, "howto_sections": [{"title": "How to read role alerts", "text": ROLE_HOWTO}],
            "scoring_note": REF_NOTE.format(ref=reference_name()),
            # ---- I0-A: how many the overlay left out, and who
            "availability": {**availability.stamp(), "left_out": len(left_out), "left_out_players": left_out}}


# ------------------------------------------------------------------------------ /api/matchups/defense
DVP_HOWTO = (
    "- **Start players against the defenses at the top** of the \"gives up the most\" list; be wary of the bottom one.\n"
    "- **Pts allowed/G** is the fantasy points each defense gives up to that position per game this season, in this league's "
    "scoring. **Rank** 1 = gives up the most (the matchup you want), 32 = the stingiest.\n"
    "- The **(L4)** columns use only the defense's last 4 games: they catch an injury or a new scheme sooner.\n"
    "- Early in the season these ranks jump around; from about week 6 they settle.\n"
    "- **Softer** means the defense has given up more to that position over its last 3 games than before: a better matchup "
    "than its season rank says. **Stiffer** means it has tightened up. Only changes bigger than the defense's normal "
    "week-to-week swing count; a defense needs four games before it shows a direction.")
PROFILE_COLS = ["opps_allowed_pg", "targets_allowed_pg", "carries_allowed_pg", "yards_per_opp_allowed", "td_rate_allowed",
                "gives_up", "rank_opportunity", "rank_efficiency", "rank_td_rate", "rank_targets", "rank_carries", "n_defenses"]
PROFILE_REF = {"points_allowed_pg": "points_allowed_pg_ref", "offense_baseline_pg": "offense_baseline_pg_ref",
               "adjusted_points_pg": "adjusted_points_pg_ref", "league_points_pg": "league_points_pg_ref",
               "rank_points": "rank_points_ref", "rank_adjusted": "rank_adjusted_ref"}


BENCH_SLOTS = {"BN", "IR", "TAXI", "RES"}


def starter_slots(ctx: Ctx, team: int) -> list[tuple[str, str | None]]:
    """One roster's current starters as (gsis_id, slot), in lineup order: house league = mart_player_availability's
    is_current_starter (no slot); any other league = Sleeper's `starters`, each paired with the league's starting slot
    (none set on Sleeper: the lineup My week proposes)."""
    if ctx.house:
        st = query("""select gsis_id from analytics.mart_player_availability where league_id = %s and rostered_by_roster_id = %s
                      and is_current_starter and gsis_id is not null order by gsis_id""", (ctx.league_id, int(team)))
        # the slot (and lineup order) where My week's lineup starts him too; the rest after, by position
        lr = cards.lineup_rows(ctx.league_id, ctx.season, int(ctx.week), int(team)) if ctx.week is not None else pd.DataFrame()
        lr = lr[(lr["role"] == "starter") & lr["gsis_id"].notna()] if not lr.empty else lr
        slot_of = {str(r["gsis_id"]): (int(r["slot_order"]), r["slot"]) for _, r in lr.iterrows()} if not lr.empty else {}
        ids = sorted(st["gsis_id"], key=lambda g: slot_of.get(g, (99, None))[0])
        return [(g, slot_of.get(g, (99, None))[1]) for g in ids]
    sids = [str(p) for r in ctx.rosters if int(r["roster_id"]) == int(team) for p in (r.get("starters") or [])]
    slots = [s for s in ctx.slots if str(s).upper() not in BENCH_SLOTS]
    slot_of = dict(zip(sids, slots, strict=False)) if len(slots) == len(sids) else {}
    idm = query("select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)", (sorted(set(sids)),))
    gsis_of = dict(zip(idm["sleeper_id"].astype(str), idm["gsis_id"], strict=False)) if not idm.empty else {}
    out = [(gsis_of[s], slot_of.get(s)) for s in sids if s in gsis_of]
    if not out and ctx.week is not None and any(int(r["roster_id"]) == int(team) for r in ctx.rosters):
        # no lineup set on Sleeper: the lineup My week proposes (ondemand: the nightly's solver on this league)
        from .ondemand import PlayerContext
        rows = PlayerContext(ctx.league_id).lineup(int(team), int(ctx.week))
        if not rows.empty:
            st = rows[(rows["role"] == "starter") & rows["gsis_id"].notna()]
            out = [(str(r["gsis_id"]), r.get("slot")) for _, r in st.iterrows()]
    return out


STARTER_GAME_SQL = """select g.home_team, g.away_team from analytics.dim_game g
                      where g.season = %s and g.week = %s and g.season_type = 'REG' and %s in (g.home_team, g.away_team)"""


def defense_starters(ctx: Ctx, team: int, positions: list[str]) -> list[dict]:
    """Your starters this week at the heatmap's positions and the defense each faces (the cells the screen rings)."""
    pairs = starter_slots(ctx, team)
    if not pairs or ctx.week is None:
        return []
    df = decorate(pd.DataFrame({"gsis_id": [g for g, _ in pairs], "slot": [s for _, s in pairs]}), ctx)
    out = []
    for r in _records(df):
        if r.get("position") not in positions:
            continue
        team_abbr, opp, home = r.get("team"), None, None
        if isinstance(team_abbr, str) and team_abbr:
            g = query(STARTER_GAME_SQL, (ctx.season, int(ctx.week), team_abbr))
            if not g.empty:
                home = bool(g.iloc[0]["home_team"] == team_abbr)
                opp = g.iloc[0]["away_team"] if home else g.iloc[0]["home_team"]
        out.append({k: r.get(k) for k in ("gsis_id", "player_name", "position", "team", "headshot_url", "slot")}
                   | {"opponent": opp, "is_home": home})
    return out


def matchups_defense(league_id: str, *, position: str | None = None, source: str | None = None,
                     team: int | None = None) -> dict:
    ctx = context(league_id, source)
    starts = [p for p in POSITIONS if p in {s.upper() for s in ctx.slots}] or list(SKILL)
    pos = _positions(position, POSITIONS, default=starts)
    cur = query("""select defense, season, position, through_week, games, points_allowed_per_game_std, points_allowed_per_game_l4,
                          games_l4, rank_std, rank_l4 from analytics.mart_defense_vs_position_current where position = any(%s)""",
                (pos,))
    season = int(cur["season"].max()) if not cur.empty else ctx.season
    lg = league_dvp(ctx, season)
    lg = lg[lg["position"].isin(pos)]
    ref = cur.rename(columns={"points_allowed_per_game_std": "points_allowed_per_game_std_ref",
                              "points_allowed_per_game_l4": "points_allowed_per_game_l4_ref",
                              "rank_std": "rank_std_ref", "rank_l4": "rank_l4_ref"})
    rows = lg.drop(columns=["allowed_l3", "allowed_prior", "allowed_season", "change", "z", "direction"]).merge(
        ref[["defense", "position", "points_allowed_per_game_std_ref", "points_allowed_per_game_l4_ref", "rank_std_ref",
             "rank_l4_ref"]], on=["defense", "position"], how="outer")
    trend = lg[["defense", "position", "allowed_l3", "allowed_prior", "allowed_season", "change", "z", "direction"]]
    dt = query("""select defense, position, allowed_l3 as allowed_l3_ref, allowed_prior as allowed_prior_ref,
                         change as change_ref, z as z_ref, direction as direction_ref
                  from analytics.mart_defense_trends where season = %s""", (season,))
    rows = rows.merge(trend, on=["defense", "position"], how="left").merge(dt, on=["defense", "position"], how="left")
    week = ctx.week if ctx.season == season else None
    if week is not None and not missing_relations(("mart_defense_position_profile",)):
        prof = query(f"""select defense, position, {', '.join(PROFILE_COLS)}, {', '.join(PROFILE_REF)}
                         from analytics.mart_defense_position_profile where season = %s and week = %s and position = any(%s)""",
                     (season, int(week), pos)).rename(columns=PROFILE_REF)
        rows = rows.merge(prof, on=["defense", "position"], how="left")
    rows["season"] = season
    rows = rows.sort_values(["position", "rank_std", "defense"], na_position="last")
    played = query("select distinct week from analytics.dim_game where season = %s and season_type = 'REG' and is_final "
                   "order by week", (season,))
    n_def = int(rows.groupby("position")["defense"].nunique().max()) if not rows.empty else 0
    return {**ctx.meta(), "season": season, "profile_week": week, "positions": pos, "n_defenses": n_def,
            "weeks_used": [int(w) for w in played["week"]] if not played.empty else [],
            "teams": _records(defense_meaning(rows)), "howto": DVP_HOWTO,                        # ---- IB-3: tone, rank
            "rank_note": RANK_NOTE, "scoring_note": REF_NOTE.format(ref=reference_name()),         # ---- IB-3
            **({"team": team, "starters": defense_starters(ctx, int(team), pos)} if team is not None else {})}


COVER_SPLIT_NOTE = ("Shutdown here = the corner's rank over the season to date, not what was known in the week of the "
                    "game.")                                    # ---- IO-4 fix round (the best-corners split's ranks)


# ---- IB-3 (Wave I-B): matchup meaning first. Every defense-vs-position cell and every cornerback call carries a tone
# (favorable / neutral / difficult: the main signal on the screen), the rank runs ONE way on both routes (1 = the
# toughest for the offense: the defense that gives up the fewest points to the position, the corner hardest to throw
# on), the rank in words, and a cornerback call carries its certainty beside it (likely / unclear / no call: the
# mart's call_strength). Thresholds: docs/METRICS.md § Matchups. The mart's own columns (rank_std: 1 = gives up the
# most) and app/lib/matchups' sentence (`line`) are unchanged (the console and the parity tests read them).
TONES = ("favorable", "neutral", "difficult")
TONE_EDGE = 10 / 32          # the card's reason line (cards.reason_pieces): rank <= 10 "the Nth-most", >= 23 "the Nth-fewest"
CERTAINTY = {"clear": "likely", "even": "unclear"}
RANK_NOTE = ("#1 = the toughest for the offense: the defense that gives up the fewest points to the position, the "
             "corner hardest to throw on.")
LABEL_TONE = {"shutdown": "difficult", "solid": "neutral", "target": "favorable"}


def _ordinal(k: int) -> str:
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


def _rank(v) -> int | None:
    return None if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v) else int(v)


def tone_edge(n: int) -> int:
    """How many ranks at each end of n count as favorable / difficult (10 of 32, the card's sentence rule)."""
    return max(1, round(n * TONE_EDGE))


def defense_tone(rank_most, n) -> str | None:
    """The tone of a defense-vs-position matchup from the mart's rank (1 = gives up the most) among n defenses."""
    r = _rank(rank_most)
    if r is None or not n:
        return None
    e = tone_edge(int(n))
    return "favorable" if r <= e else "difficult" if r >= int(n) + 1 - e else "neutral"


def tough_rank(rank_most, n) -> int | None:
    """The mart's rank turned the screen's way: 1 = gives up the fewest (the toughest for the offense)."""
    r = _rank(rank_most)
    return None if r is None or not n else int(n) + 1 - r


def gives_up_words(rank_most, n) -> str | None:
    """'gives up the 2nd-most' / 'gives up the 7th-fewest' (the nearer end; the card's words)."""
    r = _rank(rank_most)
    if r is None or not n:
        return None
    if r <= (int(n) + 1) / 2:
        return "gives up the most" if r == 1 else f"gives up the {_ordinal(r)}-most"
    k = int(n) + 1 - r
    return "gives up the fewest" if k == 1 else f"gives up the {_ordinal(k)}-fewest"


def defense_meaning(rows: pd.DataFrame) -> pd.DataFrame:
    """The defense rows + n_ranked (defenses ranked at the position), tough_rank / tough_rank_l4 (1 = toughest),
    tone, rank_words ('gives up the 2nd-most points to running backs')."""
    if rows.empty:
        return rows.assign(n_ranked=[], tough_rank=[], tough_rank_l4=[], tone=[], rank_words=[])
    out = rows.copy()
    n = out.groupby("position")["rank_std"].transform("count")
    n4 = out.groupby("position")["rank_l4"].transform("count")
    out["n_ranked"] = n.astype(int)
    out["tough_rank"] = [tough_rank(r, k) for r, k in zip(out["rank_std"], n, strict=True)]
    out["tough_rank_l4"] = [tough_rank(r, k) for r, k in zip(out["rank_l4"], n4, strict=True)]
    out["tone"] = [defense_tone(r, k) for r, k in zip(out["rank_std"], n, strict=True)]
    out["rank_words"] = [None if w is None else f"{w} points to {cards.POS_PLURAL.get(p, 'the position')}"
                         for w, p in ((gives_up_words(r, k), p) for r, k, p in zip(out["rank_std"], n, out["position"], strict=True))]
    return out


def corner_words(rank, n) -> str | None:
    """'the 17th-hardest of 74 starting corners to throw on' / 'the 9th-easiest of 74 …' (the nearer end)."""
    r, n = _rank(rank), _rank(n)
    if r is None or not n:
        return None
    if r <= (n + 1) / 2:
        k = "the hardest" if r == 1 else f"the {_ordinal(r)}-hardest"
    else:
        e = n + 1 - r
        k = "the easiest" if e == 1 else f"the {_ordinal(e)}-easiest"
    return f"{k} of {n} starting corners to throw on"


def cb_meaning(r: dict) -> dict:
    """A cornerback call's tone, its certainty (likely: his targets lean 15+ points to one side; unclear: either outside
    corner; no call), the named corners with their rank in words, and his history with them (app/lib/matchups)."""
    status, strength = r.get("call_status"), r.get("call_strength")
    n = r.get("cb_n_ranked")
    certainty = CERTAINTY.get(str(strength)) if status == "called" else "no call"
    named = []
    if status == "called":
        named.append({"name": r.get("likely_cover_name"), "slot": r.get("likely_cover_slot"), "rank": _rank(r.get("cover_rank")),
                      "label": r.get("cover_label")})
        if strength != "clear" and isinstance(r.get("other_cover_name"), str) and r.get("other_cover_name"):
            s = str(r.get("other_cover_slot") or "").lower()
            named.append({"name": r.get("other_cover_name"), "slot": r.get("other_cover_slot"), "rank": _rank(r.get(f"{s}_rank")),
                          "label": r.get(f"{s}_label")})
    for c in named:
        c["side"] = M.SLOT_WORDS.get(str(c["slot"]), "corner")
        c["words"] = corner_words(c["rank"], n) or "unranked: too few snaps to rank"
        c["tone"] = LABEL_TONE.get(str(c["label"])) if c["rank"] is not None else None
    tones = {c["tone"] for c in named if c["tone"] is not None}
    if not tones:
        tone = None                                   # no ranked corner named: no read (unknown is not neutral)
    elif certainty == "likely":
        tone = named[0]["tone"]
    else:                                             # either corner: a tone only when every ranked one agrees
        tone = next(iter(tones)) if len(tones) == 1 and all(c["tone"] is not None for c in named) else "neutral"
    side = r.get("side_share")
    other = r.get("other_side_share")

    def pct(v) -> str:
        return "?" if v is None or pd.isna(v) else f"{round(float(v) * 100)}%"

    if certainty == "likely":
        cw = f"likely: {pct(side)} of his targets go to that side, {pct(other)} to the other"
    elif certainty == "unclear":
        cw = f"unclear: {pct(side)} of his targets one way, {pct(other)} the other, so either corner"
    elif status == "tight end":
        cw = "no call: a tight end mostly draws linebackers and safeties"
    elif status == "too few targets":
        cw = "no call: too few targets with a direction to tell his side"
    else:
        cw = "no call: no depth chart yet"
    who = M.last_name(r.get("likely_cover_name")) if status == "called" else ""
    hist = M.cb_history(r, who).strip() if status == "called" else ""
    return {"tone": tone, "certainty": certainty, "certainty_words": cw, "cover_rank_words": corner_words(r.get("cover_rank"), n),
            "named_corners": named, "history": hist or None}
# ---- end IB-3


# ------------------------------------------------------------------------------ /api/matchups/cb
CB_HOWTO = (
    "- **Start the receiver whose likely corner ranks lower** when two options are close; don't bench a star for a "
    "tough corner: his targets matter more, and the projection already counts the defense.\n"
    "- **Likely across from him** is a guess from where his targets go (to the offense's left or right): the outside "
    "corner on that side (throws to the offense's left meet the defense's right corner). Public data has no receiver "
    "alignment and no coverage assignments. Checked on last season: when a receiver's targets leaned clearly to one "
    "side (15 points or more), the corner we named was charged with about 1 in 5 of his targets and the other outside "
    "corner about 1 in 7, no more than any other throw; with a closer split it was about 1 in 5 against 1 in 6 — "
    "either could be across from him, so the card names both.\n"
    "- **What public data can't tell you**: who covered whom on a play, whether a corner follows the top receiver around "
    "(our best test for that caught 1 of 6 well-known shadow corners last season, so we don't flag it), or who "
    "lines up in the slot.\n"
    "- **CB rank** = among starting corners since the start of last season (at least 20 pass plays in coverage a team "
    "game), on three numbers weighed equally: how often he is thrown at per pass play, yards per throw at him "
    "adjusted for the offenses he faced, and the quarterback rating on those throws. Shutdown = the top quarter, "
    "target = the bottom quarter, solid = the middle half.\n"
    "- Tight ends mostly draw linebackers and safeties, so they get no cornerback call. Coverage numbers come from "
    "Pro-Football-Reference's charting (2018 on), a few days after each game.")
CORNER_COLS = ("gsis_id, window_label, defender_name, quality_rank, quality_label, n_ranked, targets_per_coverage_snap, "
               "adj_yards_per_target, yards_per_target_allowed, passer_rating_allowed, round(coverage_snaps)::int as coverage_snaps, "
               "targets, is_ranked")
FACED_COLS = ("receiver_gsis_id, defender_gsis_id, defender_name, defense, games, targets, receptions, receiving_yards, "
              "receiving_tds, defender_snap_share, share_of_targets, evidence")


def _corners(season: int, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    c = query(f"select {CORNER_COLS} from analytics.mart_cb_rankings where season = %s and gsis_id = any(%s)", (season, ids))
    if c.empty:
        return {}
    two = c[c["window_label"] == "two_seasons"].drop(columns="window_label")
    for w, col in (("season", "rank_this_season"), ("last_4", "rank_last_4")):
        two = two.merge(c.loc[c["window_label"] == w, ["gsis_id", "quality_rank"]].rename(columns={"quality_rank": col}),
                        on="gsis_id", how="left")
    return {r["gsis_id"]: r for r in _records(two)}


def matchups_cb(league_id: str, *, team: int | None = None, limit: int | None = None, source: str | None = None) -> dict:
    ctx = context(league_id, source)
    n = _limit(limit)
    week = ctx.week
    if week is None:
        return {**ctx.meta(), "team": team, "matchups": [], "summary": [], "notice": "The regular season is over.",
                "howto": CB_HOWTO}
    if missing_relations(("mart_cb_matchups", "mart_cb_rankings", "mart_receiver_vs_cb")):
        return {**ctx.meta(), "team": team, "matchups": [], "summary": [],
                "notice": "This section arrives with the next data refresh.", "howto": CB_HOWTO}
    ro = rostered(ctx)
    starters: set[str] = set()
    if team is not None:
        mine = ro[ro["rostered_by_roster_id"] == int(team)]
        if mine.empty and not (ro["rostered_by_roster_id"] == int(team)).any():
            known = set(ro["rostered_by_roster_id"].dropna().astype(int))
            if int(team) not in known and (ctx.house or int(team) not in {int(r["roster_id"]) for r in ctx.rosters}):
                raise NotFound(f"no team {team} in league {ctx.league_id}")
        ids = list(mine["gsis_id"])
        starters = {g for g, _ in starter_slots(ctx, int(team))}
        cbm = query("select * from analytics.mart_cb_matchups where season = %s and week = %s and gsis_id = any(%s)",
                    (ctx.season, int(week), ids)) if ids else pd.DataFrame()
    else:
        cbm = query("select * from analytics.mart_cb_matchups where season = %s and week = %s and gsis_id = any(%s)",
                    (ctx.season, int(week), list(ro["gsis_id"])))
    if cbm.empty:
        return {**ctx.meta(), "team": team, "matchups": [], "summary": [],
                "notice": "No receivers on this roster." if team is not None else "No rostered receivers have a game this week.",
                "howto": CB_HOWTO}
    cbm["is_starter"] = cbm["gsis_id"].isin(starters)
    pj = projections(ctx, week, list(cbm["gsis_id"]))
    cbm = cbm.merge(pj, on="gsis_id", how="left")
    cbm = cbm.sort_values(["is_starter", "proj_points"], ascending=[False, False], na_position="last").head(n)
    corner_ids = sorted({x for c in ("lcb_gsis_id", "rcb_gsis_id", "nb_gsis_id") for x in cbm[c].dropna()})
    corners = _corners(ctx.season, corner_ids)
    faced = query(f"select {FACED_COLS} from analytics.mart_receiver_vs_cb where season = %s and receiver_gsis_id = any(%s) "
                  "order by defense, defender_snap_share desc nulls last, targets desc", (ctx.season, list(cbm["gsis_id"])))
    faced_by = _grouped(faced, "receiver_gsis_id")
    # ---- IP-5 (Wave I-P): the "best corners" split (his points per game against shutdown corners against the rest) is
    # gone. It ranked past weeks by the season to date (look-ahead: IO-1); rebuilt as-of (``context_record.cb_rank_asof``)
    # it would describe 3 games against top-quarter corners for the median receiver (6 at the 90th percentile, 9 at most:
    # 184 receivers, 2025 + 2026 weeks 1-4), a mean with a 95 % interval of about ±8 points, beside a call graded on
    # 2,190 receiver-games as no measurable effect. ``cover_split`` stays in the answer, always null.
    split: dict = {}
    # ---- end IP-5
    page = decorate(cbm, ctx)
    out = []
    # ---- IF-3: the corners now, for every defense on the page at once; this league's ranks (as on Compare)
    pers = cards.corner_personnel(set(cbm.loc[cbm["position"] == "WR", "opponent"].dropna()), ctx.season, int(week))
    dvp_l, memo_l = league_dvp(ctx, ctx.season), {}
    # ---- end IF-3
    for r in _records(page):
        r["line"] = links(M.cb_line(r))
        r["lean"] = M.lean_text(r) if r["call_status"] != "tight end" else None
        r["corners"] = [corners[i] | {"depth_position": side, "listed_name": r.get(f"{s}_name")}
                        for s, side in (("lcb", "Left"), ("rcb", "Right"), ("nb", "Slot"))
                        for i in [r.get(f"{s}_gsis_id")] if isinstance(i, str) and i in corners]
        r["faced"] = faced_by.get(r["gsis_id"], [])
        r["cover_split"] = split.get(r["gsis_id"])
        r.update(cb_meaning(r))                                  # ---- IB-3: the tone, the certainty, the rank in words
        # ---- IF-3: the defense's history next to its corners now (one corner read for every defense on the page)
        r["matchup_evidence"] = (matchup_evidence(ctx, r["gsis_id"], int(week), dvp=dvp_l, head=r, personnel=pers,
                                                  game=(r.get("opponent"), r.get("is_home")), memo=memo_l)
                                 if r.get("position") == "WR" and isinstance(r.get("opponent"), str) else None)
        out.append(r)
    st_rows = [r for r in out if r["is_starter"]]
    n_cb = next((int(r["cb_n_ranked"]) for r in st_rows if r.get("cb_n_ranked") is not None and not pd.isna(r["cb_n_ranked"])), None)
    caption = ("Likely across from him = the outside corner on the side more of his targets go: a lean, not an assignment "
               "(nobody publishes who covers whom). "
               + (f"#1 of {n_cb} = the starting corner hardest to throw on since the start of {ctx.season - 1}; shutdown = "
                  "the top quarter, target = the bottom quarter." if n_cb else ""))
    return {**ctx.meta(), "team": team, "matchups": out, "summary": [r["line"] for r in st_rows], "caption": caption,
            "rank_note": RANK_NOTE, "howto": CB_HOWTO}                                          # ---- IB-3


# ------------------------------------------------------------------------------ /api/players
POSITION_COLUMNS = {   # app/pages/9_Players.py
    "QB": ["attempts", "completions", "completion_rate", "passing_yards", "yards_per_attempt", "passing_tds",
           "passing_interceptions", "sacks_suffered", "dropbacks", "scrambles", "carries", "rushing_yards", "rushing_tds"],
    "RB": ["carries", "carry_share", "red_zone_carry_share", "rushing_yards", "yards_per_carry", "rushing_tds", "targets", "target_share",
           "first_read_target_share", "route_participation", "tprr_proxy", "receptions", "receiving_yards", "receiving_tds", "avg_offense_snap_pct"],
    "WR": ["targets", "target_share", "first_read_target_share", "air_yards_share", "adot", "route_participation", "tprr_proxy", "yprr_proxy",
           "red_zone_target_share", "receptions", "catch_rate", "receiving_yards", "yards_per_target", "yac_per_reception", "receiving_tds", "avg_offense_snap_pct"],
    "TE": ["targets", "target_share", "first_read_target_share", "air_yards_share", "adot", "route_participation", "tprr_proxy", "yprr_proxy",
           "red_zone_target_share", "receptions", "catch_rate", "receiving_yards", "yards_per_target", "receiving_tds", "avg_offense_snap_pct"],
    "K": ["fg_att", "fg_made", "fg_pct", "fg_made_under_40", "fg_made_40_49", "fg_made_50p", "fg_long", "pat_att", "pat_made"],
}
PLAYERS_HOWTO = (
    "- Season totals for every player at a position, ranked by fantasy points in this league's scoring. Use it to compare "
    "anyone with anyone, this year or past years.\n"
    "- **Target %**, **Carry %** and **Air-yard %** are his share of his *team's* targets, carries and downfield throws in the games "
    "he played: a player who missed games is not marked down for it.\n"
    "- **1st-read share** (2022 on) is how often he is the quarterback's first look. **Route %** is how often he is on the field when "
    "the quarterback drops back to pass; **TPRR / YPRR** are targets and yards per route. Those three are estimates from completed "
    "seasons and run a little low. **Snap %** counts every play, runs included.\n"
    "- A blank cell means the number could not be worked out (no targets, no snaps recorded, a season before charting), never zero.")


def _league_points_season(ctx: Ctx, season: int, season_type: str) -> pd.DataFrame:
    """gsis_id -> points, ppg, games (this league's scoring) for a regular season (mart_league_player_season's numbers)
    or the playoffs (the same arithmetic over the POST game rows)."""
    if season_type == "REG":
        return league_season(ctx, season)[["gsis_id", "points", "ppg", "expected_per_game", "diff_per_game", "position_rank_ppg"]]
    g = league_games(ctx, season)
    st = R.season_table(g[g["season_type"] == season_type])
    return st[["gsis_id", "points", "ppg", "expected_per_game", "diff_per_game", "position_rank_ppg"]]


def players(league_id: str, *, season: int | None = None, position: str | None = None, sort: str | None = None,
            dir: str | None = None, limit: int | None = None, offset: int = 0, q: str | None = None,
            season_type: str = "REG", min_games: int = 1, source: str | None = None,
            window: str | None = None, basis: str | None = None, weeks: str | None = None, who: str | None = None,
            team: int | None = None, nfl: str | None = None) -> dict:            # ---- II-3: the Stats frame's params
    ctx = context(league_id, source)
    season = int(season or ctx.season)
    st = (season_type or "REG").upper()
    if st not in ("REG", "POST"):
        raise BadRequest("season_type is REG or POST")
    # ---- II-3: a window → the Stats Explorer's frame (api/league_lab_api/stats.py); none → the season table as before
    if window is not None:
        return stats_frame(ctx, season=season, season_type=st, position=position, window=window, basis=basis, weeks=weeks,
                           who=who, team=team, nfl=nfl, q=q, min_games=min_games, sort=sort, dir=dir, limit=limit,
                           offset=offset)
    # ---- end II-3
    pos = _positions(position, POSITIONS)
    cols = list(dict.fromkeys(c for p in pos for c in POSITION_COLUMNS[p]))
    df = query(f"""select gsis_id, player_name, position, teams, games_played, {', '.join(cols)},
                          points_current_scoring as points_current_scoring_ref,
                          points_current_scoring_per_game as points_current_scoring_per_game_ref
                   from analytics.mart_player_season
                   where position = any(%s) and season = %s and season_type = %s and games_played >= %s""",
               (pos, season, st, int(min_games or 1)))
    df = df.merge(_league_points_season(ctx, season, st), on="gsis_id", how="left")
    if q and len(q.strip()) >= 2:
        df = df[df["player_name"].map(_norm).str.contains(_norm(q), regex=False)]
    total = int(len(df))
    off = max(0, int(offset or 0))
    df = _sort(df, sort, dir, "points").iloc[off: off + _limit(limit)]
    page = decorate(df, ctx)
    return {**ctx.meta(), "season": season, "season_type": st, "positions": pos, "columns": cols,
            "total": total, "offset": off, "players": _records(page), "howto": PLAYERS_HOWTO,
            "scoring_note": REF_NOTE.format(ref=reference_name()),
            "catalogue": (cat := ST.catalogue(season)), "presets": ST.presets(cat),          # ---- II-3 (additive)
            "groups": ST.GROUPS}                                                             # ---- IM-1


# ---- II-3: the Stats Explorer's frame (the fifth review § 4; docs/METRICS.md § "The Stats Explorer") ------------------
STATS_HOWTO = (
    "- **One row per player over the window you pick**: the season, his last 3 or 5 *games played*, the last 3 or 5 "
    "*calendar weeks* (a bye or a missed game leaves fewer games: **G** says how many), or a week range.\n"
    "- **Per game** divides the window's total by the games he played in it; shares and rates keep their own "
    "denominators (target share = his targets / his team's targets in the games he played).\n"
    "- A share over several games is the summed numerator over the summed denominator, never an average of weekly "
    "percentages.\n"
    "- A dash means the number cannot be worked out here (no targets, a season without charting, routes in season); "
    "hover it for the reason. Never zero.")


def stats_frame(ctx: Ctx, *, season: int, season_type: str, position: str | None, window: str, basis: str | None,
                weeks: str | None, who: str | None, team: int | None, nfl: str | None, q: str | None, min_games: int,
                sort: str | None, dir: str | None, limit: int | None, offset: int) -> dict:
    w = (window or "season").lower()
    if w not in ST.WINDOWS:
        raise BadRequest(f"window is one of {', '.join(ST.WINDOWS)}")
    b = (basis or "games").lower()
    if b not in ST.BASES:
        raise BadRequest("basis is games or weeks")
    wk = ST.parse_weeks(weeks)
    if w == "weeks" and wk is None:
        raise BadRequest("weeks is a range like 2-4 (calendar weeks)")
    wh = (who or "all").lower()
    if wh not in ("all", "mine", "fa", "others", "rostered"):
        raise BadRequest("who is all, mine, fa, others or rostered")
    pos = _positions(position, SKILL)
    rows = ST.season_rows(season, season_type)
    frame, desc = ST.window_rows(rows, w, b, wk)
    cat = ST.catalogue(season, rows)
    mine = frame[frame["position"].isin(SKILL)] if not frame.empty else frame
    agg = ST.aggregate_window(mine, (season, season_type, w, b, wk, id(rows), len(mine)))     # IM-1: cached per window
    if not agg.empty:
        agg = agg[agg["position"].isin(pos)]
        lg = league_games(ctx, season, None if len(agg) > 200 else list(agg["gsis_id"]))
        lg = lg[lg["season_type"] == season_type]
        agg = agg.merge(ST.points(lg, mine[mine["gsis_id"].isin(agg["gsis_id"])], ctx.scoring), on="gsis_id",
                        how="left")                                                    # IM-1: + the league's scoring
        agg = agg[agg["games"] >= max(0, int(min_games if min_games is not None else 1))]
    if agg.empty:
        agg = pd.DataFrame(columns=["gsis_id", "player_name", "position", "games"])
    if q and len(q.strip()) >= 2:
        agg = agg[agg["player_name"].map(_norm).str.contains(_norm(q), regex=False)]
    df = decorate(agg.drop(columns=[c for c in ("team",) if c in agg]), ctx)
    df = ST.owner_filter(df, wh, team)
    if nfl:
        df = df[df["team"].fillna("").str.upper() == nfl.strip().upper()]
    total = int(len(df))
    off = max(0, int(offset or 0))
    n = max(1, min(int(limit if limit is not None else ST.STATS_LIMIT), ST.STATS_LIMIT))
    default = next((p["sort"] for p in ST.PRESETS if p["positions"] == pos), "points")
    page = _sort(df, sort, dir, default).iloc[off: off + n]
    page = page[[c for c in ST.fields(pos) if c in page.columns]]
    return {**ctx.meta(), "season": season, "season_type": season_type, "positions": pos, "window": desc,
            "who": wh, "team": team, "nfl": nfl, "min_games": min_games, "total": total, "offset": off,
            "players": _records(page), "catalogue": cat, "presets": ST.presets(cat), "groups": ST.GROUPS,  # IM-1
            "howto": STATS_HOWTO}
# ---- end II-3


# ------------------------------------------------------------------------------ /api/receivers
RECEIVER_GAME_COLS = ("gsis_id, player_name, position, week, team, opponent_team, played, offense_snap_pct, snaps_known, targets, "
                      "team_targets, receptions, receiving_yards, receiving_air_yards, team_air_yards, receiving_yards_after_catch, "
                      "receiving_tds, target_share, air_yards_share, adot, points_current_scoring, charted_targets, "
                      "first_read_targets, designed_targets, checkdown_targets, team_first_read_targets, team_charted_targets, "
                      "routes_proxy, team_dropbacks_with_participation, game_id")
CONTEXTS = ("half", "score_state", "down_distance", "field_zone", "qb")
CONTEXT_ORDER = {"half": ["H1", "H2", "OT"], "score_state": ["trailing_9plus", "trailing_1_8", "tied", "leading_1_8", "leading_9plus"],
                 "down_distance": ["1st", "2nd_short", "2nd_medium", "2nd_long", "3rd_4th_short", "3rd_4th_medium", "3rd_4th_long"],
                 "field_zone": ["own_half", "opp_half", "red_zone_11_20", "inside_10"]}
CONTEXT_WORDS = {"trailing_9plus": "Trailing 9+", "trailing_1_8": "Trailing 1–8", "tied": "Tied", "leading_1_8": "Leading 1–8",
                 "leading_9plus": "Leading 9+", "2nd_short": "2nd & short (≤3)", "2nd_medium": "2nd & medium (4–6)",
                 "2nd_long": "2nd & long (7+)", "3rd_4th_short": "3rd/4th & short (≤3)", "3rd_4th_medium": "3rd/4th & medium (4–6)",
                 "3rd_4th_long": "3rd/4th & long (7+)", "own_half": "Own half", "opp_half": "Opp. half (21–50)",
                 "red_zone_11_20": "Red zone (11–20)", "inside_10": "Inside the 10", "H1": "1st half", "H2": "2nd half",
                 "OT": "Overtime", "1st": "1st down"}
YS_METRICS = ["target_share", "targets_per_game", "air_yards_share", "adot", "yac_per_reception", "avg_offense_snap_pct",
              "first_read_target_share", "route_participation", "tprr_proxy", "yprr_proxy"]


def _div(a, b):
    a, b = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    return a / b.where(b != 0)


def summarize(games: pd.DataFrame) -> pd.DataFrame:
    """app/pages/10_Receivers.py's summarize(): sum numerators and denominators over the same games, then divide;
    + first reads and the routes proxy the same way; `points` in this league's scoring, `points_ref` the reference's."""
    df = games.assign(_snap=games["offense_snap_pct"].where(games["snaps_known"].fillna(False).astype(bool)),
                      _played=games["played"].fillna(False).astype(bool))
    num = ["targets", "team_targets", "receptions", "receiving_yards", "receiving_air_yards", "team_air_yards",
           "receiving_yards_after_catch", "receiving_tds", "points", "points_current_scoring", "charted_targets",
           "first_read_targets", "designed_targets", "checkdown_targets"]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    p = df[df["_played"]]
    g = df.groupby("gsis_id")
    out = pd.DataFrame({
        "games": g["_played"].sum(),
        **{c: g[c].sum(min_count=1) for c in ("targets", "team_targets", "receptions", "receiving_yards", "receiving_air_yards",
                                              "team_air_yards", "receiving_tds", "charted_targets", "first_read_targets",
                                              "designed_targets", "checkdown_targets")},
        "yac": g["receiving_yards_after_catch"].sum(min_count=1),
        "points": g["points"].sum(min_count=1),
        "points_ref": g["points_current_scoring"].sum(min_count=1),
        "snap_pct": g["_snap"].mean(),
        "team_first_read_targets": p.groupby("gsis_id")["team_first_read_targets"].sum(min_count=1),
        "routes_proxy": pd.to_numeric(df["routes_proxy"], errors="coerce").groupby(df["gsis_id"]).sum(min_count=1),
        "team_dropbacks_with_participation": pd.to_numeric(df["team_dropbacks_with_participation"].where(df["routes_proxy"].notna()),
                                                           errors="coerce").groupby(df["gsis_id"]).sum(min_count=1),
    })
    out["target_share"] = _div(out["targets"], out["team_targets"])
    out["air_yards_share"] = _div(out["receiving_air_yards"], out["team_air_yards"])
    out["adot"] = _div(out["receiving_air_yards"], out["targets"])
    out["yac_per_rec"] = _div(out["yac"], out["receptions"])
    out["targets_per_game"] = _div(out["targets"], out["games"])
    out["points_per_game"] = _div(out["points"], out["games"])
    out["points_per_game_ref"] = _div(out["points_ref"], out["games"])
    out["first_read_target_share"] = _div(out["first_read_targets"], out["team_first_read_targets"])
    out["first_read_rate_of_targets"] = _div(out["first_read_targets"], out["charted_targets"])
    out["route_participation"] = _div(out["routes_proxy"], out["team_dropbacks_with_participation"])
    out["tprr_proxy"] = _div(g["targets"].sum().where(out["routes_proxy"].notna()), out["routes_proxy"])
    out["yprr_proxy"] = _div(g["receiving_yards"].sum().where(out["routes_proxy"].notna()), out["routes_proxy"])
    return out.reset_index()


def _yardsticks(season: int, season_type: str) -> dict:
    ys = query(f"""select position, games_played, points_current_scoring_per_game as ppg, {', '.join(YS_METRICS)}
                   from analytics.mart_player_season where season = %s and season_type = %s and position in ('WR', 'TE')
                   and games_played > 0""", (season, season_type))
    if ys.empty:
        return {}
    ys = ys[ys["games_played"] >= max(1, int(ys["games_played"].max()) // 2)]
    top = ys.sort_values("ppg", ascending=False).groupby("position").head(12)
    return {p: {m: (None if pd.isna(v) else float(v)) for m, v in t[YS_METRICS].apply(pd.to_numeric, errors="coerce").mean().items()}
            for p, t in top.groupby("position")}


def _pct(v, fallback: str) -> str:
    return f"{v:.0%}" if v is not None else fallback


def receivers_howto(season: int, ys: dict) -> str:
    wr, te = ys.get("WR", {}), ys.get("TE", {})
    label = f"the {season} top-12"
    return (
        "- **Start the receiver the offense is built around, not last week's box score.** The yardsticks are what "
        f"{label} at each position average (the 12 with the most points per game, one scale for every league).\n"
        "- **Target %** (his share of his team's targets). Why it matters: targets turn into points more reliably than anything "
        "else, and a share holds when the team throws more or less. Yardstick: the top-12 wide receivers average "
        f"{_pct(wr.get('target_share'), '28%')}, tight ends {_pct(te.get('target_share'), '21%')}; under 15% is a depth piece.\n"
        "- **Targets/G** is the same thing as a count. Why it matters: it is the volume behind the share. Yardstick: "
        f"{format(wr.get('targets_per_game') or 9.2, '.1f')} for the top-12 wide receivers, "
        f"{format(te.get('targets_per_game') or 6.3, '.1f')} for tight ends.\n"
        "- **Air-yard %** (his share of the yards his team's throws travel in the air). Why it matters: it says who gets the deep, "
        f"valuable targets, the ones that become long touchdowns. Yardstick: {_pct(wr.get('air_yards_share'), '35%')} for the "
        "top-12 wide receivers; 30%+ is the main downfield option.\n"
        "- **aDOT** (how far downfield his targets travel, on average) is a style, not a grade. Why it matters: 12+ yards means big "
        "weeks and duds; under 8 means short, steady catches (worth more in full PPR). **YAC/Rec** (yards after the catch per "
        "catch): 5+ means he makes yards on his own.\n"
        "- **Snap %** (share of plays he is on the field) is the ceiling on everything else. Why it matters: he cannot be targeted "
        "from the sideline. 80%+ is a full-time starter. On the field 95% of the time but only 12% of the targets means he is out "
        "there, not in the plan: don't count on him.\n"
        "- **First-read share**: when the quarterback throws to the receiver he looked at first, how often it is this player — the "
        f"strongest usage sign we have. Yardstick: {label} wide receivers average {_pct(wr.get('first_read_target_share'), '35%')}, "
        f"tight ends {_pct(te.get('first_read_target_share'), '22%')}; above 30% is the offense's first choice. Charting by FTN "
        "Data (CC BY-SA 4.0) starts in 2022; earlier seasons show blank, not zero.\n"
        "- **Route %** is how often he is on the field when the quarterback drops back to pass; **TPRR** (targets per route) above "
        "25% is WR1 territory; **YPRR** (yards per route) 2.0+ is a top-24 receiver. These are estimates that run 10–15% low, "
        "published after the season: the current season is blank until then.\n"
        "- **Recent form**: last 3 well above the season number is the earliest sign of a bigger role you can get from the box "
        "score; last 3 well below it is the warning sign.\n"
        "- **Context splits**: his share of the team's targets by half, score, down, field zone or quarterback. A share that jumps "
        "only when his team trails by 9+ is garbage time; one that holds when leading is in the plan whatever the score.")


def receivers(league_id: str, *, season: int | None = None, limit: int | None = None, season_type: str = "REG",
              weeks: str | None = None, players: str | None = None, context_type: str = "half",
              source: str | None = None) -> dict:
    ctx = context(league_id, source)
    season = int(season or ctx.season)
    st = (season_type or "REG").upper()
    if st not in ("REG", "POST"):
        raise BadRequest("season_type is REG or POST")
    lo, hi = (19, 22) if st == "POST" else (1, 18)
    if weeks:
        m = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*", weeks)
        if not m:
            raise BadRequest("weeks is a range like 1-6")
        lo, hi = int(m.group(1)), int(m.group(2))
    ctype = (context_type or "half").lower()
    if ctype not in (*CONTEXTS, "none"):
        raise BadRequest(f"context is one of {', '.join(CONTEXTS)} or none")
    n = _limit(limit)
    if players:
        ids = [x.strip() for x in players.split(",") if x.strip()][:MAX_LIMIT]
    else:   # the page's candidates: receivers with 10+ targets, most targets first
        cand = query("""select gsis_id from analytics.mart_player_season where season = %s and season_type = %s
                        and position in ('WR', 'TE', 'RB') and targets >= 10 order by targets desc, gsis_id""", (season, st))
        ids = list(cand["gsis_id"].head(n))
    if not ids:
        return {**ctx.meta(), "season": season, "season_type": st, "weeks": [lo, hi], "receivers": [],
                "yardsticks": {}, "howto": receivers_howto(season, {})}
    games = query(f"select {RECEIVER_GAME_COLS} from analytics.fct_player_game where season = %s and season_type = %s "
                  "and gsis_id = any(%s) and week between %s and %s order by gsis_id, week", (season, st, ids, lo, hi))
    lp = league_games(ctx, season, ids)[["gsis_id", "game_id", "points"]]
    games = games.merge(lp, on=["gsis_id", "game_id"], how="left")
    summ = summarize(games) if not games.empty else pd.DataFrame(columns=["gsis_id"])
    rf = query("""select gsis_id, week, target_share_l3, target_share_l5, target_share_std, targets_l3, team_targets_l3,
                         snap_pct_l3, points_per_game_l3 as points_per_game_l3_ref, points_per_game_std as points_per_game_std_ref
                  from analytics.mart_player_recent_form where season = %s and season_type = %s and gsis_id = any(%s)
                    and week between %s and %s""", (season, st, ids, lo, hi))
    latest = rf.sort_values("week").groupby("gsis_id").tail(1).rename(columns={"week": "form_week"}) if not rf.empty else rf
    # the league's points per game over his last 3 appearances in the window (mart_player_recent_form's rule)
    pl = games[games["played"].fillna(False).astype(bool)].sort_values("week")
    l3 = pl.groupby("gsis_id").tail(3).groupby("gsis_id")["points"].mean().round(2).rename("points_per_game_l3")
    df = pd.DataFrame({"gsis_id": ids}).merge(summ, on="gsis_id", how="left").merge(latest, on="gsis_id", how="left")
    df = df.merge(l3.reset_index(), on="gsis_id", how="left")
    df = decorate(df, ctx)
    ctx_rows: dict[str, list] = {}
    if ctype != "none":
        cx = query("""select c.gsis_id, c.context_type,
                             case when c.context_type = 'qb' then coalesce(q.player_name, c.bucket) else c.bucket end as bucket,
                             c.bucket as bucket_key, c.games, c.targets, c.team_targets, c.target_share, c.first_read_targets,
                             c.team_first_read_targets, c.first_read_target_share, c.receptions, c.receiving_yards,
                             c.yards_per_target, c.adot, c.carries, c.team_carries, c.carry_share, c.routes_proxy, c.team_dropbacks,
                             c.route_participation, c.tprr_proxy, c.yprr_proxy
                      from analytics.mart_player_context c
                      left join analytics.dim_player q on q.gsis_id = c.bucket and c.context_type = 'qb'
                      where c.season = %s and c.season_type = %s and c.gsis_id = any(%s) and c.context_type = %s""",
                   (season, st, ids, ctype))
        if not cx.empty:
            order = {b: i for i, b in enumerate(CONTEXT_ORDER.get(ctype, []))}
            cx = cx.assign(_o=cx["bucket_key"].map(order)).sort_values(["gsis_id", "_o", "bucket"]).drop(columns="_o")
            cx["bucket_label"] = cx["bucket"].map(lambda b: CONTEXT_WORDS.get(b, b))
            ctx_rows = _grouped(cx, "gsis_id")
    out = []
    for r in _records(df):
        r["context"] = ctx_rows.get(r["gsis_id"], [])
        out.append(r)
    ys = _yardsticks(season, st)
    return {**ctx.meta(), "season": season, "season_type": st, "weeks": [lo, hi], "context_type": ctype,
            "receivers": out, "yardsticks": ys, "howto": receivers_howto(season, ys),
            "scoring_note": REF_NOTE.format(ref=reference_name())}


# ------------------------------------------------------------------------------ /api/player/{gsis}/games
GAME_STAT_COLS = ["completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered", "carries",
                  "rushing_yards", "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds", "receiving_air_yards",
                  "receiving_yards_after_catch", "fumbles_lost_total", "target_share", "carry_share", "air_yards_share", "adot",
                  "first_read_target_share", "red_zone_targets", "red_zone_carries", "offense_snaps", "offense_snap_pct",
                  "fg_made", "fg_att", "fg_long", "pat_made", "pat_att"]


def player_header(gsis: str, ctx: Ctx) -> dict:
    d = decorate(pd.DataFrame({"gsis_id": [gsis]}), ctx)
    r = _records(d)[0]
    if not isinstance(r.get("player_name"), str):
        raise NotFound(f"No player with id `{gsis}`.")
    return {k: r.get(k) for k in ("gsis_id", "player_name", "position", "team", "headshot_url", "rostered_by_roster_id",
                                  "rostered_by_team")}


def player_games(league_id: str, gsis: str, *, season: int | None = None, season_type: str | None = None,
                 source: str | None = None) -> dict:
    ctx = context(league_id, source)
    head = player_header(gsis, ctx)
    season = int(season or ctx.season)
    st = (season_type or "ALL").upper()
    if st not in ("REG", "POST", "ALL"):
        raise BadRequest("season_type is REG, POST or ALL")
    g = query(f"""select p.gsis_id, p.game_id, p.season, p.season_type, p.week, p.game_date, p.team, p.opponent_team as opponent,
                         p.is_home, p.played, p.roster_status, {', '.join('p.' + c for c in GAME_STAT_COLS)},
                         p.points_current_scoring as points_ref, e.points_expected as expected_points_ref
                  from analytics.fct_player_game p
                  left join analytics.mart_player_expected_points e on e.gsis_id = p.gsis_id and e.game_id = p.game_id
                  where p.gsis_id = %s and p.season = %s and (%s = 'ALL' or p.season_type = %s)
                  order by p.season_type desc, p.week""", (gsis, season, st, st))
    lp = league_games(ctx, season, [gsis])[["game_id", "points", "points_expected"]].rename(
        columns={"points_expected": "expected_points"})
    g = g.merge(lp, on="game_id", how="left").drop(columns=["gsis_id"])
    return {**ctx.meta(), **{"player": head}, "season": season, "season_type": st, "games": _records(g),
            "scoring_note": REF_NOTE.format(ref=reference_name())}


# ------------------------------------------------------------------------------ /api/compare
SEASON_PG_COLS = ["games_played", "targets_per_game", "carries_per_game", "dropbacks_per_game", "catch_rate", "yards_per_target",
                  "yards_per_carry", "adot", "completion_rate", "yards_per_attempt", "passing_yards", "passing_tds", "rushing_yards",
                  "rushing_tds", "receiving_yards", "receiving_tds", "receptions", "targets", "carries", "attempts"]
USAGE_COLS = ["target_share", "carry_share", "air_yards_share", "first_read_target_share", "avg_offense_snap_pct",
              "red_zone_target_share", "red_zone_carry_share", "route_participation"]
FORM_COLS = ["target_share_l3", "carry_share_l3", "air_yards_share_l3", "snap_pct_l3", "first_read_share_l3", "targets_l3",
             "carries_l3", "games_l3"]
COMPARE_HOWTO = (
    "- **Use it for a close call**: pick any two players; the same rows on both sides.\n"
    "- **Projection** is the same number as the lineup cards and the player card. **Floor – ceiling** is the range 8 weeks in "
    "10 land in: take the higher floor when you only need a steady game, the higher ceiling when you need a big one.\n"
    "- **Targets / carries allowed** say whether a defense lets the position get the ball a lot (volume). **Yards per target or "
    "carry** and **touchdown rate** say whether it gives up big plays.\n"
    "- **Vs the offenses faced**: points it allowed beyond what the same offenses score against everyone else, shrunk toward "
    "zero early in the season. \"The matchup leans\" uses this rank: 6 or more places apart, else the matchups are about even.\n"
    "- Matchups move a projection less than role does: when the lineup and the matchup disagree, go with the lineup.")


def _side(ctx: Ctx, gsis: str, dvp: pd.DataFrame, pc=None) -> dict:
    from .player import SCHED_SQL
    head = player_header(gsis, ctx)
    pos, team = head["position"], head["team"]
    week = ctx.week
    out: dict = {**head}
    # this week's projection + range, the card's numbers
    if ctx.house:
        pj = projections(ctx, week, [gsis])
        out["projection"] = _records(pj.drop(columns="gsis_id"))[0] if not pj.empty else None
    else:
        pr = pc.projection(gsis, pos, week) if pc is not None and week is not None else pd.DataFrame()
        out["projection"] = ({k: pr.iloc[0][k] for k in ("proj_points", "p10", "p25", "p75", "p90")} if not pr.empty else None)
    # season per game, usage (NFL-wide), the league's points per game
    s = query(f"""select {', '.join(SEASON_PG_COLS + USAGE_COLS)}, points_current_scoring_per_game as ppg_ref
                  from analytics.mart_player_season where gsis_id = %s and season = %s and season_type = 'REG'""", (gsis, ctx.season))
    srow = _records(s)[0] if not s.empty else {}
    ls = league_season(ctx, ctx.season)
    lrow = _records(ls[ls["gsis_id"] == gsis])
    lrow = lrow[0] if lrow else {}
    out["season"] = {**{k: srow.get(k) for k in SEASON_PG_COLS}, "ppg": lrow.get("ppg"), "xppg": lrow.get("expected_per_game"),
                     "gap": lrow.get("diff_per_game"), "position_rank_ppg": lrow.get("position_rank_ppg"),
                     "ppg_ref": srow.get("ppg_ref")}
    out["usage"] = {k: srow.get(k) for k in USAGE_COLS}
    f = query(f"""select {', '.join(FORM_COLS)}, points_per_game_l3 as points_per_game_l3_ref from analytics.mart_player_recent_form
                  where gsis_id = %s and season = %s and season_type = 'REG' order by week desc limit 1""", (gsis, ctx.season))
    frow = _records(f)[0] if not f.empty else {}
    out["last3"] = {**{k: frow.get(k) for k in FORM_COLS}, "points_per_game_l3": lrow.get("points_per_game_l3"),
                    "points_per_game_l3_ref": frow.get("points_per_game_l3_ref")}
    # rest of season (the card's block)
    if ctx.house:
        rr = (query(f"select {ROS.ROS_COLUMNS} from analytics.mart_player_ros_projection where league_id = %s and gsis_id = %s",
                    (ctx.league_id, gsis)) if not missing_relations((ROS.RELATION,)) else pd.DataFrame())
    else:
        rr = pc.ros(gsis, pos) if pc is not None and week is not None else pd.DataFrame()
    out["ros"] = ros_card(rr.iloc[0]) if rr is not None and not rr.empty else None
    # the next 4 opponents with their rank vs his position (league scoring; the card's reference rank as `_ref`)
    sched = query(SCHED_SQL, (team, team, team, pos, ctx.season, team)) if isinstance(team, str) and team else pd.DataFrame()
    nxt = []
    rk = dvp[dvp["position"] == pos].set_index("defense")["rank_std"] if not dvp.empty else pd.Series(dtype=float)
    if week is not None and not sched.empty:
        last = max(18, int(sched["week"].max()))
        for w in range(week, min(week + 4, last + 1)):
            gw = sched[sched["week"] == w]
            if gw.empty:
                nxt.append({"week": w, "bye": True, "opponent": None, "is_home": None, "opp_rank": None, "opp_rank_ref": None})
            else:
                gg = gw.iloc[0]
                nxt.append({"week": w, "bye": False, "opponent": gg["opponent"], "is_home": bool(gg["is_home"]),
                            "kickoff_at": gg["kickoff_at"], "opp_rank": rk.get(gg["opponent"]), "opp_rank_ref": gg["opp_rank"]})
    out["next4"] = nxt
    # the comparison table's inputs: this week's opponent's profile vs his position (app/lib/matchups.py)
    opp = nxt[0] if nxt and not nxt[0]["bye"] else None
    prof = {}
    if opp is not None and week is not None and not missing_relations(("mart_defense_position_profile",)):
        p = query("""select * from analytics.mart_defense_position_profile where season = %s and week = %s and defense = %s
                     and position = %s""", (ctx.season, int(week), opp["opponent"], pos))
        prof = _records(p)[0] if not p.empty else {}
    proj = out["projection"] or {}
    out["_cmp"] = {"gsis_id": gsis, "player_name": head["player_name"], "position": pos,
                   "opponent": opp["opponent"] if opp else None, "is_home": opp["is_home"] if opp else None,
                   "proj_points": proj.get("proj_points"), "p10": proj.get("p10"), "p90": proj.get("p90"), **prof}
    out["matchup"] = ({k: prof.get(k) for k in ("games", "opps_allowed_pg", "targets_allowed_pg", "carries_allowed_pg",
                                                "yards_per_opp_allowed", "td_rate_allowed", "gives_up", "rank_opportunity",
                                                "rank_efficiency", "rank_td_rate", "rank_targets", "rank_carries", "n_defenses")}
                      | {"points_allowed_pg_ref": prof.get("points_allowed_pg"), "rank_points_ref": prof.get("rank_points"),
                         "adjusted_points_pg_ref": prof.get("adjusted_points_pg"), "rank_adjusted_ref": prof.get("rank_adjusted")}
                      if prof else None)
    return out


# ---- IF-3 (Wave I-F, the decision-quality review § Priority 1): the matchup evidence object. Three parts kept apart —
# `history` (the defense's rank against the position as computed: games, scoring, period, not adjusted for the offenses
# it faced), `changed` (its corners now vs the corners that rank was earned with: `cards.corner_personnel`, the overlay's
# status with its source and date), `implication` — plus `forecast_treatment`, said honestly: the projection's opponent
# inputs are the defense's points allowed to the position and the betting lines (FORECAST_OPPONENT_FEATURES, checked
# against league_lab.projections.BASE_FEATURES by api/tests/test_if3.py); nothing in it says who plays corner, so a corner
# change is "contextual only; not in the forecast". No number moves: the evidence only stops an unrepresentative rank
# from settling a close call (cards._tiebreak, the compare's verdict). docs/METRICS.md § Matchups "Current personnel".
FORECAST_OPPONENT_FEATURES = ("opp_allowed_std", "opp_allowed_l4", "opp_rank_std", "f_opp_allowed_diff", "league_allowed_avg")
FORECAST_LINE_FEATURES = ("implied_team_total", "spread_line", "total_line")
FORECAST_WORDS = "contextual only; not in the forecast"
FORECAST_DETAIL = ("The projection's opponent inputs are the points this defense has allowed to the position (the season, "
                   "the last 4 games, its rank) and the betting lines; none of them says who plays corner.")
IMPLICATION_WORDS = {
    "less_representative": "the historical rank is less representative this week: {what}",
    "stands": "the historical rank stands: the same corners",
    "unknown": "unknown: {why}",
    "unchecked": "the historical rank, without a personnel check: corners are checked for receivers only",
}
cards.STATUSES = availability.now          # the cards' corner check reads the overlay (ESPN / Sleeper, with the date)


_PLACES: dict[str, str] = {}


def _place(team: str | None) -> str:
    """'Carolina' (dim_team's name without the nickname; 32 names, kept for the process)."""
    if not isinstance(team, str) or not team:
        return "the defense"
    if not _PLACES:
        t = query("select team_abbr, team_name, team_nick from analytics.dim_team")
        _PLACES.update({r["team_abbr"]: str(r["team_name"]).removesuffix(" " + str(r["team_nick"])).strip() or r["team_abbr"]
                        for r in _records(t)})
    return _PLACES.get(team, team)


def _date_words(iso) -> str | None:
    """'Sep 30' (Eastern) from an overlay timestamp."""
    if not iso:
        return None
    try:
        t = pd.Timestamp(iso)
        t = (t.tz_localize("UTC") if t.tzinfo is None else t).tz_convert("America/New_York")
        return f"{t.strftime('%b')} {t.day}"
    except (ValueError, TypeError):
        return None


def _history(ctx: Ctx, opp: str, pos: str, week: int, dvp: pd.DataFrame, scoring: str | None = None,
             memo: dict | None = None) -> dict:
    """The defense's rank against the position as the card and the compare show it (this league's scoring, raw points
    allowed per game in its games so far) + the opponent-adjusted rank of the profile (reference scoring) beside it."""
    d = dvp[dvp["position"] == pos] if not dvp.empty else dvp
    n = int(d["rank_std"].notna().sum()) if not d.empty else 0
    row = d[d["defense"] == opp] if not d.empty else d
    r = _records(row)[0] if not row.empty else {}
    rank, games, thru = _rank(r.get("rank_std")), _rank(r.get("games")), _rank(r.get("through_week"))
    words = gives_up_words(rank, n)
    out = {"defense": opp, "position": pos, "rank_most": rank, "tough_rank": tough_rank(rank, n), "n": n or None,
           "words": None if words is None else f"{words} points to {cards.POS_PLURAL.get(pos, 'the position')}",
           "games": games, "through_week": thru, "period": f"{ctx.season}, weeks 1–{thru}" if thru else None,
           "points_allowed_pg": _f(r.get("points_allowed_per_game_std")), "scoring": scoring or f"{ctx.league_name} scoring",
           "adjusted": False, "adjusted_words": "not adjusted for the offenses it faced", "adjusted_rank": None}
    if not missing_relations(("mart_defense_position_profile",)):
        key = ("profile", ctx.season, int(week), pos)
        prof = (memo or {}).get(key)
        if prof is None:
            prof = query("""select defense, rank_adjusted, n_defenses from analytics.mart_defense_position_profile
                            where season = %s and week = %s and position = %s""", (ctx.season, int(week), pos))
            if memo is not None:
                memo[key] = prof
        p = prof[prof["defense"] == opp] if not prof.empty else prof
        if not p.empty and _rank(p.iloc[0]["rank_adjusted"]) is not None:
            ra, na = _rank(p.iloc[0]["rank_adjusted"]), _rank(p.iloc[0]["n_defenses"])
            out["adjusted_rank"] = {"rank_most": ra, "n": na, "words": gives_up_words(ra, na),
                                    "scoring": f"{reference_name()} scoring"}
    return out


def matchup_evidence(ctx: Ctx, gsis: str, week: int | None = None, *, dvp: pd.DataFrame | None = None,
                     head: dict | None = None, personnel: dict | None = None, game: tuple | None = None,
                     scoring: str | None = None, memo: dict | None = None) -> dict | None:
    """The matchup evidence for one player's game in `week` (default: the decision week); None without a game (a bye,
    no team, the season over). `dvp` = the ranks the screen shows (default: this league's, as on Compare; the card
    passes the reference mart's with `scoring`); `personnel` = a `cards.corner_personnel` answer already read and
    `game` = (opponent, is_home) already known (Matchups reads every defense at once); `memo` shares reads across rows."""
    week = ctx.week if week is None else int(week)
    if week is None:
        return None
    head = head or player_header(gsis, ctx)
    pos, team = head.get("position"), head.get("team")
    if pos not in ("QB", "RB", "WR", "TE") or not isinstance(team, str) or not team:
        return None
    if game is None:
        g = query(STARTER_GAME_SQL, (ctx.season, int(week), team))
        if g.empty:
            return None
        home = bool(g.iloc[0]["home_team"] == team)
        opp = str(g.iloc[0]["away_team"] if home else g.iloc[0]["home_team"])
    else:
        opp, home = str(game[0]), None if game[1] is None or pd.isna(game[1]) else bool(game[1])
    place = _place(opp)
    hist = _history(ctx, opp, pos, int(week), league_dvp(ctx, ctx.season) if dvp is None else dvp, scoring, memo)
    if pos == "WR":
        p = (personnel if personnel is not None else cards.corner_personnel([opp], ctx.season, int(week))).get(opp) or {
            "kind": "unknown", "why": "no corner data", "regulars": [], "listed": [], "expected": [], "missing": [],
            "depth_chart_at": None}
    else:
        p = {"kind": "not_checked", "regulars": [], "listed": [], "expected": [], "missing": [], "depth_chart_at": None}
    for e in p["expected"]:
        e["rank_words"] = (corner_words(e["rank"], e.get("n_ranked")) if e.get("rank") is not None
                           else "unranked (insufficient snaps)")
    for m in p["missing"]:
        m["date_words"] = _date_words(m.get("as_of"))
    cited = _cite_missing(p["missing"], opp)                                                            # ---- IG-2
    changed_words = _changed_words(p, place)
    kind = {"changed": "less_representative", "same": "stands", "unknown": "unknown"}.get(p["kind"], "unchecked")
    n, k = len(p["regulars"]), len(p["missing"])
    what = ("both starting corners changed" if k == 2 and n == 2 else f"all {n} regular corners changed" if k == n
            else f"{k} of its {n} regular corners changed" if k > 1 else "one of its regular corners changed")
    impl = IMPLICATION_WORDS[kind].format(what=what, why=p.get("why") or "no depth chart")
    implication = {"kind": kind, "words": impl}
    treatment = {"kind": "contextual", "words": FORECAST_WORDS, "detail": FORECAST_DETAIL,
                 "features": list(FORECAST_OPPONENT_FEATURES + FORECAST_LINE_FEATURES)}
    ev = {"gsis_id": gsis, "player_name": head.get("player_name"), "position": pos, "season": ctx.season, "week": int(week),
          "opponent": opp, "opponent_name": place, "is_home": home, "history": hist,
          "changed": {"kind": p["kind"], "depth_chart_at": _iso_ts(p.get("depth_chart_at")), "regulars": p["regulars"],
                      "listed": p["listed"], "missing": p["missing"], "expected": p["expected"], "words": changed_words,
                      "events": cited},                                                                  # ---- IG-2
          "implication": implication, "forecast_treatment": treatment, "matchup_uncertain": kind == "less_representative",
          "caveat": cards.personnel_caveat(p, place)}
    ev["sentences"] = evidence_sentences(ev)
    return ev


# ---- IG-2 (Wave I-G): the event behind each missing regular. The store's newest live availability event of the
# player (his team's events first — events.for_team, the defensive events of the matchup — then his own), the one
# that says he cannot play (his overlay status when there is one): `missing[].event` = events.cite(...) and
# `missing[].url` its source URL (his ESPN page for an ESPN report); `changed.events` lists them. No event (the store
# off, empty, unreachable, a depth-chart change): None, and the overlay's status with its source and date stays.
EVENT_LOOKBACK = timedelta(days=60)


def _cite_missing(missing: list[dict], team: str | None) -> list[dict]:
    from . import availability as AV
    from . import events
    for m in missing:
        m["event"], m["url"] = None, None
    want = [m for m in missing if isinstance(m.get("gsis_id"), str)]
    if not want or not events.enabled():
        return []
    try:
        since = events.clock() - EVENT_LOOKBACK
        evs = [e for e in events.for_team(team or "", since, kinds=("availability",)) if e["live"]]
        found = {e["gsis_id"] for e in evs}
        rest = [m["gsis_id"] for m in want if m["gsis_id"] not in found]
        if rest:
            evs += events.recent(rest, hours=EVENT_LOOKBACK.total_seconds() / 3600, kinds=("availability",))
        out = []
        for m in want:
            mine = [e for e in evs if e["gsis_id"] == m["gsis_id"] and e.get("status") in AV.CANNOT_PLAY]
            ev = next((e for e in mine if m.get("code") and e.get("status") == m.get("code")), None) or next(iter(mine), None)
            if ev is None:
                continue
            m["event"], m["url"] = events.cite(ev), ev.get("source_url")
            out.append({"gsis_id": m["gsis_id"], "name": m.get("name"), **events.cite(ev)})
        return out
    except Exception:  # noqa: BLE001 - the store never fails the evidence: the overlay's status stays
        return []
# ---- end IG-2


def _iso_ts(v) -> str | None:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return pd.Timestamp(v).isoformat()


def _changed_words(p: dict, place: str) -> str | None:
    """'Horn and Jackson are on injured reserve (ESPN, Sep 30); Evans, Lee and Smith-Wade are expected to start, all
    unranked (insufficient snaps)' / 'its regular corners Jackson and Horn are expected to start'."""
    if p["kind"] == "changed":
        src = sorted({f"{m['source']}, {m['date_words']}" if m.get("date_words") else str(m["source"])
                      for m in p["missing"] if m.get("source")})
        out = cards.missing_words(p["missing"]) + (f" ({'; '.join(src)})" if src else "")
        new = [e for e in p["expected"] if e.get("is_new")]
        if new:
            unr = [e for e in new if e.get("rank") is None]
            ranked = [f"{cards.last_name(e['name'])} {e['rank_words']}" for e in new if e.get("rank") is not None]
            tail = (", all unranked (insufficient snaps)" if len(unr) == len(new) and len(new) > 1
                    else ", unranked (insufficient snaps)" if len(unr) == len(new)
                    else " (" + "; ".join(([f"{cards._names(unr)} unranked: insufficient snaps"] if unr else []) + ranked) + ")")
            out += f"; {cards._names(new)} {'is' if len(new) == 1 else 'are'} expected to start{tail}"
        return out
    if p["kind"] == "same":
        return f"its regular corners ({cards._names(p['regulars'])}) are expected to start"
    if p["kind"] == "unknown":
        return f"whether {place}'s corners changed is unknown: {p.get('why') or 'no depth chart'}"
    return None


def evidence_sentences(ev: dict) -> list[str]:
    """The two sentences the screens show (the review's illustrative copy is the model): the history with what changed,
    then the implication with the forecast's treatment."""
    h, c, place = ev["history"], ev["changed"], ev["opponent_name"]
    if h.get("words"):
        bits = [x for x in (h.get("period") and h["period"].split(", ", 1)[-1],
                            f"{h['games']} game{'s' if h['games'] != 1 else ''}" if h.get("games") else None,
                            h.get("scoring"), h.get("adjusted_words")) if x]
        s1 = f"{place} {h['words']} ({', '.join(bits)})"
    else:
        s1 = f"{place} has no games against {cards.POS_PLURAL.get(ev['position'], 'the position')} to rank yet"
    kind = ev["implication"]["kind"]
    if kind == "less_representative":
        s1 += f", but with different corners: {c['words']}."
        what = ev["implication"]["words"].split(": ", 1)[-1]
        s2 = (f"The historical rank is less representative this week ({what}), so treat it cautiously: it does not settle "
              f"a close call. Who plays corner is {FORECAST_WORDS}.")
    elif kind == "stands":
        s1 += f"; {c['words']}."
        s2 = f"The rank stands: the same corners. Who plays corner is {FORECAST_WORDS} (the projection counts the points allowed)."
    elif kind == "unknown":
        s1 += "."
        s2 = f"{c['words'][0].upper()}{c['words'][1:]}; who plays corner is {FORECAST_WORDS}."
    else:
        s1 += "."
        s2 = (f"Who plays for {place}'s defense is checked for receivers (the corners) only; the projection counts the "
              "points it has allowed.")
    return [s1, s2]


def personnel_verdict(verdict: str, evs: list[dict | None]) -> str:
    """The compare's verdict when a side's matchup is less representative: the projection's head stays, the matchup
    lean goes ('Tuten projects 0.22 more (10.02 vs 9.80); the matchup rank does not settle it this week: …')."""
    cav = [e["caveat"] for e in evs if e and e.get("matchup_uncertain") and e.get("caveat")]
    if not cav or verdict.startswith("No projection"):
        return verdict
    return f"{verdict.split('; ', 1)[0]}; the matchup rank does not settle it this week: {'; '.join(cav)}."
# ---- end IF-3


# ---- IR-1 (Wave I-R): Compare knows who cannot play (availability.statuses: the nightly's record + Sleeper + ESPN)
def cards_last(side: dict) -> str:
    """His last name (the verdict's way: "Achane")."""
    from .applib import cards
    n = str(side.get("player_name") or "")
    return (cards.last_name(n) or n) if n else "the other"


def _compare_gate(ctx: Ctx, *pairs: tuple[dict, dict]) -> list[str]:
    """Each side who cannot play this week: no projection (a dash, with his status and why), no rest-of-season block
    when he is out indefinitely; returns the sentences ("Achane is out — on injured reserve (…)")."""
    from league_lab import availability_gate as AG

    from . import availability as AV
    ids = [side.get("gsis_id") for side, _c in pairs if isinstance(side.get("gsis_id"), str)]
    st = AV.statuses(ids, ctx.season, ctx.week) if ctx.week is not None else {}
    out = []
    for side, c in pairs:
        x = st.get(side.get("gsis_id"))
        if not x:
            continue
        x = {**x, "cannot_play": AV.sits(x)}                       # ---- IS-1: a status that rarely plays sits too
        side["availability"] = {k: x.get(k) for k in ("status", "code", "why", "source", "as_of", "cannot_play",
                                                      "out_indefinitely", "week_words", "ros_words")}
        if x.get("cannot_play"):
            side["projection"] = None
            c.update(proj_points=None, p10=None, p90=None)
            if x.get("out_indefinitely"):
                side["ros"] = None
            out.append(AG.out_sentence(cards_last(side), x))
    return out
# ---- end IR-1


def compare(league_id: str, a: str, b: str, *, source: str | None = None) -> dict:
    if not a or not b:
        raise BadRequest("compare needs a=<gsis_id> and b=<gsis_id>")
    ctx = context(league_id, source)
    dvp = league_dvp(ctx, ctx.season)
    pc = None
    if not ctx.house:
        from .ondemand import PlayerContext
        pc = PlayerContext(ctx.league_id)
    sa, sb = _side(ctx, a, dvp, pc), _side(ctx, b, dvp, pc)
    ca, cb = sa.pop("_cmp"), sb.pop("_cmp")
    outs = _compare_gate(ctx, (sa, ca), (sb, cb))                                           # ---- IR-1
    table = M.comparison_rows(ca, cb)
    rows = [{"what": r["What"], "a": r.iloc[1], "b": r.iloc[2]} for _, r in table.iterrows()]
    # ---- IF-3: the matchup evidence on both sides; a less representative rank never leans the verdict
    for s in (sa, sb):
        s["matchup_evidence"] = matchup_evidence(ctx, s["gsis_id"], dvp=dvp, head=s) if ctx.week is not None else None
    verdict = personnel_verdict(M.comparison_verdict(ca, cb), [sa["matchup_evidence"], sb["matchup_evidence"]])
    # ---- end IF-3
    if outs:                                    # ---- IR-1: "He is out" — never a call on a player who cannot play
        other = [x for x in (sa, sb) if not x.get("availability", {}).get("cannot_play")]
        verdict = " ".join(outs) + (f" Start {cards_last(other[0])}." if len(other) == 1 else "")
    return {**ctx.meta(), "a": sa, "b": sb, "verdict": verdict, "table": rows,
            "caption": (f"Week {ctx.week}. The projection decides: it already counts the opponent. The defense rows are "
                        "context: what each opponent allowed to the position in its games before this week, one scale for "
                        "every league; (#1) = gives up the most of 32.") if ctx.week else None,
            "howto": COMPARE_HOWTO, "scoring_note": REF_NOTE.format(ref=reference_name())}


# ------------------------------------------------------------------------------ /api/search for any league (Wave H, H1)
SEARCH_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
SEARCH_LIMIT = 25


def search_on_demand(league_id: str, q: str, *, source: str | None = None) -> list[dict]:
    """`/api/search` for a league the database does not hold: Sleeper's player directory (`sleeper().players()`, cached
    a day) searched by name the way `player.search` searches `mart_player_availability` (letters only, case-blind),
    mapped to gsis ids through `player_id_map`, whose team he is on from the league's rosters now; the same shape.
    Order: players with an NFL team first, then by name (the house search orders by points per game, which a league
    the database has never scored does not have)."""
    ctx = context(league_id, "sleeper" if source is None else source)
    needle = _norm(q)
    if len((q or "").strip()) < 2 or not needle:
        return []
    try:
        players = A.sleeper().players()
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    hits = []
    for sid, p in players.items():
        pos = p.get("position")
        if pos not in SEARCH_POSITIONS:
            continue
        name = p.get("full_name") or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        if pos == "DEF" and not name:
            name = f"{p.get('first_name') or sid} {p.get('last_name') or ''}".strip()
        if needle in _norm(name):
            hits.append((str(sid), name, pos, p.get("team")))
    hits.sort(key=lambda h: (h[3] is None, h[1], h[0]))
    hits = hits[:SEARCH_LIMIT]
    sids = [h[0] for h in hits]
    idm = query("select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)", (sids,)) if sids else None
    gsis_of = dict(zip(idm["sleeper_id"], idm["gsis_id"], strict=False)) if idm is not None and not idm.empty else {}
    owner = {str(p): int(r["roster_id"]) for r in ctx.rosters for p in (r.get("players") or [])}
    out = []
    for sid, name, pos, team in hits:
        rid = owner.get(sid)
        tname = ctx.names.get(rid, {}).get("team_name") if rid is not None else None
        out.append({"gsis_id": gsis_of.get(sid) or (sid if pos == "DEF" else None), "sleeper_id": sid, "player_name": name,
                    "position": pos, "nfl_team": team, "rostered_by_team": tname, "rostered_by_roster_id": rid,
                    "is_free_agent": rid is None,
                    "label": f"{name} · {pos} · {team or 'no team'} · " + ("free agent" if rid is None else f"{tname}")})
    return out
