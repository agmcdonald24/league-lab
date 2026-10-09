// Wave I-U (IU-6): the blog's cover, pictures made smaller in the browser, YouTube / X embeds and links to any https
// site. Two parts:
//   1. md.ts' new lines as pure functions (no server): the embeds' strict patterns and the post links' rule, with the
//      attacks the review asks for (a quote or slash in an id, look-alike hosts, javascript: / data:, wrong lengths).
//   2. Against the REAL API (its own server on IU6_API_PORT, default 8964, with accounts on, a throwaway secret and an
//      editor made through the app's own code path — io3's recipe): an editor writes a post with a phone-sized picture
//      (made smaller in the browser), makes it the cover, adds a YouTube link, a post on X and an outside link, and
//      publishes. Then the post (banner, the two embeds), the list (thumbnail), the home (thumbnail), and the HTML the
//      server sends a crawler that runs no script (og:image = the cover's absolute https URL). Every outside host is
//      answered or refused by this test itself (pattern web/e2e/ip0): no request leaves for YouTube or X before the tap.
// Phone at 375 and desktop at 1300; screenshots in docs/handbacks/iu6/. The account, its posts and its pictures are
// deleted after. Needs the `blog` schema with the cover column (scripts/hosted_blog.sql) on the database in the env.
import { expect, test, type Route } from "@playwright/test";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { deflateSync } from "node:zlib";

const PORT = Number(process.env.IU6_API_PORT ?? 8964);
const API = `http://localhost:${PORT}`;
const ROOT = join(import.meta.dirname, "..", "..", "..");
const API_DIR = join(ROOT, "api");
const SHOTS = join(ROOT, "docs", "handbacks", "iu6");
const SECRET = randomBytes(24).toString("hex"); // throwaway, this run only — never written anywhere
const EMAIL = `editor-${randomBytes(4).toString("hex")}@iu6.test`;
const YT = "dQw4w9WgXcQ";
const X_URL = "https://x.com/NFL/status/1843000000000000001";

