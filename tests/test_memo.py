"""INF-2 (Wave I-J, the memory diet): ``league_lab.memo`` — one least-recently-used order and one byte budget over
every in-process cache of the API (no database: a fake clock, sizes given)."""

from __future__ import annotations

import pandas as pd

from league_lab import memo

MB = 1048576


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _budget(mb: float = 1.0) -> tuple[memo.Budget, Clock]:
    c = Clock()
    return memo.Budget(mb, clock=c), c


def test_eviction_takes_the_least_recently_used_across_regions():
    b, _ = _budget(1.0)
    sql, priced = b.region("sql"), b.region("priced")
    sql.put("a", "A", nbytes=300_000)
    priced.put("p", "P", nbytes=300_000)
    sql.put("b", "B", nbytes=300_000)
    assert sql.get("a") == "A"                       # "a" used again: "p" is now the least recently used
    sql.put("c", "C", nbytes=300_000)                # 1.2 MB > 1 MB: one entry goes
    assert priced.get("p") is None
    assert [sql.get(k) for k in "abc"] == ["A", "B", "C"]
    assert b.nbytes == 900_000 and b.evictions == 1
    priced.put("q", "Q", nbytes=500_000)             # goes over by 0.4 MB: the two least recently used go ("a", "b")
    assert sql.get("a") is None and sql.get("b") is None and sql.get("c") == "C" and priced.get("q") == "Q"
    assert b.report()["regions"] == {"priced": round(500_000 / MB, 1), "sql": round(300_000 / MB, 1)}


def test_the_entry_just_put_stays_even_alone_over_the_budget():
    b, _ = _budget(1.0)
    r = b.region("ros")
    r.put("small", 1, nbytes=100)
    r.put("huge", 2, nbytes=3 * MB)
    assert r.get("huge") == 2 and r.get("small") is None
    assert b.nbytes == 3 * MB


def test_expired_entries_go_first_and_are_never_returned():
    b, clock = _budget(1.0)
    r = b.region("decisions", ttl=600)
    r.put("old", "o", ttl=120, nbytes=400_000)
    r.put("young", "y", nbytes=400_000)
    assert r.get("old") == "o"                       # the most recently used now, but it expires first
    clock.t += 121
    r.put("new", "n", nbytes=400_000)                # over: the expired "old" goes before the LRU "young"
    assert r.get("young") == "y" and r.get("new") == "n" and r.get("old") is None
    clock.t += 600
    assert r.get("young") is None and len(r) == 1    # expired on read


def test_max_entries_bounds_a_region_by_its_own_lru():
    b, _ = _budget(100.0)
    boards = b.region("boards", max_entries=2)
    other = b.region("sql")
    other.put("x", "X", nbytes=10)
    for w in (1, 2, 3):
        boards.put(w, f"board {w}", nbytes=10)
    assert boards.keys() == [2, 3] and other.get("x") == "X"


def test_a_put_replaces_and_reprices_and_clear_frees():
    b, _ = _budget(1.0)
    r = b.region("about")
    r.put("k", "v1", nbytes=100)
    r.put("k", "v2", nbytes=250)
    assert r.get("k") == "v2" and b.nbytes == 250 and r.nbytes == 250
    r.pop("k")
    assert b.nbytes == 0 and "k" not in r
    r.put("k", "v", nbytes=5)
    b.clear()
    assert b.nbytes == 0 and len(r) == 0


def test_configure_shrinks_and_evicts():
    b, _ = _budget(10.0)
    r = b.region("sql")
    for i in range(5):
        r.put(i, i, nbytes=MB)
    b.configure(2.5)
    assert r.keys() == [3, 4] and b.limit == int(2.5 * MB)


def test_sizes_frames_by_their_arrays_and_skips_shared_objects():
    df = pd.DataFrame({"g": ["00-0037840"] * 1000, "x": range(1000)})
    size = memo.sizeof(df)
    # a pointer (python strings: the API, interned) or the characters inline (pyarrow strings: this repository's root
    # environment) + 8 bytes an int — never a whole string object per row
    assert 16_000 <= size < 30_000

    class Shared:
        _memo_shared = True

        def __init__(self) -> None:
            self.frame = df

    holder = {"board": Shared(), "own": [1, 2, 3]}
    assert memo.sizeof(holder) < 1000                # the shared object is counted in its own region
    assert memo.sizeof(holder["board"]) >= size      # ... where it is the entry itself


def test_budget_from_the_environment(monkeypatch):
    monkeypatch.setenv(memo.ENV, "60")
    assert memo.budget_mb_from_env() == 60.0
    monkeypatch.setenv(memo.ENV, "nonsense")
    assert memo.budget_mb_from_env() == memo.DEFAULT_MB
    monkeypatch.delenv(memo.ENV)
    assert memo.Budget().limit == int(memo.DEFAULT_MB * MB)


def test_status_words_say_the_rss_and_the_biggest_regions():
    m = {"rss_mb": 248.4, "cache_mb": 61.2, "budget_mb": 160.0,
         "regions": {"sql": 22.1, "decisions": 24.8, "league_weeks": 19.2, "boards": 4.6, "about": 0.0, "ros": 1.2}}
    assert memo.status_words(m) == ("248 MB of the plan's 512 in use; the caches hold 61 of their 160 MB "
                                    "(decisions 25, sql 22, league weeks 19, boards 5).")
    assert memo.status_words({}) == "The API did not say how much memory it uses."
