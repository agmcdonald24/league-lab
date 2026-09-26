"""Read-only database access for the explorer.

* Connects with the *application* role (LEAGUE_LAB_APP_DB_URL or LEAGUE_LAB_APP_DB_* parts),
  which can only SELECT from analytics/ops (scripts/init_db.sql). Nothing here can mutate.
* Every query is parameterized (psycopg placeholders); schema/table names are constants in
  this module, never user input.
* Results are cached for 10 minutes keyed on the SQL + parameters, so reruns of a page never
  re-query, and a page never triggers upstream ingestion (plan §8).
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import psycopg
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from league_lab.config import get_settings

ANALYTICS = "analytics"
CACHE_TTL_SECONDS = 600


def _apply_secrets() -> bool:
    """On Streamlit Community Cloud settings live in st.secrets, not in a .env: copy the ones we
    know into the environment. Runs before every connection (cheap) rather than once at import,
    because secrets can be added after the first deploy; returns True when something new arrived.
    Local runs have no secrets file and skip this silently."""
    import os

    try:
        secrets = st.secrets
        keys = list(secrets.keys())
    except Exception:  # no secrets.toml locally
        return False
    changed = False
    for k in keys:
        if k.startswith("LEAGUE_LAB_") and os.environ.get(k) != str(secrets[k]):
            os.environ[k] = str(secrets[k])
            changed = True
    return changed


def _dsn() -> str:
    if _apply_secrets():
        get_settings.cache_clear()  # settings were built before the secrets arrived
    return get_settings().app_dsn()


def setting(name: str, default: str = "") -> str:
    """A LEAGUE_LAB_* value from the environment or Streamlit secrets (e.g. FEEDBACK_URL, APP_PASSWORD)."""
    import os

    return os.environ.get(f"LEAGUE_LAB_{name}", default)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a read-only query and return a DataFrame (cached)."""
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    # numeric/decimal columns arrive as Decimal objects; make them floats for pandas/plotly
    for c in df.columns:
        if df[c].dtype == object:
            sample = df[c].dropna()
            if not sample.empty and isinstance(sample.iloc[0], Decimal):
                df[c] = df[c].astype(float)
    return df


def scalar(sql: str, params: tuple = ()):
    df = query(sql, params)
    return None if df.empty else df.iloc[0, 0]


def connection_ok() -> tuple[bool, str]:
    try:
        who = scalar("select current_user")
        return True, str(who)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc) + "\n\n" + _diagnostics()


def _diagnostics() -> str:
    """What the app can see about its configuration (names only, never values) - shown on a failed connection."""
    import os

    from streamlit import config as st_config

    lines = []
    try:
        lines.append("secrets keys: " + ", ".join(sorted(k for k in st.secrets.keys())))
    except Exception as exc:  # noqa: BLE001
        lines.append(f"secrets: not readable ({type(exc).__name__}: {exc})")
    try:
        lines.append("secrets files checked: " + ", ".join(st_config.get_option("secrets.files")))
    except Exception as exc:  # noqa: BLE001
        lines.append(f"secrets files: unknown ({exc})")
    lines.append("LEAGUE_LAB_* in environment: " + ", ".join(sorted(k for k in os.environ if k.startswith("LEAGUE_LAB_"))))
    lines.append(f"cwd: {os.getcwd()}")
    return "Diagnostics — " + " | ".join(lines)


@st.cache_data(ttl=60, show_spinner=False)
def missing_relations(names: tuple[str, ...]) -> list[str]:
    """Which of the given analytics relations (tables or views) do not exist yet."""
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "select table_name from information_schema.tables where table_schema = %s and table_name = any(%s)",
            (ANALYTICS, list(names)),
        )
        present = {r[0] for r in cur.fetchall()}
    return [n for n in names if n not in present]


def require_relations(*names: str) -> None:
    """Stop the page with a plain instruction when a mart from a newer build is missing."""
    missing = missing_relations(tuple(names))
    if missing:
        st.warning(
            "This page needs marts that have not been built on this machine yet: "
            + ", ".join(f"`{m}`" for m in missing)
            + ". Run `make build` (and `make backtest` for the Rankings scoreboard), then reload."
        )
        st.stop()
