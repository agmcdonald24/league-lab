"""The blog (Wave I-N, IN-1; docs/BLOG.md): posts are markdown files in the repository, read once, served as JSON for
the web app's screens, as an RSS feed, and as the link previews in the HTML shell.

    blog/<yyyy-mm-dd>-<slug>.md      a post: a small front matter (title, date, summary, author, tags, draft, image)
    blog/img/<name>.png|jpg|webp     its pictures (svg is refused: it can carry script)

Routes:
    GET /api/blog?limit=             {"posts": [{slug, title, date, summary, author, tags, minutes, image}]}, newest first
    GET /api/blog/{slug}             one post: the meta + "markdown" (rendered by the web's lib/md.ts, escaping first)
    GET /blog/rss.xml                the newest 20 posts as RSS 2.0
    GET /blog/img/{name}             an image (strict name, png / jpg / webp checked by its first bytes, ≤ 2 MB)
    GET /sitemap.xml                 home, the blog, each post, the public tools

The folder is ``LEAGUE_LAB_BLOG_DIR``, default ``<repo>/blog`` (``/srv/blog`` in the image). An absent folder is an empty
blog, never an error. Nothing from a URL reaches the filesystem: a slug is looked up in the index the folder produced;
an image name must match ``IMG_NAME`` and is joined to the image folder only after that. Drafts (``draft: true``) are
left out unless ``LEAGUE_LAB_BLOG_DRAFTS=on`` (a preview on a laptop). The index is one entry in the memory budget
(``league_lab.memo`` region ``blog``: one key per folder × drafts switch, an hour, re-read after that — "push to
publish" is a deploy, so a running server never needs to notice a new file sooner). Bounded: at most ``MAX_POSTS``
posts of at most ``MAX_POST_KB`` each; anything over is skipped and logged, never served.
"""

from __future__ import annotations

import html
import logging
import math
import re
from datetime import date, datetime, time
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from league_lab import memo

from .settings import APP_NAME, ROOT, env

_log = logging.getLogger("league_lab_api.blog")

ORIGIN = "https://isuckatfantasy.io"
SITE_AUTHOR = APP_NAME                      # a post with no author is the site's
FILE_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IMG_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}\.(png|jpg|jpeg|webp)$")
IMG_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
MAX_SLUG = 80
MAX_POSTS = 300
MAX_POST_KB = 200
MAX_IMG_KB = 2048
MAX_TITLE, MAX_SUMMARY, MAX_TAGS, MAX_TAG = 140, 400, 8, 32
LIST_MAX, LIST_DEFAULT, FEED_N = 50, 20, 20
WORDS_PER_MINUTE = 220
IMG_CACHE = "public, max-age=2592000"       # 30 days: a changed picture gets a new name (docs/BLOG.md)
FEED_CACHE = "public, max-age=600"
NOT_FOUND = "No post at that address."
ET = ZoneInfo("America/New_York")

_region = memo.region("blog", ttl=3600.0, max_entries=4)


def folder() -> Path:
    """Where the posts are: LEAGUE_LAB_BLOG_DIR, else <repo>/blog (the image: /srv/blog)."""
    return Path(env("BLOG_DIR") or ROOT / "blog")


def drafts_on() -> bool:
    return env("BLOG_DRAFTS").strip().lower() in ("on", "1", "true", "yes")


# ------------------------------------------------------------------------------------------------ reading the folder
def _scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v.strip()


