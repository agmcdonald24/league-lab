"""The Streamlit app's own library modules, loaded unchanged into the API.

`app/lib/cards.py` (My Week: `lineup_rows`, `decisions`, `alternative`, `bench_gap`, `league_line`, the card
text in `render_decision` / `decision_cards`), `app/lib/ui.py` (`current_week`, `current_leagues`,
`freshness_banner`, `pct`, `player_link`) and `app/lib/signals.py` (the role-alert sentences) are the
same files the pages run. They are loaded here as a private package whose `db` module is the API's
(`league_lab_api.db`: same `query` contract, no Streamlit) while `streamlit` itself is a stand-in that
records what a page would have drawn. So:

* the numbers come from the same SQL and the same pure functions as the Streamlit pages, and
* the card text is the text `render_decision` writes: `capture(fn, ...)` runs a rendering function and
  returns its calls (`markdown`, `caption`, `info`, `container`, `metric` ...) as data. A wording change
  in `cards.py` reaches both front ends with no change here.

Nothing in `app/` is edited or imported through `lib.` (the pages' path); the stand-in is only in
`sys.modules` while the three files load.
"""

from __future__ import annotations

import contextvars
import importlib.util
import re
import sys
import types
from collections.abc import Callable
from typing import Any

from . import db as api_db
from .settings import APP_LIB, ROOT

PKG = "league_lab_api._applib"
_calls: contextvars.ContextVar[list | None] = contextvars.ContextVar("st_calls", default=None)
_PASSTHROUGH = {"cache_data", "cache_resource", "fragment", "dialog"}


class StStop(Exception):  # noqa: N818 - mirrors st.stop()
    """`st.stop()` inside a captured function."""


class _Element:
    """What every stand-in call returns: a context manager (st.container, st.expander, st.columns' items),
    a passthrough decorator (st.cache_data(...)), and an object whose methods record too (box.markdown)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        rec = _calls.get()
        if rec is not None:
            rec.append(("end", (), {}))
        return False

    def __call__(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return self

    def __iter__(self):                       # a, b = st.columns(2)
        return iter([_Element() for _ in range(8)])

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        return _recorder(name)


def _recorder(name: str) -> Callable[..., Any]:
    def call(*args, **kwargs):
        if name in _PASSTHROUGH:
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]
            return _Element()
        if name == "stop":
            raise StStop()
        rec = _calls.get()
        if rec is not None:
            rec.append((name, args, kwargs))
        return _Element()
    return call


class _StreamlitStandIn(types.ModuleType):
    """`import streamlit as st` inside the loaded files. session_state / query_params are empty dicts, so
    `ui.player_link` builds a context-free link (`Player?name=…&id=…`), which `links()` rewrites."""

    def __init__(self) -> None:
        super().__init__("streamlit")
        self.session_state: dict = {}
        self.query_params: dict = {}
        self.secrets: dict = {}

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        return _recorder(name)


def _shim_db() -> types.ModuleType:
    """`app/lib/db.py`'s public names, backed by the API's pool and cache."""
    m = types.ModuleType(f"{PKG}.db")
    m.ANALYTICS = api_db.ANALYTICS
    m.CACHE_TTL_SECONDS = api_db.CACHE_TTL_SECONDS
    m.query = api_db.query
    m.scalar = api_db.scalar
    m.missing_relations = api_db.missing_relations

    def setting(name: str, default: str = "") -> str:
        import os
        return os.environ.get(f"LEAGUE_LAB_{name}", default)

    def connection_ok() -> tuple[bool, str]:
        try:
            return True, str(api_db.scalar("select current_user"))
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def require_relations(*names: str) -> None:
        missing = api_db.missing_relations(tuple(names))
        if missing:
            raise api_db.DataNotReady("not built yet: " + ", ".join(missing))

    m.setting, m.connection_ok, m.require_relations = setting, connection_ok, require_relations
    return m


def _load() -> dict[str, types.ModuleType]:
    if str(ROOT / "src") not in sys.path:          # what app/lib/db.py does, for any league_lab.* import
        sys.path.insert(0, str(ROOT / "src"))
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(APP_LIB)]
    sys.modules[PKG] = pkg
    sys.modules[f"{PKG}.db"] = _shim_db()
    saved = sys.modules.get("streamlit")
    sys.modules["streamlit"] = _StreamlitStandIn()
    out: dict[str, types.ModuleType] = {}
    try:
        for name in ("ui", "signals", "cards"):
            spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", APP_LIB / f"{name}.py")
            assert spec is not None and spec.loader is not None, f"app/lib/{name}.py not found under {APP_LIB}"
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            setattr(pkg, name, mod)
            out[name] = mod
    finally:
        if saved is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = saved
    return out


_mods = _load()
ui: Any = _mods["ui"]
cards: Any = _mods["cards"]
signals: Any = _mods["signals"]


def capture(fn: Callable[..., Any], *args, **kwargs) -> tuple[Any, list[tuple[str, tuple, dict]]]:
    """Run a Streamlit rendering function from app/lib and return (its result, the calls it made).
    `st.stop()` ends the capture early (result None)."""
    token = _calls.set([])
    try:
        try:
            result = fn(*args, **kwargs)
        except StStop:
            result = None
        return result, list(_calls.get() or [])
    finally:
        _calls.reset(token)


# ---------------------------------------------------------------- links: the app's Player?… → the web app's /player/<id>
_LINK = re.compile(r"\[([^\]]*)\]\(Player\?([^)]*)\)")


def links(md: str) -> str:
    """Rewrite `ui.player_link` markdown (`[Name](Player?name=…&id=<gsis>…)`) to `[Name](/player/<gsis>)`;
    the web app adds the league and team and keeps the tap inside the page."""
    from urllib.parse import parse_qs

    def sub(m: re.Match) -> str:
        q = parse_qs(m.group(2))
        gid = (q.get("id") or [""])[0]
        return f"[{m.group(1)}](/player/{gid})" if gid else m.group(1)

    return _LINK.sub(sub, md)


def strip_links(md: str) -> str:
    """`[Name](anything)` → `Name` (for comparing texts across front ends)."""
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)


TEXT_CALLS = {"markdown", "caption", "write", "info", "warning", "success", "error", "subheader", "expander", "metric"}


def blocks(calls: list[tuple[str, tuple, dict]]) -> list[dict]:
    """The recorded calls as display blocks: {kind, text} (metric: {kind, label, value, delta})."""
    out: list[dict] = []
    for name, args, kwargs in calls:
        if name == "metric":
            label = args[0] if args else kwargs.get("label")
            value = args[1] if len(args) > 1 else kwargs.get("value")
            out.append({"kind": "metric", "label": str(label), "value": None if value is None else str(value),
                        "delta": None if kwargs.get("delta") is None else str(kwargs.get("delta")),
                        "help": kwargs.get("help")})
        elif name in TEXT_CALLS and args and isinstance(args[0], str):
            out.append({"kind": name, "text": links(args[0])})
    return out
