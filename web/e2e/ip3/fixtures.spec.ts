// Wave I-P (IP-3): Trends, graded. "Below / above expectation" was graded against the projection made before each next
// game (docs/METRICS.md § "Trends and the role trend, graded"): the gap closes in part the next week, and the
// projection already expects that — so the screen stops implying "buy low / sell high". With the record, Trends' head
// carries the record's line under its title and "How to read this" its full sentence; the picked player's line says
// "what happened, and his projection already counts it" with or without the record. The Trends answer is the dynasty
// league's recording (web/fixtures/trends_<id>.json) with `record` set the way the API sets it (`summary()["trend"]`,
// recorded from the fixture API on :8963 against league_lab_im4: web/fixtures/ip3/context_record.json, trimmed to what
// the screen reads). Phone at 375 and desktop at 1300; JPEG screenshots into docs/handbacks/ip3/.
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, SCRUBS, serveFixtures } from "../fixtures";
import { serveDecisions } from "../decisions-fixtures";

const FIX = join(import.meta.dirname, "..", "..", "fixtures");
const SHOTS = process.env.SHOTS_IP3 ?? join(import.meta.dirname, "..", "..", "..", "docs", "handbacks", "ip3");
mkdirSync(SHOTS, { recursive: true });
const RECORD = JSON.parse(readFileSync(join(FIX, "ip3", "context_record.json"), "utf8"));
const TRENDS = readFileSync(join(FIX, `trends_${DYNASTY}.json`), "utf8");
const PROMISE = /\b(due for|running hot|buy low|buy him|sell high|bounce back)\b/i;

async function trendsApi(context: BrowserContext, record: unknown | undefined) {
  await context.route(/\/api\/trends(\?|$)/, async (route: Route) => {
    const body = JSON.parse(TRENDS);
    if (record !== undefined) body.record = record;
    await route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(body) });
  });
}

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function size(page: Page, name: string) {
  if (name === "phone") await page.setViewportSize({ width: 375, height: 812 });
}

test("Trends with the record: the grade under the title, words that send you to the projection", async ({ page, context }, info) => {
  expect(RECORD.trend.graded).toBe(true);
  expect(RECORD.trend.head).toMatch(/^Graded on 2025 and 2026 weeks 1–4 \(Half PPR\): in their next game, players below expectation scored/);
  await serveFixtures(context);
  await trendsApi(context, RECORD.trend);
  await size(page, info.project.name);
  await page.goto(`/trends?league=${DYNASTY}&team=12`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Below and above expectation");
  await expect(page.getByTestId("trends-record")).toHaveText(RECORD.trend.head);
  await expect(page.getByTestId("answer")).toContainText("Below expectation:");
  await expect(page.getByTestId("trends-list").locator("li").first()).toBeVisible();
  if (info.project.name === "desktop") {
    // the picked player's line: what happened, already in his projection (never "an observed gap" or "due")
    await expect(page.getByTestId("trends-detail")).toContainText("his projection already counts it");
  }
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `ip3-trends-${info.project.name}.jpg`), type: "jpeg", quality: 70, scale: "css", fullPage: false });
  // How to read this: the graded sentence and no promise
  await page.getByTestId("howto").locator("summary").click();
  const howto = page.getByTestId("howto");
  await expect(howto).toContainText("Graded on past weeks, players like him scored more the next week");
  await expect(howto).toContainText("not a reason to buy on its own");
  await expect(howto).toContainText(`Graded: ${RECORD.trend.words.replace(/\.$/, "")}`);
  expect((await page.getByTestId("trends").innerText()).match(PROMISE)).toBeNull();
  if (info.project.name === "phone") {
    await howto.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(SHOTS, `ip3-trends-howto-phone.jpg`), type: "jpeg", quality: 70, scale: "css", fullPage: false });
  }
});

test("Trends without the record: no grade line, the same honest words", async ({ page, context }, info) => {
  await serveFixtures(context);
  await trendsApi(context, { graded: false, n: 0, words: null, head: null, tags: {} });
  await size(page, info.project.name);
  await page.goto(`/trends?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("trends-list").locator("li").first()).toBeVisible();
  await expect(page.getByTestId("trends-record")).toHaveCount(0);
  if (info.project.name === "desktop") await expect(page.getByTestId("trends-detail")).toContainText("his projection already counts it");
  await page.getByTestId("howto").locator("summary").click();
  await expect(page.getByTestId("howto")).toContainText("about as much as their projection already expected");
  await expect(page.getByTestId("howto")).not.toContainText("Graded:");
  expect((await page.getByTestId("trends").innerText()).match(PROMISE)).toBeNull();
  await noSideways(page);
});

test("Trends from an API without the record key (an older deploy): the screen stands", async ({ page, context }, info) => {
  await serveFixtures(context);
  await trendsApi(context, undefined);
  await size(page, info.project.name);
  await page.goto(`/trends?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("trends-list").locator("li").first()).toBeVisible();
  await expect(page.getByTestId("trends-record")).toHaveCount(0);
  await noSideways(page);
});

