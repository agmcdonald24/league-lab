"""Wave I-U, IU-6: a blog post's cover (blog_store.py, blog.py; scripts/hosted_blog.sql's `cover` column), the link
preview a crawler reads without running script, and the frame-src the YouTube embed needs (security.py).

Same setup as test_io3 (its fixtures: the `blog` schema applied with the pipeline role, accounts on with the stub
mailer, every account an `@io3.test` address deleted afterwards). One test drops the `cover` column (the hosted
database runs the new API for some hours before the nightly adds it) and puts it back by re-running the SQL file.
"""

from __future__ import annotations

import io
import re
import zipfile

import psycopg
import pytest

from league_lab_api import blog, blog_store, security

from .test_in1 import dist  # noqa: F401
from .test_io3 import (  # noqa: F401
    JPG,
    PNG,
    SAME,
    SQL_FILE,
    _pipeline_dsn,
    api,
    editor,
    folder,
    new_post,
    q,
    save,
    schema,
    sign_in,
    upload,
)

ORIGIN = "https://isuckatfantasy.io"


def _meta(text: str, prop: str) -> str | None:
    m = re.search(rf'<meta (?:property|name)="{re.escape(prop)}" content="([^"]*)"', text)
    return m.group(1) if m else None


def _publish(c, p: dict) -> dict:
    r = c.post(f"/api/blog/posts/{p['id']}/publish", headers=SAME)
    assert r.status_code == 200, r.text
    return r.json()


def _schema_sql() -> None:
    with psycopg.connect(_pipeline_dsn(), autocommit=True, connect_timeout=5) as conn, conn.transaction():
        conn.execute(SQL_FILE.read_text())


def _drop_cover() -> None:
    with psycopg.connect(_pipeline_dsn(), autocommit=True, connect_timeout=5) as conn:
        conn.execute("alter table blog.posts drop column if exists cover")


def test_a_cover_is_stored_shown_in_the_list_and_previewed(dist, editor):  # noqa: F811
    blog_store.reset()
    assert editor.get("/api/blog/mine").json()["limits"]["cover"] is True
    img = upload(editor, PNG).json()
    p = new_post(editor, title="With a <cover> & \"quotes\"", summary="The cover's post.", body="Words.")
    assert p.get("cover") is None or "cover" not in p
    r = save(editor, p, cover=img["id"])
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["cover"] == img["id"] and p["revision"] == 2
    assert editor.get(f"/api/blog/posts/{p['id']}").json()["cover"] == img["id"]
    # a save without `cover` (an older editor tab) keeps it; the same cover again writes nothing
    r = save(editor, p, body="Words, more.")
    assert r.status_code == 200 and r.json()["cover"] == img["id"]
    p = r.json()
    same = save(editor, p, cover=img["id"])
    assert same.status_code == 200 and same.json()["revision"] == p["revision"]
    _publish(editor, p)
    listed = [x for x in editor.get("/api/blog").json()["posts"] if x["slug"] == p["slug"]]
    assert listed and listed[0]["image"] == f"/blog/img/db/{img['id']}"
    one = editor.get(f"/api/blog/{p['slug']}").json()
    assert one["image"] == f"/blog/img/db/{img['id']}"
    # the crawler's HTML (no script runs): the cover's absolute https URL, every text escaped
    page = editor.get(f"/blog/{p['slug']}")
    assert page.status_code == 200
    assert _meta(page.text, "og:image") == f"{ORIGIN}/blog/img/db/{img['id']}"
    assert _meta(page.text, "twitter:image") == f"{ORIGIN}/blog/img/db/{img['id']}"
    assert _meta(page.text, "twitter:card") == "summary_large_image"
    assert _meta(page.text, "og:title") == "With a &lt;cover&gt; &amp; &quot;quotes&quot; · isuckatfantasy"
    assert "<cover>" not in page.text
    # the export carries it as the file's image line, and a file reads it back
    z = zipfile.ZipFile(io.BytesIO(editor.get("/api/blog/export").content))
    text = z.read(next(n for n in z.namelist() if p["slug"] in n)).decode()
    assert f"image: /blog/img/db/{img['id']}" in text
    assert blog.parse_post(f"2026-10-09-{p['slug']}.md", text)["image"] == f"/blog/img/db/{img['id']}"
    # removing the cover: null; the post as before (the default preview picture)
    cur = editor.get(f"/api/blog/posts/{p['id']}").json()
    r = save(editor, cur, cover=None)
    assert r.status_code == 200 and r.json()["cover"] is None
    page = editor.get(f"/blog/{p['slug']}")
    assert _meta(page.text, "og:image") == f"{ORIGIN}/og.png"


def test_a_deleted_picture_leaves_the_post_without_a_cover(editor):  # noqa: F811
    blog_store.reset()
    img = upload(editor, JPG).json()
    p = save(editor, new_post(editor, title="Gone cover"), cover=img["id"]).json()
    _publish(editor, p)
    assert editor.delete(f"/api/blog/images/{img['id']}", headers=SAME).json() == {"ok": True}
    assert editor.get(f"/api/blog/posts/{p['id']}").json()["cover"] is None
    assert [x["image"] for x in editor.get("/api/blog").json()["posts"] if x["slug"] == p["slug"]] == [None]


