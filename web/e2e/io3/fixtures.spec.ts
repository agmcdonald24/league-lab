// Wave I-O (IO-3): the blog editor — against the REAL API (the fixture API on http://localhost:8863 with accounts on
// and a throwaway secret; docs/BLOG.md § "The editor"). Before the server starts, an editor account is made through the
// app's own code path (accounts.request_link → the stub mailer → accounts.verify, in a Python one-off with the same
// throwaway secret), and the server starts with LEAGUE_LAB_EDITORS naming it; the browser carries its session cookie.
//   1. the editor: /blog shows "Write a post" → write (title, summary, tags, author, a body with every hostile shape)
//      → the draft saves itself → the preview (side by side at 1300, the Write / Preview switch at 375) renders the
//      body inert → Publish → the public post and the list → Unpublish → the post is gone → Delete.
//   2. a visitor (no cookie): no Write anywhere; /blog/new says "Sign in to write".
//   3. the Account screen shows "Your account id" (the id LEAGUE_LAB_EDITORS takes).
// Phone at 375 and desktop at 1300; screenshots in docs/handbacks/io3/. The account and its posts are deleted after.
// Needs the `blog` schema (scripts/hosted_blog.sql) and the accounts tables on the worktree's database (.env).
import { expect, test, type Page } from "@playwright/test";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const PORT = Number(process.env.IO3_API_PORT ?? 8863);
const API = `http://localhost:${PORT}`;
const ROOT = join(import.meta.dirname, "..", "..", "..");
const API_DIR = join(ROOT, "api");
const SHOTS = join(ROOT, "docs", "handbacks", "io3");
const SECRET = randomBytes(24).toString("hex"); // throwaway, this run only — never written anywhere
const EMAIL = `editor-${randomBytes(4).toString("hex")}@io3.test`;

let server: ChildProcess | null = null;
let who: { uid: string; cookie: string } | null = null;
let skipWhy: string | null = null;

function py(code: string): { ok: boolean; out: string } {
  const r = spawnSync("uv", ["run", "--quiet", "python", "-c", code], {
    cwd: API_DIR,
    env: { ...process.env, PYTHONPATH: ".", OMP_NUM_THREADS: "1", LEAGUE_LAB_ACCOUNTS: "on", LEAGUE_LAB_API_SECRET: SECRET, IO3_EMAIL: EMAIL },
    encoding: "utf8",
    timeout: 120_000,
  });
  return { ok: r.status === 0, out: `${r.stdout ?? ""}${r.stderr ?? ""}` };
}

const MAKE_EDITOR = `
import json, os, re
from league_lab_api import accounts, db
email = os.environ["IO3_EMAIL"]
accounts.request_link(email, "203.0.113.30")
msg = [m for m in accounts.STUB.sent if m["to"] == email][-1]
token = re.search(r"#signin=([A-Za-z0-9_-]+)", msg["text"]).group(1)
sid, _ = accounts.verify(token, "203.0.113.30", "Playwright")
uid = db.run_rw(lambda c: c.execute("select user_id from accounts.sessions where id = %s", (sid,)).fetchone()[0])
print("IO3 " + json.dumps({"uid": str(uid), "cookie": accounts.cookie_value(sid)}))
`;
const CLEANUP = `
import os
from league_lab_api import accounts, db
email = os.environ["IO3_EMAIL"]
def tx(c):
    c.execute("delete from blog.posts where account_id in (select id from accounts.users where email = %s)", (email,))
    c.execute("delete from blog.images where account_id in (select id from accounts.users where email = %s)", (email,))
    c.execute("delete from accounts.users where email = %s", (email,))
    c.execute("delete from accounts.login_links where user_email = %s", (email,))
db.run_rw(tx)
print("IO3 cleaned")
`;

async function up(): Promise<boolean> {
  try {
    const r = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(3000) });
    return r.ok;
  } catch {
    return false;
  }
}

