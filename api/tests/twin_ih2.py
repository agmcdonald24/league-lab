"""IH-2 (Wave I-H): the console's Waiver Wire stash region rendered headlessly (streamlit_twin.py's pattern), printed as
JSON for api/tests/test_ih2.py to compare with the API's stash words. Runs in the REPOSITORY's environment:

    uv run --project <repo> python api/tests/twin_ih2.py waivers <league> <team>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from streamlit_twin import _blocks, _kids, run  # noqa: E402


def waivers(league: str, team: str) -> dict:
    """The upside stash card: its caption, its markdown (the headline, then the detail lines) and its call line."""
    at = run("pages/2_Waiver_Wire.py", {"league": league, "team": team})
    for ch in _kids(at.main):
        if getattr(ch, "type", None) != "flex_container":
            continue
        b = _blocks(ch)
        if b and b[0]["kind"] == "caption" and b[0]["text"].startswith("Upside stash"):
            md = [x["text"] for x in b if x["kind"] == "markdown"]
            info = [x["text"] for x in b if x["kind"] == "info"]
            return {"caption": b[0]["text"], "headline": md[0] if md else None,
                    "lines": md[1].split("  \n") if len(md) > 1 else [], "call": info[0] if info else None}
    return {"caption": None, "headline": None, "lines": [], "call": None}


if __name__ == "__main__":
    kind, *args = sys.argv[1:]
    print("TWIN-JSON " + json.dumps(waivers(*args), default=str))
