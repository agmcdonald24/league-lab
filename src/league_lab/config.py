"""Runtime settings for League Lab.

Everything that differs between machines (paths, database, league) is read from the
environment (or a local ``.env``), never hardcoded. See ``.env.example`` for the full list.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Walk up from this file until we find pyproject.toml (works from any cwd)."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEAGUE_LAB_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- database (pipeline role) ---
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "league_lab"
    db_user: str = "league_lab_pipeline"
    db_password: str = ""
    db_url: str | None = Field(default=None, description="Full DSN override for the pipeline role")

    # --- database (read-only application role) ---
    app_db_user: str = "league_lab_app"
    app_db_password: str = ""
    app_db_url: str | None = Field(default=None, description="Full DSN override for the app role")

    # --- league ---
    sleeper_league_id: str = "1389709692405551104"
    sleeper_base_url: str = "https://api.sleeper.app/v1"

    # --- nflverse ---
    nflverse_base_url: str = "https://github.com/nflverse/nflverse-data/releases/download"
    ff_playerids_url: str = (
        "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
    )
    seasons_start: int = 2016
    pbp_columns: str = "core"  # "core" (~190 columns, see ingest.nflverse.PBP_CORE_COLUMNS) or "all" (~370)

    # --- paths ---
    data_dir: Path = PROJECT_ROOT / "data"
    http_timeout_seconds: float = 120.0
    http_max_retries: int = 4

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    def pipeline_dsn(self) -> str:
        if self.db_url:
            return self.db_url
        return (
            f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/"
            f"{self.db_name}"
        )

    def app_dsn(self) -> str:
        if self.app_db_url:
            return self.app_db_url
        return (
            f"postgresql://{self.app_db_user}:{self.app_db_password}@{self.db_host}:"
            f"{self.db_port}/{self.db_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
