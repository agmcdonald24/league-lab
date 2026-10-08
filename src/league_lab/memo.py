"""One byte budget for every in-process cache of the server (INF-2, Wave I-J: the memory diet).

The API kept a dozen module-level dicts (the SQL results, a league's priced weeks, its rest-of-season table, its
solved weeks, the availability contexts, the decision memos, research's priced boards, About's answers), each with
its own TTL and its own crude bound (``clear()`` when it held 50 / 100 / 256 / 500 entries, the oldest half of 2,000
SQL results). Nothing bounded the BYTES, so every league a server had seen in the last ten minutes stayed in memory
and four leagues filled 400 of the Starter plan's 512 MB (Render, Sunday 2026-10-04: "ran out of memory").

Here: one least-recently-used order across every cache, a TTL per entry (each cache keeps its own), and one budget in
bytes (``LEAGUE_LAB_CACHE_MB``, default 64: the brief's 160 was in ``memory_usage(deep=True)`` units, which count an
interned string at every row — 64 here is about what 160 deep-counted was, and about 100 MB of the Python heap once
pandas' own objects are added; see docs/DEPLOY.md § Memory). Each cache is a named ``Region`` of that budget, so
``/api/status`` can say what holds the memory. A ``put`` that takes the sum over the budget evicts the least recently
USED entries, whichever region they are in, until it fits (the entry just put stays, even alone over the budget). An
entry's size is measured once when it is put: a frame by its arrays (``frame_bytes``: a ``str`` column's pointers, the
interned strings themselves being shared; an ``object`` column deep), containers and dataclasses by walking them (a
shared object — a ``Board``, marked ``_memo_shared`` — is counted in its own region only; a dataclass's ``_memo_skip``
fields — the Sleeper client's cached payloads — are not counted).

After an eviction pass that dropped a few MB, and after a request when the RSS grew (``relieve``, the API's
middleware), ``malloc_trim(0)`` (Linux / glibc, best effort, at most every few seconds) hands the freed pages back to
the system, so the RSS the host meters follows the work down instead of staying at its high-water mark.

Nothing here knows about pandas beyond the size estimate, nor about the API: ``src/league_lab`` (anyleague) and the
API's modules share the one process-wide ``BUDGET``.
"""

from __future__ import annotations

import ctypes
import dataclasses
import os
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any

ENV = "LEAGUE_LAB_CACHE_MB"
DEFAULT_MB = 64.0
TRIM_EVERY_S = 30.0                     # malloc_trim at most this often
TRIM_AFTER_BYTES = 8 * 1024 * 1024      # ... and only after at least this much was evicted since the last one
_MISSING = object()


def budget_mb_from_env() -> float:
    try:
        v = float(os.environ.get(ENV, "") or DEFAULT_MB)
    except ValueError:
        v = DEFAULT_MB
    return v if v > 0 else DEFAULT_MB


# ------------------------------------------------------------------------------------------------ the size estimate
SAMPLE_OVER = 256           # a container longer than this is sized from SAMPLE evenly spaced items, scaled up
SAMPLE = 64


def frame_bytes(obj: Any) -> int:
    """A frame's / series' / index's bytes: the arrays, plus every object of an ``object`` column (dicts, lists, dates,
    mixed values) counted deep. A ``str`` column counts its pointers only: the API interns every text value at the
    fetch (``db.intern_strings``) and pandas' take / reindex / merge carry the same objects, so a gsis_id is one string
    however many frames hold it — counted deep, the four leagues' caches read 119 MB against the 36 MB that emptying
    them gave back (INF-2's measurement)."""
    try:
        if hasattr(obj, "columns"):
            shallow = obj.memory_usage(index=True, deep=False)
            total = int(shallow.sum())
            idx = obj.index
            if str(idx.dtype) == "object":
                total += int(idx.memory_usage(deep=True)) - int(idx.memory_usage(deep=False))
            for i, dt in enumerate(obj.dtypes):
                if str(dt) == "object":
                    col = obj.iloc[:, i]
                    total += int(col.memory_usage(index=False, deep=True)) - int(col.memory_usage(index=False, deep=False))
            return total
        deep = str(getattr(obj, "dtype", "")) == "object"
        v = obj.memory_usage(deep=deep)
        if hasattr(obj, "index") and str(getattr(obj.index, "dtype", "")) == "object" and not deep:
            v += obj.index.memory_usage(deep=True) - obj.index.memory_usage(deep=False)
        return int(v)
    except Exception:  # noqa: BLE001 - an exotic frame: the shallow size
        return sys.getsizeof(obj)


