"""Routes-feed CSV contract (plan P2-12): what a provider export must contain."""

from pathlib import Path

import pytest

from league_lab.ingest.routes_feed import RoutesFeedError, read_routes_csv


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "routes.csv"
    p.write_text(text)
    return p


def test_minimal_valid_file(tmp_path: Path) -> None:
    df = read_routes_csv(_write(tmp_path, "season,week,gsis_id,routes\n2025,1,00-0036900,31\n2025,2,00-0036900,28\n"), "pff")
    assert df.height == 2
    assert df["routes"].to_list() == [31, 28]
    assert df["provider"].unique().to_list() == ["pff"]
    assert set(df.columns) >= {"season", "week", "gsis_id", "sleeper_id", "pfr_id", "routes", "imported_at"}


def test_sleeper_id_is_enough_and_header_case_is_ignored(tmp_path: Path) -> None:
    df = read_routes_csv(_write(tmp_path, "Season,Week,Sleeper_ID,Routes,Team\n2025,1,4046,30,BUF\n"), "x")
    assert df["sleeper_id"].to_list() == ["4046"] and df["gsis_id"].to_list() == [None]


@pytest.mark.parametrize(
    "text",
    [
        "season,week,routes\n2025,1,30\n",  # no id column at all
        "season,week,gsis_id,routes\n2025,1,,30\n",  # empty id
        "season,week,gsis_id\n2025,1,00-0036900\n",  # no routes
        "season,week,gsis_id,routes\n2025,1,00-0036900,-1\n",  # negative
        "season,week,gsis_id,routes\n2025,1,00-0036900,30\n2025,1,00-0036900,31\n",  # duplicate
    ],
)
def test_rejects_bad_files(tmp_path: Path, text: str) -> None:
    with pytest.raises(RoutesFeedError):
        read_routes_csv(_write(tmp_path, text), "x")