test.beforeAll(async () => {
  test.setTimeout(240_000);
  mkdirSync(SHOTS, { recursive: true });
  if (await up()) {
    skipWhy = `something already answers on ${API}: this spec starts its own API (with the editor's id)`;
    return;
  }
  const made = py(MAKE_EDITOR);
  const line = made.out.split("\n").find((l) => l.startsWith("IO3 "));
  if (!made.ok || !line) {
    skipWhy = `could not make the editor account (accounts tables on the .env database?): ${made.out.slice(-300)}`;
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
  for (let i = 0; i < 70 && !(await up()); i++) await new Promise((r) => setTimeout(r, 3000));
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

async function asEditor(page: Page) {
  await page.context().addCookies([{ name: "ll_session", value: who!.cookie, domain: "localhost", path: "/api", httpOnly: true, sameSite: "Lax" }]);
}
async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}
/** Nothing the post carries ran or became markup: no script, no event attribute, no javascript: link, no outside picture. */
async function inert(page: Page, scope: string) {
  const bad = await page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (!root) return ["no root"];
    const out: string[] = [];
    if ((window as unknown as { __io3?: number }).__io3) out.push("a payload ran");
    if (root.querySelector("script, iframe, object, embed, style, svg")) out.push("an element the post must not make");
    for (const el of Array.from(root.querySelectorAll("*")))
      for (const a of Array.from(el.attributes)) if (/^on/i.test(a.name)) out.push(`${el.tagName} ${a.name}`);
    for (const a of Array.from(root.querySelectorAll("a"))) {
      const h = a.getAttribute("href") ?? "";
      if (!(h.startsWith("/") && !h.startsWith("//")) && !h.startsWith("https://")) out.push(`link ${h}`);
      if (h.startsWith("https://") && !/^https:\/\/([a-z0-9-]+\.)*(isuckatfantasy\.io|espn\.com|sleeper\.com|sleeper\.app|myfantasyleague\.com|yahoo\.com|nfl\.com|draftkings\.com|fanduel\.com)\//.test(h))
        out.push(`outside link ${h}`);
    }
    for (const i of Array.from(root.querySelectorAll("img"))) if (!(i.getAttribute("src") ?? "").startsWith("/blog/img/")) out.push(`img ${i.getAttribute("src")}`);
    return out;
  }, scope);
  expect(bad, `inert ${scope}`).toEqual([]);
}

const HOSTILE = [
  "## What the numbers say",
  "",
  "Start [Puka Nacua](/player/00-0039075) over most. **Bold words** and *italic words*.",
  "",
  "<script>window.__io3 = 1</script> <img src=x onerror=\"window.__io3 = 2\">",
  "[click](javascript:window.__io3=3) [evil](https://evil.example/x) [proto](//evil.example) [attr](/a\" onmouseover=\"window.__io3=4)",
  "![pic](https://evil.example/x.png) ![pic2](/blog/img/x.png\" onerror=\"window.__io3=5)",
  "",
  "| Player | Note |",
  "|---|--:|",
  "| <b onclick=window.__io3=6>x</b> | `</code><script>window.__io3=7</script>` |",
  "",
  "```",
  "</pre><script>window.__io3=8</script>",
  "```",
  "",
  "> A quote &lt;script&gt; &#60;b&#62;",
  "",
  "- one",
  "- two",
].join("\n");

test("the editor: write, preview, publish, the public post, unpublish, delete", async ({ page, isMobile }, info) => {
  test.setTimeout(150_000);
  const w = isMobile ? 375 : 1300;
  const title = `Editor check ${info.project.name} ${randomBytes(3).toString("hex")} "quoted" <b>not bold</b>`;
  await asEditor(page);

  await page.goto(`${API}/blog`);
  await expect(page.getByTestId("blog-write")).toBeVisible();
  await page.getByTestId("blog-write").click();
  await expect(page).toHaveURL(/\/blog\/new$/);
  await expect(page.getByTestId("editor-starters")).toBeVisible();
  await expect(page.getByTestId("editor-pictures")).toContainText("300 KB at most");

  await page.getByTestId("editor-title").fill(title);
  await page.getByTestId("editor-summary").fill('A summary with "quotes" and <tags>.');
  await page.getByTestId("editor-tags").fill("Matchups, week 5");
  await page.getByTestId("editor-author").fill("Andrew");
  await page.getByTestId("editor-body").fill(HOSTILE);
  // the draft saves itself and the address becomes the post's
  await expect(page).toHaveURL(/\/blog\/edit\/[0-9a-f-]{36}$/, { timeout: 15_000 });
  await expect(page.getByTestId("editor-saved")).toContainText("Saved", { timeout: 15_000 });
  await expect(page.getByTestId("editor-status")).toHaveText("Draft");
  const slug = await page.getByTestId("editor-slug").inputValue();
  expect(slug).toMatch(/^editor-check-/);

  // the preview: side by side at 1300; the switch at 375
  if (isMobile) {
    await expect(page.getByTestId("editor-preview")).toBeHidden();
    await page.getByTestId("switch-preview").click();
    await expect(page.getByTestId("editor-body")).toBeHidden();
  }
  const pv = page.getByTestId("editor-preview");
  await expect(pv).toBeVisible();
  await expect(pv.locator("h2", { hasText: "What the numbers say" })).toBeVisible();
  await expect(pv.locator("table")).toHaveCount(1);
  await expect(pv.locator('a[href^="/player/00-0039075"]')).toHaveText("Puka Nacua");
  await expect(pv).toContainText("<script>window.__io3 = 1</script>"); // raw HTML is shown as text
  await inert(page, '[data-testid="editor-preview"]');
  await noSidewaysScroll(page);
  const box = await pv.boundingBox();
  expect(box!.x + box!.width, "the preview fits the screen").toBeLessThanOrEqual(w);
  await page.screenshot({ path: join(SHOTS, `io3-editor-${w}.png`), fullPage: true });
  if (isMobile) await page.getByTestId("switch-write").click();

  // the toolbar: bold around a selection
  await page.getByTestId("editor-body").press("End");
  await page.getByTestId("tool-bold").click();
  await expect(page.getByTestId("editor-body")).toHaveValue(/\*\*bold words\*\*$/);

  // publish → the link with Copy → the public post
  await page.getByTestId("editor-publish").click();
  await expect(page.getByTestId("editor-status")).toHaveText("Published");
  await expect(page.getByTestId("editor-live-link")).toHaveText(`/blog/${slug}`);
  await page.getByTestId("editor-live-link").click();
  await expect(page.getByTestId("post-title")).toHaveText(title);
  await expect(page.getByTestId("post-meta")).toContainText("By Andrew");
  await expect(page.getByTestId("post-edit")).toBeVisible();
  await inert(page, '[data-testid="post-body"]');
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `io3-post-${w}.png`), fullPage: true });
  // the link preview in the shell: escaped
  const shell = await (await fetch(`${API}/blog/${slug}`)).text();
  expect(shell).toContain("&lt;b&gt;not bold&lt;/b&gt;");
  expect(shell.split("</head>")[0]).not.toContain("<b>not bold");

  await page.goto(`${API}/blog`);
  await expect(page.locator(`[data-testid="blog-item"][data-slug="${slug}"]`)).toBeVisible();
  await expect(page.getByTestId("blog-mine")).toBeVisible();
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `io3-list-${w}.png`), fullPage: true });

  // unpublish → gone from the public blog
  await page.locator('[data-testid="blog-mine-item"][data-status="published"] a', { hasText: "Editor check" }).first().click();
  await expect(page.getByTestId("editor-status")).toHaveText("Published");
  await page.getByTestId("editor-unpublish").click();
  await expect(page.getByTestId("editor-status")).toHaveText("Draft");
  await page.goto(`${API}/blog/${slug}`);
  await expect(page.getByTestId("post-missing")).toBeVisible();

  // delete (a second tap confirms)
  await page.goBack();
  await expect(page.getByTestId("editor-status")).toHaveText("Draft");
  await page.getByTestId("editor-delete").click();
  await page.getByTestId("editor-delete-confirm").click();
  await expect(page.getByTestId("editor-status")).toHaveText("Deleted");
  await expect(page.getByTestId("editor-restore")).toBeVisible();
});

