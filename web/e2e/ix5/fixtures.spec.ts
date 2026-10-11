// Wave I-X (IX-5): what we claim, said once and truly; a simpler menu (the review of 10 October § 4, § 5 and its
// "Proposed simpler structure"). Phone at 375 (no sideways page scroll) and desktop at 1300; screenshots into
// docs/handbacks/ix5/ (SHOTS_IX5) or e2e/.out.
//
// Recorded answers (web/fixtures/ix5/api_ix5.json) from this branch's API on league_lab_iq4 at the PO's Saturday clock
// (2026-10-10T16:00Z): GET /api/waivers for League of Scrubs team 2 and POST /api/trades/evaluate for the review's
// known trade (team 2 gives Folk to team 3 for Stafford + Reichard, the next four weeks). Everything else from the
// fixture API (e2e/fixtures.ts, e2e/decisions-fixtures.ts).
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { DYNASTY, SCRUBS, serveFixtures } from "../fixtures";

const RECORDED = join(import.meta.dirname, "..", "..", "fixtures", "ix5", "api_ix5.json");
const SHOTS = process.env.SHOTS_IX5 ?? join(import.meta.dirname, "..", ".out");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const rec = JSON.parse(readFileSync(RECORDED, "utf8")) as Record<string, any>;
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
const GUIDE = "Kickers and defenses are judged on this week only: their projections are a rough guide (weakly graded for next week, no better than chance after).";

async function recorded(context: BrowserContext, waivers: unknown = rec.waivers) {
  await context.route(/\/api\/waivers\?/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(waivers) }),
  );
  await context.route(/\/api\/trades\/evaluate/, (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(rec.evaluate) })
      : route.fallback(),
  );
}

test.beforeEach(async ({ context, page }, info) => {
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PNG }));
  await serveFixtures(context);
  await serveDecisions(context);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string, full = false) =>
  page.screenshot({ path: join(SHOTS, `ix5-${name}-${project === "phone" ? "375" : "1300"}.jpg`), type: "jpeg", quality: 70, fullPage: full });

test("the menu with a league: My Week · Waivers · Trades · Research; DFS in the ⋯ menu, its route unchanged", async ({ page }, info) => {
  await page.goto(`/?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("my-week")).toBeVisible();
  await expect(page.getByTestId("tabs").locator("a")).toHaveText(["My Week", "Waivers", "Trades", "Research"]);
  await expect(page.getByTestId("tab-dfs")).toHaveCount(0);
  await page.getByTestId("overflow").click();
  const dfs = page.getByTestId("menu-dfs");
  await expect(dfs).toBeVisible();
  await expect(dfs).toHaveAttribute("href", new RegExp(`^/dfs\\?league=${DYNASTY}&team=12`));
  await noSideways(page);
  await shot(page, "menu-league", info.project.name);
  await page.keyboard.press("Escape");
  await page.getByTestId("tab-players").click();
  await expect(page.getByTestId("subtabs").locator("a")).toHaveText(["Stats", "Rankings", "Trends", "Matchups", "Compare"]);
  await expect(page.getByTestId("tab-players")).toHaveAttribute("aria-current", "page");
  await page.getByTestId("overflow").click();
  await page.getByTestId("menu-dfs").click();
  await expect(page).toHaveURL(new RegExp(`/dfs\\?league=${DYNASTY}&team=12`));
  await expect(page.getByTestId("dfs")).toBeVisible();
});

test("the menu without a league: Home · Rankings · Research · Trades; DFS in the ⋯ menu", async ({ page }, info) => {
  await page.goto("/players?league=ref:half");
  await expect(page.getByTestId("tabs").locator("a")).toHaveText(["Home", "Rankings", "Research", "Trades"]);
  await expect(page.getByTestId("tab-players")).toHaveAttribute("aria-current", "page");
  await page.getByTestId("overflow").click();
  await expect(page.getByTestId("menu-dfs")).toBeVisible();
  await noSideways(page);
  await shot(page, "menu-browsing", info.project.name);
});

test("Waivers: no table's name; a kicker or defense is never among the strongest on the window's gain", async ({ context, page }, info) => {
  await recorded(context);
  await page.goto(`/waivers?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("top3")).toBeVisible();
  const top = rec.waivers.top3 as { move: { add: { position: string } }; guide?: string }[];
  expect(top.filter((c) => ["K", "DEF"].includes(c.move.add.position) && !c.guide)).toHaveLength(0);
  await expect(page.getByTestId("top-move")).toHaveCount(top.length);
  await expect(page.getByTestId("top3").locator("h2")).toHaveText("The three strongest moves");
  await expect(page.getByTestId("claim-guide")).toHaveCount(0);
  const note = page.getByTestId("recent-adds-note");
  if (await note.count()) {
    await expect(note).toContainText("Sleeper transactions");
    await expect(note).not.toContainText(/analytics\.|mart_/);
  }
  await expect(page.locator("main")).not.toContainText(/analytics\.|mart_/);
  await noSideways(page);
  await shot(page, "waivers", info.project.name, true);
});

