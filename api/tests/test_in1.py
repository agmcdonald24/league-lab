"""Wave I-N, IN-1: the blog (league_lab_api/blog.py) — the folder reader, the routes, the feed, the pictures, the
sitemap, the link previews in the HTML shell, and the rate-limit buckets. No database needed."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from league_lab_api import blog, ratelimit, security
from league_lab_api.main import app
from league_lab_api.settings import ROOT

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64


def post(title: str = "A post", date: str = "2026-10-06", extra: str = "", body: str = "Hello **world**.") -> str:
    return f"---\ntitle: {title}\ndate: {date}\nsummary: The summary.\ntags: [matchups, Receivers]\n{extra}---\n\n{body}\n"


@pytest.fixture
def folder(tmp_path, monkeypatch):
    d = tmp_path / "blog"
    d.mkdir()
    (d / "img").mkdir()
    monkeypatch.setenv("LEAGUE_LAB_BLOG_DIR", str(d))
    monkeypatch.delenv("LEAGUE_LAB_BLOG_DRAFTS", raising=False)
    blog.reset()
    yield d
    blog.reset()


@pytest.fixture
def api(monkeypatch):
    for k in ("LEAGUE_LAB_APP_PASSWORD", "LEAGUE_LAB_API_SECRET", "LEAGUE_LAB_GATE"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(app) as c:
        yield c


# ====================================================================================== the folder
def test_front_matter_and_the_record(folder):
    (folder / "2026-10-06-first-post.md").write_text(post(body="word " * 500))
    (folder / "2026-10-01-older.md").write_text(post("Older", "2026-10-01", "author: Andrew\nimage: chart-1.png\n"))
    posts = blog.load(folder)
    assert [p["slug"] for p in posts] == ["first-post", "older"]                    # newest first
    p = posts[0]
    assert p["title"] == "A post" and p["date"] == "2026-10-06" and p["summary"] == "The summary."
    assert p["author"] == "isuckatfantasy"                                           # no author: the site's
    assert p["tags"] == ["matchups", "receivers"] and p["minutes"] == 3              # 500 words at 220 a minute
    assert posts[1]["author"] == "Andrew" and posts[1]["image"] == "/blog/img/chart-1.png"


def test_what_is_not_a_post(folder):
    (folder / "README.md").write_text("# how to write")
    (folder / "_template.md").write_text(post())
    (folder / "2026-10-06-No-Caps.md").write_text(post())
    (folder / "2026-10-06-double--hyphen.md").write_text(post())
    (folder / "2026-10-06-untitled.md").write_text("---\ndate: 2026-10-06\n---\nbody")
    (folder / "2026-10-06-no-front-matter.md").write_text("just text")
    (folder / "2026-10-06-a-picture-elsewhere.md").write_text(post(extra="image: https://evil.example/x.png\n"))
    (folder / "2026-10-06-big.md").write_text(post(body="x" * (blog.MAX_POST_KB * 1024 + 10)))
    (folder / "notes.txt").write_text(post())
    posts = blog.load(folder)
    assert [p["slug"] for p in posts] == ["a-picture-elsewhere"]
    assert posts[0]["image"] is None                                                 # only blog/img/ pictures


def test_drafts_only_when_switched_on(folder, monkeypatch, api):
    (folder / "2026-10-06-ready.md").write_text(post())
    (folder / "2026-10-07-not-yet.md").write_text(post("Draft", "2026-10-07", "draft: true\n"))
    assert [p["slug"] for p in api.get("/api/blog").json()["posts"]] == ["ready"]
    assert api.get("/api/blog/not-yet").status_code == 404
    monkeypatch.setenv("LEAGUE_LAB_BLOG_DRAFTS", "on")
    d = api.get("/api/blog").json()["posts"]
    assert [p["slug"] for p in d] == ["not-yet", "ready"] and d[0]["draft"] is True
    assert api.get("/api/blog/not-yet").status_code == 200


def test_a_repeated_slug_serves_one_post(folder):
    (folder / "2026-10-06-same.md").write_text(post("Newer"))
    (folder / "2026-09-01-same.md").write_text(post("Older", "2026-09-01"))
    posts = blog.load(folder)
    assert [(p["slug"], p["title"]) for p in posts] == [("same", "Newer")]


def test_an_absent_folder_is_an_empty_blog(tmp_path, monkeypatch, api):
    monkeypatch.setenv("LEAGUE_LAB_BLOG_DIR", str(tmp_path / "nowhere"))
    blog.reset()
    try:
        r = api.get("/api/blog")
        assert r.status_code == 200 and r.json() == {"posts": []}
        assert api.get("/api/blog/anything").status_code == 404
        assert "<rss" in api.get("/blog/rss.xml").text
        assert api.get("/blog/img/x.png").status_code == 404
    finally:
        blog.reset()


# ====================================================================================== the routes
def test_list_and_post(folder, api):
    for i in range(1, 6):
        (folder / f"2026-10-0{i}-post-{i}.md").write_text(post(f"Post {i}", f"2026-10-0{i}"))
    r = api.get("/api/blog", params={"limit": 3})
    assert r.status_code == 200 and "max-age" in r.headers["cache-control"]
    posts = r.json()["posts"]
    assert [p["slug"] for p in posts] == ["post-5", "post-4", "post-3"]
    assert set(posts[0]) == {"slug", "title", "date", "summary", "author", "tags", "minutes", "image"}
    one = api.get("/api/blog/post-2").json()
    assert one["title"] == "Post 2" and one["markdown"].strip() == "Hello **world**."
    for bad in (0, 51, -1):
        assert api.get("/api/blog", params={"limit": bad}).status_code == 400
    assert api.get("/api/blog", params={"limit": "x"}).status_code == 422


@pytest.mark.parametrize("slug", ["..", "..%2F..%2Fsettings", "%2e%2e", "POST-1", "post_1", "post-1.md", "a" * 81,
                                  "post-1%00", "-post", "post--1", "%2Fetc%2Fpasswd", "README", "_template"])
def test_hostile_slugs_are_404_and_never_opened(folder, api, monkeypatch, slug):
    (folder / "2026-10-01-post-1.md").write_text(post())
    blog.index()                                                   # the folder read once, before the hostile asks
    opened: list[str] = []
    real_open = Path.open
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: opened.append(str(self)) or "")
    monkeypatch.setattr(Path, "open", lambda self, *a, **k: opened.append(str(self)) or real_open(self, *a, **k))
    r = api.get(f"/api/blog/{slug}")
    assert r.status_code == 404, slug
    assert opened == [], opened


# ====================================================================================== the feed and the sitemap
def test_rss_is_valid_and_escaped(folder, api):
    (folder / "2026-10-06-tricky.md").write_text(post('Start <b>him</b> & "sit" her', body="x"))
    r = api.get("/blog/rss.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/rss+xml")
    root = ET.fromstring(r.content)
    item = root.find("channel/item")
    assert item.findtext("title") == 'Start <b>him</b> & "sit" her'
    assert item.findtext("link") == "https://isuckatfantasy.io/blog/tricky"
    assert item.findtext("pubDate").startswith("Tue, 06 Oct 2026")
    assert "<b>" not in r.text


def test_sitemap_lists_home_blog_posts_and_tools(folder, api):
    (folder / "2026-10-06-first.md").write_text(post())
    root = ET.fromstring(api.get("/sitemap.xml").content)
    locs = [e.text for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert "https://isuckatfantasy.io/" in locs and "https://isuckatfantasy.io/blog" in locs
    assert "https://isuckatfantasy.io/blog/first" in locs
    for tool in ("/players", "/matchups", "/trade-calc", "/dfs", "/home"):
        assert f"https://isuckatfantasy.io{tool}" in locs


def test_robots_points_at_the_sitemap():
    text = (ROOT / "web" / "public" / "robots.txt").read_text()
    assert "Sitemap: https://isuckatfantasy.io/sitemap.xml" in text and "Disallow: /api/" in text


# ====================================================================================== the pictures
def test_images(folder, api):
    img = folder / "img"
    (img / "chart.png").write_bytes(PNG)
    (img / "photo.jpg").write_bytes(JPG)
    (img / "pic.webp").write_bytes(WEBP)
    (img / "evil.svg").write_text("<svg onload=alert(1)>")
    (img / "fake.png").write_text("<html><script>alert(1)</script></html>")
    (img / "big.png").write_bytes(PNG + b"\x00" * (blog.MAX_IMG_KB * 1024))
    (folder / "secret.png").write_bytes(PNG)
    os.symlink(folder / "secret.png", img / "link.png")
    r = api.get("/blog/img/chart.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and "max-age=2592000" in r.headers["cache-control"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert api.get("/blog/img/photo.jpg").headers["content-type"] == "image/jpeg"
    assert api.get("/blog/img/pic.webp").headers["content-type"] == "image/webp"
    for bad in ("evil.svg", "fake.png", "big.png", "link.png", "Chart.png", "..%2Fsecret.png", "missing.png", "chart.png.exe",
                "chart.gif", ".png", "a" * 90 + ".png"):
        assert api.get(f"/blog/img/{bad}").status_code == 404, bad


# ====================================================================================== the link previews
@pytest.fixture
def dist(tmp_path, monkeypatch):
    d = tmp_path / "dist"
    d.mkdir()
    src = (ROOT / "web" / "index.html").read_text()
    (d / "index.html").write_text(src)
    monkeypatch.setenv("LEAGUE_LAB_WEB_DIST", str(d))
    return d


def _meta(text: str, prop: str) -> str | None:
    m = re.search(rf'<meta (?:property|name)="{re.escape(prop)}" content="([^"]*)"', text)
    return m.group(1) if m else None


def test_the_shell_previews_each_public_path(folder, dist, api):
    (folder / "2026-10-06-how-to-read.md").write_text(post("How to read <it> & \"why\"", extra="image: chart.png\n"))
    home = api.get("/")
    assert home.status_code == 200 and "<title>isuckatfantasy</title>" in home.text    # the image workflow's grep
    assert _meta(home.text, "og:image") == "https://isuckatfantasy.io/og.png"
    assert _meta(home.text, "twitter:card") == "summary_large_image"
    b = api.get("/blog").text
    assert "<title>Blog · isuckatfantasy</title>" in b and 'rel="canonical" href="https://isuckatfantasy.io/blog"' in b
    p = api.get("/blog/how-to-read")
    assert p.status_code == 200 and p.headers["cache-control"] == "no-cache"
    assert "<title>How to read &lt;it&gt; &amp; &quot;why&quot; · isuckatfantasy</title>" in p.text
    assert "<it>" not in p.text
    assert _meta(p.text, "og:type") == "article" and _meta(p.text, "og:url") == "https://isuckatfantasy.io/blog/how-to-read"
    assert _meta(p.text, "og:description") == "The summary."
    assert _meta(p.text, "og:image") == "https://isuckatfantasy.io/blog/img/chart.png"
    assert _meta(p.text, "article:published_time") == "2026-10-06"
    for path, title in (("/players", "Every player's numbers"), ("/matchups", "This week's matchups"), ("/trade-calc", "Trade calculator"),
                        ("/dfs", "Daily fantasy values"), ("/home", "isuckatfantasy")):
        t = api.get(path, params={"league": "ref:half"}).text
        assert f"<title>{title}" in t.replace("&#x27;", "'"), path
        assert t.count("<title>") == 1 and t.count('property="og:title"') == 1, path
    other = api.get("/player/00-0036963").text
    assert other == (dist / "index.html").read_text()                                   # everything else: the default
    nope = api.get("/blog/no-such-post")
    assert nope.status_code == 404 and "<title>Blog · isuckatfantasy</title>" in nope.text and '<div id="app">' in nope.text


def test_the_inline_script_keeps_its_csp_hash(folder, dist, api):
    page = api.get("/blog").text
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", page, re.S)
    assert len(scripts) == 1
    served = "'sha256-" + base64.b64encode(hashlib.sha256(scripts[0].encode()).digest()).decode() + "'"
    assert security.inline_hashes(dist / "index.html") == [served]
    assert served in api.get("/blog").headers["content-security-policy"]


def test_a_shell_without_markers_is_served_as_it_is(folder, dist, api):
    (dist / "index.html").write_text('<!doctype html><title>x</title><div id="app"></div>')
    assert api.get("/blog").text == '<!doctype html><title>x</title><div id="app"></div>'


# ====================================================================================== the limiter and the launch posts
def test_every_new_route_has_a_bucket():
    assert ratelimit.bucket_for("GET", "/api/blog", "limit=3") == "read"
    assert ratelimit.bucket_for("GET", "/api/blog/how-to-read") == "read"
    assert ratelimit.bucket_for("GET", "/blog/rss.xml") == "read"
    assert ratelimit.bucket_for("GET", "/sitemap.xml") == "read"
    assert ratelimit.bucket_for("GET", "/blog/img/chart.png") == "read"
    assert ratelimit.bucket_for("GET", "/blog") is None and ratelimit.bucket_for("GET", "/blog/a-post") is None  # the shell


def test_the_repository_blog(monkeypatch):
    monkeypatch.delenv("LEAGUE_LAB_BLOG_DIR", raising=False)
    posts = blog.load(ROOT / "blog", drafts=False)
    first = next(p for p in posts if p["slug"] == "how-to-read-this-sites-numbers")
    assert first["author"] == "isuckatfantasy" and first["title"] == "How to read this site's numbers"
    assert not any(p["slug"] in ("readme", "template") for p in posts)
    for p in posts:                                         # every post's links stay on our own paths or https
        for href in re.findall(r"\]\(([^)\s]+)\)", p["markdown"]):
            assert href.startswith("/") or href.startswith("https://"), (p["slug"], href)
