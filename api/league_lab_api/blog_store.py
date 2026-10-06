"""The blog's editor (Wave I-O, IO-3; docs/BLOG.md § "The editor"): posts written on the site, kept in the hosted
database (schema `blog`: scripts/hosted_blog.sql), served beside the markdown files in blog/ by blog.py.

Who may write: a signed-in account (accounts.py: passkeys or the emailed link) whose id is listed in
``LEAGUE_LAB_EDITORS`` (comma-separated account ids). Unset or empty, accounts off, or the tables missing: the editor does
not exist — every route here answers 404, the public blog is exactly the files'. No password, no token, no username.

Routes (behind the beta gate like every /api/ route; JSON; ``no-store``; errors ``{error, detail, code}``):
    GET    /api/blog/mine                     the editor's posts (no bodies), the last author line, the limits
    GET    /api/blog/posts/{id}               one post with its body and revision, its saved revisions (dates, sizes)
    GET    /api/blog/posts/{id}/revisions/{n} one saved revision's title and body
    POST   /api/blog/posts                    a new draft → 201
    PUT    /api/blog/posts/{id}               save; carries the revision it edited — a stale one is 409 with the newer post
    POST   /api/blog/posts/{id}/publish       draft → published (the first publish sets the date; a file's slug refuses)
    POST   /api/blog/posts/{id}/unpublish     published → draft
    DELETE /api/blog/posts/{id}               → deleted (restorable for 30 days, then gone with its revisions)
    POST   /api/blog/posts/{id}/restore       deleted → draft
    GET    /api/blog/export                   every post of the editor as blog/*.md files (the same front matter), one zip

Every write: signed in, an editor, the same-site rule (accounts.same_site; IM-3's Guard runs first), the limiter's
`write` bucket plus 60 a minute per session, validated (below). The GET routes `mine` and `export` are declared in
blog.py ahead of ``/api/blog/{slug}`` (they are one path segment); the rest live on this module's router, which
blog.py includes into its own.

Limits: a body ≤ 200 KB (UTF-8), a title ≤ 140 characters, a summary ≤ 400, 8 tags of 32, an author ≤ 60, a slug ≤ 80
(the files' pattern, not a reserved word, not a file's); ≤ 500 posts; ≤ 30 MB of bodies in all (posts + revisions);
the last 20 revisions of a post, at most one every two minutes while autosaving.

The public reads (blog.py: the list, a post, RSS, the sitemap, the shell's meta tags) take the published rows from
``published_meta()`` (no bodies; one query a minute, cleared by this process's writes) and a post's body from
``published_body(slug)`` — only for a slug found in that list (a closed set). Both never raise: no schema, no right to
read it, the database down → no database posts.
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
import unicodedata
import uuid
import zipfile
from datetime import datetime
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from league_lab import memo
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import accounts, blog, db

log = logging.getLogger("league_lab_api.blog_store")

EDITORS_ENV = "LEAGUE_LAB_EDITORS"
PURPOSE = "blog"                       # db.run_rw's connection for these writes (accounts keeps its own)
MAX_BODY_BYTES = 200 * 1024
MAX_POSTS = 500
MAX_TOTAL_BYTES = 30 * 1024 * 1024
MAX_IMAGE_BYTES = 300 * 1024
MAX_IMAGES = 50
IMAGE_CACHE = "public, max-age=31536000, immutable"   # an id is never reused: a new picture is a new address
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
KEEP_REVISIONS = 20
REVISION_GAP_S = 120
RESTORE_DAYS = 30
WRITES_PER_MIN = 60
PUBLIC_TTL_S = 60.0
BODY_ENTRIES = 40                      # bodies kept for the public route: 40 × ≤ 200 KB ≈ 8 MB at the very worst
# words a slug may not be: the web's own paths under /blog (/blog/new, /blog/edit/<id>) and the API's under /api/blog
RESERVED = frozenset({"new", "edit", "mine", "export", "posts", "rss", "img", "editor", "drafts", "db", "feed", "write"})
_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_TAG = re.compile(r"^[a-z0-9][a-z0-9 -]*$")
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")                 # no control characters (a body keeps \t and \n)
_LINE_CONTROL = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]")          # a one-line field: no newline, no tab either
NO_STORE = {"Cache-Control": "no-store"}

_pub = memo.region("blog_db", ttl=PUBLIC_TTL_S, max_entries=BODY_ENTRIES + 21)   # bodies, the list, 20 pictures


# ---------------------------------------------------------------- who may write
_warned: set[str] = set()


def editors() -> frozenset[str]:
    """The account ids in LEAGUE_LAB_EDITORS (canonical uuids); anything else in the list is ignored and logged once."""
    out: set[str] = set()
    for part in os.environ.get(EDITORS_ENV, "").split(","):
        p = part.strip()
        if not p:
            continue
        if _ID.fullmatch(p.lower()):
            out.add(p.lower())
        elif p not in _warned and len(_warned) < 20:
            _warned.add(p)
            log.warning("blog: an entry of %s is not an account id; ignored", EDITORS_ENV)
    return frozenset(out)


TABLES = ("blog.posts", "blog.revisions", "blog.images")   # the existence checks' names (a test points them elsewhere)
READY_SQL = ("select coalesce(has_table_privilege(to_regclass(%s), 'insert'), false) "
             "and coalesce(has_table_privilege(to_regclass(%s), 'insert'), false) "
             "and coalesce(has_table_privilege(to_regclass(%s), 'insert'), false)")
_ready = {"ok": False, "next": 0.0}


def ready() -> bool:
    """The tables exist and the app role may write them — asked at most once a minute (every ten once they are)."""
    now = time.monotonic()
    if now >= _ready["next"]:
        try:
            ok = bool(db.run_rw(lambda c: c.execute(READY_SQL, TABLES).fetchone()[0], purpose=PURPOSE))
        except Exception as exc:                                     # noqa: BLE001 - never a 500 for a missing schema
            log.info("blog: the editor's tables are not usable (%s)", exc.__class__.__name__)
            ok = False
        _ready.update(ok=ok, next=now + (600.0 if ok else 60.0))
    return bool(_ready["ok"])


def reset() -> None:
    _ready.update(ok=False, next=0.0)
    _pub.clear()


def _err(status: int, code: str, words: str) -> accounts.AccountError:
    return accounts.AccountError(status, code, words)


NOT_HERE = "No page at that address."


def on() -> bool:
    """The editor exists on this server: editors listed, accounts on, the tables there."""
    return bool(editors()) and accounts.state()[0] and ready()


def editor(request: Request, *, write: bool = False) -> tuple[str, str]:
    """(account id, session id) of the signed-in editor, else the refusal: 404 (no editor on this server), 401 (signed
    out), 403 (signed in, not an editor), 429 (too many changes)."""
    if not editors() or not accounts.state()[0] or not ready():
        raise _err(404, "not_found", NOT_HERE)
    try:
        who = accounts.current_user(request)
    except psycopg.Error:
        who = None
    if who is None:
        raise _err(401, "signed_out", "Sign in to write.")
    if who[0].lower() not in editors():
        raise _err(403, "not_editor", "This account cannot write on the blog.")
    if write and not accounts.allow(f"blog:{who[2]}", WRITES_PER_MIN):
        raise _err(429, "rate_limited", "Too many changes at once. Wait a minute.")
    return who[0].lower(), who[2]


# ---------------------------------------------------------------- validation
class PostIn(BaseModel):
    title: str = Field(default="", max_length=400)
    summary: str = Field(default="", max_length=1200)
    tags: list[str] = Field(default_factory=list, max_length=20)
    author: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=256 * 1024)       # the Guard's bound: over 200 KB is clean()'s 413 in words
    slug: str | None = Field(default=None, max_length=200)


class SaveIn(PostIn):
    revision: int = Field(ge=1, le=10_000_000)
    autosave: bool = False


class PublishIn(BaseModel):
    revision: int | None = Field(default=None, ge=1, le=10_000_000)


def _line(v: str, n: int, code: str, what: str) -> str:
    v = re.sub(r"[\r\n\t\u2028\u2029\x0b\x0c]+", " ", v or "").strip()     # pasted line breaks become spaces
    v = re.sub(r" {2,}", " ", v)
    if _LINE_CONTROL.search(v):
        raise _err(400, code, f"The {what} has a character it cannot hold.")
    if len(v) > n:
        raise _err(400, code, f"The {what} is longer than {n} characters.")
    return v


def clean(p: PostIn) -> dict[str, Any]:
    """The fields as they are stored: one-line title / summary / author, tags as the files' rule, the body's line ends
    made \\n and its leading blank lines dropped (so an export reads back the same), the sizes checked."""
    title = _line(p.title, blog.MAX_TITLE, "bad_title", "title")
    summary = _line(p.summary, blog.MAX_SUMMARY, "bad_summary", "summary")
    author = _line(p.author, 60, "bad_author", "author line")
    if len(p.tags) > blog.MAX_TAGS:
        raise _err(400, "bad_tags", f"At most {blog.MAX_TAGS} tags.")
    tags: list[str] = []
    for t in p.tags:
        t = re.sub(r"\s+", " ", str(t).strip().lower())
        if not t:
            continue
        if len(t) > blog.MAX_TAG or not _TAG.fullmatch(t):
            raise _err(400, "bad_tags", f"A tag is letters, numbers, spaces and dashes, at most {blog.MAX_TAG} characters.")
        if t not in tags:
            tags.append(t)
    body = re.sub(r"\r\n?|[\u2028\u2029\x0b\x0c]", "\n", p.body).lstrip("\n")   # every line end a \n (pastes too)
    if _CONTROL.search(body):
        raise _err(400, "bad_body", "The post has a character it cannot hold (a control character).")
    size = len(body.encode("utf-8"))
    if size > MAX_BODY_BYTES:
        raise _err(413, "too_big", f"The post is over {MAX_BODY_BYTES // 1024} KB. Split it in two.")
    return {"title": title, "summary": summary, "author": author, "tags": tags, "body": body, "body_bytes": size,
            "minutes": min(10000, blog.minutes(body))}


def slug_problem(slug: str) -> str | None:
    """Why this slug cannot be a database post's: shape, reserved, or a file's (taken_by_file); None = it can."""
    if not isinstance(slug, str) or len(slug) > blog.MAX_SLUG or not blog.SLUG.fullmatch(slug):
        return "shape"
    if slug in RESERVED:
        return "reserved"
    if slug in file_slugs():
        return "taken_by_file"
    return None


def file_slugs() -> set[str]:
    """The slugs the files in blog/ hold (drafts too), from the file names alone — nothing is opened."""
    try:
        names = [p.name for p in blog.folder().iterdir()]
    except OSError:
        return set()
    out = set()
    for n in names:
        m = blog.FILE_NAME.fullmatch(n)
        if m:
            out.add(m.group(2))
    return out


def slug_from(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60].strip("-")
    return s or "post"


SLUG_WORDS = {
    "shape": "An address is lower-case letters and numbers joined by single dashes, at most 80 characters.",
    "reserved": "That address is one the site uses. Pick another.",
    "taken_by_file": "A post in the repository already has that address. Pick another.",
    "taken": "Another post already has that address. Pick another.",
    "published": "A published post keeps its address. Unpublish it to change the address.",
}


# ---------------------------------------------------------------- rows
COLS = ("id, slug, title, summary, tags, author, status, revision, created_at, updated_at, published_at, deleted_at, "
        "minutes, body_bytes, account_id")


def _iso(t: datetime | None) -> str | None:
    return t.isoformat() if t is not None else None


def _row(r: tuple, body: str | None = None) -> dict[str, Any]:
    (pid, slug, title, summary, tags, author, status, revision, created, updated, published, deleted, minutes, nbytes,
     _acct) = r[:15]
    out = {"id": str(pid), "slug": slug, "title": title, "summary": summary, "tags": list(tags or []), "author": author,
           "status": status, "revision": revision, "created_at": _iso(created), "updated_at": _iso(updated),
           "published_at": _iso(published), "deleted_at": _iso(deleted), "minutes": minutes, "bytes": nbytes,
           "date": _date(published or updated)}
    if body is not None:
        out["body"] = body
    return out


def _date(t: datetime | None) -> str | None:
    return t.astimezone(blog.ET).date().isoformat() if t is not None else None


def _check_id(post_id: str) -> str:
    if not isinstance(post_id, str) or not _ID.fullmatch(post_id):
        raise _err(404, "no_post", blog.NOT_FOUND)
    return post_id


def _get(c: psycopg.Connection, post_id: str, uid: str, *, body: bool = True, lock: bool = False) -> dict | None:
    r = c.execute(f"select {COLS}, body from blog.posts where id = %s and account_id = %s" + (" for update" if lock else ""),
                  (post_id, uid)).fetchone()
    return None if r is None else _row(r, r[15] if body else None)


def _prune(c: psycopg.Connection) -> None:
    c.execute(f"delete from blog.posts where status = 'deleted' and deleted_at < now() - interval '{RESTORE_DAYS} days'")


def _room(c: psycopg.Connection, adding: int) -> None:
    total = c.execute("select (select coalesce(sum(body_bytes), 0) from blog.posts) + "
                      "(select coalesce(sum(body_bytes), 0) from blog.revisions) + "
                      "(select coalesce(sum(size), 0) from blog.images)").fetchone()[0]
    if int(total) + adding > MAX_TOTAL_BYTES:
        raise _err(413, "blog_full", "The blog's storage is full. Delete old drafts, or export and tidy up.")


def _revision(c: psycopg.Connection, post_id: str, rev: int, title: str, body: str, nbytes: int, autosave: bool) -> None:
    """Keep this body as a revision: an autosave within two minutes of the last kept autosave replaces it (20
    revisions then reach back at least 40 minutes of typing; an explicit save is never replaced); the newest 20 stay."""
    last = c.execute(f"select id, autosave and saved_at > now() - interval '{REVISION_GAP_S} seconds' from blog.revisions "
                     "where post_id = %s order by saved_at desc, id desc limit 1", (post_id,)).fetchone()
    if autosave and last is not None and last[1]:
        c.execute("update blog.revisions set revision = %s, title = %s, body = %s, body_bytes = %s where id = %s",
                  (rev, title, body, nbytes, last[0]))
    else:
        c.execute("insert into blog.revisions (post_id, revision, title, body, body_bytes, autosave) "
                  "values (%s, %s, %s, %s, %s, %s)", (post_id, rev, title, body, nbytes, autosave))
    c.execute("delete from blog.revisions where id in (select id from blog.revisions where post_id = %s "
              "order by saved_at desc, id desc offset %s)", (post_id, KEEP_REVISIONS))


def _published_changed() -> None:
    _pub.clear()


# ---------------------------------------------------------------- the flows
def mine(uid: str) -> dict[str, Any]:
    def tx(c: psycopg.Connection) -> dict:
        _prune(c)
        rows = c.execute(f"select {COLS} from blog.posts where account_id = %s order by "
                         "(status = 'deleted'), updated_at desc limit %s", (uid, MAX_POSTS)).fetchall()
        return {"rows": rows}
    got = db.run_rw(tx, purpose=PURPOSE)
    images = db.run_rw(lambda c: c.execute("select id, kind, size, created_at from blog.images where account_id = %s "
                                           "order by created_at desc limit %s", (uid, MAX_IMAGES)).fetchall(),
                       purpose=PURPOSE)
    posts = [_row(r) for r in got["rows"]]
    last_author = next((p["author"] for p in sorted(posts, key=lambda p: p["updated_at"] or "", reverse=True)
                        if p["author"] and p["status"] != "deleted"), "")
    return {"account_id": uid, "author": last_author, "posts": posts,
            "images": [{"id": str(i), "url": f"/blog/img/db/{i}", "kind": k, "size": n, "created_at": _iso(t)}
                       for i, k, n, t in images],
            "limits": {"body_kb": MAX_BODY_BYTES // 1024, "posts": MAX_POSTS, "title": blog.MAX_TITLE,
                       "summary": blog.MAX_SUMMARY, "tags": blog.MAX_TAGS, "tag": blog.MAX_TAG, "slug": blog.MAX_SLUG,
                       "restore_days": RESTORE_DAYS, "revisions": KEEP_REVISIONS, "image_kb": MAX_IMAGE_BYTES // 1024,
                       "images": MAX_IMAGES}}


def get_post(uid: str, post_id: str) -> dict[str, Any]:
    post_id = _check_id(post_id)

    def tx(c: psycopg.Connection) -> dict | None:
        p = _get(c, post_id, uid)
        if p is None:
            return None
        p["revisions"] = [{"id": rid, "revision": rev, "saved_at": _iso(t), "bytes": n} for rid, rev, t, n in c.execute(
            "select id, revision, saved_at, body_bytes from blog.revisions where post_id = %s order by saved_at desc, "
            "id desc", (post_id,)).fetchall()]
        return p
    p = db.run_rw(tx, purpose=PURPOSE)
    if p is None:
        raise _err(404, "no_post", blog.NOT_FOUND)
    return p


def get_revision(uid: str, post_id: str, rid: int) -> dict[str, Any]:
    post_id = _check_id(post_id)
    r = db.run_rw(lambda c: c.execute(
        "select r.revision, r.title, r.body, r.saved_at from blog.revisions r join blog.posts p on p.id = r.post_id "
        "where r.id = %s and r.post_id = %s and p.account_id = %s", (rid, post_id, uid)).fetchone(), purpose=PURPOSE)
    if r is None:
        raise _err(404, "no_revision", "No saved version at that address.")
    return {"revision": r[0], "title": r[1], "body": r[2], "saved_at": _iso(r[3])}


def create(uid: str, p: PostIn) -> dict[str, Any]:
    f = clean(p)
    wanted = (p.slug or "").strip() or slug_from(f["title"] or "draft")
    files = file_slugs()

    def tx(c: psycopg.Connection) -> dict:
        _prune(c)
        if c.execute("select count(*) from blog.posts").fetchone()[0] >= MAX_POSTS:
            raise _err(409, "too_many", f"The blog holds {MAX_POSTS} posts at most. Delete one first.")
        _room(c, f["body_bytes"] * 2)
        base = wanted if slug_problem(wanted) in (None, "taken_by_file") else slug_from(f["title"] or "draft")
        slug, n = base, 1
        while slug in RESERVED or slug in files or c.execute("select 1 from blog.posts where slug = %s", (slug,)).fetchone():
            n += 1
            slug = f"{base[:74]}-{n}"
            if n > 50:
                slug = f"draft-{uuid.uuid4().hex[:12]}"
                break
        r = c.execute(f"insert into blog.posts (slug, title, summary, body, body_bytes, minutes, tags, author, status, "
                      f"account_id) values (%s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s) returning {COLS}, body",
                      (slug, f["title"], f["summary"], f["body"], f["body_bytes"], f["minutes"], f["tags"], f["author"],
                       uid)).fetchone()
        _revision(c, str(r[0]), 1, f["title"], f["body"], f["body_bytes"], autosave=False)
        return _row(r, r[15])
    return db.run_rw(tx, purpose=PURPOSE)


class Conflict(Exception):
    def __init__(self, post: dict):
        super().__init__("conflict")
        self.post = post


def save(uid: str, post_id: str, s: SaveIn) -> dict[str, Any]:
    """Save over revision ``s.revision``: a stale revision raises Conflict with the newer post (body included), never a
    silent overwrite. A slug that cannot be taken leaves the old one and says why (``slug_problem``): the words and the
    body are saved all the same (an autosave never loses text over an address)."""
    post_id = _check_id(post_id)
    f = clean(s)
    want = (s.slug or "").strip()
    files = file_slugs()

    def tx(c: psycopg.Connection) -> dict:
        cur = _get(c, post_id, uid, lock=True)
        if cur is None:
            raise _err(404, "no_post", blog.NOT_FOUND)
        if cur["status"] == "deleted":
            raise _err(409, "deleted", "This post is deleted. Restore it to edit it.")
        if cur["revision"] != s.revision:
            raise Conflict(cur)
        _room(c, max(0, f["body_bytes"] * 2 - cur["bytes"]))
        slug, problem = cur["slug"], None
        if want and want != cur["slug"]:
            if cur["status"] == "published":
                problem = "published"
            else:
                problem = slug_problem(want) if want not in files else "taken_by_file"
                if problem is None and c.execute("select 1 from blog.posts where slug = %s and id <> %s",
                                                 (want, post_id)).fetchone():
                    problem = "taken"
                if problem is None:
                    slug = want
        rev = cur["revision"] + 1
        r = c.execute(f"update blog.posts set slug = %s, title = %s, summary = %s, body = %s, body_bytes = %s, "
                      f"minutes = %s, tags = %s, author = %s, revision = %s, updated_at = now() where id = %s "
                      f"returning {COLS}, body",
                      (slug, f["title"], f["summary"], f["body"], f["body_bytes"], f["minutes"], f["tags"], f["author"],
                       rev, post_id)).fetchone()
        _revision(c, post_id, rev, f["title"], f["body"], f["body_bytes"], autosave=s.autosave)
        out = _row(r, r[15])
        if problem:
            out["slug_problem"] = problem
            out["slug_words"] = SLUG_WORDS[problem]
        return out
    out = db.run_rw(tx, purpose=PURPOSE)
    if out["status"] == "published":
        _published_changed()
    return out


def _status(uid: str, post_id: str, action: str, revision: int | None = None) -> dict[str, Any]:
    post_id = _check_id(post_id)
    files = file_slugs()

    def tx(c: psycopg.Connection) -> dict:
        cur = _get(c, post_id, uid, body=False, lock=True)
        if cur is None:
            raise _err(404, "no_post", blog.NOT_FOUND)
        if revision is not None and cur["revision"] != revision:
            full = _get(c, post_id, uid)
            raise Conflict(full)
        st = cur["status"]
        if action == "publish":
            if st == "deleted":
                raise _err(409, "deleted", "This post is deleted. Restore it first.")
            if not cur["title"]:
                raise _err(400, "no_title", "A post needs a title before it is published.")
            if cur["slug"] in files or cur["slug"] in RESERVED:
                raise _err(409, "slug_taken", SLUG_WORDS["taken_by_file"])
            sql = ("update blog.posts set status = 'published', published_at = coalesce(published_at, now()), "
                   "updated_at = now() where id = %s")
        elif action == "unpublish":
            if st != "published":
                raise _err(409, "not_published", "This post is not published.")
            sql = "update blog.posts set status = 'draft', updated_at = now() where id = %s"
        elif action == "delete":
            if st == "deleted":
                return _get(c, post_id, uid, body=False)
            sql = "update blog.posts set status = 'deleted', deleted_at = now(), updated_at = now() where id = %s"
        else:                                                                 # restore
            if st != "deleted":
                raise _err(409, "not_deleted", "This post is not deleted.")
            sql = "update blog.posts set status = 'draft', deleted_at = null, updated_at = now() where id = %s"
        c.execute(sql, (post_id,))
        return _get(c, post_id, uid, body=False)
    out = db.run_rw(tx, purpose=PURPOSE)
    _published_changed()
    return out


def export(uid: str) -> tuple[bytes, int, str]:
    """Every post of this editor that is not deleted, as blog/*.md files in one zip (the files' own front matter:
    blog.parse_post reads each back to the same post). Bounded by the storage cap (≤ 30 MB of bodies)."""
    rows, today = db.run_rw(lambda c: (c.execute(
        f"select {COLS}, body from blog.posts where account_id = %s and status <> 'deleted' order by created_at",
        (uid,)).fetchall(), c.execute("select (now() at time zone 'America/New_York')::date").fetchone()[0]),
        purpose=PURPOSE)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rows:
            p = _row(r, r[15])
            z.writestr(f"blog/{p['date']}-{p['slug']}.md", to_markdown(p))
    return buf.getvalue(), len(rows), today.isoformat()


def _q(v: str) -> str:
    return '"' + v + '"'           # blog._scalar strips one pair of quotes: the value comes back as it is


def to_markdown(p: dict[str, Any]) -> str:
    lines = ["---", f"title: {_q(p['title'] or 'Untitled')}", f"date: {p['date']}"]
    if p["summary"]:
        lines.append(f"summary: {_q(p['summary'])}")
    if p["author"]:
        lines.append(f"author: {_q(p['author'])}")
    if p["tags"]:
        lines.append("tags: [" + ", ".join(p["tags"]) + "]")
    if p["status"] != "published":
        lines.append("draft: true")
    lines += ["---", "", p["body"]]
    return "\n".join(lines)


# ---------------------------------------------------------------- the public side (blog.py reads these)
def published_meta() -> list[dict[str, Any]]:
    """The published database posts' meta (no bodies), newest first; [] without the schema. One query a minute."""
    return _published()[1]


def live() -> bool:
    """The `blog` table is there to read: the public answers then say `no-cache` (a post published a moment ago shows
    on the next load: max-age=0, must-revalidate); without it they keep the files' five minutes."""
    return _published()[0]


def _published() -> tuple[bool, list[dict[str, Any]]]:
    hit = _pub.get("list")
    if hit is None:
        hit = _pub.put("list", _read_published())
    return hit


def _read_published() -> tuple[bool, list[dict[str, Any]]]:
    try:
        with db.pool().connection(timeout=5) as c:
            if c.execute("select has_table_privilege(to_regclass(%s), 'select')", TABLES[:1]).fetchone()[0] is not True:
                return False, []
            rows = c.execute("select slug, title, summary, tags, author, minutes, published_at from blog.posts "
                             "where status = 'published' order by published_at desc limit %s", (MAX_POSTS,)).fetchall()
    except Exception as exc:                                         # noqa: BLE001 - the files' blog stays up
        log.info("blog: database posts not read (%s)", exc.__class__.__name__)
        return False, []
    out = []
    for slug, title, summary, tags, author, minutes, published in rows:
        if not blog.SLUG.fullmatch(slug or "") or not title:
            continue
        out.append({"slug": slug, "title": title, "date": _date(published), "summary": summary or "",
                    "author": author or blog.SITE_AUTHOR, "tags": list(tags or []), "minutes": minutes or 1,
                    "image": None, "draft": False, "source": "db"})
    return True, out


def published_body(slug: str) -> str | None:
    """A published database post's body — call only with a slug from ``published_meta()`` (the cache's keys are that
    closed set). None when it is gone or cannot be read."""
    key = ("body", slug)
    hit = _pub.get(key)
    if hit is None:
        try:
            with db.pool().connection(timeout=5) as c:
                r = c.execute("select body from blog.posts where slug = %s and status = 'published'", (slug,)).fetchone()
        except Exception as exc:                                     # noqa: BLE001
            log.info("blog: a database post not read (%s)", exc.__class__.__name__)
            return None
        hit = _pub.put(key, (r[0],) if r else (None,), nbytes=len(r[0].encode()) if r else 64)
    return hit[0]


# ---------------------------------------------------------------- the routes (blog.py includes `router` into its own)
router = APIRouter(dependencies=[Depends(accounts.same_site)])


def _json(body: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers=NO_STORE)


def _conflict(exc: Conflict) -> JSONResponse:
    words = "This post was changed somewhere else (another tab or device). Here is the newer version."
    return _json({"error": words, "detail": words, "code": "conflict", "post": exc.post}, 409)


def mine_route(request: Request) -> JSONResponse:
    uid, _sid = editor(request)
    return _json(mine(uid))


def export_route(request: Request) -> Response:
    uid, _sid = editor(request)
    data, n, stamp = export(uid)
    return Response(data, media_type="application/zip", headers={
        **NO_STORE, "Content-Disposition": f'attachment; filename="isuckatfantasy-blog-{stamp}.zip"', "X-Posts": str(n)})


@router.get("/api/blog/posts/{post_id}")
def post_route(post_id: str, request: Request) -> JSONResponse:
    uid, _sid = editor(request)
    return _json(get_post(uid, post_id))


@router.get("/api/blog/posts/{post_id}/revisions/{rid}")
def revision_route(post_id: str, rid: int, request: Request) -> JSONResponse:
    uid, _sid = editor(request)
    if rid < 1 or rid > 2**62:
        raise _err(404, "no_revision", "No saved version at that address.")
    return _json(get_revision(uid, post_id, rid))


@router.post("/api/blog/posts", status_code=201)
def create_route(body: PostIn, request: Request) -> JSONResponse:
    uid, _sid = editor(request, write=True)
    return _json(create(uid, body), 201)


@router.put("/api/blog/posts/{post_id}")
def save_route(post_id: str, body: SaveIn, request: Request) -> JSONResponse:
    uid, _sid = editor(request, write=True)
    try:
        return _json(save(uid, post_id, body))
    except Conflict as exc:
        return _conflict(exc)


def _action(action: str):
    def route(post_id: str, request: Request, body: PublishIn | None = None) -> JSONResponse:
        uid, _sid = editor(request, write=True)
        try:
            return _json(_status(uid, post_id, action, body.revision if body else None))
        except Conflict as exc:
            return _conflict(exc)
    route.__name__ = f"{action}_route"
    return route


router.post("/api/blog/posts/{post_id}/publish")(_action("publish"))
router.post("/api/blog/posts/{post_id}/unpublish")(_action("unpublish"))
router.post("/api/blog/posts/{post_id}/restore")(_action("restore"))


@router.delete("/api/blog/posts/{post_id}")
def delete_route(post_id: str, request: Request) -> JSONResponse:
    uid, _sid = editor(request, write=True)
    return _json(_status(uid, post_id, "delete"))


# ---------------------------------------------------------------- pictures (blog.images; served by blog.py's pages router)
def image_kind(data: bytes) -> str | None:
    """png / jpg / webp by the first bytes (the name and the declared type are never trusted); None for anything else
    (svg, gif, html named .png …)."""
    for kind in ("png", "jpg", "webp"):
        if blog._looks_like(kind, data[:16]):
            return kind
    return None


def upload(uid: str, data: bytes) -> dict[str, Any]:
    if len(data) > MAX_IMAGE_BYTES:
        raise _err(413, "too_big", f"A picture is {MAX_IMAGE_BYTES // 1024} KB at most. Make it smaller first.")
    kind = image_kind(data)
    if kind is None or len(data) < 12:
        raise _err(400, "bad_image", "A picture is a PNG, JPEG or WebP file.")

    def tx(c: psycopg.Connection) -> dict:
        if c.execute("select count(*) from blog.images").fetchone()[0] >= MAX_IMAGES:
            raise _err(409, "too_many_images", f"The blog holds {MAX_IMAGES} pictures at most. Delete one first.")
        _room(c, len(data))
        r = c.execute("insert into blog.images (kind, bytes, size, account_id) values (%s, %s, %s, %s) "
                      "returning id, created_at", (kind, data, len(data), uid)).fetchone()
        return {"id": str(r[0]), "url": f"/blog/img/db/{r[0]}", "kind": kind, "size": len(data), "created_at": _iso(r[1])}
    return db.run_rw(tx, purpose=PURPOSE)


def remove_image(uid: str, image_id: str) -> None:
    image_id = _check_id(image_id)
    n = db.run_rw(lambda c: c.execute("delete from blog.images where id = %s and account_id = %s",
                                      (image_id, uid)).rowcount, purpose=PURPOSE)
    if not n:
        raise _err(404, "no_image", "No picture at that address.")
    _pub.pop(("img", image_id))


def image(image_id: str) -> tuple[str, bytes] | None:
    """(kind, bytes) of a stored picture, or None — the id checked first; kept in the budget's region only once it
    exists (the keys are the ≤ 50 stored ids: a closed set)."""
    if not isinstance(image_id, str) or not _ID.fullmatch(image_id):
        return None
    hit = _pub.get(("img", image_id))
    if hit is not None:
        return hit
    try:
        with db.pool().connection(timeout=5) as c:
            if c.execute("select has_table_privilege(to_regclass(%s), 'select')", TABLES[2:3]).fetchone()[0] is not True:
                return None
            r = c.execute("select kind, bytes from blog.images where id = %s", (image_id,)).fetchone()
    except Exception as exc:                                         # noqa: BLE001
        log.info("blog: a picture not read (%s)", exc.__class__.__name__)
        return None
    if r is None or r[0] not in IMAGE_TYPES or image_kind(bytes(r[1])) != r[0]:
        return None
    out = (r[0], bytes(r[1]))
    _pub.put(("img", image_id), out, nbytes=len(out[1]))
    return out


@router.post("/api/blog/images", status_code=201)
async def upload_route(request: Request) -> JSONResponse:
    """The picture is the request's body as it is (no form, no base64): ≤ 320 KB at the Guard, ≤ 300 KB here."""
    data = await request.body()                                     # the Guard bounds it (security.body_limit)

    def work() -> dict:                                             # the session check and the insert: off the loop
        uid, _sid = editor(request, write=True)
        return upload(uid, data)
    return _json(await run_in_threadpool(work), 201)


@router.delete("/api/blog/images/{image_id}")
def image_delete_route(image_id: str, request: Request) -> JSONResponse:
    uid, _sid = editor(request, write=True)
    remove_image(uid, image_id)
    return _json({"ok": True})


def image_response(image_id: str) -> Response:
    got = image(image_id)
    if got is None:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    return Response(got[1], media_type=IMAGE_TYPES[got[0]], headers={"Cache-Control": IMAGE_CACHE})
