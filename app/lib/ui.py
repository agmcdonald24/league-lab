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
        # when the loaded content was fetched from the source (ops.source_partition.loaded_at), in
        # Eastern time and labelled, like the stale-injury warning below
        when = (f"{pd.to_datetime(r['last_loaded'], utc=True).tz_convert('America/New_York'):%a %b %-d, %-I:%M %p} ET"
                if pd.notna(r["last_loaded"]) else "never")
        flag = f" · ⚠️ {int(r['failures'])} partition(s) currently failing" if r["failures"] else ""
        parts.append(f"**{r['source']}** loaded {when}{flag}")
    if not cov.empty:
        c = cov.iloc[0]
        parts.append(
            f"NFL {c['season']} final games through {c['through_game_date']} (REG week {c['through_reg_week']})"
            + (f" · league scored through week {int(c['league_scored_weeks'])}" if pd.notna(c["league_scored_weeks"]) else "")
        )
    st.caption(" · ".join(parts) if parts else "No loads recorded yet — run `make pilot`.")

    # B5 stale-data flag. nflverse's current-season injury file carries no report timestamp (its
    # date_modified is empty since 2025), so "the newest report" is when the file's content last
    # changed here: ops.source_partition.loaded_at moves only on a load whose checksum changed
    # (mart_data_status.last_loaded_at). Stale when that is older than the most recent final game's
    # date, or more than `stale_hours` before the next kickoff (the next game on the schedule after
    # now). Only in a game week (a kickoff within 7 days): in the offseason nothing is flagged.
    # dim_game is skipped on a database that does not have it yet (a hosted copy between a code push
    # and the next sync): then the last-final-game rule alone decides.
    stale_hours = 48
    from .db import missing_relations

    et = "America/New_York"
    loaded = query("""select max(last_loaded_at) as loaded from analytics.mart_data_status
                      where source = 'nflverse' and dataset = 'injuries'""")
    loaded_at = pd.to_datetime(loaded["loaded"].iloc[0], utc=True) if not loaded.empty else pd.NaT
    last_final = pd.to_datetime(cov["through_game_date"].iloc[0]) if not cov.empty else pd.NaT
    next_kick, game_week = pd.NaT, True
    if not missing_relations(("dim_game",)):
        nk = query("select min(kickoff_at) as next_kickoff from analytics.dim_game where kickoff_at > now()")
        next_kick = pd.to_datetime(nk["next_kickoff"].iloc[0], utc=True) if not nk.empty else pd.NaT
        game_week = pd.notna(next_kick) and next_kick <= pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=7)
    why = []
    if game_week and pd.notna(last_final) and (pd.isna(loaded_at) or loaded_at.tz_convert(et).date() < last_final.date()):
        why.append(f"it predates the last final game ({last_final:%a %b %-d})")
    if game_week and pd.notna(next_kick) and (pd.isna(loaded_at) or loaded_at < next_kick - pd.Timedelta(hours=stale_hours)):
        why.append(f"it was loaded more than {stale_hours} h before the next kickoff ({next_kick.tz_convert(et):%a %b %-d, %-I:%M %p} ET)")
    if why:
        when = f"{loaded_at.tz_convert(et):%a %b %-d, %-I:%M %p} ET" if pd.notna(loaded_at) else "never"
        reason = " and ".join(why)
        st.warning(f"Injury report last loaded {when}; treat Questionable tags as stale. {reason[0].upper()}{reason[1:]}.")


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
    """Current-season league chains loaded in this database (several leagues can coexist).

    scoring_label (U-10) is read through to_jsonb so a hosted copy published before the column
    existed shows no label instead of failing every page (page code deploys on push, marts on sync)."""
    return query(
        """select league_id, season, league_name, playoff_week_start, last_scored_leg, is_reference_league, scoring_diff_vs_reference,
                  to_jsonb(d) ->> 'scoring_label' as scoring_label
           from analytics.dim_league_season as d where is_current_season order by is_reference_league desc, league_name"""
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
    remembered_teams: dict[str, int | None] = ss.setdefault("ll_team_by_league", {})   # last team picked per league
    whole_league: dict[str, bool] = ss.setdefault("ll_whole_league", {})              # "whole league" chosen on a page that allows it
    # The widgets carry keys, and their state is seeded - never a moving `index=`: a selectbox whose
    # default is recomputed every run loses every second change (the widget identity flips). The
    # URL seeds the widgets only when it is not the URL this code wrote itself (a fresh visit or a
    # pasted deep link); a user's pick in the widget always wins over the URL it will then rewrite.
    url_league = qp.get("league")
    external_nav = url_league is not None and url_league != ss.get("ll_url_league")
    with st.sidebar:
        st.markdown("### Perspective")
        league_ids = leagues["league_id"].tolist()
        if external_nav and url_league in league_ids:
            seed_league = url_league
        elif ss.get("ll_league") in league_ids:
            seed_league = ss.get("ll_league")
        else:
            seed_league = league_ids[0]
        # assigned every run, on purpose: a keyed widget's own state does not survive a page change
        # (the new page's widget is a new widget), but a value the app assigns before creating it does
        if external_nav or ss.get("ll_league_widget") not in league_ids:
            ss["ll_league_widget"] = seed_league
        else:
            ss["ll_league_widget"] = ss["ll_league_widget"]
        league_id = st.selectbox(
            "League", league_ids, key="ll_league_widget",
            format_func=lambda lid: f"{leagues.set_index('league_id').loc[lid, 'league_name']} {leagues.set_index('league_id').loc[lid, 'season']}",
        )
        row = leagues.set_index("league_id").loc[league_id]
        label = row["scoring_label"]
        if isinstance(label, str) and label:
            # plan U-10: what kind of league this is, in one line, on every page
            st.caption(label)
        members = query(
            """select roster_id, team_name, manager_name from analytics.dim_league_member
               where league_id = %s order by team_name""",
            (league_id,),
        )
        options = [None] + members["roster_id"].tolist() if not require_team else members["roster_id"].tolist()
        labels = {int(r.roster_id): f"{r.team_name} ({r.manager_name})" for r in members.itertuples()}
        # the URL's team applies to the URL's league only (roster ids repeat across leagues); a bare
        # ?team= (older links) applies to whichever league is selected
        url_team = None
        try:
            if qp.get("team") is not None and (url_league in (None, league_id)) and int(qp.get("team")) in labels:
                url_team = int(qp.get("team"))
        except ValueError:
            url_team = None
        team_external = url_team is not None and (external_nav or url_league is None) and qp.get("team") != ss.get("ll_url_team")
        if team_external:
            seed_team = url_team
        elif not require_team and whole_league.get(league_id):
            seed_team = None
        else:
            seed_team = remembered_teams.get(league_id)
        if seed_team not in labels:
            seed_team = None
        if seed_team is None and require_team:
            seed_team = options[0]
        # reseed when the league changed (the option list is a different roster set), on a pasted
        # link, or when the remembered value is not an option on this page (whole-league vs team-only)
        if (team_external or ss.get("ll_team_widget_league") != league_id or ss.get("ll_team_widget", "_") not in options):
            ss["ll_team_widget"] = seed_team
            ss["ll_team_widget_league"] = league_id
        else:
            ss["ll_team_widget"] = ss["ll_team_widget"]   # see the league widget: survive the page change
        roster_id = st.selectbox(
            "Team perspective", options, key="ll_team_widget",
            format_func=lambda r: "— whole league —" if r is None else labels[int(r)],
        )
        st.caption("Shareable: the URL carries the league and team.")
        if len(leagues) > 1 and not bool(row["is_reference_league"]):
            # league pages price everything in this league's own scoring (plan S-01a); only the NFL
            # research pages (Players, Trends, Receivers, defense vs position) keep the reference scale
            ref_name = leagues[leagues["is_reference_league"].astype(bool)]["league_name"].iloc[0]
            st.warning(f"NFL research pages use reference scoring (**{ref_name}**).", icon="ℹ️")
            # the key-by-key diff is one click away, never on screen by default (plan U-10)
            with st.expander("Scoring differences vs the reference league", expanded=False):
                st.caption(f"Scoring vs {ref_name}:" + scoring_diff_summary(row["scoring_diff_vs_reference"], league_slots(league_id)))
    ss["ll_league"] = league_id
    if roster_id is not None:
        remembered_teams[league_id] = int(roster_id)
    whole_league[league_id] = roster_id is None and not require_team
    st.query_params["league"] = league_id
    ss["ll_url_league"] = league_id
    if roster_id is not None:
        st.query_params["team"] = str(roster_id)
        ss["ll_url_team"] = str(roster_id)
    else:
        if "team" in st.query_params:
            del st.query_params["team"]
        ss["ll_url_team"] = None
    return league_id, (int(roster_id) if roster_id is not None else None), members


def reference_scoring_note(what: str = "Fantasy points on this page") -> None:
    """Say which scoring an NFL research table uses. Research pages keep one scale for every player
    and season (the reference league's); league pages use each league's own scoring (plan S-01a)."""
    ref = query("select league_name from analytics.dim_league_season where is_reference_league")
    name = ref["league_name"].iloc[0] if not ref.empty else "the reference league"
    st.caption(
        f"{what} use **{name}** scoring (the reference league), so every player and season compares on one scale. "
        "League pages (Team Hub, Waiver Wire, Matchups start/sit, Trade Finder, League Intel, League) use each league's own scoring."
    )


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