test("a starter fills a draft from this week's numbers and never publishes", async ({ page, isMobile }, info) => {
  test.skip(isMobile, "one viewport is enough for the starter's words");
  test.setTimeout(90_000);
  await asEditor(page);
  await page.goto(`${API}/blog/new`);
  await page.getByTestId("starter-matchups").click();
  await expect(page.getByTestId("editor-body")).toHaveValue(/As of .*week 4/, { timeout: 30_000 });
  await expect(page.getByTestId("editor-body")).toHaveValue(/Your take: …/);
  await expect(page.getByTestId("editor-title")).toHaveValue(/Matchups to target and avoid/);
  await expect(page.getByTestId("editor-saved")).toContainText("Saved", { timeout: 15_000 });
  await expect(page.getByTestId("editor-status")).toHaveText("Draft");
  await inert(page, '[data-testid="editor-preview"]');
  await page.screenshot({ path: join(SHOTS, `io3-starter-${info.project.name === "desktop" ? 1300 : 375}.png`), fullPage: true });
});

test("a visitor sees no Write and the editor's address says to sign in; the account shows its id", async ({ page, browser, isMobile }) => {
  await page.goto(`${API}/blog`);
  await expect(page.getByTestId("blog")).toBeVisible();
  await expect(page.getByTestId("blog-write")).toHaveCount(0);
  await page.goto(`${API}/blog/new`);
  await expect(page.getByTestId("editor-closed")).toContainText("Sign in to write");
  // the editor's own device: the Account screen shows the id LEAGUE_LAB_EDITORS takes
  const ctx = await browser.newContext({ viewport: page.viewportSize()!, isMobile, hasTouch: isMobile, serviceWorkers: "block" });
  const p = await ctx.newPage();
  await asEditor(p);
  await p.goto(`${API}/account`);
  await expect(p.getByTestId("account-id-value")).toHaveText(who!.uid);
  await noSidewaysScroll(p);
  await p.screenshot({ path: join(SHOTS, `io3-account-${isMobile ? 375 : 1300}.png`), fullPage: true });
  await ctx.close();
});

