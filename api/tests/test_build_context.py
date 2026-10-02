"""The build context (Wave H hotfix): every path api/Dockerfile copies from the repository must be tracked and let
through by the root .dockerignore, and no <Dockerfile>.dockerignore may shadow it (BuildKit prefers that file, and a
stale one made Render's first build fail: "/app/pages": not found)."""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "api" / "Dockerfile"
IGNORE = ROOT / ".dockerignore"


def _copy_sources() -> list[str]:
    out: list[str] = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("COPY") or "--from=" in line:
            continue
        parts = line.split()[1:]
        out.extend(p for p in parts[:-1] if not p.startswith("--"))
    return out


def _allowed_by_dockerignore(path: str) -> bool:
    """Mirror of moby/patternmatcher: last matching pattern wins; a pattern that matches a parent matches the path."""
    allowed = True
    for raw in IGNORE.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        negate = raw.startswith("!")
        pattern = raw.lstrip("!").rstrip("/")
        if pattern.endswith("/**"):             # `dir/**` keeps the directory's children, so the directory itself
            pattern = pattern[:-3]
        parts = path.split("/")
        candidates = ["/".join(parts[: i + 1]) for i in range(len(parts))]
        if any(fnmatch.fnmatchcase(c, pattern) or fnmatch.fnmatchcase(c, pattern.replace("**/", "")) for c in candidates):
            allowed = negate
    return allowed


def test_no_dockerfile_specific_ignore_file_shadows_the_root_one():
    assert not (ROOT / "api" / "Dockerfile.dockerignore").exists(), \
        "api/Dockerfile.dockerignore would replace .dockerignore for `docker build -f api/Dockerfile .`"


def test_every_copied_path_is_tracked_and_allowed():
    tracked = set(subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
                  .stdout.split("\n"))
    sources = _copy_sources()
    assert sources, "no COPY lines read from the Dockerfile"
    for src in sources:
        src = src.rstrip("/")
        assert (ROOT / src).exists(), f"{src}: not in the repository"
        assert any(t == src or t.startswith(src + "/") for t in tracked), f"{src}: not tracked by git"
        assert _allowed_by_dockerignore(src), f"{src}: excluded by .dockerignore"


def test_the_ignore_file_still_keeps_secrets_and_data_out():
    for path in (".env", "data/x", "backups/x", "dbt/models/x.sql", "web/node_modules/x", "web/dist/x"):
        assert not _allowed_by_dockerignore(path), f"{path}: would be sent to the build"


def test_render_yaml_points_at_the_root_ignore_file():
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert re.search(r"^\s*-\s*\.dockerignore\s*$", text, re.M), "render.yaml's buildFilter should list .dockerignore"