def test_a_cover_is_one_of_the_editors_own_pictures(editor, monkeypatch):  # noqa: F811
    blog_store.reset()
    p = new_post(editor, title="Cover attacks")
    for bad in ("javascript:alert(1)", "data:image/png;base64,AAAA", "/blog/img/db/x", "../../etc/passwd",
                "00000000-0000-4000-8000-000000000000",              # well formed, no such picture
                "00000000-0000-4000-8000-00000000000'", "00000000-0000-4000-8000-0000000000/0",
                "00000000-0000-4000-8000-000000000000 ", "ABCDEF00-0000-4000-8000-000000000000", "x" * 64):
        r = save(editor, p, cover=bad)                              # (a trailing space is trimmed: still no picture)
        assert r.status_code == 400 and r.json()["code"] == "bad_cover", (bad, r.text)
        assert r.json()["error"] == blog_store.COVER_WORDS
    assert save(editor, p, cover="x" * 65).status_code == 422               # over the field's bound: the model's 422
    assert save(editor, p, cover=12).status_code == 422
    # another editor's picture: the same answer as no picture at all
    mine = upload(editor, PNG).json()
    other_uid = sign_in(editor, "other-editor")
    first = blog_store.editors()
    monkeypatch.setenv(blog_store.EDITORS_ENV, ",".join([*first, other_uid]))
    theirs = upload(editor, JPG).json()
    other_post = new_post(editor, title="Theirs")
    r = save(editor, other_post, cover=mine["id"])
    assert r.status_code == 400 and r.json()["code"] == "bad_cover"
    assert save(editor, other_post, cover=theirs["id"]).status_code == 200
    # nothing was stored by the refusals
    assert q("select cover from blog.posts where id = %s", p["id"])[0][0] is None
    # a signed-out browser and a cross-site page cannot set one
    editor.cookies.clear()
    assert save(editor, other_post, cover=None).status_code == 401
    r = editor.put(f"/api/blog/posts/{other_post['id']}", json={"revision": 2, "cover": None},
                   headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_without_the_cover_column_every_read_and_save_works_as_before(dist, editor):  # noqa: F811
    blog_store.reset()
    img = upload(editor, PNG).json()
    p = new_post(editor, title="No column yet", summary="Before the nightly.")
    _drop_cover()
    try:
        blog_store.reset()
        mine = editor.get("/api/blog/mine")
        assert mine.status_code == 200 and mine.json()["limits"]["cover"] is False
        got = editor.get(f"/api/blog/posts/{p['id']}")
        assert got.status_code == 200 and got.json()["cover"] is None
        r = save(editor, got.json(), body="Saved with no column.", cover=img["id"])   # quietly not stored
        assert r.status_code == 200, r.text
        assert r.json()["cover"] is None and r.json()["body"] == "Saved with no column."
        r = save(editor, r.json(), body="And again.")
        assert r.status_code == 200
        _publish(editor, r.json())
        listed = [x for x in editor.get("/api/blog").json()["posts"] if x["slug"] == p["slug"]]
        assert listed and listed[0]["image"] is None
        assert editor.get(f"/api/blog/{p['slug']}").status_code == 200
        page = editor.get(f"/blog/{p['slug']}")
        assert page.status_code == 200 and _meta(page.text, "og:image") == f"{ORIGIN}/og.png"
        assert editor.get("/").status_code == 200 and editor.get("/blog").status_code == 200
        assert editor.get("/blog/rss.xml").status_code == 200 and editor.get("/sitemap.xml").status_code == 200
        assert editor.get("/api/blog/export").status_code == 200
        # the column arrives (the nightly) — seen without a restart once the minute is up
        _schema_sql()
        assert editor.get("/api/blog/mine").json()["limits"]["cover"] is False      # still the cached answer …
        blog_store._cover["next"] = 0.0                                             # … a minute later
        assert editor.get("/api/blog/mine").json()["limits"]["cover"] is True
        cur = editor.get(f"/api/blog/posts/{p['id']}").json()
        r = save(editor, cur, cover=img["id"])
        assert r.status_code == 200 and r.json()["cover"] == img["id"]
    finally:
        _schema_sql()
        blog_store.reset()


def test_the_csp_frames_only_youtube_nocookie(api):  # noqa: F811
    csp = api.get("/blog").headers["content-security-policy"]
    frames = [d for d in csp.split("; ") if d.startswith("frame-src")]
    assert frames == ["frame-src https://www.youtube-nocookie.com"]
    assert "frame-ancestors 'none'" in csp and "default-src 'self'" in csp
    assert "youtube" not in csp.replace("frame-src https://www.youtube-nocookie.com", "")
    assert "twitter" not in csp and "x.com" not in csp
    assert security.csp().count("youtube") == 1


@pytest.mark.parametrize("name, image", [
    ("2026-10-09-a.md", "/blog/img/db/0123abcd-0000-4000-8000-000000000000"),
    ("2026-10-09-b.md", "chart.png"),
])
def test_a_file_names_its_picture(name, image):
    text = f"---\ntitle: T\nimage: {image}\n---\n\nBody.\n"
    got = blog.parse_post(name, text)["image"]
    assert got == (image if image.startswith("/") else f"/blog/img/{image}")


@pytest.mark.parametrize("bad", ["/blog/img/db/0123ABCD-0000-4000-8000-000000000000", "/blog/img/db/../x.png",
                                 "https://evil.example/x.png", "javascript:alert(1)", "/blog/img/db/x"])
def test_a_file_cannot_name_another_picture(bad):
    assert blog.parse_post("2026-10-09-c.md", f"---\ntitle: T\nimage: {bad}\n---\n\nBody.\n")["image"] is None
