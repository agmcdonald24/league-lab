"""Wave I-O, IO-3: the blog editor (league_lab_api/blog_store.py, blog.py's merged public reads; docs/BLOG.md).

On the clone (`.env`'s database) with accounts on and the stub mailer (`LEAGUE_LAB_ACCOUNTS=on`: nothing is sent); the
`blog` schema from scripts/hosted_blog.sql (applied here with the pipeline role, twice: idempotent). The API writes
with the read-only app role exactly as on Render. Every account the tests make is an `@io3.test` address; its posts
and the account are deleted afterwards. The blog's files come from a temporary folder (LEAGUE_LAB_BLOG_DIR).
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from league_lab_api import accounts, blog, blog_store, main, ratelimit
from league_lab_api.main import app
from league_lab_api.settings import ROOT

from .conftest import DB_OK

SQL_FILE = ROOT / "scripts" / "hosted_blog.sql"
DOMAIN = "io3.test"
ID = "00000000-0000-4000-8000-000000000000"
SAME = {"Origin": "http://testserver"}
EVIL = {"Origin": "https://evil.example"}


def _pipeline_dsn() -> str:
    from league_lab.config import get_settings
    return get_settings().pipeline_dsn()


def q(sql: str, *params):
    with psycopg.connect(main._app_dsn(), autocommit=False) as conn:
        conn.execute("set transaction read write")
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur.description else None


def _cleanup() -> None:
    with psycopg.connect(main._app_dsn(), autocommit=False) as conn:
        conn.execute("set transaction read write")
        conn.execute("delete from blog.posts where account_id in (select id from accounts.users where email like %s)",
                     (f"%@{DOMAIN}",))
        conn.execute("delete from blog.images where account_id in (select id from accounts.users where email like %s)",
                     (f"%@{DOMAIN}",))
        conn.execute("delete from accounts.users where email like %s", (f"%@{DOMAIN}",))
        conn.execute("delete from accounts.login_links where user_email like %s", (f"%@{DOMAIN}",))


@pytest.fixture(scope="module")
def schema():
    if not DB_OK:
        pytest.skip("database not reachable")
    try:
        with psycopg.connect(_pipeline_dsn(), autocommit=True, connect_timeout=5) as conn:
            for _ in range(2):
                with conn.transaction():
                    conn.execute(SQL_FILE.read_text())
    except psycopg.errors.InsufficientPrivilege:
        pass
    with psycopg.connect(main._app_dsn(), autocommit=True) as conn:
        if conn.execute("select to_regclass('accounts.users'), to_regclass('blog.posts')").fetchone() is None or None in \
                conn.execute("select to_regclass('accounts.users'), to_regclass('blog.posts')").fetchone():
            pytest.skip("the accounts or blog schema is not on this database")
    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def folder(tmp_path, monkeypatch):
    d = tmp_path / "blog"
    (d / "img").mkdir(parents=True)
    (d / "2026-10-01-from-a-file.md").write_text("---\ntitle: From a file\nsummary: A file post.\n---\n\nThe file's body.\n")
    monkeypatch.setenv("LEAGUE_LAB_BLOG_DIR", str(d))
    monkeypatch.delenv("LEAGUE_LAB_BLOG_DRAFTS", raising=False)
    blog.reset()
    yield d
    blog.reset()


@pytest.fixture
def api(monkeypatch, schema, folder):
    monkeypatch.delenv("LEAGUE_LAB_APP_PASSWORD", raising=False)
    monkeypatch.delenv("LEAGUE_LAB_RESEND_API_KEY", raising=False)
    monkeypatch.delenv(blog_store.EDITORS_ENV, raising=False)
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "io3-test-secret")
    monkeypatch.setenv(accounts.ENV, "on")
    monkeypatch.setenv("LEAGUE_LAB_PUBLIC_URL", "https://isuckatfantasy.io")
    accounts.reset()
    blog_store.reset()
    with TestClient(app) as c:
        yield c
    accounts.reset()
    blog_store.reset()
    _cleanup()


def sign_in(c: TestClient, name: str) -> str:
    """A fresh browser signed in through the emailed link (the stub mailer); the account's id."""
    c.cookies.clear()
    email = f"{name}@{DOMAIN}"
    assert c.post("/api/account/login", json={"email": email}).status_code == 202
    msg = [m for m in accounts.STUB.sent if m["to"] == email][-1]
    token = re.search(r"#signin=([A-Za-z0-9_-]+)", msg["text"]).group(1)
    assert c.post("/api/account/verify", json={"token": token}).status_code == 200
    me = c.get("/api/account/me").json()
    assert re.fullmatch(r"[0-9a-f-]{36}", me["id"])                     # the Account screen's "Your account id"
    return me["id"]


