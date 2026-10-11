"""Wave I-Y, IY-3: a published post never disappears because one read failed (blog_store's last good answers; blog.py's
503 for a post it cannot read and has never read).

Live, 2026-10-11 16:33 ET: one read that raised hid every published post for a minute and 404-ed its address. Here the
public reads are made to raise — the pool not handing out a connection (PoolTimeout), a dropped connection
(OperationalError), a statement timeout (QueryCanceled) — through a stand-in for `db` that only blog_store sees (the
accounts and the editor keep the real one). The region's clock is faked to show the retry comes within RETRY_S.
Same setup as test_io3 (its fixtures; every account `@io3.test`, deleted afterwards).
"""

from __future__ import annotations

import logging

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from league_lab_api import blog, blog_store, db

from .test_in1 import dist  # noqa: F401
from .test_io3 import PNG, SAME, api, editor, folder, new_post, schema, upload  # noqa: F401

FAILURES = [PoolTimeout("couldn't get a connection after 5.00 sec"), psycopg.OperationalError("server closed the connection"),
            psycopg.errors.QueryCanceled("canceling statement due to statement timeout")]


class _Broken:
    """`db` as blog_store sees it: `pool()` hands out nothing (raises `exc`) while `down`; everything else is db's."""

    def __init__(self, exc: Exception):
        self.exc, self.down, self.tries = exc, False, 0

    def pool(self):
        real = db.pool()
        outer = self

        class _P:
            def connection(self, timeout=None):
                outer.tries += 1
                if outer.down:
                    raise outer.exc
                return real.connection(timeout=timeout)
        return _P()

    def __getattr__(self, name):
        return getattr(db, name)


class _Clock:
    def __init__(self):
        import time
        self.t = time.monotonic()

    def __call__(self):
        return self.t


@pytest.fixture
def broken(monkeypatch, request):
    b = _Broken(request.param)
    monkeypatch.setattr(blog_store, "db", b)
    clock = _Clock()
    monkeypatch.setattr(blog_store._pub.budget, "clock", clock)
    b.clock = clock
    return b


def _publish(c, p):
    r = c.post(f"/api/blog/posts/{p['id']}/publish", headers=SAME)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("broken", FAILURES, indirect=True, ids=["PoolTimeout", "OperationalError", "QueryCanceled"])
def test_a_failed_read_serves_the_last_good_answer(dist, editor, broken, caplog):  # noqa: F811
    blog_store.reset()
    img = upload(editor, PNG).json()
    p = _publish(editor, new_post(editor, title="Still here", summary="It stays.", body=f"Words.\n\n![x]({img['url']})"))
    # a good read: the list, the post, its picture, its page
    assert [x["slug"] for x in editor.get("/api/blog").json()["posts"]].count(p["slug"]) == 1
    assert editor.get(f"/api/blog/{p['slug']}").json()["markdown"].startswith("Words.")
    assert editor.get(img["url"]).status_code == 200
    # the store stops answering; the minute's cache runs out
    broken.down = True
    broken.clock.t += blog_store.PUBLIC_TTL_S + 1
    with caplog.at_level(logging.WARNING, logger="league_lab_api.blog_store"):
        listed = editor.get("/api/blog")
        one = editor.get(f"/api/blog/{p['slug']}")
        pic = editor.get(img["url"])
        page = editor.get(f"/blog/{p['slug']}")
        again = editor.get("/api/blog")
    assert listed.status_code == 200 and p["slug"] in [x["slug"] for x in listed.json()["posts"]]
    assert listed.headers["cache-control"] == "public, max-age=0, must-revalidate"            # live() stays true
    assert one.status_code == 200 and one.json()["markdown"].startswith("Words.")
    assert pic.status_code == 200 and pic.content == PNG
    assert page.status_code == 200 and "<title>Still here · isuckatfantasy</title>" in page.text
    assert again.status_code == 200 and p["slug"] in [x["slug"] for x in again.json()["posts"]]
    warned = [r for r in caplog.records if r.levelno == logging.WARNING and "not read" in r.getMessage()]
    assert {r.getMessage().split(" not read")[0] for r in warned} == {"blog: the published list", "blog: a post's body",
                                                                       "blog: a picture"}
    assert all(type(broken.exc).__name__ in r.getMessage() for r in warned)
    assert all(str(broken.exc) not in r.getMessage() for r in warned)                         # the class, never the text
    assert len(warned) == 3                                                                   # once per failure
    # the retry comes within RETRY_S, not the minute
    tries = broken.tries
    editor.get("/api/blog")
    assert broken.tries == tries                                                              # still cached …
    broken.clock.t += blog_store.RETRY_S + 0.5
    editor.get("/api/blog")
    assert broken.tries == tries + 1                                                          # … then tried again
    # a post published meanwhile (the editor writes on its own connection): not readable yet, the last good list stays
    q = _publish(editor, new_post(editor, title="Published after", body="New."))
    slugs = [x["slug"] for x in editor.get("/api/blog").json()["posts"]]
    assert p["slug"] in slugs and q["slug"] not in slugs
    # the store is back: at the next read (within RETRY_S) the new post appears
    broken.down = False
    broken.clock.t += blog_store.RETRY_S + 0.5
    slugs = [x["slug"] for x in editor.get("/api/blog").json()["posts"]]
    assert p["slug"] in slugs and q["slug"] in slugs
    assert editor.get(f"/api/blog/{q['slug']}").status_code == 200