def _sample(items: list) -> list:
    step = len(items) / SAMPLE
    return [items[int(i * step)] for i in range(SAMPLE)]


def sizeof(obj: Any, _depth: int = 0, _seen: set[int] | None = None) -> int:
    """Bytes an object holds, roughly: frames / series / arrays exactly (``deep``), containers and dataclasses by
    walking them (depth 6, every object once; a container of more than 256 items from 64 of them, scaled: a solved
    league is a few thousand small objects, sized in milliseconds), anything else by ``sys.getsizeof``. An object whose class says
    ``_memo_shared = True`` (the shared ``Board``) counts 0 when it is not the entry itself."""
    seen = set() if _seen is None else _seen
    oid = id(obj)
    if oid in seen:
        return 0
    seen.add(oid)
    if _depth > 0 and getattr(type(obj), "_memo_shared", False):
        return 0
    if hasattr(obj, "memory_usage") and hasattr(obj, "shape"):            # pandas DataFrame / Series / Index
        return frame_bytes(obj)
    nb = getattr(obj, "nbytes", None)
    if isinstance(nb, int) and hasattr(obj, "dtype"):                    # numpy array
        return nb + 112
    if _depth >= 6 or isinstance(obj, (str, bytes, int, float, bool, type(None))):
        return sys.getsizeof(obj)
    if isinstance(obj, dict):
        n = len(obj)
        items = obj.items() if n <= SAMPLE_OVER else _sample(list(obj.items()))
        part = sum(sizeof(k, _depth + 1, seen) + sizeof(v, _depth + 1, seen) for k, v in items)
        return sys.getsizeof(obj) + (part if n <= SAMPLE_OVER else part * n // SAMPLE)
    if isinstance(obj, (list, tuple, set, frozenset)):
        n = len(obj)
        vals = obj if n <= SAMPLE_OVER else _sample(list(obj))
        part = sum(sizeof(v, _depth + 1, seen) for v in vals)
        return sys.getsizeof(obj) + (part if n <= SAMPLE_OVER else part * n // SAMPLE)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        skip = getattr(type(obj), "_memo_skip", ())         # fields that are another cache's objects
        return sys.getsizeof(obj) + sum(sizeof(getattr(obj, f.name, None), _depth + 1, seen)
                                        for f in dataclasses.fields(obj) if f.name not in skip)
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict):
        return sys.getsizeof(obj) + sizeof(d, _depth + 1, seen)
    return sys.getsizeof(obj)


# ------------------------------------------------------------------------------------------------ giving memory back
_libc: Any = None
_libc_tried = False


def malloc_trim() -> bool:
    """glibc's ``malloc_trim(0)``: return the freed heap pages to the system. Linux only, best effort."""
    global _libc, _libc_tried
    if not sys.platform.startswith("linux"):
        return False
    if not _libc_tried:
        _libc_tried = True
        try:
            lib = ctypes.CDLL("libc.so.6")
            lib.malloc_trim.argtypes = [ctypes.c_size_t]
            lib.malloc_trim.restype = ctypes.c_int
            _libc = lib
        except (OSError, AttributeError):
            _libc = None
    if _libc is None:
        return False
    try:
        _libc.malloc_trim(0)
        return True
    except Exception:  # noqa: BLE001 - never load-bearing
        return False


RELIEVE_EVERY_S = 1.0                  # after a request: malloc_trim at most this often ...
RELIEVE_GROWTH_MB = 4.0                # ... and only when the RSS grew this much since the last trim
_relief = {"at": 0.0, "rss": 0.0, "trims": 0, "ms": 0.0}
_relief_lock = threading.Lock()


def relieve() -> bool:
    """After a request (the API's middleware): the request's temporaries are freed by now, but glibc keeps the pages;
    ``malloc_trim`` them when the RSS grew ``RELIEVE_GROWTH_MB`` since the last trim, at most every
    ``RELIEVE_EVERY_S``. Costs one read of ``/proc/self/statm`` otherwise. True when it trimmed."""
    now = time.monotonic()
    if now - _relief["at"] < RELIEVE_EVERY_S or not _relief_lock.acquire(blocking=False):
        return False
    try:
        rss = rss_mb() or 0.0
        if rss - _relief["rss"] < RELIEVE_GROWTH_MB:
            if rss < _relief["rss"]:
                _relief["rss"] = rss
            return False
        t0 = time.perf_counter()
        ok = malloc_trim()
        _relief.update(at=now, rss=rss_mb() or rss, trims=_relief["trims"] + int(ok),
                       ms=round((time.perf_counter() - t0) * 1000, 1))
        return ok
    finally:
        _relief_lock.release()


def relief() -> dict:
    """The trims so far (for ``/api/status``)."""
    return {"trims": _relief["trims"], "last_trim_ms": _relief["ms"]}


def rss_mb() -> float | None:
    """The process's resident memory now (``/proc/self/statm``), else its peak (``getrusage``), in MB."""
    try:
        with open("/proc/self/statm") as f:
            pages = int(f.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / 1048576, 1)
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (1048576 if sys.platform == "darwin" else 1024), 1)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------------------------------------ the budget
@dataclasses.dataclass
class _Entry:
    expires: float
    value: Any
    nbytes: int