@pytest.fixture
def editor(api, monkeypatch):
    uid = sign_in(api, "editor")
    monkeypatch.setenv(blog_store.EDITORS_ENV, f" {uid.upper()} , not-an-id,")   # case and spaces do not matter
    return api


def new_post(c: TestClient, **kw) -> dict:
    body = {"title": "A title", "summary": "A summary.", "tags": ["matchups"], "author": "Andrew", "body": "Hello."} | kw
    r = c.post("/api/blog/posts", json=body, headers=SAME)
    assert r.status_code == 201, r.text
    return r.json()


def save(c: TestClient, p: dict, **kw) -> dict:
    body = {k: p[k] for k in ("title", "summary", "tags", "author", "body", "slug")} | {"revision": p["revision"]} | kw
    return c.put(f"/api/blog/posts/{p['id']}", json=body, headers=SAME)


ROUTES = [("GET", "/api/blog/mine"), ("GET", "/api/blog/export"), ("GET", f"/api/blog/posts/{ID}"),
          ("GET", f"/api/blog/posts/{ID}/revisions/1"), ("POST", "/api/blog/posts"), ("PUT", f"/api/blog/posts/{ID}"),
          ("POST", f"/api/blog/posts/{ID}/publish"), ("POST", f"/api/blog/posts/{ID}/unpublish"),
          ("POST", f"/api/blog/posts/{ID}/restore"), ("DELETE", f"/api/blog/posts/{ID}"),
          ("POST", "/api/blog/images"), ("DELETE", f"/api/blog/images/{ID}")]
BODY = {"title": "x", "body": "x", "revision": 1}


def call(c: TestClient, method: str, path: str, headers=SAME):
    return c.request(method, path, json=BODY if method in ("POST", "PUT") else None, headers=headers)


# ====================================================================================== who may write
def test_no_editors_no_editor_every_route_is_404(api, monkeypatch):
    sign_in(api, "someone")
    for value in (None, "", " , "):
        if value is None:
            monkeypatch.delenv(blog_store.EDITORS_ENV, raising=False)
        else:
            monkeypatch.setenv(blog_store.EDITORS_ENV, value)
        for method, path in ROUTES:
            r = call(api, method, path)
            assert r.status_code == 404 and r.json()["code"] == "not_found", (value, method, path, r.text)


def test_signed_out_and_not_an_editor(api, monkeypatch):
    uid = sign_in(api, "other")
    monkeypatch.setenv(blog_store.EDITORS_ENV, "11111111-1111-4111-8111-111111111111")
    for method, path in ROUTES:
        r = call(api, method, path)
        assert r.status_code == 403 and r.json()["code"] == "not_editor", (method, path, r.text)
    api.cookies.clear()
    for method, path in ROUTES:
        r = call(api, method, path)
        assert r.status_code == 401 and r.json()["code"] == "signed_out", (method, path, r.text)
    api.cookies.set(accounts.COOKIE, "forged.0000")                     # a forged cookie reads nothing
    assert call(api, "GET", "/api/blog/mine").status_code == 401
    monkeypatch.setenv(blog_store.EDITORS_ENV, uid)
    monkeypatch.setenv(accounts.ENV, "off")                             # accounts off: no editor at all
    for method, path in ROUTES:
        assert call(api, method, path).status_code == 404, (method, path)


