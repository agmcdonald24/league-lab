"""IX-1 (Wave I-X), lf1.0: a game left early, and the projected target share (docs/METRICS.md § "A game left early").

* ``projected_target_share(gsis, position, season, week)`` — the card's (``/api/player/{gsis}``), lf1.1 (IX-6): his
  projected targets ÷ **the projected pass attempts of his team's projected starting quarterback** that week
  (``ops.projection_lines``, through ``db._run``: the live week's rows for the games not yet kicked off; the starter =
  ``mart_starter_check.projected_qb_id``, the rule the projection uses). lf1.0 divided by the sum of every projected
  player listed on his team — 40 – 47 targets a team against 29 – 33 in a real game, because each backup's line is an
  "if he plays" number — and so understated every starter. On 2026 weeks 1 – 4 the starters' projected attempts average
  30.4 against 31.2 real team targets, and the share is 0.056 from his real target share on average (docs/METRICS.md
  § "A game left early", lf1.1). His team = his newest team (``dim_player.latest_team``). RB / WR / TE only; None when he
  has no line, sits, his team's next game is not this week, or the starter has no line.
* ``game_log_marks(games, gsis, season)`` — the game log's (``/api/player/{gsis}/games``): ``left_early`` and
  ``left_early_reason`` per game (knowable when the game ended), the display-only "then missed week N" when he did not
  play his team's next game, and the on-field shares with their basis.
"""

from __future__ import annotations

import pandas as pd

from .db import query

POSITIONS = ("RB", "WR", "TE")

PTS_SQL = """
with me as (
    select distinct on (l.gsis_id) l.gsis_id, l.proj_targets, d.latest_team as team
    from ops.projection_lines as l
    join analytics.dim_player as d on d.gsis_id = l.gsis_id
    where l.season = %s and l.week = %s and l.gsis_id = %s
    order by l.gsis_id, l.fitted_at desc
),
qb as (
    select distinct on (l.gsis_id) l.gsis_id, l.proj_attempts
    from ops.projection_lines as l
    where l.season = %s and l.week = %s
      and l.gsis_id in (select m.projected_qb_id from analytics.mart_starter_check as m where m.season = %s and m.week = %s)
    order by l.gsis_id, l.fitted_at desc
)
select me.proj_targets, qb.proj_attempts as team_attempts, m.projected_qb_id, m.projected_name
from me
join analytics.mart_starter_check as m on m.team = me.team and m.season = %s and m.week = %s
left join qb on qb.gsis_id = m.projected_qb_id
"""

WORDS = ("{targets:.1f} of the {att:.1f} passes we project {team_qb} to throw in week {week} ({pct}%): the model's own "
         "forecast of his share of the team's targets this week.")


def projected_target_share(gsis: str, position: str | None, season: int | None, week: int | None,
                           sits: bool = False) -> dict | None:
    if position not in POSITIONS or season is None or week is None or sits:
        return None
    try:
        p = (int(season), int(week))
        df = query(PTS_SQL, (*p, gsis, *p, *p, *p))
    except Exception:  # noqa: BLE001 — no lines or no starter mart on this copy: no share (never a 500 for a card's extra)
        return None
    if df.empty or pd.isna(df.iloc[0]["proj_targets"]) or pd.isna(df.iloc[0]["team_attempts"]):
        return None
    mine, att = float(df.iloc[0]["proj_targets"]), float(df.iloc[0]["team_attempts"])
    if att <= 0:
        return None
    share = round(min(1.0, mine / att), 4)
    qb = df.iloc[0]["projected_name"] if isinstance(df.iloc[0]["projected_name"], str) else "his quarterback"
    return {"share": share, "targets": round(mine, 1), "team_attempts": round(att, 1), "week": int(week),
            "quarterback": qb if qb != "his quarterback" else None,
            "words": WORDS.format(targets=mine, att=att, team_qb=qb, week=int(week), pct=round(100 * share))}


