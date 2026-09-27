"""Shared UI pieces: page setup, freshness banner, filters, formatting."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .db import connection_ok, query, setting

SKILL_POSITIONS = ["QB", "RB", "WR", "TE", "K"]


def league_positions(df: pd.DataFrame, column: str = "position") -> list[str]:
    """The skill positions present in a league-scoped frame, in QB/RB/WR/TE/K order.

    A league without kicker (or TE) slots has no rows for that position; pages must not
    hard-code the five and index a pivot with a position the league does not start.
    """
    present = set(df[column].dropna().unique().tolist()) if not df.empty else set()
    return [p for p in SKILL_POSITIONS if p in present]


def _gate() -> None:
    """Optional shared password for a hosted beta (LEAGUE_LAB_APP_PASSWORD in secrets). Not a
    security boundary - the database role is read-only regardless - just a closed door for a link."""
    pw = setting("APP_PASSWORD")
    if not pw or st.session_state.get("_gate_ok"):
        return
    st.title("League Lab")
    st.caption("Private beta. Enter the password from your invite.")
    entered = st.text_input("Password", type="password")
    if entered and entered == pw:
        st.session_state["_gate_ok"] = True
        st.rerun()
    elif entered:
        st.error("That is not it.")
    st.stop()


def _sidebar_links() -> None:
    fb = setting("FEEDBACK_URL")
    with st.sidebar:
        st.radio("Table detail", ["essentials", "everything"], key="detail_level", horizontal=True,
                 format_func=lambda v: "Essentials" if v == "essentials" else "Everything",
                 help="Essentials hides denominators, noise statistics and fine-grained counts. Everything shows every column.")
        if fb:
            st.link_button("Send feedback", fb, width="stretch")
        st.caption("Data: nflverse · FTN Data (CC BY-SA 4.0) · Sleeper. See Home → Data & attribution.")


def setup(title: str, icon: str = "🏈") -> None:
    st.set_page_config(page_title=f"League Lab · {title}", page_icon=icon, layout="wide")
    _gate()
    _sidebar_links()
    ok, detail = connection_ok()
    if not ok:
        st.error(
            "Cannot reach the analytics database with the read-only role. Locally: "
            "check `.env` (LEAGUE_LAB_APP_DB_*) and that PostgreSQL is running. Hosted: set LEAGUE_LAB_APP_DB_URL in the app secrets and reboot the app.\n\n" + detail
        )
        st.stop()
    st.title(title)


def freshness_banner() -> None:
    status = query(
        """select source, max(last_loaded_at) as last_loaded, sum(failures_7d) as failures
           from analytics.mart_data_status group by source order by source"""
    )
    cov = query(
        """select season, through_game_date, through_reg_week, league_scored_weeks
           from analytics.mart_coverage order by season desc limit 1"""
    )
    parts = []
    for _, r in status.iterrows():
        when = pd.to_datetime(r["last_loaded"]).strftime("%Y-%m-%d %H:%M") if pd.notna(r["last_loaded"]) else "never"
        flag = f" · ⚠️ {int(r['failures'])} partition(s) currently failing" if r["failures"] else ""
        parts.append(f"**{r['source']}** loaded {when}{flag}")
    if not cov.empty:
        c = cov.iloc[0]
        parts.append(
            f"NFL {c['season']} final games through {c['through_game_date']} (REG week {c['through_reg_week']})"
            + (f" · league scored through week {int(c['league_scored_weeks'])}" if pd.notna(c["league_scored_weeks"]) else "")
        )
    st.caption(" · ".join(parts) if parts else "No loads recorded yet — run `make pilot`.")


def seasons_available() -> list[int]:
    df = query("select distinct season from analytics.fct_player_game order by season desc")
    return df["season"].tolist()


def league_seasons(league_id: str | None = None) -> pd.DataFrame:
    """Seasons of one league's chain (newest first). With several leagues loaded, a page must pick
    a chain first (perspective()), else two rows share each season."""
    df = query(
        """select league_id, chain_id, season, league_name, league_type, status, playoff_week_start, last_scored_leg,
                  is_current_season, roster_positions
           from analytics.dim_league_season order by season desc"""
    )
    if league_id is not None and not df.empty:
        chain = df.loc[df["league_id"] == league_id, "chain_id"]
        if not chain.empty:
            df = df[df["chain_id"] == chain.iloc[0]]
    return df


def league_slots(league_id: str) -> list[str]:
    """Positions this league starts (QB/RB/WR/TE/K/DEF present in roster_positions; SUPER_FLEX counts as QB)."""
    ls = league_seasons()
    row = ls[ls["league_id"] == league_id]
    if row.empty:
        return list(SKILL_POSITIONS)
    slots = list(row["roster_positions"].iloc[0] or [])
    present = {"QB" if s == "SUPER_FLEX" else s for s in slots}
    return [p for p in ["QB", "RB", "WR", "TE", "K", "DEF"] if p in present]


def season_picker(league_id: str, label: str = "Season") -> pd.Series:
    """A season selectbox over the selected league's chain; returns that league-season's row."""
    ls = league_seasons(league_id)
    if ls.empty:
        st.warning("No league data loaded. Run `make ingest-sleeper` and `make build`.")
        st.stop()
    seasons = ls["season"].astype(int).tolist()
    season = st.selectbox(label, seasons, format_func=lambda s: f"{s} · {ls.loc[ls['season'] == s, 'league_name'].iloc[0]}")
    return ls[ls["season"] == season].iloc[0]


def pct(v) -> str:
    return "" if pd.isna(v) else f"{float(v) * 100:.1f}%"


def fmt_df(df: pd.DataFrame, pct_cols: list[str] = (), round_cols: dict[str, int] | None = None) -> pd.DataFrame:
    out = df.copy()
    for c in pct_cols:
        if c in out.columns:
            out[c] = out[c].map(pct)
    for c, n in (round_cols or {}).items():
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").round(n)
    return out


def unavailable(metric: str, why: str) -> None:
    st.info(f"**{metric}: not available in this build.** {why}", icon="ℹ️")


# ---------------------------------------------------------------- league / team perspective
def current_leagues() -> pd.DataFrame:
    """Current-season league chains loaded in this database (several leagues can coexist)."""
    return query(
        """select league_id, season, league_name, playoff_week_start, last_scored_leg, is_reference_league, scoring_diff_vs_reference
           from analytics.dim_league_season where is_current_season order by is_reference_league desc, league_name"""
    )


def perspective(require_team: bool = True) -> tuple[str, int | None, pd.DataFrame]:
    """Sidebar selectors: which league and which roster the page looks through.

    Nothing is keyed to a particular user. Precedence for the default on each page:
      1. the URL (?league=&team=) — a shared link opens on that league and team;
      2. what was chosen earlier in this browser session — Streamlit drops the query string when
         you move between pages, so without this the selector snapped back to the reference
         league on every page;
      3. the reference league, whole-league view.
    The choice is written back to the URL on every page so any page's link stays shareable.
    Returns (league_id, roster_id, members_df).
    """
    leagues = current_leagues()
    if leagues.empty:
        st.warning("No current-season league loaded. Run `make ingest-sleeper` and `make build`.")
        st.stop()
    qp = st.query_params
    ss = st.session_state
    remembered_teams: dict[str, int | None] = ss.setdefault("ll_team_by_league", {})
    with st.sidebar:
        st.markdown("### Perspective")
        league_ids = leagues["league_id"].tolist()
        if qp.get("league") in league_ids:
            default_league = qp.get("league")
        elif ss.get("ll_league") in league_ids:
            default_league = ss.get("ll_league")
        else:
            default_league = league_ids[0]
        league_id = st.selectbox(
            "League", league_ids, index=league_ids.index(default_league),
            format_func=lambda lid: f"{leagues.set_index('league_id').loc[lid, 'league_name']} {leagues.set_index('league_id').loc[lid, 'season']}",
        )
        members = query(
            """select roster_id, team_name, manager_name from analytics.dim_league_member
               where league_id = %s order by team_name""",
            (league_id,),
        )
        options = [None] + members["roster_id"].tolist() if not require_team else members["roster_id"].tolist()
        labels = {int(r.roster_id): f"{r.team_name} ({r.manager_name})" for r in members.itertuples()}
        default_team = None
        # the URL's team applies to the URL's league only (roster ids repeat across leagues); a bare
        # ?team= (older links) applies to whichever league is selected
        try:
            if qp.get("league") in (None, league_id) and qp.get("team") is not None and int(qp.get("team")) in labels:
                default_team = int(qp.get("team"))
        except ValueError:
            default_team = None
        if default_team is None and remembered_teams.get(league_id) in labels:
            default_team = remembered_teams[league_id]
        if default_team is None and require_team:
            default_team = options[0]
        roster_id = st.selectbox(
            "Team perspective", options, index=options.index(default_team) if default_team in options else 0,
            format_func=lambda r: "— whole league —" if r is None else labels[int(r)],
        )
        st.caption("Shareable: the URL carries the league and team.")
        row = leagues.set_index("league_id").loc[league_id]
        if len(leagues) > 1 and not bool(row["is_reference_league"]):
            ref_name = leagues[leagues["is_reference_league"].astype(bool)]["league_name"].iloc[0]
            st.warning(
                f"Observed points (standings, matchups, lineups, recomputed points) use **{row['league_name']}** scoring. "
                f"Rankings (projection v2) are priced in this league's scoring. Per-game player numbers elsewhere (PPG, xPPG, "
                f"positional strength, waiver wire) are priced under **{ref_name}** scoring until per-league pricing lands (plan S-01a)."
                + scoring_diff_summary(row["scoring_diff_vs_reference"], league_slots(league_id)),
                icon="ℹ️",
            )
    ss["ll_league"] = league_id
    remembered_teams[league_id] = int(roster_id) if roster_id is not None else None
    st.query_params["league"] = league_id
    if roster_id is not None:
        st.query_params["team"] = str(roster_id)
    elif "team" in st.query_params:
        del st.query_params["team"]
    return league_id, (int(roster_id) if roster_id is not None else None), members


def scoring_diff_summary(diff: str | None, slots: list[str]) -> str:
    """The scoring keys where this league differs from the reference, skill positions first;
    kicker/defense keys are only counted when the league does not start those positions."""
    if not diff:
        return " Scoring is identical to the reference league's."
    parts = [p.strip() for p in diff.split(", ") if p.strip()]
    kd = [p for p in parts if p.split(":")[0].startswith(("fgm", "fgmiss", "xpm", "pts_allow", "yds_allow", "def_", "st_", "sack", "int:", "ff:", "fum_rec", "safe", "blk_kick"))]
    skill = [p for p in parts if p not in kd]
    text = " Differs on: " + ", ".join(skill) if skill else " Skill-position scoring is identical."
    if kd:
        text += f" (+{len(kd)} kicker/defense keys" + (")" if {"K", "DEF"} & set(slots) else " this league does not start)")
    return text + "."


def next_week_info() -> pd.Series:
    df = query("select season, last_completed_week, next_week, latest_week_with_results, next_week_first_kickoff from analytics.mart_nfl_calendar")
    return df.iloc[0] if not df.empty else pd.Series(dtype=object)
