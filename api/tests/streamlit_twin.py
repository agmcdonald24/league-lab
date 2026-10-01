"""Render a Streamlit page headlessly (Streamlit's AppTest) and print what it shows as JSON.

Runs in the REPOSITORY's environment (it needs streamlit, which the API does not install):

    uv run --project <repo> python api/tests/streamlit_twin.py home   <league> <team>
    uv run --project <repo> python api/tests/streamlit_twin.py player <league> <team> <gsis>

tests/test_parity.py calls it and compares the output with the API's JSON: the same cards, the same
sentences, the same metric values. Links are kept as the page wrote them; the test strips them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))

from streamlit.testing.v1 import AppTest  # noqa: E402


def _kids(node):
    return list(getattr(node, "children", {}).values())


def _blocks(node) -> list[dict]:
    """A container's content, flattened in order: markdown / caption / info / warning texts and metric rows."""
    out: list[dict] = []
    for ch in _kids(node):
        t = getattr(ch, "type", None)
        if t in ("markdown", "caption", "info", "warning"):
            out.append({"kind": t, "text": str(ch.value)})
        elif t == "flex_container" and _kids(ch) and all(getattr(k, "type", None) == "metric" for k in _kids(ch)):
            out.append({"kind": "metrics", "metrics": [{"label": k.label, "value": str(k.value), "delta": str(k.delta or "")}
                                                       for k in _kids(ch)]})
        elif t in ("flex_container", "expander"):
            out.extend(_blocks(ch))
    return out


def run(page: str, params: dict[str, str]) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app" / page), default_timeout=240)
    for k, v in params.items():
        at.query_params[k] = v
    at.run()
    if at.exception:
        raise SystemExit("page raised: " + at.exception[0].value)
    return at


def home(league: str, team: str) -> dict:
    at = run("Home.py", {"league": league, "team": team})
    top = _kids(at.main)
    out: dict = {"cards": [], "markdown": [], "lineup": None, "lineup_full": None, "howto": None,
                 "freshness": None, "warning": None, "notice": None}
    seen_lineup = False
    for ch in top:
        t = getattr(ch, "type", None)
        if t == "caption" and out["freshness"] is None:
            out["freshness"] = str(ch.value)
        elif t == "warning" and out["warning"] is None:
            out["warning"] = str(ch.value)
        elif t == "info" and out["notice"] is None:
            out["notice"] = str(ch.value)
        elif t == "markdown":
            out["markdown"].append(str(ch.value))
        elif t == "flex_container":
            out["cards"].append(_blocks(ch))
        elif t == "dataframe" and not seen_lineup:
            out["lineup"] = ch.value.to_dict(orient="records")
            seen_lineup = True
        elif t == "expander":
            for k in _kids(ch):
                kt = getattr(k, "type", None)
                if kt == "dataframe" and out["lineup_full"] is None:
                    out["lineup_full"] = k.value.to_dict(orient="records")
                elif kt == "markdown" and str(k.value).startswith("- The lineup") and out["howto"] is None:
                    out["howto"] = str(k.value)
    return out


def player(league: str, team: str, gsis: str) -> dict:
    at = run("pages/0_Player.py", {"league": league, "team": team, "id": gsis})
    out: dict = {"name": None, "header": None, "sections": [], "howto": None}
    for ch in _kids(at.main):
        t = getattr(ch, "type", None)
        if t == "subheader" and out["name"] is None:
            out["name"] = str(ch.value)
        elif t == "markdown" and out["name"] is not None and out["header"] is None:
            out["header"] = str(ch.value)
        elif t == "flex_container":
            b = _blocks(ch)
            out["sections"].append({"title": b[0]["text"] if b else "", "blocks": b[1:]})
        elif t == "expander":
            md = [str(k.value) for k in _kids(ch) if getattr(k, "type", None) == "markdown"]
            out["howto"] = md[0] if md else None
    return out


if __name__ == "__main__":
    kind, *args = sys.argv[1:]
    data = home(*args) if kind == "home" else player(*args)
    print("TWIN-JSON " + json.dumps(data, default=str))