def test_a_cross_site_write_is_refused(editor):
    p = new_post(editor)
    for headers in (EVIL, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
        for method, path in ROUTES:
            if method == "GET":
                continue
            r = editor.request(method, path.replace(ID, p["id"]), json=BODY if method in ("POST", "PUT") else None,
                               headers=headers)
            assert r.status_code == 403 and r.json()["code"] == "cross_site", (headers, method, path, r.text)
    assert editor.get(f"/api/blog/posts/{p['id']}").json()["revision"] == 1   # nothing changed


def test_every_new_route_has_a_bucket():
    assert ratelimit.bucket_for("GET", "/api/blog/mine") == "read"
    assert ratelimit.bucket_for("GET", f"/api/blog/posts/{ID}") == "read"
    assert ratelimit.bucket_for("GET", "/api/blog/export") == "research"
    assert ratelimit.bucket_for("GET", f"/blog/img/db/{ID}") == "read"
    for method, path in ROUTES:
        if method != "GET":
            assert ratelimit.bucket_for(method, path) == "write", (method, path)


# ====================================================================================== the flow
def test_write_conflict_publish_read_unpublish_delete_restore(editor, folder):
    mine = editor.get("/api/blog/mine").json()
    assert mine["posts"] == [] and mine["author"] == "" and mine["limits"]["body_kb"] == 200
    p = new_post(editor, title="Start Washington: a case", body="\n\nFirst words.")
    assert p["status"] == "draft" and p["slug"] == "start-washington-a-case" and p["revision"] == 1
    assert p["body"] == "First words."                                  # leading blank lines dropped (export round trip)
    # two tabs edit revision 1: the first save wins, the second is a 409 carrying the newer body — never an overwrite
    a = save(editor, p, body="Tab A's words.")
    assert a.status_code == 200 and a.json()["revision"] == 2
    b = save(editor, p, body="Tab B's words.")
    assert b.status_code == 409 and b.json()["code"] == "conflict" and b.json()["post"]["body"] == "Tab A's words."
    assert b.json()["post"]["revision"] == 2
    p = a.json()
    assert editor.get("/api/blog").json()["posts"] == [blog.meta(x) for x in blog.index()]   # a draft is not public
    assert editor.get(f"/api/blog/{p['slug']}").status_code == 404
    pub = editor.post(f"/api/blog/posts/{p['id']}/publish", json={"revision": p["revision"]}, headers=SAME)
    assert pub.status_code == 200 and pub.json()["status"] == "published" and pub.json()["published_at"]
    r = editor.get("/api/blog")
    assert r.headers["cache-control"] == "public, max-age=0, must-revalidate"   # a post published now shows on the next load
    listed = r.json()["posts"]
    assert [x["slug"] for x in listed][:2] == ["start-washington-a-case", "from-a-file"]       # newest first, one list
    one = editor.get(f"/api/blog/{p['slug']}").json()
    assert one["markdown"] == "Tab A's words." and one["author"] == "Andrew" and one["tags"] == ["matchups"]
    assert "start-washington-a-case" in editor.get("/blog/rss.xml").text
    assert "https://isuckatfantasy.io/blog/start-washington-a-case" in editor.get("/sitemap.xml").text
    assert editor.get("/api/blog/mine").json()["author"] == "Andrew"    # the author line defaults to the last one used
    # a published post keeps its address
    r = save(editor, p | {"revision": pub.json()["revision"]}, slug="another-address")
    assert r.status_code == 200 and r.json()["slug"] == p["slug"] and r.json()["slug_problem"] == "published"
    p = r.json()
    assert editor.post(f"/api/blog/posts/{p['id']}/unpublish", headers=SAME).json()["status"] == "draft"
    assert editor.get(f"/api/blog/{p['slug']}").status_code == 404 and p["slug"] not in editor.get("/sitemap.xml").text
    gone = editor.delete(f"/api/blog/posts/{p['id']}", headers=SAME).json()
    assert gone["status"] == "deleted" and gone["deleted_at"]
    assert save(editor, p | {"revision": gone["revision"]}).status_code == 409           # restore before editing
    back = editor.post(f"/api/blog/posts/{p['id']}/restore", headers=SAME).json()
    assert back["status"] == "draft" and back["deleted_at"] is None
    # revisions: every explicit save kept (autosaves within two minutes fold into one), the newest 20 at most
    full = editor.get(f"/api/blog/posts/{p['id']}").json()
    assert [r["revision"] for r in full["revisions"]][:2] == [3, 2]
    old = editor.get(f"/api/blog/posts/{p['id']}/revisions/{full['revisions'][-1]['id']}").json()
    assert old["body"] == "First words."
    cur = full
    for i in range(25):
        r = save(editor, cur, body=f"Autosave {i}", autosave=True)
        cur = r.json()
    full = editor.get(f"/api/blog/posts/{p['id']}").json()
    assert len(full["revisions"]) == 4 and full["revisions"][0]["revision"] == cur["revision"]
    for i in range(22):
        cur = save(editor, cur, body=f"Explicit {i}").json()
    assert len(editor.get(f"/api/blog/posts/{p['id']}").json()["revisions"]) == 20


def test_another_editors_posts_are_not_mine(editor, monkeypatch):
    p = new_post(editor)
    uid2 = sign_in(editor, "editor2")
    monkeypatch.setenv(blog_store.EDITORS_ENV, ",".join([uid2, *blog_store.editors()]))
    assert editor.get("/api/blog/mine").json()["posts"] == []
    assert editor.get(f"/api/blog/posts/{p['id']}").status_code == 404
    assert save(editor, p).status_code == 404
    assert editor.post(f"/api/blog/posts/{p['id']}/publish", headers=SAME).status_code == 404


# ====================================================================================== addresses
def test_slug_rules_and_the_file_collision(editor, folder):
    p = new_post(editor, title="From a file")                          # the file holds from-a-file: the draft does not
    assert p["slug"] == "from-a-file-2"
    for slug, problem in (("from-a-file", "taken_by_file"), ("new", "reserved"), ("edit", "reserved"),
                          ("mine", "reserved"), ("export", "reserved"), ("Bad Slug", "shape"), ("a--b", "shape"),
                          ("x" * 81, "shape"), ("o\nk", "shape"), ("../etc", "shape")):
        r = save(editor, p, slug=slug)
        assert r.status_code == 200 and r.json()["slug"] == p["slug"] and r.json()["slug_problem"] == problem, slug
        p = r.json()
    other = new_post(editor, title="Other")
    r = save(editor, other, slug=p["slug"])
    assert r.json()["slug_problem"] == "taken" and r.json()["slug"] == "other"
    r = save(editor, p, slug="my-own-address")
    assert r.json()["slug"] == "my-own-address" and "slug_problem" not in r.json()
    p = r.json()
    # a file pushed later with the same slug: publishing refuses; a published one meeting a newer file is left out
    (folder / "2026-10-05-my-own-address.md").write_text("---\ntitle: The file wins\n---\n\nFile.\n")
    blog.reset()
    r = editor.post(f"/api/blog/posts/{p['id']}/publish", headers=SAME)
    assert r.status_code == 409 and r.json()["code"] == "slug_taken"
    q2 = new_post(editor, title="Twin", slug="twin")
    editor.post(f"/api/blog/posts/{q2['id']}/publish", headers=SAME)
    (folder / "2026-10-02-twin.md").write_text("---\ntitle: The twin file\n---\n\nFile twin.\n")
    blog.reset()
    blog_store.reset()
    assert editor.get("/api/blog/twin").json()["markdown"] == "File twin.\n"
    assert [x["slug"] for x in editor.get("/api/blog").json()["posts"]].count("twin") == 1


def test_untitled_posts_and_ids(editor):
    p = new_post(editor, title="", body="")
    assert p["slug"] == "draft" and p["title"] == ""
    r = editor.post(f"/api/blog/posts/{p['id']}/publish", headers=SAME)
    assert r.status_code == 400 and r.json()["code"] == "no_title"
    for bad in ("not-an-id", "../../etc", ID.upper(), ID + "0"):
        assert editor.get(f"/api/blog/posts/{bad}").status_code in (404, 405), bad
    assert editor.get(f"/api/blog/posts/{ID}").status_code == 404


# ====================================================================================== hostile text
XSS_TITLE = '"><script>alert(1)</script><img src=x onerror=alert(2)>'
XSS_SUMMARY = "</description><script>alert(3)</script>&lt;b&gt; ]]> <![CDATA[x]]>"
XSS_AUTHOR = '<img src=x onerror="alert(4)">'
XSS_BODY = "\n".join([
    "<script>alert(5)</script>",
    '[click](javascript:alert(6)) [data](data:text/html,<script>alert(7)</script>) [evil](https://evil.example/x)',
    '[quote](/player/00-0036963" onmouseover="alert(8)) [proto](//evil.example) [back](/\\evil.example)',
    '![pic](https://evil.example/x.png) ![pic2](/blog/img/x.png" onerror="alert(9)) ![svg](/blog/img/x.svg)',
    "| a | b |", "|---|---|", "| <td onclick=alert(10)> | `</code><script>` |",
    "```", "</pre><script>alert(11)</script>", "```",
    "&lt;script&gt; &#60;script&#62;  0  1",
    "**[bold link](javascript:alert(12))** *<i>*",
])


def test_hostile_fields_are_stored_as_text_and_served_escaped(editor, folder):
    p = new_post(editor, title=XSS_TITLE, summary=XSS_SUMMARY, author=XSS_AUTHOR, body=XSS_BODY, slug="hostile")
    assert p["title"] == XSS_TITLE and p["body"] == XSS_BODY             # stored as typed: rendering escapes
    assert editor.post(f"/api/blog/posts/{p['id']}/publish", headers=SAME).status_code == 200
    one = editor.get("/api/blog/hostile")
    assert one.headers["content-type"].startswith("application/json") and one.json()["markdown"] == XSS_BODY
    # RSS: parses, every text escaped, no element but the feed's own
    rss = editor.get("/blog/rss.xml")
    root = ET.fromstring(rss.content)
    item = next(i for i in root.iter("item") if i.findtext("title") == XSS_TITLE)
    assert item.findtext("description") == XSS_SUMMARY
    assert {e.tag for e in root.iter()} <= {"rss", "channel", "title", "link", "description", "language", "item", "guid",
                                            "pubDate", "category"}
    assert "<script" not in rss.text and "<img" not in rss.text
    # the sitemap: the slug only
    assert "<script" not in editor.get("/sitemap.xml").text
    # the page shell's meta tags (the link preview)
    d = folder.parent / "dist"
    d.mkdir()
    (d / "index.html").write_text((ROOT / "web" / "index.html").read_text())
    import os
    os.environ["LEAGUE_LAB_WEB_DIST"] = str(d)
    try:
        page = editor.get("/blog/hostile")
    finally:
        del os.environ["LEAGUE_LAB_WEB_DIST"]
    assert page.status_code == 200
    head = page.text.split("</head>")[0]
    assert "<script>alert" not in head and "onerror=" not in head.replace("onerror=alert(2)&gt;", "")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in head and "&lt;/description&gt;" in head
    assert head.count("<title>") == 1 and head.count('property="og:title"') == 1
    os.environ["LEAGUE_LAB_WEB_DIST"] = str(d)
    try:                                                                # the editor's addresses are the app's (200)
        assert editor.get("/blog/new").status_code == 200
        assert editor.get(f"/blog/edit/{p['id']}").status_code == 200
    finally:
        del os.environ["LEAGUE_LAB_WEB_DIST"]


def test_bad_fields_are_refused(editor):
    for kw, code, status in ((dict(title="x" * 141), "bad_title", 400), (dict(summary="x" * 401), "bad_summary", 400),
                             (dict(author="x" * 61), "bad_author", 400), (dict(tags=["a"] * 2 + ["b", "c", "d", "e", "f", "g", "h", "i"]), "bad_tags", 400),
                             (dict(tags=["<b>"]), "bad_tags", 400), (dict(tags=["x" * 33]), "bad_tags", 400),
                             (dict(title="a\x00b"), "bad_title", 400), (dict(body="a\x00b"), "bad_body", 400),
                             (dict(body="a\x1bb"), "bad_body", 400), (dict(body="é" * (100 * 1024 + 1)), "too_big", 413)):
        r = editor.post("/api/blog/posts", json={"title": "t", "body": "b"} | kw, headers=SAME)
        assert r.status_code == status and r.json()["code"] == code, (kw.keys(), r.text[:200])
    r = editor.post("/api/blog/posts", json={"title": "t", "body": "x" * (200 * 1024 + 2)}, headers=SAME)
    assert r.status_code in (413, 422)                                  # over the model's bound: refused before anything
    r = editor.post("/api/blog/posts", json={"title": "t", "body": "x" * (300 * 1024)}, headers=SAME)
    assert r.status_code == 413                                         # over the Guard's 256 KB: refused at the door
    ok = new_post(editor, title="Line\nbreaks\tgo\u2028too", summary="two\nlines", body="x" * (200 * 1024))
    assert ok["title"] == "Line breaks go too" and ok["summary"] == "two lines" and ok["bytes"] == 200 * 1024
    pasted = new_post(editor, body="a\r\nb\rc\u2028d\u2029e\x0cf\tg")             # a paste from a word processor
    assert pasted["body"] == "a\nb\nc\nd\ne\nf\tg"
    assert all(new_post(editor, tags=["Matchups", "matchups", " Week 5 "])["tags"] == ["matchups", "week 5"] for _ in [0])


def test_the_limits_on_posts_and_storage(editor, monkeypatch):
    monkeypatch.setattr(blog_store, "MAX_POSTS", 2)
    new_post(editor)
    new_post(editor)
    r = editor.post("/api/blog/posts", json={"title": "third"}, headers=SAME)
    assert r.status_code == 409 and r.json()["code"] == "too_many"
    monkeypatch.setattr(blog_store, "MAX_POSTS", 500)
    monkeypatch.setattr(blog_store, "MAX_TOTAL_BYTES", 10_000)
    r = editor.post("/api/blog/posts", json={"title": "big", "body": "x" * 6000}, headers=SAME)
    assert r.status_code == 413 and r.json()["code"] == "blog_full"


# ====================================================================================== the export
def test_export_round_trip(editor):
    a = new_post(editor, title='He said "start him": a case', summary="Colons: fine; quotes \"too\".", tags=["dfs", "week 5"],
                 author="Andrew M.", body="Body with\n---\nrules and  two spaces  \n\n```players\n00-0036963\n```\n\nEnd")
    editor.post(f"/api/blog/posts/{a['id']}/publish", headers=SAME)
    b = new_post(editor, title="A draft", summary="", tags=[], author="", body="Just a draft.")
    c = new_post(editor, title="Deleted")
    editor.delete(f"/api/blog/posts/{c['id']}", headers=SAME)
    r = editor.get("/api/blog/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert re.fullmatch(r'attachment; filename="isuckatfantasy-blog-\d{4}-\d{2}-\d{2}\.zip"', r.headers["content-disposition"])
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = sorted(z.namelist())
    assert len(names) == 2 and all(n.startswith("blog/") for n in names)
    back = {}
    for n in names:
        parsed = blog.parse_post(Path(n).name, z.read(n).decode())
        assert parsed is not None, n
        back[parsed["slug"]] = parsed
    for orig, draft in ((editor.get(f"/api/blog/posts/{a['id']}").json(), False), (b, True)):
        got = back[orig["slug"]]
        assert got["title"] == orig["title"] and got["summary"] == orig["summary"] and got["tags"] == orig["tags"]
        assert got["author"] == (orig["author"] or blog.SITE_AUTHOR) and got["markdown"] == orig["body"]
        assert got["draft"] is draft
    # the files read back by the blog's own folder reader are the same posts
    assert {p["slug"] for p in blog.load(_unzip(z), drafts=True)} == set(back)


def _unzip(z: zipfile.ZipFile) -> Path:
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="io3-export-"))
    for n in z.namelist():
        (d / Path(n).name).write_bytes(z.read(n))
    return d


