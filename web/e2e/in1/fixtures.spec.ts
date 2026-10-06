// Wave I-N (IN-1): the home page, the setup screen on a desktop, the blog. Phone at 375 × 667 and desktop at 1300 × 800
// (the setup screen at 1300 × 700). Every `ref:` and blog answer comes from web/fixtures/in1/api_in1.json, recorded
// from the fixture API (the PO's recipe, `ref:half`); the rest from serveFixtures. IN-3's matchup board does not exist
// on this branch: one test answers it with a made-up row set to show the module, the others leave it 404 (hidden).
// Screenshots go to docs/handbacks/in1/ (the hand-back's evidence).
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const RECORDED = JSON.parse(readFileSync(join(import.meta.dirname, "..", "..", "fixtures", "in1", "api_in1.json"), "utf8")) as Record<
  string,
  { status: number; body: unknown }
>;
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", "..", "..", "docs", "handbacks", "in1");
mkdirSync(SHOTS, { recursive: true });
const SLUG = "how-to-read-this-sites-numbers";
const PUKA = "00-0039075";

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}${q.length ? `?${new URLSearchParams(q).toString()}` : ""}`;
};

// a second post with every piece of markdown the blog knows, raw HTML that must stay text, a wide table, a player link
const DEMO = {
  slug: "every-piece-of-markdown",
  title: "Every piece of markdown",
  date: "2026-10-05",
  summary: "A post that uses every piece the blog knows.",
  author: "isuckatfantasy",
  tags: ["test"],
  minutes: 1,
  image: null,
  markdown: [
    "Start [Puka Nacua](/player/00-0039075) this week. <script>window.__pwned = 1</script> <img src=x onerror=alert(1)>",
    "",
    "## A heading",
    "",
    "1. one",
    "2. two",
    "",
    "> A quote with **bold**.",
    "",
    "| Player | Targets per game | Share of team passes | Receiving yards per game | Touchdowns | Air yards per game |",
    "|---|--:|--:|--:|--:|--:|",
    "| Puka Nacua | 10.1 | 31% | 91.4 | 0.57 | 101.2 |",
    "| Jaxon Smith-Njigba | 9.2 | 28% | 88.0 | 0.50 | 110.5 |",
    "",
    "![A chart](/blog/img/chart-1.png) ![Elsewhere](https://evil.example/x.png)",
    "",
    "A live table:",
    "",
    "```players",
    "00-0039075",
    "00-0038543",
    "cols: targets, target_share, receiving_yards",
    "```",
    "",
    "`code <b>` and a rule:",
    "",
    "---",
    "",
    "The end.",
  ].join("\n"),
};

// the board: IN-3's real answers recorded from the merged tree (default), or missing (404: the fallback path)
async function api(context: BrowserContext, opts: { board?: "recorded" | "missing" } = {}): Promise<string[]> {
  const calls: string[] = [];
  await serveFixtures(context);
  await context.route(/\/api\/(blog|ros|about|record|matchups\/board|player)/, async (route) => {
    const u = new URL(route.request().url());
    calls.push(u.pathname + u.search);
    if (u.pathname === "/api/matchups/board" && opts.board === "missing")
      return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "no endpoint" }) });
    if (u.pathname === "/api/blog" && u.searchParams.get("limit") === "50") {
      const list = RECORDED["/api/blog?limit=50"].body as { posts: unknown[] };
      const meta = Object.fromEntries(Object.entries(DEMO).filter(([k]) => k !== "markdown"));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ posts: [...list.posts, meta] }) });
    }
    if (u.pathname === `/api/blog/${DEMO.slug}`) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DEMO) });
    const hit = RECORDED[keyOf(u)];
    if (hit) return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(hit.body) });
    if (u.pathname.startsWith("/api/blog/")) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "No post at that address." }) });
    if (/league=ref/.test(u.search) || u.pathname.startsWith("/api/blog")) return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
    return route.fallback();
  });
  await context.route(/\/blog\/img\//, (route) => route.fulfill({ status: 404, body: "" }));
  return calls;
}

async function size(page: Page, isMobile: boolean, desktopHeight = 800) {
  await page.setViewportSize(isMobile ? { width: 375, height: 667 } : { width: 1300, height: desktopHeight });
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "no sideways page scroll").toBeLessThanOrEqual(iw + 1);
}