@pytest.mark.parametrize("broken", FAILURES[:1], indirect=True, ids=["PoolTimeout"])
def test_never_read_a_database_post_is_503_and_the_files_still_answer(dist, editor, broken):  # noqa: F811
    blog_store.reset()
    p = _publish(editor, new_post(editor, title="Never read here", body="Body."))
    blog_store.reset()                                       # a process that has not read the store yet …
    broken.down = True                                       # … and cannot
    listed = editor.get("/api/blog")
    assert listed.status_code == 200 and [x["slug"] for x in listed.json()["posts"]] == ["from-a-file"]
    assert listed.headers["cache-control"] == "public, max-age=5"
    one = editor.get(f"/api/blog/{p['slug']}")
    assert one.status_code == 503 and one.json()["error"] == "This post did not load. Try again in a few seconds."
    assert one.headers["cache-control"] == "no-store" and one.headers["retry-after"] == "5"
    page = editor.get(f"/blog/{p['slug']}")
    assert page.status_code == 503 and page.headers["cache-control"] == "no-store" and page.headers["retry-after"] == "5"
    assert editor.get("/api/blog/from-a-file").status_code == 200                            # the files' post
    assert editor.get("/blog/from-a-file").status_code == 200
    assert editor.get("/blog/rss.xml").headers["cache-control"] == "public, max-age=5"
    assert editor.get("/sitemap.xml").headers["cache-control"] == "public, max-age=5"
    gone = editor.get("/blog/img/db/00000000-0000-4000-8000-000000000000")       # unknown, not "no picture"
    assert gone.status_code == 503 and gone.headers["cache-control"] == "no-store" and gone.headers["retry-after"] == "5"
    # back: the post is there again (and a slug nobody has is the 404 it always was)
    broken.down = False
    broken.clock.t += blog_store.RETRY_S + 0.5
    assert editor.get(f"/api/blog/{p['slug']}").status_code == 200
    nope = editor.get("/api/blog/no-such-post")
    assert nope.status_code == 404 and nope.json()["error"] == blog.NOT_FOUND and nope.headers["cache-control"] == "no-store"
    assert editor.get("/blog/rss.xml").headers["cache-control"] == blog.FEED_CACHE


def test_the_schema_absent_is_a_real_state_kept_a_minute(api, monkeypatch):  # noqa: F811
    blog_store.reset()
    monkeypatch.setattr(blog_store, "TABLES", ("blog.absent_iy3", "blog.absent_iy3_revisions", "blog.absent_iy3_images"))
    assert blog_store.published_meta() == [] and blog_store.live() is False and blog_store.unread() is False
    r = api.get("/api/blog/no-such-post")
    assert r.status_code == 404 and r.json()["error"] == blog.NOT_FOUND
    assert api.get("/api/blog").headers["cache-control"] == "public, max-age=300"


def test_an_unpublish_here_is_not_served_from_the_last_good(editor, monkeypatch):  # noqa: F811
    blog_store.reset()
    p = _publish(editor, new_post(editor, title="Taken down", body="Gone soon."))
    assert editor.get(f"/api/blog/{p['slug']}").status_code == 200
    assert editor.post(f"/api/blog/posts/{p['id']}/unpublish", headers=SAME).status_code == 200
    b = _Broken(FAILURES[0])
    b.down = True
    monkeypatch.setattr(blog_store, "db", b)
    assert p["slug"] not in [x["slug"] for x in editor.get("/api/blog").json()["posts"]]
    assert editor.get(f"/api/blog/{p['slug']}").status_code == 404                           # the good list: not there


def test_the_last_good_answers_are_bounded():
    blog_store.reset()
    for k in range(blog_store.BODY_ENTRIES + 5):
        blog_store._keep(blog_store._good_bodies, f"s{k}", "x", blog_store.BODY_ENTRIES)
    for k in range(blog_store.GOOD_IMAGES + 5):
        blog_store._keep(blog_store._good_images, f"i{k}", ("png", b"x"), blog_store.GOOD_IMAGES)
    assert len(blog_store._good_bodies) == blog_store.BODY_ENTRIES == 40
    assert len(blog_store._good_images) == blog_store.GOOD_IMAGES == 20
    assert "s0" not in blog_store._good_bodies and f"s{blog_store.BODY_ENTRIES + 4}" in blog_store._good_bodies
    blog_store.reset()
