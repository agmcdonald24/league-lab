"""Configuration from the environment (the same LEAGUE_LAB_* names the Streamlit app reads).

Hosted: set LEAGUE_LAB_APP_DB_URL (the read-only role's connection string) and, for the gate,
LEAGUE_LAB_APP_PASSWORD. Locally the repository's `.env` is read too (never overriding the environment),
so `uv run uvicorn ...` from `api/` talks to the same database as `make app`.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]          # the repository: app/, api/, web/ side by side
# The product's name as a manager sees it (renamed from League Lab on 2026-10-04; the codebase, the package, the
# LEAGUE_LAB_* variables, the repository and the research console keep the old name). web/src/lib/brand.ts is its twin.
APP_NAME = "isuckatfantasy"
APP_LIB = ROOT / "app" / "lib"

if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env", override=False)


def env(name: str, default: str = "") -> str:
    """LEAGUE_LAB_<name> from the environment."""
    return os.environ.get(f"LEAGUE_LAB_{name}", default)


def app_dsn() -> str:
    """The read-only role's DSN: LEAGUE_LAB_APP_DB_URL, else built from the parts the way
    league_lab.config.Settings.app_dsn() builds it (LEAGUE_LAB_APP_DB_USER / _PASSWORD + LEAGUE_LAB_DB_HOST / _PORT / _NAME)."""
    url = env("APP_DB_URL")
    if url:
        return url
    return (f"postgresql://{env('APP_DB_USER', 'league_lab_app')}:{env('APP_DB_PASSWORD')}@"
            f"{env('DB_HOST', 'localhost')}:{env('DB_PORT', '5432')}/{env('DB_NAME', 'league_lab')}")


def web_dist() -> Path:
    """Where the built web app lives (served as static files): LEAGUE_LAB_WEB_DIST, else web/dist."""
    return Path(env("WEB_DIST") or ROOT / "web" / "dist")
