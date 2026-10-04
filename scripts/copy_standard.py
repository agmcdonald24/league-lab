"""II-4 (Wave I-I; the product and analytics review § 5): apply the copy standard — rates say **per game**, **per target**,
**per route run**, **per attempt**, **per week** — to every user-facing file (headings, chart labels, tooltips,
summaries, accessibility labels, generated text; the console too) and to the tests that pin those words.

Idempotent: run it again after a merge (``uv run python scripts/copy_standard.py``) and it rewrites whatever new
"points a game" / "yards a target" phrasing a branch brought in; ``--check`` lists what it would change and exits 1 when
anything is left (the hand-back's grep). docs/WORDS.md § "The copy standard" is the rule; this script is its sweep.

Only rate phrasing changes ("<stat> a game" → "<stat> per game"); a noun "a game" ("a game in progress", "they share a
game", "a bye is not a game") is left alone. History (STATUS, CHANGELOG, METRICS' dated entries, the reviews) is not
rewritten.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOBS = ["api/league_lab_api/**/*.py", "app/**/*.py", "src/league_lab/**/*.py", "web/src/**/*.svelte", "web/src/**/*.ts",
         "api/tests/**/*.py", "tests/**/*.py", "web/e2e/**/*.ts", "docs/WORDS.md", "docs/DESIGN.md", "app/whats_new.md"]
SKIP = {"scripts/copy_standard.py"}

STAT = (r"points|point|targets|carries|yards|touchdowns|TDs|catches|receptions|snaps|attempts|rushes|passes|times|work|"
        r"expected|more|routes|dropbacks|sacks|interceptions|opportunities|chances")
RULES: list[tuple[re.Pattern, str]] = [
    # "<stat> a game" / "Targets a game" / "points a game" → "per game" (the stat word kept as written)
    (re.compile(rf"\b({STAT}) a game\b", re.IGNORECASE), r"\1 per game"),
    # "{x:.1f} a game", "14.9 a game", "(…) a game", "17% a game" → "per game"
    (re.compile(r"([}\d%)]) a game\b"), r"\1 per game"),
    # "yards a target", "{x} a target" → "per target"; "a carry", "a route", "an attempt" the same
    (re.compile(rf"\b({STAT}) a (target|carry|route run|route|catch)\b", re.IGNORECASE), r"\1 per \2"),
    (re.compile(r"([}\d%)]) a (target|carry|catch)\b"), r"\1 per \2"),
    (re.compile(rf"\b({STAT}) an attempt\b", re.IGNORECASE), r"\1 per attempt"),
    # "a team a week" → "per team per week"; "points a week", "{x} a week", "±1 a week" → "per week"
    (re.compile(r"\ba team a week\b"), "per team per week"),
    (re.compile(r"\b(points|point) a week\b", re.IGNORECASE), r"\1 per week"),
    (re.compile(r"([}\d)]) a week\b"), r"\1 per week"),
    # why.py's unit word: per = "a game" if games else "this week"
    (re.compile(r'per = "a game"'), 'per = "per game"'),
    # "A game, projected" (the pieces' caption)
    (re.compile(r"\bA game, projected\b"), "Per game, projected"),
]


def files() -> list[Path]:
    out: list[Path] = []
    for g in GLOBS:
        out += [p for p in ROOT.glob(g) if p.is_file() and "node_modules" not in p.parts]
    return sorted({p for p in out if str(p.relative_to(ROOT)) not in SKIP})


def sweep(text: str) -> str:
    for pat, rep in RULES:
        text = pat.sub(rep, text)
    return text


def main(argv: list[str]) -> int:
    check = "--check" in argv
    left = 0
    for p in files():
        old = p.read_text()
        new = sweep(old)
        if new == old:
            continue
        rel = p.relative_to(ROOT)
        n = sum(1 for a, b in zip(old.splitlines(), new.splitlines(), strict=False) if a != b)
        left += n
        print(f"{rel}: {n} line{'s' if n != 1 else ''}")
        if not check:
            p.write_text(new)
    if check and left:
        print(f"{left} line(s) still say 'a game' / 'a target' / 'a week' as a rate", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
