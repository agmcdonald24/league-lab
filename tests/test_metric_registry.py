"""IL-3 (Wave I-L): every metric family docs/METRICS.md documents has a row in dbt/seeds/metric_registry.csv.

A documented family is a `##` / `###` heading of METRICS.md that carries a version tag (`wp1.0`, `kd1.0`, `og1.0` …;
the bare model versions `v1.0` … `v3.2` are left out: those sections enumerate their metrics as rows of their own, or
are the model's version). A tag is covered when a registry row has it as its `version`, names it in its `notes`, or is
the row `ALIASES` names (the row predates the tag). `NOT_METRICS` lists the tagged sections that describe a process,
not a metric. No database. Run it alone to list the gaps: `uv run pytest -q tests/test_metric_registry.py`."""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "docs" / "METRICS.md"
REGISTRY = ROOT / "dbt" / "seeds" / "metric_registry.csv"
TAG = re.compile(r"\b([a-z][a-z_]*\d+\.\d+)\b")
BARE = re.compile(r"^v\d+\.\d+$")
# a registry row older than the section's tag (the row's version column says 1.0)
ALIASES = {"wp1.0": "week_win_probability", "cb1.0": "cb_coverage_context", "pers1.0": "matchup_personnel",
           "ti1.0": "trade_interest", "ti1.1": "trade_interest", "ev1.0": "expected_value_pricing", "sx1.0": "stats_window",
           "ra1.1": "role_alert"}
NOT_METRICS = {"fx1.0": "the feature-experiment harness: a decision rule for model inputs, not a metric"}


def _rows() -> list[dict]:
    with REGISTRY.open(newline="") as f:
        return list(csv.DictReader(f))


def documented_tags() -> dict[str, str]:
    """version tag -> the first heading that carries it."""
    out: dict[str, str] = {}
    for line in METRICS.read_text().splitlines():
        if re.match(r"^#{2,3} ", line):
            for t in TAG.findall(line):
                if not BARE.match(t):
                    out.setdefault(t, line.strip("# ").strip())
    return out


def missing() -> dict[str, str]:
    rows = _rows()
    names = {r["metric"] for r in rows}
    out = {}
    for tag, heading in documented_tags().items():
        if tag in NOT_METRICS:
            continue
        if ALIASES.get(tag) in names:
            continue
        if any(r["version"] == tag or re.search(rf"\b{re.escape(tag)}\b", r["notes"] or "") for r in rows):
            continue
        out[tag] = heading[:90]
    return out


def test_every_documented_metric_has_a_registry_row():
    gaps = missing()
    assert not gaps, "documented in docs/METRICS.md without a metric_registry.csv row:\n" + "\n".join(
        f"  {t}: {h}" for t, h in sorted(gaps.items()))


def test_the_aliases_name_real_rows():
    names = {r["metric"] for r in _rows()}
    assert set(ALIASES.values()) <= names


def test_the_registry_is_well_formed():
    rows = _rows()
    assert rows and all(len(r) == 7 for r in rows)
    assert len({r["metric"] for r in rows}) == len(rows)                       # the seed's unique test, without dbt
    assert {"week_win_probability", "week_odds_brier", "range_coverage_record"} <= {r["metric"] for r in rows}