// ============================================================================ part 1: md.ts, pure
test.describe("md.ts: embeds and links", () => {
  test("a YouTube link alone on its line is a Play button and a link — strictly matched", async ({ isMobile }) => {
    test.skip(isMobile, "pure functions: once");
    const { embed, youtubeId, mdDoc } = await import("../../src/lib/md");
    for (const ok of [`https://www.youtube.com/watch?v=${YT}`, `https://youtube.com/watch?v=${YT}&t=42s`, `https://m.youtube.com/watch?v=${YT}`, `https://youtu.be/${YT}`, `https://youtu.be/${YT}?si=abc_DEF-1`, `https://www.youtube.com/shorts/${YT}`])
      expect(youtubeId(ok), ok).toBe(YT);
    for (const bad of [
      `https://www.youtube.com.evil.example/watch?v=${YT}`, // a look-alike host
      `https://youtu.be.evil.example/${YT}`,
      `https://evil.example/youtube.com/watch?v=${YT}`,
      `https://evilyoutube.com/watch?v=${YT}`,
      `http://www.youtube.com/watch?v=${YT}`, // not https
      `https://www.youtube.com/watch?v=dQw4w9WgXc`, // 10 characters
      `https://www.youtube.com/watch?v=dQw4w9WgXcQQ`, // 12
      `https://www.youtube.com/watch?v=dQw4w9WgXc"`, // a quote
      `https://www.youtube.com/watch?v=dQw4w9WgXc'`,
      `https://www.youtube.com/watch?v=dQw4w9/gXcQ`, // a slash
      `https://youtu.be/dQw4w9WgXc%22`,
      `https://www.youtube.com/watch?v=${YT}"><script>alert(1)</script>`,
      `https://www.youtube.com/watch?v=${YT}&x="onload=alert(1)`,
      `https://user@www.youtube.com/watch?v=${YT}`,
      `https://www.youtube.com:8443/watch?v=${YT}`,
      `javascript:alert(1)//https://youtu.be/${YT}`,
      `data:text/html,https://youtu.be/${YT}`,
      `https://www.youtube.com/embed/${YT}`, // not one of the three forms
      ` https://youtu.be/${YT} trailing words`,
    ])
      expect(youtubeId(bad), bad).toBeNull();
    const html = embed(`https://youtu.be/${YT}`)!;
    expect(html).toContain(`data-yt-play="${YT}"`);
    expect(html).toContain(`href="https://www.youtube.com/watch?v=${YT}" rel="noopener noreferrer nofollow ugc" target="_blank"`);
    expect(html).not.toMatch(/<iframe|<script|youtube-nocookie|ytimg|<img/); // nothing asked of YouTube until the tap
    // in a document: only a line on its own; inside a sentence, or a look-alike, it stays text
    const doc = mdDoc(`Words.\n\nhttps://youtu.be/${YT}\n\nSee https://youtu.be/${YT} here.\n\nhttps://youtu.be.evil.example/${YT}`);
    expect(doc.match(/data-yt-play=/g)?.length).toBe(1);
    expect(doc).toContain(`<p>See https://youtu.be/${YT} here.</p>`);
    expect(doc).toContain(`<p>https://youtu.be.evil.example/${YT}</p>`);
    // two lines in one paragraph: not an embed (one link alone on its line only)
    expect(mdDoc(`https://youtu.be/${YT}\nhttps://youtu.be/${YT}`)).not.toContain("data-yt-play");
  });

  test("a post on X alone on its line is a plain link card — no script, the handle and number by pattern", async ({ isMobile }) => {
    test.skip(isMobile, "pure functions: once");
    const { embed, xPost, mdDoc } = await import("../../src/lib/md");
    expect(xPost(X_URL)).toEqual({ handle: "NFL", id: "1843000000000000001" });
    expect(xPost("https://twitter.com/a_b_1/status/12?s=20")).toEqual({ handle: "a_b_1", id: "12" });
    for (const bad of [
      "https://x.com/NF-L/status/1", // a handle with an odd character
      "https://x.com/N%22FL/status/1",
      'https://x.com/NFL"/status/1',
      "https://x.com/NFL/status/1a",
      "https://x.com/abcdefghijklmnop/status/1", // 16 characters
      "https://x.com/NFL/status/123456789012345678901", // 21 digits
      "https://x.com.evil.example/NFL/status/1",
      "https://evil.example/x.com/NFL/status/1",
      "https://x.com/NFL/status/1/photo/1",
      "http://x.com/NFL/status/1",
      "javascript:alert(1)//x.com/NFL/status/1",
    ])
      expect(xPost(bad), bad).toBeNull();
    const html = embed(X_URL)!;
    expect(html).toContain(`href="https://x.com/NFL/status/1843000000000000001" rel="noopener noreferrer nofollow ugc" target="_blank"`);
    expect(html).toContain("@NFL");
    expect(html).not.toMatch(/<script|platform\.twitter|widgets\.js|<iframe|<img/);
    expect(mdDoc(`https://twitter.com/NFL/status/7`)).toContain('href="https://x.com/NFL/status/7"');
  });

  test("a link in a post: any https site, marked as the writer's; everything else stays text; sentences keep their rule", async ({ isMobile }) => {
    test.skip(isMobile, "pure functions: once");
    const { mdDoc, md, anyHttps } = await import("../../src/lib/md");
    const out = mdDoc("[a](https://example.org/read?x=1&y=2) [b](https://sub.example.co.uk) [ours](/players) [espn](https://www.espn.com/nfl)");
    expect(out).toContain('<a href="https://example.org/read?x=1&amp;y=2" rel="noopener noreferrer nofollow ugc" target="_blank" class="ll-link">a</a>');
    expect(out).toContain('<a href="https://sub.example.co.uk" rel="noopener noreferrer nofollow ugc" target="_blank" class="ll-link">b</a>');
    expect(out).toContain('<a href="https://www.espn.com/nfl" rel="noopener noreferrer nofollow ugc" target="_blank" class="ll-link">espn</a>');
    expect(out).toContain('<a href="/players" class="ll-link">ours</a>');
    for (const bad of ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<script>alert(1)</script>", "http://example.org", "//evil.example", "https://user:pw@example.org/", "https://example.org:8443/", "https://localhost/", "https:\\\\evil.example", "https://evil.example\\@good.example/", "vbscript:x", "ftp://example.org"]) {
      expect(anyHttps(bad), bad).toBe(false);
      const h = mdDoc(`[label](${bad})`);
      expect(h, bad).not.toContain("<a ");
    }
    // a quote in the target cannot leave the attribute
    const q = mdDoc('[x](https://example.org/a"onmouseover="alert(1))');
    expect(q).not.toMatch(/"onmouseover=/);
    // md() (provider text in sentences) keeps IM-3's nine hosts
    expect(md("[x](https://example.org/)")).toBe("x");
    expect(md("[x](https://www.espn.com/)")).toContain('rel="noopener"');
  });
});

// ============================================================================ part 2: the real API
let server: ChildProcess | null = null;
let who: { uid: string; cookie: string } | null = null;
let skipWhy: string | null = null;

function py(code: string): { ok: boolean; out: string } {
  const r = spawnSync("uv", ["run", "--quiet", "python", "-c", code], {
    cwd: API_DIR,
    env: { ...process.env, PYTHONPATH: ".", OMP_NUM_THREADS: "1", LEAGUE_LAB_ACCOUNTS: "on", LEAGUE_LAB_API_SECRET: SECRET, IU6_EMAIL: EMAIL },
    encoding: "utf8",
    timeout: 120_000,
  });
  return { ok: r.status === 0, out: `${r.stdout ?? ""}${r.stderr ?? ""}` };
}
const MAKE_EDITOR = `
import json, os, re
from league_lab_api import accounts, db
email = os.environ["IU6_EMAIL"]
accounts.request_link(email, "203.0.113.31")
msg = [m for m in accounts.STUB.sent if m["to"] == email][-1]
token = re.search(r"#signin=([A-Za-z0-9_-]+)", msg["text"]).group(1)
sid, _ = accounts.verify(token, "203.0.113.31", "Playwright")
uid = db.run_rw(lambda c: c.execute("select user_id from accounts.sessions where id = %s", (sid,)).fetchone()[0])
print("IU6 " + json.dumps({"uid": str(uid), "cookie": accounts.cookie_value(sid)}))
`;
const CLEANUP = `
import os
from league_lab_api import db
email = os.environ["IU6_EMAIL"]
def tx(c):
    c.execute("delete from blog.posts where account_id in (select id from accounts.users where email = %s)", (email,))
    c.execute("delete from blog.images where account_id in (select id from accounts.users where email = %s)", (email,))
    c.execute("delete from accounts.users where email = %s", (email,))
    c.execute("delete from accounts.login_links where user_email = %s", (email,))
db.run_rw(tx)
print("IU6 cleaned")
`;
async function up(): Promise<boolean> {
  try {
    return (await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(3000) })).ok;
  } catch {
    return false;
  }
}

