"""IT-4 (Wave I-T): a decision never straddles a publication (db.one_publication); the API's connections never prepare."""

from __future__ import annotations

import pytest

from league_lab_api import db


def _ids(monkeypatch, seq):
    it = iter(seq)
    monkeypatch.setattr(db, "publication_id", lambda: next(it))


def test_the_same_publication_throughout_computes_once(monkeypatch):
    _ids(monkeypatch, ["A", "A"])
    calls = []
    assert db.one_publication(lambda: calls.append(1) or len(calls)) == 1 and len(calls) == 1


def test_a_publication_that_flips_between_two_queries_is_computed_again_on_the_new_one(monkeypatch):
    """The fake id flips between the decision's two reads: the first answer mixes A and B, so it is thrown away; the
    published caches are dropped and the decision is computed once more, wholly on B."""
    _ids(monkeypatch, ["A", "B", "B"])
    from league_lab import memo
    reg = memo.region("it4_published", published=True)
    reg.put("board", "A's board")
    board = {"pub": "A"}

    def decision():
        first = reg.get("board") or f"{board['pub']}'s board"     # query 1: the (possibly cached) board
        board["pub"] = "B"                                        # the publication lands between the two queries
        second = f"{board['pub']}'s record"                       # query 2
        return (first, second)
    assert db.one_publication(decision) == ("B's board", "B's record")
    assert reg.get("board") is None


def test_a_second_flip_during_the_retry_is_a_503_in_words_never_a_mixed_answer(monkeypatch):
    _ids(monkeypatch, ["A", "B", "C"])
    with pytest.raises(db.DataNotReady, match="being replaced"):
        db.one_publication(lambda: 1)


def test_no_publication_comment_is_todays_behaviour(monkeypatch):
    _ids(monkeypatch, [None, None])
    assert db.one_publication(lambda: 7) == 7


def test_the_pool_and_the_one_off_connections_never_prepare(monkeypatch):
    import psycopg
    seen = []
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: seen.append(k) or (_ for _ in ()).throw(psycopg.OperationalError("x")))
    for fn in (db._writer_conn, lambda: db._rw_conn("accounts")):
        db._writer = None
        with pytest.raises(psycopg.OperationalError):
            fn()
    assert seen and all("prepare_threshold" in k and k["prepare_threshold"] is None for k in seen)
    import inspect
    assert '"prepare_threshold": None' in inspect.getsource(db.pool)