# ====================================================================================== without the tables (rule 10)
def test_without_the_tables_the_blog_is_the_files_and_the_editor_is_gone(api, folder, monkeypatch):
    uid = sign_in(api, "notables")
    monkeypatch.setenv(blog_store.EDITORS_ENV, uid)
    monkeypatch.setattr(blog_store, "TABLES", ("blog.absent_io3", "blog.absent_io3_revisions", "blog.absent_io3_images"))
    blog_store.reset()
    for method, path in ROUTES:
        r = call(api, method, path)
        assert r.status_code == 404 and r.json()["code"] == "not_found", (method, path)
    assert blog_store.published_meta() == []
    files = [blog.meta(p) for p in blog.index()]
    r = api.get("/api/blog")
    assert r.json() == {"posts": files} and r.headers["cache-control"] == "public, max-age=300"   # today's answer
    assert api.get("/api/blog/from-a-file").json()["markdown"].startswith("The file's body.")
    assert api.get("/api/blog/no-such").status_code == 404
    assert api.get("/blog/rss.xml").status_code == 200 and api.get("/sitemap.xml").status_code == 200


def test_the_database_down_leaves_the_files(api, folder, monkeypatch):
    class Down:
        def connection(self, timeout=None):
            raise psycopg.OperationalError("down")
    monkeypatch.setattr(blog_store.db, "pool", lambda: Down())
    blog_store.reset()
    assert [p["slug"] for p in api.get("/api/blog").json()["posts"]] == ["from-a-file"]
    assert blog_store.published_body("anything") is None