class Budget:
    """One LRU order and one byte budget over every ``Region``."""

    def __init__(self, mb: float | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._lock = threading.RLock()
        self._order: OrderedDict[tuple[str, Hashable], None] = OrderedDict()   # least recently used first
        self.regions: dict[str, Region] = {}
        self.nbytes = 0
        self.limit = int((mb if mb is not None else budget_mb_from_env()) * 1048576)
        self.clock = clock
        self.evictions = 0
        self._evicted_since_trim = 0
        self._last_trim = 0.0

    def configure(self, mb: float | None = None) -> None:
        """A new budget (``None``: ``LEAGUE_LAB_CACHE_MB`` again); evicts at once if the caches are over it."""
        with self._lock:
            self.limit = int((mb if mb is not None else budget_mb_from_env()) * 1048576)
            self._evict(keep=None)
        self._maybe_trim()

    def region(self, name: str, ttl: float = 600.0, max_entries: int | None = None, *, published: bool = False) -> Region:
        with self._lock:
            r = self.regions.get(name)
            if r is None:
                r = self.regions[name] = Region(self, name, ttl, max_entries)
            r.published = r.published or published      # ---- IS-4: "holds published data" (dropped at a new publication)
            return r

    # ---- IS-4 (Wave I-S): a new publication drops every region that registered itself as holding published data
    def drop_published(self) -> list[str]:
        """Clear every ``published`` region; the names cleared."""
        with self._lock:
            regions = [r for r in self.regions.values() if r.published]
        for r in regions:
            r.clear()
        return sorted(r.name for r in regions)
    # ---- end IS-4

    def touch(self, slot: tuple[str, Hashable]) -> None:
        self._order.move_to_end(slot)

    def _drop(self, slot: tuple[str, Hashable]) -> int:
        """Remove one entry (lock held); its bytes."""
        self._order.pop(slot, None)
        r = self.regions[slot[0]]
        e = r._entries.pop(slot[1], None)
        if e is None:
            return 0
        r.nbytes -= e.nbytes
        self.nbytes -= e.nbytes
        return e.nbytes

    def _evict(self, keep: tuple[str, Hashable] | None) -> None:
        """Over the budget (lock held): the expired entries first, then the least recently used, never ``keep``."""
        if self.nbytes <= self.limit:
            return
        now = self.clock()
        freed = 0
        for slot in [s for s in self._order if s != keep and self.regions[s[0]]._entries[s[1]].expires <= now]:
            freed += self._drop(slot)
            self.evictions += 1
        while self.nbytes > self.limit and self._order:
            slot = next(iter(self._order))
            if slot == keep:
                if len(self._order) == 1:
                    break
                self._order.move_to_end(slot)
                continue
            freed += self._drop(slot)
            self.evictions += 1
        self._evicted_since_trim += freed

    def _maybe_trim(self) -> None:
        if self._evicted_since_trim < TRIM_AFTER_BYTES:
            return
        now = time.monotonic()
        if now - self._last_trim < TRIM_EVERY_S:
            return
        self._last_trim, self._evicted_since_trim = now, 0
        malloc_trim()

    def clear(self) -> None:
        with self._lock:
            for r in self.regions.values():
                r._entries.clear()
                r.nbytes = 0
            self._order.clear()
            self.nbytes = 0

    def report(self) -> dict:
        """``/api/status``'s ``memory`` block (less the RSS): MB per region, their sum, the budget."""
        with self._lock:
            regions = {n: round(r.nbytes / 1048576, 1) for n, r in sorted(self.regions.items())}
            entries = {n: len(r._entries) for n, r in sorted(self.regions.items())}
            return {"cache_mb": round(self.nbytes / 1048576, 1), "budget_mb": round(self.limit / 1048576, 1),
                    "regions": regions, "entries": entries, "evictions": self.evictions}


class Region:
    """One named cache in the budget: ``get`` / ``put`` with a TTL per entry (the region's, or the put's own)."""

    def __init__(self, budget: Budget, name: str, ttl: float, max_entries: int | None) -> None:
        self.budget, self.name, self.ttl, self.max_entries = budget, name, float(ttl), max_entries
        self.published = False          # ---- IS-4: set by region(..., published=True)
        self._entries: dict[Hashable, _Entry] = {}
        self.nbytes = 0

    def get(self, key: Hashable, default: Any = None) -> Any:
        """The live value (and it becomes the most recently used), else ``default``; an expired entry is dropped."""
        b = self.budget
        with b._lock:
            e = self._entries.get(key)
            if e is None:
                return default
            if e.expires <= b.clock():
                b._drop((self.name, key))
                return default
            b.touch((self.name, key))
            return e.value

    def __contains__(self, key: Hashable) -> bool:
        return self.get(key, _MISSING) is not _MISSING

    def put(self, key: Hashable, value: Any, ttl: float | None = None, nbytes: int | None = None) -> Any:
        """Keep ``value`` for ``ttl`` seconds (the region's TTL by default); evict others over the budget. ``value``."""
        size = sizeof(value) if nbytes is None else int(nbytes)
        b = self.budget
        slot = (self.name, key)
        with b._lock:
            b._drop(slot)
            self._entries[key] = _Entry(b.clock() + (self.ttl if ttl is None else float(ttl)), value, size)
            b._order[slot] = None
            self.nbytes += size
            b.nbytes += size
            if self.max_entries is not None and len(self._entries) > self.max_entries:
                for k in [s[1] for s in b._order if s[0] == self.name and s != slot][: len(self._entries) - self.max_entries]:
                    b._evicted_since_trim += b._drop((self.name, k))
                    b.evictions += 1
            b._evict(keep=slot)
        b._maybe_trim()
        return value

    def pop(self, key: Hashable) -> None:
        with self.budget._lock:
            self.budget._drop((self.name, key))

    def clear(self) -> None:
        b = self.budget
        with b._lock:
            for k in list(self._entries):
                b._drop((self.name, k))

    def __len__(self) -> int:
        return len(self._entries)

    def keys(self) -> list[Hashable]:
        with self.budget._lock:
            return list(self._entries)


BUDGET = Budget()


def region(name: str, ttl: float = 600.0, max_entries: int | None = None, *, published: bool = False) -> Region:
    """The process-wide budget's region ``name`` (made on first use). ``published=True``: it holds data read from the
    published tables, and a new publication drops it (``drop_published``; IS-4)."""
    return BUDGET.region(name, ttl, max_entries, published=published)


def drop_published() -> list[str]:
    """IS-4: clear every region that holds published data (the process-wide budget's); the names cleared."""
    return BUDGET.drop_published()


PLAN_MB = 512          # Render's Starter plan (docs/DEPLOY.md § Memory): the RSS the host meters against


def directory_words(m: dict) -> str:
    """IL-4 (Wave I-L): ``/api/status``'s ``memory.directory`` in one line (the console's Data Status page, next to
    ``status_words``): "Sleeper's player directory: 12,229 players, 15 fields, 8.6 MB (outside the caches' budget)."."""
    d = (m or {}).get("directory")
    if not isinstance(d, dict):
        return "Sleeper's player directory: not reported by this server."
    if not d.get("loaded"):
        return "Sleeper's player directory: not read yet (the first league opened reads it)."
    return (f"Sleeper's player directory: {int(d.get('rows') or 0):,} players, {int(d.get('fields') or 0)} fields, "
            f"{float(d.get('mb') or 0):.1f} MB (outside the caches' budget).")


def status_words(m: dict, plan_mb: int = PLAN_MB) -> str:
    """``/api/status``'s ``memory`` block in one line (the console's Data Status page): "412 MB of the plan's 512 in
    use; the caches hold 61 of their 64 MB (decisions 25, sql 22, league weeks 19)"."""
    if not m or m.get("rss_mb") is None:
        return "The API did not say how much memory it uses."
    regions = sorted(((v, k) for k, v in (m.get("regions") or {}).items() if v and v >= 1), reverse=True)[:4]
    parts = ", ".join(f"{k.replace('_', ' ')} {v:.0f}" for v, k in regions)
    line = f"{m['rss_mb']:.0f} MB of the plan's {plan_mb} in use"
    if m.get("budget_mb"):
        line += f"; the caches hold {m.get('cache_mb', 0):.0f} of their {m['budget_mb']:.0f} MB"
        line += f" ({parts})" if parts else ""
    return line + "."