test("two tabs: the stale save is a conflict in words, never an overwrite; the newer version is one tap", async ({ page, isMobile }) => {
  test.skip(isMobile, "the conflict's words are the same at 375 (the phone run checks the layout above)");
  test.setTimeout(90_000);
  await asEditor(page);
  await page.goto(`${API}/blog/new`);
  await page.getByTestId("editor-title").fill(`Two tabs ${randomBytes(3).toString("hex")}`);
  await page.getByTestId("editor-body").fill("First words.");
  await expect(page).toHaveURL(/\/blog\/edit\//, { timeout: 15_000 });
  await expect(page.getByTestId("editor-saved")).toContainText("Saved", { timeout: 15_000 });
  const b = await page.context().newPage();
  await b.goto(page.url());
  await expect(b.getByTestId("editor-body")).toHaveValue("First words.");
  await page.getByTestId("editor-body").fill("First words. Tab A.");
  await expect(page.getByTestId("editor-saved")).toContainText("Saved", { timeout: 15_000 });
  await b.getByTestId("editor-body").fill("First words. Tab B.");
  await expect(b.getByTestId("editor-conflict")).toBeVisible({ timeout: 15_000 });
  await expect(b.getByTestId("editor-conflict")).toContainText("Nothing was overwritten.");
  await b.screenshot({ path: join(SHOTS, "io3-conflict-1300.png") });
  await b.getByTestId("conflict-newer").click();
  await expect(b.getByTestId("editor-body")).toHaveValue("First words. Tab A.");
  await b.getByTestId("editor-body").fill("First words. Tab A. Then B.");
  await expect(b.getByTestId("editor-saved")).toContainText("Saved", { timeout: 15_000 });
  // an earlier version comes back with one tap (and saves as a new one)
  await b.getByTestId("editor-versions").click();
  await expect(b.getByTestId("editor-version-list")).toBeVisible();
  await b.getByTestId("editor-version-load").last().click();
  await expect(b.getByTestId("editor-body")).toHaveValue("First words.");
  await expect(b.getByTestId("editor-version-words")).toContainText("nothing is lost");
  await expect(b.getByTestId("editor-saved")).toContainText("Saved", { timeout: 15_000 });
  await b.close();
});

test("a dropped connection loses nothing: the device keeps the text and offers it back", async ({ page, isMobile }) => {
  test.skip(isMobile, "the same code path at 375");
  test.setTimeout(90_000);
  await asEditor(page);
  await page.goto(`${API}/blog/new`);
  await page.getByTestId("editor-title").fill(`Offline ${randomBytes(3).toString("hex")}`);
  await page.getByTestId("editor-body").fill("Saved words.");
  await expect(page).toHaveURL(/\/blog\/edit\//, { timeout: 15_000 });
  await expect(page.getByTestId("editor-saved")).toContainText("Saved", { timeout: 15_000 });
  await page.route("**/api/blog/posts/**", (route) => (route.request().method() === "PUT" ? route.abort("internetdisconnected") : route.continue()));
  await page.getByTestId("editor-body").fill("Saved words. Words typed while offline.");
  await expect(page.getByTestId("editor-problem")).toContainText("Your text is kept on this device", { timeout: 15_000 });
  await page.unroute("**/api/blog/posts/**");
  await page.reload();
  await expect(page.getByTestId("editor-local")).toBeVisible();
  await expect(page.getByTestId("editor-body")).toHaveValue("Saved words.");
  await page.getByTestId("editor-local-restore").click();
  await expect(page.getByTestId("editor-body")).toHaveValue("Saved words. Words typed while offline.");
  await expect(page.getByTestId("editor-saved")).toContainText("Saved", { timeout: 15_000 });
  await page.reload();
  await expect(page.getByTestId("editor-body")).toHaveValue("Saved words. Words typed while offline.");
  await expect(page.getByTestId("editor-local")).toHaveCount(0);
});

test("typing in a 20 KB post stays smooth (the preview is debounced)", async ({ page, isMobile }) => {
  test.skip(isMobile, "measured once, on the desktop");
  test.setTimeout(90_000);
  await asEditor(page);
  await page.goto(`${API}/blog/new`);
  await page.getByTestId("editor-title").fill(`Long ${randomBytes(3).toString("hex")}`);
  const para = "Start **him** over [Puka Nacua](/player/00-0039075): the numbers say so, with a range.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n";
  await page.getByTestId("editor-body").fill(para.repeat(Math.ceil(20_480 / para.length)));
  await expect(page.getByTestId("editor-saved")).toContainText("Saved", { timeout: 15_000 });
  await page.getByTestId("editor-body").press("End");
  const t0 = Date.now();
  await page.getByTestId("editor-body").pressSequentially("More words typed at the end of a long post.", { delay: 0 });
  const perKey = (Date.now() - t0) / 43;
  console.log(`IO3 typing: ${perKey.toFixed(1)} ms per key in a ${Math.round((await page.getByTestId("editor-body").inputValue()).length / 1024)} KB post`);
  expect(perKey).toBeLessThan(60);
  await expect(page.getByTestId("editor-preview")).toContainText("More words typed at the end of a long post.");
});

const PNG_1PX = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

test("a picture: uploaded from the editor, checked by its first bytes, shown in the preview; an svg named .png is refused", async ({ page, isMobile }) => {
  test.setTimeout(90_000);
  await asEditor(page);
  await page.goto(`${API}/blog/new`);
  await page.getByTestId("editor-title").fill(`Picture ${randomBytes(3).toString("hex")}`);
  await page.getByTestId("editor-body").fill("A chart below.");
  await expect(page).toHaveURL(/\/blog\/edit\//, { timeout: 15_000 });
  await page.getByTestId("tool-picture").click();
  await page.getByTestId("picture-file").setInputFiles({ name: "evil.png", mimeType: "image/png", buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" onload="window.__io3=9"></svg>' + " ".repeat(64)) });
  await expect(page.getByTestId("picture-problem")).toHaveText("A picture is a PNG, JPEG or WebP file.");
  await page.getByTestId("picture-file").setInputFiles({ name: "week-5-chart.png", mimeType: "image/png", buffer: PNG_1PX });
  await expect(page.getByTestId("editor-body")).toHaveValue(/!\[week-5-chart\]\(\/blog\/img\/db\/[0-9a-f-]{36}\)/);
  if (isMobile) await page.getByTestId("switch-preview").click();
  const img = page.getByTestId("editor-preview").locator('img[src^="/blog/img/db/"]');
  await expect(img).toHaveCount(1);
  await expect.poll(() => img.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBe(1);
  await inert(page, '[data-testid="editor-preview"]');
  await page.screenshot({ path: join(SHOTS, `io3-picture-${isMobile ? 375 : 1300}.png`), fullPage: true });
});