// ---- IP-3 fix round (Wave I-P): the grade where the app still implied otherwise — the Trades lists renamed with the
// record's line, the role trend's grade on DFS (the chip's detail and "What the projection already holds") and on Stats
// ("Role change", How to read this). DFS answers: IO-1's recording (web/fixtures/io1/projections_dk.json) with the
// record's role sentence set the way the API sets it (`dfs.context_for`); Stats: IO-4's recording (fixtures/io4) with the
// catalogue's Role change columns carrying `graded` as `stats.catalogue` does.
const ROLE = RECORD.role.words as string;
const NEVER_TRADE = /\b(buy low|sell high|buy him|sell him|due for|bargain|regression candidate|should turn around)\b/i;

test("Trades: the lists named for what they are, the record's line under the heading, no buy / sell on the gap", async ({ page, context }, info) => {
  await serveFixtures(context);
  await serveDecisions(context); // the Trades screen's partner finder (IA-2's recordings)
  await size(page, info.project.name);
  const tl = JSON.parse(readFileSync(join(FIX, `trades_lists_${SCRUBS}_2.json`), "utf8"));
  await page.goto(`/trades?league=${SCRUBS}&team=2`);
  const bs = page.getByTestId("buy-sell");
  await expect(bs).toBeVisible();
  await expect(bs.getByRole("heading", { level: 2 }).first()).toHaveText("Scoring below or above their work");
  await expect(page.getByTestId("gap-line")).toHaveText(tl.gap_line);
  expect(tl.gap_line).toMatch(/^Their projections already expect the gap to close part-way: no edge in buying or selling on it — graded on 4,282 games/);
  await expect(page.getByTestId("buy-low")).toContainText("Scoring below his work");
  await expect(page.getByTestId("sell-high")).toContainText("Scoring above his work");
  await expect(page.getByTestId("buy-line")).toContainText("the fit, from the projections, is the reason to ask about him — not the gap");
  await page.getByTestId("howto").locator("summary, button").first().click();
  await expect(page.getByTestId("howto")).toContainText("so it is no reason to trade on its own");
  expect((await page.locator("main").innerText()).match(NEVER_TRADE)).toBeNull();
  await noSideways(page);
  await bs.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `ip3-trades-${info.project.name}.jpg`), type: "jpeg", quality: 70, scale: "css", fullPage: false });
});

test("DFS: the role chip's detail and the holds panel carry the record's grade of the role trend", async ({ page, context }, info) => {
  const board = JSON.parse(readFileSync(join(FIX, "io1", "projections_dk.json"), "utf8"));
  board.context_meta.role_record = ROLE;
  for (const r of board.players) for (const s of r.context ?? []) if (s.signal === "role") s.graded = ROLE;
  await serveFixtures(context);
  await context.route(/\/api\/(dfs|context)\//, async (route: Route) => {
    const url = new URL(route.request().url());
    const send = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(body) });
    if (url.pathname === "/api/dfs/projections") return send(board);
    if (url.pathname === "/api/dfs/slates") return send({ season: 2026, week: 4, slates: [], not_offered: [], unreadable: [] });
    if (url.pathname === "/api/context/record") return send(RECORD);
    return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  await size(page, info.project.name);
  await page.goto("/dfs");
  await expect(page.getByTestId("dfs-proj-row").first()).toBeVisible();
  await page.getByTestId("dfs-holds").locator("summary").click();
  await expect(page.getByTestId("dfs-role-record")).toHaveText(ROLE);
  const row = page.getByTestId("dfs-proj-row").filter({ has: page.locator("[data-testid=dfs-chip][data-signal=role]") }).first();
  await row.getByTestId("dfs-proj-open").click();
  await expect(row.locator("[data-signal=role]").getByTestId("dfs-signal-graded")).toHaveText(ROLE);
  await noSideways(page);
});

test("Stats: the Role change group's help carries the record's grade (and nothing without it)", async ({ page, context }, info) => {
  const rec = JSON.parse(readFileSync(join(FIX, "io4", "api_io4.json"), "utf8"));
  const key = Object.keys(rec).find((k) => k.startsWith("/api/players?") && k.includes("window=season"))!;
  const withGrade = JSON.parse(JSON.stringify(rec[key].body));
  for (const c of withGrade.catalogue) if (c.group === "Role change") c.graded = ROLE;
  for (const graded of [true, false]) {
    await context.unrouteAll({ behavior: "ignoreErrors" });
    await serveFixtures(context);
    await context.route(/\/api\/players\?/, (route: Route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(graded ? withGrade : rec[key].body) }),
    );
    await size(page, info.project.name);
    await page.goto("/players?league=ref:half&position=WR&view=full");
    await expect(page.getByTestId("players-table-row").first()).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("howto").locator("summary").click();
    if (graded) {
      await expect(page.getByTestId("stats-role-record")).toHaveText(`Role change, graded: ${ROLE}`);
      await page.getByTestId("stats-role-record").scrollIntoViewIfNeeded();
      if (info.project.name === "phone") await page.screenshot({ path: join(SHOTS, "ip3-stats-role-phone.jpg"), type: "jpeg", quality: 70, scale: "css", fullPage: false });
    } else await expect(page.getByTestId("stats-role-record")).toHaveCount(0);
    await noSideways(page);
  }
});
// ---- end IP-3 fix round