async function inView(page: Page, testid: string, nth = 0) {
  const box = await page.getByTestId(testid).nth(nth).boundingBox();
  const vh = page.viewportSize()!.height;
  expect(box, testid).not.toBeNull();
  expect(box!.y, `${testid} top inside the viewport`).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height, `${testid} bottom inside the viewport (${vh})`).toBeLessThanOrEqual(vh);
}

test("home: the name, one sentence, two actions and live projections above the fold; modules that fail hide", async ({ context, page, isMobile }, info) => {
  const calls = await api(context);
  await size(page, isMobile);
  await page.goto("/");
  await expect(page.getByTestId("home")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("isuckatfantasy");
  await expect(page.getByTestId("home-sentence")).toContainText("Our own projections for every player");
  await expect(page.getByTestId("home-open")).toHaveAttribute("href", "/leagues");
  await expect(page.getByTestId("home-browse")).toHaveAttribute("href", "/players?league=ref:half");
  await expect(page.getByTestId("home-top-row")).toHaveCount(5);
  // above the fold at 375 × 667 and 1300 × 800: the name, the sentence, both actions, live rows
  for (const id of ["home-sentence", "home-open", "home-browse", "home-top-row"]) await inView(page, id);
  // IN-3's board (its real answer, recorded): this week's projection with this week's range, and the matchups to target
  expect(calls.some((c) => c.startsWith("/api/matchups/board"))).toBe(true);
  await expect(page.getByTestId("home-top-range").first()).toHaveText(/^range \d+\.\d–\d+\.\d$/);
  await expect(page.getByTestId("home-top-name").first()).toHaveText("Chris Olave");
  const targets = page.getByTestId("home-matchup-row");
  await expect(targets).toHaveCount(5);
  for (let i = 0; i < 5; i++) await expect(targets.nth(i)).toContainText("▲ Favorable"); // "to target": favorable only
  await expect(targets.first()).toContainText("vs ATL");
  await expect(targets.nth(1)).toContainText("at PHI");
  await expect(targets.first()).toContainText("Atlanta gives up the 7th-most points to receivers.");
  await expect(targets.first()).not.toContainText("starting corners"); // an unclear corner call: the defense's line only
  await expect(page.getByTestId("home-matchup-proj").first()).toHaveText("16.8 this week");
  await expect(page.getByTestId("home-matchups-note")).toContainText("who plays cornerback is not");
  // the record, straight: four positions, the worse ones marked
  await expect(page.getByTestId("home-grade")).toHaveCount(4);
  await expect(page.locator('[data-testid="home-grade"][data-verdict="worse"]').first()).toBeVisible();
  await expect(page.getByTestId("home-record-lead")).toContainText("quarterbacks are our weak spot");
  await expect(page.getByTestId("home-record-line")).toBeVisible();
  await expect(page.getByTestId("home-post")).toHaveCount(1);
  await expect(page.getByTestId("home-tool")).toHaveCount(4);
  await expect(page.locator('[data-tool="trade"]')).toHaveAttribute("href", "/trade-calc?league=ref%3Ahalf");
  await expect(page.getByTestId("error-card")).toHaveCount(0);
  await expect(page.getByTestId("home").getByText(/no league/i)).toHaveCount(0); // rule 9: the home never says "No league"
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `home-${info.project.name}.png`), fullPage: false, scale: "css" });
  await page.screenshot({ path: join(SHOTS, `home-full-${info.project.name}.png`), fullPage: true, scale: "css" });
  // the position tabs switch the list
  await page.getByTestId("home-top-pos").getByRole("button", { name: "RB" }).click();
  await expect(page.getByTestId("home-top-row").first()).toBeVisible();
  expect(calls.some((c) => c.startsWith("/api/matchups/board?league=ref%3Ahalf&position=RB"))).toBe(true);
  await page.getByTestId("home-top-pos").getByRole("button", { name: "WR" }).click();
  // "/home" is the same page; a name opens the drawer in Half PPR
  await page.goto("/home");
  await expect(page.getByTestId("home")).toBeVisible();
  await page.getByTestId("home-top-name").first().click();
  await expect(page.getByTestId("pane")).toBeVisible();
});