test("Waivers (MFL 70587, Big Mac Attack): a defense's card when the graded positions leave room — this week, a rough guide, last", async ({ context, page }, info) => {
  // The recorded answer: two graded claims (the Cardinals' team QB, Mitchell), then the Saints defense on this week's
  // gain (+0.15) with the guide (decisions.ix5_kd_last / ix5_guide_card).
  const w = rec.waivers_mfl8;
  const last = w.top3[w.top3.length - 1];
  expect(last.move.add.position).toBe("DEF");
  expect(last.guide).toBe(GUIDE);
  await recorded(context, w);
  await page.goto("/waivers?league=mfl%3A70587&team=8");
  await expect(page.getByTestId("top3").locator("h2")).toHaveText("The two strongest moves");
  const card = page.getByTestId("top-move-wrap").last();
  await expect(card.getByTestId("claim-add")).toHaveText(last.move.add.player_name);
  await expect(card.getByTestId("claim-guide")).toHaveText(GUIDE);
  await expect(card.getByTestId("top-move-horizon")).toHaveText(/: a rough guide$/);
  await expect(card.getByTestId("claim-total")).toHaveCount(0);
  await expect(page.getByTestId("top-move-wrap").first().getByTestId("claim-guide")).toHaveCount(0);
  await expect(page.getByTestId("waiver-answer")).toHaveText("The two strongest claims below: each helps this week. Each card's total is its gain over weeks 5–8. After them, a kicker or defense for this week only: a rough guide.");
  await expect(page.locator("main")).not.toContainText(/analytics\.|mart_/);
  await noSideways(page);
  await shot(page, "waivers-guide", info.project.name, true);
});

test("the calculator: the trust line names each position's verdict; the window says what is checked", async ({ context, page }, info) => {
  await recorded(context);
  await page.goto(`/trade-calc?league=${SCRUBS}&team=2&partner=3&give=650&get=421,11792`);
  const line = page.getByTestId("trade-provenance-line");
  await expect(line).toBeVisible({ timeout: 30_000 });
  await expect(line).toContainText("two to eight weeks ahead: quarterbacks weak, kickers no better than chance");
  await expect(line).not.toContainText("two to eight weeks ahead no better than chance, quarterbacks weak");
  const cap = page.getByTestId("window-caption");
  await expect(cap).toContainText("running backs, receivers and tight ends graded; quarterbacks a lean, level with their own record; kickers and defenses a rough guide");
  await expect(page.locator("main")).not.toContainText("near enough to trust");
  await noSideways(page);
  await line.scrollIntoViewIfNeeded();
  await shot(page, "calc-trust", info.project.name);
});

test("Matchups: a defense's rank runs one way (1 = gives up the most); no 'toughest' numbering", async ({ page }, info) => {
  await page.goto(`/matchups?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("matchups-answer")).toBeVisible();
  await expect(page.getByTestId("matchups-answer")).not.toContainText(/\d(st|nd|rd|th)-fewest/);
  const chips = page.getByTestId("starters").getByTestId("rank-small");
  expect(await chips.count()).toBeGreaterThan(0);
  for (const c of await chips.all()) await expect(c).toHaveText(/^#\d+ of \d+ vs (QB|RB|WR|TE)$/);
  await expect(page.locator("main")).not.toContainText(/toughest vs|\d(st|nd|rd|th)-fewest/);
  await expect(page.getByTestId("howto")).toContainText("#1 gives up the most points to the position");
  await noSideways(page);
  await shot(page, "matchups", info.project.name);
});