def front_matter(text: str) -> tuple[dict[str, str], str]:
    """A post's ``---`` block (``key: value`` lines; a list as ``[a, b]`` or ``a, b``) and its body. No YAML engine:
    a line that is not ``key: value`` is ignored, so nothing in a post can make the reader do more than split lines."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1:]).lstrip("\n")
        m = re.match(r"^([a-z_]+)\s*:\s*(.*)$", line.strip())
        if m:
            meta[m.group(1)] = m.group(2)
    return {}, text                                   # no closing line: the whole file is the body


def _tags(v: str | None) -> list[str]:
    raw = (v or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    out = []
    for t in raw.split(","):
        t = _scalar(t).lower()
        if t and len(t) <= MAX_TAG and re.fullmatch(r"[a-z0-9][a-z0-9 -]*", t) and t not in out:
            out.append(t)
    return out[:MAX_TAGS]


def _truthy(v: str | None) -> bool:
    return _scalar(v or "").lower() in ("true", "yes", "on", "1")


def minutes(body: str) -> int:
    """Minutes to read: words (code blocks and the players block included) at 220 a minute, at least one."""
    return max(1, math.ceil(len(re.findall(r"\S+", body)) / WORDS_PER_MINUTE))


def parse_post(name: str, text: str) -> dict[str, Any] | None:
    """One file → the post's record, or None (a name off the pattern, no title). The file name gives the slug; the
    front matter's ``date`` wins over the name's when it is a real date."""
    m = FILE_NAME.match(name)
    if not m or len(m.group(2)) > MAX_SLUG:
        return None
    meta, body = front_matter(text)
    title = _scalar(meta.get("title", ""))[:MAX_TITLE]
    if not title:
        return None
    d = None
    for cand in (_scalar(meta.get("date", "")), m.group(1)):
        try:
            d = date.fromisoformat(cand[:10])
            break
        except ValueError:
            continue
    if d is None:
        return None
    image = _scalar(meta.get("image", "")) or None
    if image and image.startswith("/blog/img/"):
        image = image[len("/blog/img/"):]
    if image and not IMG_NAME.match(image):
        image = None                                   # only a picture from blog/img/ can be a post's picture
    return {"slug": m.group(2), "title": title, "date": d.isoformat(), "summary": _scalar(meta.get("summary", ""))[:MAX_SUMMARY],
            "author": _scalar(meta.get("author", ""))[:60] or SITE_AUTHOR, "tags": _tags(meta.get("tags")),
            "minutes": minutes(body), "image": f"/blog/img/{image}" if image else None,
            "draft": _truthy(meta.get("draft")), "markdown": body, "file": name}


def load(where: Path | None = None, *, drafts: bool | None = None) -> list[dict[str, Any]]:
    """Every post in the folder, newest first (then by slug); drafts only when switched on. Never raises."""
    where = where or folder()
    drafts = drafts_on() if drafts is None else drafts
    posts: list[dict[str, Any]] = []
    try:
        names = sorted((p.name for p in where.iterdir() if p.is_file() and p.suffix == ".md"), reverse=True)
    except OSError:
        return []                                      # no folder: an empty blog
    seen: set[str] = set()
    for name in names:
        if len(posts) >= MAX_POSTS:
            _log.warning("blog: more than %d posts; the oldest are not served", MAX_POSTS)
            break
        p = where / name
        try:
            if p.is_symlink() or p.stat().st_size > MAX_POST_KB * 1024:
                _log.warning("blog: %s skipped (a link, or over %d KB)", name, MAX_POST_KB)
                continue
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _log.warning("blog: %s unreadable: %s", name, exc)
            continue
        post = parse_post(name, text)
        if post is None or (post["draft"] and not drafts):
            continue
        if post["slug"] in seen:
            _log.warning("blog: %s repeats the slug %r; the newer file is served", name, post["slug"])
            continue
        seen.add(post["slug"])
        posts.append(post)
    posts.sort(key=lambda x: (x["date"], x["slug"]), reverse=True)
    return posts


def index() -> list[dict[str, Any]]:
    """The posts, read once per hour per folder (a memo entry; the key is the folder and the drafts switch)."""
    key = (str(folder()), drafts_on())
    hit = _region.get(key)
    if hit is None:
        hit = _region.put(key, load())
    return hit


def reset() -> None:
    _region.clear()


META = ("slug", "title", "date", "summary", "author", "tags", "minutes", "image")


def meta(post: dict[str, Any]) -> dict[str, Any]:
    out = {k: post[k] for k in META}
    if post.get("draft"):
        out["draft"] = True
    return out


def find(slug: str) -> dict[str, Any] | None:
    """The post with this slug, or None — the slug is checked against the pattern and then looked up, never opened."""
    if not isinstance(slug, str) or len(slug) > MAX_SLUG or not SLUG.match(slug):
        return None
    return next((p for p in index() if p["slug"] == slug), None)


# ------------------------------------------------------------------------------------------------ the routes
router = APIRouter()        # /api/blog…: behind the gate like every /api/ route (main.py: require_auth)
pages = APIRouter()         # the feed, the pictures, the sitemap: what crawlers and link previews read, never gated


@router.get("/api/blog")
def blog_list(limit: int = LIST_DEFAULT) -> JSONResponse:
    if limit < 1 or limit > LIST_MAX:
        raise HTTPException(status_code=400, detail=f"limit is 1 to {LIST_MAX}")
    return JSONResponse({"posts": [meta(p) for p in index()[:limit]]}, headers={"Cache-Control": "public, max-age=300"})


@router.get("/api/blog/{slug}")
def blog_post(slug: str) -> JSONResponse:
    post = find(slug)
    if post is None:
        return JSONResponse({"error": NOT_FOUND, "detail": NOT_FOUND, "code": "no_post"}, status_code=404,
                            headers={"Cache-Control": "no-store"})
    return JSONResponse({**meta(post), "markdown": post["markdown"]}, headers={"Cache-Control": "public, max-age=300"})


def _rfc822(d: str) -> str:
    return format_datetime(datetime.combine(date.fromisoformat(d), time(8, 0), tzinfo=ET))


def rss() -> str:
    x = lambda s: html.escape(str(s), quote=True)  # noqa: E731
    items = []
    for p in index()[:FEED_N]:
        url = f"{ORIGIN}/blog/{p['slug']}"
        items.append(f"<item><title>{x(p['title'])}</title><link>{x(url)}</link><guid isPermaLink=\"true\">{x(url)}</guid>"
                     f"<pubDate>{x(_rfc822(p['date']))}</pubDate><description>{x(p['summary'])}</description>"
                     + "".join(f"<category>{x(t)}</category>" for t in p["tags"]) + "</item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            f"<title>{x(APP_NAME)} · Blog</title><link>{ORIGIN}/blog</link>"
            f"<description>{x(BLOG_DESCRIPTION)}</description><language>en-us</language>"
            + "".join(items) + "</channel></rss>\n")


@pages.get("/blog/rss.xml", include_in_schema=False)
def blog_rss() -> Response:
    return Response(rss(), media_type="application/rss+xml; charset=utf-8", headers={"Cache-Control": FEED_CACHE})


def _looks_like(kind: str, head: bytes) -> bool:
    if kind == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if kind in ("jpg", "jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


@pages.get("/blog/img/{name}", include_in_schema=False)
def blog_image(name: str) -> Response:
    m = IMG_NAME.match(name or "")
    if not m:
        raise HTTPException(status_code=404, detail="no such image")
    kind = m.group(1)
    base = (folder() / "img").resolve()
    f = base / name                                     # the name is [a-z0-9_-] + one extension: no separator, no dot-dot
    try:
        if f.is_symlink() or not f.is_file() or f.resolve().parent != base:
            raise HTTPException(status_code=404, detail="no such image")
        if f.stat().st_size > MAX_IMG_KB * 1024:
            _log.warning("blog: image %s over %d KB, not served", name, MAX_IMG_KB)
            raise HTTPException(status_code=404, detail="no such image")
        with f.open("rb") as fh:
            head = fh.read(16)
    except OSError as exc:
        raise HTTPException(status_code=404, detail="no such image") from exc
    if not _looks_like(kind, head):
        raise HTTPException(status_code=404, detail="no such image")
    return FileResponse(f, media_type=IMG_TYPES[kind], headers={"Cache-Control": IMG_CACHE})


# ------------------------------------------------------------------------------------------------ previews, sitemap
BLOG_DESCRIPTION = "Fantasy football analysis from isuckatfantasy: what the numbers say, how they are made, and where they have been wrong."
DEFAULT_TITLE = APP_NAME                    # "/" keeps the plain name: the image workflow's smoke step greps <title>isuckatfantasy</title>
DEFAULT_DESCRIPTION = ("Who to start this week and what each player is worth, in your league's own scoring — on Sleeper, "
                       "MyFantasyLeague, ESPN or Yahoo. Browse every player's numbers without a league.")
DEFAULT_IMAGE = f"{ORIGIN}/og.png"
# the public tools' previews (path → title, description); everything else gets the default
PAGES: dict[str, tuple[str, str]] = {
    "/": (DEFAULT_TITLE, DEFAULT_DESCRIPTION),
    "/home": (DEFAULT_TITLE, DEFAULT_DESCRIPTION),
    "/blog": (f"Blog · {APP_NAME}", BLOG_DESCRIPTION),
    "/players": (f"Every player's numbers · {APP_NAME}",
                 "Every player's stats, trends and this week's projection with its range, in PPR, Half PPR or Standard scoring."),
    "/matchups": (f"This week's matchups · {APP_NAME}",
                  "Every receiver's matchup this week: the defense against his position and the cornerback he is likely to face."),
    "/trade-calc": (f"Trade calculator · {APP_NAME}",
                    "Weigh a trade in your scoring: each side's value, the difference in words, and how sure the numbers are."),
    "/dfs": (f"Daily fantasy values · {APP_NAME}",
             "This week's projections in DraftKings and FanDuel scoring, with the context the projection does not hold."),
}
SITEMAP_PATHS = ("/home", "/blog", "/players", "/matchups", "/trade-calc", "/dfs")


def preview(path: str) -> dict[str, Any] | None:
    """The link preview for a path: {title, description, url, image, type, published?, status}; None = the default
    block stays as it is (index.html's own). An unknown post is the blog's preview with status 404."""
    p = "/" + path.strip("/") if path.strip("/") else "/"
    if p in PAGES:
        title, desc = PAGES[p]
        return {"title": title, "description": desc, "url": ORIGIN + ("/" if p == "/" else p), "image": DEFAULT_IMAGE,
                "type": "website", "status": 200}
    m = re.fullmatch(r"/blog/([^/]+)", p)
    if m:
        post = find(m.group(1))
        if post is None:
            title, desc = PAGES["/blog"]
            return {"title": title, "description": desc, "url": f"{ORIGIN}/blog", "image": DEFAULT_IMAGE, "type": "website",
                    "status": 404}
        return {"title": f"{post['title']} · {APP_NAME}", "description": post["summary"] or BLOG_DESCRIPTION,
                "url": f"{ORIGIN}/blog/{post['slug']}", "image": ORIGIN + post["image"] if post["image"] else DEFAULT_IMAGE,
                "type": "article", "published": post["date"], "author": post["author"], "status": 200}
    return None


SEO_START, SEO_END = "<!-- ll:seo -->", "<!-- /ll:seo -->"


def seo_tags(pv: dict[str, Any]) -> str:
    """The head's preview tags, every text escaped."""
    a = lambda s: html.escape(str(s), quote=True)  # noqa: E731
    tags = [f"<title>{a(pv['title'])}</title>",
            f'<meta name="description" content="{a(pv["description"])}" />',
            f'<link rel="canonical" href="{a(pv["url"])}" />',
            f'<meta property="og:type" content="{a(pv["type"])}" />',
            f'<meta property="og:site_name" content="{a(APP_NAME)}" />',
            f'<meta property="og:title" content="{a(pv["title"])}" />',
            f'<meta property="og:description" content="{a(pv["description"])}" />',
            f'<meta property="og:url" content="{a(pv["url"])}" />',
            f'<meta property="og:image" content="{a(pv["image"])}" />']
    if pv["image"] == DEFAULT_IMAGE:
        tags += ['<meta property="og:image:width" content="1200" />', '<meta property="og:image:height" content="630" />']
    if pv.get("published"):
        tags.append(f'<meta property="article:published_time" content="{a(pv["published"])}" />')
    tags += ['<meta name="twitter:card" content="summary_large_image" />',
             f'<meta name="twitter:title" content="{a(pv["title"])}" />',
             f'<meta name="twitter:description" content="{a(pv["description"])}" />',
             f'<meta name="twitter:image" content="{a(pv["image"])}" />']
    return "\n    ".join(tags)


_shells: dict[str, tuple[float, str]] = {}


def shell(index_html: Path, path: str) -> tuple[str, int] | None:
    """index.html with this path's preview in place of the default block (between the ``ll:seo`` markers), and the
    status; None = serve the file as it is (no preview for this path, or a build without the markers). The inline
    script is untouched, so the CSP's hash (security.py) still matches."""
    pv = preview(path)
    if pv is None:
        return None
    try:
        mtime = index_html.stat().st_mtime
        hit = _shells.get(str(index_html))
        if hit is None or hit[0] != mtime:
            hit = (mtime, index_html.read_text(encoding="utf-8"))
            _shells[str(index_html)] = hit
    except OSError:
        return None
    text = hit[1]
    i, j = text.find(SEO_START), text.find(SEO_END)
    if i < 0 or j < i:
        return None
    return text[: i + len(SEO_START)] + "\n    " + seo_tags(pv) + "\n    " + text[j:], pv["status"]


def sitemap() -> str:
    urls = [(f"{ORIGIN}/", None)] + [(ORIGIN + p, None) for p in SITEMAP_PATHS]
    urls += [(f"{ORIGIN}/blog/{p['slug']}", p["date"]) for p in index() if not p.get("draft")]
    body = "".join(f"<url><loc>{html.escape(u)}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>" for u, d in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + body + "</urlset>\n")


@pages.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml() -> Response:
    return Response(sitemap(), media_type="application/xml; charset=utf-8", headers={"Cache-Control": FEED_CACHE})