def test_the_script_is_idempotent_and_grants_only_its_tables():
    sql = SQL_FILE.read_text().lower()
    code = "\n".join(line.split("--")[0] for line in sql.splitlines())
    assert not re.search(r"\b(drop|alter)\b", code) and not re.search(r"^\s*truncate", code, re.M)
    assert "create schema if not exists blog" in code and code.count("create table if not exists blog.") == 3
    grants = re.findall(r"grant [^;]+;", code)
    assert all(" on blog." in g or " on schema blog " in g or " on sequence blog." in g for g in grants), grants
    assert "create role" not in code and "accounts." not in code and "analytics" not in code


# ====================================================================================== pictures
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 200


def upload(c: TestClient, data: bytes, ctype: str = "image/png", headers=SAME):
    return c.post("/api/blog/images", content=data, headers={**headers, "Content-Type": ctype})


def test_pictures_by_first_bytes_served_with_their_type(editor):
    got = {}
    for data, kind, mime in ((PNG, "png", "image/png"), (JPG, "jpg", "image/jpeg"), (WEBP, "webp", "image/webp")):
        r = upload(editor, data, "application/octet-stream")              # the declared type is never trusted
        assert r.status_code == 201 and r.json()["kind"] == kind, r.text
        got[kind] = r.json()
        img = editor.get(r.json()["url"])
        assert img.status_code == 200 and img.headers["content-type"] == mime and img.content == data
        assert img.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert img.headers["x-content-type-options"] == "nosniff"
    assert {i["id"] for i in editor.get("/api/blog/mine").json()["images"]} == {g["id"] for g in got.values()}
    for bad in (b"<svg onload=alert(1)>" + b" " * 64, b"<html><script>alert(1)</script>" + b" " * 64, b"GIF89a" + b"\x00" * 64,
                b"\x89PNG", b""):
        r = upload(editor, bad, "image/png")
        assert r.status_code == 400 and r.json()["code"] == "bad_image", bad[:10]
    r = upload(editor, b"\x89PNG\r\n\x1a\n" + b"\x00" * (300 * 1024))
    assert r.status_code == 413 and r.json()["code"] == "too_big"
    r = upload(editor, b"\x89PNG\r\n\x1a\n" + b"\x00" * (330 * 1024))
    assert r.status_code == 413                                          # the Guard's 320 KB for this route
    assert upload(editor, PNG, headers=EVIL).status_code == 403
    # the address: a lower-case uuid only, nothing from it reaches the filesystem
    for path in (f"/blog/img/db/{ID}", "/blog/img/db/..%2F..%2Fsettings", f"/blog/img/db/{got['png']['id'].upper()}",
                 "/blog/img/db/x.png", f"/blog/img/db/{got['png']['id']}%0a"):
        assert editor.get(path).status_code == 404, path
    assert editor.delete(f"/api/blog/images/{got['png']['id']}", headers=SAME).json() == {"ok": True}
    assert editor.get(got["png"]["url"]).status_code == 404
    assert editor.delete(f"/api/blog/images/{got['png']['id']}", headers=SAME).status_code == 404


def test_pictures_have_a_count(editor, monkeypatch):
    there = q("select count(*) from blog.images")[0][0]                # the count is the blog's, all editors'
    monkeypatch.setattr(blog_store, "MAX_IMAGES", there + 1)
    assert upload(editor, PNG).status_code == 201
    r = upload(editor, JPG)
    assert r.status_code == 409 and r.json()["code"] == "too_many_images"


def test_without_the_tables_a_picture_is_404(api, monkeypatch):
    monkeypatch.setattr(blog_store, "TABLES", ("blog.absent_io3", "blog.absent_io3_revisions", "blog.absent_io3_images"))
    blog_store.reset()
    assert api.get(f"/blog/img/db/{ID}").status_code == 404