test.describe("the blog with a cover and embeds, on the real API", () => {
  test.describe.configure({ mode: "serial" });
  test.beforeAll(async () => {
    test.setTimeout(300_000);
    mkdirSync(SHOTS, { recursive: true });
    if (await up()) {
      skipWhy = `something already answers on ${API}: this spec starts its own API (with the editor's id)`;
      return;
    }
    const made = py(MAKE_EDITOR);
    const line = made.out.split("\n").find((l) => l.startsWith("IU6 "));
    if (!made.ok || !line) {
      skipWhy = `could not make the editor account: ${made.out.slice(-300)}`;
      return;
    }
    who = JSON.parse(line.slice(4));
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      LEAGUE_LAB_ACCOUNTS: "on",
      LEAGUE_LAB_API_SECRET: SECRET,
      LEAGUE_LAB_EDITORS: who!.uid,
      LEAGUE_LAB_NOW: "2026-10-03T16:00:00Z",
      LEAGUE_LAB_SLEEPER_FIXTURES: join(API_DIR, "tests", "fixtures", "sleeper"),
      LEAGUE_LAB_MFL_FIXTURES: join(API_DIR, "tests", "fixtures", "mfl"),
      LEAGUE_LAB_MFL_YEAR: "2026",
      LEAGUE_LAB_PLAYER_IDS_CSV: join(API_DIR, "tests", "fixtures", "ff", "db_playerids.csv"),
      LEAGUE_LAB_GATE: "open",
      LEAGUE_LAB_AVAILABILITY: "off",
      LEAGUE_LAB_USAGE: "off",
      LEAGUE_LAB_NEWS: "off",
      OMP_NUM_THREADS: "1",
      PYTHONPATH: ".",
    };
    delete env.LEAGUE_LAB_APP_PASSWORD;
    server = spawn("uv", ["run", "uvicorn", "league_lab_api.main:app", "--port", String(PORT)], { cwd: API_DIR, env, stdio: "ignore" });
    for (let i = 0; i < 90 && !(await up()); i++) await new Promise((r) => setTimeout(r, 3000));
    if (!(await up())) skipWhy = `the API did not start on ${API}`;
  });
  test.afterAll(() => {
    server?.kill();
    server = null;
    if (who) py(CLEANUP);
  });
  test.beforeEach(async ({ page, isMobile }) => {
    test.skip(skipWhy !== null, skipWhy ?? "");
    if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
  });

  test("an editor writes a post with a cover, a resized picture, a video, a post on X and a link; readers and crawlers see it", async ({ page, context, isMobile }) => {
    test.setTimeout(240_000);
    const w = isMobile ? 375 : 1300;
    // every outside host is this test's: YouTube's player answered by a stub page, the rest refused — all recorded
    const outside: string[] = [];
    await context.route(/^https?:\/\/(?!localhost[:/])/, (route: Route) => {
      const url = route.request().url();
      outside.push(url);
      if (url.startsWith(`https://www.youtube-nocookie.com/embed/${YT}`))
        return route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>stub player</title><p>The video would play here.</p>" });
      return route.abort();
    });
    await context.addCookies([{ name: "ll_session", value: who!.cookie, domain: "localhost", path: "/api", httpOnly: true, sameSite: "Lax" }]);

    // ---- the editor
    const title = `Covers and videos ${randomBytes(3).toString("hex")}`;
    const slug = title.toLowerCase().replace(/ /g, "-");
    await page.goto(`${API}/blog/new`);
    await page.getByTestId("editor-title").fill(title);
    await page.getByTestId("editor-summary").fill("A post with a cover, a video and a post on X.");
    await page
      .getByTestId("editor-body")
      .fill(["Read [the long version](https://example.org/read) first.", "", `https://www.youtube.com/watch?v=${YT}`, "", X_URL, "", "The chart:", "", ""].join("\n"));
    await expect(page).toHaveURL(/\/blog\/edit\//, { timeout: 20_000 });
    await expect(page.getByTestId("editor-embeds")).toContainText("A YouTube or X link alone on its line");
    await page.getByTestId("tool-picture").click();
    const photo = bigPng(2400, 1600);
    await page.getByTestId("picture-file").setInputFiles({ name: "week-6-chart.png", mimeType: "image/png", buffer: photo });
    await expect(page.getByTestId("editor-body")).toHaveValue(/!\[week-6-chart\]\(\/blog\/img\/db\/[0-9a-f-]{36}\)/, { timeout: 60_000 });
    const pic = /\/blog\/img\/db\/([0-9a-f-]{36})/.exec(await page.getByTestId("editor-body").inputValue())![1];
    const stored = await (await page.request.get(`${API}/blog/img/db/${pic}`)).body();
    expect(stored.length).toBeLessThanOrEqual(300 * 1024);
    await page.getByTestId("tool-picture").click();
    await page.getByTestId("picture-make-cover").first().click();
    await expect(page.getByTestId("editor-cover")).toBeVisible();
    await expect(page.getByTestId("picture-is-cover")).toHaveCount(1);
    if (isMobile) await page.getByTestId("switch-preview").click();
    await expect(page.getByTestId("preview-cover")).toBeVisible();
    await expect(page.getByTestId("editor-preview").locator("[data-yt-play]")).toHaveCount(1);
    await page.screenshot({ path: join(SHOTS, `iu6-editor-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true });
    if (isMobile) await page.getByTestId("switch-write").click();
    await page.getByTestId("editor-publish").click();
    await expect(page.getByTestId("editor-status")).toHaveText("Published", { timeout: 30_000 });
    const saved = await (await page.request.get(`${API}/api/blog/mine`)).json();
    const mine = (saved.posts as { slug: string; id: string }[]).find((p) => p.slug === slug)!;
    const full = await (await page.request.get(`${API}/api/blog/posts/${mine.id}`)).json();
    expect(full.cover).toBe(pic);

    // ---- the post, as a reader: banner, the two embeds, nothing asked of YouTube or X before the tap
    outside.length = 0;
    await page.goto(`${API}/blog/${slug}`);
    await expect(page.getByTestId("post-title")).toHaveText(title, { timeout: 30_000 });
    const banner = page.getByTestId("post-cover");
    await expect(banner).toHaveAttribute("src", `/blog/img/db/${pic}`);
    await expect.poll(() => banner.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBe(1600);
    const body = page.getByTestId("post-body");
    const play = body.locator(`button[data-yt-play="${YT}"]`);
    await expect(play).toBeVisible();
    await expect(body.locator("iframe")).toHaveCount(0);
    const card = body.locator("a.ll-embed-card");
    await expect(card).toHaveAttribute("href", X_URL);
    await expect(card).toHaveAttribute("rel", "noopener noreferrer nofollow ugc");
    await expect(card).toContainText("@NFL");
    await expect(body.getByRole("link", { name: "the long version" })).toHaveAttribute("rel", "noopener noreferrer nofollow ugc");
    expect(await page.locator('script[src]:not([src^="/"])').count(), "no script from another origin").toBe(0);
    await page.waitForTimeout(1500);
    expect(outside, "nothing left for YouTube or X before the tap").toEqual([]);
    const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
    expect(sw, "no sideways scroll").toBeLessThanOrEqual(iw);
    await page.screenshot({ path: join(SHOTS, `iu6-post-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true });
    // the tap: then, and only then, the player — youtube-nocookie, sandboxed, lazy, its referrer policy, a title
    await play.click();
    const frame = body.locator("iframe");
    await expect(frame).toHaveCount(1);
    await expect(frame).toHaveAttribute("src", `https://www.youtube-nocookie.com/embed/${YT}?autoplay=1`);
    await expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin allow-presentation allow-popups");
    await expect(frame).toHaveAttribute("loading", "lazy");
    await expect(frame).toHaveAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    await expect(frame).toHaveAttribute("title", "YouTube video");
    await expect.poll(() => outside.length, { timeout: 15_000 }).toBeGreaterThan(0);
    expect(outside.every((u) => u.startsWith(`https://www.youtube-nocookie.com/embed/${YT}`)), outside.join(" ")).toBe(true);
    await expect(page.frameLocator('iframe[title="YouTube video"]').getByText("The video would play here.")).toBeVisible();
    await frame.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(SHOTS, `iu6-post-played-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true });

    // ---- the list and the home: the cover as the thumbnail
    await page.goto(`${API}/blog`);
    const item = page.locator(`[data-testid="blog-item"][data-slug="${slug}"]`);
    const thumb = item.getByTestId("blog-item-cover");
    await expect(thumb).toHaveAttribute("src", `/blog/img/db/${pic}`, { timeout: 30_000 });
    await expect.poll(() => thumb.evaluate((el) => (el as HTMLImageElement).naturalWidth), { timeout: 15_000 }).toBe(1600); // drawn, not a box
    {
      const { sw: s2, iw: i2 } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
      expect(s2).toBeLessThanOrEqual(i2);
    }
    await page.screenshot({ path: join(SHOTS, `iu6-list-${w}.jpg`), type: "jpeg", quality: 70, fullPage: false });
    await page.goto(`${API}/home`);
    const homePost = page.getByTestId("home-blog").locator(`a[href="/blog/${slug}"]`);
    const homeThumb = homePost.getByTestId("home-post-cover");
    await expect(homeThumb).toHaveAttribute("src", `/blog/img/db/${pic}`, { timeout: 60_000 });
    await homeThumb.scrollIntoViewIfNeeded();
    await expect.poll(() => homeThumb.evaluate((el) => (el as HTMLImageElement).naturalWidth), { timeout: 15_000 }).toBe(1600);

    // ---- a crawler (runs no script): the server's HTML carries the cover's absolute https URL, escaped
    const html = await (await fetch(`${API}/blog/${slug}`)).text();
    const meta = (prop: string) => new RegExp(`<meta (?:property|name)="${prop}" content="([^"]*)"`).exec(html)?.[1] ?? null;
    expect(meta("og:image")).toBe(`https://isuckatfantasy.io/blog/img/db/${pic}`);
    expect(meta("twitter:image")).toBe(`https://isuckatfantasy.io/blog/img/db/${pic}`);
    expect(meta("twitter:card")).toBe("summary_large_image");
    expect(meta("og:title")).toBe(`${title} · isuckatfantasy`);
    expect(meta("og:description")).toBe("A post with a cover, a video and a post on X.");
    // the CSP frames exactly one host
    const csp = (await fetch(`${API}/blog/${slug}`)).headers.get("content-security-policy") ?? "";
    expect(csp.split("; ").filter((d) => d.startsWith("frame-src"))).toEqual(["frame-src https://www.youtube-nocookie.com"]);
  });

  test("a file over 300 KB that is not a picture (HTML named .png) is refused in the browser and never sent", async ({ page, isMobile }) => {
    test.skip(isMobile, "the same code path at 375");
    test.setTimeout(120_000);
    await page.context().addCookies([{ name: "ll_session", value: who!.cookie, domain: "localhost", path: "/api", httpOnly: true, sameSite: "Lax" }]);
    const posts: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/api/blog/images")) posts.push(r.url());
    });
    await page.goto(`${API}/blog/new`);
    await page.getByTestId("editor-title").fill(`Not a picture ${randomBytes(3).toString("hex")}`);
    await expect(page).toHaveURL(/\/blog\/edit\//, { timeout: 20_000 });
    await page.getByTestId("tool-picture").click();
    const html = Buffer.from("<!doctype html><script>window.__iu6 = 1</script>" + "<p>x</p>".repeat(50_000)); // ~400 KB
    expect(html.length).toBeGreaterThan(300 * 1024);
    await page.getByTestId("picture-file").setInputFiles({ name: "evil.png", mimeType: "image/png", buffer: html });
    await expect(page.getByTestId("picture-problem")).toHaveText("A picture is a PNG, JPEG or WebP file.", { timeout: 30_000 });
    expect(posts, "nothing sent").toEqual([]);
    expect(await page.evaluate(() => (window as unknown as { __iu6?: number }).__iu6)).toBeUndefined();
  });
});

// a phone-sized PNG (several MB, nothing to compress) — io3's resize test's maker
function bigPng(w: number, h: number): Buffer {
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (b: Buffer) => {
    let c = 0xffffffff;
    for (const x of b) c = crcTable[(c ^ x) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type: string, data: Buffer) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type, "ascii"), data]);
    const c = Buffer.alloc(4);
    c.writeUInt32BE(crc(td));
    return Buffer.concat([len, td, c]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr.set([8, 2, 0, 0, 0], 8);
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) {
    const o = y * (w * 3 + 1);
    for (let x = 0; x < w; x++) {
      const i = o + 1 + x * 3;
      raw[i] = (x * 255) / w;
      raw[i + 1] = (y * 255) / h;
      raw[i + 2] = ((x ^ y) & 0x3f) + 96;
    }
  }
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(raw, { level: 0 })), chunk("IEND", Buffer.alloc(0))]);
}