test("home without the matchup board (404): the projections fall back to the season list and its range; the matchups hide", async ({ context, page, isMobile }, info) => {
  const calls = await api(context, { board: "missing" });
  await size(page, isMobile);
  await page.goto("/");
  await expect(page.getByTestId("home-top-row")).toHaveCount(5);
  expect(calls.some((c) => c.startsWith("/api/ros?league=ref%3Ahalf&position=WR"))).toBe(true);
  await expect(page.getByTestId("home-top-range").first()).toContainText(/season \d+ \(\d+–\d+\)/);
  await expect(page.getByTestId("home-top-note")).toContainText("the rest of the season");
  await expect(page.getByTestId("home-matchups")).toHaveCount(0);
  await expect(page.getByTestId("error-card")).toHaveCount(0);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `home-without-board-full-${info.project.name}.png`), fullPage: true, scale: "css" });
});

test("home: every live call failing leaves the name, the sentence, the actions and the tools; no error card", async ({ context, page, isMobile }) => {
  await serveFixtures(context);
  await context.route(/\/api\/(ros|about|record|blog|matchups)/, (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "down" }) }));
  await size(page, isMobile);
  await page.goto("/home");
  await expect(page.getByTestId("home-hero")).toBeVisible();
  await expect(page.getByTestId("home-tools")).toBeVisible();
  await page.waitForTimeout(500);
  for (const id of ["home-top", "home-matchups", "home-record", "home-blog", "error-card"]) await expect(page.getByTestId(id)).toHaveCount(0);
  await noSidewaysScroll(page);
});

for (const [label, w, h] of [["desktop", 1300, 700], ["phone", 375, 667]] as const) {
  test(`setup on a ${label} (${w} × ${h}): after Find my leagues the first league row is in view, focus on the results`, async ({ context, page }, info) => {
    test.skip(info.project.name !== (label === "desktop" ? "desktop" : "phone"), "one size per project");
    await serveFixtures(context);
    let release: () => void = () => {};
    const held = new Promise<void>((r) => (release = r));
    await context.route(/\/api\/leagues\?username=/, async (route) => {
      await held; // the loading state is visible while the answer is held
      return route.fallback();
    });
    await page.setViewportSize({ width: w, height: h });
    await page.goto("/leagues");
    await expect(page.getByTestId("username-form")).toBeVisible();
    await expect(page.getByTestId("to-home")).toHaveAttribute("href", "/home");
    if (label === "desktop") await expect(page.getByTestId("setup-results-empty")).toBeVisible();
    await page.getByTestId("username").fill("fixture_user");
    await page.getByTestId("username-go").click();
    await expect(page.getByTestId("username-go")).toHaveText("Looking…");
    await expect(page.getByTestId("username-go")).toBeDisabled();
    release();
    await expect(page.getByTestId("league-row")).toHaveCount(3);
    await page.waitForTimeout(300); // the scroll after the list renders
    await inView(page, "league-row", 0);
    await expect(page.getByTestId("setup-results")).toBeFocused();
    if (label === "desktop") {
      // beside the form: the field and the first row both in view, nothing scrolled
      await inView(page, "username");
      expect(await page.evaluate(() => scrollY)).toBe(0);
    }
    await noSidewaysScroll(page);
    await page.screenshot({ path: join(SHOTS, `leagues-after-search-${info.project.name}.png`), fullPage: false, scale: "css" });
    // a username with no league this season: said in the same place
    await page.route(/\/api\/leagues\?username=/, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { user_id: "1", username: "empty_one", display_name: "Empty One", avatar: null }, season: 2026, leagues: [] }) }),
    );
    if (label === "phone") await page.evaluate(() => scrollTo(0, 0));
    await page.getByTestId("username").fill("empty_one");
    await page.getByTestId("username-go").click();
    await expect(page.getByTestId("no-leagues")).toContainText("No leagues for that username this season.");
    await page.waitForTimeout(300);
    await inView(page, "no-leagues");
  });
}