# ---- the game log
ONFIELD_SQL = """
select p.game_id,
       (to_jsonb(p) ->> 'left_early')::boolean            as left_early,
       to_jsonb(p) ->> 'left_early_reason'                as left_early_reason,
       (to_jsonb(p) ->> 'on_field_target_share')::numeric as on_field_target_share,
       (to_jsonb(p) ->> 'on_field_carry_share')::numeric  as on_field_carry_share,
       to_jsonb(p) ->> 'on_field_basis'                   as on_field_basis
from analytics.fct_player_game as p
where p.gsis_id = %s and p.season = %s
"""

# his team's games of the season in order, and whether each has box scores on this copy (any player row)
TEAM_GAMES_SQL = """
select g.game_id, g.week, g.season_type, t.team,
       exists (select 1 from analytics.fct_player_game f where f.game_id = g.game_id and f.team = t.team) as has_rows
from analytics.dim_game as g
cross join lateral (values (g.home_team), (g.away_team)) as t(team)
where g.season = %s
order by g.week
"""


def game_log_marks(games: pd.DataFrame, gsis: str, season: int) -> pd.DataFrame:
    """``games`` (the game log's rows, with game_id, team, week, season_type, played) + the IX-1 fields."""
    cols = ["left_early", "left_early_reason", "on_field_target_share", "on_field_carry_share", "on_field_basis"]
    if games.empty:
        return games.assign(**{c: None for c in [*cols, "left_early_kind", "left_early_words"]})  # ---- IX-2
    of = query(ONFIELD_SQL, (gsis, int(season)))
    out = games.merge(of, on="game_id", how="left") if not of.empty else games.assign(**{c: None for c in cols})
    out["left_early"] = out["left_early"].astype("boolean").fillna(False).astype(bool)
    if out["left_early"].any():
        tg = query(TEAM_GAMES_SQL, (int(season),))
        mine = set(games.loc[games["played"].astype("boolean").fillna(False).astype(bool), "game_id"])
        for i in out.index[out["left_early"]]:
            r = out.loc[i]
            sched = tg[(tg["team"] == r["team"]) & (tg["season_type"] == r["season_type"])].sort_values("week")
            nxt = sched[sched["week"] > r["week"]].head(1)
            if not nxt.empty and bool(nxt.iloc[0]["has_rows"]) and nxt.iloc[0]["game_id"] not in mine:
                # display only: a later week's fact (never an input; docs/METRICS.md § "A game left early")
                out.at[i, "left_early_reason"] = f"{r['left_early_reason']}; then missed week {int(nxt.iloc[0]['week'])}"
    for c in ("on_field_target_share", "on_field_carry_share"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    # ---- IX-2 (the PO's decision): which case the mark is, as a closed field the screens read — "hurt" when the
    # play-by-play named him hurt (the reason says so), else "short" — and the words each case may use: "Left early"
    # only with the injury note (lf1.0's mark is right less than half the time without it: precision 0.437 against
    # 0.955 with the note); otherwise the plain fact, never "left early", never "hurt"
    kinds, words = [], []
    for le, reason in zip(out["left_early"], out["left_early_reason"], strict=True):
        k, w = left_early_case(bool(le), reason if isinstance(reason, str) else None)
        kinds.append(k)
        words.append(w)
    out["left_early_kind"] = kinds
    out["left_early_words"] = words
    # ---- end IX-2
    return out


HURT_MARK = "; hurt on a play in the "          # the one form int_player_game_on_field writes for the injury note
SHORT_WORDS = "Played far less than usual: {fact}"
HURT_WORDS = "Left early: {reason}"


def left_early_case(left_early: bool, reason: str | None) -> tuple[str | None, str | None]:
    """(``left_early_kind``: "hurt" | "short" | None, the words). The reason's first part is the snap fact ("15 snaps
    (20% of the team's; usually 94%)"); the injury note is the closed suffix the model writes."""
    if not left_early or not reason:
        return None, None
    if HURT_MARK in reason:
        return "hurt", HURT_WORDS.format(reason=reason)
    fact, _, rest = reason.partition("); ")
    fact = fact + ")" if rest else fact
    missed = rest.split("; then missed ", 1)
    tail = f"; then missed {missed[1]}" if len(missed) == 2 else ""
    return "short", SHORT_WORDS.format(fact=fact + tail)
