"""Every relation a page guards with require_relations() must be one it actually reads.

scripts/sync_to_hosted.sh publishes only the analytics relations referenced as `analytics.<name>`
in the app code. A guard naming a relation the page never queries (fct_play_charting on the
Receivers page once, mart_player_week_features on Rankings once) makes the hosted page refuse
to render although everything it needs is there.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
GUARD = re.compile(r"require_relations\(([^)]*)\)")


def test_guarded_relations_are_read_by_the_page():
    problems = []
    for page in sorted([APP / "Home.py", *(APP / "pages").glob("*.py")]):
        src = page.read_text()
        for m in GUARD.finditer(src):
            for name in re.findall(r"\"([a-z_]+)\"", m.group(1)):
                if f"analytics.{name}" not in src:
                    problems.append(f"{page.name}: guards {name} but never reads analytics.{name}")
    assert not problems, "\n".join(problems)
