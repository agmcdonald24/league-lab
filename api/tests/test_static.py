"""The web app served by the API: real files, the SPA fallback, cache headers. Skips when web/dist is not built."""

from __future__ import annotations

import pytest

from league_lab_api.settings import web_dist

pytestmark = pytest.mark.skipif(not (web_dist() / "index.html").exists(), reason="web/dist not built (cd web && npm run build)")


def test_shell_and_routes(client):
    for path in ("/", "/player/00-0036963", "/player/00-0036963?league=1&team=2"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), path
        assert r.headers["cache-control"] == "no-cache"
        assert '<div id="app">' in r.text and 'rel="manifest"' in r.text


def test_manifest_icons_assets(client):
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.headers["content-type"].startswith("application/manifest+json")
    man = m.json()
    assert man["display"] == "standalone" and man["start_url"] == "/"
    for icon in man["icons"]:
        assert client.get(icon["src"]).status_code == 200
    assert client.get("/icons/apple-touch-icon.png").status_code == 200
    asset = next((web_dist() / "assets").glob("*.js"))
    a = client.get(f"/assets/{asset.name}", headers={"Accept-Encoding": "gzip"})
    assert a.status_code == 200 and "immutable" in a.headers["cache-control"] and a.headers.get("content-encoding") == "gzip"
    assert client.get("/assets/nope.js").status_code == 404
    assert client.get("/api/nope").status_code == 404
    assert client.get("/sw.js").headers["cache-control"] == "no-cache"