test("blog: the list, a post at a readable measure, share = copy link, a table that scrolls by itself, a player link opens the drawer, one page view per post", async ({ context, page, isMobile }, info) => {
  await api(context);
  await context.route(/\/api\/health$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, version: "fixture-in1" }) }));
  await context.route(/^https:\/\/www\.googletagmanager\.com\//, (route) => route.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
  await context.addInitScript(() => ((window as unknown as { __llGa: string }).__llGa = "on"));
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await size(page, isMobile);
  await page.goto("/blog");
  await expect(page.getByTestId("blog-item")).toHaveCount(2);
  await expect(page.getByTestId("blog-item").first()).toContainText("How to read this site's numbers");
  await expect(page.getByTestId("blog-item").first()).toContainText("Oct 6, 2026 · 4 min read");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `blog-${info.project.name}.png`), fullPage: false, scale: "css" });

  await page.getByTestId("blog-item").first().click();
  await expect(page).toHaveURL(new RegExp(`/blog/${SLUG}$`));
  await expect(page.getByTestId("post-title")).toHaveText("How to read this site's numbers");
  await expect(page.getByTestId("post-meta")).toContainText("By isuckatfantasy");
  await expect(page.getByTestId("post-body").locator("h2").first()).toHaveText("A projection is the middle, not a promise");
  await expect(page).toHaveTitle("How to read this site's numbers · isuckatfantasy");
  // a readable measure at 1300: the text column is at most ~45rem wide
  if (!isMobile) expect((await page.getByTestId("post-body").boundingBox())!.width).toBeLessThanOrEqual(720);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `post-${info.project.name}.png`), fullPage: false, scale: "css" });
  await page.getByTestId("post-share").click();
  await expect(page.getByTestId("post-share")).toHaveText("Link copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(`${new URL(page.url()).origin}/blog/${SLUG}`);

  // the second post: every piece, raw HTML as text, a table that scrolls inside itself, our pictures only
  await page.getByTestId("post-more").getByRole("link", { name: DEMO.title }).click();
  const body = page.getByTestId("post-body");
  await expect(body.locator("ol li")).toHaveCount(2);
  await expect(body.locator("blockquote strong")).toHaveText("bold");
  await expect(body.locator("hr")).toHaveCount(1);
  await expect(body.locator("code").first()).toHaveText("code <b>");
  await expect(body.locator("script")).toHaveCount(0);
  await expect(body).toContainText("<script>window.__pwned = 1</script>");
  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
  await expect(body.locator("img.ll-md-img")).toHaveCount(1);
  await expect(body.locator("img.ll-md-img")).toHaveAttribute("src", "/blog/img/chart-1.png");
  await expect(body.locator('img[src^="https://evil"]')).toHaveCount(0);
  // the players block: those two players' Stats rows, the three columns asked for, on Half PPR
  const live = page.getByTestId("post-players");
  await expect(live.getByTestId("players-table-row")).toHaveCount(2);
  await expect(live.getByTestId("players-table-row").first()).toContainText("Puka Nacua");
  await expect(live.getByTestId("sort-target_share")).toBeVisible();
  await expect(page.getByTestId("post-players-note")).toContainText("Half PPR");
  const table = body.locator(".ll-md-table");
  await expect(table.locator("tbody tr")).toHaveCount(2);
  if (isMobile) {
    const { sw, cw } = await table.evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }));
    expect(sw, "the table is wider than its box at 375: it scrolls inside itself").toBeGreaterThan(cw);
  }
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `post-demo-full-${info.project.name}.png`), fullPage: true, scale: "css" });
  // a player link opens the drawer, in Half PPR
  await body.locator(".ll-prose").getByRole("link", { name: "Puka Nacua" }).first().click();
  await expect(page.getByTestId("pane")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/blog/${DEMO.slug}\\?.*pane=${PUKA}`));

  // GA: one page_view per post path (ids only: the post's path, no query beyond the league)
  const views = await page.evaluate(() =>
    Array.from((window as unknown as { dataLayer?: ArrayLike<unknown>[] }).dataLayer ?? [], (a) => Array.from(a))
      .filter((c) => c[0] === "event" && c[1] === "page_view")
      .map((c) => String((c[2] as Record<string, unknown>).page_path)),
  );
  expect(views.filter((p) => p === `/blog/${SLUG}`)).toHaveLength(1);
  expect(views.filter((p) => p === `/blog/${DEMO.slug}`)).toHaveLength(1);
});

test("blog: an unknown post says so; an empty blog says so; no error card", async ({ context, page }) => {
  await api(context);
  await page.goto("/blog/no-such-post");
  await expect(page.getByTestId("post-missing")).toContainText("No post at that address.");
  await context.route(/\/api\/blog\?/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ posts: [] }) }));
  await page.goto("/blog");
  await expect(page.getByTestId("blog-empty")).toBeVisible();
  await expect(page.getByTestId("error-card")).toHaveCount(0);
});

test("menu: Home and Blog are one tap from any screen", async ({ context, page }) => {
  await api(context);
  await page.goto("/players?league=ref:half");
  await page.getByTestId("overflow").click();
  await expect(page.getByTestId("menu-home")).toHaveAttribute("href", "/home?league=ref%3Ahalf");
  await page.getByTestId("menu-blog").click();
  await expect(page).toHaveURL(/\/blog$/);
  await expect(page.getByTestId("blog")).toBeVisible();
});

test("markdown documents: escaped first, only our tags", async () => {
  test.skip(test.info().project.name !== "desktop", "pure code: once is enough");
  const { mdDoc } = await import("../../src/lib/md");
  const html = mdDoc('# T\n<b onclick="x">hi</b> [x](javascript:alert(1)) [y](//evil.example) ![z](/blog/img/../../x.png)\n\n```\n<script>\n```', { league: "ref:half" });
  expect(html).not.toMatch(/<b |<script|javascript:|evil\.example|<img/);
  expect(html).toContain("<h2>T</h2>");
  expect(html).toContain("&lt;b onclick=&quot;x&quot;&gt;hi&lt;/b&gt;");
  expect(html).toContain('<pre class="ll-md-code"><code>&lt;script&gt;</code></pre>');
  expect(mdDoc("[P](/player/00-0039075)", { league: "ref:half" })).toContain('href="/player/00-0039075?league=ref%3Ahalf"');
  // ---- IN-1 fix round (review nit): a link's target is a plain, checked address — a picture, code, bold or italic
  // written inside it never lands in the href
  const { md } = await import("../../src/lib/md");
  const inside = mdDoc("[x](/p![a](/blog/img/a.png)) [y](/q`c`) [z](/r**b**) [w](/s *i* t) and **[bold link](/players)** *[it](/trends)*", { league: "ref:half" });
  const hrefs = [...inside.matchAll(/href="([^"]*)"/g)].map((m) => m[1]);
  for (const h of hrefs) expect(h, h).not.toMatch(/[<>]/);
  expect(inside).not.toMatch(/href="[^"]*(<img|<code|<strong|<em)/);
  expect(inside).toContain('<strong><a href="/players?league=ref%3Ahalf" class="ll-link">bold link</a></strong>');
  expect(inside).toContain('<em><a href="/trends?league=ref%3Ahalf" class="ll-link">it</a></em>');
  expect(inside).not.toMatch(/href="\/p[?"]/); // a picture inside the target: the words, not a link
  expect(md("[z](/r**b**)", { league: "1" })).not.toMatch(/href="[^"]*<strong/);
  expect(md("**[Puka](/player/00-0039075)**", { league: "1" })).toBe('<strong><a href="/player/00-0039075?league=1" class="ll-link">Puka</a></strong>');
  expect(md("a \uE0010\uE001 b [x](/y)", {})).not.toContain("\uE001");
});

test("home: a matchup's line is the defense's, plus the corner's only when the call is likely", async () => {
  test.skip(test.info().project.name !== "desktop", "pure code: once is enough");
  const { homeWords } = await import("../../src/components/home/home");
  const ctx = (certainty: "likely" | "unclear" | "no call") => ({
    context: {
      opponent: "KC", home: true, tone: "difficult" as const, words: "the board's long sentence",
      defense: { tone: "neutral" as const, tough_rank: 12, n_ranked: 32, words: "Kansas City is in the middle against receivers" },
      cb: { tone: "difficult" as const, certainty, corner: "Trent McDuffie", corner_rank: 2, shutdown: true, words: "he is likely to face Trent McDuffie, a shutdown corner" },
    },
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect(homeWords(ctx("likely") as any)).toBe("Kansas City is in the middle against receivers. He is likely to face Trent McDuffie, a shutdown corner.");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect(homeWords(ctx("unclear") as any)).toBe("Kansas City is in the middle against receivers.");
});
