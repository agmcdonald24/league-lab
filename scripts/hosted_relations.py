"""Which relations the readers of the hosted copy name: the one place `scripts/sync_to_hosted.sh` derives its closure.

The hosted copy (Neon) is read by two front ends, and both are found from the code, never from a hand-kept list:

* **console**: the Streamlit research console: ``app/*.py``, ``app/pages/*.py``, ``app/lib/*.py`` and the weekly
  packs (``src/league_lab/reports.py``);
* **api**: the product API: ``api/league_lab_api/*.py``, the ``app/lib`` modules it loads unchanged
  (``applib``: cards, ui, ros, signals, matchups) and the page files whose functions it compiles
  (``page_functions("<page>.py", ...)``).

Each group also takes every ``src/league_lab`` module its files import, followed import by import (``anyleague`` ->
``lineup``, ``kdef``, ``sleeper_client`` ...), so a module a route starts to use is covered with no edit here. The
walk stops at the model fit and the loaders (``NOT_FOLLOWED``): a route imports constants and pricing functions
from them, never their input tables, and what they write reaches the readers through ``ops``, which the sync
publishes whole. (Following them adds no ``analytics`` name today, only E4's experiment tables
``ops.player_prior_oof*``, which the sync leaves out on purpose.)

A **name** is every ``<schema>.<relation>`` in a reader's text for the schemas below, plus the bare names handed to
``missing_relations(...)`` / ``require_relations(...)`` (the "is this mart built" checks; schema ``analytics``).
The text is read whole (comments and docstrings too): a stray name costs a few KB on the hosted copy, a missed
one a blank screen. Names that are not relations (``raw.groupby`` on a pandas frame called ``raw``) are dropped by
the sync, which keeps only names the local database has.

Usage (from the repository root):  uv run python scripts/hosted_relations.py            group<TAB>schema.name lines
                                   uv run python scripts/hosted_relations.py --files    group<TAB>reader file lines
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "league_lab"
SCHEMAS = ("analytics", "analytics_seeds", "ops", "raw", "staging", "intermediate")
QUALIFIED = re.compile(r"\b(" + "|".join(SCHEMAS) + r")\.([a-z_][a-z0-9_]*)\b")
GUARDED = re.compile(r"\b(?:missing|require)_relations\(\s*\(?(.*?)\)", re.S)
PAGE_FUNCTIONS = re.compile(r"page_functions\(\s*\"([^\"]+\.py)\"")
# the model fit, the experiment harness and the loaders: imported for constants / pricing, their tables never read
NOT_FOLLOWED = {"projections", "rankings", "feature_groups", "experiments", "ingest", "cli", "db", "manifest", "http"}


def _imports(path: Path, in_package: bool) -> set[str]:
    """The ``league_lab`` modules a file imports (top-level module names)."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "league_lab":
                parts = node.module.split(".")
                out |= {parts[1]} if len(parts) > 1 else {a.name for a in node.names}
            elif in_package and node.level == 1:          # from .x import y / from . import x (inside src/league_lab)
                out |= {node.module.split(".")[0]} if node.module else {a.name for a in node.names}
        elif isinstance(node, ast.Import):
            out |= {a.name.split(".")[1] for a in node.names if a.name.startswith("league_lab.")}
    return out


def _with_imports(entry: list[Path]) -> list[Path]:
    """``entry`` + every src/league_lab module reachable from it (a package: all of its files, not followed)."""
    files = list(entry)
    todo = set().union(*(_imports(p, False) for p in entry)) if entry else set()
    seen: set[str] = set()
    while todo:
        mod = todo.pop()
        seen.add(mod)
        if mod in NOT_FOLLOWED:
            continue
        if (SRC / f"{mod}.py").exists():
            files.append(SRC / f"{mod}.py")
            todo |= _imports(SRC / f"{mod}.py", True) - seen
        elif (SRC / mod).is_dir():
            files.extend(sorted((SRC / mod).glob("*.py")))
    return sorted(set(files))


def readers() -> dict[str, list[Path]]:
    app_lib = sorted((ROOT / "app" / "lib").glob("*.py"))
    console = [*sorted((ROOT / "app").glob("*.py")), *sorted((ROOT / "app" / "pages").glob("*.py")), *app_lib,
               SRC / "reports.py"]
    api = sorted((ROOT / "api" / "league_lab_api").glob("*.py"))
    pages = {m for p in api for m in PAGE_FUNCTIONS.findall(p.read_text())}
    api = [*api, *app_lib, *(ROOT / "app" / "pages" / p for p in sorted(pages))]
    return {"console": _with_imports(console), "api": _with_imports(api)}


def names(path: Path) -> set[str]:
    text = path.read_text()
    found = {f"{s}.{n}" for s, n in QUALIFIED.findall(text)}
    for call in GUARDED.findall(text):
        found |= {f"analytics.{n}" for n in re.findall(r"\"([a-z_][a-z0-9_]*)\"", call)}
    return found


def relations() -> dict[str, set[str]]:
    return {group: set().union(*(names(p) for p in files)) for group, files in readers().items()}


def main(argv: list[str]) -> int:
    if argv[1:] == ["--files"]:
        for group, files in readers().items():
            for f in files:
                print(f"{group}\t{f.relative_to(ROOT)}")
        return 0
    if argv[1:]:
        print(__doc__, file=sys.stderr)
        return 64
    for group, found in relations().items():
        for name in sorted(found):
            print(f"{group}\t{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
