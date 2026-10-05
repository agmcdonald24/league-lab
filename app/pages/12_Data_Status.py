"""Data status: freshness, coverage, failures, identity quarantine and the metric registry (plan §8.6)."""

import pandas as pd
import streamlit as st
from lib.db import query, setting
from lib.table import detail_level, howto, show
from lib.ui import setup

setup("Data Status", icon="🧪")

# ---- IH-1 (Wave I-H): the stale state, in the web app's words (league_lab/freshness.py: the newest projections'
# fitted_at older than 30 hours = a missed morning update). The console reads only the nightly's rows, so its tail
# says the injury tags are from that update too (the web app's overlay keeps reading the injury feeds live).
from league_lab.freshness import nightly_state  # noqa: E402

_asof = query("select max(fitted_at) as t from ops.projections")
_nightly = nightly_state(None if _asof.empty or pd.isna(_asof["t"].iloc[0]) else pd.Timestamp(_asof["t"].iloc[0]),
                         console=True)
if _nightly["stale"]:
    st.warning(f"{_nightly['words']} (The projections were last refit {_nightly['age_hours']:.0f} hours ago; "
               f"this note shows after {_nightly['limit_hours']} hours.)")
# ---- end IH-1

# ---- INF-2 (Wave I-J): the API's memory in one line (its /api/status `memory` block; docs/DEPLOY.md § Memory). The
# console does not run the API: LEAGUE_LAB_API_URL says where it is (hosted: https://isuckatfantasy.io), and
# LEAGUE_LAB_API_TOKEN a token from its /api/login when the password gate is on.
from league_lab.memo import status_words  # noqa: E402


@st.cache_data(ttl=60, show_spinner=False)
def _api_memory(url: str, token: str) -> dict | None:
    import json
    import urllib.request
    req = urllib.request.Request(url.rstrip("/") + "/api/status",
                                 headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read()).get("memory")
    except Exception:  # noqa: BLE001 - a status line, never a failure
        return None


_api = setting("API_URL")
if _api:
    _mem = _api_memory(_api, setting("API_TOKEN"))
    st.caption("**API memory:** " + (status_words(_mem) if _mem else f"{_api} did not answer /api/status."))
else:
    st.caption("**API memory:** set LEAGUE_LAB_API_URL (and LEAGUE_LAB_API_TOKEN when the gate is on) to read it here.")
# ---- end INF-2

st.subheader("Sources")
howto("One row per source League Lab reads (NFL stats, Sleeper, charting). **Last loaded** says how fresh each one is.",
      "**Last status** is the latest attempt. A failed attempt never replaces good data, so a failure here means the numbers are "
      "a day or so *old*, not *wrong*; the next nightly refresh tries again.",
      "**Partitions** are the pieces a source comes in, usually one per season.")
status = query(
    """select source, dataset, partitions, rows_loaded, first_partition, last_partition, last_loaded_at,
              last_status, last_attempt_at, failures_7d, last_failure_at, last_error
       from analytics.mart_data_status order by source, dataset"""
)
with st.container(border=True):     # the answer first (U-13), the tables in expanders
    failing = status[status["failures_7d"].fillna(0) > 0]
    newest = pd.to_datetime(status["last_loaded_at"], utc=True).max() if not status.empty else pd.NaT
    when = f"{newest.tz_convert('America/New_York'):%a %b %-d, %-I:%M %p} ET" if pd.notna(newest) else "never"
    st.markdown(f"**{len(status)} datasets loaded, newest {when}; "
                + (f"{len(failing)} with failed loads in the last 7 days ({', '.join(failing['dataset'].astype(str).head(4))}).**" if not failing.empty
                   else "no failed loads in the last 7 days.**"))
with st.expander("Every dataset"):
    show(status, phone_cols=["dataset", "partitions", "last_loaded_at", "last_status", "failures_7d"])
if (status["failures_7d"].fillna(0) > 0).any():
    st.warning("Some partitions failed to load in the last 7 days. Previous good data was kept for those partitions; "
               "run `make status` for the manifest and `make refresh` to retry.")

st.subheader("Coverage by season")
cov = query("""select season, scheduled_games, final_games, through_reg_week, games_with_player_stats, games_with_snaps,
                      play_by_play_status, ftn_charting_status, participation_status, routes_status, leagues, league_scored_weeks
               from analytics.mart_coverage order by season""")
st.caption("Every source per season. 'not published yet' (participation) means the NFL releases that season's file after its "
           "postseason; 'no licensed feed' (routes) means the proxy from participation is what the pages use.")
with st.expander("Coverage, every season"):
    if detail_level() == "phone":   # five columns on a phone (U-13)
        cov = cov[["season", "final_games", "play_by_play_status", "ftn_charting_status", "participation_status"]]
    st.dataframe(cov, hide_index=True, width="stretch", column_config={
        "season": "Season", "scheduled_games": "Games", "final_games": "Final", "through_reg_week": "Through wk",
        "games_with_player_stats": "Games w/ stats", "games_with_snaps": "Games w/ snaps", "play_by_play_status": "Play-by-play",
        "ftn_charting_status": "FTN charting (first reads)", "participation_status": "Participation (routes proxy)",
        "routes_status": "Licensed routes", "leagues": "Leagues", "league_scored_weeks": "League weeks scored"})

st.subheader("Identity quarantine")
q = query("select issue, count(*) as rows from analytics.player_id_quarantine group by issue order by 2 desc")
st.dataframe(q, hide_index=True, width="stretch")
with st.expander("Show quarantined rows"):
    st.dataframe(query("select * from analytics.player_id_quarantine order by issue, gsis_id, sleeper_id limit 500"),
                 hide_index=True, width="stretch")

st.subheader("Recent load attempts")
recent = query(
    """select started_at, source, dataset, partition_key, status, row_count, left(error, 120) as error, code_version
       from ops.load_manifest order by load_id desc limit 100"""
)
with st.expander("The last 100 load attempts"):
    show(recent, height=360, phone_cols=["started_at", "dataset", "partition_key", "status", "row_count"])

st.subheader("Metric registry")
with st.expander("Every registered metric"):
    show(query("select metric, version, status, numerator, denominator, grain, notes from analytics_seeds.metric_registry order by status, metric"),
         phone_cols=["metric", "version", "status", "grain"])

st.subheader("Attribution")
st.markdown(
    "NFL data: **nflverse** (nflverse-data releases) and the **dynastyprocess** player-id crosswalk. "
    "League data: **Sleeper** public API. FTN charting (first reads, catchable balls, drops) is CC-BY-SA 4.0, attributed to "
    "*FTN Data via nflverse*. Check each source's terms before redistributing any of this data."
)
